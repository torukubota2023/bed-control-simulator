"""
ベッドコントロールシミュレーター用サンプルデータ生成スクリプト

3ファイルを生成:
  1. data/doctor_master.csv      - 医師マスタ（10名）
  2. data/admission_routes.csv   - 入院経路マスタ
  3. data/admission_details.csv  - 入退院詳細（2026年3月、約150入院・140退院）

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
# 3. 入退院詳細
# ---------------------------------------------------------------------------

def los_to_phase(los: int) -> str:
    if los <= 5:
        return "A"
    elif los <= 14:
        return "B"
    else:
        return "C"


def generate_admission_details():
    """2026年3月のサンプルデータ生成"""
    start_date = date(2026, 3, 1)
    end_date = date(2026, 3, 31)
    num_days = (end_date - start_date).days + 1

    # --- 病棟担当医と担当病棟のマッピング ---
    # 5F: 外科系 (C医師) + ペイン (H医師)
    # 6F: 内科系 (A, B, E医師) + G医師(救急)
    ward_doctors = {
        "5F": ["C", "H"],
        "6F": ["A", "B", "E", "G"],
    }

    # --- 入院数の目標: 約150件 ---
    # 日あたり約 4.8件 → 平日5件、土日3件程度
    records = []

    # ===== 入院イベント生成 =====
    admission_count = 0
    for day_offset in range(num_days):
        current_date = start_date + timedelta(days=day_offset)
        dow = current_date.weekday()  # 0=Mon ... 6=Sun
        is_weekend = dow >= 5

        # 日あたり入院数
        if is_weekend:
            n_admissions = random.choice([3, 3, 4, 4])
        else:
            n_admissions = random.choice([5, 5, 6, 6, 7])

        for _ in range(n_admissions):
            # 入院経路の決定
            r = random.random()
            if r < 0.40:
                route = "外来紹介"
            elif r < 0.65:
                route = "救急"
            elif r < 0.85:
                route = "連携室"
            else:
                route = "ウォークイン"

            # 入院創出医 (source_doctor)
            if route == "救急":
                # G医師が救急の中心（70%）
                source = "G" if random.random() < 0.70 else random.choice(["A", "B", "E"])
            elif route == "外来紹介":
                # D医師が外来紹介の40%を占める（入院創出多い）
                r2 = random.random()
                if r2 < 0.40:
                    source = "D"
                elif r2 < 0.55:
                    source = "A"
                elif r2 < 0.70:
                    source = "B"
                elif r2 < 0.80:
                    source = "E"
                elif r2 < 0.88:
                    source = "C"
                elif r2 < 0.93:
                    source = "H"
                elif r2 < 0.97:
                    source = "F"
                else:
                    # I医師はほとんど入院創出しない（3%程度）
                    source = "I"
            elif route == "連携室":
                # 連携室経由: 特定の医師に偏らない
                source = random.choice(["A", "B", "C", "E", "D"])
            else:  # ウォークイン
                source = random.choice(["A", "B", "E", "G"])

            # 担当医 (attending_doctor): 病棟担当医のみ
            # D, I は外来のみ → 担当医にならない
            # F, J は非常勤 → 少数のみ
            if route == "救急" and source == "G":
                # G医師が救急で入院した場合、G医師が担当することも多い
                if random.random() < 0.50:
                    attending = "G"
                    ward = "6F"
                else:
                    # 他の内科医に振る
                    attending = random.choice(["A", "B", "E"])
                    ward = "6F"
            else:
                # 病棟選択
                r3 = random.random()
                if source == "C":
                    ward = "5F"
                    attending = "C"
                elif source == "H":
                    ward = "5F"
                    attending = "H"
                elif r3 < 0.55:
                    ward = "6F"
                    attending = random.choices(
                        ["A", "B", "E"],
                        weights=[35, 30, 25],
                    )[0]
                else:
                    ward = "5F"
                    attending = random.choices(
                        ["C", "H"],
                        weights=[60, 40],
                    )[0]

            # 非常勤医師が担当になるケース（少数）
            if random.random() < 0.03:
                attending = "F"
                ward = random.choice(["5F", "6F"])

            records.append({
                "id": fixed_uuid(f"adm_{current_date}_{admission_count}"),
                "date": current_date.isoformat(),
                "ward": ward,
                "event_type": "admission",
                "route": route,
                "source_doctor": DOCTOR_BY_KEY[source]["name"],
                "attending_doctor": DOCTOR_BY_KEY[attending]["name"],
                "los_days": "",
                "phase": "",
            })
            admission_count += 1

    print(f"  入院数: {admission_count}")

    # ===== 退院イベント生成 =====
    # 約140件の退院。各担当医の特性を反映。
    discharge_count = 0

    # 担当医ごとの退院パターン定義
    # (doctor_key, count, los_distribution, friday_weight, saturday_weight)
    discharge_plans = [
        # A医師: 内科主治医、入院多い、金曜退院やや多め(30%)
        ("A", 30, {"min": 5, "max": 20, "mean": 11, "long_pct": 0.15},
         {"fri": 0.30, "sat": 0.03}),
        # B医師: 金曜退院に集中(50%+)、土曜退院もある
        ("B", 25, {"min": 5, "max": 18, "mean": 10, "long_pct": 0.10},
         {"fri": 0.52, "sat": 0.08}),
        # C医師: 外科、高回転、曜日バランス良好
        ("C", 28, {"min": 3, "max": 12, "mean": 7, "long_pct": 0.05},
         {"fri": 0.18, "sat": 0.02}),
        # E医師: 在院日数長め（C群多い60%）
        ("E", 18, {"min": 5, "max": 25, "mean": 9, "long_pct": 0.50},
         {"fri": 0.22, "sat": 0.03}),
        # G医師: 救急応援
        ("G", 15, {"min": 4, "max": 15, "mean": 9, "long_pct": 0.10},
         {"fri": 0.20, "sat": 0.05}),
        # H医師: ペイン、短期入院（A群）多い
        ("H", 20, {"min": 2, "max": 8, "mean": 4, "long_pct": 0.0},
         {"fri": 0.20, "sat": 0.02}),
        # F医師: 非常勤、少ない
        ("F", 3, {"min": 5, "max": 14, "mean": 9, "long_pct": 0.10},
         {"fri": 0.20, "sat": 0.0}),
        # J医師: 週1回、極少
        ("J", 1, {"min": 7, "max": 12, "mean": 9, "long_pct": 0.0},
         {"fri": 0.50, "sat": 0.0}),
    ]

    # 平日の日付リスト（月〜金）
    weekdays = []
    fridays = []
    saturdays = []
    all_days = []
    for day_offset in range(num_days):
        d = start_date + timedelta(days=day_offset)
        dow = d.weekday()
        all_days.append(d)
        if dow < 5:
            weekdays.append(d)
        if dow == 4:
            fridays.append(d)
        if dow == 5:
            saturdays.append(d)

    # 月〜木の日付
    mon_to_thu = [d for d in weekdays if d.weekday() < 4]

    for doc_key, count, los_dist, day_weights in discharge_plans:
        attending_name = DOCTOR_BY_KEY[doc_key]["name"]

        # 病棟
        if doc_key in ["C", "H"]:
            ward = "5F"
        else:
            ward = "6F"

        # 各退院の曜日を決める
        n_friday = int(count * day_weights["fri"])
        n_saturday = int(count * day_weights["sat"])
        n_other = count - n_friday - n_saturday

        # 金曜日の退院
        fri_dates = [random.choice(fridays) for _ in range(n_friday)]
        # 土曜日の退院
        sat_dates = [random.choice(saturdays) for _ in range(n_saturday)] if n_saturday > 0 else []

        # その他（月〜木中心、日曜はなし）
        if doc_key == "C":
            # C医師は火〜木中心（曜日バランス良好）
            tue_to_thu = [d for d in weekdays if d.weekday() in [1, 2, 3]]
            other_dates = [random.choice(tue_to_thu) for _ in range(n_other)]
        else:
            other_dates = [random.choice(mon_to_thu) for _ in range(n_other)]

        discharge_dates = fri_dates + sat_dates + other_dates

        for i, d_date in enumerate(discharge_dates):
            # 在院日数
            if random.random() < los_dist["long_pct"] and los_dist["max"] >= 15:
                los = random.randint(15, max(15, los_dist["max"]))
            else:
                los = max(los_dist["min"],
                          int(random.gauss(los_dist["mean"], 3)))
                los = min(los, los_dist["max"])
                los = max(los, 1)

            phase = los_to_phase(los)

            records.append({
                "id": fixed_uuid(f"dis_{doc_key}_{d_date}_{discharge_count}"),
                "date": d_date.isoformat(),
                "ward": ward,
                "event_type": "discharge",
                "route": "",
                "source_doctor": "",
                "attending_doctor": attending_name,
                "los_days": str(los),
                "phase": phase,
            })
            discharge_count += 1

    print(f"  退院数: {discharge_count}")

    # 日付順にソート
    records.sort(key=lambda x: x["date"])

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
# 検証
# ---------------------------------------------------------------------------
def verify(records):
    """生成データの品質チェック"""
    admissions = [r for r in records if r["event_type"] == "admission"]
    discharges = [r for r in records if r["event_type"] == "discharge"]

    print("\n=== 検証結果 ===")
    print(f"総入院数: {len(admissions)}")
    print(f"総退院数: {len(discharges)}")

    # B医師の金曜退院率
    b_discharges = [r for r in discharges if r["attending_doctor"] == "B医師"]
    b_friday = [r for r in b_discharges
                if date.fromisoformat(r["date"]).weekday() == 4]
    b_fri_pct = len(b_friday) / len(b_discharges) * 100 if b_discharges else 0
    print(f"B医師の金曜退院率: {b_fri_pct:.0f}% ({len(b_friday)}/{len(b_discharges)})")

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

    # I医師の入院創出数
    i_source = [r for r in admissions if r["source_doctor"] == "I医師"]
    print(f"I医師の入院創出数: {len(i_source)}")

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

    # 稼働率概算 (94床)
    # 退院患者のLOS合計は在院日数の一部のみ（3月以前入院分もある）
    total_patient_days = sum(int(r["los_days"]) for r in discharges if r["los_days"])
    avg_los = total_patient_days / len(discharges) if discharges else 0
    # 実際の稼働率は日次集計アプリで算出。ここでは平均在院日数のみ表示
    print(f"退院患者の平均在院日数: {avg_los:.1f}日")
    print(f"退院患者の延べ在院日数: {total_patient_days}日")

    # 病棟別入院数
    ward_5f = len([r for r in admissions if r["ward"] == "5F"])
    ward_6f = len([r for r in admissions if r["ward"] == "6F"])
    print(f"5F入院: {ward_5f}, 6F入院: {ward_6f}")

    # 週末退院の確認
    weekend_dis = [r for r in discharges
                   if date.fromisoformat(r["date"]).weekday() >= 5]
    print(f"週末退院数: {len(weekend_dis)}")


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
    verify(records)
    print("\n生成完了!")
