"""
C群コントロールモジュール — 制度余力の中でC群を弾力運用する

C群（退院準備期）は院内運用上のラベルであり、制度上の公式区分ではない。
在院15日目以降の患者を指し、退院日の前後に一定の調整余地がある。

このモジュールの目的:
- 制度要件（平均在院日数の上限）を守りながら
- 需要の谷をC群の退院タイミング調整で埋め
- 不要な稼働率低下を和らげる

「C群を長く置く」こと自体が目的ではない。
医学的に不適切な在院延長は提案しない。
推計値はすべて "proxy" とラベルする。
"""

from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# 外部モジュールのインポート（フォールバック付き）
# ---------------------------------------------------------------------------

try:
    from scripts.bed_data_manager import (
        DEFAULT_REVENUE_PARAMS,
        calculate_rolling_los,
    )
    _HAS_BED_DATA_MANAGER = True
except ImportError:
    try:
        from bed_data_manager import (
            DEFAULT_REVENUE_PARAMS,
            calculate_rolling_los,
        )
        _HAS_BED_DATA_MANAGER = True
    except ImportError:
        _HAS_BED_DATA_MANAGER = False
        DEFAULT_REVENUE_PARAMS = {
            "phase_c_revenue": 33400,
            "phase_c_cost": 4500,
        }

        def calculate_rolling_los(df, window_days=90):
            """フォールバック: bed_data_manager が読み込めない場合の代替。"""
            return None

# ---------------------------------------------------------------------------
# C群（退院準備期）の経済指標
# bed_data_manager.py の DEFAULT_REVENUE_PARAMS から引用
# ---------------------------------------------------------------------------

C_PHASE_START_DAY = 15          # C群開始日（15日目以降）
C_REVENUE_PER_DAY = 33400       # C群 日次診療報酬（円）
C_COST_PER_DAY = 4500           # C群 日次変動費（円）
C_CONTRIBUTION_PER_DAY = 28900  # C群 1日あたり運営貢献額（円）

# 空床のコスト（空いていれば収益ゼロ）
EMPTY_BED_CONTRIBUTION = 0

# 病床数
TOTAL_BEDS = 94


# ---------------------------------------------------------------------------
# 1. C群サマリー
# ---------------------------------------------------------------------------

def get_c_group_summary(
    daily_df: Optional[pd.DataFrame],
    ward: Optional[str] = None,
    target_date: Optional[date] = None,
) -> dict:
    """当日のC群状態を要約する。

    C群（在院15日目以降）は院内運用上のラベルであり、制度上の公式区分ではない。
    phase_c_count 列があれば実測値、なければ discharge_c から粗い推定を行う。

    Args:
        daily_df: 日次ベッドコントロールデータ。None 可。
        ward: 病棟フィルタ（"5F", "6F" 等）。None なら全体。
        target_date: 対象日。None なら最新日。

    Returns:
        C群サマリー dict。データなしの場合も安全に dict を返す。
    """
    empty_result = {
        "c_count": 0,
        "c_ratio": 0.0,
        "total_patients": 0,
        "c_daily_contribution": 0.0,
        "data_source": "not_available",
        "target_date": str(target_date) if target_date else None,
    }

    if daily_df is None or len(daily_df) == 0:
        return empty_result

    df = daily_df.copy()

    # 日付列の処理
    date_col = None
    for _c in ["date", "日付"]:
        if _c in df.columns:
            date_col = _c
            break
    if date_col is None:
        return empty_result

    df[date_col] = pd.to_datetime(df[date_col])

    # 病棟フィルタ
    if ward and "ward" in df.columns:
        df = df[df["ward"] == ward]
        if len(df) == 0:
            return empty_result

    # 対象日の決定
    if target_date:
        target_dt = pd.Timestamp(target_date)
        day_df = df[df[date_col] == target_dt]
    else:
        target_dt = df[date_col].max()
        day_df = df[df[date_col] == target_dt]

    if len(day_df) == 0:
        return empty_result

    row = day_df.iloc[-1]  # 複数行ある場合は最後を採用
    total_patients = int(row.get("total_patients", 0) or 0)
    resolved_date = str(target_dt.date()) if hasattr(target_dt, "date") else str(target_dt)

    # --- C群患者数の推定 ---
    # 方法1: phase_c_count 列があればそれを使用（実測値）
    if "phase_c_count" in df.columns and pd.notna(row.get("phase_c_count")):
        c_count = int(row["phase_c_count"])
        data_source = "measured"
    else:
        # 方法2: 直近7日の discharge_c の平均 × 平均C群在院日数 で概算
        # C群在院者 ≈ discharge_c_7d_avg × (avg_los - C_PHASE_START_DAY + 1)
        # ※ これは非常に粗い推定（proxy）
        data_source = "proxy"
        c_count = 0

        if "discharge_c" in df.columns:
            df_sorted = df.sort_values(date_col)
            recent = df_sorted.tail(7)
            discharge_c_vals = pd.to_numeric(recent["discharge_c"], errors="coerce").fillna(0)
            dc_avg = float(discharge_c_vals.mean())

            # 平均在院日数の推定（avg_los列があれば使用、なければ19日と仮定）
            if "avg_los" in recent.columns:
                avg_los_vals = pd.to_numeric(recent["avg_los"], errors="coerce").dropna()
                avg_los = float(avg_los_vals.mean()) if len(avg_los_vals) > 0 else 19.0
            else:
                avg_los = 19.0

            c_stay_days = max(avg_los - C_PHASE_START_DAY + 1, 1.0)
            c_count = max(int(round(dc_avg * c_stay_days)), 0)

    c_ratio = (c_count / total_patients * 100) if total_patients > 0 else 0.0

    return {
        "c_count": c_count,
        "c_ratio": round(c_ratio, 1),
        "total_patients": total_patients,
        "c_daily_contribution": c_count * C_CONTRIBUTION_PER_DAY,
        "data_source": data_source,
        "target_date": resolved_date,
    }


