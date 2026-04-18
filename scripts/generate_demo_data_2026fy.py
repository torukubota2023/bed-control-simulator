#!/usr/bin/env python3
"""ベッドコントロールシミュレーター用 2026年度通年デモデータ生成スクリプト.

2026-04-01 〜 2027-03-31 の 1 年分（365 日 × 2 病棟 = 730 レコード）を、
以下の季節性・運用パターンを織り込んで決定論的に生成する。

季節性:
  4 月 (新年度): GW 前準備期、比較的安定
  5 月 (GW)    : 5/2-5/6 連休、入院減・退院前倒し
  6 月 (梅雨)   : 高齢者呼吸器疾患増、6F で 3-5 % 増
  7-8 月 (猛暑 + お盆): 脱水・熱中症、8/8-8/16 連休対応
  9-10 月 (秋連休): 敬老の日 + 秋分の日 + スポーツの日の 3 連休週
  11 月 (呼吸器シーズン入り): 文化の日 + 勤労感謝の日連休
  12-1 月 (冬季): 12/26-1/3 年末年始、インフル・肺炎ピーク
  2-3 月 (年度末): 転院・退院準備集中

連休前後パターン:
  連休前 1-2 日: 退院 × 1.6-2.0、入院 × 0.9
  連休中       : 新規入院 × 0.3-0.5、退院 × 0.5
  連休明け 2-3 日: 入院 × 1.5-2.0、退院ほぼゼロ

病棟・医師別特性:
  5F (外科・整形, 47 床): C 医師 (外科, LOS 12-18d) / H 医師 (ペイン短期, LOS 5-8d) /
                          J 医師 (消化器外科, LOS 8-14d, 短手3 多い)
  6F (内科・ペイン, 47 床): A / B / E / G 医師 (呼吸器/循環器/消化器内科),
                            季節で疾患構成が変動

短手3:
  全入院の 14-16 %、大腸ポリペク 55 % / ヘルニア 20 % / PSG 25 %
  Day 5 到達率 5 % (6 日以上の overflow)

出力:
  output/demo_data_2026fy/sample_actual_data_ward_2026fy.csv
  output/demo_data_2026fy/admission_details_2026fy.csv
  output/demo_data_2026fy/discharge_details_2026fy.csv

Public API:
  generate_yearly_data(year: int = 2026, seed: int = 42) -> dict
    戻り値: {"daily_df", "admission_details_df", "discharge_details_df"}

CLI:
  python3 scripts/generate_demo_data_2026fy.py --year 2026 --output output/demo_data_2026fy/
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

try:
    import jpholiday
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "jpholiday が見つかりません。`pip install jpholiday` を実行してください。"
    ) from exc

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------
WARD_BEDS = {"5F": 47, "6F": 47}
DOW_NAMES_JP = ["月曜日", "火曜日", "水曜日", "木曜日", "金曜日", "土曜日", "日曜日"]

# 短手3 種類と発生比率（5F と 6F で比率が異なる）
SHORT3_TYPES = ("大腸ポリペクトミー", "ヘルニア手術", "ポリソムノグラフィー")
SHORT3_RATIO_5F = {
    "大腸ポリペクトミー": 0.35,
    "ヘルニア手術": 0.50,
    "ポリソムノグラフィー": 0.15,
}
SHORT3_RATIO_6F = {
    "大腸ポリペクトミー": 0.65,
    "ヘルニア手術": 0.05,
    "ポリソムノグラフィー": 0.30,
}
# 短手3 の全入院に対する割合
SHORT3_OVERALL_RATIO = 0.15
# Day 5 超過で通常入院に切替わる比率
SHORT3_OVERFLOW_RATE = 0.05

# 医師マスタ (scripts/generate_sample_data.py と互換)
DOCTORS_5F = ("C医師", "H医師", "J医師", "F医師")
DOCTORS_6F = ("A医師", "B医師", "E医師", "G医師")

# ---------------------------------------------------------------------------
# 季節性モデル
# ---------------------------------------------------------------------------


def _seasonal_admission_multiplier(d: date, ward: str) -> float:
    """月・病棟別の入院数倍率を返す（1.0 = 基準）。"""
    m = d.month
    if ward == "6F":
        # 6F (内科・呼吸器): 冬季ピーク、夏季底
        return {
            4: 0.90, 5: 0.85, 6: 1.00, 7: 0.90, 8: 0.85,
            9: 1.00, 10: 1.10, 11: 1.20,
            12: 1.40, 1: 1.45, 2: 1.35, 3: 1.15,
        }.get(m, 1.00)
    # 5F (外科・整形): 予定手術中心、季節変動は穏やか
    return {
        4: 0.95, 5: 0.85, 6: 1.00, 7: 1.05, 8: 0.90,
        9: 1.00, 10: 1.05, 11: 1.00,
        12: 0.95, 1: 1.00, 2: 1.10, 3: 1.15,
    }.get(m, 1.00)


def _seasonal_los_multiplier(d: date, ward: str) -> float:
    """月・病棟別の LOS 倍率を返す（1.0 = 基準）。"""
    m = d.month
    if ward == "6F":
        # 冬季は高齢者誤嚥性肺炎等で LOS 延長
        return {
            4: 1.00, 5: 0.95, 6: 1.05, 7: 1.00, 8: 0.95,
            9: 1.00, 10: 1.05, 11: 1.10,
            12: 1.15, 1: 1.20, 2: 1.15, 3: 1.05,
        }.get(m, 1.00)
    # 5F: 年度末転院準備で 3 月短縮
    return {
        4: 1.00, 5: 0.95, 6: 1.00, 7: 1.00, 8: 0.95,
        9: 1.00, 10: 1.00, 11: 1.05,
        12: 1.00, 1: 1.05, 2: 0.95, 3: 0.90,
    }.get(m, 1.00)


def _seasonal_disease_label(d: date, ward: str) -> str:
    """季節に応じた主要疾患ラベル（notes 用）。"""
    m = d.month
    if ward == "6F":
        if m in (12, 1, 2):
            return "肺炎・インフル期"
        if m == 6:
            return "梅雨・呼吸器増"
        if m in (7, 8):
            return "脱水・熱中症期"
        if m in (10, 11):
            return "呼吸器感染期入り"
        return ""
    # 5F
    if m in (2, 3):
        return "年度末転院集中"
    if m in (7, 8):
        return "外傷・整形増"
    return ""


# ---------------------------------------------------------------------------
# 祝日・連休判定
# ---------------------------------------------------------------------------


def _is_closed_day(d: date) -> bool:
    """土日または祝日判定。"""
    if d.weekday() >= 5:
        return True
    return bool(jpholiday.is_holiday(d))


def _is_institutional_closure(d: date) -> bool:
    """病院の事務体制上の『実質休診日』を判定する。

    土日祝に加え、お盆（8/13-8/16 の平日も含む）・年末年始（12/29-1/3 の平日も含む）を
    病院運営の慣習に合わせて『実質休診日』として扱う。
    """
    if _is_closed_day(d):
        return True
    # お盆（山の日 8/11 前後、平日でも週明けの 8/13, 8/14 は休診扱い）
    if d.month == 8 and 13 <= d.day <= 16:
        return True
    # 年末年始（12/29-1/3 の平日も休診扱い）
    if (d.month == 12 and d.day >= 29) or (d.month == 1 and d.day <= 3):
        return True
    return False


def _find_holiday_blocks(start: date, end: date, min_days: int = 3) -> list[tuple[date, date]]:
    """``start`` 〜 ``end`` 期間内の連続 ``min_days`` 日以上の連休ブロックを返す。

    土日祝に加えて、お盆・年末年始の慣習的休診日も含めて連続ブロックを構築する。
    """
    blocks: list[tuple[date, date]] = []
    cur = start
    while cur <= end:
        if _is_institutional_closure(cur):
            # 前後に伸ばす
            bs = cur
            while bs > start and _is_institutional_closure(bs - timedelta(days=1)):
                bs -= timedelta(days=1)
            be = cur
            while be < end and _is_institutional_closure(be + timedelta(days=1)):
                be += timedelta(days=1)
            days = (be - bs).days + 1
            if days >= min_days:
                if not blocks or blocks[-1] != (bs, be):
                    blocks.append((bs, be))
            cur = be + timedelta(days=1)
        else:
            cur += timedelta(days=1)
    return blocks


def _day_holiday_context(d: date, holiday_blocks: list[tuple[date, date]]) -> dict:
    """日付 ``d`` が連休前後でどの位置にあるかを判定する。

    戻り値キー:
      - ``in_holiday`` (bool): 連休中か
      - ``days_before`` (int or None): 連休開始までの日数（1 or 2 日前なら設定）
      - ``days_after`` (int or None): 連休明けからの日数（1 〜 3 日後なら設定）
      - ``holiday_name`` (str or None): 連休識別子
    """
    ctx: dict = {
        "in_holiday": False,
        "days_before": None,
        "days_after": None,
        "holiday_name": None,
    }
    for bs, be in holiday_blocks:
        if bs <= d <= be:
            ctx["in_holiday"] = True
            ctx["holiday_name"] = _holiday_identifier(bs, be)
            return ctx
        diff_before = (bs - d).days
        if 1 <= diff_before <= 2:
            ctx["days_before"] = diff_before
            ctx["holiday_name"] = _holiday_identifier(bs, be)
            return ctx
        diff_after = (d - be).days
        if 1 <= diff_after <= 3:
            ctx["days_after"] = diff_after
            ctx["holiday_name"] = _holiday_identifier(bs, be)
            return ctx
    return ctx


def _holiday_identifier(start: date, end: date) -> str:
    """連休ブロックの名称を返す（GW / お盆 / 年末年始 / 3連休 等）。"""
    gw_names = {"昭和の日", "憲法記念日", "みどりの日", "こどもの日"}
    cur = start
    while cur <= end:
        name = jpholiday.is_holiday_name(cur)
        if name and name in gw_names:
            return "GW"
        if cur.month == 8 and 11 <= cur.day <= 16:
            return "お盆"
        cur += timedelta(days=1)
    if (start.month == 12 and start.day >= 26) or (end.month == 1 and end.day <= 5):
        return "年末年始"
    # 最初に出会う祝日名
    cur = start
    while cur <= end:
        name = jpholiday.is_holiday_name(cur)
        if name:
            return name
        cur += timedelta(days=1)
    return f"{(end - start).days + 1}連休"


# ---------------------------------------------------------------------------
# 医師・入院パターン
# ---------------------------------------------------------------------------


def _pick_5f_attending(rng: random.Random) -> str:
    """5F の担当医を確率的に選ぶ。"""
    r = rng.random()
    if r < 0.45:
        return "C医師"  # 外科中心
    if r < 0.75:
        return "H医師"  # ペイン短期
    if r < 0.95:
        return "J医師"  # 消化器外科
    return "F医師"  # 非常勤（稀）


def _pick_6f_attending(rng: random.Random, d: date) -> str:
    """6F の担当医を確率的に選ぶ。金曜は B 医師の退院が多いが入院は通常分布。"""
    r = rng.random()
    if r < 0.33:
        return "A医師"
    if r < 0.63:
        return "B医師"
    if r < 0.88:
        return "E医師"
    return "G医師"


def _pick_los_5f(doctor: str, d: date, rng: random.Random) -> int:
    """5F の担当医別 LOS を返す（季節性を加味）。"""
    mult = _seasonal_los_multiplier(d, "5F")
    if doctor == "C医師":
        base = rng.gauss(16, 4.0)  # 外科周術期中心で若干長め
    elif doctor == "H医師":
        base = rng.gauss(8, 2.2)   # ペイン短期
    elif doctor == "J医師":
        base = rng.gauss(12, 3.0)  # 消化器外科
    else:
        base = rng.gauss(11, 2.8)
    los = max(2, int(round(base * mult)))
    return min(los, 32)


def _pick_los_6f(doctor: str, d: date, rng: random.Random) -> int:
    """6F の担当医別 LOS を返す。"""
    mult = _seasonal_los_multiplier(d, "6F")
    if doctor == "A医師":
        base = rng.gauss(22, 5.5)
    elif doctor == "B医師":
        base = rng.gauss(20, 5.0)
    elif doctor == "E医師":
        base = rng.gauss(26, 6.0)
    else:  # G医師
        base = rng.gauss(18, 4.5)
    los = max(4, int(round(base * mult)))
    return min(los, 50)


def _pick_route(ward: str, d: date, rng: random.Random) -> tuple[str, str]:
    """経路と入院創出医を返す（季節性あり）。"""
    m = d.month
    if ward == "5F":
        # 5F: 救急比率は年度末/夏季外傷期で上昇
        em_boost = 0.05 if m in (2, 3, 7, 8) else 0.0
        r = rng.random()
        if r < 0.30:
            route = "外来紹介"
        elif r < 0.50 + em_boost:
            route = "救急"
        elif r < 0.55 + em_boost:
            route = "下り搬送"
        elif r < 0.80 + em_boost:
            route = "連携室"
        else:
            route = "ウォークイン"
        if route in ("救急", "下り搬送"):
            source = rng.choice(["C医師", "G医師", "C医師"])
        elif route == "外来紹介":
            source = rng.choices(
                ["D医師", "C医師", "H医師", "I医師", "J医師"],
                weights=[30, 25, 15, 15, 15],
            )[0]
        elif route == "連携室":
            source = rng.choice(["C医師", "C医師", "D医師", "H医師"])
        else:
            source = rng.choice(["C医師", "H医師", "G医師"])
        return route, source

    # 6F
    # 呼吸器シーズンは救急比率上昇
    em_boost = 0.08 if m in (12, 1, 2) else (0.04 if m in (6, 11) else 0.0)
    r = rng.random()
    if r < 0.35:
        route = "外来紹介"
    elif r < 0.58 + em_boost:
        route = "救急"
    elif r < 0.62 + em_boost:
        route = "下り搬送"
    elif r < 0.82 + em_boost:
        route = "連携室"
    else:
        route = "ウォークイン"
    if route in ("救急", "下り搬送"):
        source = "G医師" if rng.random() < 0.65 else rng.choice(["A医師", "B医師", "E医師"])
    elif route == "外来紹介":
        source = rng.choices(
            ["D医師", "A医師", "B医師", "E医師", "I医師"],
            weights=[30, 22, 20, 18, 10],
        )[0]
    elif route == "連携室":
        source = rng.choice(["A医師", "B医師", "E医師", "D医師"])
    else:
        source = rng.choice(["A医師", "B医師", "E医師", "G医師"])
    return route, source


# ---------------------------------------------------------------------------
# 日次入退院数の決定
# ---------------------------------------------------------------------------


def _base_admissions_for_day(d: date, ward: str) -> tuple[float, float]:
    """曜日+季節を踏まえた (入院期待値, 退院期待値) を返す。"""
    dow = d.weekday()
    m_adm = _seasonal_admission_multiplier(d, ward)
    m_los = _seasonal_los_multiplier(d, ward)
    # LOS が長い月は退院も相対的に少ない
    dis_factor = m_adm / max(0.85, m_los)

    if ward == "5F":
        # 5F: 目標稼働率 85% 付近（40/47 床）
        # 平均 LOS 14-15 日 × 日次入院 3.0 で目標達成を狙う
        base_adm = {0: 3.6, 1: 3.2, 2: 3.2, 3: 3.0, 4: 2.8, 5: 1.4, 6: 1.0}[dow]
        base_dis = {0: 1.4, 1: 1.6, 2: 1.8, 3: 2.0, 4: 2.8, 5: 0.8, 6: 0.4}[dow]
    else:
        # 6F: 目標稼働率 92% 付近（43/47 床）
        base_adm = {0: 3.2, 1: 3.0, 2: 3.0, 3: 2.8, 4: 2.4, 5: 1.3, 6: 1.0}[dow]
        base_dis = {0: 1.7, 1: 2.1, 2: 2.3, 3: 2.5, 4: 3.6, 5: 0.7, 6: 0.4}[dow]
    return base_adm * m_adm, base_dis * dis_factor


def _adjust_for_holiday(
    adm: float, dis: float, ctx: dict
) -> tuple[float, float]:
    """連休前後の入退院倍率調整。"""
    if ctx["in_holiday"]:
        return adm * 0.35, dis * 0.5
    if ctx["days_before"] is not None:
        # 2 日前は 1.6、1 日前は 2.0 倍の退院
        mult = 2.0 if ctx["days_before"] == 1 else 1.6
        return adm * 0.9, dis * mult
    if ctx["days_after"] is not None:
        # 明け直後は入院集中
        mult = {1: 2.0, 2: 1.7, 3: 1.4}[ctx["days_after"]]
        return adm * mult, dis * 0.7
    return adm, dis


def _sample_count(expected: float, rng: random.Random) -> int:
    """期待値から Poisson 風の整数を生成。"""
    if expected <= 0:
        return 0
    # pandas のない所でも動く軽量ポアソン（Knuth）
    L = 2.71828182845904523536 ** (-expected)
    k = 0
    p = 1.0
    while p > L:
        k += 1
        p *= rng.random()
    return max(0, k - 1)


# ---------------------------------------------------------------------------
# メイン生成ロジック
# ---------------------------------------------------------------------------


def _los_to_phase(los: int) -> str:
    if los <= 5:
        return "A"
    if los <= 14:
        return "B"
    return "C"


def _phase_ratio(ward: str, d: date) -> dict[str, float]:
    """病棟・月別のフェーズ構成比。"""
    m = d.month
    if ward == "5F":
        # 3 月は A 群比率上げ（転院準備）
        if m in (2, 3):
            return {"a": 0.32, "b": 0.45, "c": 0.23}
        return {"a": 0.28, "b": 0.45, "c": 0.27}
    # 6F
    if m in (12, 1, 2):
        # 冬季は長期化、C 群比率上昇
        return {"a": 0.07, "b": 0.23, "c": 0.70}
    return {"a": 0.08, "b": 0.25, "c": 0.67}


def generate_yearly_data(
    year: int = 2026,
    seed: int = 42,
) -> dict[str, pd.DataFrame]:
    """指定年度（``year``-04-01 〜 翌年 03-31）の年間デモデータを生成する。

    Parameters
    ----------
    year : int, default 2026
        年度の開始年。2026 なら 2026-04-01 〜 2027-03-31。
    seed : int, default 42
        決定論性を保つための乱数シード。

    Returns
    -------
    dict[str, pandas.DataFrame]
        次の 3 つの DataFrame を含む辞書:

        - ``daily_df``: 病棟別日次サマリー (既存 ``sample_actual_data_ward_*.csv`` 互換)
        - ``admission_details_df``: 入院イベント
        - ``discharge_details_df``: 退院イベント
    """
    rng = random.Random(seed)
    uuid_ns = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

    start_date = date(year, 4, 1)
    end_date = date(year + 1, 3, 31)
    num_days = (end_date - start_date).days + 1

    # 連休ブロック（3 日以上）
    holiday_blocks = _find_holiday_blocks(start_date, end_date, min_days=3)

    # 初期在院患者数
    patients = {"5F": 40, "6F": 43}

    # 現在在院中の患者リスト (ward -> [ (admit_date, doctor, route, source, short3_type, los_target) ... ])
    in_house: dict[str, list[dict]] = {"5F": [], "6F": []}

    # 既往の初期患者（4/1 時点で既に在院している患者）を仮想的にセット
    for ward in ("5F", "6F"):
        for i in range(patients[ward]):
            # 過去にランダムに入院したと見做す
            back_days = rng.randint(3, 28 if ward == "5F" else 40)
            admit_d = start_date - timedelta(days=back_days)
            doctor = _pick_5f_attending(rng) if ward == "5F" else _pick_6f_attending(rng, admit_d)
            los_target = (
                _pick_los_5f(doctor, admit_d, rng) if ward == "5F"
                else _pick_los_6f(doctor, admit_d, rng)
            )
            # 既に長い分には合わせる
            los_target = max(los_target, back_days + rng.randint(0, 5))
            in_house[ward].append({
                "admit_date": admit_d,
                "doctor": doctor,
                "route": "外来紹介",
                "source": doctor,
                "short3_type": "該当なし",
                "los_target": los_target,
            })

    admission_records: list[dict] = []
    discharge_records: list[dict] = []
    daily_rows: list[dict] = []

    for day_offset in range(num_days):
        d = start_date + timedelta(days=day_offset)
        dow = d.weekday()
        ctx = _day_holiday_context(d, holiday_blocks)

        for ward in ("5F", "6F"):
            base_adm, base_dis = _base_admissions_for_day(d, ward)
            base_adm, base_dis = _adjust_for_holiday(base_adm, base_dis, ctx)

            beds = WARD_BEDS[ward]

            # 稼働率フィードバック: 稼働率が目標より下回れば退院を抑え、上回れば退院を促進
            target_occ = 0.87 if ward == "5F" else 0.93
            current_occ = len(in_house[ward]) / beds
            if current_occ < target_occ - 0.08:
                base_dis *= 0.55
                base_adm *= 1.25
            elif current_occ < target_occ - 0.04:
                base_dis *= 0.75
                base_adm *= 1.10
            elif current_occ > target_occ + 0.04:
                base_dis *= 1.15
                base_adm *= 0.90

            # --- 退院判定 ---
            # 1) LOS target に到達した患者を退院候補に
            today_discharges: list[dict] = []
            remaining: list[dict] = []
            for patient in in_house[ward]:
                days_in = (d - patient["admit_date"]).days
                wants_discharge = days_in >= patient["los_target"]
                # 金曜日の B 医師 / 連休前は早め退院
                if ward == "6F" and patient["doctor"] == "B医師" and dow == 4 and days_in >= patient["los_target"] - 2:
                    wants_discharge = True
                if ctx["days_before"] == 1 and days_in >= patient["los_target"] - 2:
                    wants_discharge = True
                # 週末は短手3以外は原則退院なし
                if dow >= 5 and patient["short3_type"] == "該当なし":
                    wants_discharge = wants_discharge and (rng.random() < 0.15)
                if wants_discharge:
                    today_discharges.append(patient)
                else:
                    remaining.append(patient)

            # 期待退院数との誤差を調整（多すぎれば延期、少なすぎれば追加）
            target_dis = _sample_count(base_dis, rng)
            # 1 日の退院上限（連休前 2 日前は最大 6、通常は 5）
            max_dis = 6 if ctx["days_before"] == 1 else (5 if ctx["days_before"] == 2 else 4)
            # 連休明けは退院ほぼゼロ
            if ctx["days_after"] is not None and ctx["days_after"] <= 2:
                max_dis = 2
            allowed = min(max_dis, max(target_dis, 1) + 2)
            if len(today_discharges) > allowed:
                # 超過分を明日以降に回す
                rng.shuffle(today_discharges)
                delayed = today_discharges[allowed:]
                today_discharges = today_discharges[:allowed]
                remaining.extend(delayed)
            elif len(today_discharges) < target_dis and len(remaining) > 0:
                # 近い LOS の患者を追加退院（target ちょうどまで補わずに 1 件ずつ試す）
                remaining.sort(key=lambda p: -((d - p["admit_date"]).days))
                needed = target_dis - len(today_discharges)
                added = 0
                i = 0
                while added < needed and i < len(remaining):
                    p = remaining[i]
                    # LOS target に近い（-2 日以内）で、在院 3 日以上の患者だけ
                    if (d - p["admit_date"]).days >= max(3, p["los_target"] - 2):
                        today_discharges.append(remaining.pop(i))
                        added += 1
                    else:
                        i += 1

            in_house[ward] = remaining

            # 退院レコード書き出し
            da = db = dc = 0
            los_list: list[int] = []
            short3_overflow_count = 0
            short3_overflow_los: list[int] = []
            for patient in today_discharges:
                actual_los = max(1, (d - patient["admit_date"]).days)
                phase = _los_to_phase(actual_los)
                if phase == "A":
                    da += 1
                elif phase == "B":
                    db += 1
                else:
                    dc += 1
                los_list.append(actual_los)
                # 短手3 patient が 6 日以上の滞在で退院した場合 → overflow
                if patient["short3_type"] != "該当なし" and actual_los >= 6:
                    short3_overflow_count += 1
                    short3_overflow_los.append(actual_los)
                rec = {
                    "id": str(uuid.uuid5(uuid_ns, f"dis_{ward}_{d}_{len(discharge_records)}")),
                    "date": d.isoformat(),
                    "ward": ward,
                    "event_type": "discharge",
                    "route": "",
                    "source_doctor": "",
                    "attending_doctor": patient["doctor"],
                    "los_days": str(actual_los),
                    "phase": phase,
                    "short3_type": "",
                }
                discharge_records.append(rec)

            # --- 入院判定 ---
            target_adm = _sample_count(base_adm, rng)
            available = beds - len(in_house[ward])
            actual_adm = max(0, min(target_adm, available))

            short3_today = 0
            for _ in range(actual_adm):
                doctor = _pick_5f_attending(rng) if ward == "5F" else _pick_6f_attending(rng, d)
                route, source = _pick_route(ward, d, rng)
                # 短手3 判定
                is_short3 = rng.random() < SHORT3_OVERALL_RATIO
                short3_type = "該当なし"
                if is_short3:
                    ratio_map = SHORT3_RATIO_5F if ward == "5F" else SHORT3_RATIO_6F
                    # 重み付き抽選
                    picks = list(ratio_map.keys())
                    weights = [ratio_map[p] for p in picks]
                    short3_type = rng.choices(picks, weights=weights, k=1)[0]
                    # 短手3 は外来紹介 or 連携室
                    route = rng.choice(["外来紹介", "外来紹介", "連携室"])
                    # LOS は 1-5 日、overflow で 6+ 日
                    if rng.random() < SHORT3_OVERFLOW_RATE:
                        los_target = rng.randint(6, 10)  # overflow
                    else:
                        los_target = rng.randint(1, 5)
                    short3_today += 1
                else:
                    los_target = (
                        _pick_los_5f(doctor, d, rng) if ward == "5F"
                        else _pick_los_6f(doctor, d, rng)
                    )

                in_house[ward].append({
                    "admit_date": d,
                    "doctor": doctor,
                    "route": route,
                    "source": source,
                    "short3_type": short3_type,
                    "los_target": los_target,
                })
                rec = {
                    "id": str(uuid.uuid5(uuid_ns, f"adm_{ward}_{d}_{len(admission_records)}")),
                    "date": d.isoformat(),
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

            patients[ward] = len(in_house[ward])

            # --- daily_df 行生成 ---
            total = patients[ward]
            pr = _phase_ratio(ward, d)
            pa = round(total * pr["a"])
            pb = round(total * pr["b"])
            pc = total - pa - pb
            avg_los = (sum(los_list) / len(los_list)) if los_list else 0.0
            occ = total / beds * 100
            empty = beds - total

            # notes 生成
            parts = [DOW_NAMES_JP[dow], f"稼働率{occ:.1f}%", f"空床{empty}床"]
            if ctx["in_holiday"]:
                parts.append(f"{ctx['holiday_name']}中")
            elif ctx["days_before"] is not None:
                parts.append(f"{ctx['holiday_name']}前({ctx['days_before']}日前)")
            elif ctx["days_after"] is not None:
                parts.append(f"{ctx['holiday_name']}明け{ctx['days_after']}日目")
            if dow == 4 and len(today_discharges) >= 3:
                parts.append("金曜退院集中")
            if dow == 0 and actual_adm >= 3:
                parts.append("月曜入院集中")
            disease = _seasonal_disease_label(d, ward)
            if disease:
                parts.append(disease)
            notes = " / ".join(parts)

            overflow_avg = (
                round(sum(short3_overflow_los) / len(short3_overflow_los), 1)
                if short3_overflow_los else ""
            )
            daily_rows.append({
                "date": d.isoformat(),
                "ward": ward,
                "total_patients": total,
                "new_admissions": actual_adm,
                "new_admissions_short3": short3_today,
                "short3_overflow_count": short3_overflow_count,
                "short3_overflow_avg_los": overflow_avg,
                "discharges": len(today_discharges),
                "discharge_a": da,
                "discharge_b": db,
                "discharge_c": dc,
                "discharge_los_list": ",".join(str(x) for x in los_list),
                "phase_a_count": pa,
                "phase_b_count": pb,
                "phase_c_count": pc,
                "avg_los": round(avg_los, 1),
                "notes": notes,
            })

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
    """生成データの基本統計を返す。"""
    daily = data["daily_df"]
    adm = data["admission_details_df"]
    dis = data["discharge_details_df"]

    out: dict = {
        "days": daily["date"].nunique(),
        "daily_rows": len(daily),
        "admissions": len(adm),
        "discharges": len(dis),
    }
    for ward in ("5F", "6F"):
        w = daily[daily["ward"] == ward]
        w_adm = adm[adm["ward"] == ward]
        w_dis = dis[dis["ward"] == ward]
        beds = WARD_BEDS[ward]
        out[f"{ward}_avg_occupancy_pct"] = round(w["total_patients"].mean() / beds * 100, 1)
        out[f"{ward}_admissions"] = len(w_adm)
        out[f"{ward}_discharges"] = len(w_dis)
        if len(w_dis) > 0:
            los_vals = [int(x) for x in w_dis["los_days"].tolist() if str(x).isdigit()]
            if los_vals:
                out[f"{ward}_avg_los"] = round(sum(los_vals) / len(los_vals), 1)
        if len(w_adm) > 0:
            s3 = w_adm[~w_adm["short3_type"].isin(["該当なし", ""])]
            out[f"{ward}_short3_pct"] = round(len(s3) / len(w_adm) * 100, 1)

    # 月別入院数
    adm_with_month = adm.copy()
    adm_with_month["month"] = adm_with_month["date"].str[:7]
    monthly = adm_with_month.groupby("month").size().to_dict()
    out["monthly_admissions"] = {k: int(v) for k, v in sorted(monthly.items())}
    return out


# ---------------------------------------------------------------------------
# CSV 出力
# ---------------------------------------------------------------------------


def write_csvs(data: dict[str, pd.DataFrame], output_dir: Path) -> dict[str, Path]:
    """3 つの DataFrame を CSV として出力する。"""
    output_dir.mkdir(parents=True, exist_ok=True)

    daily_path = output_dir / "sample_actual_data_ward_2026fy.csv"
    adm_path = output_dir / "admission_details_2026fy.csv"
    dis_path = output_dir / "discharge_details_2026fy.csv"

    data["daily_df"].to_csv(daily_path, index=False, encoding="utf-8-sig")
    data["admission_details_df"].to_csv(adm_path, index=False, encoding="utf-8-sig")
    data["discharge_details_df"].to_csv(dis_path, index=False, encoding="utf-8-sig")

    # 入退院統合版（既存 admission_details.csv 互換）
    combined = pd.concat(
        [data["admission_details_df"], data["discharge_details_df"]],
        ignore_index=True,
    ).sort_values(["date", "event_type"]).reset_index(drop=True)
    combined_path = output_dir / "admission_details_combined_2026fy.csv"
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
        description="2026 年度（4/1〜翌 3/31）ベッドコントロール用年間デモデータを生成"
    )
    parser.add_argument("--year", type=int, default=2026, help="年度開始年")
    parser.add_argument(
        "--output",
        type=str,
        default=str(Path(__file__).resolve().parent.parent / "output" / "demo_data_2026fy"),
        help="出力ディレクトリ",
    )
    parser.add_argument("--seed", type=int, default=42, help="乱数シード")
    args = parser.parse_args(argv)

    print(f"[generate_demo_data_2026fy] year={args.year} seed={args.seed}")
    data = generate_yearly_data(year=args.year, seed=args.seed)
    out_dir = Path(args.output)
    paths = write_csvs(data, out_dir)
    for k, p in paths.items():
        print(f"  {k:<11} -> {p}")

    summary = summarize(data)
    print("\n--- 概要 ---")
    print(f"  日数       : {summary['days']}")
    print(f"  入院合計   : {summary['admissions']}")
    print(f"  退院合計   : {summary['discharges']}")
    for ward in ("5F", "6F"):
        print(
            f"  {ward}: 稼働率 {summary[f'{ward}_avg_occupancy_pct']}% / "
            f"入院 {summary[f'{ward}_admissions']} / 退院 {summary[f'{ward}_discharges']} / "
            f"LOS {summary.get(f'{ward}_avg_los', 'N/A')} / "
            f"短手3 {summary.get(f'{ward}_short3_pct', 'N/A')}%"
        )
    print("\n  月別入院数:")
    for m, cnt in summary["monthly_admissions"].items():
        print(f"    {m}: {cnt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
