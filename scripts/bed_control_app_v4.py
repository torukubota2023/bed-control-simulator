"""ベッドコントロールアプリ v4.0 — シンプル・数字で語る

ベテランの主任・師長が毎朝見る画面。
判断に必要な5つの数字を1画面で。詳細は別タブで。
"""

import streamlit as st
import pandas as pd
import sys
import os

# --- パス設定 ---
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

# --- ページ設定 ---
st.set_page_config(
    page_title="ベッドコントロール",
    page_icon="🏥",
    layout="wide",
)

# --- モジュール読み込み ---
from bed_data_manager import (
    generate_sample_data,
    TOTAL_BEDS,
    get_ward_beds,
)
from tabs import main_tab, detail_tab, regulation_tab, data_input_tab, settings_tab

try:
    from emergency_ratio import (
        TRANSITIONAL_END_DATE,
        days_until_transitional_end,
    )
    _TRANSITIONAL_AVAILABLE = True
except Exception:
    _TRANSITIONAL_AVAILABLE = False


# ============================================================
# データ読み込み
# ============================================================

_DATA_DIR = os.path.join(os.path.dirname(_SCRIPT_DIR), "data")


def _combine_ward_dfs(df_5f: pd.DataFrame, df_6f: pd.DataFrame) -> pd.DataFrame:
    """5Fと6Fの日次データを全体に合算する。"""
    sum_cols = [
        "total_patients", "new_admissions", "new_admissions_short3",
        "discharges", "discharge_a", "discharge_b", "discharge_c",
        "phase_a_count", "phase_b_count", "phase_c_count",
    ]
    dfs = []
    for df in [df_5f, df_6f]:
        cols = ["date"] + [c for c in sum_cols if c in df.columns]
        dfs.append(df[cols].copy())

    combined = pd.concat(dfs).groupby("date", as_index=False).sum()
    combined["ward"] = "all"
    combined["data_source"] = "sample"
    combined["notes"] = ""
    combined["avg_los"] = 0.0
    return combined.sort_values("date").reset_index(drop=True)


@st.cache_data
def _load_demo_data() -> dict:
    """デモCSVからデータを読み込む。"""
    # --- 病棟別日次データ ---
    ward_csv = os.path.join(_DATA_DIR, "sample_actual_data_ward_202603.csv")
    if os.path.exists(ward_csv):
        ward_df = pd.read_csv(ward_csv)
        df_5f = ward_df[ward_df["ward"] == "5F"].copy().reset_index(drop=True)
        df_6f = ward_df[ward_df["ward"] == "6F"].copy().reset_index(drop=True)
    else:
        # CSVがない場合はサンプル生成（稼働率が高めになる）
        df_5f = generate_sample_data(num_days=30, ward="5F", seed=42)
        df_6f = generate_sample_data(num_days=30, ward="6F", seed=43)

    df_all = _combine_ward_dfs(df_5f, df_6f)

    # --- 入退院詳細データ ---
    detail_csv = os.path.join(_DATA_DIR, "admission_details.csv")
    if os.path.exists(detail_csv):
        detail = pd.read_csv(detail_csv)
        # 日本語カラムを追加（c_group_candidates.py が参照）
        if "date" in detail.columns and "日付" not in detail.columns:
            detail["日付"] = detail["date"]
        if "ward" in detail.columns and "病棟" not in detail.columns:
            detail["病棟"] = detail["ward"]
        if "event_type" in detail.columns and "入退院区分" not in detail.columns:
            detail["入退院区分"] = detail["event_type"].map(
                {"admission": "入院", "discharge": "退院"}
            ).fillna(detail["event_type"])
        if "route" in detail.columns and "経路" not in detail.columns:
            detail["経路"] = detail["route"]
    else:
        detail = pd.DataFrame(columns=[
            "date", "ward", "event_type", "route",
            "日付", "病棟", "入退院区分", "経路", "los_days",
        ])

    return {
        "daily_all": df_all,
        "ward_dfs": {"5F": df_5f, "6F": df_6f},
        "detail": detail,
    }


