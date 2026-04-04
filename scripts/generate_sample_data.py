"""
ベッドコントロールシミュレーター用サンプルデータ生成スクリプト

4ファイルを生成:
  1. data/doctor_master.csv                   - 医師マスタ（10名）
  2. data/admission_routes.csv                - 入院経路マスタ
  3. data/admission_details.csv               - 入退院詳細（2026年3月、約150入院・140退院）
  4. data/sample_actual_data_ward_202603.csv   - 病棟別日次サマリー

病棟特性:
  5F（外科・整形科, 47床）: 低稼働率 ~85%, 短在院日数 ~12日, 空床目立つ
  6F（内科・ペイン, 47床）: 高稼働率 ~95%, 長在院日数 ~22日, 満床・入院断り

固定シードで決定論的に生成。
"""

import csv
import os
import random
import uuid
from datetime import date, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# 固定シード
# ---------------------------------------------------------------------------
random.seed(42)

# UUIDも固定にするため、namespace + name ベースで生成
_UUID_NS = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


def fixed_uuid(name: str) -> str:
    return str(uuid.uuid5(_UUID_NS, name))


# ---------------------------------------------------------------------------
# パス
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# 1. 医師マスタ
# ---------------------------------------------------------------------------
DOCTORS = [
    {"key": "A", "name": "A医師", "category": "常勤病棟担当"},
    {"key": "B", "name": "B医師", "category": "常勤病棟担当"},
    {"key": "C", "name": "C医師", "category": "常勤病棟担当"},
    {"key": "D", "name": "D医師", "category": "常勤外来のみ"},
    {"key": "E", "name": "E医師", "category": "常勤病棟担当"},
    {"key": "F", "name": "F医師", "category": "非常勤"},
    {"key": "G", "name": "G医師", "category": "常勤救急応援"},
    {"key": "H", "name": "H医師", "category": "常勤病棟担当"},
    {"key": "I", "name": "I医師", "category": "常勤外来のみ"},
    {"key": "J", "name": "J医師", "category": "非常勤"},
]

# UUID を固定生成
for d in DOCTORS:
    d["id"] = fixed_uuid(f"doctor_{d['key']}")

DOCTOR_BY_KEY = {d["key"]: d for d in DOCTORS}

WARD_BEDS = {"5F": 47, "6F": 47}


def write_doctor_master():
    path = DATA_DIR / "doctor_master.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "category", "active"])
        for d in DOCTORS:
            w.writerow([d["id"], d["name"], d["category"], "True"])
    print(f"  -> {path} ({len(DOCTORS)} doctors)")


# ---------------------------------------------------------------------------
# 2. 入院経路マスタ
# ---------------------------------------------------------------------------
ROUTES = ["外来紹介", "救急", "連携室", "ウォークイン"]


def write_admission_routes():
    path = DATA_DIR / "admission_routes.csv"
    rows = []

    # 経路
    for r in ROUTES:
        rows.append({
            "id": fixed_uuid(f"route_{r}"),
            "name": r,
            "type": "経路",
            "doctor_id": "",
            "active": "True",
        })

    # 医師
    for d in DOCTORS:
        rows.append({
            "id": fixed_uuid(f"source_{d['key']}"),
            "name": d["name"],
            "type": "医師",
            "doctor_id": d["id"],
            "active": "True",
        })

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "type", "doctor_id", "active"])
        for r in rows:
            w.writerow([r["id"], r["name"], r["type"], r["doctor_id"], r["active"]])
    print(f"  -> {path} ({len(rows)} routes)")


# ---------------------------------------------------------------------------
# 3. 入退院詳細（日次シミュレーション方式）
# ---------------------------------------------------------------------------

def los_to_phase(los: int) -> str:
    if los <= 5:
        return "A"
    elif los <= 14:
        return "B"
    else:
        return "C"


