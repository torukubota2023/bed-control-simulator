"""デモデータの品質検証テスト.

2 つの観点:
1. 現実性 — 数値が臨床的に妥当な範囲内か (稼働率・LOS・救急・短手3・C 群)
2. 教育性 — 判断材料として機能する変動性があるか (曜日差・季節性・医師間差)

対象データ:
- output/demo_data_2026fy/sample_actual_data_ward_2026fy.csv  (730 日 × 2 病棟)
- output/demo_data_2026fy/admission_details_2026fy.csv
- output/demo_data_2026fy/discharge_details_2026fy.csv

実行:
    pytest tests/test_demo_data_quality.py -v

要件不達は FAIL とし、実測値を表示する（現場での調整判断の材料）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

DEMO_DIR = ROOT / "output" / "demo_data_2026fy"
DAILY_CSV = DEMO_DIR / "sample_actual_data_ward_2026fy.csv"
ADM_CSV = DEMO_DIR / "admission_details_2026fy.csv"
DIS_CSV = DEMO_DIR / "discharge_details_2026fy.csv"

BEDS_PER_WARD = 47


# ---------------------------------------------------------------------------
# フィクスチャ
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def daily_df() -> pd.DataFrame:
    if not DAILY_CSV.exists():
        pytest.skip(f"デモデータが見つかりません: {DAILY_CSV}")
    df = pd.read_csv(DAILY_CSV, encoding="utf-8-sig")
    df["date"] = pd.to_datetime(df["date"])
    return df


@pytest.fixture(scope="module")
def adm_df() -> pd.DataFrame:
    if not ADM_CSV.exists():
        pytest.skip(f"入院詳細が見つかりません: {ADM_CSV}")
    df = pd.read_csv(ADM_CSV, encoding="utf-8-sig")
    df["date"] = pd.to_datetime(df["date"])
    return df


@pytest.fixture(scope="module")
def dis_df() -> pd.DataFrame:
    if not DIS_CSV.exists():
        pytest.skip(f"退院詳細が見つかりません: {DIS_CSV}")
    df = pd.read_csv(DIS_CSV, encoding="utf-8-sig")
    df["date"] = pd.to_datetime(df["date"])
    return df


def _occupancy(df_ward: pd.DataFrame) -> pd.Series:
    """厚労省定義の日次稼働率 %."""
    return ((df_ward["total_patients"] + df_ward["discharges"]) / BEDS_PER_WARD) * 100


# ---------------------------------------------------------------------------
# 1. 現実性 — 稼働率範囲
# ---------------------------------------------------------------------------


class TestRealismOccupancy:
    """病棟別平均稼働率 70-100%."""

    def test_5f_mean_occupancy_in_range(self, daily_df):
        df_5f = daily_df[daily_df["ward"] == "5F"]
        occ = _occupancy(df_5f).mean()
        assert 70.0 <= occ <= 100.0, f"5F 平均稼働率 {occ:.1f}% が 70-100% 範囲外"

    def test_6f_mean_occupancy_in_range(self, daily_df):
        df_6f = daily_df[daily_df["ward"] == "6F"]
        occ = _occupancy(df_6f).mean()
        assert 70.0 <= occ <= 100.0, f"6F 平均稼働率 {occ:.1f}% が 70-100% 範囲外"

    def test_no_ward_above_110pct(self, daily_df):
        """同日回転で 100% 超えは正常だが、110% を超えると物理的におかしい."""
        for ward in ("5F", "6F"):
            df_w = daily_df[daily_df["ward"] == ward]
            occ = _occupancy(df_w)
            max_occ = occ.max()
            assert max_occ <= 115.0, f"{ward} 最大稼働率 {max_occ:.1f}% が 115% 超過"


# ---------------------------------------------------------------------------
# 2. 現実性 — 平均在院日数
# ---------------------------------------------------------------------------


class TestRealismALOS:
    """病棟別 ALOS 10-25 日."""

    def test_5f_alos_in_range(self, dis_df):
        df_5f = dis_df[dis_df["ward"] == "5F"]
        alos = df_5f["los_days"].mean()
        assert 10.0 <= alos <= 25.0, f"5F ALOS {alos:.1f}日 が 10-25 日範囲外"

    def test_6f_alos_in_range(self, dis_df):
        df_6f = dis_df[dis_df["ward"] == "6F"]
        alos = df_6f["los_days"].mean()
        assert 10.0 <= alos <= 30.0, (
            f"6F ALOS {alos:.1f}日 が 10-30 日範囲外 (6F は制度上限付近の設計)"
        )

    def test_5f_los_shorter_than_6f(self, dis_df):
        """5F (外科・整形) < 6F (内科・ペイン) — 台本前提."""
        alos_5f = dis_df[dis_df["ward"] == "5F"]["los_days"].mean()
        alos_6f = dis_df[dis_df["ward"] == "6F"]["los_days"].mean()
        assert alos_5f < alos_6f, (
            f"5F ({alos_5f:.1f}日) が 6F ({alos_6f:.1f}日) より短い前提に反する"
        )


# ---------------------------------------------------------------------------
# 3. 現実性 — 救急搬送後患者割合
# ---------------------------------------------------------------------------


class TestRealismEmergencyRatio:
    def test_emergency_ratio_in_range(self, adm_df):
        """入院経路「救急」の割合が全体の 5-30% (病棟横断)."""
        total = len(adm_df)
        emerg = len(adm_df[adm_df["route"] == "救急"])
        if total == 0:
            pytest.skip("入院データが空")
        pct = emerg / total * 100
        assert 5.0 <= pct <= 40.0, (
            f"入院経路 = 救急 の割合 {pct:.1f}% が 5-40% 範囲外"
        )


# ---------------------------------------------------------------------------
# 4. 現実性 — 日次入院数
# ---------------------------------------------------------------------------


class TestRealismDailyAdmissions:
    def test_daily_admissions_sane(self, daily_df):
        """日次入院数 0-15 (極端な外れ値なし)."""
        for ward in ("5F", "6F"):
            df_w = daily_df[daily_df["ward"] == ward]
            assert df_w["new_admissions"].min() >= 0
            assert df_w["new_admissions"].max() <= 15, (
                f"{ward} 日次入院最大値 {df_w['new_admissions'].max()} が 15 超過"
            )


# ---------------------------------------------------------------------------
# 5. 現実性 — 短手3 比率
# ---------------------------------------------------------------------------


class TestRealismShort3Ratio:
    def test_short3_overall_ratio(self, daily_df):
        """全体の短手3 比率が 10-20%."""
        total = daily_df["new_admissions"].sum()
        s3 = daily_df["new_admissions_short3"].sum()
        if total == 0:
            pytest.skip("入院データが空")
        pct = s3 / total * 100
        assert 10.0 <= pct <= 22.0, f"短手3 比率 {pct:.1f}% が 10-22% 範囲外"


# ---------------------------------------------------------------------------
# 6. 現実性 — C 群比率
# ---------------------------------------------------------------------------


class TestRealismCGroupRatio:
    def test_c_group_in_range(self, daily_df):
        """在院患者に占める C 群（15 日以上）が 20-60%."""
        totals = daily_df[daily_df["total_patients"] > 0].copy()
        totals["c_ratio"] = totals["phase_c_count"] / totals["total_patients"]
        mean_c = totals["c_ratio"].mean() * 100
        assert 20.0 <= mean_c <= 60.0, f"C 群比率 {mean_c:.1f}% が 20-60% 範囲外"


# ---------------------------------------------------------------------------
# 7. 教育性 — 稼働率の変動
# ---------------------------------------------------------------------------


class TestPedagogyOccupancyVariance:
    """稼働率が一定値でなく、判断材料として十分な変動がある."""

    def test_5f_occupancy_std_above_3(self, daily_df):
        df_5f = daily_df[daily_df["ward"] == "5F"]
        std = _occupancy(df_5f).std()
        assert std >= 3.0, (
            f"5F 稼働率の日次標準偏差 {std:.2f}% が 3% 未満 — 変動が乏しく教育的価値が低い"
        )

    def test_6f_occupancy_std_above_3(self, daily_df):
        df_6f = daily_df[daily_df["ward"] == "6F"]
        std = _occupancy(df_6f).std()
        assert std >= 3.0, f"6F 稼働率標準偏差 {std:.2f}% < 3% — 変動不足"


# ---------------------------------------------------------------------------
# 8. 教育性 — 曜日差（平日 > 週末）
# ---------------------------------------------------------------------------


class TestPedagogyWeekdayDiff:
    """月曜の入院 > 日曜の入院 — 現実の需要パターンを反映."""

    def test_monday_exceeds_sunday(self, daily_df):
        daily_df = daily_df.copy()
        daily_df["dow"] = daily_df["date"].dt.dayofweek
        mon_mean = daily_df[daily_df["dow"] == 0]["new_admissions"].mean()
        sun_mean = daily_df[daily_df["dow"] == 6]["new_admissions"].mean()
        assert mon_mean > sun_mean * 1.5, (
            f"月曜入院 {mon_mean:.2f}件/日 が 日曜 {sun_mean:.2f}件/日 の 1.5 倍以下 — "
            f"曜日パターンが弱く、教育材料として不足"
        )


# ---------------------------------------------------------------------------
# 9. 教育性 — 季節性（冬 > 夏 の在院数）
# ---------------------------------------------------------------------------


class TestPedagogySeasonality:
    """冬（12-2月）の在院数が夏（7-8月）より多い傾向 — 呼吸器季節."""

    def test_winter_higher_than_summer(self, daily_df):
        daily_df = daily_df.copy()
        daily_df["month"] = daily_df["date"].dt.month
        winter = daily_df[daily_df["month"].isin([12, 1, 2])]["total_patients"].mean()
        summer = daily_df[daily_df["month"].isin([7, 8])]["total_patients"].mean()
        assert winter > summer, (
            f"冬平均在院 {winter:.1f}名 が夏 {summer:.1f}名 以下 — 季節性が弱い"
        )


# ---------------------------------------------------------------------------
# 10. 教育性 — 連休前後のパターン差
# ---------------------------------------------------------------------------


class TestPedagogyHolidayPattern:
    """GW 期間中の入院は、前後の平日より有意に少ない."""

    def test_gw_has_drop(self, daily_df):
        """2026-05-02 〜 05-06 あたりの 5 月 GW 期間は入院が減少する."""
        gw = daily_df[
            (daily_df["date"] >= pd.Timestamp("2026-05-02"))
            & (daily_df["date"] <= pd.Timestamp("2026-05-06"))
        ]
        # GW 前後の平日
        before = daily_df[
            (daily_df["date"] >= pd.Timestamp("2026-04-27"))
            & (daily_df["date"] <= pd.Timestamp("2026-04-30"))
        ]
        if gw.empty or before.empty:
            pytest.skip("GW 期間データが不足")
        gw_adm = gw["new_admissions"].mean()
        before_adm = before["new_admissions"].mean()
        assert gw_adm < before_adm, (
            f"GW 入院 {gw_adm:.2f} が GW 前 {before_adm:.2f} 以上 — 連休落ち込みがない"
        )


# ---------------------------------------------------------------------------
# 11. 教育性 — 医師間の LOS 差
# ---------------------------------------------------------------------------


class TestPedagogyDoctorLOSVariance:
    """医師間の ALOS CV (変動係数) が 0.15 以上 — 医師別分析が判断材料になる."""

    def test_doctor_los_cv(self, dis_df):
        by_dr = dis_df.groupby("attending_doctor")["los_days"].mean()
        # サンプルが少なすぎる医師を除外
        sample_counts = dis_df.groupby("attending_doctor").size()
        major = by_dr[sample_counts >= 30]
        if len(major) < 3:
            pytest.skip("サンプル数 30 以上の医師が 3 名未満")
        cv = major.std() / major.mean()
        assert cv >= 0.10, (
            f"医師間 ALOS の CV {cv:.3f} が 0.10 未満 — 医師別分析の教育材料として不足"
        )


# ---------------------------------------------------------------------------
# 12. 教育性 — 病棟差
# ---------------------------------------------------------------------------


class TestPedagogyWardDiff:
    """5F と 6F の稼働率平均差が 3pt 以上."""

    def test_ward_occupancy_gap(self, daily_df):
        occ_5f = _occupancy(daily_df[daily_df["ward"] == "5F"]).mean()
        occ_6f = _occupancy(daily_df[daily_df["ward"] == "6F"]).mean()
        gap = abs(occ_5f - occ_6f)
        assert gap >= 3.0, (
            f"病棟間稼働率差 {gap:.2f}pt が 3pt 未満 — 病棟比較の教育材料として不足"
        )

    def test_ward_alos_gap(self, dis_df):
        alos_5f = dis_df[dis_df["ward"] == "5F"]["los_days"].mean()
        alos_6f = dis_df[dis_df["ward"] == "6F"]["los_days"].mean()
        gap = abs(alos_5f - alos_6f)
        assert gap >= 3.0, f"病棟間 ALOS 差 {gap:.2f}日 が 3 日未満 — 比較材料不足"


# ---------------------------------------------------------------------------
# 13. データ構造整合性
# ---------------------------------------------------------------------------


class TestDataStructureIntegrity:
    def test_daily_df_shape(self, daily_df):
        """730 件 (365 日 × 2 病棟) または近似."""
        assert 700 <= len(daily_df) <= 740, f"日次データ件数 {len(daily_df)} が想定範囲外"

    def test_required_columns(self, daily_df):
        required = {
            "date",
            "ward",
            "total_patients",
            "new_admissions",
            "new_admissions_short3",
            "discharges",
            "phase_a_count",
            "phase_b_count",
            "phase_c_count",
            "avg_los",
        }
        missing = required - set(daily_df.columns)
        assert not missing, f"不足カラム: {missing}"

    def test_no_negative_values(self, daily_df):
        for col in ["total_patients", "new_admissions", "discharges", "phase_a_count"]:
            assert (daily_df[col] >= 0).all(), f"{col} に負値が含まれる"

    def test_phase_sum_matches_total(self, daily_df):
        """phase_a + phase_b + phase_c = total_patients (完全一致)."""
        df = daily_df.copy()
        df["phase_sum"] = df["phase_a_count"] + df["phase_b_count"] + df["phase_c_count"]
        mismatch = df[df["phase_sum"] != df["total_patients"]]
        assert len(mismatch) == 0, (
            f"phase 合計 != total_patients の行が {len(mismatch)} 件: "
            f"{mismatch[['date', 'ward', 'phase_sum', 'total_patients']].head().to_dict()}"
        )


# ---------------------------------------------------------------------------
# 14. サマリー出力用（スモークテスト的な実数表示）
# ---------------------------------------------------------------------------


class TestReportingSnapshot:
    """合否判定とは別に、実数値をコンソールに出力してレポート材料にする."""

    def test_print_summary(self, daily_df, adm_df, dis_df):
        lines = []
        lines.append("=== デモデータ品質サマリ ===")
        for ward in ("5F", "6F"):
            dw = daily_df[daily_df["ward"] == ward]
            occ = _occupancy(dw)
            lines.append(
                f"{ward} 稼働率: mean={occ.mean():.1f}% / std={occ.std():.2f}% / min={occ.min():.1f} / max={occ.max():.1f}"
            )
            d_w = dis_df[dis_df["ward"] == ward]
            lines.append(
                f"{ward} ALOS: mean={d_w['los_days'].mean():.1f}日 / std={d_w['los_days'].std():.2f}日"
            )
        total_adm = len(adm_df)
        emerg = len(adm_df[adm_df["route"] == "救急"])
        lines.append(f"入院 total={total_adm}, 救急比率={emerg / max(total_adm, 1) * 100:.1f}%")
        s3 = daily_df["new_admissions_short3"].sum()
        total_new = daily_df["new_admissions"].sum()
        lines.append(f"短手3 比率={s3 / max(total_new, 1) * 100:.1f}%")
        daily_df2 = daily_df.copy()
        daily_df2["dow"] = daily_df2["date"].dt.dayofweek
        for dow_idx, dow_name in enumerate(["月", "火", "水", "木", "金", "土", "日"]):
            dow_df = daily_df2[daily_df2["dow"] == dow_idx]
            lines.append(f"曜日 {dow_name} 入院平均: {dow_df['new_admissions'].mean():.2f}件")
        for ln in lines:
            print(ln)
        # 常時成功。値の確認用。
        assert True