# ---------------------------------------------------------------------------
# 2. C群調整キャパシティ（最も重要な関数）
# ---------------------------------------------------------------------------

def calculate_c_adjustment_capacity(
    rolling_los_result: Optional[dict],
    guardrail_los_limit: float,
    c_count: Optional[int] = None,
) -> dict:
    """制度余力の中でC群をどれだけ調整できるかを計算する。

    C群（在院15日目以降）は院内運用上のラベルであり、制度上の公式区分ではない。
    LOS余力は推計値（proxy）である。個票ベースの精密計算ではない。

    Args:
        rolling_los_result: calculate_rolling_los() の戻り値 dict。None 可。
        guardrail_los_limit: 制度上の平均在院日数上限（日）。
        c_count: 現在のC群患者数（既知の場合）。

    Returns:
        C群調整キャパシティ dict。
    """
    # データなしの安全なフォールバック
    if rolling_los_result is None:
        return {
            "current_los": None,
            "los_limit": guardrail_los_limit,
            "headroom_days": None,
            "headroom_patient_days": None,
            "can_delay_discharge": False,
            "max_delay_bed_days": 0.0,
            "can_accelerate_discharge": True,
            "delay_revenue_per_day": C_CONTRIBUTION_PER_DAY,
            "status": "データなし",
            "status_color": "gray",
            "warning_message": "⚠️ rolling LOS データがありません",
            "data_source": "proxy",
        }

    # 短手3除外後のLOSを優先
    current_los = (
        rolling_los_result.get("rolling_los_ex_short3")
        or rolling_los_result.get("rolling_los")
    )

    if current_los is None:
        return {
            "current_los": None,
            "los_limit": guardrail_los_limit,
            "headroom_days": None,
            "headroom_patient_days": None,
            "can_delay_discharge": False,
            "max_delay_bed_days": 0.0,
            "can_accelerate_discharge": True,
            "delay_revenue_per_day": C_CONTRIBUTION_PER_DAY,
            "status": "データなし",
            "status_color": "gray",
            "warning_message": "⚠️ 平均在院日数を算出できません",
            "data_source": "proxy",
        }

    # --- 余力の計算 ---
    headroom_days = guardrail_los_limit - current_los

    # patient-days への換算
    total_admissions = rolling_los_result.get("total_admissions", 0)
    total_discharges = rolling_los_result.get("total_discharges", 0)
    actual_days = rolling_los_result.get("actual_days", 1)

    n_denominator = (total_admissions + total_discharges) / 2  # rolling windowの分母
    if actual_days > 0 and n_denominator > 0:
        headroom_patient_days = headroom_days * n_denominator / actual_days
    else:
        headroom_patient_days = 0.0

    # 退院タイミングの調整可否
    can_delay = headroom_days > 0.5
    max_delay_bed_days = max(headroom_patient_days, 0.0)

    # ステータス判定
    if headroom_days >= 2.0:
        status = "余力あり"
        status_color = "green"
    elif headroom_days >= 0.5:
        status = "余力わずか"
        status_color = "yellow"
    else:
        status = "余力なし"
        status_color = "red"

    # 警告メッセージ
    warning_message: Optional[str] = None
    if headroom_days < 0:
        warning_message = "⚠️ 平均在院日数が制度上限を超過しています。C群の退院を優先してください"
    elif headroom_days < 1.0:
        warning_message = "⚠️ 平均在院日数の制度余力が1日未満です"

    return {
        "current_los": round(current_los, 2),
        "los_limit": guardrail_los_limit,
        "headroom_days": round(headroom_days, 2),
        "headroom_patient_days": round(headroom_patient_days, 1),
        "can_delay_discharge": can_delay,
        "max_delay_bed_days": round(max_delay_bed_days, 1),
        "can_accelerate_discharge": True,  # 前倒し退院は常に可能
        "delay_revenue_per_day": C_CONTRIBUTION_PER_DAY,
        "status": status,
        "status_color": status_color,
        "warning_message": warning_message,
        "data_source": "proxy",  # 常にproxy（個票なしのため）
    }


