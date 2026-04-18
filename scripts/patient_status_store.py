"""患者ステータス（カンファ区分）の永続化ストア.

多職種退院調整カンファ画面で更新した患者のステータス
（🆕 新規 / ⚫ 方向性未決 / 🔵 医学的OK待ち / 🟢 家族希望待ち /
🟡 施設待ち / 🟣 介護保険待ち / 🟠 リハ最適化中）を
ローカルの JSON ファイルに保存・復元するための軽量ストア。

保存先
-------
``data/patient_status.json`` （リポジトリ直下 ``data/`` ディレクトリ）

フォーマット
-------------
::

    {
        "a1b2c3d4": "rehab",
        "b2c3d4e5": "new",
        ...
    }

キーは ``SamplePatient.patient_id``（UUID 先頭 8 桁）、値は
``_STATUS_NORMAL`` / ``_STATUS_HOLIDAY`` に含まれる ``key`` 文字列。

許容される status_key の一覧は :data:`VALID_STATUS_KEYS` に集約する。

設計上の方針
-------------
- **個人情報ではない**が、ユーザー固有の運用データなので Git 追跡しない
  （``.gitignore`` で ``data/patient_status.json`` を除外する）
- **ファイル欠損時**: ``load_status`` は ``None`` を返す（UI 側で既定値 "new"）
- **Atomic write**: tempfile + ``os.replace`` で書き込み途中の破損を防止
- **JSON 破損時**: 警告せず空辞書扱い（次回保存で上書きされる）
- **UTF-8 固定**: BMP 文字（status_key は ASCII だが将来拡張に備える）

公開 API
--------
- :data:`VALID_STATUS_KEYS` — 受け付け可能な status_key のタプル
- :func:`load_status` — 1 患者の status_key を取得
- :func:`save_status` — 1 患者の status_key を保存
- :func:`load_all_statuses` — 全患者の status_key を取得
- :func:`clear_status` — 1 患者のステータスを削除（🆕 新規扱い）
- :func:`clear_all_statuses` — 全レコードを削除（週次リセット等）
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Dict, Optional

# リポジトリ内の data/ ディレクトリ
_STORAGE_PATH = Path(__file__).resolve().parent.parent / "data" / "patient_status.json"

# 許容される status_key
# 通常モード 7 種 + 連休対策モード 3 種
# conference_material_view.py の _STATUS_NORMAL / _STATUS_HOLIDAY と一致させる
VALID_STATUS_KEYS: tuple = (
    # 通常モード 7 種
    "new",
    "medical",
    "family",
    "facility",
    "insurance",
    "rehab",
    "undecided",
    # 連休対策モード 3 種
    "before_confirmed",
    "before_adjusting",
    "continuing",
)


def _get_storage_path() -> Path:
    """保存先パスを返す（テストで差し替え可能にするための薄いラッパ）."""
    return _STORAGE_PATH


def load_all_statuses() -> Dict[str, str]:
    """全患者の status_key を ``{uuid_prefix: status_key}`` の dict で返す.

    Returns
    -------
    dict
        UUID 先頭 8 桁をキーに、status_key（str）を値とする dict。
        ファイル欠損・破損時は空 dict を返す。

    Notes
    -----
    - 値が str でないエントリや、``VALID_STATUS_KEYS`` にない値は除外する
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
    cleaned: Dict[str, str] = {}
    for key, value in data.items():
        if not isinstance(key, str):
            continue
        if not isinstance(value, str):
            continue
        if value not in VALID_STATUS_KEYS:
            # 未知の status_key は無視（スキーマ変更に対する堅牢化）
            continue
        cleaned[key] = value
    return cleaned


def load_status(patient_uuid_prefix: str) -> Optional[str]:
    """1 患者の status_key を返す.

    Parameters
    ----------
    patient_uuid_prefix : str
        UUID 先頭 8 桁（``SamplePatient.patient_id`` と同じ）

    Returns
    -------
    str or None
        該当 UUID の status_key、未登録なら ``None``。
    """
    all_statuses = load_all_statuses()
    return all_statuses.get(patient_uuid_prefix)


def save_status(patient_uuid_prefix: str, status_key: str) -> None:
    """1 患者の status_key を保存する（既存ファイルがあればマージ）.

    Parameters
    ----------
    patient_uuid_prefix : str
        UUID 先頭 8 桁
    status_key : str
        ``VALID_STATUS_KEYS`` に含まれる status_key 文字列

    Raises
    ------
    ValueError
        ``patient_uuid_prefix`` が空、または ``status_key`` が
        ``VALID_STATUS_KEYS`` にない場合。

    Notes
    -----
    - 保存先の親ディレクトリがなければ自動作成する
    - Atomic write: 同一ディレクトリの tempfile に書き、``os.replace`` で差し替える
    - 既存の全エントリを保持したまま、該当キーだけを上書きする
    - UTF-8 固定、``ensure_ascii=False`` で将来の拡張に備える
    """
    if not patient_uuid_prefix:
        raise ValueError("patient_uuid_prefix は空にできません")
    if status_key not in VALID_STATUS_KEYS:
        raise ValueError(
            f"status_key '{status_key}' は VALID_STATUS_KEYS に含まれません: "
            f"{VALID_STATUS_KEYS}"
        )

    all_statuses = load_all_statuses()
    all_statuses[patient_uuid_prefix] = status_key

    path = _get_storage_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write: 同ディレクトリに tempfile を作り、fsync してから rename
    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix=".patient_status_",
        suffix=".json.tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(all_statuses, fh, ensure_ascii=False, indent=2)
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


def clear_status(patient_uuid_prefix: str) -> None:
    """指定患者のステータスを削除（🆕 新規扱いに戻す）.

    Parameters
    ----------
    patient_uuid_prefix : str
        UUID 先頭 8 桁

    Notes
    -----
    - 対象 UUID がストアに存在しない場合は何もしない
    - ストアファイル自体が存在しない場合も何もしない
    - 削除後、ストアが空になった場合もファイルは残す（新規書き込みで空辞書になる）
    """
    if not patient_uuid_prefix:
        raise ValueError("patient_uuid_prefix は空にできません")

    all_statuses = load_all_statuses()
    if patient_uuid_prefix not in all_statuses:
        return
    del all_statuses[patient_uuid_prefix]

    path = _get_storage_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix=".patient_status_",
        suffix=".json.tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(all_statuses, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def clear_all_statuses() -> int:
    """全レコードを削除する（週次リセット等）.

    Returns
    -------
    int
        削除されたエントリ件数。ファイルが存在しなければ 0。

    Notes
    -----
    - 保存ファイルが存在しなければ何もしない（0 を返す）
    - 削除できない場合は ``OSError`` をそのまま伝播
    """
    path = _get_storage_path()
    if not path.exists():
        return 0
    # 削除前の件数を取得
    count = len(load_all_statuses())
    path.unlink()
    return count


__all__ = [
    "VALID_STATUS_KEYS",
    "load_all_statuses",
    "load_status",
    "save_status",
    "clear_status",
    "clear_all_statuses",
]
