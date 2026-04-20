"""来週末の空床予測モジュール (weekend_forecast.py) のテスト。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import List

import pandas as pd
import pytest

from scripts.weekend_forecast import (
    CI80_SIGMA_MULTIPLIER,
    DEFAULT_DISCHARGE_WINDOW_WEEKS,
    DEFAULT_EMERGENCY_WINDOW_WEEKS,
    EMERGENCY_ROUTES,
    forecast_next_weekend,
    next_week_weekend,
)


# ---------------------------------------------------------------------------
# next_week_weekend の日付判定
# ---------------------------------------------------------------------------


class TestNextWeekWeekend:
    """来週の金土日判定が各曜日で正しく動作することを確認。"""

    def test_today_is_monday(self):
        """月曜の基準日なら、来週月曜 +4/+5/+6 の金土日を返す。"""
        fri, sat, sun = next_week_weekend(date(2026, 4, 20))  # 月
        assert fri == date(2026, 5, 1)   # 11 日後 (来週金)
        assert sat == date(2026, 5, 2)
        assert sun == date(2026, 5, 3)

    def test_today_is_thursday(self):
        """カンファ想定日 (木曜) — 来週金土日は +8/+9/+10。"""
        fri, sat, sun = next_week_weekend(date(2026, 4, 23))  # 木
        assert fri == date(2026, 5, 1)
        assert sat == date(2026, 5, 2)
        assert sun == date(2026, 5, 3)

    def test_today_is_friday(self):
        """金曜なら、今日の金曜ではなく +7 日後の来週金曜を返す。"""
        fri, sat, sun = next_week_weekend(date(2026, 4, 24))  # 金
        assert fri == date(2026, 5, 1)  # 翌週の金
        assert sat == date(2026, 5, 2)
        assert sun == date(2026, 5, 3)

    def test_today_is_sunday(self):
        """日曜の基準日なら、翌日月曜 +4/+5/+6 の金土日を返す。"""
        fri, sat, sun = next_week_weekend(date(2026, 4, 26))  # 日
        assert fri == date(2026, 5, 1)
        assert sat == date(2026, 5, 2)
        assert sun == date(2026, 5, 3)

    def test_sequence_is_consecutive(self):
        """金土日は必ず連続 3 日になる。"""
        for base in [date(2026, 4, 20) + timedelta(days=i) for i in range(14)]:
            fri, sat, sun = next_week_weekend(base)
            assert (sat - fri).days == 1
            assert (sun - sat).days == 1
            assert fri.weekday() == 4
            assert sat.weekday() == 5
            assert sun.weekday() == 6


# ---------------------------------------------------------------------------
# forecast_next_weekend の振る舞い
# ---------------------------------------------------------------------------


def _make_daily_history(
    start: date, end: date, ward: str,
    daily_admissions: float, daily_discharges: float, total_patients: int,
) -> pd.DataFrame:
    """安定した日次データを生成する (平均テスト用)。"""
    rows = []
    d = start
    while d <= end:
        rows.append({
            "date": d.isoformat(),
            "ward": ward,
            "total_patients": total_patients,
            "new_admissions": daily_admissions,
            "discharges": daily_discharges,
        })
        d += timedelta(days=1)
    return pd.DataFrame(rows)


def _make_detail_df(records: List[dict]) -> pd.DataFrame:
    """入退院詳細のダミー DataFrame を作る。"""
    df = pd.DataFrame(records)
    # 必須列
    for col in ("date", "ward", "event_type", "route"):
        if col not in df.columns:
            df[col] = None
    return df


class TestForecastNextWeekend:
    """メインの forecast 関数の統合テスト。"""

    def test_returns_three_rows(self):
        """来週金土日の 3 行が返る。"""
        today = date(2026, 4, 23)  # 木
        history = _make_daily_history(
            date(2026, 1, 1), today, "5F",
            daily_admissions=3.0, daily_discharges=3.0, total_patients=42,
        )
        result = forecast_next_weekend(history, ward="5F", today=today, ward_beds=47)
        assert len(result["rows"]) == 3
        assert [r["day"] for r in result["rows"]] == ["金", "土", "日"]
        assert result["target_dates"] == [
            "2026-05-01", "2026-05-02", "2026-05-03",
        ]

    def test_vacancy_reflects_admissions_minus_discharges(self):
        """退院数 > 入院数 なら空床が増える方向にシフトする。"""
        today = date(2026, 4, 23)
        # 退院 4, 入院 2 の安定パターン → 毎日 +2 で空床増
        history = _make_daily_history(
            date(2026, 1, 1), today, "5F",
            daily_admissions=2.0, daily_discharges=4.0, total_patients=40,
        )
        result = forecast_next_weekend(history, ward="5F", today=today, ward_beds=47)
        # 現在空床 = 47 - 40 = 7, 8日先までに +2×8 = 16 増の予測 → >= 7
        assert result["rows"][0]["vacancy"] >= 7
        # 退院 < 入院 なら逆方向
        history2 = _make_daily_history(
            date(2026, 1, 1), today, "5F",
            daily_admissions=4.0, daily_discharges=2.0, total_patients=40,
        )
        result2 = forecast_next_weekend(history2, ward="5F", today=today, ward_beds=47)
        # 現在空床 7 から毎日 -2 → 0 になる
        assert result2["rows"][0]["vacancy"] < result["rows"][0]["vacancy"]

    def test_scheduled_discharge_overrides_prediction(self):
        """detail_df に入力された退院予定は予測より優先される。"""
        today = date(2026, 4, 23)
        history = _make_daily_history(
            date(2026, 1, 1), today, "5F",
            daily_admissions=3.0, daily_discharges=3.0, total_patients=40,
        )
        # 来週金 (2026-05-01) に 10 名の退院予定を入力
        detail = _make_detail_df([
            {"date": "2026-05-01", "ward": "5F",
             "event_type": "discharge", "route": None}
            for _ in range(10)
        ])
        result_no_detail = forecast_next_weekend(
            history, detail_df=None, ward="5F", today=today, ward_beds=47,
        )
        result_with_detail = forecast_next_weekend(
            history, detail_df=detail, ward="5F", today=today, ward_beds=47,
        )
        # 金曜の空床は入力があるほうがずっと多くなる (退院 10 名分前倒し反映)
        assert result_with_detail["rows"][0]["vacancy"] > result_no_detail["rows"][0]["vacancy"]
        # 入力カバレッジ: 1/3 = 33.3%
        assert abs(result_with_detail["coverage_pct"] - 33.3) < 1.0
        # 金曜の discharges_input は 10 として記録される
        assert result_with_detail["rows"][0]["discharges_input"] == 10

    def test_coverage_pct_when_all_days_have_input(self):
        """3 日すべてに退院予定入力があればカバレッジ 100%。"""
        today = date(2026, 4, 23)
        history = _make_daily_history(
            date(2026, 1, 1), today, "5F",
            daily_admissions=2.0, daily_discharges=2.0, total_patients=40,
        )
        detail = _make_detail_df([
            {"date": "2026-05-01", "ward": "5F", "event_type": "discharge", "route": None},
            {"date": "2026-05-02", "ward": "5F", "event_type": "discharge", "route": None},
            {"date": "2026-05-03", "ward": "5F", "event_type": "discharge", "route": None},
        ])
        result = forecast_next_weekend(history, detail_df=detail, ward="5F", today=today)
        assert result["coverage_pct"] == 100.0

    def test_coverage_pct_when_no_input(self):
        """入力が 0 件ならカバレッジ 0%。"""
        today = date(2026, 4, 23)
        history = _make_daily_history(
            date(2026, 1, 1), today, "5F",
            daily_admissions=2.0, daily_discharges=2.0, total_patients=40,
        )
        result = forecast_next_weekend(history, detail_df=None, ward="5F", today=today)
        assert result["coverage_pct"] == 0.0

    def test_er_margin_uses_emergency_routes_only(self):
        """救急余力は EMERGENCY_ROUTES (救急+下り搬送) のみで計算される。"""
        today = date(2026, 4, 23)
        history = _make_daily_history(
            date(2026, 1, 1), today, "5F",
            daily_admissions=2.0, daily_discharges=2.0, total_patients=42,
        )
        # 過去 12 週の金曜に 「救急」 3 件、「外来紹介」 99 件 (金曜ごと)
        detail_records = []
        for wk in range(12):
            past_fri = today - timedelta(days=today.weekday() + 3 + wk * 7)
            for _ in range(3):
                detail_records.append({
                    "date": past_fri.isoformat(), "ward": "5F",
                    "event_type": "admission", "route": "救急",
                })
            for _ in range(99):
                detail_records.append({
                    "date": past_fri.isoformat(), "ward": "5F",
                    "event_type": "admission", "route": "外来紹介",
                })
        detail = _make_detail_df(detail_records)
        result = forecast_next_weekend(
            history, detail_df=detail, ward="5F", today=today, ward_beds=47,
        )
        # 金曜の expected_emergency は救急 3 件のみ反映されるべき (外来紹介 99 件は無視)
        fri_row = result["rows"][0]
        assert 2.5 <= fri_row["expected_emergency"] <= 3.5, (
            f"expected ≒ 3.0, got {fri_row['expected_emergency']}"
        )

    def test_confidence_band_positive_when_variance_exists(self):
        """退院件数に揺らぎがあれば vacancy_high > vacancy > vacancy_low。"""
        today = date(2026, 4, 23)
        # 金曜だけ 2 / 5 / 2 / 5 と交互にばらつかせる
        rows = []
        d = date(2026, 1, 1)
        while d <= today:
            dow = d.weekday()
            dis = 3.0
            if dow == 4:  # 金
                dis = 2.0 if ((d - date(2026, 1, 2)).days // 7) % 2 == 0 else 5.0
            rows.append({
                "date": d.isoformat(), "ward": "5F",
                "total_patients": 42, "new_admissions": 3.0, "discharges": dis,
            })
            d += timedelta(days=1)
        history = pd.DataFrame(rows)
        result = forecast_next_weekend(history, ward="5F", today=today, ward_beds=47)
        fri_row = result["rows"][0]
        # 金曜の退院予測が大きくばらつくので CI がゼロでないはず
        assert fri_row["vacancy_high"] >= fri_row["vacancy"] >= fri_row["vacancy_low"]
        assert fri_row["vacancy_high"] > fri_row["vacancy_low"]

    def test_severity_levels(self):
        """er_margin の値に応じて severity が ok/warn/danger に分類される。"""
        today = date(2026, 4, 23)
        # ほぼ満床 & 救急需要が高い → danger
        history = _make_daily_history(
            date(2026, 1, 1), today, "5F",
            daily_admissions=5.0, daily_discharges=2.0, total_patients=46,
        )
        result = forecast_next_weekend(history, ward="5F", today=today, ward_beds=47)
        # 少なくとも 1 日は空床不足で severity が "danger" か "warn"
        severities = {r["severity"] for r in result["rows"]}
        assert "danger" in severities or "warn" in severities

    def test_empty_daily_df_returns_zeros(self):
        """daily_df が空でも落ちず、vacancy=0 で返る。"""
        today = date(2026, 4, 23)
        result = forecast_next_weekend(
            pd.DataFrame(), ward="5F", today=today, ward_beds=47,
        )
        assert len(result["rows"]) == 3
        assert all(r["vacancy"] == 0 for r in result["rows"])
        assert result["coverage_pct"] == 0.0
