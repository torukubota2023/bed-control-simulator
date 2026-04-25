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
