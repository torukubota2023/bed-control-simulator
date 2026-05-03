"""Patient-day weak-supervision estimate for 2026-04 nursing necessity.

This is a stronger alternative to the month-level similarity estimator.  It
uses Hn patient-days plus En/Fn procedure-name proxies as patient-day features,
but learns only from the official month x ward aggregate nursing-necessity
rates.  No patient-level rows are written to disk.
"""

from __future__ import annotations

import argparse
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MONTHLY_DIR = Path(
    "/Users/torukubota/Desktop/Ｈn_En_Fn/csv_no_insurance_number/monthly_merged"
)
DEFAULT_NURSING_CSV = ROOT / "data" / "nursing_necessity_2025fy.csv"
DEFAULT_OUT_PREFIX = ROOT / "reports" / "nursing_necessity_patient_day_202604"

TRAIN_START_YM = "202504"
TRAIN_END_YM = "202603"
TARGET_YM = "202604"
WARDS = ("5F", "6F")
OUTCOMES = ("I", "II")
RANDOM_SEED = 20260430

THRESHOLD_NEW = {"I": 0.19, "II": 0.18}
THRESHOLD_LEGACY = {"I": 0.16, "II": 0.14}

ITEM_COLS = [f"項目{i:02d}" for i in range(9, 21)]

KEYWORD_GROUPS: dict[str, list[str]] = {
    "oxygen": ["酸素", "人工呼吸", "ＮＰＰＶ", "NPPV", "ＣＰＡＰ", "CPAP"],
    "monitor": ["呼吸心拍監視", "監視及び管理"],
    "injection": ["点滴", "静注", "注射", "輸液", "シリンジ", "中心静脈"],
    "transfusion": ["輸血", "赤血球", "血小板", "血漿"],
    "endoscopy": ["内視鏡", "ＥＲＣＰ", "ERCP", "気管支鏡", "ＥＢＵＳ", "EBUS", "経食道"],
    "c_proc": [
        "中心静脈",
        "腰椎穿刺",
        "ＰＥＧ",
        "PEG",
        "胃瘻",
        "ＰＴＣＤ",
        "PTCD",
        "ＣＡＲＴ",
        "CART",
        "ステント",
        "ドレーン",
        "血液濾過",
        "エンドトキシン",
        "吸着",
    ],
    "surgery": ["手術", "麻酔"],
    "severe": ["喀痰吸引", "経鼻胃管", "褥瘡", "創傷", "常時、監視"],
    "adl": ["ＡＤＬ", "トイレ", "移乗", "ベッド上", "食事"],
}

MODEL_FEATURES = [
    "ward_6f",
    "log_stay_day",
    "phase_1_3",
    "phase_4_7",
    "phase_8_14",
    "phase_15p",
    "ef_line_count",
    "kw_oxygen_count",
    "kw_monitor_count",
    "kw_injection_count",
    "kw_transfusion_count",
    "kw_endoscopy_count",
    "kw_c_proc_count",
    "kw_surgery_count",
    "kw_severe_count",
    "kw_adl_count",
    "ass13_項目10",
    "ass13_項目11",
    "ass13_項目15",
    "ass13_項目16",
    "ass13_項目17",
    "ass21_項目10",
    "ass21_項目11",
    "ass21_項目13",
    "ass21_項目15",
    "ass21_項目16",
    "ass21_項目17",
    "ass21_項目19",
]


@dataclass(frozen=True)
class FitArtifacts:
    beta: np.ndarray
    mean: np.ndarray
    scale: np.ndarray
    features: list[str]


def normalize_ward(value: object) -> str:
    text = str(value).strip()
    return text.replace("５Ｆ", "5F").replace("６Ｆ", "6F").replace("５階", "5F").replace("６階", "6F")


