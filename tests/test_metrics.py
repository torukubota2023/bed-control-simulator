"""
ベッドコントロール指標のユニットテスト

bed_management_metrics.py の本番コードを直接 import してテストする。
"""

import pytest
import pandas as pd
import numpy as np
from datetime import timedelta

from bed_management_metrics import (
    prepare_bed_mgmt_daily_df,
    calculate_weekend_empty_metrics,
    calculate_next_day_reuse_rate,
    calculate_weekend_costs,
    calculate_weekend_whatif,
    calculate_unfilled_discharge_queue,
)


# ---------------------------------------------------------------
# Helper: テスト用 DataFrame 構築
# ---------------------------------------------------------------

def _build_weekly_df(total_beds: int, weekday_discharges: list, weekend_discharges: list):
    """1週間分のテスト DataFrame を構築する。"""
    base = pd.Timestamp("2026-04-06")  # 月曜日
    dates = [base + timedelta(days=i) for i in range(7)]
    discharges = weekday_discharges + weekend_discharges
    admissions = [5, 4, 5, 4, 3, 1, 1]

    patients = [total_beds]
    for i in range(1, 7):
        patients.append(patients[-1] + admissions[i] - discharges[i])

    return pd.DataFrame({
        "date": dates,
        "total_patients": patients,
        "new_admissions": admissions,
        "discharges": discharges,
    })


def _build_two_week_df(total_beds: int = 90):
    """2週間分のデータ（退院翌日再利用率テスト用）"""
    base = pd.Timestamp("2026-04-06")
    dates = [base + timedelta(days=i) for i in range(14)]
    # 平日は退院多め、土日は少ない
    discharges = [3, 4, 5, 4, 6, 1, 0] * 2
    admissions = [5, 4, 3, 5, 2, 1, 1] * 2
    patients = [total_beds]
    for i in range(1, 14):
        patients.append(max(0, patients[-1] + admissions[i] - discharges[i]))
    return pd.DataFrame({
        "date": dates,
        "total_patients": patients,
        "new_admissions": admissions,
        "discharges": discharges,
    })


# ---------------------------------------------------------------
# prepare_bed_mgmt_daily_df
# ---------------------------------------------------------------

class TestPrepare:
    """データ前処理のテスト"""

    def test_adds_dow_and_empty(self):
        df = _build_weekly_df(94, [3, 4, 5, 4, 6], [1, 0])
        result = prepare_bed_mgmt_daily_df(df, "全体", 94)
        assert "dow" in result.columns
        assert "empty" in result.columns
        assert len(result) == 7

    def test_ward_filter(self):
        df = _build_weekly_df(47, [2, 2, 3, 2, 3], [0, 0])
        df["ward"] = "5F"
        df2 = df.copy()
        df2["ward"] = "6F"
        combined = pd.concat([df, df2], ignore_index=True)
        result = prepare_bed_mgmt_daily_df(combined, "5F", 47)
        assert len(result) == 7

    def test_empty_df(self):
        result = prepare_bed_mgmt_daily_df(pd.DataFrame(), "全体", 94)
        assert len(result) == 0

    def test_none_input(self):
        result = prepare_bed_mgmt_daily_df(None, "全体", 94)
        assert len(result) == 0


# ---------------------------------------------------------------
# calculate_weekend_whatif (本番関数テスト)
# ---------------------------------------------------------------

class TestWeekendWhatIf:
    """前倒し x 充填確率 What-If のテスト"""

    def test_basic_case(self):
        result = calculate_weekend_whatif(shift=3, fill_rate=50, weekend_empty=10, unit_price_per_day=28900)
        assert result["effective_fill"] == pytest.approx(1.5)
        assert result["new_weekend_empty"] == pytest.approx(8.5)

    def test_full_fill_rate(self):
        result = calculate_weekend_whatif(shift=5, fill_rate=100, weekend_empty=10, unit_price_per_day=28900)
        assert result["effective_fill"] == pytest.approx(5.0)
        assert result["new_weekend_empty"] == pytest.approx(5.0)

    def test_zero_fill_rate(self):
        result = calculate_weekend_whatif(shift=3, fill_rate=0, weekend_empty=10, unit_price_per_day=28900)
        assert result["effective_fill"] == pytest.approx(0.0)
        assert result["new_weekend_empty"] == pytest.approx(10.0)

    def test_clamped_to_zero(self):
        result = calculate_weekend_whatif(shift=10, fill_rate=100, weekend_empty=5, unit_price_per_day=28900)
        assert result["effective_fill"] == pytest.approx(10.0)
        assert result["new_weekend_empty"] == pytest.approx(0.0)

    def test_zero_shift(self):
        result = calculate_weekend_whatif(shift=0, fill_rate=100, weekend_empty=10, unit_price_per_day=28900)
        assert result["effective_fill"] == pytest.approx(0.0)
        assert result["new_weekend_empty"] == pytest.approx(10.0)

    def test_saving_annual(self):
        result = calculate_weekend_whatif(shift=4, fill_rate=50, weekend_empty=8.0, unit_price_per_day=28900)
        # effective=2.0, saving_weekly = 2.0 * 2 * 28900 = 115,600
        assert result["saving_annual"] == pytest.approx(115600 * 48)


