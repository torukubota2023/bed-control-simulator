"""Create the reconciled Codex/Claude visualization pack for April 2026.

The first visualization pack focused on the Codex patient-day model.  This
second pack keeps the same four-figure structure, but adds the Claude Code
cross-check, the emergency response coefficient, and the H-file interpretation
correction that matters for handoff.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
NURSING_CSV = ROOT / "data" / "nursing_necessity_2025fy.csv"
CODEX_RESULTS = REPORTS / "nursing_necessity_patient_day_202604.csv"
CODEX_CV = REPORTS / "nursing_necessity_patient_day_202604_lomo_cv.csv"

OUT_TRENDS = REPORTS / "nursing_necessity_202604_reconciled_1_monthly_trends.png"
OUT_CV = REPORTS / "nursing_necessity_202604_reconciled_2_lomo_validation.png"
OUT_METHODS = REPORTS / "nursing_necessity_202604_reconciled_3_method_comparison.png"
OUT_FINAL = REPORTS / "nursing_necessity_202604_reconciled_4_final_adjusted_ci.png"
OUT_SUMMARY = REPORTS / "nursing_necessity_202604_reconciled_visual_summary.md"
OUT_HANDOFF = REPORTS / "nursing_necessity_202604_for_claude_code.md"

WARDS = ("5F", "6F")
OUTCOMES = ("I", "II")
THRESHOLD_NEW = {"I": 19.0, "II": 18.0}
THRESHOLD_OLD = {"I": 16.0, "II": 14.0}
EMERGENCY_COEF_PT = 1.48
WARD_COLOR = {"5F": "#2563EB", "6F": "#E11D27"}
WARD_FILL = {"5F": "#BFD1F6", "6F": "#F6BFC2"}

# Claude Code report values supplied by the user.  These are kept separate from
# Codex estimates so the figures clearly show model-to-model agreement/dispute.
CLAUDE = pd.DataFrame(
    [
        {"ward": "5F", "outcome": "I", "estimate_pct": 18.4, "ci_low_pct": 16.5, "ci_high_pct": 20.5},
        {"ward": "5F", "outcome": "II", "estimate_pct": 16.8, "ci_low_pct": 15.4, "ci_high_pct": 18.5},
        {"ward": "6F", "outcome": "I", "estimate_pct": 14.6, "ci_low_pct": 12.2, "ci_high_pct": 16.9},
        {"ward": "6F", "outcome": "II", "estimate_pct": 11.3, "ci_low_pct": 9.1, "ci_high_pct": 13.7},
    ]
)


def setup_font() -> None:
    plt.rcParams["font.family"] = ["Hiragino Sans", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def load_monthly_actual() -> pd.DataFrame:
    df = pd.read_csv(NURSING_CSV, parse_dates=["date"])
    df["ym"] = df["date"].dt.strftime("%Y-%m")
    monthly = (
        df[df["ward"].isin(WARDS)]
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


def codex_results() -> pd.DataFrame:
    return pd.read_csv(CODEX_RESULTS)


def result_row(df: pd.DataFrame, ward: str, outcome: str) -> pd.Series:
    return df[(df["ward"].eq(ward)) & (df["outcome"].eq(outcome))].iloc[0]


def plot_monthly_trends(monthly: pd.DataFrame, codex: pd.DataFrame) -> None:
    order = [
        ("5F", "I", "5F 病棟 — 必要度I"),
        ("5F", "II", "5F 病棟 — 必要度II"),
        ("6F", "I", "6F 病棟 — 必要度I"),
        ("6F", "II", "6F 病棟 — 必要度II"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(14, 8.2))
    axes = axes.ravel()
    months = sorted(monthly["ym"].unique()) + ["2026-04"]
    x_actual = np.arange(len(months) - 1)
    x_est = len(months) - 1

    for ax, (ward, outcome, title) in zip(axes, order):
        col = f"{outcome}_rate_pct"
        sub = monthly[monthly["ward"].eq(ward)].sort_values("ym")
        codex_est = float(result_row(codex, ward, outcome)["estimate_pct"])
        claude_est = float(result_row(CLAUDE, ward, outcome)["estimate_pct"])
        threshold = THRESHOLD_NEW[outcome]

        ax.plot(x_actual, sub[col], color=WARD_COLOR[ward], marker="o", linewidth=2.2, label=f"{ward} 実測")
        ax.plot([x_actual[-1], x_est], [sub[col].iloc[-1], codex_est], color="#64748B", linestyle="--", linewidth=1.1)
        ax.scatter([x_est], [codex_est], s=360, color="black", marker="*", zorder=5, label=f"Codex = {codex_est:.1f}%")
        ax.scatter(
            [x_est - 0.12],
            [claude_est],
            s=90,
            facecolor="white",
            edgecolor="#111827",
            marker="D",
            linewidth=1.5,
            zorder=6,
            label=f"Claude = {claude_est:.1f}%",
        )
        ax.axhline(threshold, color="#EF4444", linestyle="--", linewidth=1.35, label=f"新基準 {threshold:.0f}%")
        ax.axhline(THRESHOLD_OLD[outcome], color="#94A3B8", linestyle=":", linewidth=1.2, label=f"旧基準 {THRESHOLD_OLD[outcome]:.0f}%")
        ax.set_title(title, fontsize=12, weight="bold")
        ax.set_ylabel("該当患者割合 rate1 (%)")
        ax.set_xticks(np.arange(len(months)))
        ax.set_xticklabels(months, rotation=50, ha="right", fontsize=8)
        ax.set_ylim(4, max(25, sub[col].max() + 2))
        ax.grid(True, alpha=0.25)
        ax.legend(fontsize=7.5, loc="lower left")

        diff = codex_est - claude_est
        ax.text(
            0.98,
            0.05,
            f"差 Codex-Claude {diff:+.1f}pt",
            transform=ax.transAxes,
            ha="right",
            va="bottom",
            color="#334155",
            fontsize=9,
            weight="bold",
            bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="#CBD5E1"),
        )

    fig.suptitle(
        "看護必要度 月次推移（実測12ヶ月 + 2026-04 推定値）\n"
        "黒星=Codex患者日モデル / 白ダイヤ=Claude Ridgeモデル（いずれも救急係数加算前 rate1）",
        fontsize=13,
        weight="bold",
        y=0.98,
    )
    fig.text(
        0.5,
        0.02,
        "※ 4月値は推定値。新基準判定では別途、救急患者応需係数 +1.48pt を加算して割合指数を見る。",
        ha="center",
        fontsize=9,
        bbox=dict(boxstyle="round,pad=0.35", facecolor="#FFF7D6", edgecolor="#F59E0B"),
    )
    fig.tight_layout(rect=[0, 0.06, 1, 0.93])
    fig.savefig(OUT_TRENDS, dpi=220)
    plt.close(fig)


def plot_lomo_validation() -> None:
    cv = pd.read_csv(CODEX_CV)
    overall_mae = cv["residual_pct"].abs().mean()
    mae_by_outcome = cv.groupby("outcome")["residual_pct"].apply(lambda s: s.abs().mean())
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
    ax1.set_ylabel("Codex LOMO-CV 推定値 (%)")
    ax1.set_title("散布図: 実測 vs 推定 (n=48)", weight="bold")
    ax1.grid(True, alpha=0.25)
    ax1.legend(fontsize=8, loc="lower right")
    ax1.text(
        0.03,
        0.95,
        f"全体 MAE: {overall_mae:.2f} pt\nI: {mae_by_outcome['I']:.2f} pt / II: {mae_by_outcome['II']:.2f} pt\n中央値: {median_abs:.2f} pt\n最大: {max_abs:.2f} pt",
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
    ax2.set_xticklabels([str(m)[:4] + "-" + str(m)[4:] for m in months], rotation=45, ha="right", fontsize=8)
    ax2.set_ylabel("絶対誤差 (pt)")
    ax2.set_title("月別 平均絶対誤差（病棟別）", weight="bold")
    ax2.grid(axis="y", alpha=0.25)
    ax2.legend(fontsize=9)

    fig.suptitle(
        "Codex患者日モデルの LOMO-CV 検証\n"
        "各月を未知としてホールドアウトし、残り11ヶ月で学習して実測と比較",
        fontsize=13,
        weight="bold",
        y=0.98,
    )
    fig.text(
        0.5,
        0.03,
        "※ Claude RidgeのII=2.59ptは全期間で特徴選択後にLOOCVした値として再現。fold内特徴選択では約3.01pt。",
        ha="center",
        color="#DC2626",
        fontsize=10,
        weight="bold",
        bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor="#DC2626"),
    )
    fig.tight_layout(rect=[0, 0.08, 1, 0.90])
    fig.savefig(OUT_CV, dpi=220)
    plt.close(fig)


def plot_method_comparison() -> None:
    methods = pd.DataFrame(
        [
            {"label": "Claude Ridge I\n報告値", "value": 2.96, "color": "#60A5FA"},
            {"label": "Claude Ridge II\n報告値", "value": 2.59, "color": "#60A5FA"},
            {"label": "Claude Ridge II\nfold内特徴選択", "value": 3.01, "color": "#93C5FD"},
            {"label": "Codex 患者日 I\nLOMO-CV", "value": 3.41, "color": "#10B981"},
            {"label": "Codex 患者日 II\nLOMO-CV", "value": 3.16, "color": "#10B981"},
        ]
    )
    features = pd.DataFrame(
        [
            {"feature": "ii_a_項目13_high_ratio", "corr_i": -0.526, "corr_ii": -0.629},
            {"feature": "i_a_n_records", "corr_i": 0.564, "corr_ii": 0.578},
            {"feature": "ii_a_n_records", "corr_i": 0.564, "corr_ii": 0.578},
            {"feature": "denominator_days", "corr_i": 0.564, "corr_ii": 0.578},
            {"feature": "b_n_records", "corr_i": 0.564, "corr_ii": 0.573},
        ]
    )
    features["max_abs_corr"] = features[["corr_i", "corr_ii"]].abs().max(axis=1)
    features = features.sort_values("max_abs_corr")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6.2))
    ax1.barh(methods["label"].iloc[::-1], methods["value"].iloc[::-1], color=methods["color"].iloc[::-1], edgecolor="#334155")
    for i, value in enumerate(methods["value"].iloc[::-1]):
        ax1.text(value + 0.05, i, f"{value:.2f} pt", va="center", fontsize=9)
    ax1.set_xlabel("LOOCV MAE (pt、小さいほど良い)")
    ax1.set_title("推定手法の精度比較", weight="bold")
    ax1.grid(axis="x", alpha=0.25)
    ax1.set_xlim(0, 4.2)

    y = np.arange(len(features))
    ax2.barh(y - 0.18, features["corr_i"], height=0.34, color="#2563EB", alpha=0.85, label="必要度I")
    ax2.barh(y + 0.18, features["corr_ii"], height=0.34, color="#E11D27", alpha=0.85, label="必要度II")
    ax2.axvline(0, color="#334155", linewidth=1.0)
    ax2.set_yticks(y)
    ax2.set_yticklabels(features["feature"], fontsize=9)
    ax2.set_xlabel("単変数相関 r")
    ax2.set_title("Claude式Ridgeで効いたH特徴量", weight="bold")
    ax2.grid(axis="x", alpha=0.25)
    ax2.legend(fontsize=9)

    fig.suptitle(
        "手法比較と特徴量解釈\n"
        "ASS0021_項目13 はHn列番号であり、公式仕様上はB13ではなくペイロード4相当",
        fontsize=13,
        weight="bold",
        y=0.98,
    )
    fig.text(
        0.5,
        0.03,
        "解釈メモ: ASS0013=A項目、ASS0021=B項目、TAR0010=判定対象。ASS0021_項目13は食事摂取（患者状態）全介助のproxyと読むのが自然。",
        ha="center",
        fontsize=9,
        color="#F59E0B",
        weight="bold",
        bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor="#F59E0B"),
    )
    fig.tight_layout(rect=[0, 0.08, 1, 0.90])
    fig.savefig(OUT_METHODS, dpi=220)
    plt.close(fig)


def plot_final_adjusted(codex: pd.DataFrame) -> None:
    order = [
        ("5F", "I", "5F 必要度I"),
        ("5F", "II", "5F 必要度II"),
        ("6F", "I", "6F 必要度I"),
        ("6F", "II", "6F 必要度II"),
    ]
    fig, ax = plt.subplots(figsize=(12.5, 7.0))
    y = np.arange(len(order))

    for i, (ward, outcome, label) in enumerate(order):
        c = result_row(codex, ward, outcome)
        q = result_row(CLAUDE, ward, outcome)
        c_est = float(c["estimate_pct"]) + EMERGENCY_COEF_PT
        c_low = float(c["cv_pi_low_pct"]) + EMERGENCY_COEF_PT
        c_high = float(c["cv_pi_high_pct"]) + EMERGENCY_COEF_PT
        c_inner_low = float(c["cluster_ci_low_pct"]) + EMERGENCY_COEF_PT
        c_inner_high = float(c["cluster_ci_high_pct"]) + EMERGENCY_COEF_PT
        q_est = float(q["estimate_pct"]) + EMERGENCY_COEF_PT
        q_low = float(q["ci_low_pct"]) + EMERGENCY_COEF_PT
        q_high = float(q["ci_high_pct"]) + EMERGENCY_COEF_PT
        threshold = THRESHOLD_NEW[outcome]
        gap = c_est - threshold
        status = "達成圏" if gap >= 0 else ("境界域" if gap >= -2.0 else "未達")

        ax.barh(i, c_high - c_low, left=c_low, color=WARD_FILL[ward], edgecolor=WARD_FILL[ward], alpha=0.45, height=0.58)
        ax.barh(i, c_inner_high - c_inner_low, left=c_inner_low, color=WARD_FILL[ward], edgecolor=WARD_COLOR[ward], alpha=0.9, height=0.18)
        ax.plot([q_low, q_high], [i + 0.24, i + 0.24], color="#111827", linewidth=3, solid_capstyle="butt")
        ax.scatter(c_est, i, s=115, color=WARD_COLOR[ward], edgecolor="black", zorder=4, label="Codex" if i == 0 else None)
        ax.scatter(q_est, i + 0.24, s=80, marker="D", facecolor="white", edgecolor="#111827", linewidth=1.5, zorder=5, label="Claude" if i == 0 else None)
        ax.text(
            c_est,
            i - 0.34,
            f"Codex {c_est:.1f}%",
            ha="center",
            va="center",
            fontsize=10,
            weight="bold",
            color=WARD_COLOR[ward],
        )
        ax.text(
            q_est,
            i + 0.48,
            f"Claude {q_est:.1f}%",
            ha="center",
            va="center",
            fontsize=9,
            weight="bold",
            color="#111827",
        )
        ax.text(
            31.7,
            i,
            f"{status} ({gap:+.1f}pt)",
            ha="center",
            va="center",
            fontsize=10,
            weight="bold",
            color="#047857" if gap >= 0 else "#DC2626",
            bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="#F59E0B"),
        )

    ax.axvline(THRESHOLD_NEW["I"], color="#EF4444", linestyle="--", linewidth=1.5, label="必要度I 新基準 19%")
    ax.axvline(THRESHOLD_NEW["II"], color="#F59E0B", linestyle=":", linewidth=1.5, label="必要度II 新基準 18%")
    ax.set_yticks(y)
    ax.set_yticklabels([label for _, _, label in order], fontsize=11, weight="bold")
    ax.invert_yaxis()
    ax.set_xlim(5, 35)
    ax.set_xlabel("割合指数 = rate1 + 救急患者応需係数1.48pt (%)")
    ax.grid(axis="x", alpha=0.25)
    ax.legend(loc="lower right", fontsize=9)
    ax.set_title(
        "2026-04 看護必要度 推定値 + 救急係数 + 95%レンジ\n"
        "丸=Codex患者日モデル / 白ダイヤ=Claude Ridgeモデル",
        fontsize=13,
        weight="bold",
    )
    note = (
        "図の読み方\n"
        "Codex: 薄帯=LOMO-CV補正95%予測レンジ、濃帯=患者クラスタ95%CI。Claude: 黒線=Bootstrap 95%CI。\n"
        "これは管理用推計。施設基準の最終判定にはDPCデータ提出支援ツールによる確定値が必要。"
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


def write_markdown(codex: pd.DataFrame) -> None:
    cv = pd.read_csv(CODEX_CV)
    mae_i = cv[cv["outcome"].eq("I")]["residual_pct"].abs().mean()
    mae_ii = cv[cv["outcome"].eq("II")]["residual_pct"].abs().mean()
    overall_mae = cv["residual_pct"].abs().mean()

    summary_lines = [
        "# 2026-04 看護必要度 Codex-Claude 突合版 可視化サマリー",
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
        "| 病棟 | 区分 | Codex rate1 | Claude rate1 | Codex 割合指数 | Claude 割合指数 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for _, row in codex.iterrows():
        q = result_row(CLAUDE, row["ward"], row["outcome"])
        summary_lines.append(
            f"| {row['ward']} | 必要度{row['outcome']} | {row['estimate_pct']:.1f}% | "
            f"{q['estimate_pct']:.1f}% | {row['estimate_pct'] + EMERGENCY_COEF_PT:.1f}% | "
            f"{q['estimate_pct'] + EMERGENCY_COEF_PT:.1f}% |"
        )
    OUT_SUMMARY.write_text("\n".join(summary_lines), encoding="utf-8")

    handoff_lines = [
        "# CodexからClaude Codeへの突合報告: 2026-04 看護必要度推定",
        "",
        "Claudeさん、共有いただいた推定結果をこちらでも突合しました。結論からいうと、方向性はかなり一致しています。ただしHファイル解釈で1点、重要な訂正があります。",
        "",
        "## 1. Hファイル解釈",
        "",
        "- `ASS0013` は一般病棟用 必要度IのA項目評価として扱ってよいです。",
        "- `ASS0021` は必要度IIのA項目ではなく、公式仕様上は一般病棟用 必要度I/II共通のB項目「患者の状況等」です。",
        "- `TAR0010` は重症度、医療・看護必要度の判定対象です。",
        "- `ASS0021_項目13_high_ratio` はHn列番号の項目13であり、評価票のB13そのものではありません。Hn仕様のペイロード対応で見ると、`項目13` はペイロード4、つまりB項目の「食事摂取（患者の状態）」に相当すると読むのが自然です。",
        "",
        "## 2. 分母確認",
        "",
        "ASS0013/ASS0021の患者日数は確定看護必要度の分母とほぼ一致しました。ただし完全一致ではなく、最大差は2025-05 5Fの-8患者日でした。報告表現は「ほぼ一致、最大8患者日差」が安全です。",
        "",
        "## 3. 直接判定",
        "",
        "H項目合計だけの直接判定は再現性が低いことを確認しました。必要度Iは相関およそ0.50、必要度IIはおよそ-0.15でした。2020年度改定以降、A項目の一部とC項目はEFとの結合が必要なので、H単体ではI/IIの基準該当割合を再構成できない、という説明でよいと思います。",
        "",
        "## 4. 手法とLOOCV",
        "",
        f"- Codex: Hn患者日 + En/Fn処置名proxyを使った集計制約付きロジスティック回帰。LOMO-CV MAEは全体{overall_mae:.2f}pt、必要度I {mae_i:.2f}pt、必要度II {mae_ii:.2f}pt。",
        "- Claude Ridge: こちらで再実装したところ、必要度Iの点推定はほぼ完全再現しました。必要度IIのMAE 2.59ptは、全期間で相関上位3特徴を先に固定してからLOOCVすると再現しました。特徴選択まで各fold内で行う厳密LOOCVでは約3.01ptでした。少し楽観補正が入っている可能性があります。",
        "",
        "## 5. 推定値比較",
        "",
        "| 病棟 | 必要度 | Claude rate1 | Claude 95%CI | Codex rate1 | Codex CV補正95%レンジ | Codex +1.48pt |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in codex.iterrows():
        q = result_row(CLAUDE, row["ward"], row["outcome"])
        handoff_lines.append(
            f"| {row['ward']} | {row['outcome']} | {q['estimate_pct']:.1f}% | "
            f"{q['ci_low_pct']:.1f}-{q['ci_high_pct']:.1f}% | {row['estimate_pct']:.1f}% | "
            f"{row['cv_pi_low_pct']:.1f}-{row['cv_pi_high_pct']:.1f}% | "
            f"{row['estimate_pct'] + EMERGENCY_COEF_PT:.1f}% |"
        )
    handoff_lines.extend(
        [
            "",
            "## 6. 共同で言える結論",
            "",
            "- 5Fは必要度Iは達成圏、必要度IIは境界域です。確定値待ちですが、運用上はぎりぎりラインとして扱うのが妥当です。",
            "- 6Fは必要度I/IIとも未達リスクが高いです。特に必要度IIは両モデルで厳しい方向に一致しています。",
            "- 4月値は管理用推計であり、施設基準判定には使用不可。DPCデータ提出支援ツールで確定値が出るまでは方向性把握と病棟運用判断に限定します。",
            "",
            "## 7. 可視化ファイル",
            "",
            f"- 月次推移: `{OUT_TRENDS}`",
            f"- LOMO-CV検証: `{OUT_CV}`",
            f"- 手法比較: `{OUT_METHODS}`",
            f"- 最終推計: `{OUT_FINAL}`",
            "",
            "参考: 厚労省 DPC説明資料 R08 Hファイル仕様、PRRISM DPCデータ解説 Hファイル。",
        ]
    )
    OUT_HANDOFF.write_text("\n".join(handoff_lines), encoding="utf-8")


def main() -> int:
    setup_font()
    REPORTS.mkdir(parents=True, exist_ok=True)
    monthly = load_monthly_actual()
    codex = codex_results()
    plot_monthly_trends(monthly, codex)
    plot_lomo_validation()
    plot_method_comparison()
    plot_final_adjusted(codex)
    write_markdown(codex)
    for path in (OUT_TRENDS, OUT_CV, OUT_METHODS, OUT_FINAL, OUT_SUMMARY, OUT_HANDOFF):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
