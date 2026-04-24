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


def _get_currently_admitted_uuids(
    admission_details_df: Optional[pd.DataFrame],
    target_ward: str,
) -> List[str]:
    """指定病棟で現在入院中の UUID 先頭 8 桁リストを返す.

    「入院中」の定義: admission イベントはあるが対応する discharge イベントがない UUID。

    副院長フィードバック (2026-04-23): 退院予定の登録は患者ステータスに
    依存せず「入院中の患者なら誰でも」選べるようにする。カンファで
    ステータスを先に更新しないと登録できない運用は実務的でない。
    """
    if admission_details_df is None or len(admission_details_df) == 0:
        return []
    required = {"event_type", "id", "ward"}
    if not required.issubset(admission_details_df.columns):
        return []

    # 入院したが退院していない UUID を列挙
    adm = admission_details_df[admission_details_df["event_type"] == "admission"]
    disc = admission_details_df[admission_details_df["event_type"] == "discharge"]

    adm_uuids_in_ward: set = set()
    for _, row in adm.iterrows():
        pid = str(row["id"])
        if len(pid) < 8:
            continue
        if str(row.get("ward")) == target_ward:
            adm_uuids_in_ward.add(pid[:8])

    disc_uuids: set = set()
    for _, row in disc.iterrows():
        pid = str(row["id"])
        if len(pid) >= 8:
            disc_uuids.add(pid[:8])

    return sorted(adm_uuids_in_ward - disc_uuids)


def _get_eligible_uuids_for_new_plan(
    ward_map: Dict[str, str],
    target_ward: str,
    plans: Dict[str, Dict[str, Any]],
    admission_details_df: Optional[pd.DataFrame],
) -> List[str]:
    """その病棟で「入院中かつ予定日未設定」の UUID を返す.

    退院予定の登録フォーム用。ステータスが "new" でも対象に含める
    （副院長フィードバック 2026-04-23: ステータス更新を前提としない）。
    """
    admitted = _get_currently_admitted_uuids(admission_details_df, target_ward)
    eligible: List[str] = []
    for uuid in admitted:
        plan = plans.get(uuid)
        if plan and plan.get("scheduled_date"):
            continue
        eligible.append(uuid)
    return eligible


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


def _estimate_discharges_by_dow(
    admission_details_df: Optional[pd.DataFrame],
    target_ward: str,
) -> Dict[int, float]:
    """病棟別・曜日別の退院平均数を過去実績から算出.

    退院予定が未登録の日の「自然退院」を補完するために使う。
    （予測時、副院長が登録していない日は過去の平均的な退院数で埋める）

    Returns
    -------
    dict
        ``{0-6: 平均退院数/日}``。月〜日の weekday 番号をキーに平均値。
    """
    if admission_details_df is None or len(admission_details_df) == 0:
        return {i: 0.0 for i in range(7)}
    required = {"event_type", "date", "ward"}
    if not required.issubset(admission_details_df.columns):
        return {i: 0.0 for i in range(7)}

    mask = (
        (admission_details_df["event_type"] == "discharge")
        & (admission_details_df["ward"] == target_ward)
    )
    subset = admission_details_df[mask]
    if len(subset) == 0:
        return {i: 0.0 for i in range(7)}

    try:
        dts = pd.to_datetime(subset["date"])
    except (ValueError, TypeError):
        return {i: 0.0 for i in range(7)}

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


def _compute_cell_data(
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
) -> Dict[str, Any]:
    """1 セル分の表示データを計算して dict で返す（純粋関数、テスト容易）."""
    from discharge_slot_config import (
        WEEKDAY_SLOT,
        HOLIDAY_SLOT,
        calculate_effective_slot,
        is_holiday_slot_day,
    )

    is_current_month = cell_date.month == target_month
    is_today = cell_date == today
    is_sunday_or_holiday = is_holiday_slot_day(cell_date, is_holiday)

    dc = _count_discharge_plans_for_cell(
        plans, ward_map, status_map, ward, cell_date
    )
    total_discharge = dc["scheduled"] + dc["confirmed"]
    sched_adm = _count_scheduled_admissions_for_cell(
        admission_details_df, cell_date, ward
    )
    total_adm_mean = emergency_dow_mean.get(cell_date.weekday(), 0.0)
    prev_excess = _calculate_previous_day_excess(
        cell_date, daily_counts, jp_holidays
    )
    occ = current_occupancy_rate if is_today else None
    vac = current_vacancy_count if is_today else None
    slot = calculate_effective_slot(
        cell_date,
        previous_day_excess=prev_excess,
        occupancy_rate=occ,
        vacancy_count=vac,
        is_holiday=is_holiday,
    )
    base_slot = HOLIDAY_SLOT if is_sunday_or_holiday else WEEKDAY_SLOT
    slot_adjusted = slot != base_slot and not is_sunday_or_holiday
    return {
        "is_current_month": is_current_month,
        "is_today": is_today,
        "is_sunday_or_holiday": is_sunday_or_holiday,
        "is_holiday": is_holiday,
        "dc": dc,
        "total_discharge": total_discharge,
        "sched_adm": sched_adm,
        "total_adm_mean": total_adm_mean,
        "prev_excess": prev_excess,
        "slot": slot,
        "slot_adjusted": slot_adjusted,
        "remaining": slot - total_discharge,
        "is_over": (slot - total_discharge) < 0,
    }


