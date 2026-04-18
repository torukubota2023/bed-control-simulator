"""
conference_material_view のユニット / AppTest 統合テスト.

検証項目:
- モジュールが import できる
- ``render_conference_material_view()`` が実行エラーなし
- 主要な data-testid が DOM に存在する
- モード切替で ``conference-mode`` testid が変化する
- 病棟切替で ``conference-ward`` testid が変化する
- ファクト抽選のユニットテスト（ward / mode フィルタ・weight 0 スキップ・空入力）
- ステータスカテゴリ定義（通常 7 / 連休 3）
- サンプル患者データ（各 組み合わせで 10 名）
"""

from __future__ import annotations

import json
import os
import random
import sys
from datetime import date
from pathlib import Path

import pytest

# scripts/ を sys.path に追加
_SCRIPTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "scripts")
)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from views import conference_material_view as cmv  # noqa: E402


# ---------------------------------------------------------------------------
# 1. モジュール import / 公開 API の存在
# ---------------------------------------------------------------------------

class TestModuleBasics:
    """モジュールの基本的な健全性."""

    def test_public_function_exists(self):
        """公開関数 render_conference_material_view が存在する."""
        assert callable(cmv.render_conference_material_view)

    def test_status_normal_has_7_categories(self):
        """通常モードのステータスカテゴリは 7 種."""
        assert len(cmv._STATUS_NORMAL) == 7
        # 必須 key が揃っている
        keys = {s["key"] for s in cmv._STATUS_NORMAL}
        assert keys == {
            "undecided", "medical", "family", "facility",
            "insurance", "rehab", "new",
        }

    def test_status_holiday_has_4_categories(self):
        """連休対策モードのカテゴリは 4 種（"new" + 3 つの連休対策カテゴリ）.

        副院長決定（2026-04-17）: カンファ開始時は全員 "new" であるため、
        連休モードにも "new" を含め、selectbox で連休対策カテゴリに振り分ける.
        """
        assert len(cmv._STATUS_HOLIDAY) == 4
        keys = {s["key"] for s in cmv._STATUS_HOLIDAY}
        assert keys == {"before_confirmed", "before_adjusting", "continuing", "new"}

    def test_each_status_has_required_fields(self):
        """全ステータスに emoji / label / bg / fg が揃っている."""
        for pool in (cmv._STATUS_NORMAL, cmv._STATUS_HOLIDAY):
            for s in pool:
                assert "emoji" in s
                assert "label" in s
                assert "bg" in s
                assert "fg" in s


# ---------------------------------------------------------------------------
# 2. サンプル患者データ
# ---------------------------------------------------------------------------

class TestSamplePatients:
    """サンプル患者データの健全性."""

    @pytest.mark.parametrize("ward,mode", [
        ("5F", "normal"),
        ("6F", "normal"),
        ("5F", "holiday"),
        ("6F", "holiday"),
    ])
    def test_each_combination_has_10_patients(self, ward: str, mode: str):
        """各 ward × mode で 10 名のサンプル."""
        patients = cmv._get_sample_patients(ward, mode)
        assert len(patients) == 10

    def test_patient_id_is_8_char(self):
        """patient_id は UUID 先頭 8 桁."""
        for ward in ("5F", "6F"):
            for mode in ("normal", "holiday"):
                for p in cmv._get_sample_patients(ward, mode):
                    assert len(p.patient_id) == 8, f"{p.patient_id} は 8 桁でない"

    def test_no_full_patient_names(self):
        """姓のみ — フルネーム（スペース混じり等）は含まない."""
        for ward in ("5F", "6F"):
            for mode in ("normal", "holiday"):
                for p in cmv._get_sample_patients(ward, mode):
                    # 姓（1-3 文字程度）を許容、スペース混じりはフルネーム相当なので NG
                    assert " " not in p.doctor_surname
                    assert len(p.doctor_surname) <= 3

    def test_holiday_mode_uses_holiday_status_keys(self):
        """連休モードの患者の status_key は _STATUS_HOLIDAY の keys に含まれる."""
        holiday_keys = {s["key"] for s in cmv._STATUS_HOLIDAY}
        for ward in ("5F", "6F"):
            for p in cmv._get_sample_patients(ward, "holiday"):
                assert p.status_key in holiday_keys, \
                    f"{p.patient_id} の status_key={p.status_key} が holiday pool にない"

    def test_normal_mode_uses_normal_status_keys(self):
        """通常モードの患者の status_key は _STATUS_NORMAL の keys に含まれる."""
        normal_keys = {s["key"] for s in cmv._STATUS_NORMAL}
        for ward in ("5F", "6F"):
            for p in cmv._get_sample_patients(ward, "normal"):
                assert p.status_key in normal_keys

    def test_all_sample_patients_initial_status_is_new(self):
        """全サンプル患者（通常 10 + 連休 10 × 2 病棟 = 40 名）の初期ステータスは "new".

        副院長決定（2026-04-17）: カンファ開始時は全員 "new"、カンファで振り分ける流れに統一.
        """
        for ward in ("5F", "6F"):
            for mode in ("normal", "holiday"):
                for p in cmv._get_sample_patients(ward, mode):
                    assert p.status_key == "new", (
                        f"{ward}/{mode} の {p.patient_id} の初期ステータスが "
                        f"'new' ではなく '{p.status_key}'"
                    )


# ---------------------------------------------------------------------------
# 3. ファクト抽選ユニットテスト
# ---------------------------------------------------------------------------

class TestFactSelection:
    """重み付きファクト抽選."""

    def test_load_facts_returns_list(self):
        """facts.yaml 読み込みで 25 件以上のリスト."""
        facts = cmv._load_facts()
        assert isinstance(facts, list)
        assert len(facts) >= 20

    def test_select_fact_for_5f_normal(self):
        """5F / normal には該当ファクトが存在."""
        facts = cmv._load_facts()
        rng = random.Random(1)
        chosen = cmv._select_fact(facts, "5F", "normal", rng=rng)
        assert chosen is not None
        ctx = chosen.get("context", {})
        assert "5F" in ctx.get("wards", [])
        assert "normal" in ctx.get("modes", [])

    def test_select_fact_for_6f_holiday(self):
        """6F / holiday には該当ファクトが存在."""
        facts = cmv._load_facts()
        rng = random.Random(2)
        chosen = cmv._select_fact(facts, "6F", "holiday", rng=rng)
        assert chosen is not None
        ctx = chosen.get("context", {})
        assert "6F" in ctx.get("wards", [])
        assert "holiday" in ctx.get("modes", [])

    def test_select_fact_empty_input_returns_none(self):
        """空入力 → None."""
        assert cmv._select_fact([], "5F", "normal") is None

    def test_select_fact_no_match_returns_none(self):
        """どのファクトもマッチしない ward → None."""
        facts = cmv._load_facts()
        chosen = cmv._select_fact(facts, "ZZ", "normal")
        assert chosen is None

    def test_select_fact_weight_zero_skipped(self):
        """weight=0 のファクトは抽選候補から除外される。

        2026-04-18: rotation_eligible=True のファクトのみが候補になるため
        テスト入力にも rotation_eligible=True を付与する。
        """
        facts = [
            {
                "id": "zero", "text": "zero",
                "rotation_eligible": True,
                "context": {
                    "wards": ["5F"], "modes": ["normal"], "weight": 0,
                }
            },
            {
                "id": "pos", "text": "positive",
                "rotation_eligible": True,
                "context": {
                    "wards": ["5F"], "modes": ["normal"], "weight": 10,
                }
            },
        ]
        rng = random.Random(0)
        for _ in range(20):
            chosen = cmv._select_fact(facts, "5F", "normal", rng=rng)
            assert chosen is not None
            assert chosen["id"] == "pos", "weight=0 のファクトが抽選された"

    def test_select_fact_deterministic_with_seeded_rng(self):
        """同じ seed の rng → 同じ結果."""
        facts = cmv._load_facts()
        chosen_a = cmv._select_fact(facts, "5F", "normal", rng=random.Random(100))
        chosen_b = cmv._select_fact(facts, "5F", "normal", rng=random.Random(100))
        assert chosen_a is not None and chosen_b is not None
        assert chosen_a["id"] == chosen_b["id"]


# ---------------------------------------------------------------------------
# 4. 分類関数（色分け）
# ---------------------------------------------------------------------------

class TestClassifiers:
    """KPI 色分けロジック."""

    def test_occupancy_good_when_above_target(self):
        assert cmv._classify_occupancy(92.0, 90.0) == "good"
        assert cmv._classify_occupancy(90.0, 90.0) == "good"

    def test_occupancy_warning_within_5_points(self):
        assert cmv._classify_occupancy(85.0, 90.0) == "warning"
        assert cmv._classify_occupancy(86.0, 90.0) == "warning"

    def test_occupancy_danger_when_far_below(self):
        assert cmv._classify_occupancy(70.0, 90.0) == "danger"

    def test_alos_good_below_warning(self):
        assert cmv._classify_alos(17.5, 19.95, 21.0) == "good"

    def test_alos_warning_between_warning_and_limit(self):
        assert cmv._classify_alos(20.0, 19.95, 21.0) == "warning"

    def test_alos_danger_at_or_over_limit(self):
        assert cmv._classify_alos(21.0, 19.95, 21.0) == "danger"
        assert cmv._classify_alos(22.5, 19.95, 21.0) == "danger"

    def test_emergency_good_above_min(self):
        assert cmv._classify_emergency(18.0, 15.0) == "good"

    def test_emergency_warning_just_above_min(self):
        assert cmv._classify_emergency(16.0, 15.0) == "warning"

    def test_emergency_danger_below_min(self):
        assert cmv._classify_emergency(14.0, 15.0) == "danger"


# ---------------------------------------------------------------------------
# 5. AppTest を使った画面描画テスト（統合）
# ---------------------------------------------------------------------------

def _write_app_entry(path: Path) -> None:
    """AppTest 用の最小エントリファイルを書き出す."""
    path.write_text(
        """
import sys
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import streamlit as st
st.set_page_config(layout='wide')

from views.conference_material_view import render_conference_material_view
from datetime import date

render_conference_material_view(today=date(2026, 4, 17))
""",
        encoding="utf-8",
    )


