"""データ純度ガード — 院内LAN導入前の本番/デモ混入防止.

副院長指示 (2026-05-01): 院内LAN導入直前の最終確認として、
admission_details.csv にデモデータ（A医師〜J医師）と実データ（実医師コード
KJJ/HAYT 等）が混在するリスクをゼロにする。

主要機能:
- detect_data_kind(df): demo / real / mixed / empty を判定
- archive_demo_data(): デモCSVを data/archive/ にタイムスタンプ付きで退避
- create_empty_schema(): 空のスキーマ（ヘッダーのみ）の admission_details.csv を作成
- find_demo_rows() / find_real_rows(): 行単位の判定（safeguard 用フィルタ）

設計原則:
- 副作用最小（純粋関数中心）
- 既存機能を壊さない（呼び出し側で opt-in）
- 患者個人情報を扱わない（医師名のパターンマッチのみ）
"""
from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterable, Literal

import pandas as pd

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

# デモ医師名パターン（A医師〜J医師の単純なテンプレート）
_DEMO_DOCTOR_PATTERN = re.compile(r"^[A-J]医師$")

# 実医師コード（doctor_specialty_map.py の DOCTOR_SPECIALTY_GROUP と同期）
# 本ファイル単独で動作させるため、ハードコード（同期は CI / テストで担保）
REAL_DOCTOR_CODES: frozenset[str] = frozenset({
    "FKDM", "HAYT", "HIGN", "HIGT", "HOKM", "INOT", "KJJ", "KONA", "KUBT",
    "OHSY", "OKUK", "SIROK", "TAIRK", "TAM", "TATM", "TERUH", "UEMH",
})

DataKind = Literal["demo", "real", "mixed", "empty", "unknown"]

# CSV ヘッダー（admission_details.csv の正規スキーマ）
ADMISSION_DETAILS_COLUMNS: list[str] = [
    "id", "date", "ward", "event_type", "route",
    "source_doctor", "attending_doctor",
    "los_days", "phase", "short3_type",
]

DEFAULT_DETAILS_CSV = Path("data/admission_details.csv")
DEFAULT_ARCHIVE_DIR = Path("data/archive")


# ---------------------------------------------------------------------------
# 判定関数
# ---------------------------------------------------------------------------

def is_demo_doctor(name: object) -> bool:
    """デモ医師名（A医師〜J医師）かどうか判定."""
    if not isinstance(name, str):
        return False
    return bool(_DEMO_DOCTOR_PATTERN.match(name.strip()))


def is_real_doctor(code: object) -> bool:
    """実医師コードかどうか判定."""
    if not isinstance(code, str):
        return False
    return code.strip() in REAL_DOCTOR_CODES


