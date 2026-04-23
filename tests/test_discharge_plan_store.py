"""discharge_plan_store / discharge_slot_config の単体テスト.

検証項目:
- save_plan → load_plan ラウンドトリップ
- ファイル欠損時の動作（load_plan が None を返す）
- 破損 JSON でも空辞書として動作（堅牢性）
- 突発退院マーカー（unplanned）の保存・読み込み
- scheduled_date = None（調整中のみ）の保存
- get_plans_for_date / get_plans_in_range の日付フィルタ
- clear_plan / clear_all_plans の動作
- get_coordination_start_date: status 履歴から最初の非 "new" を抽出
- discharge_slot_config: 曜日・祝日・前日超過・動的調整の組み合わせ
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

import pytest

# scripts/ を sys.path に追加
_SCRIPTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "scripts")
)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import discharge_plan_store as dps  # noqa: E402
import discharge_slot_config as dsc  # noqa: E402
import patient_status_store as pss  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_plan_storage(tmp_path: Path) -> Iterator[Path]:
    """_STORAGE_PATH を一時ディレクトリに差し替える."""
    test_path = tmp_path / "discharge_plans.json"
    with patch.object(dps, "_STORAGE_PATH", test_path):
        yield test_path


@pytest.fixture
def temp_both_storages(tmp_path: Path) -> Iterator[tuple[Path, Path, Path]]:
    """discharge_plans と patient_status の両方を一時ディレクトリに差し替える."""
    plan_path = tmp_path / "discharge_plans.json"
    status_path = tmp_path / "patient_status.json"
    history_path = tmp_path / "patient_status_history.json"
    with patch.object(dps, "_STORAGE_PATH", plan_path), \
         patch.object(pss, "_STORAGE_PATH", status_path), \
         patch.object(pss, "_HISTORY_PATH", history_path):
        yield plan_path, status_path, history_path


# ---------------------------------------------------------------------------
# save_plan / load_plan の基本動作
# ---------------------------------------------------------------------------

class TestSaveLoadPlan:
    def test_roundtrip(self, temp_plan_storage: Path) -> None:
        """save → load で値が一致する."""
        dps.save_plan("a1b2c3d4", scheduled_date=date(2026, 4, 25))
        result = dps.load_plan("a1b2c3d4")
        assert result is not None
        assert result["scheduled_date"] == "2026-04-25"
        assert result["confirmed"] is False
        assert result["unplanned"] is False

    def test_load_missing_file_returns_none(self, temp_plan_storage: Path) -> None:
        """ファイルが存在しない場合は None."""
        assert dps.load_plan("xxxxx") is None

    def test_load_empty_prefix_returns_none(self, temp_plan_storage: Path) -> None:
        """空文字列の UUID は None."""
        assert dps.load_plan("") is None

    def test_save_with_all_flags(self, temp_plan_storage: Path) -> None:
        """confirmed/unplanned フラグが正しく保存される."""
        dps.save_plan(
            "abc12345",
            scheduled_date=date(2026, 5, 1),
            confirmed=True,
            unplanned=True,
        )
        result = dps.load_plan("abc12345")
        assert result is not None
        assert result["confirmed"] is True
        assert result["unplanned"] is True

    def test_save_without_scheduled_date(self, temp_plan_storage: Path) -> None:
        """scheduled_date=None（調整中のみ）の保存が可能."""
        dps.save_plan("def67890", scheduled_date=None)
        result = dps.load_plan("def67890")
        assert result is not None
        assert result["scheduled_date"] is None
        assert result["confirmed"] is False

    def test_save_empty_uuid_raises(self, temp_plan_storage: Path) -> None:
        """空の UUID は ValueError."""
        with pytest.raises(ValueError):
            dps.save_plan("", scheduled_date=date(2026, 4, 25))

    def test_save_overwrites_existing(self, temp_plan_storage: Path) -> None:
        """同じ UUID への上書きが動作する."""
        dps.save_plan("a1b2c3d4", scheduled_date=date(2026, 4, 25))
        dps.save_plan("a1b2c3d4", scheduled_date=date(2026, 4, 30), confirmed=True)
        result = dps.load_plan("a1b2c3d4")
        assert result is not None
        assert result["scheduled_date"] == "2026-04-30"
        assert result["confirmed"] is True

    def test_multiple_patients_independent(self, temp_plan_storage: Path) -> None:
        """複数患者のデータが独立して保存される."""
        dps.save_plan("pat00001", scheduled_date=date(2026, 4, 25))
        dps.save_plan("pat00002", scheduled_date=date(2026, 4, 26), unplanned=True)
        dps.save_plan("pat00003", scheduled_date=None, confirmed=False)
        assert dps.load_plan("pat00001")["scheduled_date"] == "2026-04-25"
        assert dps.load_plan("pat00002")["unplanned"] is True
        assert dps.load_plan("pat00003")["scheduled_date"] is None


# ---------------------------------------------------------------------------
# 破損データ耐性
# ---------------------------------------------------------------------------

class TestRobustness:
    def test_broken_json_returns_empty(self, temp_plan_storage: Path) -> None:
        """壊れた JSON でも空辞書扱い."""
        temp_plan_storage.write_text("{ invalid json", encoding="utf-8")
        assert dps.load_all_plans() == {}

    def test_invalid_schema_filtered(self, temp_plan_storage: Path) -> None:
        """スキーマ違反のエントリは除外される."""
        import json
        temp_plan_storage.parent.mkdir(parents=True, exist_ok=True)
        temp_plan_storage.write_text(
            json.dumps({
                "valid001": {
                    "scheduled_date": "2026-04-25",
                    "confirmed": False,
                    "unplanned": False,
                },
                "invalid1": "not a dict",  # 除外
                "invalid2": {"scheduled_date": "not-a-date"},  # 除外
                "invalid3": {"scheduled_date": "2026-04-25", "confirmed": "yes"},  # bool でない
            }),
            encoding="utf-8",
        )
        plans = dps.load_all_plans()
        assert "valid001" in plans
        assert "invalid1" not in plans
        assert "invalid2" not in plans
        assert "invalid3" not in plans


# ---------------------------------------------------------------------------
# 日付範囲クエリ
# ---------------------------------------------------------------------------

class TestDateQueries:
    def test_get_plans_for_date(self, temp_plan_storage: Path) -> None:
        """指定日の退院予定患者を取得."""
        dps.save_plan("pat00001", scheduled_date=date(2026, 4, 25))
        dps.save_plan("pat00002", scheduled_date=date(2026, 4, 25))
        dps.save_plan("pat00003", scheduled_date=date(2026, 4, 26))
        dps.save_plan("pat00004", scheduled_date=None)  # 予定なし
        result = dps.get_plans_for_date(date(2026, 4, 25))
        assert set(result) == {"pat00001", "pat00002"}

    def test_get_plans_in_range(self, temp_plan_storage: Path) -> None:
        """日付範囲内の退院予定を日別に取得."""
        dps.save_plan("pat00001", scheduled_date=date(2026, 4, 25))
        dps.save_plan("pat00002", scheduled_date=date(2026, 4, 27))
        dps.save_plan("pat00003", scheduled_date=date(2026, 5, 1))  # 範囲外
        result = dps.get_plans_in_range(date(2026, 4, 25), date(2026, 4, 30))
        assert "2026-04-25" in result
        assert "2026-04-27" in result
        assert "2026-05-01" not in result

    def test_range_validation(self, temp_plan_storage: Path) -> None:
        """start > end は ValueError."""
        with pytest.raises(ValueError):
            dps.get_plans_in_range(date(2026, 5, 1), date(2026, 4, 25))


# ---------------------------------------------------------------------------
# clear 系
# ---------------------------------------------------------------------------

class TestClear:
    def test_clear_plan(self, temp_plan_storage: Path) -> None:
        dps.save_plan("pat00001", scheduled_date=date(2026, 4, 25))
        dps.save_plan("pat00002", scheduled_date=date(2026, 4, 26))
        dps.clear_plan("pat00001")
        assert dps.load_plan("pat00001") is None
        assert dps.load_plan("pat00002") is not None

    def test_clear_plan_missing_is_noop(self, temp_plan_storage: Path) -> None:
        dps.clear_plan("nonexistent")  # raises nothing

    def test_clear_all_plans(self, temp_plan_storage: Path) -> None:
        dps.save_plan("pat00001", scheduled_date=date(2026, 4, 25))
        dps.save_plan("pat00002", scheduled_date=date(2026, 4, 26))
        count = dps.clear_all_plans()
        assert count == 2
        assert dps.load_all_plans() == {}


# ---------------------------------------------------------------------------
# 調整開始日の抽出（status 履歴から）
# ---------------------------------------------------------------------------

class TestCoordinationStart:
    def test_no_history_returns_none(self, temp_both_storages) -> None:
        """履歴が空なら None."""
        assert dps.get_coordination_start_date("pat00001") is None

    def test_only_new_returns_none(self, temp_both_storages) -> None:
        """履歴が全て new のままなら None."""
        pss.save_status("pat00001", "new")
        assert dps.get_coordination_start_date("pat00001") is None

    def test_first_transition_to_non_new(self, temp_both_storages) -> None:
        """最初の非 new への遷移日を返す."""
        # 日付を固定してテスト
        d1 = datetime(2026, 4, 10, 14, 0, 0)
        d2 = datetime(2026, 4, 17, 14, 30, 0)
        # new → medical に遷移
        with patch.object(pss, "datetime") as mock_dt:
            mock_dt.now.return_value = d1
            mock_dt.fromisoformat = datetime.fromisoformat  # キープ
            pss.save_status("pat00001", "new")
        with patch.object(pss, "datetime") as mock_dt:
            mock_dt.now.return_value = d2
            mock_dt.fromisoformat = datetime.fromisoformat
            pss.save_status("pat00001", "medical")

        result = dps.get_coordination_start_date("pat00001")
        assert result == date(2026, 4, 17)

    def test_empty_uuid_returns_none(self, temp_both_storages) -> None:
        assert dps.get_coordination_start_date("") is None


# ---------------------------------------------------------------------------
# discharge_slot_config の枠計算
# ---------------------------------------------------------------------------

class TestSlotConfig:
    def test_weekday_base_slot(self) -> None:
        """月〜土曜は 5 枠."""
        assert dsc.get_base_slot(date(2026, 4, 27)) == 5  # 月
        assert dsc.get_base_slot(date(2026, 4, 28)) == 5  # 火
        assert dsc.get_base_slot(date(2026, 5, 2)) == 5   # 土

    def test_sunday_base_slot(self) -> None:
        """日曜は 2 枠."""
        assert dsc.get_base_slot(date(2026, 4, 26)) == 2  # 日

    def test_holiday_base_slot(self) -> None:
        """祝日フラグが立っていれば 2 枠."""
        assert dsc.get_base_slot(date(2026, 4, 29), is_holiday=True) == 2

    def test_previous_excess_reduces_slot(self) -> None:
        """前日超過分が今日の枠から引かれる."""
        assert dsc.calculate_effective_slot(
            date(2026, 4, 27), previous_day_excess=2
        ) == 3  # 5 - 2

    def test_previous_excess_clamped_by_min(self) -> None:
        """前日超過で極端に減っても下限 DYNAMIC_MIN_SLOT を下回らない."""
        result = dsc.calculate_effective_slot(
            date(2026, 4, 27), previous_day_excess=10
        )
        assert result >= dsc.DYNAMIC_MIN_SLOT

    def test_sunday_immune_to_excess(self) -> None:
        """日曜は前日超過の影響を受けず 2 枠固定."""
        assert dsc.calculate_effective_slot(
            date(2026, 4, 26), previous_day_excess=5
        ) == 2

    def test_sunday_immune_to_dynamic(self) -> None:
        """日曜は動的調整の影響を受けず 2 枠固定."""
        assert dsc.calculate_effective_slot(
            date(2026, 4, 26), occupancy_rate=0.99, vacancy_count=1
        ) == 2

    def test_high_occupancy_expands_slot(self) -> None:
        """稼働率 95% 以上で +1 枠."""
        result = dsc.calculate_effective_slot(
            date(2026, 4, 27), occupancy_rate=0.97
        )
        assert result == 6  # 5 + 1

    def test_low_occupancy_contracts_slot(self) -> None:
        """稼働率 80% 未満で -1 枠."""
        result = dsc.calculate_effective_slot(
            date(2026, 4, 27), occupancy_rate=0.75
        )
        assert result == 4  # 5 - 1

    def test_low_vacancy_expands_slot(self) -> None:
        """空床 3 以下で +1 枠."""
        result = dsc.calculate_effective_slot(
            date(2026, 4, 27), vacancy_count=2
        )
        assert result == 6  # 5 + 1

    def test_dynamic_max_cap(self) -> None:
        """動的調整でも上限 DYNAMIC_MAX_SLOT を超えない."""
        result = dsc.calculate_effective_slot(
            date(2026, 4, 27), occupancy_rate=0.99, vacancy_count=1
        )
        # 両方 +1 適用されても上限 8 でクランプ
        assert result <= dsc.DYNAMIC_MAX_SLOT

    def test_dynamic_and_excess_combined(self) -> None:
        """稼働率拡張 + 前日超過の組み合わせ."""
        result = dsc.calculate_effective_slot(
            date(2026, 4, 27), previous_day_excess=1, occupancy_rate=0.97
        )
        assert result == 5  # 5 - 1 + 1

    def test_is_holiday_slot_day_sunday(self) -> None:
        assert dsc.is_holiday_slot_day(date(2026, 4, 26)) is True  # 日

    def test_is_holiday_slot_day_weekday(self) -> None:
        assert dsc.is_holiday_slot_day(date(2026, 4, 27)) is False  # 月

    def test_is_holiday_slot_day_jp_holiday(self) -> None:
        assert dsc.is_holiday_slot_day(date(2026, 4, 29), is_holiday=True) is True
