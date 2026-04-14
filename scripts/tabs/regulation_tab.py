"""制度確認タブ: 施設基準の充足状況を月次レビュー用に一覧表示。"""

import streamlit as st
import pandas as pd


_STATUS_ICON = {
    "safe": "🟢",
    "warning": "🟡",
    "danger": "🔴",
    "not_available": "⚪",
    "incomplete": "⚪",
}

_STATUS_LABEL = {
    "safe": "安全",
    "warning": "注意",
    "danger": "危険",
    "not_available": "未取得",
    "incomplete": "未完",
}

_OPERATOR_LABEL = {
    "<=": "以下",
    ">=": "以上",
    "<": "未満",
}


def render(data: dict, config: dict):
    """制度確認タブを描画する。"""
    st.subheader("📋 施設基準 — 月次確認")
    st.caption("毎月1回程度の確認用。日次のベッドコントロールにはメインタブをお使いください。")

    try:
        from guardrail_engine import calculate_guardrail_status, format_guardrail_display
    except ImportError:
        st.warning("guardrail_engine モジュールが見つかりません。")
        return

    daily_df = data.get("daily_all")
    detail_df = data.get("detail")

    if daily_df is None or len(daily_df) == 0:
        st.info("日次データを入力すると施設基準の充足状況が表示されます。")
        return

    # --- 計算 ---
    gr_config = {
        "age_85_ratio": 0.25,
        "ward": None,
    }

    try:
        results = calculate_guardrail_status(daily_df, detail_df, gr_config)
    except Exception as e:
        st.error(f"計算エラー: {e}")
        return

    if not results:
        st.info("施設基準データがありません。")
        return

    display = format_guardrail_display(results)

    # --- 総合判定 ---
    overall = display.get("overall_status", "incomplete")
    icon = _STATUS_ICON.get(overall, "⚪")
    label = _STATUS_LABEL.get(overall, "不明")
    st.markdown(f"### {icon} 総合判定: {label}")

    if display.get("danger_items"):
        st.error(f"基準逸脱: {', '.join(display['danger_items'])}")
    if display.get("warning_items"):
        st.warning(f"注意: {', '.join(display['warning_items'])}")

    # --- 項目一覧 ---
    st.markdown("---")
    rows = []
    for item in results:
        status = item.get("status", "not_available")
        current = item.get("current_value")
        threshold = item.get("threshold")
        margin = item.get("margin")
        op = item.get("operator", "")
        source = item.get("data_source", "")

        rows.append({
            "状態": _STATUS_ICON.get(status, "⚪"),
            "項目": item.get("name", ""),
            "現在値": f"{current:.1f}" if current is not None else "—",
            "基準": f"{threshold}{_OPERATOR_LABEL.get(op, '')}" if threshold is not None else "—",
            "余力": f"{margin:+.1f}" if margin is not None else "—",
            "データ": {"measured": "実測", "proxy": "推計", "not_available": "未入力"}.get(source, source),
        })

    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("表示可能な施設基準項目がありません。")

    # --- 病棟別比較 ---
    st.markdown("---")
    st.markdown("##### 病棟別の主要指標")

    ward_dfs = data.get("ward_dfs", {})
    if not ward_dfs:
        st.info("病棟別データがありません。")
        return

    ward_rows = []
    for ward_name, wdf in ward_dfs.items():
        if wdf is None or len(wdf) == 0:
            continue
        try:
            from bed_data_manager import calculate_rolling_los, get_ward_beds
            beds = get_ward_beds(ward_name)
            occ = (wdf["total_patients"] / beds * 100).mean()

            los_result = calculate_rolling_los(wdf, ward=ward_name)
            los = los_result["rolling_los"] if los_result and los_result.get("rolling_los") else None

            ward_rows.append({
                "病棟": ward_name,
                "稼働率": f"{occ:.1f}%",
                "平均在院日数": f"{los:.1f}日" if los else "—",
                "在院日数余力": f"{21.0 - los:+.1f}日" if los else "—",
            })
        except Exception:
            ward_rows.append({"病棟": ward_name, "稼働率": "—", "平均在院日数": "—", "在院日数余力": "—"})

    if ward_rows:
        st.dataframe(pd.DataFrame(ward_rows), use_container_width=True, hide_index=True)
