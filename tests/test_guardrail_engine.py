"""guardrail_engine モジュールのテスト。"""

import pandas as pd
import pytest
from datetime import date, timedelta

from guardrail_engine import (
    calculate_los_limit,
    calculate_guardrail_status,
    calculate_los_headroom,
    format_guardrail_display,
)


# ---------------------------------------------------------------------------
# 共通ヘルパー
# ---------------------------------------------------------------------------

def _make_daily_df(n_days=30, base_patients=80, base_admissions=5, base_discharges=5, start_date=None):
    """テスト用の日次DataFrameを生成する。"""
    if start_date is None:
        start_date = date(2026, 3, 1)
    rows = []
    for i in range(n_days):
        d = start_date + timedelta(days=i)
        dow = d.weekday()
        # 週末は入院少なめ
        adm = base_admissions if dow < 5 else max(1, base_admissions - 3)
        dis = base_discharges if dow < 5 else max(0, base_discharges - 4)
        patients = base_patients + (adm - dis) * (i % 3 - 1)
        rows.append({
            "date": str(d),
            "ward": "5F",
            "total_patients": max(patients, 0),
            "new_admissions": adm,
            "discharges": dis,
            "discharge_a": max(1, dis // 3),
            "discharge_b": max(1, dis // 3),
            "discharge_c": max(0, dis - 2 * max(1, dis // 3)),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# TestCalculateLosLimit
# ---------------------------------------------------------------------------

class TestCalculateLosLimit:
    def test_default_20_days(self):
        assert calculate_los_limit(0.10) == 20.0

    def test_age85_25pct(self):
        assert calculate_los_limit(0.25) == 21.0

    def test_age85_80pct(self):
        assert calculate_los_limit(0.85) == 24.0


# ---------------------------------------------------------------------------
# TestCalculateGuardrailStatus
# ---------------------------------------------------------------------------

class TestCalculateGuardrailStatus:
    def test_with_daily_data(self):
        df = _make_daily_df(30)
        results = calculate_guardrail_status(df)
        assert len(results) == 6

        # avg_los は measured
        los_item = results[0]
        assert los_item["data_source"] == "measured"

        # transfer_in_ratio は構造的にゼロ
        transfer_item = [r for r in results if r["name"] == "同一医療機関一般病棟からの転棟割合"][0]
        assert transfer_item["current_value"] == 0.0

    def test_with_detail_df(self):
        df = _make_daily_df(30)
        # 30件の入退院詳細（入院イベント）: 10件が救急
        base_date = date.today()
        detail_rows = (
            [{"route": "救急", "event_type": "admission", "date": str(base_date), "ward": "5F"} for _ in range(10)]
            + [{"route": "紹介", "event_type": "admission", "date": str(base_date), "ward": "5F"} for _ in range(20)]
        )
        detail_df = pd.DataFrame(detail_rows)

        results = calculate_guardrail_status(df, detail_df=detail_df)
        emg_item = [r for r in results if r["name"] == "救急搬送後患者割合"][0]
        assert emg_item["data_source"] == "measured"
        assert abs(emg_item["current_value"] - 33.3) < 0.5

    def test_none_input(self):
        results = calculate_guardrail_status(None)
        assert len(results) == 6
        # 転棟割合は常に measured（構造的ゼロ）、それ以外は not_available
        for item in results:
            if item["name"] == "同一医療機関一般病棟からの転棟割合":
                assert item["data_source"] == "measured"
            else:
                assert item["data_source"] == "not_available"

    def test_manual_input_config(self):
        results = calculate_guardrail_status(
            None,
            config={"home_discharge_rate": 85.0},
        )
        home_item = [r for r in results if r["name"] == "在宅復帰率"][0]
        assert home_item["data_source"] == "manual_input"
        assert home_item["status"] == "safe"


# ---------------------------------------------------------------------------
# TestCalculateLosHeadroom
# ---------------------------------------------------------------------------

class TestCalculateLosHeadroom:
    def test_basic_headroom(self):
        df = _make_daily_df(30)
        result = calculate_los_headroom(df)
        assert result["headroom_days"] is not None
        assert result["headroom_days"] > 0
        assert result["can_extend_c_group"] is True

    def test_none_df(self):
        result = calculate_los_headroom(None)
        assert result["data_source"] == "not_available"


# ---------------------------------------------------------------------------
# TestFormatGuardrailDisplay
# ---------------------------------------------------------------------------

class TestManualSeedIntegration:
    """救急 15% rolling における manual_seeds 経路のテスト（Phase 1.7）.

    制度余力ダッシュボードと救急 15% 専用タブで表示が一致するように、
    `calculate_guardrail_status()` も `config["manual_seeds"]` 経由で
    シード値を採用できる必要がある。
    優先順位: daily > summary > manual_seed > no_data。
    """

    def _make_detail_df_for_month(self, year_month: str, n_emg: int, n_other: int):
        """指定月の詳細データ（救急/その他）を生成する。"""
        y, m = year_month.split("-")
        base = f"{y}-{m}-15"
        rows = (
            [
                {"route": "救急", "event_type": "admission", "date": base, "ward": "5F"}
                for _ in range(n_emg)
            ]
            + [
                {"route": "紹介", "event_type": "admission", "date": base, "ward": "5F"}
                for _ in range(n_other)
            ]
        )
        return pd.DataFrame(rows)

    def _today_ym(self):
        return date.today().strftime("%Y-%m")

    def _prev_ym(self, months: int = 1) -> str:
        from dateutil.relativedelta import relativedelta
        d = date.today() - relativedelta(months=months)
        return d.strftime("%Y-%m")

    def test_manual_seeds_used_when_no_daily_no_summary(self):
        """日次データ・サマリーが無い月はシード値が採用される。"""
        df = _make_daily_df(30)
        # 当月のみ少量の日次データ（先月・先々月はデータ無し）
        detail_df = self._make_detail_df_for_month(self._today_ym(), n_emg=2, n_other=8)

        # 先月・先々月にシードを設定
        manual_seeds = {
            self._prev_ym(1): {"5F": 25.0, "6F": 18.0, "all": 22.0},
            self._prev_ym(2): {"5F": 30.0, "6F": 20.0, "all": 25.0},
        }
        results = calculate_guardrail_status(
            df, detail_df=detail_df,
            config={"manual_seeds": manual_seeds, "ward": "5F"},
        )
        emg_item = [r for r in results if r["name"] == "救急搬送後患者割合"][0]
        # シード値が採用された結果（rolling 平均が当月20%＋25%＋30%/3 ≈ 25%）
        assert emg_item["data_source"] == "measured"
        assert emg_item["current_value"] >= 15.0  # 15% 閾値以上
        assert "シード混在" in emg_item["description"]
        assert "🌉" in emg_item["description"]

    def test_daily_takes_priority_over_seed(self):
        """日次データがある月はシード値より優先される。"""
        df = _make_daily_df(30)
        # 当月に充実した日次データ（救急 5/全 100 = 5%）
        detail_df = self._make_detail_df_for_month(self._today_ym(), n_emg=5, n_other=95)

        # 当月に高いシード（採用されてはいけない）
        manual_seeds = {
            self._today_ym(): {"5F": 50.0, "6F": 50.0, "all": 50.0},
        }
        results_with_seed = calculate_guardrail_status(
            df, detail_df=detail_df,
            config={"manual_seeds": manual_seeds, "ward": "5F"},
        )
        results_without_seed = calculate_guardrail_status(
            df, detail_df=detail_df, config={"ward": "5F"},
        )
        emg_with = [r for r in results_with_seed if r["name"] == "救急搬送後患者割合"][0]
        emg_without = [r for r in results_without_seed if r["name"] == "救急搬送後患者割合"][0]
        # 日次優先: 当月の値はシードに引きずられない
        assert emg_with["current_value"] == emg_without["current_value"]

    def test_summary_takes_priority_over_seed(self):
        """monthly_summary がある月はシードより優先される。"""
        df = _make_daily_df(30)
        detail_df = self._make_detail_df_for_month(self._today_ym(), n_emg=2, n_other=8)
        prev_ym = self._prev_ym(1)
        # summary 値: 救急 10/100 = 10%
        monthly_summary = {
            prev_ym: {"5F": {"admissions": 100, "emergency": 10}}
        }
        # シード値: 50% (採用されてはいけない)
        manual_seeds = {
            prev_ym: {"5F": 50.0, "6F": 50.0, "all": 50.0},
        }
        results = calculate_guardrail_status(
            df, detail_df=detail_df,
            config={
                "monthly_summary": monthly_summary,
                "manual_seeds": manual_seeds,
                "ward": "5F",
            },
        )
        emg_item = [r for r in results if r["name"] == "救急搬送後患者割合"][0]
        # summary 優先: 当該月は 10% 由来 → rolling 平均は 50% にならない
        assert emg_item["current_value"] < 40.0

    def test_empty_detail_with_seeds_returns_measured(self):
        """detail_df が空でも manual_seeds だけで救急 15% が measured になる（Phase 1.8）。

        院内LAN導入直後の純粋な初期状態で、日次入院 0 行・シードのみの状態。
        """
        df = _make_daily_df(30)
        # detail_df を渡さない（None）+ シードのみ
        manual_seeds = {
            self._prev_ym(0): {"5F": 20.0, "6F": 18.0, "all": 19.0},
            self._prev_ym(1): {"5F": 25.0, "6F": 22.0, "all": 23.5},
            self._prev_ym(2): {"5F": 30.0, "6F": 28.0, "all": 29.0},
        }
        results = calculate_guardrail_status(
            df, detail_df=None,
            config={"manual_seeds": manual_seeds, "ward": "5F"},
        )
        emg_item = [r for r in results if r["name"] == "救急搬送後患者割合"][0]
        # シード採用: not_available にならず measured になる
        assert emg_item["data_source"] == "measured"
        assert emg_item["current_value"] >= 15.0
        assert "シード混在" in emg_item["description"]

    def test_empty_detail_with_summary_returns_measured(self):
        """detail_df が空 DataFrame でも monthly_summary だけで measured になる。"""
        df = _make_daily_df(30)
        empty_detail = pd.DataFrame(columns=["date", "ward", "event_type", "route"])
        # 過去 3 ヶ月の summary を入れる
        monthly_summary = {
            self._prev_ym(0): {"5F": {"admissions": 100, "emergency": 20}},
            self._prev_ym(1): {"5F": {"admissions": 90, "emergency": 18}},
            self._prev_ym(2): {"5F": {"admissions": 80, "emergency": 16}},
        }
        results = calculate_guardrail_status(
            df, detail_df=empty_detail,
            config={"monthly_summary": monthly_summary, "ward": "5F"},
        )
        emg_item = [r for r in results if r["name"] == "救急搬送後患者割合"][0]
        assert emg_item["data_source"] == "measured"
        # 20% 由来 → ratio_of_sums で計算されるはず
        assert 18.0 <= emg_item["current_value"] <= 22.0

    def test_empty_detail_no_seed_no_summary_returns_not_available(self):
        """detail_df なし & seed/summary なしは従来通り not_available."""
        df = _make_daily_df(30)
        results = calculate_guardrail_status(
            df, detail_df=None, config={"ward": "5F"},
        )
        emg_item = [r for r in results if r["name"] == "救急搬送後患者割合"][0]
        # 救急ratio は計算できない
        assert emg_item["data_source"] == "not_available"

    def test_manual_seeds_none_does_not_break_existing(self):
        """manual_seeds 未指定でも既存の挙動を壊さない（後方互換）。"""
        df = _make_daily_df(30)
        detail_df = self._make_detail_df_for_month(self._today_ym(), n_emg=10, n_other=20)

        # config なし
        results_none = calculate_guardrail_status(df, detail_df=detail_df)
        # config あるが manual_seeds なし
        results_no_seed = calculate_guardrail_status(
            df, detail_df=detail_df, config={"ward": None},
        )
        # config に manual_seeds=None
        results_seed_none = calculate_guardrail_status(
            df, detail_df=detail_df,
            config={"ward": None, "manual_seeds": None},
        )

        emg_a = [r for r in results_none if r["name"] == "救急搬送後患者割合"][0]
        emg_b = [r for r in results_no_seed if r["name"] == "救急搬送後患者割合"][0]
        emg_c = [r for r in results_seed_none if r["name"] == "救急搬送後患者割合"][0]

        assert emg_a["current_value"] == emg_b["current_value"] == emg_c["current_value"]
        assert "シード混在" not in emg_a["description"]


# ---------------------------------------------------------------------------
# TestFormatGuardrailDisplay
# ---------------------------------------------------------------------------

class TestFormatGuardrailDisplay:
    def test_format_basic(self):
        results = calculate_guardrail_status(_make_daily_df(30))
        display = format_guardrail_display(results)
        assert "overall_status" in display
        assert isinstance(display["auto_calculated"], list)
        assert isinstance(display["not_available"], list)
        # auto_calculated + not_available で全6項目
        assert len(display["auto_calculated"]) + len(display["not_available"]) == 6

    def test_incomplete_when_not_available_exists(self):
        """安全な指標のみでも not_available があれば overall_status は incomplete。"""
        # detail_df なし・config なしで呼ぶと在宅復帰率等が not_available になる
        results = calculate_guardrail_status(_make_daily_df(30))
        display = format_guardrail_display(results)
        # not_available が存在するはず（在宅復帰率・ADL低下割合・看護必要度など）
        assert len(display["not_available"]) > 0
        # danger/warning がなくても safe にはならず incomplete になる
        if not display["danger_items"] and not display["warning_items"]:
            assert display["overall_status"] == "incomplete"
