"""
past_performance_view のユニット / AppTest 統合テスト.

検証項目:
- モジュールが import できる
- 公開関数 render_past_performance_view が存在
- pure 関数の出力（サマリー KPI・月別推移・曜日・時間帯・年齢・予約リードタイム）
- 件数の境界値（FY2025 実データ 1965 件）
- AppTest で画面描画が例外なく走る
- 主要な data-testid が DOM に出る
- CSV 未取り込み時のフォールバック（例外で落ちない）
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pandas as pd
import pytest

# scripts/ を sys.path に追加
_SCRIPTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "scripts")
)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from views import past_performance_view as ppv  # noqa: E402


# ---------------------------------------------------------------------------
# 1. モジュール import / 公開 API の存在
# ---------------------------------------------------------------------------


class TestModuleBasics:
    """モジュールの基本的な健全性."""

    def test_public_function_exists(self):
        """公開関数 render_past_performance_view が存在."""
        assert callable(ppv.render_past_performance_view)

    def test_pure_functions_exposed(self):
        """pure 計算関数がすべて公開されている."""
        for fname in (
            "compute_summary_kpis",
            "compute_monthly_trend",
            "compute_dow_pattern",
            "compute_hour_distribution",
            "compute_age_distribution",
            "compute_lead_time",
        ):
            assert callable(getattr(ppv, fname)), f"{fname} が呼び出し可能でない"


# ---------------------------------------------------------------------------
# 2. サマリー KPI（compute_summary_kpis）
# ---------------------------------------------------------------------------


def _make_synth_df(n_5f_em: int = 10, n_5f_sc: int = 10,
                   n_6f_em: int = 10, n_6f_sc: int = 10,
                   elderly_frac: float = 0.3) -> pd.DataFrame:
    """合成データで compute_summary_kpis などをテストする."""
    rows = []
    base = pd.Timestamp("2025-04-01")
    records = [
        ("5F", "emergency", n_5f_em),
        ("5F", "scheduled", n_5f_sc),
        ("6F", "emergency", n_6f_em),
        ("6F", "scheduled", n_6f_sc),
    ]
    total = sum(c for _, _, c in records)
    elderly_count = int(total * elderly_frac)
    ages_elderly = [85 + i % 10 for i in range(elderly_count)]
    ages_young = [40 + i % 30 for i in range(total - elderly_count)]
    ages = ages_elderly + ages_young
    i = 0
    for ward, route, cnt in records:
        for _ in range(cnt):
            rows.append({
                "event_type": "admission",
                "event_date": base + pd.Timedelta(days=i),
                "ward": ward,
                "admission_date": base + pd.Timedelta(days=i),
                "patient_id": f"pid-{i:04d}",
                "attending_doctor": "不明",
                "admission_route": route,
                "short3_type": None,
                "age_years": ages[i] if i < len(ages) else 60,
                "notes": None,
            })
            i += 1
    return pd.DataFrame(rows)


class TestSummaryKPIs:
    """compute_summary_kpis の正しさ."""

    def test_empty_df(self):
        """空 DataFrame でも例外なく 0 相当の結果を返す."""
        r = ppv.compute_summary_kpis(pd.DataFrame({
            "admission_date": [], "ward": [], "admission_route": [], "age_years": []
        }))
        assert r["total"] == 0
        assert r["em_rate_5f"] == 0.0
        assert r["em_rate_6f"] == 0.0
        assert r["monthly_mean"] == 0.0
        assert r["elderly_ratio"] == 0.0

    def test_synthetic_numbers(self):
        """合成データ（5F 10/10, 6F 20/10, 85+=30%）で期待値と一致."""
        df = _make_synth_df(n_5f_em=10, n_5f_sc=10,
                            n_6f_em=20, n_6f_sc=10,
                            elderly_frac=0.3)
        r = ppv.compute_summary_kpis(df)
        assert r["total"] == 50
        assert r["em_rate_5f"] == pytest.approx(50.0, abs=0.01)
        # 6F em rate = 20 / (20+10) = 66.67
        assert r["em_rate_6f"] == pytest.approx(66.67, abs=0.01)
        # 85+ ratio ~30%
        assert 29.0 <= r["elderly_ratio"] <= 31.0


# ---------------------------------------------------------------------------
# 3. 月別推移 / 曜日 / 年齢 / 時間帯 / リードタイム
# ---------------------------------------------------------------------------


class TestMonthlyTrend:
    def test_columns_and_sum(self):
        df = _make_synth_df(10, 10, 10, 10, 0.3)
        m = ppv.compute_monthly_trend(df)
        assert set(m.columns) == {"month", "5F", "6F", "total"}
        # total sum should equal n
        assert int(m["total"].sum()) == 40

    def test_empty(self):
        m = ppv.compute_monthly_trend(pd.DataFrame({
            "admission_date": [], "ward": [], "admission_route": []
        }))
        assert set(m.columns) == {"month", "5F", "6F", "total"}
        assert len(m) == 0


class TestDOWPattern:
    def test_shape_and_columns(self):
        df = _make_synth_df(10, 10, 10, 10, 0.3)
        d = ppv.compute_dow_pattern(df)
        assert d.shape == (7, 4)
        assert set(d.columns) == {"5F_予定", "5F_緊急", "6F_予定", "6F_緊急"}

    def test_ward_totals(self):
        df = _make_synth_df(10, 10, 10, 10, 0.3)
        d = ppv.compute_dow_pattern(df)
        assert d["5F_予定"].sum() == 10
        assert d["5F_緊急"].sum() == 10
        assert d["6F_予定"].sum() == 10
        assert d["6F_緊急"].sum() == 10

    def test_empty(self):
        d = ppv.compute_dow_pattern(pd.DataFrame({
            "admission_date": [], "ward": [], "admission_route": []
        }))
        assert d.empty


class TestAgeDistribution:
    def test_bins(self):
        df = _make_synth_df(10, 10, 10, 10, 0.4)
        r = ppv.compute_age_distribution(df)
        assert r["labels"] == ["<65", "65-74", "75-84", "85+"]
        # 40 * 0.4 = 16
        assert r["counts"][3] == 16
        assert r["elderly_pct"] == pytest.approx(40.0, abs=0.01)

    def test_empty(self):
        r = ppv.compute_age_distribution(pd.DataFrame({
            "admission_date": [], "ward": [], "admission_route": [], "age_years": []
        }))
        assert sum(r["counts"]) == 0
        assert r["elderly_pct"] == 0.0


class TestHourDistribution:
    def test_none_details(self):
        r = ppv.compute_hour_distribution(None)
        assert r["n"] == 0
        assert sum(r["counts"]) == 0

    def test_synth_emergency_daytime(self):
        # 時刻情報付き 10 件の緊急（全て 10 時）
        rows = []
        for i in range(10):
            rows.append({
                "admission_datetime": pd.Timestamp("2025-06-01 10:00:00"),
                "register_date": pd.Timestamp("2025-05-20"),
                "type_short": "緊急",
            })
        df = pd.DataFrame(rows)
        r = ppv.compute_hour_distribution(df)
        assert r["n"] == 10
        assert r["counts"][10] == 10
        assert r["daytime_pct"] == 100.0


class TestLeadTime:
    def test_none_details(self):
        r = ppv.compute_lead_time(None)
        assert r["n"] == 0
        assert r["median"] == 0.0
        assert r["mean"] == 0.0

    def test_synth_scheduled(self):
        # 5 件の予定入院（lead_days = 0, 3, 7, 14, 30）
        rows = []
        leads = [0, 3, 7, 14, 30]
        for ld in leads:
            adm = pd.Timestamp("2025-06-15 09:00:00")
            reg = (adm - pd.Timedelta(days=ld)).normalize()
            rows.append({
                "admission_datetime": adm,
                "register_date": reg,
                "type_short": "予定",
            })
        df = pd.DataFrame(rows)
        r = ppv.compute_lead_time(df)
        assert r["n"] == 5
        assert r["median"] == 7.0
        assert r["mean"] == pytest.approx(10.8, abs=0.01)
        assert len(r["bins"]) == len(r["counts"]) == 7
        # 0 → 当日, 3 → 1-3日, 7 → 4-7日, 14 → 8-14日, 30 → 15-30日
        assert r["counts"][0] == 1  # 当日
        assert r["counts"][1] == 1  # 1-3 日
        assert r["counts"][2] == 1  # 4-7 日
        assert r["counts"][3] == 1  # 8-14 日
        assert r["counts"][4] == 1  # 15-30 日


# ---------------------------------------------------------------------------
# 4. 件数の境界値: FY2025 実データ（存在すれば）1965 件
# ---------------------------------------------------------------------------


class TestBoundaryWithRealData:
    """実際の CSV がリポジトリに含まれるときの件数検証."""

    @pytest.fixture
    def primary_df(self) -> Optional[pd.DataFrame]:
        return ppv._load_primary()

    def test_real_total_is_1965_when_present(self, primary_df):
        """CSV があれば total == 1965 (event_type=admission) でなければならない."""
        if primary_df is None:
            pytest.skip("actual_admissions_2025fy.csv が存在しない環境ではスキップ")
        assert len(primary_df) == 1965

    def test_real_summary_kpis(self, primary_df):
        """KPI が要件定義の範囲に収まる（5F ~53%, 6F ~61%, 85+ ~27-28%）."""
        if primary_df is None:
            pytest.skip("actual_admissions_2025fy.csv が存在しない環境ではスキップ")
        k = ppv.compute_summary_kpis(primary_df)
        assert k["total"] == 1965
        assert 52.0 <= k["em_rate_5f"] <= 54.0, f"5F 緊急率: {k['em_rate_5f']}"
        assert 60.0 <= k["em_rate_6f"] <= 62.0, f"6F 緊急率: {k['em_rate_6f']}"
        # 85+ ratio は仕様 27.7% 前後（データ上 27.4% のため 26-29% の幅を許容）
        assert 26.0 <= k["elderly_ratio"] <= 29.0
        # 月平均 = 1965 / 12 ≈ 163.75
        assert 160.0 <= k["monthly_mean"] <= 167.0


# ---------------------------------------------------------------------------
# 5. CSV 未取り込み時のフォールバック（_load_primary が None を返すとき）
# ---------------------------------------------------------------------------


class TestFallbackNoCSV:
    """CSV が見つからない場合でも例外で落ちないことを保証する."""

    def test_load_primary_returns_none_when_missing(self, tmp_path):
        """_CSV_PRIMARY を存在しないパスに差し替えると None."""
        with patch.object(ppv, "_CSV_PRIMARY", tmp_path / "missing.csv"):
            assert ppv._load_primary() is None

    def test_load_details_returns_none_when_missing(self, tmp_path):
        with patch.object(ppv, "_CSV_DETAILS", tmp_path / "missing.csv"):
            assert ppv._load_details() is None

    def test_render_does_not_raise_without_csv(self, tmp_path):
        """CSV が両方欠けていても描画関数は例外を投げない.

        Streamlit の `st.*` 呼び出しは ScriptRunContext が無くてもエラーにならず
        （警告のみ）、関数は return するだけ。
        """
        # Streamlit の実装都合で警告が出るため、エラーではなく戻り値のみ確認
        with patch.object(ppv, "_CSV_PRIMARY", tmp_path / "missing1.csv"), \
                patch.object(ppv, "_CSV_DETAILS", tmp_path / "missing2.csv"):
            # 例外で落ちないことだけ検証
            try:
                ppv.render_past_performance_view()
            except Exception as e:
                pytest.fail(f"CSV 未取り込み時に例外が発生: {e}")


# ---------------------------------------------------------------------------
# 6. AppTest による画面描画 / data-testid 検証
# ---------------------------------------------------------------------------


def _write_app_entry(path: Path) -> None:
    """AppTest 用の最小エントリファイルを書き出す."""
    path.write_text(
        """
