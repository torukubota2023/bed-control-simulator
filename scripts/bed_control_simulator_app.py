# 実行方法: streamlit run scripts/bed_control_simulator_app.py
"""
地域包括医療病棟 ベッドコントロールシミュレーター（Streamlit版）

おもろまちメディカルセンター（94床）向け
CLI版(bed_control_simulator.py)をインポートし、インタラクティブなUI上で
稼働率・平均在院日数・診療報酬構造をシミュレートする。
"""

import sys
import os
import io
import calendar
from datetime import date

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# 同ディレクトリのモジュールをインポートできるようにパスを追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from bed_control_simulator import (
        create_default_params,
        simulate_bed_control,
        summarize_results,
        compare_strategies,
    )
    _CORE_AVAILABLE = True
except Exception as _core_err:
    _CORE_AVAILABLE = False
    import traceback as _core_tb
    _CORE_ERROR = f"{_core_err}\n{_core_tb.format_exc()}"

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
        whatif_mixed_scenario,
        whatif_weekly_plan,
        generate_decision_report,
        calculate_marginal_bed_value,
        optimize_discharge_plan,
    )
    _DECISION_SUPPORT_AVAILABLE = True
except Exception as _e:
    import traceback as _tb
    _DECISION_SUPPORT_ERROR = f"{_e}\n{_tb.format_exc()}"

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
        create_initial_buckets_from_list,
        buckets_to_abc,
        advance_day_buckets,
        DAY_BUCKET_KEYS,
        WARD_CONFIG,
        TOTAL_BEDS,
        get_ward_beds,
        aggregate_wards,
    )
    _DATA_MANAGER_AVAILABLE = True
except Exception as _dm_err:
    import traceback as _dm_tb
    _DATA_MANAGER_ERROR = f"{_dm_err}\n{_dm_tb.format_exc()}"

# SQLite永続化モジュール
_DB_AVAILABLE = False
try:
    from db_manager import (
        save_daily_records,
        load_daily_records,
        save_abc_state,
        load_abc_state,
        save_day_buckets,
        load_day_buckets,
        clear_all_data as db_clear_all,
    )
    _DB_AVAILABLE = True
except Exception as _db_err:
    pass

# ベッドマップUI（初期セットアップ用）
_BED_MAP_AVAILABLE = False
try:
    from bed_map_ui import render_bed_map, render_confirmation, bed_data_to_buckets
    _BED_MAP_AVAILABLE = True
except Exception as _bm_err:
    import traceback as _bm_tb
    _BED_MAP_ERROR = f"{_bm_err}\n{_bm_tb.format_exc()}"

# 医師マスター管理モジュール
_DOCTOR_MASTER_AVAILABLE = False
try:
    import doctor_master as dm_doctor
    _DOCTOR_MASTER_AVAILABLE = True
except Exception as _doc_err:
    pass

# 入退院詳細データ
try:
    from bed_data_manager import (
        create_empty_detail_dataframe,
        add_admission_event,
        add_discharge_event,
        get_events_by_date,
        get_events_by_doctor,
        get_monthly_summary_by_doctor,
        get_discharge_weekday_distribution,
        save_details,
        load_details,
        analyze_doctor_performance,
    )
    _DETAIL_DATA_AVAILABLE = True
except Exception:
    _DETAIL_DATA_AVAILABLE = False

# ---------------------------------------------------------------------------
# 入退院予測エンジン（曜日別・祝日対応）
# ---------------------------------------------------------------------------
try:
    import jpholiday as _jpholiday
    _JPHOLIDAY_AVAILABLE = True
except ImportError:
    _JPHOLIDAY_AVAILABLE = False


def _is_holiday_or_weekend(d: date) -> bool:
    """土日または日本の祝日かどうかを判定する。"""
    if d.weekday() >= 5:  # 土=5, 日=6
        return True
    if _JPHOLIDAY_AVAILABLE:
        return _jpholiday.is_holiday(d)
    return False


def _is_bridge_holiday(d: date) -> bool:
    """祝日に挟まれた平日（飛び石連休の谷間）を判定する。
    前日と翌日が両方とも祝日/土日ならTrue。"""
    from datetime import timedelta
    prev_day = d - timedelta(days=1)
    next_day = d + timedelta(days=1)
    return _is_holiday_or_weekend(prev_day) and _is_holiday_or_weekend(next_day)


def _predict_admission_discharge(
    df_history: pd.DataFrame,
    num_beds: int,
    horizon: int = 7,
    min_weeks_for_dow: int = 2,
) -> pd.DataFrame:
    """過去の実績データから今後horizon日の入退院を予測する。

    予測ロジック:
        1. 曜日別平均（データが min_weeks_for_dow 週以上ある場合）
           - 直近データに高い重みをかける指数加重平均を使用
        2. 祝日・長期休日は「日曜パターン」を適用
           （当院: 休日の入院≒0、退院は週末に多い傾向を反映）
        3. 飛び石連休の谷間日も休日扱い
        4. データが少ない場合は全体平均にフォールバック

    Args:
        df_history: 過去の日次データ（date, new_admissions, discharges列が必要）
        num_beds: 病床数
        horizon: 予測日数（デフォルト7日）
        min_weeks_for_dow: 曜日別平均を使うために必要な最小週数

    Returns:
        DataFrame: date, pred_admissions, pred_discharges, pred_net,
                   pred_patients, pred_occupancy, day_type, confidence
    """
    from datetime import timedelta

    df = df_history.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    # --- 曜日別統計の構築 ---
    df["weekday"] = df["date"].dt.dayofweek  # 0=月 ~ 6=日
    n_days = len(df)
    n_weeks = n_days / 7.0

    # 指数加重: 直近ほど重みが大きい（半減期=14日）
    halflife = 14
    weights = np.exp(-np.log(2) * np.arange(n_days)[::-1] / halflife)
    df["_weight"] = weights

    use_dow = n_weeks >= min_weeks_for_dow

    if use_dow:
        # 曜日別の加重平均
        dow_stats = {}
        for dow in range(7):
            mask = df["weekday"] == dow
            subset = df[mask]
            if len(subset) == 0:
                dow_stats[dow] = {
                    "adm_mean": float(df["new_admissions"].mean()),
                    "dis_mean": float(df["discharges"].mean()),
                    "adm_std": float(df["new_admissions"].std()),
                    "dis_std": float(df["discharges"].std()),
                    "n_samples": 0,
                }
            else:
                w = subset["_weight"].values
                w_norm = w / w.sum()
                dow_stats[dow] = {
                    "adm_mean": float(np.average(subset["new_admissions"].values, weights=w_norm)),
                    "dis_mean": float(np.average(subset["discharges"].values, weights=w_norm)),
                    "adm_std": float(subset["new_admissions"].std()),
                    "dis_std": float(subset["discharges"].std()),
                    "n_samples": len(subset),
                }
    else:
        # フォールバック: 全体平均
        global_stats = {
            "adm_mean": float(df["new_admissions"].mean()),
            "dis_mean": float(df["discharges"].mean()),
            "adm_std": float(df["new_admissions"].std()),
            "dis_std": float(df["discharges"].std()),
            "n_samples": n_days,
        }

    # 日曜日のパターン（祝日に使用）
    sunday_stats = None
    if use_dow and dow_stats[6]["n_samples"] > 0:
        sunday_stats = dow_stats[6]

    # --- 予測生成 ---
    last_date = df["date"].iloc[-1].date() if hasattr(df["date"].iloc[-1], "date") else df["date"].iloc[-1]
    last_patients = int(df.iloc[-1].get("total_patients", 0) or 0)

    rows = []
    cum_patients = last_patients
    for d_offset in range(1, horizon + 1):
        target_date = last_date + timedelta(days=d_offset)
        dow = target_date.weekday()
        is_hol = _is_holiday_or_weekend(target_date)
        is_bridge = not is_hol and _is_bridge_holiday(target_date)

        # 日タイプ判定
        if is_hol:
            day_type = "休日"
        elif is_bridge:
            day_type = "連休谷間"
        else:
            day_type = "平日"

        # 予測値の決定
        if is_hol or is_bridge:
            # 休日・連休谷間 → 日曜パターンを適用
            if sunday_stats:
                pred_adm = sunday_stats["adm_mean"]
                pred_dis = sunday_stats["dis_mean"]
                std_adm = sunday_stats["adm_std"]
                std_dis = sunday_stats["dis_std"]
            elif use_dow:
                pred_adm = dow_stats[dow]["adm_mean"]
                pred_dis = dow_stats[dow]["dis_mean"]
                std_adm = dow_stats[dow]["adm_std"]
                std_dis = dow_stats[dow]["dis_std"]
            else:
                pred_adm = global_stats["adm_mean"]
                pred_dis = global_stats["dis_mean"]
                std_adm = global_stats["adm_std"]
                std_dis = global_stats["dis_std"]
        elif use_dow:
            pred_adm = dow_stats[dow]["adm_mean"]
            pred_dis = dow_stats[dow]["dis_mean"]
            std_adm = dow_stats[dow]["adm_std"]
            std_dis = dow_stats[dow]["dis_std"]
        else:
            pred_adm = global_stats["adm_mean"]
            pred_dis = global_stats["dis_mean"]
            std_adm = global_stats["adm_std"]
            std_dis = global_stats["dis_std"]

        # 患者数の累積予測
        pred_net = pred_adm - pred_dis
        cum_patients = max(0, min(num_beds, cum_patients + pred_net))
        pred_occ = cum_patients / num_beds

        # 信頼度スコア（0-100）
        # データ量と曜日別サンプル数に基づく
        if use_dow:
            _ns = dow_stats[dow]["n_samples"] if not (is_hol or is_bridge) else (sunday_stats["n_samples"] if sunday_stats else 0)
        else:
            _ns = n_days
        confidence = min(100, int(20 * np.log1p(_ns) + 10 * np.log1p(n_days / 7)))

        rows.append({
            "date": target_date,
            "weekday": dow,
            "day_type": day_type,
            "pred_admissions": round(max(0, pred_adm), 1),
            "pred_discharges": round(max(0, pred_dis), 1),
            "pred_net": round(pred_net, 1),
            "pred_patients": round(cum_patients),
            "pred_occupancy": round(pred_occ, 4),
            "std_admissions": round(std_adm, 1) if not np.isnan(std_adm) else 0,
            "std_discharges": round(std_dis, 1) if not np.isnan(std_dis) else 0,
            "confidence": confidence,
        })

    return pd.DataFrame(rows)


def _get_prediction_explanation(df_history: pd.DataFrame) -> tuple:
    """予測ロジックの解説文と信頼度を返す。

    Returns:
        (explanation_text: str, overall_confidence: str, data_summary: str)
    """
    n_days = len(df_history)
    n_weeks = n_days / 7.0

    if n_weeks >= 8:
        level = "高"
        level_icon = "🟢"
        method = "曜日別の指数加重平均（直近データに高い重み）"
        detail = f"過去{n_days}日分（約{n_weeks:.0f}週間）のデータを使用。曜日ごとの傾向が安定的に反映されています。"
    elif n_weeks >= 2:
        level = "中"
        level_icon = "🟡"
        method = "曜日別の指数加重平均（直近データに高い重み）"
        detail = f"過去{n_days}日分（約{n_weeks:.0f}週間）のデータを使用。データが増えるほど曜日別の精度が向上します。"
    else:
        level = "低"
        level_icon = "🔴"
        method = "全体平均（データ不足のため曜日別分析は未使用）"
        detail = f"過去{n_days}日分のデータのみ。2週間以上のデータが蓄積されると曜日別予測に切り替わります。"

    holiday_note = "✅ 日本の祝日を自動判定（jpholidayライブラリ使用）" if _JPHOLIDAY_AVAILABLE else "⚠️ 祝日判定ライブラリ未導入（土日のみ判定）"

    return (method, f"{level_icon} 信頼度: **{level}**", detail, holiday_note)


# ---------------------------------------------------------------------------
# A/B/C群 自動計算ロジック（日齢バケットモデル）
# ---------------------------------------------------------------------------
def calculate_abc_groups(prev_abc, new_admissions, discharge_a, discharge_b, discharge_c, prev_buckets=None):
    """
    日齢バケットモデルでA/B/C群を更新する。
    prev_bucketsがない場合は従来の簡易モデルにフォールバック。

    Args:
        prev_abc: 前日のA/B/C群辞書 {"A": int, "B": int, "C": int}
        new_admissions: 新規入院数
        discharge_a: A群退院数
        discharge_b: B群退院数
        discharge_c: C群退院数
        prev_buckets: 前日の日齢バケット辞書（Noneの場合は簡易モデル）

    Returns:
        (abc_dict, new_buckets): A/B/C群辞書と新しいバケット（簡易モデル時はNone）
    """
    if prev_buckets is not None and _DATA_MANAGER_AVAILABLE:
        new_buckets = advance_day_buckets(prev_buckets, new_admissions, discharge_a, discharge_b, discharge_c)
        a, b, c = buckets_to_abc(new_buckets)
        return {"A": a, "B": b, "C": c}, new_buckets
    else:
        # 従来の簡易モデル（フォールバック）
        prev_a = prev_abc.get("A", 0)
        prev_b = prev_abc.get("B", 0)
        prev_c = prev_abc.get("C", 0)

        a_to_b = int(prev_a / 5)
        b_to_c = int(prev_b / 9)

        new_a = prev_a - a_to_b + new_admissions - discharge_a
        new_b = prev_b + a_to_b - b_to_c - discharge_b
        new_c = prev_c + b_to_c - discharge_c

        new_a = max(0, int(new_a))
        new_b = max(0, int(new_b))
        new_c = max(0, int(new_c))

        return {"A": new_a, "B": new_b, "C": new_c}, None

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

if not _CORE_AVAILABLE:
    st.error(f"⚠️ コアモジュールのインポートに失敗しました\n\n{_CORE_ERROR}")
    st.info("Python のバージョン: " + sys.version)
    st.info("sys.path: " + str(sys.path))
    st.stop()

if not _DATA_MANAGER_AVAILABLE:
    _dm_error_msg = _DATA_MANAGER_ERROR if "_DATA_MANAGER_ERROR" in dir() else "bed_data_manager モジュールが見つかりません"
    st.sidebar.warning(f"⚠️ 日次データ管理モジュールのインポートに失敗しました\n\n{_dm_error_msg}")

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
    "daily_revenue": "日次診療報酬",
    "daily_cost": "日次コスト",
    "daily_profit": "日次運営貢献額",
    "empty_beds": "空床数",
    "excess_demand": "超過需要",
    "opportunity_loss": "未活用病床コスト",
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
    # 累積運営貢献額を追加
    if "日次運営貢献額" in df.columns:
        df["累積運営貢献額"] = df["日次運営貢献額"].cumsum()
    # 運営改善アラート列を生成
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
        if "日次運営貢献額" in df.columns and row["日次運営貢献額"] < 0:
            day_flags.append("日次赤字")
        if not day_flags:
            day_flags.append("正常運用")
        flags.append(", ".join(day_flags))
    df["運営改善アラート"] = flags
    return df


# ---------------------------------------------------------------------------
# ヘルパー: CLI の summary を Streamlit 用日本語キーに変換
# ---------------------------------------------------------------------------
def _convert_summary(cli_summary: dict, params: dict) -> dict:
    """CLI版summarize_resultsの戻り値をStreamlit表示用の日本語キー辞書に変換。"""
    days_in_month = params["days_in_month"]
    days_in_range = cli_summary["days_in_target_range"]
    return {
        "月次診療報酬": cli_summary["total_revenue"],
        "月次コスト": cli_summary["total_cost"],
        "月次運営貢献額": cli_summary["total_profit"],
        "平均稼働率": round(cli_summary["avg_occupancy"] * 100, 1),
        "月間入院数": 0,  # 後で計算
        "月間退院数": 0,  # 後で計算
        "目標レンジ内日数": days_in_range,
        "目標レンジ内率": round(days_in_range / max(days_in_month, 1) * 100, 1),
        "A群平均構成比": round(cli_summary["avg_phase_a_ratio"] * 100, 1) if pd.notna(cli_summary.get("avg_phase_a_ratio")) else 0.0,
        "B群平均構成比": round(cli_summary["avg_phase_b_ratio"] * 100, 1) if pd.notna(cli_summary.get("avg_phase_b_ratio")) else 0.0,
        "C群平均構成比": round(cli_summary["avg_phase_c_ratio"] * 100, 1) if pd.notna(cli_summary.get("avg_phase_c_ratio")) else 0.0,
        "平均在院日数": cli_summary["avg_length_of_stay"],
        "フラグ集計": {},  # 後で計算
    }


def _enrich_summary(summary: dict, df_ja: pd.DataFrame) -> dict:
    """日本語DataFrameから入退院数・フラグ集計を追加する。"""
    summary["月間入院数"] = int(df_ja["新規入院"].sum())
    summary["月間退院数"] = int(df_ja["退院"].sum())
    # フラグ集計
    flag_counts: dict[str, int] = {}
    for flags_str in df_ja["運営改善アラート"]:
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
# サイドバー: 基盤指標（稼働率1%の価値）
# ---------------------------------------------------------------------------
_UNIT_PRICE_PER_DAY = 30500  # 1日あたり入院単価
_TOTAL_BEDS_METRIC = 94
_ANNUAL_VALUE_PER_1PCT = _TOTAL_BEDS_METRIC * 0.01 * 365 * _UNIT_PRICE_PER_DAY  # ≈1,047万円
_OPERATING_PROFIT = 35500000  # 営業利益3,550万円

# Get current occupancy from latest data if available
_current_occ = None
if isinstance(st.session_state.get("daily_data"), pd.DataFrame) and len(st.session_state.daily_data) > 0:
    _dd_for_occ = st.session_state.daily_data
    if "ward" in _dd_for_occ.columns:
        # 病棟別データの場合、同一日付のtotal_patientsを合算
        _latest_date = _dd_for_occ["date"].max()
        _latest_total_patients = _dd_for_occ[_dd_for_occ["date"] == _latest_date]["total_patients"].sum()
    else:
        _latest_total_patients = _dd_for_occ.sort_values("date").iloc[-1].get("total_patients", 0)
    _current_occ = _latest_total_patients / _TOTAL_BEDS_METRIC * 100

st.sidebar.markdown("---")
if _current_occ is not None:
    _gap_to_target = max(0, 90 - _current_occ)
    _potential = _gap_to_target * _ANNUAL_VALUE_PER_1PCT / 100
    st.sidebar.metric(
        label="稼働率1% の価値",
        value=f"年間 {_ANNUAL_VALUE_PER_1PCT/10000:.0f}万円",
        delta=f"営業利益の {_ANNUAL_VALUE_PER_1PCT/_OPERATING_PROFIT*100:.0f}%相当",
    )
    st.sidebar.caption(f"現在の稼働率: {_current_occ:.1f}% | 目標90%まであと{_gap_to_target:.1f}%")
else:
    st.sidebar.metric(
        label="稼働率1% の価値",
        value=f"年間 {_ANNUAL_VALUE_PER_1PCT/10000:.0f}万円",
        delta=f"営業利益の {_ANNUAL_VALUE_PER_1PCT/_OPERATING_PROFIT*100:.0f}%相当",
    )
st.sidebar.markdown("---")

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
st.sidebar.markdown("**病棟構成**")
st.sidebar.markdown("5F: 47床 / 6F: 47床 / 合計: 94床")
total_beds = TOTAL_BEDS if _DATA_MANAGER_AVAILABLE else 94

# 病棟セレクター（両モードで有効）
_ward_options = ["全体 (94床)", "5F (47床)", "6F (47床)"]
_selected_ward_label = st.sidebar.radio("表示病棟", _ward_options, index=0, horizontal=True)
_selected_ward_key = {"全体 (94床)": "全体", "5F (47床)": "5F", "6F (47床)": "6F"}[_selected_ward_label]

# _view_beds のデフォルト値（後で病棟選択に応じて上書きされる）
_view_beds = total_beds

target_lower = st.sidebar.slider("目標稼働率下限", 0.80, 1.00, 0.90, step=0.01, format="%.2f")
target_upper = st.sidebar.slider("目標稼働率上限", 0.80, 1.00, 0.95, step=0.01, format="%.2f")

# 目標上限 < 下限のバリデーション
if target_upper < target_lower:
    st.sidebar.warning("目標稼働率上限が下限より低く設定されています。値を確認してください。")

# シミュレーションモード専用のパラメータ
if not _is_actual_data_mode:
    days_in_month = st.sidebar.number_input("月の日数", min_value=7, max_value=31, value=30)
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

# --- 患者フェーズ別パラメータ（運営貢献額ベース：変動費のみ計上） ---
with st.sidebar.expander("患者フェーズ別パラメータ"):
    st.markdown("**A群（急性期: 〜5日目）**")
    phase_a_rev = st.number_input("A群 日次診療報酬（円）", value=36000, step=1000, key="a_rev")
    phase_a_cost = st.number_input("A群 日次変動費（円）", value=12000, step=1000, key="a_cost")
    st.markdown("**B群（回復期: 6〜14日目）**")
    phase_b_rev = st.number_input("B群 日次診療報酬（円）", value=36000, step=1000, key="b_rev")
    phase_b_cost = st.number_input("B群 日次変動費（円）", value=6000, step=1000, key="b_cost")
    st.markdown("**C群（退院準備期: 15日目〜）**")
    phase_c_rev = st.number_input("C群 日次診療報酬（円）", value=33400, step=1000, key="c_rev")
    phase_c_cost = st.number_input("C群 日次変動費（円）", value=4500, step=1000, key="c_cost")

# --- 追加パラメータ ---
with st.sidebar.expander("追加パラメータ"):
    day1_bonus = st.number_input("初日加算（円）", value=0, step=1000)
    within_14_bonus = st.number_input("14日以内加算（円/日）", value=0, step=500)
    rehab_fee = st.number_input("リハビリ出来高（円/日）", value=0, step=500)
    opportunity_cost = st.number_input("未活用病床コスト（円/空床/日）", value=25000, step=1000)
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
    run_button = st.sidebar.button("シミュレーション実行", type="primary", width="stretch")
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
if "sim_ward_dfs" not in st.session_state:
    st.session_state.sim_ward_dfs = {}
if "sim_ward_raw_dfs" not in st.session_state:
    st.session_state.sim_ward_raw_dfs = {}
if "sim_ward_summaries" not in st.session_state:
    st.session_state.sim_ward_summaries = {}
if "sim_summary" not in st.session_state:
    st.session_state.sim_summary = None
if "comparison" not in st.session_state:
    st.session_state.comparison = None
if "sim_df_raw" not in st.session_state:
    st.session_state.sim_df_raw = None
if "sim_params" not in st.session_state:
    st.session_state.sim_params = None

# 日次データ管理用セッション状態（SQLiteから自動復元）
if "daily_data" not in st.session_state:
    _loaded_from_db = False
    # 1) SQLiteから復元を試みる
    if _DB_AVAILABLE:
        _db_df = load_daily_records()
        if _db_df is not None and len(_db_df) > 0:
            st.session_state.daily_data = _db_df
            _loaded_from_db = True
    # 2) DBが空の場合、CSVサンプルデータから自動読み込み（Streamlit Cloud対応）
    if not _loaded_from_db:
        _csv_fallback_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "sample_actual_data_ward_202603.csv")
        if os.path.exists(_csv_fallback_path):
            try:
                _csv_df = pd.read_csv(_csv_fallback_path)
                _csv_df["date"] = pd.to_datetime(_csv_df["date"])
                if len(_csv_df) > 0:
                    st.session_state.daily_data = _csv_df
                    _loaded_from_db = True
                    # DBにも保存して次回以降の起動を高速化
                    if _DB_AVAILABLE:
                        try:
                            save_daily_records(_csv_df)
                        except Exception:
                            pass
            except Exception:
                pass
    # 3) どちらも失敗した場合は空のDataFrame
    if not _loaded_from_db:
        if _DATA_MANAGER_AVAILABLE:
            st.session_state.daily_data = dm_create_empty_dataframe()
        else:
            st.session_state.daily_data = pd.DataFrame()

# 入退院詳細データ（医師別）
if "admission_details" not in st.session_state:
    if _DETAIL_DATA_AVAILABLE:
        st.session_state.admission_details = load_details()
    else:
        st.session_state.admission_details = pd.DataFrame()

# A/B/C群 自動計算用の状態（SQLiteから自動復元）
if "abc_state" not in st.session_state:
    _db_abc = None
    if _DB_AVAILABLE:
        _db_abc = load_abc_state()
    if _db_abc is not None:
        st.session_state.abc_state = _db_abc
    else:
        st.session_state.abc_state = {"A": 0, "B": 0, "C": 0}

# 日齢バケット（SQLiteから自動復元）
if "day_buckets" not in st.session_state:
    _db_buckets = None
    if _DB_AVAILABLE:
        _db_buckets = load_day_buckets()
    if _db_buckets is not None:
        st.session_state.day_buckets = _db_buckets
    else:
        st.session_state.day_buckets = None

# 既存データからABC状態を復元
if "abc_state_initialized" not in st.session_state:
    if _DATA_MANAGER_AVAILABLE and isinstance(st.session_state.daily_data, pd.DataFrame) and len(st.session_state.daily_data) > 0:
        _last_record = st.session_state.daily_data.sort_values("date").iloc[-1]
        _restore_a = int(_last_record.get("phase_a_count", 0) or 0)
        _restore_b = int(_last_record.get("phase_b_count", 0) or 0)
        _restore_c = int(_last_record.get("phase_c_count", 0) or 0)
        st.session_state.abc_state = {"A": _restore_a, "B": _restore_b, "C": _restore_c}
    st.session_state.abc_state_initialized = True

def _auto_save_to_db():
    """現在のセッション状態をSQLiteに自動保存"""
    if not _DB_AVAILABLE:
        return
    try:
        if isinstance(st.session_state.get("daily_data"), pd.DataFrame) and len(st.session_state.daily_data) > 0:
            save_daily_records(st.session_state.daily_data)
        if st.session_state.get("abc_state"):
            save_abc_state(st.session_state.abc_state)
        if st.session_state.get("day_buckets"):
            save_day_buckets(st.session_state.day_buckets)
    except Exception as e:
        pass  # 保存失敗してもアプリは継続

if "demo_data" not in st.session_state:
    # 教育用デモCSVを自動ロード
    _demo_csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "sample_actual_data_ward_202603.csv")
    if os.path.exists(_demo_csv_path):
        try:
            _auto_demo = pd.read_csv(_demo_csv_path)
            _auto_demo["date"] = pd.to_datetime(_auto_demo["date"])
            # 必要カラムの補完
            if "num_beds" not in _auto_demo.columns:
                _auto_demo["num_beds"] = _auto_demo["ward"].map(lambda w: get_ward_beds(w))
            if "occupancy_rate" not in _auto_demo.columns:
                _auto_demo["occupancy_rate"] = (_auto_demo["total_patients"] / _auto_demo["num_beds"] * 100).round(1)
            st.session_state.demo_data = _auto_demo.sort_values(["date", "ward"]).reset_index(drop=True)
        except Exception:
            st.session_state.demo_data = pd.DataFrame()
    else:
        st.session_state.demo_data = pd.DataFrame()

if "data_mode" not in st.session_state:
    st.session_state.data_mode = "📊 実データ入力モード"

