"""
多職種退院調整・連休対策カンファ資料画面 — Phase 1（UI 骨組み）

木曜ハドル／連休対策カンファで 1 画面（16:9）運用する Streamlit ビュー。
4 ブロック + ファクト下部バーの構成。

Phase 1 の目的:
- サンプルデータで UI の枠を確立する
- 既存モジュール (``target_config`` / ``holiday_calendar`` / ``facts.yaml``) と連携する
- ``data-testid`` 付き hidden div で E2E セレクタを確保する
- モード切替（通常／連休対策）・病棟切替（5F / 6F）の動作確認

Phase 2 以降（未実装、別タスク）:
- ``bed_data_manager`` / ``emergency_ratio`` からの実データ取得
- ステータス更新の永続化（現状は ``st.session_state`` 内のみ）
- 職種別メッセージの動的生成（現状はサンプル文言）

公開関数
---------
- :func:`render_conference_material_view` — メインエントリ

設計ルール
-----------
- 個人情報保護: サンプル患者データも匿名化（姓のみ、ID は UUID 先頭 8 桁）
- ``data-testid`` は hidden div で出力し、E2E テストの正準セレクタにする
- ヘッダー・ブロック境界は HTML モックの CSS をベースに再現（完全再現ではなく割り切り）

参照
-----
- モックアップ: ``docs/admin/conference_material_mockup.html``
- 設計仕様: ``docs/admin/conference_material_design_spec.md``
"""

from __future__ import annotations

import hashlib
import random
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
import yaml

# ---------------------------------------------------------------------------
# sys.path — scripts/ を解決可能にする（views/ 配下から target_config 等を import）
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

# target_config / holiday_calendar は scripts/ 直下
from target_config import (  # noqa: E402
    get_alos_regulatory_limit,
    get_alos_warning_threshold,
    get_emergency_ratio_minimum,
    get_occupancy_target,
)
from holiday_calendar import get_holiday_mode_banner  # noqa: E402
from patient_name_store import (  # noqa: E402
    clear_all_patient_info,
    clear_patient_info,
    load_all_patient_info,
    load_patient_info,
    save_patient_info,
)
from patient_status_store import (  # noqa: E402
    clear_all_statuses,
    clear_status,
    get_stagnant_patients,
    get_status_changes_this_week,
    load_all_statuses,
    load_all_status_history,
    load_status_history,
    save_status,
)


# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

_DEFAULT_WARD = "5F"
_WARD_OPTIONS = ["5F", "6F"]
_MAX_PATIENTS_DISPLAYED = 10

# data/facts.yaml 既定パス
_FACTS_YAML_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "facts.yaml"
)

# ステータスカテゴリ（7 種、通常モード）
# 表示順はモックに合わせる（ただしカード側の優先度とは独立）
_STATUS_NORMAL: List[Dict[str, str]] = [
    {"key": "undecided", "emoji": "⚫", "label": "方向性未決", "bg": "#424242", "fg": "#ffffff"},
    {"key": "medical", "emoji": "🔵", "label": "医学的OK待ち", "bg": "#d1ecf1", "fg": "#0c5460"},
    {"key": "family", "emoji": "🟢", "label": "家族希望待ち", "bg": "#d4edda", "fg": "#155724"},
    {"key": "facility", "emoji": "🟡", "label": "施設待ち", "bg": "#fff3cd", "fg": "#856404"},
    {"key": "insurance", "emoji": "🟣", "label": "介護保険待ち", "bg": "#e2d5f1", "fg": "#5b2c91"},
    {"key": "rehab", "emoji": "🟠", "label": "リハ最適化中", "bg": "#ffe0b2", "fg": "#bf360c"},
    {"key": "new", "emoji": "🆕", "label": "新規", "bg": "#e9ecef", "fg": "#495057"},
]

# 連休対策モードの内訳カテゴリ（4 種 — カンファ開始時の「新規」+ 分類後 3 種）
# "new" はカンファ開始前のデフォルト状態。カンファで各患者を以下の 3 種に振り分ける:
#   - before_confirmed: 連休前退院 確定
#   - before_adjusting: 連休前退院 調整中
#   - continuing: 連休中継続ケア
_STATUS_HOLIDAY: List[Dict[str, str]] = [
    {"key": "before_confirmed", "emoji": "✅", "label": "連休前退院 確定", "bg": "#d4edda", "fg": "#155724"},
    {"key": "before_adjusting", "emoji": "🛠", "label": "連休前退院 調整中", "bg": "#fff3cd", "fg": "#856404"},
    {"key": "continuing", "emoji": "🏥", "label": "連休中継続ケア", "bg": "#e9ecef", "fg": "#495057"},
    {"key": "new", "emoji": "🆕", "label": "新規", "bg": "#e9ecef", "fg": "#495057"},
]


# ---------------------------------------------------------------------------
# データクラス
# ---------------------------------------------------------------------------

@dataclass
class SamplePatient:
    """サンプル患者データ（Phase 1 用）."""

    patient_id: str  # UUID 先頭 8 桁
    doctor_surname: str  # 主治医の姓のみ
    ward: str  # "5F" or "6F"
    day_count: int  # Day N（在院日数）
    planned_date: str  # 退院予定日表示文字列（例: "4/24 (金)" or "未定"）
    status_key: str  # _STATUS_NORMAL / _STATUS_HOLIDAY の key
    note: str  # 確認事項の短文


# ---------------------------------------------------------------------------
# サンプルデータ
# ---------------------------------------------------------------------------

def _sample_patients_5f_normal() -> List[SamplePatient]:
    """5F 通常モード用 10 名のサンプル患者.

    全員の初期ステータスは "new"（🆕 新規）. カンファで各々カテゴライズする流れに統一する.
    """
    return [
        SamplePatient("a1b2c3d4", "伊藤", "5F", 35, "未定", "new",
                      "4/24までに田中医師が退院目処を再評価、要再カンファ"),
        SamplePatient("b2c3d4e5", "渡辺", "5F", 28, "未定", "new",
                      "ADL再評価を佐々木PTに依頼、その後MSWが施設候補検討"),
        SamplePatient("c3d4e5f6", "高橋", "5F", 22, "4/24 (金)", "new",
                      "ご家族面談 4/19 設定、迎え日時の確認"),
        SamplePatient("d4e5f6a7", "田中", "5F", 18, "4/20 (月)", "new",
                      "退院目処 Day 21 を確認、歩行速度+0.1 m/s 達成見込み"),
        SamplePatient("e5f6a7b8", "中村", "5F", 16, "4/21 (火)", "new",
                      "Barthel +5 目標、退院前に ADL 最終評価"),
        SamplePatient("f6a7b8c9", "鈴木", "5F", 15, "4/20 (月)", "new",
                      "主治医に退院可否の最終確認、処方見直し検討"),
        SamplePatient("a7b8c9d0", "加藤", "5F", 14, "未定", "new",
                      "老健 空床確認中、MSW が他施設も打診"),
        SamplePatient("b8c9d0e1", "佐藤", "5F", 12, "4/18 (土)", "new",
                      "認定調査 4/19 予定、ケアマネから連絡待ち"),
        SamplePatient("c9d0e1f2", "小林", "5F", 10, "4/18 (土)", "new",
                      "金朝カンファで退院判定、痛みコントロール確認"),
        SamplePatient("d0e1f2a3", "山田", "5F", 8, "未定", "new",
                      "本日初回カテゴライズ"),
    ]


def _sample_patients_6f_normal() -> List[SamplePatient]:
    """6F 通常モード用 10 名のサンプル患者.

    全員の初期ステータスは "new"（🆕 新規）. カンファで各々カテゴライズする流れに統一する.
    """
    return [
        SamplePatient("e1f2a3b4", "渡辺", "6F", 45, "未定", "new",
                      "慢性痛 神経ブロック継続中、退院目処 再判定保留"),
        SamplePatient("f2a3b4c5", "大野", "6F", 38, "未定", "new",
                      "心不全増悪繰り返し、在宅療養可否を本日判断要"),
        SamplePatient("a3b4c5d6", "松本", "6F", 32, "未定", "new",
                      "誤嚥性肺炎 再発、嚥下評価＋帰宅先調整を本日議論"),
        SamplePatient("b4c5d6e7", "井上", "6F", 27, "4/25 (土)", "new",
                      "老健 4/25 受入内定、搬送手配の確認"),
        SamplePatient("c5d6e7f8", "木村", "6F", 23, "4/24 (金)", "new",
                      "特養空床確認中、優先順位 3 番目"),
        SamplePatient("d6e7f8a9", "林", "6F", 19, "未定", "new",
                      "要介護認定申請中、訪看導入の調整"),
        SamplePatient("e7f8a9b0", "清水", "6F", 16, "4/23 (木)", "new",
                      "ケアマネ初回面談 4/21、担当者会議 4/22"),
        SamplePatient("f8a9b0c1", "山本", "6F", 13, "4/22 (水)", "new",
                      "心機能再評価後、退院可否確定"),
        SamplePatient("a9b0c1d2", "中島", "6F", 11, "4/21 (火)", "new",
                      "独居のため家族調整が必要、長男面談予定"),
        SamplePatient("b0c1d2e3", "森", "6F", 9, "4/20 (月)", "new",
                      "歩行訓練継続中、退院前に浴室動作確認"),
    ]


def _sample_patients_holiday_5f() -> List[SamplePatient]:
    """5F 連休対策モード用 10 名のサンプル患者.

    全員の初期ステータスは "new"（🆕 新規）. カンファで連休対策カテゴリ
    （確定 / 調整中 / 継続ケア）に振り分ける流れに統一する.
    """
    return [
        SamplePatient("h1a1b2c3", "伊藤", "5F", 42, "5/7 (木)", "new",
                      "連休中継続ケア、5/7 退院目標 / 連休中 リハ要員調整済"),
        SamplePatient("h2b2c3d4", "渡辺", "5F", 35, "4/28 (火)", "new",
                      "連休前退院 確定、老健 4/28 受入、転院搬送 本日手配"),
        SamplePatient("h3c3d4e5", "高橋", "5F", 29, "4/28 (火)", "new",
                      "連休前退院 確定、ご家族迎え 4/28 午後、処方7日分準備"),
        SamplePatient("h4d4e5f6", "田中", "5F", 25, "4/28 (火)", "new",
                      "連休前退院 調整中、主治医に4/28可否を本日確認"),
        SamplePatient("h5e5f6a7", "中村", "5F", 23, "4/28 (火)", "new",
                      "連休前退院 調整中、家族が連休中に旅行予定 → 前倒し交渉"),
        SamplePatient("h6f6a7b8", "鈴木", "5F", 22, "4/28 (火)", "new",
                      "連休前退院 調整中、連休中処方と頓用指示を確定"),
        SamplePatient("h7a7b8c9", "加藤", "5F", 21, "5/7 (木)", "new",
                      "連休中継続ケア、老健 5/7 受入、連休中 機能維持リハ"),
        SamplePatient("h8b8c9d0", "佐藤", "5F", 19, "4/28 (火)", "new",
                      "連休前退院 調整中、認定調査 4/26 前倒し依頼済"),
        SamplePatient("h9c9d0e1", "小林", "5F", 17, "5/7 (木)", "new",
                      "連休中継続ケア、連休明けカンファで方針再確認"),
        SamplePatient("h0d0e1f2", "山田", "5F", 15, "4/28 (火)", "new",
                      "連休前退院 確定、自宅での自主訓練指導 本日実施"),
    ]


def _sample_patients_holiday_6f() -> List[SamplePatient]:
    """6F 連休対策モード用 10 名のサンプル患者.

    全員の初期ステータスは "new"（🆕 新規）. カンファで連休対策カテゴリ
    （確定 / 調整中 / 継続ケア）に振り分ける流れに統一する.
    """
    return [
        SamplePatient("h1e1f2a3", "渡辺", "6F", 50, "5/8 (金)", "new",
                      "連休中継続ケア、心不全経過観察 / 処方調整継続"),
        SamplePatient("h2f2a3b4", "大野", "6F", 43, "5/7 (木)", "new",
                      "連休中継続ケア、連休明けに再評価"),
        SamplePatient("h3a3b4c5", "松本", "6F", 37, "4/28 (火)", "new",
                      "連休前退院 調整中、嚥下評価次第で 4/28 可否判断"),
        SamplePatient("h4b4c5d6", "井上", "6F", 32, "4/28 (火)", "new",
                      "連休前退院 確定、施設搬送 4/28 手配済"),
        SamplePatient("h5c5d6e7", "木村", "6F", 28, "4/28 (火)", "new",
                      "連休前退院 調整中、特養受入可否の最終確認"),
        SamplePatient("h6d6e7f8", "林", "6F", 24, "5/7 (木)", "new",
                      "連休中継続ケア、訪看導入準備と家族説明"),
        SamplePatient("h7e7f8a9", "清水", "6F", 21, "4/28 (火)", "new",
                      "連休前退院 確定、ケアマネと担当者会議完了"),
        SamplePatient("h8f8a9b0", "山本", "6F", 18, "4/28 (火)", "new",
                      "連休前退院 調整中、心機能再評価後 4/28 可否"),
        SamplePatient("h9a9b0c1", "中島", "6F", 16, "4/28 (火)", "new",
                      "連休前退院 調整中、長男の迎え時間調整"),
        SamplePatient("h0b0c1d2", "森", "6F", 14, "5/7 (木)", "new",
                      "連休中継続ケア、歩行訓練継続 / 浴室動作練習"),
    ]


def _get_sample_patients(ward: str, mode: str) -> List[SamplePatient]:
    """病棟×モード組合せのサンプル患者 10 名を返す."""
    if mode == "holiday":
        return _sample_patients_holiday_5f() if ward == "5F" else _sample_patients_holiday_6f()
    return _sample_patients_5f_normal() if ward == "5F" else _sample_patients_6f_normal()


# ---------------------------------------------------------------------------
# 実データ連携（2026-04-18）
# ---------------------------------------------------------------------------
# 実績データ（日次入力）モード時、bed_data_manager の admission_details から
# 現在入院中の患者リストを生成する。カンファビューでサンプルではなく実データを
# 使うためのデータ経路。
#
# マッチング戦略（get_short3_day5_patients と整合）:
#   - admission / discharge は別レコード。患者 ID が直接ひもづかないため、
#     (ward, admission_date) の組を「退院済みキー」として構築し、
#     admission 側でキーにマッチしないものを「現在入院中」とみなす。
#
# データ取得源:
#   - st.session_state["admission_details"]（bed_control_simulator_app.py が起動時に
#     data/admission_details.csv から読み込む）。
#   - テスト時は df_override パラメータで直接注入可能。
#
# 匿名化:
#   - admission の `id`（UUID）を SHA256 → 先頭 8 桁を patient_id として使う。
#     同じ admission には常に同じ UUID が生成される（永続性）。
#   - 主治医は姓のみ（attending_doctor 列は通常「姓 名」か「姓」なので
#     先頭トークンを採用）。
#   - note は実データには含まれないため、入院経路 (route) を表示する。


def _anonymize_patient_id(raw_id) -> str:
    """任意の admission ID から安定した 8 桁の匿名 ID を生成.

    None / pd.NA / 空文字列はすべて定数プレースホルダに変換。
    """
    import pandas as pd  # 遅延 import

    if raw_id is None:
        return "00000000"
    try:
        if pd.isna(raw_id):
            return "00000000"
    except (TypeError, ValueError):
        pass
    s = str(raw_id)
    if s == "" or s.lower() == "nan":
        return "00000000"
    h = hashlib.sha256(s.encode("utf-8")).hexdigest()
    return h[:8]


def _extract_surname(full_name) -> str:
    """医師フルネームから姓のみ抽出（姓名がスペース区切りを想定、そうでなければそのまま）.

    pd.NA / None / 空文字列はすべて「未定」にフォールバック。
    """
    import pandas as pd  # 遅延 import

    if full_name is None:
        return "未定"
    # pd.NA / NaN を安全に判定
    try:
        if pd.isna(full_name):
            return "未定"
    except (TypeError, ValueError):
        pass
    s = str(full_name).strip()
    if s == "" or s.lower() == "nan" or s == "<NA>":
        return "未定"
    if " " in s:
        return s.split(" ", 1)[0]
    if "　" in s:
        return s.split("　", 1)[0]
    # スペースなし → 姓のみか氏名一体かの判別は難しい。2-3 文字に切り詰める（姓として一般的）
    if len(s) > 3:
        return s[:3]
    return s


