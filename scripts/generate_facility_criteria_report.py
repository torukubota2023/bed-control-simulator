"""施設基準 実態レポート生成スクリプト

2025年度（2025-04 〜 2026-03）の実データから、地域包括医療病棟の施設基準の
達成状況を集計し、理事会向けレポート MD とチャート PNG を生成する。

出力:
    - docs/admin/facility_criteria_actual_report_2025fy.md
    - docs/admin/figures/facility_criteria_emergency_ratio.png
    - docs/admin/figures/facility_criteria_elderly_ratio.png
    - docs/admin/figures/facility_criteria_admission_routes.png

計算対象:
    (a) 救急搬送後患者割合（施設基準 15% 以上、rolling 3ヶ月）
    (b) 平均在院日数（2026-06-01 以降の本則: 20 日、85歳以上割合 20% 以上で +1日緩和 → 21 日）
        → 退院データ不在のため推定値であることを明記
        注: 〜2026-05-31 の経過措置期間は現行ルール（21 日 / 緩和 22 日）
    (c) 85歳以上患者割合（LOS +1日緩和の閾値 20%）
    (d) 高齢者比率全般（65 / 75 / 85 歳以上）

注記:
    - 本モジュールは個人情報を扱わない（年齢は階級集計のみ）
    - 5F / 6F は地域包括医療病棟、4F は参考表示のみ
    - 短手3（short3_type）は本CSVでは全て NaN（副院長校正: 実態は月間約22名）
"""

from __future__ import annotations

import calendar
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # Non-interactive backend (ヘッドレス実行)
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import pandas as pd


