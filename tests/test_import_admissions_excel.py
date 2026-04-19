"""import_admissions_excel.py のテスト。

検証項目:
    - xlsx 読み取りが成功
    - 1,965 行が変換される
    - 病棟名変換 (4F / 5F / 6F のみ)
    - admission_type 変換 (scheduled / emergency / other)
    - age_code → age_years の境界値
    - CSV 出力スキーマが admission_details と互換 (OUTPUT_COLUMNS)
    - 欠損フィールドの default 値
    - dry-run で書き込みが発生しない
    - CLI の exit code
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

# scripts/ を import path に通す
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import import_admissions_excel as mod  # noqa: E402

XLSX_PATH = ROOT / "data" / "admissions_consolidated.xlsx"

pytestmark = pytest.mark.skipif(
    not XLSX_PATH.exists(),
    reason=f"入力 xlsx が存在しない: {XLSX_PATH}",
)


# ---------------------------------------------------------------------------
# ユニット: 変換関数
# ---------------------------------------------------------------------------


class TestMapWard:
    def test_map_known_wards(self):
        assert mod.map_ward("４Ｆ病棟") == "4F"
        assert mod.map_ward("５Ｆ病棟") == "5F"
        assert mod.map_ward("６Ｆ病棟") == "6F"

    def test_unknown_ward_raises(self):
        with pytest.raises(ValueError):
            mod.map_ward("7F病棟")
        with pytest.raises(ValueError):
            mod.map_ward("ICU")
        with pytest.raises(ValueError):
            mod.map_ward("5F")  # 半角は未知扱い


class TestMapAdmissionType:
    def test_known_types(self):
        assert mod.map_admission_type("予定") == "scheduled"
        assert mod.map_admission_type("当日(予定外/緊急)") == "emergency"

    def test_unknown_defaults_to_other(self):
        assert mod.map_admission_type("不明") == "other"
        assert mod.map_admission_type("") == "other"


class TestAgeCodeToYears:
    def test_normal_6digit(self):
        # 72歳03ヶ月27日 → 72
        assert mod.age_code_to_years(720327) == 72

    def test_string_input(self):
        assert mod.age_code_to_years("720327") == 72

    def test_pad_leading_zero(self):
        # 5 桁入力 (90歳以下ケースなど): 90123 → 090123 → 09 歳
        assert mod.age_code_to_years(90123) == 9

    def test_minimum_age(self):
        # 0 歳 5ヶ月 15 日 → 000515
        assert mod.age_code_to_years("000515") == 0

    def test_maximum_age(self):
        # 99 歳 11ヶ月 30 日 → 991130
        assert mod.age_code_to_years(991130) == 99

    def test_invalid_returns_none(self):
        assert mod.age_code_to_years(None) is None
        assert mod.age_code_to_years("") is None
        assert mod.age_code_to_years("abc") is None
        assert mod.age_code_to_years("1234567") is None  # 7 桁は不正


# ---------------------------------------------------------------------------
# 統合: xlsx からの変換
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def detail_df() -> pd.DataFrame:
    return mod.load_detail(XLSX_PATH)


@pytest.fixture(scope="module")
def transformed_df(detail_df) -> pd.DataFrame:
    # 決定的 UUID (テスト再現性のため)
    return mod.transform(detail_df, seed=42)


class TestLoadDetail:
    def test_xlsx_loads(self, detail_df):
        assert isinstance(detail_df, pd.DataFrame)
        assert len(detail_df) > 0

    def test_expected_columns(self, detail_df):
        expected = {
            "source_month",
            "admission_datetime",
            "admission_date",
            "register_datetime",
            "register_date",
            "ward",
            "age_code",
            "age_label",
            "admission_type",
        }
        assert expected.issubset(set(detail_df.columns))

    def test_file_not_found_raises(self, tmp_path):
        bogus = tmp_path / "missing.xlsx"
        with pytest.raises(FileNotFoundError):
            mod.load_detail(bogus)


class TestTransform:
    def test_row_count_matches(self, detail_df, transformed_df):
        # 入力と出力で件数が 1:1
        assert len(transformed_df) == len(detail_df)

    def test_expected_total_1965(self, transformed_df):
        # 仕様書に記載の期待件数
        assert len(transformed_df) == 1965

    def test_output_columns_exact(self, transformed_df):
        assert list(transformed_df.columns) == mod.OUTPUT_COLUMNS

    def test_wards_only_4f_5f_6f(self, transformed_df):
        wards = set(transformed_df["ward"].unique())
        assert wards == {"4F", "5F", "6F"}, f"予期せぬ病棟: {wards}"

    def test_ward_distribution(self, transformed_df):
        counts = transformed_df["ward"].value_counts().to_dict()
        # 仕様書に記載の期待値
        assert counts.get("4F") == 18
        assert counts.get("5F") == 951
        assert counts.get("6F") == 996

    def test_admission_route_values(self, transformed_df):
        routes = set(transformed_df["admission_route"].unique())
        # 入力 xlsx には予定 / 緊急 の 2 種類のみ
        assert routes.issubset({"scheduled", "emergency", "other"})
        assert "scheduled" in routes
        assert "emergency" in routes

    def test_event_type_always_admission(self, transformed_df):
        assert (transformed_df["event_type"] == "admission").all()

    def test_attending_doctor_default(self, transformed_df):
        # 欠損フィールドは "不明"
        assert (transformed_df["attending_doctor"] == mod.DEFAULT_ATTENDING_DOCTOR).all()

    def test_short3_type_default_empty(self, transformed_df):
        assert (transformed_df["short3_type"] == "").all()

    def test_notes_default_empty(self, transformed_df):
        assert (transformed_df["notes"] == "").all()

    def test_patient_id_unique(self, transformed_df):
        # UUID は全件ユニーク
        ids = transformed_df["patient_id"]
        assert ids.nunique() == len(ids)

    def test_event_date_is_yyyymmdd(self, transformed_df):
        # YYYY-MM-DD 文字列
        sample = transformed_df["event_date"].iloc[0]
        assert len(sample) == 10 and sample[4] == "-" and sample[7] == "-"

    def test_event_date_equals_admission_date(self, transformed_df):
        # 入院データのみなので両者は一致
        assert (transformed_df["event_date"] == transformed_df["admission_date"]).all()

    def test_age_years_range(self, transformed_df):
        # 現実的な範囲 (0 〜 120)
        ages = transformed_df["age_years"].dropna()
        assert ages.min() >= 0
        assert ages.max() <= 120


# ---------------------------------------------------------------------------
# run / CLI
# ---------------------------------------------------------------------------


class TestRun:
    def test_dry_run_does_not_write(self, tmp_path, capsys):
        out_path = tmp_path / "should_not_exist.csv"
        result = mod.run(XLSX_PATH, out_path, dry_run=True, seed=42)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1965
        assert not out_path.exists(), "dry-run 時はファイルを書き込まない"
        captured = capsys.readouterr()
        assert "[DRY RUN]" in captured.out
        assert "1965" in captured.out

    def test_writes_csv(self, tmp_path):
        out_path = tmp_path / "out.csv"
        mod.run(XLSX_PATH, out_path, seed=42)
        assert out_path.exists()
        # 読み返して件数確認
        loaded = pd.read_csv(out_path, encoding="utf-8-sig")
        assert len(loaded) == 1965
        assert list(loaded.columns) == mod.OUTPUT_COLUMNS

    def test_csv_roundtrip_integrity(self, tmp_path):
        out_path = tmp_path / "out.csv"
        written = mod.run(XLSX_PATH, out_path, seed=42)
        loaded = pd.read_csv(out_path, encoding="utf-8-sig")
        # 行数・列数
        assert len(written) == len(loaded)
        assert list(written.columns) == list(loaded.columns)
        # 主要カラムの値が一致
        assert (written["ward"].values == loaded["ward"].values).all()
        assert (
            written["admission_route"].values == loaded["admission_route"].values
        ).all()

    def test_cli_main_exit_zero(self, tmp_path, monkeypatch):
        out_path = tmp_path / "cli_out.csv"
        argv = [
            "--input",
            str(XLSX_PATH),
            "--output",
            str(out_path),
            "--seed",
            "42",
        ]
        rc = mod.main(argv)
        assert rc == 0
        assert out_path.exists()

    def test_cli_dry_run_no_write(self, tmp_path):
        out_path = tmp_path / "cli_dry.csv"
        argv = [
            "--input",
            str(XLSX_PATH),
            "--output",
            str(out_path),
            "--dry-run",
            "--seed",
            "42",
        ]
        rc = mod.main(argv)
        assert rc == 0
        assert not out_path.exists()

    def test_cli_missing_input_exit_one(self, tmp_path, capsys):
        bogus = tmp_path / "none.xlsx"
        rc = mod.main(["--input", str(bogus), "--output", str(tmp_path / "o.csv")])
        assert rc == 1


# ---------------------------------------------------------------------------
# summarize
# ---------------------------------------------------------------------------


class TestSummarize:
    def test_summary_shape(self, transformed_df):
        s = mod.summarize(transformed_df)
        assert s["total"] == 1965
        assert set(s["by_ward"].keys()) == {"4F", "5F", "6F"}
        # 緊急率: 1116 / 1965 ≒ 56.79%
        assert 55.0 < s["emergency_rate_pct"] < 60.0
        assert s["date_min"] == "2025-04-01"
        assert s["date_max"] == "2026-03-31"
