#!/usr/bin/env python3
"""Generate sample_actual_data_ward_202604.csv with adjusted occupancy rates.

[DEPRECATED — 2026-04-18]
このスクリプトは 2026年4月単月（20 日分）のみを生成する古い教育用デモデータ
ジェネレーター。年度全体の季節性・連休対応は
:file:`scripts/generate_demo_data_2026fy.py` の ``generate_yearly_data()`` を使用すること。
既存 CSV (`data/sample_actual_data_ward_202604.csv`) の再生成時のみ本スクリプトを利用する。
"""

import csv
import os
from datetime import date, timedelta

OUTPUT_PATH = "/Users/torukubota/ai-management/data/sample_actual_data_ward_202604.csv"

BEDS_PER_WARD = 47
DOW_JP = ["月曜日", "火曜日", "水曜日", "木曜日", "金曜日", "土曜日", "日曜日"]

# Apr 1 = Wed (weekday index 2)
start_date = date(2026, 4, 1)

# --- 5F data: target avg ~87% (~41 patients), range 39-43 ---
# Hand-crafted to hit ~41 avg with Monday spikes, Friday discharge concentration, mid-month dip
# Format: (total, admissions, discharges, dis_a, dis_b, dis_c, pa, pb, pc, avg_los)
data_5f = [
    # Apr 1 Wed - start
    (41, 0, 0, 0, 0, 0, 12, 18, 11, 8.5),
    # Apr 2 Thu
    (42, 3, 2, 1, 1, 0, 12, 19, 11, 7.2),
    # Apr 3 Fri - discharge concentration
    (39, 1, 4, 1, 2, 1, 11, 17, 11, 10.1),
    # Apr 4 Sat
    (40, 1, 0, 0, 0, 0, 11, 18, 11, 7.5),
    # Apr 5 Sun
    (40, 0, 0, 0, 0, 0, 11, 18, 11, 0),
    # Apr 6 Mon - admission spike
    (43, 5, 2, 1, 1, 0, 12, 19, 12, 5.0),
    # Apr 7 Tue
    (42, 2, 3, 1, 1, 1, 12, 19, 11, 9.8),
    # Apr 8 Wed
    (42, 2, 2, 1, 1, 0, 12, 19, 11, 8.0),
    # Apr 9 Thu
    (41, 2, 3, 1, 1, 1, 11, 19, 11, 11.5),
    # Apr 10 Fri - discharge concentration
    (40, 2, 3, 1, 1, 1, 11, 18, 11, 10.3),
    # Apr 11 Sat
    (40, 1, 1, 0, 1, 0, 11, 18, 11, 12.0),
    # Apr 12 Sun - mid-month dip
    (40, 0, 0, 0, 0, 0, 11, 18, 11, 0),
    # Apr 13 Mon - admission spike
    (43, 4, 1, 1, 0, 0, 12, 19, 12, 4.0),
    # Apr 14 Tue
    (42, 1, 2, 0, 1, 1, 12, 18, 12, 13.5),
    # Apr 15 Wed
    (42, 2, 2, 1, 1, 0, 12, 18, 12, 7.5),
    # Apr 16 Thu
    (41, 1, 2, 1, 1, 0, 11, 18, 12, 6.8),
    # Apr 17 Fri - discharge concentration
    (39, 1, 3, 1, 1, 1, 11, 17, 11, 10.7),
    # Apr 18 Sat
    (40, 1, 0, 0, 0, 0, 12, 17, 11, 16.0),
    # Apr 19 Sun
    (40, 0, 0, 0, 0, 0, 12, 17, 11, 0),
    # Apr 20 Mon - demo day: 41 patients (87.2%)
    (41, 4, 3, 1, 1, 1, 11, 19, 11, 8.5),
]

# --- 6F data: target avg ~92% (~43 patients), range 42-44 ---
data_6f = [
    # Apr 1 Wed
    (44, 0, 0, 0, 0, 0, 4, 11, 29, 16.5),
    # Apr 2 Thu
    (44, 2, 2, 0, 1, 1, 4, 11, 29, 18.2),
    # Apr 3 Fri
    (43, 1, 2, 0, 0, 2, 4, 11, 28, 21.5),
    # Apr 4 Sat
    (43, 1, 1, 0, 0, 1, 4, 11, 28, 19.0),
    # Apr 5 Sun
    (43, 0, 0, 0, 0, 0, 4, 11, 28, 0),
    # Apr 6 Mon
    (44, 2, 1, 0, 0, 1, 4, 11, 29, 25.0),
    # Apr 7 Tue
    (43, 1, 2, 0, 1, 1, 4, 10, 29, 19.5),
    # Apr 8 Wed
    (44, 2, 1, 0, 0, 1, 4, 11, 29, 22.0),
    # Apr 9 Thu
    (44, 1, 1, 0, 0, 1, 4, 11, 29, 20.0),
    # Apr 10 Fri
    (43, 1, 2, 0, 1, 1, 4, 10, 29, 17.5),
    # Apr 11 Sat
    (43, 1, 1, 0, 0, 1, 4, 10, 29, 24.0),
    # Apr 12 Sun
    (43, 0, 0, 0, 0, 0, 4, 10, 29, 0),
    # Apr 13 Mon
    (44, 2, 1, 0, 0, 1, 4, 11, 29, 28.0),
    # Apr 14 Tue
    (43, 1, 2, 0, 1, 1, 4, 10, 29, 18.0),
    # Apr 15 Wed
    (43, 2, 2, 1, 0, 1, 4, 11, 28, 15.5),
    # Apr 16 Thu
    (44, 2, 1, 0, 0, 1, 4, 11, 29, 26.0),
    # Apr 17 Fri
    (42, 1, 3, 0, 1, 2, 4, 10, 28, 19.3),
    # Apr 18 Sat
    (42, 1, 1, 0, 0, 1, 4, 10, 28, 20.0),
    # Apr 19 Sun
    (42, 0, 0, 0, 0, 0, 4, 10, 28, 0),
    # Apr 20 Mon - demo day: 43 patients (91.5%)
    (43, 2, 1, 0, 0, 1, 4, 10, 29, 27.0),
]