# ---------------------------------------------------------------
# calculate_weekend_empty_metrics (本番関数テスト)
# ---------------------------------------------------------------

class TestWeekendEmptyMetrics:
    """週末空床メトリクスのテスト"""

    def test_basic_metrics(self):
        df = _build_weekly_df(94, [3, 4, 5, 4, 6], [1, 0])
        df["dow"] = pd.to_datetime(df["date"]).dt.dayofweek
        df["empty"] = 94 - df["total_patients"].clip(upper=94)
        result = calculate_weekend_empty_metrics(df, 94)
        assert result["weekend_empty"] >= 0
        assert result["fri_dis"] == pytest.approx(6.0)

    def test_empty_df(self):
        result = calculate_weekend_empty_metrics(pd.DataFrame(), 94)
        assert result["weekend_empty"] == 0
        assert result["fri_to_mon_fill_rate"] == 0


# ---------------------------------------------------------------
# calculate_next_day_reuse_rate (本番関数テスト)
# ---------------------------------------------------------------

class TestNextDayReuseRate:
    """退院翌日再利用率のテスト"""

    def test_basic_reuse(self):
        df = _build_two_week_df(90)
        result = calculate_next_day_reuse_rate(df)
        assert 0 <= result["reuse_rate"] <= 100
        assert result["reuse_total"] > 0

    def test_empty_df(self):
        result = calculate_next_day_reuse_rate(pd.DataFrame())
        assert result["reuse_rate"] == 0.0

    def test_single_row(self):
        """1行だけなら翌日がないので reuse=0"""
        df = pd.DataFrame({
            "date": [pd.Timestamp("2026-04-06")],
            "discharges": [5],
            "new_admissions": [3],
        })
        result = calculate_next_day_reuse_rate(df)
        assert result["reuse_rate"] == 0.0


# ---------------------------------------------------------------
# calculate_weekend_costs
# ---------------------------------------------------------------

class TestWeekendCosts:
    """週末コスト計算のテスト"""

    def test_cost_structure(self):
        result = calculate_weekend_costs(10.0, 28900)
        assert result["weekly"] == pytest.approx(10 * 2 * 28900)
        assert result["monthly"] == pytest.approx(result["weekly"] * 4)
        assert result["annual"] == pytest.approx(result["monthly"] * 12)


# ---------------------------------------------------------------
# calculate_unfilled_discharge_queue (新 proxy 指標)
# ---------------------------------------------------------------

class TestUnfilledDischargeQueue:
    """未充填退院キュー proxy のテスト"""

    def test_basic_queue(self):
        df = _build_two_week_df(90)
        result = calculate_unfilled_discharge_queue(df)
        assert len(result["queue_series"]) == 14
        assert result["pseudo_empty_bed_days"] >= 0
        assert result["pseudo_lag_days"] >= 0

    def test_empty_df(self):
        result = calculate_unfilled_discharge_queue(pd.DataFrame())
        assert result["pseudo_empty_bed_days"] == 0.0

    def test_queue_clamped_to_zero(self):
        """入院 > 退院 なら q_t はゼロにクランプ"""
        df = pd.DataFrame({
            "date": [pd.Timestamp("2026-04-06"), pd.Timestamp("2026-04-07")],
            "discharges": [0, 0],
            "new_admissions": [5, 5],
        })
        result = calculate_unfilled_discharge_queue(df)
        assert all(q == 0.0 for _, q in result["queue_series"])

    def test_7d_avg(self):
        """7日移動平均が返ること"""
        df = _build_two_week_df(90)
        result = calculate_unfilled_discharge_queue(df)
        assert result["queue_7d_avg"] >= 0


# ---------------------------------------------------------------
# 退院曜日分布（bed_data_manager から — 既存テスト維持）
# ---------------------------------------------------------------

class TestDischargeWeekdayDistribution:
    """退院曜日分布関数のテスト"""

    def test_get_discharge_weekday_distribution(self):
        try:
            from bed_data_manager import get_discharge_weekday_distribution
        except ImportError:
            pytest.skip("get_discharge_weekday_distribution not importable")

        base = pd.Timestamp("2026-04-06")
        records = []
        discharge_counts = [3, 4, 5, 4, 6, 1, 0]
        for week in range(2):
            for dow, count in enumerate(discharge_counts):
                event_date = base + timedelta(days=week * 7 + dow)
                for _ in range(count):
                    records.append({
                        "date": event_date.strftime("%Y-%m-%d"),
                        "event_type": "discharge",
                        "ward": "5F",
                        "attending_doctor": "テスト医師",
                    })

        df = pd.DataFrame(records)
        result = get_discharge_weekday_distribution(df)
        assert isinstance(result, dict)
        assert len(result) == 7
        assert result[4] == 12
        assert result[6] == 0
