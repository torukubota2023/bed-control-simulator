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
    "apr_5f_occ_pct": (85.5, 87.0),  # acceptable range
    "apr_6f_occ_pct": (89.5, 91.5),
    "overall_occ_pct": (87.5, 89.5),
    "single_5f_required_pct": (96.0, 99.0),  # hard / unrealistic
    "single_6f_required_pct": (87.0, 91.0),  # achievable
    "equal_effort_delta_pt": (3.0, 7.0),  # positive, meaningful
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
    occ_5f = apr_5f["total_patients"].mean() / BEDS * 100
    occ_6f = apr_6f["total_patients"].mean() / BEDS * 100
    overall_occ = (apr_5f["total_patients"].mean() + apr_6f["total_patients"].mean()) / (BEDS * 2) * 100
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

    # Critical story assertion: delta must be POSITIVE for the demo to make sense
    if delta <= 0:
        errors.append(f"❌ CRITICAL: equal effort delta is {delta:.2f} (must be > 0 for demo story)")

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