def _build_cell_progress_bar_html(cell_data: Dict[str, Any]) -> str:
    """セルボタンの下に表示する「埋まり具合」プログレスバーの HTML.

    副院長フィードバック (2026-04-24): 数値だけでは混雑度が視認しづらい。
    バーの長さ + 色で一目で判別できるようにする。

    色の閾値:
        超過 (>100%)   → 🔴 赤（#DC2626）
        満杯 (=100%)   → 🟠 オレンジ（#F59E0B）
        半分以上 (≥40%) → 🟡 黄（#FCD34D）
        使用中 (>0%)   → 🟢 緑（#10B981）
        ゼロ           → バー非表示（空のセル）

    月外セル・枠ゼロのセルもバー非表示。
    """
    if not cell_data.get("is_current_month", True):
        return ""
    slot = cell_data.get("slot", 0)
    total_discharge = cell_data.get("total_discharge", 0)
    if slot <= 0 or total_discharge <= 0:
        # 予定なし or 枠ゼロは何も描画しない（視覚ノイズを減らす）
        return ""

    ratio = total_discharge / slot if slot > 0 else 0
    is_over = cell_data.get("is_over", False)

    if is_over:
        color = "#DC2626"  # 赤
        width = 100
    elif ratio >= 1.0:
        color = "#F59E0B"  # オレンジ（ちょうど満杯）
        width = 100
    elif ratio >= 0.4:
        color = "#FCD34D"  # 黄（半分以上）
        width = int(ratio * 100)
    else:
        color = "#10B981"  # 緑（余裕）
        width = max(8, int(ratio * 100))  # 最低 8% で視認性確保

    return (
        f'<div style="height:6px;background:#F3F4F6;border-radius:3px;'
        f'margin:-2px 0 6px 0;overflow:hidden;">'
        f'<div style="height:100%;width:{width}%;background:{color};'
        f'border-radius:3px;"></div>'
        f'</div>'
    )


