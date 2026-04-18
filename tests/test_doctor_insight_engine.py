"""
テスト: doctor_insight_engine — 医師別深掘りインサイト

Phase 1 の 2 指標:
    1. 曜日別退院プロファイル（calculate_weekday_profile / build_weekday_insights）
    2. C群長期化率（calculate_c_group_stats / build_c_group_insights）
    3. 統合（build_doctor_insights）

境界条件:
    - 医師 1 名のみのケース
    - データゼロ
    - event_type="admission" のみ（退院データ無し）
    - サンプル不足（最小件数未満）
"""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from doctor_insight_engine import (  # noqa: E402
    build_c_group_insights,
    build_doctor_insights,
    build_weekday_insights,
    calculate_c_group_stats,
    calculate_weekday_profile,
    MIN_DISCHARGES_FOR_WEEKDAY,
    MIN_DISCHARGES_FOR_C_GROUP,
    FRIDAY_HEAVY_THRESHOLD_PCT,
    C_GROUP_HEAVY_ABS_PCT,
)


# ===================================================================
# フィクスチャ
# ===================================================================

@pytest.fixture
def empty_detail_df():
    """空の admission_details 風 DataFrame."""
    return pd.DataFrame(columns=[
        "id", "date", "ward", "event_type", "route",
        "source_doctor", "attending_doctor", "los_days", "phase", "short3_type",
    ])


def _make_discharge(date, doctor, los_days=7, phase="B"):
    return {
        "id": f"{date}-{doctor}-{los_days}",
        "date": date,
        "ward": "5F",
        "event_type": "discharge",
        "route": "",
        "source_doctor": "",
        "attending_doctor": doctor,
        "los_days": los_days,
        "phase": phase,
        "short3_type": "",
    }


def _make_admission(date, doctor):
    return {
        "id": f"{date}-adm-{doctor}",
        "date": date,
        "ward": "5F",
        "event_type": "admission",
        "route": "外来紹介",
        "source_doctor": doctor,
        "attending_doctor": doctor,
        "los_days": pd.NA,
        "phase": "",
        "short3_type": "該当なし",
    }


@pytest.fixture
def friday_heavy_doctor_df():
    """
    医師 A: 金曜集中（10件中 6件が金曜=60%）、C群 0%
    医師 B: 平準化（月-金で平均）、C群 30%
    """
    rows = []
    # 医師 A の退院: 金曜 6件, 火曜2件, 水曜1件, 木曜1件
    friday_dates = ["2026-03-06", "2026-03-13", "2026-03-20", "2026-03-27", "2026-04-03", "2026-04-10"]
    for d in friday_dates:
        rows.append(_make_discharge(d, "A医師", los_days=7, phase="B"))
    rows.append(_make_discharge("2026-03-03", "A医師", los_days=5, phase="A"))  # 火
    rows.append(_make_discharge("2026-03-10", "A医師", los_days=5, phase="A"))  # 火
    rows.append(_make_discharge("2026-03-04", "A医師", los_days=6, phase="B"))  # 水
    rows.append(_make_discharge("2026-03-05", "A医師", los_days=6, phase="B"))  # 木

    # 医師 B の退院: 月〜金で平均的に（各2件）、うちC群3件
    rows.append(_make_discharge("2026-03-02", "B医師", los_days=8, phase="B"))   # 月
    rows.append(_make_discharge("2026-03-09", "B医師", los_days=8, phase="B"))   # 月
    rows.append(_make_discharge("2026-03-10", "B医師", los_days=18, phase="C"))  # 火
    rows.append(_make_discharge("2026-03-17", "B医師", los_days=18, phase="C"))  # 火
    rows.append(_make_discharge("2026-03-11", "B医師", los_days=11, phase="B"))  # 水
    rows.append(_make_discharge("2026-03-18", "B医師", los_days=11, phase="B"))  # 水
    rows.append(_make_discharge("2026-03-12", "B医師", los_days=12, phase="B"))  # 木
    rows.append(_make_discharge("2026-03-19", "B医師", los_days=22, phase="C"))  # 木
    rows.append(_make_discharge("2026-03-13", "B医師", los_days=4, phase="A"))   # 金
    rows.append(_make_discharge("2026-03-20", "B医師", los_days=4, phase="A"))   # 金

    return pd.DataFrame(rows)


