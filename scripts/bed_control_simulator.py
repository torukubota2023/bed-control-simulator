#!/usr/bin/env python3
"""
ベッドコントロールシミュレーター（CLI版）

地域包括医療病棟（94床）向けのベッド運用シミュレーター。
稼働率90〜95%を維持しつつ、患者フェーズ構成比を最適化し運営貢献額を最大化する。

患者フェーズ定義：
  - A群（1〜5日目）：入院初期、変動費高・運営貢献額小
  - B群（6〜14日目）：回復期、変動費中・運営貢献額大（最も運営貢献額を生む）
  - C群（15日目以降）：安定期、変動費小・運営貢献額中（退院調整の柔軟性が高い層）

使い方:
  python scripts/bed_control_simulator.py
"""

from __future__ import annotations

import math
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# 出力先ディレクトリ（スクリプトと同階層の ../output/）
# ---------------------------------------------------------------------------
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


# ============================= ユーティリティ =============================== #


def _ensure_output_dir() -> None:
    """出力フォルダが無ければ作成する。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _setup_matplotlib_font() -> None:
    """
    matplotlib の日本語フォントを設定する。
    Streamlit Cloud (Linux) では Noto Sans CJK JP、
    macOS では Hiragino Sans、Windows では Yu Gothic を試みる。
    いずれも使えなければ英語フォールバック。
    """
    import matplotlib
    import matplotlib.font_manager
    import matplotlib.pyplot as plt

    # フォントキャッシュをクリアして最新状態を取得
    matplotlib.font_manager._load_fontmanager(try_read_cache=False)

    # 候補フォント一覧（優先順）
    candidates = [
        "Noto Sans CJK JP",       # Linux / Streamlit Cloud
        "Hiragino Sans",           # macOS
        "Hiragino Kaku Gothic Pro",# macOS
        "Yu Gothic",               # Windows
        "IPAexGothic",             # Linux
    ]

    from matplotlib.font_manager import fontManager
    available = {f.name for f in fontManager.ttflist}

    for font in candidates:
        if font in available:
            matplotlib.rcParams["font.family"] = font
            matplotlib.rcParams["axes.unicode_minus"] = False
            print(f"  [フォント] {font} を使用")
            return

    # フォールバック：sans-serif のまま（日本語が豆腐になる可能性あり）
    matplotlib.rcParams["axes.unicode_minus"] = False
    print("  [フォント] 日本語フォントが見つかりません。英語ラベルにフォールバックします。")


def _sigmoid(x: float, midpoint: float, steepness: float = 0.3) -> float:
    """シグモイド関数。0〜1 の範囲で値を返す。"""
    z = -steepness * (x - midpoint)
    # オーバーフロー防止
    if z > 500:
        return 0.0
    if z < -500:
        return 1.0
    return 1.0 / (1.0 + math.exp(z))


def _get_phase(los: int) -> str:
    """在院日数からフェーズ（A/B/C）を返す。"""
    if los <= 5:
        return "A"
    elif los <= 14:
        return "B"
    else:
        return "C"


# ========================== パラメータ生成 ================================== #


def create_default_params() -> dict[str, Any]:
    """
    シミュレーション用デフォルトパラメータ辞書を返す。

    Returns:
        dict: 全パラメータのデフォルト値を格納した辞書。
              病棟基本設定・報酬・費用・加算・閾値・乱数シードを含む。
    """
    return {
        # --- 病棟基本設定 ---
        "num_beds": 94,                          # 総病床数
        "target_occupancy_lower": 0.90,           # 目標稼働率下限
        "target_occupancy_upper": 0.95,           # 目標稼働率上限
        "days_in_month": 30,                      # シミュレーション日数
        "monthly_admissions": 150,                # 月間入院件数（目安）
        "avg_length_of_stay": 19,                 # 平均在院日数
        "discharge_adjustment_days": 2,           # 退院調整に要するラグ日数
        "admission_variation_coeff": 1.0,         # 入院数の変動係数
        "initial_occupancy": 0.90,               # 初期稼働率

        # --- 報酬・費用（1日1患者あたり、円） ---
        # コストモデル: 運営貢献額ベース（変動費のみ差引き）
        # 変動費 = 薬剤費 + 材料費 + 検査費 + 給食費
        # 固定費（看護人件費・施設維持費等）は空床でも発生するため含めない
        "phase_a_revenue": 36000,                 # A群 収益（入院14日以内: 基本3,290点+初期加算150点+リハ栄養口腔連携110点+物価対応49点=3,599点≈36,000円）
        "phase_a_cost": 12000,                    # A群 変動費（検査・薬剤・画像集中、当院診療科加重平均）
        "phase_b_revenue": 36000,                 # B群 収益（入院14日以内: A群と同じ加算構造）
        "phase_b_cost": 6000,                     # B群 変動費（急性期処置終了、残存薬剤・検査のみ）
        "phase_c_revenue": 33400,                 # C群 収益（15日以降: 初期加算・リハ加算消失で-2,600円/日）
        "phase_c_cost": 4500,                     # C群 変動費（薬剤・給食等の最低限変動費のみ）

        # --- 加算（将来拡張用、初期値0） ---
        "first_day_bonus": 0,                     # 入院初日加算
        "within_14days_bonus": 0,                 # 14日以内退院加算
        "rehab_fee": 0,                           # リハビリ加算

        # --- 未活用病床コスト ---
        "opportunity_cost": 25000,                # 空床1日あたり未活用病床コスト（円）（運営貢献額ベース）

        # --- 閾値 ---
        "discharge_promotion_threshold": 0.95,    # 退院促進開始の稼働率閾値
        "admission_suppression_threshold": 0.97,  # 入院抑制の稼働率閾値

        # --- 乱数シード ---
        "random_seed": 42,
    }


# ========================= シミュレーション本体 ============================= #


def simulate_bed_control(params: dict[str, Any], strategy: str) -> pd.DataFrame:
    """
    日次ベッドコントロールシミュレーションを実行する。

    Args:
        params: create_default_params() で生成したパラメータ辞書。
        strategy: "rotation"（回転重視）, "stable"（安定維持）, "balanced"（バランス）。

    Returns:
        pd.DataFrame: 日次シミュレーション結果。

    Raises:
        ValueError: strategy が不正な場合。

    ロジック概要:
        1. 初期状態：在院患者を稼働率約85%でランダム配置
        2. 毎日: 在院日数+1 → 退院判定 → 新規入院 → 指標計算
        3. 退院確率はシグモイドベースで在院日数に応じて増加
        4. 戦略ごとに退院確率と新規入院の閾値を調整
    """
    valid_strategies = ("rotation", "stable", "balanced")
    if strategy not in valid_strategies:
        raise ValueError(
            f"strategy は {valid_strategies} のいずれかを指定してください。got: {strategy}"
        )

    rng = np.random.default_rng(params["random_seed"])

    num_beds: int = params["num_beds"]
    days: int = params["days_in_month"]
    avg_los: int = params["avg_length_of_stay"]
    adj_days: int = params["discharge_adjustment_days"]
    monthly_adm: int = params["monthly_admissions"]
    daily_adm_mean: float = monthly_adm / days  # 1日あたり平均入院数（≒5.0）

    # 報酬・費用テーブル
    rev = {
        "A": params["phase_a_revenue"],
        "B": params["phase_b_revenue"],
        "C": params["phase_c_revenue"],
    }
    cost = {
        "A": params["phase_a_cost"],
        "B": params["phase_b_cost"],
        "C": params["phase_c_cost"],
    }

    # --- 初期状態：稼働率約90%でフェーズバランスよく配置 ---
    # A群15%, B群45%, C群40% の比率で配置（退院集中防止のためC群は10-18日に分散）
    initial_occupancy = params.get("initial_occupancy", 0.90)
    initial_patients_count = int(num_beds * initial_occupancy)
    n_a = int(initial_patients_count * 0.15)
    n_b = int(initial_patients_count * 0.45)
    n_c = initial_patients_count - n_a - n_b
    patients_init: list[int] = []
    patients_init.extend(list(rng.integers(1, 6, size=n_a)))     # A群: 1-5日
    patients_init.extend(list(rng.integers(6, 15, size=n_b)))    # B群: 6-14日
    # C群: 退院集中を防ぐため、10-18日に分散配置（初期退院ラッシュを抑制）
    patients_init.extend(list(rng.integers(10, 19, size=n_c)))   # C群: 10-18日（幅広く分散）
    patients: list[int] = patients_init

    records: list[dict[str, Any]] = []

    # シミュレーション開始日（仮に2026年4月1日）
    start_date = datetime(2026, 4, 1)

    for day_idx in range(days):
        current_date = start_date + timedelta(days=day_idx)

        # ========== STEP 1: 在院日数+1 & フェーズ更新 ========== #
        patients = [los + 1 for los in patients]

        total_before = len(patients)
        occupancy_before = total_before / num_beds

        # ========== STEP 2: 退院判定 ========== #
        discharged_indices: list[int] = []

        # バランス戦略用：事前にフェーズ構成比を計算
        if strategy == "balanced":
            phases_pre = [_get_phase(p) for p in patients]
            total_p = max(len(patients), 1)
            ratio_b_pre = phases_pre.count("B") / total_p
            ratio_c_pre = phases_pre.count("C") / total_p

        for i, los in enumerate(patients):
            # --- 基本退院確率（在院日数ベース、平均18日中心） ---
            # A群（1-5日）: ほぼ退院なし
            # B群（6-14日）: 極めて低い退院確率
            # C群初期（15-20日）: 退院確率上昇
            # C群後期（21日以降）: 退院確率高い
            if los <= 5:
                base_prob = 0.005  # A群: ほぼゼロ
            elif los <= 10:
                base_prob = 0.02   # B群前半
            elif los <= 14:
                base_prob = 0.03 + 0.02 * (los - 10) / 4.0  # B群後半: 0.03→0.05
            elif los <= 17:
                base_prob = 0.08 + 0.04 * (los - 14) / 3.0  # C群初期: 0.08→0.12
            elif los <= 20:
                base_prob = 0.12 + 0.08 * (los - 17) / 3.0  # C群中期: 0.12→0.20
            elif los <= 25:
                base_prob = 0.20 + 0.10 * (los - 20) / 5.0  # C群後期: 0.20→0.30
            else:
                base_prob = 0.35   # 長期: 0.35

            # 退院調整ラグ：入院直後（在院日数 <= adj_days）は退院不可
            if los <= adj_days:
                base_prob = 0.0

            phase = _get_phase(los)
            prob = base_prob

            # --- 稼働率フロア保護（全戦略共通、80%以下への低下を防止）---
            # 現実の病院運営では稼働率80%未満は経営的に許容されず退院抑制が働く
            if occupancy_before < 0.82:
                prob *= 0.05  # 稼働率82%未満: ほぼ退院停止
            elif occupancy_before < 0.85:
                prob *= 0.15  # 稼働率82-85%: 退院大幅抑制

            # --- 戦略別の退院確率調整 ---
            if strategy == "rotation":
                # 回転重視：C群の退院を積極化、稼働率85%以上は維持
                if occupancy_before < 0.85:
                    prob *= 0.3
                elif occupancy_before < 0.87:
                    prob *= 0.5
                else:
                    # 稼働率87%以上では積極的に回転
                    if phase == "C":
                        prob *= 2.2
                    elif phase == "B" and los >= 12:
                        prob *= 1.6
                    elif phase == "B" and los >= 10:
                        prob *= 1.2

            elif strategy == "stable":
                # 安定維持：C群の退院を抑制して稼働率を維持
                if occupancy_before > 0.96:
                    # 96%超は退院促進（過密防止）
                    if phase == "C":
                        prob *= 1.5
                else:
                    if phase == "C":
                        prob *= 0.6
                    # 稼働率が低い時は全体的に退院をさらに抑制
                    if occupancy_before < 0.90:
                        prob *= 0.4
                    if occupancy_before < 0.85:
                        prob *= 0.4

            elif strategy == "balanced":
                # バランス：稼働率ゾーン別に段階的制御
                if occupancy_before < 0.82:
                    # 稼働率82%未満: 退院をほぼ停止
                    prob *= 0.15
                elif occupancy_before < 0.85:
                    # 稼働率82-85%: 退院を強く抑制
                    prob *= 0.3
                elif occupancy_before < 0.88:
                    # 稼働率85-88%: 退院を中程度に抑制
                    prob *= 0.5
                elif occupancy_before < 0.90:
                    # 稼働率88-90%: 退院を軽く抑制
                    prob *= 0.7
                elif occupancy_before <= 0.95:
                    # 稼働率90-95%: 通常運用（微調整のみ）
                    if ratio_b_pre < 0.25 and phase == "B":
                        prob *= 0.7
                    if ratio_c_pre > 0.35 and phase == "C":
                        prob *= 1.3
                else:
                    # 稼働率95%超: C群から退院促進
                    if phase == "C":
                        prob *= 1.8
                    elif phase == "B":
                        prob *= 1.2

            # 稼働率が高すぎる場合の退院促進（全戦略共通）
            if occupancy_before >= params["discharge_promotion_threshold"]:
                prob *= 1.3

            # 確率を 0〜0.8 にクリップ
            prob = max(0.0, min(prob, 0.8))

            if rng.random() < prob:
                discharged_indices.append(i)

        # --- 稼働率80%ハードフロア: 退院数を制限 ---
        # 現実の病院では稼働率80%未満に下がることは稀（退院調整・入院促進が働く）
        min_patients = math.ceil(num_beds * 0.80)
        max_allowed_discharges = max(0, total_before - min_patients)
        if len(discharged_indices) > max_allowed_discharges:
            # 在院日数が長い患者（C群後期）から優先的に退院させ、残りは抑制
            discharged_indices.sort(key=lambda idx: patients[idx], reverse=True)
            discharged_indices = discharged_indices[:max_allowed_discharges]

        # 退院処理（逆順で除去して index ずれを防止）
        for i in sorted(discharged_indices, reverse=True):
            patients.pop(i)

        num_discharges = len(discharged_indices)

        # ========== STEP 3: 新規入院 ========== #
        empty_beds = num_beds - len(patients)
        occupancy_after_discharge = len(patients) / num_beds

        # 入院需要をポアソン分布で生成
        # 空床が多い時は待機患者がいるため需要が増える
        demand_lambda = daily_adm_mean * params["admission_variation_coeff"]
        if empty_beds > 10:
            # 空床が多い時は待機患者から追加入院
            demand_lambda *= 1.3
        demand = int(rng.poisson(demand_lambda))

        # 戦略別の新規入院制御
        max_admissions = empty_beds  # デフォルト：空床数が上限

        if strategy == "rotation":
            # 回転重視：稼働率85%以上を維持しつつ、空床があれば即受入
            # 稼働率97%まで積極受入
            allowed = max(
                0,
                int(num_beds * params["admission_suppression_threshold"])
                - len(patients),
            )
            max_admissions = allowed

        elif strategy == "stable":
            # 安定維持：稼働率93%で抑制開始
            if occupancy_after_discharge >= 0.93:
                max_admissions = max(
                    0, int(num_beds * 0.95) - len(patients)
                )
            else:
                max_admissions = empty_beds

        elif strategy == "balanced":
            # バランス：稼働率ゾーン別に入院制御
            phases_current = [_get_phase(p) for p in patients]
            total_current = max(len(patients), 1)
            ratio_a = phases_current.count("A") / total_current

            if occupancy_after_discharge < 0.90:
                # 稼働率90%未満: 積極的に入院受入（空床全て使う）
                max_admissions = empty_beds
            elif occupancy_after_discharge <= 0.95:
                # 稼働率90-95%: 通常運用
                # A群過多の場合のみ入院抑制
                if ratio_a > 0.35:
                    max_admissions = max(0, empty_beds // 2)
                else:
                    target_upper = int(num_beds * params["target_occupancy_upper"])
                    max_admissions = max(0, target_upper - len(patients))
            else:
                # 稼働率95%超: 新規入院を抑制
                max_admissions = max(0, int(num_beds * 0.95) - len(patients))

        new_admissions = min(demand, max_admissions)
        excess_demand = max(0, demand - new_admissions)

        # 入院処理（新規患者は在院日数1で追加）
        patients.extend([1] * new_admissions)

        # ========== STEP 4: 指標計算 ========== #
        total_patients = len(patients)
        occupancy_rate = total_patients / num_beds
        empty_beds_final = num_beds - total_patients

        # フェーズ別集計
        phases_all = [_get_phase(p) for p in patients]
        phase_a = phases_all.count("A")
        phase_b = phases_all.count("B")
        phase_c = phases_all.count("C")

        phase_a_ratio = phase_a / max(total_patients, 1)
        phase_b_ratio = phase_b / max(total_patients, 1)
        phase_c_ratio = phase_c / max(total_patients, 1)

        # --- 日次診療報酬 ---
        daily_revenue = (
            phase_a * rev["A"]
            + phase_b * rev["B"]
            + phase_c * rev["C"]
        )
        # 入院初日加算（新規入院者に適用）
        daily_revenue += new_admissions * params["first_day_bonus"]
        # 14日以内退院加算（退院者のうちB群比率で概算）
        # 仮定：退院者のフェーズ情報が無いため、全体のB群比率で按分
        daily_revenue += int(num_discharges * phase_b_ratio) * params["within_14days_bonus"]
        # リハビリ加算（B群・C群に適用と仮定）
        daily_revenue += (phase_b + phase_c) * params["rehab_fee"]

        # --- 日次コスト ---
        daily_cost = (
            phase_a * cost["A"]
            + phase_b * cost["B"]
            + phase_c * cost["C"]
        )

        daily_profit = daily_revenue - daily_cost

        # 未活用病床コスト（空床分）
        opportunity_loss = empty_beds_final * params["opportunity_cost"]

        # --- フラグ判定 ---
        flag_low_occ = occupancy_rate < params["target_occupancy_lower"]
        flag_high_occ = occupancy_rate > params["target_occupancy_upper"]
        flag_excess_a = phase_a_ratio > 0.35
        flag_shortage_b = phase_b_ratio < 0.25
        flag_stagnant_c = phase_c_ratio > 0.30

        # 推奨退院数（稼働率が上限超のとき、何人退院すれば目標内に戻るか）
        recommended_discharges = 0
        if occupancy_rate > params["target_occupancy_upper"]:
            recommended_discharges = total_patients - int(
                num_beds * params["target_occupancy_upper"]
            )

        # 許容保留数（稼働率が下限未満のとき、退院を遅らせてよい人数）
        allowable_holds = 0
        if occupancy_rate < params["target_occupancy_lower"]:
            allowable_holds = int(
                num_beds * params["target_occupancy_lower"]
            ) - total_patients

        records.append({
            "date": current_date.strftime("%Y-%m-%d"),
            "day": day_idx + 1,
            "total_patients": total_patients,
            "occupancy_rate": round(occupancy_rate, 4),
            "new_admissions": new_admissions,
            "discharges": num_discharges,
            "phase_a_count": phase_a,
            "phase_b_count": phase_b,
            "phase_c_count": phase_c,
            "phase_a_ratio": round(phase_a_ratio, 4),
            "phase_b_ratio": round(phase_b_ratio, 4),
            "phase_c_ratio": round(phase_c_ratio, 4),
            "daily_revenue": daily_revenue,
            "daily_cost": daily_cost,
            "daily_profit": daily_profit,
            "empty_beds": empty_beds_final,
            "excess_demand": excess_demand,
            "opportunity_loss": opportunity_loss,
            "flag_low_occupancy": flag_low_occ,
            "flag_high_occupancy": flag_high_occ,
            "flag_excess_a": flag_excess_a,
            "flag_shortage_b": flag_shortage_b,
            "flag_stagnant_c": flag_stagnant_c,
            "recommended_discharges": recommended_discharges,
            "allowable_holds": allowable_holds,
        })

    df = pd.DataFrame(records)
    return df


# ============================ サマリー生成 ================================= #


def summarize_results(df: pd.DataFrame) -> dict[str, Any]:
    """
    日次シミュレーション結果の月次サマリーを辞書で返す。

    Args:
        df: simulate_bed_control() の戻り値。

    Returns:
        dict: 以下のキーを持つ月次KPI辞書。
            avg_occupancy, total_revenue, total_cost, total_profit,
            avg_phase_a_ratio, avg_phase_b_ratio, avg_phase_c_ratio,
            avg_length_of_stay, total_empty_bed_days, total_excess_days,
            total_opportunity_loss, total_recommended_discharges,
            days_in_target_range, max_occupancy, min_occupancy
    """
    # 平均在院日数（厚生労働省 病院報告の定義に準拠）
    # 平均在院日数 = 在院患者延日数 ÷ ((新入院患者数 + 退院患者数) ÷ 2)
    total_patient_days = df["total_patients"].sum()       # 在院患者延日数
    total_new_admissions = df["new_admissions"].sum()     # 新入院患者数
    total_discharges = df["discharges"].sum()             # 退院患者数
    denominator = (total_new_admissions + total_discharges) / 2
    estimated_avg_los = total_patient_days / max(denominator, 1)

    params = create_default_params()  # 目標レンジ取得用

    return {
        "avg_occupancy": round(df["occupancy_rate"].mean(), 4),
        "total_revenue": int(df["daily_revenue"].sum()),
        "total_cost": int(df["daily_cost"].sum()),
        "total_profit": int(df["daily_profit"].sum()),
        "avg_phase_a_ratio": round(df["phase_a_ratio"].mean(), 4),
        "avg_phase_b_ratio": round(df["phase_b_ratio"].mean(), 4),
        "avg_phase_c_ratio": round(df["phase_c_ratio"].mean(), 4),
        "avg_length_of_stay": round(estimated_avg_los, 1),
        "total_empty_bed_days": int(df["empty_beds"].sum()),
        "total_excess_days": int(df["excess_demand"].sum()),
        "total_opportunity_loss": int(df["opportunity_loss"].sum()),
        "total_recommended_discharges": int(df["recommended_discharges"].sum()),
        "days_in_target_range": int(
            (
                (df["occupancy_rate"] >= params["target_occupancy_lower"])
                & (df["occupancy_rate"] <= params["target_occupancy_upper"])
            ).sum()
        ),
        "max_occupancy": round(df["occupancy_rate"].max(), 4),
        "min_occupancy": round(df["occupancy_rate"].min(), 4),
    }


# ============================ 戦略比較 ===================================== #


def compare_strategies(
    params: dict[str, Any],
    strategies: list[str] | None = None,
) -> pd.DataFrame:
    """
    複数戦略を一括実行し、サマリーを横並びで比較する。

    Args:
        params: パラメータ辞書。
        strategies: 比較する戦略名のリスト。デフォルトは3戦略すべて。

    Returns:
        pd.DataFrame: 戦略名をカラムに持つ比較表（行＝指標）。
        月次運営貢献額が最大の戦略をコンソールに表示する。
    """
    if strategies is None:
        strategies = ["rotation", "stable", "balanced"]

    summaries: dict[str, dict[str, Any]] = {}

    for strat in strategies:
        print(f"  戦略 [{strat}] シミュレーション実行中...")
        df = simulate_bed_control(params, strat)
        summaries[strat] = summarize_results(df)

    comparison = pd.DataFrame(summaries)

    # 月次運営貢献額が最大の戦略を特定して表示
    profits = {s: summaries[s]["total_profit"] for s in strategies}
    best = max(profits, key=profits.get)  # type: ignore[arg-type]
    print(f"\n  >>> 月次運営貢献額最大戦略: {best}（運営貢献額 {profits[best]:,.0f} 円）")

    return comparison


# ============================== 可視化 ===================================== #


def plot_simulation(df: pd.DataFrame, strategy_name: str) -> None:
    """
    日次シミュレーション結果を 2x2 サブプロットで可視化し PNG 保存する。

    サブプロット構成:
        (1) 稼働率推移（目標レンジ90-95%を帯で表示）
        (2) A/B/C構成比の積み上げ面グラフ
        (3) 日次運営貢献額推移（棒グラフ）
        (4) 新規入院・退院数の並列棒グラフ

    Args:
        df: simulate_bed_control() の戻り値。
        strategy_name: 戦略名（ファイル名・タイトルに使用）。
    """
    import matplotlib.pyplot as plt

    _setup_matplotlib_font()
    _ensure_output_dir()

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(
        f"ベッドコントロールシミュレーション — 戦略: {strategy_name}",
        fontsize=14,
    )

    days = df["day"]

    # --- (1) 稼働率推移 ---
    ax1 = axes[0, 0]
    ax1.plot(
        days,
        df["occupancy_rate"] * 100,
        marker="o",
        markersize=3,
        linewidth=1.5,
        color="steelblue",
    )
    ax1.axhspan(90, 95, alpha=0.2, color="green", label="目標レンジ (90-95%)")
    ax1.set_xlabel("日")
    ax1.set_ylabel("稼働率 (%)")
    ax1.set_title("稼働率推移")
    ax1.legend(loc="lower right", fontsize=8)
    ax1.set_ylim(70, 105)
    ax1.grid(True, alpha=0.3)

    # --- (2) A/B/C 構成比の積み上げ面グラフ ---
    ax2 = axes[0, 1]
    ax2.stackplot(
        days,
        df["phase_a_ratio"] * 100,
        df["phase_b_ratio"] * 100,
        df["phase_c_ratio"] * 100,
        labels=["A群 (1-5日)", "B群 (6-14日)", "C群 (15日〜)"],
        colors=["#e74c3c", "#2ecc71", "#3498db"],
        alpha=0.7,
    )
    ax2.set_xlabel("日")
    ax2.set_ylabel("構成比 (%)")
    ax2.set_title("患者フェーズ構成比")
    ax2.legend(loc="upper right", fontsize=8)
    ax2.set_ylim(0, 100)
    ax2.grid(True, alpha=0.3)

    # --- (3) 日次運営貢献額推移 ---
    ax3 = axes[1, 0]
    colors_profit = ["green" if v >= 0 else "red" for v in df["daily_profit"]]
    ax3.bar(
        days, df["daily_profit"] / 10000,
        color=colors_profit, alpha=0.7, width=0.8,
    )
    ax3.set_xlabel("日")
    ax3.set_ylabel("日次運営貢献額 (万円)")
    ax3.set_title("日次運営貢献額推移")
    ax3.axhline(y=0, color="black", linewidth=0.5)
    ax3.grid(True, alpha=0.3)

    # --- (4) 新規入院・退院数の棒グラフ ---
    ax4 = axes[1, 1]
    width = 0.35
    ax4.bar(
        days - width / 2,
        df["new_admissions"],
        width,
        label="新規入院",
        color="#2ecc71",
        alpha=0.7,
    )
    ax4.bar(
        days + width / 2,
        df["discharges"],
        width,
        label="退院",
        color="#e74c3c",
        alpha=0.7,
    )
    ax4.set_xlabel("日")
    ax4.set_ylabel("人数")
    ax4.set_title("新規入院・退院数")
    ax4.legend(fontsize=8)
    ax4.grid(True, alpha=0.3)

    plt.tight_layout()

    filepath = OUTPUT_DIR / f"bed_sim_{strategy_name}.png"
    fig.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  グラフ保存: {filepath}")


def plot_strategy_comparison(comparison_df: pd.DataFrame) -> None:
    """
    戦略比較用の棒グラフを作成し PNG 保存する。

    主要6指標（運営貢献額、稼働率、目標レンジ日数、未活用病床コスト、B群構成比、空床日数）を
    戦略間で横並び比較する。

    Args:
        comparison_df: compare_strategies() の戻り値。
    """
    import matplotlib.pyplot as plt

    _setup_matplotlib_font()
    _ensure_output_dir()

    strategies = comparison_df.columns.tolist()

    # 比較する指標（表示名、キー、スケーリング分母、単位）
    metrics = [
        ("月次運営貢献額", "total_profit", 1e4, "万円"),
        ("平均稼働率", "avg_occupancy", 0.01, "%"),  # 0.xx → xx%
        ("目標レンジ日数", "days_in_target_range", 1, "日"),
        ("未活用病床コスト合計", "total_opportunity_loss", 1e4, "万円"),
        ("B群平均構成比", "avg_phase_b_ratio", 0.01, "%"),
        ("空床日数合計", "total_empty_bed_days", 1, "床日"),
    ]

    # 戦略ごとの色
    color_map = {
        "rotation": "#e74c3c",
        "stable": "#3498db",
        "balanced": "#2ecc71",
    }
    bar_colors = [color_map.get(s, "gray") for s in strategies]

    fig, axes = plt.subplots(2, 3, figsize=(16, 8))
    fig.suptitle("戦略比較", fontsize=14)

    for idx, (title, key, scale, unit) in enumerate(metrics):
        ax = axes[idx // 3, idx % 3]
        values = [comparison_df.loc[key, s] / scale for s in strategies]
        bars = ax.bar(strategies, values, color=bar_colors, alpha=0.8)
        ax.set_title(f"{title} ({unit})")
        ax.grid(True, alpha=0.3, axis="y")

        # 値ラベルを棒の上に表示
        for bar, val in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                f"{val:.1f}",
                ha="center",
                va="bottom",
                fontsize=9,
            )

    plt.tight_layout()

    filepath = OUTPUT_DIR / "bed_sim_strategy_comparison.png"
    fig.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  戦略比較グラフ保存: {filepath}")


# ========================= 意思決定支援ロジック ============================== #


def assess_ward_status(
    df: pd.DataFrame, day_index: int, params: dict[str, Any]
) -> dict[str, Any]:
    """
    当日の病棟状態を4段階スコアリングする。

    スコアリング（100点満点）:
      - 稼働率ゾーン（40点）
      - フェーズ構成バランス（30点）
      - 運営貢献効率（20点）
      - トレンド安定性（10点）

    Args:
        df: simulate_bed_control() の戻り値。
        day_index: 評価対象日のインデックス（0始まり）。
        params: パラメータ辞書。

    Returns:
        dict: 病棟状態の評価結果。
    """
    row = df.iloc[day_index]
    occ = row["occupancy_rate"]
    num_beds = params["num_beds"]

    messages: list[str] = []

    # --- 稼働率ゾーン（40点満点） ---
    if 0.90 <= occ <= 0.95:
        occ_score = 40
        occ_zone = "target"
    elif 0.95 < occ <= 0.97:
        occ_score = 25
        occ_zone = "high"
        messages.append(f"稼働率 {occ*100:.1f}% — 目標上限超過。退院促進を検討")
    elif 0.85 <= occ < 0.90:
        occ_score = 20
        occ_zone = "low"
        messages.append(f"稼働率 {occ*100:.1f}% — 目標下限未達。入院受入を促進")
    elif occ > 0.97:
        occ_score = 10
        occ_zone = "critical"
        messages.append(f"稼働率 {occ*100:.1f}% — 過密状態。緊急退院調整を推奨")
    else:
        occ_score = 5
        occ_zone = "low"
        messages.append(f"稼働率 {occ*100:.1f}% — 大幅低稼働。積極受入を推奨")

    # --- フェーズ構成バランス（30点満点） ---
    actual_a = row["phase_a_ratio"]
    actual_b = row["phase_b_ratio"]
    actual_c = row["phase_c_ratio"]

    deviation = abs(actual_a - 0.15) + abs(actual_b - 0.45) + abs(actual_c - 0.40)
    phase_score = max(0, 30 - int(deviation * 100))

    # ペナルティ
    if actual_b < 0.25:
        phase_score = max(0, phase_score - 10)
        messages.append(f"B群比率 {actual_b*100:.1f}% — 不足（25%未満）")
    if actual_a > 0.35:
        phase_score = max(0, phase_score - 5)
        messages.append(f"A群比率 {actual_a*100:.1f}% — 過多（35%超）")
    if actual_c > 0.50:
        phase_score = max(0, phase_score - 5)
        messages.append(f"C群比率 {actual_c*100:.1f}% — 滞留（50%超）")

    # フェーズバランス判定
    if actual_b < 0.25:
        phase_balance = "b_shortage"
    elif actual_a > 0.35:
        phase_balance = "a_heavy"
    elif actual_c > 0.50:
        phase_balance = "c_stagnant"
    else:
        phase_balance = "balanced"

    # --- 運営貢献効率（20点満点） ---
    daily_profit = row["daily_profit"]
    profit_per_bed = daily_profit / num_beds
    efficiency_ratio = profit_per_bed / 25000  # 基準値 25,000円/床（運営貢献額ベース）
    profit_score = min(20, int(efficiency_ratio * 20))
    profit_score = max(0, profit_score)

    if daily_profit < 0:
        messages.append(f"本日目標未達の運用（運営貢献額 {daily_profit:,.0f} 円）")

    # --- トレンド安定性（10点満点） ---
    # 直近3日の稼働率標準偏差
    start_idx = max(0, day_index - 2)
    recent_occ = df.iloc[start_idx:day_index + 1]["occupancy_rate"]

    if len(recent_occ) >= 2:
        occ_std = recent_occ.std()
    else:
        occ_std = 0.0  # データ不足時は安定とみなす

    if occ_std < 0.02:
        trend_score = 10
    elif occ_std < 0.05:
        trend_score = 6
    else:
        trend_score = 2
        messages.append(f"稼働率変動大（直近3日σ={occ_std:.3f}）")

    # --- 総合スコア ---
    total_score = occ_score + phase_score + profit_score + trend_score
    total_score = max(0, min(100, total_score))

    if total_score >= 80:
        score_label = "healthy"
    elif total_score >= 60:
        score_label = "caution"
    elif total_score >= 40:
        score_label = "warning"
    else:
        score_label = "critical"

    return {
        "date": row["date"],
        "score": score_label,
        "score_numeric": total_score,
        "occupancy_rate": occ,
        "occupancy_zone": occ_zone,
        "phase_balance": phase_balance,
        "phase_a_ratio": actual_a,
        "phase_b_ratio": actual_b,
        "phase_c_ratio": actual_c,
        "profit_per_bed": round(profit_per_bed, 1),
        "messages": messages,
    }


def predict_occupancy(
    df: pd.DataFrame,
    day_index: int,
    params: dict[str, Any],
    horizon: int = 5,
) -> list[dict[str, Any]]:
    """
    直近の入退院ペースから線形回帰で向こうN日の稼働率を予測する。

    Args:
        df: simulate_bed_control() の戻り値。
        day_index: 基準日のインデックス（0始まり）。
        params: パラメータ辞書。
        horizon: 予測日数（デフォルト5日）。

    Returns:
        list[dict]: 各予測日のオフセット・予測稼働率・予測患者数・信頼度。
    """
    num_beds = params["num_beds"]
    current_patients = df.iloc[day_index]["total_patients"]

    # 直近5日（またはday_indexまでの日数）の入退院数から1日あたり純増減を算出
    lookback = min(5, day_index + 1)
    start_idx = day_index - lookback + 1

    recent = df.iloc[start_idx:day_index + 1]
    net_changes = recent["new_admissions"] - recent["discharges"]
    net_change = net_changes.mean()  # 1日あたり平均純増減

    predictions: list[dict[str, Any]] = []
    for t in range(1, horizon + 1):
        predicted_patients = current_patients + net_change * t
        predicted_patients = max(0, min(predicted_patients, num_beds))
        predicted_occ = predicted_patients / num_beds

        # 信頼度: 予測日数が近いほど高い
        if t <= 2:
            confidence = "high"
        elif t <= 4:
            confidence = "medium"
        else:
            confidence = "low"

        predictions.append({
            "day_offset": t,
            "predicted_occupancy": round(predicted_occ, 4),
            "predicted_patients": int(round(predicted_patients)),
            "confidence": confidence,
        })

    return predictions


def suggest_actions(
    ward_status: dict[str, Any],
    forecast: list[dict[str, Any]],
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    病棟状態と予測に基づく具体的アクション提案を返す。

    Args:
        ward_status: assess_ward_status() の戻り値。
        forecast: predict_occupancy() の戻り値。
        params: パラメータ辞書。

    Returns:
        list[dict]: 優先度付きアクションリスト（priority昇順）。
    """
    num_beds = params["num_beds"]
    occ = ward_status["occupancy_rate"]
    phase_b = ward_status["phase_b_ratio"]
    phase_a = ward_status["phase_a_ratio"]
    phase_c = ward_status["phase_c_ratio"]

    actions: list[dict[str, Any]] = []

    # 現在の患者数
    current_patients = int(round(occ * num_beds))

    # 退院推奨数の計算ヘルパー
    target_upper_patients = int(num_beds * params["target_occupancy_upper"])
    excess = max(0, current_patients - target_upper_patients)

    # 受入余力の計算ヘルパー
    target_lower_patients = int(num_beds * params["target_occupancy_lower"])
    capacity = max(0, target_lower_patients - current_patients)

    # --- 条件テーブルに基づくアクション生成 ---

    # 稼働率>97%
    if occ > 0.97:
        actions.append({
            "priority": 1,
            "category": "discharge",
            "action": f"C群から{excess}名退院推奨",
            "expected_impact": f"稼働率 {occ*100:.1f}% → {params['target_occupancy_upper']*100:.0f}% へ",
        })

    # 稼働率>97%かつ翌日も97%超予測
    if occ > 0.97 and len(forecast) >= 1 and forecast[0]["predicted_occupancy"] > 0.97:
        actions.append({
            "priority": 1,
            "category": "alert",
            "action": "緊急退院カンファレンス推奨",
            "expected_impact": "翌日も過密状態が継続する見込み",
        })

    # 稼働率95-97%かつC群>40%
    if 0.95 <= occ <= 0.97 and phase_c > 0.40:
        n_discharge = max(1, excess)
        actions.append({
            "priority": 2,
            "category": "discharge",
            "action": f"C群から{n_discharge}名退院を今週中に推奨",
            "expected_impact": "C群滞留解消と稼働率適正化",
        })

    # 稼働率<85%
    if occ < 0.85:
        actions.append({
            "priority": 1,
            "category": "admission",
            "action": f"空床{capacity}床の受入余力あり → ① 外来へ予定入院の前倒しを依頼 ② 連携室へ紹介元への空床発信を依頼 ③ 外来担当医に入院閾値引き下げを相談",
            "expected_impact": f"稼働率 {occ*100:.1f}% → {params['target_occupancy_lower']*100:.0f}% へ",
        })

    # 稼働率85-90%
    if 0.85 <= occ < 0.90:
        actions.append({
            "priority": 2,
            "category": "admission",
            "action": f"空床{capacity}床の受入余力あり → 外来・連携室へ空床状況を共有し入院受入を促進",
            "expected_impact": f"稼働率 {params['target_occupancy_lower']*100:.0f}% への引き上げ",
        })

    # B群<25%
    if phase_b < 0.25:
        actions.append({
            "priority": 2,
            "category": "hold",
            "action": "B群不足。退院を急がず在院継続推奨",
            "expected_impact": "B群比率改善による運営貢献額の最大化",
        })

    # A群>35%
    if phase_a > 0.35:
        actions.append({
            "priority": 3,
            "category": "admission",
            "action": "A群過多。新規受入を一時抑制推奨",
            "expected_impact": "A群コスト負担の軽減",
        })

    # 3日後の予測チェック
    forecast_3d = [f for f in forecast if f["day_offset"] == 3]
    if forecast_3d:
        pred_occ_3d = forecast_3d[0]["predicted_occupancy"]
        if pred_occ_3d < 0.90:
            actions.append({
                "priority": 2,
                "category": "alert",
                "action": f"3日後に稼働率90%下回る見込み（予測 {pred_occ_3d*100:.1f}%）",
                "expected_impact": "入院受入強化の事前準備推奨",
            })
        if pred_occ_3d > 0.97:
            actions.append({
                "priority": 2,
                "category": "alert",
                "action": f"3日後に過密状態の見込み（予測 {pred_occ_3d*100:.1f}%）",
                "expected_impact": "事前の退院調整推奨",
            })

    # C群>50%
    if phase_c > 0.50:
        actions.append({
            "priority": 3,
            "category": "discharge",
            "action": "C群滞留。転院調整加速推奨",
            "expected_impact": "C群比率の適正化",
        })

    # 日次運営貢献額<0
    if ward_status["profit_per_bed"] * params["num_beds"] < 0:
        actions.append({
            "priority": 3,
            "category": "alert",
            "action": "本日目標未達の運用",
            "expected_impact": "フェーズ構成・稼働率の早急な見直し",
        })

    # priority昇順でソート
    actions.sort(key=lambda x: x["priority"])

    return actions