def _pick_5f_admission_details():
    """5F入院の経路・入院創出医・担当医を決定"""
    r = random.random()
    if r < 0.35:
        route = "外来紹介"
    elif r < 0.55:
        route = "救急"
    elif r < 0.80:
        route = "連携室"
    else:
        route = "ウォークイン"

    if route == "救急":
        source = random.choice(["C", "G", "C"])
    elif route == "外来紹介":
        r2 = random.random()
        if r2 < 0.35:
            source = "D"
        elif r2 < 0.55:
            source = "C"
        elif r2 < 0.70:
            source = "H"
        elif r2 < 0.85:
            source = "I"
        else:
            source = "F"
    elif route == "連携室":
        source = random.choice(["C", "C", "D", "H"])
    else:
        source = random.choice(["C", "H", "G"])

    # 5F担当医: C（外科）or H（ペイン短期）
    if source in ["C"]:
        attending = "C"
    elif source in ["H"]:
        attending = "H"
    else:
        attending = random.choices(["C", "H"], weights=[60, 40])[0]

    if random.random() < 0.03:
        attending = "F"

    return route, source, attending


def _pick_6f_admission_details():
    """6F入院の経路・入院創出医・担当医を決定"""
    r = random.random()
    if r < 0.45:
        route = "外来紹介"
    elif r < 0.70:
        route = "救急"
    elif r < 0.85:
        route = "連携室"
    else:
        route = "ウォークイン"

    if route == "救急":
        source = "G" if random.random() < 0.70 else random.choice(["A", "B", "E"])
    elif route == "外来紹介":
        r2 = random.random()
        if r2 < 0.40:
            source = "D"
        elif r2 < 0.58:
            source = "A"
        elif r2 < 0.74:
            source = "B"
        elif r2 < 0.88:
            source = "E"
        else:
            source = "I"
    elif route == "連携室":
        source = random.choice(["A", "B", "E", "D"])
    else:
        source = random.choice(["A", "B", "E", "G"])

    if route == "救急" and source == "G":
        if random.random() < 0.45:
            attending = "G"
        else:
            attending = random.choice(["A", "B", "E"])
    else:
        attending = random.choices(["A", "B", "E"], weights=[35, 35, 30])[0]

    return route, source, attending


def _pick_5f_discharge_details():
    """5F退院の担当医・LOS・フェーズを決定"""
    # C医師55%, H医師42%, F医師3%
    r = random.random()
    if r < 0.55:
        doc = "C"
        # 外科: 短〜中LOS（平均14日程度）
        los = max(5, int(random.gauss(14, 4)))
        los = min(los, 22)
    elif r < 0.97:
        doc = "H"
        # ペイン: 短期入院（平均7日程度）
        los = max(2, int(random.gauss(7, 2)))
        los = min(los, 12)
    else:
        doc = "F"
        los = max(5, int(random.gauss(10, 3)))
        los = min(los, 16)

    phase = los_to_phase(los)
    return doc, los, phase


def _pick_6f_discharge_details(is_friday=False):
    """6F退院の担当医・LOS・フェーズを決定"""
    # 金曜日はB医師の退院確率UP
    if is_friday:
        # B医師60%, A医師22%, E医師10%, G医師8%
        r = random.random()
        if r < 0.60:
            doc = "B"
        elif r < 0.82:
            doc = "A"
        elif r < 0.92:
            doc = "E"
        else:
            doc = "G"
    else:
        # 通常日: A医師30%, B医師15%, E医師25%, G医師25%, F5%, J0%（稀）
        r = random.random()
        if r < 0.30:
            doc = "A"
        elif r < 0.45:
            doc = "B"
        elif r < 0.70:
            doc = "E"
        elif r < 0.95:
            doc = "G"
        elif r < 0.98:
            doc = "F"
        else:
            doc = "J"

    # 6F: 長いLOS
    if doc == "E":
        los = max(15, int(random.gauss(28, 5)))
        los = min(los, 42)
    elif doc == "A":
        los = max(12, int(random.gauss(24, 5)))
        los = min(los, 38)
    elif doc == "B":
        los = max(10, int(random.gauss(22, 5)))
        los = min(los, 32)
    elif doc == "G":
        los = max(8, int(random.gauss(19, 4)))
        los = min(los, 28)
    else:  # F, J
        los = max(12, int(random.gauss(17, 4)))
        los = min(los, 22)

    phase = los_to_phase(los)
    return doc, los, phase


