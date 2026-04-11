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

    # Show source as caption
    st.caption(f"判定根拠: {card.get('priority_source', '—')}")


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


def render_morning_capacity_card(morning_capacity: dict) -> None:
    """翌営業日朝の受入余力を主要KPIとして描画する.

    morning_capacity from estimate_next_morning_capacity():
    - "estimated_emergency_slots": int
    - "three_day_min_slots": int
    - "current_occupancy_pct": float
    - "planned_discharges_tomorrow": float
    - "is_proxy": bool
    - "next_business_date": str
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

    st.subheader(f"\U0001f305 翌営業日朝の受入余力{proxy_label}")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("翌朝受入余力", f"{slots}床", help="翌営業日朝の救急受入可能床数（推計）")
    with col2:
        st.metric("3営業日最小", f"{three_day_min}床", help="直近3営業日の最小受入余力")
    with col3:
        st.metric("退院予定", f"{planned_dc:.0f}名", help="翌日の退院予定人数（推計）")
    with col4:
        st.metric("判定", status_label)

    st.caption(
        f"対象日: {next_date} | "
        f"推計方法: 過去7日の曜日別パターンに基づく proxy | "
        f"翌朝に昼間の救急搬送を何床受けられるかの目安"
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
