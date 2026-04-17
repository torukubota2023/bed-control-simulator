"""
holiday_strategy_view のユニットテスト

UI 描画は Streamlit 依存のためテスト対象外。以下の pure function を検証する:
- calculate_next_holiday_countdown(today)
- compute_dow_occupancy(daily_df, ...)
- _week_overall_classification(...)
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta

import pandas as pd
import pytest

# scripts/ を sys.path に追加
_SCRIPTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "scripts")
)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from views.holiday_strategy_view import (  # noqa: E402
    _HOLIDAY_PERIODS,
    CATEGORY_A,
    CATEGORY_B,
    CATEGORY_C,
    CATEGORY_UNKNOWN,
    _classify_booking_availability,
    _is_in_holiday_period,
    _is_post_holiday_week,
    _summarize_booking_counts,
    _week_overall_classification,
    calculate_next_holiday_countdown,
    classify_discharge_candidates,
    compute_dow_occupancy,
    forecast_daily_demand_for_period,
    summarize_categories,
)


# ---------------------------------------------------------------
# 1. calculate_next_holiday_countdown
# ---------------------------------------------------------------

class TestCalculateNextHolidayCountdown:
    """次の大型連休カウントダウン."""

    def test_2026_04_17_returns_gw_12_days(self):
        """2026-04-17 時点で次の連休は GW、あと 12 日."""
        result = calculate_next_holiday_countdown(date(2026, 4, 17))
        assert result is not None
        assert result.name == "GW2026"
        assert result.days_until_start == 12
        assert result.start_date == date(2026, 4, 29)
        assert result.duration_days == 7  # 4/29 〜 5/5 = 7日間
        assert result.is_ongoing is False
        # 退院調整開始推奨日 = 開始 3 週間前 = 4/8
        assert result.discharge_planning_start_date == date(2026, 4, 8)
        # 4/17 は 4/8 より後 → passed=True
        assert result.discharge_planning_passed is True

    def test_2026_05_10_returns_obon_95_days(self):
        """2026-05-10 時点で次はお盆、あと 95 日."""
        result = calculate_next_holiday_countdown(date(2026, 5, 10))
        assert result is not None
        assert result.name == "お盆2026"
        # 5/10 → 8/13 = 95 日
        assert result.days_until_start == 95

    def test_during_gw_is_ongoing(self):
        """GW 開催中は is_ongoing=True."""
        result = calculate_next_holiday_countdown(date(2026, 4, 30))
        assert result is not None
        assert result.name == "GW2026"
        assert result.is_ongoing is True
        assert result.days_until_start == -1

    def test_discharge_planning_not_passed(self):
        """開始 3 週間より前なら planning_passed=False."""
        # GW 開始 4/29、planning_start = 4/8
        # 4/1 時点は planning_start よりさらに前
        result = calculate_next_holiday_countdown(date(2026, 4, 1))
        assert result is not None
        assert result.name == "GW2026"
        assert result.discharge_planning_passed is False

    def test_after_all_holidays_returns_none(self):
        """登録されたすべての連休が終了していたら None."""
        # 最後は 2027-08-16 なので、その翌日以降はすべて過去
        result = calculate_next_holiday_countdown(date(2028, 1, 1))
        assert result is None

    def test_none_today_returns_none(self):
        """today=None は None を返す."""
        assert calculate_next_holiday_countdown(None) is None


# ---------------------------------------------------------------
# 2. compute_dow_occupancy
# ---------------------------------------------------------------

class TestComputeDowOccupancy:
    """曜日別稼働率."""

    def test_empty_df_returns_default(self):
        """空 DataFrame はデフォルト 0.9 を返す."""
        df = pd.DataFrame()
        result = compute_dow_occupancy(df, total_beds=94)
        assert all(v == 0.9 for v in result.values())
        assert set(result.keys()) == set(range(7))

    def test_basic_computation(self):
        """月曜は稼働率高め、日曜は低めの簡易シナリオ."""
        rows = []
        # 最近 4 週
        base = pd.Timestamp("2026-03-30")  # 月曜
        for w in range(4):
            for d in range(7):
                day = base + pd.Timedelta(days=w * 7 + d)
                # 月=95%, 火〜金=92%, 土=88%, 日=80%
                occ_pct = [95, 92, 92, 92, 92, 88, 80][d]
                total_patients = int(94 * occ_pct / 100) - 1  # -1 = discharge
                rows.append({
                    "date": day,
                    "total_patients": total_patients,
                    "discharges": 1,
                })
        df = pd.DataFrame(rows)
        result = compute_dow_occupancy(df, total_beds=94)
        # 月曜は 0.95 近辺、日曜は 0.80 近辺
        assert result[0] == pytest.approx(0.95, abs=0.02)
        assert result[6] == pytest.approx(0.80, abs=0.02)
        # すべて 0-1 の範囲
        for v in result.values():
            assert 0.0 <= v <= 1.0

    def test_zero_beds_returns_default(self):
        """病床数 0 はデフォルトを返す."""
        df = pd.DataFrame({
            "date": [pd.Timestamp("2026-04-01")],
            "total_patients": [80],
            "discharges": [2],
        })
        result = compute_dow_occupancy(df, total_beds=0)
        assert all(v == 0.9 for v in result.values())

    def test_ward_filter(self):
        """ward フィルタが病棟別データを分離する."""
        rows = []
        base = pd.Timestamp("2026-03-30")
        for d in range(7):
            day = base + pd.Timedelta(days=d)
            # 5F は 95%、6F は 80%
            rows.append({"date": day, "ward": "5F", "total_patients": 44, "discharges": 1})
            rows.append({"date": day, "ward": "6F", "total_patients": 37, "discharges": 1})
        df = pd.DataFrame(rows)
        result_5f = compute_dow_occupancy(df, total_beds=47, weeks=8, ward="5F")
        result_6f = compute_dow_occupancy(df, total_beds=47, weeks=8, ward="6F")
        # 5F の方が稼働率が高い
        assert result_5f[0] > result_6f[0]

    def test_occupancy_clamped_to_one(self):
        """病床数を超える計算値は 1.0 にクランプされる."""
        df = pd.DataFrame({
            "date": [pd.Timestamp("2026-04-06")],  # 月曜
            "total_patients": [100],  # > 94
            "discharges": [5],
        })
        result = compute_dow_occupancy(df, total_beds=94)
        assert result[0] == 1.0

    def test_recent_weeks_only(self):
        """weeks=8 の境界外データは無視される."""
        # 100 日前の古いデータ + 最近のデータ
        old_day = pd.Timestamp("2026-01-05")  # 月曜・100 日以上前
        recent_day = pd.Timestamp("2026-04-13")  # 月曜・最近
        df = pd.DataFrame({
            "date": [old_day, recent_day],
            "total_patients": [30, 90],  # 古いデータは異常に低い
            "discharges": [0, 1],
        })
        # weeks=8 → 約 56 日しか遡らないので old_day は除外される
        result = compute_dow_occupancy(df, total_beds=94, weeks=8)
        # 月曜は最近の高い値のみで計算される
        assert result[0] > 0.9

    def test_missing_date_column_returns_default(self):
        """date 列がなければデフォルト."""
        df = pd.DataFrame({"total_patients": [80], "discharges": [2]})
        result = compute_dow_occupancy(df, total_beds=94)
        assert all(v == 0.9 for v in result.values())


# ---------------------------------------------------------------
# 3. _week_overall_classification
# ---------------------------------------------------------------

class TestWeekOverallClassification:
    """週全体の需要タイプ判定."""

    def test_high_demand(self):
        dow_means = {i: 10.0 for i in range(7)}
        vacancy = {i: 5.0 for i in range(7)}
        week_type, emoji, label = _week_overall_classification(dow_means, vacancy, margin=1.0)
        assert week_type == "high"
        assert label == "高需要"

    def test_low_demand(self):
        dow_means = {i: 3.0 for i in range(7)}
        vacancy = {i: 10.0 for i in range(7)}
        week_type, emoji, label = _week_overall_classification(dow_means, vacancy, margin=1.0)
        assert week_type == "low"
        assert label == "通常運用"

    def test_standard_demand(self):
        dow_means = {i: 5.0 for i in range(7)}
        vacancy = {i: 5.5 for i in range(7)}
        week_type, emoji, label = _week_overall_classification(dow_means, vacancy, margin=1.0)
        assert week_type == "standard"
        assert label == "標準"


# ---------------------------------------------------------------
# 4. 構造確認: _HOLIDAY_PERIODS の完全性
# ---------------------------------------------------------------

class TestHolidayPeriodsData:
    """大型連休の定義データ整合性."""

    def test_gw_duration_7_days(self):
        """GW2026 は 4/29 〜 5/5 の 7 日間."""
        gw = [h for h in _HOLIDAY_PERIODS if h[0] == "GW2026"]
        assert len(gw) == 1
        name, start, end = gw[0]
        assert (end - start).days + 1 == 7

    def test_holidays_chronological(self):
        """定義リストは時系列順に並んでいる（目視検証用）."""
        starts = [h[1] for h in _HOLIDAY_PERIODS]
        assert starts == sorted(starts)


# ---------------------------------------------------------------
# 5. classify_discharge_candidates（タブ 2 ロジック）
# ---------------------------------------------------------------

def _make_admission_row(
    adm_id: str,
    date_str: str,
    ward: str,
    route: str,
    short3_type: str = "該当なし",
) -> dict:
    """admission 行のヘルパー."""
    return {
        "id": adm_id,
        "date": date_str,
        "ward": ward,
        "event_type": "admission",
        "route": route,
        "source_doctor": "C医師",
        "attending_doctor": "C医師",
        "los_days": "",
        "phase": "",
        "short3_type": short3_type,
    }


def _make_discharge_row(
    dis_id: str,
    date_str: str,
    ward: str,
    los_days: int,
    phase: str = "B",
) -> dict:
    """discharge 行のヘルパー."""
    return {
        "id": dis_id,
        "date": date_str,
        "ward": ward,
        "event_type": "discharge",
        "route": "",
        "source_doctor": "",
        "attending_doctor": "C医師",
        "los_days": str(los_days),
        "phase": phase,
        "short3_type": "",
    }


class TestClassifyDischargeCandidates:
    """退院候補リストの仕分けロジック."""

    def setup_method(self):
        self.today = date(2026, 4, 17)
        self.holiday = calculate_next_holiday_countdown(self.today)  # GW2026

    def test_empty_df_returns_empty(self):
        """空 DataFrame → 空の結果 DataFrame."""
        result = classify_discharge_candidates(
            pd.DataFrame(), None, self.today, ward=None, next_holiday=self.holiday,
        )
        assert len(result) == 0
        # 必要なカラムは存在する
        assert "patient_id" in result.columns
        assert "recommended_category" in result.columns

    def test_none_df_returns_empty(self):
        """None → 空 DataFrame."""
        result = classify_discharge_candidates(
            None, None, self.today, ward=None, next_holiday=self.holiday,
        )
        assert len(result) == 0

    def test_missing_required_cols_returns_empty(self):
        """必須カラム欠損 → 空 DataFrame."""
        df = pd.DataFrame([{"foo": "bar"}])
        result = classify_discharge_candidates(
            df, None, self.today, ward=None, next_holiday=self.holiday,
        )
        assert len(result) == 0

    def test_category_a_planned_long_stay(self):
        """在院 12 日・外来紹介 → A（連休前退院候補）."""
        df = pd.DataFrame([
            _make_admission_row(
                "aaaaaaaa-0000-0000-0000-000000000001",
                "2026-04-05",  # 12 日前
                "5F",
                "外来紹介",
            ),
        ])
        result = classify_discharge_candidates(
            df, None, self.today, ward=None, next_holiday=self.holiday,
        )
        assert len(result) == 1
        assert result.iloc[0]["recommended_category"] == CATEGORY_A
        assert result.iloc[0]["stay_days"] == 13  # Day 1 = 入院日

    def test_category_b_emergency_route(self):
        """救急経路 → B（在院日数に関係なく）."""
        df = pd.DataFrame([
            _make_admission_row(
                "bbbbbbbb-0000-0000-0000-000000000001",
                "2026-04-05",  # 12 日前だが
                "5F",
                "救急",
            ),
        ])
        result = classify_discharge_candidates(
            df, None, self.today, ward=None, next_holiday=self.holiday,
        )
        assert len(result) == 1
        assert result.iloc[0]["recommended_category"] == CATEGORY_B

    def test_category_b_phase_a_short_stay(self):
        """在院 3 日・外来紹介 → B（phase A 急性期中）."""
        df = pd.DataFrame([
            _make_admission_row(
                "cccccccc-0000-0000-0000-000000000001",
                "2026-04-15",  # 3 日前
                "5F",
                "外来紹介",
            ),
        ])
        result = classify_discharge_candidates(
            df, None, self.today, ward=None, next_holiday=self.holiday,
        )
        assert len(result) == 1
        assert result.iloc[0]["recommended_category"] == CATEGORY_B
        assert result.iloc[0]["phase"] == "A"

    def test_category_unknown_no_route(self):
        """経路欠損（空文字）→ 判定不能."""
        df = pd.DataFrame([
            _make_admission_row(
                "dddddddd-0000-0000-0000-000000000001",
                "2026-04-05",
                "5F",
                "",  # route empty
            ),
        ])
        result = classify_discharge_candidates(
            df, None, self.today, ward=None, next_holiday=self.holiday,
        )
        assert len(result) == 1
        assert result.iloc[0]["recommended_category"] == CATEGORY_UNKNOWN

    def test_stay_days_boundary_7_days_is_a(self):
        """在院ちょうど 7 日・外来紹介 → A."""
        # 7 日目 → 入院日 = today - 6 = 4/11
        df = pd.DataFrame([
            _make_admission_row(
                "eeeeeeee-0000-0000-0000-000000000001",
                "2026-04-11",  # 7 日前 (stay_days=7, phase B)
                "5F",
                "外来紹介",
            ),
        ])
        result = classify_discharge_candidates(
            df, None, self.today, ward=None, next_holiday=self.holiday,
        )
        assert len(result) == 1
        assert result.iloc[0]["stay_days"] == 7
        assert result.iloc[0]["recommended_category"] == CATEGORY_A

    def test_stay_days_boundary_6_days_is_b(self):
        """在院 6 日・外来紹介 → B（まだ 7 日未満）."""
        df = pd.DataFrame([
            _make_admission_row(
                "ffffffff-0000-0000-0000-000000000001",
                "2026-04-12",  # 6 日前 (stay_days=6, phase B)
                "5F",
                "外来紹介",
            ),
        ])
        result = classify_discharge_candidates(
            df, None, self.today, ward=None, next_holiday=self.holiday,
        )
        assert len(result) == 1
        assert result.iloc[0]["stay_days"] == 6
        assert result.iloc[0]["recommended_category"] == CATEGORY_B

    def test_ward_filter_5f(self):
        """ward='5F' で 5F のみ返る."""
        df = pd.DataFrame([
            _make_admission_row("a1-0000-0000-0000-000000000001", "2026-04-05", "5F", "外来紹介"),
            _make_admission_row("a2-0000-0000-0000-000000000001", "2026-04-05", "6F", "外来紹介"),
        ])
        result = classify_discharge_candidates(
            df, None, self.today, ward="5F", next_holiday=self.holiday,
        )
        assert len(result) == 1
        assert result.iloc[0]["ward"] == "5F"

    def test_ward_filter_6f(self):
        """ward='6F' で 6F のみ返る."""
        df = pd.DataFrame([
            _make_admission_row("a3-0000-0000-0000-000000000001", "2026-04-05", "5F", "外来紹介"),
            _make_admission_row("a4-0000-0000-0000-000000000001", "2026-04-05", "6F", "外来紹介"),
        ])
        result = classify_discharge_candidates(
            df, None, self.today, ward="6F", next_holiday=self.holiday,
        )
        assert len(result) == 1
        assert result.iloc[0]["ward"] == "6F"

    def test_discharged_patient_excluded(self):
        """admission に対応する discharge が存在すれば除外される."""
        df = pd.DataFrame([
            _make_admission_row(
                "disch-000-0000-0000-0000-000000000001",
                "2026-04-05",
                "5F",
                "外来紹介",
            ),
            # この患者は 4/10 に退院（LOS=5）
            _make_discharge_row(
                "dis-000-0000-0000-0000-000000000001",
                "2026-04-10",
                "5F",
                los_days=5,
            ),
        ])
        result = classify_discharge_candidates(
            df, None, self.today, ward=None, next_holiday=self.holiday,
        )
        # 退院済みなので空
        assert len(result) == 0

    def test_future_admissions_excluded(self):
        """未来の入院予定は対象外."""
        df = pd.DataFrame([
            _make_admission_row(
                "fut-0000-0000-0000-0000-000000000001",
                "2026-04-25",  # today(4/17) より未来
                "5F",
                "外来紹介",
            ),
        ])
        result = classify_discharge_candidates(
            df, None, self.today, ward=None, next_holiday=self.holiday,
        )
        assert len(result) == 0

    def test_no_pii_columns(self):
        """返り値に個人情報カラムが含まれない（氏名/年齢/診断名/医師名）."""
        df = pd.DataFrame([
            _make_admission_row(
                "pii-0000-0000-0000-0000-000000000001",
                "2026-04-05",
                "5F",
                "外来紹介",
            ),
        ])
        result = classify_discharge_candidates(
            df, None, self.today, ward=None, next_holiday=self.holiday,
        )
        banned_keywords = [
            "name", "姓", "名", "birth", "生年月日", "年齢", "age",
            "diagnosis", "診断", "disease", "icd",
            "source_doctor", "attending_doctor", "医師",
        ]
        for col in result.columns:
            for banned in banned_keywords:
                assert banned.lower() not in col.lower(), (
                    f"個人情報カラム候補が返り値に含まれています: {col}"
                )

    def test_patient_id_is_uuid_like(self):
        """patient_id は UUID 文字列、patient_id_short は先頭 8 桁."""
        df = pd.DataFrame([
            _make_admission_row(
                "uuid1234-0000-0000-0000-000000000001",
                "2026-04-05",
                "5F",
                "外来紹介",
            ),
        ])
        result = classify_discharge_candidates(
            df, None, self.today, ward=None, next_holiday=self.holiday,
        )
        assert len(result) == 1
        pid = result.iloc[0]["patient_id"]
        pid_short = result.iloc[0]["patient_id_short"]
        assert pid == "uuid1234-0000-0000-0000-000000000001"
        assert pid_short == "uuid1234"
        assert len(pid_short) == 8

    def test_sorting_a_first_then_by_stay(self):
        """並び順: 推奨区分（A→B→C→不能）→ 在院日数降順."""
        df = pd.DataFrame([
            # B: 短期救急
            _make_admission_row("p1-0000-0000-0000-0000-000000000001",
                                "2026-04-14", "5F", "救急"),
            # A: 長期予定
            _make_admission_row("p2-0000-0000-0000-0000-000000000001",
                                "2026-04-03", "5F", "外来紹介"),
            # A: 中期予定
            _make_admission_row("p3-0000-0000-0000-0000-000000000001",
                                "2026-04-08", "5F", "連携室"),
        ])
        result = classify_discharge_candidates(
            df, None, self.today, ward=None, next_holiday=self.holiday,
        )
        assert len(result) == 3
        # 先頭 2 行は A で、在院日数降順
        assert result.iloc[0]["recommended_category"] == CATEGORY_A
        assert result.iloc[1]["recommended_category"] == CATEGORY_A
        assert result.iloc[0]["stay_days"] >= result.iloc[1]["stay_days"]
        # 3 番目は B
        assert result.iloc[2]["recommended_category"] == CATEGORY_B

    def test_none_next_holiday_still_works(self):
        """next_holiday=None でも A/B 判定は動作する（C 判定のみ無効化）."""
        df = pd.DataFrame([
            _make_admission_row(
                "nh-0000-0000-0000-0000-000000000001",
                "2026-04-05",
                "5F",
                "外来紹介",
            ),
        ])
        result = classify_discharge_candidates(
            df, None, self.today, ward=None, next_holiday=None,
        )
        assert len(result) == 1
        assert result.iloc[0]["recommended_category"] == CATEGORY_A

    def test_large_dataset_performance(self):
        """1,000 件超のデータでも 1 秒以内に処理できる."""
        import time

        rows = []
        base = date(2026, 3, 1)
        for i in range(1200):
            days_ago = i % 30
            adm_date = base + timedelta(days=days_ago)
            rows.append(_make_admission_row(
                f"perf-{i:04d}-0000-0000-0000-000000000000",
                adm_date.isoformat(),
                "5F" if i % 2 == 0 else "6F",
                "外来紹介" if i % 3 == 0 else "救急",
            ))
        df = pd.DataFrame(rows)
        start = time.perf_counter()
        result = classify_discharge_candidates(
            df, None, self.today, ward=None, next_holiday=self.holiday,
        )
        elapsed = time.perf_counter() - start
        # 厳密な性能計測ではないが、1 秒以内に終われば OK
        assert elapsed < 1.0, f"処理が遅すぎます: {elapsed:.2f}秒"
        # 結果も返る
        assert len(result) > 0


# ---------------------------------------------------------------
# 6. summarize_categories
# ---------------------------------------------------------------

class TestSummarizeCategories:
    """区分別集計."""

    def test_empty_returns_zeros(self):
        """空 DataFrame → 全区分 0."""
        counts = summarize_categories(pd.DataFrame())
        assert counts[CATEGORY_A] == 0
        assert counts[CATEGORY_B] == 0
        assert counts[CATEGORY_C] == 0
        assert counts[CATEGORY_UNKNOWN] == 0

    def test_basic_count(self):
        """カテゴリ混在時の集計."""
        df = pd.DataFrame({
            "manual_category": [
                CATEGORY_A, CATEGORY_A, CATEGORY_A,
                CATEGORY_B, CATEGORY_B,
                CATEGORY_C,
                CATEGORY_UNKNOWN,
            ],
        })
        counts = summarize_categories(df)
        assert counts[CATEGORY_A] == 3
        assert counts[CATEGORY_B] == 2
        assert counts[CATEGORY_C] == 1
        assert counts[CATEGORY_UNKNOWN] == 1

    def test_missing_column_returns_zeros(self):
        """category_col 欠損 → 全 0."""
        df = pd.DataFrame({"foo": [1, 2, 3]})
        counts = summarize_categories(df, category_col="manual_category")
        assert sum(counts.values()) == 0


# ---------------------------------------------------------------
# 4. Tab 3「📅 予約可能枠」用ヘルパー
# ---------------------------------------------------------------

class TestIsInHolidayPeriod:
    """連休期間判定."""

    def test_gw_start_day(self):
        """GW 開始日 4/29 は連休中."""
        assert _is_in_holiday_period(date(2026, 4, 29)) == "GW2026"

    def test_gw_end_day(self):
        """GW 終了日 5/5 は連休中."""
        assert _is_in_holiday_period(date(2026, 5, 5)) == "GW2026"

    def test_before_gw(self):
        """GW 開始前日 4/28 は非連休."""
        assert _is_in_holiday_period(date(2026, 4, 28)) is None

    def test_after_gw(self):
        """GW 明け 5/6 は非連休."""
        assert _is_in_holiday_period(date(2026, 5, 6)) is None


class TestIsPostHolidayWeek:
    """連休明け 7 日以内判定."""

    def test_recover_day_is_post(self):
        """5/6 は連休明け初日 → True."""
        assert _is_post_holiday_week(date(2026, 5, 6)) is True

    def test_recover_plus_6_still_post(self):
        """5/12 は連休明け +6 日 → True."""
        assert _is_post_holiday_week(date(2026, 5, 12)) is True

    def test_recover_plus_7_not_post(self):
        """5/13 は連休明け +7 日 → False."""
        assert _is_post_holiday_week(date(2026, 5, 13)) is False

    def test_during_gw_not_post(self):
        """GW 期間中は post_holiday ではない."""
        # Note: 関数は post_holiday を単独判定するため、
        # 呼び出し側で is_holiday との排他制御が必要
        assert _is_post_holiday_week(date(2026, 5, 5)) is False


class TestClassifyBookingAvailability:
    """可能枠ベースのカラー判定."""

    def test_holiday_returns_blue(self):
        """連休中は 🔵 連休."""
        emoji, label = _classify_booking_availability(slots=10, in_holiday=True)
        assert emoji == "🔵"
        assert label == "連休"

    def test_slots_0_is_red(self):
        """可能枠 0 → 🔴 満員."""
        emoji, label = _classify_booking_availability(slots=0, in_holiday=False)
        assert emoji == "🔴"
        assert label == "満員"

    def test_slots_1_is_red(self):
        """可能枠 1 → 🔴 満員."""
        emoji, label = _classify_booking_availability(slots=1, in_holiday=False)
        assert emoji == "🔴"

    def test_slots_2_is_yellow(self):
        """可能枠 2 → 🟡 やや混雑（境界）."""
        emoji, label = _classify_booking_availability(slots=2, in_holiday=False)
        assert emoji == "🟡"
        assert label == "やや混雑"

    def test_slots_4_is_yellow(self):
        """可能枠 4 → 🟡 やや混雑（境界）."""
        emoji, label = _classify_booking_availability(slots=4, in_holiday=False)
        assert emoji == "🟡"

    def test_slots_5_is_green(self):
        """可能枠 5 → 🟢 通常（境界）."""
        emoji, label = _classify_booking_availability(slots=5, in_holiday=False)
        assert emoji == "🟢"
        assert label == "通常"

    def test_slots_10_is_green(self):
        """可能枠 10 → 🟢 通常."""
        emoji, label = _classify_booking_availability(slots=10, in_holiday=False)
        assert emoji == "🟢"


class TestForecastDailyDemandForPeriod:
    """日別需要予測期間."""

    def _make_forecast(self, dow_mean: float = 8.0, trend: float = 1.0) -> dict:
        return {
            "target_week_start": date(2026, 4, 13),
            "dow_means": {i: dow_mean for i in range(7)},
            "expected_weekly_total": dow_mean * 7 * trend,
            "p25": 0.0,
            "p75": 0.0,
            "recent_trend_factor": trend,
            "confidence": "high",
            "sample_size": 1000,
        }

    def test_basic_period_generates_correct_rows(self):
        """4 週間期間 → 28 行."""
        forecast = self._make_forecast()
        result = forecast_daily_demand_for_period(
            forecast=forecast,
            start_date=date(2026, 4, 13),
            end_date=date(2026, 5, 10),
            daily_df=pd.DataFrame(),
            ward=None,
            total_beds=94,
            admission_details_df=pd.DataFrame(),
        )
        assert len(result) == 28
        assert "date" in result.columns
        assert "available_slots" in result.columns
        assert "emoji" in result.columns

    def test_empty_forecast_handled(self):
        """forecast=None でも例外なく空に近い結果."""
        result = forecast_daily_demand_for_period(
            forecast=None,
            start_date=date(2026, 4, 13),
            end_date=date(2026, 4, 19),
            daily_df=None,
            ward=None,
            total_beds=94,
            admission_details_df=None,
        )
        assert len(result) == 7
        # 予想入院 = 0, 空床 = 94 * 0.1 = 9.4 → 可能枠 9 くらい
        assert (result["expected_admissions"] == 0.0).all()

    def test_end_before_start_returns_empty(self):
        """end_date < start_date は空."""
        result = forecast_daily_demand_for_period(
            forecast=self._make_forecast(),
            start_date=date(2026, 4, 20),
            end_date=date(2026, 4, 15),
        )
        assert len(result) == 0

    def test_holiday_period_has_reduced_admissions(self):
        """GW 期間内の日は予想入院が -90%（×0.10）される."""
        forecast = self._make_forecast(dow_mean=10.0, trend=1.0)
        result = forecast_daily_demand_for_period(
            forecast=forecast,
            start_date=date(2026, 4, 28),  # GW 前日
            end_date=date(2026, 5, 6),     # GW 明け初日
        )
        # 4/28 = 通常 → ≈ 10.0
        row_pre = result[result["date"] == date(2026, 4, 28)].iloc[0]
        assert bool(row_pre["is_holiday"]) is False
        assert abs(row_pre["expected_admissions"] - 10.0) < 0.01

        # 5/1 = GW 期間中 → 10.0 × 0.10 = 1.0
        row_in = result[result["date"] == date(2026, 5, 1)].iloc[0]
        assert bool(row_in["is_holiday"]) is True
        assert row_in["holiday_name"] == "GW2026"
        assert abs(row_in["expected_admissions"] - 1.0) < 0.01
        # 連休中は available_slots = 0
        assert int(row_in["available_slots"]) == 0

    def test_post_holiday_week_has_surge(self):
        """連休明け初日（5/6）は +20%（×1.20）."""
        forecast = self._make_forecast(dow_mean=10.0, trend=1.0)
        result = forecast_daily_demand_for_period(
            forecast=forecast,
            start_date=date(2026, 5, 6),
            end_date=date(2026, 5, 10),
        )
        row = result[result["date"] == date(2026, 5, 6)].iloc[0]
        assert bool(row["is_holiday"]) is False
        assert bool(row["is_post_holiday"]) is True
        # 10.0 × 1.20 = 12.0
        assert abs(row["expected_admissions"] - 12.0) < 0.01

    def test_booked_count_reduces_slots(self):
        """admission_details に同日の admission があれば既予約が引かれる."""
        forecast = self._make_forecast(dow_mean=5.0, trend=1.0)
        details = pd.DataFrame([
            {
                "id": "x1-0000-0000-0000-000000000001",
                "date": "2026-04-20",
                "ward": "5F",
                "event_type": "admission",
                "route": "外来紹介",
                "source_doctor": "", "attending_doctor": "",
                "los_days": "", "phase": "", "short3_type": "",
            },
            {
                "id": "x2-0000-0000-0000-000000000001",
                "date": "2026-04-20",
                "ward": "5F",
                "event_type": "admission",
                "route": "外来紹介",
                "source_doctor": "", "attending_doctor": "",
                "los_days": "", "phase": "", "short3_type": "",
            },
        ])
        result = forecast_daily_demand_for_period(
            forecast=forecast,
            start_date=date(2026, 4, 20),
            end_date=date(2026, 4, 20),
            daily_df=pd.DataFrame(),
            ward="5F",
            total_beds=47,
            admission_details_df=details,
        )
        row = result.iloc[0]
        assert int(row["booked_count"]) == 2

    def test_ward_filter_excludes_other_ward_bookings(self):
        """ward='5F' 指定時、6F の admission は booked_count に入らない."""
        forecast = self._make_forecast(dow_mean=5.0, trend=1.0)
        details = pd.DataFrame([
            {
                "id": "w1-0000-0000-0000-000000000001",
                "date": "2026-04-20",
                "ward": "6F",  # 別病棟
                "event_type": "admission",
                "route": "外来紹介",
                "source_doctor": "", "attending_doctor": "",
                "los_days": "", "phase": "", "short3_type": "",
            },
        ])
        result = forecast_daily_demand_for_period(
            forecast=forecast,
            start_date=date(2026, 4, 20),
            end_date=date(2026, 4, 20),
            daily_df=pd.DataFrame(),
            ward="5F",
            total_beds=47,
            admission_details_df=details,
        )
        row = result.iloc[0]
        assert int(row["booked_count"]) == 0

    def test_boundary_color_classification(self):
        """可能枠 1 → 🔴、2 → 🟡、5 → 🟢 の分布が生成結果に現れる."""
        # dow_mean と空床を意図的に操作したいので、direct に classify を回帰確認
        # ここでは forecast_daily_demand_for_period 経由でも境界を通れるよう
        # 小さい dow_mean / total_beds を設定
        forecast = self._make_forecast(dow_mean=0.0, trend=1.0)
        # daily_df なし → 稼働率 0.9 → 空床 = total_beds × 0.1
        # total_beds=10 → 空床 1 → 可能枠 1 → 🔴
        result_red = forecast_daily_demand_for_period(
            forecast=forecast,
            start_date=date(2026, 4, 13),
            end_date=date(2026, 4, 13),
            daily_df=pd.DataFrame(),
            ward=None,
            total_beds=10,
        )
        assert int(result_red.iloc[0]["available_slots"]) == 1
        assert result_red.iloc[0]["emoji"] == "🔴"

        # total_beds=30 → 空床 3 → 可能枠 3 → 🟡
        result_yellow = forecast_daily_demand_for_period(
            forecast=forecast,
            start_date=date(2026, 4, 13),
            end_date=date(2026, 4, 13),
            daily_df=pd.DataFrame(),
            ward=None,
            total_beds=30,
        )
        assert int(result_yellow.iloc[0]["available_slots"]) == 3
        assert result_yellow.iloc[0]["emoji"] == "🟡"

        # total_beds=60 → 空床 6 → 可能枠 6 → 🟢
        result_green = forecast_daily_demand_for_period(
            forecast=forecast,
            start_date=date(2026, 4, 13),
            end_date=date(2026, 4, 13),
            daily_df=pd.DataFrame(),
            ward=None,
            total_beds=60,
        )
        assert int(result_green.iloc[0]["available_slots"]) == 6
        assert result_green.iloc[0]["emoji"] == "🟢"

    def test_past_booking_dates_still_counted(self):
        """start_date より前の予約は含まない（期間外は無視）."""
        forecast = self._make_forecast(dow_mean=0.0)
        details = pd.DataFrame([
            {
                "id": "p1-0000-0000-0000-000000000001",
                "date": "2026-04-01",  # 期間外（過去）
                "ward": "5F",
                "event_type": "admission",
                "route": "外来紹介",
                "source_doctor": "", "attending_doctor": "",
                "los_days": "", "phase": "", "short3_type": "",
            },
        ])
        result = forecast_daily_demand_for_period(
            forecast=forecast,
            start_date=date(2026, 4, 13),
            end_date=date(2026, 4, 19),
            daily_df=pd.DataFrame(),
            ward="5F",
            total_beds=47,
            admission_details_df=details,
        )
        # 期間内のどの日にも既予約は 0
        assert (result["booked_count"] == 0).all()

    def test_discharge_events_ignored(self):
        """event_type=='discharge' の行は booked_count に含まれない."""
        forecast = self._make_forecast(dow_mean=0.0)
        details = pd.DataFrame([
            {
                "id": "d1-0000-0000-0000-000000000001",
                "date": "2026-04-20",
                "ward": "5F",
                "event_type": "discharge",  # 退院
                "route": "", "source_doctor": "", "attending_doctor": "",
                "los_days": "7", "phase": "B", "short3_type": "",
            },
        ])
        result = forecast_daily_demand_for_period(
            forecast=forecast,
            start_date=date(2026, 4, 20),
            end_date=date(2026, 4, 20),
            daily_df=pd.DataFrame(),
            ward="5F",
            total_beds=47,
            admission_details_df=details,
        )
        assert int(result.iloc[0]["booked_count"]) == 0


class TestSummarizeBookingCounts:
    """カレンダー期間中の判定別日数サマリー."""

    def test_empty_returns_zeros(self):
        counts = _summarize_booking_counts(pd.DataFrame())
        assert counts["通常"] == 0
        assert counts["やや混雑"] == 0
        assert counts["満員"] == 0
        assert counts["連休"] == 0

    def test_basic_counts(self):
        df = pd.DataFrame({
            "label": ["通常", "通常", "やや混雑", "満員", "連休", "連休", "通常"],
        })
        counts = _summarize_booking_counts(df)
        assert counts["通常"] == 3
        assert counts["やや混雑"] == 1
        assert counts["満員"] == 1
        assert counts["連休"] == 2