# ---------------------------------------------------------------------------
# 3. C群シナリオシミュレーション
# ---------------------------------------------------------------------------

def simulate_c_group_scenario(
    rolling_los_result: Optional[dict],
    guardrail_los_limit: float,
    n_delay: int = 0,
    delay_days: int = 0,
    n_accelerate: int = 0,
    accelerate_days: int = 0,
) -> dict:
    """C群を操作した場合のLOS変動をシミュレートする。

    C群（在院15日目以降）は院内運用上のラベルであり、制度上の公式区分ではない。
    シミュレーション結果は推計値であり、実際の制度判定とは異なる場合がある。

    Args:
        rolling_los_result: calculate_rolling_los() の戻り値 dict。None 可。
        guardrail_los_limit: 制度上の平均在院日数上限（日）。
        n_delay: 退院を後ろ倒しする患者数。
        delay_days: 1患者あたりの後ろ倒し日数。
        n_accelerate: 退院を前倒しする患者数。
        accelerate_days: 1患者あたりの前倒し日数。

    Returns:
        シミュレーション結果 dict。
    """
    if rolling_los_result is None:
        return {
            "original_los": None,
            "simulated_los": None,
            "los_delta": None,
            "within_guardrail": False,
            "revenue_impact_daily": 0.0,
            "revenue_impact_monthly": 0.0,
            "description": "rolling LOS データがないためシミュレーションできません",
        }

    original_los = (
        rolling_los_result.get("rolling_los_ex_short3")
        or rolling_los_result.get("rolling_los")
    )

    if original_los is None:
        return {
            "original_los": None,
            "simulated_los": None,
            "los_delta": None,
            "within_guardrail": False,
            "revenue_impact_daily": 0.0,
            "revenue_impact_monthly": 0.0,
            "description": "平均在院日数を算出できないためシミュレーションできません",
        }

    total_patient_days = rolling_los_result.get("total_patient_days", 0)
    total_admissions = rolling_los_result.get("total_admissions", 0)
    total_discharges = rolling_los_result.get("total_discharges", 0)

    # LOS変動の計算
    delta_patient_days = (n_delay * delay_days) - (n_accelerate * accelerate_days)
    new_patient_days = total_patient_days + delta_patient_days

    # 分母は変わらない（入退院数は同じ。退院タイミングのシフトのみ）
    # ※ 前倒し退院で新規入院が入れば分母も変わるが、保守的に固定
    denominator = (total_admissions + total_discharges) / 2

    if denominator > 0:
        simulated_los = new_patient_days / denominator
    else:
        simulated_los = original_los

    los_delta = simulated_los - original_los
    within_guardrail = simulated_los <= guardrail_los_limit

    # 収益影響の計算
    # 後ろ倒し分: C群を残すことで得る収益
    # 前倒し分: C群収益の喪失（新規入院の保証なし → 保守的に損失として計算）
    revenue_impact_daily = (n_delay * C_CONTRIBUTION_PER_DAY) - (n_accelerate * C_CONTRIBUTION_PER_DAY)
    revenue_impact_monthly = revenue_impact_daily * 30

    # 結果説明文の生成
    parts = []
    if n_delay > 0:
        parts.append(f"C群 {n_delay}名の退院を {delay_days}日後ろ倒し")
    if n_accelerate > 0:
        parts.append(f"C群 {n_accelerate}名の退院を {accelerate_days}日前倒し")

    operation = "・".join(parts) if parts else "操作なし"
    guardrail_text = "制度内" if within_guardrail else "⚠️ 制度超過"

    description = (
        f"{operation} → LOS {original_los:.1f}日 → {simulated_los:.1f}日 "
        f"({los_delta:+.1f}日, {guardrail_text}), "
        f"月次収益影響 {revenue_impact_monthly:+,.0f}円（推計）"
    )

    return {
        "original_los": round(original_los, 2),
        "simulated_los": round(simulated_los, 2),
        "los_delta": round(los_delta, 2),
        "within_guardrail": within_guardrail,
        "revenue_impact_daily": revenue_impact_daily,
        "revenue_impact_monthly": revenue_impact_monthly,
        "description": description,
    }


