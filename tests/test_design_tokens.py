"""design_tokens.py の整合性テスト.

検証項目:
- 色トークンが HEX 形式 (#RRGGBB or #RRGGBBAA) であること
- サイズトークン（font-size / space / radius）に px 等の単位が付いていること
- タイポグラフィの数値（font-weight / line-height）が妥当な範囲にあること
- severity マッピングがすべて整合していること
"""

import re
import sys
from pathlib import Path

import pytest

# scripts/ を import path に追加
_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))

import design_tokens as dt  # noqa: E402

# ---------------------------------------------------------------------------
# 正規表現パターン
# ---------------------------------------------------------------------------
HEX_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")
PX_PATTERN = re.compile(r"^\d+(\.\d+)?px$")


# ---------------------------------------------------------------------------
# 色トークン
# ---------------------------------------------------------------------------
COLOR_TOKENS = [
    "COLOR_BG",
    "COLOR_SURFACE",
    "COLOR_BORDER",
    "COLOR_TEXT_PRIMARY",
    "COLOR_TEXT_SECONDARY",
    "COLOR_TEXT_MUTED",
    "COLOR_ACCENT",
    "COLOR_SUCCESS",
    "COLOR_WARNING",
    "COLOR_DANGER",
    "COLOR_INFO",
    "COLOR_ALERT_BG_WARNING",
    "COLOR_ALERT_BG_DANGER",
    "COLOR_ALERT_BG_SUCCESS",
    "COLOR_ALERT_BG_INFO",
]


@pytest.mark.parametrize("name", COLOR_TOKENS)
def test_color_token_is_hex(name: str) -> None:
    """全ての COLOR_* は #RRGGBB 形式であること."""
    value = getattr(dt, name)
    assert isinstance(value, str), f"{name} must be str, got {type(value)}"
    assert HEX_PATTERN.match(value), (
        f"{name}={value!r} is not a valid HEX color (#RRGGBB)"
    )


# ---------------------------------------------------------------------------
# タイポグラフィ — サイズ
# ---------------------------------------------------------------------------
FONT_SIZE_TOKENS = [
    "FONT_SIZE_H1",
    "FONT_SIZE_H2",
    "FONT_SIZE_H3",
    "FONT_SIZE_H4",
    "FONT_SIZE_BODY",
    "FONT_SIZE_CAPTION",
    "FONT_SIZE_MICRO",
    "KPI_VALUE_FONT_SIZE",
    "KPI_LABEL_FONT_SIZE",
    "KPI_UNIT_FONT_SIZE",
    "KPI_DELTA_FONT_SIZE",
]


@pytest.mark.parametrize("name", FONT_SIZE_TOKENS)
def test_font_size_has_px_unit(name: str) -> None:
    """全ての FONT_SIZE_* / KPI_*_FONT_SIZE は px 単位の文字列であること."""
    value = getattr(dt, name)
    assert isinstance(value, str), f"{name} must be str"
    assert PX_PATTERN.match(value), f"{name}={value!r} must end with 'px'"


def test_font_size_hierarchy() -> None:
    """H1 > H2 > H3 > H4 > BODY > CAPTION > MICRO の順に小さくなること."""
    order = [
        int(dt.FONT_SIZE_H1.replace("px", "")),
        int(dt.FONT_SIZE_H2.replace("px", "")),
        int(dt.FONT_SIZE_H3.replace("px", "")),
        int(dt.FONT_SIZE_H4.replace("px", "")),
        int(dt.FONT_SIZE_BODY.replace("px", "")),
        int(dt.FONT_SIZE_CAPTION.replace("px", "")),
        int(dt.FONT_SIZE_MICRO.replace("px", "")),
    ]
    assert order == sorted(order, reverse=True), (
        f"Font size hierarchy broken: {order}"
    )


# ---------------------------------------------------------------------------
# タイポグラフィ — ウエイト / 行間
# ---------------------------------------------------------------------------
def test_font_weights_in_range() -> None:
    """font-weight は 100-900 の範囲."""
    for name in (
        "FONT_WEIGHT_REGULAR",
        "FONT_WEIGHT_MEDIUM",
        "FONT_WEIGHT_SEMIBOLD",
        "FONT_WEIGHT_BOLD",
    ):
        value = getattr(dt, name)
        assert isinstance(value, int), f"{name} must be int"
        assert 100 <= value <= 900, f"{name}={value} out of range 100-900"


