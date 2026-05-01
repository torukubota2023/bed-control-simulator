"""管理者用 3 KPI ストリップの整合性テスト（2026-05-01 副院長指摘）.

副院長が画面で発見したバグ:
  画面内に「全体 稼働率 88.8%」と「90.4%」が混在していた。
  原因: `_get_top_kpi_snapshot()` で稼働率だけ「当月の月平均」を返していたが、
       同じ KPI ストリップ内の空床・在院患者数は「最新日（当日）」を使っており、
       期間が混在していたため。

修正方針:
  3 KPI すべて「最新日スナップショット」に統一（朝礼で「今いま」を即答する用途）。

このテストは、修正の退行を防ぐためにソースコード上で次を確認する:
  1. `_get_top_kpi_snapshot()` 内で `sorted_raw.iloc[-1]` を使っている
  2. `_get_top_kpi_snapshot()` 内で `monthly[...].mean()` を使っていない
     （= 月平均計算が再混入していない）
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = REPO_ROOT / "scripts" / "bed_control_simulator_app.py"


def _extract_function_source(src: str, func_name: str) -> str:
    """関数定義の本体を抽出（次の def または module-level 行まで）."""
    lines = src.split("\n")
    start = None
    for i, line in enumerate(lines):
        if re.match(rf"^def {re.escape(func_name)}\(", line):
            start = i
            break
    if start is None:
        raise AssertionError(f"function not found: {func_name}")

    # def の次行から、インデントが下がる（または次の def）まで取る
    body = []
    for line in lines[start + 1:]:
        # 空行はそのまま含める
        if not line.strip():
            body.append(line)
            continue
        # トップレベルの def / class / 通常文（非インデント）が来たら終了
        if not line[0].isspace():
            break
        body.append(line)
    return "\n".join(body)


def test_get_top_kpi_snapshot_uses_latest_day_for_occupancy():
    """_get_top_kpi_snapshot は稼働率を「当日（最新日）」から取得する."""
    src = APP_PATH.read_text(encoding="utf-8")
    body = _extract_function_source(src, "_get_top_kpi_snapshot")

    # 最新日スナップショットを使っている
    assert "sorted_raw.iloc[-1]" in body, (
        "_get_top_kpi_snapshot() が最新日スナップショット (sorted_raw.iloc[-1]) を"
        "使っていません。月平均計算が再混入した可能性があります。"
    )


def test_get_top_kpi_snapshot_does_not_use_monthly_mean():
    """_get_top_kpi_snapshot で月平均計算 (.mean()) を使っていない."""
    src = APP_PATH.read_text(encoding="utf-8")
    body = _extract_function_source(src, "_get_top_kpi_snapshot")

    # 月平均パターン（monthly[...].mean()） が body 内に無い
    forbidden_patterns = [
        r"monthly\[[^\]]+\]\.mean\(\)",
        # 念のため latest_row 以外で month-average を計算するパターンも禁止
    ]
    for pat in forbidden_patterns:
        assert not re.search(pat, body), (
            f"_get_top_kpi_snapshot() で禁止パターン {pat!r} を検出。"
            "月平均計算が再混入した可能性があります。3 KPI は最新日に統一してください。"
        )


def test_get_top_kpi_snapshot_documents_the_2026_05_01_fix():
    """修正の意図を残すコメントが本体内に存在する（将来の再発防止コンテキスト）."""
    src = APP_PATH.read_text(encoding="utf-8")
    body = _extract_function_source(src, "_get_top_kpi_snapshot")

    # 2026-05-01 修正コメントが残っている
    assert "2026-05-01" in body, (
        "_get_top_kpi_snapshot() に 2026-05-01 の修正経緯コメントがありません。"
        "再発防止のため、修正理由のコメントは残してください。"
    )
