# 実行方法: streamlit run scripts/bed_control_simulator_app.py
"""
地域包括医療病棟 ベッドコントロールシミュレーター（Streamlit版）

おもろまちメディカルセンター（94床）向け
CLI版(bed_control_simulator.py)をインポートし、インタラクティブなUI上で
稼働率・在院日数・収益構造をシミュレートする。
"""

import sys
import os
import io

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# 同ディレクトリのモジュールをインポートできるようにパスを追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bed_control_simulator import (
    create_default_params,
    simulate_bed_control,
    summarize_results,
    compare_strategies,
)

# 意思決定支援タブ用の関数（CLI版の実装が遅れている場合に備えtry/except）
_DECISION_SUPPORT_AVAILABLE = False
try:
    from bed_control_simulator import (
        assess_ward_status,
        predict_occupancy,
        suggest_actions,
        simulate_los_impact,
        calculate_optimal_los_range,
        calculate_trends,
        whatif_discharge,
        whatif_admission_surge,
        generate_decision_report,
    )
    _DECISION_SUPPORT_AVAILABLE = True
except ImportError:
    pass

# ヘルプコンテンツモジュール
_HELP_AVAILABLE = False
try:
    from help_content import HELP_TEXTS
    _HELP_AVAILABLE = True
except ImportError:
    HELP_TEXTS = {}

# 日次データ管理モジュール（独立モジュール）
_DATA_MANAGER_AVAILABLE = False
try:
    from bed_data_manager import (
        create_empty_dataframe as dm_create_empty_dataframe,
        validate_record,
        add_record,
        update_record,
        delete_record,
        calculate_daily_metrics,
        predict_occupancy_from_history,
        predict_monthly_kpi,
        generate_weekly_summary,
        export_to_csv as dm_export_to_csv,
        import_from_csv,
        generate_sample_data,
        convert_actual_to_display,
        DEFAULT_REVENUE_PARAMS,
    )
    _DATA_MANAGER_AVAILABLE = True
except ImportError:
    pass

# ---------------------------------------------------------------------------
# 戦略名マッピング（日本語 → CLI英語名）
# ---------------------------------------------------------------------------
STRATEGY_MAP = {
    "バランス戦略": "balanced",
    "回転重視戦略": "rotation",
    "安定維持戦略": "stable",
}
STRATEGY_MAP_REVERSE = {v: k for k, v in STRATEGY_MAP.items()}

# ---------------------------------------------------------------------------
# 日本語フォント設定（利用可能なフォントを試行）
# ---------------------------------------------------------------------------
_JP_FONT_SET = False

def _setup_jp_font():
    """日本語フォントを設定する。失敗時は英語フォールバック。"""
    global _JP_FONT_SET
    if _JP_FONT_SET:
        return

    import matplotlib.font_manager

    # フォントキャッシュをクリアして最新状態を取得
    matplotlib.font_manager._load_fontmanager(try_read_cache=False)

    # 候補フォント一覧（優先順: Streamlit Cloud → macOS → Windows → Linux）
    candidates = [
        "Noto Sans CJK JP",        # Linux / Streamlit Cloud
        "Hiragino Sans",            # macOS
        "Hiragino Kaku Gothic Pro", # macOS
        "Yu Gothic",                # Windows
        "IPAexGothic",              # Linux (IPAフォント)
    ]

    from matplotlib.font_manager import fontManager
    available = {f.name for f in fontManager.ttflist}

    for c in candidates:
        if c in available:
            matplotlib.rcParams["font.family"] = c
            _JP_FONT_SET = True
            matplotlib.rcParams["axes.unicode_minus"] = False
            return
    # フォールバック: sans-serif のまま（日本語は豆腐になる可能性あり）
    _JP_FONT_SET = True
    matplotlib.rcParams["axes.unicode_minus"] = False


_setup_jp_font()

# ---------------------------------------------------------------------------
# カラーパレット
# ---------------------------------------------------------------------------
COLOR_A = "#E74C3C"   # A群: 赤系
COLOR_B = "#27AE60"   # B群: 緑系
COLOR_C = "#2980B9"   # C群: 青系
COLOR_REVENUE = "#2ECC71"
COLOR_COST = "#E67E22"
COLOR_PROFIT = "#3498DB"
COLOR_TARGET = "#F39C1220"  # 目標帯（半透明）

# ---------------------------------------------------------------------------
# ページ設定
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="ベッドコントロールシミュレーター",
    page_icon="🏥",
    layout="wide",
)

st.title("🏥 ベッドコントロールシミュレーター")
st.caption("地域包括医療病棟（おもろまちメディカルセンター）向け日次シミュレーション")


# ---------------------------------------------------------------------------
# ヘルパー: CLI パラメータ辞書を構築する
# ---------------------------------------------------------------------------
def _build_cli_params(ui: dict) -> dict:
    """UIから取得した値をCLI版のパラメータキー名に変換して辞書を返す。"""
    params = create_default_params()
    params["num_beds"] = ui["total_beds"]
    params["target_occupancy_lower"] = ui["target_occupancy_lower"]
    params["target_occupancy_upper"] = ui["target_occupancy_upper"]
    params["days_in_month"] = ui["days_in_month"]
    params["monthly_admissions"] = ui["monthly_admissions"]
    params["avg_length_of_stay"] = ui["avg_length_of_stay"]
    params["discharge_adjustment_days"] = ui["discharge_adjustment_days"]
    params["admission_variation_coeff"] = ui["admission_variability"]
    params["phase_a_revenue"] = ui["phase_a_daily_revenue"]
    params["phase_a_cost"] = ui["phase_a_daily_cost"]
    params["phase_b_revenue"] = ui["phase_b_daily_revenue"]
    params["phase_b_cost"] = ui["phase_b_daily_cost"]
    params["phase_c_revenue"] = ui["phase_c_daily_revenue"]
    params["phase_c_cost"] = ui["phase_c_daily_cost"]
    params["first_day_bonus"] = ui["day1_bonus"]
    params["within_14days_bonus"] = ui["within_14days_bonus"]
    params["rehab_fee"] = ui["rehab_fee"]
    params["opportunity_cost"] = ui["opportunity_cost"]
    params["discharge_promotion_threshold"] = ui["discharge_promotion_threshold"]
    params["admission_suppression_threshold"] = ui["admission_suppression_threshold"]
    params["random_seed"] = ui["random_seed"]
    return params


# ---------------------------------------------------------------------------
# ヘルパー: CLI の DataFrame カラム名を日本語に変換
# ---------------------------------------------------------------------------
_COL_RENAME = {
    "day": "日",
    "date": "日付",
    "total_patients": "在院患者数",
    "occupancy_rate": "稼働率",
    "new_admissions": "新規入院",
    "discharges": "退院",
    "phase_a_count": "A群_患者数",
    "phase_b_count": "B群_患者数",
    "phase_c_count": "C群_患者数",
    "phase_a_ratio": "A群_構成比",
    "phase_b_ratio": "B群_構成比",
    "phase_c_ratio": "C群_構成比",
    "daily_revenue": "日次収益",
    "daily_cost": "日次コスト",
    "daily_profit": "日次粗利",
    "empty_beds": "空床数",
    "excess_demand": "超過需要",
    "opportunity_loss": "機会損失",
    "flag_low_occupancy": "flag_low_occ",
    "flag_high_occupancy": "flag_high_occ",
    "flag_excess_a": "flag_excess_a",
    "flag_shortage_b": "flag_shortage_b",
    "flag_stagnant_c": "flag_stagnant_c",
    "recommended_discharges": "推奨退院数",
    "allowable_holds": "許容保留数",
}


def _rename_df(df: pd.DataFrame) -> pd.DataFrame:
    """CLI版DataFrameのカラム名を日本語に変換し、追加列を生成する。"""
    df = df.rename(columns=_COL_RENAME)
    # 累積粗利を追加
    if "日次粗利" in df.columns:
        df["累積粗利"] = df["日次粗利"].cumsum()
    # 経営判断フラグ列を生成
    flags = []
    for _, row in df.iterrows():
        day_flags = []
        if row.get("flag_low_occ", False):
            day_flags.append("稼働率低下")
        if row.get("flag_high_occ", False):
            day_flags.append("稼働率超過")
        if row.get("flag_excess_a", False):
            day_flags.append("A群過多")
        if row.get("flag_shortage_b", False):
            day_flags.append("B群不足")
        if row.get("flag_stagnant_c", False):
            day_flags.append("C群滞留")
        if "日次粗利" in df.columns and row["日次粗利"] < 0:
            day_flags.append("日次赤字")
        if not day_flags:
            day_flags.append("正常運用")
        flags.append(", ".join(day_flags))
    df["経営判断フラグ"] = flags
    return df


# ---------------------------------------------------------------------------
# ヘルパー: CLI の summary を Streamlit 用日本語キーに変換
# ---------------------------------------------------------------------------
def _convert_summary(cli_summary: dict, params: dict) -> dict:
    """CLI版summarize_resultsの戻り値をStreamlit表示用の日本語キー辞書に変換。"""
    days_in_month = params["days_in_month"]
    days_in_range = cli_summary["days_in_target_range"]
    return {
        "月次収益": cli_summary["total_revenue"],
        "月次コスト": cli_summary["total_cost"],
        "月次粗利": cli_summary["total_profit"],
        "平均稼働率": round(cli_summary["avg_occupancy"] * 100, 1),
        "月間入院数": 0,  # 後で計算
        "月間退院数": 0,  # 後で計算
        "目標レンジ内日数": days_in_range,
        "目標レンジ内率": round(days_in_range / max(days_in_month, 1) * 100, 1),
        "A群平均構成比": round(cli_summary["avg_phase_a_ratio"] * 100, 1),
        "B群平均構成比": round(cli_summary["avg_phase_b_ratio"] * 100, 1),
        "C群平均構成比": round(cli_summary["avg_phase_c_ratio"] * 100, 1),
        "平均在院日数": cli_summary["avg_length_of_stay"],
        "フラグ集計": {},  # 後で計算
    }


def _enrich_summary(summary: dict, df_ja: pd.DataFrame) -> dict:
    """日本語DataFrameから入退院数・フラグ集計を追加する。"""
    summary["月間入院数"] = int(df_ja["新規入院"].sum())
    summary["月間退院数"] = int(df_ja["退院"].sum())
    # フラグ集計
    flag_counts: dict[str, int] = {}
    for flags_str in df_ja["経営判断フラグ"]:
        for f in flags_str.split(", "):
            flag_counts[f] = flag_counts.get(f, 0) + 1
    summary["フラグ集計"] = flag_counts
    return summary