def load_targets(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"])
    df["ym"] = df["date"].dt.strftime("%Y%m")
    out = (
        df[df["ward"].isin(WARDS)]
        .groupby(["ym", "ward"], as_index=False)
        .agg(
            I_pass=("I_pass1", "sum"),
            I_total=("I_total", "sum"),
            II_pass=("II_pass1", "sum"),
            II_total=("II_total", "sum"),
        )
    )
    out["I_rate"] = out["I_pass"] / out["I_total"]
    out["II_rate"] = out["II_pass"] / out["II_total"]
    return out


def build_patient_day_table(monthly_dir: Path) -> pd.DataFrame:
    frames = []
    for fp in sorted(monthly_dir.glob("merged_470116619_*.csv")):
        ym = fp.stem.split("_")[-1]
        if ym < TRAIN_START_YM or ym > TARGET_YM:
            continue
        frames.append(build_one_month(fp, ym))
    if not frames:
        raise FileNotFoundError(f"No monthly files found in {monthly_dir}")
    return pd.concat(frames, ignore_index=True)


def build_one_month(fp: Path, ym: str) -> pd.DataFrame:
    df = pd.read_csv(fp, dtype=str)
    h = df[df["ファイル種別"].eq("Hn")].copy()
    h["ward"] = h["項目02"].map(normalize_ward)
    h = h[h["ward"].isin(WARDS)]
    h["pid"] = h["項目03"].astype(str).str.strip()
    h["date"] = h["項目06"].astype(str).str.strip()
    h["rec"] = h["項目07"].astype(str).str.strip()
    for col in ITEM_COLS:
        h[col] = pd.to_numeric(h[col], errors="coerce").fillna(0)

    base = (
        h[h["rec"].eq("ASS0013")][["pid", "date", "ward", "項目04", "項目05", *ITEM_COLS]]
        .drop_duplicates(["pid", "date", "ward"])
        .copy()
    )
    base["ym"] = ym
    base["eval_date"] = pd.to_datetime(base["date"], format="%Y%m%d", errors="coerce")
    base["admit_date"] = pd.to_datetime(base["項目05"], format="%Y%m%d", errors="coerce")
    stay_day = (base["eval_date"] - base["admit_date"]).dt.days + 1
    base["stay_day"] = stay_day.clip(lower=1).fillna(1)
    base["log_stay_day"] = np.log1p(base["stay_day"])
    base["phase_1_3"] = (base["stay_day"] <= 3).astype(float)
    base["phase_4_7"] = base["stay_day"].between(4, 7).astype(float)
    base["phase_8_14"] = base["stay_day"].between(8, 14).astype(float)
    base["phase_15p"] = (base["stay_day"] >= 15).astype(float)
    base["ward_6f"] = (base["ward"] == "6F").astype(float)
    base = base.rename(columns={col: f"ass13_{col}" for col in ITEM_COLS})

    for rec, prefix in (("ASS0021", "ass21"), ("TAR0010", "tar10")):
        sub = (
            h[h["rec"].eq(rec)][["pid", "date", "ward", *ITEM_COLS]]
            .drop_duplicates(["pid", "date", "ward"])
            .rename(columns={col: f"{prefix}_{col}" for col in ITEM_COLS})
        )
        base = base.merge(sub, on=["pid", "date", "ward"], how="left")

    ef_features = aggregate_ef_features(df, base[["pid", "date", "ward"]].drop_duplicates())
    base = base.merge(ef_features, on=["pid", "date", "ward"], how="left")
    for col in base.columns:
        if col.startswith(("kw_", "ass21_", "tar10_")) or col == "ef_line_count":
            base[col] = pd.to_numeric(base[col], errors="coerce").fillna(0)
    return base


def aggregate_ef_features(df: pd.DataFrame, keys: pd.DataFrame) -> pd.DataFrame:
    ef = df[df["ファイル種別"].isin(["En", "Fn"])].copy()
    ef["pid"] = ef["項目02"].astype(str).str.strip()
    ef["date"] = ef["項目04"].astype(str).str.strip()
    ef["name"] = ""
    en_mask = ef["ファイル種別"].eq("En")
    ef.loc[en_mask, "name"] = ef.loc[en_mask, "項目10"].astype(str).str.strip()
    ef.loc[~en_mask, "name"] = ef.loc[~en_mask, "項目11"].astype(str).str.strip()
    ef = ef.merge(keys, on=["pid", "date"], how="inner")

    agg = ef.groupby(["pid", "date", "ward"]).size().rename("ef_line_count").reset_index()
    for name, words in KEYWORD_GROUPS.items():
        pattern = "|".join(re.escape(word) for word in words)
        matched = ef["name"].str.contains(pattern, regex=True, na=False)
        tmp = (
            ef[matched]
            .groupby(["pid", "date", "ward"])
            .size()
            .rename(f"kw_{name}_count")
            .reset_index()
        )
        agg = agg.merge(tmp, on=["pid", "date", "ward"], how="left")
    return agg


def sigmoid(values: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(values, -30, 30)))


