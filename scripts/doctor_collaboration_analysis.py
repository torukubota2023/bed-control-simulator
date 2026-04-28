"""医師間分担分析モジュール — KJJ ケーススタディ.

副院長要望 (2026-04-28): 加治佐淳一医師 (KJJ、ペイン科) が 4 月の入院受持
が多く（特に保存的疼痛管理＝肋骨骨折・腰椎圧迫骨折等の下り搬送系）、
他科 (整形外科・内科) で同様の症例を扱える患者を分担できないかを
データで見える化したい。

設計方針:
- 過去 1 年 + 2026-04 統合データ (1,960 件) を入力
- 「手術なし症例」を分担候補のプロキシとして扱う (傷病名なしの近似)
- KJJ vs 他科 (整形外科 OKUK / 脳神経外科 HOKM / 内科 HAYT 等) の比較
- 月別推移 + 4 月実績 + 分担候補件数試算

含めない方針:
- 個別医師名 vs 個別医師名の批判は避け、診療科グループでも比較
- 「分担可能性」は試算であり、現場の医学的判断は別

主要関数:
    summarize_doctor_monthly(df) -> DataFrame
    compare_kjj_vs_alternatives(df) -> Dict
    estimate_load_redistribution(df, donor, recipients, transfer_pct) -> Dict
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

try:
    from doctor_specialty_map import DOCTOR_SPECIALTY_GROUP
except ImportError:
    # フォールバック (テスト等で specialty_map 未配置時)
    DOCTOR_SPECIALTY_GROUP = {}


# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

# KJJ ケーススタディの「比較対象」候補医師 (ペイン科以外で類似症例を扱える可能性)
# - 整形外科 OKUK: 肋骨骨折・腰椎圧迫骨折の保存的治療を扱う典型科
# - 脳神経外科 HOKM: 脊椎圧迫骨折で関連可能性
# - 内科グループ: 高齢の保存的管理として広く担う
KJJ_DONOR_CODE = "KJJ"

# 直接の比較対象 (個別医師)
DIRECT_PEERS = ["OKUK", "HOKM", "HAYT", "TERUH"]

# 診療科グループ比較対象
PEER_SPECIALTY_GROUPS = ["ペイン科", "整形外科", "脳神経外科", "内科"]


# ---------------------------------------------------------------------------
# 1. 医師別 月次入院数推移
# ---------------------------------------------------------------------------

def summarize_doctor_monthly(
    df: pd.DataFrame,
    doctor_codes: Optional[List[str]] = None,
) -> pd.DataFrame:
    """医師別・月別の入院数を返す.

    Args:
        df: past_admissions_2025fy.csv 由来の DataFrame
        doctor_codes: 集計対象の医師コードリスト。None なら全医師

    Returns:
        DataFrame (index=year_month, columns=doctor_code, values=入院数)
    """
    if df.empty or "医師" not in df.columns or "入院日" not in df.columns:
        return pd.DataFrame()

    work = df.copy()
    work["入院日"] = pd.to_datetime(work["入院日"], errors="coerce")
    work = work.dropna(subset=["入院日"])
    work["ym"] = work["入院日"].dt.strftime("%Y-%m")

    if doctor_codes is not None:
        work = work[work["医師"].isin(doctor_codes)]

    pivot = work.groupby(["ym", "医師"]).size().unstack(fill_value=0)
    return pivot.sort_index()


# ---------------------------------------------------------------------------
# 2. KJJ vs 他科の比較サマリー
# ---------------------------------------------------------------------------

def compare_kjj_vs_alternatives(
    df: pd.DataFrame,
    donor_code: str = KJJ_DONOR_CODE,
    peer_codes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """KJJ と分担候補医師の負担比較サマリー.

    Args:
        df: past_admissions_2025fy.csv 由来の DataFrame
        donor_code: 分担元医師コード (デフォルト KJJ)
        peer_codes: 分担候補医師コードリスト (デフォルト DIRECT_PEERS)

    Returns:
        dict:
            "donor": {"code", "specialty", "total", "no_surgery", "monthly_avg"},
            "peers": [{"code", "specialty", "total", "no_surgery", "monthly_avg"}, ...],
            "specialty_summary": [{"group", "total", "no_surgery", "doctors": [...]}, ...]
    """
    if df.empty or "医師" not in df.columns:
        return {"donor": {}, "peers": [], "specialty_summary": []}

    if peer_codes is None:
        peer_codes = DIRECT_PEERS

    work = df.copy()
    work["入院日"] = pd.to_datetime(work["入院日"], errors="coerce")
    work = work.dropna(subset=["入院日"])

    months_span = max(1, ((work["入院日"].max() - work["入院日"].min()).days + 1) / 30.0)

    def _doctor_stat(code: str) -> Dict[str, Any]:
        sub = work[work["医師"] == code]
        no_surg = (sub["手術"] == "×").sum() if "手術" in sub.columns else 0
        ward_breakdown = (
            sub["病棟"].value_counts().to_dict() if "病棟" in sub.columns else {}
        )
        # 救急車搬送 / 下り搬送候補
        emergency_count = (sub["救急車"] == "有り").sum() if "救急車" in sub.columns else 0
        from_other_hospital = (sub["入経路"] == "他病院").sum() if "入経路" in sub.columns else 0
        return {
            "code": code,
            "specialty": DOCTOR_SPECIALTY_GROUP.get(code, "未分類"),
            "total": int(len(sub)),
            "no_surgery": int(no_surg),
            "monthly_avg": round(len(sub) / months_span, 1),
            "ward_breakdown": ward_breakdown,
            "emergency_count": int(emergency_count),
            "from_other_hospital": int(from_other_hospital),
        }

    donor_stat = _doctor_stat(donor_code)
    peer_stats = [_doctor_stat(c) for c in peer_codes]

    # 診療科グループ集計
    work["SP"] = work["医師"].map(DOCTOR_SPECIALTY_GROUP).fillna("未分類")
    specialty_summary = []
    for grp in PEER_SPECIALTY_GROUPS:
        sub = work[work["SP"] == grp]
        no_surg = (sub["手術"] == "×").sum() if "手術" in sub.columns else 0
        doctors = sub["医師"].value_counts().to_dict()
        specialty_summary.append({
            "group": grp,
            "total": int(len(sub)),
            "no_surgery": int(no_surg),
            "monthly_avg": round(len(sub) / months_span, 1),
            "doctors": doctors,
        })

    return {
        "donor": donor_stat,
        "peers": peer_stats,
        "specialty_summary": specialty_summary,
        "period": {
            "from": str(work["入院日"].min().date()),
            "to": str(work["入院日"].max().date()),
            "months_span": round(months_span, 1),
        },
    }


# ---------------------------------------------------------------------------
# 3. 分担シミュレーション（手術なし症例の N% を他科に振替）
# ---------------------------------------------------------------------------

def estimate_load_redistribution(
    df: pd.DataFrame,
    donor_code: str = KJJ_DONOR_CODE,
    transfer_pct: float = 30.0,
    target_specialty: str = "整形外科",
) -> Dict[str, Any]:
    """donor 医師の手術なし症例を target_specialty に振替えた場合の試算.

    Args:
        df: past_admissions_2025fy.csv 由来の DataFrame
        donor_code: 分担元医師コード
        transfer_pct: 振替割合 (0-100)
        target_specialty: 振替先診療科グループ

    Returns:
        dict:
            "donor_before_after": {"before", "after_total", "after_no_surgery"},
            "target_before_after": {"before", "after_total"},
            "transferred_count": 振替件数
    """
    if df.empty:
        return {}

    work = df.copy()
    work["入院日"] = pd.to_datetime(work["入院日"], errors="coerce")
    work = work.dropna(subset=["入院日"])
    work["SP"] = work["医師"].map(DOCTOR_SPECIALTY_GROUP).fillna("未分類")

    months_span = max(1, ((work["入院日"].max() - work["入院日"].min()).days + 1) / 30.0)

    donor = work[work["医師"] == donor_code]
    target = work[work["SP"] == target_specialty]

    donor_no_surg = donor[donor["手術"] == "×"] if "手術" in donor.columns else pd.DataFrame()
    transferred = int(len(donor_no_surg) * transfer_pct / 100)

    # 月平均換算
    donor_before_monthly = round(len(donor) / months_span, 1)
    donor_after_monthly = round((len(donor) - transferred) / months_span, 1)
    target_before_monthly = round(len(target) / months_span, 1)
    target_after_monthly = round((len(target) + transferred) / months_span, 1)

    return {
        "donor_code": donor_code,
        "target_specialty": target_specialty,
        "transfer_pct": transfer_pct,
        "transferred_count": transferred,
        "transferred_monthly": round(transferred / months_span, 1),
        "donor_before_after": {
            "total": int(len(donor)),
            "no_surgery": int(len(donor_no_surg)),
            "monthly_avg_before": donor_before_monthly,
            "monthly_avg_after": donor_after_monthly,
        },
        "target_before_after": {
            "total": int(len(target)),
            "monthly_avg_before": target_before_monthly,
            "monthly_avg_after": target_after_monthly,
        },
        "period_months": round(months_span, 1),
    }


# ---------------------------------------------------------------------------
# 4. 4 月単独サマリー（直近月の状況把握）
# ---------------------------------------------------------------------------

def summarize_recent_month(
    df: pd.DataFrame,
    target_ym: str = "2026-04",
    focus_doctor: str = KJJ_DONOR_CODE,
) -> Dict[str, Any]:
    """指定月の医師別件数 + フォーカス医師の詳細.

    Args:
        df: past_admissions_2025fy.csv 由来の DataFrame
        target_ym: 対象年月 (YYYY-MM)
        focus_doctor: フォーカスする医師コード

    Returns:
        dict
    """
    if df.empty:
        return {}

    work = df.copy()
    work["入院日"] = pd.to_datetime(work["入院日"], errors="coerce")
    work = work.dropna(subset=["入院日"])
    work["ym"] = work["入院日"].dt.strftime("%Y-%m")

    target = work[work["ym"] == target_ym]
    if target.empty:
        return {"target_ym": target_ym, "total": 0, "doctor_ranking": [], "focus": {}}

    # 医師別ランキング
    doctor_ranking = (
        target.groupby("医師").size().sort_values(ascending=False).reset_index()
    )
    doctor_ranking.columns = ["医師", "件数"]
    doctor_ranking["診療科"] = doctor_ranking["医師"].map(
        DOCTOR_SPECIALTY_GROUP).fillna("未分類")

    # フォーカス医師の詳細
    focus_sub = target[target["医師"] == focus_doctor]
    focus_detail = {
        "doctor": focus_doctor,
        "specialty": DOCTOR_SPECIALTY_GROUP.get(focus_doctor, "未分類"),
        "total": int(len(focus_sub)),
        "ward_breakdown": focus_sub["病棟"].value_counts().to_dict() if "病棟" in focus_sub.columns else {},
        "emergency_count": int((focus_sub["救急車"] == "有り").sum()) if "救急車" in focus_sub.columns else 0,
        "from_other_hospital": int((focus_sub["入経路"] == "他病院").sum()) if "入経路" in focus_sub.columns else 0,
        "from_home": int((focus_sub["入経路"] == "家庭").sum()) if "入経路" in focus_sub.columns else 0,
        "no_surgery": int((focus_sub["手術"] == "×").sum()) if "手術" in focus_sub.columns else 0,
        "scheduled_count": int((focus_sub["緊急"] == "予定入院").sum()) if "緊急" in focus_sub.columns else 0,
        "unscheduled_count": int(focus_sub["緊急"].astype(str).str.contains("予定外", na=False).sum()) if "緊急" in focus_sub.columns else 0,
    }

    return {
        "target_ym": target_ym,
        "total": int(len(target)),
        "doctor_ranking": doctor_ranking.to_dict("records"),
        "focus": focus_detail,
        "data_period_end": str(work["入院日"].max().date()),
    }