def simulate_los_impact(
    df: pd.DataFrame,
    params: dict[str, Any],
    delta_days_range: range = range(-3, 4),
) -> list[dict[str, Any]]:
    """
    平均在院日数をN日変動させた場合の運営貢献額インパクトを推計する。

    シミュレーション結果（df）の実績平均患者数を基準にして、在院日数の変動が
    患者数・稼働率・運営貢献額にどう影響するかを推計する。

    計算方法:
    - dfから実際の平均患者数を取得（理論値ではなく実績ベース）
    - 在院日数がN日変わると、平均患者数が (N日/基準LOS) の比率で増減すると仮定
    - 100%を超える場合は入院を断るコストを計上

    Args:
        df: simulate_bed_control() の戻り値。
        params: パラメータ辞書。
        delta_days_range: 在院日数の変動幅（デフォルト -3〜+3）。

    Returns:
        list[dict]: 各変動シナリオの月次運営貢献額・稼働率・フェーズ構成。
    """
    num_beds = params["num_beds"]
    days_in_month = params["days_in_month"]
    opportunity_cost = params["opportunity_cost"]

    # ベースラインの平均在院日数
    base_los = params["avg_length_of_stay"]

    # Little's law で基準患者数を計算（月間入院数パラメータに連動）
    # ※ params["monthly_admissions"] はスライダーで変更可能なため、
    #    dfの実績値ではなくパラメータから計算する必要がある
    monthly_adm = params["monthly_admissions"]
    daily_adm = monthly_adm / days_in_month

    # 稼働効率係数: Little's law の理論値と現場実績の差を補正する
    # 理論上 150名/月 × 18日 / 30日 = 90患者 → 96%稼働率
    # 実績では約90%（曜日偏り・週末効果・転棟タイムラグ等のため）
    # 補正係数 0.94 ≒ 90/96 で現場に近い推計値を出す
    utilization_factor = params.get("utilization_factor", 0.94)
    base_avg_patients = daily_adm * base_los * utilization_factor

    # ベースライン月次運営貢献額（delta=0の参照用）
    baseline_profit: int | None = None

    results: list[dict[str, Any]] = []

    for delta in delta_days_range:
        new_los = base_los + delta
        if new_los < 1:
            continue

        # 実績ベースで患者数を推計:
        # 在院日数がN日変わると、平均患者数は (new_los / base_los) 倍に変化
        new_avg_patients_uncapped = base_avg_patients * (new_los / base_los)

        # 病床数を超える患者は受け入れ不可（物理的制約）
        new_avg_patients = min(new_avg_patients_uncapped, num_beds)
        new_occupancy = new_avg_patients / num_beds

        # 100%超過分: 入院を断る必要がある患者数
        excess_patients = max(0, new_avg_patients_uncapped - num_beds)

        # フェーズ構成比: A=5日, B=9日(6-14), C=max(0, LOS-14)日
        a_days = min(5, new_los)
        b_days = min(9, max(0, new_los - 5))
        c_days = max(0, new_los - 14)
        total_phase_days = a_days + b_days + c_days

        if total_phase_days > 0:
            a_ratio = a_days / total_phase_days
            b_ratio = b_days / total_phase_days
            c_ratio = c_days / total_phase_days
        else:
            a_ratio = 1.0
            b_ratio = 0.0
            c_ratio = 0.0

        # 日次運営貢献額 = 実際の患者数（キャップ後） × 各フェーズの運営貢献額加重平均
        _a_profit = params.get("phase_a_revenue", 36000) - params.get("phase_a_cost", 12000)
        _b_profit = params.get("phase_b_revenue", 36000) - params.get("phase_b_cost", 6000)
        _c_profit = params.get("phase_c_revenue", 33400) - params.get("phase_c_cost", 4500)
        daily_profit = new_avg_patients * (
            a_ratio * _a_profit + b_ratio * _b_profit + c_ratio * _c_profit
        )

        # コスト計上: 100%超過分のみ
        # ※空床コストは計上しない（空床があること自体は、入院需要がなければコストではない）
        # ※超過分のみ「入院を断るコスト」として計上する
        excess_opportunity_loss = excess_patients * opportunity_cost

        # 月次運営貢献額（超過コストのみ差し引く）
        monthly_profit = int((daily_profit - excess_opportunity_loss) * days_in_month)

        if delta == 0:
            baseline_profit = monthly_profit

        results.append({
            "delta_days": delta,
            "estimated_monthly_profit": monthly_profit,
            "profit_diff": 0,  # 後で計算
            "estimated_occupancy": round(new_occupancy, 4),
            "phase_composition": {
                "A": round(a_ratio, 4),
                "B": round(b_ratio, 4),
                "C": round(c_ratio, 4),
            },
        })

    # profit_diff を計算
    if baseline_profit is not None:
        for r in results:
            r["profit_diff"] = r["estimated_monthly_profit"] - baseline_profit

    return results


