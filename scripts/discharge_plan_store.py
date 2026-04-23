"""患者ごとの退院予定情報の永続化ストア.

退院カレンダー機能で使う「退院予定日」「退院決定フラグ」「突発退院フラグ」を
患者の UUID 先頭 8 桁をキーに JSON ファイルで管理する。

病棟情報や氏名情報はここには含めず、表示側で患者データフレームと join する。
``patient_status_store`` の 7 段階ステータスとは独立したストアで、
同じ UUID をキーに結合される。

保存先
-------
- ``data/discharge_plans.json`` — 現在の退院予定（``{uuid: plan_dict}``）

フォーマット
-------------
::

    {
        "a1b2c3d4": {
            "scheduled_date": "2026-04-25",   # 退院予定日（ISO 文字列 or None）
            "confirmed": false,                # 退院決定フラグ
            "unplanned": false,                # 突発退院マーカー（主治医独断で決まった退院）
            "updated_at": "2026-04-23T10:00:00"  # 最終更新タイムスタンプ
        },
        ...
    }

設計上の方針
-------------
- **個人情報ではない** が、運用データなので ``.gitignore`` で除外する
  （``data/discharge_plans.json`` を ``.gitignore`` に追加すること）
- **Atomic write**: tempfile + ``os.replace`` で書き込み途中の破損を防ぐ
- **JSON 破損時**: 空辞書扱い（次回保存で上書き）
- **UTF-8 固定**
- **調整開始日は保持しない** — ``get_coordination_start_date()`` が
  ``patient_status_history`` から自動算出する（単一ソース原則）

公開 API
--------
- :func:`load_plan` — 1 患者の退院予定を取得
- :func:`save_plan` — 1 患者の退院予定を保存
- :func:`clear_plan` — 1 患者の退院予定を削除
- :func:`load_all_plans` — 全患者の退院予定を取得
- :func:`clear_all_plans` — 全レコードを削除（週次リセット等）
- :func:`get_coordination_start_date` — 調整開始日を status 履歴から算出
- :func:`get_plans_for_date` — 指定日に退院予定の患者 UUID 一覧を取得
- :func:`get_plans_in_range` — 日付範囲内の退院予定を取得
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# リポジトリ内の data/ ディレクトリ
_STORAGE_PATH = Path(__file__).resolve().parent.parent / "data" / "discharge_plans.json"


def _get_storage_path() -> Path:
    """保存先パスを返す（テストで差し替え可能にするための薄いラッパ）."""
    return _STORAGE_PATH


def _atomic_write_json(path: Path, data: Any) -> None:
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
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix=".discharge_plans_",
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


def _is_valid_plan(plan: Any) -> bool:
    """plan dict のスキーマ検証（破損データを弾く）."""
    if not isinstance(plan, dict):
        return False
    # scheduled_date: None または ISO 日付文字列
    sd = plan.get("scheduled_date")
    if sd is not None:
        if not isinstance(sd, str):
            return False
        try:
            date.fromisoformat(sd)
        except ValueError:
            return False
    # confirmed / unplanned: bool
    if not isinstance(plan.get("confirmed", False), bool):
        return False
    if not isinstance(plan.get("unplanned", False), bool):
        return False
    return True


def load_all_plans() -> Dict[str, Dict[str, Any]]:
    """全患者の退院予定を ``{uuid_prefix: plan_dict}`` の dict で返す.

    Returns
    -------
    dict
        UUID 先頭 8 桁をキーに、plan_dict を値とする dict。
        ファイル欠損・破損時は空 dict を返す。

    Notes
    -----
    - 値がスキーマに合わないエントリは除外する
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
    cleaned: Dict[str, Dict[str, Any]] = {}
    for key, value in data.items():
        if not isinstance(key, str):
            continue
        if not _is_valid_plan(value):
            continue
        cleaned[key] = {
            "scheduled_date": value.get("scheduled_date"),
            "confirmed": bool(value.get("confirmed", False)),
            "unplanned": bool(value.get("unplanned", False)),
            "updated_at": value.get("updated_at", ""),
        }
    return cleaned


def load_plan(patient_uuid_prefix: str) -> Optional[Dict[str, Any]]:
    """1 患者の退院予定を返す.

    Parameters
    ----------
    patient_uuid_prefix : str
        UUID 先頭 8 桁

    Returns
    -------
    dict or None
        ``{"scheduled_date": str|None, "confirmed": bool, "unplanned": bool,
        "updated_at": str}``。未登録なら ``None``。
    """
    if not patient_uuid_prefix:
        return None
    all_plans = load_all_plans()
    return all_plans.get(patient_uuid_prefix)


