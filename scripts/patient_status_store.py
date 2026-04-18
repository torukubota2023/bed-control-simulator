"""患者ステータス（カンファ区分）の永続化ストア.

多職種退院調整カンファ画面で更新した患者のステータス
（🆕 新規 / ⚫ 方向性未決 / 🔵 医学的OK待ち / 🟢 家族希望待ち /
🟡 施設待ち / 🟣 介護保険待ち / 🟠 リハ最適化中）を
ローカルの JSON ファイルに保存・復元するための軽量ストア。

保存先
-------
- ``data/patient_status.json`` — 現在ステータス（``{uuid: status}``）
- ``data/patient_status_history.json`` — 週次カンファ履歴（``{uuid: [変化イベント, ...]}``）

現在ステータスのフォーマット
-----------------------------
::

    {
        "a1b2c3d4": "rehab",
        "b2c3d4e5": "new",
        ...
    }

履歴のフォーマット
-------------------
::

    {
        "a1b2c3d4": [
            {"timestamp": "2026-04-11T14:30:00", "status": "new",
             "conference_date": "2026-04-11"},
            {"timestamp": "2026-04-18T14:35:00", "status": "undecided",
             "conference_date": "2026-04-18"},
        ],
        ...
    }

キーは ``SamplePatient.patient_id``（UUID 先頭 8 桁）、値は
``_STATUS_NORMAL`` / ``_STATUS_HOLIDAY`` に含まれる ``key`` 文字列。

許容される status_key の一覧は :data:`VALID_STATUS_KEYS` に集約する。

設計上の方針
-------------
- **個人情報ではない**が、ユーザー固有の運用データなので Git 追跡しない
  （``.gitignore`` で ``data/patient_status.json`` / ``data/patient_status_history.json`` を除外する）
- **ファイル欠損時**: ``load_status`` は ``None`` を返す（UI 側で既定値 "new"）
- **Atomic write**: tempfile + ``os.replace`` で書き込み途中の破損を防止
- **JSON 破損時**: 警告せず空辞書扱い（次回保存で上書きされる）
- **UTF-8 固定**: BMP 文字（status_key は ASCII だが将来拡張に備える）
- **履歴は変化時のみ追記**: 同じステータスで連続保存しても履歴は肥大化させない
- **履歴は後方互換**: 既存の現在ステータスの保存・読み込み挙動は変更しない

公開 API
--------
- :data:`VALID_STATUS_KEYS` — 受け付け可能な status_key のタプル
- :func:`load_status` — 1 患者の status_key を取得
- :func:`save_status` — 1 患者の status_key を保存（変化時のみ履歴追記）
- :func:`load_all_statuses` — 全患者の status_key を取得
- :func:`clear_status` — 1 患者のステータスを削除（🆕 新規扱い）
- :func:`clear_all_statuses` — 全レコードを削除（週次リセット等）
- :func:`load_status_history` — 1 患者の履歴（時系列順）
- :func:`load_all_status_history` — 全患者の履歴（集計用）
- :func:`get_status_changes_this_week` — 今週のステータス変化
- :func:`get_status_transitions` — 遷移ペアのリスト
- :func:`get_stagnant_patients` — 一定週数以上ステータスが変わらない患者
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# リポジトリ内の data/ ディレクトリ
_STORAGE_PATH = Path(__file__).resolve().parent.parent / "data" / "patient_status.json"
_HISTORY_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "patient_status_history.json"
)

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


def _get_history_path() -> Path:
    """履歴ファイルパスを返す（テストで差し替え可能にするための薄いラッパ）."""
    return _HISTORY_PATH


def _atomic_write_json(path: Path, data) -> None:
    """JSON を atomic に書き込む（tempfile + os.replace）.

    Parameters
    ----------
    path : Path
        書き込み先ファイルパス
    data : Any
        ``json.dump`` で書き出せる Python オブジェクト

    Notes
    -----
    - 親ディレクトリは自動作成する
    - 失敗時は tempfile を掃除し、例外を再送出する
    - 既存ファイルは ``os.replace`` まで無傷に保たれる（途中破損しない）
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix=".patient_status_",
        suffix=".json.tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


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
    """1 患者の status_key を保存する（既存ファイルがあればマージ、変化時は履歴追記）.

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
    - **履歴追記は変化があった場合のみ** — 同じ status を連続保存しても履歴は肥大化させない
    - 履歴書き込みの失敗は現在ステータス保存を阻害しない（warn せず握りつぶす）
    """
    if not patient_uuid_prefix:
        raise ValueError("patient_uuid_prefix は空にできません")
    if status_key not in VALID_STATUS_KEYS:
        raise ValueError(
            f"status_key '{status_key}' は VALID_STATUS_KEYS に含まれません: "
            f"{VALID_STATUS_KEYS}"
        )

    all_statuses = load_all_statuses()
    previous_status = all_statuses.get(patient_uuid_prefix)
    all_statuses[patient_uuid_prefix] = status_key

    path = _get_storage_path()
    _atomic_write_json(path, all_statuses)

    # 履歴: 変化があった場合のみ追記（新規 or status 変化）
    # 同ステータスの連続保存は履歴を肥大化させない
    if previous_status != status_key:
        try:
            _append_history_entry(patient_uuid_prefix, status_key)
        except (OSError, ValueError):
            # 履歴書き込み失敗時も UI 側の現状更新は維持
            pass


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
    _atomic_write_json(path, all_statuses)


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



