"""共通 UI コンポーネント — KPI カード、アラート、セクションヘッダー等.

役割:
- design_tokens.py / theme_css.py と一体で、ベッドコントロールアプリの視覚言語を提供する
- 各 view から統一された見た目で KPI / アラート / 見出しを描画できる汎用ヘルパー

利用法:
    from ui_components import section_title, kpi_card, alert

    section_title("今日の運営", icon="")
    kpi_card(label="稼働率", value="92.3", unit="%", severity="success")
    alert("LOS が上限に接近", severity="warning")

注意:
- 既存コードからの呼び出しは強制しない（段階的移行）
- 出力は全て <div class="bc-*"> で theme_css.py のスタイルに依存する
- streamlit.markdown(unsafe_allow_html=True) を内部で使う
"""

from __future__ import annotations

from typing import Literal, Mapping, Optional

import streamlit as st

Severity = Literal["neutral", "success", "warning", "danger", "info"]
AlertSeverity = Literal["info", "warning", "danger", "success"]
KpiSize = Literal["sm", "md", "lg"]  # md が既定、lg は Hero 用の拡大表示


def _build_testid_html(
    testid: Optional[str],
    testid_attrs: Optional[Mapping[str, str]],
    inner: str,
) -> str:
    """data-testid 付き hidden div を組み立てる（E2E テスト用）."""
    if not testid:
        return ""
    attrs = ""
    if testid_attrs:
        for k, v in testid_attrs.items():
            # キーは data-* 属性として扱う
            attrs += f' data-{k}="{v}"'
    return (
        f'<div data-testid="{testid}"{attrs} '
        f'style="display:none">{inner}</div>'
    )


def section_title(title: str, icon: str = "") -> None:
    """標準化されたセクション見出しを描画する.

    Args:
        title: 見出しテキスト。
        icon: 絵文字 / アイコン文字。空文字なら非表示。
    """
    icon_html = (
        f'<span class="bc-section-icon">{icon}</span>' if icon else ""
    )
    st.markdown(
        f'<div class="bc-section-title">{icon_html}{title}</div>',
        unsafe_allow_html=True,
    )


def kpi_card(
    label: str,
    value: str,
    unit: str = "",
    delta: Optional[str] = None,
    severity: Severity = "neutral",
    size: KpiSize = "md",
    testid: Optional[str] = None,
    testid_attrs: Optional[Mapping[str, str]] = None,
    testid_text: Optional[str] = None,
) -> None:
    """標準化された KPI カードを描画する.

    Args:
        label: 項目名（上段の小さいラベル）。
        value: 主表示の数値（文字列で渡す — フォーマット済み想定）。
        unit: 単位（%, 日, 床 など）。空文字可。
        delta: 前期比・差分の補足。None なら非表示。
        severity: 数値の色調。"neutral"（既定）/"success"/"warning"/"danger"/"info"。
        size: カードサイズ。"md"（既定） / "sm"（コンパクト） / "lg"（Hero 用拡大）。
        testid: 指定すると `data-testid="<値>"` の hidden div を同時に出力する（E2E 用）。
        testid_attrs: hidden div に付与する追加の data-* 属性（キーは data- を除いた名前）。
        testid_text: hidden div の innerText を明示指定する（既定は value と同じ）。
            既存 E2E テストとの互換のため、カード表示値と異なる数値を持たせたいときに使う。
    """
    sev_class = f"is-{severity}" if severity != "neutral" else ""
    size_class = f" is-{size}" if size != "md" else ""
    unit_html = f'<span class="bc-kpi-unit">{unit}</span>' if unit else ""
    delta_html = f'<div class="bc-kpi-delta">{delta}</div>' if delta else ""
    testid_html = _build_testid_html(
        testid, testid_attrs, testid_text if testid_text is not None else value
    )
    st.markdown(
        f"""
        <div class="bc-kpi-card{size_class}">
          <div class="bc-kpi-label">{label}</div>
          <div class="bc-kpi-value {sev_class}">{value}{unit_html}</div>
          {delta_html}
          {testid_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def alert(
    message: str,
    severity: AlertSeverity = "info",
) -> None:
    """標準化されたアラート（情報 / 警告 / 危険 / 達成）を描画する.

    Args:
        message: 表示するテキスト（HTML 可）。
        severity: "info"（既定）/"warning"/"danger"/"success"。
    """
    st.markdown(
        f'<div class="bc-alert is-{severity}">{message}</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# 文字列だけ欲しいとき用（テスト / 複合レイアウトでの埋め込み用）
# ---------------------------------------------------------------------------
def section_title_html(title: str, icon: str = "") -> str:
    """section_title と同じ HTML を文字列で返す（st.markdown を呼ばない）."""
    icon_html = (
        f'<span class="bc-section-icon">{icon}</span>' if icon else ""
    )
    return f'<div class="bc-section-title">{icon_html}{title}</div>'


def kpi_card_html(
    label: str,
    value: str,
    unit: str = "",
    delta: Optional[str] = None,
    severity: Severity = "neutral",
    size: KpiSize = "md",
    testid: Optional[str] = None,
    testid_attrs: Optional[Mapping[str, str]] = None,
    testid_text: Optional[str] = None,
) -> str:
    """kpi_card と同じ HTML を文字列で返す."""
    sev_class = f"is-{severity}" if severity != "neutral" else ""
    size_class = f" is-{size}" if size != "md" else ""
    unit_html = f'<span class="bc-kpi-unit">{unit}</span>' if unit else ""
    delta_html = f'<div class="bc-kpi-delta">{delta}</div>' if delta else ""
    testid_html = _build_testid_html(
        testid, testid_attrs, testid_text if testid_text is not None else value
    )
    return (
        f'<div class="bc-kpi-card{size_class}">'
        f'<div class="bc-kpi-label">{label}</div>'
        f'<div class="bc-kpi-value {sev_class}">{value}{unit_html}</div>'
        f"{delta_html}"
        f"{testid_html}"
        "</div>"
    )


def alert_html(message: str, severity: AlertSeverity = "info") -> str:
    """alert と同じ HTML を文字列で返す."""
    return f'<div class="bc-alert is-{severity}">{message}</div>'
