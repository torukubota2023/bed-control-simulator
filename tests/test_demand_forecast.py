"""
Phase 3α: demand_forecast モジュールのユニットテスト
+ calculate_weekend_whatif の新旧パス切替検証
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from demand_forecast import (
    DEFAULT_TOTAL_BEDS,
    classify_week_type,
    estimate_existing_vacancy,
    forecast_weekly_demand,
    load_historical_admissions,
)
from bed_management_metrics import calculate_weekend_whatif


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------

def _make_synthetic_admissions(
    start: date = date(2025, 3, 31),  # Monday
    weeks: int = 52,
    daily_counts: dict[int, int] | None = None,
    ward_mix: tuple[str, str] = ("5F", "6F"),
) -> pd.DataFrame:
    """
    合成入院データ: 曜日別入院数を指定して weeks 週分生成。

    daily_counts: {0: 月曜入院数, 1: 火曜入院数, ..., 6: 日曜入院数}
    """
    if daily_counts is None:
        # 実データの曜日別平均（月 7.92 / 火 6.94 / 水 7.33 / 木 5.71 / 金 5.31 / 土 2.44 / 日 0.29）
        daily_counts = {0: 8, 1: 7, 2: 7, 3: 6, 4: 5, 5: 2, 6: 0}

    records = []
    for w in range(weeks):
        for d in range(7):
            day = start + timedelta(days=w * 7 + d)
            n = daily_counts.get(d, 0)
            for i in range(n):
                ward = ward_mix[i % len(ward_mix)]
                records.append({
                    "admission_date": pd.Timestamp(day),
                    "ward_short": ward,
                    "dow": d,
                    "type_short": "予定" if i % 3 == 0 else "緊急",
                })
    return pd.DataFrame(records)


# ---------------------------------------------------------------
# 1. load_historical_admissions — 入出力基本動作
# ---------------------------------------------------------------

class TestLoadHistoricalAdmissions:

    def test_missing_file_returns_empty(self):
        df = load_historical_admissions("/nonexistent/path/foo.csv")
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_real_csv_if_exists(self):
        """実データが存在すれば件数を確認（約1,876件）"""
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..",
            "data", "admissions_consolidated_dedup.csv",
        )
        if not os.path.exists(path):
            pytest.skip("real CSV not available")
        df = load_historical_admissions(path)
        assert len(df) > 1000
        assert "admission_date" in df.columns
        assert "dow" in df.columns


# ---------------------------------------------------------------
# 2. forecast_weekly_demand — 基本動作と曜日別平均
# ---------------------------------------------------------------

class TestForecastWeeklyDemand:

    def test_basic_structure(self):
        df = _make_synthetic_admissions(weeks=52)
        target = date(2026, 3, 30)  # 月曜（データ末尾内）
        result = forecast_weekly_demand(df, target, ward=None, lookback_months=12)

        # 必須キーが揃っている
        for k in ("target_week_start", "dow_means", "expected_weekly_total",
                  "p25", "p75", "recent_trend_factor", "confidence", "sample_size"):
            assert k in result

        # 曜日別平均が設定値に近い
        means = result["dow_means"]
        assert means[0] == pytest.approx(8, abs=1.0)  # 月
        assert means[4] == pytest.approx(5, abs=1.0)  # 金
        assert means[6] == pytest.approx(0, abs=1.0)  # 日

    def test_weekly_total(self):
        df = _make_synthetic_admissions(weeks=52)
        target = date(2026, 3, 30)  # データ末尾内
        result = forecast_weekly_demand(df, target)
        # 8+7+7+6+5+2+0 = 35
        assert 30 <= result["expected_weekly_total"] <= 40

    def test_ward_filter(self):
        df = _make_synthetic_admissions(weeks=52)
        target = date(2026, 3, 30)
        r5f = forecast_weekly_demand(df, target, ward="5F")
        r_all = forecast_weekly_demand(df, target, ward=None)
        assert r5f["expected_weekly_total"] < r_all["expected_weekly_total"]

    def test_empty_df(self):
        result = forecast_weekly_demand(pd.DataFrame(), date(2026, 3, 30))
        assert result["expected_weekly_total"] == 0.0
        assert result["confidence"] == "low"
        assert result["sample_size"] == 0

    def test_confidence_high_with_large_sample(self):
        df = _make_synthetic_admissions(weeks=52)
        target = date(2026, 3, 30)
        result = forecast_weekly_demand(df, target)
        # 52週 × 約35件/週 = 約1,820件 → high
        assert result["confidence"] == "high"

    def test_confidence_low_with_small_sample(self):
        df = _make_synthetic_admissions(
            weeks=2,
            daily_counts={0: 2, 1: 2, 2: 2, 3: 2, 4: 2, 5: 0, 6: 0},
        )
        target = date(2025, 4, 29)  # 開始から約4週後
        result = forecast_weekly_demand(df, target)
        # 少量データ → low か medium
        assert result["confidence"] in ("low", "medium")


# ---------------------------------------------------------------
# 3. estimate_existing_vacancy
# ---------------------------------------------------------------

class TestEstimateExistingVacancy:

    def test_basic(self):
        # 稼働率 90% → 空床 9.4 床
        v = estimate_existing_vacancy(date(2026, 4, 6), 0.90, total_beds=94)
        assert v == pytest.approx(9.4)

    def test_zero_occupancy(self):
        v = estimate_existing_vacancy(date(2026, 4, 6), 0.0, total_beds=94)
        assert v == pytest.approx(94.0)

    def test_full_occupancy(self):
        v = estimate_existing_vacancy(date(2026, 4, 6), 1.0, total_beds=94)
        assert v == pytest.approx(0.0)

    def test_clamped(self):
        # 1.0 超えはクランプ
        v = estimate_existing_vacancy(date(2026, 4, 6), 1.5, total_beds=94)
        assert v == pytest.approx(0.0)

    def test_default_total_beds(self):
        v = estimate_existing_vacancy(date(2026, 4, 6), 0.90)
        # DEFAULT_TOTAL_BEDS = 94
        assert v == pytest.approx(DEFAULT_TOTAL_BEDS * 0.1)


# ---------------------------------------------------------------
# 4. classify_week_type — 3分類の境界
# ---------------------------------------------------------------

class TestClassifyWeekType:

    def test_high(self):
        # 需要 10件/日 > 空床 5床/日 + margin 1.0 → high
        r = classify_week_type(10.0, 5.0, margin=1.0)
        assert r["type"] == "high"
        assert "有効" in r["recommendation"]

    def test_low(self):
        # 需要 5件/日 < 空床 11床/日 - margin 1.0 → low
        r = classify_week_type(5.0, 11.0, margin=1.0)
        assert r["type"] == "low"
        assert "逆効果" in r["recommendation"]

    def test_standard(self):
        # 需要 6件/日 ≈ 空床 6床/日 → standard
        r = classify_week_type(6.0, 6.0, margin=1.0)
        assert r["type"] == "standard"

    def test_boundary_high(self):
        # 需要 7.01 vs 空床 6.0 + margin 1.0 → high（ぎりぎり）
        r = classify_week_type(7.01, 6.0, margin=1.0)
        assert r["type"] == "high"

    def test_boundary_low(self):
        # 需要 4.99 vs 空床 6.0 - margin 1.0 → low（ぎりぎり）
        r = classify_week_type(4.99, 6.0, margin=1.0)
        assert r["type"] == "low"

    def test_delta_value(self):
        r = classify_week_type(8.0, 5.0)
        assert r["demand_minus_vacancy"] == pytest.approx(3.0)


# ---------------------------------------------------------------
# 5. calculate_weekend_whatif — 旧シグネチャ後方互換
# ---------------------------------------------------------------

class TestLegacyCompat:
    """demand_forecast/existing_vacancy なしなら従来通り動く"""

    def test_legacy_basic(self):
        r = calculate_weekend_whatif(shift=3, fill_rate=50, weekend_empty=10, unit_price_per_day=28900)
        assert r["effective_fill"] == pytest.approx(1.5)
        assert r["new_weekend_empty"] == pytest.approx(8.5)
        assert r["method"] == "legacy_slider"

    def test_legacy_saving(self):
        r = calculate_weekend_whatif(shift=4, fill_rate=50, weekend_empty=8.0, unit_price_per_day=28900)
        assert r["saving_annual"] == pytest.approx(2 * 2 * 28900 * 48)


# ---------------------------------------------------------------
# 6. calculate_weekend_whatif — 新 data_driven パス
# ---------------------------------------------------------------

class TestDataDrivenPath:
    """demand_forecast 渡しで需要ベース計算"""

    def test_low_demand_week_effective_zero(self):
        """低需要週: 需要 < 既存空床 → effective_fill = 0"""
        forecast = {
            "expected_weekly_total": 35.0,
            "dow_means": {0: 8, 1: 7, 2: 7, 3: 6, 4: 5, 5: 2, 6: 0},
            "p25": 30.0,
            "p75": 40.0,
        }
        # 金曜需要 5件 vs 空床 11床 → 需要 < 空床 → eff=0
        r = calculate_weekend_whatif(
            shift=3, fill_rate=50, weekend_empty=10, unit_price_per_day=28900,
            demand_forecast=forecast, existing_vacancy=11.0,
        )
        assert r["method"] == "data_driven"
        assert r["week_type"] == "low"
        assert r["effective_fill"] == pytest.approx(0.0)
        assert r["saving_annual"] == pytest.approx(0.0)

    def test_high_demand_week_effective_capped(self):
        """高需要週: 需要 > 空床 → effective_fill = min(shift, 需要-空床)"""
        forecast = {
            "expected_weekly_total": 70.0,
            "dow_means": {0: 12, 1: 11, 2: 10, 3: 10, 4: 15, 5: 7, 6: 5},
            "p25": 65.0,
            "p75": 75.0,
        }
        # 金曜需要 15件 vs 空床 5床 → 需要-空床=10 → min(shift=3, 10)=3
        r = calculate_weekend_whatif(
            shift=3, fill_rate=50, weekend_empty=8, unit_price_per_day=28900,
            demand_forecast=forecast, existing_vacancy=5.0,
        )
        assert r["week_type"] == "high"
        assert r["effective_fill"] == pytest.approx(3.0)

    def test_returns_range_tuples(self):
        forecast = {
            "expected_weekly_total": 50.0,
            "dow_means": {0: 9, 1: 8, 2: 8, 3: 7, 4: 10, 5: 5, 6: 3},
            "p25": 40.0,
            "p75": 60.0,
        }
        r = calculate_weekend_whatif(
            shift=4, fill_rate=50, weekend_empty=8, unit_price_per_day=28900,
            demand_forecast=forecast, existing_vacancy=6.0,
        )
        assert "effective_fill_range" in r
        assert "saving_annual_range" in r
        p25, p75 = r["saving_annual_range"]
        assert p25 <= r["saving_annual"] <= p75 or (p25 == p75 == 0.0 and r["saving_annual"] == 0.0)

    def test_recommendation_text_present(self):
        forecast = {
            "expected_weekly_total": 35.0,
            "dow_means": {0: 8, 1: 7, 2: 7, 3: 6, 4: 5, 5: 2, 6: 0},
            "p25": 30.0,
            "p75": 40.0,
        }
        r = calculate_weekend_whatif(
            shift=3, fill_rate=50, weekend_empty=10, unit_price_per_day=28900,
            demand_forecast=forecast, existing_vacancy=11.0,
        )
        assert isinstance(r["recommendation"], str)
        assert len(r["recommendation"]) > 0
        assert "rationale" in r


# ---------------------------------------------------------------
# 7. 統合シナリオ: 実データに近い値で逆効果週を再現
# ---------------------------------------------------------------

class TestRealWorldScenario:

    def test_76pct_weeks_are_low_demand(self):
        """
        金曜平均入院 5.31件 vs 金曜平均空床 11床（稼働率 88.8%）
        → 多くの週で低需要週 = 前倒し逆効果
        """
        df = _make_synthetic_admissions(weeks=52)
        target = date(2026, 3, 27)  # 金曜日（データ末尾内）
        forecast = forecast_weekly_demand(df, target)
        existing_vac = estimate_existing_vacancy(target, 0.888, total_beds=94)

        r = calculate_weekend_whatif(
            shift=3, fill_rate=50, weekend_empty=10, unit_price_per_day=28900,
            demand_forecast=forecast, existing_vacancy=existing_vac,
        )
        # 金曜需要 約5件 < 空床 約10.5床 → low 週
        assert r["week_type"] == "low"
        assert r["effective_fill"] == pytest.approx(0.0)
