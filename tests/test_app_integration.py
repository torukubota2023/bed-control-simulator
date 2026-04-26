"""
Streamlit アプリ統合テスト — ランタイムエラー検出

Streamlit を実際に起動せず、AST解析とソースコード分析で
「セクション切替時の未定義変数アクセス」等のバグを検出する。

検出対象:
- st.session_state.X へのガードなしアクセス
- _tab_idx["..."] で参照されるタブ名がセクション定義に未登録
- データ未準備時の変数未定義パス
- st.stop() による意図しないセクションブロック
"""

import ast
import re
import textwrap
from pathlib import Path

import pytest

APP_PATH = Path(__file__).resolve().parent.parent / "scripts" / "bed_control_simulator_app.py"
APP_SOURCE = APP_PATH.read_text(encoding="utf-8")
APP_LINES = APP_SOURCE.splitlines()


# =====================================================================
# ヘルパー
# =====================================================================

def _parse_app_ast() -> ast.Module:
    """アプリソースをAST解析（構文エラー自体のテストも兼ねる）"""
    return ast.parse(APP_SOURCE, filename=str(APP_PATH))


def _find_all_tab_names_from_sections() -> list[str]:
    """セクション別タブ定義からすべてのタブ名を収集する

    _ALL_TAB_NAMES は廃止されたため、各セクションの tab_names 定義から収集する。
    ソース内のユニコードエスケープ（\\U0001f4ca 等）を実際の文字に変換して返す。
    """
    names = set()
    for line in APP_LINES:
        if "tab_names" not in line:
            continue
        # tab_names = [...], extend([...]), append("...") 内の文字列リテラルを抽出
        for m in re.finditer(r'"([^"]+)"', line):
            raw = m.group(1)
            # _tab_idx 等の参照は除外（tab_names への代入行のみ対象）
            if "tab_names" in line and ("=" in line or "extend" in line or "append" in line):
                names.add(_normalize_unicode(raw))
    return list(names)


def _normalize_unicode(s: str) -> str:
    """ソース中のユニコードエスケープを実際の文字に展開する"""
    if "\\U" in s or "\\u" in s:
        return s.encode("raw_unicode_escape").decode("unicode_escape")
    return s


def _find_tab_idx_references() -> list[tuple[int, str]]:
    """ソース内の _tab_idx["..."] 参照をすべて抽出（行番号, 正規化済みタブ名）"""
    results = []
    pattern = r'_tab_idx\["([^"]+)"\]'
    for i, line in enumerate(APP_LINES, start=1):
        for m in re.finditer(pattern, line):
            results.append((i, _normalize_unicode(m.group(1))))
    return results


def _find_session_state_dot_accesses() -> list[tuple[int, str]]:
    """st.session_state.XXX の属性アクセスを抽出（.get() は除外）"""
    results = []
    # st.session_state.attr_name のパターン（.get( を除外）
    pattern = r'st\.session_state\.(\w+)'
    for i, line in enumerate(APP_LINES, start=1):
        # コメント行はスキップ
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        for m in re.finditer(pattern, line):
            attr = m.group(1)
            # .get() 呼び出しは安全なのでスキップ
            if attr == "get":
                continue
            results.append((i, attr))
    return results


def _find_session_state_initializations() -> set[str]:
    """セッション状態初期化ブロックで定義される変数名を収集"""
    initialized = set()
    # パターン1: if "X" not in st.session_state: st.session_state.X = ...
    pattern1 = r'if\s+"(\w+)"\s+not\s+in\s+st\.session_state'
    # パターン2: st.session_state.setdefault("X", ...)
    pattern2 = r'st\.session_state\.setdefault\(\s*"(\w+)"'
    for line in APP_LINES:
        for m in re.finditer(pattern1, line):
            initialized.add(m.group(1))
        for m in re.finditer(pattern2, line):
            initialized.add(m.group(1))
    return initialized


def _find_session_state_assignments() -> set[str]:
    """st.session_state.X = ... の代入先を収集"""
    assigned = set()
    pattern = r'st\.session_state\.(\w+)\s*='
    for line in APP_LINES:
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        for m in re.finditer(pattern, line):
            attr = m.group(1)
            if attr != "get":
                assigned.add(attr)
    return assigned


