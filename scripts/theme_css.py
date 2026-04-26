"""共通 CSS — render_theme_css() で各アプリの冒頭に注入.

役割:
- design_tokens.py の値を CSS に焼き込み、全画面に統一感のある視覚言語を敷く
- Streamlit ネイティブ要素（st.metric / タブ / サイドバー等）の微調整
- UI ヘルパー（ui_components.py）が出力するクラス（.bc-*）のスタイル定義

利用法:
    from theme_css import render_theme_css
    st.markdown(render_theme_css(), unsafe_allow_html=True)

注意:
- このファイルは「デフォルトスタイル」を提供する。既存の個別 CSS（conference_material_view 等）
  は後から注入されるため、そちらで上書きできる（段階的移行）。
- data-testid のついた要素には触れない（E2E テストを壊さない）。
"""

from design_tokens import (
    ALERT_BORDER_WIDTH,
    COLOR_ACCENT,
    COLOR_ALERT_BG_DANGER,
    COLOR_ALERT_BG_INFO,
    COLOR_ALERT_BG_SUCCESS,
    COLOR_ALERT_BG_WARNING,
    COLOR_BG,
    COLOR_BORDER,
    COLOR_DANGER,
    COLOR_INFO,
    COLOR_SUCCESS,
    COLOR_SURFACE,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    COLOR_WARNING,
    FONT_FAMILY_SANS,
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
    FONT_SIZE_H1,
    FONT_SIZE_H2,
    FONT_SIZE_H3,
    FONT_WEIGHT_BOLD,
    FONT_WEIGHT_MEDIUM,
    FONT_WEIGHT_SEMIBOLD,
    KPI_CARD_PADDING,
    KPI_DELTA_FONT_SIZE,
    KPI_LABEL_FONT_SIZE,
    KPI_UNIT_FONT_SIZE,
    KPI_VALUE_FONT_SIZE,
    LINE_HEIGHT_TIGHT,
    RADIUS_MD,
    SHADOW_SM,
    SPACE_1,
    SPACE_2,
    SPACE_3,
    SPACE_4,
    SPACE_5,
)


