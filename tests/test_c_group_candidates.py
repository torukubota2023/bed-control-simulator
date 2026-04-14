"""
テスト: c_group_candidates モジュール — C群候補リスト生成・退院緊急度分類・表示サマリー

generate_c_group_candidate_list / classify_discharge_urgency /
summarize_candidates_for_display の入出力を検証する。
"""

import sys
import os
import pytest
import pandas as pd
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from c_group_candidates import (
    generate_c_group_candidate_list,
    classify_discharge_urgency,
    summarize_candidates_for_display,
)


# ===================================================================
# ヘルパー: テスト用 detail_df 生成
# ===================================================================


def _make_detail_df(rows: list[dict]) -> pd.DataFrame:
    """入退院詳細データの DataFrame を生成する。"""
    return pd.DataFrame(rows)


def _build_test_detail_df() -> pd.DataFrame:
    """C群候補が出るテストデータを作成する。

    - 入院1: 5F, 2026-03-01, 退院なし → 基準日2026-03-31で LOS=30 (C群)
    - 入院2: 5F, 2026-03-10, 退院あり(LOS=9) → 除外
    - 入院3: 6F, 2026-03-05, 退院なし → LOS=26 (C群)
    - 入院4: 5F, 2026-03-25, 退院なし → LOS=6 (閾値未満、除外)
    - 入院5: 5F, 2026-03-15, 退院なし → LOS=16 (C群)
    """
    return _make_detail_df([
        {"日付": "2026-03-01", "病棟": "5F", "入退院区分": "入院", "経路": "救急"},
        {"日付": "2026-03-10", "病棟": "5F", "入退院区分": "入院", "経路": "紹介"},
        {"日付": "2026-03-10", "病棟": "5F", "入退院区分": "退院", "経路": "", "los_days": 9},
        {"日付": "2026-03-05", "病棟": "6F", "入退院区分": "入院", "経路": "救急"},
        {"日付": "2026-03-25", "病棟": "5F", "入退院区分": "入院", "経路": "直接"},
        {"日付": "2026-03-15", "病棟": "5F", "入退院区分": "入院", "経路": "紹介"},
    ])


# ===================================================================
# generate_c_group_candidate_list
# ===================================================================


class TestGenerateCGroupCandidateList:
    """generate_c_group_candidate_list の入出力を検証する。"""

    def test_empty_data_returns_empty_list(self):
        """None detail_df → 空の候補リスト"""
        result = generate_c_group_candidate_list(detail_df=None)
        assert result["candidates"] == []
        assert result["total_candidates"] == 0

    def test_empty_dataframe_returns_empty(self):
        """空の DataFrame → 空の候補リスト"""
        df = pd.DataFrame(columns=["日付", "病棟", "入退院区分", "経路"])
        result = generate_c_group_candidate_list(detail_df=df)
        assert result["candidates"] == []
        assert result["total_candidates"] == 0

    def test_candidates_from_detail_df(self):
        """入退院詳細から C群候補を正しく識別する"""
        df = _build_test_detail_df()
        result = generate_c_group_candidate_list(
            detail_df=df,
            target_date=date(2026, 3, 31),
        )
        # 入院1(LOS=30), 入院3(LOS=26), 入院5(LOS=16) の3件がC群候補
        assert result["total_candidates"] == 3
        # LOS 降順でソートされる
        los_list = [c["estimated_los"] for c in result["candidates"]]
        assert los_list == sorted(los_list, reverse=True)

    def test_ward_filter(self):
        """病棟フィルタで 5F のみに絞り込む"""
        df = _build_test_detail_df()
        result = generate_c_group_candidate_list(
            detail_df=df,
            ward="5F",
            target_date=date(2026, 3, 31),
        )
        # 5F のC群候補: 入院1(LOS=30) と 入院5(LOS=16) の2件
        assert result["total_candidates"] == 2
        assert result["ward"] == "5F"
        for c in result["candidates"]:
            assert c["ward"] == "5F"

    def test_los_threshold(self):
        """los_threshold=20 → LOS >= 20 の候補のみ返す"""
        df = _build_test_detail_df()
        result = generate_c_group_candidate_list(
            detail_df=df,
            target_date=date(2026, 3, 31),
            los_threshold=20,
        )
        # LOS=30 と LOS=26 の2件のみ
        assert result["total_candidates"] == 2
        for c in result["candidates"]:
            assert c["estimated_los"] >= 20


