"""
地域包括医療病棟入院料 施設基準チェックエンジン

日次データから自動計算可能な制度指標の充足状況を判定する pure function モジュール。
Streamlit に依存しない。すべての関数は dict を返す（JSON互換性のため）。

注意:
    本モジュールで使用する「A群（1-5日目）」「B群（6-14日目）」「C群（15日目以降）」は
    院内運用上の便宜的ラベルであり、制度上の公式区分ではない。
    施設基準の判定は厚労省の公式定義に基づいて行う。

依存モジュール（import失敗時はフォールバックあり）:
    - reimbursement_config: FACILITY_CONSTRAINTS, HOSPITAL_DEFAULTS
    - bed_data_manager: calculate_rolling_los
"""

from __future__ import annotations

from typing import Optional

# ---------------------------------------------------------------------------
# 外部モジュールのインポート（フォールバック付き）
# ---------------------------------------------------------------------------

try:
    from scripts.reimbursement_config import FACILITY_CONSTRAINTS, HOSPITAL_DEFAULTS
    _HAS_REIMBURSEMENT_CONFIG = True
except ImportError:
    try:
        from reimbursement_config import FACILITY_CONSTRAINTS, HOSPITAL_DEFAULTS
        _HAS_REIMBURSEMENT_CONFIG = True
    except ImportError:
        _HAS_REIMBURSEMENT_CONFIG = False
        FACILITY_CONSTRAINTS = []
        HOSPITAL_DEFAULTS = {}

try:
    from scripts.bed_data_manager import calculate_rolling_los
    _HAS_BED_DATA_MANAGER = True
except ImportError:
    try:
        from bed_data_manager import calculate_rolling_los
        _HAS_BED_DATA_MANAGER = True
    except ImportError:
        _HAS_BED_DATA_MANAGER = False

try:
    from scripts.emergency_ratio import calculate_rolling_emergency_ratio
    _HAS_ROLLING_EMG = True
except ImportError:
    try:
        from emergency_ratio import calculate_rolling_emergency_ratio
        _HAS_ROLLING_EMG = True
    except ImportError:
        _HAS_ROLLING_EMG = False

        def calculate_rolling_los(df, window_days=90):
            """フォールバック: bed_data_manager が読み込めない場合の代替実装。

            Args:
                df: 日次データ DataFrame
                window_days: rolling window 日数

            Returns:
                dict or None
            """
            if df is None or len(df) == 0:
                return None
            try:
                import pandas as pd

                df_sorted = df.copy()
                if "date" in df_sorted.columns:
                    df_sorted["date"] = pd.to_datetime(df_sorted["date"])
                    df_sorted = df_sorted.sort_values("date")
                    end_date = df_sorted["date"].max()
                    start_date = end_date - pd.Timedelta(days=window_days - 1)
                    mask = df_sorted["date"] >= start_date
                    window_df = df_sorted[mask]
                else:
                    window_df = df_sorted.tail(window_days)
                    end_date = None
                    start_date = None

                actual_days = len(window_df)
                if actual_days == 0:
                    return None

                total_patient_days = float(window_df["total_patients"].sum())
                total_admissions = float(window_df["new_admissions"].sum())
                total_discharges = float(window_df["discharges"].sum())
                denominator = (total_admissions + total_discharges) / 2.0

                rolling_los = (
                    total_patient_days / denominator if denominator > 0 else None
                )

                return {
                    "rolling_los": rolling_los,
                    "rolling_los_ex_short3": rolling_los,
                    "actual_days": actual_days,
                    "total_patient_days": total_patient_days,
                    "total_admissions": total_admissions,
                    "total_discharges": total_discharges,
                    "total_short3": 0.0,
                    "is_partial": actual_days < window_days,
                    "end_date": end_date,
                    "start_date": start_date,
                }
            except Exception:
                return None


# ---------------------------------------------------------------------------
# 定数: 2026年改定 地域包括医療病棟入院料1 施設基準
# ---------------------------------------------------------------------------
# reimbursement_config.py の FACILITY_CONSTRAINTS と整合させるが、
# このモジュール単体でも動くようにデフォルト値を持つ