# ---------------------------------------------------------------------------
# シミュレーションモードのプリロード: 教育用実データを初期表示
# ---------------------------------------------------------------------------
if "sim_preloaded" not in st.session_state and not _is_actual_data_mode and _DATA_MANAGER_AVAILABLE:
    _preload_csv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "sample_actual_data_ward_202603.csv")
    if os.path.exists(_preload_csv):
        try:
            _pre_df = pd.read_csv(_preload_csv)
            _pre_df["date"] = pd.to_datetime(_pre_df["date"])

            # 実データから全体データの作成（実データモードと同じロジック）
            if "ward" in _pre_df.columns and _pre_df["ward"].isin(["5F", "6F"]).any():
                _pre_data_all = aggregate_wards(_pre_df)
            else:
                _pre_data_all = _pre_df

            # デフォルトパラメータで変換用パラメータ辞書を構築
            _pre_params_dict = {
                "target_occupancy_lower": 0.90,
                "target_occupancy_upper": 0.95,
                "days_in_month": 17,
                "monthly_admissions": 150,
                "avg_length_of_stay": 19,
                "admission_variation_coeff": 1.0,
                "occupancy_variation_coeff": 0.1,
                "initial_occupancy": 0.85,
                "strategy_params": "balanced",
                "random_seed": 42,
            }
            _pre_params = _build_cli_params(_pre_params_dict)

            # 全体データの変換
            _pre_raw_df = convert_actual_to_display(_pre_data_all, _pre_params)
            _pre_display_df = _rename_df(_pre_raw_df)

            # 全体サマリーの生成（実データモードと同じロジック）
            _pre_summary = {
                "月次診療報酬": int(_pre_raw_df["daily_revenue"].sum()),
                "月次コスト": int(_pre_raw_df["daily_cost"].sum()),
                "月次運営貢献額": int(_pre_raw_df["daily_profit"].sum()),
                "平均稼働率": round(float(_pre_raw_df["occupancy_rate"].mean()) * 100, 1),
                "月間入院数": int(_pre_raw_df["new_admissions"].sum()),
                "月間退院数": int(_pre_raw_df["discharges"].sum()),
                "目標レンジ内日数": int(
                    ((_pre_raw_df["occupancy_rate"] >= 0.90)
                     & (_pre_raw_df["occupancy_rate"] <= 0.95)).sum()
                ),
                "目標レンジ内率": round(
                    float(
                        ((_pre_raw_df["occupancy_rate"] >= 0.90)
                         & (_pre_raw_df["occupancy_rate"] <= 0.95)).mean()
                    ) * 100, 1
                ),
                "A群平均構成比": round(float(_pre_raw_df["phase_a_ratio"].mean()) * 100, 1) if pd.notna(_pre_raw_df["phase_a_ratio"].mean()) else 0.0,
                "B群平均構成比": round(float(_pre_raw_df["phase_b_ratio"].mean()) * 100, 1) if pd.notna(_pre_raw_df["phase_b_ratio"].mean()) else 0.0,
                "C群平均構成比": round(float(_pre_raw_df["phase_c_ratio"].mean()) * 100, 1) if pd.notna(_pre_raw_df["phase_c_ratio"].mean()) else 0.0,
                "平均在院日数": 0,
                "フラグ集計": {},
            }
            # 平均在院日数計算
            _total_patient_days = float(_pre_raw_df["total_patients"].sum())
            _total_new_admissions = float(_pre_raw_df["new_admissions"].sum())
            _total_discharges = float(_pre_raw_df["discharges"].sum())
            _los_denominator = (_total_new_admissions + _total_discharges) / 2
            if _los_denominator > 0 and _total_patient_days > 0:
                _pre_summary["平均在院日数"] = round(_total_patient_days / _los_denominator, 1)
            _pre_summary = _enrich_summary(_pre_summary, _pre_display_df)

            # 病棟別データの変換
            _pre_ward_dfs = {}
            _pre_ward_raw_dfs = {}
            _pre_ward_summaries = {}

            for _w in ["5F", "6F"]:
                _w_data = _pre_df[_pre_df["ward"] == _w].copy()
                if len(_w_data) > 0:
                    _w_params = _pre_params.copy()
                    _w_params["num_beds"] = get_ward_beds(_w)
                    _w_raw = convert_actual_to_display(_w_data, _w_params)
                    _w_disp = _rename_df(_w_raw)
                    _w_summary = {
                        "月次診療報酬": int(_w_raw["daily_revenue"].sum()),
                        "月次コスト": int(_w_raw["daily_cost"].sum()),
                        "月次運営貢献額": int(_w_raw["daily_profit"].sum()),
                        "平均稼働率": round(float(_w_raw["occupancy_rate"].mean()) * 100, 1),
                        "月間入院数": int(_w_raw["new_admissions"].sum()),
                        "月間退院数": int(_w_raw["discharges"].sum()),
                        "目標レンジ内日数": int(
                            ((_w_raw["occupancy_rate"] >= 0.90)
                             & (_w_raw["occupancy_rate"] <= 0.95)).sum()
                        ),
                        "目標レンジ内率": round(
                            float(
                                ((_w_raw["occupancy_rate"] >= 0.90)
                                 & (_w_raw["occupancy_rate"] <= 0.95)).mean()
                            ) * 100, 1
                        ),
                        "A群平均構成比": round(float(_w_raw["phase_a_ratio"].mean()) * 100, 1) if pd.notna(_w_raw["phase_a_ratio"].mean()) else 0.0,
                        "B群平均構成比": round(float(_w_raw["phase_b_ratio"].mean()) * 100, 1) if pd.notna(_w_raw["phase_b_ratio"].mean()) else 0.0,
                        "C群平均構成比": round(float(_w_raw["phase_c_ratio"].mean()) * 100, 1) if pd.notna(_w_raw["phase_c_ratio"].mean()) else 0.0,
                        "平均在院日数": 0,
                        "フラグ集計": {},
                    }
                    # 病棟別平均在院日数計算
                    _w_total_patient_days = float(_w_raw["total_patients"].sum())
                    _w_total_new_admissions = float(_w_raw["new_admissions"].sum())
                    _w_total_discharges = float(_w_raw["discharges"].sum())
                    _w_los_denominator = (_w_total_new_admissions + _w_total_discharges) / 2
                    if _w_los_denominator > 0 and _w_total_patient_days > 0:
                        _w_summary["平均在院日数"] = round(_w_total_patient_days / _w_los_denominator, 1)
                    _w_summary = _enrich_summary(_w_summary, _w_disp)

                    _pre_ward_dfs[_w] = _w_disp
                    _pre_ward_raw_dfs[_w] = _w_raw
                    _pre_ward_summaries[_w] = _w_summary

            # session_stateに格納
            st.session_state.sim_ward_dfs = _pre_ward_dfs
            st.session_state.sim_ward_raw_dfs = _pre_ward_raw_dfs
            st.session_state.sim_ward_summaries = _pre_ward_summaries
            st.session_state.sim_df = _pre_display_df
            st.session_state.sim_df_raw = _pre_raw_df
            st.session_state.sim_summary = _pre_summary
            st.session_state.sim_params = _pre_params
            st.session_state.sim_preloaded = True
        except Exception:
            pass

# ---------------------------------------------------------------------------
# シミュレーション実行
# ---------------------------------------------------------------------------
if run_button:
    with st.spinner("シミュレーション実行中..."):
        try:
            strategy_en = STRATEGY_MAP[strategy]
            params = _build_cli_params(params_dict)

            # --- 病棟別シミュレーション（各47床）---
            # 5F: 外科・整形系（短めの在院日数、入院数やや少なめ）
            # 6F: 内科・ペイン系（長めの在院日数、入院数多め）
            # 教育シナリオ（現実的な稼働率80%以上を維持、月平均<90%で警告発動）:
            # 5F: 初期91%→avg~85% = レンジ内から急低下（残り13日で97%必要＝ハードシナリオ）
            #   adm=35, los=14 → 退院抑制があっても入院不足で稼働率低下
            # 6F: 初期82%→avg~87% = レンジ外から回復中（残り13日で94%必要）
            #   adm=60, los=18 → 入院が退院を上回り回復トレンド
            # 10シード検証済み: 全シナリオmin>=80.8%, 5F下降7/10, 6F上昇8/10
            _ward_param_adj = {
                "5F": {
                    "avg_length_of_stay": max(10, params.get("avg_length_of_stay", 19) - 4),
                    "monthly_admissions": 35,
                    "admission_variation_coeff": 1.0,
                    "initial_occupancy": 0.91,
                    "random_seed": (params.get("random_seed") or 42) + 1,
                },
                "6F": {
                    "avg_length_of_stay": min(21, params.get("avg_length_of_stay", 19)),
                    "monthly_admissions": 60,
                    "admission_variation_coeff": 1.0,
                    "initial_occupancy": 0.82,
                    "random_seed": (params.get("random_seed") or 42) + 2,
                },
            }
            _sim_ward_dfs = {}
            _sim_ward_raw_dfs = {}
            _sim_ward_summaries = {}
            for _sw in ["5F", "6F"]:
                _sw_params = params.copy()
                _sw_params["num_beds"] = get_ward_beds(_sw)
                _sw_params.update(_ward_param_adj[_sw])
                _sw_df = simulate_bed_control(_sw_params, strategy_en)
                _sw_summary = summarize_results(_sw_df)
                _sw_df_ja = _rename_df(_sw_df)
                _sw_summary_ja = _convert_summary(_sw_summary, _sw_params)
                _sw_summary_ja = _enrich_summary(_sw_summary_ja, _sw_df_ja)
                _sim_ward_dfs[_sw] = _sw_df_ja
                _sim_ward_raw_dfs[_sw] = _sw_df
                _sim_ward_summaries[_sw] = _sw_summary_ja
            st.session_state.sim_ward_dfs = _sim_ward_dfs
            st.session_state.sim_ward_raw_dfs = _sim_ward_raw_dfs
            st.session_state.sim_ward_summaries = _sim_ward_summaries

            # --- 全体 = 5F + 6F を日次で合算 ---
            _raw_5f = _sim_ward_raw_dfs["5F"].copy()
            _raw_6f = _sim_ward_raw_dfs["6F"].copy()
            _total_beds = get_ward_beds("5F") + get_ward_beds("6F")

            # 加算系カラム（日次で合計）
            _sum_cols = ["total_patients", "new_admissions", "discharges",
                         "phase_a_count", "phase_b_count", "phase_c_count",
                         "daily_revenue", "daily_cost", "daily_profit",
                         "empty_beds", "excess_demand", "opportunity_loss",
                         "recommended_discharges", "allowable_holds"]

            df = _raw_5f[["date", "day"]].copy()
            for _col in _sum_cols:
                if _col in _raw_5f.columns and _col in _raw_6f.columns:
                    df[_col] = _raw_5f[_col].values + _raw_6f[_col].values

            # 稼働率は再計算（合計患者数 / 合計病床数）
            df["occupancy_rate"] = (df["total_patients"] / _total_beds).round(4)

            # フェーズ比率は再計算
            _total_phase = df["phase_a_count"] + df["phase_b_count"] + df["phase_c_count"]
            _total_phase_safe = _total_phase.replace(0, 1)
            df["phase_a_ratio"] = (df["phase_a_count"] / _total_phase_safe).round(4)
            df["phase_b_ratio"] = (df["phase_b_count"] / _total_phase_safe).round(4)
            df["phase_c_ratio"] = (df["phase_c_count"] / _total_phase_safe).round(4)

            # フラグは合算後の値で再判定
            df["flag_low_occupancy"] = df["occupancy_rate"] < params.get("target_occupancy_lower", 0.90)
            df["flag_high_occupancy"] = df["occupancy_rate"] > params.get("target_occupancy_upper", 0.95)
            df["flag_excess_a"] = df["phase_a_ratio"] > 0.25
            df["flag_shortage_b"] = df["phase_b_ratio"] < 0.30
            df["flag_stagnant_c"] = df["phase_c_ratio"] > 0.40

            cli_summary = summarize_results(df)
            df_ja = _rename_df(df)
            summary_ja = _convert_summary(cli_summary, params)
            summary_ja = _enrich_summary(summary_ja, df_ja)

            st.session_state.sim_df = df_ja
            st.session_state.sim_summary = summary_ja
            st.session_state.sim_df_raw = df
            st.session_state.sim_params = params

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
        # 病棟別データがある場合は合算して全体データを作成
        if "ward" in _source_data.columns and _source_data["ward"].isin(["5F", "6F"]).any():
            _source_data_all = aggregate_wards(_source_data)
        else:
            _source_data_all = _source_data

        # パラメータ辞書を構築（CLI版互換 + 実データ変換用）
        # _build_cli_params を使って完全なパラメータセットを取得
        _actual_params = _build_cli_params(params_dict)
        _actual_raw_df = convert_actual_to_display(_source_data_all, _actual_params)
        _actual_display_df = _rename_df(_actual_raw_df)

        # サマリー生成（実データ用）
        _actual_summary = {
            "月次診療報酬": int(_actual_raw_df["daily_revenue"].sum()),
            "月次コスト": int(_actual_raw_df["daily_cost"].sum()),
            "月次運営貢献額": int(_actual_raw_df["daily_profit"].sum()),
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
            "A群平均構成比": round(float(_actual_raw_df["phase_a_ratio"].mean()) * 100, 1) if pd.notna(_actual_raw_df["phase_a_ratio"].mean()) else 0.0,
            "B群平均構成比": round(float(_actual_raw_df["phase_b_ratio"].mean()) * 100, 1) if pd.notna(_actual_raw_df["phase_b_ratio"].mean()) else 0.0,
            "C群平均構成比": round(float(_actual_raw_df["phase_c_ratio"].mean()) * 100, 1) if pd.notna(_actual_raw_df["phase_c_ratio"].mean()) else 0.0,
            "平均在院日数": 0,  # 厚労省公式で計算
            "フラグ集計": {},
        }
        # 平均在院日数（厚生労働省 病院報告の定義に準拠）
        # 平均在院日数 = 在院患者延日数 ÷ ((新入院患者数 + 退院患者数) ÷ 2)
        _total_patient_days = float(_actual_raw_df["total_patients"].sum())
        _total_new_admissions = float(_actual_raw_df["new_admissions"].sum())
        _total_discharges_actual = float(_actual_raw_df["discharges"].sum())
        _los_denominator = (_total_new_admissions + _total_discharges_actual) / 2
        if _los_denominator > 0 and _total_patient_days > 0:
            _actual_summary["平均在院日数"] = round(_total_patient_days / _los_denominator, 1)

        # フラグ集計
        _actual_summary = _enrich_summary(_actual_summary, _actual_display_df)

        # セッション状態にも保存（意思決定ダッシュボード等で使用）
        st.session_state.actual_df = _actual_display_df
        st.session_state.actual_summary = _actual_summary
        st.session_state.actual_df_raw = _actual_raw_df
        st.session_state.actual_params = _actual_params
        _actual_data_available = True

        # 病棟別データの準備（3列表示用）
        _ward_data_available = ("ward" in _source_data.columns
                                and _source_data["ward"].isin(["5F", "6F"]).any())
        if _ward_data_available:
            _ward_raw_dfs = {}
            _ward_display_dfs = {}
            for _w in ["5F", "6F"]:
                _w_data = _source_data[_source_data["ward"] == _w].copy()
                if len(_w_data) > 0:
                    _w_params = _actual_params.copy()
                    _w_params["num_beds"] = get_ward_beds(_w)
                    _ward_raw_dfs[_w] = convert_actual_to_display(_w_data, _w_params)
                    _ward_display_dfs[_w] = _rename_df(_ward_raw_dfs[_w])
        else:
            _ward_data_available = False
            _ward_raw_dfs = {}
            _ward_display_dfs = {}

        # --- Ward selector データバインディング ---
        if _selected_ward_key in ("5F", "6F") and _ward_data_available and _selected_ward_key in _ward_raw_dfs:
            _view_beds = get_ward_beds(_selected_ward_key)
            _active_raw_df = _ward_raw_dfs[_selected_ward_key]
            _active_display_df = _ward_display_dfs[_selected_ward_key]
            # Override the main df and raw_df used by all tabs
            st.session_state.actual_df = _active_display_df
            st.session_state.actual_df_raw = _active_raw_df
            # Also override _actual_raw_df and _actual_display_df
            _actual_raw_df = _active_raw_df
            _actual_display_df = _active_display_df
            # Update analysis params
            _actual_params = _build_cli_params(params_dict)
            _actual_params["num_beds"] = _view_beds
            st.session_state.actual_params = _actual_params
            # Recalculate summary for selected ward
            _actual_summary = {
                "月次診療報酬": int(_actual_raw_df["daily_revenue"].sum()),
                "月次コスト": int(_actual_raw_df["daily_cost"].sum()),
                "月次運営貢献額": int(_actual_raw_df["daily_profit"].sum()),
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
                ) if len(_actual_raw_df) > 0 else 0.0,
                "A群平均構成比": round(float(_actual_raw_df["phase_a_ratio"].mean()) * 100, 1) if pd.notna(_actual_raw_df["phase_a_ratio"].mean()) else 0.0,
                "B群平均構成比": round(float(_actual_raw_df["phase_b_ratio"].mean()) * 100, 1) if pd.notna(_actual_raw_df["phase_b_ratio"].mean()) else 0.0,
                "C群平均構成比": round(float(_actual_raw_df["phase_c_ratio"].mean()) * 100, 1) if pd.notna(_actual_raw_df["phase_c_ratio"].mean()) else 0.0,
                "平均在院日数": 0,
                "フラグ集計": {},
            }
            # Calculate avg LOS for ward
            _w_total_patient_days = float(_actual_raw_df["total_patients"].sum())
            _w_total_new_admissions = float(_actual_raw_df["new_admissions"].sum())
            _w_total_discharges = float(_actual_raw_df["discharges"].sum())
            _w_los_denominator = (_w_total_new_admissions + _w_total_discharges) / 2
            if _w_los_denominator > 0 and _w_total_patient_days > 0:
                _actual_summary["平均在院日数"] = round(_w_total_patient_days / _w_los_denominator, 1)
            _actual_summary = _enrich_summary(_actual_summary, _actual_display_df)
            st.session_state.actual_summary = _actual_summary
        else:
            _view_beds = total_beds  # 94
            # 「全体」選択時: 全体の_actual_raw_dfを_active_raw_dfとして設定
            _active_raw_df = _actual_raw_df
            _active_display_df = _actual_display_df

# ---------------------------------------------------------------------------
# 結果未実行の場合の案内
# ---------------------------------------------------------------------------
_simulation_available = st.session_state.sim_df is not None

# シミュレーションモード時のブリーフィング用 _active_raw_df 事前設定
if _simulation_available and not _actual_data_available:
    if _selected_ward_key in ("5F", "6F") and st.session_state.get("sim_ward_raw_dfs", {}).get(_selected_ward_key) is not None:
        _active_raw_df = st.session_state.sim_ward_raw_dfs[_selected_ward_key]
        _view_beds = get_ward_beds(_selected_ward_key) if _DATA_MANAGER_AVAILABLE else 47
    elif st.session_state.sim_df_raw is not None:
        _active_raw_df = st.session_state.sim_df_raw

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


