"""医師別 退院プロファイル分析のテスト."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from doctor_discharge_profile import (  # noqa: E402
    FRIDAY_HEAVY_PCT,
    SMALL_SAMPLE_THRESHOLD,
    UNIFORM_GINI_MAX,
    _gini_coefficient,
    build_doctor_summary,
    compute_self_driven_los,
    compute_weekday_profile,
    compute_weekend_vacancy_risk,
)


# ---------------------------------------------------------------------------
# _gini_coefficient
# ---------------------------------------------------------------------------

class TestGini:
    def test_empty(self):
        assert _gini_coefficient([]) == 0.0

    def test_all_zero(self):
        assert _gini_coefficient([0, 0, 0]) == 0.0

    def test_perfectly_uniform(self):
        # 全値が同じ: Gini = 0
        assert _gini_coefficient([10, 10, 10, 10, 10, 10, 10]) == 0.0

    def test_fully_concentrated(self):
        # 1 点集中: Gini はほぼ max
        g = _gini_coefficient([0, 0, 0, 0, 0, 0, 100])
        assert 0.8 < g < 1.0  # 7 個で (7-1)/7 ≈ 0.857

    def test_intermediate(self):
        # 中間の偏り
        g = _gini_coefficient([10, 10, 10, 10, 50, 5, 5])
        assert 0.1 < g < 0.6


# ---------------------------------------------------------------------------
# compute_weekday_profile
# ---------------------------------------------------------------------------

def _make_df(rows: list[dict]) -> pd.DataFrame:
    """DataFrame 構築ヘルパー. discharge_date は datetime に."""
    df = pd.DataFrame(rows)
    if "discharge_date" in df.columns:
        df["discharge_date"] = pd.to_datetime(df["discharge_date"])
    return df


class TestComputeWeekdayProfile:
    def test_empty(self):
        assert compute_weekday_profile(pd.DataFrame()) == {}

    def test_basic_single_doctor(self):
        df = _make_df([
            # 月 2026-04-06 (月), 4-07(火), 4-08(水), 4-09(木), 4-10(金), 4-11(土), 4-12(日)
            {"医師": "DOC_A", "discharge_date": "2026-04-06"},
            {"医師": "DOC_A", "discharge_date": "2026-04-07"},
            {"医師": "DOC_A", "discharge_date": "2026-04-08"},
            {"医師": "DOC_A", "discharge_date": "2026-04-09"},
            {"医師": "DOC_A", "discharge_date": "2026-04-10"},
            {"医師": "DOC_A", "discharge_date": "2026-04-11"},
            {"医師": "DOC_A", "discharge_date": "2026-04-12"},
        ])
        result = compute_weekday_profile(df)
        assert "DOC_A" in result
        pf = result["DOC_A"]
        assert pf["counts"] == [1, 1, 1, 1, 1, 1, 1]
        assert pf["total"] == 7
        assert pf["gini"] == 0.0  # 完全均等
        assert pf["flag"] == "uniform"

    def test_friday_heavy(self):
        # 10 件中 4 件金曜 (40%) = friday_heavy
        df = _make_df([
            {"医師": "DOC_B", "discharge_date": "2026-04-10"},  # 金
            {"医師": "DOC_B", "discharge_date": "2026-04-17"},
            {"医師": "DOC_B", "discharge_date": "2026-04-24"},
            {"医師": "DOC_B", "discharge_date": "2026-05-01"},
            # 他の曜日 6 件
            {"医師": "DOC_B", "discharge_date": "2026-04-06"},
            {"医師": "DOC_B", "discharge_date": "2026-04-07"},
            {"医師": "DOC_B", "discharge_date": "2026-04-08"},
            {"医師": "DOC_B", "discharge_date": "2026-04-09"},
            {"医師": "DOC_B", "discharge_date": "2026-04-13"},
            {"医師": "DOC_B", "discharge_date": "2026-04-14"},
        ])
        pf = compute_weekday_profile(df)["DOC_B"]
        assert pf["friday_pct"] == 40.0
        assert pf["flag"] == "friday_heavy"

    def test_small_sample_flag(self):
        df = _make_df([
            {"医師": "DOC_C", "discharge_date": "2026-04-10"},
            {"医師": "DOC_C", "discharge_date": "2026-04-11"},
        ])
        pf = compute_weekday_profile(df)["DOC_C"]
        assert pf["is_small_sample"]

    def test_multiple_doctors(self):
        df = _make_df([
            {"医師": "A", "discharge_date": "2026-04-10"},
            {"医師": "B", "discharge_date": "2026-04-06"},
        ])
        result = compute_weekday_profile(df)
        assert set(result.keys()) == {"A", "B"}

    def test_nat_discharge_dates_excluded(self):
        df = pd.DataFrame([
            {"医師": "A", "discharge_date": pd.Timestamp("2026-04-10")},
            {"医師": "A", "discharge_date": pd.NaT},
        ])
        pf = compute_weekday_profile(df)["A"]
        # NaT は除外されて 1 件だけカウント
        assert pf["total"] == 1


# ---------------------------------------------------------------------------
# compute_self_driven_los
# ---------------------------------------------------------------------------

class TestSelfDrivenLos:
    def test_empty(self):
        assert compute_self_driven_los(pd.DataFrame()) == {}

    def test_default_is_no_surgery_all(self):
        """デフォルトは手術なし全体（予定/予定外ともに含む）."""
        df = pd.DataFrame([
            {"医師": "A", "日数": 5, "is_scheduled": True, "has_surgery": False, "診療科": "内科"},
            {"医師": "A", "日数": 7, "is_scheduled": True, "has_surgery": False, "診療科": "内科"},
            {"医師": "A", "日数": 20, "is_scheduled": False, "has_surgery": False, "診療科": "内科"},
            # 手術ありはいずれも除外
            {"医師": "A", "日数": 3, "is_scheduled": True, "has_surgery": True, "診療科": "内科"},
        ])
        result = compute_self_driven_los(df)
        # 3 件が手術なし（5, 7, 20）、median 7
        assert result["A"]["self_driven_cases"] == 3
        assert result["A"]["median_los"] == 7.0

    def test_require_scheduled_mode_backward_compat(self):
        """require_scheduled=True の旧挙動（予定入院×手術なし のみ）."""
        df = pd.DataFrame([
            {"医師": "A", "日数": 5, "is_scheduled": True, "has_surgery": False, "診療科": "内科"},
            {"医師": "A", "日数": 7, "is_scheduled": True, "has_surgery": False, "診療科": "内科"},
            {"医師": "A", "日数": 20, "is_scheduled": False, "has_surgery": False, "診療科": "内科"},
            {"医師": "A", "日数": 3, "is_scheduled": True, "has_surgery": True, "診療科": "内科"},
        ])
        result = compute_self_driven_los(df, require_scheduled=True)
        assert result["A"]["self_driven_cases"] == 2
        assert result["A"]["median_los"] == 6.0

    def test_specialty_override_map(self):
        """override_map が指定されたら診療科列より優先される."""
        df = pd.DataFrame([
            {"医師": "X", "日数": 5, "is_scheduled": True, "has_surgery": False, "診療科": "循内科"},
            {"医師": "X", "日数": 7, "is_scheduled": True, "has_surgery": False, "診療科": "循内科"},
            {"医師": "Y", "日数": 3, "is_scheduled": True, "has_surgery": False, "診療科": "内科"},
            {"医師": "Y", "日数": 5, "is_scheduled": True, "has_surgery": False, "診療科": "内科"},
        ])
        # override: X, Y ともに "内科" に統合
        override = {"X": "内科", "Y": "内科"}
        result = compute_self_driven_los(df, specialty_override_map=override)
        # 全4件が同じ "内科" グループ → peer median = median(3,5,5,7) = 5.0
        assert result["X"]["peer_group"] == "内科"
        assert result["Y"]["peer_group"] == "内科"
        assert result["X"]["peer_median"] == 5.0
        assert result["Y"]["peer_median"] == 5.0

    def test_peer_median_by_specialty(self):
        df = pd.DataFrame([
            # 内科 3 件 (median 5)
            {"医師": "A", "日数": 3, "is_scheduled": True, "has_surgery": False, "診療科": "内科"},
            {"医師": "B", "日数": 5, "is_scheduled": True, "has_surgery": False, "診療科": "内科"},
            {"医師": "B", "日数": 7, "is_scheduled": True, "has_surgery": False, "診療科": "内科"},
            # 外科 1 件 (median 10)
            {"医師": "C", "日数": 10, "is_scheduled": True, "has_surgery": False, "診療科": "外科"},
        ])
        result = compute_self_driven_los(df)
        # 内科 peer median = 5.0 (values = 3, 5, 7 → median 5)
        assert result["A"]["peer_median"] == 5.0
        # A の los 3 → peer (5) - self (3) = +2 (peerより短い)
        assert result["A"]["los_delta_vs_peer"] == 2.0

    def test_small_sample_flagged(self):
        df = pd.DataFrame([
            {"医師": "A", "日数": 5, "is_scheduled": True, "has_surgery": False, "診療科": "内科"},
        ])
        assert compute_self_driven_los(df)["A"]["is_small_sample"]


# ---------------------------------------------------------------------------
# compute_weekend_vacancy_risk
# ---------------------------------------------------------------------------

class TestWeekendVacancyRisk:
    def test_empty(self):
        assert compute_weekend_vacancy_risk(pd.DataFrame()) == {}

    def test_high_risk_doctor(self):
        # 20 件中、木(4-09) 5件 + 金(4-10) 5件 = 10件 → 50%
        df_rows = []
        for _ in range(5):
            df_rows.append({"医師": "HIGH", "discharge_date": "2026-04-09"})  # 木
        for _ in range(5):
            df_rows.append({"医師": "HIGH", "discharge_date": "2026-04-10"})  # 金
        for _ in range(10):
            df_rows.append({"医師": "HIGH", "discharge_date": "2026-04-06"})  # 月
        # 別医師で peer を作る (計20件、木+金 = 4件 = 20%)
        for _ in range(2):
            df_rows.append({"医師": "LOW", "discharge_date": "2026-04-09"})
        for _ in range(2):
            df_rows.append({"医師": "LOW", "discharge_date": "2026-04-10"})
        for _ in range(16):
            df_rows.append({"医師": "LOW", "discharge_date": "2026-04-06"})
        df = _make_df(df_rows)
        result = compute_weekend_vacancy_risk(df)
        assert result["HIGH"]["thu_fri_pct"] == 50.0
        assert result["LOW"]["thu_fri_pct"] == 20.0
        # peer median は有効サンプル全員 (HIGH=50, LOW=20) の中央値 = 35.0
        assert result["HIGH"]["peer_thu_fri_pct"] == 35.0
        # HIGH の delta = 50 - 35 = +15 (peer より高い = リスク寄与大)
        assert result["HIGH"]["delta_vs_peer"] == 15.0


# ---------------------------------------------------------------------------
# build_doctor_summary
# ---------------------------------------------------------------------------

class TestBuildDoctorSummary:
    def test_uniform_doctor_gets_positive_insight(self):
        df = _make_df([
            {"医師": "UNIF", "discharge_date": "2026-04-06", "日数": 5,
             "is_scheduled": True, "has_surgery": False, "診療科": "内科"},
            {"医師": "UNIF", "discharge_date": "2026-04-07", "日数": 5,
             "is_scheduled": True, "has_surgery": False, "診療科": "内科"},
            {"医師": "UNIF", "discharge_date": "2026-04-08", "日数": 5,
             "is_scheduled": True, "has_surgery": False, "診療科": "内科"},
            {"医師": "UNIF", "discharge_date": "2026-04-09", "日数": 5,
             "is_scheduled": True, "has_surgery": False, "診療科": "内科"},
            {"医師": "UNIF", "discharge_date": "2026-04-10", "日数": 5,
             "is_scheduled": True, "has_surgery": False, "診療科": "内科"},
            {"医師": "UNIF", "discharge_date": "2026-04-11", "日数": 5,
             "is_scheduled": True, "has_surgery": False, "診療科": "内科"},
            {"医師": "UNIF", "discharge_date": "2026-04-12", "日数": 5,
             "is_scheduled": True, "has_surgery": False, "診療科": "内科"},
        ])
        summary = build_doctor_summary(df, "UNIF")
        assert summary["weekday"]["flag"] == "uniform"
        # 均等 = ポジティブ insight
        assert any("均等" in s for s in summary["insights"])

    def test_missing_doctor_returns_empty_insights(self):
        df = _make_df([{"医師": "A", "discharge_date": "2026-04-10", "日数": 5,
                       "is_scheduled": True, "has_surgery": False, "診療科": "内科"}])
        summary = build_doctor_summary(df, "NONEXISTENT")
        assert summary["weekday"] == {}
        assert summary["insights"] == []


# ---------------------------------------------------------------------------
# 実データでのスモークテスト
# ---------------------------------------------------------------------------

_REAL_CSV = Path(__file__).resolve().parent.parent / "data" / "past_admissions_2025fy.csv"


@pytest.mark.skipif(not _REAL_CSV.exists(), reason="past_admissions CSV not present")
class TestRealDataSmoke:
    def test_real_data_shapes(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from past_admissions_loader import load_past_admissions
        df = load_past_admissions()
        weekday = compute_weekday_profile(df)
        # 17 名の医師がいるはず
        assert 10 <= len(weekday) <= 20
        # 上位医師（ > 20件）の偏り指数が合理的範囲内
        big_docs = {k: v for k, v in weekday.items() if v["total"] >= 100}
        for doc, pf in big_docs.items():
            assert 0 <= pf["gini"] <= 1, f"{doc} gini={pf['gini']}"
            assert sum(pf["pcts"]) > 99 and sum(pf["pcts"]) < 101  # 100% ± 誤差

    def test_real_data_self_driven(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from past_admissions_loader import load_past_admissions
        df = load_past_admissions()
        result = compute_self_driven_los(df)
        # 少なくとも 1 人は計算対象になっている
        assert len(result) > 0