DEFAULT_GUARDRAIL_THRESHOLDS = {
    "avg_los": {
        "base_limit": 20.0,         # 原則20日以内
        "max_limit": 24.0,          # 85歳以上80%以上の場合
        "age85_brackets": [         # (割合下限, 上限日数)
            (0.0, 20.0),
            (0.20, 21.0),
            (0.40, 22.0),
            (0.60, 23.0),
            (0.80, 24.0),
        ],
        "operator": "<=",
        "description": "平均在院日数",
    },
    "emergency_ratio": {
        "threshold": 15.0,          # 15%以上
        "operator": ">=",
        "description": "救急搬送後患者割合",
    },
    "transfer_in_ratio": {
        "threshold": 5.0,           # 5%未満
        "operator": "<",
        "description": "同一医療機関一般病棟からの転棟割合",
    },
    "home_discharge_rate": {
        "threshold": 80.0,          # 80%以上（直近6ヶ月）
        "operator": ">=",
        "description": "在宅復帰率",
        "auto_calculable": False,   # 退院先データがないため自動計算不可
    },
    "adl_decline": {
        "threshold": 5.0,           # 5%未満
        "operator": "<",
        "description": "ADL低下割合",
        "auto_calculable": False,
    },
    "nursing_necessity_i": {
        "threshold": 19.0,          # 19%以上
        "operator": ">=",
        "description": "重症度・医療看護必要度I",
        "auto_calculable": False,
    },
}


# ---------------------------------------------------------------------------
# 関数
# ---------------------------------------------------------------------------


def calculate_los_limit(age_85_ratio: float) -> float:
    """85歳以上患者割合から、調整済み平均在院日数上限を返す。

    age85_brackets を参照して段階的に判定する。
    割合が高いほど上限が緩和される（最大24日）。

    Args:
        age_85_ratio: 85歳以上患者割合（0.0〜1.0）

    Returns:
        調整済みの平均在院日数上限（日）
    """
    brackets = DEFAULT_GUARDRAIL_THRESHOLDS["avg_los"]["age85_brackets"]
    # 降順に走査して最初にマッチしたものを返す
    limit = brackets[0][1]  # デフォルト: 20.0
    for ratio_lower, days_limit in brackets:
        if age_85_ratio >= ratio_lower:
            limit = days_limit
    return limit


