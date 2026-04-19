"""
demand_forecast.py — 需要予測モジュール（Phase 3α: 需要条件付き木曜前倒しロジック）

週末空床コスト What-If を「需要側が無限」前提から切り離し、
過去実績ベースの需要予測と既存空床の比較で「前倒しが有効か/逆効果か」を判定する。

主な責務:
- 過去12ヶ月の入院実績から曜日別需要ベースラインを構築
- 対象週の需要予測（曜日別平均 + 直近2週トレンド補正 + 月係数）
- 既存空床の推定（稼働率ベース）
- 週タイプ分類（high / standard / low）— 前倒しの有効性を決定

## 2026-04-19: 実データ校正の導入
`settings/forecast_params_calibrated.yaml` に保存された実データ学習済パラメータ
（0埋め曜日係数・月係数・病棟別パターン・緊急率）を、forecast_weekly_demand が
自動でブレンドして精度を高める。実データがない環境では従来通り df からの推定のみ。

この関数群はすべて pure function で、UI (Streamlit) に依存しない。
"""

from __future__ import annotations

import os
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

# 校正パラメータ YAML のデフォルトパス（プロジェクトルート相対）
DEFAULT_CALIBRATED_PARAMS_PATH = "settings/forecast_params_calibrated.yaml"

# デフォルトフォールバック値（YAML・実データ両方なしの場合）— sample_actual の素朴平均
_FALLBACK_PARAMS: dict = {
    "overall": {
        "dow_means": {0: 8.2, 1: 7.2, 2: 7.7, 3: 6.0, 4: 5.4, 5: 2.6, 6: 0.3},
        "month_factors": {m: 1.0 for m in range(1, 13)},
        "year_avg_daily": 5.3,
        "emergency_ratio": 0.57,
        "sample_size": 0,
    },
    "by_ward": {
        "5F": {
            "dow_means": {0: 4.3, 1: 3.6, 2: 3.6, 3: 2.7, 4: 2.4, 5: 1.5, 6: 0.1},
            "month_factors": {m: 1.0 for m in range(1, 13)},
            "year_avg_daily": 2.6,
            "emergency_ratio": 0.53,
            "sample_size": 0,
        },
        "6F": {
            "dow_means": {0: 3.9, 1: 3.6, 2: 4.1, 3: 3.3, 4: 2.9, 5: 1.1, 6: 0.2},
            "month_factors": {m: 1.0 for m in range(1, 13)},
            "year_avg_daily": 2.7,
            "emergency_ratio": 0.61,
            "sample_size": 0,
        },
    },
}

# 校正パラメータのキャッシュ（プロセス内メモ）
_CALIBRATED_CACHE: dict[str, dict] = {}


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
# 校正パラメータ（YAML）読み込み
# ---------------------------------------------------------------------------

def _resolve_params_path(path: Optional[str]) -> str:
    """YAML パスを解決（絶対 or プロジェクトルート相対）。"""
    if path is None:
        path = DEFAULT_CALIBRATED_PARAMS_PATH
    if os.path.isabs(path):
        return path
    # このファイル (scripts/demand_forecast.py) からプロジェクトルート 1 階層上
    here = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(here)
    return os.path.join(project_root, path)


