"""
地域包括医療病棟入院料 診療報酬シミュレーター Streamlit アプリ

令和8年度（2026年度）診療報酬改定に基づく収益シミュレーション・施設基準チェック・
感度分析を行うインタラクティブなダッシュボード。
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# --- パス設定 ---
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from reimbursement_config import (
    DEFAULT_FEES,
    HOSPITAL_DEFAULTS,
    POINT_TABLE,
    YEN_PER_POINT,
    AdditionalFee,
    AdmissionTier,
    CaseMixCell,
    ConstraintSeverity,
    Department,
    WardType,
)
from reimbursement_help_content import HELP_TEXTS
from reimbursement_simulator import (
    calc_case_revenue,
    calc_hospital_summary,
    calc_ward_summary,
    check_all_constraints,
    generate_audit_log,
    generate_default_cases,
    get_daily_points,
    marginal_revenue_per_case,
    sensitivity_by_emergency_ratio,
)

# =====================================================================
# アプリ設定
# =====================================================================

APP_VERSION = "1.0.0"

st.set_page_config(
    page_title="診療報酬シミュレーター",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =====================================================================
# ヘルパー関数
# =====================================================================


def _fmt_yen(value: int | float) -> str:
    """円表示フォーマット"""
    return f"¥{int(value):,}"


def _fmt_yen_man(value: int | float) -> str:
    """万円表示フォーマット"""
    return f"{int(value) / 10000:,.0f}万円"


def _tier_label(tier: AdmissionTier) -> str:
    """Tier の日本語ラベル"""
    return tier.value


def _get_enabled_fees() -> list[AdditionalFee]:
    """サイドバーの選択状態に基づき有効な加算リストを返す"""
    enabled: list[AdditionalFee] = []
    for fee in DEFAULT_FEES:
        key = f"fee_{fee.name}"
        if st.session_state.get(key, fee.enabled_default):
            enabled.append(fee)
    return enabled


def _cases_to_dataframe(cases: list[CaseMixCell]) -> pd.DataFrame:
    """CaseMixCell リストを表示用 DataFrame に変換"""
    ward_type = _get_ward_type()
    enabled_fees = _get_enabled_fees()
    rows = []
    for c in cases:
        rev = calc_case_revenue(c, ward_type, enabled_fees)
        rows.append({
            "診療科": c.department.value,
            "入院形態": "救急" if c.is_emergency else "予定",
            "手術": "あり" if c.has_surgery else "なし",
            "月間件数": c.monthly_count,
            "平均在院日数": round(c.avg_los, 1),
            "入院料区分": _tier_label(c.admission_tier),
            "基本点数": rev["base_points_per_day"],
        })
    return pd.DataFrame(rows)


def _dataframe_to_cases(df: pd.DataFrame, ward: str) -> list[CaseMixCell]:
    """編集済み DataFrame を CaseMixCell リストに変換"""
    dept_map = {d.value: d for d in Department}
    cases: list[CaseMixCell] = []
    for _, row in df.iterrows():
        dept = dept_map.get(row["診療科"])
        if dept is None:
            continue
        cases.append(CaseMixCell(
            ward=ward,
            department=dept,
            is_emergency=(row["入院形態"] == "救急"),
            has_surgery=(row["手術"] == "あり"),
            monthly_count=int(row["月間件数"]),
            avg_los=float(row["平均在院日数"]),
        ))
    return cases


def _get_ward_type() -> WardType:
    """サイドバーで選択された WardType を返す"""
    if st.session_state.get("ward_type_radio") == "なし（入院料1）":
        return WardType.TYPE_1
    return WardType.TYPE_2


def _get_all_cases() -> list[CaseMixCell]:
    """全病棟のケースを session_state から取得"""
    all_cases: list[CaseMixCell] = []
    for ward in ["5F", "6F"]:
        key = f"cases_{ward}"
        if key in st.session_state:
            df = st.session_state[key]
            all_cases.extend(_dataframe_to_cases(df, ward))
    return all_cases


def _init_default_cases():
    """デフォルトケースミックスを session_state に初期化"""
    if "cases_initialized" in st.session_state:
        return
    defaults = generate_default_cases()
    for ward in ["5F", "6F"]:
        ward_cases = [c for c in defaults if c.ward == ward]
        st.session_state[f"cases_{ward}"] = _cases_to_dataframe(ward_cases)
    st.session_state["cases_initialized"] = True


def _enforce_mutual_exclusion(fee_name: str, group: str):
    """相互排他: 同グループ内の他の加算をオフにする"""
    if not st.session_state.get(f"fee_{fee_name}", False):
        return
    for other in DEFAULT_FEES:
        if other.mutual_exclusion_group == group and other.name != fee_name:
            st.session_state[f"fee_{other.name}"] = False


def _render_constraint_card(result, col):
    """施設基準チェック結果を1つのカードとして描画"""
    c = result.constraint
    if result.passed:
        icon = "✅"
        color = "green"
    elif c.severity == ConstraintSeverity.MUST:
        icon = "🚫"
        color = "red"
    else:
        icon = "⚠️"
        color = "orange"

    sign = "+" if result.margin >= 0 else ""
    with col:
        st.markdown(
            f"<div style='border-left: 4px solid {color}; padding: 8px 12px; "
            f"margin-bottom: 8px; background: {'#f0fff0' if result.passed else '#fff0f0' if color == 'red' else '#fffbe6'};'>"
            f"<strong>{icon} {c.name}</strong><br>"
            f"実測値: <strong>{result.actual_value:.1f}</strong>{c.unit} "
            f"（基準: {c.operator} {c.threshold:.1f}{c.unit}）<br>"
            f"余裕: {sign}{result.margin:.1f}"
            f"</div>",
            unsafe_allow_html=True,
        )


# =====================================================================
# サイドバー
# =====================================================================


def render_sidebar():
    """サイドバーの全要素を描画"""
    with st.sidebar:
        st.title("診療報酬シミュレーター")
        st.caption(f"v{APP_VERSION}")

        with st.expander("📋 使い方ガイド"):
            st.markdown(HELP_TEXTS["sidebar_about"])

        # --- 届出区分 ---
        st.markdown("---")
        st.markdown("**━━ 届出区分 ━━**")
        ward_choice = st.radio(
            "A100一般病棟の有無",
            ["なし（入院料1）", "あり（入院料2）"],
            index=0,
            key="ward_type_radio",
            help="A100急性期一般入院基本料を算定する病棟の有無",
        )
        with st.expander("届出区分の詳細"):
            st.markdown(HELP_TEXTS["ward_type_help"])

        if ward_choice is None:
            st.warning("届出区分を選択してください。シミュレーションが実行できません。")
            return False

        # --- 年度設定 ---
        st.markdown("---")
        st.markdown("**━━ 年度設定 ━━**")
        fiscal_year = st.radio(
            "年度",
            ["令和8年度（R8）", "令和9年度（R9）"],
            index=0,
            key="fiscal_year_radio",
        )
        # 年度に基づき物価対応料を自動切替
        if fiscal_year == "令和9年度（R9）":
            st.session_state["fee_物価対応料(令和8年度)"] = False
            st.session_state["fee_物価対応料(令和9年度)"] = True
        else:
            st.session_state["fee_物価対応料(令和8年度)"] = True
            st.session_state["fee_物価対応料(令和9年度)"] = False

        # --- 加算設定 ---
        st.markdown("---")
        st.markdown("**━━ 加算設定 ━━**")

        # カテゴリごとにグループ化
        categories: dict[str, list[AdditionalFee]] = {}
        for fee in DEFAULT_FEES:
            categories.setdefault(fee.category, []).append(fee)

        for cat_name, fees in categories.items():
            # 物価対応は年度設定で自動制御するので手動チェックボックスを出さない
            if cat_name == "物価対応":
                continue
            with st.expander(cat_name, expanded=False):
                for fee in fees:
                    key = f"fee_{fee.name}"
                    default_val = st.session_state.get(key, fee.enabled_default)
                    st.checkbox(
                        f"{fee.name}（{fee.points}点/日）",
                        value=default_val,
                        key=key,
                        help=fee.description,
                        on_change=_enforce_mutual_exclusion,
                        args=(fee.name, fee.mutual_exclusion_group)
                        if fee.mutual_exclusion_group
                        else None,
                    )

        with st.expander("加算の詳細"):
            st.markdown(HELP_TEXTS["fee_help"])

        # --- 施設条件 ---
        st.markdown("---")
        st.markdown("**━━ 施設条件 ━━**")

        st.slider(
            "85歳以上割合（%）",
            min_value=0,
            max_value=50,
            value=25,
            step=1,
            key="age_85_ratio",
        )
        st.number_input(
            "ADL低下割合（%）",
            min_value=0.0,
            max_value=20.0,
            value=3.0,
            step=0.1,
            key="adl_decline_ratio",
            format="%.1f",
        )
        st.number_input(
            "在宅復帰率（%）",
            min_value=0.0,
            max_value=100.0,
            value=80.0,
            step=0.5,
            key="home_discharge_ratio",
            format="%.1f",
        )
        st.number_input(
            "看護必要度割合（%）",
            min_value=0.0,
            max_value=100.0,
            value=20.0,
            step=0.5,
            key="nursing_necessity_ratio",
            format="%.1f",
        )
        st.checkbox(
            "データ提出加算（届出済）",
            value=True,
            key="data_submission",
        )
        st.number_input(
            "リハ専門職配置（名）",
            min_value=0,
            max_value=10,
            value=2,
            step=1,
            key="rehab_staff_count",
        )

        # --- 用語集 ---
        st.markdown("---")
        with st.expander("📖 用語集"):
            st.markdown(HELP_TEXTS["glossary"])

    return True


# =====================================================================
# Tab 1: ケースミックス入力
# =====================================================================


def render_tab_case_mix():
    """ケースミックス入力タブ"""
    st.header("ケースミックス入力")
    st.markdown(
        "各病棟の入院患者構成を入力してください。"
        "月間件数と平均在院日数を編集すると、入院料区分と基本点数が自動計算されます。"
    )

    _init_default_cases()

    ward_type = _get_ward_type()
    enabled_fees = _get_enabled_fees()

    for ward in ["5F", "6F"]:
        desc = HOSPITAL_DEFAULTS["ward_descriptions"].get(ward, "")
        st.subheader(f"{ward}（{desc}）")

        key = f"cases_{ward}"
        df = st.session_state[key].copy()

        dept_options = [d.value for d in Department]
        admission_options = ["救急", "予定"]
        surgery_options = ["あり", "なし"]

        edited_df = st.data_editor(
            df,
            column_config={
                "診療科": st.column_config.SelectboxColumn(
                    "診療科", options=dept_options, required=True
                ),
                "入院形態": st.column_config.SelectboxColumn(
                    "入院形態", options=admission_options, required=True
                ),
                "手術": st.column_config.SelectboxColumn(
                    "手術", options=surgery_options, required=True
                ),
                "月間件数": st.column_config.NumberColumn(
                    "月間件数", min_value=0, max_value=200, step=1
                ),
                "平均在院日数": st.column_config.NumberColumn(
                    "平均在院日数", min_value=1.0, max_value=90.0, step=0.5, format="%.1f"
                ),
                "入院料区分": st.column_config.TextColumn(
                    "入院料区分", disabled=True
                ),
                "基本点数": st.column_config.NumberColumn(
                    "基本点数", disabled=True
                ),
            },
            num_rows="dynamic",
            use_container_width=True,
            key=f"editor_{ward}",
        )

        # 編集結果から再計算（入院料区分・基本点数の自動更新）
        cases = _dataframe_to_cases(edited_df, ward)
        updated_df = _cases_to_dataframe(cases)
        st.session_state[key] = updated_df

        # サマリー行
        if not updated_df.empty:
            total_cases = int(updated_df["月間件数"].sum())
            total_weight = (updated_df["月間件数"] * updated_df["平均在院日数"]).sum()
            avg_los = total_weight / total_cases if total_cases > 0 else 0
            cols = st.columns(3)
            cols[0].metric("月間入院件数", f"{total_cases}件")
            cols[1].metric("加重平均在院日数", f"{avg_los:.1f}日")
            emg_count = int(
                updated_df.loc[updated_df["入院形態"] == "救急", "月間件数"].sum()
            )
            emg_ratio = (emg_count / total_cases * 100) if total_cases > 0 else 0
            cols[2].metric("救急割合", f"{emg_ratio:.1f}%")

        st.markdown("---")

    with st.expander("ケースミックス入力の詳細"):
        st.markdown(HELP_TEXTS["case_mix_help"])


# =====================================================================
# Tab 2: 収益シミュレーション
# =====================================================================


def render_tab_revenue():
    """収益シミュレーションタブ"""
    st.header("収益シミュレーション")

    ward_type = _get_ward_type()
    enabled_fees = _get_enabled_fees()
    all_cases = _get_all_cases()

    if not all_cases:
        st.warning("ケースミックスが入力されていません。「ケースミックス入力」タブでデータを入力してください。")
        return

    # --- 病院全体サマリー ---
    hospital = calc_hospital_summary(all_cases, ward_type, enabled_fees)

    st.subheader("病院全体サマリー")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("月間総収益", _fmt_yen_man(hospital["total_monthly_revenue"]))
    m2.metric("年間総収益", _fmt_yen_man(hospital["total_annual_revenue"]))
    m3.metric("加重平均日次点数", f"{hospital['weighted_avg_daily_points']:.0f}点")
    m4.metric("加重平均在院日数", f"{hospital['weighted_avg_los']:.1f}日")

    st.markdown("---")

    # --- 病棟別比較 ---
    st.subheader("病棟別比較")
    col_5f, col_6f = st.columns(2)

    for ward, col in [("5F", col_5f), ("6F", col_6f)]:
        ward_cases = [c for c in all_cases if c.ward == ward]
        if not ward_cases:
            with col:
                st.info(f"{ward}: データなし")
            continue

        summary = calc_ward_summary(ward_cases, ward_type, enabled_fees)
        with col:
            st.markdown(f"#### {ward}")
            st.metric("月間収益", _fmt_yen_man(summary["total_monthly_revenue"]))
            st.metric("月間件数", f"{summary['total_monthly_cases']}件")

            # Tier 分布パイチャート
            tier_data = {
                _tier_label(t): count
                for t, count in summary["tier_distribution"].items()
                if count > 0
            }
            if tier_data:
                fig_pie = px.pie(
                    names=list(tier_data.keys()),
                    values=list(tier_data.values()),
                    title=f"{ward} 入院料区分分布",
                    color_discrete_sequence=px.colors.qualitative.Set2,
                )
                fig_pie.update_layout(margin=dict(t=40, b=20, l=20, r=20), height=300)
                st.plotly_chart(fig_pie, use_container_width=True)

    st.markdown("---")

    # --- 入院料区分×病棟 収益内訳 ---
    st.subheader("入院料区分 × 病棟 収益内訳")
    bar_data = []
    for ward in ["5F", "6F"]:
        ward_cases = [c for c in all_cases if c.ward == ward]
        if not ward_cases:
            continue
        ws = calc_ward_summary(ward_cases, ward_type, enabled_fees)
        for tier in AdmissionTier:
            rev = ws["tier_revenue_breakdown"][tier]
            if rev > 0:
                bar_data.append({
                    "病棟": ward,
                    "入院料区分": _tier_label(tier),
                    "月間収益（万円）": rev / 10000,
                })

    if bar_data:
        fig_bar = px.bar(
            pd.DataFrame(bar_data),
            x="入院料区分",
            y="月間収益（万円）",
            color="病棟",
            barmode="group",
            title="入院料区分 × 病棟別 月間収益",
            color_discrete_map={"5F": "#4C78A8", "6F": "#F58518"},
        )
        fig_bar.update_layout(margin=dict(t=40, b=40))
        st.plotly_chart(fig_bar, use_container_width=True)

    st.markdown("---")

    # --- 日次点数プロファイル ---
    st.subheader("日次点数プロファイル（在院日数別）")
    st.caption("各入院料区分の1日あたり点数が在院日数に応じてどう変化するか。14日目→15日目で加算が消失します。")

    max_days = 30
    profile_data = []
    for tier in AdmissionTier:
        for day in range(1, max_days + 1):
            pts = get_daily_points(ward_type, tier, day, enabled_fees)
            profile_data.append({
                "在院日数（日）": day,
                "入院料区分": _tier_label(tier),
                "日次点数": pts,
            })

    fig_profile = px.line(
        pd.DataFrame(profile_data),
        x="在院日数（日）",
        y="日次点数",
        color="入院料区分",
        title="日次点数プロファイル（1〜30日）",
        markers=True,
    )
    # 14→15日目の境界線
    fig_profile.add_vline(
        x=14.5, line_dash="dash", line_color="red",
        annotation_text="加算消失（15日目〜）",
        annotation_position="top left",
    )
    fig_profile.update_layout(margin=dict(t=40, b=40))
    st.plotly_chart(fig_profile, use_container_width=True)

    with st.expander("入院料の6区分（ティア）について"):
        st.markdown(HELP_TEXTS["tier_explanation"])


# =====================================================================
# Tab 3: 施設基準チェック
# =====================================================================


def render_tab_constraints():
    """施設基準チェックタブ"""
    st.header("施設基準チェック")

    all_cases = _get_all_cases()
    if not all_cases:
        st.warning("ケースミックスが入力されていません。")
        return

    results = check_all_constraints(
        cases=all_cases,
        age_85_ratio=st.session_state.get("age_85_ratio", 25) / 100.0,
        adl_decline_ratio=st.session_state.get("adl_decline_ratio", 3.0),
        home_discharge_ratio=st.session_state.get("home_discharge_ratio", 80.0),
        nursing_necessity_ratio=st.session_state.get("nursing_necessity_ratio", 20.0),
        data_submission=st.session_state.get("data_submission", True),
        rehab_staff_count=st.session_state.get("rehab_staff_count", 2),
    )

    must_results = [r for r in results if r.constraint.severity == ConstraintSeverity.MUST]
    should_results = [r for r in results if r.constraint.severity == ConstraintSeverity.SHOULD]

    all_must_pass = all(r.passed for r in must_results)

    # --- 総合判定バナー ---
    if all_must_pass:
        st.success("✅ 全ての必須基準（MUST）を充足しています")
    else:
        failed = [r.constraint.name for r in must_results if not r.passed]
        st.error(f"🚫 必須基準に未充足項目があります: {', '.join(failed)}")

    # --- MUST 基準 ---
    st.subheader("必須基準（MUST）")
    cols = st.columns(2)
    for i, result in enumerate(must_results):
        _render_constraint_card(result, cols[i % 2])

    # --- SHOULD 基準 ---
    if should_results:
        st.subheader("推奨基準（SHOULD）")
        cols = st.columns(2)
        for i, result in enumerate(should_results):
            _render_constraint_card(result, cols[i % 2])

    with st.expander("施設基準の詳細"):
        st.markdown(HELP_TEXTS["constraint_help"])


# =====================================================================
# Tab 4: 収益最適化
# =====================================================================


def render_tab_optimization():
    """収益最適化タブ"""
    st.header("収益最適化")

    ward_type = _get_ward_type()
    enabled_fees = _get_enabled_fees()
    all_cases = _get_all_cases()

    if not all_cases:
        st.warning("ケースミックスが入力されていません。")
        return

    # --- 感度分析: 救急割合 × 収益 ---
    st.subheader("感度分析: 救急割合と月間収益")
    sensitivity = sensitivity_by_emergency_ratio(
        cases=all_cases,
        ward_type=ward_type,
        enabled_fees=enabled_fees,
        ratio_range=(0.05, 0.60),
        steps=22,
    )

    df_sens = pd.DataFrame(sensitivity)
    df_sens["救急割合（%）"] = df_sens["emergency_ratio"] * 100
    df_sens["月間収益（万円）"] = df_sens["total_monthly_revenue"] / 10000
    df_sens["基準充足"] = df_sens["emergency_constraint_passed"].map(
        {True: "充足", False: "未充足"}
    )

    fig_sens = px.line(
        df_sens,
        x="救急割合（%）",
        y="月間収益（万円）",
        color="基準充足",
        title="救急割合の変動と月間収益の関係",
        color_discrete_map={"充足": "#2CA02C", "未充足": "#D62728"},
        markers=True,
    )
    fig_sens.add_vline(
        x=15.0, line_dash="dash", line_color="red",
        annotation_text="基準: 15%以上",
        annotation_position="top left",
    )
    fig_sens.update_layout(margin=dict(t=40, b=40))
    st.plotly_chart(fig_sens, use_container_width=True)

    st.markdown("---")

    # --- 追加1件あたりの限界収益 ---
    st.subheader("追加1件あたりの限界収益")
    avg_los_input = st.number_input(
        "想定平均在院日数（日）",
        min_value=1.0,
        max_value=90.0,
        value=17.0,
        step=0.5,
        key="marginal_los",
        format="%.1f",
    )
    marginal = marginal_revenue_per_case(ward_type, enabled_fees, avg_los_input)
    marg_df = pd.DataFrame([
        {
            "入院料区分": _tier_label(tier),
            "1件あたり収益（円）": f"{rev:,}",
            "1件あたり収益（万円）": f"{rev / 10000:,.1f}",
        }
        for tier, rev in marginal.items()
    ])
    st.table(marg_df)

    st.markdown("---")

    # --- What-if シミュレーション ---
    st.subheader("What-if シミュレーション")

    current_summary = calc_hospital_summary(all_cases, ward_type, enabled_fees)
    current_revenue = current_summary["total_monthly_revenue"]

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("#### 救急割合を変更した場合")
        emg_delta = st.slider(
            "救急割合の変動幅（ポイント）",
            min_value=-20,
            max_value=20,
            value=0,
            step=1,
            key="whatif_emg_delta",
        )
        if emg_delta != 0:
            # 現在の救急割合を算出
            total = sum(c.monthly_count for c in all_cases)
            emg = sum(c.monthly_count for c in all_cases if c.is_emergency)
            current_emg_ratio = emg / total if total > 0 else 0
            new_ratio = max(0.0, min(1.0, current_emg_ratio + emg_delta / 100.0))

            from reimbursement_simulator import _adjust_emergency_ratio
            adjusted = _adjust_emergency_ratio(all_cases, new_ratio)
            new_summary = calc_hospital_summary(adjusted, ward_type, enabled_fees)
            new_revenue = new_summary["total_monthly_revenue"]
            diff = new_revenue - current_revenue
            st.metric(
                "変更後月間収益",
                _fmt_yen_man(new_revenue),
                delta=f"{diff / 10000:+,.0f}万円",
            )
        else:
            st.info("スライダーを動かすと変更後の収益を表示します")

    with col_b:
        st.markdown("#### 平均在院日数を変更した場合")
        los_delta = st.slider(
            "在院日数の変動幅（日）",
            min_value=-5.0,
            max_value=5.0,
            value=0.0,
            step=0.5,
            key="whatif_los_delta",
        )
        if los_delta != 0:
            adjusted_cases = []
            for c in all_cases:
                new_los = max(1.0, c.avg_los + los_delta)
                adjusted_cases.append(CaseMixCell(
                    ward=c.ward,
                    department=c.department,
                    is_emergency=c.is_emergency,
                    has_surgery=c.has_surgery,
                    monthly_count=c.monthly_count,
                    avg_los=new_los,
                ))
            new_summary = calc_hospital_summary(adjusted_cases, ward_type, enabled_fees)
            new_revenue = new_summary["total_monthly_revenue"]
            diff = new_revenue - current_revenue
            st.metric(
                "変更後月間収益",
                _fmt_yen_man(new_revenue),
                delta=f"{diff / 10000:+,.0f}万円",
            )

            # 施設基準チェック
            los_result = check_all_constraints(
                cases=adjusted_cases,
                age_85_ratio=st.session_state.get("age_85_ratio", 25) / 100.0,
                adl_decline_ratio=st.session_state.get("adl_decline_ratio", 3.0),
                home_discharge_ratio=st.session_state.get("home_discharge_ratio", 80.0),
                nursing_necessity_ratio=st.session_state.get("nursing_necessity_ratio", 20.0),
                data_submission=st.session_state.get("data_submission", True),
                rehab_staff_count=st.session_state.get("rehab_staff_count", 2),
            )
            los_constraint = [r for r in los_result if r.constraint.name == "平均在院日数"]
            if los_constraint:
                r = los_constraint[0]
                if r.passed:
                    st.success(f"✅ 平均在院日数 {r.actual_value:.1f}日 ≤ {r.constraint.threshold:.0f}日")
                else:
                    st.error(f"🚫 平均在院日数 {r.actual_value:.1f}日 > {r.constraint.threshold:.0f}日（基準超過）")
        else:
            st.info("スライダーを動かすと変更後の収益を表示します")

    with st.expander("感度分析の詳細"):
        st.markdown(HELP_TEXTS["optimization_help"])


# =====================================================================
# Tab 5: レポート出力
# =====================================================================


def render_tab_report():
    """レポート出力タブ"""
    st.header("レポート出力")

    ward_type = _get_ward_type()
    enabled_fees = _get_enabled_fees()
    all_cases = _get_all_cases()

    if not all_cases:
        st.warning("ケースミックスが入力されていません。")
        return

    # 施設基準チェック結果
    constraint_results = check_all_constraints(
        cases=all_cases,
        age_85_ratio=st.session_state.get("age_85_ratio", 25) / 100.0,
        adl_decline_ratio=st.session_state.get("adl_decline_ratio", 3.0),
        home_discharge_ratio=st.session_state.get("home_discharge_ratio", 80.0),
        nursing_necessity_ratio=st.session_state.get("nursing_necessity_ratio", 20.0),
        data_submission=st.session_state.get("data_submission", True),
        rehab_staff_count=st.session_state.get("rehab_staff_count", 2),
    )

    # --- 監査ログ ---
    st.subheader("監査ログ")
    audit_log = generate_audit_log(all_cases, ward_type, enabled_fees, constraint_results)
    st.code(audit_log, language="text")

    st.markdown("---")

    # --- サマリーテーブル ---
    st.subheader("収益サマリーテーブル")
    summary_rows = []
    for case in all_cases:
        rev = calc_case_revenue(case, ward_type, enabled_fees)
        summary_rows.append({
            "病棟": case.ward,
            "診療科": case.department.value,
            "入院形態": "救急" if case.is_emergency else "予定",
            "手術": "あり" if case.has_surgery else "なし",
            "月間件数": case.monthly_count,
            "平均在院日数": case.avg_los,
            "入院料区分": _tier_label(case.admission_tier),
            "基本点数/日": rev["base_points_per_day"],
            "平均日次点数": round(rev["avg_daily_points"], 1),
            "1件あたり総点数": rev["total_points_per_stay"],
            "1件あたり収益（円）": rev["total_yen_per_stay"],
            "月間収益（円）": rev["monthly_revenue"],
            "年間収益（円）": rev["annual_revenue"],
        })

    df_summary = pd.DataFrame(summary_rows)
    st.dataframe(df_summary, use_container_width=True)

    # --- CSV ダウンロード ---
    csv_buffer = io.StringIO()
    df_summary.to_csv(csv_buffer, index=False, encoding="utf-8-sig")
    csv_bytes = csv_buffer.getvalue().encode("utf-8-sig")

    st.download_button(
        label="📥 CSVダウンロード",
        data=csv_bytes,
        file_name="reimbursement_simulation_summary.csv",
        mime="text/csv",
    )

    with st.expander("レポート出力の詳細"):
        st.markdown(HELP_TEXTS["report_help"])


# =====================================================================
# メイン
# =====================================================================


def main():
    """アプリのメインエントリーポイント"""
    sidebar_ok = render_sidebar()

    if not sidebar_ok:
        st.info("サイドバーで届出区分を選択してください。")
        return

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📋 ケースミックス入力",
        "💰 収益シミュレーション",
        "🏥 施設基準チェック",
        "📈 収益最適化",
        "📄 レポート出力",
    ])

    with tab1:
        render_tab_case_mix()
    with tab2:
        render_tab_revenue()
    with tab3:
        render_tab_constraints()
    with tab4:
        render_tab_optimization()
    with tab5:
        render_tab_report()


if __name__ == "__main__":
    main()
