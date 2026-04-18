"""
目標値設定ローダー（scripts.target_config）のテスト

検証項目:
- デフォルト 90% が返る
- overrides が存在すれば優先される（テスト用 YAML で検証）
- ALOS 制度上限 21、警告 19.95
- 救急搬送 15%
- 経過措置期間判定（2026-04-17 は True、2026-06-01 は False）
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from scripts.target_config import (
    _DEFAULT_CONFIG_PATH,
    get_alos_regulatory_limit,
    get_alos_rolling_window_months,
    get_alos_warning_threshold,
    get_emergency_ratio_minimum,
    get_emergency_rolling_window_months,
    get_occupancy_target,
    get_total_beds,
    get_ward_bed_count,
    get_ward_specialty,
    is_emergency_ratio_ward_specific,
    is_transitional_period,
    load_targets,
)


# ---------------------------------------------------------------------------
# 本番設定ファイルでの基本動作
# ---------------------------------------------------------------------------

class TestDefaultConfig:
    """本番の settings/occupancy_target.yaml を読む場合の挙動。"""

    def test_load_targets_returns_dict(self):
        data = load_targets()
        assert isinstance(data, dict)
        assert "occupancy_target" in data
        assert "alos_target" in data
        assert "emergency_ratio_target" in data

    def test_occupancy_default_is_90(self):
        # 病棟・月を指定しなくてもデフォルト 90% が返る
        assert get_occupancy_target("5F") == 90.0
        assert get_occupancy_target("6F") == 90.0

    def test_occupancy_default_for_any_month(self):
        # overrides が空なので、どの月でも 90%
        assert get_occupancy_target("5F", date(2026, 4, 1)) == 90.0
        assert get_occupancy_target("6F", date(2026, 12, 1)) == 90.0
        assert get_occupancy_target("5F", date(2027, 1, 1)) == 90.0

    def test_alos_regulatory_limit_is_21(self):
        assert get_alos_regulatory_limit() == 21.0

    def test_alos_warning_threshold_is_1995(self):
        assert get_alos_warning_threshold() == 19.95

    def test_alos_rolling_window_is_3_months(self):
        assert get_alos_rolling_window_months() == 3

    def test_emergency_minimum_is_15(self):
        assert get_emergency_ratio_minimum() == 15.0

    def test_emergency_rolling_window_is_3_months(self):
        assert get_emergency_rolling_window_months() == 3

    def test_emergency_ward_specific_is_true(self):
        assert is_emergency_ratio_ward_specific() is True

    def test_total_beds_is_94(self):
        assert get_total_beds() == 94

    def test_ward_bed_count_initially_none(self):
        # 初期状態では null（実運用入力待ち）
        assert get_ward_bed_count("5F") is None
        assert get_ward_bed_count("6F") is None

    def test_ward_specialty(self):
        assert get_ward_specialty("5F") == "外科・整形"
        assert get_ward_specialty("6F") == "内科・ペイン"


# ---------------------------------------------------------------------------
# 経過措置期間判定
# ---------------------------------------------------------------------------

class TestTransitionalPeriod:
    """2026-05-31 が境界。以前＝True、以降＝False。"""

    def test_today_2026_04_17_is_transitional(self):
        assert is_transitional_period(date(2026, 4, 17)) is True

    def test_2026_05_31_is_transitional(self):
        # 終了日当日は経過措置期間内
        assert is_transitional_period(date(2026, 5, 31)) is True

    def test_2026_06_01_is_not_transitional(self):
        # 翌日（本則適用開始）は False
        assert is_transitional_period(date(2026, 6, 1)) is False

    def test_far_future_is_not_transitional(self):
        assert is_transitional_period(date(2027, 1, 1)) is False

    def test_before_end_date(self):
        assert is_transitional_period(date(2025, 12, 31)) is True


# ---------------------------------------------------------------------------
# overrides 優先の挙動（テスト用 YAML）
# ---------------------------------------------------------------------------

@pytest.fixture
def override_yaml(tmp_path: Path) -> Path:
    """5F 2026-04 を 88%、6F 2026-12 を 85% に上書きしたテスト用 YAML。"""
    yaml_text = """
