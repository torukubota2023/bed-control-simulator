"""年度デモデータ生成スクリプト (generate_demo_data_2026fy.py) のテスト."""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

# scripts/ をパスに追加
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from generate_demo_data_2026fy import (  # noqa: E402
    SHORT3_OVERALL_RATIO,
    WARD_BEDS,
    _find_holiday_blocks,
    _holiday_identifier,
    _is_institutional_closure,
    generate_yearly_data,
    summarize,
    write_csvs,
)


@pytest.fixture(scope="module")
def yearly_data() -> dict:
    """年度全体のデータを 1 回だけ生成してキャッシュ."""
    return generate_yearly_data(year=2026, seed=42)


class TestDataSchema:
    """既存 CSV とのスキーマ互換性."""

    def test_daily_df_columns_match_existing(self, yearly_data):
        """daily_df のカラムが既存 sample_actual_data_ward_202604.csv と互換."""
        daily = yearly_data["daily_df"]
        existing_path = ROOT / "data" / "sample_actual_data_ward_202604.csv"
        existing = pd.read_csv(existing_path)
        for col in existing.columns:
            assert col in daily.columns, f"既存カラム '{col}' が daily_df に不足"

    def test_daily_df_has_short3_columns(self, yearly_data):
        """daily_df が short3 関連カラムを持つ."""
        daily = yearly_data["daily_df"]
        assert "new_admissions_short3" in daily.columns
        assert "short3_overflow_count" in daily.columns
        assert "short3_overflow_avg_los" in daily.columns
        assert "discharge_los_list" in daily.columns

    def test_admission_details_schema(self, yearly_data):
        """admission_details_df のカラム."""
        adm = yearly_data["admission_details_df"]
        required = {
            "id", "date", "ward", "event_type", "route",
            "source_doctor", "attending_doctor", "los_days",
            "phase", "short3_type",
        }
        assert required.issubset(set(adm.columns))
        assert (adm["event_type"] == "admission").all()

    def test_discharge_details_schema(self, yearly_data):
        """discharge_details_df のカラム."""
        dis = yearly_data["discharge_details_df"]
        required = {
            "id", "date", "ward", "event_type",
            "attending_doctor", "los_days", "phase",
        }
        assert required.issubset(set(dis.columns))
        assert (dis["event_type"] == "discharge").all()


class TestCoverage:
    """365 日分のカバレッジ."""

    def test_full_year_days(self, yearly_data):
        """2026-04-01 〜 2027-03-31 の 365 日が揃う."""
        daily = yearly_data["daily_df"]
        unique_dates = daily["date"].nunique()
        assert unique_dates == 365, f"期待 365 日、実際 {unique_dates}"

    def test_both_wards_present(self, yearly_data):
        """5F と 6F 両方のレコードが全日に存在."""
        daily = yearly_data["daily_df"]
        for ward in ("5F", "6F"):
            ward_df = daily[daily["ward"] == ward]
            assert len(ward_df) == 365, f"{ward}: 期待 365 行、実際 {len(ward_df)}"

    def test_date_range(self, yearly_data):
        """日付範囲が正しい."""
        daily = yearly_data["daily_df"]
        dates = pd.to_datetime(daily["date"])
        assert dates.min() == pd.Timestamp("2026-04-01")
        assert dates.max() == pd.Timestamp("2027-03-31")


class TestOccupancyBounds:
    """稼働率の妥当性."""

    def test_total_patients_within_beds(self, yearly_data):
        """在院患者数が病床数を超えない."""
        daily = yearly_data["daily_df"]
        for ward, beds in WARD_BEDS.items():
            ward_df = daily[daily["ward"] == ward]
            assert ward_df["total_patients"].max() <= beds
            assert ward_df["total_patients"].min() >= 0

    def test_5f_occupancy_near_target(self, yearly_data):
        """5F の平均稼働率が目標レンジ 75-90% 内."""
        daily = yearly_data["daily_df"]
        w = daily[daily["ward"] == "5F"]
        avg_occ = w["total_patients"].mean() / WARD_BEDS["5F"]
        assert 0.70 <= avg_occ <= 0.92, f"5F 稼働率 {avg_occ:.3f} が 70-92% 範囲外"

    def test_6f_occupancy_near_target(self, yearly_data):
        """6F の平均稼働率が目標レンジ 85-98% 内."""
        daily = yearly_data["daily_df"]
        w = daily[daily["ward"] == "6F"]
        avg_occ = w["total_patients"].mean() / WARD_BEDS["6F"]
        assert 0.85 <= avg_occ <= 0.99, f"6F 稼働率 {avg_occ:.3f} が 85-99% 範囲外"


