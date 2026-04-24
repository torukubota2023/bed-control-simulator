"""退院集中リスクの事前警告ロジック（案 α, 2026-04-24 副院長指示）.

カンファ前に「今後 N 日間で混雑リスクの高い日 TOP 3」を検出する純粋関数。
Streamlit に依存しない。

背景:
    副院長の要望で、木曜カンファの前日（水曜夜）までに「この日は既に
    N 名確定で、あと M 枠しかない」を自動ハイライトしたい。見落とし
    防止 + カンファでの議論ポイントを絞る効果がある。

使い方:
    >>> from crowding_alert import detect_crowding_risk_days
    >>> risks = detect_crowding_risk_days(
    ...     plans=load_all_plans(),
    ...     ward_map={"a1b2": "5F", ...},
    ...     today=date(2026, 4, 24),
    ...     days_ahead=7,
    ... )
    >>> risks[0]  # 最もリスクの高い日
    {
        "date": date(2026, 4, 30),
        "ward": "6F",
        "scheduled": 6,
        "slot": 5,
        "excess": 1,
        "risk_level": "overflow",
        "message": "...",
    }

判定ルール:
    - overflow: 退院予定 > 枠（既に超過している or 1 名追加で超過）
    - full: 退院予定 = 枠（あと 1 名でも超過）
    - tight: 退院予定 >= 枠の 80%（残り 1-2 枠）
    - それ以外は「余裕」なので抽出されない
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Set


def _get_slot(target_date: date, jp_holidays: Optional[Set[date]] = None) -> int:
    """指定日の基本枠を返す（平日 5 / 日祝 2）."""
    if jp_holidays and target_date in jp_holidays:
        return 2
    if target_date.weekday() == 6:
        return 2
    return 5


def _count_discharge_plans_for_date(
    plans: Dict[str, Dict[str, Any]],
    ward_map: Dict[str, str],
    target_ward: str,
    target_date: date,
) -> int:
    """指定日・病棟の退院予定総数（scheduled + confirmed）を返す."""
    iso = target_date.isoformat()
    count = 0
    for uuid, plan in plans.items():
        if ward_map.get(uuid) != target_ward:
            continue
        if plan.get("scheduled_date") != iso:
            continue
        count += 1
    return count


def detect_crowding_risk_days(
    plans: Dict[str, Dict[str, Any]],
    ward_map: Dict[str, str],
    today: date,
    days_ahead: int = 7,
    jp_holidays: Optional[Set[date]] = None,
    wards: Optional[List[str]] = None,
    max_results: int = 3,
) -> List[Dict[str, Any]]:
    """今後 N 日間で混雑リスクの高い日 TOP N を抽出.

    Args:
        plans: discharge_plan_store.load_all_plans() の戻り値
        ward_map: UUID → 病棟名の map
        today: 基準日（これ以降を検査）
        days_ahead: 検査する日数（デフォルト 7 日）
        jp_holidays: 祝日セット（None なら空）
        wards: 対象病棟（None なら "5F", "6F"）
        max_results: 返す件数（デフォルト 3）

    Returns:
        リスクの高い順の dict リスト。各 dict は:
        {
            "date": date,
            "ward": str,
            "scheduled": int,
            "slot": int,
            "excess": int,  # 負なら余裕
            "risk_level": "overflow" | "full" | "tight",
            "message": str,  # 副院長向けメッセージ
        }
    """
    if wards is None:
        wards = ["5F", "6F"]
    if jp_holidays is None:
        jp_holidays = set()

    risks: List[Dict[str, Any]] = []
    for i in range(days_ahead + 1):  # today を含めて N+1 日
        d = today + timedelta(days=i)
        slot = _get_slot(d, jp_holidays)
        for ward in wards:
            scheduled = _count_discharge_plans_for_date(
                plans, ward_map, ward, d
            )
            excess = scheduled - slot
            if scheduled > slot:
                risk = "overflow"
            elif scheduled == slot:
                risk = "full"
            elif slot > 0 and scheduled >= slot * 0.8:
                risk = "tight"
            else:
                continue  # 余裕があるので抽出しない

            msg = _build_message(d, ward, scheduled, slot, risk)
            risks.append({
                "date": d,
                "ward": ward,
                "scheduled": scheduled,
                "slot": slot,
                "excess": excess,
                "risk_level": risk,
                "message": msg,
            })

    # リスクの高い順: overflow > full > tight、同じなら excess が大きい順、日付が近い順
    risk_order = {"overflow": 0, "full": 1, "tight": 2}
    risks.sort(key=lambda r: (
        risk_order[r["risk_level"]],
        -r["excess"],
        r["date"],
    ))
    return risks[:max_results]


def _build_message(
    d: date, ward: str, scheduled: int, slot: int, risk: str,
) -> str:
    """副院長向けの警告メッセージを組み立てる."""
    dow_ja = ["月", "火", "水", "木", "金", "土", "日"][d.weekday()]
    date_str = f"{d.month}/{d.day} ({dow_ja})"
    if risk == "overflow":
        return (
            f"🚨 {date_str} {ward}: 既に {scheduled} 名予定、"
            f"枠 {slot} を {scheduled - slot} 名超過 → 別日への分散が必要"
        )
    if risk == "full":
        return (
            f"🔴 {date_str} {ward}: {scheduled} 名予定で満杯、"
            f"あと 1 名入れると超過 → 追加は慎重に"
        )
    # tight
    remaining = slot - scheduled
    return (
        f"🟡 {date_str} {ward}: 既に {scheduled} 名予定、"
        f"残 {remaining} 枠のみ → 新規追加は別日を優先検討"
    )


def summarize_risks(risks: List[Dict[str, Any]]) -> Dict[str, int]:
    """リスクのサマリー（overflow/full/tight の件数）."""
    counts = {"overflow": 0, "full": 0, "tight": 0}
    for r in risks:
        level = r.get("risk_level", "")
        if level in counts:
            counts[level] += 1
    return counts


__all__ = [
    "detect_crowding_risk_days",
    "summarize_risks",
]