# ---------------------------------------------------------------------------
# キャッシュ付きシミュレーション実行関数
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def run_simulation(_params_hashable: tuple, strategy_en: str, params_dict_orig: dict):
    """シミュレーションを実行し結果をキャッシュする。"""
    params = _build_cli_params(params_dict_orig)
    df = simulate_bed_control(params, strategy_en)
    cli_summary = summarize_results(df)
    return df, cli_summary


@st.cache_data(show_spinner=False)
def run_comparison(_params_hashable: tuple, params_dict_orig: dict):
    """全戦略比較を実行しキャッシュする。"""
    params = _build_cli_params(params_dict_orig)
    strategies = ["rotation", "stable", "balanced"]
    results = {}
    for strat in strategies:
        df = simulate_bed_control(params, strat)
        cli_summary = summarize_results(df)
        ja_name = STRATEGY_MAP_REVERSE.get(strat, strat)
        df_ja = _rename_df(df)
        summary_ja = _convert_summary(cli_summary, params)
        summary_ja = _enrich_summary(summary_ja, df_ja)
        results[ja_name] = summary_ja
    return results


# ---------------------------------------------------------------------------
# サイドバー: データソース選択（グローバルモード切替）
# ---------------------------------------------------------------------------
st.sidebar.header("📊 データソース")
data_source_mode = st.sidebar.radio(
    "分析に使うデータ",
    ["🔬 シミュレーション（予測モデル）", "📋 実績データ（日次入力）"],
    help="シミュレーション：パラメータに基づく予測モデル\n実績データ：日次入力した実際の病棟データ",
    key="data_source_mode",
)
_is_actual_data_mode = data_source_mode == "📋 実績データ（日次入力）"

st.sidebar.markdown("---")

# ---------------------------------------------------------------------------
# サイドバー: パラメータ入力
# ---------------------------------------------------------------------------
st.sidebar.header("パラメータ設定")

# 病床数は両モードで必要
st.sidebar.subheader("病棟基本条件")
total_beds = st.sidebar.number_input("病床数", min_value=10, max_value=200, value=94)
target_lower = st.sidebar.slider("目標稼働率下限", 0.80, 1.00, 0.90, step=0.01, format="%.2f")
target_upper = st.sidebar.slider("目標稼働率上限", 0.80, 1.00, 0.95, step=0.01, format="%.2f")

# 目標上限 < 下限のバリデーション
if target_upper < target_lower:
    st.sidebar.warning("目標稼働率上限が下限より低く設定されています。値を確認してください。")

# シミュレーションモード専用のパラメータ
if not _is_actual_data_mode:
    days_in_month = st.sidebar.number_input("月の日数", min_value=28, max_value=31, value=30)
    monthly_admissions = st.sidebar.number_input("月間新規入院数", min_value=50, max_value=300, value=150)
    avg_los = st.sidebar.slider("平均在院日数", 10, 30, 18)
    discharge_adj = st.sidebar.number_input("退院調整日数", min_value=0, max_value=5, value=2)
    admission_var = st.sidebar.slider("入院流入変動係数", 0.50, 1.50, 1.00, step=0.05, format="%.2f")
else:
    # 実データモード用のデフォルト値（params_dict構築に必要）
    days_in_month = 30
    monthly_admissions = 150
    avg_los = 18
    discharge_adj = 2
    admission_var = 1.0

# --- 患者フェーズ別パラメータ ---
with st.sidebar.expander("患者フェーズ別パラメータ"):
    st.markdown("**A群（急性期: 〜5日目）**")
    phase_a_rev = st.number_input("A群 日次収益（円）", value=30000, step=1000, key="a_rev")
    phase_a_cost = st.number_input("A群 日次コスト（円）", value=28000, step=1000, key="a_cost")
    st.markdown("**B群（回復期: 6〜14日目）**")
    phase_b_rev = st.number_input("B群 日次収益（円）", value=30000, step=1000, key="b_rev")
    phase_b_cost = st.number_input("B群 日次コスト（円）", value=13000, step=1000, key="b_cost")
    st.markdown("**C群（退院準備期: 15日目〜）**")
    phase_c_rev = st.number_input("C群 日次収益（円）", value=30000, step=1000, key="c_rev")
    phase_c_cost = st.number_input("C群 日次コスト（円）", value=11000, step=1000, key="c_cost")

# --- 追加パラメータ ---
with st.sidebar.expander("追加パラメータ"):
    day1_bonus = st.number_input("初日加算（円）", value=0, step=1000)
    within_14_bonus = st.number_input("14日以内加算（円/日）", value=0, step=500)
    rehab_fee = st.number_input("リハビリ出来高（円/日）", value=0, step=500)
    opportunity_cost = st.number_input("機会損失コスト（円/空床/日）", value=10000, step=1000)
    discharge_threshold = st.slider("退院促進閾値", 0.80, 1.00, 0.95, step=0.01, format="%.2f")
    suppression_threshold = st.slider("新規入院抑制閾値", 0.80, 1.00, 0.97, step=0.01, format="%.2f")
    random_seed = st.number_input("乱数シード", value=42, step=1)

# --- 戦略選択・実行ボタン（シミュレーションモードのみ） ---
if not _is_actual_data_mode:
    st.sidebar.subheader("戦略選択")
    strategy = st.sidebar.radio(
        "シミュレーション戦略",
        ["バランス戦略", "回転重視戦略", "安定維持戦略"],
        index=0,
    )
    compare_all = st.sidebar.checkbox("全戦略比較", value=False)

    # --- 実行ボタン ---
    run_button = st.sidebar.button("シミュレーション実行", type="primary", use_container_width=True)
else:
    strategy = "バランス戦略"
    compare_all = False
    run_button = False

# --- サイドバー最下部: 使い方ガイド ---
if _HELP_AVAILABLE and "sidebar_about" in HELP_TEXTS:
    with st.sidebar.expander("📖 使い方ガイド"):
        st.markdown(HELP_TEXTS["sidebar_about"])

# ---------------------------------------------------------------------------
# パラメータ辞書の組み立て（UI値を保持、CLI変換は _build_cli_params で行う）
# ---------------------------------------------------------------------------
params_dict = {
    "total_beds": total_beds,
    "target_occupancy_lower": target_lower,
    "target_occupancy_upper": target_upper,
    "days_in_month": days_in_month,
    "monthly_admissions": monthly_admissions,
    "avg_length_of_stay": avg_los,
    "discharge_adjustment_days": discharge_adj,
    "admission_variability": admission_var,
    "phase_a_daily_revenue": phase_a_rev,
    "phase_a_daily_cost": phase_a_cost,
    "phase_b_daily_revenue": phase_b_rev,
    "phase_b_daily_cost": phase_b_cost,
    "phase_c_daily_revenue": phase_c_rev,
    "phase_c_daily_cost": phase_c_cost,
    "day1_bonus": day1_bonus,
    "within_14days_bonus": within_14_bonus,
    "rehab_fee": rehab_fee,
    "opportunity_cost": opportunity_cost,
    "discharge_promotion_threshold": discharge_threshold,
    "admission_suppression_threshold": suppression_threshold,
    "random_seed": int(random_seed) if random_seed else None,
}

# ---------------------------------------------------------------------------
# セッション状態管理
# ---------------------------------------------------------------------------
if "sim_df" not in st.session_state:
    st.session_state.sim_df = None
    st.session_state.sim_summary = None
    st.session_state.comparison = None
    st.session_state.sim_df_raw = None
    st.session_state.sim_params = None

# 日次データ管理用セッション状態
if "daily_data" not in st.session_state:
    if _DATA_MANAGER_AVAILABLE:
        st.session_state.daily_data = dm_create_empty_dataframe()
    else:
        st.session_state.daily_data = pd.DataFrame()

if "demo_data" not in st.session_state:
    st.session_state.demo_data = pd.DataFrame()

if "data_mode" not in st.session_state:
    st.session_state.data_mode = "📊 実データ入力モード"

# ---------------------------------------------------------------------------
# シミュレーション実行
# ---------------------------------------------------------------------------
if run_button:
    with st.spinner("シミュレーション実行中..."):
        try:
            strategy_en = STRATEGY_MAP[strategy]
            params = _build_cli_params(params_dict)
            df = simulate_bed_control(params, strategy_en)
            cli_summary = summarize_results(df)

            # CLI結果を日本語に変換
            df_ja = _rename_df(df)
            summary_ja = _convert_summary(cli_summary, params)
            summary_ja = _enrich_summary(summary_ja, df_ja)

            st.session_state.sim_df = df_ja
            st.session_state.sim_summary = summary_ja
            st.session_state.sim_df_raw = df          # 意思決定支援タブ用（CLI版DataFrame）
            st.session_state.sim_params = params       # 意思決定支援タブ用（CLI版パラメータ）

            if compare_all:
                # hashable化してキャッシュ用
                params_hashable = tuple(sorted(params_dict.items()))
                comparison = run_comparison(params_hashable, params_dict)
                st.session_state.comparison = comparison
            else:
                st.session_state.comparison = None

        except Exception as e:
            st.error(f"シミュレーションエラー: {e}")
            st.stop()