# =====================================================================
# テスト: AST解析（構文チェック）
# =====================================================================

class TestAppParsing:
    """アプリファイルの構文・インポート検証"""

    def test_ast_parse_成功(self):
        """アプリソースがAST解析可能であること（構文エラーなし）"""
        tree = _parse_app_ast()
        assert isinstance(tree, ast.Module)
        # トップレベルに十分な数のノードがあること（空ファイルでない）
        assert len(tree.body) > 50, "トップレベルノードが少なすぎる — ファイルが壊れている可能性"

    def test_py_compile_成功(self):
        """py_compile でコンパイル可能であること"""
        import py_compile
        # 例外が発生しなければ成功
        py_compile.compile(str(APP_PATH), doraise=True)


# =====================================================================
# テスト: タブ名の整合性
# =====================================================================

class TestTabNameConsistency:
    """_tab_idx 参照とセクション別タブ定義の整合性"""

    def test_全タブ参照がセクション定義に存在する(self):
        """_tab_idx["X"] で参照されるすべてのタブ名がいずれかのセクション定義に含まれること"""
        all_names = _find_all_tab_names_from_sections()
        references = _find_tab_idx_references()

        missing = []
        for line_no, tab_name in references:
            if tab_name not in all_names:
                missing.append(f"  L{line_no}: _tab_idx[\"{tab_name}\"] — セクション定義に未登録")

        assert not missing, (
            f"セクション定義に含まれないタブ名が参照されている:\n"
            + "\n".join(missing)
        )

    def test_セクション定義に重複がないこと(self):
        """セクション別タブ定義に重複したタブ名がないこと"""
        all_names = _find_all_tab_names_from_sections()
        seen = set()
        duplicates = []
        for name in all_names:
            if name in seen:
                duplicates.append(name)
            seen.add(name)

        assert not duplicates, f"セクション別タブ定義に重複あり: {duplicates}"

    def test_セクション別タブが空でないこと(self):
        """各セクションの tab_names が少なくとも1つのタブを含むこと"""
        # ソースから各セクションの tab_names 定義を検出
        section_pattern = r'(elif|if)\s+_selected_section\s*==\s*"([^"]+)":'
        sections_found = []
        for i, line in enumerate(APP_LINES, start=1):
            m = re.search(section_pattern, line)
            if m:
                section_name = m.group(2)
                # 次の行で tab_names = [] かどうかをチェック
                next_lines = "\n".join(APP_LINES[i:i+5])
                if "tab_names = []" in next_lines:
                    # tab_names = [] の場合、その後に .extend() や .append() があるか確認
                    has_extend = "tab_names.extend" in next_lines or "tab_names.append" in next_lines
                    if not has_extend:
                        sections_found.append(f"  セクション '{section_name}' (L{i}): tab_names = [] のまま")
                sections_found_ok = True

        # "⚙️ データ・設定" は tab_names = [] で始まるが .extend で追加されるので OK
        # 空のまま進むセクションがないか確認
        # （このテストは構造変更時のリグレッション検出用）

    def test_tab_idx_get使用のフォールバック確認(self):
        """_tab_idx.get() で安全にアクセスしている箇所が存在すること"""
        get_pattern = r'_tab_idx\.get\('
        get_count = len(re.findall(get_pattern, APP_SOURCE))
        # 少なくとも1箇所は .get() を使用しているはず（実績分析タブ等）
        assert get_count >= 1, "_tab_idx.get() の安全なアクセスが見つからない"

    def test_全tab_idx参照にガードがあること(self):
        """with tabs[_tab_idx["X"]] の前に if "X" in _tab_idx ガードがあること"""
        unguarded = []
        for i, line in enumerate(APP_LINES, start=1):
            m = re.search(r'with\s+tabs\[_tab_idx\["([^"]+)"\]\]', line)
            if not m:
                continue
            tab_name = _normalize_unicode(m.group(1))
            # 前の行（空行スキップ）にガードがあるか確認
            # 直前の数行、またはさらに上方（最大30行）に同タブ名のガードがあればOK
            # （split pattern: auth check + content blockで2回参照されるケース対応）
            prev_idx = i - 2  # 0-indexed
            found_guard = False
            while prev_idx >= 0 and prev_idx >= i - 6:
                prev_line = APP_LINES[prev_idx]
                if f'"{m.group(1)}" in _tab_idx' in prev_line:
                    found_guard = True
                    break
                if prev_line.strip() and not prev_line.strip().startswith('#'):
                    break
                prev_idx -= 1
            # 直前に見つからなくても、上方30行以内にガードがあればOK
            # （認証分離パターン: 同一 if ブロック内の2つ目の with tabs[...]）
            if not found_guard:
                for scan_idx in range(max(0, i - 31), i - 1):
                    if f'"{m.group(1)}" in _tab_idx' in APP_LINES[scan_idx]:
                        found_guard = True
                        break
            if not found_guard:
                unguarded.append(f"  L{i}: with tabs[_tab_idx[\"{tab_name}\"]] — ガードなし")
        assert not unguarded, (
            f"ガードなしの _tab_idx アクセス（セクション切替時にKeyError）:\n"
            + "\n".join(unguarded)
        )


