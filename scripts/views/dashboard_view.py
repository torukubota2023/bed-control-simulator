"""ダッシュボード描画モジュール — 結論カード・優先KPI・翌朝受入余力・トレードオフ評価."""

import streamlit as st


def render_action_card(card: dict) -> None:
    """結論カード（今日の一手）をダッシュボード最上段に描画する.

    card is the return value of generate_action_card():
    - "level": "critical" | "warning" | "info" | "success"
    - "color": "red" | "yellow" | "blue" | "green"
    - "emoji": str
    - "title": str
    - "actions": list[str]
    - "priority_source": str
    - "details": dict
    """
    # Build the message
    message_lines = [f"**{card['emoji']} 今日の一手: {card['title']}**"]
    message_lines.append("")  # blank line
    for action in card.get("actions", []):
        message_lines.append(action)

    message = "\n\n".join(message_lines)

    level = card.get("level", "info")
    if level == "critical":
        st.error(message)
    elif level == "warning":
        st.warning(message)
    elif level == "info":
        st.info(message)
    else:
        st.success(message)

    # Show ward scope and source as caption
    _ward_label = card.get("selected_ward")
    _scope = f"対象: {_ward_label}病棟" if _ward_label else "対象: 病院全体"
    st.caption(f"{_scope} | 判定根拠: {card.get('priority_source', '—')}")

    # Cross-ward cooperation alerts
    _cross_alerts = card.get("cross_ward_alerts", [])
    if _cross_alerts:
        with st.expander("🤝 他病棟の状況（協力体制）", expanded=True):
            for _alert in _cross_alerts:
                _alert_level = _alert.get("level", "info")
                _alert_msg = f"**{_alert.get('ward', '')}**: {_alert.get('message', '')}"
                if _alert_level == "critical":
                    st.error(_alert_msg)
                elif _alert_level == "warning":
                    st.warning(_alert_msg)
                else:
                    st.info(_alert_msg)
            st.caption("自病棟の問題でなくても、病院全体の施設基準達成に協力が必要です")


def render_kpi_priority_strip(kpi_list: list[dict]) -> None:
    """KPIを優先順位順に目立つ配置で描画する.

    kpi_list is from generate_kpi_priority_list(), each item has:
    - "name", "value", "status", "rank", "explanation"

    Display the top 3 KPIs prominently (large metrics), remaining 3 in smaller format.
    Status colors: danger=red, warning=yellow, safe=green, unknown=white
    """
    if not kpi_list:
        return

    status_emoji = {"danger": "\U0001f534", "warning": "\U0001f7e1", "safe": "\U0001f7e2", "unknown": "\u26aa"}

    # Top 3: prominent display in columns
    top_kpis = kpi_list[:3]
    cols = st.columns(len(top_kpis))
    for col, kpi in zip(cols, top_kpis):
        with col:
            emoji = status_emoji.get(kpi["status"], "\u26aa")
            st.metric(
                label=f"{emoji} {kpi['name']}",
                value=kpi["value"],
            )
            st.caption(kpi["explanation"])

    # Bottom 3: smaller display
    remaining = kpi_list[3:]
    if remaining:
        cols2 = st.columns(len(remaining))
        for col, kpi in zip(cols2, remaining):
            with col:
                emoji = status_emoji.get(kpi["status"], "\u26aa")
                st.caption(f"{emoji} **{kpi['name']}**: {kpi['value']}")
                st.caption(kpi["explanation"])


