#!/usr/bin/env python3
"""Smoke test for bed_control_simulator_app regression detection.

Runs key calculations against the demo data and asserts expected values.
Called from pre-commit hook. Fails fast if any core feature is broken.

Expected values are baseline snapshots — if you intentionally change
a calculation, update the expected values here.
"""

import os
import sys
import traceback
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

CSV_PATH = os.path.join(ROOT, "data", "sample_actual_data_ward_202604.csv")
BEDS = 47

# Expected values — update these intentionally when calculations change
EXPECTED = {
    "csv_row_count": 220,  # 110 days × 2 wards
    "csv_apr_5f_days": 20,
    "csv_apr_6f_days": 20,
    # 厚労省定義: 病床稼働率 = (在院患者数 + 退院患者数) / 病床数
    "apr_5f_occ_pct": (85.0, 88.0),  # acceptable range (目標90%未達 → 改善が必要)
    "apr_6f_occ_pct": (89.0, 92.0),
    "overall_occ_pct": (87.0, 90.0),
    "single_5f_required_pct": (95.0, 100.0),  # 残り10日で90%達成には高い稼働率が必要
    "single_6f_required_pct": (87.0, 92.0),  # 6Fも目標付近でやや追い上げ必要
    "equal_effort_delta_pt": (2.0, 7.0),  # positive = 目標未達、改善が必要
    "rolling_los_5f_range": (15.0, 21.0),  # within facility criterion 21 days
    "rolling_los_6f_range": (17.0, 23.5),  # drifting above 21日 criterion (demo story)
    # --- 診療報酬プリセットの反映チェック（What-if シミュレーションで使用） ---
    # 2024年度 vs 2026年度 で 日次貢献額が増加するか（同一入院数・稼働率で）
    "preset_contrib_2024_manyen_per_day": (240.0, 250.0),
    "preset_contrib_2026_manyen_per_day": (260.0, 272.0),
    "preset_contrib_delta_yearly_manyen": (7000.0, 8500.0),  # 改定効果のみ +7,200万円/年 と概ね一致
}

errors = []
warnings_list = []

def check(label, value, expected):
    if isinstance(expected, tuple) and len(expected) == 2:
        lo, hi = expected
        if not (lo <= value <= hi):
            errors.append(f"❌ {label}: {value:.2f} not in [{lo}, {hi}]")
            return False
    elif value != expected:
        errors.append(f"❌ {label}: {value} != {expected}")
        return False
    print(f"✅ {label}: {value}")
    return True