def prepare_matrix(df: pd.DataFrame, features: list[str]) -> np.ndarray:
    return df[features].astype(float).fillna(0).to_numpy(dtype=float)


def fit_grouped_logistic(
    patient_days: pd.DataFrame,
    targets: pd.DataFrame,
    outcome: str,
    train_groups: set[tuple[str, str]],
    features: list[str],
    l2: float = 0.05,
    learning_rate: float = 0.05,
    steps: int = 1400,
) -> FitArtifacts:
    target_rates = targets.set_index(["ym", "ward"])[f"{outcome}_rate"]
    mask = patient_days[["ym", "ward"]].apply(tuple, axis=1).isin(train_groups).to_numpy()
    train_df = patient_days.loc[mask].copy()
    x_raw = prepare_matrix(train_df, features)
    mean = x_raw.mean(axis=0)
    scale = x_raw.std(axis=0)
    scale[scale == 0] = 1.0
    x = np.column_stack([np.ones(len(x_raw)), (x_raw - mean) / scale])

    keys = train_df[["ym", "ward"]].apply(tuple, axis=1).tolist()
    unique_keys = sorted(set(keys))
    group_map = {key: i for i, key in enumerate(unique_keys)}
    group_idx = np.array([group_map[key] for key in keys], dtype=int)
    group_n = np.bincount(group_idx).astype(float)
    y = np.array([target_rates.loc[key] for key in unique_keys], dtype=float)

    beta = np.zeros(x.shape[1], dtype=float)
    beta[0] = math.log(float(y.mean()) / (1.0 - float(y.mean())))
    m1 = np.zeros_like(beta)
    m2 = np.zeros_like(beta)
    groups = len(unique_keys)

    for step in range(1, steps + 1):
        p = sigmoid(x @ beta)
        group_mean = np.bincount(group_idx, weights=p, minlength=groups) / group_n
        group_mean = np.clip(group_mean, 1e-5, 1 - 1e-5)
        d_loss_d_mean = -(y / group_mean - (1 - y) / (1 - group_mean)) / groups
        grad_eta = d_loss_d_mean[group_idx] * p * (1 - p) / group_n[group_idx]
        grad = x.T @ grad_eta
        reg = 2.0 * l2 * beta
        reg[0] = 0.0
        grad += reg

        m1 = 0.9 * m1 + 0.1 * grad
        m2 = 0.999 * m2 + 0.001 * (grad * grad)
        beta -= learning_rate * (m1 / (1 - 0.9**step)) / (np.sqrt(m2 / (1 - 0.999**step)) + 1e-8)

    return FitArtifacts(beta=beta, mean=mean, scale=scale, features=features)


def predict_probabilities(patient_days: pd.DataFrame, artifacts: FitArtifacts) -> np.ndarray:
    x_raw = prepare_matrix(patient_days, artifacts.features)
    x = np.column_stack([np.ones(len(x_raw)), (x_raw - artifacts.mean) / artifacts.scale])
    return sigmoid(x @ artifacts.beta)