def save_plan(
    patient_uuid_prefix: str,
    scheduled_date: Optional[date] = None,
    confirmed: bool = False,
    unplanned: bool = False,
    now: Optional[datetime] = None,
) -> None:
    """1 患者の退院予定を保存する.

    Parameters
    ----------
    patient_uuid_prefix : str
        UUID 先頭 8 桁
    scheduled_date : date, optional
        退院予定日。None なら予定日なし（調整中のみ）。
    confirmed : bool, default False
        退院決定フラグ。True なら確定した退院予定。
    unplanned : bool, default False
        突発退院マーカー。True なら「主治医独断で決まった退院」を意味し、
        枠超過判定や主治医別頻度集計に使う。
    now : datetime, optional
        現在時刻（テスト用注入）。

    Raises
    ------
    ValueError
        ``patient_uuid_prefix`` が空の場合。

    Notes
    -----
    - 既存の全エントリを保持したまま、該当キーだけを上書きする
    - Atomic write で書き込み途中の破損を防ぐ
    """
    if not patient_uuid_prefix:
        raise ValueError("patient_uuid_prefix は空にできません")

    current = now if now is not None else datetime.now()
    plan: Dict[str, Any] = {
        "scheduled_date": scheduled_date.isoformat() if scheduled_date else None,
        "confirmed": bool(confirmed),
        "unplanned": bool(unplanned),
        "updated_at": current.isoformat(timespec="seconds"),
    }
    all_plans = load_all_plans()
    all_plans[patient_uuid_prefix] = plan

    path = _get_storage_path()
    _atomic_write_json(path, all_plans)


def clear_plan(patient_uuid_prefix: str) -> None:
    """指定患者の退院予定を削除する.

    Parameters
    ----------
    patient_uuid_prefix : str
        UUID 先頭 8 桁

    Notes
    -----
    - 対象 UUID がストアに存在しない場合は何もしない
    """
    if not patient_uuid_prefix:
        raise ValueError("patient_uuid_prefix は空にできません")

    all_plans = load_all_plans()
    if patient_uuid_prefix not in all_plans:
        return
    del all_plans[patient_uuid_prefix]

    path = _get_storage_path()
    _atomic_write_json(path, all_plans)


def clear_all_plans() -> int:
    """全レコードを削除する.

    Returns
    -------
    int
        削除されたエントリ件数。ファイルが存在しなければ 0。
    """
    path = _get_storage_path()
    if not path.exists():
        return 0
    count = len(load_all_plans())
    path.unlink()
    return count


def get_plans_for_date(target_date: date) -> List[str]:
    """指定日に退院予定の患者 UUID 一覧を返す.

    Parameters
    ----------
    target_date : date
        対象日

    Returns
    -------
    list of str
        該当日に ``scheduled_date`` が設定されている患者の UUID 先頭 8 桁。
        順序は不定（呼び出し側でソートする）。
    """
    target_str = target_date.isoformat()
    return [
        uuid for uuid, plan in load_all_plans().items()
        if plan.get("scheduled_date") == target_str
    ]


def get_plans_in_range(
    start_date: date,
    end_date: date,
) -> Dict[str, List[str]]:
    """日付範囲内の退院予定を ``{date_str: [uuid, ...]}`` で返す.

    Parameters
    ----------
    start_date : date
        範囲開始日（含む）
    end_date : date
        範囲終了日（含む）

    Returns
    -------
    dict
        キーは YYYY-MM-DD 文字列、値は UUID 先頭 8 桁のリスト。
        該当日がない日は辞書に含めない（呼び出し側で defaultdict 等を使う）。
    """
    if start_date > end_date:
        raise ValueError("start_date は end_date 以下である必要があります")
    result: Dict[str, List[str]] = {}
    for uuid, plan in load_all_plans().items():
        sd_str = plan.get("scheduled_date")
        if not sd_str:
            continue
        try:
            sd = date.fromisoformat(sd_str)
        except ValueError:
            continue
        if start_date <= sd <= end_date:
            result.setdefault(sd_str, []).append(uuid)
    return result


# ---------------------------------------------------------------------------
# 調整開始日の抽出（patient_status_history との結合）
# ---------------------------------------------------------------------------

def get_coordination_start_date(patient_uuid_prefix: str) -> Optional[date]:
    """退院調整開始日を status 履歴から自動算出する.

    「🆕 新規（new）」以外のステータスに最初に変化した時点を
    「退院調整開始」とみなし、その日付を返す。

    Parameters
    ----------
    patient_uuid_prefix : str
        UUID 先頭 8 桁

    Returns
    -------
    date or None
        調整開始日。履歴が空、または全て "new" のままなら ``None``。

    Notes
    -----
    - ``patient_status_store.load_status_history`` を内部で呼び出す
      （循環 import を避けるため関数内 import）
    - "new" 以外（medical/family/facility/insurance/rehab/undecided 等）に
      最初に変わった履歴エントリの ``timestamp`` を日付に変換して返す
    """
    if not patient_uuid_prefix:
        return None
    # 循環 import を避けるために関数内で import
    try:
        from patient_status_store import load_status_history  # type: ignore
    except ImportError:
        # scripts/ 以外から呼ばれた場合のフォールバック
        from scripts.patient_status_store import load_status_history  # type: ignore

    history = load_status_history(patient_uuid_prefix)
    if not history:
        return None
    for entry in history:
        status = entry.get("status", "")
        if status and status != "new":
            ts_str = entry.get("timestamp", "")
            try:
                return datetime.fromisoformat(ts_str).date()
            except (ValueError, TypeError):
                continue
    return None


__all__ = [
    "load_all_plans",
    "load_plan",
    "save_plan",
    "clear_plan",
    "clear_all_plans",
    "get_plans_for_date",
    "get_plans_in_range",
    "get_coordination_start_date",
]
