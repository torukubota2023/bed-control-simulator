"""管理者用 3 KPI ストリップの整合性テスト（2026-05-01 副院長指摘 + 仕様再調整）.

経緯:
  Phase 1: 副院長が画面内で「全体 稼働率 88.8%」（月平均）と「90.4%」（当日）が
            混在しているのを発見 → 一旦すべて当日値に統一。
  Phase 2: 再考の結果、月平均は経営判断に必須なので **両方表示** する仕様に変更:
            - 主表示: 当日値（直近）
            - 括弧併記: 月平均（経営目標 90% 達成ペースの判定に必要）
            ラベルでも「月末目標 ≥ 90%」を明示し、混乱を防止。

このテストは、両方の値が並存する仕様が崩れないよう次を確認する:
  1. `_get_top_kpi_snapshot()` の戻り値に `occupancy` (当日値) と
     `occupancy_month_avg` (月平均) の両方が含まれる
  2. `_get_top_kpi_snapshot()` 内で当日値計算 (`sorted_raw.iloc[-1]`) と
     月平均計算 (`.mean()`) の両方が使われている
  3. `_render_admin_kpi_strip` で月平均が「（月平均 X.X%）」形式で併記される
  4. ラベル「月末目標 ≥ 90%」がコード上に存在する（ゲージタイトル）
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

    body = []
    for line in lines[start + 1:]:
        if not line.strip():
            body.append(line)
            continue
        if not line[0].isspace():
            break
        body.append(line)
    return "\n".join(body)


# --------------------------------------------------------------------------
# _get_top_kpi_snapshot のテスト
# --------------------------------------------------------------------------

def test_snapshot_uses_latest_day_for_occupancy():
    """主表示の稼働率は当日（最新日）スナップショットから取得する."""
    body = _extract_function_source(APP_PATH.read_text(encoding="utf-8"),
                                     "_get_top_kpi_snapshot")
    assert "sorted_raw.iloc[-1]" in body, (
        "_get_top_kpi_snapshot() が当日値 (sorted_raw.iloc[-1]) を取得していない"
    )


def test_snapshot_also_returns_month_average():
    """戻り値に occupancy_month_avg が含まれる（月平均併記用）."""
    body = _extract_function_source(APP_PATH.read_text(encoding="utf-8"),
                                     "_get_top_kpi_snapshot")
    assert '"occupancy_month_avg"' in body, (
        "_get_top_kpi_snapshot() の戻り値に occupancy_month_avg がありません。"
        "月平均併記のため必要です。"
    )
    # mean 計算が当月フィルタの上で行われている
    assert ".mean()" in body, (
        "_get_top_kpi_snapshot() 内で月平均計算 (.mean()) が見当たりません。"
    )


def test_snapshot_documents_the_2026_05_01_fix():
    """修正経緯コメントが残っている（将来の再発防止）."""
    body = _extract_function_source(APP_PATH.read_text(encoding="utf-8"),
                                     "_get_top_kpi_snapshot")
    assert "2026-05-01" in body, (
        "_get_top_kpi_snapshot() に修正経緯コメント（2026-05-01）がありません。"
    )


# --------------------------------------------------------------------------
# _render_admin_kpi_strip のテスト
# --------------------------------------------------------------------------

def test_strip_renders_month_average_in_parentheses():
    """KPI ストリップで月平均が「（月平均 X.X%）」形式で表示される."""
    body = _extract_function_source(APP_PATH.read_text(encoding="utf-8"),
                                     "_render_admin_kpi_strip")
    assert "月平均" in body, (
        "_render_admin_kpi_strip で「月平均」表記が見当たりません。"
        "副院長指示で当日値の右に括弧併記する必要があります。"
    )
    assert "occupancy_month_avg" in body, (
        "_render_admin_kpi_strip が snapshot から occupancy_month_avg を"
        "読んでいません。"
    )


def test_strip_label_shows_recent_keyword():
    """KPI ストリップの稼働率ラベルが「直近」であることを示す."""
    src = APP_PATH.read_text(encoding="utf-8")
    # _render_admin_kpi_strip 内の HTML テンプレ（ヒアドキュメント）
    # の中に「稼働率（直近）」が含まれることを確認
    assert "稼働率（直近）" in src, (
        "_render_admin_kpi_strip のラベルが「稼働率（直近）」になっていません。"
        "月平均と区別するため明示してください。"
    )


# --------------------------------------------------------------------------
# 「月末目標」明示のテスト（本日の詳細サマリー内）
# --------------------------------------------------------------------------

def test_today_summary_shows_month_end_target_in_gauge():
    """本日の詳細サマリー内のゲージに「月末目標 ≥ X%」が明示される."""
    src = APP_PATH.read_text(encoding="utf-8")
    # ゲージタイトルに月末目標表記がある
    assert "月末目標" in src, (
        "本日の詳細サマリーのゲージに「月末目標」表記がありません。"
        "副院長指示: 月末で目標 90% 以上が目標であることを分かりやすく。"
    )
    assert "現時点の月平均稼働率" in src, (
        "ゲージタイトルが「現時点の月平均稼働率」になっていません。"
    )
