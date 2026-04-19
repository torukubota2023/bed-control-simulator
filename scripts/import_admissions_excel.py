"""実データの Excel ファイル (admissions_consolidated.xlsx) を、アプリの
admission_details スキーマに準拠した CSV (actual_admissions_2025fy.csv) に変換する。

入力 xlsx (Sheet "detail", 9 列):
    source_month, admission_datetime, admission_date, register_datetime,
    register_date, ward, age_code, age_label, admission_type

出力 CSV (admission_details 互換 / 取り込み用拡張):
    event_type, event_date, ward, admission_date, patient_id,
    attending_doctor, admission_route, short3_type, age_years, notes

変換ルール:
    - 病棟名:
        ４Ｆ病棟 → 4F
        ５Ｆ病棟 → 5F
        ６Ｆ病棟 → 6F
        （それ以外は例外 ValueError）
    - admission_type:
        当日(予定外/緊急)      → emergency
        予定                   → scheduled
        （それ以外は other + warning）
    - age_code (e.g. 720327) → age_years (72) を頭2桁で計算（6桁ゼロ埋め）
    - event_type: 常に "admission"（退院データが入力 xlsx に無いため）
    - 欠損フィールド:
        attending_doctor = "不明"
        short3_type      = ""  （区分情報なし）
        patient_id       = UUID (入院1件につき1つ生成)
    - 元 xlsx は変更しない

CLI:
    python3 scripts/import_admissions_excel.py \\
        --input data/admissions_consolidated.xlsx \\
        --output data/actual_admissions_2025fy.csv

    オプション:
        --dry-run  書き込みなしで件数/病棟分布/緊急率を標準出力に表示
"""
from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path
from typing import Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "admissions_consolidated.xlsx"
DEFAULT_OUTPUT = ROOT / "data" / "actual_admissions_2025fy.csv"

# 病棟名マッピング（全角→半角 + "病棟" 除去）
WARD_MAP: dict[str, str] = {
    "４Ｆ病棟": "4F",
    "５Ｆ病棟": "5F",
    "６Ｆ病棟": "6F",
}

# admission_type マッピング（xlsx 値 → 出力値）
ADMISSION_TYPE_MAP: dict[str, str] = {
    "当日(予定外/緊急)": "emergency",
    "予定": "scheduled",
}

# 出力 CSV のカラム順（admission_details 互換 + 取り込み拡張）
OUTPUT_COLUMNS: list[str] = [
    "event_type",
    "event_date",
    "ward",
    "admission_date",
    "patient_id",
    "attending_doctor",
    "admission_route",
    "short3_type",
    "age_years",
    "notes",
]

# デフォルト値
DEFAULT_ATTENDING_DOCTOR = "不明"
DEFAULT_SHORT3_TYPE = ""
DEFAULT_NOTES = ""


def map_ward(ward_raw: str) -> str:
    """病棟名を全角→半角に変換。未知の値は ValueError。"""
    if ward_raw not in WARD_MAP:
        raise ValueError(f"未知の病棟名: {ward_raw!r} (許可: {list(WARD_MAP.keys())})")
    return WARD_MAP[ward_raw]


def map_admission_type(raw: str) -> str:
    """admission_type を英語キー (scheduled / emergency / other) に変換。"""
    if raw in ADMISSION_TYPE_MAP:
        return ADMISSION_TYPE_MAP[raw]
    return "other"


def age_code_to_years(age_code: int | str) -> Optional[int]:
    """age_code (例: 720327) を age_years (72) に変換。

    6 桁数字 (YYAAMM の想定だが実体は YY=年齢, AA=月, MM=日) の先頭 2 桁を年齢として返す。
    None / 空文字 / 不正値は None を返す。
    """
    if age_code is None:
        return None
    s = str(age_code).strip()
    if not s:
        return None
    # 5 桁以下は左ゼロ埋め (例: 90123 → 090123)
    s = s.zfill(6)
    if len(s) > 6 or not s.isdigit():
        return None
    try:
        return int(s[:2])
    except ValueError:
        return None


def load_detail(xlsx_path: Path) -> pd.DataFrame:
    """xlsx の detail シートを読み取り、生 DataFrame を返す。"""
    if not xlsx_path.exists():
        raise FileNotFoundError(f"入力ファイルが見つかりません: {xlsx_path}")
    df = pd.read_excel(xlsx_path, sheet_name="detail")
    expected = {
        "source_month",
        "admission_datetime",
        "admission_date",
        "register_datetime",
        "register_date",
        "ward",
        "age_code",
        "age_label",
        "admission_type",
    }
    missing = expected - set(df.columns)
    if missing:
        raise ValueError(f"detail シートに必須列が不足: {sorted(missing)}")
    return df


