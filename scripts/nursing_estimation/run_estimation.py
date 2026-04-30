"""2026-04 看護必要度推定の本番実行スクリプト.

実行手順:
    python3 -m scripts.nursing_estimation.run_estimation \
        --src ~/Desktop/Ｈn_En_Fn/csv_no_insurance_number/monthly_merged/ \
        --gt data/nursing_necessity_2025fy.csv \
        --out data/nursing_estimation/

成果物:
    - feature_matrix.csv: 月×病棟 特徴量行列
    - cv_predictions_I.csv / cv_predictions_II.csv: LOOCV 予測値
    - estimate_2026apr.csv: 2026-04 の点推定 + 95%CI
    - cv_summary.json: ハイパーパラメータ + LOOCV メトリクス
    - figures/*.png: 可視化 4 枚
"""

from __future__ import annotations

import argparse
import json
import warnings
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from scripts.nursing_estimation.estimator import (
    CVResult,
    bootstrap_predict_ci,
    fit_ridge,
    grid_search_hyperparams,
    leave_one_month_out_cv,
    predict,
    select_top_k_features,
)
from scripts.nursing_estimation.feature_builder import (
    attach_ground_truth,
    build_full_dataset,
)


TARGET_I_NEW = 0.19  # 2026-06-01 以降の地域包括医療病棟入院料1 必要度Ⅰ閾値
TARGET_II_NEW = 0.18

# 当院 2025FY 救急患者応需係数
EMERGENCY_RESPONSE_COEFFICIENT_PCT = 1.48 / 100.0


