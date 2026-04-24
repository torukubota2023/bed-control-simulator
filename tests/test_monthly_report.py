"""月次ベッドコントロールレポート生成のテスト."""
from __future__ import annotations

import os
import sys
from datetime import date
from typing import Any, Dict

import pytest

_SCRIPTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "scripts")
)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import generate_monthly_bed_control_report as mbr  # noqa: E402


def _mock_kpis(overrides: Dict[str, Any] = None) -> Dict[str, Any]:
    """標準的な KPI dict を返す（テスト用）."""
    base = {
        "period": "2026-04",
        "total_days_in_month": 30,
        "month_start": date(2026, 4, 1),
        "month_end": date(2026, 4, 30),
        "total_plans": 10,
        "overflow_days_by_ward": {"5F": 0, "6F": 0},
        "overflow_total_by_ward": {"5F": 0, "6F": 0},
        "total_discharges_by_ward": {"5F": 5, "6F": 5},
        "sunday_discharges_by_ward": {"5F": 1, "6F": 0},
        "unplanned_total": 0,
        "unplanned_by_doctor": {},
        "fixed_total": 0,
        "fixed_by_reason": {},
    }
    if overrides:
        base.update(overrides)
    return base


class TestCalcMonthKpis:
    """KPI 計算の単体テスト."""

    def test_empty_plans(self):
        result = mbr.calc_month_kpis(
            year=2026, month=4, plans={}, ward_map={}, doctor_map={},
        )
        assert result["total_plans"] == 0
        assert result["overflow_days_by_ward"] == {"5F": 0, "6F": 0}
        assert result["unplanned_total"] == 0
        assert result["fixed_total"] == 0

    def test_counts_all_plans_passed(self):
        """calc_month_kpis は渡された plans を全て集計する（月フィルタは
        collect_plans_for_month 側の責務）."""
        plans = {
            "p001": {"scheduled_date": "2026-04-15", "confirmed": True, "unplanned": False},
            "p002": {"scheduled_date": "2026-04-20", "confirmed": False, "unplanned": False},
            "p003": {"scheduled_date": "2026-04-20", "confirmed": False, "unplanned": False},
        }
        ward_map = {"p001": "5F", "p002": "5F", "p003": "5F"}
        result = mbr.calc_month_kpis(
            year=2026, month=4, plans=plans, ward_map=ward_map, doctor_map={},
        )
        assert result["total_discharges_by_ward"]["5F"] == 3

    def test_overflow_detection_weekday(self):
        # 2026-04-27 (月) に 6 名 → 枠 5 超過 +1
        plans = {
            f"p{i:03d}": {
                "scheduled_date": "2026-04-27",
                "confirmed": True,
                "unplanned": False,
            }
            for i in range(6)
        }
        ward_map = {k: "5F" for k in plans}
        result = mbr.calc_month_kpis(
            year=2026, month=4, plans=plans, ward_map=ward_map, doctor_map={},
        )
        assert result["overflow_days_by_ward"]["5F"] == 1
        assert result["overflow_total_by_ward"]["5F"] == 1

    def test_sunday_discharge_counted(self):
        # 2026-04-26 (日) に 1 名
        plans = {
            "p001": {"scheduled_date": "2026-04-26", "confirmed": True, "unplanned": False},
        }
        ward_map = {"p001": "5F"}
        result = mbr.calc_month_kpis(
            year=2026, month=4, plans=plans, ward_map=ward_map, doctor_map={},
        )
        assert result["sunday_discharges_by_ward"]["5F"] == 1

    def test_unplanned_by_doctor(self):
        plans = {
            "p001": {"scheduled_date": "2026-04-15", "confirmed": True, "unplanned": True},
            "p002": {"scheduled_date": "2026-04-20", "confirmed": True, "unplanned": True},
            "p003": {"scheduled_date": "2026-04-22", "confirmed": True, "unplanned": False},
        }
        ward_map = {"p001": "5F", "p002": "5F", "p003": "6F"}
        doctor_map = {"p001": "Dr_A", "p002": "Dr_A", "p003": "Dr_B"}
        result = mbr.calc_month_kpis(
            year=2026, month=4, plans=plans,
            ward_map=ward_map, doctor_map=doctor_map,
        )
        assert result["unplanned_total"] == 2
        assert result["unplanned_by_doctor"]["Dr_A"] == 2

    def test_fixed_by_reason(self):
        plans = {
            "p001": {
                "scheduled_date": "2026-04-15", "confirmed": True,
                "unplanned": False, "movable_reason": "family",
            },
            "p002": {
                "scheduled_date": "2026-04-20", "confirmed": True,
                "unplanned": False, "movable_reason": "family",
            },
            "p003": {
                "scheduled_date": "2026-04-22", "confirmed": True,
                "unplanned": False, "movable_reason": "facility",
            },
        }
        ward_map = {k: "5F" for k in plans}
        result = mbr.calc_month_kpis(
            year=2026, month=4, plans=plans, ward_map=ward_map, doctor_map={},
        )
        assert result["fixed_total"] == 3
        assert result["fixed_by_reason"]["family"] == 2
        assert result["fixed_by_reason"]["facility"] == 1


class TestRenderMarkdown:
    """Markdown 生成の単体テスト."""

    def test_basic_structure(self):
        md = mbr.render_markdown(_mock_kpis())
        # 必須セクション
        assert "# 🏥 月次ベッドコントロール" in md
        assert "## 📊 病棟別サマリー" in md
        assert "## 🚨 枠超過の発生状況" in md
        assert "## ⭐ 日曜・祝日退院" in md
        assert "## ⚡ 突発退院" in md
        assert "## 🔒 日付固定患者" in md
        assert "## 💰 経営インパクト" in md
        assert "## 📝 来月への申し送り" in md

    def test_overflow_zero_message(self):
        md = mbr.render_markdown(_mock_kpis())
        assert "✅ **今月は枠超過が発生していません**" in md

    def test_overflow_nonzero_message(self):
        kpis = _mock_kpis({
            "overflow_days_by_ward": {"5F": 3, "6F": 0},
            "overflow_total_by_ward": {"5F": 5, "6F": 0},
        })
        md = mbr.render_markdown(kpis)
        assert "⚠️ 今月の枠超過" in md
        assert "合計 3 日" in md

    def test_unplanned_zero_message(self):
        md = mbr.render_markdown(_mock_kpis())
        assert "✅ **今月は突発退院の発生なし**" in md

    def test_japanese_month_label(self):
        md = mbr.render_markdown(_mock_kpis())
        assert "4月" in md  # 月の日本語ラベル