def _get_active_data() -> dict:
    """ユーザーデータがあればそれを、なければデモデータを返す。"""
    demo = _load_demo_data()

    user_daily = st.session_state.get("v4_daily_data")
    user_detail = st.session_state.get("v4_detail_data")

    if user_daily is not None and len(user_daily) > 0:
        # ユーザー日次データを病棟別に分割
        ward_dfs = {}
        for w in ("5F", "6F"):
            wdf = user_daily[user_daily["ward"] == w].copy().reset_index(drop=True)
            if len(wdf) > 0:
                ward_dfs[w] = wdf
        if ward_dfs:
            dfs = list(ward_dfs.values())
            daily_all = _combine_ward_dfs(
                ward_dfs.get("5F", dfs[0]),
                ward_dfs.get("6F", dfs[-1]),
            ) if len(ward_dfs) == 2 else dfs[0].copy()
        else:
            daily_all = user_daily
            ward_dfs = demo["ward_dfs"]
    else:
        daily_all = demo["daily_all"]
        ward_dfs = demo["ward_dfs"]

    detail = user_detail if user_detail is not None and len(user_detail) > 0 else demo["detail"]

    return {
        "daily_all": daily_all,
        "ward_dfs": ward_dfs,
        "detail": detail,
    }


# ============================================================
# サイドバー
# ============================================================

def _render_sidebar() -> dict:
    """サイドバーを描画し設定を返す。"""
    with st.sidebar:
        st.title("🏥 ベッドコントロール")
        st.caption("v4.0")

        st.markdown("---")

        # 経過措置終了カウントダウン（地域包括医療病棟・救急搬送15%）
        # 令和6改定の経過措置は 2026-05-31 まで。6/1 以降は本則完全適用。
        if _TRANSITIONAL_AVAILABLE:
            _trans_remaining = days_until_transitional_end()
            _trans_label = TRANSITIONAL_END_DATE.strftime("%Y-%m-%d")
            if _trans_remaining > 30:
                st.info(
                    f"🗓️ 経過措置終了まで **あと {_trans_remaining} 日**\n\n"
                    f"救急搬送15%等の本則完全適用は {_trans_label} 翌日から。"
                )
            elif _trans_remaining > 7:
                st.warning(
                    f"⚠️ 経過措置終了まで **あと {_trans_remaining} 日**（{_trans_label}）\n\n"
                    f"6/1 以降は本則が完全適用されます。"
                )
            elif _trans_remaining >= 0:
                st.error(
                    f"🚨 経過措置終了まで **あと {_trans_remaining} 日**（{_trans_label}）\n\n"
                    f"明日以降の運用判断は本則ベースで。"
                )
            else:
                st.error(
                    f"🚨 経過措置は終了しました（{_trans_label}）\n\n"
                    f"地域包括医療病棟の本則が完全適用中。"
                )
            st.markdown("---")

        # 病棟選択
        ward_sel = st.radio("表示病棟", ["全体", "5F", "6F"], horizontal=True)
        ward = ward_sel if ward_sel in ("5F", "6F") else None

        st.markdown("---")

        # 目標設定（折りたたみ）
        with st.expander("⚙ 目標設定", expanded=False):
            target_occ = st.slider("目標稼働率 (%)", 80, 100, 90) / 100
            los_limit = st.number_input("在院日数上限 (日)", 14, 30, 21, step=1)

        # 病床数と1%の価値
        ward_beds = get_ward_beds(ward) if ward else TOTAL_BEDS
        marginal_yearly = int(ward_beds * 0.01 * 36000 * 365 / 10000)  # 万円

    return {
        "ward": ward,
        "target_occ": target_occ,
        "los_limit": float(los_limit),
        "total_beds": TOTAL_BEDS,
        "ward_beds": ward_beds,
        "marginal_value": marginal_yearly,
    }


# ============================================================
# メイン
# ============================================================

def main():
    config = _render_sidebar()
    data = _get_active_data()

    # --- タブ ---
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 メイン",
        "🔍 詳細分析",
        "📋 制度確認",
        "📝 データ入力",
        "⚙ 設定",
    ])

    with tab1:
        main_tab.render(data, config["ward"], config)

    with tab2:
        detail_tab.render(data, config["ward"], config)

    with tab3:
        regulation_tab.render(data, config)

    with tab4:
        data_input_tab.render()

    with tab5:
        settings_tab.render()


if __name__ == "__main__":
    main()
