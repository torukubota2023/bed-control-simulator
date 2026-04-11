"""
需要波モデル — 入院需要の波を可視化し、閑散/繁忙を判定する

当院（おもろまちメディカルセンター）は昼間帯救急中心のため、
地域の入院需要の閑散期と繁忙期がそのまま病床稼働率に響く。
このモジュールは需要の波を定量化し、C群コントロールの判断材料を提供する。

注: 時間帯別データは現状なし（日次集計のみ）。将来対応予定。
"""

from __future__ import annotations

import pandas as pd
from datetime import date, timedelta
from typing import Optional

# bed_management_metrics の prepare_bed_mgmt_daily_df を利用可能なら import
try:
    from bed_management_metrics import prepare_bed_mgmt_daily_df as _prepare
except ImportError:
    _prepare = None

# ---------------------------------------------------------------------------
# 曜日ラベル
# ---------------------------------------------------------------------------
_DOW_LABELS = ["月", "火", "水", "木", "金", "土", "日"]


# ---------------------------------------------------------------------------
# 共通ヘルパー
# ---------------------------------------------------------------------------

def _filter_ward(df: pd.DataFrame, ward: Optional[str]) -> pd.DataFrame:
    """wardフィルタを統一的に処理する。

    Args:
        df: 日次データ（ward列を持つ想定）
        ward: "5F" / "6F" / None（全病棟合算）

    Returns:
        フィルタ済みDataFrame。ward指定時はそのwardのみ、
        Noneの場合はdate単位で合算した結果を返す。
    """
    if df is None or not isinstance(df, pd.DataFrame) or len(df) == 0:
        return pd.DataFrame()

    work = df.copy()
    work["date"] = pd.to_datetime(work["date"])

    if ward is not None and "ward" in work.columns:
        work = work[work["ward"] == ward]

    # 日付単位で合算（wardが複数ある場合に備える）
    numeric_cols = [c for c in ["total_patients", "new_admissions", "discharges"]
                    if c in work.columns]
    if not numeric_cols:
        return pd.DataFrame()

    agg_dict = {c: "sum" for c in numeric_cols}
    work = work.groupby("date", as_index=False).agg(agg_dict)
    work = work.sort_values("date").reset_index(drop=True)
    return work


def _safe_empty_result() -> pd.DataFrame:
    """空の安全なDataFrameを返す。"""
    return pd.DataFrame()


# ---------------------------------------------------------------------------
# 1. calculate_demand_trend
# ---------------------------------------------------------------------------

def calculate_demand_trend(
    daily_df: pd.DataFrame,
    ward: Optional[str] = None,
) -> dict:
    """前2週間 vs 直近1週間の入院数トレンドを比較する。

    Args:
        daily_df: 日次データ
        ward: "5F" / "6F" / None

    Returns:
        トレンド情報を含む辞書
    """
    df = _filter_ward(daily_df, ward)
    if df.empty or "new_admissions" not in df.columns:
        return {
            "prev_2w_avg_admissions": 0.0,
            "last_1w_avg_admissions": 0.0,
            "trend_ratio": 1.0,
            "trend_label": "stable",
            "trend_description": "データ不足のため判定不可",
            "prev_2w_avg_discharges": 0.0,
            "last_1w_avg_discharges": 0.0,
            "data_days": 0,
        }

    data_days = len(df)
    max_date = df["date"].max()

    # 直近1週間
    last_1w_start = max_date - timedelta(days=6)
    last_1w = df[df["date"] >= last_1w_start]

    # 前2週間（直近1週間を除く、その前の14日間）
    prev_2w_end = last_1w_start - timedelta(days=1)
    prev_2w_start = prev_2w_end - timedelta(days=13)
    prev_2w = df[(df["date"] >= prev_2w_start) & (df["date"] <= prev_2w_end)]

    # 平均計算
    last_1w_avg_adm = (last_1w["new_admissions"].mean()
                       if len(last_1w) > 0 else 0.0)
    prev_2w_avg_adm = (prev_2w["new_admissions"].mean()
                       if len(prev_2w) > 0 else 0.0)

    last_1w_avg_dis = (last_1w["discharges"].mean()
                       if len(last_1w) > 0 and "discharges" in last_1w.columns
                       else 0.0)
    prev_2w_avg_dis = (prev_2w["discharges"].mean()
                       if len(prev_2w) > 0 and "discharges" in prev_2w.columns
                       else 0.0)

    # トレンド比率
    if prev_2w_avg_adm > 0:
        trend_ratio = last_1w_avg_adm / prev_2w_avg_adm
    else:
        trend_ratio = 1.0

    # ラベル判定
    if trend_ratio >= 1.15:
        trend_label = "increasing"
        pct = round(trend_ratio * 100)
        trend_description = f"需要は増加傾向（前2週比{pct}%）"
    elif trend_ratio <= 0.85:
        trend_label = "decreasing"
        pct = round(trend_ratio * 100)
        trend_description = f"需要は減少傾向（前2週比{pct}%）"
    else:
        trend_label = "stable"
        pct = round(trend_ratio * 100)
        trend_description = f"需要は横ばい（前2週比{pct}%）"

    result = {
        "prev_2w_avg_admissions": round(prev_2w_avg_adm, 2),
        "last_1w_avg_admissions": round(last_1w_avg_adm, 2),
        "trend_ratio": round(trend_ratio, 3),
        "trend_label": trend_label,
        "trend_description": trend_description,
        "prev_2w_avg_discharges": round(prev_2w_avg_dis, 2),
        "last_1w_avg_discharges": round(last_1w_avg_dis, 2),
        "data_days": data_days,
    }

    # データが3週間未満の場合
    if data_days < 21:
        result["is_partial"] = True

    return result