def leave_one_month_out(
    patient_days: pd.DataFrame,
    targets: pd.DataFrame,
    outcome: str,
    features: list[str],
) -> pd.DataFrame:
    rows = []
    months = sorted(targets["ym"].unique())
    all_groups = set(targets[["ym", "ward"]].apply(tuple, axis=1))
    actual = targets.set_index(["ym", "ward"])[f"{outcome}_rate"]

    for hold_month in months:
        train_groups = {group for group in all_groups if group[0] != hold_month}
        artifacts = fit_grouped_logistic(patient_days, targets, outcome, train_groups, features)
        hold_df = patient_days[patient_days["ym"].eq(hold_month)].copy()
        hold_df["pred"] = predict_probabilities(hold_df, artifacts)
        pred = hold_df.groupby(["ym", "ward"])["pred"].mean()
        for key, value in pred.items():
            rows.append(
                {
                    "outcome": outcome,
                    "ym": key[0],
                    "ward": key[1],
                    "predicted": float(value),
                    "actual": float(actual.loc[key]),
                    "residual": float(value - actual.loc[key]),
                }
            )
    return pd.DataFrame(rows)


def cluster_bootstrap_ci(
    target_df: pd.DataFrame,
    probabilities: np.ndarray,
    rng: np.random.Generator,
    iterations: int,
) -> tuple[float, float]:
    work = target_df[["pid", "date", "ward"]].copy()
    work["p"] = probabilities
    cluster_means = work.groupby("pid")["p"].mean().to_numpy(dtype=float)
    cluster_sizes = work.groupby("pid").size().to_numpy(dtype=float)
    if len(cluster_means) == 0:
        return math.nan, math.nan
    out = []
    indices = np.arange(len(cluster_means))
    for _ in range(iterations):
        sample = rng.choice(indices, size=len(indices), replace=True)
        out.append(float(np.average(cluster_means[sample], weights=cluster_sizes[sample])))
    low, high = np.quantile(out, [0.025, 0.975])
    return float(low), float(high)


