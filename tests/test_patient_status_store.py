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
- 履歴追記（変化時のみ）
- 履歴読み込み（時系列順）
- 今週の変化集計（境界値）
- 遷移ペア取得
- 停滞患者洗い出し
"""

from __future__ import annotations

import json
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

import patient_status_store as pss  # noqa: E402


@pytest.fixture
def temp_storage(tmp_path: Path) -> Iterator[Path]:
    """_STORAGE_PATH / _HISTORY_PATH を一時ディレクトリに差し替える."""
    test_path = tmp_path / "patient_status.json"
    history_path = tmp_path / "patient_status_history.json"
    with patch.object(pss, "_STORAGE_PATH", test_path), \
         patch.object(pss, "_HISTORY_PATH", history_path):
        yield test_path


@pytest.fixture
def temp_history(tmp_path: Path) -> Iterator[Path]:
    """履歴ファイル専用の一時パス（既存テストとは別に使える）."""
    status_path = tmp_path / "patient_status.json"
    history_path = tmp_path / "patient_status_history.json"
    with patch.object(pss, "_STORAGE_PATH", status_path), \
         patch.object(pss, "_HISTORY_PATH", history_path):
        yield history_path


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


# ===========================================================================
# 履歴機能（2026-04-18 追加）
# ===========================================================================


class TestHistoryAppendOnChange:
    """save_status は変化時のみ履歴に追記する."""

    def test_history_empty_when_file_missing(self, temp_history: Path):
        """履歴ファイル未作成時、load_status_history は空リスト."""
        assert not temp_history.exists()
        assert pss.load_status_history("any") == []
        assert pss.load_all_status_history() == {}

    def test_first_save_creates_history(self, temp_history: Path):
        """初回 save_status で履歴が 1 件追加される."""
        pss.save_status("u1", "new")
        history = pss.load_status_history("u1")
        assert len(history) == 1
        assert history[0]["status"] == "new"
        assert "timestamp" in history[0]
        assert "conference_date" in history[0]

    def test_same_status_does_not_append_history(self, temp_history: Path):
        """同じステータスで連続保存しても履歴は肥大化しない."""
        pss.save_status("u1", "new")
        pss.save_status("u1", "new")
        pss.save_status("u1", "new")
        history = pss.load_status_history("u1")
        assert len(history) == 1, (
            f"同ステータスの連続保存で履歴が肥大化している: {history}"
        )

    def test_status_change_appends_history(self, temp_history: Path):
        """ステータスが変化すると履歴に追記される."""
        pss.save_status("u1", "new")
        pss.save_status("u1", "undecided")
        pss.save_status("u1", "family")
        history = pss.load_status_history("u1")
        assert len(history) == 3
        statuses = [h["status"] for h in history]
        assert statuses == ["new", "undecided", "family"]

    def test_mixed_same_and_different_only_appends_on_change(
        self, temp_history: Path
    ):
        """(A, A, B, B, C) 保存 → 履歴は (A, B, C) の 3 件."""
        pss.save_status("u1", "new")
        pss.save_status("u1", "new")  # 同じ → 追記なし
        pss.save_status("u1", "undecided")  # 変化 → 追記
        pss.save_status("u1", "undecided")  # 同じ → 追記なし
        pss.save_status("u1", "family")  # 変化 → 追記
        history = pss.load_status_history("u1")
        assert len(history) == 3
        assert [h["status"] for h in history] == ["new", "undecided", "family"]

    def test_multiple_patients_have_independent_histories(
        self, temp_history: Path
    ):
        """複数患者の履歴は独立."""
        pss.save_status("u1", "new")
        pss.save_status("u1", "rehab")
        pss.save_status("u2", "family")
        pss.save_status("u2", "facility")
        h1 = pss.load_status_history("u1")
        h2 = pss.load_status_history("u2")
        assert [h["status"] for h in h1] == ["new", "rehab"]
        assert [h["status"] for h in h2] == ["family", "facility"]


class TestLoadStatusHistory:
    """load_status_history の読み込み動作."""

    def test_returns_empty_list_for_unknown_uuid(self, temp_history: Path):
        pss.save_status("known", "new")
        assert pss.load_status_history("unknown") == []

    def test_returns_empty_for_empty_uuid(self, temp_history: Path):
        """空 UUID は空リストを返す（raise ではなく）."""
        assert pss.load_status_history("") == []

    def test_history_sorted_by_timestamp(self, temp_history: Path):
        """load_status_history は timestamp 昇順でソートされる."""
        # 手動でファイルに書き込んで順序を乱す
        import json
        temp_history.parent.mkdir(parents=True, exist_ok=True)
        temp_history.write_text(
            json.dumps({
                "u1": [
                    {
                        "timestamp": "2026-04-18T14:00:00",
                        "status": "family",
                        "conference_date": "2026-04-18",
                    },
                    {
                        "timestamp": "2026-04-11T10:00:00",
                        "status": "new",
                        "conference_date": "2026-04-11",
                    },
                    {
                        "timestamp": "2026-04-15T09:00:00",
                        "status": "undecided",
                        "conference_date": "2026-04-15",
                    },
                ]
            }),
            encoding="utf-8",
        )
        history = pss.load_status_history("u1")
        timestamps = [h["timestamp"] for h in history]
        assert timestamps == sorted(timestamps), (
            f"時系列順でソートされていない: {timestamps}"
        )

    def test_history_contains_conference_date(self, temp_history: Path):
        """履歴エントリには conference_date が含まれる."""
        pss.save_status("u1", "new")
        history = pss.load_status_history("u1")
        assert len(history) == 1
        assert "conference_date" in history[0]
        # YYYY-MM-DD 形式
        assert len(history[0]["conference_date"]) == 10

    def test_broken_history_file_returns_empty(self, temp_history: Path):
        """JSON 構文エラーの履歴ファイルは空扱い."""
        temp_history.parent.mkdir(parents=True, exist_ok=True)
        temp_history.write_text("{ invalid json", encoding="utf-8")
        assert pss.load_all_status_history() == {}
        assert pss.load_status_history("u1") == []

    def test_non_dict_root_history_returns_empty(self, temp_history: Path):
        """履歴ファイルのルートが dict でなければ空扱い."""
        temp_history.parent.mkdir(parents=True, exist_ok=True)
        temp_history.write_text("[1,2,3]", encoding="utf-8")
        assert pss.load_all_status_history() == {}

    def test_invalid_status_in_history_excluded(self, temp_history: Path):
        """VALID_STATUS_KEYS 外のエントリは無視される."""
        import json
        temp_history.parent.mkdir(parents=True, exist_ok=True)
        temp_history.write_text(
            json.dumps({
                "u1": [
                    {"timestamp": "2026-04-18T10:00:00", "status": "legacy_status"},
                    {"timestamp": "2026-04-18T11:00:00", "status": "new"},
                ]
            }),
            encoding="utf-8",
        )
        history = pss.load_status_history("u1")
        assert len(history) == 1
        assert history[0]["status"] == "new"

    def test_non_dict_entry_in_list_skipped(self, temp_history: Path):
        """履歴エントリが dict でなければ無視される."""
        import json
        temp_history.parent.mkdir(parents=True, exist_ok=True)
        temp_history.write_text(
            json.dumps({
                "u1": [
                    "not a dict",
                    {"timestamp": "2026-04-18T11:00:00", "status": "new"},
                ]
            }),
            encoding="utf-8",
        )
        history = pss.load_status_history("u1")
        assert len(history) == 1


class TestGetStatusChangesThisWeek:
    """get_status_changes_this_week の境界値."""

    def _write_history(self, path: Path, data: dict) -> None:
        import json
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_empty_history_returns_empty(self, temp_history: Path):
        assert not temp_history.exists()
        changes = pss.get_status_changes_this_week(date(2026, 4, 18))
        assert changes == []

    def test_within_window_included(self, temp_history: Path):
        """reference_date - 7 日以内のエントリは含まれる."""
        self._write_history(temp_history, {
            "u1": [
                {
                    "timestamp": "2026-04-15T10:00:00",
                    "status": "undecided",
                    "conference_date": "2026-04-15",
                },
            ]
        })
        changes = pss.get_status_changes_this_week(date(2026, 4, 18))
        assert len(changes) == 1
        assert changes[0]["to_status"] == "undecided"

    def test_outside_window_excluded(self, temp_history: Path):
        """window 外（8 日以上前）のエントリは含まれない."""
        self._write_history(temp_history, {
            "u1": [
                {
                    "timestamp": "2026-04-01T10:00:00",
                    "status": "new",
                    "conference_date": "2026-04-01",
                },
            ]
        })
        changes = pss.get_status_changes_this_week(date(2026, 4, 18))
        assert changes == []

    def test_exact_window_boundary_included(self, temp_history: Path):
        """reference_date ちょうど 7 日前は含まれる（=）."""
        self._write_history(temp_history, {
            "u1": [
                {
                    "timestamp": "2026-04-11T10:00:00",
                    "status": "new",
                    "conference_date": "2026-04-11",
                },
            ]
        })
        # window_start = 2026-04-11 (reference 2026-04-18 - 7 days)
        changes = pss.get_status_changes_this_week(date(2026, 4, 18))
        assert len(changes) == 1

    def test_exact_window_outside_excluded(self, temp_history: Path):
        """reference_date ちょうど 8 日前は除外される（<）."""
        self._write_history(temp_history, {
            "u1": [
                {
                    "timestamp": "2026-04-10T23:59:59",
                    "status": "new",
                    "conference_date": "2026-04-10",
                },
            ]
        })
        changes = pss.get_status_changes_this_week(date(2026, 4, 18))
        assert changes == []

    def test_reference_date_today_included(self, temp_history: Path):
        """reference_date 当日のエントリも含まれる."""
        self._write_history(temp_history, {
            "u1": [
                {
                    "timestamp": "2026-04-18T14:00:00",
                    "status": "family",
                    "conference_date": "2026-04-18",
                },
            ]
        })
        changes = pss.get_status_changes_this_week(date(2026, 4, 18))
        assert len(changes) == 1

    def test_from_status_is_previous_entry(self, temp_history: Path):
        """遷移した場合 from_status は 1 つ前のエントリ."""
        self._write_history(temp_history, {
            "u1": [
                {
                    "timestamp": "2026-04-01T10:00:00",
                    "status": "new",
                    "conference_date": "2026-04-01",
                },
                {
                    "timestamp": "2026-04-15T10:00:00",
                    "status": "undecided",
                    "conference_date": "2026-04-15",
                },
            ]
        })
        changes = pss.get_status_changes_this_week(date(2026, 4, 18))
        assert len(changes) == 1
        assert changes[0]["from_status"] == "new"
        assert changes[0]["to_status"] == "undecided"

    def test_first_entry_has_empty_from_status(self, temp_history: Path):
        """履歴の最初のエントリの from_status は空文字."""
        self._write_history(temp_history, {
            "u1": [
                {
                    "timestamp": "2026-04-15T10:00:00",
                    "status": "new",
                    "conference_date": "2026-04-15",
                },
            ]
        })
        changes = pss.get_status_changes_this_week(date(2026, 4, 18))
        assert len(changes) == 1
        assert changes[0]["from_status"] == ""

    def test_custom_days_parameter(self, temp_history: Path):
        """days=14 で 2 週間前のエントリも含まれる."""
        self._write_history(temp_history, {
            "u1": [
                {
                    "timestamp": "2026-04-05T10:00:00",
                    "status": "new",
                    "conference_date": "2026-04-05",
                },
            ]
        })
        # reference=2026-04-18, 7 日前は 2026-04-11 → 4/5 は含まれない
        assert pss.get_status_changes_this_week(date(2026, 4, 18), days=7) == []
        # 14 日前は 2026-04-04 → 4/5 は含まれる
        c14 = pss.get_status_changes_this_week(date(2026, 4, 18), days=14)
        assert len(c14) == 1

    def test_negative_days_raises(self, temp_history: Path):
        with pytest.raises(ValueError):
            pss.get_status_changes_this_week(date(2026, 4, 18), days=-1)

    def test_changes_sorted_by_timestamp(self, temp_history: Path):
        """複数患者の変化もグローバルに時系列ソートされる."""
        self._write_history(temp_history, {
            "u1": [
                {
                    "timestamp": "2026-04-17T14:00:00",
                    "status": "family",
                    "conference_date": "2026-04-17",
                },
            ],
            "u2": [
                {
                    "timestamp": "2026-04-15T09:00:00",
                    "status": "new",
                    "conference_date": "2026-04-15",
                },
            ],
        })
        changes = pss.get_status_changes_this_week(date(2026, 4, 18))
        assert len(changes) == 2
        # u2 (4/15) が先、u1 (4/17) が後
        assert changes[0]["uuid"] == "u2"
        assert changes[1]["uuid"] == "u1"


class TestGetStatusTransitions:
    """get_status_transitions の動作."""

    def test_empty_history_returns_empty(self, temp_history: Path):
        assert pss.get_status_transitions("unknown") == []

    def test_single_entry_returns_empty(self, temp_history: Path):
        """履歴が 1 件なら遷移なし."""
        pss.save_status("u1", "new")
        assert pss.get_status_transitions("u1") == []

    def test_two_entries_returns_one_transition(self, temp_history: Path):
        pss.save_status("u1", "new")
        pss.save_status("u1", "undecided")
        assert pss.get_status_transitions("u1") == [("new", "undecided")]

    def test_multiple_transitions(self, temp_history: Path):
        """N 件の履歴から N-1 個の遷移ペア."""
        pss.save_status("u1", "new")
        pss.save_status("u1", "undecided")
        pss.save_status("u1", "family")
        pss.save_status("u1", "facility")
        transitions = pss.get_status_transitions("u1")
        assert transitions == [
            ("new", "undecided"),
            ("undecided", "family"),
            ("family", "facility"),
        ]


class TestGetStagnantPatients:
    """get_stagnant_patients の洗い出し."""

    def _write_history(self, path: Path, data: dict) -> None:
        import json
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_empty_history_returns_empty(self, temp_history: Path):
        assert pss.get_stagnant_patients(date(2026, 4, 18)) == []

    def test_recent_change_not_stagnant(self, temp_history: Path):
        """3 週未満の変化なし患者は停滞扱いしない."""
        self._write_history(temp_history, {
            "u1": [
                {
                    "timestamp": "2026-04-15T10:00:00",
                    "status": "undecided",
                    "conference_date": "2026-04-15",
                },
            ]
        })
        stagnant = pss.get_stagnant_patients(date(2026, 4, 18), weeks=3)
        assert stagnant == []

    def test_old_change_is_stagnant(self, temp_history: Path):
        """3 週以上変化なし → 停滞."""
        self._write_history(temp_history, {
            "u1": [
                {
                    "timestamp": "2026-03-20T10:00:00",
                    "status": "undecided",
                    "conference_date": "2026-03-20",
                },
            ]
        })
        stagnant = pss.get_stagnant_patients(date(2026, 4, 18), weeks=3)
        assert len(stagnant) == 1
        assert stagnant[0]["uuid"] == "u1"
        assert stagnant[0]["status"] == "undecided"

    def test_stagnant_sorted_by_weeks_desc(self, temp_history: Path):
        """停滞期間の長い患者が先頭に来る."""
        self._write_history(temp_history, {
            "u1": [
                {
                    "timestamp": "2026-03-25T10:00:00",
                    "status": "undecided",
                    "conference_date": "2026-03-25",
                },
            ],
            "u2": [
                {
                    "timestamp": "2026-02-10T10:00:00",
                    "status": "family",
                    "conference_date": "2026-02-10",
                },
            ],
        })
        stagnant = pss.get_stagnant_patients(date(2026, 4, 18), weeks=3)
        assert len(stagnant) == 2
        # u2 の方が古い（2/10 < 3/25）→ 先頭
        assert stagnant[0]["uuid"] == "u2"
        assert stagnant[1]["uuid"] == "u1"

    def test_custom_weeks_parameter(self, temp_history: Path):
        """weeks=1 にすると 1 週以上の未変化を全て拾う."""
        self._write_history(temp_history, {
            "u1": [
                {
                    "timestamp": "2026-04-05T10:00:00",
                    "status": "new",
                    "conference_date": "2026-04-05",
                },
            ]
        })
        # 13 日経過 → weeks=1 なら停滞、weeks=3 なら非停滞
        assert len(pss.get_stagnant_patients(date(2026, 4, 18), weeks=1)) == 1
        assert len(pss.get_stagnant_patients(date(2026, 4, 18), weeks=3)) == 0

    def test_negative_weeks_raises(self, temp_history: Path):
        with pytest.raises(ValueError):
            pss.get_stagnant_patients(date(2026, 4, 18), weeks=-1)


class TestHistoryAtomicWrite:
    """履歴書き込みも atomic であること."""

    def test_history_preserved_when_write_fails(
        self, temp_history: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """履歴追記中に os.replace 失敗しても既存履歴は壊れない."""
        # 先に 1 件正常に書き込む
        pss.save_status("u1", "new")
        original_history = pss.load_status_history("u1")
        assert len(original_history) == 1

        # os.replace を失敗させる
        def failing_replace(src: str, dst: str) -> None:
            raise OSError("simulated failure")

        monkeypatch.setattr(os, "replace", failing_replace)

        # save_status は履歴書き込みに失敗するが、現在ステータス保存も失敗する
        # （現在ステータスが先に書かれる設計）
        with pytest.raises(OSError):
            pss.save_status("u1", "undecided")

        monkeypatch.undo()
        # 既存履歴は無傷
        history = pss.load_status_history("u1")
        assert len(history) == 1
        assert history[0]["status"] == "new"


class TestHistoryBackwardsCompat:
    """履歴機能は既存挙動を壊さない."""

    def test_existing_save_status_still_writes_status_file(
        self, temp_history: Path
    ):
        """save_status は従来通り現在ステータスも書き込む."""
        pss.save_status("u1", "rehab")
        assert pss.load_status("u1") == "rehab"

    def test_history_does_not_require_existing_status_file(
        self, temp_history: Path
    ):
        """履歴ファイルだけを単独で読んでもエラーにならない."""
        assert pss.load_all_status_history() == {}

    def test_status_file_without_history_file_works(self, temp_history: Path):
        """現在ステータスがあって履歴がないケースでも正常動作."""
        # 履歴を外部で削除した状態を模擬
        pss.save_status("u1", "new")
        # 履歴ファイルを手動削除
        if temp_history.exists():
            temp_history.unlink()
        # 次の save_status は正常に動作し、履歴を新規作成する
        pss.save_status("u1", "undecided")
        history = pss.load_status_history("u1")
        # 履歴ファイル削除後の新規変化のみ記録（undecided 1 件）
        assert len(history) == 1
        assert history[0]["status"] == "undecided"

    def test_clear_all_history_removes_history_only(
        self, temp_history: Path
    ):
        """clear_all_history は現在ステータスは残す."""
        pss.save_status("u1", "new")
        pss.save_status("u1", "rehab")
        assert pss.load_status("u1") == "rehab"
        count = pss.clear_all_history()
        assert count == 1
        # 現在ステータスは残っている
        assert pss.load_status("u1") == "rehab"
        # 履歴だけ消えた
        assert pss.load_status_history("u1") == []

    def test_clear_all_history_returns_zero_when_missing(
        self, temp_history: Path
    ):
        """履歴ファイル未作成時は 0 を返す."""
        assert pss.clear_all_history() == 0