def render_morning_capacity_card(morning_capacity: dict, morning_5f: dict = None, morning_6f: dict = None) -> None:
    """翌診療日朝の受入余力を主要KPIとして描画する.

    morning_capacity from estimate_next_morning_capacity():
    - "estimated_emergency_slots": int
    - "three_day_min_slots": int
    - "current_occupancy_pct": float
    - "planned_discharges_tomorrow": float
    - "is_proxy": bool
    - "next_business_date": str

    morning_5f / morning_6f: 病棟別の同構造データ（Optional）
    """
    if not morning_capacity:
        return

    slots = morning_capacity.get("estimated_emergency_slots", 0)
    three_day_min = morning_capacity.get("three_day_min_slots", 0)
    is_proxy = morning_capacity.get("is_proxy", True)
    next_date = morning_capacity.get("next_business_date", "")
    planned_dc = morning_capacity.get("planned_discharges_tomorrow", 0)

    proxy_label = "（推計）" if is_proxy else ""

    # Determine status
    if slots >= 5:
        status_label = "\U0001f7e2 余裕あり"
        box_func = st.success  # noqa: F841
    elif slots >= 3:
        status_label = "\U0001f7e1 要注意"
        box_func = st.warning  # noqa: F841
    else:
        status_label = "\U0001f534 不足"
        box_func = st.error  # noqa: F841

    st.subheader(f"\U0001f305 翌診療日朝の受入余力{proxy_label}")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("翌朝受入余力（全体）", f"{slots}床", help="翌診療日朝の救急受入可能床数（推計）")
    with col2:
        st.metric("3診療日最小", f"{three_day_min}床", help="直近3診療日の最小受入余力")
    with col3:
        st.metric("退院予定", f"{planned_dc:.0f}名", help="翌日の退院予定人数（推計）")
    with col4:
        st.metric("判定", status_label)

    # 病棟別 受入余力
    if morning_5f is not None and morning_6f is not None:
        st.markdown("---")
        st.markdown("##### 病棟別 受入余力")
        w_col1, w_col2 = st.columns(2)
        with w_col1:
            slots_5f = morning_5f.get("estimated_emergency_slots", 0)
            if slots_5f >= 5:
                emoji_5f = "\U0001f7e2"
            elif slots_5f >= 3:
                emoji_5f = "\U0001f7e1"
            else:
                emoji_5f = "\U0001f534"
            st.metric("5F 翌朝受入余力", f"{slots_5f}床")
            planned_5f = morning_5f.get("planned_discharges_tomorrow", 0)
            st.caption(f"判定: {emoji_5f} | 退院予定: {planned_5f:.0f}名")
        with w_col2:
            slots_6f = morning_6f.get("estimated_emergency_slots", 0)
            if slots_6f >= 5:
                emoji_6f = "\U0001f7e2"
            elif slots_6f >= 3:
                emoji_6f = "\U0001f7e1"
            else:
                emoji_6f = "\U0001f534"
            st.metric("6F 翌朝受入余力", f"{slots_6f}床")
            planned_6f = morning_6f.get("planned_discharges_tomorrow", 0)
            st.caption(f"判定: {emoji_6f} | 退院予定: {planned_6f:.0f}名")

    # 病棟別 3診療日最小
    if morning_5f is not None and morning_6f is not None:
        three_day_5f = morning_5f.get("three_day_min_slots", 0)
        three_day_6f = morning_6f.get("three_day_min_slots", 0)
        w3_col1, w3_col2 = st.columns(2)
        with w3_col1:
            st.caption(f"3診療日最小: {three_day_5f}床")
        with w3_col2:
            st.caption(f"3診療日最小: {three_day_6f}床")

    st.caption(
        f"対象日: {next_date} | "
        f"推計方法: 過去7日の曜日別パターンに基づく proxy | "
        f"翌朝に昼間の救急搬送を何床受けられるかの目安"
    )

    # 3診療日最小の解説
    with st.expander("💡 「3診療日最小」とは？", expanded=False):
        st.markdown(
            "翌朝の空床数だけでは、**数日後に空床が急減するリスク**を見落とします。\n\n"
            "「3診療日最小」は、**向こう3診療日の中で最も空床が少なくなる日の予測値**です。"
            "過去の同じ曜日の入退院パターンから、日ごとの退院数・入院数を推計し、"
            "累積の空床数を追跡して最小値を取っています。\n\n"
            "**読み方の例:**\n"
            "- 翌朝10床 / 3日最小9床 → 向こう3日間おおむね安定\n"
            "- 翌朝10床 / 3日最小3床 → **明後日以降に急激に詰まる予兆**。今日のうちに退院調整を前倒しすべき\n\n"
            "つまり「翌朝」は今日の判断、「3日最小」は**先手を打つための判断材料**です。"
        )


def render_tradeoff_card(tradeoff: dict) -> None:
    """C群/制度/受入余力のトレードオフ評価を描画する.

    tradeoff from generate_tradeoff_assessment():
    - "recommendation": "keep" | "release" | "neutral"
    - "reasoning": str
    - "impacts": list[dict] with "metric", "effect", "direction"
    - "emergency_priority": bool
    """
    if not tradeoff:
        return

    rec = tradeoff.get("recommendation", "neutral")
    rec_labels = {
        "keep": "\U0001f535 C群キープ推奨（稼働率維持）",
        "release": "\U0001f7e0 C群退院推奨（制度要件優先）",
        "neutral": "\u26aa 個別判断",
    }

    with st.expander(
        f"\u2696\ufe0f C群トレードオフ評価: {rec_labels.get(rec, '—')}",
        expanded=tradeoff.get("emergency_priority", False),
    ):
        st.markdown(f"**総合判断**: {tradeoff.get('reasoning', '')}")
        st.caption(
            "C群（15日目以降）は院内運用ラベルであり、制度上の公式区分ではありません。"
            "推計値はすべて proxy です。"
        )

        if tradeoff.get("emergency_priority"):
            st.warning(
                "\u26a0 救急搬送後患者割合の確保が最優先です。"
                "C群の延長よりも退院→空床確保→救急受入を優先してください。"
            )

        # Impact table
        impacts = tradeoff.get("impacts", [])
        if impacts:
            st.markdown("**各指標への影響:**")
            for imp in impacts:
                direction = imp.get("direction", "")
                if "release" in direction:
                    icon = "\u27a1\ufe0f"
                elif "keep" in direction:
                    icon = "\u2b05\ufe0f"
                else:
                    icon = "\u2796"
                st.markdown(f"- {icon} **{imp.get('metric', '')}**: {imp.get('effect', '')}")