# ===================================================================
# classify_discharge_urgency
# ===================================================================


class TestClassifyDischargeUrgency:
    """classify_discharge_urgency のテスト"""

    def test_empty_candidates(self):
        """空リスト → 空リスト"""
        assert classify_discharge_urgency([]) == []

    def test_all_below_limit(self):
        """全員がlos_limit以下 → 全員stay_ok"""
        candidates = [
            {"estimated_los": 20},
            {"estimated_los": 18},
            {"estimated_los": 16},
        ]
        result = classify_discharge_urgency(candidates, los_limit=21.0)
        assert result == ["stay_ok", "stay_ok", "stay_ok"]

    def test_average_above_limit_urgent_needed(self):
        """平均>21、長い順に抜いて21以下にする"""
        candidates = [
            {"estimated_los": 50},
            {"estimated_los": 40},
            {"estimated_los": 18},
            {"estimated_los": 16},
        ]
        # 平均 = (50+40+18+16)/4 = 31 > 21
        # 50を抜く → (40+18+16)/3 = 24.7 > 21
        # 40を抜く → (18+16)/2 = 17 ≤ 21 ✓
        # → 50, 40 が urgent、残りは stay_ok
        result = classify_discharge_urgency(candidates, los_limit=21.0)
        assert result == ["urgent", "urgent", "stay_ok", "stay_ok"]

    def test_over_limit_but_avg_ok(self):
        """平均≤21だが個別にlos_limit超の人がいる → release"""
        candidates = [
            {"estimated_los": 25},
            {"estimated_los": 18},
            {"estimated_los": 16},
        ]
        # 平均 = (25+18+16)/3 = 19.7 ≤ 21
        # でも25は21超 → release
        result = classify_discharge_urgency(candidates, los_limit=21.0)
        assert result == ["release", "stay_ok", "stay_ok"]

    def test_single_candidate_above(self):
        """候補1人でlos超過 → urgent"""
        candidates = [{"estimated_los": 30}]
        # 平均=30 > 21 → urgent
        result = classify_discharge_urgency(candidates, los_limit=21.0)
        assert result == ["urgent"]

    def test_single_candidate_below(self):
        """候補1人でlos以下 → stay_ok"""
        candidates = [{"estimated_los": 18}]
        result = classify_discharge_urgency(candidates, los_limit=21.0)
        assert result == ["stay_ok"]

    def test_all_urgent(self):
        """全員除外しても平均が下がらない場合 → 全員urgent"""
        candidates = [
            {"estimated_los": 50},
            {"estimated_los": 45},
            {"estimated_los": 40},
        ]
        # 全員除外すると remaining_count=0 になるので全員urgent
        result = classify_discharge_urgency(candidates, los_limit=21.0)
        assert result == ["urgent", "urgent", "urgent"]


# ===================================================================
# summarize_candidates_for_display
# ===================================================================


class TestSummarizeCandidatesForDisplay:
    """summarize_candidates_for_display の表示用サマリーを検証する。"""

    def test_summarize_empty(self):
        """空の候補 → クラッシュせずサマリーを返す"""
        empty_result = {
            "candidates": [],
            "total_candidates": 0,
            "total_adjustable_bed_days": 0,
            "ward": None,
            "as_of_date": "2026-03-31",
            "data_source": "proxy",
            "note": "",
        }
        summary = summarize_candidates_for_display(
            candidates_result=empty_result,
            los_limit=24.0,
        )
        assert "summary_text" in summary
        assert summary["table_data"] == []
        assert summary["data_quality"] == "proxy"

    def test_summarize_with_candidates(self):
        """候補あり → table_data に正しいカラムが含まれる"""
        df = _build_test_detail_df()
        candidates_result = generate_c_group_candidate_list(
            detail_df=df,
            target_date=date(2026, 3, 31),
        )
        summary = summarize_candidates_for_display(
            candidates_result=candidates_result,
            los_limit=24.0,
        )
        assert len(summary["table_data"]) > 0
        expected_columns = {"入院日", "在院日数", "病棟", "経路", "判定"}
        for row in summary["table_data"]:
            assert expected_columns.issubset(row.keys()), (
                f"Missing columns: {expected_columns - row.keys()}"
            )