def render_theme_css() -> str:
    """Return <style> tag as HTML string for st.markdown(unsafe_allow_html=True).

    Returns:
        完成した <style>…</style> の文字列。st.markdown() にそのまま渡す。
    """
    return f"""
    <style>
    /* ================================================================
       ベッドコントロールアプリ共通スタイル（デザイントークン由来）
       ================================================================ */

    /* --- 基本タイポグラフィ --- */
    html, body, [class*="css"] {{
      font-family: {FONT_FAMILY_SANS};
      color: {COLOR_TEXT_PRIMARY};
    }}

    /* 背景色を config.toml と同期させ、Streamlit の古いキャッシュから来る白背景を抑制 */
    .stApp {{
      background-color: {COLOR_BG};
    }}

    /* --- 見出しの折り返し抑制 ---
       サイドバー表示などで本文幅が狭い場合も、見出しが2行に割れて視線が散らないようにする。 */
    div[data-testid="stHeading"] h1,
    div[data-testid="stHeading"] h2,
    div[data-testid="stHeading"] h3,
    div[data-testid="stMarkdownContainer"] h1,
    div[data-testid="stMarkdownContainer"] h2,
    div[data-testid="stMarkdownContainer"] h3,
    div[data-testid="stMarkdownContainer"] h4,
    .bc-app-title,
    .bc-section-title {{
      white-space: nowrap !important;
      word-break: keep-all !important;
      overflow-wrap: normal !important;
      max-width: 100% !important;
      overflow: hidden !important;
      text-overflow: ellipsis !important;
      letter-spacing: 0 !important;
    }}

    div[data-testid="stHeading"] h1,
    div[data-testid="stMarkdownContainer"] h1:not(.bc-app-title) {{
      font-size: clamp(1.55rem, 2.6vw, {FONT_SIZE_H1}) !important;
      line-height: 1.12 !important;
    }}
    div[data-testid="stHeading"] h2,
    div[data-testid="stMarkdownContainer"] h2 {{
      font-size: clamp(1.25rem, 2vw, {FONT_SIZE_H2}) !important;
      line-height: 1.18 !important;
    }}
    div[data-testid="stHeading"] h3,
    div[data-testid="stMarkdownContainer"] h3 {{
      font-size: clamp(1.05rem, 1.55vw, {FONT_SIZE_H3}) !important;
      line-height: 1.22 !important;
    }}
    div[data-testid="stMarkdownContainer"] h4,
    .bc-section-title {{
      font-size: clamp(1rem, 1.35vw, {FONT_SIZE_H3}) !important;
      line-height: 1.25 !important;
    }}

    @media (max-width: 700px) {{
      div[data-testid="stHeading"] h1,
      div[data-testid="stMarkdownContainer"] h1:not(.bc-app-title) {{
        font-size: clamp(1.15rem, 5vw, 1.5rem) !important;
      }}
      div[data-testid="stHeading"] h2,
      div[data-testid="stMarkdownContainer"] h2 {{
        font-size: clamp(1rem, 4.2vw, 1.25rem) !important;
      }}
      div[data-testid="stHeading"] h3,
      div[data-testid="stMarkdownContainer"] h3,
      div[data-testid="stMarkdownContainer"] h4,
      .bc-section-title {{
        font-size: clamp(0.95rem, 3.8vw, 1.05rem) !important;
      }}
    }}

    /* --- セクションヘッダー標準化 --- */
    .bc-section-title {{
      font-weight: {FONT_WEIGHT_SEMIBOLD};
      color: {COLOR_TEXT_PRIMARY};
      margin: {SPACE_5} 0 {SPACE_3} 0;
      padding-bottom: {SPACE_2};
      border-bottom: 1px solid {COLOR_BORDER};
    }}
    .bc-section-title .bc-section-icon {{
      margin-right: {SPACE_2};
      color: {COLOR_TEXT_SECONDARY};
    }}

    /* --- KPI カード標準 --- */
    .bc-kpi-card {{
      background: {COLOR_SURFACE};
      border: 1px solid {COLOR_BORDER};
      border-radius: {RADIUS_MD};
      padding: {KPI_CARD_PADDING};
      box-shadow: {SHADOW_SM};
    }}
    .bc-kpi-label {{
      font-size: {KPI_LABEL_FONT_SIZE};
      color: {COLOR_TEXT_SECONDARY};
      font-weight: {FONT_WEIGHT_MEDIUM};
      letter-spacing: 0.04em;
      text-transform: uppercase;
      margin-bottom: {SPACE_1};
    }}
    .bc-kpi-value {{
      font-size: {KPI_VALUE_FONT_SIZE};
      font-weight: {FONT_WEIGHT_BOLD};
      color: {COLOR_TEXT_PRIMARY};
      line-height: {LINE_HEIGHT_TIGHT};
    }}
    .bc-kpi-value.is-success {{ color: {COLOR_SUCCESS}; }}
    .bc-kpi-value.is-warning {{ color: {COLOR_WARNING}; }}
    .bc-kpi-value.is-danger  {{ color: {COLOR_DANGER};  }}
    .bc-kpi-value.is-info    {{ color: {COLOR_INFO};    }}
    .bc-kpi-unit {{
      font-size: {KPI_UNIT_FONT_SIZE};
      font-weight: {FONT_WEIGHT_MEDIUM};
      color: {COLOR_TEXT_SECONDARY};
      margin-left: {SPACE_1};
    }}
    .bc-kpi-delta {{
      font-size: {KPI_DELTA_FONT_SIZE};
      color: {COLOR_TEXT_MUTED};
      margin-top: {SPACE_1};
    }}
    /* Hero サイズ — 意思決定ダッシュボードの最重要 KPI 用 */
    .bc-kpi-card.is-lg {{
      padding: {SPACE_5} {SPACE_4};
    }}
    .bc-kpi-card.is-lg .bc-kpi-value {{
      font-size: 32px;
      line-height: 1.15;
    }}
    .bc-kpi-card.is-lg .bc-kpi-label {{
      font-size: {FONT_SIZE_BODY};
      margin-bottom: {SPACE_2};
    }}
    /* Compact サイズ — 副次 KPI・補足 */
    .bc-kpi-card.is-sm {{
      padding: {SPACE_3};
    }}
    .bc-kpi-card.is-sm .bc-kpi-value {{
      font-size: 18px;
    }}

    /* --- アラート標準 --- */
    .bc-alert {{
      background: {COLOR_SURFACE};
      border-left: {ALERT_BORDER_WIDTH} solid {COLOR_ACCENT};
      border-radius: 0 {RADIUS_MD} {RADIUS_MD} 0;
      padding: {SPACE_3} {SPACE_4};
      margin: {SPACE_3} 0;
      font-size: {FONT_SIZE_BODY};
      color: {COLOR_TEXT_PRIMARY};
      line-height: 1.5;
    }}
    .bc-alert.is-info    {{ border-left-color: {COLOR_INFO};    background: {COLOR_ALERT_BG_INFO};    }}
    .bc-alert.is-warning {{ border-left-color: {COLOR_WARNING}; background: {COLOR_ALERT_BG_WARNING}; }}
    .bc-alert.is-danger  {{ border-left-color: {COLOR_DANGER};  background: {COLOR_ALERT_BG_DANGER};  }}
    .bc-alert.is-success {{ border-left-color: {COLOR_SUCCESS}; background: {COLOR_ALERT_BG_SUCCESS}; }}

    /* --- 最上段アクションカード --- */
    .bc-action-focus {{
      background: {COLOR_SURFACE};
      border: 1px solid {COLOR_BORDER};
      border-left: 8px solid {COLOR_INFO};
      border-radius: {RADIUS_MD};
      padding: {SPACE_4} {SPACE_5};
      margin: {SPACE_3} 0 {SPACE_4} 0;
      box-shadow: {SHADOW_SM};
    }}
    .bc-action-focus.is-danger {{
      border-left-color: {COLOR_DANGER};
      background: {COLOR_ALERT_BG_DANGER};
    }}
    .bc-action-focus.is-warning {{
      border-left-color: {COLOR_WARNING};
      background: {COLOR_ALERT_BG_WARNING};
    }}
    .bc-action-focus.is-success {{
      border-left-color: {COLOR_SUCCESS};
      background: {COLOR_ALERT_BG_SUCCESS};
    }}
    .bc-action-focus.is-info {{
      border-left-color: {COLOR_INFO};
      background: {COLOR_ALERT_BG_INFO};
    }}
    .bc-action-focus-kicker {{
      color: {COLOR_TEXT_SECONDARY};
      font-size: {FONT_SIZE_CAPTION};
      font-weight: {FONT_WEIGHT_SEMIBOLD};
      margin-bottom: {SPACE_1};
    }}
    .bc-action-focus-title {{
      color: {COLOR_TEXT_PRIMARY};
      font-size: 28px;
      line-height: 1.2;
      font-weight: {FONT_WEIGHT_BOLD};
      letter-spacing: 0;
      margin-bottom: {SPACE_2};
    }}
    .bc-action-focus-action {{
      color: {COLOR_TEXT_PRIMARY};
      font-size: 16px;
      line-height: 1.55;
      font-weight: {FONT_WEIGHT_MEDIUM};
    }}
    .bc-action-focus-chips {{
      display: flex;
      flex-wrap: wrap;
      gap: {SPACE_2};
      margin-top: {SPACE_3};
    }}
    .bc-action-focus-chip {{
      display: inline-flex;
      align-items: baseline;
      gap: {SPACE_1};
      border: 1px solid {COLOR_BORDER};
      border-radius: {RADIUS_MD};
      background: rgba(255, 255, 255, 0.75);
      padding: {SPACE_1} {SPACE_3};
      color: {COLOR_TEXT_PRIMARY};
      white-space: nowrap;
    }}
    .bc-action-focus-chip-label {{
      color: {COLOR_TEXT_SECONDARY};
      font-size: {FONT_SIZE_CAPTION};
    }}
    .bc-action-focus-note {{
      color: {COLOR_TEXT_MUTED};
      font-size: {FONT_SIZE_CAPTION};
      line-height: 1.45;
      margin-top: {SPACE_2};
    }}
    @media (max-width: 700px) {{
      .bc-action-focus-title {{
        font-size: 22px;
      }}
      .bc-action-focus {{
        padding: {SPACE_3} {SPACE_4};
      }}
    }}

    /* ================================================================
       Streamlit ネイティブ要素の微調整（控えめに）
       ================================================================ */

    /* st.metric */
    div[data-testid="stMetricValue"] {{
      font-weight: {FONT_WEIGHT_BOLD};
      color: {COLOR_TEXT_PRIMARY};
    }}
    div[data-testid="stMetricLabel"] {{
      font-size: {FONT_SIZE_CAPTION};
      color: {COLOR_TEXT_SECONDARY};
    }}

    /* タブ */
    .stTabs [data-baseweb="tab-list"] {{
      gap: {SPACE_1};
      border-bottom: 1px solid {COLOR_BORDER};
    }}
    .stTabs [data-baseweb="tab"] {{
      font-size: {FONT_SIZE_BODY};
      font-weight: {FONT_WEIGHT_MEDIUM};
      color: {COLOR_TEXT_SECONDARY};
    }}
    .stTabs [aria-selected="true"] {{
      color: {COLOR_TEXT_PRIMARY};
      font-weight: {FONT_WEIGHT_SEMIBOLD};
    }}

    /* サイドバー */
    section[data-testid="stSidebar"] {{
      background: {COLOR_SURFACE};
      border-right: 1px solid {COLOR_BORDER};
    }}
    </style>
    """
