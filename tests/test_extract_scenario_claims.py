"""シナリオクレーム抽出器のユニットテスト.

カバレッジ:
- 各指標のパターンマッチ（境界値・否定ケース）
- 文脈推定（病棟・モード・データソース）
- JSON 出力整合性
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from extract_scenario_claims import (  # noqa: E402
    METRIC_META,
    SCENARIO_FILES,
    extract_all_claims,
    extract_claims_from_file,
    _infer_ward,
    _infer_mode,
    _is_plausible,
    _parse_float,
    write_claims_json,
)


# ---------------------------------------------------------------------------
# _parse_float
# ---------------------------------------------------------------------------


class TestParseFloat:
    def test_plain_integer(self):
        assert _parse_float("85") == 85.0

    def test_decimal(self):
        assert _parse_float("17.5") == 17.5

    def test_comma_separator(self):
        assert _parse_float("1,046") == 1046.0

    def test_ja_comma_separator(self):
        assert _parse_float("30，500") == 30500.0

    def test_man_format(self):
        assert _parse_float("3 万 500") == 30500.0
        assert _parse_float("3万500") == 30500.0
        assert _parse_float("1 万") == 10000.0

    def test_invalid(self):
        assert _parse_float("abc") is None
        assert _parse_float("") is None

    def test_none(self):
        assert _parse_float(None) is None


# ---------------------------------------------------------------------------
# _is_plausible（範囲ゲート）
# ---------------------------------------------------------------------------


class TestIsPlausible:
    @pytest.mark.parametrize(
        "metric,value,expected",
        [
            ("occupancy_pct", 85.0, True),
            ("occupancy_pct", 120.0, False),  # 100 % 超過
            ("occupancy_pct", -5.0, False),
            ("alos_days", 17.5, True),
            ("alos_days", 0.5, False),
            ("alos_days", 100.0, False),
            ("alos_limit_days", 21.0, True),
            ("alos_limit_days", 10.0, False),
            ("emergency_pct", 15.0, True),
            ("emergency_pct", 200.0, False),
            ("bed_total", 94.0, True),
            ("bed_total", 5.0, False),  # 病院規模として小さすぎる
            ("monthly_admissions", 150.0, True),
            ("monthly_admissions", 2.0, False),
            ("revenue_per_1pct_manyen", 1046.0, True),
            ("revenue_per_1pct_manyen", 100.0, False),
            ("friday_discharge_pct", 31.0, True),
            ("c_group_contribution_yen", 28900.0, True),
            ("c_group_contribution_yen", 500.0, False),
            ("status_count_normal", 7.0, True),
            ("status_count_normal", 100.0, False),
            ("holiday_banner_threshold_days", 21.0, True),
            ("holiday_banner_threshold_days", 999.0, False),
            # 未定義指標はデフォルト True
            ("未定義メトリック", 1.0, True),
        ],
    )
    def test_plausibility_gate(self, metric, value, expected):
        assert _is_plausible(metric, value) is expected


# ---------------------------------------------------------------------------
# 文脈推定
# ---------------------------------------------------------------------------


class TestInferWard:
    def test_5f_only(self):
        assert _infer_ward("5F は稼働率 86.5%", "") == "5F"

    def test_6f_only(self):
        assert _infer_ward("6F の救急搬送 2.6%", "") == "6F"

    def test_both_in_window(self):
        # 両方言及されると特定不能 → None
        assert _infer_ward("稼働率", "5F vs 6F の比較") is None

    def test_neither(self):
        assert _infer_ward("稼働率は高い", "週末の話") is None


class TestInferMode:
    def test_holiday_on(self):
        assert _infer_mode("連休対策モードを ON", "") == "holiday"

    def test_holiday_mention_only(self):
        # ON 文字が離れていれば normal 前提
        assert _infer_mode("連休対策モードの説明", "") == "normal"

    def test_normal_default(self):
        assert _infer_mode("普段の運用", "") == "normal"


# ---------------------------------------------------------------------------
# 個別ファイル抽出
# ---------------------------------------------------------------------------


class TestExtractFromCarnfScenario:
    @pytest.fixture(scope="class")
    def claims(self):
        path = ROOT / "docs" / "admin" / "carnf_scenario_v4.md"
        return extract_claims_from_file(path, relative_to=ROOT)

    def test_non_empty(self, claims):
        assert len(claims) >= 5

    def test_contains_occupancy(self, claims):
        occs = [c for c in claims if c.metric == "occupancy_pct"]
        assert any(c.expected_value == 86.0 for c in occs)

    def test_contains_alos_limit(self, claims):
        alos_limit = [c for c in claims if c.metric == "alos_limit_days"]
        assert any(abs(c.expected_value - 21.0) < 0.01 for c in alos_limit)

    def test_contains_holiday_threshold(self, claims):
        thresh = [c for c in claims if c.metric == "holiday_banner_threshold_days"]
        assert any(c.expected_value == 21.0 for c in thresh)

    def test_contains_status_count(self, claims):
        sc = [c for c in claims if c.metric == "status_count_normal"]
        # 7 つのステータス が必ず抽出される
        assert any(c.expected_value == 7.0 for c in sc)

    def test_source_file_format(self, claims):
        for c in claims:
            # 相対パス形式であること
            assert not c.source_file.startswith("/")
            assert c.source_file.endswith(".md")

    def test_line_numbers_valid(self, claims):
        for c in claims:
            assert c.source_line > 0


class TestExtractFromPresentationScript:
    @pytest.fixture(scope="class")
    def claims(self):
        path = ROOT / "docs" / "admin" / "presentation_script_bedcontrol_v4.md"
        return extract_claims_from_file(path, relative_to=ROOT)

    def test_contains_occupancy_target(self, claims):
        """稼働率目標 90% の抽出."""
        occ_target = [c for c in claims if c.metric == "occupancy_target_pct"]
        assert any(abs(c.expected_value - 90.0) < 0.01 for c in occ_target)

    def test_contains_emergency_threshold(self, claims):
        """救急搬送後患者割合 15% 閾値の抽出."""
        emergency_threshold = [c for c in claims if c.metric == "emergency_threshold_pct"]
        assert any(abs(c.expected_value - 15.0) < 0.01 for c in emergency_threshold)


# ---------------------------------------------------------------------------
# 統合: extract_all_claims
# ---------------------------------------------------------------------------


class TestExtractAllClaims:
    @pytest.fixture(scope="class")
    def claims(self):
        return extract_all_claims()

    def test_nonzero_total(self, claims):
        assert len(claims) >= 30, "4 台本から 30 件以上のクレームが取れること"

    def test_all_required_metrics_present(self, claims):
        """主要指標が全台本横断で 1 件以上抽出される."""
        metrics = {c.metric for c in claims}
        required = {
            "occupancy_pct",
            "alos_days",
            "emergency_pct",
            "holiday_banner_threshold_days",
        }
        assert required.issubset(metrics), f"不足: {required - metrics}"

    def test_unique_ids(self, claims):
        ids = [c.id for c in claims]
        assert len(ids) == len(set(ids)), "クレーム ID が重複"

    def test_tolerance_matches_meta(self, claims):
        """tolerance がメタデータと一致."""
        for c in claims:
            meta = METRIC_META.get(c.metric, {})
            assert c.tolerance == float(meta.get("tolerance", 1.0))

    def test_unit_matches_meta(self, claims):
        for c in claims:
            meta = METRIC_META.get(c.metric, {})
            assert c.unit == str(meta.get("unit", ""))

    def test_context_has_ward_and_mode(self, claims):
        for c in claims:
            assert "ward" in c.context
            assert "mode" in c.context
            assert "data_source" in c.context
            assert c.context["mode"] in ("normal", "holiday")
            assert c.context["data_source"] in ("demo", "actual")


# ---------------------------------------------------------------------------
# JSON 出力
# ---------------------------------------------------------------------------


class TestWriteClaimsJson:
    def test_writes_valid_json(self, tmp_path):
        claims = extract_all_claims()
        out = tmp_path / "claims.json"
        write_claims_json(claims, out)
        assert out.exists()

        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["version"] == "1.0"
        assert data["claim_count"] == len(claims)
        assert len(data["claims"]) == len(claims)
        # source_files はソート済み
        assert data["source_files"] == sorted(data["source_files"])

    def test_claim_shape(self, tmp_path):
        claims = extract_all_claims()
        if not claims:
            pytest.skip("クレームが空")
        out = tmp_path / "claims.json"
        write_claims_json(claims, out)
        data = json.loads(out.read_text(encoding="utf-8"))

        required_keys = {
            "id",
            "source_file",
            "source_line",
            "scene",
            "context",
            "claim_text",
            "metric",
            "expected_value",
            "tolerance",
            "unit",
        }
        for c in data["claims"]:
            assert required_keys.issubset(c.keys())


# ---------------------------------------------------------------------------
# 正規化・境界値
# ---------------------------------------------------------------------------


class TestBoundaryPatterns:
    """個別パターンの境界値テスト."""

    def test_occupancy_ignores_threshold_mentions(self, tmp_path):
        """「稼働率 95% 以上」のような閾値説明文は拾わない."""
        md = tmp_path / "sample.md"
        md.write_text(
            "# テスト\n稼働率 95% 以上で警告。\n稼働率 80% 以下で改善。\n",
            encoding="utf-8",
        )
        claims = extract_claims_from_file(md, relative_to=tmp_path)
        occs = [c for c in claims if c.metric == "occupancy_pct"]
        # どちらも「以上」「以下」で終わるので拾わない
        assert len(occs) == 0

    def test_occupancy_explicit_value(self, tmp_path):
        md = tmp_path / "sample.md"
        md.write_text(
            "# テスト\n5F の稼働率は 86.5%です。\n",
            encoding="utf-8",
        )
        claims = extract_claims_from_file(md, relative_to=tmp_path)
        occs = [c for c in claims if c.metric == "occupancy_pct"]
        assert len(occs) == 1
        assert occs[0].expected_value == 86.5
        assert occs[0].context["ward"] == "5F"

    def test_alos_plausibility_filter(self, tmp_path):
        """明らかに外れた ALOS は無視（ノイズガード）."""
        md = tmp_path / "sample.md"
        md.write_text(
            "# テスト\nALOS は 200 日\n",  # 非現実的な値
            encoding="utf-8",
        )
        claims = extract_claims_from_file(md, relative_to=tmp_path)
        alos = [c for c in claims if c.metric == "alos_days"]
        assert len(alos) == 0  # 範囲ゲートで弾かれる

    def test_holiday_threshold_extracts(self, tmp_path):
        md = tmp_path / "sample.md"
        md.write_text(
            "# 補章 A\n連休まで 21 日以下でバナー表示\n",
            encoding="utf-8",
        )
        claims = extract_claims_from_file(md, relative_to=tmp_path)
        thr = [c for c in claims if c.metric == "holiday_banner_threshold_days"]
        assert len(thr) >= 1

    def test_revenue_per_bed_day_from_man_notation(self, tmp_path):
        md = tmp_path / "sample.md"
        md.write_text(
            "# スライド 3\n空床 1 床は、毎日約 3 万 500 円相当の医療を届ける余力です。\n",
            encoding="utf-8",
        )
        claims = extract_claims_from_file(md, relative_to=tmp_path)
        rev = [c for c in claims if c.metric == "revenue_per_empty_bed_day_yen"]
        assert len(rev) == 1
        assert rev[0].expected_value == 30500.0

    def test_dedup_same_value_same_line(self, tmp_path):
        """同一行・同一値は 1 件にまとめる."""
        md = tmp_path / "sample.md"
        md.write_text(
            "# テスト\n稼働率 85%、稼働率 85% とも。\n",
            encoding="utf-8",
        )
        claims = extract_claims_from_file(md, relative_to=tmp_path)
        occs = [c for c in claims if c.metric == "occupancy_pct"]
        # 同じ行で 85% が 2 回出ても 1 件
        assert len(occs) == 1

    def test_status_count_7_and_4(self, tmp_path):
        md = tmp_path / "sample.md"
        md.write_text(
            "# テスト\n### 7 つのステータス（通常モード）\n### 4 つのステータス（連休対策モード）\n",
            encoding="utf-8",
        )
        claims = extract_claims_from_file(md, relative_to=tmp_path)
        sc = [c for c in claims if c.metric == "status_count_normal"]
        values = sorted(c.expected_value for c in sc)
        assert values == [4.0, 7.0]


# ---------------------------------------------------------------------------
# メタデータ整合性
# ---------------------------------------------------------------------------


class TestMetricMeta:
    def test_all_rules_have_meta(self):
        """RULES 内の全 metric が METRIC_META に定義されていること."""
        from extract_scenario_claims import RULES

        for r in RULES:
            assert r.metric in METRIC_META, f"メタ未定義: {r.metric}"

    def test_scenario_files_exist(self):
        """対象ファイルが実在する."""
        for f in SCENARIO_FILES:
            assert (ROOT / f).exists(), f"台本が見つからない: {f}"
