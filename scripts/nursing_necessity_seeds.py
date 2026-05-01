"""看護必要度 月次手動シード loader（過去月補完ブリッジ）.

副院長指示 (2026-05-01): 6/1 以降の rolling 3ヶ月看護必要度評価を、
運用開始直後から機能させるための過去月補完機構。

優先順位:
  1. 日次データ (data/nursing_necessity_2025fy.csv) があればそれを優先
  2. 日次データがない月は、settings/manual_seed_nursing_necessity.yaml で補完
  3. シードもない月は no_data

設計原則:
- 既存 nursing_necessity_loader.py を変更しない（新規モジュール、後方互換）
- 出典フラグ data_source: "csv" / "monthly_seed" / "no_data"
- 5F / 6F を分離（合計は呼び出し側で計算）
- I/II それぞれ分母・該当数を扱う
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pandas as pd
import yaml

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

DEFAULT_SEED_YAML = Path("settings/manual_seed_nursing_necessity.yaml")
SEED_REQUIRED_KEYS = ("I_total", "I_pass1", "II_total", "II_pass1")
SEED_WARDS = ("5F", "6F")

# 月次サマリーの正規列（calculate_monthly_summary と整合）
MONTHLY_COLUMNS = [
    "ym", "ward",
    "I_total", "I_pass1", "II_total", "II_pass1",
    "I_rate1", "II_rate1",
    "I_meets_legacy", "I_meets_new", "II_meets_legacy", "II_meets_new",
    "data_source",  # 新規: csv / monthly_seed / no_data
]

# しきい値（nursing_necessity_thresholds.py と同期）
THRESHOLD_I_LEGACY = 0.16
THRESHOLD_I_NEW = 0.19
THRESHOLD_II_LEGACY = 0.14
THRESHOLD_II_NEW = 0.18


# ---------------------------------------------------------------------------
# YAML 読み書き
# ---------------------------------------------------------------------------

def load_seeds_from_yaml(path: Path | str | None = None) -> dict[str, dict[str, dict[str, Optional[float]]]]:
    """看護必要度シード YAML を読み込み.

    Returns:
        {"YYYY-MM": {"5F": {I_total: ..., I_pass1: ..., II_total: ..., II_pass1: ...}, "6F": {...}}}
        キーが存在しない / null は dict から除外（呼び出し側で no_data 扱い）

    ファイルがない場合は空辞書を返す（エラーにしない）。
    """
    p = Path(path) if path else DEFAULT_SEED_YAML
    if not p.exists():
        return {}
    try:
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return {}

    raw = data.get("seeds", {}) if isinstance(data, dict) else {}
    if not isinstance(raw, dict):
        return {}

    cleaned: dict[str, dict[str, dict[str, Optional[float]]]] = {}
    for ym, ward_dict in raw.items():
        if not isinstance(ward_dict, dict):
            continue
        cleaned_wards: dict[str, dict[str, Optional[float]]] = {}
        for ward, vals in ward_dict.items():
            if ward not in SEED_WARDS:
                continue
            if not isinstance(vals, dict):
                continue
            # 必須キー全部があり、null 以外の値が 1 つでもあれば採用
            entry: dict[str, Optional[float]] = {}
            for k in SEED_REQUIRED_KEYS:
                v = vals.get(k)
                if v is None:
                    entry[k] = None
                else:
                    try:
                        entry[k] = float(v)
                    except (ValueError, TypeError):
                        entry[k] = None
            # 全部 None なら採用しない
            if any(v is not None for v in entry.values()):
                cleaned_wards[ward] = entry
        if cleaned_wards:
            cleaned[str(ym)] = cleaned_wards
    return cleaned


def is_seed_valid(seed: dict[str, Optional[float]]) -> bool:
    """シードが完全（4 つの数値が揃っている）かを判定.

    部分的に null があると rolling 計算に使えないため除外する。
    """
    return all(
        seed.get(k) is not None and isinstance(seed.get(k), (int, float))
        for k in SEED_REQUIRED_KEYS
    )


# ---------------------------------------------------------------------------
# シード行生成
# ---------------------------------------------------------------------------

def _make_seed_row(ym: str, ward: str, seed: dict[str, Optional[float]]) -> dict[str, Any]:
    """1 シード値を月次サマリー行（dict）に変換."""
    i_total = float(seed["I_total"])
    i_pass1 = float(seed["I_pass1"])
    ii_total = float(seed["II_total"])
    ii_pass1 = float(seed["II_pass1"])
    i_rate = (i_pass1 / i_total) if i_total > 0 else 0.0
    ii_rate = (ii_pass1 / ii_total) if ii_total > 0 else 0.0
    return {
        "ym": ym,
        "ward": ward,
        "I_total": int(i_total),
        "I_pass1": int(i_pass1),
        "II_total": int(ii_total),
        "II_pass1": int(ii_pass1),
        "I_rate1": i_rate,
        "II_rate1": ii_rate,
        "I_meets_legacy": i_rate >= THRESHOLD_I_LEGACY,
        "I_meets_new": i_rate >= THRESHOLD_I_NEW,
        "II_meets_legacy": ii_rate >= THRESHOLD_II_LEGACY,
        "II_meets_new": ii_rate >= THRESHOLD_II_NEW,
        "data_source": "monthly_seed",
    }


# ---------------------------------------------------------------------------
# マージ（CSV 優先 + シード補完）
# ---------------------------------------------------------------------------

def merge_monthly_with_seeds(
    monthly_df: pd.DataFrame,
    seeds: dict[str, dict[str, dict[str, Optional[float]]]] | None = None,
) -> pd.DataFrame:
    """日次CSV由来の月次サマリーに、シードで補完した行を追加.

    優先順位:
    - 既に monthly_df に存在する (ym, ward) はそのまま（CSV 優先）+ data_source="csv"
    - monthly_df にない (ym, ward) でシードがあれば追加 + data_source="monthly_seed"

    Args:
        monthly_df: calculate_monthly_summary() の出力（ym, ward, I_total, ... 列）
        seeds: load_seeds_from_yaml() の出力。None なら空辞書扱い

    Returns:
        補完後の月次サマリー DataFrame（ym, ward, MONTHLY_COLUMNS）
    """
    seeds = seeds or {}

    # CSV 由来行に data_source="csv" を付与
    csv_rows: list[dict[str, Any]] = []
    if monthly_df is not None and len(monthly_df) > 0:
        for _, row in monthly_df.iterrows():
            ward = row.get("ward")
            # 「合計」は補完対象外（5F + 6F は呼び出し側で計算可）
            if ward not in SEED_WARDS and ward != "合計":
                continue
            d = row.to_dict()
            d["data_source"] = "csv"
            csv_rows.append(d)

    existing_keys = {(r["ym"], r["ward"]) for r in csv_rows}

    # シード由来行を生成（CSV になく、かつ完全なシードのみ）
    seed_rows: list[dict[str, Any]] = []
    for ym, ward_dict in seeds.items():
        for ward in SEED_WARDS:
            if (ym, ward) in existing_keys:
                continue
            seed = ward_dict.get(ward)
            if not seed or not is_seed_valid(seed):
                continue
            seed_rows.append(_make_seed_row(ym, ward, seed))

    all_rows = csv_rows + seed_rows
    if not all_rows:
        # 空の場合も列構造は保つ
        return pd.DataFrame(columns=MONTHLY_COLUMNS)

    out = pd.DataFrame(all_rows)
    # 列順を整える（存在する列のみ）
    cols = [c for c in MONTHLY_COLUMNS if c in out.columns]
    extra = [c for c in out.columns if c not in cols]
    out = out[cols + extra]
    # ym, ward でソート
    out = out.sort_values(["ym", "ward"]).reset_index(drop=True)
    return out


def summarize_yearly_from_monthly(
    monthly_df: pd.DataFrame,
    *,
    threshold_i_legacy: float = THRESHOLD_I_LEGACY,
    threshold_i_new: float = THRESHOLD_I_NEW,
    threshold_ii_legacy: float = THRESHOLD_II_LEGACY,
    threshold_ii_new: float = THRESHOLD_II_NEW,
) -> pd.DataFrame:
    """月次サマリー（CSV + シード混在）から ward 別の yearly average を計算.

    Codex Finding 2 (2026-05-01) 対応:
    既存の calculate_yearly_average() は **日次データ** を groupby するため、
    シード行（月次粒度）を直接渡せない。本 adapter は monthly_df から
    分母・分子を ward 別に合計して同じ列構成を返す。

    Args:
        monthly_df: merge_monthly_with_seeds() の出力 (ym, ward, I_total, I_pass1, II_total, II_pass1)
        threshold_*: 基準値（テスト用に上書き可能）

    Returns:
        DataFrame with columns: ward, I_total, I_pass1, II_total, II_pass1,
            I_rate1_avg, II_rate1_avg, gap_I_legacy, gap_I_new, gap_II_legacy, gap_II_new
    """
    if monthly_df is None or len(monthly_df) == 0:
        return pd.DataFrame(columns=[
            "ward", "I_total", "I_pass1", "II_total", "II_pass1",
            "I_rate1_avg", "II_rate1_avg",
            "gap_I_legacy", "gap_I_new", "gap_II_legacy", "gap_II_new",
        ])

    df = monthly_df.copy()
    # 「合計」行は重複集計を避けるため除外（5F + 6F のみ集計）
    df = df[df["ward"].isin(SEED_WARDS)] if "ward" in df.columns else df
    if len(df) == 0:
        return pd.DataFrame(columns=[
            "ward", "I_total", "I_pass1", "II_total", "II_pass1",
            "I_rate1_avg", "II_rate1_avg",
            "gap_I_legacy", "gap_I_new", "gap_II_legacy", "gap_II_new",
        ])

    yearly = df.groupby("ward", as_index=False).agg(
        I_total=("I_total", "sum"),
        I_pass1=("I_pass1", "sum"),
        II_total=("II_total", "sum"),
        II_pass1=("II_pass1", "sum"),
    )
    yearly["I_rate1_avg"] = yearly["I_pass1"] / yearly["I_total"].replace(0, pd.NA)
    yearly["II_rate1_avg"] = yearly["II_pass1"] / yearly["II_total"].replace(0, pd.NA)
    yearly["gap_I_legacy"] = yearly["I_rate1_avg"] - threshold_i_legacy
    yearly["gap_I_new"] = yearly["I_rate1_avg"] - threshold_i_new
    yearly["gap_II_legacy"] = yearly["II_rate1_avg"] - threshold_ii_legacy
    yearly["gap_II_new"] = yearly["II_rate1_avg"] - threshold_ii_new
    return yearly


def get_data_source_summary(
    merged_df: pd.DataFrame,
    target_ym: list[str] | None = None,
) -> dict[str, dict[str, str]]:
    """月別 × 病棟別の data_source を簡潔にまとめる（UI 表示用）.

    Args:
        merged_df: merge_monthly_with_seeds() の出力
        target_ym: 表示したい月のリスト（None なら全月）

    Returns:
        {"YYYY-MM": {"5F": "csv" / "monthly_seed" / "no_data", "6F": ...}}
    """
    out: dict[str, dict[str, str]] = {}
    if merged_df is None or len(merged_df) == 0:
        return out
    for _, row in merged_df.iterrows():
        ym = row.get("ym")
        ward = row.get("ward")
        src = row.get("data_source", "csv")
        if ward not in SEED_WARDS:
            continue
        if target_ym and ym not in target_ym:
            continue
        out.setdefault(ym, {})[ward] = src
    # 欠損月は "no_data"
    if target_ym:
        for ym in target_ym:
            entry = out.setdefault(ym, {})
            for ward in SEED_WARDS:
                entry.setdefault(ward, "no_data")
    return out


# ---------------------------------------------------------------------------
# YAML 書き込み（UI 用）
# ---------------------------------------------------------------------------

def save_seed_to_yaml(
    ym: str,
    ward: str,
    seed: dict[str, Optional[float]],
    path: Path | str | None = None,
) -> Path:
    """1 (ym, ward) のシードを YAML に保存（既存値に上書き）.

    Args:
        ym: "YYYY-MM"
        ward: "5F" or "6F"
        seed: {I_total: float, I_pass1: float, II_total: float, II_pass1: float}
        path: 保存先 YAML（デフォルト: settings/manual_seed_nursing_necessity.yaml）

    Returns:
        保存先パス
    """
    if ward not in SEED_WARDS:
        raise ValueError(f"ward は {SEED_WARDS} のいずれかにしてください: {ward}")

    p = Path(path) if path else DEFAULT_SEED_YAML
    p.parent.mkdir(parents=True, exist_ok=True)

    # 既存読み込み（生 YAML を保持してコメントを温存）
    existing: dict[str, Any] = {}
    if p.exists():
        try:
            with p.open("r", encoding="utf-8") as f:
                existing = yaml.safe_load(f) or {}
        except Exception:
            existing = {}

    seeds_dict = existing.get("seeds")
    if not isinstance(seeds_dict, dict):
        seeds_dict = {}

    ym_dict = seeds_dict.get(ym)
    if not isinstance(ym_dict, dict):
        ym_dict = {}

    # 値の正規化
    norm: dict[str, Optional[float]] = {}
    for k in SEED_REQUIRED_KEYS:
        v = seed.get(k)
        if v is None:
            norm[k] = None
        else:
            norm[k] = float(v)
    ym_dict[ward] = norm
    seeds_dict[ym] = ym_dict
    existing["seeds"] = seeds_dict

    with p.open("w", encoding="utf-8") as f:
        yaml.safe_dump(existing, f, allow_unicode=True, sort_keys=True, default_flow_style=False)
    return p
