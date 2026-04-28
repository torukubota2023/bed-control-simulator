"""scripts/doctor_collaboration_analysis.py のテスト."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from doctor_collaboration_analysis import (  # noqa: E402
    compare_kjj_vs_alternatives,
    estimate_load_redistribution,
    summarize_doctor_monthly,
    summarize_recent_month,
)


@pytest.fixture
def real_df():
    """実データ (1,960 件) を読む."""
    csv_path = Path(__file__).resolve().parent.parent / "data" / "past_admissions_2025fy.csv"
    if not csv_path.exists():
        pytest.skip("実データ CSV がない環境ではスキップ")
    return pd.read_csv(csv_path, parse_dates=["入院日", "退院日"])


# ---------------------------------------------------------------------------
# summarize_doctor_monthly
# ---------------------------------------------------------------------------

class TestSummarizeDoctorMonthly:
    def test_empty_returns_empty(self):
        result = summarize_doctor_monthly(pd.DataFrame())
        assert result.empty

    def test_basic_pivot(self):
        df = pd.DataFrame({
            "医師": ["KJJ", "KJJ", "OKUK", "KJJ"],
            "入院日": pd.to_datetime(["2025-04-01", "2025-04-15", "2025-04-10", "2025-05-01"]),
        })
        result = summarize_doctor_monthly(df)
        assert result.loc["2025-04", "KJJ"] == 2
        assert result.loc["2025-04", "OKUK"] == 1
        assert result.loc["2025-05", "KJJ"] == 1

    def test_filter_by_doctor_codes(self):
        df = pd.DataFrame({
            "医師": ["KJJ", "OKUK", "HAYT"],
            "入院日": pd.to_datetime(["2025-04-01"] * 3),
        })
        result = summarize_doctor_monthly(df, doctor_codes=["KJJ", "OKUK"])
        assert "KJJ" in result.columns
        assert "OKUK" in result.columns
        assert "HAYT" not in result.columns


# ---------------------------------------------------------------------------
# compare_kjj_vs_alternatives
# ---------------------------------------------------------------------------

class TestCompareKjjVsAlternatives:
    def test_empty_returns_empty_structure(self):
        result = compare_kjj_vs_alternatives(pd.DataFrame())
        assert result == {"donor": {}, "peers": [], "specialty_summary": []}

    def test_real_data_kjj_count(self, real_df):
        result = compare_kjj_vs_alternatives(real_df)
        assert result["donor"]["code"] == "KJJ"
        # KJJ 141 件 (過去1年 129 + 4月 12)
        assert result["donor"]["total"] == 141
        # KJJ 手術なしは 135 件
        assert result["donor"]["no_surgery"] == 135
        # ペイン科分類
        assert result["donor"]["specialty"] == "ペイン科"

    def test_real_data_peers(self, real_df):
        result = compare_kjj_vs_alternatives(real_df)
        peer_codes = [p["code"] for p in result["peers"]]
        assert "OKUK" in peer_codes
        assert "HOKM" in peer_codes
        # 各ピアに total/no_surgery がある
        for peer in result["peers"]:
            assert "total" in peer
            assert "no_surgery" in peer
            assert "specialty" in peer

    def test_real_data_specialty_summary(self, real_df):
        result = compare_kjj_vs_alternatives(real_df)
        groups = [s["group"] for s in result["specialty_summary"]]
        assert "整形外科" in groups
        assert "ペイン科" in groups


# ---------------------------------------------------------------------------
# estimate_load_redistribution
# ---------------------------------------------------------------------------

class TestEstimateLoadRedistribution:
    def test_real_data_30pct_to_orthopedics(self, real_df):
        result = estimate_load_redistribution(
            real_df, donor_code="KJJ", transfer_pct=30.0,
            target_specialty="整形外科",
        )
        # 振替件数 = 135 (手術なし) × 30% = 40
        assert result["transferred_count"] == 40
        # KJJ before/after の差
        assert result["donor_before_after"]["total"] == 141
        assert result["donor_before_after"]["no_surgery"] == 135

    def test_real_data_zero_pct_no_change(self, real_df):
        result = estimate_load_redistribution(
            real_df, transfer_pct=0.0,
            target_specialty="内科",
        )
        assert result["transferred_count"] == 0


# ---------------------------------------------------------------------------
# summarize_recent_month
# ---------------------------------------------------------------------------

class TestSummarizeRecentMonth:
    def test_real_data_apr2026(self, real_df):
        result = summarize_recent_month(real_df, target_ym="2026-04",
                                         focus_doctor="KJJ")
        # 4月25日までのデータで 137 件
        assert result["total"] == 137
        # KJJ は 12 件
        assert result["focus"]["total"] == 12
        # 6F (=6階の正規化後表記) で 7 件
        assert result["focus"]["ward_breakdown"].get("6F", 0) == 7
        assert result["focus"]["ward_breakdown"].get("5F", 0) == 5

    def test_nonexistent_month_returns_empty(self, real_df):
        result = summarize_recent_month(real_df, target_ym="2099-99")
        assert result["total"] == 0
        assert result["doctor_ranking"] == []
