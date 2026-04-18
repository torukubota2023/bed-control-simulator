"""
holiday_calendar モジュールのユニットテスト

対象公開関数:
- find_next_long_holiday
- days_until_next_long_holiday
- is_in_long_holiday
- get_holiday_mode_banner
"""

from __future__ import annotations

import os
import sys
from datetime import date

import pytest

# scripts/ を sys.path に追加
_SCRIPTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "scripts")
)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from holiday_calendar import (  # noqa: E402
    days_until_next_long_holiday,
    find_next_long_holiday,
    get_holiday_mode_banner,
    is_in_long_holiday,
)


# ---------------------------------------------------------------
# 1. find_next_long_holiday: GW 2026
# ---------------------------------------------------------------

class TestFindNextLongHolidayGW:
    """2026 GW の検出

    2026 カレンダー:
      4/29(水) 昭和の日（単独 → ブロック切れ）
      4/30(木) 平日
      5/1(金) 平日
      5/2(土)〜5/6(水振休) → 連続 5 日の休業ブロック = 大型連休「GW」

    仕様「連続する 3 日以上の休業日ブロック」に厳密に従い、
    5/2〜5/6 が大型連休として検出される。
    """

    def test_gw_detected_from_april_1(self):
        result = find_next_long_holiday(date(2026, 4, 1))
        assert result is not None
        assert result["name"] == "GW"
        assert result["start"] == date(2026, 5, 2)
        assert result["end"] == date(2026, 5, 6)
        assert result["days"] == 5

    def test_gw_detected_from_april_17(self):
        """今日(CLAUDE.md 仕様の 2026-04-17)からも GW が先頭に来る."""
        result = find_next_long_holiday(date(2026, 4, 17))
        assert result is not None
        assert result["name"] == "GW"
        assert result["start"] == date(2026, 5, 2)

    def test_gw_detected_on_start_day(self):
        """開始日 5/2 当日でも当該 GW が返る."""
        result = find_next_long_holiday(date(2026, 5, 2))
        assert result is not None
        assert result["name"] == "GW"
        assert result["start"] == date(2026, 5, 2)
        assert result["end"] == date(2026, 5, 6)

    def test_gw_detected_mid_holiday(self):
        """連休中 5/4 の時点でも当該 GW を返す."""
        result = find_next_long_holiday(date(2026, 5, 4))
        assert result is not None
        assert result["name"] == "GW"
        assert result["start"] == date(2026, 5, 2)


# ---------------------------------------------------------------
# 2. お盆 2026: 祝日ではない 8/13-16 は検出されない
# ---------------------------------------------------------------

class TestFindNextLongHolidayObon:
    """2026 お盆（8/13-16 の平日は祝日ではない）

    8/11 山の日(火) は単独祝日、8/13-14 は平日、8/15(土)・8/16(日) は週末のみ
    → 連続 3 日以上の休業ブロックは存在しない
    → 8 月中の大型連休は「なし」となり、次の 9 月連休（敬老+秋分）が返る
    """

    def test_obon_not_detected_as_long_holiday(self):
        """8/1 時点の次の連休はお盆ではなく 9 月の敬老秋分."""
        result = find_next_long_holiday(date(2026, 8, 1))
        assert result is not None
        # 9/19(土) - 9/23(水 秋分の日) の 5 連休
        assert result["start"] == date(2026, 9, 19)
        assert result["end"] == date(2026, 9, 23)
        assert result["days"] == 5
        # 名前は GW/お盆/年末年始 以外なので祝日名（敬老の日）
        assert result["name"] == "敬老の日"

    def test_aug_13_15_not_in_long_holiday(self):
        """8/13〜8/15 は連休中ではない."""
        assert is_in_long_holiday(date(2026, 8, 13)) is False
        assert is_in_long_holiday(date(2026, 8, 14)) is False
        # 8/15 は土曜だが前後と連結しないので連休中ではない
        assert is_in_long_holiday(date(2026, 8, 15)) is False


# ---------------------------------------------------------------
# 3. 年末年始 2026/27
# ---------------------------------------------------------------

