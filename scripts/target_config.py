"""
目標値設定ローダー — ベッドコントロールシミュレーター用

副院長決定の稼働率目標（全病棟 全月 一律 90%）と、地域包括医療病棟の
施設基準（平均在院日数 rolling 3ヶ月 21 日以内、救急搬送後患者割合 15%
以上）を一元管理する。

設定ファイル: `settings/occupancy_target.yaml`

将来、病棟別・月別の上書きを可能にするために `overrides` 構造を用意して
いるが、初期値はすべてデフォルト（90%）を返す。

Streamlit に依存しない。pure function で提供する。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

# ---------------------------------------------------------------------------
# 定数 — モジュール解決パス
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG_PATH: Path = (
    Path(__file__).resolve().parent.parent / "settings" / "occupancy_target.yaml"
)

# フォールバック値（YAML が破損・欠損していた場合のセーフティネット）
_FALLBACK_OCCUPANCY_DEFAULT: float = 90.0
_FALLBACK_ALOS_LIMIT: float = 21.0
_FALLBACK_ALOS_WARNING: float = 19.95
_FALLBACK_EMERGENCY_MIN: float = 15.0
_FALLBACK_TRANSITIONAL_END: date = date(2026, 5, 31)


# ---------------------------------------------------------------------------
# 基本ローダー
# ---------------------------------------------------------------------------

def load_targets(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """YAML を読み込んで dict で返す。

    Args:
        config_path: 設定ファイルパス。None なら既定（settings/occupancy_target.yaml）

    Returns:
        YAML をパースした dict。ファイルが存在しない場合は空 dict。
    """
    path = config_path if config_path is not None else _DEFAULT_CONFIG_PATH
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        return {}
    return data


def _safe_get(d: Any, *keys: str, default: Any = None) -> Any:
    """ネストされた dict から安全に値を取得する。"""
    current = d
    for k in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(k)
        if current is None:
            return default
    return current


# ---------------------------------------------------------------------------
# 稼働率目標
# ---------------------------------------------------------------------------

def get_occupancy_target(
    ward: str,
    month: Optional[date] = None,
    config_path: Optional[Path] = None,
) -> float:
    """指定病棟・月の稼働率目標を返す（%、小数OK）。

    優先順位:
        1. overrides[ward][YYYY-MM] が存在すればその値
        2. なければ default（全病棟 全月 一律 90%）

    Args:
        ward: 病棟名（例: "5F", "6F"）
        month: 対象月。None なら overrides は参照せず default を返す。
        config_path: 設定ファイルパス（テスト用）

    Returns:
        稼働率目標値（%、float）
    """
    targets = load_targets(config_path)
    occ = _safe_get(targets, "occupancy_target", default={})

    default_val = occ.get("default", _FALLBACK_OCCUPANCY_DEFAULT)

    if month is not None:
        overrides = occ.get("overrides") or {}
        ward_overrides = overrides.get(ward) or {}
        month_key = f"{month.year:04d}-{month.month:02d}"
        if month_key in ward_overrides:
            return float(ward_overrides[month_key])

    return float(default_val)


# ---------------------------------------------------------------------------
# 平均在院日数
# ---------------------------------------------------------------------------

def get_alos_regulatory_limit(config_path: Optional[Path] = None) -> float:
    """平均在院日数 制度上限（21 日）。"""
    targets = load_targets(config_path)
    val = _safe_get(
        targets, "alos_target", "regulatory_limit_days",
        default=_FALLBACK_ALOS_LIMIT,
    )
    return float(val)


def get_alos_warning_threshold(config_path: Optional[Path] = None) -> float:
    """平均在院日数 警告閾値（19.95 日 — 95% 到達）。"""
    targets = load_targets(config_path)
    val = _safe_get(
        targets, "alos_target", "warning_threshold_days",
        default=_FALLBACK_ALOS_WARNING,
    )
    return float(val)


def get_alos_rolling_window_months(config_path: Optional[Path] = None) -> int:
    """平均在院日数の rolling 判定窓（月数）。"""
    targets = load_targets(config_path)
    val = _safe_get(
        targets, "alos_target", "rolling_window_months", default=3,
    )
    return int(val)


# ---------------------------------------------------------------------------
# 救急搬送後患者割合
# ---------------------------------------------------------------------------

def get_emergency_ratio_minimum(config_path: Optional[Path] = None) -> float:
    """救急搬送後患者割合 基準最小値（15%）。"""
    targets = load_targets(config_path)
    val = _safe_get(
        targets, "emergency_ratio_target", "regulatory_minimum_pct",
        default=_FALLBACK_EMERGENCY_MIN,
    )
    return float(val)


def get_emergency_rolling_window_months(config_path: Optional[Path] = None) -> int:
    """救急搬送後患者割合の rolling 判定窓（月数）。"""
    targets = load_targets(config_path)
    val = _safe_get(
        targets, "emergency_ratio_target", "rolling_window_months", default=3,
    )
    return int(val)


def is_emergency_ratio_ward_specific(config_path: Optional[Path] = None) -> bool:
    """病棟単体で判定するかどうか（5F, 6F 各病棟単体判定）。"""
    targets = load_targets(config_path)
    val = _safe_get(
        targets, "emergency_ratio_target", "ward_specific", default=True,
    )
    return bool(val)


# ---------------------------------------------------------------------------
# 経過措置
# ---------------------------------------------------------------------------

def _get_transitional_end_date(config_path: Optional[Path] = None) -> date:
    """経過措置終了日を設定から取得（YAML 未設定ならフォールバック）。"""
    targets = load_targets(config_path)
    raw = _safe_get(targets, "alos_target", "transitional_end_date")
    if raw is None:
        return _FALLBACK_TRANSITIONAL_END
    if isinstance(raw, date):
        return raw
    if isinstance(raw, str):
        # "2026-05-31" 形式を想定
        parts = raw.split("-")
        if len(parts) == 3:
            try:
                return date(int(parts[0]), int(parts[1]), int(parts[2]))
            except ValueError:
                return _FALLBACK_TRANSITIONAL_END
    return _FALLBACK_TRANSITIONAL_END


def is_transitional_period(
    today: date,
    config_path: Optional[Path] = None,
) -> bool:
    """2026-05-31 以前かどうか（経過措置期間中）。

    Args:
        today: 判定基準日
        config_path: 設定ファイルパス（テスト用）

    Returns:
        True: 経過措置期間中（6/1 本則適用前）
        False: 経過措置終了後（本則完全適用）
    """
    end = _get_transitional_end_date(config_path)
    return today <= end


# ---------------------------------------------------------------------------
# 病床情報
# ---------------------------------------------------------------------------

def get_total_beds(config_path: Optional[Path] = None) -> int:
    """総病床数（CLAUDE.md: 94 床）。"""
    targets = load_targets(config_path)
    val = _safe_get(targets, "beds", "total", default=94)
    return int(val)


def get_ward_bed_count(ward: str, config_path: Optional[Path] = None) -> Optional[int]:
    """病棟別病床数。未設定なら None を返す（実運用入力待ち）。"""
    targets = load_targets(config_path)
    val = _safe_get(targets, "beds", ward, "count")
    if val is None:
        return None
    return int(val)


def get_ward_specialty(ward: str, config_path: Optional[Path] = None) -> Optional[str]:
    """病棟別診療科ラベル。"""
    targets = load_targets(config_path)
    val = _safe_get(targets, "beds", ward, "specialty")
    if val is None:
        return None
    return str(val)
