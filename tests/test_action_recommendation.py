"""
テスト: action_recommendation モジュール — 結論カード・KPI優先リスト・トレードオフ評価

generate_action_card / generate_kpi_priority_list / generate_tradeoff_assessment の
入出力を検証する。
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from action_recommendation import (
    generate_action_card,
    generate_kpi_priority_list,
    generate_tradeoff_assessment,
)


# ===================================================================
# generate_action_card
# ===================================================================


class TestGenerateActionCard:
    """generate_action_card の優先順位ロジックを検証する。"""

    def test_empty_data_returns_success(self):
        """全 None 入力 → level='success'（正常運用）"""
        card = generate_action_card()
        assert card["level"] == "success"
        assert "title" in card
        assert "actions" in card
        assert card["color"] == "green"

    def test_emergency_danger_returns_critical(self):
        """救急 overall_status='danger' + additional_needed > 0 → level='critical'"""
        emergency = {
            "overall_status": "danger",
            "alerts": [],
            "5F": {
                "dual_ratio": {"operational": {"ratio_pct": 10.0}, "official": {"ratio_pct": 10.0, "status": "red"}},
                "additional": {"additional_needed": 5},
            },
        }
        card = generate_action_card(emergency_summary=emergency)
        assert card["level"] == "critical"
        assert card["color"] == "red"
        assert "救急" in card["priority_source"]

    def test_emergency_warning_returns_warning(self):
        """救急 overall_status='warning' → level が少なくとも 'warning'"""
        emergency = {
            "overall_status": "warning",
            "alerts": [],
            "5F": {
                "dual_ratio": {"operational": {"ratio_pct": 14.0}, "official": {"ratio_pct": 14.0, "status": "yellow"}},
                "additional": {"additional_needed": 2},
            },
        }
        card = generate_action_card(emergency_summary=emergency)
        assert card["level"] in ("warning", "critical")

    def test_guardrail_danger_returns_critical(self):
        """施設基準チェック status='danger' → level='critical'"""
        guardrail = [
            {"name": "平均在院日数", "status": "danger", "value": 25.0},
        ]
        card = generate_action_card(guardrail_status=guardrail)
        assert card["level"] == "critical"
        assert "施設基準チェック" in card["priority_source"]

    def test_occupancy_below_target_returns_warning(self):
        """稼働率 0.85 < 目標 0.90 → level='warning'"""
        card = generate_action_card(
            occupancy_rate=0.85,
            target_occupancy=0.90,
        )
        assert card["level"] == "warning"
        assert "稼働率" in card["priority_source"]

    def test_morning_capacity_low_returns_warning(self):
        """翌朝受入余力 estimated_emergency_slots=1 → level='warning'"""
        morning = {"estimated_emergency_slots": 1}
        card = generate_action_card(morning_capacity=morning)
        assert card["level"] == "warning"
        assert "翌" in card["priority_source"] or "受入" in card["priority_source"]

    def test_los_headroom_low_returns_warning(self):
        """LOS余力 headroom_days=1.0 → level='warning'"""
        los = {"headroom_days": 1.0, "current_los": 19.0, "limit_los": 20.0}
        card = generate_action_card(los_headroom=los)
        assert card["level"] == "warning"
        assert "LOS" in card["priority_source"] or "余力" in card["priority_source"]

    def test_emergency_takes_priority_over_occupancy(self):
        """救急 danger と稼働率低下が両方ある場合 → priority_source に '救急' を含む"""
        emergency = {
            "overall_status": "danger",
            "alerts": [],
            "5F": {
                "dual_ratio": {"operational": {"ratio_pct": 8.0}, "official": {"ratio_pct": 8.0, "status": "red"}},
                "additional": {"additional_needed": 10},
            },
        }
        card = generate_action_card(
            emergency_summary=emergency,
            occupancy_rate=0.80,
            target_occupancy=0.90,
        )
        assert "救急" in card["priority_source"]


# ===================================================================
# generate_kpi_priority_list
# ===================================================================


class TestGenerateKpiPriorityList:
    """generate_kpi_priority_list のリスト構造を検証する。"""

    def test_kpi_priority_list_returns_6_items(self):
        """空データでも常に6個のKPIを返す"""
        items = generate_kpi_priority_list()
        assert len(items) == 6

    def test_kpi_priority_list_ordered_by_rank(self):
        """rank が 1-6 の順序になっている"""
        items = generate_kpi_priority_list()
        ranks = [item["rank"] for item in items]
        assert ranks == [1, 2, 3, 4, 5, 6]

    def test_kpi_items_have_required_keys(self):
        """各 KPI アイテムが必要なキーを持つ"""
        items = generate_kpi_priority_list()
        required_keys = {"name", "value", "status", "rank", "explanation"}
        for item in items:
            assert required_keys.issubset(item.keys()), (
                f"Missing keys in item: {required_keys - item.keys()}"
            )


# ===================================================================
# generate_tradeoff_assessment
# ===================================================================


class TestGenerateTradeoffAssessment:
    """generate_tradeoff_assessment のトレードオフ判定を検証する。"""

    def test_tradeoff_emergency_risk_recommends_release(self):
        """救急搬送比率リスクあり → recommendation='release'"""
        emergency = {"overall_status": "danger"}
        result = generate_tradeoff_assessment(emergency_summary=emergency)
        assert result["recommendation"] == "release"
        assert result["emergency_priority"] is True

    def test_tradeoff_safe_with_capacity_recommends_keep(self):
        """全指標安全 + C群 capacity あり → recommendation='keep'"""
        c_cap = {"can_delay": True, "absorbable_beds": 3, "daily_contribution": 28900}
        los = {"headroom_days": 5.0, "current_los": 15.0, "limit_los": 20.0}
        emergency = {"overall_status": "safe"}
        morning = {"estimated_emergency_slots": 5}

        result = generate_tradeoff_assessment(
            c_adjustment_capacity=c_cap,
            emergency_summary=emergency,
            morning_capacity=morning,
            los_headroom=los,
        )
        assert result["recommendation"] == "keep"
        assert result["emergency_priority"] is False

    def test_tradeoff_partial_data_doesnt_crash(self):
        """一部の入力のみ → クラッシュしない"""
        result = generate_tradeoff_assessment(
            los_headroom={"headroom_days": 3.0},
        )
        assert "recommendation" in result
        assert "reasoning" in result
        assert "impacts" in result
        assert result["recommendation"] in ("keep", "release", "neutral")
