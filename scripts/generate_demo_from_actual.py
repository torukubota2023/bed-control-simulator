#!/usr/bin/env python3
"""実データ由来の教育用デモデータ生成スクリプト.

合成デモ (``generate_demo_data_2026fy.py``) と異なり、こちらは
`data/actual_admissions_2025fy.csv` の **実際の入院日・病棟・経路** を基盤に、
欠落している以下の情報を教育用に「補完合成」する:

  1. 退院日・LOS        : 病棟別標準 LOS の正規分布 + 短手3 階段関数
  2. 担当医師          : 病棟別医師プール（5F: C/H/J/F、6F: A/B/E/G）
  3. 短手3 分類        : ~13.5% の入院に大腸ポリペク 55% / 鼠径ヘルニア 20% / PSG 25%
  4. Day 6+ 超過       : 短手3 の ~5% が Day 6-8 まで延長（典型: 大腸ポリペク後下血）

副院長から伝達された校正情報 (2026-04-19):
  - 月間短手3: 約 22 名/月（全入院 ~163 件の 13.5%）
  - Day 6 超過: 約 1 名/月（短手3 の 4.5%）
  - 8 日以内でほぼ全員退院
  - 延長主因: 大腸ポリペクトミー後下血
  - 種別内訳: 大腸ポリペク 55% / 鼠径ヘルニア 20% / PSG 25%

入力:
  data/actual_admissions_2025fy.csv (1965 件の入院イベント)

出力 (output_dir 以下):
  sample_actual_data_ward.csv           日次サマリー（既存 2026fy と同スキーマ）
  admission_details.csv                 入院イベント
  discharge_details.csv                 退院イベント
  admission_details_combined.csv        入退院統合

Public API:
  generate_demo_from_actual(
      input_csv: Path | str = None,
      seed: int = 42,
  ) -> dict[str, pd.DataFrame]

CLI:
  python3 scripts/generate_demo_from_actual.py \
      --input data/actual_admissions_2025fy.csv \
      --output data/demo_from_actual_2025fy/
"""

from __future__ import annotations

import argparse
import random
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------
WARD_BEDS = {"5F": 47, "6F": 47}
DOW_NAMES_JP = ["月曜日", "火曜日", "水曜日", "木曜日", "金曜日", "土曜日", "日曜日"]

# 短手3 種類と発生比率（副院長指示: 大腸ポリペク 55% / 鼠径ヘルニア 20% / PSG 25%）
SHORT3_TYPES = ("大腸ポリペクトミー", "ヘルニア手術", "ポリソムノグラフィー")
SHORT3_WEIGHTS = {
    "大腸ポリペクトミー": 0.55,
    "ヘルニア手術": 0.20,
    "ポリソムノグラフィー": 0.25,
}
# 月間 22 件 / 月 163 件 ≈ 13.5%
SHORT3_OVERALL_RATIO = 0.135
# Day 6 超過率（短手3 内の比率、月 1 件 / 月 22 件 ≈ 4.5%）
SHORT3_OVERFLOW_RATE = 0.045

# 医師プール（既存 `generate_demo_data_2026fy.py` と整合）
DOCTORS_5F = ("C医師", "H医師", "J医師", "F医師")
DOCTORS_6F = ("A医師", "B医師", "E医師", "G医師")

# 5F 医師選択確率（C 外科中心 / H ペイン短期 / J 消化器外科 / F 非常勤）
DOCTORS_5F_WEIGHTS = {"C医師": 0.45, "H医師": 0.30, "J医師": 0.20, "F医師": 0.05}

# 6F 医師選択確率（A/B 二大柱 / E 長期型 / G 救急担当）
DOCTORS_6F_WEIGHTS = {"A医師": 0.33, "B医師": 0.30, "E医師": 0.25, "G医師": 0.12}

# 病棟別 LOS 正規分布パラメータ
# 5F: 外科・整形（13-14 日）、6F: 内科・ペイン（20-21 日）
LOS_DISTRIBUTIONS = {
    "5F": {"mean": 13.5, "stdev": 4.5, "floor": 2, "ceil": 32},
    "6F": {"mean": 20.5, "stdev": 6.0, "floor": 4, "ceil": 50},
}