def calculate_optimal_los_range(
    df: pd.DataFrame, params: dict[str, Any]
) -> dict[str, Any]:
    """
    月間入院数を固定した前提で、稼働率が目標レンジ（90〜95%）に収まる在院日数の範囲を算出する。

    Args:
        df: simulate_bed_control() の戻り値。
        params: パラメータ辞書。

    Returns:
        dict: 最小LOS・最大LOS・最適LOS・予想月次運営貢献額。
    """
    num_beds = params["num_beds"]
    days_in_month = params["days_in_month"]
    base_los_val = params["avg_length_of_stay"]

    target_lower = params["target_occupancy_lower"]
    target_upper = params["target_occupancy_upper"]

    # Little's law で基準患者数を計算（月間入院数パラメータに連動）
    monthly_adm = params["monthly_admissions"]
    daily_adm = monthly_adm / days_in_month
    utilization_factor = params.get("utilization_factor", 0.94)
    base_avg_patients = daily_adm * base_los_val * utilization_factor

    # 実績稼働率ベースでLOS範囲を算出
    # 稼働率 = base_avg_patients * (LOS / base_los) / num_beds
    # LOS = target_occ * num_beds * base_los / base_avg_patients
    if base_avg_patients > 0:
        los_for_lower = (target_lower * num_beds * base_los_val) / base_avg_patients
        los_for_upper = (target_upper * num_beds * base_los_val) / base_avg_patients
    else:
        los_for_lower = base_los_val * 0.8
        los_for_upper = base_los_val * 1.2

    # 修正: 稼働率100%を超えるLOSは除外し、目標レンジ内で運営貢献額最大のLOSを探索
    # 探索範囲を合理的な範囲（14〜25日）に設定
    base_los = params["avg_length_of_stay"]
    search_min = max(1, 14)
    search_max = 25
    search_range = range(search_min - base_los, search_max - base_los + 1)
    los_results = simulate_los_impact(df, params, search_range)

    # 修正: 稼働率100%超のシナリオを除外し、目標レンジ内で運営貢献額最大を探索
    candidates_in_target = [
        r for r in los_results
        if target_lower <= r["estimated_occupancy"] <= target_upper
    ]
    # 目標レンジ内に候補がない場合、稼働率100%以下の全候補から選択
    if not candidates_in_target:
        candidates_in_target = [
            r for r in los_results
            if r["estimated_occupancy"] <= 1.0
        ]
    best = max(candidates_in_target, key=lambda x: x["estimated_monthly_profit"])
    optimal_los = base_los + best["delta_days"]

    return {
        "min_los": round(los_for_lower, 1),
        "max_los": round(los_for_upper, 1),
        "optimal_los": optimal_los,
        "expected_monthly_profit": best["estimated_monthly_profit"],
    }


