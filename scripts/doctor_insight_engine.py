"""
医師別 深掘りインサイトエンジン

目的:
    副院長・師長が理事会や師長会議で使える「医師ごとの改善の可能性」を
    客観データから抽出するための分析モジュール。

設計思想:
    - 現状の医師別分析（入院件数・平均在院日数など）を **補完** する深掘り指標
    - 評価的ラベル（"悪い医師"）ではなく観察的ラベル（"金曜集中傾向"）を出力
    - severity は「注意喚起が必要か」のみを示し、非難トーンを避ける
    - 全体平均との差分で「個人の特徴」を浮かび上がらせる

指標（Phase 1: 曜日別退院 + C群長期化率）:
    1. weekday_discharge_profile — 医師ごとの曜日別退院比率と全体平均からの乖離
    2. c_group_long_stay_rate   — 医師ごとの C群（15日以上）患者比率と長期化傾向

将来拡張（design doc として温存）:
    - 退院調整の速さ（入院→退院確定までの平均日数）
    - 短手3 活用率・Day 5 超過率
    - 救急搬送後入院の貢献度

データソース:
    admission_details DataFrame（bed_data_manager.ADMISSION_DETAIL_COLUMNS）
    カラム: id / date / ward / event_type / route / source_doctor /
            attending_doctor / los_days / phase / short3_type

注意:
    - 個人情報は扱わない（表示名のみ）
    - データ不足時は空辞書 / None を返し、UI 側でグレーアウト表示に倒す
"""

from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd


# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

# 最小サンプル件数 — これ未満の医師は「データ不足」扱い
MIN_DISCHARGES_FOR_WEEKDAY = 5  # 曜日分析の最低退院数
MIN_DISCHARGES_FOR_C_GROUP = 5  # C群分析の最低退院数

# 金曜集中の警告しきい値（%）
FRIDAY_HEAVY_THRESHOLD_PCT = 40.0
# 金曜の全体平均と比較した個人乖離（ポイント差）
FRIDAY_DEVIATION_WARNING_PP = 15.0

# 週末退院比率の警告しきい値 — 極端に低い場合のみ注意喚起
WEEKEND_AVOIDANCE_THRESHOLD_PCT = 5.0

# C群長期化率の警告しきい値 — 全体中央値からの乖離（ポイント差）
C_GROUP_DEVIATION_WARNING_PP = 20.0
# C群長期化率の絶対値しきい値
C_GROUP_HEAVY_ABS_PCT = 60.0


# ---------------------------------------------------------------------------
# 内部ヘルパー
# ---------------------------------------------------------------------------

def _discharges_only(df: pd.DataFrame) -> pd.DataFrame:
    """退院イベントのみを抽出する。"""
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=df.columns if df is not None else [])
    if "event_type" not in df.columns:
        return pd.DataFrame(columns=df.columns)
    out = df[df["event_type"] == "discharge"].copy()
    # attending_doctor 欠損は除外（集計対象外）
    if "attending_doctor" in out.columns:
        out = out[out["attending_doctor"].notna()]
        out = out[out["attending_doctor"].astype(str).str.strip() != ""]
    return out


def _ensure_date(df: pd.DataFrame) -> pd.DataFrame:
    """date 列を datetime に変換する（破壊的変更を避けるためコピー済み想定）。"""
    if "date" in df.columns:
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


# ---------------------------------------------------------------------------
# 指標 1: 曜日別退院プロファイル
# ---------------------------------------------------------------------------