def make_notes(d, total):
    dow_idx = d.weekday()  # 0=Mon
    dow_str = DOW_JP[dow_idx]
    occ = total / BEDS_PER_WARD * 100
    empty = BEDS_PER_WARD - total
    parts = [f"{dow_str} / 稼働率{occ:.1f}% / 空床{empty}床"]
    if occ >= 93:
        parts.append("高稼働")
    elif occ < 85:
        parts.append("稼働率低め")
    if dow_idx == 0:  # Monday
        parts.append("月曜入院集中")
    if dow_idx == 4:  # Friday
        # check if discharges >= 3 (we'll pass this info)
        pass  # handled below
    return parts, occ

def verify_flow(ward_name, data):
    """Verify total_patients = prev + admissions - discharges for day 2+."""
    errors = []
    for i in range(1, len(data)):
        prev_total = data[i-1][0]
        total, adm, dis = data[i][0], data[i][1], data[i][2]
        expected = prev_total + adm - dis
        if expected != total:
            d = start_date + timedelta(days=i)
            errors.append(f"  {ward_name} {d}: expected {expected}, got {total} (prev={prev_total} +{adm} -{dis})")
    return errors

# Verify consistency before writing
errors = verify_flow("5F", data_5f) + verify_flow("6F", data_6f)

# Also verify phase sums
for i, row in enumerate(data_5f):
    total, _, _, _, _, _, pa, pb, pc, _ = row
    if pa + pb + pc != total:
        d = start_date + timedelta(days=i)
        errors.append(f"  5F {d}: phase sum {pa+pb+pc} != total {total}")

for i, row in enumerate(data_6f):
    total, _, _, _, _, _, pa, pb, pc, _ = row
    if pa + pb + pc != total:
        d = start_date + timedelta(days=i)
        errors.append(f"  6F {d}: phase sum {pa+pb+pc} != total {total}")

# Also verify discharge sum
for i, row in enumerate(data_5f):
    _, _, dis, da, db, dc, _, _, _, _ = row
    if da + db + dc != dis:
        d = start_date + timedelta(days=i)
        errors.append(f"  5F {d}: discharge sum {da+db+dc} != discharges {dis}")

for i, row in enumerate(data_6f):
    _, _, dis, da, db, dc, _, _, _, _ = row
    if da + db + dc != dis:
        d = start_date + timedelta(days=i)
        errors.append(f"  6F {d}: discharge sum {da+db+dc} != discharges {dis}")

if errors:
    print("CONSISTENCY ERRORS:")
    for e in errors:
        print(e)
    print("\nFixing flow errors...")

# Fix flow issues in 5F - adjust admissions/discharges to match totals
def fix_flow(data):
    """Recompute admissions to match total flow."""
    fixed = list(data)
    for i in range(1, len(data)):
        prev_total = fixed[i-1][0]
        row = list(fixed[i])
        total = row[0]
        needed_net = total - prev_total  # net = adm - dis
        current_net = row[1] - row[2]
        if current_net != needed_net:
            # Adjust admissions
            row[1] = needed_net + row[2]
            if row[1] < 0:
                # Need to adjust discharges too
                row[2] = row[2] + row[1]  # reduce discharges
                row[1] = 0
            fixed[i] = tuple(row)
    return fixed

data_5f = fix_flow(data_5f)
data_6f = fix_flow(data_6f)

# Re-verify
errors2 = verify_flow("5F", data_5f) + verify_flow("6F", data_6f)
if errors2:
    print("STILL HAVE ERRORS after fix:")
    for e in errors2:
        print(e)
else:
    print("Flow consistency: OK")

# Write CSV
rows = []
header = ["date","ward","total_patients","new_admissions","discharges",
          "discharge_a","discharge_b","discharge_c",
          "phase_a_count","phase_b_count","phase_c_count","avg_los","notes"]