def generate_admission_details():
    """日次シミュレーションで入退院を生成

    各日の入退院数を稼働率ターゲットに基づき決定:
    - 5F: 稼働率 ~85% (40人前後/47床)
    - 6F: 稼働率 ~95% (45人前後/47床)
    """
    start_date = date(2026, 3, 1)
    end_date = date(2026, 3, 31)
    num_days = (end_date - start_date).days + 1

    # 初期患者数
    patients_5f = 41
    patients_6f = 44

    records = []
    admission_count = 0
    discharge_count = 0

    for day_offset in range(num_days):
        current_date = start_date + timedelta(days=day_offset)
        dow = current_date.weekday()  # 0=Mon ... 6=Sun
        is_weekend = dow >= 5
        is_friday = dow == 4

        # ====== 5F: 低稼働パターン ======
        # 目標: ~40人 (85%)
        # 入院: 平日2-3件、週末1件
        # 退院: 入院より多め → 空床が残る
        if is_weekend:
            n_adm_5f = random.choice([1, 1, 1, 2])
            n_dis_5f = random.choice([1, 1, 2, 2])
        else:
            # 基本入院数
            n_adm_5f = random.choice([2, 2, 3, 3])
            # 退院数: 入院と同等〜やや多め（空床を維持）
            base_dis = random.choice([2, 2, 2, 3, 3])
            # 患者数が目標(40)より多ければ退院増
            if patients_5f > 41:
                base_dis += 1
            elif patients_5f < 39:
                base_dis = max(1, base_dis - 1)
            n_dis_5f = base_dis

        # 退院数は患者数を超えない
        n_dis_5f = min(n_dis_5f, patients_5f)
        # 入院数はベッド数を超えない
        n_adm_5f = min(n_adm_5f, WARD_BEDS["5F"] - patients_5f + n_dis_5f)
        n_adm_5f = max(0, n_adm_5f)

        # 5F入院レコード生成
        for _ in range(n_adm_5f):
            route, source, attending = _pick_5f_admission_details()
            records.append({
                "id": fixed_uuid(f"adm_{current_date}_{admission_count}"),
                "date": current_date.isoformat(),
                "ward": "5F",
                "event_type": "admission",
                "route": route,
                "source_doctor": DOCTOR_BY_KEY[source]["name"],
                "attending_doctor": DOCTOR_BY_KEY[attending]["name"],
                "los_days": "",
                "phase": "",
            })
            admission_count += 1

        # 5F退院レコード生成
        for _ in range(n_dis_5f):
            doc, los, phase = _pick_5f_discharge_details()
            records.append({
                "id": fixed_uuid(f"dis_{current_date}_{discharge_count}"),
                "date": current_date.isoformat(),
                "ward": "5F",
                "event_type": "discharge",
                "route": "",
                "source_doctor": "",
                "attending_doctor": DOCTOR_BY_KEY[doc]["name"],
                "los_days": str(los),
                "phase": phase,
            })
            discharge_count += 1

        patients_5f = patients_5f + n_adm_5f - n_dis_5f

        # ====== 6F: 高稼働パターン ======
        # 目標: ~45人 (95%)
        # 入院: 平日2件（満床で受けられない日も）
        # 退院: 少なめ → 満床が続く、金曜に集中
        if is_weekend:
            n_adm_6f = random.choice([1, 1, 1, 2])
            n_dis_6f = random.choice([0, 0, 1, 1])
        elif is_friday:
            # 金曜は退院集中日
            n_adm_6f = random.choice([1, 2, 2, 2])
            n_dis_6f = random.choice([3, 4, 4, 5, 5])
        else:
            n_adm_6f = random.choice([2, 2, 2, 3])
            # 通常日は退院少ない（月〜木）
            n_dis_6f = random.choice([1, 1, 2, 2, 2])
            # 患者数が多すぎれば退院増
            if patients_6f >= 47:
                n_dis_6f += 1
            elif patients_6f < 43:
                n_dis_6f = max(0, n_dis_6f - 1)

        n_dis_6f = min(n_dis_6f, patients_6f)
        # 満床なら入院制限
        available_6f = WARD_BEDS["6F"] - patients_6f + n_dis_6f
        if available_6f <= 0:
            n_adm_6f = 0
        else:
            n_adm_6f = min(n_adm_6f, available_6f)
        n_adm_6f = max(0, n_adm_6f)

        # 6F入院レコード生成
        for _ in range(n_adm_6f):
            route, source, attending = _pick_6f_admission_details()
            records.append({
                "id": fixed_uuid(f"adm_{current_date}_{admission_count}"),
                "date": current_date.isoformat(),
                "ward": "6F",
                "event_type": "admission",
                "route": route,
                "source_doctor": DOCTOR_BY_KEY[source]["name"],
                "attending_doctor": DOCTOR_BY_KEY[attending]["name"],
                "los_days": "",
                "phase": "",
            })
            admission_count += 1

        # 6F退院レコード生成
        for _ in range(n_dis_6f):
            doc, los, phase = _pick_6f_discharge_details(is_friday=is_friday)
            records.append({
                "id": fixed_uuid(f"dis_{current_date}_{discharge_count}"),
                "date": current_date.isoformat(),
                "ward": "6F",
                "event_type": "discharge",
                "route": "",
                "source_doctor": "",
                "attending_doctor": DOCTOR_BY_KEY[doc]["name"],
                "los_days": str(los),
                "phase": phase,
            })
            discharge_count += 1

        patients_6f = patients_6f + n_adm_6f - n_dis_6f

    print(f"  入院数: {admission_count}")
    print(f"  退院数: {discharge_count}")

    # 日付順にソート
    records.sort(key=lambda x: (x["date"], x["event_type"]))

    # CSVに書き出し
    path = DATA_DIR / "admission_details.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "date", "ward", "event_type", "route",
                     "source_doctor", "attending_doctor", "los_days", "phase"])
        for r in records:
            w.writerow([
                r["id"], r["date"], r["ward"], r["event_type"],
                r["route"], r["source_doctor"], r["attending_doctor"],
                r["los_days"], r["phase"],
            ])
    print(f"  -> {path} ({len(records)} records)")
    return records


