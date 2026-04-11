"""
共通テストフィクスチャ — ベッドコントロールシミュレーター用
"""
import pytest
import pandas as pd
import numpy as np
from datetime import date, timedelta


@pytest.fixture
def sample_two_ward_df():
    """同日の5F・6F 2行を持つDataFrame"""
    data = {
        "date": [pd.Timestamp("2026-04-01"), pd.Timestamp("2026-04-01")],
        "ward": pd.array(["5F", "6F"], dtype="string"),
        "total_patients": pd.array([40, 45], dtype="Int64"),
        "new_admissions": pd.array([3, 4], dtype="Int64"),
        "new_admissions_short3": pd.array([0, 0], dtype="Int64"),
        "discharges": pd.array([2, 3], dtype="Int64"),
        "discharge_a": pd.array([1, 1], dtype="Int64"),
        "discharge_b": pd.array([1, 1], dtype="Int64"),
        "discharge_c": pd.array([0, 1], dtype="Int64"),
        "discharge_los_list": pd.array(["3,10", "2,8,18"], dtype="string"),
        "phase_a_count": pd.array([8, 9], dtype="Int64"),
        "phase_b_count": pd.array([15, 17], dtype="Int64"),
        "phase_c_count": pd.array([17, 19], dtype="Int64"),
        "avg_los": pd.array([None, None], dtype="Float64"),
        "notes": pd.array(["", ""], dtype="string"),
    }
    return pd.DataFrame(data)


@pytest.fixture
def sample_multi_day_df():
    """複数日（5日分）の全病棟データ"""
    dates = [pd.Timestamp("2026-04-01") + timedelta(days=i) for i in range(5)]
    data = {
        "date": dates,
        "ward": pd.array(["all"] * 5, dtype="string"),
        "total_patients": pd.array([80, 82, 81, 83, 85], dtype="Int64"),
        "new_admissions": pd.array([5, 6, 4, 7, 5], dtype="Int64"),
        "new_admissions_short3": pd.array([0, 0, 0, 0, 0], dtype="Int64"),
        "discharges": pd.array([3, 4, 5, 5, 3], dtype="Int64"),
        "discharge_a": pd.array([1, 2, 2, 2, 1], dtype="Int64"),
        "discharge_b": pd.array([1, 1, 2, 2, 1], dtype="Int64"),
        "discharge_c": pd.array([1, 1, 1, 1, 1], dtype="Int64"),
        "discharge_los_list": pd.array(["", "", "", "", ""], dtype="string"),
        "phase_a_count": pd.array([15, 16, 14, 17, 16], dtype="Int64"),
        "phase_b_count": pd.array([30, 31, 32, 30, 33], dtype="Int64"),
        "phase_c_count": pd.array([35, 35, 35, 36, 36], dtype="Int64"),
        "avg_los": pd.array([None] * 5, dtype="Float64"),
        "notes": pd.array([""] * 5, dtype="string"),
    }
    return pd.DataFrame(data)


@pytest.fixture
def sample_90day_df():
    """90日分のデータ（rolling LOS計算用）"""
    n = 90
    rng = np.random.default_rng(42)
    dates = [pd.Timestamp("2026-01-01") + timedelta(days=i) for i in range(n)]
    total_patients = rng.integers(75, 90, size=n)
    new_admissions = rng.integers(3, 8, size=n)
    discharges = rng.integers(3, 8, size=n)
    data = {
        "date": dates,
        "ward": pd.array(["all"] * n, dtype="string"),
        "total_patients": pd.array(total_patients, dtype="Int64"),
        "new_admissions": pd.array(new_admissions, dtype="Int64"),
        "new_admissions_short3": pd.array([0] * n, dtype="Int64"),
        "discharges": pd.array(discharges, dtype="Int64"),
        "discharge_a": pd.array([1] * n, dtype="Int64"),
        "discharge_b": pd.array([1] * n, dtype="Int64"),
        "discharge_c": pd.array([1] * n, dtype="Int64"),
        "discharge_los_list": pd.array([""] * n, dtype="string"),
        "phase_a_count": pd.array([15] * n, dtype="Int64"),
        "phase_b_count": pd.array([30] * n, dtype="Int64"),
        "phase_c_count": pd.array([35] * n, dtype="Int64"),
        "avg_los": pd.array([None] * n, dtype="Float64"),
        "notes": pd.array([""] * n, dtype="string"),
    }
    return pd.DataFrame(data)