# ---------------------------------------------------------------------------
# 実データモード: 実績データからシミュレーション互換DataFrameを生成
# ---------------------------------------------------------------------------
_actual_data_available = False
if _is_actual_data_mode and _DATA_MANAGER_AVAILABLE:
    # データモードに応じてデータソースを選択
    _is_demo = st.session_state.get("data_mode") == "🎮 デモモード（サンプルデータ）"
    if _is_demo:
        _source_data = st.session_state.demo_data if isinstance(st.session_state.demo_data, pd.DataFrame) else pd.DataFrame()
    else:
        _source_data = st.session_state.daily_data

    if isinstance(_source_data, pd.DataFrame) and len(_source_data) >= 1:
        # パラメータ辞書を構築（CLI版互換 + 実データ変換用）
        # _build_cli_params を使って完全なパラメータセットを取得
        _actual_params = _build_cli_params(params_dict)
        _actual_raw_df = convert_actual_to_display(_source_data, _actual_params)
        _actual_display_df = _rename_df(_actual_raw_df)

        # サマリー生成（実データ用）
        _actual_summary = {
            "月次収益": int(_actual_raw_df["daily_revenue"].sum()),
            "月次コスト": int(_actual_raw_df["daily_cost"].sum()),
            "月次粗利": int(_actual_raw_df["daily_profit"].sum()),
            "平均稼働率": round(float(_actual_raw_df["occupancy_rate"].mean()) * 100, 1),
            "月間入院数": int(_actual_raw_df["new_admissions"].sum()),
            "月間退院数": int(_actual_raw_df["discharges"].sum()),
            "目標レンジ内日数": int(
                ((_actual_raw_df["occupancy_rate"] >= target_lower)
                 & (_actual_raw_df["occupancy_rate"] <= target_upper)).sum()
            ),
            "目標レンジ内率": round(
                float(
                    ((_actual_raw_df["occupancy_rate"] >= target_lower)
                     & (_actual_raw_df["occupancy_rate"] <= target_upper)).mean()
                ) * 100, 1
            ),
            "A群平均構成比": round(float(_actual_raw_df["phase_a_ratio"].mean()) * 100, 1),
            "B群平均構成比": round(float(_actual_raw_df["phase_b_ratio"].mean()) * 100, 1),
            "C群平均構成比": round(float(_actual_raw_df["phase_c_ratio"].mean()) * 100, 1),
            "平均在院日数": 0,  # 実データから取得
            "フラグ集計": {},
        }
        # 平均在院日数（実データに avg_los がある場合）
        if "avg_los" in _source_data.columns:
            _avg_los_vals = pd.to_numeric(_source_data["avg_los"], errors="coerce").dropna()
            if len(_avg_los_vals) > 0:
                _actual_summary["平均在院日数"] = round(float(_avg_los_vals.mean()), 1)

        # フラグ集計
        _actual_summary = _enrich_summary(_actual_summary, _actual_display_df)

        # セッション状態にも保存（意思決定ダッシュボード等で使用）
        st.session_state.actual_df = _actual_display_df
        st.session_state.actual_summary = _actual_summary
        st.session_state.actual_df_raw = _actual_raw_df
        st.session_state.actual_params = _actual_params
        _actual_data_available = True

# ---------------------------------------------------------------------------
# 結果未実行の場合の案内
# ---------------------------------------------------------------------------
_simulation_available = st.session_state.sim_df is not None

# ---------------------------------------------------------------------------
# ヘルパー: 金額フォーマット
# ---------------------------------------------------------------------------
def fmt_yen(val: int) -> str:
    """円表示フォーマット（万円単位）"""
    if abs(val) >= 10000:
        return f"¥{val/10000:,.1f}万"
    return f"¥{val:,}"


def fmt_yen_full(val: int) -> str:
    """円表示フォーマット（全額）"""
    return f"¥{val:,}"


# ---------------------------------------------------------------------------
# タブ構成
# ---------------------------------------------------------------------------
if _is_actual_data_mode:
    # 実績データモード: What-if分析・戦略比較は非表示
    tab_names = [
        "日次推移", "フェーズ構成", "収支分析", "経営判断フラグ",
        "\U0001f3af 意思決定ダッシュボード", "\U0001f4c8 トレンド分析",
    ]
    tab_names.append("データ")
    if _DATA_MANAGER_AVAILABLE:
        tab_names.append("📋 日次データ入力")
        tab_names.append("🔮 実績分析・予測")
else:
    # シミュレーションモード（従来通り）
    tab_names = [
        "日次推移", "フェーズ構成", "収支分析", "経営判断フラグ",
        "\U0001f3af 意思決定ダッシュボード", "\U0001f52e What-if分析", "\U0001f4c8 トレンド分析",
    ]
    if st.session_state.comparison is not None:
        tab_names.append("戦略比較")
    tab_names.append("データ")
    if _DATA_MANAGER_AVAILABLE:
        tab_names.append("📋 日次データ入力")
        tab_names.append("🔮 実績分析・予測")

tabs = st.tabs(tab_names)
# タブ名→インデックスのマッピング
_tab_idx = {name: i for i, name in enumerate(tab_names)}

