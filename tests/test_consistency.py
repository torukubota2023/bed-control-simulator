"""
整合性テスト — LOS一貫性・救急搬送比率モード・翌朝受入余力分離・結論カード病棟文脈

デモシナリオと各コンポーネント間の数値一貫性を検証する。
"""

import os
import sys
import pytest
import pandas as pd
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from bed_data_manager import calculate_rolling_los
from guardrail_engine import calculate_los_headroom, calculate_los_limit
from action_recommendation import generate_action_card, generate_kpi_priority_list
from emergency_ratio import get_ward_emergency_summary, estimate_next_morning_capacity


# ---------------------------------------------------------------------------
# フィクスチャ: デモデータ読み込み
# ---------------------------------------------------------------------------

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def _load_ward_data(ward: str) -> pd.DataFrame:
    """病棟別デモデータを読み込む。"""
    path = os.path.join(DATA_DIR, "sample_actual_data_ward_202604.csv")
    if not os.path.exists(path):
        pytest.skip(f"デモデータが見つかりません: {path}")
    df = pd.read_csv(path)
    return df[df["ward"] == ward].copy()


def _load_all_ward_data() -> pd.DataFrame:
    """全病棟のデモデータを読み込む。"""
    path = os.path.join(DATA_DIR, "sample_actual_data_ward_202604.csv")
    if not os.path.exists(path):
        pytest.skip(f"デモデータが見つかりません: {path}")
    return pd.read_csv(path)


def _load_admission_details() -> pd.DataFrame:
    """入退院詳細データを読み込む。"""
    path = os.path.join(DATA_DIR, "admission_details.csv")
    if not os.path.exists(path):
        pytest.skip(f"入退院詳細データが見つかりません: {path}")
    return pd.read_csv(path)


# ---------------------------------------------------------------------------
# 1. LOS 一貫性テスト
# ---------------------------------------------------------------------------


class TestLosConsistency:
    """rolling 90日 LOS が guardrail / action recommendation で同じ source を使う。"""

    def test_rolling_los_same_for_same_data(self):
        """同一DataFrameに対してcalculate_rolling_losとcalculate_los_headroomのLOSが一致する。"""
        df_5f = _load_ward_data("5F")
        if len(df_5f) == 0:
            pytest.skip("5F data is empty")

        rolling = calculate_rolling_los(df_5f, window_days=90)
        headroom = calculate_los_headroom(df_5f, {"age_85_ratio": 0.25})

        assert rolling["rolling_los"] is not None
        assert headroom["current_los"] is not None
        # 同一データなのでLOS値は一致するはず
        assert abs(rolling["rolling_los"] - headroom["current_los"]) < 0.01, (
            f"rolling_los={rolling['rolling_los']}, headroom current_los={headroom['current_los']}"
        )

    def test_ward_los_differs_between_5f_6f(self):
        """5Fと6FのLOSは異なる値になる（デモデータの設計上）。"""
        df_5f = _load_ward_data("5F")
        df_6f = _load_ward_data("6F")
        if len(df_5f) == 0 or len(df_6f) == 0:
            pytest.skip("Ward data is empty")

        los_5f = calculate_rolling_los(df_5f, window_days=90)["rolling_los"]
        los_6f = calculate_rolling_los(df_6f, window_days=90)["rolling_los"]

        assert los_5f is not None and los_6f is not None
        assert los_5f != los_6f, "5F and 6F should have different LOS values"

    def test_demo_los_values_in_expected_range(self):
        """デモデータのLOS値がシナリオ台本の想定範囲内にある。"""
        df_5f = _load_ward_data("5F")
        df_6f = _load_ward_data("6F")
        if len(df_5f) == 0 or len(df_6f) == 0:
            pytest.skip("Ward data is empty")

        los_5f = calculate_rolling_los(df_5f, window_days=90)["rolling_los"]
        los_6f = calculate_rolling_los(df_6f, window_days=90)["rolling_los"]

        # シナリオ台本: 5F≒17.7, 6F≒21.3 (±1.5の許容)
        assert 15.0 < los_5f < 20.0, f"5F LOS={los_5f} is out of expected range"
        assert 19.0 < los_6f < 24.0, f"6F LOS={los_6f} is out of expected range"

    def test_los_headroom_consistent_across_calls(self):
        """同一データで2回呼んでも同じ結果になる（冪等性）。"""
        df_5f = _load_ward_data("5F")
        if len(df_5f) == 0:
            pytest.skip("5F data is empty")

        config = {"age_85_ratio": 0.25}
        h1 = calculate_los_headroom(df_5f, config)
        h2 = calculate_los_headroom(df_5f, config)

        assert h1["current_los"] == h2["current_los"]
        assert h1["headroom_days"] == h2["headroom_days"]


