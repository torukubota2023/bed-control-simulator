"""
結論カード（今日の一手）生成モジュール — ダッシュボード用アクション推奨

病棟運営における複数KPI（救急搬送後患者割合・施設基準チェック・稼働率・
LOS余力・C群調整余地）を優先順位に従い評価し、「今日の一手」として
1枚の結論カードを生成する pure function モジュール。

優先順位（上ほど優先）:
    1. 制度リスク（救急搬送後患者割合 15% 未達・LOS上限超過リスク）
    2. 稼働率下振れ（月間稼働率 90% 未達見込み）
    3. 翌診療日朝受入余力不足
    4. LOS余力低下
    5. C群調整余地
    6. 正常運用

用語:
    - C群（15日目以降）は院内運用ラベルであり、制度上の公式区分ではない
    - 推計値はすべて proxy であり、実績とは乖離する可能性がある

Streamlit に依存しない。すべての関数は dict / list を返す。
外部ライブラリへの依存なし（標準ライブラリのみ）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

_LEVELS = {
    "critical": {"color": "red", "emoji": "🔴"},
    "warning": {"color": "yellow", "emoji": "🟡"},
    "info": {"color": "blue", "emoji": "🔵"},
    "success": {"color": "green", "emoji": "🟢"},
}

_EMERGENCY_THRESHOLD_PCT: float = 15.0
_MIN_EMERGENCY_SLOTS: int = 3
_LOS_HEADROOM_WARNING_DAYS: float = 2.0
_DEFAULT_TARGET_OCCUPANCY: float = 0.90


# ---------------------------------------------------------------------------
# 内部ヘルパー
# ---------------------------------------------------------------------------


def _safe_get(d: Optional[dict], *keys: str, default: Any = None) -> Any:
    """ネストされた dict から安全に値を取得する。"""
    if d is None:
        return default
    current = d
    for k in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(k)
        if current is None:
            return default
    return current


def _check_emergency_risk(emergency_summary: Optional[dict]) -> Optional[dict]:
    """救急搬送後患者割合の制度リスクを評価する。

    Returns:
        リスク検出時は {"level", "title", "actions", "priority_source", "details"} を返す。
        リスクなしの場合は None。
    """
    if emergency_summary is None:
        return None

    overall = _safe_get(emergency_summary, "overall_status", default="")
    alerts = _safe_get(emergency_summary, "alerts", default=[])

    # 各病棟の状況を確認
    danger_wards: list[str] = []
    ward_details: dict[str, dict] = {}

    for ward in ("5F", "6F"):
        ward_data = _safe_get(emergency_summary, ward)
        if ward_data is None:
            continue

        # operational（短手3除外）があれば優先、なければ official
        mode_data = _safe_get(ward_data, "dual_ratio", "operational") or _safe_get(ward_data, "dual_ratio", "official")
        if mode_data is None:
            continue

        ratio_pct = _safe_get(mode_data, "ratio_pct", default=0.0)
        additional_needed = _safe_get(ward_data, "additional", "additional_needed", default=0)

        ward_details[ward] = {
            "ratio_pct": ratio_pct,
            "additional_needed": additional_needed,
        }

        if overall == "danger" or additional_needed > 0:
            danger_wards.append(ward)

    if not danger_wards:
        # danger でなくても warning の場合がある
        if overall == "warning":
            actions = ["👉 救急搬送受入れを優先的に確保する"]
            for ward, info in ward_details.items():
                needed = info.get("additional_needed", 0)
                if needed > 0:
                    actions.append(
                        f"👉 {ward}: あと{needed}件の救急入院が必要（推計）"
                    )
            if len(actions) < 2:
                actions.append("👉 救急搬送比率の推移を注視する")

            return {
                "level": "warning",
                "title": "救急搬送後患者割合が注意域 — 受入れ強化を検討",
                "actions": actions[:3],
                "priority_source": "救急搬送後患者割合（注意域）",
                "details": {"overall_status": overall, "wards": ward_details},
            }
        return None

    # danger の場合
    actions = ["👉 救急搬送の受入れを最優先にする"]
    for ward in danger_wards:
        needed = ward_details[ward].get("additional_needed", 0)
        ratio = ward_details[ward].get("ratio_pct", 0.0)
        if needed > 0:
            actions.append(
                f"👉 {ward}: 現在{ratio:.1f}% — あと{needed}件の救急入院が必要（推計）"
            )
    if len(actions) < 2:
        actions.append("👉 紹介・予定入院より救急受入れを優先する")

    return {
        "level": "critical",
        "title": "救急搬送後患者割合が危険域 — 直ちに受入れ最優先モードへ",
        "actions": actions[:3],
        "priority_source": "救急搬送後患者割合 15% 未達リスク",
        "details": {"overall_status": overall, "danger_wards": danger_wards, "wards": ward_details},
    }


def _check_guardrail_risk(guardrail_status: Optional[list]) -> Optional[dict]:
    """施設基準チェック（LOS上限等）のリスクを評価する。"""
    if not guardrail_status:
        return None

    danger_items: list[dict] = []
    warning_items: list[dict] = []

    for item in guardrail_status:
        status = _safe_get(item, "status", default="")
        if status == "danger":
            danger_items.append(item)
        elif status == "warning":
            warning_items.append(item)

    if danger_items:
        actions = ["👉 制度基準の逸脱リスクを直ちに確認する"]
        for item in danger_items[:2]:
            name = _safe_get(item, "name", default="制度指標")
            actions.append(f"👉 {name}: 基準逸脱の恐れ — 是正措置を検討")
        return {
            "level": "critical",
            "title": "施設基準チェック違反リスク — 是正措置が必要",
            "actions": actions[:3],
            "priority_source": "施設基準チェック（danger）",
            "details": {"danger_count": len(danger_items), "items": danger_items},
        }

    if warning_items:
        actions = ["👉 制度指標の推移を注視する"]
        for item in warning_items[:2]:
            name = _safe_get(item, "name", default="制度指標")
            actions.append(f"👉 {name}: 注意域に接近中")
        return {
            "level": "warning",
            "title": "施設基準チェック注意域 — 推移を監視",
            "actions": actions[:3],
            "priority_source": "施設基準チェック（warning）",
            "details": {"warning_count": len(warning_items), "items": warning_items},
        }

    return None


def _check_occupancy_risk(
    occupancy_rate: Optional[float],
    monthly_kpi: Optional[dict],
    target_occupancy: float,
) -> Optional[dict]:
    """稼働率の下振れリスクを評価する。"""
    current_rate = occupancy_rate
    projected_rate = _safe_get(monthly_kpi, "projected_occupancy")

    # 判定する値がない場合はスキップ
    if current_rate is None and projected_rate is None:
        return None

    # projected があればそちらを優先（月末着地予測）
    check_rate = projected_rate if projected_rate is not None else current_rate
    target_pct = target_occupancy * 100

    if check_rate is not None and check_rate < target_occupancy:
        gap_pct = (target_occupancy - check_rate) * 100
        rate_pct = check_rate * 100
        label = "月末着地予測" if projected_rate is not None else "現在"

        actions = [
            f"👉 {label}稼働率 {rate_pct:.1f}% — 目標 {target_pct:.0f}% まであと {gap_pct:.1f}pt",
            "👉 入院受入れの積極化を検討する",
        ]
        if gap_pct > 5:
            actions.append("👉 C群の退院後ろ倒しも選択肢に（LOS余力を確認の上）")

        return {
            "level": "warning",
            "title": f"稼働率が目標を下回る見込み（{label} {rate_pct:.1f}%）",
            "actions": actions[:3],
            "priority_source": "稼働率下振れ",
            "details": {
                "current_rate": current_rate,
                "projected_rate": projected_rate,
                "target": target_occupancy,
                "gap_pct": gap_pct,
            },
        }

    return None


def _check_morning_capacity(morning_capacity: Optional[dict]) -> Optional[dict]:
    """翌診療日朝の救急受入余力を評価する。"""
    if morning_capacity is None:
        return None

    slots = _safe_get(morning_capacity, "estimated_emergency_slots", default=None)
    if slots is None:
        return None

    if slots < _MIN_EMERGENCY_SLOTS:
        actions = [
            f"👉 翌朝の救急受入枠が推計{slots}床 — 余力不足の恐れ",
            "👉 本日中に退院可能な患者の退院調整を急ぐ",
        ]
        expected_discharges = _safe_get(morning_capacity, "expected_discharges", default=None)
        if expected_discharges is not None:
            actions.append(f"👉 退院予定 {expected_discharges}名の確実な実行を確認")

        return {
            "level": "warning",
            "title": f"翌朝の救急受入余力が不足（推計{slots}床）",
            "actions": actions[:3],
            "priority_source": "翌診療日朝受入余力不足",
            "details": {"estimated_emergency_slots": slots, "morning_capacity": morning_capacity},
        }

    return None


def _check_los_headroom(los_headroom: Optional[dict]) -> Optional[dict]:
    """LOS余力の低下を評価する。"""
    if los_headroom is None:
        return None

    headroom_days = _safe_get(los_headroom, "headroom_days", default=None)
    if headroom_days is None:
        return None

    if headroom_days < _LOS_HEADROOM_WARNING_DAYS:
        current_los = _safe_get(los_headroom, "current_los", default=None)
        limit_los = _safe_get(los_headroom, "limit_los", default=None)

        actions = [f"👉 LOS（在院日数）余力が残り{headroom_days:.1f}日 — C群の退院前倒しを検討"]
        if current_los is not None and limit_los is not None:
            actions.append(
                f"👉 現在の平均在院日数 {current_los:.1f}日（上限 {limit_los:.1f}日）"
            )
        actions.append("👉 長期入院患者の退院調整を加速する")

        return {
            "level": "warning",
            "title": f"平均在院日数の余力が低下（残り{headroom_days:.1f}日）",
            "actions": actions[:3],
            "priority_source": "LOS（在院日数）余力低下",
            "details": {"headroom_days": headroom_days, "los_headroom": los_headroom},
        }

    return None


def _check_c_group_opportunity(
    c_adjustment_capacity: Optional[dict],
    occupancy_rate: Optional[float],
    target_occupancy: float,
) -> Optional[dict]:
    """C群調整余地（稼働率補填の機会）を評価する。"""
    if c_adjustment_capacity is None:
        return None

    can_delay = _safe_get(c_adjustment_capacity, "can_delay", default=False)
    absorbable_beds = _safe_get(c_adjustment_capacity, "absorbable_beds", default=0)

    if not can_delay or absorbable_beds <= 0:
        return None

    # 稼働率が低い場合のみ C群延長を示唆
    occupancy_low = (
        occupancy_rate is not None and occupancy_rate < target_occupancy
    )
    if not occupancy_low:
        return None

    contribution = _safe_get(c_adjustment_capacity, "daily_contribution", default=28900)

    actions = [
        f"👉 C群退院の後ろ倒しで最大{absorbable_beds}床の空床を補填可能（proxy推計）",
        f"👉 C群運営貢献額: {contribution:,.0f}円/日/床（proxy）",
        "👉 LOS（在院日数）余力・救急搬送比率を確認の上で判断する",
    ]

    return {
        "level": "info",
        "title": "C群の退院調整で空床補填の余地あり（院内運用ラベル・proxy推計）",
        "actions": actions[:3],
        "priority_source": "C群調整余地",
        "details": {
            "can_delay": can_delay,
            "absorbable_beds": absorbable_beds,
            "daily_contribution": contribution,
            "note": "C群は院内運用ラベル。推計値はすべてproxy。",
        },
    }


def _build_success_card() -> dict:
    """正常運用時のカードを生成する。"""
    return {
        "level": "success",
        "title": "各指標は正常範囲 — 通常運用を継続",
        "actions": [
            "👉 定時の入退院調整を着実に実行する",
            "👉 翌日の退院予定を再確認する",
        ],
        "priority_source": "正常運用",
        "details": {},
    }


def _collect_cross_ward_alerts(
    emergency_summary: Optional[dict],
    selected_ward: Optional[str],
) -> list:
    """選択していない他病棟の重要アラートを収集する。"""
    if not selected_ward or not emergency_summary:
        return []

    alerts: list = []
    for ward in ("5F", "6F"):
        if ward == selected_ward:
            continue
        ward_data = _safe_get(emergency_summary, ward)
        if ward_data is None:
            continue

        # operational（短手3除外）があれば優先、なければ official
        mode_data = _safe_get(ward_data, "dual_ratio", "operational") or _safe_get(
            ward_data, "dual_ratio", "official"
        )
        if mode_data is None:
            continue

        ratio_pct = _safe_get(mode_data, "ratio_pct", default=0.0)
        status = _safe_get(mode_data, "status", default="")
        additional = _safe_get(
            ward_data, "additional", "additional_needed", default=0
        )

        if status == "red" or additional > 0:
            alerts.append({
                "ward": ward,
                "type": "emergency_ratio",
                "level": "critical",
                "message": f"{ward}の救急搬送比率が危険域（{ratio_pct:.1f}%）— あと{additional}件必要",
            })
        elif status == "yellow":
            alerts.append({
                "ward": ward,
                "type": "emergency_ratio",
                "level": "warning",
                "message": f"{ward}の救急搬送比率が注意域（{ratio_pct:.1f}%）",
            })

    return alerts


def _attach_level_meta(card: dict) -> dict:
    """level に基づいて color / emoji を付与する。"""
    level = card.get("level", "info")
    meta = _LEVELS.get(level, _LEVELS["info"])
    card["color"] = meta["color"]
    card["emoji"] = meta["emoji"]
    return card


# ---------------------------------------------------------------------------
# 公開関数 1: generate_action_card
# ---------------------------------------------------------------------------


def generate_action_card(
    emergency_summary: Optional[dict] = None,
    guardrail_status: Optional[list] = None,
    los_headroom: Optional[dict] = None,
    morning_capacity: Optional[dict] = None,
    monthly_kpi: Optional[dict] = None,
    c_group_summary: Optional[dict] = None,
    c_adjustment_capacity: Optional[dict] = None,
    demand_classification: Optional[dict] = None,
    occupancy_rate: Optional[float] = None,
    target_occupancy: float = _DEFAULT_TARGET_OCCUPANCY,
    selected_ward: Optional[str] = None,
) -> dict:
    """優先順位に従い、最も重要なアクション推奨カードを1枚生成する。

    すべての引数は Optional であり、データ未取得の項目は評価をスキップする。

    Args:
        emergency_summary: get_ward_emergency_summary() の戻り値
        guardrail_status: 施設基準チェックエンジンの判定結果リスト
        los_headroom: LOS余力情報 {"headroom_days", "current_los", "limit_los"}
        morning_capacity: 翌診療日朝の受入余力 {"estimated_emergency_slots", ...}
        monthly_kpi: 月次KPI {"projected_occupancy", ...}
        c_group_summary: C群サマリー
        c_adjustment_capacity: C群調整余地 {"can_delay", "absorbable_beds", ...}
        demand_classification: 需要波モデルの分類結果
        occupancy_rate: 現在の稼働率（0.0-1.0）
        target_occupancy: 目標稼働率（デフォルト 0.90）

    Returns:
        dict:
            - "level": "critical" | "warning" | "info" | "success"
            - "color": "red" | "yellow" | "blue" | "green"
            - "emoji": str
            - "title": str（メインメッセージ、1行）
            - "actions": list[str]（2-3個のアクション項目、👉 プレフィクス付き）
            - "priority_source": str（このレベルのトリガー）
            - "details": dict（補足数値）
    """
    def _finalize(card: dict) -> dict:
        """level meta を付与し、selected_ward があれば追加する。"""
        c = _attach_level_meta(card)
        if selected_ward:
            c["selected_ward"] = selected_ward
            c["cross_ward_alerts"] = _collect_cross_ward_alerts(
                emergency_summary, selected_ward
            )
        return c

    # 優先順位 1: 制度リスク（救急搬送後患者割合）
    result = _check_emergency_risk(emergency_summary)
    if result is not None and result["level"] == "critical":
        return _finalize(result)

    # 優先順位 1: 制度リスク（施設基準チェック）
    result_gr = _check_guardrail_risk(guardrail_status)
    if result_gr is not None and result_gr["level"] == "critical":
        return _finalize(result_gr)

    # 優先順位 2: 稼働率下振れ
    result_occ = _check_occupancy_risk(occupancy_rate, monthly_kpi, target_occupancy)
    if result_occ is not None:
        return _finalize(result_occ)

    # 優先順位 3: 翌診療日朝受入余力不足
    result_mc = _check_morning_capacity(morning_capacity)
    if result_mc is not None:
        return _finalize(result_mc)

    # 優先順位 4: LOS余力低下
    result_los = _check_los_headroom(los_headroom)
    if result_los is not None:
        return _finalize(result_los)

    # 優先順位 1 の warning（critical でないもの）も拾う
    if result is not None and result["level"] == "warning":
        return _finalize(result)
    if result_gr is not None and result_gr["level"] == "warning":
        return _finalize(result_gr)

    # 優先順位 5: C群調整余地
    result_c = _check_c_group_opportunity(
        c_adjustment_capacity, occupancy_rate, target_occupancy
    )
    if result_c is not None:
        return _finalize(result_c)

    # 優先順位 6: 正常運用
    return _finalize(_build_success_card())


# ---------------------------------------------------------------------------
# 公開関数 2: generate_kpi_priority_list
# ---------------------------------------------------------------------------


def generate_kpi_priority_list(
    emergency_summary: Optional[dict] = None,
    guardrail_status: Optional[list] = None,
    los_headroom: Optional[dict] = None,
    morning_capacity: Optional[dict] = None,
    morning_capacity_5f: Optional[dict] = None,
    morning_capacity_6f: Optional[dict] = None,
    monthly_kpi: Optional[dict] = None,
    c_group_summary: Optional[dict] = None,
    c_adjustment_capacity: Optional[dict] = None,
    occupancy_rate: Optional[float] = None,
    target_occupancy: float = _DEFAULT_TARGET_OCCUPANCY,
) -> List[Dict[str, Any]]:
    """KPIを優先順位順に並べたリストを生成する。

    UI上でKPIを重要度順に表示するために使用する。

    Args:
        （generate_action_card と同一）

    Returns:
        list[dict]: 各要素は以下のキーを持つ:
            - "name": str（KPI名）
            - "value": str（表示用の値）
            - "status": "danger" | "warning" | "safe" | "unknown"
            - "rank": int（優先順位、1が最も重要）
            - "explanation": str（状況の説明）
    """
    items: List[Dict[str, Any]] = []
    rank = 0

    # --- 1. 救急搬送後患者割合 ---
    rank += 1
    if emergency_summary is not None:
        overall = _safe_get(emergency_summary, "overall_status", default="unknown")
        status_map = {"danger": "danger", "warning": "warning", "safe": "safe", "incomplete": "unknown"}
        status = status_map.get(overall, "unknown")

        # 各病棟の割合を表示用に組み立て（operational優先、なければofficial）
        parts: list[str] = []
        _er_mode_used = "official"
        for ward in ("5F", "6F"):
            op_data = _safe_get(emergency_summary, ward, "dual_ratio", "operational")
            of_data = _safe_get(emergency_summary, ward, "dual_ratio", "official")
            mode_data = op_data or of_data
            if op_data is not None:
                _er_mode_used = "operational"
            if mode_data is not None:
                ratio = _safe_get(mode_data, "ratio_pct", default=0.0)
                parts.append(f"{ward}: {ratio:.1f}%")

        value = " / ".join(parts) if parts else "データなし"
        _mode_label = "院内運用用" if _er_mode_used == "operational" else "届出確認用"
        explanation = (
            f"施設基準: 各病棟 {_EMERGENCY_THRESHOLD_PCT:.0f}% 以上が必要（{_mode_label}）"
            if status != "unknown"
            else "データ不足のため判定不能"
        )

        items.append({
            "name": f"救急搬送比率（{_mode_label}）",
            "value": value,
            "status": status,
            "rank": rank,
            "explanation": explanation,
        })
    else:
        items.append({
            "name": "救急搬送後患者割合",
            "value": "未取得",
            "status": "unknown",
            "rank": rank,
            "explanation": "データが入力されていません",
        })

    # --- 2. 施設基準チェック ---
    rank += 1
    if guardrail_status:
        danger_count = sum(1 for g in guardrail_status if _safe_get(g, "status") == "danger")
        warning_count = sum(1 for g in guardrail_status if _safe_get(g, "status") == "warning")
        safe_count = len(guardrail_status) - danger_count - warning_count

        if danger_count > 0:
            status = "danger"
            value = f"逸脱リスク {danger_count}件"
        elif warning_count > 0:
            status = "warning"
            value = f"注意 {warning_count}件"
        else:
            status = "safe"
            value = f"全{safe_count}項目 正常"

        items.append({
            "name": "施設基準チェック",
            "value": value,
            "status": status,
            "rank": rank,
            "explanation": "2026年改定基準に基づく施設基準充足状況",
        })
    else:
        items.append({
            "name": "施設基準チェック",
            "value": "未取得",
            "status": "unknown",
            "rank": rank,
            "explanation": "データが入力されていません",
        })

    # --- 3. 稼働率 ---
    rank += 1
    if occupancy_rate is not None:
        rate_pct = occupancy_rate * 100
        target_pct = target_occupancy * 100
        if occupancy_rate >= target_occupancy:
            status = "safe"
        elif occupancy_rate >= target_occupancy - 0.05:
            status = "warning"
        else:
            status = "danger"

        projected = _safe_get(monthly_kpi, "projected_occupancy")
        value = f"{rate_pct:.1f}%"
        if projected is not None:
            value += f"（月末予測: {projected * 100:.1f}%）"

        items.append({
            "name": "病床稼働率",
            "value": value,
            "status": status,
            "rank": rank,
            "explanation": f"目標: {target_pct:.0f}%（稼働率1% ≈ 年間約1,200万円）",
        })
    else:
        items.append({
            "name": "病床稼働率",
            "value": "未取得",
            "status": "unknown",
            "rank": rank,
            "explanation": "データが入力されていません",
        })

    # --- 4. 翌朝受入余力 ---
    rank += 1
    if morning_capacity is not None:
        slots = _safe_get(morning_capacity, "estimated_emergency_slots", default=None)
        if slots is not None:
            # 病棟別データがあれば病棟別表示に切替
            if morning_capacity_5f is not None and morning_capacity_6f is not None:
                slots_5f = _safe_get(morning_capacity_5f, "estimated_emergency_slots", default=0)
                slots_6f = _safe_get(morning_capacity_6f, "estimated_emergency_slots", default=0)
                value = f"5F: {slots_5f}床 / 6F: {slots_6f}床"
                min_slots = min(slots_5f, slots_6f)
                if min_slots >= 5:
                    status = "safe"
                elif min_slots >= _MIN_EMERGENCY_SLOTS:
                    status = "warning"
                else:
                    status = "danger"
                explanation = f"各病棟で最低{_MIN_EMERGENCY_SLOTS}床の余力を推奨（全体: {slots}床）"
            else:
                status = "safe" if slots >= _MIN_EMERGENCY_SLOTS else "warning"
                value = f"推計 {slots}床"
                explanation = f"救急受入に最低{_MIN_EMERGENCY_SLOTS}床の余力を推奨"
        else:
            status = "unknown"
            value = "算出不能"
            explanation = "必要データが不足しています"

        items.append({
            "name": "翌朝受入余力",
            "value": value,
            "status": status,
            "rank": rank,
            "explanation": explanation,
        })
    else:
        items.append({
            "name": "翌朝受入余力",
            "value": "未取得",
            "status": "unknown",
            "rank": rank,
            "explanation": "データが入力されていません",
        })

    # --- 5. 平均在院日数余力 ---
    rank += 1
    if los_headroom is not None:
        headroom = _safe_get(los_headroom, "headroom_days", default=None)
        if headroom is not None:
            if headroom < _LOS_HEADROOM_WARNING_DAYS:
                status = "warning"
            else:
                status = "safe"
            value = f"余力 {headroom:.1f}日"

            current = _safe_get(los_headroom, "current_los")
            limit = _safe_get(los_headroom, "limit_los")
            if current is not None and limit is not None:
                explanation = f"現在 {current:.1f}日 / 上限 {limit:.1f}日"
            else:
                explanation = "rolling 3ヶ月平均在院日数の制度上限との差分"
        else:
            status = "unknown"
            value = "算出不能"
            explanation = "必要データが不足しています"

        items.append({
            "name": "平均在院日数余力",
            "value": value,
            "status": status,
            "rank": rank,
            "explanation": explanation,
        })
    else:
        items.append({
            "name": "平均在院日数余力",
            "value": "未取得",
            "status": "unknown",
            "rank": rank,
            "explanation": "データが入力されていません",
        })

    # --- 6. C群調整余地 ---
    rank += 1
    if c_adjustment_capacity is not None:
        can_delay = _safe_get(c_adjustment_capacity, "can_delay", default=False)
        absorbable = _safe_get(c_adjustment_capacity, "absorbable_beds", default=0)

        if can_delay and absorbable > 0:
            status = "safe"
            value = f"最大 {absorbable}床補填可能（proxy推計）"
            explanation = "C群（院内運用ラベル）退院調整による空床補填の余地"
        else:
            status = "safe"
            value = "調整余地なし"
            explanation = "現在C群で吸収可能な空床はありません（proxy推計）"

        items.append({
            "name": "C群調整余地",
            "value": value,
            "status": status,
            "rank": rank,
            "explanation": explanation,
        })
    elif c_group_summary is not None:
        items.append({
            "name": "C群調整余地",
            "value": "調整余地の算出データなし",
            "status": "unknown",
            "rank": rank,
            "explanation": "C群サマリーはあるが調整余地の算出データが不足（proxy推計）",
        })
    else:
        items.append({
            "name": "C群調整余地",
            "value": "未取得",
            "status": "unknown",
            "rank": rank,
            "explanation": "データが入力されていません",
        })

    return items


# ---------------------------------------------------------------------------
# 公開関数 3: generate_tradeoff_assessment
# ---------------------------------------------------------------------------


def generate_tradeoff_assessment(
    c_adjustment_capacity: Optional[dict] = None,
    emergency_summary: Optional[dict] = None,
    morning_capacity: Optional[dict] = None,
    los_headroom: Optional[dict] = None,
) -> dict:
    """C群の「留める」vs「退院させる」のトレードオフを評価する。

    C群（15日目以降）は院内運用ラベルであり、制度上の公式区分ではない。
    推計値はすべて proxy であり、実績とは乖離する可能性がある。

    Args:
        c_adjustment_capacity: C群調整余地の情報
        emergency_summary: 救急搬送後患者割合のサマリー
        morning_capacity: 翌診療日朝の受入余力
        los_headroom: LOS余力情報

    Returns:
        dict:
            - "recommendation": "keep" | "release" | "neutral"
            - "reasoning": str
            - "impacts": list[dict] with keys "metric", "effect", "direction"
            - "emergency_priority": bool
    """
    impacts: List[Dict[str, str]] = []
    emergency_priority = False
    reasoning_parts: list[str] = []

    # --- 救急搬送比率のリスク評価 ---
    emergency_at_risk = False
    if emergency_summary is not None:
        overall = _safe_get(emergency_summary, "overall_status", default="")
        if overall in ("danger", "warning"):
            emergency_at_risk = True
            emergency_priority = True
            impacts.append({
                "metric": "救急搬送後患者割合",
                "effect": "C群退院 → 空床確保 → 救急受入枠増加",
                "direction": "release有利",
            })
            reasoning_parts.append(
                "救急搬送後患者割合が未達リスクのため、C群を退院させて救急受入枠を確保すべき"
            )

    # --- LOS余力の評価 ---
    los_tight = False
    if los_headroom is not None:
        headroom = _safe_get(los_headroom, "headroom_days", default=None)
        if headroom is not None:
            if headroom < _LOS_HEADROOM_WARNING_DAYS:
                los_tight = True
                impacts.append({
                    "metric": "平均在院日数",
                    "effect": f"LOS余力 {headroom:.1f}日 — C群延長はLOS上限超過リスク",
                    "direction": "release有利",
                })
                reasoning_parts.append(
                    f"LOS余力が{headroom:.1f}日と逼迫しており、C群を長く留めるとLOS上限を超過するリスクがある"
                )
            else:
                impacts.append({
                    "metric": "平均在院日数",
                    "effect": f"LOS余力 {headroom:.1f}日 — C群延長の余地あり",
                    "direction": "keep可能",
                })

    # --- 翌朝受入余力の評価 ---
    if morning_capacity is not None:
        slots = _safe_get(morning_capacity, "estimated_emergency_slots", default=None)
        if slots is not None:
            if slots < _MIN_EMERGENCY_SLOTS:
                impacts.append({
                    "metric": "翌朝受入余力",
                    "effect": f"推計{slots}床 — C群退院で余力確保を",
                    "direction": "release有利",
                })
                reasoning_parts.append(
                    f"翌朝の救急受入余力が{slots}床と不足しており、C群退院で空床を確保したい"
                )
            else:
                impacts.append({
                    "metric": "翌朝受入余力",
                    "effect": f"推計{slots}床 — 十分な余力あり",
                    "direction": "keep可能",
                })

    # --- C群調整余地の評価 ---
    if c_adjustment_capacity is not None:
        can_delay = _safe_get(c_adjustment_capacity, "can_delay", default=False)
        absorbable = _safe_get(c_adjustment_capacity, "absorbable_beds", default=0)
        contribution = _safe_get(c_adjustment_capacity, "daily_contribution", default=28900)

        if can_delay and absorbable > 0:
            impacts.append({
                "metric": "C群運営貢献（proxy推計）",
                "effect": f"留めれば{absorbable}床 × {contribution:,.0f}円/日の運営貢献",
                "direction": "keep有利",
            })
            if not emergency_at_risk and not los_tight:
                reasoning_parts.append(
                    f"C群を留めることで最大{absorbable}床分の運営貢献が得られる（proxy推計）"
                )

    # --- 総合判定 ---
    if emergency_at_risk:
        recommendation = "release"
        if not reasoning_parts:
            reasoning_parts.append("救急搬送後患者割合の確保が最優先のため、C群退院を推奨する")
    elif los_tight:
        recommendation = "release"
        if not reasoning_parts:
            reasoning_parts.append("LOS余力が逼迫しているため、C群退院を推奨する")
    elif (
        c_adjustment_capacity is not None
        and _safe_get(c_adjustment_capacity, "can_delay", default=False)
        and _safe_get(c_adjustment_capacity, "absorbable_beds", default=0) > 0
    ):
        # 救急も LOS も安全で、C群で補填できる場合
        recommendation = "keep"
        if not reasoning_parts:
            reasoning_parts.append(
                "救急比率・LOS余力ともに安全圏のため、C群を留めて稼働率を維持できる（proxy推計）"
            )
    else:
        recommendation = "neutral"
        if not reasoning_parts:
            reasoning_parts.append(
                "現在のデータからは明確な方向性は出ない — 個別患者の状況に応じて判断を"
            )

    # impacts が空の場合のフォールバック
    if not impacts:
        impacts.append({
            "metric": "総合",
            "effect": "評価に必要なデータが不足しています",
            "direction": "判定不能",
        })

    return {
        "recommendation": recommendation,
        "reasoning": "。".join(reasoning_parts),
        "impacts": impacts,
        "emergency_priority": emergency_priority,
    }
