"""
地域包括医療病棟入院料 診療報酬シミュレーター 計算エンジン

reimbursement_config.py の定数・型を用いて、収益計算・施設基準チェック・
感度分析を行う純粋な計算モジュール。Streamlit 依存なし。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from reimbursement_config import (
    DEPARTMENT_DEFAULTS,
    FACILITY_CONSTRAINTS,
    POINT_OVER_90_DAYS,
    POINT_TABLE,
    YEN_PER_POINT,
    AdditionalFee,
    AdmissionTier,
    CaseMixCell,
    ConstraintSeverity,
    Department,
    FacilityConstraint,
    WardType,
)


# ===========================================================================
# Point calculation
# ===========================================================================


def get_base_points(ward_type: WardType, tier: AdmissionTier) -> int:
    """Look up the 6-cell point table.

    Args:
        ward_type: 病棟入院料の届出区分 (TYPE_1 or TYPE_2).
        tier: 入院料区分 (TIER_1 / TIER_2 / TIER_3).

    Returns:
        1日あたりの基本点数.

    Raises:
        KeyError: テーブルに該当する組み合わせがない場合.
    """
    return POINT_TABLE[(ward_type, tier)]


def get_daily_points(
    ward_type: WardType,
    tier: AdmissionTier,
    day_of_stay: int,
    enabled_fees: list[AdditionalFee],
) -> int:
    """Base points + applicable fees for a given day.

    90日超の場合は POINT_OVER_90_DAYS を基本点数として使用する。
    加算は day_start <= day <= day_end（day_end が None なら無制限）の場合に適用。

    Args:
        ward_type: 病棟入院料の届出区分.
        tier: 入院料区分.
        day_of_stay: 入院日数（1-indexed）.
        enabled_fees: 有効な加算リスト.

    Returns:
        当該日の合計点数（基本点数 + 加算点数）.
    """
    if day_of_stay > 90:
        base = POINT_OVER_90_DAYS
    else:
        base = get_base_points(ward_type, tier)

    fee_total = 0
    for fee in enabled_fees:
        if fee.day_start <= day_of_stay:
            if fee.day_end is None or day_of_stay <= fee.day_end:
                fee_total += fee.points

    return base + fee_total


def calc_stay_total_points(
    ward_type: WardType,
    tier: AdmissionTier,
    los: int,
    enabled_fees: list[AdditionalFee],
) -> int:
    """Sum daily points over the entire stay (day 1 .. day los).

    Args:
        ward_type: 病棟入院料の届出区分.
        tier: 入院料区分.
        los: 在院日数.
        enabled_fees: 有効な加算リスト.

    Returns:
        入院全期間の合計点数.
    """
    return sum(
        get_daily_points(ward_type, tier, day, enabled_fees)
        for day in range(1, los + 1)
    )


def calc_stay_total_yen(
    ward_type: WardType,
    tier: AdmissionTier,
    los: int,
    enabled_fees: list[AdditionalFee],
) -> int:
    """Total yen for one stay = total_points * YEN_PER_POINT.

    Args:
        ward_type: 病棟入院料の届出区分.
        tier: 入院料区分.
        los: 在院日数.
        enabled_fees: 有効な加算リスト.

    Returns:
        入院1件あたりの総収入（円）.
    """
    return calc_stay_total_points(ward_type, tier, los, enabled_fees) * YEN_PER_POINT


# ===========================================================================
# Case-level calculation
# ===========================================================================


def calc_case_revenue(
    case: CaseMixCell,
    ward_type: WardType,
    enabled_fees: list[AdditionalFee],
) -> dict:
    """For one CaseMixCell, calculate revenue breakdown.

    Args:
        case: ケースミックスの1セル.
        ward_type: 病棟入院料の届出区分.
        enabled_fees: 有効な加算リスト.

    Returns:
        dict with keys: tier, base_points_per_day, avg_daily_points,
        total_points_per_stay, total_yen_per_stay, monthly_revenue,
        annual_revenue.
    """
    tier = case.admission_tier
    los = max(1, round(case.avg_los))
    base_points = get_base_points(ward_type, tier)
    total_points = calc_stay_total_points(ward_type, tier, los, enabled_fees)
    avg_daily = total_points / los if los > 0 else 0.0
    total_yen = total_points * YEN_PER_POINT
    monthly_rev = total_yen * case.monthly_count
    annual_rev = monthly_rev * 12

    return {
        "tier": tier,
        "base_points_per_day": base_points,
        "avg_daily_points": avg_daily,
        "total_points_per_stay": total_points,
        "total_yen_per_stay": total_yen,
        "monthly_revenue": monthly_rev,
        "annual_revenue": annual_rev,
    }


# ===========================================================================
# Ward / Hospital aggregation
# ===========================================================================


def calc_ward_summary(
    cases: list[CaseMixCell],
    ward_type: WardType,
    enabled_fees: list[AdditionalFee],
) -> dict:
    """Aggregate revenue across all cases for one ward.

    Args:
        cases: 当該病棟のケースミックスセルリスト.
        ward_type: 病棟入院料の届出区分.
        enabled_fees: 有効な加算リスト.

    Returns:
        dict with keys: total_monthly_cases, weighted_avg_los,
        weighted_avg_daily_points, total_monthly_revenue,
        total_annual_revenue, tier_distribution, tier_revenue_breakdown.
    """
    total_monthly_cases = 0
    weighted_los_sum = 0.0
    weighted_daily_points_sum = 0.0
    total_monthly_revenue = 0
    tier_distribution: dict[AdmissionTier, int] = {
        AdmissionTier.TIER_1: 0,
        AdmissionTier.TIER_2: 0,
        AdmissionTier.TIER_3: 0,
    }
    tier_revenue_breakdown: dict[AdmissionTier, int] = {
        AdmissionTier.TIER_1: 0,
        AdmissionTier.TIER_2: 0,
        AdmissionTier.TIER_3: 0,
    }

    for case in cases:
        if case.monthly_count == 0:
            continue
        rev = calc_case_revenue(case, ward_type, enabled_fees)
        count = case.monthly_count
        total_monthly_cases += count
        weighted_los_sum += case.avg_los * count
        weighted_daily_points_sum += rev["avg_daily_points"] * count
        total_monthly_revenue += rev["monthly_revenue"]
        tier_distribution[rev["tier"]] += count
        tier_revenue_breakdown[rev["tier"]] += rev["monthly_revenue"]

    weighted_avg_los = (
        weighted_los_sum / total_monthly_cases if total_monthly_cases > 0 else 0.0
    )
    weighted_avg_daily_points = (
        weighted_daily_points_sum / total_monthly_cases
        if total_monthly_cases > 0
        else 0.0
    )

    return {
        "total_monthly_cases": total_monthly_cases,
        "weighted_avg_los": weighted_avg_los,
        "weighted_avg_daily_points": weighted_avg_daily_points,
        "total_monthly_revenue": total_monthly_revenue,
        "total_annual_revenue": total_monthly_revenue * 12,
        "tier_distribution": tier_distribution,
        "tier_revenue_breakdown": tier_revenue_breakdown,
    }


def calc_hospital_summary(
    all_cases: list[CaseMixCell],
    ward_type: WardType,
    enabled_fees: list[AdditionalFee],
) -> dict:
    """Hospital-level aggregation across all wards.

    Same structure as calc_ward_summary but across all wards.

    Args:
        all_cases: 全病棟のケースミックスセルリスト.
        ward_type: 病棟入院料の届出区分.
        enabled_fees: 有効な加算リスト.

    Returns:
        dict: calc_ward_summary と同じ構造.
    """
    return calc_ward_summary(all_cases, ward_type, enabled_fees)


# ===========================================================================
# Constraint checking
# ===========================================================================


@dataclass
class ConstraintResult:
    """施設基準チェック結果.

    Attributes:
        constraint: チェック対象の施設基準.
        actual_value: 実測値.
        passed: 基準を満たしているかどうか.
        margin: 余裕度（正=安全圏、負=違反）.
    """

    constraint: FacilityConstraint
    actual_value: float
    passed: bool
    margin: float


def check_avg_los(
    cases: list[CaseMixCell], age_85_ratio: float
) -> ConstraintResult:
    """Check weighted average LOS against the facility constraint.

    Threshold adjusts based on 85歳以上割合:
    base = 20 + floor(age_85_ratio / 0.20), max = 24.

    Args:
        cases: ケースミックスセルリスト.
        age_85_ratio: 85歳以上患者の割合 (0.0-1.0).

    Returns:
        ConstraintResult with actual LOS vs adjusted threshold.
    """
    # Find the avg LOS constraint
    constraint = _find_constraint("平均在院日数")

    # Calculate adjusted threshold
    adjustment = min(math.floor(age_85_ratio / 0.20), 4)
    adjusted_threshold = 20.0 + adjustment
    adjusted_threshold = min(adjusted_threshold, 24.0)

    # Calculate weighted average LOS
    total_count = sum(c.monthly_count for c in cases)
    if total_count == 0:
        actual = 0.0
    else:
        actual = sum(c.avg_los * c.monthly_count for c in cases) / total_count

    # operator is "<="
    passed = actual <= adjusted_threshold
    margin = adjusted_threshold - actual

    # Create a modified constraint with the adjusted threshold for reporting
    adjusted_constraint = FacilityConstraint(
        name=constraint.name,
        threshold=adjusted_threshold,
        operator=constraint.operator,
        severity=constraint.severity,
        description=constraint.description,
        unit=constraint.unit,
        adjustable=constraint.adjustable,
    )

    return ConstraintResult(
        constraint=adjusted_constraint,
        actual_value=actual,
        passed=passed,
        margin=margin,
    )


def check_emergency_ratio(cases: list[CaseMixCell]) -> ConstraintResult:
    """Check emergency admission ratio >= 15%.

    Args:
        cases: ケースミックスセルリスト.

    Returns:
        ConstraintResult with actual emergency ratio vs 15% threshold.
    """
    constraint = _find_constraint("救急搬送後患者割合")

    total_count = sum(c.monthly_count for c in cases)
    emergency_count = sum(c.monthly_count for c in cases if c.is_emergency)

    if total_count == 0:
        actual = 0.0
    else:
        actual = (emergency_count / total_count) * 100.0

    # operator is ">="
    passed = actual >= constraint.threshold
    margin = actual - constraint.threshold

    return ConstraintResult(
        constraint=constraint,
        actual_value=actual,
        passed=passed,
        margin=margin,
    )


def check_constraint_generic(
    actual: float, constraint: FacilityConstraint
) -> ConstraintResult:
    """Generic check using the constraint's operator and threshold.

    Supports operators: "<=", ">=", "<", ">".

    Args:
        actual: 実測値.
        constraint: チェック対象の施設基準.

    Returns:
        ConstraintResult.
    """
    threshold = constraint.threshold
    op = constraint.operator

    if op == "<=":
        passed = actual <= threshold
        margin = threshold - actual
    elif op == ">=":
        passed = actual >= threshold
        margin = actual - threshold
    elif op == "<":
        passed = actual < threshold
        margin = threshold - actual
    elif op == ">":
        passed = actual > threshold
        margin = actual - threshold
    else:
        raise ValueError(f"Unknown operator: {op}")

    return ConstraintResult(
        constraint=constraint,
        actual_value=actual,
        passed=passed,
        margin=margin,
    )


def check_all_constraints(
    cases: list[CaseMixCell],
    age_85_ratio: float,
    adl_decline_ratio: float,
    home_discharge_ratio: float,
    nursing_necessity_ratio: float,
    data_submission: bool,
    rehab_staff_count: int,
) -> list[ConstraintResult]:
    """Run all FACILITY_CONSTRAINTS checks.

    Args:
        cases: ケースミックスセルリスト.
        age_85_ratio: 85歳以上患者割合 (0.0-1.0).
        adl_decline_ratio: ADL低下患者割合 (%).
        home_discharge_ratio: 在宅復帰率 (%).
        nursing_necessity_ratio: 重症度・医療看護必要度の該当割合 (%).
        data_submission: データ提出加算の届出有無.
        rehab_staff_count: リハ専門職の配置人数.

    Returns:
        list[ConstraintResult]: 全施設基準のチェック結果.
    """
    results: list[ConstraintResult] = []

    # 1. 平均在院日数（adjustable）
    results.append(check_avg_los(cases, age_85_ratio))

    # 2. 救急搬送後患者割合
    results.append(check_emergency_ratio(cases))

    # 3. ADL低下割合
    adl_constraint = _find_constraint("ADL低下割合")
    results.append(check_constraint_generic(adl_decline_ratio, adl_constraint))

    # 4. 在宅復帰率
    home_constraint = _find_constraint("在宅復帰率")
    results.append(check_constraint_generic(home_discharge_ratio, home_constraint))

    # 5. 重症度・医療看護必要度
    nursing_constraint = _find_constraint("重症度・医療看護必要度")
    results.append(
        check_constraint_generic(nursing_necessity_ratio, nursing_constraint)
    )

    # 6. データ提出加算
    data_constraint = _find_constraint("データ提出加算")
    data_value = 1.0 if data_submission else 0.0
    results.append(check_constraint_generic(data_value, data_constraint))

    # 7. リハ専門職配置
    rehab_constraint = _find_constraint("リハ専門職配置")
    results.append(
        check_constraint_generic(float(rehab_staff_count), rehab_constraint)
    )

    return results


def _find_constraint(name: str) -> FacilityConstraint:
    """Helper to find a constraint by name from FACILITY_CONSTRAINTS.

    Args:
        name: 施設基準の名前.

    Returns:
        FacilityConstraint.

    Raises:
        ValueError: 該当する施設基準が見つからない場合.
    """
    for c in FACILITY_CONSTRAINTS:
        if c.name == name:
            return c
    raise ValueError(f"Constraint not found: {name}")


# ===========================================================================
# Sensitivity analysis
# ===========================================================================


def sensitivity_by_emergency_ratio(
    cases: list[CaseMixCell],
    ward_type: WardType,
    enabled_fees: list[AdditionalFee],
    ratio_range: tuple[float, float] = (0.10, 0.50),
    steps: int = 20,
) -> list[dict]:
    """Vary emergency admission ratio and return revenue + constraint status.

    各ステップで全ケースの emergency/planned 比率を変更し、
    収益と救急搬送後患者割合の基準充足状況を算出する。

    Args:
        cases: 元のケースミックスセルリスト.
        ward_type: 病棟入院料の届出区分.
        enabled_fees: 有効な加算リスト.
        ratio_range: 救急割合の範囲 (min, max).
        steps: 分割ステップ数.

    Returns:
        list[dict]: 各ステップの {emergency_ratio, total_monthly_revenue,
        total_annual_revenue, emergency_constraint_passed, emergency_constraint_margin}.
    """
    results: list[dict] = []
    lo, hi = ratio_range
    step_size = (hi - lo) / steps if steps > 0 else 0

    for i in range(steps + 1):
        target_ratio = lo + step_size * i

        # Rebuild cases with the new emergency ratio
        adjusted_cases = _adjust_emergency_ratio(cases, target_ratio)

        # Calculate revenue
        summary = calc_hospital_summary(adjusted_cases, ward_type, enabled_fees)

        # Check emergency constraint
        emg_result = check_emergency_ratio(adjusted_cases)

        results.append(
            {
                "emergency_ratio": target_ratio,
                "total_monthly_revenue": summary["total_monthly_revenue"],
                "total_annual_revenue": summary["total_annual_revenue"],
                "emergency_constraint_passed": emg_result.passed,
                "emergency_constraint_margin": emg_result.margin,
            }
        )

    return results


def _adjust_emergency_ratio(
    cases: list[CaseMixCell], target_ratio: float
) -> list[CaseMixCell]:
    """Adjust case mix to achieve a target emergency ratio.

    同じ department / ward / surgery の組み合わせごとに、
    emergency と planned の件数を target_ratio に従って再配分する。

    Args:
        cases: 元のケースミックスセルリスト.
        target_ratio: 目標救急割合 (0.0-1.0).

    Returns:
        list[CaseMixCell]: 件数調整済みのケースリスト.
    """
    # Group by (ward, department, has_surgery) pairs
    from collections import defaultdict

    groups: dict[tuple[str, Department, bool], list[CaseMixCell]] = defaultdict(list)
    for case in cases:
        key = (case.ward, case.department, case.has_surgery)
        groups[key].append(case)

    adjusted: list[CaseMixCell] = []

    for key, group_cases in groups.items():
        total = sum(c.monthly_count for c in group_cases)
        if total == 0:
            adjusted.extend(group_cases)
            continue

        emg_count = round(total * target_ratio)
        planned_count = total - emg_count

        for case in group_cases:
            new_count = emg_count if case.is_emergency else planned_count
            adjusted.append(
                CaseMixCell(
                    ward=case.ward,
                    department=case.department,
                    is_emergency=case.is_emergency,
                    has_surgery=case.has_surgery,
                    monthly_count=new_count,
                    avg_los=case.avg_los,
                )
            )
            # Only assign once per group
            if case.is_emergency:
                emg_count = 0
            else:
                planned_count = 0

    return adjusted


def marginal_revenue_per_case(
    ward_type: WardType,
    enabled_fees: list[AdditionalFee],
    avg_los: float = 17.0,
) -> dict[AdmissionTier, int]:
    """Revenue from one additional case at each tier level.

    Args:
        ward_type: 病棟入院料の届出区分.
        enabled_fees: 有効な加算リスト.
        avg_los: 想定平均在院日数.

    Returns:
        dict mapping AdmissionTier -> marginal revenue in yen.
    """
    los = max(1, round(avg_los))
    return {
        tier: calc_stay_total_yen(ward_type, tier, los, enabled_fees)
        for tier in AdmissionTier
    }


# ===========================================================================
# Utility
# ===========================================================================


def generate_default_cases() -> list[CaseMixCell]:
    """Generate default case mix from DEPARTMENT_DEFAULTS in config.

    Each department is split into 4 cells:
    - emergency + no surgery
    - emergency + surgery
    - planned + no surgery
    - planned + surgery

    The monthly_count for each cell is derived from the department's
    emergency_ratio and surgery_ratio.

    Returns:
        list[CaseMixCell]: デフォルトケースミックス.
    """
    cases: list[CaseMixCell] = []

    for dept, defaults in DEPARTMENT_DEFAULTS.items():
        total = defaults["monthly_count"]
        emg_ratio = defaults["emergency_ratio"]
        surg_ratio = defaults["surgery_ratio"]
        avg_los = defaults["avg_los"]
        ward = defaults["primary_ward"]

        emg_total = round(total * emg_ratio)
        planned_total = total - emg_total

        emg_surg = round(emg_total * surg_ratio)
        emg_no_surg = emg_total - emg_surg
        planned_surg = round(planned_total * surg_ratio)
        planned_no_surg = planned_total - planned_surg

        cells = [
            (True, False, emg_no_surg),    # emergency, no surgery
            (True, True, emg_surg),         # emergency, surgery
            (False, False, planned_no_surg),  # planned, no surgery
            (False, True, planned_surg),     # planned, surgery
        ]

        for is_emg, has_surg, count in cells:
            cases.append(
                CaseMixCell(
                    ward=ward,
                    department=dept,
                    is_emergency=is_emg,
                    has_surgery=has_surg,
                    monthly_count=count,
                    avg_los=avg_los,
                )
            )

    return cases


def generate_audit_log(
    cases: list[CaseMixCell],
    ward_type: WardType,
    enabled_fees: list[AdditionalFee],
    constraint_results: list[ConstraintResult],
) -> str:
    """Generate a text audit log with constraint results and revenue summary.

    Args:
        cases: ケースミックスセルリスト.
        ward_type: 病棟入院料の届出区分.
        enabled_fees: 有効な加算リスト.
        constraint_results: 施設基準チェック結果のリスト.

    Returns:
        str: 監査ログテキスト.
    """
    lines: list[str] = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines.append("=" * 70)
    lines.append(f"診療報酬シミュレーション 監査ログ  {now}")
    lines.append(f"病棟入院料区分: {ward_type.value}")
    lines.append("=" * 70)

    # --- Constraint results ---
    lines.append("")
    lines.append("■ 施設基準チェック結果")
    lines.append("-" * 50)

    must_results = [r for r in constraint_results if r.constraint.severity == ConstraintSeverity.MUST]
    should_results = [r for r in constraint_results if r.constraint.severity == ConstraintSeverity.SHOULD]

    must_passed = sum(1 for r in must_results if r.passed)
    must_total = len(must_results)

    lines.append(f"  MUST基準: {must_passed}/{must_total} 充足")

    for r in must_results:
        status = "OK" if r.passed else "NG"
        sign = "+" if r.margin >= 0 else ""
        lines.append(
            f"  [{status}] {r.constraint.name}: "
            f"実測 {r.actual_value:.1f}{r.constraint.unit} "
            f"(基準 {r.constraint.operator} {r.constraint.threshold:.1f}{r.constraint.unit}, "
            f"余裕 {sign}{r.margin:.1f})"
        )

    if should_results:
        should_passed = sum(1 for r in should_results if r.passed)
        should_total = len(should_results)
        lines.append(f"  SHOULD基準: {should_passed}/{should_total} 充足")

        for r in should_results:
            status = "OK" if r.passed else "注意"
            sign = "+" if r.margin >= 0 else ""
            lines.append(
                f"  [{status}] {r.constraint.name}: "
                f"実測 {r.actual_value:.1f}{r.constraint.unit} "
                f"(基準 {r.constraint.operator} {r.constraint.threshold:.1f}{r.constraint.unit}, "
                f"余裕 {sign}{r.margin:.1f})"
            )

    # --- Revenue summary ---
    lines.append("")
    lines.append("■ 収益サマリー")
    lines.append("-" * 50)

    summary = calc_hospital_summary(cases, ward_type, enabled_fees)
    lines.append(f"  月間入院件数: {summary['total_monthly_cases']}件")
    lines.append(f"  加重平均在院日数: {summary['weighted_avg_los']:.1f}日")
    lines.append(f"  加重平均日額点数: {summary['weighted_avg_daily_points']:.0f}点")
    lines.append(f"  月間収入: {summary['total_monthly_revenue']:,}円")
    lines.append(f"  年間収入: {summary['total_annual_revenue']:,}円")

    # Tier breakdown
    lines.append("")
    lines.append("  入院料区分別内訳:")
    for tier in AdmissionTier:
        count = summary["tier_distribution"][tier]
        rev = summary["tier_revenue_breakdown"][tier]
        lines.append(f"    {tier.value}: {count}件/月, {rev:,}円/月")

    # --- Enabled fees ---
    lines.append("")
    lines.append("■ 有効加算一覧")
    lines.append("-" * 50)
    for fee in enabled_fees:
        end_str = f"{fee.day_end}日目" if fee.day_end is not None else "無制限"
        lines.append(
            f"  {fee.name}: {fee.points}点 "
            f"({fee.day_start}日目〜{end_str})"
        )

    lines.append("")
    lines.append("=" * 70)

    return "\n".join(lines)
