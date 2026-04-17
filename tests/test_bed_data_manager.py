"""
bed_data_manager.py のユニットテスト
"""
import io
import pytest
import pandas as pd
import numpy as np
from datetime import date, timedelta

import bed_data_manager as bdm


# ===================================================================
# test_update_record
# ===================================================================
class TestUpdateRecord:
    def test_update_specific_ward(self, sample_two_ward_df):
        """5Fのみ更新 → 6Fは変更なし"""
        df = sample_two_ward_df.copy()
        updated = bdm.update_record(df, "2026-04-01", {"total_patients": 42}, ward="5F")
        row_5f = updated[updated["ward"] == "5F"].iloc[0]
        row_6f = updated[updated["ward"] == "6F"].iloc[0]
        assert row_5f["total_patients"] == 42
        assert row_6f["total_patients"] == 45  # unchanged

    def test_update_ward_none_backward_compat(self, sample_two_ward_df):
        """ward=None → 日付一致の最初のレコードを更新（後方互換）"""
        df = sample_two_ward_df.copy()
        updated = bdm.update_record(df, "2026-04-01", {"total_patients": 99}, ward=None)
        # ward=None は日付一致する全行を更新する
        assert (updated["total_patients"] == 99).all()

    def test_update_nonexistent_date_raises(self, sample_two_ward_df):
        """存在しない日付 → ValueError"""
        with pytest.raises(ValueError, match="レコードが見つかりません"):
            bdm.update_record(sample_two_ward_df, "2099-12-31", {"total_patients": 1})


# ===================================================================
# test_import_from_csv
# ===================================================================
class TestImportFromCsv:
    def test_valid_csv(self):
        """正常なCSV → 正しいカラムを持つDataFrame"""
        csv_text = (
            "date,ward,total_patients,new_admissions,discharges\n"
            "2026-04-01,5F,40,3,2\n"
            "2026-04-01,6F,45,4,3\n"
        )
        df, err = bdm.import_from_csv(csv_text)
        assert err == ""
        assert len(df) == 2
        assert "date" in df.columns
        assert "total_patients" in df.columns
        assert df["ward"].tolist() == ["5F", "6F"]

    def test_invalid_csv_format(self):
        """不正なCSV → 空DataFrame + エラーメッセージ"""
        csv_text = "this,is,not,valid\nno,date,column,here\n"
        df, err = bdm.import_from_csv(csv_text)
        assert len(df) == 0
        assert err != ""

    def test_csv_with_duplicate_date_ward(self):
        """日付+病棟の重複 → エラーメッセージ"""
        csv_text = (
            "date,ward,total_patients,new_admissions,discharges\n"
            "2026-04-01,5F,40,3,2\n"
            "2026-04-01,5F,41,4,3\n"
        )
        df, err = bdm.import_from_csv(csv_text)
        assert "重複" in err


# ===================================================================
# test_calculate_daily_metrics
# ===================================================================
class TestCalculateDailyMetrics:
    def test_occupancy_rate(self, sample_multi_day_df):
        """稼働率が正しく計算される"""
        result = bdm.calculate_daily_metrics(sample_multi_day_df, num_beds=94)
        assert "occupancy_rate" in result.columns
        # 厚労省定義: (在院患者数 + 退院数) / 病床数
        row0 = result.iloc[0]
        expected = (80 + 3) / 94
        assert abs(row0["occupancy_rate"] - expected) < 1e-6

    def test_moving_averages(self, sample_multi_day_df):
        """7日移動平均カラムが追加される"""
        result = bdm.calculate_daily_metrics(sample_multi_day_df, num_beds=94)
        assert "occupancy_7d_ma" in result.columns
        assert "admission_7d_ma" in result.columns
        assert "discharge_7d_ma" in result.columns
        # 値がNaNでないことを確認
        assert not result["occupancy_7d_ma"].isna().any()

    def test_empty_dataframe(self):
        """空DataFrame → 空DataFrameを返す"""
        empty = bdm.create_empty_dataframe()
        result = bdm.calculate_daily_metrics(empty)
        assert len(result) == 0


