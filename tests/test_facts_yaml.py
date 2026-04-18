"""data/facts.yaml の構造検証テスト。

ベッドコントロールアプリの多職種退院調整・連休対策カンファ画面下部に
ローテーション表示するエビデンスファクト集 YAML の妥当性を検証する。

検証項目:
- YAML が正しく読み込めること
- 25 件すべて必須フィールドが揃っていること
- PMID / DOI の形式チェック
- layer が 1-7 の範囲
- weight が 1-10 の範囲
- audience が定義済みの値のみ
"""

import re
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

FACTS_YAML_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "facts.yaml"
)

EXPECTED_FACT_COUNT = 25

VALID_LAYERS = {1, 2, 3, 4, 5, 6, 7}

VALID_LAYER_NAMES = {
    1: "退院時機能の最適化",
    2: "退院タイミング判断",
    3: "リハビリの時間・強度・継続",
    4: "多職種カンファ・連携の力",
    5: "退院支援看護師の専門性",
    6: "安全・既成概念の解除",
    7: "病棟運営・社会的文脈",
}

VALID_WARDS = {"5F", "6F"}
VALID_MODES = {"normal", "holiday"}
VALID_AUDIENCES = {"all", "rehab", "discharge_ns", "doctor", "nurse"}

REQUIRED_TOP_FIELDS = {"version", "updated", "facts"}
REQUIRED_FACT_FIELDS = {
    "id",
    "layer",
    "layer_name",
    "text",
    "author",
    "journal",
    "year",
    "n",
    "pmid",
    "doi",
    "context",
}
REQUIRED_CONTEXT_FIELDS = {"wards", "modes", "audience", "weight"}

# PMID は 1 桁以上の数字
PMID_PATTERN = re.compile(r"^\d{1,9}$")
# DOI は 10. で始まりスラッシュを含む標準形式
DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$")


# ---------------------------------------------------------------------------
# フィクスチャ
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def facts_data():
    """facts.yaml を読み込む（モジュール内キャッシュ）。"""
    assert FACTS_YAML_PATH.exists(), f"YAML が存在しない: {FACTS_YAML_PATH}"
    with FACTS_YAML_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.fixture(scope="module")
def facts(facts_data):
    """facts リストだけ取り出す。"""
    return facts_data["facts"]


# ---------------------------------------------------------------------------
# 基本読み込み
# ---------------------------------------------------------------------------

def test_yaml_loads(facts_data):
    """YAML として読み込める。"""
    assert isinstance(facts_data, dict)


def test_top_level_fields_present(facts_data):
    """トップレベルに version / updated / facts が揃っている。"""
    missing = REQUIRED_TOP_FIELDS - set(facts_data.keys())
    assert not missing, f"トップレベル必須フィールド欠落: {missing}"


def test_version_is_integer(facts_data):
    """version は整数。"""
    assert isinstance(facts_data["version"], int)
    assert facts_data["version"] >= 1


def test_updated_is_date_string(facts_data):
    """updated は日付として読み込まれる (YAML は YYYY-MM-DD を date 型に変換)。"""
    from datetime import date
    assert isinstance(facts_data["updated"], (str, date)), (
        f"updated は str または date であるべき: {type(facts_data['updated'])}"
    )


# ---------------------------------------------------------------------------
# 件数
# ---------------------------------------------------------------------------

def test_expected_fact_count(facts):
    """25 件揃っている。"""
    assert len(facts) == EXPECTED_FACT_COUNT, (
        f"期待 {EXPECTED_FACT_COUNT} 件、実際 {len(facts)} 件"
    )


def test_ids_are_unique(facts):
    """id に重複がない。"""
    ids = [f["id"] for f in facts]
    duplicates = [x for x in ids if ids.count(x) > 1]
    assert not duplicates, f"id 重複: {set(duplicates)}"


def test_ids_follow_convention(facts):
    """id は f001 〜 f025 の連番。"""
    ids = [f["id"] for f in facts]
    expected = [f"f{i:03d}" for i in range(1, EXPECTED_FACT_COUNT + 1)]
    assert ids == expected, f"id 連番不一致: {ids}"


# ---------------------------------------------------------------------------
# 必須フィールド
# ---------------------------------------------------------------------------

def test_all_facts_have_required_fields(facts):
    """すべてのファクトに必須フィールドが揃っている。"""
    for fact in facts:
        missing = REQUIRED_FACT_FIELDS - set(fact.keys())
        assert not missing, f"{fact.get('id')}: 必須フィールド欠落 {missing}"


