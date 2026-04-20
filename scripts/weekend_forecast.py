"""
来週末の空床予測と救急余力を算出するモジュール

目的:
    多職種退院調整カンファで副院長が翌週以降の退院戦略を議論するとき、
    その判断のレバー (= カンファで決める退院計画) と結果指標 (= 来週末の
    空床予測) が同じ画面に出ていることを保証する。

設計方針 (副院長決定 2026-04-20):
    1. 対象期間は「今週末」ではなく「**来週の金・土・日**」。
       今週末はカンファ時点で既に退院予定が確定しており、議論で動かせない。
    2. 退院予測は「**同曜日 × 過去 8 週間平均**」をベースに、
       詳細データに入力済みの退院予定があればそちらを優先する
       (現場の入力が精度に直結する設計 → 入力インセンティブ化)。
    3. 入院予測は同曜日 × 過去 8 週間平均 (退院と同じ)。
    4. 救急余力 = 予測空床 − 同曜日の過去 12 週間平均救急搬送件数。
    5. 誤差を隠さず **80% 信頼区間 (±バンド)** を UI に渡す。
    6. 退院予定入力カバレッジ % を返して「入力が薄い週は幅広めに見る」
       判断を副院長側で可能にする。

バックテスト精度 (2026FY デモデータ、43 週分):
    5F 来週末 3 日合計: MAE 1.35 人 (18% of 平均 7.4 人)
    6F 来週末 3 日合計: MAE 1.49 人 (32% of 平均 4.6 人)
    → 意思決定用の規模感把握には十分。本質的な変動 (特に 6F) は
      80% 信頼区間で副院長に見せる。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

# 退院・入院予測の同曜日平均ウィンドウ (週)
DEFAULT_DISCHARGE_WINDOW_WEEKS: int = 8

# 救急搬送件数の同曜日平均ウィンドウ (週) — 退院より長めに取る
DEFAULT_EMERGENCY_WINDOW_WEEKS: int = 12

# 信頼区間の係数 (80% → ±1.28σ の正規近似)
CI80_SIGMA_MULTIPLIER: float = 1.28

# 制度上「救急搬送後」に該当するルート
EMERGENCY_ROUTES: Tuple[str, ...] = ("救急", "下り搬送")


# ---------------------------------------------------------------------------
# 日付ユーティリティ
# ---------------------------------------------------------------------------


def next_week_weekend(today: date) -> Tuple[date, date, date]:
    """``today`` を基準に、**来週の金・土・日** の日付を返す。

    「来週」は ISO week 基準で今週の次の週を指す。
    今日が月曜なら +4 日 (今週金) ではなく +11 日 (来週金) を返す。

    Args:
        today: 基準日

    Returns:
        (来週金, 来週土, 来週日) のタプル
    """
    # 今日から次の月曜までの日数 (同週の月曜は次週扱いにする)
    days_to_next_monday = (7 - today.weekday()) % 7
    if days_to_next_monday == 0:
        days_to_next_monday = 7  # 今日が月曜 → 来週月曜へ
    next_monday = today + timedelta(days=days_to_next_monday)
    return (
        next_monday + timedelta(days=4),  # 金
        next_monday + timedelta(days=5),  # 土
        next_monday + timedelta(days=6),  # 日
    )


# ---------------------------------------------------------------------------
# 曜日別平均の計算
# ---------------------------------------------------------------------------


def _compute_dow_mean_std(
    daily_df: pd.DataFrame,
    target_dow: int,
    reference_date: date,
    window_weeks: int,
    col: str,
) -> Tuple[float, float]:
    """基準日から遡って ``window_weeks`` 週間分、対象曜日の ``col`` の平均と標準偏差を返す。

    Args:
        daily_df: 日次データ (date, ward 等のカラムを持つ想定)
        target_dow: 曜日 (Monday=0 ... Sunday=6)
        reference_date: 基準日 (これより前のデータのみ使用)
        window_weeks: 遡る週数
        col: 集計対象の数値列名 (例: ``"discharges"``, ``"new_admissions"``)

    Returns:
        (mean, std)。データが 0 件なら (0.0, 0.0)。std は n=1 なら 0.0。
    """
    if daily_df is None or len(daily_df) == 0 or col not in daily_df.columns:
        return 0.0, 0.0

    df = daily_df.copy()
    df["_date"] = pd.to_datetime(df["date"]).dt.date
    df = df[df["_date"] < reference_date]
    df["_dow"] = pd.to_datetime(df["date"]).dt.dayofweek
    sub = df[df["_dow"] == target_dow].copy()
    if sub.empty:
        return 0.0, 0.0
    sub = sub.sort_values("_date").tail(window_weeks)
    vals = sub[col].astype(float)
    mean = float(vals.mean()) if len(vals) > 0 else 0.0
    std = float(vals.std(ddof=0)) if len(vals) > 1 else 0.0
    return mean, std


def _count_emergency_on_weekday(
    detail_df: pd.DataFrame,
    target_dow: int,
    reference_date: date,
    window_weeks: int,
    ward: Optional[str],
) -> float:
    """対象曜日の過去 ``window_weeks`` 週間の救急搬送件数 (救急+下り搬送) の 1 日あたり平均。

    detail_df から event_type=admission かつ route が EMERGENCY_ROUTES の行を
    対象曜日ごとに集計する。データなしなら 0.0。
    """
    if detail_df is None or len(detail_df) == 0:
        return 0.0
    df = detail_df.copy()
    if "event_type" in df.columns:
        df = df[df["event_type"] == "admission"]
    if "route" in df.columns:
        df = df[df["route"].isin(list(EMERGENCY_ROUTES))]
    if ward is not None and "ward" in df.columns:
        df = df[df["ward"] == ward]
    if df.empty:
        return 0.0
    df["_date"] = pd.to_datetime(df["date"]).dt.date
    df = df[df["_date"] < reference_date]
    df["_dow"] = pd.to_datetime(df["date"]).dt.dayofweek
    sub = df[df["_dow"] == target_dow]
    if sub.empty:
        return 0.0

    # 過去 window_weeks 週間に絞る (reference_date から window_weeks * 7 日前以降)
    cutoff = reference_date - timedelta(days=window_weeks * 7)
    sub = sub[sub["_date"] >= cutoff]
    if sub.empty:
        return 0.0

    # 対象曜日の出現日数で割る (0 件の日も 1 日分カウント)
    unique_dates = sub["_date"].nunique()
    # unique_dates は「1 件以上あった日」のカウントなので、window_weeks を上限にする
    denominator = max(min(unique_dates, window_weeks), 1)
    total_emergency = len(sub)
    return total_emergency / denominator


# ---------------------------------------------------------------------------
# 入力済み退院予定の取得
# ---------------------------------------------------------------------------


def _get_scheduled_discharges(
    detail_df: Optional[pd.DataFrame], target_date: date, ward: Optional[str]
) -> int:
    """detail_df に入力済みの該当日の退院予定件数を返す。"""
    if detail_df is None or len(detail_df) == 0:
        return 0
    df = detail_df.copy()
    if "event_type" in df.columns:
        df = df[df["event_type"] == "discharge"]
    if ward is not None and "ward" in df.columns:
        df = df[df["ward"] == ward]
    if df.empty:
        return 0
    df["_date"] = pd.to_datetime(df["date"]).dt.date
    return int((df["_date"] == target_date).sum())


# ---------------------------------------------------------------------------
# メイン関数
# ---------------------------------------------------------------------------


def forecast_next_weekend(
    daily_df: pd.DataFrame,
    detail_df: Optional[pd.DataFrame] = None,
    ward: Optional[str] = None,
    today: Optional[date] = None,
    ward_beds: int = 47,
    discharge_window_weeks: int = DEFAULT_DISCHARGE_WINDOW_WEEKS,
    emergency_window_weeks: int = DEFAULT_EMERGENCY_WINDOW_WEEKS,
) -> Dict[str, Any]:
    """来週の金・土・日の空床と救急余力を予測する。

    計算ロジック:
        1. 来週金土日の各日について:
           - 退院予定: detail_df に入力があれば実測、無ければ同曜日×8週平均
           - 新規入院予測: 同曜日×8週平均 (予定・緊急を含む総入院)
           - その日の空床 = 現在空床 + 累積(退院 - 入院)
           - 救急余力 = 空床予測 - 同曜日×12週 救急搬送平均
        2. 退院・入院の分散から 80% 信頼区間を算出
        3. 退院予定入力カバレッジ % を算出

    Args:
        daily_df: 日次データ (date, ward, total_patients, new_admissions, discharges)
        detail_df: 入退院詳細データ (任意)
        ward: 対象病棟 ("5F" / "6F")。None なら全体
        today: 基準日 (省略時は date.today())
        ward_beds: 病棟の病床数
        discharge_window_weeks: 退院・入院の同曜日平均のウィンドウ
        emergency_window_weeks: 救急搬送の同曜日平均のウィンドウ

    Returns:
        {
            "rows": [
                {
                    "day": "金",                  # 曜日ラベル
                    "date": "2026-05-01",         # ISO 日付
                    "vacancy": int,               # 空床予測 (中央値)
                    "vacancy_low": int,           # 80% 信頼区間下端
                    "vacancy_high": int,          # 80% 信頼区間上端
                    "er_margin": int,             # 救急余力 (= vacancy - 想定救急)
                    "severity": str,              # "ok" / "warn" / "danger"
                    "discharges_input": int,      # 入力済み退院予定
                    "discharges_predicted": float, # 曜日平均による退院予測
                    "admissions_predicted": float, # 曜日平均による入院予測
                    "expected_emergency": float,   # 曜日平均による救急件数
                },
                ...
            ],
            "coverage_pct": float,         # 3 日分の退院予定入力カバレッジ
            "total_vacancy_bed_days": int, # 3 日合計の空床 (床日)
            "uncertainty_bed_days": int,   # 3 日合計の不確実性 (±床日)
            "ward": Optional[str],
            "target_dates": list[str],     # ISO 日付のリスト
            "is_proxy": True,              # 予測値であることを明示
        }
    """
    td = today if today is not None else date.today()
    fri, sat, sun = next_week_weekend(td)
    target_days = [(fri, "金"), (sat, "土"), (sun, "日")]

    # 現在の空床
    current_empty = _current_empty_beds(daily_df, ward, ward_beds)

    # 各日の予測を計算
    rows: List[Dict[str, Any]] = []
    cumulative_vacancy = float(current_empty)
    cumulative_var = 0.0  # 分散の累積 (独立仮定で加算)
    discharges_input_sum = 0
    target_dates: List[str] = []

    # 対象日ごとに中間日 (今日～対象日まで) の退院・入院も累積する
    prev_day = td
    for target_date, label in target_days:
        # 今日から target_date までの全日を走査して累積 delta を計算
        d = prev_day + timedelta(days=1)
        while d <= target_date:
            dow = d.weekday()
            # 退院: 入力優先、無ければ同曜日平均
            input_discharges = _get_scheduled_discharges(detail_df, d, ward)
            predicted_discharges, dis_std = _compute_dow_mean_std(
                daily_df, dow, td, discharge_window_weeks, "discharges",
            )
            effective_discharges = (
                float(input_discharges) if input_discharges > 0
                else predicted_discharges
            )
            # 入院予測 (曜日平均のみ)
            predicted_admissions, adm_std = _compute_dow_mean_std(
                daily_df, dow, td, discharge_window_weeks, "new_admissions",
            )
            cumulative_vacancy += effective_discharges - predicted_admissions
            # 不確実性: 実測入力分には分散付けない (確定値扱い)、
            # 予測退院・予測入院それぞれに std^2 を加算
            if input_discharges == 0:
                cumulative_var += dis_std ** 2
            cumulative_var += adm_std ** 2

            if d == target_date:
                # target_date の結果を row として確定
                target_dow = target_date.weekday()
                expected_emergency = _count_emergency_on_weekday(
                    detail_df, target_dow, td, emergency_window_weeks, ward,
                )
                vacancy_mid = max(int(round(cumulative_vacancy)), 0)
                ci_half_width = CI80_SIGMA_MULTIPLIER * (cumulative_var ** 0.5)
                vacancy_low = max(int(round(cumulative_vacancy - ci_half_width)), 0)
                vacancy_high = int(round(cumulative_vacancy + ci_half_width))
                er_margin = int(round(cumulative_vacancy - expected_emergency))

                # severity 判定
                if er_margin >= 1:
                    severity = "ok"
                elif er_margin == 0:
                    severity = "warn"
                else:
                    severity = "danger"

                rows.append({
                    "day": label,
                    "date": target_date.isoformat(),
                    "vacancy": vacancy_mid,
                    "vacancy_low": vacancy_low,
                    "vacancy_high": vacancy_high,
                    "er_margin": er_margin,
                    "severity": severity,
                    "discharges_input": input_discharges,
                    "discharges_predicted": round(predicted_discharges, 2),
                    "admissions_predicted": round(predicted_admissions, 2),
                    "expected_emergency": round(expected_emergency, 2),
                })
                if input_discharges > 0:
                    discharges_input_sum += 1

                target_dates.append(target_date.isoformat())
            d += timedelta(days=1)
        prev_day = target_date

    # カバレッジ = 入力のあった対象日数 / 対象日数
    coverage_pct = (discharges_input_sum / len(target_days) * 100.0) if target_days else 0.0

    total_vacancy = sum(r["vacancy"] for r in rows)
    # 不確実性合計: 各日の半幅を平方和で合成
    total_uncertainty = int(round(sum(
        max(r["vacancy_high"] - r["vacancy"], 1) for r in rows
    ) ** 0.5))

    return {
        "rows": rows,
        "coverage_pct": round(coverage_pct, 1),
        "total_vacancy_bed_days": total_vacancy,
        "uncertainty_bed_days": total_uncertainty,
        "ward": ward,
        "target_dates": target_dates,
        "is_proxy": True,
    }


# ---------------------------------------------------------------------------
# ヘルパー: 現在空床
# ---------------------------------------------------------------------------


def _current_empty_beds(
    daily_df: pd.DataFrame, ward: Optional[str], ward_beds: int,
) -> int:
    """daily_df の最新日の空床数を返す。"""
    if daily_df is None or len(daily_df) == 0:
        return 0
    df = daily_df.copy()
    if ward is not None and "ward" in df.columns:
        df = df[df["ward"] == ward]
    if df.empty:
        return 0
    df["_date"] = pd.to_datetime(df["date"])
    latest = df.sort_values("_date").iloc[-1]
    if "total_patients" not in df.columns:
        return 0
    occupied = int(latest["total_patients"])
    return max(ward_beds - occupied, 0)
