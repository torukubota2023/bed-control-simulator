"""
demand_forecast.py — 需要予測モジュール（Phase 3α: 需要条件付き木曜前倒しロジック）

週末空床コスト What-If を「需要側が無限」前提から切り離し、
過去実績ベースの需要予測と既存空床の比較で「前倒しが有効か/逆効果か」を判定する。

主な責務:
- 過去12ヶ月の入院実績から曜日別需要ベースラインを構築
- 対象週の需要予測（曜日別平均 + 直近2週トレンド補正）
- 既存空床の推定（稼働率ベース）
- 週タイプ分類（high / standard / low）— 前倒しの有効性を決定

この関数群はすべて pure function で、UI (Streamlit) に依存しない。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional, Literal

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

# 病床数デフォルト — HOSPITAL_DEFAULTS["total_beds"] と同値（単一ソース原則）
# 変更時は scripts/reimbursement_config.py も同時更新すること
DEFAULT_TOTAL_BEDS = 94

# 曜日ラベル（月=0 ... 日=6）
_DOW_JA = ["月", "火", "水", "木", "金", "土", "日"]

# 分類境界（床/日）
DEFAULT_MARGIN = 1.0


# ---------------------------------------------------------------------------
# データ読み込み
# ---------------------------------------------------------------------------

def load_historical_admissions(
    path: str = "data/admissions_consolidated_dedup.csv",
) -> pd.DataFrame:
    """
    1年分の入院実績 CSV を読み込む。

    Args:
        path: CSV のパス（プロジェクトルート相対 or 絶対）

    Returns:
        DataFrame with columns:
            admission_date (datetime), ward_short ("5F"|"6F"),
            dow (0-6), type_short
        空 CSV や読み込み失敗時は空 DataFrame を返す。
    """
    try:
        df = pd.read_csv(path)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return pd.DataFrame(
            columns=["admission_date", "ward_short", "dow", "type_short"]
        )

    if len(df) == 0:
        return df

    # admission_date を datetime に変換
    if "admission_date" in df.columns:
        df["admission_date"] = pd.to_datetime(df["admission_date"], errors="coerce")
        df = df.dropna(subset=["admission_date"])

    # dow 列がなければ付与
    if "dow" not in df.columns and "admission_date" in df.columns:
        df["dow"] = df["admission_date"].dt.dayofweek

    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# 需要予測
# ---------------------------------------------------------------------------

def _compute_dow_means(
    df: pd.DataFrame, date_col: str = "admission_date"
) -> dict[int, float]:
    """曜日別の1日平均入院数を計算する。"""
    if df is None or len(df) == 0 or date_col not in df.columns:
        return {i: 0.0 for i in range(7)}

    # 日ごとに集計 → 曜日別平均
    daily = df.groupby(df[date_col].dt.date).size().reset_index(name="count")
    daily["dow"] = pd.to_datetime(daily[date_col]).dt.dayofweek
    means = daily.groupby("dow")["count"].mean()

    return {i: float(means.get(i, 0.0)) for i in range(7)}


def _compute_recent_trend_factor(
    df: pd.DataFrame,
    target_week_start: date,
    date_col: str = "admission_date",
    lookback_months: int = 12,
) -> float:
    """
    直近2週 vs 過去12ヶ月 の入院数比（トレンド補正係数）。

    Returns:
        float: 1.0 が平常、>1.0 は増加傾向、<1.0 は減少傾向
    """
    if df is None or len(df) == 0 or date_col not in df.columns:
        return 1.0

    target_ts = pd.Timestamp(target_week_start)
    recent_start = target_ts - pd.Timedelta(days=14)
    baseline_start = target_ts - pd.DateOffset(months=lookback_months)

    recent = df[(df[date_col] >= recent_start) & (df[date_col] < target_ts)]
    baseline = df[(df[date_col] >= baseline_start) & (df[date_col] < target_ts)]

    if len(recent) == 0 or len(baseline) == 0:
        return 1.0

    # 1日平均で比較
    recent_days = max(1, (target_ts - recent_start).days)
    baseline_days = max(1, (target_ts - baseline_start).days)
    recent_per_day = len(recent) / recent_days
    baseline_per_day = len(baseline) / baseline_days

    if baseline_per_day <= 0:
        return 1.0

    factor = recent_per_day / baseline_per_day
    # 極端な値をクランプ（0.5〜1.5）
    return float(max(0.5, min(1.5, factor)))


def forecast_weekly_demand(
    admissions_df: pd.DataFrame,
    target_week_start: date,
    ward: Optional[str] = None,
    lookback_months: int = 12,
) -> dict:
    """
    対象週の需要予測（過去 lookback_months ヶ月の曜日別平均 + 直近2週トレンド補正）。

    Args:
        admissions_df: load_historical_admissions() の出力
        target_week_start: 対象週の開始日（通常は月曜日）
        ward: "5F" | "6F" | None (全体)
        lookback_months: 参照する過去月数（デフォルト12）

    Returns:
        dict:
            target_week_start: date
            dow_means: {0: 月曜1日平均, ..., 6: 日曜1日平均}
            expected_weekly_total: 週間合計予測（トレンド補正後）
            p25, p75: 信頼区間（ポアソン分布近似）
            recent_trend_factor: float
            confidence: "high" | "medium" | "low"
            sample_size: 集計対象レコード数
    """
    empty_result = {
        "target_week_start": target_week_start,
        "dow_means": {i: 0.0 for i in range(7)},
        "expected_weekly_total": 0.0,
        "p25": 0.0,
        "p75": 0.0,
        "recent_trend_factor": 1.0,
        "confidence": "low",
        "sample_size": 0,
    }

    if admissions_df is None or len(admissions_df) == 0:
        return empty_result

    df = admissions_df.copy()

    # 病棟フィルタ
    if ward in ("5F", "6F") and "ward_short" in df.columns:
        df = df[df["ward_short"] == ward]

    if len(df) == 0:
        return empty_result

    # lookback_months で期間フィルタ
    target_ts = pd.Timestamp(target_week_start)
    start_ts = target_ts - pd.DateOffset(months=lookback_months)
    if "admission_date" in df.columns:
        df = df[(df["admission_date"] >= start_ts) & (df["admission_date"] < target_ts)]

    if len(df) == 0:
        return empty_result

    # 曜日別平均
    dow_means = _compute_dow_means(df)

    # トレンド補正
    trend_factor = _compute_recent_trend_factor(
        df, target_week_start, lookback_months=lookback_months
    )

    # 週間合計（トレンド補正）
    base_total = sum(dow_means.values())
    expected_weekly_total = base_total * trend_factor

    # 信頼区間（ポアソン近似）: 標準偏差 ≈ sqrt(λ)
    # λ = 日平均 * 7 → std = sqrt(λ)
    std = np.sqrt(max(0.0, expected_weekly_total))
    p25 = max(0.0, expected_weekly_total - 0.6745 * std)
    p75 = expected_weekly_total + 0.6745 * std

    # 信頼度判定: サンプル数で評価
    sample_size = len(df)
    if sample_size >= 500:
        confidence = "high"
    elif sample_size >= 100:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "target_week_start": target_week_start,
        "dow_means": dow_means,
        "expected_weekly_total": float(expected_weekly_total),
        "p25": float(p25),
        "p75": float(p75),
        "recent_trend_factor": float(trend_factor),
        "confidence": confidence,
        "sample_size": int(sample_size),
    }


# ---------------------------------------------------------------------------
# 既存空床の推定
# ---------------------------------------------------------------------------

def estimate_existing_vacancy(
    target_date: date,  # noqa: ARG001 - 将来の曜日別補正用
    occupancy_rate: float,
    total_beds: int = DEFAULT_TOTAL_BEDS,
) -> float:
    """
    対象日の既存空床数を推定する（稼働率ベース）。

    Args:
        target_date: 対象日（曜日別補正用、現状は未使用）
        occupancy_rate: 稼働率 0-1（0.90 なら 90%）
        total_beds: 病床数

    Returns:
        float: 推定空床数
    """
    if occupancy_rate is None or not np.isfinite(occupancy_rate):
        occupancy_rate = 0.9
    # 1 を超える稼働率は 1 にクランプ
    occupancy_rate = max(0.0, min(1.0, float(occupancy_rate)))
    return float(total_beds * (1 - occupancy_rate))


# ---------------------------------------------------------------------------
# 週タイプ分類
# ---------------------------------------------------------------------------

WeekType = Literal["high", "standard", "low"]


def classify_week_type(
    expected_demand_daily: float,
    existing_vacancy_daily: float,
    margin: float = DEFAULT_MARGIN,
) -> dict:
    """
    需要 vs 供給バランスで週タイプを分類する。

    - "high":     需要 > 既存空床 + margin       → 木曜前倒し有効
    - "standard": 需要 ≈ 既存空床 (±margin)      → 効果は限定的
    - "low":      需要 < 既存空床 - margin       → 前倒しは逆効果

    Args:
        expected_demand_daily: 対象日の期待需要（入院/日）
        existing_vacancy_daily: 対象日の既存空床（床/日）
        margin: 判定マージン（床/日、デフォルト1.0）

    Returns:
        dict:
            type: "high" | "standard" | "low"
            demand_minus_vacancy: float
            recommendation: str（日本語サマリー）
            rationale: str（根拠の日本語説明）
    """
    delta = float(expected_demand_daily) - float(existing_vacancy_daily)

    if delta > margin:
        week_type: WeekType = "high"
        recommendation = "前倒し有効"
        rationale = (
            f"予想需要 {expected_demand_daily:.1f}件/日 > 既存空床 "
            f"{existing_vacancy_daily:.1f}床/日。新規入院が既存空床を超えるため、"
            f"前倒しで空けた床も埋まりやすい。"
        )
    elif delta < -margin:
        week_type = "low"
        recommendation = "前倒し逆効果"
        rationale = (
            f"予想需要 {expected_demand_daily:.1f}件/日 << 既存空床 "
            f"{existing_vacancy_daily:.1f}床/日。既存空床で需要は吸収される。"
            f"前倒しは稼働率悪化のリスクのみ。"
        )
    else:
        week_type = "standard"
        recommendation = "標準運用"
        rationale = (
            f"予想需要 {expected_demand_daily:.1f}件/日 ≈ 既存空床 "
            f"{existing_vacancy_daily:.1f}床/日（±{margin:.1f}）。"
            f"前倒しの効果は限定的。通常運用で可。"
        )

    return {
        "type": week_type,
        "demand_minus_vacancy": float(delta),
        "recommendation": recommendation,
        "rationale": rationale,
    }