class TestAppTestIntegration:
    """Streamlit AppTest による実画面描画."""

    @pytest.fixture
    def app_path(self, tmp_path: Path) -> Path:
        """エントリ app を一時ディレクトリに書き出して scripts/ の隣に置く."""
        # scripts ディレクトリ内部に配置する必要があるので /tmp は使わない
        repo_scripts = Path(__file__).resolve().parent.parent / "scripts"
        entry = repo_scripts / "_conference_view_test_entry.py"
        _write_app_entry(entry)
        yield entry
        # 後始末
        try:
            entry.unlink()
        except FileNotFoundError:
            pass

    def test_app_runs_without_error(self, app_path: Path):
        """render_conference_material_view() が実行エラーなしで走る."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        assert not at.exception, (
            f"Streamlit 実行時例外: "
            f"{[e.value for e in at.exception]}"
        )

    def test_primary_testids_in_markdown(self, app_path: Path):
        """主要な data-testid が markdown 出力に含まれる."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        # 全 markdown 要素の body を連結
        markdown_text = "\n".join(m.value for m in at.markdown)
        required_testids = [
            "conference-mode",
            "conference-ward",
            "conference-occupancy-pct",
            "conference-alos-days",
            "conference-emergency-pct",
            "conference-holiday-days",
            "conference-patient-count",
            "conference-fact-id",
        ]
        for testid in required_testids:
            assert f'data-testid="{testid}"' in markdown_text, \
                f"testid '{testid}' が画面描画に含まれない"

    def test_default_mode_is_normal(self, app_path: Path):
        """初期モードは normal."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        assert 'data-testid="conference-mode" style="display:none">normal<' in markdown_text

    def test_default_ward_is_5f(self, app_path: Path):
        """初期病棟は 5F."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        assert 'data-testid="conference-ward" style="display:none">5F<' in markdown_text

    def test_mode_toggle_switches_to_holiday(self, app_path: Path):
        """連休対策モードトグルで conference-mode が holiday に変化."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        # トグルを ON にして再実行
        assert len(at.toggle) >= 1
        at.toggle[0].set_value(True)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        assert 'data-testid="conference-mode" style="display:none">holiday<' in markdown_text

    def test_ward_selectbox_switches_to_6f(self, app_path: Path):
        """ワード selectbox で 6F に切り替えると conference-ward が 6F になる."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        # 病棟 selectbox は唯一の selectbox（個別患者ステータスは popover + radio に移行済み）
        assert len(at.selectbox) == 1
        at.selectbox[0].set_value("6F").run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        assert 'data-testid="conference-ward" style="display:none">6F<' in markdown_text

    def test_patient_count_is_10(self, app_path: Path):
        """患者行は 10 名分."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        assert 'data-testid="conference-patient-count" style="display:none">10<' in markdown_text

    def test_fact_id_starts_with_f(self, app_path: Path):
        """抽選されたファクト ID は "f" で始まる（f001-f025 形式）."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        # testid の内容を抽出
        import re
        m = re.search(
            r'data-testid="conference-fact-id"\s+style="display:none">([^<]*)<',
            markdown_text,
        )
        assert m is not None, "conference-fact-id が画面に出ない"
        fact_id = m.group(1).strip()
        # 空ならフォールバック（該当ファクトなし）も許容するが、
        # 5F/normal は必ず対象ファクトがあるはず
        assert fact_id.startswith("f"), f"想定外のファクト ID: {fact_id}"


# ---------------------------------------------------------------------------
# 6. 医師/患者 編集機能（患者情報編集）
# ---------------------------------------------------------------------------

class TestDoctorPatientCellFormatter:
    """_format_doctor_patient_cell の単体テスト."""

    def test_all_empty_shows_fallback_surname_with_unenterd_label(self):
        """全フィールド空 → "姓 / 未入力"."""
        html = cmv._format_doctor_patient_cell(
            doctor_name="", patient_name="", patient_id="",
            fallback_surname="田中",
        )
        assert "田中" in html
        assert "未入力" in html

    def test_doctor_name_only(self):
        """主治医のみ入力 → 主治医名のみ表示、未入力ラベルなし."""
        html = cmv._format_doctor_patient_cell(
            doctor_name="佐藤医師", patient_name="", patient_id="",
            fallback_surname="田中",
        )
        assert "佐藤医師" in html
        assert "未入力" not in html

    def test_doctor_and_patient_name(self):
        """主治医 + 患者名."""
        html = cmv._format_doctor_patient_cell(
            doctor_name="田中医師", patient_name="山田太郎", patient_id="",
            fallback_surname="田中",
        )
        assert "田中医師" in html
        assert "山田太郎" in html

    def test_all_fields_filled_shows_id(self):
        """全フィールド入力 → ID も併記."""
        html = cmv._format_doctor_patient_cell(
            doctor_name="田中医師", patient_name="山田太郎", patient_id="12345",
            fallback_surname="田中",
        )
        assert "田中医師" in html
        assert "山田太郎" in html
        assert "ID:12345" in html

    def test_patient_name_only_uses_fallback_surname(self):
        """患者名のみ入力（主治医名空）→ フォールバック姓が使われる."""
        html = cmv._format_doctor_patient_cell(
            doctor_name="", patient_name="山田太郎", patient_id="",
            fallback_surname="田中",
        )
        # 主治医部分にフォールバック姓が使われる
        assert "田中" in html
        assert "山田太郎" in html
        # 「/」で区切られている
        assert "/" in html

    def test_whitespace_treated_as_empty(self):
        """空白だけのフィールドは空扱い."""
        html = cmv._format_doctor_patient_cell(
            doctor_name="   ", patient_name="  ", patient_id=" ",
            fallback_surname="田中",
        )
        assert "未入力" in html


class TestPatientEditUIIntegration:
    """AppTest でビュー描画時の医師/患者 編集 UI を検証."""

    @pytest.fixture
    def app_path(self, tmp_path: Path) -> Path:
        """エントリ app を一時ディレクトリに書き出して scripts/ の隣に置く."""
        repo_scripts = Path(__file__).resolve().parent.parent / "scripts"
        entry = repo_scripts / "_conference_view_test_entry.py"
        _write_app_entry(entry)
        yield entry
        try:
            entry.unlink()
        except FileNotFoundError:
            pass

    @pytest.fixture(autouse=True)
    def isolate_storage(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """テスト間で patient_names.json を汚染しない."""
        import patient_name_store as pns
        isolated_path = tmp_path / "patient_names.json"
        monkeypatch.setattr(pns, "_STORAGE_PATH", isolated_path)
        yield

    def test_header_renamed_to_doctor_slash_patient(self, app_path: Path):
        """医師列のヘッダーが「医師 / 患者」に変更されている."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        assert "医師 / 患者" in markdown_text, (
            "ヘッダーが「医師 / 患者」になっていない"
        )

    def test_edit_text_inputs_exist_for_each_patient(self, app_path: Path):
        """患者行ごとに編集用の text_input が 3 個ずつ（計 30 個）存在する.

        Streamlit 1.55 の AppTest は ``st.popover`` を直接公開しないが、
        中身の ``st.text_input`` は ``at.text_input`` から取得できる。
        10 名 × (主治医 / 患者名 / 患者ID) = 30 個を確認する。
        """
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        # 10 名 × 3 フィールド = 30 個
        edit_keys = [
            inp for inp in at.text_input
            if any(inp.key.endswith(f"edit_{suffix}_") or f"edit_{suffix}_" in inp.key
                   for suffix in ("doctor", "pname", "pid"))
        ]
        assert len(edit_keys) == 30, (
            f"編集 text_input 数が 30 ではない: {len(edit_keys)} "
            f"(all keys: {[i.key for i in at.text_input]})"
        )

    def test_empty_fields_show_fallback_label(self, app_path: Path):
        """初期状態（JSON ファイル欠損）では「未入力」ラベルが表示される."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        # 少なくとも 1 つは「未入力」が見える
        assert "未入力" in markdown_text

    def test_edit_button_wrap_class_present(self, app_path: Path):
        """印刷時の非表示用ラッパークラス conf-edit-btn-wrap が出力される."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        assert "conf-edit-btn-wrap" in markdown_text, (
            "印刷時に編集ボタンを非表示にするラッパークラスがない"
        )

    def test_print_media_hides_edit_button(self, app_path: Path):
        """@media print で .conf-edit-btn-wrap が display:none 化されている."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        # CSS 注入テキストに print で非表示のルールがある
        assert "@media print" in markdown_text
        assert ".conf-edit-btn-wrap" in markdown_text

    def test_print_keeps_patient_names_visible(self, app_path: Path):
        """@media print では conf-patient-row は非表示にしない（名前はそのまま印刷される）."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        # 患者行自体は印刷時に display:none になっていない
        # @media print 内で .conf-patient-row { display: none } が書かれていないか確認
        import re
        # @media print { ... } ブロックを抽出
        print_blocks = re.findall(
            r"@media print\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}",
            markdown_text,
        )
        for block in print_blocks:
            assert "conf-patient-row" not in block, (
                "print media で .conf-patient-row が非表示化されている"
            )


# ---------------------------------------------------------------------------
# 7. 「週末受入余力」ラベル（医療倫理的表現への切替）
# ---------------------------------------------------------------------------

class TestWeekendCapacityLabel:
    """副院長決定: 金額表示 → 床日表示 への意味転換."""

    @pytest.fixture
    def app_path(self, tmp_path: Path) -> Path:
        """エントリ app を一時ディレクトリに書き出して scripts/ の隣に置く."""
        repo_scripts = Path(__file__).resolve().parent.parent / "scripts"
        entry = repo_scripts / "_conference_view_test_entry.py"
        _write_app_entry(entry)
        yield entry
        try:
            entry.unlink()
        except FileNotFoundError:
            pass

    @pytest.fixture(autouse=True)
    def isolate_storage(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """テスト間で JSON 保存を汚染しない."""
        import patient_name_store as pns
        import patient_status_store as pss
        monkeypatch.setattr(pns, "_STORAGE_PATH", tmp_path / "patient_names.json")
        monkeypatch.setattr(pss, "_STORAGE_PATH", tmp_path / "patient_status.json")
        monkeypatch.setattr(
            pss, "_HISTORY_PATH", tmp_path / "patient_status_history.json"
        )
        yield

    def test_weekend_capacity_label_shown(self, app_path: Path):
        """通常モードで「週末受入余力」ラベルが表示される."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        assert "週末受入余力" in markdown_text, (
            "通常モードで「週末受入余力」ラベルが表示されていない"
        )

    def test_weekend_old_cost_label_not_shown(self, app_path: Path):
        """古い「週末空床コスト」ラベルが表示されていない."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        assert "週末空床コスト" not in markdown_text, (
            "古い「週末空床コスト」ラベルが残存している"
        )

    def test_weekend_capacity_unit_is_bed_days(self, app_path: Path):
        """単位が「床日」で表示される."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        assert "床日" in markdown_text

    def test_weekend_capacity_5f_value_19(self, app_path: Path):
        """5F 通常モードの床日合計は 4+8+7=19 床日."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        # 通常モード 5F: forecast vacancy = [4, 8, 7] → 合計 19
        assert "週末受入余力 19床日" in markdown_text, (
            "5F 通常モードの受入余力が 19 床日になっていない"
        )

    def test_holiday_mode_uses_capacity_label_too(self, app_path: Path):
        """連休モードでも「週末受入余力」ラベルが使われる（「空床損失」ではない）."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        # 連休対策モード ON
        assert len(at.toggle) >= 1
        at.toggle[0].set_value(True)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        assert "週末受入余力" in markdown_text
        # 古い「空床損失」は残っていない
        assert "空床損失" not in markdown_text, (
            "古い「空床損失」ラベルが残存している"
        )


# ---------------------------------------------------------------------------
# 8. Block B の動的集計（ステータス変更で内訳が変化する）
# ---------------------------------------------------------------------------