def _classify_doctor_value(value: object) -> str:
    """医師列の1値を 'demo' / 'real' / 'unknown' / 'empty' に分類."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "empty"
    if not isinstance(value, str) or not value.strip():
        return "empty"
    if is_demo_doctor(value):
        return "demo"
    if is_real_doctor(value):
        return "real"
    return "unknown"


def detect_data_kind(df: pd.DataFrame) -> DataKind:
    """DataFrame のデータ種類を判定.

    判定ロジック:
    - 空 DataFrame: "empty"
    - 医師列（attending_doctor / source_doctor）の値を集計
    - 全てが demo: "demo"
    - 全てが real: "real"
    - 両方含む: "mixed"
    - demo/real ともゼロ件: "empty"（ヘッダーのみ等）
    - unknown のみ: "unknown"

    Args:
        df: 判定対象 DataFrame（admission_details.csv の構造想定）

    Returns:
        "demo" / "real" / "mixed" / "empty" / "unknown"
    """
    if df is None or len(df) == 0:
        return "empty"

    candidate_cols = [c for c in ("attending_doctor", "source_doctor") if c in df.columns]
    if not candidate_cols:
        return "unknown"

    has_demo = False
    has_real = False
    has_unknown = False

    for col in candidate_cols:
        for val in df[col].tolist():
            kind = _classify_doctor_value(val)
            if kind == "demo":
                has_demo = True
            elif kind == "real":
                has_real = True
            elif kind == "unknown":
                has_unknown = True

    if has_demo and has_real:
        return "mixed"
    if has_demo:
        return "demo"
    if has_real:
        return "real"
    if has_unknown:
        return "unknown"
    return "empty"


def find_demo_rows(df: pd.DataFrame) -> pd.Series:
    """デモ行（attending_doctor または source_doctor が demo パターン）を bool マスクで返す.

    Returns:
        df の長さの bool Series (True = デモ行)
    """
    if df is None or len(df) == 0:
        return pd.Series(dtype=bool)
    mask = pd.Series(False, index=df.index)
    for col in ("attending_doctor", "source_doctor"):
        if col in df.columns:
            mask = mask | df[col].map(is_demo_doctor).fillna(False)
    return mask


def find_real_rows(df: pd.DataFrame) -> pd.Series:
    """実医師コード行を bool マスクで返す."""
    if df is None or len(df) == 0:
        return pd.Series(dtype=bool)
    mask = pd.Series(False, index=df.index)
    for col in ("attending_doctor", "source_doctor"):
        if col in df.columns:
            mask = mask | df[col].map(is_real_doctor).fillna(False)
    return mask


def filter_real_only(df: pd.DataFrame) -> pd.DataFrame:
    """実データ行のみを残す（safeguard 用、デモ・unknown は除外）.

    Args:
        df: 入力 DataFrame

    Returns:
        実医師コード行のみの DataFrame
    """
    if df is None or len(df) == 0:
        return df
    return df.loc[find_real_rows(df)].copy()


# ---------------------------------------------------------------------------
# アーカイブ・初期化
# ---------------------------------------------------------------------------

def archive_demo_data(
    csv_path: Path | str = DEFAULT_DETAILS_CSV,
    archive_dir: Path | str = DEFAULT_ARCHIVE_DIR,
    *,
    label: str = "demo",
    timestamp: datetime | None = None,
) -> Path:
    """既存 CSV を archive_dir にタイムスタンプ付きで退避.

    例: data/admission_details.csv → data/archive/admission_details_demo_20260501_134500.csv

    Args:
        csv_path: 退避元 CSV パス
        archive_dir: 退避先ディレクトリ（自動作成）
        label: ファイル名ラベル（"demo" / "backup" 等）
        timestamp: 退避時刻（None なら現在時刻）

    Returns:
        退避後のファイルパス

    Raises:
        FileNotFoundError: csv_path が存在しない場合
    """
    csv_path = Path(csv_path)
    archive_dir = Path(archive_dir)
    if not csv_path.exists():
        raise FileNotFoundError(f"退避元ファイルが存在しません: {csv_path}")

    archive_dir.mkdir(parents=True, exist_ok=True)
    ts = (timestamp or datetime.now()).strftime("%Y%m%d_%H%M%S")
    out = archive_dir / f"{csv_path.stem}_{label}_{ts}{csv_path.suffix}"
    shutil.copy2(csv_path, out)
    return out


def create_empty_schema(
    csv_path: Path | str = DEFAULT_DETAILS_CSV,
    columns: Iterable[str] = ADMISSION_DETAILS_COLUMNS,
) -> Path:
    """空スキーマ（ヘッダーのみ）の CSV を作成.

    既存ファイルは上書きされる（呼び出し側が事前に archive_demo_data で退避想定）。

    Args:
        csv_path: 出力先 CSV パス
        columns: 列名リスト（デフォルト: admission_details.csv の正規スキーマ）

    Returns:
        作成したファイルパス
    """
    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(columns=list(columns))
    df.to_csv(csv_path, index=False)
    return csv_path


def initialize_for_production(
    csv_path: Path | str = DEFAULT_DETAILS_CSV,
    archive_dir: Path | str = DEFAULT_ARCHIVE_DIR,
    *,
    timestamp: datetime | None = None,
) -> dict:
    """本番初期化: 既存 CSV を退避し、空スキーマを作成（一括処理）.

    使用想定:
    - 院内LAN導入前に副院長が UI ボタンから呼び出す
    - 1 回のみ実行する想定（複数回呼ぶと退避ファイルが増える）

    Returns:
        dict:
            archived_path: 退避ファイルパス（既存 CSV があった場合）
            created_path: 新規空スキーマパス
            previous_kind: 退避元のデータ種類（"demo" / "real" / "mixed" / "empty"）
            row_count: 退避した行数
    """
    csv_path = Path(csv_path)
    archive_dir = Path(archive_dir)

    # 既存 CSV の状態を記録
    archived_path: Path | None = None
    previous_kind: DataKind = "empty"
    row_count = 0
    if csv_path.exists():
        try:
            df = pd.read_csv(csv_path)
            previous_kind = detect_data_kind(df)
            row_count = len(df)
        except Exception:
            previous_kind = "unknown"
            row_count = -1
        # ラベルを動的に決定（demo の場合だけ "demo"、それ以外は "backup"）
        label = "demo" if previous_kind == "demo" else "backup"
        archived_path = archive_demo_data(
            csv_path, archive_dir, label=label, timestamp=timestamp,
        )

    created_path = create_empty_schema(csv_path)
    return {
        "archived_path": archived_path,
        "created_path": created_path,
        "previous_kind": previous_kind,
        "row_count": row_count,
    }


# ---------------------------------------------------------------------------
# 表示用ヘルパー
# ---------------------------------------------------------------------------

def describe_data_kind(kind: DataKind, *, with_emoji: bool = True) -> str:
    """データ種類のラベル文字列（UI バナー表示用）."""
    table = {
        "real":    ("✅", "実データ", "本番運用中"),
        "demo":    ("⚠️", "デモデータ", "教育用、本番分析には使用しないでください"),
        "mixed":   ("🚨", "デモと実の混在", "至急、本番初期化または手動整理が必要"),
        "empty":   ("📭", "空（未入力）", "日次データを入力してください"),
        "unknown": ("❓", "未分類データ", "医師列の値が想定外、内容確認が必要"),
    }
    emoji, label, note = table.get(kind, ("❓", str(kind), ""))
    prefix = f"{emoji} " if with_emoji else ""
    return f"{prefix}{label} — {note}" if note else f"{prefix}{label}"


def severity_for_kind(kind: DataKind) -> str:
    """UI severity ラベル（success / warning / danger / info / neutral）."""
    return {
        "real":    "success",
        "demo":    "warning",
        "mixed":   "danger",
        "empty":   "info",
        "unknown": "warning",
    }.get(kind, "neutral")