def load_calibrated_params(
    path: Optional[str] = None,
    use_cache: bool = True,
) -> dict:
    """
    `settings/forecast_params_calibrated.yaml` から校正パラメータを読み込む。

    Args:
        path: YAML パス（絶対 or プロジェクトルート相対）。None なら既定パス
        use_cache: True ならプロセス内キャッシュを利用

    Returns:
        dict: {"overall": {...}, "by_ward": {"5F": {...}, "6F": {...}}, "metadata": {...}}
        読み込み失敗時は _FALLBACK_PARAMS を返す（キーは必ず揃う）。
    """
    resolved = _resolve_params_path(path)
    if use_cache and resolved in _CALIBRATED_CACHE:
        return _CALIBRATED_CACHE[resolved]

    try:
        import yaml  # 遅延 import（pytest などで YAML 未インストール環境を守る）
        with open(resolved, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except (FileNotFoundError, ImportError, Exception):
        raw = {}

    # キーを dict[int, float] へ正規化（YAML 内では int キーが str になる場合あり）
    result: dict = {}
    result["metadata"] = raw.get("metadata", {})

    def _normalize_scope(scope: dict) -> dict:
        dm = scope.get("dow_means", {})
        mf = scope.get("month_factors", {})
        return {
            "dow_means": {int(k): float(v) for k, v in dm.items()},
            "month_factors": {int(k): float(v) for k, v in mf.items()},
            "year_avg_daily": float(scope.get("year_avg_daily", 0.0)),
            "emergency_ratio": float(scope.get("emergency_ratio", 0.0)),
            "sample_size": int(scope.get("sample_size", 0)),
        }

    if "overall" in raw:
        result["overall"] = _normalize_scope(raw["overall"])
    else:
        result["overall"] = _FALLBACK_PARAMS["overall"].copy()

    by_ward = raw.get("by_ward", {}) or {}
    result["by_ward"] = {}
    for w in ("5F", "6F"):
        if w in by_ward:
            result["by_ward"][w] = _normalize_scope(by_ward[w])
        else:
            result["by_ward"][w] = _FALLBACK_PARAMS["by_ward"][w].copy()

    if use_cache:
        _CALIBRATED_CACHE[resolved] = result
    return result


def clear_calibrated_cache() -> None:
    """テスト用: キャッシュをクリア。"""
    _CALIBRATED_CACHE.clear()


# ---------------------------------------------------------------------------
# 実データからの校正パラメータ学習
# ---------------------------------------------------------------------------

def learn_calibration_params(
    admissions_df: pd.DataFrame,
    date_col: str = "admission_date",
    ward_col: str = "ward_short",
    route_col: str = "admission_route",
) -> dict:
    """
    実データから校正パラメータを学習する（0埋め曜日係数・月係数・緊急率）。

    日毎に入院数をカウントした後、欠損日（入院 0 件の日）を 0 埋めした上で
    曜日別・月別平均を取る。これにより日曜など極少曜日の過大評価を防ぐ。

    Args:
        admissions_df: 入院実績 DataFrame（`admission_date` 列必須）
        date_col: 日付列名
        ward_col: 病棟列名（存在しなければ overall のみ返す）
        route_col: 入退院ルート列名（`emergency` 値で緊急率を計算）

    Returns:
        dict: `load_calibrated_params()` と同じ構造。学習不能時は _FALLBACK_PARAMS。
    """
    if admissions_df is None or len(admissions_df) == 0 or date_col not in admissions_df.columns:
        import copy
        return copy.deepcopy(_FALLBACK_PARAMS)

    df = admissions_df.copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col])
    if len(df) == 0:
        import copy
        return copy.deepcopy(_FALLBACK_PARAMS)

    # 全日付グリッド作成
    start = df[date_col].min().normalize()
    end = df[date_col].max().normalize()
    grid = pd.DataFrame({"date": pd.date_range(start, end)})
    grid["dow"] = grid["date"].dt.dayofweek
    grid["month"] = grid["date"].dt.month

    def _compute_scope(sub: pd.DataFrame) -> dict:
        if len(sub) == 0:
            return {
                "dow_means": {i: 0.0 for i in range(7)},
                "month_factors": {m: 1.0 for m in range(1, 13)},
                "year_avg_daily": 0.0,
                "emergency_ratio": 0.0,
                "sample_size": 0,
            }
        daily = sub.groupby(sub[date_col].dt.normalize()).size().reset_index(name="count")
        daily.columns = ["date", "count"]
        m = grid.merge(daily, on="date", how="left").fillna({"count": 0})
        dow_means = {int(d): float(m[m["dow"] == d]["count"].mean()) for d in range(7)}
        month_means: dict[int, float] = {}
        for mn in range(1, 13):
            vals = m[m["month"] == mn]["count"]
            if len(vals) > 0:
                month_means[int(mn)] = float(vals.mean())
        if month_means:
            year_avg = float(np.mean(list(month_means.values())))
        else:
            year_avg = 0.0
        if year_avg > 0:
            month_factors = {mn: round(v / year_avg, 4) for mn, v in month_means.items()}
        else:
            month_factors = {mn: 1.0 for mn in range(1, 13)}
        if route_col in sub.columns and len(sub) > 0:
            em = float((sub[route_col] == "emergency").mean())
        else:
            em = 0.0
        return {
            "dow_means": {k: round(v, 4) for k, v in dow_means.items()},
            "month_factors": month_factors,
            "year_avg_daily": round(year_avg, 4),
            "emergency_ratio": round(em, 4),
            "sample_size": int(len(sub)),
        }

    # overall: 5F/6F のみ（4F は数が少なく 6F 系と別運用）
    if ward_col in df.columns:
        overall_df = df[df[ward_col].isin(["5F", "6F"])]
        by_ward = {w: _compute_scope(df[df[ward_col] == w]) for w in ("5F", "6F")}
    else:
        overall_df = df
        by_ward = {
            "5F": _FALLBACK_PARAMS["by_ward"]["5F"].copy(),
            "6F": _FALLBACK_PARAMS["by_ward"]["6F"].copy(),
        }

    return {
        "metadata": {"version": 1, "calibrated_at": str(date.today())},
        "overall": _compute_scope(overall_df),
        "by_ward": by_ward,
    }


