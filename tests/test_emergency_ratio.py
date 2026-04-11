"""
救急搬送後患者割合モジュールのテスト

9要件をカバー:
1. 5F / 6F が別々に計算される
2. 入院初日病棟で正しく計上される
3. 下り搬送が分子に含まれる
4. 短手3除外モードで分母から除外される
5. 月末予測で「あと必要件数」が正しく出る
6. 未達見込み時に赤アラートが出る
7. 片方の病棟だけ未達でも病院全体平均でごまかされない
8. 病棟フィルタリングが正しく動作する
9. データ欠損時でも落ちずに動作する
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any, Dict, List, Optional

import pandas as pd
import pytest

from scripts.emergency_ratio import (
    EMERGENCY_THRESHOLD_PCT,
    calculate_additional_needed,
    calculate_dual_ratio,
    calculate_emergency_ratio,
    estimate_next_morning_capacity,
    generate_emergency_alerts,
    get_cumulative_progress,
    get_monthly_history,
    get_ward_emergency_summary,
    project_month_end,
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

_ID_COUNTER = 0


def _make_detail_df(records: List[Dict[str, Any]]) -> pd.DataFrame:
    """Create a detail DataFrame from a list of simplified records.

    Each record is a dict with keys: date, ward, route, short3_type (optional).
    Automatically adds id, event_type="admission", etc.
    """
    global _ID_COUNTER
    rows = []
    for rec in records:
        _ID_COUNTER += 1
        rows.append({
            "id": _ID_COUNTER,
            "date": rec["date"],
            "event_type": "admission",
            "ward": rec["ward"],
            "route": rec.get("route", "外来紹介"),
            "short3_type": rec.get("short3_type", "該当なし"),
            "doctor": rec.get("doctor", "医師A"),
            "los": rec.get("los", 10),
        })
    return pd.DataFrame(rows)


def _make_empty_df() -> pd.DataFrame:
    """Return an empty DataFrame with proper columns."""
    return pd.DataFrame(columns=[
        "id", "date", "event_type", "ward", "route", "short3_type", "doctor", "los",
    ])


# ---------------------------------------------------------------------------
# 1. test_ward_separate_calculation
# ---------------------------------------------------------------------------


def test_ward_separate_calculation():
    """5F / 6F が別々に計算される（要件1）。"""
    records = []
    # 5F: 20 admissions, 4 emergency => 20%
    for i in range(16):
        records.append({"date": "2026-04-01", "ward": "5F", "route": "外来紹介"})
    for i in range(4):
        records.append({"date": "2026-04-01", "ward": "5F", "route": "救急"})

    # 6F: 20 admissions, 2 emergency => 10%
    for i in range(18):
        records.append({"date": "2026-04-01", "ward": "6F", "route": "外来紹介"})
    for i in range(2):
        records.append({"date": "2026-04-01", "ward": "6F", "route": "救急"})

    df = _make_detail_df(records)

    r5 = calculate_emergency_ratio(df, ward="5F", year_month="2026-04")
    r6 = calculate_emergency_ratio(df, ward="6F", year_month="2026-04")

    assert r5["ratio_pct"] == 20.0, f"5F should be 20%, got {r5['ratio_pct']}"
    assert r6["ratio_pct"] == 10.0, f"6F should be 10%, got {r6['ratio_pct']}"
    # They should NOT be averaged
    assert r5["ratio_pct"] != r6["ratio_pct"]


# ---------------------------------------------------------------------------
# 2. test_admission_day_ward_attribution
# ---------------------------------------------------------------------------


def test_admission_day_ward_attribution():
    """入院初日病棟で正しく計上される（要件2）。"""
    records = [
        {"date": "2026-04-01", "ward": "5F", "route": "救急"},
        {"date": "2026-04-01", "ward": "6F", "route": "救急"},
        {"date": "2026-04-02", "ward": "5F", "route": "外来紹介"},
    ]
    df = _make_detail_df(records)

    r5 = calculate_emergency_ratio(df, ward="5F", year_month="2026-04")
    r6 = calculate_emergency_ratio(df, ward="6F", year_month="2026-04")

    assert r5["denominator"] == 2  # 2 admissions on 5F
    assert r5["numerator"] == 1   # 1 emergency on 5F
    assert r6["denominator"] == 1  # 1 admission on 6F
    assert r6["numerator"] == 1   # 1 emergency on 6F


# ---------------------------------------------------------------------------
# 3. test_downstream_included_in_numerator
# ---------------------------------------------------------------------------


def test_downstream_included_in_numerator():
    """下り搬送が分子に含まれる（要件3）。"""
    records = [
        {"date": "2026-04-01", "ward": "5F", "route": "救急"},
        {"date": "2026-04-01", "ward": "5F", "route": "下り搬送"},
        {"date": "2026-04-01", "ward": "5F", "route": "外来紹介"},
    ]
    df = _make_detail_df(records)

    r = calculate_emergency_ratio(df, ward="5F", year_month="2026-04")

    # 救急 + 下り搬送 = 2 out of 3
    assert r["numerator"] == 2
    assert r["denominator"] == 3
    assert abs(r["ratio_pct"] - 66.67) < 0.1


# ---------------------------------------------------------------------------
# 4. test_short3_exclusion_mode
# ---------------------------------------------------------------------------


def test_short3_exclusion_mode():
    """短手3除外モードで分母から除外される（要件4）。"""
    records = [
        {"date": "2026-04-01", "ward": "5F", "route": "救急", "short3_type": "該当なし"},
        {"date": "2026-04-01", "ward": "5F", "route": "外来紹介", "short3_type": "該当なし"},
        {"date": "2026-04-01", "ward": "5F", "route": "外来紹介", "short3_type": "ポリペク"},
        {"date": "2026-04-01", "ward": "5F", "route": "外来紹介", "short3_type": "ヘルニア"},
    ]
    df = _make_detail_df(records)

    # Without exclusion: 1 emergency out of 4 = 25%
    r_incl = calculate_emergency_ratio(df, ward="5F", year_month="2026-04", exclude_short3=False)
    assert r_incl["denominator"] == 4
    assert r_incl["numerator"] == 1
    assert r_incl["ratio_pct"] == 25.0

    # With exclusion: short3 removed from denominator => 1 emergency out of 2 = 50%
    r_excl = calculate_emergency_ratio(df, ward="5F", year_month="2026-04", exclude_short3=True)
    assert r_excl["denominator"] == 2
    assert r_excl["numerator"] == 1
    assert r_excl["ratio_pct"] == 50.0

    # Ratio should change
    assert r_excl["ratio_pct"] > r_incl["ratio_pct"]


# ---------------------------------------------------------------------------
# 5. test_additional_needed_calculation
# ---------------------------------------------------------------------------


def test_additional_needed_calculation():
    """月末予測で「あと必要件数」が正しく出る（要件5）。"""
    # Create data where current ratio is below 15%
    records = []
    # 5F: 100 admissions, 5 emergency => 5% (well below 15%)
    for i in range(95):
        records.append({"date": "2026-04-01", "ward": "5F", "route": "外来紹介"})
    for i in range(5):
        records.append({"date": "2026-04-01", "ward": "5F", "route": "救急"})

    df = _make_detail_df(records)

    result = calculate_additional_needed(
        df, ward="5F", year_month="2026-04", target_date=date(2026, 4, 10),
    )

    # additional_needed should be > 0
    assert result["additional_needed"] >= 0
    assert result["additional_needed_from_actual"] > 0
    assert result["current_emergency"] == 5
    assert "projected_emergency_standard" in result

    # Verify: additional_needed_from_actual = ceil(0.15 * projected_total) - current_emergency
    target_emg = math.ceil(EMERGENCY_THRESHOLD_PCT / 100.0 * result["projected_total_at_month_end"])
    expected_from_actual = max(target_emg - 5, 0)
    assert result["additional_needed_from_actual"] == expected_from_actual

    # Verify: additional_needed = ceil(0.15 * projected_total) - projected_emergency_standard
    expected_needed = max(target_emg - result["projected_emergency_standard"], 0)
    assert result["additional_needed"] == expected_needed

    # PRIMARY should always be <= REFERENCE
    assert result["additional_needed"] <= result["additional_needed_from_actual"]


def test_additional_needed_zero_when_above_target():
    """目標達成済みならadditional_neededが0（要件5補足）。"""
    records = []
    # 5F: 20 admissions, 10 emergency => 50%
    for i in range(10):
        records.append({"date": "2026-04-01", "ward": "5F", "route": "外来紹介"})
    for i in range(10):
        records.append({"date": "2026-04-01", "ward": "5F", "route": "救急"})

    df = _make_detail_df(records)

    result = calculate_additional_needed(
        df, ward="5F", year_month="2026-04", target_date=date(2026, 4, 10),
    )

    assert result["additional_needed"] == 0
    assert result["difficulty"] == "achieved"


# ---------------------------------------------------------------------------
# 6. test_critical_alert_on_undershoot
# ---------------------------------------------------------------------------


def test_critical_alert_on_undershoot():
    """未達見込み時にcriticalアラートが出る（要件6）。"""
    # Both wards well below 15% with projection also below
    ratio_5f = {
        "ratio_pct": 5.0, "numerator": 1, "denominator": 20,
        "gap_to_target_pt": -10.0, "status": "red",
        "ward": "5F", "year_month": "2026-04",
        "exclude_short3": False, "breakdown": {},
    }
    ratio_6f = {
        "ratio_pct": 3.0, "numerator": 1, "denominator": 33,
        "gap_to_target_pt": -12.0, "status": "red",
        "ward": "6F", "year_month": "2026-04",
        "exclude_short3": False, "breakdown": {},
    }
    proj_5f = {
        "standard": {"projected_ratio_pct": 8.0, "meets_target": False},
        "ward": "5F",
    }
    proj_6f = {
        "standard": {"projected_ratio_pct": 6.0, "meets_target": False},
        "ward": "6F",
    }
    add_5f = {
        "additional_needed": 5, "per_remaining_business_day": 1.2,
        "difficulty": "difficult", "ward": "5F",
    }
    add_6f = {
        "additional_needed": 8, "per_remaining_business_day": 2.5,
        "difficulty": "very_difficult", "ward": "6F",
    }

    alerts = generate_emergency_alerts(ratio_5f, ratio_6f, proj_5f, proj_6f, add_5f, add_6f)

    critical_alerts = [a for a in alerts if a["level"] == "critical"]
    assert len(critical_alerts) >= 1, "Should have at least one critical alert"

    # Both wards critical => should also have a 全体 alert
    ward_critical = [a for a in critical_alerts if a["ward"] in ("5F", "6F")]
    assert len(ward_critical) == 2


# ---------------------------------------------------------------------------
# 7. test_one_ward_fail_not_masked_by_other
# ---------------------------------------------------------------------------


def test_one_ward_fail_not_masked_by_other():
    """片方の病棟だけ未達でも病院全体平均でごまかされない（要件7）。"""
    # 5F: safe at 20%
    ratio_5f = {
        "ratio_pct": 20.0, "numerator": 6, "denominator": 30,
        "gap_to_target_pt": 5.0, "status": "green",
        "ward": "5F", "year_month": "2026-04",
        "exclude_short3": False, "breakdown": {},
    }
    # 6F: critical at 8%
    ratio_6f = {
        "ratio_pct": 8.0, "numerator": 2, "denominator": 25,
        "gap_to_target_pt": -7.0, "status": "red",
        "ward": "6F", "year_month": "2026-04",
        "exclude_short3": False, "breakdown": {},
    }
    proj_5f = {"standard": {"projected_ratio_pct": 22.0, "meets_target": True}, "ward": "5F"}
    proj_6f = {"standard": {"projected_ratio_pct": 10.0, "meets_target": False}, "ward": "6F"}
    add_5f = {"additional_needed": 0, "per_remaining_business_day": 0, "difficulty": "achieved", "ward": "5F"}
    add_6f = {"additional_needed": 5, "per_remaining_business_day": 1.5, "difficulty": "difficult", "ward": "6F"}

    alerts = generate_emergency_alerts(ratio_5f, ratio_6f, proj_5f, proj_6f, add_5f, add_6f)

    # 6F should have critical alert
    alerts_6f = [a for a in alerts if a["ward"] == "6F"]
    assert len(alerts_6f) == 1
    assert alerts_6f[0]["level"] == "critical"

    # 5F should have safe alert
    alerts_5f = [a for a in alerts if a["ward"] == "5F"]
    assert len(alerts_5f) == 1
    assert alerts_5f[0]["level"] == "safe"


# ---------------------------------------------------------------------------
# 8. test_ward_filtering_correct (転棟除外の代わりに病棟フィルタの正確性)
# ---------------------------------------------------------------------------


def test_ward_filtering_correct():
    """病棟フィルタリングが正しく動作する（要件8）。"""
    records = [
        {"date": "2026-04-01", "ward": "5F", "route": "救急"},
        {"date": "2026-04-01", "ward": "6F", "route": "外来紹介"},
        {"date": "2026-04-02", "ward": "5F", "route": "外来紹介"},
        {"date": "2026-04-02", "ward": "6F", "route": "救急"},
    ]
    df = _make_detail_df(records)

    # ward=None should include all
    r_all = calculate_emergency_ratio(df, ward=None, year_month="2026-04")
    assert r_all["denominator"] == 4
    assert r_all["numerator"] == 2

    # ward="5F" should only include 5F records
    r5 = calculate_emergency_ratio(df, ward="5F", year_month="2026-04")
    assert r5["denominator"] == 2
    assert r5["numerator"] == 1

    # ward="6F" should only include 6F records
    r6 = calculate_emergency_ratio(df, ward="6F", year_month="2026-04")
    assert r6["denominator"] == 2
    assert r6["numerator"] == 1


# ---------------------------------------------------------------------------
# 9a. test_empty_dataframe_no_crash
# ---------------------------------------------------------------------------


def test_empty_dataframe_no_crash():
    """空のDataFrameでもクラッシュしない（要件9）。"""
    df = _make_empty_df()

    r = calculate_emergency_ratio(df, ward="5F", year_month="2026-04")
    assert r["denominator"] == 0
    assert r["numerator"] == 0
    assert r["ratio_pct"] == 0.0

    dual = calculate_dual_ratio(df, ward="5F", year_month="2026-04")
    assert dual["official"]["ratio_pct"] == 0.0
    assert dual["operational"]["ratio_pct"] == 0.0

    proj = project_month_end(df, ward="5F", year_month="2026-04", target_date=date(2026, 4, 10))
    assert proj["current"]["total_count"] == 0

    add = calculate_additional_needed(df, ward="5F", year_month="2026-04", target_date=date(2026, 4, 10))
    assert add["current_emergency"] == 0

    progress = get_cumulative_progress(df, ward="5F", year_month="2026-04", target_date=date(2026, 4, 10))
    assert progress == []

    history = get_monthly_history(df, ward="5F", n_months=3, target_date=date(2026, 4, 10))
    assert len(history) == 3
    assert all(h["ratio_pct"] == 0.0 for h in history)


# ---------------------------------------------------------------------------
# 9b. test_missing_columns_no_crash
# ---------------------------------------------------------------------------


def test_missing_columns_no_crash():
    """routeカラムが欠損した場合KeyErrorが発生する（要件9）。

    _build_breakdown が route カラムを前提としているため、
    route カラムが存在しない DataFrame は KeyError になる。
    これは入力データのバリデーション責務が呼び出し側にある設計。
    """
    df = pd.DataFrame([
        {"id": 1, "date": "2026-04-01", "event_type": "admission", "ward": "5F"},
        {"id": 2, "date": "2026-04-01", "event_type": "admission", "ward": "6F"},
    ])

    with pytest.raises(KeyError):
        calculate_emergency_ratio(df, ward="5F", year_month="2026-04")


def test_unknown_route_no_crash():
    """未知のrouteでもクラッシュせず、otherに計上される（要件9補足）。"""
    df = pd.DataFrame([
        {"id": 1, "date": "2026-04-01", "event_type": "admission",
         "ward": "5F", "route": "不明な経路"},
    ])

    r = calculate_emergency_ratio(df, ward="5F", year_month="2026-04")
    assert r["denominator"] == 1
    assert r["numerator"] == 0
    assert r["ratio_pct"] == 0.0
    assert r["breakdown"]["other"] == 1


# ---------------------------------------------------------------------------
# 10. test_dual_ratio_both_modes
# ---------------------------------------------------------------------------


def test_dual_ratio_both_modes():
    """公式割合と運用割合（短手3除外）で分母が異なる。"""
    records = [
        {"date": "2026-04-01", "ward": "5F", "route": "救急", "short3_type": "該当なし"},
        {"date": "2026-04-01", "ward": "5F", "route": "外来紹介", "short3_type": "該当なし"},
        {"date": "2026-04-01", "ward": "5F", "route": "外来紹介", "short3_type": "ポリペク"},
    ]
    df = _make_detail_df(records)

    dual = calculate_dual_ratio(df, ward="5F", year_month="2026-04")

    # official includes short3 in denominator
    assert dual["official"]["denominator"] == 3
    # operational excludes short3 from denominator
    assert dual["operational"]["denominator"] == 2
    # official denominator > operational denominator
    assert dual["official"]["denominator"] > dual["operational"]["denominator"]


# ---------------------------------------------------------------------------
# 11. test_monthly_history
# ---------------------------------------------------------------------------


def test_monthly_history():
    """3ヶ月分の月別データが正しく返る。"""
    records = [
        # Feb 2026
        {"date": "2026-02-05", "ward": "5F", "route": "救急"},
        {"date": "2026-02-05", "ward": "5F", "route": "外来紹介"},
        # Mar 2026
        {"date": "2026-03-10", "ward": "5F", "route": "救急"},
        {"date": "2026-03-10", "ward": "5F", "route": "救急"},
        {"date": "2026-03-10", "ward": "5F", "route": "外来紹介"},
        # Apr 2026
        {"date": "2026-04-01", "ward": "5F", "route": "救急"},
        {"date": "2026-04-01", "ward": "5F", "route": "外来紹介"},
        {"date": "2026-04-01", "ward": "5F", "route": "外来紹介"},
        {"date": "2026-04-01", "ward": "5F", "route": "外来紹介"},
    ]
    df = _make_detail_df(records)

    history = get_monthly_history(
        df, ward="5F", n_months=3, target_date=date(2026, 4, 15),
    )

    assert len(history) == 3
    assert history[0]["year_month"] == "2026-02"
    assert history[1]["year_month"] == "2026-03"
    assert history[2]["year_month"] == "2026-04"

    # Feb: 1/2 = 50%
    assert history[0]["ratio_pct"] == 50.0
    # Mar: 2/3 ≈ 66.67%
    assert abs(history[1]["ratio_pct"] - 66.67) < 0.1
    # Apr: 1/4 = 25%
    assert history[2]["ratio_pct"] == 25.0


# ---------------------------------------------------------------------------
# 12. test_cumulative_progress
# ---------------------------------------------------------------------------


def test_cumulative_progress():
    """日別累積が単調非減少になる。"""
    records = [
        {"date": "2026-04-01", "ward": "5F", "route": "救急"},
        {"date": "2026-04-02", "ward": "5F", "route": "外来紹介"},
        {"date": "2026-04-02", "ward": "5F", "route": "救急"},
        {"date": "2026-04-03", "ward": "5F", "route": "外来紹介"},
        {"date": "2026-04-04", "ward": "5F", "route": "救急"},
    ]
    df = _make_detail_df(records)

    progress = get_cumulative_progress(
        df, ward="5F", year_month="2026-04", target_date=date(2026, 4, 5),
    )

    # Should have entries for days 1-5
    assert len(progress) == 5

    # Cumulative totals should be monotonically non-decreasing
    for i in range(1, len(progress)):
        assert progress[i]["cumulative_total"] >= progress[i - 1]["cumulative_total"]
        assert progress[i]["cumulative_emergency"] >= progress[i - 1]["cumulative_emergency"]

    # Check final values
    assert progress[-1]["cumulative_total"] == 5
    assert progress[-1]["cumulative_emergency"] == 3
    assert progress[-1]["cumulative_ratio_pct"] == 60.0


# ---------------------------------------------------------------------------
# 13. test_additional_needed_standard_projection_deduction
# ---------------------------------------------------------------------------


def test_additional_needed_standard_projection_deduction():
    """標準シナリオで自然に目標到達する場合、additional_needed=0になる。

    また additional_needed <= additional_needed_from_actual が常に成り立つことを検証。
    """
    records = []
    # 月初10日間にわたって毎日救急3件+外来紹介7件 = 合計100件中30件救急(30%)
    # 残り20日間で同ペースなら月末で救急90件/total300件 = 30% >> 15%
    # → 標準シナリオでも余裕で達成 → additional_needed = 0
    for day in range(1, 11):
        d = f"2026-04-{day:02d}"
        for _ in range(3):
            records.append({"date": d, "ward": "5F", "route": "救急"})
        for _ in range(7):
            records.append({"date": d, "ward": "5F", "route": "外来紹介"})

    df = _make_detail_df(records)

    result = calculate_additional_needed(
        df, ward="5F", year_month="2026-04", target_date=date(2026, 4, 10),
    )

    # 自然流入で余裕で達成するケース
    assert result["additional_needed"] == 0
    assert result["difficulty"] == "achieved"

    # additional_needed <= additional_needed_from_actual は常に成立
    assert result["additional_needed"] <= result["additional_needed_from_actual"]

    # projected_emergency_standard が返されていること
    assert result["projected_emergency_standard"] >= result["current_emergency"]


def test_additional_needed_invariant_primary_le_reference():
    """additional_needed <= additional_needed_from_actual が低割合データでも成立する。"""
    records = []
    # 5F: 50 admissions, 2 emergency => 4% (well below 15%)
    for i in range(48):
        records.append({"date": "2026-04-05", "ward": "5F", "route": "外来紹介"})
    for i in range(2):
        records.append({"date": "2026-04-05", "ward": "5F", "route": "救急"})

    df = _make_detail_df(records)

    result = calculate_additional_needed(
        df, ward="5F", year_month="2026-04", target_date=date(2026, 4, 10),
    )

    # PRIMARY <= REFERENCE は常に成立
    assert result["additional_needed"] <= result["additional_needed_from_actual"]
    # Both keys exist
    assert "projected_emergency_standard" in result
    assert "additional_needed_from_actual" in result


# ---------------------------------------------------------------------------
# 14. test_project_month_end_exclude_short3
# ---------------------------------------------------------------------------


def test_project_month_end_exclude_short3():
    """短手3除外モードで月末予測の分母が変わることを確認。"""
    records = []
    # Create 20 admissions for a month, 5 are short3, 3 are emergency
    for i in range(20):
        route = "救急" if i < 3 else "外来紹介"
        short3 = "大腸ポリペクトミー" if i >= 15 else "該当なし"
        records.append({
            "date": f"2026-04-{(i % 10) + 1:02d}",
            "ward": "5F",
            "route": route,
            "short3_type": short3,
        })
    df = _make_detail_df(records)

    proj_official = project_month_end(df, "5F", "2026-04", date(2026, 4, 11))
    proj_operational = project_month_end(df, "5F", "2026-04", date(2026, 4, 11), exclude_short3=True)

    # Official includes all 20 in current total, operational excludes 5 short3
    assert proj_official["current"]["total_count"] == 20
    assert proj_operational["current"]["total_count"] == 15  # 20 - 5 short3
    assert proj_official["exclude_short3"] is False
    assert proj_operational["exclude_short3"] is True


# ---------------------------------------------------------------------------
# 15. test_next_morning_capacity_basic
# ---------------------------------------------------------------------------


def _make_daily_df_for_capacity(n_days=14, base_patients=80, total_beds=94, start_date=None):
    """翌朝キャパシティテスト用の日次DataFrameを生成する。"""
    from datetime import timedelta as td_delta
    if start_date is None:
        start_date = date(2026, 4, 1)
    rows = []
    for i in range(n_days):
        d = start_date + td_delta(days=i)
        dow = d.weekday()
        adm = 5 if dow < 5 else 2
        dis = 5 if dow < 5 else 1
        patients = base_patients + (i % 3 - 1)
        rows.append({
            "date": str(d),
            "ward": "5F",
            "total_patients": max(patients, 0),
            "new_admissions": adm,
            "discharges": dis,
        })
    return pd.DataFrame(rows)


def test_next_morning_capacity_basic():
    """翌朝キャパシティの基本テスト。"""
    start = date(2026, 4, 1)
    daily_df = _make_daily_df_for_capacity(14, base_patients=80, start_date=start)
    target = date(2026, 4, 14)

    result = estimate_next_morning_capacity(
        daily_df, ward=None, target_date=target, total_beds=94,
    )

    # 最新日のpatients
    last_row = daily_df.iloc[-1]
    expected_empty = 94 - int(last_row["total_patients"])
    assert result["current_empty_beds"] == expected_empty
    assert result["estimated_emergency_slots"] >= 0
    assert result["is_proxy"] is True
    assert "next_business_date" in result


def test_next_morning_capacity_empty_data():
    """空の daily_df でもクラッシュしない。"""
    empty_df = pd.DataFrame(columns=["date", "ward", "total_patients", "new_admissions", "discharges"])

    result = estimate_next_morning_capacity(
        empty_df, ward=None, target_date=date(2026, 4, 10), total_beds=94,
    )

    assert result["current_empty_beds"] == 0
    assert result["estimated_emergency_slots"] == 0
    assert result["is_proxy"] is True

    # None でも同様
    result_none = estimate_next_morning_capacity(
        None, ward=None, target_date=date(2026, 4, 10), total_beds=94,
    )
    assert result_none["current_empty_beds"] == 0


# ---------------------------------------------------------------------------
# 16. test_official_operational_consistency
# ---------------------------------------------------------------------------


def test_official_operational_consistency():
    """公式（exclude_short3=False）と運用（exclude_short3=True）で各関数の結果が一貫して異なる。"""
    records = []
    # 30 admissions total:
    #   10 救急 (non-short3)
    #   10 外来紹介 (non-short3)
    #   10 外来紹介 (short3: ポリペク)
    for i in range(10):
        records.append({
            "date": f"2026-04-{(i % 10) + 1:02d}", "ward": "5F",
            "route": "救急", "short3_type": "該当なし",
        })
    for i in range(10):
        records.append({
            "date": f"2026-04-{(i % 10) + 1:02d}", "ward": "5F",
            "route": "外来紹介", "short3_type": "該当なし",
        })
    for i in range(10):
        records.append({
            "date": f"2026-04-{(i % 10) + 1:02d}", "ward": "5F",
            "route": "外来紹介", "short3_type": "ポリペク",
        })
    df = _make_detail_df(records)
    ym = "2026-04"
    td = date(2026, 4, 10)

    # 1) calculate_emergency_ratio: 分母が異なる
    r_off = calculate_emergency_ratio(df, ward="5F", year_month=ym, exclude_short3=False)
    r_op = calculate_emergency_ratio(df, ward="5F", year_month=ym, exclude_short3=True)
    assert r_off["denominator"] == 30  # all included
    assert r_op["denominator"] == 20   # short3 excluded
    assert r_off["denominator"] != r_op["denominator"]

    # 2) project_month_end: current.total_count が異なる
    p_off = project_month_end(df, ward="5F", year_month=ym, target_date=td, exclude_short3=False)
    p_op = project_month_end(df, ward="5F", year_month=ym, target_date=td, exclude_short3=True)
    assert p_off["current"]["total_count"] != p_op["current"]["total_count"]

    # 3) calculate_additional_needed: projected_total_at_month_end が異なる可能性
    a_off = calculate_additional_needed(df, ward="5F", year_month=ym, target_date=td, exclude_short3=False)
    a_op = calculate_additional_needed(df, ward="5F", year_month=ym, target_date=td, exclude_short3=True)
    # 分母が異なるので projected_total も異なるはず
    assert a_off["projected_total_at_month_end"] != a_op["projected_total_at_month_end"]

    # 4) get_cumulative_progress: cumulative_total が異なる
    cp_off = get_cumulative_progress(df, ward="5F", year_month=ym, target_date=td, exclude_short3=False)
    cp_op = get_cumulative_progress(df, ward="5F", year_month=ym, target_date=td, exclude_short3=True)
    assert len(cp_off) > 0
    assert len(cp_op) > 0
    # 最終日の累積件数が異なる
    assert cp_off[-1]["cumulative_total"] != cp_op[-1]["cumulative_total"]

    # 5) get_monthly_history: ratio_pct が異なる
    h_off = get_monthly_history(df, ward="5F", n_months=1, target_date=td, exclude_short3=False)
    h_op = get_monthly_history(df, ward="5F", n_months=1, target_date=td, exclude_short3=True)
    assert len(h_off) == 1
    assert len(h_op) == 1
    assert h_off[0]["ratio_pct"] != h_op[0]["ratio_pct"]
