from __future__ import annotations

"""
HOPE送信用サマリー生成モジュール

富士通HOPE電子カルテのToDo機能で一斉送信するための
病床管理メッセージを生成する。

制約:
- 400文字以内（HOPEのToDo文字数制限）
- 患者個人情報は絶対に含めない（氏名・ID・生年月日なし）
- 入院日と在院日数のみで表現する
"""

from datetime import date, datetime
from typing import Optional

import streamlit as st

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

# HOPEのToDo機能の文字数制限
MAX_CHARS = 400

# 署名
SIGNATURE = "（病床管理室）"


# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------

def _format_date_short(d: date) -> str:
    """日付を短い形式に変換する（例: 4/5）"""
    return f"{d.month}/{d.day}"


def _count_chars(text: str) -> int:
    """メッセージの文字数をカウントする（改行含む）"""
    return len(text)


def _trim_to_limit(text: str, limit: int = MAX_CHARS) -> str:
    """文字数制限を超える場合、末尾を切り詰めて署名を付け直す"""
    if _count_chars(text) <= limit:
        return text
    # 署名を除いた本文を切り詰める
    trimmed = text[: limit - len(SIGNATURE) - len("\n…\n")]
    # 最後の改行位置で切る（行の途中で切れないようにする）
    last_newline = trimmed.rfind("\n")
    if last_newline > 0:
        trimmed = trimmed[:last_newline]
    return trimmed + "\n…\n" + SIGNATURE


# ---------------------------------------------------------------------------
# 1. 全体サマリーメッセージ生成
# ---------------------------------------------------------------------------