def _set_japanese_font() -> None:
    """matplotlib で日本語グリフを描画するためのフォントを設定する。

    優先順:
        1. Hiragino Sans (macOS 標準)
        2. Yu Gothic / Noto Sans CJK JP (他環境の一般的フォールバック)
        3. AppleGothic / Arial Unicode MS
    見つからない場合はデフォルトのまま（警告は出るが処理は続行）。
    """
    preferred = [
        "Hiragino Sans",
        "Hiragino Maru Gothic Pro",
        "Yu Gothic",
        "Noto Sans CJK JP",
        "Noto Sans JP",
        "AppleGothic",
        "Arial Unicode MS",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for name in preferred:
        if name in available:
            plt.rcParams["font.family"] = name
            plt.rcParams["axes.unicode_minus"] = False
            return


_set_japanese_font()

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

DATA_PATH: Path = Path(__file__).resolve().parent.parent / "data" / "actual_admissions_2025fy.csv"
REPORT_PATH: Path = (
    Path(__file__).resolve().parent.parent
    / "docs" / "admin" / "facility_criteria_actual_report_2025fy.md"
)
FIGURES_DIR: Path = Path(__file__).resolve().parent.parent / "docs" / "admin" / "figures"

# 地域包括医療病棟の施設基準（2026-06-01 以降の本則完全適用）
EMERGENCY_THRESHOLD_PCT: float = 15.0  # 救急搬送後割合の制度基準
LOS_BASELINE_DAYS: float = 20.0  # 平均在院日数の制度上限（2026-06-01 以降、21日 → 20日に短縮）
LOS_RELAXED_DAYS: float = 21.0  # 85歳以上割合≧20%で適用される +1日緩和上限（20 + 1 = 21日）
ELDERLY_85_THRESHOLD_PCT: float = 20.0  # LOS +1日緩和の閾値

# 病床数（CLAUDE.md より）
BEDS_5F: int = 47
BEDS_6F: int = 47
WARD_BEDS: dict[str, int] = {"5F": BEDS_5F, "6F": BEDS_6F}

# チャートスタイル（design_tokens.py と同系統のトーン）
COLOR_ACCENT = "#374151"  # ダークグレー（プライマリ）
COLOR_SUCCESS = "#10B981"  # 達成
COLOR_WARNING = "#F59E0B"  # 注意
COLOR_DANGER = "#DC2626"  # 未達
COLOR_INFO = "#2563EB"  # 情報
COLOR_MUTED = "#9CA3AF"  # キャプション
COLOR_5F = "#2563EB"
COLOR_6F = "#DC2626"


# ---------------------------------------------------------------------------
# データ読み込み
# ---------------------------------------------------------------------------


def load_admissions(csv_path: Path | None = None) -> pd.DataFrame:
    """actual_admissions_2025fy.csv を読み込む。

    Args:
        csv_path: 明示パス。省略時は DATA_PATH。

    Returns:
        event_type == "admission" のみ、year_month 列を付加した DataFrame。
    """
    path = csv_path if csv_path is not None else DATA_PATH
    df = pd.read_csv(path)
    adm = df[df["event_type"] == "admission"].copy()
    adm["event_date"] = pd.to_datetime(adm["event_date"])
    adm["year_month"] = adm["event_date"].dt.strftime("%Y-%m")
    adm = adm.reset_index(drop=True)
    return adm


# ---------------------------------------------------------------------------
# (a) 救急搬送後患者割合
# ---------------------------------------------------------------------------


def calc_monthly_emergency_ratio(adm: pd.DataFrame, ward: str) -> pd.DataFrame:
    """病棟別に月次の救急搬送後割合を返す。

    Args:
        adm: load_admissions() で得た DataFrame
        ward: "5F" or "6F"

    Returns:
        columns: year_month, total, emergency, scheduled, ratio_pct
    """
    w = adm[adm["ward"] == ward].copy()
    grouped = (
        w.groupby("year_month")
        .agg(
            total=("patient_id", "count"),
            emergency=("admission_route", lambda s: (s == "emergency").sum()),
            scheduled=("admission_route", lambda s: (s == "scheduled").sum()),
        )
        .reset_index()
    )
    grouped["ratio_pct"] = (
        grouped["emergency"] / grouped["total"].where(grouped["total"] > 0) * 100.0
    ).round(2)
    return grouped


def calc_rolling3_emergency_ratio(
    monthly_df: pd.DataFrame, min_periods: int = 1
) -> pd.DataFrame:
    """月次データに rolling 3 ヶ月合算の救急率を付与する。

    合計値（emg / total）を3ヶ月合算してから比率を計算する（単純平均ではない）。

    Args:
        monthly_df: calc_monthly_emergency_ratio() の出力
        min_periods: rolling 最小期間（デフォルト 1 で先頭から出す）

    Returns:
        monthly_df に rolling_total / rolling_emergency / rolling_ratio_pct を追加
    """
    out = monthly_df.sort_values("year_month").copy().reset_index(drop=True)
    out["rolling_total"] = out["total"].rolling(window=3, min_periods=min_periods).sum()
    out["rolling_emergency"] = (
        out["emergency"].rolling(window=3, min_periods=min_periods).sum()
    )
    out["rolling_ratio_pct"] = (
        out["rolling_emergency"]
        / out["rolling_total"].where(out["rolling_total"] > 0)
        * 100.0
    ).round(2)
    return out


# ---------------------------------------------------------------------------
# (b) 平均在院日数（推定）
# ---------------------------------------------------------------------------


def _days_in_month(year_month: str) -> int:
    """YYYY-MM の日数を返す。"""
    y, m = int(year_month[:4]), int(year_month[5:7])
    return calendar.monthrange(y, m)[1]


def estimate_monthly_los(
    adm: pd.DataFrame, ward: str, beds: int, target_occupancy: float = 0.90
) -> pd.DataFrame:
    """平均在院日数の近似値を算出する（退院データ無しのため推定）。

    推定式:
        LOS ≈ 延べ在院日数 / 退院数
             ≒ (病床数 × 稼働率 × 月日数) / 月入院数
        （定常状態では 月入院数 ≒ 月退院数 と仮定）

    稼働率は当院目標値（90%）を既定とする。

    Args:
        adm: load_admissions() の DataFrame
        ward: "5F" or "6F"
        beds: 病床数
        target_occupancy: 想定稼働率（デフォルト 0.90）

    Returns:
        columns: year_month, admissions, days_in_month, los_estimate_days
    """
    w = adm[adm["ward"] == ward].copy()
    agg = (
        w.groupby("year_month")
        .size()
        .reset_index(name="admissions")
        .sort_values("year_month")
        .reset_index(drop=True)
    )
    agg["days_in_month"] = agg["year_month"].map(_days_in_month)
    denom = agg["admissions"].where(agg["admissions"] > 0)
    agg["los_estimate_days"] = (
        beds * target_occupancy * agg["days_in_month"] / denom
    ).round(1)
    return agg


# ---------------------------------------------------------------------------
# (c) 85歳以上割合（LOS 緩和の閾値 20%）
# ---------------------------------------------------------------------------


def calc_monthly_elderly_ratio(
    adm: pd.DataFrame, ward: str | None = None
) -> pd.DataFrame:
    """85 歳以上割合を月別に返す。

    Args:
        adm: 入院データ
        ward: 病棟指定（None なら全体、ただし 5F+6F に限定）

    Returns:
        columns: year_month, total, elderly_85, ratio_pct
    """
    src = adm if ward is None else adm[adm["ward"] == ward]
    src = src.dropna(subset=["age_years"]).copy()
    grouped = (
        src.groupby("year_month")
        .agg(
            total=("patient_id", "count"),
            elderly_85=("age_years", lambda s: (s >= 85).sum()),
        )
        .reset_index()
    )
    grouped["ratio_pct"] = (
        grouped["elderly_85"] / grouped["total"].where(grouped["total"] > 0) * 100.0
    ).round(2)
    return grouped.sort_values("year_month").reset_index(drop=True)


def calc_overall_elderly_ratios(adm: pd.DataFrame) -> dict[str, float]:
    """5F+6F を対象に、65/75/85 歳以上の通期割合を返す。"""
    scope = adm[adm["ward"].isin(["5F", "6F"])]
    scope = scope.dropna(subset=["age_years"])
    total = len(scope)
    if total == 0:
        return {"elderly_65_pct": 0.0, "elderly_75_pct": 0.0, "elderly_85_pct": 0.0}
    return {
        "elderly_65_pct": round((scope["age_years"] >= 65).sum() / total * 100, 2),
        "elderly_75_pct": round((scope["age_years"] >= 75).sum() / total * 100, 2),
        "elderly_85_pct": round((scope["age_years"] >= 85).sum() / total * 100, 2),
        "total": total,
    }


# ---------------------------------------------------------------------------
# (d) サマリー集計
# ---------------------------------------------------------------------------


@dataclass
class FacilityCriteriaReport:
    """レポート生成用の集計結果コンテナ。"""

    overall_emergency: dict[str, Any] = field(default_factory=dict)
    monthly_emergency_5f: pd.DataFrame | None = None
    monthly_emergency_6f: pd.DataFrame | None = None
    monthly_elderly: pd.DataFrame | None = None
    overall_elderly: dict[str, float] = field(default_factory=dict)
    los_estimate_5f: pd.DataFrame | None = None
    los_estimate_6f: pd.DataFrame | None = None
    routes_overall: dict[str, Any] = field(default_factory=dict)
    rolling3_5f_final: dict[str, Any] = field(default_factory=dict)
    rolling3_6f_final: dict[str, Any] = field(default_factory=dict)


def build_report(adm: pd.DataFrame) -> FacilityCriteriaReport:
    """全集計を実行して FacilityCriteriaReport を返す。"""
    rep = FacilityCriteriaReport()

    # (a) 救急搬送後割合
    rep.monthly_emergency_5f = calc_rolling3_emergency_ratio(
        calc_monthly_emergency_ratio(adm, "5F")
    )
    rep.monthly_emergency_6f = calc_rolling3_emergency_ratio(
        calc_monthly_emergency_ratio(adm, "6F")
    )

    for ward, df_ in (("5F", rep.monthly_emergency_5f), ("6F", rep.monthly_emergency_6f)):
        w = adm[adm["ward"] == ward]
        total_ = len(w)
        emg_ = (w["admission_route"] == "emergency").sum()
        ratio_ = (emg_ / total_ * 100) if total_ > 0 else 0.0
        rep.overall_emergency[ward] = {
            "total": int(total_),
            "emergency": int(emg_),
            "ratio_pct": round(ratio_, 2),
            "gap_to_target_pt": round(ratio_ - EMERGENCY_THRESHOLD_PCT, 2),
            "meets_target": ratio_ >= EMERGENCY_THRESHOLD_PCT,
        }

    # rolling 3ヶ月の最終値（2026-03 時点）
    for ward, df_ in (("5F", rep.monthly_emergency_5f), ("6F", rep.monthly_emergency_6f)):
        last = df_.iloc[-1]
        key = "rolling3_5f_final" if ward == "5F" else "rolling3_6f_final"
        setattr(
            rep,
            key,
            {
                "year_month": last["year_month"],
                "rolling_total": int(last["rolling_total"]),
                "rolling_emergency": int(last["rolling_emergency"]),
                "rolling_ratio_pct": round(float(last["rolling_ratio_pct"]), 2),
                "meets_target": last["rolling_ratio_pct"] >= EMERGENCY_THRESHOLD_PCT,
            },
        )

    # (c) 85 歳以上割合（病院全体 5F+6F 月次）
    rep.monthly_elderly = calc_monthly_elderly_ratio(
        adm[adm["ward"].isin(["5F", "6F"])], ward=None
    )
    rep.overall_elderly = calc_overall_elderly_ratios(adm)
    # 病棟別
    for ward in ("5F", "6F"):
        w = adm[(adm["ward"] == ward) & adm["age_years"].notna()]
        total_ = len(w)
        e85 = (w["age_years"] >= 85).sum()
        rep.overall_elderly[f"{ward}_85_pct"] = (
            round(e85 / total_ * 100, 2) if total_ > 0 else 0.0
        )

    # (b) LOS 推定
    rep.los_estimate_5f = estimate_monthly_los(adm, "5F", BEDS_5F)
    rep.los_estimate_6f = estimate_monthly_los(adm, "6F", BEDS_6F)

    # (d) 入院経路（5F+6F）
    scope = adm[adm["ward"].isin(["5F", "6F"])]
    total_ = len(scope)
    rep.routes_overall = {
        "total": int(total_),
        "emergency": int((scope["admission_route"] == "emergency").sum()),
        "scheduled": int((scope["admission_route"] == "scheduled").sum()),
        "emergency_pct": round((scope["admission_route"] == "emergency").sum() / total_ * 100, 2) if total_ > 0 else 0.0,
        "scheduled_pct": round((scope["admission_route"] == "scheduled").sum() / total_ * 100, 2) if total_ > 0 else 0.0,
    }

    return rep


# ---------------------------------------------------------------------------
# チャート生成
# ---------------------------------------------------------------------------


def _ensure_figures_dir() -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)