def calculate_guardrail_status(
    daily_df,
    detail_df=None,
    config: Optional[dict] = None,
) -> list[dict]:
    """日次データから制度指標の充足状況を計算する。

    Args:
        daily_df: 日次ベッドコントロールデータ（DataFrame）。
            calculate_rolling_los() に渡せる形式。None可。
        detail_df: 入退院詳細データ（DataFrame、任意）。
            "route" カラムがあれば救急搬送割合を計算できる。
        config: 設定辞書。以下のキーを参照する:
            - age_85_ratio (float): 85歳以上患者割合（デフォルト0.25）
            - home_discharge_rate (float): 手動入力の在宅復帰率
            - adl_decline (float): 手動入力のADL低下割合
            - nursing_necessity_i (float): 手動入力の重症度・医療看護必要度I

    Returns:
        指標ごとの充足状況を表す dict のリスト。
        各 dict の構造:
            name (str): 指標名
            current_value (float): 現在値
            threshold (float): 基準値
            operator (str): 比較演算子 ("<=", ">=", "<")
            margin (float): 余力（正=安全圏、負=逸脱）
            status (str): "safe" / "warning" / "danger"
            data_source (str): "measured" / "proxy" / "manual_input" / "not_available"
            description (str): 説明文
    """
    config = config or {}
    age_85_ratio = config.get("age_85_ratio", 0.25)
    results: list[dict] = []

    # ---------------------------------------------------------------
    # 1. 平均在院日数
    # ---------------------------------------------------------------
    los_limit = calculate_los_limit(age_85_ratio)
    los_result = calculate_rolling_los(daily_df) if daily_df is not None else None

    if los_result is not None:
        # rolling_los_ex_short3 があればそちらを優先
        current_los = (
            los_result.get("rolling_los_ex_short3")
            or los_result.get("rolling_los")
        )
        if current_los is not None:
            margin = los_limit - current_los
            status = _margin_to_status(margin, safe_threshold=2.0)
            results.append({
                "name": "平均在院日数",
                "current_value": round(current_los, 2),
                "threshold": los_limit,
                "operator": "<=",
                "margin": round(margin, 2),
                "status": status,
                "data_source": "measured",
                "description": (
                    f"rolling 90日平均在院日数 "
                    f"（85歳以上{age_85_ratio:.0%}→上限{los_limit:.0f}日）"
                ),
            })
        else:
            results.append(_not_available_item(
                "平均在院日数", los_limit, "<=",
                "rolling LOS計算不可（データ不足）",
            ))
    else:
        results.append(_not_available_item(
            "平均在院日数", los_limit, "<=",
            "日次データなし",
        ))

    # ---------------------------------------------------------------
    # 2. 救急搬送後患者割合（直近3ヶ月rolling平均）
    # ---------------------------------------------------------------
    emg_threshold = DEFAULT_GUARDRAIL_THRESHOLDS["emergency_ratio"]["threshold"]
    monthly_summary = config.get("monthly_summary") if config else None
    _emg_calculated = False

    if _HAS_ROLLING_EMG and detail_df is not None and len(detail_df) > 0 and "route" in detail_df.columns:
        rolling_emg = calculate_rolling_emergency_ratio(
            detail_df, ward=config.get("ward") if config else None,
            monthly_summary=monthly_summary,
        )
        if rolling_emg["denominator"] > 0:
            current_emg = rolling_emg["ratio_pct"]
            margin = current_emg - emg_threshold
            status = _margin_to_status(margin, safe_threshold=5.0)
            # 月別内訳テキスト
            months_info = " / ".join(
                f"{mb['year_month']}:{mb['numerator']}/{mb['denominator']}"
                for mb in rolling_emg["monthly_breakdown"]
                if mb["denominator"] > 0
            )
            results.append({
                "name": "救急搬送後患者割合",
                "current_value": round(current_emg, 1),
                "threshold": emg_threshold,
                "operator": ">=",
                "margin": round(margin, 1),
                "status": status,
                "data_source": "measured",
                "description": (
                    f"直近3ヶ月rolling平均 "
                    f"{rolling_emg['numerator']}/{rolling_emg['denominator']}件"
                    f"（{months_info}）"
                ),
            })
            _emg_calculated = True

    if not _emg_calculated:
        # フォールバック: rolling関数が使えない場合は従来の単月計算
        if detail_df is not None and len(detail_df) > 0 and "route" in detail_df.columns:
            admissions_df = detail_df[detail_df["event_type"] == "admission"]
            total_admissions = len(admissions_df)
            emergency_count = int(admissions_df["route"].isin(["救急", "下り搬送"]).sum())
            current_emg = (emergency_count / total_admissions * 100) if total_admissions > 0 else 0.0
            margin = current_emg - emg_threshold
            status = _margin_to_status(margin, safe_threshold=5.0)
            results.append({
                "name": "救急搬送後患者割合",
                "current_value": round(current_emg, 1),
                "threshold": emg_threshold,
                "operator": ">=",
                "margin": round(margin, 1),
                "status": status,
                "data_source": "measured",
                "description": f"救急・下り搬送後入院 {emergency_count}/{total_admissions}件",
            })
        else:
            results.append(_not_available_item(
                "救急搬送後患者割合", emg_threshold, ">=",
                "入退院詳細データなし",
            ))

    # ---------------------------------------------------------------
    # 3. 同一医療機関一般病棟からの転棟割合
    # ---------------------------------------------------------------
    # 当院は急性期病棟非併設(TYPE_1)のため、構造的にゼロ
    transfer_threshold = DEFAULT_GUARDRAIL_THRESHOLDS["transfer_in_ratio"]["threshold"]
    results.append({
        "name": "同一医療機関一般病棟からの転棟割合",
        "current_value": 0.0,
        "threshold": transfer_threshold,
        "operator": "<",
        "margin": round(transfer_threshold - 0.0, 1),
        "status": "safe",
        "data_source": "measured",
        "description": "急性期病棟非併設(TYPE_1)のため構造的にゼロ",
    })

    # ---------------------------------------------------------------
    # 4. 在宅復帰率（手動入力 or not_available）
    # ---------------------------------------------------------------
    _append_manual_or_na(
        results, config,
        key="home_discharge_rate",
        name="在宅復帰率",
        threshold=DEFAULT_GUARDRAIL_THRESHOLDS["home_discharge_rate"]["threshold"],
        operator=">=",
        safe_threshold=5.0,
    )

    # ---------------------------------------------------------------
    # 5. ADL低下割合（手動入力 or not_available）
    # ---------------------------------------------------------------
    _append_manual_or_na(
        results, config,
        key="adl_decline",
        name="ADL低下割合",
        threshold=DEFAULT_GUARDRAIL_THRESHOLDS["adl_decline"]["threshold"],
        operator="<",
        safe_threshold=1.0,
    )

    # ---------------------------------------------------------------
    # 6. 重症度・医療看護必要度I（手動入力 or not_available）
    # ---------------------------------------------------------------
    _append_manual_or_na(
        results, config,
        key="nursing_necessity_i",
        name="重症度・医療看護必要度I",
        threshold=DEFAULT_GUARDRAIL_THRESHOLDS["nursing_necessity_i"]["threshold"],
        operator=">=",
        safe_threshold=3.0,
    )

    return results