def calculate_trends(
    df: pd.DataFrame, params: dict[str, Any], window: int = 7
) -> dict[str, Any]:
    """
    移動平均ベースのトレンド分析を行う。

    Args:
        df: simulate_bed_control() の戻り値。
        params: パラメータ辞書。
        window: 移動平均のウィンドウサイズ（デフォルト7日）。

    Returns:
        dict: 稼働率・フェーズ構成比・運営貢献効率のトレンドと移動平均。
    """
    num_beds = params["num_beds"]
    alerts: list[str] = []

    # 有効なウィンドウサイズ（データ数以下に制限）
    effective_window = min(window, len(df))

    def _calc_trend(series: pd.Series, w: int) -> tuple[str, list[float]]:
        """移動平均を計算しトレンド方向を判定する。"""
        ma = series.rolling(window=w, min_periods=1).mean()
        ma_list = [round(v, 4) for v in ma.tolist()]
        if len(ma_list) >= 2:
            diff = ma_list[-1] - ma_list[0]
            if diff > 0.02:
                return "rising", ma_list
            elif diff < -0.02:
                return "falling", ma_list
        return "stable", ma_list

    # 稼働率トレンド
    occ_trend, occ_ma = _calc_trend(df["occupancy_rate"], effective_window)

    # フェーズ構成比トレンド
    a_trend, a_ma = _calc_trend(df["phase_a_ratio"], effective_window)
    b_trend, b_ma = _calc_trend(df["phase_b_ratio"], effective_window)
    c_trend, c_ma = _calc_trend(df["phase_c_ratio"], effective_window)

    # 運営貢献効率トレンド
    profit_per_bed = df["daily_profit"] / num_beds
    profit_trend, profit_ma = _calc_trend(profit_per_bed, effective_window)

    # 警告生成
    target_lower = params["target_occupancy_lower"]
    target_upper = params["target_occupancy_upper"]

    if b_trend == "falling":
        alerts.append("B群比率が下降トレンド — 運営貢献額低下リスク")
    if occ_trend == "falling" and occ_ma[-1] < target_lower:
        alerts.append("稼働率が目標レンジ下限を下回るトレンド")
    if occ_trend == "rising" and occ_ma[-1] > target_upper:
        alerts.append("稼働率が目標レンジ上限を上回るトレンド")
    if profit_trend == "falling":
        alerts.append("運営貢献効率が下降トレンド")

    return {
        "occupancy_trend": occ_trend,
        "occupancy_ma": occ_ma,
        "phase_a_trend": a_trend,
        "phase_b_trend": b_trend,
        "phase_c_trend": c_trend,
        "phase_a_ma": a_ma,
        "phase_b_ma": b_ma,
        "phase_c_ma": c_ma,
        "profit_efficiency_trend": profit_trend,
        "profit_per_bed_ma": profit_ma,
        "alerts": alerts,
    }


