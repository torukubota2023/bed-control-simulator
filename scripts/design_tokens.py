"""デザイントークン — ベッドコントロールアプリの視覚言語定義.

副院長決定: ニュートラル・グレースケール中心のパレット
- 医療専門職が毎日使うツール
- 静謐で情報を読み取りやすい仕上がり
- 数値を目立たせ、装飾を抑える

単一ソース原則: 色・タイポ・余白・角丸・シャドウの定数はすべてここに集約する。
UI 側で直接 HEX や px を書き散らさず、このモジュールからインポートする。
"""

from typing import Final

# ---------------------------------------------------------------------------
# Color Tokens
# ---------------------------------------------------------------------------
# Base: ニュートラル・グレースケール中心
COLOR_BG: Final[str] = "#FAFAFA"            # 画面全体の背景
COLOR_SURFACE: Final[str] = "#FFFFFF"       # カード・パネル背景
COLOR_BORDER: Final[str] = "#E5E7EB"        # 区切り線・境界
COLOR_TEXT_PRIMARY: Final[str] = "#1F2937"  # メインテキスト
COLOR_TEXT_SECONDARY: Final[str] = "#6B7280"  # サブテキスト
COLOR_TEXT_MUTED: Final[str] = "#9CA3AF"    # キャプション・補足

# Accent — 数値・状態表示用。控えめ
COLOR_ACCENT: Final[str] = "#374151"        # プライマリアクセント（ダークグレー）
COLOR_SUCCESS: Final[str] = "#10B981"       # 達成
COLOR_WARNING: Final[str] = "#F59E0B"       # 注意
COLOR_DANGER: Final[str] = "#DC2626"        # 未達・警告
COLOR_INFO: Final[str] = "#2563EB"          # 情報（限定利用）

# アラート背景色（淡色）— ベースは白に近いグレーに色味をほんの少し乗せる
COLOR_ALERT_BG_WARNING: Final[str] = "#FFFBEB"
COLOR_ALERT_BG_DANGER: Final[str] = "#FEF2F2"
COLOR_ALERT_BG_SUCCESS: Final[str] = "#F0FDF4"
COLOR_ALERT_BG_INFO: Final[str] = "#EFF6FF"

# ---------------------------------------------------------------------------
# Typography Tokens
# ---------------------------------------------------------------------------
FONT_SIZE_H1: Final[str] = "28px"
FONT_SIZE_H2: Final[str] = "22px"
FONT_SIZE_H3: Final[str] = "18px"
FONT_SIZE_H4: Final[str] = "16px"
FONT_SIZE_BODY: Final[str] = "14px"
FONT_SIZE_CAPTION: Final[str] = "12px"
FONT_SIZE_MICRO: Final[str] = "10px"

FONT_WEIGHT_REGULAR: Final[int] = 400
FONT_WEIGHT_MEDIUM: Final[int] = 500
FONT_WEIGHT_SEMIBOLD: Final[int] = 600
FONT_WEIGHT_BOLD: Final[int] = 700

LINE_HEIGHT_TIGHT: Final[float] = 1.2
LINE_HEIGHT_NORMAL: Final[float] = 1.5
LINE_HEIGHT_RELAXED: Final[float] = 1.75

# 日本語対応フォントスタック
FONT_FAMILY_SANS: Final[str] = (
    "'Hiragino Sans', 'Yu Gothic', 'Meiryo', "
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
)

# ---------------------------------------------------------------------------
# Spacing Tokens
# ---------------------------------------------------------------------------
SPACE_1: Final[str] = "4px"
SPACE_2: Final[str] = "8px"
SPACE_3: Final[str] = "12px"
SPACE_4: Final[str] = "16px"
SPACE_5: Final[str] = "24px"
SPACE_6: Final[str] = "32px"

# ---------------------------------------------------------------------------
# Radius Tokens
# ---------------------------------------------------------------------------
RADIUS_SM: Final[str] = "4px"
RADIUS_MD: Final[str] = "8px"
RADIUS_LG: Final[str] = "12px"
RADIUS_FULL: Final[str] = "9999px"  # pill

# ---------------------------------------------------------------------------
# Shadow Tokens
# ---------------------------------------------------------------------------
SHADOW_SM: Final[str] = "0 1px 2px rgba(0,0,0,0.04)"
SHADOW_MD: Final[str] = "0 2px 6px rgba(0,0,0,0.06)"
SHADOW_LG: Final[str] = "0 4px 12px rgba(0,0,0,0.08)"

# ---------------------------------------------------------------------------
# Component specific
# ---------------------------------------------------------------------------
KPI_CARD_PADDING: Final[str] = SPACE_4
KPI_VALUE_FONT_SIZE: Final[str] = "24px"
KPI_LABEL_FONT_SIZE: Final[str] = FONT_SIZE_CAPTION
KPI_UNIT_FONT_SIZE: Final[str] = FONT_SIZE_CAPTION
KPI_DELTA_FONT_SIZE: Final[str] = FONT_SIZE_CAPTION

ALERT_BORDER_WIDTH: Final[str] = "3px"

# ---------------------------------------------------------------------------
# Severity キーと色のマッピング（UI ヘルパーから参照）
# ---------------------------------------------------------------------------
SEVERITY_COLORS: Final[dict[str, str]] = {
    "neutral": COLOR_ACCENT,
    "success": COLOR_SUCCESS,
    "warning": COLOR_WARNING,
    "danger": COLOR_DANGER,
    "info": COLOR_INFO,
}

SEVERITY_BG_COLORS: Final[dict[str, str]] = {
    "neutral": COLOR_SURFACE,
    "success": COLOR_ALERT_BG_SUCCESS,
    "warning": COLOR_ALERT_BG_WARNING,
    "danger": COLOR_ALERT_BG_DANGER,
    "info": COLOR_ALERT_BG_INFO,
}
