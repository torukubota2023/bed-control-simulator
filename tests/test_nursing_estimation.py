"""scripts/nursing_estimation の基礎テスト.

ユニットテストの粒度:
    - h_file_loader の判定ロジック（is_eligible）
    - feature_builder の集約が空入力でクラッシュしない
    - estimator の Ridge 解が NumPy linalg と整合する
    - bootstrap CI が point_estimate を CI 内に含む

統合テストはスローなので、smoke 範囲に留める（フル run は手動実行）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.nursing_estimation.estimator import (
    bootstrap_predict_ci,
    fit_ridge,
    predict,
    select_top_k_features,
)
from scripts.nursing_estimation.feature_builder import _aggregate_evaluator_block
from scripts.nursing_estimation.h_file_loader import is_eligible


# ---------------------------------------------------------------------------
# h_file_loader.is_eligible
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "a, b, c, expected",
    [
        (0, 0, 0, False),
        (1, 0, 0, False),
        (2, 0, 0, True),
        (0, 0, 1, True),
        (1, 3, 0, True),
        (1, 2, 0, False),
        (5, 0, 0, True),
        (0, 5, 0, False),  # B 単独では該当しない
    ],
)
def test_is_eligible(a: int, b: int, c: int, expected: bool) -> None:
    assert is_eligible(a, b, c) is expected


# ---------------------------------------------------------------------------
# feature_builder._aggregate_evaluator_block
# ---------------------------------------------------------------------------


def test_aggregate_empty_block() -> None:
    out = _aggregate_evaluator_block(pd.DataFrame(), "test")
    assert out["test_n_records"] == 0
    # 11 項目 × 3 統計量 + n_records = 34 キー
    assert len(out) == 34
    for v in out.values():
        assert v == 0 or v == 0.0


def test_aggregate_with_values() -> None:
    df = pd.DataFrame({"項目10": ["1", "2", "0", "1"], "項目11": ["0", "0", "0", "1"]})
    out = _aggregate_evaluator_block(df, "x")
    assert out["x_n_records"] == 4
    assert out["x_項目10_pos_ratio"] == pytest.approx(3 / 4)
    assert out["x_項目10_high_ratio"] == pytest.approx(1 / 4)  # >=2 だけ
    assert out["x_項目10_mean"] == pytest.approx(1.0)
    assert out["x_項目11_pos_ratio"] == pytest.approx(1 / 4)


# ---------------------------------------------------------------------------
# estimator.fit_ridge
# ---------------------------------------------------------------------------


def test_ridge_recovers_simple_linear_relationship() -> None:
    rng = np.random.default_rng(42)
    X = rng.normal(size=(50, 2))
    y = 3 * X[:, 0] - 2 * X[:, 1] + 0.1
    df = pd.DataFrame({"x1": X[:, 0], "x2": X[:, 1]})
    target = pd.Series(y)
    model = fit_ridge(df, target, ["x1", "x2"], alpha=0.01, target="test")
    pred = predict(model, df)
    assert np.abs(pred - y).max() < 0.05


def test_select_top_k_features() -> None:
    rng = np.random.default_rng(0)
    n = 30
    X = pd.DataFrame(
        {
            "strong": rng.normal(size=n),
            "noise": rng.normal(size=n),
            "weak": rng.normal(size=n),
        }
    )
    y = 5 * X["strong"] + 0.5 * X["weak"] + rng.normal(scale=0.1, size=n)
    feats = select_top_k_features(X, y, k=2)
    assert "strong" in feats
    assert len(feats) == 2


# ---------------------------------------------------------------------------
# estimator.bootstrap_predict_ci
# ---------------------------------------------------------------------------


def test_bootstrap_ci_contains_point() -> None:
    rng = np.random.default_rng(1)
    n = 24
    X = rng.normal(size=(n, 3))
    y = 0.5 * X[:, 0] + 0.05 + rng.normal(scale=0.02, size=n)
    df = pd.DataFrame(
        {
            "year_month": [f"2025{m:02d}" for m in range(4, 4 + n // 2)] * 2,
            "ward": ["5F"] * (n // 2) + ["6F"] * (n // 2),
            "x1": X[:, 0],
            "x2": X[:, 1],
            "x3": X[:, 2],
            "rate": y,
        }
    )
    new_data = df.iloc[:2].copy()
    new_data["year_month"] = "202604"
    ci = bootstrap_predict_ci(
        df,
        "rate",
        ["x1", "x2", "x3"],
        alpha=1.0,
        target_name="test",
        new_data=new_data,
        n_boot=200,
        rng_seed=7,
    )
    for _, val in ci.items():
        assert val.lower_95 <= val.point_estimate <= val.upper_95
        assert 0.0 <= val.lower_95
        assert val.upper_95 <= 1.0  # clip [0,1]


# ---------------------------------------------------------------------------
# 完全パイプラインの薄い smoke（実データに依存しない）
# ---------------------------------------------------------------------------


def test_predict_has_finite_output() -> None:
    df = pd.DataFrame(
        {
            "x1": np.linspace(-1, 1, 12),
            "x2": np.linspace(0, 2, 12),
            "y": np.linspace(0.1, 0.3, 12),
        }
    )
    model = fit_ridge(df, df["y"], ["x1", "x2"], alpha=1.0, target="test")
    pred = predict(model, df)
    assert np.all(np.isfinite(pred))