import sys
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import streamlit as st
st.set_page_config(layout='wide')

from views.past_performance_view import render_past_performance_view

render_past_performance_view()
""",
        encoding="utf-8",
    )


class TestAppTestIntegration:
    """Streamlit AppTest による実画面描画."""

    @pytest.fixture
    def app_path(self, tmp_path: Path) -> Path:
        repo_scripts = Path(__file__).resolve().parent.parent / "scripts"
        entry = repo_scripts / "_past_performance_view_test_entry.py"
        _write_app_entry(entry)
        yield entry
        try:
            entry.unlink()
        except FileNotFoundError:
            pass

    def test_app_runs_without_error(self, app_path: Path):
        """render_past_performance_view() が実行エラーなしで走る."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=60)
        at.run()
        assert not at.exception, (
            f"Streamlit 実行時例外: "
            f"{[e.value for e in at.exception]}"
        )

    def test_primary_testids_in_markdown(self, app_path: Path):
        """主要な data-testid が markdown 出力に含まれる."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=60)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        required_testids = [
            "past-perf-total-admissions",
            "past-perf-emergency-rate-5f",
            "past-perf-emergency-rate-6f",
            "past-perf-elderly-ratio",
        ]
        for testid in required_testids:
            assert f'data-testid="{testid}"' in markdown_text, (
                f"testid '{testid}' が画面描画に含まれない"
            )

    def test_total_admissions_reflects_1965_when_csv_present(self, app_path: Path):
        """CSV が存在すれば総入院件数 testid の値は 1965."""
        if ppv._load_primary() is None:
            pytest.skip("CSV 未取り込み環境ではスキップ")
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=60)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        # value は testid_text で 1965 を格納
        assert 'data-testid="past-perf-total-admissions" style="display:none">1965<' in markdown_text
