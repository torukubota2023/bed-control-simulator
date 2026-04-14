"""メインタブ: 5つの指標を1画面で表示する。

ベテランの主任・師長が毎朝見る画面。
数字と基準値の差だけを見せる。判定ラベルや推奨アクションは出さない。
"""

import streamlit as st
import pandas as pd
from datetime import date


# ---------------------------------------------------------------------------
# 計算ヘルパー
# ---------------------------------------------------------------------------

def _current_month_df(df: pd.DataFrame) -> pd.DataFrame:
    """データの最終月のみ抽出する。"""
    if df is None or len(df) == 0:
        return df
    dates = pd.to_datetime(df["date"])
    last = dates.max()
    mask = (dates.dt.year == last.year) & (dates.dt.month == last.month)
    return df[mask].copy()


def _calc_occupancy(monthly_df: pd.DataFrame, beds: int) -> dict:
    """当月の平均稼働率(%)を返す。"""
    if monthly_df is None or len(monthly_df) == 0 or beds <= 0:
        return {"value": None, "delta": None}
    occ = (monthly_df["total_patients"] / beds * 100).mean()
    return {"value": round(occ, 1)}


def _calc_rolling_los(daily_df_full: pd.DataFrame, ward: str | None) -> dict:
    """rolling 90日の平均在院日数を返す。"""
    try:
        from bed_data_manager import calculate_rolling_los
        result = calculate_rolling_los(daily_df_full, ward=ward)
        if result and result.get("rolling_los") is not None:
            return {"value": round(result["rolling_los"], 1)}
    except Exception:
        pass
    return {"value": None}


def _calc_emergency_ratio(detail_df: pd.DataFrame, ward: str | None) -> dict:
    """当月の救急搬送後患者割合(%)を返す。"""
    try:
        from emergency_ratio import calculate_emergency_ratio
        if detail_df is None or len(detail_df) == 0:
            return {"value": None}
        dates = pd.to_datetime(detail_df["日付"])
        last = dates.max()
        ym = last.strftime("%Y-%m")
        w = ward if ward else "5F"  # 全体の場合は各病棟で計算
        if ward:
            result = calculate_emergency_ratio(detail_df, ward, ym)
            return {"value": round(result["ratio_pct"], 1)} if result else {"value": None}
        else:
            # 全体 = 両病棟の加重平均
            r5 = calculate_emergency_ratio(detail_df, "5F", ym)
            r6 = calculate_emergency_ratio(detail_df, "6F", ym)
            if r5 and r6:
                total_adm = r5.get("total_admissions", 0) + r6.get("total_admissions", 0)
                total_er = r5.get("emergency_count", 0) + r6.get("emergency_count", 0)
                ratio = total_er / total_adm * 100 if total_adm > 0 else 0
                return {"value": round(ratio, 1)}
    except Exception:
        pass
    return {"value": None}


def _calc_c_group(daily_df: pd.DataFrame, detail_df: pd.DataFrame, ward: str | None) -> dict:
    """C群の人数と30日超の人数を返す。"""
    result = {"count": 0, "over30": 0}
    try:
        from c_group_control import get_c_group_summary
        summary = get_c_group_summary(daily_df, ward=ward)
        result["count"] = summary.get("c_count", 0)
    except Exception:
        pass
    try:
        from c_group_candidates import generate_c_group_candidate_list
        if detail_df is not None and len(detail_df) > 0:
            candidates = generate_c_group_candidate_list(
                detail_df=detail_df, ward=ward, los_threshold=15,
            )
            result["over30"] = sum(
                1 for c in candidates.get("candidates", [])
                if c.get("estimated_los", 0) >= 30
            )
    except Exception:
        pass
    return result