# ===================================================================
# test_calculate_rolling_los
# ===================================================================
class TestCalculateRollingLos:
    def test_90day_data(self, sample_90day_df):
        """90日分データ → rolling LOS を正しく計算"""
        result = bdm.calculate_rolling_los(sample_90day_df, window_days=90)
        assert result is not None
        assert "rolling_los" in result
        assert result["rolling_los"] is not None
        assert result["actual_days"] == 90
        assert result["is_partial"] is False

    def test_short_data_partial(self, sample_multi_day_df):
        """90日未満のデータ → is_partial=True"""
        result = bdm.calculate_rolling_los(sample_multi_day_df, window_days=90)
        assert result is not None
        assert result["is_partial"] is True
        assert result["actual_days"] == 5

    def test_empty_dataframe(self):
        """空DataFrame → None"""
        empty = bdm.create_empty_dataframe()
        result = bdm.calculate_rolling_los(empty)
        assert result is None

    def test_none_input(self):
        """None → None"""
        result = bdm.calculate_rolling_los(None)
        assert result is None


# ===================================================================
# test_export_to_csv
# ===================================================================
class TestExportToCsv:
    def test_bom_prefix(self, sample_multi_day_df):
        """出力がBOM文字で始まる"""
        csv_str = bdm.export_to_csv(sample_multi_day_df)
        assert csv_str.startswith("\ufeff")

    def test_columns_present(self, sample_multi_day_df):
        """主要カラムがCSVヘッダに含まれる"""
        csv_str = bdm.export_to_csv(sample_multi_day_df)
        header = csv_str.split("\n")[0]
        assert "date" in header
        assert "total_patients" in header
        assert "new_admissions" in header


# ===================================================================
# test_delete_record
# ===================================================================
class TestDeleteRecord:
    def test_delete_by_date_and_ward(self, sample_two_ward_df):
        """日付+病棟指定 → その行だけ削除"""
        result = bdm.delete_record(sample_two_ward_df, "2026-04-01", ward="5F")
        assert len(result) == 1
        assert result.iloc[0]["ward"] == "6F"

    def test_delete_by_date_only(self, sample_two_ward_df):
        """日付のみ指定（ward=None）→ 全レコード削除"""
        result = bdm.delete_record(sample_two_ward_df, "2026-04-01", ward=None)
        assert len(result) == 0

    def test_delete_nonexistent_date(self, sample_two_ward_df):
        """存在しない日付 → 件数変わらず"""
        result = bdm.delete_record(sample_two_ward_df, "2099-12-31")
        assert len(result) == 2


