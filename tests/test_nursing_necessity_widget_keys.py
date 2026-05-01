"""看護必要度関連 Streamlit 画面の widget key 衝突防止テスト.

Phase 1.9（2026-05-01）: ダイアログとタブで同一 render 関数を呼ぶときに
``StreamlitDuplicateElementKey`` が発生しないよう、各 render 関数に
``key_prefix`` 引数が用意されていることを確認する。
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, relpath: str):
    """Streamlit を import せずソースだけ読み込む補助関数."""
    src = (REPO_ROOT / relpath).read_text(encoding="utf-8")
    return src


def test_render_references_accepts_key_prefix():
    """nursing_necessity_lecture.render_references が key_prefix を受け取る."""
    from nursing_necessity_lecture import render_references
    sig = inspect.signature(render_references)
    assert "key_prefix" in sig.parameters
    # キーワード引数（*, key_prefix=...）として定義されている
    assert sig.parameters["key_prefix"].kind == inspect.Parameter.KEYWORD_ONLY
    # デフォルト値あり（後方互換）
    assert sig.parameters["key_prefix"].default == "nn_dl"


def test_render_in_streamlit_accepts_key_prefix():
    """nursing_necessity_disease_manual.render_in_streamlit が key_prefix を受け取る."""
    from nursing_necessity_disease_manual import render_in_streamlit
    sig = inspect.signature(render_in_streamlit)
    assert "key_prefix" in sig.parameters
    assert sig.parameters["key_prefix"].kind == inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["key_prefix"].default == "nn_disease_manual"


def test_lecture_uses_key_prefix_for_download_button():
    """lecture モジュールが download_button の key で key_prefix を使っている."""
    src = _load_module("lecture", "scripts/nursing_necessity_lecture.py")
    # ハードコーディングされた "nn_dl_" key が残っていない
    # （key_prefix 経由でなければならない）
    assert 'key=f"nn_dl_{' not in src, (
        "ハードコーディングの 'nn_dl_' key が残っている。"
        "key_prefix 経由に修正してください。"
    )
    # key_prefix を使ったキー生成パターンが存在
    assert re.search(r'key=f"\{key_prefix\}_', src) is not None


def test_disease_manual_uses_key_prefix_for_widgets():
    """疾患マニュアルが全 widget で key_prefix を使っている."""
    src = _load_module("dm", "scripts/nursing_necessity_disease_manual.py")
    # ハードコーディングされた key が残っていない
    forbidden_keys = [
        '"nn_disease_manual_group_filter"',
        '"nn_disease_manual_query"',
        '"nn_disease_manual_selected_disease"',
        '"nn_disease_manual_docx"',
    ]
    for k in forbidden_keys:
        assert f"key={k}" not in src, (
            f"ハードコーディングの key={k} が残っている。"
            "key_prefix 経由に修正してください。"
        )
    # f-string で key_prefix を参照
    assert re.search(r'key=f"\{key_prefix\}_', src) is not None


def test_app_passes_distinct_key_prefixes():
    """bed_control_simulator_app.py がダイアログとタブで別の key_prefix を渡している."""
    src = _load_module("app", "scripts/bed_control_simulator_app.py")
    # render_references の呼び出しは少なくとも 2 箇所
    ref_calls = re.findall(
        r'_nn_render_references\([^)]*key_prefix\s*=\s*"([^"]+)"',
        src,
    )
    assert len(ref_calls) >= 2, "render_references の呼び出しが 2 箇所未満"
    # 異なる prefix が使われている（衝突しない）
    assert len(set(ref_calls)) == len(ref_calls), (
        f"render_references の key_prefix が重複している: {ref_calls}"
    )

    # render_disease_manual も同様
    dm_calls = re.findall(
        r'_nn_render_disease_manual\([^)]*key_prefix\s*=\s*"([^"]+)"',
        src,
    )
    # 注: ダイアログ 2 個（lecture_dlg 内 + 単独 dlg）+ タブ 1 個 = 計 3 個
    assert len(dm_calls) >= 2, "render_disease_manual の key_prefix 付き呼び出しが 2 箇所未満"
    assert len(set(dm_calls)) == len(dm_calls), (
        f"render_disease_manual の key_prefix が重複している: {dm_calls}"
    )