def whatif_discharge(
    df: pd.DataFrame,
    day_index: int,
    params: dict[str, Any],
    n_discharge: int,
    target_phase: str = "C",
) -> dict[str, Any]:
    """
    特定フェーズからN名退院させた場合の即時効果を計算する。

    Args:
        df: simulate_bed_control() の戻り値。
        day_index: 基準日のインデックス。
        params: パラメータ辞書。
        n_discharge: 退院させる人数。
        target_phase: 退院対象フェーズ（デフォルト "C"）。

    Returns:
        dict: ベースラインとシナリオの比較結果・推奨判定。
    """
    row = df.iloc[day_index]
    num_beds = params["num_beds"]

    baseline_patients = row["total_patients"]
    new_patients = baseline_patients - n_discharge
    new_occupancy = new_patients / num_beds

    # フェーズ別運営貢献額（収益 - コスト）
    phase_gross = {
        "A": params["phase_a_revenue"] - params["phase_a_cost"],
        "B": params["phase_b_revenue"] - params["phase_b_cost"],
        "C": params["phase_c_revenue"] - params["phase_c_cost"],
    }

    profit_lost = n_discharge * phase_gross[target_phase]
    baseline_profit = row["daily_profit"]
    new_daily_profit = baseline_profit - profit_lost

    # 退院後のフェーズ構成（概算）
    phase_a_count = row["phase_a_count"]
    phase_b_count = row["phase_b_count"]
    phase_c_count = row["phase_c_count"]

    if target_phase == "A":
        phase_a_count = max(0, phase_a_count - n_discharge)
    elif target_phase == "B":
        phase_b_count = max(0, phase_b_count - n_discharge)
    else:
        phase_c_count = max(0, phase_c_count - n_discharge)

    total_after = max(1, phase_a_count + phase_b_count + phase_c_count)
    composition_after = {
        "A": round(phase_a_count / total_after, 4),
        "B": round(phase_b_count / total_after, 4),
        "C": round(phase_c_count / total_after, 4),
    }

    # 推奨判定
    target_lower = params["target_occupancy_lower"]
    target_upper = params["target_occupancy_upper"]

    if target_lower <= new_occupancy <= target_upper:
        recommendation = f"推奨: 退院後稼働率 {new_occupancy*100:.1f}% — 目標レンジ内"
    elif new_occupancy < target_lower:
        recommendation = (
            f"注意: 退院後稼働率 {new_occupancy*100:.1f}% — "
            f"目標下限({target_lower*100:.0f}%)を下回る"
        )
    else:
        recommendation = (
            f"退院後も稼働率 {new_occupancy*100:.1f}% — "
            f"追加退院を検討"
        )

    return {
        "scenario_name": f"{target_phase}群{n_discharge}名退院",
        "baseline_profit": int(baseline_profit),
        "scenario_profit": int(new_daily_profit),
        "profit_diff": int(new_daily_profit - baseline_profit),
        "baseline_occupancy": round(row["occupancy_rate"], 4),
        "scenario_occupancy": round(new_occupancy, 4),
        "phase_composition_after": composition_after,
        "recommendation": recommendation,
    }


