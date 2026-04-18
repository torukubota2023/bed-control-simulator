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

import random
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    load_all_statuses,
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


def _sample_kpi_metrics(ward: str) -> Dict[str, float]:
    """病棟別サンプル KPI 値（Phase 1 はハードコード、Phase 2 で実データ接続）."""
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
# CSS 注入
# ---------------------------------------------------------------------------

def _inject_css() -> None:
    """画面共通の CSS を注入する（モック HTML に近いルック）.

    印刷時にファクトバーを非表示にする ``@media print`` も同時に注入する。
    """
    st.markdown(
        """
        <style>
        /* コンテナ幅拡張 */
        .conf-root .block-container { padding-top: 1rem; padding-bottom: 1rem; }
        /* ヘッダー */
        .conf-header {
            background: #2c3e50;
            color: #fff;
            padding: 8px 16px;
            border-radius: 4px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-family: "Hiragino Sans", "Yu Gothic", "Meiryo", sans-serif;
            margin-bottom: 10px;
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
        /* KPI 行 */
        .conf-kpi-row {
            background: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 4px;
            padding: 8px 12px;
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 12px;
            margin-bottom: 10px;
        }
        .conf-kpi { text-align: center; }
        .conf-kpi .label { font-size: 10px; color: #666; }
        .conf-kpi .value {
            font-size: 20px;
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
            padding: 1px 8px;
            border-radius: 10px;
            font-size: 11px;
            font-weight: 600;
            white-space: nowrap;
        }
        /* 患者行 — 医師/患者 170px / 病棟 32px / Day 46px / 予定 72px / 確認事項 1fr
           ステータスと編集は Streamlit 列側に分離（popover クリック用） */
        .conf-patient-row {
            display: grid;
            grid-template-columns: 170px 32px 46px 72px 1fr;
            gap: 6px;
            align-items: center;
            padding: 4px 6px;
            font-size: 12px;
            border-bottom: 1px solid #f3f3f3;
            line-height: 1.3;
        }
        .conf-patient-row .doctor { font-weight: 600; color: #333; }
        .conf-patient-row .doctor .pname { color: #444; font-weight: 500; }
        .conf-patient-row .doctor .pid {
            color: #888;
            font-size: 10px;
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
        .conf-patient-row .note { color: #333; }
        /* 予測行 */
        .conf-forecast-row {
            display: grid;
            grid-template-columns: 60px 1fr 1fr;
            gap: 4px;
            font-size: 12px;
            padding: 3px 0;
            border-bottom: 1px dashed #eee;
        }
        .conf-forecast-row .day { font-weight: 600; }
        .conf-forecast-row .vacancy.warn { color: #e67e22; font-weight: 600; }
        .conf-forecast-row .vacancy.danger { color: #c0392b; font-weight: 600; }
        .conf-forecast-summary {
            margin-top: 8px;
            padding: 8px;
            background: #fff3e0;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
            text-align: center;
            color: #e65100;
        }
        /* 役割ブロック */
        .conf-role {
            padding: 6px 10px;
            border-left: 3px solid #3498db;
            font-size: 12px;
            background: #fafbfc;
            border-radius: 2px;
            margin-bottom: 6px;
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
        .conf-role li { font-size: 11px; line-height: 1.4; padding: 1px 0; color: #444; }
        .conf-role li::before { content: "・"; margin-right: 2px; }
        /* ファクトバー */
        .conf-fact-bar {
            background: #2c3e50;
            color: #ecf0f1;
            padding: 8px 14px;
            border-radius: 4px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 12px;
            margin-top: 10px;
        }
        .conf-fact-bar .fact-label {
            font-size: 10px;
            background: #34495e;
            padding: 2px 6px;
            border-radius: 3px;
            margin-right: 10px;
        }
        .conf-fact-bar .fact-text { flex: 1; }
        .conf-fact-bar .fact-src {
            font-size: 10px;
            opacity: 0.75;
            margin-left: 10px;
        }
        /* ステータス popover trigger（タグ風スタイル）
           副院長決定（2026-04-17）: ステータスタグ自体をクリッカブルにして
           タグ → プルダウン → その場で変更 の一貫した UX にする */
        .conf-status-popover-wrap .stPopover > div[data-testid="stPopoverButton"] > button,
        .conf-status-popover-wrap div[data-testid="stPopover"] > div > button,
        .conf-status-popover-wrap button[kind="secondary"] {
            background: var(--conf-status-bg, #e9ecef) !important;
            color: var(--conf-status-fg, #495057) !important;
            border: none !important;
            border-radius: 12px !important;
            padding: 2px 10px !important;
            font-size: 11px !important;
            font-weight: 600 !important;
            min-height: 24px !important;
            height: auto !important;
            line-height: 1.3 !important;
            white-space: nowrap !important;
            box-shadow: none !important;
        }
        .conf-status-popover-wrap .stPopover > div[data-testid="stPopoverButton"] > button:hover,
        .conf-status-popover-wrap div[data-testid="stPopover"] > div > button:hover,
        .conf-status-popover-wrap button[kind="secondary"]:hover {
            opacity: 0.9 !important;
            cursor: pointer !important;
        }
        /* 編集ボタン（✏️）も小さく */
        .conf-edit-btn-wrap .stPopover > div[data-testid="stPopoverButton"] > button,
        .conf-edit-btn-wrap div[data-testid="stPopover"] > div > button,
        .conf-edit-btn-wrap button[kind="secondary"] {
            min-height: 24px !important;
            height: auto !important;
            padding: 2px 6px !important;
            font-size: 11px !important;
        }
        @media print {
            .conf-fact-bar { display: none !important; }
            /* 編集ボタン（popover）は印刷時に非表示。患者名・ID はそのまま印刷 */
            .conf-edit-btn-wrap { display: none !important; }
            /* ステータス popover も印刷時は静的ラベル表示のみにする（トリガー部非表示） */
            .conf-status-popover-wrap .stPopover { display: none !important; }
            .conf-status-print-tag { display: inline-block !important; }
            /* データ管理 expander は印刷不要 */
            .conf-data-manage-wrap { display: none !important; }
        }
        .conf-status-print-tag { display: none; }
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

    - ヘッダー付近に ``st.expander`` で配置（closed by default）
    - チェックボックスで対象を選択（主治医名 / 患者名 / 患者ID / ステータス）
    - 「クリア」のタイプ入力で二重確認
    - 入力 == "クリア" かつ 1 件以上チェックで実行ボタンが有効化
    - 実行後: フィードバック + 確認入力欄リセット + rerun
    - 印刷時は ``conf-data-manage-wrap`` クラスで非表示
    """
    # 印刷時非表示用のラッパークラス
    st.markdown(
        '<div class="conf-data-manage-wrap">',
        unsafe_allow_html=True,
    )
    with st.expander("🗑 データ管理（一括クリア）", expanded=False):
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
    st.markdown("</div>", unsafe_allow_html=True)


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
# ブロック描画: ヘッダー
# ---------------------------------------------------------------------------

def _render_header(
    today: date,
    ward: str,
    mode: str,
    banner: Dict[str, Any],
) -> None:
    """ヘッダー（タイトル・モード・病棟・連休カウントダウン）を描画."""
    mode_label = "通常モード" if mode == "normal" else "🚨 連休対策モード"
    mode_cls = "" if mode == "normal" else "holiday"
    # 曜日表示
    weekday_ja = ["月", "火", "水", "木", "金", "土", "日"][today.weekday()]
    days_cls = _severity_to_cls(banner.get("severity", "none"))
    banner_text = banner.get("banner_text", "") or ""
    st.markdown(
        f"""
        <div class="conf-header">
          <div>
            <span class="title">🗓 多職種退院調整・連休対策カンファ</span>
            <span class="mode {mode_cls}">{mode_label}</span>
          </div>
          <div class="meta">
            {today.isoformat()} ({weekday_ja}) | {ward} 表示中 |
            <span class="days {days_cls}">{banner_text}</span>
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
            <div class="value" style="color:{countdown_color};font-size:16px;">{countdown_text}</div>
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

def _render_block_b(
    ward: str,
    mode: str,
    patients: List[SamplePatient],
) -> None:
    """ブロック B: 週末見通し + ステータス内訳."""
    forecast = _sample_weekend_forecast(ward, mode)

    title = (
        f"GW期間 {len(forecast)}連休の見通し（{ward}）"
        if mode == "holiday"
        else f"今週末の見通し（{ward}）"
    )
    forecast_rows_html = "".join(
        (
            f'<div class="conf-forecast-row">'
            f'<span class="day">{row["day"]}</span>'
            f'<span>空床 <span class="vacancy {row["severity"]}">{row["vacancy"]}</span></span>'
            f'<span>救急余力 {row["er_margin"]:+d}</span>'
            f"</div>"
        )
        for row in forecast
    )

    # 週末受入余力（床日）— 週末または連休期間の空床 vacancy を床日として合計する.
    # 副院長決定（2026-04-17）: 「経営的損失（金額）」から「医療者として応需可能
    # だった患者機会（床日）」への意味転換. 医療倫理上、空床を金額で語らず
    # 「受け入れられた可能性のある患者数」として可視化する.
    total_bed_days = sum(int(row.get("vacancy", 0)) for row in forecast)
    if mode == "holiday":
        cost_text = (
            f"連休期間 週末受入余力 {total_bed_days}床日"
            f"（応需可能だった患者機会）"
        )
        cost_bg = "#ffebee"
        cost_fg = "#b71c1c"
    else:
        cost_text = (
            f"週末受入余力 {total_bed_days}床日"
            f"（応需可能だった患者機会）"
        )
        cost_bg = "#fff3e0"
        cost_fg = "#e65100"

    # 内訳 — 現在の患者リストから集計
    status_counts = _count_status(patients)

    if mode == "holiday":
        # 連休対策モード時は 3 カテゴリ表示
        breakdown_items = []
        for meta in _STATUS_HOLIDAY:
            count = status_counts.get(meta["key"], 0)
            breakdown_items.append(
                f'<div style="display:flex;justify-content:space-between;padding:3px 0;font-size:12px;">'
                f'{_format_status_tag(meta["key"], mode)}'
                f'<span style="font-weight:600;">{count}名</span></div>'
            )
        breakdown_title = f"連休前 退院目標 ({ward})"
    else:
        breakdown_items = []
        for meta in _STATUS_NORMAL:
            count = status_counts.get(meta["key"], 0)
            breakdown_items.append(
                f'<div style="display:flex;justify-content:space-between;padding:3px 0;font-size:12px;">'
                f'{_format_status_tag(meta["key"], mode)}'
                f'<span style="font-weight:600;">{count}名</span></div>'
            )
        breakdown_title = "在院患者ステータス内訳"

    st.markdown(
        f"""
        <div style="border:1px solid #dee2e6;border-radius:4px;padding:10px;background:#fefefe;">
          <div style="font-size:13px;font-weight:700;color:#555;margin-bottom:6px;">{title}</div>
          {forecast_rows_html}
          <div class="conf-forecast-summary" style="background:{cost_bg};color:{cost_fg};">{cost_text}</div>
          <div style="font-size:12px;font-weight:700;color:#555;margin-top:10px;margin-bottom:4px;">
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

def _render_block_c(
    patients: List[SamplePatient],
    mode: str,
) -> None:
    """ブロック C: 10 名の患者行 + ステータス popover + 編集 popover.

    副院長決定（2026-04-17）: ステータスタグ自体をクリック → その場でプルダウン表示
    → 選択 → 即保存 の一貫した UX に刷新（右側の selectbox 列は撤去）。
    """
    # 在院日数降順でソート
    sorted_patients = sorted(patients, key=lambda p: p.day_count, reverse=True)
    displayed = sorted_patients[:_MAX_PATIENTS_DISPLAYED]

    st.markdown(
        f"""
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
          <div style="font-size:13px;font-weight:700;color:#555;">
            個別患者のステータス（カンファで更新）
          </div>
          <div style="font-size:11px;color:#666;">
            表示中 {len(displayed)} / 最大 {_MAX_PATIENTS_DISPLAYED} 名
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ヘッダー（5 列: 医師/患者 | 病棟 | 在院 | 退院予定 | 確認事項）
    # ステータス・編集は Streamlit 列側で別途見出しを描画
    header_col_html, header_col_status, header_col_edit = st.columns(
        [0.80, 0.14, 0.06]
    )
    with header_col_html:
        st.markdown(
            '<div class="conf-patient-row" style="font-size:10px;color:#666;font-weight:600;'
            'border-bottom:2px solid #aaa;">'
            '<span>医師 / 患者</span><span>病棟</span><span>在院</span>'
            '<span>退院予定</span><span>確認事項</span>'
            "</div>",
            unsafe_allow_html=True,
        )
    with header_col_status:
        st.markdown(
            '<div style="font-size:10px;color:#666;font-weight:600;text-align:center;'
            'padding:4px 0;border-bottom:2px solid #aaa;">ステータス</div>',
            unsafe_allow_html=True,
        )
    with header_col_edit:
        st.markdown(
            '<div style="font-size:10px;color:#666;font-weight:600;text-align:center;'
            'padding:4px 0;border-bottom:2px solid #aaa;">編集</div>',
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
        with row_col1:
            st.markdown(
                f"""
                <div class="conf-patient-row">
                  <span class="doctor">{doctor_patient_html}</span>
                  <span class="ward {ward_cls}">{p.ward}</span>
                  <span class="day">Day {p.day_count}</span>
                  <span class="plan-date">{p.planned_date}</span>
                  <span class="note" title="{p.note}">{p.note}</span>
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
                # 変更があれば即保存
                if (new_doctor != doctor_name
                        or new_pname != patient_name
                        or new_pid != patient_id_str):
                    save_patient_info(
                        p.patient_id,
                        doctor_name=new_doctor,
                        patient_name=new_pname,
                        patient_id=new_pid,
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
                    clr_status = st.checkbox(
                        "ステータス（🆕 新規に戻す）",
                        key=f"clr_status_{p.patient_id}",
                    )
                    any_checked = clr_doctor or clr_pname or clr_pid or clr_status
                    if st.button(
                        "この患者の選択項目をクリア",
                        key=f"clr_exec_{p.patient_id}",
                        disabled=not any_checked,
                    ):
                        cleared_items: List[str] = []
                        if clr_doctor or clr_pname or clr_pid:
                            clear_patient_info(
                                p.patient_id,
                                clear_doctor=clr_doctor,
                                clear_name=clr_pname,
                                clear_id=clr_pid,
                            )
                            if clr_doctor:
                                cleared_items.append("主治医名")
                            if clr_pname:
                                cleared_items.append("患者名")
                            if clr_pid:
                                cleared_items.append("患者ID")
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
    """facts.yaml から 1 件抽選して画面下部に表示する（印刷時非表示）."""
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


# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------

def render_conference_material_view(
    today: Optional[date] = None,
    *,
    rng: Optional[random.Random] = None,
    facts_override: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """多職種退院調整・連休対策カンファ資料画面を描画する（Phase 1）.

    Parameters
    ----------
    today : date, optional
        基準日。None なら ``date.today()``。
    rng : random.Random, optional
        ファクト抽選用の乱数器（テスト用）。None なら新規生成。
    facts_override : list, optional
        facts.yaml 読み込みを上書きするリスト（テスト用）。

    Returns
    -------
    None
        副作用（Streamlit 画面描画）のみ。

    Notes
    -----
    - 16:9 レイアウトは親ページの ``st.set_page_config(layout="wide")`` 前提。
    - ステータス更新は ``st.session_state['conf_patient_status']`` に保存される
      （Phase 1 はセッション内のみ、永続化は Phase 2）。
    """
    _today = today if today is not None else date.today()
    _init_session(_today)

    # CSS は毎回注入（reactive でも重複は Streamlit 側で吸収される）
    _inject_css()

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
        st.caption(
            "ヘッダーの連休カウントダウンは ``holiday_calendar`` が自動判定。"
            "モードトグルは表示を切り替えるだけで、カウントダウンは常時表示。"
        )

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

    # --- データ管理（一括クリア）— ヘッダーの直下、Block A の直前 ---
    _render_data_manage_expander()

    # --- ブロック A: KPI 5 横並び ---
    kpi = _sample_kpi_metrics(ward)
    _render_block_a(ward, _today, banner, kpi)

    # --- 中央: ブロック B (左 300px) + ブロック C (右) ---
    patients = _get_sample_patients(ward, mode)
    middle_left, middle_right = st.columns([0.3, 0.7])
    with middle_left:
        _render_block_b(ward, mode, patients)
    with middle_right:
        _render_block_c(patients, mode)

    # --- ブロック D: 職種別 今週のお願い ---
    st.markdown("&nbsp;", unsafe_allow_html=True)
    _render_block_d(patients, mode)

    # --- ファクトバー ---
    _render_fact_bar(ward, mode, rng=rng, facts_override=facts_override)
