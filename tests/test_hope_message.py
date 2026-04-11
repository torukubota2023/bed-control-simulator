"""
HOPE送信用サマリー生成モジュール — アラート拡張機能のテスト

pure function のみをテストする（Streamlit 依存なし）。
"""

from __future__ import annotations

from datetime import date

import pytest

# テスト対象のインポート（Streamlit の import を回避するため sys.modules にモック登録）
import sys
from unittest.mock import MagicMock

# Streamlit をモック化して import エラーを回避
sys.modules.setdefault("streamlit", MagicMock())

from scripts.hope_message_generator import (
    MAX_CHARS,
    generate_action_items,
    generate_enhanced_summary_message,
    generate_summary_message,
    _build_alert_section,
    _count_chars,
)


# ---------------------------------------------------------------------------
# テスト用フィクスチャ
# ---------------------------------------------------------------------------

def _make_guardrail_results(los_status="safe", los_value=18.5, los_threshold=21.0):
    """guardrail_engine.calculate_guardrail_status() 相当のモックデータ。"""
    return [
        {
            "name": "平均在院日数",
            "current_value": los_value,
            "threshold": los_threshold,
            "operator": "<=",
            "margin": los_threshold - los_value,
            "status": los_status,
            "data_source": "measured",
            "description": "rolling 90日平均在院日数",
        },
        {
            "name": "救急搬送後患者割合",
            "current_value": 16.0,
            "threshold": 15.0,
            "operator": ">=",
            "margin": 1.0,
            "status": "safe",
            "data_source": "measured",
            "description": "救急・下り搬送後入院",
        },
    ]


def _make_emergency_summary(
    ward_5f_status="green",
    ward_6f_status="red",
    ward_5f_ratio=16.2,
    ward_6f_ratio=12.3,
    ward_6f_needed=3,
):
    """emergency_ratio.get_ward_emergency_summary() 相当のモックデータ。"""
    return {
        "5F": {
            "dual_ratio": {
                "official": {
                    "numerator": 8,
                    "denominator": 50,
                    "ratio_pct": ward_5f_ratio,
                    "status": ward_5f_status,
                },
                "operational": {
                    "numerator": 8,
                    "denominator": 48,
                    "ratio_pct": ward_5f_ratio + 0.5,
                    "status": ward_5f_status,
                },
            },
            "projection": {"standard": {"meets_target": True}},
            "additional": {"additional_needed": 0, "per_remaining_business_day": 0.0},
        },
        "6F": {
            "dual_ratio": {
                "official": {
                    "numerator": 6,
                    "denominator": 49,
                    "ratio_pct": ward_6f_ratio,
                    "status": ward_6f_status,
                },
                "operational": {
                    "numerator": 6,
                    "denominator": 47,
                    "ratio_pct": ward_6f_ratio + 0.3,
                    "status": ward_6f_status,
                },
            },
            "projection": {"standard": {"meets_target": False}},
            "additional": {
                "additional_needed": ward_6f_needed,
                "per_remaining_business_day": 0.5,
            },
        },
        "alerts": [],
        "target_date": date(2026, 4, 11),
        "year_month": "2026-04",
    }


def _make_c_group_alerts(level="warning", message="C群が 35% と高水準。退院調整の停滞に注意してください"):
    """c_group_control.generate_c_group_alerts() 相当のモックデータ。"""
    return [
        {
            "level": level,
            "message": message,
            "category": "c_group",
        },
    ]


def _make_ward_data(patients_5f=40, patients_6f=46):
    """病棟別データのモック。"""
    return {
        "5F": {"patients": patients_5f, "beds": 47},
        "6F": {"patients": patients_6f, "beds": 47},
    }


# ---------------------------------------------------------------------------
# 1. test_generate_action_items_emergency_red
# ---------------------------------------------------------------------------

def test_generate_action_items_emergency_red():
    """救急搬送後患者割合がred（未達）の場合、アクション項目が生成される。"""
    emergency = _make_emergency_summary(ward_6f_status="red", ward_6f_needed=3)
    items = generate_action_items(emergency_summary=emergency)
    assert len(items) > 0
    # 6Fの救急受入強化が含まれる
    assert any("6F" in i and "救急受入強化" in i for i in items)
    assert any("あと3件" in i for i in items)


# ---------------------------------------------------------------------------
# 2. test_generate_action_items_guardrail_warning
# ---------------------------------------------------------------------------

def test_generate_action_items_guardrail_warning():
    """制度ガードレールがwarningの場合、退院調整アクションが生成される。"""
    guardrail = _make_guardrail_results(los_status="warning", los_value=20.5, los_threshold=21.0)
    items = generate_action_items(guardrail_results=guardrail)
    assert len(items) > 0
    assert any("退院調整" in i for i in items)
    assert any("20.5" in i for i in items)


# ---------------------------------------------------------------------------
# 3. test_generate_action_items_empty
# ---------------------------------------------------------------------------

