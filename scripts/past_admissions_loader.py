"""過去入院データ（2025年度事務提供 CSV）のローダー.

`data/past_admissions_2025fy.csv` を読み込み、以下を提供する:

- 生 DataFrame のロード＋派生列付与（`is_emergency_transport` 等）
- 既存 `emergency_ratio.calculate_rolling_emergency_ratio()` が受け取る
  `monthly_summary` 形式への変換
- 短手3 推定ヘルパー（副院長指示 2026-04-24 のヒューリスティック）
- イ/ロ/ハ判定の過去遡及集計

**重要な制度ルール（副院長指示 2026-04-24）:**
- 救急搬送後 15% 判定の分子 = 自院救急 + 下り搬送（両方を救急搬送としてカウント）
- 分母 = 全入院（短手3 を**除外しない**）
- 短手3 の識別は統計・収入分析用途のみ。救急比率計算とは切り離す

Streamlit には依存しない pure function のみ。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

DEFAULT_CSV_PATH: Path = Path(__file__).resolve().parent.parent / "data" / "past_admissions_2025fy.csv"

# 救急搬送判定ラベル
EMERGENCY_AMBULANCE_YES: str = "有り"

# 入経路ラベル
ROUTE_HOME: str = "家庭"
ROUTE_FACILITY: str = "施設入"
ROUTE_OTHER_HOSPITAL: str = "他病院"

# 手術ラベル
SURGERY_YES: str = "○"
SURGERY_NO: str = "×"

# 短手3 推定ルール（副院長指示 2026-04-24）:
#   - 手術あり × 日数 ≤ 2 → 確実に短手3（大腸ポリペクトミー等）
#   - 手術あり × 日数 ≤ 5 → ほぼ短手3（短期滞在）
# この推定は **統計・収入分析のみ** に使う。救急比率計算とは分離する。
SHORT3_CERTAIN_LOS_MAX: int = 2
SHORT3_LIKELY_LOS_MAX: int = 5


# ---------------------------------------------------------------------------
# ロード
# ---------------------------------------------------------------------------

def load_past_admissions(csv_path: Optional[Path] = None) -> pd.DataFrame:
    """過去入院データ CSV をロードし、派生列を付与して返す.

    派生列:
        - ``is_emergency_transport``: 救急車=='有り' (bool)
        - ``is_self_emergency``: 自院救急搬送 (救急車有 × 入経路 ∈ 家庭/施設入)
        - ``is_downstream_transfer``: 下り搬送 (救急車有 × 入経路=他病院)
        - ``is_scheduled``: 予定入院 (緊急='予定入院')
        - ``has_surgery``: 手術=='○'
        - ``is_short3_certain``: 手術○ × 日数 ≤ 2 (大腸ポリペク等、確実)
        - ``is_short3_likely``: 手術○ × 日数 ≤ 5 (短期滞在、ほぼ確実)
        - ``admission_date``: 入院日を date 型で
        - ``discharge_date``: 退院日を date 型で（在院中は NaT）

    Args:
        csv_path: CSV ファイルパス。省略時は ``data/past_admissions_2025fy.csv``。

    Returns:
        派生列付き DataFrame。ロード失敗時は空の DataFrame。
    """
    path = csv_path if csv_path is not None else DEFAULT_CSV_PATH
    if not path.exists():
        return pd.DataFrame()

    df = pd.read_csv(path)

    # 日付を date 型に（NaT を許容）
    df["admission_date"] = pd.to_datetime(df["入院日"], errors="coerce").dt.date
    df["discharge_date"] = pd.to_datetime(df["退院日"], errors="coerce").dt.date

    # 救急搬送フラグ
    df["is_emergency_transport"] = df["救急車"].astype(str) == EMERGENCY_AMBULANCE_YES

    # 自院救急 / 下り搬送の分離
    df["is_self_emergency"] = (
        df["is_emergency_transport"]
        & df["入経路"].isin([ROUTE_HOME, ROUTE_FACILITY])
    )
    df["is_downstream_transfer"] = (
        df["is_emergency_transport"]
        & (df["入経路"] == ROUTE_OTHER_HOSPITAL)
    )

    # 予定入院フラグ
    df["is_scheduled"] = df["緊急"].astype(str) == "予定入院"

    # 手術
    df["has_surgery"] = df["手術"].astype(str) == SURGERY_YES

    # 短手3 推定（統計用途のみ、救急比率分母には使わない）
    los = pd.to_numeric(df["日数"], errors="coerce")
    df["is_short3_certain"] = df["has_surgery"] & (los <= SHORT3_CERTAIN_LOS_MAX)
    df["is_short3_likely"] = df["has_surgery"] & (los <= SHORT3_LIKELY_LOS_MAX)

    return df


# ---------------------------------------------------------------------------
# 救急比率 → monthly_summary 変換
# ---------------------------------------------------------------------------

def to_monthly_summary(
    df: pd.DataFrame,
    exclude_short3_from_denominator: bool = False,
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """DataFrame を ``calculate_rolling_emergency_ratio`` の monthly_summary 形式に変換.

    既存の rolling 計算機に食わせるための adapter。

    **制度ルール（2026-06-01 以降の本則適用）:**
        分母に短手3 を含める（``exclude_short3_from_denominator=False`` がデフォルト）。
        ``True`` にすると短手3 除外モードだが、**制度判定では使わない**こと。

    Args:
        df: ``load_past_admissions()`` の戻り値
        exclude_short3_from_denominator: 分母から短手3（推定）を除外するか
            （デフォルト False = 制度準拠）

    Returns:
        ``{"YYYY-MM": {"5F": {"admissions": int, "emergency": int}, "6F": {...}, "all": {...}}}``
    """
    if df.empty:
        return {}

    # 入院日が無いレコードは除外（data quality）
    work = df[df["admission_date"].notna()].copy()
    if work.empty:
        return {}

    # 月キー
    work["ym"] = work["admission_date"].apply(lambda d: f"{d.year:04d}-{d.month:02d}")

    # 分母フィルタ（短手3 除外モードの場合のみ）
    if exclude_short3_from_denominator:
        # 「確実な短手3」のみ除外（保守的）
        work_for_denom = work[~work["is_short3_certain"]]
    else:
        work_for_denom = work

    summary: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for ym in sorted(work["ym"].unique()):
        summary[ym] = {}
        ym_df = work[work["ym"] == ym]
        ym_df_denom = work_for_denom[work_for_denom["ym"] == ym]
        for ward_key, ward_filter in [
            ("5F", ym_df["病棟"] == "5F"),
            ("6F", ym_df["病棟"] == "6F"),
            ("all", pd.Series([True] * len(ym_df), index=ym_df.index)),
        ]:
            ward_df = ym_df[ward_filter]
            # 分母は exclude_short3 適用版
            ward_df_denom = ym_df_denom[ym_df_denom["病棟"].isin(["5F", "6F"])] if ward_key == "all" else ym_df_denom[ym_df_denom["病棟"] == ward_key]
            summary[ym][ward_key] = {
                "admissions": int(len(ward_df_denom)),
                "emergency": int(ward_df["is_emergency_transport"].sum()),
                "self_emergency": int(ward_df["is_self_emergency"].sum()),
                "downstream_transfer": int(ward_df["is_downstream_transfer"].sum()),
            }
    return summary


# ---------------------------------------------------------------------------
# 短手3 推定サマリー（統計用途）
# ---------------------------------------------------------------------------

def summarize_short3_estimate(df: pd.DataFrame) -> Dict[str, Any]:
    """短手3 推定の全期間集計.

    副院長指示のヒューリスティック:
        - 確実: 手術あり × 日数 ≤ 2
        - ほぼ確実: 手術あり × 日数 ≤ 5

    **注意:** この推定は統計・収入分析のみ。救急比率の分母除外には使わない。

    Returns:
        dict: {
            "total_surgeries": 手術あり全件,
            "short3_certain": 確実（≤2日）,
            "short3_likely": ほぼ確実（≤5日）,
            "short3_likely_excluding_certain": 3-5日の手術入院,
            "non_short3_surgery": 6日以上の手術入院,
        }
    """
    if df.empty:
        return {
            "total_surgeries": 0,
            "short3_certain": 0,
            "short3_likely": 0,
            "short3_likely_excluding_certain": 0,
            "non_short3_surgery": 0,
        }
    surgery = df[df["has_surgery"]]
    n_surgery = int(len(surgery))
    n_certain = int(surgery["is_short3_certain"].sum())
    n_likely = int(surgery["is_short3_likely"].sum())
    return {
        "total_surgeries": n_surgery,
        "short3_certain": n_certain,
        "short3_likely": n_likely,
        "short3_likely_excluding_certain": n_likely - n_certain,
        "non_short3_surgery": n_surgery - n_likely,
    }


# ---------------------------------------------------------------------------
# イ/ロ/ハ 遡及判定
# ---------------------------------------------------------------------------

def tabulate_tier_distribution(df: pd.DataFrame) -> Dict[str, Any]:
    """2026改定 入院料1 のイ/ロ/ハ 判定を過去データに遡及適用.

    判定ロジック（入院料1 = A100 算定病棟なしの想定、当院該当）:
        - イ: 緊急入院（=予定外） × 手術なし → 3,367 点
        - ロ: 緊急入院 × 手術あり / 予定入院 × 手術なし → 3,267 点
        - ハ: 予定入院 × 手術あり → 3,117 点

    Note:
        制度上「緊急入院」は救急搬送だけでなく「予定外の医療入院」全般を含むため、
        本データの「緊急」列（予定外/予定入院）をそのまま使う。

    Returns:
        dict: {
            "total": 全件,
            "tier_i": 件数,
            "tier_ro": 件数,
            "tier_ha": 件数,
            "by_ward": {"5F": {...}, "6F": {...}},
        }
    """
    if df.empty:
        return {"total": 0, "tier_i": 0, "tier_ro": 0, "tier_ha": 0, "by_ward": {}}

    is_emergency = ~df["is_scheduled"]  # 予定入院 以外 = 緊急
    has_surgery = df["has_surgery"]

    tier_i = is_emergency & ~has_surgery
    tier_ro = (is_emergency & has_surgery) | (~is_emergency & ~has_surgery)
    tier_ha = ~is_emergency & has_surgery

    overall = {
        "total": int(len(df)),
        "tier_i": int(tier_i.sum()),
        "tier_ro": int(tier_ro.sum()),
        "tier_ha": int(tier_ha.sum()),
    }

    by_ward: Dict[str, Dict[str, int]] = {}
    for w in ["5F", "6F"]:
        mask = df["病棟"] == w
        by_ward[w] = {
            "total": int(mask.sum()),
            "tier_i": int((tier_i & mask).sum()),
            "tier_ro": int((tier_ro & mask).sum()),
            "tier_ha": int((tier_ha & mask).sum()),
        }
    overall["by_ward"] = by_ward
    return overall