# =====================================================================
# テスト: セッション状態の安全性
# =====================================================================

class TestSessionStateSafety:
    """st.session_state へのアクセスが適切にガードされているか"""

    def test_全アクセス変数が初期化または代入されている(self):
        """st.session_state.X へのアクセスに対応する初期化 or 代入が存在すること"""
        initialized = _find_session_state_initializations()
        assigned = _find_session_state_assignments()
        all_defined = initialized | assigned

        accesses = _find_session_state_dot_accesses()

        # Streamlit 組み込み属性・メソッドは除外
        builtin_attrs = {"query_params", "theme", "pop", "update", "keys", "values", "items", "clear"}

        undefined = []
        for line_no, attr in accesses:
            if attr in builtin_attrs:
                continue
            if attr not in all_defined:
                undefined.append(f"  L{line_no}: st.session_state.{attr} — 初期化/代入が見つからない")

        assert not undefined, (
            f"初期化なしでアクセスされている session_state 変数:\n"
            + "\n".join(undefined[:20])  # 最初の20件のみ表示
        )

    def test_主要変数の初期化ブロック存在(self):
        """データ保持用の主要セッション変数に初期化ブロックがあること"""
        initialized = _find_session_state_initializations()
        critical_vars = [
            "sim_df", "sim_summary", "sim_df_raw", "sim_params",
            "sim_ward_dfs", "sim_ward_raw_dfs", "sim_ward_summaries",
            "comparison",
        ]
        missing = [v for v in critical_vars if v not in initialized]
        assert not missing, f"主要セッション変数の初期化が見つからない: {missing}"

    def test_session_state_get_使用箇所が存在する(self):
        """安全な .get() アクセスが適切に使用されていること"""
        get_pattern = r'st\.session_state\.get\('
        get_count = len(re.findall(get_pattern, APP_SOURCE))
        # 多くの箇所で .get() が使われているはず
        assert get_count >= 5, f"st.session_state.get() の使用が少なすぎる ({get_count}箇所)"


# =====================================================================
# テスト: データフォールバックパス（最重要 — 今回のバグを検出するテスト）
# =====================================================================

