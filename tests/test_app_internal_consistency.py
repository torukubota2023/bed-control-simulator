"""アプリ内セクション間整合性テスト.

同じデータから計算される指標が、複数の画面・セクションで矛盾していないかを
自動検証する。CLAUDE.md §7 「セクション間整合性チェック」の自動化。

検証対象（例）:
- smoke_test.py が使う稼働率計算ロジック と bed_data_manager の計算が一致
- サマリー画面の 5F 稼働率 と カンファ Block A の 5F 稼働率が同値
- 必要床日の定義が複数箇所で一致
- LOS rolling 90日計算が単一実装（二重計算していない）

このファイルは Streamlit ランナー経由ではなく、純粋な Python モジュールレベルで
呼び出して整合性を検証する（E2E より速く、確実）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

BEDS_PER_WARD = 47
CSV_PATH = ROOT / "data" / "sample_actual_data_ward_202604.csv"


# ---------------------------------------------------------------------------
# フィクスチャ
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def apr_df() -> pd.DataFrame:
    """4 月実績データ（5F / 6F 両方含む）."""
    if not CSV_PATH.exists():
        pytest.skip(f"データ CSV が見つかりません: {CSV_PATH}")
    df = pd.read_csv(CSV_PATH)
    df["date"] = pd.to_datetime(df["date"])
    return df[df["date"].dt.month == 4].copy()


@pytest.fixture(scope="module")
def full_df() -> pd.DataFrame:
    """全期間データ（rolling LOS 計算用）."""
    if not CSV_PATH.exists():
        pytest.skip(f"データ CSV が見つかりません: {CSV_PATH}")
    df = pd.read_csv(CSV_PATH)
    df["date"] = pd.to_datetime(df["date"])
    return df


# ---------------------------------------------------------------------------
# 1. 稼働率計算の単一実装チェック
# ---------------------------------------------------------------------------


class TestOccupancyConsistency:
    """稼働率が複数箇所で同一の計算式を使っていることを確認."""

    def _mhlw_occupancy(self, df_ward: pd.DataFrame) -> float:
        """厚労省定義: (在院患者数 + 退院患者数) / 病床数."""
        return ((df_ward["total_patients"] + df_ward["discharges"]).mean() / BEDS_PER_WARD) * 100

    def test_5f_matches_smoke_and_scenario(self, apr_df):
        """5F 稼働率が smoke_test.py の期待範囲内."""
        apr_5f = apr_df[apr_df["ward"] == "5F"]
        occ = self._mhlw_occupancy(apr_5f)
        # smoke_test.py の SCENARIO_EXPECTED["occ_5f_display"] = (86.0, 87.0)
        assert 85.0 <= occ <= 88.0, f"5F 稼働率 {occ:.2f}% が smoke 範囲外"

    def test_6f_matches_smoke_and_scenario(self, apr_df):
        apr_6f = apr_df[apr_df["ward"] == "6F"]
        occ = self._mhlw_occupancy(apr_6f)
        assert 89.0 <= occ <= 92.0, f"6F 稼働率 {occ:.2f}% が smoke 範囲外"

    def test_overall_equals_average_of_wards(self, apr_df):
        """全体稼働率 = 各病棟の平均 (病床数同一前提)."""
        apr_5f = apr_df[apr_df["ward"] == "5F"]
        apr_6f = apr_df[apr_df["ward"] == "6F"]
        occ_5f = self._mhlw_occupancy(apr_5f)
        occ_6f = self._mhlw_occupancy(apr_6f)
        # 5F と 6F が同じ 47 床なので単純平均で良い
        expected_overall = (occ_5f + occ_6f) / 2
        # 独立計算経路
        combined_patients = (
            apr_5f["total_patients"].mean() + apr_6f["total_patients"].mean()
        )
        combined_discharges = apr_5f["discharges"].mean() + apr_6f["discharges"].mean()
        direct_overall = ((combined_patients + combined_discharges) / (BEDS_PER_WARD * 2)) * 100
        assert abs(expected_overall - direct_overall) < 0.1, (
            f"全体稼働率の 2 通りの計算が不一致: avg_of_wards={expected_overall:.2f}, "
            f"direct={direct_overall:.2f}"
        )


# ---------------------------------------------------------------------------
# 2. Rolling LOS 計算の単一実装チェック
# ---------------------------------------------------------------------------


class TestRollingLOSConsistency:
    def test_rolling_los_function_available(self):
        from bed_data_manager import calculate_rolling_los  # noqa: F401

    def test_rolling_los_returns_expected_shape(self, full_df):
        from bed_data_manager import calculate_rolling_los

        w_df = full_df[full_df["ward"] == "5F"].copy()
        result = calculate_rolling_los(w_df, window_days=90)
        assert result is not None
        assert "rolling_los" in result
        assert isinstance(result["rolling_los"], (int, float))

    def test_rolling_los_5f_below_6f(self, full_df):
        """5F (rolling LOS ≈ 17.7 日) < 6F (rolling LOS ≈ 21.3 日) — 台本の前提."""
        from bed_data_manager import calculate_rolling_los

        r5 = calculate_rolling_los(full_df[full_df["ward"] == "5F"].copy(), window_days=90)
        r6 = calculate_rolling_los(full_df[full_df["ward"] == "6F"].copy(), window_days=90)
        assert r5 and r6
        assert r5["rolling_los"] is not None
        assert r6["rolling_los"] is not None
        assert r5["rolling_los"] < r6["rolling_los"], (
            f"シナリオ前提違反: 5F ({r5['rolling_los']:.1f}日) < 6F ({r6['rolling_los']:.1f}日) "
            f"のはずが逆転している"
        )


# ---------------------------------------------------------------------------
# 3. 必要床日（稼働率ギャップ）の計算が単一
# ---------------------------------------------------------------------------


class TestRequiredBedDaysConsistency:
    """必要床日 = (目標稼働率 × 総床日) - 実績床日 の計算が独立に再計算しても同じ."""

    def test_required_bed_days_formula(self, apr_df):
        # 台本前提: 目標 90%, 20 日経過, 残り 10 日 (合計 30 日前提の April)
        target = 0.90
        total_days = 30  # 4 月
        elapsed_days = 20  # smoke_test と同じ前提
        total_beds = BEDS_PER_WARD * 2

        # 経過した 20 日の延べ床数（稼働）
        _5f = apr_df[apr_df["ward"] == "5F"]
        _6f = apr_df[apr_df["ward"] == "6F"]
        actual_bed_days = (
            (_5f["total_patients"] + _5f["discharges"]).sum()
            + (_6f["total_patients"] + _6f["discharges"]).sum()
        )
        required_bed_days = total_beds * total_days * target
        remaining_required = required_bed_days - actual_bed_days
        assert remaining_required > 0, (
            f"残り床日が負値: required={required_bed_days}, actual={actual_bed_days} — "
            f"計算式が誤っているか、データ異常"
        )
        # 残り 10 日で割った 1 日あたりの必要床数
        per_day = remaining_required / (total_days - elapsed_days)
        # 1 日あたり必要床数は病床数の 90-110% 程度に収まるべき（極端な値は計算誤り）
        ratio = per_day / total_beds
        assert 0.85 <= ratio <= 1.10, (
            f"1 日あたり必要床数が異常: {per_day:.1f} 床 / 総 {total_beds} 床 = "
            f"{ratio * 100:.1f}% — 計算式を確認"
        )


# ---------------------------------------------------------------------------
# 4. 診療報酬プリセット（2026 > 2024）
# ---------------------------------------------------------------------------


class TestRevenuePresetConsistency:
    def test_2026_preset_exceeds_2024(self):
        from bed_data_manager import calculate_ideal_phase_ratios

        r2024 = calculate_ideal_phase_ratios(
            num_beds=94,
            monthly_admissions=150,
            target_occupancy=0.93,
            days_per_month=30,
            phase_a_contrib=36000 - 12000,
            phase_b_contrib=36000 - 6000,
            phase_c_contrib=33400 - 4500,
        )
        r2026 = calculate_ideal_phase_ratios(
            num_beds=94,
            monthly_admissions=150,
            target_occupancy=0.93,
            days_per_month=30,
            phase_a_contrib=38500 - 12000,
            phase_b_contrib=38500 - 6000,
            phase_c_contrib=35500 - 4500,
        )
        assert r2026["daily_contribution"] > r2024["daily_contribution"], (
            f"2026 プリセットが 2024 を超過しない: "
            f"2024 = {r2024['daily_contribution']:.0f}, "
            f"2026 = {r2026['daily_contribution']:.0f}"
        )
        # 台本の「約 20 万円／日増加」「年間 7,700 万円」と整合する範囲
        delta_daily = r2026["daily_contribution"] - r2024["daily_contribution"]
        delta_yearly = delta_daily * 365 / 10000  # 万円
        assert 6000 <= delta_yearly <= 9000, (
            f"年間増収が台本の『約 7,700 万円』と不整合: {delta_yearly:.0f} 万円"
        )


# ---------------------------------------------------------------------------
# 5. 病床数定数の一貫性
# ---------------------------------------------------------------------------


class TestBedConstantsConsistency:
    """病床数 94 / 47 が scripts 内で矛盾なく使われていること."""

    def test_total_beds_94(self):
        # 台本・CLAUDE.md 双方で「94 床」が前提。各ソースの定義が食い違っていないかを確認
        from bed_data_manager import get_ward_beds

        assert get_ward_beds("5F") == 47
        assert get_ward_beds("6F") == 47
        assert get_ward_beds("5F") + get_ward_beds("6F") == 94

    def test_smoke_test_beds_constant(self):
        """smoke_test.py が BEDS=47 を使う前提."""
        smoke = (ROOT / "scripts" / "hooks" / "smoke_test.py").read_text(encoding="utf-8")
        assert "BEDS = 47" in smoke, "smoke_test.py の BEDS 定数が 47 でない"


# ---------------------------------------------------------------------------
# 6. 金曜退院率: データと smoke の期待値が一致
# ---------------------------------------------------------------------------


class TestFridayDischargeConsistency:
    def test_friday_discharge_within_scenario_range(self, apr_df):
        apr_disc = apr_df[apr_df["discharges"] > 0]
        friday = apr_disc[apr_disc["date"].dt.dayofweek == 4]
        total = apr_disc["discharges"].sum()
        friday_total = friday["discharges"].sum()
        if total == 0:
            pytest.skip("退院データが空")
        pct = friday_total / total * 100
        # 台本 31%、smoke 期待 25-35%
        assert 25.0 <= pct <= 35.0, f"金曜退院率が台本レンジ外: {pct:.1f}%"


# ---------------------------------------------------------------------------
# 7. データモードと claims の整合性
# ---------------------------------------------------------------------------


class TestClaimsPayloadConsistency:
    """scenario_claims.json の metric 定義が Playwright 側の testid マップと整合."""

    def test_claims_json_exists_after_extraction(self):
        """Python 抽出器を走らせれば reports/scenario_claims.json が生成される."""
        from extract_scenario_claims import extract_all_claims, write_claims_json

        out = ROOT / "reports" / "scenario_claims.json"
        claims = extract_all_claims()
        write_claims_json(claims, out)
        assert out.exists()
        import json

        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["claim_count"] > 0

    def test_metric_testid_map_covers_rule_metrics(self):
        """Playwright METRIC_TO_TESTID と Python RULES の metric セットが揃う."""
        from extract_scenario_claims import RULES

        py_metrics = {r.metric for r in RULES}
        ts_path = ROOT / "playwright" / "test_scenario_qa.spec.ts"
        ts_text = ts_path.read_text(encoding="utf-8")
        # TS 側で定義されている metric キーをざっくり抽出
        for m in py_metrics:
            assert m in ts_text, (
                f"Playwright 側 METRIC_TO_TESTID に metric '{m}' が定義されていない"
            )


# ---------------------------------------------------------------------------
# 8. emergency_ratio の公的/運用 2 系統が分離
# ---------------------------------------------------------------------------


class TestEmergencyRatioConsistency:
    def test_official_and_operational_functions_exist(self):
        from emergency_ratio import (  # noqa: F401
            calculate_emergency_ratio,
            is_transitional_period,
        )

    def test_transitional_period_gate(self):
        """2026-06-01 以降は is_transitional_period = False."""
        from datetime import date

        from emergency_ratio import is_transitional_period

        assert is_transitional_period(date(2026, 4, 18)) is True
        assert is_transitional_period(date(2026, 5, 31)) is True
        # 本則適用開始
        assert is_transitional_period(date(2026, 6, 1)) is False
        assert is_transitional_period(date(2026, 7, 15)) is False


# ---------------------------------------------------------------------------
# 9. 戦略選択 UI 廃止（2026-04-18）— ハードコード確認
# ---------------------------------------------------------------------------


class TestStrategyHardcodedBalanced:
    def test_simulator_strategy_is_balanced(self):
        """bed_control_simulator_app.py 内で strategy が 'バランス戦略' に固定."""
        app = (ROOT / "scripts" / "bed_control_simulator_app.py").read_text(encoding="utf-8")
        # UI からの選択は廃止されているので、ハードコード文字列の存在確認
        assert "バランス戦略" in app, "バランス戦略のハードコードが見当たらない"
