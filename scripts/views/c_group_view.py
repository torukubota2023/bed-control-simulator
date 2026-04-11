"""C群候補一覧（lite版）描画モジュール."""

import streamlit as st
import pandas as pd


def render_c_group_candidates_lite(
    candidates_summary: dict,
    candidates_result: dict,
) -> None:
    """C群候補一覧（lite版）を描画する.

    candidates_summary from summarize_candidates_for_display()
    candidates_result from generate_c_group_candidate_list()
    """
    st.subheader("\U0001f465 C群調整候補一覧（lite版・推計）")
    st.caption(
        "C群（在院15日目以降）は院内運用ラベルです。制度上の正式区分ではありません。"
        "以下は入退院イベントからの推計であり、実際の在院状況と異なる場合があります。"
    )

    # Warning if exists
    warning = candidates_summary.get("warning")
    if warning:
        st.warning(warning)

    # Summary text
    st.info(candidates_summary.get("summary_text", "データなし"))

    # Table
    table_data = candidates_summary.get("table_data", [])
    if table_data:
        df = pd.DataFrame(table_data)
        st.dataframe(df, width="stretch", hide_index=True)
    else:
        st.info("該当する候補はありません。")

    # Tradeoff note
    tradeoff_note = candidates_summary.get("tradeoff_note", "")
    if tradeoff_note:
        st.caption(tradeoff_note)

    # Data quality notice
    st.caption(
        f"\U0001f4ca データ品質: {candidates_summary.get('data_quality', 'proxy')} | "
        "将来のHOPE連携で患者レベルの正確なデータに移行予定"
    )