# ---------------------------------------------------------------------------
# 2. classify_demand_period
# ---------------------------------------------------------------------------

def classify_demand_period(
    daily_df: pd.DataFrame,
    ward: Optional[str] = None,
) -> dict:
    """直近の需要を過去データと比較して、閑散/通常/繁忙を判定する。

    7日移動合計の分布から直近1週間のパーセンタイルを算出する。

    Args:
        daily_df: 日次データ
        ward: "5F" / "6F" / None

    Returns:
        閑散/繁忙判定を含む辞書
    """
    df = _filter_ward(daily_df, ward)
    if df.empty or "new_admissions" not in df.columns:
        return {
            "classification": "normal",
            "classification_ja": "通常",
            "percentile": 50.0,
            "last_7d_total_admissions": 0,
            "historical_avg_7d_admissions": 0.0,
            "confidence": "low",
        }

    data_days = len(df)

    # 信頼度
    if data_days >= 90:
        confidence = "high"
    elif data_days >= 30:
        confidence = "medium"
    else:
        confidence = "low"

    # 7日移動合計
    df = df.set_index("date").sort_index()
    rolling_7d = df["new_admissions"].rolling(window=7, min_periods=7).sum()
    rolling_7d = rolling_7d.dropna()

    if len(rolling_7d) == 0:
        return {
            "classification": "normal",
            "classification_ja": "通常",
            "percentile": 50.0,
            "last_7d_total_admissions": int(df["new_admissions"].tail(7).sum()),
            "historical_avg_7d_admissions": 0.0,
            "confidence": confidence,
        }

    last_7d_total = rolling_7d.iloc[-1]
    historical_avg = rolling_7d.mean()

    # パーセンタイル計算: 直近値が過去分布の何%に位置するか
    below_count = (rolling_7d < last_7d_total).sum()
    equal_count = (rolling_7d == last_7d_total).sum()
    percentile = (below_count + equal_count * 0.5) / len(rolling_7d) * 100

    # 判定
    if percentile >= 75:
        classification = "busy"
        classification_ja = "繁忙期"
    elif percentile <= 25:
        classification = "quiet"
        classification_ja = "閑散期"
    else:
        classification = "normal"
        classification_ja = "通常"

    return {
        "classification": classification,
        "classification_ja": classification_ja,
        "percentile": round(percentile, 1),
        "last_7d_total_admissions": int(last_7d_total),
        "historical_avg_7d_admissions": round(float(historical_avg), 1),
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# 3. calculate_dow_pattern
# ---------------------------------------------------------------------------

def calculate_dow_pattern(
    daily_df: pd.DataFrame,
    ward: Optional[str] = None,
) -> pd.DataFrame:
    """曜日別の入院数・退院数パターンを返す。

    Args:
        daily_df: 日次データ
        ward: "5F" / "6F" / None

    Returns:
        7行のDataFrame（dow, dow_label, avg_admissions, avg_discharges,
        avg_occupancy_rate, avg_empty, n_samples）
    """
    df = _filter_ward(daily_df, ward)
    if df.empty:
        # 空の場合でも正しい構造のDataFrameを返す
        return pd.DataFrame({
            "dow": range(7),
            "dow_label": _DOW_LABELS,
            "avg_admissions": [0.0] * 7,
            "avg_discharges": [0.0] * 7,
            "avg_occupancy_rate": [0.0] * 7,
            "avg_empty": [0.0] * 7,
            "n_samples": [0] * 7,
        })

    df = df.copy()
    df["dow"] = df["date"].dt.dayofweek  # 0=月曜

    # 曜日別集計
    agg_dict = {"new_admissions": "mean", "date": "count"}
    if "discharges" in df.columns:
        agg_dict["discharges"] = "mean"
    if "total_patients" in df.columns:
        agg_dict["total_patients"] = "mean"

    grouped = df.groupby("dow", as_index=False).agg(agg_dict)
    grouped = grouped.rename(columns={
        "new_admissions": "avg_admissions",
        "date": "n_samples",
    })
    if "discharges" in grouped.columns:
        grouped = grouped.rename(columns={"discharges": "avg_discharges"})
    else:
        grouped["avg_discharges"] = 0.0

    if "total_patients" in grouped.columns:
        grouped = grouped.rename(columns={"total_patients": "avg_occupancy_rate"})
    else:
        grouped["avg_occupancy_rate"] = 0.0

    # 空床数（total_bedsが不明なので、あるならemptyを計算、なければ0）
    grouped["avg_empty"] = 0.0

    # 全7曜日を保証
    full_dow = pd.DataFrame({"dow": range(7)})
    grouped = full_dow.merge(grouped, on="dow", how="left").fillna(0)

    # 曜日ラベル
    grouped["dow_label"] = grouped["dow"].map(lambda x: _DOW_LABELS[x])

    # 列の整形・丸め
    grouped["avg_admissions"] = grouped["avg_admissions"].round(2)
    grouped["avg_discharges"] = grouped["avg_discharges"].round(2)
    grouped["avg_occupancy_rate"] = grouped["avg_occupancy_rate"].round(2)
    grouped["avg_empty"] = grouped["avg_empty"].round(2)
    grouped["n_samples"] = grouped["n_samples"].astype(int)

    return grouped[["dow", "dow_label", "avg_admissions", "avg_discharges",
                     "avg_occupancy_rate", "avg_empty", "n_samples"]]


# ---------------------------------------------------------------------------
# 4. generate_demand_heatmap_data
# ---------------------------------------------------------------------------

def generate_demand_heatmap_data(
    daily_df: pd.DataFrame,
    value_col: str = "new_admissions",
    ward: Optional[str] = None,
) -> Optional[pd.DataFrame]:
    """月 x 曜日 のヒートマップ用ピボットテーブルを生成する。

    データが3ヶ月以上ある場合に有効。3ヶ月未満なら None を返す。

    Args:
        daily_df: 日次データ
        value_col: 値に使うカラム名
        ward: "5F" / "6F" / None

    Returns:
        ピボットテーブル（index=月, columns=曜日ラベル）またはNone
    """
    df = _filter_ward(daily_df, ward)
    if df.empty or value_col not in df.columns:
        return None

    df = df.copy()
    df["month"] = df["date"].dt.month
    df["dow"] = df["date"].dt.dayofweek

    # 3ヶ月以上のデータがあるか
    n_months = df["month"].nunique()
    date_range_days = (df["date"].max() - df["date"].min()).days
    if date_range_days < 90 or n_months < 3:
        return None

    # ピボット
    pivot = df.pivot_table(
        index="month",
        columns="dow",
        values=value_col,
        aggfunc="mean",
    )

    # 列名を曜日ラベルに変換
    pivot.columns = [_DOW_LABELS[c] for c in pivot.columns]
    pivot = pivot.round(2)

    return pivot


# ---------------------------------------------------------------------------
# 5. calculate_demand_score
# ---------------------------------------------------------------------------

def calculate_demand_score(
    daily_df: pd.DataFrame,
    ward: Optional[str] = None,
) -> dict:
    """直近14日と30日の需要スコアを算出する。

    スコアはパーセンタイルベース（0-100、50が平均）。

    Args:
        daily_df: 日次データ
        ward: "5F" / "6F" / None

    Returns:
        スコアと日本語ラベルを含む辞書
    """
    df = _filter_ward(daily_df, ward)
    if df.empty or "new_admissions" not in df.columns:
        return {
            "score_14d": 50.0,
            "score_30d": 50.0,
            "label_14d": "標準",
            "label_30d": "標準",
        }

    df = df.set_index("date").sort_index()

    def _calc_score(window: int) -> float:
        """指定期間の移動合計からパーセンタイルスコアを計算する。"""
        rolling = df["new_admissions"].rolling(
            window=window, min_periods=window
        ).sum().dropna()
        if len(rolling) == 0:
            return 50.0

        current = rolling.iloc[-1]
        below = (rolling < current).sum()
        equal = (rolling == current).sum()
        pct = (below + equal * 0.5) / len(rolling) * 100
        return round(pct, 1)

    score_14d = _calc_score(14)
    score_30d = _calc_score(30)

    def _score_to_label(score: float) -> str:
        """スコアを日本語ラベルに変換する。"""
        if score >= 80:
            return "高い"
        elif score >= 60:
            return "やや高い"
        elif score >= 40:
            return "標準"
        elif score >= 20:
            return "やや低い"
        else:
            return "低い"

    return {
        "score_14d": score_14d,
        "score_30d": score_30d,
        "label_14d": _score_to_label(score_14d),
        "label_30d": _score_to_label(score_30d),
    }


# ---------------------------------------------------------------------------
# 6. detect_demand_alerts
# ---------------------------------------------------------------------------

def detect_demand_alerts(
    daily_df: pd.DataFrame,
    ward: Optional[str] = None,
) -> list[dict]:
    """需要波に基づくアラートを生成する。

    Args:
        daily_df: 日次データ
        ward: "5F" / "6F" / None

    Returns:
        アラート辞書のリスト
    """
    alerts: list[dict] = []

    # トレンド分析
    trend = calculate_demand_trend(daily_df, ward)

    if trend["data_days"] == 0:
        return alerts

    if trend["trend_label"] == "decreasing":
        pct = round(trend["trend_ratio"] * 100)
        alerts.append({
            "level": "warning",
            "message": (
                f"直近1週間の入院数が前2週間比で{100 - pct}%減少しています。"
                "入院需要が減少傾向です。C群の退院調整に余裕を持たせられます"
            ),
            "metric": "trend",
        })
    elif trend["trend_label"] == "increasing":
        pct = round(trend["trend_ratio"] * 100)
        alerts.append({
            "level": "info",
            "message": (
                f"直近1週間の入院数が前2週間比で{pct - 100}%増加しています。"
                "入院需要が増加傾向です。C群の前倒し退院を検討してください"
            ),
            "metric": "trend",
        })

    # 金曜退院集中チェック
    dow_pattern = calculate_dow_pattern(daily_df, ward)
    if dow_pattern is not None and len(dow_pattern) == 7:
        fri_dis = dow_pattern.loc[dow_pattern["dow"] == 4, "avg_discharges"]
        if len(fri_dis) > 0:
            fri_val = fri_dis.values[0]
            # 金曜以外の平均
            other_dis = dow_pattern.loc[
                dow_pattern["dow"] != 4, "avg_discharges"
            ]["avg_discharges"] if False else dow_pattern.loc[
                dow_pattern["dow"] != 4, "avg_discharges"
            ]
            other_avg = other_dis.mean()
            if other_avg > 0 and fri_val >= other_avg * 1.5:
                alerts.append({
                    "level": "info",
                    "message": (
                        f"金曜退院集中の傾向があります"
                        f"（金曜 {fri_val:.1f}件 vs 他曜日平均 {other_avg:.1f}件）"
                    ),
                    "metric": "weekend",
                })

    return alerts