def test_generate_action_items_empty():
    """アラートがない場合、空リストが返る。"""
    # すべてNone
    items = generate_action_items()
    assert items == []

    # safe状態のデータを渡してもアクションは生成されない
    guardrail = _make_guardrail_results(los_status="safe", los_value=18.0)
    emergency = _make_emergency_summary(ward_5f_status="green", ward_6f_status="green")
    ward_data = _make_ward_data(patients_5f=42, patients_6f=42)  # ~89% occupancy
    items = generate_action_items(
        guardrail_results=guardrail,
        emergency_summary=emergency,
        ward_data=ward_data,
    )
    assert items == []


# ---------------------------------------------------------------------------
# 4. test_build_alert_section_all_data
# ---------------------------------------------------------------------------

def test_build_alert_section_all_data():
    """3つのデータソースすべてが揃っている場合のアラートセクション。"""
    guardrail = _make_guardrail_results(los_status="warning", los_value=20.5)
    emergency = _make_emergency_summary(ward_6f_status="red", ward_6f_ratio=12.3, ward_6f_needed=3)
    c_alerts = _make_c_group_alerts()

    section = _build_alert_section(guardrail, emergency, c_alerts)
    assert "[制度]" in section
    assert "[救急]" in section
    assert "[C群]" in section
    assert "20.5日" in section
    assert "12.3%" in section


# ---------------------------------------------------------------------------
# 5. test_build_alert_section_partial
# ---------------------------------------------------------------------------

def test_build_alert_section_partial():
    """一部のデータしかない場合でもエラーなく動作する。"""
    # 救急のみ
    emergency = _make_emergency_summary()
    section = _build_alert_section(emergency_summary=emergency)
    assert "[救急]" in section
    assert "[制度]" not in section
    assert "[C群]" not in section

    # C群のみ
    c_alerts = _make_c_group_alerts()
    section = _build_alert_section(c_group_alerts=c_alerts)
    assert "[C群]" in section
    assert "[制度]" not in section
    assert "[救急]" not in section

    # すべてNone
    section = _build_alert_section()
    assert section == ""


# ---------------------------------------------------------------------------
# 6. test_enhanced_message_under_400_chars
# ---------------------------------------------------------------------------

def test_enhanced_message_under_400_chars():
    """拡張メッセージの各メッセージが400文字以内である。"""
    guardrail = _make_guardrail_results(los_status="danger", los_value=21.5)
    emergency = _make_emergency_summary(ward_6f_status="red", ward_6f_needed=5)
    c_alerts = _make_c_group_alerts()
    ward_data = _make_ward_data(patients_5f=46, patients_6f=47)

    messages = generate_enhanced_summary_message(
        target_date=date(2026, 4, 11),
        total_beds=94,
        ward_data=ward_data,
        admissions=5,
        discharges=3,
        avg_los=17.8,
        ward_rolling_los={
            "5F": {"los": 18.5, "days": 90},
            "6F": {"los": 19.2, "days": 90},
        },
        rolling_los_limit=21,
        guardrail_results=guardrail,
        emergency_summary=emergency,
        c_group_alerts=c_alerts,
    )

    for i, msg in enumerate(messages):
        char_count = _count_chars(msg)
        assert char_count <= MAX_CHARS, (
            f"メッセージ{i+1}が{char_count}文字で400文字制限を超過: {msg[:100]}..."
        )


# ---------------------------------------------------------------------------
# 7. test_enhanced_message_no_alerts
# ---------------------------------------------------------------------------

def test_enhanced_message_no_alerts():
    """アラートデータがない場合、メッセージ1のみが返る。"""
    ward_data = _make_ward_data()
    messages = generate_enhanced_summary_message(
        target_date=date(2026, 4, 11),
        total_beds=94,
        ward_data=ward_data,
        admissions=5,
        discharges=4,
    )
    assert len(messages) == 1
    assert "病床管理" in messages[0]


# ---------------------------------------------------------------------------
# 8. test_enhanced_message_with_alerts
# ---------------------------------------------------------------------------

def test_enhanced_message_with_alerts():
    """アラートデータがある場合、メッセージ2が追加される。"""
    guardrail = _make_guardrail_results(los_status="warning", los_value=20.5)
    emergency = _make_emergency_summary(ward_6f_status="red")
    c_alerts = _make_c_group_alerts()
    ward_data = _make_ward_data()

    messages = generate_enhanced_summary_message(
        target_date=date(2026, 4, 11),
        total_beds=94,
        ward_data=ward_data,
        admissions=5,
        discharges=4,
        guardrail_results=guardrail,
        emergency_summary=emergency,
        c_group_alerts=c_alerts,
    )
    assert len(messages) == 2
    assert "病床管理" in messages[0]
    assert "制度アラート" in messages[1]
    # メッセージ2にアクション項目が含まれる
    assert "対応" in messages[1]
