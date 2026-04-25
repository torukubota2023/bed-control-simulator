"""テスト: nursing_necessity_strategy — 2026看護必要度ギャップ管理."""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from nursing_necessity_strategy import (  # noqa: E402
    DEFAULT_6F_STRATEGY_PACKAGE,
    TARGET_NURSING_NECESSITY_I_PCT,
    build_6f_strategy_cards,
    build_nursing_necessity_actions,
    build_patient_day_conversion_rows,
    build_physician_case_matching_rows,
    calculate_6f_action_mix,
    calculate_emergency_response_coefficient,
    estimate_intervention_gain_pct,
    simulate_strategy_package,
    summarize_actual_necessity_gaps,
    summarize_monthly_admission_volume,
    summarize_nursing_necessity,
    summarize_ward_case_mix,
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


def test_actual_necessity_gap_summary_translates_gap_to_patient_days():
    rows = []
    specs = [
        ("2025-12-01", 190, 170),
        ("2026-01-01", 100, 80),
        ("2026-02-01", 100, 80),
        ("2026-03-01", 100, 80),
    ]
    for date_str, i_pass, ii_pass in specs:
        rows.append({
            "date": date_str,
            "ward": "6F",
            "I_total": 1000,
            "I_pass1": i_pass,
            "II_total": 1000,
            "II_pass1": ii_pass,
        })
    df = pd.DataFrame(rows)

    summary = summarize_actual_necessity_gaps(
        df,
        ward="6F",
        emergency_coefficient_pct=1.5,
        recent_months=3,
    )
    by_scope_type = {(row["scope"], row["necessity_type"]): row for row in summary}

    recent_i = by_scope_type[("直近3ヶ月", "I")]
    assert recent_i["rate_pct"] == pytest.approx(10.0)
    assert recent_i["index_pct"] == pytest.approx(11.5)
    assert recent_i["gap_pct"] == pytest.approx(7.5)
    assert recent_i["required_days_per_month"] == pytest.approx(75.0)

    recent_ii = by_scope_type[("直近3ヶ月", "II")]
    assert recent_ii["rate_pct"] == pytest.approx(8.0)
    assert recent_ii["gap_pct"] == pytest.approx(8.5)
    assert recent_ii["required_days_per_month"] == pytest.approx(85.0)


def test_ward_case_mix_uses_doctor_map_and_department_fallback():
    df = pd.DataFrame([
        {
            "病棟": "6F", "医師": "TERUH", "診療科": "内科", "日数": 7,
            "手術": "×", "救急車": "有り", "緊急": "予定外",
        },
        {
            "病棟": "6F", "医師": "KJJ", "診療科": "麻酔科", "日数": 23,
            "手術": "○", "救急車": "無し", "緊急": "予定入院",
        },
        {
            "病棟": "6F", "医師": "UNKNOWN", "診療科": "循内科", "日数": 9,
            "手術": "×", "救急車": "無し", "緊急": "予定外",
        },
        {
            "病棟": "5F", "医師": "OKUK", "診療科": "整形外科", "日数": 12,
            "手術": "○", "救急車": "無し", "緊急": "予定外",
        },
    ])

    mix = summarize_ward_case_mix(
        df,
        ward="6F",
        specialty_map={"TERUH": "内科", "KJJ": "ペイン科"},
    )

    assert mix["n"] == 3
    assert mix["internal_pct"] == pytest.approx(66.7, abs=0.1)
    assert mix["pain_pct"] == pytest.approx(33.3, abs=0.1)
    assert mix["no_surgery_pct"] == pytest.approx(66.7, abs=0.1)
    assert mix["scheduled_pct"] == pytest.approx(33.3, abs=0.1)
    assert mix["ambulance_pct"] == pytest.approx(33.3, abs=0.1)
    assert mix["median_los"] == pytest.approx(9.0)


def test_monthly_admission_volume_summarizes_ward_range():
    df = pd.DataFrame([
        {"病棟": "6F", "入院日": "2026-01-01"},
        {"病棟": "6F", "入院日": "2026-01-02"},
        {"病棟": "6F", "入院日": "2026-02-01"},
        {"病棟": "5F", "入院日": "2026-02-01"},
    ])

    volume = summarize_monthly_admission_volume(df, ward="6F")

    assert volume["total_admissions"] == 3
    assert volume["mean_admissions"] == pytest.approx(1.5)
    assert volume["median_admissions"] == pytest.approx(1.5)
    assert volume["min_admissions"] == 1
    assert volume["max_admissions"] == 2
    assert volume["monthly_rows"] == [
        {"ym": "2026-01", "admissions": 2},
        {"ym": "2026-02", "admissions": 1},
    ]


def test_strategy_package_simulation_shows_remaining_gap():
    total_days = sum(DEFAULT_6F_STRATEGY_PACKAGE.values())
    result = simulate_strategy_package(
        base_rate_pct=13.13,
        emergency_coefficient_pct=1.48,
        target_pct=18.0,
        denominator_days_per_month=1200,
        added_eligible_days_per_month=total_days,
    )

    assert total_days == 40
    assert result["before_index_pct"] == pytest.approx(14.61)
    assert result["gain_pct"] == pytest.approx(3.33, abs=0.01)
    assert result["after_index_pct"] == pytest.approx(17.94, abs=0.01)
    assert result["remaining_gap_pct"] == pytest.approx(0.06, abs=0.01)
    assert result["meets_target"] is False


def test_patient_day_conversion_rows_translate_shortage_to_cases():
    rows = build_patient_day_conversion_rows(99.4)
    by_action = {row["action"]: row for row in rows}

    assert by_action["記録回収"]["required_cases_per_month"] == 100
    assert by_action["ペイン科A6 3日維持"]["required_cases_per_month"] == 34
    assert by_action["C21系 1件"]["required_cases_per_month"] == 25
    assert by_action["C23系 1件"]["required_cases_per_month"] == 20
    assert by_action["内科A項目 5日維持"]["required_cases_per_month"] == 20


def test_physician_case_matching_rows_are_clinical_and_actionable():
    rows = build_physician_case_matching_rows()
    combined = " ".join(
        row["case_pattern"] + row["fit_type"] + row["doctor_check"] + row["nurse_sync"]
        for row in rows
    )

    assert len(rows) >= 8
    assert "肺炎" in combined
    assert "心不全" in combined
    assert "CV" in combined
    assert "PEG" in combined
    assert "薬剤名" in combined
    assert "同日" in combined


def test_default_6f_action_mix_reaches_recent_safety_line():
    mix = calculate_6f_action_mix()
    by_action = {row["action"]: row for row in mix["rows"]}

    assert by_action["記録回収"]["patient_days"] == 11
    assert by_action["内科A項目"]["patient_days"] == 40
    assert "肺炎" in by_action["内科A項目"]["note"]
    assert by_action["ペイン科A6"]["patient_days"] == 9
    assert "薬剤名" in by_action["ペイン科A6"]["note"]
    assert by_action["C21系"]["patient_days"] == 16
    assert by_action["C22系"]["patient_days"] == 4
    assert by_action["C23系"]["patient_days"] == 20
    assert mix["total_patient_days"] == 100


def test_6f_strategy_cards_include_ethics_behavior_and_ui_lenses():
    cards = build_6f_strategy_cards({
        "internal_pct": 72.7,
        "pain_pct": 13.4,
        "no_surgery_pct": 84.6,
    })
    lenses = {card["lens"] for card in cards}
    combined = " ".join(card["action"] + card["metric"] for card in cards)

    assert {"医療倫理", "医学的エビデンス", "行動人間学", "UI/視覚効果"} <= lenses
    assert "虚偽記載" in combined
    assert "チェックリスト" in combined