def run(
    src_dir: Path,
    gt_csv: Path,
    out_dir: Path,
    n_boot: int = 1000,
    target_month: str = "202604",
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir = out_dir / "figures"
    fig_dir.mkdir(exist_ok=True)

    print(f"[1/6] Building features from {src_dir} ...")
    df = build_full_dataset(src_dir)
    df = attach_ground_truth(df, gt_csv)
    df.to_csv(out_dir / "feature_matrix.csv", index=False)
    print(f"      shape: {df.shape}")

    print("[2/6] Hyperparameter search via LOOCV (necessity I) ...")
    best_I = grid_search_hyperparams(df, "I_actual_rate", "I")
    print(
        f"      best: K={best_I.feature_count}, alpha={best_I.alpha}, "
        f"MAE={best_I.mae:.4f}, RMSE={best_I.rmse:.4f}"
    )
    best_I.predictions.to_csv(out_dir / "cv_predictions_I.csv", index=False)

    print("[3/6] Hyperparameter search via LOOCV (necessity II) ...")
    best_II = grid_search_hyperparams(df, "II_actual_rate", "II")
    print(
        f"      best: K={best_II.feature_count}, alpha={best_II.alpha}, "
        f"MAE={best_II.mae:.4f}, RMSE={best_II.rmse:.4f}"
    )
    best_II.predictions.to_csv(out_dir / "cv_predictions_II.csv", index=False)

    print(f"[4/6] Bootstrap 95% CI for {target_month} predictions (B={n_boot}) ...")
    target_df = df[df["year_month"] == target_month].reset_index(drop=True)
    if target_df.empty:
        raise RuntimeError(f"No feature rows found for year_month={target_month}")

    ci_I = bootstrap_predict_ci(
        df,
        "I_actual_rate",
        best_I.feature_cols,
        best_I.alpha,
        "I",
        target_df,
        n_boot=n_boot,
    )
    ci_II = bootstrap_predict_ci(
        df,
        "II_actual_rate",
        best_II.feature_cols,
        best_II.alpha,
        "II",
        target_df,
        n_boot=n_boot,
    )

    rows = []
    for ward in ("5F", "6F"):
        for kind, ci_dict, target in (
            ("I", ci_I, TARGET_I_NEW),
            ("II", ci_II, TARGET_II_NEW),
        ):
            ci = ci_dict[(target_month, ward)]
            index_value = ci.point_estimate + EMERGENCY_RESPONSE_COEFFICIENT_PCT
            rows.append(
                {
                    "year_month": target_month,
                    "ward": ward,
                    "kind": kind,
                    "rate1_estimate": ci.point_estimate,
                    "rate1_lower_95": ci.lower_95,
                    "rate1_upper_95": ci.upper_95,
                    "emergency_coeff": EMERGENCY_RESPONSE_COEFFICIENT_PCT,
                    "index_with_coeff": index_value,
                    "index_lower_95_with_coeff": ci.lower_95 + EMERGENCY_RESPONSE_COEFFICIENT_PCT,
                    "index_upper_95_with_coeff": ci.upper_95 + EMERGENCY_RESPONSE_COEFFICIENT_PCT,
                    "target_threshold": target,
                    "passes_at_point": (index_value >= target),
                    "passes_at_upper_ci": (
                        ci.upper_95 + EMERGENCY_RESPONSE_COEFFICIENT_PCT >= target
                    ),
                    "passes_at_lower_ci": (
                        ci.lower_95 + EMERGENCY_RESPONSE_COEFFICIENT_PCT >= target
                    ),
                }
            )
    estimate_df = pd.DataFrame(rows)
    estimate_df.to_csv(out_dir / "estimate_2026apr.csv", index=False)
    print(
        "      4-cell estimate (rate1 only, before adding emergency coefficient):\n"
        + estimate_df[
            [
                "ward",
                "kind",
                "rate1_estimate",
                "rate1_lower_95",
                "rate1_upper_95",
                "index_with_coeff",
                "passes_at_point",
            ]
        ].to_string()
    )

    print("[5/6] Saving CV summary ...")
    summary = {
        "necessity_I": {
            "best_alpha": best_I.alpha,
            "best_K": best_I.feature_count,
            "selected_features": best_I.feature_cols,
            "loocv_mae": best_I.mae,
            "loocv_rmse": best_I.rmse,
        },
        "necessity_II": {
            "best_alpha": best_II.alpha,
            "best_K": best_II.feature_count,
            "selected_features": best_II.feature_cols,
            "loocv_mae": best_II.mae,
            "loocv_rmse": best_II.rmse,
        },
        "bootstrap_n": n_boot,
        "target_month": target_month,
        "emergency_response_coefficient_pct": EMERGENCY_RESPONSE_COEFFICIENT_PCT,
    }
    with (out_dir / "cv_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("[6/6] Generating visualizations ...")
    _generate_figures(
        df=df,
        best_I=best_I,
        best_II=best_II,
        ci_I=ci_I,
        ci_II=ci_II,
        target_month=target_month,
        fig_dir=fig_dir,
    )

    print("\n✅ All done.")
    print(f"   Outputs: {out_dir}")


def _generate_figures(
    df: pd.DataFrame,
    best_I: CVResult,
    best_II: CVResult,
    ci_I: dict,
    ci_II: dict,
    target_month: str,
    fig_dir: Path,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.family"] = ["Hiragino Sans", "Yu Gothic", "Meiryo", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    # ---- 図① 推定値バーチャート + 95% CI + 新基準線 ----
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), constrained_layout=True)

    for ax, (ci_dict, kind, target) in zip(
        axes,
        [
            (ci_I, "Ⅰ", TARGET_I_NEW),
            (ci_II, "Ⅱ", TARGET_II_NEW),
        ],
    ):
        wards = ["5F", "6F"]
        points = []
        lowers = []
        uppers = []
        idx_points = []
        idx_lowers = []
        idx_uppers = []
        for w in wards:
            ci = ci_dict[(target_month, w)]
            points.append(ci.point_estimate)
            lowers.append(ci.point_estimate - ci.lower_95)
            uppers.append(ci.upper_95 - ci.point_estimate)
            idx_points.append(ci.point_estimate + EMERGENCY_RESPONSE_COEFFICIENT_PCT)
            idx_lowers.append(idx_points[-1] - (ci.lower_95 + EMERGENCY_RESPONSE_COEFFICIENT_PCT))
            idx_uppers.append((ci.upper_95 + EMERGENCY_RESPONSE_COEFFICIENT_PCT) - idx_points[-1])

        x = np.arange(len(wards))
        width = 0.35
        bars1 = ax.bar(
            x - width / 2,
            np.array(points) * 100,
            width,
            yerr=[np.array(lowers) * 100, np.array(uppers) * 100],
            capsize=5,
            color="#5B8DBF",
            edgecolor="#1F4E79",
            label="該当患者割合（推定値）",
        )
        bars2 = ax.bar(
            x + width / 2,
            np.array(idx_points) * 100,
            width,
            yerr=[np.array(idx_lowers) * 100, np.array(idx_uppers) * 100],
            capsize=5,
            color="#E8A87C",
            edgecolor="#A85831",
            label="割合指数（+ 救急係数 1.48pt）",
        )
        ax.axhline(target * 100, color="#C73E1D", linestyle="--", linewidth=1.5,
                   label=f"2026-06 新基準 {int(target*100)}%")
        for i, (p, ip) in enumerate(zip(points, idx_points)):
            ax.text(i - width / 2, p * 100 + 0.5, f"{p*100:.1f}%", ha="center", fontsize=9)
            ax.text(i + width / 2, ip * 100 + 0.5, f"{ip*100:.1f}%", ha="center", fontsize=9)
        ax.set_xticks(x)
        ax.set_xticklabels(wards)
        ax.set_ylabel("該当患者割合 (%)")
        ax.set_title(f"必要度{kind}（2026-04 推定 + 95% CI）")
        ax.set_ylim(0, max(40, max(idx_points) * 100 * 1.4))
        ax.legend(loc="upper right", fontsize=8)
        ax.grid(axis="y", alpha=0.3)

    fig.suptitle("看護必要度 2026-04 推定値（H ファイル特徴量 × Ridge 回帰 + Bootstrap 95% CI）",
                 fontsize=12)
    fig.savefig(fig_dir / "1_estimate_with_ci.png", dpi=120, bbox_inches="tight")
    plt.close(fig)

    # ---- 図② 12 ヶ月実測 + 4 月推定の時系列 ----
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), constrained_layout=True)
    train = df.dropna(subset=["I_actual_rate"]).copy()
    train["year_month"] = train["year_month"].astype(str)
    months_order = sorted(train["year_month"].unique()) + [target_month]
    x_pos = {ym: i for i, ym in enumerate(months_order)}

    for ax, target_col, ci_dict, kind, target in zip(
        axes,
        ["I_actual_rate", "II_actual_rate"],
        [ci_I, ci_II],
        ["Ⅰ", "Ⅱ"],
        [TARGET_I_NEW, TARGET_II_NEW],
    ):
        for w, color in [("5F", "#1F4E79"), ("6F", "#A85831")]:
            sub = train[train["ward"] == w].sort_values("year_month")
            xs = [x_pos[ym] for ym in sub["year_month"]]
            ys = (sub[target_col] * 100).tolist()
            ax.plot(xs, ys, "o-", color=color, label=f"{w} 確定値", linewidth=1.5, markersize=5)
            ci = ci_dict[(target_month, w)]
            xt = x_pos[target_month]
            yt = ci.point_estimate * 100
            yl = ci.lower_95 * 100
            yu = ci.upper_95 * 100
            ax.errorbar(
                xt, yt, yerr=[[yt - yl], [yu - yt]],
                fmt="D", color=color, ecolor=color, capsize=6, markersize=8,
                label=f"{w} 推定値 (95% CI)",
                markerfacecolor="white", markeredgewidth=2,
            )
        ax.axhline(target * 100, color="#C73E1D", linestyle="--", linewidth=1, alpha=0.6,
                   label=f"新基準 {int(target*100)}%")
        ax.set_xticks(list(x_pos.values()))
        ax.set_xticklabels([ym[:4] + "-" + ym[4:] for ym in months_order], rotation=45, fontsize=8)
        ax.set_ylabel(f"必要度{kind} 該当割合 (%)")
        ax.set_title(f"必要度{kind} 時系列（12 ヶ月実測 + 2026-04 推定）")
        ax.set_ylim(0, max(35, ax.get_ylim()[1]))
        ax.legend(loc="lower left", fontsize=8, ncol=2)
        ax.grid(alpha=0.3)

    fig.savefig(fig_dir / "2_timeseries_with_estimate.png", dpi=120, bbox_inches="tight")
    plt.close(fig)

    # ---- 図③ LOOCV 校正プロット ----
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), constrained_layout=True)
    for ax, cv, kind in zip(axes, [best_I, best_II], ["Ⅰ", "Ⅱ"]):
        x = cv.predictions["actual"] * 100
        y = cv.predictions["predicted"] * 100
        for w, color in [("5F", "#1F4E79"), ("6F", "#A85831")]:
            mask = cv.predictions["ward"] == w
            ax.scatter(x[mask], y[mask], color=color, label=w, s=30, alpha=0.7)
        lim = max(x.max(), y.max()) + 3
        ax.plot([0, lim], [0, lim], "k--", linewidth=1, alpha=0.5, label="y = x")
        ax.set_xlabel("確定値 (%)")
        ax.set_ylabel("LOOCV 推定値 (%)")
        ax.set_title(f"必要度{kind} 校正 (MAE={cv.mae*100:.2f}pt, RMSE={cv.rmse*100:.2f}pt)")
        ax.set_xlim(0, lim)
        ax.set_ylim(0, lim)
        ax.legend(fontsize=9)
        ax.grid(alpha=0.3)
    fig.savefig(fig_dir / "3_calibration.png", dpi=120, bbox_inches="tight")
    plt.close(fig)

    # ---- 図④ 特徴量重要度（標準化係数の絶対値） ----
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), constrained_layout=True)
    train_df = df.dropna(subset=["I_actual_rate"]).reset_index(drop=True)
    for ax, cv, target_col, kind in zip(
        axes,
        [best_I, best_II],
        ["I_actual_rate", "II_actual_rate"],
        ["Ⅰ", "Ⅱ"],
    ):
        model = fit_ridge(train_df, train_df[target_col], cv.feature_cols, cv.alpha, cv.target)
        idx = np.argsort(np.abs(model.coefs))[::-1]
        names = [cv.feature_cols[i] for i in idx]
        vals = [model.coefs[i] for i in idx]
        colors = ["#1F4E79" if v > 0 else "#A85831" for v in vals]
        ax.barh(range(len(names)), vals, color=colors)
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names, fontsize=8)
        ax.set_xlabel("標準化回帰係数")
        ax.set_title(f"必要度{kind} 特徴量重要度（{cv.feature_count} 特徴量, α={cv.alpha}）")
        ax.axvline(0, color="k", linewidth=0.5)
        ax.invert_yaxis()
        ax.grid(axis="x", alpha=0.3)
    fig.savefig(fig_dir / "4_feature_importance.png", dpi=120, bbox_inches="tight")
    plt.close(fig)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--src",
        default="/Users/torukubota/Desktop/Ｈn_En_Fn/csv_no_insurance_number/monthly_merged",
    )
    parser.add_argument("--gt", default="data/nursing_necessity_2025fy.csv")
    parser.add_argument("--out", default="data/nursing_estimation")
    parser.add_argument("--target-month", default="202604")
    parser.add_argument("--n-boot", type=int, default=1000)
    args = parser.parse_args(argv)

    run(
        src_dir=Path(args.src),
        gt_csv=Path(args.gt),
        out_dir=Path(args.out),
        n_boot=args.n_boot,
        target_month=args.target_month,
    )


if __name__ == "__main__":
    main()
