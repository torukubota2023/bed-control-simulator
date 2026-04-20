"""設定タブ: HOPE連携・シナリオ保存・CSVエクスポート・救急シード入力。"""

from pathlib import Path

import streamlit as st
import pandas as pd
import yaml


_SEED_YAML_PATH = Path(__file__).resolve().parent.parent.parent / "settings" / "manual_seed_emergency_ratio.yaml"


def render():
    """設定タブを描画する。"""
    sub1, sub2, sub3, sub4 = st.tabs([
        "📨 HOPE連携",
        "💾 シナリオ管理",
        "📤 エクスポート",
        "🩺 救急シード入力",
    ])

    with sub1:
        _render_hope()

    with sub2:
        _render_scenarios()

    with sub3:
        _render_export()

    with sub4:
        _render_emergency_seed()


# ---------------------------------------------------------------------------
# HOPE連携
# ---------------------------------------------------------------------------

def _render_hope():
    """HOPEメッセージ生成。"""
    try:
        from hope_message_generator import render_hope_tab
        render_hope_tab()
    except ImportError:
        st.info("HOPE連携モジュールが見つかりません。")
    except Exception as e:
        st.warning(f"HOPE連携の初期化エラー: {e}")
        st.info("HOPE連携はベッドコントロールデータが読み込まれた状態で使用できます。")


# ---------------------------------------------------------------------------
# シナリオ管理
# ---------------------------------------------------------------------------

def _render_scenarios():
    """シナリオの保存・比較。"""
    try:
        from scenario_manager import (
            save_scenario, list_scenarios, load_scenario, delete_scenario,
        )
    except ImportError:
        st.info("シナリオ管理モジュールが見つかりません。")
        return

    st.markdown("##### 保存済みシナリオ")
    scenarios = list_scenarios()

    if not scenarios:
        st.caption("保存済みシナリオはありません。")
    else:
        for s in scenarios:
            c1, c2 = st.columns([4, 1])
            with c1:
                st.text(f"{s.get('name', '無名')} — {s.get('created_at', '')}")
            with c2:
                if st.button("読込", key=f"load_{s.get('id', '')}"):
                    loaded = load_scenario(s["id"])
                    if loaded:
                        st.success(f"シナリオ「{s['name']}」を読み込みました。")

    st.markdown("---")
    st.markdown("##### 現在の状態を保存")
    scenario_name = st.text_input("シナリオ名", key="scenario_save_name")
    if st.button("保存", key="save_scenario") and scenario_name:
        try:
            save_scenario(scenario_name, st.session_state)
            st.success(f"シナリオ「{scenario_name}」を保存しました。")
        except Exception as e:
            st.error(f"保存エラー: {e}")


# ---------------------------------------------------------------------------
# エクスポート
# ---------------------------------------------------------------------------

def _render_export():
    """データのCSVエクスポート。"""
    st.markdown("##### 現在のデータをCSVでダウンロード")

    # 日次データ
    daily = st.session_state.get("v4_daily_data")
    if daily is not None and len(daily) > 0:
        csv = daily.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📊 日次データ CSV",
            csv,
            "daily_data.csv",
            "text/csv",
        )
    else:
        st.caption("ユーザー入力の日次データがありません（デモデータ使用中）。")

    # 詳細データ
    detail = st.session_state.get("v4_detail_data")
    if detail is not None and len(detail) > 0:
        export_cols = [
            c for c in [
                "date", "ward", "event_type", "route",
                "has_surgery", "admission_tier", "data_version", "los_days",
            ]
            if c in detail.columns
        ]
        csv = detail[export_cols].to_csv(index=False).encode("utf-8")
        st.download_button(
            "📋 入退院詳細 CSV",
            csv,
            "admission_details.csv",
            "text/csv",
        )
    else:
        st.caption("ユーザー入力の入退院詳細データがありません（デモデータ使用中）。")


# ---------------------------------------------------------------------------
# 救急シード入力（rolling 3 ヶ月 bridge）
# ---------------------------------------------------------------------------

def _load_seed_yaml() -> dict:
    """settings/manual_seed_emergency_ratio.yaml を読み込む。"""
    if not _SEED_YAML_PATH.exists():
        return {"seeds": {}}
    try:
        with _SEED_YAML_PATH.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if "seeds" not in data:
            data["seeds"] = {}
        return data
    except Exception as e:
        st.error(f"シードファイル読込エラー: {e}")
        return {"seeds": {}}


