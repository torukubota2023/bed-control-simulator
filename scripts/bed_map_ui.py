"""
病床マップUI モジュール

おもろまちメディカルセンターの病棟フロアプランを視覚的に表示し、
各ベッドの在院日数を初期入力するための Streamlit コンポーネント。

個人情報は一切含めない（在院日数の集計値のみ）。
"""

from __future__ import annotations

import streamlit as st
import pandas as pd

from bed_data_manager import (
    ROOM_LAYOUT_5F,
    ROOM_LAYOUT_6F,
    ROOM_TYPES_5F,
    ROOM_TYPES_6F,
    WARD_CONFIG,
    DAY_BUCKET_KEYS,
)

# ---------------------------------------------------------------------------
# CSS スタイル定義（コンパクトレイアウト用）
# ---------------------------------------------------------------------------

_CSS = """
<style>
/* コンパクトな number_input */
div[data-testid="stNumberInput"] {
    margin-bottom: 0.1rem;
}
div[data-testid="stNumberInput"] label {
    font-size: 0.75rem;
    margin-bottom: 0;
}
div[data-testid="stNumberInput"] input {
    padding: 0.2rem 0.4rem;
    font-size: 0.8rem;
    height: 1.8rem;
}

/* 部屋コンテナのスタイル */
.room-container {
    border: 1px solid #ddd;
    border-radius: 6px;
    padding: 4px 6px;
    margin: 2px 0;
    min-height: 50px;
}
.room-header {
    font-size: 0.75rem;
    font-weight: bold;
    margin-bottom: 2px;
    padding: 1px 4px;
    border-radius: 3px;
}
.room-tokushitsu { background-color: #fff3cd; }
.room-koshitsu { background-color: #d1ecf1; }
.room-4bed { background-color: #d4edda; }
.room-2bed { background-color: #e2d9f3; }
.room-storage { background-color: #e2e3e5; color: #6c757d; }

/* メトリクスを小さく */
div[data-testid="stMetric"] {
    padding: 0.3rem 0;
}

/* ゾーンヘッダー */
.zone-label {
    font-size: 0.8rem;
    font-weight: bold;
    color: #555;
    border-bottom: 1px solid #ccc;
    margin-bottom: 4px;
    padding-bottom: 2px;
}
</style>
"""

# ---------------------------------------------------------------------------
# 部屋タイプ → CSS クラス マッピング
# ---------------------------------------------------------------------------

_TYPE_CSS = {
    "特室": "room-tokushitsu",
    "個室": "room-koshitsu",
    "4人部屋": "room-4bed",
    "2人部屋": "room-2bed",
    "倉庫": "room-storage",
}

# ---------------------------------------------------------------------------
# 表示グループ定義（コンパクトレイアウト用の行構成）
# ---------------------------------------------------------------------------

# 6F の表示グループ（部屋番号リスト）
_DISPLAY_ROWS_6F = [
    # Row 1: 個室ゾーン
    ["602", "603", "605", "606", "607", "608", "610"],
    # Row 2: 特室 + 個室
    ["612", "613", "615", "616", "617", "628", "630"],
    # Row 3: 4人部屋（前半）
    ["601", "618", "620", "621", "622", "623"],
    # Row 4: 4人部屋（後半）+ 2人部屋
    ["625", "626", "627", "631"],
]

_ROW_LABELS = [
    "個室ゾーン",
    "特室・個室ゾーン",
    "多床室ゾーン A",
    "多床室ゾーン B",
]


def _get_display_rows(ward: str) -> list[list[str]]:
    """病棟に応じた表示行リストを返す。"""
    if ward == "6F":
        return _DISPLAY_ROWS_6F
    # 5F: 番号を 5xx に変換。611(倉庫)→511(個室) の違いを反映
    rows = []
    for row in _DISPLAY_ROWS_6F:
        new_row = []
        for room in row:
            room_5f = f"5{room[1:]}"
            # 611(倉庫)は6Fのみ。5Fでは511(個室)として含める
            if room == "611":
                continue
            new_row.append(room_5f)
        rows.append(new_row)
    # 511を個室ゾーン（Row 1）の末尾に追加
    rows[0].append("511")
    return rows


# ---------------------------------------------------------------------------
# 部屋レンダリング
# ---------------------------------------------------------------------------

