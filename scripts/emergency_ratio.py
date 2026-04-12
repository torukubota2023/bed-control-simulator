"""
救急搬送後患者割合モジュール — 病棟別・月別の救急搬送後患者割合を計算する

地域包括医療病棟の施設基準において、救急搬送後の入院患者割合 15% 以上が
求められる。本モジュールは日次入退院データから割合を算出し、月末予測・
アラート生成までを pure function で提供する。

用語:
    - 救急: 救急車搬送による入院
    - 下り搬送: 救急患者連携搬送料が算定される連携搬送
    - 病棟帰属: 入院日（day 0）の病棟で判定

Streamlit に依存しない。すべての関数は dict / list を返す。
推計値はすべて proxy であり、実績とは乖離する可能性がある。
"""

from __future__ import annotations

import calendar
import math
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

EMERGENCY_THRESHOLD_PCT: float = 15.0


def _safe_nested(d: Optional[dict], *keys: str) -> Any:
    """ネストされた dict から安全に値を取得する。"""
    current = d
    for k in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(k)
    return current
EMERGENCY_MARGIN_PCT: float = 17.0  # green 閾値（2pt マージン）
EMERGENCY_ROUTES: list[str] = ["救急", "下り搬送"]
SHORT3_DEFAULT_LABEL: str = "該当なし"
SCENARIO_MULTIPLIERS: dict[str, float] = {
    "conservative": 0.7,
    "standard": 1.0,
    "optimistic": 1.3,
}

_ROUTE_KEY_MAP: dict[str, str] = {
    "救急": "ambulance",
    "下り搬送": "downstream",
    "外来紹介": "scheduled",
    "連携室": "liaison",
    "ウォークイン": "walkin",
}


# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------


def _resolve_year_month(
    year_month: Optional[str], target_date: Optional[date]
) -> str:
    """year_month と target_date から対象月を決定する。"""
    if year_month is not None:
        return year_month
    d = target_date if target_date is not None else date.today()
    return d.strftime("%Y-%m")


