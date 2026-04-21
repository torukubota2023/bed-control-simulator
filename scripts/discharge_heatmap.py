"""
退院予定ヒートマップ計算モジュール

多職種退院調整カンファで「今後の退院予定の日別分布」を一目で見るための
データを作る。業務集中の回避と、週末空床による稼働率低下の回避を目的とする。

設計方針（副院長決定 2026-04-21）:
- 表示期間: 基本 14 日先、連休があれば連休末まで（最大 21 日）
- 表示値: **全退院件数** をメインに、うち C 群（LOS ≥ 15 日）件数を小字併記
- 色判定: 全退院件数の閾値（業務集中・稼働率の観点）
  - 0 件: ⚪ 灰（空白、稼働率リスク）
  - 1-3 件: 🟢 緑（適正、平均域）
  - 4 件: 🟡 橙（注意、平均+1σ）
  - 5 件以上: 🔴 赤（集中、平均+2σ）
- クリックで該当日の C 群退院患者 ID をハイライト（Block C で該当行を点灯）

本モジュールは pure function のみ提供。Streamlit 依存なし。
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

# C 群の閾値（在院日数）— c_group_candidates.py と整合
C_GROUP_LOS_THRESHOLD: int = 15

# 色判定閾値（全退院件数ベース）— 副院長決定 2026-04-21
SEVERITY_DANGER_COUNT: int = 5    # 5 件以上で 🔴 集中
SEVERITY_WARNING_COUNT: int = 4   # 4 件で 🟡 注意
SEVERITY_EMPTY_COUNT: int = 0     # 0 件で ⚪ 空白

# 期間
DEFAULT_DAYS_AHEAD: int = 14
MAX_DAYS_AHEAD_WITH_HOLIDAY: int = 21

_DOW_LABELS_JA: Tuple[str, ...] = ("月", "火", "水", "木", "金", "土", "日")


# ---------------------------------------------------------------------------
# 日付ヘルパー
# ---------------------------------------------------------------------------


def _parse_planned_date(
    planned_date_str: str, reference_date: date,
) -> Optional[date]:
    """SamplePatient の planned_date 文字列を date オブジェクトに変換する。

    想定フォーマット:
      - "4/24 (金)" / "4/24(金)" / "4/24"   → 月日のみ、年は reference_date から推測
      - "2026-04-24"                        → ISO
      - "5/7 (木)"                          → 跨月対応

    Args:
        planned_date_str: 退院予定日表示文字列
        reference_date: 基準日（今日）— 年推測・跨年対応用

    Returns:
        date or None（"未定" やパース失敗時）
    """
    if not planned_date_str or planned_date_str.strip() in ("", "未定", "-"):
        return None

    s = planned_date_str.strip()

    # ISO フォーマット (YYYY-MM-DD) 優先
    iso_match = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if iso_match:
        try:
            return date(int(iso_match.group(1)), int(iso_match.group(2)),
                        int(iso_match.group(3)))
        except ValueError:
            return None

    # M/D (曜日) フォーマット
    md_match = re.match(r"^(\d{1,2})/(\d{1,2})", s)
    if md_match:
        month = int(md_match.group(1))
        day = int(md_match.group(2))
        # 年は reference_date の年。ただし月が reference より大幅に小さければ翌年扱い
        year = reference_date.year
        if month < reference_date.month - 3:
            year += 1
        try:
            return date(year, month, day)
        except ValueError:
            return None

    return None


# ---------------------------------------------------------------------------
# 期間判定
# ---------------------------------------------------------------------------


def compute_period_end(
    today: date,
    days_ahead: int = DEFAULT_DAYS_AHEAD,
    holiday_start: Optional[date] = None,
    holiday_end: Optional[date] = None,
    max_days_ahead: int = MAX_DAYS_AHEAD_WITH_HOLIDAY,
) -> Tuple[date, bool]:
    """ヒートマップ期間の末尾日を決定する。

    基本は today + days_ahead、ただし次の連休が期間内に始まり終了が
    max_days_ahead 以内ならば連休末まで延長する。

    Args:
        today: 基準日
        days_ahead: デフォルト表示日数
        holiday_start: 次の連休の開始日（あれば）
        holiday_end: 次の連休の終了日（あれば）
        max_days_ahead: 連休延長時の最大日数

    Returns:
        (末尾日, 延長されたか) のタプル
    """
    base_end = today + timedelta(days=days_ahead)
    max_end = today + timedelta(days=max_days_ahead)

    if holiday_start is None or holiday_end is None:
        return base_end, False

    # 連休が基本期間より後にある場合は影響なし
    if holiday_start > base_end:
        return base_end, False

    # 連休末が基本期間内に収まるなら延長不要（期間を縮めない）
    if holiday_end <= base_end:
        return base_end, False

    # 連休末が base_end を超えるが max_end 以内なら連休末まで延長
    if holiday_end <= max_end:
        return holiday_end, True

    # max_end を超える連休の場合は max_end で clamp
    return max_end, True


# ---------------------------------------------------------------------------
# severity 判定
# ---------------------------------------------------------------------------


def classify_cell_severity(total_discharges: int) -> str:
    """1 日の全退院件数から severity を判定する。

    Returns:
        "empty" / "ok" / "warn" / "danger"
    """
    if total_discharges <= 0:
        return "empty"
    if total_discharges >= SEVERITY_DANGER_COUNT:
        return "danger"
    if total_discharges >= SEVERITY_WARNING_COUNT:
        return "warn"
    return "ok"


# ---------------------------------------------------------------------------
# メイン計算
# ---------------------------------------------------------------------------


def compute_discharge_heatmap_from_patients(
    patients: List[Any],
    today: date,
    days_ahead: int = DEFAULT_DAYS_AHEAD,
    holiday_start: Optional[date] = None,
    holiday_end: Optional[date] = None,
    c_group_los_threshold: int = C_GROUP_LOS_THRESHOLD,
) -> Dict[str, Any]:
    """SamplePatient 相当のリストから退院ヒートマップを計算する。

    各患者は以下の属性を持つ想定:
      - patient_id: str
      - day_count: int  (現在の在院日数)
      - planned_date: str  ("M/D (曜日)" or "未定" or "")
      - doctor_surname: str  (ハイライト時の表示用)
      - status_key: str (optional)

    Args:
        patients: SamplePatient オブジェクトまたは同等の構造を持つリスト
        today: 基準日
        days_ahead: 表示日数
        holiday_start, holiday_end: 次の連休の期間（延長用）
        c_group_los_threshold: C 群判定の閾値（LOS ≥ N）

    Returns:
        {
            "cells": [
                {
                    "date": "2026-04-24",
                    "dow": 4,
                    "dow_label": "金",
                    "is_weekend": False,
                    "is_holiday": False,
                    "total": 4,
                    "c_group": 2,
                    "severity": "warn",
                    "patient_ids": ["a1b2", "c3d4", ...],
                    "c_group_patient_ids": ["a1b2", "c3d4"],
                    "c_group_patient_names": ["高橋", "田中"],
                },
                ...
            ],
            "period_start": "2026-04-22",
            "period_end": "2026-05-03",
            "total_days": 12,
            "extended_for_holiday": True,
            "grand_total": 28,
            "grand_c_group": 12,
            "concentrated_days": [{"date": "2026-05-01", "total": 5}, ...],
            "empty_days": [{"date": "2026-05-02", "dow_label": "土"}, ...],
        }
    """
    period_start = today + timedelta(days=1)
    period_end, extended = compute_period_end(
        today, days_ahead=days_ahead,
        holiday_start=holiday_start, holiday_end=holiday_end,
    )

    # 各日のセルを初期化
    cells_by_date: Dict[date, Dict[str, Any]] = {}
    d = period_start
    while d <= period_end:
        is_holiday = (
            holiday_start is not None and holiday_end is not None
            and holiday_start <= d <= holiday_end
        )
        cells_by_date[d] = {
            "date": d.isoformat(),
            "dow": d.weekday(),
            "dow_label": _DOW_LABELS_JA[d.weekday()],
            "is_weekend": d.weekday() >= 5,
            "is_holiday": is_holiday,
            "total": 0,
            "c_group": 0,
            "severity": "empty",
            "patient_ids": [],
            "c_group_patient_ids": [],
            "c_group_patient_names": [],
        }
        d += timedelta(days=1)

    # 患者をループしてセルに振り分け
    for p in patients:
        planned_str = getattr(p, "planned_date", "") or ""
        planned_dt = _parse_planned_date(planned_str, today)
        if planned_dt is None:
            continue
        if planned_dt < period_start or planned_dt > period_end:
            continue
        cell = cells_by_date[planned_dt]
        pid = getattr(p, "patient_id", "")
        day_count = int(getattr(p, "day_count", 0) or 0)
        doctor_surname = getattr(p, "doctor_surname", "") or ""

        # 退院時の予測 LOS = 現在の day_count + (planned_dt - today).days
        projected_los = day_count + (planned_dt - today).days
        is_c_group = projected_los >= c_group_los_threshold

        cell["total"] += 1
        cell["patient_ids"].append(pid)
        if is_c_group:
            cell["c_group"] += 1
            cell["c_group_patient_ids"].append(pid)
            if doctor_surname:
                cell["c_group_patient_names"].append(doctor_surname)

    # severity 判定 + セル ソート
    cells: List[Dict[str, Any]] = []
    for d_key in sorted(cells_by_date.keys()):
        cell = cells_by_date[d_key]
        cell["severity"] = classify_cell_severity(cell["total"])
        cells.append(cell)

    # サマリー
    grand_total = sum(c["total"] for c in cells)
    grand_c_group = sum(c["c_group"] for c in cells)
    concentrated_days = [
        {"date": c["date"], "dow_label": c["dow_label"], "total": c["total"],
         "c_group": c["c_group"]}
        for c in cells if c["severity"] == "danger"
    ]
    warning_days = [
        {"date": c["date"], "dow_label": c["dow_label"], "total": c["total"],
         "c_group": c["c_group"]}
        for c in cells if c["severity"] == "warn"
    ]
    empty_days = [
        {"date": c["date"], "dow_label": c["dow_label"],
         "is_weekend": c["is_weekend"]}
        for c in cells if c["severity"] == "empty"
    ]

    return {
        "cells": cells,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "total_days": len(cells),
        "extended_for_holiday": extended,
        "grand_total": grand_total,
        "grand_c_group": grand_c_group,
        "concentrated_days": concentrated_days,
        "warning_days": warning_days,
        "empty_days": empty_days,
    }