def calculate_weekday_profile(
    df: pd.DataFrame,
    doctor_name: Optional[str] = None,
) -> Dict:
    """
    医師ごと（または全体）の曜日別退院プロファイルを返す。

    Args:
        df: admission_details DataFrame
        doctor_name: 対象医師名。None なら全体集計。

    Returns:
        dict: {
            "total_discharges": int,
            "weekday_counts": {0: int, 1: int, ..., 6: int},  # 0=月
            "weekday_pct":    {0: float, ..., 6: float},       # 合計100
            "friday_pct":     float,
            "weekend_pct":    float,   # 土日合算
            "weekday_pct_mf": float,   # 月-金合算
            "enough_data":    bool,
        }

        データ不足の場合 total_discharges=0, enough_data=False
    """
    empty_result = {
        "total_discharges": 0,
        "weekday_counts": {i: 0 for i in range(7)},
        "weekday_pct": {i: 0.0 for i in range(7)},
        "friday_pct": 0.0,
        "weekend_pct": 0.0,
        "weekday_pct_mf": 0.0,
        "enough_data": False,
    }

    dis = _discharges_only(df)
    if len(dis) == 0:
        return empty_result

    dis = _ensure_date(dis)
    if doctor_name is not None:
        dis = dis[dis["attending_doctor"] == doctor_name]

    total = len(dis)
    if total == 0:
        return empty_result

    dis["_wd"] = dis["date"].dt.dayofweek
    counts: Dict[int, int] = {i: 0 for i in range(7)}
    vc = dis["_wd"].value_counts().to_dict()
    for k, v in vc.items():
        if pd.notna(k):
            counts[int(k)] = int(v)

    pct = {i: (counts[i] / total * 100) for i in range(7)}
    friday_pct = pct[4]
    weekend_pct = pct[5] + pct[6]
    weekday_pct_mf = pct[0] + pct[1] + pct[2] + pct[3] + pct[4]

    return {
        "total_discharges": total,
        "weekday_counts": counts,
        "weekday_pct": pct,
        "friday_pct": round(friday_pct, 1),
        "weekend_pct": round(weekend_pct, 1),
        "weekday_pct_mf": round(weekday_pct_mf, 1),
        "enough_data": total >= MIN_DISCHARGES_FOR_WEEKDAY,
    }


def _classify_weekday_severity(
    friday_pct: float,
    weekend_pct: float,
    overall_friday_pct: float,
    overall_weekend_pct: float,
    enough_data: bool,
) -> str:
    """
    曜日プロファイルの severity を返す。

    Returns:
        "warning"  — 金曜集中 or 週末回避が顕著
        "neutral"  — 全体平均圏内
        "unknown"  — データ不足
    """
    if not enough_data:
        return "unknown"

    friday_deviation = friday_pct - overall_friday_pct
    weekend_deviation = overall_weekend_pct - weekend_pct  # 低いほど回避傾向

    if friday_pct >= FRIDAY_HEAVY_THRESHOLD_PCT:
        return "warning"
    if friday_deviation >= FRIDAY_DEVIATION_WARNING_PP:
        return "warning"
    if weekend_pct <= WEEKEND_AVOIDANCE_THRESHOLD_PCT and overall_weekend_pct > WEEKEND_AVOIDANCE_THRESHOLD_PCT:
        return "warning"
    if weekend_deviation >= 10.0:
        return "warning"
    return "neutral"


def build_weekday_insights(df: pd.DataFrame) -> List[Dict]:
    """
    全医師の曜日別退院プロファイルを一覧で返す。

    Returns:
        List[dict]: 医師ごとに以下を含む
            - doctor: 医師名
            - total_discharges: 総退院数
            - friday_pct / weekend_pct / weekday_pct_mf
            - overall_friday_pct / overall_weekend_pct: 全体平均（比較用）
            - severity: "warning" | "neutral" | "unknown"
            - observation: 自然言語での観察コメント
            - action_hint: 改善の可能性（提案トーン）
            - enough_data: bool
    """
    dis = _discharges_only(df)
    if len(dis) == 0:
        return []

    overall = calculate_weekday_profile(df, doctor_name=None)
    overall_friday = overall["friday_pct"]
    overall_weekend = overall["weekend_pct"]

    doctors = sorted(dis["attending_doctor"].dropna().unique())
    insights: List[Dict] = []
    for doc in doctors:
        prof = calculate_weekday_profile(df, doctor_name=doc)
        if prof["total_discharges"] == 0:
            continue
        severity = _classify_weekday_severity(
            prof["friday_pct"], prof["weekend_pct"],
            overall_friday, overall_weekend,
            prof["enough_data"],
        )

        # 観察コメント（非難にならない記述）
        if not prof["enough_data"]:
            observation = (
                f"退院 {prof['total_discharges']} 件 — サンプル不足のため"
                "傾向判定は保留"
            )
            action_hint = "データが蓄積次第、再評価"
        elif prof["friday_pct"] >= FRIDAY_HEAVY_THRESHOLD_PCT:
            observation = (
                f"金曜退院が {prof['friday_pct']:.0f}%（全体平均 {overall_friday:.0f}%）"
                "— 退院が週末前に集中する傾向"
            )
            action_hint = (
                "金曜退院のうち家族調整が可能なケースを火〜木に分散すると、"
                "土日の稼働率低下を抑えられる可能性"
            )
        elif (prof["friday_pct"] - overall_friday) >= FRIDAY_DEVIATION_WARNING_PP:
            observation = (
                f"金曜退院が {prof['friday_pct']:.0f}%（全体平均より"
                f"+{prof['friday_pct'] - overall_friday:.0f}pt）"
            )
            action_hint = (
                "金曜集中の背景確認（家族面会タイミング、退院指導の曜日固定等）"
            )
        elif prof["weekend_pct"] <= WEEKEND_AVOIDANCE_THRESHOLD_PCT and overall_weekend > WEEKEND_AVOIDANCE_THRESHOLD_PCT:
            observation = (
                f"週末退院が {prof['weekend_pct']:.0f}%（全体平均 {overall_weekend:.0f}%）"
                "— 週末退院を回避する傾向"
            )
            action_hint = (
                "退院可能と判断された患者のうち、土日の家族調整が可能なケースを"
                "個別に再検討する余地"
            )
        elif (overall_weekend - prof["weekend_pct"]) >= 10.0:
            observation = (
                f"週末退院が {prof['weekend_pct']:.0f}%（全体平均より"
                f"-{overall_weekend - prof['weekend_pct']:.0f}pt）"
            )
            action_hint = "週末退院の選択肢検討（任意・患者背景次第）"
        else:
            observation = (
                f"曜日分布は全体平均圏内（金 {prof['friday_pct']:.0f}% / "
                f"週末 {prof['weekend_pct']:.0f}%）"
            )
            action_hint = "現在の退院タイミング運用を維持"

        insights.append({
            "doctor": doc,
            "total_discharges": prof["total_discharges"],
            "friday_pct": prof["friday_pct"],
            "weekend_pct": prof["weekend_pct"],
            "weekday_pct_mf": prof["weekday_pct_mf"],
            "overall_friday_pct": overall_friday,
            "overall_weekend_pct": overall_weekend,
            "severity": severity,
            "observation": observation,
            "action_hint": action_hint,
            "enough_data": prof["enough_data"],
        })

    return insights