def _build_discharged_keys(detail_df) -> set:
    """admission_details の discharge レコードから (ward, admission_date_iso) のキー集合を作る.

    注意: discharge レコードは los_days を持つが、admission_date 列は持たない。
    admission_date は discharge_date - los_days で復元する。
    この復元は短手3 判定（get_short3_day5_patients）と同じ戦略。
    """
    import pandas as pd  # 遅延 import（views/ がアプリ以外でも import される場合のため）

    discharged: set = set()
    if detail_df is None or len(detail_df) == 0:
        return discharged
    if not hasattr(detail_df, "columns"):
        return discharged
    required = {"event_type", "date", "ward", "los_days"}
    if not required.issubset(set(detail_df.columns)):
        return discharged

    try:
        discharges = detail_df[detail_df["event_type"].astype(str) == "discharge"]
    except Exception:
        return discharged

    for _, row in discharges.iterrows():
        los_raw = row.get("los_days", "")
        if los_raw in (None, ""):
            continue
        try:
            if pd.isna(los_raw):
                continue
        except (TypeError, ValueError):
            pass
        try:
            los_int = int(float(los_raw))
        except (ValueError, TypeError):
            continue
        try:
            d_date = pd.to_datetime(row.get("date", "")).date()
        except Exception:
            continue
        try:
            adm_date = d_date - timedelta(days=los_int)
        except Exception:
            continue
        ward_val = str(row.get("ward", ""))
        discharged.add((ward_val, adm_date.isoformat()))
    return discharged


def _patients_from_actual_data(
    today: date,
    ward: str,
    mode: str,
    *,
    df_override=None,
    max_patients: int = _MAX_PATIENTS_DISPLAYED,
) -> Tuple[List[SamplePatient], Dict[str, Any]]:
    """実績データ（admission_details）から現在入院中の患者を SamplePatient リストに変換.

    Parameters
    ----------
    today : date
        基準日（在院日数計算に使う）。
    ward : str
        "5F" or "6F"。フィルタ条件。
    mode : str
        "normal" or "holiday"（note の文言生成に影響するが現時点では影響軽微）。
    df_override : pd.DataFrame, optional
        テスト用。None の場合 ``st.session_state["admission_details"]`` を参照。
    max_patients : int
        表示上限。デフォルト 10。

    Returns
    -------
    (patients, meta)
        patients : List[SamplePatient]
            実データから抽出された現在入院中の患者（最大 max_patients 名）。
            空の場合もあり（呼び出し元でフォールバック／情報バナーを判断）。
        meta : Dict[str, Any]
            {
                "total_inpatients": int,   # 表示上限前の全在院者数
                "data_unavailable": bool,  # admission_details が無い／空
                "reason": str,             # "ok" / "no_data" / "no_inpatients" / "error"
            }

    Notes
    -----
    - admission_details がセッション中に未登録・空の場合は空リストを返す
      (呼び出し元で警告を出す)。
    - matching は get_short3_day5_patients と同じく (ward, admission_date) キーで行う。
    """
    import pandas as pd  # 遅延 import

    meta: Dict[str, Any] = {
        "total_inpatients": 0,
        "data_unavailable": False,
        "reason": "ok",
    }

    # DataFrame の取得 -------------------------------------------------------
    detail_df = df_override
    if detail_df is None:
        try:
            detail_df = st.session_state.get("admission_details")
        except Exception:
            detail_df = None

    if detail_df is None:
        meta["data_unavailable"] = True
        meta["reason"] = "no_data"
        return [], meta
    if not isinstance(detail_df, pd.DataFrame) or len(detail_df) == 0:
        meta["data_unavailable"] = True
        meta["reason"] = "no_data"
        return [], meta

    required_cols = {"event_type", "date", "ward"}
    if not required_cols.issubset(set(detail_df.columns)):
        meta["data_unavailable"] = True
        meta["reason"] = "error"
        return [], meta

    # 退院済みキー（(ward, admission_date) 集合）----------------------------
    try:
        discharged_keys = _build_discharged_keys(detail_df)
    except Exception:
        discharged_keys = set()

    # admission から現在入院中を抽出 ---------------------------------------
    try:
        admissions = detail_df[detail_df["event_type"].astype(str) == "admission"]
    except Exception:
        meta["reason"] = "error"
        return [], meta

    current_inpatients: List[SamplePatient] = []
    for _, row in admissions.iterrows():
        w = str(row.get("ward", ""))
        if w != ward:
            continue
        # 入院日
        try:
            adm_date = pd.to_datetime(row.get("date", "")).date()
        except Exception:
            continue
        # 退院済みならスキップ
        key = (w, adm_date.isoformat())
        if key in discharged_keys:
            continue
        # 基準日より後に入院したレコード（将来予約）はスキップ
        if adm_date > today:
            continue

        # 在院日数: Day 1 = 入院当日
        day_count = max(1, (today - adm_date).days + 1)

        # 主治医（attending_doctor から姓を抽出、空なら「未定」）
        doctor_surname = _extract_surname(row.get("attending_doctor", ""))

        # 入院経路を note として表示（実データは予定退院日を持たないため「未定」）
        route = row.get("route", "")
        try:
            if pd.isna(route):
                route = ""
        except (TypeError, ValueError):
            pass
        note = f"（実データ）入院経路: {route}" if route else "（実データ）"

        anon_id = _anonymize_patient_id(str(row.get("id", "")))

        current_inpatients.append(
            SamplePatient(
                patient_id=anon_id,
                doctor_surname=doctor_surname or "未定",
                ward=ward,
                day_count=int(day_count),
                planned_date="未定",
                status_key="new",
                note=note,
            )
        )

    meta["total_inpatients"] = len(current_inpatients)
    if len(current_inpatients) == 0:
        meta["reason"] = "no_inpatients"

    # 在院日数降順で上位 max_patients 名 -----------------------------------
    current_inpatients.sort(key=lambda p: p.day_count, reverse=True)
    return current_inpatients[:max_patients], meta


def _resolve_patients(
    today: date,
    ward: str,
    mode: str,
    *,
    data_source_override: Optional[str] = None,
    df_override=None,
) -> Tuple[List[SamplePatient], str, Dict[str, Any]]:
    """データソース判定 → 患者リスト取得のエントリ.

    Returns
    -------
    (patients, source_tag, meta)
        patients : List[SamplePatient]
        source_tag : "actual" or "sample"
        meta : dict（source_tag == "actual" の場合のみ _patients_from_actual_data の meta）
    """
    if data_source_override is not None:
        ds = data_source_override
    else:
        try:
            ds = st.session_state.get("data_source_mode", "")
        except Exception:
            ds = ""

    # 文字列ラベルを比較（app 側の定義と合わせる）
    is_actual = ds == "📋 実績データ（日次入力）"

    if is_actual:
        patients, meta = _patients_from_actual_data(
            today, ward, mode, df_override=df_override,
        )
        return patients, "actual", meta

    return _get_sample_patients(ward, mode), "sample", {
        "total_inpatients": 10,
        "data_unavailable": False,
        "reason": "ok",
    }


def _sample_kpi_metrics(ward: str) -> Dict[str, float]:
    """病棟別サンプル KPI 値（データ未読込時のフォールバック）.

    実データ連携が可能な場合は :func:`_compute_live_kpi_metrics` を優先し、
    その関数が ``None`` を返したときのみこのサンプルを使う。
    """
    if ward == "5F":
        return {
            "occupancy_pct": 85.0,
            "alos_days": 17.5,
            "emergency_pct": 17.0,
            "remaining_business_days": 9.0,
            "required_bed_days": 28.0,
        }
    return {
        "occupancy_pct": 82.0,
        "alos_days": 18.8,
        "emergency_pct": 14.0,
        "remaining_business_days": 9.0,
        "required_bed_days": 34.0,
    }


def _compute_live_kpi_metrics(
    ward: str,
    today: date,
    *,
    session_state: Optional[Any] = None,
    detail_df_override=None,
    ward_dfs_override: Optional[Dict[str, Any]] = None,
    ward_dfs_full_override: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, float]]:
    """「本日のサマリー」と同じデータソースから Block A の KPI を計算する.

    副院長決定 (2026-04-18): サマリー上部と Block A が乖離して見える
    (例: サマリー 86.5% / カンファ 85%) 問題を解消するため、同じ
    ``st.session_state`` の ward_raw_dfs / admission_details を参照し、
    同一の計算関数 (``calculate_rolling_los`` / ``calculate_emergency_ratio``)
    を呼ぶ。

    Returns
    -------
    dict or None
        計算に必要なデータが揃っている場合のみ dict を返す。
        揃っていない場合は ``None`` を返し、呼び出し側で
        :func:`_sample_kpi_metrics` にフォールバックする。

    Notes
    -----
    - ``occupancy_pct`` は ``ward_raw_dfs[ward]["occupancy_rate"].mean() * 100``
      (サマリー「月平均稼働率」と同じ式)
    - ``alos_days`` は ``calculate_rolling_los(ward_raw_dfs_full[ward], window_days=90)``
      の ``rolling_los_ex_short3`` (なければ ``rolling_los``)
      — サマリー「📏 在院日数(90日rolling)」と同じ式
    - ``emergency_pct`` は ``_calc_emergency_ratio_with_gate`` 互換で病棟別に
      計算。経過措置中 (~2026-05-31) は単月、本則適用後 (2026-06-01~) は
      rolling 3ヶ月。admission_details が無ければ None を返す。
    - 3 指標のいずれかが取得できない場合は、取得できた分だけ上書きし、
      残りはサンプル値でフォールバックする (部分的実データ表示を許容)。
    - ``ward == "全体"`` は本ビューでは想定外 (_WARD_OPTIONS は ["5F", "6F"])
      だが念のため全病棟合算の挙動に対応する。
    """
    # セッションステート取得 — st 未初期化 (テストから直接呼ぶ場合) もケア
    if session_state is None:
        try:
            session_state = st.session_state
        except Exception:
            return None

    # 取得: 病棟別 raw DataFrame (current month / full)
    ward_dfs = ward_dfs_override if ward_dfs_override is not None else (
        session_state.get("sim_ward_raw_dfs")
        or session_state.get("ward_raw_dfs")
        or {}
    )
    ward_dfs_full = ward_dfs_full_override if ward_dfs_full_override is not None else (
        session_state.get("sim_ward_raw_dfs_full")
        or session_state.get("ward_raw_dfs_full")
        or {}
    )

    # データが全く無い場合は None を返してサンプルフォールバック
    if not ward_dfs and not ward_dfs_full:
        return None

    # サンプルをベースに、取得できた実データで上書きする (部分実データ戦略)
    result: Dict[str, float] = dict(_sample_kpi_metrics(ward))

    # --- 稼働率 (サマリーと完全一致する式) ---
    # サマリー (_render_ward_kpi_with_alert) は ward_raw_dfs[ward] の
    # "occupancy_rate" 列の mean() * 100 を月平均稼働率として表示する。
    # カンファ Block A も同じ式で計算する。
    target_df = None
    if ward in ward_dfs:
        target_df = ward_dfs.get(ward)
    if target_df is None or not hasattr(target_df, "columns"):
        # full データでフォールバック (current month フィルタ前)
        if ward in ward_dfs_full:
            target_df = ward_dfs_full.get(ward)

    occ_updated = False
    if target_df is not None and hasattr(target_df, "columns") and len(target_df) > 0:
        try:
            occ_col = "occupancy_rate" if "occupancy_rate" in target_df.columns else "稼働率"
            occ_series = target_df[occ_col]
            occ_mean = float(occ_series.mean())
            # occupancy_rate は 0-1 ratio, 稼働率 は 0-100 または 0-1
            if occ_col == "occupancy_rate":
                occ_pct = occ_mean * 100
            else:
                occ_pct = occ_mean * 100 if occ_mean < 1.5 else occ_mean
            result["occupancy_pct"] = round(occ_pct, 1)
            occ_updated = True
        except Exception:
            pass

    # --- 平均在院日数 (サマリーと同じ 90 日 rolling) ---
    # サマリー (_ward_rolling_results) は calculate_rolling_los() の
    # rolling_los_ex_short3 (無ければ rolling_los) を表示する。
    full_target_df = ward_dfs_full.get(ward) if ward in ward_dfs_full else target_df
    if full_target_df is not None and hasattr(full_target_df, "columns") and len(full_target_df) > 0:
        try:
            # 遅延 import で循環 / テスト時 import コスト回避
            from bed_data_manager import calculate_rolling_los as _calc_rolling_los
            monthly_summary = session_state.get("monthly_summary") if hasattr(session_state, "get") else None
            rolling = _calc_rolling_los(
                full_target_df,
                window_days=90,
                monthly_summary=monthly_summary,
                ward=ward if ward in ("5F", "6F") else None,
            )
            if rolling is not None:
                los_val = rolling.get("rolling_los_ex_short3") or rolling.get("rolling_los")
                if los_val is not None:
                    result["alos_days"] = round(float(los_val), 1)
        except Exception:
            pass

    # --- 救急搬送後患者割合 (サマリー/意思決定ダッシュボードと同じロジック) ---
    detail_df = detail_df_override if detail_df_override is not None else (
        session_state.get("admission_details") if hasattr(session_state, "get") else None
    )
    has_details = detail_df is not None and hasattr(detail_df, "columns") and len(detail_df) > 0
    if has_details:
        try:
            # 遅延 import — emergency_ratio を本ビューが直接依存しないように
            from emergency_ratio import (
                calculate_emergency_ratio as _calc_er,
                calculate_rolling_emergency_ratio as _calc_rolling_er,
                is_transitional_period as _is_transitional,
                load_manual_seeds_from_yaml as _load_seeds,
            )
            target_ward = ward if ward in ("5F", "6F") else None
            ym = f"{today.year:04d}-{today.month:02d}"
            if _is_transitional(today):
                # 経過措置中 (~2026-05-31): 単月判定
                er = _calc_er(detail_df, ward=target_ward, year_month=ym, target_date=today)
            else:
                # 本則完全適用 (2026-06-01~): rolling 3ヶ月
                # 過去月の実データ不足時に備えて手動シード YAML を読み込む
                seeds = _load_seeds()
                er = _calc_rolling_er(
                    detail_df,
                    ward=target_ward,
                    target_date=today,
                    window_months=3,
                    manual_seeds=seeds if seeds else None,
                )
            if er is not None and er.get("ratio_pct") is not None:
                result["emergency_pct"] = round(float(er["ratio_pct"]), 1)
                # シードが採用された月があれば記録する（KPI キャプション用）
                seed_months = er.get("seed_used_months") or []
                if seed_months:
                    result["emergency_seed_months"] = seed_months
                    result["emergency_calculation_method"] = er.get(
                        "calculation_method", "mean_of_ratios_with_seeds"
                    )
        except Exception:
            pass

    # --- 残り診療日 / 必要床日 ---
    # カレンダー上の月末までの日数 (サマリーの _calc_remaining_days と同じ簡易式)
    try:
        import calendar as _cal
        last_day = _cal.monthrange(today.year, today.month)[1]
        remaining = max(0, last_day - today.day)
        result["remaining_business_days"] = float(remaining)
    except Exception:
        pass

    # 必要床日 = (目標稼働率 - 現在月平均稼働率) × 残日数 × 病棟床数
    # 既にサマリーで達成している場合は 0。
    try:
        from bed_data_manager import get_ward_beds as _get_ward_beds
        ward_beds = _get_ward_beds(ward) if ward in ("5F", "6F") else 94
        target_pct = float(get_occupancy_target(ward, month=today))  # 90.0 等
        gap_pct = max(0.0, target_pct - float(result["occupancy_pct"]))
        rem = float(result.get("remaining_business_days", 0.0))
        # 必要床日 ≈ gap_pct/100 × ward_beds × 残日数
        required = round(gap_pct / 100.0 * ward_beds * rem, 0)
        result["required_bed_days"] = float(required)
    except Exception:
        pass

    # occ_updated すら出来ていない場合はサンプルだけを返す形になるが、
    # 上位の _render_block_a はサンプル dict も受け付けるので問題ない。
    # ただし 1 指標も更新できなかった場合は None を返し、呼び出し側で
    # 明示的にサンプルを使う (将来的にテストや警告表示が可能になる)。
    # データ自体は取れているが計算に失敗した場合のみ部分実データを返す。
    if not occ_updated and not has_details:
        return None
    return result


