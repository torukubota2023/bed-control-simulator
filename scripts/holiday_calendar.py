"""
連休カレンダーモジュール

多職種退院調整・連休対策カンファ資料画面で用いる「大型連休」検出ロジック。

**大型連休の定義**
- 土曜・日曜・日本の祝日（jpholiday 判定）が **連続する 3 日以上** のブロック
- 通常の土日 2 連休は対象外
- 祝日振替により 4 日以上に拡張された週末はすべて大型連休扱い

**代表名の付与規則**
- 期間内に「昭和の日」「憲法記念日」「みどりの日」「こどもの日」のいずれかを含む
  → ``GW``
- 期間内に 8/11〜8/16 の日付を含む（「山の日」前後を含む夏季の連続休業）
  → ``お盆``
- 期間の開始または終了が 12/28〜1/5 の範囲にかかる
  → ``年末年始``
- それ以外は期間内で最初に現れる祝日名（土日のみの連休なら「3連休」）

Public API
----------
- :func:`find_next_long_holiday`
- :func:`days_until_next_long_holiday`
- :func:`is_in_long_holiday`
- :func:`get_holiday_mode_banner`
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

try:
    import jpholiday  # type: ignore
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "jpholiday が見つかりません。`pip install jpholiday` を実行してください。"
    ) from exc


# 大型連休検出の既定閾値（3 連休以上）
DEFAULT_MIN_DAYS: int = 3

# 先読みする最大日数（2 年超の先の連休は探さない）
_MAX_LOOKAHEAD_DAYS: int = 400

# severity 判定閾値（日数）
_SEVERITY_INFO_THRESHOLD: int = 15   # 15 日以上で info
_SEVERITY_URGENT_THRESHOLD: int = 7  # 7 日以内で urgent（8-14 日は warning）


def _is_closed_day(d: date) -> bool:
    """``d`` が土日または日本の祝日なら True。

    Parameters
    ----------
    d : date
        判定対象日

    Returns
    -------
    bool
        土日祝なら True。平日なら False。
    """
    # weekday(): Monday=0 ... Sunday=6
    if d.weekday() >= 5:  # Saturday=5, Sunday=6
        return True
    return bool(jpholiday.is_holiday(d))


def _block_start(d: date) -> date:
    """``d`` を含む休業日ブロックの開始日を返す。

    ``d`` が休業日でない場合は ``d`` 自身を返す。
    """
    start = d
    while _is_closed_day(start - timedelta(days=1)):
        start -= timedelta(days=1)
    return start


def _block_end(d: date) -> date:
    """``d`` を含む休業日ブロックの終了日を返す。

    ``d`` が休業日でない場合は ``d`` 自身を返す。
    """
    end = d
    while _is_closed_day(end + timedelta(days=1)):
        end += timedelta(days=1)
    return end


def _assign_holiday_name(start: date, end: date) -> str:
    """期間の代表名を返す。

    判定の優先順位:
      1. GW（昭和の日／憲法記念日／みどりの日／こどもの日のいずれかを含む）
      2. お盆（8/11〜8/16 の日付を含む）
      3. 年末年始（開始・終了が 12/28〜1/5 にかかる）
      4. 期間内で最初に出てくる祝日名
      5. 該当なしなら「N連休」

    Parameters
    ----------
    start, end : date
        連休の開始日・終了日（両端含む）
    """
    gw_names = {"昭和の日", "憲法記念日", "みどりの日", "こどもの日"}
    first_holiday_name: Optional[str] = None

    cur = start
    while cur <= end:
        name = jpholiday.is_holiday_name(cur)
        if name:
            if name in gw_names:
                return "GW"
            if first_holiday_name is None:
                first_holiday_name = name
        # お盆（8/11〜8/16）
        if cur.month == 8 and 11 <= cur.day <= 16:
            return "お盆"
        cur += timedelta(days=1)

    # 年末年始: 12/28〜翌 1/5 に触れる
    def _in_year_end(d: date) -> bool:
        return (d.month == 12 and d.day >= 28) or (d.month == 1 and d.day <= 5)

    if _in_year_end(start) or _in_year_end(end):
        return "年末年始"

    if first_holiday_name:
        return first_holiday_name

    days = (end - start).days + 1
    return f"{days}連休"


def find_next_long_holiday(
    reference_date: date, min_days: int = DEFAULT_MIN_DAYS,
) -> Optional[dict]:
    """``reference_date`` 以降の最初の大型連休を返す。

    ``reference_date`` 当日が大型連休中なら、その連休を返す。

    Parameters
    ----------
    reference_date : date
        基準日。
    min_days : int, default ``DEFAULT_MIN_DAYS`` (=3)
        大型連休とみなす連続日数の下限。

    Returns
    -------
    dict or None
        ``{"start": date, "end": date, "days": int, "name": str}`` 形式。
        先読み範囲内に大型連休がなければ ``None``。

    Notes
    -----
    - 先読みは最大 ``_MAX_LOOKAHEAD_DAYS`` 日。
    """
    if reference_date is None:
        return None

    cur = reference_date
    limit = reference_date + timedelta(days=_MAX_LOOKAHEAD_DAYS)

    while cur <= limit:
        if _is_closed_day(cur):
            block_start = _block_start(cur)
            block_end = _block_end(cur)
            days = (block_end - block_start).days + 1
            if days >= min_days and block_end >= reference_date:
                return {
                    "start": block_start,
                    "end": block_end,
                    "days": days,
                    "name": _assign_holiday_name(block_start, block_end),
                }
            # このブロックは条件を満たさないので次の日に飛ぶ
            cur = block_end + timedelta(days=1)
        else:
            cur += timedelta(days=1)

    return None


def days_until_next_long_holiday(
    reference_date: date, min_days: int = DEFAULT_MIN_DAYS,
) -> Optional[int]:
    """次の大型連休の **開始日** までの日数を返す。

    Parameters
    ----------
    reference_date : date
        基準日。
    min_days : int, default ``DEFAULT_MIN_DAYS``
        大型連休の下限日数。

    Returns
    -------
    int or None
        ``start - reference_date`` の日数（連休中・当日開始なら 0 以下）。
        連休が見つからなければ ``None``。
    """
    holiday = find_next_long_holiday(reference_date, min_days=min_days)
    if holiday is None:
        return None
    return (holiday["start"] - reference_date).days


def is_in_long_holiday(
    reference_date: date, min_days: int = DEFAULT_MIN_DAYS,
) -> bool:
    """``reference_date`` 自体が大型連休中か判定する。

    Parameters
    ----------
    reference_date : date
        判定対象日。
    min_days : int, default ``DEFAULT_MIN_DAYS``
        大型連休の下限日数。

    Returns
    -------
    bool
        連休中なら True。
    """
    if reference_date is None or not _is_closed_day(reference_date):
        return False
    block_start = _block_start(reference_date)
    block_end = _block_end(reference_date)
    return (block_end - block_start).days + 1 >= min_days


def _classify_severity(days_remaining: Optional[int]) -> str:
    """残日数から severity ラベルを返す。

    - ``None`` または負値 → ``"none"``
    - 15 日以上 → ``"info"``
    - 8〜14 日 → ``"warning"``
    - 7 日以内（0 含む） → ``"urgent"``
    """
    if days_remaining is None or days_remaining < 0:
        return "none"
    if days_remaining >= _SEVERITY_INFO_THRESHOLD:
        return "info"
    if days_remaining >= _SEVERITY_URGENT_THRESHOLD + 1:
        # 8 日以上 14 日以下
        return "warning"
    # 0〜7 日
    return "urgent"


def get_holiday_mode_banner(reference_date: date) -> dict:
    """カンファ画面ヘッダー用の表示情報を返す。

    Parameters
    ----------
    reference_date : date
        基準日。

    Returns
    -------
    dict
        次のキーを持つ辞書:

        - ``days_remaining`` (int or None): 次の大型連休開始までの日数。
          連休中は 0、先読み範囲に連休がなければ ``None``。
        - ``severity`` (str): ``"info"`` / ``"warning"`` / ``"urgent"`` / ``"none"``。
        - ``holiday_name`` (str or None): 代表名（"GW" 等）。
        - ``holiday_start`` (date or None): 開始日。
        - ``holiday_end`` (date or None): 終了日。
        - ``banner_text`` (str): 例 ``"GW まで残 12日"``。連休中は
          ``"GW 期間中（残り N 日）"``。
    """
    if reference_date is None:
        return {
            "days_remaining": None,
            "severity": "none",
            "holiday_name": None,
            "holiday_start": None,
            "holiday_end": None,
            "banner_text": "大型連休の予定はありません",
        }

    holiday = find_next_long_holiday(reference_date)
    if holiday is None:
        return {
            "days_remaining": None,
            "severity": "none",
            "holiday_name": None,
            "holiday_start": None,
            "holiday_end": None,
            "banner_text": "大型連休の予定はありません",
        }

    start: date = holiday["start"]
    end: date = holiday["end"]
    name: str = holiday["name"]
    days_remaining = (start - reference_date).days

    # 連休中 (start <= reference_date <= end)
    if start <= reference_date <= end:
        remaining_in_holiday = (end - reference_date).days + 1
        return {
            "days_remaining": 0,
            "severity": "urgent",
            "holiday_name": name,
            "holiday_start": start,
            "holiday_end": end,
            "banner_text": f"{name} 期間中（残り {remaining_in_holiday}日）",
        }

    severity = _classify_severity(days_remaining)
    return {
        "days_remaining": days_remaining,
        "severity": severity,
        "holiday_name": name,
        "holiday_start": start,
        "holiday_end": end,
        "banner_text": f"{name} まで残 {days_remaining}日",
    }