# ---------------------------------------------------------------------------
# 指標 2: C群長期化率
# ---------------------------------------------------------------------------

def calculate_c_group_stats(
    df: pd.DataFrame,
    doctor_name: Optional[str] = None,
) -> Dict:
    """
    医師ごと（または全体）の C群（在院15日以上）統計を返す。

    phase 列が存在する退院レコードのみで集計する。

    Returns:
        dict: {
            "total_discharges": int,
            "c_group_count": int,
            "c_group_pct": float,     # 退院全体に占めるC群比率
            "avg_los_c": float,        # C群患者の平均在院日数
            "max_los_c": int,          # C群患者の最長在院日数
            "enough_data": bool,
        }
    """
    empty_result = {
        "total_discharges": 0,
        "c_group_count": 0,
        "c_group_pct": 0.0,
        "avg_los_c": 0.0,
        "max_los_c": 0,
        "enough_data": False,
    }

    dis = _discharges_only(df)
    if len(dis) == 0 or "phase" not in dis.columns:
        return empty_result

    if doctor_name is not None:
        dis = dis[dis["attending_doctor"] == doctor_name]

    total = len(dis)
    if total == 0:
        return empty_result

    c_rows = dis[dis["phase"] == "C"]
    c_count = len(c_rows)
    c_pct = (c_count / total * 100) if total > 0 else 0.0

    if "los_days" in c_rows.columns and c_count > 0:
        los_c = pd.to_numeric(c_rows["los_days"], errors="coerce").dropna()
        avg_los_c = float(los_c.mean()) if len(los_c) > 0 else 0.0
        max_los_c = int(los_c.max()) if len(los_c) > 0 else 0
    else:
        avg_los_c = 0.0
        max_los_c = 0

    return {
        "total_discharges": total,
        "c_group_count": c_count,
        "c_group_pct": round(c_pct, 1),
        "avg_los_c": round(avg_los_c, 1),
        "max_los_c": max_los_c,
        "enough_data": total >= MIN_DISCHARGES_FOR_C_GROUP,
    }


def _classify_c_group_severity(
    c_group_pct: float,
    overall_c_group_pct: float,
    enough_data: bool,
) -> str:
    """C群長期化率の severity を返す。"""
    if not enough_data:
        return "unknown"
    if c_group_pct >= C_GROUP_HEAVY_ABS_PCT:
        return "warning"
    if (c_group_pct - overall_c_group_pct) >= C_GROUP_DEVIATION_WARNING_PP:
        return "warning"
    return "neutral"


