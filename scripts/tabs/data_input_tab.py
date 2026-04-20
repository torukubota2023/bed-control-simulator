"""データ入力タブ: 日次データ・入退院詳細の入力・CSV取込・エクスポート。

令和 8 年度診療報酬改定（2026-06-01 本則適用）の地域包括医療病棟入院料
イ/ロ/ハ 区分判定に対応するため、入院時に以下を記録する:
    - 経路（5 区分: 救急 / 下り搬送 / 外来紹介 / 連携室 / ウォークイン）
    - 主傷病に対する手術の有無（医科点数表 第二章第十部第一節の手術）

過去データとの混同を防ぐため、`data_version` カラムで粒度を区別する:
    - "legacy_binary": 2025FY 事務データ由来（予定外/予定 の 2 値分類のみ）
    - "detailed_v1":   2026-04 以降の新規入力（経路 5 区分 + 手術有無あり）
"""

import streamlit as st
import pandas as pd
from datetime import date, timedelta

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

_DAILY_REQUIRED = ["date", "ward", "total_patients", "new_admissions", "discharges"]
_DETAIL_REQUIRED = ["date", "ward", "event_type", "route"]
_WARDS = ["5F", "6F"]
_ROUTES = ["救急", "外来紹介", "連携室", "ウォークイン", "下り搬送"]
_EMERGENCY_ROUTES = {"救急", "下り搬送"}  # 制度上の「救急搬送後」に該当
_EVENT_TYPES = {"入院": "admission", "退院": "discharge"}
_DATA_VERSION_DETAILED = "detailed_v1"  # 2026-04〜 詳細分類
_DATA_VERSION_LEGACY = "legacy_binary"  # 2025FY 事務由来（2 値分類のみ）


def _derive_admission_tier(route: str, has_surgery: bool) -> str:
    """入院経路と手術有無から入院料区分（イ/ロ/ハ）を返す（表示用文字列）。

    2026年度診療報酬改定 地域包括医療病棟入院料 1/2 の判定:
        - イ（入院料1）: 緊急入院 + 手術なし
        - ロ（入院料2）: 緊急入院 + 手術あり / 予定入院 + 手術なし
        - ハ（入院料3）: 予定入院 + 手術あり

    Args:
        route: 入院経路（_ROUTES のいずれか、または空）
        has_surgery: 主傷病に対する手術の有無

    Returns:
        "イ（入院料1）" / "ロ（入院料2）" / "ハ（入院料3）" / "未判定"
    """
    if not route:
        return "未判定"
    is_emergency = route in _EMERGENCY_ROUTES
    if is_emergency and not has_surgery:
        return "イ（入院料1）"
    if not is_emergency and has_surgery:
        return "ハ（入院料3）"
    return "ロ（入院料2）"


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

def _validate_daily_csv(df: pd.DataFrame) -> tuple[bool, str]:
    """日次データCSVのバリデーション。"""
    missing = [c for c in _DAILY_REQUIRED if c not in df.columns]
    if missing:
        return False, f"必須カラムが不足: {', '.join(missing)}"
    if len(df) == 0:
        return False, "データが空です"
    return True, f"{len(df)}行のデータを確認"


def _validate_detail_csv(df: pd.DataFrame) -> tuple[bool, str]:
    """入退院詳細CSVのバリデーション。"""
    missing = [c for c in _DETAIL_REQUIRED if c not in df.columns]
    if missing:
        return False, f"必須カラムが不足: {', '.join(missing)}"
    if len(df) == 0:
        return False, "データが空です"
    return True, f"{len(df)}件のイベントを確認"


def _add_japanese_columns(df: pd.DataFrame) -> pd.DataFrame:
    """英語カラムから日本語カラムを追加（c_group_candidates等が参照）。"""
    df = df.copy()
    if "date" in df.columns and "日付" not in df.columns:
        df["日付"] = df["date"]
    if "ward" in df.columns and "病棟" not in df.columns:
        df["病棟"] = df["ward"]
    if "event_type" in df.columns and "入退院区分" not in df.columns:
        df["入退院区分"] = df["event_type"].map(
            {"admission": "入院", "discharge": "退院"}
        ).fillna(df["event_type"])
    if "route" in df.columns and "経路" not in df.columns:
        df["経路"] = df["route"]
    return df