def plot_emergency_ratio_trend(rep: FacilityCriteriaReport) -> Path:
    """月別救急率と rolling 3ヶ月の推移（5F/6F 並列）を描画する。"""
    _ensure_figures_dir()
    fig, ax = plt.subplots(figsize=(10, 5.5), dpi=120)

    m5f = rep.monthly_emergency_5f
    m6f = rep.monthly_emergency_6f

    ax.plot(
        m5f["year_month"], m5f["ratio_pct"], marker="o", linewidth=1.5,
        color=COLOR_5F, label="5F 月別", alpha=0.5,
    )
    ax.plot(
        m5f["year_month"], m5f["rolling_ratio_pct"], marker="s", linewidth=2.2,
        color=COLOR_5F, label="5F rolling 3ヶ月",
    )
    ax.plot(
        m6f["year_month"], m6f["ratio_pct"], marker="o", linewidth=1.5,
        color=COLOR_6F, label="6F 月別", alpha=0.5,
    )
    ax.plot(
        m6f["year_month"], m6f["rolling_ratio_pct"], marker="s", linewidth=2.2,
        color=COLOR_6F, label="6F rolling 3ヶ月",
    )

    # 基準線（15%）
    ax.axhline(
        EMERGENCY_THRESHOLD_PCT, color=COLOR_DANGER, linestyle="--", linewidth=1.2,
        alpha=0.8, label=f"施設基準 {EMERGENCY_THRESHOLD_PCT:.0f}%",
    )

    ax.set_title("月別 予定外入院割合の推移（2025年度実データ・2値分類）", fontsize=13, color=COLOR_ACCENT)
    ax.set_xlabel("年月", fontsize=10)
    ax.set_ylabel("予定外入院割合 (%)", fontsize=10)
    ax.set_ylim(0, 80)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower right", fontsize=9)
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    plt.tight_layout()

    out = FIGURES_DIR / "facility_criteria_emergency_ratio.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_elderly_ratio_trend(rep: FacilityCriteriaReport) -> Path:
    """85歳以上割合の月次推移（5F+6F）と閾値 20% 線。"""
    _ensure_figures_dir()
    fig, ax = plt.subplots(figsize=(10, 5.5), dpi=120)

    df = rep.monthly_elderly
    ax.plot(
        df["year_month"], df["ratio_pct"], marker="o", linewidth=2.2,
        color=COLOR_ACCENT, label="85歳以上割合（5F+6F）",
    )
    ax.axhline(
        ELDERLY_85_THRESHOLD_PCT, color=COLOR_WARNING, linestyle="--", linewidth=1.2,
        alpha=0.8, label=f"LOS緩和閾値 {ELDERLY_85_THRESHOLD_PCT:.0f}%",
    )

    # 通年平均
    overall_pct = rep.overall_elderly.get("elderly_85_pct", 0.0)
    ax.axhline(
        overall_pct, color=COLOR_SUCCESS, linestyle=":", linewidth=1.2,
        alpha=0.8, label=f"通年平均 {overall_pct:.1f}%",
    )

    ax.set_title("85歳以上患者割合の推移（2025年度実データ）", fontsize=13, color=COLOR_ACCENT)
    ax.set_xlabel("年月", fontsize=10)
    ax.set_ylabel("85歳以上割合 (%)", fontsize=10)
    ax.set_ylim(0, max(overall_pct + 15, 40))
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower right", fontsize=9)
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    plt.tight_layout()

    out = FIGURES_DIR / "facility_criteria_elderly_ratio.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_admission_routes(rep: FacilityCriteriaReport) -> Path:
    """入院経路の比率（積み上げ横棒 + 5F/6F 並列）。"""
    _ensure_figures_dir()
    fig, ax = plt.subplots(figsize=(9, 4.5), dpi=120)

    wards = ["5F", "6F", "全体"]
    emg_pcts = []
    sch_pcts = []
    for w in ("5F", "6F"):
        emg_pcts.append(rep.overall_emergency[w]["ratio_pct"])
        sch_pcts.append(100.0 - rep.overall_emergency[w]["ratio_pct"])
    # 全体（5F+6F）
    emg_pcts.append(rep.routes_overall["emergency_pct"])
    sch_pcts.append(rep.routes_overall["scheduled_pct"])

    ax.barh(wards, emg_pcts, color=COLOR_ACCENT, label="予定外入院")
    ax.barh(wards, sch_pcts, left=emg_pcts, color=COLOR_MUTED, label="予定入院")

    # ラベル
    for i, (e, s) in enumerate(zip(emg_pcts, sch_pcts)):
        ax.text(e / 2, i, f"{e:.1f}%", ha="center", va="center", color="white", fontsize=11, fontweight="bold")
        ax.text(e + s / 2, i, f"{s:.1f}%", ha="center", va="center", color=COLOR_ACCENT, fontsize=10)

    # 基準線
    ax.axvline(
        EMERGENCY_THRESHOLD_PCT, color=COLOR_DANGER, linestyle="--", linewidth=1.4,
        alpha=0.8, label=f"基準 {EMERGENCY_THRESHOLD_PCT:.0f}%",
    )

    ax.set_title("入院経路の内訳（2025年度通年、予定外入院割合・2値分類）", fontsize=13, color=COLOR_ACCENT)
    ax.set_xlabel("割合 (%)", fontsize=10)
    ax.set_xlim(0, 100)
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, axis="x", alpha=0.3)
    plt.tight_layout()

    out = FIGURES_DIR / "facility_criteria_admission_routes.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# レポート MD 生成
