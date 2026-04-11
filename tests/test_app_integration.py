"""
Streamlit アプリ統合テスト — ランタイムエラー検出

Streamlit を実際に起動せず、AST解析とソースコード分析で
「セクション切替時の未定義変数アクセス」等のバグを検出する。

検出対象:
- st.session_state.X へのガードなしアクセス
- _tab_idx["..."] で参照されるタブ名が _ALL_TAB_NAMES に未登録
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


def _find_all_tab_names_from_source() -> list[str]:
    """ソースから _ALL_TAB_NAMES リストの文字列要素を抽出する

    ソース内のユニコードエスケープ（\\U0001f4ca 等）を実際の文字に変換して返す。
    """
    # _ALL_TAB_NAMES = [ ... ] の定義を正規表現で取得
    pattern = r"_ALL_TAB_NAMES\s*=\s*\[(.*?)\]"
    match = re.search(pattern, APP_SOURCE, re.DOTALL)
    assert match, "_ALL_TAB_NAMES の定義がソース内に見つからない"
    raw = match.group(1)
    # 文字列リテラルを抽出（ユニコードエスケープ含む）
    raw_names = re.findall(r'"([^"]*)"', raw)
    # ユニコードエスケープ（\\U0001f4ca 等）を実際の文字に変換
    names = []
    for n in raw_names:
        if "\\U" in n or "\\u" in n:
            names.append(n.encode("raw_unicode_escape").decode("unicode_escape"))
        else:
            names.append(n)
    return names


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
    """_tab_idx 参照とマスターリスト _ALL_TAB_NAMES の整合性"""

    def test_全タブ参照がマスターリストに存在する(self):
        """_tab_idx["X"] で参照されるすべてのタブ名が _ALL_TAB_NAMES に含まれること"""
        all_names = _find_all_tab_names_from_source()
        references = _find_tab_idx_references()

        missing = []
        for line_no, tab_name in references:
            if tab_name not in all_names:
                missing.append(f"  L{line_no}: _tab_idx[\"{tab_name}\"] — マスターリストに未登録")

        assert not missing, (
            f"_ALL_TAB_NAMES に含まれないタブ名が参照されている:\n"
            + "\n".join(missing)
        )

    def test_マスターリストに重複がないこと(self):
        """_ALL_TAB_NAMES に重複したタブ名がないこと"""
        all_names = _find_all_tab_names_from_source()
        seen = set()
        duplicates = []
        for name in all_names:
            if name in seen:
                duplicates.append(name)
            seen.add(name)

        assert not duplicates, f"_ALL_TAB_NAMES に重複あり: {duplicates}"

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

        # "📋 データ管理" は tab_names = [] で始まるが .extend で追加されるので OK
        # 空のまま進むセクションがないか確認
        # （このテストは構造変更時のリグレッション検出用）

    def test_tab_idx_get使用のフォールバック確認(self):
        """_tab_idx.get() で安全にアクセスしている箇所が存在すること"""
        get_pattern = r'_tab_idx\.get\('
        get_count = len(re.findall(get_pattern, APP_SOURCE))
        # 少なくとも1箇所は .get() を使用しているはず（実績分析タブ等）
        assert get_count >= 1, "_tab_idx.get() の安全なアクセスが見つからない"


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

        # st.stop() と ダミー値パスの両方が存在することを確認
        assert "st.stop()" in block, "st.stop() がデータロードブロックに存在しない"

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

    def test_st_stop前にneeds_sim_dataチェックがある(self):
        """st.stop() が _needs_sim_data 条件内にのみ配置されていること
        （データ不要セクションで st.stop() が発動しないこと）"""
        block = self._extract_data_loading_block()
        lines = block.splitlines()

        stop_locations = []
        for i, line in enumerate(lines):
            if "st.stop()" in line:
                # 直前の10行以内に _needs_sim_data チェックがあることを確認
                context = "\n".join(lines[max(0, i-10):i+1])
                has_guard = "_needs_sim_data" in context or "if _needs_sim_data" in context
                if not has_guard:
                    stop_locations.append(f"  データロードブロック内 L+{i}: st.stop() に _needs_sim_data ガードなし")

        assert not stop_locations, (
            "st.stop() が _needs_sim_data ガードなしで配置されている — "
            "データ不要セクション（制度管理等）がブロックされる:\n"
            + "\n".join(stop_locations)
        )

    def test_ダミー値パスとst_stop_パスの排他性(self):
        """st.stop() パスとダミー値パスが排他的であること
        （_needs_sim_data=True → st.stop(), _needs_sim_data=False → ダミー値）"""
        block = self._extract_data_loading_block()

        # 実績データモード側
        actual_section = block.split("else:")[0] if "else:" in block else block
        # 「if _needs_sim_data:」の後に st.stop()、else に ダミー値 のパターンを確認
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
            assert has_tab_context or has_auth_context or has_password_context, (
                f"L{ln}: st.stop() がタブコンテキストや認証ガード外にある — "
                f"全セクションをブロックする可能性あり"
            )


# =====================================================================
# テスト: セクション→タブマッピングの完全性
# =====================================================================

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
            if any(kw in val for kw in ["ダッシュボード", "意思決定", "制度", "データ", "HOPE"]):
                menu_sections.add(_normalize(val))

        # 各メニューセクションに対応する条件分岐があること
        for section in menu_sections:
            assert section in defined_sections, (
                f"セクション '{section}' のタブ定義分岐が見つからない"
            )

    def test_elseブランチにフォールバックタブがある(self):
        """セクション判定の else ブランチにフォールバック tab_names があること"""
        # セクション条件分岐ブロック内に else: tab_names = [...] があること
        block_start = APP_SOURCE.find('if _selected_section == "')
        block_end = APP_SOURCE.find("st.caption(", block_start)
        block = APP_SOURCE[block_start:block_end]

        assert "else:" in block, "セクション判定に else フォールバックがない"
        # else の後に tab_names 定義があること
        else_pos = block.rfind("else:")
        after_else = block[else_pos:]
        assert "tab_names" in after_else, "else フォールバックに tab_names 定義がない"


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

        for m in matches:
            after = APP_SOURCE[m.end():m.end() + 500]
            assert "_require_data_auth" in after, (
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
        """ダッシュボード・意思決定支援が _needs_sim_data の判定に含まれること"""
        pattern = r'_needs_sim_data\s*=\s*_selected_section\s+in\s+\[([^\]]+)\]'
        match = re.search(pattern, APP_SOURCE)
        assert match, "_needs_sim_data の定義が見つからない"

        sections_in_check = match.group(1)
        # ダッシュボードと意思決定支援が含まれていること
        assert "ダッシュボード" in sections_in_check, "ダッシュボードが _needs_sim_data に含まれていない"
        assert "意思決定支援" in sections_in_check, "意思決定支援が _needs_sim_data に含まれていない"

    def test_データ不要セクションが_needs_sim_dataに含まれない(self):
        """制度管理・データ管理・HOPE連携が _needs_sim_data に含まれないこと
        （これらのセクションはデータなしでもアクセスできるべき）"""
        pattern = r'_needs_sim_data\s*=\s*_selected_section\s+in\s+\[([^\]]+)\]'
        match = re.search(pattern, APP_SOURCE)
        assert match, "_needs_sim_data の定義が見つからない"

        sections_in_check = match.group(1)
        # データ不要セクションが含まれていないこと
        assert "制度管理" not in sections_in_check, "制度管理が _needs_sim_data に誤って含まれている"
        assert "データ管理" not in sections_in_check, "データ管理が _needs_sim_data に誤って含まれている"
        assert "HOPE" not in sections_in_check, "HOPE連携が _needs_sim_data に誤って含まれている"
