"""退院カレンダー描画（🏥 退院調整 > 📅 退院カレンダー タブ）.

副院長のベッドコントロール業務を支援するための月俯瞰カレンダー。
- 退院予定を 3 層（調整中 / 予定 / 決定）で可視化
- 入院予定を重ね表示（退院と入院のバランスを一目で把握）
- 日曜枠の空きを強調（副院長指示: 日曜退院を推奨）
- 当月・翌月のタブ切替、病棟別タブ（5F / 6F）

データソース
-------------
- ``discharge_plan_store.load_all_plans()``: 退院予定（UUID → plan dict）
- ``patient_status_store.load_all_statuses()``: 調整中判定（"new" 以外 = 調整中）
- ``admission_details_df``: UUID → 病棟 map、入院予定（未来日 admission）、緊急入院実績
- ``discharge_slot_config``: 枠ルール（月〜土 5 / 日祝 2）

2026-04-23 副院長判断に基づく実装
----------------------------------
- 月〜土 5 枠、日祝 2 枠（固定）
- 日曜マスは視覚的に強調（推奨マーカー）
- 入院予定 ≈ 退院予定のバランスを各日に「入/退/差」で表示
- 超過時はセル背景色を変えて警告
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

_DOW_JA = ["月", "火", "水", "木", "金", "土", "日"]

# -----------------------------------------------------------------------------
# データ構築ヘルパー
# -----------------------------------------------------------------------------


def _build_patient_ward_map(
    admission_details_df: Optional[pd.DataFrame],
) -> Dict[str, str]:
    """入院詳細 DataFrame から UUID 先頭 8 桁 → 病棟名 の map を構築.

    同じ患者が再入院した場合は最新のレコードで上書き（現在入院中の病棟を反映）。
    """
    if admission_details_df is None or len(admission_details_df) == 0:
        return {}
    if "id" not in admission_details_df.columns:
        return {}
    if "ward" not in admission_details_df.columns:
        return {}

    # 入院イベントのみに絞る（退院イベントでも同じ patient_id だが、入院側を使う）
    if "event_type" in admission_details_df.columns:
        df = admission_details_df[admission_details_df["event_type"] == "admission"]
    else:
        df = admission_details_df
    if len(df) == 0:
        return {}

    # 日付で昇順ソートし、最新の ward で上書き
    if "date" in df.columns:
        df = df.sort_values("date")

    mp: Dict[str, str] = {}
    for _, row in df.iterrows():
        pid = str(row["id"])
        if len(pid) >= 8:
            mp[pid[:8]] = str(row["ward"])
    return mp


def _count_discharge_plans_for_cell(
    plans: Dict[str, Dict[str, Any]],
    ward_map: Dict[str, str],
    status_map: Dict[str, str],
    target_ward: str,
    target_date: date,
) -> Dict[str, int]:
    """指定日・病棟の退院予定を 3 層でカウント.

    Returns
    -------
    dict
        - ``adjusting``: 調整中の患者数（status が new 以外だが予定日は未設定）
        - ``scheduled``: 退院予定日ありで未確定（confirmed=False）
        - ``confirmed``: 退院決定（confirmed=True）
        - ``unplanned``: 突発退院マーカー付き（重複カウントあり、上 3 つに含まれる）
    """
    iso = target_date.isoformat()
    counts = {"adjusting": 0, "scheduled": 0, "confirmed": 0, "unplanned": 0}
    for uuid, plan in plans.items():
        if ward_map.get(uuid) != target_ward:
            continue
        sd = plan.get("scheduled_date")
        if sd != iso:
            continue
        if plan.get("confirmed"):
            counts["confirmed"] += 1
        else:
            counts["scheduled"] += 1
        if plan.get("unplanned"):
            counts["unplanned"] += 1
    return counts


def _count_adjusting_patients_for_ward(
    ward_map: Dict[str, str],
    status_map: Dict[str, str],
    plans: Dict[str, Dict[str, Any]],
    target_ward: str,
) -> int:
    """指定病棟で「調整中」（new 以外 かつ scheduled_date 未設定）の患者数.

    カレンダーの特定セルには乗らないが、病棟サマリーで「この病棟で
    予定日未定の調整中が N 名います」と表示するために使う。
    """
    count = 0
    for uuid, status in status_map.items():
        if ward_map.get(uuid) != target_ward:
            continue
        if status == "new":
            continue
        plan = plans.get(uuid)
        if plan is not None and plan.get("scheduled_date"):
            # 予定日が設定済みなら scheduled または confirmed に含まれる
            continue
        count += 1
    return count


def _count_scheduled_admissions_for_cell(
    admission_details_df: Optional[pd.DataFrame],
    target_date: date,
    target_ward: str,
) -> int:
    """指定日・病棟の予定入院数を admission_details_df から集計.

    ``event_type == "admission"`` かつ ``date == target_date`` かつ
    ``ward == target_ward`` の件数を返す。将来日にレコードがあれば予約入院として扱う。
    """
    if admission_details_df is None or len(admission_details_df) == 0:
        return 0
    required_cols = {"event_type", "date", "ward"}
    if not required_cols.issubset(admission_details_df.columns):
        return 0

    mask = (
        (admission_details_df["event_type"] == "admission")
        & (admission_details_df["ward"] == target_ward)
    )
    subset = admission_details_df[mask]
    if len(subset) == 0:
        return 0

    # date は文字列または date 型の可能性。両対応
    target_iso = target_date.isoformat()
    # pd.to_datetime で正規化
    try:
        dates = pd.to_datetime(subset["date"]).dt.date
    except (ValueError, TypeError):
        return 0
    return int((dates == target_date).sum())


def _estimate_emergency_admissions_by_dow(
    admission_details_df: Optional[pd.DataFrame],
    target_ward: str,
) -> Dict[int, float]:
    """病棟別・曜日別の緊急入院平均数を過去実績から算出.

    「予定入院」と「緊急入院」の区別が admission_details_df にない場合、
    全入院数の曜日別平均を返す（予約分はカレンダー上で明示される）。

    Returns
    -------
    dict
        ``{0: 平均数/月, 1: ..., ..., 6: ...}``。月〜日の weekday 番号をキーに平均値。
    """
    if admission_details_df is None or len(admission_details_df) == 0:
        return {i: 0.0 for i in range(7)}
    required_cols = {"event_type", "date", "ward"}
    if not required_cols.issubset(admission_details_df.columns):
        return {i: 0.0 for i in range(7)}

    mask = (
        (admission_details_df["event_type"] == "admission")
        & (admission_details_df["ward"] == target_ward)
    )
    subset = admission_details_df[mask]
    if len(subset) == 0:
        return {i: 0.0 for i in range(7)}

    try:
        dts = pd.to_datetime(subset["date"])
    except (ValueError, TypeError):
        return {i: 0.0 for i in range(7)}

    # 日単位に集計 → 曜日別平均
    by_day = subset.assign(_date=dts.dt.date).groupby("_date").size()
    all_days = pd.date_range(dts.min(), dts.max()).date
    daily_series = pd.Series(index=all_days, dtype=float)
    for d in all_days:
        daily_series[d] = float(by_day.get(d, 0))

    by_dow: Dict[int, float] = {}
    for i in range(7):
        same_dow = [daily_series[d] for d in all_days if d.weekday() == i]
        by_dow[i] = round(sum(same_dow) / len(same_dow), 2) if same_dow else 0.0
    return by_dow


# -----------------------------------------------------------------------------
# カレンダーグリッド生成
# -----------------------------------------------------------------------------


def _get_month_weeks(year: int, month: int) -> List[List[date]]:
    """指定月の週リスト（月曜始まり、各週 7 日）."""
    cal = calendar.Calendar(firstweekday=0)
    return cal.monthdatescalendar(year, month)


def _find_previous_business_day(
    target_date: date,
    jp_holidays: set,
) -> date:
    """指定日の「前営業日」を返す（日曜・祝日を飛ばす）.

    平日/土曜は通常通り前日。前日が日曜・祝日なら、さらに 1 日ずつ遡る。
    """
    prev = target_date - timedelta(days=1)
    while prev.weekday() == 6 or prev in jp_holidays:
        prev = prev - timedelta(days=1)
    return prev


def _precompute_daily_discharge_counts(
    plans: Dict[str, Dict[str, Any]],
    ward_map: Dict[str, str],
    status_map: Dict[str, str],
    ward: str,
    start_date: date,
    end_date: date,
) -> Dict[date, int]:
    """期間内の各日の退院予定総数を事前計算.

    前日超過の計算に使う。各日の (scheduled + confirmed) 合計を返す。
    """
    counts: Dict[date, int] = {}
    days = (end_date - start_date).days + 1
    for i in range(days):
        d = start_date + timedelta(days=i)
        dc = _count_discharge_plans_for_cell(
            plans, ward_map, status_map, ward, d
        )
        counts[d] = dc["scheduled"] + dc["confirmed"]
    return counts


def _calculate_previous_day_excess(
    target_date: date,
    daily_counts: Dict[date, int],
    jp_holidays: set,
) -> int:
    """前営業日の枠超過分を返す.

    日曜・祝日は HOLIDAY_SLOT 固定で「繰り越しの起点にならない」仕様のため、
    前営業日（平日 or 土曜）を遡り、その日の退院数から WEEKDAY_SLOT を引いた正の値を返す。
    """
    from discharge_slot_config import WEEKDAY_SLOT
    prev = _find_previous_business_day(target_date, jp_holidays)
    prev_count = daily_counts.get(prev, 0)
    return max(0, prev_count - WEEKDAY_SLOT)


def _render_calendar_cell_html(
    cell_date: date,
    target_month: int,
    ward: str,
    plans: Dict[str, Dict[str, Any]],
    ward_map: Dict[str, str],
    status_map: Dict[str, str],
    admission_details_df: Optional[pd.DataFrame],
    emergency_dow_mean: Dict[int, float],
    today: date,
    daily_counts: Dict[date, int],
    jp_holidays: set,
    current_occupancy_rate: Optional[float] = None,
    current_vacancy_count: Optional[int] = None,
    is_holiday: bool = False,
) -> str:
    """単一セル（日付）の HTML を返す.

    Parameters
    ----------
    daily_counts : dict[date, int]
        期間内の日別退院予定数（前日超過の繰り越し計算に使う）
    current_occupancy_rate : float, optional
        現在（=今日）の稼働率。今日のセルのみ動的枠調整に反映。
    current_vacancy_count : int, optional
        現在の空床数。今日のセルのみ動的枠調整に反映。
    """
    from discharge_slot_config import (
        WEEKDAY_SLOT,
        HOLIDAY_SLOT,
        calculate_effective_slot,
        is_holiday_slot_day,
    )

    is_current_month = cell_date.month == target_month
    is_today = cell_date == today
    is_sunday_or_holiday = is_holiday_slot_day(cell_date, is_holiday)

    # 退院予定カウント
    dc = _count_discharge_plans_for_cell(
        plans, ward_map, status_map, ward, cell_date
    )
    total_discharge = dc["scheduled"] + dc["confirmed"]

    # 入院予定カウント
    sched_adm = _count_scheduled_admissions_for_cell(
        admission_details_df, cell_date, ward
    )

    # 緊急入院見込み
    dow = cell_date.weekday()
    total_adm_mean = emergency_dow_mean.get(dow, 0.0)

    # 前日超過の計算（日曜・祝日は飛ばして遡る、月初なら 0）
    prev_excess = _calculate_previous_day_excess(
        cell_date, daily_counts, jp_holidays
    )

    # 動的枠調整は今日のセルのみ反映（未来日は基本枠ベース）
    occ_for_calc = current_occupancy_rate if is_today else None
    vac_for_calc = current_vacancy_count if is_today else None

    slot = calculate_effective_slot(
        cell_date,
        previous_day_excess=prev_excess,
        occupancy_rate=occ_for_calc,
        vacancy_count=vac_for_calc,
        is_holiday=is_holiday,
    )
    remaining = slot - total_discharge
    is_over = remaining < 0

    # 色決定
    if not is_current_month:
        bg_color = "#F3F4F6"  # 月外は薄いグレー
        text_color = "#9CA3AF"
    elif is_over:
        bg_color = "#FEE2E2"  # 超過は赤
        text_color = "#991B1B"
    elif is_sunday_or_holiday:
        bg_color = "#FEF3C7"  # 日祝は黄色（推奨マーカー）
        text_color = "#78350F"
    elif total_discharge == 0 and sched_adm == 0:
        bg_color = "#FFFFFF"  # 何もない日は白
        text_color = "#1F2937"
    else:
        bg_color = "#ECFDF5"  # 予定あり通常は薄緑
        text_color = "#065F46"

    border = "3px solid #1E88E5" if is_today else "1px solid #E5E7EB"

    # 曜日ラベル
    dow_label = _DOW_JA[cell_date.weekday()]

    # 退院内訳の表示
    discharge_breakdown = ""
    if total_discharge > 0:
        parts = []
        if dc["confirmed"] > 0:
            parts.append(f'<span style="color:#065F46;font-weight:bold;">●{dc["confirmed"]}</span>')
        if dc["scheduled"] > 0:
            parts.append(f'<span style="color:#2563EB;">○{dc["scheduled"]}</span>')
        discharge_breakdown = " ".join(parts)
    else:
        discharge_breakdown = '<span style="color:#9CA3AF;">—</span>'

    # 突発退院マーカー
    unplanned_mark = ""
    if dc["unplanned"] > 0:
        unplanned_mark = f'<span style="color:#DC2626;" title="突発退院">⚡{dc["unplanned"]}</span>'

    # 入院予定表示（スケジュール済み + 緊急見込み）
    adm_display = ""
    if sched_adm > 0 or total_adm_mean > 0:
        if sched_adm > 0:
            adm_display += f'<span style="color:#7C3AED;">入{sched_adm}</span>'
        if total_adm_mean > 0 and sched_adm == 0:
            # 予約入院ゼロでも平均的な入院流入を表示
            adm_display += f'<span style="color:#9CA3AF;">入～{total_adm_mean:.1f}</span>'

    # 入退院差分（稼働率方向）
    balance = sched_adm - total_discharge
    balance_label = ""
    if total_discharge > 0 or sched_adm > 0:
        if balance > 0:
            balance_label = f'<span style="color:#059669;">↑+{balance}</span>'
        elif balance < 0:
            balance_label = f'<span style="color:#DC2626;">↓{balance}</span>'

    # 枠残り表示（動的調整 or 前日超過で枠が変わった場合は ✨ マーカー）
    base_slot = HOLIDAY_SLOT if is_sunday_or_holiday else WEEKDAY_SLOT
    slot_adjusted = slot != base_slot and not is_sunday_or_holiday
    adjust_mark = '<span title="動的調整" style="color:#7C3AED;">✨</span>' if slot_adjusted else ""
    if is_over:
        slot_label = f'{adjust_mark}<span style="color:#991B1B;font-weight:bold;">超過{abs(remaining)}</span>'
    else:
        slot_label = f'{adjust_mark}<span style="color:#6B7280;">残{remaining}/{slot}</span>'

    # 前日繰り越しマーカー
    excess_mark = ""
    if prev_excess > 0 and is_current_month and not is_sunday_or_holiday:
        excess_mark = f'<span title="前日超過繰り越し" style="color:#DC2626;">↩-{prev_excess}</span>'

    # 日曜・祝日の推奨バッジ
    recommend_badge = ""
    if is_sunday_or_holiday and is_current_month and remaining > 0:
        recommend_badge = '<div style="font-size:10px;color:#78350F;">⭐推奨枠</div>'

    # セル HTML
    html = (
        f'<div style="'
        f'background:{bg_color};'
        f'color:{text_color};'
        f'border:{border};'
        f'border-radius:6px;'
        f'padding:4px 6px;'
        f'margin:1px;'
        f'min-height:90px;'
        f'font-size:11px;'
        f'line-height:1.3;'
        f'">'
        f'<div style="display:flex;justify-content:space-between;align-items:baseline;">'
        f'<span style="font-weight:{"bold" if is_today else "normal"};font-size:13px;">{cell_date.day}</span>'
        f'<span style="color:#6B7280;font-size:9px;">{dow_label}</span>'
        f'</div>'
        f'<div style="margin-top:2px;">退: {discharge_breakdown} {unplanned_mark}</div>'
        f'<div>{adm_display} {balance_label}</div>'
        f'<div style="margin-top:2px;font-size:10px;">{slot_label} {excess_mark}</div>'
        f'{recommend_badge}'
        f'</div>'
    )
    return html


def _render_month_calendar(
    year: int,
    month: int,
    ward: str,
    plans: Dict[str, Dict[str, Any]],
    ward_map: Dict[str, str],
    status_map: Dict[str, str],
    admission_details_df: Optional[pd.DataFrame],
    emergency_dow_mean: Dict[int, float],
    today: date,
    jp_holidays: Optional[set] = None,
    current_occupancy_rate: Optional[float] = None,
    current_vacancy_count: Optional[int] = None,
) -> None:
    """1 ヶ月分のカレンダーを streamlit に描画.

    Parameters
    ----------
    current_occupancy_rate : float, optional
        今日のセルのみに適用する動的枠調整用の稼働率。
    current_vacancy_count : int, optional
        同じく今日のセルに適用する空床数。
    """
    import streamlit as st

    if jp_holidays is None:
        jp_holidays = set()

    weeks = _get_month_weeks(year, month)

    # 前日超過の計算に必要な日別退院数（期間内の全日）
    grid_start = weeks[0][0] if weeks else date(year, month, 1)
    grid_end = weeks[-1][-1] if weeks else date(year, month, 1)
    daily_counts = _precompute_daily_discharge_counts(
        plans, ward_map, status_map, ward, grid_start, grid_end
    )

    # ヘッダー（曜日ラベル）
    header_cells = []
    for i, d in enumerate(_DOW_JA):
        weekday_color = "#DC2626" if i == 6 else "#374151"  # 日曜のみ赤
        header_cells.append(
            f'<div style="text-align:center;font-weight:bold;padding:6px;'
            f'background:#F9FAFB;color:{weekday_color};border-radius:4px;">{d}</div>'
        )
    header_html = (
        '<div style="display:grid;grid-template-columns:repeat(7,1fr);gap:2px;">'
        + "".join(header_cells)
        + "</div>"
    )
    st.markdown(header_html, unsafe_allow_html=True)

    # 各週を 7 列グリッドで描画
    for week in weeks:
        row_cells = []
        for d in week:
            is_holiday = d in jp_holidays
            cell_html = _render_calendar_cell_html(
                cell_date=d,
                target_month=month,
                ward=ward,
                plans=plans,
                ward_map=ward_map,
                status_map=status_map,
                admission_details_df=admission_details_df,
                emergency_dow_mean=emergency_dow_mean,
                today=today,
                daily_counts=daily_counts,
                jp_holidays=jp_holidays,
                current_occupancy_rate=current_occupancy_rate,
                current_vacancy_count=current_vacancy_count,
                is_holiday=is_holiday,
            )
            row_cells.append(cell_html)
        row_html = (
            '<div style="display:grid;grid-template-columns:repeat(7,1fr);gap:2px;margin-bottom:2px;">'
            + "".join(row_cells)
            + "</div>"
        )
        st.markdown(row_html, unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# 月次 KPI と凡例
# -----------------------------------------------------------------------------


def _calculate_monthly_kpi(
    plans: Dict[str, Dict[str, Any]],
    ward_map: Dict[str, str],
    target_ward: str,
    year: int,
    month: int,
) -> Dict[str, int]:
    """月単位の退院 KPI を集計.

    Returns
    -------
    dict
        - ``total``: 月内の退院予定数（scheduled + confirmed 合計）
        - ``sunday_discharges``: 日曜退院予定数
        - ``unplanned_count``: 突発退院マーカー付き数
    """
    total = 0
    sunday = 0
    unplanned = 0
    for uuid, plan in plans.items():
        if ward_map.get(uuid) != target_ward:
            continue
        sd_str = plan.get("scheduled_date")
        if not sd_str:
            continue
        try:
            sd = date.fromisoformat(sd_str)
        except ValueError:
            continue
        if sd.year != year or sd.month != month:
            continue
        total += 1
        if sd.weekday() == 6:
            sunday += 1
        if plan.get("unplanned"):
            unplanned += 1
    return {"total": total, "sunday_discharges": sunday, "unplanned_count": unplanned}


def _render_legend() -> None:
    """カレンダーの凡例を描画."""
    import streamlit as st

    legend_html = (
        '<div style="display:flex;gap:16px;flex-wrap:wrap;font-size:11px;color:#6B7280;margin:8px 0;">'
        '<span><span style="color:#065F46;font-weight:bold;">●</span> 退院決定</span>'
        '<span><span style="color:#2563EB;">○</span> 退院予定</span>'
        '<span><span style="color:#DC2626;">⚡</span> 突発退院</span>'
        '<span><span style="color:#7C3AED;">入 N</span> 予定入院</span>'
        '<span><span style="color:#059669;">↑+N</span> 入院過多（稼働率↑）</span>'
        '<span><span style="color:#DC2626;">↓-N</span> 退院過多（稼働率↓）</span>'
        '<span><span style="color:#7C3AED;">✨</span> 動的枠調整（稼働率連動）</span>'
        '<span><span style="color:#DC2626;">↩-N</span> 前日超過の繰り越し</span>'
        '<span style="background:#FEF3C7;padding:2px 6px;border-radius:3px;">日曜・祝日（推奨）</span>'
        '<span style="background:#FEE2E2;padding:2px 6px;border-radius:3px;">枠超過</span>'
        "</div>"
    )
    st.markdown(legend_html, unsafe_allow_html=True)


def _get_unplanned_by_doctor(
    plans: Dict[str, Dict[str, Any]],
    admission_details_df: Optional[pd.DataFrame],
    target_ward: Optional[str] = None,
) -> Dict[str, int]:
    """突発退院マーカー付きの患者を主治医別に集計.

    主治医別に「突発退院（ルール違反的な主治医独断退院）」の件数を出す。
    副院長の運用改善要望: 主治医のうち誰が主に突発退院を発生させているかを
    見える化することで、カンファ・運用ルール周知の対象を絞る。

    Parameters
    ----------
    plans : dict
        退院予定ストアの全データ
    admission_details_df : pd.DataFrame, optional
        入院詳細（UUID → 主治医の map 構築に使う）
    target_ward : str, optional
        病棟で絞る場合に指定。None なら全病棟集計。

    Returns
    -------
    dict
        ``{doctor_name: count}``、件数降順ソート済みの順序を保つには
        外部で ``sorted(items)`` すること。
    """
    if admission_details_df is None or len(admission_details_df) == 0:
        return {}
    if "id" not in admission_details_df.columns:
        return {}
    if "attending_doctor" not in admission_details_df.columns:
        return {}

    df = admission_details_df
    if "event_type" in df.columns:
        df = df[df["event_type"] == "admission"]
    if len(df) == 0:
        return {}

    uuid_to_doctor: Dict[str, str] = {}
    uuid_to_ward: Dict[str, str] = {}
    for _, row in df.iterrows():
        pid = str(row["id"])[:8]
        uuid_to_doctor[pid] = str(row.get("attending_doctor", "不明"))
        if "ward" in df.columns:
            uuid_to_ward[pid] = str(row.get("ward", ""))

    by_doctor: Dict[str, int] = {}
    for uuid, plan in plans.items():
        if not plan.get("unplanned"):
            continue
        if target_ward is not None and uuid_to_ward.get(uuid) != target_ward:
            continue
        doctor = uuid_to_doctor.get(uuid, "不明")
        by_doctor[doctor] = by_doctor.get(doctor, 0) + 1
    return by_doctor


def _render_unplanned_doctor_summary(
    plans: Dict[str, Dict[str, Any]],
    admission_details_df: Optional[pd.DataFrame],
    target_ward: str,
) -> None:
    """主治医別の突発退院頻度を streamlit に描画."""
    import streamlit as st

    by_doctor = _get_unplanned_by_doctor(plans, admission_details_df, target_ward)
    if not by_doctor:
        return

    sorted_items = sorted(by_doctor.items(), key=lambda kv: kv[1], reverse=True)
    items = [f"**{d}**: {n} 名" for d, n in sorted_items]
    st.caption(
        f"⚡ 突発退院（主治医独断で決まった退院）の主治医別内訳: "
        + " / ".join(items)
        + "  ※ 運用ルール的には本来、退院日はカンファで調整する。"
    )


def _render_emergency_forecast_summary(
    emergency_dow_mean: Dict[int, float],
    ward: str,
) -> None:
    """曜日別緊急入院見込みのサマリー."""
    import streamlit as st

    items = []
    for i in range(7):
        items.append(f"{_DOW_JA[i]}: {emergency_dow_mean.get(i, 0.0):.1f}")
    summary = " / ".join(items)
    st.caption(
        f"**{ward} 病棟の過去 1 年の曜日別入院平均**: {summary}（名/日）  "
        f"※ 退院計画時の参考値。実際の緊急入院は予測不能。"
    )


# -----------------------------------------------------------------------------
# メインエントリ
# -----------------------------------------------------------------------------


def render_discharge_calendar_tab(
    admission_details_df: Optional[pd.DataFrame] = None,
    today: Optional[date] = None,
    jp_holidays: Optional[set] = None,
    ward_occupancy_rates: Optional[Dict[str, float]] = None,
    ward_vacancy_counts: Optional[Dict[str, int]] = None,
) -> None:
    """🏥 退院調整 > 📅 退院カレンダー タブの本体.

    Parameters
    ----------
    admission_details_df : pd.DataFrame, optional
        入院詳細データ（``st.session_state["admission_details"]`` 相当）。
        UUID → 病棟 map の構築、予定入院数集計、緊急平均算出、
        主治医別突発退院集計に使う。
    today : date, optional
        基準日（None なら ``date.today()``）。テスト用注入点。
    jp_holidays : set of date, optional
        日本の祝日セット。None なら空セット扱い。
    ward_occupancy_rates : dict, optional
        病棟別の現在稼働率（``{"5F": 0.92, "6F": 0.88}``）。
        今日のセルのみ動的枠調整に反映。
    ward_vacancy_counts : dict, optional
        病棟別の現在空床数。同様に今日のセルのみ動的枠調整に反映。
    """
    import streamlit as st

    if today is None:
        today = date.today()
    if jp_holidays is None:
        jp_holidays = set()

    # ---- データ取得 ----
    try:
        from discharge_plan_store import load_all_plans
        from patient_status_store import load_all_statuses
    except ImportError:
        # scripts/ 以外から呼ばれた場合のフォールバック
        from scripts.discharge_plan_store import load_all_plans  # type: ignore
        from scripts.patient_status_store import load_all_statuses  # type: ignore

    plans = load_all_plans()
    status_map = load_all_statuses()
    ward_map = _build_patient_ward_map(admission_details_df)

    # ---- ヘッダー ----
    st.markdown("### 📅 退院カレンダー")
    st.markdown(
        f"**基準日: {today.isoformat()}（{_DOW_JA[today.weekday()]}）** — "
        "退院の予定と入院の流入を重ねて見ることで、ベッドコントロールを数字で判断できます。"
    )

    # ---- 病棟タブ × 月タブ ----
    ward_tabs = st.tabs(["🏥 5F 病棟", "🏥 6F 病棟"])

    for ward_idx, ward_label in enumerate(["5F", "6F"]):
        with ward_tabs[ward_idx]:
            # 病棟サマリー
            adjusting = _count_adjusting_patients_for_ward(
                ward_map, status_map, plans, ward_label
            )
            kpi_current = _calculate_monthly_kpi(
                plans, ward_map, ward_label, today.year, today.month
            )
            # 翌月 KPI
            next_year, next_month = (today.year, today.month + 1)
            if next_month > 12:
                next_year += 1
                next_month = 1
            kpi_next = _calculate_monthly_kpi(
                plans, ward_map, ward_label, next_year, next_month
            )

            summary_html = (
                f'<div style="background:#F9FAFB;padding:12px;border-radius:6px;margin:8px 0;">'
                f'<div style="font-size:13px;color:#374151;">'
                f'<b>{ward_label} 病棟サマリー</b> '
                f'<span style="color:#6B7280;margin-left:16px;">'
                f'調整中（予定日未定）: {adjusting} 名 / '
                f'今月退院予定: {kpi_current["total"]} 名 / '
                f'うち日曜退院: {kpi_current["sunday_discharges"]} 名 / '
                f'突発退院: {kpi_current["unplanned_count"]} 名'
                f'</span></div></div>'
            )
            st.markdown(summary_html, unsafe_allow_html=True)

            # 緊急入院予測（曜日別）
            emergency_dow_mean = _estimate_emergency_admissions_by_dow(
                admission_details_df, ward_label
            )
            _render_emergency_forecast_summary(emergency_dow_mean, ward_label)

            # 月タブ（当月 / 翌月）
            month_tabs = st.tabs([
                f"📆 {today.year}年{today.month}月（当月）",
                f"📆 {next_year}年{next_month}月（翌月）",
            ])

            # 病棟別の稼働率・空床を取得（今日のセル用動的枠調整）
            ward_occ = (ward_occupancy_rates or {}).get(ward_label)
            ward_vac = (ward_vacancy_counts or {}).get(ward_label)

            with month_tabs[0]:
                _render_month_calendar(
                    year=today.year,
                    month=today.month,
                    ward=ward_label,
                    plans=plans,
                    ward_map=ward_map,
                    status_map=status_map,
                    admission_details_df=admission_details_df,
                    emergency_dow_mean=emergency_dow_mean,
                    today=today,
                    jp_holidays=jp_holidays,
                    current_occupancy_rate=ward_occ,
                    current_vacancy_count=ward_vac,
                )
                _render_legend()
                _render_unplanned_doctor_summary(plans, admission_details_df, ward_label)

            with month_tabs[1]:
                _render_month_calendar(
                    year=next_year,
                    month=next_month,
                    ward=ward_label,
                    plans=plans,
                    ward_map=ward_map,
                    status_map=status_map,
                    admission_details_df=admission_details_df,
                    emergency_dow_mean=emergency_dow_mean,
                    today=today,
                    jp_holidays=jp_holidays,
                    current_occupancy_rate=None,  # 翌月は動的調整対象外
                    current_vacancy_count=None,
                )
                _render_legend()
                st.caption(
                    f"翌月 {next_year}年{next_month}月 "
                    f"退院予定: {kpi_next['total']} 名 / "
                    f"日曜退院: {kpi_next['sunday_discharges']} 名 / "
                    f"突発: {kpi_next['unplanned_count']} 名"
                )

    # ---- 画面下部: E2E 用 testid ----
    st.markdown(
        '<div data-testid="discharge-calendar" style="display:none;"></div>',
        unsafe_allow_html=True,
    )


__all__ = ["render_discharge_calendar_tab"]
