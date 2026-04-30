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
# Figure 7: LOOCV 検証（散布図 + 月別 MAE バー）
# ---------------------------------------------------------------------------


def make_figure_loocv_validation(
    cv_pred_I_csv: Path,
    cv_pred_II_csv: Path,
    output_path: Path,
) -> None:
    """LOOCV の予測値と実測値の散布図 + 月別 MAE バー."""
    pred_I = pd.read_csv(cv_pred_I_csv)
    pred_I["kind"] = "I"
    pred_II = pd.read_csv(cv_pred_II_csv)
    pred_II["kind"] = "II"
    pred = pd.concat([pred_I, pred_II], ignore_index=True)
    pred["year_month"] = pred["year_month"].astype(str)
    pred["actual_pct"] = pred["actual"] * 100
    pred["predicted_pct"] = pred["predicted"] * 100
    pred["abs_error_pt"] = (pred["predicted_pct"] - pred["actual_pct"]).abs()

    overall_mae = pred["abs_error_pt"].mean()
    median_err = pred["abs_error_pt"].median()
    max_err = pred["abs_error_pt"].max()
    n_total = len(pred)

    fig = plt.figure(figsize=(14, 6.5))
    gs = fig.add_gridspec(2, 2, height_ratios=[14, 1.2], hspace=0.55, wspace=0.25)
    ax_left = fig.add_subplot(gs[0, 0])
    ax_right = fig.add_subplot(gs[0, 1])
    ax_note = fig.add_subplot(gs[1, :])
    ax_note.axis("off")

    # ---- Left: 散布図 ----
    marker_map = {
        ("5F", "I"): {"marker": "o", "color": "#1F77B4", "label": "5F 必要度Ⅰ"},
        ("5F", "II"): {"marker": "s", "color": "#5BA3D9", "label": "5F 必要度Ⅱ"},
        ("6F", "I"): {"marker": "o", "color": "#D62728", "label": "6F 必要度Ⅰ"},
        ("6F", "II"): {"marker": "s", "color": "#FF8B8B", "label": "6F 必要度Ⅱ"},
    }
    for (ward, kind), style in marker_map.items():
        sub = pred[(pred["ward"] == ward) & (pred["kind"] == kind)]
        ax_left.scatter(
            sub["actual_pct"],
            sub["predicted_pct"],
            marker=style["marker"],
            color=style["color"],
            s=80,
            alpha=0.75,
            edgecolor="white",
            linewidth=1,
            label=style["label"],
            zorder=3,
        )

    lim_min = max(0, min(pred["actual_pct"].min(), pred["predicted_pct"].min()) - 1.5)
    lim_max = max(pred["actual_pct"].max(), pred["predicted_pct"].max()) + 1.5
    ax_left.plot(
        [lim_min, lim_max],
        [lim_min, lim_max],
        linestyle="--",
        color="#888",
        linewidth=1.2,
        alpha=0.7,
        label="理想線（実測 = 推定）",
        zorder=1,
    )
    ax_left.set_xlim(lim_min, lim_max)
    ax_left.set_ylim(lim_min, lim_max)
    ax_left.set_xlabel("実測値 (%)", fontsize=11)
    ax_left.set_ylabel("LOOCV 推定値 (%)", fontsize=11)
    ax_left.set_title(f"散布図: 実測 vs 推定（n={n_total}）", fontsize=12, fontweight="bold")
    ax_left.grid(alpha=0.25, zorder=0)
    ax_left.legend(loc="lower right", fontsize=9, framealpha=0.95)

    # 統計ボックス（左上）
    stat_text = (
        f"全体 MAE: {overall_mae:.2f} pt\n"
        f"中央値: {median_err:.2f} pt\n"
        f"最大: {max_err:.2f} pt"
    )
    ax_left.text(
        0.04,
        0.96,
        stat_text,
        transform=ax_left.transAxes,
        ha="left",
        va="top",
        fontsize=10,
        fontweight="bold",
        bbox=dict(
            boxstyle="round,pad=0.45",
            facecolor="#E3F2FD",
            edgecolor="#1F77B4",
            linewidth=1.2,
        ),
    )

    # ---- Right: 月別 MAE バー ----
    months = sorted(pred["year_month"].unique())
    n_months = len(months)
    width = 0.38
    x_pos = np.arange(n_months)

    mae_5F = []
    mae_6F = []
    for ym in months:
        m5 = pred[(pred["year_month"] == ym) & (pred["ward"] == "5F")]["abs_error_pt"].mean()
        m6 = pred[(pred["year_month"] == ym) & (pred["ward"] == "6F")]["abs_error_pt"].mean()
        mae_5F.append(m5)
        mae_6F.append(m6)

    ax_right.bar(
        x_pos - width / 2,
        mae_5F,
        width,
        color="#1F77B4",
        edgecolor="#0F4C75",
        linewidth=0.5,
        label="5F",
    )
    ax_right.bar(
        x_pos + width / 2,
        mae_6F,
        width,
        color="#D62728",
        edgecolor="#8B1A1B",
        linewidth=0.5,
        label="6F",
    )
    ax_right.axhline(
        overall_mae,
        color="#333",
        linestyle="--",
        linewidth=1.2,
        alpha=0.85,
        label=f"全体 MAE = {overall_mae:.2f} pt",
        zorder=1,
    )
    ax_right.set_xticks(x_pos)
    ax_right.set_xticklabels(
        [f"{ym[:4]}-{ym[4:]}" for ym in months], rotation=45, fontsize=8, ha="right"
    )
    ax_right.set_ylabel("絶対誤差 (pt)", fontsize=11)
    ax_right.set_title("月別 平均絶対誤差（病棟別）", fontsize=12, fontweight="bold")
    ax_right.legend(loc="upper left", fontsize=9, framealpha=0.95)
    ax_right.grid(axis="y", alpha=0.25, zorder=0)

    # ---- Title ----
    fig.suptitle(
        "LOOCV（リーブワンアウト）による推論精度の検証\n"
        "過去 12 ヶ月の各月を「未知」と仮定し、残り 11 ヶ月から Ridge 回帰で推定 → 実測と比較",
        fontsize=12,
        fontweight="bold",
        y=0.99,
    )

    # ---- Bottom note ----
    if overall_mae <= 2.5:
        verdict = f"✅ 高精度（MAE = {overall_mae:.1f}pt）— 推定値の信頼性は高い"
        verdict_color = "#2CA02C"
    elif overall_mae <= 3.5:
        verdict = f"🟡 中精度（MAE = {overall_mae:.1f}pt）— 方向性把握には十分、判断には実測併用推奨"
        verdict_color = "#FF9800"
    else:
        verdict = f"⚠️ 低精度（MAE = {overall_mae:.1f}pt）— 単なる推論、判断には実測データが必要"
        verdict_color = "#D62728"
    ax_note.text(
        0.5,
        0.5,
        verdict,
        transform=ax_note.transAxes,
        ha="center",
        va="center",
        fontsize=11,
        fontweight="bold",
        color=verdict_color,
        bbox=dict(
            boxstyle="round,pad=0.5",
            facecolor="white",
            edgecolor=verdict_color,
            linewidth=1.5,
        ),
    )

    fig.savefig(output_path, dpi=130, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 8: 手法比較（K/α grid の MAE + 採用された Ridge 係数）
# ---------------------------------------------------------------------------


def _compute_loocv_mae_for_config(
    df: pd.DataFrame, target_col: str, target_name: str, k: int, alpha: float
) -> float:
    """指定 K, alpha で LOOCV MAE を計算する."""
    from scripts.nursing_estimation.estimator import (
        leave_one_month_out_cv,
        select_top_k_features,
    )

    train_df = df.dropna(subset=[target_col]).reset_index(drop=True)
    feat_pool = [
        c
        for c in train_df.columns
        if c not in ("year_month", "ward", "I_actual_rate", "II_actual_rate")
    ]
    feats = select_top_k_features(train_df[feat_pool], train_df[target_col], k)
    res = leave_one_month_out_cv(train_df, target_col, feats, alpha, target_name)
    return res.mae * 100  # pt 換算


def make_figure_method_comparison(
    feature_csv: Path,
    summary_json: Path,
    output_path: Path,
) -> None:
    df = pd.read_csv(feature_csv)
    with summary_json.open("r", encoding="utf-8") as f:
        summary = json.load(f)

    # 比較する手法構成
    configs = [
        ("ベースライン（K=3, α=10）", 3, 10.0),
        ("特徴量増（K=8, α=10）", 8, 10.0),
        ("正則化弱（K=5, α=0.1）", 5, 0.1),
        ("正則化強（K=12, α=100）", 12, 100.0),
        ("採用: 必要度Ⅰ（K=5, α=1.0）", 5, 1.0),
        ("採用: 必要度Ⅱ（K=3, α=0.1）", 3, 0.1),
    ]

    rows = []
    for label, k, alpha in configs:
        mae_I = _compute_loocv_mae_for_config(df, "I_actual_rate", "I", k, alpha)
        mae_II = _compute_loocv_mae_for_config(df, "II_actual_rate", "II", k, alpha)
        avg = (mae_I + mae_II) / 2
        rows.append({"label": label, "k": k, "alpha": alpha, "mae_I": mae_I, "mae_II": mae_II, "mae_avg": avg})
    comp_df = pd.DataFrame(rows).sort_values("mae_avg", ascending=False).reset_index(drop=True)

    baseline_mae = comp_df.iloc[0]["mae_avg"]
    best_mae = comp_df.iloc[-1]["mae_avg"]
    best_label = comp_df.iloc[-1]["label"]
    improvement_pct = (1 - best_mae / baseline_mae) * 100

    # ---- Figure ----
    fig = plt.figure(figsize=(14, 7))
    gs = fig.add_gridspec(2, 2, height_ratios=[10, 1], hspace=0.05, wspace=0.30)
    ax_left = fig.add_subplot(gs[0, 0])
    ax_right = fig.add_subplot(gs[0, 1])
    ax_note = fig.add_subplot(gs[1, :])
    ax_note.axis("off")

    # ---- Left: 手法比較バー ----
    y_positions = list(range(len(comp_df)))
    colors = []
    for label in comp_df["label"]:
        if label.startswith("採用"):
            colors.append("#2CA02C")  # 緑
        elif "ベースライン" in label:
            colors.append("#888888")  # 灰
        else:
            colors.append("#5BA3D9")  # 青

    bars = ax_left.barh(
        y_positions,
        comp_df["mae_avg"],
        color=colors,
        edgecolor="white",
        linewidth=0.8,
    )
    for i, (idx, row) in enumerate(comp_df.iterrows()):
        ax_left.text(
            row["mae_avg"] + 0.05,
            i,
            f"{row['mae_avg']:.2f} pt",
            va="center",
            ha="left",
            fontsize=10,
            fontweight="bold",
        )
    ax_left.axvline(
        baseline_mae,
        color="#888",
        linestyle="--",
        linewidth=1.2,
        alpha=0.7,
        label=f"ベースライン MAE = {baseline_mae:.2f}",
    )
    ax_left.set_yticks(y_positions)
    ax_left.set_yticklabels(comp_df["label"], fontsize=10)
    ax_left.set_xlabel("LOOCV 平均絶対誤差（pt）※ 小さいほど良い", fontsize=11)
    ax_left.set_title("各手法の精度比較", fontsize=12, fontweight="bold")
    ax_left.legend(loc="lower right", fontsize=9, framealpha=0.95)
    ax_left.grid(axis="x", alpha=0.25, zorder=0)
    ax_left.invert_yaxis()
    xlim_max = comp_df["mae_avg"].max() * 1.15
    ax_left.set_xlim(0, xlim_max)

    # ---- Right: 採用モデルの Ridge 標準化係数 ----
    from scripts.nursing_estimation.estimator import fit_ridge

    train_df = df.dropna(subset=["I_actual_rate"]).reset_index(drop=True)
    feats_I = summary["necessity_I"]["selected_features"]
    feats_II = summary["necessity_II"]["selected_features"]
    model_I = fit_ridge(train_df, train_df["I_actual_rate"], feats_I,
                        alpha=summary["necessity_I"]["best_alpha"], target="I")
    model_II = fit_ridge(train_df, train_df["II_actual_rate"], feats_II,
                         alpha=summary["necessity_II"]["best_alpha"], target="II")

    feat_set = list(dict.fromkeys(feats_I + feats_II))  # 順序維持で uniq
    coefs_I = []
    coefs_II = []
    for f in feat_set:
        coefs_I.append(model_I.coefs[feats_I.index(f)] if f in feats_I else 0.0)
        coefs_II.append(model_II.coefs[feats_II.index(f)] if f in feats_II else 0.0)

    y2 = np.arange(len(feat_set))
    width = 0.4
    bars_I = ax_right.barh(
        y2 - width / 2,
        coefs_I,
        width,
        color="#1F77B4",
        edgecolor="white",
        linewidth=0.5,
        label="必要度Ⅰ モデル",
    )
    bars_II = ax_right.barh(
        y2 + width / 2,
        coefs_II,
        width,
        color="#FF8B8B",
        edgecolor="white",
        linewidth=0.5,
        label="必要度Ⅱ モデル",
    )
    for i, c in enumerate(coefs_I):
        if c != 0:
            ax_right.text(
                c + (0.0003 if c > 0 else -0.0003),
                i - width / 2,
                f"{c:+.4f}",
                va="center",
                ha="left" if c > 0 else "right",
                fontsize=8,
            )
    for i, c in enumerate(coefs_II):
        if c != 0:
            ax_right.text(
                c + (0.0003 if c > 0 else -0.0003),
                i + width / 2,
                f"{c:+.4f}",
                va="center",
                ha="left" if c > 0 else "right",
                fontsize=8,
            )
    ax_right.axvline(0, color="#444", linewidth=0.8)
    ax_right.set_yticks(y2)
    ax_right.set_yticklabels(feat_set, fontsize=9)
    ax_right.set_xlabel("Ridge 標準化回帰係数 ※ 絶対値が大きいほど予測に効いている", fontsize=10)
    ax_right.set_title("採用モデルの特徴量重み（標準化係数）", fontsize=12, fontweight="bold")
    ax_right.legend(loc="lower right", fontsize=9, framealpha=0.95)
    ax_right.grid(axis="x", alpha=0.25, zorder=0)
    ax_right.invert_yaxis()

    # ---- Title ----
    fig.suptitle(
        "ハイパーパラメータ探索を活用した推論精度の改善試行\n"
        "サンプル数 n=24（12 ヶ月 × 2 病棟）の制約下で、特徴量数 K と正則化強度 α を変えて比較",
        fontsize=12,
        fontweight="bold",
        y=0.99,
    )

    # ---- Bottom note ----
    note_text = (
        f"📊 改善幅: {baseline_mae:.2f} → {best_mae:.2f} pt（{improvement_pct:.0f}% 改善）  ｜  "
        f"最良手法: {best_label}\n"
        "⚠️ サンプル数 n=24 のため複雑モデルは過学習リスク。実測データ取得が依然 最優先。"
    )
    ax_note.text(
        0.5,
        0.5,
        note_text,
        transform=ax_note.transAxes,
        ha="center",
        va="center",
        fontsize=10,
        bbox=dict(
            boxstyle="round,pad=0.5",
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

    print("[1/4] Generating monthly trend figure ...")
    make_figure_monthly_trend(
        feature_csv=base / "feature_matrix.csv",
        estimate_csv=base / "estimate_2026apr.csv",
        summary_json=base / "cv_summary.json",
        output_path=fig_dir / "5_monthly_trend_with_estimate.png",
    )
    print(f"     -> {fig_dir / '5_monthly_trend_with_estimate.png'}")

    print("[2/4] Generating horizontal CI summary figure ...")
    make_figure_horizontal_ci(
        estimate_csv=base / "estimate_2026apr.csv",
        summary_json=base / "cv_summary.json",
        output_path=fig_dir / "6_horizontal_ci_summary.png",
    )
    print(f"     -> {fig_dir / '6_horizontal_ci_summary.png'}")

    print("[3/4] Generating LOOCV validation figure ...")
    make_figure_loocv_validation(
        cv_pred_I_csv=base / "cv_predictions_I.csv",
        cv_pred_II_csv=base / "cv_predictions_II.csv",
        output_path=fig_dir / "7_loocv_validation.png",
    )
    print(f"     -> {fig_dir / '7_loocv_validation.png'}")

    print("[4/4] Generating method comparison figure ...")
    make_figure_method_comparison(
        feature_csv=base / "feature_matrix.csv",
        summary_json=base / "cv_summary.json",
        output_path=fig_dir / "8_method_comparison.png",
    )
    print(f"     -> {fig_dir / '8_method_comparison.png'}")
    print("\n✅ Done.")
    print(f"     -> {fig_dir / '6_horizontal_ci_summary.png'}")
    print("\n✅ Done.")


if __name__ == "__main__":
    main()