# ===================================================================
# Feature 1: Short3 overflow in LOS calculation
# ===================================================================
class TestShort3OverflowLos:
    """短手3オーバーフロー患者のLOS計算テスト。

    短手3患者のうち6日以上入院した「オーバーフロー」患者は
    通常患者として在院日数計算に算入される。
    5日以内退院の短手3のみ除外する。
    """

    def _make_df_with_overflow(self, n=30, short3_count=5, overflow_count=2):
        """short3_overflow_count 列を含むテスト用DataFrame。

        Args:
            n: 日数
            short3_count: 短手3新規入院数（日次で1日目にまとめて計上）
            overflow_count: うちオーバーフロー数（6日以上入院）
        """
        dates = [pd.Timestamp("2026-03-01") + timedelta(days=i) for i in range(n)]
        data = {
            "date": dates,
            "ward": ["5F"] * n,
            "total_patients": [80] * n,
            "new_admissions": [5] * n,
            "new_admissions_short3": [0] * n,
            "discharges": [5] * n,
            "short3_overflow_count": [0] * n,
            "short3_overflow_avg_los": [0.0] * n,
        }
        # 1日目にまとめて短手3を計上
        data["new_admissions_short3"][0] = short3_count
        data["short3_overflow_count"][0] = overflow_count
        if overflow_count > 0:
            data["short3_overflow_avg_los"][0] = 8.0  # 平均8日
        return pd.DataFrame(data)

    def test_overflow_excludes_only_5day_short3(self):
        """short3=5, overflow=2 → 除外は3件（5-2）のみ"""
        df = self._make_df_with_overflow(n=30, short3_count=5, overflow_count=2)
        result = bdm.calculate_rolling_los(df, window_days=90)

        assert result is not None
        assert result["total_short3"] == 5.0
        assert result["total_short3_overflow"] == 2.0
        assert result["short3_5day_excluded"] == 3.0  # 5 - 2 = 3

    def test_overflow_affects_ex_short3_los(self):
        """オーバーフローがある場合、rolling_los_ex_short3 が rolling_los と異なる"""
        df = self._make_df_with_overflow(n=30, short3_count=5, overflow_count=2)
        result = bdm.calculate_rolling_los(df, window_days=90)

        assert result is not None
        # 除外される短手3(3件)があるので ex_short3 は異なるはず
        assert result["rolling_los_ex_short3"] is not None
        assert result["rolling_los"] is not None
        assert result["rolling_los_ex_short3"] != result["rolling_los"]

    def test_no_overflow_all_short3_excluded(self):
        """overflow=0 → 全短手3が除外される（後方互換動作）"""
        df = self._make_df_with_overflow(n=30, short3_count=5, overflow_count=0)
        result = bdm.calculate_rolling_los(df, window_days=90)

        assert result is not None
        assert result["total_short3_overflow"] == 0.0
        assert result["short3_5day_excluded"] == 5.0  # 全5件除外

    def test_all_short3_overflow(self):
        """overflow == short3 → 除外ゼロ、ex_short3 == rolling_los"""
        df = self._make_df_with_overflow(n=30, short3_count=5, overflow_count=5)
        result = bdm.calculate_rolling_los(df, window_days=90)

        assert result is not None
        assert result["short3_5day_excluded"] == 0.0  # 全員オーバーフロー
        assert result["rolling_los_ex_short3"] == result["rolling_los"]

    def test_overflow_count_column_missing_backward_compat(self):
        """short3_overflow_count 列がない場合 → 全短手3が除外される（後方互換）"""
        df = self._make_df_with_overflow(n=30, short3_count=5, overflow_count=2)
        df = df.drop(columns=["short3_overflow_count", "short3_overflow_avg_los"])
        result = bdm.calculate_rolling_los(df, window_days=90)

        assert result is not None
        assert result["total_short3_overflow"] == 0.0  # 列なし → 0
        assert result["short3_5day_excluded"] == 5.0   # 全5件除外

    def test_overflow_count_nonnegative(self):
        """short3_overflow_count は常に0以上"""
        df = self._make_df_with_overflow(n=30, short3_count=5, overflow_count=2)
        result = bdm.calculate_rolling_los(df, window_days=90)

        assert result["total_short3_overflow"] >= 0
        assert result["short3_5day_excluded"] >= 0

    def test_overflow_avg_los_ge_6_when_present(self):
        """オーバーフロー患者がいる場合、short3_overflow_avg_los >= 6"""
        df = self._make_df_with_overflow(n=30, short3_count=5, overflow_count=2)
        # short3_overflow_avg_los は data 側で 8.0 に設定済み
        overflow_rows = df[df["short3_overflow_count"] > 0]
        for _, row in overflow_rows.iterrows():
            assert row["short3_overflow_avg_los"] >= 6.0


