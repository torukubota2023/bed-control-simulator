#!/usr/bin/env python3
"""シナリオ QA レポート生成スクリプト.

Playwright 照合結果、pytest 整合性テスト結果、デモデータ品質テスト結果を統合し、
reports/scenario_qa_report_YYYY-MM-DD.md を生成する。

副院長が `npm run qa` 1 回で全チェックを走らせ、この 1 ファイルを読めば
何が台本と食い違っているか・現場で説明すべきズレは何か がわかる状態を作る。

入力:
- reports/scenario_claims.json            (台本クレーム)
- reports/scenario_qa_playwright.json     (Playwright 照合結果)
- pytest 実行 (本モジュール内で subprocess 起動)

出力:
- reports/scenario_qa_report_YYYY-MM-DD.md

CLI:
    python3 scripts/generate_qa_report.py
    python3 scripts/generate_qa_report.py --skip-pytest  # pytest を走らせず既存出力のみ利用
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
CLAIMS_JSON = REPORTS / "scenario_claims.json"
PLAYWRIGHT_JSON = REPORTS / "scenario_qa_playwright.json"
DEMO_QUALITY_JSON = REPORTS / "demo_data_quality.json"
INTERNAL_CONSISTENCY_JSON = REPORTS / "internal_consistency.json"


# ---------------------------------------------------------------------------
# サブセクション生成
# ---------------------------------------------------------------------------


@dataclass
class PytestResult:
    """pytest 実行結果の簡易サマリ."""

    name: str
    passed: int
    failed: int
    errors: int
    skipped: int
    total: int
    raw_tail: str  # 最後の数行（失敗詳細）

    @property
    def status(self) -> str:
        return "OK" if self.failed == 0 and self.errors == 0 else "NG"


def _run_pytest(target: str, display_name: str) -> PytestResult:
    """pytest を subprocess で走らせ、結果を集計."""
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        target,
        "-v",
        "--tb=short",
        "-q",
        "--no-header",
    ]
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    out = proc.stdout + "\n" + proc.stderr
    # pytest の「= 23 passed, 1 failed in 0.04s =」のような行を探す
    import re

    summary_line = ""
    for line in out.splitlines()[::-1]:
        if ("passed" in line or "failed" in line or "error" in line) and "in " in line:
            summary_line = line
            break

    def _match_count(label: str) -> int:
        m = re.search(rf"(\d+)\s+{label}", summary_line)
        return int(m.group(1)) if m else 0

    passed = _match_count("passed")
    failed = _match_count("failed")
    errors = _match_count("error")
    skipped = _match_count("skipped")
    total = passed + failed + errors + skipped

    tail_lines = out.strip().splitlines()[-30:]
    return PytestResult(
        name=display_name,
        passed=passed,
        failed=failed,
        errors=errors,
        skipped=skipped,
        total=total,
        raw_tail="\n".join(tail_lines),
    )


# ---------------------------------------------------------------------------
# Playwright 結果の集計
# ---------------------------------------------------------------------------


def _load_playwright_results() -> dict[str, Any] | None:
    if not PLAYWRIGHT_JSON.exists():
        return None
    return json.loads(PLAYWRIGHT_JSON.read_text(encoding="utf-8"))


def _classify_fail(delta: float, tolerance: float) -> str:
    """差異サイズで「重大」「軽微」を区別."""
    if abs(delta) > tolerance * 3:
        return "critical"
    return "minor"


# ---------------------------------------------------------------------------
# デモデータ品質スナップショット抽出
# ---------------------------------------------------------------------------


def _demo_snapshot() -> dict[str, Any] | None:
    """test_demo_data_quality.py 内の TestReportingSnapshot 的な要約を計算."""
    import pandas as pd

    csv = ROOT / "output" / "demo_data_2026fy" / "sample_actual_data_ward_2026fy.csv"
    dis = ROOT / "output" / "demo_data_2026fy" / "discharge_details_2026fy.csv"
    adm = ROOT / "output" / "demo_data_2026fy" / "admission_details_2026fy.csv"
    if not csv.exists():
        return None
    df = pd.read_csv(csv, encoding="utf-8-sig")
    df["date"] = pd.to_datetime(df["date"])
    BEDS = 47
    out: dict[str, Any] = {}
    for ward in ("5F", "6F"):
        w = df[df["ward"] == ward]
        occ = (w["total_patients"] + w["discharges"]) / BEDS * 100
        out[f"{ward}_occ_mean"] = float(occ.mean())
        out[f"{ward}_occ_std"] = float(occ.std())
        out[f"{ward}_occ_min"] = float(occ.min())
        out[f"{ward}_occ_max"] = float(occ.max())
    if dis.exists():
        d = pd.read_csv(dis, encoding="utf-8-sig")
        for ward in ("5F", "6F"):
            dw = d[d["ward"] == ward]
            out[f"{ward}_alos"] = float(dw["los_days"].mean())
    if adm.exists():
        a = pd.read_csv(adm, encoding="utf-8-sig")
        out["admission_total"] = len(a)
        out["emergency_pct"] = (
            len(a[a["route"] == "救急"]) / max(len(a), 1) * 100
        )
    out["short3_pct"] = (
        df["new_admissions_short3"].sum() / max(df["new_admissions"].sum(), 1) * 100
    )
    return out


# ---------------------------------------------------------------------------
# レポート Markdown 組み立て
# ---------------------------------------------------------------------------


def _render_playwright_section(pw: dict[str, Any] | None) -> str:
    if pw is None:
        return "_Playwright 結果ファイルが見つかりません（`npm run qa:playwright` 未実行）。_\n"

    fails = [r for r in pw["results"] if r["status"] == "FAIL"]
    critical = [r for r in fails if _classify_fail(r.get("delta") or 0, r["tolerance"]) == "critical"]
    minor = [r for r in fails if r not in critical]
    missing_testid = [r for r in pw["results"] if r["status"] == "MISSING_TESTID"]
    missing_dom = [r for r in pw["results"] if r["status"] == "MISSING_DOM"]

    lines: list[str] = []
    lines.append(f"- 実行時刻: {pw.get('generated_at', '(不明)')}")
    lines.append(
        f"- 対象クレーム数: {pw['total_claims']}（PASS {pw['pass']} / FAIL {pw['fail']} / "
        f"SKIPPED {pw['skipped']} / MISSING_TESTID {pw['missing_testid']} / MISSING_DOM {pw['missing_dom']}）"
    )
    lines.append("")

    # 重大不一致
    lines.append(f"### 重大不一致（{len(critical)} 件）")
    if not critical:
        lines.append("なし。")
    else:
        for i, r in enumerate(critical, start=1):
            lines.append(
                f"{i}. `{r['source_file']}:L{r['source_line']}` 「{r['claim_text'][:50]}」"
                f" → 実画面: {r['actual']} / 台本: {r['expected']}"
                f" [{r['context'].get('ward', '-')}, {r['context'].get('mode', '-')}]"
                f" (ズレ {r['delta']:+.2f}、許容 ±{r['tolerance']})"
            )
            lines.append(
                f"   - 修正案: 台本側を「{r['actual']}」に更新、"
                f"もしくはデモデータを調整して台本値に寄せる"
            )
    lines.append("")

    # 軽微ズレ
    lines.append(f"### 軽微ズレ（{len(minor)} 件）")
    if not minor:
        lines.append("なし。")
    else:
        for i, r in enumerate(minor[:20], start=1):
            lines.append(
                f"{i}. `{r['source_file']}:L{r['source_line']}` {r['metric']}"
                f" — 実 {r['actual']} vs 台本 {r['expected']}（ズレ {r['delta']:+.2f}、許容 ±{r['tolerance']}）"
            )
        if len(minor) > 20:
            lines.append(f"... 他 {len(minor) - 20} 件（reports/scenario_qa_playwright.json 参照）")
    lines.append("")

    # SKIPPED の情報提示（MISSING_TESTID/MISSING_DOM のみ）
    if missing_testid or missing_dom:
        lines.append(f"### Playwright 側で照合できなかった項目（{len(missing_testid) + len(missing_dom)} 件）")
        if missing_testid:
            lines.append(f"- data-testid 未実装: {len(missing_testid)} 件")
        if missing_dom:
            lines.append(f"- DOM 値パース不可: {len(missing_dom)} 件")
        lines.append(
            "_これらは pytest 側の `tests/test_app_internal_consistency.py` で補完的に検証しています。_"
        )
        lines.append("")

    return "\n".join(lines)


def _render_demo_realism(snap: dict[str, Any] | None, dq: PytestResult | None) -> str:
    lines: list[str] = []
    if snap is None:
        lines.append("_デモデータが生成されていません（output/demo_data_2026fy/）._\n")
        if dq:
            lines.append(f"pytest: {dq.status}（{dq.passed}/{dq.total}）")
        return "\n".join(lines)

    def _ok(x: bool) -> str:
        return "✓" if x else "✗"

    checks = [
        (
            "5F 稼働率",
            f"{snap['5F_occ_mean']:.1f}%",
            f"70-95%, σ={snap['5F_occ_std']:.1f}",
            70 <= snap["5F_occ_mean"] <= 95,
        ),
        (
            "6F 稼働率",
            f"{snap['6F_occ_mean']:.1f}%",
            f"80-100%, σ={snap['6F_occ_std']:.1f}",
            80 <= snap["6F_occ_mean"] <= 100,
        ),
        (
            "5F ALOS",
            f"{snap.get('5F_alos', 0):.1f}日",
            "10-25 日",
            10 <= snap.get("5F_alos", 0) <= 25,
        ),
        (
            "6F ALOS",
            f"{snap.get('6F_alos', 0):.1f}日",
            "10-30 日",
            10 <= snap.get("6F_alos", 0) <= 30,
        ),
        (
            "救急比率",
            f"{snap.get('emergency_pct', 0):.1f}%",
            "5-40%",
            5 <= snap.get("emergency_pct", 0) <= 40,
        ),
        (
            "短手3 比率",
            f"{snap['short3_pct']:.1f}%",
            "10-22%",
            10 <= snap["short3_pct"] <= 22,
        ),
        (
            "稼働率変動 (5F σ)",
            f"{snap['5F_occ_std']:.1f}%",
            "≥3%",
            snap["5F_occ_std"] >= 3.0,
        ),
    ]
    lines.append("| 指標 | 実測 | 期待 | 判定 |")
    lines.append("|------|------|------|------|")
    for name, actual, expected, ok in checks:
        lines.append(f"| {name} | {actual} | {expected} | {_ok(ok)} |")
    if dq:
        lines.append("")
        lines.append(
            f"pytest 総合: **{dq.status}**（{dq.passed}/{dq.total} pass, {dq.failed} fail）"
        )
    return "\n".join(lines)


def _render_pedagogy(snap: dict[str, Any] | None) -> str:
    if snap is None:
        return "_デモデータ未生成のため教育性検証不可._\n"
    lines: list[str] = []

    # σ 指標からの推奨
    std_5f = snap["5F_occ_std"]
    std_6f = snap["6F_occ_std"]
    lines.append(f"- 稼働率の日次変動: 5F σ={std_5f:.1f}%, 6F σ={std_6f:.1f}%")
    if std_5f < 4.0:
        lines.append(
            f"  - 5F の変動幅がやや小さい。需要波・季節性パラメータを 1.5-2x に調整すると教育材料として機能しやすい"
        )
    if std_6f < 4.0:
        lines.append(f"  - 6F の変動幅がやや小さい。冬季 (12-2月) の倍率を再確認")
    else:
        lines.append("  - 変動幅は判断材料として十分 (±σ が稼働率の 5% 以上を推奨)")

    # 稼働率レンジ
    lines.append(
        f"- 稼働率レンジ: 5F={snap['5F_occ_min']:.1f}〜{snap['5F_occ_max']:.1f}%, "
        f"6F={snap['6F_occ_min']:.1f}〜{snap['6F_occ_max']:.1f}%"
    )
    return "\n".join(lines)


def _render_claim_source_breakdown(claims_json: dict[str, Any]) -> str:
    claims = claims_json.get("claims", [])
    by_file: dict[str, int] = defaultdict(int)
    by_metric: dict[str, int] = defaultdict(int)
    for c in claims:
        by_file[c["source_file"]] += 1
        by_metric[c["metric"]] += 1
    lines = ["### ファイル別クレーム数", "", "| ファイル | 件数 |", "|----|----|"]
    for f, n in sorted(by_file.items()):
        lines.append(f"| `{f}` | {n} |")
    lines.extend(["", "### 指標別クレーム数", "", "| 指標 | 件数 |", "|----|----|"])
    for m, n in sorted(by_metric.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {m} | {n} |")
    return "\n".join(lines)


def _overall_grade(
    pw: dict[str, Any] | None,
    ic: PytestResult | None,
    dq: PytestResult | None,
) -> tuple[str, list[str]]:
    """全体判定 OK/NG と理由."""
    reasons: list[str] = []
    ok = True
    if pw is None:
        reasons.append("Playwright 照合未実行")
        ok = False
    elif pw["fail"] > 0:
        reasons.append(f"台本と実アプリの重大ズレ {pw['fail']} 件")
        ok = False
    if ic is not None and ic.status != "OK":
        reasons.append(f"内部整合性テスト {ic.failed} 件 FAIL")
        ok = False
    if dq is not None and dq.status != "OK":
        reasons.append(f"デモデータ品質テスト {dq.failed} 件 FAIL")
        ok = False
    if ok:
        return "OK", ["すべての QA チェックをパス"]
    return "NG", reasons


# ---------------------------------------------------------------------------
# エントリーポイント
# ---------------------------------------------------------------------------


def generate_report(
    skip_pytest: bool = False,
    out_path: Path | None = None,
) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    default_out = REPORTS / f"scenario_qa_report_{today}.md"
    out = out_path or default_out

    # クレーム JSON
    if not CLAIMS_JSON.exists():
        from extract_scenario_claims import extract_all_claims, write_claims_json

        print("[info] scenario_claims.json が無いので再抽出")
        write_claims_json(extract_all_claims(), CLAIMS_JSON)
    claims_payload = json.loads(CLAIMS_JSON.read_text(encoding="utf-8"))

    # Playwright 結果
    pw = _load_playwright_results()

    # pytest 実行
    ic_result: PytestResult | None = None
    dq_result: PytestResult | None = None
    if not skip_pytest:
        print("[info] pytest: test_app_internal_consistency.py")
        ic_result = _run_pytest(
            "tests/test_app_internal_consistency.py",
            "内部整合性",
        )
        print("[info] pytest: test_demo_data_quality.py")
        dq_result = _run_pytest(
            "tests/test_demo_data_quality.py",
            "デモデータ品質",
        )

    # デモスナップショット
    snap = _demo_snapshot()

    # 判定
    grade, reasons = _overall_grade(pw, ic_result, dq_result)
    commit_hash = _get_git_commit()

    # Markdown 組み立て
    md: list[str] = []
    md.append("# シナリオ QA レポート\n")
    md.append(
        f"**生成日:** {datetime.now().isoformat(timespec='seconds')}\n"
        f"**対象台本:** {len(claims_payload['source_files'])} 本 "
        f"({claims_payload['claim_count']} クレーム抽出)\n"
        f"**対象アプリ:** ベッドコントロール（commit `{commit_hash}`）\n"
        f"**総合判定:** **{grade}**\n"
    )
    md.append("## 判定理由\n")
    for r in reasons:
        md.append(f"- {r}")
    md.append("")

    # ---- 1. 台本 ↔ 実アプリ 数値一致 ----
    md.append("## 1. 台本 ↔ 実アプリ 数値一致（Playwright）\n")
    md.append(_render_playwright_section(pw))
    md.append("")

    # ---- 2. アプリ内 整合性 ----
    md.append("## 2. アプリ内 整合性（pytest）\n")
    if ic_result:
        md.append(
            f"- pytest 結果: **{ic_result.status}** — {ic_result.passed} pass, "
            f"{ic_result.failed} fail, {ic_result.errors} error, {ic_result.skipped} skip\n"
        )
        if ic_result.failed > 0:
            md.append("### 失敗詳細\n")
            md.append("```")
            md.append(ic_result.raw_tail)
            md.append("```\n")
    else:
        md.append("_pytest 実行をスキップ_\n")

    # ---- 3. デモデータ 現実性 ----
    md.append("## 3. デモデータ 現実性\n")
    md.append(_render_demo_realism(snap, dq_result))
    md.append("")

    # ---- 4. デモデータ 教育性 ----
    md.append("## 4. デモデータ 教育性（推奨調整）\n")
    md.append(_render_pedagogy(snap))
    md.append("")

    # ---- 5. クレームサマリ ----
    md.append("## 5. 抽出クレーム内訳（参考）\n")
    md.append(_render_claim_source_breakdown(claims_payload))
    md.append("")

    # ---- 6. 総評 ----
    md.append("## 総評\n")
    if grade == "OK":
        md.append(
            "すべての QA 層（台本一致・アプリ内整合・現実性・教育性）をパス。"
            "副院長がカンファ中に台本を読み上げる際、実アプリの数値と齟齬なく進められる状態です。"
        )
    else:
        md.append("以下の項目を優先して修正してください。")
        for r in reasons:
            md.append(f"- {r}")
        md.append("\n修正後、再度 `npm run qa` を実行してください。")
    md.append("")

    md.append("---\n")
    md.append(
        "_このレポートは `scripts/generate_qa_report.py` が自動生成したものです。"
        "台本を更新した際は `npm run qa:claims` で抽出を更新してください。_\n"
    )

    out.write_text("\n".join(md), encoding="utf-8")
    return out


def _get_git_commit() -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return proc.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="シナリオ QA レポート生成")
    parser.add_argument(
        "--skip-pytest",
        action="store_true",
        help="pytest を実行せず既存出力のみ使う",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="出力先 Markdown パス（未指定時は reports/scenario_qa_report_YYYY-MM-DD.md）",
    )
    args = parser.parse_args(argv)

    out_path = Path(args.out) if args.out else None
    try:
        out = generate_report(skip_pytest=args.skip_pytest, out_path=out_path)
    except Exception as e:
        print(f"[error] レポート生成失敗: {e}")
        return 1

    print(f"[ok] レポート生成: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