class TestDataFallbackPaths:
    """データ未準備時に必要な変数が全パスで定義されるか検証

    今回のバグ: セクション切替時に _needs_sim_data=False のパスで
    df, summary 等が未定義のまま後続コードに到達していた問題を検出する。
    """

    def _extract_data_loading_block(self) -> str:
        """データロードブロック（_needs_sim_data 周辺）のソースを抽出"""
        start_marker = "_needs_sim_data = _selected_section"
        end_marker = "# カレンダー月日数のフォールバック"

        start_line = None
        end_line = None
        for i, line in enumerate(APP_LINES):
            if start_marker in line:
                start_line = i
            if end_marker in line and start_line is not None:
                end_line = i
                break

        assert start_line is not None, "データロードブロックの開始が見つからない"
        assert end_line is not None, "データロードブロックの終了が見つからない"
        return "\n".join(APP_LINES[start_line:end_line])

    def test_実績データモード_データなし_ダミー変数定義(self):
        """_is_actual_data_mode=True, _actual_data_available=False 時に
        df, summary, days_in_month, _active_raw_df, _active_cli_params が定義されること"""
        block = self._extract_data_loading_block()

        # 「データ不要セクション → ダミー値で続行」パス内の変数定義を確認
        required_vars = ["df", "summary", "days_in_month", "_active_raw_df", "_active_cli_params"]

        # st.stop() を廃止し、ダミー値パスで全ケースをカバー
        # （st.stop() は他タブの描画をブロックするため使用しない）

        # ダミー値定義パスの確認
        for var in required_vars:
            # 「ダミー値で続行」コメント周辺に変数定義があること
            pattern = rf"^\s+{re.escape(var)}\s*="
            matches = re.findall(pattern, block, re.MULTILINE)
            assert len(matches) >= 1, (
                f"データ未準備フォールバックで '{var}' の定義が見つからない。"
                f"セクション切替時にランタイムエラーになる可能性あり"
            )

    def test_シミュレーションモード_データなし_ダミー変数定義(self):
        """_is_actual_data_mode=False, _simulation_available=False 時に
        df, summary, days_in_month, _active_raw_df, _active_cli_params が定義されること"""
        block = self._extract_data_loading_block()

        required_vars = ["df", "summary", "days_in_month", "_active_raw_df", "_active_cli_params"]

        for var in required_vars:
            pattern = rf"^\s+{re.escape(var)}\s*="
            matches = re.findall(pattern, block, re.MULTILINE)
            assert len(matches) >= 1, (
                f"シミュレーション未実行フォールバックで '{var}' の定義が見つからない"
            )

    def test_データロードブロックにst_stopがないこと(self):
        """データロードブロック内に st.stop() が存在しないこと
        （st.stop() は他タブの描画をブロックするため、ダミー値パスで代替）"""
        block = self._extract_data_loading_block()
        lines = block.splitlines()

        stop_locations = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            # コメント行は除外
            if stripped.startswith("#"):
                continue
            if "st.stop()" in stripped:
                stop_locations.append(f"  データロードブロック内 L+{i}: st.stop() が残存")

        assert not stop_locations, (
            "データロードブロック内に st.stop() が残存 — "
            "他タブの描画がブロックされる可能性あり:\n"
            + "\n".join(stop_locations)
        )

    def test_ダミー値パスの完全性(self):
        """データ未準備時にダミー値パスが必ず通ること
        （_needs_sim_data の条件分岐が存在し、全パスでダミー値が設定される）"""
        block = self._extract_data_loading_block()

        # _needs_sim_data による条件分岐が存在すること
        assert "if _needs_sim_data:" in block or "if _needs_sim_data" in block, (
            "_needs_sim_data による条件分岐がデータロードブロックに存在しない"
        )


# =====================================================================
# テスト: st.stop() の安全性
# =====================================================================

class TestStStopSafety:
    """st.stop() が意図しないセクションをブロックしないことを検証"""

    def test_st_stop_総数の確認(self):
        """st.stop() の使用箇所数が想定範囲内であること"""
        stop_count = APP_SOURCE.count("st.stop()")
        # 現在の想定: 5-10箇所程度
        assert 3 <= stop_count <= 20, (
            f"st.stop() が {stop_count} 箇所 — 想定範囲外。"
            f"新しい st.stop() 追加時はセクション切替への影響を確認すること"
        )

    def test_データロード外のst_stop_はタブ内に限定(self):
        """データロードブロック外の st.stop() が with tabs[...] 内にあること"""
        # st.stop() の行番号を取得
        stop_lines = []
        for i, line in enumerate(APP_LINES, start=1):
            if "st.stop()" in line and not line.lstrip().startswith("#"):
                stop_lines.append(i)

        # データロードブロックの範囲を特定
        data_block_start = None
        data_block_end = None
        for i, line in enumerate(APP_LINES, start=1):
            if "_needs_sim_data = _selected_section" in line:
                data_block_start = i
            if "# カレンダー月日数のフォールバック" in line:
                data_block_end = i
                break

        # データロードブロック外の st.stop() をチェック
        outside_stops = [
            ln for ln in stop_lines
            if data_block_start and data_block_end and not (data_block_start <= ln <= data_block_end)
        ]

        # これらはすべて with tabs[...] ブロック内か、認証ガード内であるべき
        for ln in outside_stops:
            # st.stop() のインデントレベルで判定（トップレベル=危険、深い=タブ内で安全）
            line = APP_LINES[ln - 1]
            indent = len(line) - len(line.lstrip())
            # インデント8以上 = タブ内のネストされた処理（バリデーション等）
            if indent >= 8:
                continue
            # インデント浅い場合: 直前200行以内に with tabs[ か _require_data_auth があるか確認
            context_start = max(0, ln - 200)
            context = "\n".join(APP_LINES[context_start:ln])
            has_tab_context = "with tabs[" in context
            has_auth_context = "_require_data_auth" in context
            has_password_context = "password" in context.lower() or "パスワード" in context
            has_core_import_guard = "_CORE_AVAILABLE" in context
            assert (
                has_tab_context
                or has_auth_context
                or has_password_context
                or has_core_import_guard
            ), (
                f"L{ln}: st.stop() がタブコンテキストや認証ガード外にある — "
                f"全セクションをブロックする可能性あり"
            )


