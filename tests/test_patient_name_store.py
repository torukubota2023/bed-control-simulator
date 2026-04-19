"""patient_name_store の単体テスト.

検証項目:
- save → load ラウンドトリップ
- ファイル欠損時の動作
- 空文字列フィールドの扱い
- 複数患者データの独立性
- Atomic 書き込み（途中失敗で既存ファイルを壊さない）
- 破損 JSON でも空辞書として動作（堅牢性）
- UTF-8 日本語の正しい保存
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

import patient_name_store as pns  # noqa: E402


@pytest.fixture
def temp_storage(tmp_path: Path) -> Iterator[Path]:
    """_STORAGE_PATH を一時ディレクトリに差し替える."""
    test_path = tmp_path / "patient_names.json"
    with patch.object(pns, "_STORAGE_PATH", test_path):
        yield test_path


class TestLoadMissingFile:
    """ファイル欠損時の動作."""

    def test_load_all_returns_empty_dict_when_file_missing(self, temp_storage: Path):
        assert not temp_storage.exists()
        assert pns.load_all_patient_info() == {}

    def test_load_single_returns_empty_fields_when_file_missing(self, temp_storage: Path):
        assert not temp_storage.exists()
        info = pns.load_patient_info("a1b2c3d4")
        assert info == {
            "doctor_name": "",
            "patient_name": "",
            "patient_id": "",
            "note": "",
        }

    def test_load_single_returns_empty_fields_for_unknown_uuid(self, temp_storage: Path):
        """存在しない UUID でも空フィールドを返す（ファイル自体はあってもよい）."""
        pns.save_patient_info("known", doctor_name="佐藤医師")
        info = pns.load_patient_info("unknown")
        assert info == {
            "doctor_name": "",
            "patient_name": "",
            "patient_id": "",
            "note": "",
        }


class TestRoundTrip:
    """save → load のラウンドトリップ."""

    def test_full_fields_roundtrip(self, temp_storage: Path):
        pns.save_patient_info(
            "a1b2c3d4",
            doctor_name="田中医師",
            patient_name="山田太郎",
            patient_id="12345",
        )
        info = pns.load_patient_info("a1b2c3d4")
        assert info["doctor_name"] == "田中医師"
        assert info["patient_name"] == "山田太郎"
        assert info["patient_id"] == "12345"
        # note は省略時は空（副院長指示 2026-04-19）
        assert info["note"] == ""

    def test_note_field_roundtrip(self, temp_storage: Path):
        """確認事項（note）フィールドを保存・復元できる.

        副院長指示（2026-04-19）: カンファの ✏️ 編集から
        確認事項をその場で記録可能に。
        """
        pns.save_patient_info(
            "a1b2c3d4",
            doctor_name="田中医師",
            patient_name="山田太郎",
            patient_id="12345",
            note="4/24までに退院目処を再評価、要再カンファ",
        )
        info = pns.load_patient_info("a1b2c3d4")
        assert info["note"] == "4/24までに退院目処を再評価、要再カンファ"

    def test_note_field_multiline_preserved(self, temp_storage: Path):
        """確認事項の改行が保持される（text_area 複数行入力想定）."""
        note_multiline = "ご家族面談 4/19 実施\n迎え日時を確認\n着替え準備の依頼"
        pns.save_patient_info("u1", note=note_multiline)
        info = pns.load_patient_info("u1")
        assert info["note"] == note_multiline
        assert info["note"].count("\n") == 2

    def test_clear_note_only(self, temp_storage: Path):
        """clear_patient_info で note のみクリアできる."""
        pns.save_patient_info(
            "u1",
            doctor_name="田中",
            patient_name="山田",
            patient_id="111",
            note="初回確認",
        )
        pns.clear_patient_info("u1", clear_note=True)
        info = pns.load_patient_info("u1")
        assert info["note"] == ""
        # 他フィールドは維持される
        assert info["doctor_name"] == "田中"
        assert info["patient_name"] == "山田"
        assert info["patient_id"] == "111"

    def test_note_only_entry_removed_when_cleared(self, temp_storage: Path):
        """note のみ記入したエントリで note クリアするとエントリごと削除."""
        pns.save_patient_info("u1", note="テスト")
        pns.clear_patient_info("u1", clear_note=True)
        # エントリが消えるので load は _EMPTY_INFO を返す
        info = pns.load_patient_info("u1")
        assert info["note"] == ""
        assert info["doctor_name"] == ""

    def test_empty_fields_roundtrip(self, temp_storage: Path):
        """空文字列フィールドでも保存・復元できる."""
        pns.save_patient_info("empty_uuid", doctor_name="", patient_name="", patient_id="")
        info = pns.load_patient_info("empty_uuid")
        assert info == {
            "doctor_name": "",
            "patient_name": "",
            "patient_id": "",
            "note": "",
        }

    def test_partial_fields_roundtrip(self, temp_storage: Path):
        """一部だけ入力でも残りは空文字列で保存される."""
        pns.save_patient_info("partial", doctor_name="伊藤医師")
        info = pns.load_patient_info("partial")
        assert info["doctor_name"] == "伊藤医師"
        assert info["patient_name"] == ""
        assert info["patient_id"] == ""

    def test_japanese_utf8_roundtrip(self, temp_storage: Path):
        """日本語（UTF-8）が正しく保存・読み出しできる."""
        pns.save_patient_info(
            "jp_utf8",
            doctor_name="渡辺裕史",
            patient_name="小林かずこ",
            patient_id="院内-0042",
        )
        # ファイル内容も直接確認
        content = temp_storage.read_text(encoding="utf-8")
        assert "渡辺裕史" in content
        assert "小林かずこ" in content
        assert "院内-0042" in content
        # load で復元できる
        info = pns.load_patient_info("jp_utf8")
        assert info["doctor_name"] == "渡辺裕史"
        assert info["patient_name"] == "小林かずこ"
        assert info["patient_id"] == "院内-0042"

    def test_overwrite_existing_entry(self, temp_storage: Path):
        """同じ UUID で再保存すると上書きされる."""
        pns.save_patient_info("same", doctor_name="旧医師", patient_name="旧名")
        pns.save_patient_info("same", doctor_name="新医師", patient_name="新名", patient_id="999")
        info = pns.load_patient_info("same")
        assert info["doctor_name"] == "新医師"
        assert info["patient_name"] == "新名"
        assert info["patient_id"] == "999"


class TestMultiplePatientIndependence:
    """複数患者データの独立性."""

    def test_multiple_patients_do_not_interfere(self, temp_storage: Path):
        """patient A を保存した後、B を保存しても A が残っている."""
        pns.save_patient_info(
            "patient_a", doctor_name="A医師", patient_name="A名", patient_id="A001"
        )
        pns.save_patient_info(
            "patient_b", doctor_name="B医師", patient_name="B名", patient_id="B002"
        )
        pns.save_patient_info(
            "patient_c", doctor_name="C医師", patient_name="C名", patient_id="C003"
        )
        assert pns.load_patient_info("patient_a")["doctor_name"] == "A医師"
        assert pns.load_patient_info("patient_b")["doctor_name"] == "B医師"
        assert pns.load_patient_info("patient_c")["doctor_name"] == "C医師"

    def test_load_all_returns_all_entries(self, temp_storage: Path):
        pns.save_patient_info("p1", doctor_name="X")
        pns.save_patient_info("p2", patient_name="Y")
        all_info = pns.load_all_patient_info()
        assert set(all_info.keys()) == {"p1", "p2"}
        assert all_info["p1"]["doctor_name"] == "X"
        assert all_info["p2"]["patient_name"] == "Y"

    def test_update_one_does_not_affect_others(self, temp_storage: Path):
        """1 名更新しても他の患者データは変化しない."""
        pns.save_patient_info("stable", doctor_name="不変医師", patient_id="S-100")
        pns.save_patient_info("changing", doctor_name="旧")
        pns.save_patient_info("changing", doctor_name="新")
        stable = pns.load_patient_info("stable")
        assert stable["doctor_name"] == "不変医師"
        assert stable["patient_id"] == "S-100"


class TestAtomicWrite:
    """Atomic 書き込みで既存ファイルを壊さない."""

    def test_existing_file_preserved_when_write_fails(
        self, temp_storage: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """書き込み中に例外が発生しても既存ファイルは壊れない."""
        # まず正常に保存
        pns.save_patient_info(
            "original", doctor_name="オリジナル医師", patient_name="オリジナル名"
        )
        original_content = temp_storage.read_text(encoding="utf-8")
        assert "オリジナル医師" in original_content

        # os.replace を失敗させる
        real_replace = os.replace

        def failing_replace(src: str, dst: str) -> None:
            # tempfile は残したまま例外
            raise OSError("simulated replace failure")

        monkeypatch.setattr(os, "replace", failing_replace)

        with pytest.raises(OSError, match="simulated replace failure"):
            pns.save_patient_info(
                "original", doctor_name="新医師", patient_name="新名"
            )

        # replace を戻す
        monkeypatch.setattr(os, "replace", real_replace)

        # 既存ファイルは無傷
        assert temp_storage.read_text(encoding="utf-8") == original_content
        assert pns.load_patient_info("original")["doctor_name"] == "オリジナル医師"

    def test_no_leftover_tempfiles_on_success(self, temp_storage: Path):
        """正常終了時に ``.patient_names_*.json.tmp`` が残らない."""
        pns.save_patient_info("ok", doctor_name="OK医師")
        leftover = list(temp_storage.parent.glob(".patient_names_*.json.tmp"))
        assert leftover == [], f"tempfile が残っている: {leftover}"

    def test_tempfile_cleaned_on_write_failure(
        self, temp_storage: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """書き込み失敗時でも tempfile は掃除される."""

        def failing_replace(src: str, dst: str) -> None:
            raise OSError("simulated failure")

        monkeypatch.setattr(os, "replace", failing_replace)

        with pytest.raises(OSError):
            pns.save_patient_info("x", doctor_name="Y")

        leftover = list(temp_storage.parent.glob(".patient_names_*.json.tmp"))
        assert leftover == [], f"失敗後に tempfile が残っている: {leftover}"


class TestRobustness:
    """堅牢性 — 破損 JSON や想定外フォーマット."""

    def test_broken_json_returns_empty_dict(self, temp_storage: Path):
        """JSON 構文エラーのファイルは空扱い."""
        temp_storage.parent.mkdir(parents=True, exist_ok=True)
        temp_storage.write_text("{ invalid json", encoding="utf-8")
        assert pns.load_all_patient_info() == {}

    def test_non_dict_root_returns_empty(self, temp_storage: Path):
        """ルートが dict でない（list 等）なら空扱い."""
        temp_storage.parent.mkdir(parents=True, exist_ok=True)
        temp_storage.write_text('["not", "a", "dict"]', encoding="utf-8")
        assert pns.load_all_patient_info() == {}

    def test_non_dict_value_entries_excluded(self, temp_storage: Path):
        """値が dict でないエントリは無視される."""
        temp_storage.parent.mkdir(parents=True, exist_ok=True)
        temp_storage.write_text(
            '{"good": {"doctor_name": "D"}, "bad": "not_a_dict"}',
            encoding="utf-8",
        )
        all_info = pns.load_all_patient_info()
        assert "good" in all_info
        assert "bad" not in all_info
        assert all_info["good"]["doctor_name"] == "D"
        # 欠損フィールドは空文字列で補完される
        assert all_info["good"]["patient_name"] == ""

    def test_empty_uuid_raises(self, temp_storage: Path):
        """空 UUID は ValueError."""
        with pytest.raises(ValueError):
            pns.save_patient_info("", doctor_name="X")

    def test_parent_directory_created_if_missing(self, tmp_path: Path):
        """保存先の親ディレクトリがなければ自動作成."""
        deep_path = tmp_path / "deep" / "nested" / "patient_names.json"
        with patch.object(pns, "_STORAGE_PATH", deep_path):
            assert not deep_path.parent.exists()
            pns.save_patient_info("x", doctor_name="D")
            assert deep_path.exists()
            assert pns.load_patient_info("x")["doctor_name"] == "D"

    def test_defensive_copy_on_load(self, temp_storage: Path):
        """load_patient_info の返り値を改変しても内部状態は壊れない."""
        pns.save_patient_info("defcopy", doctor_name="元")
        info = pns.load_patient_info("defcopy")
        info["doctor_name"] = "改変"
        # もう一度 load すると元の値
        info2 = pns.load_patient_info("defcopy")
        assert info2["doctor_name"] == "元"


class TestJSONStructure:
    """保存される JSON の形式."""

    def test_saved_json_is_valid_utf8(self, temp_storage: Path):
        pns.save_patient_info("utf", doctor_name="日本語")
        content = temp_storage.read_text(encoding="utf-8")
        data = json.loads(content)
        assert isinstance(data, dict)
        assert data["utf"]["doctor_name"] == "日本語"

    def test_saved_json_is_human_readable_indent(self, temp_storage: Path):
        """indent 付きで書き出される（デバッグ時の可読性）."""
        pns.save_patient_info("x", doctor_name="A")
        content = temp_storage.read_text(encoding="utf-8")
        # indent=2 なら改行が入る
        assert "\n" in content


class TestClearPatientInfo:
    """clear_patient_info (個別クリア) の動作."""

    def test_clear_doctor_only(self, temp_storage: Path):
        """主治医のみクリア → 他は残る."""
        pns.save_patient_info(
            "u1", doctor_name="田中医師", patient_name="山田", patient_id="111"
        )
        pns.clear_patient_info("u1", clear_doctor=True)
        info = pns.load_patient_info("u1")
        assert info["doctor_name"] == ""
        assert info["patient_name"] == "山田"
        assert info["patient_id"] == "111"

    def test_clear_name_only(self, temp_storage: Path):
        pns.save_patient_info(
            "u1", doctor_name="田中", patient_name="山田", patient_id="111"
        )
        pns.clear_patient_info("u1", clear_name=True)
        info = pns.load_patient_info("u1")
        assert info["doctor_name"] == "田中"
        assert info["patient_name"] == ""
        assert info["patient_id"] == "111"

    def test_clear_id_only(self, temp_storage: Path):
        pns.save_patient_info(
            "u1", doctor_name="田中", patient_name="山田", patient_id="111"
        )
        pns.clear_patient_info("u1", clear_id=True)
        info = pns.load_patient_info("u1")
        assert info["doctor_name"] == "田中"
        assert info["patient_name"] == "山田"
        assert info["patient_id"] == ""

    def test_clear_multiple_fields(self, temp_storage: Path):
        """2 フィールド同時クリア."""
        pns.save_patient_info(
            "u1", doctor_name="田中", patient_name="山田", patient_id="111"
        )
        pns.clear_patient_info("u1", clear_doctor=True, clear_id=True)
        info = pns.load_patient_info("u1")
        assert info["doctor_name"] == ""
        assert info["patient_name"] == "山田"
        assert info["patient_id"] == ""

    def test_clear_all_fields_removes_entry(self, temp_storage: Path):
        """3 フィールド全クリア → エントリ自体が削除される."""
        pns.save_patient_info(
            "u1", doctor_name="田中", patient_name="山田", patient_id="111"
        )
        pns.save_patient_info("u2", doctor_name="佐藤")
        pns.clear_patient_info(
            "u1", clear_doctor=True, clear_name=True, clear_id=True
        )
        # u1 のエントリは削除される（load_all で見ない）
        all_info = pns.load_all_patient_info()
        assert "u1" not in all_info
        assert "u2" in all_info

    def test_no_flags_is_noop(self, temp_storage: Path):
        """全フラグ False → 何もしない."""
        pns.save_patient_info(
            "u1", doctor_name="田中", patient_name="山田", patient_id="111"
        )
        pns.clear_patient_info("u1")
        info = pns.load_patient_info("u1")
        assert info["doctor_name"] == "田中"
        assert info["patient_name"] == "山田"
        assert info["patient_id"] == "111"

    def test_clear_nonexistent_uuid_is_noop(self, temp_storage: Path):
        """存在しない UUID に対するクリアは例外なしで何もしない."""
        pns.save_patient_info("u1", doctor_name="田中")
        pns.clear_patient_info("unknown", clear_doctor=True)
        # u1 は無傷
        assert pns.load_patient_info("u1")["doctor_name"] == "田中"

    def test_clear_empty_uuid_raises(self, temp_storage: Path):
        with pytest.raises(ValueError):
            pns.clear_patient_info("", clear_doctor=True)

    def test_clear_does_not_affect_other_patients(self, temp_storage: Path):
        """別患者のエントリは影響を受けない."""
        pns.save_patient_info("u1", doctor_name="田中")
        pns.save_patient_info("u2", doctor_name="佐藤", patient_name="鈴木")
        pns.clear_patient_info("u1", clear_doctor=True)
        # u2 は無傷
        info2 = pns.load_patient_info("u2")
        assert info2["doctor_name"] == "佐藤"
        assert info2["patient_name"] == "鈴木"


class TestClearAllPatientInfo:
    """clear_all_patient_info (一括クリア) の動作."""

    def test_clear_all_doctor_only(self, temp_storage: Path):
        pns.save_patient_info(
            "u1", doctor_name="田中", patient_name="山田", patient_id="111"
        )
        pns.save_patient_info(
            "u2", doctor_name="佐藤", patient_name="鈴木", patient_id="222"
        )
        count = pns.clear_all_patient_info(clear_doctor=True)
        assert count == 2
        assert pns.load_patient_info("u1")["doctor_name"] == ""
        assert pns.load_patient_info("u1")["patient_name"] == "山田"
        assert pns.load_patient_info("u2")["doctor_name"] == ""
        assert pns.load_patient_info("u2")["patient_name"] == "鈴木"

    def test_clear_all_name_only(self, temp_storage: Path):
        pns.save_patient_info("u1", patient_name="A")
        pns.save_patient_info("u2", patient_name="B")
        count = pns.clear_all_patient_info(clear_name=True)
        assert count == 2
        # 両方 patient_name が空になったので エントリごと削除される
        assert pns.load_all_patient_info() == {}

    def test_clear_all_id_only(self, temp_storage: Path):
        pns.save_patient_info(
            "u1", doctor_name="田中", patient_id="111"
        )
        pns.save_patient_info(
            "u2", doctor_name="佐藤", patient_id="222"
        )
        count = pns.clear_all_patient_info(clear_id=True)
        assert count == 2
        assert pns.load_patient_info("u1")["patient_id"] == ""
        assert pns.load_patient_info("u1")["doctor_name"] == "田中"
        assert pns.load_patient_info("u2")["patient_id"] == ""

    def test_clear_all_multiple_fields(self, temp_storage: Path):
        """2 フィールド一括クリア."""
        pns.save_patient_info(
            "u1", doctor_name="田中", patient_name="山田", patient_id="111"
        )
        count = pns.clear_all_patient_info(clear_doctor=True, clear_name=True)
        assert count == 1
        info = pns.load_patient_info("u1")
        assert info["doctor_name"] == ""
        assert info["patient_name"] == ""
        assert info["patient_id"] == "111"

    def test_clear_all_only_counts_changed_entries(self, temp_storage: Path):
        """元々空の患者はカウントしない."""
        pns.save_patient_info("u1", doctor_name="田中")  # doctor あり
        pns.save_patient_info("u2", doctor_name="")  # doctor 空（patient_name も空）
        # u2 は 3 フィールド全空 → save 時に保存されるが clear_doctor で変化なし
        # u1 は変化あり → count = 1
        count = pns.clear_all_patient_info(clear_doctor=True)
        assert count == 1

    def test_clear_all_no_flags_returns_zero(self, temp_storage: Path):
        pns.save_patient_info("u1", doctor_name="田中")
        count = pns.clear_all_patient_info()
        assert count == 0
        # データは無傷
        assert pns.load_patient_info("u1")["doctor_name"] == "田中"

    def test_clear_all_on_empty_store_returns_zero(self, temp_storage: Path):
        """ストアが空でも例外なく 0 を返す."""
        count = pns.clear_all_patient_info(clear_doctor=True)
        assert count == 0

    def test_clear_all_fields_removes_all_entries(self, temp_storage: Path):
        """3 フィールド全クリア → 全エントリ削除."""
        pns.save_patient_info(
            "u1", doctor_name="田中", patient_name="山田", patient_id="111"
        )
        pns.save_patient_info(
            "u2", doctor_name="佐藤", patient_name="鈴木", patient_id="222"
        )
        count = pns.clear_all_patient_info(
            clear_doctor=True, clear_name=True, clear_id=True
        )
        assert count == 2
        assert pns.load_all_patient_info() == {}
