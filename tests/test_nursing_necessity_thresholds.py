"""scripts/nursing_necessity_thresholds.py の単体テスト."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

# scripts/ を import path に追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from nursing_necessity_thresholds import (  # noqa: E402
    EMERGENCY_RESPONSE_COEFFICIENT_CAP,
    EMERGENCY_RESPONSE_COEFFICIENT_RATE,
    THRESHOLD_I_LEGACY,
    THRESHOLD_I_NEW,
    THRESHOLD_II_LEGACY,
    THRESHOLD_II_NEW,
    calculate_emergency_response_coefficient,
    evaluate_compliance,
    get_both_thresholds,
    get_threshold,
)


# ---------------------------------------------------------------------------
# get_threshold
# ---------------------------------------------------------------------------

class TestGetThreshold:
    """transitional 期間に応じた基準値返却."""

    def test_経過措置期間中はⅠ_16percent(self):
        assert get_threshold("I", date(2026, 5, 31)) == THRESHOLD_I_LEGACY
        assert get_threshold("I", date(2026, 1, 1)) == THRESHOLD_I_LEGACY

    def test_経過措置期間中はⅡ_14percent(self):
        assert get_threshold("II", date(2026, 5, 31)) == THRESHOLD_II_LEGACY

    def test_本則適用後はⅠ_19percent(self):
        assert get_threshold("I", date(2026, 6, 1)) == THRESHOLD_I_NEW
        assert get_threshold("I", date(2027, 1, 1)) == THRESHOLD_I_NEW

    def test_本則適用後はⅡ_18percent(self):
        assert get_threshold("II", date(2026, 6, 1)) == THRESHOLD_II_NEW

    def test_必要度区分が無効な場合はValueError(self):
        with pytest.raises(ValueError):
            get_threshold("III", date(2026, 5, 31))


# ---------------------------------------------------------------------------
# get_both_thresholds
# ---------------------------------------------------------------------------

class TestGetBothThresholds:
    """旧/新基準を tuple で返す."""

    def test_Ⅰ_両基準が返る(self):
        legacy, new = get_both_thresholds("I")
        assert legacy == THRESHOLD_I_LEGACY
        assert new == THRESHOLD_I_NEW
        assert new > legacy  # 新基準は厳格化方向

    def test_Ⅱ_両基準が返る(self):
        legacy, new = get_both_thresholds("II")
        assert legacy == THRESHOLD_II_LEGACY
        assert new == THRESHOLD_II_NEW
        assert new > legacy

    def test_必要度区分が無効な場合はValueError(self):
        with pytest.raises(ValueError):
            get_both_thresholds("X")


# ---------------------------------------------------------------------------
# evaluate_compliance
# ---------------------------------------------------------------------------

class TestEvaluateCompliance:
    """旧/新基準との照合と判定."""

    def test_新基準達成_status_ok_new(self):
        result = evaluate_compliance(0.20, "I", date(2026, 5, 31))
        assert result["status"] == "ok_new"
        assert result["meets_new"] is True
        assert result["meets_legacy"] is True

    def test_旧基準のみ達成_status_ok_legacy_only(self):
        result = evaluate_compliance(0.1821, "I", date(2026, 5, 31))
        assert result["status"] == "ok_legacy_only"
        assert result["meets_legacy"] is True
        assert result["meets_new"] is False

    def test_両基準未達_status_fail(self):
        result = evaluate_compliance(0.0603, "II", date(2026, 5, 31))
        assert result["status"] == "fail"
        assert result["meets_legacy"] is False
        assert result["meets_new"] is False

    def test_ギャップが正しく計算される(self):
        result = evaluate_compliance(0.1606, "I", date(2026, 5, 31))
        assert result["gap_legacy"] == pytest.approx(0.1606 - THRESHOLD_I_LEGACY)
        # 係数なしの場合 gap_new = rate - new
        assert result["gap_new"] == pytest.approx(0.1606 - THRESHOLD_I_NEW)

    def test_経過措置中は_current_threshold_が_legacy(self):
        result = evaluate_compliance(0.20, "I", date(2026, 5, 31))
        assert result["current_threshold"] == THRESHOLD_I_LEGACY

    def test_本則適用後は_current_threshold_が_new(self):
        result = evaluate_compliance(0.20, "I", date(2026, 6, 1))
        assert result["current_threshold"] == THRESHOLD_I_NEW

    def test_必要度区分が無効な場合はValueError(self):
        with pytest.raises(ValueError):
            evaluate_compliance(0.20, "Z", date(2026, 5, 31))

    def test_救急応需係数で新基準を超えると_ok_new_with_coefficient(self):
        # 5F-Ⅰ 12ヶ月平均 18.21% + 応需係数 1.48% = 19.69% → 新19% 達成
        result = evaluate_compliance(
            0.1821, "I", date(2026, 6, 1),
            emergency_coefficient=0.0148,
        )
        assert result["status"] == "ok_new_with_coefficient"
        assert result["meets_new"] is True
        assert result["meets_new_without_coefficient"] is False

    def test_応需係数あっても新基準未達なら_fail(self):
        # 6F-Ⅱ 13.13% + 1.48% = 14.61% → 新18% 未達
        result = evaluate_compliance(
            0.1313, "II", date(2026, 6, 1),
            emergency_coefficient=0.0148,
        )
        assert result["status"] == "fail"
        assert result["meets_new"] is False

    def test_応需係数なしで既に新基準達成なら_ok_new(self):
        result = evaluate_compliance(
            0.20, "I", date(2026, 6, 1),
            emergency_coefficient=0.0148,
        )
        assert result["status"] == "ok_new"
        assert result["meets_new_without_coefficient"] is True

    def test_adjusted_rate_new_は_rate_plus_coefficient(self):
        result = evaluate_compliance(
            0.18, "I", date(2026, 6, 1),
            emergency_coefficient=0.02,
        )
        assert result["adjusted_rate_new"] == pytest.approx(0.20)


# ---------------------------------------------------------------------------
# calculate_emergency_response_coefficient
# ---------------------------------------------------------------------------

class TestCalculateEmergencyResponseCoefficient:
    """救急患者応需係数の計算."""

    def test_当院想定値_279件_94床_で約_1_48percent(self):
        result = calculate_emergency_response_coefficient(
            annual_emergency_count=279,
            bed_count=94,
        )
        # 279 / 94 * 0.005 = 0.0148404...
        assert result["coefficient"] == pytest.approx(0.01484, abs=0.0001)
        assert result["per_bed_count"] == pytest.approx(2.97, abs=0.01)
        assert result["capped"] is False

    def test_上限_10percent_で_capped(self):
        # 病床あたり 25 件超 → 0.125 → 上限 0.10
        result = calculate_emergency_response_coefficient(
            annual_emergency_count=2500,
            bed_count=100,
        )
        assert result["coefficient_raw"] == pytest.approx(0.125)
        assert result["coefficient"] == 0.10
        assert result["capped"] is True

    def test_eligible_admission_ratio_を反映する(self):
        # 救急のうち 50% が地包病棟に入る場合
        result = calculate_emergency_response_coefficient(
            annual_emergency_count=200,
            bed_count=100,
            eligible_admission_ratio=0.5,
        )
        # (200 * 0.5 / 100) * 0.005 = 0.005
        assert result["coefficient"] == pytest.approx(0.005)

    def test_救急ゼロ件で係数ゼロ(self):
        result = calculate_emergency_response_coefficient(
            annual_emergency_count=0,
            bed_count=94,
        )
        assert result["coefficient"] == 0.0

    def test_病床数ゼロは_ValueError(self):
        with pytest.raises(ValueError):
            calculate_emergency_response_coefficient(279, 0)

    def test_負の救急件数は_ValueError(self):
        with pytest.raises(ValueError):
            calculate_emergency_response_coefficient(-1, 94)

    def test_eligible_ratio_範囲外は_ValueError(self):
        with pytest.raises(ValueError):
            calculate_emergency_response_coefficient(279, 94, eligible_admission_ratio=1.5)
        with pytest.raises(ValueError):
            calculate_emergency_response_coefficient(279, 94, eligible_admission_ratio=-0.1)

    def test_定数の値(self):
        assert EMERGENCY_RESPONSE_COEFFICIENT_RATE == 0.005
        assert EMERGENCY_RESPONSE_COEFFICIENT_CAP == 0.10


# ---------------------------------------------------------------------------
# 定数の妥当性
# ---------------------------------------------------------------------------

class TestConstants:
    """基準値定数が制度通りであること."""

    def test_Ⅰ_legacy_は_16percent(self):
        assert THRESHOLD_I_LEGACY == pytest.approx(0.16)

    def test_Ⅰ_new_は_19percent(self):
        assert THRESHOLD_I_NEW == pytest.approx(0.19)

    def test_Ⅱ_legacy_は_14percent(self):
        assert THRESHOLD_II_LEGACY == pytest.approx(0.14)

    def test_Ⅱ_new_は_18percent(self):
        assert THRESHOLD_II_NEW == pytest.approx(0.18)

    def test_新基準は旧より厳格(self):
        assert THRESHOLD_I_NEW > THRESHOLD_I_LEGACY
        assert THRESHOLD_II_NEW > THRESHOLD_II_LEGACY