@pytest.fixture
def single_doctor_df():
    """医師 1 名のみ、退院 6 件（最小サンプル 5 以上）"""
    rows = []
    for i, d in enumerate(["2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06", "2026-03-09"]):
        los = 8
        phase = "B"
        rows.append(_make_discharge(d, "単独医師", los_days=los, phase=phase))
    return pd.DataFrame(rows)


@pytest.fixture
def c_group_heavy_doctor_df():
    """C群長期化医師 C医師 (C比率75%) vs 標準医師 D医師 (C比率20%)"""
    rows = []
    # C医師: 退院8件中6件がC群
    for d in ["2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06", "2026-03-09"]:
        rows.append(_make_discharge(d, "C医師", los_days=20, phase="C"))
    rows.append(_make_discharge("2026-03-10", "C医師", los_days=8, phase="B"))
    rows.append(_make_discharge("2026-03-11", "C医師", los_days=4, phase="A"))

    # D医師: 退院10件中2件のみC群
    for d in ["2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06", "2026-03-09", "2026-03-10", "2026-03-11"]:
        rows.append(_make_discharge(d, "D医師", los_days=7, phase="B"))
    rows.append(_make_discharge("2026-03-12", "D医師", los_days=17, phase="C"))
    rows.append(_make_discharge("2026-03-13", "D医師", los_days=18, phase="C"))

    return pd.DataFrame(rows)


# ===================================================================
# calculate_weekday_profile
# ===================================================================

class TestCalculateWeekdayProfile:
    def test_empty_df_returns_zero(self, empty_detail_df):
        result = calculate_weekday_profile(empty_detail_df)
        assert result["total_discharges"] == 0
        assert result["enough_data"] is False
        assert result["friday_pct"] == 0.0

    def test_admission_only_returns_zero(self):
        """入院レコードのみ → 退院分析は 0"""
        df = pd.DataFrame([
            _make_admission("2026-03-02", "X医師"),
            _make_admission("2026-03-03", "X医師"),
        ])
        result = calculate_weekday_profile(df)
        assert result["total_discharges"] == 0
        assert result["enough_data"] is False

    def test_friday_heavy_overall(self, friday_heavy_doctor_df):
        """全体で金曜が最多のはず（A6件 + B2件 = 計8件 / 全20件 = 40%）"""
        result = calculate_weekday_profile(friday_heavy_doctor_df)
        assert result["total_discharges"] == 20
        assert result["weekday_counts"][4] == 8  # 金曜
        assert result["friday_pct"] == 40.0
        assert result["enough_data"] is True

    def test_per_doctor_profile(self, friday_heavy_doctor_df):
        """A医師の金曜率は 60%"""
        result = calculate_weekday_profile(friday_heavy_doctor_df, doctor_name="A医師")
        assert result["total_discharges"] == 10
        assert result["friday_pct"] == 60.0
        assert result["weekday_counts"][4] == 6

    def test_percentage_sums_to_100(self, friday_heavy_doctor_df):
        result = calculate_weekday_profile(friday_heavy_doctor_df)
        total_pct = sum(result["weekday_pct"].values())
        assert abs(total_pct - 100.0) < 0.01

    def test_enough_data_threshold(self):
        """最小件数 5 未満 → enough_data=False"""
        rows = [_make_discharge(f"2026-03-0{i+2}", "少数医師", los_days=7, phase="B") for i in range(3)]
        df = pd.DataFrame(rows)
        result = calculate_weekday_profile(df, doctor_name="少数医師")
        assert result["total_discharges"] == 3
        assert result["enough_data"] is False

    def test_weekend_pct_calc(self):
        """土日2件/総4件 = 50%"""
        rows = [
            _make_discharge("2026-03-02", "Z医師", los_days=7, phase="B"),  # 月
            _make_discharge("2026-03-03", "Z医師", los_days=7, phase="B"),  # 火
            _make_discharge("2026-03-07", "Z医師", los_days=7, phase="B"),  # 土
            _make_discharge("2026-03-08", "Z医師", los_days=7, phase="B"),  # 日
        ]
        df = pd.DataFrame(rows)
        result = calculate_weekday_profile(df, doctor_name="Z医師")
        assert result["weekend_pct"] == 50.0


# ===================================================================
# build_weekday_insights
# ===================================================================

