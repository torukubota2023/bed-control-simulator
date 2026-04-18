"""患者名・主治医名・患者ID の永続化ストア.

多職種退院調整カンファ画面で編集した患者情報（主治医名 / 患者名 / 患者ID）を
ローカルの JSON ファイルに保存・復元するための軽量ストア。

保存先
-------
``data/patient_names.json`` （リポジトリ直下 ``data/`` ディレクトリ）

フォーマット
-------------
::

    {
        "a1b2c3d4": {
            "doctor_name": "田中医師",
            "patient_name": "山田太郎",
            "patient_id": "12345"
        },
        ...
    }

キーは ``SamplePatient.patient_id``（UUID 先頭 8 桁）をそのまま使う。

設計上の方針
-------------
- **個人情報保護**: このファイルは ``.gitignore`` で除外する。Git 追跡禁止
- **ファイル欠損時**: 空辞書を返して UI 側で初期値を表示する
- **Atomic write**: tempfile + ``os.replace`` で書き込み途中の破損を防止
- **JSON 破損時**: 警告せず空辞書扱い（次回保存で上書きされるため）
- **UTF-8 固定**: 日本語を BMP 文字として正しく書き出す

公開 API
--------
- :func:`load_patient_info` — 1 患者の情報を取得
- :func:`save_patient_info` — 1 患者の情報を保存
- :func:`load_all_patient_info` — 全患者の情報を取得
- :func:`clear_patient_info` — 1 患者の指定項目をクリア
- :func:`clear_all_patient_info` — 全患者の指定項目を一括クリア
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

# リポジトリ内の data/ ディレクトリ
_STORAGE_PATH = Path(__file__).resolve().parent.parent / "data" / "patient_names.json"

# 1 患者分の空フィールド
_EMPTY_INFO: Dict[str, str] = {
    "doctor_name": "",
    "patient_name": "",
    "patient_id": "",
}


def _get_storage_path() -> Path:
    """保存先パスを返す（テストで差し替え可能にするための薄いラッパ）."""
    return _STORAGE_PATH


def load_all_patient_info() -> Dict[str, Dict[str, str]]:
    """全患者の情報を ``{uuid_prefix: {...}}`` の dict で返す.

    Returns
    -------
    dict
        UUID 先頭 8 桁をキーに、``{"doctor_name", "patient_name", "patient_id"}``
        の 3 フィールドを持つ dict。ファイル欠損や破損時は空 dict を返す。
    """
    path = _get_storage_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    # 値が dict でないエントリは除外（想定外フォーマットの堅牢化）
    cleaned: Dict[str, Dict[str, str]] = {}
    for key, value in data.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        cleaned[key] = {
            "doctor_name": str(value.get("doctor_name", "")),
            "patient_name": str(value.get("patient_name", "")),
            "patient_id": str(value.get("patient_id", "")),
        }
    return cleaned


def load_patient_info(patient_uuid_prefix: str) -> Dict[str, str]:
    """1 患者の情報を返す.

    Parameters
    ----------
    patient_uuid_prefix : str
        UUID 先頭 8 桁（``SamplePatient.patient_id`` と同じ）

    Returns
    -------
    dict
        ``{"doctor_name": str, "patient_name": str, "patient_id": str}``。
        該当データがなければ全フィールド空文字の dict を返す。
    """
    all_info = load_all_patient_info()
    if patient_uuid_prefix in all_info:
        # defensive copy
        return dict(all_info[patient_uuid_prefix])
    return dict(_EMPTY_INFO)


def save_patient_info(
    patient_uuid_prefix: str,
    doctor_name: str = "",
    patient_name: str = "",
    patient_id: str = "",
) -> None:
    """1 患者の情報を保存する（既存ファイルがあればマージ）.

    Parameters
    ----------
    patient_uuid_prefix : str
        UUID 先頭 8 桁
    doctor_name : str
        主治医名（空文字可）
    patient_name : str
        患者名（空文字可）
    patient_id : str
        患者ID（空文字可）

    Notes
    -----
    - 保存先の親ディレクトリがなければ自動作成する
    - Atomic write: 同一ディレクトリの tempfile に書き、``os.replace`` で差し替える
    - 既存の全エントリを保持したまま、該当キーだけを上書きする
    - UTF-8 固定、``ensure_ascii=False`` で日本語を BMP 文字として書く
    """
    if not patient_uuid_prefix:
        raise ValueError("patient_uuid_prefix は空にできません")

    all_info = load_all_patient_info()
    all_info[patient_uuid_prefix] = {
        "doctor_name": str(doctor_name),
        "patient_name": str(patient_name),
        "patient_id": str(patient_id),
    }

    path = _get_storage_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write: 同ディレクトリに tempfile を作り、fsync してから rename
    # （同一ボリューム内でなければ os.replace が atomic にならないため）
    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix=".patient_names_",
        suffix=".json.tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(all_info, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        # 失敗時は tempfile を掃除（既存ファイルは無傷のまま）
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _atomic_write_all(all_info: Dict[str, Dict[str, str]]) -> None:
    """``all_info`` dict をストアにまとめて書き込む (Atomic)."""
    path = _get_storage_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix=".patient_names_",
        suffix=".json.tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(all_info, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def clear_patient_info(
    patient_uuid_prefix: str,
    clear_doctor: bool = False,
    clear_name: bool = False,
    clear_id: bool = False,
) -> None:
    """指定した項目のみ空文字にする（エントリ自体は残す）.

    Parameters
    ----------
    patient_uuid_prefix : str
        UUID 先頭 8 桁
    clear_doctor : bool
        True なら主治医名を空文字にクリア
    clear_name : bool
        True なら患者名を空文字にクリア
    clear_id : bool
        True なら患者IDを空文字にクリア

    Notes
    -----
    - 全てのフラグが False の場合は何もしない
    - 対象 UUID がストアに存在しない場合は何もしない
    - クリア後、3 フィールド全てが空になった場合はエントリごと削除
    - Atomic write で既存エントリは保護される
    """
    if not patient_uuid_prefix:
        raise ValueError("patient_uuid_prefix は空にできません")

    if not (clear_doctor or clear_name or clear_id):
        return

    all_info = load_all_patient_info()
    if patient_uuid_prefix not in all_info:
        return

    entry = all_info[patient_uuid_prefix]
    if clear_doctor:
        entry["doctor_name"] = ""
    if clear_name:
        entry["patient_name"] = ""
    if clear_id:
        entry["patient_id"] = ""

    # 全フィールド空なら エントリごと削除
    if not entry["doctor_name"] and not entry["patient_name"] and not entry["patient_id"]:
        del all_info[patient_uuid_prefix]
    else:
        all_info[patient_uuid_prefix] = entry

    _atomic_write_all(all_info)


def clear_all_patient_info(
    clear_doctor: bool = False,
    clear_name: bool = False,
    clear_id: bool = False,
) -> int:
    """全患者の指定項目を一括クリアする.

    Parameters
    ----------
    clear_doctor : bool
        True なら全患者の主治医名をクリア
    clear_name : bool
        True なら全患者の患者名をクリア
    clear_id : bool
        True なら全患者の患者IDをクリア

    Returns
    -------
    int
        実際に変更された患者エントリの件数（元々空で変化がなかった患者は含めない）

    Notes
    -----
    - 全フラグが False なら 0 を返す（何もしない）
    - クリア後に 3 フィールド全て空になったエントリは削除
    """
    if not (clear_doctor or clear_name or clear_id):
        return 0

    all_info = load_all_patient_info()
    if not all_info:
        return 0

    changed_count = 0
    new_all_info: Dict[str, Dict[str, str]] = {}

    for uuid_prefix, entry in all_info.items():
        before = {
            "doctor_name": entry.get("doctor_name", ""),
            "patient_name": entry.get("patient_name", ""),
            "patient_id": entry.get("patient_id", ""),
        }
        after = dict(before)
        if clear_doctor:
            after["doctor_name"] = ""
        if clear_name:
            after["patient_name"] = ""
        if clear_id:
            after["patient_id"] = ""

        if after != before:
            changed_count += 1

        # 全フィールド空ならエントリ削除（new_all_info に追加しない）
        if after["doctor_name"] or after["patient_name"] or after["patient_id"]:
            new_all_info[uuid_prefix] = after

    _atomic_write_all(new_all_info)
    return changed_count


__all__ = [
    "load_all_patient_info",
    "load_patient_info",
    "save_patient_info",
    "clear_patient_info",
    "clear_all_patient_info",
]