def _get_daily_data() -> pd.DataFrame | None:
    """session_stateからユーザー入力の日次データを取得。"""
    return st.session_state.get("v4_daily_data")


def _get_detail_data() -> pd.DataFrame | None:
    """session_stateからユーザー入力の詳細データを取得。"""
    return st.session_state.get("v4_detail_data")


# ---------------------------------------------------------------------------
# 描画
# ---------------------------------------------------------------------------

def render():
    """データ入力タブを描画する。"""
    st.subheader("📝 データ入力")

    # --- データソース表示 ---
    has_daily = _get_daily_data() is not None
    has_detail = _get_detail_data() is not None

    if has_daily or has_detail:
        cols = st.columns([3, 1])
        with cols[0]:
            parts = []
            if has_daily:
                n = len(st.session_state["v4_daily_data"])
                parts.append(f"日次データ {n}行")
            if has_detail:
                n = len(st.session_state["v4_detail_data"])
                parts.append(f"入退院詳細 {n}件")
            st.success(f"ユーザーデータ使用中: {' / '.join(parts)}")
        with cols[1]:
            if st.button("デモに戻す", type="secondary"):
                st.session_state.pop("v4_daily_data", None)
                st.session_state.pop("v4_detail_data", None)
                st.rerun()
    else:
        st.info("デモデータを使用中 — CSVアップロードまたは手動入力でデータを切り替えられます")

    st.markdown("---")

    # --- サブタブ ---
    tab1, tab2 = st.tabs(["📊 日次データ", "📋 入退院詳細"])

    with tab1:
        _render_daily_input()

    with tab2:
        _render_detail_input()


