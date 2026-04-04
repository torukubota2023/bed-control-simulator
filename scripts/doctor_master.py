"""
医師・スタッフマスタ管理モジュール

おもろまちメディカルセンターのベッドコントロールシミュレーター用
医師マスタおよび入院創出元（入院経路含む）を管理する。

個人情報は一切含めない（氏名は表示名のみ）。
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# 定数定義
# ---------------------------------------------------------------------------

# 医師カテゴリ
DOCTOR_CATEGORIES = ["常勤病棟担当", "常勤外来のみ", "非常勤", "常勤救急応援"]

# 入院創出元タイプ
ADMISSION_SOURCE_TYPES = ["医師", "部署", "経路"]

# デフォルト入院経路（初回セットアップ時に自動登録）
DEFAULT_ADMISSION_ROUTES = ["外来紹介", "救急", "連携室", "ウォークイン"]

# データ保存先
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DOCTOR_MASTER_CSV = DATA_DIR / "doctor_master.csv"
ADMISSION_ROUTES_CSV = DATA_DIR / "admission_routes.csv"

# DataFrameカラム定義
DOCTOR_COLUMNS = ["id", "name", "category", "active"]
ADMISSION_SOURCE_COLUMNS = ["id", "name", "type", "doctor_id", "active"]

# ---------------------------------------------------------------------------
# 内部ストア（モジュール内キャッシュ）
# ---------------------------------------------------------------------------

_doctor_df: Optional[pd.DataFrame] = None
_admission_source_df: Optional[pd.DataFrame] = None


# ---------------------------------------------------------------------------
# CSV永続化（ロード / セーブ）
# ---------------------------------------------------------------------------

def _load_doctors() -> pd.DataFrame:
    """医師マスタCSVを読み込む。ファイルが無ければ空DataFrameを返す。"""
    global _doctor_df
    if DOCTOR_MASTER_CSV.exists():
        _doctor_df = pd.read_csv(DOCTOR_MASTER_CSV, dtype=str)
        # active列をboolに変換
        _doctor_df["active"] = _doctor_df["active"].map(
            {"True": True, "true": True, "1": True}
        ).fillna(False)
    else:
        _doctor_df = pd.DataFrame(columns=DOCTOR_COLUMNS)
        _doctor_df["active"] = _doctor_df["active"].astype(bool)
    return _doctor_df


def _save_doctors() -> None:
    """医師マスタをCSVに保存する。"""
    global _doctor_df
    if _doctor_df is None:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _doctor_df.to_csv(DOCTOR_MASTER_CSV, index=False)


def _load_admission_sources() -> pd.DataFrame:
    """入院創出元CSVを読み込む。ファイルが無ければデフォルト経路で初期化する。"""
    global _admission_source_df
    if ADMISSION_ROUTES_CSV.exists():
        _admission_source_df = pd.read_csv(ADMISSION_ROUTES_CSV, dtype=str)
        _admission_source_df["active"] = _admission_source_df["active"].map(
            {"True": True, "true": True, "1": True}
        ).fillna(False)
    else:
        # デフォルト経路で初期化
        rows = []
        for route_name in DEFAULT_ADMISSION_ROUTES:
            rows.append({
                "id": str(uuid.uuid4()),
                "name": route_name,
                "type": "経路",
                "doctor_id": "",
                "active": True,
            })
        _admission_source_df = pd.DataFrame(rows, columns=ADMISSION_SOURCE_COLUMNS)
        _save_admission_sources()
    return _admission_source_df


def _save_admission_sources() -> None:
    """入院創出元をCSVに保存する。"""
    global _admission_source_df
    if _admission_source_df is None:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _admission_source_df.to_csv(ADMISSION_ROUTES_CSV, index=False)


def _get_doctor_df() -> pd.DataFrame:
    """医師DataFrameを取得（未ロードならロード）。"""
    global _doctor_df
    if _doctor_df is None:
        _load_doctors()
    return _doctor_df


def _get_admission_source_df() -> pd.DataFrame:
    """入院創出元DataFrameを取得（未ロードならロード）。"""
    global _admission_source_df
    if _admission_source_df is None:
        _load_admission_sources()
    return _admission_source_df


# ---------------------------------------------------------------------------
# 医師CRUD
# ---------------------------------------------------------------------------

def add_doctor(name: str, category: str) -> dict:
    """
    医師を追加する。

    Parameters
    ----------
    name : str
        表示名（例: "田中先生"）
    category : str
        カテゴリ（DOCTOR_CATEGORIES のいずれか）

    Returns
    -------
    dict
        追加された医師レコード
    """
    if category not in DOCTOR_CATEGORIES:
        raise ValueError(
            f"無効なカテゴリ: {category}。"
            f"有効な値: {DOCTOR_CATEGORIES}"
        )

    df = _get_doctor_df()
    new_record = {
        "id": str(uuid.uuid4()),
        "name": name,
        "category": category,
        "active": True,
    }
    new_row = pd.DataFrame([new_record])
    global _doctor_df
    _doctor_df = pd.concat([df, new_row], ignore_index=True)
    _save_doctors()

    # 対応する入院創出元も自動登録
    add_admission_source(name=name, source_type="医師", doctor_id=new_record["id"])

    return new_record


def update_doctor(doctor_id: str, updates: dict) -> dict:
    """
    医師情報を更新する。

    Parameters
    ----------
    doctor_id : str
        対象医師のID
    updates : dict
        更新するフィールドと値（例: {"name": "新名前", "category": "非常勤"}）

    Returns
    -------
    dict
        更新後の医師レコード
    """
    df = _get_doctor_df()
    mask = df["id"] == doctor_id
    if not mask.any():
        raise ValueError(f"医師ID {doctor_id} が見つかりません。")

    # カテゴリのバリデーション
    if "category" in updates and updates["category"] not in DOCTOR_CATEGORIES:
        raise ValueError(
            f"無効なカテゴリ: {updates['category']}。"
            f"有効な値: {DOCTOR_CATEGORIES}"
        )

    # idは変更不可
    updates.pop("id", None)

    for key, value in updates.items():
        if key in DOCTOR_COLUMNS:
            df.loc[mask, key] = value

    global _doctor_df
    _doctor_df = df
    _save_doctors()

    return df.loc[mask].iloc[0].to_dict()


def deactivate_doctor(doctor_id: str) -> bool:
    """
    医師を論理削除（非アクティブ化）する。

    Parameters
    ----------
    doctor_id : str
        対象医師のID

    Returns
    -------
    bool
        成功ならTrue
    """
    df = _get_doctor_df()
    mask = df["id"] == doctor_id
    if not mask.any():
        raise ValueError(f"医師ID {doctor_id} が見つかりません。")

    df.loc[mask, "active"] = False
    global _doctor_df
    _doctor_df = df
    _save_doctors()

    # 対応する入院創出元も非アクティブ化
    src_df = _get_admission_source_df()
    src_mask = (src_df["doctor_id"] == doctor_id)
    if src_mask.any():
        src_df.loc[src_mask, "active"] = False
        global _admission_source_df
        _admission_source_df = src_df
        _save_admission_sources()

    return True


def get_active_doctors() -> list[dict]:
    """アクティブな医師一覧を返す。"""
    df = _get_doctor_df()
    active = df[df["active"] == True]  # noqa: E712
    return active.to_dict("records")


def get_doctors_by_category(category: str) -> list[dict]:
    """
    指定カテゴリのアクティブな医師一覧を返す。

    Parameters
    ----------
    category : str
        フィルタするカテゴリ
    """
    if category not in DOCTOR_CATEGORIES:
        raise ValueError(
            f"無効なカテゴリ: {category}。"
            f"有効な値: {DOCTOR_CATEGORIES}"
        )
    df = _get_doctor_df()
    filtered = df[(df["category"] == category) & (df["active"] == True)]  # noqa: E712
    return filtered.to_dict("records")


# ---------------------------------------------------------------------------
# 入院創出元CRUD
# ---------------------------------------------------------------------------

def add_admission_source(
    name: str,
    source_type: str,
    doctor_id: Optional[str] = None,
) -> dict:
    """
    入院創出元を追加する。

    Parameters
    ----------
    name : str
        表示名
    source_type : str
        タイプ（"医師", "部署", "経路"）
    doctor_id : str, optional
        医師IDへのリンク（typeが"医師"の場合）

    Returns
    -------
    dict
        追加されたレコード
    """
    if source_type not in ADMISSION_SOURCE_TYPES:
        raise ValueError(
            f"無効なタイプ: {source_type}。"
            f"有効な値: {ADMISSION_SOURCE_TYPES}"
        )

    df = _get_admission_source_df()
    new_record = {
        "id": str(uuid.uuid4()),
        "name": name,
        "type": source_type,
        "doctor_id": doctor_id or "",
        "active": True,
    }
    new_row = pd.DataFrame([new_record])
    global _admission_source_df
    _admission_source_df = pd.concat([df, new_row], ignore_index=True)
    _save_admission_sources()

    return new_record


def get_admission_routes() -> list[str]:
    """アクティブな入院経路名の一覧を返す。"""
    df = _get_admission_source_df()
    routes = df[(df["type"] == "経路") & (df["active"] == True)]  # noqa: E712
    return routes["name"].tolist()


def add_admission_route(name: str) -> bool:
    """
    入院経路を追加する。

    Parameters
    ----------
    name : str
        経路名

    Returns
    -------
    bool
        成功ならTrue（既に存在する場合はFalse）
    """
    existing = get_admission_routes()
    if name in existing:
        return False

    add_admission_source(name=name, source_type="経路")
    return True


def remove_admission_route(name: str) -> bool:
    """
    入院経路を論理削除する。

    Parameters
    ----------
    name : str
        経路名

    Returns
    -------
    bool
        成功ならTrue（見つからない場合はFalse）
    """
    df = _get_admission_source_df()
    mask = (df["type"] == "経路") & (df["name"] == name) & (df["active"] == True)  # noqa: E712
    if not mask.any():
        return False

    df.loc[mask, "active"] = False
    global _admission_source_df
    _admission_source_df = df
    _save_admission_sources()
    return True


# ---------------------------------------------------------------------------
# Streamlit表示用ヘルパー
# ---------------------------------------------------------------------------

def get_doctor_display_options() -> dict[str, list[str]]:
    """
    医師をカテゴリ別にグループ化して返す（Streamlit selectbox/dropdown用）。

    Returns
    -------
    dict
        {"常勤病棟担当": ["A先生", "B先生"], "常勤外来のみ": [...], ...}
    """
    result: dict[str, list[str]] = {}
    for category in DOCTOR_CATEGORIES:
        doctors = get_doctors_by_category(category)
        names = [d["name"] for d in doctors]
        if names:
            result[category] = names
    return result


def get_admission_source_options() -> dict[str, list[str]]:
    """
    入院創出元をグループ化して返す（Streamlit dropdown用）。

    医師はカテゴリ別、経路・部署はその他経路としてまとめる。

    Returns
    -------
    dict
        {"── 常勤病棟担当 ──": [...], "── その他経路 ──": ["連携室", ...]}
    """
    result: dict[str, list[str]] = {}

    # 医師をカテゴリ別に追加
    for category in DOCTOR_CATEGORIES:
        doctors = get_doctors_by_category(category)
        names = [d["name"] for d in doctors]
        if names:
            result[f"── {category} ──"] = names

    # 経路・部署をまとめる
    df = _get_admission_source_df()
    other = df[
        (df["type"].isin(["経路", "部署"]))
        & (df["active"] == True)  # noqa: E712
    ]
    other_names = other["name"].tolist()
    if other_names:
        result["── その他経路 ──"] = other_names

    return result


# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------

def reload() -> None:
    """キャッシュをクリアしてCSVから再読み込みする。"""
    global _doctor_df, _admission_source_df
    _doctor_df = None
    _admission_source_df = None
    _load_doctors()
    _load_admission_sources()


def get_doctor_by_id(doctor_id: str) -> Optional[dict]:
    """IDで医師を検索する。見つからなければNoneを返す。"""
    df = _get_doctor_df()
    mask = df["id"] == doctor_id
    if not mask.any():
        return None
    return df.loc[mask].iloc[0].to_dict()


def get_doctor_by_name(name: str) -> Optional[dict]:
    """表示名で医師を検索する（アクティブのみ）。見つからなければNoneを返す。"""
    df = _get_doctor_df()
    mask = (df["name"] == name) & (df["active"] == True)  # noqa: E712
    if not mask.any():
        return None
    return df.loc[mask].iloc[0].to_dict()
