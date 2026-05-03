"""Create a 4-panel visualization pack for the April 2026 nursing estimate."""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import estimate_nursing_necessity_patient_day_202604 as patient_day_model


REPORTS = ROOT / "reports"
NURSING_CSV = ROOT / "data" / "nursing_necessity_2025fy.csv"
PATIENT_DAY_RESULTS = REPORTS / "nursing_necessity_patient_day_202604.csv"
PATIENT_DAY_CV = REPORTS / "nursing_necessity_patient_day_202604_lomo_cv.csv"
MONTHLY_RESULTS = REPORTS / "nursing_necessity_estimate_202604.csv"

OUT_TRENDS = REPORTS / "nursing_necessity_202604_viz_1_monthly_trends.png"
OUT_CV = REPORTS / "nursing_necessity_202604_viz_2_lomo_validation.png"
OUT_METHODS = REPORTS / "nursing_necessity_202604_viz_3_method_features.png"
OUT_FINAL = REPORTS / "nursing_necessity_202604_viz_4_final_ci.png"
OUT_REPORT = REPORTS / "nursing_necessity_202604_visual_summary.md"

THRESHOLD_NEW = {"I": 19.0, "II": 18.0}
THRESHOLD_OLD = {"I": 16.0, "II": 14.0}
WARD_COLOR = {"5F": "#2563EB", "6F": "#E11D27"}
WARD_FILL = {"5F": "#BFD1F6", "6F": "#F6BFC2"}


