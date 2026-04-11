"""
db_manager.py のユニットテスト

SQLiteデータベースの保存・読み込み・クリア操作をテストする。
各テストは一時ファイルを使用し、本番DBには影響しない。
"""

import os
import tempfile
import pytest
import pandas as pd
import numpy as np
from datetime import datetime

# テスト対象モジュール
from db_manager import (
    get_connection,
    save_daily_records,
    load_daily_records,
    save_abc_state,
    load_abc_state,
    clear_all_data,
)


@pytest.fixture
def tmp_db(tmp_path):
    """一時DBファイルパスを返す fixture"""
    return str(tmp_path / "test_bed_control.db")


@pytest.fixture
def sample_daily_df():
    """テスト用の日次レコード DataFrame"""
    return pd.DataFrame({
        "date": pd.to_datetime(["2026-04-01", "2026-04-02"]),
        "ward": ["all", "all"],
        "total_patients": [80, 82],
        "new_admissions": [5, 6],
        "new_admissions_short3": [0, 1],
        "discharges": [3, 4],
        "discharge_a": [1, 2],
        "discharge_b": [1, 1],
        "discharge_c": [1, 1],
        "discharge_los_list": ["3,10,18", "2,8"],
        "phase_a_count": [15, 16],
        "phase_b_count": [30, 31],
        "phase_c_count": [35, 35],
        "avg_los": [12.5, 13.0],
        "notes": ["", "test note"],
        "data_source": ["manual", "manual"],
    })


# ---------------------------------------------------------------
# save_daily_records → load_daily_records ラウンドトリップ
# ---------------------------------------------------------------


class TestSaveDailyRecords:
    """save_daily_records のテスト"""

    def test_save_and_load_roundtrip(self, tmp_db, sample_daily_df):
        """保存したDataFrameを読み込み、データが一致することを確認"""
        result = save_daily_records(sample_daily_df, db_path=tmp_db)
        assert result is True

        loaded = load_daily_records(db_path=tmp_db)
        assert len(loaded) == 2

        # 日付の一致
        loaded_dates = sorted(loaded["date"].dt.strftime("%Y-%m-%d").tolist())
        assert loaded_dates == ["2026-04-01", "2026-04-02"]

        # 数値カラムの一致
        row1 = loaded[loaded["date"] == pd.Timestamp("2026-04-01")].iloc[0]
        assert int(row1["total_patients"]) == 80
        assert int(row1["new_admissions"]) == 5
        assert int(row1["discharges"]) == 3
        assert int(row1["discharge_a"]) == 1
        assert int(row1["discharge_b"]) == 1
        assert int(row1["discharge_c"]) == 1
        assert row1["discharge_los_list"] == "3,10,18"

    def test_save_invalid_data_returns_false(self, tmp_db):
        """非DataFrameを渡すと False を返し、部分保存されない"""
        result = save_daily_records("not a dataframe", db_path=tmp_db)
        assert result is False

        # DBにデータが残っていないことを確認
        loaded = load_daily_records(db_path=tmp_db)
        assert loaded.empty

    def test_save_overwrite_existing(self, tmp_db, sample_daily_df):
        """同じ日付・wardのデータを再保存すると上書きされる（REPLACE INTO）"""
        save_daily_records(sample_daily_df, db_path=tmp_db)

        # total_patients を変更して再保存
        df_updated = sample_daily_df.copy()
        df_updated.loc[0, "total_patients"] = 99
        save_daily_records(df_updated, db_path=tmp_db)

        loaded = load_daily_records(db_path=tmp_db)
        assert len(loaded) == 2  # 行数は増えない
        row1 = loaded[loaded["date"] == pd.Timestamp("2026-04-01")].iloc[0]
        assert int(row1["total_patients"]) == 99


# ---------------------------------------------------------------
# load_daily_records: 空DBからの読み込み
# ---------------------------------------------------------------


class TestLoadDailyRecords:
    """load_daily_records のテスト"""

    def test_load_from_empty_db(self, tmp_db):
        """空のDBから読み込むと空のDataFrameが返る"""
        loaded = load_daily_records(db_path=tmp_db)
        assert isinstance(loaded, pd.DataFrame)
        assert loaded.empty
        # 期待カラムが存在すること
        assert "date" in loaded.columns
        assert "ward" in loaded.columns
        assert "total_patients" in loaded.columns


# ---------------------------------------------------------------
# save_abc_state / load_abc_state ラウンドトリップ
# ---------------------------------------------------------------


class TestAbcState:
    """ABC状態の保存・読み込みテスト"""

    def test_roundtrip(self, tmp_db):
        """保存した ABC 状態を正しく読み戻せる"""
        state = {"A": 15.0, "B": 30.0, "C": 35.0}
        result = save_abc_state(state, db_path=tmp_db)
        assert result is True

        loaded = load_abc_state(db_path=tmp_db)
        assert loaded is not None
        assert loaded["A"] == 15.0
        assert loaded["B"] == 30.0
        assert loaded["C"] == 35.0

    def test_load_from_empty_returns_none(self, tmp_db):
        """データがない場合は None を返す"""
        loaded = load_abc_state(db_path=tmp_db)
        assert loaded is None

    def test_overwrite(self, tmp_db):
        """再保存すると上書きされる"""
        save_abc_state({"A": 10, "B": 20, "C": 30}, db_path=tmp_db)
        save_abc_state({"A": 99, "B": 88, "C": 77}, db_path=tmp_db)

        loaded = load_abc_state(db_path=tmp_db)
        assert loaded["A"] == 99.0
        assert loaded["B"] == 88.0
        assert loaded["C"] == 77.0


# ---------------------------------------------------------------
# clear_all_data
# ---------------------------------------------------------------


class TestClearAllData:
    """clear_all_data のテスト"""

    def test_clear_removes_all(self, tmp_db, sample_daily_df):
        """データ保存後にclearすると全テーブルが空になる"""
        save_daily_records(sample_daily_df, db_path=tmp_db)
        save_abc_state({"A": 10, "B": 20, "C": 30}, db_path=tmp_db)

        # クリア前にデータが存在することを確認
        assert not load_daily_records(db_path=tmp_db).empty
        assert load_abc_state(db_path=tmp_db) is not None

        # クリア実行
        clear_all_data(db_path=tmp_db)

        # クリア後にデータが空であることを確認
        assert load_daily_records(db_path=tmp_db).empty
        assert load_abc_state(db_path=tmp_db) is None