version: 1
updated: 2026-04-17

occupancy_target:
  default: 90
  overrides:
    5F:
      2026-04: 88
      2026-05: 87.5
    6F:
      2026-12: 85

alos_target:
  regulatory_limit_days: 21
  warning_threshold_days: 19.95
  rolling_window_months: 3
  transitional_end_date: "2026-05-31"

emergency_ratio_target:
  regulatory_minimum_pct: 15
  rolling_window_months: 3
  ward_specific: true

beds:
  total: 94
  5F:
    count: 48
    specialty: "外科・整形"
  6F:
    count: 46
    specialty: "内科・ペイン"
"""
    path = tmp_path / "override.yaml"
    path.write_text(yaml_text, encoding="utf-8")
    return path


class TestOverrides:
    """overrides が優先されることを検証する。"""

    def test_override_applies_for_matching_ward_and_month(self, override_yaml: Path):
        # 5F 2026-04 → 88（override）
        assert get_occupancy_target("5F", date(2026, 4, 1), override_yaml) == 88.0

    def test_override_applies_for_second_month(self, override_yaml: Path):
        # 5F 2026-05 → 87.5（小数 override）
        assert get_occupancy_target("5F", date(2026, 5, 15), override_yaml) == 87.5

    def test_override_per_ward(self, override_yaml: Path):
        # 6F 2026-12 → 85（override）
        assert get_occupancy_target("6F", date(2026, 12, 1), override_yaml) == 85.0

    def test_fallback_to_default_when_month_not_overridden(self, override_yaml: Path):
        # 5F 2026-06 は override に無いので default 90
        assert get_occupancy_target("5F", date(2026, 6, 1), override_yaml) == 90.0

    def test_fallback_to_default_when_ward_not_overridden(self, override_yaml: Path):
        # 存在しない病棟 "7F" → default 90
        assert get_occupancy_target("7F", date(2026, 4, 1), override_yaml) == 90.0

    def test_no_month_uses_default(self, override_yaml: Path):
        # month を渡さないと overrides 参照しない
        assert get_occupancy_target("5F", None, override_yaml) == 90.0

    def test_ward_bed_count_from_override_yaml(self, override_yaml: Path):
        assert get_ward_bed_count("5F", override_yaml) == 48
        assert get_ward_bed_count("6F", override_yaml) == 46


# ---------------------------------------------------------------------------
# エッジケース
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """壊れた YAML・欠損ファイルに対するフォールバック。"""

    def test_missing_file_returns_empty_dict(self, tmp_path: Path):
        missing = tmp_path / "nonexistent.yaml"
        assert load_targets(missing) == {}

    def test_missing_file_fallback_to_defaults(self, tmp_path: Path):
        missing = tmp_path / "nonexistent.yaml"
        assert get_occupancy_target("5F", date(2026, 4, 1), missing) == 90.0
        assert get_alos_regulatory_limit(missing) == 21.0
        assert get_alos_warning_threshold(missing) == 19.95
        assert get_emergency_ratio_minimum(missing) == 15.0

    def test_missing_file_transitional_fallback(self, tmp_path: Path):
        missing = tmp_path / "nonexistent.yaml"
        # YAML が無くても経過措置判定は動く（定数フォールバック）
        assert is_transitional_period(date(2026, 4, 17), missing) is True
        assert is_transitional_period(date(2026, 6, 1), missing) is False

    def test_empty_yaml_fallback(self, tmp_path: Path):
        empty = tmp_path / "empty.yaml"
        empty.write_text("", encoding="utf-8")
        assert load_targets(empty) == {}
        assert get_occupancy_target("5F", None, empty) == 90.0

    def test_default_config_path_exists(self):
        # 本番 YAML ファイルが実際に存在すること
        assert _DEFAULT_CONFIG_PATH.exists(), (
            f"設定ファイル {_DEFAULT_CONFIG_PATH} が存在しません"
        )