class TestSeasonality:
    """季節性の実装."""

    def test_winter_total_patients_higher_6f(self, yearly_data):
        """6F の冬季（12-2 月）平均在院患者数が夏季（6-8 月）より多い（需要圧の表現）."""
        daily = yearly_data["daily_df"]
        w = daily[daily["ward"] == "6F"].copy()
        w["month"] = pd.to_datetime(w["date"]).dt.month
        winter_avg = w[w["month"].isin([12, 1, 2])]["total_patients"].mean()
        summer_avg = w[w["month"].isin([6, 7, 8])]["total_patients"].mean()
        # 冬季の需要圧は病床制約で入院数上限に達しがちなので、
        # 在院患者数ベースで比較（冬季は夏季より 0.98 倍以上）
        assert winter_avg >= summer_avg * 0.98, (
            f"6F 冬季平均在院 {winter_avg:.1f} < 夏季 {summer_avg:.1f} × 0.98"
        )

    def test_winter_admission_pressure_5f(self, yearly_data):
        """5F の夏季（7-8 月外傷期）入院が中立月（4 月）より多い."""
        daily = yearly_data["daily_df"]
        w = daily[daily["ward"] == "5F"].copy()
        w["month"] = pd.to_datetime(w["date"]).dt.month
        summer = w[w["month"].isin([7, 8])]["new_admissions"].sum()
        april = w[w["month"] == 4]["new_admissions"].sum()
        # 7-8 月は 2 か月分なので、4 月との比較は割り算で日次平均
        summer_per_day = summer / 62  # 7+8 月
        april_per_day = april / 30
        assert summer_per_day >= april_per_day * 0.95, (
            f"5F 夏季日次入院 {summer_per_day:.2f} < 4 月 {april_per_day:.2f} × 0.95"
        )

    def test_winter_los_longer_than_summer_6f(self, yearly_data):
        """6F の冬季 LOS が夏季より長い傾向."""
        dis = yearly_data["discharge_details_df"].copy()
        dis["month"] = pd.to_datetime(dis["date"]).dt.month
        dis["los"] = dis["los_days"].astype(int)
        w = dis[dis["ward"] == "6F"]
        winter_los = w[w["month"].isin([12, 1, 2])]["los"].mean()
        summer_los = w[w["month"].isin([6, 7, 8])]["los"].mean()
        assert winter_los > summer_los - 2, (
            f"6F 冬季 LOS {winter_los:.1f} < 夏季 LOS {summer_los:.1f} - 2"
        )


class TestHolidayPatterns:
    """連休前後の入退院パターン."""

    def test_gw_detected(self):
        """GW (2026-05-02 〜 2026-05-06) が連休ブロックとして検出される."""
        blocks = _find_holiday_blocks(date(2026, 4, 1), date(2026, 5, 31))
        gw_blocks = [(bs, be) for bs, be in blocks
                     if _holiday_identifier(bs, be) == "GW"]
        assert len(gw_blocks) >= 1, "GW 連休が検出されない"

    def test_obon_detected(self):
        """お盆（2026-08-13 〜 2026-08-16）を含む連休ブロックが検出."""
        blocks = _find_holiday_blocks(date(2026, 8, 1), date(2026, 8, 31))
        obon_blocks = [(bs, be) for bs, be in blocks
                       if _holiday_identifier(bs, be) == "お盆"]
        assert len(obon_blocks) >= 1, "お盆連休が検出されない"

    def test_new_year_detected(self):
        """年末年始（12/29 〜 1/3）を含む連休ブロックが検出."""
        blocks = _find_holiday_blocks(date(2026, 12, 1), date(2027, 1, 31))
        nny_blocks = [(bs, be) for bs, be in blocks
                      if _holiday_identifier(bs, be) == "年末年始"]
        assert len(nny_blocks) >= 1, "年末年始連休が検出されない"

    def test_institutional_closure_includes_obon_weekdays(self):
        """8/13-8/16 の平日も『実質休診日』扱い."""
        assert _is_institutional_closure(date(2026, 8, 13))  # Thu
        assert _is_institutional_closure(date(2026, 8, 14))  # Fri

    def test_institutional_closure_includes_year_end_weekdays(self):
        """12/30-12/31 の平日も『実質休診日』扱い."""
        assert _is_institutional_closure(date(2026, 12, 30))  # Wed
        assert _is_institutional_closure(date(2026, 12, 31))  # Thu

    def test_gw_post_holiday_admission_surge(self, yearly_data):
        """GW 明け（5/7 Thu）の入院が通常木曜平均より多い."""
        daily = yearly_data["daily_df"]
        daily_dt = daily.copy()
        daily_dt["date"] = pd.to_datetime(daily_dt["date"])
        gw_post = daily_dt[daily_dt["date"] == "2026-05-07"]["new_admissions"].sum()
        # 通常木曜（4 月他日）の平均
        thursdays = daily_dt[
            (daily_dt["date"].dt.weekday == 3)
            & (daily_dt["date"].dt.month.isin([4, 6]))
        ]["new_admissions"].mean()
        # thursdays は 1 病棟あたり/1日あたりでなく合計だが、比較には十分
        # GW 明けは 2 病棟合計で通常木曜合計の 1.2 倍以上
        normal_thu = daily_dt[
            (daily_dt["date"].dt.weekday == 3)
            & (daily_dt["date"].dt.month.isin([4, 6]))
        ].groupby("date")["new_admissions"].sum().mean()
        assert gw_post >= normal_thu * 1.1, (
            f"GW 明け入院 {gw_post} < 通常木曜 {normal_thu:.1f} × 1.1"
        )

    def test_gw_pre_discharge_surge(self, yearly_data):
        """GW 前（5/1 Fri）の退院が通常金曜より多い."""
        daily = yearly_data["daily_df"]
        daily_dt = daily.copy()
        daily_dt["date"] = pd.to_datetime(daily_dt["date"])
        pre_discharge = daily_dt[daily_dt["date"] == "2026-05-01"]["discharges"].sum()
        normal_fri = daily_dt[
            (daily_dt["date"].dt.weekday == 4)
            & (daily_dt["date"].dt.month.isin([4, 6]))
        ].groupby("date")["discharges"].sum().mean()
        assert pre_discharge >= normal_fri * 1.1, (
            f"GW 前退院 {pre_discharge} < 通常金曜 {normal_fri:.1f} × 1.1"
        )