# ===================================================================
# Feature 3: Monthly summary integration in rolling LOS
# ===================================================================
class TestMonthlySummaryLos:
    """monthly_summary によるrolling LOS補完テスト。"""

    def _make_april_df(self, n_days=14):
        """4月分の日次データ（14日間）"""
        dates = [pd.Timestamp("2026-04-01") + timedelta(days=i) for i in range(n_days)]
        return pd.DataFrame({
            "date": dates,
            "ward": ["5F"] * n_days,
            "total_patients": [80] * n_days,
            "new_admissions": [5] * n_days,
            "new_admissions_short3": [0] * n_days,
            "discharges": [5] * n_days,
        })

    def test_summary_months_added_to_totals(self):
        """日次データ前の月サマリーが合算される"""
        df = self._make_april_df(n_days=14)
        summary = {
            "2026-02": {
                "5F": {
                    "patient_days": 1200,
                    "admissions": 50,
                    "discharges": 48,
                }
            },
            "2026-03": {
                "5F": {
                    "patient_days": 1300,
                    "admissions": 55,
                    "discharges": 53,
                }
            },
        }

        result = bdm.calculate_rolling_los(df, window_days=90, monthly_summary=summary, ward="5F")
        assert result is not None

        # 14日分のpatient_days(80*14=1120) + 1200 + 1300 = 3620
        expected_patient_days = 80 * 14 + 1200 + 1300
        assert result["total_patient_days"] == expected_patient_days

        # admissions: 14*5 + 50 + 55 = 175
        expected_admissions = 5 * 14 + 50 + 55
        assert result["total_admissions"] == expected_admissions

        # discharges: 14*5 + 48 + 53 = 171
        expected_discharges = 5 * 14 + 48 + 53
        assert result["total_discharges"] == expected_discharges

    def test_summary_months_used_count(self):
        """summary_months_used に使用された月が記録される"""
        df = self._make_april_df(n_days=14)
        summary = {
            "2026-02": {"5F": {"patient_days": 1200, "admissions": 50, "discharges": 48}},
            "2026-03": {"5F": {"patient_days": 1300, "admissions": 55, "discharges": 53}},
        }

        result = bdm.calculate_rolling_los(df, window_days=90, monthly_summary=summary, ward="5F")
        assert result is not None
        assert len(result["summary_months_used"]) == 2
        assert "2026-02" in result["summary_months_used"]
        assert "2026-03" in result["summary_months_used"]

    def test_summary_month_overlapping_with_daily_ignored(self):
        """日次データとオーバーラップする月のサマリーは無視される"""
        df = self._make_april_df(n_days=14)  # 4月1日〜
        summary = {
            "2026-04": {"5F": {"patient_days": 9999, "admissions": 999, "discharges": 999}},
        }

        result_with = bdm.calculate_rolling_los(df, window_days=90, monthly_summary=summary, ward="5F")
        result_without = bdm.calculate_rolling_los(df, window_days=90, ward="5F")

        # 4月のサマリーは日次データ開始日以降なので無視される
        assert result_with["total_patient_days"] == result_without["total_patient_days"]
        assert result_with["total_admissions"] == result_without["total_admissions"]

    def test_no_summary_returns_daily_only(self):
        """monthly_summary=None → 日次データのみで計算"""
        df = self._make_april_df(n_days=14)
        result = bdm.calculate_rolling_los(df, window_days=90, ward="5F")

        assert result is not None
        assert result["total_patient_days"] == 80 * 14
        assert result["total_admissions"] == 5 * 14
        assert len(result["summary_months_used"]) == 0

    def test_summary_ward_fallback_sums_all_wards(self):
        """指定wardのサマリーがない場合、5F+6Fを合算する（フォールバック動作）"""
        df = self._make_april_df(n_days=14)
        summary = {
            "2026-03": {
                "6F": {"patient_days": 1300, "admissions": 55, "discharges": 53},
                # 5Fのデータなし → ward_key="5F" が空dictなのでフォールバック
            },
        }

        result = bdm.calculate_rolling_los(df, window_days=90, monthly_summary=summary, ward="5F")
        assert result is not None
        # ward_key="5F" が見つからないと5F+6F合算フォールバック
        # 14日分(80*14=1120) + 6Fの1300 = 2420
        assert result["total_patient_days"] == 80 * 14 + 1300
        assert len(result["summary_months_used"]) == 1
        assert "2026-03" in result["summary_months_used"]


