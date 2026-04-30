"""H ファイルから月次・病棟別の特徴量を構築するモジュール.

直接の該当判定再構成では必要度Ⅱの相関が低い (r=-0.15)。
これは ASS0021 の値が「評価員の見立て」であり、最終確定値（DPC 支援ツール再計算）
とは違う層のデータだからと考えられる。

代替策として、H ファイル全項目の月次集計統計量を特徴量化し、
機械学習で確定値を予測するアプローチを取る。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from scripts.nursing_estimation.h_file_loader import (
    HFileRecords,
    ITEM_COLS,
    parse_merged_csv,
)


def _safe_int(s: object) -> int:
    if pd.isna(s):
        return 0
    try:
        return int(str(s).strip().lstrip("0") or "0")
    except (TypeError, ValueError):
        return 0


def _aggregate_evaluator_block(
    df: pd.DataFrame, prefix: str
) -> dict[str, float]:
    """評価者種別ごとのレコード集合から、項目10〜20 の集約特徴量を作る."""
    out: dict[str, float] = {}
    if df.empty:
        for col in ITEM_COLS:
            out[f"{prefix}_{col}_mean"] = 0.0
            out[f"{prefix}_{col}_pos_ratio"] = 0.0
            out[f"{prefix}_{col}_high_ratio"] = 0.0
        out[f"{prefix}_n_records"] = 0
        return out

    for col in ITEM_COLS:
        if col not in df.columns:
            out[f"{prefix}_{col}_mean"] = 0.0
            out[f"{prefix}_{col}_pos_ratio"] = 0.0
            out[f"{prefix}_{col}_high_ratio"] = 0.0
            continue
        vals = df[col].apply(_safe_int)
        out[f"{prefix}_{col}_mean"] = float(vals.mean())
        out[f"{prefix}_{col}_pos_ratio"] = float((vals > 0).mean())
        out[f"{prefix}_{col}_high_ratio"] = float((vals >= 2).mean())
    out[f"{prefix}_n_records"] = int(len(df))
    return out


def build_monthly_features(records: HFileRecords, ym: str) -> pd.DataFrame:
    """1 ヶ月分の H ファイルから (月, 病棟) 別の特徴量行列を構築."""
    rows = []
    for ward in ("5F", "6F"):
        feat: dict[str, object] = {"year_month": ym, "ward": ward}

        ni = records.need_i_a[records.need_i_a["ward"] == ward]
        nii = records.need_ii_a[records.need_ii_a["ward"] == ward]
        bi = records.b_items[records.b_items["ward"] == ward]

        feat.update(_aggregate_evaluator_block(ni, "i_a"))
        feat.update(_aggregate_evaluator_block(nii, "ii_a"))
        feat.update(_aggregate_evaluator_block(bi, "b"))

        # 在院延べ日数（denominator） = ASS0013 のレコード数（評価日数）
        feat["denominator_days"] = int(len(ni))
        feat["unique_patients"] = int(ni["patient_id"].nunique()) if not ni.empty else 0

        # ASS0021 の "high A score patients" など（必要度Ⅱ補強用）
        if not nii.empty:
            a_score_ii = nii.apply(
                lambda r: sum(_safe_int(r.get(c)) for c in ITEM_COLS), axis=1
            )
            feat["ii_a_score_mean"] = float(a_score_ii.mean())
            feat["ii_a_score_p75"] = float(a_score_ii.quantile(0.75))
            feat["ii_a_score_high2_ratio"] = float((a_score_ii >= 2).mean())
            feat["ii_a_score_high4_ratio"] = float((a_score_ii >= 4).mean())
        else:
            feat["ii_a_score_mean"] = 0.0
            feat["ii_a_score_p75"] = 0.0
            feat["ii_a_score_high2_ratio"] = 0.0
            feat["ii_a_score_high4_ratio"] = 0.0

        rows.append(feat)
    return pd.DataFrame(rows)


def build_full_dataset(monthly_dir: str | Path) -> pd.DataFrame:
    """全月の特徴量行列を結合."""
    monthly_dir = Path(monthly_dir)
    parts = []
    for path in sorted(monthly_dir.glob("merged_*.csv")):
        ym = path.stem.split("_")[-1]
        rec = parse_merged_csv(path)
        parts.append(build_monthly_features(rec, ym))
    return pd.concat(parts, ignore_index=True)


def attach_ground_truth(
    features: pd.DataFrame, gt_csv: str | Path
) -> pd.DataFrame:
    """確定看護必要度 CSV を結合."""
    gt = pd.read_csv(gt_csv)
    gt["date"] = pd.to_datetime(gt["date"])
    gt = gt[gt["ward"].isin(("5F", "6F"))].copy()
    gt["year_month"] = gt["date"].dt.strftime("%Y%m")
    gt_agg = (
        gt.groupby(["year_month", "ward"])
        .agg(
            I_total=("I_total", "sum"),
            I_pass=("I_pass1", "sum"),
            II_total=("II_total", "sum"),
            II_pass=("II_pass1", "sum"),
        )
        .reset_index()
    )
    gt_agg["I_actual_rate"] = gt_agg["I_pass"] / gt_agg["I_total"]
    gt_agg["II_actual_rate"] = gt_agg["II_pass"] / gt_agg["II_total"]
    return features.merge(
        gt_agg[["year_month", "ward", "I_actual_rate", "II_actual_rate"]],
        on=["year_month", "ward"],
        how="left",
    )