def _render_comparison_strip(ward_key, ward_raw_dfs, ward_display_dfs, view_beds_fn):
    """選択中の病棟以外のKPIを小さく表示する比較ストリップ"""
    if not ward_raw_dfs:
        return
    other_wards = [w for w in ["5F", "6F"] if w != ward_key]
    if ward_key == "全体":
        other_wards = ["5F", "6F"]

    if not other_wards:
        return

    # 他病棟の参考値を常に展開表示（色分け付き）
    st.markdown("#### 📊 他病棟の参考値")
    cols = st.columns(len(other_wards))
    for i, w in enumerate(other_wards):
        if w in ward_raw_dfs and len(ward_raw_dfs[w]) > 0:
            w_df = ward_raw_dfs[w]
            w_beds = view_beds_fn(w)
            last_row = w_df.iloc[-1]
            occ = last_row.get("occupancy_rate", 0) * 100
            patients = int(last_row.get("total_patients", 0))
            avg_occ = float(w_df["occupancy_rate"].mean()) * 100
            empty_beds = w_beds - patients
            # 稼働率による色分け
            if occ < 90:
                _bg = "#FDEDEC"; _border = "#E74C3C"; _icon = "🔴"
            elif occ <= 95:
                _bg = "#EAFAF1"; _border = "#27AE60"; _icon = "🟢"
            else:
                _bg = "#FEF9E7"; _border = "#F39C12"; _icon = "🟡"
            with cols[i]:
                st.markdown(f"""
<div style="background:{_bg}; padding:12px; border-radius:8px; border-left:4px solid {_border}; margin-bottom:8px;">
<h4 style="margin:0 0 4px 0;">{_icon} {w}（{w_beds}床）</h4>
<p style="margin:2px 0; font-size:1.1em;"><b>直近稼働率: {occ:.1f}%</b></p>
<p style="margin:2px 0;">月平均: {avg_occ:.1f}% ｜ 在院: {patients}名 ｜ 空床: {empty_beds}床</p>
</div>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# データ基準の残日数計算ヘルパー
# ---------------------------------------------------------------------------
def _calc_remaining_days(raw_df):
    """データの最終日から月末までの残日数を計算"""
    try:
        _date_col = "date" if "date" in raw_df.columns else "日付"
        _last_date = pd.to_datetime(raw_df[_date_col].iloc[-1])
        _days_in_month = calendar.monthrange(_last_date.year, _last_date.month)[1]
        return max(0, _days_in_month - _last_date.day)
    except Exception:
        return calendar.monthrange(date.today().year, date.today().month)[1] - date.today().day


def _calc_monthly_target(raw_df, target_lower, total_days_in_month, view_beds):
    """
    月平均稼働率の目標達成に必要な残日数の稼働率を計算する。

    Returns:
        dict: {
            "avg_so_far": これまでの平均稼働率(%),
            "days_elapsed": 経過日数,
            "days_remaining": 残日数,
            "total_days": 月の総日数,
            "required_occ": 残日数で必要な平均稼働率(%),
            "projected_monthly_avg": 現在のペースでの月末予測稼働率(%),
            "monthly_target_pct": 月平均目標(%),
            "gap_patients": 目標達成に必要な追加患者数/日,
            "achievable": 達成可能かどうか (True/False),
            "difficulty": "easy" / "moderate" / "hard" / "impossible"
        }
    """
    try:
        _occ_col = "occupancy_rate" if "occupancy_rate" in raw_df.columns else "稼働率"
        _occ_values = raw_df[_occ_col].dropna().values.copy()
        if len(_occ_values) == 0:
            return None

        # スケール統一（0-1 → 0-100）
        if _occ_values.mean() < 1.5:
            _occ_values = _occ_values * 100

        _avg_so_far = float(_occ_values.mean())
        _days_elapsed = len(_occ_values)

        # 月の総日数を決定（データの日付から、またはパラメータから）
        _D = total_days_in_month
        for _dc in ["date", "日付"]:
            if _dc in raw_df.columns:
                try:
                    _last_date = pd.to_datetime(raw_df[_dc].iloc[-1])
                    _D = calendar.monthrange(_last_date.year, _last_date.month)[1]
                    break
                except Exception:
                    pass

        _days_remaining = max(0, _D - _days_elapsed)
        _target_pct = target_lower * 100  # 例: 90.0

        if _days_remaining == 0:
            # 月末 — 実績確定
            return {
                "avg_so_far": _avg_so_far,
                "days_elapsed": _days_elapsed,
                "days_remaining": 0,
                "total_days": _D,
                "required_occ": 0,
                "projected_monthly_avg": _avg_so_far,
                "monthly_target_pct": _target_pct,
                "gap_patients": 0,
                "achievable": _avg_so_far >= _target_pct,
                "difficulty": "done",
            }

        # 必要稼働率 R = (target × D - avg × d) / remaining
        _required_occ = (_target_pct * _D - _avg_so_far * _days_elapsed) / _days_remaining

        # 現在のペースでの月末予測
        _projected_monthly_avg = _avg_so_far  # 現在の平均が続く想定

        # 目標達成に必要な追加患者数/日
        _current_avg_patients = _avg_so_far / 100 * view_beds
        _required_avg_patients = _required_occ / 100 * view_beds
        _gap_patients = max(0, _required_avg_patients - _current_avg_patients)

        # 難易度判定
        if _required_occ > 100:
            _difficulty = "impossible"
        elif _required_occ > 95:
            _difficulty = "hard"
        elif _required_occ > 90:
            _difficulty = "moderate"
        else:
            _difficulty = "easy"

        return {
            "avg_so_far": round(_avg_so_far, 1),
            "days_elapsed": _days_elapsed,
            "days_remaining": _days_remaining,
            "total_days": _D,
            "required_occ": round(_required_occ, 1),
            "projected_monthly_avg": round(_projected_monthly_avg, 1),
            "monthly_target_pct": _target_pct,
            "gap_patients": round(_gap_patients, 1),
            "achievable": _required_occ <= 100,
            "difficulty": _difficulty,
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 稼働率アラート付きKPI表示ヘルパー
# ---------------------------------------------------------------------------
def _render_ward_kpi_with_alert(raw_df, target_lower, target_upper, view_beds):
    """病棟KPIを表示し、稼働率低下時はアラートを表示する"""
    try:
        _occ_col = "occupancy_rate" if "occupancy_rate" in raw_df.columns else "稼働率"
        _tp_col = "total_patients" if "total_patients" in raw_df.columns else "在院患者数"

        _occ_mean = raw_df[_occ_col].mean()
        _sel_occ = float(_occ_mean) * 100 if pd.notna(_occ_mean) else 0.0
        # occupancy_rate is 0-1 ratio, 稼働率 might already be 0-100
        if _occ_col == "稼働率" and _sel_occ > 0 and _sel_occ < 1.5:
            _sel_occ = _sel_occ * 100

        _tp_mean = raw_df[_tp_col].mean()
        _sel_patients = int(_tp_mean) if pd.notna(_tp_mean) else 0

        _last_row = raw_df.iloc[-1]
        _last_occ_val = _last_row.get(_occ_col, 0) if hasattr(_last_row, 'get') else _last_row[_occ_col] if _occ_col in raw_df.columns else 0
        _sel_last_occ = float(_last_occ_val) * 100 if pd.notna(_last_occ_val) else 0.0
        if _occ_col == "稼働率" and _sel_last_occ > 0 and _sel_last_occ < 1.5:
            _sel_last_occ = _sel_last_occ * 100

        _last_tp_val = _last_row.get(_tp_col, 0) if hasattr(_last_row, 'get') else _last_row[_tp_col] if _tp_col in raw_df.columns else 0
        _sel_empty = max(0, view_beds - (int(_last_tp_val) if pd.notna(_last_tp_val) else 0))
    except Exception:
        # Fallback if data access fails
        _sel_occ = 0.0
        _sel_patients = 0
        _sel_last_occ = 0.0
        _sel_empty = 0

    _kpi1, _kpi2, _kpi3 = st.columns(3)

    # 直近稼働率の色分け
    if _sel_last_occ < target_lower * 100:
        _kpi1.metric("直近稼働率", f"{_sel_last_occ:.1f}%", delta=f"⚠️ 目標下限{target_lower*100:.0f}%未満", delta_color="inverse")
    elif _sel_last_occ > target_upper * 100:
        _kpi1.metric("直近稼働率", f"{_sel_last_occ:.1f}%", delta=f"目標上限{target_upper*100:.0f}%超過", delta_color="inverse")
    else:
        _kpi1.metric("直近稼働率", f"{_sel_last_occ:.1f}%", delta="目標レンジ内", delta_color="normal")

    _kpi2.metric("平均稼働率", f"{_sel_occ:.1f}%")
    _kpi3.metric("平均在院数", f"{_sel_patients}名")

    # 稼働率低下アラート（赤字）
    if _sel_last_occ < target_lower * 100:
        _remaining_days = _calc_remaining_days(raw_df)
        st.error(
            f"🔴 **稼働率低下アラート**: 直近稼働率 {_sel_last_occ:.1f}% が目標下限 {target_lower*100:.0f}% を下回っています "
            f"（空床 {_sel_empty}床 = 未活用病床コスト 約{_sel_empty * 34000 // 10000:.0f}万円/日・**今月残り{_remaining_days}日で約{_sel_empty * 34000 * _remaining_days // 10000:.0f}万円**）\n\n"
            "**対策:**\n"
            "- 🏥 予定入院の前倒しを外来担当医へ依頼\n"
            "- 📞 連携室へ依頼：紹介元クリニック・病院へ空床受入れ可能を発信\n"
            "- 💬 外来担当医に入院推奨閾値の引き下げを相談（通院患者の入院検討）\n"
            "- 🔄 C群患者の戦略的在院調整（平均在院日数21日以内で調整可、運営貢献額28,900円/日を維持）\n"
            "- 📋 B群患者も在院継続で運営貢献額確保（リハ加算1: 110点算定中）"
        )
        # 回復トレンドチェック
        if len(raw_df) >= 3:
            _trend_occ_col_r = "occupancy_rate" if "occupancy_rate" in raw_df.columns else "稼働率"
            _recent_3_r = raw_df[_trend_occ_col_r].tail(3).values
            if _recent_3_r[0] < 1.5:
                _recent_3_r = _recent_3_r * 100
            _trend_slope_r = _recent_3_r[-1] - _recent_3_r[0]
            if _trend_slope_r > 1:
                _projected_r = _sel_last_occ + _trend_slope_r * 2
                _recovery_msg = "このペースが続けば目標レンジへの復帰が見込めます。" if _projected_r >= target_lower * 100 else ""
                st.info(
                    f"📈 **回復トレンド検出**: 直近3日で {_trend_slope_r:+.1f}% の上昇傾向。{_recovery_msg}\n\n"
                    "**継続すべき対策:**\n"
                    "- 🏥 新規入院の受入継続（効果が出ています）\n"
                    "- 🔄 C群患者の戦略的在院調整を維持（運営貢献額28,900円/日を確保中）\n"
                    "- ✅ 現在の方針は正しい方向 — 焦らず継続"
                )
        # 月平均目標トラッカー
        _mt = _calc_monthly_target(raw_df, target_lower, 31, view_beds)
        if _mt:
            if _mt["difficulty"] == "impossible":
                st.error(
                    f"⛔ **月平均{_mt['monthly_target_pct']:.0f}%達成は困難**: "
                    f"経過{_mt['days_elapsed']}日の平均 {_mt['avg_so_far']:.1f}% → "
                    f"残り{_mt['days_remaining']}日で **{_mt['required_occ']:.1f}%** が必要（100%超のため達成困難）\n\n"
                    f"**月間未活用病床コスト見込み**: 約{int(_mt['gap_patients'] * 25000 * _mt['days_remaining'] // 10000)}万円"
                )
            elif _mt["difficulty"] == "hard":
                st.warning(
                    f"🟠 **月平均{_mt['monthly_target_pct']:.0f}%達成には高稼働が必要**: "
                    f"経過{_mt['days_elapsed']}日の平均 {_mt['avg_so_far']:.1f}% → "
                    f"残り{_mt['days_remaining']}日で **{_mt['required_occ']:.1f}%** が必要\n\n"
                    f"目標達成には1日あたり **+{_mt['gap_patients']:.0f}名** の在院患者増が必要"
                )
            elif _mt["difficulty"] == "moderate":
                st.info(
                    f"📊 **月平均{_mt['monthly_target_pct']:.0f}%達成への道筋**: "
                    f"経過{_mt['days_elapsed']}日の平均 {_mt['avg_so_far']:.1f}% → "
                    f"残り{_mt['days_remaining']}日で **{_mt['required_occ']:.1f}%** をキープすれば達成"
                )
        return  # トレンドチェック不要

    # トレンド予測（稼働率が低下傾向か？）
    _trend_occ_col = "occupancy_rate" if "occupancy_rate" in raw_df.columns else "稼働率"
    if len(raw_df) >= 3:
        _recent_3 = raw_df[_trend_occ_col].tail(3).values * 100
        _trend_slope = _recent_3[-1] - _recent_3[0]  # 3日間の変化量
        _projected = _sel_last_occ + _trend_slope  # 同じペースで続いた場合の予測

        if _trend_slope < -2 and _projected < target_lower * 100:
            _days_to_breach = max(1, int((_sel_last_occ - target_lower * 100) / abs(_trend_slope / 2)))
            st.warning(
                f"⚠️ **稼働率低下傾向**: 直近3日で {_trend_slope:+.1f}% の低下傾向。"
                f"このペースが続くと約{_days_to_breach}日後に目標下限を下回る可能性\n\n"
                "**予防策:**\n"
                "- 🏥 外来へ予定入院の前倒しを依頼 / 連携室へ空床状況の発信を依頼\n"
                "- 🔄 今週退院予定のC群患者の退院日を再検討（平均在院日数の最適化余地があれば活用）\n"
                "- 📋 退院集中日の分散を検討"
            )

    # 月平均目標トラッカー（レンジ内でも平均が低い場合に表示）
    _mt = _calc_monthly_target(raw_df, target_lower, 31, view_beds)
    if _mt and _mt["avg_so_far"] < _mt["monthly_target_pct"]:
        if _mt["difficulty"] == "impossible":
            st.error(
                f"⛔ **月平均{_mt['monthly_target_pct']:.0f}%達成は困難**: "
                f"経過{_mt['days_elapsed']}日の平均 {_mt['avg_so_far']:.1f}% → "
                f"残り{_mt['days_remaining']}日で **{_mt['required_occ']:.1f}%** が必要（100%超のため達成困難）"
            )
        elif _mt["difficulty"] == "hard":
            st.warning(
                f"🟠 **現在はレンジ内ですが月平均{_mt['monthly_target_pct']:.0f}%未達のリスク**: "
                f"経過{_mt['days_elapsed']}日の平均 {_mt['avg_so_far']:.1f}% → "
                f"残り{_mt['days_remaining']}日で **{_mt['required_occ']:.1f}%** が必要\n\n"
                f"**稼働率を高めに維持してください** — 目標達成には1日あたり **+{_mt['gap_patients']:.0f}名** の在院増が必要"
            )
        elif _mt["difficulty"] == "moderate":
            st.info(
                f"📊 **月平均{_mt['monthly_target_pct']:.0f}%達成には高めの稼働率が必要**: "
                f"経過{_mt['days_elapsed']}日の平均 {_mt['avg_so_far']:.1f}% → "
                f"残り{_mt['days_remaining']}日で **{_mt['required_occ']:.1f}%** をキープすれば達成可能"
            )
    elif _mt and _mt["avg_so_far"] >= _mt["monthly_target_pct"]:
        st.success(
            f"✅ **月平均{_mt['monthly_target_pct']:.0f}%達成ペース**: "
            f"経過{_mt['days_elapsed']}日の平均 {_mt['avg_so_far']:.1f}% — "
            f"残り{_mt['days_remaining']}日も **{_mt['required_occ']:.1f}%以上** を維持すれば目標達成"
        )


# ---------------------------------------------------------------------------
# 朝のブリーフィング（常時表示・タブ外最上部）
# ---------------------------------------------------------------------------
_is_demo = st.session_state.get("data_mode") == "🎮 デモモード（サンプルデータ）"
_sim_has_data = _simulation_available and isinstance(st.session_state.get("sim_df_raw"), pd.DataFrame) and len(st.session_state.sim_df_raw) > 0
if _actual_data_available or _sim_has_data or (_is_demo and isinstance(st.session_state.get("demo_data"), pd.DataFrame) and len(st.session_state.get("demo_data", pd.DataFrame())) > 0):
    with st.container():
        st.markdown("### ☀️ 今日のブリーフィング")
        _brief_cols = st.columns([1, 1, 1, 2])

        # 稼働率ゲージ（plotly gauge chart）
        with _brief_cols[0]:
            import plotly.graph_objects as go
            _gauge_occ = float(_active_raw_df["occupancy_rate"].iloc[-1] * 100) if "occupancy_rate" in _active_raw_df.columns else float(_active_raw_df["稼働率"].iloc[-1])
            _gauge_fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=_gauge_occ,
                number={"suffix": "%", "font": {"size": 28}},
                title={"text": f"稼働率（{_selected_ward_key}）", "font": {"size": 14}},
                gauge={
                    "axis": {"range": [75, 100], "tickwidth": 1},
                    "bar": {"color": "#1f77b4"},
                    "steps": [
                        {"range": [75, target_lower * 100], "color": "#ffcccc"},
                        {"range": [target_lower * 100, target_upper * 100], "color": "#ccffcc"},
                        {"range": [target_upper * 100, 100], "color": "#ffffcc"},
                    ],
                    "threshold": {
                        "line": {"color": "red", "width": 2},
                        "thickness": 0.75,
                        "value": target_lower * 100,
                    },
                },
            ))
            _gauge_fig.update_layout(height=200, margin=dict(l=20, r=20, t=40, b=10))
            st.plotly_chart(_gauge_fig, use_container_width=True)

        # 主要KPI
        with _brief_cols[1]:
            _brief_tp_col = "total_patients" if "total_patients" in _active_raw_df.columns else "在院患者数"
            _brief_patients = int(_active_raw_df[_brief_tp_col].iloc[-1])
            _brief_empty = _view_beds - _brief_patients
            st.metric("在院患者数", f"{_brief_patients}名", delta=f"空床 {_brief_empty}床")
            if _brief_empty > (_view_beds * 0.10):
                _remaining_days = _calc_remaining_days(_active_raw_df) if isinstance(_active_raw_df, pd.DataFrame) and len(_active_raw_df) > 0 else 0 if isinstance(_active_raw_df, pd.DataFrame) and len(_active_raw_df) > 0 else 0
                st.caption(f"⚠️ 空床{_brief_empty}床 = 未活用病床コスト 約{_brief_empty * 34000 // 10000:.0f}万円/日・今月残り{_remaining_days}日で約{_brief_empty * 34000 * _remaining_days // 10000:.0f}万円")

        # 病棟比較ミニバッジ
        with _brief_cols[2]:
            if _selected_ward_key == "全体":
                for _bw in ["5F", "6F"]:
                    _bw_beds = get_ward_beds(_bw)
                    if hasattr(st.session_state, 'sim_ward_raw_dfs') and _bw in st.session_state.get("sim_ward_raw_dfs", {}):
                        _bw_df = st.session_state.sim_ward_raw_dfs[_bw]
                        _bw_occ = float(_bw_df["occupancy_rate"].iloc[-1] * 100)
                    elif "_ward_raw_dfs" in dir() and _bw in _ward_raw_dfs:
                        _bw_df = _ward_raw_dfs[_bw]
                        _bw_occ_col = "occupancy_rate" if "occupancy_rate" in _bw_df.columns else "稼働率"
                        _bw_occ = float(_bw_df[_bw_occ_col].iloc[-1] * 100) if _bw_df[_bw_occ_col].iloc[-1] < 1.5 else float(_bw_df[_bw_occ_col].iloc[-1])
                    else:
                        _bw_occ = None
                    if _bw_occ is not None:
                        _bw_status = "✅ 目標内" if target_lower * 100 <= _bw_occ <= target_upper * 100 else "⚠️ 要注意"
                        st.markdown(f"**{_bw}**: {_bw_occ:.1f}% {_bw_status}")
            else:
                st.markdown(f"**{_selected_ward_key}** を表示中")
                _other = "6F" if _selected_ward_key == "5F" else "5F"
                st.caption(f"他病棟 → サイドバーで切替")

        # 今日のアクション（簡潔版）
        with _brief_cols[3]:
            st.markdown("**📋 今日のアクション**")
            _occ_col_brief = "occupancy_rate" if "occupancy_rate" in _active_raw_df.columns else "稼働率"
            _last_occ_brief = float(_active_raw_df[_occ_col_brief].iloc[-1])
            if _last_occ_brief < 1.5:
                _last_occ_brief *= 100

            if _last_occ_brief < target_lower * 100:
                # 回復トレンドチェック
                _is_recovering = False
                if len(_active_raw_df) >= 3:
                    _rec_check = _active_raw_df[_occ_col_brief].tail(3).values
                    if _rec_check[0] < 1.5:
                        _rec_check = _rec_check * 100
                    if _rec_check[-1] - _rec_check[0] > 1:
                        _is_recovering = True

                if _is_recovering:
                    st.markdown("📈 **稼働率回復中 — 対策継続**")
                    st.markdown("- ✅ 入院受入施策が効果を発揮中（外来・連携室への依頼継続）")
                    st.markdown("- 🔄 戦略的在院調整を維持")
                    st.markdown("- 📊 回復ペースを注視（焦らず継続）")
                else:
                    st.markdown("🔴 **稼働率低下中 — 即対応**")
                    st.markdown("- 連携室へ依頼：紹介元へ空床受入れ可能を発信")
                    st.markdown("- 外来へ予定入院の前倒しを依頼")
                    st.markdown("- C群の戦略的在院調整を検討")
                    st.markdown("- B群は在院継続で運営貢献額確保（運営貢献額30,000円/日）")
            elif _last_occ_brief > target_upper * 100:
                st.markdown("🟡 **高稼働 — 退院調整検討**")
                st.markdown("- A群→B群への移行準備確認")
                st.markdown("- 退院可能なC群の退院日確定")
            else:
                st.markdown("🟢 **目標レンジ内 — 維持継続**")
                st.markdown("- 明日以降の入退院バランス確認")
                st.markdown("- B群リハビリ進捗チェック")

            # トレンド警告（3日スロープ）
            if len(_active_raw_df) >= 3:
                _recent_brief = _active_raw_df[_occ_col_brief].tail(3).values
                if _recent_brief[0] < 1.5:
                    _recent_brief = _recent_brief * 100
                _slope_brief = _recent_brief[-1] - _recent_brief[0]
                if _slope_brief < -2 and _last_occ_brief < (target_lower * 100 + 3):
                    st.warning(f"📉 低下トレンド検出（3日間で{_slope_brief:.1f}%）")
                elif _slope_brief > 1 and _last_occ_brief < target_lower * 100:
                    st.info(f"📈 回復トレンド（3日間で+{_slope_brief:.1f}%） — 対策継続を推奨")

            # 月平均達成見通し
            _mt_brief = _calc_monthly_target(_active_raw_df, target_lower, 31, _view_beds) if isinstance(_active_raw_df, pd.DataFrame) and len(_active_raw_df) > 0 else None
            if _mt_brief:
                if _mt_brief["avg_so_far"] >= _mt_brief["monthly_target_pct"]:
                    st.caption(f"✅ 月平均 {_mt_brief['avg_so_far']:.1f}% — 達成ペース")
                elif _mt_brief["difficulty"] in ("easy", "moderate"):
                    st.caption(f"📊 月平均 {_mt_brief['avg_so_far']:.1f}% — 残り{_mt_brief['days_remaining']}日で{_mt_brief['required_occ']:.0f}%必要")
                else:
                    st.caption(f"⚠️ 月平均 {_mt_brief['avg_so_far']:.1f}% — 達成に{_mt_brief['required_occ']:.0f}%必要（厳しい）")

        st.markdown("---")

# ---------------------------------------------------------------------------
# タブ構成
# ---------------------------------------------------------------------------
if _is_actual_data_mode:
    # 実績データモード: 戦略比較は非表示
    tab_names = [
        "📊 日次推移", "🔄 フェーズ構成", "💰 運営分析", "🚨 運営改善アラート",
        "\U0001f3af 意思決定ダッシュボード", "\U0001f52e What-if分析", "\U0001f4c8 トレンド分析",
    ]
    tab_names.append("👨‍⚕️ 退院タイミング")
    tab_names.append("データ")
    if _DATA_MANAGER_AVAILABLE:
        tab_names.append("📋 日次データ入力")
        tab_names.append("🔮 実績分析・予測")
    if _DOCTOR_MASTER_AVAILABLE:
        tab_names.append("👨‍⚕️ 医師別分析")
        tab_names.append("💡 改善のヒント")
        tab_names.append("⚙️ 医師マスター")
else:
    # シミュレーションモード（従来通り）
    tab_names = [
        "📊 日次推移", "🔄 フェーズ構成", "💰 運営分析", "🚨 運営改善アラート",
        "\U0001f3af 意思決定ダッシュボード", "\U0001f52e What-if分析", "\U0001f4c8 トレンド分析",
    ]
    tab_names.append("👨‍⚕️ 退院タイミング")
    if st.session_state.comparison is not None:
        tab_names.append("戦略比較")
    tab_names.append("データ")
    if _DATA_MANAGER_AVAILABLE:
        tab_names.append("📋 日次データ入力")
        tab_names.append("🔮 実績分析・予測")
    if _DOCTOR_MASTER_AVAILABLE:
        tab_names.append("👨‍⚕️ 医師別分析")
        tab_names.append("💡 改善のヒント")
        tab_names.append("⚙️ 医師マスター")

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
            st.info("🎓 これは教育用デモデータです。5F（稼働率低下傾向）と6F（安定稼働）のシナリオが含まれています。")

            # デモデータが既にロード済みかチェック
            _demo_loaded = isinstance(st.session_state.demo_data, pd.DataFrame) and len(st.session_state.demo_data) > 0

            dm_demo_col1, dm_demo_col2, dm_demo_col3 = st.columns(3)
            with dm_demo_col1:
                if _demo_loaded:
                    _demo_ward_count = st.session_state.demo_data["ward"].nunique() if "ward" in st.session_state.demo_data.columns else 0
                    _demo_day_count = st.session_state.demo_data["date"].nunique() if "date" in st.session_state.demo_data.columns else 0
                    st.success(f"✅ デモデータロード済（{_demo_ward_count}病棟 × {_demo_day_count}日分）")
                else:
                    st.warning("デモデータが見つかりません")
            with dm_demo_col2:
                if st.button("🔄 ランダムデータで再生成（30日分）", key="dm_gen_sample",
                             help="教育用デモの代わりにランダムなダミーデータを生成します"):
                    _demo_5f = generate_sample_data(num_days=30, num_beds=get_ward_beds("5F"))
                    _demo_5f["ward"] = "5F"
                    _demo_6f = generate_sample_data(num_days=30, num_beds=get_ward_beds("6F"))
                    _demo_6f["ward"] = "6F"
                    st.session_state.demo_data = pd.concat([_demo_5f, _demo_6f], ignore_index=True).sort_values(["date", "ward"]).reset_index(drop=True)
                    st.success("ランダムサンプルデータ（30日分）を生成しました。")
                    _auto_save_to_db()
                    st.rerun()

            with dm_demo_col3:
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
                                      "discharge_a", "discharge_b", "discharge_c",
                                      "phase_a_count", "phase_b_count", "phase_c_count",
                                      "notes"]
                _demo_cols_available = [c for c in _demo_cols_to_show if c in _demo_display.columns]
                st.dataframe(
                    _demo_display[_demo_cols_available].rename(columns={
                        "date_str": "日付",
                        "total_patients": "在院患者数",
                        "new_admissions": "新規入院",
                        "discharges": "退院",
                        "discharge_a": "A群退院",
                        "discharge_b": "B群退院",
                        "discharge_c": "C群退院",
                        "phase_a_count": "A群（自動）",
                        "phase_b_count": "B群（自動）",
                        "phase_c_count": "C群（自動）",
                        "notes": "備考",
                    }),
                    width="stretch",
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
                        _auto_save_to_db()
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

            # --- 全データクリア ---
            if len(st.session_state.daily_data) > 0:
                with st.expander("⚠️ 全データ消去", expanded=False):
                    st.warning(f"現在 {len(st.session_state.daily_data)} 件のデータがあります。この操作は取り消せません。")
                    _confirm_text = st.text_input(
                        "消去するには「全て消去」と入力してください",
                        key="dm_clear_confirm",
                    )
                    if st.button("🗑️ 全データを消去", type="primary", disabled=(_confirm_text != "全て消去"), key="dm_clear_btn"):
                        st.session_state.daily_data = dm_create_empty_dataframe()
                        st.session_state.abc_state = {"A": 0, "B": 0, "C": 0}
                        st.session_state.day_buckets = {k: 0 for k in DAY_BUCKET_KEYS}
                        if "ward_abc_state" in st.session_state:
                            del st.session_state.ward_abc_state
                        if "ward_day_buckets" in st.session_state:
                            del st.session_state.ward_day_buckets
                        if _DB_AVAILABLE:
                            db_clear_all()
                        st.success("全データを消去しました。")
                        st.rerun()

            st.markdown("---")

            # --- データ入力フォーム ---
            st.markdown("#### 新しいデータを追加")

            # 初回セットアップ: データがない場合、ベッドマップから初期値を設定
            _has_data = len(st.session_state.daily_data) > 0
            _abc_is_zero = (st.session_state.abc_state["A"] == 0
                            and st.session_state.abc_state["B"] == 0
                            and st.session_state.abc_state["C"] == 0)

            if not _has_data and _abc_is_zero:
                st.info("⚡ 初回セットアップ：病棟ベッドマップで各患者の在院日数を入力してください（初回のみ）")

                if _BED_MAP_AVAILABLE:
                    # 病棟選択タブ
                    setup_tab_5f, setup_tab_6f = st.tabs(["5F病棟", "6F病棟"])

                    with setup_tab_5f:
                        bed_data_5f = render_bed_map("5F")
                    with setup_tab_6f:
                        bed_data_6f = render_bed_map("6F")

                    st.markdown("---")

                    # 両病棟の確認・確定
                    st.markdown("### 確認・確定")
                    confirm_col1, confirm_col2 = st.columns(2)
                    with confirm_col1:
                        confirmed_5f = render_confirmation("5F", bed_data_5f, WARD_CONFIG["5F"]["rooms"])
                    with confirm_col2:
                        confirmed_6f = render_confirmation("6F", bed_data_6f, WARD_CONFIG["6F"]["rooms"])

                    if confirmed_5f and confirmed_6f:
                        # 5Fのバケット計算
                        buckets_5f = bed_data_to_buckets(bed_data_5f)
                        a_5f, b_5f, c_5f = buckets_to_abc(buckets_5f)

                        # 6Fのバケット計算
                        buckets_6f = bed_data_to_buckets(bed_data_6f)
                        a_6f, b_6f, c_6f = buckets_to_abc(buckets_6f)

                        # 合計
                        total_a = a_5f + a_6f
                        total_b = b_5f + b_6f
                        total_c = c_5f + c_6f

                        # セッションステートに保存
                        st.session_state.ward_abc_state = {
                            "5F": {"A": a_5f, "B": b_5f, "C": c_5f},
                            "6F": {"A": a_6f, "B": b_6f, "C": c_6f},
                        }
                        st.session_state.ward_day_buckets = {
                            "5F": buckets_5f,
                            "6F": buckets_6f,
                        }
                        st.session_state.abc_state = {"A": total_a, "B": total_b, "C": total_c}
                        st.session_state.day_buckets = {k: buckets_5f[k] + buckets_6f[k] for k in DAY_BUCKET_KEYS}
                        st.session_state.init_total_patients = sum(1 for v in bed_data_5f.values() if v > 0) + sum(1 for v in bed_data_6f.values() if v > 0)

                        st.success(f"✅ 初期値を設定しました！ 5F: A{a_5f}/B{b_5f}/C{c_5f} | 6F: A{a_6f}/B{b_6f}/C{c_6f} | 合計: {total_a + total_b + total_c}名")
                        _auto_save_to_db()
                        st.rerun()
                    elif confirmed_5f or confirmed_6f:
                        st.warning("両方の病棟を確定してください。")
                else:
                    st.warning("ベッドマップUIが利用できません。")
                    if "_BED_MAP_ERROR" in dir():
                        st.code(_BED_MAP_ERROR)

                st.markdown("---")

            # 現在のA/B/C群状態を表示
            _ward_abc = st.session_state.get("ward_abc_state", {})
            if _ward_abc:
                st.markdown("**病棟別 A/B/C群**")
                w_col1, w_col2, w_col3 = st.columns(3)
                for _w_col, _w_name in zip([w_col1, w_col2, w_col3], ["5F", "6F", "合計"]):
                    with _w_col:
                        if _w_name == "合計":
                            _w_abc = st.session_state.abc_state
                        else:
                            _w_abc = _ward_abc.get(_w_name, {"A": 0, "B": 0, "C": 0})
                        _w_total = _w_abc["A"] + _w_abc["B"] + _w_abc["C"]
                        st.markdown(f"**{_w_name}**: A:{_w_abc['A']} B:{_w_abc['B']} C:{_w_abc['C']} 計:{_w_total}")
            else:
                abc_col1, abc_col2, abc_col3, abc_col4 = st.columns(4)
                with abc_col1:
                    st.metric("A群（自動計算）", st.session_state.abc_state["A"])
                with abc_col2:
                    st.metric("B群（自動計算）", st.session_state.abc_state["B"])
                with abc_col3:
                    st.metric("C群（自動計算）", st.session_state.abc_state["C"])
                with abc_col4:
                    abc_total = st.session_state.abc_state["A"] + st.session_state.abc_state["B"] + st.session_state.abc_state["C"]
                    st.metric("合計", abc_total)

            with st.form("dm_add_record_form", clear_on_submit=True):
                form_col0, form_col1, form_col2 = st.columns(3)
                with form_col0:
                    input_ward = st.selectbox("病棟", ["5F", "6F"], key="input_ward_select")
                with form_col1:
                    input_date = st.date_input("日付", value=pd.Timestamp.now().normalize())
                with form_col2:
                    _ward_max_beds = 47
                    input_total = st.number_input("在院患者総数", min_value=0, max_value=_ward_max_beds, value=40, step=1)

                input_admissions = st.number_input("新規入院数", min_value=0, max_value=30, value=5, step=1)

                st.markdown("**退院内訳（各群の退院数を入力 → 退院数は自動合算）**")
                form_col5, form_col6, form_col7 = st.columns(3)
                with form_col5:
                    input_discharge_a = st.number_input("A群退院（1-5日目）", min_value=0, max_value=30, value=0, step=1)
                with form_col6:
                    input_discharge_b = st.number_input("B群退院（6-14日目）", min_value=0, max_value=30, value=0, step=1)
                with form_col7:
                    input_discharge_c = st.number_input("C群退院（15日目〜）", min_value=0, max_value=30, value=0, step=1)

                # 退院数は内訳から自動合算
                auto_discharges = input_discharge_a + input_discharge_b + input_discharge_c
                st.info(f"💡 退院数（自動合算）: **{auto_discharges}名**（A群:{input_discharge_a} + B群:{input_discharge_b} + C群:{input_discharge_c}）")

                input_notes = st.text_input("備考（任意）", value="")

                submitted = st.form_submit_button("追加", type="primary", width="stretch")

                if submitted:
                    # A/B/C群を自動計算（日齢バケットモデル対応）
                    _prev_buckets = st.session_state.get("day_buckets", None)

                    new_abc, new_buckets = calculate_abc_groups(
                        st.session_state.abc_state,
                        input_admissions,
                        input_discharge_a, input_discharge_b, input_discharge_c,
                        prev_buckets=_prev_buckets,
                    )
                    new_a = new_abc["A"]
                    new_b = new_abc["B"]
                    new_c = new_abc["C"]

                    new_record = {
                        "date": pd.Timestamp(input_date),
                        "ward": input_ward,
                        "total_patients": int(input_total),
                        "new_admissions": int(input_admissions),
                        "discharges": int(auto_discharges),
                        "discharge_a": int(input_discharge_a),
                        "discharge_b": int(input_discharge_b),
                        "discharge_c": int(input_discharge_c),
                        "phase_a_count": new_a,
                        "phase_b_count": new_b,
                        "phase_c_count": new_c,
                        "avg_los": pd.NA,
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
                        # ABC状態とバケットを更新
                        st.session_state.abc_state = {"A": new_a, "B": new_b, "C": new_c}
                        if new_buckets is not None:
                            st.session_state.day_buckets = new_buckets
                        st.success(f"{input_date} のデータを追加しました。（A群:{new_a} B群:{new_b} C群:{new_c} / 退院計:{auto_discharges}名）")
                        _auto_save_to_db()
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
                                  "discharge_a", "discharge_b", "discharge_c",
                                  "phase_a_count", "phase_b_count", "phase_c_count",
                                  "notes"]
                _display_cols_available = [c for c in _display_cols if c in display_data.columns]
                edited_df = st.data_editor(
                    display_data[_display_cols_available].rename(columns={
                        "date_str": "日付",
                        "total_patients": "在院患者数",
                        "new_admissions": "新規入院",
                        "discharges": "退院（自動）",
                        "discharge_a": "A群退院",
                        "discharge_b": "B群退院",
                        "discharge_c": "C群退院",
                        "phase_a_count": "A群（自動）",
                        "phase_b_count": "B群（自動）",
                        "phase_c_count": "C群（自動）",
                        "notes": "備考",
                    }),
                    column_config={
                        "日付": st.column_config.TextColumn(disabled=True),
                        "退院（自動）": st.column_config.NumberColumn(disabled=True),
                        "A群（自動）": st.column_config.NumberColumn(disabled=True),
                        "B群（自動）": st.column_config.NumberColumn(disabled=True),
                        "C群（自動）": st.column_config.NumberColumn(disabled=True),
                    },
                    width="stretch",
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
                                "A群退院": "discharge_a",
                                "B群退院": "discharge_b",
                                "C群退院": "discharge_c",
                                "備考": "notes",
                            }
                            for ja_col, en_col in col_map_rev.items():
                                if ja_col in edited_df.columns:
                                    updated[en_col] = edited_df[ja_col].values

                            # 退院数を内訳から再計算
                            updated["discharges"] = (
                                updated["discharge_a"].fillna(0).astype(int)
                                + updated["discharge_b"].fillna(0).astype(int)
                                + updated["discharge_c"].fillna(0).astype(int)
                            )

                            # A/B/C群を時系列順に再計算（日齢バケットモデル対応）
                            updated = updated.sort_values("date").reset_index(drop=True)

                            # 初日のバケットを取得（session_stateに保存された初期バケット）
                            _edit_buckets = st.session_state.get("day_buckets", None)
                            _edit_abc = st.session_state.abc_state.copy()

                            # 初期バケットがある場合は初期バケットから再構築
                            # データの初日からバケットモデルで順次再計算
                            if _edit_buckets is not None and _DATA_MANAGER_AVAILABLE:
                                # 初期バケットを復元（init_total_patientsの時点のバケット）
                                # 全レコードを初期状態から順に再計算
                                _recalc_buckets = st.session_state.get("_initial_day_buckets", _edit_buckets)
                                # _initial_day_bucketsが未保存なら現在のday_bucketsを初期として使う
                                # ただし、初回設定時のバケットを保存しておく必要がある
                                if "_initial_day_buckets" not in st.session_state and _edit_buckets is not None:
                                    # 初期バケットがないので、バケットなしで再計算（簡易モデル）
                                    pass

                                _cur_buckets = st.session_state.get("_initial_day_buckets", None)
                                if _cur_buckets is not None:
                                    for idx in range(len(updated)):
                                        row = updated.iloc[idx]
                                        _new_buckets = advance_day_buckets(
                                            _cur_buckets,
                                            int(row.get("new_admissions", 0) or 0),
                                            int(row.get("discharge_a", 0) or 0),
                                            int(row.get("discharge_b", 0) or 0),
                                            int(row.get("discharge_c", 0) or 0),
                                        )
                                        a, b, c = buckets_to_abc(_new_buckets)
                                        updated.at[idx, "phase_a_count"] = a
                                        updated.at[idx, "phase_b_count"] = b
                                        updated.at[idx, "phase_c_count"] = c
                                        _cur_buckets = _new_buckets

                                    st.session_state.day_buckets = _cur_buckets
                                    st.session_state.abc_state = {"A": a, "B": b, "C": c}
                                else:
                                    # 簡易モデルでフォールバック
                                    _fb_abc = {"A": 0, "B": 0, "C": 0}
                                    for idx in range(len(updated)):
                                        row = updated.iloc[idx]
                                        _fb_abc, _ = calculate_abc_groups(
                                            _fb_abc,
                                            int(row.get("new_admissions", 0) or 0),
                                            int(row.get("discharge_a", 0) or 0),
                                            int(row.get("discharge_b", 0) or 0),
                                            int(row.get("discharge_c", 0) or 0),
                                            prev_buckets=None,
                                        )
                                        updated.at[idx, "phase_a_count"] = _fb_abc["A"]
                                        updated.at[idx, "phase_b_count"] = _fb_abc["B"]
                                        updated.at[idx, "phase_c_count"] = _fb_abc["C"]
                                    st.session_state.abc_state = _fb_abc
                            else:
                                # バケットなし: 簡易モデルで再計算
                                _fb_abc = {"A": 0, "B": 0, "C": 0}
                                for idx in range(len(updated)):
                                    row = updated.iloc[idx]
                                    _fb_abc, _ = calculate_abc_groups(
                                        _fb_abc,
                                        int(row.get("new_admissions", 0) or 0),
                                        int(row.get("discharge_a", 0) or 0),
                                        int(row.get("discharge_b", 0) or 0),
                                        int(row.get("discharge_c", 0) or 0),
                                        prev_buckets=None,
                                    )
                                    updated.at[idx, "phase_a_count"] = _fb_abc["A"]
                                    updated.at[idx, "phase_b_count"] = _fb_abc["B"]
                                    updated.at[idx, "phase_c_count"] = _fb_abc["C"]
                                st.session_state.abc_state = _fb_abc

                            st.session_state.daily_data = updated
                            st.success("変更を保存しました。A/B/C群と退院数を再計算しました。")
                            _auto_save_to_db()
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
                            _auto_save_to_db()
                            st.rerun()

                st.caption(f"合計 {len(st.session_state.daily_data)} 件のレコード")
            else:
                st.warning(
                    "まずデータを入力してください。操作方法がわからない場合は"
                    "「🎮 デモモード（サンプルデータ）」でお試しください。"
                )

        # === 入退院詳細入力 ===
        if _DOCTOR_MASTER_AVAILABLE and _DETAIL_DATA_AVAILABLE:
            st.markdown("---")
            st.markdown("#### 入退院詳細（医師別）")
            st.caption("入院・退院ごとに経路と医師を記録します")

            _detail_tab_adm, _detail_tab_dis = st.tabs(["🏥 入院記録", "🚪 退院記録"])

            _active_doctors = dm_doctor.get_active_doctors() if _DOCTOR_MASTER_AVAILABLE else []
            _doctor_names = [d["name"] for d in _active_doctors]
            _routes = dm_doctor.get_admission_routes() if _DOCTOR_MASTER_AVAILABLE else []
            _source_options = dm_doctor.get_admission_source_options() if _DOCTOR_MASTER_AVAILABLE else {}

            # Flatten source options for selectbox
            _flat_sources = ["（なし）"]
            for group_label, names in _source_options.items():
                _flat_sources.append(f"--- {group_label} ---")
                _flat_sources.extend(names)
            _selectable_sources = [s for s in _flat_sources if not s.startswith("---")]

            with _detail_tab_adm:
                with st.form("admission_detail_form"):
                    st.markdown("##### 入院を記録")
                    _adm_col1, _adm_col2 = st.columns(2)
                    with _adm_col1:
                        _adm_date = st.date_input("入院日", value=date.today(), key="adm_detail_date")
                        _adm_ward = st.selectbox("病棟", ["5F", "6F"], key="adm_detail_ward")
                    with _adm_col2:
                        _adm_route = st.selectbox("入院経路", _routes, key="adm_detail_route")

                    _adm_col3, _adm_col4 = st.columns(2)
                    with _adm_col3:
                        _adm_source = st.selectbox("入院創出医（入院を生んだ医師）", _selectable_sources, key="adm_detail_source")
                    with _adm_col4:
                        _adm_attending = st.selectbox("入院担当医（主治医）", [""] + _doctor_names, key="adm_detail_attending")

                    _adm_submit = st.form_submit_button("入院を記録", type="primary")
                    if _adm_submit:
                        if not _adm_attending:
                            st.error("入院担当医を選択してください")
                        else:
                            _source_name = _adm_source if _adm_source != "（なし）" else ""
                            st.session_state.admission_details = add_admission_event(
                                st.session_state.admission_details,
                                str(_adm_date), _adm_ward, _adm_route,
                                _source_name, _adm_attending
                            )
                            save_details(st.session_state.admission_details)
                            st.success(f"✅ 入院記録を追加しました（{_adm_attending}先生, {_adm_route}）")
                            st.rerun()

            with _detail_tab_dis:
                with st.form("discharge_detail_form"):
                    st.markdown("##### 退院を記録")
                    _dis_col1, _dis_col2 = st.columns(2)
                    with _dis_col1:
                        _dis_date = st.date_input("退院日", value=date.today(), key="dis_detail_date")
                        _dis_ward = st.selectbox("病棟", ["5F", "6F"], key="dis_detail_ward")
                    with _dis_col2:
                        _dis_attending = st.selectbox("担当医（主治医）", [""] + _doctor_names, key="dis_detail_attending")
                        _dis_los = st.number_input("在院日数", min_value=1, max_value=365, value=14, key="dis_detail_los")

                    # Show auto-calculated phase
                    if _dis_los <= 5:
                        st.info(f"フェーズ: **A群**（急性期 1-5日）| 在院{_dis_los}日")
                    elif _dis_los <= 14:
                        st.info(f"フェーズ: **B群**（回復期 6-14日）| 在院{_dis_los}日")
                    else:
                        st.info(f"フェーズ: **C群**（退院準備期 15日以上）| 在院{_dis_los}日")

                    _dis_submit = st.form_submit_button("退院を記録", type="primary")
                    if _dis_submit:
                        if not _dis_attending:
                            st.error("担当医を選択してください")
                        else:
                            st.session_state.admission_details = add_discharge_event(
                                st.session_state.admission_details,
                                str(_dis_date), _dis_ward, _dis_attending, _dis_los
                            )
                            save_details(st.session_state.admission_details)
                            st.success(f"✅ 退院記録を追加しました（{_dis_attending}先生, 在院{_dis_los}日）")
                            st.rerun()

            # Show recent records
            if len(st.session_state.admission_details) > 0:
                st.markdown("##### 直近の記録")
                _recent = st.session_state.admission_details.sort_values("date", ascending=False).head(20).copy()
                _display_cols = {
                    "date": "日付", "ward": "病棟", "event_type": "種別",
                    "route": "経路", "source_doctor": "入院創出医",
                    "attending_doctor": "担当医", "los_days": "在院日数", "phase": "フェーズ"
                }
                _available_detail_cols = [c for c in _display_cols.keys() if c in _recent.columns]
                _recent_display = _recent[_available_detail_cols].rename(
                    columns={k: v for k, v in _display_cols.items() if k in _available_detail_cols}
                )
                if "種別" in _recent_display.columns:
                    _recent_display["種別"] = _recent_display["種別"].map({"admission": "入院", "discharge": "退院"})
                st.dataframe(_recent_display, use_container_width=True, hide_index=True)

    # ----- タブ: 🔮 実績分析・予測 -----
    with tabs[_dm_tab_analysis_idx]:
        st.subheader("🔮 実績分析・予測")

        # データモードに応じてデータソースを切り替え
        _is_analysis_demo = st.session_state.get("data_mode") == "🎮 デモモード（サンプルデータ）"
        if _is_analysis_demo:
            _active_data = st.session_state.demo_data if isinstance(st.session_state.demo_data, pd.DataFrame) else pd.DataFrame()
        else:
            _active_data = st.session_state.daily_data

        # Ward selector filtering / aggregation
        if not _is_analysis_demo and isinstance(_active_data, pd.DataFrame) and "ward" in _active_data.columns:
            if _selected_ward_key in ("5F", "6F"):
                _active_data = _active_data[_active_data["ward"] == _selected_ward_key].copy()
            else:
                # 全体モード: 病棟データを日付ごとに合算
                _active_data = aggregate_wards(_active_data)

        if _selected_ward_key != "全体":
            st.caption(f"📍 {_selected_ward_key} ({_view_beds}床) のデータを表示中")

        if _is_analysis_demo:
            st.warning("⚠️ デモデータによる分析です。実際の病棟データではありません。")

        if not isinstance(_active_data, pd.DataFrame) or len(_active_data) < 3:
            if _is_analysis_demo:
                st.warning("分析には最低3日分のデモデータが必要です。「📋 日次データ入力」タブでサンプルデータを生成してください。")
            else:
                st.warning("分析には最低3日分のデータが必要です。「📋 日次データ入力」タブでデータを追加してください。")
        else:
            _analysis_df = _active_data.copy()
            _metrics_df = calculate_daily_metrics(_analysis_df, num_beds=_view_beds)

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
                _a_mean = _recent7["phase_a_ratio"].mean()
                avg_a = float(_a_mean) * 100 if pd.notna(_a_mean) else 0.0
                st.metric("A群平均", f"{avg_a:.1f}%" if pd.notna(_a_mean) else "N/A")
            with s_col5:
                _b_mean = _recent7["phase_b_ratio"].mean()
                avg_b = float(_b_mean) * 100 if pd.notna(_b_mean) else 0.0
                st.metric("B群平均", f"{avg_b:.1f}%" if pd.notna(_b_mean) else "N/A")
            with s_col6:
                _c_mean = _recent7["phase_c_ratio"].mean()
                avg_c = float(_c_mean) * 100 if pd.notna(_c_mean) else 0.0
                st.metric("C群平均", f"{avg_c:.1f}%" if pd.notna(_c_mean) else "N/A")

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
                _metrics_df["phase_a_ratio"].fillna(0).astype(float) * 100,
                _metrics_df["phase_b_ratio"].fillna(0).astype(float) * 100,
                _metrics_df["phase_c_ratio"].fillna(0).astype(float) * 100,
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
                _analysis_df, num_beds=_view_beds, horizon=7
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
                st.dataframe(pred_display, width="stretch", hide_index=True)
            else:
                st.info("予測に十分なデータがありません。")

            st.markdown("---")

            # --- 下部: 月次着地予想 ---
            st.markdown("#### 今月の着地予想")
            _monthly_kpi = predict_monthly_kpi(
                _analysis_df, num_beds=_view_beds,
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
                    gross_profit = _monthly_kpi["推定月次運営貢献額"]  # bed_data_manager側のキー名
                    if abs(gross_profit) >= 10000:
                        st.metric("推定月次運営貢献額", f"¥{gross_profit/10000:,.1f}万")
                    else:
                        st.metric("推定月次運営貢献額", f"¥{gross_profit:,}")
                    st.metric("推定平均在院日数", f"{_monthly_kpi['推定平均在院日数']}日",
                             help="厚労省公式: 在院患者延日数 ÷ ((新入院患者数 + 退院患者数) ÷ 2)")

                st.caption(f"残り{_monthly_kpi['残り日数']}日 | 予測入院数: {_monthly_kpi['今月入院数_予測']}名")
                st.caption("※ 平均在院日数は厚生労働省「病院報告」の公式定義に準拠")

            st.markdown("---")

            # --- 最下部: 週次トレンド ---
            st.markdown("#### 週次トレンド")
            _weekly = generate_weekly_summary(_analysis_df, num_beds=_view_beds)

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
                    width="stretch",
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
    # シミュレーションモードの病棟セレクター対応
    if _selected_ward_key in ("5F", "6F") and st.session_state.sim_ward_dfs.get(_selected_ward_key) is not None:
        df = st.session_state.sim_ward_dfs[_selected_ward_key]
        summary = st.session_state.sim_ward_summaries[_selected_ward_key]
        _active_raw_df = st.session_state.sim_ward_raw_dfs[_selected_ward_key]
        _active_cli_params = st.session_state.sim_params.copy()
        _active_cli_params["num_beds"] = get_ward_beds(_selected_ward_key)
        _view_beds = get_ward_beds(_selected_ward_key)
    else:
        df = st.session_state.sim_df
        summary = st.session_state.sim_summary
        _active_raw_df = st.session_state.sim_df_raw
        _active_cli_params = st.session_state.sim_params
        # Ward selected but ward data not available - need to re-run simulation
        if _selected_ward_key in ("5F", "6F"):
            _view_beds = get_ward_beds(_selected_ward_key)

# ---------------------------------------------------------------------------
# _active_raw_df と _active_display_df のフォールバック設定
# ---------------------------------------------------------------------------
if '_active_raw_df' not in locals():
    _active_raw_df = pd.DataFrame()
if '_active_display_df' not in locals():
    _active_display_df = pd.DataFrame()
if '_active_cli_params' not in locals():
    _active_cli_params = {}

# --- サイドバーの現在値で分析パラメータを同期 ---
# シミュレーション実行時に保存された sim_params は再実行まで更新されないため、
# LOS最適化・限界価値分析など「パラメータのみで計算する分析関数」には
# スライダーの最新値を反映させる。
if _active_cli_params:
    _current_sidebar_params = _build_cli_params(params_dict)
    _active_cli_params = _active_cli_params.copy()
    for _sync_key in (
        "monthly_admissions", "avg_length_of_stay", "days_in_month",
        "phase_a_revenue", "phase_a_cost", "phase_b_revenue", "phase_b_cost",
        "phase_c_revenue", "phase_c_cost", "opportunity_cost",
        "first_day_bonus", "within_14days_bonus", "rehab_fee",
    ):
        _active_cli_params[_sync_key] = _current_sidebar_params[_sync_key]

# ===== タブ1: 日次推移 =====
with tabs[_tab_idx["📊 日次推移"]]:
    st.subheader("日次推移")
    if _is_actual_data_mode:
        st.info(f"📋 実績データモード（{len(df)}日分のデータを表示中）")
    if _selected_ward_key != "全体":
        st.caption(f"📍 {_selected_ward_key} ({_view_beds}床) のデータを表示中")
    if not _is_actual_data_mode and _selected_ward_key != "全体":
        if isinstance(_active_raw_df, pd.DataFrame) and len(_active_raw_df) > 0:
            _render_ward_kpi_with_alert(_active_raw_df, target_lower, target_upper, _view_beds)
    if _is_actual_data_mode:
        if _selected_ward_key != "全体":
            if isinstance(_active_raw_df, pd.DataFrame) and len(_active_raw_df) > 0:
                _render_ward_kpi_with_alert(_active_raw_df, target_lower, target_upper, _view_beds)
        if _selected_ward_key == "全体" and isinstance(_active_raw_df, pd.DataFrame) and len(_active_raw_df) > 0:
            _occ_key = "occupancy_rate" if "occupancy_rate" in _active_raw_df.columns else "稼働率"
            _tp_key = "total_patients" if "total_patients" in _active_raw_df.columns else "在院患者数"
            _total_last_occ_val = _active_raw_df.iloc[-1].get(_occ_key, 0)
            _total_last_occ = float(_total_last_occ_val) * 100 if pd.notna(_total_last_occ_val) else 0.0
            if _total_last_occ < target_lower * 100:
                _total_tp_val = _active_raw_df.iloc[-1].get(_tp_key, 0)
                _total_empty = _view_beds - (int(_total_tp_val) if pd.notna(_total_tp_val) else 0)
                _remaining_days = _calc_remaining_days(_active_raw_df) if isinstance(_active_raw_df, pd.DataFrame) and len(_active_raw_df) > 0 else 0
                st.error(
                    f"🔴 **全体稼働率低下**: {_total_last_occ:.1f}% が目標下限{target_lower*100:.0f}%未満 "
                    f"（空床{_total_empty}床 = 未活用病床コスト 約{_total_empty * 34000 // 10000:.0f}万円/日・**今月残り{_remaining_days}日で約{_total_empty * 34000 * _remaining_days // 10000:.0f}万円**）\n\n"
                    "**対策:** ① 外来へ予定入院の前倒しを依頼 ② 連携室へ紹介元への空床発信を依頼 ③ 外来担当医に入院閾値の引き下げを相談 + C群の戦略的在院調整で稼働率維持"
                )
        if _ward_data_available:
            _render_comparison_strip(_selected_ward_key, _ward_raw_dfs, _ward_display_dfs, get_ward_beds)
    if _HELP_AVAILABLE and "tab_daily" in HELP_TEXTS:
        with st.expander("📖 このタブの見方と活用法"):
            st.markdown(HELP_TEXTS["tab_daily"])

    # --- 曜日ラベル生成 ---
    _weekday_names = ["月", "火", "水", "木", "金", "土", "日"]
    _day_weekdays = []
    if "日付" in df.columns:
        for _d in df["日付"]:
            try:
                _day_weekdays.append(pd.Timestamp(_d).weekday())
            except Exception:
                _day_weekdays.append((int(df[df["日付"] == _d]["日"].iloc[0]) - 1) % 7)
    else:
        _day_weekdays = [(d - 1) % 7 for d in df["日"]]
    _weekend_days = [df["日"].iloc[i] for i in range(len(df)) if _day_weekdays[i] >= 5]

    def _add_weekend_bg(ax_obj, weekend_list):
        """土日をグレー背景で強調するヘルパー"""
        for _wd in weekend_list:
            ax_obj.axvspan(_wd - 0.5, _wd + 0.5, alpha=0.08, color="gray")

    def _set_weekday_ticks(ax_obj, day_series, weekday_list):
        """曜日ラベル付き目盛りを設定するヘルパー"""
        _tpos = list(day_series)
        _tlbl = [f"{d}\n{_weekday_names[weekday_list[i]]}" for i, d in enumerate(_tpos)]
        if len(_tpos) > 15:
            _step = max(1, len(_tpos) // 15)
            _show = list(range(0, len(_tpos), _step))
            ax_obj.set_xticks([_tpos[j] for j in _show])
            ax_obj.set_xticklabels([_tlbl[j] for j in _show], fontsize=8)
        else:
            ax_obj.set_xticks(_tpos)
            ax_obj.set_xticklabels(_tlbl, fontsize=8)

    # --- 稼働率推移 ---
    fig, ax = plt.subplots(figsize=(12, 4))
    _add_weekend_bg(ax, _weekend_days)
    ax.plot(df["日"], df["稼働率"] * 100, color="#2C3E50", linewidth=2, label="稼働率")
    ax.axhspan(
        target_lower * 100, target_upper * 100,
        alpha=0.15, color="#F39C12", label=f"目標レンジ ({target_lower*100:.0f}-{target_upper*100:.0f}%)"
    )
    ax.set_xlabel("日")
    ax.set_ylabel("稼働率 (%)")
    ax.set_title("稼働率推移（グレー背景=土日）")
    _set_weekday_ticks(ax, df["日"], _day_weekdays)
    ax.legend(loc="lower right")
    ax.set_xlim(1, days_in_month)
    ax.grid(True, alpha=0.3)

    # --- 月平均目標達成ライン（点線）---
    # _active_raw_df と df の両方で試行（カラム名の違いに対応）
    _mt_chart = None
    for _mt_src_df in [_active_raw_df, df]:
        if _mt_chart is None and isinstance(_mt_src_df, pd.DataFrame) and len(_mt_src_df) > 0:
            _mt_chart = _calc_monthly_target(_mt_src_df, target_lower, 31, _view_beds)
    if _mt_chart and _mt_chart["days_remaining"] > 0 and _mt_chart["avg_so_far"] < _mt_chart["monthly_target_pct"]:
        _chart_last_day = len(df["稼働率"])  # データの最終日番号
        _chart_end_day = _mt_chart["total_days"]  # 月末日番号
        _required_occ_pct = _mt_chart["required_occ"]
        _occ_pct_values = (df["稼働率"] * 100).tolist()

        # 最終日の実績値から必要稼働率への点線
        _target_x = [_chart_last_day, _chart_last_day + 1, _chart_end_day]
        _target_y = [_occ_pct_values[-1], _required_occ_pct, _required_occ_pct]

        # 目標ラインの色を難易度で変更
        _target_color = "#FF4444" if _mt_chart["difficulty"] in ("hard", "impossible") else "#FF8800"

        ax.plot(_target_x, _target_y,
                linestyle="--", linewidth=2.5, color=_target_color,
                marker="", zorder=5)

        # 必要稼働率のラベル
        ax.annotate(
            f'目標達成に必要\n{_required_occ_pct:.1f}%',
            xy=(_chart_end_day - 2, _required_occ_pct),
            fontsize=10, fontweight="bold", color=_target_color,
            ha="right", va="bottom",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=_target_color, alpha=0.9),
        )

        # X軸の範囲を月末まで拡張
        ax.set_xlim(1, _chart_end_day + 0.5)

        # 月平均の水平線（現在の平均）
        ax.axhline(y=_mt_chart["avg_so_far"], color="gray", linestyle=":", linewidth=1, alpha=0.7)
        ax.annotate(
            f'月平均 {_mt_chart["avg_so_far"]:.1f}%',
            xy=(2, _mt_chart["avg_so_far"]),
            fontsize=9, color="gray", va="bottom",
        )

    st.pyplot(fig)
    plt.close(fig)

    # 病棟別稼働率は病棟セレクターで切り替え（比較ストリップで他病棟を表示）

    # --- 在院患者数推移 ---
    col1, col2 = st.columns(2)
    with col1:
        fig, ax = plt.subplots(figsize=(6, 3.5))
        _add_weekend_bg(ax, _weekend_days)
        ax.plot(df["日"], df["在院患者数"], color="#8E44AD", linewidth=2)
        ax.axhline(y=_view_beds, color="#E74C3C", linestyle="--", alpha=0.5, label=f"病床数({_view_beds})")
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
        _add_weekend_bg(ax, _weekend_days)
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

    # 病棟別在院患者数は病棟セレクターで切り替え

    # --- 日次運営貢献額推移 ---
    fig, ax = plt.subplots(figsize=(12, 4))
    _add_weekend_bg(ax, _weekend_days)
    colors_profit = [COLOR_PROFIT if v >= 0 else COLOR_A for v in df["日次運営貢献額"]]
    ax.bar(df["日"], df["日次運営貢献額"] / 10000, color=colors_profit, alpha=0.8)
    ax.axhline(y=0, color="black", linewidth=0.5)
    ax.set_xlabel("日")
    ax.set_ylabel("運営貢献額（万円）")
    ax.set_title("日次運営貢献額推移")
    ax.set_xlim(0.5, days_in_month + 0.5)
    ax.grid(True, alpha=0.3, axis="y")
    st.pyplot(fig)
    plt.close(fig)

    # --- 今週のハイライト ---
    st.markdown("---")
    st.subheader("📌 今月のハイライト")
    _occ_pct = df["稼働率"] * 100
    _min_occ_idx = _occ_pct.idxmin()
    _max_occ_idx = _occ_pct.idxmax()
    _max_discharge_idx = df["退院"].idxmax()
    _hl_c1, _hl_c2, _hl_c3 = st.columns(3)
    with _hl_c1:
        _min_day = int(df.loc[_min_occ_idx, "日"])
        _min_wd = _weekday_names[_day_weekdays[_min_occ_idx]] if _min_occ_idx < len(_day_weekdays) else ""
        st.metric(
            f"稼働率最低日（{_min_day}日・{_min_wd}）",
            f"{_occ_pct.iloc[_min_occ_idx]:.1f}%",
        )
    with _hl_c2:
        _max_day = int(df.loc[_max_occ_idx, "日"])
        _max_wd = _weekday_names[_day_weekdays[_max_occ_idx]] if _max_occ_idx < len(_day_weekdays) else ""
        st.metric(
            f"稼働率最高日（{_max_day}日・{_max_wd}）",
            f"{_occ_pct.iloc[_max_occ_idx]:.1f}%",
        )
    with _hl_c3:
        _dc_day = int(df.loc[_max_discharge_idx, "日"])
        _dc_wd = _weekday_names[_day_weekdays[_max_discharge_idx]] if _max_discharge_idx < len(_day_weekdays) else ""
        st.metric(
            f"最大退院日（{_dc_day}日・{_dc_wd}）",
            f"{int(df.loc[_max_discharge_idx, '退院'])}名",
        )


# ===== タブ2: フェーズ構成 =====
with tabs[_tab_idx["🔄 フェーズ構成"]]:
    st.subheader("フェーズ構成")
    if _selected_ward_key != "全体":
        st.caption(f"📍 {_selected_ward_key} ({_view_beds}床) のデータを表示中")
    if not _is_actual_data_mode and _selected_ward_key != "全体":
        if isinstance(_active_raw_df, pd.DataFrame) and len(_active_raw_df) > 0:
            _render_ward_kpi_with_alert(_active_raw_df, target_lower, target_upper, _view_beds)
    if _is_actual_data_mode:
        if _selected_ward_key != "全体":
            if isinstance(_active_raw_df, pd.DataFrame) and len(_active_raw_df) > 0:
                _render_ward_kpi_with_alert(_active_raw_df, target_lower, target_upper, _view_beds)
        if _ward_data_available:
            _render_comparison_strip(_selected_ward_key, _ward_raw_dfs, _ward_display_dfs, get_ward_beds)

    # --- A/B/C群の定義パネル（常時表示、折りたたみではない） ---
    st.markdown("---")
    _col_a, _col_b, _col_c = st.columns(3)
    with _col_a:
        st.markdown("""
        <div style="background-color:#FDEDEC; padding:12px; border-radius:8px; border-left:4px solid #E74C3C;">
        <h4 style="color:#E74C3C; margin:0;">🔴 A群（急性期）</h4>
        <p style="margin:4px 0;"><b>入院1〜5日目</b></p>
        <p style="margin:4px 0; font-size:0.9em;">
        検査・処置・初期治療が集中<br>
        看護必要度が最も高い<br>
        初期加算(150点)+リハ栄養口腔連携(110点)+物価対応(49点)算定<br>
        <b>収入36,000円 / 変動費12,000円</b><br>
        <span style="color:#E74C3C;"><b>運営貢献額24,000円/日（約2.4万円/日）</b></span>
        </p>
        <p style="margin:4px 0; font-size:0.85em; color:#666;">
        💡 多すぎると初期変動費で運営貢献額圧迫<br>
        目安：全体の15〜20%
        </p>
        </div>
        """, unsafe_allow_html=True)
    with _col_b:
        st.markdown("""
        <div style="background-color:#EAFAF1; padding:12px; border-radius:8px; border-left:4px solid #27AE60;">
        <h4 style="color:#27AE60; margin:0;">🟢 B群（回復期）</h4>
        <p style="margin:4px 0;"><b>入院6〜14日目</b></p>
        <p style="margin:4px 0; font-size:0.9em;">
        リハビリ・回復・退院準備<br>
        コストが下がり始める<br>
        初期加算(150点)+リハ栄養口腔連携(110点)+物価対応(49点)算定<br>
        <b>収入36,000円 / 変動費6,000円</b><br>
        <span style="color:#27AE60;"><b>運営貢献額30,000円/日（約3.0万円/日・★安定貢献層）</b></span>
        </p>
        <p style="margin:4px 0; font-size:0.85em; color:#666;">
        💡 この層を厚くすることが運営貢献額の最大化の鍵<br>
        目安：全体の40〜50%
        </p>
        </div>
        """, unsafe_allow_html=True)
    with _col_c:
        st.markdown("""
        <div style="background-color:#EBF5FB; padding:12px; border-radius:8px; border-left:4px solid #2980B9;">
        <h4 style="color:#2980B9; margin:0;">🔵 C群（退院準備期）</h4>
        <p style="margin:4px 0;"><b>入院15日目以降</b></p>
        <p style="margin:4px 0; font-size:0.9em;">
        退院調整・転院待ち・在宅準備<br>
        コスト最小だが長期滞留リスク<br>
        物価対応(49点)のみ算定<br>
        <b>収入33,400円 / 変動費4,500円</b><br>
        <span style="color:#2980B9;"><b>運営貢献額28,900円/日（約2.9万円/日・良好だが要調整）</b></span>
        </p>
        <p style="margin:4px 0; font-size:0.85em; color:#666;">
        💡 退院調整の柔軟性が高い層。稼働率維持に活用<br>
        ※14日超で初期加算(1,500円)+リハ栄養口腔連携加算(1,100円)消失<br>
        目安：全体の30〜40%
        </p>
        </div>
        """, unsafe_allow_html=True)
    st.markdown("---")

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
        if sum(sizes) > 0:
            ax.pie(
                sizes, labels=labels, colors=[COLOR_A, COLOR_B, COLOR_C],
                autopct=None, startangle=90, textprops={"fontsize": 10},
            )
        else:
            ax.text(0.5, 0.5, "フェーズデータなし", ha="center", va="center",
                    fontsize=12, transform=ax.transAxes)
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

    # --- 理想構成比との比較 ---
    st.markdown("---")
    st.subheader("📐 理想構成比との比較")
    _ideal = {"A群": 15, "B群": 45, "C群": 40}
    _actual_phase = {
        "A群": summary["A群平均構成比"],
        "B群": summary["B群平均構成比"],
        "C群": summary["C群平均構成比"],
    }
    fig, ax = plt.subplots(figsize=(8, 4))
    _phase_labels = list(_ideal.keys())
    _x_pos = np.arange(len(_phase_labels))
    _bar_w = 0.35
    _bars_ideal = ax.bar(_x_pos - _bar_w/2, [_ideal[k] for k in _phase_labels], _bar_w,
                          label="理想", color=["#F5B7B1", "#ABEBC6", "#AED6F1"], edgecolor="gray", linewidth=0.5)
    _bars_actual = ax.bar(_x_pos + _bar_w/2, [_actual_phase[k] for k in _phase_labels], _bar_w,
                           label="実績", color=[COLOR_A, COLOR_B, COLOR_C], alpha=0.85)
    ax.set_ylabel("構成比 (%)")
    ax.set_title("理想 vs 実績 フェーズ構成比")
    ax.set_xticks(_x_pos)
    ax.set_xticklabels(_phase_labels)
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")
    # 値ラベル
    for _bar in _bars_ideal:
        _h = _bar.get_height()
        ax.text(_bar.get_x() + _bar.get_width()/2, _h + 0.5, f"{_h:.0f}%", ha="center", fontsize=9, color="gray")
    for _bar in _bars_actual:
        _h = _bar.get_height()
        ax.text(_bar.get_x() + _bar.get_width()/2, _h + 0.5, f"{_h:.1f}%", ha="center", fontsize=9)
    st.pyplot(fig)
    plt.close(fig)

    # 乖離の一文解説
    _b_diff = _actual_phase["B群"] - _ideal["B群"]
    if _b_diff >= 0:
        st.success(f"B群（安定貢献層）は理想比率を **+{_b_diff:.1f}%** 上回っています。良好な状態です。")
    elif _b_diff > -5:
        st.warning(f"B群（安定貢献層）は理想比率を **{_b_diff:.1f}%** 下回っています。やや注意が必要です。")
    else:
        st.error(f"B群（安定貢献層）は理想比率を **{_b_diff:.1f}%** 下回っています。退院・入院バランスの見直しが急務です。")

    # 病棟別フェーズ構成は病棟セレクターで切り替え（比較ストリップで他病棟を表示）


# ===== タブ3: 運営分析 =====
with tabs[_tab_idx["💰 運営分析"]]:
    st.subheader("運営分析")
    if _selected_ward_key != "全体":
        st.caption(f"📍 {_selected_ward_key} ({_view_beds}床) のデータを表示中")
    if not _is_actual_data_mode and _selected_ward_key != "全体":
        if isinstance(_active_raw_df, pd.DataFrame) and len(_active_raw_df) > 0:
            _render_ward_kpi_with_alert(_active_raw_df, target_lower, target_upper, _view_beds)
    if _is_actual_data_mode:
        if _selected_ward_key != "全体":
            if isinstance(_active_raw_df, pd.DataFrame) and len(_active_raw_df) > 0:
                _render_ward_kpi_with_alert(_active_raw_df, target_lower, target_upper, _view_beds)
        if _ward_data_available:
            _render_comparison_strip(_selected_ward_key, _ward_raw_dfs, _ward_display_dfs, get_ward_beds)
    if _HELP_AVAILABLE and "tab_finance" in HELP_TEXTS:
        with st.expander("📖 このタブの見方と活用法"):
            st.markdown(HELP_TEXTS["tab_finance"])

    # --- 月次目標達成率パネル（稼働率90%ラインベース） ---
    _target_occ_line = target_lower  # 0.90
    # 稼働率90%時の月次診療報酬目標 = 病床数 × 90% × 日数 × 加重平均日次報酬（約28,000円）
    _weighted_daily_rev = 28000  # A/B/C群の加重平均運営貢献額
    _target_monthly_rev = _view_beds * _target_occ_line * days_in_month * _weighted_daily_rev
    _actual_monthly_rev = summary["月次運営貢献額"]
    _achievement_rate = (_actual_monthly_rev / _target_monthly_rev * 100) if _target_monthly_rev > 0 else 0
    _actual_avg_occ = summary["平均稼働率"]

    # 色分け
    if _achievement_rate >= 100:
        _ach_bg = "#EAFAF1"; _ach_border = "#27AE60"; _ach_icon = "✅"; _ach_msg = "目標達成"
    elif _achievement_rate >= 80:
        _ach_bg = "#FEF9E7"; _ach_border = "#F39C12"; _ach_icon = "⚠️"; _ach_msg = "あと少し"
    else:
        _ach_bg = "#FDEDEC"; _ach_border = "#E74C3C"; _ach_icon = "🔴"; _ach_msg = "要改善"

    # 稼働率の色分け
    if _actual_avg_occ < _target_occ_line * 100:
        _occ_color = "#E74C3C"
    elif _actual_avg_occ <= target_upper * 100:
        _occ_color = "#27AE60"
    else:
        _occ_color = "#F39C12"

    st.markdown(f"""
<div style="background:{_ach_bg}; padding:16px 20px; border-radius:10px; border-left:5px solid {_ach_border}; margin-bottom:16px;">
<div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap;">
<div>
<h3 style="margin:0; color:{_ach_border};">{_ach_icon} 月次目標達成率: {_achievement_rate:.1f}%　<span style="font-size:0.7em; color:#666;">（{_ach_msg}）</span></h3>
<p style="margin:4px 0 0 0; font-size:0.9em; color:#555;">
稼働率最低ライン（{_target_occ_line*100:.0f}%）ベースの月次運営貢献額目標: <b>{_target_monthly_rev/10000:,.0f}万円</b>
｜ 実績: <b>{_actual_monthly_rev/10000:,.0f}万円</b>
</p>
</div>
<div style="text-align:center; padding:4px 16px;">
<p style="margin:0; font-size:0.8em; color:#888;">平均稼働率</p>
<p style="margin:0; font-size:1.6em; font-weight:bold; color:{_occ_color};">{_actual_avg_occ:.1f}%</p>
<p style="margin:0; font-size:0.75em; color:#888;">目標: {_target_occ_line*100:.0f}〜{target_upper*100:.0f}%</p>
</div>
</div>
</div>
""", unsafe_allow_html=True)

    # --- メトリクスカード ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("月次診療報酬", fmt_yen(summary["月次診療報酬"]))
    c2.metric("月次コスト", fmt_yen(summary["月次コスト"]))
    c3.metric("月次運営貢献額", fmt_yen(summary["月次運営貢献額"]))
    c4.metric("平均稼働率", f"{summary['平均稼働率']:.1f}%")

    c5, c6, c7, c8, c9 = st.columns(5)
    c5.metric("月間入院数", f"{summary['月間入院数']}人")
    c6.metric("月間退院数", f"{summary['月間退院数']}人")
    c7.metric("目標レンジ内日数", f"{summary['目標レンジ内日数']}/{days_in_month}日")
    c8.metric("目標レンジ内率", f"{summary['目標レンジ内率']}%")
    c9.metric("平均在院日数", f"{summary['平均在院日数']}日",
              help="厚労省公式: 在院患者延日数 ÷ ((新入院患者数 + 退院患者数) ÷ 2)")
    st.caption("※ 平均在院日数は厚生労働省「病院報告」の公式定義に準拠")

    # --- 日次診療報酬・コスト・運営貢献額 ---
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(df["日"], df["日次診療報酬"] / 10000, color=COLOR_REVENUE, linewidth=2, label="診療報酬収入")
    ax.plot(df["日"], df["日次コスト"] / 10000, color=COLOR_COST, linewidth=2, label="コスト")
    ax.plot(df["日"], df["日次運営貢献額"] / 10000, color=COLOR_PROFIT, linewidth=2, label="運営貢献額")
    ax.axhline(y=0, color="black", linewidth=0.5)
    ax.set_xlabel("日")
    ax.set_ylabel("金額（万円）")
    ax.set_title("日次診療報酬・コスト・運営貢献額推移")
    ax.legend()
    ax.set_xlim(1, days_in_month)
    ax.grid(True, alpha=0.3)
    st.pyplot(fig)
    plt.close(fig)

    # --- 累積運営貢献額推移 ---
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.fill_between(
        df["日"], df["累積運営貢献額"] / 10000, 0,
        where=df["累積運営貢献額"] >= 0, color=COLOR_PROFIT, alpha=0.3,
    )
    ax.fill_between(
        df["日"], df["累積運営貢献額"] / 10000, 0,
        where=df["累積運営貢献額"] < 0, color=COLOR_A, alpha=0.3,
    )
    ax.plot(df["日"], df["累積運営貢献額"] / 10000, color=COLOR_PROFIT, linewidth=2)
    ax.axhline(y=0, color="black", linewidth=0.5)
    ax.set_xlabel("日")
    ax.set_ylabel("累積運営貢献額（万円）")
    ax.set_title("累積運営貢献額推移")
    ax.set_xlim(1, days_in_month)
    ax.grid(True, alpha=0.3)
    st.pyplot(fig)
    plt.close(fig)

    # --- フェーズ別運営貢献額の内訳 ---
    st.markdown("---")
    st.subheader("📊 フェーズ別運営貢献額の内訳")
    # 運営貢献額単価（変動費のみ）: A=24000, B=30000, C=28900
    _profit_per_day = {
        "A群": _active_cli_params.get("phase_a_revenue", 36000) - _active_cli_params.get("phase_a_cost", 12000),
        "B群": _active_cli_params.get("phase_b_revenue", 36000) - _active_cli_params.get("phase_b_cost", 6000),
        "C群": _active_cli_params.get("phase_c_revenue", 33400) - _active_cli_params.get("phase_c_cost", 4500),
    }
    _phase_profit_a = (df["A群_患者数"] * _profit_per_day["A群"]).sum()
    _phase_profit_b = (df["B群_患者数"] * _profit_per_day["B群"]).sum()
    _phase_profit_c = (df["C群_患者数"] * _profit_per_day["C群"]).sum()
    _phase_profit_total = _phase_profit_a + _phase_profit_b + _phase_profit_c

    _fp_c1, _fp_c2, _fp_c3 = st.columns(3)
    with _fp_c1:
        _pct_a = (_phase_profit_a / _phase_profit_total * 100) if _phase_profit_total > 0 else 0
        st.markdown(
            f'<div style="background-color:#FDEDEC; padding:10px; border-radius:8px; text-align:center;">'
            f'<b style="color:#E74C3C;">A群の運営貢献額</b><br>'
            f'<span style="font-size:1.3em;">{_phase_profit_a/10000:,.0f}万円</span><br>'
            f'<span style="font-size:0.9em;">全体の {_pct_a:.1f}%</span></div>',
            unsafe_allow_html=True,
        )
    with _fp_c2:
        _pct_b = (_phase_profit_b / _phase_profit_total * 100) if _phase_profit_total > 0 else 0
        st.markdown(
            f'<div style="background-color:#EAFAF1; padding:10px; border-radius:8px; text-align:center;">'
            f'<b style="color:#27AE60;">B群の運営貢献額</b><br>'
            f'<span style="font-size:1.3em;">{_phase_profit_b/10000:,.0f}万円</span><br>'
            f'<span style="font-size:0.9em;">全体の {_pct_b:.1f}%</span></div>',
            unsafe_allow_html=True,
        )
    with _fp_c3:
        _pct_c = (_phase_profit_c / _phase_profit_total * 100) if _phase_profit_total > 0 else 0
        st.markdown(
            f'<div style="background-color:#EBF5FB; padding:10px; border-radius:8px; text-align:center;">'
            f'<b style="color:#2980B9;">C群の運営貢献額</b><br>'
            f'<span style="font-size:1.3em;">{_phase_profit_c/10000:,.0f}万円</span><br>'
            f'<span style="font-size:0.9em;">全体の {_pct_c:.1f}%</span></div>',
            unsafe_allow_html=True,
        )

    # 運営貢献額のどこが効いているかの一文解説
    _max_phase = max([("A群", _pct_a), ("B群", _pct_b), ("C群", _pct_c)], key=lambda x: x[1])
    _phase_desc = {"A群": "A群（急性期）", "B群": "B群（回復期）", "C群": "C群（退院準備期）"}
    st.info(f"💡 今月の運営貢献額の **{_max_phase[1]:.0f}%** は **{_phase_desc[_max_phase[0]]}** が生み出しています。")

    # 病棟別収支は病棟セレクターで切り替え（比較ストリップで他病棟を表示）


# ===== タブ4: 運営改善アラート =====
with tabs[_tab_idx["🚨 運営改善アラート"]]:
    st.subheader("運営改善アラート")
    if _selected_ward_key != "全体":
        st.caption(f"📍 {_selected_ward_key} ({_view_beds}床) のデータを表示中")
    if not _is_actual_data_mode and _selected_ward_key != "全体":
        if isinstance(_active_raw_df, pd.DataFrame) and len(_active_raw_df) > 0:
            _render_ward_kpi_with_alert(_active_raw_df, target_lower, target_upper, _view_beds)
    if _is_actual_data_mode:
        if _selected_ward_key != "全体":
            if isinstance(_active_raw_df, pd.DataFrame) and len(_active_raw_df) > 0:
                _render_ward_kpi_with_alert(_active_raw_df, target_lower, target_upper, _view_beds)
        if _selected_ward_key == "全体" and isinstance(_active_raw_df, pd.DataFrame) and len(_active_raw_df) > 0:
            _occ_key = "occupancy_rate" if "occupancy_rate" in _active_raw_df.columns else "稼働率"
            _tp_key = "total_patients" if "total_patients" in _active_raw_df.columns else "在院患者数"
            _total_last_occ_val = _active_raw_df.iloc[-1].get(_occ_key, 0)
            _total_last_occ = float(_total_last_occ_val) * 100 if pd.notna(_total_last_occ_val) else 0.0
            if _total_last_occ < target_lower * 100:
                _total_tp_val = _active_raw_df.iloc[-1].get(_tp_key, 0)
                _total_empty = _view_beds - (int(_total_tp_val) if pd.notna(_total_tp_val) else 0)
                _remaining_days = _calc_remaining_days(_active_raw_df) if isinstance(_active_raw_df, pd.DataFrame) and len(_active_raw_df) > 0 else 0
                st.error(
                    f"🔴 **全体稼働率低下**: {_total_last_occ:.1f}% が目標下限{target_lower*100:.0f}%未満 "
                    f"（空床{_total_empty}床 = 未活用病床コスト 約{_total_empty * 34000 // 10000:.0f}万円/日・**今月残り{_remaining_days}日で約{_total_empty * 34000 * _remaining_days // 10000:.0f}万円**）\n\n"
                    "**対策:** ① 外来へ予定入院の前倒しを依頼 ② 連携室へ紹介元への空床発信を依頼 ③ 外来担当医に入院閾値の引き下げを相談 + C群の戦略的在院調整で稼働率維持"
                )
        if _ward_data_available:
            _render_comparison_strip(_selected_ward_key, _ward_raw_dfs, _ward_display_dfs, get_ward_beds)
    if _HELP_AVAILABLE and "tab_flags" in HELP_TEXTS:
        with st.expander("📖 このタブの見方と活用法"):
            st.markdown(HELP_TEXTS["tab_flags"])

    # --- フラグ一覧テーブル ---
    flag_df = df[["日", "稼働率", "在院患者数", "運営改善アラート"]].copy()
    flag_df["稼働率"] = (flag_df["稼働率"] * 100).round(1).astype(str) + "%"

    def highlight_flags(row):
        """フラグに基づき行の背景色を設定"""
        flags = row["運営改善アラート"]
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
    st.dataframe(styled, width="stretch", height=400)

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

    # --- ベッドコントロール優先原則 ---
    st.markdown("---")
    st.subheader("ベッドコントロール優先原則")
    st.info(
        "**📌 判断の優先順位（看護必要度基準を満たす前提で）**\n\n"
        "1️⃣ **稼働率レンジ（90-95%）を維持する** — 空床は診療報酬収入ゼロ、1床/日≈2.5万円の未活用病床コスト\n\n"
        "2️⃣ **平均在院日数21日以内で戦略的在院調整を活用** — C群でも運営貢献額28,900円/日を生む\n\n"
        "3️⃣ **運営貢献額を減らさない** — 退院させて空床を出すより、平均在院日数の最適化で稼働率を維持\n\n"
        "⚠️ 退院を急ぐべきは「満床で新規入院を断らざるを得ない場合」のみ"
    )

    # --- 推奨アクション ---
    st.markdown("---")
    st.subheader("推奨アクション")
    avg_occ = summary["平均稼働率"]
    if avg_occ < target_lower * 100:
        st.error(
            f"⚠️ 平均稼働率 {avg_occ:.1f}% が目標下限 {target_lower*100:.0f}% を下回っています。\n\n"
            "**最優先:** 入院促進策の強化\n"
            "- ① 予定入院の前倒しを外来担当医へ依頼\n"
            "- ② 連携室へ依頼：紹介元クリニック・病院へ空床受入れ可能を発信\n"
            "- ③ 外来担当医に入院推奨閾値の引き下げを相談\n\n"
            "**注意:** C群患者は在院継続で運営貢献額確保。空床1床/日 ≈ 2.5万円の未活用病床コスト。"
            "平均在院日数21日以内であれば戦略的在院調整で稼働率を維持する。"
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
        if avg_occ >= target_upper * 100:
            st.warning(
                f"C群構成比 {summary['C群平均構成比']:.1f}% が高く、稼働率も{avg_occ:.1f}%で高稼働。\n\n"
                "**推奨:** 退院可能なC群から優先的に退院調整し、受入枠を確保。外来・連携室へ空床状況を共有"
            )
        else:
            st.info(
                f"C群構成比 {summary['C群平均構成比']:.1f}% は高めですが、稼働率{avg_occ:.1f}%で余裕あり。\n\n"
                "**判断:** 平均在院日数21日以内ならC群の戦略的在院調整で稼働率維持を優先。"
                "在院継続で運営貢献額28,900円/日を確保。"
            )

    # --- 今日のアクションリスト ---
    st.markdown("---")
    st.subheader("📋 今日のアクションリスト")
    _last_row = df.iloc[-1]
    _last_flags = _last_row.get("運営改善アラート", "正常運用")
    _last_occ = _last_row["稼働率"] * 100
    _last_patients = int(_last_row["在院患者数"])
    _last_empty = _view_beds - _last_patients
    _last_c = int(_last_row["C群_患者数"]) if "C群_患者数" in df.columns else 0
    _last_a = int(_last_row["A群_患者数"]) if "A群_患者数" in df.columns else 0
    _last_b = int(_last_row["B群_患者数"]) if "B群_患者数" in df.columns else 0

    _action_items = []
    if "C群滞留" in _last_flags or _last_c > _last_patients * 0.4:
        if _last_occ >= target_upper * 100:
            # 満床に近い場合のみ退院調整を推奨
            _discharge_target = max(1, int(_last_c * 0.1))
            _action_items.append(f"⚠️ 高稼働のためC群から{_discharge_target}名の退院調整を検討（稼働率{_last_occ:.1f}%）")
        else:
            # 稼働率に余裕がある場合はC群の戦略的在院調整を推奨
            _action_items.append(f"C群{_last_c}名は戦略的在院調整で稼働率維持（運営貢献額28,900円/日/名 × 空床よりプラス）")
    if "稼働率低下" in _last_flags:
        _remaining_days = _calc_remaining_days(_active_raw_df)
        _action_items.append(f"🔴 空床{_last_empty}床（未活用病床コスト 約{_last_empty * 34000 // 10000:.0f}万円/日・今月残り{_remaining_days}日で約{_last_empty * 34000 * _remaining_days // 10000:.0f}万円）→ 外来へ予定入院前倒し依頼 / 連携室へ紹介元への空床発信依頼 / 外来担当医へ入院閾値引き下げ相談")
        _action_items.append("🔴 C群患者の戦略的在院調整 — 在院継続で運営貢献額確保し稼働率維持を優先")
    if "稼働率超過" in _last_flags:
        _action_items.append(f"退院調整を優先（在院{_last_patients}名、稼働率{_last_occ:.1f}%）")
    if "A群過多" in _last_flags:
        _action_items.append("A群の新規入院ペースを確認（数日でB群に移行予定）")
    if "B群不足" in _last_flags:
        _action_items.append("B群患者のリハビリ進捗を確認、在院継続で運営貢献額確保")
    if _last_empty > 0 and "正常運用" in _last_flags:
        _action_items.append(f"空床{_last_empty}床（受入余力{min(5, _last_empty)}名）→ 外来・連携室へ空床状況を共有し入院受入を促進")
    if _last_b > 0:
        _action_items.append(f"B群{_last_b}名のリハビリ進捗・退院準備状況を確認")

    if _action_items:
        for _item in _action_items:
            st.checkbox(_item, value=False, key=f"action_{hash(_item)}")
    else:
        st.success("特別なアクションは不要です。現行運用を維持してください。")

    # 病棟別フラグは病棟セレクターで切り替え（比較ストリップで他病棟を表示）


# ===== タブ5-7: 意思決定支援タブ =====
# --- タブ5: 意思決定ダッシュボード ---
with tabs[_tab_idx["\U0001f3af 意思決定ダッシュボード"]]:
    if not _DECISION_SUPPORT_AVAILABLE:
        st.error("意思決定支援機能はまだ利用できません。CLI版（bed_control_simulator.py）に必要な関数が実装されていません。")
        if "_DECISION_SUPPORT_ERROR" in dir():
            st.code(_DECISION_SUPPORT_ERROR)
    else:
        st.subheader("\U0001f3af 意思決定ダッシュボード")
        if _HELP_AVAILABLE and "tab_decision" in HELP_TEXTS:
            with st.expander("📖 このタブの見方と活用法"):
                st.markdown(HELP_TEXTS["tab_decision"])

        # 安全チェック: _active_raw_dfが有効でない場合は処理をスキップ
        if not isinstance(_active_raw_df, pd.DataFrame) or len(_active_raw_df) == 0:
            st.error("意思決定分析に必要なデータがありません。実績データを入力するかシミュレーションを実行してください。")
        else:
            _raw_df = _active_raw_df
            _cli_params = _active_cli_params

            # --- 病棟状態カード ---
            _day_idx = len(_raw_df) - 1  # 最終日を評価対象
            _ward_status = assess_ward_status(_raw_df, _day_idx, _cli_params)

        # --- 稼働率予測（ブリーフィングでも使うので先に計算） ---
        _forecast = predict_occupancy(_raw_df, _day_idx, _cli_params, horizon=5)
        _actions = suggest_actions(_ward_status, _forecast, _cli_params)

        # --- 🌅 朝のブリーフィング ---
        _br_score_numeric = _ward_status.get("score_numeric", 0)
        _br_score_label = _ward_status.get("score", "unknown")
        _br_score_ja = {"healthy": "健全", "caution": "注意", "warning": "警告", "critical": "危機"}.get(_br_score_label, _br_score_label)
        _br_occ = _ward_status.get("occupancy_rate", 0) * 100
        _br_last_row = _raw_df.iloc[_day_idx]
        _br_patients = int(_br_last_row.get("total_patients", round(_br_occ / 100 * _view_beds)))
        _br_empty = _view_beds - _br_patients
        _br_pct_a = _ward_status.get("phase_a_ratio", 0) * 100
        _br_pct_b = _ward_status.get("phase_b_ratio", 0) * 100
        _br_pct_c = _ward_status.get("phase_c_ratio", 0) * 100
        _br_phase_a = int(round(_br_patients * _br_pct_a / 100))
        _br_phase_b = int(round(_br_patients * _br_pct_b / 100))
        _br_phase_c = _br_patients - _br_phase_a - _br_phase_b

        # 優先アクション（上位2件）
        _br_top_actions = sorted(_actions, key=lambda a: a.get("priority", 99))[:2]
        _br_action_lines = ""
        _cat_labels = {"discharge": "退院", "admission": "入院", "hold": "保持", "alert": "警告"}
        for _i, _act in enumerate(_br_top_actions, 1):
            _cat = _cat_labels.get(_act.get("category", ""), "")
            _br_action_lines += f"{_i}. [{_cat}] {_act['action']}\n"

        # 向こう3日の見通し
        _br_forecast_lines = ""
        _forecast_3 = _forecast[:3]
        _forecast_labels = ["明日", "明後日", "3日後"]
        _fc_values = []
        for _fi, _fc in enumerate(_forecast_3):
            _fc_occ = _fc["predicted_occupancy"] * 100
            _fc_values.append(_fc_occ)
            _lbl = _forecast_labels[_fi] if _fi < len(_forecast_labels) else f"{_fi+1}日後"
            _br_forecast_lines += f"{_lbl} {_fc_occ:.1f}%"
            if _fi < len(_forecast_3) - 1:
                _br_forecast_lines += " → "

        _br_forecast_comment = ""
        if _fc_values and min(_fc_values) < target_lower * 100:
            _br_forecast_comment = f"→ 入院受入施策（外来への前倒し依頼・連携室経由の紹介促進）を強化しないと{target_lower*100:.0f}%を割る見込み"
        elif _fc_values and max(_fc_values) > target_upper * 100:
            _br_forecast_comment = f"→ 退院調整を進めないと{target_upper*100:.0f}%を超える見込み"
        else:
            _br_forecast_comment = "→ 目標レンジ内で推移する見込み"

        _briefing_text = f"""━━━ 本日のブリーフィング ━━━
**病棟状態: {_br_score_ja}（{_br_score_numeric}点）**
在院 {_br_patients}名 / 空床 {_br_empty}床 / 稼働率 {_br_occ:.1f}%
A群 {_br_phase_a}名({_br_pct_a:.0f}%) / B群 {_br_phase_b}名({_br_pct_b:.0f}%) / C群 {_br_phase_c}名({_br_pct_c:.0f}%)

**優先アクション:**
{_br_action_lines}
**向こう3日の見通し:**
{_br_forecast_lines}
{_br_forecast_comment}
"""
        if _br_score_label == "healthy":
            st.success(_briefing_text)
        elif _br_score_label == "caution":
            st.warning(_briefing_text)
        else:
            st.error(_briefing_text)

        st.markdown("---")

        # --- 病棟状態詳細 ---
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
        _ws_c3.metric("1床あたり運営貢献額", fmt_yen(int(_ward_status.get('profit_per_bed', 0))))

        if _ward_status.get("messages"):
            st.markdown("**メッセージ:**")
            for _msg in _ward_status["messages"]:
                st.markdown(f"- {_msg}")

        st.markdown("---")

        # --- 稼働率予測 ---
        st.subheader("稼働率予測（5日間）")

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
        st.subheader("平均在院日数（LOS）最適化分析")

        # 前提条件: 月間入院数をスライダーで変更可能にする
        _los_default_adm = _cli_params["monthly_admissions"]
        _los_monthly_adm = st.slider(
            "月間入院数（この値を固定して平均在院日数を変化させます）",
            min_value=50, max_value=300, value=int(_los_default_adm), step=10,
            key="los_monthly_adm_slider",
            help="月間入院数を変更するとグラフが再計算されます。当院の実績は約150名/月です。"
        )
        # スライダーの値で一時的にパラメータを上書き
        _los_params = dict(_cli_params)
        _los_params["monthly_admissions"] = _los_monthly_adm
        # LOS分析は常に月単位（30日）で計算する
        # ※シミュレーション日数（例: 17日）をそのまま使うと日次入院数が過大になり
        #   全パターンで稼働率100%になってしまう
        _los_params["days_in_month"] = 30

        st.markdown(
            f"> **前提条件:** 月間入院数を **{_los_monthly_adm}名で固定** したまま、"
            f"平均在院日数だけを変化させた場合のシミュレーションです。"
            f"平均在院日数が変わると稼働率も変わる点にご注意ください。"
            f"上のスライダーで月間入院数を変えると再計算されます。"
        )
        st.caption(
            "※ 推定稼働率にはLittle's lawの理論値に稼働効率係数（0.94）を乗じています。"
            "入退院の曜日偏り・週末効果・ベッド回転ラグ等により、"
            "理論値と現場実績には約6%の差があるため補正しています。"
        )

        _los_impact = simulate_los_impact(_raw_df, _los_params)
        _optimal_los = calculate_optimal_los_range(_raw_df, _los_params)

        # --- 2段グラフ: 上=運営貢献額変化、下=稼働率変化 ---
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), height_ratios=[3, 2])
        fig.subplots_adjust(hspace=0.35)

        _deltas = [r["delta_days"] for r in _los_impact]
        _pdiffs = [r["profit_diff"] / 10000 for r in _los_impact]
        _occs = [r["estimated_occupancy"] * 100 for r in _los_impact]
        _actual_los_labels = [f"{avg_los + d}日\n({d:+d}日)" for d in _deltas]

        # 上段: 運営貢献額変化
        _bar_colors = [COLOR_PROFIT if v >= 0 else COLOR_A for v in _pdiffs]
        bars = ax1.bar(range(len(_deltas)), _pdiffs, color=_bar_colors, alpha=0.8)
        ax1.axhline(y=0, color="black", linewidth=0.5)
        ax1.set_ylabel("運営貢献額の変化（万円/月）")
        ax1.set_title(f"平均在院日数を変えたら？（月間入院数 {_los_monthly_adm}名で固定）")
        ax1.set_xticks(range(len(_deltas)))
        ax1.set_xticklabels(_actual_los_labels)
        ax1.grid(True, alpha=0.3, axis="y")
        # 棒グラフの上に金額表示
        for bar_obj, val in zip(bars, _pdiffs):
            _y_pos = bar_obj.get_height() if val >= 0 else bar_obj.get_height()
            ax1.text(bar_obj.get_x() + bar_obj.get_width() / 2, _y_pos,
                     f"{val:+.0f}万", ha="center",
                     va="bottom" if val >= 0 else "top",
                     fontsize=10, fontweight="bold")

        # 下段: 稼働率変化
        _occ_colors = []
        for o in _occs:
            if o > 100:
                _occ_colors.append("#E74C3C")  # 赤: 100%超（入院拒否発生）
            elif o >= 90:
                _occ_colors.append("#27AE60")  # 緑: 目標レンジ
            else:
                _occ_colors.append("#F39C12")  # 黄: 90%未満（空床多い）
        ax2.bar(range(len(_deltas)), _occs, color=_occ_colors, alpha=0.8)
        ax2.axhline(y=90, color="#27AE60", linewidth=1, linestyle="--", label="目標下限 90%")
        ax2.axhline(y=95, color="#F39C12", linewidth=1, linestyle="--", label="目標上限 95%")
        ax2.axhline(y=100, color="#E74C3C", linewidth=1, linestyle="--", label="満床 100%")
        ax2.set_ylabel("推定稼働率（%）")
        ax2.set_xlabel("平均在院日数")
        ax2.set_xticks(range(len(_deltas)))
        ax2.set_xticklabels(_actual_los_labels)
        ax2.set_ylim(max(0, min(_occs) - 10), max(_occs) + 5)
        ax2.grid(True, alpha=0.3, axis="y")
        ax2.legend(fontsize=8, loc="lower right")
        # 棒グラフの上に稼働率表示
        for i, o in enumerate(_occs):
            ax2.text(i, o + 0.5, f"{o:.0f}%", ha="center", va="bottom", fontsize=10, fontweight="bold")

        st.pyplot(fig)
        plt.close(fig)

        # --- 解説パネル ---
        # 各シナリオの要約テーブル
        _los_table_data = []
        for r in _los_impact:
            _d = r["delta_days"]
            _los_val = avg_los + _d
            _occ_val = r["estimated_occupancy"] * 100
            _diff_val = r["profit_diff"] / 10000
            if _occ_val > 100:
                _comment = "❌ 満床超過 → 入院を断る必要あり（コスト発生）"
            elif _occ_val > 95:
                _comment = "⚠️ 高稼働（95%超）→ 入院枠の余裕が少ない"
            elif _occ_val >= 90:
                _comment = "✅ 目標レンジ内（90〜95%）"
            elif _occ_val >= 85:
                _comment = "📉 やや空床多い → 入院促進の検討を"
            else:
                _comment = "📉 空床多い → 入院確保が急務"
            _los_table_data.append({
                "平均在院日数": f"{_los_val}日 ({_d:+d}日)",
                "推定稼働率": f"{_occ_val:.0f}%",
                "月次運営貢献額の変化": f"{_diff_val:+.0f}万円",
                "状況": _comment,
            })
        st.dataframe(
            pd.DataFrame(_los_table_data),
            use_container_width=True,
            hide_index=True,
        )

        st.markdown(
            "**📖 このグラフの読み方：**\n\n"
            "- **上段（棒グラフ・青/赤）:** 平均在院日数を変えたときの運営貢献額の増減です。"
            "現在の設定（±0）を基準に、プラスなら青、マイナスなら赤で表示します。\n"
            "- **下段（棒グラフ・色分け）:** そのときの推定稼働率です。"
            "緑=目標レンジ（90〜95%）、黄=90%未満、赤=満床超過（100%超）です。\n\n"
            "**ポイント（稼働率で意味が変わります）:**\n\n"
            "| 稼働率 | 平均在院日数を延ばすと | 平均在院日数を短くすると |\n"
            "|:---:|:---|:---|\n"
            "| **100%未満**（当院の通常） | ✅ 空床が埋まり運営貢献額が**増える** | ⚠️ 空床が増え運営貢献額が**減る** |\n"
            "| **100%付近** | ❌ 入院を断るコストが発生し**マイナスに転じる** | 回転が速まり新規を受けやすくなる |\n\n"
            "**当院の実態（稼働率90%前後）では、平均在院日数を少し延ばすことで空床が減り、"
            "運営貢献額が増える場合があります。** "
            "ただし、平均在院日数の延長は医学的に適切な範囲内で判断してください。\n\n"
            "⚠️ このシミュレーションは「月間入院数が一定」という前提です。"
            "平均在院日数を短くしても入院数を増やせれば稼働率は維持できます。"
            "**退院促進と入院確保はセットで考える必要があります。**"
        )

        st.info(
            f"**最適平均在院日数レンジ:** {_optimal_los['min_los']:.1f} 〜 {_optimal_los['max_los']:.1f} 日 "
            f"（最適値: {_optimal_los['optimal_los']} 日）\n\n"
            f"期待月次運営貢献額: {fmt_yen(_optimal_los['expected_monthly_profit'])}\n\n"
            f"現在の設定: {avg_los} 日"
        )

        st.markdown("---")

        # --- 💰 病棟運営最適化アドバイザー ---
        st.subheader("\U0001f4b0 病棟運営最適化アドバイザー")

        # 限界価値分析
        _marginal = calculate_marginal_bed_value(_cli_params)
        _gross_a = _marginal["phase_gross"]["A"]
        _gross_b = _marginal["phase_gross"]["B"]
        _gross_c = _marginal["phase_gross"]["C"]
        _lifetime = _marginal["new_admission_lifetime_profit"]
        _daily_avg = _marginal["new_admission_daily_avg"]
        _breakeven = _marginal["breakeven_days"]

        # 限界価値パネル
        st.markdown("##### 限界価値分析")
        _mv_c1, _mv_c2, _mv_c3 = st.columns(3)
        _mv_c1.metric("A群 運営貢献額/日", fmt_yen(int(_gross_a)))
        _mv_c2.metric("B群 運営貢献額/日", fmt_yen(int(_gross_b)), delta="安定貢献層")
        _mv_c3.metric("C群 運営貢献額/日", fmt_yen(int(_gross_c)), delta="最高効率")

        _mv_c4, _mv_c5, _mv_c6 = st.columns(3)
        _mv_c4.metric("新規1名 生涯期待運営貢献額", fmt_yen(_lifetime))
        _mv_c5.metric("新規1名 日平均運営貢献額", fmt_yen(_daily_avg))
        _mv_c6.metric("損益分岐日数", f"{_breakeven}日")

        # C群 vs 新規の判断基準
        if _gross_c > _daily_avg:
            st.warning(
                f"**C群在院調整({fmt_yen(int(_gross_c))}/日) > 新規平均({fmt_yen(_daily_avg)}/日)**\n\n"
                f"差額 +{fmt_yen(int(_gross_c - _daily_avg))}/日 → "
                f"空床がある限りC群は持たせる方が得。退院させるのは満床で入院を断る場合のみ。"
            )
        else:
            st.success(
                f"**新規平均({fmt_yen(_daily_avg)}/日) >= C群在院調整({fmt_yen(int(_gross_c))}/日)**\n\n"
                f"→ 回転させて新規を入れる方が効率的。"
            )

        st.markdown("---")

        # 今日の最適プラン
        st.markdown("##### 今日の最適プラン")

        _demand_default = 5
        _opt_plan = optimize_discharge_plan(
            _raw_df, _day_idx, _cli_params, expected_daily_demand=_demand_default
        )
        _cs = _opt_plan["current_state"]
        _rec = _opt_plan["recommendation"]
        _aft = _opt_plan["after_state"]
        _econ = _opt_plan["economics"]

        _opt_col1, _opt_col2 = st.columns(2)
        with _opt_col1:
            st.markdown(
                f"**現状:** 稼働率 {_cs['occupancy']*100:.1f}% | "
                f"空床 {_cs['empty_beds']}床 | "
                f"A群{_cs['a']}名 B群{_cs['b']}名 C群{_cs['c']}名"
            )
        with _opt_col2:
            st.markdown(f"**入院需要（既定値）:** 約{_demand_default}名/日")

        # 推奨アクション
        _rec_text = (
            f"**推奨: C群退院 {_rec['c_discharge']}名"
        )
        if _rec["b_discharge"] > 0:
            _rec_text += f" / B群退院 {_rec['b_discharge']}名"
        _rec_text += f" / 新規入院 {_rec['new_admissions']}名**"

        if _rec["total_discharge"] == 0:
            st.success(_rec_text)
        else:
            st.warning(_rec_text)

        # 理由
        for _r in _opt_plan["reasoning"]:
            st.markdown(f"- {_r}")

        # 経済効果
        _econ_cols = st.columns(4)
        _econ_cols[0].metric(
            "退院による運営貢献額減",
            fmt_yen(_econ["daily_lost_profit"]),
            delta=f"-{fmt_yen(_econ['daily_lost_profit'])}" if _econ["daily_lost_profit"] > 0 else "0",
            delta_color="inverse",
        )
        _econ_cols[1].metric(
            "新規入院の初日運営貢献額",
            fmt_yen(_econ["daily_gained_profit"]),
        )
        _econ_cols[2].metric(
            "日次純効果",
            fmt_yen(_econ["daily_net_impact"]),
            delta=f"{_econ['daily_net_impact']:+,}円",
            delta_color="normal",
        )
        _econ_cols[3].metric(
            "新規の将来期待運営貢献額",
            fmt_yen(_econ["future_gain_from_new"]),
        )

        # 実施後の状態
        st.markdown(
            f"**実施後:** 在院{_aft['total']}名 / "
            f"稼働率{_aft['occupancy']*100:.1f}%"
        )

        st.markdown("---")

        # 需要別シミュレーション
        st.markdown("##### 需要別シミュレーション")
        _demand_slider = st.slider(
            "入院需要予測（名/日）", min_value=1, max_value=15, value=5,
            key="revenue_advisor_demand",
        )

        _demand_results = []
        for _d in range(1, _demand_slider + 1):
            _d_plan = optimize_discharge_plan(
                _raw_df, _day_idx, _cli_params, expected_daily_demand=_d
            )
            _demand_results.append({
                "需要": f"{_d}名",
                "推奨C群退院": f"{_d_plan['recommendation']['c_discharge']}名",
                "推奨B群退院": f"{_d_plan['recommendation']['b_discharge']}名",
                "推奨入院": f"{_d_plan['recommendation']['new_admissions']}名",
                "翌日稼働率": f"{_d_plan['after_state']['occupancy']*100:.1f}%",
                "日次運営貢献額変化": fmt_yen(_d_plan['economics']['daily_net_impact']),
            })

        _demand_df = pd.DataFrame(_demand_results)
        st.dataframe(_demand_df, width="stretch", hide_index=True)

        # C群退院が発生する閾値を見つける
        _threshold = None
        for _d in range(1, 16):
            _d_plan = optimize_discharge_plan(
                _raw_df, _day_idx, _cli_params, expected_daily_demand=_d
            )
            if _d_plan["recommendation"]["c_discharge"] > 0:
                _threshold = _d
                break

        if _threshold:
            st.info(f"**ポイント:** 需要{_threshold}名以上でC群退院が必要になります")
        else:
            st.info("**ポイント:** 現在の空床数では需要15名まで退院調整不要です")

# --- タブ6: What-if分析（シミュレーションモードのみ） ---
if "\U0001f52e What-if分析" in _tab_idx:
    with tabs[_tab_idx["\U0001f52e What-if分析"]]:
        if not _DECISION_SUPPORT_AVAILABLE:
            st.error("意思決定支援機能はまだ利用できません。CLI版（bed_control_simulator.py）に必要な関数が実装されていません。")
        if "_DECISION_SUPPORT_ERROR" in dir():
            st.code(_DECISION_SUPPORT_ERROR)
        else:
            st.subheader("\U0001f52e What-if分析")
            st.info(
                "💡 **過去の任意の日に戻って「もしあの日こうしていたら？」をシミュレーションできます。**\n\n"
                "実績データの中から日付を選び、退院・入院の人数を変えてみることで、"
                "稼働率や運営貢献額がどう変わるかを即座に確認できます。"
            )
            if _HELP_AVAILABLE and "tab_whatif" in HELP_TEXTS:
                with st.expander("📖 このタブの見方と活用法"):
                    st.markdown(HELP_TEXTS["tab_whatif"])

            # 安全チェック: _active_raw_dfが有効でない場合は処理をスキップ
            if not isinstance(_active_raw_df, pd.DataFrame) or len(_active_raw_df) == 0:
                st.error("What-if分析に必要なデータがありません。実績データを入力するかシミュレーションを実行してください。")
            else:
                _raw_df = _active_raw_df
                _cli_params = _active_cli_params

            _wi_dates = pd.to_datetime(_raw_df["date"]) if "date" in _raw_df.columns else None

            _scenario_type = st.radio(
                "シナリオを選んでください",
                ["今日の入退院シナリオ", "週間退院計画", "入院需要変動"],
                captions=[
                    "1日分の退院・入院を変えたら？",
                    "1週間の退院計画を立てて検証",
                    "入院需要が急増/急減したら？",
                ],
                horizontal=True,
                key="whatif_scenario_type",
            )

            # ==================================================================
            # 今日の入退院シナリオ（混合退院 + 新規入院）
            # ==================================================================
            if _scenario_type == "今日の入退院シナリオ":
                st.markdown("#### 📅 日付を選んで「もしも」を試す")
                st.caption("過去の任意の日を選び、退院・入院の人数を変えると稼働率や貢献額がどう変わるかシミュレーションします。")
                # 日付ラベル付きの起点日選択
                if _wi_dates is not None and len(_wi_dates) > 0:
                    _wi_date_options = {
                        i + 1: f"{d.strftime('%m/%d')}（{['月','火','水','木','金','土','日'][d.weekday()]}）"
                        for i, d in enumerate(_wi_dates)
                    }
                    _wi_day = st.select_slider(
                        "🕐 どの日に戻りますか？",
                        options=list(_wi_date_options.keys()),
                        value=len(_raw_df),
                        format_func=lambda x: _wi_date_options[x],
                        key="wi_day_mixed",
                    )
                else:
                    _wi_day = st.slider("起点日", 1, len(_raw_df), value=len(_raw_df), key="wi_day_mixed")
                _wi_row = _raw_df.iloc[_wi_day - 1]

                # 現在の病棟状態を表示
                _wi_cur_total = int(_wi_row["total_patients"])
                _wi_cur_a = int(_wi_row["phase_a_count"])
                _wi_cur_b = int(_wi_row["phase_b_count"])
                _wi_cur_c = int(_wi_row["phase_c_count"])
                _wi_cur_occ = _wi_row["occupancy_rate"]
                _wi_date_label = _wi_dates.iloc[_wi_day - 1].strftime("%Y/%m/%d") if _wi_dates is not None else f"Day {_wi_day}"

                st.markdown(f"**📋 {_wi_date_label} の病棟状態（この状態からシミュレーション開始）**")
                _state_cols = st.columns(5)
                with _state_cols[0]:
                    st.metric("在院患者数", f"{_wi_cur_total}名")
                with _state_cols[1]:
                    st.metric("稼働率", f"{_wi_cur_occ*100:.1f}%")
                with _state_cols[2]:
                    st.metric("A群（急性期）", f"{_wi_cur_a}名")
                with _state_cols[3]:
                    st.metric("B群（回復期）", f"{_wi_cur_b}名")
                with _state_cols[4]:
                    st.metric("C群（退院準備）", f"{_wi_cur_c}名")

                st.markdown("---")

                # 退院予定と新規入院を横並びで入力
                _col_discharge, _col_admission = st.columns([3, 2])

                with _col_discharge:
                    st.markdown("**退院予定**")
                    _wi_da = st.number_input(
                        f"A群（急性期転院）: 最大{_wi_cur_a}名",
                        min_value=0, max_value=max(_wi_cur_a, 0), value=0, step=1,
                        key="wi_mixed_da",
                    )
                    _wi_db = st.number_input(
                        f"B群（回復退院）: 最大{_wi_cur_b}名",
                        min_value=0, max_value=max(_wi_cur_b, 0), value=0, step=1,
                        key="wi_mixed_db",
                    )
                    _wi_dc = st.number_input(
                        f"C群（計画退院）: 最大{_wi_cur_c}名",
                        min_value=0, max_value=max(_wi_cur_c, 0), value=0, step=1,
                        key="wi_mixed_dc",
                    )
                    st.markdown(f"退院合計: **{_wi_da + _wi_db + _wi_dc}名**")

                with _col_admission:
                    st.markdown("**新規入院予定**")
                    _wi_remaining = _wi_cur_total - (_wi_da + _wi_db + _wi_dc)
                    _wi_avail = max(0, _cli_params["num_beds"] - max(_wi_remaining, 0))
                    _wi_new_adm = st.number_input(
                        f"新規入院: 最大{_wi_avail}名",
                        min_value=0, max_value=max(_wi_avail, 0), value=0, step=1,
                        key="wi_mixed_new",
                    )

                # よくある退院パターン（プリセット）
                st.markdown("**よくある退院パターン**")
                _presets = {
                    "通常日パターン（A:0 B:1 C:3 入院:5）": (0, 1, 3, 5),
                    "月曜集中パターン（A:1 B:2 C:5 入院:3）": (1, 2, 5, 3),
                    "週末パターン（A:0 B:0 C:1 入院:1）": (0, 0, 1, 1),
                    "繁忙日パターン（A:1 B:3 C:4 入院:7）": (1, 3, 4, 7),
                }
                _preset_cols = st.columns(len(_presets))
                for _pi, (_pname, _pvals) in enumerate(_presets.items()):
                    with _preset_cols[_pi]:
                        if st.button(_pname, key=f"preset_{_pi}", width="stretch"):
                            st.session_state["wi_mixed_da"] = min(_pvals[0], _wi_cur_a)
                            st.session_state["wi_mixed_db"] = min(_pvals[1], _wi_cur_b)
                            st.session_state["wi_mixed_dc"] = min(_pvals[2], _wi_cur_c)
                            _remaining_p = _wi_cur_total - (
                                min(_pvals[0], _wi_cur_a)
                                + min(_pvals[1], _wi_cur_b)
                                + min(_pvals[2], _wi_cur_c)
                            )
                            _avail_p = max(0, _cli_params["num_beds"] - max(_remaining_p, 0))
                            st.session_state["wi_mixed_new"] = min(_pvals[3], _avail_p)
                            st.rerun()

                st.markdown("---")

                if st.button("シナリオ実行", key="btn_whatif_mixed", type="primary"):
                    _mix_result = whatif_mixed_scenario(
                        _raw_df, _wi_day - 1, _cli_params,
                        discharge_a=_wi_da, discharge_b=_wi_db, discharge_c=_wi_dc,
                        new_admissions=_wi_new_adm,
                    )

                    st.markdown(f"### 📊 結果: {_wi_date_label} の実績 → もしこうしていたら")
                    _mc1, _mc2 = st.columns(2)
                    _bl = _mix_result["baseline"]
                    _sc = _mix_result["scenario"]
                    _df_diff = _mix_result["diff"]

                    with _mc1:
                        st.markdown("**Before（現状）**")
                        st.metric("稼働率", f"{_bl['occupancy']*100:.1f}%")
                        st.metric("在院患者数", f"{_bl['total']}名")
                        st.metric("A群", f"{_bl['a']}名")
                        st.metric("B群", f"{_bl['b']}名")
                        st.metric("C群", f"{_bl['c']}名")
                        st.metric("日次運営貢献額", fmt_yen(_bl["daily_profit"]))

                    with _mc2:
                        st.markdown("**After（シナリオ後）**")
                        st.metric(
                            "稼働率",
                            f"{_sc['occupancy']*100:.1f}%",
                            delta=f"{_df_diff['occupancy']*100:+.1f}%",
                        )
                        st.metric(
                            "在院患者数",
                            f"{_sc['total']}名",
                            delta=f"{_df_diff['total']:+d}名",
                        )
                        st.metric(
                            "A群",
                            f"{_sc['a']}名",
                            delta=f"{_sc['a'] - _bl['a']:+d}名",
                        )
                        st.metric(
                            "B群",
                            f"{_sc['b']}名",
                            delta=f"{_sc['b'] - _bl['b']:+d}名",
                        )
                        st.metric(
                            "C群",
                            f"{_sc['c']}名",
                            delta=f"{_sc['c'] - _bl['c']:+d}名",
                        )
                        _profit_delta_val = _df_diff["daily_profit"]
                        _profit_delta_str = f"+{fmt_yen(int(_profit_delta_val))}" if _profit_delta_val >= 0 else f"-{fmt_yen(abs(int(_profit_delta_val)))}"
                        st.metric(
                            "日次運営貢献額",
                            fmt_yen(_sc["daily_profit"]),
                            delta=_profit_delta_str,
                        )

                    # フェーズ構成比 Before/After 棒グラフ
                    st.markdown("#### 📊 フェーズ構成比の変化")
                    _phase_labels = ["A群", "B群", "C群"]
                    _bl_total_safe = max(_bl["total"], 1)
                    _before_ratios = [
                        _bl["a"] / _bl_total_safe * 100,
                        _bl["b"] / _bl_total_safe * 100,
                        _bl["c"] / _bl_total_safe * 100,
                    ]
                    _after_ratios = [
                        _mix_result["phase_composition_after"]["A"] * 100,
                        _mix_result["phase_composition_after"]["B"] * 100,
                        _mix_result["phase_composition_after"]["C"] * 100,
                    ]
                    _fig_comp, _ax_comp = plt.subplots(figsize=(8, 4))
                    _x_idx = np.arange(len(_phase_labels))
                    _bar_w = 0.35
                    _ax_comp.bar(_x_idx - _bar_w / 2, _before_ratios, _bar_w, label="Before", color="#3498DB")
                    _ax_comp.bar(_x_idx + _bar_w / 2, _after_ratios, _bar_w, label="After", color="#E74C3C")
                    _ax_comp.set_ylabel("構成比 (%)")
                    _ax_comp.set_xticks(_x_idx)
                    _ax_comp.set_xticklabels(_phase_labels)
                    _ax_comp.legend()
                    _ax_comp.set_ylim(0, 100)
                    for _bi, (_bv, _av) in enumerate(zip(_before_ratios, _after_ratios)):
                        _ax_comp.text(_bi - _bar_w / 2, _bv + 1, f"{_bv:.1f}%", ha="center", fontsize=9)
                        _ax_comp.text(_bi + _bar_w / 2, _av + 1, f"{_av:.1f}%", ha="center", fontsize=9)
                    plt.tight_layout()
                    st.pyplot(_fig_comp)
                    plt.close(_fig_comp)

                    # 判定メッセージ
                    st.markdown("#### 💡 判定")
                    for _msg in _mix_result["messages"]:
                        if _msg.startswith("✅"):
                            st.success(_msg)
                        else:
                            st.warning(_msg)

            # ==================================================================
            # 週間退院計画
            # ==================================================================
            elif _scenario_type == "週間退院計画":
                st.markdown("#### 📅 1週間の退院計画を試す")
                st.caption("開始日を選び、7日間の退院・入院計画を入力すると、日ごとの稼働率変化をシミュレーションします。前日の結果が翌日に反映されます。")

                _wi_wk_max = max(len(_raw_df) - 6, 1)
                if _wi_dates is not None and len(_wi_dates) > 0:
                    _wi_wk_options = {
                        i + 1: f"{_wi_dates.iloc[i].strftime('%m/%d')}（{['月','火','水','木','金','土','日'][_wi_dates.iloc[i].weekday()]}）"
                        for i in range(_wi_wk_max)
                    }
                    _wi_start_day = st.select_slider(
                        "🕐 いつから計画を始めますか？（7日間）",
                        options=list(_wi_wk_options.keys()),
                        value=_wi_wk_max,
                        format_func=lambda x: _wi_wk_options[x],
                        key="wi_weekly_start",
                    )
                else:
                    _wi_start_day = st.slider(
                        "開始日", 1, _wi_wk_max, value=_wi_wk_max, key="wi_weekly_start",
                    )
                _n_plan_days = min(7, len(_raw_df) - _wi_start_day + 1)

                _weekday_names = ["月", "火", "水", "木", "金", "土", "日"]

                # デフォルト値をDataFrameで作成
                _plan_data = []
                for _di in range(_n_plan_days):
                    _day_idx = _wi_start_day - 1 + _di
                    _row_i = _raw_df.iloc[_day_idx]
                    _date_str = str(_row_i["date"]) if "date" in _raw_df.columns else f"Day {_day_idx + 1}"
                    # 曜日を推定（day_indexから）
                    _wd = _di % 7
                    _plan_data.append({
                        "日付": _date_str,
                        "A群退院": 0,
                        "B群退院": 1 if _wd < 5 else 0,
                        "C群退院": 3 if _wd == 0 else (2 if _wd < 5 else (1 if _wd == 5 else 0)),
                        "新規入院": 5 if _wd < 5 else (3 if _wd == 5 else 2),
                    })

                _plan_df = pd.DataFrame(_plan_data)
                _edited_plan = st.data_editor(
                    _plan_df,
                    column_config={
                        "日付": st.column_config.TextColumn("日付", disabled=True),
                        "A群退院": st.column_config.NumberColumn("A群退院", min_value=0, max_value=20, step=1),
                        "B群退院": st.column_config.NumberColumn("B群退院", min_value=0, max_value=30, step=1),
                        "C群退院": st.column_config.NumberColumn("C群退院", min_value=0, max_value=30, step=1),
                        "新規入院": st.column_config.NumberColumn("新規入院", min_value=0, max_value=20, step=1),
                    },
                    width="stretch",
                    hide_index=True,
                    key="weekly_plan_editor",
                )

                # 合計行を表示
                _total_row = _edited_plan[["A群退院", "B群退院", "C群退院", "新規入院"]].sum()
                st.markdown(
                    f"**週間合計:** 退院 {int(_total_row['A群退院'] + _total_row['B群退院'] + _total_row['C群退院'])}名 "
                    f"（A:{int(_total_row['A群退院'])} B:{int(_total_row['B群退院'])} C:{int(_total_row['C群退院'])}） / "
                    f"新規入院 {int(_total_row['新規入院'])}名"
                )

                if st.button("週間計画シミュレーション実行", key="btn_whatif_weekly", type="primary"):
                    # DataFrameからdaily_plansリストを構築
                    _daily_plans = []
                    for _di in range(len(_edited_plan)):
                        _day_idx = _wi_start_day - 1 + _di
                        _daily_plans.append({
                            "day_index": _day_idx,
                            "discharge_a": int(_edited_plan.iloc[_di]["A群退院"]),
                            "discharge_b": int(_edited_plan.iloc[_di]["B群退院"]),
                            "discharge_c": int(_edited_plan.iloc[_di]["C群退院"]),
                            "new_admissions": int(_edited_plan.iloc[_di]["新規入院"]),
                        })

                    _weekly_result = whatif_weekly_plan(_raw_df, _cli_params, _daily_plans)
                    _w_results = _weekly_result["daily_results"]
                    _w_summary = _weekly_result["summary"]

                    if _w_results:
                        # 日別結果テーブル
                        st.markdown("### 日別シミュレーション結果")
                        _result_table = []
                        for _wr in _w_results:
                            _result_table.append({
                                "日付": str(_wr["date"]),
                                "退院": _wr["discharge"]["total"],
                                "新規入院": _wr["new_admissions"],
                                "在院数": _wr["after"]["total"],
                                "A群": _wr["after"]["a"],
                                "B群": _wr["after"]["b"],
                                "C群": _wr["after"]["c"],
                                "稼働率": f"{_wr['occupancy']*100:.1f}%",
                                "日次運営貢献額": fmt_yen(_wr["daily_profit"]),
                            })
                        st.dataframe(pd.DataFrame(_result_table), width="stretch", hide_index=True)

                        # 稼働率・運営貢献額推移グラフ
                        st.markdown("### 📊 稼働率・運営貢献額推移")
                        _fig_w, (_ax_occ_w, _ax_profit_w) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)

                        _dates_w = [str(r["date"]) for r in _w_results]
                        _occs_w = [r["occupancy"] * 100 for r in _w_results]
                        _profits_w = [r["daily_profit"] / 10000 for r in _w_results]

                        # 稼働率
                        _ax_occ_w.bar(_dates_w, _occs_w, color="#3498DB", alpha=0.8)
                        _ax_occ_w.axhline(y=target_lower * 100, color="#E74C3C", linestyle="--", alpha=0.7, label=f"下限{target_lower*100:.0f}%")
                        _ax_occ_w.axhline(y=target_upper * 100, color="#E74C3C", linestyle="--", alpha=0.7, label=f"上限{target_upper*100:.0f}%")
                        _ax_occ_w.set_ylabel("稼働率 (%)")
                        _ax_occ_w.legend(fontsize=8)
                        _ax_occ_w.set_ylim(max(0, min(_occs_w) - 10), 105)
                        for _xi, _yv in enumerate(_occs_w):
                            _ax_occ_w.text(_xi, _yv + 0.5, f"{_yv:.1f}%", ha="center", fontsize=8)

                        # 運営貢献額
                        _profit_colors = ["#27AE60" if p >= 0 else "#E74C3C" for p in _profits_w]
                        _ax_profit_w.bar(_dates_w, _profits_w, color=_profit_colors, alpha=0.8)
                        _ax_profit_w.set_ylabel("日次運営貢献額 (万円)")
                        _ax_profit_w.axhline(y=0, color="gray", linewidth=0.5)
                        for _xi, _yv in enumerate(_profits_w):
                            _ax_profit_w.text(_xi, _yv + 0.3, f"{_yv:.1f}", ha="center", fontsize=8)

                        plt.xticks(rotation=45, ha="right")
                        plt.tight_layout()
                        st.pyplot(_fig_w)
                        plt.close(_fig_w)

                        # 週間サマリー
                        st.markdown("### 週間サマリー")
                        _ws1, _ws2, _ws3, _ws4 = st.columns(4)
                        with _ws1:
                            st.metric("退院合計", f"{_w_summary['total_discharge']}名")
                        with _ws2:
                            st.metric("入院合計", f"{_w_summary['total_admission']}名")
                        with _ws3:
                            st.metric("平均稼働率", f"{_w_summary['avg_occupancy']*100:.1f}%")
                        with _ws4:
                            st.metric("運営貢献額合計", fmt_yen(_w_summary["total_profit"]))

            # ==================================================================
            # 入院需要変動シナリオ
            # ==================================================================
            else:
                st.markdown("#### 📈 入院需要が変動したらどうなる？")
                st.caption("GW明けの入院集中やお盆期間の減少など、入院需要の変動が稼働率に与える影響をシミュレーションします。")

                # プリセットシナリオ
                _surge_presets = {
                    "GW明け入院集中 +30%": 30,
                    "お盆期間 -40%": -40,
                    "インフル流行 +25%": 25,
                    "年末年始 -30%": -30,
                    "連休前駆け込み +20%": 20,
                    "カスタム": None,
                }
                _surge_preset_name = st.selectbox(
                    "シナリオ選択",
                    list(_surge_presets.keys()),
                    key="wi_surge_preset",
                )
                _surge_preset_val = _surge_presets[_surge_preset_name]

                if _surge_preset_val is not None:
                    _surge_pct = st.slider(
                        "変動率", -50, 50, value=_surge_preset_val, step=5,
                        format="%d%%", key="wi_surge_pct",
                    )
                else:
                    _surge_pct = st.slider(
                        "変動率", -50, 50, value=0, step=5,
                        format="%d%%", key="wi_surge_pct",
                    )

                if st.button("シナリオ実行", key="btn_whatif_surge", type="primary"):
                    _surge_result = whatif_admission_surge(
                        _cli_params, surge_pct=_surge_pct / 100.0,
                        strategy=STRATEGY_MAP[strategy],
                    )

                    _sc1, _sc2 = st.columns(2)
                    with _sc1:
                        st.markdown("**Before（現状）**")
                        st.metric("稼働率", f"{_surge_result['baseline_occupancy']*100:.1f}%")
                        st.metric("月次運営貢献額", fmt_yen(int(_surge_result["baseline_profit"])))
                    with _sc2:
                        st.markdown("**After（シナリオ）**")
                        _s_occ_delta = (_surge_result["scenario_occupancy"] - _surge_result["baseline_occupancy"]) * 100
                        _s_profit_delta = _surge_result["scenario_profit"] - _surge_result["baseline_profit"]
                        st.metric(
                            "稼働率",
                            f"{_surge_result['scenario_occupancy']*100:.1f}%",
                            delta=f"{_s_occ_delta:+.1f}%",
                        )
                        _s_profit_delta_str = f"+{fmt_yen(abs(int(_s_profit_delta)))}" if _s_profit_delta >= 0 else f"-{fmt_yen(abs(int(_s_profit_delta)))}"
                        st.metric(
                            "月次運営貢献額",
                            fmt_yen(int(_surge_result["scenario_profit"])),
                            delta=_s_profit_delta_str,
                        )

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
        if "_DECISION_SUPPORT_ERROR" in dir():
            st.code(_DECISION_SUPPORT_ERROR)
    else:
        st.subheader("\U0001f4c8 トレンド分析")
        if _HELP_AVAILABLE and "tab_trends" in HELP_TEXTS:
            with st.expander("📖 このタブの見方と活用法"):
                st.markdown(HELP_TEXTS["tab_trends"])

        # 安全チェック: _active_raw_dfが有効でない場合は処理をスキップ
        if not isinstance(_active_raw_df, pd.DataFrame) or len(_active_raw_df) == 0:
            st.error("トレンド分析に必要なデータがありません。実績データを入力するかシミュレーションを実行してください。")
        else:
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

        # --- 運営貢献効率トレンド ---
        st.markdown("### 運営貢献効率トレンド")
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
            ax.set_ylabel("1床あたり運営貢献額（万円）")
            ax.set_title("1床あたり運営貢献額トレンド（移動平均）")
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
            "月次診療報酬", "月次コスト", "月次運営貢献額",
            "平均稼働率", "月間入院数", "月間退院数",
            "平均在院日数",
            "目標レンジ内日数", "目標レンジ内率",
            "A群平均構成比", "B群平均構成比", "C群平均構成比",
        ]
        compare_data = {}
        for strat_name, strat_summary in comparison.items():
            compare_data[strat_name] = {k: strat_summary[k] for k in compare_keys}

        compare_df = pd.DataFrame(compare_data).T
        compare_df.index.name = "戦略"

        # 金額カラムをフォーマット
        for col in ["月次診療報酬", "月次コスト", "月次運営貢献額"]:
            compare_df[col] = compare_df[col].apply(lambda x: fmt_yen_full(int(x)))

        # パーセンテージカラム
        for col in ["平均稼働率", "目標レンジ内率", "A群平均構成比", "B群平均構成比", "C群平均構成比"]:
            compare_df[col] = compare_df[col].apply(lambda x: f"{x}%")

        st.dataframe(compare_df, width="stretch")

        # --- 主要指標の棒グラフ比較 ---
        strategies_list = list(comparison.keys())
        profits = [comparison[s]["月次運営貢献額"] / 10000 for s in strategies_list]
        occ_rates = [comparison[s]["平均稼働率"] for s in strategies_list]
        in_range = [comparison[s]["目標レンジ内率"] for s in strategies_list]

        fig, axes = plt.subplots(1, 3, figsize=(14, 4))
        bar_colors = [COLOR_A, COLOR_B, COLOR_C]

        axes[0].bar(strategies_list, profits, color=bar_colors, alpha=0.8)
        axes[0].set_title("月次運営貢献額（万円）")
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
        best_profit = max(comparison.items(), key=lambda x: x[1]["月次運営貢献額"])
        best_occ = min(comparison.items(),
                       key=lambda x: abs(x[1]["平均稼働率"] - (target_lower + target_upper) / 2 * 100))
        best_range = max(comparison.items(), key=lambda x: x[1]["目標レンジ内率"])

        col1, col2, col3 = st.columns(3)
        with col1:
            st.success(f"**運営貢献額最大:** {best_profit[0]}\n\n{fmt_yen(best_profit[1]['月次運営貢献額'])}")
        with col2:
            st.success(f"**稼働率最適:** {best_occ[0]}\n\n{best_occ[1]['平均稼働率']:.1f}%")
        with col3:
            st.success(f"**レンジ内最大:** {best_range[0]}\n\n{best_range[1]['目標レンジ内率']:.1f}%")



# ===== タブ: 👨‍⚕️ 退院タイミング =====
with tabs[_tab_idx["👨‍⚕️ 退院タイミング"]]:
    st.subheader("🔄 入退院バランス・空床リスクモニター")
    st.caption("退院は臨床判断。問題は「退院後の空床がいつ埋まるか」と「入院ペースは足りているか」です。")

    # ---- データ取得 ----
    _dt_raw = None
    if _is_actual_data_mode:
        _src = st.session_state.get("daily_data")
        if isinstance(_src, pd.DataFrame) and len(_src) > 0:
            _agg = aggregate_wards(_src) if "ward" in _src.columns else _src
            _dt_raw = calculate_daily_metrics(_agg, num_beds=_view_beds)
    else:
        _dt_raw = st.session_state.get("sim_df_raw")

    if _dt_raw is None or len(_dt_raw) == 0:
        st.info("シミュレーションを実行するか、実績データを入力してください。")
    else:
        # 最新日のデータ
        _last = _dt_raw.iloc[-1]
        _occ_now = float(_last.get("occupancy_rate", 0) or 0)
        _pts_now = int(_last.get("total_patients", 0) or 0)
        _empty_beds = _view_beds - _pts_now

        # 入退院データ
        _adm_today = int(_last.get("new_admissions", 0) or 0)
        _dis_today = int(_last.get("discharges", 0) or 0)
        _net_today = _adm_today - _dis_today

        # 時系列データ（グラフ用）
        _dt_plot = _dt_raw.copy()
        _dt_plot["date"] = pd.to_datetime(_dt_plot["date"])

        # 移動平均（データに含まれていない場合は計算）
        if "admission_7d_ma" not in _dt_plot.columns:
            _dt_plot["admission_7d_ma"] = _dt_plot["new_admissions"].rolling(7, min_periods=1).mean()
        if "discharge_7d_ma" not in _dt_plot.columns:
            _dt_plot["discharge_7d_ma"] = _dt_plot["discharges"].rolling(7, min_periods=1).mean()
        if "daily_net_change" not in _dt_plot.columns:
            _dt_plot["daily_net_change"] = _dt_plot["new_admissions"] - _dt_plot["discharges"]

        # 直近7日の平均
        _recent = _dt_plot.tail(7)
        _adm_7d = float(_recent["new_admissions"].mean())
        _dis_7d = float(_recent["discharges"].mean())
        _net_7d = _adm_7d - _dis_7d

        # パラメータ
        _ui_safe = ui if "ui" in dir() and isinstance(ui, dict) else {}
        occ_gap = target_lower - _occ_now

        # ============================================================
        # ① 空床リスクモニター（予測エンジン駆動）
        # ============================================================
        st.markdown("### 🛏️ 空床リスクモニター")
        st.caption("過去の入退院パターンから今後7日間を予測します。データが蓄積するほど精度が向上します。")

        _m1, _m2, _m3, _m4 = st.columns(4)
        with _m1:
            _occ_icon = "🟢" if _occ_now >= target_lower else "🔴"
            st.metric("現在の稼働率", f"{_occ_icon} {_occ_now*100:.1f}%",
                      delta=f"目標 {target_lower*100:.0f}%{'まで達成' if _occ_now >= target_lower else f' あと{occ_gap*100:.1f}pt'}")
        with _m2:
            st.metric("空床数", f"{_empty_beds}床",
                      delta=f"{'余裕あり' if _empty_beds > 5 else '残りわずか'}")
        with _m3:
            st.metric("直近7日 入院ペース", f"{_adm_7d:.1f}名/日")
        with _m4:
            # 空床が埋まるまでの推定日数
            _fill_days = _empty_beds / max(_adm_7d - _dis_7d, 0.01) if _net_7d > 0 else float("inf")
            if _fill_days == float("inf") or _fill_days < 0:
                st.metric("空床回復見込み", "⚠️ 不透明",
                          delta="入院＜退院が続いています")
            else:
                st.metric("空床回復見込み", f"約{_fill_days:.0f}日",
                          delta=f"純増{_net_7d:.1f}名/日ペース")

        # ---- 予測エンジンによる7日間予測 ----
        st.markdown("#### 🔮 今後7日間の入退院予測")

        _pred_df = _predict_admission_discharge(_dt_plot, num_beds=_view_beds, horizon=7)
        _dow_names_jp = ["月", "火", "水", "木", "金", "土", "日"]

        # 予測テーブル表示
        _pred_display = _pred_df.copy()
        _pred_display["日付"] = _pred_display["date"].apply(
            lambda d: f"{d.month}/{d.day}({_dow_names_jp[d.weekday()]})")
        _pred_display["種別"] = _pred_display["day_type"]
        _pred_display["予測入院"] = _pred_display["pred_admissions"]
        _pred_display["予測退院"] = _pred_display["pred_discharges"]
        _pred_display["純増減"] = _pred_display["pred_net"]
        _pred_display["予測患者数"] = _pred_display["pred_patients"].astype(int)
        _pred_display["予測稼働率"] = (_pred_display["pred_occupancy"] * 100).round(1).astype(str) + "%"
        _pred_display["信頼度"] = _pred_display["confidence"].apply(
            lambda c: f"{'🟢' if c >= 60 else '🟡' if c >= 30 else '🔴'} {c}%")

        st.dataframe(
            _pred_display[["日付", "種別", "予測入院", "予測退院", "純増減",
                           "予測患者数", "予測稼働率", "信頼度"]],
            use_container_width=True, hide_index=True)

        # グラフ: 予測入退院数と稼働率
        _fig_eb, (_ax_eb1, _ax_eb2) = plt.subplots(1, 2, figsize=(10, 3.5))

        _pred_x = list(range(len(_pred_df)))
        _pred_labels = [f"{r['date'].month}/{r['date'].day}\n({_dow_names_jp[r['weekday']]})"
                        for _, r in _pred_df.iterrows()]
        # 休日バーの色分け
        _adm_colors = ["#BBDEFB" if r["day_type"] != "平日" else "#42A5F5"
                       for _, r in _pred_df.iterrows()]
        _dis_colors = ["#FFCDD2" if r["day_type"] != "平日" else "#EF5350"
                       for _, r in _pred_df.iterrows()]

        # 左: 入退院予測の棒グラフ
        _bar_w = 0.35
        _ax_eb1.bar([x - _bar_w/2 for x in _pred_x], _pred_df["pred_admissions"],
                    _bar_w, color=_adm_colors, edgecolor="#1565C0", alpha=0.85, label="予測入院")
        _ax_eb1.bar([x + _bar_w/2 for x in _pred_x], _pred_df["pred_discharges"],
                    _bar_w, color=_dis_colors, edgecolor="#C62828", alpha=0.85, label="予測退院")
        # 誤差範囲（±1σ）
        _ax_eb1.errorbar([x - _bar_w/2 for x in _pred_x], _pred_df["pred_admissions"],
                         yerr=_pred_df["std_admissions"], fmt="none", ecolor="#1565C0", capsize=3, alpha=0.5)
        _ax_eb1.errorbar([x + _bar_w/2 for x in _pred_x], _pred_df["pred_discharges"],
                         yerr=_pred_df["std_discharges"], fmt="none", ecolor="#C62828", capsize=3, alpha=0.5)
        # 休日背景
        for i, (_, r) in enumerate(_pred_df.iterrows()):
            if r["day_type"] != "平日":
                _ax_eb1.axvspan(i - 0.5, i + 0.5, color="#FFF9C4", alpha=0.3)
        _ax_eb1.set_xticks(_pred_x)
        _ax_eb1.set_xticklabels(_pred_labels, fontsize=8)
        _ax_eb1.set_ylabel("人数", fontsize=10)
        _ax_eb1.set_title("入退院予測（7日間）", fontsize=11, fontweight="bold")
        _ax_eb1.legend(fontsize=8, loc="upper right")

        # 右: 稼働率推移予測
        _pred_occ_pct = [o * 100 for o in _pred_df["pred_occupancy"]]
        _ax_eb2.plot(_pred_x, _pred_occ_pct, "o-", color="#1565C0", linewidth=2, markersize=5)
        _ax_eb2.axhline(y=target_lower * 100, color="#E74C3C", linestyle="--", linewidth=1,
                        label=f"目標下限 {target_lower*100:.0f}%")
        _ax_eb2.axhline(y=target_upper * 100, color="#27AE60", linestyle="--", linewidth=1,
                        label=f"目標上限 {target_upper*100:.0f}%")
        _ax_eb2.fill_between(_pred_x, target_lower * 100, target_upper * 100,
                             alpha=0.1, color="#27AE60")
        # 休日背景
        for i, (_, r) in enumerate(_pred_df.iterrows()):
            if r["day_type"] != "平日":
                _ax_eb2.axvspan(i - 0.5, i + 0.5, color="#FFF9C4", alpha=0.3)
        _ax_eb2.set_xticks(_pred_x)
        _ax_eb2.set_xticklabels(_pred_labels, fontsize=8)
        _ax_eb2.set_ylabel("稼働率 (%)", fontsize=10)
        _ax_eb2.set_title("稼働率の推移予測", fontsize=11, fontweight="bold")
        _ax_eb2.legend(fontsize=8)

        _fig_eb.tight_layout()
        st.pyplot(_fig_eb)
        plt.close(_fig_eb)

        # ---- 予測ロジックの解説（グラフそば） ----
        _pred_method, _pred_confidence, _pred_detail, _pred_holiday = \
            _get_prediction_explanation(_dt_plot)
        with st.expander("📐 この予測はどう計算されているか"):
            st.markdown(f"""
**予測手法:** {_pred_method}

**{_pred_confidence}**

{_pred_detail}

**予測のしくみ:**
1. **曜日別パターン学習** — 過去データの曜日ごとの入院数・退院数を集計し、直近のデータほど重く反映する指数加重平均を使用（半減期14日）
2. **祝日・長期休日の自動判定** — {_pred_holiday}。祝日・連休の谷間は「日曜パターン」を適用（当院の特徴: 休日入院≒0、週末退院が多い）
3. **誤差範囲の表示** — グラフのエラーバー（ヒゲ）は±1標準偏差。振れ幅の大きい曜日ほどヒゲが長くなります
4. **信頼度スコア** — 各曜日のサンプル数と全体のデータ蓄積量から算出（0〜100%）

**データ蓄積と精度向上のしくみ:**

| データ蓄積量 | 予測モード | 期待される精度 |
|:---:|:---:|:---:|
| 2週間未満 | 全体平均（曜日区別なし） | 🔴 低 |
| 2〜8週間 | 曜日別加重平均 | 🟡 中 |
| 8週間以上 | 曜日別加重平均（安定） | 🟢 高 |

💡 **2ヶ月分のデータが蓄積すると「金曜退院は多い」「月曜入院は少ない」など、当院固有のパターンが安定的に反映されます。**
💡 **GW・年末年始などの長期連休は、祝日判定＋連休谷間判定で自動的に「入院≒0」パターンが適用されます。**
""")

        # ---- 判定メッセージ（予測ベース） ----
        _pred_7d_adm = float(_pred_df["pred_admissions"].sum())
        _pred_7d_dis = float(_pred_df["pred_discharges"].sum())
        _pred_7d_net = _pred_7d_adm - _pred_7d_dis
        _pred_last_occ = float(_pred_df.iloc[-1]["pred_occupancy"])

        if _pred_7d_net > 0:
            if _pred_last_occ >= target_lower:
                st.success(f"✅ 7日間の予測: 入院 **{_pred_7d_adm:.0f}名** ＞ 退院 **{_pred_7d_dis:.0f}名**"
                           f"（純増 {_pred_7d_net:+.0f}名）。"
                           f"稼働率は **{_pred_last_occ*100:.1f}%** に回復見込み。"
                           f"**臨床的に適切な退院を進めて問題ありません。**")
            else:
                st.info(f"📈 7日間の予測: 入院 **{_pred_7d_adm:.0f}名** ＞ 退院 **{_pred_7d_dis:.0f}名**"
                        f"（純増 {_pred_7d_net:+.0f}名）。"
                        f"ただし7日後の予測稼働率 **{_pred_last_occ*100:.1f}%** は"
                        f"目標 {target_lower*100:.0f}% に未到達。入院ペースの維持・強化が必要です。")
        elif _pred_7d_net == 0:
            st.warning(f"⚠️ 7日間の予測: 入院 **{_pred_7d_adm:.0f}名** ≒ 退院 **{_pred_7d_dis:.0f}名**。"
                       "稼働率は横ばいの見込み。空床を埋めるには**新規入院の促進**が必要です。")
        else:
            st.error(f"🔴 7日間の予測: 入院 **{_pred_7d_adm:.0f}名** ＜ 退院 **{_pred_7d_dis:.0f}名**"
                     f"（純減 {_pred_7d_net:+.0f}名）。"
                     f"稼働率は **{_pred_last_occ*100:.1f}%** まで低下する見込みです。  \n"
                     f"**対策:** 紹介元への空床案内の発信、地域連携室との入院促進協議を検討してください。")

        st.markdown("---")

        # ============================================================
        # ② 入退院バランスダッシュボード
        # ============================================================
        st.markdown("### 📊 入退院バランスダッシュボード")
        st.caption("稼働率の問題は「退院が多い」のではなく「入院が足りない」かもしれません。入口と出口のバランスを確認します。")

        # ---- 日次バランスサマリー ----
        _bal1, _bal2, _bal3, _bal4 = st.columns(4)
        with _bal1:
            st.metric("直近日 入院", f"{_adm_today}名",
                      delta=f"7日平均 {_adm_7d:.1f}名")
        with _bal2:
            st.metric("直近日 退院", f"{_dis_today}名",
                      delta=f"7日平均 {_dis_7d:.1f}名")
        with _bal3:
            _net_icon = "🟢" if _net_today >= 0 else "🔴"
            st.metric("直近日 純増減", f"{_net_icon} {_net_today:+d}名",
                      delta=f"7日平均 {_net_7d:+.1f}名")
        with _bal4:
            # 入退院比率（入院/退院）
            _ratio = _adm_7d / max(_dis_7d, 0.1)
            _ratio_icon = "🟢" if _ratio >= 1.0 else "🔴"
            st.metric("入退院比率（7日）", f"{_ratio_icon} {_ratio:.2f}",
                      delta="1.0以上なら稼働率↑")

        # ---- グラフ: 入退院トレンド ----
        if len(_dt_plot) >= 3:
            _fig_bal, (_ax_bal1, _ax_bal2) = plt.subplots(2, 1, figsize=(10, 7), gridspec_kw={"height_ratios": [3, 2]})

            _dates = _dt_plot["date"]

            # 上段: 入院数 vs 退院数（棒グラフ + 移動平均線）
            _bar_width = 0.35
            _x_idx = np.arange(len(_dates))

            # 棒が多すぎる場合は直近30日に絞る
            _show_n = min(len(_dt_plot), 30)
            _dp = _dt_plot.tail(_show_n).reset_index(drop=True)
            _x_show = np.arange(_show_n)
            _dates_show = _dp["date"]

            _ax_bal1.bar(_x_show - _bar_width/2, _dp["new_admissions"], _bar_width,
                        label="入院", color="#42A5F5", alpha=0.7, edgecolor="#1565C0")
            _ax_bal1.bar(_x_show + _bar_width/2, _dp["discharges"], _bar_width,
                        label="退院", color="#EF5350", alpha=0.7, edgecolor="#C62828")
            _ax_bal1.plot(_x_show, _dp["admission_7d_ma"], "-", color="#1565C0",
                         linewidth=2, label="入院 7日MA")
            _ax_bal1.plot(_x_show, _dp["discharge_7d_ma"], "-", color="#C62828",
                         linewidth=2, label="退院 7日MA")
            _ax_bal1.set_ylabel("人数", fontsize=10)
            _ax_bal1.set_title("入院数 vs 退院数（直近最大30日）", fontsize=11, fontweight="bold")
            _ax_bal1.legend(fontsize=8, loc="upper left")
            # X軸ラベル（日付）
            _tick_step = max(1, _show_n // 10)
            _ax_bal1.set_xticks(_x_show[::_tick_step])
            _ax_bal1.set_xticklabels([d.strftime("%m/%d") for d in _dates_show.iloc[::_tick_step]], fontsize=8, rotation=45)

            # 下段: 日次純増減（ウォーターフォール風）
            _net_vals = _dp["daily_net_change"].values
            _colors_net = ["#42A5F5" if v >= 0 else "#EF5350" for v in _net_vals]
            _ax_bal2.bar(_x_show, _net_vals, color=_colors_net, alpha=0.8, edgecolor="none")
            _ax_bal2.axhline(y=0, color="#333", linewidth=0.8)
            _ax_bal2.set_ylabel("純増減（名）", fontsize=10)
            _ax_bal2.set_title("日次純増減（入院 − 退院）", fontsize=11, fontweight="bold")
            _ax_bal2.set_xticks(_x_show[::_tick_step])
            _ax_bal2.set_xticklabels([d.strftime("%m/%d") for d in _dates_show.iloc[::_tick_step]], fontsize=8, rotation=45)

            # 純増減がマイナス続きなら背景に薄い赤
            _neg_streak = sum(1 for v in _net_vals[-7:] if v < 0)
            if _neg_streak >= 5:
                _ax_bal2.set_facecolor("#FFF3E0")

            _fig_bal.tight_layout()
            st.pyplot(_fig_bal)
            plt.close(_fig_bal)

        # ---- 曜日別パターン分析 ----
        if len(_dt_plot) >= 7:
            st.markdown("#### 📅 曜日別 入退院パターン")
            _dow = _dt_plot.copy()
            _dow["weekday"] = _dow["date"].dt.dayofweek  # 0=月, 6=日
            _dow_names = ["月", "火", "水", "木", "金", "土", "日"]
            _dow_adm = _dow.groupby("weekday")["new_admissions"].mean()
            _dow_dis = _dow.groupby("weekday")["discharges"].mean()

            _fig_dow, _ax_dow = plt.subplots(figsize=(8, 3.5))
            _x_dow = np.arange(7)
            _ax_dow.bar(_x_dow - 0.2, [_dow_adm.get(i, 0) for i in range(7)], 0.4,
                       label="入院（平均）", color="#42A5F5", alpha=0.8)
            _ax_dow.bar(_x_dow + 0.2, [_dow_dis.get(i, 0) for i in range(7)], 0.4,
                       label="退院（平均）", color="#EF5350", alpha=0.8)
            _ax_dow.set_xticks(_x_dow)
            _ax_dow.set_xticklabels(_dow_names, fontsize=10)
            _ax_dow.set_ylabel("平均人数", fontsize=10)
            _ax_dow.set_title("曜日別の入退院パターン", fontsize=11, fontweight="bold")
            _ax_dow.legend(fontsize=9)
            _fig_dow.tight_layout()
            st.pyplot(_fig_dow)
            plt.close(_fig_dow)

            # 曜日別のギャップ分析
            _dow_gap = {d: _dow_adm.get(d, 0) - _dow_dis.get(d, 0) for d in range(7)}
            _worst_days = sorted(_dow_gap.items(), key=lambda x: x[1])[:2]
            _best_days = sorted(_dow_gap.items(), key=lambda x: x[1], reverse=True)[:2]

            _gc1, _gc2 = st.columns(2)
            with _gc1:
                _worst_txt = "、".join([f"**{_dow_names[d]}**（{v:+.1f}名）" for d, v in _worst_days])
                st.markdown(f"""
<div style="background:#ffebee;border-radius:10px;padding:14px;border-left:5px solid #E74C3C;">
<strong>🔴 退院超過が多い曜日:</strong> {_worst_txt}<br>
→ この曜日に新規入院を集中させる工夫（紹介元との調整）が効果的
</div>""", unsafe_allow_html=True)
            with _gc2:
                _best_txt = "、".join([f"**{_dow_names[d]}**（{v:+.1f}名）" for d, v in _best_days])
                st.markdown(f"""
<div style="background:#e8f5e9;border-radius:10px;padding:14px;border-left:5px solid #27AE60;">
<strong>🟢 入院超過が多い曜日:</strong> {_best_txt}<br>
→ この曜日のベッド確保を優先（退院調整のタイミング調整）
</div>""", unsafe_allow_html=True)

        st.markdown("---")

        # ============================================================
        # ③ アクションガイド
        # ============================================================
        st.markdown("### 📋 状況別アクションガイド")

        _actions = []
        # 入退院バランスに基づく判定
        if _net_7d >= 0.5:
            _actions.append(("🟢", "入院ペース良好",
                             f"直近7日の純増 {_net_7d:+.1f}名/日。入院が退院を上回っており、稼働率は改善傾向です。"
                             "臨床的に適切なタイミングでの退院を進めてください。"))
        elif _net_7d >= -0.5:
            _actions.append(("🟡", "入退院が均衡",
                             f"直近7日の純増減 {_net_7d:+.1f}名/日。稼働率は横ばいです。"
                             "目標稼働率を下回っている場合は、紹介元への連携を少し強化してください。"))
        else:
            _actions.append(("🔴", "退院超過が続いています",
                             f"直近7日の純増減 {_net_7d:+.1f}名/日。入院が退院に追いついていません。  \n"
                             "**入院促進策:** 紹介元への空床情報の発信、救急受入枠の拡大、地域連携室との退院調整日の見直し"))

        # 空床数に基づく判定
        if _empty_beds <= 3:
            _actions.append(("🟢", f"空床わずか（{_empty_beds}床）",
                             "ほぼ満床です。退院調整を計画的に進め、新規入院の受入枠を確保してください。"))
        elif _empty_beds <= round(_view_beds * (1 - target_lower)):
            _actions.append(("🟡", f"空床 {_empty_beds}床（目標範囲内）",
                             f"入院ペース {_adm_7d:.1f}名/日が維持されれば問題ありません。"))
        else:
            _need_extra = _empty_beds - round(_view_beds * (1 - target_lower))
            _actions.append(("🔴", f"空床 {_empty_beds}床（目標超過）",
                             f"目標稼働率を達成するにはあと **{_need_extra}名** の入院が必要です。  \n"
                             "**対策:** 紹介元への積極的な空床案内、地域連携室との連携強化"))

        # 入退院比率に基づく判定
        _ratio_7d = _adm_7d / max(_dis_7d, 0.1)
        if _ratio_7d < 0.8:
            _actions.append(("🔴", f"入退院比率 {_ratio_7d:.2f}（入院不足）",
                             "退院10名に対して入院8名未満。入院の「入口」に課題があります。  \n"
                             "紹介元別の入院数を確認し、減少している紹介元をフォローしてください。"))
        elif _ratio_7d < 1.0:
            _actions.append(("🟡", f"入退院比率 {_ratio_7d:.2f}（やや入院不足）",
                             "入院がわずかに退院を下回っています。トレンドの推移を注視してください。"))

        for icon, title, msg in _actions:
            bg = "#e8f5e9" if icon == "🟢" else "#fff3e0" if icon == "🟡" else "#ffebee"
            border = "#27AE60" if icon == "🟢" else "#F39C12" if icon == "🟡" else "#E74C3C"
            st.markdown(f"""
<div style="background:{bg};border-radius:10px;padding:14px;margin-bottom:10px;border-left:5px solid {border};">
<strong>{icon} {title}</strong><br>{msg}
</div>""", unsafe_allow_html=True)


# ===== タブ: データ =====
with tabs[_tab_idx["データ"]]:
    st.subheader("日次データ")
    if _HELP_AVAILABLE and "tab_data" in HELP_TEXTS:
        with st.expander("📖 このタブの見方と活用法"):
            st.markdown(HELP_TEXTS["tab_data"])

    # データ表示
    display_df = df.copy()
    display_df["稼働率"] = (display_df["稼働率"] * 100).round(1)
    st.dataframe(display_df, width="stretch", height=500)

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
# タブ: ⚙️ 医師マスター
# ---------------------------------------------------------------------------
if _DOCTOR_MASTER_AVAILABLE and "⚙️ 医師マスター" in _tab_idx:
    with tabs[_tab_idx["⚙️ 医師マスター"]]:
        st.subheader("⚙️ 医師マスター設定")
        st.caption("入退院データに紐づける医師・入院経路を管理します")

        _doc_tab1, _doc_tab2 = st.tabs(["👨‍⚕️ 医師管理", "🛣️ 入院経路管理"])

        with _doc_tab1:
            # --- Add doctor form ---
            with st.form("add_doctor_form"):
                st.markdown("##### 医師を追加")
                _doc_col1, _doc_col2 = st.columns(2)
                with _doc_col1:
                    _new_doc_name = st.text_input("医師名", placeholder="例: 田中太郎")
                with _doc_col2:
                    _new_doc_cat = st.selectbox("区分", ["常勤病棟担当", "常勤外来のみ", "非常勤", "常勤救急応援"])
                _add_doc_submit = st.form_submit_button("追加", type="primary")
                if _add_doc_submit and _new_doc_name.strip():
                    dm_doctor.add_doctor(_new_doc_name.strip(), _new_doc_cat)
                    st.success(f"✅ {_new_doc_name} を追加しました")
                    st.rerun()

            # --- Current doctor list ---
            st.markdown("##### 登録済み医師一覧")
            _active_docs = dm_doctor.get_active_doctors()
            if len(_active_docs) > 0:
                _doc_display = pd.DataFrame(_active_docs)[["name", "category"]]
                _doc_display.columns = ["医師名", "区分"]
                st.dataframe(_doc_display, use_container_width=True, hide_index=True)

                # Delete doctor
                with st.expander("医師を削除"):
                    _del_doc_name = st.selectbox("削除する医師", [d["name"] for d in _active_docs], key="del_doc_select")
                    if st.button("削除", key="del_doc_btn"):
                        _del_doc = next((d for d in _active_docs if d["name"] == _del_doc_name), None)
                        if _del_doc:
                            dm_doctor.deactivate_doctor(_del_doc["id"])
                            st.success(f"✅ {_del_doc_name} を削除しました")
                            st.rerun()
            else:
                st.info("医師が登録されていません。上のフォームから追加してください。")

        with _doc_tab2:
            # --- Current routes ---
            st.markdown("##### 入院経路一覧")
            _routes = dm_doctor.get_admission_routes()
            for r in _routes:
                st.write(f"• {r}")

            # --- Add route ---
            with st.form("add_route_form"):
                _new_route = st.text_input("新しい入院経路", placeholder="例: 院内紹介")
                _add_route_submit = st.form_submit_button("追加")
                if _add_route_submit and _new_route.strip():
                    dm_doctor.add_admission_route(_new_route.strip())
                    st.success(f"✅ {_new_route} を追加しました")
                    st.rerun()

            # --- Remove route ---
            with st.expander("入院経路を削除"):
                _del_route = st.selectbox("削除する経路", _routes, key="del_route_select")
                if st.button("削除", key="del_route_btn"):
                    dm_doctor.remove_admission_route(_del_route)
                    st.success(f"✅ {_del_route} を削除しました")
                    st.rerun()

# ---------------------------------------------------------------------------
# タブ: 👨‍⚕️ 医師別分析
# ---------------------------------------------------------------------------
if _DOCTOR_MASTER_AVAILABLE and _DETAIL_DATA_AVAILABLE and "👨‍⚕️ 医師別分析" in _tab_idx:
    with tabs[_tab_idx["👨‍⚕️ 医師別分析"]]:
        st.subheader("👨‍⚕️ 医師別分析")

        _detail_df = st.session_state.get("admission_details", pd.DataFrame())

        if not isinstance(_detail_df, pd.DataFrame) or len(_detail_df) == 0:
            st.info("入退院詳細データがありません。「日次データ入力」タブで入退院を記録してください。")
        else:
            # Month selector
            _detail_df["date"] = pd.to_datetime(_detail_df["date"])
            _available_months = sorted(_detail_df["date"].dt.to_period("M").unique())
            _month_options = [str(m) for m in _available_months]
            _selected_month = st.selectbox("分析月", _month_options, index=len(_month_options)-1 if _month_options else 0)

            if _selected_month:
                _monthly_summary = get_monthly_summary_by_doctor(_detail_df, _selected_month)

                if _monthly_summary:
                    # --- Overview metrics ---
                    _total_adm = sum(d.get("admissions", 0) for d in _monthly_summary.values())
                    _total_dis = sum(d.get("discharges", 0) for d in _monthly_summary.values())
                    _total_created = sum(d.get("admissions_created", 0) for d in _monthly_summary.values())

                    _ov_col1, _ov_col2, _ov_col3 = st.columns(3)
                    with _ov_col1:
                        st.metric("月間入院数", f"{_total_adm}件")
                    with _ov_col2:
                        st.metric("月間退院数", f"{_total_dis}件")
                    with _ov_col3:
                        st.metric("入院創出（記録あり）", f"{_total_created}件")

                    st.markdown("---")

                    # --- Doctor-level table ---
                    st.markdown("#### 医師別パフォーマンス")
                    _doc_rows = []
                    for doc_name, stats in sorted(_monthly_summary.items()):
                        _doc_rows.append({
                            "医師名": doc_name,
                            "入院担当": stats.get("admissions", 0),
                            "入院創出": stats.get("admissions_created", 0),
                            "退院": stats.get("discharges", 0),
                            "平均在院日数": f"{stats.get('avg_los', 0):.1f}" if stats.get("avg_los") else "-",
                            "A群": stats.get("phase_a", 0),
                            "B群": stats.get("phase_b", 0),
                            "C群": stats.get("phase_c", 0),
                        })
                    if _doc_rows:
                        st.dataframe(pd.DataFrame(_doc_rows), use_container_width=True, hide_index=True)

                    # --- Discharge weekday distribution ---
                    st.markdown("#### 退院曜日分布")
                    _weekday_dist = get_discharge_weekday_distribution(_detail_df)
                    if _weekday_dist:
                        _wd_labels = ["月", "火", "水", "木", "金", "土", "日"]
                        _wd_values = [_weekday_dist.get(i, 0) for i in range(7)]

                        fig_wd, ax_wd = plt.subplots(figsize=(8, 3))
                        _wd_colors = ["#2563EB" if i < 5 else "#EF4444" for i in range(7)]
                        ax_wd.bar(_wd_labels, _wd_values, color=_wd_colors)
                        ax_wd.set_ylabel("退院件数")
                        ax_wd.set_title("全体の退院曜日分布")
                        st.pyplot(fig_wd)
                        plt.close(fig_wd)

                        # Check Friday concentration
                        _total_dis_wd = sum(_wd_values)
                        if _total_dis_wd > 0:
                            _fri_pct = _wd_values[4] / _total_dis_wd * 100
                            if _fri_pct > 30:
                                _fri_loss = _wd_values[4] * 0.25 * 2 * _UNIT_PRICE_PER_DAY  # rough estimate
                                st.warning(f"⚠️ 金曜退院が全体の{_fri_pct:.0f}%を占めています。週末の稼働率低下の要因の可能性があります。")

                    # --- Per-doctor weekday heatmap ---
                    st.markdown("#### 医師別 退院曜日パターン")
                    _doc_names_in_data = _detail_df[_detail_df["event_type"] == "discharge"]["attending_doctor"].unique()
                    for _dn in sorted(_doc_names_in_data):
                        _doc_wd = get_discharge_weekday_distribution(_detail_df, _dn)
                        if _doc_wd and sum(_doc_wd.values()) > 0:
                            _wd_vals = [_doc_wd.get(i, 0) for i in range(7)]
                            _total_d = sum(_wd_vals)
                            _fri_ratio = _wd_vals[4] / _total_d * 100 if _total_d > 0 else 0
                            _pattern = " ".join([f"{_wd_labels[i]}:{_wd_vals[i]}" for i in range(7)])
                            _flag = " ⚠️金曜集中" if _fri_ratio > 40 else ""
                            st.write(f"**{_dn}**: {_pattern} （金曜率{_fri_ratio:.0f}%）{_flag}")
                else:
                    st.info(f"{_selected_month} のデータがありません")

# ---------------------------------------------------------------------------
# タブ: 💡 改善のヒント（インタラクティブ What-If シミュレーション付き）
# ---------------------------------------------------------------------------
if _DOCTOR_MASTER_AVAILABLE and _DETAIL_DATA_AVAILABLE and "💡 改善のヒント" in _tab_idx:
    with tabs[_tab_idx["💡 改善のヒント"]]:
        import plotly.graph_objects as go

        st.subheader("💡 改善のヒント")
        st.caption("運用データから改善の種を自動検出し、What-Ifシミュレーションで効果を試算します")

        _detail_df = st.session_state.get("admission_details", pd.DataFrame())
        _daily_df = st.session_state.get("daily_data", pd.DataFrame())
        _wd_labels = ["月", "火", "水", "木", "金", "土", "日"]

        _hints_found = False
        # 各ヒントの改善額を積み上げ用に記録
        _hint_savings = {}
        _avg_occ_7d = None  # Hint 1 で算出、Hint 5 で参照

        # =====================================================================
        # Hint 1: 稼働率ギャップ
        # =====================================================================
        if isinstance(_daily_df, pd.DataFrame) and len(_daily_df) > 0:
            if "ward" in _daily_df.columns:
                # 病棟別データの場合、日付ごとに合算してから直近7日を取得
                _agg_daily = _daily_df.groupby("date").agg({"total_patients": "sum"}).reset_index()
                _latest_data = _agg_daily.sort_values("date").tail(7)
            else:
                _latest_data = _daily_df.sort_values("date").tail(7)
            _avg_occ_7d = _latest_data["total_patients"].mean() / _TOTAL_BEDS_METRIC * 100
            _gap = 90 - _avg_occ_7d
            if _gap > 0:
                _hints_found = True
                _annual_loss = _gap * _ANNUAL_VALUE_PER_1PCT / 100
                _profit_pct = _annual_loss / _OPERATING_PROFIT * 100

                with st.expander("⚠️ 稼働率ギャップ", expanded=True):
                    # --- 検出アラート ---
                    st.markdown(f"""
                    <div style="background: #FFF7ED; border-left: 4px solid #F97316; padding: 16px; border-radius: 4px; margin-bottom: 16px;">
                        <strong style="color: #1E293B; font-size: 16px;">⚠️ 稼働率ギャップ検出</strong><br>
                        <span style="color: #64748B;">直近7日間の平均稼働率: <strong>{_avg_occ_7d:.1f}%</strong>（目標90%まであと<strong>{_gap:.1f}%</strong>）</span><br>
                        <span style="color: #EF4444; font-weight: bold;">年間推定ロス: {_annual_loss/10000:.0f}万円（営業利益の{_profit_pct:.0f}%相当）</span>
                    </div>
                    """, unsafe_allow_html=True)

                    # --- What-If シミュレーション ---
                    st.markdown("##### 🔧 What-If シミュレーション")
                    _hint1_default = min(_gap, 5.0)
                    _hint1_default_rounded = round(_hint1_default * 2) / 2  # 0.5刻みに丸め
                    _hint1_target = st.slider(
                        "稼働率改善目標（%ポイント）",
                        min_value=0.5, max_value=5.0, step=0.5,
                        value=min(_hint1_default_rounded, 5.0),
                        key="_hint_occ_slider",
                    )
                    _hint1_annual_value = _hint1_target * _ANNUAL_VALUE_PER_1PCT / 100
                    _hint1_profit_impact = _hint1_annual_value / _OPERATING_PROFIT * 100
                    _hint1_per_person = _hint1_annual_value * 0.58 / 290  # 人件費率58%, 290人

                    _hint_savings["稼働率改善"] = _hint1_annual_value

                    _h1c1, _h1c2 = st.columns(2)
                    with _h1c1:
                        st.metric("現在の稼働率", f"{_avg_occ_7d:.1f}%")
                    with _h1c2:
                        st.metric("改善後の稼働率", f"{_avg_occ_7d + _hint1_target:.1f}%", delta=f"+{_hint1_target:.1f}%")

                    st.info(
                        f"もし稼働率を **{_hint1_target:.1f}%** 改善できたら → "
                        f"年間 **{_hint1_annual_value/10000:.0f}万円** の改善 "
                        f"（営業利益の **{_hint1_profit_impact:.0f}%** 相当、"
                        f"職員一人あたり年間 **{_hint1_per_person/10000:.1f}万円**）"
                    )

        # =====================================================================
        # Hint 2: 金曜退院の集中
        # =====================================================================
        if isinstance(_detail_df, pd.DataFrame) and len(_detail_df) > 0:
            _wd_dist = get_discharge_weekday_distribution(_detail_df)
            if _wd_dist:
                _total_dis_h = sum(_wd_dist.values())
                if _total_dis_h > 0:
                    _fri_count = _wd_dist.get(4, 0)
                    _fri_pct_h = _fri_count / _total_dis_h * 100
                    if _fri_pct_h > 25:
                        _hints_found = True
                        _expected_even = _total_dis_h / 5
                        _excess_fri = _fri_count - _expected_even

                        with st.expander("⚠️ 金曜退院の集中", expanded=True):
                            # --- 検出アラート ---
                            st.markdown(f"""
                            <div style="background: #FFF7ED; border-left: 4px solid #F97316; padding: 16px; border-radius: 4px; margin-bottom: 16px;">
                                <strong style="color: #1E293B; font-size: 16px;">⚠️ 金曜退院の集中検出</strong><br>
                                <span style="color: #64748B;">金曜退院: {_fri_count}件（全体の<strong>{_fri_pct_h:.0f}%</strong>）→ 土日の稼働率低下の要因</span>
                            </div>
                            """, unsafe_allow_html=True)

                            # --- 医師別の金曜集中テーブル ---
                            st.markdown("##### 📋 医師別 金曜退院率")
                            _dis_df_h2 = _detail_df[_detail_df["event_type"] == "discharge"]
                            _doc_names_h2 = sorted(_dis_df_h2["attending_doctor"].unique())
                            _fri_table_rows = []
                            for _dn in _doc_names_h2:
                                _doc_wd = get_discharge_weekday_distribution(_detail_df, _dn)
                                if _doc_wd and sum(_doc_wd.values()) > 0:
                                    _d_total = sum(_doc_wd.values())
                                    _d_fri = _doc_wd.get(4, 0)
                                    _d_fri_pct = _d_fri / _d_total * 100
                                    _fri_table_rows.append({
                                        "医師名": _dn,
                                        "総退院数": _d_total,
                                        "金曜退院数": _d_fri,
                                        "金曜率(%)": round(_d_fri_pct, 1),
                                        "集中": "⚠️" if _d_fri_pct > 30 else "",
                                    })
                            if _fri_table_rows:
                                _fri_table_df = pd.DataFrame(_fri_table_rows).sort_values("金曜率(%)", ascending=False)
                                st.dataframe(_fri_table_df, use_container_width=True, hide_index=True)

                            # --- What-If シミュレーション ---
                            st.markdown("##### 🔧 What-If シミュレーション")
                            _hint2_move_pct = st.slider(
                                "金曜退院のうち火〜木へ移動する割合（%）",
                                min_value=0, max_value=100, step=10, value=50,
                                key="_hint_fri_slider",
                            )
                            _hint2_moved = int(_excess_fri * _hint2_move_pct / 100)
                            _hint2_weekend_saved = _hint2_moved * 2 * _UNIT_PRICE_PER_DAY
                            _hint2_annual = _hint2_weekend_saved * 12
                            _hint2_profit_pct = _hint2_annual / _OPERATING_PROFIT * 100

                            _hint_savings["金曜退院分散"] = _hint2_annual

                            # Before/After の曜日分布チャート
                            _before_vals = [_wd_dist.get(i, 0) for i in range(7)]
                            _after_vals = list(_before_vals)
                            # 金曜から火〜木へ均等に振り分け
                            _after_vals[4] = max(0, _after_vals[4] - _hint2_moved)
                            _per_day_add = _hint2_moved / 3  # 火・水・木に均等配分
                            for _di in [1, 2, 3]:
                                _after_vals[_di] += _per_day_add

                            _fig_h2 = go.Figure()
                            _fig_h2.add_trace(go.Bar(
                                x=_wd_labels, y=_before_vals,
                                name="現在", marker_color="#94A3B8",
                            ))
                            _fig_h2.add_trace(go.Bar(
                                x=_wd_labels, y=_after_vals,
                                name="改善後", marker_color="#3B82F6",
                            ))
                            _fig_h2.update_layout(
                                barmode="group", height=300,
                                title="退院の曜日分布（現在 vs 改善後）",
                                xaxis_title="曜日", yaxis_title="退院件数",
                                margin=dict(t=40, b=40, l=40, r=20),
                            )
                            st.plotly_chart(_fig_h2, use_container_width=True)

                            _h2c1, _h2c2 = st.columns(2)
                            with _h2c1:
                                st.metric("移動する退院件数", f"{_hint2_moved}件/月")
                            with _h2c2:
                                st.metric("年間改善額", f"{_hint2_annual/10000:.0f}万円",
                                          delta=f"営業利益の{_hint2_profit_pct:.0f}%")

        # =====================================================================
        # Hint 3: 医師別の退院曜日偏り
        # =====================================================================
        if isinstance(_detail_df, pd.DataFrame) and len(_detail_df) > 0:
            _dis_df_h3 = _detail_df[_detail_df["event_type"] == "discharge"]
            _doc_names_h3 = sorted(_dis_df_h3["attending_doctor"].unique())
            if len(_doc_names_h3) > 0:
                with st.expander("🔍 医師別の退院曜日偏り", expanded=False):
                    st.markdown("""
                    <div style="background: #EFF6FF; border-left: 4px solid #3B82F6; padding: 16px; border-radius: 4px; margin-bottom: 16px;">
                        <strong style="color: #1E293B; font-size: 16px;">🔍 医師別 退院曜日パターン分析</strong><br>
                        <span style="color: #64748B;">特定の医師の退院曜日を調整した場合の効果をシミュレーションします</span>
                    </div>
                    """, unsafe_allow_html=True)

                    _hint3_doc = st.selectbox(
                        "分析する医師を選択",
                        _doc_names_h3,
                        key="_hint_doc_select",
                    )
                    _doc_wd_h3 = get_discharge_weekday_distribution(_detail_df, _hint3_doc)
                    if _doc_wd_h3 and sum(_doc_wd_h3.values()) > 0:
                        _doc_vals_h3 = [_doc_wd_h3.get(i, 0) for i in range(7)]
                        _doc_total_h3 = sum(_doc_vals_h3)
                        _doc_fri_h3 = _doc_vals_h3[4]

                        # 医師の現在の分布チャート
                        _fig_h3 = go.Figure()
                        _colors_h3 = ["#3B82F6" if i != 4 else "#EF4444" for i in range(7)]
                        _fig_h3.add_trace(go.Bar(
                            x=_wd_labels, y=_doc_vals_h3,
                            marker_color=_colors_h3,
                        ))
                        _fig_h3.update_layout(
                            height=250,
                            title=f"{_hint3_doc} の退院曜日分布",
                            xaxis_title="曜日", yaxis_title="退院件数",
                            margin=dict(t=40, b=40, l=40, r=20),
                            showlegend=False,
                        )
                        st.plotly_chart(_fig_h3, use_container_width=True)

                        # What-If: この医師の金曜退院を移動
                        st.markdown("##### 🔧 What-If シミュレーション")
                        _hint3_max_move = max(int(_doc_fri_h3), 0)
                        if _hint3_max_move > 0:
                            _hint3_move = st.slider(
                                f"この医師の金曜退院を何件火〜木に移動？",
                                min_value=0, max_value=_hint3_max_move, step=1,
                                value=min(_hint3_max_move, max(1, _hint3_max_move // 2)),
                                key="_hint_doc_fri_slider",
                            )
                            _hint3_saved = _hint3_move * 2 * _UNIT_PRICE_PER_DAY * 12
                            _hint3_profit = _hint3_saved / _OPERATING_PROFIT * 100

                            _hint_savings[f"{_hint3_doc}退院調整"] = _hint3_saved

                            # Before/After
                            _after_h3 = list(_doc_vals_h3)
                            _after_h3[4] = max(0, _after_h3[4] - _hint3_move)
                            _per_day_h3 = _hint3_move / 3
                            for _di in [1, 2, 3]:
                                _after_h3[_di] += _per_day_h3

                            _fig_h3b = go.Figure()
                            _fig_h3b.add_trace(go.Bar(x=_wd_labels, y=_doc_vals_h3, name="現在", marker_color="#94A3B8"))
                            _fig_h3b.add_trace(go.Bar(x=_wd_labels, y=_after_h3, name="改善後", marker_color="#3B82F6"))
                            _fig_h3b.update_layout(
                                barmode="group", height=250,
                                title=f"{_hint3_doc}: 退院曜日（現在 vs 改善後）",
                                xaxis_title="曜日", yaxis_title="退院件数",
                                margin=dict(t=40, b=40, l=40, r=20),
                            )
                            st.plotly_chart(_fig_h3b, use_container_width=True)

                            _h3c1, _h3c2 = st.columns(2)
                            with _h3c1:
                                st.metric("移動する退院件数", f"{_hint3_move}件/月")
                            with _h3c2:
                                st.metric("年間改善額", f"{_hint3_saved/10000:.0f}万円",
                                          delta=f"営業利益の{_hint3_profit:.0f}%")
                        else:
                            st.info(f"{_hint3_doc} の金曜退院は0件です。調整の必要はありません。")
                    else:
                        st.info(f"{_hint3_doc} の退院データがありません。")

        # =====================================================================
        # Hint 4: 在院日数の最適化
        # =====================================================================
        if isinstance(_detail_df, pd.DataFrame) and len(_detail_df) > 0:
            _dis_df_h4 = _detail_df[_detail_df["event_type"] == "discharge"].copy()
            if "los_days" in _dis_df_h4.columns and len(_dis_df_h4) > 0:
                # 医師別の平均在院日数を算出
                _dis_df_h4["los_days"] = pd.to_numeric(_dis_df_h4["los_days"], errors="coerce")
                _los_by_doc = _dis_df_h4.groupby("attending_doctor")["los_days"].agg(["mean", "count"]).reset_index()
                _los_by_doc.columns = ["医師名", "平均在院日数", "退院件数"]
                _los_by_doc = _los_by_doc[_los_by_doc["退院件数"] >= 2]  # 2件以上のみ

                # 極端な在院日数を検出（< 7日 or > 18日）
                _short_los = _los_by_doc[_los_by_doc["平均在院日数"] < 7]
                _long_los = _los_by_doc[_los_by_doc["平均在院日数"] > 18]
                _has_outlier = len(_short_los) > 0 or len(_long_los) > 0

                if _has_outlier or len(_los_by_doc) > 0:
                    with st.expander("📊 在院日数の最適化", expanded=_has_outlier):
                        if _has_outlier:
                            _outlier_msgs = []
                            for _, _r in _short_los.iterrows():
                                _outlier_msgs.append(f"{_r['医師名']}: 平均{_r['平均在院日数']:.1f}日（短い）")
                            for _, _r in _long_los.iterrows():
                                _outlier_msgs.append(f"{_r['医師名']}: 平均{_r['平均在院日数']:.1f}日（長い）")
                            st.markdown(f"""
                            <div style="background: #FFF7ED; border-left: 4px solid #F97316; padding: 16px; border-radius: 4px; margin-bottom: 16px;">
                                <strong style="color: #1E293B; font-size: 16px;">📊 在院日数の偏り検出</strong><br>
                                <span style="color: #64748B;">{"、".join(_outlier_msgs)}</span>
                            </div>
                            """, unsafe_allow_html=True)
                            _hints_found = True
                        else:
                            st.markdown("""
                            <div style="background: #EFF6FF; border-left: 4px solid #3B82F6; padding: 16px; border-radius: 4px; margin-bottom: 16px;">
                                <strong style="color: #1E293B; font-size: 16px;">📊 在院日数の最適化シミュレーション</strong><br>
                                <span style="color: #64748B;">医師別の在院日数を調整した場合の効果を試算します</span>
                            </div>
                            """, unsafe_allow_html=True)

                        # 医師別在院日数テーブル
                        st.markdown("##### 📋 医師別 平均在院日数")
                        _los_display = _los_by_doc.copy()
                        _los_display["平均在院日数"] = _los_display["平均在院日数"].round(1)
                        st.dataframe(_los_display, use_container_width=True, hide_index=True)

                        # What-If シミュレーション
                        st.markdown("##### 🔧 What-If シミュレーション")
                        _h4_doc_list = _los_by_doc["医師名"].tolist()
                        _h4_doc = st.selectbox(
                            "在院日数を調整する医師を選択",
                            _h4_doc_list,
                            key="_hint_los_doc_select",
                        )
                        _h4_current_los = float(_los_by_doc[_los_by_doc["医師名"] == _h4_doc]["平均在院日数"].iloc[0])
                        _h4_doc_count = int(_los_by_doc[_los_by_doc["医師名"] == _h4_doc]["退院件数"].iloc[0])

                        _h4_adjust = st.slider(
                            "平均在院日数の調整（日）",
                            min_value=-3.0, max_value=3.0, step=0.5, value=0.0,
                            key="_hint_los_slider",
                            help="マイナス=早期退院、プラス=延長",
                        )
                        _h4_new_los = max(1.0, _h4_current_los + _h4_adjust)

                        _h4c1, _h4c2 = st.columns(2)
                        with _h4c1:
                            st.metric("現在の平均在院日数", f"{_h4_current_los:.1f}日")
                        with _h4c2:
                            st.metric("調整後の平均在院日数", f"{_h4_new_los:.1f}日",
                                      delta=f"{_h4_adjust:+.1f}日")

                        # 効果試算
                        if _h4_adjust != 0:
                            # 在院日数が短くなる → 空いたベッドに新入院を入れられるポテンシャル
                            # 在院日数が長くなる → 稼働率は上がるが回転率が下がる
                            _h4_bed_days_change = _h4_adjust * _h4_doc_count  # 月あたりベッド日数変化
                            if _h4_adjust < 0:
                                # 早期退院 → 新入院受入ポテンシャル
                                _h4_new_admissions = abs(_h4_bed_days_change) / max(_h4_new_los, 1)
                                _h4_annual_value = abs(_h4_bed_days_change) * _UNIT_PRICE_PER_DAY * 12
                                _h4_profit_pct = _h4_annual_value / _OPERATING_PROFIT * 100
                                _hint_savings[f"{_h4_doc}在院日数最適化"] = _h4_annual_value
                                st.success(
                                    f"もし{_h4_doc}の患者が平均{abs(_h4_adjust):.1f}日早く退院し、"
                                    f"空いたベッドに新入院が入れば → "
                                    f"月{abs(_h4_bed_days_change):.0f}ベッド日 × 年間 = "
                                    f"**{_h4_annual_value/10000:.0f}万円** の改善ポテンシャル"
                                    f"（営業利益の**{_h4_profit_pct:.0f}%**相当）"
                                )
                            else:
                                # 延長 → 稼働率は上がるがコスト増
                                _h4_occ_gain = _h4_bed_days_change / (_TOTAL_BEDS_METRIC * 30) * 100
                                _h4_annual_gain = _h4_occ_gain * _ANNUAL_VALUE_PER_1PCT / 100
                                _hint_savings[f"{_h4_doc}在院日数延長"] = _h4_annual_gain
                                st.info(
                                    f"在院日数を{_h4_adjust:.1f}日延長 → "
                                    f"稼働率が約{_h4_occ_gain:.2f}%上昇 → "
                                    f"年間 **{_h4_annual_gain/10000:.0f}万円** の効果"
                                    f"（ただし回転率は低下します）"
                                )
                        else:
                            st.caption("スライダーを動かして在院日数の調整効果をシミュレーションしてください。")

        # =====================================================================
        # Hint 5: 改善の積み重ね効果（全スライダーの合計を動的に集計）
        # =====================================================================
        if _hints_found or len(_hint_savings) > 0:
            st.markdown("---")
            st.markdown("#### 🏗️ 改善の積み重ね効果")

            # 基本指標テーブル
            st.markdown(f"""
            | 指標 | 数値 |
            |------|------|
            | 稼働率1% の年間価値 | **{_ANNUAL_VALUE_PER_1PCT/10000:.0f}万円** |
            | 営業利益に対する比率 | **{_ANNUAL_VALUE_PER_1PCT/_OPERATING_PROFIT*100:.0f}%** |
            | 人件費率58%換算（290人） | 一人あたり年間 **約{_ANNUAL_VALUE_PER_1PCT*0.58/290/10000:.1f}万円** |
            """)

            # 各ヒントの積み上げサマリー
            if len(_hint_savings) > 0:
                _stack_rows = []
                for _hint_name, _hint_val in _hint_savings.items():
                    _stack_rows.append({
                        "改善項目": _hint_name,
                        "年間改善額（万円）": round(_hint_val / 10000),
                        "営業利益比（%）": round(_hint_val / _OPERATING_PROFIT * 100, 1),
                    })
                _stack_df = pd.DataFrame(_stack_rows)
                _total_savings = sum(_hint_savings.values())
                _stack_rows.append({
                    "改善項目": "合計",
                    "年間改善額（万円）": round(_total_savings / 10000),
                    "営業利益比（%）": round(_total_savings / _OPERATING_PROFIT * 100, 1),
                })
                _stack_df = pd.DataFrame(_stack_rows)
                st.dataframe(_stack_df, use_container_width=True, hide_index=True)

                # 改善後の稼働率予測
                if isinstance(_daily_df, pd.DataFrame) and len(_daily_df) > 0:
                    _curr_occ = _avg_occ_7d if _avg_occ_7d is not None else 85.0
                    _occ_improvement = _total_savings / _ANNUAL_VALUE_PER_1PCT * 100
                    _new_occ = _curr_occ + _occ_improvement
                    st.success(
                        f"すべての改善を実現した場合 → "
                        f"稼働率 **{_curr_occ:.1f}%** → **{min(_new_occ, 100):.1f}%** "
                        f"（+{_occ_improvement:.1f}%）、"
                        f"年間 **{_total_savings/10000:.0f}万円** の改善"
                    )
            else:
                st.info("個別の改善は小さくても、積み重ねることで大きな効果になります。")

        if not _hints_found and len(_hint_savings) == 0:
            st.success("現時点で特に改善が必要なヒントはありません。データが蓄積されると自動で検出されます。")

# ---------------------------------------------------------------------------
# フッター
# ---------------------------------------------------------------------------
st.markdown("---")
if _is_actual_data_mode:
    _footer_ward = f" ({_selected_ward_key})" if _selected_ward_key != "全体" else ""
    st.caption(
        f"データソース: **実績データ{_footer_ward}** | "
        f"病床数: {_view_beds} | "
        f"目標稼働率: {target_lower*100:.0f}-{target_upper*100:.0f}%"
    )
else:
    st.caption(
        f"戦略: **{strategy}** | "
        f"病床数: {_view_beds} | "
        f"目標稼働率: {target_lower*100:.0f}-{target_upper*100:.0f}% | "
        f"月間入院: {monthly_admissions}件 | "
        f"平均在院日数: {avg_los}日"
    )
