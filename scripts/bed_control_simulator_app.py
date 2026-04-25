# 実行方法: streamlit run scripts/bed_control_simulator_app.py
# v3.5.1 — 2026年改定対応（施設基準計算）
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
from datetime import date, timedelta

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
        calculate_rolling_los,
        calculate_ideal_phase_ratios,
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
        parse_discharge_los_list,
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
    import traceback as _db_tb
    _DB_ERROR = f"{_db_err}\n{_db_tb.format_exc()}"

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
    import traceback as _doc_tb
    _DOCTOR_MASTER_ERROR = f"{_doc_err}\n{_doc_tb.format_exc()}"

# HOPE送信用サマリー生成モジュール
_HOPE_AVAILABLE = False
try:
    from hope_message_generator import render_hope_tab as _render_hope_tab
    _HOPE_AVAILABLE = True
except Exception as _hope_err:
    import traceback as _hope_tb
    _HOPE_ERROR = f"{_hope_err}\n{_hope_tb.format_exc()}"

# シナリオ保存・比較・AI分析マネージャー
_SCENARIO_MANAGER_AVAILABLE = False
try:
    from scenario_manager import (
        save_scenario, load_scenario, list_scenarios, delete_scenario,
        compare_scenarios, analyze_scenarios
    )
    _SCENARIO_MANAGER_AVAILABLE = True
except Exception as _sm_err:
    import traceback as _sm_tb
    _SCENARIO_MANAGER_ERROR = f"{_sm_err}\n{_sm_tb.format_exc()}"

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
        get_discharge_weekday_stats,
        get_sunday_discharge_candidates,
        simulate_discharge_shift,
    )
    _DETAIL_DATA_AVAILABLE = True
except Exception as _detail_err:
    import traceback as _detail_tb
    _DETAIL_DATA_ERROR = f"{_detail_err}\n{_detail_tb.format_exc()}"
    _DETAIL_DATA_AVAILABLE = False

# ---------------------------------------------------------------------------
# 医師別 深掘りインサイトエンジン
# ---------------------------------------------------------------------------
try:
    from doctor_insight_engine import (
        build_doctor_insights as _di_build_doctor_insights,
        build_weekday_insights as _di_build_weekday_insights,
        build_c_group_insights as _di_build_c_group_insights,
    )
    _DOCTOR_INSIGHT_AVAILABLE = True
except Exception as _di_err:
    import traceback as _di_tb
    _DOCTOR_INSIGHT_ERROR = f"{_di_err}\n{_di_tb.format_exc()}"
    _DOCTOR_INSIGHT_AVAILABLE = False

# ---------------------------------------------------------------------------
# 空床マネジメント指標モジュール
# ---------------------------------------------------------------------------
try:
    from bed_management_metrics import (
        prepare_bed_mgmt_daily_df,
        calculate_weekend_empty_metrics,
        calculate_next_day_reuse_rate,
        calculate_weekend_costs,
        calculate_weekend_whatif,
        calculate_unfilled_discharge_queue,
    )
    _BED_MGMT_METRICS_AVAILABLE = True
except Exception as _bmm_err:
    import traceback as _bmm_tb
    _BED_MGMT_METRICS_ERROR = f"{_bmm_err}\n{_bmm_tb.format_exc()}"
    _BED_MGMT_METRICS_AVAILABLE = False

# Phase 3α: 需要条件付き木曜前倒しロジック
try:
    from demand_forecast import (
        load_historical_admissions,
        forecast_weekly_demand,
        estimate_existing_vacancy,
    )
    _DEMAND_FORECAST_AVAILABLE = True
except Exception as _df_err:
    import traceback as _df_tb
    _DEMAND_FORECAST_ERROR = f"{_df_err}\n{_df_tb.format_exc()}"
    _DEMAND_FORECAST_AVAILABLE = False

# ---------------------------------------------------------------------------
# 施設基準チェック・需要波・C群コントロール
# ---------------------------------------------------------------------------
_GUARDRAIL_AVAILABLE = False
try:
    from guardrail_engine import (
        calculate_los_limit,
        calculate_guardrail_status,
        calculate_los_headroom,
        format_guardrail_display,
    )
    from demand_wave import (
        calculate_demand_trend,
        classify_demand_period,
        calculate_dow_pattern,
        calculate_demand_score,
        detect_demand_alerts,
        calculate_route_demand_trend,
    )
    from c_group_control import (
        get_c_group_summary,
        calculate_c_adjustment_capacity,
        simulate_c_group_scenario,
        calculate_demand_absorption,
        generate_c_group_alerts,
        C_CONTRIBUTION_PER_DAY,
    )
    from emergency_ratio import (
        calculate_emergency_ratio,
        calculate_rolling_emergency_ratio,
        calculate_dual_ratio,
        project_month_end,
        calculate_additional_needed,
        generate_emergency_alerts,
        get_ward_emergency_summary,
        get_monthly_history,
        get_cumulative_progress,
        EMERGENCY_THRESHOLD_PCT,
        estimate_next_morning_capacity,
        TRANSITIONAL_END_DATE,
        days_until_transitional_end,
        is_transitional_period,
    )
    _GUARDRAIL_AVAILABLE = True
    _EMERGENCY_RATIO_AVAILABLE = True
except Exception as _gr_err:
    import traceback as _gr_tb
    _GUARDRAIL_ERROR = f"{_gr_err}\n{_gr_tb.format_exc()}"
    _EMERGENCY_RATIO_AVAILABLE = False

# 過去入院データ（2025年度事務提供 CSV）ローダー
# 日次入力が 3 ヶ月貯まるまで救急15% の rolling 計算を補完する。
try:
    from past_admissions_loader import (
        load_past_admissions,
        to_monthly_summary as past_to_monthly_summary,
    )
    _PAST_ADMISSIONS_AVAILABLE = True
except Exception:
    _PAST_ADMISSIONS_AVAILABLE = False

# 看護必要度モジュール（Stage A, 2026-04-25 追加）
try:
    from nursing_necessity_loader import (
        load_nursing_necessity,
        calculate_monthly_summary as nn_calculate_monthly_summary,
        calculate_yearly_average as nn_calculate_yearly_average,
    )
    from nursing_necessity_thresholds import (
        THRESHOLD_I_LEGACY,
        THRESHOLD_I_NEW,
        THRESHOLD_II_LEGACY,
        THRESHOLD_II_NEW,
        EMERGENCY_RESPONSE_COEFFICIENT_CAP,
        calculate_emergency_response_coefficient as nn_calc_response_coef,
        get_threshold as nn_get_threshold,
    )
    from nursing_necessity_lecture import (
        LECTURE_MARKDOWN as _NN_LECTURE_MD,
        render_references as _nn_render_references,
    )
    _NURSING_NECESSITY_AVAILABLE = True
except Exception:
    _NURSING_NECESSITY_AVAILABLE = False
    _NN_LECTURE_MD = ""
    _nn_render_references = None


# ---------------------------------------------------------------------------
# 月別サマリー統合 — 過去1年CSV + 既存 session_state.monthly_summary
# ---------------------------------------------------------------------------
# 救急15% rolling 計算の bootstrap 用途:
#   1. 過去入院データ（事務提供 CSV）から monthly_summary を生成
#   2. session_state.monthly_summary（手動入力）で上書き
#   3. rolling 計算は daily_df → merged summary → manual_seed の優先順位で自動選択
#
# 日次データ（admission_details.csv）が 3 ヶ月分貯まれば自動的に日次優先になり、
# 過去CSV は「古い月の監視」のみに縮退する（副院長指示 2026-04-24）。
def _build_effective_monthly_summary() -> dict:
    """過去CSV と session_state.monthly_summary を merge した辞書を返す。"""
    merged: dict = {}
    if _PAST_ADMISSIONS_AVAILABLE:
        try:
            past_df = st.session_state.get("past_admissions_df")
            if past_df is not None and len(past_df) > 0:
                merged = dict(past_to_monthly_summary(past_df))
        except Exception:
            merged = {}
    # 手動入力サマリーで上書き（副院長が個別修正した値を優先）
    manual_summary = st.session_state.get("monthly_summary", {})
    if isinstance(manual_summary, dict):
        for ym, ward_data in manual_summary.items():
            if ym in merged and isinstance(ward_data, dict):
                # 既存の過去CSV ベースに手動値を shallow merge
                merged[ym] = {**merged[ym], **ward_data}
            else:
                merged[ym] = ward_data
    return merged


# ---------------------------------------------------------------------------
# 救急搬送比率 — 経過措置期間ゲート付きラッパー
# ---------------------------------------------------------------------------
# 2026-05-31 までは令和6改定の経過措置期間（最大3ヶ月の困難時期除外が許容）
# 2026-06-01 以降は本則完全適用 → 判定期間は rolling 3ヶ月（単月ではない）
#   仕様確定日: 2026-04-15（事務担当者確認）
#   詳細: CLAUDE.md「制度ルール確定事項（2026-06-01 以降の地域包括医療病棟運用）」
#
# 経過措置中は既存の calculate_emergency_ratio() を呼び、本則適用後は
# calculate_rolling_emergency_ratio() に自動で切り替える。戻り値の互換性を
# 維持するため、rolling 結果に単月の breakdown を重ねた dict を返す。
def _calc_emergency_ratio_with_gate(detail_df, ward, year_month, target_date,
                                     exclude_short3=False):
    """経過措置ゲート付きの救急搬送比率計算。

    Args:
        detail_df: 入退院詳細データ
        ward: "5F" / "6F" / None
        year_month: "YYYY-MM" 形式の対象月
        target_date: 基準日（経過措置判定用）
        exclude_short3: 後方互換のため保持。2026改定で無視される

    Returns:
        calculate_emergency_ratio() と同形式の dict。
        ゲート内は単月判定、ゲート外は rolling 3ヶ月判定の数値を持つ。
        monthly_breakdown は rolling モードのみ含まれる。
    """
    if not _EMERGENCY_RATIO_AVAILABLE:
        return None

    # 経過措置中 or 本則適用後を判定
    if is_transitional_period(target_date):
        # 経過措置中（〜2026-05-31）: 単月判定（既存挙動）
        return calculate_emergency_ratio(
            detail_df, ward=ward, year_month=year_month,
            exclude_short3=exclude_short3, target_date=target_date,
        )

    # 本則適用（2026-06-01〜）: rolling 3ヶ月判定
    # breakdown / exclude_short3 は単月版から流用（UI の円グラフ等で必要）
    single_month = calculate_emergency_ratio(
        detail_df, ward=ward, year_month=year_month,
        exclude_short3=exclude_short3, target_date=target_date,
    )

    # 過去入院データ（事務提供 CSV）を monthly_summary 形式に変換し、
    # 既存 session_state.monthly_summary と merge（日次データが無い月を補完）。
    # 日次データ > summary > manual_seed の優先順位は emergency_ratio 側で解決。
    _eff_summary = _build_effective_monthly_summary()

    rolling = calculate_rolling_emergency_ratio(
        detail_df, ward=ward, target_date=target_date, window_months=3,
        monthly_summary=_eff_summary,
    )

    # rolling の分子/分母/比率/ステータスで単月の値を上書き
    merged = dict(single_month)
    merged["numerator"] = rolling["numerator"]
    merged["denominator"] = rolling["denominator"]
    merged["ratio_pct"] = rolling["ratio_pct"]
    merged["gap_to_target_pt"] = rolling["gap_to_target_pt"]
    merged["status"] = rolling["status"]
    merged["monthly_breakdown"] = rolling.get("monthly_breakdown", [])
    merged["_rolling_window_months"] = rolling.get("window_months", 3)
    merged["_gate_mode"] = "rolling_3m"
    return merged


# ---------------------------------------------------------------------------
# 結論カード / 今日の一手 / C群候補lite
# ---------------------------------------------------------------------------
_ACTION_CARD_AVAILABLE = False
_ACTION_CARD_ERROR = ""
try:
    from action_recommendation import (
        generate_action_card,
        generate_kpi_priority_list,
        generate_tradeoff_assessment,
    )
    _ACTION_CARD_AVAILABLE = True
except Exception as _ac_err:
    import traceback as _ac_tb
    _ACTION_CARD_ERROR = f"{_ac_err}\n{_ac_tb.format_exc()}"

_C_GROUP_CANDIDATES_AVAILABLE = False
try:
    from c_group_candidates import (
        generate_c_group_candidate_list,
        classify_discharge_urgency,
        summarize_candidates_for_display,
    )
    _C_GROUP_CANDIDATES_AVAILABLE = True
except Exception as _cgc_err:
    import traceback as _cgc_tb
    _C_GROUP_CANDIDATES_ERROR = f"{_cgc_err}\n{_cgc_tb.format_exc()}"

# views（描画ロジック分離）
_VIEWS_AVAILABLE = False
_VIEWS_ERROR = ""
try:
    from views.dashboard_view import (
        render_action_card,
        render_kpi_priority_strip,
        render_morning_capacity_card,
        render_tradeoff_card,
    )
    from views.c_group_view import render_c_group_candidates_lite
    from views.guardrail_view import render_guardrail_summary, render_demand_wave_summary
    from views.holiday_strategy_view import (
        render_weekly_demand_dashboard,
        render_discharge_candidates_tab,
        render_booking_availability_calendar,
        calculate_next_holiday_countdown,
        compute_dow_occupancy,
    )
    _VIEWS_AVAILABLE = True
except Exception as _v_err:
    import traceback as _v_tb
    _VIEWS_ERROR = f"{_v_err}\n{_v_tb.format_exc()}"

# 多職種退院調整・連休対策カンファ ビュー（views と独立の try/except）
# 依存: target_config / holiday_calendar / data/facts.yaml
# 失敗しても他セクションに影響させない。
_CONFERENCE_VIEW_AVAILABLE = False
_CONFERENCE_VIEW_ERROR = ""
try:
    from views.conference_material_view import render_conference_material_view
    _CONFERENCE_VIEW_AVAILABLE = True
except Exception as _cv_err:
    import traceback as _cv_tb
    _CONFERENCE_VIEW_ERROR = f"{_cv_err}\n{_cv_tb.format_exc()}"

# 退院カレンダービュー（Ph.2, 2026-04-23 副院長指示）
# 依存: discharge_plan_store / patient_status_store / discharge_slot_config
# 失敗しても他セクションに影響させない。
_DISCHARGE_CAL_VIEW_AVAILABLE = False
_DISCHARGE_CAL_VIEW_ERROR = ""
try:
    from views.discharge_calendar_view import render_discharge_calendar_tab
    _DISCHARGE_CAL_VIEW_AVAILABLE = True
except Exception as _dc_err:
    import traceback as _dc_tb
    _DISCHARGE_CAL_VIEW_ERROR = f"{_dc_err}\n{_dc_tb.format_exc()}"

# 過去実績分析ビュー（views と独立の try/except）
# 依存: data/actual_admissions_2025fy.csv（無くても view 内でフォールバック）
# 失敗しても他セクションに影響させない。
_PAST_PERF_VIEW_AVAILABLE = False
_PAST_PERF_VIEW_ERROR = ""
try:
    from views.past_performance_view import render_past_performance_view
    _PAST_PERF_VIEW_AVAILABLE = True
except Exception as _pp_err:
    import traceback as _pp_tb
    _PAST_PERF_VIEW_ERROR = f"{_pp_err}\n{_pp_tb.format_exc()}"

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
# デザイントークン（design_tokens.py と整合 — matplotlib から参照するための束ね）
# 日次推移タブ / フェーズ構成タブ / 運営分析タブ / トレンド分析タブで共有する
# ---------------------------------------------------------------------------
_DT_TEXT_PRIMARY = "#1F2937"
_DT_TEXT_SECONDARY = "#6B7280"
_DT_TEXT_MUTED = "#9CA3AF"
_DT_BORDER = "#E5E7EB"
_DT_ACCENT = "#374151"      # 主役ダークグレー（全体の線・ALOS など）
_DT_WARD_5F = "#2563EB"     # 5F: ブルー
_DT_WARD_6F = "#8B5CF6"     # 6F: パープル
_DT_WARNING = "#F59E0B"
_DT_DANGER = "#DC2626"
_DT_SUCCESS = "#10B981"
_DT_INFO = "#2563EB"
# 実線 / 破線 / 点線の標準線幅
_DT_LW_PRIMARY = 2.5
_DT_LW_TARGET = 1.8
_DT_LW_AUX = 1.2


def _bc_apply_chart_style(ax_obj, show_xgrid: bool = False) -> None:
    """ニュートラル・ミニマルな共通チャートスタイル（横グリッドのみ / 上右 spine 非表示）."""
    ax_obj.set_facecolor("white")
    ax_obj.grid(False)
    ax_obj.yaxis.grid(True, color=_DT_BORDER, linewidth=0.8, alpha=0.9)
    if show_xgrid:
        ax_obj.xaxis.grid(True, color=_DT_BORDER, linewidth=0.6, alpha=0.6)
    ax_obj.set_axisbelow(True)
    for _spine_name, _spine in ax_obj.spines.items():
        if _spine_name in ("top", "right"):
            _spine.set_visible(False)
        else:
            _spine.set_color(_DT_BORDER)
            _spine.set_linewidth(0.8)
    ax_obj.tick_params(colors=_DT_TEXT_SECONDARY, labelsize=9)
    ax_obj.xaxis.label.set_color(_DT_TEXT_SECONDARY)
    ax_obj.yaxis.label.set_color(_DT_TEXT_SECONDARY)
    ax_obj.xaxis.label.set_fontsize(10)
    ax_obj.yaxis.label.set_fontsize(10)


def _bc_style_legend(leg_obj) -> None:
    """共通凡例スタイル（枠なし・控えめ・セカンダリーカラー）."""
    if leg_obj is None:
        return
    leg_obj.get_frame().set_alpha(0.0)
    for _t in leg_obj.get_texts():
        _t.set_color(_DT_TEXT_SECONDARY)
        _t.set_fontsize(9)

# ---------------------------------------------------------------------------
# ページ設定
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="ベッドコントロールシミュレーター",
    page_icon="🏥",
    layout="wide",
)

# --- 共通デザインシステム CSS を注入（単一ソース: theme_css.py + design_tokens.py） ---
# 既存の個別 CSS は後続で注入されるため、そちらで上書き可能（段階的移行）
try:
    from theme_css import render_theme_css as _render_theme_css
    st.markdown(_render_theme_css(), unsafe_allow_html=True)
except Exception as _theme_err:
    # デザインシステム不在でも本体機能は止めない
    import traceback as _theme_tb
    st.sidebar.warning(
        f"⚠️ デザインシステム CSS の読み込みに失敗しました（機能は動作します）\n\n"
        f"{_theme_err}\n{_theme_tb.format_exc()}"
    )

# --- 共通 UI コンポーネント（section_title / kpi_card / alert） ---
# 取り込みに失敗しても本体機能は維持するため、フォールバックとして no-op 相当を用意
try:
    from ui_components import (
        alert as _bc_alert,
        kpi_card as _bc_kpi_card,
        section_title as _bc_section_title,
    )
    _UI_COMPONENTS_AVAILABLE = True
except Exception as _uc_err:
    _UI_COMPONENTS_AVAILABLE = False

    def _bc_section_title(title: str, icon: str = "") -> None:  # type: ignore[no-redef]
        st.markdown(f"#### {icon} {title}" if icon else f"#### {title}")

    def _bc_kpi_card(  # type: ignore[no-redef]
        label: str,
        value: str,
        unit: str = "",
        delta=None,
        severity: str = "neutral",
        size: str = "md",
        testid=None,
        testid_attrs=None,
        testid_text=None,
    ) -> None:
        st.metric(label, f"{value}{unit}", delta=delta)
        if testid:
            _attrs = ""
            if testid_attrs:
                for _k, _v in testid_attrs.items():
                    _attrs += f' data-{_k}="{_v}"'
            _inner = testid_text if testid_text is not None else value
            st.markdown(
                f'<div data-testid="{testid}"{_attrs} style="display:none">{_inner}</div>',
                unsafe_allow_html=True,
            )

    def _bc_alert(message: str, severity: str = "info") -> None:  # type: ignore[no-redef]
        if severity == "danger":
            st.error(message)
        elif severity == "warning":
            st.warning(message)
        elif severity == "success":
            st.success(message)
        else:
            st.info(message)

# --- パスワード認証（データ入力・エクスポート時のみ） ---
if "data_authenticated" not in st.session_state:
    st.session_state.data_authenticated = False


def _require_data_auth(section_label: str = "この機能") -> bool:
    """データ入力・エクスポート時のパスワード認証ガード。認証済みならTrueを返す。"""
    if st.session_state.data_authenticated:
        return True
    st.info(f"🔐 {section_label}を利用するにはパスワードが必要です（データ改ざん防止）")
    _pw = st.text_input("パスワード", type="password", key=f"pw_{section_label}")
    if st.button("認証", key=f"auth_{section_label}"):
        if _pw == "1234":
            st.session_state.data_authenticated = True
            st.rerun()
        else:
            st.error("パスワードが違います")
    return False

if not _CORE_AVAILABLE:
    st.error(f"⚠️ コアモジュールのインポートに失敗しました\n\n{_CORE_ERROR}")
    st.info("Python のバージョン: " + sys.version)
    st.info("sys.path: " + str(sys.path))
    st.stop()

if not _DATA_MANAGER_AVAILABLE:
    _dm_error_msg = _DATA_MANAGER_ERROR if "_DATA_MANAGER_ERROR" in dir() else "bed_data_manager モジュールが見つかりません"
    st.sidebar.warning(f"⚠️ 日次データ管理モジュールのインポートに失敗しました\n\n{_dm_error_msg}")

if not _DB_AVAILABLE and "_DB_ERROR" in dir():
    st.sidebar.warning(f"⚠️ SQLite永続化モジュールのインポートに失敗しました\n\n{_DB_ERROR}")

if not _DOCTOR_MASTER_AVAILABLE and "_DOCTOR_MASTER_ERROR" in dir():
    st.sidebar.warning(f"⚠️ 医師マスター管理モジュールのインポートに失敗しました\n\n{_DOCTOR_MASTER_ERROR}")

if not _HOPE_AVAILABLE and "_HOPE_ERROR" in dir():
    st.sidebar.warning(f"⚠️ HOPE送信サマリーモジュールのインポートに失敗しました\n\n{_HOPE_ERROR}")

if not _DETAIL_DATA_AVAILABLE and "_DETAIL_DATA_ERROR" in dir():
    st.sidebar.warning(f"⚠️ 入退院詳細データモジュールのインポートに失敗しました\n\n{_DETAIL_DATA_ERROR}")

if not _BED_MGMT_METRICS_AVAILABLE and "_BED_MGMT_METRICS_ERROR" in dir():
    st.sidebar.warning(f"⚠️ 空床マネジメント指標モジュールのインポートに失敗しました\n\n{_BED_MGMT_METRICS_ERROR}")

if not _GUARDRAIL_AVAILABLE and "_GUARDRAIL_ERROR" in dir():
    st.sidebar.warning(f"⚠️ 施設基準チェックモジュールのインポートに失敗しました\n\n{_GUARDRAIL_ERROR}")

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
_UNIT_PRICE_PER_DAY = 34960  # 1日あたり入院単価
_TOTAL_BEDS_METRIC = 94
_ANNUAL_VALUE_PER_1PCT = _TOTAL_BEDS_METRIC * 0.01 * 365 * _UNIT_PRICE_PER_DAY  # ≈1,199万円
_OPERATING_PROFIT = 35500000  # 年間黒字額3,550万円

# Get monthly average occupancy from data if available
_current_occ = None
if isinstance(st.session_state.get("daily_data"), pd.DataFrame) and len(st.session_state.daily_data) > 0:
    _dd_for_occ = st.session_state.daily_data
    # 厚労省定義: 病床稼働率 = (在院患者数 + 退院患者数) / 病床数
    _dis_fallback = _dd_for_occ["discharges"] if "discharges" in _dd_for_occ.columns else 0
    if "ward" in _dd_for_occ.columns:
        # 病棟別データの場合、日付ごとに(total_patients + discharges)を合算してから平均
        _dd_for_occ_tmp = _dd_for_occ.copy()
        _dd_for_occ_tmp["_occ_numerator"] = _dd_for_occ_tmp["total_patients"] + (_dd_for_occ_tmp["discharges"] if "discharges" in _dd_for_occ_tmp.columns else 0)
        _mean_total_patients = _dd_for_occ_tmp.groupby("date")["_occ_numerator"].sum().mean()
    else:
        _mean_total_patients = (_dd_for_occ["total_patients"] + _dis_fallback).mean()
    _current_occ = _mean_total_patients / _TOTAL_BEDS_METRIC * 100

# ---------------------------------------------------------------------------
# サイドバー: メニュー選択（データソースの上に配置）
# ---------------------------------------------------------------------------
_section_names = ["📊 今日の運営", "🔮 What-if・戦略"]
if _GUARDRAIL_AVAILABLE and _DATA_MANAGER_AVAILABLE:
    _section_names.append("🛡️ 制度管理")
# 🏥 退院調整: 情報階層リデザイン Phase 1（2026-04-18）
# 旧「🗓 連休対策」「🏥 多職種退院調整カンファ」と意思決定支援の「退院タイミング」を
# 単一セクションに統合。カンファ・退院タイミング・需要予測・退院候補・予約枠の 5 タブ構成。
# 両方の依存 view が揃っていないときのみセクションを出す（片方だけでも出す運用はしない）
if _CONFERENCE_VIEW_AVAILABLE and _DEMAND_FORECAST_AVAILABLE and _VIEWS_AVAILABLE:
    _section_names.append("🏥 退院調整")
# 📈 過去1年分析: 情報階層リデザイン Phase 5（2026-04-25）
# 旧「🛡️ 制度管理 > 📊 過去1年分析」タブを独立セクションに昇格。
# 制度管理 = 現場目線（今この瞬間の制度コンプライアンス監視）、
# 過去1年分析 = 経営者目線（過去 1 年の傾向理解、理事会/師長会議の議論材料）。
if _PAST_ADMISSIONS_AVAILABLE:
    _section_names.append("📈 過去1年分析")
# ⚙️ データ・設定: 情報階層リデザイン Phase 4（2026-04-18・最終）
# 旧「📋 データ管理」に旧「📨 HOPE連携」セクションとサイドバー短手3 パラメータを統合。
# データ・設定モジュールの依存があれば（or HOPE 単独でも）セクションを出す。
if _DATA_MANAGER_AVAILABLE or _DOCTOR_MASTER_AVAILABLE or _HOPE_AVAILABLE:
    _section_names.append("⚙️ データ・設定")

_selected_section = st.sidebar.radio("メニュー", _section_names, label_visibility="collapsed")
st.sidebar.markdown("---")

# ---------------------------------------------------------------------------
# 経過措置終了カウントダウン（地域包括医療病棟・救急搬送15%）
# 令和6改定の経過措置は 2026-05-31 まで。6/1 以降は本則完全適用。
# 本シミュレーターの判定ロジック自体は既に本則ベースだが、運用現場の
# 心構えとして残り日数を可視化する。
# ---------------------------------------------------------------------------
if _EMERGENCY_RATIO_AVAILABLE:
    _trans_remaining = days_until_transitional_end()
    _trans_label = TRANSITIONAL_END_DATE.strftime("%Y-%m-%d")
    if _trans_remaining > 30:
        st.sidebar.info(
            f"🗓️ 経過措置終了まで **あと {_trans_remaining} 日**\n\n"
            f"地域包括医療病棟の救急搬送15%等の本則完全適用は {_trans_label} 翌日から。"
        )
    elif _trans_remaining > 7:
        st.sidebar.warning(
            f"⚠️ 経過措置終了まで **あと {_trans_remaining} 日**（{_trans_label}）\n\n"
            f"6/1 以降は救急搬送15%等の本則が完全適用されます。"
        )
    elif _trans_remaining >= 0:
        st.sidebar.error(
            f"🚨 経過措置終了まで **あと {_trans_remaining} 日**（{_trans_label}）\n\n"
            f"明日以降の運用判断は本則ベースで行ってください。"
        )
    else:
        st.sidebar.error(
            f"🚨 経過措置は終了しました（{_trans_label}）\n\n"
            f"地域包括医療病棟の本則が完全適用されています。"
        )
    st.sidebar.markdown("---")

_sidebar_annual_value_placeholder = st.sidebar.empty()  # プリセット確定後に更新
_sidebar_occ_placeholder = st.sidebar.empty()  # target_lower 確定後に表示
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

# _view_beds / _active_raw_df のデフォルト値（後で病棟選択・データ読込に応じて上書きされる）
_view_beds = total_beds
_active_raw_df = pd.DataFrame()
_active_raw_df_full = pd.DataFrame()

target_lower = st.sidebar.slider("目標稼働率下限", 0.80, 1.00, 0.90, step=0.01, format="%.2f")
target_upper = st.sidebar.slider("目標稼働率上限", 0.80, 1.00, 0.95, step=0.01, format="%.2f")
helper_cap = st.sidebar.slider("助ける側の上限", 0.90, 1.00, 0.96, step=0.01, format="%.2f",
                                help="助け合いで目標達成する際、助ける側の病棟に求める稼働率の上限。無理のない範囲を設定してください。")

# 目標上限 < 下限のバリデーション
if target_upper < target_lower:
    st.sidebar.warning("目標稼働率上限が下限より低く設定されています。値を確認してください。")

# サイドバー基盤指標のcaptionを目標値反映で表示
_target_occ_pct = target_lower * 100
if _current_occ is not None:
    _gap_to_target = max(0, _target_occ_pct - _current_occ)
    _sidebar_occ_placeholder.caption(
        f"月平均稼働率: {_current_occ:.1f}% | 目標{_target_occ_pct:.0f}%まであと{_gap_to_target:.1f}%"
    )

# シミュレーションモード専用のパラメータ
if not _is_actual_data_mode:
    days_in_month = st.sidebar.number_input("月の日数（経過日数）", min_value=7, max_value=31, value=20,
                                              help="シミュレーション対象の日数（月の途中の場合は経過日数）")
    _sidebar_calendar_days = st.sidebar.number_input("カレンダー月日数", min_value=28, max_value=31, value=30,
                                                      help="月の実際の日数（例: 4月=30日）。経過日数より大きい場合、残り日数の分析が有効になります")
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

# ---------------------------------------------------------------------------
# 診療報酬プリセット定義
# ---------------------------------------------------------------------------
# 各フェーズの日次診療報酬は「基本入院料 + 初期加算 + リハビリ出来高推定」を
# 合算した包括値。初日加算・14日以内加算・リハビリ出来高の個別欄は
# 追加で上乗せしたい場合のみ使用。
_FEE_PRESETS = {
    "2024年度（令和6年度）": {
        "desc": "基本 3,050点/日 ＋ 初期加算 150点/日（14日以内）",
        "base_points": 3050,
        "initial_bonus_points": 150,
        "a_rev": 36000, "a_cost": 12000,   # 30,500 + 1,500(初期) + 4,000(リハ推定)
        "b_rev": 36000, "b_cost": 6000,    # 同上
        "c_rev": 33400, "c_cost": 4500,    # 30,500 + 2,900(リハ推定)
        "day1_bonus": 0, "within_14_bonus": 0, "rehab_fee": 0,
        "note": "初期加算1,500円/日・リハビリ出来高は各群の報酬に包含済み",
        "max_avg_los": 21,  # 地域包括医療病棟の算定基準: 平均在院日数上限
        "max_avg_los_relaxed": 21,  # 85歳以上20%以上の場合（+0日、同じ）
        # 短手3 包括収入（1件あたり、円）— 当院ミックス (大腸ポリペク80% + 鼠径ヘル等20%)
        # K721-1 12,580点 × 0.80 + K633-5 24,147点 × 0.20 ≈ 14,893点 ≈ ¥148,930
        "short3_revenue_per_case": 148930,
        "short3_cost_per_case": 25000,  # 材料・薬剤費の推定
    },
    "2026年度（令和8年度）": {
        "desc": "入院料1: イ3,367 / ロ3,267 / ハ3,117点（加重平均≈3,250点）＋ 初期加算 150点",
        "base_points": 3250,  # 加重平均
        "initial_bonus_points": 150,
        "a_rev": 38500, "a_cost": 12000,   # 32,500 + 1,500(初期) + 4,500(リハ推定)
        "b_rev": 38500, "b_cost": 6000,    # 同上
        "c_rev": 35500, "c_cost": 4500,    # 32,500 + 3,000(リハ推定)
        "day1_bonus": 0, "within_14_bonus": 0, "rehab_fee": 0,
        "note": "入院料1（急性期非併設）の加重平均。初期加算・リハビリ出来高は各群に包含済み",
        "max_avg_los": 20,  # 2026年改定で21→20日に短縮
        "max_avg_los_relaxed": 21,  # 85歳以上20%以上の場合（+1日緩和）
        # 短手3 は 2026年改定で外来シフト促進のため引き下げ予想（中医協議論中）
        # 保守的に -10% を仮定: 148,930 × 0.90 ≈ 134,037 円
        # 出典: https://www.prrism.com/newscolumns/10560/ (2026年改定方向性)
        "short3_revenue_per_case": 134040,
        "short3_cost_per_case": 25000,  # コストは変わらない想定
    },
}

# --- 診療報酬プリセット選択 ---
_fee_preset_name = st.sidebar.selectbox(
    "診療報酬改定プリセット",
    list(_FEE_PRESETS.keys()),
    index=0,
    help="改定年度を選ぶと診療報酬パラメータが自動設定されます。個別調整も可能です。",
)
_fee_preset = _FEE_PRESETS[_fee_preset_name]
st.sidebar.caption(f"📋 {_fee_preset['desc']}")

# 85歳以上20%以上の緩和措置
_elderly_relaxation = st.sidebar.checkbox(
    "85歳以上が20%以上（在院日数+1日緩和）",
    value=True,
    help="85歳以上の入院患者割合が20%以上の場合、平均在院日数の算定基準が+1日緩和されます",
)
_max_avg_los = _fee_preset.get("max_avg_los_relaxed", 21) if _elderly_relaxation else _fee_preset.get("max_avg_los", 21)
_base_max_los = _fee_preset.get("max_avg_los", 21)
_los_label = f"平均在院日数上限: {_max_avg_los}日以内" + (f"（通常{_base_max_los}日+1日緩和）" if _elderly_relaxation and _max_avg_los > _base_max_los else "")
st.sidebar.caption(f"📏 {_los_label}")

# プリセット切替時にセッションステートを更新
if "prev_fee_preset" not in st.session_state:
    st.session_state.prev_fee_preset = _fee_preset_name
if st.session_state.prev_fee_preset != _fee_preset_name:
    # プリセットが変更された → 各パラメータのセッションステートを上書き
    for _k, _sk in [
        ("a_rev", "a_rev"), ("a_cost", "a_cost"),
        ("b_rev", "b_rev"), ("b_cost", "b_cost"),
        ("c_rev", "c_rev"), ("c_cost", "c_cost"),
        ("day1_bonus", "day1_bonus_input"), ("within_14_bonus", "within_14_bonus_input"),
        ("rehab_fee", "rehab_fee_input"),
    ]:
        if _sk in st.session_state:
            st.session_state[_sk] = _fee_preset[_k]
    st.session_state.prev_fee_preset = _fee_preset_name
    st.rerun()

# --- 患者フェーズ別パラメータ（運営貢献額ベース：変動費のみ計上） ---
with st.sidebar.expander("患者フェーズ別パラメータ"):
    st.caption(f"ℹ️ {_fee_preset['note']}")
    st.markdown("**A群（急性期: 〜5日目）**")
    phase_a_rev = st.number_input("A群 日次診療報酬（円）", value=_fee_preset["a_rev"], step=1000, key="a_rev")
    phase_a_cost = st.number_input("A群 日次変動費（円）", value=_fee_preset["a_cost"], step=1000, key="a_cost")
    st.markdown("**B群（回復期: 6〜14日目）**")
    phase_b_rev = st.number_input("B群 日次診療報酬（円）", value=_fee_preset["b_rev"], step=1000, key="b_rev")
    phase_b_cost = st.number_input("B群 日次変動費（円）", value=_fee_preset["b_cost"], step=1000, key="b_cost")
    st.markdown("**C群（退院準備期: 15日目〜）**")
    phase_c_rev = st.number_input("C群 日次診療報酬（円）", value=_fee_preset["c_rev"], step=1000, key="c_rev")
    phase_c_cost = st.number_input("C群 日次変動費（円）", value=_fee_preset["c_cost"], step=1000, key="c_cost")

# --- 短手3（短期滞在手術等基本料3）パラメータ ---
# Phase 3: 運営貢献額を通常分と短手3分で分離表示
# 4種類 + その他 のタイプ別に点数管理。入力時に種類を選ぶ。

# 短手3 種類の定義: ラベル → (収入円, コスト円, 説明)
SHORT3_TYPE_POLYP_S = "大腸ポリペク（2cm未満）"
SHORT3_TYPE_POLYP_L = "大腸ポリペク（2cm以上）"
SHORT3_TYPE_INGUINAL = "鼠径ヘルニア手術"
SHORT3_TYPE_PSG = "終夜睡眠ポリグラフィー (PSG)"
SHORT3_TYPE_OTHER = "その他"
SHORT3_TYPE_NONE = "該当なし"

# 2026年改定予測: 全体的に -10% を仮定（中医協で議論中）
_is_2026 = "2026" in _fee_preset_name
_s3_mult = 0.90 if _is_2026 else 1.00

# デフォルト単価（令和6年度ベース、点数 × 10 円）
# 注: 短期滞在手術等基本料3 では麻酔（全身・脊椎・局所）の有無による点数分けはなく、
#     手術料・検査料・麻酔料・薬剤料・材料料がすべて包括されている統一点数。
# 出典: https://shirobon.net/medicalfee/latest/ika/r06_ika/r06i_ch1/r06i1_pa2/r06i12_sec4/r06i124_A400.html
_SHORT3_DEFAULT_REVENUE = {
    SHORT3_TYPE_POLYP_S:  int(125800 * _s3_mult),   # K721-1: 12,580点
    SHORT3_TYPE_POLYP_L:  int(161530 * _s3_mult),   # K721-2: 16,153点
    SHORT3_TYPE_INGUINAL: int(241470 * _s3_mult),   # K633-5: 24,147点（麻酔包括）
    SHORT3_TYPE_PSG:      int(82210 * _s3_mult),    # D237-3 終夜睡眠ポリグラフィー3（院内・訪問実施）: 8,221点
    SHORT3_TYPE_OTHER:    0,                        # その他: 稀なので収入無視
}
_SHORT3_DEFAULT_COST = {
    SHORT3_TYPE_POLYP_S:  15000,   # 内視鏡・処置具
    SHORT3_TYPE_POLYP_L:  20000,
    SHORT3_TYPE_INGUINAL: 60000,   # 手術材料・メッシュ等
    SHORT3_TYPE_PSG:      10000,   # 検査消耗品
    SHORT3_TYPE_OTHER:    0,
}

# Phase 4（2026-04-18）: 短手3 パラメータの入力 UI は「⚙️ データ・設定 > 🏃 短手3設定」
# タブに移設。ここでは session_state からマップを再構築するだけにして、
# 下流（運営貢献額サマリー・月次分離表示など）が従来どおり参照できる形を維持する。
# 初回レンダリング時は widget が未作成で session_state にキーがないので、
# デフォルト値にフォールバック。2 回目以降のレンダリングでは前回値を取得する。
_short3_revenue_map = {}
_short3_cost_map = {}
for _t in [SHORT3_TYPE_POLYP_S, SHORT3_TYPE_POLYP_L, SHORT3_TYPE_INGUINAL, SHORT3_TYPE_PSG, SHORT3_TYPE_OTHER]:
    _short3_revenue_map[_t] = st.session_state.get(
        f"short3_rev_{_t}", _SHORT3_DEFAULT_REVENUE[_t]
    )
    _short3_cost_map[_t] = st.session_state.get(
        f"short3_cost_{_t}", _SHORT3_DEFAULT_COST[_t]
    )

# --- 追加パラメータ ---
with st.sidebar.expander("追加パラメータ"):
    st.caption("ℹ️ 初日加算・14日以内加算・リハビリ出来高はプリセットでA/B/C群報酬に包含済み。\n追加で上乗せしたい場合のみ入力してください。")
    day1_bonus = st.number_input("初日加算（円）", value=_fee_preset["day1_bonus"], step=1000, key="day1_bonus_input")
    within_14_bonus = st.number_input("14日以内加算（円/日）", value=_fee_preset["within_14_bonus"], step=500, key="within_14_bonus_input")
    rehab_fee = st.number_input("リハビリ出来高（円/日）", value=_fee_preset["rehab_fee"], step=500, key="rehab_fee_input")
    opportunity_cost = st.number_input("空床の影響額（円/空床/日）", value=25000, step=1000)
    discharge_threshold = st.slider("退院促進閾値", 0.80, 1.00, 0.95, step=0.01, format="%.2f")
    suppression_threshold = st.slider("新規入院抑制閾値", 0.80, 1.00, 0.97, step=0.01, format="%.2f")
    random_seed = st.number_input("乱数シード", value=42, step=1)

# --- プリセット連動の計算済み値（全タブ共通）---
# 空床1床/日あたりの逸失診療報酬（プリセットのフェーズ加重平均）
_daily_rev_per_bed = 0.15 * phase_a_rev + 0.45 * phase_b_rev + 0.40 * phase_c_rev
# 空床1床/日あたりの逸失運営貢献額（報酬 - 変動費）
_daily_profit_per_bed = 0.15 * (phase_a_rev - phase_a_cost) + 0.45 * (phase_b_rev - phase_b_cost) + 0.40 * (phase_c_rev - phase_c_cost)
# 稼働率1%の年間価値（プリセット連動で再計算）
_ANNUAL_VALUE_PER_1PCT = _TOTAL_BEDS_METRIC * 0.01 * 365 * _daily_rev_per_bed
# サイドバーの稼働率1%の価値をプリセット連動で更新
_sidebar_annual_value_placeholder.metric(
    label="稼働率1%（≈1名の入院）の価値",
    value=f"年間 {_ANNUAL_VALUE_PER_1PCT/10000:.0f}万円",
    delta="常勤医師1名分の手取り年収に相当",
)
st.sidebar.markdown(
    f'<div data-testid="revenue" data-unit="万円/年" style="display:none">{_ANNUAL_VALUE_PER_1PCT/10000:.0f}</div>',
    unsafe_allow_html=True,
)

# --- 実行ボタン（シミュレーションモードのみ） ---
# 戦略選択 UI は 2026-04-18 に削除、現状はバランス戦略固定。
# 戦略別パラメータ辞書・ユニットテストは保持（将来の復活に備えて温存）。
if not _is_actual_data_mode:
    strategy = "バランス戦略"  # ハードコード（UI 入力なし）
    run_button = st.sidebar.button("シミュレーション実行", type="primary", use_container_width=True)
else:
    strategy = "バランス戦略"
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
if "monthly_summary" not in st.session_state:
    st.session_state.monthly_summary = {}

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
        _csv_fallback_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "sample_actual_data_ward_202604.csv")
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
        _detail_csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "admission_details.csv")
        st.session_state.admission_details = load_details(_detail_csv_path)
    else:
        st.session_state.admission_details = pd.DataFrame()

# 過去入院データ（事務提供の過去1年 CSV）— 救急15% rolling 計算の bootstrap 用
# 日次入力が 3 ヶ月分貯まれば自動的に日次データが優先されるため、
# これは「古い月の監視」専用。
if "past_admissions_df" not in st.session_state:
    if _PAST_ADMISSIONS_AVAILABLE:
        try:
            st.session_state.past_admissions_df = load_past_admissions()
        except Exception:
            st.session_state.past_admissions_df = pd.DataFrame()
    else:
        st.session_state.past_admissions_df = pd.DataFrame()

# 看護必要度データ（事務提供 XLSM 由来 CSV、2026-04-25 追加）
# 個人情報なし（「データ（全体）」シートの集計値のみ取り込み）
if "nursing_necessity_df" not in st.session_state:
    if _NURSING_NECESSITY_AVAILABLE:
        try:
            st.session_state.nursing_necessity_df = load_nursing_necessity()
        except Exception:
            st.session_state.nursing_necessity_df = pd.DataFrame()
    else:
        st.session_state.nursing_necessity_df = pd.DataFrame()

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
    _demo_csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "sample_actual_data_ward_202604.csv")
    if os.path.exists(_demo_csv_path):
        try:
            _auto_demo = pd.read_csv(_demo_csv_path)
            _auto_demo["date"] = pd.to_datetime(_auto_demo["date"])
            # 必要カラムの補完
            if "num_beds" not in _auto_demo.columns:
                _auto_demo["num_beds"] = _auto_demo["ward"].map(lambda w: get_ward_beds(w))
            if "occupancy_rate" not in _auto_demo.columns:
                # 厚労省定義: 病床稼働率 = (在院患者数 + 退院患者数) / 病床数
                _auto_dis = _auto_demo["discharges"] if "discharges" in _auto_demo.columns else 0
                _auto_demo["occupancy_rate"] = ((_auto_demo["total_patients"] + _auto_dis) / _auto_demo["num_beds"] * 100).round(1)
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
if not _is_actual_data_mode and _DATA_MANAGER_AVAILABLE:
    _preload_csv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "sample_actual_data_ward_202604.csv")
    if os.path.exists(_preload_csv):
        try:
            _pre_df_full = pd.read_csv(_preload_csv)
            _pre_df_full["date"] = pd.to_datetime(_pre_df_full["date"])
            # 現在月のみに絞る（過去90日rolling LOS用データを除外）
            _pre_last = _pre_df_full["date"].iloc[-1]
            _pre_mask = (_pre_df_full["date"].dt.year == _pre_last.year) & (_pre_df_full["date"].dt.month == _pre_last.month)
            _pre_df = _pre_df_full[_pre_mask].reset_index(drop=True)

            # 実データから全体データの作成（実データモードと同じロジック）
            if "ward" in _pre_df.columns and _pre_df["ward"].isin(["5F", "6F"]).any():
                _pre_data_all = aggregate_wards(_pre_df)
                _pre_data_all_full = aggregate_wards(_pre_df_full)
            else:
                _pre_data_all = _pre_df
                _pre_data_all_full = _pre_df_full

            # デフォルトパラメータで変換用パラメータ辞書を構築
            _pre_params_dict = {
                "target_occupancy_lower": target_lower,
                "target_occupancy_upper": target_upper,
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
            # rolling LOS用の全データも変換
            _pre_raw_df_full = convert_actual_to_display(_pre_data_all_full, _pre_params)

            # 全体サマリーの生成（実データモードと同じロジック）
            _pre_summary = {
                "月次診療報酬": int(_pre_raw_df["daily_revenue"].sum()),
                "月次コスト": int(_pre_raw_df["daily_cost"].sum()),
                "月次運営貢献額": int(_pre_raw_df["daily_profit"].sum()),
                "平均稼働率": round(float(_pre_raw_df["occupancy_rate"].mean()) * 100, 1),
                "月間入院数": int(_pre_raw_df["new_admissions"].sum()),
                "月間退院数": int(_pre_raw_df["discharges"].sum()),
                "目標レンジ内日数": int(
                    ((_pre_raw_df["occupancy_rate"] >= target_lower)
                     & (_pre_raw_df["occupancy_rate"] <= target_upper)).sum()
                ),
                "目標レンジ内率": round(
                    float(
                        ((_pre_raw_df["occupancy_rate"] >= target_lower)
                         & (_pre_raw_df["occupancy_rate"] <= target_upper)).mean()
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

            _pre_ward_raw_dfs_full = {}
            for _w in ["5F", "6F"]:
                _w_data = _pre_df[_pre_df["ward"] == _w].copy()
                _w_data_full = _pre_df_full[_pre_df_full["ward"] == _w].copy()
                if len(_w_data) > 0:
                    _w_params = _pre_params.copy()
                    _w_params["num_beds"] = get_ward_beds(_w)
                    _w_raw = convert_actual_to_display(_w_data, _w_params)
                    _w_disp = _rename_df(_w_raw)
                    if len(_w_data_full) > 0:
                        _pre_ward_raw_dfs_full[_w] = convert_actual_to_display(_w_data_full, _w_params)
                    _w_summary = {
                        "月次診療報酬": int(_w_raw["daily_revenue"].sum()),
                        "月次コスト": int(_w_raw["daily_cost"].sum()),
                        "月次運営貢献額": int(_w_raw["daily_profit"].sum()),
                        "平均稼働率": round(float(_w_raw["occupancy_rate"].mean()) * 100, 1),
                        "月間入院数": int(_w_raw["new_admissions"].sum()),
                        "月間退院数": int(_w_raw["discharges"].sum()),
                        "目標レンジ内日数": int(
                            ((_w_raw["occupancy_rate"] >= target_lower)
                             & (_w_raw["occupancy_rate"] <= target_upper)).sum()
                        ),
                        "目標レンジ内率": round(
                            float(
                                ((_w_raw["occupancy_rate"] >= target_lower)
                                 & (_w_raw["occupancy_rate"] <= target_upper)).mean()
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
            st.session_state.sim_ward_raw_dfs_full = _pre_ward_raw_dfs_full
            st.session_state.sim_ward_summaries = _pre_ward_summaries
            st.session_state.sim_df = _pre_display_df
            st.session_state.sim_df_raw = _pre_raw_df
            st.session_state.sim_df_raw_full = _pre_raw_df_full
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
            params = _build_cli_params(params_dict)

            # --- 教育用CSVデータからロード（デモCSVと同一データを使用） ---
            _sim_csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "sample_actual_data_ward_202604.csv")
            _sim_csv_loaded = False
            if os.path.exists(_sim_csv_path) and _DATA_MANAGER_AVAILABLE:
                _sim_csv_df_full = pd.read_csv(_sim_csv_path)
                _sim_csv_df_full["date"] = pd.to_datetime(_sim_csv_df_full["date"])
                # 現在月のみに絞る（過去90日rolling LOS用データを除外）
                _sim_last = _sim_csv_df_full["date"].iloc[-1]
                _sim_mask = (_sim_csv_df_full["date"].dt.year == _sim_last.year) & (_sim_csv_df_full["date"].dt.month == _sim_last.month)
                _sim_csv_df = _sim_csv_df_full[_sim_mask].reset_index(drop=True)
                if "ward" in _sim_csv_df.columns and _sim_csv_df["ward"].isin(["5F", "6F"]).any():
                    _sim_data_all = aggregate_wards(_sim_csv_df)
                    _sim_data_all_full = aggregate_wards(_sim_csv_df_full)
                    _sim_raw_df = convert_actual_to_display(_sim_data_all, params)
                    _sim_raw_df_full = convert_actual_to_display(_sim_data_all_full, params)
                    _sim_display_df = _rename_df(_sim_raw_df)
                    _sim_summary = {
                        "月次診療報酬": int(_sim_raw_df["daily_revenue"].sum()),
                        "月次コスト": int(_sim_raw_df["daily_cost"].sum()),
                        "月次運営貢献額": int(_sim_raw_df["daily_profit"].sum()),
                        "平均稼働率": round(float(_sim_raw_df["occupancy_rate"].mean()) * 100, 1),
                        "月間入院数": int(_sim_raw_df["new_admissions"].sum()),
                        "月間退院数": int(_sim_raw_df["discharges"].sum()),
                        "目標レンジ内日数": int(
                            ((_sim_raw_df["occupancy_rate"] >= target_lower)
                             & (_sim_raw_df["occupancy_rate"] <= target_upper)).sum()
                        ),
                        "目標レンジ内率": round(
                            float(
                                ((_sim_raw_df["occupancy_rate"] >= target_lower)
                                 & (_sim_raw_df["occupancy_rate"] <= target_upper)).mean()
                            ) * 100, 1
                        ),
                        "A群平均構成比": round(float(_sim_raw_df["phase_a_ratio"].mean()) * 100, 1) if pd.notna(_sim_raw_df["phase_a_ratio"].mean()) else 0.0,
                        "B群平均構成比": round(float(_sim_raw_df["phase_b_ratio"].mean()) * 100, 1) if pd.notna(_sim_raw_df["phase_b_ratio"].mean()) else 0.0,
                        "C群平均構成比": round(float(_sim_raw_df["phase_c_ratio"].mean()) * 100, 1) if pd.notna(_sim_raw_df["phase_c_ratio"].mean()) else 0.0,
                        "平均在院日数": 0,
                        "フラグ集計": {},
                    }
                    _total_patient_days = float(_sim_raw_df["total_patients"].sum())
                    _total_new_admissions = float(_sim_raw_df["new_admissions"].sum())
                    _total_discharges = float(_sim_raw_df["discharges"].sum())
                    _los_denominator = (_total_new_admissions + _total_discharges) / 2
                    if _los_denominator > 0 and _total_patient_days > 0:
                        _sim_summary["平均在院日数"] = round(_total_patient_days / _los_denominator, 1)
                    _sim_summary = _enrich_summary(_sim_summary, _sim_display_df)

                    # 病棟別データ
                    _sim_ward_dfs = {}
                    _sim_ward_raw_dfs = {}
                    _sim_ward_raw_dfs_full = {}
                    _sim_ward_summaries = {}
                    for _sw in ["5F", "6F"]:
                        _sw_data = _sim_csv_df[_sim_csv_df["ward"] == _sw].copy()
                        _sw_data_full = _sim_csv_df_full[_sim_csv_df_full["ward"] == _sw].copy()
                        if len(_sw_data) > 0:
                            _sw_params = params.copy()
                            _sw_params["num_beds"] = get_ward_beds(_sw)
                            _sw_raw = convert_actual_to_display(_sw_data, _sw_params)
                            _sw_disp = _rename_df(_sw_raw)
                            if len(_sw_data_full) > 0:
                                _sim_ward_raw_dfs_full[_sw] = convert_actual_to_display(_sw_data_full, _sw_params)
                            _sw_summary = {
                                "月次診療報酬": int(_sw_raw["daily_revenue"].sum()),
                                "月次コスト": int(_sw_raw["daily_cost"].sum()),
                                "月次運営貢献額": int(_sw_raw["daily_profit"].sum()),
                                "平均稼働率": round(float(_sw_raw["occupancy_rate"].mean()) * 100, 1),
                                "月間入院数": int(_sw_raw["new_admissions"].sum()),
                                "月間退院数": int(_sw_raw["discharges"].sum()),
                                "目標レンジ内日数": int(
                                    ((_sw_raw["occupancy_rate"] >= target_lower)
                                     & (_sw_raw["occupancy_rate"] <= target_upper)).sum()
                                ),
                                "目標レンジ内率": round(
                                    float(
                                        ((_sw_raw["occupancy_rate"] >= target_lower)
                                         & (_sw_raw["occupancy_rate"] <= target_upper)).mean()
                                    ) * 100, 1
                                ),
                                "A群平均構成比": round(float(_sw_raw["phase_a_ratio"].mean()) * 100, 1) if pd.notna(_sw_raw["phase_a_ratio"].mean()) else 0.0,
                                "B群平均構成比": round(float(_sw_raw["phase_b_ratio"].mean()) * 100, 1) if pd.notna(_sw_raw["phase_b_ratio"].mean()) else 0.0,
                                "C群平均構成比": round(float(_sw_raw["phase_c_ratio"].mean()) * 100, 1) if pd.notna(_sw_raw["phase_c_ratio"].mean()) else 0.0,
                                "平均在院日数": 0,
                                "フラグ集計": {},
                            }
                            _sw_total_patient_days = float(_sw_raw["total_patients"].sum())
                            _sw_total_new_admissions = float(_sw_raw["new_admissions"].sum())
                            _sw_total_discharges = float(_sw_raw["discharges"].sum())
                            _sw_los_denominator = (_sw_total_new_admissions + _sw_total_discharges) / 2
                            if _sw_los_denominator > 0 and _sw_total_patient_days > 0:
                                _sw_summary["平均在院日数"] = round(_sw_total_patient_days / _sw_los_denominator, 1)
                            _sw_summary = _enrich_summary(_sw_summary, _sw_disp)
                            _sim_ward_dfs[_sw] = _sw_disp
                            _sim_ward_raw_dfs[_sw] = _sw_raw
                            _sim_ward_summaries[_sw] = _sw_summary

                    st.session_state.sim_ward_dfs = _sim_ward_dfs
                    st.session_state.sim_ward_raw_dfs = _sim_ward_raw_dfs
                    st.session_state.sim_ward_raw_dfs_full = _sim_ward_raw_dfs_full
                    st.session_state.sim_ward_summaries = _sim_ward_summaries
                    st.session_state.sim_df = _sim_display_df
                    st.session_state.sim_summary = _sim_summary
                    st.session_state.sim_df_raw = _sim_raw_df
                    st.session_state.sim_df_raw_full = _sim_raw_df_full
                    st.session_state.sim_params = params
                    st.session_state.comparison = None
                    _sim_csv_loaded = True

            if not _sim_csv_loaded:
                st.error("教育用CSVデータが見つかりません。data/sample_actual_data_ward_202604.csv を確認してください。")

        except Exception as e:
            st.error(f"シミュレーションエラー: {e}")

# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 実データ用ヘルパー（モジュール先頭で定義: 下流で使う前に利用可能にする）
# ---------------------------------------------------------------------------
def _calc_short3_summary(df_in, revenue_per_case, cost_per_case):
    """
    短手3（短期滞在手術等基本料3）の件数・収入・コストを算出する。

    Phase 3: 運営貢献額の分離表示用。
    new_admissions_short3 列を合計して包括点数ベースで収入を計算する。

    Args:
        df_in: 日次データ DataFrame (new_admissions_short3 列を含む)
        revenue_per_case: 短手3 1件あたりの包括収入（円）
        cost_per_case: 短手3 1件あたりのコスト（円、材料・薬剤費等）

    Returns:
        dict: {
            "cases": int,           # 期間内の短手3 件数
            "revenue": int,         # 短手3 による総収入（円）
            "cost": int,            # 短手3 による総コスト（円）
            "contribution": int,    # 短手3 による運営貢献額（円）
        }
    """
    if not isinstance(df_in, pd.DataFrame) or len(df_in) == 0:
        return {"cases": 0, "revenue": 0, "cost": 0, "contribution": 0}
    if "new_admissions_short3" not in df_in.columns:
        return {"cases": 0, "revenue": 0, "cost": 0, "contribution": 0}
    _cases = int(df_in["new_admissions_short3"].fillna(0).sum())
    _revenue = _cases * int(revenue_per_case)
    _cost = _cases * int(cost_per_case)
    return {
        "cases": _cases,
        "revenue": _revenue,
        "cost": _cost,
        "contribution": _revenue - _cost,
    }


def _filter_current_month(df_in):
    """
    最新日付と同じ年月の行のみに絞り込む。rolling LOS用の過去90日データを除外するために使う。
    日付カラムがなければそのまま返す。
    """
    if not isinstance(df_in, pd.DataFrame) or len(df_in) == 0:
        return df_in
    for _dc in ("date", "日付"):
        if _dc in df_in.columns:
            try:
                _dates = pd.to_datetime(df_in[_dc])
                _last = _dates.iloc[-1]
                _mask = (_dates.dt.year == _last.year) & (_dates.dt.month == _last.month)
                return df_in[_mask].reset_index(drop=True)
            except Exception:
                return df_in
    return df_in



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
        # _full: 過去90日rolling LOS用の全データ
        _actual_raw_df_full = convert_actual_to_display(_source_data_all, _actual_params)
        # 現在月のみにフィルタ（チャート・サマリー用）
        _actual_raw_df = _filter_current_month(_actual_raw_df_full)
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
            _ward_raw_dfs_full = {}  # rolling LOS用の全データ
            _ward_raw_dfs = {}       # 現在月のみ（チャート・サマリー用）
            _ward_display_dfs = {}
            for _w in ["5F", "6F"]:
                _w_data = _source_data[_source_data["ward"] == _w].copy()
                if len(_w_data) > 0:
                    _w_params = _actual_params.copy()
                    _w_params["num_beds"] = get_ward_beds(_w)
                    _w_full = convert_actual_to_display(_w_data, _w_params)
                    _ward_raw_dfs_full[_w] = _w_full
                    _ward_raw_dfs[_w] = _filter_current_month(_w_full)
                    _ward_display_dfs[_w] = _rename_df(_ward_raw_dfs[_w])
        else:
            _ward_data_available = False
            _ward_raw_dfs_full = {}
            _ward_raw_dfs = {}
            _ward_display_dfs = {}

        # 全体主義計算用にセッションステートへ保存（全タブから参照可能に）
        st.session_state.ward_raw_dfs = _ward_raw_dfs if _ward_data_available else {}
        st.session_state.ward_raw_dfs_full = _ward_raw_dfs_full if _ward_data_available else {}
        st.session_state.actual_df_raw_full = _actual_raw_df_full

        # _active_raw_df_full のデフォルト（全体選択時は全体の full データ）
        _active_raw_df_full = _actual_raw_df_full

        # --- Ward selector データバインディング ---
        if _selected_ward_key in ("5F", "6F") and _ward_data_available and _selected_ward_key in _ward_raw_dfs:
            _view_beds = get_ward_beds(_selected_ward_key)
            _active_raw_df = _ward_raw_dfs[_selected_ward_key]
            _active_raw_df_full = _ward_raw_dfs_full.get(_selected_ward_key, _active_raw_df)
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
        _active_raw_df_full = st.session_state.get("sim_ward_raw_dfs_full", {}).get(_selected_ward_key, _active_raw_df)
        _view_beds = get_ward_beds(_selected_ward_key) if _DATA_MANAGER_AVAILABLE else 47
    elif st.session_state.sim_df_raw is not None:
        _active_raw_df = st.session_state.sim_df_raw
        _active_raw_df_full = st.session_state.get("sim_df_raw_full", _active_raw_df)

# _active_raw_df_full のフォールバック初期化
# （実データモードでは既に設定済み、シミュレーションモードでは _active_raw_df と同じ）
if '_active_raw_df_full' not in locals() or _active_raw_df_full is None:
    _active_raw_df_full = _active_raw_df if '_active_raw_df' in locals() else pd.DataFrame()

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

        # 現在月のデータのみにフィルタリング（rolling LOS計算用の過去90日データを除外）
        # raw_dfには過去3ヶ月分のデータが含まれる場合があるため、最新日付と同じ年月のみに絞る
        _current_month_df = raw_df
        _D = total_days_in_month
        for _dc in ["date", "日付"]:
            if _dc in raw_df.columns:
                try:
                    _dates = pd.to_datetime(raw_df[_dc])
                    _last_date = _dates.iloc[-1]
                    _D = calendar.monthrange(_last_date.year, _last_date.month)[1]
                    # 最新日と同じ年月の行のみ抽出
                    _same_month_mask = (_dates.dt.year == _last_date.year) & (_dates.dt.month == _last_date.month)
                    _current_month_df = raw_df[_same_month_mask]
                    break
                except Exception:
                    pass

        _occ_values = _current_month_df[_occ_col].dropna().values.copy()
        if len(_occ_values) == 0:
            return None

        # スケール統一（0-1 → 0-100）
        if _occ_values.mean() < 1.5:
            _occ_values = _occ_values * 100

        _avg_so_far = float(_occ_values.mean())
        _days_elapsed = len(_occ_values)

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
# 全体主義ベッドコントロール — 病棟間補完計算
# ---------------------------------------------------------------------------
def _calc_cross_ward_target(ward_raw_dfs, target_lower, total_days_in_month, ward_beds_fn, helper_cap_pct=96.0):
    """
    全体主義計算: 一方の病棟が単体で月平均目標未達でも、
    他病棟の補完で全体94床として目標達成できるかを計算する。
    helper_cap_pct: ヘルパー病棟に求める稼働率の上限（%）。これ以上は無理強いしない。
    """
    try:
        wards = ["5F", "6F"]
        ward_info = {}

        for w in wards:
            raw_df = ward_raw_dfs.get(w)
            if raw_df is None or not isinstance(raw_df, pd.DataFrame) or len(raw_df) == 0:
                return None
            _occ_col = "occupancy_rate" if "occupancy_rate" in raw_df.columns else "稼働率"

            # 現在月のデータのみに絞る（rolling LOS用の過去90日データを除外）
            _current_month_df = raw_df
            _D = total_days_in_month
            for _dc in ["date", "日付"]:
                if _dc in raw_df.columns:
                    try:
                        _dates = pd.to_datetime(raw_df[_dc])
                        _last_date = _dates.iloc[-1]
                        _D = calendar.monthrange(_last_date.year, _last_date.month)[1]
                        _same_month_mask = (_dates.dt.year == _last_date.year) & (_dates.dt.month == _last_date.month)
                        _current_month_df = raw_df[_same_month_mask]
                        break
                    except Exception:
                        pass

            _occ = _current_month_df[_occ_col].dropna().values.copy()
            if len(_occ) == 0:
                return None
            if _occ.mean() < 1.5:
                _occ = _occ * 100
            beds = ward_beds_fn(w)
            avg = float(_occ.mean())
            days_elapsed = len(_occ)
            last_occ = float(_occ[-1])

            days_remaining = max(0, _D - days_elapsed)
            bd_done = beds * days_elapsed * (avg / 100)

            if days_remaining > 0:
                required_solo = (target_lower * 100 * _D - avg * days_elapsed) / days_remaining
            else:
                required_solo = 0

            ward_info[w] = {
                "beds": beds, "avg": round(avg, 1), "last_occ": round(last_occ, 1),
                "days_elapsed": days_elapsed, "days_remaining": days_remaining,
                "total_days": _D, "bd_done": bd_done,
                "required_solo": round(required_solo, 1),
                "solo_difficulty": "impossible" if required_solo > 100 else "hard" if required_solo > 95 else "moderate" if required_solo > 90 else "easy",
            }

        total_beds = sum(ward_info[w]["beds"] for w in wards)
        days_elapsed = ward_info[wards[0]]["days_elapsed"]
        days_remaining = ward_info[wards[0]]["days_remaining"]
        total_days = ward_info[wards[0]]["total_days"]

        if days_remaining <= 0:
            return None

        total_bd_done = sum(ward_info[w]["bd_done"] for w in wards)
        total_bd_required = total_beds * total_days * (target_lower * 100) / 100
        bd_remaining_needed = total_bd_required - total_bd_done
        overall_required = bd_remaining_needed / (total_beds * days_remaining) * 100

        # --- 均等努力方式（Equal Effort）---
        # 全体目標達成に必要な上昇幅Δを計算し、両病棟で等しく負担する
        # 残り日数で各病棟が current_avg + Δ の稼働率を維持する前提
        # 式: Σ(beds_w × remaining × (avg_w + Δ) / 100) = bd_remaining_needed
        # → Σ(beds_w × avg_w) + Δ × Σ(beds_w) = bd_remaining_needed / remaining × 100
        _sum_beds_avg = sum(ward_info[w]["avg"] * ward_info[w]["beds"] for w in wards)
        _sum_beds = sum(ward_info[w]["beds"] for w in wards)
        _needed_per_day = bd_remaining_needed / days_remaining if days_remaining > 0 else 0
        # _needed_per_day = Σ(beds_w × (avg_w + Δ) / 100)
        # = (_sum_beds_avg + Δ × _sum_beds) / 100
        if _sum_beds > 0:
            _delta = (_needed_per_day * 100 - _sum_beds_avg) / _sum_beds
        else:
            _delta = 0

        # 各病棟の均等努力目標
        equal_effort = {}
        for w in wards:
            _target = ward_info[w]["avg"] + _delta
            _over_cap = _target > helper_cap_pct
            equal_effort[w] = {
                "target": round(_target, 1),
                "delta": round(_delta, 1),
                "feasible": _target <= 100,
                "within_cap": not _over_cap,
            }

        # 多段階シナリオ（均等努力の上昇幅別）
        # 1.0pt 刻み、範囲 -2.0 ~ +10.0pt（必ず達成シナリオを含む）
        _effort_scenarios = []
        for d in range(-2, 11):  # -2, -1, 0, 1, ..., 10 (1.0pt 刻み)
            _row = {"delta": float(d)}
            _all_feasible = True
            _all_within_cap = True
            for w in wards:
                _t = ward_info[w]["avg"] + d
                _row[w] = round(_t, 1)
                if _t > 100:
                    _all_feasible = False
                if _t > helper_cap_pct:
                    _all_within_cap = False
            # この上昇幅での全体稼働率を計算
            _total_bd = sum(ward_info[w]["beds"] * days_remaining * (ward_info[w]["avg"] + d) / 100 for w in wards)
            _overall = (total_bd_done + _total_bd) / (total_beds * total_days) * 100
            _row["overall"] = round(_overall, 1)
            _row["achieves_target"] = _overall >= target_lower * 100
            _row["feasible"] = _all_feasible
            _row["within_cap"] = _all_within_cap
            _effort_scenarios.append(_row)

        helper_ward = None
        helped_ward = None
        for w in wards:
            if ward_info[w]["solo_difficulty"] in ("hard", "impossible"):
                helped_ward = w
                helper_ward = [x for x in wards if x != w][0]
                break

        return {
            "overall_avg": round(total_bd_done / (total_beds * days_elapsed) * 100, 1),
            "overall_required": round(overall_required, 1),
            "overall_achievable": overall_required <= 100,
            "helper_cap_pct": helper_cap_pct,
            "days_elapsed": days_elapsed, "days_remaining": days_remaining,
            "total_days": total_days, "target_pct": target_lower * 100,
            "wards": ward_info,
            "equal_effort": equal_effort,
            "delta": round(_delta, 1),
            "effort_scenarios": _effort_scenarios,
            "helper_ward": helper_ward, "helped_ward": helped_ward,
        }
    except Exception:
        return None


def _get_holistic_ward_dfs():
    """全体主義計算用の病棟別データを取得（実績・シミュレーション両対応）"""
    # 1. 実績データモードで保存されたデータ
    dfs = st.session_state.get("ward_raw_dfs", {})
    if dfs and "5F" in dfs and "6F" in dfs:
        return dfs
    # 2. シミュレーションモードのデータ
    dfs = st.session_state.get("sim_ward_raw_dfs", {})
    if dfs and "5F" in dfs and "6F" in dfs:
        return dfs
    return {}


def _filter_effort_scenarios_for_display(scenarios, fail_count=3, achieve_count=2):
    """
    均等努力方式の上昇幅別シナリオ表示用に、遷移点周辺の5行を抜粋する。

    ルール:
    - 未達成(❌)の末尾 fail_count 行 = 最も達成に近い未達成シナリオ
    - 達成可(✅⚠️🔶)の先頭 achieve_count 行 = 最も小さい努力で達成するシナリオ
    - 全て未達成 → 最後の 5 行（最も達成に近い順）
    - 全て達成 → 最初の 5 行（最も小さい努力順）

    Args:
        scenarios: list of dict, _calc_cross_ward_target の effort_scenarios
        fail_count: 未達成行を何行表示するか
        achieve_count: 達成行を何行表示するか

    Returns:
        list of dict: 抜粋後のシナリオ（最大 fail_count + achieve_count 行）
    """
    if not scenarios:
        return []
    max_rows = fail_count + achieve_count
    not_achieved = [s for s in scenarios if not s.get("achieves_target", False)]
    achieved = [s for s in scenarios if s.get("achieves_target", False)]

    if not achieved:
        # 全て未達成 → 最後の max_rows 行（最も達成に近い順）
        return scenarios[-max_rows:]
    if not not_achieved:
        # 全て達成 → 最初の max_rows 行
        return scenarios[:max_rows]

    # 通常: 遷移点周辺 — 未達成の末尾 + 達成の先頭
    tail_fail = not_achieved[-fail_count:]
    head_achieve = achieved[:achieve_count]
    return tail_fail + head_achieve


# ---------------------------------------------------------------------------
# 稼働率アラート付きKPI表示ヘルパー
# ---------------------------------------------------------------------------
def _render_ward_kpi_with_alert(raw_df, target_lower, target_upper, view_beds):
    """病棟KPIを表示し、稼働率低下時はアラートを表示する"""
    st.session_state["_holistic_table_content"] = None
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
            f"（空床 {_sel_empty}床 = 空床の影響額 約{_sel_empty * int(_daily_rev_per_bed) // 10000:.0f}万円/日・**今月残り{_remaining_days}日で約{_sel_empty * int(_daily_rev_per_bed) * _remaining_days // 10000:.0f}万円**）\n\n"
            "**対策:**\n"
            "- 🏥 予定入院の前倒しを外来担当医へ依頼\n"
            "- 📞 連携室へ依頼：紹介元クリニック・病院へ空床受入れ可能を発信\n"
            "- 💬 外来担当医に入院推奨閾値の引き下げを相談（通院患者の入院検討）\n"
            f"- 🔄 C群患者の戦略的在院調整（平均在院日数{_max_avg_los}日以内で調整可、運営貢献額28,900円/日を維持）\n"
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
                    f"**月間 空床の影響額見込み**: 約{int(_mt['gap_patients'] * 25000 * _mt['days_remaining'] // 10000)}万円"
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
            # --- 全体主義メッセージ（単体困難時に表示 — 均等努力方式）---
            _hw_dfs = _get_holistic_ward_dfs()
            if _mt["difficulty"] in ("hard", "impossible") and _hw_dfs:
                _cw = _calc_cross_ward_target(_hw_dfs, target_lower, globals().get("_calendar_month_days", 30), get_ward_beds, helper_cap * 100)
                if _cw and _cw["overall_achievable"]:
                    _ee = _cw["equal_effort"]
                    _delta = _cw["delta"]
                    if _delta > 0:
                        # Δ > 0: 両病棟とも追加努力が必要なケース
                        _lines = [
                            f"🤝 **助け合いで目標達成 — 助け合い方式**\n\n"
                            f"{_selected_ward_key}単体での月平均{_cw['target_pct']:.0f}%達成は困難ですが、"
                            f"**両病棟が均等に+{_delta:.1f}pt上昇**すれば全体達成可能です。\n\n"
                            f"**■ 助け合い目標（残り{_cw['days_remaining']}日）**\n"
                        ]
                        for w in ["5F", "6F"]:
                            _wi = _cw["wards"][w]
                            _ei = _ee[w]
                            _cap_note = "" if _ei["within_cap"] else f" ⚠️上限{_cw['helper_cap_pct']:.0f}%超"
                            _lines.append(f"- {w}: 現在平均 {_wi['avg']:.1f}% → 目標 **{_ei['target']:.1f}%**（+{_delta:.1f}pt）{_cap_note}\n")
                        _lines.append("\n")
                        # 多段階シナリオ表（遷移点周辺5行に絞って表示）
                        _tbl = "**■ 上昇幅別シナリオ（遷移点周辺）**\n\n"
                        _tbl += "| 上昇幅 | 5F目標 | 6F目標 | 全体 | 達成 |\n|---|---|---|---|---|\n"
                        _display_scenarios = _filter_effort_scenarios_for_display(_cw["effort_scenarios"])
                        for _es in _display_scenarios:
                            _mark = "✅" if _es["achieves_target"] and _es["feasible"] else "⚠️" if _es["achieves_target"] else "❌"
                            if not _es["within_cap"]:
                                _mark = "🔶" if _es["achieves_target"] else "❌"
                            _bold = "**" if abs(_es["delta"] - _delta) < 0.5 else ""
                            _tbl += f"| {_bold}{_es['delta']:+.0f}pt{_bold} | {_bold}{_es['5F']:.1f}%{_bold} | {_bold}{_es['6F']:.1f}%{_bold} | {_bold}{_es['overall']:.1f}%{_bold} | {_mark} |\n"
                        _lines.append(_tbl)
                        st.session_state["_holistic_table_content"] = ("info", "".join(_lines))
                    else:
                        # Δ ≤ 0: 全体ペースは既に目標達成済 — 追加努力不要
                        _other_w = "6F" if _selected_ward_key == "5F" else "5F"
                        _wi_self = _cw["wards"][_selected_ward_key]
                        _wi_other = _cw["wards"][_other_w]
                        _overall_now = (_wi_self["avg"] * _wi_self["beds"] + _wi_other["avg"] * _wi_other["beds"]) / (_wi_self["beds"] + _wi_other["beds"])
                        _lines = [
                            f"🤝 **助け合いで既に目標達成ペース — 追加努力不要**\n\n"
                            f"{_selected_ward_key}単体での月平均{_cw['target_pct']:.0f}%達成は困難ですが、"
                            f"**{_other_w}が{_wi_other['avg']:.1f}%で高稼働のため、全体（94床）では現在 {_overall_now:.1f}% で既に目標をクリア**しています。\n\n"
                            f"- {_selected_ward_key}: 現在平均 {_wi_self['avg']:.1f}%\n"
                            f"- {_other_w}: 現在平均 {_wi_other['avg']:.1f}%\n"
                            f"- 全体加重平均: **{_overall_now:.1f}%** （経営目標{_cw['target_pct']:.0f}%クリア）\n\n"
                            f"💡 稼働率は限られた病床で医療を届け続けるための目標です。施設基準（地域包括医療病棟）の要件は**平均在院日数**のみで、稼働率要件はありません。\n"
                        ]
                        st.session_state["_holistic_table_content"] = ("success", "".join(_lines))
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
        # --- 全体主義チェック: 均等努力方式で両病棟の目標を表示 ---
        _holistic_msg_shown = False
        _holistic_ward_dfs2 = _get_holistic_ward_dfs()
        if _selected_ward_key in ("5F", "6F") and _holistic_ward_dfs2:
            _cw_msg = _calc_cross_ward_target(_holistic_ward_dfs2, target_lower, globals().get("_calendar_month_days", 30), get_ward_beds, helper_cap * 100)
            if _cw_msg and _cw_msg["overall_achievable"] and _cw_msg.get("helped_ward"):
                _ee_msg = _cw_msg["equal_effort"]
                _delta_msg = _cw_msg["delta"]
                _ee_self = _ee_msg[_selected_ward_key]
                _other_w = "6F" if _selected_ward_key == "5F" else "5F"
                _ee_other = _ee_msg[_other_w]
                if _ee_self["within_cap"] and _ee_other["within_cap"]:
                    st.success(
                        f"🤝 **助け合いで全体目標達成ペース**: "
                        f"経過{_mt['days_elapsed']}日の平均 {_mt['avg_so_far']:.1f}% — "
                        f"両病棟とも **+{_delta_msg:.1f}pt** ずつ上昇すれば全体{_cw_msg['target_pct']:.0f}%達成"
                        f"（{_selected_ward_key}→{_ee_self['target']:.1f}%, {_other_w}→{_ee_other['target']:.1f}%）"
                    )
                else:
                    st.warning(
                        f"🤝 **助け合いでは上限超過あり**: "
                        f"両病棟+{_delta_msg:.1f}ptで全体達成ですが、一部が上限{_cw_msg['helper_cap_pct']:.0f}%を超えます。"
                        f"（{_selected_ward_key}→{_ee_self['target']:.1f}%, {_other_w}→{_ee_other['target']:.1f}%）"
                    )
                # 助け合い目標の多段階テーブル
                _h_lines = [
                    f"🤝 **助け合いで目標達成**\n\n"
                    f"両病棟が同じ上昇幅（Δ）で稼働率を上げ、全体{_cw_msg['target_pct']:.0f}%達成を目指します。\n\n"
                    f"**■ 助け合い目標（残り{_cw_msg['days_remaining']}日）**\n"
                ]
                for w in ["5F", "6F"]:
                    _wi = _cw_msg["wards"][w]
                    _ei = _ee_msg[w]
                    _cap_note = "" if _ei["within_cap"] else f" ⚠️上限{_cw_msg['helper_cap_pct']:.0f}%超"
                    _h_lines.append(f"- {w}: 現在平均 {_wi['avg']:.1f}% → 目標 **{_ei['target']:.1f}%**（+{_delta_msg:.1f}pt）{_cap_note}\n")
                _h_lines.append("\n")
                _h_tbl = "**■ 上昇幅別シナリオ（遷移点周辺）**\n\n"
                _h_tbl += "| 上昇幅 | 5F目標 | 6F目標 | 全体 | 達成 |\n|---|---|---|---|---|\n"
                _display_h = _filter_effort_scenarios_for_display(_cw_msg["effort_scenarios"])
                for _es in _display_h:
                    _mark = "✅" if _es["achieves_target"] and _es["feasible"] else "⚠️" if _es["achieves_target"] else "❌"
                    if not _es["within_cap"]:
                        _mark = "🔶" if _es["achieves_target"] else "❌"
                    _bold = "**" if abs(_es["delta"] - _delta_msg) < 0.5 else ""
                    _h_tbl += f"| {_bold}{_es['delta']:+.0f}pt{_bold} | {_bold}{_es['5F']:.1f}%{_bold} | {_bold}{_es['6F']:.1f}%{_bold} | {_bold}{_es['overall']:.1f}%{_bold} | {_mark} |\n"
                _h_lines.append(_h_tbl)
                st.session_state["_holistic_table_content"] = ("info", "".join(_h_lines))
                _holistic_msg_shown = True
        if not _holistic_msg_shown:
            st.success(
                f"✅ **月平均{_mt['monthly_target_pct']:.0f}%達成ペース**: "
                f"経過{_mt['days_elapsed']}日の平均 {_mt['avg_so_far']:.1f}% — "
                f"残り{_mt['days_remaining']}日も **{_mt['required_occ']:.1f}%以上** を維持すれば目標達成"
            )

    # --- 全体主義メッセージ（追加表示: 困難側 — 均等努力方式） ---
    _holistic_ward_dfs3 = _get_holistic_ward_dfs()
    if _holistic_ward_dfs3 and _mt and _selected_ward_key in ("5F", "6F"):
        _cw2 = _calc_cross_ward_target(_holistic_ward_dfs3, target_lower, globals().get("_calendar_month_days", 30), get_ward_beds, helper_cap * 100)
        if _cw2 and _cw2["overall_achievable"]:
            if _cw2.get("helped_ward") == _selected_ward_key and _mt["difficulty"] in ("hard", "impossible"):
                _ee2 = _cw2["equal_effort"]
                _delta2 = _cw2["delta"]
                _lines2 = [
                    f"🤝 **助け合いで全体目標達成が可能**\n\n"
                    f"{_selected_ward_key}単体は困難でも、両病棟が均等に **+{_delta2:.1f}pt** 上昇すれば全体{_cw2['target_pct']:.0f}%達成可能。\n\n"
                ]
                for w in ["5F", "6F"]:
                    _wi2 = _cw2["wards"][w]
                    _ei2 = _ee2[w]
                    _lines2.append(f"- {w}: 現在平均 {_wi2['avg']:.1f}% → 目標 **{_ei2['target']:.1f}%**（+{_delta2:.1f}pt）\n")
                _lines2.append("\n")
                _tbl2 = "**■ 上昇幅別シナリオ（遷移点周辺）**\n\n"
                _tbl2 += "| 上昇幅 | 5F目標 | 6F目標 | 全体 | 達成 |\n|---|---|---|---|---|\n"
                _display_2 = _filter_effort_scenarios_for_display(_cw2["effort_scenarios"])
                for _es2 in _display_2:
                    _m2 = "✅" if _es2["achieves_target"] and _es2["feasible"] else "⚠️" if _es2["achieves_target"] else "❌"
                    if not _es2["within_cap"]:
                        _m2 = "🔶" if _es2["achieves_target"] else "❌"
                    _b2 = "**" if abs(_es2["delta"] - _delta2) < 0.5 else ""
                    _tbl2 += f"| {_b2}{_es2['delta']:+.0f}pt{_b2} | {_b2}{_es2['5F']:.1f}%{_b2} | {_b2}{_es2['6F']:.1f}%{_b2} | {_b2}{_es2['overall']:.1f}%{_b2} | {_m2} |\n"
                _lines2.append(_tbl2)
                st.session_state["_holistic_table_content"] = ("info", "".join(_lines2))


# ---------------------------------------------------------------------------
# 本日のサマリー（折りたたみ可能・タブ外最上部）
# 本日の病床状況 + 今日の一手 + KPI + アラートをまとめて1つの expander に
# 朝の確認後は折りたたんで、モード別タブコンテンツに集中できる
# ---------------------------------------------------------------------------
_summary_expander = st.expander("☀️ 本日のサマリー（クリックで折りたたみ）", expanded=True)

_is_demo = st.session_state.get("data_mode") == "🎮 デモモード（サンプルデータ）"
_sim_has_data = _simulation_available and isinstance(st.session_state.get("sim_df_raw"), pd.DataFrame) and len(st.session_state.sim_df_raw) > 0
if _actual_data_available or _sim_has_data or (_is_demo and isinstance(st.session_state.get("demo_data"), pd.DataFrame) and len(st.session_state.get("demo_data", pd.DataFrame())) > 0):
    with _summary_expander:
        _brief_cols = st.columns([1, 1, 1, 2])

        # 稼働率ゲージ（plotly gauge chart）
        with _brief_cols[0]:
            import plotly.graph_objects as go
            _gauge_occ_col = "occupancy_rate" if "occupancy_rate" in _active_raw_df.columns else "稼働率"
            _gauge_occ = float(_active_raw_df[_gauge_occ_col].mean() * 100) if _active_raw_df[_gauge_occ_col].mean() < 1.5 else float(_active_raw_df[_gauge_occ_col].mean())
            _gauge_fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=_gauge_occ,
                number={"suffix": "%", "font": {"size": 28}},
                title={"text": f"月平均稼働率（{_selected_ward_key}）", "font": {"size": 11}},
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
            _gauge_fig.update_layout(height=140, margin=dict(l=10, r=10, t=30, b=0))
            st.plotly_chart(_gauge_fig, use_container_width=True)

        # 主要KPI
        with _brief_cols[1]:
            _brief_tp_col = "total_patients" if "total_patients" in _active_raw_df.columns else "在院患者数"
            _brief_patients = int(_active_raw_df[_brief_tp_col].iloc[-1])
            _brief_empty = _view_beds - _brief_patients
            st.metric("在院患者数（今の空き）", f"{_brief_patients}名", delta=f"空床 {_brief_empty}床")
            if _brief_empty > (_view_beds * 0.10):
                _remaining_days = _calc_remaining_days(_active_raw_df) if isinstance(_active_raw_df, pd.DataFrame) and len(_active_raw_df) > 0 else 0 if isinstance(_active_raw_df, pd.DataFrame) and len(_active_raw_df) > 0 else 0
                st.caption(f"⚠️ 空床{_brief_empty}床 = 空床の影響額 約{_brief_empty * int(_daily_rev_per_bed) // 10000:.0f}万円/日・今月残り{_remaining_days}日で約{_brief_empty * int(_daily_rev_per_bed) * _remaining_days // 10000:.0f}万円")

        # 病棟比較ミニバッジ
        with _brief_cols[2]:
            if _selected_ward_key == "全体":
                for _bw in ["5F", "6F"]:
                    _bw_beds = get_ward_beds(_bw)
                    if hasattr(st.session_state, 'sim_ward_raw_dfs') and _bw in st.session_state.get("sim_ward_raw_dfs", {}):
                        _bw_df = st.session_state.sim_ward_raw_dfs[_bw]
                        _bw_occ = float(_bw_df["occupancy_rate"].mean() * 100)
                    elif "_ward_raw_dfs" in dir() and _bw in _ward_raw_dfs:
                        _bw_df = _ward_raw_dfs[_bw]
                        _bw_occ_col = "occupancy_rate" if "occupancy_rate" in _bw_df.columns else "稼働率"
                        _bw_occ = float(_bw_df[_bw_occ_col].mean() * 100) if _bw_df[_bw_occ_col].mean() < 1.5 else float(_bw_df[_bw_occ_col].mean())
                    else:
                        _bw_occ = None
                    if _bw_occ is not None:
                        _bw_status = "✅ 目標内" if target_lower * 100 <= _bw_occ <= target_upper * 100 else "⚠️ 要注意"
                        st.markdown(f"**{_bw}**: {_bw_occ:.1f}% {_bw_status}")
            else:
                st.markdown(f"**{_selected_ward_key}** を表示中")
                _other = "6F" if _selected_ward_key == "5F" else "5F"
                st.caption(f"他病棟 → サイドバーで切替")

        # 今日のアクション（超簡潔版）
        with _brief_cols[3]:
            _occ_col_brief = "occupancy_rate" if "occupancy_rate" in _active_raw_df.columns else "稼働率"
            _last_occ_brief = float(_active_raw_df[_occ_col_brief].iloc[-1])
            if _last_occ_brief < 1.5:
                _last_occ_brief *= 100

            # 月平均稼働率も取得（直近1日と月平均の両方で総合判定する）
            _month_avg_brief = _gauge_occ  # ゲージ用に計算済みの月平均稼働率

            if _last_occ_brief < target_lower * 100:
                # 直近1日が目標未達
                _is_recovering = False
                if len(_active_raw_df) >= 3:
                    _rec_check = _active_raw_df[_occ_col_brief].tail(3).values
                    if _rec_check[0] < 1.5:
                        _rec_check = _rec_check * 100
                    if _rec_check[-1] - _rec_check[0] > 1:
                        _is_recovering = True
                if _is_recovering:
                    _action_icon = "📈"
                    _action_title = "回復中 — 対策継続"
                    _action_detail = "入院受入施策が効果を発揮中"
                else:
                    _action_icon = "🔴"
                    _action_title = "稼働率低下 — 即対応"
                    _action_detail = "連携室→空床発信 / 予定入院前倒し"
            elif _last_occ_brief > target_upper * 100:
                _action_icon = "🟡"
                _action_title = "高稼働 — 退院調整"
                _action_detail = "A→B群移行確認 / C群退院日確定"
            elif _month_avg_brief < target_lower * 100:
                # 直近1日は目標レンジ内だが、月平均は目標未達
                # → 「今日は良いが月全体では足りない」
                _action_icon = "📊"
                _action_title = "月平均未達 — ペースアップ"
                _action_detail = f"今日は目標内だが月平均{_month_avg_brief:.1f}%＜目標{target_lower*100:.0f}%"
            else:
                _action_icon = "🟢"
                _action_title = "目標レンジ内 — 維持継続"
                _action_detail = "退院タイミングを整え空床時間を最小化"

            # 月平均達成見通し
            _brief_month_days = 31
            if isinstance(_active_raw_df, pd.DataFrame) and len(_active_raw_df) > 0:
                _brief_date_ref = _active_raw_df["date"].iloc[-1] if "date" in _active_raw_df.columns else pd.Timestamp.now()
                if isinstance(_brief_date_ref, str):
                    _brief_date_ref = pd.to_datetime(_brief_date_ref)
                _brief_month_days = calendar.monthrange(_brief_date_ref.year, _brief_date_ref.month)[1]
            _mt_brief = _calc_monthly_target(_active_raw_df, target_lower, _brief_month_days, _view_beds) if isinstance(_active_raw_df, pd.DataFrame) and len(_active_raw_df) > 0 else None
            _mt_txt = ""
            if _mt_brief:
                if _mt_brief["avg_so_far"] >= _mt_brief["monthly_target_pct"]:
                    _mt_txt = f"✅ 月平均{_mt_brief['avg_so_far']:.1f}%達成ペース"
                else:
                    _mt_txt = f"📊 月平均{_mt_brief['avg_so_far']:.1f}%→残り{_mt_brief['days_remaining']}日で{_mt_brief['required_occ']:.0f}%必要"

            _mt_line = f'<br/><span style="color:#888;font-size:0.8em;">{_mt_txt}</span>' if _mt_txt else ''
            st.markdown(
                f"<div style='padding:4px 8px;background:#F8F9FA;border-radius:4px;font-size:0.9em;'>"
                f"{_action_icon} <strong>{_action_title}</strong><br/>"
                f"<span style='color:#555;font-size:0.85em;'>{_action_detail}</span>"
                f"{_mt_line}"
                f"</div>",
                unsafe_allow_html=True,
            )

        # --- 💡 空床数×稼働率 インサイト（1行版）---
        _empty_few = _brief_empty < (_view_beds * 0.10)
        _occ_high = _gauge_occ >= (target_lower * 100)

        if _empty_few and _occ_high:
            _insight_msg = "🟢 **回転良好** — 空床少+稼働率高"
        elif not _empty_few and not _occ_high:
            _insight_msg = "🔴 **入院増が必要** — 空床多+稼働率低"
        elif _empty_few and not _occ_high:
            _insight_msg = "⚠️ **詰まりの兆候** — 退院調整を確認"
        else:
            _insight_msg = "🟡 **受入余地あり** — 新規入院で伸ばせます"

        st.markdown(
            f"<div style='padding:4px 8px;background:#F0F4F8;border-left:3px solid #5B9BD5;"
            f"border-radius:3px;margin:4px 0;font-size:0.85em;'>"
            f"💡 {_insight_msg}"
            f" <span style='color:#999;font-size:0.8em;'>｜空床数＝今の判断 ・ 稼働率＝今月の成績</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

        # --- 📏 平均在院日数（rolling）— コンパクト版 ---
        if _DATA_MANAGER_AVAILABLE:
            _ward_rolling_results = {}
            _ward_dfs_for_rolling = (
                globals().get("_ward_raw_dfs_full", {})
                or st.session_state.get("ward_raw_dfs_full", {})
            )
            for _w in ["5F", "6F"]:
                _wdf = _ward_dfs_for_rolling.get(_w) if _ward_dfs_for_rolling else None
                if _wdf is None or not isinstance(_wdf, pd.DataFrame) or len(_wdf) == 0:
                    if _selected_ward_key == _w and isinstance(_active_raw_df_full, pd.DataFrame) and len(_active_raw_df_full) > 0:
                        _wdf = _active_raw_df_full
                    else:
                        continue
                try:
                    _ward_rolling_results[_w] = calculate_rolling_los(_wdf, window_days=90, monthly_summary=st.session_state.get("monthly_summary"), ward=_w)
                except Exception:
                    pass

            if _ward_rolling_results:
                _los_parts = []
                for _w, _rolling in _ward_rolling_results.items():
                    if _rolling is None or _rolling.get("rolling_los") is None:
                        continue
                    _r_los_ex = _rolling.get("rolling_los_ex_short3")
                    _r_los = _rolling["rolling_los"]
                    _r_judge = _r_los_ex if _r_los_ex is not None else _r_los
                    _r_diff = _r_judge - _max_avg_los
                    if _r_judge <= _max_avg_los:
                        _r_icon = "✅"
                        _r_color = "#27AE60"
                    elif _r_judge <= _max_avg_los + 0.5:
                        _r_icon = "⚠️"
                        _r_color = "#F39C12"
                    else:
                        _r_icon = "🔴"
                        _r_color = "#C0392B"
                    _los_parts.append(
                        f"<strong>{_w}</strong>{_r_icon}"
                        f"<strong style='color:{_r_color};'>{_r_judge}日</strong>"
                        f"/{_max_avg_los}日"
                    )
                if _los_parts:
                    st.markdown(
                        f"<div style='padding:4px 8px;background:#F8F9FA;border-left:3px solid #3498DB;"
                        f"border-radius:3px;margin:2px 0;font-size:0.85em;'>"
                        f"📏 在院日数(90日rolling): {' ｜ '.join(_los_parts)}"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

# ---------------------------------------------------------------------------
# 結論カード（今日の一手）— サマリー expander 内に表示
# ---------------------------------------------------------------------------
_ac_has_data = isinstance(_active_raw_df, pd.DataFrame) and len(_active_raw_df) > 0
if _selected_section in ["📊 今日の運営", "🔮 What-if・戦略"]:
    if not (_ACTION_CARD_AVAILABLE and _VIEWS_AVAILABLE):
        _missing = []
        if not _ACTION_CARD_AVAILABLE:
            _missing.append(f"action_recommendation: {_ACTION_CARD_ERROR}")
        if not _VIEWS_AVAILABLE:
            _missing.append(f"views: {_VIEWS_ERROR}")
        with st.expander("⚙️ 結論カード モジュール読み込み状況", expanded=False):
            for _m in _missing:
                st.code(_m)

    if _ac_has_data and _ACTION_CARD_AVAILABLE and _VIEWS_AVAILABLE:
        _ac_emergency_summary = None
        _ac_guardrail_status = None
        _ac_los_headroom = None
        _ac_morning_capacity = None
        _ac_morning_5f = None
        _ac_morning_6f = None
        _ac_monthly_kpi = None
        _ac_c_summary = None
        _ac_c_capacity = None
        _ac_demand_class = None
        _ac_occupancy = None

        try:
            _ac_daily_df = _active_raw_df if isinstance(_active_raw_df, pd.DataFrame) and len(_active_raw_df) > 0 else None
            # LOS計算には rolling 90日分が必要 → full データを使う
            _ac_daily_df_full = _active_raw_df_full if isinstance(_active_raw_df_full, pd.DataFrame) and len(_active_raw_df_full) > 0 else _ac_daily_df
            # 翌朝受入余力「全体」は常に病院全体データで計算する（病棟選択に汚染されない）
            # _daily_df はデータ管理タブ（後方）で初めて定義されるため、ここでは session_state から直接取得
            _ac_overall_src = locals().get("_daily_df", st.session_state.get("daily_data"))
            _ac_overall_df = _ac_overall_src if isinstance(_ac_overall_src, pd.DataFrame) and len(_ac_overall_src) > 0 else _ac_daily_df
            _ac_detail_df = st.session_state.get("admission_details") if _DETAIL_DATA_AVAILABLE else None
            if isinstance(_ac_detail_df, pd.DataFrame) and len(_ac_detail_df) == 0:
                _ac_detail_df = None
            _ac_config = {"age_85_ratio": 0.25, "monthly_summary": st.session_state.get("monthly_summary", {})}

            if _ac_daily_df is not None:
                _ac_occ_key = "occupancy_rate" if "occupancy_rate" in _ac_daily_df.columns else "稼働率"
                _ac_occ_val = _ac_daily_df.iloc[-1].get(_ac_occ_key, None)
                if _ac_occ_val is not None and pd.notna(_ac_occ_val):
                    _ac_occupancy = float(_ac_occ_val)

            if _EMERGENCY_RATIO_AVAILABLE and _ac_detail_df is not None:
                try:
                    _ac_emergency_summary = get_ward_emergency_summary(_ac_detail_df)
                except Exception:
                    pass

            if _GUARDRAIL_AVAILABLE and _ac_daily_df is not None:
                try:
                    _ac_guardrail_status = calculate_guardrail_status(_ac_daily_df, _ac_detail_df, _ac_config)
                except Exception:
                    pass

            if _GUARDRAIL_AVAILABLE and _ac_daily_df_full is not None:
                try:
                    _ac_los_headroom = calculate_los_headroom(_ac_daily_df_full, _ac_config)
                except Exception:
                    pass

            if _EMERGENCY_RATIO_AVAILABLE and _ac_overall_df is not None:
                try:
                    _ac_morning_capacity = estimate_next_morning_capacity(
                        _ac_overall_df, _ac_detail_df, ward=None, total_beds=94,
                    )
                except Exception:
                    pass
                _ac_morning_5f = None
                _ac_morning_6f = None
                # 病棟別の受入余力は病棟別データを使う（全体合算データではward="5F"が見つからない）
                _ac_ward_dfs = st.session_state.get("sim_ward_raw_dfs") or st.session_state.get("ward_raw_dfs") or {}
                try:
                    if "5F" in _ac_ward_dfs and isinstance(_ac_ward_dfs["5F"], pd.DataFrame) and len(_ac_ward_dfs["5F"]) > 0:
                        _ac_morning_5f = estimate_next_morning_capacity(
                            _ac_ward_dfs["5F"], _ac_detail_df, ward="5F", ward_beds=47,
                        )
                    if "6F" in _ac_ward_dfs and isinstance(_ac_ward_dfs["6F"], pd.DataFrame) and len(_ac_ward_dfs["6F"]) > 0:
                        _ac_morning_6f = estimate_next_morning_capacity(
                            _ac_ward_dfs["6F"], _ac_detail_df, ward="6F", ward_beds=47,
                        )
                except Exception:
                    pass

            if _ac_daily_df is not None:
                try:
                    _ac_monthly_kpi = predict_monthly_kpi(_ac_daily_df, num_beds=_view_beds)
                except Exception:
                    pass

            if _GUARDRAIL_AVAILABLE and _ac_daily_df is not None:
                try:
                    _ac_c_summary = get_c_group_summary(_ac_daily_df, ward=_selected_ward_key if _selected_ward_key in ("5F", "6F") else None)
                    _ac_rolling = calculate_rolling_los(_ac_daily_df_full, window_days=90, monthly_summary=st.session_state.get("monthly_summary"), ward=_selected_ward_key if _selected_ward_key in ("5F", "6F") else None)
                    _ac_los_limit = calculate_los_limit(_ac_config.get("age_85_ratio", 0.25))
                    _ac_c_capacity = calculate_c_adjustment_capacity(
                        _ac_rolling, _ac_los_limit,
                        _ac_c_summary.get("c_count") if _ac_c_summary else None,
                    )
                except Exception:
                    pass

            if _GUARDRAIL_AVAILABLE and _ac_daily_df is not None:
                try:
                    _ac_demand_class = classify_demand_period(_ac_daily_df)
                except Exception:
                    pass

        except Exception as _ac_data_err:
            # データ準備の例外を握り潰さず、デバッグ用にキャプションで表示
            st.caption(f"⚠️ KPIデータ準備エラー: {type(_ac_data_err).__name__}: {_ac_data_err}")

        try:
            _ac_selected = _selected_ward_key if _selected_ward_key in ("5F", "6F") else None
            _ac_card = generate_action_card(
                emergency_summary=_ac_emergency_summary,
                guardrail_status=_ac_guardrail_status,
                los_headroom=_ac_los_headroom,
                morning_capacity=_ac_morning_capacity,
                monthly_kpi=_ac_monthly_kpi,
                c_group_summary=_ac_c_summary,
                c_adjustment_capacity=_ac_c_capacity,
                demand_classification=_ac_demand_class,
                occupancy_rate=_ac_occupancy,
                target_occupancy=target_lower if "target_lower" in dir() else 0.90,
                selected_ward=_ac_selected,
            )
            with _summary_expander:
                render_action_card(_ac_card)

                # -----------------------------------------------------------
                # 短手3 Day 5 到達アラート（本則完全適用後 = 2026-06-01 以降のみ）
                # -----------------------------------------------------------
                # 本則適用後は LOS 計算の分母に、短手3 患者の入院日数を
                # 「5日まで含めない、6日目以降は入院初日まで遡って全日数カウント」
                # という階段関数で扱う。Day 5 到達患者が翌日延長すると、その瞬間に
                # LOS 分母に +6 日 jump する不連続点が発生するため事前警告する。
                #
                # bed_data_manager.get_short3_day5_patients() を呼び出して
                # Day 5 到達の短手3 患者を検出する。
                _short3_day5_alert_enabled = True  # 2026-04-17 本実装で有効化
                if (
                    _short3_day5_alert_enabled
                    and _EMERGENCY_RATIO_AVAILABLE
                    and not is_transitional_period(date.today())
                    and _ac_detail_df is not None
                ):
                    try:
                        from bed_data_manager import get_short3_day5_patients
                        _short3_day5 = get_short3_day5_patients(_ac_detail_df, date.today())
                        if _short3_day5:
                            st.warning(
                                f"⚠️ 短手3 患者 {len(_short3_day5)} 名が入院 Day 5 到達。"
                                "明日（Day 6）に滞在が延びると、入院初日まで遡って LOS 分母に "
                                "+6 日計上されます（6/1 以降の本則適用ルール）。"
                            )
                    except Exception:
                        pass

            _ac_kpi_list = generate_kpi_priority_list(
                emergency_summary=_ac_emergency_summary,
                guardrail_status=_ac_guardrail_status,
                los_headroom=_ac_los_headroom,
                morning_capacity=_ac_morning_capacity,
                morning_capacity_5f=_ac_morning_5f,
                morning_capacity_6f=_ac_morning_6f,
                monthly_kpi=_ac_monthly_kpi,
                c_group_summary=_ac_c_summary,
                c_adjustment_capacity=_ac_c_capacity,
                occupancy_rate=_ac_occupancy,
                target_occupancy=target_lower if "target_lower" in dir() else 0.90,
            )
            with _summary_expander:
                render_kpi_priority_strip(_ac_kpi_list)

                if _ac_morning_capacity is not None:
                    render_morning_capacity_card(_ac_morning_capacity, morning_5f=_ac_morning_5f, morning_6f=_ac_morning_6f)

                if _ac_c_capacity is not None:
                    _ac_tradeoff = generate_tradeoff_assessment(
                        c_adjustment_capacity=_ac_c_capacity,
                        emergency_summary=_ac_emergency_summary,
                        morning_capacity=_ac_morning_capacity,
                        los_headroom=_ac_los_headroom,
                    )
                    render_tradeoff_card(_ac_tradeoff)
        except Exception as _render_err:
            st.error(f"結論カード描画エラー: {_render_err}")
            import traceback
            st.code(traceback.format_exc())


# ---------------------------------------------------------------------------
# セクション共通ヘッダー（サマリー expander 内に表示）
# ---------------------------------------------------------------------------
if _selected_section in ["📊 今日の運営", "🔮 What-if・戦略"]:
  with _summary_expander:
    # 病棟選択キャプション
    if _selected_ward_key != "全体":
        st.caption(f"📍 {_selected_ward_key} ({_view_beds}床) のデータを表示中")
    # 病棟KPIアラート
    if _selected_ward_key != "全体":
        if isinstance(_active_raw_df, pd.DataFrame) and len(_active_raw_df) > 0:
            _render_ward_kpi_with_alert(_active_raw_df, target_lower, target_upper, _view_beds)
    # 全体稼働率低下アラート（実績データモード）
    if _is_actual_data_mode:
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
                    f"（空床{_total_empty}床 = 空床の影響額 約{_total_empty * int(_daily_rev_per_bed) // 10000:.0f}万円/日・**今月残り{_remaining_days}日で約{_total_empty * int(_daily_rev_per_bed) * _remaining_days // 10000:.0f}万円**）\n\n"
                    "**対策:** ① 外来へ予定入院の前倒しを依頼 ② 連携室へ紹介元への空床発信を依頼 ③ 外来担当医に入院閾値の引き下げを相談 + C群の戦略的在院調整で稼働率維持"
                )
        # 比較ストリップ
        if _ward_data_available:
            _render_comparison_strip(_selected_ward_key, _ward_raw_dfs, _ward_display_dfs, get_ward_beds)

# What-if・戦略セクション: 機能チェックをタブの外に表示
if _selected_section == "🔮 What-if・戦略" and not _DECISION_SUPPORT_AVAILABLE:
    st.error("意思決定支援機能はまだ利用できません。CLI版（bed_control_simulator.py）に必要な関数が実装されていません。")
    if "_DECISION_SUPPORT_ERROR" in dir():
        st.code(_DECISION_SUPPORT_ERROR)

# ---------------------------------------------------------------------------
# セクション別タブ構成（_selected_section はサイドバー上部で定義済み）
# ---------------------------------------------------------------------------
if _selected_section == "\U0001f4ca 今日の運営":
    # Phase 2 情報階層リデザイン（2026-04-18）: 旧「📊 ダッシュボード」を改名し、
    # 旧「🎯 意思決定支援」（Phase 3 で「🔮 What-if・戦略」に改名）から
    # 「意思決定ダッシュボード」「運営改善アラート」を集約。
    # 朝の目線の流れ（総合状況 → アラート → 詳細指標）に沿って 6 タブ構成。
    # 2026-04-18 追加: 「📉 過去実績分析」タブ（FY2025 実績可視化）を末尾に追加
    tab_names = ["\U0001f3af 意思決定ダッシュボード", "\U0001f6a8 運営改善アラート", "\U0001f4ca 日次推移", "\U0001f504 フェーズ構成", "\U0001f4b0 運営分析", "\U0001f4c8 トレンド分析"]
    if _PAST_PERF_VIEW_AVAILABLE:
        tab_names.append("\U0001f4c9 過去実績分析")
elif _selected_section == "\U0001f52e What-if・戦略":
    # Phase 1: 「👨‍⚕️ 退院タイミング」タブを「🏥 退院調整」へ移設
    # Phase 2: 「意思決定ダッシュボード」「運営改善アラート」を「📊 今日の運営」へ移設
    # Phase 3: セクション名を「🎯 意思決定支援」→「🔮 What-if・戦略」へ改名（仮説検証・経営シミュレーション専用）
    # 2026-04-18: 「戦略比較」タブを削除（戦略選択 UI 廃止に伴う）
    # → What-if 分析 + 仮説管理の 1-2 タブ構成
    tab_names = ["\U0001f52e What-if分析"]
    if _SCENARIO_MANAGER_AVAILABLE:
        tab_names.append("\U0001f4be 仮説管理")
elif _selected_section == "\U0001f6e1\ufe0f 制度管理":
    tab_names = ["\U0001f6e1\ufe0f 制度・需要・C群"]
    if _DOCTOR_MASTER_AVAILABLE:
        tab_names.append("\U0001f4a1 改善のヒント")
    # 2026-04-25: 「📊 過去1年分析」は新セクション「📈 過去1年分析」に移設（Phase 5）
elif _selected_section == "\U0001f4c8 過去1年分析":
    # 2026-04-25 Phase 5: 経営者目線の過去 1 年深掘り分析（独立セクションに昇格）
    # 旧「🛡️ 制度管理 > 📊 過去1年分析」タブを移設。1 タブ単一ページ構成。
    tab_names = ["\U0001f4ca 過去1年分析"]
elif _selected_section == "\U0001f3e5 退院調整":
    # Phase 1 情報階層リデザイン（2026-04-18）: 5 タブ統合
    # 2026-04-23: 「📅 退院カレンダー」を新規追加（副院長指示）、既存「📅 予約可能枠」を「📅 入院受入枠」に改名
    # カンファ資料 / 退院カレンダー / 退院タイミング / 今週の需要予測 / 退院候補リスト / 入院受入枠
    tab_names = ["\U0001f3e5 カンファ資料", "\U0001f4c5 退院カレンダー", "\U0001f468\u200d\u2695\ufe0f 退院タイミング", "\U0001f4ca 今週の需要予測", "\U0001f4cb 退院候補リスト", "\U0001f4c5 入院受入枠"]
elif _selected_section == "\u2699\ufe0f データ・設定":
    # Phase 4 情報階層リデザイン（2026-04-18・最終）: 旧「📋 データ管理」に
    # 旧「📨 HOPE連携」セクションとサイドバー「🏃 短手3 パラメータ」を統合した 7 タブ構成
    tab_names = []
    if _DATA_MANAGER_AVAILABLE:
        tab_names.extend(["\U0001f4cb 日次データ入力", "\U0001f52e 実績分析・予測"])
    if _DOCTOR_MASTER_AVAILABLE:
        tab_names.extend(["\U0001f468\u200d\u2695\ufe0f 医師別分析", "\u2699\ufe0f 医師マスター"])
    tab_names.append("\U0001f4e5 データエクスポート")
    if _HOPE_AVAILABLE:
        tab_names.append("\U0001f4e8 HOPE送信")
    tab_names.append("\U0001f3c3 短手3設定")
    tab_names.append("データ")
else:
    tab_names = ["\U0001f4ca 日次推移"]

# タブナビゲーション（モード名 + 区切りバー）
_section_label = _selected_section if "_selected_section" in dir() else "📊 今日の運営"
st.markdown(
    f'<div style="background:linear-gradient(90deg,#1E88E5 0%,#42A5F5 100%);'
    f'padding:8px 16px;border-radius:8px;margin:12px 0 4px 0;">'
    f'<span style="color:white;font-weight:bold;font-size:1.0em;">'
    f'{_section_label}</span>'
    f'<span style="color:rgba(255,255,255,0.7);font-size:0.85em;margin-left:12px;">'
    f'👇 タブで切り替え</span></div>',
    unsafe_allow_html=True,
)

# セクションの visible tabs だけを作成（hidden tab + CSS 方式を廃止）
tabs = st.tabs(tab_names)
_tab_idx = {name: i for i, name in enumerate(tab_names)}

# =====================================================================
# 日次データ管理タブ（シミュレーション未実行でも利用可能）
# st.stop() の前に配置することで、シミュレーション未実行でも表示される
# =====================================================================
if _DATA_MANAGER_AVAILABLE and "📋 日次データ入力" in _tab_idx:
    _dm_tab_daily_idx = _tab_idx["📋 日次データ入力"]
    _dm_tab_analysis_idx = _tab_idx.get("🔮 実績分析・予測")

    # ----- タブ: 📋 日次データ入力 -----
    _dm_auth_ok = False
    with tabs[_dm_tab_daily_idx]:
        _bc_section_title("日次データ入力", icon="📋")
        _dm_auth_ok = _require_data_auth("データ入力")

    # 認証成功時のみタブ内容を描画（st.stop()を使わず他タブへの影響を防ぐ）
    if _dm_auth_ok:
        with tabs[_dm_tab_daily_idx]:
            # --- モード切替 ---
            st.radio(
                "データモード",
                ["📊 実データ入力モード", "🎮 デモモード（サンプルデータ）"],
                key="data_mode",
            )
            _is_demo_mode = st.session_state.data_mode == "🎮 デモモード（サンプルデータ）"

            st.markdown("---")

            # ============================================================
            # 📊 本日のサマリー KPI — 入力者が今の状況を把握した上で入力する
            # ============================================================
            _bc_section_title("本日のサマリー", icon="📊")

            # 本日の入退院数・現在の在院数を計算
            _today_ts = pd.Timestamp.now().normalize()
            try:
                if _is_demo_mode:
                    _src_df = st.session_state.demo_data
                else:
                    _src_df = st.session_state.daily_data
                if isinstance(_src_df, pd.DataFrame) and len(_src_df) > 0 and "date" in _src_df.columns:
                    _df_chk = _src_df.copy()
                    _df_chk["date"] = pd.to_datetime(_df_chk["date"], errors="coerce")
                    _today_rows = _df_chk[_df_chk["date"] == _today_ts]
                    _n_adm_today = int(_today_rows["new_admissions"].fillna(0).sum()) if "new_admissions" in _today_rows.columns else 0
                    _n_dis_today = int(_today_rows["discharges"].fillna(0).sum()) if "discharges" in _today_rows.columns else 0
                else:
                    _n_adm_today = 0
                    _n_dis_today = 0
            except Exception:
                _n_adm_today = 0
                _n_dis_today = 0

            _abc_cur = st.session_state.get("abc_state", {"A": 0, "B": 0, "C": 0})
            _n_inpatients = int(_abc_cur.get("A", 0)) + int(_abc_cur.get("B", 0)) + int(_abc_cur.get("C", 0))

            _sum_col1, _sum_col2, _sum_col3 = st.columns(3)
            with _sum_col1:
                _bc_kpi_card(
                    label="本日の入院",
                    value=str(_n_adm_today),
                    unit="件",
                    severity="info" if _n_adm_today > 0 else "neutral",
                )
            with _sum_col2:
                _bc_kpi_card(
                    label="本日の退院",
                    value=str(_n_dis_today),
                    unit="件",
                    severity="info" if _n_dis_today > 0 else "neutral",
                )
            with _sum_col3:
                _bc_kpi_card(
                    label="現在の在院",
                    value=str(_n_inpatients),
                    unit="名",
                    severity="neutral",
                )

            st.markdown("---")

            if _is_demo_mode:
                # ============================================================
                # デモモード
                # ============================================================
                _bc_alert(
                    "🎓 これは教育用デモデータです。5F（稼働率低下傾向）と6F（安定稼働）のシナリオが含まれています。",
                    severity="info",
                )

                # デモデータが既にロード済みかチェック
                _demo_loaded = isinstance(st.session_state.demo_data, pd.DataFrame) and len(st.session_state.demo_data) > 0

                (
                    dm_demo_col1,
                    dm_demo_col2,
                    dm_demo_col3,
                    dm_demo_col4,
                    dm_demo_col5,
                ) = st.columns(5)
                with dm_demo_col1:
                    if _demo_loaded:
                        _demo_ward_count = st.session_state.demo_data["ward"].nunique() if "ward" in st.session_state.demo_data.columns else 0
                        _demo_day_count = st.session_state.demo_data["date"].nunique() if "date" in st.session_state.demo_data.columns else 0
                        _bc_alert(
                            f"デモデータロード済（{_demo_ward_count}病棟 × {_demo_day_count}日分）",
                            severity="success",
                        )
                    else:
                        _bc_alert("デモデータが見つかりません", severity="warning")
                with dm_demo_col2:
                    if st.button(
                        "📊 年度デモデータ生成（2026FY 365日分）",
                        key="dm_gen_yearly",
                        help="2026年度全体（4/1〜翌3/31）に季節性・連休パターンを織り込んだ1年分のデモデータを生成します",
                    ):
                        try:
                            from generate_demo_data_2026fy import generate_yearly_data
                            _yearly = generate_yearly_data(year=2026, seed=42)
                            _yearly_daily = _yearly["daily_df"].copy()
                            _yearly_daily["date"] = pd.to_datetime(_yearly_daily["date"])
                            # occupancy_rate / num_beds 補完（初期ロード時と同じロジック）
                            if "num_beds" not in _yearly_daily.columns:
                                _yearly_daily["num_beds"] = _yearly_daily["ward"].map(lambda w: get_ward_beds(w))
                            if "occupancy_rate" not in _yearly_daily.columns:
                                _yearly_daily["occupancy_rate"] = (
                                    (_yearly_daily["total_patients"] + _yearly_daily["discharges"])
                                    / _yearly_daily["num_beds"] * 100
                                ).round(1)
                            st.session_state.demo_data = _yearly_daily.sort_values(["date", "ward"]).reset_index(drop=True)
                            _bc_alert(
                                f"2026年度デモデータ（2病棟×365日 = {len(_yearly_daily)}レコード）を生成しました。"
                                "GW・お盆・年末年始を含む連休前後パターンと、冬季呼吸器感染症ピーク等の季節性が反映されています。",
                                severity="success",
                            )
                            _auto_save_to_db()
                            st.rerun()
                        except ImportError as _e:
                            _bc_alert(
                                f"年度デモデータ生成モジュールが読み込めません: {_e}",
                                severity="danger",
                            )
                        except Exception as _e:  # noqa: BLE001
                            _bc_alert(f"年度デモデータ生成に失敗しました: {_e}", severity="danger")

                with dm_demo_col3:
                    if st.button(
                        "📊 実データ由来デモを読み込む（2025FY）",
                        key="dm_load_from_actual",
                        help="actual_admissions_2025fy.csv をベースに生成した教育用デモ（実データの入院日・病棟・経路を保持し、退院日・医師・短手3 を補完合成）をロードします。data/demo_from_actual_2025fy/ に CSV が生成されていない場合は自動生成します。",
                    ):
                        try:
                            from pathlib import Path as _Path
                            _actual_demo_dir = _Path(__file__).resolve().parent.parent / "data" / "demo_from_actual_2025fy"
                            _actual_demo_csv = _actual_demo_dir / "sample_actual_data_ward.csv"
                            # CSV がなければ生成
                            if not _actual_demo_csv.exists():
                                from generate_demo_from_actual import (
                                    generate_demo_from_actual,
                                    write_csvs,
                                )
                                _data = generate_demo_from_actual(seed=42)
                                write_csvs(_data, _actual_demo_dir)
                            _actual_daily = pd.read_csv(_actual_demo_csv, encoding="utf-8-sig")
                            _actual_daily["date"] = pd.to_datetime(_actual_daily["date"])
                            if "num_beds" not in _actual_daily.columns:
                                _actual_daily["num_beds"] = _actual_daily["ward"].map(lambda w: get_ward_beds(w))
                            if "occupancy_rate" not in _actual_daily.columns:
                                _actual_daily["occupancy_rate"] = (
                                    (_actual_daily["total_patients"] + _actual_daily["discharges"])
                                    / _actual_daily["num_beds"] * 100
                                ).round(1)
                            st.session_state.demo_data = _actual_daily.sort_values(["date", "ward"]).reset_index(drop=True)
                            _bc_alert(
                                f"実データ由来デモ（2025FY 365日分 = {len(_actual_daily)}レコード）を読み込みました。"
                                "実データの入院イベント（5F 951件 / 6F 996件）をベースに、退院日・担当医・短手3（13.5%）・Day 6+ 延長（~5%）を合成しています。",
                                severity="success",
                            )
                            _auto_save_to_db()
                            st.rerun()
                        except ImportError as _e:
                            _bc_alert(
                                f"実データ由来デモ生成モジュールが読み込めません: {_e}",
                                severity="danger",
                            )
                        except FileNotFoundError as _e:
                            _bc_alert(
                                f"実データ CSV が見つかりません: {_e}",
                                severity="danger",
                            )
                        except Exception as _e:  # noqa: BLE001
                            _bc_alert(f"実データ由来デモのロードに失敗しました: {_e}", severity="danger")

                with dm_demo_col4:
                    if st.button("🔄 ランダムデータで再生成（30日分）", key="dm_gen_sample",
                                 help="教育用デモの代わりにランダムなダミーデータを生成します"):
                        _demo_5f = generate_sample_data(num_days=30, num_beds=get_ward_beds("5F"))
                        _demo_5f["ward"] = "5F"
                        _demo_6f = generate_sample_data(num_days=30, num_beds=get_ward_beds("6F"))
                        _demo_6f["ward"] = "6F"
                        st.session_state.demo_data = pd.concat([_demo_5f, _demo_6f], ignore_index=True).sort_values(["date", "ward"]).reset_index(drop=True)
                        _bc_alert("ランダムサンプルデータ（30日分）を生成しました。", severity="success")
                        _auto_save_to_db()
                        st.rerun()

                with dm_demo_col5:
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
                        _bc_alert("データなし", severity="info")

                st.markdown("---")

                # --- デモデータ一覧（閲覧のみ） ---
                _bc_section_title("デモデータ一覧（閲覧専用）", icon="📄")
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
                        use_container_width=True,
                        height=min(400, 50 + len(_demo_display) * 35),
                        hide_index=True,
                    )
                    st.caption(f"合計 {len(st.session_state.demo_data)} 件のデモレコード")
                else:
                    _bc_alert(
                        "デモデータがありません。「サンプルデータ生成」ボタンを押してください。",
                        severity="info",
                    )

            else:
                # ============================================================
                # 実データ入力モード
                # ============================================================

                # --- データ管理セクション ---
                _bc_section_title("データ管理", icon="🗂")
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
                            _bc_alert(f"インポート警告: {import_error}", severity="warning")
                        if len(imported_df) > 0:
                            st.session_state.daily_data = imported_df
                            _bc_alert(
                                f"{len(imported_df)}件のデータをインポートしました。",
                                severity="success",
                            )
                            _auto_save_to_db()
                        elif not import_error:
                            _bc_alert("CSVにデータがありません。", severity="info")

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
                        _bc_alert("データなし", severity="info")

                # --- 運用開始時：過去月サマリー入力 ---
                with st.expander("📋 過去月サマリー入力（運用開始時）", expanded=False):
                    st.caption("運用開始時に先月・先々月のデータを入力すると、初日から3ヶ月rolling平均を計算できます。")

                    _summary_months = []
                    _today = date.today()
                    for _i in range(1, 3):
                        _y = _today.year
                        _m = _today.month - _i
                        while _m <= 0:
                            _m += 12
                            _y -= 1
                        _summary_months.append(f"{_y:04d}-{_m:02d}")

                    _summary_data = st.session_state.monthly_summary.copy()

                    for _sm in _summary_months:
                        st.markdown(f"**{_sm}**")
                        for _ward in ["5F", "6F"]:
                            _key_prefix = f"summary_{_sm}_{_ward}"
                            _existing = _summary_data.get(_sm, {}).get(_ward, {})

                            _cols = st.columns(4)
                            with _cols[0]:
                                _s_adm = st.number_input(
                                    f"{_ward} 入院件数", min_value=0, value=int(_existing.get("admissions", 0)),
                                    key=f"{_key_prefix}_adm", label_visibility="visible"
                                )
                            with _cols[1]:
                                _s_dis = st.number_input(
                                    f"{_ward} 退院件数", min_value=0, value=int(_existing.get("discharges", 0)),
                                    key=f"{_key_prefix}_dis", label_visibility="visible"
                                )
                            with _cols[2]:
                                _s_emg = st.number_input(
                                    f"{_ward} 救急+下り搬送", min_value=0, value=int(_existing.get("emergency", 0)),
                                    key=f"{_key_prefix}_emg", label_visibility="visible"
                                )
                            with _cols[3]:
                                _s_pd = st.number_input(
                                    f"{_ward} 在院延日数", min_value=0, value=int(_existing.get("patient_days", 0)),
                                    key=f"{_key_prefix}_pd", label_visibility="visible"
                                )

                            if _sm not in _summary_data:
                                _summary_data[_sm] = {}
                            _summary_data[_sm][_ward] = {
                                "admissions": _s_adm,
                                "discharges": _s_dis,
                                "emergency": _s_emg,
                                "patient_days": _s_pd,
                            }

                    if st.button("サマリーデータを保存", key="save_monthly_summary"):
                        st.session_state.monthly_summary = _summary_data
                        _bc_alert("過去月サマリーデータを保存しました。", severity="success")

                # --- 全データクリア ---
                if len(st.session_state.daily_data) > 0:
                    with st.expander("⚠️ 全データ消去", expanded=False):
                        _bc_alert(
                            f"現在 {len(st.session_state.daily_data)} 件のデータがあります。この操作は取り消せません。",
                            severity="warning",
                        )
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
                            _bc_alert("全データを消去しました。", severity="success")
                            st.rerun()

                st.markdown("---")

                # --- データ入力フォーム ---
                _bc_section_title("1日分を登録", icon="📝")
                st.caption("入院・退院を1日分まとめて登録します。医師別の詳細も同時に記録されます。")

                # 初回セットアップ: データがない場合、ベッドマップから初期値を設定
                _has_data = len(st.session_state.daily_data) > 0
                _abc_is_zero = (st.session_state.abc_state["A"] == 0
                                and st.session_state.abc_state["B"] == 0
                                and st.session_state.abc_state["C"] == 0)

                if not _has_data and _abc_is_zero:
                    _bc_alert(
                        "⚡ 初回セットアップ：病棟ベッドマップで各患者の在院日数を入力してください（初回のみ）",
                        severity="info",
                    )

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

                            _bc_alert(
                                f"初期値を設定しました。5F: A{a_5f}/B{b_5f}/C{c_5f} | 6F: A{a_6f}/B{b_6f}/C{c_6f} | 合計: {total_a + total_b + total_c}名",
                                severity="success",
                            )
                            _auto_save_to_db()
                            st.rerun()
                        elif confirmed_5f or confirmed_6f:
                            _bc_alert("両方の病棟を確定してください。", severity="warning")
                    else:
                        _bc_alert("ベッドマップUIが利用できません。", severity="warning")
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

                # ============================================================
                # 統合入力フォーム v3: 日次集計 + 医師別詳細 を1回で入力
                # ============================================================
                # 以前は「新しいデータを追加」と「入退院詳細（医師別）」が別々で
                # 二度手間になっていたため、1つのフォームに統合。
                # 送信時に daily_data と admission_details の両方に書き込む。
                st.caption("🆕 入力UI v3 (統合版: 日次集計＋医師別詳細を1回で登録)")

                # 送信後リセット用フラグ: ウィジェット生成前に session_state を初期化
                if st.session_state.get("_dm_reset_inputs", False):
                    for _k in [
                        "dm_discharge_count", "dm_admission_count",
                        "dm_total_patients", "dm_notes",
                    ]:
                        st.session_state.pop(_k, None)
                    for _i in range(8):
                        # 退院スロット
                        st.session_state.pop(f"dm_los_slot_slide_{_i}", None)
                        st.session_state.pop(f"dm_los_slot_input_{_i}", None)
                        st.session_state.pop(f"dm_los_manual_{_i}", None)
                        st.session_state.pop(f"dm_dis_attending_{_i}", None)
                        # 入院スロット
                        st.session_state.pop(f"dm_adm_route_{_i}", None)
                        st.session_state.pop(f"dm_adm_source_{_i}", None)
                        st.session_state.pop(f"dm_adm_attending_{_i}", None)
                        st.session_state.pop(f"dm_adm_short3_{_i}", None)  # 旧キー（後方互換）
                        st.session_state.pop(f"dm_adm_short3_type_{_i}", None)
                    st.session_state["_dm_reset_inputs"] = False

                # 医師・経路マスター読込
                _active_doctors_ui = dm_doctor.get_active_doctors() if _DOCTOR_MASTER_AVAILABLE else []
                _doctor_names_ui = [d["name"] for d in _active_doctors_ui]
                _routes_ui = dm_doctor.get_admission_routes() if _DOCTOR_MASTER_AVAILABLE else ["外来紹介", "救急", "下り搬送", "連携室", "ウォークイン"]
                _source_options_ui = dm_doctor.get_admission_source_options() if _DOCTOR_MASTER_AVAILABLE else {}
                _flat_source_list = ["（なし）"]
                for _g_label, _names in _source_options_ui.items():
                    _flat_source_list.extend(_names)

                with st.container(border=True):
                    st.caption("🗓 共通項目（病棟・日付・在院患者総数）")
                    form_col0, form_col1, form_col2 = st.columns(3)
                    with form_col0:
                        input_ward = st.selectbox("病棟", ["5F", "6F"], key="input_ward_select")
                    with form_col1:
                        input_date = st.date_input("日付", value=pd.Timestamp.now().normalize(), key="dm_date")
                    with form_col2:
                        _ward_max_beds = 47
                        input_total = st.number_input(
                            "在院患者総数", min_value=0, max_value=_ward_max_beds,
                            value=40, step=1, key="dm_total_patients",
                        )

                # --- 入院情報セクション ---
                with st.container(border=True):
                    _bc_section_title("入院登録", icon="🏥")
                    input_admissions = st.number_input(
                        "新規入院数（入院なしは0）",
                        min_value=0, max_value=8, value=0, step=1,
                        key="dm_admission_count",
                        help="本日の新規入院数を入力。下に入院人数分のスロットが展開されます。",
                    )

                    _adm_events = []  # [(route, source, attending, short3_type), ...]
                    # 短手3 種類の選択肢（該当なしを先頭）
                    _short3_type_options = [
                        SHORT3_TYPE_NONE,
                        SHORT3_TYPE_POLYP_S,
                        SHORT3_TYPE_POLYP_L,
                        SHORT3_TYPE_INGUINAL,
                        SHORT3_TYPE_PSG,
                        SHORT3_TYPE_OTHER,
                    ]
                    if input_admissions > 0:
                        st.caption(f"💡 {int(input_admissions)}名分の入院詳細を入力してください（経路・担当医は必須）")
                    for _a_slot_row in range(0, 8, 2):
                        _a_slot_cols = st.columns(2)
                        for _aci, _a_col in enumerate(_a_slot_cols):
                            _asi = _a_slot_row + _aci
                            if _asi >= input_admissions:
                                continue
                            with _a_col:
                                with st.container(border=True):
                                    st.caption(f"✏️ 入院{_asi + 1}")
                                    _a_route = st.selectbox(
                                        "経路（必須）",
                                        _routes_ui,
                                        key=f"dm_adm_route_{_asi}",
                                    )
                                    _a_attending = st.selectbox(
                                        "入院担当医（必須）",
                                        [""] + _doctor_names_ui,
                                        key=f"dm_adm_attending_{_asi}",
                                    )
                                    with st.expander("詳細（任意）", expanded=False):
                                        _a_source = st.selectbox(
                                            "入院創出医",
                                            _flat_source_list,
                                            key=f"dm_adm_source_{_asi}",
                                        )
                                        _a_short3_type = st.selectbox(
                                            "🏃 短手3 種類",
                                            _short3_type_options,
                                            key=f"dm_adm_short3_type_{_asi}",
                                            help="短期滞在手術等基本料3（4泊5日以内）の算定対象。該当する場合は種類を選択。計算は種類別の包括点数で行われます。",
                                        )
                                    _adm_events.append((_a_route, _a_source, _a_attending, _a_short3_type))

                    # 短手3 内数を集計（「該当なし」以外を1件とカウント）
                    input_admissions_short3 = sum(
                        1 for ev in _adm_events if ev[3] and ev[3] != SHORT3_TYPE_NONE
                    )

                    # --- 短手3 → 通常入院 切替（高度オプション: 折りたたみ） ---
                    with st.expander("短手3 → 通常入院 切替（該当がある場合のみ）", expanded=False):
                        input_short3_overflow = st.number_input(
                            "短手3→通常切替（6日以上入院継続）",
                            min_value=0, max_value=10, value=0, step=1,
                            help="短手3患者が6日目以降も入院継続した場合の切替患者数",
                            key="input_short3_overflow",
                        )
                        input_short3_overflow_los = None
                        if input_short3_overflow > 0:
                            input_short3_overflow_los = st.number_input(
                                "切替患者の入院初日からの在院日数",
                                min_value=6, max_value=90, value=6, step=1,
                                help="入院料: Tier3 ¥31,170/日（予定入院+手術あり）",
                                key="input_short3_overflow_los",
                            )

                # --- 退院情報セクション ---
                with st.container(border=True):
                    _bc_section_title("退院登録", icon="🚪")
                    st.caption("🟢 A群: 1-5日 ／ 🟡 B群: 6-14日 ／ 🔴 C群: 15日以上")
                    input_discharge_count = st.number_input(
                        "退院人数（退院なしは0）",
                        min_value=0, max_value=8, value=0, step=1,
                        key="dm_discharge_count",
                        help="本日の退院患者数を入力。下に退院人数分のスロットが展開されます。",
                    )

                    # 在院日数スライダー（通常1-90日、90日超は数値入力）
                    _los_options = list(range(1, 91))
                    if input_discharge_count > 0:
                        st.caption(f"💡 {int(input_discharge_count)}名分の退院詳細を入力してください（在院日数・担当医）")
                    _los_all = []
                    _dis_attendings = []
                    for _slot_row in range(0, 8, 2):
                        _slot_cols = st.columns(2)
                        for _ci, _col in enumerate(_slot_cols):
                            _si = _slot_row + _ci
                            if _si >= input_discharge_count:
                                continue
                            with _col:
                                with st.container(border=True):
                                    st.caption(f"✏️ 退院{_si + 1}")
                                    _manual_key = f"dm_los_manual_{_si}"
                                    _is_manual = st.checkbox(
                                        "📝 90日超（数値入力）",
                                        key=_manual_key,
                                        help="91日以上の長期入院患者の場合にチェック。",
                                    )
                                    if _is_manual:
                                        _los_val = st.number_input(
                                            "在院日数",
                                            min_value=1, max_value=365, value=91, step=1,
                                            key=f"dm_los_slot_input_{_si}",
                                        )
                                    else:
                                        _los_val = st.select_slider(
                                            "在院日数",
                                            options=_los_options,
                                            value=10,
                                            key=f"dm_los_slot_slide_{_si}",
                                        )
                                    _d_attending = st.selectbox(
                                        "担当医（必須）",
                                        [""] + _doctor_names_ui,
                                        key=f"dm_dis_attending_{_si}",
                                    )
                                    _los_all.append(_los_val)
                                    _dis_attendings.append(_d_attending)

                # 退院人数分だけ有効値として集計
                auto_discharges = int(input_discharge_count)
                _los_active = _los_all[:auto_discharges]
                _auto_da = sum(1 for x in _los_active if 1 <= x <= 5)
                _auto_db = sum(1 for x in _los_active if 6 <= x <= 14)
                _auto_dc = sum(1 for x in _los_active if x >= 15)

                # --- サマリー情報ボックス ---
                _summary_parts = []
                if input_admissions > 0:
                    # 短手3 種類別の内訳と収入見込みを計算
                    _s3_revenue_total = 0
                    _s3_type_counts = {}
                    for (_r, _s, _att, _s3t) in _adm_events:
                        if _s3t and _s3t != SHORT3_TYPE_NONE:
                            _s3_type_counts[_s3t] = _s3_type_counts.get(_s3t, 0) + 1
                            _s3_revenue_total += _short3_revenue_map.get(_s3t, 0)
                    if input_admissions_short3 > 0:
                        _s3_breakdown = " / ".join(f"{_t}:{_c}" for _t, _c in _s3_type_counts.items())
                        _s3_txt = f"（うち短手3: {input_admissions_short3}名 [{_s3_breakdown}] 包括収入見込 ¥{_s3_revenue_total:,}）"
                    else:
                        _s3_txt = ""
                    _summary_parts.append(f"入院 **{int(input_admissions)}名**{_s3_txt}")
                if auto_discharges > 0:
                    _avg_los_display = sum(_los_active) / len(_los_active)
                    _phase_badges = " ".join(
                        f"{'🟢' if v <= 5 else '🟡' if v <= 14 else '🔴'}{v}日" for v in _los_active
                    )
                    _summary_parts.append(
                        f"退院 **{auto_discharges}名**: {_phase_badges}"
                        f"（A:{_auto_da} B:{_auto_db} C:{_auto_dc}　平均LOS（在院日数）: **{_avg_los_display:.1f}日**）"
                    )
                if _summary_parts:
                    _bc_alert("💡 " + "<br><br>".join(_summary_parts), severity="info")
                else:
                    _bc_alert(
                        "💡 入院・退院なし（上で人数を設定するとスロットが展開されます）",
                        severity="info",
                    )

                input_notes = st.text_input("備考（任意）", value="", key="dm_notes")

                submitted = st.button("1日分を登録", type="primary", use_container_width=True, key="dm_add_btn")

                if submitted:
                    # --- バリデーション: 全入院・全退院の担当医が入力されているか ---
                    _validation_errors = []
                    for _a_i, (_r, _s, _att, _s3) in enumerate(_adm_events):
                        if not _att:
                            _validation_errors.append(f"入院{_a_i + 1}: 担当医を選択してください")
                    for _d_i, _d_att in enumerate(_dis_attendings):
                        if not _d_att:
                            _validation_errors.append(f"退院{_d_i + 1}: 担当医を選択してください")

                    if _validation_errors:
                        _bc_alert(
                            "⚠️ 入力を確認してください:<br>" + "<br>".join(_validation_errors),
                            severity="danger",
                        )
                        st.stop()

                    # 在院日数リストからA/B/C退院数を算出
                    _active_los = list(_los_active)
                    _los_str = ",".join(str(v) for v in _active_los)
                    _, input_discharge_a, input_discharge_b, input_discharge_c, _calc_avg_los = parse_discharge_los_list(_los_str)
                    import math
                    _avg_los_val = _calc_avg_los if not math.isnan(_calc_avg_los) else pd.NA

                    # A/B/C群を自動計算（日齢バケットモデル対応）
                    _prev_buckets = st.session_state.get("day_buckets", None)

                    new_abc, new_buckets = calculate_abc_groups(
                        st.session_state.abc_state,
                        int(input_admissions),
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
                        "new_admissions_short3": int(input_admissions_short3),
                        "short3_overflow_count": int(input_short3_overflow),
                        "short3_overflow_avg_los": float(input_short3_overflow_los) if input_short3_overflow_los is not None else pd.NA,
                        "discharges": int(auto_discharges),
                        "discharge_a": int(input_discharge_a),
                        "discharge_b": int(input_discharge_b),
                        "discharge_c": int(input_discharge_c),
                        "discharge_los_list": _los_str,
                        "phase_a_count": new_a,
                        "phase_b_count": new_b,
                        "phase_c_count": new_c,
                        "avg_los": _avg_los_val,
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

                        # --- 詳細データ (admission_details) にも同時書き込み ---
                        # 統合フォームの核心: daily_data と admission_details を1回の操作で書く
                        _detail_written_count = 0
                        if _DETAIL_DATA_AVAILABLE:
                            try:
                                _details_df = st.session_state.admission_details
                                _date_str = str(input_date)
                                # 入院イベント（短手3 種類も記録 - Phase 3）
                                for (_r, _s, _att, _s3t) in _adm_events:
                                    _source_name = _s if _s and _s != "（なし）" else ""
                                    # 短手3 種類: "該当なし" なら None として渡す
                                    _s3_type_to_store = _s3t if _s3t and _s3t != SHORT3_TYPE_NONE else None
                                    _details_df = add_admission_event(
                                        _details_df, _date_str, input_ward,
                                        _r, _source_name, _att,
                                        short3_type=_s3_type_to_store,
                                    )
                                    _detail_written_count += 1
                                # 退院イベント
                                for _los_v, _d_att in zip(_active_los, _dis_attendings):
                                    _details_df = add_discharge_event(
                                        _details_df, _date_str, input_ward,
                                        _d_att, int(_los_v),
                                    )
                                    _detail_written_count += 1
                                st.session_state.admission_details = _details_df
                                save_details(_details_df)
                            except Exception as _detail_err:
                                st.warning(f"⚠️ 詳細データの保存で警告: {_detail_err}")

                        _phase_detail = " ".join(
                            f"{'🟢' if v <= 5 else '🟡' if v <= 14 else '🔴'}{v}日" for v in _active_los
                        ) if _active_los else "なし"
                        _detail_note = f" / 医師別詳細 {_detail_written_count}件記録" if _detail_written_count > 0 else ""
                        _bc_alert(
                            f"{input_date} ({input_ward}) の 1日分を登録しました。"
                            f"（退院:{_phase_detail} / A群:{new_a} B群:{new_b} C群:{new_c}{_detail_note}）",
                            severity="success",
                        )
                        _auto_save_to_db()
                        # 次回再描画時に全入力フィールドを初期化する
                        st.session_state["_dm_reset_inputs"] = True
                        st.rerun()
                    else:
                        _bc_alert(f"入力エラー: {error_msg}", severity="danger")

                st.markdown("---")

                # --- データ一覧・編集 ---
                _bc_section_title("本日の記録一覧", icon="📊")
                if len(st.session_state.daily_data) > 0:
                    display_data = st.session_state.daily_data.copy()
                    display_data["date"] = pd.to_datetime(display_data["date"])
                    display_data = display_data.sort_values("date", ascending=False).reset_index(drop=True)

                    # 表示用にフォーマット
                    display_data["date_str"] = display_data["date"].dt.strftime("%Y-%m-%d")

                    # st.data_editor で編集可能テーブル（data_sourceカラムは非表示）
                    # ward 列を先頭付近に表示して、同一日付の 5F/6F を区別しやすくする
                    _display_cols = ["date_str", "ward", "total_patients", "new_admissions",
                                      "new_admissions_short3",
                                      "short3_overflow_count",
                                      "discharges",
                                      "discharge_los_list",
                                      "discharge_a", "discharge_b", "discharge_c",
                                      "phase_a_count", "phase_b_count", "phase_c_count",
                                      "avg_los", "notes"]
                    _display_cols_available = [c for c in _display_cols if c in display_data.columns]
                    edited_df = st.data_editor(
                        display_data[_display_cols_available].rename(columns={
                            "date_str": "日付",
                            "ward": "病棟",
                            "total_patients": "在院患者数",
                            "new_admissions": "新規入院",
                            "new_admissions_short3": "うち短手3",
                            "short3_overflow_count": "短手3切替",
                            "discharges": "退院（自動）",
                            "discharge_los_list": "退院LOS（在院日数）一覧",
                            "discharge_a": "A群退院",
                            "discharge_b": "B群退院",
                            "discharge_c": "C群退院",
                            "phase_a_count": "A群（自動）",
                            "phase_b_count": "B群（自動）",
                            "phase_c_count": "C群（自動）",
                            "avg_los": "退院平均LOS",
                            "notes": "備考",
                        }),
                        column_config={
                            "日付": st.column_config.TextColumn(disabled=True),
                            "病棟": st.column_config.TextColumn(disabled=True),
                            "うち短手3": st.column_config.NumberColumn(help="短期滞在手術等基本料3の内数（Phase 1: 記録のみ）"),
                            "退院（自動）": st.column_config.NumberColumn(disabled=True),
                            "退院LOS一覧": st.column_config.TextColumn(disabled=True, help="退院患者の在院日数（カンマ区切り）"),
                            "A群退院": st.column_config.NumberColumn(disabled=True),
                            "B群退院": st.column_config.NumberColumn(disabled=True),
                            "C群退院": st.column_config.NumberColumn(disabled=True),
                            "A群（自動）": st.column_config.NumberColumn(disabled=True),
                            "B群（自動）": st.column_config.NumberColumn(disabled=True),
                            "C群（自動）": st.column_config.NumberColumn(disabled=True),
                            "退院平均LOS": st.column_config.NumberColumn(disabled=True, format="%.1f"),
                        },
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
                                _bc_alert(
                                    "変更を保存しました。A/B/C群と退院数を再計算しました。",
                                    severity="success",
                                )
                                _auto_save_to_db()
                                st.rerun()
                            except Exception as e:
                                _bc_alert(f"保存エラー: {e}", severity="danger")

                    with edit_col2:
                        # 削除用：日付 + 病棟 を選択（同一日付の5F/6Fを区別するため）
                        _del_options = [
                            (f"{row['date_str']} ({row.get('ward', 'all')})",
                             row['date_str'],
                             row.get('ward', None))
                            for _, row in display_data.iterrows()
                        ]
                        if _del_options:
                            _del_labels = [opt[0] for opt in _del_options]
                            del_label = st.selectbox("削除する日付・病棟", _del_labels, key="dm_del_date")
                            if st.button("選択した行を削除", key="dm_delete_btn"):
                                # 選択ラベルから date と ward を復元
                                _idx = _del_labels.index(del_label)
                                _del_date_str = _del_options[_idx][1]
                                _del_ward = _del_options[_idx][2]
                                st.session_state.daily_data = delete_record(
                                    st.session_state.daily_data, _del_date_str, ward=_del_ward,
                                )
                                _bc_alert(f"{del_label} のデータを削除しました。", severity="success")
                                _auto_save_to_db()
                                st.rerun()

                    st.caption(f"合計 {len(st.session_state.daily_data)} 件のレコード")
                else:
                    _bc_alert(
                        "まずデータを入力してください。操作方法がわからない場合は"
                        "「🎮 デモモード（サンプルデータ）」でお試しください。",
                        severity="warning",
                    )

            # === 入退院詳細 表示のみ（入力は統合フォームに一本化） ===
            # 旧「入退院詳細（医師別）」の入力セクションは統合フォームに移行済み。
            # ここでは記録された直近のイベント一覧のみ表示する。
            if _DOCTOR_MASTER_AVAILABLE and _DETAIL_DATA_AVAILABLE:
                if len(st.session_state.admission_details) > 0:
                    st.markdown("---")
                    _bc_section_title("入退院詳細（医師別）— 直近の記録", icon="👩‍⚕️")
                    st.caption("入力は上の「1日分を登録」フォームで行います。医師別情報は1回の登録でまとめて記録されます。")
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
            fig_occ, ax_occ = plt.subplots(figsize=(12, 3))
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
            fig_ad, ax_ad = plt.subplots(figsize=(12, 3))
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
            fig_phase, ax_phase = plt.subplots(figsize=(12, 3))
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
                fig_pred, ax_pred = plt.subplots(figsize=(12, 3))

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

                st.caption(f"残り{_monthly_kpi['残り日数']}日 | 受入見込み数: {_monthly_kpi['今月入院数_予測']}名")
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
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("週次サマリーを生成するにはデータが不足しています。")

# =====================================================================
# シミュレーション結果タブ / 実績データタブ
# =====================================================================
# データが必要なセクション（今日の運営・What-if・戦略・退院調整）かどうか
# 2026-04-21 副院長決定: 退院調整セクションも sim/実績データなしでは
# 実値に見えるサンプル表示が誤解を招くためガード対象に含める。
# カンファ資料はビュー単独起動 (run_conference_view.py) でのみサンプル表示。
_needs_sim_data = _selected_section in ["📊 今日の運営", "🔮 What-if・戦略", "🏥 退院調整"]
# データ準備完了フラグ（st.stop()の代わりに各タブでガードに使用）
_data_ready = False

if _is_actual_data_mode:
    # 実績データモード
    if not _actual_data_available:
        if _needs_sim_data:
            _no_data_msg = "実績データがありません。「📋 日次データ入力」タブでデータを入力するか、デモデータを生成してください。"
            for _t in tabs:
                with _t:
                    st.info(_no_data_msg)
        # データ不要セクション or データ未入力 → ダミー値で続行（st.stop()を使わず他タブへの影響を防ぐ）
        df = pd.DataFrame()
        summary = {}
        days_in_month = 30
        _active_raw_df = pd.DataFrame()
        _active_cli_params = {}
    else:
        _data_ready = True
        df = st.session_state.actual_df
        summary = st.session_state.actual_summary
        _active_raw_df = st.session_state.actual_df_raw
        _active_cli_params = dict(st.session_state.actual_params)  # コピーして病棟別に上書き可能にする
        if _selected_ward_key in ("5F", "6F"):
            _active_cli_params["num_beds"] = get_ward_beds(_selected_ward_key)
            # 月間入院数も病棟の病床比率で按分（全体150名→各病棟75名）
            _bed_ratio = get_ward_beds(_selected_ward_key) / _TOTAL_BEDS_METRIC
            _active_cli_params["monthly_admissions"] = int(
                _active_cli_params.get("monthly_admissions", 150) * _bed_ratio
            )
        # 実データモードでは days_in_month をデータ日数に合わせる
        days_in_month = len(df)
        # カレンダー上の月日数（目標計算用）
        _data_month_ref = df["日付"].iloc[-1] if "日付" in df.columns else (df["date"].iloc[-1] if "date" in df.columns else pd.Timestamp.now())
        if isinstance(_data_month_ref, str):
            _data_month_ref = pd.to_datetime(_data_month_ref)
        _calendar_month_days = calendar.monthrange(_data_month_ref.year, _data_month_ref.month)[1]
else:
    # シミュレーションモード
    if not _simulation_available:
        if _needs_sim_data:
            _no_data_msg = "サイドバーのパラメータを設定し「シミュレーション実行」ボタンを押してください。"
            for _t in tabs:
                with _t:
                    st.info(_no_data_msg)
        # データ不要セクション or シミュレーション未実行 → ダミー値で続行（st.stop()を使わず他タブへの影響を防ぐ）
        df = pd.DataFrame()
        summary = {}
        days_in_month = 30
        _active_raw_df = pd.DataFrame()
        _active_cli_params = {}
    elif _selected_ward_key in ("5F", "6F") and st.session_state.sim_ward_dfs.get(_selected_ward_key) is not None:
        _data_ready = True
        df = st.session_state.sim_ward_dfs[_selected_ward_key]
        summary = st.session_state.sim_ward_summaries[_selected_ward_key]
        _active_raw_df = st.session_state.sim_ward_raw_dfs[_selected_ward_key]
        _active_raw_df_full = st.session_state.get("sim_ward_raw_dfs_full", {}).get(_selected_ward_key, _active_raw_df)
        _active_cli_params = st.session_state.sim_params.copy()
        _active_cli_params["num_beds"] = get_ward_beds(_selected_ward_key)
        _bed_ratio_sim = get_ward_beds(_selected_ward_key) / _TOTAL_BEDS_METRIC
        _active_cli_params["monthly_admissions"] = int(
            _active_cli_params.get("monthly_admissions", 150) * _bed_ratio_sim
        )
        _view_beds = get_ward_beds(_selected_ward_key)
    else:
        _data_ready = True
        df = st.session_state.sim_df
        summary = st.session_state.sim_summary
        _active_raw_df = st.session_state.sim_df_raw
        _active_raw_df_full = st.session_state.get("sim_df_raw_full", _active_raw_df)
        _active_cli_params = st.session_state.sim_params.copy()
        # Ward selected but ward data not available - need to re-run simulation
        if _selected_ward_key in ("5F", "6F"):
            _active_cli_params["num_beds"] = get_ward_beds(_selected_ward_key)
            _bed_ratio_fallback = get_ward_beds(_selected_ward_key) / _TOTAL_BEDS_METRIC
            _active_cli_params["monthly_admissions"] = int(
                _active_cli_params.get("monthly_admissions", 150) * _bed_ratio_fallback
            )
            _view_beds = get_ward_beds(_selected_ward_key)

# カレンダー月日数のフォールバック
if '_calendar_month_days' not in locals():
    # シミュレーションモード: サイドバーのカレンダー月日数を使用
    _calendar_month_days = _sidebar_calendar_days if '_sidebar_calendar_days' in dir() else days_in_month

# ---------------------------------------------------------------------------
# _active_raw_df と _active_display_df のフォールバック設定
# ---------------------------------------------------------------------------
if '_active_raw_df' not in locals():
    _active_raw_df = pd.DataFrame()
if '_active_raw_df_full' not in locals():
    _active_raw_df_full = _active_raw_df
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
    # 病棟別表示では monthly_admissions と num_beds を病床比率で再スケール
    if _selected_ward_key in ("5F", "6F"):
        _active_cli_params["num_beds"] = get_ward_beds(_selected_ward_key)
        _bed_ratio_sync = get_ward_beds(_selected_ward_key) / _TOTAL_BEDS_METRIC
        _active_cli_params["monthly_admissions"] = int(
            _active_cli_params["monthly_admissions"] * _bed_ratio_sync
        )

# ===== タブ1: 日次推移 =====
if "📊 日次推移" in _tab_idx and _data_ready:
    with tabs[_tab_idx["📊 日次推移"]]:
        st.subheader("日次推移")
        if _HELP_AVAILABLE and "tab_daily" in HELP_TEXTS:
            with st.expander("📖 このタブの見方と活用法"):
                st.markdown(HELP_TEXTS["tab_daily"])

        # --- 日次推移タブでもモジュールレベルの共通スタイルを使う（エイリアス） ---
        # `_apply_daily_axes_style` / `_style_daily_legend` は互換のため残すが、
        # 実体はモジュールレベルの `_bc_apply_chart_style` / `_bc_style_legend` を参照する。
        _apply_daily_axes_style = _bc_apply_chart_style
        _style_daily_legend = _bc_style_legend

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
            """土日を極薄グレー背景で強調するヘルパー（新デザイン）."""
            for _wd in weekend_list:
                ax_obj.axvspan(_wd - 0.5, _wd + 0.5, alpha=0.06, color=_DT_TEXT_MUTED)

        def _set_weekday_ticks(ax_obj, day_series, weekday_list):
            """曜日ラベル付き目盛りを設定するヘルパー"""
            _tpos = list(day_series)
            _tlbl = [f"{d}\n{_weekday_names[weekday_list[i]]}" for i, d in enumerate(_tpos)]
            if len(_tpos) > 15:
                _step = max(1, len(_tpos) // 15)
                _show = list(range(0, len(_tpos), _step))
                ax_obj.set_xticks([_tpos[j] for j in _show])
                ax_obj.set_xticklabels([_tlbl[j] for j in _show], fontsize=9, color=_DT_TEXT_SECONDARY)
            else:
                ax_obj.set_xticks(_tpos)
                ax_obj.set_xticklabels(_tlbl, fontsize=9, color=_DT_TEXT_SECONDARY)

        # --- 今日の指標サマリー（KPIカード3列） ---
        # 本日値 = データ最終日、月平均 = これまでの平均
        try:
            _today_occ_pct = float(df["稼働率"].iloc[-1]) * 100
            _avg_occ_pct_kpi = float(df["稼働率"].mean()) * 100
            _delta_occ = _today_occ_pct - _avg_occ_pct_kpi

            _today_patients = float(df["在院患者数"].iloc[-1])
            _avg_patients = float(df["在院患者数"].mean())
            _delta_patients = _today_patients - _avg_patients

            # ALOS: summary から月平均・rolling があれば本日の参考値として使う
            _today_los = None
            _avg_los = None
            if isinstance(summary, dict):
                # summary に "rolling_los" or "平均在院日数" が入っているパターンをカバー
                for _k in ("平均在院日数", "rolling_los", "avg_los"):
                    if _k in summary and summary[_k] is not None:
                        _avg_los = float(summary[_k])
                        break
            # df 内に在院日数列があれば最終日値を本日値として使用（無ければ avg と同値）
            if "平均在院日数" in df.columns:
                try:
                    _today_los = float(df["平均在院日数"].iloc[-1])
                except Exception:
                    _today_los = None
            if _today_los is None:
                _today_los = _avg_los

            _bc_section_title("今日の指標サマリー", icon="📊")
            _kpi_col1, _kpi_col2, _kpi_col3 = st.columns(3)
            with _kpi_col1:
                _sev = "success" if _today_occ_pct >= target_lower * 100 else ("warning" if _today_occ_pct >= (target_lower * 100 - 3) else "danger")
                _delta_str = f"月平均比 {_delta_occ:+.1f} pt（月平均 {_avg_occ_pct_kpi:.1f}%）"
                _bc_kpi_card(
                    label="稼働率（本日）",
                    value=f"{_today_occ_pct:.1f}",
                    unit="%",
                    delta=_delta_str,
                    severity=_sev,
                )
            with _kpi_col2:
                _delta_p_str = f"月平均比 {_delta_patients:+.1f} 名（月平均 {_avg_patients:.1f} 名）"
                _bc_kpi_card(
                    label="在院患者数（本日）",
                    value=f"{_today_patients:.0f}",
                    unit=" 名",
                    delta=_delta_p_str,
                    severity="neutral",
                )
            with _kpi_col3:
                if _today_los is not None and _avg_los is not None:
                    _delta_los = _today_los - _avg_los
                    _bc_kpi_card(
                        label="平均在院日数（直近）",
                        value=f"{_today_los:.1f}",
                        unit=" 日",
                        delta=f"月平均 {_avg_los:.1f} 日",
                        severity="neutral",
                    )
                elif _avg_los is not None:
                    _bc_kpi_card(
                        label="平均在院日数（月平均）",
                        value=f"{_avg_los:.1f}",
                        unit=" 日",
                        severity="neutral",
                    )
                else:
                    _bc_kpi_card(
                        label="平均在院日数",
                        value="—",
                        severity="neutral",
                    )
        except Exception as _kpi_err:
            # KPI サマリーで失敗しても本体グラフは描画する
            import traceback as _kpi_tb
            st.caption(f"（KPI サマリー取得エラー: {type(_kpi_err).__name__}）")

        st.markdown("")  # 空行（セクション間の呼吸）

        # --- 稼働率推移（Hero チャート） ---
        _bc_section_title("稼働率の推移", icon="📊")
        fig, ax = plt.subplots(figsize=(12, 3.2))
        fig.patch.set_alpha(0.0)
        _add_weekend_bg(ax, _weekend_days)
        ax.plot(
            df["日"], df["稼働率"] * 100,
            color=_DT_ACCENT, linewidth=_DT_LW_PRIMARY, label="稼働率",
            zorder=3,
        )
        ax.axhspan(
            target_lower * 100, target_upper * 100,
            alpha=0.10, color=_DT_WARNING,
            label=f"目標レンジ ({target_lower*100:.0f}-{target_upper*100:.0f}%)",
            zorder=1,
        )
        ax.set_xlabel("日")
        ax.set_ylabel("稼働率 (%)")
        _set_weekday_ticks(ax, df["日"], _day_weekdays)
        _apply_daily_axes_style(ax)
        _leg = ax.legend(loc="upper left", ncol=2, frameon=False)
        _style_daily_legend(_leg)
        ax.set_xlim(1, days_in_month)

        # --- 月平均ライン（常時表示）---
        _avg_occ_pct = df["稼働率"].mean() * 100
        ax.axhline(
            y=_avg_occ_pct, color=_DT_TEXT_MUTED, linestyle=":",
            linewidth=_DT_LW_AUX, alpha=0.8, zorder=2,
        )
        ax.annotate(
            f'月平均 {_avg_occ_pct:.1f}%',
            xy=(2, _avg_occ_pct),
            fontsize=9, color=_DT_TEXT_SECONDARY, va="bottom",
        )

        # --- 残り日数の目標達成ライン（常時表示）---
        # _calc_monthly_target で計算、失敗時はフォールバックで直接計算
        _mt_chart = None
        for _mt_src_df in [_active_raw_df, df]:
            if _mt_chart is None and isinstance(_mt_src_df, pd.DataFrame) and len(_mt_src_df) > 0:
                _mt_chart = _calc_monthly_target(_mt_src_df, target_lower, _calendar_month_days, _view_beds)

        # フォールバック: _calc_monthly_targetが失敗しても残り日数があれば直接計算
        if _mt_chart is None and _calendar_month_days > days_in_month:
            _fb_avg = _avg_occ_pct
            _fb_elapsed = days_in_month
            _fb_remaining = _calendar_month_days - _fb_elapsed
            _fb_target = target_lower * 100
            _fb_required = (_fb_target * _calendar_month_days - _fb_avg * _fb_elapsed) / _fb_remaining
            _mt_chart = {
                "avg_so_far": round(_fb_avg, 1),
                "days_elapsed": _fb_elapsed,
                "days_remaining": _fb_remaining,
                "total_days": _calendar_month_days,
                "required_occ": round(_fb_required, 1),
                "monthly_target_pct": _fb_target,
                "difficulty": "impossible" if _fb_required > 100 else "hard" if _fb_required > 95 else "moderate" if _fb_required > 90 else "easy",
            }

        if _mt_chart and _mt_chart["days_remaining"] > 0:
            _chart_last_day = len(df["稼働率"])  # データの最終日番号
            _chart_end_day = _mt_chart["total_days"]  # 月末日番号
            _required_occ_pct = _mt_chart["required_occ"]
            _occ_pct_values = (df["稼働率"] * 100).tolist()

            # --- 全体主義計算（均等努力方式）---
            # 病棟別表示時に、単体目標線に加えて均等努力目標線も表示する
            _has_equal_effort = False
            _ee_target = None
            _ee_over_cap = False
            _delta_chart = 0
            if _selected_ward_key in ("5F", "6F"):
                # _get_holistic_ward_dfs() がうまく動かない場合の3段階フォールバック
                _holistic_ward_dfs = _get_holistic_ward_dfs()
                if not _holistic_ward_dfs:
                    _holistic_ward_dfs = globals().get("_ward_raw_dfs", {})
                if _holistic_ward_dfs and "5F" in _holistic_ward_dfs and "6F" in _holistic_ward_dfs:
                    try:
                        _cw_chart = _calc_cross_ward_target(
                            _holistic_ward_dfs, target_lower, _calendar_month_days,
                            get_ward_beds, helper_cap * 100,
                        )
                        if _cw_chart and _cw_chart.get("equal_effort"):
                            _ee_self_chart = _cw_chart["equal_effort"][_selected_ward_key]
                            _delta_chart = _cw_chart.get("delta", 0)
                            # Δ > 0 の場合のみ「均等努力目標」を描画する。
                            # Δ ≤ 0 は「全体ペースが既に目標達成済 = 追加努力不要」を意味するため、
                            # 現状より低い数値を「目標」として表示すると誤解を招く。
                            if _delta_chart > 0:
                                _ee_target = _ee_self_chart["target"]
                                _has_equal_effort = True
                                if not _ee_self_chart["within_cap"]:
                                    _ee_over_cap = True
                    except Exception:
                        pass

            # --- 目標ライン描画（単体目標を常時表示、均等努力目標を併記）---
            # 1. 目標線（赤/オレンジ/緑の破線）を必ず表示
            # 表示病棟に応じてラベル文言を切り替え
            # - 「全体」選択時: 全体目標（94床ベース）
            # - 「5F」「6F」選択時: 単体目標（各病棟ベース）
            _label_scope = "全体目標" if _selected_ward_key == "全体" else "単体目標"
            _target_x = [_chart_last_day, _chart_last_day + 1, _chart_end_day]
            _target_y = [_occ_pct_values[-1], _required_occ_pct, _required_occ_pct]

            if _mt_chart["avg_so_far"] >= _mt_chart["monthly_target_pct"]:
                _target_color = _DT_SUCCESS
                _target_label = f'{_label_scope} 維持\n{_required_occ_pct:.1f}%以上'
            else:
                _target_color = _DT_DANGER if _mt_chart["difficulty"] in ("hard", "impossible") else _DT_WARNING
                _target_label = f'{_label_scope} 必要\n{_required_occ_pct:.1f}%'

            ax.plot(_target_x, _target_y,
                    linestyle="--", linewidth=_DT_LW_TARGET, color=_target_color,
                    marker="", zorder=5, label=f"{_label_scope} {_required_occ_pct:.1f}%")
            ax.annotate(
                _target_label,
                xy=(_chart_end_day - 2, _required_occ_pct),
                fontsize=9, fontweight="bold", color=_target_color,
                ha="right", va="bottom",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=_target_color, alpha=0.9),
            )

            # 2. 均等努力目標線（補助）— 全体主義での目標達成ライン
            if _has_equal_effort and _ee_target is not None:
                _ee_display = min(_ee_target, helper_cap * 100) if _ee_over_cap else _ee_target
                _ee_x = [_chart_last_day, _chart_last_day + 1, _chart_end_day]
                _ee_y = [_occ_pct_values[-1], _ee_display, _ee_display]
                _ee_line_color = _DT_WARNING if _ee_over_cap else _DT_INFO
                ax.plot(_ee_x, _ee_y,
                        linestyle=":", linewidth=_DT_LW_TARGET, color=_ee_line_color,
                        marker="", zorder=4, alpha=0.85,
                        label=f"助け合い {_ee_display:.1f}%")
                if _ee_over_cap:
                    _ee_label = f'助け合い(上限到達)\n{helper_cap*100:.0f}%'
                else:
                    _delta_sign = "+" if _delta_chart >= 0 else ""
                    _ee_label = f'助け合い目標\n{_ee_display:.1f}%（{_delta_sign}{_delta_chart:.1f}pt）'
                # ラベル位置: 単体目標と被らないよう、下側に配置
                _label_va = "top" if _ee_display < _required_occ_pct else "bottom"
                ax.annotate(
                    _ee_label,
                    xy=(_chart_end_day - 6, _ee_display),
                    fontsize=9, fontweight="bold", color=_ee_line_color,
                    ha="right", va=_label_va,
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=_ee_line_color, alpha=0.9),
                )

            # X軸の範囲を月末まで拡張
            ax.set_xlim(1, _chart_end_day + 0.5)

        st.pyplot(fig)
        plt.close(fig)

        # --- 全体主義テーブル（グラフ下に表示） ---
        _htc = st.session_state.get("_holistic_table_content")
        if _htc:
            _htc_type, _htc_body = _htc
            if _htc_type == "info":
                st.info(_htc_body)
            elif _htc_type == "success":
                st.success(_htc_body)
            elif _htc_type == "warning":
                st.warning(_htc_body)
            elif _htc_type == "error":
                st.error(_htc_body)

        # 病棟別稼働率は病棟セレクターで切り替え（比較ストリップで他病棟を表示）

        # --- Secondary チャート（在院患者数・新規入院/退院数）---
        col1, col2 = st.columns(2)
        with col1:
            _bc_section_title("在院患者数の推移", icon="🛏")
            fig, ax = plt.subplots(figsize=(6, 3.2))
            fig.patch.set_alpha(0.0)
            _add_weekend_bg(ax, _weekend_days)
            ax.plot(
                df["日"], df["在院患者数"],
                color=_DT_WARD_6F, linewidth=_DT_LW_PRIMARY, zorder=3,
                label="在院患者数",
            )
            ax.axhline(
                y=_view_beds, color=_DT_DANGER, linestyle="--",
                linewidth=_DT_LW_TARGET, alpha=0.6,
                label=f"病床数 {_view_beds}",
            )
            ax.set_xlabel("日")
            ax.set_ylabel("患者数（名）")
            _set_weekday_ticks(ax, df["日"], _day_weekdays)
            _apply_daily_axes_style(ax)
            _leg = ax.legend(loc="upper left", ncol=2, frameon=False)
            _style_daily_legend(_leg)
            ax.set_xlim(1, days_in_month)
            st.pyplot(fig)
            plt.close(fig)

        # --- 新規入院・退院数 ---
        with col2:
            _bc_section_title("新規入院・退院数", icon="🚪")
            fig, ax = plt.subplots(figsize=(6, 3.2))
            fig.patch.set_alpha(0.0)
            _add_weekend_bg(ax, _weekend_days)
            x = df["日"]
            width = 0.38
            ax.bar(
                x - width/2, df["新規入院"], width,
                label="新規入院", color=_DT_INFO, alpha=0.85, edgecolor="none",
            )
            ax.bar(
                x + width/2, df["退院"], width,
                label="退院", color=_DT_WARD_6F, alpha=0.85, edgecolor="none",
            )
            ax.set_xlabel("日")
            ax.set_ylabel("人数")
            _set_weekday_ticks(ax, df["日"], _day_weekdays)
            _apply_daily_axes_style(ax)
            _leg = ax.legend(loc="upper left", ncol=2, frameon=False)
            _style_daily_legend(_leg)
            ax.set_xlim(0.5, days_in_month + 0.5)
            st.pyplot(fig)
            plt.close(fig)

        # 病棟別在院患者数は病棟セレクターで切り替え

        # --- 日次運営貢献額推移（Tertiary）---
        _bc_section_title("日次運営貢献額の推移", icon="💴")
        fig, ax = plt.subplots(figsize=(12, 2.8))
        fig.patch.set_alpha(0.0)
        _add_weekend_bg(ax, _weekend_days)
        # 正 = 成功色（緑系）、負 = 危険色（赤系）
        colors_profit = [_DT_SUCCESS if v >= 0 else _DT_DANGER for v in df["日次運営貢献額"]]
        ax.bar(
            df["日"], df["日次運営貢献額"] / 10000,
            color=colors_profit, alpha=0.85, edgecolor="none",
        )
        ax.axhline(y=0, color=_DT_TEXT_MUTED, linewidth=0.8)
        ax.set_xlabel("日")
        ax.set_ylabel("運営貢献額（万円）")
        _set_weekday_ticks(ax, df["日"], _day_weekdays)
        _apply_daily_axes_style(ax)
        ax.set_xlim(0.5, days_in_month + 0.5)
        st.pyplot(fig)
        plt.close(fig)

        # --- 今月のハイライト ---
        _bc_section_title("今月のハイライト", icon="📌")
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
if "🔄 フェーズ構成" in _tab_idx and _data_ready:
    with tabs[_tab_idx["🔄 フェーズ構成"]]:
        st.subheader("フェーズ構成")

        # --- A/B/C群の定義パネル（常時表示、折りたたみではない） ---
        _col_a, _col_b, _col_c = st.columns(3)
        with _col_a:
            st.markdown("""<div style="background:#FDEDEC;padding:6px 8px;border-radius:6px;border-left:3px solid #E74C3C;font-size:0.85em;">
<b style="color:#E74C3C;">🔴 A群（1〜5日）</b><br>
急性期・初期加算あり<br>
<b>貢献額 2.4万円/日</b>　目安15〜20%
</div>""", unsafe_allow_html=True)
        with _col_b:
            st.markdown("""<div style="background:#EAFAF1;padding:6px 8px;border-radius:6px;border-left:3px solid #27AE60;font-size:0.85em;">
<b style="color:#27AE60;">🟢 B群（6〜14日）</b><br>
回復期・★安定貢献層<br>
<b>貢献額 3.0万円/日</b>　目安40〜50%
</div>""", unsafe_allow_html=True)
        with _col_c:
            st.markdown("""<div style="background:#EBF5FB;padding:6px 8px;border-radius:6px;border-left:3px solid #2980B9;font-size:0.85em;">
<b style="color:#2980B9;">🔵 C群（15日〜）</b><br>
退院準備・退院調整で稼働維持<br>
<b>貢献額 2.9万円/日</b>　目安30〜40%
</div>""", unsafe_allow_html=True)

        if _HELP_AVAILABLE and "tab_phase" in HELP_TEXTS:
            with st.expander("📖 さらに詳しい活用法を見る"):
                st.markdown(HELP_TEXTS["tab_phase"])

        # --- KPI: A/B/C 群の人数と構成比（直近日） ---
        _bc_section_title("今日のフェーズ構成", icon="📊")
        try:
            _phase_total = float(df["A群_患者数"].iloc[-1] + df["B群_患者数"].iloc[-1] + df["C群_患者数"].iloc[-1])
            _a_n = float(df["A群_患者数"].iloc[-1])
            _b_n = float(df["B群_患者数"].iloc[-1])
            _c_n = float(df["C群_患者数"].iloc[-1])
            _a_p = (_a_n / _phase_total * 100) if _phase_total > 0 else 0.0
            _b_p = (_b_n / _phase_total * 100) if _phase_total > 0 else 0.0
            _c_p = (_c_n / _phase_total * 100) if _phase_total > 0 else 0.0

            _a_avg = float(summary.get("A群平均構成比", 0.0))
            _b_avg = float(summary.get("B群平均構成比", 0.0))
            _c_avg = float(summary.get("C群平均構成比", 0.0))

            _kpi_ph_c1, _kpi_ph_c2, _kpi_ph_c3 = st.columns(3)
            with _kpi_ph_c1:
                _bc_kpi_card(
                    label="A群（1〜5日・急性期）",
                    value=f"{_a_n:.0f}",
                    unit=" 名",
                    delta=f"構成比 {_a_p:.1f}% / 月平均 {_a_avg:.1f}%",
                    severity="neutral",
                )
            with _kpi_ph_c2:
                _bc_kpi_card(
                    label="B群（6〜14日・回復期）",
                    value=f"{_b_n:.0f}",
                    unit=" 名",
                    delta=f"構成比 {_b_p:.1f}% / 月平均 {_b_avg:.1f}%",
                    severity="success" if 40.0 <= _b_avg <= 55.0 else "neutral",
                )
            with _kpi_ph_c3:
                # C群は40%超過で注意喚起（長期在院過多のサイン）
                _c_sev = "warning" if _c_avg > 40.0 else "neutral"
                _bc_kpi_card(
                    label="C群（15日〜・退院準備）",
                    value=f"{_c_n:.0f}",
                    unit=" 名",
                    delta=f"構成比 {_c_p:.1f}% / 月平均 {_c_avg:.1f}%",
                    severity=_c_sev,
                )

            # C群が月平均で40%超過の場合は注意喚起
            if _c_avg > 40.0:
                _bc_alert(
                    f"⚠️ <b>C群平均構成比 {_c_avg:.1f}%</b> は目安（30〜40%）を上回っています。"
                    f"長期在院層が厚く、退院調整の余地を確認してください。",
                    severity="warning",
                )
        except Exception:
            # KPI 表示失敗してもグラフ描画は継続
            pass

        st.markdown("")  # 呼吸のための空行

        # --- A/B/C構成比の積み上げ面グラフ ---
        _bc_section_title("フェーズ別患者数推移（積み上げ）", icon="📈")
        fig, ax = plt.subplots(figsize=(12, 3))
        fig.patch.set_alpha(0.0)
        ax.stackplot(
            df["日"],
            df["A群_患者数"], df["B群_患者数"], df["C群_患者数"],
            labels=["A群（急性期）", "B群（回復期）", "C群（退院準備）"],
            colors=[COLOR_A, COLOR_B, COLOR_C],
            alpha=0.75,
        )
        ax.set_xlabel("日")
        ax.set_ylabel("患者数")
        ax.set_xlim(1, days_in_month)
        _bc_apply_chart_style(ax)
        _leg_stack = ax.legend(loc="upper left", ncol=3, frameon=False)
        _bc_style_legend(_leg_stack)
        st.pyplot(fig)
        plt.close(fig)

        col1, col2 = st.columns(2)

        # --- 平均円グラフ ---
        with col1:
            _bc_section_title("A/B/C 平均構成比", icon="🟢")
            fig, ax = plt.subplots(figsize=(4, 4))
            fig.patch.set_alpha(0.0)
            sizes = [summary["A群平均構成比"], summary["B群平均構成比"], summary["C群平均構成比"]]
            labels = [
                f"A群（急性期）\n{sizes[0]:.1f}%",
                f"B群（回復期）\n{sizes[1]:.1f}%",
                f"C群（退院準備）\n{sizes[2]:.1f}%",
            ]
            if sum(sizes) > 0:
                ax.pie(
                    sizes, labels=labels, colors=[COLOR_A, COLOR_B, COLOR_C],
                    autopct=None, startangle=90,
                    textprops={"fontsize": 10, "color": _DT_TEXT_PRIMARY},
                    wedgeprops={"edgecolor": "white", "linewidth": 2},
                )
            else:
                ax.text(0.5, 0.5, "フェーズデータなし", ha="center", va="center",
                        fontsize=12, color=_DT_TEXT_SECONDARY, transform=ax.transAxes)
            st.pyplot(fig)
            plt.close(fig)

        # --- フェーズ別患者数推移（折れ線） ---
        with col2:
            _bc_section_title("フェーズ別患者数推移（折れ線）", icon="📉")
            fig, ax = plt.subplots(figsize=(5, 3.5))
            fig.patch.set_alpha(0.0)
            ax.plot(df["日"], df["A群_患者数"], color=COLOR_A, linewidth=_DT_LW_PRIMARY, label="A群（急性期）")
            ax.plot(df["日"], df["B群_患者数"], color=COLOR_B, linewidth=_DT_LW_PRIMARY, label="B群（回復期）")
            ax.plot(df["日"], df["C群_患者数"], color=COLOR_C, linewidth=_DT_LW_PRIMARY, label="C群（退院準備）")
            ax.set_xlabel("日")
            ax.set_ylabel("患者数")
            ax.set_xlim(1, days_in_month)
            _bc_apply_chart_style(ax)
            _leg_pline = ax.legend(loc="upper left", ncol=3, frameon=False)
            _bc_style_legend(_leg_pline)
            st.pyplot(fig)
            plt.close(fig)

        # --- 理論上限との比較（Little法則ベース）---
        # ⚠️ これは「全患者が14日以上在院する」前提の上限値であり、
        #    実際には早期退院があるため B 実績 < 上限、C 実績 > 上限 となる傾向がある
        st.markdown("---")
        _bc_section_title("理論上限との比較（Little法則ベース）", icon="📐")

        # サイドバーの現在設定から理論値を動的計算
        # ⚠️ 病棟別表示時は、月間入院数も病床比率で按分する必要がある
        # （全体150人 × 47床/94床 = 75人/月 が病棟あたりの想定入院数）
        _target_occ_mid = (target_lower + target_upper) / 2  # 90-95%範囲の中央値
        _monthly_adm_full = params_dict.get("monthly_admissions", 150)
        if _selected_ward_key in ("5F", "6F"):
            _bed_ratio_phase = _view_beds / _TOTAL_BEDS_METRIC if _TOTAL_BEDS_METRIC > 0 else 0.5
            _monthly_adm_input = int(round(_monthly_adm_full * _bed_ratio_phase))
        else:
            _monthly_adm_input = _monthly_adm_full
        _ideal_result = calculate_ideal_phase_ratios(
            num_beds=_view_beds,
            monthly_admissions=_monthly_adm_input,
            target_occupancy=_target_occ_mid,
            days_per_month=_sidebar_calendar_days if '_sidebar_calendar_days' in dir() else 30,
            phase_a_contrib=phase_a_rev - phase_a_cost,
            phase_b_contrib=phase_b_rev - phase_b_cost,
            phase_c_contrib=phase_c_rev - phase_c_cost,
        )
        _ideal = {
            "A群": _ideal_result["a_pct"],
            "B群": _ideal_result["b_pct"],
            "C群": _ideal_result["c_pct"],
        }
        _actual_phase = {
            "A群": summary["A群平均構成比"],
            "B群": summary["B群平均構成比"],
            "C群": summary["C群平均構成比"],
        }

        # 理論値の導出条件を表示
        if _selected_ward_key in ("5F", "6F"):
            _adm_explain = f"月間入院数 <b>{_monthly_adm_input}人</b>（全体{_monthly_adm_full}人 × {_view_beds}/{_TOTAL_BEDS_METRIC}床比按分）"
        else:
            _adm_explain = f"月間入院数 <b>{_monthly_adm_input}人</b>"
        _bc_alert(
            f"📊 <b>理論上限の前提条件</b>: "
            f"{_adm_explain} × "
            f"目標稼働率 <b>{_target_occ_mid*100:.1f}%</b>（{target_lower*100:.0f}〜{target_upper*100:.0f}%の中央値） × "
            f"病床数 <b>{_view_beds}床</b> "
            f"→ 理論的平均在院日数 <b>{_ideal_result['target_los']:.1f}日</b><br>"
            f"A群 (1-5日): <b>{_ideal_result['a_count']:.1f}人</b> / "
            f"B群 (6-14日): <b>{_ideal_result['b_count']:.1f}人</b> / "
            f"C群 (15日-): <b>{_ideal_result['c_count']:.1f}人</b><br>"
            f"⚠️ <b>これは「全員が14日以上在院する」前提の上限値です。</b> "
            f"実際には短期退院があるため、B群は上限より少なく・C群は上限より多くなるのが普通です。",
            severity="info",
        )
        if not _ideal_result["feasible"]:
            _bc_alert(f"⚠️ {_ideal_result['notes']}", severity="warning")

        # 根拠の詳細説明
        with st.expander("🔎 この理論上限はどう計算しているか（Little法則）"):
            st.markdown(f"""
**計算ステップ**

1. **目標稼働率から必要な在院患者数を算出**
   - 目標在院患者数 = 病床数 × 目標稼働率
   - {_view_beds}床 × {_target_occ_mid*100:.1f}% = **{_ideal_result['target_patients']:.1f}人**

2. **Little法則で平均在院日数を逆算**
   - 平均在院日数 = 在院患者数 ÷ 1日あたり入院数
   - {_ideal_result['target_patients']:.1f}人 ÷ {_ideal_result['daily_admissions']:.2f}人/日 = **{_ideal_result['target_los']:.1f}日**

3. **「全員が14日以上在院する」前提で各フェーズの上限人数を算出**
   - この前提なら、全患者が A群→B群→C群 と順に流れます
   - A群上限 = 1日の入院数 × 5日間 = {_ideal_result['daily_admissions']:.2f} × 5 = **{_ideal_result['a_count']:.1f}人**
   - B群上限 = 1日の入院数 × 9日間 = {_ideal_result['daily_admissions']:.2f} × 9 = **{_ideal_result['b_count']:.1f}人**
   - C群上限 = 1日の入院数 × (平均在院日数 - 14日) = {_ideal_result['daily_admissions']:.2f} × {max(0, _ideal_result['target_los']-14):.2f} = **{_ideal_result['c_count']:.1f}人**

4. **構成比に変換**
   - A群: {_ideal_result['a_pct']:.1f}% / B群: {_ideal_result['b_pct']:.1f}% / C群: {_ideal_result['c_pct']:.1f}%

**⚠️ 実際との差の読み方**
現実には、入院後14日を待たずに退院する患者さんがいます。その患者さんは B群にたどり着かない分だけ、**B群は上限より少なく**、代わりに長期在院の高齢フレイル例などが **C群を上限より押し上げる** 傾向があります。

- B群が上限より低い = 早期退院が多い（必ずしも悪いことではない）
- C群が上限より高い = 長期在院層が厚い（退院調整の余地を見る指標）
- 合計人数（在院患者数）は Little 法則により保存されます

**根拠**: [Little法則](https://en.wikipedia.org/wiki/Little%27s_law) — 待ち行列理論の基本法則
`平均患者数 = 入院率 × 平均在院日数`
""")

        st.caption(f"月{_monthly_adm_input}人入院・稼働率{_target_occ_mid*100:.1f}%前提")
        fig, ax = plt.subplots(figsize=(8, 4))
        fig.patch.set_alpha(0.0)
        _phase_labels = list(_ideal.keys())
        _x_pos = np.arange(len(_phase_labels))
        _bar_w = 0.35
        _bars_ideal = ax.bar(
            _x_pos - _bar_w/2, [_ideal[k] for k in _phase_labels], _bar_w,
            label="理論上限（全員14日以上在院の仮定）",
            color=["#F5B7B1", "#ABEBC6", "#AED6F1"],
            edgecolor=_DT_BORDER, linewidth=0.6,
        )
        _bars_actual = ax.bar(
            _x_pos + _bar_w/2, [_actual_phase[k] for k in _phase_labels], _bar_w,
            label="実績",
            color=[COLOR_A, COLOR_B, COLOR_C], alpha=0.85,
        )
        ax.set_ylabel("構成比 (%)")
        ax.set_xticks(_x_pos)
        ax.set_xticklabels(_phase_labels)
        _bc_apply_chart_style(ax)
        _leg_ideal = ax.legend(loc="upper right", frameon=False)
        _bc_style_legend(_leg_ideal)
        # 値ラベル
        for _bar in _bars_ideal:
            _h = _bar.get_height()
            ax.text(_bar.get_x() + _bar.get_width()/2, _h + 0.5, f"{_h:.1f}%",
                    ha="center", fontsize=9, color=_DT_TEXT_MUTED)
        for _bar in _bars_actual:
            _h = _bar.get_height()
            ax.text(_bar.get_x() + _bar.get_width()/2, _h + 0.5, f"{_h:.1f}%",
                    ha="center", fontsize=9, color=_DT_TEXT_PRIMARY, fontweight="bold")
        st.pyplot(fig)
        plt.close(fig)

        # 乖離の一文解説（上限との差を「早期退院の多さ」「長期在院層の厚み」として読み替える）
        _b_diff = _actual_phase["B群"] - _ideal["B群"]
        _c_diff = _actual_phase["C群"] - _ideal["C群"]
        _bc_alert(
            f"<b>実績と上限の差の読み方</b><br>"
            f"・B群: 上限 {_ideal['B群']:.1f}% に対して実績 {_actual_phase['B群']:.1f}%（{_b_diff:+.1f}%）"
            f" → 差がマイナスに大きいほど、入院後14日以内に退院する患者さんの割合が高いことを意味します<br>"
            f"・C群: 上限 {_ideal['C群']:.1f}% に対して実績 {_actual_phase['C群']:.1f}%（{_c_diff:+.1f}%）"
            f" → 差がプラスに大きいほど、15日以上の長期在院層が厚いことを意味します（退院調整の余地を見る指標）",
            severity="info",
        )
        if _c_diff > 8:
            _bc_alert(
                f"⚠️ C群が上限より <b>{_c_diff:+.1f}%</b> と大きく上回っています。長期在院層の退院調整を検討する価値があります。",
                severity="warning",
            )

        # --- What-if シミュレーション（経営会議提案用）---
        st.markdown("---")
        with st.expander("🔬 What-if シミュレーション — 入院数・稼働率を変えたら", expanded=False):
            st.caption(
                "経営会議で「もし月間入院数を○人にしたら」「目標稼働率を○%にしたら」という議論をする際、"
                "理論的なフェーズ構成と運営貢献額の変化を即座に試算できます。"
            )

            _whatif_col_left, _whatif_col_right = st.columns([1, 2])

            with _whatif_col_left:
                st.markdown("**📊 シナリオ設定**")
                # 病棟別表示時はスライダー範囲も病床比率で按分
                if _selected_ward_key in ("5F", "6F"):
                    _wi_min = 60
                    _wi_max = 90
                    _wi_step = 5
                    _wi_help = f"{_selected_ward_key}病棟の月間入院数を60〜90人の範囲で変更できます"
                else:
                    _wi_min = 120
                    _wi_max = 180
                    _wi_step = 5
                    _wi_help = "全体の月間入院数を120〜180人の範囲で変更できます"
                # Session state を明示的に初期化する（`value=` と `key=` の併用による
                # 状態不整合を避けるため）
                _key_adm = f"whatif_phase_adm_{_selected_ward_key}"
                _key_occ = f"whatif_phase_occ_{_selected_ward_key}"
                _default_adm = int(max(_wi_min, min(_wi_max, _monthly_adm_input)))
                _default_occ = round(_target_occ_mid * 100 * 2) / 2  # 0.5刻みに丸め
                if _key_adm not in st.session_state:
                    st.session_state[_key_adm] = _default_adm
                if _key_occ not in st.session_state:
                    st.session_state[_key_occ] = _default_occ
                # スライダー値がプリセット/病棟切替で min/max レンジ外になった場合のクランプ
                if st.session_state[_key_adm] < _wi_min or st.session_state[_key_adm] > _wi_max:
                    st.session_state[_key_adm] = _default_adm
                if st.session_state[_key_occ] < 85.0 or st.session_state[_key_occ] > 100.0:
                    st.session_state[_key_occ] = _default_occ

                _whatif_admissions = st.slider(
                    "月間入院数",
                    min_value=_wi_min,
                    max_value=_wi_max,
                    step=_wi_step,
                    key=_key_adm,
                    help=_wi_help,
                )
                _whatif_occ_pct = st.slider(
                    "目標稼働率 (%)",
                    min_value=85.0,
                    max_value=100.0,
                    step=0.5,
                    format="%.1f",
                    key=_key_occ,
                    help="目標稼働率を85〜100%の範囲で0.5%刻みで変更できます",
                )
                # 念のため session_state から直接読む（戻り値とずれていた場合の防御）
                _whatif_admissions = int(st.session_state[_key_adm])
                _whatif_occ_pct = float(st.session_state[_key_occ])
                _whatif_occ = _whatif_occ_pct / 100

                st.markdown("")
                st.caption(
                    f"現在のサイドバー設定（ベースライン）: 月{int(_monthly_adm_input)}人 / {_target_occ_mid*100:.1f}%  \n"
                    f"↑ このスライダーの値: **月{_whatif_admissions}人 / {_whatif_occ_pct:.1f}%**（右側の計算に使用中）"
                )

            with _whatif_col_right:
                # 選択値で理論値を計算（プリセットの診療報酬を反映）
                _whatif_result = calculate_ideal_phase_ratios(
                    num_beds=_view_beds,
                    monthly_admissions=_whatif_admissions,
                    target_occupancy=_whatif_occ,
                    days_per_month=_sidebar_calendar_days if '_sidebar_calendar_days' in dir() else 30,
                    phase_a_contrib=phase_a_rev - phase_a_cost,
                    phase_b_contrib=phase_b_rev - phase_b_cost,
                    phase_c_contrib=phase_c_rev - phase_c_cost,
                )

                # 上部: 主要メトリクス
                _m1, _m2, _m3 = st.columns(3)
                _m1.metric("平均在院日数", f"{_whatif_result['target_los']:.1f}日")
                _m2.metric("目標在院患者数", f"{_whatif_result['target_patients']:.0f}人")
                _m3.metric("1日次運営貢献額", f"{_whatif_result['daily_contribution']/10000:.0f}万円")

                # 施設基準との比較
                if _whatif_result['target_los'] > 21:
                    _bc_alert(
                        f"🔴 <b>施設基準リスク</b>: 平均在院日数 {_whatif_result['target_los']:.1f}日 &gt; 21日 "
                        f"(2025年度上限)。このシナリオは地域包括医療病棟入院料1の算定基準を満たせません。",
                        severity="danger",
                    )
                elif _whatif_result['target_los'] > 20:
                    _bc_alert(
                        f"🟡 <b>2026年度注意</b>: 平均在院日数 {_whatif_result['target_los']:.1f}日 は "
                        f"2026年度上限20日を超過。85歳以上20%超なら+1日緩和で21日以内。",
                        severity="warning",
                    )
                elif not _whatif_result['feasible']:
                    _bc_alert(f"⚠️ {_whatif_result['notes']}", severity="warning")
                else:
                    _bc_alert(
                        f"✅ 平均在院日数 {_whatif_result['target_los']:.1f}日は施設基準内（上限21日）",
                        severity="success",
                    )

                # フェーズ別人数と比率の棒グラフ
                st.caption(f"月{_whatif_admissions}人入院 × 目標稼働率{_whatif_occ_pct:.1f}% → 理論構成")
                fig_wi, ax_wi = plt.subplots(figsize=(8, 3.5))
                fig_wi.patch.set_alpha(0.0)
                _wi_labels = ["A群\n(1-5日)", "B群\n(6-14日)", "C群\n(15日-)"]
                _wi_counts = [
                    _whatif_result['a_count'],
                    _whatif_result['b_count'],
                    _whatif_result['c_count'],
                ]
                _wi_pcts = [
                    _whatif_result['a_pct'],
                    _whatif_result['b_pct'],
                    _whatif_result['c_pct'],
                ]
                _wi_colors_list = [COLOR_A, COLOR_B, COLOR_C]
                _wi_bars = ax_wi.bar(_wi_labels, _wi_counts, color=_wi_colors_list, alpha=0.85)
                for _bar, _count, _pct in zip(_wi_bars, _wi_counts, _wi_pcts):
                    _h = _bar.get_height()
                    ax_wi.text(
                        _bar.get_x() + _bar.get_width() / 2,
                        _h + max(_wi_counts) * 0.02,
                        f"{_count:.1f}人\n({_pct:.1f}%)",
                        ha="center", fontsize=10, fontweight="bold",
                        color=_DT_TEXT_PRIMARY,
                    )
                ax_wi.set_ylabel("患者数（人）")
                ax_wi.set_ylim(0, max(_wi_counts) * 1.25)
                _bc_apply_chart_style(ax_wi)
                st.pyplot(fig_wi)
                plt.close(fig_wi)

            # 現在値との差分を1行サマリーで表示
            _delta_adm = _whatif_admissions - int(_monthly_adm_input)
            _delta_occ = _whatif_occ_pct - (_target_occ_mid * 100)
            _current_result = calculate_ideal_phase_ratios(
                num_beds=_view_beds,
                monthly_admissions=int(_monthly_adm_input),
                target_occupancy=_target_occ_mid,
                days_per_month=_sidebar_calendar_days if '_sidebar_calendar_days' in dir() else 30,
                phase_a_contrib=phase_a_rev - phase_a_cost,
                phase_b_contrib=phase_b_rev - phase_b_cost,
                phase_c_contrib=phase_c_rev - phase_c_cost,
            )
            _delta_contrib = (_whatif_result['daily_contribution'] - _current_result['daily_contribution'])
            _delta_contrib_monthly = _delta_contrib * 30
            _delta_contrib_yearly = _delta_contrib * 365

            if abs(_delta_adm) > 0 or abs(_delta_occ) > 0.1:
                _delta_label = []
                if _delta_adm != 0:
                    _delta_label.append(f"入院 **{_delta_adm:+d}人/月**")
                if abs(_delta_occ) > 0.1:
                    _delta_label.append(f"稼働率 **{_delta_occ:+.1f}%**")
                _delta_text = " / ".join(_delta_label)

                if _delta_contrib > 0:
                    _bc_alert(
                        f"💰 <b>現状との比較</b>: {_delta_text}<br>"
                        f"→ 日次運営貢献額 <b>+{_delta_contrib/10000:.1f}万円/日</b> "
                        f"（月間 <b>+{_delta_contrib_monthly/10000:.0f}万円</b> / "
                        f"年間 <b>+{_delta_contrib_yearly/10000:,.0f}万円</b>）",
                        severity="success",
                    )
                elif _delta_contrib < 0:
                    _bc_alert(
                        f"💰 <b>現状との比較</b>: {_delta_text}<br>"
                        f"→ 日次運営貢献額 <b>{_delta_contrib/10000:.1f}万円/日</b> "
                        f"（月間 <b>{_delta_contrib_monthly/10000:.0f}万円</b> / "
                        f"年間 <b>{_delta_contrib_yearly/10000:,.0f}万円</b>）",
                        severity="warning",
                    )

            # 経営会議提案用の注記
            st.caption(
                "💡 **経営会議での使い方**: スライダーで「実現可能な目標」を探り、"
                "その場合のフェーズ構成・運営貢献額・施設基準リスクを同時に確認できます。"
                "入院数を増やす施策（外来強化・連携室拡充）の定量的な期待値算出に活用できます。"
            )

        # 病棟別フェーズ構成は病棟セレクターで切り替え（比較ストリップで他病棟を表示）


# ===== タブ3: 運営分析 =====
if "💰 運営分析" in _tab_idx and _data_ready:
    with tabs[_tab_idx["💰 運営分析"]]:
        st.subheader("運営分析")
        if _HELP_AVAILABLE and "tab_finance" in HELP_TEXTS:
            with st.expander("📖 このタブの見方と活用法"):
                st.markdown(HELP_TEXTS["tab_finance"])

        # --- 稼働率ギャップ＆月次達成パネル ---
        _target_occ_line = target_lower  # 0.90
        _actual_avg_occ = summary["平均稼働率"]
        _occ_gap = _actual_avg_occ - _target_occ_line * 100  # 例: 87.2 - 90 = -2.8

        # 金額ベースの計算（補助指標として表示）
        # 目標は経過日数ベースで計算（19日分の実績を19日分の目標と比較）
        # 加重平均日次運営貢献額（現在のプリセットから計算: A15%+B45%+C40%の比率）
        _weighted_daily_rev = 0.15 * (phase_a_rev - phase_a_cost) + 0.45 * (phase_b_rev - phase_b_cost) + 0.40 * (phase_c_rev - phase_c_cost)
        _days_elapsed = summary.get("シミュレーション日数", days_in_month)
        _target_monthly_rev = _view_beds * _target_occ_line * _days_elapsed * _weighted_daily_rev
        # 運営貢献額: 現在のプリセットでリアルタイム再計算
        _actual_monthly_rev = summary["月次運営貢献額"]
        if isinstance(_active_raw_df, pd.DataFrame) and len(_active_raw_df) > 0:
            _has_phase_cols = all(c in _active_raw_df.columns for c in ["phase_a_count", "phase_b_count", "phase_c_count"])
            if _has_phase_cols:
                _pa_d = int(_active_raw_df["phase_a_count"].sum())
                _pb_d = int(_active_raw_df["phase_b_count"].sum())
                _pc_d = int(_active_raw_df["phase_c_count"].sum())
                _actual_monthly_rev = (_pa_d * phase_a_rev + _pb_d * phase_b_rev + _pc_d * phase_c_rev) - (_pa_d * phase_a_cost + _pb_d * phase_b_cost + _pc_d * phase_c_cost)
        _achievement_rate = (_actual_monthly_rev / _target_monthly_rev * 100) if _target_monthly_rev > 0 else 0

        # 残り日数と未活用病床コスト（直近の空床数ベース）
        _days_left = max(0, _calendar_month_days - _days_elapsed)
        # 直近日の実績から空床数を取得（平均ではなく最新日）
        _last_patients_col = "在院患者数" if "在院患者数" in df.columns else "total_patients"
        _last_patients_val = int(df[_last_patients_col].iloc[-1]) if _last_patients_col in df.columns and len(df) > 0 else round(_actual_avg_occ / 100 * _view_beds)
        _current_empty = max(0, _view_beds - _last_patients_val)
        _remaining_cost = _current_empty * int(_daily_rev_per_bed) * _days_left

        # 色分け（稼働率ベースで判定）
        if _occ_gap >= 0:
            _ach_bg = "#EAFAF1"; _ach_border = "#27AE60"; _ach_icon = "✅"; _ach_msg = "目標レンジ内"
        elif _occ_gap >= -3:
            _ach_bg = "#FEF9E7"; _ach_border = "#F39C12"; _ach_icon = "⚠️"; _ach_msg = "目標未達"
        else:
            _ach_bg = "#FDEDEC"; _ach_border = "#E74C3C"; _ach_icon = "🔴"; _ach_msg = "大幅未達"

        # 稼働率の色分け
        if _actual_avg_occ < _target_occ_line * 100:
            _occ_color = "#E74C3C"
        elif _actual_avg_occ <= target_upper * 100:
            _occ_color = "#27AE60"
        else:
            _occ_color = "#F39C12"

        # ギャップの表示文字列
        _gap_sign = "+" if _occ_gap >= 0 else ""
        _gap_str = f"{_gap_sign}{_occ_gap:.1f}pt"

        # 残日数メッセージ
        if _days_left > 0:
            _remaining_msg = f"残り<b>{_days_left}日</b>で現ペース継続時の空床の影響額: <b>約{_remaining_cost // 10000:,.0f}万円</b>"
        else:
            _remaining_msg = "月末（実績確定）"

        st.markdown(f"""
<div style="background:{_ach_bg}; padding:8px 12px; border-radius:10px; border-left:5px solid {_ach_border}; margin-bottom:8px;">
<div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap;">
<div>
<h3 style="margin:0; color:{_ach_border};">{_ach_icon} 稼働率 {_actual_avg_occ:.1f}%（目標{_target_occ_line*100:.0f}%比 {_gap_str}）　<span style="font-size:0.7em; color:#666;">— {_ach_msg}</span></h3>
<p style="margin:4px 0 0 0; font-size:0.9em; color:#555;">
運営貢献額({_days_elapsed}日分): 実績 <b>{_actual_monthly_rev/10000:,.0f}万円</b> / 目標(90%ベース) <b>{_target_monthly_rev/10000:,.0f}万円</b>（達成率 {_achievement_rate:.1f}%）
</p>
<p style="margin:2px 0 0 0; font-size:0.9em; color:#555;">
{_remaining_msg}
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

        # --- メトリクスカード（現在のプリセットでリアルタイム再計算）---
        # フェーズ別患者日数からプリセットの報酬・コストで再計算
        _recalc_rev = summary["月次診療報酬"]
        _recalc_cost = summary["月次コスト"]
        _recalc_profit = summary["月次運営貢献額"]
        if isinstance(_active_raw_df, pd.DataFrame) and len(_active_raw_df) > 0:
            _has_phase = all(c in _active_raw_df.columns for c in ["phase_a_count", "phase_b_count", "phase_c_count"])
            if _has_phase:
                _pa_days = int(_active_raw_df["phase_a_count"].sum())
                _pb_days = int(_active_raw_df["phase_b_count"].sum())
                _pc_days = int(_active_raw_df["phase_c_count"].sum())
                _recalc_rev = _pa_days * phase_a_rev + _pb_days * phase_b_rev + _pc_days * phase_c_rev
                _recalc_cost = _pa_days * phase_a_cost + _pb_days * phase_b_cost + _pc_days * phase_c_cost
                _recalc_profit = _recalc_rev - _recalc_cost

        # --- 月末予測・目標値の計算 ---
        _proj_rev = _recalc_rev / _days_elapsed * _calendar_month_days if _days_elapsed > 0 else _recalc_rev
        _proj_cost = _recalc_cost / _days_elapsed * _calendar_month_days if _days_elapsed > 0 else _recalc_cost
        _proj_profit = _proj_rev - _proj_cost
        # 目標値（稼働率90%・95%での月間額）
        _target_lo_rev = _view_beds * target_lower * _calendar_month_days * _daily_rev_per_bed
        _target_hi_rev = _view_beds * target_upper * _calendar_month_days * _daily_rev_per_bed
        _target_lo_cost = _view_beds * target_lower * _calendar_month_days * (0.15 * phase_a_cost + 0.45 * phase_b_cost + 0.40 * phase_c_cost)
        _target_hi_cost = _view_beds * target_upper * _calendar_month_days * (0.15 * phase_a_cost + 0.45 * phase_b_cost + 0.40 * phase_c_cost)
        _target_lo_profit = _target_lo_rev - _target_lo_cost
        _target_hi_profit = _target_hi_rev - _target_hi_cost
        # 予測 vs 目標の比較基準: 目標レンジの中央値（90%と95%の中間 → 例: 92.5%だが端数回避で切り上げ）
        _target_mid = (target_lower + target_upper) / 2  # 例: 0.925
        # 94%固定ではなくレンジ中央+1ptを採用（90-95%なら93.5→94%相当）
        _target_compare = 0.94
        _target_cmp_rev = _view_beds * _target_compare * _calendar_month_days * _daily_rev_per_bed
        _target_cmp_cost = _view_beds * _target_compare * _calendar_month_days * (0.15 * phase_a_cost + 0.45 * phase_b_cost + 0.40 * phase_c_cost)
        _target_cmp_profit = _target_cmp_rev - _target_cmp_cost
        _profit_vs_target = (_proj_profit / _target_cmp_profit * 100) if _target_cmp_profit > 0 else 0

        # --- 冒頭 KPI カード（3枚）: 今月の総運営貢献額・平均日次貢献額・目標比 ---
        _bc_section_title("今月の運営貢献サマリー", icon="💰")
        _avg_daily_contrib = (_recalc_profit / _days_elapsed) if _days_elapsed > 0 else 0.0
        _target_daily_contrib = _target_cmp_profit / _calendar_month_days if _calendar_month_days > 0 else 0.0
        _delta_daily = _avg_daily_contrib - _target_daily_contrib
        # 予測と目標下限の差（先月比の代替 — 月次の改善余地）
        _delta_vs_target_monthly = _proj_profit - _target_lo_profit
        _kpi_fin_c1, _kpi_fin_c2, _kpi_fin_c3 = st.columns(3)
        with _kpi_fin_c1:
            _bc_kpi_card(
                label=f"今月の総運営貢献額（{_days_elapsed}日分実績）",
                value=f"{_recalc_profit/10000:,.0f}",
                unit=" 万円",
                delta=f"現ペース月末予測 {_proj_profit/10000:,.0f} 万円",
                severity="success" if _profit_vs_target >= 100 else ("warning" if _profit_vs_target >= 90 else "danger"),
            )
        with _kpi_fin_c2:
            _bc_kpi_card(
                label="平均日次貢献額（実績）",
                value=f"{_avg_daily_contrib/10000:,.1f}",
                unit=" 万円/日",
                delta=f"目標比 {_delta_daily/10000:+,.1f} 万円/日（目標 {_target_daily_contrib/10000:.1f} 万円/日）",
                severity="success" if _delta_daily >= 0 else ("warning" if _delta_daily >= -_target_daily_contrib * 0.05 else "danger"),
            )
        with _kpi_fin_c3:
            _bc_kpi_card(
                label=f"月末予測 vs 目標（稼働率 {_target_compare*100:.0f}%）",
                value=f"{_profit_vs_target:.1f}",
                unit=" %",
                delta=f"目標下限 ({target_lower*100:.0f}%) 比 {_delta_vs_target_monthly/10000:+,.0f} 万円",
                severity="success" if _profit_vs_target >= 100 else ("warning" if _profit_vs_target >= 90 else "danger"),
            )

        st.markdown("")  # 呼吸のための空行

        c1, c2, c3, c4 = st.columns(4)
        c1.metric(f"診療報酬（{_days_elapsed}日分実績）", fmt_yen(_recalc_rev),
                  help="入院患者の診療報酬合計（入院料＋初期加算＋リハビリ出来高）")
        c2.metric(f"コスト（{_days_elapsed}日分実績）", fmt_yen(_recalc_cost),
                  help="薬剤費・材料費・検査費・給食費などの変動費合計（固定費は含まない）")
        c3.metric(f"運営貢献額（{_days_elapsed}日分実績）", fmt_yen(_recalc_profit),
                  help="診療報酬 − 変動費コスト = 病棟が生み出す粗利益（固定費カバーに充てる額）")
        c4.metric("平均稼働率", f"{summary['平均稼働率']:.1f}%")

        # 月末予測・目標値
        st.markdown(f"""
<div style="background:#F8F9FA; padding:12px 16px; border-radius:8px; margin:8px 0 12px 0; font-size:0.9em;">
<table style="width:100%; border-collapse:collapse;">
<tr style="border-bottom:1px solid #DEE2E6;">
<th style="text-align:left; padding:4px 8px; color:#666;">　</th>
<th style="text-align:right; padding:4px 8px; color:#666;">診療報酬</th>
<th style="text-align:right; padding:4px 8px; color:#666;">コスト</th>
<th style="text-align:right; padding:4px 8px; color:#666;">運営貢献額</th>
</tr>
<tr style="border-bottom:1px solid #EEE;">
<td style="padding:4px 8px;">📊 現ペース月末予測</td>
<td style="text-align:right; padding:4px 8px; font-weight:bold;">{_proj_rev/10000:,.0f}万円</td>
<td style="text-align:right; padding:4px 8px;">{_proj_cost/10000:,.0f}万円</td>
<td style="text-align:right; padding:4px 8px; font-weight:bold;">{_proj_profit/10000:,.0f}万円</td>
</tr>
<tr style="border-bottom:1px solid #EEE;">
<td style="padding:4px 8px;">🎯 目標値（稼働率{target_lower*100:.0f}%）</td>
<td style="text-align:right; padding:4px 8px;">{_target_lo_rev/10000:,.0f}万円</td>
<td style="text-align:right; padding:4px 8px;">{_target_lo_cost/10000:,.0f}万円</td>
<td style="text-align:right; padding:4px 8px;">{_target_lo_profit/10000:,.0f}万円</td>
</tr>
<tr>
<td style="padding:4px 8px;">🎯 目標値（稼働率{target_upper*100:.0f}%）</td>
<td style="text-align:right; padding:4px 8px;">{_target_hi_rev/10000:,.0f}万円</td>
<td style="text-align:right; padding:4px 8px;">{_target_hi_cost/10000:,.0f}万円</td>
<td style="text-align:right; padding:4px 8px;">{_target_hi_profit/10000:,.0f}万円</td>
</tr>
</table>
<p style="margin:6px 0 0 0; text-align:right; color:#555;">予測 vs 目標（稼働率{_target_compare*100:.0f}%）: <b style="color:{'#27AE60' if _profit_vs_target >= 100 else '#E74C3C'};">{_profit_vs_target:.1f}%</b></p>
</div>
""", unsafe_allow_html=True)
        st.caption("💡 診療報酬=入院料収入 | コスト=変動費(固定費除く) | 運営貢献額=粗利益")

        # =========================================================================
        # 短手3 分離表示パネル（Phase 3）
        # =========================================================================
        # 通常入院 + 短手3 包括点数の運営貢献額を分離して見せる
        # admission_details の short3_type 列を使って種類別に集計
        _show_short3_panel = False
        _short3_summary_month = {"total_cases": 0, "total_revenue": 0, "total_cost": 0, "by_type": {}}
        if _DETAIL_DATA_AVAILABLE and isinstance(st.session_state.get("admission_details"), pd.DataFrame):
            _ad_df = st.session_state.admission_details
            if len(_ad_df) > 0 and "short3_type" in _ad_df.columns:
                # 現在月でフィルタ
                _ad_df = _ad_df.copy()
                _ad_df["date"] = pd.to_datetime(_ad_df["date"])
                if len(_ad_df) > 0:
                    _latest = _ad_df["date"].max()
                    _month_mask = (_ad_df["date"].dt.year == _latest.year) & (_ad_df["date"].dt.month == _latest.month)
                    _ad_month = _ad_df[_month_mask]
                    # 病棟でフィルタ（全体のときはフィルタしない）
                    if _selected_ward_key in ("5F", "6F"):
                        _ad_month = _ad_month[_ad_month["ward"] == _selected_ward_key]
                    # 入院イベントかつ short3_type あり
                    _ad_s3 = _ad_month[
                        (_ad_month["event_type"] == "admission")
                        & _ad_month["short3_type"].notna()
                        & (_ad_month["short3_type"] != "")
                    ]
                    if len(_ad_s3) > 0:
                        _show_short3_panel = True
                        for _s3t, _grp in _ad_s3.groupby("short3_type"):
                            _cnt = len(_grp)
                            _rev = _short3_revenue_map.get(_s3t, 0) * _cnt
                            _cost = _short3_cost_map.get(_s3t, 0) * _cnt
                            _short3_summary_month["by_type"][str(_s3t)] = {
                                "cases": _cnt, "revenue": _rev, "cost": _cost,
                                "contribution": _rev - _cost,
                            }
                            _short3_summary_month["total_cases"] += _cnt
                            _short3_summary_month["total_revenue"] += _rev
                            _short3_summary_month["total_cost"] += _cost

        if _show_short3_panel:
            _s3_total_contrib = _short3_summary_month["total_revenue"] - _short3_summary_month["total_cost"]
            # 通常分の運営貢献額 (recalc profit は通常分として扱う)
            _normal_contrib = _recalc_profit
            _combined_contrib = _normal_contrib + _s3_total_contrib

            st.markdown("### 🏃 短手3（包括点数）分離表示")
            st.caption(
                f"{_selected_ward_key} の今月の短期滞在手術等基本料3 算定分。包括点数ベースで別計算しています。"
            )

            _s3_cols = st.columns(3)
            _s3_cols[0].metric(
                "短手3 件数",
                f"{_short3_summary_month['total_cases']}件",
                help="当月の 短期滞在手術等基本料3 算定件数",
            )
            _s3_cols[1].metric(
                "短手3 収入（包括）",
                f"¥{_short3_summary_month['total_revenue']/10000:,.1f}万",
                help="種類別の包括点数 × 件数の合計",
            )
            _s3_cols[2].metric(
                "短手3 運営貢献額",
                f"¥{_s3_total_contrib/10000:,.1f}万",
                help="短手3 収入 − 短手3 コスト",
            )

            # 種類別内訳テーブル
            _s3_rows = []
            for _t, _d in _short3_summary_month["by_type"].items():
                _s3_rows.append({
                    "種類": _t,
                    "件数": _d["cases"],
                    "収入/件": f"¥{_short3_revenue_map.get(_t, 0):,}",
                    "収入合計": f"¥{_d['revenue']:,}",
                    "貢献額/件": f"¥{_short3_revenue_map.get(_t, 0) - _short3_cost_map.get(_t, 0):,}",
                    "貢献額合計": f"¥{_d['contribution']:,}",
                })
            if _s3_rows:
                st.dataframe(pd.DataFrame(_s3_rows), hide_index=True, use_container_width=True)

            # 合算表示: 通常分 + 短手3分
            st.markdown(
                f"""
<div style="background:#F0F9FF; padding:12px 16px; border-radius:8px; border-left:4px solid #0EA5E9; margin:8px 0;">
<b>📊 月次運営貢献額（通常分 + 短手3 分）</b><br/>
<table style="width:100%; border-collapse:collapse; margin-top:6px;">
<tr><td style="padding:3px 6px; color:#555;">通常入院分（病棟稼働）</td>
    <td style="text-align:right; padding:3px 6px;"><b>¥{_normal_contrib/10000:,.1f}万</b></td></tr>
<tr><td style="padding:3px 6px; color:#555;">短手3 分（包括点数）</td>
    <td style="text-align:right; padding:3px 6px;"><b>¥{_s3_total_contrib/10000:,.1f}万</b> ({_short3_summary_month['total_cases']}件)</td></tr>
<tr style="border-top:1px solid #BAE6FD;">
    <td style="padding:4px 6px;"><b>合計</b></td>
    <td style="text-align:right; padding:4px 6px;"><b style="color:#0369A1;">¥{_combined_contrib/10000:,.1f}万</b></td></tr>
</table>
</div>
""",
                unsafe_allow_html=True,
            )

        c5, c6, c7, c8, c9 = st.columns(5)
        c5.metric("月間入院数", f"{summary['月間入院数']}人")
        c6.metric("月間退院数", f"{summary['月間退院数']}人")
        c7.metric("目標レンジ内日数", f"{summary['目標レンジ内日数']}/{days_in_month}日")
        c8.metric("目標レンジ内率", f"{summary['目標レンジ内率']}%")
        _current_avg_los = summary["平均在院日数"]  # 今月集計値（選択中ビューの値）
        _is_ward_view = _selected_ward_key in ("5F", "6F")

        # --- 過去3ヶ月rolling 平均在院日数（2026年改定対応・施設基準は各病棟ごとに判定）---
        # ⚠️ 重要: 地域包括医療病棟の施設基準は各病棟ごとに満たす必要がある。
        # 全病棟・5F・6F それぞれを個別に計算して判定する。
        # 2026年改定: 短手3算定患者は平均在院日数計算から除外する
        _rolling_ds = None
        _rolling_los_ds = None
        _rolling_los_ex_ds = None
        _rolling_days_ds = 0
        _rolling_is_partial_ds = False
        if _DATA_MANAGER_AVAILABLE and isinstance(_active_raw_df_full, pd.DataFrame) and len(_active_raw_df_full) > 0:
            try:
                _rolling_ds = calculate_rolling_los(_active_raw_df_full, window_days=90, monthly_summary=st.session_state.get("monthly_summary"), ward=_selected_ward_key if _selected_ward_key in ("5F", "6F") else None)
                if _rolling_ds:
                    _rolling_los_ds = _rolling_ds.get("rolling_los")
                    _rolling_los_ex_ds = _rolling_ds.get("rolling_los_ex_short3")
                    _rolling_days_ds = _rolling_ds.get("actual_days", 0)
                    _rolling_is_partial_ds = _rolling_ds.get("is_partial", False)
            except Exception:
                _rolling_ds = None

        # 各病棟ごとの rolling を計算
        _ward_rolling_ds = {}
        if _DATA_MANAGER_AVAILABLE:
            _ward_dfs_ds = (
                globals().get("_ward_raw_dfs_full", {})
                or st.session_state.get("ward_raw_dfs_full", {})
            )
            for _w in ["5F", "6F"]:
                _wdf_ds = _ward_dfs_ds.get(_w) if _ward_dfs_ds else None
                if _wdf_ds is None and _selected_ward_key == _w and isinstance(_active_raw_df_full, pd.DataFrame):
                    _wdf_ds = _active_raw_df_full
                if _wdf_ds is not None and isinstance(_wdf_ds, pd.DataFrame) and len(_wdf_ds) > 0:
                    try:
                        _ward_rolling_ds[_w] = calculate_rolling_los(_wdf_ds, window_days=90, monthly_summary=st.session_state.get("monthly_summary"), ward=_w)
                    except Exception:
                        pass

        # 施設基準判定: rolling (短手3除外後) 値を優先、未計算なら月次集計値にフォールバック
        # 2026年改定で施設基準判定は短手3除外後の値を用いる
        _judge_rolling = _rolling_los_ex_ds if _rolling_los_ex_ds is not None else _rolling_los_ds
        _judge_los = _judge_rolling if _judge_rolling is not None else _current_avg_los
        _los_over = _judge_los - _max_avg_los

        if _rolling_los_ds is not None:
            # 短手3 を除外した場合に値が変わるなら併記
            if _rolling_los_ex_ds is not None and _rolling_los_ex_ds != _rolling_los_ds:
                _delta_label = f"3ヶ月平均: {_rolling_los_ds}日→除外後{_rolling_los_ex_ds}日"
            else:
                _delta_label = f"3ヶ月平均: {_rolling_los_ds}日（{_rolling_days_ds}日分）"
        else:
            _delta_label = None

        c9.metric(
            "平均在院日数（今月集計）",
            f"{_current_avg_los}日",
            delta=_delta_label if _delta_label else (f"基準超過 +{_los_over:.1f}日" if _los_over > 0 else f"基準内（余裕 {-_los_over:.1f}日）"),
            delta_color="off" if _delta_label else ("inverse" if _los_over > 0 else "normal"),
            help="施設基準判定は3ヶ月rolling平均で行います。厚労省公式: 在院患者延日数 ÷ ((新入院患者数 + 退院患者数) ÷ 2)",
        )

        _caption_lines = [
            f"※ 今月集計は厚生労働省「病院報告」の公式定義に準拠",
            f"算定基準上限: **{_max_avg_los}日以内**（{_fee_preset_name}）",
        ]
        st.caption("　|　".join(_caption_lines))

        # --- 各病棟の施設基準判定を常時表示（病棟別個別判定）---
        if _ward_rolling_ds:
            st.markdown(
                "**📏 各病棟の施設基準判定（3ヶ月rolling・各病棟ごと）**  \n"
                "<span style='color:#666;font-size:0.85em;'>"
                "⚠️ 地域包括医療病棟の平均在院日数基準は、病院全体ではなく"
                "<strong>各病棟それぞれ</strong>が満たす必要があります"
                "</span>",
                unsafe_allow_html=True,
            )
            _ward_judge_cols = st.columns(len(_ward_rolling_ds))
            _any_ward_over = False
            _ward_over_details = []
            for _idx, (_w, _wres) in enumerate(_ward_rolling_ds.items()):
                with _ward_judge_cols[_idx]:
                    if _wres is None or _wres.get("rolling_los") is None:
                        st.markdown(f"**{_w}**: データなし")
                        continue
                    _wlos = _wres["rolling_los"]
                    _wlos_ex = _wres.get("rolling_los_ex_short3")
                    _wshort3 = _wres.get("total_short3", 0) or 0
                    _wdays = _wres["actual_days"]
                    _wpartial = _wres["is_partial"]
                    # 施設基準判定は「短手3除外後」値で行う（2026年改定対応）
                    _wjudge = _wlos_ex if _wlos_ex is not None else _wlos
                    _wdiff = _wjudge - _max_avg_los
                    if _wjudge <= _max_avg_los:
                        _wicon = "✅"
                        _wstatus = "基準内"
                        _wcolor = "#27AE60"
                    elif _wjudge <= _max_avg_los + 0.5:
                        _wicon = "⚠️"
                        _wstatus = f"ぎりぎり(+{_wdiff:.1f}日)"
                        _wcolor = "#F39C12"
                        _any_ward_over = True
                        _ward_over_details.append((_w, _wjudge, _wdiff))
                    else:
                        _wicon = "🔴"
                        _wstatus = f"超過(+{_wdiff:.1f}日)"
                        _wcolor = "#C0392B"
                        _any_ward_over = True
                        _ward_over_details.append((_w, _wjudge, _wdiff))
                    _wdays_txt = f"過去{_wdays}日(不足)" if _wpartial else f"過去{_wdays}日"
                    # 短手3 除外後の併記
                    if _wshort3 > 0 and _wlos_ex is not None and _wlos_ex != _wlos:
                        _wex_txt = (
                            f"<br/><span style='color:#666;font-size:0.85em;'>"
                            f"通常 {_wlos}日 → 短手3除外後 "
                            f"<strong style='color:{_wcolor};'>{_wlos_ex}日</strong>"
                            f"（除外 {int(_wshort3)}件）</span>"
                        )
                    else:
                        _wex_txt = ""
                    st.markdown(
                        f"<div style='padding:8px 12px;background:#F8F9FA;border-left:4px solid {_wcolor};border-radius:4px;'>"
                        f"<strong>{_w}病棟</strong>: {_wicon} "
                        f"<strong style='color:{_wcolor};font-size:1.15em;'>{_wjudge}日</strong> "
                        f"/ 上限 {_max_avg_los}日<br/>{_wstatus}"
                        f"{_wex_txt}"
                        f"<br/><span style='color:#888;font-size:0.8em;'>{_wdays_txt}</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

        # --- 平均在院日数アラート（病棟別判定に変更）---
        # いずれかの病棟が基準超過している場合にアラート表示
        if _ward_rolling_ds and _ward_over_details:
            # C群患者数を取得（選択病棟の値）
            _c_count = 0
            if "C群患者数" in df.columns:
                _c_count = int(df["C群患者数"].iloc[-1]) if len(df) > 0 else 0
            elif "phase_c_count" in df.columns:
                _c_count = int(df["phase_c_count"].iloc[-1]) if len(df) > 0 else 0

            _over_descriptions = []
            for _w, _wlos, _wdiff in _ward_over_details:
                _over_descriptions.append(f"**{_w}: {_wlos}日（+{_wdiff:.1f}日超過）**")
            _over_text = "、".join(_over_descriptions)

            _critical = any(_wdiff > 0.5 for _w, _wlos, _wdiff in _ward_over_details)
            _los_alert_lines = [
                f"🚨 <b>病棟施設基準超過</b> — {_over_text}<br><br>",
                f"地域包括医療病棟の施設基準（各病棟ごとに平均在院日数{_max_avg_los}日以内）を満たさなくなるリスクがあります。",
                f" 該当病棟で早急にC群（15日目以降）患者の退院調整が必要です。<br><br>",
                "<b>対策（該当病棟のC群患者からの退院促進）:</b><br>",
                "・超過している病棟のC群（在院15日以上）患者をリストアップ<br>",
                "・転院先・在宅復帰先の早期確保（連携室への依頼）<br>",
                "・退院前カンファレンスの前倒し実施<br>",
                "・該当病棟への新規入院受入れ（分母を増やす）による平均在院日数の引き下げ",
            ]
            if _c_count > 0 and _is_ward_view:
                _los_alert_lines.append(f"<br>現在の{_selected_ward_key}のC群患者数: <b>{_c_count}名</b>")
            if _critical:
                _bc_alert("".join(_los_alert_lines), severity="danger")
            else:
                _bc_alert("".join(_los_alert_lines), severity="warning")
        elif _rolling_los_ds is not None and _los_over > -1 and _los_over < 0:
            # 選択病棟・全体が基準ぎりぎり（余裕1日未満）
            # 施設基準判定は除外後の値を使う
            _info_los = _judge_rolling if _judge_rolling is not None else _rolling_los_ds
            _ex_note = ""
            if _rolling_los_ex_ds is not None and _rolling_los_ex_ds != _rolling_los_ds:
                _ex_note = f"（通常 {_rolling_los_ds}日 → 短手3除外後 {_rolling_los_ex_ds}日）"
            _bc_alert(
                f"ℹ️ <b>余裕は{-_los_over:.1f}日</b> — {_selected_ward_key} の3ヶ月rolling は {_info_los}日 "
                f"{_ex_note}で基準内ですが、基準超過が近づいています。C群患者の退院タイミングに注意してください。",
                severity="info",
            )

        # --- 日次診療報酬・コスト・運営貢献額（プリセット連動で再計算）---
        _chart_rev = df["日次診療報酬"]
        _chart_cost = df["日次コスト"]
        _chart_profit = df["日次運営貢献額"]
        # フェーズ別患者数カラムがあれば現在のプリセットで再計算
        _phase_cols_ja = {"A群患者数": (phase_a_rev, phase_a_cost), "B群患者数": (phase_b_rev, phase_b_cost), "C群患者数": (phase_c_rev, phase_c_cost)}
        if all(c in df.columns for c in _phase_cols_ja):
            _chart_rev = sum(df[c] * r for c, (r, _) in _phase_cols_ja.items())
            _chart_cost = sum(df[c] * k for c, (_, k) in _phase_cols_ja.items())
            _chart_profit = _chart_rev - _chart_cost

        _bc_section_title("日次診療報酬・コスト・運営貢献額推移", icon="📈")
        fig, ax = plt.subplots(figsize=(12, 3))
        fig.patch.set_alpha(0.0)
        ax.plot(df["日"], _chart_rev / 10000, color=COLOR_REVENUE, linewidth=_DT_LW_PRIMARY, label="診療報酬収入")
        ax.plot(df["日"], _chart_cost / 10000, color=COLOR_COST, linewidth=_DT_LW_PRIMARY, label="コスト")
        ax.plot(df["日"], _chart_profit / 10000, color=COLOR_PROFIT, linewidth=_DT_LW_PRIMARY, label="運営貢献額")
        ax.axhline(y=0, color=_DT_TEXT_MUTED, linewidth=0.8)
        ax.set_xlabel("日")
        ax.set_ylabel("金額（万円）")
        ax.set_xlim(1, days_in_month)
        _bc_apply_chart_style(ax)
        _leg_fin = ax.legend(loc="upper left", ncol=3, frameon=False)
        _bc_style_legend(_leg_fin)
        st.pyplot(fig)
        plt.close(fig)

        # --- 累積運営貢献額推移（月全体・予測線・目標ライン付き）---
        _cum_profit = _chart_profit.cumsum()
        _cum_values = (_cum_profit / 10000).values  # 万円単位
        _days_values = df["日"].values
        _days_elapsed = len(_days_values)
        _end_day = int(_calendar_month_days) if '_calendar_month_days' in dir() else int(days_in_month)

        _bc_section_title("累積運営貢献額推移（月全体・予測線・目標レンジ付き）", icon="📊")
        fig, ax = plt.subplots(figsize=(12, 3))
        fig.patch.set_alpha(0.0)
        # 実績の塗りつぶし
        ax.fill_between(
            _days_values, _cum_values, 0,
            where=_cum_values >= 0, color=COLOR_PROFIT, alpha=0.25,
        )
        ax.fill_between(
            _days_values, _cum_values, 0,
            where=_cum_values < 0, color=COLOR_A, alpha=0.25,
        )
        # 実績ライン
        ax.plot(_days_values, _cum_values, color=COLOR_PROFIT, linewidth=_DT_LW_PRIMARY, label="実績（累積）")

        # --- 月末までの予測と目標ラインを描画 ---
        _projection_text = []
        if _days_elapsed >= 1 and _end_day > _days_elapsed:
            # ① 現ペース維持の月末予測値
            _current_pace_per_day = _cum_values[-1] / _days_elapsed  # 万円/日
            _projected_end = _cum_values[-1] + _current_pace_per_day * (_end_day - _days_elapsed)

            _proj_x = [_days_values[-1], _end_day]
            _proj_y = [_cum_values[-1], _projected_end]
            ax.plot(_proj_x, _proj_y,
                    linestyle="--", linewidth=2.5, color=COLOR_PROFIT, alpha=0.6,
                    label=f"現ペース予測 → 月末 約{_projected_end:,.0f}万円")
            ax.scatter([_end_day], [_projected_end], s=80, color=COLOR_PROFIT, zorder=5)
            _projection_text.append(f"現ペース予測 **{_projected_end:,.0f}万円**")

            # ② 目標稼働率レンジでの月末見込み（90%/95%）
            #    目標達成時の1日あたり平均運営貢献額 ≈ ベッド数 × 目標稼働率 × 平均運営貢献額/床日
            #    ここでは、実績の「在院患者あたり運営貢献額」をそのまま使い、患者数を稼働率から逆算
            try:
                _avg_profit_per_patient = (
                    _chart_profit.sum() / df["在院患者数"].sum()
                    if df["在院患者数"].sum() > 0 else 0
                )  # 円/人
            except Exception:
                _avg_profit_per_patient = 0

            if _avg_profit_per_patient > 0:
                # 目標下限（90%）で月全体を運用した場合
                _target_lo_daily = _view_beds * target_lower * _avg_profit_per_patient / 10000  # 万円/日
                _target_hi_daily = _view_beds * target_upper * _avg_profit_per_patient / 10000
                _target_lo_end = _target_lo_daily * _end_day
                _target_hi_end = _target_hi_daily * _end_day

                # 目標レンジ帯（1日目から月末まで線形増加）
                _target_x = [1, _end_day]
                _target_lo_y = [_target_lo_daily, _target_lo_end]
                _target_hi_y = [_target_hi_daily, _target_hi_end]

                ax.fill_between(
                    _target_x, _target_lo_y, _target_hi_y,
                    color="#F39C12", alpha=0.15,
                    label=f"目標レンジ ({target_lower*100:.0f}-{target_upper*100:.0f}%稼働)",
                )
                ax.plot(_target_x, _target_lo_y,
                        linestyle=":", linewidth=1.5, color="#F39C12", alpha=0.7)
                ax.plot(_target_x, _target_hi_y,
                        linestyle=":", linewidth=1.5, color="#F39C12", alpha=0.7)

                # 目標下限の月末値をマーク
                ax.scatter([_end_day], [_target_lo_end], s=60, color="#E67E22", zorder=5, marker="s")

                # --- ラベル配置: 値の大小順に上下を決める ---
                # 高い値のラベルを上に、低い値のラベルを下に配置する
                if _target_lo_end >= _projected_end:
                    # 目標下限 > 実績予測 → 目標下限を上、実績予測を下
                    _upper_xy = (_end_day, _target_lo_end)
                    _upper_text = f"目標下限{target_lower*100:.0f}%\n{_target_lo_end:,.0f}万円"
                    _upper_color = "#D35400"
                    _upper_edge = "#E67E22"
                    _lower_xy = (_end_day, _projected_end)
                    _lower_text = f"実績ペース予測\n{_projected_end:,.0f}万円"
                    _lower_color = COLOR_PROFIT
                    _lower_edge = COLOR_PROFIT
                    _upper_fontsize = 8
                    _lower_fontsize = 9
                else:
                    # 実績予測 > 目標下限 → 実績予測を上、目標下限を下
                    _upper_xy = (_end_day, _projected_end)
                    _upper_text = f"実績ペース予測\n{_projected_end:,.0f}万円"
                    _upper_color = COLOR_PROFIT
                    _upper_edge = COLOR_PROFIT
                    _lower_xy = (_end_day, _target_lo_end)
                    _lower_text = f"目標下限{target_lower*100:.0f}%\n{_target_lo_end:,.0f}万円"
                    _lower_color = "#D35400"
                    _lower_edge = "#E67E22"
                    _upper_fontsize = 9
                    _lower_fontsize = 8

                ax.annotate(
                    _upper_text,
                    xy=_upper_xy,
                    xytext=(-10, 12), textcoords="offset points",
                    fontsize=_upper_fontsize, fontweight="bold", color=_upper_color,
                    ha="right", va="bottom",
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=_upper_edge, alpha=0.9),
                )
                ax.annotate(
                    _lower_text,
                    xy=_lower_xy,
                    xytext=(-10, -12), textcoords="offset points",
                    fontsize=_lower_fontsize, fontweight="bold", color=_lower_color,
                    ha="right", va="top",
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=_lower_edge, alpha=0.9),
                )

                # 差額の計算
                _gap_to_target_lo = _projected_end - _target_lo_end
                _gap_to_target_hi = _projected_end - _target_hi_end
                _projection_text.append(
                    f"目標下限({target_lower*100:.0f}%)比 **{_gap_to_target_lo:+,.0f}万円** / "
                    f"目標上限({target_upper*100:.0f}%)比 **{_gap_to_target_hi:+,.0f}万円**"
                )
            else:
                # 目標レンジが計算できない場合: 実績予測ラベルのみ表示
                ax.annotate(
                    f"実績ペース予測\n{_projected_end:,.0f}万円",
                    xy=(_end_day, _projected_end),
                    xytext=(-10, 12), textcoords="offset points",
                    fontsize=9, fontweight="bold", color=COLOR_PROFIT,
                    ha="right", va="bottom",
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=COLOR_PROFIT, alpha=0.9),
                )

        ax.axhline(y=0, color=_DT_TEXT_MUTED, linewidth=0.8)
        ax.set_xlabel("日")
        ax.set_ylabel("累積運営貢献額（万円）")
        ax.set_xlim(1, _end_day + 0.5)
        _bc_apply_chart_style(ax)
        _leg_cum = ax.legend(loc="upper left", frameon=False)
        _bc_style_legend(_leg_cum)
        st.pyplot(fig)
        plt.close(fig)

        # 予測値の要約キャプション
        if _projection_text:
            st.caption("📊 " + " ｜ ".join(_projection_text))

        # --- フェーズ別運営貢献額の内訳 ---
        _bc_section_title("フェーズ別運営貢献額の内訳", icon="📊")
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
        st.caption(f"💡 運営貢献額の {_max_phase[1]:.0f}% は {_phase_desc[_max_phase[0]]} が創出")

        # --- 🌙 夜勤安全ライン × 稼働率シミュレーション ---
        with st.expander("🌙 夜勤安全ライン × 稼働率シミュレーション", expanded=False):

            _nc_cols = st.columns([1, 1, 2])

            with _nc_cols[0]:
                st.markdown("**🌙 夜勤の設定**")
                _nc_nightly = st.slider(
                    "夜勤安全ライン（在院数）",
                    min_value=int(_view_beds * 0.70),
                    max_value=int(_view_beds * 0.98),
                    value=int(_view_beds * 0.87),
                    step=1,
                    help="夜勤者が無理なく対応できる在院患者数",
                    key="nc_nightly_slider"
                )
                _nc_empty_night = _view_beds - _nc_nightly
                st.caption(f"夜間空床: {_nc_empty_night}床（急変時ベッド確保）")

            with _nc_cols[1]:
                st.markdown("**☀️ 日中の回転目標**")
                _nc_wd_dis = st.slider(
                    "平日の退院目標（人/日）",
                    min_value=1,
                    max_value=12,
                    value=7,
                    step=1,
                    help="退院1人＋入院1人のペアリングが前提",
                    key="nc_weekday_dis_slider"
                )
                _nc_we_dis = st.slider(
                    "土日の退院（人/日）",
                    min_value=0,
                    max_value=4,
                    value=1,
                    step=1,
                    help="土曜のみ2組・日曜0の場合は平均1を入力",
                    key="nc_weekend_dis_slider"
                )
                _nc_monthly_admits = _nc_wd_dis * 20 + _nc_we_dis * 10
                st.caption(f"月間入院数: 平日{_nc_wd_dis}×20日 + 土日{_nc_we_dis}×10日 = {_nc_monthly_admits}人（当院の現状≒150人）\n※土曜2組・日曜0の場合、平均1人/日で入力")

            with _nc_cols[2]:
                # Calculate results
                _nc_wd_occ = (_nc_nightly + _nc_wd_dis) / _view_beds * 100
                _nc_we_occ = (_nc_nightly + _nc_we_dis) / _view_beds * 100
                _nc_monthly_occ = (_nc_wd_occ * 20 + _nc_we_occ * 10) / 30

                # Current values for comparison
                _nc_current_occ = _gauge_occ if '_gauge_occ' in dir() else 88.8
                _nc_occ_improvement = _nc_monthly_occ - _nc_current_occ
                _nc_annual_improvement = _nc_occ_improvement * float(st.session_state.get("annual_value_1pct", 1199))

                # Bonus calculation
                _nc_bonus_per_person = _nc_annual_improvement * 10000 * 0.58 / 290  # yen

                st.markdown("**📊 シミュレーション結果**")

                _rc1, _rc2 = st.columns(2)
                with _rc1:
                    st.metric("平日稼働率", f"{_nc_wd_occ:.1f}%",
                              delta=f"夜{_nc_nightly}人+退院{_nc_wd_dis}人")
                    st.metric("土日稼働率", f"{_nc_we_occ:.1f}%",
                              delta=f"夜{_nc_nightly}人+退院{_nc_we_dis}人")
                with _rc2:
                    st.metric("月平均稼働率", f"{_nc_monthly_occ:.1f}%",
                              delta=f"{_nc_occ_improvement:+.1f}pt",
                              delta_color="normal" if _nc_occ_improvement >= 0 else "inverse")
                    st.metric("年間改善額", f"{_nc_annual_improvement:+,.0f}万円",
                              delta=f"一人あたり +{_nc_bonus_per_person:,.0f}円/年" if _nc_bonus_per_person > 0 else f"一人あたり {_nc_bonus_per_person:,.0f}円/年")

                # Visual comparison
                if _nc_occ_improvement > 0:
                    _bc_alert(
                        f"🌙 <b>夜勤在院{_nc_nightly}人</b>（現状より楽）で、"
                        f"稼働率<b>{_nc_monthly_occ:.1f}%</b>（+{_nc_occ_improvement:.1f}pt）。<br>"
                        f"年間 <b>{_nc_annual_improvement:,.0f}万円</b> の改善。"
                        f"職員一人あたり年間 <b>+{_nc_bonus_per_person:,.0f}円</b>"
                        f"（賞与約+{_nc_bonus_per_person/50000:.0f}%相当）。<br>"
                        f"<b>条件:</b> 平日の退院を{_nc_wd_dis}人/日に増やし、退院当日に入院を受ける（入退院ペアリング）。",
                        severity="success",
                    )
                elif _nc_occ_improvement < -1:
                    _bc_alert(
                        f"⚠️ この設定では稼働率が{_nc_occ_improvement:+.1f}pt低下します。"
                        f"夜勤安全ラインを上げるか、日中退院を増やしてください。",
                        severity="warning",
                    )
                else:
                    _bc_alert(
                        "ℹ️ 現状維持に近い設定です。日中退院を増やすとさらに改善します。",
                        severity="info",
                    )

            # What-if table
            st.markdown(f"**📋 退院数による改善効果（夜勤在院{_nc_nightly}人固定）**")

            _nc_table_data = []
            for d in range(0, 11):
                _d_occ = (_nc_nightly + d) / _view_beds * 100
                _d_monthly = (_d_occ * 20 + _nc_we_occ * 10) / 30
                _d_imp = (_d_monthly - _nc_current_occ) * float(st.session_state.get("annual_value_1pct", 1199))
                _d_bonus = _d_imp * 10000 * 0.58 / 290
                _nc_table_data.append({
                    "平日退院数": f"{d}人/日",
                    "平日稼働率": f"{_d_occ:.1f}%",
                    "月平均稼働率": f"{_d_monthly:.1f}%",
                    "年間改善額": f"{_d_imp:+,.0f}万円",
                    "一人あたり": f"{_d_bonus:+,.0f}円/年",
                })

            _nc_table_df = pd.DataFrame(_nc_table_data)
            st.dataframe(_nc_table_df, use_container_width=True, hide_index=True)

            st.caption(
                "※ 前提: 退院した日に入院を受ける（入退院ペアリング）。"
                "人件費率58%・職員290名で計算。稼働率1%の年間価値は左サイドバーの値を使用。"
            )


# ===== タブ4: 運営改善アラート =====
# TODO: views/alerts_view.py に描画ロジックを分離する（依存変数が多いため段階的に実施）
if "🚨 運営改善アラート" in _tab_idx and _data_ready:
    with tabs[_tab_idx["🚨 運営改善アラート"]]:
        st.subheader("運営改善アラート")
        st.caption("※ このタブの平均在院日数は**当月実績**です。制度管理タブの rolling 90日 LOS とは算出期間が異なります。")
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
        st.dataframe(styled, use_container_width=True, height=400)

        # --- 目標レンジ内日数 ---
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
        st.markdown("**ベッドコントロール優先原則**")
        st.info(
            f"1️⃣ **稼働率90-95%維持** — 1床/日≈{_daily_profit_per_bed/10000:.1f}万円  \n"
            f"2️⃣ **在院日数{_max_avg_los}日以内で戦略的在院調整** — C群{phase_c_rev - phase_c_cost:,.0f}円/日  \n"
            "3️⃣ **運営貢献額を減らさない** — 退院を急ぐのは満床で入院を断る場合のみ"
        )

        # --- 推奨アクション ---
        st.markdown("**推奨アクション**")
        avg_occ = summary["平均稼働率"]
        if avg_occ < target_lower * 100:
            st.error(
                f"⚠️ 平均稼働率 {avg_occ:.1f}% が目標下限 {target_lower*100:.0f}% を下回っています。\n\n"
                "**最優先:** 入院促進策の強化\n"
                "- ① 予定入院の前倒しを外来担当医へ依頼\n"
                "- ② 連携室へ依頼：紹介元クリニック・病院へ空床受入れ可能を発信\n"
                "- ③ 外来担当医に入院推奨閾値の引き下げを相談\n\n"
                f"**注意:** C群患者は在院継続で運営貢献額確保。空床1床/日 ≈ {_daily_profit_per_bed/10000:.1f}万円の影響額。"
                f"平均在院日数{_max_avg_los}日以内であれば戦略的在院調整で稼働率を維持する。"
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
                    f"**判断:** 平均在院日数{_max_avg_los}日以内ならC群の戦略的在院調整で稼働率維持を優先。"
                    "在院継続で運営貢献額28,900円/日を確保。"
                )

        # --- 平均在院日数 算定基準クリア計画（病棟別に判定・各病棟個別表示） ---
        # ⚠️ 施設基準は各病棟ごとに満たす必要があるため、超過している病棟ごとに
        # クリア計画を表示する。「全体」表示時でも病棟別に表示する。

        def _render_clearance_plan(ward_label, ward_df, ward_summary, max_avg_los):
            """指定病棟のクリア計画を計算・表示する。基準超過時のみ表示。"""
            try:
                ward_los = ward_summary.get("平均在院日数", 0)
                los_over = ward_los - max_avg_los
                if los_over <= 0:
                    return False  # 表示なし

                if not (_calendar_month_days > days_in_month):
                    return False

                days_elapsed_local = days_in_month
                days_left = _calendar_month_days - days_elapsed_local
                total_adm = ward_summary.get("月間入院数", 0)
                total_dis = ward_summary.get("月間退院数", 0)

                half_turnover = (total_adm + total_dis) / 2
                patient_days_past = ward_los * half_turnover

                # 直近の在院患者数・C群数
                tp_col = "在院患者数" if "在院患者数" in ward_df.columns else ("total_patients" if "total_patients" in ward_df.columns else None)
                c_col = "C群_患者数" if "C群_患者数" in ward_df.columns else ("phase_c_count" if "phase_c_count" in ward_df.columns else None)
                ward_beds_local = get_ward_beds(ward_label) if ward_label in ("5F", "6F") else _TOTAL_BEDS_METRIC
                last_patients = int(ward_df[tp_col].iloc[-1]) if tp_col else ward_beds_local
                last_c = int(ward_df[c_col].iloc[-1]) if c_col else 0

                daily_adm = total_adm / max(days_elapsed_local, 1)
                daily_dis = total_dis / max(days_elapsed_local, 1)
                adm_remaining = round(daily_adm * days_left)
                dis_remaining_base = round(daily_dis * days_left)

                pd_remaining_base = last_patients * days_left
                pd_month_base = patient_days_past + pd_remaining_base
                adm_month = total_adm + adm_remaining
                dis_month_base = total_dis + dis_remaining_base
                ht_month_base = (adm_month + dis_month_base) / 2
                los_month_base = pd_month_base / max(ht_month_base, 1)

                avg_save_days = days_left * 0.6
                n_needed = 0
                for n in range(1, last_c + 20):
                    pd_saved = n * avg_save_days
                    new_pd = pd_month_base - pd_saved
                    new_dis = dis_month_base + n
                    new_ht = (adm_month + new_dis) / 2
                    new_los = new_pd / max(new_ht, 1)
                    if new_los <= max_avg_los:
                        n_needed = n
                        break
                else:
                    n_needed = n

                st.markdown(f"**🚨 {ward_label}病棟 平均在院日数 {max_avg_los}日以内クリア計画**")
                st.error(
                    f"**現状**: 平均在院日数 **{ward_los}日**（基準 {max_avg_los}日以内を **+{los_over:.1f}日超過**）\n\n"
                    f"**月末予測（このままの場合）**: 約 **{los_month_base:.1f}日** — "
                    f"{'基準超過が継続' if los_month_base > max_avg_los else '自然に基準内に収まる見込み'}\n\n"
                    f"**必要な対策**: 残り **{days_left}日** でC群（在院15日以上）患者を "
                    f"**追加{n_needed}名** 退院させれば基準クリア見込み"
                )

                plan_col1, plan_col2 = st.columns(2)
                with plan_col1:
                    st.markdown("**退院計画シミュレーション**")
                    plan_rows = []
                    for pn in range(0, min(n_needed + 3, last_c + 1)):
                        pn_pd = pd_month_base - pn * avg_save_days
                        pn_dis = dis_month_base + pn
                        pn_ht = (adm_month + pn_dis) / 2
                        pn_los = pn_pd / max(pn_ht, 1)
                        pn_status = "✅ クリア" if pn_los <= max_avg_los else "❌ 超過"
                        plan_rows.append({
                            "C群追加退院数": f"{pn}名",
                            "予測平均在院日数": f"{pn_los:.1f}日",
                            "判定": pn_status,
                        })
                    st.dataframe(pd.DataFrame(plan_rows), hide_index=True, use_container_width=True)

                with plan_col2:
                    st.markdown("**退院候補の優先順位**")
                    st.markdown(
                        "1. **在院日数が最も長いC群患者**から順に退院調整\n"
                        "2. 退院先の確保状況を連携室に確認\n"
                        "3. 退院前カンファレンスを今週中に実施\n\n"
                        f"現在の{ward_label}のC群患者: **{last_c}名**\n\n"
                        f"このうち **{n_needed}名** の退院で基準クリア\n\n"
                        "**同時に新規入院の受入れ**（分母増加）も有効:\n"
                        f"- 現在の入院ペース: 約{daily_adm:.1f}名/日\n"
                        f"- 入院を増やすほど平均在院日数は下がる"
                    )

                st.caption(
                    f"※ 計算前提: 残り{days_left}日間の入院{adm_remaining}名・退院{dis_remaining_base}名（現ペース）"
                    f"＋C群追加退院による在院患者延日数の減少（退院1名あたり平均{avg_save_days:.0f}日分）"
                )
                return True
            except Exception:
                return False

        # 「全体」モード時: 各病棟のクリア計画を順次チェック・表示
        # 「病棟」モード時: その病棟のクリア計画のみ表示
        if _selected_ward_key == "全体":
            # 全体モードでも各病棟のサマリーから個別判定する
            if globals().get("_ward_data_available", False):
                _ward_dfs_plan = globals().get("_ward_raw_dfs", {})
                _ward_displays_plan = globals().get("_ward_display_dfs", {})
                for _w_label in ["5F", "6F"]:
                    _w_raw_df_plan = _ward_dfs_plan.get(_w_label) if _ward_dfs_plan else None
                    _w_disp_df_plan = _ward_displays_plan.get(_w_label) if _ward_displays_plan else None
                    if _w_raw_df_plan is None or len(_w_raw_df_plan) == 0:
                        continue
                    # 病棟別サマリーを再計算（厚労省公式）
                    _w_pd = float(_w_raw_df_plan["total_patients"].sum())
                    _w_adm = float(_w_raw_df_plan["new_admissions"].sum())
                    _w_dis_n = float(_w_raw_df_plan["discharges"].sum())
                    _w_los_denom = (_w_adm + _w_dis_n) / 2
                    _w_los = round(_w_pd / _w_los_denom, 1) if _w_los_denom > 0 else 0
                    _w_summary_plan = {
                        "平均在院日数": _w_los,
                        "月間入院数": int(_w_adm),
                        "月間退院数": int(_w_dis_n),
                    }
                    # 表示用 DataFrame: 在院患者数・C群_患者数 のフォールバック対応
                    _w_render_df = _w_disp_df_plan if _w_disp_df_plan is not None and len(_w_disp_df_plan) > 0 else _w_raw_df_plan
                    _render_clearance_plan(_w_label, _w_render_df, _w_summary_plan, _max_avg_los)
        else:
            # 病棟モード: その病棟のみ
            _render_clearance_plan(_selected_ward_key, df, summary, _max_avg_los)

        # --- 今日のアクションリスト ---
        st.markdown("**📋 今日のアクションリスト**")
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
            _action_items.append(f"🔴 空床{_last_empty}床（空床の影響額 約{_last_empty * int(_daily_rev_per_bed) // 10000:.0f}万円/日・今月残り{_remaining_days}日で約{_last_empty * int(_daily_rev_per_bed) * _remaining_days // 10000:.0f}万円）→ 外来へ予定入院前倒し依頼 / 連携室へ紹介元への空床発信依頼 / 外来担当医へ入院閾値引き下げ相談")
            _action_items.append("🔴 C群患者の戦略的在院調整 — 在院継続で運営貢献額確保し稼働率維持を優先")
        # 平均在院日数超過時のアクション（病棟別判定 — クリア計画は上のセクションに表示済み）
        # ※ ここでは「当月実績LOS」で判定する（制度管理タブのrolling 90日LOSとは異なる）
        # 各病棟ごとに判定し、超過していれば該当病棟のアクションを追加
        _alert_action_added = False
        if _calendar_month_days > days_in_month:
            # 選択ビューの平均在院日数で判定
            _view_avg_los = summary.get("平均在院日数", 0)
            _view_los_over = _view_avg_los - _max_avg_los
            if _view_los_over > 0 and _selected_ward_key in ("5F", "6F"):
                _action_items.append(
                    f"🚨 **{_selected_ward_key}病棟 当月平均在院日数{_view_avg_los}日（基準{_max_avg_los}日超過）** → C群退院調整を今週中に実施（クリア計画参照）"
                )
                _alert_action_added = True
            elif _selected_ward_key == "全体" and globals().get("_ward_data_available", False):
                # 全体モード: 各病棟を個別判定
                _ward_dfs_act = globals().get("_ward_raw_dfs", {})
                for _w_act in ["5F", "6F"]:
                    _w_df_act = _ward_dfs_act.get(_w_act) if _ward_dfs_act else None
                    if _w_df_act is None or len(_w_df_act) == 0:
                        continue
                    _w_pd_a = float(_w_df_act["total_patients"].sum())
                    _w_adm_a = float(_w_df_act["new_admissions"].sum())
                    _w_dis_a = float(_w_df_act["discharges"].sum())
                    _w_denom_a = (_w_adm_a + _w_dis_a) / 2
                    _w_los_a = round(_w_pd_a / _w_denom_a, 1) if _w_denom_a > 0 else 0
                    if _w_los_a > _max_avg_los:
                        _action_items.append(
                            f"🚨 **{_w_act}病棟 当月平均在院日数{_w_los_a}日（基準{_max_avg_los}日超過）** → C群退院調整を今週中に実施（クリア計画参照）"
                        )
                        _alert_action_added = True
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


# ===== 意思決定タブ群（「📊 今日の運営」「🔮 What-if・戦略」に分散配置） =====
# --- タブ5: 意思決定ダッシュボード ---
if "\U0001f3af 意思決定ダッシュボード" in _tab_idx:
    with tabs[_tab_idx["\U0001f3af 意思決定ダッシュボード"]]:
        if not _DECISION_SUPPORT_AVAILABLE:
            pass  # エラーメッセージはタブ外のセクションヘッダーで表示済み
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

                # --- 朝のブリーフィング: 指標の下ごしらえ ---
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

                # 稼働率の severity を目標レンジに合わせて決定（Hero カード用）
                if _br_occ < target_lower * 100:
                    _occ_severity = "warning"  # 目標下限未達
                    _occ_delta = f"目標 {target_lower*100:.0f}% 未達（-{target_lower*100 - _br_occ:.1f}pt）"
                elif _br_occ > target_upper * 100:
                    _occ_severity = "danger"  # 上限超過
                    _occ_delta = f"目標 {target_upper*100:.0f}% 超過（+{_br_occ - target_upper*100:.1f}pt）"
                else:
                    _occ_severity = "success"
                    _occ_delta = f"目標レンジ内（{target_lower*100:.0f}〜{target_upper*100:.0f}%）"

                # 空床の severity: 0 は危機、1-2 は注意、3以上はニュートラル
                if _br_empty <= 0:
                    _empty_severity = "danger"
                    _empty_delta = "満床 — 入院受け入れ困難"
                elif _br_empty <= 2:
                    _empty_severity = "warning"
                    _empty_delta = "余力わずか"
                else:
                    _empty_severity = "neutral"
                    _empty_delta = f"{_view_beds}床中"

                # 病棟ステータスの severity マッピング
                _status_severity_map = {
                    "healthy": "success",
                    "caution": "warning",
                    "warning": "warning",
                    "critical": "danger",
                }
                _status_severity = _status_severity_map.get(_br_score_label, "neutral")

                # 優先アクション（上位2件）— ブリーフィングとアラート両方で使う
                _br_top_actions = sorted(_actions, key=lambda a: a.get("priority", 99))[:2]
                _cat_labels = {"discharge": "退院", "admission": "入院", "hold": "保持", "alert": "警告"}

                # 向こう3日の見通し
                _forecast_3 = _forecast[:3]
                _forecast_labels = ["明日", "明後日", "3日後"]
                _fc_values = []
                _br_forecast_parts = []
                for _fi, _fc in enumerate(_forecast_3):
                    _fc_occ = _fc["predicted_occupancy"] * 100
                    _fc_values.append(_fc_occ)
                    _lbl = _forecast_labels[_fi] if _fi < len(_forecast_labels) else f"{_fi+1}日後"
                    _br_forecast_parts.append(f"{_lbl} {_fc_occ:.1f}%")
                _br_forecast_lines = " → ".join(_br_forecast_parts)

                if _fc_values and min(_fc_values) < target_lower * 100:
                    _br_forecast_comment = f"入院受入施策（外来への前倒し依頼・連携室経由の紹介促進）を強化しないと{target_lower*100:.0f}%を割る見込み"
                elif _fc_values and max(_fc_values) > target_upper * 100:
                    _br_forecast_comment = f"退院調整を進めないと{target_upper*100:.0f}%を超える見込み"
                else:
                    _br_forecast_comment = "目標レンジ内で推移する見込み"

                # -----------------------------------------------------------
                # Hero: 今朝の病棟状況（3 カード、数値を大きく・色で状態を示す）
                # -----------------------------------------------------------
                _bc_section_title("今朝の病棟状況", icon="\U0001f305")
                _hc1, _hc2, _hc3 = st.columns(3)
                with _hc1:
                    _bc_kpi_card(
                        "稼働率", f"{_br_occ:.1f}", "%",
                        delta=_occ_delta,
                        severity=_occ_severity,
                        size="lg",
                    )
                with _hc2:
                    _bc_kpi_card(
                        "空床", f"{_br_empty}", "床",
                        delta=_empty_delta,
                        severity=_empty_severity,
                        size="lg",
                    )
                with _hc3:
                    _bc_kpi_card(
                        "病棟ステータス", _br_score_ja, "",
                        delta=f"スコア {_br_score_numeric}点",
                        severity=_status_severity,
                        size="lg",
                    )

                # フェーズ構成は Hero のすぐ下で触る程度に（phase testid はここで保持）
                _phase_cols = st.columns(3)
                with _phase_cols[0]:
                    _bc_kpi_card(
                        "A群（急性期）", f"{_br_phase_a}", "名",
                        delta=f"{_br_pct_a:.0f}% 構成",
                        severity="neutral",
                        size="sm",
                    )
                with _phase_cols[1]:
                    _bc_kpi_card(
                        "B群（回復期）", f"{_br_phase_b}", "名",
                        delta=f"{_br_pct_b:.0f}% 構成",
                        severity="neutral",
                        size="sm",
                    )
                with _phase_cols[2]:
                    # C群カードに phase testid を埋め込む（E2E 互換）
                    # hidden div のテキストは A+B+C 合計（Playwright テストが参照）
                    _bc_kpi_card(
                        "C群（退院準備）", f"{_br_phase_c}", "名",
                        delta=f"{_br_pct_c:.0f}% 構成",
                        severity="neutral",
                        size="sm",
                        testid="phase",
                        testid_attrs={
                            "a": str(_br_phase_a),
                            "b": str(_br_phase_b),
                            "c": str(_br_phase_c),
                        },
                        testid_text=str(_br_phase_a + _br_phase_b + _br_phase_c),
                    )

                # -----------------------------------------------------------
                # 朝のブリーフィング: 優先アクション + 3日の見通しを1枚のアラートに
                # -----------------------------------------------------------
                _bc_section_title("朝のブリーフィング", icon="\U0001f304")
                _br_action_html = ""
                if _br_top_actions:
                    _br_action_items = []
                    for _i, _act in enumerate(_br_top_actions, 1):
                        _cat = _cat_labels.get(_act.get("category", ""), "")
                        _br_action_items.append(f"<li>[{_cat}] {_act['action']}</li>")
                    _br_action_html = "<ul style='margin:4px 0 8px 20px;padding:0;'>" + "".join(_br_action_items) + "</ul>"
                _briefing_html = (
                    f"<div style='font-weight:600;margin-bottom:6px;'>在院 {_br_patients}名 / 空床 {_br_empty}床 / 稼働率 {_br_occ:.1f}%</div>"
                    + (f"<div style='margin-top:6px;'><b>優先アクション</b></div>{_br_action_html}" if _br_action_html else "")
                    + f"<div style='margin-top:6px;'><b>向こう3日の見通し</b>：{_br_forecast_lines}</div>"
                    + f"<div style='color:#6B7280;margin-top:4px;font-size:13px;'>→ {_br_forecast_comment}</div>"
                )
                _briefing_severity_map = {
                    "healthy": "success",
                    "caution": "warning",
                    "warning": "warning",
                    "critical": "danger",
                }
                _bc_alert(_briefing_html, severity=_briefing_severity_map.get(_br_score_label, "info"))

                # 病棟状態詳細のサブ KPI（運営貢献額）
                _bc_section_title("詳細指標", icon="\U0001f4ca")
                _ws_c1, _ws_c2, _ws_c3 = st.columns(3)
                with _ws_c1:
                    _bc_kpi_card(
                        "ステータススコア", f"{_ward_status['score_numeric']}", "点",
                        severity=_status_severity,
                        size="md",
                    )
                with _ws_c2:
                    _bc_kpi_card(
                        "1床あたり運営貢献額",
                        fmt_yen(int(_ward_status.get('profit_per_bed', 0))), "",
                        severity="neutral",
                        size="md",
                    )
                with _ws_c3:
                    _bc_kpi_card(
                        "総在院患者数", f"{_br_patients}", "名",
                        delta=f"定床 {_view_beds}床",
                        severity="neutral",
                        size="md",
                    )

                if _ward_status.get("messages"):
                    with st.expander("病棟状態に関する補足メッセージ", expanded=False):
                        for _msg in _ward_status["messages"]:
                            st.markdown(f"- {_msg}")

                # --- 稼働率予測 ---
                _bc_section_title("稼働率予測（5日間）", icon="\U0001f4c8")

                fig, ax = plt.subplots(figsize=(12, 3))
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

                # --- 推奨アクション ---
                _bc_section_title("推奨アクション", icon="\U0001f3af")
                _cat_icons = {"discharge": "\U0001f504", "admission": "\U0001f4e5", "hold": "\u23f8\ufe0f", "alert": "\u26a0\ufe0f"}
                for _act in sorted(_actions, key=lambda a: a.get("priority", 99)):
                    _icon = _cat_icons.get(_act.get("category", ""), "")
                    _prio = _act.get("priority", 5)
                    if _prio == 1:
                        _sev = "danger"
                    elif _prio == 2:
                        _sev = "warning"
                    else:
                        _sev = "info"
                    _act_html = (
                        f"<div style='font-weight:600;margin-bottom:4px;'>{_icon} {_act['action']}</div>"
                        f"<div style='color:#6B7280;font-size:13px;'>期待効果: {_act.get('expected_impact', 'N/A')}</div>"
                    )
                    _bc_alert(_act_html, severity=_sev)

                # --- LOS最適化 ---
                _bc_section_title("平均在院日数 最適化分析", icon="\U0001f4cf")

                # 前提条件: 月間入院数をスライダーで変更可能にする
                _los_default_adm = _cli_params["monthly_admissions"]
                # 病棟切替でスライダーのデフォルト値をリセットするためキーに病棟名を含める
                _los_slider_key = f"los_monthly_adm_slider_{_selected_ward_key}"
                _los_monthly_adm = st.slider(
                    "月間入院数（この値を固定して平均在院日数を変化させます）",
                    min_value=50, max_value=300, value=int(_los_default_adm), step=5,
                    key=_los_slider_key,
                    help="月間入院数を変更するとグラフが再計算されます。当院の実績は約150名/月です。"
                )
                # スライダーの値で一時的にパラメータを上書き
                _los_params = dict(_cli_params)
                _los_params["monthly_admissions"] = _los_monthly_adm
                # LOS分析は常に月単位（30日）で計算する
                # ※シミュレーション日数（例: 17日）をそのまま使うと日次入院数が過大になり
                #   全パターンで稼働率100%になってしまう
                _los_params["days_in_month"] = 30

                st.caption(
                    f"前提: 月間入院数 **{_los_monthly_adm}名固定**。スライダーで変更可。"
                    f"推定稼働率はLittle's law×効率係数0.94で補正。"
                )

                _los_impact = simulate_los_impact(_raw_df, _los_params)
                _optimal_los = calculate_optimal_los_range(_raw_df, _los_params)

                # --- 2段グラフ: 上=運営貢献額変化、下=稼働率変化 ---
                fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 5), height_ratios=[3, 2])
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

                with st.expander("📖 このグラフの読み方"):
                    st.markdown(
                        "- **上段:** 運営貢献額の増減（青=プラス、赤=マイナス）\n"
                        "- **下段:** 推定稼働率（緑=目標内、黄=90%未満、赤=100%超）\n\n"
                        "**ポイント:** 稼働率100%未満では在院日数延長→空床減→貢献額増。"
                        "100%付近では入院を断るリスクあり。退院促進と入院確保はセットで検討。"
                    )

                _bc_alert(
                    f"<b>最適平均在院日数レンジ:</b> {_optimal_los['min_los']:.1f} 〜 {_optimal_los['max_los']:.1f} 日"
                    f"（最適値: {_optimal_los['optimal_los']} 日）<br>"
                    f"期待月次運営貢献額: {fmt_yen(_optimal_los['expected_monthly_profit'])}<br>"
                    f"現在の設定: {avg_los} 日",
                    severity="info",
                )

                # --- 病棟運営最適化アドバイザー ---
                _bc_section_title("病棟運営最適化アドバイザー", icon="\U0001f4b0")

                # 限界価値分析
                _marginal = calculate_marginal_bed_value(_cli_params)
                _gross_a = _marginal["phase_gross"]["A"]
                _gross_b = _marginal["phase_gross"]["B"]
                _gross_c = _marginal["phase_gross"]["C"]
                _lifetime = _marginal["new_admission_lifetime_profit"]
                _daily_avg = _marginal["new_admission_daily_avg"]
                _breakeven = _marginal["breakeven_days"]

                # 限界価値パネル
                st.markdown("**限界価値分析**")
                _mv_c1, _mv_c2, _mv_c3 = st.columns(3)
                with _mv_c1:
                    _bc_kpi_card(
                        "A群 運営貢献額/日", fmt_yen(int(_gross_a)), "",
                        severity="neutral", size="md",
                    )
                with _mv_c2:
                    _bc_kpi_card(
                        "B群 運営貢献額/日", fmt_yen(int(_gross_b)), "",
                        delta="安定貢献層",
                        severity="neutral", size="md",
                    )
                with _mv_c3:
                    _bc_kpi_card(
                        "C群 運営貢献額/日", fmt_yen(int(_gross_c)), "",
                        delta="最高効率",
                        severity="success", size="md",
                    )

                _mv_c4, _mv_c5, _mv_c6 = st.columns(3)
                with _mv_c4:
                    _bc_kpi_card(
                        "新規1名 生涯期待運営貢献額", fmt_yen(_lifetime), "",
                        severity="neutral", size="md",
                    )
                with _mv_c5:
                    _bc_kpi_card(
                        "新規1名 日平均運営貢献額", fmt_yen(_daily_avg), "",
                        severity="neutral", size="md",
                    )
                with _mv_c6:
                    _bc_kpi_card(
                        "損益分岐日数", f"{_breakeven}", "日",
                        severity="neutral", size="md",
                    )

                # C群 vs 新規の判断基準
                if _gross_c > _daily_avg:
                    _bc_alert(
                        f"<b>C群在院調整({fmt_yen(int(_gross_c))}/日) &gt; 新規平均({fmt_yen(_daily_avg)}/日)</b><br>"
                        f"差額 +{fmt_yen(int(_gross_c - _daily_avg))}/日 → "
                        f"空床がある限りC群は持たせる方が得。退院させるのは満床で入院を断る場合のみ。",
                        severity="warning",
                    )
                else:
                    _bc_alert(
                        f"<b>新規平均({fmt_yen(_daily_avg)}/日) &ge; C群在院調整({fmt_yen(int(_gross_c))}/日)</b><br>"
                        f"→ 回転させて新規を入れる方が効率的。",
                        severity="success",
                    )

                # 今日の最適プラン
                _bc_section_title("今日の最適プラン", icon="\U0001f4c5")

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
                    f"<b>推奨: C群退院 {_rec['c_discharge']}名"
                )
                if _rec["b_discharge"] > 0:
                    _rec_text += f" / B群退院 {_rec['b_discharge']}名"
                _rec_text += f" / 新規入院 {_rec['new_admissions']}名</b>"

                if _rec["total_discharge"] == 0:
                    _bc_alert(_rec_text, severity="success")
                else:
                    _bc_alert(_rec_text, severity="warning")

                # 理由
                for _r in _opt_plan["reasoning"]:
                    st.markdown(f"- {_r}")

                # 経済効果 — 日次純効果を Hero 的に強調
                _net_val = _econ["daily_net_impact"]
                _net_sev = "success" if _net_val > 0 else ("danger" if _net_val < 0 else "neutral")
                _econ_cols = st.columns(4)
                with _econ_cols[0]:
                    _lost = _econ["daily_lost_profit"]
                    _bc_kpi_card(
                        "退院による運営貢献額減",
                        fmt_yen(_lost), "",
                        delta=(f"-{fmt_yen(_lost)}" if _lost > 0 else "0"),
                        severity=("warning" if _lost > 0 else "neutral"),
                        size="md",
                    )
                with _econ_cols[1]:
                    _bc_kpi_card(
                        "新規入院の初日運営貢献額",
                        fmt_yen(_econ["daily_gained_profit"]), "",
                        severity="neutral",
                        size="md",
                    )
                with _econ_cols[2]:
                    _bc_kpi_card(
                        "日次純効果",
                        fmt_yen(_net_val), "",
                        delta=f"{_net_val:+,}円",
                        severity=_net_sev,
                        size="md",
                    )
                with _econ_cols[3]:
                    _bc_kpi_card(
                        "新規の将来期待運営貢献額",
                        fmt_yen(_econ["future_gain_from_new"]), "",
                        severity="neutral",
                        size="md",
                    )

                # 実施後の状態
                st.markdown(
                    f"**実施後:** 在院{_aft['total']}名 / "
                    f"稼働率{_aft['occupancy']*100:.1f}%"
                )

                # 需要別シミュレーション（詳細 — expander に収納）
                _bc_section_title("需要別シミュレーション", icon="\U0001f50d")
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
                st.dataframe(_demand_df, use_container_width=True, hide_index=True)

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
                    _bc_alert(f"<b>ポイント:</b> 需要{_threshold}名以上でC群退院が必要になります", severity="info")
                else:
                    _bc_alert("<b>ポイント:</b> 現在の空床数では需要15名まで退院調整不要です", severity="info")

# --- タブ6: What-if分析（シミュレーションモードのみ） ---
if "\U0001f52e What-if分析" in _tab_idx:
    with tabs[_tab_idx["\U0001f52e What-if分析"]]:
        if not _DECISION_SUPPORT_AVAILABLE:
            pass  # エラーメッセージはタブ外のセクションヘッダーで表示済み
        else:
            st.subheader("\U0001f52e What-if分析")
            st.caption("過去の任意の日に戻って「もしこうしていたら？」を試せます。")
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
                    _bc_section_title("入力条件", icon="📅")
                    st.caption("過去の任意の日を選び、退院・入院の人数を変えると稼働率や貢献額がどう変わるかシミュレーションします。")

                    with st.container(border=True):
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
                            _bc_kpi_card(
                                label="在院患者数",
                                value=str(_wi_cur_total),
                                unit="名",
                                severity="neutral",
                                size="sm",
                            )
                        with _state_cols[1]:
                            _cur_occ_pct = _wi_cur_occ * 100
                            _cur_sev = "success" if target_lower * 100 <= _cur_occ_pct <= target_upper * 100 else (
                                "warning" if _cur_occ_pct < target_lower * 100 else "danger"
                            )
                            _bc_kpi_card(
                                label="稼働率",
                                value=f"{_cur_occ_pct:.1f}",
                                unit="%",
                                severity=_cur_sev,
                                size="sm",
                            )
                        with _state_cols[2]:
                            _bc_kpi_card(
                                label="A群（急性期）",
                                value=str(_wi_cur_a),
                                unit="名",
                                severity="neutral",
                                size="sm",
                            )
                        with _state_cols[3]:
                            _bc_kpi_card(
                                label="B群（回復期）",
                                value=str(_wi_cur_b),
                                unit="名",
                                severity="neutral",
                                size="sm",
                            )
                        with _state_cols[4]:
                            _bc_kpi_card(
                                label="C群（退院準備）",
                                value=str(_wi_cur_c),
                                unit="名",
                                severity="neutral",
                                size="sm",
                            )

                        # プリセットの pending 適用（ウィジェット作成前に行う必要がある）
                        # Streamlit の制約: ウィジェットキーに紐づく session_state は
                        # ウィジェット作成後に書き込めないため、pending フラグ方式で対応
                        if "_wi_pending_preset" in st.session_state:
                            _pvals_pending = st.session_state.pop("_wi_pending_preset")
                            st.session_state["wi_mixed_da"] = min(_pvals_pending[0], _wi_cur_a)
                            st.session_state["wi_mixed_db"] = min(_pvals_pending[1], _wi_cur_b)
                            st.session_state["wi_mixed_dc"] = min(_pvals_pending[2], _wi_cur_c)
                            _remaining_pp = _wi_cur_total - (
                                min(_pvals_pending[0], _wi_cur_a)
                                + min(_pvals_pending[1], _wi_cur_b)
                                + min(_pvals_pending[2], _wi_cur_c)
                            )
                            _avail_pp = max(0, _cli_params["num_beds"] - max(_remaining_pp, 0))
                            st.session_state["wi_mixed_new"] = min(_pvals_pending[3], _avail_pp)

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
                                if st.button(_pname, key=f"preset_{_pi}", use_container_width=True):
                                    # pending フラグで保存 → 次回 rerun 時に
                                    # ウィジェット作成前に適用される
                                    st.session_state["_wi_pending_preset"] = _pvals
                                    st.rerun()

                    if st.button("シナリオ実行", key="btn_whatif_mixed", type="primary"):
                        _mix_result = whatif_mixed_scenario(
                            _raw_df, _wi_day - 1, _cli_params,
                            discharge_a=_wi_da, discharge_b=_wi_db, discharge_c=_wi_dc,
                            new_admissions=_wi_new_adm,
                        )

                        _bc_section_title(f"結果: {_wi_date_label} の実績 → もしこうしていたら", icon="📊")
                        _mc1, _mc2 = st.columns(2)
                        _bl = _mix_result["baseline"]
                        _sc = _mix_result["scenario"]
                        _df_diff = _mix_result["diff"]

                        # severity 判定ヘルパー（稼働率）
                        def _occ_severity(occ_pct: float) -> str:
                            if target_lower * 100 <= occ_pct <= target_upper * 100:
                                return "success"
                            if occ_pct < target_lower * 100:
                                return "warning"
                            return "danger"

                        # severity 判定ヘルパー（改善方向）
                        def _dir_severity(diff_val: float) -> str:
                            if diff_val > 0:
                                return "success"
                            if diff_val < 0:
                                return "danger"
                            return "neutral"

                        with _mc1:
                            st.markdown("**Before（現状）**")
                            _bl_occ_pct = _bl["occupancy"] * 100
                            _bc_kpi_card(
                                label="稼働率",
                                value=f"{_bl_occ_pct:.1f}",
                                unit="%",
                                severity=_occ_severity(_bl_occ_pct),
                                size="sm",
                            )
                            _bc_kpi_card(label="在院患者数", value=str(_bl["total"]), unit="名", severity="neutral", size="sm")
                            _bc_kpi_card(label="A群", value=str(_bl["a"]), unit="名", severity="neutral", size="sm")
                            _bc_kpi_card(label="B群", value=str(_bl["b"]), unit="名", severity="neutral", size="sm")
                            _bc_kpi_card(label="C群", value=str(_bl["c"]), unit="名", severity="neutral", size="sm")
                            _bc_kpi_card(
                                label="日次運営貢献額",
                                value=fmt_yen(_bl["daily_profit"]),
                                severity="neutral",
                                size="sm",
                            )

                        with _mc2:
                            st.markdown("**After（シナリオ後）**")
                            _sc_occ_pct = _sc["occupancy"] * 100
                            _occ_diff_pct = _df_diff["occupancy"] * 100
                            _bc_kpi_card(
                                label="稼働率",
                                value=f"{_sc_occ_pct:.1f}",
                                unit="%",
                                delta=f"{_occ_diff_pct:+.1f}%",
                                severity=_occ_severity(_sc_occ_pct),
                                size="sm",
                            )
                            _bc_kpi_card(
                                label="在院患者数",
                                value=str(_sc["total"]),
                                unit="名",
                                delta=f"{_df_diff['total']:+d}名",
                                severity="neutral",
                                size="sm",
                            )
                            _bc_kpi_card(
                                label="A群",
                                value=str(_sc["a"]),
                                unit="名",
                                delta=f"{_sc['a'] - _bl['a']:+d}名",
                                severity="neutral",
                                size="sm",
                            )
                            _bc_kpi_card(
                                label="B群",
                                value=str(_sc["b"]),
                                unit="名",
                                delta=f"{_sc['b'] - _bl['b']:+d}名",
                                severity="neutral",
                                size="sm",
                            )
                            _bc_kpi_card(
                                label="C群",
                                value=str(_sc["c"]),
                                unit="名",
                                delta=f"{_sc['c'] - _bl['c']:+d}名",
                                severity="neutral",
                                size="sm",
                            )
                            _profit_delta_val = _df_diff["daily_profit"]
                            _profit_delta_str = f"+{fmt_yen(int(_profit_delta_val))}" if _profit_delta_val >= 0 else f"-{fmt_yen(abs(int(_profit_delta_val)))}"
                            _bc_kpi_card(
                                label="日次運営貢献額",
                                value=fmt_yen(_sc["daily_profit"]),
                                delta=_profit_delta_str,
                                severity=_dir_severity(_profit_delta_val),
                                size="lg",
                            )

                        # フェーズ構成比 Before/After 棒グラフ
                        _bc_section_title("フェーズ構成比の変化", icon="📊")
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
                        _bc_section_title("判定", icon="💡")
                        for _msg in _mix_result["messages"]:
                            if _msg.startswith("✅"):
                                _bc_alert(_msg, severity="success")
                            else:
                                _bc_alert(_msg, severity="warning")

                # ==================================================================
                # 週間退院計画
                # ==================================================================
                elif _scenario_type == "週間退院計画":
                    _bc_section_title("入力条件", icon="📅")
                    st.caption("7日間の退院・入院計画を入力し、日ごとの稼働率変化をシミュレーション。")

                    with st.container(border=True):
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
                            use_container_width=True,
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
                            _bc_section_title("日別シミュレーション結果", icon="📋")
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
                            st.dataframe(pd.DataFrame(_result_table), use_container_width=True, hide_index=True)

                            # 稼働率・運営貢献額推移グラフ
                            _bc_section_title("稼働率・運営貢献額推移", icon="📊")
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
                            _bc_section_title("週間サマリー", icon="📅")
                            _ws1, _ws2, _ws3, _ws4 = st.columns(4)
                            _avg_occ_pct = _w_summary["avg_occupancy"] * 100
                            _avg_occ_sev = (
                                "success" if target_lower * 100 <= _avg_occ_pct <= target_upper * 100
                                else ("warning" if _avg_occ_pct < target_lower * 100 else "danger")
                            )
                            with _ws1:
                                _bc_kpi_card(label="退院合計", value=str(_w_summary["total_discharge"]), unit="名", severity="neutral")
                            with _ws2:
                                _bc_kpi_card(label="入院合計", value=str(_w_summary["total_admission"]), unit="名", severity="neutral")
                            with _ws3:
                                _bc_kpi_card(
                                    label="平均稼働率",
                                    value=f"{_avg_occ_pct:.1f}",
                                    unit="%",
                                    severity=_avg_occ_sev,
                                )
                            with _ws4:
                                _total_profit_sev = "success" if _w_summary["total_profit"] > 0 else ("danger" if _w_summary["total_profit"] < 0 else "neutral")
                                _bc_kpi_card(
                                    label="運営貢献額合計",
                                    value=fmt_yen(_w_summary["total_profit"]),
                                    severity=_total_profit_sev,
                                )

                # ==================================================================
                # 入院需要変動シナリオ
                # ==================================================================
                else:
                    _bc_section_title("入力条件", icon="📈")
                    st.caption("GW明け・お盆等の入院需要変動が稼働率に与える影響をシミュレーション。")

                    with st.container(border=True):
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

                        _bc_section_title("結果: 需要変動の影響", icon="📊")
                        _sc1, _sc2 = st.columns(2)
                        _s_bl_occ_pct = _surge_result["baseline_occupancy"] * 100
                        _s_sc_occ_pct = _surge_result["scenario_occupancy"] * 100

                        def _s_occ_sev(occ_pct: float) -> str:
                            if target_lower * 100 <= occ_pct <= target_upper * 100:
                                return "success"
                            if occ_pct < target_lower * 100:
                                return "warning"
                            return "danger"

                        with _sc1:
                            st.markdown("**Before（現状）**")
                            _bc_kpi_card(
                                label="稼働率",
                                value=f"{_s_bl_occ_pct:.1f}",
                                unit="%",
                                severity=_s_occ_sev(_s_bl_occ_pct),
                            )
                            _bc_kpi_card(
                                label="月次運営貢献額",
                                value=fmt_yen(int(_surge_result["baseline_profit"])),
                                severity="neutral",
                            )
                        with _sc2:
                            st.markdown("**After（シナリオ）**")
                            _s_occ_delta = (_surge_result["scenario_occupancy"] - _surge_result["baseline_occupancy"]) * 100
                            _s_profit_delta = _surge_result["scenario_profit"] - _surge_result["baseline_profit"]
                            _bc_kpi_card(
                                label="稼働率",
                                value=f"{_s_sc_occ_pct:.1f}",
                                unit="%",
                                delta=f"{_s_occ_delta:+.1f}%",
                                severity=_s_occ_sev(_s_sc_occ_pct),
                            )
                            _s_profit_delta_str = f"+{fmt_yen(abs(int(_s_profit_delta)))}" if _s_profit_delta >= 0 else f"-{fmt_yen(abs(int(_s_profit_delta)))}"
                            _s_profit_sev = "success" if _s_profit_delta > 0 else ("danger" if _s_profit_delta < 0 else "neutral")
                            _bc_kpi_card(
                                label="月次運営貢献額",
                                value=fmt_yen(int(_surge_result["scenario_profit"])),
                                delta=_s_profit_delta_str,
                                severity=_s_profit_sev,
                                size="lg",
                            )

                        _s_rec = _surge_result.get("recommendation", "")
                        if "推奨" in _s_rec or "有効" in _s_rec:
                            _bc_alert(f"<strong>推奨:</strong> {_s_rec}", severity="success")
                        elif "注意" in _s_rec or "リスク" in _s_rec:
                            _bc_alert(f"<strong>注意:</strong> {_s_rec}", severity="warning")
                        else:
                            _bc_alert(f"<strong>分析結果:</strong> {_s_rec}", severity="info")

            # --- What-If シナリオ保存 ---
            if _SCENARIO_MANAGER_AVAILABLE:
                st.markdown("---")
                with st.expander("💾 このシナリオを保存"):
                    from datetime import datetime as _dt_now
                    _save_name = st.text_input("シナリオ名", value=f"whatif_{_dt_now.now().strftime('%m%d_%H%M')}", key="save_scenario_name")
                    _save_notes = st.text_area("メモ", value="", height=60, key="save_scenario_notes")
                    if st.button("保存", key="save_whatif_btn"):
                        _scenario_id = save_scenario(
                            name=_save_name,
                            scenario_type="what_if",
                            parameters={},
                            results={},
                            notes=_save_notes,
                        )
                        _bc_alert(f"保存しました: <strong>{_save_name}</strong>", severity="success")

# --- タブ: トレンド分析 ---
if "\U0001f4c8 トレンド分析" in _tab_idx:
    with tabs[_tab_idx["\U0001f4c8 トレンド分析"]]:
        if not _DECISION_SUPPORT_AVAILABLE:
            pass  # エラーメッセージはタブ外のセクションヘッダーで表示済み
        else:
            st.subheader("\U0001f4c8 トレンド分析")
            if _HELP_AVAILABLE and "tab_trends" in HELP_TEXTS:
                with st.expander("📖 このタブの見方と活用法"):
                    st.markdown(HELP_TEXTS["tab_trends"])

            # 安全チェック: _active_raw_dfが有効でない場合は処理をスキップ
            if not isinstance(_active_raw_df, pd.DataFrame) or len(_active_raw_df) == 0:
                _bc_alert(
                    "トレンド分析に必要なデータがありません。実績データを入力するかシミュレーションを実行してください。",
                    severity="danger",
                )
            else:
                _raw_df = _active_raw_df
                _cli_params = _active_cli_params

                _trend_window = st.slider("移動平均ウィンドウ（日）", 3, 14, value=7, key="trend_window")
                _trends = calculate_trends(_raw_df, _cli_params, window=_trend_window)

                _trend_arrows = {"rising": "\u2197\ufe0f 上昇", "falling": "\u2198\ufe0f 下降", "stable": "\u2192 安定"}

                # --- トレンドサマリー（冒頭アラート） ---
                _occ_dir = _trends.get("occupancy_trend", "stable")
                _profit_dir = _trends.get("profit_efficiency_trend", "stable")
                _b_dir = _trends.get("phase_b_trend", "stable")
                _alerts_preview = _trends.get("alerts", [])
                # 改善方向の判定: 稼働率上昇・運営貢献効率上昇・B群安定/上昇
                _improving = (_profit_dir == "rising") and (_b_dir != "falling")
                _worsening = (_profit_dir == "falling") or (_b_dir == "falling") or (_occ_dir == "falling")
                if _improving:
                    _summary_sev = "success"
                    _summary_icon = "📈"
                    _summary_msg = (
                        f"{_trend_window}日移動平均で <b>運営貢献効率が上昇</b>・B群安定 — 改善傾向にあります。"
                    )
                elif _worsening:
                    _summary_sev = "warning"
                    _summary_icon = "📉"
                    _reasons = []
                    if _profit_dir == "falling":
                        _reasons.append("運営貢献効率が下降")
                    if _b_dir == "falling":
                        _reasons.append("B群比率が下降")
                    if _occ_dir == "falling":
                        _reasons.append("稼働率が下降")
                    _summary_msg = (
                        f"{_trend_window}日移動平均で {'・'.join(_reasons)} — 早めの対策を検討してください。"
                    )
                else:
                    _summary_sev = "info"
                    _summary_icon = "➡️"
                    _summary_msg = (
                        f"{_trend_window}日移動平均で主要指標は <b>安定</b>しています。"
                    )
                _bc_alert(f"{_summary_icon} <b>トレンドサマリー</b>: {_summary_msg}", severity=_summary_sev)

                # --- KPI カード: 主要トレンドの方向性 ---
                _bc_section_title("主要トレンド", icon="🧭")
                _occ_ma = _trends.get("occupancy_ma", [])
                _ppb_ma_kpi = _trends.get("profit_per_bed_ma", [])
                _phase_b_ma_kpi = _trends.get("phase_b_ma", [])
                _occ_latest = (_occ_ma[-1] * 100) if _occ_ma else 0.0
                _ppb_latest = (_ppb_ma_kpi[-1] / 10000) if _ppb_ma_kpi else 0.0
                _b_latest = (_phase_b_ma_kpi[-1] * 100) if _phase_b_ma_kpi else 0.0

                def _trend_severity(direction: str, prefer_rising: bool) -> str:
                    """トレンド方向を severity に写像する。"""
                    if direction == "rising":
                        return "success" if prefer_rising else "warning"
                    if direction == "falling":
                        return "warning" if prefer_rising else "success"
                    return "neutral"

                _kpi_tr_c1, _kpi_tr_c2, _kpi_tr_c3 = st.columns(3)
                with _kpi_tr_c1:
                    _bc_kpi_card(
                        label="稼働率（移動平均）",
                        value=f"{_occ_latest:.1f}",
                        unit=" %",
                        delta=f"{_trend_arrows.get(_occ_dir, '')}（{_trend_window}日MA）",
                        severity=_trend_severity(_occ_dir, prefer_rising=True)
                        if _occ_latest < target_upper * 100 else ("warning" if _occ_dir == "rising" else "neutral"),
                    )
                with _kpi_tr_c2:
                    _bc_kpi_card(
                        label="1床あたり運営貢献額（移動平均）",
                        value=f"{_ppb_latest:,.2f}",
                        unit=" 万円/床",
                        delta=f"{_trend_arrows.get(_profit_dir, '')}（{_trend_window}日MA）",
                        severity=_trend_severity(_profit_dir, prefer_rising=True),
                    )
                with _kpi_tr_c3:
                    _bc_kpi_card(
                        label="B群構成比（移動平均）",
                        value=f"{_b_latest:.1f}",
                        unit=" %",
                        delta=f"{_trend_arrows.get(_b_dir, '')}（{_trend_window}日MA）",
                        severity=_trend_severity(_b_dir, prefer_rising=True),
                    )

                st.markdown("")  # 呼吸のための空行

                # --- 稼働率トレンド ---
                _bc_section_title("稼働率トレンド", icon="📊")
                _occ_trend_label = _trend_arrows.get(_trends.get("occupancy_trend", "stable"), _trends.get("occupancy_trend", ""))
                st.caption(f"トレンド: {_occ_trend_label}")

                fig, ax = plt.subplots(figsize=(12, 3))
                fig.patch.set_alpha(0.0)
                _daily_occ = [_raw_df.iloc[i]["occupancy_rate"] * 100 for i in range(len(_raw_df))]
                _days_range = list(range(1, len(_raw_df) + 1))
                ax.plot(_days_range, _daily_occ, color=_DT_TEXT_MUTED, linewidth=_DT_LW_AUX, alpha=0.7, label="日次実績")
                if _occ_ma:
                    _ma_start = len(_days_range) - len(_occ_ma)
                    _ma_days = _days_range[_ma_start:]
                    ax.plot(
                        _ma_days, [v * 100 for v in _occ_ma],
                        color=_DT_ACCENT, linewidth=_DT_LW_PRIMARY,
                        label=f"{_trend_window}日移動平均",
                    )
                ax.axhspan(
                    target_lower * 100, target_upper * 100,
                    alpha=0.10, color=_DT_WARNING,
                    label=f"目標レンジ ({target_lower*100:.0f}-{target_upper*100:.0f}%)",
                )
                ax.set_xlabel("日")
                ax.set_ylabel("稼働率 (%)")
                _bc_apply_chart_style(ax)
                _leg_occ = ax.legend(loc="lower right", frameon=False)
                _bc_style_legend(_leg_occ)
                st.pyplot(fig)
                plt.close(fig)

                # --- フェーズ構成比トレンド ---
                _bc_section_title("フェーズ構成比トレンド（移動平均）", icon="📉")
                _phase_a_label = _trend_arrows.get(_trends.get("phase_a_trend", "stable"), _trends.get("phase_a_trend", ""))
                _phase_b_label = _trend_arrows.get(_trends.get("phase_b_trend", "stable"), _trends.get("phase_b_trend", ""))
                _phase_c_label = _trend_arrows.get(_trends.get("phase_c_trend", "stable"), _trends.get("phase_c_trend", ""))
                st.caption(f"A群: {_phase_a_label} / B群: {_phase_b_label} / C群: {_phase_c_label}")

                fig, ax = plt.subplots(figsize=(12, 3))
                fig.patch.set_alpha(0.0)
                _phase_a_ma = _trends.get("phase_a_ma", [])
                _phase_b_ma = _trends.get("phase_b_ma", [])
                _phase_c_ma = _trends.get("phase_c_ma", [])
                if _phase_a_ma:
                    _pm_start = len(_days_range) - len(_phase_a_ma)
                    _pm_days = _days_range[_pm_start:]
                    ax.plot(_pm_days, [v * 100 for v in _phase_a_ma], color=COLOR_A, linewidth=_DT_LW_PRIMARY, label="A群（急性期）")
                    ax.plot(_pm_days, [v * 100 for v in _phase_b_ma], color=COLOR_B, linewidth=_DT_LW_PRIMARY, label="B群（回復期）")
                    ax.plot(_pm_days, [v * 100 for v in _phase_c_ma], color=COLOR_C, linewidth=_DT_LW_PRIMARY, label="C群（退院準備）")
                ax.set_xlabel("日")
                ax.set_ylabel("構成比 (%)")
                _bc_apply_chart_style(ax)
                _leg_phase = ax.legend(loc="upper right", ncol=3, frameon=False)
                _bc_style_legend(_leg_phase)
                st.pyplot(fig)
                plt.close(fig)

                # --- 運営貢献効率トレンド ---
                _bc_section_title("1床あたり運営貢献額トレンド（移動平均）", icon="💹")
                _profit_trend_label = _trend_arrows.get(_trends.get("profit_efficiency_trend", "stable"),
                                                         _trends.get("profit_efficiency_trend", ""))
                st.caption(f"トレンド: {_profit_trend_label}")

                _ppb_ma = _trends.get("profit_per_bed_ma", [])
                if _ppb_ma:
                    fig, ax = plt.subplots(figsize=(12, 3))
                    fig.patch.set_alpha(0.0)
                    _ppb_start = len(_days_range) - len(_ppb_ma)
                    _ppb_days = _days_range[_ppb_start:]
                    ax.plot(
                        _ppb_days, [v / 10000 for v in _ppb_ma],
                        color=COLOR_PROFIT, linewidth=_DT_LW_PRIMARY,
                    )
                    ax.set_xlabel("日")
                    ax.set_ylabel("1床あたり運営貢献額（万円）")
                    _bc_apply_chart_style(ax)
                    st.pyplot(fig)
                    plt.close(fig)

                # --- 警告セクション ---
                _alerts = _trends.get("alerts", [])
                if _alerts:
                    _bc_section_title("警告", icon="⚠️")
                    for _alert in _alerts:
                        _bc_alert(_alert, severity="warning")
                else:
                    _bc_alert("現在、警告はありません。", severity="success")


# --- タブ: 📉 過去実績分析（FY2025 実データ可視化） ---
# 2026-04-18 追加: actual_admissions_2025fy.csv を読み込み、月別推移・曜日パターン・
# 時間帯・年齢分布・予約リードタイムを 1 画面で俯瞰する。
# シミュレーション実行の有無に関わらず動作する（CSV 依存のみ）。
if "\U0001f4c9 過去実績分析" in _tab_idx:
    with tabs[_tab_idx["\U0001f4c9 過去実績分析"]]:
        if not _PAST_PERF_VIEW_AVAILABLE:
            _bc_alert(
                "過去実績分析ビューの読み込みに失敗しました。",
                severity="danger",
            )
            if _PAST_PERF_VIEW_ERROR:
                with st.expander("エラー詳細（開発用）", expanded=False):
                    st.code(_PAST_PERF_VIEW_ERROR)
        else:
            try:
                render_past_performance_view()
            except Exception as _pp_render_err:
                _bc_alert(
                    "過去実績分析の描画中にエラーが発生しました。",
                    severity="danger",
                )
                with st.expander("エラー詳細（開発用）", expanded=False):
                    import traceback as _pp_render_tb
                    st.code(f"{_pp_render_err}\n{_pp_render_tb.format_exc()}")


# ===== タブ: 戦略比較（2026-04-18 削除） =====
# サイドバーの戦略選択 UI 廃止に伴い、全戦略比較タブと関連ロジックを削除。
# 戦略別パラメータ辞書・`simulate_bed_control(strategy=...)`・ユニットテストは保持。


# ===== タブ: 💾 仮説管理 =====
if "💾 仮説管理" in _tab_idx and _SCENARIO_MANAGER_AVAILABLE:
    with tabs[_tab_idx["💾 仮説管理"]]:
        _bc_section_title("改善仮説の保存・比較", icon="💾")
        st.caption("What-Ifシミュレーション結果を保存し、複数シナリオを比較・AI分析できます")

        # Section 1: Saved scenarios list
        _scenarios = list_scenarios()

        if not _scenarios:
            _bc_alert(
                "保存済みのシナリオはありません。What-if分析タブで結果を保存してください。",
                severity="info",
            )
        else:
            _bc_section_title("保存済みシナリオ", icon="📋")
            with st.container(border=True):
                _bc_alert(
                    f"現在 <strong>{len(_scenarios)}件</strong> のシナリオが保存されています。比較対象列にチェックすると 2 件以上で比較と AI 分析が実行できます。",
                    severity="info",
                )
                _sc_df = pd.DataFrame([{
                    "選択": False,
                    "名前": s["name"],
                    "種類": s.get("scenario_type", ""),
                    "保存日時": s.get("created_at", "")[:16],
                    "メモ": s.get("notes", ""),
                    "ID": s["id"],
                } for s in _scenarios])

                _edited_df = st.data_editor(
                    _sc_df,
                    column_config={
                        "選択": st.column_config.CheckboxColumn("比較対象"),
                        "ID": None,  # hide
                    },
                    disabled=["名前", "種類", "保存日時", "メモ"],
                    hide_index=True,
                    key="scenario_selector"
                )

            _selected_ids = _edited_df[_edited_df["選択"]]["ID"].tolist()

            # Section 2: Comparison
            if len(_selected_ids) >= 2:
                _bc_section_title("シナリオ比較", icon="📊")
                _comparison = compare_scenarios(_selected_ids)

                if _comparison and "comparison" in _comparison:
                    _comp = _comparison["comparison"]

                    # Metrics table
                    if "metrics_table" in _comp:
                        st.dataframe(
                            pd.DataFrame(_comp["metrics_table"]),
                            hide_index=True,
                            use_container_width=True
                        )

                    # Summary cards
                    col1, col2 = st.columns(2)
                    with col1:
                        _occ_range = _comp.get("occupancy_range", [0, 0])
                        _bc_kpi_card(
                            label="稼働率レンジ",
                            value=f"{_occ_range[0]:.1f}% 〜 {_occ_range[1]:.1f}",
                            unit="%",
                            severity="info",
                        )
                    with col2:
                        _rev_range = _comp.get("revenue_range", [0, 0])
                        _bc_kpi_card(
                            label="収益影響レンジ",
                            value=f"{_rev_range[0]:.0f} 〜 {_rev_range[1]:.0f}",
                            unit="万円/年",
                            severity="info",
                        )

                # Section 3: AI Analysis
                _bc_section_title("AI分析", icon="🤖")
                if st.button("分析を実行", key="run_ai_analysis", type="primary"):
                    _loaded = [load_scenario(sid) for sid in _selected_ids]
                    _loaded = [s for s in _loaded if s is not None]

                    _analysis = analyze_scenarios(
                        scenarios=_loaded,
                        current_metrics=None,
                        guardrail_status=None,
                        emergency_summary=None,
                    )

                    if _analysis:
                        # Executive summary
                        if _analysis.get("summary"):
                            _bc_alert(
                                f"<strong>総合所見:</strong> {_analysis['summary']}",
                                severity="info",
                            )

                        # Best scenario
                        _best = _analysis.get("best_scenario", {})
                        if _best.get("name"):
                            _bc_alert(
                                f"<strong>推奨シナリオ:</strong> {_best['name']}<br>理由: {_best.get('reason', '')}",
                                severity="success",
                            )

                        # Insights
                        _insights = _analysis.get("insights", [])
                        if _insights:
                            with st.expander("💡 分析結果の詳細", expanded=True):
                                for ins in _insights:
                                    _icon = "🔴" if ins.get("priority") == "high" else "🟡" if ins.get("priority") == "medium" else "🟢"
                                    st.markdown(f"{_icon} {ins.get('text', '')}")

                        # Recommendations
                        _recs = _analysis.get("recommendations", [])
                        if _recs:
                            with st.expander("📋 推奨アクション", expanded=True):
                                for rec in _recs:
                                    st.markdown(f"**{rec.get('rank', '')}. {rec.get('action', '')}**")
                                    st.caption(f"期待効果: {rec.get('expected_impact', '')} | 実行しやすさ: {rec.get('feasibility', '')} | リスク: {rec.get('risk', '')}")

                        # Risk assessment
                        if _analysis.get("risk_assessment"):
                            with st.expander("⚠️ リスク評価"):
                                _bc_alert(_analysis["risk_assessment"], severity="warning")

            elif len(_selected_ids) == 1:
                _bc_alert(
                    "比較するには 2 つ以上のシナリオを選択してください。",
                    severity="info",
                )

            # Delete button
            st.markdown("---")
            _bc_section_title("シナリオ削除", icon="🗑️")
            _del_id = st.selectbox("削除するシナリオ", options=["（選択してください）"] + [f"{s['name']} ({s['id'][:8]})" for s in _scenarios], key="del_scenario")
            if _del_id != "（選択してください）" and st.button("🗑️ 削除", key="delete_scenario_btn"):
                _del_actual_id = [s["id"] for s in _scenarios if f"{s['name']} ({s['id'][:8]})" == _del_id]
                if _del_actual_id:
                    delete_scenario(_del_actual_id[0])
                    _bc_alert("削除しました", severity="success")
                    st.rerun()


# ===== タブ: 👨‍⚕️ 退院タイミング（「🏥 退院調整」セクション内） =====
# Phase 1 情報階層リデザイン（2026-04-18）で旧「🎯 意思決定支援」（Phase 3 で「🔮 What-if・戦略」に改名）から移設。
# レンダリングは _tab_idx に "👨‍⚕️ 退院タイミング" が存在するかでガード。
# _dt_raw / _view_beds / target_lower / target_upper はサイドバーで初期化済み。
if "👨‍⚕️ 退院タイミング" in _tab_idx:
    with tabs[_tab_idx["👨‍⚕️ 退院タイミング"]]:
        st.subheader("🔄 入退院バランス・空床リスクモニター")

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
            _ui_candidate = globals().get("ui")
            _ui_safe = _ui_candidate if isinstance(_ui_candidate, dict) else {}
            occ_gap = target_lower - _occ_now

            # ============================================================
            # ① 空床リスクモニター（予測エンジン駆動）
            # ============================================================
            st.markdown("**🛏️ 空床リスクモニター**")

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
            st.caption("※ この機能は入院を正確に予測するものではありません。退院タイミングを整えて、予測しにくい救急入院を受けやすくするための参考値です。")

            _pred_df = _predict_admission_discharge(_dt_plot, num_beds=_view_beds, horizon=7)
            _dow_names_jp = ["月", "火", "水", "木", "金", "土", "日"]

            # 予測テーブル表示
            _pred_display = _pred_df.copy()
            _pred_display["日付"] = _pred_display["date"].apply(
                lambda d: f"{d.month}/{d.day}({_dow_names_jp[d.weekday()]})")
            _pred_display["種別"] = _pred_display["day_type"]
            _pred_display["受入見込み"] = _pred_display["pred_admissions"]
            _pred_display["退院見込み"] = _pred_display["pred_discharges"]
            _pred_display["純増減"] = _pred_display["pred_net"]
            _pred_display["予測患者数"] = _pred_display["pred_patients"].astype(int)
            _pred_display["予測稼働率"] = (_pred_display["pred_occupancy"] * 100).round(1).astype(str) + "%"
            _pred_display["信頼度"] = _pred_display["confidence"].apply(
                lambda c: f"{'🟢' if c >= 60 else '🟡' if c >= 30 else '🔴'} {c}%")

            st.dataframe(
                _pred_display[["日付", "種別", "受入見込み", "退院見込み", "純増減",
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
                        _bar_w, color=_adm_colors, edgecolor="#1565C0", alpha=0.85, label="受入見込み")
            _ax_eb1.bar([x + _bar_w/2 for x in _pred_x], _pred_df["pred_discharges"],
                        _bar_w, color=_dis_colors, edgecolor="#C62828", alpha=0.85, label="退院見込み")
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

            # ============================================================
            # ② 入退院バランスダッシュボード
            # ============================================================
            st.markdown("**📊 入退院バランスダッシュボード**")

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
                _fig_bal, (_ax_bal1, _ax_bal2) = plt.subplots(2, 1, figsize=(10, 5), gridspec_kw={"height_ratios": [3, 2]})

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
    <div style="background:#ffebee;border-radius:8px;padding:8px;border-left:4px solid #E74C3C;">
    <strong>🔴 退院超過が多い曜日:</strong> {_worst_txt}<br>
    → この曜日に新規入院を集中させる工夫が効果的
    </div>""", unsafe_allow_html=True)
                with _gc2:
                    _best_txt = "、".join([f"**{_dow_names[d]}**（{v:+.1f}名）" for d, v in _best_days])
                    st.markdown(f"""
    <div style="background:#e8f5e9;border-radius:8px;padding:8px;border-left:4px solid #27AE60;">
    <strong>🟢 入院超過が多い曜日:</strong> {_best_txt}<br>
    → この曜日のベッド確保を優先
    </div>""", unsafe_allow_html=True)

            # ============================================================
            # ③ アクションガイド
            # ============================================================
            st.markdown("**📋 状況別アクションガイド**")

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
    <div style="background:{bg};border-radius:8px;padding:8px;margin-bottom:6px;border-left:4px solid {border};">
    <strong>{icon} {title}</strong><br>{msg}
    </div>""", unsafe_allow_html=True)

            # ============================================================
            # ④ 退院マネジメント（家族目線の退院調整）
            # ============================================================
            _dm_detail_df = st.session_state.get("admission_details", pd.DataFrame())
            if not isinstance(_dm_detail_df, pd.DataFrame) or len(_dm_detail_df) == 0:
                st.info("入退院詳細データが必要です")
            else:
                # --- セクション1: 📊 退院曜日分布（グラフ） ---
                try:
                    _dm_stats = get_discharge_weekday_stats(_dm_detail_df)
                    st.markdown("### 📊 退院曜日分布")

                    _dm_dist = _dm_stats["distribution"]
                    _dm_labels = _dm_stats["labels"]
                    _dm_total = _dm_stats["total"]
                    _dm_fri_pct = _dm_stats["friday_pct"]

                    if _dm_total > 0:
                        st.metric("金曜退院率", f"{_dm_fri_pct}%",
                                  delta=f"金曜集中度 {_dm_stats['concentration_index']:.1f}倍",
                                  delta_color="inverse")

                        _dm_counts = [_dm_dist.get(i, 0) for i in range(7)]
                        _dm_colors = ["#e74c3c" if i == 4 else "#3498db" for i in range(7)]
                        _dm_avg_line = _dm_total / 7.0

                        _dm_fig, _dm_ax = plt.subplots(figsize=(10, 3))
                        _dm_ax.bar(_dm_labels, _dm_counts, color=_dm_colors, edgecolor="white")
                        _dm_ax.axhline(y=_dm_avg_line, color="gray", linestyle="--", linewidth=1, label=f"均等分布 ({_dm_avg_line:.1f}件)")
                        _dm_ax.set_ylabel("退院件数")
                        _dm_ax.set_title("曜日別退院件数")
                        _dm_ax.legend()
                        for idx_bar, cnt in enumerate(_dm_counts):
                            if cnt > 0:
                                _dm_ax.text(idx_bar, cnt + 0.3, str(cnt), ha="center", fontsize=10)
                        _dm_fig.tight_layout()
                        st.pyplot(_dm_fig)
                        plt.close(_dm_fig)

                        st.caption("金曜に退院が集中すると、土日に空床が増えます")
                    else:
                        st.info("退院データがありません")
                except Exception as _dm_e1:
                    st.warning(f"退院曜日分布の表示でエラーが発生しました: {_dm_e1}")

                # --- セクション2: 👨‍👩‍👧 日曜退院候補リスト ---
                try:
                    st.markdown("### 👨‍👩‍👧 ご家族の都合に合わせた日曜退院候補")

                    _dm_daily_src = st.session_state.get("daily_data")
                    if isinstance(_dm_daily_src, pd.DataFrame) and len(_dm_daily_src) > 0:
                        _dm_daily_df = aggregate_wards(_dm_daily_src) if "ward" in _dm_daily_src.columns else _dm_daily_src
                    elif _dt_raw is not None and len(_dt_raw) > 0:
                        _dm_daily_df = _dt_raw
                    else:
                        _dm_daily_df = pd.DataFrame()

                    _dm_ward_beds = {"5F": 47, "6F": 47}

                    if len(_dm_daily_df) == 0:
                        st.info("日次データが必要です")
                    else:
                        _dm_candidates = get_sunday_discharge_candidates(
                            _dm_detail_df, _dm_daily_df, ward_beds=_dm_ward_beds
                        )

                        # --- パターンB「早める」条件付き表示ロジック ---
                        # 現在の稼働率・LOSを計算
                        if "total_patients" in _dm_daily_df.columns:
                            _dm_current_occ = _dm_daily_df["total_patients"].tail(7).mean() / 94 * 100
                        else:
                            _dm_current_occ = 0.0
                        if "avg_los" in _dm_daily_df.columns:
                            _dm_current_los = _dm_daily_df["avg_los"].tail(7).mean()
                        else:
                            _dm_current_los = 0.0

                        _dm_target_occ_pct = target_lower * 100  # 目標稼働率（%）
                        _dm_los_threshold = _max_avg_los - 1.0   # 施設基準-1日（迫るライン）

                        _dm_show_pattern_b = (_dm_current_occ >= _dm_target_occ_pct) or (_dm_current_los >= _dm_los_threshold)

                        # パターンB非表示の場合はフィルタリング
                        if not _dm_show_pattern_b:
                            _dm_candidates = [c for c in _dm_candidates if c.get("shift_type") != "早める"]

                        # --- ガイダンスメッセージ ---
                        if not _dm_show_pattern_b:
                            st.info(
                                f"💡 稼働率{_dm_current_occ:.1f}%・在院日数{_dm_current_los:.1f}日 — "
                                "C群在院継続で貢献額確保が有利。「早める」候補は稼働率目標到達時に表示。"
                            )
                        else:
                            if _dm_current_los >= _dm_los_threshold:
                                st.warning(
                                    f"⚠️ 平均在院日数 {_dm_current_los:.1f}日 — "
                                    f"施設基準{_max_avg_los}日に迫っています。"
                                    "在院日数短縮のため「早める」退院調整を検討してください。"
                                )
                            elif _dm_current_occ >= _dm_target_occ_pct:
                                st.success(
                                    f"✅ 稼働率 {_dm_current_occ:.1f}% — 目標圏内です。"
                                    "月曜の新規入院枠確保のため「早める」退院調整も有効です。"
                                )

                        if len(_dm_candidates) == 0:
                            st.info("現在、日曜退院の調整候補はありません")
                        else:
                            _dm_cand_df = pd.DataFrame(_dm_candidates)

                            # 調整方向カラムを生成
                            _dm_weekday_names = {0: "月", 1: "火", 4: "金", 5: "土"}
                            def _dm_format_direction(row):
                                _orig_date = pd.to_datetime(row["date"])
                                _orig_wd = _orig_date.dayofweek
                                _wd_name = _dm_weekday_names.get(_orig_wd, "?")
                                _days = row["additional_days"]
                                if row["shift_type"] == "延ばす":
                                    return f"\U0001f7e2 {_wd_name}\u2192日（+{_days}日）"
                                else:
                                    return f"\U0001f535 {_wd_name}\u2192日（{_days}日）"
                            if "shift_type" in _dm_cand_df.columns:
                                _dm_cand_df["direction_label"] = _dm_cand_df.apply(_dm_format_direction, axis=1)
                            else:
                                _dm_cand_df["direction_label"] = ""

                            # LOS余裕を見やすくフォーマット
                            if "los_margin" in _dm_cand_df.columns:
                                _dm_cand_df["los_margin"] = _dm_cand_df["los_margin"].apply(
                                    lambda x: f"+{x:.1f}日" if x >= 0 else f"{x:.1f}日"
                                )

                            _dm_display_cols = {
                                "ward": "病棟",
                                "date": "退院予定日",
                                "direction_label": "調整方向",
                                "phase": "フェーズ",
                                "los_days": "在院日数",
                                "attending_doctor": "担当医",
                                "sunday_date": "日曜退院日",
                                "los_margin": "LOS（在院日数）余裕",
                                "recommendation": "推奨",
                            }
                            _dm_cand_show = _dm_cand_df[[c for c in _dm_display_cols.keys() if c in _dm_cand_df.columns]].copy()
                            _dm_cand_show.rename(columns=_dm_display_cols, inplace=True)

                            def _dm_highlight_recommend(row):
                                if row.get("推奨") == "◎":
                                    return ["background-color: #e8f5e9"] * len(row)
                                return [""] * len(row)

                            st.dataframe(
                                _dm_cand_show.style.apply(_dm_highlight_recommend, axis=1),
                                use_container_width=True,
                                hide_index=True,
                            )

                        st.caption("働き世代のご家族にとって、日曜はお迎えしやすい日です。"
                                   "🟢延ばす＝週末稼働率UP、🔵早める＝在院日数短縮＋月曜入院枠確保。"
                                   "家族目線の退院調整が運営改善にもつながります。")
                except Exception as _dm_e2:
                    st.warning(f"日曜退院候補リストの表示でエラーが発生しました: {_dm_e2}")

                # --- セクション3: 🔮 退院調整シミュレーション ---
                try:
                    st.markdown("### 🔮 退院調整シミュレーション")

                    # スライダーの最大値は候補者数（候補がいなければ5をデフォルト）
                    _dm_max_shifts = len(_dm_candidates) if "_dm_candidates" in dir() and len(_dm_candidates) > 0 else 5
                    _dm_n_shifts = st.slider(
                        "日曜退院に調整する人数",
                        min_value=0,
                        max_value=max(_dm_max_shifts, 1),
                        value=0,
                        key="dm_shift_slider",
                    )

                    _dm_result = simulate_discharge_shift(
                        daily_df=_dm_daily_df if "_dm_daily_df" in dir() and isinstance(_dm_daily_df, pd.DataFrame) and len(_dm_daily_df) > 0 else pd.DataFrame(),
                        detail_df=_dm_detail_df,
                        n_shifts=_dm_n_shifts,
                        beds_total=_view_beds,
                    )

                    _dm_before = _dm_result["before"]
                    _dm_after = _dm_result["after"]
                    _dm_impact = _dm_result["impact"]

                    _dm_col1, _dm_col2, _dm_col3 = st.columns(3)
                    with _dm_col1:
                        st.metric(
                            "週末稼働率",
                            f"{_dm_after['weekend_avg_occ']:.1f}%",
                            delta=f"{_dm_impact['weekend_occ_change_pt']:+.1f}pt" if _dm_n_shifts > 0 else None,
                        )
                    with _dm_col2:
                        _dm_monthly_man = _dm_impact["additional_contribution_per_month"]
                        st.metric(
                            "月間追加運営貢献額",
                            f"{_dm_monthly_man // 10000}万円" if _dm_monthly_man >= 10000 else f"{_dm_monthly_man:,}円",
                        )
                    with _dm_col3:
                        st.metric(
                            "在院日数への影響",
                            f"+{_dm_impact['los_impact_days']:.2f}日",
                        )

                    # 曜日別稼働率の週間パターン（グループ棒グラフ）
                    _dm_day_labels = ["月", "火", "水", "木", "金", "土", "日"]
                    _dm_before_vals = [_dm_before["weekday_occ"].get(i, 0) for i in range(7)]
                    _dm_after_vals = [_dm_after["weekday_occ"].get(i, 0) for i in range(7)]

                    _dm_fig2, _dm_ax2 = plt.subplots(figsize=(10, 3))
                    _dm_x = np.arange(len(_dm_day_labels))
                    _dm_width = 0.35

                    # 目標レンジ（棒の背面に描画）
                    _dm_ax2.axhspan(90, 95, alpha=0.1, color='gold', label='目標レンジ (90-95%)')

                    # 棒グラフ描画
                    _dm_bars1 = _dm_ax2.bar(_dm_x - _dm_width / 2, _dm_before_vals, _dm_width, label='現状', color='#95a5a6', alpha=0.8)
                    if _dm_n_shifts > 0:
                        _dm_bars2 = _dm_ax2.bar(_dm_x + _dm_width / 2, _dm_after_vals, _dm_width, label='調整後', color='#27ae60', alpha=0.8)

                    # 値ラベル（現状）
                    for _dm_bar in _dm_bars1:
                        _dm_ax2.text(_dm_bar.get_x() + _dm_bar.get_width() / 2., _dm_bar.get_height() + 0.3,
                                     f'{_dm_bar.get_height():.1f}%', ha='center', va='bottom', fontsize=8, color='#666')
                    # 値ラベル（調整後）
                    if _dm_n_shifts > 0:
                        for _dm_bar in _dm_bars2:
                            _dm_ax2.text(_dm_bar.get_x() + _dm_bar.get_width() / 2., _dm_bar.get_height() + 0.3,
                                         f'{_dm_bar.get_height():.1f}%', ha='center', va='bottom', fontsize=8, color='#27ae60')

                    _dm_ax2.set_xticks(_dm_x)
                    _dm_ax2.set_xticklabels(_dm_day_labels)
                    _dm_ax2.set_ylabel("稼働率 (%)")
                    _dm_ax2.set_title("曜日別稼働率の変化（週間パターン）")
                    _dm_ax2.legend()

                    # Y軸範囲を自動調整（差が見えるように）
                    _dm_all_vals = _dm_before_vals + (_dm_after_vals if _dm_n_shifts > 0 else [])
                    _dm_y_min = max(0, min(_dm_all_vals) - 3)
                    _dm_y_max = min(100, max(_dm_all_vals) + 3)
                    _dm_ax2.set_ylim(_dm_y_min, _dm_y_max)

                    _dm_ax2.grid(axis='y', alpha=0.3)
                    _dm_fig2.tight_layout()
                    st.pyplot(_dm_fig2)
                    plt.close(_dm_fig2)

                    st.caption("家族目線の退院調整が運営改善にもつながります。")
                except Exception as _dm_e3:
                    st.warning(f"退院調整シミュレーションの表示でエラーが発生しました: {_dm_e3}")


# ===== タブ: データ =====
if "データ" in _tab_idx and _data_ready:
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

        # データ出典の注意書き（実運用開始までの過渡期表示）
        # 本タブは 2 系統のデータを表示しているため、混乱を防ぐためバナーで明示する。
        # 実運用で admission_details に実医師コードが入力され始めたら、
        # 上半分も自動的に実データに切り替わる（その時点でこのバナーは不要になる）。
        _bc_alert(
            "**📌 データ出典の注意** "
            "本タブの**上半分**（医師別パフォーマンス・退院曜日分布・改善の可能性）は、"
            "現在は教育用デモデータ（A医師〜J医師、`admission_details.csv`）を表示しています。"
            "実運用で実医師コードが入力され始めると、ここは自動的に実データに切り替わります。"
            "／ 一方、**下半分**（過去1年プロファイル分析）は事務提供の実データ"
            "（実医師コード UEMH/TAM 等、`past_admissions_2025fy.csv`）です。",
            severity="info",
        )

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
                            if _fri_pct > 25:
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

            # =========================================================
            # 📊 深掘りインサイト（Phase 1: 曜日プロファイル + C群長期化率）
            # 全期間データで医師ごとの傾向を抽出。月別サマリとは独立。
            # =========================================================
            if _DOCTOR_INSIGHT_AVAILABLE:
                st.markdown("---")
                _bc_section_title("医師別 改善の可能性（深掘りインサイト）", icon="💡")
                st.caption(
                    "全期間の退院データから、医師ごとの傾向を客観指標で抽出します。"
                    "評価ではなく改善の可能性の提示を目的とし、理事会・師長会議での議論材料に使えます。"
                )

                _insights_all = _di_build_doctor_insights(_detail_df)
                if not _insights_all:
                    _bc_alert(
                        "深掘りインサイトを出すには退院データが必要です。"
                        "「日次データ入力」タブで退院イベントを記録してください。",
                        severity="info",
                    )
                else:
                    # サマリ: warning 件数
                    _warning_docs = [i for i in _insights_all if i.get("worst_severity") == "warning"]
                    _neutral_docs = [i for i in _insights_all if i.get("worst_severity") == "neutral"]
                    _unknown_docs = [i for i in _insights_all if i.get("worst_severity") == "unknown"]

                    _sum_c1, _sum_c2, _sum_c3 = st.columns(3)
                    with _sum_c1:
                        _bc_kpi_card(
                            "注目の医師",
                            str(len(_warning_docs)),
                            "名",
                            severity="warning" if _warning_docs else "neutral",
                            size="md",
                        )
                    with _sum_c2:
                        _bc_kpi_card(
                            "平均圏内",
                            str(len(_neutral_docs)),
                            "名",
                            severity="neutral",
                            size="md",
                        )
                    with _sum_c3:
                        _bc_kpi_card(
                            "データ不足",
                            str(len(_unknown_docs)),
                            "名",
                            severity="neutral",
                            size="md",
                        )

                    # --- 指標 1: 曜日別退院プロファイル ---
                    st.markdown("##### 📅 曜日別退院プロファイル")
                    st.caption(
                        "金曜集中 or 週末回避が顕著な医師を抽出。"
                        "退院の曜日分散が土日稼働率に直結します。"
                    )
                    _wd_rows = []
                    for ins in _insights_all:
                        wd = ins.get("weekday")
                        if not wd:
                            continue
                        _severity_icon = {
                            "warning": "⚠️",
                            "neutral": "🟢",
                            "unknown": "—",
                        }.get(wd.get("severity", "unknown"), "—")
                        _wd_rows.append({
                            "": _severity_icon,
                            "医師名": ins["doctor"],
                            "退院数": wd.get("total_discharges", 0),
                            "金曜率(%)": wd.get("friday_pct", 0.0),
                            "週末率(%)": wd.get("weekend_pct", 0.0),
                            "観察": wd.get("observation", ""),
                        })
                    if _wd_rows:
                        _wd_df = pd.DataFrame(_wd_rows)
                        st.dataframe(_wd_df, use_container_width=True, hide_index=True)

                        # 注目医師ごとのアクションヒント
                        _wd_warnings = [
                            ins for ins in _insights_all
                            if ins.get("weekday") and ins["weekday"].get("severity") == "warning"
                        ]
                        if _wd_warnings:
                            for ins in _wd_warnings:
                                wd = ins["weekday"]
                                _bc_alert(
                                    f"**{ins['doctor']}**: {wd['observation']}  \n"
                                    f"💡 {wd['action_hint']}",
                                    severity="warning",
                                )
                        else:
                            _bc_alert(
                                "曜日分布について注目が必要な医師はいません。",
                                severity="success",
                            )

                    # --- 指標 2: C群長期化率 ---
                    st.markdown("##### 🏥 C群（15日以上）長期化率")
                    st.caption(
                        "在院15日以上の患者比率。診療科・患者背景で違いはありますが、"
                        "平均から大きく乖離する場合は退院阻害要因の棚卸しが有効です。"
                    )
                    _cg_rows = []
                    for ins in _insights_all:
                        cg = ins.get("c_group")
                        if not cg:
                            continue
                        _severity_icon = {
                            "warning": "⚠️",
                            "neutral": "🟢",
                            "unknown": "—",
                        }.get(cg.get("severity", "unknown"), "—")
                        _cg_rows.append({
                            "": _severity_icon,
                            "医師名": ins["doctor"],
                            "退院数": cg.get("total_discharges", 0),
                            "C群数": cg.get("c_group_count", 0),
                            "C群率(%)": cg.get("c_group_pct", 0.0),
                            "C群平均LOS(日)": cg.get("avg_los_c", 0.0),
                            "観察": cg.get("observation", ""),
                        })
                    if _cg_rows:
                        _cg_df = pd.DataFrame(_cg_rows)
                        st.dataframe(_cg_df, use_container_width=True, hide_index=True)

                        _cg_warnings = [
                            ins for ins in _insights_all
                            if ins.get("c_group") and ins["c_group"].get("severity") == "warning"
                        ]
                        if _cg_warnings:
                            for ins in _cg_warnings:
                                cg = ins["c_group"]
                                _bc_alert(
                                    f"**{ins['doctor']}**: {cg['observation']}  \n"
                                    f"💡 {cg['action_hint']}",
                                    severity="warning",
                                )
                        else:
                            _bc_alert(
                                "C群長期化について注目が必要な医師はいません。",
                                severity="success",
                            )

                    # --- 将来拡張の予告（非UI） ---
                    with st.expander("ℹ️ 今後追加予定の深掘り指標", expanded=False):
                        st.markdown("""
- **退院調整の速さ** — 入院→退院確定までの平均日数
- **短手3 活用率 / Day 5 超過率** — 短手3 症例の選び方と延長リスク
- **救急搬送後入院の貢献度** — 救急 15% 基準達成への寄与

これらは追加実装予定です。現時点では「曜日プロファイル」と「C群長期化率」の 2 指標のみで運用します。
""")
            elif "_DOCTOR_INSIGHT_ERROR" in dir():
                st.caption(f"（深掘りインサイトモジュールの読み込みに失敗しました: {_DOCTOR_INSIGHT_ERROR[:200]}）")

        # =========================================================
        # 📊 過去1年プロファイル分析（2026-04-24 追加）
        # admission_details が空でも past_admissions_df があれば動作する。
        # 運用開始後に日次データが積み重なれば、同じロジックで
        # admission_details からも計算できる（data-source 非依存）。
        # =========================================================
        if _PAST_ADMISSIONS_AVAILABLE:
            _pa_df_prof = st.session_state.get("past_admissions_df", pd.DataFrame())
            if not _pa_df_prof.empty:
                st.markdown("---")
                _bc_section_title(
                    "過去1年プロファイル分析（実データ：退院曜日・自主回転・週末空床リスク）",
                    icon="📊",
                )
                st.caption(
                    "📍 **データ出典**: 事務提供の 2025 年度実データ（1,823 件、実医師コード UEMH/TAM 等）。"
                    "上半分のデモデータ（A医師〜J医師）とは出典が異なります。"
                    "**中央値との差** で提示し、順位付けは避けています "
                    "（中央在院日数 = 同診療科の他医師 / 金+土退院率 = 全医師。"
                    "金+土退院率は 1 名のみの診療科が複数あるため leave-one-out せず本人を含む全医師中央値）。"
                    "件数 < 20 件の医師は参考値扱い（グレー表示）。"
                )

                try:
                    import plotly.graph_objects as go
                    _plotly_dp = True
                except ImportError:
                    _plotly_dp = False

                from doctor_discharge_profile import (
                    build_doctor_summary,
                    compute_self_driven_los,
                    compute_weekday_profile,
                    compute_weekend_vacancy_risk,
                )
                from doctor_specialty_map import DOCTOR_SPECIALTY_GROUP

                # ---- ビュー切替 ----
                _view_mode = st.radio(
                    "表示モード",
                    ["🌐 全体概観", "👤 個別医師プロファイル"],
                    horizontal=True,
                    key="doctor_profile_view_mode",
                )

                _weekday_prof = compute_weekday_profile(_pa_df_prof)
                # 手術なし全体を対象（副院長指示 2026-04-24）+ 副院長分類を使用
                _self_driven = compute_self_driven_los(
                    _pa_df_prof,
                    specialty_override_map=DOCTOR_SPECIALTY_GROUP,
                    require_scheduled=False,
                )
                _weekend_risk = compute_weekend_vacancy_risk(_pa_df_prof)

                if _view_mode == "🌐 全体概観":
                    # --- 週末空床リスク寄与度（金+土退院率）ランキング ---
                    st.markdown("#### 🔴 週末空床リスク寄与度（金+土退院率）")
                    st.caption(
                        "金曜＋土曜の退院が多いほど、土日に空床が発生しやすい "
                        "（当院は土曜入院 2.2件/日・日曜入院 0.3件/日でほぼ補充されない）。"
                        "全医師の中央値より高い医師は、対象患者の "
                        "**月曜以降への退院振替** を検討（日曜・祝日は 1 病棟 2 人/日 まで補助枠として活用可）。"
                    )
                    if _plotly_dp and _weekend_risk:
                        _risk_sorted = sorted(
                            [(d, r) for d, r in _weekend_risk.items()],
                            key=lambda kv: -kv[1]["fri_sat_pct"],
                        )
                        _doctors = [d for d, _ in _risk_sorted]
                        _fri_sat = [r["fri_sat_pct"] for _, r in _risk_sorted]
                        _colors = [
                            "#9CA3AF" if r["is_small_sample"]
                            else ("#DC2626" if r["delta_vs_peer"] >= 5
                                  else "#F59E0B" if r["delta_vs_peer"] >= 0
                                  else "#10B981")
                            for _, r in _risk_sorted
                        ]
                        _peer_med = _risk_sorted[0][1]["peer_fri_sat_pct"] if _risk_sorted else 0
                        _fig_risk = go.Figure()
                        _fig_risk.add_trace(go.Bar(
                            x=_fri_sat, y=_doctors, orientation="h",
                            marker_color=_colors,
                            text=[f"{v:.1f}%" for v in _fri_sat],
                            textposition="outside",
                            hovertemplate="%{y}<br>金+土: %{x:.1f}%<extra></extra>",
                        ))
                        _fig_risk.add_vline(
                            x=_peer_med, line_width=2, line_dash="dash",
                            line_color="#374151",
                            annotation_text=f"全医師の中央値 {_peer_med:.1f}%",
                            annotation_position="top",
                        )
                        _fig_risk.update_layout(
                            height=max(300, 30 * len(_doctors)),
                            xaxis_title="金+土曜退院率 (%)",
                            margin=dict(l=60, r=80, t=30, b=40),
                            showlegend=False,
                        )
                        st.plotly_chart(_fig_risk, use_container_width=True)
                        st.caption(
                            "🔴 赤＝全医師の中央値より +5pt 以上（リスク寄与大、振替推奨）／"
                            "🟠 オレンジ＝全医師の中央値より 0〜5pt 上／"
                            "🟢 緑＝全医師の中央値より下（リスク抑制）／"
                            "⚪ グレー＝件数 < 20（参考値）"
                        )

                    # --- 自主回転 中央在院日数 ---
                    st.markdown("#### 🔄 医師別 中央在院日数（手術なし症例）")
                    st.caption(
                        "術後経過という外的要因を排除した「手術なし」症例で、"
                        "医師の退院判断を比較。**診療科グループは副院長分類**（内科/外科/"
                        "ペイン科/整形外科/脳神経外科/外来専任/訪問診療医）。"
                        "**同グループの他医師の中央値** より **短ければ自主的に回転**、"
                        "**長ければゆったり** という傾向が読める。"
                    )
                    if _plotly_dp and _self_driven:
                        _sd_sorted = sorted(
                            [(d, s) for d, s in _self_driven.items()],
                            key=lambda kv: kv[1]["median_los"],
                        )
                        _sd_docs = [d for d, _ in _sd_sorted]
                        _sd_self = [s["median_los"] for _, s in _sd_sorted]
                        _sd_peer = [s["peer_median"] for _, s in _sd_sorted]
                        _sd_ns = [s["self_driven_cases"] for _, s in _sd_sorted]
                        _sd_small = [s["is_small_sample"] for _, s in _sd_sorted]
                        _sd_colors = [
                            "#9CA3AF" if sm else "#2563EB"
                            for sm in _sd_small
                        ]
                        _fig_sd = go.Figure()
                        _fig_sd.add_trace(go.Scatter(
                            x=_sd_self, y=_sd_docs,
                            mode="markers",
                            marker=dict(size=14, color=_sd_colors),
                            name="自身の中央在院日数",
                            hovertemplate="%{y}<br>self %{x}日<br>件数 %{customdata}<extra></extra>",
                            customdata=_sd_ns,
                        ))
                        _fig_sd.add_trace(go.Scatter(
                            x=_sd_peer, y=_sd_docs,
                            mode="markers",
                            marker=dict(size=10, color="#DC2626", symbol="line-ns-open"),
                            name="他医師の中央値",
                            hovertemplate="%{y}<br>他医師 %{x}日<extra></extra>",
                        ))
                        _fig_sd.update_layout(
                            height=max(300, 30 * len(_sd_docs)),
                            xaxis_title="中央在院日数（日）",
                            margin=dict(l=60, r=20, t=30, b=40),
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                        )
                        st.plotly_chart(_fig_sd, use_container_width=True)

                    # --- 曜日偏り Gini ランキング ---
                    with st.expander("📏 曜日偏り指数（Gini 係数）ランキング", expanded=False):
                        if _weekday_prof:
                            _gini_rows = []
                            for doc, pf in sorted(
                                _weekday_prof.items(),
                                key=lambda kv: -kv[1]["gini"],
                            ):
                                _gini_rows.append({
                                    "医師": doc + ("（参考値）" if pf["is_small_sample"] else ""),
                                    "件数": pf["total"],
                                    "Gini": pf["gini"],
                                    "月": pf["pcts"][0],
                                    "火": pf["pcts"][1],
                                    "水": pf["pcts"][2],
                                    "木": pf["pcts"][3],
                                    "金": pf["pcts"][4],
                                    "土": pf["pcts"][5],
                                    "日": pf["pcts"][6],
                                    "分類": {
                                        "friday_heavy": "⚠️ 金曜集中",
                                        "monday_heavy": "ℹ️ 月曜集中",
                                        "uniform": "✅ 均等",
                                        "normal": "—",
                                    }.get(pf["flag"], "—"),
                                })
                            st.dataframe(
                                pd.DataFrame(_gini_rows),
                                use_container_width=True, hide_index=True,
                            )
                            st.caption(
                                "Gini 係数: 0 = 完全均等 / 1 = 極端な偏り。"
                                "7 曜日で 1 曜日集中だと 0.857 が理論最大。"
                            )

                else:  # 個別医師プロファイル
                    _doc_list = sorted(_weekday_prof.keys())
                    if not _doc_list:
                        st.info("医師プロファイルを計算できるデータがありません。")
                    else:
                        _sel_doc = st.selectbox("医師コードを選択", _doc_list, key="profile_doctor_select")
                        _summary = build_doctor_summary(
                            _pa_df_prof, _sel_doc,
                            specialty_override_map=DOCTOR_SPECIALTY_GROUP,
                            require_scheduled=False,
                        )

                        # メインカード
                        _wd = _summary["weekday"]
                        _sd = _summary["self_driven"]
                        _wr = _summary["weekend_risk"]

                        _cols_prof = st.columns(4)
                        _cols_prof[0].metric("退院件数", f"{_wd.get('total', 0)}件")
                        _cols_prof[1].metric(
                            "金曜退院率",
                            f"{_wd.get('friday_pct', 0):.1f}%",
                            delta=f"{_wd.get('friday_pct', 0) - 14.3:+.1f}pt（均等比）",
                        )
                        _cols_prof[2].metric(
                            "金+土退院率",
                            f"{_wr.get('fri_sat_pct', 0):.1f}%",
                            delta=f"{_wr.get('delta_vs_peer', 0):+.1f}pt（全医師中央値との差）",
                            delta_color="inverse",  # 高いほど悪い
                        )
                        _cols_prof[3].metric(
                            "曜日偏りGini",
                            f"{_wd.get('gini', 0):.3f}",
                            help="0=完全均等, 1=極端な偏り",
                        )

                        # Insights バッジ
                        _insights = _summary["insights"]
                        if _insights:
                            st.markdown("##### 📝 プロファイル要約")
                            for ins in _insights:
                                if ins.startswith("✅"):
                                    _bc_alert(ins, severity="success")
                                elif ins.startswith("⚠️"):
                                    _bc_alert(ins, severity="warning")
                                elif ins.startswith("📈"):
                                    _bc_alert(ins, severity="info")
                                else:
                                    _bc_alert(ins, severity="neutral")

                        # 曜日棒グラフ
                        if _plotly_dp and _wd:
                            _fig_wd = go.Figure(go.Bar(
                                x=["月", "火", "水", "木", "金", "土", "日"],
                                y=_wd["counts"],
                                marker_color=[
                                    "#2563EB" if i < 3 else
                                    "#F59E0B" if i == 3 else
                                    "#DC2626" if i == 4 else "#6B7280"
                                    for i in range(7)
                                ],
                                text=[
                                    f"{_wd['counts'][i]}<br>({_wd['pcts'][i]:.1f}%)"
                                    for i in range(7)
                                ],
                                textposition="outside",
                            ))
                            _fig_wd.update_layout(
                                title=f"{_sel_doc} の退院曜日分布",
                                height=300,
                                yaxis_title="退院件数",
                                margin=dict(l=40, r=20, t=40, b=40),
                                showlegend=False,
                            )
                            st.plotly_chart(_fig_wd, use_container_width=True)

                        # 自主回転 LOS 詳細
                        if _sd and not _sd.get("is_small_sample", True):
                            _sd_col1, _sd_col2 = st.columns(2)
                            _sd_col1.metric(
                                "手術なし 件数",
                                f"{_sd['self_driven_cases']}件",
                                help=f"診療科グループ: {_sd.get('peer_group', '—')}",
                            )
                            _sd_col2.metric(
                                f"中央在院日数（vs {_sd.get('peer_group', '他医師')}）",
                                f"{_sd['median_los']}日",
                                delta=f"{_sd['los_delta_vs_peer']:+.1f}日（他医師 {_sd['peer_median']}日）",
                                delta_color="normal",  # 他医師より短い=正=良
                            )

                        if _wd.get("is_small_sample", False):
                            _bc_alert(
                                f"⚪ 退院件数が {_wd['total']} 件と少ないため、"
                                f"参考値扱いとしてください（閾値: 20件）",
                                severity="info",
                            )

# ---------------------------------------------------------------------------
# タブ: 📊 過去1年分析（事務提供の2025年度実データ）
# ---------------------------------------------------------------------------
# 2026-04-24 実装:
#   A) 救急15% rolling 3ヶ月推移（5F / 6F / 全体 × 月別 + 15%基準線）
#   B) イ/ロ/ハ判定の過去遡及分布（全期間 + 病棟別）
#
# 副院長指示の制度ルール（厳守）:
#   - 分子 = 自院救急 + 下り搬送（救急車=有の全件）
#   - 分母 = 全入院（短手3 を除外しない）
#   - 短手3 識別は統計用途のみで救急比率計算とは分離
if _PAST_ADMISSIONS_AVAILABLE and "\U0001f4ca 過去1年分析" in _tab_idx:
    with tabs[_tab_idx["\U0001f4ca 過去1年分析"]]:
        st.header("\U0001f4ca 過去1年分析（2025年度事務提供データ）")
        _pa_df = st.session_state.get("past_admissions_df", pd.DataFrame())
        if _pa_df.empty:
            st.warning(
                "過去入院データを読み込めません。"
                "`data/past_admissions_2025fy.csv` の存在を確認してください。"
            )
        else:
            _pa_5f = int((_pa_df["病棟"] == "5F").sum())
            _pa_6f = int((_pa_df["病棟"] == "6F").sum())
            _pa_total = len(_pa_df)
            st.caption(
                f"期間: 2025-04-01〜2026-03-31 ｜ "
                f"{_pa_total:,} 件 ｜ 5F: {_pa_5f:,} / 6F: {_pa_6f:,} ｜ "
                f"救急搬送: {int(_pa_df['is_emergency_transport'].sum())} 件"
                f"（自院 {int(_pa_df['is_self_emergency'].sum())} / "
                f"下り {int(_pa_df['is_downstream_transfer'].sum())}）"
            )

            # bridge 卒業通知バナー（副院長指示 2026-04-24）
            # 手動シード YAML にエントリがある月のうち、過去 CSV で代替された月を検出。
            # 優先順位は daily > summary > manual_seed のため、代替済みシードは既に
            # 使われていないが、副院長が yaml を片付ける判断材料として表示する。
            try:
                from emergency_ratio import (
                    load_manual_seeds_from_yaml as _er_load_seeds,
                    get_superseded_seed_months as _er_superseded,
                )
                _pa_seeds = _er_load_seeds()
                _pa_superseded = _er_superseded(_pa_seeds, _pa_df)
                if _pa_superseded:
                    _superseded_list = ", ".join(_pa_superseded)
                    st.success(
                        f"\U0001f393 **bridge 卒業判定**: "
                        f"{_superseded_list} の手動シードは過去 CSV で代替されました。"
                        f"`settings/manual_seed_emergency_ratio.yaml` の該当月エントリは"
                        f"削除して問題ありません（既に優先順位上は使われていません）。"
                    )
                elif _pa_seeds:
                    st.info(
                        "手動シード YAML にエントリがありますが、過去 CSV で代替されて"
                        "いる月はありません。現状のシードは引き続き rolling 計算に"
                        "使用される可能性があります。"
                    )
            except Exception as _er_err:
                # 卒業判定は補助機能なので、失敗しても本体機能は動かす
                import traceback as _er_tb
                with st.expander("bridge 卒業判定の読み込みエラー（補助機能）", expanded=False):
                    st.code(f"{_er_err}\n{_er_tb.format_exc()}")

            try:
                import plotly.graph_objects as go
                _plotly_ok = True
            except ImportError:
                _plotly_ok = False
                st.warning("Plotly 未インストールのためグラフ表示できません。")

            # ===== A: 救急15% rolling 3ヶ月推移 =====
            st.subheader("\U0001f691 救急搬送後割合 rolling 3ヶ月推移")
            st.caption(
                "**制度基準 15%** — 2026-06-01 以降の本則完全適用下では、"
                "**両病棟で rolling 3ヶ月が常に 15% 以上** を維持する必要があります。"
            )

            from past_admissions_loader import to_monthly_summary as _pa_to_summary
            _pa_summary = _pa_to_summary(_pa_df)

            # rolling 3ヶ月の月別計算（2025-06 以降、3ヶ月分揃う月のみ）
            _pa_months_sorted = sorted(_pa_summary.keys())
            _rolling_rows = []
            for i, ym in enumerate(_pa_months_sorted):
                if i < 2:
                    continue  # 3ヶ月分揃わない月はスキップ
                window = _pa_months_sorted[i - 2 : i + 1]
                row = {"month": ym}
                for ward_key in ("5F", "6F", "all"):
                    num = sum(_pa_summary[w][ward_key]["emergency"] for w in window)
                    den = sum(_pa_summary[w][ward_key]["admissions"] for w in window)
                    row[f"{ward_key}_pct"] = round(num / den * 100, 2) if den > 0 else 0.0
                    row[f"{ward_key}_num"] = num
                    row[f"{ward_key}_den"] = den
                _rolling_rows.append(row)

            if _rolling_rows and _plotly_ok:
                _months = [r["month"] for r in _rolling_rows]
                _fig_roll = go.Figure()
                # 15% 閾値
                _fig_roll.add_hline(
                    y=15, line_width=2, line_dash="dash", line_color="#DC2626",
                    annotation_text="制度基準 15%", annotation_position="top right",
                )
                _fig_roll.add_trace(go.Scatter(
                    x=_months, y=[r["5F_pct"] for r in _rolling_rows],
                    mode="lines+markers", name="5F", line=dict(color="#2563EB", width=3),
                    hovertemplate="%{x}<br>5F: %{y:.1f}%<extra></extra>",
                ))
                _fig_roll.add_trace(go.Scatter(
                    x=_months, y=[r["6F_pct"] for r in _rolling_rows],
                    mode="lines+markers", name="6F", line=dict(color="#7C3AED", width=3),
                    hovertemplate="%{x}<br>6F: %{y:.1f}%<extra></extra>",
                ))
                _fig_roll.add_trace(go.Scatter(
                    x=_months, y=[r["all_pct"] for r in _rolling_rows],
                    mode="lines+markers", name="全体",
                    line=dict(color="#6B7280", width=2, dash="dot"),
                    hovertemplate="%{x}<br>全体: %{y:.1f}%<extra></extra>",
                ))
                _fig_roll.update_layout(
                    height=400,
                    yaxis_title="救急搬送後割合 (%)",
                    xaxis_title="月末時点（rolling 3ヶ月平均）",
                    hovermode="x unified",
                    margin=dict(l=40, r=20, t=30, b=40),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                )
                st.plotly_chart(_fig_roll, use_container_width=True)

                # rolling の直近値をメトリクス表示
                _latest = _rolling_rows[-1]
                _cols_r = st.columns(3)
                for _col, _k, _lbl in [
                    (_cols_r[0], "5F", "5F 直近 rolling"),
                    (_cols_r[1], "6F", "6F 直近 rolling"),
                    (_cols_r[2], "all", "全体 直近 rolling"),
                ]:
                    _v = _latest[f"{_k}_pct"]
                    _stat = "🟢 クリア" if _v >= 15.0 else ("🟡 ギリギリ" if _v >= 13.0 else "🔴 未達")
                    _col.metric(
                        _lbl,
                        f"{_v:.1f}%",
                        help=f"分子 {_latest[f'{_k}_num']} / 分母 {_latest[f'{_k}_den']}",
                    )
                    _col.caption(_stat)

                # 表形式でも見せる（折りたたみ）
                with st.expander("月別 rolling 値の一覧（表）", expanded=False):
                    _df_roll = pd.DataFrame(_rolling_rows).rename(columns={
                        "month": "月末",
                        "5F_pct": "5F (%)", "6F_pct": "6F (%)", "all_pct": "全体 (%)",
                        "5F_num": "5F 分子", "5F_den": "5F 分母",
                        "6F_num": "6F 分子", "6F_den": "6F 分母",
                        "all_num": "全体 分子", "all_den": "全体 分母",
                    })
                    st.dataframe(
                        _df_roll[["月末", "5F (%)", "6F (%)", "全体 (%)",
                                  "5F 分子", "5F 分母", "6F 分子", "6F 分母",
                                  "全体 分子", "全体 分母"]],
                        use_container_width=True, hide_index=True,
                    )
            elif not _rolling_rows:
                st.info("rolling 3ヶ月を計算できる月がありません（3ヶ月以上のデータが必要）。")

            st.divider()

            # ===== B: イ/ロ/ハ判定の過去遡及 =====
            st.subheader("\U0001f4cb イ/ロ/ハ判定の過去遡及分布（2026改定 入院料1）")
            st.caption(
                "**判定ロジック:** 緊急入院×手術なし=**イ**(3,367点) / "
                "緊急×手術 or 予定×手術なし=**ロ**(3,267点) / "
                "予定×手術=**ハ**(3,117点)。病棟別に入院構成の差が見えます。"
            )
            from past_admissions_loader import tabulate_tier_distribution as _pa_tier
            _tier = _pa_tier(_pa_df)

            if _plotly_ok and _tier["total"] > 0:
                # 病棟別 スタック横棒グラフ（割合ベース）
                _wards = ["5F", "6F"]
                _total_5f = _tier["by_ward"]["5F"]["total"]
                _total_6f = _tier["by_ward"]["6F"]["total"]
                _pct_i = [
                    _tier["by_ward"]["5F"]["tier_i"] / _total_5f * 100 if _total_5f else 0,
                    _tier["by_ward"]["6F"]["tier_i"] / _total_6f * 100 if _total_6f else 0,
                ]
                _pct_ro = [
                    _tier["by_ward"]["5F"]["tier_ro"] / _total_5f * 100 if _total_5f else 0,
                    _tier["by_ward"]["6F"]["tier_ro"] / _total_6f * 100 if _total_6f else 0,
                ]
                _pct_ha = [
                    _tier["by_ward"]["5F"]["tier_ha"] / _total_5f * 100 if _total_5f else 0,
                    _tier["by_ward"]["6F"]["tier_ha"] / _total_6f * 100 if _total_6f else 0,
                ]
                _fig_tier = go.Figure()
                _fig_tier.add_trace(go.Bar(
                    name="イ (3,367点)", y=_wards, x=_pct_i, orientation="h",
                    marker_color="#10B981",
                    text=[f"{v:.1f}%" for v in _pct_i], textposition="inside",
                ))
                _fig_tier.add_trace(go.Bar(
                    name="ロ (3,267点)", y=_wards, x=_pct_ro, orientation="h",
                    marker_color="#F59E0B",
                    text=[f"{v:.1f}%" for v in _pct_ro], textposition="inside",
                ))
                _fig_tier.add_trace(go.Bar(
                    name="ハ (3,117点)", y=_wards, x=_pct_ha, orientation="h",
                    marker_color="#DC2626",
                    text=[f"{v:.1f}%" for v in _pct_ha], textposition="inside",
                ))
                _fig_tier.update_layout(
                    barmode="stack",
                    height=250,
                    xaxis_title="入院構成比 (%)",
                    margin=dict(l=40, r=20, t=30, b=40),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                )
                st.plotly_chart(_fig_tier, use_container_width=True)

                # 件数テーブル
                _cols_t = st.columns(3)
                _cols_t[0].metric(
                    "イ (緊急×無手術)", f"{_tier['tier_i']:,}件",
                    help=f"全体 {_tier['tier_i']/_tier['total']*100:.1f}% / 5F {_tier['by_ward']['5F']['tier_i']} / 6F {_tier['by_ward']['6F']['tier_i']}",
                )
                _cols_t[1].metric(
                    "ロ (緊急×手術 or 予定×無手術)", f"{_tier['tier_ro']:,}件",
                    help=f"全体 {_tier['tier_ro']/_tier['total']*100:.1f}% / 5F {_tier['by_ward']['5F']['tier_ro']} / 6F {_tier['by_ward']['6F']['tier_ro']}",
                )
                _cols_t[2].metric(
                    "ハ (予定×手術)", f"{_tier['tier_ha']:,}件",
                    help=f"全体 {_tier['tier_ha']/_tier['total']*100:.1f}% / 5F {_tier['by_ward']['5F']['tier_ha']} / 6F {_tier['by_ward']['6F']['tier_ha']}",
                )

                st.caption(
                    f"💡 **運用の含意:** 5F は手術系（ハ 26.7%）、"
                    f"6F は内科緊急系（イ 61.9%）の構成。"
                    f"2026改定で「ハ」は3,117点と最も低いため、"
                    f"5F の手術予定入院比率は収入面で注視が必要。"
                )

            # 短手3 推定（参考情報、分母には入れる）
            with st.expander("📎 短手3 推定（統計参考、救急比率の分母には常に含める）", expanded=False):
                from past_admissions_loader import summarize_short3_estimate as _pa_s3
                _s3 = _pa_s3(_pa_df)
                _cs3 = st.columns(3)
                _cs3[0].metric("手術あり全件", f"{_s3['total_surgeries']:,}")
                _cs3[1].metric("短手3 確実（≤2日）", f"{_s3['short3_certain']:,}")
                _cs3[2].metric("短手3 ほぼ確実（≤5日）", f"{_s3['short3_likely']:,}")
                st.caption(
                    "ヒューリスティック: 手術○ × 日数 ≤ 2 = 確実（大腸ポリペクトミー等）、"
                    "≤ 5 = ほぼ確実（短期滞在手術）。"
                    "**この識別は統計・収入分析用途のみ。"
                    "救急15%の分母からは一切除外しません**（制度ルール）。"
                )

            st.divider()

            # ===== C: 退経路別分析（2026-04-24 追加） =====
            st.subheader("\U0001f3e0 退経路別分析（9分類・病棟別）")
            st.caption(
                "退経路は 2026改定「在宅復帰率」の分子を決める。"
                "自宅・居住系・回復リ・地域包の4系を分子対象（病院機能により差あり）。"
            )
            from past_admissions_loader import tabulate_discharge_routes as _pa_routes
            _routes = _pa_routes(_pa_df)
            if _routes["total_with_discharge"] > 0:
                _route_order = ["自宅", "居住系", "介護老", "回復リ", "地域包", "病院他", "その他", "終了", "未記入"]
                _route_colors = {
                    "自宅": "#10B981",    # 緑（望ましい）
                    "居住系": "#34D399",   # 薄緑
                    "介護老": "#FCD34D",   # 黄
                    "回復リ": "#60A5FA",   # 青
                    "地域包": "#A78BFA",   # 紫
                    "病院他": "#F59E0B",   # 橙（転院）
                    "その他": "#9CA3AF",   # 灰
                    "終了": "#6B7280",    # 濃灰
                    "未記入": "#E5E7EB",   # 薄灰
                }
                _wards = ["5F", "6F"]
                if _plotly_ok:
                    _fig_routes = go.Figure()
                    for route in _route_order:
                        if route not in _routes["overall"]:
                            continue
                        _vals = []
                        for w in _wards:
                            total_w = sum(_routes["by_ward"][w].values())
                            cnt = _routes["by_ward"][w].get(route, 0)
                            _vals.append(cnt / total_w * 100 if total_w > 0 else 0)
                        _fig_routes.add_trace(go.Bar(
                            name=f"{route}",
                            y=_wards, x=_vals, orientation="h",
                            marker_color=_route_colors.get(route, "#9CA3AF"),
                            text=[f"{v:.1f}%" if v >= 3 else "" for v in _vals],
                            textposition="inside",
                            hovertemplate=f"%{{y}}<br>{route}: %{{x:.1f}}%<extra></extra>",
                        ))
                    _fig_routes.update_layout(
                        barmode="stack",
                        height=220,
                        xaxis_title="退経路構成比 (%)",
                        margin=dict(l=40, r=20, t=20, b=40),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                    )
                    st.plotly_chart(_fig_routes, use_container_width=True)
                # 在宅復帰率（自宅＋居住系）の指標
                _home_rate_overall = (
                    _routes["overall"].get("自宅", 0) + _routes["overall"].get("居住系", 0)
                ) / _routes["total_with_discharge"] * 100
                _home_5f = sum(_routes["by_ward"]["5F"].values())
                _home_6f = sum(_routes["by_ward"]["6F"].values())
                _home_5f_rate = (
                    _routes["by_ward"]["5F"].get("自宅", 0) + _routes["by_ward"]["5F"].get("居住系", 0)
                ) / _home_5f * 100 if _home_5f else 0
                _home_6f_rate = (
                    _routes["by_ward"]["6F"].get("自宅", 0) + _routes["by_ward"]["6F"].get("居住系", 0)
                ) / _home_6f * 100 if _home_6f else 0
                _cols_h = st.columns(3)
                _cols_h[0].metric("全体 自宅+居住系", f"{_home_rate_overall:.1f}%")
                _cols_h[1].metric("5F 自宅+居住系", f"{_home_5f_rate:.1f}%")
                _cols_h[2].metric("6F 自宅+居住系", f"{_home_6f_rate:.1f}%")
                st.caption(
                    "💡 自宅+居住系の合計が **在宅復帰率** の主要分子。"
                    "病院他（転院）が多い病棟は下り搬送の受け皿として機能。"
                )

            st.divider()

            # ===== D: 入院の季節性・曜日性（2026-04-24 追加） =====
            st.subheader("\U0001f4c5 入院の季節性・曜日性")
            st.caption(
                "月別・曜日別の入院パターンを可視化。"
                "救急曜日集中のピークと予定入院の平準化ポテンシャルを特定する。"
            )
            from past_admissions_loader import tabulate_seasonality as _pa_season
            _season = _pa_season(_pa_df)
            if _season["by_month"] and _plotly_ok:
                # 月別推移
                _months_s = sorted(_season["by_month"].keys())
                _vals_month = [_season["by_month"][m] for m in _months_s]
                _fig_month = go.Figure()
                _fig_month.add_trace(go.Bar(
                    x=_months_s, y=_vals_month,
                    marker_color="#374151",
                    text=_vals_month, textposition="outside",
                    hovertemplate="%{x}<br>%{y} 件<extra></extra>",
                ))
                _avg_month = sum(_vals_month) / len(_vals_month) if _vals_month else 0
                _fig_month.add_hline(
                    y=_avg_month, line_dash="dash", line_color="#DC2626",
                    annotation_text=f"年間平均 {_avg_month:.0f}件",
                    annotation_position="top right",
                )
                _fig_month.update_layout(
                    height=280,
                    yaxis_title="月間入院数 (件)",
                    xaxis_title="月",
                    margin=dict(l=40, r=20, t=20, b=40),
                    showlegend=False,
                )
                st.plotly_chart(_fig_month, use_container_width=True)

                # 曜日別（救急 vs 予定）
                _wd_labels_s = ["月", "火", "水", "木", "金", "土", "日"]
                _fig_wd = go.Figure()
                _fig_wd.add_trace(go.Bar(
                    name="救急搬送",
                    x=_wd_labels_s,
                    y=[_season["emergency_by_weekday"].get(w, 0) for w in _wd_labels_s],
                    marker_color="#DC2626",
                    hovertemplate="%{x}曜<br>救急: %{y}件<extra></extra>",
                ))
                _fig_wd.add_trace(go.Bar(
                    name="予定入院",
                    x=_wd_labels_s,
                    y=[_season["scheduled_by_weekday"].get(w, 0) for w in _wd_labels_s],
                    marker_color="#2563EB",
                    hovertemplate="%{x}曜<br>予定: %{y}件<extra></extra>",
                ))
                _other_by_wd = [
                    _season["by_weekday"].get(w, 0)
                    - _season["emergency_by_weekday"].get(w, 0)
                    - _season["scheduled_by_weekday"].get(w, 0)
                    for w in _wd_labels_s
                ]
                _fig_wd.add_trace(go.Bar(
                    name="その他（予定外非救急）",
                    x=_wd_labels_s, y=_other_by_wd,
                    marker_color="#9CA3AF",
                    hovertemplate="%{x}曜<br>その他: %{y}件<extra></extra>",
                ))
                _fig_wd.update_layout(
                    barmode="stack",
                    height=280,
                    yaxis_title="年間入院数 (件)",
                    xaxis_title="曜日",
                    margin=dict(l=40, r=20, t=20, b=40),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                )
                st.plotly_chart(_fig_wd, use_container_width=True)
                _peak_wd = max(_wd_labels_s, key=lambda w: _season["by_weekday"].get(w, 0))
                _low_wd = min(_wd_labels_s, key=lambda w: _season["by_weekday"].get(w, 0))
                st.caption(
                    f"💡 **ピーク曜日:** {_peak_wd}（{_season['by_weekday'][_peak_wd]}件）／"
                    f"**底曜日:** {_low_wd}（{_season['by_weekday'][_low_wd]}件）。"
                    "曜日差が大きければ予定入院の平準化で稼働率安定化の余地あり。"
                )

            st.divider()

            # ===== E: 短手3 内訳（診療科別・医師別）（2026-04-24 追加） =====
            st.subheader("\U0001f50d 短手3 内訳（診療科別・医師別）")
            st.caption(
                "手術×日数ヒューリスティックの詳細分解。"
                "短手3 の増減計画立案・収入影響分析に使用（救急15%計算には未使用）。"
            )
            from past_admissions_loader import tabulate_short3_breakdown as _pa_s3b
            _s3b = _pa_s3b(_pa_df)
            if _s3b["by_department_certain"] or _s3b["by_department_likely"]:
                _cols_s3b = st.columns(2)
                with _cols_s3b[0]:
                    st.markdown("**診療科別 確実（≤2日）**")
                    if _s3b["top_departments_certain"]:
                        for dept, cnt in _s3b["top_departments_certain"]:
                            st.text(f"  {dept}: {cnt} 件")
                    else:
                        st.caption("該当なし")
                with _cols_s3b[1]:
                    st.markdown("**医師別 確実（≤2日） Top 5**")
                    if _s3b["top_doctors_certain"]:
                        for doc, cnt in _s3b["top_doctors_certain"]:
                            st.text(f"  {doc}: {cnt} 件")
                    else:
                        st.caption("該当なし")

                with st.expander("📊 ほぼ確実（≤5日）の診療科別", expanded=False):
                    if _s3b["by_department_likely"]:
                        _df_likely = pd.DataFrame([
                            {"診療科": k, "件数": v}
                            for k, v in sorted(
                                _s3b["by_department_likely"].items(),
                                key=lambda x: x[1], reverse=True
                            )
                        ])
                        st.dataframe(_df_likely, use_container_width=True, hide_index=True)

            st.divider()

            # ===== F: 手術有無別 LOS 比較（2026-04-24 追加） =====
            st.subheader("\u23f1\ufe0f 手術有無別 平均在院日数（LOS）比較")
            st.caption(
                "手術の有無で LOS がどう変わるかを病棟別・診療科別に可視化。"
                "入院計画立案時の日数見積に使う。"
            )
            from past_admissions_loader import tabulate_los_by_surgery as _pa_los
            _los = _pa_los(_pa_df)
            if _los["surgery_yes"]["count"] > 0 or _los["surgery_no"]["count"] > 0:
                _cols_los = st.columns(4)
                _cols_los[0].metric(
                    "全体 手術あり 中央値",
                    f"{_los['surgery_yes']['median']:.1f} 日",
                    help=f"n={_los['surgery_yes']['count']} / 平均 {_los['surgery_yes']['mean']:.1f}",
                )
                _cols_los[1].metric(
                    "全体 手術なし 中央値",
                    f"{_los['surgery_no']['median']:.1f} 日",
                    help=f"n={_los['surgery_no']['count']} / 平均 {_los['surgery_no']['mean']:.1f}",
                )
                _diff = _los["surgery_no"]["median"] - _los["surgery_yes"]["median"]
                _cols_los[2].metric(
                    "差（手術なし − あり）",
                    f"{_diff:+.1f} 日",
                    help="通常は手術なしの方が長い（保存的治療 or 介護的）",
                )
                _cols_los[3].metric(
                    "全体 手術あり P75",
                    f"{_los['surgery_yes']['p75']:.1f} 日",
                    help="上位25%の境界（長期化の目安）",
                )

                # 病棟別・診療科別テーブル
                _rows_los = []
                for w in ("5F", "6F"):
                    _rows_los.append({
                        "区分": f"{w} 病棟",
                        "手術あり 中央値": f"{_los['by_ward'][w]['surgery_yes']['median']:.1f}",
                        "手術あり n": _los['by_ward'][w]['surgery_yes']['count'],
                        "手術なし 中央値": f"{_los['by_ward'][w]['surgery_no']['median']:.1f}",
                        "手術なし n": _los['by_ward'][w]['surgery_no']['count'],
                    })
                for dept, stats in sorted(
                    _los["by_department"].items(),
                    key=lambda x: -(x[1]["surgery_yes"]["count"] + x[1]["surgery_no"]["count"]),
                )[:8]:
                    _rows_los.append({
                        "区分": f"[{dept}]",
                        "手術あり 中央値": f"{stats['surgery_yes']['median']:.1f}",
                        "手術あり n": stats['surgery_yes']['count'],
                        "手術なし 中央値": f"{stats['surgery_no']['median']:.1f}",
                        "手術なし n": stats['surgery_no']['count'],
                    })
                st.dataframe(
                    pd.DataFrame(_rows_los),
                    use_container_width=True, hide_index=True,
                )
                st.caption(
                    "💡 診療科は退院済み ≥5 件のみ表示（統計的意義確保）。"
                    "中央値同士の差が診療科横断で顕著なら、ベッド計画の科別補正が有効。"
                )

        # ===== G: 看護必要度トレンド（Stage A, 2026-04-25 追加） =====
        # 地域包括医療病棟の看護必要度Ⅰ/Ⅱ 該当患者割合を 12 ヶ月時系列で可視化。
        # 2026-06-01 から新基準（Ⅰ16%→19%, Ⅱ14%→18%）が適用されるため、
        # 旧/新両基準を並列表示して、移行までのギャップを副院長に明示する。
        _nn_df = st.session_state.get("nursing_necessity_df", pd.DataFrame())
        if _NURSING_NECESSITY_AVAILABLE and not _nn_df.empty:
            st.divider()
            _bc_section_title(
                "看護必要度トレンド（地域包括医療病棟基準）",
                icon="📊",
            )
            st.caption(
                "事務提供の **1,095 行**（12 ヶ月 × 3 病棟 × 365 日）から、地域包括医療病棟基準の達成状況を可視化。"
                f"**経過措置終了まで残 {days_until_transitional_end()} 日**: "
                f"2026-06-01 から新基準（Ⅰ {THRESHOLD_I_NEW:.0%}, Ⅱ {THRESHOLD_II_NEW:.0%}）が適用されます。"
            )

            # ===== 📚 看護必要度ミニレクチャー（医師・看護師の協力で達成する） =====
            # 当院特有の戦略・役割分担・実践 TIPS を網羅した教育コンテンツ。
            # データを見る前にまず制度を理解する人向けに上部配置（デフォルト閉じる）。
            if _NN_LECTURE_MD:
                with st.expander(
                    "📚 看護必要度ミニレクチャー — 医師・看護師の協力で達成する（クリックで展開）",
                    expanded=False,
                ):
                    st.markdown(_NN_LECTURE_MD)
                    # レクチャー直下に参考エビデンス・出典をオフライン対応で描画
                    # 公式 PDF（厚労省・日循）+ 要約 markdown + 評価項目表画像 を統一管理
                    if _nn_render_references is not None:
                        import os as _nn_os
                        _nn_project_root = _nn_os.path.normpath(
                            _nn_os.path.join(_nn_os.path.dirname(_nn_os.path.abspath(__file__)), "..")
                        )
                        st.markdown("---")
                        _nn_render_references(st, _nn_project_root)

            try:
                import plotly.graph_objects as go

                _nn_monthly = nn_calculate_monthly_summary(_nn_df)
                _nn_yearly = nn_calculate_yearly_average(_nn_df)

                # ===== 救急患者応需係数の計算（過去 1 年実データから）=====
                # 令和8改定で新設。年間救急搬送 ÷ 病床数 × 0.005（上限 10%）を
                # 看護必要度該当患者割合に加算して新基準と比較する。
                _nn_pa_df = st.session_state.get("past_admissions_df", pd.DataFrame())
                _nn_emergency_count = 0
                if isinstance(_nn_pa_df, pd.DataFrame) and not _nn_pa_df.empty and "is_emergency_transport" in _nn_pa_df.columns:
                    _nn_emergency_count = int(_nn_pa_df["is_emergency_transport"].sum())
                _nn_bed_count = 94  # 5F 47 + 6F 47
                if _nn_emergency_count > 0:
                    _nn_coef_dict = nn_calc_response_coef(
                        annual_emergency_count=_nn_emergency_count,
                        bed_count=_nn_bed_count,
                    )
                    _nn_coef = _nn_coef_dict["coefficient"]
                else:
                    _nn_coef = 0.0
                    _nn_coef_dict = {"per_bed_count": 0, "coefficient_raw": 0, "capped": False}

                # 救急応需係数のサマリーカード
                _bc_alert(
                    f"**🚑 救急患者応需係数（令和8改定で新設）**: "
                    f"年間救急搬送 {_nn_emergency_count} 件 ÷ {_nn_bed_count} 床 × 0.005 "
                    f"= **{_nn_coef * 100:.2f}%**（上限 {EMERGENCY_RESPONSE_COEFFICIENT_CAP:.0%}）"
                    f"<br>この値が **新基準 19% / 18% に対して該当患者割合に加算**されます（旧基準には不適用）。",
                    severity="info",
                )

                # ===== 12ヶ月平均カード（4 枚: 5F-Ⅰ, 5F-Ⅱ, 6F-Ⅰ, 6F-Ⅱ）=====
                st.markdown("**12 ヶ月通算平均 vs 新基準（応需係数加算後）**")
                _nn_cols = st.columns(4)
                _nn_card_specs = [
                    ("5F", "I", THRESHOLD_I_NEW, "5F 必要度Ⅰ", _nn_cols[0]),
                    ("5F", "II", THRESHOLD_II_NEW, "5F 必要度Ⅱ", _nn_cols[1]),
                    ("6F", "I", THRESHOLD_I_NEW, "6F 必要度Ⅰ", _nn_cols[2]),
                    ("6F", "II", THRESHOLD_II_NEW, "6F 必要度Ⅱ", _nn_cols[3]),
                ]
                for ward, typ, new_th, label, col in _nn_card_specs:
                    _row = _nn_yearly[_nn_yearly["ward"] == ward]
                    if _row.empty:
                        continue
                    _rate = _row[f"{typ}_rate1_avg"].iloc[0]
                    _adjusted = _rate + _nn_coef
                    _gap = _adjusted - new_th
                    _sev = "success" if _gap >= 0 else ("warning" if _gap >= -0.02 else "danger")
                    with col:
                        _bc_kpi_card(
                            label,
                            f"{_adjusted * 100:.2f}",
                            "%",
                            severity=_sev,
                            size="md",
                            delta=f"実績{_rate * 100:.2f}% + 応需{_nn_coef * 100:.2f}% ／ 新基準{new_th:.0%} 比 {_gap * 100:+.2f}pt",
                        )

                # ===== 必要度Ⅰ 月次折れ線グラフ =====
                st.markdown("**必要度Ⅰ 月次推移（5F / 6F、応需係数加算後）**")
                _fig_i = go.Figure()
                for ward, color in [("5F", _DT_WARD_5F), ("6F", _DT_WARD_6F)]:
                    sub = _nn_monthly[_nn_monthly["ward"] == ward].sort_values("ym")
                    # 実線 = 加算後（実態判定）、点線 = 実績
                    adjusted_y = (sub["I_rate1"] + _nn_coef) * 100
                    _fig_i.add_trace(go.Scatter(
                        x=sub["ym"], y=adjusted_y,
                        mode="lines+markers", name=f"{ward}（加算後）",
                        line=dict(color=color, width=2.5),
                    ))
                    _fig_i.add_trace(go.Scatter(
                        x=sub["ym"], y=sub["I_rate1"] * 100,
                        mode="lines", name=f"{ward}（実績）",
                        line=dict(color=color, width=1, dash="dot"),
                        opacity=0.5,
                    ))
                # 旧基準・新基準のしきい値ライン
                _fig_i.add_hline(
                    y=THRESHOLD_I_LEGACY * 100, line_dash="dot",
                    line_color=_DT_TEXT_MUTED,
                    annotation_text=f"旧基準 {THRESHOLD_I_LEGACY:.0%}",
                    annotation_position="bottom right",
                )
                _fig_i.add_hline(
                    y=THRESHOLD_I_NEW * 100, line_dash="dash",
                    line_color=_DT_DANGER,
                    annotation_text=f"新基準 {THRESHOLD_I_NEW:.0%}（2026-06-01〜）",
                    annotation_position="top right",
                )
                _fig_i.update_layout(
                    height=320, margin=dict(l=10, r=10, t=10, b=10),
                    yaxis=dict(title="該当患者割合 (%)", range=[0, 30]),
                    xaxis=dict(title="月"),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02),
                    plot_bgcolor="white",
                )
                st.plotly_chart(_fig_i, use_container_width=True)

                # ===== 必要度Ⅱ 月次折れ線グラフ =====
                st.markdown("**必要度Ⅱ 月次推移（5F / 6F、応需係数加算後）**")
                _fig_ii = go.Figure()
                for ward, color in [("5F", _DT_WARD_5F), ("6F", _DT_WARD_6F)]:
                    sub = _nn_monthly[_nn_monthly["ward"] == ward].sort_values("ym")
                    adjusted_y_ii = (sub["II_rate1"] + _nn_coef) * 100
                    _fig_ii.add_trace(go.Scatter(
                        x=sub["ym"], y=adjusted_y_ii,
                        mode="lines+markers", name=f"{ward}（加算後）",
                        line=dict(color=color, width=2.5),
                    ))
                    _fig_ii.add_trace(go.Scatter(
                        x=sub["ym"], y=sub["II_rate1"] * 100,
                        mode="lines", name=f"{ward}（実績）",
                        line=dict(color=color, width=1, dash="dot"),
                        opacity=0.5,
                    ))
                _fig_ii.add_hline(
                    y=THRESHOLD_II_LEGACY * 100, line_dash="dot",
                    line_color=_DT_TEXT_MUTED,
                    annotation_text=f"旧基準 {THRESHOLD_II_LEGACY:.0%}",
                    annotation_position="bottom right",
                )
                _fig_ii.add_hline(
                    y=THRESHOLD_II_NEW * 100, line_dash="dash",
                    line_color=_DT_DANGER,
                    annotation_text=f"新基準 {THRESHOLD_II_NEW:.0%}（2026-06-01〜）",
                    annotation_position="top right",
                )
                _fig_ii.update_layout(
                    height=320, margin=dict(l=10, r=10, t=10, b=10),
                    yaxis=dict(title="該当患者割合 (%)", range=[0, 30]),
                    xaxis=dict(title="月"),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02),
                    plot_bgcolor="white",
                )
                st.plotly_chart(_fig_ii, use_container_width=True)

                # ===== 月別達成マトリクス =====
                with st.expander("📋 月別達成マトリクス（応需係数加算後で新基準判定）", expanded=False):
                    st.caption(
                        f"応需係数 +{_nn_coef * 100:.2f}% を加算して判定。"
                        "✅=加算後で新基準達成 / ⚠️=加算後でも旧基準のみ達成（新未達）/ 🔴=加算後でも両基準未達"
                    )
                    _matrix_rows = []
                    for ym in sorted(_nn_monthly["ym"].unique()):
                        _row = {"月": ym}
                        for ward in ["5F", "6F"]:
                            for typ in ["I", "II"]:
                                _r = _nn_monthly[
                                    (_nn_monthly["ym"] == ym) & (_nn_monthly["ward"] == ward)
                                ]
                                if _r.empty:
                                    _row[f"{ward}-{typ}"] = "-"
                                    continue
                                _rate = _r[f"{typ}_rate1"].iloc[0]
                                _adjusted = _rate + _nn_coef
                                _new_th = THRESHOLD_I_NEW if typ == "I" else THRESHOLD_II_NEW
                                _legacy_th = THRESHOLD_I_LEGACY if typ == "I" else THRESHOLD_II_LEGACY
                                _meets_new_adj = _adjusted >= _new_th
                                _meets_legacy_adj = _adjusted >= _legacy_th
                                if _meets_new_adj:
                                    icon = "✅"
                                elif _meets_legacy_adj:
                                    icon = "⚠️"
                                else:
                                    icon = "🔴"
                                _row[f"{ward}-{typ}"] = f"{icon} {_adjusted * 100:.2f}%"
                        _matrix_rows.append(_row)
                    st.dataframe(
                        pd.DataFrame(_matrix_rows),
                        use_container_width=True, hide_index=True,
                    )

                st.caption(
                    f"💡 **読み方**: 応需係数 +{_nn_coef * 100:.2f}% を加算しても "
                    "⚠️/🔴 が並ぶ月は実態として基準未達。"
                    "特に直近 (2026-1〜3) で 6F が新基準未達状態が続いているため、"
                    "6/1 移行時のリスクが高い。"
                    "改善策: ①救急受入を増やして応需係数を上げる ②重症患者比率を上げる "
                    "③短手3比率を見直す。"
                )
            except Exception as _nn_err:
                st.warning(f"⚠️ 看護必要度トレンドの描画でエラー: {_nn_err}")

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
        _annual_loss_total = 0  # Hint 1 で算出、他Hintで参照

        # =====================================================================
        # Hint 1: 稼働率ギャップ
        # =====================================================================
        if isinstance(_daily_df, pd.DataFrame) and len(_daily_df) > 0:
            if "ward" in _daily_df.columns:
                if _selected_ward_key in ("5F", "6F"):
                    _hint_daily = _daily_df[_daily_df["ward"] == _selected_ward_key]
                else:
                    _hint_daily = _daily_df.groupby("date").agg({"total_patients": "sum"}).reset_index()
                _latest_data = _hint_daily.sort_values("date").tail(7)
            else:
                _latest_data = _daily_df.sort_values("date").tail(7)
            _avg_occ_7d = _latest_data["total_patients"].mean() / _view_beds * 100
            _gap = _target_occ_pct - _avg_occ_7d
            if _gap > 0:
                _hints_found = True
                _annual_loss = _gap * _ANNUAL_VALUE_PER_1PCT
                _annual_loss_total = _annual_loss
                _profit_pct = _annual_loss / _OPERATING_PROFIT * 100

                with st.expander("⚠️ 稼働率ギャップ", expanded=True):
                    # --- 検出アラート ---
                    st.markdown(f"""
                    <div style="background: #FFF7ED; border-left: 4px solid #F97316; padding: 8px; border-radius: 4px; margin-bottom: 8px;">
                        <strong style="color: #1E293B;">⚠️ 稼働率ギャップ検出</strong><br>
                        <span style="color: #64748B;">直近7日平均: <strong>{_avg_occ_7d:.1f}%</strong>（目標{_target_occ_pct:.0f}%まで<strong>{_gap:.1f}%</strong>）</span>
                        <span style="color: #EF4444; font-weight: bold;"> → 年間{_annual_loss/10000:.0f}万円相当</span>
                    </div>
                    """, unsafe_allow_html=True)

                    st.caption("具体策: ① 金+土退院の月曜以降への振替 ② 医師別退院曜日調整 ③ 在院日数の最適化")

                    # --- What-If シミュレーション ---
                    st.markdown("##### 🔧 What-If シミュレーション")
                    _hint1_default = min(_gap, 5.0)
                    _hint1_default_rounded = round(_hint1_default * 2) / 2  # 0.5刻みに丸め
                    _hint1_target = st.slider(
                        "稼働率改善目標（%ポイント）",
                        min_value=0.5, max_value=10.0, step=0.5,
                        value=min(_hint1_default_rounded, 10.0),
                        key="_hint_occ_slider",
                    )
                    _hint1_annual_value = _hint1_target * _ANNUAL_VALUE_PER_1PCT
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
                        f"（職員一人あたり年間 **{_hint1_per_person/10000:.1f}万円**）"
                    )

        # =====================================================================
        # 📊 空床マネジメント指標（週末空床コスト）
        # 空床マネジメントの核心: 退院タイミングを整えて空床時間を最小化する
        # 当院は土曜入院も1-2件程度のため、土日2日間を「谷」として計算
        # =====================================================================
        if isinstance(_daily_df, pd.DataFrame) and len(_daily_df) > 0 and _BED_MGMT_METRICS_AVAILABLE:
            # --- 空床マネジメント指標: bed_management_metrics モジュールで算出 ---
            _bed_mgmt_df = prepare_bed_mgmt_daily_df(_daily_df, _selected_ward_key, _view_beds)
            _wem = calculate_weekend_empty_metrics(_bed_mgmt_df, _view_beds)
            _weekend_empty = _wem["weekend_empty"]
            _fri_dis = _wem["fri_dis"]
            _mon_adm = _wem["mon_adm"]
            _fill_rate = _wem["fri_to_mon_fill_rate"]
            _reuse = calculate_next_day_reuse_rate(_bed_mgmt_df)
            _reuse_rate = _reuse["reuse_rate"]
            _wcosts = calculate_weekend_costs(_weekend_empty, _UNIT_PRICE_PER_DAY)
            _weekend_cost_per_week = _wcosts["weekly"]
            _weekend_cost_annual = _wcosts["annual"]

            if _weekend_empty > 2:  # 空床が目立つ場合にのみ表示
                _hints_found = True
                with st.expander("📊 週末空床コスト（空床マネジメントの指標）", expanded=True):
                    st.markdown(f"""
                    <div style="background: #EFF6FF; border-left: 4px solid #3B82F6; padding: 8px; border-radius: 4px; margin-bottom: 8px;">
                        <strong style="color: #1E293B; font-size: 16px;">📊 空床マネジメント指標</strong><br>
                        <span style="color: #475569;">空床マネジメント = 退院タイミングを整えて、空いた床を遊ばせない</span><br>
                        <span style="color: #64748B; font-size: 0.85em;">※ 当院は救急・予定外入院が8割。「誰が入るか」ではなく「空床時間」を減らすのが本質</span>
                    </div>
                    """, unsafe_allow_html=True)

                    _bm1, _bm2, _bm3, _bm4 = st.columns(4)
                    _bm1.metric(
                        "土日 平均空床数",
                        f"{_weekend_empty:.1f}床",
                        help="土日の平均空床数。当院は土曜入院も1-2件/日程度なので土日2日間が谷底",
                    )
                    _bm2.metric(
                        "週末空床コスト",
                        f"¥{_weekend_cost_per_week/10000:.0f}万/週",
                        delta=f"年間 約{_weekend_cost_annual/10000:.0f}万",
                        delta_color="inverse",
                        help=f"空床{_weekend_empty:.0f}床 × 2日(土日) × ¥{_UNIT_PRICE_PER_DAY:,}/床日",
                    )
                    _bm3.metric(
                        "退院翌日再利用率",
                        f"{_reuse_rate:.0f}%",
                        help="退院で空いた床が翌日の入院で埋まった割合。高いほど空床時間が短い",
                    )
                    _bm4.metric(
                        "金→月 充填率",
                        f"{_fill_rate:.0f}%",
                        help=f"金曜退院 平均{_fri_dis:.1f}人 → 月曜入院 平均{_mon_adm:.1f}人",
                    )

                    # ---------------------------------------------------------
                    # 📝 What-If: 退院前倒し × 充填確率  ── 経営会議提案から除外
                    # ---------------------------------------------------------
                    # 2026-04-17 副院長判断で、木曜前倒し運用（Phase 1）を
                    # 独立提案から撤回しました。過去 12ヶ月データ検証の結果、
                    # 高需要週は年 2〜3 回のみで経営インパクトが 50〜150 万円
                    # と限定的と判明したためです。Phase 2 連休対策と
                    # Phase 3α 需要予測ダッシュボードの実装に注力します。
                    #
                    # なお、計算ロジック（forecast_weekly_demand /
                    # calculate_weekend_whatif / estimate_existing_vacancy）は
                    # Phase 2 での再利用を見越して保持しています。
                    st.caption(
                        "💡 木曜前倒し運用は過去12ヶ月データで検証した結果、"
                        "高需要週が年2-3回のみで経営インパクトが限定的と判明したため、"
                        "経営会議提案から除外しました（2026-04-17 副院長判断）。"
                        "Phase 2 連休対策・Phase 3α 需要予測に注力します。"
                    )

        # =====================================================================
        # Hint 2: 金+土退院の集中（2026-04-25 副院長判断で「金曜→火〜木前倒し」から
        # 「金+土→月曜以降後ろ倒し」に思想転換）
        # =====================================================================
        if isinstance(_detail_df, pd.DataFrame) and len(_detail_df) > 0:
            _wd_dist = get_discharge_weekday_distribution(_detail_df)
            if _wd_dist:
                _total_dis_h = sum(_wd_dist.values())
                if _total_dis_h > 0:
                    _fri_count = _wd_dist.get(4, 0)
                    _sat_count = _wd_dist.get(5, 0)
                    _fri_sat_count = _fri_count + _sat_count
                    _fri_sat_pct_h = _fri_sat_count / _total_dis_h * 100
                    # 金+土退院率が peer 中央値（実データ 33.8%）相当を超えたら検出
                    if _fri_sat_pct_h > 30:
                        _hints_found = True

                        with st.expander("⚠️ 金+土退院の集中", expanded=True):
                            # --- 検出アラート ---
                            st.markdown(f"""
                            <div style="background: #FFF7ED; border-left: 4px solid #F97316; padding: 8px; border-radius: 4px; margin-bottom: 8px;">
                                <strong style="color: #1E293B;">⚠️ 金+土退院の集中検出</strong> —
                                <span style="color: #64748B;">金 {_fri_count} 件 + 土 {_sat_count} 件 = {_fri_sat_count} 件（<strong>{_fri_sat_pct_h:.0f}%</strong>）→ 土日稼働率低下の要因</span>
                            </div>
                            """, unsafe_allow_html=True)

                            # --- 医師別の金+土集中テーブル ---
                            st.markdown("##### 📋 医師別 金+土退院率")
                            _dis_df_h2 = _detail_df[_detail_df["event_type"] == "discharge"]
                            _doc_names_h2 = sorted(_dis_df_h2["attending_doctor"].unique())
                            _fri_sat_table_rows = []
                            for _dn in _doc_names_h2:
                                _doc_wd = get_discharge_weekday_distribution(_detail_df, _dn)
                                if _doc_wd and sum(_doc_wd.values()) > 0:
                                    _d_total = sum(_doc_wd.values())
                                    _d_fri = _doc_wd.get(4, 0)
                                    _d_sat = _doc_wd.get(5, 0)
                                    _d_fri_sat = _d_fri + _d_sat
                                    _d_fri_sat_pct = _d_fri_sat / _d_total * 100
                                    _fri_sat_table_rows.append({
                                        "医師名": _dn,
                                        "総退院数": _d_total,
                                        "金曜": _d_fri,
                                        "土曜": _d_sat,
                                        "金+土率(%)": round(_d_fri_sat_pct, 1),
                                        "集中": "⚠️" if _d_fri_sat_pct > 40 else "",
                                    })
                            if _fri_sat_table_rows:
                                _fri_sat_table_df = pd.DataFrame(_fri_sat_table_rows).sort_values("金+土率(%)", ascending=False)
                                st.dataframe(_fri_sat_table_df, use_container_width=True, hide_index=True)

                            # --- What-If シミュレーション ---
                            st.markdown("##### 🔧 What-If シミュレーション")
                            st.caption(
                                "💡 **退院日を月曜以降に振り替える** ことで、土日空床を抑制します。"
                                "金曜退院 1 件 → 月曜以降に振替で **土日 2 日分**、"
                                "土曜退院 1 件 → 月曜以降に振替で **日曜 1 日分** の空床を防止。"
                                "なお **日曜・祝日も 1 病棟あたり 2 人/日 まで** は退院可能（補助枠として活用）。"
                            )
                            _hint2_move_pct = st.slider(
                                "金+土退院のうち月曜以降に振り替える割合（%）",
                                min_value=0, max_value=100, step=10, value=50,
                                key="_hint_fri_slider",
                            )
                            _hint2_fri_moved = int(_fri_count * _hint2_move_pct / 100)
                            _hint2_sat_moved = int(_sat_count * _hint2_move_pct / 100)
                            # 金曜→月曜 = 土日2日分、土曜→月曜 = 日曜1日分
                            _hint2_weekend_saved = (
                                _hint2_fri_moved * 2 + _hint2_sat_moved * 1
                            ) * _UNIT_PRICE_PER_DAY
                            _hint2_annual = _hint2_weekend_saved * 12
                            _hint2_moved = _hint2_fri_moved + _hint2_sat_moved
                            _hint2_profit_pct = _hint2_annual / _OPERATING_PROFIT * 100

                            _hint_savings["金+土退院振替"] = _hint2_annual

                            # Before/After の曜日分布チャート
                            _before_vals = [_wd_dist.get(i, 0) for i in range(7)]
                            _after_vals = list(_before_vals)
                            # 金・土から月曜以降（月・火・水・木）に均等振り分け
                            _after_vals[4] = max(0, _after_vals[4] - _hint2_fri_moved)
                            _after_vals[5] = max(0, _after_vals[5] - _hint2_sat_moved)
                            _per_day_add = _hint2_moved / 4  # 月・火・水・木に均等配分
                            for _di in [0, 1, 2, 3]:
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
                                st.metric(
                                    "振替する退院件数",
                                    f"{_hint2_moved}件/月",
                                    help=f"金 {_hint2_fri_moved} 件 + 土 {_hint2_sat_moved} 件",
                                )
                            with _h2c2:
                                st.metric("年間改善額", f"{_hint2_annual/10000:.0f}万円",
                                          delta="改善余地あり")
                            if _annual_loss_total > 0:
                                _h2_gap_pct = min(100, _hint2_annual / _annual_loss_total * 100)
                                st.caption(f"→ 稼働率ギャップ（年間{_annual_loss_total/10000:.0f}万円）の **{_h2_gap_pct:.0f}%** をカバー")

        # =====================================================================
        # Hint 3: 医師別の退院曜日偏り
        # =====================================================================
        if isinstance(_detail_df, pd.DataFrame) and len(_detail_df) > 0:
            _dis_df_h3 = _detail_df[_detail_df["event_type"] == "discharge"]
            _doc_names_h3 = sorted(_dis_df_h3["attending_doctor"].unique())
            if len(_doc_names_h3) > 0:
                with st.expander("🔍 医師別の退院曜日偏り", expanded=False):
                    st.caption(
                        "特定医師の退院曜日を調整した場合の効果をシミュレーション "
                        "（金+土退院 → 月曜以降への振替。日曜・祝日も 1 病棟 2 人/日 まで補助枠として活用可）"
                    )

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
                        _doc_sat_h3 = _doc_vals_h3[5]
                        _doc_fri_sat_h3 = _doc_fri_h3 + _doc_sat_h3

                        # 医師の現在の分布チャート（金・土を強調）
                        _fig_h3 = go.Figure()
                        _colors_h3 = ["#EF4444" if i in (4, 5) else "#3B82F6" for i in range(7)]
                        _fig_h3.add_trace(go.Bar(
                            x=_wd_labels, y=_doc_vals_h3,
                            marker_color=_colors_h3,
                        ))
                        _fig_h3.update_layout(
                            height=250,
                            title=f"{_hint3_doc} の退院曜日分布（金・土を強調）",
                            xaxis_title="曜日", yaxis_title="退院件数",
                            margin=dict(t=40, b=40, l=40, r=20),
                            showlegend=False,
                        )
                        st.plotly_chart(_fig_h3, use_container_width=True)

                        # What-If: この医師の金+土退院を月曜以降に振替
                        st.markdown("##### 🔧 What-If シミュレーション")
                        _hint3_max_move = max(int(_doc_fri_sat_h3), 0)
                        if _hint3_max_move > 0:
                            _hint3_move = st.slider(
                                f"この医師の金+土退院を何件月曜以降に振替？",
                                min_value=0, max_value=_hint3_max_move, step=1,
                                value=min(_hint3_max_move, max(1, _hint3_max_move // 2)),
                                key="_hint_doc_fri_slider",
                            )
                            # 金:土 の比率で按分（実態に合わせる）
                            if _doc_fri_sat_h3 > 0:
                                _move_fri = round(_hint3_move * _doc_fri_h3 / _doc_fri_sat_h3)
                            else:
                                _move_fri = 0
                            _move_sat = _hint3_move - _move_fri
                            # 金曜→月曜 = 土日2日分、土曜→月曜 = 日曜1日分
                            _hint3_saved = (_move_fri * 2 + _move_sat * 1) * _UNIT_PRICE_PER_DAY * 12
                            _hint3_profit = _hint3_saved / _OPERATING_PROFIT * 100

                            _hint_savings[f"{_hint3_doc}退院振替"] = _hint3_saved

                            # Before/After（金土から月〜木に振り分け）
                            _after_h3 = list(_doc_vals_h3)
                            _after_h3[4] = max(0, _after_h3[4] - _move_fri)
                            _after_h3[5] = max(0, _after_h3[5] - _move_sat)
                            _per_day_h3 = _hint3_move / 4
                            for _di in [0, 1, 2, 3]:
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
                                st.metric(
                                    "振替する退院件数",
                                    f"{_hint3_move}件/月",
                                    help=f"金 {_move_fri} 件 + 土 {_move_sat} 件",
                                )
                            with _h3c2:
                                st.metric("年間改善額", f"{_hint3_saved/10000:.0f}万円",
                                          delta="改善余地あり")
                            if _annual_loss_total > 0:
                                _h3_gap_pct = min(100, _hint3_saved / _annual_loss_total * 100)
                                st.caption(f"→ 稼働率ギャップの **{_h3_gap_pct:.0f}%** をカバー")
                        else:
                            st.info(f"{_hint3_doc} の金+土退院は0件です。調整の必要はありません。")
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
                            <div style="background: #FFF7ED; border-left: 4px solid #F97316; padding: 8px; border-radius: 4px; margin-bottom: 8px;">
                                <strong style="color: #1E293B;">📊 在院日数の偏り検出</strong> —
                                <span style="color: #64748B;">{"、".join(_outlier_msgs)}</span>
                            </div>
                            """, unsafe_allow_html=True)
                            _hints_found = True
                        else:
                            st.caption("医師別の在院日数を調整した場合の効果を試算")

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
                            min_value=-15.0, max_value=15.0, step=0.5, value=0.0,
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
                                )
                                if _annual_loss_total > 0:
                                    _h4_gap_pct = min(100, _h4_annual_value / _annual_loss_total * 100)
                                    st.caption(f"→ 稼働率ギャップの **{_h4_gap_pct:.0f}%** をカバー")
                            else:
                                # 延長 → 稼働率は上がるがコスト増
                                _h4_occ_gain = _h4_bed_days_change / (_view_beds * 30) * 100
                                _h4_annual_gain = _h4_occ_gain * _ANNUAL_VALUE_PER_1PCT
                                _hint_savings[f"{_h4_doc}在院日数延長"] = _h4_annual_gain
                                st.info(
                                    f"在院日数を{_h4_adjust:.1f}日延長 → "
                                    f"稼働率が約{_h4_occ_gain:.2f}%上昇 → "
                                    f"年間 **{_h4_annual_gain/10000:.0f}万円** の効果"
                                    f"（ただし回転率は低下します）"
                                )
                                if _annual_loss_total > 0:
                                    _h4e_gap_pct = min(100, _h4_annual_gain / _annual_loss_total * 100)
                                    st.caption(f"→ 稼働率ギャップの **{_h4e_gap_pct:.0f}%** をカバー")
                        else:
                            st.caption("スライダーを動かして在院日数の調整効果をシミュレーションしてください。")

        # =====================================================================
        # Hint 5: 改善の積み重ね効果（全スライダーの合計を動的に集計）
        # =====================================================================
        if _hints_found or len(_hint_savings) > 0:
            st.markdown("**🏗️ 改善の積み重ね効果**")

            # 基本指標テーブル
            st.markdown(f"""
            | 指標 | 数値 |
            |------|------|
            | 稼働率1%（≈1名の入院）の年間価値 | **{_ANNUAL_VALUE_PER_1PCT/10000:.0f}万円** |
            | 人件費率58%換算（290人） | 一人あたり年間 **約{_ANNUAL_VALUE_PER_1PCT*0.58/290/10000:.1f}万円** |
            """)

            # 各ヒントの積み上げサマリー
            if len(_hint_savings) > 0:
                _stack_rows = []
                for _hint_name, _hint_val in _hint_savings.items():
                    _stack_rows.append({
                        "改善項目": _hint_name,
                        "年間改善額（万円）": round(_hint_val / 10000),
                    })
                _stack_df = pd.DataFrame(_stack_rows)
                _total_savings = sum(_hint_savings.values())
                _stack_rows.append({
                    "改善項目": "合計",
                    "年間改善額（万円）": round(_total_savings / 10000),
                })
                _stack_df = pd.DataFrame(_stack_rows)
                st.dataframe(_stack_df, use_container_width=True, hide_index=True)

                if _annual_loss_total > 0:
                    _coverage_pct = min(100, _total_savings / _annual_loss_total * 100)
                    st.markdown(f"##### 🎯 目標ギャップに対するカバー率: **{_coverage_pct:.0f}%**")
                    st.progress(min(1.0, _coverage_pct / 100))
                    if _coverage_pct >= 100:
                        st.success("🎉 上記の改善策で目標稼働率90%を達成できる見込みです！")
                    elif _coverage_pct >= 50:
                        st.info(f"残り **{100 - _coverage_pct:.0f}%** は、新規入院経路の開拓や地域連携の強化で補完を検討してください。")
                    else:
                        st.warning(f"カバー率 **{_coverage_pct:.0f}%** — より積極的な改善策の検討が必要です。")

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

# =====================================================================
# 施設基準チェック・需要波・C群コントロール タブ
# =====================================================================
if _GUARDRAIL_AVAILABLE and _DATA_MANAGER_AVAILABLE and "🛡️ 制度・需要・C群" in _tab_idx:
    with tabs[_tab_idx["🛡️ 制度・需要・C群"]]:
        st.header("🛡️ 施設基準チェック・需要波・C群コントロール")
        st.caption("⚠️ C群（退院準備期）は院内運用上のラベルであり、制度上の公式区分ではありません。")

        # --- データ準備 ---
        # _daily_df は既存変数（日次データ）。存在しない場合のフォールバック
        _gr_daily_df = _daily_df if isinstance(_daily_df, pd.DataFrame) and len(_daily_df) > 0 else None
        # Full data for LOS calculations (rolling 90日)
        _gr_daily_df_full_src = st.session_state.get("actual_df_raw_full")
        _gr_daily_df_full = _gr_daily_df_full_src if isinstance(_gr_daily_df_full_src, pd.DataFrame) and len(_gr_daily_df_full_src) > 0 else _gr_daily_df
        _gr_detail_df = None  # 詳細データがあれば使う
        # detail_data_manager から取得を試みる
        if _DETAIL_DATA_AVAILABLE:
            try:
                _gr_detail_df = globals().get("_detail_events_df")
                if _gr_detail_df is None or (isinstance(_gr_detail_df, pd.DataFrame) and len(_gr_detail_df) == 0):
                    _gr_detail_df = st.session_state.get("admission_details")
            except Exception:
                _gr_detail_df = st.session_state.get("admission_details")

        _gr_ward_selected = _selected_ward_key if _selected_ward_key in ("5F", "6F") else None
        _gr_config = {
            "age_85_ratio": 0.25,  # HOSPITAL_DEFAULTS参照
            "monthly_summary": st.session_state.get("monthly_summary", {}),
            "ward": _gr_ward_selected,
        }

        # --- 3つのサブセクション ---
        _gr_sub1, _gr_sub2, _gr_sub3, _gr_sub4 = st.tabs(["🛡️ 制度余力", "🌊 需要波", "📋 C群コントロール", "🚑 救急搬送15%"])

        # ============================================
        # サブタブ1: 制度余力
        # ============================================
        with _gr_sub1:
            st.subheader("制度余力ダッシュボード")

            # 現在の表示病棟を明示
            if _selected_ward_key in ("5F", "6F"):
                _gr_ward_beds = get_ward_beds(_selected_ward_key) if _DATA_MANAGER_AVAILABLE else 47
                st.markdown(f"**\U0001f4cc 表示中: {_selected_ward_key}病棟（{_gr_ward_beds}床）**")
            else:
                st.markdown(f"**\U0001f4cc 表示中: 全体（{total_beds}床）**")

            if _gr_daily_df is not None:
                # 病棟別データの準備
                _gr_ward_dfs = st.session_state.get("sim_ward_raw_dfs_full") or st.session_state.get("ward_raw_dfs_full") or {}

                # 病棟選択時は病棟フィルタ済みデータで計算
                if _gr_ward_selected and _gr_ward_selected in _gr_ward_dfs:
                    _gr_daily_df_ward = _gr_ward_dfs[_gr_ward_selected]
                    _gr_results = calculate_guardrail_status(_gr_daily_df_ward, _gr_detail_df, _gr_config)
                    _los_hr = calculate_los_headroom(_gr_daily_df_ward, _gr_config)
                else:
                    _gr_results = calculate_guardrail_status(_gr_daily_df, _gr_detail_df, _gr_config)
                    _los_hr = calculate_los_headroom(_gr_daily_df_full, _gr_config)
                _gr_display = format_guardrail_display(_gr_results)

                # 病棟別LOS余力（比較表示用）
                _los_hr_5f = None
                _los_hr_6f = None
                for _w_key in ("5F", "6F"):
                    if _w_key in _gr_ward_dfs and isinstance(_gr_ward_dfs[_w_key], pd.DataFrame) and len(_gr_ward_dfs[_w_key]) > 0:
                        try:
                            _w_los = calculate_los_headroom(_gr_ward_dfs[_w_key], _gr_config)
                            if _w_key == "5F":
                                _los_hr_5f = _w_los
                            else:
                                _los_hr_6f = _w_los
                        except Exception:
                            pass

                # 描画をviewモジュールに委譲
                if _VIEWS_AVAILABLE:
                    render_guardrail_summary({
                        "results": _gr_results,
                        "display": _gr_display,
                        "los_headroom": _los_hr,
                        "los_headroom_5f": _los_hr_5f,
                        "los_headroom_6f": _los_hr_6f,
                    })
                else:
                    st.warning("描画モジュール (views) の読み込みに失敗しました。制度余力の詳細表示は利用できません。")
                    _status_emoji = {"safe": "🟢", "warning": "🟡", "danger": "🔴", "incomplete": "🟠"}.get(_gr_display["overall_status"], "⚪")
                    _status_ja = {"safe": "安全", "warning": "注意", "danger": "危険", "incomplete": "未完（データ不足）"}.get(_gr_display["overall_status"], "不明")
                    st.markdown(f"### {_status_emoji} 総合判定: **{_status_ja}**")

                # 翌診療日朝の受入余力
                if _EMERGENCY_RATIO_AVAILABLE:
                    st.markdown("---")
                    st.subheader("🌅 翌診療日朝の救急受入余力（推計）")
                    try:
                        _morning_ward = _selected_ward_key if _selected_ward_key in ("5F", "6F") else None
                        _morning_beds = 47 if _morning_ward else 94
                        _morning_cap = estimate_next_morning_capacity(
                            _gr_daily_df, _gr_detail_df,
                            ward=_morning_ward,
                            target_date=None,
                            total_beds=_morning_beds,
                        )
                        _mc_cols = st.columns(3)
                        with _mc_cols[0]:
                            st.metric("今夜の空床", f"{_morning_cap['current_empty_beds']}床")
                        with _mc_cols[1]:
                            st.metric("明朝の受入可能枠", f"{_morning_cap['estimated_emergency_slots']}床",
                                      delta="推計")
                        with _mc_cols[2]:
                            st.metric("3診療日の最小受入余力", f"{_morning_cap['three_day_min_slots']}床",
                                      delta="最悪ケース")
                        st.caption("⚠️ 推計値です。予定入院・退院の変動により実際とは異なります。")
                    except Exception:
                        st.info("データ不足のため翌朝受入余力を計算できません")
            else:
                st.info("日次データを入力すると制度余力が表示されます")

        # ============================================
        # サブタブ2: 需要波
        # ============================================
        with _gr_sub2:
            st.subheader("需要波ダッシュボード")

            if _gr_daily_df is not None:
                # 病棟選択
                _dw_ward = st.selectbox("病棟", [None, "5F", "6F"], format_func=lambda x: "全体" if x is None else x, key="dw_ward_select")

                # トレンド・分類・スコア
                _dw_trend = calculate_demand_trend(_gr_daily_df, _dw_ward)
                _dw_class = classify_demand_period(_gr_daily_df, _dw_ward)
                _dw_score = calculate_demand_score(_gr_daily_df, _dw_ward)

                if _VIEWS_AVAILABLE:
                    render_demand_wave_summary({
                        "trend": _dw_trend,
                        "classification": _dw_class,
                        "score": _dw_score,
                    })
                else:
                    _trend_emoji = {"increasing": "\U0001f4c8", "decreasing": "\U0001f4c9", "stable": "\u27a1\ufe0f"}.get(_dw_trend["trend_label"], "\u27a1\ufe0f")
                    st.markdown(f"### {_trend_emoji} {_dw_trend['trend_description']}")
                    st.info("\u63cf\u753b\u30e2\u30b8\u30e5\u30fc\u30eb (views) \u306e\u8aad\u307f\u8fbc\u307f\u306b\u5931\u6557\u3057\u307e\u3057\u305f\u3002\u8a73\u7d30\u8868\u793a\u306f\u5229\u7528\u3067\u304d\u307e\u305b\u3093\u3002")

                # 曜日別パターン
                st.markdown("---")
                st.subheader("📅 曜日別パターン")
                _dw_dow = calculate_dow_pattern(_gr_daily_df, _dw_ward)
                if _dw_dow is not None and len(_dw_dow) > 0:
                    import matplotlib.pyplot as plt
                    _fig_dow, _ax_dow = plt.subplots(figsize=(10, 3))
                    _x = range(7)
                    _ax_dow.bar([i - 0.15 for i in _x], _dw_dow["avg_admissions"], width=0.3, label="入院", color="#4CAF50", alpha=0.8)
                    _ax_dow.bar([i + 0.15 for i in _x], _dw_dow["avg_discharges"], width=0.3, label="退院", color="#FF5722", alpha=0.8)
                    _ax_dow.set_xticks(list(_x))
                    _ax_dow.set_xticklabels(_dw_dow["dow_label"].tolist())
                    _ax_dow.set_ylabel("件数")
                    _ax_dow.legend()
                    _ax_dow.set_title("曜日別 入院・退院パターン")
                    st.pyplot(_fig_dow)
                    plt.close(_fig_dow)

                # アラート
                _dw_alerts = detect_demand_alerts(_gr_daily_df, _dw_ward)
                if _dw_alerts:
                    st.markdown("---")
                    st.subheader("⚡ 需要アラート")
                    for _alert in _dw_alerts:
                        _alert_icon = {"warning": "⚠️", "info": "ℹ️"}.get(_alert["level"], "ℹ️")
                        st.markdown(f"{_alert_icon} {_alert['message']}")

                # 経路別需要トレンド
                if _EMERGENCY_RATIO_AVAILABLE and _gr_detail_df is not None and len(_gr_detail_df) > 0:
                    st.markdown("---")
                    st.subheader("🚑 経路別需要トレンド（救急 / 下り搬送 / その他）")

                    _route_trend = calculate_route_demand_trend(_gr_daily_df, _gr_detail_df, _dw_ward)

                    _rt_cols = st.columns(3)
                    _rt_labels = [
                        ("rescue", "🚑 救急", _route_trend.get("rescue", {})),
                        ("downstream", "🏥 下り搬送", _route_trend.get("downstream", {})),
                        ("other", "📋 その他", _route_trend.get("other", {})),
                    ]
                    for _rt_idx, (_rt_key, _rt_label, _rt_data) in enumerate(_rt_labels):
                        with _rt_cols[_rt_idx]:
                            if _rt_data:
                                _rt_emoji = {"increasing": "📈", "stable": "➡️", "decreasing": "📉"}.get(_rt_data.get("trend_label", "stable"), "➡️")
                                st.metric(
                                    _rt_label,
                                    f"{_rt_data.get('daily_avg', 0):.1f}件/日",
                                    delta=f"{_rt_emoji} 前週比 {_rt_data.get('trend_ratio', 1.0)*100:.0f}%",
                                )
            else:
                st.info("日次データを入力すると需要波分析が表示されます")

        # ============================================
        # サブタブ3: C群コントロール
        # ============================================
        with _gr_sub3:
            _bc_section_title("C群コントロールパネル", icon="📋")
            st.caption("C群（在院15日目以降）は院内運用上のラベルで、制度上の公式区分ではありません。表示値は proxy（推計）を含みます。")

            # 現在の表示病棟を明示
            _cg_ward_filter_label = _selected_ward_key if _selected_ward_key in ("5F", "6F") else None
            if _cg_ward_filter_label:
                _cg_ward_beds = get_ward_beds(_cg_ward_filter_label) if _DATA_MANAGER_AVAILABLE else 47
                st.caption(f"📌 表示中: **{_cg_ward_filter_label}病棟**（{_cg_ward_beds}床）")
            else:
                st.caption(f"📌 表示中: **全体**（{total_beds}床）")

            if _gr_daily_df is not None:
                # ============================================================
                # 計算フェーズ（表示前にすべての値を準備する）
                # ============================================================
                _cg_ward_filter = _selected_ward_key if _selected_ward_key in ("5F", "6F") else None
                _cg_summary = get_c_group_summary(_gr_daily_df, ward=_cg_ward_filter)
                # 病棟選択時は病棟フィルタ済みデータでLOS計算
                _cg_ward_dfs = _gr_ward_dfs if "_gr_ward_dfs" in dir() else (st.session_state.get("sim_ward_raw_dfs_full") or st.session_state.get("ward_raw_dfs_full") or {})
                _cg_los_df = _cg_ward_dfs.get(_cg_ward_filter, _gr_daily_df_full) if _cg_ward_filter and _cg_ward_dfs else _gr_daily_df_full
                _los_hr = calculate_los_headroom(_cg_los_df, _gr_config)
                _los_limit = _los_hr["los_limit"]
                _cg_rolling = calculate_rolling_los(_cg_los_df, monthly_summary=st.session_state.get("monthly_summary"), ward=_cg_ward_filter) if _cg_los_df is not None else None
                _cg_capacity = calculate_c_adjustment_capacity(_cg_rolling, _los_limit, _cg_summary["c_count"])
                _dw_class_cg = classify_demand_period(_gr_daily_df, ward=_cg_ward_filter)
                _dw_trend_cg = calculate_demand_trend(_gr_daily_df, ward=_cg_ward_filter)

                # 救急搬送比率リスク（C群アラート・候補一覧で使用）
                _er_risk_for_cg = None
                if _EMERGENCY_RATIO_AVAILABLE and _gr_detail_df is not None and len(_gr_detail_df) > 0:
                    try:
                        from datetime import date as _cg_date
                        _cg_today = _cg_date.today()
                        _cg_ym = _cg_today.strftime("%Y-%m")
                        # 経過措置ゲート: 〜2026-05-31 は単月、6/1 以降は rolling 3ヶ月
                        _er_5f_cg = _calc_emergency_ratio_with_gate(_gr_detail_df, "5F", _cg_ym, _cg_today)
                        _er_6f_cg = _calc_emergency_ratio_with_gate(_gr_detail_df, "6F", _cg_ym, _cg_today)
                        _er_need_5f_cg = calculate_additional_needed(_gr_detail_df, "5F", _cg_ym, _cg_today)
                        _er_need_6f_cg = calculate_additional_needed(_gr_detail_df, "6F", _cg_ym, _cg_today)
                        _er_risk_for_cg = {
                            "5F": {
                                "status": _er_5f_cg["status"],
                                "additional_needed": _er_need_5f_cg["additional_needed"],
                                "ratio_pct": _er_5f_cg["ratio_pct"],
                            },
                            "6F": {
                                "status": _er_6f_cg["status"],
                                "additional_needed": _er_need_6f_cg["additional_needed"],
                                "ratio_pct": _er_6f_cg["ratio_pct"],
                            },
                        }
                    except Exception:
                        pass

                # 救急搬送比率リスクの要約フラグ（病棟フィルタ対応）
                _cg_er_risk = False
                if _er_risk_for_cg is not None:
                    if _cg_ward_filter:
                        # 特定病棟表示時はその病棟のみ判定
                        _cg_er_risk = _er_risk_for_cg.get(_cg_ward_filter, {}).get("additional_needed", 0) > 0
                    else:
                        # 全体表示時はいずれかの病棟にリスクがあればTrue
                        for _w_key in ("5F", "6F"):
                            if _er_risk_for_cg.get(_w_key, {}).get("additional_needed", 0) > 0:
                                _cg_er_risk = True
                                break

                _cg_alerts = generate_c_group_alerts(
                    _cg_summary, _cg_capacity, _dw_class_cg["classification"],
                    emergency_ratio_risk=_er_risk_for_cg,
                )

                # ============================================================
                # 表示フェーズ: Hero(現状) → Secondary(根拠・アラート) → Tertiary(詳細)
                # ============================================================

                # --- Hero: C群の現状（3 KPI） ---
                _bc_section_title("現状サマリー", icon="👥")

                _ds_ja_map = {"measured": "実測", "proxy": "推計", "manual_input": "手動", "not_available": ""}
                _ds_tag = _ds_ja_map.get(_cg_summary['data_source'], '')
                _ds_delta = f"データソース: {_ds_tag}" if _ds_tag else None

                # C群構成比のseverity判定: >30% danger, 20-30% warning, それ未満 neutral（generate_c_group_alerts の閾値に準拠）
                _cg_ratio = float(_cg_summary.get('c_ratio', 0.0))
                if _cg_ratio > 30:
                    _cg_ratio_sev = "danger"
                elif _cg_ratio >= 20:
                    _cg_ratio_sev = "warning"
                else:
                    _cg_ratio_sev = "neutral"

                _cg_col1, _cg_col2, _cg_col3 = st.columns(3)
                with _cg_col1:
                    _bc_kpi_card(
                        label="C群患者数",
                        value=f"{_cg_summary['c_count']}",
                        unit=" 名",
                        delta=_ds_delta,
                        severity="neutral",
                    )
                with _cg_col2:
                    _bc_kpi_card(
                        label="C群構成比",
                        value=f"{_cg_ratio:.1f}",
                        unit="%",
                        delta="高水準警戒: 30% 超",
                        severity=_cg_ratio_sev,
                    )
                with _cg_col3:
                    _contrib = _cg_summary['c_daily_contribution']
                    _bc_kpi_card(
                        label="C群 日次貢献額",
                        value=f"¥{_contrib:,.0f}",
                        delta="C群患者数 × 28,900円/日",
                        severity="neutral",
                    )

                # --- Secondary 1: 平均在院日数の余力（最重要の判断材料） ---
                st.markdown("")  # 呼吸
                _bc_section_title("平均在院日数の余力", icon="⏳")

                if _cg_capacity["current_los"] is not None:
                    _cap_sev_map = {"green": "success", "yellow": "warning", "red": "danger", "gray": "neutral"}
                    _cap_sev = _cap_sev_map.get(_cg_capacity["status_color"], "neutral")

                    _cap_col1, _cap_col2, _cap_col3 = st.columns(3)
                    with _cap_col1:
                        _bc_kpi_card(
                            label="現在の平均在院日数",
                            value=f"{_cg_capacity['current_los']:.1f}",
                            unit=" 日",
                            severity="neutral",
                        )
                    with _cap_col2:
                        _bc_kpi_card(
                            label="制度上限",
                            value=f"{_cg_capacity['los_limit']:.0f}",
                            unit=" 日",
                            severity="neutral",
                        )
                    with _cap_col3:
                        _bc_kpi_card(
                            label=f"余力（{_cg_capacity['status']}）",
                            value=f"{_cg_capacity['headroom_days']:.1f}",
                            unit=" 日",
                            delta="上限 − 現在LOS",
                            severity=_cap_sev,
                        )

                    # 判断メッセージを severity 付きアラートに集約
                    if _cg_er_risk:
                        # 救急搬送比率リスクがある → LOS余力があっても後ろ倒しは推奨しない
                        _bc_alert(
                            "救急搬送比率に未達リスクあり — C群退院を進めてベッドを確保してください",
                            severity="warning",
                        )
                    elif _cg_capacity["can_delay_discharge"]:
                        _delay_days = _cg_capacity['max_delay_bed_days']
                        _bc_alert(
                            f"C群退院の後ろ倒し可能（最大約 {_delay_days:.0f} 日分の余地あり）",
                            severity="success",
                        )
                    else:
                        _bc_alert(
                            "C群退院の後ろ倒し不可（平均在院日数の余力不足）",
                            severity="danger",
                        )

                    if _cg_capacity["warning_message"]:
                        _bc_alert(_cg_capacity["warning_message"], severity="warning")
                else:
                    _bc_alert("平均在院日数データがありません。", severity="info")

                # --- Secondary 2: C群アラート（存在するときのみ） ---
                if _cg_alerts:
                    st.markdown("")  # 呼吸
                    _bc_section_title("C群アラート", icon="⚡")
                    _alert_sev_map = {"danger": "danger", "warning": "warning", "info": "info"}
                    for _alert in _cg_alerts:
                        _bc_alert(
                            _alert['message'],
                            severity=_alert_sev_map.get(_alert["level"], "info"),
                        )

                # --- Tertiary 1: C群調整候補一覧（具体的なアクション対象） ---
                if _C_GROUP_CANDIDATES_AVAILABLE and _VIEWS_AVAILABLE:
                    st.markdown("")  # 呼吸
                    _bc_section_title("退院調整候補一覧", icon="📝")
                    _cg_morning_slots = None
                    if _EMERGENCY_RATIO_AVAILABLE:
                        try:
                            _cg_mc = estimate_next_morning_capacity(
                                _gr_daily_df, _gr_detail_df, ward=_cg_ward_filter, total_beds=47 if _cg_ward_filter else 94,
                            )
                            _cg_morning_slots = _cg_mc.get("estimated_emergency_slots")
                        except Exception:
                            pass
                    _cg_candidates_result = generate_c_group_candidate_list(
                        detail_df=_gr_detail_df,
                        daily_df=_gr_daily_df,
                        ward=_cg_ward_filter,
                        target_date=None,
                        los_threshold=15,
                    )
                    _cg_display_summary = summarize_candidates_for_display(
                        _cg_candidates_result,
                        los_limit=_los_limit,
                        emergency_ratio_risk=_cg_er_risk,
                        morning_capacity_slots=_cg_morning_slots,
                        current_ward_los=_cg_capacity.get("current_los"),
                    )
                    render_c_group_candidates_lite(_cg_display_summary, _cg_candidates_result)

                # --- Tertiary 2: 需要吸収シミュレーション（折りたたみ） ---
                with st.expander("🌊 需要吸収シミュレーション（分析・検討用）"):
                    _cg_total_beds = 47 if _cg_ward_filter else 94
                    _cg_occ = globals().get("_occ_now")
                    if _cg_occ is None:
                        _latest = _gr_daily_df.iloc[-1] if len(_gr_daily_df) > 0 else None
                        if _latest is not None:
                            _tp = float(_latest.get("total_patients", 0))
                            _ds = float(_latest.get("discharges", 0))
                            _cg_occ = (_tp + _ds) / _cg_total_beds if _cg_total_beds > 0 else 0.0
                        else:
                            _cg_occ = 0.0

                    _cg_absorption = calculate_demand_absorption(
                        _cg_capacity,
                        _dw_trend_cg["trend_label"],
                        _cg_occ,
                        target_occupancy=target_lower if "target_lower" in dir() else 0.90,
                    )

                    _rec_sev_map = {"C群キープ推奨": "info", "C群前倒し推奨": "warning", "現状維持": "success"}
                    _rec_sev = _rec_sev_map.get(_cg_absorption["recommendation"], "info")
                    _bc_alert(
                        f"<b>{_cg_absorption['recommendation']}</b><br>{_cg_absorption['recommendation_reason']}",
                        severity=_rec_sev,
                    )
                    st.caption(_cg_absorption["absorption_description"])

                # --- Tertiary 3: C群 What-If シミュレーション（折りたたみ） ---
                with st.expander("🔮 C群 What-If シミュレーション（詳細分析用）"):
                    _sim_col1, _sim_col2 = st.columns(2)
                    with _sim_col1:
                        st.markdown("**退院後ろ倒し**")
                        _sim_n_delay = st.slider("後ろ倒し人数", 0, 10, 0, key="cg_n_delay")
                        _sim_delay_days = st.slider("後ろ倒し日数", 0, 7, 2, key="cg_delay_days")
                    with _sim_col2:
                        st.markdown("**退院前倒し**")
                        _sim_n_accel = st.slider("前倒し人数", 0, 10, 0, key="cg_n_accel")
                        _sim_accel_days = st.slider("前倒し日数", 0, 7, 1, key="cg_accel_days")

                    if _sim_n_delay > 0 or _sim_n_accel > 0:
                        _sim_result = simulate_c_group_scenario(
                            _cg_rolling, _los_limit,
                            n_delay=_sim_n_delay, delay_days=_sim_delay_days,
                            n_accelerate=_sim_n_accel, accelerate_days=_sim_accel_days,
                        )

                        if _sim_result["simulated_los"] is not None:
                            _sim_sev = "success" if _sim_result["within_guardrail"] else "danger"
                            _bc_alert(
                                f"<b>{_sim_result['description']}</b>",
                                severity=_sim_sev,
                            )
                            if not _sim_result["within_guardrail"]:
                                _bc_alert(
                                    "このシナリオでは平均在院日数が制度上限を超過します。実行は推奨しません。",
                                    severity="danger",
                                )
                        else:
                            _bc_alert(_sim_result["description"], severity="warning")
            else:
                _bc_alert("日次データを入力するとC群コントロールパネルが表示されます", severity="info")

        # ============================================
        # サブタブ4: 救急搬送後患者割合 15%
        # ============================================
        with _gr_sub4:
            st.subheader("🚑 救急搬送後患者割合（病棟別・単月管理）")
            st.caption("施設基準: 救急搬送後の入院患者割合が15%以上であること。5F・6Fそれぞれで単月管理します。")

            if _gr_detail_df is not None and len(_gr_detail_df) > 0 and _EMERGENCY_RATIO_AVAILABLE:
                import matplotlib.pyplot as plt
                from datetime import date as _er_date

                _er_today = _er_date.today()
                _er_ym = _er_today.strftime("%Y-%m")

                # --- 表示モード選択 ---
                _er_display_mode = st.radio(
                    "表示する比率",
                    ["両方表示（推奨）", "届出確認用のみ", "院内運用用のみ（短手3除外）"],
                    index=0,
                    horizontal=True,
                    key="er_display_mode",
                )

                _er_use_short3_excl = _er_display_mode == "院内運用用のみ（短手3除外）"

                # =========================================
                # セクション1: 5F / 6F 別の今月カード
                # =========================================
                st.markdown("---")
                st.markdown("### 📊 今月の状況（5F / 6F）")

                _er_col_5f, _er_col_6f = st.columns(2)

                for _er_ward, _er_col in [("5F", _er_col_5f), ("6F", _er_col_6f)]:
                    with _er_col:
                        st.markdown(f"#### {_er_ward}")

                        _er_dual = calculate_dual_ratio(_gr_detail_df, _er_ward, _er_ym, _er_today)

                        # 届出確認用
                        _er_official = _er_dual["official"]
                        # 院内運用用
                        _er_operational = _er_dual["operational"]

                        # メイン表示の決定
                        if _er_display_mode == "届出確認用のみ":
                            _er_items = [("届出確認用", _er_official)]
                        elif _er_display_mode == "院内運用用のみ（短手3除外）":
                            _er_items = [("院内運用用（短手3除外）", _er_operational)]
                        else:
                            _er_items = [("届出確認用", _er_official), ("院内運用用（短手3除外）", _er_operational)]

                        for _er_label, _er_data in _er_items:
                            _er_status_icon = {"green": "🟢", "yellow": "🟡", "red": "🔴"}.get(_er_data["status"], "⚪")
                            _er_gap = _er_data["gap_to_target_pt"]
                            _er_gap_str = f"+{_er_gap:.1f}pt" if _er_gap >= 0 else f"{_er_gap:.1f}pt"

                            st.markdown(f"**{_er_label}**")
                            st.metric(
                                label=f"{_er_status_icon} 救急搬送後患者割合",
                                value=f"{_er_data['ratio_pct']:.1f}%",
                                delta=f"基準との差 {_er_gap_str}",
                                delta_color="normal" if _er_gap >= 0 else "inverse",
                            )
                            st.caption(
                                f"分子（救急+下り搬送）: {_er_data['numerator']}件 / "
                                f"分母（対象入院）: {_er_data['denominator']}件"
                            )
                            # 内訳
                            _bd = _er_data["breakdown"]
                            _bd_parts = []
                            if _bd["ambulance"] > 0:
                                _bd_parts.append(f"救急車 {_bd['ambulance']}")
                            if _bd["downstream"] > 0:
                                _bd_parts.append(f"下り搬送 {_bd['downstream']}")
                            if _bd_parts:
                                st.caption(f"内訳: {' / '.join(_bd_parts)}")
                            if _er_data["exclude_short3"] and _bd.get("excluded_short3", 0) > 0:
                                st.caption(f"短手3除外: {_bd['excluded_short3']}件")

                # =========================================
                # セクション2: 月末着地予測
                # =========================================
                st.markdown("---")
                st.markdown("### 🔮 月末着地予測")

                _proj_col_5f, _proj_col_6f = st.columns(2)

                for _er_ward, _proj_col in [("5F", _proj_col_5f), ("6F", _proj_col_6f)]:
                    with _proj_col:
                        st.markdown(f"#### {_er_ward}")
                        _er_proj = project_month_end(_gr_detail_df, _er_ward, _er_ym, _er_today, exclude_short3=_er_use_short3_excl)

                        st.caption(
                            f"経過日数: {_er_proj['current']['elapsed_days']}日 / "
                            f"残り: {_er_proj['remaining_calendar_days']}日（診療日 {_er_proj['remaining_business_days']}日）"
                        )

                        # 3シナリオ表示
                        _scn_cols = st.columns(3)
                        for _scn_idx, (_scn_key, _scn_label, _scn_color) in enumerate([
                            ("conservative", "保守", "🔵"),
                            ("standard", "標準", "🟢"),
                            ("optimistic", "良好", "🟡"),
                        ]):
                            with _scn_cols[_scn_idx]:
                                _scn = _er_proj[_scn_key]
                                _scn_icon = "✅" if _scn["meets_target"] else "❌"
                                st.metric(
                                    f"{_scn_color} {_scn_label}",
                                    f"{_scn['projected_ratio_pct']:.1f}%",
                                    delta=f"{'達成' if _scn['meets_target'] else '未達'}",
                                    delta_color="normal" if _scn["meets_target"] else "inverse",
                                )
                                st.caption(
                                    f"搬送 {_scn['projected_emergency']}件 / "
                                    f"入院 {_scn['projected_total']}件"
                                )

                        # 直近14日の実績ベース
                        st.caption(
                            f"推計基盤: 直近14日の救急搬送 平均 {_er_proj['daily_emergency_rate_14d']:.1f}件/日、"
                            f"入院 平均 {_er_proj['daily_total_rate_14d']:.1f}件/日"
                        )

                # =========================================
                # セクション3: あと何件必要か
                # =========================================
                st.markdown("---")
                st.markdown("### 🎯 15%達成に必要な追加件数")

                _need_col_5f, _need_col_6f = st.columns(2)

                for _er_ward, _need_col in [("5F", _need_col_5f), ("6F", _need_col_6f)]:
                    with _need_col:
                        st.markdown(f"#### {_er_ward}")
                        _er_need = calculate_additional_needed(
                            _gr_detail_df, _er_ward, _er_ym, _er_today,
                            exclude_short3=_er_use_short3_excl,
                        )

                        if _er_need["additional_needed"] <= 0:
                            st.success(f"✅ 現時点で15%基準を達成済み（現在 {_er_need['current_emergency']}件）")
                        else:
                            _diff_label = {
                                "achieved": "達成済み",
                                "easy": "達成見込み",
                                "moderate": "やや厳しい",
                                "difficult": "厳しい",
                                "very_difficult": "非常に厳しい",
                            }.get(_er_need["difficulty"], "")
                            _diff_color = {
                                "easy": "🟢",
                                "moderate": "🟡",
                                "difficult": "🟠",
                                "very_difficult": "🔴",
                            }.get(_er_need["difficulty"], "⚪")

                            st.markdown(
                                f"{_diff_color} **あと {_er_need['additional_needed']}件** 必要 "
                                f"（難易度: {_diff_label}）"
                            )
                            st.caption(
                                f"残り日数あたり: {_er_need['per_remaining_calendar_day']:.1f}件/日 "
                                f"（診療日あたり: {_er_need['per_remaining_business_day']:.1f}件/日）"
                            )
                            if _er_need["this_week_needed"] > 0:
                                st.caption(f"今週中に必要: {_er_need['this_week_needed']}件")

                            if _er_need["additional_needed_from_actual"] > _er_need["additional_needed"]:
                                st.caption(
                                    f"（参考: 今後の自然流入を見込まない場合は {_er_need['additional_needed_from_actual']}件必要）"
                                )

                            if not _er_need["achievable"]:
                                st.error(
                                    "⚠️ 現在のペースでは達成困難です。"
                                    "救急搬送・下り搬送の受入体制を強化してください。"
                                )

                # =========================================
                # セクション4: 危険域アラート
                # =========================================
                # 経過措置ゲート: 〜2026-05-31 は単月、6/1 以降は rolling 3ヶ月
                _er_ratio_5f = _calc_emergency_ratio_with_gate(_gr_detail_df, "5F", _er_ym, _er_today, exclude_short3=_er_use_short3_excl)
                _er_ratio_6f = _calc_emergency_ratio_with_gate(_gr_detail_df, "6F", _er_ym, _er_today, exclude_short3=_er_use_short3_excl)

                # 判定モードの可視化（本則適用後は「rolling 3ヶ月判定」である旨を明示）
                if not is_transitional_period(_er_today) and _er_ratio_5f is not None:
                    st.caption(
                        "ℹ️ 2026-06-01 以降は **rolling 3ヶ月判定** を採用しています"
                        "（単月ではなく直近3ヶ月の分子・分母を合算して判定）。"
                        "今月の状況カードに表示される単月数値とは異なる場合があります。"
                    )
                _er_proj_5f = project_month_end(_gr_detail_df, "5F", _er_ym, _er_today, exclude_short3=_er_use_short3_excl)
                _er_proj_6f = project_month_end(_gr_detail_df, "6F", _er_ym, _er_today, exclude_short3=_er_use_short3_excl)
                _er_need_5f = calculate_additional_needed(_gr_detail_df, "5F", _er_ym, _er_today, exclude_short3=_er_use_short3_excl)
                _er_need_6f = calculate_additional_needed(_gr_detail_df, "6F", _er_ym, _er_today, exclude_short3=_er_use_short3_excl)

                _er_alerts = generate_emergency_alerts(
                    _er_ratio_5f, _er_ratio_6f,
                    _er_proj_5f, _er_proj_6f,
                    _er_need_5f, _er_need_6f,
                )

                _critical_alerts = [a for a in _er_alerts if a["level"] == "critical"]
                _warning_alerts = [a for a in _er_alerts if a["level"] == "warning"]
                _caution_alerts = [a for a in _er_alerts if a["level"] == "caution"]

                if _critical_alerts:
                    st.markdown("---")
                    st.markdown("### 🚨 緊急アラート — 受入最優先モード")
                    for _alert in _critical_alerts:
                        st.error(f"🔴 **{_alert['title']}**")
                        st.error(_alert["message"])
                        if _alert.get("actions"):
                            for _action in _alert["actions"]:
                                st.markdown(f"  → {_action}")

                if _warning_alerts:
                    st.markdown("---")
                    for _alert in _warning_alerts:
                        st.warning(f"🟡 **{_alert['title']}**")
                        st.warning(_alert["message"])

                if _caution_alerts:
                    for _alert in _caution_alerts:
                        st.info(f"ℹ️ {_alert['title']}: {_alert['message']}")

                # =========================================
                # セクション5: グラフ
                # =========================================
                st.markdown("---")
                st.markdown("### 📈 推移グラフ")

                _chart_tab1, _chart_tab2, _chart_tab3 = st.tabs([
                    "月内累積推移", "過去12か月実績", "入院経路の構成比"
                ])

                # グラフ1: 月内累積推移（5F / 6F）
                with _chart_tab1:
                    _cum_col_5f, _cum_col_6f = st.columns(2)
                    for _er_ward, _cum_col in [("5F", _cum_col_5f), ("6F", _cum_col_6f)]:
                        with _cum_col:
                            st.markdown(f"**{_er_ward}**")
                            _cum_data = get_cumulative_progress(
                                _gr_detail_df, _er_ward, _er_ym, _er_today,
                                exclude_short3=_er_use_short3_excl,
                            )
                            if _cum_data:
                                _cum_df = pd.DataFrame(_cum_data)
                                _fig_cum, _ax_cum = plt.subplots(figsize=(6, 3))
                                _ax_cum.plot(
                                    range(len(_cum_df)),
                                    _cum_df["cumulative_ratio_pct"],
                                    marker="o",
                                    markersize=3,
                                    linewidth=1.5,
                                    color="#1976D2",
                                    label=f"{_er_ward} 累積比率",
                                )
                                _ax_cum.axhline(
                                    y=15, color="red", linestyle="--",
                                    linewidth=1, label="基準 15%"
                                )
                                _ax_cum.set_ylabel("%")
                                _ax_cum.set_title(f"{_er_ward} 月内累積推移")
                                _ax_cum.set_xticks(range(len(_cum_df)))
                                _day_labels = [str(i + 1) for i in range(len(_cum_df))]
                                _ax_cum.set_xticklabels(_day_labels, fontsize=7)
                                _ax_cum.set_xlabel("日")
                                _ax_cum.legend(fontsize=8)
                                _ax_cum.set_ylim(0, max(30, _cum_df["cumulative_ratio_pct"].max() + 5))
                                _fig_cum.tight_layout()
                                st.pyplot(_fig_cum)
                                plt.close(_fig_cum)
                            else:
                                st.info("データなし")

                # グラフ2: 過去12か月の単月実績
                with _chart_tab2:
                    _hist_col_5f, _hist_col_6f = st.columns(2)
                    for _er_ward, _hist_col in [("5F", _hist_col_5f), ("6F", _hist_col_6f)]:
                        with _hist_col:
                            st.markdown(f"**{_er_ward}**")
                            _hist_data = get_monthly_history(
                                _gr_detail_df, _er_ward, n_months=12, target_date=_er_today,
                                exclude_short3=_er_use_short3_excl,
                            )
                            if _hist_data:
                                _hist_df = pd.DataFrame(_hist_data)
                                _fig_hist, _ax_hist = plt.subplots(figsize=(6, 3))
                                _bar_colors = [
                                    "#4CAF50" if r >= 15 else "#F44336"
                                    for r in _hist_df["ratio_pct"]
                                ]
                                _ax_hist.bar(
                                    range(len(_hist_df)),
                                    _hist_df["ratio_pct"],
                                    color=_bar_colors,
                                    alpha=0.8,
                                )
                                _ax_hist.axhline(
                                    y=15, color="red", linestyle="--",
                                    linewidth=1, label="基準 15%"
                                )
                                _ax_hist.set_ylabel("%")
                                _ax_hist.set_title(f"{_er_ward} 過去12か月")
                                _ax_hist.set_xticks(range(len(_hist_df)))
                                _ax_hist.set_xticklabels(
                                    [ym[-5:] for ym in _hist_df["year_month"]],
                                    fontsize=7, rotation=45,
                                )
                                _ax_hist.legend(fontsize=8)
                                _fig_hist.tight_layout()
                                st.pyplot(_fig_hist)
                                plt.close(_fig_hist)
                            else:
                                st.info("過去データなし")

                # グラフ3: 入院経路の構成比（今月）
                with _chart_tab3:
                    _route_col_5f, _route_col_6f = st.columns(2)
                    for _er_ward, _route_col in [("5F", _route_col_5f), ("6F", _route_col_6f)]:
                        with _route_col:
                            st.markdown(f"**{_er_ward}**")
                            # 入院経路構成比の円グラフは当月単月の内訳を表示するため
                            # 経過措置ゲートの影響を受けない（rolling 3ヶ月の breakdown は
                            # 構成比の瞬間スナップショットとして不適切）
                            _er_ratio_ward = calculate_emergency_ratio(
                                _gr_detail_df, _er_ward, _er_ym, target_date=_er_today
                            )
                            _bd = _er_ratio_ward["breakdown"]
                            _pie_labels = []
                            _pie_values = []
                            _pie_colors = []
                            _color_map = {
                                "救急車": ("#F44336", _bd["ambulance"]),
                                "下り搬送": ("#FF9800", _bd["downstream"]),
                                "外来紹介": ("#4CAF50", _bd["scheduled"]),
                                "連携室": ("#2196F3", _bd["liaison"]),
                                "ウォークイン": ("#9E9E9E", _bd["walkin"]),
                                "その他": ("#607D8B", _bd["other"]),
                            }
                            for _lbl, (_clr, _val) in _color_map.items():
                                if _val > 0:
                                    _pie_labels.append(f"{_lbl} ({_val})")
                                    _pie_values.append(_val)
                                    _pie_colors.append(_clr)

                            if _pie_values:
                                _fig_pie, _ax_pie = plt.subplots(figsize=(5, 3))
                                _ax_pie.pie(
                                    _pie_values,
                                    labels=_pie_labels,
                                    colors=_pie_colors,
                                    autopct="%1.0f%%",
                                    startangle=90,
                                    textprops={"fontsize": 8},
                                )
                                _ax_pie.set_title(f"{_er_ward} 入院経路構成（今月）")
                                _fig_pie.tight_layout()
                                st.pyplot(_fig_pie)
                                plt.close(_fig_pie)
                            else:
                                st.info("データなし")

            elif not _EMERGENCY_RATIO_AVAILABLE:
                st.warning("救急搬送後患者割合モジュールの読み込みに失敗しました")
            else:
                st.info("入退院詳細データを入力すると救急搬送後患者割合が表示されます")

# ---------------------------------------------------------------------------
# データエクスポートタブ
# ---------------------------------------------------------------------------
if "📥 データエクスポート" in _tab_idx:
    _export_auth_ok = False
    with tabs[_tab_idx["📥 データエクスポート"]]:
        st.header("📥 データエクスポート")
        st.caption("入力済みデータをCSV形式でダウンロードできます。Excel等で解析にご利用ください。")
        _export_auth_ok = _require_data_auth("データエクスポート")

    # 認証成功時のみエクスポート内容を描画（st.stop()を使わず他タブへの影響を防ぐ）
    if _export_auth_ok:
        with tabs[_tab_idx["📥 データエクスポート"]]:
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("📋 病棟日次データ")
                _export_ward_df = None
                if _DATA_MANAGER_AVAILABLE:
                    try:
                        from bed_data_manager import load_actual_data
                        for _ward in ["5F", "6F"]:
                            _wdf = load_actual_data(_ward)
                            if _wdf is not None and not _wdf.empty:
                                if _export_ward_df is None:
                                    _export_ward_df = _wdf.copy()
                                else:
                                    _export_ward_df = pd.concat([_export_ward_df, _wdf], ignore_index=True)
                    except Exception:
                        pass

                if _export_ward_df is not None and not _export_ward_df.empty:
                    st.write(f"レコード数: {len(_export_ward_df)}件")
                    st.download_button(
                        "⬇️ 病棟日次データ (CSV)",
                        data=_export_ward_df.to_csv(index=False).encode("utf-8-sig"),
                        file_name="ward_daily_data.csv",
                        mime="text/csv",
                        key="dl_ward_data"
                    )
                else:
                    st.info("病棟日次データがありません")

            with col2:
                st.subheader("📋 入退院詳細データ")
                _export_detail_df = None
                if _DATA_MANAGER_AVAILABLE:
                    try:
                        from bed_data_manager import load_admission_details
                        _export_detail_df = load_admission_details()
                    except Exception:
                        pass

                if _export_detail_df is not None and not _export_detail_df.empty:
                    st.write(f"レコード数: {len(_export_detail_df)}件")
                    st.download_button(
                        "⬇️ 入退院詳細データ (CSV)",
                        data=_export_detail_df.to_csv(index=False).encode("utf-8-sig"),
                        file_name="admission_details.csv",
                        mime="text/csv",
                        key="dl_detail_data"
                    )
                else:
                    st.info("入退院詳細データがありません")

            # Scenario export
            st.markdown("---")
            st.subheader("💾 保存済みシナリオ")
            if _SCENARIO_MANAGER_AVAILABLE:
                _export_scenarios = list_scenarios()
                if _export_scenarios:
                    import json as _json_export
                    _sc_json = _json_export.dumps(_export_scenarios, ensure_ascii=False, indent=2, default=str)
                    st.write(f"シナリオ数: {len(_export_scenarios)}件")
                    st.download_button(
                        "⬇️ シナリオデータ (JSON)",
                        data=_sc_json.encode("utf-8"),
                        file_name="saved_scenarios.json",
                        mime="application/json",
                        key="dl_scenarios"
                    )
                else:
                    st.info("保存済みシナリオがありません")
            else:
                st.info("シナリオマネージャーが利用できません")


# ---------------------------------------------------------------------------
# HOPE送信用サマリータブ（Phase 4 で「⚙️ データ・設定」配下へ統合）
# ---------------------------------------------------------------------------
if _HOPE_AVAILABLE and "📨 HOPE送信" in _tab_idx:
    with tabs[_tab_idx["📨 HOPE送信"]]:
        _render_hope_tab()

# ---------------------------------------------------------------------------
# 🏃 短手3設定タブ（Phase 4: 2026-04-18）
# サイドバーの「🏃 短手3（包括点数・種類別）パラメータ」エクスパンダーから移設。
# session_state キー（short3_rev_*, short3_cost_*）は従来のまま維持しており、
# 下流の集計（bed_control_simulator_app.py 上方で構築される _short3_revenue_map）が
# 次回レンダリング時に新しい値を拾う。
# ---------------------------------------------------------------------------
if "🏃 短手3設定" in _tab_idx:
    with tabs[_tab_idx["🏃 短手3設定"]]:
        st.header("🏃 短手3（包括点数・種類別）パラメータ")
        st.caption(
            "短期滞在手術等基本料3 は包括点数で算定されます。種類別に1件あたりの収入とコストを設定できます。"
            + ("（2026年改定で -10% を仮定）" if _is_2026 else "")
        )
        st.info(
            "設定値は入院シミュレーションの **運営貢献額サマリー**・**短手3 分離表示パネル**・"
            "**月次運営貢献額** に反映されます。変更後、シミュレーション実行または"
            "再描画で結果が更新されます。"
        )
        _s3_cols = st.columns(2)
        for _idx, _t in enumerate(
            [SHORT3_TYPE_POLYP_S, SHORT3_TYPE_POLYP_L, SHORT3_TYPE_INGUINAL, SHORT3_TYPE_PSG, SHORT3_TYPE_OTHER]
        ):
            with _s3_cols[_idx % 2]:
                st.markdown(f"**{_t}**")
                _rev = st.number_input(
                    f"{_t} 収入（円/件）",
                    min_value=0, max_value=500000,
                    value=_SHORT3_DEFAULT_REVENUE[_t],
                    step=1000,
                    key=f"short3_rev_{_t}",
                )
                _cost = st.number_input(
                    f"{_t} コスト（円/件）",
                    min_value=0, max_value=200000,
                    value=_SHORT3_DEFAULT_COST[_t],
                    step=1000,
                    key=f"short3_cost_{_t}",
                )
                if _rev > 0:
                    st.caption(f"→ 運営貢献額: **¥{_rev - _cost:,}/件**")
                st.markdown("")

# ---------------------------------------------------------------------------
# 🏥 退院調整セクション（Phase 1 情報階層リデザイン・2026-04-18）:
# 旧「🗓 連休対策」由来の 3 タブ（今週の需要予測・退院候補リスト・入院受入枠 [旧名: 予約可能枠]）
# を「🏥 退院調整」セクションへ移設。共通データ準備ブロックはセクション名のみ
# 差し替え、タブ名は原文を維持する。
# ---------------------------------------------------------------------------
if (
    _selected_section == "\U0001f3e5 退院調整"
    and _DEMAND_FORECAST_AVAILABLE
    and _VIEWS_AVAILABLE
    and _data_ready
    and "\U0001f4ca 今週の需要予測" in _tab_idx
):
    # --- 共通データ準備 ---
    _hs_today = date.today()
    # 対象週: 今週の月曜
    _hs_week_start = _hs_today - timedelta(days=_hs_today.weekday())

    # ward フィルタ
    _hs_ward = _selected_ward_key if _selected_ward_key in ("5F", "6F") else None
    _hs_total_beds = (
        get_ward_beds(_hs_ward) if (_hs_ward and _DATA_MANAGER_AVAILABLE) else total_beds
    )

    # 過去 12ヶ月の入院実績 CSV ロード
    _hs_csv_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "data",
        "admissions_consolidated_dedup.csv",
    )
    try:
        _hs_hist_df = load_historical_admissions(_hs_csv_path)
    except Exception:
        _hs_hist_df = pd.DataFrame()

    # 需要予測
    try:
        _hs_forecast = forecast_weekly_demand(
            _hs_hist_df, _hs_week_start, ward=_hs_ward, lookback_months=12
        )
    except Exception:
        _hs_forecast = {
            "target_week_start": _hs_week_start,
            "dow_means": {i: 0.0 for i in range(7)},
            "expected_weekly_total": 0.0,
            "p25": 0.0,
            "p75": 0.0,
            "recent_trend_factor": 1.0,
            "confidence": "low",
            "sample_size": 0,
        }

    # 曜日別稼働率（直近 8 週）→ 曜日別空床
    _hs_daily_df = st.session_state.get("daily_data", pd.DataFrame())
    _hs_dow_occ = compute_dow_occupancy(
        _hs_daily_df, total_beds=_hs_total_beds, weeks=8, ward=_hs_ward
    )
    _hs_vacancy_by_dow = {
        i: max(0.0, _hs_total_beds * (1.0 - _hs_dow_occ.get(i, 0.9))) for i in range(7)
    }

    # --- タブ 1: 今週の需要予測 ---
    if "\U0001f4ca 今週の需要予測" in _tab_idx:
        with tabs[_tab_idx["\U0001f4ca 今週の需要予測"]]:
            st.header("📊 今週の需要予測")
            st.caption("病棟師長向け：今週の入院予測と既存空床を突合して、前倒し可否を判定します")
            render_weekly_demand_dashboard(
                forecast=_hs_forecast,
                vacancy_by_dow=_hs_vacancy_by_dow,
                ward=_hs_ward,
                total_beds=_hs_total_beds,
                today=_hs_today,
                week_start=_hs_week_start,
            )

    # --- タブ 2: 退院候補リスト ---
    if "\U0001f4cb 退院候補リスト" in _tab_idx:
        with tabs[_tab_idx["\U0001f4cb 退院候補リスト"]]:
            st.header("📋 退院候補リスト")
            st.caption(
                "退院調整会議向け：現在入院中の患者さんを「連休前に退院可能か」で自動仕分けいたします"
            )
            # 次の大型連休情報を取得
            _hs_next_holiday = calculate_next_holiday_countdown(_hs_today)
            # admission_details をセッションから取得
            _hs_details_df = st.session_state.get("admission_details", pd.DataFrame())
            render_discharge_candidates_tab(
                details_df=_hs_details_df,
                daily_df=_hs_daily_df,
                ward=_hs_ward,
                next_holiday=_hs_next_holiday,
                today=_hs_today,
            )

    # --- タブ: 入院受入枠（2026-04-23 改名、旧「予約可能枠」）---
    # 旧タブ名は「📅 予約可能枠」で、退院の枠管理ではなく入院の受入枠を表すことが
    # 分かりにくかったため、2026-04-23 に「📅 入院受入枠」に改名。
    # 退院側は別タブ「📅 退院カレンダー」に分離（discharge_calendar_view）。
    if "\U0001f4c5 入院受入枠" in _tab_idx:
        with tabs[_tab_idx["\U0001f4c5 入院受入枠"]]:
            st.header("📅 入院受入枠")
            st.caption(
                "予約受付事務員向け：外来から入院依頼があった時に 4 週間先までの受入可能枠を確認します。"
                "退院側のカレンダーは「📅 退院カレンダー」タブを参照してください。"
            )
            # 既に上で計算済みの変数を流用
            _hs_details_df_tab3 = st.session_state.get("admission_details", pd.DataFrame())
            render_booking_availability_calendar(
                forecast=_hs_forecast,
                details_df=_hs_details_df_tab3,
                daily_df=_hs_daily_df,
                ward=_hs_ward,
                total_beds=_hs_total_beds,
                today=_hs_today,
                weeks_ahead=4,
            )
            st.caption(
                "4 週間先までの日別予想需要を、予約受付事務員向けに色分け表示いたします。"
            )

# ---------------------------------------------------------------------------
# 🏥 退院調整セクション — 🏥 カンファ資料 タブ
# conference_material_view が自律的に病棟・モード切替・4 ブロック + ファクト
# バーを描画するため、ここではタブコンテキストに入って関数を呼び出すだけ。
# data-testid (conference-*) は view 内部で hidden div として出力される。
# ---------------------------------------------------------------------------
if (
    _selected_section == "\U0001f3e5 退院調整"
    and _CONFERENCE_VIEW_AVAILABLE
    and _data_ready
    and "\U0001f3e5 カンファ資料" in _tab_idx
):
    with tabs[_tab_idx["\U0001f3e5 カンファ資料"]]:
        st.caption(
            "木曜ハドル／連休対策カンファで 1 画面運用。病棟・モードを切り替え、"
            "カンファ中にステータス欄を更新してください。"
        )
        try:
            render_conference_material_view(today=date.today())
        except Exception as _cv_render_err:
            st.error(
                "カンファ資料の描画中にエラーが発生しました。"
                "設定（target_config / holiday_calendar / data/facts.yaml）を確認してください。"
            )
            with st.expander("エラー詳細（開発用）", expanded=False):
                import traceback as _cv_render_tb
                st.code(f"{_cv_render_err}\n{_cv_render_tb.format_exc()}")
elif (
    _selected_section == "\U0001f3e5 退院調整"
    and not _CONFERENCE_VIEW_AVAILABLE
):
    # 通常ここには来ないが（_section_names に入らないため）、
    # 万が一ルート経由で来た場合のフォールバック。
    st.error(
        "カンファビューが読み込めませんでした。views/conference_material_view.py の"
        "依存モジュール（yaml / target_config / holiday_calendar）を確認してください。"
    )
    if _CONFERENCE_VIEW_ERROR:
        with st.expander("エラー詳細", expanded=False):
            st.code(_CONFERENCE_VIEW_ERROR)

# ---------------------------------------------------------------------------
# 🏥 退院調整セクション — 📅 退院カレンダー タブ（Ph.2, 2026-04-23 副院長指示）
# ---------------------------------------------------------------------------
# 月俯瞰カレンダーで退院予定を 3 層（調整中/予定/決定）で可視化し、
# 入院予定を重ねて稼働率方向を示す。病棟別（5F/6F）× 当月/翌月のタブ構造。
# 日曜枠は推奨マーカーとして視覚的に強調する。
if (
    _selected_section == "\U0001f3e5 退院調整"
    and _DISCHARGE_CAL_VIEW_AVAILABLE
    and "\U0001f4c5 退院カレンダー" in _tab_idx
):
    with tabs[_tab_idx["\U0001f4c5 退院カレンダー"]]:
        try:
            _dc_details_df = st.session_state.get("admission_details", pd.DataFrame())
            # 祝日セット（holiday_calendar が使えれば利用、無ければ空セット）
            _dc_jp_holidays = set()
            try:
                from holiday_calendar import is_holiday as _dc_is_holiday  # type: ignore
                # 当月・翌月の範囲で祝日を列挙
                _dc_today = date.today()
                _dc_start = _dc_today.replace(day=1)
                _dc_end = (_dc_start + timedelta(days=70)).replace(day=1) + timedelta(days=35)
                for _dc_i in range((_dc_end - _dc_start).days):
                    _dc_d = _dc_start + timedelta(days=_dc_i)
                    if _dc_is_holiday(_dc_d):
                        _dc_jp_holidays.add(_dc_d)
            except Exception:
                _dc_jp_holidays = set()
            render_discharge_calendar_tab(
                admission_details_df=_dc_details_df,
                today=date.today(),
                jp_holidays=_dc_jp_holidays,
            )
        except Exception as _dc_render_err:
            st.error(
                "退院カレンダーの描画中にエラーが発生しました。"
                "discharge_plan_store / discharge_slot_config を確認してください。"
            )
            with st.expander("エラー詳細（開発用）", expanded=False):
                import traceback as _dc_render_tb
                st.code(f"{_dc_render_err}\n{_dc_render_tb.format_exc()}")
elif (
    _selected_section == "\U0001f3e5 退院調整"
    and not _DISCHARGE_CAL_VIEW_AVAILABLE
    and "\U0001f4c5 退院カレンダー" in _tab_idx
):
    with tabs[_tab_idx["\U0001f4c5 退院カレンダー"]]:
        st.error(
            "退院カレンダービューが読み込めませんでした。"
            "views/discharge_calendar_view.py の依存モジュールを確認してください。"
        )
        if _DISCHARGE_CAL_VIEW_ERROR:
            with st.expander("エラー詳細", expanded=False):
                st.code(_DISCHARGE_CAL_VIEW_ERROR)

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
    # 2026-04-18: 戦略選択 UI 廃止に伴い「戦略: バランス戦略」表示を削除
    st.caption(
        f"病床数: {_view_beds} | "
        f"目標稼働率: {target_lower*100:.0f}-{target_upper*100:.0f}% | "
        f"月間入院: {_active_cli_params.get('monthly_admissions', monthly_admissions)}件 | "
        f"平均在院日数: {avg_los}日"
    )
