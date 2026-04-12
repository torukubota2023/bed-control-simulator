"""制度ガードレール・需要波 描画モジュール — 制度余力・需要トレンドの表示ロジック."""

import streamlit as st


def render_guardrail_summary(guardrail_status: dict) -> None:
    """制度余力ダッシュボードの概要を描画する.

    guardrail_status は以下のキーを持つ dict:
    - "results": list[dict] — calculate_guardrail_status() の戻り値
    - "display": dict — format_guardrail_display() の戻り値
    - "los_headroom": dict — calculate_los_headroom() の戻り値

    各 result item:
    - "name", "current_value", "threshold", "operator", "margin",
      "status", "data_source", "description"
    """
    results = guardrail_status.get("results", [])
    display = guardrail_status.get("display", {})
    los_headroom = guardrail_status.get("los_headroom")

    # 全体ステータス
    overall = display.get("overall_status", "unknown")
    status_emoji = {"safe": "\U0001f7e2", "warning": "\U0001f7e1", "danger": "\U0001f534", "incomplete": "\U0001f7e0"}.get(overall, "\u26aa")
    status_ja = {"safe": "\u5b89\u5168", "warning": "\u6ce8\u610f", "danger": "\u5371\u967a", "incomplete": "\u672a\u5b8c\uff08\u30c7\u30fc\u30bf\u4e0d\u8db3\uff09"}.get(overall, "\u4e0d\u660e")
    st.markdown(f"### {status_emoji} \u7dcf\u5408\u5224\u5b9a: **{status_ja}**")

    # 指標カード
    ds_label_map = {"measured": "\u5b9f\u6e2c", "proxy": "\u63a8\u8a08", "manual_input": "\u624b\u52d5\u5165\u529b", "not_available": "\u672a\u53d6\u5f97"}
    status_icon_map = {"safe": "\U0001f7e2", "warning": "\U0001f7e1", "danger": "\U0001f534", "not_available": "\u26aa"}

    for item in results:
        ds_label = ds_label_map.get(item["data_source"], "")
        status_icon = status_icon_map.get(item["status"], "\u26aa")

        if item["current_value"] is not None:
            val_str = f"{item['current_value']}"
            margin_str = f"\u4f59\u529b: {item['margin']:+.1f}" if item["margin"] is not None else ""
            st.markdown(
                f"{status_icon} **{item['name']}**: {val_str} "
                f"\uff08\u57fa\u6e96 {item['operator']} {item['threshold']}\uff09{margin_str} "
                f"<small style='color:gray'>({ds_label})</small>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"{status_icon} **{item['name']}**: \u2014 "
                f"<small style='color:gray'>({ds_label}: {item['description']})</small>",
                unsafe_allow_html=True,
            )

    # LOS余力の詳細
    if los_headroom is not None:
        st.markdown("---")
        st.subheader("\U0001f4cf \u5e73\u5747\u5728\u9662\u65e5\u6570\u306e\u4f59\u529b")
        if los_headroom["current_los"] is not None:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("\u73fe\u5728\u306e\u5e73\u5747\u5728\u9662\u65e5\u6570", f"{los_headroom['current_los']:.1f}\u65e5")
            with col2:
                st.metric("\u5236\u5ea6\u4e0a\u9650", f"{los_headroom['los_limit']:.0f}\u65e5")
            with col3:
                delta = los_headroom['headroom_days']
                can_extend = los_headroom['can_extend_c_group']
                st.metric("\u4f59\u529b", f"{delta:.1f}\u65e5", delta=f"C\u7fa4\u5ef6\u9577{'\u53ef' if can_extend else '\u4e0d\u53ef'}")

            if los_headroom.get("headroom_patient_days") is not None:
                st.info(f"\U0001f4ca \u5ef6\u3079\u5165\u9662\u65e5\u6570\u63db\u7b97\u306e\u4f59\u529b: \u7d04 {los_headroom['headroom_patient_days']:.0f} \u65e5\u5206\uff08\u63a8\u8a08\uff09")
        else:
            st.warning("\u65e5\u6b21\u30c7\u30fc\u30bf\u4e0d\u8db3\u306e\u305f\u3081\u5e73\u5747\u5728\u9662\u65e5\u6570\u306e\u4f59\u529b\u3092\u8a08\u7b97\u3067\u304d\u307e\u305b\u3093")


def render_demand_wave_summary(demand_result: dict) -> None:
    """需要波ダッシュボードのトレンド・分類・スコアを描画する.

    demand_result は以下のキーを持つ dict:
    - "trend": dict — calculate_demand_trend() の戻り値
    - "classification": dict — classify_demand_period() の戻り値
    - "score": dict — calculate_demand_score() の戻り値
    """
    trend = demand_result.get("trend", {})
    classification = demand_result.get("classification", {})
    score = demand_result.get("score", {})

    # トレンド
    trend_emoji = {
        "increasing": "\U0001f4c8",
        "decreasing": "\U0001f4c9",
        "stable": "\u27a1\ufe0f",
    }.get(trend.get("trend_label", "stable"), "\u27a1\ufe0f")
    st.markdown(f"### {trend_emoji} {trend.get('trend_description', '')}")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("\u524d2\u9031\u9593 \u5e73\u5747\u5165\u9662", f"{trend.get('prev_2w_avg_admissions', 0):.1f}\u4ef6/\u65e5")
    with col2:
        st.metric("\u76f4\u8fd11\u9031\u9593 \u5e73\u5747\u5165\u9662", f"{trend.get('last_1w_avg_admissions', 0):.1f}\u4ef6/\u65e5")
    with col3:
        ratio_pct = round(trend.get("trend_ratio", 1.0) * 100)
        st.metric("\u524d2\u9031\u6bd4", f"{ratio_pct}%")

    # 閑散/繁忙判定
    st.markdown("---")
    class_emoji = {"quiet": "\U0001f535", "normal": "\U0001f7e2", "busy": "\U0001f534"}.get(
        classification.get("classification", ""), "\u26aa"
    )
    st.markdown(
        f"**\u9700\u8981\u5206\u985e**: {class_emoji} {classification.get('classification_ja', '')} "
        f"\uff08\u30d1\u30fc\u30bb\u30f3\u30bf\u30a4\u30eb: {classification.get('percentile', 0):.0f}%\u3001"
        f"\u4fe1\u983c\u5ea6: {classification.get('confidence', '')}\uff09"
    )

    # 需要スコア
    if score:
        col1, col2 = st.columns(2)
        with col1:
            st.metric("14\u65e5\u9700\u8981\u30b9\u30b3\u30a2", f"{score.get('score_14d', 0):.0f}/100", delta=score.get("label_14d", ""))
        with col2:
            st.metric("30\u65e5\u9700\u8981\u30b9\u30b3\u30a2", f"{score.get('score_30d', 0):.0f}/100", delta=score.get("label_30d", ""))