def calculate_los_headroom(
    daily_df,
    config: Optional[dict] = None,
) -> dict:
    """LOS余力（C群コントロールで最も重要な指標）を詳細に計算する。

    Args:
        daily_df: 日次ベッドコントロールデータ（DataFrame）。None可。
        config: 設定辞書。以下のキーを参照する:
            - age_85_ratio (float): 85歳以上患者割合（デフォルト0.25）
            - c_group_count (int): 現在のC群患者数（既知の場合）
            - window_days (int): rolling window 日数（デフォルト90）

    Returns:
        LOS余力の詳細情報を表す dict:
            current_los (float): 現在のrolling LOS
            los_limit (float): 基準上限
            headroom_days (float): 余力（日数）= limit - current
            headroom_patient_days (float): 余力をpatient-daysに変換（概算）
            can_extend_c_group (bool): C群延長が制度的に可能か
            max_extend_days_per_patient (float or None): 1患者あたり最大延長可能日数
            data_source (str): "measured" / "proxy" / "not_available"
    """
    config = config or {}
    age_85_ratio = config.get("age_85_ratio", 0.25)
    window_days = config.get("window_days", 90)
    c_group_count = config.get("c_group_count", None)
    los_limit = calculate_los_limit(age_85_ratio)

    los_result = calculate_rolling_los(daily_df, window_days=window_days) if daily_df is not None else None

    if los_result is None:
        return {
            "current_los": None,
            "los_limit": los_limit,
            "headroom_days": None,
            "headroom_patient_days": None,
            "can_extend_c_group": False,
            "max_extend_days_per_patient": None,
            "data_source": "not_available",
        }

    current_los = (
        los_result.get("rolling_los_ex_short3")
        or los_result.get("rolling_los")
    )

    if current_los is None:
        return {
            "current_los": None,
            "los_limit": los_limit,
            "headroom_days": None,
            "headroom_patient_days": None,
            "can_extend_c_group": False,
            "max_extend_days_per_patient": None,
            "data_source": "not_available",
        }

    headroom_days = los_limit - current_los

    # headroom_patient_days の概算
    # N ≈ (admissions + discharges) / 2 を使う
    total_adm = los_result.get("total_admissions", 0)
    total_dis = los_result.get("total_discharges", 0)
    actual_days = los_result.get("actual_days", window_days)
    n_approx = (total_adm + total_dis) / 2.0

    if n_approx > 0 and actual_days > 0:
        headroom_patient_days = headroom_days * n_approx / actual_days
        data_source = "proxy"
    else:
        headroom_patient_days = None
        data_source = "not_available"

    # C群1患者あたりの最大延長可能日数
    max_extend = None
    if c_group_count is not None and c_group_count > 0 and headroom_patient_days is not None:
        max_extend = headroom_patient_days / c_group_count

    return {
        "current_los": round(current_los, 2),
        "los_limit": los_limit,
        "headroom_days": round(headroom_days, 2),
        "headroom_patient_days": round(headroom_patient_days, 2) if headroom_patient_days is not None else None,
        "can_extend_c_group": headroom_days > 0,
        "max_extend_days_per_patient": round(max_extend, 2) if max_extend is not None else None,
        "data_source": data_source,
    }