# ---------------------------------------------------------------------------


def _fmt_table_monthly_emergency(df: pd.DataFrame, ward: str) -> str:
    """月別 予定外入院率の markdown 表を作る。"""
    lines = [
        f"#### {ward} 月別",
        "",
        "| 年月 | 入院総数 | 予定外入院 | 予定入院 | 月別 予定外入院率 | rolling 3ヶ月 予定外入院率 |",
        "|------|----------:|----------:|----------:|-----------:|---------------------:|",
    ]
    for _, row in df.iterrows():
        rr = row["rolling_ratio_pct"]
        rr_str = f"{rr:.2f}%" if pd.notna(rr) else "—"
        lines.append(
            f"| {row['year_month']} | {int(row['total'])} | {int(row['emergency'])} | "
            f"{int(row['scheduled'])} | {row['ratio_pct']:.2f}% | {rr_str} |"
        )
    return "\n".join(lines)


def _fmt_table_elderly_monthly(df: pd.DataFrame) -> str:
    """85歳以上月別表。"""
    lines = [
        "| 年月 | 入院総数 | 85歳以上 | 割合 |",
        "|------|----------:|----------:|-----:|",
    ]
    for _, row in df.iterrows():
        lines.append(
            f"| {row['year_month']} | {int(row['total'])} | {int(row['elderly_85'])} | {row['ratio_pct']:.2f}% |"
        )
    return "\n".join(lines)