def _calc_weekend(monthly_df: pd.DataFrame, beds: int) -> dict:
    """週末と平日の稼働率差、金曜退院集中率を返す。"""
    if monthly_df is None or len(monthly_df) == 0 or beds <= 0:
        return {"drop": None, "fri_pct": None}
    df = monthly_df.copy()
    df["_dow"] = pd.to_datetime(df["date"]).dt.dayofweek
    weekday = df[df["_dow"] < 5]
    weekend = df[df["_dow"] >= 5]
    if len(weekday) == 0 or len(weekend) == 0:
        return {"drop": None, "fri_pct": None}
    wd_occ = (weekday["total_patients"] / beds * 100).mean()
    we_occ = (weekend["total_patients"] / beds * 100).mean()
    drop = round(we_occ - wd_occ, 1)
    # 金曜退院集中率
    friday = df[df["_dow"] == 4]
    fri_dis = friday["discharges"].sum()
    total_dis = df["discharges"].sum()
    fri_pct = round(fri_dis / total_dis * 100, 1) if total_dis > 0 else 0
    return {"drop": drop, "fri_pct": fri_pct}


# ---------------------------------------------------------------------------
# 描画
# ---------------------------------------------------------------------------

def render(data: dict, ward: str | None, config: dict):
    """メインタブを描画する。

    Args:
        data: {"daily_all": df, "ward_dfs": {"5F": df, "6F": df}, "detail": df}
        ward: "5F", "6F", or None (全体)
        config: {"target_occ": 0.90, "los_limit": 21.0, "ward_beds": int, ...}
    """
    # --- データ選択 ---
    if ward and ward in data.get("ward_dfs", {}):
        daily_full = data["ward_dfs"][ward]
        beds = config["ward_beds"]
    else:
        daily_full = data.get("daily_all")
        beds = config["total_beds"]

    monthly = _current_month_df(daily_full)
    detail = data.get("detail")

    target_occ = config["target_occ"] * 100
    los_limit = config["los_limit"]

    # --- 計算 ---
    occ = _calc_occupancy(monthly, beds)
    los = _calc_rolling_los(daily_full, ward)
    er = _calc_emergency_ratio(detail, ward)
    cg = _calc_c_group(monthly, detail, ward)
    wk = _calc_weekend(monthly, beds)

    # --- 病棟ラベル ---
    ward_label = f"{ward}病棟（{beds}床）" if ward else f"全体（{beds}床）"
    st.caption(ward_label)

    # --- 指標表示: 上段3列（制度指標） ---
    c1, c2, c3 = st.columns(3)

    with c1:
        if occ["value"] is not None:
            delta = round(occ["value"] - target_occ, 1)
            st.metric("稼働率", f"{occ['value']:.1f}%",
                      f"目標{target_occ:.0f}%比 {delta:+.1f}%")
        else:
            st.metric("稼働率", "—")

    with c2:
        if los["value"] is not None:
            headroom = round(los_limit - los["value"], 1)
            st.metric("平均在院日数", f"{los['value']:.1f}日",
                      f"余力 {headroom:+.1f}日",
                      delta_color="normal")
        else:
            st.metric("平均在院日数", "—")

    with c3:
        if er["value"] is not None:
            er_delta = round(er["value"] - 15.0, 1)
            st.metric("救急搬送比率", f"{er['value']:.1f}%",
                      f"基準15%比 {er_delta:+.1f}%")
        else:
            st.metric("救急搬送比率", "—", "データ未入力")

    # --- 指標表示: 下段2列（運用指標） ---
    c4, c5 = st.columns(2)

    with c4:
        label = f"{cg['count']}名"
        if cg["over30"] > 0:
            st.metric("C群滞留", label, f"30日超 {cg['over30']}名",
                      delta_color="inverse")
        else:
            st.metric("C群滞留", label, "30日超 なし", delta_color="off")

    with c5:
        if wk["drop"] is not None:
            st.metric("週末稼働率低下", f"{wk['drop']:+.1f}%",
                      f"金曜退院集中 {wk['fri_pct']:.0f}%",
                      delta_color="inverse")
        else:
            st.metric("週末稼働率低下", "—")

    # --- 稼働率1%の価値 ---
    mv = config.get("marginal_value")
    if mv:
        st.markdown(f"<div style='text-align:center; color:gray; margin-top:1em;'>"
                    f"稼働率1%の価値: 年間 {mv:,}万円</div>",
                    unsafe_allow_html=True)