# ---------------------------------------------------------------------------
# 4. 病棟別日次サマリー生成
# ---------------------------------------------------------------------------
DOW_NAMES_JP = ["月曜日", "火曜日", "水曜日", "木曜日", "金曜日", "土曜日", "日曜日"]


def generate_ward_daily_summary(records):
    """入退院詳細データから病棟別日次サマリーを生成"""
    start_date = date(2026, 3, 1)
    end_date = date(2026, 3, 31)
    num_days = (end_date - start_date).days + 1

    # 初期患者数（admission_detailsと同じ）
    current_patients = {"5F": 41, "6F": 44}

    # 日別・病棟別の入退院を集計
    daily_events = {}
    for day_offset in range(num_days):
        d = start_date + timedelta(days=day_offset)
        for ward in ["5F", "6F"]:
            daily_events[(d, ward)] = {
                "admissions": 0,
                "discharges": 0,
                "discharge_a": 0,
                "discharge_b": 0,
                "discharge_c": 0,
                "los_list": [],
            }

    for r in records:
        d = date.fromisoformat(r["date"])
        ward = r["ward"]
        key = (d, ward)
        if key not in daily_events:
            continue
        if r["event_type"] == "admission":
            daily_events[key]["admissions"] += 1
        elif r["event_type"] == "discharge":
            daily_events[key]["discharges"] += 1
            phase = r["phase"]
            if phase == "A":
                daily_events[key]["discharge_a"] += 1
            elif phase == "B":
                daily_events[key]["discharge_b"] += 1
            elif phase == "C":
                daily_events[key]["discharge_c"] += 1
            if r["los_days"]:
                daily_events[key]["los_list"].append(int(r["los_days"]))

    # 日次サマリー生成
    rows = []
    # フェーズ構成比
    phase_ratio = {
        "5F": {"a": 0.28, "b": 0.45, "c": 0.27},
        "6F": {"a": 0.08, "b": 0.25, "c": 0.67},
    }

    for day_offset in range(num_days):
        d = start_date + timedelta(days=day_offset)
        dow = d.weekday()
        dow_name = DOW_NAMES_JP[dow]

        for ward in ["5F", "6F"]:
            ev = daily_events[(d, ward)]
            beds = WARD_BEDS[ward]

            current_patients[ward] = current_patients[ward] + ev["admissions"] - ev["discharges"]
            current_patients[ward] = max(0, min(beds, current_patients[ward]))
            total = current_patients[ward]

            occupancy = total / beds * 100

            # フェーズ別患者数
            pr = phase_ratio[ward]
            pa = round(total * pr["a"])
            pb = round(total * pr["b"])
            pc = total - pa - pb

            # 平均在院日数
            if ev["los_list"]:
                avg_los = sum(ev["los_list"]) / len(ev["los_list"])
            else:
                avg_los = 12.0 if ward == "5F" else 22.0

            notes = _generate_note(ward, dow_name, occupancy, total, beds,
                                   ev["admissions"], ev["discharges"], d)

            rows.append({
                "date": d.isoformat(),
                "ward": ward,
                "total_patients": total,
                "new_admissions": ev["admissions"],
                "discharges": ev["discharges"],
                "discharge_a": ev["discharge_a"],
                "discharge_b": ev["discharge_b"],
                "discharge_c": ev["discharge_c"],
                "phase_a_count": pa,
                "phase_b_count": pb,
                "phase_c_count": pc,
                "avg_los": round(avg_los, 1),
                "notes": notes,
            })

    path = DATA_DIR / "sample_actual_data_ward_202603.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["date", "ward", "total_patients", "new_admissions",
                     "discharges", "discharge_a", "discharge_b", "discharge_c",
                     "phase_a_count", "phase_b_count", "phase_c_count",
                     "avg_los", "notes"])
        for r in rows:
            w.writerow([
                r["date"], r["ward"], r["total_patients"],
                r["new_admissions"], r["discharges"],
                r["discharge_a"], r["discharge_b"], r["discharge_c"],
                r["phase_a_count"], r["phase_b_count"], r["phase_c_count"],
                r["avg_los"], r["notes"],
            ])
    print(f"  -> {path} ({len(rows)} rows)")
    return rows


