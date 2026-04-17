"""
holiday_strategy_view.py — 連休対策セクションの描画モジュール

3 タブ構成:
  - 第 1 タブ「📊 今週の需要予測」
  - 第 2 タブ「📋 退院候補リスト」（Task 2 で追加）
  - 第 3 タブ「📅 予約可能枠」（Task 3 で追加予定）

pure function として提供する:
- calculate_next_holiday_countdown(today) — 次の大型連休までの日数計算
- compute_dow_occupancy(daily_df, weeks=8) — 曜日別稼働率（直近 N 週）
- classify_discharge_candidates(...) — 在院患者の A/B/C 仕分け

UI 描画:
- render_weekly_demand_dashboard(...) — タブ 1 の本体
- render_discharge_candidates_tab(...) — タブ 2 の本体

設計上のルール（個人情報保護）:
- admission_details の id 列は UUID であり、氏名・生年月日・診断名は元データに存在しない
- 出力 DataFrame は id を短縮表示（先頭 8 桁）する以外に個人情報カラムを一切含めない
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import pandas as pd


# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

# 大型連休の定義（名前, 開始日, 終了日）
# 年度で入れ替わる可能性があるため、将来的には config 化する
_HOLIDAY_PERIODS: list[tuple[str, date, date]] = [
    ("GW2026", date(2026, 4, 29), date(2026, 5, 5)),
    ("お盆2026", date(2026, 8, 13), date(2026, 8, 16)),
    ("SW2026", date(2026, 9, 19), date(2026, 9, 22)),
    ("年末年始2026-27", date(2026, 12, 27), date(2027, 1, 4)),
    ("GW2027", date(2027, 4, 29), date(2027, 5, 5)),
    ("お盆2027", date(2027, 8, 13), date(2027, 8, 16)),
]

# 退院調整開始推奨のリードタイム（週）
_DISCHARGE_PLANNING_LEAD_WEEKS = 3

# 曜日ラベル（月=0 ... 日=6）
_DOW_JA = ["月", "火", "水", "木", "金", "土", "日"]


# ---------------------------------------------------------------------------
# データ構造
# ---------------------------------------------------------------------------

@dataclass
class HolidayCountdown:
    """次の大型連休の情報."""
    name: str
    start_date: date
    end_date: date
    days_until_start: int  # 負なら連休中／既に終了
    duration_days: int
    is_ongoing: bool
    discharge_planning_start_date: date
    discharge_planning_passed: bool  # 推奨日が既に過ぎているか


# ---------------------------------------------------------------------------
# 次の大型連休までのカウントダウン
# ---------------------------------------------------------------------------

def calculate_next_holiday_countdown(today: date) -> Optional[HolidayCountdown]:
    """
    指定日付時点で「次の大型連休」（開催中を含む）を返す。

    ルール:
      - 連休がまだ始まっていない場合は最も近い連休を返す
      - 連休が開催中の場合はその連休を返す（is_ongoing=True）
      - すべての連休が終了している場合は None を返す

    Args:
        today: 基準日

    Returns:
        HolidayCountdown | None
    """
    if today is None:
        return None

    # 開催中 or 未来の連休のみフィルタ
    candidates: list[tuple[str, date, date]] = []
    for name, start, end in _HOLIDAY_PERIODS:
        if end >= today:
            candidates.append((name, start, end))

    if not candidates:
        return None

    # 最も早い開始日のものを返す
    candidates.sort(key=lambda x: x[1])
    name, start, end = candidates[0]

    duration = (end - start).days + 1
    days_until_start = (start - today).days
    is_ongoing = (start <= today <= end)

    planning_start = start - timedelta(weeks=_DISCHARGE_PLANNING_LEAD_WEEKS)
    planning_passed = today > planning_start

    return HolidayCountdown(
        name=name,
        start_date=start,
        end_date=end,
        days_until_start=days_until_start,
        duration_days=duration,
        is_ongoing=is_ongoing,
        discharge_planning_start_date=planning_start,
        discharge_planning_passed=planning_passed,
    )


# ---------------------------------------------------------------------------
# 曜日別稼働率の計算（直近 N 週の実測）
# ---------------------------------------------------------------------------

def compute_dow_occupancy(
    daily_df: pd.DataFrame,
    total_beds: int = 94,
    weeks: int = 8,
    ward: Optional[str] = None,
) -> dict[int, float]:
    """
    直近 N 週の日次データから曜日別稼働率（0-1）を計算する。

    データが不足している場合は 0.9（デフォルト）を全曜日に返す。

    Args:
        daily_df: 日次データ DataFrame（date, total_patients, discharges, optionally ward）
        total_beds: 病床数（全体 94, 5F/6F 47）
        weeks: 遡る週数
        ward: "5F" | "6F" | None

    Returns:
        dict {0: 月曜稼働率, ..., 6: 日曜稼働率}
    """
    default: dict[int, float] = {i: 0.9 for i in range(7)}

    if daily_df is None or len(daily_df) == 0:
        return default
    if total_beds is None or total_beds <= 0:
        return default

    df = daily_df.copy()

    # 日付列の正規化
    if "date" not in df.columns:
        return default
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    if len(df) == 0:
        return default

    # 病棟フィルタ（指定時のみ）
    if ward in ("5F", "6F") and "ward" in df.columns:
        df = df[df["ward"] == ward]
        if len(df) == 0:
            return default

    # 直近 N 週のみ
    max_date = df["date"].max()
    cutoff = max_date - pd.Timedelta(days=weeks * 7)
    df = df[df["date"] > cutoff]
    if len(df) == 0:
        return default

    if "total_patients" not in df.columns:
        return default

    # 厚労省定義: 稼働率 = (在院患者数 + 退院患者数) / 病床数
    dis = df["discharges"] if "discharges" in df.columns else 0
    df = df.assign(_occ_num=df["total_patients"] + dis)

    # 複数病棟が混在する場合は同日合算
    if "ward" in df.columns and ward is None:
        daily = df.groupby("date")["_occ_num"].sum().reset_index()
    else:
        daily = df[["date", "_occ_num"]].copy()

    daily["dow"] = daily["date"].dt.dayofweek
    means = daily.groupby("dow")["_occ_num"].mean()

    result: dict[int, float] = {}
    for i in range(7):
        if i in means.index and total_beds > 0:
            val = float(means.loc[i]) / float(total_beds)
            # 0-1 にクランプ
            result[i] = max(0.0, min(1.0, val))
        else:
            result[i] = default[i]
    return result


# ---------------------------------------------------------------------------
# 週単位の判定: 平均予想入院 vs 平均既存空床
# ---------------------------------------------------------------------------

def _week_overall_classification(
    dow_means: dict[int, float],
    vacancy_by_dow: dict[int, float],
    margin: float = 1.0,
) -> tuple[str, str, str]:
    """
    週全体（7日平均）で需要タイプを判定する。

    Returns:
        (type, emoji, label)
        type: "high" | "standard" | "low"
    """
    avg_demand = sum(dow_means.get(i, 0.0) for i in range(7)) / 7.0
    avg_vacancy = sum(vacancy_by_dow.get(i, 0.0) for i in range(7)) / 7.0
    delta = avg_demand - avg_vacancy

    if delta > margin:
        return "high", "🔴", "高需要"
    elif delta < -margin:
        return "low", "🟢", "通常運用"
    else:
        return "standard", "🟡", "標準"


# ---------------------------------------------------------------------------
# 描画: タブ 1「📊 今週の需要予測」
# ---------------------------------------------------------------------------

def render_weekly_demand_dashboard(
    forecast: dict,
    vacancy_by_dow: dict[int, float],
    ward: Optional[str],
    total_beds: int,
    today: Optional[date] = None,
    week_start: Optional[date] = None,
) -> None:
    """
    タブ 1「📊 今週の需要予測」本体を描画する。

    Args:
        forecast: forecast_weekly_demand() の戻り値
        vacancy_by_dow: {dow: 空床数/日}
        ward: 病棟フィルタ
        total_beds: 病床数
        today: 現在日（None なら date.today()）
        week_start: 対象週の月曜（None なら forecast["target_week_start"]）
    """
    import streamlit as st  # lazy import to keep this module importable in tests

    if today is None:
        today = date.today()
    if week_start is None:
        week_start = forecast.get("target_week_start", today)

    dow_means: dict[int, float] = forecast.get("dow_means", {i: 0.0 for i in range(7)})

    # -------------------------------------------------------------------
    # B-1. 週全体判定バナー
    # -------------------------------------------------------------------
    week_label = _format_week_label(week_start)
    ward_label = ward if ward in ("5F", "6F") else "全体"

    week_type, emoji, label = _week_overall_classification(dow_means, vacancy_by_dow)
    avg_demand = sum(dow_means.get(i, 0.0) for i in range(7)) / 7.0
    avg_vacancy = sum(vacancy_by_dow.get(i, 0.0) for i in range(7)) / 7.0

    banner_text = (
        f"**今週（{week_label}）の病棟需要判定（{ward_label}）: {emoji} {label}**\n\n"
        f"平均予想入院 {avg_demand:.1f}件/日 vs 平均既存空床 {avg_vacancy:.1f}床/日"
    )

    if week_type == "high":
        st.error(banner_text)
    elif week_type == "standard":
        st.warning(banner_text)
    else:
        st.success(banner_text)

    # -------------------------------------------------------------------
    # B-2. 7 日間予測テーブル
    # -------------------------------------------------------------------
    st.markdown("#### 📋 7日間予測テーブル")

    rows = []
    week_dates = [week_start + timedelta(days=i) for i in range(7)]
    for i in range(7):
        demand = float(dow_means.get(i, 0.0))
        vacancy = float(vacancy_by_dow.get(i, 0.0))
        delta = demand - vacancy
        if delta > 1.0:
            judge = "🔴 高需要"
        elif delta < -1.0:
            judge = "🟢 通常"
        else:
            judge = "🟡 標準"
        rows.append({
            "曜日": _DOW_JA[i],
            "日付": week_dates[i].strftime("%m/%d"),
            "予想入院（件）": round(demand, 1),
            "予想空床（床）": round(vacancy, 1),
            "需要判定": judge,
        })

    table_df = pd.DataFrame(rows)
    st.dataframe(table_df, hide_index=True, use_container_width=True)

    # 隠し div: E2E 用の testid（既存パターンに合わせる）
    st.markdown(
        f'<div data-testid="weekly-demand-summary" data-week-type="{week_type}" '
        f'data-ward="{ward_label}" style="display:none">'
        f'avg_demand={avg_demand:.2f};avg_vacancy={avg_vacancy:.2f}</div>',
        unsafe_allow_html=True,
    )

    # -------------------------------------------------------------------
    # B-3. 大型連休カウントダウンカード
    # -------------------------------------------------------------------
    st.markdown("---")
    st.markdown("#### 🗓 次の大型連休")
    countdown = calculate_next_holiday_countdown(today)
    if countdown is None:
        st.info("当面の大型連休は設定されていません。次年度カレンダーを追加してください。")
    else:
        _render_holiday_countdown_card(countdown, today)

    # -------------------------------------------------------------------
    # B-4. 計算方法の expander
    # -------------------------------------------------------------------
    st.markdown("---")
    with st.expander("💡 この予測の計算方法"):
        st.markdown(
            "- **予想入院数** = 過去 12ヶ月の曜日別平均 × 直近 2 週トレンド補正\n"
            "- **予想空床数** = 病床数 × (1 − 曜日別直近稼働率)\n"
            "- **需要判定** = 予想入院数 vs 既存空床の比較（margin = 1.0 床/日）\n"
            "- **データソース**: `data/admissions_consolidated_dedup.csv`（過去 12ヶ月・約 1,876 件）\n"
            "- **病棟フィルタ**: サイドバーの病棟選択（全体 / 5F / 6F）に連動\n"
            "- **曜日別稼働率**: 日次入力データの直近 8 週の同曜日実測から算出\n"
        )

        # 信頼度と sample_size
        conf = forecast.get("confidence", "low")
        n = forecast.get("sample_size", 0)
        trend = forecast.get("recent_trend_factor", 1.0)
        st.caption(
            f"現在の信頼度: **{conf}** / 集計レコード数: {n} 件 / "
            f"直近 2 週トレンド補正: ×{trend:.2f}"
        )


def _format_week_label(week_start: date) -> str:
    """週ラベルを `YYYY-MM-DD 週` 形式で生成する。"""
    return week_start.strftime("%Y-%m-%d") + " 週"


def _render_holiday_countdown_card(cd: HolidayCountdown, today: date) -> None:
    """HolidayCountdown を Streamlit 上にカード表示する。"""
    import streamlit as st

    start_str = cd.start_date.strftime("%Y-%m-%d")
    planning_str = cd.discharge_planning_start_date.strftime("%m月%d日")

    if cd.is_ongoing:
        st.warning(
            f"🗓 **{cd.name}（{cd.duration_days}日間）** は開催中です\n\n"
            f"期間: {start_str} 〜 {cd.end_date.strftime('%Y-%m-%d')}"
        )
        return

    lines = [
        f"🗓 **次の大型連休: {cd.name}（{cd.duration_days}日間）**",
        f"開始まで **あと {cd.days_until_start} 日**（{start_str}）",
    ]
    if cd.discharge_planning_passed:
        lines.append(
            f"退院調整開始推奨日: {planning_str}頃（3週間前、既に過ぎています）"
        )
    else:
        days_to_planning = (cd.discharge_planning_start_date - today).days
        lines.append(
            f"退院調整開始推奨日: {planning_str}頃（3週間前、あと {days_to_planning} 日）"
        )

    if cd.name.startswith("GW"):
        lines.append("GW パイロット運用中 ⚠")

    body = "\n\n".join(lines)
    if cd.days_until_start <= 7:
        st.error(body)
    elif cd.days_until_start <= 21:
        st.warning(body)
    else:
        st.info(body)


# ---------------------------------------------------------------------------
# 退院候補の仕分け（タブ 2 ロジック）
# ---------------------------------------------------------------------------

# 予定入院系の経路（A 区分の必要条件）
_PLANNED_ROUTES: frozenset[str] = frozenset({"外来紹介", "連携室"})

# A 判定のしきい値
_A_MIN_STAY_DAYS = 7  # 在院 ≥ 7 日（= 急性期を越えたとみなせる最低線）

# C 判定: 連休明けまでの推定滞在日数マージン（日）
_C_MIN_PROJECTED_STAY_MARGIN = 1

# 区分ラベル（絵文字付き）
CATEGORY_A = "🟢 A"
CATEGORY_B = "🟡 B"
CATEGORY_C = "🔵 C"
CATEGORY_UNKNOWN = "⚪ 判定不能"

_CATEGORY_ORDER = [CATEGORY_A, CATEGORY_B, CATEGORY_C, CATEGORY_UNKNOWN]

_CATEGORY_LABELS = {
    CATEGORY_A: "連休前退院候補",
    CATEGORY_B: "連休中継続妥当",
    CATEGORY_C: "連休明け退院予定",
    CATEGORY_UNKNOWN: "判定不能",
}


def _infer_phase_from_stay(stay_days: int) -> str:
    """在院日数から phase を推定する（los_to_phase と同じ境界）."""
    if stay_days <= 5:
        return "A"
    if stay_days <= 14:
        return "B"
    return "C"


def classify_discharge_candidates(
    admission_details_df: Optional[pd.DataFrame],
    daily_df: Optional[pd.DataFrame],  # noqa: ARG001 — 将来拡張用（直近稼働率の参照）
    as_of_date: date,
    ward: Optional[str] = None,
    next_holiday: Optional[HolidayCountdown] = None,
) -> pd.DataFrame:
    """
    現在入院中の患者を「連休前に退院可能か」で A/B/C/判定不能 に仕分ける。

    判定ルール（概要）:
      - A: 在院 ≥ 7 日 AND 経路が「外来紹介」「連携室」 AND phase が B or C
      - B: 在院 < 7 日 OR 経路が「救急」「下り搬送」 OR phase が A
      - C: 連休をまたいで滞在継続する見込み（連休明けまで推定）
      - 判定不能: データ不足

    Args:
        admission_details_df: admission_details の DataFrame。
            必須列: id, date, ward, event_type, route（optional: phase, los_days）
        daily_df: 日次在院患者数（現時点では classification に使用しない）
        as_of_date: 基準日（today）
        ward: "5F" | "6F" | None（None は全病棟）
        next_holiday: calculate_next_holiday_countdown() の戻り値。None 可

    Returns:
        列構成:
          patient_id_short, patient_id, ward, admission_date, stay_days,
          route, phase, recommended_category, manual_category

        個人情報保護のため、元データに存在しない氏名/年齢/診断名等のカラムは
        一切含めない。patient_id は UUID、patient_id_short は先頭 8 桁。
    """
    empty = pd.DataFrame(columns=[
        "patient_id_short",
        "patient_id",
        "ward",
        "admission_date",
        "stay_days",
        "route",
        "phase",
        "recommended_category",
        "manual_category",
    ])

    if admission_details_df is None or not isinstance(admission_details_df, pd.DataFrame):
        return empty
    if len(admission_details_df) == 0:
        return empty
    required = {"id", "date", "ward", "event_type"}
    if not required.issubset(set(admission_details_df.columns)):
        return empty

    df = admission_details_df.copy()

    # ward フィルタ
    if ward in ("5F", "6F"):
        df = df[df["ward"].astype(str) == ward]
    if len(df) == 0:
        return empty

    # 日付の正規化
    df["_date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["_date"])
    if len(df) == 0:
        return empty

    # 現在入院中 = admission 行のうち、同じ ward x admission_date に
    # 対応する discharge が存在しない行
    #
    # マッチング戦略:
    #   discharges 側は los_days と date を持つため、
    #   (ward, discharge_date - los_days) = admission_date となる組を消し込む。
    #   los_days が欠損している discharge は対応不能なので現在入院判定から除外しない。
    admissions = df[df["event_type"].astype(str) == "admission"].copy()
    discharges = df[df["event_type"].astype(str) == "discharge"].copy()

    # 退院済み (ward, admission_date) キー集合
    discharged_keys: set[tuple[str, str]] = set()
    for _, row in discharges.iterrows():
        los_raw = row.get("los_days", "")
        try:
            los_int = int(float(los_raw)) if los_raw not in ("", None) else None
        except (ValueError, TypeError):
            los_int = None
        if los_int is None:
            continue
        try:
            d_date = pd.to_datetime(row.get("date")).date()
        except Exception:
            continue
        try:
            adm_date = d_date - timedelta(days=los_int)
        except Exception:
            continue
        discharged_keys.add((str(row.get("ward", "")), adm_date.isoformat()))

    # 仕分けロジック ---------------------------------------------------
    rows_out: list[dict] = []
    for _, row in admissions.iterrows():
        try:
            adm_date = pd.to_datetime(row["_date"]).date()
        except Exception:
            continue
        if adm_date > as_of_date:
            # 未来の入院予定は対象外
            continue

        ward_val = str(row.get("ward", ""))
        key = (ward_val, adm_date.isoformat())
        if key in discharged_keys:
            continue  # 既に退院済み

        stay_days = (as_of_date - adm_date).days + 1  # Day 1 = 入院初日
        if stay_days <= 0:
            continue

        route_raw = row.get("route", "")
        try:
            if pd.isna(route_raw):
                route_raw = ""
        except (TypeError, ValueError):
            pass
        route = str(route_raw) if route_raw is not None else ""

        # admission 行の phase は基本的に空なので stay_days から推定
        phase_raw = row.get("phase", "")
        try:
            if pd.isna(phase_raw):
                phase_raw = ""
        except (TypeError, ValueError):
            pass
        phase = str(phase_raw) if phase_raw not in (None, "") else _infer_phase_from_stay(stay_days)

        # 区分判定 -----------------------------------------------------
        category = _classify_one(
            stay_days=stay_days,
            route=route,
            phase=phase,
            as_of_date=as_of_date,
            next_holiday=next_holiday,
        )

        pid = str(row.get("id", ""))
        pid_short = pid[:8] if pid else ""

        rows_out.append({
            "patient_id_short": pid_short,
            "patient_id": pid,
            "ward": ward_val,
            "admission_date": adm_date.isoformat(),
            "stay_days": stay_days,
            "route": route or "不明",
            "phase": phase or "不明",
            "recommended_category": category,
            "manual_category": category,
        })

    if not rows_out:
        return empty

    result = pd.DataFrame(rows_out)
    # 推奨区分順 → 在院日数降順でソート（優先対応順）
    cat_rank = {c: i for i, c in enumerate(_CATEGORY_ORDER)}
    result["_rank"] = result["recommended_category"].map(cat_rank).fillna(99).astype(int)
    result = result.sort_values(
        by=["_rank", "stay_days"],
        ascending=[True, False],
    ).drop(columns=["_rank"]).reset_index(drop=True)
    return result


def _classify_one(
    stay_days: int,
    route: str,
    phase: str,
    as_of_date: date,
    next_holiday: Optional[HolidayCountdown],
) -> str:
    """1 患者を A/B/C/判定不能 に分類する pure helper."""
    # データ不足
    if not route or route == "不明":
        return CATEGORY_UNKNOWN

    # C: 連休を明確にまたぐ見込み
    # 平均 LOS（5F=17.7, 6F=21.3 程度）を前提に、next_holiday 終了までの必要
    # 在院日数と比較する。近似のため margin=1 日。
    if next_holiday is not None and not next_holiday.is_ongoing:
        # 連休明けの翌日（= end_date + 1）
        recover_day = next_holiday.end_date + timedelta(days=1)
        # as_of_date から recover_day までの日数
        days_until_recovery = (recover_day - as_of_date).days
        # 典型 LOS を phase ベースで推定
        typical_los = {"A": 5, "B": 12, "C": 20}.get(phase, 14)
        projected_remaining = max(0, typical_los - stay_days)
        if days_until_recovery > 0 and projected_remaining >= days_until_recovery + _C_MIN_PROJECTED_STAY_MARGIN:
            return CATEGORY_C

    # B（強条件）: 救急系経路 or phase A（急性期中）
    if route in ("救急", "下り搬送", "ウォークイン"):
        return CATEGORY_B
    if phase == "A":
        return CATEGORY_B

    # A 条件: 在院 ≥ 7 日 AND 予定入院系 AND phase B or C
    if (
        stay_days >= _A_MIN_STAY_DAYS
        and route in _PLANNED_ROUTES
        and phase in ("B", "C")
    ):
        return CATEGORY_A

    # どれにも該当しない場合
    # - 在院 < 7 日（急性期抜けきっていない）や
    # - phase A（急性期中）は B
    if stay_days < _A_MIN_STAY_DAYS:
        return CATEGORY_B

    # それ以外（例: 予定入院だが phase A 完了直後で stay_days=7 だが phase 推定で A）
    return CATEGORY_B


def summarize_categories(
    classified_df: pd.DataFrame,
    category_col: str = "manual_category",
) -> dict[str, int]:
    """区分別の件数集計（順序を保つ dict で返す）."""
    counts = {c: 0 for c in _CATEGORY_ORDER}
    if classified_df is None or len(classified_df) == 0 or category_col not in classified_df.columns:
        return counts
    vc = classified_df[category_col].value_counts()
    for cat in _CATEGORY_ORDER:
        counts[cat] = int(vc.get(cat, 0))
    return counts


# ---------------------------------------------------------------------------
# 描画: タブ 2「📋 退院候補リスト」
# ---------------------------------------------------------------------------

def render_discharge_candidates_tab(
    details_df: Optional[pd.DataFrame],
    daily_df: Optional[pd.DataFrame],
    ward: Optional[str],
    next_holiday: Optional[HolidayCountdown],
    today: Optional[date] = None,
) -> None:
    """
    タブ 2「📋 退院候補リスト」本体を描画する。

    Args:
        details_df: st.session_state["admission_details"]
        daily_df: st.session_state["daily_data"]（将来拡張用）
        ward: "5F" | "6F" | None
        next_holiday: calculate_next_holiday_countdown() の戻り値
        today: 基準日（None なら date.today()）
    """
    import streamlit as st  # lazy import

    if today is None:
        today = date.today()

    # ---- ヘッダーサマリー ----
    ward_label = ward if ward in ("5F", "6F") else "全体"
    if next_holiday is None:
        st.info("当面の大型連休が設定されていません。カウントダウン対象がないため、現時点の在院患者一覧のみを表示します。")
        holiday_header = "次の大型連休: （未設定）"
    else:
        recover_day = next_holiday.end_date + timedelta(days=1)
        planning_date = next_holiday.discharge_planning_start_date
        if next_holiday.discharge_planning_passed:
            gap = (planning_date - today).days
            planning_txt = f"退院調整推奨日: {planning_date.strftime('%m月%d日')}頃（あと {gap} 日 ※過ぎています）"
        else:
            gap = (planning_date - today).days
            planning_txt = f"退院調整推奨日: {planning_date.strftime('%m月%d日')}頃（あと {gap} 日）"
        holiday_header = (
            f"**次の大型連休: {next_holiday.name}"
            f"（{next_holiday.start_date.strftime('%Y-%m-%d')} 〜 "
            f"{next_holiday.end_date.strftime('%Y-%m-%d')}、"
            f"{next_holiday.duration_days}日間）**  \n{planning_txt}"
        )
        st.markdown(holiday_header)
        st.caption(f"連休明け復帰日（参考）: {recover_day.strftime('%Y-%m-%d')}")

    # ---- 分類 ----
    classified = classify_discharge_candidates(
        admission_details_df=details_df,
        daily_df=daily_df,
        as_of_date=today,
        ward=ward,
        next_holiday=next_holiday,
    )

    # セッションステートに保持（手動区分変更の永続化用）
    state_key = f"_discharge_candidates_manual_{ward_label}"
    if state_key not in st.session_state or not isinstance(st.session_state[state_key], dict):
        st.session_state[state_key] = {}
    manual_map: dict[str, str] = st.session_state[state_key]

    # 手動区分を反映
    if len(classified) > 0:
        classified["manual_category"] = classified.apply(
            lambda r: manual_map.get(r["patient_id"], r["recommended_category"]),
            axis=1,
        )

    # ---- サマリー ----
    total = len(classified)
    if total == 0:
        st.info(
            "現在、在院中の患者データがありません。\n\n"
            "（`admission_details` に入院レコードが無いか、対応する退院レコードと相殺された状態です）"
        )
        # それでも testid は出す（E2E 用）
        st.markdown(
            f'<div data-testid="discharge-candidates-summary" '
            f'data-total="0" data-ward="{ward_label}" style="display:none">empty</div>',
            unsafe_allow_html=True,
        )
        return

    counts_by_ward = classified["ward"].value_counts().to_dict()
    counts_5f = int(counts_by_ward.get("5F", 0))
    counts_6f = int(counts_by_ward.get("6F", 0))

    cat_counts = summarize_categories(classified, category_col="manual_category")

    summary_lines = [f"現在在院患者数: **{total}名**"]
    if ward in ("5F", "6F"):
        summary_lines[0] += f"（{ward}）"
    else:
        summary_lines[0] += f"（5F: {counts_5f} / 6F: {counts_6f}）"
    for cat in _CATEGORY_ORDER:
        n = cat_counts[cat]
        pct = (n / total * 100.0) if total > 0 else 0.0
        summary_lines.append(f"- {cat} {_CATEGORY_LABELS[cat]}  {n}名（{pct:.0f}%）")
    st.markdown("\n".join(summary_lines))

    # ---- フィルタ行 ----
    st.markdown("---")
    st.markdown("#### 🔍 フィルタ")
    col1, col2, col3 = st.columns([1.2, 1.5, 2])
    with col1:
        filter_ward = st.selectbox(
            "病棟",
            options=["（サイドバーと連動）", "5F", "6F"],
            index=0,
            key=f"dc_ward_{ward_label}",
            help="サイドバーの病棟選択と連動しています。このフィルタは追加の絞り込みです。",
        )
    with col2:
        filter_cat = st.selectbox(
            "区分",
            options=["すべて"] + _CATEGORY_ORDER,
            index=0,
            key=f"dc_cat_{ward_label}",
        )
    with col3:
        stay_min = int(classified["stay_days"].min())
        stay_max = int(classified["stay_days"].max())
        if stay_min == stay_max:
            st.caption(f"在院日数レンジ: {stay_min} 日のみ")
            stay_range = (stay_min, stay_max)
        else:
            stay_range = st.slider(
                "在院日数レンジ",
                min_value=stay_min,
                max_value=stay_max,
                value=(stay_min, stay_max),
                key=f"dc_stay_{ward_label}",
            )

    # フィルタ適用
    filtered = classified.copy()
    if filter_ward in ("5F", "6F"):
        filtered = filtered[filtered["ward"] == filter_ward]
    if filter_cat != "すべて":
        filtered = filtered[filtered["manual_category"] == filter_cat]
    filtered = filtered[
        (filtered["stay_days"] >= stay_range[0])
        & (filtered["stay_days"] <= stay_range[1])
    ]

    # ---- 患者リスト表 ----
    st.markdown("---")
    st.markdown(f"#### 📝 患者リスト（{len(filtered)} 名）")

    if len(filtered) == 0:
        st.info("該当する患者がいません。フィルタを緩めてください。")
    else:
        display_df = filtered[[
            "patient_id_short",
            "ward",
            "admission_date",
            "stay_days",
            "route",
            "phase",
            "recommended_category",
            "manual_category",
        ]].rename(columns={
            "patient_id_short": "患者ID",
            "ward": "病棟",
            "admission_date": "入院日",
            "stay_days": "在院日数",
            "route": "経路",
            "phase": "Phase",
            "recommended_category": "推奨区分",
            "manual_category": "手動区分",
        })

        edited = st.data_editor(
            display_df,
            hide_index=True,
            use_container_width=True,
            disabled=[
                "患者ID", "病棟", "入院日", "在院日数", "経路", "Phase", "推奨区分",
            ],
            column_config={
                "手動区分": st.column_config.SelectboxColumn(
                    "手動区分",
                    options=_CATEGORY_ORDER,
                    required=True,
                    help="会議中の議論結果を反映させてください",
                ),
            },
            key=f"dc_editor_{ward_label}",
        )

        # 手動変更をセッションステートへ保存
        try:
            for i, row in edited.reset_index(drop=True).iterrows():
                orig_idx = filtered.index[i]
                pid = filtered.loc[orig_idx, "patient_id"]
                new_cat = row["手動区分"]
                if new_cat and new_cat in _CATEGORY_ORDER:
                    manual_map[pid] = new_cat
        except Exception:
            # 編集反映失敗時は黙ってスキップ（UI を壊さない）
            pass

    # ---- エクスポート ----
    st.markdown("---")
    st.markdown("#### 💾 エクスポート")
    exp_col1, exp_col2, exp_col3 = st.columns(3)

    csv_df = classified.rename(columns={
        "patient_id_short": "患者ID(短縮)",
        "patient_id": "患者ID(UUID)",
        "ward": "病棟",
        "admission_date": "入院日",
        "stay_days": "在院日数",
        "route": "経路",
        "phase": "Phase",
        "recommended_category": "推奨区分",
        "manual_category": "手動区分",
    })
    csv_buf = io.StringIO()
    csv_df.to_csv(csv_buf, index=False)
    csv_bytes = csv_buf.getvalue().encode("utf-8-sig")

    with exp_col1:
        st.download_button(
            "📄 CSV ダウンロード",
            data=csv_bytes,
            file_name=f"discharge_candidates_{today.isoformat()}_{ward_label}.csv",
            mime="text/csv",
            key=f"dc_csv_{ward_label}",
            help="退院調整会議用の完全版（手動区分変更反映）",
        )

    with exp_col2:
        show_print = st.button(
            "🖨 印刷レイアウト表示",
            key=f"dc_print_{ward_label}",
            help="区分別にグループ化して表示します",
        )

    with exp_col3:
        # 統計のみ（個人情報なし）
        stats_rows = []
        for cat in _CATEGORY_ORDER:
            stats_rows.append({
                "区分": cat,
                "ラベル": _CATEGORY_LABELS[cat],
                "人数": cat_counts[cat],
                "比率": f"{(cat_counts[cat] / total * 100):.1f}%" if total > 0 else "0.0%",
            })
        stats_df = pd.DataFrame(stats_rows)
        stats_buf = io.StringIO()
        stats_df.to_csv(stats_buf, index=False)
        st.download_button(
            "📊 統計のみエクスポート",
            data=stats_buf.getvalue().encode("utf-8-sig"),
            file_name=f"discharge_stats_{today.isoformat()}_{ward_label}.csv",
            mime="text/csv",
            key=f"dc_stats_{ward_label}",
            help="個別患者情報を含まない集計値のみ",
        )

    if show_print:
        st.markdown("---")
        st.markdown("### 🖨 印刷プレビュー")
        st.caption(
            f"基準日: {today.isoformat()}   "
            f"対象病棟: {ward_label}   "
            f"総在院数: {total} 名"
        )
        for cat in _CATEGORY_ORDER:
            group = classified[classified["manual_category"] == cat]
            if len(group) == 0:
                continue
            st.markdown(f"**{cat} {_CATEGORY_LABELS[cat]}  ({len(group)}名)**")
            print_df = group[[
                "patient_id_short",
                "ward",
                "admission_date",
                "stay_days",
                "route",
                "phase",
            ]].rename(columns={
                "patient_id_short": "患者ID",
                "ward": "病棟",
                "admission_date": "入院日",
                "stay_days": "在院日数",
                "route": "経路",
                "phase": "Phase",
            })
            st.table(print_df)

    # ---- 行動ガイド ----
    with st.expander("💡 退院調整会議での使い方"):
        st.markdown(
            "1. 本リストを画面共有、または印刷して会議で配布いたします\n"
            "2. 区分 🟢 A の各患者について、主治医・看護師・MSW で退院可能性を確認いたします\n"
            "3. 「手動区分」を変更しながら、連休前に退院させる候補を絞り込みます\n"
            "4. 絞り込んだリストを CSV エクスポートして記録に残します\n"
            "5. 次回会議で進捗を共有いたします\n\n"
            "判定アルゴリズムは近似です。最終判断は必ず臨床的評価に基づいて行ってください。\n"
            "本リストは個人情報（氏名・生年月日・診断名）を一切含みません。"
        )

    # ---- E2E 用 testid ----
    st.markdown(
        f'<div data-testid="discharge-candidates-summary" '
        f'data-total="{total}" data-ward="{ward_label}" '
        f'data-a="{cat_counts[CATEGORY_A]}" '
        f'data-b="{cat_counts[CATEGORY_B]}" '
        f'data-c="{cat_counts[CATEGORY_C]}" '
        f'data-unknown="{cat_counts[CATEGORY_UNKNOWN]}" '
        f'style="display:none">classified</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# タブ 3「📅 予約可能枠」: 日別需要予測・カレンダー表示
# ---------------------------------------------------------------------------

# カラー閾値（可能枠ベース）
_BOOKING_THRESHOLD_RED = 2    # 可能枠 0〜1 → 🔴 満員
_BOOKING_THRESHOLD_YELLOW = 5  # 可能枠 2〜4 → 🟡 やや混雑（5 以上 → 🟢）

# 連休期間の入院数減少率（-90%）
_HOLIDAY_ADMISSION_REDUCTION = 0.10  # 残り 10% だけ期待
# 連休明け週の補正（+20%）
_POST_HOLIDAY_SURGE_FACTOR = 1.20


def _is_in_holiday_period(target_date: date) -> Optional[str]:
    """指定日が大型連休期間に含まれるなら連休名を返す。含まれなければ None."""
    for name, start, end in _HOLIDAY_PERIODS:
        if start <= target_date <= end:
            return name
    return None


def _is_post_holiday_week(target_date: date) -> bool:
    """指定日が大型連休明けの 7 日以内（連休終了翌日〜+6 日）か."""
    for _, _, end in _HOLIDAY_PERIODS:
        recover_start = end + timedelta(days=1)
        recover_end = end + timedelta(days=7)
        if recover_start <= target_date <= recover_end:
            return True
    return False


def _classify_booking_availability(slots: int, in_holiday: bool) -> tuple[str, str]:
    """
    可能枠数と連休フラグから (emoji, label) を返す。

    - 連休中: 🔵 連休 (枠「-」)
    - 可能枠 0〜1: 🔴 満員
    - 可能枠 2〜4: 🟡 やや混雑
    - 可能枠 >= 5: 🟢 通常
    """
    if in_holiday:
        return "🔵", "連休"
    if slots < _BOOKING_THRESHOLD_RED:
        return "🔴", "満員"
    if slots < _BOOKING_THRESHOLD_YELLOW:
        return "🟡", "やや混雑"
    return "🟢", "通常"


def forecast_daily_demand_for_period(
    forecast: Optional[dict],
    start_date: date,
    end_date: date,
    daily_df: Optional[pd.DataFrame] = None,
    ward: Optional[str] = None,
    total_beds: int = 94,
    admission_details_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    start_date 〜 end_date（両端含む）の各日について、日別需要・空床・可能枠を計算する。

    - 連休期間は予想入院を -90%（= ×0.10）
    - 連休明けの 7 日間は +20%（= ×1.20）
    - 予想空床 = total_beds × (1 - 曜日別稼働率)
    - 既予約 = admission_details_df の event_type=='admission' で date が一致する件数
    - 可能枠 = 予想空床 - 予想入院 - 既予約（下限 0）

    Args:
        forecast: forecast_weekly_demand() の戻り値（dow_means, recent_trend_factor を使用）
        start_date: 期間の開始日（含む）
        end_date: 期間の終了日（含む）
        daily_df: 日次データ（compute_dow_occupancy で使用）
        ward: "5F" | "6F" | None
        total_beds: 病床数
        admission_details_df: 既予約カウント用

    Returns:
        DataFrame with columns:
          date (date), dow (int 0-6), dow_label (str),
          expected_admissions (float), expected_vacancy (float),
          holiday_name (str | ""), is_holiday (bool), is_post_holiday (bool),
          booked_count (int), available_slots (int),
          emoji (str), label (str), is_holiday_flag (bool)
    """
    cols = [
        "date", "dow", "dow_label",
        "expected_admissions", "expected_vacancy",
        "holiday_name", "is_holiday", "is_post_holiday",
        "booked_count", "available_slots",
        "emoji", "label",
    ]
    if start_date is None or end_date is None:
        return pd.DataFrame(columns=cols)
    if end_date < start_date:
        return pd.DataFrame(columns=cols)

    # dow_means と trend_factor
    if forecast is None:
        dow_means = {i: 0.0 for i in range(7)}
        trend_factor = 1.0
    else:
        dow_means = forecast.get("dow_means") or {i: 0.0 for i in range(7)}
        trend_factor = float(forecast.get("recent_trend_factor") or 1.0)

    # 曜日別空床（daily_df から）
    dow_occ = compute_dow_occupancy(
        daily_df if daily_df is not None else pd.DataFrame(),
        total_beds=total_beds,
        weeks=8,
        ward=ward,
    )

    # 既予約マップ: (ward, date.isoformat()) -> count
    booked_map: dict[tuple[str, str], int] = {}
    if admission_details_df is not None and isinstance(admission_details_df, pd.DataFrame) and len(admission_details_df) > 0:
        required = {"date", "ward", "event_type"}
        if required.issubset(set(admission_details_df.columns)):
            ad = admission_details_df.copy()
            ad = ad[ad["event_type"].astype(str) == "admission"]
            if ward in ("5F", "6F"):
                ad = ad[ad["ward"].astype(str) == ward]
            ad["_date"] = pd.to_datetime(ad["date"], errors="coerce")
            ad = ad.dropna(subset=["_date"])
            for _, row in ad.iterrows():
                try:
                    d = row["_date"].date()
                except Exception:
                    continue
                w = str(row.get("ward", ""))
                key = (w, d.isoformat())
                booked_map[key] = booked_map.get(key, 0) + 1

    rows: list[dict] = []
    cursor = start_date
    while cursor <= end_date:
        dow = cursor.weekday()
        dow_label = _DOW_JA[dow]

        base_admissions = float(dow_means.get(dow, 0.0)) * trend_factor
        base_vacancy = float(total_beds) * (1.0 - float(dow_occ.get(dow, 0.9)))

        holiday_name = _is_in_holiday_period(cursor) or ""
        in_holiday = bool(holiday_name)
        post_holiday = _is_post_holiday_week(cursor) and not in_holiday

        # 入院数の補正
        if in_holiday:
            expected_adm = base_admissions * _HOLIDAY_ADMISSION_REDUCTION
        elif post_holiday:
            expected_adm = base_admissions * _POST_HOLIDAY_SURGE_FACTOR
        else:
            expected_adm = base_admissions

        expected_vac = max(0.0, base_vacancy)

        # 既予約（ward=None（全体）なら 5F+6F 合算相当、map 内の全 key で date が一致するものを合計）
        if ward in ("5F", "6F"):
            booked = int(booked_map.get((ward, cursor.isoformat()), 0))
        else:
            booked = 0
            for (w, dstr), cnt in booked_map.items():
                if dstr == cursor.isoformat():
                    booked += cnt

        # 可能枠 = 空床 − 予想入院 − 既予約（連休中は 0 固定）
        if in_holiday:
            slots = 0
        else:
            slots = max(0, int(round(expected_vac - expected_adm - booked)))

        emoji, label = _classify_booking_availability(slots, in_holiday)

        rows.append({
            "date": cursor,
            "dow": dow,
            "dow_label": dow_label,
            "expected_admissions": round(expected_adm, 2),
            "expected_vacancy": round(expected_vac, 2),
            "holiday_name": holiday_name,
            "is_holiday": in_holiday,
            "is_post_holiday": post_holiday,
            "booked_count": booked,
            "available_slots": slots,
            "emoji": emoji,
            "label": label,
        })
        cursor = cursor + timedelta(days=1)

    return pd.DataFrame(rows, columns=cols)