# ---------------------------------------------------------------------------
# 2. 救急搬送比率モード明示テスト
# ---------------------------------------------------------------------------


class TestEmergencyRatioMode:
    """official/operationalの両値が区別され、ラベル情報が欠けない。"""

    def test_dual_ratio_has_both_modes(self):
        """get_ward_emergency_summaryがofficial/operationalを両方返す。"""
        detail_df = _load_admission_details()
        result = get_ward_emergency_summary(detail_df)

        for ward in ("5F", "6F"):
            if ward in result:
                dual = result[ward].get("dual_ratio", {})
                assert "official" in dual, f"{ward}: official mode missing"
                assert "operational" in dual, f"{ward}: operational mode missing"

    def test_official_and_operational_have_ratio_pct(self):
        """各モードのデータにratio_pctが含まれる。"""
        detail_df = _load_admission_details()
        result = get_ward_emergency_summary(detail_df)

        for ward in ("5F", "6F"):
            if ward not in result:
                continue
            for mode in ("official", "operational"):
                mode_data = result[ward].get("dual_ratio", {}).get(mode)
                if mode_data is not None:
                    assert "ratio_pct" in mode_data, f"{ward}/{mode}: ratio_pct missing"

    def test_kpi_list_emergency_label_includes_mode(self):
        """KPIリストの救急搬送比率名にモード名（院内運用用/届出確認用）が含まれる。"""
        detail_df = _load_admission_details()
        emergency = get_ward_emergency_summary(detail_df)

        kpis = generate_kpi_priority_list(emergency_summary=emergency)
        er_kpi = next((k for k in kpis if "救急" in k["name"]), None)
        assert er_kpi is not None, "救急搬送関連のKPIが見つかりません"
        assert "院内運用用" in er_kpi["name"] or "届出確認用" in er_kpi["name"], (
            f"KPI名にモード明示がない: {er_kpi['name']}"
        )


# ---------------------------------------------------------------------------
# 3. 翌朝受入余力の overall vs ward 分離テスト
# ---------------------------------------------------------------------------


class TestMorningCapacitySeparation:
    """overall cardはhospital-wide、ward cardはward-specific。"""

    def test_overall_uses_total_beds(self):
        """全体の翌朝受入余力がtotal_beds=94で計算される。"""
        all_df = _load_all_ward_data()
        detail_df = _load_admission_details()

        result = estimate_next_morning_capacity(
            all_df, detail_df, ward=None, total_beds=94,
        )
        # 現在の空床が94床を超えることはない
        assert result["current_empty_beds"] <= 94
        assert result["estimated_emergency_slots"] <= 94

    def test_ward_uses_ward_beds(self):
        """病棟別は47床基準で計算される。"""
        df_5f = _load_ward_data("5F")
        detail_df = _load_admission_details()
        if len(df_5f) == 0:
            pytest.skip("5F data is empty")

        result = estimate_next_morning_capacity(
            df_5f, detail_df, ward="5F", ward_beds=47,
        )
        assert result["current_empty_beds"] <= 47
        assert result["estimated_emergency_slots"] <= 47

    def test_overall_and_ward_sum_approximately_matches(self):
        """5F + 6Fの空床の合計が、全体の空床と大きく乖離しない。"""
        all_df = _load_all_ward_data()
        df_5f = _load_ward_data("5F")
        df_6f = _load_ward_data("6F")
        detail_df = _load_admission_details()
        if len(df_5f) == 0 or len(df_6f) == 0:
            pytest.skip("Ward data is empty")

        overall = estimate_next_morning_capacity(all_df, detail_df, ward=None, total_beds=94)
        w5f = estimate_next_morning_capacity(df_5f, detail_df, ward="5F", ward_beds=47)
        w6f = estimate_next_morning_capacity(df_6f, detail_df, ward="6F", ward_beds=47)

        ward_sum = w5f["current_empty_beds"] + w6f["current_empty_beds"]
        overall_beds = overall["current_empty_beds"]
        # 全体値と病棟合計が大きく乖離しないこと（±5床の許容）
        assert abs(ward_sum - overall_beds) <= 5, (
            f"ward_sum={ward_sum}, overall={overall_beds}"
        )