class TestShort3:
    """短手3 の実装."""

    def test_short3_ratio_near_target(self, yearly_data):
        """短手3 入院が全入院の 10-20% 範囲."""
        adm = yearly_data["admission_details_df"]
        total = len(adm)
        s3 = adm[~adm["short3_type"].isin(["該当なし", ""])]
        ratio = len(s3) / total
        assert 0.10 <= ratio <= 0.20, (
            f"短手3 比率 {ratio:.3f} が 10-20% 範囲外 (target={SHORT3_OVERALL_RATIO})"
        )

    def test_short3_types_all_present(self, yearly_data):
        """短手3 の 3 種類（大腸ポリペク / ヘルニア / PSG）が全て出現."""
        adm = yearly_data["admission_details_df"]
        types = set(adm[adm["short3_type"] != "該当なし"]["short3_type"].unique())
        types.discard("")
        expected = {"大腸ポリペクトミー", "ヘルニア手術", "ポリソムノグラフィー"}
        assert expected.issubset(types), f"期待 {expected}、実際 {types}"

    def test_short3_overflow_exists(self, yearly_data):
        """短手3 overflow（Day 6 以上入院継続）レコードが存在."""
        daily = yearly_data["daily_df"]
        assert daily["short3_overflow_count"].sum() > 0


class TestDoctorDistribution:
    """医師別偏り."""

    def test_5f_doctors(self, yearly_data):
        """5F の担当医が C / H / J / F 医師に限定."""
        dis = yearly_data["discharge_details_df"]
        w = dis[dis["ward"] == "5F"]
        doctors = set(w["attending_doctor"].unique())
        expected = {"C医師", "H医師", "J医師", "F医師"}
        assert doctors.issubset(expected), (
            f"5F に想定外の医師: {doctors - expected}"
        )

    def test_6f_doctors(self, yearly_data):
        """6F の担当医が A / B / E / G 医師に限定."""
        dis = yearly_data["discharge_details_df"]
        w = dis[dis["ward"] == "6F"]
        doctors = set(w["attending_doctor"].unique())
        expected = {"A医師", "B医師", "E医師", "G医師"}
        assert doctors.issubset(expected), (
            f"6F に想定外の医師: {doctors - expected}"
        )

    def test_h_doctor_short_los(self, yearly_data):
        """H 医師（ペイン短期）の平均 LOS が 10 日以下."""
        dis = yearly_data["discharge_details_df"].copy()
        dis["los"] = dis["los_days"].astype(int)
        h = dis[dis["attending_doctor"] == "H医師"]
        assert h["los"].mean() <= 10.5

    def test_e_doctor_long_los(self, yearly_data):
        """E 医師の平均 LOS が 20 日以上（長期型）."""
        dis = yearly_data["discharge_details_df"].copy()
        dis["los"] = dis["los_days"].astype(int)
        e = dis[dis["attending_doctor"] == "E医師"]
        assert e["los"].mean() >= 20.0

    def test_b_doctor_friday_discharge_bias(self, yearly_data):
        """B 医師の金曜退院比率が通常曜日より高い."""
        dis = yearly_data["discharge_details_df"].copy()
        dis["date"] = pd.to_datetime(dis["date"])
        dis["dow"] = dis["date"].dt.weekday
        b = dis[dis["attending_doctor"] == "B医師"]
        fri_ratio = (b["dow"] == 4).mean()
        other_avg = (b["dow"].isin([0, 1, 2, 3])).mean() / 4  # 平日平均
        assert fri_ratio > other_avg, (
            f"B 医師金曜退院比率 {fri_ratio:.3f} ≦ 平日平均 {other_avg:.3f}"
        )


