#!/usr/bin/env python3
"""シナリオ台本から「数値主張」を抽出して JSON 化するツール.

目的
----
副院長がカンファ台本を読みながらアプリを確認した際、稼働率や目標値の
不一致（台本 85% vs 実画面 86.5% 等）を自動検出できる状態を作る。

対象台本
--------
- docs/admin/carnf_scenario_v1.md            (カンファ運用台本)
- docs/admin/demo_scenario_v3.6.md           (臨床現場向け総合台本)
- docs/admin/presentation_script_bedcontrol.md (理事会講演原稿)
- docs/admin/slides/weekend_holiday_kpi/script.md (連休対策経営会議台本)

抽出方針
--------
- 指標ごとに「これは何の数字か」を正規表現で同定
- 文脈（章、病棟、モード、データソース）を隣接する見出し等から推定
- tolerance は指標ごとに設定（稼働率・LOS は 1.0、救急比率は 2.0 等）

Public API
----------
``extract_claims_from_file(path: Path) -> List[Claim]``
    単一 Markdown からクレームを抽出。

``extract_all_claims() -> List[Claim]``
    4 本の台本から全クレームを抽出。

``write_claims_json(claims, out_path)``
    JSON 出力（reports/scenario_claims.json）。

CLI
---
    python3 scripts/extract_scenario_claims.py
    python3 scripts/extract_scenario_claims.py --out reports/scenario_claims.json
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "reports" / "scenario_claims.json"

# 抽出対象台本（相対パス）
SCENARIO_FILES = [
    "docs/admin/carnf_scenario_v1.md",
    "docs/admin/demo_scenario_v3.6.md",
    "docs/admin/presentation_script_bedcontrol.md",
    "docs/admin/slides/weekend_holiday_kpi/script.md",
]

# 指標メタデータ:
#   metric    : 指標キー（JSON で使う）
#   unit      : 単位（UI 表示用）
#   tolerance : 許容誤差
#   testid    : 対応する data-testid（Playwright 照合用）
METRIC_META: dict[str, dict[str, Any]] = {
    "occupancy_pct": {"unit": "%", "tolerance": 1.5, "testid": "conference-occupancy-pct"},
    "occupancy_target_pct": {"unit": "%", "tolerance": 0.5, "testid": None},
    "alos_days": {"unit": "日", "tolerance": 1.0, "testid": "conference-alos-days"},
    "alos_limit_days": {"unit": "日", "tolerance": 0.5, "testid": None},
    "emergency_pct": {"unit": "%", "tolerance": 2.0, "testid": "conference-emergency-pct"},
    "emergency_threshold_pct": {"unit": "%", "tolerance": 0.5, "testid": None},
    "holiday_days_until": {"unit": "日", "tolerance": 2.0, "testid": "conference-holiday-days"},
    "holiday_banner_threshold_days": {"unit": "日", "tolerance": 0.5, "testid": None},
    "holiday_warning_threshold_days": {"unit": "日", "tolerance": 0.5, "testid": None},
    "holiday_danger_threshold_days": {"unit": "日", "tolerance": 0.5, "testid": None},
    "bed_total": {"unit": "床", "tolerance": 0.5, "testid": None},
    "bed_per_ward": {"unit": "床", "tolerance": 0.5, "testid": None},
    "monthly_admissions": {"unit": "件", "tolerance": 5.0, "testid": None},
    "revenue_per_1pct_manyen": {"unit": "万円/年", "tolerance": 10.0, "testid": None},
    "revenue_per_empty_bed_day_yen": {"unit": "円/床日", "tolerance": 300.0, "testid": None},
    "friday_discharge_pct": {"unit": "%", "tolerance": 3.0, "testid": None},
    "short3_rate_pct": {"unit": "%", "tolerance": 2.0, "testid": None},
    "c_group_contribution_yen": {"unit": "円/日", "tolerance": 500.0, "testid": None},
    "patient_count_rows": {"unit": "名", "tolerance": 0.5, "testid": "conference-patient-count"},
    "status_count_normal": {"unit": "種", "tolerance": 0.5, "testid": None},
    "status_count_holiday": {"unit": "種", "tolerance": 0.5, "testid": None},
}

# ---------------------------------------------------------------------------
# データクラス
# ---------------------------------------------------------------------------


@dataclass
class Claim:
    """台本内の 1 件の数値主張."""

    id: str
    source_file: str
    source_line: int
    scene: str
    context: dict[str, Any]
    claim_text: str
    metric: str
    expected_value: float
    tolerance: float
    unit: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# ヘッダー検出・文脈推定
# ---------------------------------------------------------------------------

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def _iter_lines_with_context(text: str) -> Iterable[tuple[int, str, str]]:
    """各行について (line_number_1based, line_text, nearest_header) を返す.

    直近の ``#`` 〜 ``######`` 見出しを追跡し、シーン名として供給する。
    """
    current_header = ""
    for idx, line in enumerate(text.splitlines(), start=1):
        m = _HEADER_RE.match(line.rstrip())
        if m:
            current_header = m.group(2).strip()
        yield idx, line, current_header


def _infer_ward(line: str, window: str) -> str | None:
    """行 + 直近の窓から病棟を推定する."""
    text = line + "\n" + window
    if "5F" in text and "6F" in text:
        # 両方言及は汎用文脈。明確な主語が取れないので None のまま。
        return None
    if "5F" in text:
        return "5F"
    if "6F" in text:
        return "6F"
    return None


def _infer_mode(line: str, window: str) -> str:
    text = line + "\n" + window
    if "連休対策モード" in text and "ON" in text:
        return "holiday"
    if "連休対策モード" in text:
        # モード切替の説明だけなら normal 前提
        return "normal"
    return "normal"


def _infer_data_source(line: str, scene: str) -> str:
    """デモデータ vs 実績データの区別. 明示されていなければ demo."""
    combo = line + " " + scene
    if "実データ" in combo or "実績データ" in combo:
        return "actual"
    return "demo"


def _window_around(lines: list[str], idx0: int, radius: int = 3) -> str:
    lo = max(0, idx0 - radius)
    hi = min(len(lines), idx0 + radius + 1)
    return "\n".join(lines[lo:hi])


# ---------------------------------------------------------------------------
# 抽出ルール
# ---------------------------------------------------------------------------


@dataclass
class ExtractionRule:
    """1 パターンのクレーム抽出ルール."""

    metric: str
    pattern: re.Pattern
    id_suffix: str
    group: int = 1  # 数値を取り出すキャプチャグループ
    skip_if: re.Pattern | None = None  # 除外パターン（並列候補と競合回避）


RULES: list[ExtractionRule] = [
    # --- 稼働率 ---
    # 「稼働率は 85%」「稼働率 85%」「稼働率は約 88.8%」
    # 差分・改善系（「稼働率 1% の改善」「稼働率 1% の重み」「1% 違うだけ」）は拾わない。
    # 「稼働率は 100% を超える」のような定義説明も拾わない。
    # 「稼働率 90% を維持」のような未来形・仮定形も拾わない。
    ExtractionRule(
        metric="occupancy_pct",
        pattern=re.compile(
            r"稼働率(?:は|が|を|\s)*(?:約|およそ|おおよそ)?\s*([-\d]+(?:\.\d+)?)\s*%"
            r"(?!\s*(?:以上|以下|を超|超え|超過|を維持|維持|以外|程度|前後|近い|ぐらい|くらい|の(?:改善|変動|違い|重み|差|ポイント|動き|意味|場合)))"
        ),
        id_suffix="occ-pct",
    ),
    # 「目標 90%」「目標の 90%」「目標 92%」(稼働率目標)
    ExtractionRule(
        metric="occupancy_target_pct",
        pattern=re.compile(
            r"(?:目標(?:の|値)?|稼働率目標)\s*(?:は)?\s*([-\d]+(?:\.\d+)?)\s*%"
        ),
        id_suffix="occ-target",
    ),
    # --- ALOS ---
    # 「ALOS は 17.5 日」「平均在院日数 17.5 日」「約 17.7 日」
    # 「制度上限 21 日」は alos_limit_days で別途拾うので、ここでは「上限」が直前にある場合を除外。
    # 「ALOS 21 日近い」のような仮定形も除外するため「近い/前後/程度」を拒否。
    ExtractionRule(
        metric="alos_days",
        pattern=re.compile(
            r"(?<!上限)(?<!上限の)(?<!上限\s)(?:ALOS|平均在院日数|在院日数|rolling\s*3\s*ヶ月の?\s*ALOS)\s*(?:は|が|で|に|について|:|：)?\s*(?:約|およそ)?\s*([-\d]+(?:\.\d+)?)\s*日(?!まで|以内|以下|以上|超|の上限|近い|前後|程度|ほど|くらい|ぐらい)"
        ),
        id_suffix="alos-days",
    ),
    # 「制度上限 21 日」「上限 21 日」「制度上限の 21 日」
    ExtractionRule(
        metric="alos_limit_days",
        pattern=re.compile(
            r"(?:制度)?上限(?:の|は)?\s*([-\d]+(?:\.\d+)?)\s*日"
        ),
        id_suffix="alos-limit",
    ),
    # --- 救急 ---
    # 「救急搬送後 15%」「救急搬送 17%」「救急搬送比率 22%」
    ExtractionRule(
        metric="emergency_pct",
        pattern=re.compile(
            r"救急(?:搬送後?|搬送後?患者)?(?:割合|比率|)\s*(?:は|が|で)?\s*(?:約|およそ)?\s*([-\d]+(?:\.\d+)?)\s*%(?!以上|以下|を下回|超え|超過|を切)"
        ),
        id_suffix="emerg-pct",
    ),
    # 「基準 15%」「15% を下回る」「15% 達成」
    ExtractionRule(
        metric="emergency_threshold_pct",
        pattern=re.compile(r"(?:基準|救急搬送後患者割合|達成基準)\s*([-\d]+(?:\.\d+)?)\s*%"),
        id_suffix="emerg-thresh",
    ),
    # --- 連休 ---
    # 「連休まで 21 日以下」「21 日を切ると」「連休 14 日前」
    ExtractionRule(
        metric="holiday_banner_threshold_days",
        pattern=re.compile(
            r"(?:連休まで\s*)?([-\d]+)\s*日\s*(?:以下|を切る|を切ると|以内)"
        ),
        id_suffix="holiday-thresh-banner",
    ),
    # --- 病床数 ---
    # 「94 床」「47 床」「総病床数 94 床」
    ExtractionRule(
        metric="bed_total",
        pattern=re.compile(r"(?:総病床数|病床数|全体)\s*(?:は)?\s*([0-9]{2,3})\s*床"),
        id_suffix="bed-total",
    ),
    # --- 月間入院 ---
    # 「月間入院数約 150 件」「約 150 件/月」
    ExtractionRule(
        metric="monthly_admissions",
        pattern=re.compile(r"月間入院(?:数)?(?:約)?\s*([-\d]+(?:\.\d+)?)\s*件"),
        id_suffix="monthly-admissions",
    ),
    # --- 収益 ---
    # 「1% の変動は年間約 1,046 万円」「約 1,046 万円」
    ExtractionRule(
        metric="revenue_per_1pct_manyen",
        pattern=re.compile(
            r"稼働率\s*1\s*%\s*(?:の)?(?:変動|違い|改善|≒)?\s*(?:は|が|で|により|で年間)?\s*年間\s*(?:約)?\s*([0-9,]+(?:\.[0-9]+)?)\s*万円"
        ),
        id_suffix="rev-per-1pct",
    ),
    # 「空床 1 床は、毎日約 3 万 500 円相当」→ 固定値 30500 として捕捉
    # 「30,500 円」単体は誤検出を避けるため「床」が近接している場合のみ
    ExtractionRule(
        metric="revenue_per_empty_bed_day_yen",
        pattern=re.compile(
            r"1\s*床(?:[^\n]{0,40}?)(3\s*万\s*500|30[,，]?500|30500)\s*円"
        ),
        id_suffix="rev-per-bed-day",
    ),
    # --- 金曜退院集中 ---
    # 「金曜退院集中 31%」「退院の 31% が金曜」
    ExtractionRule(
        metric="friday_discharge_pct",
        pattern=re.compile(
            r"(?:金曜(?:日)?退院(?:集中|の)?|退院の)\s*(?:約)?\s*([-\d]+(?:\.\d+)?)\s*%"
        ),
        id_suffix="friday-discharge",
    ),
    # --- C 群貢献額 ---
    # 「C群 日額貢献 ≈ 28,900 円」「約 28,900 円」「1名・1日あたりの運営貢献は約 28,900 円」
    ExtractionRule(
        metric="c_group_contribution_yen",
        pattern=re.compile(
            r"C\s*群(?:[^\n]{0,60}?)(?:約)?\s*([0-9,]+)\s*円(?:／日|/日|\s*\(推計\))?"
        ),
        id_suffix="c-contrib",
    ),
    # --- 患者行数 ---
    # 「最大 10 名の患者行」 → 10 に限定（「1 名の患者について」は拾わない）
    ExtractionRule(
        metric="patient_count_rows",
        pattern=re.compile(r"最大\s*([0-9]+)\s*名の患者(?:行|が|群)"),
        id_suffix="patient-rows",
    ),
    # --- ステータス種類数 ---
    # 「7 つのステータス」「7 種」「4 つのステータス」「4 種」
    ExtractionRule(
        metric="status_count_normal",
        pattern=re.compile(r"([0-9]+)\s*(?:つ|種)の?ステータス"),
        id_suffix="status-cnt",
    ),
]


# ---------------------------------------------------------------------------
# 抽出コア
# ---------------------------------------------------------------------------


def _parse_float(raw: str) -> float | None:
    """「1,046」「30,500」など桁区切りを受けて float 化.

    「3 万 500」のような和式表記も限定的に受ける（円単位）。
    """
    if raw is None:
        return None
    cleaned = raw.replace(",", "").replace("，", "")
    # 「3 万 500」→ 30500（和式簡易）
    man_match = re.match(r"^\s*([0-9]+)\s*万\s*([0-9]+)?\s*$", cleaned)
    if man_match:
        manbu = int(man_match.group(1)) * 10000
        rest = int(man_match.group(2) or 0)
        return float(manbu + rest)
    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_claims_from_file(path: Path, relative_to: Path | None = None) -> list[Claim]:
    """単一 Markdown ファイルからクレームを抽出."""
    relative_to = relative_to or ROOT
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    rel = str(path.relative_to(relative_to))
    claims: list[Claim] = []
    seen_keys: set[tuple[str, int, str]] = set()

    # 見出し追跡用に 1 周
    headers_by_line: list[str] = []
    current = ""
    for ln in lines:
        m = _HEADER_RE.match(ln.rstrip())
        if m:
            current = m.group(2).strip()
        headers_by_line.append(current)

    for idx, line in enumerate(lines, start=1):
        scene = headers_by_line[idx - 1]
        window = _window_around(lines, idx - 1)
        ward = _infer_ward(line, window)
        mode = _infer_mode(line, window)
        data_source = _infer_data_source(line, scene)

        for rule in RULES:
            for m in rule.pattern.finditer(line):
                # 稼働率 rule は「以上/以下」形式を排除（しきい値説明文）
                if rule.metric == "occupancy_pct" and (
                    "以上" in line[m.start() :] or "以下" in line[m.start() :]
                ):
                    continue
                # 目標稼働率 rule は単独数値（「X%」）のみ拾う
                raw = m.group(rule.group)
                val = _parse_float(raw)
                if val is None:
                    continue

                # 数値の現実性ゲート: 明らかに対象外の値は捨てる
                if not _is_plausible(rule.metric, val):
                    continue

                # 重複排除キー: (metric, line, value) で 1 件のみ
                key = (rule.metric, idx, f"{val:.2f}")
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                meta = METRIC_META.get(rule.metric, {})
                # ID 衝突回避: 候補を作り、既出なら occurrence を振る
                candidate = _make_claim_id(rel, rule.id_suffix, idx, ward, val, 0)
                occ = 0
                existing_ids = {c.id for c in claims}
                while candidate in existing_ids:
                    occ += 1
                    candidate = _make_claim_id(rel, rule.id_suffix, idx, ward, val, occ)
                claim_id = candidate
                claim_text = _crop_claim(line, m.start(), m.end())

                claims.append(
                    Claim(
                        id=claim_id,
                        source_file=rel,
                        source_line=idx,
                        scene=scene,
                        context={
                            "ward": ward,
                            "mode": mode,
                            "data_source": data_source,
                        },
                        claim_text=claim_text,
                        metric=rule.metric,
                        expected_value=val,
                        tolerance=float(meta.get("tolerance", 1.0)),
                        unit=str(meta.get("unit", "")),
                    )
                )

    return claims


def _is_plausible(metric: str, value: float) -> bool:
    """極端に外れた数値をノイズとしてフィルタ."""
    if metric in ("occupancy_pct", "occupancy_target_pct"):
        # 稼働率は 30% 以上 100% 以下を現実的とみなす（1% は差分・1-4 は段落番号ノイズ）
        return 30 <= value <= 110
    if metric == "emergency_pct":
        # 救急比率は 0-50% を現実的範囲に（台本の「2.6%」「17%」「22%」等）
        return 0 <= value <= 60
    if metric == "alos_days":
        return 1 <= value <= 60
    if metric == "alos_limit_days":
        return 14 <= value <= 30
    if metric == "emergency_threshold_pct":
        return 5 <= value <= 30
    if metric in (
        "holiday_banner_threshold_days",
        "holiday_warning_threshold_days",
        "holiday_danger_threshold_days",
    ):
        return 1 <= value <= 60
    if metric == "bed_total":
        return 40 <= value <= 300
    if metric == "monthly_admissions":
        return 50 <= value <= 500
    if metric == "revenue_per_1pct_manyen":
        return 500 <= value <= 5000
    if metric == "revenue_per_empty_bed_day_yen":
        return 20000 <= value <= 50000
    if metric == "friday_discharge_pct":
        return 10 <= value <= 60
    if metric == "c_group_contribution_yen":
        return 20000 <= value <= 40000
    if metric == "patient_count_rows":
        return 1 <= value <= 50
    if metric in ("status_count_normal", "status_count_holiday"):
        return 2 <= value <= 12
    return True


def _make_claim_id(
    rel: str,
    suffix: str,
    line: int,
    ward: str | None,
    val: float,
    occurrence: int = 0,
) -> str:
    base = Path(rel).stem.replace("_", "-").lower()
    # 値を ID に埋め込むことで、同じ行で同じメトリック・異なる値が複数ある場合も分離
    val_tag = f"{int(val)}" if float(val).is_integer() else f"{val:.1f}".replace(".", "p")
    tag = f"{base}-L{line}-{suffix}-{val_tag}"
    if ward:
        tag += f"-{ward.lower()}"
    if occurrence > 0:
        tag += f"-occ{occurrence}"
    return tag


def _crop_claim(line: str, span_start: int, span_end: int, radius: int = 28) -> str:
    """マッチ部分の前後 radius 文字を含む抜粋を返す."""
    lo = max(0, span_start - radius)
    hi = min(len(line), span_end + radius)
    return line[lo:hi].strip()


# ---------------------------------------------------------------------------
# オーケストレーション
# ---------------------------------------------------------------------------


def extract_all_claims(files: Iterable[str] | None = None) -> list[Claim]:
    """対象台本全件のクレームを抽出."""
    files = list(files) if files is not None else list(SCENARIO_FILES)
    all_claims: list[Claim] = []
    for rel_path in files:
        abs_path = ROOT / rel_path
        if not abs_path.exists():
            print(f"[warn] ファイルが見つかりません: {rel_path}")
            continue
        all_claims.extend(extract_claims_from_file(abs_path, relative_to=ROOT))
    return all_claims


def write_claims_json(claims: list[Claim], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "claim_count": len(claims),
        "source_files": sorted({c.source_file for c in claims}),
        "claims": [c.to_dict() for c in claims],
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="シナリオ台本から数値主張を抽出")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="出力 JSON パス")
    parser.add_argument(
        "--file",
        action="append",
        help="対象ファイル（複数可、未指定時は全台本）",
        default=None,
    )
    args = parser.parse_args(argv)

    claims = extract_all_claims(args.file)
    out = Path(args.out)
    write_claims_json(claims, out)

    by_file: dict[str, int] = {}
    by_metric: dict[str, int] = {}
    for c in claims:
        by_file[c.source_file] = by_file.get(c.source_file, 0) + 1
        by_metric[c.metric] = by_metric.get(c.metric, 0) + 1

    print(f"抽出完了: {len(claims)} 件")
    print(f"出力先: {out}")
    print("\nファイル別:")
    for f, n in sorted(by_file.items()):
        print(f"  {n:3d} 件  {f}")
    print("\n指標別:")
    for m, n in sorted(by_metric.items(), key=lambda kv: -kv[1]):
        print(f"  {n:3d} 件  {m}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