def whatif_admission_surge(
    params: dict[str, Any],
    surge_pct: float = 0.2,
    strategy: str = "balanced",
) -> dict[str, Any]:
    """
    入院需要がX%増減した場合の月次インパクトを推計する。

    Args:
        params: パラメータ辞書。
        surge_pct: 入院需要の変動率（+0.2 = 20%増、-0.2 = 20%減）。
        strategy: シミュレーション戦略。

    Returns:
        dict: ベースラインとシナリオの月次比較結果。
    """
    # ベースライン実行
    baseline_df = simulate_bed_control(params, strategy)
    baseline_summary = summarize_results(baseline_df)

    # 変動シナリオ
    modified_params = params.copy()
    modified_params["monthly_admissions"] = int(
        params["monthly_admissions"] * (1 + surge_pct)
    )
    scenario_df = simulate_bed_control(modified_params, strategy)
    scenario_summary = summarize_results(scenario_df)

    profit_diff = scenario_summary["total_profit"] - baseline_summary["total_profit"]

    # 推奨文
    if surge_pct > 0:
        direction = "増加"
    else:
        direction = "減少"

    if scenario_summary["avg_occupancy"] > 0.97:
        recommendation = f"入院{abs(surge_pct)*100:.0f}%{direction}時、過密リスクあり。退院促進体制の強化を推奨"
    elif scenario_summary["avg_occupancy"] < 0.85:
        recommendation = f"入院{abs(surge_pct)*100:.0f}%{direction}時、低稼働リスクあり → 連携室へ紹介元への空床発信を依頼 / 外来へ予定入院の前倒しを依頼"
    else:
        recommendation = f"入院{abs(surge_pct)*100:.0f}%{direction}時、稼働率は許容範囲内"

    return {
        "scenario_name": f"入院需要{surge_pct*100:+.0f}%",
        "baseline_profit": baseline_summary["total_profit"],
        "scenario_profit": scenario_summary["total_profit"],
        "profit_diff": profit_diff,
        "baseline_occupancy": baseline_summary["avg_occupancy"],
        "scenario_occupancy": scenario_summary["avg_occupancy"],
        "recommendation": recommendation,
    }


def whatif_mixed_scenario(
    df: pd.DataFrame,
    day_index: int,
    params: dict[str, Any],
    discharge_a: int = 0,
    discharge_b: int = 0,
    discharge_c: int = 0,
    new_admissions: int = 0,
) -> dict[str, Any]:
    """
    現場のリアルな退院シナリオをシミュレーション。
    A/B/C群それぞれの退院人数と新規入院数を指定して、
    稼働率・運営貢献額・フェーズ構成の変化を計算する。
    """
    row = df.iloc[day_index]

    # ベースライン
    baseline_patients = int(row["total_patients"])
    baseline_a = int(row["phase_a_count"])
    baseline_b = int(row["phase_b_count"])
    baseline_c = int(row["phase_c_count"])

    # 退院人数のバリデーション（各群の在院数を超えないように）
    actual_discharge_a = min(discharge_a, baseline_a)
    actual_discharge_b = min(discharge_b, baseline_b)
    actual_discharge_c = min(discharge_c, baseline_c)
    total_discharge = actual_discharge_a + actual_discharge_b + actual_discharge_c

    # 新規入院のバリデーション（空床数を超えないように）
    remaining_after_discharge = baseline_patients - total_discharge
    available_beds = max(0, params["num_beds"] - remaining_after_discharge)
    actual_new_admissions = min(new_admissions, available_beds)

    # シナリオ後の状態
    new_a = baseline_a - actual_discharge_a + actual_new_admissions  # 新規入院はA群
    new_b = baseline_b - actual_discharge_b
    new_c = baseline_c - actual_discharge_c
    new_total = new_a + new_b + new_c
    new_occupancy = new_total / params["num_beds"]

    # 運営貢献額計算
    gross = {
        "A": params["phase_a_revenue"] - params["phase_a_cost"],
        "B": params["phase_b_revenue"] - params["phase_b_cost"],
        "C": params["phase_c_revenue"] - params["phase_c_cost"],
    }

    baseline_profit = (
        baseline_a * gross["A"] + baseline_b * gross["B"] + baseline_c * gross["C"]
    )
    scenario_profit = new_a * gross["A"] + new_b * gross["B"] + new_c * gross["C"]

    # フェーズ構成比
    new_total_safe = max(new_total, 1)

    # 推奨判定
    target_lower = params.get("target_occupancy_lower", 0.90)
    target_upper = params.get("target_occupancy_upper", 0.95)

    messages: list[str] = []
    if new_occupancy < target_lower:
        messages.append(
            f"⚠️ 稼働率が{new_occupancy*100:.1f}%に低下し目標下限{target_lower*100:.0f}%を下回ります"
        )
    elif new_occupancy > target_upper:
        messages.append(
            f"⚠️ 稼働率が{new_occupancy*100:.1f}%で目標上限{target_upper*100:.0f}%を超過しています"
        )
    else:
        messages.append(f"✅ 稼働率{new_occupancy*100:.1f}%は目標レンジ内です")

    # B群比率チェック
    new_b_ratio = new_b / new_total_safe
    if new_b_ratio < 0.25:
        messages.append("⚠️ B群比率が25%未満。退院を急がず回復期患者を確保すべき")

    # A群比率チェック
    new_a_ratio = new_a / new_total_safe
    if new_a_ratio > 0.35:
        messages.append("⚠️ A群が35%超。初期コスト増で運営貢献額圧迫の恐れ")

    return {
        "scenario_name": (
            f"退院A:{actual_discharge_a}名 B:{actual_discharge_b}名 "
            f"C:{actual_discharge_c}名 / 新規入院:{actual_new_admissions}名"
        ),
        "baseline": {
            "total": baseline_patients,
            "a": baseline_a,
            "b": baseline_b,
            "c": baseline_c,
            "occupancy": row["occupancy_rate"],
            "daily_profit": int(baseline_profit),
        },
        "scenario": {
            "total": new_total,
            "a": new_a,
            "b": new_b,
            "c": new_c,
            "occupancy": round(new_occupancy, 4),
            "daily_profit": int(scenario_profit),
        },
        "diff": {
            "total": new_total - baseline_patients,
            "occupancy": round(new_occupancy - row["occupancy_rate"], 4),
            "daily_profit": int(scenario_profit - baseline_profit),
        },
        "phase_composition_after": {
            "A": round(new_a / new_total_safe, 3),
            "B": round(new_b / new_total_safe, 3),
            "C": round(new_c / new_total_safe, 3),
        },
        "messages": messages,
        "discharge_detail": {
            "a": actual_discharge_a,
            "b": actual_discharge_b,
            "c": actual_discharge_c,
            "total": total_discharge,
            "new_admissions": actual_new_admissions,
        },
    }


