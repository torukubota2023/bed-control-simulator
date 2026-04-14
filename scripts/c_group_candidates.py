"""
C群候補者リスト（lite版）モジュール — 入退院詳細データからC群候補を抽出する  # v3.5.2

C群（在院15日目以降）は院内運用上のラベルであり、制度上の公式区分ではない。
本モジュールは入退院詳細イベント（detail_df）から、退院イベントが未記録の
入院患者を抽出し、在院日数が閾値以上の患者をC群候補として一覧化する。

IMPORTANT:
- 患者レベルの正確なデータにはHOPEシステム連携が必要（将来構想）
- 本モジュールの出力は入退院イベントから算出した PROXY データである
- 臨床判断・家族状況・退院支援状況は考慮されない
- 延長推奨リストではなく「調整候補一覧（lite）」として扱うこと

Streamlit に依存しない。pandas と標準ライブラリのみ使用する。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

C_PHASE_START_DAY: int = 15
"""C群開始日（15日目以降）"""

_DATA_SOURCE_LABEL: str = "proxy"
_PROXY_NOTE: str = (
    "本データはlite版です。入退院イベントから算出したデータであり、"
    "実際の在院状況とは乖離する可能性があります。"
    "臨床判断・家族状況・退院支援体制を踏まえた最終判断は担当医が行ってください。"
)


# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------

def _safe_date(d) -> Optional[date]:
    """各種日付型を date に変換する。"""
    if d is None:
        return None
    if isinstance(d, date) and not isinstance(d, pd.Timestamp):
        return d
    try:
        return pd.Timestamp(d).date()
    except Exception:
        return None


def _detect_columns(df: pd.DataFrame) -> dict[str, Optional[str]]:
    """detail_df のカラム名を自動検出する。

    bed_data_manager の ADMISSION_DETAIL_COLUMNS 形式と
    日本語カラム形式の両方に対応する。
    """
    mapping: dict[str, Optional[str]] = {
        "date": None,
        "ward": None,
        "event_type": None,
        "route": None,
    }
    # 日付
    for c in ["date", "日付"]:
        if c in df.columns:
            mapping["date"] = c
            break
    # 病棟
    for c in ["ward", "病棟"]:
        if c in df.columns:
            mapping["ward"] = c
            break
    # イベント種別
    for c in ["event_type", "入退院区分"]:
        if c in df.columns:
            mapping["event_type"] = c
            break
    # 経路
    for c in ["route", "経路"]:
        if c in df.columns:
            mapping["route"] = c
            break
    return mapping


def _is_admission_event(event_type_value: str, col_name: str) -> bool:
    """イベントが入院かどうかを判定する。"""
    if col_name == "event_type":
        return str(event_type_value).strip().lower() == "admission"
    # 日本語カラムの場合
    return str(event_type_value).strip() == "入院"


def _is_discharge_event(event_type_value: str, col_name: str) -> bool:
    """イベントが退院かどうかを判定する。"""
    if col_name == "event_type":
        return str(event_type_value).strip().lower() == "discharge"
    return str(event_type_value).strip() == "退院"


def _empty_result(
    ward: Optional[str] = None,
    target_date: Optional[date] = None,
    note: str = "",
) -> dict:
    """空の候補リスト結果を返す。"""
    return {
        "candidates": [],
        "total_candidates": 0,
        "total_adjustable_bed_days": 0,
        "ward": ward,
        "as_of_date": str(target_date) if target_date else None,
        "data_source": _DATA_SOURCE_LABEL,
        "note": note or _PROXY_NOTE,
    }


# ---------------------------------------------------------------------------
# 1. C群候補リスト生成
# ---------------------------------------------------------------------------

def generate_c_group_candidate_list(
    detail_df: Optional[pd.DataFrame] = None,
    daily_df: Optional[pd.DataFrame] = None,
    ward: Optional[str] = None,
    target_date: Optional[date] = None,
    los_threshold: int = C_PHASE_START_DAY,
) -> dict:
    """C群候補リスト（lite版）を生成する。

    入退院詳細データ（detail_df）から、退院イベント未記録の入院患者を抽出し、
    在院日数が los_threshold 以上の患者をC群候補として返す。

    患者レベルのHISデータがないため、これは入退院イベントベースの PROXY である。
    - 入院日 → 現在の在院日数を算出
    - 退院イベント未記録 → まだ入院中と仮定

    Args:
        detail_df: 入退院詳細DataFrame（bed_data_manager形式）。None可。
        daily_df: 日次病棟サマリーDataFrame。現時点では未使用（将来拡張用）。
        ward: 病棟フィルタ（"5F", "6F" 等）。Noneなら全体。
        target_date: 基準日。Noneなら detail_df 内の最新日。
        los_threshold: C群とみなす最低在院日数（デフォルト15日）。

    Returns:
        dict:
            - "candidates": list[dict] — 各候補の情報
            - "total_candidates": int
            - "total_adjustable_bed_days": int
            - "ward": str | None
            - "as_of_date": str
            - "data_source": "proxy"
            - "note": str
    """
    # --- データなしの場合 ---
    if detail_df is None or len(detail_df) == 0:
        return _empty_result(
            ward=ward,
            target_date=target_date,
            note="入退院詳細データがありません。" + _PROXY_NOTE,
        )

    cols = _detect_columns(detail_df)
    date_col = cols["date"]
    ward_col = cols["ward"]
    event_col = cols["event_type"]

    if date_col is None or event_col is None:
        return _empty_result(
            ward=ward,
            target_date=target_date,
            note="必要なカラム（日付・イベント種別）が見つかりません。" + _PROXY_NOTE,
        )

    df = detail_df.copy()
    df[date_col] = pd.to_datetime(df[date_col])

    # --- 基準日の決定 ---
    if target_date is not None:
        ref_date = _safe_date(target_date)
    else:
        ref_date = df[date_col].max().date()

    if ref_date is None:
        return _empty_result(ward=ward, target_date=None, note=_PROXY_NOTE)

    # --- 病棟フィルタ ---
    if ward and ward_col and ward_col in df.columns:
        df = df[df[ward_col] == ward]
        if len(df) == 0:
            return _empty_result(
                ward=ward,
                target_date=ref_date,
                note=f"病棟 {ward} のデータがありません。" + _PROXY_NOTE,
            )

    # --- 入院イベントと退院イベントを分離 ---
    admissions = df[
        df[event_col].apply(lambda x: _is_admission_event(str(x), event_col))
    ].copy()
    discharges = df[
        df[event_col].apply(lambda x: _is_discharge_event(str(x), event_col))
    ].copy()

    if len(admissions) == 0:
        return _empty_result(
            ward=ward,
            target_date=ref_date,
            note="入院イベントがありません。" + _PROXY_NOTE,
        )

    # --- 退院済みの入院日・病棟ペアを特定 ---
    # 同一病棟・同一日の入退院ペアを簡易マッチング
    # 注: 患者IDがないため完全なマッチングは不可能（proxy の限界）
    discharged_keys: set[tuple] = set()
    ward_key = ward_col if ward_col else None

    for _, row in discharges.iterrows():
        d_date = row[date_col]
        los = row.get("los_days", pd.NA)
        w = row[ward_key] if ward_key else "unknown"

        if pd.notna(los):
            try:
                los_int = int(los)
                admission_date = d_date - pd.Timedelta(days=los_int)
                discharged_keys.add((str(w), str(admission_date.date())))
            except (ValueError, TypeError):
                pass

    # --- 未退院の入院イベントを抽出 ---
    route_col = cols["route"]
    candidates: list[dict] = []

    for _, row in admissions.iterrows():
        adm_date = row[date_col]
        adm_date_d = adm_date.date() if hasattr(adm_date, "date") else _safe_date(adm_date)
        if adm_date_d is None:
            continue

        w = row[ward_key] if ward_key else "unknown"
        key = (str(w), str(adm_date_d))

        # 基準日より未来の入院は除外
        if adm_date_d > ref_date:
            continue

        # 退院済みなら除外
        if key in discharged_keys:
            continue

        # 推定在院日数
        estimated_los = (ref_date - adm_date_d).days
        if estimated_los < los_threshold:
            continue

        # 経路
        route = ""
        if route_col and route_col in row.index:
            r = row[route_col]
            route = str(r) if pd.notna(r) else ""

        candidates.append({
            "admission_date": str(adm_date_d),
            "estimated_los": estimated_los,
            "ward": str(w),
            "phase": "C",
            "is_proxy": True,
            "route": route,
        })

    # LOS降順でソート
    candidates.sort(key=lambda c: c["estimated_los"], reverse=True)

    total_adjustable = 0

    return {
        "candidates": candidates,
        "total_candidates": len(candidates),
        "total_adjustable_bed_days": total_adjustable,
        "ward": ward,
        "as_of_date": str(ref_date),
        "data_source": _DATA_SOURCE_LABEL,
        "note": _PROXY_NOTE,
    }


# ---------------------------------------------------------------------------
# 2. 退院緊急度の分類
# ---------------------------------------------------------------------------

def classify_discharge_urgency(
    candidates: list[dict],
    los_limit: float = 21.0,
    current_ward_los: Optional[float] = None,
    emergency_ratio_risk: bool = False,
) -> list[str]:
    """C群候補を病棟全体の平均在院日数と救急搬送比率リスクに基づいて退院緊急度を分類する。

    candidates は estimated_los 降順でソート済みであること。

    判定基準（優先順位）:
    1. 救急搬送比率の未達リスクがある場合 → 退院必要（ベッド確保のため）
    2. 病棟全体LOS > los_limit → 退院シミュレーションで急ぎ度を算出
    3. 病棟全体LOS ≤ los_limit かつ救急リスクなし → 全員まだ在留可能

    Args:
        candidates: C群候補リスト（estimated_los降順）
        los_limit: 平均在院日数の制度上限（日）
        current_ward_los: 病棟全体のrolling平均在院日数。Noneの場合はC群平均で代替
        emergency_ratio_risk: 救急搬送後患者割合の未達リスクがあるか

    Returns:
        list[str]: 各候補に対応するurgencyラベル
            "urgent" = 急ぎ退院必要
            "release" = 退院必要（救急受入枠確保のため）
            "stay_ok" = まだ在留可能
    """
    if not candidates:
        return []

    all_los = [c["estimated_los"] for c in candidates]
    total = len(all_los)

    # 判定基準: 病棟全体のLOSを優先、不明ならC群平均で代替
    reference_los = current_ward_los if current_ward_los is not None else (sum(all_los) / total)

    if reference_los <= los_limit:
        if emergency_ratio_risk:
            # LOS基準内だが救急搬送比率が未達リスク
            # → 在院日数の長い順に「退院必要」（ベッドを空けて救急受入枠を確保）
            return ["release"] * total
        # LOS基準内かつ救急リスクなし → 全員在留可能
        return ["stay_ok"] * total

    # 病棟全体の平均がlos_limitを超過 → 長い順に退院シミュレーション
    # C群候補の平均で代替している場合のシミュレーション
    urgency = ["stay_ok"] * total
    remaining_sum = sum(all_los)
    remaining_count = total

    for i in range(total):
        urgency[i] = "urgent"
        remaining_sum -= all_los[i]
        remaining_count -= 1

        if remaining_count == 0:
            break

        if (remaining_sum / remaining_count) <= los_limit:
            # 残りの人を判定
            for j in range(i + 1, total):
                if all_los[j] > los_limit:
                    urgency[j] = "release"
                else:
                    urgency[j] = "stay_ok"
            break

    return urgency


# ---------------------------------------------------------------------------
# 3. 表示用サマリー
# ---------------------------------------------------------------------------

def summarize_candidates_for_display(
    candidates_result: dict,
    los_limit: float,
    emergency_ratio_risk: bool = False,
    morning_capacity_slots: Optional[int] = None,
    current_ward_los: Optional[float] = None,
) -> dict:
    """候補リストをUI表示用にサマリー化する。

    Args:
        candidates_result: generate_c_group_candidate_list の戻り値。
        los_limit: 平均在院日数の制度上限（日）。
        emergency_ratio_risk: 救急搬送後患者割合のリスクがあるか。
        morning_capacity_slots: 翌朝の空床予測数。None可。
        current_ward_los: 病棟全体のrolling平均在院日数。None可。

    Returns:
        dict:
            - "summary_text": str
            - "table_data": list[dict]
            - "total_adjustable": int
            - "tradeoff_note": str
            - "warning": str | None
            - "data_quality": "proxy"
    """
    candidates = candidates_result.get("candidates", [])
    total = candidates_result.get("total_candidates", 0)
    ward = candidates_result.get("ward")
    as_of = candidates_result.get("as_of_date", "")

    ward_label = f"（{ward}）" if ward else "（全体）"

    # --- 判定（urgency分類）---
    urgency_labels = classify_discharge_urgency(
        candidates, los_limit, current_ward_los, emergency_ratio_risk,
    )

    # --- サマリーテキスト ---
    if total == 0:
        summary_text = (
            f"{ward_label} C群候補はありません（{as_of}時点）。\n"
            "入退院詳細データの入力状況をご確認ください。"
        )
    else:
        # urgency分類で急ぎ退院必要の人数を出す
        urgent_count = sum(1 for u in urgency_labels if u == "urgent")
        release_count = sum(1 for u in urgency_labels if u == "release")
        if urgent_count > 0:
            summary_text = (
                f"{ward_label} C群候補 {total}名（{as_of}時点）\n"
                f"平均在院日数を{los_limit:.0f}日以下にするには、あと{urgent_count}名の退院が必要です。\n"
                "※ 臨床判断・退院支援状況を踏まえてご判断ください。"
            )
        elif release_count > 0 and emergency_ratio_risk:
            summary_text = (
                f"{ward_label} C群候補 {total}名（{as_of}時点）\n"
                f"救急搬送比率の未達リスクがあります。C群退院を進めてベッドを確保し、救急受入を優先してください。\n"
                "※ 臨床判断・退院支援状況を踏まえてご判断ください。"
            )
        else:
            summary_text = (
                f"{ward_label} C群候補 {total}名（{as_of}時点）\n"
                f"病棟全体の平均在院日数は基準内です。稼働率維持のため急ぎの退院調整は不要です。\n"
                "※ 臨床判断・退院支援状況を踏まえてご判断ください。"
            )

    # --- テーブルデータ ---
    table_data: list[dict] = []
    for c, urgency in zip(candidates, urgency_labels):
        table_data.append({
            "入院日": c["admission_date"],
            "在院日数": c["estimated_los"],
            "病棟": c["ward"],
            "経路": c["route"] if c["route"] else "—",
            "判定": {
                "urgent": "🔴 急ぎ退院必要",
                "release": "🟡 退院必要",
                "stay_ok": "🟢 まだ在留可能",
            }.get(urgency, "—"),
        })

    # --- トレードオフ注記 ---
    tradeoff_parts: list[str] = []
    tradeoff_parts.append(
        "C群の退院タイミング調整は、稼働率維持と制度要件のバランスで決定します。"
    )
    if emergency_ratio_risk:
        tradeoff_parts.append(
            "現在、救急搬送後患者割合に未達リスクがあるため、退院→救急受入を優先してください。"
        )
    if morning_capacity_slots is not None and morning_capacity_slots < 3:
        tradeoff_parts.append(
            f"翌朝の空床予測が{morning_capacity_slots}床と少なく、新規受入に影響する可能性があります。"
        )
    tradeoff_note = " ".join(tradeoff_parts)

    # --- 警告 ---
    warning: Optional[str] = None
    if emergency_ratio_risk:
        warning = (
            "⚠ 救急搬送後患者割合の制度要件リスクがあります。"
            "C群の延長よりも退院→空床確保→救急受入を優先してください。"
        )
    elif morning_capacity_slots is not None and morning_capacity_slots < 3:
        warning = (
            f"⚠ 翌朝の空床予測が{morning_capacity_slots}床です。"
            "新規入院受入に支障が出る可能性があります。"
        )

    return {
        "summary_text": summary_text,
        "table_data": table_data,
        "total_adjustable": 0,
        "tradeoff_note": tradeoff_note,
        "warning": warning,
        "data_quality": _DATA_SOURCE_LABEL,
    }