def _summarize_booking_counts(daily_df: pd.DataFrame) -> dict[str, int]:
    """カレンダー期間中の判定別日数サマリー."""
    summary = {"通常": 0, "やや混雑": 0, "満員": 0, "連休": 0}
    if daily_df is None or len(daily_df) == 0:
        return summary
    for _, row in daily_df.iterrows():
        label = row.get("label", "")
        if label in summary:
            summary[label] += 1
    return summary


def render_booking_availability_calendar(
    forecast: Optional[dict],
    details_df: Optional[pd.DataFrame],
    daily_df: Optional[pd.DataFrame],
    ward: Optional[str],
    total_beds: int = 94,
    today: Optional[date] = None,
    weeks_ahead: int = 4,
) -> None:
    """
    タブ 3「📅 予約可能枠」本体を描画する。

    Args:
        forecast: forecast_weekly_demand() の戻り値
        details_df: st.session_state["admission_details"]
        daily_df: st.session_state["daily_data"]
        ward: "5F" | "6F" | None
        total_beds: 病床数
        today: 基準日（None なら date.today()）
        weeks_ahead: 先まで表示する週数（デフォルト 4）
    """
    import streamlit as st  # lazy import

    if today is None:
        today = date.today()

    ward_label = ward if ward in ("5F", "6F") else "全体"

    # 表示期間: 今週月曜 〜 weeks_ahead 週先の日曜
    week_start = today - timedelta(days=today.weekday())
    period_start = week_start
    period_end = week_start + timedelta(days=weeks_ahead * 7 - 1)

    # 日次需要を生成
    daily_forecast = forecast_daily_demand_for_period(
        forecast=forecast,
        start_date=period_start,
        end_date=period_end,
        daily_df=daily_df,
        ward=ward,
        total_beds=total_beds,
        admission_details_df=details_df,
    )

    # ------------------------------------------------------------------
    # B-1. ヘッダーサマリー
    # ------------------------------------------------------------------
    st.markdown(f"**今日: {today.isoformat()}（{_DOW_JA[today.weekday()]}）**")

    # 次の連休
    next_holiday = calculate_next_holiday_countdown(today)
    if next_holiday is not None:
        st.markdown(
            f"次の連休: **{next_holiday.name}**"
            f"（{next_holiday.start_date.strftime('%m/%d')} 〜 "
            f"{next_holiday.end_date.strftime('%m/%d')}、"
            f"{next_holiday.duration_days}日間）"
        )

        # 連休明け初日
        if not next_holiday.is_ongoing:
            recover_day = next_holiday.end_date + timedelta(days=1)
            if period_start <= recover_day <= period_end and len(daily_forecast) > 0:
                recover_row = daily_forecast[daily_forecast["date"] == recover_day]
                if len(recover_row) > 0:
                    rr = recover_row.iloc[0]
                    em = rr["emoji"]
                    lbl = rr["label"]
                    st.markdown(
                        f"連休明け初日（{recover_day.strftime('%m/%d %a')} → "
                        f"{_DOW_JA[recover_day.weekday()]}曜日）: "
                        f"{em} {lbl}予想 — "
                        f"{'予約を控えめに' if lbl != '通常' else '通常運用可'}"
                    )
    else:
        st.caption("当面の大型連休は設定されていません。")

    # 合計日数サマリー
    summary = _summarize_booking_counts(daily_forecast)
    st.markdown(
        f"今週〜{weeks_ahead}週後 合計: "
        f"🟢 通常 {summary['通常']}日 / "
        f"🟡 やや混雑 {summary['やや混雑']}日 / "
        f"🔴 満員 {summary['満員']}日 / "
        f"🔵 連休 {summary['連休']}日"
    )

    if len(daily_forecast) == 0:
        st.info("表示期間のデータが生成できませんでした。daily_data や forecast を確認してください。")
        return

    # ------------------------------------------------------------------
    # B-2. カレンダー本体（週単位） + 詳細パネル
    # ------------------------------------------------------------------
    st.markdown("---")
    st.markdown("#### 🗓 4週間カレンダー")

    # 選択中の日付（session_state で保持）
    sel_key = f"booking_cal_selected_{ward_label}"
    if sel_key not in st.session_state:
        st.session_state[sel_key] = today.isoformat()

    # 左: カレンダー / 右: 詳細パネル
    col_cal, col_detail = st.columns([3, 2])

    with col_cal:
        # 週ごとに区切る
        for w in range(weeks_ahead):
            wk_start = period_start + timedelta(days=w * 7)
            wk_end = wk_start + timedelta(days=6)
            st.markdown(
                f"**第{w+1}週 ({wk_start.strftime('%m/%d')}〜{wk_end.strftime('%m/%d')})**"
            )
            day_cols = st.columns(7)
            for i in range(7):
                d = wk_start + timedelta(days=i)
                # 期間外 guard
                match = daily_forecast[daily_forecast["date"] == d]
                if len(match) == 0:
                    continue
                row = match.iloc[0]
                emoji = row["emoji"]
                lbl = row["label"]
                slots = int(row["available_slots"])
                slot_str = "-" if row["is_holiday"] else f"{slots}枠"
                is_today = (d == today)
                holiday_tag = ""
                if row["holiday_name"]:
                    holiday_tag = "(連休)"
                elif row["is_post_holiday"]:
                    holiday_tag = "(明)"

                with day_cols[i]:
                    label_text = (
                        f"{_DOW_JA[d.weekday()]} {d.day}{holiday_tag}\n"
                        f"{emoji} {slot_str}"
                    )
                    btn_key = f"booking_cal_btn_{ward_label}_{d.isoformat()}"
                    if st.button(
                        label_text,
                        key=btn_key,
                        use_container_width=True,
                        type="primary" if is_today else "secondary",
                    ):
                        st.session_state[sel_key] = d.isoformat()

    with col_detail:
        st.markdown("#### 📝 日付の詳細")
        sel_iso = st.session_state.get(sel_key, today.isoformat())
        try:
            sel_date = date.fromisoformat(sel_iso)
        except ValueError:
            sel_date = today
        match = daily_forecast[daily_forecast["date"] == sel_date]
        if len(match) == 0:
            st.info("選択中の日付は表示期間外です。")
        else:
            row = match.iloc[0]
            em = row["emoji"]
            lbl = row["label"]
            dow_lbl = _DOW_JA[sel_date.weekday()]
            tag = ""
            if row["holiday_name"]:
                tag = f" — {row['holiday_name']} 連休中"
            elif row["is_post_holiday"]:
                tag = " — 連休明け"

            st.markdown(
                f"**{sel_date.isoformat()} ({dow_lbl}){tag}**  \n"
                f"予想入院: {row['expected_admissions']:.1f} 件  \n"
                f"予想空床: {row['expected_vacancy']:.1f} 床  \n"
                f"既予約: {int(row['booked_count'])} 件  \n"
                f"可能枠: **{'-' if row['is_holiday'] else int(row['available_slots'])}**"
                f" （{em} {lbl}）"
            )

            # 推奨運用
            st.markdown("**推奨運用:**")
            if row["is_holiday"]:
                st.markdown(
                    "- 連休期間中は予定入院の予約を避ける\n"
                    "- 連休明け以降を提案する"
                )
            elif lbl == "満員":
                st.markdown(
                    f"- 新規予定入院の予約は別日を提案  \n"
                    f"- やむを得ず入れる場合は手術日固定等の優先度高いもののみ"
                )
            elif lbl == "やや混雑":
                st.markdown(
                    "- 代替日（近隣の 🟢 の日）を第一に提案  \n"
                    "- 同日確定を希望される場合は受入可能"
                )
            else:
                st.markdown("- そのまま予約確定して問題なし")

    # ------------------------------------------------------------------
    # B-3. 診療科別 予約ルール（簡易）
    # ------------------------------------------------------------------
    st.markdown("---")
    with st.expander("🔧 診療科別 予約ルール（簡易）"):
        st.caption(
            "ルールはセッション内に保存されます。初期実装のため、カレンダー上の判定への反映は将来対応です。"
        )
        rules_key = "holiday_booking_rules"
        if rules_key not in st.session_state or not isinstance(st.session_state[rules_key], dict):
            st.session_state[rules_key] = {}

        dept = st.selectbox(
            "診療科",
            options=["内科", "外科", "整形外科", "その他"],
            index=0,
            key=f"booking_rules_dept_{ward_label}",
        )
        current = st.session_state[rules_key].get(dept, {})
        op_fixed = st.checkbox(
            "手術日固定（火・木のみ予約可）",
            value=bool(current.get("op_fixed", False)),
            key=f"booking_rules_op_{ward_label}_{dept}",
        )
        no_post = st.checkbox(
            "連休明け 3 日間は予約しない",
            value=bool(current.get("no_post_holiday_3d", False)),
            key=f"booking_rules_np_{ward_label}_{dept}",
        )
        if st.button("ルールを保存", key=f"booking_rules_save_{ward_label}_{dept}"):
            st.session_state[rules_key][dept] = {
                "op_fixed": op_fixed,
                "no_post_holiday_3d": no_post,
            }
            st.success(f"{dept} のルールを保存しました。")

    # ------------------------------------------------------------------
    # B-4. エクスポート
    # ------------------------------------------------------------------
    st.markdown("---")
    st.markdown("#### 💾 エクスポート")
    exp_col1, exp_col2 = st.columns(2)

    csv_df = daily_forecast[[
        "date", "dow_label", "expected_admissions", "expected_vacancy",
        "booked_count", "available_slots", "label", "holiday_name",
    ]].rename(columns={
        "date": "日付",
        "dow_label": "曜日",
        "expected_admissions": "予想入院",
        "expected_vacancy": "予想空床",
        "booked_count": "既予約",
        "available_slots": "可能枠",
        "label": "判定",
        "holiday_name": "連休名",
    })
    csv_buf = io.StringIO()
    csv_df.to_csv(csv_buf, index=False)
    csv_bytes = csv_buf.getvalue().encode("utf-8-sig")

    with exp_col1:
        st.download_button(
            "📄 CSV ダウンロード",
            data=csv_bytes,
            file_name=f"booking_availability_{today.isoformat()}_{ward_label}.csv",
            mime="text/csv",
            key=f"booking_csv_{ward_label}",
            help="日付ごとの予想入院・空床・可能枠・判定を CSV で出力します",
        )

    with exp_col2:
        st.caption(
            "🖨 印刷は、ブラウザの印刷機能（Ctrl/Cmd + P）でカレンダー部分を印刷してください。"
        )

    # ------------------------------------------------------------------
    # B-5. 使い方ガイド
    # ------------------------------------------------------------------
    with st.expander("💡 予約可能枠カレンダーの使い方"):
        st.markdown(
            "**【予約受付事務員向け】**\n"
            "1. 新規予約依頼を受けたら、このカレンダーで希望日を確認\n"
            "2. 🟢 通常 → そのまま予約確定\n"
            "3. 🟡 やや混雑 → 代替日を提案（近隣の 🟢 の日）\n"
            "4. 🔴 満員 → 必ず代替日を提案、または主治医と相談\n"
            "5. 🔵 連休 → 連休明け以降を提案\n\n"
            "**【病棟師長向け】**\n"
            "- 毎朝カレンダーを確認、連休前後に 🔴 が集中していないか確認\n"
            "- 🔴 の日が多い週は、退院調整を強化（タブ 2「退院候補リスト」と連携）"
        )

    # ------------------------------------------------------------------
    # E2E 用 testid
    # ------------------------------------------------------------------
    st.markdown(
        f'<div data-testid="booking-availability-summary" '
        f'data-ward="{ward_label}" '
        f'data-green="{summary["通常"]}" '
        f'data-yellow="{summary["やや混雑"]}" '
        f'data-red="{summary["満員"]}" '
        f'data-blue="{summary["連休"]}" '
        f'data-total-days="{len(daily_forecast)}" '
        f'style="display:none">calendar</div>',
        unsafe_allow_html=True,
    )
