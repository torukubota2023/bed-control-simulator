#!/usr/bin/env python3
"""Regenerate April 2026 6F data to create a meaningful equal-effort story.

Design goals:
- 5F April avg ~86% (KEEP current data): 5F alone needs 97%+ for remaining days (unrealistic)
- 6F April avg ~90.5% (REDUCE from current 96.9%):
  * 6F alone can still hit 90% monthly single-target (~89% needed → easy)
  * But overall hospital is 88.4% < 90% → needs effort
  * Equal effort Δ ≈ +5pt: 5F→91%, 6F→95.5% (both within 96% cap)
- Past 90 days (Jan-Mar) data: PRESERVED unchanged

This creates a demo where:
- 5F is too low to hit 90% alone
- 6F must aim HIGHER than its own single-target to help
- The extra load is split equally between both wards
"""

import csv
from datetime import date, timedelta

CSV_PATH = "/Users/torukubota/ai-management/data/sample_actual_data_ward_202604.csv"
BEDS = 47
DOW_JP = ["月曜日", "火曜日", "水曜日", "木曜日", "金曜日", "土曜日", "日曜日"]

# Target: sum over 20 days ≈ 851 (avg 42.55 → occ 90.53%)
# Preserve phase structure: A≈4, B≈17-19, C≈20-21
# (total, adm, dis, dis_a, dis_b, dis_c, pa, pb, pc, avg_los)
new_6f_april = [
    # Apr 1 Wed - start
    (43, 0, 0, 0, 0, 0, 4, 18, 21, 18.0),
    # Apr 2 Thu: 43→43 net0 (adm=1, dis=1)
    (43, 1, 1, 0, 0, 1, 4, 18, 21, 19.5),
    # Apr 3 Fri: 43→42 net-1 (adm=1, dis=2) Fri discharge
    (42, 1, 2, 0, 1, 1, 4, 17, 21, 20.8),
    # Apr 4 Sat: 42→42 net0
    (42, 0, 0, 0, 0, 0, 4, 17, 21, 0),
    # Apr 5 Sun: 42→42 net0
    (42, 0, 0, 0, 0, 0, 4, 17, 21, 0),
    # Apr 6 Mon: 42→44 net+2 (adm=3, dis=1) Mon spike
    (44, 3, 1, 0, 0, 1, 4, 19, 21, 22.0),
    # Apr 7 Tue: 44→43 net-1 (adm=1, dis=2)
    (43, 1, 2, 0, 1, 1, 4, 18, 21, 18.5),
    # Apr 8 Wed: 43→43 net0
    (43, 1, 1, 0, 0, 1, 4, 18, 21, 21.0),
    # Apr 9 Thu: 43→43 net0
    (43, 1, 1, 0, 0, 1, 4, 18, 21, 19.0),
    # Apr 10 Fri: 43→42 net-1 Fri
    (42, 1, 2, 0, 1, 1, 4, 17, 21, 17.5),
    # Apr 11 Sat: 42→42
    (42, 0, 0, 0, 0, 0, 4, 17, 21, 0),
    # Apr 12 Sun: 42→42
    (42, 0, 0, 0, 0, 0, 4, 17, 21, 0),
    # Apr 13 Mon: 42→44 net+2 Mon spike
    (44, 3, 1, 0, 0, 1, 4, 19, 21, 24.0),
    # Apr 14 Tue: 44→43 net-1
    (43, 1, 2, 0, 1, 1, 4, 18, 21, 19.0),
    # Apr 15 Wed: 43→43
    (43, 1, 1, 0, 0, 1, 4, 18, 21, 17.0),
    # Apr 16 Thu: 43→43 (phase shift: discharge A, admit A+)
    (43, 1, 1, 1, 0, 0, 4, 18, 21, 15.5),
    # Apr 17 Fri: 43→41 net-2 Fri discharge concentration
    (41, 1, 3, 0, 1, 2, 4, 17, 20, 19.3),
    # Apr 18 Sat: 41→41
    (41, 0, 0, 0, 0, 0, 4, 17, 20, 0),
    # Apr 19 Sun: 41→41
    (41, 0, 0, 0, 0, 0, 4, 17, 20, 0),
    # Apr 20 Mon: 41→44 net+3 (demo day) Mon spike
    (44, 4, 1, 0, 0, 1, 4, 19, 21, 23.0),
]

# --- Verify flow consistency ---
errors = []
for i in range(1, len(new_6f_april)):
    prev_total = new_6f_april[i-1][0]
    total, adm, dis = new_6f_april[i][:3]
    if prev_total + adm - dis != total:
        errors.append(f"Day {i+1}: {prev_total}+{adm}-{dis} != {total}")

# Verify phase sums
for i, row in enumerate(new_6f_april):
    total, _, _, _, _, _, pa, pb, pc, _ = row
    if pa + pb + pc != total:
        errors.append(f"Day {i+1}: phase {pa}+{pb}+{pc}={pa+pb+pc} != total {total}")

# Verify discharge sums
for i, row in enumerate(new_6f_april):
    _, _, dis, da, db, dc, _, _, _, _ = row
    if da + db + dc != dis:
        errors.append(f"Day {i+1}: dis_phase {da}+{db}+{dc}={da+db+dc} != dis {dis}")