# ---------------------------------------------------------------------------
# 履歴（週次カンファごとのステータス変化記録）
# ---------------------------------------------------------------------------

def load_all_status_history() -> Dict[str, List[Dict[str, str]]]:
    """全患者の履歴を ``{uuid_prefix: [entry, ...]}`` の dict で返す.

    Returns
    -------
    dict
        UUID 先頭 8 桁をキーに、履歴エントリ（dict）のリストを値とする dict。
        各エントリは ``{"timestamp": ISO, "status": status_key, "conference_date": YYYY-MM-DD}``。
        ファイル欠損・破損時は空 dict を返す。

    Notes
    -----
    - 値が list でないエントリは除外する
    - 各エントリについて、status が ``VALID_STATUS_KEYS`` にあるもののみ保持
    - ``timestamp`` / ``conference_date`` のパースは行わない（呼び出し側で扱う）
    """
    path = _get_history_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    cleaned: Dict[str, List[Dict[str, str]]] = {}
    for key, entries in data.items():
        if not isinstance(key, str):
            continue
        if not isinstance(entries, list):
            continue
        cleaned_entries: List[Dict[str, str]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            status = entry.get("status")
            if not isinstance(status, str) or status not in VALID_STATUS_KEYS:
                continue
            ts = entry.get("timestamp")
            if not isinstance(ts, str):
                continue
            # conference_date は任意（省略可）
            new_entry: Dict[str, str] = {"timestamp": ts, "status": status}
            cdate = entry.get("conference_date")
            if isinstance(cdate, str):
                new_entry["conference_date"] = cdate
            cleaned_entries.append(new_entry)
        if cleaned_entries:
            cleaned[key] = cleaned_entries
    return cleaned


def load_status_history(patient_uuid_prefix: str) -> List[Dict[str, str]]:
    """1 患者の履歴を時系列順（古い順）に返す.

    Parameters
    ----------
    patient_uuid_prefix : str
        UUID 先頭 8 桁

    Returns
    -------
    list of dict
        ``[{"timestamp": ..., "status": ..., "conference_date": ...}, ...]``。
        該当 UUID の履歴がなければ空リスト。
        ``timestamp`` で昇順ソート済み。
    """
    if not patient_uuid_prefix:
        return []
    all_history = load_all_status_history()
    entries = all_history.get(patient_uuid_prefix, [])
    # timestamp 文字列で昇順ソート（ISO 形式なので文字列比較で時系列順になる）
    return sorted(entries, key=lambda e: e.get("timestamp", ""))


def _append_history_entry(
    patient_uuid_prefix: str,
    status_key: str,
    now: Optional[datetime] = None,
) -> None:
    """履歴に 1 件追記する（内部用 — 変化時のみ呼ばれる）.

    Parameters
    ----------
    patient_uuid_prefix : str
        UUID 先頭 8 桁
    status_key : str
        ``VALID_STATUS_KEYS`` に含まれる status_key
    now : datetime, optional
        現在時刻（テスト用注入）。None なら ``datetime.now()``。

    Notes
    -----
    - conference_date は ``now`` の date 部分を YYYY-MM-DD 文字列で記録
    - Atomic write を使って既存履歴を壊さない
    """
    if status_key not in VALID_STATUS_KEYS:
        raise ValueError(
            f"status_key '{status_key}' は VALID_STATUS_KEYS に含まれません"
        )
    current = now if now is not None else datetime.now()
    entry: Dict[str, str] = {
        "timestamp": current.isoformat(timespec="seconds"),
        "status": status_key,
        "conference_date": current.date().isoformat(),
    }
    all_history = load_all_status_history()
    all_history.setdefault(patient_uuid_prefix, []).append(entry)

    path = _get_history_path()
    _atomic_write_json(path, all_history)


def get_status_changes_this_week(
    reference_date: date,
    days: int = 7,
) -> List[Dict[str, str]]:
    """指定日から直近 ``days`` 日以内のステータス変化を集計する.

    Parameters
    ----------
    reference_date : date
        基準日（通常は今日）。この日から過去 ``days`` 日以内の変化を拾う。
    days : int, default 7
        遡る日数（デフォルト 1 週間）。

    Returns
    -------
    list of dict
        各エントリは ``{"uuid": ..., "from_status": ..., "to_status": ...,
        "timestamp": ..., "conference_date": ...}``。
        ``from_status`` は「その変化イベントの 1 つ手前」、``to_status`` は変化後。
        履歴の最初のエントリ（初登場）では ``from_status`` は None。
        時系列（古い順）でソートされる。
    """
    if days < 0:
        raise ValueError("days は 0 以上の整数")
    window_start = reference_date - timedelta(days=days)
    all_history = load_all_status_history()
    changes: List[Dict[str, str]] = []
    for uuid, entries in all_history.items():
        sorted_entries = sorted(entries, key=lambda e: e.get("timestamp", ""))
        for i, entry in enumerate(sorted_entries):
            ts_str = entry.get("timestamp", "")
            try:
                ts_date = datetime.fromisoformat(ts_str).date()
            except (ValueError, TypeError):
                continue
            # window_start <= ts_date <= reference_date
            if ts_date < window_start or ts_date > reference_date:
                continue
            from_status: Optional[str] = None
            if i > 0:
                from_status = sorted_entries[i - 1].get("status")
            change: Dict[str, str] = {
                "uuid": uuid,
                "from_status": from_status if from_status is not None else "",
                "to_status": entry.get("status", ""),
                "timestamp": ts_str,
            }
            cdate = entry.get("conference_date")
            if isinstance(cdate, str):
                change["conference_date"] = cdate
            changes.append(change)
    changes.sort(key=lambda c: c.get("timestamp", ""))
    return changes


def get_status_transitions(patient_uuid_prefix: str) -> List[Tuple[str, str]]:
    """そのまま変化した遷移ペア: ``[(new → undecided), (undecided → family), ...]``.

    Parameters
    ----------
    patient_uuid_prefix : str
        UUID 先頭 8 桁

    Returns
    -------
    list of tuple
        ``[(from_status, to_status), ...]`` の時系列順リスト。
        履歴が 2 件未満なら空リスト（遷移が発生していないため）。
    """
    history = load_status_history(patient_uuid_prefix)
    if len(history) < 2:
        return []
    transitions: List[Tuple[str, str]] = []
    for i in range(1, len(history)):
        prev = history[i - 1].get("status", "")
        curr = history[i].get("status", "")
        if prev and curr:
            transitions.append((prev, curr))
    return transitions


def get_stagnant_patients(
    reference_date: date,
    weeks: int = 3,
) -> List[Dict[str, str]]:
    """指定週数以上ステータスが変わらない患者を洗い出す.

    Parameters
    ----------
    reference_date : date
        基準日（通常は今日）
    weeks : int, default 3
        この週数以上、最新履歴から変化がない患者を「停滞」とみなす

    Returns
    -------
    list of dict
        ``[{"uuid": ..., "status": ..., "last_changed": ISO date,
        "weeks_stagnant": float}, ...]``。
        ``weeks_stagnant`` は最新履歴からの経過週数（小数）。
        履歴が 1 件もない患者は含めない（変化のトラッキング対象外）。
    """
    if weeks < 0:
        raise ValueError("weeks は 0 以上の整数")
    threshold_days = weeks * 7
    all_history = load_all_status_history()
    stagnant: List[Dict[str, str]] = []
    for uuid, entries in all_history.items():
        if not entries:
            continue
        sorted_entries = sorted(entries, key=lambda e: e.get("timestamp", ""))
        latest = sorted_entries[-1]
        ts_str = latest.get("timestamp", "")
        try:
            latest_date = datetime.fromisoformat(ts_str).date()
        except (ValueError, TypeError):
            continue
        days_since = (reference_date - latest_date).days
        if days_since >= threshold_days:
            stagnant.append({
                "uuid": uuid,
                "status": latest.get("status", ""),
                "last_changed": latest_date.isoformat(),
                "weeks_stagnant": f"{days_since / 7:.1f}",
            })
    stagnant.sort(key=lambda s: float(s.get("weeks_stagnant", "0")), reverse=True)
    return stagnant


def clear_all_history() -> int:
    """履歴を全削除する（テスト用・週次リセット等）.

    Returns
    -------
    int
        削除された患者数。ファイルが存在しなければ 0。
    """
    path = _get_history_path()
    if not path.exists():
        return 0
    count = len(load_all_status_history())
    path.unlink()
    return count


__all__ = [
    "VALID_STATUS_KEYS",
    "load_all_statuses",
    "load_status",
    "save_status",
    "clear_status",
    "clear_all_statuses",
    "load_all_status_history",
    "load_status_history",
    "get_status_changes_this_week",
    "get_status_transitions",
    "get_stagnant_patients",
    "clear_all_history",
]
