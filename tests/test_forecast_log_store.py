"""退院カレンダー予測ログ store のテスト."""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import forecast_log_store  # noqa: E402
from forecast_log_store import (  # noqa: E402
    HIT_RATE_TOLERANCE,
    build_actual_inpatients_map,
    compare_with_actuals,
    estimate_dow_stats,
    load_all_snapshots,
    save_forecast_snapshot,
)


@pytest.fixture
def tmp_snapshot_dir(tmp_path, monkeypatch):
    """SNAPSHOT_DIR を一時ディレクトリに差し替え."""
    target = tmp_path / "forecast_snapshots"
    monkeypatch.setattr(forecast_log_store, "SNAPSHOT_DIR", target)
    return target


def _make_forecast(start: date, n_days: int) -> list[dict]:
    """ダミー予測データを生成."""
    return [
        {
            "date": start + timedelta(days=i),
            "inpatients": 40.0 + i * 0.5,
            "occupancy": 85.0 + i * 0.3,
        }
        for i in range(n_days)
    ]


class TestSaveForecast:
    def test_save_and_load(self, tmp_snapshot_dir):
        forecast = _make_forecast(date(2026, 4, 25), 7)
        ok = save_forecast_snapshot(
            ward="5F", forecast=forecast, total_beds=47,
            generated_at=datetime(2026, 4, 24, 12, 0),
        )
        assert ok
        snapshots = load_all_snapshots()
        assert len(snapshots) == 1
        assert snapshots[0]["ward"] == "5F"
        assert snapshots[0]["total_beds"] == 47
        assert snapshots[0]["horizon_days"] == 7
        assert len(snapshots[0]["items"]) == 7

    def test_empty_forecast_not_saved(self, tmp_snapshot_dir):
        ok = save_forecast_snapshot(
            ward="5F", forecast=[], total_beds=47,
        )
        assert not ok
        assert load_all_snapshots() == []

    def test_ward_filter(self, tmp_snapshot_dir):
        save_forecast_snapshot(
            ward="5F", forecast=_make_forecast(date(2026, 4, 25), 3), total_beds=47,
            generated_at=datetime(2026, 4, 24),
        )
        save_forecast_snapshot(
            ward="6F", forecast=_make_forecast(date(2026, 4, 25), 3), total_beds=47,
            generated_at=datetime(2026, 4, 24),
        )
        assert len(load_all_snapshots()) == 2
        assert len(load_all_snapshots(ward="5F")) == 1
        assert load_all_snapshots(ward="5F")[0]["ward"] == "5F"


class TestCompareWithActuals:
    def test_empty(self):
        assert compare_with_actuals([], {}) == {"by_ward": {}, "total_comparisons": 0}

    def test_perfect_prediction(self, tmp_snapshot_dir):
        # 予測値 = 実績値 → MAPE = 0、bias = 0、hit = 100%
        forecast = _make_forecast(date(2026, 4, 25), 5)
        save_forecast_snapshot(
            ward="5F", forecast=forecast, total_beds=47,
            generated_at=datetime(2026, 4, 24),
        )
        actuals = {
            r["date"].isoformat(): {"5F": r["inpatients"]}
            for r in forecast
        }
        result = compare_with_actuals(load_all_snapshots(), actuals)
        assert result["by_ward"]["5F"]["mape"] == 0.0
        assert result["by_ward"]["5F"]["bias"] == 0.0
        assert result["by_ward"]["5F"]["hit_rate_2"] == 100.0

    def test_systematic_overprediction(self, tmp_snapshot_dir):
        forecast = [
            {"date": date(2026, 4, 25), "inpatients": 42.0, "occupancy": 89.0},
            {"date": date(2026, 4, 26), "inpatients": 43.0, "occupancy": 91.0},
        ]
        save_forecast_snapshot(
            ward="5F", forecast=forecast, total_beds=47,
            generated_at=datetime(2026, 4, 24),
        )
        # 実績は各 -3 名 → bias = +3（過大予測）
        actuals = {
            "2026-04-25": {"5F": 39.0},
            "2026-04-26": {"5F": 40.0},
        }
        result = compare_with_actuals(load_all_snapshots(), actuals)
        assert result["by_ward"]["5F"]["bias"] == 3.0
        assert result["by_ward"]["5F"]["mae"] == 3.0
        # 絶対誤差 3 > tolerance 2 → hit_rate = 0
        assert result["by_ward"]["5F"]["hit_rate_2"] == 0.0

    def test_horizon_filter(self, tmp_snapshot_dir):
        forecast = _make_forecast(date(2026, 4, 25), 20)
        save_forecast_snapshot(
            ward="5F", forecast=forecast, total_beds=47,
            generated_at=datetime(2026, 4, 24),
        )
        actuals = {
            r["date"].isoformat(): {"5F": r["inpatients"]}
            for r in forecast
        }
        # horizon 1-14 のみ評価 → 14 日分
        result = compare_with_actuals(
            load_all_snapshots(), actuals,
            min_horizon_days=1, max_horizon_days=14,
        )
        assert result["by_ward"]["5F"]["n"] == 14


class TestEstimateDowStats:
    def test_empty(self):
        assert estimate_dow_stats({}) == {
            i: {"mean": 0.0, "std": 0.0, "n": 0} for i in range(7)
        }

    def test_mean_and_std(self):
        # 月曜日: [2, 4, 6] → mean=4, std>0
        daily = {
            date(2026, 4, 6): 2.0,    # 月
            date(2026, 4, 13): 4.0,   # 月
            date(2026, 4, 20): 6.0,   # 月
            date(2026, 4, 7): 3.0,    # 火
        }
        stats = estimate_dow_stats(daily)
        assert stats[0]["mean"] == 4.0
        assert stats[0]["std"] > 0
        assert stats[0]["n"] == 3
        assert stats[1]["mean"] == 3.0
        assert stats[1]["std"] == 0.0  # 1 点のみ
        assert stats[1]["n"] == 1


class TestBuildActualInpatientsMap:
    def test_empty_df(self):
        result = build_actual_inpatients_map(
            pd.DataFrame(), date(2026, 4, 1), date(2026, 4, 30),
        )
        assert result == {}

    def test_running_count(self):
        # 4/1 に 5F admission 2件、4/2 に discharge 1件、4/3 に admission 1件
        # → 4/1=2, 4/2=1, 4/3=2
        df = pd.DataFrame([
            {"event_type": "admission", "date": "2026-04-01", "ward": "5F"},
            {"event_type": "admission", "date": "2026-04-01", "ward": "5F"},
            {"event_type": "discharge", "date": "2026-04-02", "ward": "5F"},
            {"event_type": "admission", "date": "2026-04-03", "ward": "5F"},
        ])
        result = build_actual_inpatients_map(df, date(2026, 4, 1), date(2026, 4, 3))
        assert result["2026-04-01"]["5F"] == 2.0
        assert result["2026-04-02"]["5F"] == 1.0
        assert result["2026-04-03"]["5F"] == 2.0