def setup_font() -> None:
    plt.rcParams["font.family"] = ["Hiragino Sans", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def load_monthly_actual() -> pd.DataFrame:
    df = pd.read_csv(NURSING_CSV, parse_dates=["date"])
    df["ym"] = df["date"].dt.strftime("%Y-%m")
    monthly = (
        df[df["ward"].isin(["5F", "6F"])]
        .groupby(["ym", "ward"], as_index=False)
        .agg(
            I_total=("I_total", "sum"),
            I_pass=("I_pass1", "sum"),
            II_total=("II_total", "sum"),
            II_pass=("II_pass1", "sum"),
        )
    )
    monthly["I_rate_pct"] = monthly["I_pass"] / monthly["I_total"] * 100
    monthly["II_rate_pct"] = monthly["II_pass"] / monthly["II_total"] * 100
    return monthly


def load_estimates() -> pd.DataFrame:
    return pd.read_csv(PATIENT_DAY_RESULTS)


def plot_monthly_trends(monthly: pd.DataFrame, estimates: pd.DataFrame) -> None:
    order = [
        ("5F", "I", "5F 病棟 — 必要度I"),
        ("5F", "II", "5F 病棟 — 必要度II"),
        ("6F", "I", "6F 病棟 — 必要度I"),
        ("6F", "II", "6F 病棟 — 必要度II"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(14, 8.2), sharex=False)
    axes = axes.ravel()
    months = sorted(monthly["ym"].unique()) + ["2026-04"]
    x_actual = np.arange(len(months) - 1)
    x_est = len(months) - 1

    for ax, (ward, outcome, title) in zip(axes, order):
        col = f"{outcome}_rate_pct"
        sub = monthly[monthly["ward"].eq(ward)].sort_values("ym")
        est = float(estimates[(estimates["ward"].eq(ward)) & (estimates["outcome"].eq(outcome))]["estimate_pct"].iloc[0])
        threshold = THRESHOLD_NEW[outcome]
        gap = est - threshold

        ax.plot(x_actual, sub[col], color=WARD_COLOR[ward], marker="o", linewidth=2.2, label=f"{ward} 実測")
        ax.plot([x_actual[-1], x_est], [sub[col].iloc[-1], est], color="#64748B", linestyle="--", linewidth=1.2)
        ax.scatter([x_est], [est], s=360, color="black", marker="*", zorder=5, label=f"4月推定 = {est:.1f}%")
        ax.axhline(THRESHOLD_NEW[outcome], color="#EF4444", linestyle="--", linewidth=1.4, label=f"新基準 {threshold:.0f}%")
        ax.axhline(THRESHOLD_OLD[outcome], color="#94A3B8", linestyle=":", linewidth=1.2, label=f"旧基準 {THRESHOLD_OLD[outcome]:.0f}%")
        ax.set_title(title, fontsize=12, weight="bold")
        ax.set_ylabel("該当患者割合 (%)")
        ax.set_xticks(np.arange(len(months)))
        ax.set_xticklabels(months, rotation=50, ha="right", fontsize=8)
        ax.set_ylim(4, max(25, sub[col].max() + 2))
        ax.grid(True, alpha=0.25)
        ax.legend(fontsize=8, loc="lower left")

        status = "到達" if gap >= 0 else "未達"
        ax.text(
            0.98,
            0.05,
            f"{status} ({gap:+.1f}pt)",
            transform=ax.transAxes,
            ha="right",
            va="bottom",
            color="#DC2626" if gap < 0 else "#047857",
            fontsize=10,
            weight="bold",
            bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="#DC2626" if gap < 0 else "#047857"),
        )

    fig.suptitle(
        "看護必要度 月次推移（実測12ヶ月 + 2026-04 患者日モデル推定値）\n"
        "Hn患者日 + En/Fn処置名proxyから集計制約付きロジスティック回帰で推定",
        fontsize=13,
        weight="bold",
        y=0.98,
    )
    fig.text(
        0.5,
        0.02,
        "※ 4月値は推定値。施設基準判定にはDPCデータ提出支援ツールによる確定値が必要。",
        ha="center",
        fontsize=9,
        bbox=dict(boxstyle="round,pad=0.35", facecolor="#FFF7D6", edgecolor="#F59E0B"),
    )
    fig.tight_layout(rect=[0, 0.06, 1, 0.93])
    fig.savefig(OUT_TRENDS, dpi=220)
    plt.close(fig)


def plot_lomo_validation() -> None:
    cv = pd.read_csv(PATIENT_DAY_CV)
    cv["label"] = cv["ward"] + " 必要度" + cv["outcome"]
    overall_mae = cv["residual_pct"].abs().mean()
    median_abs = cv["residual_pct"].abs().median()
    max_abs = cv["residual_pct"].abs().max()

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6.3), gridspec_kw={"width_ratios": [1, 1.45]})

    markers = {"I": "o", "II": "s"}
    for (ward, outcome), sub in cv.groupby(["ward", "outcome"]):
        ax1.scatter(
            sub["actual_pct"],
            sub["predicted_pct"],
            label=f"{ward} 必要度{outcome}",
            color=WARD_COLOR[ward],
            marker=markers[outcome],
            s=70,
            alpha=0.72,
            edgecolor="#334155",
            linewidth=0.5,
        )
    lim_low = min(cv["actual_pct"].min(), cv["predicted_pct"].min()) - 1
    lim_high = max(cv["actual_pct"].max(), cv["predicted_pct"].max()) + 1
    ax1.plot([lim_low, lim_high], [lim_low, lim_high], color="#888888", linestyle="--", label="理想線")
    ax1.set_xlim(lim_low, lim_high)
    ax1.set_ylim(lim_low, lim_high)
    ax1.set_xlabel("実測値 (%)")
    ax1.set_ylabel("LOMO-CV 推定値 (%)")
    ax1.set_title("散布図: 実測 vs 推定 (n=48)", weight="bold")
    ax1.grid(True, alpha=0.25)
    ax1.legend(fontsize=8, loc="lower right")
    ax1.text(
        0.03,
        0.95,
        f"全体 MAE: {overall_mae:.2f} pt\n中央値: {median_abs:.2f} pt\n最大: {max_abs:.2f} pt",
        transform=ax1.transAxes,
        va="top",
        fontsize=10,
        weight="bold",
        bbox=dict(boxstyle="round,pad=0.35", facecolor="#EEF2FF", edgecolor="#2563EB"),
    )

    month_ward = cv.groupby(["ym", "ward"], as_index=False)["residual_pct"].apply(lambda s: s.abs().mean())
    month_ward = month_ward.rename(columns={"residual_pct": "abs_error"})
    months = sorted(month_ward["ym"].unique())
    x = np.arange(len(months))
    width = 0.38
    for offset, ward in [(-width / 2, "5F"), (width / 2, "6F")]:
        vals = [
            float(month_ward[(month_ward["ym"].eq(month)) & (month_ward["ward"].eq(ward))]["abs_error"].iloc[0])
            for month in months
        ]
        ax2.bar(x + offset, vals, width=width, label=ward, color=WARD_COLOR[ward], alpha=0.86)
    ax2.axhline(overall_mae, color="black", linestyle="--", linewidth=1.2, label=f"全体 MAE = {overall_mae:.2f} pt")
    ax2.set_xticks(x)
    month_labels = []
    for month in months:
        text = str(month)
        month_labels.append(text[:4] + "-" + text[4:] if len(text) == 6 else text)
    ax2.set_xticklabels(month_labels, rotation=45, ha="right", fontsize=8)
    ax2.set_ylabel("絶対誤差 (pt)")
    ax2.set_title("月別 平均絶対誤差（病棟別）", weight="bold")
    ax2.grid(axis="y", alpha=0.25)
    ax2.legend(fontsize=9)

    fig.suptitle(
        "LOMO-CV（リーブワンマンスアウト）による推論精度の検証\n"
        "過去12ヶ月の各月を未知と仮定し、残り11ヶ月で学習 → 実測と比較",
        fontsize=13,
        weight="bold",
        y=0.98,
    )
    fig.text(
        0.5,
        0.03,
        f"※ 検証誤差 MAE={overall_mae:.2f}pt。点推定は管理用、施設基準判断には確定データが必要。",
        ha="center",
        color="#DC2626",
        fontsize=10,
        weight="bold",
        bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor="#DC2626"),
    )
    fig.tight_layout(rect=[0, 0.08, 1, 0.90])
    fig.savefig(OUT_CV, dpi=220)
    plt.close(fig)