for i in range(20):
    d = start_date + timedelta(days=i)
    dow_idx = d.weekday()

    for ward_name, data in [("5F", data_5f), ("6F", data_6f)]:
        total, adm, dis, da, db, dc, pa, pb, pc, avg_los = data[i]

        note_parts, occ = make_notes(d, total)

        # Add Friday discharge flag
        if dow_idx == 4 and dis >= 3:
            note_parts.append("金曜退院集中")

        notes = " / ".join(note_parts)

        rows.append([
            d.strftime("%Y-%m-%d"), ward_name, total, adm, dis,
            da, db, dc, pa, pb, pc, avg_los, notes
        ])

# Sort: all 5F first, then all 6F (matching original format)
rows_5f = [r for r in rows if r[1] == "5F"]
rows_6f = [r for r in rows if r[1] == "6F"]
all_rows = rows_5f + rows_6f

with open(OUTPUT_PATH, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(header)
    for r in all_rows:
        w.writerow(r)

print(f"\nCSV written to {OUTPUT_PATH}")

# --- Stats ---
print("\n=== STATISTICS ===")

totals_5f = [data_5f[i][0] for i in range(20)]
totals_6f = [data_6f[i][0] for i in range(20)]

avg_5f = sum(totals_5f) / len(totals_5f)
avg_6f = sum(totals_6f) / len(totals_6f)
avg_all = (avg_5f + avg_6f) / 2

occ_5f = avg_5f / BEDS_PER_WARD * 100
occ_6f = avg_6f / BEDS_PER_WARD * 100
occ_all = (avg_5f + avg_6f) / (BEDS_PER_WARD * 2) * 100

print(f"5F: avg patients = {avg_5f:.1f}, avg occupancy = {occ_5f:.1f}%")
print(f"6F: avg patients = {avg_6f:.1f}, avg occupancy = {occ_6f:.1f}%")
print(f"Overall: avg patients = {avg_5f + avg_6f:.1f}/94, avg occupancy = {occ_all:.1f}%")

print(f"\nApr 7 (today): 5F={data_5f[6][0]}, 6F={data_6f[6][0]}, total={data_5f[6][0]+data_6f[6][0]}")
print(f"Apr 20 (demo): 5F={data_5f[19][0]}, 6F={data_6f[19][0]}, total={data_5f[19][0]+data_6f[19][0]}")

# Phase averages for 5F
pa_5f = sum(data_5f[i][6] for i in range(20)) / 20
pb_5f = sum(data_5f[i][7] for i in range(20)) / 20
pc_5f = sum(data_5f[i][8] for i in range(20)) / 20
print(f"\n5F phase avg: A={pa_5f:.1f}, B={pb_5f:.1f}, C={pc_5f:.1f}")

pa_6f = sum(data_6f[i][6] for i in range(20)) / 20
pb_6f = sum(data_6f[i][7] for i in range(20)) / 20
pc_6f = sum(data_6f[i][8] for i in range(20)) / 20
print(f"6F phase avg: A={pa_6f:.1f}, B={pb_6f:.1f}, C={pc_6f:.1f}")

# --- Holistic helper calculation ---
# If 5F maintains current avg for remaining 10 days (Apr 11-20),
# what does 6F need to hit 90% overall?
print("\n=== HOLISTIC HELPER CALCULATION ===")
# First 10 days (Apr 1-10) are fixed
sum_5f_first10 = sum(totals_5f[:10])
sum_6f_first10 = sum(totals_6f[:10])
sum_5f_last10 = sum(totals_5f[10:])
# 5F avg for last 10 days
avg_5f_last10 = sum_5f_last10 / 10
print(f"5F first 10 days sum: {sum_5f_first10}, avg: {sum_5f_first10/10:.1f}")
print(f"5F last 10 days sum: {sum_5f_last10}, avg: {avg_5f_last10:.1f}")

# Target: overall 90% = 84.6 patients/day across both wards
target_total_per_day = BEDS_PER_WARD * 2 * 0.90  # 84.6
target_total_20days = target_total_per_day * 20  # 1692

current_total = sum(totals_5f) + sum(totals_6f)
print(f"\nCurrent 20-day total: {current_total}")
print(f"Target 20-day total for 90%: {target_total_20days:.0f}")
print(f"Gap: {target_total_20days - current_total:.0f} patient-days")

# If 5F stays at current avg, what does 6F need for remaining 10 days?
needed_6f_last10 = target_total_20days - sum_5f_first10 - sum_6f_first10 - sum_5f_last10
actual_6f_last10 = sum(totals_6f[10:])
needed_6f_avg_last10 = needed_6f_last10 / 10
needed_6f_occ_last10 = needed_6f_avg_last10 / BEDS_PER_WARD * 100

print(f"\n6F actual last 10 days: sum={actual_6f_last10}, avg={actual_6f_last10/10:.1f}")
print(f"6F needed last 10 days for 90% overall: sum={needed_6f_last10:.0f}, avg={needed_6f_avg_last10:.1f}")
print(f"6F needed occupancy for remaining 10 days: {needed_6f_occ_last10:.1f}%")

print(f"\n5F range: {min(totals_5f)}-{max(totals_5f)}")
print(f"6F range: {min(totals_6f)}-{max(totals_6f)}")
