"""v4 制度確認タブ（scripts/tabs/regulation_tab.py）の軽量確認テスト。

Phase 1.8（2026-05-01）横展開で、`gr_config` に `manual_seeds` と
`monthly_summary` が含まれることを確認する。
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REGULATION_TAB = REPO_ROOT / "scripts" / "tabs" / "regulation_tab.py"


def test_regulation_tab_imports():
    """regulation_tab.py が import できる（構文エラーなし）。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "regulation_tab", REGULATION_TAB
    )
    assert spec is not None and spec.loader is not None
    # exec_module まで走らせると streamlit 依存が出るので、ソース構文チェックに留める
    src = REGULATION_TAB.read_text(encoding="utf-8")
    compile(src, str(REGULATION_TAB), "exec")


def test_gr_config_includes_manual_seeds():
    """gr_config に manual_seeds キーが追加されている（Phase 1.8 横展開）."""
    src = REGULATION_TAB.read_text(encoding="utf-8")
    # manual_seeds の試行 import が含まれている
    assert "load_manual_seeds_from_yaml" in src
    # gr_config 辞書内に manual_seeds キーがある
    assert re.search(r'"manual_seeds"\s*:', src) is not None


def test_gr_config_includes_monthly_summary():
    """gr_config に monthly_summary キーが追加されている。"""
    src = REGULATION_TAB.read_text(encoding="utf-8")
    assert re.search(r'"monthly_summary"\s*:', src) is not None


def test_seed_loader_failure_falls_back_to_none():
    """シードロード失敗時に None フォールバックが書かれている。"""
    src = REGULATION_TAB.read_text(encoding="utf-8")
    # try/except で None フォールバック
    pattern = re.compile(
        r"try:.*?load_manual_seeds_from_yaml.*?except\s+Exception:\s*\n\s*_reg_manual_seeds\s*=\s*None",
        re.DOTALL,
    )
    assert pattern.search(src) is not None
