"""看護必要度 推定モデル.

データ:
    - 説明変数 X: H ファイル特徴量 (112 列)
    - 目的変数 y: 確定看護必要度 該当患者割合 (rate1)

学習:
    - 12 ヶ月 × 2 病棟 = 24 サンプル
    - Ridge 回帰（L2 正則化）+ 特徴量標準化
    - 高相関特徴量を上位 K 個に絞る（一変数 |r| 順で選択）
    - 必要度Ⅰ・Ⅱを別モデルとして学習

検証:
    - Leave-One-Month-Out CV: 12 月のうち 1 月の両病棟をホールドアウト → 残り 11 月で学習
    - 評価指標: MAE, RMSE, predicted vs actual scatter

不確実性:
    - パラメトリック・ブートストラップ B=1000
    - 患者単位ではなく月×病棟単位での復元抽出（24 サンプルから）
    - 各 bootstrap 反復で再学習 + 4 月予測 → 1000 件の予測分布
    - 95%CI = 2.5 / 97.5 percentile

過学習対策:
    - 特徴量数 K を LOOCV で決定（K ∈ {3, 5, 8, 12}）
    - alpha (L2 正則化強度) も同じく LOOCV で決定（alpha ∈ {0.1, 1.0, 10.0, 100.0}）
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# 線形代数ユーティリティ（scikit-learn 不要、純粋 numpy で実装）
# ---------------------------------------------------------------------------


def _ridge_fit(X: np.ndarray, y: np.ndarray, alpha: float) -> np.ndarray:
    """Ridge 回帰の閉形式解 (X は標準化済み + 切片列を含むことを前提).

    Returns coefficient vector w such that y_hat = X @ w.
    切片用の最初の列は正則化対象外.
    """
    n, p = X.shape
    reg = alpha * np.eye(p)
    reg[0, 0] = 0.0  # 切片列は正則化しない
    return np.linalg.solve(X.T @ X + reg, X.T @ y)


def _standardize(
    X_train: np.ndarray, X_test: np.ndarray | None = None
) -> tuple[np.ndarray, np.ndarray | None, np.ndarray, np.ndarray]:
    mu = X_train.mean(axis=0)
    sigma = X_train.std(axis=0, ddof=0)
    sigma_safe = np.where(sigma < 1e-9, 1.0, sigma)
    X_train_std = (X_train - mu) / sigma_safe
    X_test_std = None
    if X_test is not None:
        X_test_std = (X_test - mu) / sigma_safe
    return X_train_std, X_test_std, mu, sigma_safe


def _add_intercept(X: np.ndarray) -> np.ndarray:
    return np.hstack([np.ones((X.shape[0], 1)), X])


# ---------------------------------------------------------------------------
# 特徴量選択
# ---------------------------------------------------------------------------


def select_top_k_features(
    X: pd.DataFrame, y: pd.Series, k: int
) -> list[str]:
    """目的変数との |相関| が高い上位 k 個の特徴量を選ぶ."""
    cors = []
    for col in X.columns:
        s = X[col].astype(float)
        if s.std() < 1e-9:
            continue
        r = s.corr(y)
        if not pd.isna(r):
            cors.append((col, abs(r)))
    cors.sort(key=lambda t: -t[1])
    return [c for c, _ in cors[:k]]


# ---------------------------------------------------------------------------
# モデル学習・予測
# ---------------------------------------------------------------------------


@dataclass
class FittedModel:
    feature_cols: list[str]
    intercept: float
    coefs: np.ndarray
    feature_means: np.ndarray
    feature_stds: np.ndarray
    alpha: float
    target: str  # "I" or "II"


def fit_ridge(
    X_df: pd.DataFrame,
    y: pd.Series,
    feature_cols: list[str],
    alpha: float,
    target: str,
) -> FittedModel:
    X = X_df[feature_cols].astype(float).to_numpy()
    y_arr = y.astype(float).to_numpy()
    X_std, _, mu, sigma = _standardize(X)
    X_aug = _add_intercept(X_std)
    w = _ridge_fit(X_aug, y_arr, alpha)
    return FittedModel(
        feature_cols=feature_cols,
        intercept=float(w[0]),
        coefs=w[1:],
        feature_means=mu,
        feature_stds=sigma,
        alpha=alpha,
        target=target,
    )


def predict(model: FittedModel, X_df: pd.DataFrame) -> np.ndarray:
    X = X_df[model.feature_cols].astype(float).to_numpy()
    X_std = (X - model.feature_means) / model.feature_stds
    return model.intercept + X_std @ model.coefs


# ---------------------------------------------------------------------------
# Leave-One-Month-Out CV
# ---------------------------------------------------------------------------


@dataclass
class CVResult:
    target: str
    feature_count: int
    alpha: float
    mae: float
    rmse: float
    predictions: pd.DataFrame  # year_month, ward, predicted, actual
    feature_cols: list[str]


def leave_one_month_out_cv(
    df: pd.DataFrame,
    target_col: str,
    feature_cols: list[str],
    alpha: float,
    target_name: str,
) -> CVResult:
    train_df = df.dropna(subset=[target_col]).reset_index(drop=True)
    months = sorted(train_df["year_month"].unique())
    rows = []
    for hold_ym in months:
        tr = train_df[train_df["year_month"] != hold_ym].reset_index(drop=True)
        te = train_df[train_df["year_month"] == hold_ym].reset_index(drop=True)
        if te.empty:
            continue
        # tr/te ごとに特徴量再選択は過学習を緩和するが、サンプル少のため共通に固定
        model = fit_ridge(tr, tr[target_col], feature_cols, alpha, target_name)
        pred = predict(model, te)
        for i in range(len(te)):
            rows.append(
                {
                    "year_month": te.loc[i, "year_month"],
                    "ward": te.loc[i, "ward"],
                    "predicted": float(pred[i]),
                    "actual": float(te.loc[i, target_col]),
                }
            )
    pred_df = pd.DataFrame(rows)
    err = pred_df["predicted"] - pred_df["actual"]
    return CVResult(
        target=target_name,
        feature_count=len(feature_cols),
        alpha=alpha,
        mae=float(np.abs(err).mean()),
        rmse=float(np.sqrt((err**2).mean())),
        predictions=pred_df,
        feature_cols=feature_cols,
    )


def grid_search_hyperparams(
    df: pd.DataFrame,
    target_col: str,
    target_name: str,
    k_grid: tuple[int, ...] = (3, 5, 8, 12),
    alpha_grid: tuple[float, ...] = (0.1, 1.0, 10.0, 100.0),
) -> CVResult:
    """ハイパーパラメータ探索 (LOOCV MAE 最小化)."""
    train_df = df.dropna(subset=[target_col]).reset_index(drop=True)
    feat_pool = [
        c
        for c in train_df.columns
        if c
        not in (
            "year_month",
            "ward",
            "I_actual_rate",
            "II_actual_rate",
        )
    ]
    best: CVResult | None = None
    for k in k_grid:
        feats = select_top_k_features(train_df[feat_pool], train_df[target_col], k)
        for alpha in alpha_grid:
            res = leave_one_month_out_cv(
                train_df, target_col, feats, alpha, target_name
            )
            if best is None or res.mae < best.mae:
                best = res
    assert best is not None
    return best


# ---------------------------------------------------------------------------
# Bootstrap 95% CI
# ---------------------------------------------------------------------------


@dataclass
class PredictionWithCI:
    point_estimate: float
    lower_95: float
    upper_95: float
    bootstrap_samples: np.ndarray = field(repr=False)


def bootstrap_predict_ci(
    df: pd.DataFrame,
    target_col: str,
    feature_cols: list[str],
    alpha: float,
    target_name: str,
    new_data: pd.DataFrame,
    n_boot: int = 1000,
    rng_seed: int = 20260430,
) -> dict[tuple[str, str], PredictionWithCI]:
    """月×病棟単位の復元抽出 + Ridge 再学習 + 4 月予測.

    Returns
    -------
    Dict mapping (year_month, ward) -> PredictionWithCI
    """
    train_df = df.dropna(subset=[target_col]).reset_index(drop=True)
    rng = np.random.default_rng(rng_seed)
    n = len(train_df)

    # 全 bootstrap 反復で予測値を蓄積
    pred_matrix: list[np.ndarray] = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boot = train_df.iloc[idx].reset_index(drop=True)
        # bootstrap で y がすべて同じになる退化を避ける
        if boot[target_col].std() < 1e-9:
            continue
        model = fit_ridge(boot, boot[target_col], feature_cols, alpha, target_name)
        preds = predict(model, new_data)
        pred_matrix.append(preds)

    pred_arr = np.stack(pred_matrix, axis=0)  # shape: (n_boot, n_new)
    point = pred_arr.mean(axis=0)
    lower = np.percentile(pred_arr, 2.5, axis=0)
    upper = np.percentile(pred_arr, 97.5, axis=0)

    # 中央モデル（フルデータ）の点推定を「最良点推定」にする（より bias の少ない値）
    central_model = fit_ridge(
        train_df, train_df[target_col], feature_cols, alpha, target_name
    )
    central_pred = predict(central_model, new_data)

    out: dict[tuple[str, str], PredictionWithCI] = {}
    for i in range(len(new_data)):
        key = (str(new_data.iloc[i]["year_month"]), str(new_data.iloc[i]["ward"]))
        out[key] = PredictionWithCI(
            point_estimate=float(np.clip(central_pred[i], 0.0, 1.0)),
            lower_95=float(np.clip(lower[i], 0.0, 1.0)),
            upper_95=float(np.clip(upper[i], 0.0, 1.0)),
            bootstrap_samples=pred_arr[:, i].copy(),
        )
    return out