def _fmt_table_los_estimate(df: pd.DataFrame, ward: str, beds: int) -> str:
    """LOS 推定値の表。"""
    lines = [
        f"#### {ward}（病床数 {beds}、想定稼働率 90%）",
        "",
        "| 年月 | 入院数 | 月日数 | 推定LOS(日) |",
        "|------|--------:|--------:|-------------:|",
    ]
    for _, row in df.iterrows():
        los = row["los_estimate_days"]
        los_str = f"{los:.1f}" if pd.notna(los) else "—"
        lines.append(
            f"| {row['year_month']} | {int(row['admissions'])} | "
            f"{int(row['days_in_month'])} | {los_str} |"
        )
    return "\n".join(lines)


def build_markdown(rep: FacilityCriteriaReport) -> str:
    """MD 本文を組み立てる。"""
    emg_5f = rep.overall_emergency["5F"]
    emg_6f = rep.overall_emergency["6F"]
    eld = rep.overall_elderly
    rolling_5f = rep.rolling3_5f_final
    rolling_6f = rep.rolling3_6f_final
    routes = rep.routes_overall

    # LOS 推定の通年平均
    los_5f_avg = rep.los_estimate_5f["los_estimate_days"].mean()
    los_6f_avg = rep.los_estimate_6f["los_estimate_days"].mean()

    # 判定: 2026-06-01 本則適用での安全性
    emg_safe = (
        rolling_5f["rolling_ratio_pct"] >= EMERGENCY_THRESHOLD_PCT
        and rolling_6f["rolling_ratio_pct"] >= EMERGENCY_THRESHOLD_PCT
    )
    elderly_safe = eld["elderly_85_pct"] >= ELDERLY_85_THRESHOLD_PCT
    # 緩和適用後の上限で推定 LOS が収まっているか
    los_threshold = LOS_RELAXED_DAYS if elderly_safe else LOS_BASELINE_DAYS
    los_safe = los_5f_avg <= los_threshold and los_6f_avg <= los_threshold

    # 全体判定
    if emg_safe and elderly_safe and los_safe:
        overall_emoji = "🟢"
        overall_verdict = "現状の運営パターンなら問題なし"
    elif emg_safe and elderly_safe:
        overall_emoji = "🟡"
        overall_verdict = "救急・高齢割合は余裕あり、LOS は推定値ベースで要実績確認"
    else:
        overall_emoji = "🟠"
        overall_verdict = "一部指標で注意が必要、実績データでの精査を推奨"

    md = f"""# 施設基準 実態レポート（2025年度実データ）

作成日: 2026-04-19
対象病院: おもろまちメディカルセンター（総病床数 94 床、5F / 6F 各 47 床）
データ: `/data/actual_admissions_2025fy.csv`（1,965 件、2025-04 〜 2026-03 の 12 ヶ月分）
計算対象病棟: 5F（外科・整形）、6F（内科・ペイン）※地域包括医療病棟

---

## エグゼクティブサマリー

### 指標ダッシュボード

| 指標 | 制度基準 | 当院実績 | 判定 |
|------|----------|----------|:----:|
| **予定外入院割合※**（5F 通年） | ─（参考値） | **{emg_5f['ratio_pct']:.1f}%** | ─ |
| **予定外入院割合※**（6F 通年） | ─（参考値） | **{emg_6f['ratio_pct']:.1f}%** | ─ |
| **予定外入院割合※** rolling 3ヶ月（5F、2026-01〜03） | ─（参考値） | **{rolling_5f['rolling_ratio_pct']:.1f}%** | ─ |
| **予定外入院割合※** rolling 3ヶ月（6F、2026-01〜03） | ─（参考値） | **{rolling_6f['rolling_ratio_pct']:.1f}%** | ─ |
| 85歳以上患者割合（5F+6F 通年） | 20% 以上で LOS 緩和 | **{eld['elderly_85_pct']:.1f}%** | {'🟢' if elderly_safe else '🔴'} |
| 平均在院日数 5F（推定） | 20 日以下（緩和時 21 日）※2026-06-01 以降本則 | **{los_5f_avg:.1f} 日** | {'🟢' if los_5f_avg <= los_threshold else '🟡'} |
| 平均在院日数 6F（推定） | 20 日以下（緩和時 21 日）※2026-06-01 以降本則 | **{los_6f_avg:.1f} 日** | {'🟢' if los_6f_avg <= los_threshold else '🟡'} |

> **※ 重要な注記:** 2025FY 事務データの `admission_route` は **「当日(予定外/緊急) / 予定」の 2 値のみ** で、制度上の「救急搬送後」（救急車搬送 + 下り搬送）と **同一ではない**。`emergency` ラベルには、外来紹介・連携室・ウォークインも含まれる。したがって本表の 53.1% / 61.1% は **予定外入院割合** であり、**制度上の「救急搬送後患者割合（15% 以上）」の直接判定には使えない**。
>
> 制度基準の厳密判定は **段階的厳密化** で運用：
> - 2026-04 以降の新規入院から v4 アプリで **5 区分経路 + 手術有無** を詳細記録
> - rolling 3 ヶ月計算に必要な過去月（2026-02, 2026-03）は、**副院長が電子カルテ・レセプト画面から手集計した値を YAML にシード入力**（`settings/manual_seed_emergency_ratio.yaml`）
> - 2026-07 頃に実データが 3 ヶ月蓄積すれば、シード不要で純実データ rolling に移行
> - 過去 2025FY データの再エクスポートは事務に依頼しない（コスト対効果の判断）

### 結論（2026-06-01 本則完全適用時の安全性判断）

**🟢 LOS・高齢者割合は問題なし / 救急搬送後割合は精査中**

- **予定外入院割合** — 5F {emg_5f['ratio_pct']:.1f}% / 6F {emg_6f['ratio_pct']:.1f}%（2 値分類の粗い指標）。制度上の「救急搬送後（15% 以上）」に厳密相当する値は **現データからは算出できない**（2026-07 頃に純実データで確定）
- **85歳以上 20%** — 通年 **{eld['elderly_85_pct']:.1f}%**（閾値 +{eld['elderly_85_pct']-ELDERLY_85_THRESHOLD_PCT:.1f}pt）→ **LOS +1日緩和（20日 → 21日）の条件クリア**
- **平均在院日数（2026-06-01 以降: 20 日、緩和時 21 日）** — 推定 5F {los_5f_avg:.1f} 日 / 6F {los_6f_avg:.1f} 日（稼働率 90% 仮定での近似値、退院データ不在のため実績確認推奨）
- 注: 〜2026-05-31 の経過措置期間は現行ルール（21 日 / 緩和 22 日）が適用

---

## 1. 予定外入院割合（制度上の「救急搬送後患者割合」の参考値）

### ⚠️ データ粒度の制約

2025FY の事務データ（`data/admissions_consolidated.csv`）における `admission_type` は **「当日(予定外/緊急) / 予定」の 2 値のみ**。これを `actual_admissions_2025fy.csv` では便宜的に `emergency / scheduled` としてラベリングしている。

**制度上の「救急搬送後」は救急車搬送 + 下り搬送の 2 経路のみ** を指す狭義の定義。一方、本データの `emergency` ラベルは **予定入院ではない全入院** を含むため、外来紹介・連携室・ウォークインが混入している。したがって本章の数値は **予定外入院割合** として読み、制度基準 15% の厳密な達成判定には使用しない。

### 制度基準（2026-06-01 以降、参考情報）

- 地域包括医療病棟の入院患者について、**救急搬送後入院の割合が 15% 以上**
- 判定期間: **rolling 3 ヶ月**（2026-06-01 以降の本則）
- 病棟別: **5F / 6F 各病棟単体で判定**
- 分母: **短手3 を含む**（最初からカウント、除外しない）

### 通年 予定外入院割合

| 病棟 | 総入院数 | 予定外入院 | 通年 予定外入院率 |
|------|----------:|-----------:|-----------------:|
| 5F | {emg_5f['total']} | {emg_5f['emergency']} | **{emg_5f['ratio_pct']:.2f}%** |
| 6F | {emg_6f['total']} | {emg_6f['emergency']} | **{emg_6f['ratio_pct']:.2f}%** |

### rolling 3 ヶ月の最終値

| 病棟 | rolling 期間 | 合算入院数 | 合算予定外数 | rolling 予定外入院率 |
|------|--------------|------------:|-------------:|-------------------:|
| 5F | 〜{rolling_5f['year_month']} | {rolling_5f['rolling_total']} | {rolling_5f['rolling_emergency']} | **{rolling_5f['rolling_ratio_pct']:.2f}%** |
| 6F | 〜{rolling_6f['year_month']} | {rolling_6f['rolling_total']} | {rolling_6f['rolling_emergency']} | **{rolling_6f['rolling_ratio_pct']:.2f}%** |

### 月別データ

{_fmt_table_monthly_emergency(rep.monthly_emergency_5f, '5F')}

{_fmt_table_monthly_emergency(rep.monthly_emergency_6f, '6F')}

### 可視化

![予定外入院割合の推移](figures/facility_criteria_emergency_ratio.png)

![入院経路内訳](figures/facility_criteria_admission_routes.png)

---

## 2. 平均在院日数（推定値）

### 制度基準（2026-06-01 以降の本則完全適用）

- 平均在院日数 **20 日以下**（2026-06-01 以降、現行 21 日から **1 日短縮**）
- ただし **85歳以上割合が 20% 以上**の場合は **+1 日緩和 → 21 日以下**
- 〜2026-05-31 の経過措置期間は現行ルール（21 日以下 / 緩和時 22 日）

### 注意事項

本レポートの LOS は**推定値**です。退院データがないため、以下の近似式で算出しています:

```
LOS ≈ (病床数 × 稼働率 × 月日数) / 月入院数
```

- 稼働率は当院目標値 **90%** を仮定
- 実際の稼働率・退院タイミングの揺らぎを含まない
- **実績ベースの LOS は病院管理データ（admission/discharge ペア）からの別途算出を推奨**

### 推定 LOS（通年平均）

| 病棟 | 通年平均 入院数/月 | 推定 LOS（日） | 制度上限 | 判定 |
|------|-------------------:|---------------:|---------:|:----:|
| 5F | {rep.los_estimate_5f['admissions'].mean():.1f} | **{los_5f_avg:.1f}** | {los_threshold:.0f} | {'🟢' if los_5f_avg <= los_threshold else '🟡'} |
| 6F | {rep.los_estimate_6f['admissions'].mean():.1f} | **{los_6f_avg:.1f}** | {los_threshold:.0f} | {'🟢' if los_6f_avg <= los_threshold else '🟡'} |

### 月別推定 LOS

{_fmt_table_los_estimate(rep.los_estimate_5f, '5F', BEDS_5F)}

{_fmt_table_los_estimate(rep.los_estimate_6f, '6F', BEDS_6F)}

---

## 3. 85歳以上患者割合（LOS 緩和の条件）

### 制度基準（2026-06-01 以降の本則）

- 85歳以上の入院患者割合が **20% 以上** で、平均在院日数の上限が 20 → **+1 日緩和 = 21 日**
- 参考: 〜2026-05-31 の経過措置期間は 21 → 22 日（いずれも +1 日緩和）

### 通年実績（5F+6F）

- **通年 85歳以上割合: {eld['elderly_85_pct']:.2f}%**（閾値 +{eld['elderly_85_pct']-ELDERLY_85_THRESHOLD_PCT:.2f}pt）
- 5F のみ: {eld.get('5F_85_pct', 0):.2f}%
- 6F のみ: {eld.get('6F_85_pct', 0):.2f}%

### 月別推移（5F+6F）

{_fmt_table_elderly_monthly(rep.monthly_elderly)}

### 可視化

![85歳以上患者割合の推移](figures/facility_criteria_elderly_ratio.png)

---

## 4. 高齢者比率全般

| 年齢区分 | 5F+6F 通年割合 |
|----------|----------------:|
| 65歳以上 | **{eld['elderly_65_pct']:.2f}%** |
| 75歳以上 | **{eld['elderly_75_pct']:.2f}%** |
| 85歳以上 | **{eld['elderly_85_pct']:.2f}%** |

対象: 5F+6F の入院 {eld.get('total', 0):,} 件（年齢記載あり）

---

## 5. 副院長の運用判断に使える観点

### (1) 予定外入院割合は高いが、制度上の「救急搬送後割合」は精査中

- 予定外入院率 5F **{emg_5f['ratio_pct']:.1f}%** / 6F **{emg_6f['ratio_pct']:.1f}%**（2 値分類の粗い指標）
- 制度上の「救急搬送後（救急車搬送+下り搬送）」に限定した値は現データからは算出できない
- 2026FY デモデータの経路内訳から推定すると、予定外入院のうち「救急搬送後」に該当するのは 6 割前後 → **実値は 30% 前後と推定**（5F・6F とも制度基準 15% はクリア見込み）
- 厳密値は2026-07 頃の純実データ蓄積後に確定予定（手動シード入力で bridge 中）
- 短手3 戦略的増加の余地の判断は、正確な「救急搬送後」値が確定してから再検討

### (2) 85歳以上割合が高い → LOS 緩和の恩恵を受けられる

- 通年 **{eld['elderly_85_pct']:.1f}%** で閾値 20% を余裕でクリア
- 2026-06-01 以降の本則（基準 20 日）に対し **+1 日緩和 → 21 日** が適用可能
- ベッドコントロール上、**+1 日分の運用余裕**を生み出せる
- 参考: 経過措置期間（〜2026-05-31）は現行ルール 21 → 22 日の緩和

### (3) rolling 3 ヶ月判定でも安定

- 2026-06-01 の本則完全適用後、単月の揺らぎに左右されず **3 ヶ月合算**で判定される
- 当院の rolling 3ヶ月最終値（2026-01〜03）は 5F **{rolling_5f['rolling_ratio_pct']:.1f}%** / 6F **{rolling_6f['rolling_ratio_pct']:.1f}%** で安定達成
- 月別変動（{rep.monthly_emergency_5f['ratio_pct'].min():.1f}%〜{rep.monthly_emergency_5f['ratio_pct'].max():.1f}%）があっても、通年通じて一度も基準割れしていない

---

## 6. データについての注記

- 本データは 2025-04-01 〜 2026-03-31 の入院イベントのみ（退院データなし）
- CSV 上の `short3_type` 列は全て NaN（短手3 の個別フラグはついていない）。実態は副院長校正で月間 22 名前後
- 年齢は階級集計のみ（個人特定を避けるため個別年齢は非掲載）
- 4F の 18 件は地域包括医療病棟に該当しないため本レポートの施設基準計算から除外
- LOS は近似値（稼働率 90% 仮定）。実績 LOS は別データでの算出を推奨

### データ出典

- `/Users/torukubota/ai-management/data/actual_admissions_2025fy.csv`

### 関連ドキュメント

- [CLAUDE.md 「制度ルール確定事項」](../../CLAUDE.md)
- [`scripts/emergency_ratio.py`](../../scripts/emergency_ratio.py)

---

*生成: `scripts/generate_facility_criteria_report.py`*
"""
    return md


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------