def plot_method_features() -> None:
    cv = pd.read_csv(PATIENT_DAY_CV)
    results = pd.read_csv(PATIENT_DAY_RESULTS)
    monthly = pd.read_csv(MONTHLY_RESULTS) if MONTHLY_RESULTS.exists() else pd.DataFrame()

    patient_day_mae = cv["residual_pct"].abs().mean()
    by_outcome_mae = cv.groupby("outcome")["residual_pct"].apply(lambda s: s.abs().mean()).to_dict()
    cluster_mean_half_width = ((results["cluster_ci_high_pct"] - results["cluster_ci_low_pct"]) / 2).mean()
    cv_range_half_width = ((results["cv_pi_high_pct"] - results["cv_pi_low_pct"]) / 2).mean()
    monthly_loo = float(monthly["loo_mae_pct"].mean()) if not monthly.empty and "loo_mae_pct" in monthly.columns else np.nan

    labels = [
        "月次類似法\n(前回LOO)",
        "患者日モデル\nLOMO-CV",
        "患者クラスタCI\n半幅のみ",
        "CV補正レンジ\n半幅",
    ]
    values = [monthly_loo, patient_day_mae, cluster_mean_half_width, cv_range_half_width]
    colors = ["#8B8B8B", "#10B981", "#60A5FA", "#F59E0B"]

    feature_importance = compute_feature_importance()
    top = feature_importance.head(10).iloc[::-1]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6.2))
    ax1.barh(labels[::-1], values[::-1], color=colors[::-1], alpha=0.85, edgecolor="#334155")
    for i, value in enumerate(values[::-1]):
        ax1.text(value + 0.08, i, f"{value:.2f} pt", va="center", fontsize=9)
    ax1.axvline(patient_day_mae, color="#047857", linestyle="--", linewidth=1.2, label=f"患者日 LOMO MAE = {patient_day_mae:.2f}")
    ax1.set_xlabel("pt（小さいほど狭い/良い。ただしCI半幅とMAEは意味が異なる）")
    ax1.set_title("不確実性・精度指標の比較", weight="bold")
    ax1.grid(axis="x", alpha=0.25)
    ax1.legend(fontsize=8)

    ax2.barh(top["feature_label"], top["importance"], color="#2563EB", alpha=0.86)
    for i, value in enumerate(top["importance"]):
        ax2.text(value + 0.02, i, f"{value:.2f}", va="center", fontsize=8)
    ax2.axvline(1.0, color="#888888", linestyle="--", linewidth=1.0, label="目安 = 1.0")
    ax2.set_xlabel("標準化係数の平均絶対値")
    ax2.set_title("患者日モデルの特徴量重要度（I/II平均）", weight="bold")
    ax2.grid(axis="x", alpha=0.25)
    ax2.legend(fontsize=8)

    fig.suptitle(
        "LOMO-CVを活用した推論精度・特徴量の見える化\n"
        f"必要度I MAE={by_outcome_mae.get('I', np.nan):.2f}pt / 必要度II MAE={by_outcome_mae.get('II', np.nan):.2f}pt",
        fontsize=13,
        weight="bold",
        y=0.98,
    )
    fig.text(
        0.5,
        0.03,
        "※ 患者クラスタCIは狭いが、教師ラベルが月次集計のみのため、判断にはLOMO-CV誤差を併記する。",
        ha="center",
        fontsize=10,
        color="#F59E0B",
        weight="bold",
        bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor="#F59E0B"),
    )
    fig.tight_layout(rect=[0, 0.08, 1, 0.90])
    fig.savefig(OUT_METHODS, dpi=220)
    plt.close(fig)