def format_guardrail_display(results: list[dict]) -> dict:
    """UI表示用のサマリーを作る。

    Args:
        results: calculate_guardrail_status() の戻り値

    Returns:
        表示用サマリー dict:
            overall_status (str): "safe" / "warning" / "danger"（最悪の指標に合わせる）
            auto_calculated (list): 自動計算された指標のリスト
            not_available (list): データ不足の指標のリスト
            danger_items (list): 逸脱している指標名
            warning_items (list): 警告レベルの指標名
    """
    if not results:
        return {
            "overall_status": "not_available",
            "auto_calculated": [],
            "not_available": [],
            "danger_items": [],
            "warning_items": [],
        }

    auto_calculated = []
    not_available = []
    danger_items = []
    warning_items = []

    for item in results:
        name = item.get("name", "")
        ds = item.get("data_source", "not_available")
        status = item.get("status", "not_available")

        if ds in ("measured", "proxy", "manual_input"):
            auto_calculated.append(name)
        else:
            not_available.append(name)

        if status == "danger":
            danger_items.append(name)
        elif status == "warning":
            warning_items.append(name)

    # overall_status: 最悪の指標に合わせる
    # not_available の重要指標がある場合は "incomplete" として安全と誤認させない
    if danger_items:
        overall_status = "danger"
    elif warning_items:
        overall_status = "warning"
    elif not_available:
        overall_status = "incomplete"
    else:
        overall_status = "safe"

    return {
        "overall_status": overall_status,
        "auto_calculated": auto_calculated,
        "not_available": not_available,
        "danger_items": danger_items,
        "warning_items": warning_items,
    }


# ---------------------------------------------------------------------------
# 内部ヘルパー関数
# ---------------------------------------------------------------------------


def _margin_to_status(margin: float, safe_threshold: float = 2.0) -> str:
    """margin値からステータスを判定する。

    Args:
        margin: 余力値（正=安全圏、負=逸脱）
        safe_threshold: この値以上なら "safe"

    Returns:
        "safe" / "warning" / "danger"
    """
    if margin <= 0:
        return "danger"
    elif margin < safe_threshold:
        return "warning"
    else:
        return "safe"


def _not_available_item(
    name: str,
    threshold: float,
    operator: str,
    description: str,
) -> dict:
    """data_source="not_available" の指標用テンプレートを返す。

    Args:
        name: 指標名
        threshold: 基準値
        operator: 比較演算子
        description: 説明文

    Returns:
        not_available状態の指標 dict
    """
    return {
        "name": name,
        "current_value": None,
        "threshold": threshold,
        "operator": operator,
        "margin": None,
        "status": "not_available",
        "data_source": "not_available",
        "description": description,
    }


def _append_manual_or_na(
    results: list[dict],
    config: dict,
    key: str,
    name: str,
    threshold: float,
    operator: str,
    safe_threshold: float = 2.0,
) -> None:
    """configに手動入力値があればそれを使い、なければnot_availableを追加する。

    Args:
        results: 結果リスト（この関数が直接追記する）
        config: 設定辞書
        key: configから取得するキー名
        name: 指標名
        threshold: 基準値
        operator: 比較演算子
        safe_threshold: safe判定の閾値
    """
    value = config.get(key)
    if value is not None:
        # operator に応じて margin を計算
        if operator in (">=",):
            margin = value - threshold
        elif operator in ("<=",):
            margin = threshold - value
        elif operator in ("<",):
            margin = threshold - value
        else:
            margin = 0.0

        status = _margin_to_status(margin, safe_threshold=safe_threshold)
        results.append({
            "name": name,
            "current_value": round(value, 1),
            "threshold": threshold,
            "operator": operator,
            "margin": round(margin, 1),
            "status": status,
            "data_source": "manual_input",
            "description": f"手動入力値: {value}",
        })
    else:
        results.append(_not_available_item(
            name, threshold, operator,
            f"データ未入力（{DEFAULT_GUARDRAIL_THRESHOLDS.get(key, {}).get('description', name)}）",
        ))