# 医師別 LOS 調整（平均に対する倍率）
DOCTOR_LOS_MULTIPLIER = {
    "C医師": 1.15,   # 外科周術期、やや長め
    "H医師": 0.55,   # ペイン短期
    "J医師": 0.90,   # 消化器外科
    "F医師": 0.85,   # 非常勤
    "A医師": 1.05,
    "B医師": 1.00,
    "E医師": 1.25,   # 長期型
    "G医師": 0.90,   # 救急多め = 短め退院
}


# ---------------------------------------------------------------------------
# ルート正規化
# ---------------------------------------------------------------------------


def _normalize_route(raw: str, rng: random.Random) -> str:
    """実 CSV の `scheduled` / `emergency` を既存デモのルート語彙にマッピング.

    既存スキーマ: 外来紹介 / 救急 / 下り搬送 / 連携室 / ウォークイン
    """
    if not raw:
        return "外来紹介"
    raw_l = raw.strip().lower()
    if raw_l == "emergency":
        # 救急 75% / 下り搬送 15% / ウォークイン 10%
        r = rng.random()
        if r < 0.75:
            return "救急"
        if r < 0.90:
            return "下り搬送"
        return "ウォークイン"
    if raw_l == "scheduled":
        # 外来紹介 65% / 連携室 30% / ウォークイン 5%
        r = rng.random()
        if r < 0.65:
            return "外来紹介"
        if r < 0.95:
            return "連携室"
        return "ウォークイン"
    return raw  # 既に日本語ラベルならそのまま


# ---------------------------------------------------------------------------
# 医師選択
# ---------------------------------------------------------------------------


def _pick_doctor(ward: str, route: str, rng: random.Random) -> str:
    """病棟と経路に応じて担当医を確率的に選ぶ."""
    if ward == "5F":
        weights = DOCTORS_5F_WEIGHTS.copy()
        if route in ("救急", "下り搬送"):
            # 救急系は C 医師（外科）に寄せる
            weights = {"C医師": 0.60, "H医師": 0.10, "J医師": 0.25, "F医師": 0.05}
    else:  # 6F
        weights = DOCTORS_6F_WEIGHTS.copy()
        if route in ("救急", "下り搬送"):
            # 救急系は G 医師に寄せる
            weights = {"A医師": 0.15, "B医師": 0.15, "E医師": 0.10, "G医師": 0.60}
    names = list(weights.keys())
    probs = [weights[n] for n in names]
    return rng.choices(names, weights=probs, k=1)[0]


def _pick_source_doctor(ward: str, route: str, attending: str, rng: random.Random) -> str:
    """経路に応じた入院創出医（source_doctor）を決める."""
    if route == "外来紹介":
        # 外来は D/I 医師（外来専任）をよく使う
        if ward == "5F":
            return rng.choices(
                ["D医師", "C医師", "H医師", "I医師", "J医師"],
                weights=[30, 25, 15, 15, 15],
            )[0]
        return rng.choices(
            ["D医師", "A医師", "B医師", "E医師", "I医師"],
            weights=[30, 22, 20, 18, 10],
        )[0]
    if route == "連携室":
        return attending  # 連携室経由は受持医が創出
    # 救急/下り搬送/ウォークイン → 受持医が creator
    return attending


# ---------------------------------------------------------------------------
# LOS サンプリング
# ---------------------------------------------------------------------------


def _sample_los_normal(ward: str, doctor: str, rng: random.Random) -> int:
    """通常入院の LOS を正規分布からサンプリング.

    病棟ベース（mean, stdev）× 医師別倍率 → 整数化・下限上限クリップ.
    """
    params = LOS_DISTRIBUTIONS[ward]
    mult = DOCTOR_LOS_MULTIPLIER.get(doctor, 1.0)
    base = rng.gauss(params["mean"] * mult, params["stdev"])
    los = max(params["floor"], int(round(base)))
    return min(los, params["ceil"])


