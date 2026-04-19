"""QA レポート生成器のユニットテスト.

カバレッジ:
- レポート Markdown が想定形式で出力される
- Playwright 結果・pytest 結果・デモ品質がすべて反映される
- 総合判定ロジック
- pytest 実行部分は skip_pytest=True でモック的に回避
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from generate_qa_report import (  # noqa: E402
    PytestResult,
    _classify_fail,
    _overall_grade,
    _render_claim_source_breakdown,
    _render_demo_realism,
    _render_pedagogy,
    _render_playwright_section,
    generate_report,
)


# ---------------------------------------------------------------------------
# _classify_fail
# ---------------------------------------------------------------------------


class TestClassifyFail:
    def test_within_tolerance_is_minor(self):
        # 差異 1 < 許容 1.5 * 3 = 4.5
        assert _classify_fail(1.0, 1.5) == "minor"

    def test_above_3x_tolerance_is_critical(self):
        assert _classify_fail(5.0, 1.5) == "critical"

    def test_negative_delta_handled(self):
        assert _classify_fail(-5.0, 1.5) == "critical"


# ---------------------------------------------------------------------------
# _overall_grade
# ---------------------------------------------------------------------------


class TestOverallGrade:
    def test_all_ok(self):
        pw = {"fail": 0}
        ic = PytestResult("x", 10, 0, 0, 0, 10, "")
        dq = PytestResult("y", 20, 0, 0, 0, 20, "")
        grade, reasons = _overall_grade(pw, ic, dq)
        assert grade == "OK"

    def test_playwright_missing_is_ng(self):
        grade, reasons = _overall_grade(None, None, None)
        assert grade == "NG"
        assert any("Playwright" in r for r in reasons)

    def test_playwright_fail_is_ng(self):
        pw = {"fail": 3}
        grade, reasons = _overall_grade(pw, None, None)
        assert grade == "NG"
        assert any("3" in r for r in reasons)

    def test_consistency_fail_is_ng(self):
        pw = {"fail": 0}
        ic = PytestResult("x", 9, 1, 0, 0, 10, "")
        grade, reasons = _overall_grade(pw, ic, None)
        assert grade == "NG"

    def test_demo_quality_fail_is_ng(self):
        pw = {"fail": 0}
        dq = PytestResult("y", 19, 1, 0, 0, 20, "")
        grade, reasons = _overall_grade(pw, None, dq)
        assert grade == "NG"


# ---------------------------------------------------------------------------
# _render_playwright_section
# ---------------------------------------------------------------------------


class TestRenderPlaywrightSection:
    def test_missing_file(self):
        result = _render_playwright_section(None)
        assert "見つかりません" in result

    def test_no_failures(self):
        pw = {
            "generated_at": "2026-04-19T00:00:00Z",
            "total_claims": 10,
            "pass": 9,
            "fail": 0,
            "skipped": 1,
            "missing_testid": 0,
            "missing_dom": 0,
            "results": [],
        }
        result = _render_playwright_section(pw)
        assert "重大不一致（0 件）" in result
        assert "軽微ズレ（0 件）" in result
        assert "なし。" in result

    def test_critical_failures_rendered(self):
        pw = {
            "generated_at": "2026-04-19T00:00:00Z",
            "total_claims": 2,
            "pass": 0,
            "fail": 2,
            "skipped": 0,
            "missing_testid": 0,
            "missing_dom": 0,
            "results": [
                {
                    "claim_id": "c1",
                    "source_file": "docs/admin/x.md",
                    "source_line": 73,
                    "metric": "occupancy_pct",
                    "expected": 85.0,
                    "actual": 99.0,
                    "tolerance": 1.5,
                    "status": "FAIL",
                    "delta": 14.0,  # >3x tolerance → critical
                    "claim_text": "今月の稼働率は 85%",
                    "context": {"ward": "5F", "mode": "normal"},
                    "note": "",
                },
                {
                    "claim_id": "c2",
                    "source_file": "docs/admin/y.md",
                    "source_line": 100,
                    "metric": "alos_days",
                    "expected": 17.5,
                    "actual": 18.3,
                    "tolerance": 1.0,
                    "status": "FAIL",
                    "delta": 0.8,  # minor
                    "claim_text": "ALOS 17.5 日",
                    "context": {"ward": None, "mode": "normal"},
                    "note": "",
                },
            ],
        }
        result = _render_playwright_section(pw)
        assert "重大不一致（1 件）" in result
        assert "軽微ズレ（1 件）" in result
        assert "docs/admin/x.md:L73" in result
        assert "docs/admin/y.md:L100" in result

    def test_missing_testid_reported(self):
        pw = {
            "generated_at": "2026-04-19T00:00:00Z",
            "total_claims": 1,
            "pass": 0,
            "fail": 0,
            "skipped": 0,
            "missing_testid": 1,
            "missing_dom": 0,
            "results": [
                {
                    "claim_id": "c3",
                    "source_file": "a.md",
                    "source_line": 1,
                    "metric": "foo",
                    "expected": 10,
                    "actual": None,
                    "tolerance": 1,
                    "status": "MISSING_TESTID",
                    "delta": None,
                    "claim_text": "",
                    "context": {"ward": None, "mode": "normal"},
                    "note": "",
                },
            ],
        }
        result = _render_playwright_section(pw)
        assert "MISSING_TESTID" in result or "data-testid 未実装" in result


# ---------------------------------------------------------------------------
# _render_demo_realism
# ---------------------------------------------------------------------------


class TestRenderDemoRealism:
    def test_snapshot_none(self):
        assert "生成されていません" in _render_demo_realism(None, None)

    def test_snapshot_renders_table(self):
        snap = {
            "5F_occ_mean": 85.9,
            "5F_occ_std": 9.2,
            "5F_occ_min": 55.3,
            "5F_occ_max": 110.6,
            "6F_occ_mean": 97.1,
            "6F_occ_std": 7.1,
            "6F_occ_min": 72.3,
            "6F_occ_max": 110.6,
            "5F_alos": 13.2,
            "6F_alos": 20.5,
            "admission_total": 1851,
            "emergency_pct": 19.1,
            "short3_pct": 14.2,
        }
        result = _render_demo_realism(snap, None)
        assert "5F 稼働率" in result
        assert "85.9%" in result
        assert "| 指標 | 実測" in result  # テーブルヘッダ


# ---------------------------------------------------------------------------
# _render_pedagogy
# ---------------------------------------------------------------------------


class TestRenderPedagogy:
    def test_none_returns_notice(self):
        assert "不可" in _render_pedagogy(None)

    def test_high_variance_is_praised(self):
        snap = {
            "5F_occ_std": 9.2,
            "6F_occ_std": 7.1,
            "5F_occ_min": 55,
            "5F_occ_max": 110,
            "6F_occ_min": 72,
            "6F_occ_max": 110,
        }
        result = _render_pedagogy(snap)
        assert "十分" in result

    def test_low_variance_suggests_adjustment(self):
        snap = {
            "5F_occ_std": 2.1,
            "6F_occ_std": 2.5,
            "5F_occ_min": 80,
            "5F_occ_max": 92,
            "6F_occ_min": 85,
            "6F_occ_max": 93,
        }
        result = _render_pedagogy(snap)
        # 調整提案が入る
        assert "調整" in result or "再確認" in result


# ---------------------------------------------------------------------------
# _render_claim_source_breakdown
# ---------------------------------------------------------------------------


class TestRenderClaimSourceBreakdown:
    def test_renders_tables(self):
        payload = {
            "claims": [
                {"source_file": "a.md", "metric": "occupancy_pct"},
                {"source_file": "a.md", "metric": "alos_days"},
                {"source_file": "b.md", "metric": "occupancy_pct"},
            ]
        }
        md = _render_claim_source_breakdown(payload)
        assert "ファイル別クレーム数" in md
        assert "a.md" in md
        assert "b.md" in md
        assert "指標別クレーム数" in md


# ---------------------------------------------------------------------------
# エンドツーエンド: generate_report
# ---------------------------------------------------------------------------


class TestGenerateReport:
    def test_generates_markdown(self, tmp_path):
        # pytest を走らせず、既存の claims と playwright を利用
        out = tmp_path / "report.md"
        result = generate_report(skip_pytest=True, out_path=out)
        assert result == out
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "# シナリオ QA レポート" in content
        assert "## 1. 台本 ↔ 実アプリ 数値一致" in content
        assert "## 2. アプリ内 整合性" in content
        assert "## 3. デモデータ 現実性" in content
        assert "## 4. デモデータ 教育性" in content
        assert "## 5. 抽出クレーム内訳" in content

    def test_missing_playwright_shows_notice(self, tmp_path, monkeypatch):
        """Playwright JSON 不在時は警告を表示."""
        from generate_qa_report import PLAYWRIGHT_JSON

        # 一時的にパスを変更
        import generate_qa_report as mod

        bogus = tmp_path / "nonexistent.json"
        monkeypatch.setattr(mod, "PLAYWRIGHT_JSON", bogus)
        out = tmp_path / "report.md"
        generate_report(skip_pytest=True, out_path=out)
        content = out.read_text(encoding="utf-8")
        assert "見つかりません" in content


# ---------------------------------------------------------------------------
# PytestResult
# ---------------------------------------------------------------------------


class TestPytestResult:
    def test_status_ok(self):
        r = PytestResult("x", 10, 0, 0, 0, 10, "")
        assert r.status == "OK"

    def test_status_ng_on_fail(self):
        r = PytestResult("x", 9, 1, 0, 0, 10, "")
        assert r.status == "NG"

    def test_status_ng_on_error(self):
        r = PytestResult("x", 9, 0, 1, 0, 10, "")
        assert r.status == "NG"