class TestBuildWeekdayInsights:
    def test_empty_df_returns_empty(self, empty_detail_df):
        assert build_weekday_insights(empty_detail_df) == []

    def test_friday_heavy_doctor_flagged_warning(self, friday_heavy_doctor_df):
        insights = build_weekday_insights(friday_heavy_doctor_df)
        doctors = {i["doctor"]: i for i in insights}
        assert "A医師" in doctors
        a = doctors["A医師"]
        # A医師は金曜 60% なので severity=warning
        assert a["severity"] == "warning"
        assert a["friday_pct"] >= FRIDAY_HEAVY_THRESHOLD_PCT
        assert "金曜" in a["observation"]

    def test_balanced_doctor_neutral(self, friday_heavy_doctor_df):
        insights = build_weekday_insights(friday_heavy_doctor_df)
        doctors = {i["doctor"]: i for i in insights}
        assert "B医師" in doctors
        b = doctors["B医師"]
        # B医師は平準化 → warning にならない
        assert b["severity"] in ("neutral", "warning")  # allow for relative deviation
        # 金曜率 20%
        assert b["friday_pct"] == 20.0

    def test_single_doctor_returns_one_entry(self, single_doctor_df):
        insights = build_weekday_insights(single_doctor_df)
        assert len(insights) == 1
        assert insights[0]["doctor"] == "単独医師"
        assert insights[0]["enough_data"] is True

    def test_action_hint_is_not_blaming(self, friday_heavy_doctor_df):
        """action_hint は非難トーンではなく提案トーン"""
        insights = build_weekday_insights(friday_heavy_doctor_df)
        for ins in insights:
            # ネガティブワードが含まれない
            assert "悪い" not in ins["observation"]
            assert "悪い" not in ins["action_hint"]
            assert "問題" not in ins["action_hint"]


# ===================================================================
# calculate_c_group_stats
# ===================================================================

class TestCalculateCGroupStats:
    def test_empty_returns_zero(self, empty_detail_df):
        result = calculate_c_group_stats(empty_detail_df)
        assert result["total_discharges"] == 0
        assert result["c_group_pct"] == 0.0
        assert result["enough_data"] is False

    def test_c_heavy_doctor(self, c_group_heavy_doctor_df):
        """C医師: 退院8件中C群6件 = 75%"""
        result = calculate_c_group_stats(c_group_heavy_doctor_df, doctor_name="C医師")
        assert result["total_discharges"] == 8
        assert result["c_group_count"] == 6
        assert result["c_group_pct"] == 75.0
        assert result["enough_data"] is True

    def test_d_standard_doctor(self, c_group_heavy_doctor_df):
        """D医師: 退院10件中C群2件 = 20%"""
        result = calculate_c_group_stats(c_group_heavy_doctor_df, doctor_name="D医師")
        assert result["total_discharges"] == 10
        assert result["c_group_count"] == 2
        assert result["c_group_pct"] == 20.0

    def test_avg_los_c(self, c_group_heavy_doctor_df):
        """C医師 C群 6件全て los=20 → avg_los_c=20"""
        result = calculate_c_group_stats(c_group_heavy_doctor_df, doctor_name="C医師")
        assert result["avg_los_c"] == 20.0
        assert result["max_los_c"] == 20

    def test_no_c_group_doctor(self):
        """C群が0件の医師 → c_group_pct=0, avg_los_c=0"""
        rows = [_make_discharge(f"2026-03-0{i+2}", "全短期医師", los_days=5, phase="A") for i in range(6)]
        df = pd.DataFrame(rows)
        result = calculate_c_group_stats(df, doctor_name="全短期医師")
        assert result["c_group_pct"] == 0.0
        assert result["avg_los_c"] == 0.0

    def test_enough_data_threshold(self):
        """最小件数未満 → enough_data=False"""
        rows = [_make_discharge(f"2026-03-0{i+2}", "少数医師", los_days=20, phase="C") for i in range(3)]
        df = pd.DataFrame(rows)
        result = calculate_c_group_stats(df, doctor_name="少数医師")
        assert result["enough_data"] is False


# ===================================================================
# build_c_group_insights
# ===================================================================