def _sample_los_short3(rng: random.Random) -> tuple[int, bool]:
    """短手3 の LOS をサンプリング.

    戻り値: (LOS 日数, overflow フラグ)
      - 通常: 1-5 日（Day 5 まで。中心値 4 日 = 入院→手術→1 泊→退院が典型）
      - overflow (~4.5%): 6-8 日（延長 = 下血等の合併症）
    """
    if rng.random() < SHORT3_OVERFLOW_RATE:
        # 延長ケース: 6-8 日（副院長: 8 日以内でほぼ退院）
        return rng.choices([6, 7, 8], weights=[0.5, 0.35, 0.15])[0], True
    # 通常ケース: 1-5 日（中心 4 日）
    return rng.choices([1, 2, 3, 4, 5], weights=[0.05, 0.15, 0.25, 0.35, 0.20])[0], False


def _pick_short3_type(overflow: bool, rng: random.Random) -> str:
    """短手3 種別を選ぶ.

    副院長指示: overflow（延長）の主因は大腸ポリペクトミー後下血。
    """
    if overflow:
        # 延長ケース: 大腸ポリペクの比率を上げる (85%)
        return rng.choices(
            SHORT3_TYPES,
            weights=[0.85, 0.05, 0.10],
            k=1,
        )[0]
    # 通常分布
    names = list(SHORT3_WEIGHTS.keys())
    probs = [SHORT3_WEIGHTS[n] for n in names]
    return rng.choices(names, weights=probs, k=1)[0]


# ---------------------------------------------------------------------------
# フェーズ分類
# ---------------------------------------------------------------------------


def _los_to_phase(los: int) -> str:
    if los <= 5:
        return "A"
    if los <= 14:
        return "B"
    return "C"


def _build_phantom_initial_inpatients(
    fy_start: date, rng: random.Random
) -> list[dict]:
    """年度開始日時点で既に在院している患者（教育用 phantom）を生成する.

    これは daily_df.total_patients を自然な値に保つための仮想データで、
    admission_details / discharge_details CSV には含まれない。
    5F: 35 床 / 6F: 43 床 程度を目標に、過去にランダムに入院した患者として配置。
    """
    phantoms: list[dict] = []
    for ward, target in (("5F", 35), ("6F", 43)):
        for _ in range(target):
            back_days = rng.randint(3, 28 if ward == "5F" else 40)
            admit_d = fy_start - timedelta(days=back_days)
            # phantom の LOS は既に back_days + 数日で退院する想定
            los = back_days + rng.randint(1, 6)
            phantoms.append({
                "admit_date": admit_d,
                "ward": ward,
                "doctor": None,       # daily 集計には不要
                "short3_type": "該当なし",
                "los": los,
                "discharge_date": admit_d + timedelta(days=los),
            })
    return phantoms


def _enforce_bed_capacity(
    trajectories: list[dict], rng: random.Random
) -> list[dict]:
    """病床制約（47 床/病棟）を満たすよう LOS を早期退院で圧縮する.

    アルゴリズム:
      1. 病棟別に入院日でソート
      2. 各入院日で在院数をチェック、47 超過なら最長在院者の LOS を
         今日 -1 日まで圧縮（早期退院）
      3. 短手3 患者は基準 LOS を保持（教育用指標を維持するため）
      4. 全患者の LOS >= 1 を保証
    """
    # 病棟別にソート（入院日昇順 → admit_date 同じならランダム安定化のため index 保持）
    for ward in ("5F", "6F"):
        beds = WARD_BEDS[ward]
        ward_pts = [p for p in trajectories if p["ward"] == ward]
        ward_pts.sort(key=lambda p: (p["admit_date"], rng.random()))

        # 日ごとに在院チェック
        # 在院中の患者を discharge_date 昇順で管理
        in_house: list[dict] = []

        for pt in ward_pts:
            d = pt["admit_date"]
            # 期限切れ患者を退院させる
            in_house = [q for q in in_house if q["discharge_date"] > d]
            # 病床超過チェック
            while len(in_house) >= beds:
                # 最長在院者（admit_date 最古かつ短手3 でない患者を優先）
                non_s3 = [q for q in in_house if q["short3_type"] == "該当なし"]
                candidates = non_s3 if non_s3 else in_house
                victim = max(candidates, key=lambda q: (d - q["admit_date"]).days)
                # 今日 -1 日まで圧縮（最低 LOS 1 日は保証）
                new_los = max(1, (d - victim["admit_date"]).days)
                victim["los"] = new_los
                victim["discharge_date"] = victim["admit_date"] + timedelta(days=new_los)
                # in_house から除外
                in_house = [q for q in in_house if q is not victim]
            # 新患を追加
            in_house.append(pt)
    return trajectories