def compute_feature_importance() -> pd.DataFrame:
    patient_days = patient_day_model.build_patient_day_table(patient_day_model.DEFAULT_MONTHLY_DIR)
    targets = patient_day_model.load_targets(patient_day_model.DEFAULT_NURSING_CSV)
    features = [feature for feature in patient_day_model.MODEL_FEATURES if feature in patient_days.columns]
    groups = set(
        targets[targets["ym"].between(patient_day_model.TRAIN_START_YM, patient_day_model.TRAIN_END_YM)][
            ["ym", "ward"]
        ].apply(tuple, axis=1)
    )

    rows = []
    for outcome in ["I", "II"]:
        artifacts = patient_day_model.fit_grouped_logistic(
            patient_days=patient_days,
            targets=targets,
            outcome=outcome,
            train_groups=groups,
            features=features,
            steps=1800,
        )
        coefs = np.abs(artifacts.beta[1:])
        for feature, coef in zip(features, coefs):
            rows.append({"feature": feature, "outcome": outcome, "coef_abs": float(coef)})
    out = pd.DataFrame(rows).groupby("feature", as_index=False)["coef_abs"].mean()
    out["importance"] = out["coef_abs"] / max(float(out["coef_abs"].median()), 1e-9)
    out["feature_label"] = out["feature"].map(feature_label)
    return out.sort_values("importance", ascending=False)


def feature_label(feature: str) -> str:
    labels = {
        "ward_6f": "6F病棟",
        "log_stay_day": "在院日数",
        "phase_1_3": "Day1-3",
        "phase_4_7": "Day4-7",
        "phase_8_14": "Day8-14",
        "phase_15p": "Day15+",
        "ef_line_count": "EF行数",
        "kw_oxygen_count": "酸素proxy",
        "kw_monitor_count": "監視proxy",
        "kw_injection_count": "注射proxy",
        "kw_transfusion_count": "輸血proxy",
        "kw_endoscopy_count": "内視鏡proxy",
        "kw_c_proc_count": "C項目候補proxy",
        "kw_surgery_count": "手術/麻酔proxy",
        "kw_severe_count": "重症ケアproxy",
        "kw_adl_count": "ADL proxy",
    }
    if feature in labels:
        return labels[feature]
    return feature.replace("ass13_", "ASS0013 ").replace("ass21_", "ASS0021 ")


