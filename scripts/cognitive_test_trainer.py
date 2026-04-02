# 実行方法: streamlit run scripts/cognitive_test_trainer.py
"""
認知機能検査トレーニング（高齢者運転免許向け）

運転免許更新時の認知機能検査（手がかり再生検査）を
模擬体験・反復練習できるStreamlitアプリ。
"""

import streamlit as st
import random
import time
import math
from datetime import datetime

try:
    import pandas as pd
    _PANDAS_AVAILABLE = True
except ImportError:
    _PANDAS_AVAILABLE = False

try:
    import plotly.graph_objects as go
    import plotly.express as px
    _PLOTLY_AVAILABLE = True
except ImportError:
    _PLOTLY_AVAILABLE = False

# ---------------------------------------------------------------------------
# ページ設定（最初に呼ぶ）
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="認知機能検査トレーニング",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# 文字サイズ設定（サイドバーで選択 → CSS に反映）
# ---------------------------------------------------------------------------
FONT_SIZE_PRESETS = {
    "標準": {
        "base": 18, "h1": 2.2, "h2": 1.8, "h3": 1.5,
        "btn": 1.2, "btn_pad": 0.6, "btn_h": 3,
        "tab": 1.1, "tab_pad": 0.8,
        "emoji": 3.5, "card_label": 1.2, "card_hint": 0.95,
        "score": 3, "timer": 2, "result": 1.1,
        "metric": 2, "input": 1.1, "input_pad": 0.5,
    },
    "大きめ": {
        "base": 22, "h1": 2.6, "h2": 2.2, "h3": 1.8,
        "btn": 1.5, "btn_pad": 0.8, "btn_h": 3.5,
        "tab": 1.3, "tab_pad": 1.0,
        "emoji": 4.5, "card_label": 1.5, "card_hint": 1.15,
        "score": 3.5, "timer": 2.5, "result": 1.3,
        "metric": 2.5, "input": 1.3, "input_pad": 0.6,
    },
    "特大": {
        "base": 26, "h1": 3.0, "h2": 2.5, "h3": 2.1,
        "btn": 1.8, "btn_pad": 1.0, "btn_h": 4.0,
        "tab": 1.5, "tab_pad": 1.2,
        "emoji": 5.5, "card_label": 1.8, "card_hint": 1.35,
        "score": 4.0, "timer": 3.0, "result": 1.5,
        "metric": 3.0, "input": 1.5, "input_pad": 0.7,
    },
}

if "font_size" not in st.session_state:
    st.session_state["font_size"] = "標準"

# サイドバー最上部に文字サイズ切替を配置
st.sidebar.markdown("### 🔤 文字の大きさ")
_fs_cols = st.sidebar.columns(3)
for _i, _label in enumerate(FONT_SIZE_PRESETS):
    with _fs_cols[_i]:
        if st.button(
            _label,
            key=f"fs_{_label}",
            type="primary" if st.session_state["font_size"] == _label else "secondary",
            use_container_width=True,
        ):
            st.session_state["font_size"] = _label
            st.rerun()
st.sidebar.markdown("---")

_fs = FONT_SIZE_PRESETS[st.session_state["font_size"]]

