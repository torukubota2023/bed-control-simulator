"""デプロイ関連アセットの存在確認・妥当性テスト."""

import importlib
import sys
from pathlib import Path

import pytest

# プロジェクトルート（tests/ の親ディレクトリ）
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# scripts/ をインポートパスに追加
_scripts_dir = str(PROJECT_ROOT / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)


# ---------- 1. デプロイドキュメントの存在確認 ----------

_DEPLOY_DOCS = [
    "docs/admin/intranet_deployment_plan.md",
    "docs/admin/intranet_browser_compatibility_plan.md",
    "docs/admin/browser_validation_matrix.md",
    "docs/admin/portable_browser_operation_guide.md",
    "docs/admin/lan_setup_guide.md",
]


@pytest.mark.parametrize("rel_path", _DEPLOY_DOCS)
def test_deployment_docs_exist(rel_path: str) -> None:
    path = PROJECT_ROOT / rel_path
    assert path.exists(), f"デプロイドキュメントが見つかりません: {path}"


# ---------- 2. デプロイスクリプトの存在確認 ----------

_DEPLOY_SCRIPTS = [
    "deploy/launch_bed_control.bat",
    "deploy/launch_portable_firefox.bat",
    "deploy/open_bed_control.ps1",
]


@pytest.mark.parametrize("rel_path", _DEPLOY_SCRIPTS)
def test_deploy_scripts_exist(rel_path: str) -> None:
    path = PROJECT_ROOT / rel_path
    assert path.exists(), f"デプロイスクリプトが見つかりません: {path}"


# ---------- 3. ツールの存在確認 ----------

def test_browser_probe_exists() -> None:
    path = PROJECT_ROOT / "tools" / "browser_probe.html"
    assert path.exists(), "tools/browser_probe.html が見つかりません"


# ---------- 4. requirements ファイルの存在確認 ----------

_REQUIREMENTS = [
    "requirements.txt",
    "requirements-edge90.txt",
]


@pytest.mark.parametrize("rel_path", _REQUIREMENTS)
def test_requirements_files_exist(rel_path: str) -> None:
    path = PROJECT_ROOT / rel_path
    assert path.exists(), f"requirements ファイルが見つかりません: {path}"


# ---------- 5. browser_probe.html の妥当性 ----------

def test_browser_probe_is_valid_html() -> None:
    content = (PROJECT_ROOT / "tools" / "browser_probe.html").read_text(encoding="utf-8")
    assert "<!DOCTYPE" in content.upper(), "DOCTYPE 宣言が含まれていません"
    assert "function" in content, "チェック用の function が含まれていません"


# ---------- 6. views モジュールの存在確認 ----------

_VIEWS_FILES = [
    "scripts/views/__init__.py",
    "scripts/views/dashboard_view.py",
    "scripts/views/c_group_view.py",
    "scripts/views/guardrail_view.py",
]


@pytest.mark.parametrize("rel_path", _VIEWS_FILES)
def test_views_modules_exist(rel_path: str) -> None:
    path = PROJECT_ROOT / rel_path
    assert path.exists(), f"views モジュールが見つかりません: {path}"


# ---------- 7. views モジュールのインポート・関数存在確認 ----------

def _import_with_streamlit_mock(module_name: str):
    """streamlit が未インストールでもインポートできるようモックする."""
    import types
    import unittest.mock as mock

    # streamlit のモックを作成（未インストール時のみ）
    if "streamlit" not in sys.modules:
        st_mock = mock.MagicMock(spec=[])
        sys.modules["streamlit"] = st_mock
        # streamlit のサブモジュールもモック
        for sub in ("components", "delta_generator"):
            sys.modules[f"streamlit.{sub}"] = types.ModuleType(f"streamlit.{sub}")

    # キャッシュされたモジュールを再読込しないよう一旦削除
    full_name = module_name
    if full_name in sys.modules:
        del sys.modules[full_name]

    return importlib.import_module(full_name)


def test_dashboard_view_functions() -> None:
    mod = _import_with_streamlit_mock("views.dashboard_view")
    expected = [
        "render_action_card",
        "render_kpi_priority_strip",
        "render_morning_capacity_card",
        "render_tradeoff_card",
    ]
    for fn_name in expected:
        assert hasattr(mod, fn_name), f"dashboard_view に {fn_name} が定義されていません"
        assert callable(getattr(mod, fn_name)), f"dashboard_view.{fn_name} は callable ではありません"


def test_c_group_view_functions() -> None:
    mod = _import_with_streamlit_mock("views.c_group_view")
    expected = [
        "render_c_group_candidates_lite",
    ]
    for fn_name in expected:
        assert hasattr(mod, fn_name), f"c_group_view に {fn_name} が定義されていません"
        assert callable(getattr(mod, fn_name)), f"c_group_view.{fn_name} は callable ではありません"


def test_guardrail_view_functions() -> None:
    mod = _import_with_streamlit_mock("views.guardrail_view")
    expected = [
        "render_guardrail_summary",
        "render_demand_wave_summary",
    ]
    for fn_name in expected:
        assert hasattr(mod, fn_name), f"guardrail_view に {fn_name} が定義されていません"
        assert callable(getattr(mod, fn_name)), f"guardrail_view.{fn_name} は callable ではありません"