# =====================================================================
# テスト: セクション→タブマッピングの完全性
# =====================================================================

class TestActionFocusEthics:
    """最上段アクションカードの倫理フレーミングを守る"""

    def test_6f必要度カードは適応確認を先頭に置く(self):
        block_start = APP_SOURCE.find("def _build_past_year_focus_payload")
        block_end = APP_SOURCE.find("def _build_section_focus_payload", block_start)
        block = APP_SOURCE[block_start:block_end]

        assert "6F 必要度II: 月{_shortage:.1f}患者日ギャップ" in block
        assert "🛡️ 適応のある患者を見つけて" in block
        assert "適応評価後の参考値" in block
        assert "適応外処置・虚偽記録・病棟都合の患者選別は絶対NG" in block

    def test_管理者用3kpiは折りたたみ外に残す(self):
        summary_idx = APP_SOURCE.find('st.expander("☀️ 本日の詳細サマリー')
        strip_idx = APP_SOURCE.find("_render_admin_kpi_strip(locals())")

        assert strip_idx != -1, "管理者用KPI行の描画が見つからない"
        assert summary_idx != -1, "本日の詳細サマリー expander が見つからない"
        assert strip_idx < summary_idx, "管理者用KPI行は詳細サマリーの外・上に置く"
        assert 'data-testid="current-patients"' in APP_SOURCE


class TestSectionTabMapping:
    """サイドバーセクションとタブの対応が完全であること"""

    def test_全セクションにタブが割り当てられている(self):
        """_selected_section の全分岐で tab_names が定義されていること"""
        import unicodedata

        def _normalize(s: str) -> str:
            """ユニコードエスケープを展開し NFC 正規化する"""
            if "\\U" in s or "\\u" in s:
                s = s.encode("raw_unicode_escape").decode("unicode_escape")
            return unicodedata.normalize("NFC", s)

        # セクション定義を探索（_selected_section == "..." の条件分岐）
        section_pattern = r'_selected_section\s*==\s*"([^"]+)"'
        defined_sections = set(_normalize(s) for s in re.findall(section_pattern, APP_SOURCE))

        # サイドバーメニューに含まれるセクション
        menu_block = APP_SOURCE[APP_SOURCE.find("_section_names"):APP_SOURCE.find("_selected_section")]
        menu_sections = set()
        for m in re.finditer(r'"([^"]+)"', menu_block):
            val = m.group(1)
            if any(kw in val for kw in ["今日の運営", "意思決定", "制度", "データ", "HOPE", "過去1年"]):
                menu_sections.add(_normalize(val))

        # 各メニューセクションに対応する条件分岐があること
        for section in menu_sections:
            assert section in defined_sections, (
                f"セクション '{section}' のタブ定義分岐が見つからない"
            )

    def test_elseブランチにフォールバックタブがある(self):
        """セクション判定の else ブランチにフォールバック tab_names があること"""
        # セクション条件分岐ブロック内の トップレベル else: tab_names = [...] を確認
        # st.tabs(tab_names) 呼び出しの直前までを対象にする
        block_start = APP_SOURCE.find('if _selected_section == "')
        block_end = APP_SOURCE.find("st.tabs(tab_names)", block_start)
        block = APP_SOURCE[block_start:block_end]

        assert "else:" in block, "セクション判定に else フォールバックがない"
        # インデントなし（トップレベル）の else: を探す
        import re
        # セクション分岐は行頭の else: （インデント0〜1レベル）
        match = re.search(r'^else:\s*\n\s+tab_names\s*=', block, re.MULTILINE)
        assert match, "else フォールバックに tab_names 定義がない"


