"""制度確認タブ: 月次レビュー用の施設基準指標一覧。"""

import streamlit as st


def render(data: dict, config: dict):
    """制度確認タブを描画する。"""
    st.subheader("📋 施設基準 — 月次確認")
    st.caption("毎月1回程度の確認用。日次のベッドコントロールにはメインタブをお使いください。")

    st.markdown("---")

    try:
        from guardrail_engine import calculate_guardrail_status, format_guardrail_display

        daily_df = data.get("daily_all")
        detail_df = data.get("detail")

        if daily_df is None or len(daily_df) == 0:
            st.info("日次データを入力すると施設基準の充足状況が表示されます。")
            return

        gr_config = {"age_85_ratio": 0.25}
        results = calculate_guardrail_status(daily_df, detail_df, gr_config)
        display = format_guardrail_display(results)

        # 一覧表
        rows = []
        for item in display.get("items", []):
            status_icon = {"safe": "🟢", "warning": "🟡", "danger": "🔴",
                          "incomplete": "⚪"}.get(item.get("status", ""), "⚪")
            rows.append({
                "状態": status_icon,
                "項目": item.get("label", ""),
                "現在値": item.get("value_text", "—"),
                "基準": item.get("threshold_text", "—"),
                "余力": item.get("headroom_text", "—"),
            })

        if rows:
            import pandas as pd
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("施設基準データがありません。")

    except ImportError:
        st.warning("guardrail_engine モジュールが見つかりません。")
    except Exception as e:
        st.error(f"計算エラー: {e}")