def test_font_weight_ordering() -> None:
    """Regular < Medium < Semibold < Bold."""
    assert (
        dt.FONT_WEIGHT_REGULAR
        < dt.FONT_WEIGHT_MEDIUM
        < dt.FONT_WEIGHT_SEMIBOLD
        < dt.FONT_WEIGHT_BOLD
    )


def test_line_heights_in_range() -> None:
    """line-height は 1.0 - 2.5 の妥当な範囲."""
    for name in ("LINE_HEIGHT_TIGHT", "LINE_HEIGHT_NORMAL", "LINE_HEIGHT_RELAXED"):
        value = getattr(dt, name)
        assert isinstance(value, float), f"{name} must be float"
        assert 1.0 <= value <= 2.5, f"{name}={value} out of range"
    assert dt.LINE_HEIGHT_TIGHT < dt.LINE_HEIGHT_NORMAL < dt.LINE_HEIGHT_RELAXED


def test_font_family_sans_contains_japanese_fallback() -> None:
    """日本語フォントがフォントスタックに含まれること."""
    assert "Hiragino" in dt.FONT_FAMILY_SANS or "Yu Gothic" in dt.FONT_FAMILY_SANS


# ---------------------------------------------------------------------------
# 余白 / 角丸 / シャドウ
# ---------------------------------------------------------------------------
SPACE_TOKENS = ["SPACE_1", "SPACE_2", "SPACE_3", "SPACE_4", "SPACE_5", "SPACE_6"]


@pytest.mark.parametrize("name", SPACE_TOKENS)
def test_space_has_px_unit(name: str) -> None:
    """SPACE_* は px 単位."""
    value = getattr(dt, name)
    assert PX_PATTERN.match(value), f"{name}={value!r} must end with 'px'"


def test_space_ordering() -> None:
    """SPACE_1 < SPACE_2 < … < SPACE_6."""
    values = [int(getattr(dt, n).replace("px", "")) for n in SPACE_TOKENS]
    assert values == sorted(values), f"SPACE_* ordering broken: {values}"


def test_radius_tokens() -> None:
    """RADIUS_* の値が定義されていること. FULL は pill 相当の大きい値."""
    for name in ("RADIUS_SM", "RADIUS_MD", "RADIUS_LG"):
        value = getattr(dt, name)
        assert PX_PATTERN.match(value), f"{name}={value!r} must end with 'px'"
    assert dt.RADIUS_FULL.endswith("px")
    assert int(dt.RADIUS_FULL.replace("px", "")) >= 9999


def test_shadow_tokens_are_css_strings() -> None:
    """SHADOW_* は CSS の box-shadow 文字列."""
    for name in ("SHADOW_SM", "SHADOW_MD", "SHADOW_LG"):
        value = getattr(dt, name)
        assert isinstance(value, str)
        # box-shadow は px と rgba を必ず含む（このプロジェクトの約束）
        assert "px" in value and "rgba" in value, (
            f"{name}={value!r} is not a valid box-shadow value"
        )


# ---------------------------------------------------------------------------
# Severity マッピング
# ---------------------------------------------------------------------------
def test_severity_color_mapping_complete() -> None:
    """SEVERITY_COLORS は 5 つのキーを持つ."""
    expected_keys = {"neutral", "success", "warning", "danger", "info"}
    assert set(dt.SEVERITY_COLORS.keys()) == expected_keys
    for key, value in dt.SEVERITY_COLORS.items():
        assert HEX_PATTERN.match(value), (
            f"SEVERITY_COLORS[{key!r}]={value!r} is not a valid HEX color"
        )


def test_severity_bg_mapping_complete() -> None:
    """SEVERITY_BG_COLORS も同じキーを持つ."""
    expected_keys = {"neutral", "success", "warning", "danger", "info"}
    assert set(dt.SEVERITY_BG_COLORS.keys()) == expected_keys


def test_severity_colors_reference_existing_tokens() -> None:
    """SEVERITY_COLORS の値は COLOR_* の実値と一致すること (単一ソース)."""
    assert dt.SEVERITY_COLORS["success"] == dt.COLOR_SUCCESS
    assert dt.SEVERITY_COLORS["warning"] == dt.COLOR_WARNING
    assert dt.SEVERITY_COLORS["danger"] == dt.COLOR_DANGER
    assert dt.SEVERITY_COLORS["info"] == dt.COLOR_INFO
    assert dt.SEVERITY_COLORS["neutral"] == dt.COLOR_ACCENT
