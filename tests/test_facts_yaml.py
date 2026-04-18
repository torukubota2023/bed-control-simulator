"""data/facts.yaml の構造検証テスト。

ベッドコントロールアプリの多職種退院調整・連休対策カンファ画面下部に
ローテーション表示するエビデンスファクト集 YAML の妥当性を検証する。

検証項目:
- YAML が正しく読み込めること
- 必須フィールドが揃っていること（``rotation_eligible`` を含む）
- PMID / DOI の形式チェック
- layer が 1-7 の範囲
- weight が 1-10 の範囲
- audience が定義済みの値のみ
- rotation_eligible=True が 12 件（副院長指示 2026-04-18）

履歴:
- 2026-04-17: version 1（25 件）
- 2026-04-18: version 2（80 件に拡充、``rotation_eligible`` 追加）
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

# 2026-04-18 拡充後の期待件数（80 件）
EXPECTED_FACT_COUNT = 80

# 副院長指示（2026-04-18）: ローテーション対象ファクトは 12 件に限定
EXPECTED_ROTATION_ELIGIBLE_COUNT = 12

# 副院長が指定した rotation_eligible=True の 12 著者（部分一致）
EXPECTED_ROTATION_AUTHORS = {
    "Valenzuela",          # 1
    "Martínez-Velilla",    # 2
    "Kato",                # 3
    "Handoll",             # 4
    "Bernabei",            # 5
    "Haas",                # 6
    "Rajendran",           # 7
    "Klassen",             # 8
    "Loyd",                # 9
    "Andrews",             # 10
    "Sawada",              # 11
    # #12 は agent 裁量（Yang / Takahashi / Nakaya 等から選定可）
}

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
    "rotation_eligible",
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
    """拡充後 80 件揃っている（副院長指示 2026-04-18）。"""
    assert len(facts) == EXPECTED_FACT_COUNT, (
        f"期待 {EXPECTED_FACT_COUNT} 件、実際 {len(facts)} 件"
    )


def test_ids_are_unique(facts):
    """id に重複がない。"""
    ids = [f["id"] for f in facts]
    duplicates = [x for x in ids if ids.count(x) > 1]
    assert not duplicates, f"id 重複: {set(duplicates)}"


def test_ids_follow_convention(facts):
    """id は f001 〜 f{N:03d} の連番（N = 総件数）。"""
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
    """PMID が null のファクトは国内論文・統計資料など。

    80 件拡充後は国内統計資料（厚労省/日本病院会/GemMed/帝国DB 等）が
    多数含まれるため、具体的な ID セットではなく
    「国内系レイヤー（4/5/7）のみに出現」を確認する。
    """
    null_pmid_facts = [f for f in facts if f["pmid"] is None]
    # PMID null は国内統計・国内論文・施設基準資料・厚労省資料など。
    # 2026-04-18 拡充後は Layer 1（地域包括医療病棟構想など厚労省資料）
    # にも含まれるため許容範囲を拡張。
    # Layer 3（リハビリ介入）と Layer 6（安全反証）は海外 RCT/Cochrane なので PMID 必須。
    DISALLOWED_NULL_PMID_LAYERS = {3, 6}
    for f in null_pmid_facts:
        assert f["layer"] not in DISALLOWED_NULL_PMID_LAYERS, (
            f"{f['id']}: Layer {f['layer']} は PMID 必須（PMID null 不可）"
        )
    # 既存 4 件（f017/f020/f024/f025）は引き続き PMID null
    existing_null_ids = {f["id"] for f in null_pmid_facts}
    for expected_id in {"f017", "f020", "f024", "f025"}:
        assert expected_id in existing_null_ids, (
            f"{expected_id}: 既存の PMID null エントリが存在しない"
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
    """各レイヤーの件数が 2026-04-18 拡充後の実態（合計 80 件）と一致する。

    旧マスター .md の分布（v1: 6/4/3/4/3/2/3）から以下の方針で拡張:
    - Layer 1（退院時機能の最適化）: +13 で 19（ローテーション対象を内包）
    - Layer 2（退院タイミング判断）: +4 で 8（国内施設基準含む）
    - Layer 3（リハビリ強度・継続）: +9 で 12
    - Layer 4（多職種カンファ）: +6 で 10（国内統計含む）
    - Layer 5（退院支援 NS）: +5 で 8
    - Layer 6（安全・反証）: +1 で 3
    - Layer 7（病棟運営・社会的文脈）: +17 で 20（国内統計メイン）
    """
    expected_counts = {1: 19, 2: 8, 3: 12, 4: 10, 5: 8, 6: 3, 7: 20}
    actual_counts: dict[int, int] = {}
    for fact in facts:
        actual_counts[fact["layer"]] = actual_counts.get(fact["layer"], 0) + 1
    assert actual_counts == expected_counts, (
        f"レイヤー件数不一致: 期待 {expected_counts}、実際 {actual_counts}"
    )
    assert sum(expected_counts.values()) == EXPECTED_FACT_COUNT, (
        f"レイヤー合計 {sum(expected_counts.values())} が "
        f"EXPECTED_FACT_COUNT {EXPECTED_FACT_COUNT} と不一致"
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
    """レイヤー 1 (退院時機能の最適化) の weight は 8-10 の高値帯。

    2026-04-18 拡充後は追加エビデンス（Boyne 2023 等）の weight が 9 のため
    8-10 の範囲を許容する。中核の 6 件（既存 f001-f006）は依然 10。
    """
    for fact in facts:
        if fact["layer"] == 1:
            w = fact["context"]["weight"]
            assert w in {8, 9, 10}, (
                f"{fact['id']}: レイヤー 1 は weight 8-10 の範囲 "
                f"(実際 {w})"
            )
    # 中核 6 件（f001-f006）は weight=10 を維持
    core_ids = {"f001", "f002", "f003", "f004", "f005", "f006"}
    for fact in facts:
        if fact["id"] in core_ids:
            assert fact["context"]["weight"] == 10, (
                f"{fact['id']}: 中核エントリは weight=10 を維持する"
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
    """レイヤー 4 (多職種カンファ) の weight は 5-7 の範囲。

    2026-04-18 拡充後は国内統計資料（GemMed 等）を weight=5 で追加したため
    5-7 を許容する。中核 4 件（f014-f017）は weight=7 を維持。
    """
    core_ids = {"f014", "f015", "f016", "f017"}
    for fact in facts:
        if fact["layer"] == 4:
            w = fact["context"]["weight"]
            assert w in {5, 6, 7}, (
                f"{fact['id']}: レイヤー 4 は weight 5-7 (実際 {w})"
            )
            if fact["id"] in core_ids:
                assert w == 7, (
                    f"{fact['id']}: レイヤー 4 中核は weight=7 維持"
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


# ---------------------------------------------------------------------------
# rotation_eligible フィールド検証（副院長指示 2026-04-18）
# ---------------------------------------------------------------------------

def test_rotation_eligible_is_boolean(facts):
    """rotation_eligible は bool 型。"""
    for fact in facts:
        val = fact.get("rotation_eligible")
        assert isinstance(val, bool), (
            f"{fact['id']}: rotation_eligible は bool ({type(val).__name__} "
            f"={val!r})"
        )


def test_rotation_eligible_count_is_12(facts):
    """ローテーション対象（rotation_eligible=True）は厳密に 12 件。

    副院長指示（2026-04-18）: 「退院調整が医学的エビデンスに反する印象を避ける」
    ため、ローテーション表示は入院延長×リハ介入×高齢者予後改善を示す
    エビデンスレベル強のもの 12 件に限定する。
    """
    rotation = [f for f in facts if f.get("rotation_eligible") is True]
    assert len(rotation) == EXPECTED_ROTATION_ELIGIBLE_COUNT, (
        f"rotation_eligible=True は {EXPECTED_ROTATION_ELIGIBLE_COUNT} 件厳守 "
        f"(実際 {len(rotation)} 件: {[r['id'] for r in rotation]})"
    )


def test_rotation_eligible_includes_required_authors(facts):
    """ローテーション対象には副院長指定の 11 著者が必ず含まれる（12 件中）。"""
    rotation = [f for f in facts if f.get("rotation_eligible") is True]
    rotation_authors = {r["author"] for r in rotation}
    # 各指定著者について、rotation_authors に前方一致する要素が少なくとも 1 つある
    for required_author in EXPECTED_ROTATION_AUTHORS:
        matches = [a for a in rotation_authors if a.startswith(required_author)]
        assert matches, (
            f"副院長指定著者 '{required_author}' が rotation_eligible=True に含まれない。"
            f" 実際のローテーション著者: {rotation_authors}"
        )


def test_rotation_eligible_layers_are_1_or_3(facts):
    """ローテーション対象は Layer 1（退院時機能の最適化）/Layer 2（退院タイミング）
    /Layer 3（リハビリ強度）のみ。

    副院長指示で「入院延長×リハ介入×高齢者予後改善」を示すエビデンスに限定
    するため、統計資料 Layer 7 や安全反証 Layer 6 等は対象外。
    Layer 2 は Handoll 2021 の「多職種リハ」が含まれるため許容。
    """
    ALLOWED_ROTATION_LAYERS = {1, 2, 3}
    for fact in facts:
        if fact.get("rotation_eligible") is True:
            assert fact["layer"] in ALLOWED_ROTATION_LAYERS, (
                f"{fact['id']}: rotation_eligible=True だが Layer "
                f"{fact['layer']} は対象外（Layer 1/2/3 のみ許容）"
            )


def test_non_rotation_eligible_examples_excluded(facts):
    """副院長が明示的に除外した代表エントリは rotation_eligible=False である。

    - Au 2019 (週末退院安全): 延長支持ではない
    - Sunkara 2020 SIBR: 多職種カンファ、運用系
    - Howlett 2026 ED: 運営系
    - Van Spall 2019 PACT-HF: 退院支援 NS 系
    - Hartley 2022: 安全性（延長支持ではない）
    - Bernhardt 2015 AVERT: 反証
    """
    excluded_patterns = [
        "Au 20",
        "Sunkara",
        "Howlett",
        "Van Spall",
        "Hartley",
        "Bernhardt",
    ]
    for pattern in excluded_patterns:
        matches = [
            f for f in facts if f["author"].startswith(pattern)
        ]
        assert matches, f"テスト前提: 著者 '{pattern}' のエントリが存在する"
        for f in matches:
            assert f.get("rotation_eligible") is False, (
                f"{f['id']} ({f['author']}): 副院長の除外指示に反して "
                f"rotation_eligible={f.get('rotation_eligible')} になっている"
            )


def test_rotation_eligible_all_have_pmid(facts):
    """ローテーション対象は全て PMID 付き（エビデンスレベル強の証）。

    国内統計・国内事例（PMID null）はローテーション対象から除外する副院長方針。
    """
    for fact in facts:
        if fact.get("rotation_eligible") is True:
            assert fact["pmid"] is not None, (
                f"{fact['id']}: rotation_eligible=True なら PMID 必須"
            )