def whatif_weekly_plan(
    df: pd.DataFrame,
    params: dict[str, Any],
    daily_plans: list[dict[str, int]],
) -> dict[str, Any]:
    """
    1週間の入退院計画をシミュレーション。

    daily_plans: [{"day_index": int, "discharge_a": int, "discharge_b": int,
                   "discharge_c": int, "new_admissions": int}, ...]
    各日の結果を順次計算し、前日の結果が翌日のベースラインになる。
    """
    results: list[dict[str, Any]] = []
    current_state: dict[str, int] | None = None

    for plan in daily_plans:
        day_idx = plan["day_index"]
        if day_idx >= len(df):
            break

        if current_state is None:
            # 初日はdfのデータを使用
            row = df.iloc[day_idx]
            current_a = int(row["phase_a_count"])
            current_b = int(row["phase_b_count"])
            current_c = int(row["phase_c_count"])
            current_total = int(row["total_patients"])
        else:
            # 2日目以降は前日のシナリオ結果を使用
            current_a = current_state["a"]
            current_b = current_state["b"]
            current_c = current_state["c"]
            current_total = current_state["total"]

        # 退院処理
        d_a = min(plan.get("discharge_a", 0), current_a)
        d_b = min(plan.get("discharge_b", 0), current_b)
        d_c = min(plan.get("discharge_c", 0), current_c)

        after_a = current_a - d_a
        after_b = current_b - d_b
        after_c = current_c - d_c
        after_total = after_a + after_b + after_c

        # 新規入院
        available = max(0, params["num_beds"] - after_total)
        new_adm = min(plan.get("new_admissions", 0), available)

        final_a = after_a + new_adm  # 新規入院はA群
        final_b = after_b
        final_c = after_c
        final_total = final_a + final_b + final_c

        occupancy = final_total / params["num_beds"]

        gross = {
            "A": params["phase_a_revenue"] - params["phase_a_cost"],
            "B": params["phase_b_revenue"] - params["phase_b_cost"],
            "C": params["phase_c_revenue"] - params["phase_c_cost"],
        }
        profit = final_a * gross["A"] + final_b * gross["B"] + final_c * gross["C"]

        day_result = {
            "day_index": day_idx,
            "date": (
                df.iloc[day_idx]["date"] if day_idx < len(df) else f"Day {day_idx + 1}"
            ),
            "discharge": {"a": d_a, "b": d_b, "c": d_c, "total": d_a + d_b + d_c},
            "new_admissions": new_adm,
            "after": {
                "a": final_a,
                "b": final_b,
                "c": final_c,
                "total": final_total,
            },
            "occupancy": round(occupancy, 4),
            "daily_profit": int(profit),
        }
        results.append(day_result)

        # フェーズ遷移（簡易：B群の一部がC群に、A群の一部がB群に進む）
        transition_a_to_b = max(0, int(final_a * 0.20))  # A群の20%がB群へ
        transition_b_to_c = max(0, int(final_b * 0.10))  # B群の10%がC群へ

        current_state = {
            "a": final_a - transition_a_to_b,
            "b": final_b + transition_a_to_b - transition_b_to_c,
            "c": final_c + transition_b_to_c,
            "total": final_total,
        }

    # 週間サマリー
    total_discharge = sum(r["discharge"]["total"] for r in results)
    total_admission = sum(r["new_admissions"] for r in results)
    total_profit = sum(r["daily_profit"] for r in results)
    avg_occupancy = sum(r["occupancy"] for r in results) / max(len(results), 1)

    return {
        "daily_results": results,
        "summary": {
            "total_discharge": total_discharge,
            "total_admission": total_admission,
            "total_profit": total_profit,
            "avg_occupancy": round(avg_occupancy, 4),
            "days_planned": len(results),
        },
    }


# ======================== 病棟運営最適化アドバイザー ============================ #


def calculate_marginal_bed_value(params: dict[str, Any]) -> dict[str, Any]:
    """
    各フェーズの1床1日あたりの限界価値を計算し、
    退院・保持の経済的判断基準を提供する。

    Args:
        params: パラメータ辞書（phase_a_revenue/cost, phase_b_*, phase_c_*,
                avg_length_of_stay 等を含む）。

    Returns:
        dict: phase_gross, new_admission_lifetime_profit,
              new_admission_daily_avg, c_hold_daily_value,
              c_replace_day1_impact, c_replace_lifetime_impact,
              breakeven_days, opportunity_cost_per_day。
    """
    gross_a = params["phase_a_revenue"] - params["phase_a_cost"]
    gross_b = params["phase_b_revenue"] - params["phase_b_cost"]
    gross_c = params["phase_c_revenue"] - params["phase_c_cost"]

    avg_los = params.get("avg_length_of_stay", 18)
    a_days = min(5, avg_los)
    b_days = min(9, max(0, avg_los - 5))
    c_days = max(0, avg_los - 14)

    # 新規入院1名の生涯期待運営貢献額
    lifetime_profit = a_days * gross_a + b_days * gross_b + c_days * gross_c
    # 新規入院1名の日平均運営貢献額
    daily_avg_profit = lifetime_profit / max(avg_los, 1)

    # C群を1日延長する純価値（未活用病床コストなしの場合）
    c_hold_value = gross_c
    # C群を退院させて新規を入れた場合の損益変化
    replace_day1_impact = -gross_c + gross_a  # 当日の損益変化
    replace_lifetime_impact = lifetime_profit - gross_c  # 生涯で見た純効果

    # 損益分岐日数: 何日で新規入院の累積運営貢献額がC群延長を上回るか
    breakeven_days = 0
    cum_new = 0
    cum_hold = 0
    for d in range(1, 60):
        cum_hold += gross_c
        if d <= 5:
            cum_new += gross_a
        elif d <= 14:
            cum_new += gross_b
        else:
            cum_new += gross_c
        if cum_new >= cum_hold and breakeven_days == 0:
            breakeven_days = d

    return {
        "phase_gross": {"A": gross_a, "B": gross_b, "C": gross_c},
        "new_admission_lifetime_profit": int(lifetime_profit),
        "new_admission_daily_avg": int(daily_avg_profit),
        "c_hold_daily_value": gross_c,
        "c_replace_day1_impact": replace_day1_impact,
        "c_replace_lifetime_impact": int(replace_lifetime_impact),
        "breakeven_days": breakeven_days,
        "opportunity_cost_per_day": params.get("opportunity_cost", 25000),
    }


def optimize_discharge_plan(
    df: pd.DataFrame,
    day_index: int,
    params: dict[str, Any],
    expected_daily_demand: int = 5,
) -> dict[str, Any]:
    """
    収益を最大化する退院計画を自動生成する。

    需要（入院希望患者数）と現在の稼働率から、
    C群の退院数と新規入院数の最適バランスを算出する。

    Args:
        df: simulate_bed_control() の戻り値 DataFrame。
        day_index: 評価対象日のインデックス。
        params: パラメータ辞書。
        expected_daily_demand: 1日あたりの入院需要（期待値）。

    Returns:
        dict: current_state, recommendation, after_state,
              economics, reasoning, marginal_values。
    """
    row = df.iloc[day_index]
    num_beds = params["num_beds"]
    target_lower = params.get("target_occupancy_lower", 0.90)
    target_upper = params.get("target_occupancy_upper", 0.95)

    current_total = int(row["total_patients"])
    current_a = int(row["phase_a_count"])
    current_b = int(row["phase_b_count"])
    current_c = int(row["phase_c_count"])
    current_occupancy = row["occupancy_rate"]

    empty_beds = num_beds - current_total
    marginal = calculate_marginal_bed_value(params)

    # === 最適退院数の計算 ===
    optimal_c_discharge = 0
    optimal_b_discharge = 0
    reasoning: list[str] = []

    if current_occupancy < target_lower:
        # 稼働率が低い → 退院させない、入院促進施策を展開
        reasoning.append(
            f"稼働率{current_occupancy*100:.1f}%は目標下限{target_lower*100:.0f}%未満"
        )
        reasoning.append("→ 退院は最小限にし、外来へ予定入院前倒し依頼・連携室へ紹介元への空床発信依頼・外来担当医へ入院閾値引き下げ相談")
        optimal_c_discharge = 0
        recommended_admissions = min(expected_daily_demand, empty_beds)

    elif current_occupancy <= target_upper:
        # 目標レンジ内
        if expected_daily_demand > empty_beds:
            # 需要が空床を超える → C群から退院させて受入枠を確保
            need_beds = expected_daily_demand - empty_beds
            optimal_c_discharge = min(need_beds, current_c)
            reasoning.append(
                f"入院需要{expected_daily_demand}名に対し空床{empty_beds}床"
            )
            reasoning.append(
                f"→ C群から{optimal_c_discharge}名退院させて受入枠を確保"
            )
            recommended_admissions = min(
                expected_daily_demand, empty_beds + optimal_c_discharge
            )
        else:
            # 需要 ≤ 空床 → 退院不要、そのまま受入
            reasoning.append(
                f"空床{empty_beds}床で入院需要{expected_daily_demand}名を収容可能"
            )
            reasoning.append(
                "→ C群は退院させず持たせる（運営貢献額2.9万/日を継続獲得）"
            )
            optimal_c_discharge = 0
            recommended_admissions = expected_daily_demand

    else:
        # 稼働率が高い
        over_count = current_total - int(num_beds * target_upper)
        optimal_c_discharge = min(max(over_count, 0), current_c)
        if optimal_c_discharge < max(over_count, 0):
            optimal_b_discharge = min(
                max(over_count, 0) - optimal_c_discharge,
                max(0, current_b - int(current_total * 0.25)),
            )
        reasoning.append(
            f"稼働率{current_occupancy*100:.1f}%が目標上限{target_upper*100:.0f}%超過"
        )
        reasoning.append(f"→ C群{optimal_c_discharge}名の退院調整を推奨")
        if optimal_b_discharge > 0:
            reasoning.append(
                f"→ B群後半（12日目以降）から{optimal_b_discharge}名も検討"
            )
        recommended_admissions = min(
            expected_daily_demand,
            empty_beds + optimal_c_discharge + optimal_b_discharge,
        )

    # === 経済効果の計算 ===
    total_discharge = optimal_c_discharge + optimal_b_discharge

    # 退院による運営貢献額減少
    lost_profit = (
        optimal_c_discharge * marginal["phase_gross"]["C"]
        + optimal_b_discharge * marginal["phase_gross"]["B"]
    )

    # 新規入院による運営貢献額増加（初日はA群）
    gained_profit = recommended_admissions * marginal["phase_gross"]["A"]

    # 将来利益（新規入院の生涯期待値）
    future_gain = recommended_admissions * marginal["new_admission_lifetime_profit"]

    # 最適後の状態
    new_total = current_total - total_discharge + recommended_admissions
    new_occupancy = new_total / max(num_beds, 1)

    return {
        "current_state": {
            "total": current_total,
            "occupancy": current_occupancy,
            "a": current_a,
            "b": current_b,
            "c": current_c,
            "empty_beds": empty_beds,
        },
        "recommendation": {
            "c_discharge": optimal_c_discharge,
            "b_discharge": optimal_b_discharge,
            "total_discharge": total_discharge,
            "new_admissions": recommended_admissions,
        },
        "after_state": {
            "total": new_total,
            "occupancy": round(new_occupancy, 4),
        },
        "economics": {
            "daily_lost_profit": int(lost_profit),
            "daily_gained_profit": int(gained_profit),
            "daily_net_impact": int(gained_profit - lost_profit),
            "future_gain_from_new": int(future_gain),
            "c_hold_value_per_day": marginal["c_hold_daily_value"],
            "breakeven_days": marginal["breakeven_days"],
        },
        "reasoning": reasoning,
        "marginal_values": marginal,
    }