def estimate(
    patient_days: pd.DataFrame,
    targets: pd.DataFrame,
    bootstrap: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    features = [feature for feature in MODEL_FEATURES if feature in patient_days.columns]
    historical_groups = set(
        targets[
            targets["ym"].between(TRAIN_START_YM, TRAIN_END_YM)
        ][["ym", "ward"]].apply(tuple, axis=1)
    )
    rng = np.random.default_rng(RANDOM_SEED)

    cv_frames = [leave_one_month_out(patient_days, targets, outcome, features) for outcome in OUTCOMES]
    cv = pd.concat(cv_frames, ignore_index=True)

    rows = []
    for outcome in OUTCOMES:
        artifacts = fit_grouped_logistic(
            patient_days=patient_days,
            targets=targets,
            outcome=outcome,
            train_groups=historical_groups,
            features=features,
            steps=1800,
        )
        target_month = patient_days[patient_days["ym"].eq(TARGET_YM)].copy()
        target_month["p"] = predict_probabilities(target_month, artifacts)

        for ward in WARDS:
            sub = target_month[target_month["ward"].eq(ward)].copy()
            estimate_value = float(sub["p"].mean())
            ci_low, ci_high = cluster_bootstrap_ci(sub, sub["p"].to_numpy(), rng, bootstrap)

            cv_sub = cv[(cv["outcome"].eq(outcome)) & (cv["ward"].eq(ward))]
            mae = float(cv_sub["residual"].abs().mean())
            rmse = float(np.sqrt(np.mean(np.square(cv_sub["residual"]))))
            pi_low = max(0.0, estimate_value - 1.96 * rmse)
            pi_high = min(1.0, estimate_value + 1.96 * rmse)
            rows.append(
                {
                    "ward": ward,
                    "outcome": outcome,
                    "estimate": estimate_value,
                    "cluster_ci_low": ci_low,
                    "cluster_ci_high": ci_high,
                    "cv_mae": mae,
                    "cv_rmse": rmse,
                    "cv_pi_low": pi_low,
                    "cv_pi_high": pi_high,
                    "patient_days": int(len(sub)),
                    "patients": int(sub["pid"].nunique()),
                    "observed_days": int(sub["date"].nunique()),
                }
            )
    results = pd.DataFrame(rows).sort_values(["ward", "outcome"]).reset_index(drop=True)
    for col in ["estimate", "cluster_ci_low", "cluster_ci_high", "cv_mae", "cv_rmse", "cv_pi_low", "cv_pi_high"]:
        results[f"{col}_pct"] = results[col] * 100
    for col in ["predicted", "actual", "residual"]:
        cv[f"{col}_pct"] = cv[col] * 100
    return results, cv


def plot_results(results: pd.DataFrame, out_png: Path) -> None:
    plt.rcParams["font.family"] = ["Hiragino Sans", "Arial Unicode MS", "DejaVu Sans"]
    order = [
        ("5F", "I", "5F 必要度I"),
        ("5F", "II", "5F 必要度II"),
        ("6F", "I", "6F 必要度I"),
        ("6F", "II", "6F 必要度II"),
    ]
    colors = {"5F": "#89A9E8", "6F": "#EE9B9B"}

    fig, ax = plt.subplots(figsize=(12, 6.8))
    for i, (ward, outcome, label) in enumerate(order):
        row = results[(results["ward"].eq(ward)) & (results["outcome"].eq(outcome))].iloc[0]
        est = row["estimate_pct"]
        low = row["cluster_ci_low_pct"]
        high = row["cluster_ci_high_pct"]
        pi_low = row["cv_pi_low_pct"]
        pi_high = row["cv_pi_high_pct"]
        ax.plot([pi_low, pi_high], [i, i], color=colors[ward], alpha=0.25, linewidth=14, solid_capstyle="butt")
        ax.plot([low, high], [i, i], color=colors[ward], alpha=0.85, linewidth=7, solid_capstyle="butt")
        ax.scatter(est, i, s=90, color="#174EA6" if ward == "5F" else "#B91C1C", zorder=4)
        ax.text(est, i + 0.27, f"{est:.1f}%", ha="center", va="center", fontsize=11, weight="bold")
        ax.text(high + 0.25, i - 0.22, f"MAE {row['cv_mae_pct']:.1f}pt", fontsize=8, color="#475569")

    ax.axvline(THRESHOLD_NEW["I"] * 100, color="#DC2626", linestyle="--", linewidth=1.4, label="必要度I 新基準 19%")
    ax.axvline(THRESHOLD_NEW["II"] * 100, color="#F97316", linestyle="--", linewidth=1.4, label="必要度II 新基準 18%")
    ax.axvline(THRESHOLD_LEGACY["I"] * 100, color="#94A3B8", linestyle=":", linewidth=1.2, label="4-5月 旧I基準 16%")
    ax.axvline(THRESHOLD_LEGACY["II"] * 100, color="#CBD5E1", linestyle=":", linewidth=1.2, label="4-5月 旧II基準 14%")
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([item[2] for item in order])
    ax.invert_yaxis()
    ax.set_xlim(0, 30)
    ax.grid(axis="x", alpha=0.25)
    ax.set_xlabel("該当患者割合 (%)")
    ax.set_title(
        "2026年4月 看護必要度 患者日モデル推計\n"
        "濃い帯=患者クラスタ95%CI / 薄い帯=LOMO-CV補正95%予測レンジ",
        fontsize=12,
        weight="bold",
        pad=16,
    )
    ax.legend(loc="lower right", fontsize=9)
    note = (
        "Hn患者日 + En/Fn処置名proxyを患者日特徴量化。教師ラベルは2025年度の月×病棟確定集計のみ。\n"
        "個票は出力しない。CIを狭く見せすぎないため、患者クラスタCIとは別にLOMO-CV補正レンジを併記。"
    )
    fig.text(
        0.05,
        0.02,
        note,
        ha="left",
        va="bottom",
        fontsize=9,
        bbox=dict(boxstyle="round,pad=0.45", facecolor="#FFF7D6", edgecolor="#F59E0B"),
    )
    fig.tight_layout(rect=[0, 0.11, 1, 0.94])
    fig.savefig(out_png, dpi=220)
    plt.close(fig)


def write_report(results: pd.DataFrame, cv: pd.DataFrame, out_md: Path, out_png: Path) -> None:
    lines = [
        "# 2026年4月 看護必要度 患者日モデル推計",
        "",
        f"![2026年4月 看護必要度 患者日モデル推計]({out_png})",
        "",
        "## 推計結果",
        "",
        "| 病棟 | 区分 | 推定値 | 患者クラスタ95%CI | LOMO-CV MAE | CV補正95%予測レンジ |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for _, row in results.iterrows():
        lines.append(
            f"| {row['ward']} | 必要度{row['outcome']} | {row['estimate_pct']:.1f}% | "
            f"{row['cluster_ci_low_pct']:.1f}-{row['cluster_ci_high_pct']:.1f}% | "
            f"{row['cv_mae_pct']:.1f}pt | {row['cv_pi_low_pct']:.1f}-{row['cv_pi_high_pct']:.1f}% |"
        )
    lines.extend(
        [
            "",
            "## モデル",
            "",
            "- 観測単位: Hn `ASS0013` を分母にした患者日。",
            "- 特徴量: 在院相対日、Hn評価項目、En/Fnの処置名キーワードproxy（酸素、注射、輸血、内視鏡、C項目候補など）。",
            "- 教師情報: 患者日ごとの真ラベルは使えないため、2025年度の月×病棟集計 `I_pass1/I_total`, `II_pass1/II_total` のみ。",
            "- 学習: 月×病棟の平均予測確率が確定割合に近づくように、集計制約付きロジスティック回帰を正則化付きで推定。小標本の弱教師ありのため、CV誤差と4月推定の安定性を見て `l2=0.05` を採用。",
            "- 妥当性: Leave-One-Month-Out CVで各月をホールドアウトし、確定値との誤差を評価。",
            "",
            "## 注意",
            "",
            "- 濃いCIは患者クラスタ再標本化のみなので狭い。月次集計しか教師ラベルがない不確実性はLOMO-CV補正レンジを見る。",
            "- DPCデータ提出支援ツールの確定値ではない。移行期間中の管理用推計。",
            "- 患者ID・患者日個票は出力していない。",
            "",
            "## LOMO-CV 詳細",
            "",
            "| 区分 | 病棟 | MAE | RMSE | 最大絶対誤差 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for (outcome, ward), sub in cv.groupby(["outcome", "ward"]):
        lines.append(
            f"| 必要度{outcome} | {ward} | {sub['residual_pct'].abs().mean():.2f}pt | "
            f"{np.sqrt(np.mean(np.square(sub['residual_pct']))):.2f}pt | "
            f"{sub['residual_pct'].abs().max():.2f}pt |"
        )
    out_md.write_text("\n".join(lines), encoding="utf-8")


def run(monthly_dir: Path, nursing_csv: Path, out_prefix: Path, bootstrap: int) -> None:
    patient_days = build_patient_day_table(monthly_dir)
    targets = load_targets(nursing_csv)
    results, cv = estimate(patient_days, targets, bootstrap)

    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    out_results = out_prefix.with_suffix(".csv")
    out_cv = out_prefix.parent / f"{out_prefix.name}_lomo_cv.csv"
    out_png = out_prefix.with_suffix(".png")
    out_md = out_prefix.with_suffix(".md")

    results.to_csv(out_results, index=False)
    cv.to_csv(out_cv, index=False)
    plot_results(results, out_png)
    write_report(results, cv, out_md, out_png)

    print(f"results: {out_results}")
    print(f"cv: {out_cv}")
    print(f"plot: {out_png}")
    print(f"report: {out_md}")
    print(
        results[
            [
                "ward",
                "outcome",
                "estimate_pct",
                "cluster_ci_low_pct",
                "cluster_ci_high_pct",
                "cv_mae_pct",
                "cv_pi_low_pct",
                "cv_pi_high_pct",
            ]
        ].to_string(index=False)
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="2026-04 看護必要度 患者日モデル推計")
    parser.add_argument("--monthly-dir", type=Path, default=DEFAULT_MONTHLY_DIR)
    parser.add_argument("--nursing-csv", type=Path, default=DEFAULT_NURSING_CSV)
    parser.add_argument("--out-prefix", type=Path, default=DEFAULT_OUT_PREFIX)
    parser.add_argument("--bootstrap", type=int, default=5000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run(args.monthly_dir, args.nursing_csv, args.out_prefix, args.bootstrap)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