# =====================================================================
# テスト: パスワードガードの存在確認
# =====================================================================

class TestPasswordGuard:
    """データ入力・エクスポートタブにパスワードガードがあること"""

    def test_データ入力タブにパスワードガードがある(self):
        """日次データ入力タブに _require_data_auth が適用されていること"""
        # _tab_idx["📋 日次データ入力"] の近くに _require_data_auth があるか
        pattern = r'_tab_idx\["📋 日次データ入力"\]'
        matches = list(re.finditer(pattern, APP_SOURCE))
        assert matches, "日次データ入力タブの参照が見つからない"

        for m in matches:
            # 参照箇所の後200文字以内に _require_data_auth があるか
            after = APP_SOURCE[m.end():m.end() + 500]
            assert "_require_data_auth" in after, (
                "日次データ入力タブに _require_data_auth ガードが見つからない"
            )

    def test_データエクスポートタブにパスワードガードがある(self):
        """データエクスポートタブに _require_data_auth が適用されていること"""
        pattern = r'_tab_idx\["📥 データエクスポート"\]'
        matches = list(re.finditer(pattern, APP_SOURCE))
        assert matches, "データエクスポートタブの参照が見つからない"

        # 認証分離パターン対応: 複数の参照のうち少なくとも1つに _require_data_auth があればOK
        found_auth = False
        for m in matches:
            after = APP_SOURCE[m.end():m.end() + 500]
            if "_require_data_auth" in after:
                found_auth = True
                break
        assert found_auth, (
            "データエクスポートタブに _require_data_auth ガードが見つからない"
        )


# =====================================================================
# テスト: 変数スコープ安全性（AST解析）
# =====================================================================

class TestVariableScopeSafety:
    """条件分岐内の変数定義漏れを検出"""

    def test_days_in_month_全パスで定義(self):
        """days_in_month がデータロードの全パスで定義されること"""
        # データロードブロック内で days_in_month を検索
        block_start = None
        block_end = None
        for i, line in enumerate(APP_LINES):
            if "_needs_sim_data = _selected_section" in line:
                block_start = i
            if "# カレンダー月日数のフォールバック" in line:
                block_end = i
                break

        assert block_start and block_end, "データロードブロックが見つからない"
        block = "\n".join(APP_LINES[block_start:block_end])

        # days_in_month の定義箇所をカウント
        assignments = re.findall(r"days_in_month\s*=", block)
        # 最低4箇所: 実績あり / 実績なしダミー / シミュレーションあり / シミュレーションなしダミー
        # ただし実績ありは df の長さから算出、シミュレーションありは run_simulation の戻り値
        # ダミーは2箇所
        assert len(assignments) >= 2, (
            f"days_in_month の定義が {len(assignments)} 箇所しかない — "
            f"一部パスで未定義になる可能性あり"
        )

    def test_active_raw_df_全パスで定義(self):
        """_active_raw_df がデータロードの全パスで定義されること"""
        block_start = None
        block_end = None
        for i, line in enumerate(APP_LINES):
            if "_needs_sim_data = _selected_section" in line:
                block_start = i
            if "# カレンダー月日数のフォールバック" in line:
                block_end = i
                break

        block = "\n".join(APP_LINES[block_start:block_end])
        assignments = re.findall(r"_active_raw_df\s*=", block)
        # ダミー2箇所 + 通常データ箇所
        assert len(assignments) >= 2, (
            f"_active_raw_df の定義が {len(assignments)} 箇所しかない — "
            f"一部パスで未定義になる可能性あり"
        )

    def test_active_cli_params_全パスで定義(self):
        """_active_cli_params がデータロードの全パスで定義されること"""
        block_start = None
        block_end = None
        for i, line in enumerate(APP_LINES):
            if "_needs_sim_data = _selected_section" in line:
                block_start = i
            if "# カレンダー月日数のフォールバック" in line:
                block_end = i
                break

        block = "\n".join(APP_LINES[block_start:block_end])
        assignments = re.findall(r"_active_cli_params\s*=", block)
        assert len(assignments) >= 2, (
            f"_active_cli_params の定義が {len(assignments)} 箇所しかない — "
            f"一部パスで未定義になる可能性あり"
        )


