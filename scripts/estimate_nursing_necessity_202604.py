"""2026-04 nursing necessity estimator.

The DPC submission support tool is unavailable during the 2026 fee-revision
transition, so this script estimates April 2026 nursing necessity rates from:

- exact April 2025 - March 2026 nursing necessity aggregates
- the same period of admission case-mix data in the bed-control app
- April 2026 admission case-mix data

Patient identifiers are used only inside the optional Hn denominator check and
are never written to output files.
"""

from __future__ import annotations

import argparse
import math
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
DEFAULT_ADMISSION_CSV = ROOT / "data" / "past_admissions_2025fy.csv"
DEFAULT_OUT_PREFIX = ROOT / "reports" / "nursing_necessity_estimate_202604"

TARGET_YM = "202604"
TRAIN_START_YM = "202504"
TRAIN_END_YM = "202603"
WARDS = ("5F", "6F")
OUTCOMES = ("I", "II")
K_NEIGHBORS = 6
RANDOM_SEED = 20260430

# 2026-06-01 onward thresholds used for readiness visualization.
THRESHOLD_NEW = {"I": 0.19, "II": 0.18}
THRESHOLD_LEGACY = {"I": 0.16, "II": 0.14}

# Feature weights for the distance metric.  These are deliberately simple and
# clinical-operation oriented; with 12 historical months per ward, a complex
# regression model would be too fragile.
FEATURE_WEIGHTS = {
    "admissions_per_day": 0.8,
    "emergency_transport_rate": 1.4,
    "unscheduled_rate": 1.2,
    "surgery_rate": 2.0,
    "short3_likely_rate": 2.0,
    "mean_los": 1.2,
    "median_los": 1.0,
    "dept_内科_rate": 1.5,
    "dept_循内科_rate": 1.3,
    "dept_外科_rate": 1.7,
    "dept_整形外_rate": 1.7,
    "dept_脳神外_rate": 1.2,
    "dept_麻酔科_rate": 2.0,
    "route_家庭_rate": 1.0,
    "route_施設入_rate": 1.0,
    "route_他病院_rate": 1.0,
}


@dataclass(frozen=True)
class EstimateResult:
    ward: str
    outcome: str
    estimate: float
    ci_low: float
    ci_high: float
    projected_denominator: float
    observed_days: int | None
    admission_cutoff_day: int
    loo_mae: float


def normalize_ward(value: object) -> str:
    text = str(value).strip()
    return (
        text.replace("５Ｆ", "5F")
        .replace("６Ｆ", "6F")
        .replace("５階", "5F")
        .replace("６階", "6F")
    )


def month_days(ym: str) -> int:
    return int(pd.Period(ym, freq="M").days_in_month)