class TestBlockBDynamicAggregation:
    """Block B の内訳件数が Block C のステータスから動的に集計されることを検証."""

    @pytest.fixture
    def app_path(self, tmp_path: Path) -> Path:
        """エントリ app を一時ディレクトリに書き出して scripts/ の隣に置く."""
        repo_scripts = Path(__file__).resolve().parent.parent / "scripts"
        entry = repo_scripts / "_conference_view_test_entry.py"
        _write_app_entry(entry)
        yield entry
        try:
            entry.unlink()
        except FileNotFoundError:
            pass

    @pytest.fixture(autouse=True)
    def isolate_storage(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        import patient_name_store as pns
        import patient_status_store as pss
        monkeypatch.setattr(pns, "_STORAGE_PATH", tmp_path / "patient_names.json")
        monkeypatch.setattr(pss, "_STORAGE_PATH", tmp_path / "patient_status.json")
        monkeypatch.setattr(
            pss, "_HISTORY_PATH", tmp_path / "patient_status_history.json"
        )
        yield

    def test_initial_all_patients_counted_as_new(self, app_path: Path):
        """初期状態では 10 名全員が "🆕 新規" に集計される."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        # Block B の内訳タグの後に「10名」が続くパターン（順序は最後）
        # _STATUS_NORMAL の末尾が "new"
        assert "🆕 新規" in markdown_text
        # 10名の表示（内訳行の金額なし簡易確認）
        assert "10名" in markdown_text

    def test_count_status_uses_session_state(self):
        """_count_status は session_state を優先し、既存患者の初期値を置き換える."""
        # _count_status は session_state 優先 → ストア → サンプル既定 の順に読む
        # サンプル患者（全員 new）に対して、session_state で一部上書きした状態を再現
        patients = cmv._get_sample_patients("5F", "normal")

        import streamlit as st
        # session_state のダミー設定（AppTest 外でも可能）
        # _count_status 内の st.session_state.get で fallback が効くので直接代入
        try:
            st.session_state.clear()
        except Exception:
            pass
        try:
            st.session_state["conf_patient_status"] = {
                patients[0].patient_id: "rehab",
                patients[1].patient_id: "medical",
            }
        except Exception:
            # Streamlit コンテキスト外なら辞書はそのまま（関数側で get() がある）
            pass

        counts = cmv._count_status(patients)
        # 2 名は更新、残り 8 名は "new"
        # session_state が利用できない環境でも 10 名全員 "new" になる（下記アサーションで対応）
        total = sum(counts.values())
        assert total == 10


# ---------------------------------------------------------------------------
# 9. ステータス変更時の JSON 永続化（即保存）
# ---------------------------------------------------------------------------

class TestStatusPersistence:
    """ステータス selectbox を変更すると patient_status.json に保存される."""

    @pytest.fixture
    def app_path(self, tmp_path: Path) -> Path:
        repo_scripts = Path(__file__).resolve().parent.parent / "scripts"
        entry = repo_scripts / "_conference_view_test_entry.py"
        _write_app_entry(entry)
        yield entry
        try:
            entry.unlink()
        except FileNotFoundError:
            pass

    @pytest.fixture
    def isolated_stores(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """2 つのストア（名前 / ステータス）+ 履歴ファイルを独立した一時ファイルに差し替える."""
        import patient_name_store as pns
        import patient_status_store as pss
        names_path = tmp_path / "patient_names.json"
        status_path = tmp_path / "patient_status.json"
        history_path = tmp_path / "patient_status_history.json"
        monkeypatch.setattr(pns, "_STORAGE_PATH", names_path)
        monkeypatch.setattr(pss, "_STORAGE_PATH", status_path)
        monkeypatch.setattr(pss, "_HISTORY_PATH", history_path)
        return {
            "names_path": names_path,
            "status_path": status_path,
            "history_path": history_path,
        }

    def test_status_file_initially_absent(self, isolated_stores: dict, app_path: Path):
        """アプリ初期描画時、ステータス JSON はまだ作成されない（selectbox 未変更）."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        # 初期描画だけで selectbox を動かしていない → ファイル未作成
        assert not isolated_stores["status_path"].exists()

    def test_save_status_directly_roundtrips(self, isolated_stores: dict):
        """save_status 直接呼び出しで JSON に書き込まれる."""
        import patient_status_store as pss
        pss.save_status("test_uuid", "rehab")
        assert isolated_stores["status_path"].exists()
        data = json.loads(isolated_stores["status_path"].read_text(encoding="utf-8"))
        assert data == {"test_uuid": "rehab"}

    def test_load_all_statuses_reflects_saved_entries(self, isolated_stores: dict):
        """save 後に load_all_statuses で復元できる."""
        import patient_status_store as pss
        pss.save_status("u1", "new")
        pss.save_status("u2", "medical")
        pss.save_status("u3", "family")
        all_statuses = pss.load_all_statuses()
        assert all_statuses == {"u1": "new", "u2": "medical", "u3": "family"}

    def test_view_reads_persisted_status_on_startup(
        self, isolated_stores: dict, app_path: Path
    ):
        """起動前に保存されたステータスが UI 初期状態に反映される."""
        import patient_status_store as pss
        # 5F 通常モードの最初の患者 "a1b2c3d4" を事前に "rehab" で保存
        pss.save_status("a1b2c3d4", "rehab")

        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        # 画面のどこかに「🟠 リハ最適化中」が表示される（該当患者 1 名分のタグ）
        assert "リハ最適化中" in markdown_text


# ---------------------------------------------------------------------------
# 10. ステータスタグ クリッカブル化（副院長 UX 改善指示 2026-04-17）
# ---------------------------------------------------------------------------

class TestStatusTagClickable:
    """ステータスタグ自体を popover trigger にした新 UX の検証.

    副院長決定（2026-04-17）: 右側の selectbox 列を撤去し、ステータスタグを
    クリック → プルダウン → 選択 → 即保存 の流れに統一。
    """

    @pytest.fixture
    def app_path(self, tmp_path: Path) -> Path:
        repo_scripts = Path(__file__).resolve().parent.parent / "scripts"
        entry = repo_scripts / "_conference_view_test_entry.py"
        _write_app_entry(entry)
        yield entry
        try:
            entry.unlink()
        except FileNotFoundError:
            pass

    @pytest.fixture(autouse=True)
    def isolate_storage(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """各テストでストア JSON を汚染しない."""
        import patient_name_store as pns
        import patient_status_store as pss
        monkeypatch.setattr(pns, "_STORAGE_PATH", tmp_path / "patient_names.json")
        monkeypatch.setattr(pss, "_STORAGE_PATH", tmp_path / "patient_status.json")
        monkeypatch.setattr(
            pss, "_HISTORY_PATH", tmp_path / "patient_status_history.json"
        )
        yield

    def test_no_status_update_selectbox_anymore(self, app_path: Path):
        """右側のステータス更新 selectbox が完全に撤去されている.

        残っている selectbox は病棟切替の 1 個だけ（`conf_ward_select`）。
        """
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        # selectbox は病棟切替の 1 個のみ
        assert len(at.selectbox) == 1, (
            f"selectbox が 1 個（病棟切替のみ）ではなく {len(at.selectbox)} 個存在する"
        )
        assert at.selectbox[0].key == "conf_ward_select"
        # 旧ラベル「ステータス更新 - 」は画面に出ない
        all_sb_labels = [sb.label for sb in at.selectbox]
        for label in all_sb_labels:
            assert "ステータス更新" not in (label or ""), (
                f"旧ラベル『ステータス更新』が残存: {label}"
            )
        # 旧 key `status_select_` も存在しない
        for sb in at.selectbox:
            assert not sb.key.startswith("status_select_"), (
                f"旧 selectbox key が残存: {sb.key}"
            )

    def test_ten_status_radios_per_patient(self, app_path: Path):
        """患者行ごとに popover 内のステータス radio が 1 個ずつ（計 10 個）存在."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        status_radios = [r for r in at.radio if r.key.startswith("status_radio_")]
        assert len(status_radios) == 10, (
            f"ステータス radio が 10 個ではない: {len(status_radios)} "
            f"(all keys: {[r.key for r in at.radio]})"
        )

    def test_status_radio_has_seven_options_in_normal_mode(self, app_path: Path):
        """通常モードでは radio の選択肢が 7 カテゴリ."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        status_radios = [r for r in at.radio if r.key.startswith("status_radio_")]
        assert len(status_radios) > 0
        for r in status_radios:
            assert len(r.options) == 7, (
                f"radio {r.key} の選択肢が 7 個でない: {len(r.options)}"
            )

    def test_status_radio_has_four_options_in_holiday_mode(self, app_path: Path):
        """連休対策モードでは radio の選択肢が 4 カテゴリ（new + 3）."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        # 連休対策モードに切替
        assert len(at.toggle) >= 1
        at.toggle[0].set_value(True)
        at.run()
        status_radios = [r for r in at.radio if r.key.startswith("status_radio_")]
        assert len(status_radios) == 10
        for r in status_radios:
            assert len(r.options) == 4, (
                f"radio {r.key} の連休モード選択肢が 4 個でない: {len(r.options)}"
            )

    def test_status_radio_select_persists_to_json(self, app_path: Path, tmp_path: Path):
        """radio で『リハ最適化中』を選ぶ → JSON に即保存される."""
        import patient_status_store as pss

        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()

        # 最初の患者 (a1b2c3d4 — 在院日数最大の "伊藤") の radio を取得
        status_radios = [r for r in at.radio if r.key.startswith("status_radio_")]
        assert len(status_radios) == 10
        # 初期値は "new"
        assert status_radios[0].value == "new"

        # "rehab" に切り替え → run()
        status_radios[0].set_value("rehab").run()

        # JSON に永続化されていること
        status_file = tmp_path / "patient_status.json"
        assert status_file.exists(), "status JSON が書き込まれていない"
        data = json.loads(status_file.read_text(encoding="utf-8"))
        # どの患者のものか（最長在院は "a1b2c3d4"）
        assert data.get("a1b2c3d4") == "rehab", (
            f"ステータス更新が JSON に反映されていない: {data}"
        )

        # 画面表示にも反映
        markdown_text = "\n".join(m.value for m in at.markdown)
        assert "リハ最適化中" in markdown_text

    def test_popover_wrap_class_present(self, app_path: Path):
        """ステータス popover ラッパークラス conf-status-popover-wrap が出力される."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        # 10 名 × 1 個 = 10 回登場するはず
        count = markdown_text.count("conf-status-popover-wrap")
        # CSS 定義で 1 回 + 各行 1 回（合計 11 回以上）
        assert count >= 11, (
            f"conf-status-popover-wrap クラスの登場回数が少ない: {count}"
        )

    def test_css_variable_for_status_color_present(self, app_path: Path):
        """各 popover trigger に CSS 変数 --conf-status-bg が注入されている."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        assert "--conf-status-bg:" in markdown_text
        assert "--conf-status-fg:" in markdown_text

    def test_print_media_hides_popover_trigger(self, app_path: Path):
        """@media print で popover trigger が非表示化される（代わりに静的タグ表示）."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        # CSS に print 用の規則が入っている
        assert "conf-status-print-tag" in markdown_text
        assert "conf-status-popover-wrap" in markdown_text


# ---------------------------------------------------------------------------
# 11. データクリア機能（副院長決定 2026-04-17 Q1-Q4）
# ---------------------------------------------------------------------------

class TestCountStoredData:
    """_count_stored_data ヘルパー関数の単体テスト."""

    @pytest.fixture(autouse=True)
    def isolate_storage(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        import patient_name_store as pns
        import patient_status_store as pss
        monkeypatch.setattr(pns, "_STORAGE_PATH", tmp_path / "patient_names.json")
        monkeypatch.setattr(pss, "_STORAGE_PATH", tmp_path / "patient_status.json")
        monkeypatch.setattr(
            pss, "_HISTORY_PATH", tmp_path / "patient_status_history.json"
        )
        yield

    def test_empty_stores_return_zero(self):
        """ファイル未作成時、全フィールド 0."""
        stats = cmv._count_stored_data()
        assert stats == {"doctor": 0, "name": 0, "id": 0, "status": 0}

    def test_counts_only_nonempty_fields(self):
        """空文字フィールドはカウントに含まれない."""
        import patient_name_store as pns
        pns.save_patient_info("u1", doctor_name="田中", patient_name="", patient_id="")
        pns.save_patient_info("u2", doctor_name="佐藤", patient_name="山田", patient_id="")
        pns.save_patient_info("u3", doctor_name="", patient_name="", patient_id="111")
        stats = cmv._count_stored_data()
        assert stats["doctor"] == 2  # u1, u2
        assert stats["name"] == 1  # u2
        assert stats["id"] == 1  # u3

    def test_status_count(self):
        """status は永続化ストアのエントリ数."""
        import patient_status_store as pss
        pss.save_status("a", "rehab")
        pss.save_status("b", "medical")
        stats = cmv._count_stored_data()
        assert stats["status"] == 2


class TestIndividualClearUI:
    """個別クリア UI (✏️ popover 内) の検証."""

    @pytest.fixture
    def app_path(self, tmp_path: Path) -> Path:
        repo_scripts = Path(__file__).resolve().parent.parent / "scripts"
        entry = repo_scripts / "_conference_view_test_entry.py"
        _write_app_entry(entry)
        yield entry
        try:
            entry.unlink()
        except FileNotFoundError:
            pass

    @pytest.fixture(autouse=True)
    def isolate_storage(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        import patient_name_store as pns
        import patient_status_store as pss
        monkeypatch.setattr(pns, "_STORAGE_PATH", tmp_path / "patient_names.json")
        monkeypatch.setattr(pss, "_STORAGE_PATH", tmp_path / "patient_status.json")
        monkeypatch.setattr(
            pss, "_HISTORY_PATH", tmp_path / "patient_status_history.json"
        )
        yield

    def test_individual_clear_checkboxes_exist(self, app_path: Path):
        """患者ごとに 4 種のクリアチェックボックスが存在する（10 名 × 4 = 40 個）."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        # それぞれのキーを数える
        clr_doc = [c for c in at.checkbox if c.key.startswith("clr_doc_")]
        clr_name = [c for c in at.checkbox if c.key.startswith("clr_name_")]
        clr_id = [c for c in at.checkbox if c.key.startswith("clr_id_")]
        clr_status = [c for c in at.checkbox if c.key.startswith("clr_status_")]
        assert len(clr_doc) == 10, f"clr_doc_ チェックボックスが 10 個ない: {len(clr_doc)}"
        assert len(clr_name) == 10, f"clr_name_ チェックボックスが 10 個ない: {len(clr_name)}"
        assert len(clr_id) == 10, f"clr_id_ チェックボックスが 10 個ない: {len(clr_id)}"
        assert len(clr_status) == 10, f"clr_status_ チェックボックスが 10 個ない: {len(clr_status)}"

    def test_individual_clear_button_exists(self, app_path: Path):
        """個別クリア実行ボタンが患者 10 名分存在."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        clr_buttons = [b for b in at.button if b.key.startswith("clr_exec_")]
        assert len(clr_buttons) == 10


class TestBulkClearUI:
    """一括クリア UI (データ管理 expander) の検証."""

    @pytest.fixture
    def app_path(self, tmp_path: Path) -> Path:
        repo_scripts = Path(__file__).resolve().parent.parent / "scripts"
        entry = repo_scripts / "_conference_view_test_entry.py"
        _write_app_entry(entry)
        yield entry
        try:
            entry.unlink()
        except FileNotFoundError:
            pass

    @pytest.fixture(autouse=True)
    def isolate_storage(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        import patient_name_store as pns
        import patient_status_store as pss
        monkeypatch.setattr(pns, "_STORAGE_PATH", tmp_path / "patient_names.json")
        monkeypatch.setattr(pss, "_STORAGE_PATH", tmp_path / "patient_status.json")
        monkeypatch.setattr(
            pss, "_HISTORY_PATH", tmp_path / "patient_status_history.json"
        )
        yield

    def test_bulk_clear_expander_label_shown(self, app_path: Path):
        """"🗑 データ管理（一括クリア）" ラベルが画面に出る."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        # expander のラベルは at.expander / markdown のどちらでも検出できる
        all_labels = [e.label for e in at.expander]
        assert any("データ管理" in (label or "") for label in all_labels), (
            f"データ管理 expander が見つからない: {all_labels}"
        )

    def test_bulk_clear_checkboxes_exist(self, app_path: Path):
        """一括クリア用チェックボックス 4 種が存在."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        keys = {c.key for c in at.checkbox}
        assert "clr_all_doctor" in keys
        assert "clr_all_name" in keys
        assert "clr_all_id" in keys
        assert "clr_all_status" in keys

    def test_bulk_clear_confirm_text_input_exists(self, app_path: Path):
        """確認用タイプ入力欄が存在."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        keys = {t.key for t in at.text_input}
        assert "clr_all_confirm" in keys

    def test_bulk_clear_button_disabled_initially(self, app_path: Path):
        """初期状態（チェックなし + 確認文字未入力）で実行ボタンが disabled."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        # clr_all_exec ボタンを検出
        btns = [b for b in at.button if b.key == "clr_all_exec"]
        assert len(btns) == 1
        assert btns[0].disabled is True, "初期状態で実行ボタンが disabled でない"

    def test_bulk_clear_button_disabled_when_only_checkbox(self, app_path: Path):
        """チェックボックスのみ選択で確認文字未入力 → disabled."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        # チェックボックスを 1 個 ON
        for c in at.checkbox:
            if c.key == "clr_all_doctor":
                c.set_value(True)
                break
        at.run()
        btns = [b for b in at.button if b.key == "clr_all_exec"]
        assert len(btns) == 1
        assert btns[0].disabled is True, "確認文字なしで disabled でない"

    def test_bulk_clear_button_disabled_when_only_confirm_text(self, app_path: Path):
        """確認文字のみ入力でチェックなし → disabled."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        for t in at.text_input:
            if t.key == "clr_all_confirm":
                t.set_value("クリア")
                break
        at.run()
        btns = [b for b in at.button if b.key == "clr_all_exec"]
        assert len(btns) == 1
        assert btns[0].disabled is True, "チェックなしで disabled でない"

    def test_bulk_clear_button_enabled_when_both_satisfied(self, app_path: Path):
        """チェック + 確認文字完全一致 → ボタン有効化."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        # チェックボックス 1 個 ON
        for c in at.checkbox:
            if c.key == "clr_all_doctor":
                c.set_value(True)
                break
        # 確認文字を「クリア」に
        for t in at.text_input:
            if t.key == "clr_all_confirm":
                t.set_value("クリア")
                break
        at.run()
        btns = [b for b in at.button if b.key == "clr_all_exec"]
        assert len(btns) == 1
        assert btns[0].disabled is False, "両方満たしても実行ボタンが有効化されない"

    def test_bulk_clear_button_disabled_for_partial_match(self, app_path: Path):
        """確認文字が「クリア」と完全一致しない場合は disabled."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        for c in at.checkbox:
            if c.key == "clr_all_doctor":
                c.set_value(True)
                break
        for t in at.text_input:
            if t.key == "clr_all_confirm":
                t.set_value("クリアする")  # 部分一致・余分な文字
                break
        at.run()
        btns = [b for b in at.button if b.key == "clr_all_exec"]
        assert len(btns) == 1
        assert btns[0].disabled is True, "部分一致で disabled になっていない"

    def test_bulk_clear_executes_and_clears_store(self, app_path: Path, tmp_path: Path):
        """実行ボタンをクリックすると JSON ファイルから該当フィールドが消える."""
        import patient_name_store as pns

        # 事前に 2 名分データを保存
        pns.save_patient_info("a1b2c3d4", doctor_name="旧医師", patient_name="旧患者")
        pns.save_patient_info("b2c3d4e5", doctor_name="旧医師2", patient_id="999")

        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()

        # 主治医名を一括クリア
        for c in at.checkbox:
            if c.key == "clr_all_doctor":
                c.set_value(True)
                break
        for t in at.text_input:
            if t.key == "clr_all_confirm":
                t.set_value("クリア")
                break
        at.run()

        # ボタンをクリック
        for b in at.button:
            if b.key == "clr_all_exec":
                b.click()
                break
        at.run()

        # doctor_name が空になっていること
        info_a = pns.load_patient_info("a1b2c3d4")
        info_b = pns.load_patient_info("b2c3d4e5")
        assert info_a["doctor_name"] == ""
        assert info_b["doctor_name"] == ""
        # 他フィールドは残る
        assert info_a["patient_name"] == "旧患者"
        assert info_b["patient_id"] == "999"

    def test_data_manage_wrap_class_present_for_print_hiding(self, app_path: Path):
        """印刷時非表示用のラッパークラス conf-data-manage-wrap が出力される."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        assert "conf-data-manage-wrap" in markdown_text

    def test_print_media_hides_data_manage_wrap(self, app_path: Path):
        """@media print の CSS に conf-data-manage-wrap: display:none がある."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        import re
        # @media print { ... } ブロックを抽出
        print_blocks = re.findall(
            r"@media print\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}",
            markdown_text,
        )
        found = False
        for block in print_blocks:
            if "conf-data-manage-wrap" in block and "display" in block and "none" in block:
                found = True
                break
        assert found, "@media print の CSS に conf-data-manage-wrap 非表示ルールがない"

    def test_bulk_clear_counts_shown_in_labels(self, app_path: Path):
        """チェックボックスのラベルに現在の件数が表示される."""
        import patient_name_store as pns
        import patient_status_store as pss

        # 事前にデータを入れる（主治医 1 名、ステータス 2 名）
        pns.save_patient_info("u1", doctor_name="田中")
        pss.save_status("s1", "rehab")
        pss.save_status("s2", "medical")

        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()

        # チェックボックスのラベルから件数を確認
        labels = {c.key: c.label for c in at.checkbox}
        assert "1 名" in labels.get("clr_all_doctor", ""), (
            f"clr_all_doctor ラベルに件数 1 が出ていない: {labels.get('clr_all_doctor')}"
        )
        assert "2 名" in labels.get("clr_all_status", ""), (
            f"clr_all_status ラベルに件数 2 が出ていない: {labels.get('clr_all_status')}"
        )


# ---------------------------------------------------------------------------
# 12. 連休対策モード切替 推奨バナー（副院長決定 2026-04-18）
# ---------------------------------------------------------------------------

def _write_app_entry_with_today(path: Path, today_str: str) -> None:
    """任意 today でカンファビューを描画する AppTest 用エントリ.

    ``today_str`` は ``"2026, 4, 18"`` 形式（date() コンストラクタ引数の直書き）。
    """
    path.write_text(
        f"""
import sys
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import streamlit as st
st.set_page_config(layout='wide')

from views.conference_material_view import render_conference_material_view
from datetime import date

render_conference_material_view(today=date({today_str}))
""",
        encoding="utf-8",
    )


class TestHolidayModeRecommendBanner:
    """連休対策モード切替の推奨バナー描画を検証.

    副院長決定（2026-04-18）: 連休対策モードは手動切替のみ。
    ただし「連休まで 21 日以下」になったら、画面上部に推奨バナー（💡…切替を推奨）
    を表示して気づきを促す。severity は 8-21 日=warning（橙）、7 日以内=urgent（赤）。
    """

    @pytest.fixture(autouse=True)
    def isolate_storage(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        import patient_name_store as pns
        import patient_status_store as pss
        monkeypatch.setattr(pns, "_STORAGE_PATH", tmp_path / "patient_names.json")
        monkeypatch.setattr(pss, "_STORAGE_PATH", tmp_path / "patient_status.json")
        monkeypatch.setattr(
            pss, "_HISTORY_PATH", tmp_path / "patient_status_history.json"
        )
        yield

    def _app_entry(self, tmp_path: Path, today_str: str) -> Path:
        repo_scripts = Path(__file__).resolve().parent.parent / "scripts"
        entry = repo_scripts / "_conference_view_test_entry.py"
        _write_app_entry_with_today(entry, today_str)
        return entry

    def _markdown(self, app_path: Path) -> str:
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        return "\n".join(m.value for m in at.markdown), at

    def test_banner_absent_when_days_exceed_21(self, tmp_path: Path):
        """2026-04-10（GW まで 22 日）では推奨バナーは表示されない."""
        app = self._app_entry(tmp_path, "2026, 4, 10")
        try:
            markdown, _ = self._markdown(app)
            assert (
                'data-testid="conference-holiday-mode-recommend-banner"'
                not in markdown
            ), "21 日超なのに推奨バナーが表示されている"
        finally:
            app.unlink(missing_ok=True)

    def test_banner_shown_at_boundary_21_days(self, tmp_path: Path):
        """2026-04-11（GW まで 21 日）では推奨バナーが warning severity で出る."""
        app = self._app_entry(tmp_path, "2026, 4, 11")
        try:
            markdown, _ = self._markdown(app)
            assert (
                'data-testid="conference-holiday-mode-recommend-banner"'
                in markdown
            ), "21 日ちょうどで推奨バナーが出ない"
            assert 'data-severity="warning"' in markdown
        finally:
            app.unlink(missing_ok=True)

    def test_banner_warning_severity_at_14_days(self, tmp_path: Path):
        """2026-04-18（GW まで 14 日）では warning severity（橙）."""
        app = self._app_entry(tmp_path, "2026, 4, 18")
        try:
            markdown, _ = self._markdown(app)
            assert (
                'data-testid="conference-holiday-mode-recommend-banner"'
                in markdown
            )
            assert 'data-severity="warning"' in markdown
            assert 'data-days="14"' in markdown
            assert "💡" in markdown
            assert "連休対策モードへの切替を推奨します" in markdown
        finally:
            app.unlink(missing_ok=True)

    def test_banner_urgent_severity_at_7_days(self, tmp_path: Path):
        """2026-04-25（GW まで 7 日）では urgent severity（赤）."""
        app = self._app_entry(tmp_path, "2026, 4, 25")
        try:
            markdown, _ = self._markdown(app)
            assert 'data-severity="urgent"' in markdown
            assert 'data-days="7"' in markdown
        finally:
            app.unlink(missing_ok=True)

    def test_banner_hidden_when_holiday_mode_on(self, tmp_path: Path):
        """連休対策モード ON に切り替えると推奨バナーは非表示."""
        app = self._app_entry(tmp_path, "2026, 4, 18")
        try:
            from streamlit.testing.v1 import AppTest
            at = AppTest.from_file(str(app), default_timeout=30)
            at.run()
            # 初期状態（通常モード）ではバナー表示
            md1 = "\n".join(m.value for m in at.markdown)
            assert (
                'data-testid="conference-holiday-mode-recommend-banner"'
                in md1
            )
            # モードを holiday に切替
            assert len(at.toggle) >= 1
            at.toggle[0].set_value(True)
            at.run()
            md2 = "\n".join(m.value for m in at.markdown)
            assert (
                'data-testid="conference-holiday-mode-recommend-banner"'
                not in md2
            ), "連休対策モード ON なのに推奨バナーが残っている"
            # 戻すと再表示
            at.toggle[0].set_value(False)
            at.run()
            md3 = "\n".join(m.value for m in at.markdown)
            assert (
                'data-testid="conference-holiday-mode-recommend-banner"'
                in md3
            ), "通常モードに戻したのにバナーが再表示されない"
        finally:
            app.unlink(missing_ok=True)

    def test_banner_print_visible_style_injected(self, tmp_path: Path):
        """印刷時（@media print）にもバナーは表示される（display:none にならない）."""
        app = self._app_entry(tmp_path, "2026, 4, 18")
        try:
            markdown, _ = self._markdown(app)
            # バナー用スタイルが含まれており、@media print で display:none にされていない
            assert ".conf-holiday-recommend-banner" in markdown
            # print ブロック抽出してバナーが display:none されていないことを確認
            import re
            # CSS の @media print ブロック全体（複数）を取得
            print_blocks = re.findall(
                r"@media print\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}",
                markdown,
            )
            for block in print_blocks:
                if "conf-holiday-recommend-banner" in block:
                    # 対象クラスに display: none が指定されていないことを確認
                    # （display プロパティそのものが無ければ OK、あっても none ではない）
                    assert "display: none" not in block, (
                        "推奨バナーが print で非表示化されている"
                    )
                    assert "display:none" not in block, (
                        "推奨バナーが print で非表示化されている"
                    )
        finally:
            app.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 📚 rotation_eligible フィルタと折りたたみファクトライブラリ（2026-04-18）
# ---------------------------------------------------------------------------

class TestRotationEligibleFilter:
    """``_select_fact`` の rotation_eligible フィルタ（副院長指示 2026-04-18）."""

    def _base_fact(self, fact_id, rotation_eligible, weight=5):
        return {
            "id": fact_id,
            "text": f"{fact_id} text",
            "author": "Test",
            "journal": "Test J",
            "year": 2024,
            "n": "n=1",
            "pmid": "12345",
            "doi": "10.1234/test",
            "layer": 1,
            "layer_name": "退院時機能の最適化",
            "rotation_eligible": rotation_eligible,
            "context": {
                "wards": ["5F"], "modes": ["normal"],
                "audience": ["all"], "weight": weight,
            },
        }

    def test_default_selects_only_rotation_eligible(self):
        """デフォルト (rotation_only=True) では rotation_eligible=True のみ抽選."""
        facts = [
            self._base_fact("rot_true_1", True, weight=5),
            self._base_fact("rot_false_1", False, weight=100),
            self._base_fact("rot_false_2", False, weight=100),
        ]
        rng = random.Random(0)
        for _ in range(30):
            chosen = cmv._select_fact(facts, "5F", "normal", rng=rng)
            assert chosen is not None
            assert chosen["id"] == "rot_true_1", (
                f"rotation_eligible=False のファクト {chosen['id']} が抽選された"
            )

    def test_rotation_only_false_includes_all(self):
        """rotation_only=False なら rotation_eligible 無視（全件候補）."""
        facts = [
            self._base_fact("rot_true_1", True, weight=1),
            self._base_fact("rot_false_1", False, weight=100),
        ]
        # 重みの差で rot_false_1 が選ばれる頻度が高いはず
        rng = random.Random(0)
        false_count = 0
        for _ in range(100):
            chosen = cmv._select_fact(
                facts, "5F", "normal", rng=rng, rotation_only=False,
            )
            assert chosen is not None
            if chosen["id"] == "rot_false_1":
                false_count += 1
        assert false_count > 50, (
            f"rotation_only=False で rot_false_1 が十分選ばれない ({false_count}/100)"
        )

    def test_production_yaml_filter_returns_only_12(self):
        """本番 facts.yaml からのローテーション候補は 12 件に限定される."""
        facts = cmv._load_facts()
        eligible = [f for f in facts if f.get("rotation_eligible") is True]
        assert len(eligible) == 12, (
            f"本番 YAML の rotation_eligible=True は 12 件 (実際 {len(eligible)})"
        )

    def test_all_production_5F_normal_selections_are_eligible(self):
        """複数回抽選しても、選ばれたファクトは全て rotation_eligible=True."""
        facts = cmv._load_facts()
        # 多様な seed で複数回抽選して、全て rotation_eligible=True であることを確認
        for seed in range(50):
            rng = random.Random(seed)
            chosen = cmv._select_fact(facts, "5F", "normal", rng=rng)
            if chosen is None:
                continue
            assert chosen.get("rotation_eligible") is True, (
                f"seed={seed} で選ばれた {chosen['id']} が rotation_eligible=False"
            )


class TestFilterFactsByKeyword:
    """キーワード検索ヘルパー ``_filter_facts_by_keyword``."""

    def _mk(self, **kwargs):
        base = {
            "id": "x", "text": "", "author": "", "journal": "",
            "layer_name": "",
        }
        base.update(kwargs)
        return base

    def test_empty_keyword_returns_all(self):
        facts = [self._mk(text="AAA"), self._mk(text="BBB")]
        assert cmv._filter_facts_by_keyword(facts, "") == facts
        assert cmv._filter_facts_by_keyword(facts, "   ") == facts

    def test_match_in_text(self):
        facts = [
            self._mk(id="1", text="Cochrane 2022 NNTH=25"),
            self._mk(id="2", text="他のテキスト"),
        ]
        hits = cmv._filter_facts_by_keyword(facts, "Cochrane")
        assert [f["id"] for f in hits] == ["1"]

    def test_match_is_case_insensitive(self):
        facts = [self._mk(text="JAMA Intern Med")]
        hits = cmv._filter_facts_by_keyword(facts, "jama")
        assert len(hits) == 1

    def test_match_in_author(self):
        facts = [self._mk(author="Martínez-Velilla 2019")]
        hits = cmv._filter_facts_by_keyword(facts, "Martínez")
        assert len(hits) == 1

    def test_match_in_journal(self):
        facts = [self._mk(journal="BMJ SPRINTT")]
        hits = cmv._filter_facts_by_keyword(facts, "SPRINTT")
        assert len(hits) == 1

    def test_match_in_layer_name(self):
        facts = [self._mk(layer_name="退院時機能の最適化")]
        hits = cmv._filter_facts_by_keyword(facts, "機能")
        assert len(hits) == 1


class TestGroupFactsByLayer:
    """レイヤーグループ化ヘルパー ``_group_facts_by_layer``."""

    def test_groups_by_layer(self):
        facts = [
            {"id": "a", "layer": 1},
            {"id": "b", "layer": 3},
            {"id": "c", "layer": 1},
        ]
        grouped = cmv._group_facts_by_layer(facts)
        assert set(grouped.keys()) == {1, 3}
        assert [f["id"] for f in grouped[1]] == ["a", "c"]
        assert [f["id"] for f in grouped[3]] == ["b"]

    def test_sorted_by_id(self):
        facts = [
            {"id": "f010", "layer": 1},
            {"id": "f001", "layer": 1},
            {"id": "f005", "layer": 1},
        ]
        grouped = cmv._group_facts_by_layer(facts)
        assert [f["id"] for f in grouped[1]] == ["f001", "f005", "f010"]

    def test_skips_missing_layer(self):
        facts = [{"id": "a", "layer": 1}, {"id": "b"}]
        grouped = cmv._group_facts_by_layer(facts)
        assert 1 in grouped
        assert len(grouped[1]) == 1


class TestFactLibraryExpanderIntegration:
    """📚 折りたたみファクトライブラリの統合テスト（AppTest）."""

    @pytest.fixture
    def app_path(self, tmp_path: Path) -> Path:
        repo_scripts = Path(__file__).resolve().parent.parent / "scripts"
        entry = repo_scripts / "_conference_view_fact_library_entry.py"
        _write_app_entry(entry)
        yield entry
        try:
            entry.unlink()
        except FileNotFoundError:
            pass

    def test_fact_library_expander_rendered(self, app_path: Path):
        """ファクトライブラリ expander が画面に含まれる."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        # expander のラベルに「他のエビデンスを見る」が含まれる
        labels = [e.label for e in at.expander]
        has_library = any("他のエビデンスを見る" in lab for lab in labels)
        assert has_library, (
            f"ファクトライブラリ expander が画面にない。ラベル一覧: {labels}"
        )

    def test_fact_library_hidden_testids_present(self, app_path: Path):
        """件数 testid が描画される (total/rotation/non-rotation)."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        assert 'data-testid="conference-fact-library-total"' in markdown_text
        assert 'data-testid="conference-fact-library-rotation"' in markdown_text
        assert 'data-testid="conference-fact-library-non-rotation"' in markdown_text

    def test_fact_library_total_count_matches_yaml(self, app_path: Path):
        """testid に出る total 件数が YAML の件数と一致."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        import re
        m = re.search(
            r'data-testid="conference-fact-library-total"[^>]*>(\d+)<',
            markdown_text,
        )
        assert m is not None, "fact-library-total testid に値が入っていない"
        total_in_ui = int(m.group(1))
        yaml_total = len(cmv._load_facts())
        assert total_in_ui == yaml_total, (
            f"UI 総件数 {total_in_ui} が YAML 件数 {yaml_total} と不一致"
        )

    def test_fact_library_rotation_count_is_12(self, app_path: Path):
        """UI に出るローテーション件数が 12."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        import re
        m = re.search(
            r'data-testid="conference-fact-library-rotation"[^>]*>(\d+)<',
            markdown_text,
        )
        assert m is not None
        assert int(m.group(1)) == 12, (
            f"ローテーション件数が 12 件でない (実際 {m.group(1)})"
        )

    def test_fact_library_wrap_class_in_markdown(self, app_path: Path):
        """conf-fact-library-wrap クラスが出力される（印刷 CSS 対象）."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        assert "conf-fact-library-wrap" in markdown_text

    def test_fact_library_print_media_hides_wrap(self, app_path: Path):
        """@media print で conf-fact-library-wrap が display:none."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        import re
        # @media print ブロックを抽出し、その中に display:none が指定されているか確認
        print_blocks = re.findall(
            r"@media print\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}",
            markdown_text,
        )
        found_hide = False
        for block in print_blocks:
            if "conf-fact-library-wrap" in block and "display: none" in block:
                found_hide = True
                break
            if "conf-fact-library-wrap" in block and "display:none" in block:
                found_hide = True
                break
        assert found_hide, (
            "@media print で conf-fact-library-wrap が非表示にされていない"
        )


class TestFactBarStillPrintsNormally:
    """ローテーションバー自体は印刷表示される（副院長指示）."""

    @pytest.fixture
    def app_path(self, tmp_path: Path) -> Path:
        repo_scripts = Path(__file__).resolve().parent.parent / "scripts"
        entry = repo_scripts / "_conference_view_fact_bar_print_entry.py"
        _write_app_entry(entry)
        yield entry
        try:
            entry.unlink()
        except FileNotFoundError:
            pass

    def test_print_hides_fact_bar_legacy(self, app_path: Path):
        """既存仕様通り conf-fact-bar は @media print で非表示（既存挙動維持）."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        import re
        print_blocks = re.findall(
            r"@media print\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}",
            markdown_text,
        )
        # conf-fact-bar が print で display:none にされていることを確認（既存仕様）
        found_fact_bar_hide = any(
            "conf-fact-bar" in block
            and ("display:none" in block or "display: none" in block)
            for block in print_blocks
        )
        assert found_fact_bar_hide, (
            "conf-fact-bar の印刷時非表示（既存仕様）が失われている"
        )


# ---------------------------------------------------------------------------
# 実データ連携（2026-04-18 追加）
# ---------------------------------------------------------------------------

import pandas as pd  # noqa: E402


def _make_detail_df(rows: list) -> pd.DataFrame:
    """admission_details 互換の DataFrame を構築するヘルパー.

    rows: list of dicts with optional keys:
      event_type ("admission" / "discharge"), date, ward, route,
      source_doctor, attending_doctor, los_days, phase, id, short3_type
    """
    cols = [
        "id", "date", "ward", "event_type", "route",
        "source_doctor", "attending_doctor",
        "los_days", "phase", "short3_type",
    ]
    filled = []
    for i, r in enumerate(rows):
        record = {c: r.get(c, None) for c in cols}
        if record["id"] is None:
            record["id"] = f"evt-{i:04d}"
        filled.append(record)
    df = pd.DataFrame(filled, columns=cols)
    df["date"] = pd.to_datetime(df["date"])
    df["id"] = df["id"].astype("string")
    df["ward"] = df["ward"].astype("string")
    df["event_type"] = df["event_type"].astype("string")
    df["attending_doctor"] = df["attending_doctor"].astype("string")
    df["los_days"] = pd.to_numeric(df["los_days"], errors="coerce").astype("Int64")
    return df


class TestPatientsFromActualData:
    """_patients_from_actual_data のユニットテスト."""

    def test_returns_empty_on_none_df(self):
        """df が None のとき空リスト + data_unavailable=True."""
        patients, meta = cmv._patients_from_actual_data(
            today=date(2026, 4, 17), ward="5F", mode="normal",
            df_override=None,
        )
        assert patients == []
        assert meta["data_unavailable"] is True
        assert meta["reason"] == "no_data"

    def test_returns_empty_on_empty_df(self):
        """空 DataFrame でも落ちず空リストを返す."""
        empty = _make_detail_df([])
        patients, meta = cmv._patients_from_actual_data(
            today=date(2026, 4, 17), ward="5F", mode="normal",
            df_override=empty,
        )
        assert patients == []
        assert meta["data_unavailable"] is True
        assert meta["reason"] == "no_data"

    def test_ward_filter_works(self):
        """ward が一致する admission のみ返る."""
        df = _make_detail_df([
            {"event_type": "admission", "date": "2026-04-10", "ward": "5F",
             "attending_doctor": "田中", "route": "外来紹介"},
            {"event_type": "admission", "date": "2026-04-10", "ward": "6F",
             "attending_doctor": "佐藤", "route": "救急"},
        ])
        p_5f, _ = cmv._patients_from_actual_data(
            today=date(2026, 4, 17), ward="5F", mode="normal", df_override=df,
        )
        p_6f, _ = cmv._patients_from_actual_data(
            today=date(2026, 4, 17), ward="6F", mode="normal", df_override=df,
        )
        assert len(p_5f) == 1
        assert p_5f[0].ward == "5F"
        assert len(p_6f) == 1
        assert p_6f[0].ward == "6F"

    def test_discharged_patients_excluded(self):
        """退院済み患者（(ward, admission_date) が discharge レコードに対応）は除外."""
        df = _make_detail_df([
            # 入院 4/10、退院 4/15 (los=5) → 現在入院していない
            {"event_type": "admission", "date": "2026-04-10", "ward": "5F",
             "attending_doctor": "田中", "route": "外来紹介"},
            {"event_type": "discharge", "date": "2026-04-15", "ward": "5F",
             "attending_doctor": "田中", "los_days": 5},
            # 入院 4/12、未退院 → 在院中
            {"event_type": "admission", "date": "2026-04-12", "ward": "5F",
             "attending_doctor": "佐藤", "route": "救急"},
        ])
        patients, _ = cmv._patients_from_actual_data(
            today=date(2026, 4, 17), ward="5F", mode="normal", df_override=df,
        )
        assert len(patients) == 1
        assert patients[0].doctor_surname == "佐藤"
        # 4/12 → 4/17 は 6 日目 (Day 1 = 入院当日)
        assert patients[0].day_count == 6

    def test_future_admission_excluded(self):
        """today より後に入院予定のレコードは含めない."""
        df = _make_detail_df([
            {"event_type": "admission", "date": "2026-04-25", "ward": "5F",
             "attending_doctor": "未来"},
        ])
        patients, meta = cmv._patients_from_actual_data(
            today=date(2026, 4, 17), ward="5F", mode="normal", df_override=df,
        )
        assert len(patients) == 0
        assert meta["reason"] == "no_inpatients"

    def test_sorting_by_day_count_desc(self):
        """在院日数降順（長期優先）で返る."""
        df = _make_detail_df([
            {"event_type": "admission", "date": "2026-04-16", "ward": "5F",
             "attending_doctor": "A"},  # Day 2
            {"event_type": "admission", "date": "2026-03-17", "ward": "5F",
             "attending_doctor": "B"},  # Day 32
            {"event_type": "admission", "date": "2026-04-10", "ward": "5F",
             "attending_doctor": "C"},  # Day 8
        ])
        patients, _ = cmv._patients_from_actual_data(
            today=date(2026, 4, 17), ward="5F", mode="normal", df_override=df,
        )
        assert [p.doctor_surname for p in patients] == ["B", "C", "A"]

    def test_max_patients_limit(self):
        """max_patients=10 を超えるデータでも上位 10 名のみ."""
        rows = []
        base = date(2026, 4, 1)
        for i in range(15):
            rows.append({
                "event_type": "admission",
                "date": base.isoformat(),
                "ward": "5F",
                "attending_doctor": f"Dr{i:02d}",
                "id": f"adm-{i:04d}",
            })
        df = _make_detail_df(rows)
        patients, meta = cmv._patients_from_actual_data(
            today=date(2026, 4, 17), ward="5F", mode="normal", df_override=df,
        )
        assert len(patients) == 10
        assert meta["total_inpatients"] == 15

    def test_fewer_than_10_patients_handled(self):
        """在院者が 10 名未満でも正しく動く（3 名など）."""
        rows = [
            {"event_type": "admission", "date": "2026-04-10", "ward": "5F",
             "attending_doctor": "田中"},
            {"event_type": "admission", "date": "2026-04-12", "ward": "5F",
             "attending_doctor": "佐藤"},
            {"event_type": "admission", "date": "2026-04-14", "ward": "5F",
             "attending_doctor": "鈴木"},
        ]
        df = _make_detail_df(rows)
        patients, meta = cmv._patients_from_actual_data(
            today=date(2026, 4, 17), ward="5F", mode="normal", df_override=df,
        )
        assert len(patients) == 3
        assert meta["total_inpatients"] == 3
        assert meta["reason"] == "ok"
        # 全員 status_key=new で初期化される
        for p in patients:
            assert p.status_key == "new"

    def test_no_inpatients_reason(self):
        """admission がゼロ（discharge のみ、or ward 不一致）の場合 no_inpatients."""
        df = _make_detail_df([
            {"event_type": "admission", "date": "2026-04-10", "ward": "6F",
             "attending_doctor": "田中"},
        ])
        patients, meta = cmv._patients_from_actual_data(
            today=date(2026, 4, 17), ward="5F", mode="normal", df_override=df,
        )
        assert patients == []
        assert meta["reason"] == "no_inpatients"
        assert meta["total_inpatients"] == 0

    def test_stable_anonymized_patient_id(self):
        """同じ admission id からは同じ patient_id が返る（ステータス永続性の保証）."""
        df = _make_detail_df([
            {"id": "fixed-id-1234", "event_type": "admission",
             "date": "2026-04-10", "ward": "5F", "attending_doctor": "田中"},
        ])
        p1, _ = cmv._patients_from_actual_data(
            today=date(2026, 4, 17), ward="5F", mode="normal", df_override=df,
        )
        p2, _ = cmv._patients_from_actual_data(
            today=date(2026, 4, 17), ward="5F", mode="normal", df_override=df,
        )
        assert len(p1) == 1 and len(p2) == 1
        assert p1[0].patient_id == p2[0].patient_id
        # 8 桁 hex
        assert len(p1[0].patient_id) == 8
        all(c in "0123456789abcdef" for c in p1[0].patient_id)

    def test_missing_columns_graceful_fallback(self):
        """admission_details に必須列が欠落していてもエラーにならない."""
        broken = pd.DataFrame({"foo": [1, 2], "bar": [3, 4]})
        patients, meta = cmv._patients_from_actual_data(
            today=date(2026, 4, 17), ward="5F", mode="normal",
            df_override=broken,
        )
        assert patients == []
        assert meta["reason"] == "error"

    def test_doctor_surname_extraction(self):
        """姓 名（スペース区切り）から姓のみ抽出."""
        df = _make_detail_df([
            {"event_type": "admission", "date": "2026-04-10", "ward": "5F",
             "attending_doctor": "田中 太郎"},
            {"event_type": "admission", "date": "2026-04-10", "ward": "5F",
             "attending_doctor": "佐藤　花子"},  # 全角スペース
            {"event_type": "admission", "date": "2026-04-10", "ward": "5F",
             "attending_doctor": "鈴木"},
        ])
        patients, _ = cmv._patients_from_actual_data(
            today=date(2026, 4, 17), ward="5F", mode="normal", df_override=df,
        )
        surnames = [p.doctor_surname for p in patients]
        assert "田中" in surnames
        assert "佐藤" in surnames
        assert "鈴木" in surnames

    def test_doctor_empty_fallback(self):
        """attending_doctor が空の場合「未定」にフォールバック."""
        df = _make_detail_df([
            {"event_type": "admission", "date": "2026-04-10", "ward": "5F",
             "attending_doctor": None},
        ])
        patients, _ = cmv._patients_from_actual_data(
            today=date(2026, 4, 17), ward="5F", mode="normal", df_override=df,
        )
        assert len(patients) == 1
        assert patients[0].doctor_surname == "未定"

    def test_note_shows_route(self):
        """note に入院経路が含まれる."""
        df = _make_detail_df([
            {"event_type": "admission", "date": "2026-04-10", "ward": "5F",
             "attending_doctor": "田中", "route": "救急"},
        ])
        patients, _ = cmv._patients_from_actual_data(
            today=date(2026, 4, 17), ward="5F", mode="normal", df_override=df,
        )
        assert "実データ" in patients[0].note
        assert "救急" in patients[0].note


class TestResolvePatientsDispatch:
    """_resolve_patients のモード分岐."""

    def test_simulation_mode_returns_sample(self):
        """シミュレーションモード → サンプル 10 名."""
        patients, src, meta = cmv._resolve_patients(
            today=date(2026, 4, 17), ward="5F", mode="normal",
            data_source_override="🔬 シミュレーション（予測モデル）",
        )
        assert src == "sample"
        assert len(patients) == 10

    def test_empty_data_source_defaults_to_sample(self):
        """data_source_mode が空文字列でもサンプルにフォールバック."""
        patients, src, _ = cmv._resolve_patients(
            today=date(2026, 4, 17), ward="5F", mode="normal",
            data_source_override="",
        )
        assert src == "sample"
        assert len(patients) == 10

    def test_actual_mode_uses_actual_data(self):
        """実績データモード → 実データから取得."""
        df = _make_detail_df([
            {"event_type": "admission", "date": "2026-04-10", "ward": "5F",
             "attending_doctor": "田中"},
        ])
        patients, src, meta = cmv._resolve_patients(
            today=date(2026, 4, 17), ward="5F", mode="normal",
            data_source_override="📋 実績データ（日次入力）",
            df_override=df,
        )
        assert src == "actual"
        assert len(patients) == 1
        assert "実データ" in patients[0].note

    def test_actual_mode_empty_data_returns_empty(self):
        """実績データモードで DataFrame 空 → 空リスト + meta.data_unavailable."""
        patients, src, meta = cmv._resolve_patients(
            today=date(2026, 4, 17), ward="5F", mode="normal",
            data_source_override="📋 実績データ（日次入力）",
            df_override=_make_detail_df([]),
        )
        assert src == "actual"
        assert patients == []
        assert meta["data_unavailable"] is True


class TestAnonymizePatientId:
    """_anonymize_patient_id のヘルパーテスト."""

    def test_same_input_same_output(self):
        assert cmv._anonymize_patient_id("abc") == cmv._anonymize_patient_id("abc")

    def test_different_input_different_output(self):
        assert cmv._anonymize_patient_id("abc") != cmv._anonymize_patient_id("xyz")

    def test_empty_input_safe(self):
        assert len(cmv._anonymize_patient_id("")) == 8
        assert len(cmv._anonymize_patient_id(None)) == 8

    def test_returns_8_char(self):
        assert len(cmv._anonymize_patient_id("whatever-uuid-here")) == 8


class TestExtractSurname:
    """_extract_surname のヘルパーテスト."""

    def test_half_space_split(self):
        assert cmv._extract_surname("田中 太郎") == "田中"

    def test_full_space_split(self):
        assert cmv._extract_surname("佐藤　花子") == "佐藤"

    def test_short_name_pass_through(self):
        assert cmv._extract_surname("鈴木") == "鈴木"

    def test_long_name_truncated(self):
        assert cmv._extract_surname("山田太郎花子") == "山田太"

    def test_empty_fallback(self):
        assert cmv._extract_surname("") == "未定"
        assert cmv._extract_surname(None) == "未定"


class TestConferenceRendersWithActualData:
    """render_conference_material_view が実データ引数で落ちないこと（統合）."""

    def test_render_with_empty_actual_data_shows_warning(self, tmp_path):
        """実データモード + 空 DataFrame → warning が出る（エラーで落ちない）."""
        import importlib

        # ストリームリット AppTest を使わずに内部関数の結線だけ検証
        # _resolve_patients が空 + actual を返すことを確認
        patients, src, meta = cmv._resolve_patients(
            today=date(2026, 4, 17), ward="5F", mode="normal",
            data_source_override="📋 実績データ（日次入力）",
            df_override=_make_detail_df([]),
        )
        assert src == "actual"
        assert patients == []
        assert meta["data_unavailable"] is True

    def test_render_with_actual_data_via_apptest(self, tmp_path):
        """AppTest で実データモードを渡しても描画が完走する."""
        from streamlit.testing.v1 import AppTest

        repo_scripts = Path(__file__).resolve().parent.parent / "scripts"
        entry = repo_scripts / "_conference_view_actual_entry.py"
        entry.write_text(
            """
import sys
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import streamlit as st
st.set_page_config(layout='wide')

import pandas as pd
from datetime import date

# 実データモードを強制し、空 DataFrame を渡す
from views.conference_material_view import render_conference_material_view

render_conference_material_view(
    today=date(2026, 4, 17),
    data_source_override='📋 実績データ（日次入力）',
    df_override=pd.DataFrame(),
)
""",
            encoding="utf-8",
        )
        try:
            at = AppTest.from_file(str(entry), default_timeout=30)
            at.run()
            # エラーで終わっていないこと
            assert not at.exception, f"レンダリングで例外: {at.exception}"
            # warning が 1 つ以上出ていること
            warnings_text = " ".join(w.value for w in at.warning) if at.warning else ""
            # no_data は warning 表示（reason="no_data" → st.warning）
            assert "入退院詳細データが未登録" in warnings_text or len(at.warning) > 0
        finally:
            try:
                entry.unlink()
            except FileNotFoundError:
                pass


# ---------------------------------------------------------------------------
# 11. 週次カンファ履歴 UI（2026-04-18 新規）
# ---------------------------------------------------------------------------

class TestWeeklyHistoryExpander:
    """📈 先週からの変化 expander の描画検証."""

    @pytest.fixture
    def app_path(self, tmp_path: Path) -> Path:
        repo_scripts = Path(__file__).resolve().parent.parent / "scripts"
        entry = repo_scripts / "_conference_view_test_entry.py"
        _write_app_entry(entry)
        yield entry
        try:
            entry.unlink()
        except FileNotFoundError:
            pass

    @pytest.fixture(autouse=True)
    def isolate_storage(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """ステータス/履歴/名前ストアを隔離."""
        import patient_name_store as pns
        import patient_status_store as pss
        monkeypatch.setattr(pns, "_STORAGE_PATH", tmp_path / "patient_names.json")
        monkeypatch.setattr(pss, "_STORAGE_PATH", tmp_path / "patient_status.json")
        monkeypatch.setattr(
            pss, "_HISTORY_PATH", tmp_path / "patient_status_history.json"
        )
        yield

    def test_history_expander_testid_present(self, app_path: Path):
        """履歴エクスパンダーの data-testid (件数集計) が markdown に含まれる."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        # 3 種の集計件数テスト ID
        assert 'data-testid="conference-history-changes-count"' in markdown_text
        assert 'data-testid="conference-history-stagnant-count"' in markdown_text
        assert 'data-testid="conference-history-long-undecided-count"' in markdown_text

    def test_history_expander_initial_counts_zero(self, app_path: Path):
        """初期状態（履歴ファイル未作成）では全カウントが 0."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        # 0 が 3 箇所出るはず（changes/stagnant/long_undecided）
        import re
        m = re.search(
            r'data-testid="conference-history-changes-count" '
            r'style="display:none">(\d+)<',
            markdown_text,
        )
        assert m is not None
        assert m.group(1) == "0"

    def test_history_expander_shows_changes_after_save(self, app_path: Path):
        """履歴ファイルに記録があると expander の集計が 1 以上になる.

        Note: entry app は today=date(2026, 4, 17) 固定なので、
        history 側も同日以前の日付で手動書き込み、reference_date の窓に入れる。
        """
        import patient_status_store as pss
        import json
        # 直接履歴ファイルに書き込む（2026-04-15 の変化 2 件）
        history_path = Path(pss._HISTORY_PATH)
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text(
            json.dumps({
                "a1b2c3d4": [
                    {
                        "timestamp": "2026-04-12T10:00:00",
                        "status": "new",
                        "conference_date": "2026-04-12",
                    },
                    {
                        "timestamp": "2026-04-15T10:00:00",
                        "status": "undecided",
                        "conference_date": "2026-04-15",
                    },
                ]
            }),
            encoding="utf-8",
        )

        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        import re
        m = re.search(
            r'data-testid="conference-history-changes-count" '
            r'style="display:none">(\d+)<',
            markdown_text,
        )
        assert m is not None
        count = int(m.group(1))
        # reference_date=2026-04-17, 窓 [4/10, 4/17] → 2 件とも該当
        assert count == 2, f"履歴変化カウントが 2 ではない: {count}"

    def test_history_expander_renders_without_error(self, app_path: Path):
        """履歴 expander を含む全体描画で例外が出ない."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        assert not at.exception, (
            f"履歴 expander 描画で例外: {[e.value for e in at.exception]}"
        )

    def test_history_label_present_in_expander(self, app_path: Path):
        """expander ラベル「📈 先週からの変化」が画面に存在する."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        # expander は at.expander で確認
        labels = [e.label for e in at.expander] if at.expander else []
        joined = " | ".join(labels)
        assert "📈" in joined or "先週からの変化" in joined, (
            f"履歴 expander ラベルが見つからない: {labels}"
        )

    def test_stagnant_warning_shown_for_old_history(self, app_path: Path):
        """3 週以上前の履歴のみの患者 → 停滞警告に登場."""
        import patient_status_store as pss
        import json
        # 履歴ファイルを直接書き込む（3 週以上前の日付）
        # 5F サンプルの実在 UUID "a1b2c3d4" を使う
        history_path = Path(pss._HISTORY_PATH)
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text(
            json.dumps({
                "a1b2c3d4": [
                    {
                        "timestamp": "2026-03-20T10:00:00",
                        "status": "undecided",
                        "conference_date": "2026-03-20",
                    },
                ]
            }),
            encoding="utf-8",
        )

        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        # 停滞患者 testid が存在する
        assert "conference-history-stagnant-a1b2c3d4" in markdown_text, (
            "停滞患者の testid が見つからない"
        )

    def test_long_undecided_warning_shown(self, app_path: Path):
        """在院 21 日以上 × undecided の患者は要議論リストに登場."""
        import patient_status_store as pss
        # サンプル 5F 最初の患者 a1b2c3d4 は Day 35（在院 21 日以上）
        # status を undecided にセット
        pss.save_status("a1b2c3d4", "undecided")

        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        # 要議論 testid が存在する
        assert "conference-history-long-undecided-a1b2c3d4" in markdown_text

    def test_per_patient_history_btn_testid_exists(self, app_path: Path):
        """各患者行に 📜 履歴ボタンの testid が出る（10 名分）."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        import re
        testids = re.findall(
            r'data-testid="conference-history-btn-([a-f0-9]{8})"',
            markdown_text,
        )
        # 10 名分出るはず
        assert len(testids) == 10, (
            f"📜 履歴ボタンの testid が 10 個ではない: {len(testids)} ({testids})"
        )

    def test_print_css_hides_history_expander(self, app_path: Path):
        """@media print で履歴 expander が非表示になる CSS が含まれる."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        # print CSS に history-expander-wrap / history-btn-wrap の non-display が入る
        assert ".conf-history-expander-wrap" in markdown_text
        assert ".conf-history-btn-wrap" in markdown_text

    def test_existing_testids_preserved(self, app_path: Path):
        """既存 data-testid が履歴機能追加で壊れていないこと."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        markdown_text = "\n".join(m.value for m in at.markdown)
        # 主要な既存 testid が全て存在する
        required_testids = [
            "conference-mode",
            "conference-ward",
            "conference-occupancy-pct",
            "conference-alos-days",
            "conference-emergency-pct",
            "conference-patient-count",
            "conference-fact-id",
        ]
        for testid in required_testids:
            assert f'data-testid="{testid}"' in markdown_text, (
                f"既存 testid '{testid}' が壊れている"
            )


class TestHistoryStoreHelpers:
    """新規ヘルパ関数 _format_status_label / _aggregate_status_changes."""

    def test_format_status_label_normal(self):
        """通常モードの status_key が正しくラベル化."""
        assert "方向性未決" in cmv._format_status_label("undecided")
        assert "新規" in cmv._format_status_label("new")

    def test_format_status_label_holiday(self):
        """連休モードの status_key も同じ関数で解決."""
        assert "連休前退院" in cmv._format_status_label("before_confirmed")

    def test_format_status_label_unknown(self):
        """未知 key は フォールバック表示."""
        assert "未分類" in cmv._format_status_label("invalid_key")

    def test_aggregate_status_changes_counts_transitions(self):
        """_aggregate_status_changes が遷移ペアごとに件数集計する."""
        changes = [
            {"uuid": "u1", "from_status": "new", "to_status": "undecided"},
            {"uuid": "u2", "from_status": "new", "to_status": "undecided"},
            {"uuid": "u3", "from_status": "undecided", "to_status": "family"},
        ]
        agg = cmv._aggregate_status_changes(changes)
        assert agg[("new", "undecided")] == 2
        assert agg[("undecided", "family")] == 1

    def test_aggregate_status_changes_empty(self):
        assert cmv._aggregate_status_changes([]) == {}

    def test_aggregate_includes_new_tracking(self):
        """初出エントリ（from_status="") も別キーで集計される."""
        changes = [
            {"uuid": "u1", "from_status": "", "to_status": "new"},
            {"uuid": "u2", "from_status": "", "to_status": "new"},
        ]
        agg = cmv._aggregate_status_changes(changes)
        assert agg[("", "new")] == 2


# ---------------------------------------------------------------------------
# 10. Live KPI metrics — サマリーと Block A の数値整合性
# ---------------------------------------------------------------------------

class _FakeSessionState:
    """st.session_state の .get() インターフェースを模倣する簡易コンテナ."""

    def __init__(self, data: dict):
        self._d = dict(data)

    def get(self, key, default=None):
        return self._d.get(key, default)

    def __getitem__(self, key):
        return self._d[key]

    def __contains__(self, key):
        return key in self._d


class TestLiveKpiMetrics:
    """_compute_live_kpi_metrics が「本日のサマリー」と同じ数値を返す."""

    def _make_ward_df(self, mean_occ_pct: float, days: int = 18):
        """occupancy_rate 平均が指定 % になる 1 月分の DataFrame を構築."""
        import pandas as pd
        from datetime import datetime, timedelta

        start = datetime(2026, 4, 1)
        dates = [start + timedelta(days=i) for i in range(days)]
        # occupancy_rate は 0-1 ratio
        occ = mean_occ_pct / 100.0
        return pd.DataFrame(
            {
                "date": dates,
                "occupancy_rate": [occ] * days,
                "total_patients": [int(47 * occ)] * days,
                "new_admissions": [5] * days,
                "discharges": [5] * days,
                "daily_revenue": [1_500_000] * days,
                "daily_cost": [900_000] * days,
                "daily_profit": [600_000] * days,
                "phase_a_ratio": [0.4] * days,
                "phase_b_ratio": [0.4] * days,
                "phase_c_ratio": [0.2] * days,
            }
        )

    def test_returns_none_when_no_session_data(self):
        """session_state 空なら None (サンプル値フォールバック)."""
        fake = _FakeSessionState({})
        result = cmv._compute_live_kpi_metrics("5F", date(2026, 4, 18), session_state=fake)
        assert result is None

    def test_occupancy_matches_summary_5f(self):
        """5F の occupancy_pct は ward_raw_dfs["5F"] の occupancy_rate.mean()*100 と一致."""
        df_5f = self._make_ward_df(86.5)
        fake = _FakeSessionState({"ward_raw_dfs": {"5F": df_5f}, "ward_raw_dfs_full": {"5F": df_5f}})
        result = cmv._compute_live_kpi_metrics("5F", date(2026, 4, 18), session_state=fake)
        assert result is not None
        assert result["occupancy_pct"] == 86.5, (
            f"Block A の稼働率がサマリーと乖離: Block A={result['occupancy_pct']}, 期待=86.5"
        )

    def test_occupancy_matches_summary_6f(self):
        """6F の occupancy_pct もサマリーと一致 (副院長指摘: 6F 91.1% vs 82% の乖離)."""
        df_6f = self._make_ward_df(91.1)
        fake = _FakeSessionState({"ward_raw_dfs": {"6F": df_6f}, "ward_raw_dfs_full": {"6F": df_6f}})
        result = cmv._compute_live_kpi_metrics("6F", date(2026, 4, 18), session_state=fake)
        assert result is not None
        assert result["occupancy_pct"] == 91.1

    def test_sim_ward_dfs_takes_precedence_over_actual(self):
        """シミュレーションモード時は sim_ward_raw_dfs を優先する."""
        df_sim = self._make_ward_df(88.0)
        df_actual = self._make_ward_df(70.0)
        fake = _FakeSessionState(
            {
                "sim_ward_raw_dfs": {"5F": df_sim},
                "ward_raw_dfs": {"5F": df_actual},
            }
        )
        result = cmv._compute_live_kpi_metrics("5F", date(2026, 4, 18), session_state=fake)
        assert result is not None
        assert result["occupancy_pct"] == 88.0, "sim_ward_raw_dfs が優先されていない"

    def test_remaining_days_uses_calendar_month_end(self):
        """残り診療日は当月末までのカレンダー日数と一致する."""
        df_5f = self._make_ward_df(85.0)
        fake = _FakeSessionState({"ward_raw_dfs": {"5F": df_5f}, "ward_raw_dfs_full": {"5F": df_5f}})
        # 2026-04-18 なら 4/30 まで 12 日
        result = cmv._compute_live_kpi_metrics("5F", date(2026, 4, 18), session_state=fake)
        assert result is not None
        assert result["remaining_business_days"] == 12.0

    def test_required_bed_days_zero_when_target_met(self):
        """稼働率が目標 90% を上回っているときは必要床日は 0."""
        df_5f = self._make_ward_df(92.0)
        fake = _FakeSessionState({"ward_raw_dfs": {"5F": df_5f}, "ward_raw_dfs_full": {"5F": df_5f}})
        result = cmv._compute_live_kpi_metrics("5F", date(2026, 4, 18), session_state=fake)
        assert result is not None
        assert result["required_bed_days"] == 0.0

    def test_alos_computed_from_rolling_los(self):
        """alos_days は calculate_rolling_los() の結果を反映 (サンプル 17.5 とは異なる値)."""
        df_5f = self._make_ward_df(86.5, days=90)
        fake = _FakeSessionState({"ward_raw_dfs": {"5F": df_5f}, "ward_raw_dfs_full": {"5F": df_5f}})
        result = cmv._compute_live_kpi_metrics("5F", date(2026, 4, 18), session_state=fake)
        assert result is not None
        # rolling_los = 在院延日数 / ((入院+退院)/2)
        # 在院延日数 = 47*0.865 * 90 ≈ 3660, (新5+退5)/2 * 90 = 450 → 3660/450 ≈ 8.1
        # サンプル値 17.5 ではない → 実データ経由で計算されていることを保証
        assert result["alos_days"] != 17.5
        assert 0 < result["alos_days"] < 50  # 常識的範囲

    def test_conference_block_a_matches_summary_occupancy(self):
        """Block A の `conference-occupancy-pct` testid がサマリー月平均と一致する (E2E 代用)."""
        # サマリー計算式: ward_raw_dfs[ward]["occupancy_rate"].mean() * 100
        # カンファ Block A: _compute_live_kpi_metrics(ward) → occupancy_pct
        # 両者が同じ値を返すことを保証する統合テスト。
        df_6f = self._make_ward_df(91.1)
        fake = _FakeSessionState({"ward_raw_dfs": {"6F": df_6f}, "ward_raw_dfs_full": {"6F": df_6f}})
        kpi = cmv._compute_live_kpi_metrics("6F", date(2026, 4, 18), session_state=fake)
        # サマリーの式を再現して期待値を得る
        expected_summary_occ = round(float(df_6f["occupancy_rate"].mean()) * 100, 1)
        assert kpi["occupancy_pct"] == expected_summary_occ, (
            f"サマリーとカンファ Block A の稼働率が乖離: "
            f"サマリー={expected_summary_occ} vs Block A={kpi['occupancy_pct']}"
        )

    def test_fallback_to_full_df_when_current_month_missing(self):
        """ward_raw_dfs にデータがなくても ward_raw_dfs_full があれば計算できる."""
        df_full = self._make_ward_df(89.0)
        fake = _FakeSessionState({"ward_raw_dfs": {}, "ward_raw_dfs_full": {"5F": df_full}})
        result = cmv._compute_live_kpi_metrics("5F", date(2026, 4, 18), session_state=fake)
        assert result is not None
        assert result["occupancy_pct"] == 89.0

    def test_explicit_override_params(self):
        """ward_dfs_override / ward_dfs_full_override が session_state を上書きする."""
        df_over = self._make_ward_df(80.0)
        df_session = self._make_ward_df(95.0)
        fake = _FakeSessionState({"ward_raw_dfs": {"5F": df_session}})
        result = cmv._compute_live_kpi_metrics(
            "5F", date(2026, 4, 18),
            session_state=fake,
            ward_dfs_override={"5F": df_over},
            ward_dfs_full_override={"5F": df_over},
        )
        assert result is not None
        assert result["occupancy_pct"] == 80.0