def render_room(room_num: str, num_beds: int, room_type: str, ward: str) -> dict:
    """
    単一の部屋をレンダリングし、各ベッドの在院日数を返す。

    Args:
        room_num: 部屋番号 (例: "601")
        num_beds: ベッド数
        room_type: 部屋タイプ (特室/個室/4人部屋/2人部屋/倉庫)
        ward: 病棟 ("5F" or "6F")

    Returns:
        dict: {bed_id: los} 形式。bed_id は "601_1" のような文字列。
    """
    bed_data: dict[str, int] = {}
    css_class = _TYPE_CSS.get(room_type, "room-koshitsu")

    # 倉庫の場合は表示のみ
    if room_type == "倉庫" or num_beds == 0:
        st.markdown(
            f'<div class="room-header {css_class}">'
            f"{room_num} (倉庫)</div>",
            unsafe_allow_html=True,
        )
        return bed_data

    # 部屋ヘッダー
    type_label = f"{num_beds}人" if num_beds > 1 else room_type
    st.markdown(
        f'<div class="room-header {css_class}">'
        f"{room_num} ({type_label})</div>",
        unsafe_allow_html=True,
    )

    # ベッド入力
    if num_beds == 1:
        key = f"bed_{ward}_{room_num}_1"
        val = st.number_input(
            "日数",
            min_value=0,
            max_value=365,
            value=st.session_state.get(key, 0),
            key=key,
            label_visibility="collapsed",
        )
        bed_data[f"{room_num}_1"] = val
    else:
        cols = st.columns(num_beds)
        for i, col in enumerate(cols, start=1):
            key = f"bed_{ward}_{room_num}_{i}"
            with col:
                val = col.number_input(
                    f"#{i}",
                    min_value=0,
                    max_value=365,
                    value=st.session_state.get(key, 0),
                    key=key,
                    label_visibility="collapsed",
                )
                bed_data[f"{room_num}_{i}"] = val

    return bed_data


# ---------------------------------------------------------------------------
# メインレンダリング
# ---------------------------------------------------------------------------

def render_bed_map(ward: str) -> dict:
    """
    病棟のベッドマップをレンダリングし、全ベッドの在院日数データを返す。

    Args:
        ward: "5F" or "6F"

    Returns:
        dict: {"room_bed" (例: "601_1"): LOS日数 (int, 0=空床)} の辞書
    """
    # CSS 注入
    st.markdown(_CSS, unsafe_allow_html=True)

    # 病棟データ取得
    if ward == "5F":
        rooms = ROOM_LAYOUT_5F
        room_types = ROOM_TYPES_5F
    else:
        rooms = ROOM_LAYOUT_6F
        room_types = ROOM_TYPES_6F

    bed_data: dict[str, int] = {}

    # ヘッダー行: タイトル + クリアボタン
    hdr_col1, hdr_col2 = st.columns([4, 1])
    with hdr_col1:
        st.markdown(f"#### {ward} 病床マップ")
    with hdr_col2:
        if st.button("全てクリア", key=f"clear_all_{ward}", type="secondary"):
            for room_num, num_beds in rooms.items():
                for i in range(1, num_beds + 1):
                    key = f"bed_{ward}_{room_num}_{i}"
                    st.session_state[key] = 0
            st.rerun()

    # 凡例
    st.markdown(
        '<span style="font-size:0.7rem;">'
        '<span style="background:#d1ecf1;padding:1px 6px;border-radius:3px;">個室</span> '
        '<span style="background:#fff3cd;padding:1px 6px;border-radius:3px;">特室</span> '
        '<span style="background:#d4edda;padding:1px 6px;border-radius:3px;">4人部屋</span> '
        '<span style="background:#e2d9f3;padding:1px 6px;border-radius:3px;">2人部屋</span> '
        '<span style="background:#e2e3e5;padding:1px 6px;border-radius:3px;color:#6c757d;">倉庫</span> '
        "| 数値 = 在院日数（0 = 空床）"
        "</span>",
        unsafe_allow_html=True,
    )

    # 行ごとにレンダリング
    display_rows = _get_display_rows(ward)
    for row_idx, row_rooms in enumerate(display_rows):
        st.markdown(
            f'<div class="zone-label">{_ROW_LABELS[row_idx]}</div>',
            unsafe_allow_html=True,
        )
        cols = st.columns(len(row_rooms))
        for col, room_num in zip(cols, row_rooms):
            with col:
                num_beds = rooms.get(room_num, 0)
                room_type = room_types.get(room_num, "個室")
                room_data = render_room(room_num, num_beds, room_type, ward)
                bed_data.update(room_data)

    # サマリー行（リアルタイム）
    occupied = sum(1 for v in bed_data.values() if v > 0)
    licensed = WARD_CONFIG[ward]["beds"]
    empty = licensed - occupied
    los_values = [v for v in bed_data.values() if v > 0]
    avg_los = sum(los_values) / len(los_values) if los_values else 0.0

    st.divider()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("入院患者数", f"{occupied}名")
    m2.metric("空床数", f"{empty}床")
    m3.metric("稼働率", f"{occupied / licensed * 100:.1f}%")
    m4.metric("平均在院日数", f"{avg_los:.1f}日")

    return bed_data


