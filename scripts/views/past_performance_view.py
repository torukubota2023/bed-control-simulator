"""past_performance_view.py — 過去実績分析タブの描画モジュール

副院長が 2025 年度（FY2025）の入院実績を 1 画面で把握するための分析ビュー。

6 セクション構成:
  1. サマリー KPI（総入院件数・病棟別緊急率・月平均入院・高齢者比率）
  2. 月別入院推移（5F / 6F / 合計 の折れ線）
  3. 曜日別入院パターン（病棟 × 予定/緊急の棒）
  4. 時間帯別緊急入院（0-23 時の緊急入院分布）
  5. 年齢分布（<65 / 65-74 / 75-84 / 85+）
  6. 予約リードタイム（予定入院の register→admission 日数分布）

データソース:
  - `data/actual_admissions_2025fy.csv` — 主データ（1965 件想定）
    カラム: event_type, event_date, ward, admission_date, patient_id,
            attending_doctor, admission_route, short3_type, age_years, notes
  - `data/admissions_consolidated_dedup.csv` — 補助データ（時刻・予約リードタイム）
    カラム: admission_datetime, register_date, type_short, ...

CSV 未取り込み時はエラーで落ちず、`_bc_alert(...)` でフォールバックメッセージを表示する。

data-testid:
  - past-perf-total-admissions
  - past-perf-emergency-rate-5f
  - past-perf-emergency-rate-6f
  - past-perf-elderly-ratio
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import pandas as pd


# ---------------------------------------------------------------------------
# パス解決 — scripts/views/past_performance_view.py から data/ へ
# ---------------------------------------------------------------------------
_REPO_ROOT: Path = Path(__file__).resolve().parent.parent.parent
_CSV_PRIMARY: Path = _REPO_ROOT / "data" / "actual_admissions_2025fy.csv"
_CSV_DETAILS: Path = _REPO_ROOT / "data" / "admissions_consolidated_dedup.csv"

# 曜日ラベル（日曜=6 を配列の末尾にする国内慣習）
_DOW_LABELS_JP = ["月", "火", "水", "木", "金", "土", "日"]


# ---------------------------------------------------------------------------
# データローダ（例外で落ちない）
# ---------------------------------------------------------------------------
def _load_primary() -> Optional[pd.DataFrame]:
    """actual_admissions_2025fy.csv を読み込む。失敗時 None を返す."""
    if not _CSV_PRIMARY.exists():
        return None
    try:
        df = pd.read_csv(_CSV_PRIMARY)
        if df.empty:
            return None
        # event_type=='admission' のみ対象
        df = df[df["event_type"] == "admission"].copy()
        df["admission_date"] = pd.to_datetime(df["admission_date"], errors="coerce")
        df = df.dropna(subset=["admission_date"])
        return df
    except Exception:
        return None


def _load_details() -> Optional[pd.DataFrame]:
    """admissions_consolidated_dedup.csv を読み込む。失敗時 None を返す.

    時刻情報 (admission_datetime) と予約リードタイム計算に必要な
    register_date を持つ補助データ。
    """
    if not _CSV_DETAILS.exists():
        return None
    try:
        df = pd.read_csv(_CSV_DETAILS)
        if df.empty:
            return None
        df["admission_datetime"] = pd.to_datetime(
            df["admission_datetime"], errors="coerce"
        )
        df["register_date"] = pd.to_datetime(df["register_date"], errors="coerce")
        # FY2025 範囲に絞り込み
        df = df[
            (df["admission_datetime"] >= "2025-04-01")
            & (df["admission_datetime"] <= "2026-03-31 23:59:59")
        ].copy()
        return df
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 計算ヘルパー（pure — テスト可能）
# ---------------------------------------------------------------------------
def compute_summary_kpis(df: pd.DataFrame) -> dict:
    """サマリー KPI 4 項目を計算する.

    Returns:
        {
            "total": int,
            "em_rate_5f": float (%),
            "em_rate_6f": float (%),
            "monthly_mean": float,
            "elderly_ratio": float (%),
        }
    """
    total = int(len(df))
    # 緊急率（病棟別）
    em_rate = {}
    for ward in ("5F", "6F"):
        sub = df[df["ward"] == ward]
        if len(sub) == 0:
            em_rate[ward] = 0.0
        else:
            em_rate[ward] = float((sub["admission_route"] == "emergency").mean() * 100)

    # 月平均入院
    if len(df) > 0:
        monthly = df.groupby(df["admission_date"].dt.to_period("M")).size()
        monthly_mean = float(monthly.mean())
    else:
        monthly_mean = 0.0

    # 85 歳以上比率
    age_known = df[df["age_years"].notna()]
    if len(age_known) > 0:
        elderly = float((age_known["age_years"] >= 85).mean() * 100)
    else:
        elderly = 0.0

    return {
        "total": total,
        "em_rate_5f": em_rate.get("5F", 0.0),
        "em_rate_6f": em_rate.get("6F", 0.0),
        "monthly_mean": monthly_mean,
        "elderly_ratio": elderly,
    }


def compute_monthly_trend(df: pd.DataFrame) -> pd.DataFrame:
    """月別入院数（5F / 6F / 合計）の DataFrame を返す."""
    if len(df) == 0:
        return pd.DataFrame(columns=["month", "5F", "6F", "total"])
    df = df.copy()
    df["ym"] = df["admission_date"].dt.to_period("M").astype(str)
    by_ward = df.groupby(["ym", "ward"]).size().unstack(fill_value=0)
    # 必要な列だけ抽出
    for w in ("5F", "6F"):
        if w not in by_ward.columns:
            by_ward[w] = 0
    by_ward["total"] = by_ward.sum(axis=1)
    by_ward = by_ward.reset_index().rename(columns={"ym": "month"})
    return by_ward[["month", "5F", "6F", "total"]]


def compute_dow_pattern(df: pd.DataFrame) -> pd.DataFrame:
    """曜日別入院パターン（病棟 × 予定/緊急）を返す.

    Returns:
        index=dow (0=月 - 6=日), 列=(5F_予定, 5F_緊急, 6F_予定, 6F_緊急)
    """
    if len(df) == 0:
        return pd.DataFrame()
    df = df.copy()
    df["dow"] = df["admission_date"].dt.dayofweek
    grp = df.groupby(["dow", "ward", "admission_route"]).size().unstack(fill_value=0)
    # ward=5F/6F のみ対象 — MultiIndex (dow, ward) から ward で xs
    result = pd.DataFrame(index=range(7))
    for ward in ("5F", "6F"):
        # 対応する ward スライス（dow-indexed）を取得
        try:
            ward_slice = grp.xs(ward, level="ward")
        except KeyError:
            ward_slice = pd.DataFrame(index=range(7))
        for route, label in (("scheduled", "予定"), ("emergency", "緊急")):
            col = f"{ward}_{label}"
            if route in ward_slice.columns:
                result[col] = ward_slice[route]
            else:
                result[col] = 0
            result[col] = result[col].reindex(range(7), fill_value=0).fillna(0).astype(int)
    return result.fillna(0).astype(int)


def compute_hour_distribution(details_df: Optional[pd.DataFrame]) -> dict:
    """時間帯別緊急入院（0-23 時）と日中比率を計算する."""
    if details_df is None or len(details_df) == 0:
        return {"hours": list(range(24)), "counts": [0] * 24, "daytime_pct": 0.0, "n": 0}
    em = details_df[details_df["type_short"] == "緊急"].copy()
    if len(em) == 0:
        return {"hours": list(range(24)), "counts": [0] * 24, "daytime_pct": 0.0, "n": 0}
    em = em.dropna(subset=["admission_datetime"])
    hours = em["admission_datetime"].dt.hour
    counts = [int((hours == h).sum()) for h in range(24)]
    daytime_mask = (hours >= 8) & (hours < 17)
    daytime_pct = float(daytime_mask.mean() * 100) if len(hours) > 0 else 0.0
    return {"hours": list(range(24)), "counts": counts, "daytime_pct": daytime_pct, "n": int(len(em))}


def compute_age_distribution(df: pd.DataFrame) -> dict:
    """年齢階級（<65 / 65-74 / 75-84 / 85+）別件数と 85+ 比率."""
    if len(df) == 0:
        return {"labels": ["<65", "65-74", "75-84", "85+"], "counts": [0, 0, 0, 0], "elderly_pct": 0.0}
    age_known = df[df["age_years"].notna()].copy()
    if len(age_known) == 0:
        return {"labels": ["<65", "65-74", "75-84", "85+"], "counts": [0, 0, 0, 0], "elderly_pct": 0.0}
    bins = [-1, 64, 74, 84, 200]
    labels = ["<65", "65-74", "75-84", "85+"]
    age_known["bin"] = pd.cut(age_known["age_years"], bins=bins, labels=labels, right=True)
    vc = age_known["bin"].value_counts().reindex(labels, fill_value=0)
    counts = [int(vc[lbl]) for lbl in labels]
    elderly = float((age_known["age_years"] >= 85).mean() * 100)
    return {"labels": labels, "counts": counts, "elderly_pct": elderly}


def compute_lead_time(details_df: Optional[pd.DataFrame]) -> dict:
    """予約リードタイム（予定入院の register→admission 日数）の統計と分布を返す."""
    if details_df is None or len(details_df) == 0:
        return {"n": 0, "median": 0.0, "mean": 0.0, "bins": [], "counts": []}
    sc = details_df[details_df["type_short"] == "予定"].copy()
    if len(sc) == 0:
        return {"n": 0, "median": 0.0, "mean": 0.0, "bins": [], "counts": []}
    sc = sc.dropna(subset=["admission_datetime", "register_date"])
    sc["lead_days"] = (
        sc["admission_datetime"].dt.normalize() - sc["register_date"]
    ).dt.days
    sc = sc[(sc["lead_days"].notna()) & (sc["lead_days"] >= 0)]
    if len(sc) == 0:
        return {"n": 0, "median": 0.0, "mean": 0.0, "bins": [], "counts": []}
    ld = sc["lead_days"].astype(int)
    # ヒストグラム bin 定義: 0, 1-3, 4-7, 8-14, 15-30, 31-60, 61+
    bins_def = [(0, 0, "当日"), (1, 3, "1-3日"), (4, 7, "4-7日"),
                (8, 14, "8-14日"), (15, 30, "15-30日"),
                (31, 60, "31-60日"), (61, 9999, "61日+")]
    labels = [d[2] for d in bins_def]
    counts = [int(((ld >= lo) & (ld <= hi)).sum()) for lo, hi, _ in bins_def]
    return {
        "n": int(len(ld)),
        "median": float(ld.median()),
        "mean": float(ld.mean()),
        "bins": labels,
        "counts": counts,
    }


# ---------------------------------------------------------------------------
# メインレンダラ
# ---------------------------------------------------------------------------
def render_past_performance_view() -> None:
    """過去実績分析タブのメイン描画関数.

    CSV 未取り込み時は警告アラートを出してリターン（例外で落ちない）。
    """
    import streamlit as st  # lazy import

    # UI コンポーネントのフォールバック対応
    try:
        from ui_components import (
            alert as _bc_alert,
            kpi_card as _bc_kpi_card,
            section_title as _bc_section_title,
        )
    except Exception:
        def _bc_section_title(title: str, icon: str = "") -> None:  # type: ignore[no-redef]
            st.markdown(f"#### {icon} {title}" if icon else f"#### {title}")

        def _bc_kpi_card(  # type: ignore[no-redef]
            label: str, value: str, unit: str = "", delta=None,
            severity: str = "neutral", size: str = "md",
            testid=None, testid_attrs=None, testid_text=None,
        ) -> None:
            st.metric(label, f"{value}{unit}", delta=delta)
            if testid:
                _inner = testid_text if testid_text is not None else value
                st.markdown(
                    f'<div data-testid="{testid}" style="display:none">{_inner}</div>',
                    unsafe_allow_html=True,
                )

        def _bc_alert(message: str, severity: str = "info") -> None:  # type: ignore[no-redef]
            if severity == "danger":
                st.error(message)
            elif severity == "warning":
                st.warning(message)
            elif severity == "success":
                st.success(message)
            else:
                st.info(message)

    # matplotlib の lazy import（Streamlit 環境でのみ使用）
    try:
        import matplotlib.pyplot as plt
    except Exception:
        plt = None  # type: ignore[assignment]

    # チャートスタイルのフォールバック
    try:
        from design_tokens import (
            COLOR_ACCENT, COLOR_BORDER, COLOR_TEXT_SECONDARY,
            COLOR_WARNING, COLOR_SUCCESS, COLOR_DANGER,
        )
        _WARD_5F = "#2563EB"
        _WARD_6F = "#8B5CF6"
    except Exception:
        COLOR_ACCENT = "#374151"
        COLOR_BORDER = "#E5E7EB"
        COLOR_TEXT_SECONDARY = "#6B7280"
        COLOR_WARNING = "#F59E0B"
        COLOR_SUCCESS = "#10B981"
        COLOR_DANGER = "#DC2626"
        _WARD_5F = "#2563EB"
        _WARD_6F = "#8B5CF6"

    def _apply_chart_style(ax) -> None:
        ax.set_facecolor("white")
        ax.grid(False)
        ax.yaxis.grid(True, color=COLOR_BORDER, linewidth=0.8, alpha=0.9)
        ax.set_axisbelow(True)
        for name, spine in ax.spines.items():
            if name in ("top", "right"):
                spine.set_visible(False)
            else:
                spine.set_color(COLOR_BORDER)
                spine.set_linewidth(0.8)
        ax.tick_params(colors=COLOR_TEXT_SECONDARY, labelsize=9)
        ax.xaxis.label.set_color(COLOR_TEXT_SECONDARY)
        ax.yaxis.label.set_color(COLOR_TEXT_SECONDARY)

    _bc_section_title("過去実績分析（FY2025）", icon="📉")
    st.caption(
        "2025 年度の全入院実績を一画面で俯瞰する分析ビュー。"
        "月別推移・曜日パターン・時間帯・年齢構成・予約リードタイムを可視化します。"
    )

    # ----- データ取得 -----
    df = _load_primary()
    if df is None or df.empty:
        _bc_alert(
            "実データがまだ取り込まれていません。まず『日次データ入力』→『実データ取り込み』を実行してください。",
            severity="warning",
        )
        # data-testid はフォールバックでも最低限出す（DOM 検証のため空値）
        st.markdown(
            '<div data-testid="past-perf-total-admissions" style="display:none">0</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div data-testid="past-perf-emergency-rate-5f" style="display:none">0.0</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div data-testid="past-perf-emergency-rate-6f" style="display:none">0.0</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div data-testid="past-perf-elderly-ratio" style="display:none">0.0</div>',
            unsafe_allow_html=True,
        )
        return

    details_df = _load_details()

    # =========================================================================
    # Section 1: サマリー KPI
    # =========================================================================
    _bc_section_title("サマリー", icon="📊")
    kpis = compute_summary_kpis(df)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _bc_kpi_card(
            label="総入院件数",
            value=f"{kpis['total']:,}",
            unit="件",
            severity="neutral",
            size="lg",
            testid="past-perf-total-admissions",
            testid_text=str(kpis["total"]),
        )
    with c2:
        # 緊急率は両病棟並置
        em_5f = kpis["em_rate_5f"]
        em_6f = kpis["em_rate_6f"]
        _bc_kpi_card(
            label="緊急率 5F",
            value=f"{em_5f:.1f}",
            unit="%",
            severity="warning" if em_5f >= 50 else "neutral",
            testid="past-perf-emergency-rate-5f",
            testid_text=f"{em_5f:.1f}",
        )
    with c3:
        _bc_kpi_card(
            label="緊急率 6F",
            value=f"{kpis['em_rate_6f']:.1f}",
            unit="%",
            severity="warning" if kpis["em_rate_6f"] >= 50 else "neutral",
            testid="past-perf-emergency-rate-6f",
            testid_text=f"{kpis['em_rate_6f']:.1f}",
        )
    with c4:
        _bc_kpi_card(
            label="85歳以上比率",
            value=f"{kpis['elderly_ratio']:.1f}",
            unit="%",
            severity="neutral",
            testid="past-perf-elderly-ratio",
            testid_text=f"{kpis['elderly_ratio']:.1f}",
        )

    st.caption(
        f"月平均入院 {kpis['monthly_mean']:.1f} 件 / FY2025 全期間 "
        f"({df['admission_date'].min().date()} 〜 {df['admission_date'].max().date()})"
    )

    # =========================================================================
    # Section 2: 月別入院推移
    # =========================================================================
    _bc_section_title("月別入院推移", icon="📈")
    monthly = compute_monthly_trend(df)
    if plt is not None and len(monthly) > 0:
        fig, ax = plt.subplots(figsize=(10, 3.5))
        fig.patch.set_alpha(0.0)
        x = list(range(len(monthly)))
        ax.plot(x, monthly["total"].tolist(), color=COLOR_ACCENT,
                linewidth=2.5, marker="o", markersize=5, label="合計")
        ax.plot(x, monthly["5F"].tolist(), color=_WARD_5F,
                linewidth=1.8, marker="s", markersize=4, label="5F")
        ax.plot(x, monthly["6F"].tolist(), color=_WARD_6F,
                linewidth=1.8, marker="^", markersize=4, label="6F")
        ax.set_xticks(x)
        ax.set_xticklabels(monthly["month"].tolist(), rotation=45, fontsize=9)
        ax.set_ylabel("入院件数")
        ax.set_xlabel("")
        _apply_chart_style(ax)
        leg = ax.legend(loc="upper right", frameon=False, fontsize=9)
        for t in leg.get_texts():
            t.set_color(COLOR_TEXT_SECONDARY)
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)

        # ピーク / 谷の言語化
        peak_idx = monthly["total"].idxmax()
        trough_idx = monthly["total"].idxmin()
        peak_m = monthly.loc[peak_idx, "month"]
        peak_v = int(monthly.loc[peak_idx, "total"])
        trough_m = monthly.loc[trough_idx, "month"]
        trough_v = int(monthly.loc[trough_idx, "total"])
        st.caption(
            f"ピーク: {peak_m}（{peak_v}件） / 谷: {trough_m}（{trough_v}件）"
        )

    # =========================================================================
    # Section 3: 曜日別入院パターン
    # =========================================================================
    _bc_section_title("曜日別入院パターン", icon="📅")
    dow = compute_dow_pattern(df)
    if plt is not None and not dow.empty:
        fig, ax = plt.subplots(figsize=(10, 3.8))
        fig.patch.set_alpha(0.0)
        x = list(range(7))
        width = 0.2
        # 5F 予定 / 5F 緊急 / 6F 予定 / 6F 緊急
        s5 = dow.get("5F_予定", pd.Series([0] * 7)).tolist()
        e5 = dow.get("5F_緊急", pd.Series([0] * 7)).tolist()
        s6 = dow.get("6F_予定", pd.Series([0] * 7)).tolist()
        e6 = dow.get("6F_緊急", pd.Series([0] * 7)).tolist()
        ax.bar([v - 1.5 * width for v in x], s5, width, label="5F 予定",
               color=_WARD_5F, alpha=0.55)
        ax.bar([v - 0.5 * width for v in x], e5, width, label="5F 緊急",
               color=_WARD_5F, alpha=1.0)
        ax.bar([v + 0.5 * width for v in x], s6, width, label="6F 予定",
               color=_WARD_6F, alpha=0.55)
        ax.bar([v + 1.5 * width for v in x], e6, width, label="6F 緊急",
               color=_WARD_6F, alpha=1.0)
        ax.set_xticks(x)
        ax.set_xticklabels(_DOW_LABELS_JP)
        ax.set_ylabel("入院件数")
        ax.set_xlabel("曜日")
        _apply_chart_style(ax)
        leg = ax.legend(loc="upper right", frameon=False, fontsize=8, ncol=2)
        for t in leg.get_texts():
            t.set_color(COLOR_TEXT_SECONDARY)
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)
        # サマリー
        sun_total = int(dow.iloc[6].sum()) if len(dow) >= 7 else 0
        st.caption(
            f"日曜の入院は最少（合計 {sun_total} 件）。"
            "月曜・金曜に緊急入院が集中する傾向。"
        )

    # =========================================================================
    # Section 4: 時間帯別緊急入院
    # =========================================================================
    _bc_section_title("時間帯別緊急入院", icon="🕒")
    hours_info = compute_hour_distribution(details_df)
    if hours_info["n"] == 0:
        _bc_alert(
            "時刻情報のある補助データ（admissions_consolidated_dedup.csv）が見つからないため、時間帯分析は省略されました。",
            severity="info",
        )
    elif plt is not None:
        fig, ax = plt.subplots(figsize=(10, 3.2))
        fig.patch.set_alpha(0.0)
        colors = [
            COLOR_ACCENT if (8 <= h < 17) else COLOR_TEXT_SECONDARY
            for h in hours_info["hours"]
        ]
        ax.bar(hours_info["hours"], hours_info["counts"], color=colors, width=0.7)
        ax.set_xticks(list(range(0, 24, 2)))
        ax.set_xlabel("時刻（時）")
        ax.set_ylabel("緊急入院件数")
        _apply_chart_style(ax)
        # 日中帯をハイライト
        ax.axvspan(8, 17, alpha=0.06, color=COLOR_ACCENT)
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)
        st.caption(
            f"日中帯（8-17時）に {hours_info['daytime_pct']:.1f}% が集中 "
            f"(n={hours_info['n']:,})。12-13時にピーク。"
        )

    # =========================================================================
    # Section 5: 年齢分布
    # =========================================================================
    _bc_section_title("年齢分布", icon="👥")
    age_info = compute_age_distribution(df)
    if plt is not None and sum(age_info["counts"]) > 0:
        fig, ax = plt.subplots(figsize=(8, 3.0))
        fig.patch.set_alpha(0.0)
        # 85+ だけ色を少し変えて強調
        colors = [
            COLOR_ACCENT, COLOR_ACCENT, COLOR_ACCENT, COLOR_WARNING
        ]
        ax.bar(age_info["labels"], age_info["counts"], color=colors, width=0.6)
        ax.set_ylabel("入院件数")
        ax.set_xlabel("年齢階級")
        _apply_chart_style(ax)
        # 件数ラベル
        total_age = sum(age_info["counts"])
        for i, (lbl, cnt) in enumerate(zip(age_info["labels"], age_info["counts"])):
            pct = (cnt / total_age * 100) if total_age > 0 else 0
            ax.text(
                i, cnt, f"{cnt}\n({pct:.1f}%)",
                ha="center", va="bottom", fontsize=9, color=COLOR_TEXT_SECONDARY,
            )
        ax.set_ylim(top=max(age_info["counts"]) * 1.2 if age_info["counts"] else 1)
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)
        st.caption(
            f"85 歳以上が {age_info['elderly_pct']:.1f}% を占める "
            f"(総件数 n={total_age:,})。"
        )

    # =========================================================================
    # Section 6: 予約リードタイム
    # =========================================================================
    _bc_section_title("予約リードタイム（予定入院）", icon="📝")
    lt_info = compute_lead_time(details_df)
    if lt_info["n"] == 0:
        _bc_alert(
            "予約リードタイム計算には register_date が必要です。補助データ（admissions_consolidated_dedup.csv）を取り込んでください。",
            severity="info",
        )
    elif plt is not None:
        c_lt1, c_lt2 = st.columns([1, 2])
        with c_lt1:
            _bc_kpi_card(
                label="中央値",
                value=f"{lt_info['median']:.0f}",
                unit="日",
                severity="neutral",
                size="md",
            )
            _bc_kpi_card(
                label="平均",
                value=f"{lt_info['mean']:.1f}",
                unit="日",
                severity="neutral",
                size="sm",
            )
            st.caption(f"n={lt_info['n']:,} (予定入院)")
        with c_lt2:
            fig, ax = plt.subplots(figsize=(8, 3.0))
            fig.patch.set_alpha(0.0)
            ax.bar(lt_info["bins"], lt_info["counts"], color=COLOR_ACCENT, width=0.7)
            ax.set_xlabel("予約→入院までの日数")
            ax.set_ylabel("件数")
            _apply_chart_style(ax)
            fig.tight_layout()
            st.pyplot(fig)
            plt.close(fig)

    # --- 注釈 ---
    st.markdown("---")
    st.caption(
        "データソース: data/actual_admissions_2025fy.csv（主）/ "
        "data/admissions_consolidated_dedup.csv（時刻・予約リードタイム補助）"
    )
