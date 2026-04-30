"""H ファイル（看護必要度評価票）パーサ.

データ仕様（実データから推定、当院 2025-04 〜 2026-04 で実証検証済み）:

monthly_merged の Hn 行 = 厚労省標準 H ファイル
    項目01: 施設コード
    項目02: 病棟コード（5F, 6F, 4F 等、当院では 5F/6F のみ地域包括医療病棟）
    項目03: データ識別番号（患者 ID、保険番号削除済）
    項目04: 退院年月日
    項目05: 入院年月日
    項目06: 評価年月日
    項目07: 評価者コード
        ASS0013 = 必要度Ⅰ A 項目評価（値域 0/1、二値判定）
        ASS0021 = 必要度Ⅱ A 項目評価（値域 0/1/2、コード由来スコア）
        TAR0010 = B 項目（患者の状況、自立度評価）
    項目08: 評価開始日
    項目09: 評価ステータス（0 = 通常評価）
    項目10〜20: 各項目の評価点（評価者コード別に意味が変わる）

各患者×日について最大 3 レコードが存在する。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


WARDS_OF_INTEREST = ("5F", "6F")
EVALUATOR_NEED_I = "ASS0013"
EVALUATOR_NEED_II = "ASS0021"
EVALUATOR_B_ITEM = "TAR0010"

ITEM_COLS = [f"項目{i:02d}" for i in range(10, 21)]


@dataclass
class HFileRecords:
    need_i_a: pd.DataFrame  # 必要度Ⅰ A 項目評価レコード（ASS0013）
    need_ii_a: pd.DataFrame  # 必要度Ⅱ A 項目評価レコード（ASS0021）
    b_items: pd.DataFrame  # B 項目評価レコード（TAR0010）


def _normalize(s: pd.Series) -> pd.Series:
    return s.astype("string").str.strip()


def _coerce_int(value: object) -> int:
    if pd.isna(value):
        return 0
    try:
        return int(str(value).strip().lstrip("0") or "0")
    except (TypeError, ValueError):
        return 0


def parse_merged_csv(path: str | Path) -> HFileRecords:
    """1 ヶ月分の merged_*.csv を読み、Hn 部分を評価者別に分離する."""
    df = pd.read_csv(path, encoding="utf-8", dtype=str, low_memory=False)
    hn = df[df["ファイル種別"] == "Hn"].copy()
    hn["ward"] = _normalize(hn["項目02"])
    hn["evaluator"] = _normalize(hn["項目07"])
    hn["patient_id"] = _normalize(hn["項目03"])
    hn["eval_date"] = pd.to_datetime(_normalize(hn["項目06"]), format="%Y%m%d", errors="coerce")
    hn["admit_date"] = pd.to_datetime(_normalize(hn["項目05"]), format="%Y%m%d", errors="coerce")
    hn["discharge_date"] = pd.to_datetime(_normalize(hn["項目04"]), format="%Y%m%d", errors="coerce")
    # 退院日が 00000000（在院中）は NaT になる
    hn = hn[hn["ward"].isin(WARDS_OF_INTEREST)].copy()

    need_i = hn[hn["evaluator"] == EVALUATOR_NEED_I].copy()
    need_ii = hn[hn["evaluator"] == EVALUATOR_NEED_II].copy()
    b_items = hn[hn["evaluator"] == EVALUATOR_B_ITEM].copy()

    return HFileRecords(need_i_a=need_i, need_ii_a=need_ii, b_items=b_items)


def load_all_months(directory: str | Path) -> dict[str, HFileRecords]:
    """monthly_merged ディレクトリ全体を読み込む."""
    directory = Path(directory)
    out: dict[str, HFileRecords] = {}
    for path in sorted(directory.glob("merged_*.csv")):
        ym = path.stem.split("_")[-1]  # merged_470116619_202504 -> 202504
        out[ym] = parse_merged_csv(path)
    return out


def compute_a_score_need_i(row: pd.Series) -> int:
    """必要度Ⅰ A 項目得点合計.

    ASS0013 のレコードでは項目10〜17 が A1〜A7（または A1〜A6+合計）に対応する想定。
    実データでは値域 0/1 が大半で、項目10-15, 17 を A1-A7 のチェック有無として合算する。
    """
    cols = ["項目10", "項目11", "項目14", "項目15", "項目17"]
    return sum(_coerce_int(row.get(c)) for c in cols)


def compute_a_score_need_ii(row: pd.Series) -> int:
    """必要度Ⅱ A 項目得点合計.

    ASS0021 のレコードでは項目10〜20 が A1〜A11 相当（コード由来スコアで 0/1/2）。
    """
    cols = [f"項目{i:02d}" for i in (10, 11, 12, 13, 14, 15, 17, 18, 19, 20)]
    return sum(_coerce_int(row.get(c)) for c in cols)


def compute_c_score_need_i(row: pd.Series) -> int:
    """必要度Ⅰ C 項目得点（手術等）.

    実データ確認: ASS0013 の項目16 が C 項目に近い値（"000" or "010"）を示し、
    これを 0 / 1 の該当として扱う。
    """
    val = row.get("項目16")
    if pd.isna(val):
        return 0
    s = str(val).strip()
    if s in ("0", "000", ""):
        return 0
    return 1


def compute_c_score_need_ii(row: pd.Series) -> int:
    """必要度Ⅱ C 項目得点.

    ASS0021 の項目16 = C 項目フラグ（0/1）.
    """
    return _coerce_int(row.get("項目16"))


def compute_b_score(row: pd.Series) -> int:
    """B 項目（患者の状況）合計.

    TAR0010 の項目10 が B 項目集約値（実データでは 0 = 自立 / 5 = 介助）.
    """
    return _coerce_int(row.get("項目10"))


def is_eligible(a_score: int, b_score: int, c_score: int) -> bool:
    """看護必要度 該当判定（地域包括医療病棟 / 地域包括ケア病棟 共通ロジック）.

    該当条件（いずれか）:
        - A ≥ 2
        - C ≥ 1
        - A ≥ 1 かつ B ≥ 3
    """
    if a_score >= 2:
        return True
    if c_score >= 1:
        return True
    if a_score >= 1 and b_score >= 3:
        return True
    return False


def daily_eligibility_table(
    records: HFileRecords, kind: str
) -> pd.DataFrame:
    """評価者別レコードから患者×日の該当判定テーブルを作る.

    Parameters
    ----------
    records : HFileRecords
    kind : "I" | "II"

    Returns
    -------
    DataFrame with columns: patient_id, ward, eval_date, a_score, b_score, c_score, eligible
    """
    if kind == "I":
        a_df = records.need_i_a.copy()
        compute_a = compute_a_score_need_i
        compute_c = compute_c_score_need_i
    elif kind == "II":
        a_df = records.need_ii_a.copy()
        compute_a = compute_a_score_need_ii
        compute_c = compute_c_score_need_ii
    else:
        raise ValueError(f"kind must be 'I' or 'II', got {kind!r}")

    if a_df.empty:
        return pd.DataFrame(columns=["patient_id", "ward", "eval_date", "a_score", "b_score", "c_score", "eligible"])

    a_df = a_df.dropna(subset=["eval_date"]).copy()
    a_df["a_score"] = a_df.apply(compute_a, axis=1)
    a_df["c_score"] = a_df.apply(compute_c, axis=1)

    b_df = records.b_items.dropna(subset=["eval_date"]).copy()
    b_df["b_score"] = b_df.apply(compute_b_score, axis=1)
    b_df = b_df[["patient_id", "ward", "eval_date", "b_score"]]

    merged = a_df.merge(
        b_df,
        on=["patient_id", "ward", "eval_date"],
        how="left",
    )
    merged["b_score"] = merged["b_score"].fillna(0).astype(int)

    merged["eligible"] = merged.apply(
        lambda r: is_eligible(int(r["a_score"]), int(r["b_score"]), int(r["c_score"])),
        axis=1,
    )

    return merged[["patient_id", "ward", "eval_date", "a_score", "b_score", "c_score", "eligible", "admit_date", "discharge_date"]].copy()


def monthly_eligibility_summary(
    records: HFileRecords, kind: str, ym: str
) -> pd.DataFrame:
    """病棟×月の該当患者割合を計算.

    rate1 = 該当延べ日数 / 在院延べ日数 (= 全評価レコード数)
    """
    daily = daily_eligibility_table(records, kind)
    if daily.empty:
        return pd.DataFrame(columns=["year_month", "ward", "kind", "denominator_days", "eligible_days", "rate1"])

    grouped = daily.groupby("ward").agg(
        denominator_days=("eligible", "size"),
        eligible_days=("eligible", "sum"),
    ).reset_index()
    grouped["rate1"] = grouped["eligible_days"] / grouped["denominator_days"]
    grouped["year_month"] = ym
    grouped["kind"] = kind
    return grouped[["year_month", "ward", "kind", "denominator_days", "eligible_days", "rate1"]]