def save_calibrated_params(params: dict, path: Optional[str] = None) -> str:
    """
    校正パラメータを YAML に保存する（ラウンドトリップ対応）。

    Args:
        params: learn_calibration_params() の出力 or 同構造 dict
        path: 保存先（None なら既定パス）

    Returns:
        実際に保存された絶対パス
    """
    import yaml
    resolved = _resolve_params_path(path)
    os.makedirs(os.path.dirname(resolved), exist_ok=True)
    # numpy/pandas 型を Python ネイティブへ
    serializable = _to_serializable(params)
    with open(resolved, "w", encoding="utf-8") as f:
        yaml.safe_dump(serializable, f, allow_unicode=True,
                       sort_keys=False, default_flow_style=False)
    # 保存後、キャッシュを同時に更新（直後の読み込みと一貫）
    _CALIBRATED_CACHE[resolved] = load_calibrated_params(resolved, use_cache=False)
    return resolved


def _to_serializable(obj):
    """numpy / pandas 型を Python ネイティブ型に再帰変換（YAML safe_dump 用）。"""
    if isinstance(obj, dict):
        return {k: _to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_serializable(x) for x in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


# ---------------------------------------------------------------------------
# 需要予測
# ---------------------------------------------------------------------------

def _compute_dow_means(
    df: pd.DataFrame,
    date_col: str = "admission_date",
    zero_fill: bool = True,
) -> dict[int, float]:
    """
    曜日別の1日平均入院数を計算する。

    Args:
        df: 入院実績 DataFrame
        date_col: 日付列
        zero_fill: True なら入院 0 件の日も含めて平均を取る（0埋め）。
                   False は既存仕様（入院イベントがある日のみで平均）。
    """
    if df is None or len(df) == 0 or date_col not in df.columns:
        return {i: 0.0 for i in range(7)}

    daily = df.groupby(df[date_col].dt.normalize()).size().reset_index(name="count")
    daily.columns = ["date", "count"]

    if zero_fill and len(daily) > 0:
        start = daily["date"].min()
        end = daily["date"].max()
        grid = pd.DataFrame({"date": pd.date_range(start, end)})
        daily = grid.merge(daily, on="date", how="left").fillna({"count": 0})

    daily["dow"] = pd.to_datetime(daily["date"]).dt.dayofweek
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
    use_calibration: bool = True,
    calibrated_params: Optional[dict] = None,
) -> dict:
    """
    対象週の需要予測（過去 lookback_months ヶ月の曜日別平均 + 直近2週トレンド補正 + 月係数）。

    2026-04-19 以降、`use_calibration=True`（既定）の場合:
    - 曜日別平均は 0 埋めベース（入院 0 件の日も計算に含める）
    - `settings/forecast_params_calibrated.yaml` の月係数を対象週の月に適用
    - 校正パラメータとデータ駆動推定をブレンド（サンプル数で重み付け）

    既存の public API（必須引数）は変わらないため、古い呼び出しも動作する。

    Args:
        admissions_df: load_historical_admissions() の出力
        target_week_start: 対象週の開始日（通常は月曜日）
        ward: "5F" | "6F" | None (全体)
        lookback_months: 参照する過去月数（デフォルト12）
        use_calibration: 校正パラメータを使うか（新規、デフォルト True）
        calibrated_params: 明示的に校正パラメータを渡す（テスト用、None で YAML 読み込み）

    Returns:
        dict:
            target_week_start: date
            dow_means: {0: 月曜1日平均, ..., 6: 日曜1日平均}
            expected_weekly_total: 週間合計予測（トレンド + 月係数補正後）
            p25, p75: 信頼区間（ポアソン分布近似）
            recent_trend_factor: float
            month_factor: float（2026-04-19 追加。校正無効時は 1.0）
            confidence: "high" | "medium" | "low"
            sample_size: 集計対象レコード数
            calibration_used: bool（2026-04-19 追加）
    """
    empty_result = {
        "target_week_start": target_week_start,
        "dow_means": {i: 0.0 for i in range(7)},
        "expected_weekly_total": 0.0,
        "p25": 0.0,
        "p75": 0.0,
        "recent_trend_factor": 1.0,
        "month_factor": 1.0,
        "confidence": "low",
        "sample_size": 0,
        "calibration_used": False,
    }

    # 入力 DataFrame が None / 空 / 日付列欠落 → 従来通り empty を返す（後方互換性）
    # 校正パラメータは「データ少量時の補強」用途であり、入力ゼロ時は使わない
    if (
        admissions_df is None
        or len(admissions_df) == 0
        or "admission_date" not in getattr(admissions_df, "columns", [])
    ):
        return empty_result

    # 校正パラメータの取得
    cal = None
    if use_calibration:
        cal = calibrated_params if calibrated_params is not None else load_calibrated_params()

    df = admissions_df.copy()

    # 病棟フィルタ
    if ward in ("5F", "6F") and "ward_short" in df.columns:
        df = df[df["ward_short"] == ward]

    # lookback_months で期間フィルタ
    target_ts = pd.Timestamp(target_week_start)
    start_ts = target_ts - pd.DateOffset(months=lookback_months)
    if "admission_date" in df.columns and len(df) > 0:
        df = df[(df["admission_date"] >= start_ts) & (df["admission_date"] < target_ts)]

    # フィルタ後にデータが消えた場合も empty
    if len(df) == 0:
        return empty_result

    # データ駆動 dow_means（0埋め: 校正モード ON のとき）
    data_dow_means = _compute_dow_means(df, zero_fill=use_calibration)
    trend_factor = _compute_recent_trend_factor(
        df, target_week_start, lookback_months=lookback_months
    )

    # 校正パラメータ由来の dow_means
    cal_dow_means: dict[int, float] = {}
    cal_month_factor = 1.0
    if cal is not None:
        scope = cal.get("by_ward", {}).get(ward, cal.get("overall", {})) if ward in ("5F", "6F") else cal.get("overall", {})
        cal_dow_means = scope.get("dow_means", {}) or {}
        month_factors = scope.get("month_factors", {}) or {}
        cal_month_factor = float(month_factors.get(target_ts.month, 1.0))

    # ブレンド: データサンプルが少ないほど校正に寄せる
    # 信頼度の閾値と同じ考え方（500 で high）
    sample_size = len(df)
    if use_calibration and cal_dow_means:
        # データ重み w = min(1, sample_size / 500)
        w = min(1.0, sample_size / 500.0) if sample_size > 0 else 0.0
        dow_means = {
            i: w * data_dow_means.get(i, 0.0) + (1 - w) * cal_dow_means.get(i, 0.0)
            for i in range(7)
        }
    else:
        dow_means = data_dow_means

    # 全部 0 かつ 校正も無い場合は empty を返す
    if sum(dow_means.values()) == 0 and not cal_dow_means:
        return empty_result

    # 週間合計（トレンド × 月係数）
    base_total = sum(dow_means.values())
    expected_weekly_total = base_total * trend_factor * cal_month_factor

    # 信頼区間（ポアソン近似）: 標準偏差 ≈ sqrt(λ)
    std = np.sqrt(max(0.0, expected_weekly_total))
    p25 = max(0.0, expected_weekly_total - 0.6745 * std)
    p75 = expected_weekly_total + 0.6745 * std

    # 信頼度判定: サンプル数で評価
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
        "month_factor": float(cal_month_factor),
        "confidence": confidence,
        "sample_size": int(sample_size),
        "calibration_used": bool(use_calibration and cal_dow_means),
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