def test_all_facts_have_context_fields(facts):
    """すべてのファクトの context に必須サブフィールドが揃っている。"""
    for fact in facts:
        ctx = fact["context"]
        missing = REQUIRED_CONTEXT_FIELDS - set(ctx.keys())
        assert not missing, f"{fact['id']}: context に {missing} が欠落"


# ---------------------------------------------------------------------------
# テキスト内容
# ---------------------------------------------------------------------------

def test_text_is_nonempty(facts):
    """text が空でない。"""
    for fact in facts:
        assert fact["text"], f"{fact['id']}: text が空"
        assert isinstance(fact["text"], str)


def test_text_length_reasonable(facts):
    """text は 20〜200 字程度（画面 1 行表示用）。"""
    for fact in facts:
        length = len(fact["text"])
        assert 20 <= length <= 200, (
            f"{fact['id']}: text 長 {length} 字は範囲外 (20-200 字)"
        )


def test_author_and_journal_nonempty(facts):
    """author / journal が空でない。"""
    for fact in facts:
        assert fact["author"], f"{fact['id']}: author が空"
        assert fact["journal"], f"{fact['id']}: journal が空"


def test_year_is_reasonable_integer(facts):
    """year は 2010〜2026 の整数。"""
    for fact in facts:
        year = fact["year"]
        assert isinstance(year, int), f"{fact['id']}: year が int でない"
        assert 2010 <= year <= 2027, (
            f"{fact['id']}: year={year} が範囲外"
        )


# ---------------------------------------------------------------------------
# PMID / DOI 形式
# ---------------------------------------------------------------------------

def test_pmid_format(facts):
    """PMID は数字のみ、または null (国内論文・統計資料)。"""
    for fact in facts:
        pmid = fact["pmid"]
        if pmid is None:
            continue
        assert isinstance(pmid, str), (
            f"{fact['id']}: PMID は str または null にする ({pmid!r})"
        )
        assert PMID_PATTERN.match(pmid), (
            f"{fact['id']}: PMID 形式不正 {pmid!r}"
        )


def test_doi_format(facts):
    """DOI は 10.xxxx/yyy 形式、または null。"""
    for fact in facts:
        doi = fact["doi"]
        if doi is None:
            continue
        assert isinstance(doi, str), f"{fact['id']}: DOI が str でない"
        assert DOI_PATTERN.match(doi), (
            f"{fact['id']}: DOI 形式不正 {doi!r}"
        )


def test_pmid_and_doi_consistency(facts):
    """PMID が null のファクトは国内論文・統計資料 (DOI も null が多い)。"""
    null_pmid_ids = [f["id"] for f in facts if f["pmid"] is None]
    # マスター上、国内論文 (f017 f020) と国内統計 (f024 f025) は PMID なし
    assert set(null_pmid_ids) == {"f017", "f020", "f024", "f025"}, (
        f"PMID null のファクトが想定外: {null_pmid_ids}"
    )


# ---------------------------------------------------------------------------
# layer / layer_name
# ---------------------------------------------------------------------------

def test_layer_in_range(facts):
    """layer は 1-7。"""
    for fact in facts:
        assert fact["layer"] in VALID_LAYERS, (
            f"{fact['id']}: layer={fact['layer']} が範囲外"
        )


def test_layer_name_matches_layer(facts):
    """layer_name が layer と一致する。"""
    for fact in facts:
        expected_name = VALID_LAYER_NAMES[fact["layer"]]
        assert fact["layer_name"] == expected_name, (
            f"{fact['id']}: layer {fact['layer']} の名前が不一致 "
            f"(期待 {expected_name!r}、実際 {fact['layer_name']!r})"
        )


def test_layer_distribution(facts):
    """各レイヤーの件数がマスター .md と一致する。"""
    expected_counts = {1: 6, 2: 4, 3: 3, 4: 4, 5: 3, 6: 2, 7: 3}
    actual_counts: dict[int, int] = {}
    for fact in facts:
        actual_counts[fact["layer"]] = actual_counts.get(fact["layer"], 0) + 1
    assert actual_counts == expected_counts, (
        f"レイヤー件数不一致: 期待 {expected_counts}、実際 {actual_counts}"
    )


# ---------------------------------------------------------------------------
# context フィールド
# ---------------------------------------------------------------------------

