"""看護必要度データ（事務提供 XLSM 由来 CSV）のローダー.

`data/nursing_necessity_2025fy.csv` を読み込み、以下を提供する:

- 生 DataFrame のロード（日次×病棟×Ⅰ/Ⅱ × 基準①/②）
- 月次集計（病棟別、必要度Ⅰ/Ⅱ）
- 直近 3 ヶ月 rolling 達成率
- 基準割れ検出

**個人情報なし**: XLSM の「データ（全体）」シートから抽出した集計値のみ扱う。
「患者別」シート（個人情報あり）は取り込まない設計。

Streamlit に依存しない pure function のみ。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import List, Optional

import pandas as pd

from nursing_necessity_thresholds import (
    THRESHOLD_I_LEGACY,
    THRESHOLD_I_NEW,
    THRESHOLD_II_LEGACY,
    THRESHOLD_II_NEW,
    get_threshold,
)

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

DEFAULT_CSV_PATH: Path = (
    Path(__file__).resolve().parent.parent / "data" / "nursing_necessity_2025fy.csv"
)

# 病棟ラベル
WARD_5F: str = "5F"
WARD_6F: str = "6F"
WARD_TOTAL: str = "合計"
WARDS: List[str] = [WARD_5F, WARD_6F, WARD_TOTAL]

# 必要度区分
NECESSITY_I: str = "I"
NECESSITY_II: str = "II"


# ---------------------------------------------------------------------------
# ロード
# ---------------------------------------------------------------------------

def load_nursing_necessity(csv_path: Optional[Path] = None) -> pd.DataFrame:
    """看護必要度データ CSV をロードして返す.

    CSV 列:
        - date: 日付（YYYY-MM-DD）
        - ward: 病棟（"5F" / "6F" / "合計"）
        - teisho: 定床数
        - I_total: 必要度Ⅰ 患者延べ数（地域包括医療病棟）
        - I_pass1: 必要度Ⅰ 基準①超対象患者数
        - I_rate1: 必要度Ⅰ 基準①「満たす割合」
        - I_admit: 必要度Ⅰ 入棟患者数
        - I_pass2: 必要度Ⅰ 基準②超対象患者数
        - I_rate2: 必要度Ⅰ 基準②「満たす割合」
        - II_total, II_pass1, II_rate1, II_admit, II_pass2, II_rate2: 必要度Ⅱ 同様
        - ym: 年月（YYYY-MM）

    Args:
        csv_path: CSV ファイルパス。省略時は ``data/nursing_necessity_2025fy.csv``。

    Returns:
        DataFrame。ファイル不在時は空 DataFrame。
    """
    path = csv_path if csv_path is not None else DEFAULT_CSV_PATH
    if not path.exists():
        return pd.DataFrame()

    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[df["date"].notna()].copy()
    df["ym"] = df["date"].dt.to_period("M").astype(str)
    return df


# ---------------------------------------------------------------------------
# 月次集計
# ---------------------------------------------------------------------------

def calculate_monthly_summary(df: pd.DataFrame) -> pd.DataFrame:
    """日次データを月次集計に変換.

    Args:
        df: ``load_nursing_necessity()`` の戻り値

    Returns:
        DataFrame with columns:
            - ym, ward
            - I_total, I_pass1, I_rate1
            - II_total, II_pass1, II_rate1
            - I_meets_legacy, I_meets_new, II_meets_legacy, II_meets_new (bool)
    """
    if df.empty:
        return pd.DataFrame()

    monthly = df.groupby(["ym", "ward"], as_index=False).agg(
        I_total=("I_total", "sum"),
        I_pass1=("I_pass1", "sum"),
        II_total=("II_total", "sum"),
        II_pass1=("II_pass1", "sum"),
    )

    # 月次達成率を再計算（日次の単純平均ではなく、合計から再計算）
    monthly["I_rate1"] = monthly["I_pass1"] / monthly["I_total"].replace(0, pd.NA)
    monthly["II_rate1"] = monthly["II_pass1"] / monthly["II_total"].replace(0, pd.NA)

    # 達成判定（旧/新両基準）
    monthly["I_meets_legacy"] = monthly["I_rate1"] >= THRESHOLD_I_LEGACY
    monthly["I_meets_new"] = monthly["I_rate1"] >= THRESHOLD_I_NEW
    monthly["II_meets_legacy"] = monthly["II_rate1"] >= THRESHOLD_II_LEGACY
    monthly["II_meets_new"] = monthly["II_rate1"] >= THRESHOLD_II_NEW

    return monthly


def calculate_yearly_average(df: pd.DataFrame) -> pd.DataFrame:
    """12 ヶ月通算平均（病棟別）を計算.

    日次の単純平均ではなく、患者延べ数の合計から達成率を再計算する
    （月次集計と同じ思想 = 加重平均相当）。

    Returns:
        DataFrame with columns: ward, I_rate1_avg, II_rate1_avg, gap_I_new, gap_II_new
    """
    if df.empty:
        return pd.DataFrame()

    avg = df.groupby("ward", as_index=False).agg(
        I_total=("I_total", "sum"),
        I_pass1=("I_pass1", "sum"),
        II_total=("II_total", "sum"),
        II_pass1=("II_pass1", "sum"),
    )
    avg["I_rate1_avg"] = avg["I_pass1"] / avg["I_total"].replace(0, pd.NA)
    avg["II_rate1_avg"] = avg["II_pass1"] / avg["II_total"].replace(0, pd.NA)
    avg["gap_I_legacy"] = avg["I_rate1_avg"] - THRESHOLD_I_LEGACY
    avg["gap_I_new"] = avg["I_rate1_avg"] - THRESHOLD_I_NEW
    avg["gap_II_legacy"] = avg["II_rate1_avg"] - THRESHOLD_II_LEGACY
    avg["gap_II_new"] = avg["II_rate1_avg"] - THRESHOLD_II_NEW
    return avg


# ---------------------------------------------------------------------------
# Rolling 3ヶ月（Stage B 用）
# ---------------------------------------------------------------------------

def calculate_rolling_3month(
    df: pd.DataFrame,
    today: Optional[date] = None,
) -> dict:
    """直近 3 ヶ月 rolling 達成率を病棟 × Ⅰ/Ⅱ で返す.

    Args:
        df: ``load_nursing_necessity()`` の戻り値
        today: 基準日。省略時は最新月。

    Returns:
        dict (例):
            {
                "5F": {"I": 0.182, "II": 0.164, "months": ["2026-01", "2026-02", "2026-03"]},
                "6F": {"I": 0.110, "II": 0.090, "months": [...]},
                "合計": {...},
                "current_threshold_I": 0.16,
                "current_threshold_II": 0.14,
            }
    """
    if df.empty:
        return {}

    monthly = calculate_monthly_summary(df)

    # 「最新 3 ヶ月」を決定
    available_months = sorted(monthly["ym"].unique())
    if not available_months:
        return {}

    if today is not None:
        target_ym = today.strftime("%Y-%m")
        # target_ym 以下の最新 3 ヶ月
        eligible = [m for m in available_months if m <= target_ym]
        recent_3 = eligible[-3:]
    else:
        recent_3 = available_months[-3:]

    if len(recent_3) < 3:
        # 3 ヶ月揃わない場合は利用可能分で集計
        pass

    result: dict = {
        "months": recent_3,
        "current_threshold_I": get_threshold(NECESSITY_I, today),
        "current_threshold_II": get_threshold(NECESSITY_II, today),
    }

    for ward in WARDS:
        sub = monthly[(monthly["ward"] == ward) & (monthly["ym"].isin(recent_3))]
        if sub.empty:
            result[ward] = {"I": None, "II": None}
            continue
        i_total = sub["I_total"].sum()
        ii_total = sub["II_total"].sum()
        result[ward] = {
            "I": (sub["I_pass1"].sum() / i_total) if i_total > 0 else None,
            "II": (sub["II_pass1"].sum() / ii_total) if ii_total > 0 else None,
        }
    return result


# ---------------------------------------------------------------------------
# 基準割れ検出（Stage B のアラート基盤）
# ---------------------------------------------------------------------------

def detect_threshold_breaches(
    monthly_df: pd.DataFrame,
    today: Optional[date] = None,
) -> List[dict]:
    """月別の基準割れを検出.

    Args:
        monthly_df: ``calculate_monthly_summary()`` の戻り値
        today: 基準日。省略時は date.today()

    Returns:
        list of dict:
            {
                "ym": "2026-02",
                "ward": "6F",
                "necessity_type": "I" | "II",
                "rate": 0.101,
                "legacy_threshold": 0.16,
                "new_threshold": 0.19,
                "severity": "fail_both" | "fail_new_only",
            }
        rate が new 基準を下回る行のみ返す。
    """
    if monthly_df.empty:
        return []

    breaches: List[dict] = []
    for _, row in monthly_df.iterrows():
        if row["ward"] == WARD_TOTAL:
            continue  # 合計は重複なので除外

        # 必要度Ⅰ
        if row.get("I_total", 0) > 0 and not row["I_meets_new"]:
            severity = "fail_both" if not row["I_meets_legacy"] else "fail_new_only"
            breaches.append({
                "ym": row["ym"],
                "ward": row["ward"],
                "necessity_type": "I",
                "rate": float(row["I_rate1"]),
                "legacy_threshold": THRESHOLD_I_LEGACY,
                "new_threshold": THRESHOLD_I_NEW,
                "severity": severity,
            })

        # 必要度Ⅱ
        if row.get("II_total", 0) > 0 and not row["II_meets_new"]:
            severity = "fail_both" if not row["II_meets_legacy"] else "fail_new_only"
            breaches.append({
                "ym": row["ym"],
                "ward": row["ward"],
                "necessity_type": "II",
                "rate": float(row["II_rate1"]),
                "legacy_threshold": THRESHOLD_II_LEGACY,
                "new_threshold": THRESHOLD_II_NEW,
                "severity": severity,
            })

    return breaches
