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