def build_c_group_insights(df: pd.DataFrame) -> List[Dict]:
    """
    全医師の C群長期化率をインサイトとして一覧化する。

    Returns:
        List[dict]: 医師ごとに以下を含む
            - doctor / total_discharges / c_group_count / c_group_pct /
              avg_los_c / max_los_c
            - overall_c_group_pct
            - severity / observation / action_hint / enough_data
    """
    dis = _discharges_only(df)
    if len(dis) == 0:
        return []

    overall = calculate_c_group_stats(df, doctor_name=None)
    overall_c_pct = overall["c_group_pct"]

    doctors = sorted(dis["attending_doctor"].dropna().unique())
    insights: List[Dict] = []
    for doc in doctors:
        stats = calculate_c_group_stats(df, doctor_name=doc)
        if stats["total_discharges"] == 0:
            continue
        severity = _classify_c_group_severity(
            stats["c_group_pct"], overall_c_pct, stats["enough_data"],
        )

        if not stats["enough_data"]:
            observation = (
                f"退院 {stats['total_discharges']} 件 — サンプル不足のため"
                "傾向判定は保留"
            )
            action_hint = "データが蓄積次第、再評価"
        elif stats["c_group_pct"] >= C_GROUP_HEAVY_ABS_PCT:
            observation = (
                f"C群（15日以上）が {stats['c_group_pct']:.0f}%"
                f"（全体平均 {overall_c_pct:.0f}%）— 長期化が目立つ"
                f" / C群 平均在院 {stats['avg_los_c']:.0f}日"
            )
            action_hint = (
                "入院 15 日経過時点のカンファで退院阻害要因を棚卸し。"
                "療養先調整 / 家族支援 / 医療必要度の側面から個別に整理"
            )
        elif (stats["c_group_pct"] - overall_c_pct) >= C_GROUP_DEVIATION_WARNING_PP:
            observation = (
                f"C群が {stats['c_group_pct']:.0f}%（全体平均より"
                f"+{stats['c_group_pct'] - overall_c_pct:.0f}pt）"
            )
            action_hint = (
                "担当患者の疾患構成を確認の上、C群化の共通要因があれば"
                "退院調整カンファで共有"
            )
        else:
            observation = (
                f"C群 {stats['c_group_pct']:.0f}%（全体平均 {overall_c_pct:.0f}%）— 平均圏内"
            )
            action_hint = "現在の退院調整ペースを維持"

        insights.append({
            "doctor": doc,
            "total_discharges": stats["total_discharges"],
            "c_group_count": stats["c_group_count"],
            "c_group_pct": stats["c_group_pct"],
            "avg_los_c": stats["avg_los_c"],
            "max_los_c": stats["max_los_c"],
            "overall_c_group_pct": overall_c_pct,
            "severity": severity,
            "observation": observation,
            "action_hint": action_hint,
            "enough_data": stats["enough_data"],
        })

    return insights


# ---------------------------------------------------------------------------
# 統合: 医師ごとの深掘りインサイト
# ---------------------------------------------------------------------------

def build_doctor_insights(df: pd.DataFrame) -> List[Dict]:
    """
    全医師の深掘りインサイトを統合して返す。

    各医師のレコードは:
        - doctor
        - weekday: build_weekday_insights の該当要素（医師別）
        - c_group: build_c_group_insights の該当要素（医師別）
        - worst_severity: "warning" > "neutral" > "unknown" の優先順位

    UI 側はこれを表形式 or カード形式で表示する。
    worst_severity で降順ソートすると「要注目の医師」が先頭に来る。
    """
    wd_list = build_weekday_insights(df)
    cg_list = build_c_group_insights(df)

    wd_by_doc = {w["doctor"]: w for w in wd_list}
    cg_by_doc = {c["doctor"]: c for c in cg_list}

    doctors = sorted(set(wd_by_doc.keys()) | set(cg_by_doc.keys()))
    results: List[Dict] = []
    severity_rank = {"warning": 2, "neutral": 1, "unknown": 0}

    for doc in doctors:
        wd = wd_by_doc.get(doc)
        cg = cg_by_doc.get(doc)
        severities = []
        if wd:
            severities.append(wd.get("severity", "unknown"))
        if cg:
            severities.append(cg.get("severity", "unknown"))
        worst = "unknown"
        worst_rank = -1
        for s in severities:
            r = severity_rank.get(s, 0)
            if r > worst_rank:
                worst_rank = r
                worst = s
        results.append({
            "doctor": doc,
            "weekday": wd,
            "c_group": cg,
            "worst_severity": worst,
        })

    # warning > neutral > unknown の順に並べる
    results.sort(key=lambda r: -severity_rank.get(r["worst_severity"], 0))
    return results
