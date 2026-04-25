"""テスト: nursing_necessity_strategy — 2026看護必要度ギャップ管理."""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from nursing_necessity_strategy import (  # noqa: E402
    TARGET_NURSING_NECESSITY_I_PCT,
    build_nursing_necessity_actions,
    calculate_emergency_response_coefficient,
    estimate_intervention_gain_pct,
    summarize_nursing_necessity,
)


def _make_past_df(emergency_5f: int = 110, emergency_6f: int = 110) -> pd.DataFrame:
    rows = []
    rows.extend({"病棟": "5F", "is_emergency_transport": True} for _ in range(emergency_5f))
    rows.extend({"病棟": "5F", "is_emergency_transport": False} for _ in range(200))
    rows.extend({"病棟": "6F", "is_emergency_transport": True} for _ in range(emergency_6f))
    rows.extend({"病棟": "6F", "is_emergency_transport": False} for _ in range(200))
    return pd.DataFrame(rows)


def test_emergency_response_coefficient_matches_strategy_doc_example():
    """年間220件/94床なら約1.17pt、表示上は約1.2pt."""
    coeff = calculate_emergency_response_coefficient(220, 94)
    assert coeff == pytest.approx(1.17, abs=0.01)


def test_summarize_nursing_necessity_calculates_gap_by_ward():
    df = _make_past_df(emergency_5f=110, emergency_6f=110)
    rows = summarize_nursing_necessity(
        df,
        base_need_pct_by_ward={"5F": 16.0, "6F": 11.0},
        target_pct=TARGET_NURSING_NECESSITY_I_PCT,
    )
    by_ward = {row["ward"]: row for row in rows}

    assert by_ward["5F"]["emergency_coeff_pct"] == pytest.approx(1.17, abs=0.01)
    assert by_ward["5F"]["index_pct"] == pytest.approx(17.17, abs=0.01)
    assert by_ward["5F"]["gap_pct"] == pytest.approx(1.83, abs=0.01)
    assert by_ward["5F"]["status"] == "あと少し"

    assert by_ward["6F"]["index_pct"] == pytest.approx(12.17, abs=0.01)
    assert by_ward["6F"]["gap_pct"] == pytest.approx(6.83, abs=0.01)
    assert by_ward["6F"]["status"] == "緊急介入"


def test_summarize_accepts_raw_ambulance_column():
    df = pd.DataFrame([
        {"病棟": "5F", "救急車": "有り"},
        {"病棟": "5F", "救急車": "無し"},
        {"病棟": "6F", "救急車": "有り"},
    ])
    rows = summarize_nursing_necessity(
        df,
        base_need_pct_by_ward={"5F": 18.0, "6F": 18.0},
        period_months=12,
    )
    by_ward = {row["ward"]: row for row in rows}

    assert by_ward["5F"]["annual_emergency_count"] == 1
    assert by_ward["6F"]["annual_emergency_count"] == 1


def test_intervention_package_gain_is_broken_down_by_item():
    gain = estimate_intervention_gain_pct(
        c21_cases=8,
        c22_cases=5,
        c23_cases=2,
        a6_days=45,
        beds=47,
        occupancy_target=0.90,
    )

    assert gain["denominator_days"] == pytest.approx(1269.0, abs=0.1)
    assert gain["c21_days"] == 32
    assert gain["c22_days"] == 10
    assert gain["c23_days"] == 10
    assert gain["a6_days"] == 45
    assert gain["total_days"] == 97
    assert gain["total_gain_pct"] == pytest.approx(7.64, abs=0.01)


def test_actions_are_gap_sensitive_and_non_blaming():
    rows = [
        {"ward": "5F", "gap_pct": 1.8, "required_ac_days_per_month": 23.0, "status": "あと少し"},
        {"ward": "6F", "gap_pct": 6.8, "required_ac_days_per_month": 86.0, "status": "緊急介入"},
    ]
    actions = build_nursing_necessity_actions(rows)
    by_ward = {action["ward"]: action for action in actions}

    assert by_ward["5F"]["priority"] == "watch"
    assert by_ward["6F"]["priority"] == "urgent"
    all_text = " ".join(
        [action["message"] for action in actions]
        + [hint for action in actions for hint in action["next_actions"]]
    )
    assert "悪い" not in all_text
    assert "不必要な処置" not in all_text