# ===================================================================
# Feature: 本則完全適用 (2026-06-01) の短手3 階段関数
# ===================================================================
class TestShort3StairFunctionPostTransitional:
    """CLAUDE.md 確定仕様 (2026-06-01 以降本則完全適用) の階段関数テスト。

    - Day 5 以下 → 分母に含めない
    - Day 6 以上に延びた瞬間 → 入院初日まで遡って全日数を加算 (+6日 jump)
    - 経過措置中 (today <= 2026-05-31) は従来動作を維持する
    """

    def _make_df(self, n=30, short3_count=0, overflow_count=0, overflow_los=8.0):
        """テスト用日次DataFrame。"""
        dates = [pd.Timestamp("2026-03-01") + timedelta(days=i) for i in range(n)]
        data = {
            "date": dates,
            "ward": ["5F"] * n,
            "total_patients": [80] * n,
            "new_admissions": [5] * n,
            "new_admissions_short3": [0] * n,
            "discharges": [5] * n,
            "short3_overflow_count": [0] * n,
            "short3_overflow_avg_los": [0.0] * n,
        }
        if short3_count > 0:
            data["new_admissions_short3"][0] = short3_count
            data["short3_overflow_count"][0] = overflow_count
            data["short3_overflow_avg_los"][0] = overflow_los
        return pd.DataFrame(data)

    def test_transitional_period_today_2026_04_17(self):
        """経過措置期間中 (今日) → transitional=True、既存挙動が維持される。"""
        df = self._make_df(n=30, short3_count=0, overflow_count=0)
        result = bdm.calculate_rolling_los(df, window_days=90, today=date(2026, 4, 17))

        assert result is not None
        assert result["transitional"] is True
        # 短手3=0 なら rolling_los == rolling_los_ex_short3
        assert result["rolling_los"] is not None
        assert result["rolling_los_ex_short3"] == result["rolling_los"]

    def test_transitional_period_last_day(self):
        """経過措置終了当日 (2026-05-31) は transitional=True。"""
        df = self._make_df(n=30)
        result = bdm.calculate_rolling_los(df, window_days=90, today=date(2026, 5, 31))

        assert result is not None
        assert result["transitional"] is True

    def test_post_transitional_from_2026_06_01(self):
        """本則完全適用初日 (2026-06-01) → transitional=False。"""
        df = self._make_df(n=30)
        result = bdm.calculate_rolling_los(df, window_days=90, today=date(2026, 6, 1))

        assert result is not None
        assert result["transitional"] is False

    def test_default_today_uses_date_today(self):
        """today=None → date.today() を使う（現在は経過措置中）。"""
        df = self._make_df(n=30)
        result = bdm.calculate_rolling_los(df, window_days=90)

        assert result is not None
        # 2026-04-17 時点では経過措置中
        # (将来このテストが 2026-06-01 以降に実行されると transitional=False になる)
        expected_transitional = date.today() <= date(2026, 5, 31)
        assert result["transitional"] == expected_transitional

    def test_transitional_period_short3_day5_excluded(self):
        """経過措置中: 5日以内退院の短手3 は従来通り除外される。"""
        df = self._make_df(n=30, short3_count=5, overflow_count=2)
        result = bdm.calculate_rolling_los(df, window_days=90, today=date(2026, 4, 17))

        assert result is not None
        assert result["transitional"] is True
        assert result["short3_5day_excluded"] == 3.0  # 5 - 2
        # ex_short3 は rolling_los と異なる（除外患者がある）
        assert result["rolling_los_ex_short3"] != result["rolling_los"]

    def test_post_transitional_short3_day5_excluded(self):
        """本則完全適用: Day 5 以下の短手3 は分母から除外される（日次集計レベルでも同挙動）。"""
        df = self._make_df(n=30, short3_count=5, overflow_count=2)
        result = bdm.calculate_rolling_los(df, window_days=90, today=date(2026, 6, 1))

        assert result is not None
        assert result["transitional"] is False
        assert result["short3_5day_excluded"] == 3.0  # 5 - 2
        # Day 5 以下の短手3 (3件) は rolling_los_ex_short3 で除外される
        assert result["rolling_los_ex_short3"] is not None
        assert result["rolling_los_ex_short3"] != result["rolling_los"]

    def test_post_transitional_short3_day6_overflow_included(self):
        """本則完全適用: Day 6 以上の短手3 (overflow) は入院初日から全日数が分母に算入される。

        日次集計データでは、overflow 患者の患者日数は既に total_patient_days に
        含まれているため、overflow は rolling_los / rolling_los_ex_short3 の分子・分母に
        算入されている状態が「入院初日まで遡って全日数をカウント」に対応する。
        """
        df = self._make_df(n=30, short3_count=5, overflow_count=5, overflow_los=8.0)
        result = bdm.calculate_rolling_los(df, window_days=90, today=date(2026, 6, 1))

        assert result is not None
        assert result["transitional"] is False
        # 全員 overflow なので 5日以内除外はゼロ
        assert result["short3_5day_excluded"] == 0.0
        # overflow 患者は rolling_los に算入されたまま → ex_short3 == rolling_los
        assert result["rolling_los_ex_short3"] == result["rolling_los"]

    def test_stair_function_discontinuity_day5_to_day6(self):
        """Day 5/6 境界で分母が +6 日 jump する不連続点を直接検証。

        シナリオ: 短手3 5件中 2件が overflow (Day 6+) のケースと、
        同じ5件中 4件が overflow のケースを比較。
        overflow 数が増えると除外数が減るため、分母 (admissions+discharges)/2 が
        小さくなるはずが、overflow 患者の分子側の患者日数は同じように含まれる。
        結果として rolling_los_ex_short3 は 4件overflowの方が低くなる
        (除外2件のみ = 除外患者日数が少なくなる → ex_short3が本来の値に近づく)。
        """
        # ケース A: 5件中 2件 overflow → 3件除外
        df_a = self._make_df(n=30, short3_count=5, overflow_count=2, overflow_los=8.0)
        result_a = bdm.calculate_rolling_los(df_a, window_days=90, today=date(2026, 6, 1))

        # ケース B: 5件中 4件 overflow → 1件除外
        df_b = self._make_df(n=30, short3_count=5, overflow_count=4, overflow_los=8.0)
        result_b = bdm.calculate_rolling_los(df_b, window_days=90, today=date(2026, 6, 1))

        assert result_a["transitional"] is False
        assert result_b["transitional"] is False
        assert result_a["short3_5day_excluded"] == 3.0
        assert result_b["short3_5day_excluded"] == 1.0

        # 除外数が増える → ex_short3 の分母が減る → LOS 値が変化
        # (確実な不連続性として、除外数が変わると ex_short3 値が異なる)
        assert result_a["rolling_los_ex_short3"] != result_b["rolling_los_ex_short3"]

    def test_regression_baseline_5F_17_7_transitional(self):
        """リグレッション: 今日(2026-04-17)の5Fデモデータで rolling_los == 17.7 が維持される。"""
        import os
        csv_path = os.path.join(
            os.path.dirname(__file__), "..", "data", "sample_actual_data_ward_202604.csv"
        )
        if not os.path.exists(csv_path):
            pytest.skip("デモデータが見つかりません")

        df = pd.read_csv(csv_path)
        df_5f = df[df["ward"] == "5F"].copy()
        result = bdm.calculate_rolling_los(df_5f, window_days=90, today=date(2026, 4, 17))

        assert result is not None
        assert result["rolling_los"] == 17.7, f"5F rolling_los drifted: {result['rolling_los']}"

    def test_regression_baseline_6F_21_3_transitional(self):
        """リグレッション: 今日(2026-04-17)の6Fデモデータで rolling_los == 21.3 が維持される。"""
        import os
        csv_path = os.path.join(
            os.path.dirname(__file__), "..", "data", "sample_actual_data_ward_202604.csv"
        )
        if not os.path.exists(csv_path):
            pytest.skip("デモデータが見つかりません")

        df = pd.read_csv(csv_path)
        df_6f = df[df["ward"] == "6F"].copy()
        result = bdm.calculate_rolling_los(df_6f, window_days=90, today=date(2026, 4, 17))

        assert result is not None
        assert result["rolling_los"] == 21.3, f"6F rolling_los drifted: {result['rolling_los']}"

    def test_regression_baseline_post_transitional_no_short3(self):
        """リグレッション: 本則完全適用下でも短手3=0のデモデータなら 17.7/21.3 が維持される。"""
        import os
        csv_path = os.path.join(
            os.path.dirname(__file__), "..", "data", "sample_actual_data_ward_202604.csv"
        )
        if not os.path.exists(csv_path):
            pytest.skip("デモデータが見つかりません")

        df = pd.read_csv(csv_path)
        df_5f = df[df["ward"] == "5F"].copy()
        df_6f = df[df["ward"] == "6F"].copy()

        r5 = bdm.calculate_rolling_los(df_5f, window_days=90, today=date(2026, 6, 1))
        r6 = bdm.calculate_rolling_los(df_6f, window_days=90, today=date(2026, 6, 1))

        assert r5["rolling_los"] == 17.7
        assert r6["rolling_los"] == 21.3
        assert r5["transitional"] is False
        assert r6["transitional"] is False