# =====================================================================
# 日次データ管理タブ（シミュレーション未実行でも利用可能）
# st.stop() の前に配置することで、シミュレーション未実行でも表示される
# =====================================================================
if _DATA_MANAGER_AVAILABLE:
    _dm_tab_daily_idx = _tab_idx["📋 日次データ入力"]
    _dm_tab_analysis_idx = _tab_idx["🔮 実績分析・予測"]

    # ----- タブ: 📋 日次データ入力 -----
    with tabs[_dm_tab_daily_idx]:
        st.subheader("📋 日次データ入力")

        # --- モード切替 ---
        st.radio(
            "データモード",
            ["📊 実データ入力モード", "🎮 デモモード（サンプルデータ）"],
            key="data_mode",
        )
        _is_demo_mode = st.session_state.data_mode == "🎮 デモモード（サンプルデータ）"

        st.markdown("---")

        if _is_demo_mode:
            # ============================================================
            # デモモード
            # ============================================================
            st.info("これはデモデータです。実際の病棟データではありません。")

            dm_demo_col1, dm_demo_col2 = st.columns(2)
            with dm_demo_col1:
                if st.button("サンプルデータ生成（30日分）", key="dm_gen_sample",
                             help="デモ用に過去30日分のダミーデータを生成します"):
                    st.session_state.demo_data = generate_sample_data(num_days=30, num_beds=total_beds)
                    st.success("サンプルデータ（30日分）を生成しました。")
                    st.rerun()

            with dm_demo_col2:
                if isinstance(st.session_state.demo_data, pd.DataFrame) and len(st.session_state.demo_data) > 0:
                    _demo_csv_str = dm_export_to_csv(st.session_state.demo_data)
                    _demo_date_str = pd.Timestamp.now().strftime("%Y-%m-%d")
                    st.download_button(
                        label="CSVダウンロード",
                        data=_demo_csv_str.encode("utf-8-sig"),
                        file_name=f"bed_daily_data_デモ_{_demo_date_str}.csv",
                        mime="text/csv",
                        key="dm_demo_csv_download",
                    )
                else:
                    st.info("データなし")

            st.markdown("---")

            # --- デモデータ一覧（閲覧のみ） ---
            st.markdown("#### デモデータ一覧（閲覧専用）")
            if isinstance(st.session_state.demo_data, pd.DataFrame) and len(st.session_state.demo_data) > 0:
                _demo_display = st.session_state.demo_data.copy()
                _demo_display["date"] = pd.to_datetime(_demo_display["date"])
                _demo_display = _demo_display.sort_values("date", ascending=False).reset_index(drop=True)
                _demo_display["date_str"] = _demo_display["date"].dt.strftime("%Y-%m-%d")

                _demo_cols_to_show = ["date_str", "total_patients", "new_admissions", "discharges",
                                      "phase_a_count", "phase_b_count", "phase_c_count",
                                      "avg_los", "notes"]
                _demo_cols_available = [c for c in _demo_cols_to_show if c in _demo_display.columns]
                st.dataframe(
                    _demo_display[_demo_cols_available].rename(columns={
                        "date_str": "日付",
                        "total_patients": "在院患者数",
                        "new_admissions": "新規入院",
                        "discharges": "退院",
                        "phase_a_count": "A群",
                        "phase_b_count": "B群",
                        "phase_c_count": "C群",
                        "avg_los": "平均在院日数",
                        "notes": "備考",
                    }),
                    use_container_width=True,
                    height=min(400, 50 + len(_demo_display) * 35),
                    hide_index=True,
                )
                st.caption(f"合計 {len(st.session_state.demo_data)} 件のデモレコード")
            else:
                st.info("デモデータがありません。「サンプルデータ生成」ボタンを押してください。")

        else:
            # ============================================================
            # 実データ入力モード
            # ============================================================

            # --- データ管理セクション ---
            st.markdown("#### データ管理")
            dm_col1, dm_col2 = st.columns(2)

            with dm_col1:
                uploaded_file = st.file_uploader(
                    "CSVアップロード", type=["csv"], key="dm_csv_upload",
                    help="以前ダウンロードしたCSVファイルをアップロードしてデータを復元します"
                )
                if uploaded_file is not None:
                    csv_content = uploaded_file.getvalue().decode("utf-8")
                    imported_df, import_error = import_from_csv(csv_content)
                    if import_error:
                        st.warning(f"インポート警告: {import_error}")
                    if len(imported_df) > 0:
                        st.session_state.daily_data = imported_df
                        st.success(f"{len(imported_df)}件のデータをインポートしました。")
                    elif not import_error:
                        st.info("CSVにデータがありません。")

            with dm_col2:
                if len(st.session_state.daily_data) > 0:
                    csv_str = dm_export_to_csv(st.session_state.daily_data)
                    _real_date_str = pd.Timestamp.now().strftime("%Y-%m-%d")
                    st.download_button(
                        label="CSVダウンロード",
                        data=csv_str.encode("utf-8-sig"),
                        file_name=f"bed_daily_data_実データ_{_real_date_str}.csv",
                        mime="text/csv",
                        key="dm_csv_download",
                    )
                else:
                    st.info("データなし")

            st.markdown("---")

            # --- データ入力フォーム ---
            st.markdown("#### 新しいデータを追加")
            with st.form("dm_add_record_form", clear_on_submit=True):
                form_col1, form_col2 = st.columns(2)
                with form_col1:
                    input_date = st.date_input("日付", value=pd.Timestamp.now().normalize())
                with form_col2:
                    input_total = st.number_input("在院患者数", min_value=0, max_value=94, value=85, step=1)

                form_col3, form_col4 = st.columns(2)
                with form_col3:
                    input_admissions = st.number_input("新規入院数", min_value=0, max_value=30, value=5, step=1)
                with form_col4:
                    input_discharges = st.number_input("退院数", min_value=0, max_value=30, value=5, step=1)

                form_col5, form_col6, form_col7 = st.columns(3)
                with form_col5:
                    input_phase_a = st.number_input("A群（1-5日目）", min_value=0, max_value=94, value=13, step=1)
                with form_col6:
                    input_phase_b = st.number_input("B群（6-14日目）", min_value=0, max_value=94, value=38, step=1)
                with form_col7:
                    input_phase_c = st.number_input("C群（15日目〜）", min_value=0, max_value=94, value=34, step=1)

                form_col8, form_col9 = st.columns(2)
                with form_col8:
                    input_avg_los = st.number_input("平均在院日数（任意）", min_value=0.0, max_value=60.0,
                                                     value=0.0, step=0.1,
                                                     help="0の場合は空欄として扱います")
                with form_col9:
                    input_notes = st.text_input("備考（任意）", value="")

                submitted = st.form_submit_button("追加", type="primary", use_container_width=True)

                if submitted:
                    new_record = {
                        "date": pd.Timestamp(input_date),
                        "total_patients": int(input_total),
                        "new_admissions": int(input_admissions),
                        "discharges": int(input_discharges),
                        "phase_a_count": int(input_phase_a),
                        "phase_b_count": int(input_phase_b),
                        "phase_c_count": int(input_phase_c),
                        "avg_los": float(input_avg_los) if input_avg_los > 0 else pd.NA,
                        "notes": input_notes,
                        "data_source": "manual",
                    }
                    is_valid, error_msg = validate_record(
                        new_record, existing_df=st.session_state.daily_data
                    )
                    if is_valid:
                        st.session_state.daily_data = add_record(
                            st.session_state.daily_data, new_record
                        )
                        st.success(f"{input_date} のデータを追加しました。")
                        st.rerun()
                    else:
                        st.error(f"入力エラー:\n{error_msg}")

            st.markdown("---")

            # --- データ一覧・編集 ---
            st.markdown("#### 記録データ一覧")
            if len(st.session_state.daily_data) > 0:
                display_data = st.session_state.daily_data.copy()
                display_data["date"] = pd.to_datetime(display_data["date"])
                display_data = display_data.sort_values("date", ascending=False).reset_index(drop=True)

                # 表示用にフォーマット
                display_data["date_str"] = display_data["date"].dt.strftime("%Y-%m-%d")

                # st.data_editor で編集可能テーブル（data_sourceカラムは非表示）
                _display_cols = ["date_str", "total_patients", "new_admissions", "discharges",
                                  "phase_a_count", "phase_b_count", "phase_c_count",
                                  "avg_los", "notes"]
                _display_cols_available = [c for c in _display_cols if c in display_data.columns]
                edited_df = st.data_editor(
                    display_data[_display_cols_available].rename(columns={
                        "date_str": "日付",
                        "total_patients": "在院患者数",
                        "new_admissions": "新規入院",
                        "discharges": "退院",
                        "phase_a_count": "A群",
                        "phase_b_count": "B群",
                        "phase_c_count": "C群",
                        "avg_los": "平均在院日数",
                        "notes": "備考",
                    }),
                    use_container_width=True,
                    height=min(400, 50 + len(display_data) * 35),
                    num_rows="fixed",
                    key="dm_data_editor",
                )

                edit_col1, edit_col2 = st.columns(2)
                with edit_col1:
                    if st.button("変更を保存", key="dm_save_edits", type="primary"):
                        # 編集内容を反映
                        try:
                            updated = st.session_state.daily_data.copy()
                            updated = updated.sort_values("date", ascending=False).reset_index(drop=True)
                            col_map_rev = {
                                "在院患者数": "total_patients",
                                "新規入院": "new_admissions",
                                "退院": "discharges",
                                "A群": "phase_a_count",
                                "B群": "phase_b_count",
                                "C群": "phase_c_count",
                                "平均在院日数": "avg_los",
                                "備考": "notes",
                            }
                            for ja_col, en_col in col_map_rev.items():
                                if ja_col in edited_df.columns:
                                    updated[en_col] = edited_df[ja_col].values
                            updated = updated.sort_values("date").reset_index(drop=True)
                            st.session_state.daily_data = updated
                            st.success("変更を保存しました。")
                            st.rerun()
                        except Exception as e:
                            st.error(f"保存エラー: {e}")

                with edit_col2:
                    # 削除用：日付を選択
                    delete_dates = display_data["date_str"].tolist()
                    if delete_dates:
                        del_date = st.selectbox("削除する日付", delete_dates, key="dm_del_date")
                        if st.button("選択した日付を削除", key="dm_delete_btn"):
                            st.session_state.daily_data = delete_record(
                                st.session_state.daily_data, del_date
                            )
                            st.success(f"{del_date} のデータを削除しました。")
                            st.rerun()

                st.caption(f"合計 {len(st.session_state.daily_data)} 件のレコード")
            else:
                st.warning(
                    "まずデータを入力してください。操作方法がわからない場合は"
                    "「🎮 デモモード（サンプルデータ）」でお試しください。"
                )

    # ----- タブ: 🔮 実績分析・予測 -----
    with tabs[_dm_tab_analysis_idx]:
        st.subheader("🔮 実績分析・予測")

        # データモードに応じてデータソースを切り替え
        _is_analysis_demo = st.session_state.get("data_mode") == "🎮 デモモード（サンプルデータ）"
        if _is_analysis_demo:
            _active_data = st.session_state.demo_data if isinstance(st.session_state.demo_data, pd.DataFrame) else pd.DataFrame()
        else:
            _active_data = st.session_state.daily_data

        if _is_analysis_demo:
            st.warning("⚠️ デモデータによる分析です。実際の病棟データではありません。")

        if not isinstance(_active_data, pd.DataFrame) or len(_active_data) < 3:
            if _is_analysis_demo:
                st.warning("分析には最低3日分のデモデータが必要です。「📋 日次データ入力」タブでサンプルデータを生成してください。")
            else:
                st.warning("分析には最低3日分のデータが必要です。「📋 日次データ入力」タブでデータを追加してください。")
        else:
            _analysis_df = _active_data.copy()
            _metrics_df = calculate_daily_metrics(_analysis_df, num_beds=total_beds)

            # --- 上部: 実績サマリー ---
            st.markdown("#### 直近7日間のサマリー")
            _recent7 = _metrics_df.tail(min(7, len(_metrics_df)))

            s_col1, s_col2, s_col3 = st.columns(3)
            with s_col1:
                avg_occ = float(_recent7["occupancy_rate"].mean()) * 100
                st.metric("平均稼働率", f"{avg_occ:.1f}%")
            with s_col2:
                total_adm = int(_recent7["new_admissions"].sum())
                st.metric("入院合計", f"{total_adm}名")
            with s_col3:
                total_dis = int(_recent7["discharges"].sum())
                st.metric("退院合計", f"{total_dis}名")

            s_col4, s_col5, s_col6 = st.columns(3)
            with s_col4:
                avg_a = float(_recent7["phase_a_ratio"].mean()) * 100
                st.metric("A群平均", f"{avg_a:.1f}%")
            with s_col5:
                avg_b = float(_recent7["phase_b_ratio"].mean()) * 100
                st.metric("B群平均", f"{avg_b:.1f}%")
            with s_col6:
                avg_c = float(_recent7["phase_c_ratio"].mean()) * 100
                st.metric("C群平均", f"{avg_c:.1f}%")

            st.markdown("---")

            # --- 中部: 実績グラフ ---
            st.markdown("#### 実績グラフ")

            # 稼働率推移
            fig_occ, ax_occ = plt.subplots(figsize=(12, 4))
            dates = _metrics_df["date"]
            ax_occ.plot(dates, _metrics_df["occupancy_rate"] * 100,
                        color="#2C3E50", linewidth=2, label="稼働率（実績）")
            ax_occ.plot(dates, _metrics_df["occupancy_7d_ma"] * 100,
                        color="#E67E22", linewidth=1.5, linestyle="--", label="7日移動平均")
            ax_occ.axhspan(target_lower * 100, target_upper * 100,
                           alpha=0.15, color="#F39C12",
                           label=f"目標レンジ ({target_lower*100:.0f}-{target_upper*100:.0f}%)")
            ax_occ.set_ylabel("稼働率 (%)")
            ax_occ.set_title("稼働率推移")
            ax_occ.legend(loc="lower right", fontsize=8)
            ax_occ.grid(True, alpha=0.3)
            plt.xticks(rotation=45)
            plt.tight_layout()
            st.pyplot(fig_occ)

            # 入退院数推移（棒グラフ）
            fig_ad, ax_ad = plt.subplots(figsize=(12, 4))
            x_pos = np.arange(len(_metrics_df))
            bar_width = 0.35
            ax_ad.bar(x_pos - bar_width / 2,
                      _metrics_df["new_admissions"].astype(float),
                      bar_width, label="入院", color="#27AE60", alpha=0.8)
            ax_ad.bar(x_pos + bar_width / 2,
                      _metrics_df["discharges"].astype(float),
                      bar_width, label="退院", color="#E74C3C", alpha=0.8)
            # x軸ラベルを日付に
            tick_step = max(1, len(_metrics_df) // 10)
            ax_ad.set_xticks(x_pos[::tick_step])
            ax_ad.set_xticklabels(
                [d.strftime("%m/%d") for d in _metrics_df["date"].iloc[::tick_step]],
                rotation=45
            )
            ax_ad.set_ylabel("人数")
            ax_ad.set_title("入退院数推移")
            ax_ad.legend()
            ax_ad.grid(True, alpha=0.3, axis="y")
            plt.tight_layout()
            st.pyplot(fig_ad)

            # フェーズ構成比推移（積み上げ面グラフ）
            fig_phase, ax_phase = plt.subplots(figsize=(12, 4))
            ax_phase.stackplot(
                _metrics_df["date"],
                _metrics_df["phase_a_ratio"].astype(float) * 100,
                _metrics_df["phase_b_ratio"].astype(float) * 100,
                _metrics_df["phase_c_ratio"].astype(float) * 100,
                labels=["A群（急性期）", "B群（回復期）", "C群（安定期）"],
                colors=["#E74C3C", "#27AE60", "#2980B9"],
                alpha=0.7,
            )
            ax_phase.set_ylabel("構成比 (%)")
            ax_phase.set_title("フェーズ構成比推移")
            ax_phase.legend(loc="upper right", fontsize=8)
            ax_phase.set_ylim(0, 100)
            ax_phase.grid(True, alpha=0.3)
            plt.xticks(rotation=45)
            plt.tight_layout()
            st.pyplot(fig_phase)

            st.markdown("---")

            # --- 中下部: 稼働率予測 ---
            st.markdown("#### 向こう7日間の稼働率予測")
            _pred_df = predict_occupancy_from_history(
                _analysis_df, num_beds=total_beds, horizon=7
            )

            if len(_pred_df) > 0:
                fig_pred, ax_pred = plt.subplots(figsize=(12, 4))

                # 過去実績（実線）
                ax_pred.plot(_metrics_df["date"], _metrics_df["occupancy_rate"] * 100,
                             color="#2C3E50", linewidth=2, label="実績")

                # 予測（破線）
                # 実績の最後と予測の最初をつなぐ
                pred_dates = pd.concat([
                    pd.Series([_metrics_df["date"].iloc[-1]]),
                    _pred_df["date"]
                ])
                pred_values = pd.concat([
                    pd.Series([float(_metrics_df["occupancy_rate"].iloc[-1]) * 100]),
                    _pred_df["predicted_occupancy"] * 100
                ])
                ax_pred.plot(pred_dates, pred_values,
                             color="#E74C3C", linewidth=2, linestyle="--", label="予測")

                # 目標レンジ
                all_dates = pd.concat([_metrics_df["date"], _pred_df["date"]])
                ax_pred.axhspan(target_lower * 100, target_upper * 100,
                                alpha=0.10, color="#F39C12",
                                label=f"目標レンジ ({target_lower*100:.0f}-{target_upper*100:.0f}%)")

                # 信頼度を色で表示
                for _, row in _pred_df.iterrows():
                    color = {"high": "#27AE60", "medium": "#F39C12", "low": "#E74C3C"}
                    ax_pred.scatter(row["date"], row["predicted_occupancy"] * 100,
                                    color=color.get(row["confidence"], "#999"),
                                    s=40, zorder=5)

                ax_pred.set_ylabel("稼働率 (%)")
                ax_pred.set_title("稼働率予測（実績 + 予測）")
                ax_pred.legend(loc="lower right", fontsize=8)
                ax_pred.grid(True, alpha=0.3)
                plt.xticks(rotation=45)
                plt.tight_layout()
                st.pyplot(fig_pred)

                st.caption("予測根拠: 直近14日の入退院ペースから推計。●の色: 🟢高信頼 🟡中信頼 🔴低信頼")

                # 予測テーブル
                pred_display = _pred_df.copy()
                pred_display["date"] = pred_display["date"].dt.strftime("%Y-%m-%d (%a)")
                pred_display["predicted_occupancy"] = (pred_display["predicted_occupancy"] * 100).round(1)
                pred_display = pred_display.rename(columns={
                    "date": "日付",
                    "predicted_patients": "予測患者数",
                    "predicted_occupancy": "予測稼働率(%)",
                    "confidence": "信頼度",
                })
                st.dataframe(pred_display, use_container_width=True, hide_index=True)
            else:
                st.info("予測に十分なデータがありません。")

            st.markdown("---")

            # --- 下部: 月次着地予想 ---
            st.markdown("#### 今月の着地予想")
            _monthly_kpi = predict_monthly_kpi(
                _analysis_df, num_beds=total_beds,
                revenue_params=DEFAULT_REVENUE_PARAMS,
            )

            if _monthly_kpi:
                kpi_col1, kpi_col2, kpi_col3 = st.columns(3)
                with kpi_col1:
                    st.metric("月末予想稼働率", f"{_monthly_kpi['月末予想稼働率']}%")
                    st.metric("月末予想在院患者数", f"{_monthly_kpi['月末予想在院患者数']}名")
                with kpi_col2:
                    st.metric("今月入院数（実績）", f"{_monthly_kpi['今月入院数_実績']}名")
                    st.metric("今月入院数（予測込み）", f"{_monthly_kpi['今月入院数_合計']}名")
                with kpi_col3:
                    gross_profit = _monthly_kpi["推定月次粗利"]
                    if abs(gross_profit) >= 10000:
                        st.metric("推定月次粗利", f"¥{gross_profit/10000:,.1f}万")
                    else:
                        st.metric("推定月次粗利", f"¥{gross_profit:,}")
                    st.metric("推定平均在院日数", f"{_monthly_kpi['推定平均在院日数']}日")

                st.caption(f"残り{_monthly_kpi['残り日数']}日 | 予測入院数: {_monthly_kpi['今月入院数_予測']}名")

            st.markdown("---")

            # --- 最下部: 週次トレンド ---
            st.markdown("#### 週次トレンド")
            _weekly = generate_weekly_summary(_analysis_df, num_beds=total_beds)

            if _weekly:
                weekly_display = []
                for w in _weekly:
                    row = {
                        "期間": f"{w['week_start']}〜{w['week_end']}",
                        "日数": w["days"],
                        "平均稼働率(%)": w["avg_occupancy_rate"],
                        "入院合計": w["total_admissions"],
                        "退院合計": w["total_discharges"],
                        "A群(%)": w["avg_phase_a_ratio"],
                        "B群(%)": w["avg_phase_b_ratio"],
                        "C群(%)": w["avg_phase_c_ratio"],
                    }
                    if w["prev_week_occupancy_change"] is not None:
                        row["前週比(pt)"] = f"{w['prev_week_occupancy_change']:+.1f}"
                    else:
                        row["前週比(pt)"] = "-"
                    weekly_display.append(row)

                st.dataframe(
                    pd.DataFrame(weekly_display),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("週次サマリーを生成するにはデータが不足しています。")

# =====================================================================
# シミュレーション結果タブ / 実績データタブ
# =====================================================================
if _is_actual_data_mode:
    # 実績データモード
    if not _actual_data_available:
        with tabs[0]:
            st.info(
                "実績データがありません。「📋 日次データ入力」タブでデータを入力するか、"
                "デモデータを生成してください。"
            )
        st.stop()
    df = st.session_state.actual_df
    summary = st.session_state.actual_summary
    _active_raw_df = st.session_state.actual_df_raw
    _active_cli_params = st.session_state.actual_params
    # 実データモードでは days_in_month をデータ日数に合わせる
    days_in_month = len(df)
else:
    # シミュレーションモード
    if not _simulation_available:
        with tabs[0]:
            st.info("サイドバーのパラメータを設定し「シミュレーション実行」ボタンを押してください。")
        st.stop()
    df = st.session_state.sim_df
    summary = st.session_state.sim_summary
    _active_raw_df = st.session_state.sim_df_raw
    _active_cli_params = st.session_state.sim_params

# ===== タブ1: 日次推移 =====
with tabs[_tab_idx["日次推移"]]:
    st.subheader("日次推移")
    if _is_actual_data_mode:
        st.info(f"📋 実績データモード（{len(df)}日分のデータを表示中）")
    if _HELP_AVAILABLE and "tab_daily" in HELP_TEXTS:
        with st.expander("📖 このタブの見方と活用法"):
            st.markdown(HELP_TEXTS["tab_daily"])

    # --- 稼働率推移 ---
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(df["日"], df["稼働率"] * 100, color="#2C3E50", linewidth=2, label="稼働率")
    ax.axhspan(
        target_lower * 100, target_upper * 100,
        alpha=0.15, color="#F39C12", label=f"目標レンジ ({target_lower*100:.0f}-{target_upper*100:.0f}%)"
    )
    ax.set_xlabel("日")
    ax.set_ylabel("稼働率 (%)")
    ax.set_title("稼働率推移")
    ax.legend(loc="lower right")
    ax.set_xlim(1, days_in_month)
    ax.grid(True, alpha=0.3)
    st.pyplot(fig)
    plt.close(fig)

    # --- 在院患者数推移 ---
    col1, col2 = st.columns(2)
    with col1:
        fig, ax = plt.subplots(figsize=(6, 3.5))
        ax.plot(df["日"], df["在院患者数"], color="#8E44AD", linewidth=2)
        ax.axhline(y=total_beds, color="#E74C3C", linestyle="--", alpha=0.5, label=f"病床数({total_beds})")
        ax.set_xlabel("日")
        ax.set_ylabel("患者数")
        ax.set_title("在院患者数推移")
        ax.legend()
        ax.set_xlim(1, days_in_month)
        ax.grid(True, alpha=0.3)
        st.pyplot(fig)
        plt.close(fig)

    # --- 新規入院・退院数 ---
    with col2:
        fig, ax = plt.subplots(figsize=(6, 3.5))
        x = df["日"]
        width = 0.35
        ax.bar(x - width/2, df["新規入院"], width, label="新規入院", color=COLOR_B, alpha=0.8)
        ax.bar(x + width/2, df["退院"], width, label="退院", color=COLOR_A, alpha=0.8)
        ax.set_xlabel("日")
        ax.set_ylabel("人数")
        ax.set_title("新規入院・退院数")
        ax.legend()
        ax.set_xlim(0.5, days_in_month + 0.5)
        ax.grid(True, alpha=0.3, axis="y")
        st.pyplot(fig)
        plt.close(fig)

    # --- 日次粗利推移 ---
    fig, ax = plt.subplots(figsize=(12, 4))
    colors_profit = [COLOR_PROFIT if v >= 0 else COLOR_A for v in df["日次粗利"]]
    ax.bar(df["日"], df["日次粗利"] / 10000, color=colors_profit, alpha=0.8)
    ax.axhline(y=0, color="black", linewidth=0.5)
    ax.set_xlabel("日")
    ax.set_ylabel("粗利（万円）")
    ax.set_title("日次粗利推移")
    ax.set_xlim(0.5, days_in_month + 0.5)
    ax.grid(True, alpha=0.3, axis="y")
    st.pyplot(fig)
    plt.close(fig)


# ===== タブ2: フェーズ構成 =====
with tabs[_tab_idx["フェーズ構成"]]:
    st.subheader("フェーズ構成")

    # --- A/B/C群の定義パネル（常時表示） ---
    _col_a, _col_b, _col_c = st.columns(3)
    with _col_a:
        st.markdown(
            '<div style="background:#FFF0F0;padding:12px;border-radius:8px;border-left:4px solid #E74C3C;">'
            '<b style="color:#E74C3C;">🔴 A群（急性期）</b><br>'
            '<b>入院1〜5日目</b><br>'
            '<span style="font-size:0.9em;">'
            '検査・診断・治療開始フェーズ<br>'
            '収益 30,000円 − コスト 28,000円<br>'
            '<b>粗利 2,000円/日</b>（最小）<br><br>'
            '入院初期は検査が集中し、包括払いではコストが収益を圧迫。'
            '<b>35%超で要注意</b>。ただしA群がないとB群が育たない。'
            '</span></div>',
            unsafe_allow_html=True,
        )
    with _col_b:
        st.markdown(
            '<div style="background:#F0FFF0;padding:12px;border-radius:8px;border-left:4px solid #27AE60;">'
            '<b style="color:#27AE60;">🟢 B群（回復期）★稼ぎ頭</b><br>'
            '<b>入院6〜14日目</b><br>'
            '<span style="font-size:0.9em;">'
            '治療安定・回復フェーズ<br>'
            '収益 30,000円 − コスト 13,000円<br>'
            '<b>粗利 17,000円/日</b>（最大）<br><br>'
            '検査一巡でコスト低下。収益は変わらず粗利が最大化する'
            '「ゴールデンタイム」。<b>目標 45%前後</b>。'
            '</span></div>',
            unsafe_allow_html=True,
        )
    with _col_c:
        st.markdown(
            '<div style="background:#F0F0FF;padding:12px;border-radius:8px;border-left:4px solid #2980B9;">'
            '<b style="color:#2980B9;">🔵 C群（退院準備期）＝需給調整弁</b><br>'
            '<b>入院15日目以降</b><br>'
            '<span style="font-size:0.9em;">'
            '医学的安定・退院調整フェーズ<br>'
            '収益 30,000円 − コスト 11,000円<br>'
            '<b>粗利 19,000円/日</b>（中）<br><br>'
            '粗利は高いが長期滞在は機会損失。稼働率低下時は保持、'
            '高騰時は退院促進。<b>30%超で滞留注意</b>。'
            '</span></div>',
            unsafe_allow_html=True,
        )
    st.caption("💡 包括払いのため収益は一律。コストだけが変動 → フェーズ構成が経営を左右します")

    if _HELP_AVAILABLE and "tab_phase" in HELP_TEXTS:
        with st.expander("📖 さらに詳しい活用法を見る"):
            st.markdown(HELP_TEXTS["tab_phase"])

    # --- A/B/C構成比の積み上げ面グラフ ---
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.stackplot(
        df["日"],
        df["A群_患者数"], df["B群_患者数"], df["C群_患者数"],
        labels=["A群（急性期）", "B群（回復期）", "C群（退院準備）"],
        colors=[COLOR_A, COLOR_B, COLOR_C],
        alpha=0.75,
    )
    ax.set_xlabel("日")
    ax.set_ylabel("患者数")
    ax.set_title("フェーズ別患者数推移（積み上げ）")
    ax.legend(loc="upper right")
    ax.set_xlim(1, days_in_month)
    ax.grid(True, alpha=0.3)
    st.pyplot(fig)
    plt.close(fig)

    col1, col2 = st.columns(2)

    # --- 平均円グラフ ---
    with col1:
        fig, ax = plt.subplots(figsize=(5, 5))
        sizes = [summary["A群平均構成比"], summary["B群平均構成比"], summary["C群平均構成比"]]
        labels = [
            f"A群（急性期）\n{sizes[0]:.1f}%",
            f"B群（回復期）\n{sizes[1]:.1f}%",
            f"C群（退院準備）\n{sizes[2]:.1f}%",
        ]
        ax.pie(
            sizes, labels=labels, colors=[COLOR_A, COLOR_B, COLOR_C],
            autopct=None, startangle=90, textprops={"fontsize": 10},
        )
        ax.set_title("A/B/C平均構成比")
        st.pyplot(fig)
        plt.close(fig)

    # --- フェーズ別患者数推移（折れ線） ---
    with col2:
        fig, ax = plt.subplots(figsize=(6, 4.5))
        ax.plot(df["日"], df["A群_患者数"], color=COLOR_A, linewidth=2, label="A群（急性期）")
        ax.plot(df["日"], df["B群_患者数"], color=COLOR_B, linewidth=2, label="B群（回復期）")
        ax.plot(df["日"], df["C群_患者数"], color=COLOR_C, linewidth=2, label="C群（退院準備）")
        ax.set_xlabel("日")
        ax.set_ylabel("患者数")
        ax.set_title("フェーズ別患者数推移")
        ax.legend()
        ax.set_xlim(1, days_in_month)
        ax.grid(True, alpha=0.3)
        st.pyplot(fig)
        plt.close(fig)


# ===== タブ3: 収支分析 =====
with tabs[_tab_idx["収支分析"]]:
    st.subheader("収支分析")
    if _HELP_AVAILABLE and "tab_finance" in HELP_TEXTS:
        with st.expander("📖 このタブの見方と活用法"):
            st.markdown(HELP_TEXTS["tab_finance"])

    # --- メトリクスカード ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("月次収益", fmt_yen(summary["月次収益"]))
    c2.metric("月次コスト", fmt_yen(summary["月次コスト"]))
    c3.metric("月次粗利", fmt_yen(summary["月次粗利"]))
    c4.metric("平均稼働率", f"{summary['平均稼働率']:.1f}%")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("月間入院数", f"{summary['月間入院数']}人")
    c6.metric("月間退院数", f"{summary['月間退院数']}人")
    c7.metric("目標レンジ内日数", f"{summary['目標レンジ内日数']}/{days_in_month}日")
    c8.metric("目標レンジ内率", f"{summary['目標レンジ内率']}%")

    # --- 日次収益・コスト・粗利 ---
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(df["日"], df["日次収益"] / 10000, color=COLOR_REVENUE, linewidth=2, label="収益")
    ax.plot(df["日"], df["日次コスト"] / 10000, color=COLOR_COST, linewidth=2, label="コスト")
    ax.plot(df["日"], df["日次粗利"] / 10000, color=COLOR_PROFIT, linewidth=2, label="粗利")
    ax.axhline(y=0, color="black", linewidth=0.5)
    ax.set_xlabel("日")
    ax.set_ylabel("金額（万円）")
    ax.set_title("日次収益・コスト・粗利推移")
    ax.legend()
    ax.set_xlim(1, days_in_month)
    ax.grid(True, alpha=0.3)
    st.pyplot(fig)
    plt.close(fig)

    # --- 累積粗利推移 ---
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.fill_between(
        df["日"], df["累積粗利"] / 10000, 0,
        where=df["累積粗利"] >= 0, color=COLOR_PROFIT, alpha=0.3,
    )
    ax.fill_between(
        df["日"], df["累積粗利"] / 10000, 0,
        where=df["累積粗利"] < 0, color=COLOR_A, alpha=0.3,
    )
    ax.plot(df["日"], df["累積粗利"] / 10000, color=COLOR_PROFIT, linewidth=2)
    ax.axhline(y=0, color="black", linewidth=0.5)
    ax.set_xlabel("日")
    ax.set_ylabel("累積粗利（万円）")
    ax.set_title("累積粗利推移")
    ax.set_xlim(1, days_in_month)
    ax.grid(True, alpha=0.3)
    st.pyplot(fig)
    plt.close(fig)


# ===== タブ4: 経営判断フラグ =====
with tabs[_tab_idx["経営判断フラグ"]]:
    st.subheader("経営判断フラグ")
    if _HELP_AVAILABLE and "tab_flags" in HELP_TEXTS:
        with st.expander("📖 このタブの見方と活用法"):
            st.markdown(HELP_TEXTS["tab_flags"])

    # --- フラグ一覧テーブル ---
    flag_df = df[["日", "稼働率", "在院患者数", "経営判断フラグ"]].copy()
    flag_df["稼働率"] = (flag_df["稼働率"] * 100).round(1).astype(str) + "%"

    def highlight_flags(row):
        """フラグに基づき行の背景色を設定"""
        flags = row["経営判断フラグ"]
        if "日次赤字" in flags:
            return ["background-color: #FADBD8"] * len(row)
        elif "稼働率低下" in flags:
            return ["background-color: #FEF9E7"] * len(row)
        elif "稼働率超過" in flags or "入院抑制中" in flags:
            return ["background-color: #FDEBD0"] * len(row)
        elif "正常運用" in flags:
            return ["background-color: #D5F5E3"] * len(row)
        return [""] * len(row)

    styled = flag_df.style.apply(highlight_flags, axis=1)
    st.dataframe(styled, use_container_width=True, height=400)

    # --- 目標レンジ内日数 ---
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("目標レンジ内日数", f"{summary['目標レンジ内日数']}/{days_in_month}日")
        st.metric("目標レンジ内率", f"{summary['目標レンジ内率']}%")

    with col2:
        st.markdown("**フラグ発生日数**")
        for flag, count in sorted(summary["フラグ集計"].items(), key=lambda x: -x[1]):
            if flag == "正常運用":
                st.success(f"{flag}: {count}日")
            elif "赤字" in flag:
                st.error(f"{flag}: {count}日")
            elif "低下" in flag or "高" in flag:
                st.warning(f"{flag}: {count}日")
            else:
                st.info(f"{flag}: {count}日")

    # --- 推奨アクション ---
    st.markdown("---")
    st.subheader("推奨アクション")
    avg_occ = summary["平均稼働率"]
    if avg_occ < target_lower * 100:
        st.warning(
            f"平均稼働率 {avg_occ:.1f}% が目標下限 {target_lower*100:.0f}% を下回っています。\n\n"
            "**推奨:** 入院促進策の強化（紹介元への営業、救急受入体制の強化）"
        )
    elif avg_occ > target_upper * 100:
        st.warning(
            f"平均稼働率 {avg_occ:.1f}% が目標上限 {target_upper*100:.0f}% を上回っています。\n\n"
            "**推奨:** 退院調整の前倒し、地域連携室との早期カンファレンス"
        )
    else:
        st.success(
            f"平均稼働率 {avg_occ:.1f}% は目標レンジ内です。現行運用を維持してください。"
        )

    if summary["C群平均構成比"] > 40:
        st.warning(
            f"C群（退院準備期）の平均構成比が {summary['C群平均構成比']:.1f}% と高めです。\n\n"
            "**推奨:** 退院支援の早期介入、転院調整の効率化"
        )


# ===== タブ5-7: 意思決定支援タブ =====
# --- タブ5: 意思決定ダッシュボード ---
with tabs[_tab_idx["\U0001f3af 意思決定ダッシュボード"]]:
    if not _DECISION_SUPPORT_AVAILABLE:
        st.error("意思決定支援機能はまだ利用できません。CLI版（bed_control_simulator.py）に必要な関数が実装されていません。")
    else:
        st.subheader("\U0001f3af 意思決定ダッシュボード")
        if _HELP_AVAILABLE and "tab_decision" in HELP_TEXTS:
            with st.expander("📖 このタブの見方と活用法"):
                st.markdown(HELP_TEXTS["tab_decision"])
        _raw_df = _active_raw_df
        _cli_params = _active_cli_params

        # --- 病棟状態カード ---
        _day_idx = len(_raw_df) - 1  # 最終日を評価対象
        _ward_status = assess_ward_status(_raw_df, _day_idx, _cli_params)

        _score = _ward_status.get("score", "unknown")
        if _score == "healthy":
            st.success(f"病棟状態: {_score.upper()} (スコア: {_ward_status['score_numeric']})")
        elif _score == "caution":
            st.warning(f"病棟状態: {_score.upper()} (スコア: {_ward_status['score_numeric']})")
        else:
            st.error(f"病棟状態: {_score.upper()} (スコア: {_ward_status['score_numeric']})")

        _ws_c1, _ws_c2, _ws_c3 = st.columns(3)
        _ws_c1.metric("稼働率", f"{_ward_status['occupancy_rate']*100:.1f}%")
        _ws_c2.metric("ステータススコア", f"{_ward_status['score_numeric']}")
        _ws_c3.metric("1床あたり粗利", fmt_yen(int(_ward_status.get('profit_per_bed', 0))))

        if _ward_status.get("messages"):
            st.markdown("**メッセージ:**")
            for _msg in _ward_status["messages"]:
                st.markdown(f"- {_msg}")

        st.markdown("---")

        # --- 稼働率予測 ---
        st.subheader("稼働率予測（5日間）")
        _forecast = predict_occupancy(_raw_df, _day_idx, _cli_params, horizon=5)

        fig, ax = plt.subplots(figsize=(12, 4))
        # 実績（最後の10日分）
        _history_start = max(0, len(_raw_df) - 10)
        _hist_days = list(range(_history_start + 1, len(_raw_df) + 1))
        _hist_occ = [_raw_df.iloc[i]["occupancy_rate"] * 100 for i in range(_history_start, len(_raw_df))]
        ax.plot(_hist_days, _hist_occ, color="#2C3E50", linewidth=2, label="実績", marker="o", markersize=3)

        # 予測
        _pred_days = [len(_raw_df) + f["day_offset"] for f in _forecast]
        _pred_occ = [f["predicted_occupancy"] * 100 for f in _forecast]
        _confidences = [f.get("confidence", "medium") for f in _forecast]
        _alphas = {"high": 1.0, "medium": 0.6, "low": 0.3}
        ax.plot(_pred_days, _pred_occ, color="#E74C3C", linewidth=2, linestyle="--", label="予測", marker="s", markersize=4)
        for _px, _py, _conf in zip(_pred_days, _pred_occ, _confidences):
            _a = _alphas.get(_conf, 0.5)
            ax.scatter([_px], [_py], color="#E74C3C", alpha=_a, s=60, zorder=5)

        # 目標レンジ帯
        ax.axhspan(target_lower * 100, target_upper * 100, alpha=0.15, color="#F39C12",
                    label=f"目標レンジ ({target_lower*100:.0f}-{target_upper*100:.0f}%)")
        ax.set_xlabel("日")
        ax.set_ylabel("稼働率 (%)")
        ax.set_title("稼働率 実績 + 予測")
        ax.legend(loc="lower right")
        ax.grid(True, alpha=0.3)
        st.pyplot(fig)
        plt.close(fig)

        st.markdown("---")

        # --- 推奨アクション ---
        st.subheader("推奨アクション")
        _actions = suggest_actions(_ward_status, _forecast, _cli_params)
        _cat_icons = {"discharge": "\U0001f504", "admission": "\U0001f4e5", "hold": "\u23f8\ufe0f", "alert": "\u26a0\ufe0f"}
        for _act in sorted(_actions, key=lambda a: a.get("priority", 99)):
            _icon = _cat_icons.get(_act.get("category", ""), "")
            _text = f"{_icon} **{_act['action']}**\n\n期待効果: {_act.get('expected_impact', 'N/A')}"
            _prio = _act.get("priority", 5)
            if _prio == 1:
                st.error(_text)
            elif _prio == 2:
                st.warning(_text)
            else:
                st.info(_text)

        st.markdown("---")

        # --- LOS最適化 ---
        st.subheader("在院日数（LOS）最適化分析")
        _los_impact = simulate_los_impact(_raw_df, _cli_params)
        _optimal_los = calculate_optimal_los_range(_raw_df, _cli_params)

        fig, ax = plt.subplots(figsize=(10, 4))
        _deltas = [r["delta_days"] for r in _los_impact]
        _pdiffs = [r["profit_diff"] / 10000 for r in _los_impact]
        _bar_colors = [COLOR_PROFIT if v >= 0 else COLOR_A for v in _pdiffs]
        ax.bar(_deltas, _pdiffs, color=_bar_colors, alpha=0.8)
        ax.axhline(y=0, color="black", linewidth=0.5)
        ax.set_xlabel("在院日数変化（日）")
        ax.set_ylabel("粗利変化（万円）")
        ax.set_title("在院日数変化が月次粗利に与える影響")
        ax.set_xticks(_deltas)
        ax.set_xticklabels([f"{d:+d}" for d in _deltas])
        ax.grid(True, alpha=0.3, axis="y")
        st.pyplot(fig)
        plt.close(fig)

        st.info(
            f"**最適在院日数レンジ:** {_optimal_los['min_los']:.1f} 〜 {_optimal_los['max_los']:.1f} 日 "
            f"（最適値: {_optimal_los['optimal_los']} 日）\n\n"
            f"期待月次粗利: {fmt_yen(_optimal_los['expected_monthly_profit'])}\n\n"
            f"現在の設定: {avg_los} 日"
        )

# --- タブ6: What-if分析（シミュレーションモードのみ） ---
if "\U0001f52e What-if分析" in _tab_idx:
    with tabs[_tab_idx["\U0001f52e What-if分析"]]:
        if not _DECISION_SUPPORT_AVAILABLE:
            st.error("意思決定支援機能はまだ利用できません。CLI版（bed_control_simulator.py）に必要な関数が実装されていません。")
        else:
            st.subheader("\U0001f52e What-if分析")
            if _HELP_AVAILABLE and "tab_whatif" in HELP_TEXTS:
                with st.expander("📖 このタブの見方と活用法"):
                    st.markdown(HELP_TEXTS["tab_whatif"])
            _raw_df = _active_raw_df
            _cli_params = _active_cli_params

            _scenario_type = st.radio(
                "シナリオ選択",
                ["退院シナリオ", "入院需要変動シナリオ"],
                horizontal=True,
                key="whatif_scenario_type",
            )

            if _scenario_type == "退院シナリオ":
                st.markdown("#### 退院シナリオ")
                _wi_day = st.slider("対象日", 1, len(_raw_df), value=len(_raw_df), key="wi_day")
                _wi_n = st.slider("退院人数", 1, 10, value=2, key="wi_n_discharge")
                _wi_phase = st.radio("対象フェーズ", ["A", "B", "C"], index=2, horizontal=True, key="wi_phase")

                if st.button("シナリオ実行", key="btn_whatif_discharge"):
                    _wi_result = whatif_discharge(_raw_df, _wi_day - 1, _cli_params, _wi_n, target_phase=_wi_phase)

                    _wc1, _wc2 = st.columns(2)
                    with _wc1:
                        st.markdown("**Before（現状）**")
                        st.metric("稼働率", f"{_wi_result['baseline_occupancy']*100:.1f}%")
                        st.metric("日次粗利", fmt_yen(int(_wi_result["baseline_profit"])))
                    with _wc2:
                        st.markdown("**After（シナリオ）**")
                        _occ_delta = (_wi_result["scenario_occupancy"] - _wi_result["baseline_occupancy"]) * 100
                        _profit_delta = _wi_result["scenario_profit"] - _wi_result["baseline_profit"]
                        st.metric("稼働率", f"{_wi_result['scenario_occupancy']*100:.1f}%",
                                  delta=f"{_occ_delta:+.1f}%")
                        st.metric("日次粗利", fmt_yen(int(_wi_result["scenario_profit"])),
                                  delta=fmt_yen(int(_profit_delta)))

                    _rec = _wi_result.get("recommendation", "")
                    if "推奨" in _rec or "有効" in _rec:
                        st.info(f"**推奨:** {_rec}")
                    elif "注意" in _rec or "リスク" in _rec:
                        st.warning(f"**注意:** {_rec}")
                    else:
                        st.info(f"**分析結果:** {_rec}")

            else:
                st.markdown("#### 入院需要変動シナリオ")
                _surge_pct = st.slider("変動率", -50, 50, value=0, step=5, format="%d%%", key="wi_surge_pct")

                if st.button("シナリオ実行", key="btn_whatif_surge"):
                    _surge_result = whatif_admission_surge(_cli_params, surge_pct=_surge_pct / 100.0,
                                                           strategy=STRATEGY_MAP[strategy])

                    _sc1, _sc2 = st.columns(2)
                    with _sc1:
                        st.markdown("**Before（現状）**")
                        st.metric("稼働率", f"{_surge_result['baseline_occupancy']*100:.1f}%")
                        st.metric("月次粗利", fmt_yen(int(_surge_result["baseline_profit"])))
                    with _sc2:
                        st.markdown("**After（シナリオ）**")
                        _s_occ_delta = (_surge_result["scenario_occupancy"] - _surge_result["baseline_occupancy"]) * 100
                        _s_profit_delta = _surge_result["scenario_profit"] - _surge_result["baseline_profit"]
                        st.metric("稼働率", f"{_surge_result['scenario_occupancy']*100:.1f}%",
                                  delta=f"{_s_occ_delta:+.1f}%")
                        st.metric("月次粗利", fmt_yen(int(_surge_result["scenario_profit"])),
                                  delta=fmt_yen(int(_s_profit_delta)))

                    _s_rec = _surge_result.get("recommendation", "")
                    if "推奨" in _s_rec or "有効" in _s_rec:
                        st.info(f"**推奨:** {_s_rec}")
                    elif "注意" in _s_rec or "リスク" in _s_rec:
                        st.warning(f"**注意:** {_s_rec}")
                    else:
                        st.info(f"**分析結果:** {_s_rec}")

# --- タブ: トレンド分析 ---
with tabs[_tab_idx["\U0001f4c8 トレンド分析"]]:
    if not _DECISION_SUPPORT_AVAILABLE:
        st.error("意思決定支援機能はまだ利用できません。CLI版（bed_control_simulator.py）に必要な関数が実装されていません。")
    else:
        st.subheader("\U0001f4c8 トレンド分析")
        if _HELP_AVAILABLE and "tab_trends" in HELP_TEXTS:
            with st.expander("📖 このタブの見方と活用法"):
                st.markdown(HELP_TEXTS["tab_trends"])
        _raw_df = _active_raw_df
        _cli_params = _active_cli_params

        _trend_window = st.slider("移動平均ウィンドウ（日）", 3, 14, value=7, key="trend_window")
        _trends = calculate_trends(_raw_df, _cli_params, window=_trend_window)

        _trend_arrows = {"rising": "\u2197\ufe0f 上昇", "falling": "\u2198\ufe0f 下降", "stable": "\u2192 安定"}

        # --- 稼働率トレンド ---
        st.markdown("### 稼働率トレンド")
        _occ_trend_label = _trend_arrows.get(_trends.get("occupancy_trend", "stable"), _trends.get("occupancy_trend", ""))
        st.markdown(f"**トレンド:** {_occ_trend_label}")

        fig, ax = plt.subplots(figsize=(12, 4))
        _daily_occ = [_raw_df.iloc[i]["occupancy_rate"] * 100 for i in range(len(_raw_df))]
        _days_range = list(range(1, len(_raw_df) + 1))
        ax.plot(_days_range, _daily_occ, color="#BDC3C7", linewidth=1, alpha=0.7, label="日次実績")
        _occ_ma = _trends.get("occupancy_ma", [])
        if _occ_ma:
            _ma_start = len(_days_range) - len(_occ_ma)
            _ma_days = _days_range[_ma_start:]
            ax.plot(_ma_days, [v * 100 for v in _occ_ma], color="#2C3E50", linewidth=2.5, label=f"{_trend_window}日移動平均")
        ax.axhspan(target_lower * 100, target_upper * 100, alpha=0.15, color="#F39C12",
                    label=f"目標レンジ ({target_lower*100:.0f}-{target_upper*100:.0f}%)")
        ax.set_xlabel("日")
        ax.set_ylabel("稼働率 (%)")
        ax.set_title("稼働率トレンド")
        ax.legend(loc="lower right")
        ax.grid(True, alpha=0.3)
        st.pyplot(fig)
        plt.close(fig)

        st.markdown("---")

        # --- フェーズ構成比トレンド ---
        st.markdown("### フェーズ構成比トレンド")
        _phase_a_label = _trend_arrows.get(_trends.get("phase_a_trend", "stable"), _trends.get("phase_a_trend", ""))
        _phase_b_label = _trend_arrows.get(_trends.get("phase_b_trend", "stable"), _trends.get("phase_b_trend", ""))
        _phase_c_label = _trend_arrows.get(_trends.get("phase_c_trend", "stable"), _trends.get("phase_c_trend", ""))
        st.markdown(f"A群: {_phase_a_label} / B群: {_phase_b_label} / C群: {_phase_c_label}")

        fig, ax = plt.subplots(figsize=(12, 4))
        _phase_a_ma = _trends.get("phase_a_ma", [])
        _phase_b_ma = _trends.get("phase_b_ma", [])
        _phase_c_ma = _trends.get("phase_c_ma", [])
        if _phase_a_ma:
            _pm_start = len(_days_range) - len(_phase_a_ma)
            _pm_days = _days_range[_pm_start:]
            ax.plot(_pm_days, [v * 100 for v in _phase_a_ma], color=COLOR_A, linewidth=2, label="A群（急性期）")
            ax.plot(_pm_days, [v * 100 for v in _phase_b_ma], color=COLOR_B, linewidth=2, label="B群（回復期）")
            ax.plot(_pm_days, [v * 100 for v in _phase_c_ma], color=COLOR_C, linewidth=2, label="C群（退院準備）")
        ax.set_xlabel("日")
        ax.set_ylabel("構成比 (%)")
        ax.set_title("フェーズ構成比トレンド（移動平均）")
        ax.legend()
        ax.grid(True, alpha=0.3)
        st.pyplot(fig)
        plt.close(fig)

        st.markdown("---")

        # --- 粗利効率トレンド ---
        st.markdown("### 粗利効率トレンド")
        _profit_trend_label = _trend_arrows.get(_trends.get("profit_efficiency_trend", "stable"),
                                                 _trends.get("profit_efficiency_trend", ""))
        st.markdown(f"**トレンド:** {_profit_trend_label}")

        _ppb_ma = _trends.get("profit_per_bed_ma", [])
        if _ppb_ma:
            fig, ax = plt.subplots(figsize=(12, 4))
            _ppb_start = len(_days_range) - len(_ppb_ma)
            _ppb_days = _days_range[_ppb_start:]
            ax.plot(_ppb_days, [v / 10000 for v in _ppb_ma], color=COLOR_PROFIT, linewidth=2.5)
            ax.set_xlabel("日")
            ax.set_ylabel("1床あたり粗利（万円）")
            ax.set_title("1床あたり粗利トレンド（移動平均）")
            ax.grid(True, alpha=0.3)
            st.pyplot(fig)
            plt.close(fig)

        st.markdown("---")

        # --- 警告セクション ---
        _alerts = _trends.get("alerts", [])
        if _alerts:
            st.markdown("### 警告")
            for _alert in _alerts:
                st.warning(_alert)
        else:
            st.success("現在、警告はありません。")


# ===== タブ: 戦略比較（条件付き、シミュレーションモードのみ） =====
if "戦略比較" in _tab_idx and st.session_state.comparison is not None:
    with tabs[_tab_idx["戦略比較"]]:
        st.subheader("全戦略比較")
        if _HELP_AVAILABLE and "tab_strategy_compare" in HELP_TEXTS:
            with st.expander("📖 このタブの見方と活用法"):
                st.markdown(HELP_TEXTS["tab_strategy_compare"])
        comparison = st.session_state.comparison

        # --- 比較テーブル ---
        compare_keys = [
            "月次収益", "月次コスト", "月次粗利",
            "平均稼働率", "月間入院数", "月間退院数",
            "目標レンジ内日数", "目標レンジ内率",
            "A群平均構成比", "B群平均構成比", "C群平均構成比",
        ]
        compare_data = {}
        for strat_name, strat_summary in comparison.items():
            compare_data[strat_name] = {k: strat_summary[k] for k in compare_keys}

        compare_df = pd.DataFrame(compare_data).T
        compare_df.index.name = "戦略"

        # 金額カラムをフォーマット
        for col in ["月次収益", "月次コスト", "月次粗利"]:
            compare_df[col] = compare_df[col].apply(lambda x: fmt_yen_full(int(x)))

        # パーセンテージカラム
        for col in ["平均稼働率", "目標レンジ内率", "A群平均構成比", "B群平均構成比", "C群平均構成比"]:
            compare_df[col] = compare_df[col].apply(lambda x: f"{x}%")

        st.dataframe(compare_df, use_container_width=True)

        # --- 主要指標の棒グラフ比較 ---
        strategies_list = list(comparison.keys())
        profits = [comparison[s]["月次粗利"] / 10000 for s in strategies_list]
        occ_rates = [comparison[s]["平均稼働率"] for s in strategies_list]
        in_range = [comparison[s]["目標レンジ内率"] for s in strategies_list]

        fig, axes = plt.subplots(1, 3, figsize=(14, 4))
        bar_colors = [COLOR_A, COLOR_B, COLOR_C]

        axes[0].bar(strategies_list, profits, color=bar_colors, alpha=0.8)
        axes[0].set_title("月次粗利（万円）")
        axes[0].grid(True, alpha=0.3, axis="y")
        for i, v in enumerate(profits):
            axes[0].text(i, v + max(profits)*0.02, f"{v:.0f}", ha="center", fontsize=9)

        axes[1].bar(strategies_list, occ_rates, color=bar_colors, alpha=0.8)
        axes[1].set_title("平均稼働率 (%)")
        axes[1].grid(True, alpha=0.3, axis="y")
        for i, v in enumerate(occ_rates):
            axes[1].text(i, v + 0.2, f"{v:.1f}", ha="center", fontsize=9)

        axes[2].bar(strategies_list, in_range, color=bar_colors, alpha=0.8)
        axes[2].set_title("目標レンジ内率 (%)")
        axes[2].grid(True, alpha=0.3, axis="y")
        for i, v in enumerate(in_range):
            axes[2].text(i, v + 0.5, f"{v:.1f}", ha="center", fontsize=9)

        plt.tight_layout()
        st.pyplot(fig)
        plt.close(fig)

        # --- 最適戦略のハイライト ---
        st.markdown("---")
        best_profit = max(comparison.items(), key=lambda x: x[1]["月次粗利"])
        best_occ = min(comparison.items(),
                       key=lambda x: abs(x[1]["平均稼働率"] - (target_lower + target_upper) / 2 * 100))
        best_range = max(comparison.items(), key=lambda x: x[1]["目標レンジ内率"])

        col1, col2, col3 = st.columns(3)
        with col1:
            st.success(f"**粗利最大:** {best_profit[0]}\n\n{fmt_yen(best_profit[1]['月次粗利'])}")
        with col2:
            st.success(f"**稼働率最適:** {best_occ[0]}\n\n{best_occ[1]['平均稼働率']:.1f}%")
        with col3:
            st.success(f"**レンジ内最大:** {best_range[0]}\n\n{best_range[1]['目標レンジ内率']:.1f}%")



# ===== タブ: データ =====
with tabs[_tab_idx["データ"]]:
    st.subheader("日次データ")
    if _HELP_AVAILABLE and "tab_data" in HELP_TEXTS:
        with st.expander("📖 このタブの見方と活用法"):
            st.markdown(HELP_TEXTS["tab_data"])

    # データ表示
    display_df = df.copy()
    display_df["稼働率"] = (display_df["稼働率"] * 100).round(1)
    st.dataframe(display_df, use_container_width=True, height=500)

    # CSVダウンロード
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False, encoding="utf-8-sig")
    st.download_button(
        label="CSVダウンロード",
        data=csv_buffer.getvalue(),
        file_name="bed_control_simulation.csv",
        mime="text/csv",
    )

# ---------------------------------------------------------------------------
# フッター
# ---------------------------------------------------------------------------
st.markdown("---")
if _is_actual_data_mode:
    st.caption(
        f"データソース: **実績データ** | "
        f"病床数: {total_beds} | "
        f"目標稼働率: {target_lower*100:.0f}-{target_upper*100:.0f}%"
    )
else:
    st.caption(
        f"戦略: **{strategy}** | "
        f"病床数: {total_beds} | "
        f"目標稼働率: {target_lower*100:.0f}-{target_upper*100:.0f}% | "
        f"月間入院: {monthly_admissions}件 | "
        f"平均在院日数: {avg_los}日"
    )