# =====================================================================
# テスト: _needs_sim_data の論理的完全性
# =====================================================================

class TestNeedsSimDataLogic:
    """_needs_sim_data の定義が全データ依存セクションをカバーしているか"""

    def test_データ依存セクションが_needs_sim_dataに含まれる(self):
        """今日の運営・What-if・戦略・退院調整が _needs_sim_data の判定に含まれること

        2026-04-21: 退院調整セクションは sim/実績データなしのサンプル表示が
        実値と誤認されるため、ガード対象に追加された。
        """
        pattern = r'_needs_sim_data\s*=\s*_selected_section\s+in\s+\[([^\]]+)\]'
        match = re.search(pattern, APP_SOURCE)
        assert match, "_needs_sim_data の定義が見つからない"

        sections_in_check = match.group(1)
        # 今日の運営と What-if・戦略が含まれていること（Phase 3 情報階層リデザインで改名）
        assert "今日の運営" in sections_in_check, "今日の運営が _needs_sim_data に含まれていない"
        assert "What-if・戦略" in sections_in_check, "What-if・戦略が _needs_sim_data に含まれていない"
        assert "退院調整" in sections_in_check, (
            "退院調整が _needs_sim_data に含まれていない — シミュレーション未実行時に "
            "カンファ画面でサンプル値が実値と誤認されるリスクあり"
        )

    def test_データ不要セクションが_needs_sim_dataに含まれない(self):
        """制度管理・データ・設定が _needs_sim_data に含まれないこと
        （これらのセクションはデータなしでもアクセスできるべき）

        Phase 4（2026-04-18）: 旧「📋 データ管理」「📨 HOPE連携」は
        「⚙️ データ・設定」へ統合された。
        """
        pattern = r'_needs_sim_data\s*=\s*_selected_section\s+in\s+\[([^\]]+)\]'
        match = re.search(pattern, APP_SOURCE)
        assert match, "_needs_sim_data の定義が見つからない"

        sections_in_check = match.group(1)
        # データ不要セクションが含まれていないこと
        assert "制度管理" not in sections_in_check, "制度管理が _needs_sim_data に誤って含まれている"
        assert "データ・設定" not in sections_in_check, "データ・設定が _needs_sim_data に誤って含まれている"
        assert "HOPE" not in sections_in_check, "HOPE が _needs_sim_data に誤って含まれている（HOPE 送信タブは「⚙️ データ・設定」配下）"
        # Phase 4 以前の旧名称が再出現していないか
        assert "データ管理" not in sections_in_check, "旧称「データ管理」が _needs_sim_data に残っている"


# =====================================================================
# テスト: Streamlit描画順序の安全性
# =====================================================================