try:
    # --- 1. CSV structure ---
    df = pd.read_csv(CSV_PATH)
    check("csv_row_count", len(df), EXPECTED["csv_row_count"])

    df["date"] = pd.to_datetime(df["date"])
    apr = df[df["date"].dt.month == 4]
    apr_5f = apr[apr["ward"] == "5F"]
    apr_6f = apr[apr["ward"] == "6F"]
    check("csv_apr_5f_days", len(apr_5f), EXPECTED["csv_apr_5f_days"])
    check("csv_apr_6f_days", len(apr_6f), EXPECTED["csv_apr_6f_days"])

    # --- 2. Occupancy rates (core story) ---
    # 厚労省定義: 病床稼働率 = (在院患者数 + 退院患者数) / 病床数
    _dis_5f = apr_5f["discharges"] if "discharges" in apr_5f.columns else 0
    _dis_6f = apr_6f["discharges"] if "discharges" in apr_6f.columns else 0
    occ_5f = (apr_5f["total_patients"] + _dis_5f).mean() / BEDS * 100
    occ_6f = (apr_6f["total_patients"] + _dis_6f).mean() / BEDS * 100
    overall_occ = ((apr_5f["total_patients"] + _dis_5f).mean() + (apr_6f["total_patients"] + _dis_6f).mean()) / (BEDS * 2) * 100
    check("apr_5f_occ_pct", occ_5f, EXPECTED["apr_5f_occ_pct"])
    check("apr_6f_occ_pct", occ_6f, EXPECTED["apr_6f_occ_pct"])
    check("overall_occ_pct", overall_occ, EXPECTED["overall_occ_pct"])

    # --- 3. Single-ward monthly targets ---
    target = 90.0
    D = 30
    d_elapsed = 20
    d_remain = 10
    single_5f = (target * D - occ_5f * d_elapsed) / d_remain
    single_6f = (target * D - occ_6f * d_elapsed) / d_remain
    check("single_5f_required_pct", single_5f, EXPECTED["single_5f_required_pct"])
    check("single_6f_required_pct", single_6f, EXPECTED["single_6f_required_pct"])

    # --- 4. Equal effort delta (全体主義) ---
    total_bd_done = BEDS * d_elapsed * (occ_5f + occ_6f) / 100
    total_bd_required = BEDS * 2 * D * target / 100
    bd_remaining = total_bd_required - total_bd_done
    needed_per_day = bd_remaining / d_remain
    sum_beds_avg = (occ_5f + occ_6f) * BEDS
    delta = (needed_per_day * 100 - sum_beds_avg) / (BEDS * 2)
    check("equal_effort_delta_pt", delta, EXPECTED["equal_effort_delta_pt"])

    # デモストーリー: 目標未達 → 改善が必要、deltaは正の値
    # deltaが正 = 目標未達で追加努力が必要
    if delta > 10 or delta < -10:
        errors.append(f"❌ CRITICAL: equal effort delta is {delta:.2f} (absolute value > 10 is unexpected)")

    # --- 5. Rolling LOS (3-month) ---
    try:
        from bed_data_manager import calculate_rolling_los
        for w, expected_key in [("5F", "rolling_los_5f_range"), ("6F", "rolling_los_6f_range")]:
            w_df = df[df["ward"] == w].copy()
            w_df = w_df.rename(columns={
                "date": "date",
                "total_patients": "total_patients",
                "new_admissions": "new_admissions",
                "discharges": "discharges",
            })
            result = calculate_rolling_los(w_df, window_days=90)
            if result and result.get("rolling_los") is not None:
                check(f"rolling_los_{w}", result["rolling_los"], EXPECTED[expected_key])
            else:
                warnings_list.append(f"⚠️  rolling_los for {w} returned None")
    except ImportError as e:
        warnings_list.append(f"⚠️  bed_data_manager import failed: {e}")

    # --- 5b. Fee preset reflection in calculate_ideal_phase_ratios ---
    try:
        from bed_data_manager import calculate_ideal_phase_ratios
        r2024 = calculate_ideal_phase_ratios(
            num_beds=94, monthly_admissions=150, target_occupancy=0.93, days_per_month=30,
            phase_a_contrib=36000-12000, phase_b_contrib=36000-6000, phase_c_contrib=33400-4500,
        )
        r2026 = calculate_ideal_phase_ratios(
            num_beds=94, monthly_admissions=150, target_occupancy=0.93, days_per_month=30,
            phase_a_contrib=38500-12000, phase_b_contrib=38500-6000, phase_c_contrib=35500-4500,
        )
        contrib_2024 = r2024["daily_contribution"] / 10000
        contrib_2026 = r2026["daily_contribution"] / 10000
        delta_yearly = (r2026["daily_contribution"] - r2024["daily_contribution"]) * 365 / 10000
        check("preset_contrib_2024_manyen_per_day", contrib_2024, EXPECTED["preset_contrib_2024_manyen_per_day"])
        check("preset_contrib_2026_manyen_per_day", contrib_2026, EXPECTED["preset_contrib_2026_manyen_per_day"])
        check("preset_contrib_delta_yearly_manyen", delta_yearly, EXPECTED["preset_contrib_delta_yearly_manyen"])
        # Critical: 2026 must produce a strictly larger daily contribution than 2024
        if contrib_2026 <= contrib_2024:
            errors.append(
                f"❌ CRITICAL: 2026 preset ({contrib_2026:.1f}万円) did not exceed 2024 ({contrib_2024:.1f}万円) — "
                f"診療報酬プリセットがcalculate_ideal_phase_ratiosに反映されていない可能性"
            )
    except Exception as e:
        errors.append(f"❌ preset reflection check crashed: {e}")

    # --- 6. App imports cleanly (syntax + top-level execution) ---
    try:
        import py_compile
        py_compile.compile(os.path.join(ROOT, "scripts", "bed_control_simulator_app.py"), doraise=True)
        print("✅ bed_control_simulator_app.py compiles")
    except py_compile.PyCompileError as e:
        errors.append(f"❌ app fails py_compile: {e}")

    # === 7. SCENARIO CONSISTENCY CHECKS ===
    # These values must match the demo scenario script exactly.
    # If data changes cause these to drift, update BOTH data AND scenario.
    SCENARIO_EXPECTED = {
        "overall_occ_display": (88.5, 89.0),  # 全体稼働率 (scenario says 88.8%)
        "occ_5f_display": (86.0, 87.0),        # 5F稼働率 (scenario says 86.5%)
        "occ_6f_display": (90.5, 92.0),        # 6F稼働率 (scenario says 91.1%)
        "los_6f_rolling_above_21": True,        # 6F rolling > 21日 (triggers alert)
        "los_5f_rolling_below_21": True,        # 5F rolling < 21日 (within criteria)
        "current_month_los_overall": (19.0, 22.0),  # 今月LOS全体 (realistic range)
        "current_month_los_6f": (21.0, 24.0),  # 6F今月LOS > 21日
        "current_month_los_5f": (16.0, 21.0),  # 5F今月LOS < 21日
        "friday_discharge_pct": (25, 35),       # 金曜退院率 (scenario says 31%)
    }

    print("\n--- Scenario Consistency Checks ---")

    # 7a. Display occupancy rates (same as core but with scenario-precise ranges)
    check("scenario_overall_occ_display", overall_occ, SCENARIO_EXPECTED["overall_occ_display"])
    check("scenario_occ_5f_display", occ_5f, SCENARIO_EXPECTED["occ_5f_display"])
    check("scenario_occ_6f_display", occ_6f, SCENARIO_EXPECTED["occ_6f_display"])

    # 7b. Rolling LOS scenario assertions (6F above 21, 5F below 21)
    try:
        from bed_data_manager import calculate_rolling_los as _calc_rlos
        rolling_results = {}
        for w in ["5F", "6F"]:
            w_df = df[df["ward"] == w].copy()
            r = _calc_rlos(w_df, window_days=90)
            if r and r.get("rolling_los") is not None:
                rolling_results[w] = r["rolling_los"]

        if "6F" in rolling_results:
            is_above = rolling_results["6F"] > 21.0
            if is_above == SCENARIO_EXPECTED["los_6f_rolling_above_21"]:
                print(f"✅ los_6f_rolling_above_21: {rolling_results['6F']:.1f} > 21 = {is_above}")
            else:
                errors.append(f"❌ los_6f_rolling_above_21: {rolling_results['6F']:.1f} > 21 = {is_above}, expected {SCENARIO_EXPECTED['los_6f_rolling_above_21']}")

        if "5F" in rolling_results:
            is_below = rolling_results["5F"] < 21.0
            if is_below == SCENARIO_EXPECTED["los_5f_rolling_below_21"]:
                print(f"✅ los_5f_rolling_below_21: {rolling_results['5F']:.1f} < 21 = {is_below}")
            else:
                errors.append(f"❌ los_5f_rolling_below_21: {rolling_results['5F']:.1f} < 21 = {is_below}, expected {SCENARIO_EXPECTED['los_5f_rolling_below_21']}")
    except ImportError:
        warnings_list.append("⚠️  scenario rolling LOS check skipped (import failed)")

    # 7c. Current month average LOS (April data)
    apr_los_rows_5f = apr_5f[apr_5f["avg_los"] > 0]
    apr_los_rows_6f = apr_6f[apr_6f["avg_los"] > 0]
    if len(apr_los_rows_5f) > 0 and len(apr_los_rows_6f) > 0:
        los_5f_mean = apr_los_rows_5f["avg_los"].mean()
        los_6f_mean = apr_los_rows_6f["avg_los"].mean()
        los_overall_mean = pd.concat([apr_los_rows_5f["avg_los"], apr_los_rows_6f["avg_los"]]).mean()
        check("scenario_current_month_los_overall", los_overall_mean, SCENARIO_EXPECTED["current_month_los_overall"])
        check("scenario_current_month_los_6f", los_6f_mean, SCENARIO_EXPECTED["current_month_los_6f"])
        check("scenario_current_month_los_5f", los_5f_mean, SCENARIO_EXPECTED["current_month_los_5f"])
    else:
        warnings_list.append("⚠️  scenario LOS check skipped (no avg_los data)")

    # 7d. Friday discharge percentage
    if "notes" in df.columns:
        apr_all = df[df["date"].dt.month == 4]
        apr_with_discharges = apr_all[apr_all["discharges"] > 0]
        if len(apr_with_discharges) > 0:
            friday_rows = apr_with_discharges[apr_with_discharges["date"].dt.dayofweek == 4]
            total_discharges = apr_with_discharges["discharges"].sum()
            friday_discharges = friday_rows["discharges"].sum()
            friday_pct = friday_discharges / total_discharges * 100 if total_discharges > 0 else 0
            check("scenario_friday_discharge_pct", friday_pct, SCENARIO_EXPECTED["friday_discharge_pct"])
        else:
            warnings_list.append("⚠️  scenario friday discharge check skipped (no discharge data)")

except Exception as e:
    errors.append(f"❌ smoke test crashed: {e}")
    traceback.print_exc()

# --- Report ---
print()
if warnings_list:
    for w in warnings_list:
        print(w)

if errors:
    print("\n🚫 SMOKE TEST FAILED")
    for e in errors:
        print(e)
    sys.exit(1)

print("\n✅ SMOKE TEST PASSED — 主要計算はすべて期待範囲内")
sys.exit(0)
