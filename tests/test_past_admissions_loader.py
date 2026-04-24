"""過去入院データローダーのテスト."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from past_admissions_loader import (  # noqa: E402
    DEFAULT_CSV_PATH,
    EMERGENCY_AMBULANCE_YES,
    SHORT3_CERTAIN_LOS_MAX,
    SHORT3_LIKELY_LOS_MAX,
    load_past_admissions,
    summarize_short3_estimate,
    tabulate_tier_distribution,
    to_monthly_summary,
)


def _make_sample_csv(tmp_path: Path) -> Path:
    """テスト用のミニ CSV を生成."""
    df = pd.DataFrame([
        # 5F 緊急×救急車×家庭 = 自院救急、手術なし（イ）
        {"患者番号": 1, "病棟": "5F", "救急車": "有り", "緊急": "予定外（救急医療入院以外）",
         "入経路": "家庭", "入院日": "2025-04-01", "退院日": "2025-04-10",
         "退経路": "自宅", "日数": 10, "診療科": "内科", "医師": "TERUH", "手術": "×"},
        # 5F 緊急×救急車×他病院 = 下り搬送、手術あり（ロ）
        {"患者番号": 2, "病棟": "5F", "救急車": "有り", "緊急": "予定外（救急医療入院以外）",
         "入経路": "他病院", "入院日": "2025-04-02", "退院日": "2025-04-08",
         "退経路": "自宅", "日数": 7, "診療科": "外科", "医師": "KONA", "手術": "○"},
        # 5F 予定×手術×2日 = 短手3確実、ハ
        {"患者番号": 3, "病棟": "5F", "救急車": "無し", "緊急": "予定入院",
         "入経路": "家庭", "入院日": "2025-04-03", "退院日": "2025-04-04",
         "退経路": "自宅", "日数": 2, "診療科": "外科", "医師": "HIGT", "手術": "○"},
        # 6F 予定×手術×5日 = 短手3ほぼ（ハ）
        {"患者番号": 4, "病棟": "6F", "救急車": "無し", "緊急": "予定入院",
         "入経路": "家庭", "入院日": "2025-05-01", "退院日": "2025-05-05",
         "退経路": "自宅", "日数": 5, "診療科": "麻酔科", "医師": "TAIRK", "手術": "○"},
        # 6F 予定×手術なし = ロ
        {"患者番号": 5, "病棟": "6F", "救急車": "無し", "緊急": "予定入院",
         "入経路": "他病院", "入院日": "2025-05-05", "退院日": "2025-05-20",
         "退経路": "居住系", "日数": 16, "診療科": "内科", "医師": "KUBT", "手術": "×"},
        # 6F 在院中（退院日 NaT）
        {"患者番号": 6, "病棟": "6F", "救急車": "有り", "緊急": "予定外（救急医療入院以外）",
         "入経路": "施設入", "入院日": "2025-05-25", "退院日": None,
         "退経路": None, "日数": None, "診療科": "内科", "医師": "KJJ", "手術": "×"},
    ])
    csv_path = tmp_path / "sample_past.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8")
    return csv_path


# ---------------------------------------------------------------------------
# load_past_admissions
# ---------------------------------------------------------------------------

class TestLoadPastAdmissions:
    def test_load_empty_when_missing(self, tmp_path):
        df = load_past_admissions(tmp_path / "nonexistent.csv")
        assert df.empty

    def test_load_sample(self, tmp_path):
        csv = _make_sample_csv(tmp_path)
        df = load_past_admissions(csv)
        assert len(df) == 6

    def test_emergency_transport_flag(self, tmp_path):
        csv = _make_sample_csv(tmp_path)
        df = load_past_admissions(csv)
        assert df["is_emergency_transport"].sum() == 3  # 1,2,6
        # 患者番号 1: 救急車=有
        assert df.iloc[0]["is_emergency_transport"]
        # 患者番号 3: 救急車=無
        assert not df.iloc[2]["is_emergency_transport"]

    def test_self_emergency_vs_downstream(self, tmp_path):
        csv = _make_sample_csv(tmp_path)
        df = load_past_admissions(csv)
        # 自院救急 = 家庭 or 施設入 × 救急車有 = 2件 (患者1, 患者6)
        assert df["is_self_emergency"].sum() == 2
        # 下り搬送 = 他病院 × 救急車有 = 1件 (患者2)
        assert df["is_downstream_transfer"].sum() == 1

    def test_short3_estimation(self, tmp_path):
        csv = _make_sample_csv(tmp_path)
        df = load_past_admissions(csv)
        # 手術あり×日数≤2: 患者3（日数2）のみ
        assert df["is_short3_certain"].sum() == 1
        # 手術あり×日数≤5: 患者3（2日）+ 患者4（5日） = 2件
        assert df["is_short3_likely"].sum() == 2
        # 患者2（7日の手術）は short3 ではない
        assert not df.iloc[1]["is_short3_certain"]
        assert not df.iloc[1]["is_short3_likely"]

    def test_dates_parsed(self, tmp_path):
        csv = _make_sample_csv(tmp_path)
        df = load_past_admissions(csv)
        assert df.iloc[0]["admission_date"] == date(2025, 4, 1)
        assert df.iloc[0]["discharge_date"] == date(2025, 4, 10)
        # 在院中は NaT
        assert pd.isna(df.iloc[5]["discharge_date"])


# ---------------------------------------------------------------------------
# to_monthly_summary
# ---------------------------------------------------------------------------

class TestToMonthlySummary:
    def test_empty_df(self):
        assert to_monthly_summary(pd.DataFrame()) == {}

    def test_basic_structure(self, tmp_path):
        csv = _make_sample_csv(tmp_path)
        df = load_past_admissions(csv)
        summary = to_monthly_summary(df)
        # 2 ヶ月分ある (2025-04, 2025-05)
        assert set(summary.keys()) == {"2025-04", "2025-05"}
        # 各月に 5F, 6F, all の3キー
        for ym in summary.values():
            assert set(ym.keys()) == {"5F", "6F", "all"}

    def test_admissions_count(self, tmp_path):
        csv = _make_sample_csv(tmp_path)
        df = load_past_admissions(csv)
        summary = to_monthly_summary(df)
        # 2025-04: 5F 3件, 6F 0件, all 3件
        assert summary["2025-04"]["5F"]["admissions"] == 3
        assert summary["2025-04"]["6F"]["admissions"] == 0
        assert summary["2025-04"]["all"]["admissions"] == 3
        # 2025-05: 5F 0件, 6F 3件, all 3件
        assert summary["2025-05"]["5F"]["admissions"] == 0
        assert summary["2025-05"]["6F"]["admissions"] == 3
        assert summary["2025-05"]["all"]["admissions"] == 3

    def test_emergency_count(self, tmp_path):
        csv = _make_sample_csv(tmp_path)
        df = load_past_admissions(csv)
        summary = to_monthly_summary(df)
        # 2025-04 5F: 患者1 (自院) + 患者2 (下り) = 2件救急
        assert summary["2025-04"]["5F"]["emergency"] == 2
        assert summary["2025-04"]["5F"]["self_emergency"] == 1
        assert summary["2025-04"]["5F"]["downstream_transfer"] == 1
        # 2025-05 6F: 患者6 (施設入×救急車有) = 1件
        assert summary["2025-05"]["6F"]["emergency"] == 1
        assert summary["2025-05"]["6F"]["self_emergency"] == 1
        assert summary["2025-05"]["6F"]["downstream_transfer"] == 0

    def test_short3_NOT_excluded_from_denominator_by_default(self, tmp_path):
        """制度ルール：短手3 は分母に含める（除外しない）."""
        csv = _make_sample_csv(tmp_path)
        df = load_past_admissions(csv)
        summary = to_monthly_summary(df, exclude_short3_from_denominator=False)
        # 2025-04 5F: 患者1,2,3 = 3件（短手3候補の患者3 も含む）
        assert summary["2025-04"]["5F"]["admissions"] == 3

    def test_short3_exclusion_mode(self, tmp_path):
        """除外モード（制度判定外で使う用）."""
        csv = _make_sample_csv(tmp_path)
        df = load_past_admissions(csv)
        summary = to_monthly_summary(df, exclude_short3_from_denominator=True)
        # 2025-04 5F: 患者3 (短手3確実) を除外 → 2件
        assert summary["2025-04"]["5F"]["admissions"] == 2


# ---------------------------------------------------------------------------
# summarize_short3_estimate
# ---------------------------------------------------------------------------

class TestSummarizeShort3:
    def test_empty(self):
        result = summarize_short3_estimate(pd.DataFrame())
        assert result["total_surgeries"] == 0
        assert result["short3_certain"] == 0

    def test_counts(self, tmp_path):
        csv = _make_sample_csv(tmp_path)
        df = load_past_admissions(csv)
        result = summarize_short3_estimate(df)
        # 手術あり: 患者2 (7日), 患者3 (2日), 患者4 (5日) = 3件
        assert result["total_surgeries"] == 3
        # 確実 (≤2日): 患者3
        assert result["short3_certain"] == 1
        # ほぼ (≤5日): 患者3, 4
        assert result["short3_likely"] == 2
        # 3〜5日のみ: 患者4
        assert result["short3_likely_excluding_certain"] == 1
        # 非短手3手術 (≥6日): 患者2
        assert result["non_short3_surgery"] == 1


# ---------------------------------------------------------------------------
# tabulate_tier_distribution
# ---------------------------------------------------------------------------

class TestTabulateTierDistribution:
    def test_empty(self):
        result = tabulate_tier_distribution(pd.DataFrame())
        assert result["total"] == 0

    def test_tier_assignment(self, tmp_path):
        csv = _make_sample_csv(tmp_path)
        df = load_past_admissions(csv)
        result = tabulate_tier_distribution(df)

        # 判定ロジック:
        #   イ = 緊急×無手術（患者1, 患者6）= 2件
        #   ロ = (緊急×有手術) or (予定×無手術) = 患者2, 患者5 = 2件
        #   ハ = 予定×有手術 = 患者3, 患者4 = 2件
        assert result["tier_i"] == 2
        assert result["tier_ro"] == 2
        assert result["tier_ha"] == 2
        assert result["total"] == 6

        # 5F: 患者1(イ), 患者2(ロ), 患者3(ハ)
        assert result["by_ward"]["5F"]["tier_i"] == 1
        assert result["by_ward"]["5F"]["tier_ro"] == 1
        assert result["by_ward"]["5F"]["tier_ha"] == 1
        # 6F: 患者4(ハ), 患者5(ロ), 患者6(イ)
        assert result["by_ward"]["6F"]["tier_i"] == 1
        assert result["by_ward"]["6F"]["tier_ro"] == 1
        assert result["by_ward"]["6F"]["tier_ha"] == 1


# ---------------------------------------------------------------------------
# 実データでのスモークテスト（CSV 実在時のみ）
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not DEFAULT_CSV_PATH.exists(),
    reason="data/past_admissions_2025fy.csv not present",
)
class TestRealDataSmoke:
    def test_loads(self):
        df = load_past_admissions()
        assert len(df) > 0
        # 基本的な整合性
        assert df["is_self_emergency"].sum() + df["is_downstream_transfer"].sum() == df["is_emergency_transport"].sum()

    def test_emergency_ratio_sanity(self):
        df = load_past_admissions()
        ratio = df["is_emergency_transport"].mean() * 100
        # 期待値: 15% 前後（制度基準近辺）
        assert 5 < ratio < 30, f"emergency ratio = {ratio:.1f}%"

    def test_monthly_summary_roundtrip(self):
        df = load_past_admissions()
        summary = to_monthly_summary(df)
        # 少なくとも12ヶ月あるはず
        assert len(summary) >= 11
        # 各月 5F/6F/all のキーが揃っている
        for ym, ward_data in summary.items():
            assert "5F" in ward_data and "6F" in ward_data and "all" in ward_data
            # all = 5F + 6F 近似
            assert ward_data["all"]["admissions"] >= ward_data["5F"]["admissions"] + ward_data["6F"]["admissions"] - 2