# ---------------------------------------------------------------------------
# 4. 需要吸収計算
# ---------------------------------------------------------------------------

def calculate_demand_absorption(
    c_adjustment_capacity: dict,
    demand_trend: str,
    occupancy_rate: float,
    target_occupancy: float = 0.90,
) -> dict:
    """需要の谷をC群でどれだけ吸収できるかを計算する。

    C群（在院15日目以降）は院内運用上のラベルであり、制度上の公式区分ではない。
    吸収可能量は推計値（proxy）である。

    Args:
        c_adjustment_capacity: calculate_c_adjustment_capacity() の戻り値 dict。
        demand_trend: 需要トレンド（"increasing" / "decreasing" / "stable"）。
        occupancy_rate: 現在の稼働率（0〜1の小数）。
        target_occupancy: 目標稼働率（デフォルト0.90）。

    Returns:
        需要吸収計算結果 dict。
    """
    demand_gap = target_occupancy - occupancy_rate  # 正なら稼働率不足
    demand_gap_beds = demand_gap * TOTAL_BEDS

    max_delay_bed_days = c_adjustment_capacity.get("max_delay_bed_days", 0.0)

    # C群で吸収可能な床数（7日間分の後ろ倒し可能bed-daysを1日あたりに換算）
    absorbable_by_c = min(max_delay_bed_days / 7, demand_gap_beds) if demand_gap_beds > 0 else 0.0
    absorbable_by_c = max(absorbable_by_c, 0.0)

    absorption_rate = (absorbable_by_c / demand_gap_beds * 100) if demand_gap_beds > 0 else 0.0

    # 推奨の判定
    if demand_trend == "decreasing" and demand_gap > 0:
        # 需要減少 + 稼働率不足 → C群キープ推奨
        recommendation = "C群キープ推奨"
        recommendation_reason = (
            f"需要減少トレンドかつ稼働率が目標を {demand_gap*100:.1f}pt 下回っています。"
            "C群の退院を急がず、制度余力の範囲内で在院を維持することで稼働率を下支えできます"
        )
    elif demand_trend == "increasing" and occupancy_rate >= target_occupancy:
        # 需要増加 + 稼働率十分 → C群前倒し推奨
        recommendation = "C群前倒し推奨"
        recommendation_reason = (
            "需要増加トレンドかつ稼働率は目標以上です。"
            "C群の前倒し退院で受入枠を確保し、新規入院を受け入れる余地を作れます"
        )
    else:
        recommendation = "現状維持"
        recommendation_reason = "需要トレンドと稼働率の組み合わせから、現時点でC群の積極的な調整は不要です"

    absorption_description = (
        f"目標稼働率 {target_occupancy*100:.0f}% との差: {demand_gap*100:.1f}pt "
        f"({demand_gap_beds:.1f}床相当)。"
        f"C群で吸収可能: {absorbable_by_c:.1f}床 ({absorption_rate:.0f}%)（推計）"
    )

    return {
        "demand_gap": round(demand_gap, 4),
        "demand_gap_beds": round(demand_gap_beds, 1),
        "absorbable_by_c": round(absorbable_by_c, 1),
        "absorption_rate": round(absorption_rate, 1),
        "absorption_description": absorption_description,
        "recommendation": recommendation,
        "recommendation_reason": recommendation_reason,
    }


