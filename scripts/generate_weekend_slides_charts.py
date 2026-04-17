"""
経営陣向けプレゼン用チャート生成（dedup 後データ / 案B: リードタイム分析 3 枚追加）

出力: docs/admin/slides/weekend_holiday_kpi/charts/01..13.png（10 は変更不要なため再生成対象外）
データ: data/admissions_consolidated_dedup.csv（1,876 件、2025-04-01 〜 2026-03-31）

実行: python3 scripts/generate_weekend_slides_charts.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

plt.rcParams["font.family"] = "Hiragino Sans"
plt.rcParams["axes.unicode_minus"] = False

# 色定義
COLOR_PLAN = "#2E86AB"      # 予定=青
COLOR_EMERG = "#F18F01"     # 緊急=橙
COLOR_ALERT = "#C73E1D"     # 警告=赤
COLOR_OK = "#4CAF50"        # 強調=緑
COLOR_GREY = "#9E9E9E"

DATA_PATH = Path("/Users/kubotatoru/ai-management/data/admissions_consolidated_dedup.csv")
OUT_DIR = Path("/Users/kubotatoru/ai-management/docs/admin/slides/weekend_holiday_kpi/charts")
OUT_DIR.mkdir(parents=True, exist_ok=True)

FIGSIZE = (16, 9)
DPI = 120

DOW_LABELS = ["月", "火", "水", "木", "金", "土", "日"]

# 大型連休定義
HOLIDAYS = {
    "GW2025": ("2025-05-03", "2025-05-06"),
    "お盆2025": ("2025-08-09", "2025-08-17"),
    "シルバーW": ("2025-09-13", "2025-09-15"),
    "年末年始": ("2025-12-27", "2026-01-04"),
    "冬連休": ("2026-02-21", "2026-02-23"),
}

# 単発祝日（連休に含まれないもの）
SINGLE_HOLIDAYS = [
    "2025-04-29", "2025-07-21", "2025-10-13", "2025-11-03", "2025-11-24",
    "2025-12-23", "2026-01-13", "2026-02-11", "2026-03-20",
]


def load_data() -> pd.DataFrame:
    df = pd.read_csv(
        DATA_PATH,
        parse_dates=["admission_datetime", "register_datetime"],
    )
    df["ad"] = df["admission_datetime"].dt.date
    df["dow"] = df["admission_datetime"].dt.dayofweek
    df["hour"] = df["admission_datetime"].dt.hour
    return df


def _all_dates() -> pd.DatetimeIndex:
    return pd.date_range("2025-04-01", "2026-03-31")


def _in_period(ts: pd.Series, start: str, end: str) -> pd.Series:
    s = pd.Timestamp(start)
    e = pd.Timestamp(end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    return (ts >= s) & (ts <= e)


def _holiday_dateset() -> set:
    out: set = set()
    for s, e in HOLIDAYS.values():
        d = pd.Timestamp(s)
        while d <= pd.Timestamp(e):
            out.add(d.date())
            d += pd.Timedelta(days=1)
    return out


# ------------------------------------------------------------
# 01: 曜日別 1日あたり平均入院数（積み上げ棒）
# ------------------------------------------------------------
def chart_01_dow(df: pd.DataFrame) -> None:
    all_d = _all_dates()
    dow_days = pd.Series([d.dayofweek for d in all_d]).value_counts().sort_index()

    plan_by_dow = df[df["type_short"] == "予定"].groupby("dow").size().reindex(range(7), fill_value=0)
    emerg_by_dow = df[df["type_short"] == "緊急"].groupby("dow").size().reindex(range(7), fill_value=0)

    plan_avg = (plan_by_dow / dow_days).values
    emerg_avg = (emerg_by_dow / dow_days).values

    fig, ax = plt.subplots(figsize=FIGSIZE)
    x = np.arange(7)
    bars1 = ax.bar(x, plan_avg, color=COLOR_PLAN, label="予定", edgecolor="white")
    bars2 = ax.bar(x, emerg_avg, bottom=plan_avg, color=COLOR_EMERG, label="緊急", edgecolor="white")

    for i in range(7):
        total = plan_avg[i] + emerg_avg[i]
        ax.text(i, total + 0.15, f"{total:.2f}", ha="center", va="bottom", fontsize=13, fontweight="bold")
        if plan_avg[i] > 0.3:
            ax.text(i, plan_avg[i] / 2, f"{plan_avg[i]:.2f}", ha="center", va="center", fontsize=11, color="white", fontweight="bold")
        if emerg_avg[i] > 0.3:
            ax.text(i, plan_avg[i] + emerg_avg[i] / 2, f"{emerg_avg[i]:.2f}", ha="center", va="center", fontsize=11, color="white", fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(DOW_LABELS, fontsize=14)
    ax.set_ylabel("1日あたり平均入院件数", fontsize=13)
    ax.set_title("曜日別 1日あたり平均入院数（2025-04 〜 2026-03, n=1,876）", fontsize=16, fontweight="bold", pad=15)
    ax.legend(loc="upper right", fontsize=12)
    ax.set_ylim(0, max(plan_avg + emerg_avg) * 1.2)
    ax.grid(axis="y", alpha=0.3)

    # 月/日の強調
    ax.annotate("月曜に集中",
                xy=(0, plan_avg[0] + emerg_avg[0]), xytext=(0.2, plan_avg[0] + emerg_avg[0] + 1.2),
                fontsize=12, color=COLOR_ALERT, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=COLOR_ALERT, lw=1.5))
    ax.annotate("日曜はほぼゼロ",
                xy=(6, plan_avg[6] + emerg_avg[6]), xytext=(4.3, 2.0),
                fontsize=12, color=COLOR_ALERT, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=COLOR_ALERT, lw=1.5))

    plt.tight_layout()
    plt.savefig(OUT_DIR / "01_dow_admissions.png", dpi=DPI, bbox_inches="tight")
    plt.close()
    return plan_avg, emerg_avg


# ------------------------------------------------------------
# 02: 曜日別 日次分布（箱ひげ図）
# ------------------------------------------------------------
def chart_02_boxplot(df: pd.DataFrame) -> None:
    daily = df.groupby("ad").size().reset_index(name="cnt")
    daily["dow"] = pd.to_datetime(daily["ad"]).dt.dayofweek
    # 0-count日補完
    full = pd.DataFrame({"ad": _all_dates().date})
    full = full.merge(daily, on="ad", how="left").fillna({"cnt": 0})
    full["dow"] = pd.to_datetime(full["ad"]).dt.dayofweek

    data = [full[full["dow"] == d]["cnt"].values for d in range(7)]

    fig, ax = plt.subplots(figsize=FIGSIZE)
    colors = [COLOR_PLAN] * 4 + [COLOR_EMERG] + [COLOR_ALERT] * 2
    bp = ax.boxplot(data, labels=DOW_LABELS, patch_artist=True,
                    medianprops=dict(color="black", linewidth=2),
                    meanprops=dict(marker="D", markerfacecolor="white", markeredgecolor="black", markersize=9),
                    showmeans=True)
    for patch, c in zip(bp["boxes"], colors):
        patch.set_facecolor(c)
        patch.set_alpha(0.6)

    ax.set_ylabel("1日あたり入院件数", fontsize=13)
    ax.set_title("曜日別 日次分布（箱ひげ図 — 白菱形=平均、中央線=中央値）", fontsize=16, fontweight="bold", pad=15)
    ax.grid(axis="y", alpha=0.3)

    # 注釈
    weekday_patch = mpatches.Patch(color=COLOR_PLAN, alpha=0.6, label="平日（月〜木）")
    fri_patch = mpatches.Patch(color=COLOR_EMERG, alpha=0.6, label="金曜（境界）")
    weekend_patch = mpatches.Patch(color=COLOR_ALERT, alpha=0.6, label="週末（土・日）")
    ax.legend(handles=[weekday_patch, fri_patch, weekend_patch], loc="upper right", fontsize=12)

    ax.text(0.02, 0.96, "箱位置の重なりがない = 構造的な需要パターン",
            transform=ax.transAxes, fontsize=13, color=COLOR_ALERT, fontweight="bold",
            verticalalignment="top",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#FFF3E0", edgecolor=COLOR_ALERT))

    plt.tight_layout()
    plt.savefig(OUT_DIR / "02_dow_boxplot.png", dpi=DPI, bbox_inches="tight")
    plt.close()


# ------------------------------------------------------------
# 03: 月別トレンド
# ------------------------------------------------------------
def chart_03_monthly(df: pd.DataFrame) -> None:
    df2 = df.copy()
    df2["ym"] = df2["admission_datetime"].dt.to_period("M")
    all_d = _all_dates()
    month_days: dict = {}
    for d in all_d:
        k = d.to_period("M")
        month_days[k] = month_days.get(k, 0) + 1

    mc = df2.groupby("ym").size()
    months = sorted(mc.index.tolist())
    avgs = [mc[m] / month_days[m] for m in months]
    labels = [str(m) for m in months]

    fig, ax = plt.subplots(figsize=FIGSIZE)
    x = np.arange(len(months))
    ax.plot(x, avgs, marker="o", markersize=10, linewidth=2.5, color=COLOR_PLAN, markerfacecolor="white", markeredgewidth=2)

    for i, v in enumerate(avgs):
        ax.text(i, v + 0.08, f"{v:.2f}", ha="center", fontsize=11, fontweight="bold")

    # ピーク・谷強調
    min_i = int(np.argmin(avgs))
    max_i = int(np.argmax(avgs))
    ax.scatter([min_i], [avgs[min_i]], s=300, color=COLOR_ALERT, zorder=5, marker="v")
    ax.scatter([max_i], [avgs[max_i]], s=300, color=COLOR_OK, zorder=5, marker="^")

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, fontsize=11)
    ax.set_ylabel("1日あたり平均入院件数", fontsize=13)
    ax.set_title("月別 1日あたり平均入院件数（12ヶ月間）", fontsize=16, fontweight="bold", pad=15)
    ax.grid(alpha=0.3)
    ax.set_ylim(min(avgs) - 0.5, max(avgs) + 0.8)

    ax.annotate(f"最低 {avgs[min_i]:.2f}件/日", xy=(min_i, avgs[min_i]), xytext=(min_i - 0.5, avgs[min_i] - 0.45),
                fontsize=12, color=COLOR_ALERT, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=COLOR_ALERT))
    ax.annotate(f"最高 {avgs[max_i]:.2f}件/日", xy=(max_i, avgs[max_i]), xytext=(max_i - 1.5, avgs[max_i] + 0.4),
                fontsize=12, color=COLOR_OK, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=COLOR_OK))

    plt.tight_layout()
    plt.savefig(OUT_DIR / "03_monthly_trend.png", dpi=DPI, bbox_inches="tight")
    plt.close()
    return dict(zip(labels, avgs))


# ------------------------------------------------------------
# 04: 大型連休の落ち込み
# ------------------------------------------------------------
def chart_04_holiday_drop(df: pd.DataFrame) -> None:
    results = []
    for name, (s, e) in HOLIDAYS.items():
        s_ts = pd.Timestamp(s)
        e_ts = pd.Timestamp(e)
        days = (e_ts - s_ts).days + 1
        in_h = df[_in_period(df["admission_datetime"], s, e)]
        avg_h = len(in_h) / days
        prior_s = (s_ts - pd.Timedelta(days=14)).strftime("%Y-%m-%d")
        prior_e = (s_ts - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        pri = df[_in_period(df["admission_datetime"], prior_s, prior_e)]
        avg_p = len(pri) / 14
        drop = (avg_h - avg_p) / avg_p * 100 if avg_p > 0 else 0
        results.append((name, days, avg_h, avg_p, drop))

    names = [r[0] for r in results]
    drops = [r[4] for r in results]
    avgs_h = [r[2] for r in results]
    avgs_p = [r[3] for r in results]

    fig, ax = plt.subplots(figsize=FIGSIZE)
    x = np.arange(len(names))
    width = 0.38
    b1 = ax.bar(x - width / 2, avgs_p, width, label="直前2週 1日平均", color=COLOR_PLAN, alpha=0.85)
    b2 = ax.bar(x + width / 2, avgs_h, width, label="連休中 1日平均", color=COLOR_ALERT, alpha=0.85)

    for i, (h, p, d) in enumerate(zip(avgs_h, avgs_p, drops)):
        ax.text(i - width / 2, p + 0.1, f"{p:.2f}", ha="center", fontsize=10)
        ax.text(i + width / 2, h + 0.1, f"{h:.2f}", ha="center", fontsize=10)
        ax.text(i, max(h, p) + 1.0, f"{d:+.1f}%", ha="center", fontsize=12, color=COLOR_ALERT, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels([f"{r[0]}\n({r[1]}日)" for r in results], fontsize=12)
    ax.set_ylabel("1日あたり平均入院件数", fontsize=13)
    ax.set_title("大型連休の入院数 — 直前2週との比較", fontsize=16, fontweight="bold", pad=15)
    ax.legend(loc="upper right", fontsize=12)
    ax.grid(axis="y", alpha=0.3)
    ax.set_ylim(0, max(avgs_p) * 1.5)

    plt.tight_layout()
    plt.savefig(OUT_DIR / "04_holiday_drop.png", dpi=DPI, bbox_inches="tight")
    plt.close()
    return results


# ------------------------------------------------------------
# 05: 緊急入院の時刻分布
# ------------------------------------------------------------
def chart_05_emergency_hour(df: pd.DataFrame) -> None:
    em = df[df["type_short"] == "緊急"].copy()
    hr = em["hour"].value_counts().sort_index().reindex(range(24), fill_value=0)
    total = hr.sum()
    peak_mask = (hr.index >= 13) & (hr.index <= 18)

    fig, ax = plt.subplots(figsize=FIGSIZE)
    colors = [COLOR_ALERT if peak_mask[i] else COLOR_EMERG for i in range(24)]
    bars = ax.bar(range(24), hr.values, color=colors, edgecolor="white")
    for i, v in enumerate(hr.values):
        if v > 0:
            ax.text(i, v + 2, str(v), ha="center", fontsize=9)

    ax.set_xticks(range(24))
    ax.set_xticklabels([f"{h}時" for h in range(24)], fontsize=10)
    ax.set_ylabel("件数（年間）", fontsize=13)
    ax.set_title(f"緊急入院の時刻分布（年間 {total}件）", fontsize=16, fontweight="bold", pad=15)
    ax.grid(axis="y", alpha=0.3)

    peak_sum = hr[13:19].sum()
    ratio = peak_sum / total * 100
    ax.axvspan(12.5, 18.5, alpha=0.12, color=COLOR_ALERT)
    ax.text(0.5, 0.95,
            f"13-18時 に {peak_sum}件（{ratio:.1f}%）集中\n"
            f"深夜 0-5時 は {hr[0:6].sum()}件 / 夜間 19-23時 は {hr[19:].sum()}件",
            transform=ax.transAxes, fontsize=13, color=COLOR_ALERT, fontweight="bold",
            verticalalignment="top",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#FFF3E0", edgecolor=COLOR_ALERT))

    ax.text(0.98, 0.95, "午前退院の床は\n同日午後に充填される",
            transform=ax.transAxes, fontsize=12, color=COLOR_OK, fontweight="bold",
            verticalalignment="top", horizontalalignment="right",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#E8F5E9", edgecolor=COLOR_OK))

    plt.tight_layout()
    plt.savefig(OUT_DIR / "05_emergency_hour.png", dpi=DPI, bbox_inches="tight")
    plt.close()
    return total, peak_sum, ratio


# ------------------------------------------------------------
# 06: 区分別 1日平均
# ------------------------------------------------------------
def chart_06_category(df: pd.DataFrame) -> None:
    all_d = _all_dates()
    holiday_set = _holiday_dateset()
    single_set = {pd.Timestamp(x).date() for x in SINGLE_HOLIDAYS if pd.Timestamp(x).date() not in holiday_set}

    categories = {"通常平日": [], "週末": [], "単発祝日": [], "大型連休": []}
    for d in all_d:
        dd = d.date()
        if dd in holiday_set:
            categories["大型連休"].append(dd)
        elif dd in single_set:
            categories["単発祝日"].append(dd)
        elif d.dayofweek >= 5:
            categories["週末"].append(dd)
        else:
            categories["通常平日"].append(dd)

    daily = df.groupby("ad").size()
    cat_avg = {}
    cat_n = {}
    for c, dates in categories.items():
        vals = [daily.get(d, 0) for d in dates]
        cat_avg[c] = sum(vals) / len(dates) if dates else 0
        cat_n[c] = len(dates)

    fig, ax = plt.subplots(figsize=FIGSIZE)
    names = list(cat_avg.keys())
    vals = [cat_avg[n] for n in names]
    colors = [COLOR_PLAN, COLOR_ALERT, "#FFB300", "#7B1FA2"]

    bars = ax.bar(names, vals, color=colors, edgecolor="white", width=0.62)
    for i, (b, v) in enumerate(zip(bars, vals)):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.15, f"{v:.2f}/日\n({cat_n[names[i]]}日)",
                ha="center", fontsize=12, fontweight="bold")

    # ギャップ矢印
    gap = cat_avg["通常平日"] - cat_avg["週末"]
    ax.annotate("", xy=(1, cat_avg["週末"] + 0.2), xytext=(1, cat_avg["通常平日"] - 0.2),
                arrowprops=dict(arrowstyle="<->", color=COLOR_ALERT, lw=2.5))
    ax.text(1.3, (cat_avg["通常平日"] + cat_avg["週末"]) / 2,
            f"ギャップ\n-{gap:.2f}件/日",
            fontsize=13, color=COLOR_ALERT, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#FFF3E0", edgecolor=COLOR_ALERT))

    ax.set_ylabel("1日あたり平均入院件数", fontsize=13)
    ax.set_title("区分別 1日平均入院件数", fontsize=16, fontweight="bold", pad=15)
    ax.grid(axis="y", alpha=0.3)
    ax.set_ylim(0, max(vals) * 1.25)

    plt.tight_layout()
    plt.savefig(OUT_DIR / "06_category_comparison.png", dpi=DPI, bbox_inches="tight")
    plt.close()
    return cat_avg, cat_n


# ------------------------------------------------------------
# 07: GW 具体例（日次）
# ------------------------------------------------------------
def chart_07_gw(df: pd.DataFrame) -> None:
    start = pd.Timestamp("2025-04-26")
    end = pd.Timestamp("2025-05-11")
    dd = pd.date_range(start, end)
    daily = df[_in_period(df["admission_datetime"], start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))]
    by = daily.groupby([daily["admission_datetime"].dt.date, "type_short"]).size().unstack(fill_value=0)
    by = by.reindex(pd.Index([d.date() for d in dd]), fill_value=0)
    plan_v = by.get("予定", pd.Series([0] * len(dd))).values
    emerg_v = by.get("緊急", pd.Series([0] * len(dd))).values

    fig, ax = plt.subplots(figsize=FIGSIZE)
    x = np.arange(len(dd))
    ax.bar(x, plan_v, color=COLOR_PLAN, label="予定", edgecolor="white")
    ax.bar(x, emerg_v, bottom=plan_v, color=COLOR_EMERG, label="緊急", edgecolor="white")

    # GW期間シェード
    gw_s_idx = (pd.Timestamp("2025-05-03") - start).days
    gw_e_idx = (pd.Timestamp("2025-05-06") - start).days
    ax.axvspan(gw_s_idx - 0.5, gw_e_idx + 0.5, alpha=0.15, color=COLOR_ALERT, label="GW期間")

    for i in range(len(dd)):
        total = plan_v[i] + emerg_v[i]
        if total > 0:
            ax.text(i, total + 0.3, str(total), ha="center", fontsize=10, fontweight="bold")

    labels = [f"{d.month}/{d.day}\n{DOW_LABELS[d.dayofweek]}" for d in dd]
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylabel("1日あたり入院件数", fontsize=13)
    ax.set_title("GW2025 前後の日次入院数（2025-04-26 〜 2025-05-11）", fontsize=16, fontweight="bold", pad=15)
    ax.legend(loc="upper left", fontsize=12)
    ax.grid(axis="y", alpha=0.3)

    # 連休明け強調
    post_idx = (pd.Timestamp("2025-05-07") - start).days
    post_val = plan_v[post_idx] + emerg_v[post_idx]
    ax.annotate(f"連休明け {int(post_val)}件\n（平日平均の約2倍）",
                xy=(post_idx, post_val), xytext=(post_idx - 2.5, post_val + 2),
                fontsize=12, color=COLOR_ALERT, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=COLOR_ALERT, lw=1.8))

    plt.tight_layout()
    plt.savefig(OUT_DIR / "07_gw_daily.png", dpi=DPI, bbox_inches="tight")
    plt.close()
    return int(post_val)


# ------------------------------------------------------------
# 08: 年末年始 具体例
# ------------------------------------------------------------
def chart_08_nenmatsu(df: pd.DataFrame) -> None:
    start = pd.Timestamp("2025-12-20")
    end = pd.Timestamp("2026-01-11")
    dd = pd.date_range(start, end)
    daily = df[_in_period(df["admission_datetime"], start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))]
    by = daily.groupby([daily["admission_datetime"].dt.date, "type_short"]).size().unstack(fill_value=0)
    by = by.reindex(pd.Index([d.date() for d in dd]), fill_value=0)
    plan_v = by.get("予定", pd.Series([0] * len(dd))).values
    emerg_v = by.get("緊急", pd.Series([0] * len(dd))).values

    fig, ax = plt.subplots(figsize=FIGSIZE)
    x = np.arange(len(dd))
    ax.bar(x, plan_v, color=COLOR_PLAN, label="予定", edgecolor="white")
    ax.bar(x, emerg_v, bottom=plan_v, color=COLOR_EMERG, label="緊急", edgecolor="white")

    s_idx = (pd.Timestamp("2025-12-27") - start).days
    e_idx = (pd.Timestamp("2026-01-04") - start).days
    ax.axvspan(s_idx - 0.5, e_idx + 0.5, alpha=0.15, color=COLOR_ALERT, label="年末年始期間")

    for i in range(len(dd)):
        total = plan_v[i] + emerg_v[i]
        if total > 0:
            ax.text(i, total + 0.3, str(total), ha="center", fontsize=9, fontweight="bold")

    labels = [f"{d.month}/{d.day}\n{DOW_LABELS[d.dayofweek]}" for d in dd]
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9, rotation=0)
    ax.set_ylabel("1日あたり入院件数", fontsize=13)
    ax.set_title("年末年始 前後の日次入院数（2025-12-20 〜 2026-01-11）", fontsize=16, fontweight="bold", pad=15)
    ax.legend(loc="upper right", fontsize=12)
    ax.grid(axis="y", alpha=0.3)

    # 助走期間の注釈
    ax.text(0.02, 0.95, "助走期間（12/20 から漸減）\n→ 退院計画が立てやすい",
            transform=ax.transAxes, fontsize=12, color=COLOR_OK, fontweight="bold",
            verticalalignment="top",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#E8F5E9", edgecolor=COLOR_OK))

    # 1/5 連休明け
    post_idx = (pd.Timestamp("2026-01-05") - start).days
    post_val = plan_v[post_idx] + emerg_v[post_idx]
    ax.annotate(f"連休明け {int(post_val)}件",
                xy=(post_idx, post_val), xytext=(post_idx - 3, post_val + 1.8),
                fontsize=12, color=COLOR_ALERT, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=COLOR_ALERT, lw=1.8))

    plt.tight_layout()
    plt.savefig(OUT_DIR / "08_nenmatsu_daily.png", dpi=DPI, bbox_inches="tight")
    plt.close()
    return int(post_val)


# ------------------------------------------------------------
# 09: 改善インパクト
# ------------------------------------------------------------
def chart_09_impact(cat_avg: dict) -> None:
    current_weekend = cat_avg["週末"]
    normal_wd = cat_avg["通常平日"]
    gap = normal_wd - current_weekend
    # 1/3 を取り戻す想定
    target_weekend = current_weekend + gap / 3

    fig, ax = plt.subplots(figsize=FIGSIZE)
    cats = ["現状\n週末平均", "改善後\n週末平均 (1/3吸収)", "参考\n通常平日平均"]
    vals = [current_weekend, target_weekend, normal_wd]
    colors = [COLOR_ALERT, COLOR_OK, COLOR_PLAN]
    bars = ax.bar(cats, vals, color=colors, width=0.5, edgecolor="white")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.15, f"{v:.2f}/日", ha="center", fontsize=13, fontweight="bold")

    # 吸収効果
    absorbed = target_weekend - current_weekend
    ax.annotate("", xy=(1, target_weekend - 0.1), xytext=(1, current_weekend + 0.1),
                arrowprops=dict(arrowstyle="->", color=COLOR_OK, lw=2.5))
    ax.text(1.35, (current_weekend + target_weekend) / 2,
            f"吸収効果\n+{absorbed:.2f}件/日",
            fontsize=13, color=COLOR_OK, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#E8F5E9", edgecolor=COLOR_OK))

    # 年間効果試算
    weekend_days = 104 + 28  # 週末 + 連休期間約
    annual_gain = absorbed * weekend_days
    annual_yen = annual_gain * 14  # 1件14万円想定
    ax.text(0.02, 0.95,
            f"想定年間吸収: {annual_gain:.0f}件 × 14万円 ≒ {annual_yen/10000:.0f}百万円/年\n"
            f"（週末104日 + 連休28日 想定）",
            transform=ax.transAxes, fontsize=12, color="black", fontweight="bold",
            verticalalignment="top",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#FFFDE7", edgecolor=COLOR_PLAN))

    ax.set_ylabel("1日あたり平均入院件数", fontsize=13)
    ax.set_title("Phase 1 改善インパクト試算（ギャップの 1/3 吸収）", fontsize=16, fontweight="bold", pad=15)
    ax.grid(axis="y", alpha=0.3)
    ax.set_ylim(0, normal_wd * 1.3)

    plt.tight_layout()
    plt.savefig(OUT_DIR / "09_impact_simulation.png", dpi=DPI, bbox_inches="tight")
    plt.close()


# ------------------------------------------------------------
# 11: 予定入院リードタイム分布
# ------------------------------------------------------------
def chart_11_lead_time(df: pd.DataFrame) -> None:
    plan = df[df["type_short"] == "予定"].copy()
    plan["lead_days"] = (
        pd.to_datetime(plan["admission_datetime"].dt.date) - pd.to_datetime(plan["register_datetime"].dt.date)
    ).dt.days

    median = plan["lead_days"].median()
    mean = plan["lead_days"].mean()
    p25 = plan["lead_days"].quantile(0.25)
    p75 = plan["lead_days"].quantile(0.75)
    p90 = plan["lead_days"].quantile(0.90)

    # 8日以上比率
    over8 = (plan["lead_days"] >= 8).sum() / len(plan) * 100

    fig, ax = plt.subplots(figsize=FIGSIZE)
    # 0..60 day histogram
    bins = np.arange(0, 62, 1)
    clipped = plan["lead_days"].clip(lower=0, upper=60)
    ax.hist(clipped, bins=bins, color=COLOR_PLAN, alpha=0.85, edgecolor="white")

    # P25-P75 shade
    ax.axvspan(p25, p75, alpha=0.15, color=COLOR_OK, label=f"P25-P75 ({p25:.0f}-{p75:.0f}日)")
    # median line
    ax.axvline(median, color=COLOR_ALERT, linestyle="--", linewidth=2.5, label=f"中央値 {median:.0f}日")
    ax.axvline(mean, color="black", linestyle=":", linewidth=2, label=f"平均 {mean:.1f}日")

    ax.set_xlabel("予約から入院までの日数（60日以上は 60 に集約）", fontsize=13)
    ax.set_ylabel("件数", fontsize=13)
    ax.set_title(f"予定入院のリードタイム分布（n={len(plan)}, 平均 {mean:.1f}日前に予約）",
                 fontsize=16, fontweight="bold", pad=15)
    ax.legend(loc="upper right", fontsize=12)
    ax.grid(axis="y", alpha=0.3)
    ax.set_xlim(-0.5, 60.5)

    ax.text(0.98, 0.75,
            f"約 {over8:.0f}% が 8日以上前に予約\n→ 連休前後の曜日配置は運用可能",
            transform=ax.transAxes, fontsize=13, color=COLOR_OK, fontweight="bold",
            verticalalignment="top", horizontalalignment="right",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#E8F5E9", edgecolor=COLOR_OK))

    plt.tight_layout()
    plt.savefig(OUT_DIR / "11_lead_time_dist.png", dpi=DPI, bbox_inches="tight")
    plt.close()
    return median, mean, p25, p75, p90, over8


# ------------------------------------------------------------
# 12: 登録曜日 × 入院曜日 ヒートマップ（予定入院）
# ------------------------------------------------------------
def chart_12_reg_admit_heatmap(df: pd.DataFrame) -> None:
    plan = df[df["type_short"] == "予定"].copy()
    plan["ad_dow"] = plan["admission_datetime"].dt.dayofweek
    plan["rg_dow"] = plan["register_datetime"].dt.dayofweek
    mat = plan.groupby(["rg_dow", "ad_dow"]).size().unstack(fill_value=0)
    mat = mat.reindex(index=range(7), columns=range(7), fill_value=0)

    fig, ax = plt.subplots(figsize=FIGSIZE)
    im = ax.imshow(mat.values, cmap="Blues", aspect="auto")

    # Cell labels
    for i in range(7):
        for j in range(7):
            v = mat.iloc[i, j]
            color = "white" if v > mat.values.max() * 0.5 else "black"
            if v > 0:
                ax.text(j, i, int(v), ha="center", va="center", color=color, fontsize=11, fontweight="bold")

    ax.set_xticks(range(7))
    ax.set_yticks(range(7))
    ax.set_xticklabels(DOW_LABELS, fontsize=13)
    ax.set_yticklabels(DOW_LABELS, fontsize=13)
    ax.set_xlabel("入院曜日", fontsize=13)
    ax.set_ylabel("登録曜日", fontsize=13)
    ax.set_title("予定入院: 登録曜日 × 入院曜日（件数ヒートマップ）", fontsize=16, fontweight="bold", pad=15)

    cbar = plt.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label("件数", fontsize=12)

    ax.text(0.5, -0.18,
            "月〜水に登録された予定入院の多くは火〜金に配置 → 曜日選択の自由度あり",
            transform=ax.transAxes, fontsize=12, color=COLOR_OK, fontweight="bold",
            verticalalignment="top", horizontalalignment="center",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#E8F5E9", edgecolor=COLOR_OK))

    plt.tight_layout()
    plt.savefig(OUT_DIR / "12_register_dow_vs_admit_dow.png", dpi=DPI, bbox_inches="tight")
    plt.close()


# ------------------------------------------------------------
# 13: 連休前後の予約タイミング
# ------------------------------------------------------------
def chart_13_holiday_lead(df: pd.DataFrame) -> None:
    holiday_windows = {
        "GW2025":   ("2025-04-26", "2025-05-03", "2025-05-06", "2025-05-13"),
        "お盆2025": ("2025-08-02", "2025-08-09", "2025-08-17", "2025-08-24"),
        "シルバーW": ("2025-09-06", "2025-09-13", "2025-09-15", "2025-09-22"),
        "年末年始": ("2025-12-20", "2025-12-27", "2026-01-04", "2026-01-11"),
    }

    plan = df[df["type_short"] == "予定"].copy()

    names = []
    pre_counts = []
    in_counts = []
    post_counts = []
    for name, (pre_s, h_s, h_e, post_e) in holiday_windows.items():
        pre = plan[_in_period(plan["admission_datetime"], pre_s, (pd.Timestamp(h_s) - pd.Timedelta(days=1)).strftime("%Y-%m-%d"))]
        inside = plan[_in_period(plan["admission_datetime"], h_s, h_e)]
        post = plan[_in_period(plan["admission_datetime"], (pd.Timestamp(h_e) + pd.Timedelta(days=1)).strftime("%Y-%m-%d"), post_e)]
        names.append(name)
        pre_counts.append(len(pre))
        in_counts.append(len(inside))
        post_counts.append(len(post))

    fig, ax = plt.subplots(figsize=FIGSIZE)
    y = np.arange(len(names))
    height = 0.62
    b1 = ax.barh(y, pre_counts, height, color=COLOR_PLAN, label="連休前週（開始前7日）")
    b2 = ax.barh(y, in_counts, height, left=pre_counts, color=COLOR_GREY, label="連休期間中")
    left3 = [p + i for p, i in zip(pre_counts, in_counts)]
    b3 = ax.barh(y, post_counts, height, left=left3, color=COLOR_OK, label="連休明け週（終了翌日+7日）")

    for i, (p, inn, po) in enumerate(zip(pre_counts, in_counts, post_counts)):
        total = p + inn + po
        if p > 0:
            ax.text(p / 2, i, str(p), ha="center", va="center", color="white", fontsize=11, fontweight="bold")
        if inn > 0:
            ax.text(p + inn / 2, i, str(inn), ha="center", va="center", color="white", fontsize=11, fontweight="bold")
        if po > 0:
            ax.text(p + inn + po / 2, i, str(po), ha="center", va="center", color="white", fontsize=11, fontweight="bold")
        ax.text(total + 1, i, f"計 {total}件", va="center", fontsize=11)

    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=13)
    ax.set_xlabel("予定入院件数", fontsize=13)
    ax.set_title("連休前後の予定入院分布（前週 / 連休中 / 明け週）", fontsize=16, fontweight="bold", pad=15)
    ax.legend(loc="lower right", fontsize=12)
    ax.grid(axis="x", alpha=0.3)
    ax.invert_yaxis()

    total_in = sum(in_counts)
    ax.text(0.98, 0.05,
            f"連休期間内の予定入院合計 {total_in}件 → ほぼゼロ\n"
            "連休明け週に予定入院を寄せる運用が\nすでに一部実施されている",
            transform=ax.transAxes, fontsize=12, color=COLOR_OK, fontweight="bold",
            verticalalignment="bottom", horizontalalignment="right",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#E8F5E9", edgecolor=COLOR_OK))

    plt.tight_layout()
    plt.savefig(OUT_DIR / "13_holiday_lead_window.png", dpi=DPI, bbox_inches="tight")
    plt.close()
    return names, pre_counts, in_counts, post_counts


# ------------------------------------------------------------
# main
# ------------------------------------------------------------
def main() -> None:
    df = load_data()
    print(f"loaded: {len(df)} rows, {df['admission_datetime'].min()} 〜 {df['admission_datetime'].max()}")
    print(f"  予定: {(df['type_short']=='予定').sum()}  緊急: {(df['type_short']=='緊急').sum()}")

    plan_avg, emerg_avg = chart_01_dow(df)
    print("[01] dow ok")
    chart_02_boxplot(df)
    print("[02] boxplot ok")
    monthly = chart_03_monthly(df)
    print(f"[03] monthly ok ({len(monthly)} months)")
    holiday_res = chart_04_holiday_drop(df)
    print("[04] holiday drop ok")
    for r in holiday_res:
        print(f"    {r[0]}: {r[1]}d, inside={r[2]:.2f}, prior={r[3]:.2f}, drop={r[4]:.1f}%")
    em_total, em_peak, em_ratio = chart_05_emergency_hour(df)
    print(f"[05] emerg hour ok (peak {em_peak}/{em_total} = {em_ratio:.1f}%)")
    cat_avg, cat_n = chart_06_category(df)
    print("[06] category ok")
    for k, v in cat_avg.items():
        print(f"    {k}: {v:.2f}/day ({cat_n[k]}日)")
    post_gw = chart_07_gw(df)
    print(f"[07] GW ok (5/7 = {post_gw}件)")
    post_ne = chart_08_nenmatsu(df)
    print(f"[08] 年末年始 ok (1/5 = {post_ne}件)")
    chart_09_impact(cat_avg)
    print("[09] impact sim ok")
    print("[10] (retained, no regen)")
    lt_med, lt_mean, lt_p25, lt_p75, lt_p90, over8 = chart_11_lead_time(df)
    print(f"[11] lead time ok (median={lt_med:.1f}, mean={lt_mean:.1f}, P25={lt_p25:.1f}, P75={lt_p75:.1f}, 8日+比率={over8:.1f}%)")
    chart_12_reg_admit_heatmap(df)
    print("[12] heatmap ok")
    names, pre, inside, post = chart_13_holiday_lead(df)
    print("[13] holiday lead ok")
    for n, p, i, po in zip(names, pre, inside, post):
        print(f"    {n}: pre={p}, in={i}, post={po}")


if __name__ == "__main__":
    main()