def generate_decision_report(
    df: pd.DataFrame,
    params: dict[str, Any],
    strategy: str = "balanced",
) -> dict[str, Any]:
    """
    全意思決定支援機能を統合したレポートを生成する。

    最終日の病棟状態・予測・アクション提案・LOS影響分析・最適LOS・
    トレンド分析・What-Ifシナリオをまとめて返す。

    Args:
        df: simulate_bed_control() の戻り値。
        params: パラメータ辞書。
        strategy: シミュレーション戦略名。

    Returns:
        dict: 統合レポート辞書（ward_status, forecast, actions, los_impact,
              optimal_los, trends, whatif_discharge_2c, summary_text）。
    """
    last_idx = len(df) - 1

    # 各分析を実行
    ward_status = assess_ward_status(df, last_idx, params)
    forecast = predict_occupancy(df, last_idx, params)
    actions = suggest_actions(ward_status, forecast, params)
    los_impact = simulate_los_impact(df, params)
    optimal_los = calculate_optimal_los_range(df, params)
    trends = calculate_trends(df, params)
    whatif_2c = whatif_discharge(df, last_idx, params, n_discharge=2, target_phase="C")

    # サマリーテキスト生成（日本語）
    lines: list[str] = []
    lines.append(f"■ 病棟状態: {ward_status['score']}（{ward_status['score_numeric']}点）")
    lines.append(
        f"  稼働率 {ward_status['occupancy_rate']*100:.1f}% / "
        f"A群 {ward_status['phase_a_ratio']*100:.1f}% / "
        f"B群 {ward_status['phase_b_ratio']*100:.1f}% / "
        f"C群 {ward_status['phase_c_ratio']*100:.1f}%"
    )

    if ward_status["messages"]:
        for msg in ward_status["messages"]:
            lines.append(f"  ! {msg}")

    lines.append(f"■ トレンド: 稼働率={trends['occupancy_trend']}, "
                 f"B群={trends['phase_b_trend']}, "
                 f"運営貢献効率={trends['profit_efficiency_trend']}")

    if trends["alerts"]:
        for alert in trends["alerts"]:
            lines.append(f"  ! {alert}")

    if forecast:
        f3 = [f for f in forecast if f["day_offset"] == 3]
        if f3:
            lines.append(
                f"■ 3日後予測: 稼働率 {f3[0]['predicted_occupancy']*100:.1f}%"
                f"（信頼度: {f3[0]['confidence']}）"
            )

    if actions:
        lines.append(f"■ アクション提案: {len(actions)}件")
        for a in actions[:3]:  # 上位3件
            lines.append(f"  [{a['category']}] {a['action']}")

    lines.append(
        f"■ 最適在院日数: {optimal_los['optimal_los']}日"
        f"（許容範囲 {optimal_los['min_los']:.1f}〜{optimal_los['max_los']:.1f}日）"
    )

    lines.append(
        f"■ C群2名退院シナリオ: 運営貢献額差 {whatif_2c['profit_diff']:+,}円/日, "
        f"{whatif_2c['recommendation']}"
    )

    summary_text = "\n".join(lines)

    # 病棟運営最適化アドバイザー
    optimization = optimize_discharge_plan(df, last_idx, params)

    return {
        "ward_status": ward_status,
        "forecast": forecast,
        "actions": actions,
        "los_impact": los_impact,
        "optimal_los": optimal_los,
        "trends": trends,
        "whatif_discharge_2c": whatif_2c,
        "optimization": optimization,
        "summary_text": summary_text,
    }


# ================================ メイン ==================================== #


def main() -> None:
    """
    メインエントリポイント。

    実行フロー:
        1. 3戦略（rotation, stable, balanced）を順次シミュレーション
        2. 各戦略の日次結果をCSV出力（output/フォルダ）
        3. 各戦略のグラフ出力（PNG）
        4. 戦略比較表をコンソール出力＋CSV出力
        5. 最適戦略（運営貢献額最大）を表示
    """
    print("=" * 60)
    print(" ベッドコントロールシミュレーター v1.0")
    print(" 地域包括医療病棟（94床）")
    print("=" * 60)

    _ensure_output_dir()
    params = create_default_params()

    strategies = ["rotation", "stable", "balanced"]
    strategy_labels = {
        "rotation": "回転重視",
        "stable": "安定維持",
        "balanced": "バランス",
    }

    results: dict[str, pd.DataFrame] = {}
    summaries: dict[str, dict[str, Any]] = {}

    # --- 各戦略のシミュレーション実行 ---
    for strat in strategies:
        label = strategy_labels[strat]
        print(f"\n--- 戦略: {label}（{strat}）---")

        df = simulate_bed_control(params, strat)
        results[strat] = df
        summaries[strat] = summarize_results(df)

        # CSV出力
        csv_path = OUTPUT_DIR / f"bed_sim_{strat}.csv"
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"  CSV保存: {csv_path}")

        # グラフ出力
        try:
            plot_simulation(df, strat)
        except Exception as e:
            print(f"  [警告] グラフ作成に失敗しました: {e}")

        # サマリー表示
        s = summaries[strat]
        print(f"  平均稼働率: {s['avg_occupancy'] * 100:.1f}%")
        print(f"  月次運営貢献額: {s['total_profit']:,.0f} 円")
        print(
            f"  目標レンジ日数: {s['days_in_target_range']} / "
            f"{params['days_in_month']} 日"
        )
        print(
            f"  A群比率: {s['avg_phase_a_ratio'] * 100:.1f}% / "
            f"B群比率: {s['avg_phase_b_ratio'] * 100:.1f}% / "
            f"C群比率: {s['avg_phase_c_ratio'] * 100:.1f}%"
        )

    # --- 戦略比較 ---
    print("\n" + "=" * 60)
    print(" 戦略比較")
    print("=" * 60)

    comparison_df = pd.DataFrame(summaries)
    print(comparison_df.to_string())

    # 比較CSV出力
    comp_csv_path = OUTPUT_DIR / "bed_sim_strategy_comparison.csv"
    comparison_df.to_csv(comp_csv_path, encoding="utf-8-sig")
    print(f"\n  比較表CSV保存: {comp_csv_path}")

    # 戦略比較グラフ
    try:
        plot_strategy_comparison(comparison_df)
    except Exception as e:
        print(f"  [警告] 戦略比較グラフ作成に失敗しました: {e}")

    # --- 最適戦略の特定 ---
    profits = {s: summaries[s]["total_profit"] for s in strategies}
    best = max(profits, key=profits.get)  # type: ignore[arg-type]

    print("\n" + "=" * 60)
    print(f" 最適戦略: {strategy_labels[best]}（{best}）")
    print(f" 月次運営貢献額: {profits[best]:,.0f} 円")
    print("=" * 60)

    # --- 各戦略の詳細一覧 ---
    print("\n[補足] 各戦略の特徴:")
    for strat in strategies:
        label = strategy_labels[strat]
        s = summaries[strat]
        print(
            f"  {label}({strat}): "
            f"運営貢献額 {s['total_profit']:>12,.0f} 円 | "
            f"稼働率 {s['avg_occupancy'] * 100:.1f}% | "
            f"目標レンジ {s['days_in_target_range']}日"
        )

    # === 意思決定支援レポート ===
    print("\n" + "=" * 60)
    print("意思決定支援レポート（バランス戦略）")
    print("=" * 60)

    balanced_df = results["balanced"]
    report = generate_decision_report(balanced_df, params, "balanced")

    # ward_status表示
    ws = report["ward_status"]
    print(f"\n【病棟状態】 {ws['date']}")
    print(f"  総合スコア: {ws['score_numeric']}点 → {ws['score']}")
    print(f"  稼働率: {ws['occupancy_rate']*100:.1f}%（ゾーン: {ws['occupancy_zone']}）")
    print(f"  フェーズバランス: {ws['phase_balance']}")
    print(f"    A群 {ws['phase_a_ratio']*100:.1f}% / "
          f"B群 {ws['phase_b_ratio']*100:.1f}% / "
          f"C群 {ws['phase_c_ratio']*100:.1f}%")
    print(f"  運営貢献効率: {ws['profit_per_bed']:,.0f} 円/床")
    if ws["messages"]:
        for msg in ws["messages"]:
            print(f"  ! {msg}")

    # forecast表示
    print("\n【稼働率予測（向こう5日）】")
    for fc in report["forecast"]:
        print(f"  +{fc['day_offset']}日: "
              f"稼働率 {fc['predicted_occupancy']*100:.1f}% "
              f"({fc['predicted_patients']}名) "
              f"[信頼度: {fc['confidence']}]")

    # actions表示
    print("\n【アクション提案】")
    if report["actions"]:
        for a in report["actions"]:
            print(f"  [優先度{a['priority']}][{a['category']}] "
                  f"{a['action']} → {a['expected_impact']}")
    else:
        print("  特になし")

    # los_impact表示
    print("\n【在院日数変動インパクト（Little's law推計）】")
    for li in report["los_impact"]:
        sign = "+" if li["delta_days"] >= 0 else ""
        pc = li["phase_composition"]
        print(f"  LOS {sign}{li['delta_days']}日: "
              f"月次運営貢献額 {li['estimated_monthly_profit']:>12,}円 "
              f"(差分 {li['profit_diff']:>+10,}円) "
              f"稼働率 {li['estimated_occupancy']*100:.1f}% "
              f"A:{pc['A']*100:.0f}%/B:{pc['B']*100:.0f}%/C:{pc['C']*100:.0f}%")

    # optimal_los表示
    opt = report["optimal_los"]
    print(f"\n【最適在院日数】")
    print(f"  最適LOS: {opt['optimal_los']}日 "
          f"（目標稼働率レンジ対応: {opt['min_los']:.1f}〜{opt['max_los']:.1f}日）")
    print(f"  予想月次運営貢献額: {opt['expected_monthly_profit']:,}円")

    print(f"\n完了。出力先: {OUTPUT_DIR}")


# =========================================================================== #


if __name__ == "__main__":
    main()