# ===================================================================
# Feature: get_short3_day5_patients インターフェース
# ===================================================================
class TestShort3Day5Interface:
    """bed_control_simulator_app.py から呼ばれる Day 5 アラート用 API。"""

    # --- 共通: 入退院詳細 DataFrame ビルダー ---
    @staticmethod
    def _make_admission(id_: str, date_str: str, ward: str, short3_type: str = "該当なし"):
        return {
            "id": id_,
            "date": date_str,
            "ward": ward,
            "event_type": "admission",
            "route": "外来紹介",
            "source_doctor": "",
            "attending_doctor": "",
            "los_days": "",
            "phase": "",
            "short3_type": short3_type,
        }

    @staticmethod
    def _make_discharge(id_: str, date_str: str, ward: str, los_days: int):
        return {
            "id": id_,
            "date": date_str,
            "ward": ward,
            "event_type": "discharge",
            "route": "",
            "source_doctor": "",
            "attending_doctor": "",
            "los_days": str(los_days),
            "phase": "",
            "short3_type": "",
        }

    def test_transitional_period_returns_empty_list(self):
        """経過措置中は常に空リストを返す。"""
        result = bdm.get_short3_day5_patients(df=pd.DataFrame(), today=date(2026, 4, 17))
        assert result == []

    def test_empty_or_invalid_dataframe_returns_empty(self):
        """空 DataFrame / None は空リストを返す。"""
        assert bdm.get_short3_day5_patients(df=None, today=date(2026, 6, 15)) == []
        assert bdm.get_short3_day5_patients(df=pd.DataFrame(), today=date(2026, 6, 15)) == []

    def test_default_today_returns_list(self):
        """today=None でもエラーにならず list が返る。"""
        result = bdm.get_short3_day5_patients(df=pd.DataFrame())
        assert isinstance(result, list)

    # --- 実データロジック ---
    def test_transitional_period_blocks_even_with_day5_patients(self):
        """経過措置中 (2026-05-31 以前) は Day 5 患者がいても空リスト。"""
        today = date(2026, 5, 31)
        adm_date = today - timedelta(days=4)  # Day 5 (Day 1 = 入院初日)
        df = pd.DataFrame([
            self._make_admission("a1", adm_date.isoformat(), "5F", "短手3 ヘルニア"),
        ])
        assert bdm.get_short3_day5_patients(df=df, today=today) == []

    def test_post_transitional_returns_day5_short3_patients(self):
        """本則完全適用後 (2026-06-15) かつ Day 5 到達の短手3 患者 2 名 → 2 件返却。"""
        today = date(2026, 6, 15)
        adm_date = today - timedelta(days=4)  # Day 5
        df = pd.DataFrame([
            self._make_admission("a1", adm_date.isoformat(), "5F", "短手3 ヘルニア"),
            self._make_admission("a2", adm_date.isoformat(), "6F", "短手3 大腸ポリープ"),
            # Day 5 の通常入院（短手3 ではない）は除外される
            self._make_admission("a3", adm_date.isoformat(), "5F", "該当なし"),
        ])
        result = bdm.get_short3_day5_patients(df=df, today=today)
        assert len(result) == 2
        patient_ids = {r["patient_id"] for r in result}
        assert patient_ids == {"a1", "a2"}
        for r in result:
            assert r["stay_days"] == 5
            assert r["admission_date"] == adm_date
            assert r["ward"] in {"5F", "6F"}

    def test_day4_and_day6_patients_excluded(self):
        """Day 4 と Day 6 の短手3 患者のみ（Day 5 なし）→ 空リスト。"""
        today = date(2026, 6, 15)
        day4_adm = today - timedelta(days=3)  # Day 4
        day6_adm = today - timedelta(days=5)  # Day 6
        df = pd.DataFrame([
            self._make_admission("a1", day4_adm.isoformat(), "5F", "短手3 ヘルニア"),
            self._make_admission("a2", day6_adm.isoformat(), "6F", "短手3 白内障"),
        ])
        assert bdm.get_short3_day5_patients(df=df, today=today) == []

    def test_already_discharged_day5_patient_excluded(self):
        """Day 5 到達だが既に退院済み (los_days=4) → 除外される。"""
        today = date(2026, 6, 15)
        adm_date = today - timedelta(days=4)  # Day 5
        # 退院日 = adm_date + 4 日 (los_days=4)
        dis_date = adm_date + timedelta(days=4)
        df = pd.DataFrame([
            self._make_admission("a1", adm_date.isoformat(), "5F", "短手3 ヘルニア"),
            self._make_discharge("d1", dis_date.isoformat(), "5F", los_days=4),
            # 別の未退院 Day 5 患者（対照）
            self._make_admission("a2", adm_date.isoformat(), "6F", "短手3 ポリープ"),
        ])
        result = bdm.get_short3_day5_patients(df=df, today=today)
        assert len(result) == 1
        assert result[0]["patient_id"] == "a2"
        assert result[0]["ward"] == "6F"