def _render_daily_input():
    """日次データの入力UI。"""

    # --- CSVアップロード ---
    st.markdown("##### CSVアップロード")
    st.caption(f"必須カラム: {', '.join(_DAILY_REQUIRED)}")

    uploaded = st.file_uploader("日次データCSV", type="csv", key="daily_csv_upload")
    if uploaded is not None:
        try:
            df = pd.read_csv(uploaded)
            ok, msg = _validate_daily_csv(df)
            if ok:
                st.success(msg)
                st.dataframe(df.head(5), use_container_width=True, hide_index=True)
                if st.button("このデータを使用する", key="use_daily"):
                    st.session_state["v4_daily_data"] = df
                    st.rerun()
            else:
                st.error(msg)
        except Exception as e:
            st.error(f"CSV読み込みエラー: {e}")

    # --- 手動入力 ---
    st.markdown("---")
    st.markdown("##### 手動入力")

    with st.form("daily_entry_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            entry_date = st.date_input("日付", value=date.today())
            entry_ward = st.selectbox("病棟", _WARDS)
            entry_patients = st.number_input("在院患者数", 0, 94, 40)
        with c2:
            entry_adm = st.number_input("新規入院", 0, 30, 3)
            entry_dis = st.number_input("退院", 0, 30, 3)

        if st.form_submit_button("追加"):
            new_row = pd.DataFrame([{
                "date": str(entry_date),
                "ward": entry_ward,
                "total_patients": entry_patients,
                "new_admissions": entry_adm,
                "discharges": entry_dis,
                "data_source": "manual",
            }])
            existing = _get_daily_data()
            if existing is not None:
                updated = pd.concat([existing, new_row], ignore_index=True)
            else:
                updated = new_row
            st.session_state["v4_daily_data"] = updated
            st.rerun()

    # --- 現在のデータプレビュー ---
    current = _get_daily_data()
    if current is not None and len(current) > 0:
        st.markdown("---")
        st.markdown("##### 現在のデータ")
        st.dataframe(current, use_container_width=True, hide_index=True)
        csv = current.to_csv(index=False).encode("utf-8")
        st.download_button("CSVダウンロード", csv, "daily_data.csv", "text/csv")


def _render_detail_input():
    """入退院詳細の入力UI。"""

    # --- CSVアップロード ---
    st.markdown("##### CSVアップロード")
    st.caption(f"必須カラム: {', '.join(_DETAIL_REQUIRED)}")

    uploaded = st.file_uploader("入退院詳細CSV", type="csv", key="detail_csv_upload")
    if uploaded is not None:
        try:
            df = pd.read_csv(uploaded)
            ok, msg = _validate_detail_csv(df)
            if ok:
                st.success(msg)
                st.dataframe(df.head(5), use_container_width=True, hide_index=True)
                if st.button("このデータを使用する", key="use_detail"):
                    df = _add_japanese_columns(df)
                    st.session_state["v4_detail_data"] = df
                    st.rerun()
            else:
                st.error(msg)
        except Exception as e:
            st.error(f"CSV読み込みエラー: {e}")

    # --- 手動入力 ---
    st.markdown("---")
    st.markdown("##### 手動入力")

    with st.form("detail_entry_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            ev_date = st.date_input("日付", value=date.today(), key="detail_date")
            ev_ward = st.selectbox("病棟", _WARDS, key="detail_ward")
            ev_type_ja = st.selectbox("種別", list(_EVENT_TYPES.keys()))
        with c2:
            ev_route = st.selectbox("経路（入院時）", [""] + _ROUTES)
            ev_los = st.number_input("在院日数（退院時）", 0, 365, 0)

        # 2026年度改定 イ/ロ/ハ 判定用: 主傷病に対する手術の有無
        # 医科点数表 第二章第十部第一節に掲げる手術に限る
        ev_has_surgery = st.checkbox(
            "主傷病に対する手術を実施（2026年度改定 イ/ロ/ハ 判定用）",
            value=False,
            help=(
                "医科点数表 第二章第十部第一節の手術に限る。"
                "退院時・または入院時に計画が確定していれば ON。"
                "イ（入院料1）= 緊急×手術なし、ロ = 緊急×手術あり or 予定×手術なし、"
                "ハ（入院料3）= 予定×手術あり。"
            ),
        )

        if st.form_submit_button("追加"):
            ev_type_en = _EVENT_TYPES[ev_type_ja]
            route_value = ev_route if ev_type_en == "admission" else ""
            surgery_value = bool(ev_has_surgery) if ev_type_en == "admission" else False
            tier_label = (
                _derive_admission_tier(route_value, surgery_value)
                if ev_type_en == "admission"
                else ""
            )
            new_row = pd.DataFrame([{
                "date": str(ev_date),
                "ward": ev_ward,
                "event_type": ev_type_en,
                "route": route_value,
                "has_surgery": surgery_value,
                "admission_tier": tier_label,
                "data_version": _DATA_VERSION_DETAILED,
                "los_days": ev_los if ev_type_en == "discharge" else None,
                "日付": str(ev_date),
                "病棟": ev_ward,
                "入退院区分": ev_type_ja,
                "経路": route_value,
                "手術": "あり" if surgery_value else "なし" if ev_type_en == "admission" else "",
                "入院料区分": tier_label,
            }])
            existing = _get_detail_data()
            if existing is not None:
                updated = pd.concat([existing, new_row], ignore_index=True)
            else:
                updated = new_row
            st.session_state["v4_detail_data"] = updated
            st.rerun()

    # --- 現在のデータプレビュー ---
    current = _get_detail_data()
    if current is not None and len(current) > 0:
        st.markdown("---")
        st.markdown("##### 現在のデータ")
        display_cols = [
            c for c in [
                "date", "ward", "event_type", "route",
                "has_surgery", "admission_tier", "data_version", "los_days",
            ]
            if c in current.columns
        ]
        st.dataframe(current[display_cols], use_container_width=True, hide_index=True)
        csv = current[display_cols].to_csv(index=False).encode("utf-8")
        st.download_button("CSVダウンロード", csv, "admission_details.csv", "text/csv")