# ---------------------------------------------------------------------------
# 4. selected ward 結論カード文脈テスト
# ---------------------------------------------------------------------------


class TestActionCardWardContext:
    """病棟選択時のカードに selected_ward が反映される。"""

    def test_no_ward_selected_returns_no_selected_ward(self):
        """selected_ward未指定 → カードにselected_wardキーなし。"""
        card = generate_action_card()
        assert "selected_ward" not in card

    def test_ward_selected_returns_selected_ward(self):
        """selected_ward='6F' → カードに'6F'が入る。"""
        card = generate_action_card(selected_ward="6F")
        assert card.get("selected_ward") == "6F"

    def test_5f_selected_with_6f_danger_still_has_5f_context(self):
        """5F選択時でも、emergency_summaryに6Fの危険があった場合、
        selected_ward='5F'が維持される（カードの文脈は選択病棟を示す）。"""
        emergency = {
            "overall_status": "danger",
            "alerts": [],
            "6F": {
                "dual_ratio": {
                    "operational": {"ratio_pct": 5.0},
                    "official": {"ratio_pct": 5.0, "status": "red"},
                },
                "additional": {"additional_needed": 10},
            },
        }
        card = generate_action_card(
            emergency_summary=emergency,
            selected_ward="5F",
        )
        # 結論カードは病院全体の救急リスクで赤になるが、
        # selected_wardは選択中の病棟を示す
        assert card.get("selected_ward") == "5F"

    def test_card_level_reflects_overall_risk(self):
        """selected_ward='5F'でも、6Fの重大リスクは level に反映される
        （ただしselected_wardは5Fを示す）。"""
        emergency = {
            "overall_status": "danger",
            "alerts": [],
            "6F": {
                "dual_ratio": {
                    "operational": {"ratio_pct": 5.0},
                    "official": {"ratio_pct": 5.0, "status": "red"},
                },
                "additional": {"additional_needed": 10},
            },
        }
        card = generate_action_card(
            emergency_summary=emergency,
            selected_ward="5F",
        )
        assert card["level"] == "critical"
        assert card.get("selected_ward") == "5F"
        assert len(card.get("cross_ward_alerts", [])) > 0, "6F danger should appear in cross_ward_alerts"

    def test_cross_ward_alerts_empty_when_no_other_ward_problem(self):
        """他病棟に問題がないとき cross_ward_alerts は空。"""
        card = generate_action_card(selected_ward="5F")
        assert card.get("cross_ward_alerts", []) == []


# ---------------------------------------------------------------------------
# 5. デモシナリオのスナップショット寄りテスト
# ---------------------------------------------------------------------------


class TestDemoScenarioValues:
    """demo_scenario_v3.5.md で使う代表値がデータから再計算した結果と大きく乖離しない。"""

    def test_6f_los_exceeds_limit(self):
        """6FのrollingLOSが制度上限(21日)付近またはそれ以上。"""
        df_6f = _load_ward_data("6F")
        if len(df_6f) == 0:
            pytest.skip("6F data is empty")

        los = calculate_rolling_los(df_6f, window_days=90)["rolling_los"]
        limit = calculate_los_limit(0.25)  # 85歳以上25%
        # 6Fは上限付近 (headroom < 2日)
        assert los > limit - 2.0, f"6F LOS={los} should be near/above limit={limit}"

    def test_5f_los_has_headroom(self):
        """5FのLOSには余力がある。"""
        df_5f = _load_ward_data("5F")
        if len(df_5f) == 0:
            pytest.skip("5F data is empty")

        headroom = calculate_los_headroom(df_5f, {"age_85_ratio": 0.25})
        assert headroom["headroom_days"] > 1.0, (
            f"5F headroom={headroom['headroom_days']} should have margin"
        )

    def test_overall_status_structure(self):
        """get_ward_emergency_summaryがoverall_statusを返す。"""
        detail_df = _load_admission_details()
        result = get_ward_emergency_summary(detail_df)
        assert "overall_status" in result
        assert result["overall_status"] in ("danger", "warning", "safe", "incomplete")
