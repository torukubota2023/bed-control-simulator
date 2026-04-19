"""週末・連休対策プレゼン用チャート PNG 生成スクリプト (v4).

2025FY 実データ (1,965 件) を使い、
/Users/torukubota/ai-management/docs/admin/slides/weekend_holiday_kpi/charts/
配下の 13 枚の PNG を再生成する。

実行:
    .venv/bin/python3 scripts/generate_weekend_holiday_charts.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

import matplotlib
matplotlib.use("Agg")

import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Japanese Font
# ---------------------------------------------------------------------------


def _set_japanese_font() -> str:
    """Pick first available Japanese-capable font. Returns font name used."""
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
            return name
    return "default"


_FONT_NAME = _set_japanese_font()
print(f"[font] using: {_FONT_NAME}")


# ---------------------------------------------------------------------------
# Design tokens (keep in sync with scripts/design_tokens.py)
# ---------------------------------------------------------------------------

COLOR_ACCENT = "#374151"        # ダークグレー（主色）
COLOR_5F = "#2563EB"             # 青
COLOR_6F = "#DC2626"             # 赤
COLOR_SUCCESS = "#10B981"        # 緑
COLOR_WARNING = "#F59E0B"        # 黄
COLOR_DANGER = "#DC2626"         # 赤
COLOR_INFO = "#2563EB"           # 青
COLOR_BORDER = "#E5E7EB"         # 薄グレー
COLOR_MUTED = "#9CA3AF"          # キャプション
COLOR_TEXT = "#1F2937"
COLOR_BG = "#FFFFFF"

DOW_LABELS = ["月", "火", "水", "木", "金", "土", "日"]
DOW_LABELS_SHORT = DOW_LABELS  # 同じ


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_MAIN = REPO_ROOT / "data" / "actual_admissions_2025fy.csv"
DATA_AUX = REPO_ROOT / "data" / "admissions_consolidated_dedup.csv"
OUT_DIR = REPO_ROOT / "docs" / "admin" / "slides" / "weekend_holiday_kpi" / "charts"


# ---------------------------------------------------------------------------
# Style helpers
# ---------------------------------------------------------------------------


def _style_axes(ax, title: str = "", xlabel: str = "", ylabel: str = "") -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(COLOR_BORDER)
    ax.spines["bottom"].set_color(COLOR_BORDER)
    ax.tick_params(colors=COLOR_TEXT, labelsize=10)
    ax.grid(axis="y", linestyle="--", linewidth=0.6, color=COLOR_BORDER, alpha=0.8)
    ax.set_axisbelow(True)
    if title:
        ax.set_title(title, fontsize=14, color=COLOR_TEXT, pad=14, fontweight="bold")
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=11, color=COLOR_TEXT)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=11, color=COLOR_TEXT)


def _save_fig(fig, filename: str) -> Path:
    path = OUT_DIR / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=COLOR_BG)
    plt.close(fig)
    size_kb = path.stat().st_size / 1024
    print(f"[out] {filename}: {size_kb:.1f} KB")
    return path


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------


def load_main() -> pd.DataFrame:
    df = pd.read_csv(DATA_MAIN, encoding="utf-8-sig")
    df["admission_date"] = pd.to_datetime(df["admission_date"])
    df["dow"] = df["admission_date"].dt.dayofweek  # 0=Mon
    df["month"] = df["admission_date"].dt.to_period("M").astype(str)
    return df


def load_aux() -> pd.DataFrame | None:
    if not DATA_AUX.exists():
        print(f"[warn] aux CSV not found: {DATA_AUX}")
        return None
    df = pd.read_csv(DATA_AUX, encoding="utf-8-sig")
    df["admission_datetime"] = pd.to_datetime(df["admission_datetime"], errors="coerce")
    df["admission_date"] = pd.to_datetime(df["admission_date"], errors="coerce")
    df["register_date"] = pd.to_datetime(df["register_date"], errors="coerce")
    df["register_datetime"] = pd.to_datetime(df["register_datetime"], errors="coerce")
    return df


def daily_counts(df_main: pd.DataFrame) -> pd.DataFrame:
    """0 埋め済み日別入院数 DataFrame (date, dow, count)。"""
    date_range = pd.date_range(
        df_main["admission_date"].min(),
        df_main["admission_date"].max(),
        freq="D",
    )
    daily = pd.DataFrame({"date": date_range})
    daily["dow"] = daily["date"].dt.dayofweek
    counts = df_main.groupby("admission_date").size()
    daily["count"] = daily["date"].map(counts).fillna(0).astype(int)
    return daily


# ---------------------------------------------------------------------------
# Holiday definitions (2025FY)
# ---------------------------------------------------------------------------


GW_DATES = pd.date_range("2025-04-29", "2025-05-05", freq="D")
OBON_DATES = pd.date_range("2025-08-11", "2025-08-16", freq="D")
NY_DATES = pd.date_range("2025-12-28", "2026-01-05", freq="D")


def classify_category(date: pd.Timestamp) -> str:
    """日付 → '連休' / '週末' / '平日'."""
    if date in GW_DATES or date in OBON_DATES or date in NY_DATES:
        return "連休"
    if date.dayofweek >= 5:
        return "週末"
    return "平日"


# ===========================================================================
# Chart 01 — 曜日別入院数（0 埋めあり）
# ===========================================================================


def chart_01(df_main: pd.DataFrame) -> None:
    daily = daily_counts(df_main)
    avg = daily.groupby("dow")["count"].mean()

    fig, ax = plt.subplots(figsize=(11, 5.5))
    colors = [COLOR_ACCENT] * 7
    colors[0] = COLOR_5F       # 月曜（最多）
    colors[6] = COLOR_DANGER   # 日曜（最少）
    bars = ax.bar(DOW_LABELS, avg.values, color=colors, edgecolor="white", width=0.7)

    for bar, v in zip(bars, avg.values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.15,
            f"{v:.2f}",
            ha="center", va="bottom",
            fontsize=12, fontweight="bold", color=COLOR_TEXT,
        )

    # 注釈
    ax.annotate(
        f"月曜ピーク\n{avg.iloc[0]:.2f} 件/日",
        xy=(0, avg.iloc[0]),
        xytext=(0.7, avg.iloc[0] + 1.2),
        fontsize=11, color=COLOR_5F, fontweight="bold",
        arrowprops=dict(arrowstyle="->", color=COLOR_5F, lw=1.4),
    )
    ax.annotate(
        f"日曜最低\n{avg.iloc[6]:.2f} 件/日\n（月曜の {avg.iloc[6]/avg.iloc[0]*100:.0f}%）",
        xy=(6, avg.iloc[6]),
        xytext=(4.3, 3.5),
        fontsize=11, color=COLOR_DANGER, fontweight="bold",
        arrowprops=dict(arrowstyle="->", color=COLOR_DANGER, lw=1.4),
    )

    _style_axes(
        ax,
        title="曜日別 入院数（2025FY 平均、0 埋めあり）",
        xlabel="曜日",
        ylabel="1日あたり平均入院数（件）",
    )
    ax.set_ylim(0, max(avg.values) * 1.25)
    fig.text(
        0.99, 0.01,
        f"n={len(df_main):,} 件 / 期間: 2025-04-01 〜 2026-03-31",
        ha="right", va="bottom", fontsize=9, color=COLOR_MUTED,
    )
    _save_fig(fig, "01_dow_admissions.png")


# ===========================================================================
# Chart 02 — 曜日別ボックスプロット
# ===========================================================================


def chart_02(df_main: pd.DataFrame) -> None:
    daily = daily_counts(df_main)
    data_by_dow = [daily[daily["dow"] == d]["count"].values for d in range(7)]

    fig, ax = plt.subplots(figsize=(11, 5.5))
    bp = ax.boxplot(
        data_by_dow,
        labels=DOW_LABELS,
        patch_artist=True,
        widths=0.6,
        medianprops=dict(color=COLOR_DANGER, linewidth=2),
        whiskerprops=dict(color=COLOR_ACCENT, linewidth=1),
        capprops=dict(color=COLOR_ACCENT, linewidth=1),
        flierprops=dict(
            marker="o", markerfacecolor=COLOR_MUTED,
            markeredgecolor=COLOR_MUTED, markersize=5, alpha=0.6,
        ),
    )
    for i, patch in enumerate(bp["boxes"]):
        if i == 0:
            patch.set_facecolor(COLOR_5F)
            patch.set_alpha(0.35)
        elif i == 6:
            patch.set_facecolor(COLOR_DANGER)
            patch.set_alpha(0.35)
        else:
            patch.set_facecolor(COLOR_ACCENT)
            patch.set_alpha(0.25)
        patch.set_edgecolor(COLOR_ACCENT)
        patch.set_linewidth(1.0)

    # 中央値テキスト
    for i, arr in enumerate(data_by_dow):
        med = np.median(arr)
        ax.text(
            i + 1, med + 0.25, f"中央値 {med:.0f}",
            ha="center", fontsize=9, color=COLOR_TEXT, fontweight="bold",
        )

    _style_axes(
        ax,
        title="曜日別 入院数分布（ボックスプロット、日別 n=52 週）",
        xlabel="曜日",
        ylabel="1日あたり入院数（件）",
    )
    ax.set_ylim(-0.5, max([max(d) if len(d) else 0 for d in data_by_dow]) + 2)
    fig.text(
        0.99, 0.01,
        "箱 = IQR（25-75%）、中線 = 中央値、ひげ = 最小/最大（外れ値除く）",
        ha="right", va="bottom", fontsize=9, color=COLOR_MUTED,
    )
    _save_fig(fig, "02_dow_boxplot.png")


# ===========================================================================
# Chart 03 — 月別推移
# ===========================================================================


def chart_03(df_main: pd.DataFrame) -> None:
    monthly = df_main.groupby("month").size().reindex(
        sorted(df_main["month"].unique()), fill_value=0,
    )
    months = list(monthly.index)
    values = monthly.values
    mean_val = values.mean()

    fig, ax = plt.subplots(figsize=(12, 5.5))
    ax.plot(
        months, values,
        marker="o", markersize=8,
        color=COLOR_ACCENT, linewidth=2.2,
        markerfacecolor=COLOR_ACCENT, markeredgecolor="white",
    )
    ax.axhline(mean_val, color=COLOR_MUTED, linestyle="--", linewidth=1, alpha=0.7)
    ax.text(
        0.1, mean_val + 2,
        f"年平均 {mean_val:.0f} 件",
        ha="left", fontsize=9, color=COLOR_MUTED, fontweight="bold",
    )

    # 数値ラベル
    for i, v in enumerate(values):
        ax.text(
            i, v + 3, f"{v}",
            ha="center", fontsize=10, fontweight="bold", color=COLOR_TEXT,
        )

    # ピーク / 谷のアノテーション
    max_i = int(np.argmax(values))
    min_i = int(np.argmin(values))
    peak_ratio = values[max_i] / mean_val
    trough_ratio = values[min_i] / mean_val

    ax.annotate(
        f"最多ピーク\n{months[max_i]}: {values[max_i]} 件\n（年平均比 ×{peak_ratio:.2f}）",
        xy=(max_i, values[max_i]),
        xytext=(max_i + 0.5, values[max_i] + 20),
        fontsize=10, color=COLOR_SUCCESS, fontweight="bold",
        arrowprops=dict(arrowstyle="->", color=COLOR_SUCCESS, lw=1.4),
    )
    ax.annotate(
        f"最低谷\n{months[min_i]}: {values[min_i]} 件\n（年平均比 ×{trough_ratio:.2f}）",
        xy=(min_i, values[min_i]),
        xytext=(min_i - 0.8, values[min_i] - 30),
        fontsize=10, color=COLOR_DANGER, fontweight="bold",
        arrowprops=dict(arrowstyle="->", color=COLOR_DANGER, lw=1.4),
    )

    _style_axes(
        ax,
        title="月別 入院数推移（2025FY・12 ヶ月）",
        xlabel="年月",
        ylabel="月間入院数（件）",
    )
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    ax.set_ylim(min(values) - 40, max(values) + 40)
    _save_fig(fig, "03_monthly_trend.png")


# ===========================================================================
# Chart 04 — 連休中の落ち込み
# ===========================================================================


def chart_04(df_main: pd.DataFrame) -> None:
    daily = daily_counts(df_main)
    daily["category"] = daily["date"].apply(classify_category)
    stats = daily.groupby("category")["count"].mean().reindex(["平日", "週末", "連休"])

    fig, ax = plt.subplots(figsize=(10, 5.5))
    colors = [COLOR_ACCENT, COLOR_WARNING, COLOR_DANGER]
    bars = ax.bar(stats.index, stats.values, color=colors, edgecolor="white", width=0.55)

    baseline = stats.loc["平日"]
    for bar, (cat, v) in zip(bars, stats.items()):
        diff_pct = (v - baseline) / baseline * 100
        label = f"{v:.2f} 件/日"
        if cat != "平日":
            label += f"\n({diff_pct:+.0f}% vs 平日)"
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.15,
            label,
            ha="center", va="bottom",
            fontsize=11, fontweight="bold", color=COLOR_TEXT,
        )

    _style_axes(
        ax,
        title="カテゴリ別 1 日平均入院数（平日 vs 週末 vs 連休）",
        xlabel="カテゴリ",
        ylabel="1日あたり平均入院数（件）",
    )
    ax.set_ylim(0, baseline * 1.3)
    fig.text(
        0.99, 0.01,
        "連休 = GW (4/29-5/5) + 盆 (8/11-8/16) + 年末年始 (12/28-1/5)",
        ha="right", va="bottom", fontsize=9, color=COLOR_MUTED,
    )
    _save_fig(fig, "04_holiday_drop.png")


# ===========================================================================
# Chart 05 — 救急搬送時間帯分布
# ===========================================================================


def chart_05(df_aux: pd.DataFrame | None) -> None:
    if df_aux is None:
        print("[skip] 05: aux CSV なし")
        return
    emer = df_aux[df_aux["admission_type"] == "当日(予定外/緊急)"].copy()
    emer = emer.dropna(subset=["admission_datetime"])
    emer["hour"] = emer["admission_datetime"].dt.hour
    hours = range(24)
    counts = emer["hour"].value_counts().reindex(hours, fill_value=0)

    fig, ax = plt.subplots(figsize=(12, 5.5))
    colors = []
    for h in hours:
        if 9 <= h <= 17:
            colors.append(COLOR_ACCENT)
        elif 18 <= h <= 22 or 6 <= h <= 8:
            colors.append(COLOR_WARNING)
        else:
            colors.append(COLOR_MUTED)
    ax.bar(list(hours), counts.values, color=colors, edgecolor="white", width=0.85)

    # ピーク帯アノテーション
    peak_hour = int(counts.idxmax())
    ax.annotate(
        f"ピーク {peak_hour}時台\n{counts.max():,} 件",
        xy=(peak_hour, counts.max()),
        xytext=(peak_hour + 3, counts.max() + 8),
        fontsize=11, color=COLOR_DANGER, fontweight="bold",
        arrowprops=dict(arrowstyle="->", color=COLOR_DANGER, lw=1.4),
    )

    # 昼間帯帯の背景帯
    ax.axvspan(8.5, 17.5, color=COLOR_ACCENT, alpha=0.06, zorder=0)
    ax.text(13, counts.max() * 1.05, "日勤帯（9-17時）", ha="center",
            fontsize=10, color=COLOR_ACCENT, fontweight="bold")

    _style_axes(
        ax,
        title="救急搬送 時間帯別分布（2025FY、n=%d 件）" % len(emer),
        xlabel="時刻（時）",
        ylabel="搬送件数（件）",
    )
    ax.set_xticks(list(range(0, 24, 2)))
    ax.set_xlim(-0.5, 23.5)
    ax.set_ylim(0, counts.max() * 1.25)
    fig.text(
        0.99, 0.01,
        "出典: admissions_consolidated_dedup.csv（admission_datetime より時刻抽出）",
        ha="right", va="bottom", fontsize=9, color=COLOR_MUTED,
    )
    _save_fig(fig, "05_emergency_hour.png")


# ===========================================================================
# Chart 06 — カテゴリ（5F/6F × 予定/緊急）比較
# ===========================================================================


def chart_06(df_main: pd.DataFrame) -> None:
    pivot = df_main.groupby(["ward", "admission_route"]).size().unstack(fill_value=0)
    pivot = pivot.reindex(index=["5F", "6F"])
    wards = list(pivot.index)

    scheduled = pivot.get("scheduled", pd.Series([0, 0], index=wards)).values
    emergency = pivot.get("emergency", pd.Series([0, 0], index=wards)).values

    fig, ax = plt.subplots(figsize=(10, 5.5))
    bar_w = 0.5
    x = np.arange(len(wards))
    p1 = ax.bar(x, scheduled, bar_w, label="予定", color=COLOR_5F, edgecolor="white")
    p2 = ax.bar(x, emergency, bar_w, bottom=scheduled, label="緊急",
                color=COLOR_DANGER, edgecolor="white")

    # 数値ラベル
    for i, (s, e) in enumerate(zip(scheduled, emergency)):
        ax.text(x[i], s / 2, f"{s}", ha="center", va="center",
                fontsize=12, fontweight="bold", color="white")
        ax.text(x[i], s + e / 2, f"{e}", ha="center", va="center",
                fontsize=12, fontweight="bold", color="white")
        total = s + e
        ax.text(x[i], total + 15, f"計 {total} 件",
                ha="center", fontsize=11, fontweight="bold", color=COLOR_TEXT)
        emer_pct = e / total * 100 if total else 0
        ax.text(x[i], -total * 0.06,
                f"緊急率 {emer_pct:.1f}%",
                ha="center", fontsize=10, color=COLOR_DANGER)

    ax.set_xticks(x)
    ax.set_xticklabels(wards)
    ax.legend(loc="upper right", frameon=False, fontsize=11)

    _style_axes(
        ax,
        title="病棟別・入院経路内訳（2025FY）",
        xlabel="病棟",
        ylabel="入院数（件）",
    )
    maxval = (scheduled + emergency).max()
    ax.set_ylim(-maxval * 0.12, maxval * 1.15)
    _save_fig(fig, "06_category_comparison.png")


# ===========================================================================
# Chart 07 — GW 日別入院数
# ===========================================================================


def _plot_holiday_daily(
    df_main: pd.DataFrame,
    start: str,
    end: str,
    title: str,
    outname: str,
) -> None:
    daily = daily_counts(df_main)
    mask = (daily["date"] >= start) & (daily["date"] <= end)
    sub = daily[mask].copy()
    weekday_avg = daily[daily["dow"] < 5]["count"].mean()

    fig, ax = plt.subplots(figsize=(11, 5.5))
    labels = [f"{d.strftime('%m/%d')}\n({DOW_LABELS[d.dayofweek]})" for d in sub["date"]]
    colors = [COLOR_DANGER if d.dayofweek >= 5 else COLOR_ACCENT for d in sub["date"]]
    # 祝日（自明な GW/盆/年末年始は赤系強調）
    for i, d in enumerate(sub["date"]):
        if d in GW_DATES and d.dayofweek < 5:
            colors[i] = COLOR_WARNING
        if d in OBON_DATES and d.dayofweek < 5:
            colors[i] = COLOR_WARNING
        if d in NY_DATES and d.dayofweek < 5:
            colors[i] = COLOR_WARNING

    bars = ax.bar(labels, sub["count"].values, color=colors,
                  edgecolor="white", width=0.7)

    for bar, v in zip(bars, sub["count"].values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.2,
            f"{int(v)}",
            ha="center", va="bottom",
            fontsize=12, fontweight="bold", color=COLOR_TEXT,
        )

    ax.axhline(weekday_avg, color=COLOR_5F, linestyle="--", linewidth=1.5, alpha=0.85)
    ax.text(
        len(sub) - 0.4, weekday_avg + 0.3,
        f"通常平日平均 {weekday_avg:.2f} 件/日",
        ha="right", fontsize=10, color=COLOR_5F, fontweight="bold",
    )

    legend_elems = [
        mpatches.Patch(color=COLOR_ACCENT, label="平日（非祝日）"),
        mpatches.Patch(color=COLOR_WARNING, label="祝日（平日扱いの暦）"),
        mpatches.Patch(color=COLOR_DANGER, label="週末"),
    ]
    ax.legend(handles=legend_elems, loc="upper right", frameon=False, fontsize=10)

    _style_axes(ax, title=title, xlabel="日付", ylabel="1日あたり入院数（件）")
    ax.set_ylim(0, max(weekday_avg * 1.8, sub["count"].max() + 2))
    _save_fig(fig, outname)


def chart_07(df_main: pd.DataFrame) -> None:
    _plot_holiday_daily(
        df_main,
        "2025-04-29", "2025-05-05",
        title="GW 期間 日別入院数（2025-04-29 〜 05-05）",
        outname="07_gw_daily.png",
    )


# ===========================================================================
# Chart 08 — 年末年始 日別入院数
# ===========================================================================


def chart_08(df_main: pd.DataFrame) -> None:
    _plot_holiday_daily(
        df_main,
        "2025-12-28", "2026-01-05",
        title="年末年始 日別入院数（2025-12-28 〜 2026-01-05）",
        outname="08_nenmatsu_daily.png",
    )


# ===========================================================================
# Chart 09 — インパクトシミュレーション（従来 vs v4）
# ===========================================================================


def chart_09() -> None:
    days = ["連休前日", "1日目", "2日目", "3日目", "4日目", "連休明け"]
    legacy = [95, 75, 60, 60, 65, 80]   # 従来型（連休前集中）
    v4 = [90, 87, 85, 85, 83, 85]        # v4 分散型

    fig, ax = plt.subplots(figsize=(11.5, 6))
    ax.plot(days, legacy,
            marker="o", markersize=9, color=COLOR_DANGER,
            linewidth=2.2, label="従来型（連休前集中）",
            markerfacecolor=COLOR_DANGER, markeredgecolor="white")
    ax.plot(days, v4,
            marker="s", markersize=9, color=COLOR_SUCCESS,
            linewidth=2.2, label="v4 分散退院型",
            markerfacecolor=COLOR_SUCCESS, markeredgecolor="white")

    # 数値ラベル
    for i, (l, v) in enumerate(zip(legacy, v4)):
        ax.text(i, l - 3, f"{l}%", ha="center", fontsize=10,
                color=COLOR_DANGER, fontweight="bold")
        ax.text(i, v + 2, f"{v}%", ha="center", fontsize=10,
                color=COLOR_SUCCESS, fontweight="bold")

    # 差分ハイライト（連休中の最低点で）
    min_idx = int(np.argmin(legacy))
    diff = v4[min_idx] - legacy[min_idx]
    ax.annotate(
        f"最大差 +{diff} pt",
        xy=(min_idx, (legacy[min_idx] + v4[min_idx]) / 2),
        xytext=(min_idx + 0.8, (legacy[min_idx] + v4[min_idx]) / 2),
        fontsize=14, fontweight="bold", color=COLOR_ACCENT,
        arrowprops=dict(arrowstyle="<->", color=COLOR_ACCENT, lw=2),
    )

    # 目標帯（85-90%）
    ax.axhspan(85, 90, color=COLOR_SUCCESS, alpha=0.08, zorder=0)
    ax.text(len(days) - 0.4, 87.5, "目標帯 85-90%",
            ha="right", fontsize=9, color=COLOR_SUCCESS, fontweight="bold")

    _style_axes(
        ax,
        title="連休 5 日間の病棟稼働率 シミュレーション（従来 vs v4 分散退院型）",
        xlabel="日次",
        ylabel="稼働率（%）",
    )
    ax.set_ylim(50, 100)
    ax.legend(loc="lower left", frameon=False, fontsize=11)
    fig.text(
        0.99, 0.01,
        "※ 想定モデル（連休前日 = 通常日）/ v4 は前倒し退院を分散した仮説シナリオ",
        ha="right", va="bottom", fontsize=9, color=COLOR_MUTED,
    )
    _save_fig(fig, "09_impact_simulation.png")


# ===========================================================================
# Chart 10 — アクションロードマップ（ガント風）
# ===========================================================================


def chart_10() -> None:
    # 各提案の (開始週, 終了週, 説明) を設定。通年 = 0-52
    # x軸: 週（週番号ではなく相対週表示、連休 5 週目に配置）
    # 提案①: 連休 3 週前〜連休明けまで（-3 〜 +1 週）
    # 提案②: 毎週通年
    # 提案③: 毎週（月曜確認）＋ 四半期（理事会）
    # 視覚的には 3 レーン水平バー
    fig, ax = plt.subplots(figsize=(12, 5.5))

    # レーン位置
    lanes = {
        "提案①\n連休前倒し退院\nプロトコル": 2,
        "提案②\n月曜カンファ\n予約最適化": 1,
        "提案③\nKPI モニタリング\n月曜確認 + 四半期理事会": 0,
    }

    # 提案①: 連休ごとにアクティブ帯（GW=4月末, 盆=8月, 年末年始=12月〜1月）
    # 週単位 1-52 で図示
    holiday_weeks = [
        (16, 20, "GW"),        # ~4/17-5/8
        (31, 35, "盆"),        # ~7/31-8/28
        (51, 2, "年末年始"),   # wrapping ignore → 使わない
    ]
    for wk_start, wk_end, label in holiday_weeks[:2]:
        ax.barh(lanes["提案①\n連休前倒し退院\nプロトコル"],
                wk_end - wk_start, left=wk_start, height=0.55,
                color=COLOR_WARNING, edgecolor="white")
        ax.text((wk_start + wk_end) / 2, lanes["提案①\n連休前倒し退院\nプロトコル"],
                label, ha="center", va="center", fontsize=9,
                fontweight="bold", color=COLOR_TEXT)
    # 年末年始は wrap するので最後のみ描画
    ax.barh(lanes["提案①\n連休前倒し退院\nプロトコル"],
            4, left=48, height=0.55,
            color=COLOR_WARNING, edgecolor="white")
    ax.text(50, lanes["提案①\n連休前倒し退院\nプロトコル"], "年末年始",
            ha="center", va="center", fontsize=9,
            fontweight="bold", color=COLOR_TEXT)

    # 提案②: 通年帯
    ax.barh(lanes["提案②\n月曜カンファ\n予約最適化"],
            52, left=0, height=0.55,
            color=COLOR_5F, edgecolor="white", alpha=0.85)
    ax.text(26, lanes["提案②\n月曜カンファ\n予約最適化"], "毎週月曜 8:30 カンファ（通年 52 週）",
            ha="center", va="center", fontsize=10,
            fontweight="bold", color="white")

    # 提案③: 毎週モニタ（通年、色淡） + 四半期マイルストーン
    ax.barh(lanes["提案③\nKPI モニタリング\n月曜確認 + 四半期理事会"],
            52, left=0, height=0.55,
            color=COLOR_ACCENT, edgecolor="white", alpha=0.7)
    ax.text(26, lanes["提案③\nKPI モニタリング\n月曜確認 + 四半期理事会"],
            "週次KPI 確認（月曜朝）",
            ha="center", va="center", fontsize=10,
            fontweight="bold", color="white")
    # 四半期理事会マーカー
    for wk in [12, 25, 38, 51]:
        ax.scatter(wk, lanes["提案③\nKPI モニタリング\n月曜確認 + 四半期理事会"],
                   marker="D", color=COLOR_DANGER, s=120, zorder=5,
                   edgecolor="white", linewidth=1.5)
    ax.text(51.5, lanes["提案③\nKPI モニタリング\n月曜確認 + 四半期理事会"] - 0.35,
            "◆=理事会", ha="right", va="top", fontsize=9,
            color=COLOR_DANGER, fontweight="bold")

    ax.set_yticks(list(lanes.values()))
    ax.set_yticklabels(list(lanes.keys()), fontsize=10)
    ax.set_xticks([0, 13, 26, 39, 52])
    ax.set_xticklabels(["4月", "7月", "10月", "1月", "3月末"])
    _style_axes(
        ax,
        title="v4 3 提案 アクションロードマップ（年間スケジュール）",
        xlabel="実施時期（2025FY）",
        ylabel="",
    )
    ax.set_xlim(0, 52)
    ax.set_ylim(-0.6, 2.6)
    ax.grid(axis="x", linestyle="--", linewidth=0.6, color=COLOR_BORDER, alpha=0.8)
    ax.grid(axis="y", visible=False)
    _save_fig(fig, "10_action_roadmap.png")


# ===========================================================================
# Chart 11 — 予約リードタイム分布
# ===========================================================================


def chart_11(df_aux: pd.DataFrame | None) -> None:
    if df_aux is None:
        print("[skip] 11: aux CSV なし")
        return
    sched = df_aux[df_aux["admission_type"] == "予定"].copy()
    sched["lead"] = (sched["admission_date"] - sched["register_date"]).dt.days
    sched = sched[(sched["lead"] >= 0) & sched["lead"].notna()]

    median_val = sched["lead"].median()
    mean_val = sched["lead"].mean()

    fig, ax = plt.subplots(figsize=(12, 5.5))
    bins = np.arange(0, 70, 2)
    ax.hist(
        sched["lead"].clip(upper=68),
        bins=bins, color=COLOR_ACCENT, edgecolor="white", alpha=0.85,
    )

    ax.axvline(median_val, color=COLOR_DANGER, linestyle="--", linewidth=2)
    ax.axvline(mean_val, color=COLOR_WARNING, linestyle="--", linewidth=2)
    ymax = ax.get_ylim()[1]
    ax.text(median_val, ymax * 0.92, f"中央値 {median_val:.0f} 日",
            color=COLOR_DANGER, fontweight="bold", fontsize=11,
            ha="left", va="center",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                      edgecolor=COLOR_DANGER))
    ax.text(mean_val + 2, ymax * 0.75, f"平均 {mean_val:.1f} 日",
            color=COLOR_WARNING, fontweight="bold", fontsize=11,
            ha="left", va="center",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                      edgecolor=COLOR_WARNING))

    _style_axes(
        ax,
        title=f"予約リードタイム分布（予定入院 n={len(sched):,} 件）",
        xlabel="予約から入院までの日数（日）",
        ylabel="件数（件）",
    )
    ax.set_xlim(0, 70)
    fig.text(
        0.99, 0.01,
        "※ 68日以上は 68 日にクリップ",
        ha="right", va="bottom", fontsize=9, color=COLOR_MUTED,
    )
    _save_fig(fig, "11_lead_time_dist.png")


# ===========================================================================
# Chart 12 — 予約曜日 × 入院曜日 ヒートマップ
# ===========================================================================


def chart_12(df_aux: pd.DataFrame | None) -> None:
    if df_aux is None:
        print("[skip] 12: aux CSV なし")
        return
    sched = df_aux[df_aux["admission_type"] == "予定"].copy()
    sched = sched.dropna(subset=["admission_date", "register_date"])
    sched["admit_dow"] = sched["admission_date"].dt.dayofweek
    sched["reg_dow"] = sched["register_date"].dt.dayofweek
    # 0-6 に固定
    xtab = pd.crosstab(sched["reg_dow"], sched["admit_dow"])
    xtab = xtab.reindex(index=range(7), columns=range(7), fill_value=0)

    fig, ax = plt.subplots(figsize=(10, 6.5))
    im = ax.imshow(xtab.values, cmap="Blues", aspect="auto")
    ax.set_xticks(range(7))
    ax.set_xticklabels(DOW_LABELS)
    ax.set_yticks(range(7))
    ax.set_yticklabels(DOW_LABELS)
    ax.set_xlabel("入院曜日", fontsize=11, color=COLOR_TEXT)
    ax.set_ylabel("予約曜日", fontsize=11, color=COLOR_TEXT)

    # 数値
    vmax = xtab.values.max()
    for i in range(7):
        for j in range(7):
            v = xtab.iat[i, j]
            ax.text(j, i, f"{v}",
                    ha="center", va="center",
                    color="white" if v > vmax / 2 else COLOR_TEXT,
                    fontsize=10, fontweight="bold")

    cbar = plt.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label("件数", fontsize=10, color=COLOR_TEXT)

    ax.set_title("予約曜日 × 入院曜日 ヒートマップ（予定入院のみ、n=%d）" % len(sched),
                 fontsize=14, color=COLOR_TEXT, pad=14, fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    _save_fig(fig, "12_register_dow_vs_admit_dow.png")


# ===========================================================================
# Chart 13 — 連休前 30 日の予約曜日分布
# ===========================================================================


def chart_13(df_aux: pd.DataFrame | None) -> None:
    if df_aux is None:
        print("[skip] 13: aux CSV なし")
        return
    sched = df_aux[df_aux["admission_type"] == "予定"].copy()
    sched = sched.dropna(subset=["admission_date", "register_date"])

    # 連休開始日
    holiday_windows = {
        "GW": ("2025-04-29", "2025-05-05"),
        "盆": ("2025-08-11", "2025-08-16"),
        "年末年始": ("2025-12-28", "2026-01-05"),
    }

    # 各連休について、admission_date が連休期間内のレコードの register_date の曜日を集計
    counts = {name: np.zeros(7, dtype=int) for name in holiday_windows}
    for name, (start, end) in holiday_windows.items():
        sdate = pd.to_datetime(start)
        edate = pd.to_datetime(end)
        mask = (sched["admission_date"] >= sdate) & (sched["admission_date"] <= edate)
        sub = sched[mask]
        for d in sub["register_date"].dt.dayofweek:
            if 0 <= d <= 6:
                counts[name][d] += 1
        # 追加: 連休 30 日前から連休終了直前までの予約（連休にかからない予約）で、
        # admission_date が連休後 14 日以内のレコードも補足的に含める
        win_start = sdate - pd.Timedelta(days=30)
        follow_end = edate + pd.Timedelta(days=14)
        window_mask = (
            (sched["register_date"] >= win_start) &
            (sched["register_date"] <= edate) &
            (sched["admission_date"] >= sdate) &
            (sched["admission_date"] <= follow_end)
        )

    x = np.arange(7)
    width = 0.26
    fig, ax = plt.subplots(figsize=(12, 5.5))
    colors_map = {"GW": COLOR_DANGER, "盆": COLOR_WARNING, "年末年始": COLOR_5F}
    for i, (name, vals) in enumerate(counts.items()):
        ax.bar(x + (i - 1) * width, vals, width,
               label=f"{name}", color=colors_map[name],
               edgecolor="white")
        for xi, v in zip(x, vals):
            if v > 0:
                ax.text(xi + (i - 1) * width, v + 0.3, f"{v}",
                        ha="center", fontsize=9, color=COLOR_TEXT,
                        fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(DOW_LABELS)
    ax.legend(loc="upper right", frameon=False, fontsize=11, title="連休種別",
              title_fontsize=10)

    _style_axes(
        ax,
        title="連休中の入院患者の 予約曜日分布（どの曜日に予約が入るか）",
        xlabel="予約曜日",
        ylabel="予約件数（件）",
    )
    fig.text(
        0.99, 0.01,
        "連休期間に入院した予定入院患者の register_date 曜日を集計",
        ha="right", va="bottom", fontsize=9, color=COLOR_MUTED,
    )
    _save_fig(fig, "13_holiday_lead_window.png")


# ===========================================================================
# Main
# ===========================================================================


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[data] loading: {DATA_MAIN}")
    df_main = load_main()
    print(f"[data] main rows: {len(df_main):,}")

    print(f"[data] loading: {DATA_AUX}")
    df_aux = load_aux()
    if df_aux is not None:
        print(f"[data] aux rows: {len(df_aux):,}")

    print(f"[out] target dir: {OUT_DIR}")
    print()

    chart_01(df_main)
    chart_02(df_main)
    chart_03(df_main)
    chart_04(df_main)
    chart_05(df_aux)
    chart_06(df_main)
    chart_07(df_main)
    chart_08(df_main)
    chart_09()
    chart_10()
    chart_11(df_aux)
    chart_12(df_aux)
    chart_13(df_aux)

    print()
    print("[done] 全チャート生成完了")


if __name__ == "__main__":
    main()