# ---------------------------------------------------------------------------
# 5. C群アラート生成
# ---------------------------------------------------------------------------

def generate_c_group_alerts(
    c_summary: dict,
    c_capacity: dict,
    demand_classification: str | None = None,
    emergency_ratio_risk: dict | None = None,
) -> list[dict]:
    """C群コントロールに関するアラートを生成する。

    C群（在院15日目以降）は院内運用上のラベルであり、制度上の公式区分ではない。

    Args:
        c_summary: get_c_group_summary() の戻り値 dict。
        c_capacity: calculate_c_adjustment_capacity() の戻り値 dict。
        demand_classification: 需要分類（"quiet" / "normal" / "busy"）。

    Returns:
        アラートのリスト。各アラートは level / message / category を持つ dict。
    """
    alerts: list[dict] = []
    headroom_days = c_capacity.get("headroom_days")
    c_ratio = c_summary.get("c_ratio", 0.0)

    # headroom_days が None の場合はアラートを出さない（データ不足）
    if headroom_days is None:
        return alerts

    # 制度超過（最重要）
    if headroom_days < 0:
        alerts.append({
            "level": "danger",
            "message": "平均在院日数が制度上限を超過中。C群の退院を最優先で進めてください",
            "category": "c_group",
        })

    # LOS余力わずか + 閑散期
    if 0 <= headroom_days < 1 and demand_classification == "quiet":
        alerts.append({
            "level": "warning",
            "message": "LOS余力わずか、需要閑散期のためC群延長は慎重に",
            "category": "c_group",
        })

    # C群構成比が高い
    if c_ratio > 30:
        alerts.append({
            "level": "warning",
            "message": f"C群が {c_ratio:.0f}% と高水準。退院調整の停滞に注意してください",
            "category": "c_group",
        })

    # 閑散期 + 余力あり → C群キープの好機
    if demand_classification == "quiet" and headroom_days >= 2:
        alerts.append({
            "level": "info",
            "message": "需要閑散期・LOS余力あり。C群キープで稼働率を下支えできます",
            "category": "c_group",
        })

    # 繁忙期 → 前倒し退院の好機
    if demand_classification == "busy":
        alerts.append({
            "level": "info",
            "message": "需要繁忙期。C群の前倒し退院で受入枠を確保できます",
            "category": "c_group",
        })

    # 救急搬送後患者割合リスク — C群長期滞在とのトレードオフ
    if emergency_ratio_risk is not None:
        for ward_name, ward_risk in emergency_ratio_risk.items():
            if isinstance(ward_risk, dict) and ward_risk.get("status") == "red":
                additional = ward_risk.get("additional_needed", 0)
                ratio_pct = ward_risk.get("ratio_pct", 0.0)
                alerts.append({
                    "level": "warning",
                    "category": "emergency_ratio",
                    "message": (
                        f"{ward_name} の救急搬送後患者割合が {ratio_pct:.1f}%（目標15%）と低く、"
                        f"あと {additional} 件の救急入院が必要です。"
                        "C群の長期滞在がベッドを占有すると救急受入枠が減り、"
                        "割合改善が困難になります"
                        "（C群キープ↔救急受入のトレードオフに注意）"
                    ),
                })

    return alerts