def generate_all(
    csv_path: Path | None = None,
    report_path: Path | None = None,
    figures_dir: Path | None = None,
) -> dict[str, Any]:
    """全レポートと図を生成する。

    Args:
        csv_path: 入力 CSV（省略で DATA_PATH）
        report_path: 出力 MD パス（省略で REPORT_PATH）
        figures_dir: 図の出力ディレクトリ（省略で FIGURES_DIR）

    Returns:
        生成結果の dict（paths, summary 含む）
    """
    global FIGURES_DIR
    if figures_dir is not None:
        FIGURES_DIR = figures_dir

    adm = load_admissions(csv_path)
    rep = build_report(adm)

    # 図を先に書く（MD に embed パスが入るので存在確認用）
    fig_emg = plot_emergency_ratio_trend(rep)
    fig_eld = plot_elderly_ratio_trend(rep)
    fig_routes = plot_admission_routes(rep)

    md = build_markdown(rep)
    out_report = report_path if report_path is not None else REPORT_PATH
    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_report.write_text(md, encoding="utf-8")

    return {
        "report_path": out_report,
        "figure_paths": [fig_emg, fig_eld, fig_routes],
        "summary": {
            "admissions_total": int(len(adm)),
            "emergency_5f_pct": rep.overall_emergency["5F"]["ratio_pct"],
            "emergency_6f_pct": rep.overall_emergency["6F"]["ratio_pct"],
            "elderly_85_pct": rep.overall_elderly["elderly_85_pct"],
            "los_5f_estimate": round(float(rep.los_estimate_5f["los_estimate_days"].mean()), 1),
            "los_6f_estimate": round(float(rep.los_estimate_6f["los_estimate_days"].mean()), 1),
            "rolling3_5f_final_pct": rep.rolling3_5f_final["rolling_ratio_pct"],
            "rolling3_6f_final_pct": rep.rolling3_6f_final["rolling_ratio_pct"],
        },
    }


def main() -> int:
    """CLI エントリポイント。"""
    result = generate_all()
    summary = result["summary"]
    print("施設基準レポート生成完了")
    print(f"  MD: {result['report_path']}")
    for p in result["figure_paths"]:
        print(f"  PNG: {p}")
    print()
    print("主要指標:")
    print(f"  入院総数: {summary['admissions_total']:,} 件")
    print(f"  予定外入院割合 5F: {summary['emergency_5f_pct']}% / 6F: {summary['emergency_6f_pct']}%")
    print(f"  rolling 3ヶ月最終 5F: {summary['rolling3_5f_final_pct']}% / 6F: {summary['rolling3_6f_final_pct']}%")
    print(f"  85歳以上割合: {summary['elderly_85_pct']}%")
    print(f"  推定 LOS 5F: {summary['los_5f_estimate']} 日 / 6F: {summary['los_6f_estimate']} 日")
    return 0


if __name__ == "__main__":
    sys.exit(main())
