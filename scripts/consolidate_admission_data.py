"""月次入院データ(当日入院-YYYYMM.xlsx)を1ファイルに統合する。

入力: data/admin_data_raw/admin_data/当日入院-YYYYMM.xlsx (2025-04 〜 2026-01)
出力:
  - data/admissions_consolidated.csv       (全入院レコード)
  - data/admissions_consolidated.xlsx      (detail + monthly_summary シート)
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "admin_data_raw" / "admin_data"
OUT_CSV = ROOT / "data" / "admissions_consolidated.csv"
OUT_XLSX = ROOT / "data" / "admissions_consolidated.xlsx"

FILE_RE = re.compile(r"当日入院-(\d{6})(?: \(\d+\))?\.xlsx$")


def load_month(path: Path) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=0, header=None)
    # 1行目はヘッダ相当だが件数サマリも混ざっているので、2行目以降を採用
    df = raw.iloc[1:].copy()
    df.columns = [
        "admission_dt_raw",
        "admission_date",
        "register_dt_raw",
        "register_date",
        "ward",
        "age_code",
        "age_label",
        "_blank",
        "flag_sameday",
        "flag_planned",
    ]
    df = df.drop(columns=["_blank"])
    # 日時変換
    df["admission_datetime"] = pd.to_datetime(
        df["admission_dt_raw"].astype(str).str.zfill(14),
        format="%Y%m%d%H%M%S",
        errors="coerce",
    )
    df["admission_date"] = pd.to_datetime(
        df["admission_date"].astype(str).str.zfill(8), format="%Y%m%d", errors="coerce"
    ).dt.date
    df["register_datetime"] = pd.to_datetime(
        df["register_dt_raw"].astype(str).str.zfill(14),
        format="%Y%m%d%H%M%S",
        errors="coerce",
    )
    df["register_date"] = pd.to_datetime(
        df["register_date"].astype(str).str.zfill(8), format="%Y%m%d", errors="coerce"
    ).dt.date

    df["admission_type"] = df.apply(
        lambda r: "当日(予定外/緊急)"
        if str(r["flag_sameday"]).strip() == "○"
        else ("予定" if str(r["flag_planned"]).strip() == "○" else "不明"),
        axis=1,
    )
    return df[
        [
            "admission_datetime",
            "admission_date",
            "register_datetime",
            "register_date",
            "ward",
            "age_code",
            "age_label",
            "admission_type",
        ]
    ]


def main() -> None:
    # 重複ファイル ((1) 付き) を除外し、各月1ファイルのみ採用
    seen: dict[str, Path] = {}
    for p in sorted(RAW_DIR.glob("当日入院-*.xlsx")):
        m = FILE_RE.search(p.name)
        if not m:
            continue
        yyyymm = m.group(1)
        # "(1)" 無しを優先
        if yyyymm not in seen or "(" not in p.name:
            if yyyymm not in seen:
                seen[yyyymm] = p
            elif "(" not in p.name:
                seen[yyyymm] = p

    frames = []
    print(f"対象月: {sorted(seen.keys())}")
    for yyyymm in sorted(seen.keys()):
        path = seen[yyyymm]
        df = load_month(path)
        df.insert(0, "source_month", f"{yyyymm[:4]}-{yyyymm[4:]}")
        frames.append(df)
        print(f"  {yyyymm}: {len(df):>4} 件  ({path.name})")

    all_df = pd.concat(frames, ignore_index=True)
    all_df = all_df.sort_values(["admission_datetime", "ward"]).reset_index(drop=True)

    # 月次×病棟×区分サマリ
    summary = (
        all_df.groupby(["source_month", "ward", "admission_type"]).size().unstack(fill_value=0)
    )
    summary["合計"] = summary.sum(axis=1)
    summary = summary.reset_index()

    all_df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as xw:
        all_df.to_excel(xw, sheet_name="detail", index=False)
        summary.to_excel(xw, sheet_name="monthly_summary", index=False)

    print(f"\n合計レコード: {len(all_df)} 件")
    print(f"  CSV:  {OUT_CSV.relative_to(ROOT)}")
    print(f"  XLSX: {OUT_XLSX.relative_to(ROOT)}")
    print("\n--- 月×病棟×区分サマリ ---")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