def plot_final_ci() -> None:
    results = pd.read_csv(PATIENT_DAY_RESULTS)
    order = [
        ("5F", "I", "5F 必要度I"),
        ("5F", "II", "5F 必要度II"),
        ("6F", "I", "6F 必要度I"),
        ("6F", "II", "6F 必要度II"),
    ]

    fig, ax = plt.subplots(figsize=(12.5, 6.8))
    y = np.arange(len(order))
    for i, (ward, outcome, label) in enumerate(order):
        row = results[(results["ward"].eq(ward)) & (results["outcome"].eq(outcome))].iloc[0]
        est = float(row["estimate_pct"])
        low = float(row["cv_pi_low_pct"])
        high = float(row["cv_pi_high_pct"])
        inner_low = float(row["cluster_ci_low_pct"])
        inner_high = float(row["cluster_ci_high_pct"])
        threshold = THRESHOLD_NEW[outcome]
        gap = est - threshold
        status = "達成見込み" if gap >= 0 else ("ボーダー" if gap >= -2.0 else "未達")

        ax.barh(i, high - low, left=low, color=WARD_FILL[ward], edgecolor=WARD_FILL[ward], alpha=0.55, height=0.58)
        ax.barh(i, inner_high - inner_low, left=inner_low, color=WARD_FILL[ward], edgecolor=WARD_COLOR[ward], alpha=0.9, height=0.18)
        ax.scatter(est, i, s=110, color=WARD_COLOR[ward], edgecolor="black", zorder=4)
        ax.text(est, i - 0.34, f"{est:.1f}%", ha="center", va="center", fontsize=11, weight="bold", color=WARD_COLOR[ward])
        ax.text(low, i - 0.26, f"{low:.1f}", ha="right", va="center", fontsize=8, color=WARD_COLOR[ward])
        ax.text(high, i - 0.26, f"{high:.1f}", ha="left", va="center", fontsize=8, color=WARD_COLOR[ward])
        ax.text(
            31.0,
            i,
            f"{status} ({gap:+.1f}pt)",
            ha="center",
            va="center",
            fontsize=10,
            weight="bold",
            color="#DC2626" if gap < 0 else "#047857",
            bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="#F59E0B"),
        )

    ax.axvline(THRESHOLD_NEW["I"], color="#EF4444", linestyle="--", linewidth=1.5, label="必要度I 新基準 19%")
    ax.axvline(THRESHOLD_NEW["II"], color="#F59E0B", linestyle=":", linewidth=1.5, label="必要度II 新基準 18%")
    ax.set_yticks(y)
    ax.set_yticklabels([label for _, _, label in order], fontsize=11, weight="bold")
    ax.invert_yaxis()
    ax.set_xlim(0, 35)
    ax.set_xlabel("該当患者割合 (%)")
    ax.grid(axis="x", alpha=0.25)
    ax.legend(loc="lower right", fontsize=9)
    ax.set_title(
        "2026-04 看護必要度 推定値 + 95%レンジ\n"
        "推論方法: 患者日モデル（Hn患者日 + En/Fn処置名proxy）",
        fontsize=13,
        weight="bold",
    )
    note = (
        "図の読み方\n"
        "濃い帯: 同一患者内相関を考慮した患者クラスタ95%CI。薄い帯: LOMO-CV誤差を加味した実務上の95%予測レンジ。\n"
        "点推定は管理用推計であり、施設基準の確定判定にはDPCデータ提出支援ツールによる実測が必要。"
    )
    fig.text(
        0.08,
        0.02,
        note,
        ha="left",
        va="bottom",
        fontsize=9,
        bbox=dict(boxstyle="round,pad=0.55", facecolor="#FFF7D6", edgecolor="#F59E0B"),
    )
    fig.tight_layout(rect=[0, 0.15, 1, 0.94])
    fig.savefig(OUT_FINAL, dpi=220)
    plt.close(fig)


def write_summary() -> None:
    results = pd.read_csv(PATIENT_DAY_RESULTS)
    lines = [
        "# 2026-04 看護必要度 可視化サマリー",
        "",
        f"![月次推移]({OUT_TRENDS})",
        "",
        f"![LOMO-CV検証]({OUT_CV})",
        "",
        f"![手法比較]({OUT_METHODS})",
        "",
        f"![最終推計]({OUT_FINAL})",
        "",
        "## 数値",
        "",
        "| 病棟 | 区分 | 推定値 | 患者クラスタ95%CI | CV補正95%予測レンジ |",
        "|---|---:|---:|---:|---:|",
    ]
    for _, row in results.iterrows():
        lines.append(
            f"| {row['ward']} | 必要度{row['outcome']} | {row['estimate_pct']:.1f}% | "
            f"{row['cluster_ci_low_pct']:.1f}-{row['cluster_ci_high_pct']:.1f}% | "
            f"{row['cv_pi_low_pct']:.1f}-{row['cv_pi_high_pct']:.1f}% |"
        )
    OUT_REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    setup_font()
    monthly = load_monthly_actual()
    estimates = load_estimates()
    plot_monthly_trends(monthly, estimates)
    plot_lomo_validation()
    plot_method_features()
    plot_final_ci()
    write_summary()
    print(OUT_TRENDS)
    print(OUT_CV)
    print(OUT_METHODS)
    print(OUT_FINAL)
    print(OUT_REPORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
