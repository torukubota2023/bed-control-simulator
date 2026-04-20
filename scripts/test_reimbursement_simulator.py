"""
地域包括医療病棟入院料 診療報酬シミュレーター ユニットテスト

reimbursement_simulator.py の全主要関数を網羅的にテストする。
"""

import sys
import os

import pytest

# Ensure scripts directory is on path
sys.path.insert(0, os.path.dirname(__file__))

from reimbursement_config import (
    AdditionalFee,
    AdmissionTier,
    CaseMixCell,
    classify_admission_tier,
    Department,
    POINT_OVER_90_DAYS,
    POINT_TABLE,
    WardType,
    YEN_PER_POINT,
)
from reimbursement_simulator import (
    calc_case_revenue,
    calc_stay_total_points,
    check_all_constraints,
    check_avg_los,
    check_emergency_ratio,
    generate_default_cases,
    get_base_points,
    get_daily_points,
    marginal_revenue_per_case,
)


# ===========================================================================
# Helpers
# ===========================================================================

# Minimal fee set used across many tests
INITIAL_FEE = AdditionalFee(
    name="初期加算",
    points=150,
    day_start=1,
    day_end=14,
    enabled_default=True,
    category="基本加算",
)
PRICE_FEE = AdditionalFee(
    name="物価対応料(令和8年度)",
    points=49,
    day_start=1,
    day_end=None,
    enabled_default=True,
    category="物価対応",
)
DEFAULT_FEES = [INITIAL_FEE, PRICE_FEE]


def _make_case(
    is_emergency: bool,
    has_surgery: bool,
    monthly_count: int = 10,
    avg_los: float = 17.0,
    ward: str = "6F",
    department: Department = Department.INTERNAL,
) -> CaseMixCell:
    return CaseMixCell(
        ward=ward,
        department=department,
        is_emergency=is_emergency,
        has_surgery=has_surgery,
        monthly_count=monthly_count,
        avg_los=avg_los,
    )


# ===========================================================================
# 1. Point table tests
# ===========================================================================


class TestPointTable:
    def test_point_table_type1_tier1(self):
        assert get_base_points(WardType.TYPE_1, AdmissionTier.TIER_1) == 3367

    def test_point_table_type1_tier3(self):
        assert get_base_points(WardType.TYPE_1, AdmissionTier.TIER_3) == 3117

    def test_point_table_type2_tier1(self):
        assert get_base_points(WardType.TYPE_2, AdmissionTier.TIER_1) == 3316

    def test_point_table_type2_tier3(self):
        assert get_base_points(WardType.TYPE_2, AdmissionTier.TIER_3) == 3066

    def test_all_6_tiers_exist(self):
        """All 6 ward_type x tier combinations return a valid int."""
        for wt in WardType:
            for tier in AdmissionTier:
                pts = get_base_points(wt, tier)
                assert isinstance(pts, int)
                assert pts > 0


# ===========================================================================
# 2. Admission tier derivation
# ===========================================================================


class TestAdmissionTier:
    def test_tier_emergency_no_surgery(self):
        case = _make_case(is_emergency=True, has_surgery=False)
        assert case.admission_tier == AdmissionTier.TIER_1

    def test_tier_emergency_with_surgery(self):
        case = _make_case(is_emergency=True, has_surgery=True)
        assert case.admission_tier == AdmissionTier.TIER_2

    def test_tier_planned_no_surgery(self):
        case = _make_case(is_emergency=False, has_surgery=False)
        assert case.admission_tier == AdmissionTier.TIER_2

    def test_tier_planned_with_surgery(self):
        case = _make_case(is_emergency=False, has_surgery=True)
        assert case.admission_tier == AdmissionTier.TIER_3


class TestClassifyAdmissionTierStandalone:
    """`classify_admission_tier()` のスタンドアロン判定関数のテスト。"""

    def test_emergency_no_surgery_is_tier1(self):
        """イ（入院料1）: 緊急・手術なし → TIER_1（最高点）"""
        assert classify_admission_tier(True, False) == AdmissionTier.TIER_1

    def test_emergency_with_surgery_is_tier2(self):
        """ロ（入院料2）: 緊急・手術あり → TIER_2"""
        assert classify_admission_tier(True, True) == AdmissionTier.TIER_2

    def test_planned_no_surgery_is_tier2(self):
        """ロ（入院料2）: 予定・手術なし → TIER_2"""
        assert classify_admission_tier(False, False) == AdmissionTier.TIER_2

    def test_planned_with_surgery_is_tier3(self):
        """ハ（入院料3）: 予定・手術あり → TIER_3（最低点）"""
        assert classify_admission_tier(False, True) == AdmissionTier.TIER_3

    def test_classify_matches_patient_group(self):
        """スタンドアロン関数と PatientGroup.admission_tier の結果が一致する。"""
        for is_emg in (True, False):
            for has_surg in (True, False):
                case = _make_case(is_emergency=is_emg, has_surgery=has_surg)
                assert classify_admission_tier(is_emg, has_surg) == case.admission_tier


# ===========================================================================
# 3. Daily points
# ===========================================================================