# ---------------------------------------------------------------------------
# 実データ読込
# ---------------------------------------------------------------------------


def load_actual_admissions(input_csv: Path | str) -> pd.DataFrame:
    """実データ CSV を読み込み、5F/6F のみ抽出する.

    Parameters
    ----------
    input_csv : Path | str
        `data/actual_admissions_2025fy.csv` などのパス

    Returns
    -------
    pd.DataFrame
        カラム: event_type, event_date, ward, admission_date, patient_id,
                attending_doctor, admission_route, short3_type, age_years, notes
        5F / 6F のみ。4F は除外。
    """
    p = Path(input_csv)
    if not p.exists():
        raise FileNotFoundError(f"実データ CSV が見つかりません: {p}")
    df = pd.read_csv(p, encoding="utf-8-sig")
    # 5F / 6F のみ残す（4F は対象外）
    df = df[df["ward"].isin(["5F", "6F"])].copy()
    df["event_date"] = pd.to_datetime(df["event_date"])
    df = df.sort_values(["event_date", "ward"]).reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# メイン生成
# ---------------------------------------------------------------------------


def generate_demo_from_actual(
    input_csv: Optional[Path | str] = None,
    seed: int = 42,
) -> dict[str, pd.DataFrame]:
    """実データから教育用デモデータを生成する.

    Parameters
    ----------
    input_csv : Path | str | None
        入力 CSV。None の場合は ``data/actual_admissions_2025fy.csv`` を使用。
    seed : int
        決定論性のための乱数シード。

    Returns
    -------
    dict[str, pd.DataFrame]
        キー: ``daily_df`` / ``admission_details_df`` / ``discharge_details_df``
    """
    if input_csv is None:
        root = Path(__file__).resolve().parent.parent
        input_csv = root / "data" / "actual_admissions_2025fy.csv"

    actual = load_actual_admissions(input_csv)

    rng = random.Random(seed)
    uuid_ns = uuid.UUID("b2c3d4e5-f6a7-8901-bcde-f23456789012")

    # ----- 入院イベントを合成（既存 patient_id を再利用） -----
    admission_records: list[dict] = []
    # admit_date / ward / doctor / los / short3 を後続処理のために保持
    patient_trajectories: list[dict] = []

    for _, row in actual.iterrows():
        admit_d: datetime = row["admission_date"]
        if pd.isna(admit_d):
            admit_d = row["event_date"]
        if isinstance(admit_d, str):
            admit_d = pd.to_datetime(admit_d)
        admit_d = pd.Timestamp(admit_d).to_pydatetime().date()

        ward = row["ward"]
        raw_route = str(row.get("admission_route", "") or "")
        route = _normalize_route(raw_route, rng)
        doctor = _pick_doctor(ward, route, rng)
        source = _pick_source_doctor(ward, route, doctor, rng)

        # 短手3 判定
        is_short3 = rng.random() < SHORT3_OVERALL_RATIO
        short3_type = "該当なし"
        if is_short3:
            los, overflow = _sample_los_short3(rng)
            short3_type = _pick_short3_type(overflow, rng)
            # 短手3 は scheduled（外来紹介 or 連携室）に制限
            if route in ("救急", "下り搬送"):
                # 救急経由の短手3 はあり得ないため外来紹介に変更
                route = "外来紹介"
                source = _pick_source_doctor(ward, route, doctor, rng)
        else:
            los = _sample_los_normal(ward, doctor, rng)

        rec = {
            "id": str(uuid.uuid5(uuid_ns, f"adm_{row['patient_id']}")),
            "date": admit_d.isoformat(),
            "ward": ward,
            "event_type": "admission",
            "route": route,
            "source_doctor": source,
            "attending_doctor": doctor,
            "los_days": "",
            "phase": "",
            "short3_type": short3_type,
        }
        admission_records.append(rec)

        patient_trajectories.append({
            "admit_date": admit_d,
            "ward": ward,
            "doctor": doctor,
            "short3_type": short3_type,
            "los": los,
            "discharge_date": admit_d + timedelta(days=los),
        })

    # ----- 病床制約で LOS 圧縮 -----
    # 実データは各病棟 47 床で運用されているため、合成 LOS が長すぎて
    # overflow する場合は、最長在院者を早期退院させて整合を取る。
    patient_trajectories = _enforce_bed_capacity(patient_trajectories, rng)

    # ----- 退院イベント合成 -----
    discharge_records: list[dict] = []
    for i, pt in enumerate(patient_trajectories):
        dis_d = pt["discharge_date"]
        los = pt["los"]
        phase = _los_to_phase(los)
        rec = {
            "id": str(uuid.uuid5(uuid_ns, f"dis_{i}_{pt['ward']}_{dis_d}")),
            "date": dis_d.isoformat(),
            "ward": pt["ward"],
            "event_type": "discharge",
            "route": "",
            "source_doctor": "",
            "attending_doctor": pt["doctor"],
            "los_days": str(los),
            "phase": phase,
            "short3_type": "",  # 退院レコードに種別は持たせない（既存 2026fy と互換）
        }
        discharge_records.append(rec)

    # ----- 日次サマリー合成 -----
    # 日付レンジ = 入院日 min 〜 入院日 max（年度末でカット、tail は切る）
    admit_dates = [pt["admit_date"] for pt in patient_trajectories]
    start_d = min(admit_dates)
    end_d = max(admit_dates)

    # 初期在院患者（教育用仮想データ、admission_records には載せない）
    # 年度開始日時点で既に入院している患者を仮想配置する。
    # これにより Day 1 の total_patients が 0 にならず現実的になる。
    phantom_initial = _build_phantom_initial_inpatients(start_d, rng)

    # 各日の在院数・入退院数を集計
    daily_rows: list[dict] = []
    # dict 化で高速アクセス
    by_ward: dict[str, list[dict]] = {"5F": [], "6F": []}
    for pt in patient_trajectories:
        by_ward[pt["ward"]].append(pt)
    # phantom を在院判定用にのみ追加
    phantom_by_ward: dict[str, list[dict]] = {"5F": [], "6F": []}
    for pt in phantom_initial:
        phantom_by_ward[pt["ward"]].append(pt)

    cur = start_d
    while cur <= end_d:
        for ward in ("5F", "6F"):
            pts = by_ward[ward]
            # 当日在院（実データ由来）= 入院日 ≤ cur < 退院日
            in_house_real = [
                p for p in pts
                if p["admit_date"] <= cur < p["discharge_date"]
            ]
            # phantom 初期在院者も在院判定に加算（daily 表示用）
            in_house_phantom = [
                p for p in phantom_by_ward[ward]
                if p["admit_date"] <= cur < p["discharge_date"]
            ]
            in_house = in_house_real + in_house_phantom
            total = len(in_house)
            # 当日入院
            today_adm = [p for p in pts if p["admit_date"] == cur]
            actual_adm = len(today_adm)
            short3_today = sum(1 for p in today_adm if p["short3_type"] != "該当なし")
            # 当日退院
            today_dis = [p for p in pts if p["discharge_date"] == cur]
            actual_dis = len(today_dis)
            # 退院 LOS 分解
            los_list: list[int] = [p["los"] for p in today_dis]
            da = sum(1 for los in los_list if los <= 5)
            db = sum(1 for los in los_list if 6 <= los <= 14)
            dc = sum(1 for los in los_list if los >= 15)
            # 短手3 overflow（Day 6+ 退院の短手3 件数）
            overflow_los = [
                p["los"] for p in today_dis
                if p["short3_type"] != "該当なし" and p["los"] >= 6
            ]
            overflow_count = len(overflow_los)
            overflow_avg_los = (
                round(sum(overflow_los) / len(overflow_los), 1) if overflow_los else ""
            )
            avg_los = (sum(los_list) / len(los_list)) if los_list else 0.0

            # フェーズ内訳（在院 LOS 進捗ベース: cur - admit_date を使う）
            phase_a = phase_b = phase_c = 0
            for p in in_house:
                days_in = (cur - p["admit_date"]).days + 1  # +1 で入院初日を 1 日目扱い
                if days_in <= 5:
                    phase_a += 1
                elif days_in <= 14:
                    phase_b += 1
                else:
                    phase_c += 1
            beds = WARD_BEDS[ward]
            occ_pct = total / beds * 100
            empty = beds - total
            dow = cur.weekday()

            # notes 生成
            parts = [DOW_NAMES_JP[dow], f"稼働率{occ_pct:.1f}%", f"空床{empty}床"]
            notes = " / ".join(parts)

            daily_rows.append({
                "date": cur.isoformat(),
                "ward": ward,
                "total_patients": total,
                "new_admissions": actual_adm,
                "new_admissions_short3": short3_today,
                "short3_overflow_count": overflow_count,
                "short3_overflow_avg_los": overflow_avg_los,
                "discharges": actual_dis,
                "discharge_a": da,
                "discharge_b": db,
                "discharge_c": dc,
                "discharge_los_list": ",".join(str(x) for x in los_list),
                "phase_a_count": phase_a,
                "phase_b_count": phase_b,
                "phase_c_count": phase_c,
                "avg_los": round(avg_los, 1),
                "notes": notes,
            })
        cur += timedelta(days=1)

    daily_df = pd.DataFrame(daily_rows)
    admission_df = pd.DataFrame(admission_records)
    discharge_df = pd.DataFrame(discharge_records)
    return {
        "daily_df": daily_df,
        "admission_details_df": admission_df,
        "discharge_details_df": discharge_df,
    }


