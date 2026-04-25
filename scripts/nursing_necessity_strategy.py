"""2026年度改定 看護必要度ギャップ管理ロジック.

目的:
    2026年度改定で導入された「割合指数」
    (該当患者割合 + 救急患者応需係数) を、当院の病棟別戦略に落とし込む。

設計:
    - Streamlit 非依存の pure function
    - 過去入院 CSV の救急搬送件数から救急患者応需係数を推計
    - A/C項目の実データは未連携のため、現在の該当患者割合は手入力値を使う

注意:
    ここで出す介入効果は「医学的に必要な処置・ケアの記録漏れを減らす」
    ための運用試算であり、不必要な処置を増やす提案ではない。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional

import pandas as pd


# ---------------------------------------------------------------------------
# 制度・病院前提
# ---------------------------------------------------------------------------

# 厚労省 令和8年度改定資料:
#   基準該当患者割合に係る指数 = 該当患者割合 + 救急患者応需係数
#   地域包括医療病棟入院料1: 必要度I 19%, 必要度II 18%
TARGET_NURSING_NECESSITY_I_PCT = 19.0
TARGET_NURSING_NECESSITY_II_PCT = 18.0

# 救急患者応需係数: 年間救急搬送件数 ÷ 許可病床数 × 0.005
EMERGENCY_RESPONSE_COEFFICIENT = 0.005

DEFAULT_WARD_BEDS: Dict[str, int] = {
    "5F": 47,
    "6F": 47,
}

# 2026_nursing_necessity_unified_strategy.md の現状仮置き値。
# HIS/看護必要度データ連携後は UI から上書きする。
DEFAULT_BASE_NEED_PCT_BY_WARD: Dict[str, float] = {
    "5F": 16.0,
    "6F": 11.0,
}

DEFAULT_OCCUPANCY_TARGET = 0.90
MONTH_DAYS = 30

C_ITEM_DAYS: Dict[str, int] = {
    "C21": 4,  # CV, 腰椎穿刺, ERCP, 内視鏡止血など
    "C22": 2,  # 気管支鏡, TEE, EBUSなど
    "C23": 5,  # PEG, PTCD, CART, 消化管ステントなど
}

NECESSITY_TARGET_PCT: Dict[str, float] = {
    "I": TARGET_NURSING_NECESSITY_I_PCT,
    "II": TARGET_NURSING_NECESSITY_II_PCT,
}

DEFAULT_6F_STRATEGY_PACKAGE: Dict[str, int] = {
    "record_recovery_days": 8,
    "internal_medicine_a2_days": 14,
    "pain_a6_days": 6,
    "c_item_days": 12,
}

DEFAULT_6F_ACTION_MIX: Dict[str, int] = {
    "record_recovery_days": 11,
    "internal_cases": 8,
    "internal_days_per_case": 5,
    "pain_cases": 3,
    "pain_days_per_case": 3,
    "c21_cases": 4,
    "c22_cases": 2,
    "c23_cases": 4,
}

PATIENT_DAY_CONVERSION_RULES: List[Dict[str, Any]] = [
    {
        "action": "記録回収",
        "patient_days_per_case": 1,
        "example": "酸素・注射・処置の実施済み記録を同日確定する",
    },
    {
        "action": "ペイン科A6 3日維持",
        "patient_days_per_case": 3,
        "example": "適応が明確な疼痛管理を3日分正しく評価する",
    },
    {
        "action": "C21系 1件",
        "patient_days_per_case": C_ITEM_DAYS["C21"],
        "example": "CV、腰椎穿刺、ERCP、内視鏡止血など",
    },
    {
        "action": "C23系 1件",
        "patient_days_per_case": C_ITEM_DAYS["C23"],
        "example": "PEG、PTCD、CART、消化管ステントなど",
    },
    {
        "action": "内科A項目 5日維持",
        "patient_days_per_case": 5,
        "example": "酸素+注射3種、輸血、シリンジポンプ等を5日分評価する",
    },
]


# ---------------------------------------------------------------------------
# 内部ヘルパー
# ---------------------------------------------------------------------------

def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if pd.isna(out):
        return default
    return out


def _as_int(value: Any, default: int = 0) -> int:
    try:
        out = int(value)
    except (TypeError, ValueError):
        return default
    return max(out, 0)


def _emergency_mask(df: pd.DataFrame) -> pd.Series:
    """過去CSV/派生列のどちらからでも救急搬送フラグを作る."""
    if df is None or df.empty:
        return pd.Series(dtype=bool)
    if "is_emergency_transport" in df.columns:
        return df["is_emergency_transport"].fillna(False).astype(bool)
    if "救急車" in df.columns:
        return df["救急車"].astype(str).isin(["有り", "あり", "有", "1", "True", "true"])
    return pd.Series([False] * len(df), index=df.index)


def _ward_mask(df: pd.DataFrame, ward: str) -> pd.Series:
    if df is None or df.empty:
        return pd.Series(dtype=bool)
    if "病棟" in df.columns:
        return df["病棟"].astype(str) == ward
    if "ward" in df.columns:
        return df["ward"].astype(str) == ward
    return pd.Series([False] * len(df), index=df.index)


def _classify_gap(gap_pct: float) -> str:
    """不足ptから病棟の対応レベルを返す."""
    if gap_pct <= 0:
        return "達成圏"
    if gap_pct <= 2.0:
        return "あと少し"
    if gap_pct <= 5.0:
        return "重点介入"
    return "緊急介入"


def _monthly_denominator_days(
    beds: int,
    occupancy_target: float = DEFAULT_OCCUPANCY_TARGET,
    month_days: int = MONTH_DAYS,
) -> float:
    return max(beds, 0) * max(occupancy_target, 0.0) * max(month_days, 0)


# ---------------------------------------------------------------------------
# 公開関数
# ---------------------------------------------------------------------------

def calculate_emergency_response_coefficient(
    annual_emergency_count: int,
    beds: int,
    coefficient: float = EMERGENCY_RESPONSE_COEFFICIENT,
) -> float:
    """救急患者応需係数を percentage point として返す.

    例:
        年間220件 / 94床 * 0.005 = 0.0117 = 1.17 percentage point
    """
    beds_int = _as_int(beds)
    if beds_int <= 0:
        return 0.0
    emergency = _as_int(annual_emergency_count)
    return round((emergency / beds_int) * coefficient * 100, 2)


def summarize_nursing_necessity(
    df: pd.DataFrame,
    base_need_pct_by_ward: Optional[Mapping[str, float]] = None,
    beds_by_ward: Optional[Mapping[str, int]] = None,
    target_pct: float = TARGET_NURSING_NECESSITY_I_PCT,
    occupancy_target: float = DEFAULT_OCCUPANCY_TARGET,
    period_months: float = 12.0,
) -> List[Dict[str, Any]]:
    """病棟別に割合指数・不足pt・月あたり必要該当日数を返す.

    Args:
        df: 過去入院データ。``is_emergency_transport`` または ``救急車`` 列を使う。
        base_need_pct_by_ward: 現在の該当患者割合。実データ未連携のため手入力前提。
        beds_by_ward: 病棟別病床数。
        target_pct: 必要度Iなら19.0、必要度IIなら18.0。
        occupancy_target: 月間分母日数の試算に使う稼働率。
        period_months: df が何か月分か。12か月未満なら年換算する。
    """
    work_df = df if isinstance(df, pd.DataFrame) else pd.DataFrame()
    base_map = dict(DEFAULT_BASE_NEED_PCT_BY_WARD)
    if base_need_pct_by_ward:
        base_map.update({k: _as_float(v) for k, v in base_need_pct_by_ward.items()})

    beds_map = dict(DEFAULT_WARD_BEDS)
    if beds_by_ward:
        beds_map.update({k: _as_int(v) for k, v in beds_by_ward.items()})

    target = _as_float(target_pct, TARGET_NURSING_NECESSITY_I_PCT)
    annualize_factor = 12.0 / max(_as_float(period_months, 12.0), 0.1)
    emergency = _emergency_mask(work_df)

    rows: List[Dict[str, Any]] = []
    for ward in sorted(beds_map.keys()):
        beds = beds_map[ward]
        ward_rows = _ward_mask(work_df, ward)
        observed_emergency = int((ward_rows & emergency).sum()) if not work_df.empty else 0
        annual_emergency = int(round(observed_emergency * annualize_factor))
        coeff_pct = calculate_emergency_response_coefficient(annual_emergency, beds)
        base_pct = round(_as_float(base_map.get(ward, 0.0)), 2)
        index_pct = round(base_pct + coeff_pct, 2)
        gap_pct = round(max(0.0, target - index_pct), 2)
        denominator_days = _monthly_denominator_days(beds, occupancy_target)
        required_ac_days = round((gap_pct / 100) * denominator_days, 1)

        rows.append({
            "ward": ward,
            "beds": beds,
            "base_need_pct": base_pct,
            "annual_emergency_count": annual_emergency,
            "emergency_coeff_pct": coeff_pct,
            "index_pct": index_pct,
            "target_pct": target,
            "gap_pct": gap_pct,
            "required_ac_days_per_month": required_ac_days,
            "status": _classify_gap(gap_pct),
        })
    return rows


def estimate_intervention_gain_pct(
    c21_cases: int = 8,
    c22_cases: int = 5,
    c23_cases: int = 2,
    a6_days: int = 45,
    beds: int = 47,
    occupancy_target: float = DEFAULT_OCCUPANCY_TARGET,
    month_days: int = MONTH_DAYS,
) -> Dict[str, Any]:
    """A/C項目の月間介入パッケージが該当患者割合を何pt押し上げるか試算."""
    denom = _monthly_denominator_days(beds, occupancy_target, month_days)
    if denom <= 0:
        denom = 1.0

    c21_days = _as_int(c21_cases) * C_ITEM_DAYS["C21"]
    c22_days = _as_int(c22_cases) * C_ITEM_DAYS["C22"]
    c23_days = _as_int(c23_cases) * C_ITEM_DAYS["C23"]
    a6_days_int = _as_int(a6_days)
    total_days = c21_days + c22_days + c23_days + a6_days_int

    def gain(days: int) -> float:
        return round((days / denom) * 100, 2)

    return {
        "denominator_days": round(denom, 1),
        "c21_days": c21_days,
        "c21_gain_pct": gain(c21_days),
        "c22_days": c22_days,
        "c22_gain_pct": gain(c22_days),
        "c23_days": c23_days,
        "c23_gain_pct": gain(c23_days),
        "a6_days": a6_days_int,
        "a6_gain_pct": gain(a6_days_int),
        "total_days": total_days,
        "total_gain_pct": gain(total_days),
    }


def build_nursing_necessity_actions(summary_rows: List[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """病棟別サマリーから、会議に出せる改善アクション案を作る."""
    actions: List[Dict[str, Any]] = []
    for row in summary_rows:
        ward = str(row.get("ward", ""))
        gap = _as_float(row.get("gap_pct", 0.0))
        required_days = _as_float(row.get("required_ac_days_per_month", 0.0))
        status = str(row.get("status", _classify_gap(gap)))

        if gap <= 0:
            priority = "maintain"
            message = "基準達成圏。救急受入と算定漏れ監査を維持。"
            next_actions = [
                "週次でA/C項目の記録漏れを確認",
                "Day8以降の非該当長期化を増やさない",
            ]
        elif gap <= 2.0:
            priority = "watch"
            message = "あと少し。大きな方針転換より、算定漏れゼロで届く可能性。"
            next_actions = [
                "CV・腰椎穿刺・内視鏡処置などC21の取りこぼしを週次確認",
                "酸素 + 注射3種などA2点パターンの記録を毎日点検",
            ]
        elif gap <= 5.0:
            priority = "focus"
            message = "重点介入が必要。A項目とC項目の月間目標を置く段階。"
            next_actions = [
                "C21/C22/C23の月間件数目標を師長会議で共有",
                "Day3退院困難因子スクリーニングとDay8以降の退院支援をセット運用",
            ]
        else:
            priority = "urgent"
            message = "不足が大きい。6F型の集中パッケージで分子を増やす必要。"
            next_actions = [
                "A6単独3点、酸素 + 注射3種、輸血などの該当日を毎日監査",
                "C21/C22/C23の実施時に該当日数を即時確認",
                "救急搬送受入は稼働率と係数の両方に効くが、係数だけでは不足を埋めにくい",
            ]

        actions.append({
            "ward": ward,
            "status": status,
            "priority": priority,
            "gap_pct": round(gap, 2),
            "required_ac_days_per_month": round(required_days, 1),
            "message": message,
            "next_actions": next_actions,
        })
    return actions


# ---------------------------------------------------------------------------
# 6F 実データ戦略ボード
# ---------------------------------------------------------------------------

def summarize_actual_necessity_gaps(
    nursing_df: pd.DataFrame,
    ward: str = "6F",
    emergency_coefficient_pct: float = 0.0,
    recent_months: int = 3,
) -> List[Dict[str, Any]]:
    """看護必要度実績 CSV から、通年/直近の不足該当日数を計算する.

    ``nursing_necessity_loader`` の DataFrame を直接受け、必要度 I/II の
    実績割合、救急患者応需係数加算後の割合指数、月あたり必要該当日数を返す。
    """
    if nursing_df is None or nursing_df.empty:
        return []
    if "ward" not in nursing_df.columns:
        return []

    work = nursing_df[nursing_df["ward"].astype(str) == ward].copy()
    if work.empty:
        return []
    if "ym" not in work.columns and "date" in work.columns:
        work["date"] = pd.to_datetime(work["date"], errors="coerce")
        work["ym"] = work["date"].dt.to_period("M").astype(str)

    months = sorted(work["ym"].dropna().unique()) if "ym" in work.columns else []
    recent = months[-max(_as_int(recent_months, 3), 1):] if months else []

    scopes = [
        ("12ヶ月平均", work, max(len(months), 1), months),
    ]
    if recent:
        scopes.append((
            f"直近{len(recent)}ヶ月",
            work[work["ym"].isin(recent)],
            len(recent),
            recent,
        ))

    rows: List[Dict[str, Any]] = []
    for scope_label, scope_df, period_months, scope_months in scopes:
        for typ in ("I", "II"):
            total_col = f"{typ}_total"
            pass_col = f"{typ}_pass1"
            if total_col not in scope_df.columns or pass_col not in scope_df.columns:
                continue
            denominator_days = int(pd.to_numeric(scope_df[total_col], errors="coerce").fillna(0).sum())
            pass_days = int(pd.to_numeric(scope_df[pass_col], errors="coerce").fillna(0).sum())
            if denominator_days <= 0:
                continue
            rate_pct = pass_days / denominator_days * 100
            target_pct = NECESSITY_TARGET_PCT[typ]
            index_pct = rate_pct + emergency_coefficient_pct
            gap_pct = max(0.0, target_pct - index_pct)
            required_days_total = gap_pct / 100 * denominator_days
            required_days_per_month = required_days_total / max(period_months, 1)
            denominator_days_per_month = denominator_days / max(period_months, 1)

            rows.append({
                "ward": ward,
                "scope": scope_label,
                "months": list(scope_months),
                "period_months": period_months,
                "necessity_type": typ,
                "target_pct": round(target_pct, 2),
                "rate_pct": round(rate_pct, 2),
                "emergency_coeff_pct": round(emergency_coefficient_pct, 2),
                "index_pct": round(index_pct, 2),
                "gap_pct": round(gap_pct, 2),
                "denominator_days": denominator_days,
                "denominator_days_per_month": round(denominator_days_per_month, 1),
                "pass_days": pass_days,
                "required_days_total": round(required_days_total, 1),
                "required_days_per_month": round(required_days_per_month, 1),
                "status": _classify_gap(gap_pct),
            })
    return rows


def summarize_ward_case_mix(
    past_df: pd.DataFrame,
    ward: str = "6F",
    specialty_map: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    """過去入院 CSV から 6F の患者ミックスを要約する."""
    if past_df is None or past_df.empty:
        return {
            "ward": ward,
            "n": 0,
            "internal_pct": 0.0,
            "pain_pct": 0.0,
            "no_surgery_pct": 0.0,
            "scheduled_pct": 0.0,
            "ambulance_pct": 0.0,
            "median_los": 0.0,
            "specialty_rows": [],
        }

    work = past_df.copy()
    ward_col = "病棟" if "病棟" in work.columns else "ward"
    if ward_col not in work.columns:
        return summarize_ward_case_mix(pd.DataFrame(), ward, specialty_map)
    work = work[work[ward_col].astype(str) == ward].copy()
    if work.empty:
        return summarize_ward_case_mix(pd.DataFrame(), ward, specialty_map)

    doctor_col = "医師" if "医師" in work.columns else "attending_doctor"
    dept_col = "診療科" if "診療科" in work.columns else None
    los_col = "日数" if "日数" in work.columns else "los_days"
    surgery_col = "手術" if "手術" in work.columns else "has_surgery"
    emergency_col = "救急車" if "救急車" in work.columns else "is_emergency_transport"
    scheduled_col = "緊急" if "緊急" in work.columns else "is_scheduled"

    if specialty_map and doctor_col in work.columns:
        def _map_group(row: pd.Series) -> str:
            doctor = str(row.get(doctor_col, ""))
            mapped = specialty_map.get(doctor)
            if mapped:
                return mapped
            if dept_col:
                return str(row.get(dept_col, "未分類"))
            return "未分類"

        work["_group"] = work.apply(_map_group, axis=1)
    elif dept_col:
        work["_group"] = work[dept_col].astype(str)
    else:
        work["_group"] = "未分類"

    los = pd.to_numeric(work[los_col], errors="coerce") if los_col in work.columns else pd.Series(dtype=float)
    n = int(len(work))
    internal_count = int(work["_group"].isin(["内科", "循内科"]).sum())
    pain_count = int((work["_group"] == "ペイン科").sum())

    if surgery_col in work.columns:
        if work[surgery_col].dtype == bool:
            surgery_count = int(work[surgery_col].fillna(False).sum())
        else:
            surgery_count = int((work[surgery_col].astype(str) == "○").sum())
    else:
        surgery_count = 0

    if emergency_col in work.columns:
        if work[emergency_col].dtype == bool:
            ambulance_count = int(work[emergency_col].fillna(False).sum())
        else:
            ambulance_count = int(work[emergency_col].astype(str).isin(["有り", "あり", "有"]).sum())
    else:
        ambulance_count = 0

    if scheduled_col in work.columns:
        if work[scheduled_col].dtype == bool:
            scheduled_count = int(work[scheduled_col].fillna(False).sum())
        else:
            scheduled_count = int((work[scheduled_col].astype(str) == "予定入院").sum())
    else:
        scheduled_count = 0

    specialty_rows: List[Dict[str, Any]] = []
    for group, sub in work.groupby("_group"):
        sub_los = pd.to_numeric(sub[los_col], errors="coerce") if los_col in sub.columns else pd.Series(dtype=float)
        specialty_rows.append({
            "group": str(group),
            "n": int(len(sub)),
            "pct": round(len(sub) / n * 100, 1) if n else 0.0,
            "median_los": round(float(sub_los.median()), 1) if len(sub_los.dropna()) else 0.0,
        })
    specialty_rows.sort(key=lambda r: r["n"], reverse=True)

    return {
        "ward": ward,
        "n": n,
        "internal_pct": round(internal_count / n * 100, 1) if n else 0.0,
        "pain_pct": round(pain_count / n * 100, 1) if n else 0.0,
        "no_surgery_pct": round((n - surgery_count) / n * 100, 1) if n else 0.0,
        "scheduled_pct": round(scheduled_count / n * 100, 1) if n else 0.0,
        "ambulance_pct": round(ambulance_count / n * 100, 1) if n else 0.0,
        "median_los": round(float(los.median()), 1) if len(los.dropna()) else 0.0,
        "specialty_rows": specialty_rows,
    }


def simulate_strategy_package(
    base_rate_pct: float,
    emergency_coefficient_pct: float,
    target_pct: float,
    denominator_days_per_month: float,
    added_eligible_days_per_month: float,
) -> Dict[str, Any]:
    """追加該当日数が割合指数を何pt改善するかを試算する."""
    denominator = max(_as_float(denominator_days_per_month), 1.0)
    gain_pct = _as_float(added_eligible_days_per_month) / denominator * 100
    before_index = _as_float(base_rate_pct) + _as_float(emergency_coefficient_pct)
    after_index = before_index + gain_pct
    target = _as_float(target_pct)
    remaining_gap = max(0.0, target - after_index)
    surplus = after_index - target
    return {
        "gain_pct": round(gain_pct, 2),
        "before_index_pct": round(before_index, 2),
        "after_index_pct": round(after_index, 2),
        "remaining_gap_pct": round(remaining_gap, 2),
        "surplus_pct": round(surplus, 2),
        "meets_target": after_index >= target,
    }


def build_patient_day_conversion_rows(required_days_per_month: float) -> List[Dict[str, Any]]:
    """不足患者日を「何件/月が必要か」に換算する."""
    required = max(_as_float(required_days_per_month), 0.0)
    rows: List[Dict[str, Any]] = []
    for rule in PATIENT_DAY_CONVERSION_RULES:
        unit_days = max(_as_float(rule["patient_days_per_case"], 1.0), 1.0)
        monthly_cases = math.ceil(required / unit_days) if required > 0 else 0
        rows.append({
            "action": rule["action"],
            "patient_days_per_case": unit_days,
            "required_cases_per_month": monthly_cases,
            "required_cases_per_week": round(monthly_cases / 4.3, 1) if monthly_cases else 0.0,
            "example": rule["example"],
        })
    return rows


def calculate_6f_action_mix(
    record_recovery_days: int = DEFAULT_6F_ACTION_MIX["record_recovery_days"],
    internal_cases: int = DEFAULT_6F_ACTION_MIX["internal_cases"],
    internal_days_per_case: int = DEFAULT_6F_ACTION_MIX["internal_days_per_case"],
    pain_cases: int = DEFAULT_6F_ACTION_MIX["pain_cases"],
    pain_days_per_case: int = DEFAULT_6F_ACTION_MIX["pain_days_per_case"],
    c21_cases: int = DEFAULT_6F_ACTION_MIX["c21_cases"],
    c22_cases: int = DEFAULT_6F_ACTION_MIX["c22_cases"],
    c23_cases: int = DEFAULT_6F_ACTION_MIX["c23_cases"],
) -> Dict[str, Any]:
    """6F向け月間アクションミックスを患者日へ換算する."""
    rows = [
        {
            "action": "記録回収",
            "monthly_cases": _as_int(record_recovery_days),
            "days_per_case": 1,
            "patient_days": _as_int(record_recovery_days),
            "note": "実施済みの酸素・注射・処置を同日確定",
        },
        {
            "action": "内科A項目",
            "monthly_cases": _as_int(internal_cases),
            "days_per_case": _as_int(internal_days_per_case, 5),
            "patient_days": _as_int(internal_cases) * _as_int(internal_days_per_case, 5),
            "note": "酸素+注射3種、輸血、シリンジポンプなど",
        },
        {
            "action": "ペイン科A6",
            "monthly_cases": _as_int(pain_cases),
            "days_per_case": _as_int(pain_days_per_case, 3),
            "patient_days": _as_int(pain_cases) * _as_int(pain_days_per_case, 3),
            "note": "適応が明確な疼痛管理を正しく評価",
        },
        {
            "action": "C21系",
            "monthly_cases": _as_int(c21_cases),
            "days_per_case": C_ITEM_DAYS["C21"],
            "patient_days": _as_int(c21_cases) * C_ITEM_DAYS["C21"],
            "note": "CV、腰椎穿刺、ERCP、内視鏡止血など",
        },
        {
            "action": "C22系",
            "monthly_cases": _as_int(c22_cases),
            "days_per_case": C_ITEM_DAYS["C22"],
            "patient_days": _as_int(c22_cases) * C_ITEM_DAYS["C22"],
            "note": "気管支鏡、TEE、EBUSなど",
        },
        {
            "action": "C23系",
            "monthly_cases": _as_int(c23_cases),
            "days_per_case": C_ITEM_DAYS["C23"],
            "patient_days": _as_int(c23_cases) * C_ITEM_DAYS["C23"],
            "note": "PEG、PTCD、CART、消化管ステントなど",
        },
    ]
    total = sum(row["patient_days"] for row in rows)
    return {
        "rows": rows,
        "total_patient_days": total,
    }


def build_6f_strategy_cards(case_mix: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """6F の内科・ペイン科特性に合わせた行動カードを返す."""
    internal_pct = _as_float(case_mix.get("internal_pct", 0.0))
    pain_pct = _as_float(case_mix.get("pain_pct", 0.0))
    no_surgery_pct = _as_float(case_mix.get("no_surgery_pct", 0.0))

    return [
        {
            "lens": "医療倫理",
            "owner": "全職種",
            "signal": "点数目的の処置は不可",
            "action": "適応のある治療・ケアの記録漏れだけを回収する。迷う症例は医師・看護師・医事で同日確認。",
            "metric": "虚偽記載 0、適応外処置 0",
        },
        {
            "lens": "医学的エビデンス",
            "owner": "内科・ペイン科医師",
            "signal": f"6Fは内科系 {internal_pct:.1f}%、ペイン科 {pain_pct:.1f}%、手術なし {no_surgery_pct:.1f}%",
            "action": "内科は酸素+注射3種/A4+A3/輸血/ドレナージ/C項目を、ペイン科は適応が明確なA6処置のみを確認。",
            "metric": "A2以上 or C1以上の該当日数",
        },
        {
            "lens": "行動人間学",
            "owner": "医師・看護師ペア",
            "signal": "入院時と朝の判断が、その日の評価を決める",
            "action": "入院時30秒自問、朝ラウンド即答、木曜ハドルの3つに固定。チェックリストで記憶に頼らない。",
            "metric": "同日回答率、翌日持ち越し件数",
        },
        {
            "lens": "UI/視覚効果",
            "owner": "管理者",
            "signal": "不足ptより「月に何日足りないか」の方が行動に移りやすい",
            "action": "赤/黄/緑、進捗バー、残不足日数、職種別の今日の一手を同じ画面に表示する。",
            "metric": "残不足患者日/月",
        },
    ]