class TestDailyPoints:
    def test_daily_points_day1_with_fees(self):
        """Day 1: base + 初期加算(150) + 物価対応(49) at minimum."""
        pts = get_daily_points(
            WardType.TYPE_1, AdmissionTier.TIER_1, day_of_stay=1, enabled_fees=DEFAULT_FEES
        )
        base = 3367
        assert pts >= base + 150 + 49
        assert pts == base + 150 + 49

    def test_daily_points_day15_no_initial_fee(self):
        """Day 15: 初期加算 expired (day_end=14), only 物価対応 applies."""
        pts = get_daily_points(
            WardType.TYPE_1, AdmissionTier.TIER_1, day_of_stay=15, enabled_fees=DEFAULT_FEES
        )
        base = 3367
        # 初期加算 does NOT apply on day 15
        assert pts == base + 49

    def test_daily_points_day91_over90(self):
        """Day 91: POINT_OVER_90_DAYS(988) + applicable fees."""
        pts = get_daily_points(
            WardType.TYPE_1, AdmissionTier.TIER_1, day_of_stay=91, enabled_fees=DEFAULT_FEES
        )
        # 物価対応(49) has day_end=None, so still applies
        assert pts == POINT_OVER_90_DAYS + 49
        assert pts == 988 + 49


# ===========================================================================
# 4. Stay total
# ===========================================================================


class TestStayTotal:
    def test_stay_14days(self):
        """14-day stay: all days have 初期加算 + 物価対応."""
        total = calc_stay_total_points(
            WardType.TYPE_1, AdmissionTier.TIER_1, los=14, enabled_fees=DEFAULT_FEES
        )
        base = 3367
        expected = (base + 150 + 49) * 14
        assert total == expected

    def test_stay_17days(self):
        """17-day stay: 14 days with full fees + 3 days with only 物価対応."""
        total = calc_stay_total_points(
            WardType.TYPE_1, AdmissionTier.TIER_1, los=17, enabled_fees=DEFAULT_FEES
        )
        base = 3367
        first_14 = (base + 150 + 49) * 14
        last_3 = (base + 49) * 3
        assert total == first_14 + last_3


# ===========================================================================
# 5. Constraint checks
# ===========================================================================


class TestConstraints:
    def _make_cases_with_los(self, avg_los: float, count: int = 100) -> list[CaseMixCell]:
        """Helper: single case with given avg_los and count."""
        return [_make_case(is_emergency=True, has_surgery=False, monthly_count=count, avg_los=avg_los)]

    def test_avg_los_pass(self):
        """LOS 19, age85=10% -> threshold=20, pass."""
        cases = self._make_cases_with_los(19.0)
        result = check_avg_los(cases, age_85_ratio=0.10)
        assert result.passed is True

    def test_avg_los_fail(self):
        """LOS 21, age85=10% -> threshold=20, fail."""
        cases = self._make_cases_with_los(21.0)
        result = check_avg_los(cases, age_85_ratio=0.10)
        assert result.passed is False

    def test_avg_los_adjusted(self):
        """LOS 21, age85=25% -> threshold = 20 + floor(0.25/0.20) = 21, pass."""
        cases = self._make_cases_with_los(21.0)
        result = check_avg_los(cases, age_85_ratio=0.25)
        assert result.passed is True
        assert result.constraint.threshold == 21.0

    def test_emergency_ratio_pass(self):
        """20% emergency -> >= 15% threshold, pass."""
        cases = [
            _make_case(is_emergency=True, has_surgery=False, monthly_count=20),
            _make_case(is_emergency=False, has_surgery=False, monthly_count=80),
        ]
        result = check_emergency_ratio(cases)
        assert result.passed is True

    def test_emergency_ratio_fail(self):
        """10% emergency -> < 15% threshold, fail."""
        cases = [
            _make_case(is_emergency=True, has_surgery=False, monthly_count=10),
            _make_case(is_emergency=False, has_surgery=False, monthly_count=90),
        ]
        result = check_emergency_ratio(cases)
        assert result.passed is False

    def test_check_all_constraints_returns_all(self):
        """check_all_constraints returns 7 results (one per FACILITY_CONSTRAINTS entry)."""
        cases = [_make_case(is_emergency=True, has_surgery=False, monthly_count=100)]
        results = check_all_constraints(
            cases=cases,
            age_85_ratio=0.10,
            adl_decline_ratio=3.0,
            home_discharge_ratio=80.0,
            nursing_necessity_ratio=20.0,
            data_submission=True,
            rehab_staff_count=2,
        )
        assert len(results) == 7


# ===========================================================================
# 6. Default case generation
# ===========================================================================


class TestDefaultCases:
    def test_generate_default_cases_count(self):
        """4 departments x 4 combos = 16 cells."""
        cases = generate_default_cases()
        assert len(cases) == 16

    def test_default_cases_total_monthly(self):
        """Total monthly count should sum to ~150."""
        cases = generate_default_cases()
        total = sum(c.monthly_count for c in cases)
        assert total == 150


# ===========================================================================
# 7. Revenue calculation
# ===========================================================================


class TestRevenue:
    def test_case_revenue_structure(self):
        """Returned dict has all expected keys."""
        case = _make_case(is_emergency=True, has_surgery=False, monthly_count=10, avg_los=17.0)
        rev = calc_case_revenue(case, WardType.TYPE_1, DEFAULT_FEES)
        expected_keys = {
            "tier",
            "base_points_per_day",
            "avg_daily_points",
            "total_points_per_stay",
            "total_yen_per_stay",
            "monthly_revenue",
            "annual_revenue",
        }
        assert set(rev.keys()) == expected_keys

    def test_marginal_revenue_ordering(self):
        """TIER_1 > TIER_2 > TIER_3 for same LOS and fees."""
        marginals = marginal_revenue_per_case(WardType.TYPE_1, DEFAULT_FEES, avg_los=17.0)
        assert marginals[AdmissionTier.TIER_1] > marginals[AdmissionTier.TIER_2]
        assert marginals[AdmissionTier.TIER_2] > marginals[AdmissionTier.TIER_3]
