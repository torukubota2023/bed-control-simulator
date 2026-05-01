"""nursing_necessity_seeds のテスト."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from nursing_necessity_seeds import (
    DEFAULT_SEED_YAML,
    SEED_REQUIRED_KEYS,
    get_data_source_summary,
    is_seed_valid,
    load_seeds_from_yaml,
    merge_monthly_with_seeds,
    save_seed_to_yaml,
)


# ---------------------------------------------------------------------------
# load_seeds_from_yaml
# ---------------------------------------------------------------------------

class TestLoadSeeds:
    def test_missing_file_returns_empty(self, tmp_path):
        result = load_seeds_from_yaml(tmp_path / "nonexistent.yaml")
        assert result == {}

    def test_template_with_only_nulls(self, tmp_path):
        p = tmp_path / "seed.yaml"
        p.write_text("seeds: {}\n", encoding="utf-8")
        result = load_seeds_from_yaml(p)
        assert result == {}

    def test_partial_seed_kept(self, tmp_path):
        p = tmp_path / "seed.yaml"
        p.write_text(
            "seeds:\n"
            "  '2026-04':\n"
            "    '5F':\n"
            "      I_total: 1280\n"
            "      I_pass1: 240\n"
            "      II_total: 1280\n"
            "      II_pass1: 215\n",
            encoding="utf-8",
        )
        result = load_seeds_from_yaml(p)
        assert "2026-04" in result
        assert "5F" in result["2026-04"]
        assert result["2026-04"]["5F"]["I_total"] == 1280.0
        assert result["2026-04"]["5F"]["I_pass1"] == 240.0

    def test_invalid_ward_filtered(self, tmp_path):
        p = tmp_path / "seed.yaml"
        p.write_text(
            "seeds:\n"
            "  '2026-04':\n"
            "    '5F':\n"
            "      I_total: 1000\n"
            "      I_pass1: 200\n"
            "      II_total: 1000\n"
            "      II_pass1: 180\n"
            "    'invalid_ward':\n"
            "      I_total: 999\n",
            encoding="utf-8",
        )
        result = load_seeds_from_yaml(p)
        assert "5F" in result["2026-04"]
        assert "invalid_ward" not in result["2026-04"]

    def test_all_null_skipped(self, tmp_path):
        p = tmp_path / "seed.yaml"
        p.write_text(
            "seeds:\n"
            "  '2026-04':\n"
            "    '5F':\n"
            "      I_total: null\n"
            "      I_pass1: null\n"
            "      II_total: null\n"
            "      II_pass1: null\n",
            encoding="utf-8",
        )
        result = load_seeds_from_yaml(p)
        # 全部 null なら採用しない
        assert "2026-04" not in result

    def test_invalid_yaml_returns_empty(self, tmp_path):
        p = tmp_path / "broken.yaml"
        p.write_text("seeds: : [\n", encoding="utf-8")
        result = load_seeds_from_yaml(p)
        assert result == {}


# ---------------------------------------------------------------------------
# is_seed_valid
# ---------------------------------------------------------------------------

class TestIsSeedValid:
    def test_complete(self):
        seed = {"I_total": 1000, "I_pass1": 200, "II_total": 1000, "II_pass1": 180}
        assert is_seed_valid(seed) is True

    def test_partial_with_null(self):
        seed = {"I_total": 1000, "I_pass1": None, "II_total": 1000, "II_pass1": 180}
        assert is_seed_valid(seed) is False

    def test_empty(self):
        assert is_seed_valid({}) is False


# ---------------------------------------------------------------------------
# merge_monthly_with_seeds
# ---------------------------------------------------------------------------

class TestMerge:
    def _make_csv_df(self):
        # 既存の月次サマリー（CSV 由来）— 2025-04 の 5F/6F のみ
        return pd.DataFrame([
            {"ym": "2025-04", "ward": "5F",
             "I_total": 1303, "I_pass1": 295,
             "II_total": 1303, "II_pass1": 261,
             "I_rate1": 0.226, "II_rate1": 0.200,
             "I_meets_legacy": True, "I_meets_new": True,
             "II_meets_legacy": True, "II_meets_new": True},
            {"ym": "2025-04", "ward": "6F",
             "I_total": 1312, "I_pass1": 282,
             "II_total": 1312, "II_pass1": 250,
             "I_rate1": 0.215, "II_rate1": 0.190,
             "I_meets_legacy": True, "I_meets_new": True,
             "II_meets_legacy": True, "II_meets_new": True},
        ])

    def test_csv_only_no_seeds(self):
        df = self._make_csv_df()
        out = merge_monthly_with_seeds(df, seeds={})
        assert len(out) == 2
        assert (out["data_source"] == "csv").all()

    def test_seeds_added_for_missing_months(self):
        df = self._make_csv_df()
        seeds = {
            "2026-04": {
                "5F": {"I_total": 1200, "I_pass1": 240, "II_total": 1200, "II_pass1": 216},
                "6F": {"I_total": 1180, "I_pass1": 200, "II_total": 1180, "II_pass1": 180},
            },
        }
        out = merge_monthly_with_seeds(df, seeds=seeds)
        # 既存 2 + シード 2 = 4 行
        assert len(out) == 4
        # 2025-04 = csv
        csv_rows = out[out["ym"] == "2025-04"]
        assert (csv_rows["data_source"] == "csv").all()
        # 2026-04 = monthly_seed
        seed_rows = out[out["ym"] == "2026-04"]
        assert (seed_rows["data_source"] == "monthly_seed").all()
        # rate が正しく計算されている
        sf_seed = seed_rows[seed_rows["ward"] == "5F"].iloc[0]
        assert abs(sf_seed["I_rate1"] - 0.20) < 0.001  # 240/1200

    def test_csv_takes_priority_over_seed(self):
        df = self._make_csv_df()
        # 同じ 2025-04 5F のシードを定義しても CSV が優先
        seeds = {
            "2025-04": {
                "5F": {"I_total": 999, "I_pass1": 999, "II_total": 999, "II_pass1": 999},
            },
        }
        out = merge_monthly_with_seeds(df, seeds=seeds)
        # 2 行のまま（重複追加されない）
        assert len(out) == 2
        # CSV 値が残る
        sf = out[(out["ym"] == "2025-04") & (out["ward"] == "5F")].iloc[0]
        assert sf["I_total"] == 1303
        assert sf["data_source"] == "csv"

    def test_invalid_seed_skipped(self):
        df = self._make_csv_df()
        seeds = {
            "2026-04": {
                "5F": {"I_total": 1200, "I_pass1": None, "II_total": 1200, "II_pass1": 216},
                # I_pass1 が null なので採用されない
            },
        }
        out = merge_monthly_with_seeds(df, seeds=seeds)
        assert len(out) == 2  # CSV 2 行のみ、シード追加なし

    def test_empty_input(self):
        out = merge_monthly_with_seeds(pd.DataFrame(), seeds=None)
        assert len(out) == 0

    def test_seed_threshold_judgment(self):
        seeds = {
            "2026-04": {
                "5F": {"I_total": 1000, "I_pass1": 200, "II_total": 1000, "II_pass1": 180},
                # I 20% (新基準19%以上で達成)、II 18% (新基準18%でちょうど達成)
                "6F": {"I_total": 1000, "I_pass1": 150, "II_total": 1000, "II_pass1": 120},
                # I 15% (新基準19% に未達)、II 12% (新基準18% に未達)
            },
        }
        out = merge_monthly_with_seeds(pd.DataFrame(), seeds=seeds)
        sf = out[out["ward"] == "5F"].iloc[0]
        # numpy bool / Python bool の差異を吸収して bool() で比較
        assert bool(sf["I_meets_new"]) is True   # 20% >= 19%
        assert bool(sf["II_meets_new"]) is True  # 18% >= 18%

        ssf = out[out["ward"] == "6F"].iloc[0]
        assert bool(ssf["I_meets_new"]) is False    # 15% < 19%
        assert bool(ssf["II_meets_new"]) is False   # 12% < 18%


# ---------------------------------------------------------------------------
# get_data_source_summary
# ---------------------------------------------------------------------------

class TestSourceSummary:
    def test_basic(self):
        df = pd.DataFrame([
            {"ym": "2025-04", "ward": "5F", "data_source": "csv"},
            {"ym": "2025-04", "ward": "6F", "data_source": "csv"},
            {"ym": "2026-04", "ward": "5F", "data_source": "monthly_seed"},
        ])
        s = get_data_source_summary(df, target_ym=["2025-04", "2026-04", "2026-05"])
        assert s["2025-04"]["5F"] == "csv"
        assert s["2025-04"]["6F"] == "csv"
        assert s["2026-04"]["5F"] == "monthly_seed"
        # 6F 2026-04 / 5F+6F 2026-05 → no_data
        assert s["2026-04"]["6F"] == "no_data"
        assert s["2026-05"]["5F"] == "no_data"
        assert s["2026-05"]["6F"] == "no_data"


# ---------------------------------------------------------------------------
# save_seed_to_yaml
# ---------------------------------------------------------------------------

class TestSaveSeed:
    def test_save_new_seed(self, tmp_path):
        p = tmp_path / "seed.yaml"
        out = save_seed_to_yaml(
            "2026-04", "5F",
            {"I_total": 1200, "I_pass1": 240, "II_total": 1200, "II_pass1": 216},
            path=p,
        )
        assert out == p
        assert p.exists()
        loaded = load_seeds_from_yaml(p)
        assert loaded["2026-04"]["5F"]["I_total"] == 1200.0

    def test_save_overwrites_existing(self, tmp_path):
        p = tmp_path / "seed.yaml"
        save_seed_to_yaml(
            "2026-04", "5F",
            {"I_total": 1000, "I_pass1": 200, "II_total": 1000, "II_pass1": 180},
            path=p,
        )
        save_seed_to_yaml(
            "2026-04", "5F",
            {"I_total": 1500, "I_pass1": 300, "II_total": 1500, "II_pass1": 270},
            path=p,
        )
        loaded = load_seeds_from_yaml(p)
        assert loaded["2026-04"]["5F"]["I_total"] == 1500.0

    def test_save_preserves_other_wards(self, tmp_path):
        p = tmp_path / "seed.yaml"
        save_seed_to_yaml(
            "2026-04", "5F",
            {"I_total": 1000, "I_pass1": 200, "II_total": 1000, "II_pass1": 180},
            path=p,
        )
        save_seed_to_yaml(
            "2026-04", "6F",
            {"I_total": 1100, "I_pass1": 220, "II_total": 1100, "II_pass1": 198},
            path=p,
        )
        loaded = load_seeds_from_yaml(p)
        # 両方残っている
        assert "5F" in loaded["2026-04"]
        assert "6F" in loaded["2026-04"]

    def test_invalid_ward_raises(self, tmp_path):
        p = tmp_path / "seed.yaml"
        with pytest.raises(ValueError):
            save_seed_to_yaml("2026-04", "X棟", {}, path=p)


# ---------------------------------------------------------------------------
# 既存 YAML テンプレが load 可能か（リグレッション）
# ---------------------------------------------------------------------------

def test_default_yaml_template_is_loadable():
    """settings/manual_seed_nursing_necessity.yaml がコメントのみ・seeds: {} の状態でも読める."""
    if not DEFAULT_SEED_YAML.exists():
        pytest.skip("デフォルト YAML がまだ存在しない")
    result = load_seeds_from_yaml(DEFAULT_SEED_YAML)
    # 空辞書（seeds: {}）が期待値
    assert isinstance(result, dict)
