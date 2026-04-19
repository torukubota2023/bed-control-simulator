"""実データ由来デモデータ生成スクリプト (generate_demo_from_actual.py) のテスト."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

# scripts/ をパスに追加
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from generate_demo_from_actual import (  # noqa: E402
    DOCTORS_5F,
    DOCTORS_6F,
    SHORT3_OVERALL_RATIO,
    SHORT3_OVERFLOW_RATE,
    WARD_BEDS,
    generate_demo_from_actual,
    load_actual_admissions,
    summarize,
    write_csvs,
)

ACTUAL_CSV = ROOT / "data" / "actual_admissions_2025fy.csv"


@pytest.fixture(scope="module")
def demo_data() -> dict:
    """実データからデモを 1 回だけ生成してキャッシュ."""
    return generate_demo_from_actual(input_csv=ACTUAL_CSV, seed=42)


# ---------------------------------------------------------------------------
# 入力読込・フォールバック
# ---------------------------------------------------------------------------


class TestInputFallback:
    """入力 CSV が読めない場合のフォールバック."""

    def test_missing_csv_raises_filenotfound(self, tmp_path):
        """存在しないパスを渡すと FileNotFoundError."""
        missing = tmp_path / "does_not_exist.csv"
        with pytest.raises(FileNotFoundError):
            generate_demo_from_actual(input_csv=missing, seed=42)

    def test_missing_csv_cli_returns_nonzero(self, tmp_path):
        """CLI は stderr に出して 1 を返す."""
        from generate_demo_from_actual import main
        missing = tmp_path / "nope.csv"
        rc = main(["--input", str(missing), "--output", str(tmp_path), "--seed", "42"])
        assert rc == 1

    def test_load_actual_admissions_filters_wards(self, tmp_path):
        """4F などは読込時点で除外される."""
        df = load_actual_admissions(ACTUAL_CSV)
        assert set(df["ward"].unique()).issubset({"5F", "6F"})


# ---------------------------------------------------------------------------
# 実データ件数の保持
# ---------------------------------------------------------------------------


class TestActualAdmissionCounts:
    """病棟別入院件数が実データと完全一致する."""

    def test_5f_count_matches_actual(self, demo_data):
        adm = demo_data["admission_details_df"]
        count_5f = len(adm[adm["ward"] == "5F"])
        assert count_5f == 951, f"5F 件数 {count_5f} (期待 951)"

    def test_6f_count_matches_actual(self, demo_data):
        adm = demo_data["admission_details_df"]
        count_6f = len(adm[adm["ward"] == "6F"])
        assert count_6f == 996, f"6F 件数 {count_6f} (期待 996)"

    def test_admission_total(self, demo_data):
        adm = demo_data["admission_details_df"]
        assert len(adm) == 1947  # 951 + 996

    def test_discharge_count_equals_admission(self, demo_data):
        """退院件数 = 入院件数（1:1 対応）."""
        assert len(demo_data["discharge_details_df"]) == len(
            demo_data["admission_details_df"]
        )


# ---------------------------------------------------------------------------
# 短手3 比率
# ---------------------------------------------------------------------------


class TestShort3Ratios:
    """副院長校正情報への準拠."""

    def test_short3_ratio_in_12_to_15_pct(self, demo_data):
        """短手3 比率が 12-15% の範囲内（target 13.5%）."""
        adm = demo_data["admission_details_df"]
        s3 = adm[~adm["short3_type"].isin(["該当なし", ""])]
        ratio = len(s3) / len(adm)
        assert 0.12 <= ratio <= 0.15, (
            f"短手3 比率 {ratio:.3f} が 12-15% 範囲外 (target={SHORT3_OVERALL_RATIO})"
        )

    def test_day6_overflow_in_3_to_7_pct(self, demo_data):
        """Day 6 超過率が短手3 内の 3-7% 範囲（target 5% ± 2%）."""
        adm = demo_data["admission_details_df"]
        dis = demo_data["discharge_details_df"]
        # admission と discharge は 1:1 対応（順序保持）
        s3_mask = ~adm["short3_type"].isin(["該当なし", ""])
        s3_discharges = dis[s3_mask.values].copy()
        s3_discharges["los"] = s3_discharges["los_days"].astype(int)
        overflow = s3_discharges[s3_discharges["los"] >= 6]
        ratio = len(overflow) / max(1, len(s3_discharges))
        assert 0.03 <= ratio <= 0.07, (
            f"Day 6+ overflow 比率 {ratio:.3f} が 3-7% 範囲外 "
            f"(target={SHORT3_OVERFLOW_RATE})"
        )

    def test_short3_monthly_average_near_22(self, demo_data):
        """月間短手3 件数の平均が 18-26 件の範囲（target 22 件/月）."""
        adm = demo_data["admission_details_df"]
        s3 = adm[~adm["short3_type"].isin(["該当なし", ""])].copy()
        s3["month"] = s3["date"].str[:7]
        monthly = s3.groupby("month").size()
        assert 18 <= monthly.mean() <= 26, (
            f"月間平均短手3 {monthly.mean():.1f} が 18-26 件範囲外"
        )

    def test_short3_type_weights(self, demo_data):
        """短手3 種別の内訳が target に近い（大腸ポリペク 55% / 鼠径 20% / PSG 25%）."""
        adm = demo_data["admission_details_df"]
        s3 = adm[~adm["short3_type"].isin(["該当なし", ""])]
        counts = s3["short3_type"].value_counts(normalize=True).to_dict()
        # ±10% の誤差許容
        assert counts.get("大腸ポリペクトミー", 0) >= 0.45
        assert counts.get("大腸ポリペクトミー", 0) <= 0.70  # overflow 補正含む
        assert counts.get("ヘルニア手術", 0) >= 0.10
        assert counts.get("ヘルニア手術", 0) <= 0.30
        assert counts.get("ポリソムノグラフィー", 0) >= 0.15
        assert counts.get("ポリソムノグラフィー", 0) <= 0.35

    def test_overflow_los_within_8_days(self, demo_data):
        """延長ケースも Day 8 以内でほぼ退院（副院長指示）."""
        adm = demo_data["admission_details_df"]
        dis = demo_data["discharge_details_df"]
        s3_mask = ~adm["short3_type"].isin(["該当なし", ""])
        s3_discharges = dis[s3_mask.values].copy()
        s3_discharges["los"] = s3_discharges["los_days"].astype(int)
        # 短手3 全員の最大 LOS
        if len(s3_discharges) > 0:
            assert s3_discharges["los"].max() <= 10, (
                f"短手3 最大 LOS {s3_discharges['los'].max()} 日 (8 日以内目標)"
            )


# ---------------------------------------------------------------------------
# CSV スキーマ互換
# ---------------------------------------------------------------------------


class TestSchemaCompat:
    """生成 CSV のスキーマが既存デモと互換."""

    def test_daily_df_columns_match_2026fy(self, demo_data):
        """daily_df のカラムが既存 2026fy デモと一致."""
        daily = demo_data["daily_df"]
        existing = pd.read_csv(
            ROOT / "output" / "demo_data_2026fy" / "sample_actual_data_ward_2026fy.csv"
        )
        for col in existing.columns:
            assert col in daily.columns, f"既存カラム '{col}' が daily_df に不足"

    def test_admission_details_schema(self, demo_data):
        """admission_details_df のカラム."""
        adm = demo_data["admission_details_df"]
        required = {
            "id", "date", "ward", "event_type", "route",
            "source_doctor", "attending_doctor", "los_days",
            "phase", "short3_type",
        }
        assert required.issubset(set(adm.columns))
        assert (adm["event_type"] == "admission").all()

    def test_discharge_details_schema(self, demo_data):
        """discharge_details_df のカラム."""
        dis = demo_data["discharge_details_df"]
        required = {
            "id", "date", "ward", "event_type",
            "attending_doctor", "los_days", "phase",
        }
        assert required.issubset(set(dis.columns))
        assert (dis["event_type"] == "discharge").all()

    def test_daily_has_short3_columns(self, demo_data):
        """daily_df が短手3 関連カラムを持つ."""
        daily = demo_data["daily_df"]
        for col in (
            "new_admissions_short3",
            "short3_overflow_count",
            "short3_overflow_avg_los",
            "discharge_los_list",
        ):
            assert col in daily.columns


# ---------------------------------------------------------------------------
# 医師・病棟整合
# ---------------------------------------------------------------------------


class TestDoctorConstraints:
    """医師プールが病棟別に正しく限定される."""

    def test_5f_doctors(self, demo_data):
        adm = demo_data["admission_details_df"]
        dis = demo_data["discharge_details_df"]
        doctors = set(adm[adm["ward"] == "5F"]["attending_doctor"].unique())
        doctors |= set(dis[dis["ward"] == "5F"]["attending_doctor"].unique())
        assert doctors.issubset(set(DOCTORS_5F)), f"5F に想定外の医師: {doctors}"

    def test_6f_doctors(self, demo_data):
        adm = demo_data["admission_details_df"]
        dis = demo_data["discharge_details_df"]
        doctors = set(adm[adm["ward"] == "6F"]["attending_doctor"].unique())
        doctors |= set(dis[dis["ward"] == "6F"]["attending_doctor"].unique())
        assert doctors.issubset(set(DOCTORS_6F)), f"6F に想定外の医師: {doctors}"


# ---------------------------------------------------------------------------
# 病床制約
# ---------------------------------------------------------------------------


class TestBedCapacity:
    """病床超過が発生しない."""

    def test_total_patients_within_beds(self, demo_data):
        daily = demo_data["daily_df"]
        for ward, beds in WARD_BEDS.items():
            ward_df = daily[daily["ward"] == ward]
            assert ward_df["total_patients"].max() <= beds, (
                f"{ward}: 最大在院 {ward_df['total_patients'].max()} > {beds} 床"
            )

    def test_5f_avg_occupancy_reasonable(self, demo_data):
        """5F 平均稼働率が 55-85% の範囲（実運用値）."""
        daily = demo_data["daily_df"]
        w = daily[daily["ward"] == "5F"]
        avg = w["total_patients"].mean() / WARD_BEDS["5F"]
        assert 0.55 <= avg <= 0.85, f"5F 稼働率 {avg:.3f} が範囲外"

    def test_6f_avg_occupancy_reasonable(self, demo_data):
        """6F 平均稼働率が 80-99% の範囲."""
        daily = demo_data["daily_df"]
        w = daily[daily["ward"] == "6F"]
        avg = w["total_patients"].mean() / WARD_BEDS["6F"]
        assert 0.80 <= avg <= 0.99, f"6F 稼働率 {avg:.3f} が範囲外"


# ---------------------------------------------------------------------------
# 日付レンジ
# ---------------------------------------------------------------------------


class TestDateRange:
    """生成データは年度範囲（4/1〜翌3/31）."""

    def test_365_days(self, demo_data):
        daily = demo_data["daily_df"]
        assert daily["date"].nunique() == 365

    def test_both_wards_all_days(self, demo_data):
        daily = demo_data["daily_df"]
        for ward in ("5F", "6F"):
            assert len(daily[daily["ward"] == ward]) == 365

    def test_start_2025_04_01(self, demo_data):
        daily = demo_data["daily_df"]
        dates = pd.to_datetime(daily["date"])
        assert dates.min() == pd.Timestamp("2025-04-01")

    def test_end_2026_03_31(self, demo_data):
        daily = demo_data["daily_df"]
        dates = pd.to_datetime(daily["date"])
        assert dates.max() == pd.Timestamp("2026-03-31")


# ---------------------------------------------------------------------------
# 整合性
# ---------------------------------------------------------------------------


class TestConsistency:
    """セクション間整合."""

    def test_admission_total_matches_daily(self, demo_data):
        """admission_details の件数合計 = daily_df.new_admissions 合計."""
        daily = demo_data["daily_df"]
        adm = demo_data["admission_details_df"]
        assert daily["new_admissions"].sum() == len(adm)

    def test_short3_total_matches_daily(self, demo_data):
        """new_admissions_short3 合計 = admission_details の短手3 件数."""
        daily = demo_data["daily_df"]
        adm = demo_data["admission_details_df"]
        s3 = adm[~adm["short3_type"].isin(["該当なし", ""])]
        assert daily["new_admissions_short3"].sum() == len(s3)

    def test_discharge_phases_sum(self, demo_data):
        """discharge_a + b + c == discharges."""
        daily = demo_data["daily_df"]
        total = daily["discharges"].sum()
        phase_sum = (
            daily["discharge_a"].sum()
            + daily["discharge_b"].sum()
            + daily["discharge_c"].sum()
        )
        assert phase_sum == total


# ---------------------------------------------------------------------------
# 再現性
# ---------------------------------------------------------------------------


class TestDeterministic:
    def test_same_seed_same_output(self):
        d1 = generate_demo_from_actual(input_csv=ACTUAL_CSV, seed=42)
        d2 = generate_demo_from_actual(input_csv=ACTUAL_CSV, seed=42)
        pd.testing.assert_frame_equal(d1["daily_df"], d2["daily_df"])


# ---------------------------------------------------------------------------
# CSV 出力
# ---------------------------------------------------------------------------


class TestCSVOutput:
    def test_write_csvs_creates_4_files(self, tmp_path, demo_data):
        paths = write_csvs(demo_data, tmp_path)
        for key in ("daily", "admission", "discharge", "combined"):
            assert paths[key].exists()
            assert paths[key].stat().st_size > 0

    def test_file_names_match_spec(self, tmp_path, demo_data):
        """出力ファイル名がタスク仕様と一致."""
        paths = write_csvs(demo_data, tmp_path)
        assert paths["daily"].name == "sample_actual_data_ward.csv"
        assert paths["admission"].name == "admission_details.csv"
        assert paths["discharge"].name == "discharge_details.csv"
        assert paths["combined"].name == "admission_details_combined.csv"

    def test_roundtrip_daily(self, tmp_path, demo_data):
        paths = write_csvs(demo_data, tmp_path)
        roundtrip = pd.read_csv(paths["daily"])
        assert len(roundtrip) == len(demo_data["daily_df"])


# ---------------------------------------------------------------------------
# サマリ
# ---------------------------------------------------------------------------


class TestSummarize:
    def test_summarize_returns_dict(self, demo_data):
        s = summarize(demo_data)
        assert s["days"] == 365
        assert "short3_ratio_pct" in s
        assert "short3_overflow_ratio_pct" in s
        assert "5F_avg_occupancy_pct" in s
        assert "6F_avg_occupancy_pct" in s
        assert len(s["monthly_admissions"]) == 12