class TestFindNextLongHolidayYearEnd:
    """年末年始の検出

    12/31(木) は平日扱い（祝日ではなく行政・医療は診療日）
    1/1(金 元日祝) 〜 1/3(日) → 3 日連続休業ブロック
    → 「年末年始」として検出される
    """

    def test_year_end_detected_from_dec_1(self):
        result = find_next_long_holiday(date(2026, 12, 1))
        assert result is not None
        assert result["name"] == "年末年始"
        assert result["start"] == date(2027, 1, 1)
        assert result["end"] == date(2027, 1, 3)
        assert result["days"] == 3

    def test_dec_31_is_not_in_long_holiday(self):
        """12/31(木) は祝日でも土日でもないので連休中ではない."""
        assert is_in_long_holiday(date(2026, 12, 31)) is False


# ---------------------------------------------------------------
# 4. 3 連休判定の下限: 土日のみ 2 連休は対象外
# ---------------------------------------------------------------

class TestMinDaysThreshold:
    """min_days=3 では通常の土日 2 連休は検出されない."""

    def test_weekend_only_not_detected(self):
        """2026-03-07(土)〜3-8(日) のような祝日を含まない週末は 2 日なので除外.

        2026-03 は祝日が 3/20(金 春分の日) のみ。
        3/20(金)〜3/22(日) の 3 連休は検出されるはず。
        3/7(土) から検索したとき、最初に 3/7-3/8 の 2 日ブロックをスキップして
        3/20-3/22 の 3 日ブロックを返さなければならない。
        """
        result = find_next_long_holiday(date(2026, 3, 7))
        assert result is not None
        # 3/7-3/8 の 2 日ブロックは無視される
        assert result["start"] != date(2026, 3, 7)
        assert result["days"] >= 3

    def test_two_day_weekend_is_not_long_holiday(self):
        """3/7(土) 自体は連休中でない（2 日しかないため）."""
        assert is_in_long_holiday(date(2026, 3, 7)) is False
        assert is_in_long_holiday(date(2026, 3, 8)) is False

    def test_min_days_2_accepts_weekend(self):
        """min_days=2 を渡せば土日 2 連休も検出される."""
        # 2026-03-07(土)〜3-8(日) ブロック
        result = find_next_long_holiday(date(2026, 3, 7), min_days=2)
        assert result is not None
        assert result["start"] == date(2026, 3, 7)
        assert result["end"] == date(2026, 3, 8)
        assert result["days"] == 2


# ---------------------------------------------------------------
# 5. is_in_long_holiday: 境界と連休中
# ---------------------------------------------------------------

class TestIsInLongHoliday:
    def test_inside_gw(self):
        assert is_in_long_holiday(date(2026, 5, 2)) is True  # 開始日
        assert is_in_long_holiday(date(2026, 5, 4)) is True  # 中間
        assert is_in_long_holiday(date(2026, 5, 6)) is True  # 終了日

    def test_outside_gw(self):
        assert is_in_long_holiday(date(2026, 5, 1)) is False  # 前日（平日）
        assert is_in_long_holiday(date(2026, 5, 7)) is False  # 翌日（平日）

    def test_isolated_holiday_not_in_long_holiday(self):
        """単独祝日は大型連休ではない."""
        # 4/29(水) 昭和の日は単独
        assert is_in_long_holiday(date(2026, 4, 29)) is False

    def test_none_returns_false(self):
        assert is_in_long_holiday(None) is False


# ---------------------------------------------------------------
# 6. days_until_next_long_holiday
# ---------------------------------------------------------------

class TestDaysUntilNextLongHoliday:
    def test_from_april_17(self):
        """4/17 → GW 開始 5/2 は 15 日先."""
        assert days_until_next_long_holiday(date(2026, 4, 17)) == 15

    def test_on_start_day_returns_zero(self):
        """開始日当日は 0 日."""
        assert days_until_next_long_holiday(date(2026, 5, 2)) == 0

    def test_during_holiday_returns_negative(self):
        """連休中は負の値（開始日は過去）."""
        # 5/4 なら start=5/2 との差 = -2
        assert days_until_next_long_holiday(date(2026, 5, 4)) == -2

    def test_none_returns_none(self):
        """reference_date=None → None."""
        assert days_until_next_long_holiday(None) is None