def _sample_weekend_forecast(ward: str, mode: str) -> List[Dict[str, Any]]:
    """週末または連休の見通し（Phase 1 はサンプル）."""
    if mode == "holiday":
        # 連休 5 日分（GW 想定のサンプル）
        if ward == "5F":
            return [
                {"day": "4/29水", "vacancy": 11, "er_margin": -3, "severity": "danger"},
                {"day": "4/30木", "vacancy": 13, "er_margin": -4, "severity": "danger"},
                {"day": "5/1金", "vacancy": 14, "er_margin": -5, "severity": "danger"},
                {"day": "5/2土", "vacancy": 15, "er_margin": -5, "severity": "danger"},
                {"day": "5/3日", "vacancy": 13, "er_margin": -3, "severity": "danger"},
            ]
        return [
            {"day": "4/29水", "vacancy": 9, "er_margin": -2, "severity": "danger"},
            {"day": "4/30木", "vacancy": 11, "er_margin": -3, "severity": "danger"},
            {"day": "5/1金", "vacancy": 12, "er_margin": -4, "severity": "danger"},
            {"day": "5/2土", "vacancy": 13, "er_margin": -4, "severity": "danger"},
            {"day": "5/3日", "vacancy": 12, "er_margin": -3, "severity": "danger"},
        ]
    # 通常モードは金土日の 3 日分
    if ward == "5F":
        return [
            {"day": "金", "vacancy": 4, "er_margin": 2, "severity": "warn"},
            {"day": "土", "vacancy": 8, "er_margin": -1, "severity": "danger"},
            {"day": "日", "vacancy": 7, "er_margin": 0, "severity": "warn"},
        ]
    return [
        {"day": "金", "vacancy": 3, "er_margin": 1, "severity": "warn"},
        {"day": "土", "vacancy": 5, "er_margin": 0, "severity": "warn"},
        {"day": "日", "vacancy": 4, "er_margin": 0, "severity": "warn"},
    ]


# ---------------------------------------------------------------------------
# facts.yaml ローダー + 重み付き抽選
# ---------------------------------------------------------------------------