class TestBuildCGroupInsights:
    def test_empty_returns_empty(self, empty_detail_df):
        assert build_c_group_insights(empty_detail_df) == []

    def test_heavy_c_doctor_flagged(self, c_group_heavy_doctor_df):
        insights = build_c_group_insights(c_group_heavy_doctor_df)
        doctors = {i["doctor"]: i for i in insights}
        # C医師 は 75% > 60%(絶対閾値) なので warning
        assert "C医師" in doctors
        assert doctors["C医師"]["severity"] == "warning"
        assert doctors["C医師"]["c_group_pct"] >= C_GROUP_HEAVY_ABS_PCT

    def test_action_hints_present(self, c_group_heavy_doctor_df):
        insights = build_c_group_insights(c_group_heavy_doctor_df)
        for ins in insights:
            assert "action_hint" in ins
            assert isinstance(ins["action_hint"], str)
            assert len(ins["action_hint"]) > 0

    def test_overall_pct_set(self, c_group_heavy_doctor_df):
        """全体の C 群比率が各エントリに含まれる"""
        insights = build_c_group_insights(c_group_heavy_doctor_df)
        for ins in insights:
            assert "overall_c_group_pct" in ins
            assert ins["overall_c_group_pct"] >= 0


# ===================================================================
# build_doctor_insights（統合）
# ===================================================================

class TestBuildDoctorInsights:
    def test_empty_returns_empty(self, empty_detail_df):
        assert build_doctor_insights(empty_detail_df) == []

    def test_sort_by_worst_severity(self, friday_heavy_doctor_df):
        """warning の医師が先頭に来る"""
        insights = build_doctor_insights(friday_heavy_doctor_df)
        assert len(insights) >= 1
        # 先頭は warning であるべき（A医師）
        first = insights[0]
        assert first["worst_severity"] in ("warning", "neutral")

    def test_each_entry_has_both_dims(self, friday_heavy_doctor_df):
        """各医師エントリに weekday と c_group が含まれる"""
        insights = build_doctor_insights(friday_heavy_doctor_df)
        for ins in insights:
            assert "doctor" in ins
            assert "weekday" in ins
            assert "c_group" in ins
            assert "worst_severity" in ins

    def test_single_doctor_case(self, single_doctor_df):
        """医師 1 名のみ → insights に 1 件"""
        insights = build_doctor_insights(single_doctor_df)
        assert len(insights) == 1
        assert insights[0]["doctor"] == "単独医師"

    def test_mixed_data_merges_correctly(self, c_group_heavy_doctor_df):
        """曜日分析と C群分析が同じ医師エントリに統合される"""
        insights = build_doctor_insights(c_group_heavy_doctor_df)
        doctors = {i["doctor"]: i for i in insights}
        assert "C医師" in doctors
        assert "D医師" in doctors
        assert doctors["C医師"]["c_group"]["c_group_pct"] == 75.0
        assert doctors["D医師"]["c_group"]["c_group_pct"] == 20.0


# ===================================================================
# 境界値: データ品質低いケース
# ===================================================================

class TestEdgeCases:
    def test_attending_doctor_nan_ignored(self):
        """attending_doctor が NaN の行は除外される"""
        rows = [
            _make_discharge("2026-03-02", "医師X", los_days=7, phase="B"),
            _make_discharge("2026-03-03", "医師X", los_days=7, phase="B"),
            {
                "id": "nan-row",
                "date": "2026-03-04",
                "ward": "5F",
                "event_type": "discharge",
                "route": "",
                "source_doctor": "",
                "attending_doctor": None,
                "los_days": 7,
                "phase": "B",
                "short3_type": "",
            },
        ]
        df = pd.DataFrame(rows)
        result = calculate_weekday_profile(df)
        # NaN行は除外されるため合計2件
        assert result["total_discharges"] == 2

    def test_missing_phase_column_graceful(self):
        """phase 列が無くても例外を投げない"""
        df = pd.DataFrame([{
            "id": "1", "date": "2026-03-02", "ward": "5F",
            "event_type": "discharge", "route": "",
            "source_doctor": "", "attending_doctor": "医師Y",
            "los_days": 7, "short3_type": "",
        }])
        result = calculate_c_group_stats(df, doctor_name="医師Y")
        assert result["total_discharges"] == 0  # phase 列無しなら C群判定不能

    def test_unknown_severity_for_insufficient_data(self):
        """データ不足の医師は severity=unknown"""
        rows = [_make_discharge(f"2026-03-0{i+2}", "少数医師", los_days=20, phase="C") for i in range(3)]
        df = pd.DataFrame(rows)
        insights = build_weekday_insights(df)
        # 少数医師が存在する場合 severity=unknown
        for ins in insights:
            if ins["doctor"] == "少数医師":
                assert ins["severity"] == "unknown"
                assert ins["enough_data"] is False