# ---------------------------------------------------------------------------
# 統計サマリ
# ---------------------------------------------------------------------------


def summarize(data: dict[str, pd.DataFrame]) -> dict:
    """生成データの概要を返す."""
    daily = data["daily_df"]
    adm = data["admission_details_df"]
    dis = data["discharge_details_df"]

    out: dict = {
        "days": daily["date"].nunique(),
        "daily_rows": len(daily),
        "admissions": len(adm),
        "discharges": len(dis),
    }
    # 短手3 全体
    s3 = adm[~adm["short3_type"].isin(["該当なし", ""])]
    out["short3_total"] = len(s3)
    out["short3_ratio_pct"] = round(len(s3) / max(1, len(adm)) * 100, 2)
    # Day 6+ 超過（LOS ≥ 6 の短手3 退院）
    dis_s3 = discharge_short3_rows(adm, dis)
    dis_s3_overflow = dis_s3[dis_s3["los_days"].astype(int) >= 6]
    out["short3_overflow_count"] = len(dis_s3_overflow)
    out["short3_overflow_ratio_pct"] = round(
        len(dis_s3_overflow) / max(1, len(dis_s3)) * 100, 2
    )

    for ward in ("5F", "6F"):
        w_daily = daily[daily["ward"] == ward]
        w_adm = adm[adm["ward"] == ward]
        w_dis = dis[dis["ward"] == ward]
        beds = WARD_BEDS[ward]
        out[f"{ward}_avg_occupancy_pct"] = round(
            w_daily["total_patients"].mean() / beds * 100, 1
        )
        out[f"{ward}_admissions"] = len(w_adm)
        out[f"{ward}_discharges"] = len(w_dis)
        if len(w_dis) > 0:
            los_vals = [int(x) for x in w_dis["los_days"].tolist() if str(x).isdigit()]
            if los_vals:
                out[f"{ward}_avg_los"] = round(sum(los_vals) / len(los_vals), 1)
        if len(w_adm) > 0:
            w_s3 = w_adm[~w_adm["short3_type"].isin(["該当なし", ""])]
            out[f"{ward}_short3_pct"] = round(len(w_s3) / len(w_adm) * 100, 2)

    # 月別入院数
    adm_with_month = adm.copy()
    adm_with_month["month"] = adm_with_month["date"].str[:7]
    monthly = adm_with_month.groupby("month").size().to_dict()
    out["monthly_admissions"] = {k: int(v) for k, v in sorted(monthly.items())}

    # 月別短手3 件数
    s3_with_month = s3.copy()
    s3_with_month["month"] = s3_with_month["date"].str[:7]
    monthly_s3 = s3_with_month.groupby("month").size().to_dict()
    out["monthly_short3"] = {k: int(v) for k, v in sorted(monthly_s3.items())}

    return out