def generate_summary_message(
    target_date,
    total_beds,
    ward_data,
    admissions,
    discharges,
    avg_los=None,
    notes=None,
    rolling_los=None,
    rolling_los_limit=None,
    rolling_days=None,
    ward_rolling_los=None,
):
    """
    全体サマリーメッセージ（全員向け）を生成する。

    Parameters
    ----------
    target_date : date
        対象日付
    total_beds : int
        総病床数（94）
    ward_data : dict
        病棟別データ。例:
        {"5F": {"patients": 40, "beds": 47},
         "6F": {"patients": 46, "beds": 47}}
    admissions : int
        当日入院数
    discharges : int
        当日退院数
    avg_los : float, optional
        平均在院日数（今月集計）
    notes : str, optional
        追加コメント（状況・対応方針など）
    rolling_los : float, optional
        [後方互換] 全体の3ヶ月rolling LOS（ward_rolling_los を優先推奨）
    rolling_los_limit : int, optional
        施設基準の上限日数（例: 21日、20日）
    rolling_days : int, optional
        rolling計算に使った実際の日数（90日に満たない場合もあり）
    ward_rolling_los : dict, optional
        病棟別の3ヶ月rolling LOS（2026年改定対応・施設基準判定は各病棟ごと）
        例: {"5F": {"los": 18.5, "days": 90}, "6F": {"los": 19.2, "days": 85}}

    Returns
    -------
    str
        400文字以内のメッセージ
    """
    date_str = _format_date_short(target_date)

    # 全体の患者数・稼働率を計算
    total_patients = sum(w["patients"] for w in ward_data.values())
    overall_rate = total_patients / total_beds * 100 if total_beds > 0 else 0
    net_change = admissions - discharges
    net_sign = "+" if net_change >= 0 else ""

    # ヘッダー
    lines = [
        f"【病床管理】{date_str}",
        f"全体{total_patients}/{total_beds}床({overall_rate:.1f}%)",
    ]

    # 病棟別情報
    for ward_name in sorted(ward_data.keys()):
        w = ward_data[ward_name]
        patients = w["patients"]
        beds = w["beds"]
        rate = patients / beds * 100 if beds > 0 else 0
        vacancy = beds - patients
        warning = "⚠" if rate >= 95 else ""
        if vacancy <= 0:
            lines.append(f"{ward_name}:{patients}/{beds}床({rate:.1f}%) 満床{warning}")
        else:
            label = "残" if vacancy <= 2 else "空"
            lines.append(f"{ward_name}:{patients}/{beds}床({rate:.1f}%) {label}{vacancy}床{warning}")

    # 入退院サマリー
    lines.append(f"本日 入院{admissions} 退院{discharges} 純増{net_sign}{net_change}")

    # 平均在院日数（今月集計）
    if avg_los is not None:
        lines.append(f"平均在院日数:{avg_los:.1f}日")

    # 過去3ヶ月rolling 平均在院日数（病棟別・施設基準判定用・2026年改定対応）
    # ⚠️ 施設基準は各病棟ごとに判定するため、病棟別に表示する
    # 2026年改定: 短手3算定患者は計算から除外（los_ex_short3 があればそちらで判定）
    if ward_rolling_los:
        _rolling_parts = []
        _any_excluded = False  # 短手3 除外が実際に効いているか
        for _wname in sorted(ward_rolling_los.keys()):
            _wdata = ward_rolling_los[_wname]
            _wlos = _wdata.get("los") if isinstance(_wdata, dict) else None
            _wlos_ex = _wdata.get("los_ex_short3") if isinstance(_wdata, dict) else None
            _wdays = _wdata.get("days") if isinstance(_wdata, dict) else None
            if _wlos is None:
                continue
            # 施設基準判定は除外後の値を優先
            _wjudge = _wlos_ex if _wlos_ex is not None else _wlos
            if _wlos_ex is not None and _wlos_ex != _wlos:
                _any_excluded = True
            if rolling_los_limit is not None:
                if _wjudge <= rolling_los_limit:
                    _status = "✅"
                elif _wjudge <= rolling_los_limit + 0.5:
                    _status = "⚠"
                else:
                    _status = "🔴"
                _rolling_parts.append(f"{_wname}:{_wjudge:.1f}日{_status}")
            else:
                _rolling_parts.append(f"{_wname}:{_wjudge:.1f}日")
        if _rolling_parts:
            if rolling_los_limit is not None:
                _header = f"3M平均在院(基準{rolling_los_limit}日):"
                if _any_excluded:
                    _header = f"3M平均在院※(基準{rolling_los_limit}日):"
                lines.append(_header)
            else:
                lines.append(f"3M平均在院※:" if _any_excluded else f"3M平均在院:")
            lines.append(" / ".join(_rolling_parts))
            if _any_excluded:
                lines.append("※短手3除外後")
    elif rolling_los is not None:
        # 後方互換: 全体の rolling_los が渡された場合
        if rolling_los_limit is not None:
            if rolling_los <= rolling_los_limit:
                _status = "✅"
            elif rolling_los <= rolling_los_limit + 0.5:
                _status = "⚠"
            else:
                _status = "🔴"
            _suffix = f"（{rolling_days}日分）" if rolling_days is not None and rolling_days < 90 else ""
            lines.append(f"3M平均在院:{rolling_los:.1f}日/{rolling_los_limit}日{_status}{_suffix}")
        else:
            lines.append(f"3M平均在院:{rolling_los:.1f}日")

    # 追加コメント
    if notes and notes.strip():
        lines.append("")
        # コメントを行ごとに追加
        for note_line in notes.strip().split("\n"):
            lines.append(note_line)

    # 署名
    lines.append(SIGNATURE)

    message = "\n".join(lines)
    return _trim_to_limit(message)


# ---------------------------------------------------------------------------
# 2. 医師別退院調整依頼メッセージ生成
# ---------------------------------------------------------------------------