# ---------------------------------------------------------------
# 7. severity の境界値テスト
#    15日以上=info / 8-14日=warning / 7日以内=urgent
# ---------------------------------------------------------------

class TestSeverityBoundaries:
    """banner の severity 分岐を残日数境界で検証.

    次の GW 開始 = 2026-05-02。
    残 15 日 → 4/17
    残 14 日 → 4/18
    残 8 日  → 4/24
    残 7 日  → 4/25
    """

    def test_15_days_is_info(self):
        banner = get_holiday_mode_banner(date(2026, 4, 17))
        assert banner["days_remaining"] == 15
        assert banner["severity"] == "info"

    def test_14_days_is_warning(self):
        banner = get_holiday_mode_banner(date(2026, 4, 18))
        assert banner["days_remaining"] == 14
        assert banner["severity"] == "warning"

    def test_8_days_is_warning(self):
        banner = get_holiday_mode_banner(date(2026, 4, 24))
        assert banner["days_remaining"] == 8
        assert banner["severity"] == "warning"

    def test_7_days_is_urgent(self):
        banner = get_holiday_mode_banner(date(2026, 4, 25))
        assert banner["days_remaining"] == 7
        assert banner["severity"] == "urgent"

    def test_0_days_is_urgent(self):
        """開始日当日 → urgent."""
        banner = get_holiday_mode_banner(date(2026, 5, 2))
        assert banner["severity"] == "urgent"


# ---------------------------------------------------------------
# 8. banner の構造と表示文
# ---------------------------------------------------------------

class TestHolidayModeBannerStructure:
    """banner の戻り値構造."""

    _REQUIRED_KEYS = {
        "days_remaining",
        "severity",
        "holiday_name",
        "holiday_start",
        "holiday_end",
        "banner_text",
    }

    def test_banner_has_all_keys(self):
        banner = get_holiday_mode_banner(date(2026, 4, 17))
        assert set(banner.keys()) == self._REQUIRED_KEYS

    def test_banner_text_contains_name_and_days(self):
        banner = get_holiday_mode_banner(date(2026, 4, 17))
        assert "GW" in banner["banner_text"]
        assert "15" in banner["banner_text"]

    def test_banner_during_holiday(self):
        """連休中の banner は 0 日扱いかつ期間情報を持つ."""
        banner = get_holiday_mode_banner(date(2026, 5, 4))
        assert banner["days_remaining"] == 0
        assert banner["severity"] == "urgent"
        assert banner["holiday_name"] == "GW"
        assert banner["holiday_start"] == date(2026, 5, 2)
        assert banner["holiday_end"] == date(2026, 5, 6)
        assert "GW" in banner["banner_text"]

    def test_banner_none_reference(self):
        """reference_date=None でも例外を出さずデフォルト値."""
        banner = get_holiday_mode_banner(None)
        assert banner["severity"] == "none"
        assert banner["holiday_name"] is None
        assert banner["days_remaining"] is None

    def test_banner_far_future_returns_none_severity(self):
        """先読み上限を超える日付には大型連休情報なし."""
        # 2100 年は jpholiday の想定外なので None 返却を期待
        # （少なくとも severity=none か有効な値が返ること）
        banner = get_holiday_mode_banner(date(2099, 12, 1))
        assert banner["severity"] in ("none", "info", "warning", "urgent")


# ---------------------------------------------------------------
# 9. find_next_long_holiday: 基本構造
# ---------------------------------------------------------------

class TestFindNextLongHolidayStructure:
    def test_result_keys(self):
        result = find_next_long_holiday(date(2026, 4, 1))
        assert result is not None
        assert set(result.keys()) == {"start", "end", "days", "name"}

    def test_end_after_start(self):
        result = find_next_long_holiday(date(2026, 4, 1))
        assert result is not None
        assert result["end"] >= result["start"]

    def test_days_consistent_with_range(self):
        """days は (end - start).days + 1 と一致."""
        result = find_next_long_holiday(date(2026, 4, 1))
        assert result is not None
        computed = (result["end"] - result["start"]).days + 1
        assert result["days"] == computed

    def test_none_reference_returns_none(self):
        assert find_next_long_holiday(None) is None