def test_wards_valid(facts):
    """wards に 5F / 6F 以外の値がない。"""
    for fact in facts:
        wards = fact["context"]["wards"]
        assert isinstance(wards, list)
        assert wards, f"{fact['id']}: wards が空"
        invalid = set(wards) - VALID_WARDS
        assert not invalid, f"{fact['id']}: 未定義の ward {invalid}"


def test_modes_valid(facts):
    """modes が normal / holiday のみ。"""
    for fact in facts:
        modes = fact["context"]["modes"]
        assert isinstance(modes, list)
        assert modes, f"{fact['id']}: modes が空"
        invalid = set(modes) - VALID_MODES
        assert not invalid, f"{fact['id']}: 未定義の mode {invalid}"


def test_audience_valid(facts):
    """audience が定義済みの値のみ。"""
    for fact in facts:
        audience = fact["context"]["audience"]
        assert isinstance(audience, list)
        assert audience, f"{fact['id']}: audience が空"
        invalid = set(audience) - VALID_AUDIENCES
        assert not invalid, f"{fact['id']}: 未定義の audience {invalid}"


def test_weight_in_range(facts):
    """weight が 1-10 の整数。"""
    for fact in facts:
        weight = fact["context"]["weight"]
        assert isinstance(weight, int), (
            f"{fact['id']}: weight が int でない ({weight!r})"
        )
        assert 1 <= weight <= 10, (
            f"{fact['id']}: weight={weight} が範囲外"
        )


# ---------------------------------------------------------------------------
# 重み付け指針の検証 (マスター .md の状況連動ロジックに沿った期待値)
# ---------------------------------------------------------------------------

def test_layer1_is_highest_weight(facts):
    """レイヤー 1 (退院時機能の最適化) の weight=10。"""
    for fact in facts:
        if fact["layer"] == 1:
            assert fact["context"]["weight"] == 10, (
                f"{fact['id']}: レイヤー 1 は weight=10 にする "
                f"(実際 {fact['context']['weight']})"
            )


def test_layer2_weight(facts):
    """レイヤー 2 (退院タイミング) の weight は 8 または 9 (連休特化)。"""
    for fact in facts:
        if fact["layer"] == 2:
            w = fact["context"]["weight"]
            assert w in {8, 9}, (
                f"{fact['id']}: レイヤー 2 は weight 8 or 9 にする (実際 {w})"
            )


def test_layer4_weight(facts):
    """レイヤー 4 (多職種カンファ) の weight=7。"""
    for fact in facts:
        if fact["layer"] == 4:
            assert fact["context"]["weight"] == 7, (
                f"{fact['id']}: レイヤー 4 は weight=7 にする "
                f"(実際 {fact['context']['weight']})"
            )


def test_layer7_weight(facts):
    """レイヤー 7 (病棟運営・社会文脈) の weight=4。"""
    for fact in facts:
        if fact["layer"] == 7:
            assert fact["context"]["weight"] == 4, (
                f"{fact['id']}: レイヤー 7 は weight=4 にする "
                f"(実際 {fact['context']['weight']})"
            )


def test_handoll_2021_is_5F_only(facts):
    """Handoll 2021 (大腿骨骨折) は 5F 限定。"""
    handoll = next(f for f in facts if f["author"].startswith("Handoll"))
    assert handoll["context"]["wards"] == ["5F"], (
        f"Handoll 2021 は wards=[5F] にする (実際 {handoll['context']['wards']})"
    )


def test_boutera_2026_is_5F_only(facts):
    """Boutera 2026 (大腿骨骨折週末退院) は 5F 限定。"""
    boutera = next(f for f in facts if f["author"].startswith("Boutera"))
    assert boutera["context"]["wards"] == ["5F"], (
        f"Boutera 2026 は wards=[5F] にする "
        f"(実際 {boutera['context']['wards']})"
    )


def test_considine_2018_is_holiday_focused(facts):
    """Considine 2018 (金曜退院痛み主因) は連休モード特化で weight=9。"""
    considine = next(f for f in facts if f["author"].startswith("Considine"))
    assert "holiday" in considine["context"]["modes"], (
        f"Considine 2018 は modes に holiday を含む "
        f"(実際 {considine['context']['modes']})"
    )
    assert considine["context"]["weight"] == 9, (
        f"Considine 2018 は weight=9 (実際 {considine['context']['weight']})"
    )
