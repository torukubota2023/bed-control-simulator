"""ui_components.py のテスト.

Streamlit のランタイムを起動しないよう、*_html() ヘルパーを中心に検証する。
streamlit.markdown を経由する関数（section_title / kpi_card / alert）は
monkeypatch で st.markdown を差し替えて呼び出されることだけ確認する。

検証項目:
- ヘルパーが例外なく HTML を返す
- severity クラスが正しく付与される
- theme_css.py の出力に必要な <style> が含まれる
"""

import sys
from pathlib import Path

import pytest

# scripts/ を import path に追加
_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))

import ui_components as uc  # noqa: E402
from theme_css import render_theme_css  # noqa: E402


# ---------------------------------------------------------------------------
# *_html() ヘルパー — 純粋関数
# ---------------------------------------------------------------------------
class TestSectionTitleHtml:
    def test_basic_title(self) -> None:
        html = uc.section_title_html("今日の運営")
        assert "bc-section-title" in html
        assert "今日の運営" in html

    def test_with_icon(self) -> None:
        html = uc.section_title_html("退院調整", icon="📋")
        assert "📋" in html
        assert "bc-section-icon" in html

    def test_empty_icon_omits_span(self) -> None:
        html = uc.section_title_html("データ・設定", icon="")
        assert "bc-section-icon" not in html


class TestKpiCardHtml:
    def test_minimal(self) -> None:
        html = uc.kpi_card_html("稼働率", "92.3")
        assert "bc-kpi-card" in html
        assert "bc-kpi-label" in html
        assert "bc-kpi-value" in html
        assert "稼働率" in html
        assert "92.3" in html

    def test_with_unit(self) -> None:
        html = uc.kpi_card_html("稼働率", "92.3", unit="%")
        assert "bc-kpi-unit" in html
        assert "%" in html

    def test_without_unit_omits_unit_span(self) -> None:
        html = uc.kpi_card_html("件数", "42")
        assert "bc-kpi-unit" not in html

    def test_with_delta(self) -> None:
        html = uc.kpi_card_html("稼働率", "92.3", unit="%", delta="+1.2pt")
        assert "bc-kpi-delta" in html
        assert "+1.2pt" in html

    def test_without_delta_omits_delta_div(self) -> None:
        html = uc.kpi_card_html("稼働率", "92.3", unit="%")
        assert "bc-kpi-delta" not in html

    @pytest.mark.parametrize(
        "severity,expected_class",
        [
            ("neutral", ""),
            ("success", "is-success"),
            ("warning", "is-warning"),
            ("danger", "is-danger"),
            ("info", "is-info"),
        ],
    )
    def test_severity_class(self, severity: str, expected_class: str) -> None:
        html = uc.kpi_card_html("label", "1", severity=severity)  # type: ignore[arg-type]
        if expected_class:
            assert expected_class in html
        else:
            # neutral は severity クラス無し
            assert "is-success" not in html
            assert "is-danger" not in html

    @pytest.mark.parametrize(
        "size,expected_class",
        [
            ("md", ""),
            ("sm", "is-sm"),
            ("lg", "is-lg"),
        ],
    )
    def test_size_class(self, size: str, expected_class: str) -> None:
        html = uc.kpi_card_html("label", "1", size=size)  # type: ignore[arg-type]
        if expected_class:
            assert expected_class in html
        else:
            assert "is-sm" not in html
            assert "is-lg" not in html

    def test_testid_basic(self) -> None:
        html = uc.kpi_card_html("C群", "31", "名", testid="phase")
        assert 'data-testid="phase"' in html
        # デフォルトでは hidden div の中身は value と同じ
        assert ">31</div>" in html
        assert 'display:none' in html

    def test_testid_attrs(self) -> None:
        html = uc.kpi_card_html(
            "C群", "31", "名",
            testid="phase",
            testid_attrs={"a": "14", "b": "36", "c": "31"},
        )
        assert 'data-a="14"' in html
        assert 'data-b="36"' in html
        assert 'data-c="31"' in html

    def test_testid_text_override(self) -> None:
        # カード表示は C 群の数（31）、hidden div のテキストは合計（81）にできる
        html = uc.kpi_card_html(
            "C群", "31", "名",
            testid="phase",
            testid_attrs={"a": "14", "b": "36", "c": "31"},
            testid_text="81",
        )
        assert '>81</div>' in html
        # カードの value 表示（31）も残っている
        assert '>31<span class="bc-kpi-unit">' in html

    def test_no_testid_no_hidden_div(self) -> None:
        html = uc.kpi_card_html("稼働率", "92.3", "%")
        assert 'data-testid=' not in html
        assert 'display:none' not in html


class TestAlertHtml:
    @pytest.mark.parametrize(
        "severity", ["info", "warning", "danger", "success"]
    )
    def test_severity_class(self, severity: str) -> None:
        html = uc.alert_html("テストメッセージ", severity=severity)  # type: ignore[arg-type]
        assert f"is-{severity}" in html
        assert "bc-alert" in html
        assert "テストメッセージ" in html

    def test_default_is_info(self) -> None:
        html = uc.alert_html("m")
        assert "is-info" in html


