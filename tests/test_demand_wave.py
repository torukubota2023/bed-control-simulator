"""demand_wave モジュールのテスト。"""

import pandas as pd
import pytest
from datetime import date, timedelta

from demand_wave import (
    calculate_demand_trend,
    classify_demand_period,
    calculate_dow_pattern,
    calculate_demand_score,
    detect_demand_alerts,
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


# ---------------------------------------------------------------------------
# TestCalculateDemandTrend
# ---------------------------------------------------------------------------

class TestCalculateDemandTrend:
    def test_stable_trend(self):
        df = _make_daily_df(30)
        result = calculate_demand_trend(df)
        assert result["trend_label"] == "stable"
        assert 0.85 <= result["trend_ratio"] <= 1.15

    def test_decreasing_trend(self):
        df = _make_daily_df(30)
        # 直近1週間の入院数を半分にする
        df["date"] = pd.to_datetime(df["date"])
        max_date = df["date"].max()
        last_1w_mask = df["date"] >= (max_date - timedelta(days=6))
        df.loc[last_1w_mask, "new_admissions"] = df.loc[last_1w_mask, "new_admissions"] // 2
        df["date"] = df["date"].dt.strftime("%Y-%m-%d")
        result = calculate_demand_trend(df)
        assert result["trend_label"] == "decreasing"

    def test_empty_df(self):
        df = pd.DataFrame(columns=["date", "ward", "total_patients", "new_admissions", "discharges"])
        result = calculate_demand_trend(df)
        assert result["data_days"] == 0
        assert result["trend_label"] == "stable"


# ---------------------------------------------------------------------------
# TestClassifyDemandPeriod
# ---------------------------------------------------------------------------

class TestClassifyDemandPeriod:
    def test_normal_period(self):
        df = _make_daily_df(30)
        result = classify_demand_period(df)
        assert result["classification"] in ("normal", "busy", "quiet")

    def test_short_data(self):
        df = _make_daily_df(7)
        result = classify_demand_period(df)
        assert result["confidence"] == "low"


# ---------------------------------------------------------------------------
# TestCalculateDowPattern
# ---------------------------------------------------------------------------

class TestCalculateDowPattern:
    def test_always_7_rows(self):
        df = _make_daily_df(30)
        result = calculate_dow_pattern(df)
        assert len(result) == 7


# ---------------------------------------------------------------------------
# TestDetectDemandAlerts
# ---------------------------------------------------------------------------

class TestDetectDemandAlerts:
    def test_decreasing_generates_warning(self):
        df = _make_daily_df(30)
        # 直近1週間を入院ゼロにする
        df["date"] = pd.to_datetime(df["date"])
        max_date = df["date"].max()
        last_1w_mask = df["date"] >= (max_date - timedelta(days=6))
        df.loc[last_1w_mask, "new_admissions"] = 0
        df["date"] = df["date"].dt.strftime("%Y-%m-%d")

        alerts = detect_demand_alerts(df)
        trend_alerts = [a for a in alerts if a.get("metric") == "trend"]
        assert len(trend_alerts) >= 1
        assert trend_alerts[0]["level"] == "warning"


# ---------------------------------------------------------------------------
# TestCalculateDemandScore
# ---------------------------------------------------------------------------

class TestCalculateDemandScore:
    def test_score_range(self):
        df = _make_daily_df(30)
        result = calculate_demand_score(df)
        assert 0 <= result["score_14d"] <= 100
        assert 0 <= result["score_30d"] <= 100
