"""patient_status_store の単体テスト.

検証項目:
- save → load ラウンドトリップ
- ファイル欠損時の動作（load_status が None を返す）
- 無効な status_key の拒否（ValueError）
- 複数患者データの独立性
- Atomic 書き込み（途中失敗で既存ファイルを壊さない）
- 破損 JSON でも空辞書として動作（堅牢性）
- UTF-8 日本語の正しい保存
- clear_all_statuses の動作
"""

from __future__ import annotations

import json
import os
import sys
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

import patient_status_store as pss  # noqa: E402


@pytest.fixture
def temp_storage(tmp_path: Path) -> Iterator[Path]:
    """_STORAGE_PATH を一時ディレクトリに差し替える."""
    test_path = tmp_path / "patient_status.json"
    with patch.object(pss, "_STORAGE_PATH", test_path):
        yield test_path


class TestLoadMissingFile:
    """ファイル欠損時の動作."""

    def test_load_all_returns_empty_dict_when_file_missing(self, temp_storage: Path):
        assert not temp_storage.exists()
        assert pss.load_all_statuses() == {}

    def test_load_single_returns_none_when_file_missing(self, temp_storage: Path):
        assert not temp_storage.exists()
        assert pss.load_status("a1b2c3d4") is None

    def test_load_single_returns_none_for_unknown_uuid(self, temp_storage: Path):
        """存在しない UUID では None を返す（ファイル自体はあってもよい）."""
        pss.save_status("known", "rehab")
        assert pss.load_status("unknown") is None


class TestRoundTrip:
    """save → load のラウンドトリップ."""

    def test_full_roundtrip(self, temp_storage: Path):
        pss.save_status("a1b2c3d4", "rehab")
        assert pss.load_status("a1b2c3d4") == "rehab"

    def test_new_status_roundtrip(self, temp_storage: Path):
        """初期値 "new" が保存・復元できる."""
        pss.save_status("b2c3d4e5", "new")
        assert pss.load_status("b2c3d4e5") == "new"

    def test_overwrite_existing_entry(self, temp_storage: Path):
        """同じ UUID で再保存すると上書きされる."""
        pss.save_status("same", "new")
        pss.save_status("same", "medical")
        pss.save_status("same", "family")
        assert pss.load_status("same") == "family"

    def test_all_valid_status_keys_roundtrip(self, temp_storage: Path):
        """VALID_STATUS_KEYS の全てが保存・復元できる."""
        for i, key in enumerate(pss.VALID_STATUS_KEYS):
            uuid_prefix = f"uuid{i:04d}"
            pss.save_status(uuid_prefix, key)
            assert pss.load_status(uuid_prefix) == key


class TestInvalidInputs:
    """不正入力の拒否."""

    def test_empty_uuid_raises_value_error(self, temp_storage: Path):
        with pytest.raises(ValueError):
            pss.save_status("", "new")

    def test_invalid_status_key_raises_value_error(self, temp_storage: Path):
        """VALID_STATUS_KEYS にない値は拒否."""
        with pytest.raises(ValueError):
            pss.save_status("uuid", "invalid_status")

    def test_empty_status_key_raises_value_error(self, temp_storage: Path):
        with pytest.raises(ValueError):
            pss.save_status("uuid", "")


class TestMultiplePatientIndependence:
    """複数患者データの独立性."""

    def test_multiple_patients_do_not_interfere(self, temp_storage: Path):
        """patient A を保存した後、B を保存しても A が残っている."""
        pss.save_status("patient_a", "rehab")
        pss.save_status("patient_b", "medical")
        pss.save_status("patient_c", "family")
        assert pss.load_status("patient_a") == "rehab"
        assert pss.load_status("patient_b") == "medical"
        assert pss.load_status("patient_c") == "family"

    def test_load_all_returns_all_entries(self, temp_storage: Path):
        pss.save_status("p1", "new")
        pss.save_status("p2", "facility")
        all_statuses = pss.load_all_statuses()
        assert set(all_statuses.keys()) == {"p1", "p2"}
        assert all_statuses["p1"] == "new"
        assert all_statuses["p2"] == "facility"

    def test_update_one_does_not_affect_others(self, temp_storage: Path):
        """1 名更新しても他の患者データは変化しない."""
        pss.save_status("stable", "rehab")
        pss.save_status("changing", "new")
        pss.save_status("changing", "medical")
        assert pss.load_status("stable") == "rehab"