def discharge_short3_rows(adm: pd.DataFrame, dis: pd.DataFrame) -> pd.DataFrame:
    """入院レコードから短手3 だった患者の退院を抽出する.

    admission.id と discharge は 1:1 対応しないため、id の uuid5 計算から
    間接的に紐付けるのではなく、入院 DataFrame の非該当なし件数と
    退院 DataFrame の数が同じ配置（同順序で合成済み）であることを利用する。
    """
    # admission 順と discharge 順は `patient_trajectories` で 1:1 で生成している
    # 短手3 判定は admission.short3_type で行う（discharge.short3_type は空のため）
    if len(adm) != len(dis):
        return dis.iloc[0:0]
    s3_mask = ~adm["short3_type"].isin(["該当なし", ""])
    return dis[s3_mask.values].copy()


# ---------------------------------------------------------------------------
# CSV 書き出し
# ---------------------------------------------------------------------------


def write_csvs(data: dict[str, pd.DataFrame], output_dir: Path) -> dict[str, Path]:
    """4 つの CSV を指定ディレクトリに書き出す.

    ファイル名は既存 `data/` 以下の命名規則に合わせて suffix を省略。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    daily_path = output_dir / "sample_actual_data_ward.csv"
    adm_path = output_dir / "admission_details.csv"
    dis_path = output_dir / "discharge_details.csv"
    combined_path = output_dir / "admission_details_combined.csv"

    data["daily_df"].to_csv(daily_path, index=False, encoding="utf-8-sig")
    data["admission_details_df"].to_csv(adm_path, index=False, encoding="utf-8-sig")
    data["discharge_details_df"].to_csv(dis_path, index=False, encoding="utf-8-sig")

    combined = pd.concat(
        [data["admission_details_df"], data["discharge_details_df"]],
        ignore_index=True,
    ).sort_values(["date", "event_type"]).reset_index(drop=True)
    combined.to_csv(combined_path, index=False, encoding="utf-8-sig")

    return {
        "daily": daily_path,
        "admission": adm_path,
        "discharge": dis_path,
        "combined": combined_path,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="実データ（actual_admissions_2025fy.csv）から教育用デモデータを生成"
    )
    root = Path(__file__).resolve().parent.parent
    parser.add_argument(
        "--input",
        type=str,
        default=str(root / "data" / "actual_admissions_2025fy.csv"),
        help="入力 CSV のパス",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(root / "data" / "demo_from_actual_2025fy"),
        help="出力ディレクトリ",
    )
    parser.add_argument("--seed", type=int, default=42, help="乱数シード")
    args = parser.parse_args(argv)

    print(f"[generate_demo_from_actual] input={args.input} seed={args.seed}")
    try:
        data = generate_demo_from_actual(input_csv=args.input, seed=args.seed)
    except FileNotFoundError as e:
        print(f"[error] {e}")
        return 1

    out_dir = Path(args.output)
    paths = write_csvs(data, out_dir)
    for k, p in paths.items():
        print(f"  {k:<11} -> {p}")

    summary = summarize(data)
    print("\n--- 概要 ---")
    print(f"  日数         : {summary['days']}")
    print(f"  入院合計     : {summary['admissions']}")
    print(f"  退院合計     : {summary['discharges']}")
    print(
        f"  短手3        : {summary['short3_total']} 件 "
        f"({summary['short3_ratio_pct']}%)"
    )
    print(
        f"  Day 6+ 超過 : {summary['short3_overflow_count']} 件 "
        f"(短手3 中 {summary['short3_overflow_ratio_pct']}%)"
    )
    for ward in ("5F", "6F"):
        print(
            f"  {ward}: 稼働率 {summary[f'{ward}_avg_occupancy_pct']}% / "
            f"入院 {summary[f'{ward}_admissions']} / 退院 {summary[f'{ward}_discharges']} / "
            f"LOS {summary.get(f'{ward}_avg_los', 'N/A')} / "
            f"短手3 {summary.get(f'{ward}_short3_pct', 'N/A')}%"
        )
    print("\n  月別短手3 件数:")
    for m, cnt in summary["monthly_short3"].items():
        print(f"    {m}: {cnt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