def generate_doctor_message(
    target_date,
    doctor_name,
    patients_over_threshold,
    ward_occupancy=None,
    threshold_days=21,
):
    """
    医師別の退院調整依頼メッセージを生成する。

    Parameters
    ----------
    target_date : date
        対象日付
    doctor_name : str
        医師名
    patients_over_threshold : list of dict
        閾値超え患者リスト。各dictに以下のキーを含む:
        - "ward": str  病棟名（例: "6F"）
        - "admission_date": str  入院日（例: "3/15"）
        - "los": int  在院日数
    ward_occupancy : dict, optional
        病棟の稼働率情報。例:
        {"6F": {"rate": 97.9, "vacancy": 1}}
    threshold_days : int
        在院日数の閾値（デフォルト21日）

    Returns
    -------
    str
        400文字以内のメッセージ
    """
    date_str = _format_date_short(target_date)

    lines = [
        f"【退院調整のご相談】{date_str}",
        f"{doctor_name}先生",
        "",
        f"担当患者で在院{threshold_days}日以上の方:",
    ]

    # 患者リスト（個人情報なし: 病棟・入院日・在院日数のみ）
    # 文字数制限のため、多すぎる場合は件数を制限する
    max_patients = len(patients_over_threshold)
    remaining_budget = MAX_CHARS - _count_chars("\n".join(lines)) - 200  # 後続テキスト分を確保
    patient_lines = []
    for p in sorted(patients_over_threshold, key=lambda x: -x["los"]):
        line = f"・{p['ward']} 入院{p['admission_date']} 在院{p['los']}日目"
        if _count_chars("\n".join(patient_lines + [line])) > remaining_budget:
            remaining = max_patients - len(patient_lines)
            if remaining > 0:
                patient_lines.append(f"・他{remaining}名")
            break
        patient_lines.append(line)

    lines.extend(patient_lines)

    # 病棟稼働率の補足
    if ward_occupancy:
        lines.append("")
        for ward_name in sorted(ward_occupancy.keys()):
            info = ward_occupancy[ward_name]
            rate = info.get("rate", 0)
            vacancy = info.get("vacancy", 0)
            if vacancy <= 2:
                lines.append(f"現在{ward_name}稼働率{rate:.1f}%(残{vacancy}床)で")
                lines.append("新規入院の受入が困難な状況です。")
                break
        else:
            # 特に逼迫していない場合の一般的な文面
            ward_summaries = []
            for wn in sorted(ward_occupancy.keys()):
                wi = ward_occupancy[wn]
                ward_summaries.append(f"{wn}:{wi.get('rate', 0):.0f}%")
            lines.append(f"現在の稼働率 {' '.join(ward_summaries)}")

    # 依頼文
    lines.append("")
    lines.append("退院・転院・転棟の見通しがあれば")
    lines.append("お知らせいただけると助かります。")
    lines.append("")
    lines.append("ご多忙のところ恐れ入りますが")
    lines.append("よろしくお願いいたします。")
    lines.append(SIGNATURE)

    message = "\n".join(lines)
    return _trim_to_limit(message)


# ---------------------------------------------------------------------------
# 3. Streamlit UI描画関数
# ---------------------------------------------------------------------------

