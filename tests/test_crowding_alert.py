"""crowding_alert モジュールのテスト.

副院長指示 (2026-04-24): カンファ前警告機能の動作保証。
"""
from __future__ import annotations

import os
import sys
from datetime import date

import pytest

_SCRIPTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "scripts")
)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from crowding_alert import (  # noqa: E402
    detect_crowding_risk_days,
    summarize_risks,
)


def _make_plans(entries: list[tuple[str, str, str]]) -> dict:
    """[(uuid, scheduled_date_iso, status)] → plans dict."""
    plans = {}
    for uuid, iso, status in entries:
        plans[uuid] = {
            "scheduled_date": iso,
            "confirmed": (status == "confirmed"),
            "unplanned": (status == "unplanned"),
        }
    return plans


class TestDetectCrowdingRisk:
    """リスク検出ロジック."""

    def test_empty_plans_returns_empty(self):
        result = detect_crowding_risk_days(
            plans={}, ward_map={}, today=date(2026, 4, 24), days_ahead=7,
        )
        assert result == []

    def test_overflow_detected(self):
        # 5F に 6 名（枠 5 を超過）
        plans = _make_plans([
            (f"p00{i}", "2026-04-27", "scheduled") for i in range(1, 7)
        ])
        ward_map = {f"p00{i}": "5F" for i in range(1, 7)}
        result = detect_crowding_risk_days(
            plans=plans, ward_map=ward_map,
            today=date(2026, 4, 24), days_ahead=7,
        )
        assert len(result) >= 1
        assert result[0]["risk_level"] == "overflow"
        assert result[0]["date"] == date(2026, 4, 27)
        assert result[0]["scheduled"] == 6
        assert result[0]["slot"] == 5
        assert result[0]["excess"] == 1

    def test_full_detected(self):
        # 5F に 5 名（枠 5 ちょうど）
        plans = _make_plans([
            (f"p00{i}", "2026-04-27", "scheduled") for i in range(1, 6)
        ])
        ward_map = {f"p00{i}": "5F" for i in range(1, 6)}
        result = detect_crowding_risk_days(
            plans=plans, ward_map=ward_map,
            today=date(2026, 4, 24), days_ahead=7,
        )
        assert len(result) == 1
        assert result[0]["risk_level"] == "full"
        assert result[0]["scheduled"] == 5
        assert result[0]["excess"] == 0

    def test_tight_detected(self):
        # 5F に 4 名（枠 5 のうち 80% 超）
        plans = _make_plans([
            (f"p00{i}", "2026-04-27", "scheduled") for i in range(1, 5)
        ])
        ward_map = {f"p00{i}": "5F" for i in range(1, 5)}
        result = detect_crowding_risk_days(
            plans=plans, ward_map=ward_map,
            today=date(2026, 4, 24), days_ahead=7,
        )
        assert len(result) == 1
        assert result[0]["risk_level"] == "tight"
        assert result[0]["excess"] == -1  # 残 1

    def test_roomy_day_not_detected(self):
        # 5F に 2 名（余裕）
        plans = _make_plans([
            ("p001", "2026-04-27", "scheduled"),
            ("p002", "2026-04-27", "scheduled"),
        ])
        ward_map = {"p001": "5F", "p002": "5F"}
        result = detect_crowding_risk_days(
            plans=plans, ward_map=ward_map,
            today=date(2026, 4, 24), days_ahead=7,
        )
        assert result == []

    def test_sunday_tight_detected(self):
        # 日曜（枠 2）に 2 名 = 満杯
        # 2026-04-26 は日曜
        plans = _make_plans([
            ("p001", "2026-04-26", "scheduled"),
            ("p002", "2026-04-26", "scheduled"),
        ])
        ward_map = {"p001": "5F", "p002": "5F"}
        result = detect_crowding_risk_days(
            plans=plans, ward_map=ward_map,
            today=date(2026, 4, 24), days_ahead=7,
        )
        assert len(result) == 1
        assert result[0]["risk_level"] == "full"
        assert result[0]["slot"] == 2

    def test_holiday_uses_holiday_slot(self):
        # 2026-04-29 (水) を祝日指定
        holiday = {date(2026, 4, 29)}
        plans = _make_plans([
            ("p001", "2026-04-29", "scheduled"),
            ("p002", "2026-04-29", "scheduled"),
        ])
        ward_map = {"p001": "5F", "p002": "5F"}
        result = detect_crowding_risk_days(
            plans=plans, ward_map=ward_map,
            today=date(2026, 4, 24), days_ahead=7,
            jp_holidays=holiday,
        )
        assert len(result) == 1
        assert result[0]["slot"] == 2  # 祝日枠

    def test_sorted_by_risk_level(self):
        # overflow (5F 4/27), full (6F 4/28), tight (5F 4/29)
        plans = _make_plans(
            [(f"o{i}", "2026-04-27", "scheduled") for i in range(1, 7)]  # overflow 6/5
            + [(f"f{i}", "2026-04-28", "scheduled") for i in range(1, 6)]  # full 5/5
            + [(f"t{i}", "2026-04-29", "scheduled") for i in range(1, 5)]  # tight 4/5
        )
        ward_map = {}
        for key in plans:
            ward_map[key] = "5F" if key.startswith("o") or key.startswith("t") else "6F"

        result = detect_crowding_risk_days(
            plans=plans, ward_map=ward_map,
            today=date(2026, 4, 24), days_ahead=7, max_results=10,
        )
        levels = [r["risk_level"] for r in result]
        assert levels == ["overflow", "full", "tight"]

    def test_max_results_respected(self):
        # 10 日ぶんの超過を作って max_results=3 を検証
        entries = []
        ward_map = {}
        for d in range(25, 30):  # 4/25〜4/29
            iso = f"2026-04-{d:02d}"
            for i in range(6):  # 6 名 > 枠 5
                uid = f"u{d}_{i}"
                entries.append((uid, iso, "scheduled"))
                ward_map[uid] = "5F"
        plans = _make_plans(entries)
        result = detect_crowding_risk_days(
            plans=plans, ward_map=ward_map,
            today=date(2026, 4, 24), days_ahead=7, max_results=3,
        )
        assert len(result) == 3

    def test_days_ahead_boundary(self):
        # days_ahead=2 で 4/26 までをチェック、4/27 の overflow は検出されない
        plans = _make_plans([
            (f"p{i}", "2026-04-27", "scheduled") for i in range(1, 7)
        ])
        ward_map = {f"p{i}": "5F" for i in range(1, 7)}
        result = detect_crowding_risk_days(
            plans=plans, ward_map=ward_map,
            today=date(2026, 4, 24), days_ahead=2,
        )
        assert result == []  # 4/27 は範囲外


class TestSummarizeRisks:
    """サマリー集計."""

    def test_empty(self):
        assert summarize_risks([]) == {"overflow": 0, "full": 0, "tight": 0}

    def test_counts_by_level(self):
        risks = [
            {"risk_level": "overflow"},
            {"risk_level": "overflow"},
            {"risk_level": "full"},
            {"risk_level": "tight"},
            {"risk_level": "tight"},
            {"risk_level": "tight"},
        ]
        result = summarize_risks(risks)
        assert result == {"overflow": 2, "full": 1, "tight": 3}

    def test_unknown_level_ignored(self):
        risks = [{"risk_level": "xyz"}, {"risk_level": "overflow"}]
        result = summarize_risks(risks)
        assert result == {"overflow": 1, "full": 0, "tight": 0}