def _load_facts(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """facts.yaml を読み込んで facts リストを返す（失敗時は空リスト）."""
    p = path if path is not None else _FACTS_YAML_PATH
    if not p.exists():
        return []
    try:
        with open(p, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except (yaml.YAMLError, OSError):
        return []
    if not isinstance(data, dict):
        return []
    facts = data.get("facts") or []
    if not isinstance(facts, list):
        return []
    return facts


def _select_fact(
    facts: List[Dict[str, Any]],
    ward: str,
    mode: str,
    rng: Optional[random.Random] = None,
    *,
    rotation_only: bool = True,
) -> Optional[Dict[str, Any]]:
    """現在の ward / mode に合致するファクトを weight 付き重み抽選で 1 件返す.

    Parameters
    ----------
    facts : list
        YAML からロードしたファクトリスト
    ward : str
        "5F" | "6F"
    mode : str
        "normal" | "holiday"
    rng : random.Random, optional
        乱数生成器（テスト用）。None なら ``random.Random()`` 新規生成。
    rotation_only : bool, optional
        2026-04-18 副院長指示で追加. True (デフォルト) なら
        ``rotation_eligible=True`` のファクトのみを候補にする.
        「退院調整が医学的エビデンスに反する印象を避ける」ため、
        下部バーのローテーション表示は入院延長×リハ介入×高齢者予後改善を
        示すエビデンス（12 件）に限定する. False ならこの制約を外す
        （互換用、主にテスト用）.

    Returns
    -------
    dict or None
        合致するファクト 1 件、なければ None
    """
    if not facts:
        return None
    candidates: List[Dict[str, Any]] = []
    weights: List[float] = []
    for fact in facts:
        if rotation_only and fact.get("rotation_eligible") is not True:
            continue
        ctx = fact.get("context") or {}
        wards = ctx.get("wards") or []
        modes = ctx.get("modes") or []
        if ward not in wards:
            continue
        if mode not in modes:
            continue
        w = ctx.get("weight", 1)
        try:
            weight_val = float(w)
        except (TypeError, ValueError):
            weight_val = 1.0
        if weight_val <= 0:
            continue
        candidates.append(fact)
        weights.append(weight_val)
    if not candidates:
        return None
    _rng = rng if rng is not None else random.Random()
    # weighted sampling
    chosen = _rng.choices(candidates, weights=weights, k=1)[0]
    return chosen


# ---------------------------------------------------------------------------
# 折りたたみ UI 用: ファクトをレイヤー別にグループ化するヘルパー
# ---------------------------------------------------------------------------

# 折りたたみ expander 用のレイヤー表示順序と見出し（副院長指示 2026-04-18）
# - レイヤー 1 / 3 を冒頭に置く（ローテーション対象と同じ領域を勉強目的に）
# - 以降 2 / 4 / 5 / 7 / 6 の順で「退院判断」「多職種」「NS」「統計」「安全」と続ける
_EXPANDER_LAYER_ORDER: List[Dict[str, Any]] = [
    {"layer": 1, "emoji": "🏃", "title": "入院リハ強化で予後改善"},
    {"layer": 3, "emoji": "⏱", "title": "リハビリの時間・強度・継続"},
    {"layer": 2, "emoji": "🛌", "title": "退院タイミング判断"},
    {"layer": 4, "emoji": "🤝", "title": "多職種カンファ・退院支援"},
    {"layer": 5, "emoji": "👩‍⚕️", "title": "退院支援看護師の専門性"},
    {"layer": 7, "emoji": "📊", "title": "病棟運営・国内統計"},
    {"layer": 6, "emoji": "⚠️", "title": "安全性・反証"},
]


def _group_facts_by_layer(
    facts: List[Dict[str, Any]],
) -> Dict[int, List[Dict[str, Any]]]:
    """facts を layer 番号でグループ化して返す（id 昇順でソート）."""
    grouped: Dict[int, List[Dict[str, Any]]] = {}
    for fact in facts:
        layer = fact.get("layer")
        if not isinstance(layer, int):
            continue
        grouped.setdefault(layer, []).append(fact)
    # id 昇順でソート
    for layer, items in grouped.items():
        items.sort(key=lambda f: str(f.get("id", "")))
    return grouped


def _filter_facts_by_keyword(
    facts: List[Dict[str, Any]],
    keyword: str,
) -> List[Dict[str, Any]]:
    """キーワードを含むファクトだけに絞り込む（text / author / journal 対象）."""
    kw = (keyword or "").strip().lower()
    if not kw:
        return facts
    hits: List[Dict[str, Any]] = []
    for fact in facts:
        haystacks = [
            str(fact.get("text", "")),
            str(fact.get("author", "")),
            str(fact.get("journal", "")),
            str(fact.get("layer_name", "")),
        ]
        blob = " ".join(haystacks).lower()
        if kw in blob:
            hits.append(fact)
    return hits


# ---------------------------------------------------------------------------
# CSS 注入
# ---------------------------------------------------------------------------

def _inject_css() -> None:
    """画面共通の CSS を注入する（モック HTML に近いルック）.

    2026-04-18 副院長指示で「1920x1080 で全要素が1画面収納」を目標に圧縮実施.
    Streamlit デフォルトの余白（block-container padding 96+160px, gap 16px）を
    極小化し、patient 行の popover ボタン高さを 40px → 22px に下げる.

    2026-04-18 追加調整（副院長指示）: 770px への圧縮は「縮めすぎ」で文字が重なって
    読みにくい状態のため、125% 拡大（~960px）で視認性を回復する.
    「ヘッダーとエビデンスがギリギリ収まる」を目標にし、文字重なりを解消する.

    印刷時にファクトバーを非表示にする ``@media print`` も同時に注入する。
    """
    st.markdown(
        """
        <style>
        /* ========================================================
           1. Streamlit デフォルト余白の圧縮（1画面収納の主役）
           ======================================================== */
        /* block-container の大きな上下パディング（96+160px）を削減 */
        section[data-testid="stMainBlockContainer"],
        .main .block-container,
        .block-container {
            padding-top: 1.5rem !important;
            padding-bottom: 0.5rem !important;
            max-width: 100% !important;
        }
        /* トップレベル要素間のギャップ（125%拡大: 0.25rem → 0.3rem） */
        section[data-testid="stMainBlockContainer"] > div[data-testid="stVerticalBlock"] {
            gap: 0.3rem !important;
        }
        /* コンテナ幅拡張（互換） */
        .conf-root .block-container { padding-top: 1rem; padding-bottom: 0.5rem; }
        /* ========================================================
           2. ヘッダー（125%拡大: padding 6→8, title 15→16）
           ======================================================== */
        .conf-header {
            background: #2c3e50;
            color: #fff;
            padding: 8px 16px;
            border-radius: 4px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-family: "Hiragino Sans", "Yu Gothic", "Meiryo", sans-serif;
            margin-bottom: 5px;
        }
        .conf-header .title { font-size: 16px; font-weight: 600; }
        .conf-header .mode {
            background: #e67e22;
            padding: 3px 10px;
            border-radius: 4px;
            font-size: 12px;
            margin-left: 8px;
        }
        .conf-header .mode.holiday {
            background: #c0392b;
            font-weight: 700;
        }
        .conf-header .meta { font-size: 13px; opacity: 0.9; }
        .conf-header .meta .days.urgent { color: #ff6b6b; font-weight: 700; }
        .conf-header .meta .days.warning { color: #f39c12; font-weight: 600; }
        /* ========================================================
           3. KPI 行（2026-04-18 105%拡大: padding 6→8, value 22→23）
           ======================================================== */
        .conf-kpi-row {
            background: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 4px;
            padding: 8px 12px;
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 12px;
            margin-bottom: 6px;
        }
        .conf-kpi { text-align: center; line-height: 1.25; }
        .conf-kpi .label { font-size: 11px; color: #666; }
        .conf-kpi .value {
            font-size: 23px;
            font-weight: 700;
            color: #2c3e50;
        }
        .conf-kpi .value.warning { color: #e67e22; }
        .conf-kpi .value.danger { color: #c0392b; }
        .conf-kpi .value.good { color: #27ae60; }
        .conf-kpi .unit { font-size: 12px; color: #666; font-weight: normal; }
        .conf-kpi .target { font-size: 11px; color: #888; }
        /* ステータスタグ（Block B の内訳で使用する静的表示） */
        .conf-status-tag {
            display: inline-block;
            padding: 2px 10px;
            border-radius: 10px;
            font-size: 12px;
            font-weight: 600;
            white-space: nowrap;
        }
        /* ========================================================
           5. 患者行（2026-04-18 105%拡大: min-height 26→28）
           ======================================================== */
        /* 患者行 — 医師/患者 170px / 病棟 32px / Day 46px / 予定 72px / 確認事項 1fr
           ステータスと編集は Streamlit 列側に分離（popover クリック用） */
        .conf-patient-row {
            display: grid;
            grid-template-columns: 170px 32px 46px 72px 1fr;
            gap: 6px;
            align-items: center;
            padding: 3px 8px;
            font-size: 12px;
            border-bottom: 1px solid #f3f3f3;
            line-height: 1.3;
            min-height: 28px;
        }
        /* v4 新機能（2026-04-19、対応策 B）: 前回カンファから変化のあった
           患者行の左端にグレーハイライトを付与。台本（carnf_scenario_v4.md
           第0章「黒帯のハイライトが付いているのが前回から変わった患者さん」）
           の記述と実画面を一致させる. */
        .conf-patient-row-changed {
            border-left: 4px solid #9CA3AF !important;
            padding-left: 6px !important;
            background: linear-gradient(
                90deg,
                rgba(156, 163, 175, 0.08) 0%,
                rgba(156, 163, 175, 0.02) 30%,
                transparent 60%
            );
        }
        /* ブロック C ヘッダー統合ラッパー（タイトル + バッジ、重なり回避） */
        .conf-block-c-header-wrap {
            margin-bottom: 10px;
        }
        .conf-block-c-title-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 6px;
        }
        .conf-block-c-title {
            font-size: 14px;
            font-weight: 700;
            color: #555;
        }
        .conf-block-c-count {
            font-size: 12px;
            color: #666;
        }
        /* ブロック C 冒頭の「📝 前回からの変化」要約バッジ（v4 新機能） */
        .conf-block-c-summary {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 8px;
            padding: 6px 10px;
            margin-top: 0;
            margin-bottom: 0;
            font-size: 12px;
            color: #374151;
            background: #F3F4F6;
            border-left: 3px solid #6B7280;
            border-radius: 2px;
        }
        .conf-block-c-summary .summary-label {
            font-weight: 600;
            color: #1F2937;
        }
        .conf-block-c-summary .summary-item b {
            color: #2563EB;
            font-size: 13px;
        }
        .conf-block-c-summary .summary-sep {
            color: #9CA3AF;
            font-weight: 300;
        }
        .conf-block-c-summary .summary-hint {
            color: #6B7280;
            font-size: 11px;
            margin-left: auto;
        }
        .conf-block-c-summary-empty {
            background: #FAFAFA;
            border-left-color: #D1D5DB;
            color: #6B7280;
        }
        .conf-block-c-summary-empty .summary-empty {
            font-style: italic;
            font-size: 11px;
        }
        /* ヘッダー行専用クラス:
           重なり防止のため、下側に明示的な余白と境界線を確保する.
           Block C 内の `stHorizontalBlock:has(.conf-patient-row)` は
           margin-bottom:0 で圧縮されているため、ヘッダー行だけは
           独自セレクタで余白を差し戻す. */
        .conf-patient-row-header {
            min-height: 24px !important;
            padding-top: 4px !important;
            padding-bottom: 6px !important;
            border-bottom: 2px solid #aaa !important;
            margin-bottom: 0 !important;
        }
        /* ヘッダー行を含む stHorizontalBlock にヘッダー専用セレクタで
           確実に下マージンを確保する（先行する :has(.conf-patient-row) の
           margin-bottom:0 より詳細度を高める）.
           さらに、Streamlit が stHorizontalBlock を子要素の高さに合わせず
           圧縮する挙動（header_container 14px vs header_div 26px）に対抗し、
           min-height と align-items で子のオーバーフローを吸収する. */
        div[data-testid="stHorizontalBlock"]:has(.conf-patient-row-header),
        div[data-testid="stHorizontalBlock"]:has(.conf-patient-row.conf-patient-row-header) {
            margin-bottom: 4px !important;
            padding-bottom: 0 !important;
            min-height: 30px !important;
            align-items: stretch !important;
        }
        /* ヘッダーを含む列と要素コンテナにも同じ最低高さを強制 */
        [data-testid="stColumn"]:has(.conf-patient-row-header),
        [data-testid="stElementContainer"]:has(.conf-patient-row-header) {
            min-height: 30px !important;
        }
        /* 医師/患者セル: 170px 幅に文字列を収め、折り返しによる
           行全体のオーバーフロー（副院長指摘 2026-04-18: ヘッダー行との
           重なりの根本原因）を防止する. */
        .conf-patient-row .doctor {
            font-weight: 600;
            color: #333;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .conf-patient-row .doctor .pname { color: #444; font-weight: 500; }
        .conf-patient-row .doctor .pid {
            color: #888;
            font-size: 11px;
            font-weight: 400;
            margin-left: 4px;
        }
        .conf-patient-row .doctor .empty {
            color: #999;
            font-style: italic;
            font-weight: 400;
        }
        .conf-patient-row .ward.f5 { color: #2980b9; font-weight: 600; }
        .conf-patient-row .ward.f6 { color: #8e44ad; font-weight: 600; }
        .conf-patient-row .day { color: #666; }
        .conf-patient-row .plan-date { color: #555; }
        .conf-patient-row .note {
            color: #333;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        /* ========================================================
           6. Block C 列全体: popover button 高さ & 列余白
              125%拡大: 22px → 28px で文字重なり解消（患者 10 名全員表示維持）
           ======================================================== */
        /* カンファ画面内の全 popover button を 28px 高さに
           st.markdown('<div class="conf-root">') は自己閉じ要素で
           子孫セレクタが効かないため、グローバルに適用.
           ベッドコントロールアプリ本体で st.popover は未使用のため影響なし. */
        div[data-testid="stPopover"] > button,
        button[data-testid="stPopoverButton"],
        .stPopover button {
            min-height: 28px !important;
            height: 28px !important;
            padding: 3px 10px !important;
            font-size: 11px !important;
            line-height: 1.25 !important;
            font-weight: 500 !important;
            white-space: nowrap !important;
        }
        /* 患者行を含む水平ブロックの列間 gap & マージンを縮める（:has セレクタ）*/
        div[data-testid="stHorizontalBlock"]:has(.conf-patient-row) {
            gap: 5px !important;
            margin-bottom: 0 !important;
            min-height: unset !important;
        }
        div[data-testid="stHorizontalBlock"]:has(.conf-patient-row) > [data-testid="stColumn"] {
            padding: 0 !important;
        }
        /* popover を持つ列の内部 vertical gap を 0 に */
        [data-testid="stColumn"]:has(button[data-testid="stPopoverButton"]) > div[data-testid="stVerticalBlock"] {
            gap: 0 !important;
        }
        /* stElementContainer の余白（popover 列のみ）*/
        [data-testid="stColumn"]:has(button[data-testid="stPopoverButton"]) [data-testid="stElementContainer"] {
            margin: 0 !important;
        }
        /* ========================================================
           7. 予測行（125%拡大）
           ======================================================== */
        .conf-forecast-row {
            display: grid;
            grid-template-columns: 60px 1fr 1fr;
            gap: 5px;
            font-size: 12px;
            padding: 3px 0;
            border-bottom: 1px dashed #eee;
        }
        .conf-forecast-row .day { font-weight: 600; }
        .conf-forecast-row .vacancy.warn { color: #e67e22; font-weight: 600; }
        .conf-forecast-row .vacancy.danger { color: #c0392b; font-weight: 600; }
        .conf-forecast-summary {
            margin-top: 5px;
            padding: 6px 8px;
            background: #fff3e0;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
            text-align: center;
            color: #e65100;
        }
        /* ========================================================
           8. 役割ブロック（2026-04-18 105%拡大: padding 6→9, li line-height 1.35→1.5）
           ======================================================== */
        .conf-role {
            padding: 9px 11px;
            border-left: 3px solid #3498db;
            font-size: 12px;
            background: #fafbfc;
            border-radius: 2px;
            margin-bottom: 4px;
        }
        .conf-role.reha { border-left-color: #27ae60; }
        .conf-role.disch { border-left-color: #e67e22; }
        .conf-role.doc { border-left-color: #8e44ad; }
        .conf-role.nurse { border-left-color: #3498db; }
        .conf-role .role-name {
            font-weight: 700;
            font-size: 13px;
            margin-bottom: 4px;
        }
        .conf-role ul { list-style: none; padding: 0; margin: 0; }
        .conf-role li { font-size: 11px; line-height: 1.5; padding: 1px 0; color: #444; }
        .conf-role li::before { content: "・"; margin-right: 2px; }
        /* ========================================================
           9. ファクトバー（2026-04-18 105%拡大: padding 6→8）
           ======================================================== */
        .conf-fact-bar {
            background: #2c3e50;
            color: #ecf0f1;
            padding: 8px 14px;
            border-radius: 4px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 12px;
            margin-top: 6px;
        }
        .conf-fact-bar .fact-label {
            font-size: 11px;
            background: #34495e;
            padding: 3px 8px;
            border-radius: 3px;
            margin-right: 10px;
        }
        .conf-fact-bar .fact-text { flex: 1; }
        .conf-fact-bar .fact-src {
            font-size: 11px;
            opacity: 0.75;
            margin-left: 10px;
        }
        /* ========================================================
           10. ステータス popover trigger（タグ風スタイル）
               副院長決定（2026-04-17）: ステータスタグ自体をクリッカブルに
               2026-04-18: 125%拡大で 22px → 28px（文字重なり解消）
           ======================================================== */
        .conf-status-popover-wrap .stPopover > div[data-testid="stPopoverButton"] > button,
        .conf-status-popover-wrap div[data-testid="stPopover"] > div > button,
        .conf-status-popover-wrap button[kind="secondary"] {
            background: var(--conf-status-bg, #e9ecef) !important;
            color: var(--conf-status-fg, #495057) !important;
            border: none !important;
            border-radius: 14px !important;
            padding: 2px 10px !important;
            font-size: 11px !important;
            font-weight: 600 !important;
            min-height: 28px !important;
            height: 28px !important;
            line-height: 1.25 !important;
            white-space: nowrap !important;
            box-shadow: none !important;
        }
        .conf-status-popover-wrap .stPopover > div[data-testid="stPopoverButton"] > button:hover,
        .conf-status-popover-wrap div[data-testid="stPopover"] > div > button:hover,
        .conf-status-popover-wrap button[kind="secondary"]:hover {
            opacity: 0.9 !important;
            cursor: pointer !important;
        }
        /* ========================================================
           11. 編集ボタン（✏️）125%拡大
           ======================================================== */
        .conf-edit-btn-wrap .stPopover > div[data-testid="stPopoverButton"] > button,
        .conf-edit-btn-wrap div[data-testid="stPopover"] > div > button,
        .conf-edit-btn-wrap button[kind="secondary"] {
            min-height: 28px !important;
            height: 28px !important;
            padding: 2px 8px !important;
            font-size: 11px !important;
        }
        /* ========================================================
           12. 上部コントロール（病棟/モード）125%拡大
           ======================================================== */
        .conf-root div[data-testid="stSelectbox"] {
            margin-bottom: 0 !important;
        }
        .conf-root div[data-testid="stSelectbox"] > label,
        .conf-root div[data-testid="stCheckbox"] > label {
            font-size: 12px !important;
            padding-bottom: 0 !important;
            margin-bottom: 2px !important;
        }
        .conf-root div[data-baseweb="select"] > div {
            min-height: 36px !important;
        }
        /* トグルラベルも 125%拡大 */
        .conf-root label[data-testid="stWidgetLabel"] {
            font-size: 12px !important;
        }
        /* ========================================================
           13. 印刷時設定
           ======================================================== */
        @media print {
            .conf-fact-bar { display: none !important; }
            /* 編集ボタン（popover）は印刷時に非表示。患者名・ID はそのまま印刷 */
            .conf-edit-btn-wrap { display: none !important; }
            /* ステータス popover も印刷時は静的ラベル表示のみにする（トリガー部非表示） */
            .conf-status-popover-wrap .stPopover { display: none !important; }
            .conf-status-print-tag { display: inline-block !important; }
            /* データ管理 expander は印刷不要 */
            .conf-data-manage-wrap { display: none !important; }
            /* 📚 ファクトライブラリ（折りたたみ）も印刷不要 */
            .conf-fact-library-wrap { display: none !important; }
            /* 📈 履歴エクスパンダー／個別履歴 popover は印刷不要 */
            .conf-history-expander-wrap { display: none !important; }
            .conf-history-btn-wrap { display: none !important; }
        }
        .conf-status-print-tag { display: none; }
        /* ========================================================
           14. 📚 ファクトライブラリ（折りたたみ expander）
               副院長指示（2026-04-18）: ローテーション 12 件以外の
               全 80 件を勉強目的で閲覧できる expander。画面下部の
               ファクトバー直下に配置し、印刷時は非表示にする。
           ======================================================== */
        .conf-fact-library-wrap { margin-top: 4px; }
        .conf-fact-library-wrap details.conf-fact-library {
            background: #ecf0f1;
            color: #2c3e50;
            border: 1px solid #bdc3c7;
            border-radius: 4px;
            padding: 0;
            font-size: 12px;
        }
        .conf-fact-library-wrap details.conf-fact-library summary {
            padding: 6px 12px;
            cursor: pointer;
            font-weight: 600;
            user-select: none;
            list-style: none;
        }
        .conf-fact-library-wrap details.conf-fact-library summary::-webkit-details-marker {
            display: none;
        }
        .conf-fact-library-wrap details.conf-fact-library summary::before {
            content: "▶";
            margin-right: 6px;
            font-size: 10px;
            display: inline-block;
            transition: transform 0.15s;
        }
        .conf-fact-library-wrap details.conf-fact-library[open] summary::before {
            transform: rotate(90deg);
        }
        .conf-fact-library-wrap .fact-lib-body {
            padding: 8px 12px 12px 12px;
            background: #ffffff;
            max-height: 480px;
            overflow-y: auto;
            border-top: 1px solid #bdc3c7;
        }
        .conf-fact-library-wrap .fact-lib-section {
            margin-bottom: 10px;
        }
        .conf-fact-library-wrap .fact-lib-section-title {
            font-weight: 700;
            font-size: 12px;
            color: #2c3e50;
            margin: 6px 0 4px 0;
            border-bottom: 1px solid #d5dbdb;
            padding-bottom: 2px;
        }
        .conf-fact-library-wrap .fact-lib-section-title .lib-count {
            font-size: 11px;
            color: #666;
            font-weight: 500;
            margin-left: 4px;
        }
        .conf-fact-library-wrap .fact-lib-item {
            padding: 4px 6px;
            border-left: 3px solid #bdc3c7;
            margin: 3px 0 3px 4px;
            background: #f8f9fa;
            border-radius: 0 3px 3px 0;
            line-height: 1.35;
        }
        .conf-fact-library-wrap .fact-lib-item.rotation {
            border-left-color: #27ae60;
            background: #eafaf1;
        }
        .conf-fact-library-wrap .fact-lib-item .lib-rot-badge {
            display: inline-block;
            background: #27ae60;
            color: #fff;
            padding: 0 5px;
            border-radius: 3px;
            font-size: 10px;
            font-weight: 600;
            margin-right: 4px;
            vertical-align: 1px;
        }
        .conf-fact-library-wrap .fact-lib-item .lib-text {
            font-size: 12px;
            color: #2c3e50;
        }
        .conf-fact-library-wrap .fact-lib-item .lib-meta {
            font-size: 10px;
            color: #7f8c8d;
            margin-top: 2px;
        }
        .conf-fact-library-wrap .fact-lib-item .lib-meta .lib-pmid {
            color: #2980b9;
        }
        .conf-fact-library-wrap .fact-lib-search {
            margin-bottom: 6px;
        }
        .conf-fact-library-wrap .fact-lib-empty {
            padding: 12px;
            color: #7f8c8d;
            text-align: center;
            font-style: italic;
        }
        /* ========================================================
           15. 📈 週次カンファ履歴ビュー
               副院長指示（2026-04-18）: 先週からの変化を可視化し、
               停滞患者を洗い出す。エビデンスバー直上に配置し、
               印刷時は非表示にする（@media print で処理済み）。
           ======================================================== */
        .conf-history-expander-wrap { margin-top: 4px; margin-bottom: 4px; }
        .conf-history-summary {
            background: #f4f6f8;
            border-left: 3px solid #34495e;
            padding: 8px 12px;
            margin: 6px 0;
            font-size: 12px;
            color: #2c3e50;
            border-radius: 0 3px 3px 0;
        }
        .conf-history-summary-title {
            font-weight: 700;
            margin-bottom: 4px;
            color: #34495e;
        }
        .conf-history-summary-item {
            display: inline-block;
            margin: 2px 6px 2px 0;
            padding: 1px 6px;
            background: #ffffff;
            border: 1px solid #d5dbdb;
            border-radius: 10px;
            font-size: 11px;
        }
        .conf-history-warning {
            background: #fff5e6;
            border-left: 3px solid #f39c12;
            padding: 8px 12px;
            margin: 6px 0;
            font-size: 12px;
            color: #7e5109;
            border-radius: 0 3px 3px 0;
        }
        .conf-history-warning-title {
            font-weight: 700;
            margin-bottom: 4px;
            color: #b9770e;
        }
        .conf-history-empty {
            padding: 8px 12px;
            color: #7f8c8d;
            font-size: 12px;
            font-style: italic;
            text-align: center;
        }
        .conf-history-timeline {
            font-size: 11px;
            color: #2c3e50;
        }
        .conf-history-timeline .hist-entry {
            padding: 3px 6px;
            margin: 2px 0;
            background: #f8f9fa;
            border-left: 2px solid #95a5a6;
            border-radius: 0 3px 3px 0;
        }
        .conf-history-timeline .hist-entry .hist-date {
            font-weight: 600;
            color: #34495e;
            margin-right: 4px;
        }
        .conf-history-timeline .hist-entry.hist-first {
            border-left-color: #27ae60;
        }
        /* 個別 📜 履歴ボタンのラッパー（印刷非表示用） */
        .conf-history-btn-wrap { display: inline-block; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _status_meta(status_key: str, mode: str) -> Dict[str, str]:
    """status_key に対応するメタ情報を返す（見つからなければ未決）."""
    pool = _STATUS_HOLIDAY if mode == "holiday" else _STATUS_NORMAL
    for s in pool:
        if s["key"] == status_key:
            return s
    # モード不一致時のフォールバック: 別モード側から探す
    fallback_pool = _STATUS_NORMAL if mode == "holiday" else _STATUS_HOLIDAY
    for s in fallback_pool:
        if s["key"] == status_key:
            return s
    return {"key": "unknown", "emoji": "❓", "label": "未分類", "bg": "#cccccc", "fg": "#333333"}


def _format_status_tag(status_key: str, mode: str) -> str:
    """ステータスタグの HTML スニペット（span）を返す."""
    meta = _status_meta(status_key, mode)
    return (
        f'<span class="conf-status-tag" '
        f'style="background:{meta["bg"]};color:{meta["fg"]};">'
        f'{meta["emoji"]} {meta["label"]}</span>'
    )


def _format_doctor_patient_cell(
    *,
    doctor_name: str,
    patient_name: str,
    patient_id: str,
    fallback_surname: str,
) -> str:
    """医師/患者セルの内側 HTML を返す.

    表示ルール:
    - 全フィールド空 → 「{姓} / 未入力」（姓はサンプルデータの姓）
    - 主治医名のみあり → 「{主治医名}」
    - 患者名もあり → 「{主治医名} / {患者名}」
    - 患者 ID もあり → 「{主治医名} / {患者名} <small>ID:{id}</small>」
    - 主治医名空で患者名のみ → 「{姓} / {患者名}」（姓はフォールバック）

    Parameters
    ----------
    doctor_name : str
        編集済みの主治医名（空文字可）
    patient_name : str
        編集済みの患者名（空文字可）
    patient_id : str
        編集済みの患者ID（空文字可）
    fallback_surname : str
        主治医名が未入力のときに表示するサンプル姓

    Returns
    -------
    str
        HTML スニペット（``<span>`` なしの内側のみ）
    """
    d = doctor_name.strip() if doctor_name else ""
    n = patient_name.strip() if patient_name else ""
    i = patient_id.strip() if patient_id else ""

    # 全フィールド空 → 未入力ラベル
    if not d and not n and not i:
        return f'{fallback_surname}<span class="empty"> / 未入力</span>'

    # 主治医部分: 入力があればそれを、なければフォールバック姓
    doctor_part = d if d else fallback_surname

    parts = [doctor_part]
    if n:
        parts.append(f'<span class="pname">{n}</span>')
    head = " / ".join(parts)

    if i:
        return f'{head}<span class="pid">ID:{i}</span>'
    return head


def _severity_to_cls(severity: str) -> str:
    """サイドバーバナーの severity をヘッダー表示用 class にマップ."""
    if severity == "urgent":
        return "urgent"
    if severity == "warning":
        return "warning"
    return ""


def _classify_occupancy(pct: float, target: float) -> str:
    """稼働率の色分け: good/warning/danger."""
    if pct >= target:
        return "good"
    if pct >= target - 5:
        return "warning"
    return "danger"


def _classify_alos(days: float, warning: float, limit: float) -> str:
    """ALOS の色分け: 上限超=danger、警告閾値超=warning、それ以外=good."""
    if days >= limit:
        return "danger"
    if days >= warning:
        return "warning"
    return "good"


def _classify_emergency(pct: float, minimum: float) -> str:
    """救急割合の色分け: 下回る=danger、ちょうど近い=warning、超=good."""
    if pct < minimum:
        return "danger"
    if pct < minimum + 2:
        return "warning"
    return "good"


def _render_data_manage_expander() -> None:
    """一括クリア UI（副院長決定 2026-04-17 Q2=🅰 / Q3=🅱 / Q4=🅱）.

    - 2026-04-18 圧縮（副院長指示）: メイン画面の縦幅を食わないよう
      ``st.sidebar`` 配下の ``st.expander`` に移設（closed by default）
    - チェックボックスで対象を選択（主治医名 / 患者名 / 患者ID / ステータス）
    - 「クリア」のタイプ入力で二重確認
    - 入力 == "クリア" かつ 1 件以上チェックで実行ボタンが有効化
    - 実行後: フィードバック + 確認入力欄リセット + rerun
    - 印刷時は ``conf-data-manage-wrap`` クラスで非表示
    """
    # 印刷時非表示用のラッパークラス（印刷は main 側ではもう不要だが互換維持）
    st.sidebar.markdown(
        '<div class="conf-data-manage-wrap">',
        unsafe_allow_html=True,
    )
    with st.sidebar.expander("🗑 カンファデータ管理", expanded=False):
        stats = _count_stored_data()
        st.caption(
            "全患者の編集データをまとめてクリアします。"
            "確認のため「クリア」と入力してから実行してください。"
        )
        clr_all_doctor = st.checkbox(
            f"全患者の主治医名をクリア（現在 {stats['doctor']} 名入力済）",
            key="clr_all_doctor",
        )
        clr_all_name = st.checkbox(
            f"全患者の患者名をクリア（現在 {stats['name']} 名入力済）",
            key="clr_all_name",
        )
        clr_all_id = st.checkbox(
            f"全患者の患者ID をクリア（現在 {stats['id']} 名入力済）",
            key="clr_all_id",
        )
        clr_all_status = st.checkbox(
            f"全患者のステータスを 🆕 新規 に戻す（現在 {stats['status']} 名変更済）",
            key="clr_all_status",
        )

        any_checked = (
            clr_all_doctor or clr_all_name or clr_all_id or clr_all_status
        )

        confirm_text = st.text_input(
            '確認のため「クリア」と入力してください:',
            key="clr_all_confirm",
            placeholder="クリア",
        )
        is_confirmed = confirm_text == "クリア"

        execute_disabled = (not is_confirmed) or (not any_checked)
        if st.button(
            "実行",
            key="clr_all_exec",
            disabled=execute_disabled,
            type="primary",
        ):
            cleared_summary: List[str] = []
            if clr_all_doctor or clr_all_name or clr_all_id:
                n_names = clear_all_patient_info(
                    clear_doctor=clr_all_doctor,
                    clear_name=clr_all_name,
                    clear_id=clr_all_id,
                )
                targets: List[str] = []
                if clr_all_doctor:
                    targets.append("主治医名")
                if clr_all_name:
                    targets.append("患者名")
                if clr_all_id:
                    targets.append("患者ID")
                cleared_summary.append(
                    f"{'/'.join(targets)}: {n_names}件"
                )
            if clr_all_status:
                try:
                    n_status = clear_all_statuses()
                except OSError:
                    n_status = 0
                # session_state もリセット
                st.session_state["conf_patient_status"] = {}
                cleared_summary.append(f"ステータス: {n_status}件")

            # 確認入力欄をリセット
            st.session_state["clr_all_confirm"] = ""
            # チェックボックスもリセット
            for key in (
                "clr_all_doctor",
                "clr_all_name",
                "clr_all_id",
                "clr_all_status",
            ):
                if key in st.session_state:
                    st.session_state[key] = False

            st.success(
                "一括クリア完了: " + " / ".join(cleared_summary)
            )
            st.rerun()
    st.sidebar.markdown("</div>", unsafe_allow_html=True)


def _count_stored_data() -> Dict[str, int]:
    """現在の永続化ストアに入力済み・変更済みの件数を集計.

    Returns
    -------
    dict
        ``{"doctor": 主治医名入力済み件数, "name": 患者名入力済み件数,
           "id": 患者ID入力済み件数, "status": ステータス変更済み件数}``

    Notes
    -----
    - 「入力済み」= 非空文字。空文字エントリはカウントしない
    - ステータスは永続化ストアに保存されたエントリ数
      （セッション内のみの変更は対象外 — あくまで「クリアすべきファイル側の件数」）
    """
    all_names = load_all_patient_info()
    all_statuses = load_all_statuses()

    doctor_count = sum(1 for v in all_names.values() if v.get("doctor_name"))
    name_count = sum(1 for v in all_names.values() if v.get("patient_name"))
    id_count = sum(1 for v in all_names.values() if v.get("patient_id"))
    status_count = len(all_statuses)

    return {
        "doctor": doctor_count,
        "name": name_count,
        "id": id_count,
        "status": status_count,
    }


# ---------------------------------------------------------------------------
# セッション初期化
# ---------------------------------------------------------------------------

def _init_session(today: date) -> None:
    """ビュー専用の session_state を初期化する."""
    if "conf_ward" not in st.session_state:
        st.session_state["conf_ward"] = _DEFAULT_WARD
    if "conf_mode" not in st.session_state:
        st.session_state["conf_mode"] = "normal"
    # 患者ステータス（サンプルの初期値を投入 — ユーザー操作で上書き可）
    if "conf_patient_status" not in st.session_state:
        st.session_state["conf_patient_status"] = {}
    # 表示中の今日日付（シミュレーション用に固定化可能）
    if "conf_today" not in st.session_state:
        st.session_state["conf_today"] = today


# ---------------------------------------------------------------------------
# 連休対策モード推奨バナー（Block A 直上）
# ---------------------------------------------------------------------------

def _render_holiday_mode_recommendation_banner(
    mode: str,
    banner: Dict[str, Any],
) -> None:
    """通常モード時、連休まで 21 日以下で切替推奨バナーを表示する.

    副院長決定（2026-04-18）: 連休対策モードは師長が手動で ON/OFF する運用.
    自動切替は行わず、気づきのきっかけとして画面上部に推奨バナーを出す.

    表示条件
    --------
    - ``mode == "normal"`` （連休対策モードが OFF）
    - ``banner["days_remaining"] is not None``
    - ``banner["days_remaining"] <= 21``

    色・severity
    -----------
    - ``days_remaining <= 7`` → ``urgent`` （赤）
    - ``8 <= days_remaining <= 21`` → ``warning`` （橙）
    - 連休期間中 (``days_remaining <= 0``) でも通常モードなら、切替推奨として赤表示
    """
    if mode != "normal":
        return
    days_remaining = banner.get("days_remaining")
    if days_remaining is None:
        return
    if days_remaining > 21:
        return

    holiday_name = banner.get("holiday_name") or "連休"
    severity_label = "urgent" if days_remaining <= 7 else "warning"
    if days_remaining <= 0:
        # 連休中なのに通常モードのまま → 切替推奨（urgent 強調）
        banner_text = (
            f"💡 {holiday_name} 期間中 — 連休対策モードへの切替を推奨します"
        )
    else:
        banner_text = (
            f"💡 {holiday_name} まで {days_remaining} 日 — "
            f"連休対策モードへの切替を推奨します"
        )

    # --- インライン HTML でバナーを描画 ---
    # bc-alert CSS（theme_css.py）はメインアプリ経由では読み込まれるが、
    # 本ビュー単独起動時（run_conference_view.py）でも同じ見た目にするため、
    # ここでは独立した CSS（.conf-holiday-recommend-banner）でスタイルを閉じる。
    # data-testid は E2E 検証用、印刷時にも表示（@media print で消さない）。
    severity_color_map = {
        "warning": {
            "bg": "#fff7e6",
            "border": "#e67e22",
            "fg": "#7a4a0b",
        },
        "urgent": {
            "bg": "#fdecec",
            "border": "#c0392b",
            "fg": "#7a1f17",
        },
    }
    color = severity_color_map.get(severity_label, severity_color_map["warning"])

    st.markdown(
        f"""
        <style>
        .conf-holiday-recommend-banner {{
            margin: 4px 0 6px 0;
            padding: 7px 12px;
            border-left: 4px solid {color["border"]};
            background: {color["bg"]};
            color: {color["fg"]};
            font-size: 12px;
            font-weight: 600;
            border-radius: 0 6px 6px 0;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
            line-height: 1.35;
        }}
        .conf-holiday-recommend-banner .hint {{
            font-weight: 400;
            font-size: 11px;
            opacity: 0.85;
            margin-left: 8px;
        }}
        @media print {{
            .conf-holiday-recommend-banner {{
                /* 師長が紙で持ち帰るときの気づきにもなるよう、印刷時も表示 */
                border-left: 4px solid {color["border"]};
                background: {color["bg"]};
                color: {color["fg"]};
                print-color-adjust: exact;
                -webkit-print-color-adjust: exact;
            }}
        }}
        </style>
        <div class="conf-holiday-recommend-banner"
             data-testid="conference-holiday-mode-recommend-banner"
             data-severity="{severity_label}"
             data-days="{days_remaining}">
          {banner_text}
          <span class="hint">（「連休対策モード」トグルを ON にしてください）</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# ブロック描画: ヘッダー
# ---------------------------------------------------------------------------

def _render_header(
    today: date,
    ward: str,
    mode: str,
    banner: Dict[str, Any],
) -> None:
    """ヘッダー（タイトル・モード・日付）を描画.

    2026-04-18 圧縮（副院長指示）:
    - 「{ward} 表示中」は上部セレクトで可視なので撤去
    - GW カウントダウンは Block A にもあるのでヘッダーからは撤去
      （banner_text の severity クラスは CSS 互換のために残す）
    """
    mode_label = "通常モード" if mode == "normal" else "🚨 連休対策モード"
    mode_cls = "" if mode == "normal" else "holiday"
    # 曜日表示
    weekday_ja = ["月", "火", "水", "木", "金", "土", "日"][today.weekday()]
    st.markdown(
        f"""
        <div class="conf-header">
          <div>
            <span class="title">🗓 多職種退院調整・連休対策カンファ</span>
            <span class="mode {mode_cls}">{mode_label}</span>
          </div>
          <div class="meta">
            {today.isoformat()} ({weekday_ja})
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# ブロック描画: A 今月の目標達成進捗
# ---------------------------------------------------------------------------

def _render_block_a(
    ward: str,
    today: date,
    banner: Dict[str, Any],
    kpi: Dict[str, float],
) -> None:
    """ブロック A: 5 KPI 横並び."""
    occupancy_target = get_occupancy_target(ward, month=today)
    alos_limit = get_alos_regulatory_limit()
    alos_warn = get_alos_warning_threshold()
    emergency_min = get_emergency_ratio_minimum()

    occ_pct = kpi["occupancy_pct"]
    alos_days = kpi["alos_days"]
    er_pct = kpi["emergency_pct"]
    remaining_days = int(kpi["remaining_business_days"])
    required_bed_days = int(kpi["required_bed_days"])

    occ_cls = _classify_occupancy(occ_pct, occupancy_target)
    alos_cls = _classify_alos(alos_days, alos_warn, alos_limit)
    er_cls = _classify_emergency(er_pct, emergency_min)

    # 稼働率の差分
    occ_diff = occ_pct - occupancy_target
    occ_diff_label = f"{occ_diff:+.0f}pt"

    # ALOS の余裕／超過
    alos_gap = alos_limit - alos_days
    if alos_gap > 0:
        alos_target_label = f"制度上限 {alos_limit:.0f}日 まで余裕"
    else:
        alos_target_label = f"制度上限 {alos_limit:.0f}日 超過"

    # 救急 15%
    if er_pct >= emergency_min:
        er_target_label = "基準達成"
    else:
        er_target_label = f"基準 {emergency_min:.0f}% 未達"

    # シードが採用されている場合、KPI ラベルに注記を付与
    seed_months = kpi.get("emergency_seed_months", []) if isinstance(kpi, dict) else []
    if seed_months:
        er_target_label = f"{er_target_label} ・ ※{'/'.join(seed_months)} は手入力シード"

    # 連休残日数
    days_remaining = banner.get("days_remaining")
    holiday_name = banner.get("holiday_name") or "連休"
    h_start = banner.get("holiday_start")
    h_end = banner.get("holiday_end")
    severity = banner.get("severity", "none")
    countdown_color = "#e67e22"
    if severity == "urgent":
        countdown_color = "#c0392b"
    elif severity == "warning":
        countdown_color = "#e67e22"
    else:
        countdown_color = "#2c3e50"

    if days_remaining is None:
        countdown_text = "予定なし"
        countdown_sub = ""
    elif days_remaining <= 0:
        countdown_text = banner.get("banner_text", "連休中")
        countdown_sub = ""
    else:
        countdown_text = f"{holiday_name} まで {days_remaining}日"
        if h_start and h_end:
            duration = (h_end - h_start).days + 1
            countdown_sub = f"{h_start.month}/{h_start.day} 開始・{duration}連休"
        else:
            countdown_sub = ""

    st.markdown(
        f"""
        <div class="conf-kpi-row">
          <div class="conf-kpi">
            <div class="label">今月の稼働率</div>
            <div class="value {occ_cls}">{occ_pct:.0f}<span class="unit">%</span></div>
            <div class="target">目標 {occupancy_target:.0f}% ・ {occ_diff_label}</div>
          </div>
          <div class="conf-kpi">
            <div class="label">平均在院日数 (3ヶ月)</div>
            <div class="value {alos_cls}">{alos_days:.1f}<span class="unit">日</span></div>
            <div class="target">{alos_target_label}</div>
          </div>
          <div class="conf-kpi">
            <div class="label">救急搬送後 {emergency_min:.0f}%</div>
            <div class="value {er_cls}">{er_pct:.0f}<span class="unit">%</span></div>
            <div class="target">{er_target_label}</div>
          </div>
          <div class="conf-kpi">
            <div class="label">残り診療日</div>
            <div class="value">{remaining_days}<span class="unit">日</span></div>
            <div class="target">必要床日 +{required_bed_days}</div>
          </div>
          <div class="conf-kpi">
            <div class="label">次の大型連休</div>
            <div class="value" style="color:{countdown_color};font-size:18px;">{countdown_text}</div>
            <div class="target">{countdown_sub}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # testid hidden divs
    st.markdown(
        f'<div data-testid="conference-occupancy-pct" style="display:none">{occ_pct:.1f}</div>'
        f'<div data-testid="conference-alos-days" style="display:none">{alos_days:.1f}</div>'
        f'<div data-testid="conference-emergency-pct" style="display:none">{er_pct:.1f}</div>'
        f'<div data-testid="conference-holiday-days" style="display:none">'
        f'{"" if days_remaining is None else days_remaining}</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# ブロック描画: B 今週の見通し + 内訳
# ---------------------------------------------------------------------------

def _compute_weekend_forecast(
    ward: str, mode: str,
    daily_df: Optional[pd.DataFrame] = None,
    detail_df: Optional[pd.DataFrame] = None,
    today: Optional[date] = None,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Block B の予測データを返す。

    通常モード: 実データ (daily_df, detail_df) があれば weekend_forecast モジュール
    で来週末の予測を計算。データ不足時はサンプル値にフォールバック。
    連休対策モード: 現行通りサンプル値を使う (連休は次の大型連休固定のため)。

    Returns:
        (forecast_rows, meta) のタプル。
        meta には coverage_pct, total_uncertainty, is_real などを含む。
    """
    # 連休対策モードはサンプル固定
    if mode == "holiday":
        rows = _sample_weekend_forecast(ward, mode)
        return rows, {"is_real": False, "coverage_pct": None, "total_uncertainty": 0}

    # 通常モード: 実データが揃えば計算、足りなければサンプル
    has_real = (
        daily_df is not None and isinstance(daily_df, pd.DataFrame)
        and len(daily_df) >= 56  # 少なくとも 8 週間分の履歴
    )
    if not has_real:
        rows = _sample_weekend_forecast(ward, mode)
        return rows, {"is_real": False, "coverage_pct": None, "total_uncertainty": 0}

    try:
        from weekend_forecast import forecast_next_weekend as _fcast
        from bed_data_manager import get_ward_beds as _get_ward_beds
        ward_key = ward if ward in ("5F", "6F") else None
        ward_beds = _get_ward_beds(ward) if ward_key else 47
        result = _fcast(
            daily_df, detail_df=detail_df, ward=ward_key,
            today=today, ward_beds=ward_beds,
        )
        rows = result["rows"]
        return rows, {
            "is_real": True,
            "coverage_pct": result["coverage_pct"],
            "total_uncertainty": result["uncertainty_bed_days"],
            "target_dates": result.get("target_dates", []),
        }
    except Exception:
        rows = _sample_weekend_forecast(ward, mode)
        return rows, {"is_real": False, "coverage_pct": None, "total_uncertainty": 0}


def _render_block_b(
    ward: str,
    mode: str,
    patients: List[SamplePatient],
    daily_df: Optional[pd.DataFrame] = None,
    detail_df: Optional[pd.DataFrame] = None,
    today: Optional[date] = None,
) -> None:
    """ブロック B: 来週末見通し + ステータス内訳.

    副院長決定 2026-04-20: カンファは来週以降の退院戦略を議論する場なので、
    今週末ではなく「来週末」の見通しを表示する (カンファの意思決定レバーと
    結果指標を同期させる)。
    """
    forecast, forecast_meta = _compute_weekend_forecast(
        ward, mode, daily_df=daily_df, detail_df=detail_df, today=today,
    )

    if mode == "holiday":
        title = f"GW期間 {len(forecast)}連休の見通し（{ward}）"
    elif forecast_meta.get("is_real"):
        title = f"来週末の見通し（{ward}・カンファ決定の影響を反映）"
    else:
        title = f"来週末の見通し（{ward}・サンプル表示）"

    def _fmt_row(row: Dict[str, Any]) -> str:
        """1 行分の HTML を返す。±バンドがあれば併記する。"""
        day = row["day"]
        vac = row["vacancy"]
        sev = row["severity"]
        er = row["er_margin"]
        # ±バンド (実データ計算時のみ)
        low = row.get("vacancy_low")
        high = row.get("vacancy_high")
        if low is not None and high is not None and high > low:
            band = f'<span style="color:#888;font-size:11px;margin-left:4px;">[{low}〜{high}]</span>'
        else:
            band = ""
        return (
            f'<div class="conf-forecast-row">'
            f'<span class="day">{day}</span>'
            f'<span>空床 <span class="vacancy {sev}">{vac}</span>{band}</span>'
            f'<span>救急余力 {er:+d}</span>'
            f"</div>"
        )

    forecast_rows_html = "".join(_fmt_row(r) for r in forecast)

    # 週末受入余力（床日）
    total_bed_days = sum(int(row.get("vacancy", 0)) for row in forecast)
    uncert = forecast_meta.get("total_uncertainty", 0) if forecast_meta.get("is_real") else 0
    uncert_suffix = f"（± {uncert} 床日）" if uncert > 0 else ""
    if mode == "holiday":
        cost_text = (
            f"連休期間 週末受入余力 {total_bed_days}床日"
            f"{uncert_suffix}（応需可能だった患者機会）"
        )
        cost_bg = "#ffebee"
        cost_fg = "#b71c1c"
    else:
        cost_text = (
            f"来週末受入余力 {total_bed_days}床日"
            f"{uncert_suffix}（応需可能な患者機会）"
        )
        cost_bg = "#fff3e0"
        cost_fg = "#e65100"

    # 退院予定入力カバレッジ（実データ計算時のみ）
    coverage_html = ""
    if forecast_meta.get("is_real") and forecast_meta.get("coverage_pct") is not None:
        cov = forecast_meta["coverage_pct"]
        if cov >= 66.7:
            cov_color = "#10B981"  # success green
            cov_label = "精度高"
        elif cov >= 33.3:
            cov_color = "#F59E0B"  # warning orange
            cov_label = "精度中"
        else:
            cov_color = "#DC2626"  # danger red
            cov_label = "曜日平均で補完"
        coverage_html = (
            f'<div style="font-size:11px;color:#666;margin-top:6px;">'
            f'退院予定入力カバレッジ '
            f'<span style="color:{cov_color};font-weight:600;">{cov:.0f}%</span> '
            f'<span style="color:#888;">({cov_label})</span>'
            f'</div>'
        )

    # 内訳 — 現在の患者リストから集計
    status_counts = _count_status(patients)

    if mode == "holiday":
        # 連休対策モード時は 3 カテゴリ表示
        breakdown_items = []
        for meta in _STATUS_HOLIDAY:
            count = status_counts.get(meta["key"], 0)
            breakdown_items.append(
                f'<div style="display:flex;justify-content:space-between;padding:4px 0;font-size:13px;">'
                f'{_format_status_tag(meta["key"], mode)}'
                f'<span style="font-weight:600;">{count}名</span></div>'
            )
        breakdown_title = f"連休前 退院目標 ({ward})"
    else:
        breakdown_items = []
        for meta in _STATUS_NORMAL:
            count = status_counts.get(meta["key"], 0)
            breakdown_items.append(
                f'<div style="display:flex;justify-content:space-between;padding:4px 0;font-size:13px;">'
                f'{_format_status_tag(meta["key"], mode)}'
                f'<span style="font-weight:600;">{count}名</span></div>'
            )
        breakdown_title = "在院患者ステータス内訳"

    st.markdown(
        f"""
        <div style="border:1px solid #dee2e6;border-radius:4px;padding:12px;background:#fefefe;">
          <div style="font-size:14px;font-weight:700;color:#555;margin-bottom:7px;">{title}</div>
          {forecast_rows_html}
          <div class="conf-forecast-summary" style="background:{cost_bg};color:{cost_fg};">{cost_text}</div>
          {coverage_html}
          <div style="font-size:13px;font-weight:700;color:#555;margin-top:12px;margin-bottom:5px;">
            {breakdown_title}
          </div>
          {"".join(breakdown_items)}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _count_status(patients: List[SamplePatient]) -> Dict[str, int]:
    """患者リストをステータス key ごとに集計.

    Block B の内訳件数は本関数の結果から動的に組み立てられる. 優先順位:
      1. ``st.session_state['conf_patient_status']`` (セッション内の直近の更新)
      2. ``patient_status_store.load_all_statuses()`` (永続化ストア)
      3. ``SamplePatient.status_key`` (サンプル既定値)
    """
    persisted = load_all_statuses()
    session_map = st.session_state.get("conf_patient_status", {})
    counts: Dict[str, int] = {}
    for p in patients:
        current = session_map.get(
            p.patient_id,
            persisted.get(p.patient_id, p.status_key),
        )
        counts[current] = counts.get(current, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# ブロック描画: C 個別患者ステータス
# ---------------------------------------------------------------------------
#
# ============================================================
# 🚨 重要: このビューは 1 画面（16:9、1920×1080）で完全表示
# 必須。新機能追加時に縦幅を増やさない。要素を増やすなら既
# 存要素を横並びに or 折りたたみに。副院長の運用が壊れる。
#
# 特に編集列（conf-edit-btn-wrap）内の 📜 履歴 / ✏️ 編集
# ポップオーバーは **横並び固定**（縦積み禁止）。縦積みにすると
# 患者行の縦幅が倍になり 1 画面に収まらなくなる。
# 回帰テスト: tests/test_conference_material_view.py の
#   ``test_edit_column_buttons_are_horizontal_not_stacked``
#   ``test_conference_view_fits_in_one_screen``
# が縦幅肥大を検知する。落ちたら必ず原因を追って直すこと。
# ============================================================


def _get_demo_status_history(today: date) -> Dict[str, List[Dict[str, str]]]:
    """教育用のデモステータス履歴を today 相対で生成する.

    副院長指示（2026-04-19）: 実履歴が空の状態でも「前回からの変化」が
    意味のある数字（カンファ台本 v4 第0章と一致: ステータス変更 3 件 /
    新規登録 1 件）で表示されるよう、デモ用の仮想履歴を提供する。

    設計:
      - today - 10 日（窓外）: 過去の「前回」エントリ
      - today - 4 日（窓内）: 遷移エントリ（3 患者、transition 3 件）
      - today - 5 日（窓内）: 初出エントリ（1 患者、new 1 件）

    対象は 5F・6F 各 4 名ずつ（病棟切替時も同じ数字になる）。
    """
    outside = today - timedelta(days=10)
    inside_trans = today - timedelta(days=4)
    inside_new = today - timedelta(days=5)

    def _entry(status: str, d: date) -> Dict[str, str]:
        return {
            "timestamp": f"{d.isoformat()}T10:00:00",
            "status": status,
            "conference_date": d.isoformat(),
        }

    return {
        # === 5F サンプル患者（伊藤・渡辺・高橋・田中）===
        # 伊藤 Day 35: new → undecided（遷移 1）
        "a1b2c3d4": [_entry("new", outside), _entry("undecided", inside_trans)],
        # 渡辺 Day 28: new → medical_ok_waiting（遷移 2）
        "b2c3d4e5": [_entry("new", outside), _entry("medical_ok_waiting", inside_trans)],
        # 高橋 Day 22: rehab_optimizing → family_wish_waiting（遷移 3）
        "c3d4e5f6": [
            _entry("rehab_optimizing", outside),
            _entry("family_wish_waiting", inside_trans),
        ],
        # 田中 Day 18: 初出（新規登録 1）
        "d4e5f6a7": [_entry("new", inside_new)],
        # === 6F サンプル患者（渡辺・大野・松本・井上）===
        # 6F 選択時も同じ 3 件 + 1 件になるよう対称的に配置
        "e1f2a3b4": [_entry("new", outside), _entry("undecided", inside_trans)],
        "f2a3b4c5": [
            _entry("new", outside),
            _entry("medical_ok_waiting", inside_trans),
        ],
        "a3b4c5d6": [
            _entry("rehab_optimizing", outside),
            _entry("family_wish_waiting", inside_trans),
        ],
        "b4c5d6e7": [_entry("new", inside_new)],
    }


def _get_effective_status_changes(today: date, days: int = 7) -> List[Dict[str, str]]:
    """実履歴 + デモフォールバックで変化イベントを返す.

    副院長指示（2026-04-19）: 実履歴が空の教育・デモ環境でも、
    台本と一致する数字（変化 3 件 / 新規 1 件）で表示するため、
    実運用履歴が 1 件もないときに限り、デモ履歴を使う。

    実履歴に 1 件でもデータがあれば、そちらを優先（実運用モード）。
    """
    real_history = load_all_status_history()
    if real_history:
        # 実運用モード: 既存関数で集計
        return get_status_changes_this_week(today, days)

    # 実履歴ゼロ → 教育デモにフォールバック
    demo_history = _get_demo_status_history(today)
    window_start = today - timedelta(days=days)
    demo_changes: List[Dict[str, str]] = []
    for uuid, entries in demo_history.items():
        sorted_entries = sorted(entries, key=lambda e: e.get("timestamp", ""))
        for i, entry in enumerate(sorted_entries):
            ts_str = entry.get("timestamp", "")
            try:
                from datetime import datetime as _dt
                ts_date = _dt.fromisoformat(ts_str).date()
            except (ValueError, TypeError):
                continue
            if ts_date < window_start or ts_date > today:
                continue
            from_status = (
                sorted_entries[i - 1].get("status") if i > 0 else None
            )
            change: Dict[str, str] = {
                "uuid": uuid,
                "from_status": from_status if from_status is not None else "",
                "to_status": entry.get("status", ""),
                "timestamp": ts_str,
            }
            cdate = entry.get("conference_date")
            if isinstance(cdate, str):
                change["conference_date"] = cdate
            demo_changes.append(change)
    return demo_changes


def _render_block_c(
    patients: List[SamplePatient],
    mode: str,
    today: Optional[date] = None,
) -> None:
    """ブロック C: 10 名の患者行 + ステータス popover + 編集 popover.

    副院長決定（2026-04-17）: ステータスタグ自体をクリック → その場でプルダウン表示
    → 選択 → 即保存 の一貫した UX に刷新（右側の selectbox 列は撤去）。

    副院長指示（2026-04-19、v4 対応策 B）: Block C 冒頭に「📝 前回からの変化」
    要約バッジを表示。変化のあった患者行は左端にグレーハイライトを付与する。
    台本（carnf_scenario_v4.md 第0章）と実画面を一致させるための実装。
    """
    # 在院日数降順でソート
    sorted_patients = sorted(patients, key=lambda p: p.day_count, reverse=True)
    displayed = sorted_patients[:_MAX_PATIENTS_DISPLAYED]

    # ==================================================================
    # 「📝 前回からの変化」要約バッジ（v4 新機能、2026-04-19）
    # 履歴 JSON から直近 7 日間のステータス変化を集計
    # ==================================================================
    displayed_uuids = {p.patient_id for p in displayed}
    changed_uuids: set = set()
    transition_count = 0
    new_entry_count = 0
    has_history_data = False

    if today is not None:
        try:
            recent_changes = _get_effective_status_changes(today, days=7)
        except (OSError, ValueError):
            recent_changes = []
        changes_in_displayed = [
            c for c in recent_changes if c.get("uuid") in displayed_uuids
        ]
        has_history_data = len(changes_in_displayed) > 0
        changed_uuids = {c.get("uuid") for c in changes_in_displayed}
        for c in changes_in_displayed:
            if c.get("from_status"):
                transition_count += 1
            else:
                new_entry_count += 1

    # 要約バッジの中身 HTML を先に組み立てる
    if has_history_data:
        badge_inner_html = (
            '<span class="summary-label">📝 前回からの変化:</span> '
            f'<span class="summary-item">ステータス変更 '
            f'<b>{transition_count}</b> 件</span>'
            '<span class="summary-sep">/</span>'
            f'<span class="summary-item">新規登録 '
            f'<b>{new_entry_count}</b> 件</span>'
            '<span class="summary-hint">（詳細は下部「📈 先週からの変化」で確認）</span>'
        )
        badge_class = "conf-block-c-summary"
    else:
        badge_inner_html = (
            '<span class="summary-label">📝 前回からの変化:</span> '
            '<span class="summary-empty">履歴データ蓄積中'
            '（次回カンファから変化を表示します）</span>'
        )
        badge_class = "conf-block-c-summary conf-block-c-summary-empty"

    # タイトル行 + 要約バッジ + hidden testid を 1 つの markdown に統合
    # 副院長指示（2026-04-19）: タイトル「個別患者のステータス」と要約バッジが
    # 重なって見える問題を回避するため、Streamlit のブロック間隔に依存せず
    # 単一の HTML ブロック内で縦方向の順序を保証する
    st.markdown(
        f'''
        <div class="conf-block-c-header-wrap">
          <div class="conf-block-c-title-row">
            <div class="conf-block-c-title">個別患者のステータス（カンファで更新）</div>
            <div class="conf-block-c-count">表示中 {len(displayed)} / 最大 {_MAX_PATIENTS_DISPLAYED} 名</div>
          </div>
          <div class="{badge_class}" data-testid="conference-block-c-summary">
            {badge_inner_html}
          </div>
          <div data-testid="conference-block-c-changes-count" style="display:none">{transition_count}</div>
          <div data-testid="conference-block-c-new-count" style="display:none">{new_entry_count}</div>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    # ヘッダー（5 列: 医師/患者 | 病棟 | 在院 | 退院予定 | 確認事項）
    # ステータス・編集は Streamlit 列側で別途見出しを描画
    header_col_html, header_col_status, header_col_edit = st.columns(
        [0.80, 0.14, 0.06]
    )
    with header_col_html:
        # 2026-04-18: ヘッダー行に conf-patient-row-header クラスを付与し、
        # 1 行目との縦方向の重なりを防止（border-bottom / padding-bottom は CSS 側で統一）
        st.markdown(
            '<div class="conf-patient-row conf-patient-row-header" '
            'style="font-size:11px;color:#666;font-weight:600;">'
            '<span>医師 / 患者</span><span>病棟</span><span>在院</span>'
            '<span>退院予定</span><span>確認事項</span>'
            "</div>",
            unsafe_allow_html=True,
        )
    with header_col_status:
        st.markdown(
            '<div class="conf-patient-row-header" '
            'style="font-size:11px;color:#666;font-weight:600;text-align:center;">'
            'ステータス</div>',
            unsafe_allow_html=True,
        )
    with header_col_edit:
        st.markdown(
            '<div class="conf-patient-row-header" '
            'style="font-size:11px;color:#666;font-weight:600;text-align:center;">'
            '編集</div>',
            unsafe_allow_html=True,
        )

    status_pool = _STATUS_HOLIDAY if mode == "holiday" else _STATUS_NORMAL
    status_keys = [s["key"] for s in status_pool]

    # 永続化ストアから全ステータスを一括読み込み（毎レンダーで最新を反映）
    persisted_statuses = load_all_statuses()

    for p in displayed:
        ward_cls = "f5" if p.ward == "5F" else "f6"
        # 優先度: session_state > 永続化ストア > サンプル既定値
        current_key = st.session_state["conf_patient_status"].get(
            p.patient_id,
            persisted_statuses.get(p.patient_id, p.status_key),
        )

        # 現在の status が status_pool に含まれなければ 先頭にフォールバック
        if current_key not in status_keys:
            current_idx = 0
        else:
            current_idx = status_keys.index(current_key)

        # 編集中の患者情報を load（ファイルから毎回読む）
        stored = load_patient_info(p.patient_id)
        doctor_name = stored.get("doctor_name", "")
        patient_name = stored.get("patient_name", "")
        patient_id_str = stored.get("patient_id", "")
        stored_note = stored.get("note", "")
        # 確認事項は stored を優先、未設定時はサンプル既定値にフォールバック
        # （副院長指示 2026-04-19: ✏️ 編集から入力可能に）
        display_note = stored_note if stored_note else p.note

        # 医師/患者セルの表示 HTML を組み立てる
        doctor_patient_html = _format_doctor_patient_cell(
            doctor_name=doctor_name,
            patient_name=patient_name,
            patient_id=patient_id_str,
            fallback_surname=p.doctor_surname,
        )

        # 現在ステータスのメタ（popover trigger の見た目用）
        current_meta = _status_meta(current_key, mode)
        trigger_label = f"{current_meta['emoji']} {current_meta['label']}"

        # 患者行: 左（HTML 5 列, 確認事項まで）+ 中央（ステータス popover, タグ風）+ 右（編集 popover）
        row_col1, row_col_status, row_col_edit = st.columns([0.80, 0.14, 0.06])
        # v4 新機能（2026-04-19）: 前回カンファから変化のあった患者には
        # 左端グレーハイライト用クラスを付与
        row_classes = "conf-patient-row"
        if p.patient_id in changed_uuids:
            row_classes += " conf-patient-row-changed"
        with row_col1:
            # 2026-04-19: 確認事項は stored を優先表示（stored 空ならサンプル既定値）
            # HTML インジェクション対策として最低限 " エスケープ
            safe_note = (display_note or "").replace('"', '&quot;')
            st.markdown(
                f"""
                <div class="{row_classes}">
                  <span class="doctor">{doctor_patient_html}</span>
                  <span class="ward {ward_cls}">{p.ward}</span>
                  <span class="day">Day {p.day_count}</span>
                  <span class="plan-date">{p.planned_date}</span>
                  <span class="note" title="{safe_note}">{safe_note}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with row_col_status:
            # popover trigger をタグ風に見せるための CSS 変数 + ラッパークラス
            # 印刷時用のフォールバック（静的タグ）も添える
            st.markdown(
                f'<div class="conf-status-popover-wrap" '
                f'style="--conf-status-bg:{current_meta["bg"]};'
                f'--conf-status-fg:{current_meta["fg"]};">'
                f'<span class="conf-status-print-tag conf-status-tag" '
                f'style="background:{current_meta["bg"]};color:{current_meta["fg"]};">'
                f'{trigger_label}</span>',
                unsafe_allow_html=True,
            )
            with st.popover(trigger_label, use_container_width=True):
                st.caption("ステータスを選択")
                # 7 or 4 カテゴリを radio で表示（絵文字 + ラベル）
                new_key = st.radio(
                    label=f"ステータス更新 - {p.doctor_surname} ({p.patient_id})",
                    options=status_keys,
                    format_func=lambda k, _pool=status_pool: (
                        next(
                            (f"{s['emoji']} {s['label']}" for s in _pool if s["key"] == k),
                            k,
                        )
                    ),
                    index=current_idx,
                    key=f"status_radio_{p.patient_id}",
                    label_visibility="collapsed",
                )
                if new_key != current_key:
                    # 即保存 + session_state 同期 + rerun（副院長決定 🅰 即保存方式）
                    st.session_state["conf_patient_status"][p.patient_id] = new_key
                    try:
                        save_status(p.patient_id, new_key)
                    except (OSError, ValueError):
                        # 書き込み失敗時も UI 上のステータス変更は維持（次回の保存機会で再試行）
                        pass
                    st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
        with row_col_edit:
            # 印刷時は非表示にするためラッパー div で囲う
            st.markdown(
                '<div class="conf-edit-btn-wrap">',
                unsafe_allow_html=True,
            )
            # ============================================================
            # 📜 履歴 / ✏️ 編集 は **横並び固定**（縦積み禁止）
            # 2026-04-18 修正: 縦積み → 横並び 2 列
            # 理由: 副院長の 1 画面（1920×1080）運用を維持するため
            # ============================================================
            hist_col, edit_col = st.columns(2, gap="small")
        with hist_col:
            # 📜 履歴 popover（2026-04-18 新規）: タイムラインと遷移ペアを表示
            # 印刷時は非表示（.conf-history-btn-wrap は @media print で消える）
            st.markdown(
                '<div class="conf-history-btn-wrap" '
                f'data-testid="conference-history-btn-{p.patient_id}">',
                unsafe_allow_html=True,
            )
            with st.popover("📜", use_container_width=False):
                st.caption(
                    f"履歴タイムライン — {p.doctor_surname} ({p.patient_id})"
                )
                history = load_status_history(p.patient_id)
                if not history:
                    st.markdown(
                        '<div class="conf-history-empty">'
                        'まだ履歴はありません（カンファでステータスを更新すると記録されます）。'
                        '</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    # タイムライン表示（時系列順・古い → 新しい）
                    timeline_parts: List[str] = ['<div class="conf-history-timeline">']
                    for idx, h in enumerate(history):
                        ts = h.get("timestamp", "")
                        status = h.get("status", "")
                        cdate = h.get("conference_date", ts[:10] if ts else "")
                        label = _format_status_label(status)
                        is_first = "hist-first" if idx == 0 else ""
                        timeline_parts.append(
                            f'<div class="hist-entry {is_first}">'
                            f'<span class="hist-date">{cdate}</span>'
                            f'{label}'
                            f'</div>'
                        )
                    timeline_parts.append('</div>')
                    st.markdown("".join(timeline_parts), unsafe_allow_html=True)

                    # 遷移ペア表示（2 件以上の履歴がある場合のみ）
                    if len(history) >= 2:
                        st.divider()
                        st.caption("ステータス遷移")
                        for i in range(1, len(history)):
                            prev_label = _format_status_label(
                                history[i - 1].get("status", "")
                            )
                            curr_label = _format_status_label(
                                history[i].get("status", "")
                            )
                            st.markdown(
                                f"- {prev_label} → {curr_label}",
                                unsafe_allow_html=False,
                            )
            st.markdown("</div>", unsafe_allow_html=True)
        with edit_col:
            with st.popover("✏️", use_container_width=False):
                st.caption(
                    f"患者 {p.patient_id}（UUID 先頭8桁）の情報を編集"
                )
                new_doctor = st.text_input(
                    "主治医名",
                    value=doctor_name,
                    key=f"edit_doctor_{p.patient_id}",
                    placeholder="例: 田中医師",
                )
                new_pname = st.text_input(
                    "患者名",
                    value=patient_name,
                    key=f"edit_pname_{p.patient_id}",
                    placeholder="例: 山田太郎",
                )
                new_pid = st.text_input(
                    "患者ID",
                    value=patient_id_str,
                    key=f"edit_pid_{p.patient_id}",
                    placeholder="例: 12345",
                )
                # 2026-04-19: 確認事項フィールド（副院長指示）
                # 複数行可。表示列と同期し、カンファの議論内容をその場で記録
                new_note = st.text_area(
                    "確認事項",
                    value=stored_note,
                    key=f"edit_note_{p.patient_id}",
                    placeholder=f"例: {p.note}",
                    help=(
                        "カンファで話し合った確認事項・次のアクションを記入してください。"
                        "未入力時はサンプル既定値が表示されます。"
                    ),
                    height=80,
                )
                # 変更があれば即保存
                if (new_doctor != doctor_name
                        or new_pname != patient_name
                        or new_pid != patient_id_str
                        or new_note != stored_note):
                    save_patient_info(
                        p.patient_id,
                        doctor_name=new_doctor,
                        patient_name=new_pname,
                        patient_id=new_pid,
                        note=new_note,
                    )
                    st.rerun()

                # --- 個別クリア UI（副院長決定 2026-04-17 Q1=🅲 選択式） ---
                st.divider()
                with st.expander("🗑 クリア", expanded=False):
                    clr_doctor = st.checkbox(
                        "主治医名",
                        key=f"clr_doc_{p.patient_id}",
                    )
                    clr_pname = st.checkbox(
                        "患者名",
                        key=f"clr_name_{p.patient_id}",
                    )
                    clr_pid = st.checkbox(
                        "患者ID",
                        key=f"clr_id_{p.patient_id}",
                    )
                    clr_note = st.checkbox(
                        "確認事項",
                        key=f"clr_note_{p.patient_id}",
                    )
                    clr_status = st.checkbox(
                        "ステータス（🆕 新規に戻す）",
                        key=f"clr_status_{p.patient_id}",
                    )
                    any_checked = (clr_doctor or clr_pname or clr_pid
                                   or clr_note or clr_status)
                    if st.button(
                        "この患者の選択項目をクリア",
                        key=f"clr_exec_{p.patient_id}",
                        disabled=not any_checked,
                    ):
                        cleared_items: List[str] = []
                        if clr_doctor or clr_pname or clr_pid or clr_note:
                            clear_patient_info(
                                p.patient_id,
                                clear_doctor=clr_doctor,
                                clear_name=clr_pname,
                                clear_id=clr_pid,
                                clear_note=clr_note,
                            )
                            if clr_doctor:
                                cleared_items.append("主治医名")
                            if clr_pname:
                                cleared_items.append("患者名")
                            if clr_pid:
                                cleared_items.append("患者ID")
                            if clr_note:
                                cleared_items.append("確認事項")
                        if clr_status:
                            try:
                                clear_status(p.patient_id)
                            except (OSError, ValueError):
                                pass
                            # session_state からも削除
                            st.session_state["conf_patient_status"].pop(
                                p.patient_id, None
                            )
                            cleared_items.append("ステータス")
                        st.success(
                            f"クリア完了: {' / '.join(cleared_items)}"
                        )
                        st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

    # testid hidden div
    st.markdown(
        f'<div data-testid="conference-patient-count" style="display:none">{len(displayed)}</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# ブロック描画: D 職種別 今週のお願い
# ---------------------------------------------------------------------------

def _render_block_d(
    patients: List[SamplePatient],
    mode: str,
) -> None:
    """ブロック D: 4 列 — リハ / 退院支援 NS / 医師 / 看護.

    現状はサンプル固定文言。将来的には patients から動的集計予定。
    """
    counts = _count_status(patients)

    if mode == "holiday":
        reha_items = [
            "連休前退院予定者：退院前 ADL 最終評価・自宅訓練指導",
            "連休中継続ケア：要員シフト確保、機能維持リハ継続",
        ]
        disch_items = [
            "連休前 施設転院者の搬送手配",
            "介護保険 認定調査 前倒し依頼",
            "家族前倒し交渉 1 名以上：連休中旅行等の調整",
        ]
        doc_items = [
            "連休中処方確定：頓用指示・発熱時対応を明記",
            "連休前最終退院判定：4/28 可否確認",
        ]
        nurse_items = [
            "連休前退院者の家族連絡先・緊急時対応を再確認",
            "連休中継続ケアの当番看護・夜勤体制確認",
        ]
    else:
        rehab_n = counts.get("rehab", 0)
        undec_n = counts.get("undecided", 0)
        family_n = counts.get("family", 0)
        facility_n = counts.get("facility", 0)
        insurance_n = counts.get("insurance", 0)
        medical_n = counts.get("medical", 0)
        new_n = counts.get("new", 0)
        reha_items = [
            f"🟠 リハ最適化中 {rehab_n}名：機能目標進捗を本日確認",
            f"⚫ 方向性未決 {undec_n}名：ADL再評価を実施（MSW前段階）",
        ]
        disch_items = [
            f"🟢 家族 {family_n}名：面談・迎え時間調整",
            f"🟡 施設 {facility_n}名：施設打診 / 🟣 介護 {insurance_n}名：ケアマネ調整",
            f"⚫ 未決 {undec_n}名：ADL評価後に施設候補検討",
        ]
        doc_items = [
            f"🔵 OK待ち {medical_n}名：金朝カンファで判定",
            f"⚫ 未決 {undec_n}名：退院目処の再評価",
            f"🆕 新規 {new_n}名：状態評価・カテゴライズ",
        ]
        nurse_items = [
            "全患者の週末処方確認、痛みコントロール再チェック",
            "週末退院予定者の引継ぎを準備",
        ]

    def _render_role(role_cls: str, title: str, items: List[str]) -> str:
        """1 役割のブロック HTML を返す."""
        lis = "".join(f"<li>{it}</li>" for it in items)
        return (
            f'<div class="conf-role {role_cls}">'
            f'<div class="role-name">{title}</div>'
            f'<ul>{lis}</ul></div>'
        )

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(_render_role("reha", "🏃 リハ PT/OT/ST", reha_items), unsafe_allow_html=True)
    with col2:
        st.markdown(_render_role("disch", "📋 退院支援 NS", disch_items), unsafe_allow_html=True)
    with col3:
        st.markdown(_render_role("doc", "👔 医師", doc_items), unsafe_allow_html=True)
    with col4:
        st.markdown(_render_role("nurse", "🧑‍⚕️ 看護", nurse_items), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# ブロック描画: ファクトバー
# ---------------------------------------------------------------------------

def _render_fact_bar(
    ward: str,
    mode: str,
    rng: Optional[random.Random] = None,
    facts_override: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """facts.yaml から 1 件抽選して画面下部に表示する（印刷時非表示）.

    2026-04-18 副院長指示で以下を追加:
    - ローテーション表示は ``rotation_eligible=True`` の 12 件に限定
      （入院延長×リハ介入×高齢者予後改善を示す強エビデンスのみ）
    - 下部に「📚 他のエビデンスを見る」折りたたみ expander を配置し、
      全 80 件をレイヤー別に勉強目的で閲覧できるようにする。
    - 折りたたみ部は ``@media print`` で非表示にする（ローテーションは印刷表示）。
    """
    facts = facts_override if facts_override is not None else _load_facts()
    fact = _select_fact(facts, ward, mode, rng=rng)
    if fact is None:
        # フォールバック
        st.markdown(
            '<div class="conf-fact-bar">'
            '<span class="fact-label">エビデンス</span>'
            '<span class="fact-text">該当するファクトがありません（facts.yaml の context を確認）</span>'
            '<span class="fact-src">—</span>'
            '</div>'
            '<div data-testid="conference-fact-id" style="display:none"></div>',
            unsafe_allow_html=True,
        )
        # ローテーションがなくても折りたたみライブラリは描画（勉強目的）
        _render_fact_library(facts)
        return

    fact_id = str(fact.get("id", ""))
    text = str(fact.get("text", ""))
    author = str(fact.get("author", ""))
    journal = str(fact.get("journal", ""))
    year = fact.get("year", "")
    pmid = fact.get("pmid")
    src_parts: List[str] = []
    if author:
        src_parts.append(author)
    if journal:
        src_parts.append(str(journal))
    if year:
        src_parts.append(str(year))
    if pmid:
        src_parts.append(f"PMID: {pmid}")
    src_text = " | ".join(src_parts)

    st.markdown(
        f"""
        <div class="conf-fact-bar">
          <span class="fact-label">エビデンス</span>
          <span class="fact-text">{text}</span>
          <span class="fact-src">{src_text}</span>
        </div>
        <div data-testid="conference-fact-id" style="display:none">{fact_id}</div>
        """,
        unsafe_allow_html=True,
    )

    # 折りたたみファクトライブラリ（全 80 件、勉強目的、印刷時非表示）
    _render_fact_library(facts)


# ---------------------------------------------------------------------------
# ブロック描画: 📚 ファクトライブラリ（折りたたみ expander）
# ---------------------------------------------------------------------------

def _render_fact_library(
    facts: List[Dict[str, Any]],
) -> None:
    """ローテーション対象外のファクトも含めた全件をレイヤー別に表示する expander.

    副院長指示（2026-04-18）:
    - ローテーションバー（rotation_eligible=True の 12 件）とは別に、
      残りのエビデンスも勉強目的で閲覧できるようにする
    - 折りたたみで画面の密度を保つ
    - 印刷時は自動で非表示（``@media print`` による）
    - 検索ボックスで日本語キーワード絞り込み可能
    """
    if not facts:
        return

    # 件数内訳を事前計算
    total = len(facts)
    rotation_count = sum(1 for f in facts if f.get("rotation_eligible") is True)
    non_rotation_count = total - rotation_count

    # hidden div: E2E 用 testid（件数確認）
    st.markdown(
        '<div class="conf-fact-library-wrap">'
        f'<div data-testid="conference-fact-library-total" style="display:none">{total}</div>'
        f'<div data-testid="conference-fact-library-rotation" style="display:none">{rotation_count}</div>'
        f'<div data-testid="conference-fact-library-non-rotation" style="display:none">{non_rotation_count}</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Streamlit の st.expander を使って検索ボックスを内部に配置
    # ラベルに件数を出して「何が見られるか」を明示
    label = f"📚 他のエビデンスを見る（全 {total} 件・勉強用）"
    with st.expander(label, expanded=False):
        # data-testid: expander 本体の識別
        st.markdown(
            '<div data-testid="conference-fact-library-expander" style="display:none">open</div>',
            unsafe_allow_html=True,
        )

        # 検索ボックス（日本語でキーワード絞り込み）
        # key は session_state 経由で維持される
        keyword = st.text_input(
            "🔍 キーワード検索（著者名・雑誌名・本文）",
            value="",
            key="conf_fact_library_keyword",
            placeholder="例: Cochrane / 脳卒中 / 日本 / HAD / Bernabei ...",
        )

        filtered = _filter_facts_by_keyword(facts, keyword)
        grouped = _group_facts_by_layer(filtered)

        if not filtered:
            st.markdown(
                '<div class="fact-lib-empty">該当するファクトが見つかりません（キーワードを変えてお試しください）</div>',
                unsafe_allow_html=True,
            )
            return

        # レイヤー順に表示
        body_html_parts: List[str] = ['<div class="fact-lib-body">']
        for section in _EXPANDER_LAYER_ORDER:
            layer_num = section["layer"]
            emoji = section["emoji"]
            title = section["title"]
            items = grouped.get(layer_num, [])
            if not items:
                continue
            cnt = len(items)
            body_html_parts.append(
                f'<div class="fact-lib-section" data-testid="fact-lib-section-{layer_num}">'
                f'<div class="fact-lib-section-title">{emoji} {title}'
                f'<span class="lib-count">（{cnt} 件）</span></div>'
            )
            for fact in items:
                is_rot = fact.get("rotation_eligible") is True
                css_class = "fact-lib-item rotation" if is_rot else "fact-lib-item"
                badge = (
                    '<span class="lib-rot-badge">ROTATION</span>'
                    if is_rot else ""
                )
                text = str(fact.get("text", ""))
                author = str(fact.get("author", ""))
                journal = str(fact.get("journal", ""))
                year = fact.get("year", "")
                n_val = str(fact.get("n", ""))
                pmid = fact.get("pmid")
                doi = fact.get("doi")
                meta_parts: List[str] = []
                if author:
                    meta_parts.append(author)
                if journal:
                    meta_parts.append(journal)
                if year:
                    meta_parts.append(str(year))
                if n_val:
                    meta_parts.append(n_val)
                if pmid:
                    meta_parts.append(
                        f'<span class="lib-pmid">PMID: {pmid}</span>'
                    )
                elif doi:
                    meta_parts.append(f'DOI: {doi}')
                meta_text = " | ".join(meta_parts)
                fact_id = str(fact.get("id", ""))
                body_html_parts.append(
                    f'<div class="{css_class}" data-testid="fact-lib-item-{fact_id}">'
                    f'<div class="lib-text">{badge}{text}</div>'
                    f'<div class="lib-meta">{meta_text}</div>'
                    f'</div>'
                )
            body_html_parts.append('</div>')

        body_html_parts.append('</div>')
        st.markdown(
            '<div class="conf-fact-library-wrap">' + "".join(body_html_parts) + '</div>',
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# 履歴ビュー: 週次カンファ履歴（2026-04-18 新規）
# ---------------------------------------------------------------------------

def _format_status_label(status_key: str) -> str:
    """status_key → 表示ラベル（emoji + 日本語）. モード非依存で両プールから探す.

    Notes
    -----
    - 履歴表示はモードに関係なく過去の status_key をそのまま読む
    - 通常モード 7 種 + 連休モード 3 種の統合プールから検索
    - 未知の値は "❓ 未分類" を返す
    """
    for pool in (_STATUS_NORMAL, _STATUS_HOLIDAY):
        for s in pool:
            if s["key"] == status_key:
                return f"{s['emoji']} {s['label']}"
    return "❓ 未分類"


def _aggregate_status_changes(
    changes: List[Dict[str, str]],
) -> Dict[Tuple[str, str], int]:
    """変化イベントのリストを遷移ペアごとに集計する.

    Parameters
    ----------
    changes : list
        :func:`get_status_changes_this_week` の返り値

    Returns
    -------
    dict
        ``{(from_status, to_status): count, ...}``。
        初出エントリ（from_status が空）は ``("", to_status)`` キーで集計。
    """
    agg: Dict[Tuple[str, str], int] = {}
    for c in changes:
        key = (c.get("from_status", ""), c.get("to_status", ""))
        agg[key] = agg.get(key, 0) + 1
    return agg


def _render_weekly_history_expander(
    patients: List[SamplePatient],
    today: date,
) -> None:
    """週次カンファ履歴エクスパンダーを描画する（エビデンスバー直上）.

    副院長指示（2026-04-18）: 振り返り・トレンド可視化専用。
    プロフェッショナルなトーン（個人非難しない）で傾向分析に特化する。

    含まれる要素:
    - 今週のステータス変化サマリー（遷移ペア × 件数）
    - 停滞警告: 3 週以上ステータスが変わらない患者
    - 長期入院 × 方向性未決 の要議論リスト

    Parameters
    ----------
    patients : list
        表示中の患者リスト（病棟フィルタ後）。
        停滞判定は表示中の患者 ID と履歴の intersection のみで行う。
    today : date
        基準日（通常はカンファ当日）
    """
    # 表示中の患者 UUID をセットで保持（病棟フィルタ後）
    displayed_uuids = {p.patient_id for p in patients}
    day_count_by_uuid = {p.patient_id: p.day_count for p in patients}
    note_by_uuid = {p.patient_id: p.note for p in patients}

    # 履歴データ取得（変化件数 + 停滞患者）
    # 2026-04-19: 実履歴が空でも教育デモが意味を持つよう effective 関数に切替
    changes = _get_effective_status_changes(today, days=7)
    # 表示中の病棟の患者のみフィルタ
    changes_in_ward = [c for c in changes if c.get("uuid") in displayed_uuids]

    stagnant = get_stagnant_patients(today, weeks=3)
    stagnant_in_ward = [s for s in stagnant if s.get("uuid") in displayed_uuids]

    # 長期入院 × 方向性未決: 表示中患者でステータスが "undecided" かつ在院日数 >= 21 日
    # 最新ステータスは現在ステータスから取得（履歴なしでも評価可能にするため）
    current_statuses = load_all_statuses()
    long_stay_undecided: List[Dict[str, object]] = []
    for p in patients:
        latest = current_statuses.get(p.patient_id, p.status_key)
        if latest == "undecided" and p.day_count >= 21:
            long_stay_undecided.append({
                "uuid": p.patient_id,
                "day_count": p.day_count,
                "note": p.note,
            })

    # hidden testid: 集計件数を E2E テストから参照可能にする
    st.markdown(
        '<div class="conf-history-expander-wrap">'
        f'<div data-testid="conference-history-changes-count" style="display:none">'
        f'{len(changes_in_ward)}</div>'
        f'<div data-testid="conference-history-stagnant-count" style="display:none">'
        f'{len(stagnant_in_ward)}</div>'
        f'<div data-testid="conference-history-long-undecided-count" style="display:none">'
        f'{len(long_stay_undecided)}</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    label = "📈 先週からの変化（履歴・停滞・要議論）"
    with st.expander(label, expanded=False):
        st.markdown(
            '<div data-testid="conference-history-expander" style="display:none">open</div>',
            unsafe_allow_html=True,
        )

        # === セクション 1: 今週のステータス変化サマリー ===
        if changes_in_ward:
            agg = _aggregate_status_changes(changes_in_ward)
            summary_items: List[str] = []
            # 初出（from が空）と遷移を分けて表示
            transitions = []
            new_entries = 0
            for (from_k, to_k), cnt in sorted(
                agg.items(), key=lambda kv: (-kv[1], kv[0][1])
            ):
                if not from_k:
                    new_entries += cnt
                    continue
                transitions.append(
                    f'<span class="conf-history-summary-item">'
                    f'{_format_status_label(from_k)} → {_format_status_label(to_k)}: '
                    f'{cnt} 名</span>'
                )
            pieces_html = "".join(transitions)
            new_pieces = ""
            if new_entries:
                new_pieces = (
                    f'<span class="conf-history-summary-item">'
                    f'🆕 新規トラッキング開始: {new_entries} 名</span>'
                )
            st.markdown(
                f'<div class="conf-history-summary">'
                f'<div class="conf-history-summary-title">'
                f'今週のステータス変化（直近 7 日・{ward_label(patients)}）</div>'
                f'{pieces_html}{new_pieces}'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="conf-history-empty">'
                '今週はステータス変化の履歴が記録されていません（初回起動時や全員の状態が先週から不変の場合に表示されます）。'
                '</div>',
                unsafe_allow_html=True,
            )

        # === セクション 2: 停滞警告 ===
        if stagnant_in_ward:
            items_html: List[str] = []
            for s in stagnant_in_ward:
                uuid = s.get("uuid", "")
                status_label = _format_status_label(s.get("status", ""))
                weeks = s.get("weeks_stagnant", "")
                last_changed = s.get("last_changed", "")
                day_count = day_count_by_uuid.get(uuid, 0)
                items_html.append(
                    f'<div class="conf-history-summary-item" '
                    f'data-testid="conference-history-stagnant-{uuid}">'
                    f'ID {uuid} (Day {day_count}): {status_label}から {weeks} 週停滞 '
                    f'(最終更新 {last_changed})'
                    f'</div>'
                )
            st.markdown(
                f'<div class="conf-history-warning">'
                f'<div class="conf-history-warning-title">'
                f'⚠ 3 週以上ステータス変化のない患者（要再評価）</div>'
                f'{"".join(items_html)}'
                f'</div>',
                unsafe_allow_html=True,
            )

        # === セクション 3: 長期入院 × 方向性未決 ===
        if long_stay_undecided:
            items_html2: List[str] = []
            for lu in long_stay_undecided:
                uuid = lu.get("uuid", "")
                day = lu.get("day_count", "")
                note = lu.get("note", "")
                items_html2.append(
                    f'<div class="conf-history-summary-item" '
                    f'data-testid="conference-history-long-undecided-{uuid}">'
                    f'ID {uuid} (Day {day}): {note}'
                    f'</div>'
                )
            st.markdown(
                f'<div class="conf-history-warning">'
                f'<div class="conf-history-warning-title">'
                f'⚠ 在院 21 日以上 × 方向性未決（カンファで重点議論）</div>'
                f'{"".join(items_html2)}'
                f'</div>',
                unsafe_allow_html=True,
            )

        # 全セクションが空の場合のフォールバック
        if (not changes_in_ward and not stagnant_in_ward
                and not long_stay_undecided):
            st.markdown(
                '<div class="conf-history-empty">'
                '履歴データはまだ蓄積されていません。カンファでステータスを更新していくと、'
                '次週以降ここにトレンドが表示されます。'
                '</div>',
                unsafe_allow_html=True,
            )


def ward_label(patients: List[SamplePatient]) -> str:
    """患者リストの代表病棟（表示中サンプルの最頻）を返す.

    Notes
    -----
    ヒストリー表示のキャプションに使う軽量ヘルパ。
    """
    if not patients:
        return "—"
    # 先頭患者の病棟を使う（_resolve_patients で 1 病棟にフィルタ済み前提）
    return patients[0].ward


# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------

def render_conference_material_view(
    today: Optional[date] = None,
    *,
    rng: Optional[random.Random] = None,
    facts_override: Optional[List[Dict[str, Any]]] = None,
    data_source_override: Optional[str] = None,
    df_override=None,
) -> None:
    """多職種退院調整・連休対策カンファ資料画面を描画する（Phase 1 + 実データ連携）.

    Parameters
    ----------
    today : date, optional
        基準日。None なら ``date.today()``。
    rng : random.Random, optional
        ファクト抽選用の乱数器（テスト用）。None なら新規生成。
    facts_override : list, optional
        facts.yaml 読み込みを上書きするリスト（テスト用）。
    data_source_override : str, optional
        データソースラベルを直接指定（テスト用）。None の場合
        ``st.session_state["data_source_mode"]`` を参照。
    df_override : pd.DataFrame, optional
        admission_details DataFrame を直接注入（テスト用）。

    Returns
    -------
    None
        副作用（Streamlit 画面描画）のみ。

    Notes
    -----
    - 16:9 レイアウトは親ページの ``st.set_page_config(layout="wide")`` 前提。
    - ステータス更新は ``st.session_state['conf_patient_status']`` に保存される。
    - データソース「実績データ（日次入力）」モードでは admission_details から
      現在入院中の患者を取得する。データが無い場合は警告を表示し、サンプルは出さない。
    """
    _today = today if today is not None else date.today()
    _init_session(_today)

    # CSS は毎回注入（reactive でも重複は Streamlit 側で吸収される）
    _inject_css()

    # カンファ画面全体を .conf-root スコープで包む（CSS の .conf-root セレクタを有効化）
    # close tag は関数末尾（ファクトバー後）に書く
    st.markdown('<div class="conf-root">', unsafe_allow_html=True)

    # --- 上部コントロール: 病棟 / モード 切替 ---
    ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([2, 2, 3])
    with ctrl_col1:
        selected_ward = st.selectbox(
            "病棟",
            _WARD_OPTIONS,
            index=_WARD_OPTIONS.index(st.session_state["conf_ward"]),
            key="conf_ward_select",
        )
        if selected_ward != st.session_state["conf_ward"]:
            st.session_state["conf_ward"] = selected_ward
            # 病棟変更時は患者ステータスをリセット（異なる患者群のため）
            st.session_state["conf_patient_status"] = {}
    with ctrl_col2:
        holiday_mode = st.toggle(
            "連休対策モード",
            value=(st.session_state["conf_mode"] == "holiday"),
            key="conf_mode_toggle",
        )
        new_mode = "holiday" if holiday_mode else "normal"
        if new_mode != st.session_state["conf_mode"]:
            st.session_state["conf_mode"] = new_mode
            # モード変更時もステータスをリセット（カテゴリ体系が異なる）
            st.session_state["conf_patient_status"] = {}
    with ctrl_col3:
        # 2026-04-18 圧縮: 縦幅を食わないよう長文 caption を削除
        st.caption("連休 5 連休以上の場合は自動で連休対策モードを推奨")

    ward = st.session_state["conf_ward"]
    mode = st.session_state["conf_mode"]
    banner = get_holiday_mode_banner(_today)

    # testid hidden — モード・病棟
    st.markdown(
        f'<div data-testid="conference-mode" style="display:none">{mode}</div>'
        f'<div data-testid="conference-ward" style="display:none">{ward}</div>',
        unsafe_allow_html=True,
    )

    # --- ヘッダー ---
    _render_header(_today, ward, mode, banner)

    # --- データ管理（一括クリア）— 2026-04-18 サイドバーに移設（縦 40px 削減）---
    _render_data_manage_expander()

    # --- 連休対策モード切替 推奨バナー（Block A 直上） ---
    # 副院長決定（2026-04-18）: 連休対策モードは師長が手動で ON/OFF する運用。
    # ただし「連休まで 21 日以下」になったら、切替のきっかけとなる推奨バナーを
    # 画面上部に表示する。バナーは通常モード時のみ表示し、連休対策モード ON 時は
    # 非表示（既に切替済みのため）。
    # severity: 8-21 日は warning（橙）、7 日以内は urgent（赤、_bc_alert では danger に変換）。
    _render_holiday_mode_recommendation_banner(mode, banner)

    # --- ブロック A: KPI 5 横並び ---
    # サマリー上部の数値と一致させるため、session_state を参照して
    # 実データから計算する (副院長決定 2026-04-18)。
    # データが未読込ならサンプル値にフォールバック。
    kpi = _compute_live_kpi_metrics(ward, _today) or _sample_kpi_metrics(ward)
    _render_block_a(ward, _today, banner, kpi)

    # --- 中央: ブロック B (左 300px) + ブロック C (右) ---
    # データソースに応じてサンプル or 実データを選択する
    patients, _data_src, _data_meta = _resolve_patients(
        _today, ward, mode,
        data_source_override=data_source_override,
        df_override=df_override,
    )

    # 実データモード時、データが無い or 入院患者が少ないケースで情報提示
    if _data_src == "actual":
        _reason = _data_meta.get("reason", "ok")
        _total = int(_data_meta.get("total_inpatients", 0))
        if _reason == "no_data":
            st.warning(
                "実データモードですが、入退院詳細データが未登録です。"
                "まず「⚙️ データ・設定 → 日次データ入力」で入退院イベントを入力してください。"
                " — サンプル患者は表示しません。"
            )
        elif _reason == "no_inpatients":
            st.warning(
                f"実データモードですが、{ward} に現在入院中の患者がいません（データ上の退院済みを除外済み）。"
                "直近の入院イベントが登録されているか確認してください。"
            )
        elif _reason == "ok" and _total < _MAX_PATIENTS_DISPLAYED:
            st.info(f"実データで取得できた {ward} の在院患者は {_total} 名です。")
        # data-testid: 実データフラグ（E2E で識別可能にしておく）
        st.markdown(
            f'<div data-testid="conference-data-source" style="display:none">actual</div>'
            f'<div data-testid="conference-inpatient-count" style="display:none">{_total}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div data-testid="conference-data-source" style="display:none">sample</div>',
            unsafe_allow_html=True,
        )

    # Block B: 来週末の見通しに必要な日次・詳細データを session_state から取得
    # (None なら _render_block_b 側で自動的にサンプル表示にフォールバック)
    _block_b_daily_df = None
    _block_b_detail_df = None
    try:
        _ward_dfs_full = (
            st.session_state.get("sim_ward_raw_dfs_full")
            or st.session_state.get("ward_raw_dfs_full")
            or {}
        )
        if ward in _ward_dfs_full:
            _block_b_daily_df = _ward_dfs_full[ward]
        _block_b_detail_df = st.session_state.get("admission_details")
    except Exception:
        pass

    middle_left, middle_right = st.columns([0.3, 0.7])
    with middle_left:
        _render_block_b(
            ward, mode, patients,
            daily_df=_block_b_daily_df,
            detail_df=_block_b_detail_df,
            today=_today,
        )
    with middle_right:
        _render_block_c(patients, mode, _today)

    # --- ブロック D: 職種別 今週のお願い ---
    # 2026-04-18 圧縮: 不要な &nbsp; 余白を削除（縦 26px 削減）
    _render_block_d(patients, mode)

    # --- 📈 週次カンファ履歴エクスパンダー（エビデンスバー直上） ---
    # 2026-04-18 新規: 先週からの変化・停滞警告・要議論リストを可視化
    _render_weekly_history_expander(patients, _today)

    # --- ファクトバー ---
    _render_fact_bar(ward, mode, rng=rng, facts_override=facts_override)

    # conf-root スコープを閉じる
    st.markdown('</div>', unsafe_allow_html=True)
