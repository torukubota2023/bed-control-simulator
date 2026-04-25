"""医師別 退院プロファイル分析モジュール.

過去1年の入院データ（事務提供 CSV）または日次入力データ（admission_details.csv）
から、医師ごとの退院行動パターンを分析する。

**設計思想（副院長指示 2026-04-24）:**
- 「順位付け」ではなく **peer（同診療科 or 全体）中央値からの差** で提示
- 小サンプル（件数 < 20）は「参考値」注記
- ポジティブ側面を必ず併記できるよう、複数の指標を並列に返す
- 医師本人に見せる前提で、差分と意味合いを透明に

**4 指標:**
1. 退院曜日の偏り（Gini 係数 + 各曜日の割合）
2. 自分主導の短期退院傾向（予定入院×手術なし の median LOS）
3. 稼働率下落への影響（金曜＋土曜退院割合 = 週末空床リスク寄与）
4. 個別サマリー（1-3 を 1 医師分まとめる）

**Data source 非依存:**
関数は DataFrame + 列名を引数で受け取るため、過去CSV も admission_details も
同じロジックで動く。運用開始後は日次入力 → 即時反映。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

WEEKDAY_LABELS_JA: List[str] = ["月", "火", "水", "木", "金", "土", "日"]

# 小サンプル注記閾値（件数 < 20 は参考値扱い）
SMALL_SAMPLE_THRESHOLD: int = 20

# 金曜集中 / 週明け集中 の判定閾値（%）
FRIDAY_HEAVY_PCT: float = 30.0
MONDAY_HEAVY_PCT: float = 25.0
UNIFORM_GINI_MAX: float = 0.15  # Gini < 0.15 なら均等

# ---------------------------------------------------------------------------
# Helper: Gini 係数
# ---------------------------------------------------------------------------

def _gini_coefficient(values: List[float]) -> float:
    """値のリストの Gini 係数を返す（0 = 完全均等、1 = 完全集中）.

    ここでは「医師の退院曜日分布（7要素）の偏り」を測るのに使う。
    - 全曜日に均等に退院: Gini = 0
    - 1 曜日に集中: Gini = (n-1)/n ≈ 0.857（7 曜日の場合）
    """
    if not values:
        return 0.0
    total = sum(values)
    if total == 0:
        return 0.0
    n = len(values)
    sorted_vals = sorted(values)
    # 通常の Gini: sum_i sum_j |x_i - x_j| / (2 * n * sum(x))
    # より効率的な公式: (2 * sum(i * x_sorted_i) - (n+1) * sum) / (n * sum)
    cum = sum((i + 1) * v for i, v in enumerate(sorted_vals))
    gini = (2.0 * cum - (n + 1) * total) / (n * total)
    return round(max(0.0, min(1.0, gini)), 3)


# ---------------------------------------------------------------------------
# 指標 1: 退院曜日の偏り
# ---------------------------------------------------------------------------

def compute_weekday_profile(
    df: pd.DataFrame,
    doctor_col: str = "医師",
    discharge_date_col: str = "discharge_date",
) -> Dict[str, Dict[str, Any]]:
    """医師別の退院曜日分布と偏り指標を返す.

    Args:
        df: DataFrame（過去CSV or admission_details を想定）
        doctor_col: 医師コードを含む列名
        discharge_date_col: 退院日（date 型 or datetime）の列名

    Returns:
        ``{医師コード: {counts: [月〜日の件数7要素],
                       pcts: [同7要素の割合%],
                       total: 総退院数,
                       gini: 偏り指数,
                       friday_pct: 金曜率,
                       monday_pct: 月曜率,
                       weekend_risk_pct: 金+土曜率 (週末空床リスク),
                       flag: 'friday_heavy' | 'monday_heavy' | 'uniform' | 'normal',
                       is_small_sample: bool}}``
    """
    if df.empty or doctor_col not in df.columns or discharge_date_col not in df.columns:
        return {}

    # 退院日が NaT なレコードは除外
    work = df[df[discharge_date_col].notna()].copy()
    if work.empty:
        return {}

    # weekday 抽出
    work["_weekday"] = pd.to_datetime(work[discharge_date_col]).dt.weekday

    result: Dict[str, Dict[str, Any]] = {}
    for doctor, sub in work.groupby(doctor_col, sort=True):
        counts = [int((sub["_weekday"] == i).sum()) for i in range(7)]
        total = sum(counts)
        if total == 0:
            continue
        pcts = [round(c / total * 100, 1) for c in counts]
        gini = _gini_coefficient([float(c) for c in counts])
        fri_pct = pcts[4]
        mon_pct = pcts[0]
        sat_pct = pcts[5]
        weekend_risk = round(fri_pct + sat_pct, 1)

        if fri_pct >= FRIDAY_HEAVY_PCT:
            flag = "friday_heavy"
        elif mon_pct >= MONDAY_HEAVY_PCT:
            flag = "monday_heavy"
        elif gini < UNIFORM_GINI_MAX:
            flag = "uniform"
        else:
            flag = "normal"

        result[str(doctor)] = {
            "counts": counts,
            "pcts": pcts,
            "total": total,
            "gini": gini,
            "friday_pct": fri_pct,
            "monday_pct": mon_pct,
            "weekend_risk_pct": weekend_risk,
            "flag": flag,
            "is_small_sample": total < SMALL_SAMPLE_THRESHOLD,
        }
    return result


# ---------------------------------------------------------------------------
# 指標 2: 自分主導の短期退院傾向
# ---------------------------------------------------------------------------

def compute_self_driven_los(
    df: pd.DataFrame,
    doctor_col: str = "医師",
    los_col: str = "日数",
    scheduled_col: Optional[str] = "is_scheduled",
    surgery_col: str = "has_surgery",
    specialty_col: Optional[str] = "診療科",
    specialty_override_map: Optional[Dict[str, str]] = None,
    require_scheduled: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """手術なし の全入院 median LOS を医師別に算出.

    **考え方（2026-04-24 修正）:**
    術後経過という外的要因を排除した「手術なし」症例で、
    医師の退院判断（状態良好 → 退院、調整待ちで延長 等）を比較する。
    予定/予定外の両方を含めることで、内科系医師にもサンプル数が確保できる。

    **peer（他医師の中央値）の計算:**
    ``specialty_override_map`` が指定されれば、医師コード → 診療科グループ
    として使う（副院長の実務分類を尊重）。未指定なら ``specialty_col`` 列を
    そのまま使う。「外来専任」「訪問診療医」のような peer 単独グループは
    「全体中央値」をフォールバックとして使う。

    Args:
        df: DataFrame
        doctor_col: 医師列名
        los_col: 在院日数列名
        scheduled_col: 予定入院フラグ列名（require_scheduled=True の時のみ使用）
        surgery_col: 手術フラグ列名
        specialty_col: 診療科列名（override_map 未指定時）
        specialty_override_map: 医師コード → 診療科グループ（副院長分類）
        require_scheduled: True なら 予定入院×手術なし（旧挙動）、
                           False なら手術なし全体（新挙動・デフォルト）

    Returns:
        ``{医師コード: {self_driven_cases: int,
                       median_los: float,
                       peer_median: float (同診療科 or 全体),
                       los_delta_vs_peer: float (peer - self: 正=短い),
                       peer_group: str (分類名),
                       is_small_sample: bool}}``
    """
    required = {doctor_col, los_col, surgery_col}
    if df.empty or not required.issubset(df.columns):
        return {}
    if require_scheduled and scheduled_col not in df.columns:
        return {}

    # フィルタリング
    if require_scheduled:
        work = df[df[scheduled_col] & ~df[surgery_col]].copy()
    else:
        work = df[~df[surgery_col]].copy()
    if work.empty:
        return {}
    work[los_col] = pd.to_numeric(work[los_col], errors="coerce")
    work = work.dropna(subset=[los_col])
    if work.empty:
        return {}

    # 診療科グループを決定（override_map 優先）
    if specialty_override_map:
        work["_specialty_group"] = work[doctor_col].map(
            lambda d: specialty_override_map.get(str(d), "未分類")
        )
        group_col = "_specialty_group"
    elif specialty_col and specialty_col in work.columns:
        group_col = specialty_col
    else:
        group_col = None

    # 診療科グループ別 peer median を事前計算
    peer_median_by_spec: Dict[str, float] = {}
    if group_col:
        for spec, sub in work.groupby(group_col):
            # サンプル 2 以上ないと peer として意味がない
            if len(sub) >= 2:
                peer_median_by_spec[str(spec)] = float(sub[los_col].median())
    overall_median = float(work[los_col].median())

    result: Dict[str, Dict[str, Any]] = {}
    for doctor, sub in work.groupby(doctor_col):
        n = len(sub)
        if n == 0:
            continue
        doc_median = float(sub[los_col].median())
        # peer は 同じ診療科グループの中央値（自身のみで peer 不成立なら全体）
        peer_group = "全体"
        if group_col and group_col in sub.columns:
            specs = sub[group_col].dropna().unique()
            if len(specs) == 1:
                spec_key = str(specs[0])
                if spec_key in peer_median_by_spec:
                    peer_med = peer_median_by_spec[spec_key]
                    peer_group = spec_key
                else:
                    peer_med = overall_median
            else:
                peer_med = overall_median
        else:
            peer_med = overall_median
        result[str(doctor)] = {
            "self_driven_cases": int(n),
            "median_los": round(doc_median, 1),
            "peer_median": round(peer_med, 1),
            "los_delta_vs_peer": round(peer_med - doc_median, 1),  # 正=peer より短い
            "peer_group": peer_group,
            "is_small_sample": n < SMALL_SAMPLE_THRESHOLD,
        }
    return result


# ---------------------------------------------------------------------------
# 指標 3: 稼働率下落への影響（週末空床リスク寄与）
# ---------------------------------------------------------------------------

def compute_weekend_vacancy_risk(
    df: pd.DataFrame,
    doctor_col: str = "医師",
    discharge_date_col: str = "discharge_date",
) -> Dict[str, Dict[str, Any]]:
    """金土退院の割合（週末空床リスク寄与度）を医師別に算出.

    **考え方（2026-04-25 副院長指示で木金→金土に変更）:**
    当院の過去1年データでは土曜入院 2.22 件/日（平日の 30%）、
    日曜入院 0.27 件/日（ほぼゼロ）。金曜退院 → 土日 2 日間空床、
    土曜退院 → 日曜 1 日間空床と直接的に週末空床を生む。
    医師個別の"金+土"率を peer 平均と比較し、稼働率下落への影響傾向を可視化。
    対策: 金土退院対象患者を **日曜（補充ほぼゼロで滞留しない）** または
    **月曜以降（月曜入院 7.35 件/日で当日中に補充される）** に振り替える。

    Returns:
        ``{医師コード: {friday_pct, saturday_pct, fri_sat_pct,
                       peer_fri_sat_pct (全医師の同指標の中央値),
                       delta_vs_peer: 正=peer より高い(リスク寄与大),
                       total_discharges, is_small_sample}}``
    """
    profile = compute_weekday_profile(df, doctor_col, discharge_date_col)
    if not profile:
        return {}

    # 全医師の fri_sat_pct 中央値を peer として使う
    # （該当サンプル数 >= SMALL_SAMPLE_THRESHOLD の医師だけで計算）
    qualifying = [
        v["weekend_risk_pct"] for v in profile.values()
        if not v["is_small_sample"]
    ]
    peer_median = (
        float(pd.Series(qualifying).median()) if qualifying else 0.0
    )

    result: Dict[str, Dict[str, Any]] = {}
    for doctor, pf in profile.items():
        result[doctor] = {
            "friday_pct": pf["friday_pct"],
            "saturday_pct": pf["pcts"][5],
            "fri_sat_pct": pf["weekend_risk_pct"],
            "peer_fri_sat_pct": round(peer_median, 1),
            "delta_vs_peer": round(pf["weekend_risk_pct"] - peer_median, 1),
            "total_discharges": pf["total"],
            "is_small_sample": pf["is_small_sample"],
        }
    return result


# ---------------------------------------------------------------------------
# 指標 4: 個別医師のサマリー
# ---------------------------------------------------------------------------

def build_doctor_summary(
    df: pd.DataFrame,
    doctor: str,
    doctor_col: str = "医師",
    discharge_date_col: str = "discharge_date",
    los_col: str = "日数",
    scheduled_col: str = "is_scheduled",
    surgery_col: str = "has_surgery",
    specialty_col: Optional[str] = "診療科",
    specialty_override_map: Optional[Dict[str, str]] = None,
    require_scheduled: bool = False,
) -> Dict[str, Any]:
    """1 医師分のプロファイル（本人向けビュー用）をまとめて返す.

    Returns:
        dict: {
            "doctor": 医師コード,
            "weekday": 退院曜日プロファイル（compute_weekday_profile の 1 人分）,
            "self_driven": 自分主導 LOS（compute_self_driven_los の 1 人分）,
            "weekend_risk": 週末空床リスク（compute_weekend_vacancy_risk の 1 人分）,
            "insights": [str] ポジティブ/改善点のフレーズ,
        }
    """
    weekday = compute_weekday_profile(df, doctor_col, discharge_date_col).get(doctor, {})
    self_driven = compute_self_driven_los(
        df, doctor_col=doctor_col, los_col=los_col,
        scheduled_col=scheduled_col, surgery_col=surgery_col,
        specialty_col=specialty_col,
        specialty_override_map=specialty_override_map,
        require_scheduled=require_scheduled,
    ).get(doctor, {})
    weekend_risk = compute_weekend_vacancy_risk(df, doctor_col, discharge_date_col).get(doctor, {})

    insights: List[str] = []
    # ポジティブ / 改善フレーズの生成
    if weekday:
        if weekday["flag"] == "uniform":
            insights.append("✅ 退院曜日が均等（週末空床リスクを抑える退院計画）")
        elif weekday["flag"] == "friday_heavy":
            insights.append(
                f"⚠️ 金曜退院が {weekday['friday_pct']:.0f}% と集中。"
                f"対象患者の **月曜以降** への退院振替を検討（土日空床抑制）"
            )
        elif weekday["flag"] == "monday_heavy":
            insights.append(
                f"ℹ️ 月曜退院が {weekday['monday_pct']:.0f}% と多め。"
                f"週末越しの入院が目立つ"
            )

    if self_driven and not self_driven.get("is_small_sample", True):
        delta = self_driven.get("los_delta_vs_peer", 0.0)
        _group = self_driven.get("peer_group", "全体")
        if delta >= 1.0:
            insights.append(
                f"✅ 手術なしの中央在院日数 {self_driven['median_los']}日 "
                f"({_group}他医師 {self_driven['peer_median']}日) — 自主的に回転させている"
            )
        elif delta <= -1.5:
            insights.append(
                f"📈 手術なしの中央在院日数 {self_driven['median_los']}日 "
                f"({_group}他医師 {self_driven['peer_median']}日) — 他医師より長め"
            )

    if weekend_risk and not weekend_risk.get("is_small_sample", True):
        delta_w = weekend_risk.get("delta_vs_peer", 0.0)
        if delta_w <= -5.0:
            insights.append(
                f"✅ 金+土退院率 {weekend_risk['fri_sat_pct']:.0f}% "
                f"(全医師中央値 {weekend_risk['peer_fri_sat_pct']:.0f}%) — 週末空床リスクを抑えている"
            )
        elif delta_w >= 5.0:
            insights.append(
                f"⚠️ 金+土退院率 {weekend_risk['fri_sat_pct']:.0f}% "
                f"(全医師中央値 {weekend_risk['peer_fri_sat_pct']:.0f}%) — "
                f"対象患者の **月曜以降** への退院振替を検討"
                f"（日曜・祝日は 1 病棟 2 人/日 まで補助枠として活用可）"
            )

    return {
        "doctor": doctor,
        "weekday": weekday,
        "self_driven": self_driven,
        "weekend_risk": weekend_risk,
        "insights": insights,
    }