def transform(detail_df: pd.DataFrame, *, seed: Optional[int] = None) -> pd.DataFrame:
    """detail DataFrame を admission_details 互換の出力 DataFrame に変換する。

    Args:
        detail_df: load_detail が返す生 DataFrame
        seed: UUID 生成の決定性のため、指定時は uuid.uuid5 の名前空間シードとして使用

    Returns:
        OUTPUT_COLUMNS の順に並んだ DataFrame
    """
    out = pd.DataFrame()
    # event_type は常に admission（退院データなし）
    out["event_type"] = ["admission"] * len(detail_df)

    # 日付正規化 (YYYY-MM-DD 文字列)
    adm_dates = pd.to_datetime(detail_df["admission_date"], errors="coerce")
    date_str = adm_dates.dt.strftime("%Y-%m-%d")
    out["event_date"] = date_str
    out["admission_date"] = date_str

    # 病棟マッピング
    out["ward"] = detail_df["ward"].astype(str).map(map_ward)

    # patient_id: UUID 生成
    if seed is not None:
        namespace = uuid.UUID(int=int(seed) & ((1 << 128) - 1))
        out["patient_id"] = [
            str(uuid.uuid5(namespace, f"{i}")) for i in range(len(detail_df))
        ]
    else:
        out["patient_id"] = [str(uuid.uuid4()) for _ in range(len(detail_df))]

    # 欠損 / 既定値
    out["attending_doctor"] = DEFAULT_ATTENDING_DOCTOR

    # admission_route: 予定/緊急/その他 → scheduled/emergency/other
    out["admission_route"] = detail_df["admission_type"].astype(str).map(map_admission_type)

    out["short3_type"] = DEFAULT_SHORT3_TYPE

    # 年齢計算
    out["age_years"] = detail_df["age_code"].map(age_code_to_years).astype("Int64")

    out["notes"] = DEFAULT_NOTES

    return out[OUTPUT_COLUMNS]


def summarize(out_df: pd.DataFrame) -> dict:
    """件数・病棟分布・緊急率などをまとめた dict を返す。"""
    total = len(out_df)
    ward_counts = out_df["ward"].value_counts().sort_index().to_dict()
    route_counts = out_df["admission_route"].value_counts().sort_index().to_dict()
    emergency_count = int(route_counts.get("emergency", 0))
    emergency_rate = (emergency_count / total * 100.0) if total > 0 else 0.0
    return {
        "total": total,
        "by_ward": ward_counts,
        "by_route": route_counts,
        "emergency_rate_pct": round(emergency_rate, 2),
        "date_min": out_df["event_date"].min() if total else None,
        "date_max": out_df["event_date"].max() if total else None,
    }


def print_summary(summary: dict, *, dry_run: bool = False) -> None:
    prefix = "[DRY RUN] " if dry_run else ""
    print(f"{prefix}期間: {summary['date_min']} 〜 {summary['date_max']}")
    print(f"{prefix}合計件数: {summary['total']} 件")
    print(f"{prefix}病棟別件数:")
    for ward, n in summary["by_ward"].items():
        print(f"{prefix}  {ward}: {n:>4} 件")
    print(f"{prefix}入院経路別件数:")
    for route, n in summary["by_route"].items():
        print(f"{prefix}  {route}: {n:>4} 件")
    print(f"{prefix}緊急率: {summary['emergency_rate_pct']:.2f}%")


def run(
    input_path: Path,
    output_path: Path,
    *,
    dry_run: bool = False,
    seed: Optional[int] = None,
) -> pd.DataFrame:
    """メイン処理: 変換 → （dry_run でなければ）CSV 書き出し → サマリ表示。"""
    detail_df = load_detail(input_path)
    out_df = transform(detail_df, seed=seed)
    summary = summarize(out_df)
    print_summary(summary, dry_run=dry_run)

    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        out_df.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"\n出力: {output_path}")
    return out_df


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="admissions_consolidated.xlsx を admission_details 互換 CSV に変換",
    )
    p.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"入力 xlsx (default: {DEFAULT_INPUT.relative_to(ROOT)})",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"出力 CSV (default: {DEFAULT_OUTPUT.relative_to(ROOT)})",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="書き込みなしで件数/病棟分布/緊急率のみ表示",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=None,
        help="UUID 生成の決定性シード (テスト用途)",
    )
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    try:
        run(args.input, args.output, dry_run=args.dry_run, seed=args.seed)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
