"""
bed_data_manager.py のユニットテスト
"""
import io
import pytest
import pandas as pd
import numpy as np
from datetime import timedelta

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
