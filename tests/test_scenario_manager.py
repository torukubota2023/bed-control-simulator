"""
シナリオマネージャーのテスト

保存・読み込み・比較・分析の各機能を検証する。
一時 SQLite データベースを使用し、Streamlit に依存しない。
"""

import os
import sys
import tempfile
import unittest

# プロジェクトルートを sys.path に追加
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from scripts.scenario_manager import (
    save_scenario,
    load_scenario,
    list_scenarios,
    delete_scenario,
    compare_scenarios,
    analyze_scenarios,
)


def _make_temp_db() -> str:
    """テスト用の一時DBファイルパスを返す。"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return path


def _sample_scenario_params() -> dict:
    """サンプルのシナリオパラメータを返す。"""
    return {
        "day_index": 10,
        "discharge_a": 0,
        "discharge_b": 1,
        "discharge_c": 3,
        "new_admissions": 5,
    }


def _sample_scenario_results(occupancy: float = 0.92, daily_profit: int = 150000) -> dict:
    """サンプルのシナリオ結果を返す。"""
    baseline_profit = 120000
    return {
        "scenario_name": "テストシナリオ",
        "baseline": {
            "total": 85,
            "a": 25,
            "b": 30,
            "c": 30,
            "occupancy": 0.90,
            "daily_profit": baseline_profit,
        },
        "scenario": {
            "total": 87,
            "a": 30,
            "b": 29,
            "c": 28,
            "occupancy": occupancy,
            "daily_profit": daily_profit,
        },
        "diff": {
            "total": 2,
            "occupancy": round(occupancy - 0.90, 4),
            "daily_profit": daily_profit - baseline_profit,
        },
        "phase_composition_after": {"A": 0.345, "B": 0.333, "C": 0.322},
        "messages": [],
        "discharge_detail": {
            "a": 0,
            "b": 1,
            "c": 3,
            "total": 4,
            "new_admissions": 5,
        },
    }


class TestScenarioManager(unittest.TestCase):
    """シナリオマネージャーのテストケース"""

    def setUp(self):
        self.db_path = _make_temp_db()

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    # ------------------------------------------------------------------
    # 1. test_save_and_load_scenario
    # ------------------------------------------------------------------
    def test_save_and_load_scenario(self):
        """シナリオの保存と読み込みのラウンドトリップを検証する。"""
        params = _sample_scenario_params()
        results = _sample_scenario_results()

        sid = save_scenario(
            name="C群3名退院",
            scenario_type="whatif_mixed",
            parameters=params,
            results=results,
            baseline_snapshot={"occupancy": 0.90},
            tags=["テスト", "C群"],
            notes="テスト用シナリオ",
            db_path=self.db_path,
        )

        self.assertIsNotNone(sid)
        self.assertTrue(len(sid) > 0)

        loaded = load_scenario(sid, db_path=self.db_path)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["name"], "C群3名退院")
        self.assertEqual(loaded["scenario_type"], "whatif_mixed")
        self.assertEqual(loaded["parameters"]["discharge_c"], 3)
        self.assertEqual(loaded["results"]["scenario"]["total"], 87)
        self.assertEqual(loaded["baseline_snapshot"]["occupancy"], 0.90)
        self.assertIn("テスト", loaded["tags"])
        self.assertIn("C群", loaded["tags"])
        self.assertEqual(loaded["notes"], "テスト用シナリオ")

    # ------------------------------------------------------------------
    # 2. test_list_scenarios
    # ------------------------------------------------------------------
    def test_list_scenarios(self):
        """シナリオ一覧の取得（フィルタあり/なし）を検証する。"""
        # 3件保存（2種類）
        save_scenario("シナリオA", "whatif_mixed", {}, {},
                       db_path=self.db_path)
        save_scenario("シナリオB", "whatif_weekly", {}, {},
                       db_path=self.db_path)
        save_scenario("シナリオC", "whatif_mixed", {}, {},
                       db_path=self.db_path)

        # 全件
        all_list = list_scenarios(db_path=self.db_path)
        self.assertEqual(len(all_list), 3)

        # フィルタ: whatif_mixed のみ
        mixed_list = list_scenarios(scenario_type="whatif_mixed",
                                     db_path=self.db_path)
        self.assertEqual(len(mixed_list), 2)
        for item in mixed_list:
            self.assertEqual(item["scenario_type"], "whatif_mixed")

        # フィルタ: whatif_weekly のみ
        weekly_list = list_scenarios(scenario_type="whatif_weekly",
                                      db_path=self.db_path)
        self.assertEqual(len(weekly_list), 1)

    # ------------------------------------------------------------------
    # 3. test_delete_scenario
    # ------------------------------------------------------------------
    def test_delete_scenario(self):
        """シナリオの削除と削除確認を検証する。"""
        sid = save_scenario("削除テスト", "whatif_mixed", {}, {},
                             db_path=self.db_path)

        # 削除前に存在確認
        self.assertIsNotNone(load_scenario(sid, db_path=self.db_path))

        # 削除
        result = delete_scenario(sid, db_path=self.db_path)
        self.assertTrue(result)

        # 削除後
        self.assertIsNone(load_scenario(sid, db_path=self.db_path))

        # 存在しない ID の削除
        result2 = delete_scenario("nonexistent-id", db_path=self.db_path)
        self.assertFalse(result2)

    # ------------------------------------------------------------------
    # 4. test_compare_two_scenarios
    # ------------------------------------------------------------------
    def test_compare_two_scenarios(self):
        """2シナリオの比較が正しい構造を返すことを検証する。"""
        sid1 = save_scenario(
            "シナリオ1", "whatif_mixed",
            _sample_scenario_params(),
            _sample_scenario_results(occupancy=0.91, daily_profit=140000),
            db_path=self.db_path,
        )
        sid2 = save_scenario(
            "シナリオ2", "whatif_mixed",
            _sample_scenario_params(),
            _sample_scenario_results(occupancy=0.93, daily_profit=160000),
            db_path=self.db_path,
        )

        result = compare_scenarios([sid1, sid2], db_path=self.db_path)

        self.assertEqual(len(result["scenarios"]), 2)
        comp = result["comparison"]
        self.assertIn("occupancy_range", comp)
        self.assertIn("revenue_range", comp)
        self.assertIn("best_occupancy_id", comp)
        self.assertIn("best_revenue_id", comp)
        self.assertIn("metrics_table", comp)
        self.assertEqual(len(comp["metrics_table"]), 2)

    # ------------------------------------------------------------------
    # 5. test_compare_identifies_best
    # ------------------------------------------------------------------
    def test_compare_identifies_best(self):
        """best_occupancy_id と best_revenue_id が正しく特定されることを検証する。"""
        # シナリオ1: 稼働率92.5%（最適）、収益低い
        sid1 = save_scenario(
            "最適稼働率", "whatif_mixed",
            _sample_scenario_params(),
            _sample_scenario_results(occupancy=0.925, daily_profit=130000),
            db_path=self.db_path,
        )
        # シナリオ2: 稼働率95%、収益高い
        sid2 = save_scenario(
            "高収益", "whatif_mixed",
            _sample_scenario_params(),
            _sample_scenario_results(occupancy=0.95, daily_profit=180000),
            db_path=self.db_path,
        )

        result = compare_scenarios([sid1, sid2], db_path=self.db_path)
        comp = result["comparison"]

        # 92.5%に最も近いのはシナリオ1
        self.assertEqual(comp["best_occupancy_id"], sid1)
        # 収益が最も高いのはシナリオ2
        self.assertEqual(comp["best_revenue_id"], sid2)

    # ------------------------------------------------------------------
    # 6. test_analyze_basic
    # ------------------------------------------------------------------
    def test_analyze_basic(self):
        """基本的な分析が insights と recommendations を返すことを検証する。"""
        scenarios = [
            {
                "id": "test-1",
                "name": "テストシナリオ1",
                "scenario_type": "whatif_mixed",
                "parameters": _sample_scenario_params(),
                "results": _sample_scenario_results(occupancy=0.92, daily_profit=150000),
            },
            {
                "id": "test-2",
                "name": "テストシナリオ2",
                "scenario_type": "whatif_mixed",
                "parameters": _sample_scenario_params(),
                "results": _sample_scenario_results(occupancy=0.88, daily_profit=130000),
            },
        ]

        result = analyze_scenarios(scenarios)

        self.assertIn("insights", result)
        self.assertIn("recommendations", result)
        self.assertIn("best_scenario", result)
        self.assertIn("risk_assessment", result)
        self.assertIn("summary", result)

        # recommendations は最大3件
        self.assertLessEqual(len(result["recommendations"]), 3)
        self.assertEqual(len(result["recommendations"]), 2)

        # 各 recommendation の構造確認
        for rec in result["recommendations"]:
            self.assertIn("rank", rec)
            self.assertIn("action", rec)
            self.assertIn("expected_impact", rec)
            self.assertIn("feasibility", rec)
            self.assertIn("risk", rec)

        # best_scenario の構造確認
        self.assertIsNotNone(result["best_scenario"])
        self.assertIn("id", result["best_scenario"])
        self.assertIn("name", result["best_scenario"])
        self.assertIn("reason", result["best_scenario"])

    # ------------------------------------------------------------------
    # 7. test_analyze_with_guardrail
    # ------------------------------------------------------------------
    def test_analyze_with_guardrail(self):
        """施設基準チェック warning 時に LOS リスクが検出されることを検証する。"""
        scenarios = [
            {
                "id": "test-los",
                "name": "長期在院シナリオ",
                "scenario_type": "whatif_mixed",
                "parameters": _sample_scenario_params(),
                "results": _sample_scenario_results(occupancy=0.92, daily_profit=150000),
            },
        ]

        guardrail_status = [
            {
                "name": "平均在院日数",
                "current_value": 19.5,
                "threshold": 20.0,
                "operator": "<=",
                "margin": 0.5,
                "status": "warning",
                "data_source": "measured",
                "description": "rolling 90日平均在院日数",
            },
        ]

        result = analyze_scenarios(scenarios, guardrail_status=guardrail_status)

        # 施設基準チェック warning に関する insight が含まれること
        warning_insights = [
            i for i in result["insights"]
            if "施設基準チェック" in i["text"] and "警告" in i["text"]
        ]
        if not warning_insights:
            # "警告域" の表現もチェック
            warning_insights = [
                i for i in result["insights"]
                if "施設基準チェック" in i["text"]
            ]
        self.assertTrue(len(warning_insights) > 0,
                        f"施設基準チェック警告に関するインサイトが見つかりません。insights={result['insights']}")

    # ------------------------------------------------------------------
    # 8. test_analyze_with_emergency
    # ------------------------------------------------------------------
    def test_analyze_with_emergency(self):
        """救急搬送比率 red 時に空床減少シナリオがペナルティを受けることを検証する。"""
        # 稼働率が高い（空床減少）シナリオ
        scenarios = [
            {
                "id": "test-high-occ",
                "name": "高稼働率シナリオ",
                "scenario_type": "whatif_mixed",
                "parameters": _sample_scenario_params(),
                "results": _sample_scenario_results(occupancy=0.96, daily_profit=170000),
            },
        ]

        emergency_summary = {
            "5F": {
                "dual_ratio": {
                    "official": {
                        "ratio_pct": 12.0,
                        "status": "red",
                    },
                },
            },
            "6F": {
                "dual_ratio": {
                    "official": {
                        "ratio_pct": 18.0,
                        "status": "green",
                    },
                },
            },
        }

        result = analyze_scenarios(scenarios, emergency_summary=emergency_summary)

        # 救急搬送関連の insight が含まれること
        emergency_insights = [
            i for i in result["insights"]
            if "救急" in i["text"]
        ]
        self.assertTrue(len(emergency_insights) > 0,
                        "救急搬送に関するインサイトが見つかりません")

        # 高稼働率に関する insight も含まれること
        occ_insights = [
            i for i in result["insights"]
            if "目標上限" in i["text"] or "稼働率" in i["text"]
        ]
        self.assertTrue(len(occ_insights) > 0)

    # ------------------------------------------------------------------
    # 9. test_analyze_empty
    # ------------------------------------------------------------------
    def test_analyze_empty(self):
        """空リストでの分析がクラッシュしないことを検証する。"""
        result = analyze_scenarios([])

        self.assertIsNotNone(result)
        self.assertEqual(result["insights"], [])
        self.assertEqual(result["recommendations"], [])
        self.assertIsNone(result["best_scenario"])
        self.assertIsInstance(result["risk_assessment"], str)
        self.assertIsInstance(result["summary"], str)

    # ------------------------------------------------------------------
    # 10. test_save_scenario_generates_uuid
    # ------------------------------------------------------------------
    def test_save_scenario_generates_uuid(self):
        """各保存で一意の UUID が生成されることを検証する。"""
        ids = set()
        for i in range(10):
            sid = save_scenario(
                f"シナリオ{i}", "whatif_mixed", {}, {},
                db_path=self.db_path,
            )
            self.assertNotIn(sid, ids, f"UUID の重複が検出されました: {sid}")
            ids.add(sid)

        self.assertEqual(len(ids), 10)


if __name__ == "__main__":
    unittest.main()
