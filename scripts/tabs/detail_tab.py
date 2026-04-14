"""詳細分析タブ: C群候補・What-If・医師別・週末分析。"""

import streamlit as st
import pandas as pd


def render(data: dict, ward: str | None, config: dict):
    """詳細分析タブを描画する。"""
    sub1, sub2, sub3, sub4 = st.tabs([
        "C群候補一覧", "What-If", "医師別分析", "週末分析",
    ])

    with sub1:
        _render_c_group_list(data, ward)

    with sub2:
        _render_whatif(data, ward, config)

    with sub3:
        _render_doctor_analysis(data)

    with sub4:
        _render_weekend_analysis(data, ward, config)


# ---------------------------------------------------------------------------
# C群候補一覧
# ---------------------------------------------------------------------------

def _render_c_group_list(data: dict, ward: str | None):
    """C群候補の一覧表（在院日数順、判定ラベルなし）。"""
    try:
        from c_group_candidates import generate_c_group_candidate_list
    except ImportError:
        st.warning("c_group_candidates モジュールが見つかりません。")
        return

    detail = data.get("detail")
    if detail is None or len(detail) == 0:
        st.info("入退院詳細データを入力するとC群候補が表示されます。")
        return

    result = generate_c_group_candidate_list(
        detail_df=detail, ward=ward, los_threshold=15,
    )
    candidates = result.get("candidates", [])

    if not candidates:
        st.info("C群候補はありません。")
        return

    st.caption(f"{len(candidates)}名（在院15日以上・在院日数順）")
    table = pd.DataFrame([
        {
            "入院日": c["admission_date"],
            "在院日数": c["estimated_los"],
            "病棟": c["ward"],
            "経路": c.get("route", "—") or "—",
        }
        for c in candidates
    ])
    st.dataframe(table, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# What-If シミュレーション
# ---------------------------------------------------------------------------

def _render_whatif(data: dict, ward: str | None, config: dict):
    """退院タイミング変更のWhat-Ifシミュレーション。"""
    try:
        from bed_data_manager import calculate_rolling_los
        from c_group_control import simulate_c_group_scenario
    except ImportError:
        st.warning("必要なモジュールが見つかりません。")
        return

    # 現在のrolling LOS
    ward_dfs = data.get("ward_dfs", {})
    if ward and ward in ward_dfs:
        daily_df = ward_dfs[ward]
    else:
        daily_df = data.get("daily_all")

    if daily_df is None or len(daily_df) == 0:
        st.info("日次データが必要です。")
        return

    rolling = calculate_rolling_los(daily_df, ward=ward)
    if rolling is None or rolling.get("rolling_los") is None:
        st.info("在院日数データが不足しています。")
        return

    los_limit = config["los_limit"]
    current_los = rolling["rolling_los"]

    st.caption(f"現在の平均在院日数: {current_los:.1f}日（上限 {los_limit:.0f}日）")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**退院後ろ倒し**")
        n_delay = st.slider("後ろ倒し人数", 0, 10, 0, key="wi_delay_n")
        delay_days = st.slider("後ろ倒し日数", 0, 7, 2, key="wi_delay_d")
    with c2:
        st.markdown("**退院前倒し**")
        n_accel = st.slider("前倒し人数", 0, 10, 0, key="wi_accel_n")
        accel_days = st.slider("前倒し日数", 0, 7, 1, key="wi_accel_d")

    if n_delay > 0 or n_accel > 0:
        result = simulate_c_group_scenario(
            rolling, los_limit,
            n_delay=n_delay, delay_days=delay_days,
            n_accelerate=n_accel, accelerate_days=accel_days,
        )
        if result.get("simulated_los") is not None:
            sim_los = result["simulated_los"]
            delta = result["los_delta"]
            within = result["within_guardrail"]
            icon = "✅" if within else "❌"

            mc1, mc2, mc3 = st.columns(3)
            with mc1:
                st.metric("シミュレーション後LOS", f"{sim_los:.1f}日",
                          f"{delta:+.1f}日", delta_color="inverse")
            with mc2:
                st.metric("上限内", icon)
            with mc3:
                rev = result.get("revenue_impact_monthly", 0)
                st.metric("月間収益影響", f"¥{rev:,.0f}")
    else:
        st.caption("スライダーを動かすとシミュレーション結果が表示されます。")


# ---------------------------------------------------------------------------
# 医師別分析
# ---------------------------------------------------------------------------

def _render_doctor_analysis(data: dict):
    """医師別の入退院パターン。"""
    try:
        from bed_data_manager import get_monthly_summary_by_doctor
    except ImportError:
        st.warning("bed_data_manager モジュールが見つかりません。")
        return

    detail = data.get("detail")
    if detail is None or len(detail) == 0:
        st.info("入退院詳細データを入力すると医師別分析が表示されます。")
        return

    # 最新月を取得
    dates = pd.to_datetime(detail["date"])
    last = dates.max()
    ym = last.strftime("%Y-%m")

    try:
        summary = get_monthly_summary_by_doctor(detail, ym)
    except Exception as e:
        st.warning(f"集計エラー: {e}")
        return

    if not summary:
        st.info(f"{ym} の医師別データがありません。")
        return

    st.caption(f"{ym} の医師別実績")
    rows = []
    for doctor, info in summary.items():
        rows.append({
            "医師名": doctor,
            "入院数": info.get("admissions", 0),
            "退院数": info.get("discharges", 0),
            "平均LOS": f"{info.get('avg_los', 0):.1f}日" if info.get("avg_los") else "—",
        })

    if rows:
        df = pd.DataFrame(rows).sort_values("入院数", ascending=False)
        st.dataframe(df, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# 週末分析
# ---------------------------------------------------------------------------

def _render_weekend_analysis(data: dict, ward: str | None, config: dict):
    """週末の稼働率低下と空床コスト分析。"""
    ward_dfs = data.get("ward_dfs", {})
    if ward and ward in ward_dfs:
        daily_df = ward_dfs[ward].copy()
        beds = config["ward_beds"]
    else:
        daily_df = data.get("daily_all")
        if daily_df is not None:
            daily_df = daily_df.copy()
        beds = config["total_beds"]

    if daily_df is None or len(daily_df) == 0:
        st.info("日次データが必要です。")
        return

    # 曜日計算
    daily_df["_dow"] = pd.to_datetime(daily_df["date"]).dt.dayofweek
    daily_df["_occ"] = daily_df["total_patients"] / beds * 100

    weekday = daily_df[daily_df["_dow"] < 5]
    weekend = daily_df[daily_df["_dow"] >= 5]

    if len(weekday) == 0 or len(weekend) == 0:
        st.info("平日・週末の両方のデータが必要です。")
        return

    wd_occ = weekday["_occ"].mean()
    we_occ = weekend["_occ"].mean()
    drop = we_occ - wd_occ

    # 曜日別の退院数
    fri = daily_df[daily_df["_dow"] == 4]
    total_dis = daily_df["discharges"].sum()
    fri_dis = fri["discharges"].sum()
    fri_pct = fri_dis / total_dis * 100 if total_dis > 0 else 0

    # 週末の平均空床
    we_empty = beds - weekend["total_patients"].mean()

    # 空床コスト推計
    unit_price = 36000  # 1日1床あたり包括単価（円）
    weekly_cost = we_empty * 2 * unit_price  # 土日2日分
    monthly_cost = weekly_cost * 4
    annual_cost = weekly_cost * 52

    # 表示
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("平日稼働率", f"{wd_occ:.1f}%")
    with c2:
        st.metric("週末稼働率", f"{we_occ:.1f}%", f"{drop:+.1f}%")
    with c3:
        st.metric("週末平均空床", f"{we_empty:.1f}床")

    st.markdown("---")

    c4, c5, c6 = st.columns(3)
    with c4:
        st.metric("金曜退院集中率", f"{fri_pct:.0f}%",
                  f"金曜 {fri_dis:.0f} / 全体 {total_dis:.0f}")
    with c5:
        st.metric("月間空床コスト推計", f"¥{monthly_cost:,.0f}")
    with c6:
        st.metric("年間空床コスト推計", f"¥{annual_cost:,.0f}")

    # 曜日別退院数チャート
    st.markdown("---")
    st.caption("曜日別の平均退院数")
    dow_labels = ["月", "火", "水", "木", "金", "土", "日"]
    dow_dis = daily_df.groupby("_dow")["discharges"].mean()
    chart_df = pd.DataFrame({
        "曜日": [dow_labels[i] for i in dow_dis.index],
        "平均退院数": dow_dis.values,
    })
    st.bar_chart(chart_df, x="曜日", y="平均退院数")
