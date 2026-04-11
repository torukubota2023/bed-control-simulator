"""
bed_management_metrics.py — 空床時間マネジメント指標モジュール

病棟稼働率シミュレーター v3.0 の中核指標を pure function として提供する。
UI (Streamlit) に依存しない純粋計算ロジックのみを含む。

主な責務:
- 週末空床コスト計算
- 退院翌日再利用率
- 金→月充填率
- 退院前倒し × 充填確率 What-If
- 未充填退院キュー proxy (pseudo lag)
- データ前処理 (病棟集約・曜日付与・空床列生成)
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Optional


# ---------------------------------------------------------------------------
# データ前処理
# ---------------------------------------------------------------------------

def prepare_bed_mgmt_daily_df(
    df: pd.DataFrame,
    selected_ward: str,
    total_beds: int,
) -> pd.DataFrame:
    """
    日次データを空床マネジメント分析用に前処理する。

    Args:
        df: 日次データ (date, total_patients, new_admissions, discharges, [ward])
        selected_ward: "全体" / "5F" / "6F"
        total_beds: 対象病床数

    Returns:
        前処理済みDataFrame (dow列・empty列付き)
    """
    if df is None or not isinstance(df, pd.DataFrame) or len(df) == 0:
        return pd.DataFrame()

    work = df.copy()
    work["date"] = pd.to_datetime(work["date"])

    # 病棟フィルタリング
    if "ward" in work.columns:
        if selected_ward in ("5F", "6F"):
            work = work[work["ward"] == selected_ward]
        else:
            work = work.groupby("date").agg({
                "total_patients": "sum",
                "new_admissions": "sum",
                "discharges": "sum",
            }).reset_index()

    if len(work) == 0:
        return pd.DataFrame()

    work["dow"] = work["date"].dt.dayofweek  # 0=月, 4=金, 5=土, 6=日
    work["empty"] = total_beds - work["total_patients"].clip(upper=total_beds)

    return work.sort_values("date").reset_index(drop=True)


# ---------------------------------------------------------------------------
# 週末空床メトリクス
# ---------------------------------------------------------------------------

def calculate_weekend_empty_metrics(
    df: pd.DataFrame,
    total_beds: int,  # noqa: ARG001 - 将来の拡張用
) -> dict:
    """
    曜日別の空床パターンと金→月充填率を算出する。

    Args:
        df: prepare_bed_mgmt_daily_df() の出力 (dow, empty, discharges, new_admissions 列必須)
        total_beds: 病床数

    Returns:
        dict with keys:
            fri_empty, sat_empty, sun_empty, weekend_empty,
            fri_dis, mon_adm, fri_to_mon_fill_rate
    """
    if df is None or not isinstance(df, pd.DataFrame) or len(df) == 0:
        return {
            "fri_empty": 0, "sat_empty": 0, "sun_empty": 0,
            "weekend_empty": 0, "fri_dis": 0, "mon_adm": 0,
            "fri_to_mon_fill_rate": 0,
        }

    dow_empty = df.groupby("dow")["empty"].mean()
    fri_empty = dow_empty.get(4, 0)
    sat_empty = dow_empty.get(5, 0)
    sun_empty = dow_empty.get(6, 0)
    weekend_empty = (sat_empty + sun_empty) / 2

    fri_dis = (
        df[df["dow"] == 4]["discharges"].mean()
        if "discharges" in df.columns and 4 in df["dow"].values
        else 0
    )
    mon_adm = (
        df[df["dow"] == 0]["new_admissions"].mean()
        if "new_admissions" in df.columns and 0 in df["dow"].values
        else 0
    )
    fri_to_mon_fill_rate = (mon_adm / fri_dis * 100) if fri_dis > 0 else 0

    return {
        "fri_empty": float(fri_empty),
        "sat_empty": float(sat_empty),
        "sun_empty": float(sun_empty),
        "weekend_empty": float(weekend_empty),
        "fri_dis": float(fri_dis),
        "mon_adm": float(mon_adm),
        "fri_to_mon_fill_rate": float(fri_to_mon_fill_rate),
    }


# ---------------------------------------------------------------------------
# 退院翌日再利用率
# ---------------------------------------------------------------------------

def calculate_next_day_reuse_rate(df: pd.DataFrame) -> dict:
    """
    退院翌日に同数以上の入院があった割合 (proxy reuse rate)。

    Args:
        df: prepare_bed_mgmt_daily_df() の出力 (date順にソート済み)

    Returns:
        dict with keys: reuse_pairs, reuse_total, reuse_rate (%)
    """
    if df is None or not isinstance(df, pd.DataFrame) or len(df) < 2:
        return {"reuse_pairs": 0, "reuse_total": 0, "reuse_rate": 0.0}

    sorted_df = df.sort_values("date").reset_index(drop=True)
    reuse_pairs = 0
    reuse_total = 0

    for i in range(len(sorted_df) - 1):
        today_dis = int(sorted_df.iloc[i].get("discharges", 0) or 0)
        tomorrow_adm = int(sorted_df.iloc[i + 1].get("new_admissions", 0) or 0)
        if today_dis > 0:
            reuse_pairs += min(today_dis, tomorrow_adm)
            reuse_total += today_dis

    reuse_rate = (reuse_pairs / reuse_total * 100) if reuse_total > 0 else 0.0

    return {
        "reuse_pairs": reuse_pairs,
        "reuse_total": reuse_total,
        "reuse_rate": float(reuse_rate),
    }


# ---------------------------------------------------------------------------
# 週末空床コスト
# ---------------------------------------------------------------------------

def calculate_weekend_costs(
    weekend_empty: float,
    unit_price_per_day: float,
) -> dict:
    """
    週末空床コスト (週次・月次・年次) を算出する。概算値。

    Args:
        weekend_empty: 土日平均空床数
        unit_price_per_day: 1日あたり入院単価

    Returns:
        dict with keys: weekly, monthly, annual
    """
    weekly = weekend_empty * 2 * unit_price_per_day
    monthly = weekly * 4
    annual = monthly * 12

    return {
        "weekly": float(weekly),
        "monthly": float(monthly),
        "annual": float(annual),
    }


# ---------------------------------------------------------------------------
# 退院前倒し × 充填確率 What-If
# ---------------------------------------------------------------------------

def calculate_weekend_whatif(
    shift: int,
    fill_rate: float,
    weekend_empty: float,
    unit_price_per_day: float,
) -> dict:
    """
    金曜退院を木曜に前倒しした場合の空床改善効果を試算する。

    前倒しだけでは空床は減らない。
    空いた床に新規入院が入る確率 (充填確率) を掛けて初めて効果が出る。

    Args:
        shift: 前倒し人数
        fill_rate: 充填確率 (0〜100)
        weekend_empty: 改善前の土日平均空床数
        unit_price_per_day: 1日あたり入院単価

    Returns:
        dict with keys:
            effective_fill, new_weekend_empty,
            new_cost_weekly, saving_weekly, saving_annual
    """
    effective_fill = shift * (fill_rate / 100)
    new_weekend_empty = max(0.0, weekend_empty - effective_fill)
    new_cost_weekly = new_weekend_empty * 2 * unit_price_per_day
    before_cost_weekly = weekend_empty * 2 * unit_price_per_day
    saving_weekly = before_cost_weekly - new_cost_weekly
    saving_annual = saving_weekly * 4 * 12

    return {
        "effective_fill": float(effective_fill),
        "new_weekend_empty": float(new_weekend_empty),
        "new_cost_weekly": float(new_cost_weekly),
        "saving_weekly": float(saving_weekly),
        "saving_annual": float(saving_annual),
    }


# ---------------------------------------------------------------------------
# 未充填退院キュー proxy (pseudo lag)
# ---------------------------------------------------------------------------

def calculate_unfilled_discharge_queue(df: pd.DataFrame) -> dict:
    """
    未充填退院キュー: 退院で空いた床がまだ埋まっていない擬似在庫を推計する。

    計算式: q_t = max(0, q_{t-1} + discharges_t - admissions_t)

    ※ 時刻データがないため推計 proxy。実測値ではない。

    Args:
        df: prepare_bed_mgmt_daily_df() の出力 (date順)

    Returns:
        dict with keys:
            queue_series: list of (date, q_t) tuples
            pseudo_empty_bed_days: sum of q_t (面積)
            pseudo_lag_days: pseudo_empty_bed_days / total_discharges
            queue_7d_avg: 7日移動平均の最終値
    """
    if df is None or not isinstance(df, pd.DataFrame) or len(df) == 0:
        return {
            "queue_series": [],
            "pseudo_empty_bed_days": 0.0,
            "pseudo_lag_days": 0.0,
            "queue_7d_avg": 0.0,
        }

    sorted_df = df.sort_values("date").reset_index(drop=True)
    q = 0.0
    queue_values = []
    queue_series = []
    total_discharges = 0

    for _, row in sorted_df.iterrows():
        dis = int(row.get("discharges", 0) or 0)
        adm = int(row.get("new_admissions", 0) or 0)
        q = max(0.0, q + dis - adm)
        queue_values.append(q)
        queue_series.append((row["date"], q))
        total_discharges += dis

    pseudo_empty_bed_days = sum(queue_values)
    pseudo_lag_days = (
        pseudo_empty_bed_days / total_discharges
        if total_discharges > 0 else 0.0
    )

    # 7日移動平均の最終値
    q_series = pd.Series(queue_values)
    queue_7d_avg = float(q_series.rolling(7, min_periods=1).mean().iloc[-1])

    return {
        "queue_series": queue_series,
        "pseudo_empty_bed_days": float(pseudo_empty_bed_days),
        "pseudo_lag_days": float(pseudo_lag_days),
        "queue_7d_avg": queue_7d_avg,
    }
