"""c_group_control モジュールのテスト。"""

import pandas as pd
import pytest
from datetime import date, timedelta

from c_group_control import (
    get_c_group_summary,
    calculate_c_adjustment_capacity,
    simulate_c_group_scenario,
    calculate_demand_absorption,
    generate_c_group_alerts,
    C_CONTRIBUTION_PER_DAY,
)


# ---------------------------------------------------------------------------
# 共通ヘルパー
# ---------------------------------------------------------------------------

def _make_daily_df(n_days=30, base_patients=80, base_admissions=5, base_discharges=5, start_date=None):
    """テスト用の日次DataFrameを生成する。"""
    if start_date is None:
        start_date = date(2026, 3, 1)
    rows = []
    for i in range(n_days):
        d = start_date + timedelta(days=i)
        dow = d.weekday()
        # 週末は入院少なめ
        adm = base_admissions if dow < 5 else max(1, base_admissions - 3)
        dis = base_discharges if dow < 5 else max(0, base_discharges - 4)
        patients = base_patients + (adm - dis) * (i % 3 - 1)
        rows.append({
            "date": str(d),
            "ward": "5F",
            "total_patients": max(patients, 0),
            "new_admissions": adm,
            "discharges": dis,
            "discharge_a": max(1, dis // 3),
            "discharge_b": max(1, dis // 3),
            "discharge_c": max(0, dis - 2 * max(1, dis // 3)),
        })
    return pd.DataFrame(rows)


def _make_rolling_los_result(rolling_los=18.0):
    """テスト用の rolling LOS 結果 dict を生成する。

    total_patient_days = rolling_los * denominator となるように設定。
    denominator = (total_admissions + total_discharges) / 2 = 400。
    """
    denominator = 400
    return {
        "rolling_los": rolling_los,
        "rolling_los_ex_short3": rolling_los,
        "total_patient_days": rolling_los * denominator,
        "total_admissions": denominator,
        "total_discharges": denominator,
        "actual_days": 90,
    }


# ---------------------------------------------------------------------------
# TestGetCGroupSummary
# ---------------------------------------------------------------------------

class TestGetCGroupSummary:
    def test_basic_summary(self):
        df = _make_daily_df(30)
        result = get_c_group_summary(df)
        assert result["c_count"] >= 0
        assert result["data_source"] in ("measured", "proxy")

    def test_none_df(self):
        result = get_c_group_summary(None)
        assert result["data_source"] == "not_available"


# ---------------------------------------------------------------------------
# TestCalculateCGroupAdjustmentCapacity
# ---------------------------------------------------------------------------

class TestCalculateCGroupAdjustmentCapacity:
    def test_headroom_available(self):
        result = calculate_c_adjustment_capacity(
            _make_rolling_los_result(18.0),
            guardrail_los_limit=21.0,
        )
        assert result["headroom_days"] == 3.0
        assert result["can_delay_discharge"] is True
        assert result["status"] == "余力あり"

    def test_headroom_tight(self):
        result = calculate_c_adjustment_capacity(
            _make_rolling_los_result(20.5),
            guardrail_los_limit=21.0,
        )
        assert result["headroom_days"] == 0.5
        assert result["status"] == "余力わずか"

    def test_no_headroom(self):
        result = calculate_c_adjustment_capacity(
            _make_rolling_los_result(22.0),
            guardrail_los_limit=21.0,
        )
        assert result["headroom_days"] == -1.0
        assert result["can_delay_discharge"] is False
        assert result["status"] == "余力なし"
        assert result["warning_message"] is not None


# ---------------------------------------------------------------------------
# TestSimulateCGroupScenario
# ---------------------------------------------------------------------------

class TestSimulateCGroupScenario:
    def test_delay_increases_los(self):
        result = simulate_c_group_scenario(
            _make_rolling_los_result(18.0),
            guardrail_los_limit=21.0,
            n_delay=3,
            delay_days=2,
        )
        assert result["simulated_los"] > result["original_los"]
        assert result["los_delta"] > 0

    def test_within_guardrail(self):
        result = simulate_c_group_scenario(
            _make_rolling_los_result(18.0),
            guardrail_los_limit=21.0,
            n_delay=1,
            delay_days=1,
        )
        assert result["within_guardrail"] is True


# ---------------------------------------------------------------------------
# TestCalculateDemandAbsorption
# ---------------------------------------------------------------------------

class TestCalculateDemandAbsorption:
    def test_quiet_period_c_keep(self):
        capacity = calculate_c_adjustment_capacity(
            _make_rolling_los_result(18.0),
            guardrail_los_limit=21.0,
        )
        result = calculate_demand_absorption(
            c_adjustment_capacity=capacity,
            demand_trend="decreasing",
            occupancy_rate=0.85,
            target_occupancy=0.90,
        )
        assert result["recommendation"] == "C群キープ推奨"


# ---------------------------------------------------------------------------
# TestGenerateCGroupAlerts
# ---------------------------------------------------------------------------

class TestGenerateCGroupAlerts:
    def test_danger_on_exceed(self):
        c_summary = {"c_count": 10, "c_ratio": 20.0}
        c_capacity = {"headroom_days": -1.0}
        alerts = generate_c_group_alerts(c_summary, c_capacity, "normal")
        danger_alerts = [a for a in alerts if a["level"] == "danger"]
        assert len(danger_alerts) >= 1

    def test_info_on_quiet_headroom(self):
        c_summary = {"c_count": 5, "c_ratio": 10.0}
        c_capacity = {"headroom_days": 3.0}
        alerts = generate_c_group_alerts(c_summary, c_capacity, "quiet")
        info_alerts = [a for a in alerts if a["level"] == "info"]
        assert len(info_alerts) >= 1