def load_nursing_targets(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"])
    df["ym"] = df["date"].dt.strftime("%Y%m")
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
    monthly["I_rate"] = monthly["I_pass"] / monthly["I_total"]
    monthly["II_rate"] = monthly["II_pass"] / monthly["II_total"]
    return monthly


def load_admission_features(path: Path, target_ym: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["admission_date"] = pd.to_datetime(df["入院日"], errors="coerce")
    df = df[df["admission_date"].notna()].copy()
    df["ym"] = df["admission_date"].dt.strftime("%Y%m")
    df["ward"] = df["病棟"].map(normalize_ward)
    df = df[df["ward"].isin(WARDS)].copy()

    df["is_emergency_transport"] = df["救急車"].astype(str).eq("有り")
    df["is_scheduled"] = df["緊急"].astype(str).eq("予定入院")
    df["has_surgery"] = df["手術"].astype(str).eq("○")
    df["los"] = pd.to_numeric(df["日数"], errors="coerce")
    df["is_short3_likely"] = df["has_surgery"] & (df["los"] <= 5)

    rows: list[dict[str, float | str | int]] = []
    for (ym, ward), sub in df.groupby(["ym", "ward"], sort=True):
        if ym == target_ym:
            observed_day = int(sub["admission_date"].dt.day.max())
        else:
            observed_day = month_days(ym)

        row: dict[str, float | str | int] = {
            "ym": ym,
            "ward": ward,
            "admissions": int(len(sub)),
            "admission_cutoff_day": observed_day,
            "admissions_per_day": len(sub) / max(observed_day, 1),
            "emergency_transport_rate": float(sub["is_emergency_transport"].mean()),
            "unscheduled_rate": float((~sub["is_scheduled"]).mean()),
            "surgery_rate": float(sub["has_surgery"].mean()),
            "short3_likely_rate": float(sub["is_short3_likely"].mean()),
            "mean_los": float(sub["los"].mean()),
            "median_los": float(sub["los"].median()),
        }

        for dept in ("内科", "循内科", "外科", "整形外", "脳神外", "麻酔科"):
            row[f"dept_{dept}_rate"] = float(sub["診療科"].astype(str).eq(dept).mean())
        for route in ("家庭", "施設入", "他病院"):
            row[f"route_{route}_rate"] = float(sub["入経路"].astype(str).eq(route).mean())

        rows.append(row)

    return pd.DataFrame(rows)


def load_hn_denominators(monthly_dir: Path, target_ym: str) -> pd.DataFrame:
    """Use Hn ASS0013 rows only to estimate available patient-day denominators."""
    fp = monthly_dir / f"merged_470116619_{target_ym}.csv"
    if not fp.exists():
        return pd.DataFrame(columns=["ym", "ward", "hn_observed_days", "hn_patient_days", "projected_denominator"])

    usecols = ["ファイル種別", "項目02", "項目03", "項目06", "項目07"]
    df = pd.read_csv(fp, dtype=str, usecols=usecols)
    h = df[df["ファイル種別"].astype(str).eq("Hn")].copy()
    h["ward"] = h["項目02"].map(normalize_ward)
    h = h[h["ward"].isin(WARDS)]
    h = h[h["項目07"].astype(str).str.strip().eq("ASS0013")]
    h["pid"] = h["項目03"].astype(str).str.strip()
    h["date"] = h["項目06"].astype(str).str.strip()

    rows = []
    for ward, sub in h.groupby("ward"):
        patient_days = sub[["pid", "date"]].drop_duplicates().shape[0]
        observed_days = int(sub["date"].nunique())
        projected = patient_days * month_days(target_ym) / max(observed_days, 1)
        rows.append(
            {
                "ym": target_ym,
                "ward": ward,
                "hn_observed_days": observed_days,
                "hn_patient_days": patient_days,
                "projected_denominator": projected,
            }
        )
    return pd.DataFrame(rows)


def feature_columns(df: pd.DataFrame) -> list[str]:
    excluded = {
        "ym",
        "ward",
        "admissions",
        "admission_cutoff_day",
        "hn_observed_days",
        "hn_patient_days",
        "projected_denominator",
        "I_total",
        "I_pass",
        "II_total",
        "II_pass",
        "I_rate",
        "II_rate",
    }
    cols = [c for c in df.columns if c not in excluded and pd.api.types.is_numeric_dtype(df[c])]
    return [c for c in cols if df[c].nunique(dropna=True) > 1]


def standardized_distance(
    train: pd.DataFrame,
    target: pd.Series,
    cols: Iterable[str],
) -> pd.Series:
    cols = list(cols)
    x = train[cols].astype(float)
    xp = target[cols].astype(float)
    med = x.median()
    x = x.fillna(med)
    xp = xp.fillna(med)
    mu = x.mean()
    sd = x.std(ddof=0).replace(0, 1)
    z = (x - mu) / sd
    zp = (xp - mu) / sd
    weights = np.array([FEATURE_WEIGHTS.get(c, 1.0) for c in cols], dtype=float)
    dist = np.sqrt((((z - zp.values) ** 2) * weights).sum(axis=1) / weights.sum())
    return pd.Series(dist, index=train.index)


def kernel_weights(distances: np.ndarray) -> np.ndarray:
    # Inverse-square kernel keeps the nearest months influential, while avoiding
    # a single-month prediction.
    weights = 1.0 / np.power(distances + 0.15, 2)
    return weights / weights.sum()


def predict_one(
    data: pd.DataFrame,
    target_row: pd.Series,
    ward: str,
    outcome: str,
    cols: list[str],
    rng: np.random.Generator,
    bootstrap: int,
) -> tuple[EstimateResult, pd.DataFrame]:
    target_col = f"{outcome}_rate"
    train = data[
        (data["ward"] == ward)
        & (data["ym"] >= TRAIN_START_YM)
        & (data["ym"] <= TRAIN_END_YM)
    ].copy()

    distances = standardized_distance(train, target_row, cols)
    nearest_idx = distances.sort_values().index[:K_NEIGHBORS]
    nearest = train.loc[nearest_idx, ["ym", "ward", target_col]].copy()
    nearest["distance"] = distances.loc[nearest_idx].to_numpy()
    nearest["similarity_weight"] = kernel_weights(nearest["distance"].to_numpy())
    nearest = nearest.rename(columns={target_col: "actual_rate"})

    rates = nearest["actual_rate"].to_numpy(dtype=float)
    weights = nearest["similarity_weight"].to_numpy(dtype=float)
    ward_mean = float(train[target_col].mean())
    estimate = 0.9 * float(np.dot(weights, rates)) + 0.1 * ward_mean

    loo_residuals = leave_one_out_residuals(train, target_col, cols)
    projected_denominator = float(
        target_row.get("projected_denominator")
        or target_row.get("hn_patient_days")
        or target_row.get(f"{outcome}_total")
        or 1200
    )

    samples = []
    for _ in range(bootstrap):
        sampled = rng.choice(np.arange(len(rates)), size=len(rates), replace=True, p=weights)
        boot_rate = 0.9 * float(np.mean(rates[sampled])) + 0.1 * ward_mean
        if len(loo_residuals) > 0:
            boot_rate += float(rng.choice(loo_residuals))
        boot_rate = float(np.clip(boot_rate, 0.001, 0.999))
        n = max(int(round(projected_denominator)), 1)
        samples.append(rng.binomial(n, boot_rate) / n)

    low, high = np.quantile(samples, [0.025, 0.975])
    result = EstimateResult(
        ward=ward,
        outcome=outcome,
        estimate=estimate,
        ci_low=float(low),
        ci_high=float(high),
        projected_denominator=projected_denominator,
        observed_days=(
            int(target_row["hn_observed_days"])
            if not pd.isna(target_row.get("hn_observed_days", np.nan))
            else None
        ),
        admission_cutoff_day=int(target_row.get("admission_cutoff_day", 0)),
        loo_mae=float(np.mean(np.abs(loo_residuals))) if len(loo_residuals) else math.nan,
    )
    nearest.insert(0, "outcome", outcome)
    return result, nearest


def leave_one_out_residuals(train: pd.DataFrame, target_col: str, cols: list[str]) -> np.ndarray:
    residuals: list[float] = []
    for idx, row in train.iterrows():
        other = train.drop(index=idx)
        distances = standardized_distance(other, row, cols)
        nearest_idx = distances.sort_values().index[: min(K_NEIGHBORS - 1, len(other))]
        nearest_rates = other.loc[nearest_idx, target_col].to_numpy(dtype=float)
        nearest_dist = distances.loc[nearest_idx].to_numpy(dtype=float)
        weights = kernel_weights(nearest_dist)
        pred = 0.9 * float(np.dot(weights, nearest_rates)) + 0.1 * float(other[target_col].mean())
        residuals.append(float(row[target_col] - pred))
    arr = np.array(residuals, dtype=float)
    return arr - arr.mean()


def build_plot(results: pd.DataFrame, out_png: Path) -> None:
    plt.rcParams["font.family"] = [
        "Hiragino Sans",
        "Yu Gothic",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    order = [
        ("5F", "I", "5F 必要度I"),
        ("5F", "II", "5F 必要度II"),
        ("6F", "I", "6F 必要度I"),
        ("6F", "II", "6F 必要度II"),
    ]
    colors = {"5F": "#9DB9F2", "6F": "#F4A3A3"}
    y = np.arange(len(order))

    fig, ax = plt.subplots(figsize=(12, 6.8))
    for i, (ward, outcome, label) in enumerate(order):
        row = results[(results["ward"] == ward) & (results["outcome"] == outcome)].iloc[0]
        est = row["estimate_pct"]
        low = row["ci_low_pct"]
        high = row["ci_high_pct"]
        ax.barh(i, high - low, left=low, height=0.58, color=colors[ward], alpha=0.55)
        ax.scatter(est, i, s=88, color="#1F4E9A" if ward == "5F" else "#B91C1C", zorder=3)
        ax.text(est, i - 0.34, f"{est:.1f}%", ha="center", va="center", fontsize=10, weight="bold")
        ax.text(low, i - 0.28, f"{low:.1f}", ha="right", va="center", fontsize=8, color=colors[ward])
        ax.text(high, i - 0.28, f"{high:.1f}", ha="left", va="center", fontsize=8, color=colors[ward])

    ax.axvline(THRESHOLD_NEW["I"] * 100, color="#DC2626", linestyle="--", linewidth=1.4, label="必要度I 新基準 19%")
    ax.axvline(THRESHOLD_NEW["II"] * 100, color="#F97316", linestyle="--", linewidth=1.4, label="必要度II 新基準 18%")
    ax.axvline(THRESHOLD_LEGACY["I"] * 100, color="#94A3B8", linestyle=":", linewidth=1.2, label="4-5月 旧I基準 16%")
    ax.axvline(THRESHOLD_LEGACY["II"] * 100, color="#CBD5E1", linestyle=":", linewidth=1.2, label="4-5月 旧II基準 14%")
    ax.set_yticks(y)
    ax.set_yticklabels([label for _, _, label in order])
    ax.invert_yaxis()
    ax.set_xlim(0, 32)
    ax.set_xlabel("該当患者割合（%）")
    ax.set_title(
        "2026年4月 看護必要度推計 + 95%信頼区間\n"
        "推計方法: 2025年度確定値 × 入院属性類似月の重み付き平均",
        fontsize=13,
        weight="bold",
    )
    ax.grid(axis="x", alpha=0.25)
    ax.legend(loc="lower right", fontsize=9)

    note = (
        "注: 点は推定値、帯は95%信頼区間。DPC支援ツールによる確定値ではありません。\n"
        "学習: 2025/04-2026/03の確定必要度。特徴量: 入院数/日、救急、予定外、手術、短手3推定、LOS、診療科、入経路。\n"
        "4月入院データはアプリCSVの4/1-4/25、分母補助はmonthly_merged Hnの4/1-4/28を使用。"
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
    fig.tight_layout(rect=[0, 0.12, 1, 1])
    fig.savefig(out_png, dpi=220)
    plt.close(fig)


def write_markdown(results: pd.DataFrame, similarity: pd.DataFrame, out_md: Path, out_png: Path) -> None:
    rows = []
    for _, row in results.iterrows():
        rows.append(
            "| {ward} | 必要度{outcome} | {estimate_pct:.1f}% | {ci_low_pct:.1f}-{ci_high_pct:.1f}% | {legacy} | {new} |".format(
                ward=row["ward"],
                outcome=row["outcome"],
                estimate_pct=row["estimate_pct"],
                ci_low_pct=row["ci_low_pct"],
                ci_high_pct=row["ci_high_pct"],
                legacy="到達" if row["estimate"] >= THRESHOLD_LEGACY[row["outcome"]] else "未達",
                new="到達" if row["estimate"] >= THRESHOLD_NEW[row["outcome"]] else "未達",
            )
        )

    md = [
        "# 2026年4月 看護必要度推計",
        "",
        f"![2026年4月 看護必要度推計]({out_png})",
        "",
        "## 推計結果",
        "",
        "| 病棟 | 区分 | 推定値 | 95%信頼区間 | 4-5月旧基準 | 6/1以降新基準 |",
        "|---|---:|---:|---:|---:|---:|",
        *rows,
        "",
        "## 方法",
        "",
        "1. `data/nursing_necessity_2025fy.csv` から、2025年4月-2026年3月の病棟別・必要度I/IIの確定月次割合を作成した。",
        "2. `data/past_admissions_2025fy.csv` から、同じ月×病棟で入院属性ベクトルを作成した。特徴量は入院数/日、救急搬送、予定外入院、手術、短手3推定、平均/中央値LOS、診療科構成、入経路構成。",
        "3. 2026年4月の入院属性ベクトルを作成し、各病棟ごとに2025年度12ヶ月の中から最も近い6ヶ月を抽出した。",
        "4. 手術・短手3・麻酔科・外科/整形外科・内科・救急・LOSをやや重くした標準化距離で類似度を計算し、逆二乗カーネルで重み付き平均した。",
        "5. 95%信頼区間は、類似月の重み付きブートストラップ、leave-one-out残差、Hn患者日分母に基づく二項揺らぎを合わせて推定した。",
        "",
        "## 注意",
        "",
        "- これはDPCデータ提出支援ツールによる確定計算ではなく、移行期間の管理用推計。",
        "- 4月入院データはアプリCSV上 2026-04-25 まで。`monthly_merged` のHn分母補助は 2026-04-28 まで。",
        "- 患者IDや個票は出力していない。",
        "",
        "## 類似月",
        "",
    ]

    for (ward, outcome), sub in similarity.groupby(["ward", "outcome"]):
        md.append(f"### {ward} 必要度{outcome}")
        md.append("")
        md.append("| 類似月 | 確定実績 | 距離 | 重み |")
        md.append("|---|---:|---:|---:|")
        for _, row in sub.iterrows():
            md.append(
                f"| {row['ym']} | {row['actual_rate'] * 100:.1f}% | "
                f"{row['distance']:.3f} | {row['similarity_weight']:.3f} |"
            )
        md.append("")

    out_md.write_text("\n".join(md), encoding="utf-8")


def run(
    monthly_dir: Path,
    nursing_csv: Path,
    admission_csv: Path,
    out_prefix: Path,
    target_ym: str,
    bootstrap: int,
) -> None:
    targets = load_nursing_targets(nursing_csv)
    features = load_admission_features(admission_csv, target_ym)
    denominators = load_hn_denominators(monthly_dir, target_ym)

    data = features.merge(targets, on=["ym", "ward"], how="left")
    data = data.merge(denominators, on=["ym", "ward"], how="left")
    cols = feature_columns(data)

    target_rows = data[(data["ym"] == target_ym) & (data["ward"].isin(WARDS))]
    rng = np.random.default_rng(RANDOM_SEED)
    results: list[EstimateResult] = []
    nearest_rows: list[pd.DataFrame] = []

    for ward in WARDS:
        target_row = target_rows[target_rows["ward"] == ward].iloc[0]
        for outcome in OUTCOMES:
            result, nearest = predict_one(
                data=data,
                target_row=target_row,
                ward=ward,
                outcome=outcome,
                cols=cols,
                rng=rng,
                bootstrap=bootstrap,
            )
            results.append(result)
            nearest_rows.append(nearest)

    result_df = pd.DataFrame([r.__dict__ for r in results])
    result_df["estimate_pct"] = result_df["estimate"] * 100
    result_df["ci_low_pct"] = result_df["ci_low"] * 100
    result_df["ci_high_pct"] = result_df["ci_high"] * 100
    result_df["loo_mae_pct"] = result_df["loo_mae"] * 100
    result_df = result_df.sort_values(["ward", "outcome"]).reset_index(drop=True)

    similarity_df = pd.concat(nearest_rows, ignore_index=True)
    similarity_df = similarity_df[["ward", "outcome", "ym", "actual_rate", "distance", "similarity_weight"]]

    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    out_csv = out_prefix.with_suffix(".csv")
    out_similarity_csv = out_prefix.parent / f"{out_prefix.name}_similarity.csv"
    out_png = out_prefix.with_suffix(".png")
    out_md = out_prefix.with_suffix(".md")

    result_df.to_csv(out_csv, index=False)
    similarity_df.to_csv(out_similarity_csv, index=False)
    build_plot(result_df, out_png)
    write_markdown(result_df, similarity_df, out_md, out_png)

    print(f"results: {out_csv}")
    print(f"similarity: {out_similarity_csv}")
    print(f"plot: {out_png}")
    print(f"report: {out_md}")
    print(result_df[["ward", "outcome", "estimate_pct", "ci_low_pct", "ci_high_pct", "loo_mae_pct"]].to_string(index=False))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="2026-04 看護必要度推計")
    parser.add_argument("--monthly-dir", type=Path, default=DEFAULT_MONTHLY_DIR)
    parser.add_argument("--nursing-csv", type=Path, default=DEFAULT_NURSING_CSV)
    parser.add_argument("--admission-csv", type=Path, default=DEFAULT_ADMISSION_CSV)
    parser.add_argument("--out-prefix", type=Path, default=DEFAULT_OUT_PREFIX)
    parser.add_argument("--target-ym", default=TARGET_YM)
    parser.add_argument("--bootstrap", type=int, default=10000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run(
        monthly_dir=args.monthly_dir,
        nursing_csv=args.nursing_csv,
        admission_csv=args.admission_csv,
        out_prefix=args.out_prefix,
        target_ym=args.target_ym,
        bootstrap=args.bootstrap,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