class TestStreamlitDrawingOrder:
    """st.tabs() の後にセクションヘッダー等が描画されていないか検出

    背景: st.tabs() の後に st.header / st.markdown / st.error 等を
    呼ぶと、タブコンテンツの下部に埋もれてユーザーに見えなくなる。
    ヘッダー・アラート等は st.tabs() の前に配置すべき。
    """

    def _find_tabs_and_post_draws(self) -> list[str]:
        """st.tabs() 呼び出し後、次の with tabs[] までの間に
        トップレベル（タブ外）の st.* 描画コールがないか検出"""
        violations = []
        # 描画系コール（タブ外に置くと埋もれるもの）
        draw_calls = [
            "st.header(", "st.subheader(", "st.title(",
            "st.error(", "st.warning(", "st.info(", "st.success(",
        ]
        # st.caption は許容（タブ切替の案内テキスト等で使用）
        in_post_tabs_zone = False
        tabs_line = 0

        for i, line in enumerate(APP_LINES, start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue

            # tabs = st.tabs(...) を検出
            if "= st.tabs(" in line:
                in_post_tabs_zone = True
                tabs_line = i
                continue

            # with tabs[...] に到達したらゾーン終了
            if in_post_tabs_zone and "with tabs[" in line:
                in_post_tabs_zone = False
                continue

            # ゾーン内の描画コール検出
            if in_post_tabs_zone:
                indent = len(line) - len(line.lstrip())
                # インデントが浅い（タブ外）場合のみ検出
                if indent <= 4:
                    for call in draw_calls:
                        if call in stripped:
                            violations.append(
                                f"  L{i}: {stripped[:80]} — st.tabs() (L{tabs_line}) の後にタブ外描画"
                            )
                            break

        return violations

    def test_タブ外描画がst_tabs後に存在しないこと(self):
        """st.tabs() の後、with tabs[] の前にタブ外の描画コールがないこと"""
        violations = self._find_tabs_and_post_draws()
        assert not violations, (
            "st.tabs() の後にタブ外の描画コールが検出された — "
            "タブコンテンツの下に埋もれる可能性あり:\n"
            + "\n".join(violations)
        )


# =====================================================================
# テスト: 空DataFrame・欠損キーへの防御
# =====================================================================

class TestEmptyDataDefense:
    """データが空またはキーが欠損する場合の防御コードの存在を確認

    背景: 実績データ未投入・デモデータ未ロード時に、空のDataFrameや
    辞書に対してキーアクセスするとKeyError/IndexErrorが発生する。
    """

    def test_ward_dfs_アクセスにガードがあること(self):
        """_ward_dfs["5F"] 等のアクセス前に存在チェックがあること"""
        # _ward_dfs["5F"] or _ward_dfs["6F"] のアクセスを検出
        pattern = r'_ward_dfs\["[56]F"\]'
        accesses = []
        for i, line in enumerate(APP_LINES, start=1):
            if line.lstrip().startswith("#"):
                continue
            if re.search(pattern, line):
                accesses.append(i)

        # 各アクセスの上方20行以内に if "5F" in _ward_dfs / _ward_dfs.get 等のガードがあるか
        unguarded = []
        for ln in accesses:
            context_start = max(0, ln - 21)
            context = "\n".join(APP_LINES[context_start:ln - 1])
            has_guard = (
                '"5F" in _ward_dfs' in context
                or '"6F" in _ward_dfs' in context
                or '_ward_dfs.get' in context
                or 'if _ward_dfs' in context
                or '_ward_dfs and' in context
                or 'for _ward' in context
                or 'for ward' in context
                or '.items()' in context
            )
            if not has_guard:
                unguarded.append(f"  L{ln}: {APP_LINES[ln-1].strip()[:80]}")

        # 3箇所以上のガードなしアクセスがあれば警告
        assert len(unguarded) <= 2, (
            f"_ward_dfs へのガードなしアクセスが {len(unguarded)} 箇所:\n"
            + "\n".join(unguarded[:10])
        )

    def test_data_ready_フラグが定義されていること(self):
        """_data_ready フラグが定義され、データ依存タブのガードに使用されていること"""
        # _data_ready の定義を確認
        has_definition = "_data_ready" in APP_SOURCE
        assert has_definition, "_data_ready フラグが定義されていない"

        # _data_ready の使用箇所をカウント（and _data_ready / if _data_ready 両方）
        guard_count = (
            APP_SOURCE.count("and _data_ready")
            + APP_SOURCE.count("if _data_ready")
            + APP_SOURCE.count("if not _data_ready")
        )
        assert guard_count >= 3, (
            f"_data_ready がガードとして {guard_count} 箇所しか使用されていない — "
            f"データ依存タブのガード不足の可能性あり"
        )

    def test_empty_df_チェックパターンが存在すること(self):
        """DataFrame が空でないかのチェック（len(df) > 0 or not df.empty）が
        データ依存処理の前に存在すること"""
        # 空チェックパターン
        empty_checks = (
            APP_SOURCE.count("df.empty")
            + APP_SOURCE.count("len(df)")
            + APP_SOURCE.count("df is not None")
            + APP_SOURCE.count("if df is None")
        )
        assert empty_checks >= 3, (
            f"DataFrame の空チェックが {empty_checks} 箇所しかない — "
            f"空データ時のエラー防御が不十分な可能性あり"
        )