def _generate_note(ward, dow_name, occupancy, total, beds,
                   admissions, discharges, d):
    """病棟特性に応じたノートを生成"""
    parts = [dow_name]

    if ward == "5F":
        empty = beds - total
        parts.append(f"{occupancy:.1f}%")
        if occupancy <= 80:
            parts.append(f"空床{empty}床 稼働率低迷")
        elif occupancy <= 85:
            parts.append(f"空床{empty}床 稼働率低め")
        elif occupancy <= 88:
            parts.append(f"空床{empty}床")
        else:
            parts.append("稼働率回復中")

        if discharges > admissions + 1:
            parts.append("退院超過")
        elif admissions > discharges + 1:
            parts.append("入院増加も空床残る")

    else:  # 6F
        empty = beds - total
        parts.append(f"{occupancy:.1f}%")
        if occupancy >= 100:
            parts.append("満床 入院断り発生")
        elif occupancy >= 97:
            parts.append(f"残{empty}床 入院制限中")
        elif occupancy >= 95:
            parts.append("満床近い 受入余力なし")
        elif occupancy >= 91:
            parts.append("高稼働")
        else:
            parts.append("稼働率やや低下")

        if d.weekday() == 4 and discharges >= 4:
            parts.append(f"金曜退院集中({discharges}名)")
        elif d.weekday() == 4 and discharges >= 3:
            parts.append("金曜退院多め")

        if admissions == 0 and d.weekday() < 5 and occupancy >= 95:
            parts.append("新規受入困難")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# 検証