class TestActionFocusCardHtml:
    def test_basic_action_focus_card(self) -> None:
        html = uc.action_focus_card_html(
            "6Fは必要度IIの不足患者日を埋める",
            "C23または内科A5日を月20件ペースで確認する",
            severity="danger",
            chips=[("月不足", "99.4患者日"), ("ペース", "約1.5日に1件")],
            note="適応のある医療・ケアの記録漏れ防止のみ",
            testid="section-action-focus",
        )
        assert "bc-action-focus" in html
        assert "is-danger" in html
        assert "今日あと何をすればいいか" in html
        assert "6Fは必要度II" in html
        assert "99.4患者日" in html
        assert 'data-testid="section-action-focus"' in html

    def test_action_focus_card_escapes_html(self) -> None:
        html = uc.action_focus_card_html(
            "<script>",
            "A < B",
            chips=[("x", "<b>")],
        )
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "A &lt; B" in html
        assert "&lt;b&gt;" in html


# ---------------------------------------------------------------------------
# Streamlit を呼ぶ関数 — monkeypatch で副作用のみ確認
# ---------------------------------------------------------------------------
class TestStreamlitWrappers:
    def test_section_title_calls_markdown(self, monkeypatch) -> None:
        calls: list[tuple[str, dict]] = []

        def fake_markdown(body, **kwargs):
            calls.append((body, kwargs))

        monkeypatch.setattr(uc.st, "markdown", fake_markdown)
        uc.section_title("見出し", icon="🏥")
        assert len(calls) == 1
        body, kwargs = calls[0]
        assert "bc-section-title" in body
        assert "見出し" in body
        assert kwargs.get("unsafe_allow_html") is True

    def test_kpi_card_calls_markdown(self, monkeypatch) -> None:
        calls: list[tuple[str, dict]] = []
        monkeypatch.setattr(
            uc.st, "markdown", lambda body, **k: calls.append((body, k))
        )
        uc.kpi_card("稼働率", "92.3", unit="%", delta="+1.2pt", severity="success")
        assert len(calls) == 1
        body, kwargs = calls[0]
        assert "bc-kpi-card" in body
        assert "is-success" in body
        assert "+1.2pt" in body
        assert kwargs.get("unsafe_allow_html") is True

    def test_alert_calls_markdown(self, monkeypatch) -> None:
        calls: list[tuple[str, dict]] = []
        monkeypatch.setattr(
            uc.st, "markdown", lambda body, **k: calls.append((body, k))
        )
        uc.alert("LOS が上限に接近", severity="warning")
        assert len(calls) == 1
        body, kwargs = calls[0]
        assert "bc-alert" in body
        assert "is-warning" in body
        assert "LOS が上限に接近" in body
        assert kwargs.get("unsafe_allow_html") is True

    def test_action_focus_card_calls_markdown(self, monkeypatch) -> None:
        calls: list[tuple[str, dict]] = []
        monkeypatch.setattr(
            uc.st, "markdown", lambda body, **k: calls.append((body, k))
        )
        uc.action_focus_card("今日の一手", "退院日を1名確定", severity="warning")
        assert len(calls) == 1
        body, kwargs = calls[0]
        assert "bc-action-focus" in body
        assert "今日の一手" in body
        assert kwargs.get("unsafe_allow_html") is True


# ---------------------------------------------------------------------------
# theme_css.render_theme_css()
# ---------------------------------------------------------------------------
class TestRenderThemeCss:
    def test_returns_style_tag(self) -> None:
        css = render_theme_css()
        assert "<style>" in css
        assert "</style>" in css

    def test_contains_core_classes(self) -> None:
        """共通 UI コンポーネントのクラスに対応する CSS が含まれること."""
        css = render_theme_css()
        for cls in (
            ".bc-section-title",
            ".bc-kpi-card",
            ".bc-kpi-label",
            ".bc-kpi-value",
            ".bc-alert",
            ".bc-action-focus",
            ".bc-admin-kpi-strip",
        ):
            assert cls in css, f"{cls} missing from theme CSS"

    def test_contains_severity_variants(self) -> None:
        """severity バリエーションが展開されていること."""
        css = render_theme_css()
        for variant in ("is-success", "is-warning", "is-danger", "is-info"):
            assert variant in css, f"{variant} missing from theme CSS"

    def test_contains_streamlit_native_targets(self) -> None:
        """Streamlit ネイティブ要素の微調整が含まれること."""
        css = render_theme_css()
        assert 'data-testid="stMetricValue"' in css
        assert 'data-testid="stSidebar"' in css
        assert ".stTabs" in css

    def test_is_string(self) -> None:
        assert isinstance(render_theme_css(), str)
