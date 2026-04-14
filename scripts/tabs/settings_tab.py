"""設定タブ: HOPE連携・シナリオ保存・CSVエクスポート。"""

import streamlit as st
import pandas as pd


def render():
    """設定タブを描画する。"""
    sub1, sub2, sub3 = st.tabs(["📨 HOPE連携", "💾 シナリオ管理", "📤 エクスポート"])

    with sub1:
        _render_hope()

    with sub2:
        _render_scenarios()

    with sub3:
        _render_export()


# ---------------------------------------------------------------------------
# HOPE連携
# ---------------------------------------------------------------------------

def _render_hope():
    """HOPEメッセージ生成。"""
    try:
        from hope_message_generator import render_hope_tab
        render_hope_tab()
    except ImportError:
        st.info("HOPE連携モジュールが見つかりません。")
    except Exception as e:
        st.warning(f"HOPE連携の初期化エラー: {e}")
        st.info("HOPE連携はベッドコントロールデータが読み込まれた状態で使用できます。")


# ---------------------------------------------------------------------------
# シナリオ管理
# ---------------------------------------------------------------------------

def _render_scenarios():
    """シナリオの保存・比較。"""
    try:
        from scenario_manager import (
            save_scenario, list_scenarios, load_scenario, delete_scenario,
        )
    except ImportError:
        st.info("シナリオ管理モジュールが見つかりません。")
        return

    st.markdown("##### 保存済みシナリオ")
    scenarios = list_scenarios()

    if not scenarios:
        st.caption("保存済みシナリオはありません。")
    else:
        for s in scenarios:
            c1, c2 = st.columns([4, 1])
            with c1:
                st.text(f"{s.get('name', '無名')} — {s.get('created_at', '')}")
            with c2:
                if st.button("読込", key=f"load_{s.get('id', '')}"):
                    loaded = load_scenario(s["id"])
                    if loaded:
                        st.success(f"シナリオ「{s['name']}」を読み込みました。")

    st.markdown("---")
    st.markdown("##### 現在の状態を保存")
    scenario_name = st.text_input("シナリオ名", key="scenario_save_name")
    if st.button("保存", key="save_scenario") and scenario_name:
        try:
            save_scenario(scenario_name, st.session_state)
            st.success(f"シナリオ「{scenario_name}」を保存しました。")
        except Exception as e:
            st.error(f"保存エラー: {e}")


# ---------------------------------------------------------------------------
# エクスポート
# ---------------------------------------------------------------------------

def _render_export():
    """データのCSVエクスポート。"""
    st.markdown("##### 現在のデータをCSVでダウンロード")

    # 日次データ
    daily = st.session_state.get("v4_daily_data")
    if daily is not None and len(daily) > 0:
        csv = daily.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📊 日次データ CSV",
            csv,
            "daily_data.csv",
            "text/csv",
        )
    else:
        st.caption("ユーザー入力の日次データがありません（デモデータ使用中）。")

    # 詳細データ
    detail = st.session_state.get("v4_detail_data")
    if detail is not None and len(detail) > 0:
        export_cols = [c for c in ["date", "ward", "event_type", "route", "los_days"]
                       if c in detail.columns]
        csv = detail[export_cols].to_csv(index=False).encode("utf-8")
        st.download_button(
            "📋 入退院詳細 CSV",
            csv,
            "admission_details.csv",
            "text/csv",
        )
    else:
        st.caption("ユーザー入力の入退院詳細データがありません（デモデータ使用中）。")