def render_hope_tab(
    df=None,
    ward_df=None,
    doctor_patients=None,
):
    """
    HOPE送信用サマリータブのUI描画関数。

    Streamlitのタブ内で呼び出し、以下を表示する:
    - 全体サマリーセクション: メッセージプレビュー + コピー用表示
    - 医師別メッセージセクション: 医師選択 → メッセージプレビュー + コピー用表示
    - 文字数カウント（400文字制限）
    - カスタマイズ用の追加コメント入力欄

    Parameters
    ----------
    df : pd.DataFrame, optional
        日次シミュレーション結果（columns: day, patients, admissions, discharges, avg_los等）
    ward_df : pd.DataFrame, optional
        病棟別データ（columns: ward, patients, beds等）
    doctor_patients : dict, optional
        医師別の長期入院患者データ。例:
        {"田中医師": [{"ward": "6F", "admission_date": "3/15", "los": 21}, ...]}
    """
    st.subheader("📨 HOPE送信用サマリー")
    st.caption("富士通HOPE電子カルテ ToDo機能用メッセージ（400文字以内）")

    # ----- 対象日付 -----
    target_date = st.date_input(
        "対象日付",
        value=date.today(),
        key="hope_target_date",
    )

    st.markdown("---")

    # =====================================================================
    # 全体サマリーセクション
    # =====================================================================
    st.markdown("### 全体サマリー（全員向け）")

    # 病棟データの入力UI
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**5F（外科・整形）**")
        patients_5f = st.number_input(
            "5F 入院患者数", min_value=0, max_value=47, value=40,
            key="hope_5f_patients",
        )
    with col2:
        st.markdown("**6F（内科・ペイン）**")
        patients_6f = st.number_input(
            "6F 入院患者数", min_value=0, max_value=47, value=46,
            key="hope_6f_patients",
        )

    col3, col4, col5 = st.columns(3)
    with col3:
        admissions = st.number_input(
            "当日入院数", min_value=0, max_value=30, value=5,
            key="hope_admissions",
        )
    with col4:
        discharges = st.number_input(
            "当日退院数", min_value=0, max_value=30, value=4,
            key="hope_discharges",
        )
    with col5:
        avg_los = st.number_input(
            "平均在院日数（今月集計）", min_value=0.0, max_value=60.0, value=17.8,
            step=0.1, format="%.1f",
            key="hope_avg_los",
        )

    # --- 過去3ヶ月rolling 平均在院日数（病棟別・2026年改定対応） ---
    # ⚠️ 施設基準は各病棟ごとに判定するため、病棟別の rolling LOS を入力する
    st.markdown("**📏 3ヶ月rolling 平均在院日数（各病棟ごと・施設基準判定）**")
    st.caption("⚠️ 地域包括医療病棟の施設基準は、病院全体ではなく各病棟それぞれが満たす必要があります")
    col_rw1, col_rw2, col_rlimit = st.columns(3)
    with col_rw1:
        rolling_5f_input = st.number_input(
            "5F 3ヶ月平均在院日数",
            min_value=0.0, max_value=60.0, value=18.5,
            step=0.1, format="%.1f",
            key="hope_rolling_5f",
            help="5F病棟の過去3ヶ月rolling平均在院日数（通常値）。意思決定ダッシュボードの値と合わせてください。",
        )
    with col_rw2:
        rolling_6f_input = st.number_input(
            "6F 3ヶ月平均在院日数",
            min_value=0.0, max_value=60.0, value=19.2,
            step=0.1, format="%.1f",
            key="hope_rolling_6f",
            help="6F病棟の過去3ヶ月rolling平均在院日数（通常値）。",
        )
    with col_rlimit:
        rolling_limit_input = st.number_input(
            "施設基準上限（日）",
            min_value=15, max_value=25, value=21,
            key="hope_rolling_limit",
            help="2025年度: 21日、2026年度: 20日（85歳以上緩和時 21日）",
        )

    # 短手3除外後の値（2026年改定対応・オプション）
    with st.expander("📝 短手3除外後の値を入力（2026年改定・施設基準判定用）", expanded=False):
        st.caption(
            "2026年改定では、施設基準判定の平均在院日数計算から短手3（大腸ポリペクトミー等）の算定患者を除外します。"
            "意思決定ダッシュボードに表示される「除外後」の値をここに入力してください。"
            "0 のままなら除外なしで通常値を使います。"
        )
        col_ex1, col_ex2 = st.columns(2)
        with col_ex1:
            rolling_5f_ex_input = st.number_input(
                "5F 3ヶ月平均在院日数（短手3除外後）",
                min_value=0.0, max_value=60.0, value=0.0,
                step=0.1, format="%.1f",
                key="hope_rolling_5f_ex",
            )
        with col_ex2:
            rolling_6f_ex_input = st.number_input(
                "6F 3ヶ月平均在院日数（短手3除外後）",
                min_value=0.0, max_value=60.0, value=0.0,
                step=0.1, format="%.1f",
                key="hope_rolling_6f_ex",
            )

    # 追加コメント入力
    notes = st.text_area(
        "追加コメント（状況・対応方針など）",
        placeholder="例:\n6F満床近く入院制限中\n5Fは受入余力あり\n\n▼対応\n長期入院(21日超)の退院調整を推進",
        height=120,
        key="hope_notes",
    )

    # 病棟データ構築
    ward_data = {
        "5F": {"patients": patients_5f, "beds": 47},
        "6F": {"patients": patients_6f, "beds": 47},
    }
    total_beds = 94

    # 病棟別 rolling LOS を構築（短手3除外後の値も含める）
    ward_rolling_los = {}
    if rolling_5f_input > 0:
        _5f_entry = {"los": rolling_5f_input, "days": 90}
        if rolling_5f_ex_input > 0:
            _5f_entry["los_ex_short3"] = rolling_5f_ex_input
        ward_rolling_los["5F"] = _5f_entry
    if rolling_6f_input > 0:
        _6f_entry = {"los": rolling_6f_input, "days": 90}
        if rolling_6f_ex_input > 0:
            _6f_entry["los_ex_short3"] = rolling_6f_ex_input
        ward_rolling_los["6F"] = _6f_entry

    # メッセージ生成
    summary_msg = generate_summary_message(
        target_date=target_date,
        total_beds=total_beds,
        ward_data=ward_data,
        admissions=admissions,
        discharges=discharges,
        avg_los=avg_los,
        notes=notes if notes and notes.strip() else None,
        ward_rolling_los=ward_rolling_los if ward_rolling_los else None,
        rolling_los_limit=rolling_limit_input,
    )

    # プレビュー表示
    char_count = _count_chars(summary_msg)
    if char_count <= MAX_CHARS:
        st.success(f"文字数: {char_count}/{MAX_CHARS}")
    else:
        st.error(f"文字数: {char_count}/{MAX_CHARS} — 制限超過！")

    st.code(summary_msg, language=None)

    st.markdown("---")

    # =====================================================================
    # 医師別メッセージセクション
    # =====================================================================
    st.markdown("### 医師別 退院調整依頼")

    # 医師名入力
    doctor_name = st.text_input(
        "医師名",
        value="",
        placeholder="例: 田中",
        key="hope_doctor_name",
    )

    # 在院日数閾値
    threshold_days = st.number_input(
        "在院日数の閾値（日）",
        min_value=7, max_value=60, value=21,
        key="hope_threshold_days",
    )

    # 担当患者リスト入力UI
    st.markdown("**閾値超え患者リスト**（個人情報なし: 病棟・入院日・在院日数のみ）")

    # セッションステートで患者リストを管理
    if "hope_patient_list" not in st.session_state:
        st.session_state.hope_patient_list = [
            {"ward": "6F", "admission_date": "", "los": 21},
        ]

    patients_list = st.session_state.hope_patient_list

    # 患者リストの編集UI
    updated_patients = []
    for i, p in enumerate(patients_list):
        cols = st.columns([1, 2, 1, 0.5])
        with cols[0]:
            ward = st.selectbox(
                "病棟", ["5F", "6F"], index=0 if p["ward"] == "5F" else 1,
                key=f"hope_pw_{i}",
                label_visibility="collapsed",
            )
        with cols[1]:
            adm_date = st.text_input(
                "入院日", value=p["admission_date"],
                placeholder="例: 3/15",
                key=f"hope_pad_{i}",
                label_visibility="collapsed",
            )
        with cols[2]:
            los = st.number_input(
                "在院日数", min_value=1, max_value=365, value=p["los"],
                key=f"hope_plos_{i}",
                label_visibility="collapsed",
            )
        with cols[3]:
            remove = st.button("✕", key=f"hope_premove_{i}")
            if remove:
                continue
        updated_patients.append({"ward": ward, "admission_date": adm_date, "los": los})

    st.session_state.hope_patient_list = updated_patients

    # 患者追加ボタン
    if st.button("＋ 患者を追加", key="hope_add_patient"):
        st.session_state.hope_patient_list.append(
            {"ward": "6F", "admission_date": "", "los": threshold_days}
        )
        st.rerun()

    # 病棟稼働率情報の構築
    ward_occupancy = {}
    for ward_name, w in ward_data.items():
        rate = w["patients"] / w["beds"] * 100 if w["beds"] > 0 else 0
        vacancy = w["beds"] - w["patients"]
        ward_occupancy[ward_name] = {"rate": rate, "vacancy": vacancy}

    # 有効な患者データのみフィルタ（入院日が入力済みのもの）
    valid_patients = [
        p for p in updated_patients if p["admission_date"].strip()
    ]

    if doctor_name.strip() and valid_patients:
        doctor_msg = generate_doctor_message(
            target_date=target_date,
            doctor_name=doctor_name.strip(),
            patients_over_threshold=valid_patients,
            ward_occupancy=ward_occupancy,
            threshold_days=threshold_days,
        )

        doc_char_count = _count_chars(doctor_msg)
        if doc_char_count <= MAX_CHARS:
            st.success(f"文字数: {doc_char_count}/{MAX_CHARS}")
        else:
            st.error(f"文字数: {doc_char_count}/{MAX_CHARS} — 制限超過！")

        st.code(doctor_msg, language=None)
    elif doctor_name.strip():
        st.info("患者リストの入院日を入力してください。")
    else:
        st.info("医師名を入力するとメッセージが生成されます。")