def _save_seed_yaml(data: dict) -> bool:
    """シード YAML を保存する。"""
    try:
        with _SEED_YAML_PATH.open("w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
        return True
    except Exception as e:
        st.error(f"シードファイル保存エラー: {e}")
        return False


def _render_emergency_seed():
    """救急搬送後割合の手動シード入力 UI。

    2026-04 以降に実データ入力を開始した直後は rolling 3 ヶ月計算に必要な
    過去月データが足りないため、副院長が電子カルテ・レセプト画面で手集計
    した値を記録する。実データが 3 ヶ月溜まれば自動的に不要化される。
    """
    st.markdown("##### 🩺 救急搬送後割合 — 過去月の手動シード入力")
    st.caption(
        "rolling 3 ヶ月判定（2026-06-01 本則適用）に必要な過去月値を、"
        "副院長が電子カルテ・レセプト画面から手集計して記録するブリッジ機構。"
        "実データが 3 ヶ月蓄積すれば自動的にシードは不使用になる。"
    )

    data = _load_seed_yaml()
    seeds = data.get("seeds", {})

    st.info(
        "**制度上の「救急搬送後」** = 救急車搬送 + 救急患者連携搬送（下り搬送）のみ。"
        "外来紹介・連携室・ウォークインは含めない。"
        "分母は該当月の全入院（短手3 含む、2026-06-01 以降の本則ルール）。"
    )

    # 編集可能な月（先月・先々月のみを想定）
    editable_months = sorted(seeds.keys()) if seeds else ["2026-02", "2026-03"]
    for ym in editable_months:
        st.markdown(f"**{ym}**")
        month_block = seeds.setdefault(ym, {"5F": {"emergency_pct": None, "memo": ""},
                                             "6F": {"emergency_pct": None, "memo": ""}})
        c1, c2 = st.columns(2)
        for ward, col in (("5F", c1), ("6F", c2)):
            ward_block = month_block.setdefault(ward, {"emergency_pct": None, "memo": ""})
            current_val = ward_block.get("emergency_pct")
            with col:
                new_val = st.number_input(
                    f"{ward} 救急搬送後割合 (%)",
                    min_value=0.0,
                    max_value=100.0,
                    value=float(current_val) if current_val is not None else 0.0,
                    step=0.1,
                    format="%.1f",
                    key=f"seed_{ym}_{ward}_pct",
                    help="救急搬送後件数 ÷ 全入院件数 × 100。未入力の場合は 0 のままにしてください。",
                )
                new_memo = st.text_input(
                    f"{ward} メモ（任意）",
                    value=ward_block.get("memo", "") or "",
                    key=f"seed_{ym}_{ward}_memo",
                )
                # 0.0 はシード未入力と区別する必要があるため、チェックボックスで明示
                use_this = st.checkbox(
                    f"{ward} の値をシードとして使用",
                    value=current_val is not None,
                    key=f"seed_{ym}_{ward}_use",
                )
                if use_this:
                    ward_block["emergency_pct"] = float(new_val)
                else:
                    ward_block["emergency_pct"] = None
                ward_block["memo"] = new_memo
        st.markdown("")

    st.markdown("---")
    editor_name = st.text_input(
        "記録者名", value=data.get("updated_by", "副院長 久保田徹"), key="seed_updated_by"
    )
    source_note = st.text_input(
        "集計ソース", value=data.get("source", "電子カルテ + レセプト"),
        key="seed_source",
        help="例: 電子カルテの入院一覧 + レセプトの救急医療管理加算算定件数",
    )

    if st.button("💾 シード値を保存", key="save_seed_yaml"):
        from datetime import date as _date
        data["updated_at"] = str(_date.today())
        data["updated_by"] = editor_name
        data["source"] = source_note
        data["seeds"] = seeds
        if _save_seed_yaml(data):
            st.success("シード値を保存しました。次回の rolling 3 ヶ月計算に反映されます。")

    # 現在の状態サマリー
    st.markdown("---")
    st.markdown("##### 現在のシード値サマリー")
    summary_rows = []
    for ym, ward_map in sorted(seeds.items()):
        for ward in ("5F", "6F"):
            pct = (ward_map or {}).get(ward, {}).get("emergency_pct")
            summary_rows.append({
                "年月": ym,
                "病棟": ward,
                "救急搬送後 (%)": f"{pct:.1f}" if pct is not None else "（未入力）",
                "メモ": (ward_map or {}).get(ward, {}).get("memo", "") or "",
            })
    if summary_rows:
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)
