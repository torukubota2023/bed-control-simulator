"""退院枠ルールの単一ソース定数.

副院長判断（2026-04-23）の退院枠ルールを定数化した。この値は
``discharge_calendar_view`` / 枠超過判定 / 動的枠調整 / 日曜推奨バナー
の全てで参照される。変更する場合はここだけを編集すれば全画面に反映される。

---

確定仕様（2026-04-23）
-----------------------

**基本枠（1 病棟あたり）:**
- 月〜金: 5 名
- 土曜: 5 名（半ドンだが平日扱い）
- 日曜・祝日: 2 名（推奨対象、固定）

**超過ルール:**
- 平日/土曜で枠を超過 → 翌営業日（= 次の平日 or 土曜）の枠から超過分を引く
- 連続超過時の累積はしない（前日分のみ反映、その翌日は元の 5 枠に復帰）
- 日曜・祝日は固定 2 枠で、超過の繰り越し対象外（飛ばす）

**動的枠調整:**
- 稼働率 ≥ 95% または 空床 ≤ 3 → 退院枠 +1 名（翌営業日の枠を増やして稼働率を下げる）
- 稼働率 < 80% → 退院枠 -1 名（退院ペースを抑えて稼働率を維持）
- ※日曜・祝日の 2 枠は動的調整の対象外（固定）

**日曜推奨:**
- カレンダー UI で日曜マスの残枠を強調表示
- 月次 KPI「日曜退院実施数」を 📊 今日の運営 タブに出す

データ根拠
----------
- 2025-04 〜 2026-03 の 1965 件の入院データから、1 病棟あたり月退院数は 57-62 名
- 枠総量は典型月 140 枠/病棟/月 → 月 80 名でも充足率 57%（大幅余裕）
- 日曜退院は現状 0.3〜1.3 名/日 → 2 枠は「退院を封じない最低保証」として機能
"""

from __future__ import annotations

from datetime import date
from typing import Optional

# -----------------------------------------------------------------------------
# 基本枠
# -----------------------------------------------------------------------------

#: 月〜土曜の 1 病棟あたり退院枠（名/日）
WEEKDAY_SLOT: int = 5

#: 日曜・祝日の 1 病棟あたり退院枠（名/日、固定）
HOLIDAY_SLOT: int = 2

# -----------------------------------------------------------------------------
# 動的枠調整の閾値
# -----------------------------------------------------------------------------

#: 稼働率がこの値以上になったら退院枠を +1 する（空床確保のため）
DYNAMIC_EXPAND_OCCUPANCY_THRESHOLD: float = 0.95

#: 空床数がこの値以下になったら退院枠を +1 する（稼働率閾値と OR 条件）
DYNAMIC_EXPAND_VACANCY_THRESHOLD: int = 3

#: 稼働率がこの値未満になったら退院枠を -1 する（退院ペース抑制で稼働率維持）
DYNAMIC_CONTRACT_OCCUPANCY_THRESHOLD: float = 0.80

#: 動的調整で枠を増やす幅（名）
DYNAMIC_ADJUST_AMOUNT: int = 1

#: 動的調整の最大枠（上限、暴走防止）
DYNAMIC_MAX_SLOT: int = 8

#: 動的調整の最小枠（下限、退院停止防止）
DYNAMIC_MIN_SLOT: int = 3


# -----------------------------------------------------------------------------
# ヘルパー関数
# -----------------------------------------------------------------------------

def get_base_slot(target_date: date, is_holiday: bool = False) -> int:
    """指定日の基本退院枠（1 病棟あたり）を返す.

    Parameters
    ----------
    target_date : date
        対象日
    is_holiday : bool, default False
        祝日かどうか（日本の祝日判定は呼び出し側で実施）。
        日曜は weekday で判定するため、ここでは祝日のみフラグで渡す。

    Returns
    -------
    int
        基本枠の名数。日曜・祝日なら HOLIDAY_SLOT、それ以外は WEEKDAY_SLOT。
    """
    if is_holiday:
        return HOLIDAY_SLOT
    # weekday: 月=0 .. 日=6
    if target_date.weekday() == 6:  # 日曜
        return HOLIDAY_SLOT
    return WEEKDAY_SLOT


def is_holiday_slot_day(target_date: date, is_holiday: bool = False) -> bool:
    """その日が「休日枠（固定 2 枠・動的調整対象外）」の日か判定.

    Parameters
    ----------
    target_date : date
        対象日
    is_holiday : bool, default False
        祝日かどうか

    Returns
    -------
    bool
        日曜 or 祝日なら True。
    """
    return is_holiday or target_date.weekday() == 6


def calculate_effective_slot(
    target_date: date,
    previous_day_excess: int = 0,
    occupancy_rate: Optional[float] = None,
    vacancy_count: Optional[int] = None,
    is_holiday: bool = False,
) -> int:
    """その日の「実効枠」を計算する（基本枠 − 前日超過 ± 動的調整）.

    Parameters
    ----------
    target_date : date
        対象日
    previous_day_excess : int, default 0
        前日（前営業日）の枠超過分。正の値なら今日の枠を減らす。
    occupancy_rate : float, optional
        現在の稼働率（0.0〜1.0）。設定されている場合、動的調整を適用。
    vacancy_count : int, optional
        現在の空床数。動的調整の OR 条件として使う。
    is_holiday : bool, default False
        祝日かどうか

    Returns
    -------
    int
        実効枠（0 以下にはならず、最低 0 を返す）。
        日曜・祝日は HOLIDAY_SLOT を常に返す（超過・動的調整の影響を受けない）。

    Notes
    -----
    - 日曜・祝日は HOLIDAY_SLOT（2）固定で、何があっても変わらない（副院長指示）
    - 前日超過の繰り越しは「翌営業日 1 日のみ」（累積しない）
    - 動的調整は平日/土曜のみ、上限 DYNAMIC_MAX_SLOT、下限 DYNAMIC_MIN_SLOT
    """
    # 日曜・祝日は固定
    if is_holiday_slot_day(target_date, is_holiday):
        return HOLIDAY_SLOT

    base = WEEKDAY_SLOT
    effective = base - max(0, previous_day_excess)

    # 動的調整
    if occupancy_rate is not None:
        if occupancy_rate >= DYNAMIC_EXPAND_OCCUPANCY_THRESHOLD:
            effective += DYNAMIC_ADJUST_AMOUNT
        elif occupancy_rate < DYNAMIC_CONTRACT_OCCUPANCY_THRESHOLD:
            effective -= DYNAMIC_ADJUST_AMOUNT

    if vacancy_count is not None and vacancy_count <= DYNAMIC_EXPAND_VACANCY_THRESHOLD:
        # 稼働率と別条件で OR（空床逼迫時は拡張）
        if effective <= base:  # 既に稼働率で拡張済みなら二重適用しない
            effective += DYNAMIC_ADJUST_AMOUNT

    # 上限・下限でクランプ
    effective = max(DYNAMIC_MIN_SLOT, min(DYNAMIC_MAX_SLOT, effective))
    return max(0, effective)


__all__ = [
    "WEEKDAY_SLOT",
    "HOLIDAY_SLOT",
    "DYNAMIC_EXPAND_OCCUPANCY_THRESHOLD",
    "DYNAMIC_EXPAND_VACANCY_THRESHOLD",
    "DYNAMIC_CONTRACT_OCCUPANCY_THRESHOLD",
    "DYNAMIC_ADJUST_AMOUNT",
    "DYNAMIC_MAX_SLOT",
    "DYNAMIC_MIN_SLOT",
    "get_base_slot",
    "is_holiday_slot_day",
    "calculate_effective_slot",
]
