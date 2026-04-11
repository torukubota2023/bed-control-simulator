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
        detail_rows = (
            [{"route": "救急", "event_type": "admission"} for _ in range(10)]
            + [{"route": "紹介", "event_type": "admission"} for _ in range(20)]
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