def _build_cell_button_label(
    cell_date: date,
    cell_data: Dict[str, Any],
) -> str:
    """st.button 用のラベル文字列を生成.

    ボタンは HTML 不可のためテキスト + 絵文字で視認性を確保する。
    3〜4 行構成で、改行は \\n。

    Prefix 絵文字は「日付種別」+「混雑度」の複合表示（副院長フィードバック 2026-04-24）。
    日曜/祝日の ⭐🎌 と、退院枠の埋まり具合 🟡🔴🚨 を併記することで、
    数値を読まなくても一目で「空いてる日」「いっぱいの日」「超過日」が判別できる。
    """
    dow = _DOW_JA[cell_date.weekday()]
    if not cell_data["is_current_month"]:
        return f"{cell_date.day}"

    # 複合 prefix: 日付種別絵文字 + 混雑度絵文字
    # 混雑度は「退院予定数が枠に対してどれだけ埋まっているか」で判定
    prefixes: List[str] = []

    # 日付種別（祝日 > 日曜）
    if cell_data["is_holiday"]:
        prefixes.append("🎌")
    elif cell_data["is_sunday_or_holiday"]:
        prefixes.append("⭐")

    # 混雑度（予定が入った日のみ、空っぽの日は prefix なしで静かに）
    total_discharge = cell_data["total_discharge"]
    slot = cell_data["slot"]
    remaining = cell_data["remaining"]
    if cell_data["is_over"]:
        prefixes.append("🚨")  # 超過
    elif total_discharge > 0 and remaining == 0:
        prefixes.append("🔴")  # 満杯（枠ちょうど使い切り）
    elif total_discharge > 0 and slot > 0 and remaining <= max(1, slot // 3):
        prefixes.append("🟡")  # ギリギリ（残り 1/3 以下）
    # それ以外（空 or 余裕）は prefix なし

    prefix = " ".join(prefixes)

    dc = cell_data["dc"]
    total_discharge = cell_data["total_discharge"]
    if total_discharge == 0:
        dc_str = "🏥退 —"
    elif dc["confirmed"] > 0 and dc["scheduled"] > 0:
        dc_str = f"🏥退 ●{dc['confirmed']} ○{dc['scheduled']}"
    elif dc["confirmed"] > 0:
        dc_str = f"🏥退 ●{dc['confirmed']}"
    else:
        dc_str = f"🏥退 ○{dc['scheduled']}"

    sched_adm = cell_data["sched_adm"]
    mean_adm = cell_data["total_adm_mean"]
    if sched_adm > 0:
        adm_str = f"📥入 {sched_adm}"
    elif mean_adm > 0:
        adm_str = f"📥入 ~{mean_adm:.1f}"
    else:
        adm_str = "📥入 —"

    remaining = cell_data["remaining"]
    slot = cell_data["slot"]
    if remaining < 0:
        slot_str = f"超過 {abs(remaining)}"
    else:
        slot_str = f"残 {remaining}/{slot}"

    # 追加マーカー
    extras = []
    if cell_data["slot_adjusted"]:
        extras.append("✨")
    if cell_data["prev_excess"] > 0:
        extras.append(f"↩{cell_data['prev_excess']}")
    if dc["unplanned"] > 0:
        extras.append(f"⚡{dc['unplanned']}")
    extra_str = " ".join(extras)

    # 行構成（3 行 + extras の 4 行目）
    head = f"{prefix} {cell_date.day}({dow})".strip()
    lines = [head, f"{dc_str}  {adm_str}", slot_str]
    if extra_str:
        lines.append(extra_str)
    return "\n".join(lines)


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
    session_key_prefix: str = "dcal",
) -> None:
    """1 ヶ月分のカレンダーを streamlit に描画（セルクリック対応）.

    各日は ``st.button`` としてクリック可能。クリックすると
    ``st.session_state[{session_key_prefix}_selected_{ward}]`` に ISO 日付文字列が保存され、
    カレンダー下部の詳細パネルがその日の情報を表示する。
    """
    import streamlit as st

    if jp_holidays is None:
        jp_holidays = set()

    weeks = _get_month_weeks(year, month)
    grid_start = weeks[0][0] if weeks else date(year, month, 1)
    grid_end = weeks[-1][-1] if weeks else date(year, month, 1)
    daily_counts = _precompute_daily_discharge_counts(
        plans, ward_map, status_map, ward, grid_start, grid_end
    )

    # ヘッダー（曜日ラベル）
    header_cells = []
    for i, d in enumerate(_DOW_JA):
        weekday_color = "#DC2626" if i == 6 else "#374151"
        header_cells.append(
            f'<div style="text-align:center;font-weight:bold;padding:6px;'
            f'background:#F9FAFB;color:{weekday_color};border-radius:4px;">{d}</div>'
        )
    header_html = (
        '<div style="display:grid;grid-template-columns:repeat(7,1fr);gap:2px;margin-bottom:4px;">'
        + "".join(header_cells)
        + "</div>"
    )
    st.markdown(header_html, unsafe_allow_html=True)

    sel_key = f"{session_key_prefix}_selected_{ward}"

    # 各週を 7 列で描画
    for week_idx, week in enumerate(weeks):
        day_cols = st.columns(7)
        for i, d in enumerate(week):
            is_holiday = d in jp_holidays
            cell_data = _compute_cell_data(
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
            label = _build_cell_button_label(d, cell_data)
            btn_key = f"{session_key_prefix}_btn_{ward}_{year}_{month}_{d.isoformat()}"
            btn_type = "primary" if cell_data["is_today"] else "secondary"
            with day_cols[i]:
                clicked = st.button(
                    label,
                    key=btn_key,
                    use_container_width=True,
                    type=btn_type,
                    disabled=not cell_data["is_current_month"],
                )
                # ボタン直下の埋まり具合プログレスバー（副院長 2026-04-24）
                bar_html = _build_cell_progress_bar_html(cell_data)
                if bar_html:
                    st.markdown(bar_html, unsafe_allow_html=True)
                if clicked:
                    st.session_state[sel_key] = d.isoformat()
                    st.rerun()


# -----------------------------------------------------------------------------
# 詳細パネル（選択日の患者一覧・登録 UI）
# -----------------------------------------------------------------------------


def _display_name_for_uuid(uuid: str, names: Dict[str, Dict[str, str]]) -> str:
    """UUID から表示名を生成（氏名があれば氏名、なければ ID 先頭8桁）."""
    info = names.get(uuid) or {}
    name = info.get("patient_name") or ""
    if name:
        return name
    return f"ID {uuid}"


#: カンファステータスキー → 表示用ラベル（カンファ画面と統一）
_STATUS_LABEL_MAP: Dict[str, str] = {
    "new": "🆕 新規",
    "medical": "🔵 医学的OK待ち",
    "family": "🟢 家族希望待ち",
    "facility": "🟡 施設待ち",
    "insurance": "🟣 介護保険待ち",
    "rehab": "🟠 リハ最適化中",
    "undecided": "⚫ 方向性未決",
    "before_confirmed": "連休前・確定",
    "before_adjusting": "連休前・調整中",
    "continuing": "連休継続",
}


def _status_key_to_label(status_key: str) -> str:
    """status_key を絵文字付き日本語ラベルに変換（未知のキーはそのまま返す）."""
    return _STATUS_LABEL_MAP.get(status_key, status_key)


def _render_day_detail_panel(
    selected_date: date,
    ward: str,
    plans: Dict[str, Dict[str, Any]],
    status_map: Dict[str, str],
    ward_map: Dict[str, str],
    admission_details_df: Optional[pd.DataFrame] = None,
) -> None:
    """選択された日の退院予定患者一覧と新規登録フォームを表示."""
    import streamlit as st

    try:
        from discharge_plan_store import save_plan, clear_plan  # type: ignore
        from patient_name_store import load_all_patient_info  # type: ignore
    except ImportError:
        from scripts.discharge_plan_store import save_plan, clear_plan  # type: ignore
        from scripts.patient_name_store import load_all_patient_info  # type: ignore

    names = load_all_patient_info()
    day_iso = selected_date.isoformat()
    dow = _DOW_JA[selected_date.weekday()]

    st.markdown("---")
    st.markdown(
        f"### 📝 {selected_date.strftime('%Y-%m-%d')} ({dow}) の {ward} 退院予定"
    )
    st.caption("カレンダーの日をクリックすると、この欄が選択日に切り替わります。")

    # その日の既存予定患者
    plans_for_day = [
        (uuid, plans[uuid])
        for uuid in plans
        if plans[uuid].get("scheduled_date") == day_iso
        and ward_map.get(uuid) == ward
    ]

    if plans_for_day:
        st.markdown(f"**登録済み: {len(plans_for_day)} 名**")
        for uuid, plan in plans_for_day:
            info = names.get(uuid) or {}
            display_name = _display_name_for_uuid(uuid, names)
            doctor = info.get("doctor_name") or "主治医不明"
            cols = st.columns([3, 1, 1, 1])
            with cols[0]:
                st.markdown(f"**{display_name}** （Dr. {doctor}）")
            with cols[1]:
                current_conf = bool(plan.get("confirmed", False))
                new_conf = st.checkbox(
                    "決定",
                    value=current_conf,
                    key=f"dcal_conf_{ward}_{uuid}_{day_iso}",
                )
                if new_conf != current_conf:
                    save_plan(
                        uuid,
                        scheduled_date=selected_date,
                        confirmed=new_conf,
                        unplanned=bool(plan.get("unplanned", False)),
                    )
                    st.rerun()
            with cols[2]:
                current_unp = bool(plan.get("unplanned", False))
                new_unp = st.checkbox(
                    "突発",
                    value=current_unp,
                    key=f"dcal_unp_{ward}_{uuid}_{day_iso}",
                )
                if new_unp != current_unp:
                    save_plan(
                        uuid,
                        scheduled_date=selected_date,
                        confirmed=bool(plan.get("confirmed", False)),
                        unplanned=new_unp,
                    )
                    st.rerun()
            with cols[3]:
                if st.button(
                    "🗑",
                    key=f"dcal_del_{ward}_{uuid}_{day_iso}",
                    help="この日の退院予定を削除",
                ):
                    clear_plan(uuid)
                    st.rerun()
    else:
        st.caption("この日に退院予定の患者はいません。")

    # 新規追加セクション（入院中の患者から誰でも選べる）
    st.markdown("**この日に退院予定を追加:**")
    eligible_uuids = _get_eligible_uuids_for_new_plan(
        ward_map=ward_map,
        target_ward=ward,
        plans=plans,
        admission_details_df=admission_details_df,
    )

    if not eligible_uuids:
        if admission_details_df is None or len(admission_details_df) == 0:
            st.info(
                "⚠️ 入院患者データがありません。サイドバーの「データソース」で"
                "実績データを選択するか、シミュレーションを実行すると "
                f"{ward} 病棟の入院中患者が一覧に出ます。"
            )
        else:
            st.caption(
                f"{ward} 病棟で入院中かつ退院予定未設定の患者がいません。"
                "（全員に予定日が入っているか、退院イベントが既に記録されています）"
            )
        return

    # 選択肢: 氏名あれば氏名、なければ ID。ステータスと主治医を併記。
    def _fmt(uuid: str) -> str:
        info = names.get(uuid) or {}
        display_name = _display_name_for_uuid(uuid, names)
        status_label = status_map.get(uuid, "🆕 新規")
        # ステータスキーから表示用ラベルに変換（カンファ画面と同じ絵文字）
        status_display = _status_key_to_label(status_label)
        doctor = info.get("doctor_name") or ""
        parts = [display_name]
        if doctor:
            parts.append(f"Dr. {doctor}")
        parts.append(status_display)
        return "（".join([parts[0], " / ".join(parts[1:]) + "）"])

    selected_uuid = st.selectbox(
        "対象患者",
        options=eligible_uuids,
        format_func=_fmt,
        key=f"dcal_add_select_{ward}_{day_iso}",
    )
    cols = st.columns([1, 1, 2])
    with cols[0]:
        add_confirmed = st.checkbox(
            "決定として登録",
            key=f"dcal_add_conf_{ward}_{day_iso}",
        )
    with cols[1]:
        add_unplanned = st.checkbox(
            "突発退院",
            key=f"dcal_add_unp_{ward}_{day_iso}",
            help="主治医独断で決まった退院の場合にチェック",
        )
    with cols[2]:
        if st.button(
            f"📌 {day_iso} に登録",
            key=f"dcal_add_submit_{ward}_{day_iso}",
            type="primary",
            use_container_width=True,
        ):
            save_plan(
                selected_uuid,
                scheduled_date=selected_date,
                confirmed=add_confirmed,
                unplanned=add_unplanned,
            )
            st.success(f"✅ 登録しました（{_display_name_for_uuid(selected_uuid, names)}）")
            st.rerun()


# -----------------------------------------------------------------------------
# 予測計算（予約入院 + 退院予定 + 緊急入院曜日平均 から日次稼働率を推計）
# -----------------------------------------------------------------------------


def _compute_occupancy_forecast(
    ward: str,
    start_date: date,
    end_date: date,
    initial_inpatients: int,
    total_beds: int,
    plans: Dict[str, Dict[str, Any]],
    ward_map: Dict[str, str],
    admission_details_df: Optional[pd.DataFrame],
    emergency_dow_mean: Dict[int, float],
    discharge_dow_mean: Optional[Dict[int, float]] = None,
) -> List[Dict[str, Any]]:
    """日次稼働率予測を漸化式で計算する.

    各日: 翌日在院 = 当日在院 − 退院予定 + 予約入院 + 緊急入院見込み

    Parameters
    ----------
    initial_inpatients : int
        開始日朝の在院数。これを起点に漸化式で翌日以降を計算。
    total_beds : int
        病棟の病床数（稼働率 = 在院 / 病床）。
    emergency_dow_mean : dict
        ``{0-6: 1日あたり平均緊急入院数}``。予約入院と区別はできないが、
        過去1年のデータからは全入院の曜日平均を使う。

    Returns
    -------
    list of dict
        各日 ``{"date", "inpatients", "occupancy", "scheduled_discharges",
        "confirmed_discharges", "scheduled_admissions", "emergency_mean",
        "net_change"}``。
    """
    results: List[Dict[str, Any]] = []
    current_inpatients = float(initial_inpatients)
    days = (end_date - start_date).days + 1

    # 退院予定の日付 → (scheduled, confirmed) の事前集計
    discharge_by_date: Dict[str, Dict[str, int]] = {}
    for uuid, plan in plans.items():
        if ward_map.get(uuid) != ward:
            continue
        sd_str = plan.get("scheduled_date")
        if not sd_str:
            continue
        rec = discharge_by_date.setdefault(sd_str, {"scheduled": 0, "confirmed": 0})
        if plan.get("confirmed"):
            rec["confirmed"] += 1
        else:
            rec["scheduled"] += 1

    # 予約入院の日付 → 件数 の事前集計（admission_details_df の未来日）
    scheduled_adm_by_date: Dict[str, int] = {}
    if admission_details_df is not None and len(admission_details_df) > 0:
        required = {"event_type", "date", "ward"}
        if required.issubset(admission_details_df.columns):
            mask = (
                (admission_details_df["event_type"] == "admission")
                & (admission_details_df["ward"] == ward)
            )
            subset = admission_details_df[mask]
            if len(subset) > 0:
                try:
                    dates = pd.to_datetime(subset["date"]).dt.date
                    for d in dates:
                        iso = d.isoformat()
                        scheduled_adm_by_date[iso] = scheduled_adm_by_date.get(iso, 0) + 1
                except (ValueError, TypeError):
                    pass

    for i in range(days):
        d = start_date + timedelta(days=i)
        iso = d.isoformat()
        dow = d.weekday()

        disc_rec = discharge_by_date.get(iso, {"scheduled": 0, "confirmed": 0})
        scheduled_discharges = disc_rec["scheduled"]
        confirmed_discharges = disc_rec["confirmed"]
        registered_discharge = scheduled_discharges + confirmed_discharges
        # 退院予定が未登録の日は過去の曜日平均で補完（自然退院の想定）
        if registered_discharge > 0 or discharge_dow_mean is None:
            total_discharge_for_calc = float(registered_discharge)
        else:
            total_discharge_for_calc = discharge_dow_mean.get(dow, 0.0)
        # 表示用も計算に使った値（登録済み + 曜日平均フォールバック）
        # → 在院数の増減と退院バーの不一致を避ける。
        total_discharge = round(total_discharge_for_calc, 1)

        scheduled_admission = scheduled_adm_by_date.get(iso, 0)
        emergency_mean = emergency_dow_mean.get(dow, 0.0)

        # 未来日の入院は「予約入院 + 緊急見込み」（重複を避ける：予約があれば緊急は控えめに）
        # ただし admission_details の曜日平均は全入院を含むため、別々に扱うと二重カウントになる
        # シンプルに: 予約入院があればそちらを使う、なければ緊急曜日平均を使う
        if scheduled_admission > 0:
            total_admission = float(scheduled_admission)
        else:
            total_admission = emergency_mean

        net_change = total_admission - total_discharge_for_calc
        current_inpatients = max(0.0, current_inpatients + net_change)
        occupancy = current_inpatients / total_beds if total_beds > 0 else 0.0

        results.append({
            "date": d,
            "inpatients": round(current_inpatients, 1),
            "occupancy": round(occupancy * 100, 1),
            "scheduled_discharges": scheduled_discharges,
            "confirmed_discharges": confirmed_discharges,
            "total_discharge": total_discharge,
            "scheduled_admissions": scheduled_admission,
            "emergency_mean": round(emergency_mean, 1),
            "total_admission": round(total_admission, 1),
            "net_change": round(net_change, 1),
        })
    return results


def _estimate_current_inpatients(
    admission_details_df: Optional[pd.DataFrame],
    target_ward: str,
    reference_date: date,
) -> int:
    """基準日時点で入院中の患者数を admission/discharge の履歴から推定.

    当病棟の admission 件数 − discharge 件数（いずれも reference_date まで）
    をネット残として返す。CSV 上は admission/discharge 各行が独立した UUID
    を持つ（同一患者でも ID が異なる）ため、件数差分で推定する。
    """
    if admission_details_df is None or len(admission_details_df) == 0:
        return 0
    required = {"event_type", "date", "ward"}
    if not required.issubset(admission_details_df.columns):
        return 0

    try:
        df = admission_details_df.copy()
        df["date"] = pd.to_datetime(df["date"]).dt.date
    except (ValueError, TypeError):
        return 0

    # 基準日までのイベント × 当病棟に限定
    df = df[(df["date"] <= reference_date) & (df["ward"] == target_ward)]
    if len(df) == 0:
        return 0

    adm_count = int((df["event_type"] == "admission").sum())
    disc_count = int((df["event_type"] == "discharge").sum())
    return max(0, adm_count - disc_count)


def _render_forecast_charts(
    forecast: List[Dict[str, Any]],
    today: date,
    total_beds: int,
    ward: str,
    testid_suffix: str = "",
) -> None:
    """稼働率・在院数・入退院の予測グラフを Plotly で描画.

    信頼幅つき:
    - 近未来 2 週間以内: 実線 + ±2 名相当の帯
    - 2〜4 週先: 点線 + ±5 名相当の帯
    """
    import streamlit as st
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        st.warning(
            "Plotly が未インストールのため予測グラフは表示できません。"
            "`pip install plotly` で有効化してください。"
        )
        return

    if not forecast:
        st.caption("予測データが生成できませんでした。")
        return

    # 信頼幅の区切り（今日から14日先まで「近未来」、それ以降「長期」）
    near_cutoff = today + timedelta(days=14)

    dates = [r["date"] for r in forecast]
    inpatients = [r["inpatients"] for r in forecast]
    occupancy = [r["occupancy"] for r in forecast]
    total_disc = [r["total_discharge"] for r in forecast]
    total_adm = [r["total_admission"] for r in forecast]

    # 信頼幅（在院数ベース）
    band_upper_inp = []
    band_lower_inp = []
    band_upper_occ = []
    band_lower_occ = []
    for r in forecast:
        if r["date"] <= near_cutoff:
            band_width = 2.0
        else:
            band_width = 5.0
        band_upper_inp.append(r["inpatients"] + band_width)
        band_lower_inp.append(max(0, r["inpatients"] - band_width))
        if total_beds > 0:
            band_upper_occ.append(round((r["inpatients"] + band_width) / total_beds * 100, 1))
            band_lower_occ.append(round(max(0, r["inpatients"] - band_width) / total_beds * 100, 1))
        else:
            band_upper_occ.append(0.0)
            band_lower_occ.append(0.0)

    # 近未来と長期の境界で線を分割
    near_dates = [d for d in dates if d <= near_cutoff]
    near_inp = [inp for d, inp in zip(dates, inpatients) if d <= near_cutoff]
    near_occ = [o for d, o in zip(dates, occupancy) if d <= near_cutoff]
    long_dates = [d for d in dates if d > near_cutoff]
    long_inp = [inp for d, inp in zip(dates, inpatients) if d > near_cutoff]
    long_occ = [o for d, o in zip(dates, occupancy) if d > near_cutoff]

    # 3 段のサブプロット（稼働率 / 在院数 / 入退院）
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        subplot_titles=(
            f"📊 {ward} 稼働率予測（退院カレンダーの予定を反映）",
            f"🛏 {ward} 在院患者数予測",
            f"📈 {ward} 入退院数予測",
        ),
        vertical_spacing=0.08,
        row_heights=[0.4, 0.3, 0.3],
    )

    # --- 稼働率（信頼帯 + 近未来実線 + 長期点線） ---
    fig.add_trace(
        go.Scatter(
            x=dates, y=band_upper_occ, mode="lines",
            line=dict(width=0), showlegend=False, hoverinfo="skip",
        ),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=dates, y=band_lower_occ, mode="lines",
            line=dict(width=0), fill="tonexty",
            fillcolor="rgba(37, 99, 235, 0.15)",
            name="信頼幅（±2〜5名）", hoverinfo="skip",
        ),
        row=1, col=1,
    )
    if near_occ:
        fig.add_trace(
            go.Scatter(
                x=near_dates, y=near_occ, mode="lines",
                line=dict(color="#2563EB", width=3),
                name="近未来 2 週間（実線）",
            ),
            row=1, col=1,
        )
    if long_occ:
        fig.add_trace(
            go.Scatter(
                x=long_dates, y=long_occ, mode="lines",
                line=dict(color="#2563EB", width=2, dash="dot"),
                name="2 週先〜（点線、参考）",
            ),
            row=1, col=1,
        )
    # 目標レンジ（90-95%）
    fig.add_hrect(
        y0=90, y1=95, fillcolor="rgba(245, 158, 11, 0.08)",
        line_width=0, row=1, col=1,
    )
    # 今日のマーカー
    fig.add_vline(
        x=today.isoformat(),
        line_width=1, line_dash="dash", line_color="#DC2626",
        row=1, col=1,
    )

    # --- 在院患者数 ---
    fig.add_trace(
        go.Scatter(
            x=dates, y=band_upper_inp, mode="lines",
            line=dict(width=0), showlegend=False, hoverinfo="skip",
        ),
        row=2, col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=dates, y=band_lower_inp, mode="lines",
            line=dict(width=0), fill="tonexty",
            fillcolor="rgba(124, 58, 237, 0.15)",
            showlegend=False, hoverinfo="skip",
        ),
        row=2, col=1,
    )
    if near_inp:
        fig.add_trace(
            go.Scatter(
                x=near_dates, y=near_inp, mode="lines",
                line=dict(color="#7C3AED", width=3),
                showlegend=False,
            ),
            row=2, col=1,
        )
    if long_inp:
        fig.add_trace(
            go.Scatter(
                x=long_dates, y=long_inp, mode="lines",
                line=dict(color="#7C3AED", width=2, dash="dot"),
                showlegend=False,
            ),
            row=2, col=1,
        )
    # 病床数ライン
    fig.add_hline(
        y=total_beds, line_width=1, line_dash="dash",
        line_color="#DC2626",
        annotation_text=f"病床数 {total_beds}",
        annotation_position="top right",
        row=2, col=1,
    )

    # --- 入退院数（棒グラフ） ---
    fig.add_trace(
        go.Bar(
            x=dates, y=total_adm,
            name="入院（予定＋緊急見込み）",
            marker_color="#7C3AED",
        ),
        row=3, col=1,
    )
    fig.add_trace(
        go.Bar(
            x=dates, y=total_disc,
            name="退院（決定＋予定）",
            marker_color="#2563EB",
        ),
        row=3, col=1,
    )

    fig.update_layout(
        height=700,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.10, x=0),
        margin=dict(l=40, r=20, t=80, b=40),
        barmode="group",
    )
    fig.update_yaxes(title_text="稼働率 (%)", range=[70, 100], row=1, col=1)
    fig.update_yaxes(title_text="在院患者数（名）", row=2, col=1)
    fig.update_yaxes(title_text="人数", row=3, col=1)

    st.plotly_chart(
        fig,
        use_container_width=True,
        key=f"discharge_calendar_forecast_{ward}_{testid_suffix}",
    )

    st.caption(
        f"📐 **予測の前提:** "
        f"開始日の在院数を起点に、各日「在院 − 退院予定 + 入院（予約 or 曜日平均）」で漸化式的に計算。"
        f" **信頼幅:** 近未来2週間 ±2名、2週以降 ±5名。"
        f" **点線部分**は精度が落ちるため参考値として扱ってください。"
        f" 緊急入院は過去1年の全入院の曜日平均で代用（予約入院がある日はそちらを優先）。"
    )


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
        '<div style="display:flex;gap:16px;flex-wrap:wrap;font-size:11px;color:#6B7280;margin:8px 0;padding:8px;background:#F9FAFB;border-radius:6px;">'
        '<span><b>🏥退</b> = 退院予定数（●決定 / ○予定）</span>'
        '<span><b>📥入</b> = 入院予定数（~n は曜日平均）</span>'
        '<span><b>残 N/5</b> = 枠残り</span>'
        '<span><b>⭐</b> 日曜推奨</span>'
        '<span><b>🎌</b> 祝日</span>'
        '<span style="color:#059669;"><b>🟢バー短め</b>=余裕</span>'
        '<span style="color:#B45309;"><b>🟡</b>+バー半分=ギリギリ</span>'
        '<span style="color:#DC2626;"><b>🔴</b>+バー満=満杯</span>'
        '<span style="color:#B91C1C;"><b>🚨</b>+赤バー=枠超過</span>'
        '<span><b>⚡N</b> 突発退院</span>'
        '<span><b>↩N</b> 前日超過の繰り越し</span>'
        '<span><b>✨</b> 動的枠調整（稼働率連動）</span>'
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

            # 選択日の session_state 初期値は今日
            sel_key = f"dcal_selected_{ward_label}"
            if sel_key not in st.session_state:
                st.session_state[sel_key] = today.isoformat()

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

            # ---- 詳細パネル（選択日の患者一覧・登録 UI） ----
            # 病棟タブ内・月タブ外に配置。当月/翌月どちらのカレンダーをクリックしても
            # この同じパネルが選択日を追従して更新される。
            sel_iso = st.session_state.get(sel_key, today.isoformat())
            try:
                sel_date = date.fromisoformat(sel_iso)
            except ValueError:
                sel_date = today
            _render_day_detail_panel(
                selected_date=sel_date,
                ward=ward_label,
                plans=plans,
                status_map=status_map,
                ward_map=ward_map,
                admission_details_df=admission_details_df,
            )

            # ---- 予測グラフ（稼働率・在院数・入退院） ----
            # 退院カレンダーに登録した予定を反映した、向こう1ヶ月（翌月末まで）の予測。
            # 副院長フィードバック (2026-04-24): 「稼働率への影響や入退院の数を
            # 視覚的にすぐわかる工夫」に応える。
            forecast_end = date(next_year, next_month, 28)  # 翌月末近くまで
            # より確実な翌月末: timedelta で算出
            if next_month == 12:
                forecast_end = date(next_year + 1, 1, 1) - timedelta(days=1)
            else:
                forecast_end = date(next_year, next_month + 1, 1) - timedelta(days=1)

            # 病床数（5F/6F は 47 床ずつ、全体 94 床）
            ward_beds = 47 if ward_label in ("5F", "6F") else 94

            # 開始時在院数を admission_details から推定
            initial_inp = _estimate_current_inpatients(
                admission_details_df, ward_label, today
            )
            # 推定できない / 異常値のフォールバック: 病床数 × 現在稼働率 or 85%
            if initial_inp == 0 or initial_inp > ward_beds * 1.05:
                if ward_occ is not None:
                    initial_inp = int(ward_beds * ward_occ)
                else:
                    initial_inp = int(ward_beds * 0.85)  # 保守的な値（稼働率85%相当）

            discharge_dow_mean = _estimate_discharges_by_dow(
                admission_details_df, ward_label
            )
            forecast = _compute_occupancy_forecast(
                ward=ward_label,
                start_date=today,
                end_date=forecast_end,
                initial_inpatients=initial_inp,
                total_beds=ward_beds,
                plans=plans,
                ward_map=ward_map,
                admission_details_df=admission_details_df,
                emergency_dow_mean=emergency_dow_mean,
                discharge_dow_mean=discharge_dow_mean,
            )
            _render_forecast_charts(
                forecast=forecast,
                today=today,
                total_beds=ward_beds,
                ward=ward_label,
                testid_suffix=ward_label,
            )

    # ---- 画面下部: E2E 用 testid ----
    st.markdown(
        '<div data-testid="discharge-calendar" style="display:none;"></div>',
        unsafe_allow_html=True,
    )


__all__ = ["render_discharge_calendar_tab"]
