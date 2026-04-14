"""詳細分析タブ: C群候補・What-If・医師別・週末分析。"""

import streamlit as st


def render(data: dict, ward: str | None, config: dict):
    """詳細分析タブを描画する。"""
    st.subheader("🔍 詳細分析")

    sub1, sub2, sub3, sub4 = st.tabs([
        "C群候補一覧", "What-If", "医師別分析", "週末分析",
    ])

    with sub1:
        _render_c_group_list(data, ward, config)

    with sub2:
        st.info("Phase 2 で実装予定")

    with sub3:
        st.info("Phase 3 で実装予定")

    with sub4:
        st.info("Phase 3 で実装予定")


def _render_c_group_list(data: dict, ward: str | None, config: dict):
    """C群候補の一覧表（数字のみ、判定ラベルなし）。"""
    try:
        from c_group_candidates import generate_c_group_candidate_list

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

        import pandas as pd
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

    except ImportError:
        st.warning("c_group_candidates モジュールが見つかりません。")