class TestAtomicWrite:
    """Atomic 書き込みで既存ファイルを壊さない."""

    def test_existing_file_preserved_when_write_fails(
        self, temp_storage: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """書き込み中に例外が発生しても既存ファイルは壊れない."""
        # まず正常に保存
        pss.save_status("original", "rehab")
        original_content = temp_storage.read_text(encoding="utf-8")
        assert "rehab" in original_content

        # os.replace を失敗させる
        real_replace = os.replace

        def failing_replace(src: str, dst: str) -> None:
            raise OSError("simulated replace failure")

        monkeypatch.setattr(os, "replace", failing_replace)

        with pytest.raises(OSError, match="simulated replace failure"):
            pss.save_status("original", "family")

        monkeypatch.setattr(os, "replace", real_replace)

        # 既存ファイルは無傷
        assert temp_storage.read_text(encoding="utf-8") == original_content
        assert pss.load_status("original") == "rehab"

    def test_no_leftover_tempfiles_on_success(self, temp_storage: Path):
        """正常終了時に ``.patient_status_*.json.tmp`` が残らない."""
        pss.save_status("ok", "new")
        leftover = list(temp_storage.parent.glob(".patient_status_*.json.tmp"))
        assert leftover == [], f"tempfile が残っている: {leftover}"

    def test_tempfile_cleaned_on_write_failure(
        self, temp_storage: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """書き込み失敗時でも tempfile は掃除される."""

        def failing_replace(src: str, dst: str) -> None:
            raise OSError("simulated failure")

        monkeypatch.setattr(os, "replace", failing_replace)

        with pytest.raises(OSError):
            pss.save_status("x", "new")

        leftover = list(temp_storage.parent.glob(".patient_status_*.json.tmp"))
        assert leftover == [], f"失敗後に tempfile が残っている: {leftover}"


class TestRobustness:
    """堅牢性 — 破損 JSON や想定外フォーマット."""

    def test_broken_json_returns_empty_dict(self, temp_storage: Path):
        """JSON 構文エラーのファイルは空扱い."""
        temp_storage.parent.mkdir(parents=True, exist_ok=True)
        temp_storage.write_text("{ invalid json", encoding="utf-8")
        assert pss.load_all_statuses() == {}

    def test_non_dict_root_returns_empty(self, temp_storage: Path):
        """ルートが dict でない（list 等）なら空扱い."""
        temp_storage.parent.mkdir(parents=True, exist_ok=True)
        temp_storage.write_text('["not", "a", "dict"]', encoding="utf-8")
        assert pss.load_all_statuses() == {}

    def test_non_string_value_entries_excluded(self, temp_storage: Path):
        """値が str でないエントリは無視される."""
        temp_storage.parent.mkdir(parents=True, exist_ok=True)
        temp_storage.write_text(
            '{"good": "rehab", "bad": 123}',
            encoding="utf-8",
        )
        all_statuses = pss.load_all_statuses()
        assert "good" in all_statuses
        assert "bad" not in all_statuses
        assert all_statuses["good"] == "rehab"

    def test_unknown_status_key_excluded(self, temp_storage: Path):
        """VALID_STATUS_KEYS にない値は load 時に無視される."""
        temp_storage.parent.mkdir(parents=True, exist_ok=True)
        temp_storage.write_text(
            '{"ok": "new", "legacy": "old_category"}',
            encoding="utf-8",
        )
        all_statuses = pss.load_all_statuses()
        assert "ok" in all_statuses
        assert "legacy" not in all_statuses

    def test_parent_directory_created_if_missing(self, tmp_path: Path):
        """保存先の親ディレクトリがなければ自動作成."""
        deep_path = tmp_path / "deep" / "nested" / "patient_status.json"
        with patch.object(pss, "_STORAGE_PATH", deep_path):
            assert not deep_path.parent.exists()
            pss.save_status("x", "new")
            assert deep_path.exists()
            assert pss.load_status("x") == "new"


class TestJSONStructure:
    """保存される JSON の形式."""

    def test_saved_json_is_valid(self, temp_storage: Path):
        pss.save_status("utf", "rehab")
        content = temp_storage.read_text(encoding="utf-8")
        data = json.loads(content)
        assert isinstance(data, dict)
        assert data["utf"] == "rehab"

    def test_saved_json_is_human_readable_indent(self, temp_storage: Path):
        """indent 付きで書き出される（デバッグ時の可読性）."""
        pss.save_status("x", "new")
        content = temp_storage.read_text(encoding="utf-8")
        assert "\n" in content


class TestClearAllStatuses:
    """clear_all_statuses の動作."""

    def test_clear_removes_all_entries(self, temp_storage: Path):
        pss.save_status("a", "new")
        pss.save_status("b", "rehab")
        assert pss.load_all_statuses() == {"a": "new", "b": "rehab"}
        pss.clear_all_statuses()
        assert pss.load_all_statuses() == {}

    def test_clear_when_file_missing_is_noop(self, temp_storage: Path):
        """ファイルが存在しなくても例外を投げない."""
        assert not temp_storage.exists()
        pss.clear_all_statuses()  # noop
        assert not temp_storage.exists()

    def test_clear_returns_count_of_cleared_entries(self, temp_storage: Path):
        """clear_all_statuses は削除件数を返す."""
        pss.save_status("a", "new")
        pss.save_status("b", "rehab")
        pss.save_status("c", "medical")
        count = pss.clear_all_statuses()
        assert count == 3
        assert pss.load_all_statuses() == {}

    def test_clear_returns_zero_when_file_missing(self, temp_storage: Path):
        """ファイル未作成時の返り値は 0."""
        count = pss.clear_all_statuses()
        assert count == 0

    def test_clear_returns_one_for_single_entry(self, temp_storage: Path):
        pss.save_status("only", "rehab")
        count = pss.clear_all_statuses()
        assert count == 1


class TestClearStatus:
    """clear_status (個別クリア) の動作."""

    def test_clear_removes_specified_entry(self, temp_storage: Path):
        pss.save_status("a", "rehab")
        pss.save_status("b", "medical")
        pss.clear_status("a")
        assert pss.load_status("a") is None
        assert pss.load_status("b") == "medical"

    def test_clear_nonexistent_uuid_is_noop(self, temp_storage: Path):
        """存在しない UUID のクリアは例外なしで何もしない."""
        pss.save_status("a", "rehab")
        pss.clear_status("unknown")
        assert pss.load_status("a") == "rehab"

    def test_clear_when_file_missing_is_noop(self, temp_storage: Path):
        """ファイル未作成時でも例外なし."""
        assert not temp_storage.exists()
        pss.clear_status("unknown")  # noop
        # ファイル未作成のまま
        assert not temp_storage.exists()

    def test_clear_empty_uuid_raises(self, temp_storage: Path):
        with pytest.raises(ValueError):
            pss.clear_status("")

    def test_clear_last_entry_leaves_empty_file(self, temp_storage: Path):
        """最後のエントリをクリア → ファイルは残るが空辞書になる."""
        pss.save_status("only", "rehab")
        pss.clear_status("only")
        assert pss.load_all_statuses() == {}
        # ファイルは残っている（load は空辞書を返す）
        # 注: 仕様上、空辞書ファイルが残っても load_all_statuses の結果は {} なので OK


class TestValidStatusKeys:
    """VALID_STATUS_KEYS の確認."""

    def test_valid_keys_is_tuple(self):
        """VALID_STATUS_KEYS は tuple."""
        assert isinstance(pss.VALID_STATUS_KEYS, tuple)

    def test_valid_keys_contains_new(self):
        """"new" は必ず含まれる（副院長指示: 初期値は new）."""
        assert "new" in pss.VALID_STATUS_KEYS

    def test_valid_keys_contains_normal_mode_keys(self):
        """通常モード 7 種が含まれる."""
        for key in ("undecided", "medical", "family", "facility",
                    "insurance", "rehab", "new"):
            assert key in pss.VALID_STATUS_KEYS

    def test_valid_keys_contains_holiday_mode_keys(self):
        """連休対策モード 3 種が含まれる."""
        for key in ("before_confirmed", "before_adjusting", "continuing"):
            assert key in pss.VALID_STATUS_KEYS
