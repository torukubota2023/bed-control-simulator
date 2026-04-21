"""退院ヒートマップ計算モジュール (discharge_heatmap.py) のテスト。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

import pytest

from scripts.discharge_heatmap import (
    C_GROUP_LOS_THRESHOLD,
    DEFAULT_DAYS_AHEAD,
    MAX_DAYS_AHEAD_WITH_HOLIDAY,
    SEVERITY_DANGER_COUNT,
    SEVERITY_WARNING_COUNT,
    _parse_planned_date,
    classify_cell_severity,
    compute_discharge_heatmap_from_patients,
    compute_period_end,
)


# ---------------------------------------------------------------------------
# ダミー患者クラス
# ---------------------------------------------------------------------------


@dataclass
class _DummyPatient:
    patient_id: str
    day_count: int
    planned_date: str
    doctor_surname: str = ""
    status_key: str = "new"


# ---------------------------------------------------------------------------
# _parse_planned_date
# ---------------------------------------------------------------------------


class TestParsePlannedDate:
    def test_md_with_dow(self):
        """`4/24 (金)` 形式をパースする。"""
        ref = date(2026, 4, 21)
        assert _parse_planned_date("4/24 (金)", ref) == date(2026, 4, 24)

    def test_md_only(self):
        """`5/1` 形式をパースする。"""
        ref = date(2026, 4, 21)
        assert _parse_planned_date("5/1", ref) == date(2026, 5, 1)

    def test_iso_format(self):
        """`2026-04-24` 形式をパースする。"""
        ref = date(2026, 4, 21)
        assert _parse_planned_date("2026-04-24", ref) == date(2026, 4, 24)

    def test_year_inference_next_year(self):
        """1 月の日付が 10 月基準なら翌年扱い。"""
        ref = date(2026, 10, 15)
        assert _parse_planned_date("1/5", ref) == date(2027, 1, 5)

    def test_undetermined_returns_none(self):
        """"未定" / 空文字は None を返す。"""
        ref = date(2026, 4, 21)
        assert _parse_planned_date("未定", ref) is None
        assert _parse_planned_date("", ref) is None
        assert _parse_planned_date("-", ref) is None


# ---------------------------------------------------------------------------
# compute_period_end
# ---------------------------------------------------------------------------


class TestComputePeriodEnd:
    def test_no_holiday_returns_base(self):
        """連休がない場合は today + days_ahead。"""
        today = date(2026, 4, 21)
        end, extended = compute_period_end(today, days_ahead=14)
        assert end == date(2026, 5, 5)
        assert not extended

    def test_holiday_within_window_extends(self):
        """連休末が 14-21 日以内なら連休末まで延長される。"""
        today = date(2026, 4, 21)
        end, extended = compute_period_end(
            today, days_ahead=14,
            holiday_start=date(2026, 5, 2),
            holiday_end=date(2026, 5, 6),
        )
        # 連休末 5/6 は today+15。base_end 5/5 より先 → 延長
        assert end == date(2026, 5, 6)
        assert extended

    def test_holiday_already_within_base_no_extension(self):
        """連休末が base_end 以内なら延長不要。"""
        today = date(2026, 4, 21)
        end, extended = compute_period_end(
            today, days_ahead=14,
            holiday_start=date(2026, 4, 29),
            holiday_end=date(2026, 5, 3),
        )
        # 連休末 5/3 < base_end 5/5 → 延長なし
        assert end == date(2026, 5, 5)
        assert not extended

    def test_holiday_beyond_max_clamps(self):
        """連休末が max_days_ahead を超える場合は clamp される。"""
        today = date(2026, 4, 21)
        end, extended = compute_period_end(
            today, days_ahead=14,
            holiday_start=date(2026, 5, 2),
            holiday_end=date(2026, 5, 15),  # today + 24日 (max=21)
            max_days_ahead=21,
        )
        # max_end = today + 21 = 5/12
        assert end == date(2026, 5, 12)
        assert extended

    def test_holiday_after_base_end_no_impact(self):
        """連休が base_end より後なら影響なし。"""
        today = date(2026, 4, 21)
        end, extended = compute_period_end(
            today, days_ahead=14,
            holiday_start=date(2026, 6, 1),
            holiday_end=date(2026, 6, 5),
        )
        assert end == date(2026, 5, 5)
        assert not extended


# ---------------------------------------------------------------------------
# classify_cell_severity
# ---------------------------------------------------------------------------


class TestClassifyCellSeverity:
    def test_zero_is_empty(self):
        assert classify_cell_severity(0) == "empty"

    def test_one_to_three_is_ok(self):
        assert classify_cell_severity(1) == "ok"
        assert classify_cell_severity(2) == "ok"
        assert classify_cell_severity(3) == "ok"

    def test_four_is_warn(self):
        assert classify_cell_severity(4) == "warn"

    def test_five_plus_is_danger(self):
        assert classify_cell_severity(5) == "danger"
        assert classify_cell_severity(10) == "danger"


# ---------------------------------------------------------------------------
# compute_discharge_heatmap_from_patients (統合)
# ---------------------------------------------------------------------------


class TestComputeDischargeHeatmap:
    def test_empty_patients_returns_all_empty_cells(self):
        """患者が 0 人なら、すべての日が空セルで返る。"""
        today = date(2026, 4, 21)
        result = compute_discharge_heatmap_from_patients([], today)
        assert len(result["cells"]) == 14  # 翌日から 14 日
        assert all(c["total"] == 0 for c in result["cells"])
        assert result["grand_total"] == 0
        assert result["grand_c_group"] == 0

    def test_period_respects_holiday_extension(self):
        """連休があれば period_end が延長される。"""
        today = date(2026, 4, 21)
        result = compute_discharge_heatmap_from_patients(
            [], today,
            holiday_start=date(2026, 5, 2),
            holiday_end=date(2026, 5, 6),
        )
        assert result["extended_for_holiday"] is True
        assert result["period_end"] == "2026-05-06"
        # 翌日 4/22 から 5/6 まで = 15 日
        assert result["total_days"] == 15

    def test_c_group_classification(self):
        """day_count + 残日数 ≥ 15 の患者が C 群としてカウントされる。"""
        today = date(2026, 4, 21)
        patients = [
            # Day 10、退院 4/25（+4 日）→ LOS 14（C群未満）
            _DummyPatient("p1", 10, "4/25", "田中"),
            # Day 12、退院 4/25（+4 日）→ LOS 16（C群）
            _DummyPatient("p2", 12, "4/25", "高橋"),
            # Day 20、退院 4/25（+4 日）→ LOS 24（C群）
            _DummyPatient("p3", 20, "4/25", "中村"),
        ]
        result = compute_discharge_heatmap_from_patients(patients, today)
        # 4/25 のセル
        apr25 = next(c for c in result["cells"] if c["date"] == "2026-04-25")
        assert apr25["total"] == 3
        assert apr25["c_group"] == 2
        assert set(apr25["c_group_patient_ids"]) == {"p2", "p3"}
        assert set(apr25["c_group_patient_names"]) == {"高橋", "中村"}

    def test_severity_danger_threshold(self):
        """1 日に 5 人退院予定 → severity=danger。"""
        today = date(2026, 4, 21)
        patients = [
            _DummyPatient(f"p{i}", 20, "4/25") for i in range(5)
        ]
        result = compute_discharge_heatmap_from_patients(patients, today)
        apr25 = next(c for c in result["cells"] if c["date"] == "2026-04-25")
        assert apr25["total"] == 5
        assert apr25["severity"] == "danger"
        assert len(result["concentrated_days"]) == 1
        assert result["concentrated_days"][0]["date"] == "2026-04-25"

    def test_severity_warn_threshold(self):
        """4 人で warn。"""
        today = date(2026, 4, 21)
        patients = [
            _DummyPatient(f"p{i}", 10, "4/25") for i in range(4)
        ]
        result = compute_discharge_heatmap_from_patients(patients, today)
        apr25 = next(c for c in result["cells"] if c["date"] == "2026-04-25")
        assert apr25["severity"] == "warn"
        assert len(result["warning_days"]) == 1

    def test_undetermined_patients_excluded(self):
        """planned_date="未定" の患者はヒートマップに乗らない。"""
        today = date(2026, 4, 21)
        patients = [
            _DummyPatient("p1", 20, "未定"),
            _DummyPatient("p2", 20, "4/25"),
        ]
        result = compute_discharge_heatmap_from_patients(patients, today)
        # total は 1 のみ
        assert result["grand_total"] == 1
        apr25 = next(c for c in result["cells"] if c["date"] == "2026-04-25")
        assert apr25["total"] == 1
        assert apr25["patient_ids"] == ["p2"]

    def test_weekend_and_holiday_flags(self):
        """土日・連休フラグが正しくセルに付く。"""
        today = date(2026, 4, 21)  # 火
        result = compute_discharge_heatmap_from_patients(
            [], today,
            holiday_start=date(2026, 5, 2),
            holiday_end=date(2026, 5, 6),
        )
        # 4/25 は土曜日
        sat = next(c for c in result["cells"] if c["date"] == "2026-04-25")
        assert sat["is_weekend"] is True
        assert sat["is_holiday"] is False
        # 5/4 は連休中（月曜でもあるが is_weekend=False）
        may4 = next((c for c in result["cells"] if c["date"] == "2026-05-04"), None)
        assert may4 is not None
        assert may4["is_holiday"] is True

    def test_empty_days_listed(self):
        """退院予定が 0 名の日が empty_days として収集される。"""
        today = date(2026, 4, 21)
        patients = [
            _DummyPatient("p1", 20, "4/25"),  # 1 日だけに集中
        ]
        result = compute_discharge_heatmap_from_patients(patients, today)
        # 14 日のうち 1 日だけ total>0、残り 13 日は empty
        assert len(result["empty_days"]) == 13

    def test_patients_outside_window_ignored(self):
        """期間外の退院予定は無視される。"""
        today = date(2026, 4, 21)
        patients = [
            _DummyPatient("p1", 20, "6/1"),  # 期間外
            _DummyPatient("p2", 20, "4/25"),  # 期間内
        ]
        result = compute_discharge_heatmap_from_patients(patients, today)
        assert result["grand_total"] == 1