# ---------------------------------------------------------------------------
def verify(records, ward_rows=None):
    """生成データの品質チェック"""
    admissions = [r for r in records if r["event_type"] == "admission"]
    discharges = [r for r in records if r["event_type"] == "discharge"]

    print("\n=== 検証結果 ===")
    print(f"総入院数: {len(admissions)}")
    print(f"総退院数: {len(discharges)}")

    # 病棟別入院数
    ward_5f_adm = [r for r in admissions if r["ward"] == "5F"]
    ward_6f_adm = [r for r in admissions if r["ward"] == "6F"]
    print(f"\n5F入院: {len(ward_5f_adm)}, 6F入院: {len(ward_6f_adm)}")

    # 病棟別退院数
    ward_5f_dis = [r for r in discharges if r["ward"] == "5F"]
    ward_6f_dis = [r for r in discharges if r["ward"] == "6F"]
    print(f"5F退院: {len(ward_5f_dis)}, 6F退院: {len(ward_6f_dis)}")

    # 病棟別平均在院日数
    if ward_5f_dis:
        avg_5f = sum(int(r["los_days"]) for r in ward_5f_dis if r["los_days"]) / len(ward_5f_dis)
        print(f"5F平均在院日数: {avg_5f:.1f}日")
    if ward_6f_dis:
        avg_6f = sum(int(r["los_days"]) for r in ward_6f_dis if r["los_days"]) / len(ward_6f_dis)
        print(f"6F平均在院日数: {avg_6f:.1f}日")

    # B医師の金曜退院率（6F）
    b_discharges = [r for r in discharges if r["attending_doctor"] == "B医師"]
    b_friday = [r for r in b_discharges
                if date.fromisoformat(r["date"]).weekday() == 4]
    b_fri_pct = len(b_friday) / len(b_discharges) * 100 if b_discharges else 0
    print(f"\nB医師の金曜退院率: {b_fri_pct:.0f}% ({len(b_friday)}/{len(b_discharges)})")

    # A医師の金曜退院率
    a_discharges = [r for r in discharges if r["attending_doctor"] == "A医師"]
    a_friday = [r for r in a_discharges
                if date.fromisoformat(r["date"]).weekday() == 4]
    a_fri_pct = len(a_friday) / len(a_discharges) * 100 if a_discharges else 0
    print(f"A医師の金曜退院率: {a_fri_pct:.0f}% ({len(a_friday)}/{len(a_discharges)})")

    # E医師のC群割合
    e_discharges = [r for r in discharges if r["attending_doctor"] == "E医師"]
    e_c_phase = [r for r in e_discharges if r["phase"] == "C"]
    e_c_pct = len(e_c_phase) / len(e_discharges) * 100 if e_discharges else 0
    print(f"E医師のC群割合: {e_c_pct:.0f}% ({len(e_c_phase)}/{len(e_discharges)})")

    # D医師の入院創出数
    d_source = [r for r in admissions if r["source_doctor"] == "D医師"]
    print(f"D医師の入院創出数: {len(d_source)}")

    # G医師の救急経路率
    g_admissions = [r for r in admissions if r["source_doctor"] == "G医師"]
    g_emergency = [r for r in g_admissions if r["route"] == "救急"]
    g_em_pct = len(g_emergency) / len(g_admissions) * 100 if g_admissions else 0
    print(f"G医師の救急経路率: {g_em_pct:.0f}% ({len(g_emergency)}/{len(g_admissions)})")

    # H医師のA群割合
    h_discharges = [r for r in discharges if r["attending_doctor"] == "H医師"]
    h_a_phase = [r for r in h_discharges if r["phase"] == "A"]
    h_a_pct = len(h_a_phase) / len(h_discharges) * 100 if h_discharges else 0
    print(f"H医師のA群割合: {h_a_pct:.0f}% ({len(h_a_phase)}/{len(h_discharges)})")

    # 週末退院
    weekend_dis = [r for r in discharges
                   if date.fromisoformat(r["date"]).weekday() >= 5]
    print(f"週末退院数: {len(weekend_dis)}")

    # 6F金曜退院集中度
    fri_6f_dis = [r for r in discharges
                  if r["ward"] == "6F"
                  and date.fromisoformat(r["date"]).weekday() == 4]
    print(f"6F金曜退院数: {len(fri_6f_dis)}")

    # 病棟別稼働率
    if ward_rows:
        print("\n=== 病棟別稼働率 ===")
        for ward in ["5F", "6F"]:
            ward_data = [r for r in ward_rows if r["ward"] == ward]
            if ward_data:
                patients = [r["total_patients"] for r in ward_data]
                beds = WARD_BEDS[ward]
                avg_occ = sum(patients) / len(patients) / beds * 100
                max_p = max(patients)
                min_p = min(patients)
                full_days = sum(1 for p in patients if p >= beds)
                print(f"{ward}: 平均稼働率 {avg_occ:.1f}% "
                      f"(患者数 {min_p}-{max_p}, 満床日数 {full_days})")

        # 全体稼働率
        daily_totals = {}
        for r in ward_rows:
            d = r["date"]
            daily_totals[d] = daily_totals.get(d, 0) + r["total_patients"]
        total_beds = sum(WARD_BEDS.values())
        avg_total_occ = sum(daily_totals.values()) / len(daily_totals) / total_beds * 100
        print(f"全体: 平均稼働率 {avg_total_occ:.1f}% (94床)")


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("サンプルデータ生成開始...")
    print("\n1. 医師マスタ")
    write_doctor_master()
    print("\n2. 入院経路マスタ")
    write_admission_routes()
    print("\n3. 入退院詳細")
    records = generate_admission_details()
    print("\n4. 病棟別日次サマリー")
    ward_rows = generate_ward_daily_summary(records)
    verify(records, ward_rows)
    print("\n生成完了!")