def _filter_admissions(
    detail_df: pd.DataFrame,
    ward: Optional[str] = None,
    year_month: Optional[str] = None,
) -> pd.DataFrame:
    """入院イベントを病棟・月でフィルタして返す。"""
    if detail_df.empty:
        return detail_df

    df = detail_df[detail_df["event_type"] == "admission"].copy()

    if ward is not None:
        df = df[df["ward"] == ward]

    if year_month is not None:
        df["_ym"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")
        df = df[df["_ym"] == year_month]
        df = df.drop(columns=["_ym"])

    return df


def _is_short3(val: Any) -> bool:
    """short3_type が実際の短手3に該当するかを判定する。"""
    if pd.isna(val):
        return False
    s = str(val).strip()
    if s == "" or s == SHORT3_DEFAULT_LABEL:
        return False
    return True


def _build_breakdown(adm_df: pd.DataFrame, exclude_short3: bool) -> Dict[str, int]:
    """経路別の内訳を構築する。"""
    breakdown: Dict[str, int] = {
        "ambulance": 0,
        "downstream": 0,
        "scheduled": 0,
        "liaison": 0,
        "walkin": 0,
        "other": 0,
    }
    if exclude_short3:
        breakdown["excluded_short3"] = 0

    if adm_df.empty:
        return breakdown

    for route_val in adm_df["route"]:
        key = _ROUTE_KEY_MAP.get(str(route_val), "other")
        breakdown[key] += 1

    return breakdown


def _status_from_ratio(ratio_pct: float) -> str:
    """割合からステータスを返す。"""
    if ratio_pct >= EMERGENCY_MARGIN_PCT:
        return "green"
    if ratio_pct >= EMERGENCY_THRESHOLD_PCT:
        return "yellow"
    return "red"


def _business_days_in_range(start: date, end: date) -> int:
    """start から end（含む）の平日数を返す。"""
    if start > end:
        return 0
    count = 0
    d = start
    while d <= end:
        if d.weekday() < 5:  # Mon-Fri
            count += 1
        d += timedelta(days=1)
    return count


# ---------------------------------------------------------------------------
# 1. calculate_emergency_ratio
# ---------------------------------------------------------------------------


def calculate_emergency_ratio(
    detail_df: pd.DataFrame,
    ward: Optional[str] = None,
    year_month: Optional[str] = None,
    exclude_short3: bool = False,
    target_date: Optional[date] = None,
) -> Dict[str, Any]:
    """指定病棟・月の救急搬送後患者割合を計算する。

    Args:
        detail_df: 入退院詳細データ
        ward: 病棟 ("5F"/"6F")。None なら全体
        year_month: 対象月 ("2026-04")。None なら target_date から導出
        exclude_short3: True なら短手3を分母から除外
        target_date: 基準日。None なら今日

    Returns:
        割合・内訳を含む dict
    """
    ym = _resolve_year_month(year_month, target_date)
    adm_df = _filter_admissions(detail_df, ward=ward, year_month=ym)

    # 短手3 除外
    excluded_count = 0
    if exclude_short3 and not adm_df.empty and "short3_type" in adm_df.columns:
        short3_mask = adm_df["short3_type"].apply(_is_short3)
        excluded_count = int(short3_mask.sum())
        adm_df = adm_df[~short3_mask]

    # 内訳
    breakdown = _build_breakdown(adm_df, exclude_short3)
    if exclude_short3:
        breakdown["excluded_short3"] = excluded_count

    denominator = len(adm_df)
    numerator = 0
    if not adm_df.empty and "route" in adm_df.columns:
        numerator = int(adm_df["route"].isin(EMERGENCY_ROUTES).sum())

    ratio_pct = (numerator / denominator * 100.0) if denominator > 0 else 0.0
    gap = ratio_pct - EMERGENCY_THRESHOLD_PCT

    return {
        "numerator": numerator,
        "denominator": denominator,
        "ratio_pct": round(ratio_pct, 2),
        "gap_to_target_pt": round(gap, 2),
        "status": _status_from_ratio(ratio_pct),
        "exclude_short3": exclude_short3,
        "ward": ward,
        "year_month": ym,
        "breakdown": breakdown,
    }


# ---------------------------------------------------------------------------
# 2. calculate_dual_ratio
# ---------------------------------------------------------------------------


def calculate_dual_ratio(
    detail_df: pd.DataFrame,
    ward: Optional[str] = None,
    year_month: Optional[str] = None,
    target_date: Optional[date] = None,
) -> Dict[str, Any]:
    """公式割合と運用割合（短手3除外）の両方を返す。"""
    ym = _resolve_year_month(year_month, target_date)
    return {
        "official": calculate_emergency_ratio(
            detail_df, ward=ward, year_month=ym, exclude_short3=False
        ),
        "operational": calculate_emergency_ratio(
            detail_df, ward=ward, year_month=ym, exclude_short3=True
        ),
    }


# ---------------------------------------------------------------------------
# 3. project_month_end
# ---------------------------------------------------------------------------


def project_month_end(
    detail_df: pd.DataFrame,
    ward: Optional[str] = None,
    year_month: Optional[str] = None,
    target_date: Optional[date] = None,
    exclude_short3: bool = False,
) -> Dict[str, Any]:
    """月末時点の救急搬送後患者割合を3シナリオで予測する。

    過去14日間の曜日別パターンをベースに、残日数分を外挿する。
    推計値は proxy であり、実績とは乖離する可能性がある。
    """
    ym = _resolve_year_month(year_month, target_date)
    td = target_date if target_date is not None else date.today()

    # 月の範囲
    year_int, month_int = int(ym[:4]), int(ym[5:7])
    _, last_day = calendar.monthrange(year_int, month_int)
    month_start = date(year_int, month_int, 1)
    month_end = date(year_int, month_int, last_day)

    # 現在までの入院
    adm_df = _filter_admissions(detail_df, ward=ward, year_month=ym)
    # 短手3除外
    if exclude_short3 and not adm_df.empty and "short3_type" in adm_df.columns:
        adm_df = adm_df[~adm_df["short3_type"].apply(_is_short3)]
    current_total = len(adm_df)
    current_emergency = 0
    if not adm_df.empty and "route" in adm_df.columns:
        current_emergency = int(adm_df["route"].isin(EMERGENCY_ROUTES).sum())

    elapsed_days = max((min(td, month_end) - month_start).days + 1, 0)

    # 残日数
    next_day = td + timedelta(days=1)
    remaining_calendar_days = max((month_end - td).days, 0)
    remaining_business_days = _business_days_in_range(next_day, month_end) if next_day <= month_end else 0

    # 過去14日間のデータで曜日別パターンを算出
    lookback_start = td - timedelta(days=13)
    all_adm = _filter_admissions(detail_df, ward=ward)
    if exclude_short3 and not all_adm.empty and "short3_type" in all_adm.columns:
        all_adm = all_adm[~all_adm["short3_type"].apply(_is_short3)]

    if not all_adm.empty:
        all_adm = all_adm.copy()
        all_adm["_date"] = pd.to_datetime(all_adm["date"]).dt.date
        recent = all_adm[
            (all_adm["_date"] >= lookback_start) & (all_adm["_date"] <= td)
        ]
    else:
        recent = pd.DataFrame()

    # 日別集計
    dow_emergency: Dict[int, list] = {i: [] for i in range(7)}
    dow_total: Dict[int, list] = {i: [] for i in range(7)}

    if not recent.empty:
        recent_dates = recent["_date"].unique()
        for d in pd.date_range(lookback_start, td):
            dd = d.date()
            dow = dd.weekday()
            day_data = recent[recent["_date"] == dd]
            day_total = len(day_data)
            day_emg = 0
            if not day_data.empty and "route" in day_data.columns:
                day_emg = int(day_data["route"].isin(EMERGENCY_ROUTES).sum())
            dow_total[dow].append(day_total)
            dow_emergency[dow].append(day_emg)

    # 曜日別平均
    dow_pattern: Dict[int, float] = {}
    dow_total_pattern: Dict[int, float] = {}
    for dow in range(7):
        vals_e = dow_emergency[dow]
        vals_t = dow_total[dow]
        dow_pattern[dow] = sum(vals_e) / len(vals_e) if vals_e else 0.0
        dow_total_pattern[dow] = sum(vals_t) / len(vals_t) if vals_t else 0.0

    # 14日平均
    lookback_days = min(14, (td - lookback_start).days + 1)
    if not recent.empty:
        total_days_with_data = len(pd.date_range(lookback_start, td))
        daily_emergency_rate_14d = (
            recent["route"].isin(EMERGENCY_ROUTES).sum() / total_days_with_data
            if "route" in recent.columns
            else 0.0
        )
        daily_total_rate_14d = len(recent) / total_days_with_data
    else:
        daily_emergency_rate_14d = 0.0
        daily_total_rate_14d = 0.0

    # シナリオ別予測
    scenarios: Dict[str, Dict[str, Any]] = {}
    for scenario_name, multiplier in SCENARIO_MULTIPLIERS.items():
        proj_emg = float(current_emergency)
        proj_tot = float(current_total)

        d = next_day
        while d <= month_end:
            dow = d.weekday()
            proj_emg += dow_pattern.get(dow, 0.0) * multiplier
            proj_tot += dow_total_pattern.get(dow, 0.0) * multiplier
            d += timedelta(days=1)

        proj_emg_int = round(proj_emg)
        proj_tot_int = round(proj_tot)
        proj_ratio = (proj_emg_int / proj_tot_int * 100.0) if proj_tot_int > 0 else 0.0

        scenarios[scenario_name] = {
            "projected_emergency": proj_emg_int,
            "projected_total": proj_tot_int,
            "projected_ratio_pct": round(proj_ratio, 2),
            "meets_target": proj_ratio >= EMERGENCY_THRESHOLD_PCT,
            "multiplier": multiplier,
        }

    current_ratio = (current_emergency / current_total * 100.0) if current_total > 0 else 0.0

    return {
        "current": {
            "emergency_count": current_emergency,
            "total_count": current_total,
            "ratio_pct": round(current_ratio, 2),
            "elapsed_days": elapsed_days,
        },
        "conservative": scenarios["conservative"],
        "standard": scenarios["standard"],
        "optimistic": scenarios["optimistic"],
        "remaining_calendar_days": remaining_calendar_days,
        "remaining_business_days": remaining_business_days,
        "daily_emergency_rate_14d": round(float(daily_emergency_rate_14d), 2),
        "daily_total_rate_14d": round(float(daily_total_rate_14d), 2),
        "dow_pattern": {k: round(v, 2) for k, v in dow_pattern.items()},
        "ward": ward,
        "year_month": ym,
        "exclude_short3": exclude_short3,
    }


# ---------------------------------------------------------------------------
# 4. calculate_additional_needed
# ---------------------------------------------------------------------------


def calculate_additional_needed(
    detail_df: pd.DataFrame,
    ward: Optional[str] = None,
    year_month: Optional[str] = None,
    target_date: Optional[date] = None,
    exclude_short3: bool = False,
) -> Dict[str, Any]:
    """15% 達成に必要な追加救急入院数を算出する。"""
    ym = _resolve_year_month(year_month, target_date)
    td = target_date if target_date is not None else date.today()

    ratio_result = calculate_emergency_ratio(
        detail_df, ward=ward, year_month=ym,
        exclude_short3=exclude_short3, target_date=td,
    )
    projection = project_month_end(
        detail_df, ward=ward, year_month=ym, target_date=td,
        exclude_short3=exclude_short3,
    )

    current_emergency = ratio_result["numerator"]
    projected_total = projection["standard"]["projected_total"]
    projected_emergency_standard = projection["standard"]["projected_emergency"]
    target_emg = math.ceil(EMERGENCY_THRESHOLD_PCT / 100.0 * projected_total)

    # PRIMARY: 標準シナリオの予測救急数を差し引いた追加必要数
    needed = max(target_emg - projected_emergency_standard, 0)
    # REFERENCE: 現在の実績のみから算出した追加必要数（自然流入を見込まない）
    needed_from_actual = max(target_emg - current_emergency, 0)

    remaining_cal = projection["remaining_calendar_days"]
    remaining_biz = projection["remaining_business_days"]

    per_cal = needed / remaining_cal if remaining_cal > 0 else float("inf") if needed > 0 else 0.0
    per_biz = needed / remaining_biz if remaining_biz > 0 else float("inf") if needed > 0 else 0.0

    # 今週残りの必要数（今日から日曜まで）
    days_until_sunday = 6 - td.weekday()  # 0=Mon, 6=Sun
    if days_until_sunday < 0:
        days_until_sunday = 0
    if remaining_cal > 0 and days_until_sunday > 0:
        this_week_needed = math.ceil(needed * min(days_until_sunday, remaining_cal) / remaining_cal)
    else:
        this_week_needed = 0

    # 難易度判定（PRIMARY値ベース）
    if needed <= 0:
        difficulty = "achieved"
    elif per_biz < 0.5:
        difficulty = "easy"
    elif per_biz < 1.0:
        difficulty = "moderate"
    elif per_biz < 1.5:
        difficulty = "difficult"
    else:
        difficulty = "very_difficult"

    achievable = per_biz <= 2.0 if needed > 0 else True

    return {
        "additional_needed": needed,
        "additional_needed_from_actual": needed_from_actual,
        "current_emergency": current_emergency,
        "projected_emergency_standard": projected_emergency_standard,
        "projected_total_at_month_end": projected_total,
        "target_emergency_at_month_end": target_emg,
        "per_remaining_calendar_day": round(per_cal, 2),
        "per_remaining_business_day": round(per_biz, 2),
        "this_week_needed": this_week_needed,
        "difficulty": difficulty,
        "achievable": achievable,
        "ward": ward,
        "year_month": ym,
    }


# ---------------------------------------------------------------------------
# 5. generate_emergency_alerts
# ---------------------------------------------------------------------------


def generate_emergency_alerts(
    ratio_5f: Dict[str, Any],
    ratio_6f: Dict[str, Any],
    projection_5f: Dict[str, Any],
    projection_6f: Dict[str, Any],
    additional_5f: Dict[str, Any],
    additional_6f: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """病棟ごとのアラートメッセージを生成する。"""
    alerts: List[Dict[str, Any]] = []

    ward_data = [
        ("5F", ratio_5f, projection_5f, additional_5f),
        ("6F", ratio_6f, projection_6f, additional_6f),
    ]

    critical_count = 0

    for ward_name, ratio, proj, additional in ward_data:
        current_pct = ratio["ratio_pct"]
        std_meets = proj["standard"]["meets_target"]

        if current_pct < EMERGENCY_THRESHOLD_PCT and not std_meets:
            # critical
            critical_count += 1
            needed = additional["additional_needed"]
            per_biz = additional["per_remaining_business_day"]
            actions = [
                f"残り平日あたり {per_biz:.1f} 件の救急入院が必要",
                "救急隊への受入可能連絡の強化",
                "連携病院への下り搬送受入の働きかけ",
            ]
            if additional["difficulty"] == "very_difficult":
                actions.append("月内達成は困難 — 来月の挽回計画を検討")

            alerts.append({
                "level": "critical",
                "ward": ward_name,
                "title": f"{ward_name} 救急搬送後患者割合 — 未達見込み",
                "message": (
                    f"現在 {current_pct:.1f}%（目標15%）。"
                    f"このままでは今月の救急搬送後患者割合15%を満たさない見込みです。"
                    f"あと {needed} 件の救急入院が必要です。"
                ),
                "actions": actions,
            })

        elif current_pct < EMERGENCY_THRESHOLD_PCT and std_meets:
            # warning — 現時点では未達だが、標準シナリオでは達成見込み
            alerts.append({
                "level": "warning",
                "ward": ward_name,
                "title": f"{ward_name} 救急搬送後患者割合 — 現時点で未達",
                "message": (
                    f"現在 {current_pct:.1f}%（目標15%）。"
                    f"現時点では目標未達ですが、標準シナリオでは月末に"
                    f" {proj['standard']['projected_ratio_pct']:.1f}% となり達成見込みです。"
                ),
                "actions": ["このペースを維持してください"],
            })

        elif current_pct < EMERGENCY_MARGIN_PCT:
            # caution — 達成しているが余裕が少ない
            alerts.append({
                "level": "caution",
                "ward": ward_name,
                "title": f"{ward_name} 救急搬送後患者割合 — 余裕薄",
                "message": (
                    f"現在 {current_pct:.1f}%（目標15%）。"
                    f"目標は超えていますが、マージンが {current_pct - EMERGENCY_THRESHOLD_PCT:.1f}pt と薄いため注意が必要です。"
                ),
                "actions": ["救急受入ペースの維持を意識してください"],
            })

        else:
            # safe
            alerts.append({
                "level": "safe",
                "ward": ward_name,
                "title": f"{ward_name} 救急搬送後患者割合 — 順調",
                "message": f"現在 {current_pct:.1f}%。十分なマージンがあります。",
                "actions": [],
            })

    # 両病棟 critical の場合、全体アラートを追加
    if critical_count == 2:
        alerts.append({
            "level": "critical",
            "ward": "全体",
            "title": "全病棟で救急搬送後患者割合 — 未達見込み",
            "message": (
                "5F・6F ともに今月の救急搬送後患者割合15%を満たさない見込みです。"
                "病院全体として緊急対策が必要です。"
            ),
            "actions": [
                "救急受入体制の全体見直し",
                "連携病院との下り搬送拡大の検討",
                "経営会議での報告・対策協議",
            ],
        })

    return alerts


# ---------------------------------------------------------------------------
# 6. get_ward_emergency_summary
# ---------------------------------------------------------------------------


def get_ward_emergency_summary(
    detail_df: pd.DataFrame,
    target_date: Optional[date] = None,
) -> Dict[str, Any]:
    """両病棟の救急搬送後患者割合サマリーを一括取得する。"""
    td = target_date if target_date is not None else date.today()
    ym = td.strftime("%Y-%m")

    result: Dict[str, Any] = {}

    for w in ("5F", "6F"):
        result[w] = {
            "dual_ratio": calculate_dual_ratio(detail_df, ward=w, year_month=ym, target_date=td),
            "projection": project_month_end(detail_df, ward=w, year_month=ym, target_date=td),
            "additional": calculate_additional_needed(detail_df, ward=w, year_month=ym, target_date=td),
        }

    alerts = generate_emergency_alerts(
        ratio_5f=result["5F"]["dual_ratio"]["official"],
        ratio_6f=result["6F"]["dual_ratio"]["official"],
        projection_5f=result["5F"]["projection"],
        projection_6f=result["6F"]["projection"],
        additional_5f=result["5F"]["additional"],
        additional_6f=result["6F"]["additional"],
    )

    result["alerts"] = alerts
    result["target_date"] = td
    result["year_month"] = ym

    # overall_status: 両病棟の最悪値を採用
    statuses = []
    for w in ("5F", "6F"):
        s = _safe_nested(result, w, "dual_ratio", "official", "status")
        if s:
            statuses.append(s)
    if not statuses:
        result["overall_status"] = "incomplete"
    elif "red" in statuses:
        result["overall_status"] = "danger"
    elif "yellow" in statuses:
        result["overall_status"] = "warning"
    else:
        result["overall_status"] = "safe"

    return result


# ---------------------------------------------------------------------------
# 7. get_monthly_history
# ---------------------------------------------------------------------------


def get_monthly_history(
    detail_df: pd.DataFrame,
    ward: Optional[str] = None,
    n_months: int = 12,
    target_date: Optional[date] = None,
    exclude_short3: bool = False,
) -> List[Dict[str, Any]]:
    """過去 N ヶ月分の月別救急搬送後患者割合を返す（チャート用）。"""
    td = target_date if target_date is not None else date.today()
    results: List[Dict[str, Any]] = []

    for i in range(n_months - 1, -1, -1):
        # i ヶ月前
        y = td.year
        m = td.month - i
        while m <= 0:
            m += 12
            y -= 1
        ym = f"{y:04d}-{m:02d}"

        r = calculate_emergency_ratio(
            detail_df, ward=ward, year_month=ym, exclude_short3=exclude_short3,
        )
        results.append({
            "year_month": ym,
            "ratio_pct": r["ratio_pct"],
            "numerator": r["numerator"],
            "denominator": r["denominator"],
            "status": r["status"],
        })

    return results


# ---------------------------------------------------------------------------
# 8. get_cumulative_progress
# ---------------------------------------------------------------------------


def get_cumulative_progress(
    detail_df: pd.DataFrame,
    ward: Optional[str] = None,
    year_month: Optional[str] = None,
    target_date: Optional[date] = None,
    exclude_short3: bool = False,
) -> List[Dict[str, Any]]:
    """当月の日別累積救急搬送後患者割合を返す（進捗チャート用）。"""
    ym = _resolve_year_month(year_month, target_date)
    td = target_date if target_date is not None else date.today()

    year_int, month_int = int(ym[:4]), int(ym[5:7])
    _, last_day = calendar.monthrange(year_int, month_int)
    month_start = date(year_int, month_int, 1)
    end_date = min(date(year_int, month_int, last_day), td)

    # 当月入院データ取得
    adm_df = _filter_admissions(detail_df, ward=ward, year_month=ym)

    if exclude_short3 and not adm_df.empty and "short3_type" in adm_df.columns:
        short3_mask = adm_df["short3_type"].apply(_is_short3)
        adm_df = adm_df[~short3_mask]

    if adm_df.empty:
        return []

    adm_df = adm_df.copy()
    adm_df["_date"] = pd.to_datetime(adm_df["date"]).dt.date

    results: List[Dict[str, Any]] = []
    cum_emergency = 0
    cum_total = 0

    d = month_start
    while d <= end_date:
        day_data = adm_df[adm_df["_date"] == d]
        day_total = len(day_data)
        day_emg = 0
        if not day_data.empty and "route" in day_data.columns:
            day_emg = int(day_data["route"].isin(EMERGENCY_ROUTES).sum())

        cum_emergency += day_emg
        cum_total += day_total

        cum_ratio = (cum_emergency / cum_total * 100.0) if cum_total > 0 else 0.0

        results.append({
            "date": d.isoformat(),
            "cumulative_emergency": cum_emergency,
            "cumulative_total": cum_total,
            "cumulative_ratio_pct": round(cum_ratio, 2),
        })

        d += timedelta(days=1)

    return results


# ---------------------------------------------------------------------------
# 9. estimate_next_morning_capacity
# ---------------------------------------------------------------------------


def _next_business_date(d: date) -> date:
    """次の診療日（土日をスキップ）を返す。祝日は未対応。"""
    nxt = d + timedelta(days=1)
    while nxt.weekday() >= 5:  # 5=Sat, 6=Sun
        nxt += timedelta(days=1)
    return nxt


def estimate_next_morning_capacity(
    daily_df: pd.DataFrame,
    detail_df: Optional[pd.DataFrame] = None,
    ward: Optional[str] = None,
    target_date: Optional[date] = None,
    total_beds: int = 94,
    ward_beds: Optional[int] = None,
) -> Dict[str, Any]:
    """翌診療日朝の救急受入余力をproxy推計する。

    直近のデータから、翌診療日朝の時点で何床空いているかを推計する。
    推計値はproxyであり、実際の空床数とは異なる可能性がある。

    Args:
        daily_df: 日次データ
        detail_df: 入退院詳細データ（退院予定の確認用、Noneなら平均で推計）
        ward: "5F" / "6F" / None
        target_date: 基準日。None なら今日
        total_beds: 病院全体の病床数
        ward_beds: 病棟の病床数（ward指定時のみ使用）

    Returns:
        翌朝の受入余力を含む dict
    """
    td = target_date if target_date is not None else date.today()
    beds = ward_beds if (ward is not None and ward_beds is not None) else total_beds
    next_biz = _next_business_date(td)

    # デフォルト結果（データ不足時）
    default_result: Dict[str, Any] = {
        "current_empty_beds": 0,
        "current_occupancy_pct": 0.0,
        "planned_discharges_tomorrow": 0.0,
        "expected_admissions_tomorrow": 0.0,
        "estimated_emergency_slots": 0,
        "three_day_min_slots": 0,
        "ward": ward,
        "target_date": td.isoformat(),
        "is_proxy": True,
        "next_business_date": next_biz.isoformat(),
    }

    if daily_df is None or not isinstance(daily_df, pd.DataFrame) or len(daily_df) == 0:
        return default_result

    df = daily_df.copy()
    df["date"] = pd.to_datetime(df["date"])

    # 病棟フィルタ
    if ward is not None and "ward" in df.columns:
        df = df[df["ward"] == ward]

    # 日付単位で合算
    numeric_cols = [c for c in ["total_patients", "new_admissions", "discharges"]
                    if c in df.columns]
    if not numeric_cols or "total_patients" not in df.columns:
        return default_result

    agg_dict = {c: "sum" for c in numeric_cols}
    df = df.groupby("date", as_index=False).agg(agg_dict)
    df = df.sort_values("date").reset_index(drop=True)

    if df.empty:
        return default_result

    # 最新日のデータ
    latest = df.iloc[-1]
    current_patients = int(latest["total_patients"])
    current_empty = max(beds - current_patients, 0)
    current_occupancy = (current_patients / beds * 100.0) if beds > 0 else 0.0

    # --- 退院推計 ---
    planned_discharges: float = 0.0

    # detail_dfから翌診療日の退院予定を取得
    if detail_df is not None and isinstance(detail_df, pd.DataFrame) and len(detail_df) > 0:
        det = detail_df.copy()
        if "event_type" in det.columns:
            dis_df = det[det["event_type"] == "discharge"]
            if ward is not None and "ward" in dis_df.columns:
                dis_df = dis_df[dis_df["ward"] == ward]
            if not dis_df.empty:
                dis_df = dis_df.copy()
                dis_df["_date"] = pd.to_datetime(dis_df["date"]).dt.date
                planned_tomorrow = dis_df[dis_df["_date"] == next_biz]
                if len(planned_tomorrow) > 0:
                    planned_discharges = float(len(planned_tomorrow))

    # detail_dfに翌日データがない場合、過去7日の平均退院数を使用
    if planned_discharges == 0.0 and "discharges" in df.columns:
        last_7d = df.tail(7)
        if len(last_7d) > 0:
            planned_discharges = round(float(last_7d["discharges"].mean()), 1)

    # --- 入院推計（同じ曜日の過去4週間平均） ---
    target_dow = next_biz.weekday()
    expected_admissions: float = 0.0

    if "new_admissions" in df.columns:
        df["_dow"] = df["date"].dt.dayofweek
        same_dow = df[df["_dow"] == target_dow].tail(4)
        if len(same_dow) > 0:
            expected_admissions = round(float(same_dow["new_admissions"].mean()), 1)

    # --- 翌朝の受入可能枠 ---
    net_capacity = current_empty + planned_discharges - expected_admissions
    emergency_slots = max(int(round(net_capacity)), 0)

    # --- 3診療日の最小受入余力 ---
    min_slots = emergency_slots
    cumulative_empty = float(current_empty)

    biz_day = next_biz
    for i in range(3):
        dow_i = biz_day.weekday()
        # 同曜日の退院・入院推計
        if "_dow" not in df.columns:
            df["_dow"] = df["date"].dt.dayofweek
        same_dow_i = df[df["_dow"] == dow_i].tail(4)

        dis_est = float(same_dow_i["discharges"].mean()) if (
            len(same_dow_i) > 0 and "discharges" in same_dow_i.columns
        ) else planned_discharges
        adm_est = float(same_dow_i["new_admissions"].mean()) if (
            len(same_dow_i) > 0 and "new_admissions" in same_dow_i.columns
        ) else expected_admissions

        cumulative_empty = cumulative_empty + dis_est - adm_est
        day_slots = max(int(round(cumulative_empty)), 0)
        if day_slots < min_slots:
            min_slots = day_slots

        biz_day = _next_business_date(biz_day)

    return {
        "current_empty_beds": current_empty,
        "current_occupancy_pct": round(current_occupancy, 1),
        "planned_discharges_tomorrow": planned_discharges,
        "expected_admissions_tomorrow": expected_admissions,
        "estimated_emergency_slots": emergency_slots,
        "three_day_min_slots": min_slots,
        "ward": ward,
        "target_date": td.isoformat(),
        "is_proxy": True,
        "next_business_date": next_biz.isoformat(),
    }