if errors:
    print("CONSISTENCY ERRORS:")
    for e in errors:
        print(" ", e)
    raise SystemExit(1)

# --- Stats ---
totals = [r[0] for r in new_6f_april]
avg_patients = sum(totals) / 20
print(f"6F Apr avg: {avg_patients:.2f} patients → {avg_patients/BEDS*100:.2f}% occupancy")
print(f"6F Apr range: {min(totals)}-{max(totals)}")

# --- Read existing CSV ---
with open(CSV_PATH, "r") as f:
    reader = csv.reader(f)
    header = next(reader)
    rows = list(reader)

# --- Rebuild: keep all rows except 6F April, replace with new data ---
start_date = date(2026, 4, 1)
new_rows = []
apr_6f_new_rows = []

# Generate new 6F April rows
for i in range(20):
    d = start_date + timedelta(days=i)
    dow_idx = d.weekday()
    dow_str = DOW_JP[dow_idx]
    total, adm, dis, da, db, dc, pa, pb, pc, avg_los = new_6f_april[i]
    occ = total / BEDS * 100
    empty = BEDS - total

    note_parts = [f"{dow_str} / 稼働率{occ:.1f}% / 空床{empty}床"]
    if occ >= 93:
        note_parts.append("高稼働")
    elif occ < 85:
        note_parts.append("稼働率低め")
    if dow_idx == 0:
        note_parts.append("月曜入院集中")
    if dow_idx == 4 and dis >= 3:
        note_parts.append("金曜退院集中")
    notes = " / ".join(note_parts)

    apr_6f_new_rows.append([
        d.strftime("%Y-%m-%d"), "6F", total, adm, dis,
        da, db, dc, pa, pb, pc, avg_los, notes,
    ])

# Filter original rows: keep all except 6F April 2026
kept_rows = []
for r in rows:
    date_str = r[0]
    ward = r[1]
    if ward == "6F" and date_str.startswith("2026-04"):
        continue  # skip, replaced below
    kept_rows.append(r)

# Insert new 6F April rows
all_rows = kept_rows + apr_6f_new_rows

# Sort: by ward then date (matching original 5F-all-first, 6F-all-first pattern)
def sort_key(row):
    return (row[1], row[0])  # ward, date

all_rows.sort(key=sort_key)

# Write back
with open(CSV_PATH, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(header)
    for r in all_rows:
        w.writerow(r)

print(f"\nCSV updated: {CSV_PATH}")
print(f"Total rows: {len(all_rows)}")

# --- Verify final stats (April only) ---
total_5f = 0
count_5f = 0
total_6f = 0
count_6f = 0
for r in all_rows:
    if r[0].startswith("2026-04"):
        if r[1] == "5F":
            total_5f += int(r[2])
            count_5f += 1
        elif r[1] == "6F":
            total_6f += int(r[2])
            count_6f += 1

avg_5f = total_5f / count_5f
avg_6f = total_6f / count_6f
occ_5f = avg_5f / BEDS * 100
occ_6f = avg_6f / BEDS * 100
overall_occ = (avg_5f + avg_6f) / (BEDS * 2) * 100

print(f"\n=== April 2026 Stats ===")
print(f"5F: {count_5f} days, avg {avg_5f:.2f} patients, occ {occ_5f:.2f}%")
print(f"6F: {count_6f} days, avg {avg_6f:.2f} patients, occ {occ_6f:.2f}%")
print(f"Overall (94 beds): {overall_occ:.2f}%")

# --- Calculate targets ---
target_pct = 90.0
days_total = 30
days_elapsed = 20
days_remaining = 10

# Single-ward targets
single_5f = (target_pct * days_total - occ_5f * days_elapsed) / days_remaining
single_6f = (target_pct * days_total - occ_6f * days_elapsed) / days_remaining
print(f"\n=== Single-ward targets (残り{days_remaining}日) ===")
print(f"5F: {single_5f:.1f}% required → {'HARD/IMPOSSIBLE' if single_5f > 95 else 'feasible'}")
print(f"6F: {single_6f:.1f}% required → {'HARD' if single_6f > 95 else 'achievable'}")

# Equal effort calculation
total_bd_done = BEDS * days_elapsed * (occ_5f + occ_6f) / 100
total_bd_required = BEDS * 2 * days_total * target_pct / 100
bd_remaining_needed = total_bd_required - total_bd_done
needed_per_day = bd_remaining_needed / days_remaining
sum_beds_avg = (occ_5f + occ_6f) * BEDS
sum_beds = BEDS * 2
delta = (needed_per_day * 100 - sum_beds_avg) / sum_beds
print(f"\n=== Equal Effort (均等努力) ===")
print(f"Current overall: {overall_occ:.2f}% (target {target_pct}%)")
print(f"Δ = {delta:+.2f}pt (each ward increases by this amount)")
print(f"5F equal-effort target: {occ_5f + delta:.2f}%")
print(f"6F equal-effort target: {occ_6f + delta:.2f}%")
print(f"Within 96% cap: 5F={occ_5f + delta <= 96}, 6F={occ_6f + delta <= 96}")