# ---------------------------------------------------------------------------
# カスタムCSS（選択された文字サイズに応じて動的生成）
# ---------------------------------------------------------------------------
st.markdown(f"""
<style>
    /* 全体のベースフォント */
    html, body, [class*="css"] {{
        font-size: {_fs['base']}px;
    }}
    /* ヘッダー類 */
    h1 {{ font-size: {_fs['h1']}rem !important; }}
    h2 {{ font-size: {_fs['h2']}rem !important; }}
    h3 {{ font-size: {_fs['h3']}rem !important; }}
    /* ボタンを大きく */
    .stButton > button {{
        font-size: {_fs['btn']}rem !important;
        padding: {_fs['btn_pad']}rem 1.5rem !important;
        min-height: {_fs['btn_h']}rem;
    }}
    /* タブのフォント */
    .stTabs [data-baseweb="tab"] {{
        font-size: {_fs['tab']}rem !important;
        padding: {_fs['tab_pad']}rem 1.2rem !important;
    }}
    /* 大きな絵文字カード */
    .emoji-card {{
        text-align: center;
        padding: 1rem;
        border-radius: 12px;
        background: #f8f9fa;
        border: 2px solid #dee2e6;
        margin: 0.3rem;
    }}
    .emoji-card .emoji {{
        font-size: {_fs['emoji']}rem;
        display: block;
        margin-bottom: 0.3rem;
    }}
    .emoji-card .label {{
        font-size: {_fs['card_label']}rem;
        font-weight: bold;
        color: #333;
    }}
    .emoji-card .hint {{
        font-size: {_fs['card_hint']}rem;
        color: #666;
    }}
    /* スコア表示 */
    .score-big {{
        font-size: {_fs['score']}rem;
        font-weight: bold;
        text-align: center;
    }}
    .score-pass {{ color: #28a745; }}
    .score-fail {{ color: #dc3545; }}
    /* タイマー */
    .timer-display {{
        font-size: {_fs['timer']}rem;
        font-weight: bold;
        text-align: center;
        padding: 0.5rem;
        border-radius: 8px;
        background: #fff3cd;
        border: 2px solid #ffc107;
        margin-bottom: 1rem;
    }}
    /* 正解/不正解 */
    .result-correct {{
        color: #28a745;
        font-weight: bold;
        font-size: {_fs['result']}rem;
    }}
    .result-incorrect {{
        color: #dc3545;
        font-weight: bold;
        font-size: {_fs['result']}rem;
    }}
    /* メトリック値を大きく */
    [data-testid="stMetricValue"] {{
        font-size: {_fs['metric']}rem !important;
    }}
    /* 入力欄を大きく */
    .stTextInput input {{
        font-size: {_fs['input']}rem !important;
        padding: {_fs['input_pad']}rem !important;
    }}
    /* --- レスポンシブ絵文字グリッド --- */
    .emoji-grid {{
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 0.5rem;
    }}
    /* iPad 縦向き (~768px) 以下は 2 列 */
    @media (max-width: 900px) {{
        .emoji-grid {{
            grid-template-columns: repeat(2, 1fr);
        }}
    }}
    /* スマホ (~480px) 以下は 1 列 */
    @media (max-width: 480px) {{
        .emoji-grid {{
            grid-template-columns: 1fr;
        }}
    }}
    /* iPad でサイドバーを折りたたみやすく */
    @media (max-width: 900px) {{
        [data-testid="stSidebar"] {{
            min-width: 0px !important;
        }}
    }}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 定数データ
# ---------------------------------------------------------------------------

CATEGORIES = [
    "戦いの武器", "楽器", "体の一部", "電気製品",
    "昆虫", "動物", "野菜", "台所用品",
    "文房具", "乗り物", "果物", "衣類",
    "鳥", "花", "大工道具", "家具",
]

PATTERNS = {
    "A": [
        "大砲", "オルガン", "耳", "ラジオ",
        "テントウムシ", "ライオン", "タケノコ", "フライパン",
        "ものさし", "オートバイ", "ブドウ", "スカート",
        "にわとり", "バラ", "ペンチ", "ベッド",
    ],
    "B": [
        "戦車", "太鼓", "目", "ステレオ",
        "トンボ", "ウサギ", "トマト", "ヤカン",
        "万年筆", "飛行機", "レモン", "コート",
        "ペンギン", "ユリ", "カナヅチ", "机",
    ],
    "C": [
        "機関銃", "琴", "親指", "電子レンジ",
        "セミ", "牛", "トウモロコシ", "ナベ",
        "ハサミ", "トラック", "メロン", "ドレス",
        "クジャク", "チューリップ", "ドライバー", "椅子",
    ],
    "D": [
        "刀", "アコーディオン", "足", "テレビ",
        "カブトムシ", "馬", "カボチャ", "包丁",
        "筆", "ヘリコプター", "パイナップル", "ズボン",
        "スズメ", "ヒマワリ", "ノコギリ", "ソファー",
    ],
}

EMOJI_MAP = {
    # Pattern A
    "大砲": "💣", "オルガン": "🎹", "耳": "👂", "ラジオ": "📻",
    "テントウムシ": "🐞", "ライオン": "🦁", "タケノコ": "🎋", "フライパン": "🍳",
    "ものさし": "📏", "オートバイ": "🏍️", "ブドウ": "🍇", "スカート": "👗",
    "にわとり": "🐔", "バラ": "🌹", "ペンチ": "🔧", "ベッド": "🛏️",
    # Pattern B
    "戦車": "🔫", "太鼓": "🥁", "目": "👁️", "ステレオ": "🔊",
    "トンボ": "🪰", "ウサギ": "🐰", "トマト": "🍅", "ヤカン": "🫖",
    "万年筆": "🖋️", "飛行機": "✈️", "レモン": "🍋", "コート": "🧥",
    "ペンギン": "🐧", "ユリ": "🌷", "カナヅチ": "🔨", "机": "🪑",
    # Pattern C
    "機関銃": "🔫", "琴": "🎵", "親指": "👍", "電子レンジ": "📡",
    "セミ": "🦗", "牛": "🐄", "トウモロコシ": "🌽", "ナベ": "🍲",
    "ハサミ": "✂️", "トラック": "🚛", "メロン": "🍈", "ドレス": "👗",
    "クジャク": "🦚", "チューリップ": "🌷", "ドライバー": "🪛", "椅子": "🪑",
    # Pattern D
    "刀": "⚔️", "アコーディオン": "🪗", "足": "🦶", "テレビ": "📺",
    "カブトムシ": "🪲", "馬": "🐴", "カボチャ": "🎃", "包丁": "🔪",
    "筆": "🖌️", "ヘリコプター": "🚁", "パイナップル": "🍍", "ズボン": "👖",
    "スズメ": "🐦", "ヒマワリ": "🌻", "ノコギリ": "🪚", "ソファー": "🛋️",
}

# ---------------------------------------------------------------------------
# ヘルパー関数
# ---------------------------------------------------------------------------

def init_session_state():
    """セッション状態の初期化"""
    defaults = {
        # テスト本番モード
        "test_phase": "not_started",  # not_started, memorize, interference, free_recall, cued_recall, result
        "test_pattern": None,
        "test_board_index": 0,
        "test_timer_start": None,
        "test_free_answers": [],
        "test_cued_answers": {},
        "test_interference_answers": [],
        "test_interference_problems": [],
        # トレーニングモード
        "train_phase": "not_started",  # not_started, memorize, interference, cued_recall, result
        "train_pattern": None,
        "train_timer_start": None,
        "train_cued_answers": {},
        # 学習記録
        "history": [],  # list of dicts
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def get_board_items(pattern_key, board_index):
    """指定パターンのボード（4アイテム）を返す"""
    items = PATTERNS[pattern_key]
    start = board_index * 4
    return items[start:start + 4]


def get_board_categories(board_index):
    """指定ボードのカテゴリヒント（4つ）を返す"""
    start = board_index * 4
    return CATEGORIES[start:start + 4]


def render_item_card(item, category, show_hint=True):
    """アイテムカードをHTMLで描画"""
    emoji = EMOJI_MAP.get(item, "❓")
    hint_html = f'<div class="hint">（{category}）</div>' if show_hint else ""
    st.markdown(
        f"""<div class="emoji-card">
            <span class="emoji">{emoji}</span>
            <div class="label">{item}</div>
            {hint_html}
        </div>""",
        unsafe_allow_html=True,
    )


def render_board(pattern_key, board_index, show_hint=True):
    """4アイテムのボードを表示（HTMLグリッド — iPad レスポンシブ対応）"""
    items = get_board_items(pattern_key, board_index)
    cats = get_board_categories(board_index)
    render_items_grid(items, cats, show_hint=show_hint)


def render_items_grid(items, categories, show_hint=True):
    """アイテム群をレスポンシブHTMLグリッドで描画"""
    cards_html = ""
    for item, cat in zip(items, categories):
        emoji = EMOJI_MAP.get(item, "❓")
        hint_html = f'<div class="hint">（{cat}）</div>' if show_hint else ""
        cards_html += (
            f'<div class="emoji-card">'
            f'<span class="emoji">{emoji}</span>'
            f'<div class="label">{item}</div>'
            f'{hint_html}'
            f'</div>'
        )
    st.markdown(f'<div class="emoji-grid">{cards_html}</div>', unsafe_allow_html=True)


def render_all_items(pattern_key, show_hint=True):
    """16アイテム全てを一覧グリッドで描画"""
    items = PATTERNS[pattern_key]
    render_items_grid(items, CATEGORIES, show_hint=show_hint)


def generate_arithmetic_problems(count=20):
    """妨害課題用の算数問題を生成"""
    problems = []
    for _ in range(count):
        op = random.choice(["+", "-"])
        if op == "+":
            a = random.randint(10, 90)
            b = random.randint(1, 99 - a)
            answer = a + b
        else:
            a = random.randint(11, 99)
            b = random.randint(1, a - 1)
            answer = a - b
        problems.append({"text": f"{a} {op} {b} = ?", "answer": answer})
    return problems


def elapsed_seconds(start_time):
    """経過秒数を返す"""
    if start_time is None:
        return 0
    return time.time() - start_time


def remaining_seconds(start_time, duration):
    """残り秒数を返す（0以上）"""
    return max(0, duration - elapsed_seconds(start_time))


def format_time(seconds):
    """秒数をMM:SS形式に変換"""
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m:02d}:{s:02d}"


def normalize_answer(text):
    """回答テキストを正規化（比較用）"""
    import unicodedata
    text = text.strip()
    text = unicodedata.normalize("NFKC", text)
    # カタカナ→ひらがな変換はしない（元データがカタカナ混在のため）
    # 全角→半角は NFKC で処理済み
    return text


def check_answer(user_answer, correct_answer):
    """回答が正しいか判定"""
    ua = normalize_answer(user_answer)
    ca = normalize_answer(correct_answer)
    if not ua:
        return False
    # 完全一致
    if ua == ca:
        return True
    # 部分一致（ユーザー入力が正解に含まれる or 逆）
    if len(ua) >= 2 and (ua in ca or ca in ua):
        return True
    return False


def calculate_test_score(pattern_key, free_answers, cued_answers):
    """
    テスト本番の採点
    - 自由再生で正解: 2点
    - 手がかり再生のみで正解: 1点
    - 満点: 32点
    - 総合点 = 2.499 * 手がかり再生スコア(0-32)
    """
    items = PATTERNS[pattern_key]
    free_correct = set()
    cued_correct = set()

    # 自由再生チェック
    for ans in free_answers:
        for idx, item in enumerate(items):
            if check_answer(ans, item):
                free_correct.add(idx)
                break

    # 手がかり再生チェック
    for idx_str, ans in cued_answers.items():
        idx = int(idx_str)
        if check_answer(ans, items[idx]):
            cued_correct.add(idx)

    # 手がかり再生のスコア（自由再生で正解したものも含む）
    all_correct = free_correct | cued_correct
    cued_score = len(all_correct)  # 0-16

    # 各アイテムの得点
    item_scores = {}
    for idx in range(16):
        if idx in free_correct:
            item_scores[idx] = 2  # 自由再生で正解
        elif idx in cued_correct:
            item_scores[idx] = 1  # 手がかり再生のみで正解
        else:
            item_scores[idx] = 0

    raw_score = sum(item_scores.values())  # 0-32
    total_score = round(2.499 * cued_score, 1)

    return {
        "free_correct": free_correct,
        "cued_correct": cued_correct,
        "all_correct": all_correct,
        "item_scores": item_scores,
        "raw_score": raw_score,
        "cued_score": cued_score,
        "total_score": total_score,
        "passed": total_score >= 36,
    }


def calculate_training_score(pattern_key, cued_answers):
    """トレーニングモードの採点"""
    items = PATTERNS[pattern_key]
    correct = set()
    for idx_str, ans in cued_answers.items():
        idx = int(idx_str)
        if check_answer(ans, items[idx]):
            correct.add(idx)
    return {
        "correct": correct,
        "score": len(correct),
        "total": 16,
        "rate": len(correct) / 16 * 100,
    }


def add_history_entry(mode, pattern_key, score_data):
    """学習記録に追加"""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "mode": mode,
        "pattern": pattern_key,
        "date": datetime.now().strftime("%m/%d %H:%M"),
    }
    if mode == "test":
        entry["raw_score"] = score_data["raw_score"]
        entry["total_score"] = score_data["total_score"]
        entry["passed"] = score_data["passed"]
        entry["correct_count"] = len(score_data["all_correct"])
        entry["item_scores"] = score_data["item_scores"]
    else:
        entry["correct_count"] = score_data["score"]
        entry["rate"] = score_data["rate"]
        entry["correct_indices"] = list(score_data["correct"])
    st.session_state.history.append(entry)


def render_timer(start_time, duration, label="残り時間"):
    """タイマー表示"""
    remaining = remaining_seconds(start_time, duration)
    st.markdown(
        f'<div class="timer-display">{label}: {format_time(remaining)}</div>',
        unsafe_allow_html=True,
    )
    progress = 1.0 - (remaining / duration) if duration > 0 else 1.0
    st.progress(min(1.0, max(0.0, progress)))
    return remaining


# ---------------------------------------------------------------------------
# サイドバー
# ---------------------------------------------------------------------------

def render_sidebar():
    """サイドバーの描画"""
    st.sidebar.title("🧠 認知機能検査トレーニング")
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        """
        **75歳以上の運転免許更新時**に実施される
        「認知機能検査（手がかり再生検査）」の
        練習アプリです。
        """
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("📋 検査の概要")
    st.sidebar.markdown(
        """
        1. **16枚の絵**を記憶する（4枚×4セット）
        2. **妨害課題**（簡単な計算問題）
        3. **自由再生**（ヒントなしで思い出す）
        4. **手がかり再生**（カテゴリヒントあり）
        """
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("📊 合格基準")
    st.sidebar.markdown(
        """
        - 総合点 **36点以上** で合格
        - 満点は約80点（16問全問正解時）
        """
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("💡 記憶のコツ")
    with st.sidebar.expander("ストーリー法", expanded=False):
        st.markdown(
            "絵をつなげてお話を作ります。"
            "例：**ライオン**が**オートバイ**に乗って"
            "**ブドウ**畑へ行き、**フライパン**で料理した。"
        )
    with st.sidebar.expander("場所法（記憶の宮殿）", expanded=False):
        st.markdown(
            "よく知っている場所（自宅など）の各部屋に"
            "絵を置いていくイメージです。"
            "玄関に**大砲**、リビングに**オルガン**..."
        )
    with st.sidebar.expander("語呂合わせ法", expanded=False):
        st.markdown(
            "頭文字を使ってリズムの良い言葉を作ります。"
            "「お（オルガン）・た（タケノコ）・ら（ライオン）・ぶ（ブドウ）」"
            "→「お寺でライブ」のように。"
        )
    with st.sidebar.expander("カテゴリ分類法", expanded=False):
        st.markdown(
            "ヒント（カテゴリ）と絵をセットで覚えます。"
            "「動物→ライオン」「果物→ブドウ」のように"
            "カテゴリから連想できるようにしましょう。"
        )

    # 練習回数
    st.sidebar.markdown("---")
    history = st.session_state.get("history", [])
    st.sidebar.metric("累計練習回数", f"{len(history)} 回")


# ---------------------------------------------------------------------------
# タブ1: テスト本番モード
# ---------------------------------------------------------------------------

def render_test_mode():
    """テスト本番モードのUI"""
    st.header("🎯 テスト本番モード")
    st.markdown("実際の認知機能検査と同じ流れで練習します。")

    phase = st.session_state.test_phase

    # ------ 開始前 ------
    if phase == "not_started":
        st.info("パターンを選んで「テスト開始」を押してください。")

        col1, col2 = st.columns([1, 2])
        with col1:
            pattern = st.selectbox(
                "出題パターン",
                ["ランダム", "A", "B", "C", "D"],
                key="test_pattern_select",
            )
        with col2:
            st.markdown("")  # spacer
            st.markdown("")
            if st.button("テスト開始", type="primary", use_container_width=True):
                if pattern == "ランダム":
                    pattern = random.choice(["A", "B", "C", "D"])
                st.session_state.test_pattern = pattern
                st.session_state.test_phase = "memorize"
                st.session_state.test_board_index = 0
                st.session_state.test_timer_start = time.time()
                st.session_state.test_free_answers = []
                st.session_state.test_cued_answers = {}
                st.session_state.test_interference_answers = []
                st.session_state.test_interference_problems = generate_arithmetic_problems(30)
                st.rerun()

        # パターンプレビュー
        st.markdown("---")
        st.subheader("各パターンの一覧（参考）")
        preview_tabs = st.tabs(["パターンA", "パターンB", "パターンC", "パターンD"])
        for i, (key, items) in enumerate(PATTERNS.items()):
            with preview_tabs[i]:
                for board_idx in range(4):
                    sub_items = items[board_idx * 4:(board_idx + 1) * 4]
                    sub_cats = CATEGORIES[board_idx * 4:(board_idx + 1) * 4]
                    cols = st.columns(4)
                    for j, (item, cat) in enumerate(zip(sub_items, sub_cats)):
                        with cols[j]:
                            emoji = EMOJI_MAP.get(item, "❓")
                            st.markdown(f"**{emoji} {item}**（{cat}）")
                    if board_idx < 3:
                        st.markdown("---")

    # ------ 記憶フェーズ ------
    elif phase == "memorize":
        pk = st.session_state.test_pattern
        board_idx = st.session_state.test_board_index
        st.subheader(f"📝 記憶フェーズ（ボード {board_idx + 1}/4） ― パターン{pk}")
        st.markdown("以下の4つの絵とカテゴリを覚えてください。")

        remaining = render_timer(st.session_state.test_timer_start, 60, "このボードの残り時間")

        render_board(pk, board_idx, show_hint=True)

        st.markdown("")
        col_a, col_b = st.columns(2)
        with col_a:
            if remaining <= 0:
                st.warning("時間切れです。次へ進んでください。")
        with col_b:
            btn_label = "次のボードへ" if board_idx < 3 else "妨害課題へ進む"
            if st.button(btn_label, type="primary", use_container_width=True):
                if board_idx < 3:
                    st.session_state.test_board_index = board_idx + 1
                    st.session_state.test_timer_start = time.time()
                else:
                    st.session_state.test_phase = "interference"
                    st.session_state.test_timer_start = time.time()
                st.rerun()

        # 自動更新（タイマー表示のため）
        if remaining > 0:
            time.sleep(1)
            st.rerun()

    # ------ 妨害課題 ------
    elif phase == "interference":
        st.subheader("🔢 妨害課題（計算問題）")
        st.markdown("簡単な計算問題を解いてください。これは記憶を妨害するための課題です。")

        remaining = render_timer(st.session_state.test_timer_start, 120, "残り時間")

        problems = st.session_state.test_interference_problems
        answers = st.session_state.test_interference_answers

        # 現在の問題番号
        current_idx = len(answers)
        if current_idx < len(problems) and remaining > 0:
            problem = problems[current_idx]
            st.markdown(f"### 問題 {current_idx + 1}: {problem['text']}")
            user_ans = st.number_input(
                "答えを入力",
                value=None,
                step=1,
                key=f"interference_{current_idx}",
                placeholder="数字を入力...",
            )
            if st.button("回答", key=f"interference_btn_{current_idx}"):
                if user_ans is not None:
                    st.session_state.test_interference_answers.append(int(user_ans))
                    st.rerun()
        elif remaining <= 0 or current_idx >= len(problems):
            st.success("妨害課題終了です。")

        col_skip, col_next = st.columns(2)
        with col_next:
            if st.button("自由再生へ進む", type="primary", use_container_width=True):
                st.session_state.test_phase = "free_recall"
                st.session_state.test_timer_start = time.time()
                st.rerun()

        # 正答率表示
        if len(answers) > 0:
            correct_count = sum(
                1 for i, a in enumerate(answers)
                if a == problems[i]["answer"]
            )
            st.caption(f"計算正答: {correct_count}/{len(answers)}")

        if remaining > 0 and current_idx < len(problems):
            time.sleep(1)
            st.rerun()

    # ------ 自由再生 ------
    elif phase == "free_recall":
        pk = st.session_state.test_pattern
        st.subheader("✏️ 自由再生（ヒントなし）")
        st.markdown("先ほど覚えた16個の絵を、思い出せるだけ書いてください。ヒントはありません。")

        remaining = render_timer(st.session_state.test_timer_start, 120, "残り時間")

        # 入力エリア
        free_text = st.text_area(
            "思い出した絵を1行に1つずつ入力してください",
            value="\n".join(st.session_state.test_free_answers),
            height=300,
            key="free_recall_input",
            placeholder="例:\nライオン\nブドウ\nオートバイ",
        )

        col1, col2 = st.columns(2)
        with col1:
            entered = [line.strip() for line in free_text.split("\n") if line.strip()]
            st.caption(f"入力済み: {len(entered)} 個 / 16個")
        with col2:
            if st.button("手がかり再生へ進む", type="primary", use_container_width=True):
                st.session_state.test_free_answers = entered
                st.session_state.test_phase = "cued_recall"
                st.session_state.test_timer_start = time.time()
                st.rerun()

        if remaining > 0:
            time.sleep(1)
            st.rerun()

    # ------ 手がかり再生 ------
    elif phase == "cued_recall":
        pk = st.session_state.test_pattern
        st.subheader("🔑 手がかり再生（カテゴリヒントあり）")
        st.markdown("カテゴリ（ヒント）を見て、それぞれの絵を思い出してください。")

        remaining = render_timer(st.session_state.test_timer_start, 120, "残り時間")

        # 16カテゴリをリスト形式で入力（iPad対応）
        for idx in range(16):
            cat = CATEGORIES[idx]
            cols = st.columns([1, 2])
            with cols[0]:
                st.markdown(f"**{idx+1}. {cat}**")
            with cols[1]:
                ans = st.text_input(
                    f"{cat}の答え",
                    value=st.session_state.test_cued_answers.get(str(idx), ""),
                    key=f"cued_{idx}",
                    label_visibility="collapsed",
                    placeholder=f"{cat}は？",
                )
                st.session_state.test_cued_answers[str(idx)] = ans

        st.markdown("")
        if st.button("採点する", type="primary", use_container_width=True):
            st.session_state.test_phase = "result"
            st.rerun()

        if remaining > 0:
            time.sleep(1)
            st.rerun()

    # ------ 採点結果 ------
    elif phase == "result":
        pk = st.session_state.test_pattern
        items = PATTERNS[pk]
        score = calculate_test_score(
            pk,
            st.session_state.test_free_answers,
            st.session_state.test_cued_answers,
        )

        st.subheader(f"📊 採点結果（パターン{pk}）")

        # 合否判定
        if score["passed"]:
            st.markdown(
                f'<div class="score-big score-pass">総合点: {score["total_score"]}点 ― 合格</div>',
                unsafe_allow_html=True,
            )
            st.balloons()
        else:
            st.markdown(
                f'<div class="score-big score-fail">総合点: {score["total_score"]}点 ― 不合格（36点以上で合格）</div>',
                unsafe_allow_html=True,
            )

        st.markdown("")

        # スコア内訳
        col_m1, col_m2 = st.columns(2)
        col_m1.metric("自由再生 正解", f"{len(score['free_correct'])} / 16")
        col_m2.metric("手がかり再生 正解", f"{len(score['cued_correct'])} / 16")
        col_m3, col_m4 = st.columns(2)
        col_m3.metric("合計正解数", f"{len(score['all_correct'])} / 16")
        col_m4.metric("素点", f"{score['raw_score']} / 32")

        st.markdown("---")

        # 各アイテム詳細（HTMLグリッドで iPad 対応）
        st.subheader("各アイテムの結果")
        result_cards = ""
        for idx in range(16):
            item = PATTERNS[pk][idx]
            cat = CATEGORIES[idx]
            emoji = EMOJI_MAP.get(item, "❓")
            pts = score["item_scores"][idx]
            if pts == 2:
                result_cards += (
                    f'<div class="emoji-card" style="border-color:#28a745;">'
                    f'<span class="emoji">{emoji}</span>'
                    f'<div class="result-correct">{item}（{cat}）<br>⭕ 自由再生で正解 [2点]</div>'
                    f'</div>'
                )
            elif pts == 1:
                result_cards += (
                    f'<div class="emoji-card" style="border-color:#ffc107;">'
                    f'<span class="emoji">{emoji}</span>'
                    f'<div class="result-correct">{item}（{cat}）<br>🔺 手がかり再生で正解 [1点]</div>'
                    f'</div>'
                )
            else:
                result_cards += (
                    f'<div class="emoji-card" style="border-color:#dc3545;">'
                    f'<span class="emoji">{emoji}</span>'
                    f'<div class="result-incorrect">{item}（{cat}）<br>❌ 不正解 [0点]</div>'
                    f'</div>'
                )
        st.markdown(f'<div class="emoji-grid">{result_cards}</div>', unsafe_allow_html=True)

        # 履歴追加
        add_history_entry("test", pk, score)

        st.markdown("---")
        if st.button("もう一度テストする", type="primary", use_container_width=True):
            st.session_state.test_phase = "not_started"
            st.session_state.test_pattern = None
            st.session_state.test_board_index = 0
            st.session_state.test_free_answers = []
            st.session_state.test_cued_answers = {}
            st.rerun()


# ---------------------------------------------------------------------------
# タブ2: 毎日5分トレーニング
# ---------------------------------------------------------------------------

def render_training_mode():
    """毎日5分トレーニングモードのUI"""
    st.header("💪 毎日5分トレーニング")
    st.markdown("短時間で手軽に記憶力を鍛えましょう。カテゴリヒント付きで回答します。")

    phase = st.session_state.train_phase

    # ------ 開始前 ------
    if phase == "not_started":
        st.info("ボタンを押すとランダムなパターンで練習が始まります。")
        if st.button("トレーニング開始", type="primary", use_container_width=True):
            pk = random.choice(["A", "B", "C", "D"])
            st.session_state.train_pattern = pk
            st.session_state.train_phase = "memorize"
            st.session_state.train_timer_start = time.time()
            st.session_state.train_cued_answers = {}
            st.rerun()

    # ------ 記憶フェーズ（全16枚一覧） ------
    elif phase == "memorize":
        pk = st.session_state.train_pattern
        st.subheader(f"📝 記憶フェーズ ― パターン{pk}")
        st.markdown("以下の16個の絵とカテゴリをできるだけ覚えてください。")

        remaining = render_timer(st.session_state.train_timer_start, 120, "残り時間")

        render_all_items(pk, show_hint=True)

        st.markdown("")
        if st.button("覚えた！妨害課題へ", type="primary", use_container_width=True):
            st.session_state.train_phase = "interference"
            st.session_state.train_timer_start = time.time()
            st.session_state.train_interference_problems = generate_arithmetic_problems(15)
            st.session_state.train_interference_answers = []
            st.rerun()

        if remaining > 0:
            time.sleep(1)
            st.rerun()

    # ------ 妨害課題（30秒） ------
    elif phase == "interference":
        st.subheader("🔢 妨害課題（計算問題）")

        remaining = render_timer(st.session_state.train_timer_start, 30, "残り時間")

        problems = st.session_state.train_interference_problems
        answers = st.session_state.get("train_interference_answers", [])
        current_idx = len(answers)

        if current_idx < len(problems) and remaining > 0:
            problem = problems[current_idx]
            st.markdown(f"### {problem['text']}")
            user_ans = st.number_input(
                "答え", value=None, step=1,
                key=f"train_interf_{current_idx}",
                placeholder="数字を入力...",
            )
            if st.button("回答", key=f"train_interf_btn_{current_idx}"):
                if user_ans is not None:
                    if "train_interference_answers" not in st.session_state:
                        st.session_state.train_interference_answers = []
                    st.session_state.train_interference_answers.append(int(user_ans))
                    st.rerun()

        if remaining <= 0 or current_idx >= len(problems):
            st.success("妨害課題終了！")

        if st.button("手がかり再生へ", type="primary", use_container_width=True):
            st.session_state.train_phase = "cued_recall"
            st.session_state.train_timer_start = time.time()
            st.rerun()

        if remaining > 0 and current_idx < len(problems):
            time.sleep(1)
            st.rerun()

    # ------ 手がかり再生 ------
    elif phase == "cued_recall":
        pk = st.session_state.train_pattern
        st.subheader("🔑 手がかり再生")
        st.markdown("カテゴリヒントを見て、思い出してください。")

        remaining = render_timer(st.session_state.train_timer_start, 120, "残り時間")

        for idx in range(16):
            cat = CATEGORIES[idx]
            cols = st.columns([1, 2])
            with cols[0]:
                st.markdown(f"**{idx+1}. {cat}**")
            with cols[1]:
                ans = st.text_input(
                    f"{cat}",
                    value=st.session_state.train_cued_answers.get(str(idx), ""),
                    key=f"train_cued_{idx}",
                    label_visibility="collapsed",
                    placeholder=f"{cat}は？",
                )
                st.session_state.train_cued_answers[str(idx)] = ans

        if st.button("採点する", type="primary", use_container_width=True):
            st.session_state.train_phase = "result"
            st.rerun()

        if remaining > 0:
            time.sleep(1)
            st.rerun()

    # ------ 結果 ------
    elif phase == "result":
        pk = st.session_state.train_pattern
        items = PATTERNS[pk]
        score = calculate_training_score(pk, st.session_state.train_cued_answers)

        st.subheader(f"📊 結果（パターン{pk}）")

        # スコア
        rate = score["rate"]
        if rate >= 80:
            color_class = "score-pass"
            comment = "素晴らしい！この調子で続けましょう。"
        elif rate >= 50:
            color_class = "score-pass"
            comment = "良い成績です。苦手なカテゴリを重点的に覚えましょう。"
        else:
            color_class = "score-fail"
            comment = "繰り返し練習すれば必ず覚えられます。頑張りましょう！"

        st.markdown(
            f'<div class="score-big {color_class}">'
            f'{score["score"]} / {score["total"]} 正解（{rate:.0f}%）</div>',
            unsafe_allow_html=True,
        )
        st.markdown(f"**{comment}**")
        st.markdown("---")

        # 各アイテム詳細（HTMLグリッドで iPad 対応）
        st.subheader("各アイテムの結果")
        result_cards = ""
        for idx in range(16):
            item = items[idx]
            cat = CATEGORIES[idx]
            emoji = EMOJI_MAP.get(item, "❓")
            is_correct = idx in score["correct"]
            user_ans = st.session_state.train_cued_answers.get(str(idx), "")
            if is_correct:
                result_cards += (
                    f'<div class="emoji-card" style="border-color:#28a745;">'
                    f'<span class="emoji">{emoji}</span>'
                    f'<div class="result-correct">{item}（{cat}）<br>⭕ 正解</div>'
                    f'</div>'
                )
            else:
                display_ans = user_ans if user_ans else "（未回答）"
                result_cards += (
                    f'<div class="emoji-card" style="border-color:#dc3545;">'
                    f'<span class="emoji">{emoji}</span>'
                    f'<div class="result-incorrect">{item}（{cat}）<br>❌ あなたの回答: {display_ans}</div>'
                    f'</div>'
                )
        st.markdown(f'<div class="emoji-grid">{result_cards}</div>', unsafe_allow_html=True)

        add_history_entry("training", pk, score)

        st.markdown("---")
        if st.button("もう一度トレーニングする", type="primary", use_container_width=True):
            st.session_state.train_phase = "not_started"
            st.session_state.train_pattern = None
            st.session_state.train_cued_answers = {}
            st.rerun()


# ---------------------------------------------------------------------------
# タブ3: 学習記録
# ---------------------------------------------------------------------------

def render_progress():
    """学習記録の表示"""
    st.header("📊 学習記録")

    history = st.session_state.get("history", [])

    if not history:
        st.info("まだ練習記録がありません。テスト本番モードまたはトレーニングモードで練習してみましょう！")
        return

    # 概要メトリクス
    test_entries = [h for h in history if h["mode"] == "test"]
    train_entries = [h for h in history if h["mode"] == "training"]

    col1, col2 = st.columns(2)
    col1.metric("総練習回数", f"{len(history)} 回")
    col2.metric("テスト本番", f"{len(test_entries)} 回")
    col3, col4 = st.columns(2)
    col3.metric("トレーニング", f"{len(train_entries)} 回")

    if test_entries:
        latest_score = test_entries[-1].get("total_score", 0)
        col4.metric("最新テスト総合点", f"{latest_score} 点")
    elif train_entries:
        latest_rate = train_entries[-1].get("rate", 0)
        col4.metric("最新トレーニング正答率", f"{latest_rate:.0f}%")

    st.markdown("---")

    # スコア推移グラフ
    if _PLOTLY_AVAILABLE and len(history) >= 2:
        st.subheader("スコア推移")

        # テスト本番のスコア推移
        if test_entries:
            fig = go.Figure()
            dates = [e["date"] for e in test_entries]
            scores = [e.get("total_score", 0) for e in test_entries]
            fig.add_trace(go.Scatter(
                x=list(range(1, len(dates) + 1)),
                y=scores,
                mode="lines+markers",
                name="テスト総合点",
                line=dict(color="#1f77b4", width=3),
                marker=dict(size=10),
                text=dates,
                hovertemplate="回数: %{x}<br>総合点: %{y}点<br>日時: %{text}<extra></extra>",
            ))
            fig.add_hline(y=36, line_dash="dash", line_color="red",
                          annotation_text="合格ライン（36点）")
            fig.update_layout(
                title="テスト本番 ― 総合点の推移",
                xaxis_title="テスト回数",
                yaxis_title="総合点",
                yaxis=dict(range=[0, 85]),
                height=350,
            )
            st.plotly_chart(fig, use_container_width=True)

        # トレーニングのスコア推移
        if train_entries:
            fig2 = go.Figure()
            dates2 = [e["date"] for e in train_entries]
            rates = [e.get("rate", 0) for e in train_entries]
            fig2.add_trace(go.Scatter(
                x=list(range(1, len(dates2) + 1)),
                y=rates,
                mode="lines+markers",
                name="正答率",
                line=dict(color="#2ca02c", width=3),
                marker=dict(size=10),
                text=dates2,
                hovertemplate="回数: %{x}<br>正答率: %{y:.0f}%<br>日時: %{text}<extra></extra>",
            ))
            fig2.add_hline(y=80, line_dash="dash", line_color="green",
                           annotation_text="目標（80%）")
            fig2.update_layout(
                title="トレーニング ― 正答率の推移",
                xaxis_title="トレーニング回数",
                yaxis_title="正答率 (%)",
                yaxis=dict(range=[0, 105]),
                height=350,
            )
            st.plotly_chart(fig2, use_container_width=True)

    st.markdown("---")

    # カテゴリ別正答分析
    st.subheader("カテゴリ別の苦手分析")

    # 全練習からカテゴリ別正答率を集計
    category_stats = {cat: {"attempts": 0, "correct": 0} for cat in CATEGORIES}

    for entry in history:
        pk = entry.get("pattern")
        if pk is None:
            continue
        if entry["mode"] == "test":
            item_scores = entry.get("item_scores", {})
            for idx in range(16):
                cat = CATEGORIES[idx]
                category_stats[cat]["attempts"] += 1
                if item_scores.get(idx, item_scores.get(str(idx), 0)) > 0:
                    category_stats[cat]["correct"] += 1
        elif entry["mode"] == "training":
            correct_indices = entry.get("correct_indices", [])
            for idx in range(16):
                cat = CATEGORIES[idx]
                category_stats[cat]["attempts"] += 1
                if idx in correct_indices:
                    category_stats[cat]["correct"] += 1

    if any(v["attempts"] > 0 for v in category_stats.values()):
        rows = []
        for cat in CATEGORIES:
            s = category_stats[cat]
            if s["attempts"] > 0:
                rate = s["correct"] / s["attempts"] * 100
                rows.append({
                    "カテゴリ": cat,
                    "挑戦回数": s["attempts"],
                    "正解回数": s["correct"],
                    "正答率(%)": round(rate, 1),
                })

        if rows and _PANDAS_AVAILABLE:
            df = pd.DataFrame(rows)
            df = df.sort_values("正答率(%)", ascending=True)

            # 苦手カテゴリ（正答率が低い順にハイライト）
            weak = df[df["正答率(%)"] < 70]
            if not weak.empty:
                st.warning(
                    f"苦手カテゴリ: {', '.join(weak['カテゴリ'].tolist())} "
                    f"（正答率70%未満）"
                )

            # バーチャート
            if _PLOTLY_AVAILABLE:
                fig3 = go.Figure()
                colors = ["#dc3545" if r < 50 else "#ffc107" if r < 70 else "#28a745"
                          for r in df["正答率(%)"].values]
                fig3.add_trace(go.Bar(
                    x=df["カテゴリ"],
                    y=df["正答率(%)"],
                    marker_color=colors,
                    text=[f"{r:.0f}%" for r in df["正答率(%)"].values],
                    textposition="outside",
                ))
                fig3.update_layout(
                    title="カテゴリ別正答率",
                    xaxis_title="カテゴリ",
                    yaxis_title="正答率 (%)",
                    yaxis=dict(range=[0, 110]),
                    height=400,
                )
                st.plotly_chart(fig3, use_container_width=True)
            else:
                st.dataframe(df, use_container_width=True)
    else:
        st.caption("まだデータがありません。")

    st.markdown("---")

    # 練習履歴テーブル
    st.subheader("練習履歴")
    if _PANDAS_AVAILABLE:
        history_rows = []
        for entry in reversed(history):
            row = {
                "日時": entry.get("date", ""),
                "モード": "テスト本番" if entry["mode"] == "test" else "トレーニング",
                "パターン": entry.get("pattern", ""),
            }
            if entry["mode"] == "test":
                row["正解数"] = f'{entry.get("correct_count", 0)}/16'
                row["総合点"] = entry.get("total_score", "")
                row["合否"] = "合格" if entry.get("passed") else "不合格"
            else:
                row["正解数"] = f'{entry.get("correct_count", 0)}/16'
                row["総合点"] = "-"
                row["合否"] = f'{entry.get("rate", 0):.0f}%'
            history_rows.append(row)
        st.dataframe(pd.DataFrame(history_rows), use_container_width=True)

    st.markdown("---")

    # 記録クリア
    if st.button("学習記録をすべてクリア", type="secondary"):
        st.session_state.history = []
        st.rerun()


# ---------------------------------------------------------------------------
# メインアプリ
# ---------------------------------------------------------------------------

def main():
    """メインエントリポイント"""
    init_session_state()
    render_sidebar()

    st.title("🧠 認知機能検査トレーニング")
    st.markdown(
        "75歳以上の運転免許更新時に行われる**認知機能検査（手がかり再生検査）**の練習アプリです。"
        "繰り返し練習して、検査本番に備えましょう。"
    )

    tab1, tab2, tab3 = st.tabs([
        "🎯 テスト本番モード",
        "💪 毎日5分トレーニング",
        "📊 学習記録",
    ])

    with tab1:
        render_test_mode()

    with tab2:
        render_training_mode()

    with tab3:
        render_progress()


if __name__ == "__main__":
    main()