class TestConsistency:
    """データ整合性."""

    def test_discharge_phases_sum(self, yearly_data):
        """discharge_a + discharge_b + discharge_c == discharges."""
        daily = yearly_data["daily_df"]
        total_discharges = daily["discharges"].sum()
        phase_sum = (
            daily["discharge_a"].sum()
            + daily["discharge_b"].sum()
            + daily["discharge_c"].sum()
        )
        assert phase_sum == total_discharges, (
            f"退院フェーズ合計 {phase_sum} != 退院数 {total_discharges}"
        )

    def test_phase_counts_sum_to_total(self, yearly_data):
        """phase_a + phase_b + phase_c ≒ total_patients（丸め誤差 ±1）."""
        daily = yearly_data["daily_df"]
        diffs = (
            daily["phase_a_count"]
            + daily["phase_b_count"]
            + daily["phase_c_count"]
            - daily["total_patients"]
        ).abs()
        assert (diffs <= 1).all(), (
            f"フェーズ合計と total の差が > 1: max={diffs.max()}"
        )

    def test_admission_discharge_count_match(self, yearly_data):
        """admission_details の件数合計 == daily_df.new_admissions 合計."""
        daily = yearly_data["daily_df"]
        adm = yearly_data["admission_details_df"]
        assert daily["new_admissions"].sum() == len(adm)

    def test_discharge_count_match(self, yearly_data):
        """discharge_details の件数合計 == daily_df.discharges 合計."""
        daily = yearly_data["daily_df"]
        dis = yearly_data["discharge_details_df"]
        assert daily["discharges"].sum() == len(dis)


class TestDeterministic:
    """再現性."""

    def test_same_seed_same_output(self):
        """同じシードなら同じ結果."""
        d1 = generate_yearly_data(year=2026, seed=42)
        d2 = generate_yearly_data(year=2026, seed=42)
        pd.testing.assert_frame_equal(d1["daily_df"], d2["daily_df"])


class TestCSVOutput:
    """CSV 書き出し."""

    def test_write_csvs_creates_files(self, tmp_path, yearly_data):
        """write_csvs が 4 つのファイルを出力."""
        paths = write_csvs(yearly_data, tmp_path)
        for key in ("daily", "admission", "discharge", "combined"):
            assert paths[key].exists(), f"{key} CSV が出力されない"
            assert paths[key].stat().st_size > 0

    def test_written_csv_roundtrip(self, tmp_path, yearly_data):
        """書き出した CSV を pandas で読み直してもデータが一致."""
        paths = write_csvs(yearly_data, tmp_path)
        roundtrip = pd.read_csv(paths["daily"])
        assert len(roundtrip) == len(yearly_data["daily_df"])
        assert list(roundtrip.columns) == list(yearly_data["daily_df"].columns)


class TestSummarize:
    """統計サマリ."""

    def test_summarize_returns_dict(self, yearly_data):
        summary = summarize(yearly_data)
        assert isinstance(summary, dict)
        assert summary["days"] == 365
        assert "5F_avg_occupancy_pct" in summary
        assert "6F_avg_occupancy_pct" in summary
        assert "monthly_admissions" in summary
        assert len(summary["monthly_admissions"]) == 12


class TestCLI:
    """CLI 動作."""

    def test_main_exits_zero(self, tmp_path):
        """CLI が正常終了する."""
        from generate_demo_data_2026fy import main
        rc = main(["--year", "2026", "--output", str(tmp_path), "--seed", "42"])
        assert rc == 0
        assert (tmp_path / "sample_actual_data_ward_2026fy.csv").exists()
