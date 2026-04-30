"""副院長提示スタイルに合わせた発表用ビジュアライゼーション.

入力:
    - data/nursing_estimation/feature_matrix.csv  （13 ヶ月特徴量 + 確定値）
    - data/nursing_estimation/estimate_2026apr.csv （4 月推定値 + 95%CI）
    - data/nursing_estimation/cv_summary.json （ハイパーパラメータ）

出力:
    - data/nursing_estimation/figures/5_monthly_trend_with_estimate.png
    - data/nursing_estimation/figures/6_horizontal_ci_summary.png

実行:
    python3 -m scripts.nursing_estimation.visualize_publication
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyBboxPatch

matplotlib.use("Agg")
plt.rcParams["font.family"] = ["Hiragino Sans", "Hiragino Maru Gothic Pro", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


# ---------------------------------------------------------------------------
# 制度ルール定数
# ---------------------------------------------------------------------------
TARGET_NEW = {"I": 19.0, "II": 18.0}  # 2026-06-01 以降
TARGET_OLD = {"I": 16.0, "II": 14.0}  # 令和 6 年度
EMERGENCY_COEFF_PCT = 1.48

WARD_COLORS = {"5F": "#1F77B4", "6F": "#D62728"}  # 青 / 赤


# ---------------------------------------------------------------------------
# Figure 5: 4 panel 月次推移 + 推定★
# ---------------------------------------------------------------------------


def _plot_monthly_panel(
    ax: plt.Axes,
    actual_df: pd.DataFrame,
    estimate_row: pd.Series,
    ward: str,
    kind: str,
) -> None:
    """1 panel: 12 ヶ月実測 + 4 月推定★ + 新旧基準ライン + 達成判定バッジ."""
    actual = actual_df[actual_df["ward"] == ward].sort_values("year_month").copy()
    target_col = f"{kind}_actual_rate"
    actual = actual.dropna(subset=[target_col]).copy()
    actual["pct"] = actual[target_col] * 100.0

    months_order = list(actual["year_month"]) + ["202604"]
    x_pos = list(range(len(months_order)))

    # 実測線
    ax.plot(
        x_pos[:-1],
        actual["pct"].tolist(),
        marker="o",
        linewidth=2.0,
        markersize=7,
        color=WARD_COLORS[ward],
        label=f"{ward} 実測",
        zorder=3,
    )

    # 4 月推定 ★
    estimate_pct = float(estimate_row["rate1_estimate"]) * 100.0
    ax.plot(
        [x_pos[-2], x_pos[-1]],
        [actual["pct"].iloc[-1], estimate_pct],
        linestyle="--",
        color="#888",
        linewidth=1.0,
        alpha=0.7,
        zorder=2,
    )
    ax.scatter(
        [x_pos[-1]],
        [estimate_pct],
        marker="*",
        s=420,
        color="black",
        edgecolor="white",
        linewidth=1.5,
        zorder=5,
        label=f"4 月推定 = {estimate_pct:.1f}%",
    )

    # 新基準ライン
    target_new = TARGET_NEW[kind]
    ax.axhline(
        target_new,
        color="#D62728",
        linestyle="--",
        linewidth=1.5,
        alpha=0.85,
        label=f"新基準 {int(target_new)}%",
        zorder=1,
    )
    # 旧基準ライン
    target_old = TARGET_OLD[kind]
    ax.axhline(
        target_old,
        color="#888",
        linestyle=":",
        linewidth=1.0,
        alpha=0.6,
        label=f"旧基準 {int(target_old)}%",
        zorder=1,
    )

    # X 軸ラベル
    labels = [f"{ym[:4]}-{ym[4:]}" for ym in months_order]
    ax.set_xticks(x_pos)
    ax.set_xticklabels(labels, rotation=45, fontsize=8, ha="right")

    # Y 軸範囲
    ymin = max(0.0, min(actual["pct"].min(), estimate_pct, target_old) - 1.5)
    ymax = max(actual["pct"].max(), estimate_pct, target_new) + 2.5
    ax.set_ylim(ymin, ymax)
    ax.set_ylabel("該当患者割合 (%)", fontsize=10)
    ax.set_title(f"{ward} 病棟 — 必要度{kind}", fontsize=12, fontweight="bold")
    ax.grid(alpha=0.25, zorder=0)
    ax.legend(loc="lower left", fontsize=8, framealpha=0.9)

    # 達成判定バッジ（右下）
    gap_pt = estimate_pct - target_new
    if gap_pt >= 0:
        badge_text = f"達成 (+{gap_pt:.1f}pt)"
        badge_color = "#2CA02C"
    else:
        badge_text = f"未達 ({gap_pt:.1f}pt)"
        badge_color = "#D62728"
    ax.text(
        0.985,
        0.04,
        badge_text,
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=10,
        fontweight="bold",
        color=badge_color,
        bbox=dict(
            boxstyle="round,pad=0.4",
            facecolor="white",
            edgecolor=badge_color,
            linewidth=1.5,
        ),
    )


def make_figure_monthly_trend(
    feature_csv: Path,
    estimate_csv: Path,
    summary_json: Path,
    output_path: Path,
) -> None:
    actual_df = pd.read_csv(feature_csv)
    actual_df["year_month"] = actual_df["year_month"].astype(str)

    est_df = pd.read_csv(estimate_csv)
    est_df["year_month"] = est_df["year_month"].astype(str)

    with summary_json.open("r", encoding="utf-8") as f:
        summary = json.load(f)
    mae_I = summary["necessity_I"]["loocv_mae"] * 100
    mae_II = summary["necessity_II"]["loocv_mae"] * 100
    k_I = summary["necessity_I"]["best_K"]
    k_II = summary["necessity_II"]["best_K"]

    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=False)

    panels = [
        ("5F", "I", axes[0, 0]),
        ("5F", "II", axes[0, 1]),
        ("6F", "I", axes[1, 0]),
        ("6F", "II", axes[1, 1]),
    ]

    for ward, kind, ax in panels:
        est_row = est_df[(est_df["ward"] == ward) & (est_df["kind"] == kind)].iloc[0]
        _plot_monthly_panel(ax, actual_df, est_row, ward, kind)

    fig.suptitle(
        "看護必要度 月次推移（実測 12 ヶ月）+ 2026-04 推定値\n"
        "推定方法: H ファイル基礎データの月次特徴量 → Ridge 回帰（L2 正則化）で確定値との関係を学習 → 4 月予測",
        fontsize=12,
        fontweight="bold",
    )
    fig.tight_layout(rect=[0, 0.06, 1, 0.94])

    # フッター注釈
    footer = (
        f"📊 4 月推定の根拠: 必要度Ⅰ = {k_I} 特徴量, LOOCV MAE = {mae_I:.2f}pt  ／  "
        f"必要度Ⅱ = {k_II} 特徴量, LOOCV MAE = {mae_II:.2f}pt    "
        "｜  ⚠️ 推定値（実測ではない）。施設基準判定には使用不可。6/1 までの方向性把握用。"
    )
    fig.text(
        0.5,
        0.015,
        footer,
        ha="center",
        va="bottom",
        fontsize=9,
        color="#444",
        bbox=dict(
            boxstyle="round,pad=0.5",
            facecolor="#FFF8E1",
            edgecolor="#E0C97F",
            linewidth=1,
        ),
    )

    fig.savefig(output_path, dpi=130, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 6: 横バー + 95%CI + 新旧基準ライン + 解説パネル
# ---------------------------------------------------------------------------


def _classify_status(point: float, lower: float, upper: float, target: float) -> tuple[str, str]:
    """点推定と CI から達成判定を分類."""
    if lower >= target:
        return "達成（確実）", "#2CA02C"
    if upper < target:
        return "未達（確実）", "#D62728"
    return "ボーダーまたぐ", "#FF9800"


def make_figure_horizontal_ci(
    estimate_csv: Path,
    summary_json: Path,
    output_path: Path,
) -> None:
    est_df = pd.read_csv(estimate_csv)

    rows = [
        ("5F", "I", "5F 必要度Ⅰ", WARD_COLORS["5F"]),
        ("5F", "II", "5F 必要度Ⅱ", WARD_COLORS["5F"]),
        ("6F", "I", "6F 必要度Ⅰ", WARD_COLORS["6F"]),
        ("6F", "II", "6F 必要度Ⅱ", WARD_COLORS["6F"]),
    ]

    fig = plt.figure(figsize=(13, 9))
    gs = fig.add_gridspec(2, 1, height_ratios=[2.2, 1.0], hspace=0.05)
    ax = fig.add_subplot(gs[0])
    ax_text = fig.add_subplot(gs[1])
    ax_text.axis("off")

    y_positions = list(range(len(rows)))[::-1]  # 上から 5F-Ⅰ, 5F-Ⅱ, 6F-Ⅰ, 6F-Ⅱ

    for idx, (ward, kind, label, color) in enumerate(rows):
        y = y_positions[idx]
        est_row = est_df[(est_df["ward"] == ward) & (est_df["kind"] == kind)].iloc[0]
        point = float(est_row["rate1_estimate"]) * 100
        lower = float(est_row["rate1_lower_95"]) * 100
        upper = float(est_row["rate1_upper_95"]) * 100

        # 95% CI バー
        bar_face = "#B7DCFF" if ward == "5F" else "#FFC9C9"
        bar_edge = color
        ax.barh(
            y,
            upper - lower,
            left=lower,
            height=0.55,
            color=bar_face,
            edgecolor=bar_edge,
            linewidth=1.5,
            alpha=0.85,
            zorder=2,
        )

        # 点推定マーカー
        ax.scatter(
            point,
            y,
            s=200,
            color=color,
            edgecolor="white",
            linewidth=1.5,
            zorder=4,
        )

        # 中央上に点推定 %
        ax.text(
            point,
            y + 0.36,
            f"{point:.1f}%",
            ha="center",
            va="bottom",
            fontsize=12,
            fontweight="bold",
            color=color,
            zorder=5,
        )

        # 左端 lower
        ax.text(
            lower - 0.4,
            y,
            f"{lower:.1f}",
            ha="right",
            va="center",
            fontsize=10,
            color=color,
            zorder=5,
        )
        # 右端 upper
        ax.text(
            upper + 0.4,
            y,
            f"{upper:.1f}",
            ha="left",
            va="center",
            fontsize=10,
            color=color,
            zorder=5,
        )

        # 達成判定バッジ
        target = TARGET_NEW[kind]
        status_text, status_color = _classify_status(point, lower, upper, target)
        ax.text(
            38.5,
            y,
            f"⚠️ {status_text}",
            ha="right",
            va="center",
            fontsize=10,
            fontweight="bold",
            color=status_color,
            bbox=dict(
                boxstyle="round,pad=0.3",
                facecolor="white",
                edgecolor=status_color,
                linewidth=1.2,
            ),
        )

    # 縦の閾値ライン
    ax.axvline(
        TARGET_NEW["I"],
        color="#D62728",
        linestyle="--",
        linewidth=1.8,
        alpha=0.85,
        label=f"必要度Ⅰ 新基準 {int(TARGET_NEW['I'])}%",
        zorder=1,
    )
    ax.axvline(
        TARGET_NEW["II"],
        color="#FF9800",
        linestyle=":",
        linewidth=1.8,
        alpha=0.85,
        label=f"必要度Ⅱ 新基準 {int(TARGET_NEW['II'])}%",
        zorder=1,
    )

    # 凡例（点推定マーカー＋CI 範囲）
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    legend_handles = [
        Line2D([], [], marker="o", color="w", markerfacecolor="#1F77B4",
               markersize=12, label="推定値", linestyle=""),
        Line2D([], [], color="#D62728", linestyle="--", linewidth=1.8,
               label="必要度Ⅰ 新基準 19%"),
        Line2D([], [], color="#FF9800", linestyle=":", linewidth=1.8,
               label="必要度Ⅱ 新基準 18%"),
        Patch(facecolor="#B7DCFF", edgecolor="#1F77B4", label="95% 信頼区間"),
    ]
    ax.legend(handles=legend_handles, loc="lower right", fontsize=9, framealpha=0.95)

    ax.set_yticks(y_positions)
    ax.set_yticklabels([r[2] for r in rows], fontsize=11)
    ax.set_xlabel("該当患者割合 (%)", fontsize=11)
    ax.set_xlim(0, 40)
    ax.set_ylim(-0.7, len(rows) - 0.3)
    ax.grid(axis="x", alpha=0.3, zorder=0)
    ax.set_title(
        "2026-04 看護必要度 推定値 + 95% 信頼区間\n"
        "推論方法: H ファイル特徴量 × Ridge 回帰（L2 正則化）+ Bootstrap (B=1000) で 95%CI 算出",
        fontsize=13,
        fontweight="bold",
        pad=15,
    )

    # 解説パネル（下半分）
    with summary_json.open("r", encoding="utf-8") as f:
        summary = json.load(f)
    mae_I = summary["necessity_I"]["loocv_mae"] * 100
    mae_II = summary["necessity_II"]["loocv_mae"] * 100

    explanation = (
        "📖  推定方法（素人向け解説）\n"
        f"   ① 過去 12 ヶ月の H ファイル基礎データから「月×病棟」の特徴量を計算（112 列）\n"
        f"   ② 確定看護必要度との関係を Ridge 回帰（L2 正則化）で学習\n"
        f"        ※ 必要度Ⅰ = 5 特徴量, α=1.0, LOOCV MAE = {mae_I:.2f}pt\n"
        f"        ※ 必要度Ⅱ = 3 特徴量, α=0.1, LOOCV MAE = {mae_II:.2f}pt\n"
        "   ③ 4 月の特徴量にモデルを適用 → 点推定値\n"
        "\n"
        "📐  95% 信頼区間の意味\n"
        "       「真の 4 月実測値は、この範囲のどこかに 95% の確率で入る」という統計的予測。\n"
        "       範囲の幅は Bootstrap（24 サンプルから復元抽出 × 1000 回再学習）の予測分布から計算。\n"
        "       区間が新基準ラインをまたぐ場合は判定不能（ボーダーまたぐ）。\n"
        "\n"
        "⚠️  注意: これは推定値です。施設基準達成判定には実測データが必須。\n"
        f"       事務に 4 月実データを依頼すると、信頼区間なしの確定値が得られます。\n"
        f"       なお、本表は rate1（救急係数 1.48pt 加算前）。割合指数の判定は別途参照。"
    )
    ax_text.text(
        0.025,
        0.96,
        explanation,
        transform=ax_text.transAxes,
        ha="left",
        va="top",
        fontsize=10,
        bbox=dict(
            boxstyle="round,pad=0.7",
            facecolor="#FFF8E1",
            edgecolor="#E0C97F",
            linewidth=1.2,
        ),
    )

    fig.savefig(output_path, dpi=130, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> None:
    base = Path("data/nursing_estimation")
    fig_dir = base / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    print("[1/2] Generating monthly trend figure ...")
    make_figure_monthly_trend(
        feature_csv=base / "feature_matrix.csv",
        estimate_csv=base / "estimate_2026apr.csv",
        summary_json=base / "cv_summary.json",
        output_path=fig_dir / "5_monthly_trend_with_estimate.png",
    )
    print(f"     -> {fig_dir / '5_monthly_trend_with_estimate.png'}")

    print("[2/2] Generating horizontal CI summary figure ...")
    make_figure_horizontal_ci(
        estimate_csv=base / "estimate_2026apr.csv",
        summary_json=base / "cv_summary.json",
        output_path=fig_dir / "6_horizontal_ci_summary.png",
    )
    print(f"     -> {fig_dir / '6_horizontal_ci_summary.png'}")
    print("\n✅ Done.")


if __name__ == "__main__":
    main()