# ---------------------------------------------------------------------------
# 確認画面
# ---------------------------------------------------------------------------

def render_confirmation(ward: str, bed_data: dict, rooms: dict) -> bool:
    """
    入力内容の確認画面を表示する。

    Args:
        ward: "5F" or "6F"
        bed_data: render_bed_map() の戻り値
        rooms: ROOM_LAYOUT_5F or ROOM_LAYOUT_6F

    Returns:
        True: ユーザーが確定ボタンを押した場合
    """
    occupied = sum(1 for v in bed_data.values() if v > 0)
    total_los = [v for v in bed_data.values() if v > 0]
    licensed = WARD_CONFIG[ward]["beds"]

    st.markdown(f"### {ward} 初期データ確認")

    col1, col2, col3 = st.columns(3)
    col1.metric("入院患者数", f"{occupied}名")
    col2.metric("空床数", f"{licensed - occupied}床")
    if total_los:
        col3.metric("平均在院日数", f"{sum(total_los) / len(total_los):.1f}日")
    else:
        col3.metric("平均在院日数", "---")

    # A/B/C 群の内訳
    a_count = sum(1 for v in total_los if 1 <= v <= 5)
    b_count = sum(1 for v in total_los if 6 <= v <= 14)
    c_count = sum(1 for v in total_los if v >= 15)

    st.markdown(
        f"**A群（1-5日目）**: {a_count}名 / "
        f"**B群（6-14日目）**: {b_count}名 / "
        f"**C群（15日目以上）**: {c_count}名"
    )

    # 稼働率バー
    occupancy_pct = occupied / licensed * 100 if licensed > 0 else 0
    st.progress(min(occupancy_pct / 100, 1.0), text=f"稼働率 {occupancy_pct:.1f}%")

    # 入院患者の詳細テーブル
    occupied_beds = {k: v for k, v in bed_data.items() if v > 0}
    if occupied_beds:
        df = pd.DataFrame(
            [
                {
                    "部屋": k.split("_")[0] + "号室",
                    "ベッド": k.split("_")[1],
                    "在院日数": v,
                    "群": "A" if v <= 5 else ("B" if v <= 14 else "C"),
                }
                for k, v in sorted(occupied_beds.items())
            ]
        )
        st.dataframe(df, hide_index=True, height=200)
    else:
        st.info("入院患者データがありません。")

    return st.button(
        "この内容で確定する",
        type="primary",
        key=f"confirm_{ward}",
    )


# ---------------------------------------------------------------------------
# ベッドデータ → 日齢バケット変換
# ---------------------------------------------------------------------------

def bed_data_to_buckets(bed_data: dict) -> dict:
    """
    ベッドマップデータ（room_bed -> LOS）を日齢バケット形式に変換する。

    Args:
        bed_data: {"room_bed": los_days} の辞書

    Returns:
        dict: {day_1: count, day_2: count, ..., day_14: count, day_15plus: count}
    """
    buckets = {k: 0 for k in DAY_BUCKET_KEYS}
    for _bed_id, los in bed_data.items():
        if los <= 0:
            continue
        if los <= 14:
            buckets[f"day_{los}"] += 1
        else:
            buckets["day_15plus"] += 1
    return buckets
