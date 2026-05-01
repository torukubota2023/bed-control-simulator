"""data_purity_guard のテスト."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from data_purity_guard import (
    ADMISSION_DETAILS_COLUMNS,
    REAL_DOCTOR_CODES,
    archive_demo_data,
    create_empty_schema,
    describe_data_kind,
    detect_data_kind,
    filter_real_only,
    find_demo_rows,
    find_real_rows,
    initialize_for_production,
    is_demo_doctor,
    is_real_doctor,
    severity_for_kind,
)


# ---------------------------------------------------------------------------
# 単純判定関数
# ---------------------------------------------------------------------------

class TestIsDemoDoctor:
    def test_a_through_j_are_demo(self):
        for letter in "ABCDEFGHIJ":
            assert is_demo_doctor(f"{letter}医師") is True

    def test_real_codes_are_not_demo(self):
        for code in ("KJJ", "HAYT", "OKUK", "TERUH"):
            assert is_demo_doctor(code) is False

    def test_invalid_inputs(self):
        assert is_demo_doctor(None) is False
        assert is_demo_doctor("") is False
        assert is_demo_doctor(123) is False
        assert is_demo_doctor("Z医師") is False  # K-Z は対象外
        assert is_demo_doctor("AA医師") is False
        assert is_demo_doctor("A医師さん") is False


class TestIsRealDoctor:
    def test_known_codes(self):
        for code in REAL_DOCTOR_CODES:
            assert is_real_doctor(code) is True

    def test_demo_names_are_not_real(self):
        assert is_real_doctor("A医師") is False
        assert is_real_doctor("J医師") is False

    def test_invalid_inputs(self):
        assert is_real_doctor(None) is False
        assert is_real_doctor("") is False
        assert is_real_doctor("XYZ") is False  # 未登録コード


# ---------------------------------------------------------------------------
# detect_data_kind
# ---------------------------------------------------------------------------

class TestDetectDataKind:
    def test_empty_dataframe(self):
        df = pd.DataFrame(columns=ADMISSION_DETAILS_COLUMNS)
        assert detect_data_kind(df) == "empty"

    def test_none(self):
        assert detect_data_kind(None) == "empty"  # type: ignore[arg-type]

    def test_demo_only(self):
        df = pd.DataFrame({
            "attending_doctor": ["A医師", "B医師", "C医師"],
            "source_doctor": ["A医師", "B医師", "C医師"],
        })
        assert detect_data_kind(df) == "demo"

    def test_real_only(self):
        df = pd.DataFrame({
            "attending_doctor": ["KJJ", "HAYT", "OKUK"],
            "source_doctor": ["KJJ", "HAYT", "OKUK"],
        })
        assert detect_data_kind(df) == "real"

    def test_mixed(self):
        df = pd.DataFrame({
            "attending_doctor": ["A医師", "KJJ", "B医師"],
            "source_doctor": ["A医師", "KJJ", "B医師"],
        })
        assert detect_data_kind(df) == "mixed"

    def test_only_unknown(self):
        df = pd.DataFrame({
            "attending_doctor": ["不明", "未設定"],
            "source_doctor": ["不明", "未設定"],
        })
        assert detect_data_kind(df) == "unknown"

    def test_real_with_unknown_only_returns_real(self):
        # 実医師コードがあれば優先して real 判定（unknown は無視）
        df = pd.DataFrame({
            "attending_doctor": ["KJJ", "不明"],
            "source_doctor": ["KJJ", "不明"],
        })
        assert detect_data_kind(df) == "real"

    def test_no_doctor_columns(self):
        df = pd.DataFrame({"date": ["2026-04-01"], "ward": ["5F"]})
        assert detect_data_kind(df) == "unknown"


# ---------------------------------------------------------------------------
# find_demo_rows / find_real_rows / filter_real_only
# ---------------------------------------------------------------------------

class TestFindRows:
    def test_find_demo_rows(self):
        df = pd.DataFrame({
            "attending_doctor": ["A医師", "KJJ", "B医師", "HAYT"],
            "source_doctor": ["A医師", "KJJ", "B医師", "HAYT"],
        })
        mask = find_demo_rows(df)
        assert mask.tolist() == [True, False, True, False]

    def test_find_real_rows(self):
        df = pd.DataFrame({
            "attending_doctor": ["A医師", "KJJ", "B医師", "HAYT"],
            "source_doctor": ["A医師", "KJJ", "B医師", "HAYT"],
        })
        mask = find_real_rows(df)
        assert mask.tolist() == [False, True, False, True]

    def test_filter_real_only_removes_demo(self):
        df = pd.DataFrame({
            "attending_doctor": ["A医師", "KJJ", "B医師", "HAYT"],
            "source_doctor": ["A医師", "KJJ", "B医師", "HAYT"],
            "los_days": [5, 7, 3, 9],
        })
        out = filter_real_only(df)
        assert len(out) == 2
        assert out["attending_doctor"].tolist() == ["KJJ", "HAYT"]


# ---------------------------------------------------------------------------
# archive_demo_data / create_empty_schema / initialize_for_production
# ---------------------------------------------------------------------------

class TestArchiveAndCreate:
    def test_archive_existing_csv(self, tmp_path):
        src = tmp_path / "details.csv"
        df = pd.DataFrame({
            "id": ["1"], "date": ["2026-04-01"], "ward": ["5F"],
            "event_type": ["admission"], "attending_doctor": ["A医師"],
        })
        df.to_csv(src, index=False)

        archive_dir = tmp_path / "archive"
        ts = datetime(2026, 5, 1, 14, 30, 0)
        out = archive_demo_data(src, archive_dir, label="demo", timestamp=ts)
        assert out.exists()
        assert "demo" in out.name
        assert "20260501_143000" in out.name

    def test_archive_missing_raises(self, tmp_path):
        src = tmp_path / "missing.csv"
        with pytest.raises(FileNotFoundError):
            archive_demo_data(src, tmp_path / "archive")

    def test_create_empty_schema(self, tmp_path):
        out = tmp_path / "details.csv"
        create_empty_schema(out)
        assert out.exists()
        df = pd.read_csv(out)
        assert list(df.columns) == ADMISSION_DETAILS_COLUMNS
        assert len(df) == 0

    def test_initialize_for_production_with_demo(self, tmp_path):
        src = tmp_path / "details.csv"
        archive_dir = tmp_path / "archive"
        df = pd.DataFrame({
            "id": ["1", "2"],
            "date": ["2026-04-01", "2026-04-02"],
            "ward": ["5F", "6F"],
            "event_type": ["admission", "discharge"],
            "attending_doctor": ["A医師", "B医師"],
            "source_doctor": ["A医師", "B医師"],
        })
        df.to_csv(src, index=False)

        ts = datetime(2026, 5, 1, 12, 0, 0)
        result = initialize_for_production(src, archive_dir, timestamp=ts)
        # 退避済
        assert result["archived_path"].exists()
        assert "demo" in result["archived_path"].name
        # 新スキーマ作成済
        assert result["created_path"].exists()
        new_df = pd.read_csv(result["created_path"])
        assert len(new_df) == 0
        # メタ
        assert result["previous_kind"] == "demo"
        assert result["row_count"] == 2

    def test_initialize_for_production_with_no_existing_file(self, tmp_path):
        src = tmp_path / "details.csv"  # 存在しない
        archive_dir = tmp_path / "archive"
        result = initialize_for_production(src, archive_dir)
        # 退避なし、空スキーマだけ作成
        assert result["archived_path"] is None
        assert result["created_path"].exists()
        assert result["previous_kind"] == "empty"
        assert result["row_count"] == 0

    def test_initialize_for_production_with_real_data_uses_backup_label(self, tmp_path):
        # 実データを含む CSV を初期化する場合は "backup" ラベルで退避
        src = tmp_path / "details.csv"
        archive_dir = tmp_path / "archive"
        df = pd.DataFrame({
            "id": ["1"],
            "date": ["2026-04-01"],
            "ward": ["5F"],
            "event_type": ["admission"],
            "attending_doctor": ["KJJ"],
            "source_doctor": ["KJJ"],
        })
        df.to_csv(src, index=False)

        result = initialize_for_production(src, archive_dir)
        assert result["previous_kind"] == "real"
        assert "backup" in result["archived_path"].name
        # 「demo」ラベルがついていないことを確認
        assert "_demo_" not in result["archived_path"].name


# ---------------------------------------------------------------------------
# describe / severity
# ---------------------------------------------------------------------------

class TestDescribe:
    def test_describe_data_kind_includes_emoji(self):
        assert "✅" in describe_data_kind("real")
        assert "⚠️" in describe_data_kind("demo")
        assert "🚨" in describe_data_kind("mixed")

    def test_severity_mapping(self):
        assert severity_for_kind("real") == "success"
        assert severity_for_kind("demo") == "warning"
        assert severity_for_kind("mixed") == "danger"
        assert severity_for_kind("empty") == "info"
