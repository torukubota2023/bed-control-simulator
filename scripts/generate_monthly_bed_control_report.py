"""月次ベッドコントロールレポート自動生成（案 γ, 2026-04-24 副院長指示）.

指定月の KPI（枠超過、日曜退院、主治医別突発退院 TOP 3 等）を集計して
Markdown レポートを `docs/admin/reports/` に出力する。経営会議・師長会議向け
の定形資料として、毎月 1 回実行する想定。

使い方:
    # 当月のレポートを生成
    python3 scripts/generate_monthly_bed_control_report.py

    # 指定月のレポートを生成
    python3 scripts/generate_monthly_bed_control_report.py --year 2026 --month 4

    # カスタム出力先
    python3 scripts/generate_monthly_bed_control_report.py --output /tmp/report.md

Streamlit には依存しない pure function。将来 Streamlit 内からも
呼び出せる設計（generate_report() → str）。
"""
from __future__ import annotations

import argparse
import calendar
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# scripts/ を import パスに
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import pandas as pd  # noqa: E402

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

BEDS_PER_WARD = 47
WARDS = ["5F", "6F"]

# 2025-2026 祝日（簡略版）
JP_HOLIDAYS: Set[date] = {
    date(2025, 4, 29), date(2025, 5, 3), date(2025, 5, 4), date(2025, 5, 5),
    date(2025, 5, 6), date(2025, 7, 21), date(2025, 8, 11), date(2025, 9, 15),
    date(2025, 9, 23), date(2025, 10, 13), date(2025, 11, 3), date(2025, 11, 23),
    date(2025, 11, 24), date(2026, 1, 1), date(2026, 1, 12), date(2026, 2, 11),
    date(2026, 2, 23), date(2026, 3, 20), date(2026, 4, 29),
}


def _get_slot(d: date) -> int:
    if d in JP_HOLIDAYS:
        return 2
    if d.weekday() == 6:
        return 2
    return 5


# ---------------------------------------------------------------------------
# データ集計ロジック
# ---------------------------------------------------------------------------

def collect_plans_for_month(
    year: int, month: int,
) -> Dict[str, Dict[str, Any]]:
    """指定月に scheduled_date を持つ退院予定を返す（動かせない理由を保持）."""
    try:
        from discharge_plan_store import load_all_plans  # type: ignore
    except ImportError:
        return {}
    plans = load_all_plans()
    filtered: Dict[str, Dict[str, Any]] = {}
    for uuid, plan in plans.items():
        sd_str = plan.get("scheduled_date")
        if not sd_str:
            continue
        try:
            sd = date.fromisoformat(sd_str)
        except ValueError:
            continue
        if sd.year == year and sd.month == month:
            filtered[uuid] = plan
    return filtered


def collect_ward_map() -> Dict[str, str]:
    """admission_details.csv から UUID → 病棟 map を構築."""
    csv_path = Path(__file__).resolve().parent.parent / "data" / "admission_details.csv"
    if not csv_path.exists():
        return {}
    try:
        df = pd.read_csv(csv_path)
    except Exception:
        return {}
    if "id" not in df.columns or "ward" not in df.columns:
        return {}
    if "event_type" in df.columns:
        df = df[df["event_type"] == "admission"]
    mp: Dict[str, str] = {}
    for _, row in df.iterrows():
        pid = str(row["id"])
        if len(pid) >= 8:
            mp[pid[:8]] = str(row["ward"])
    return mp


def collect_doctor_map() -> Dict[str, str]:
    """admission_details.csv から UUID → 主治医 map を構築."""
    csv_path = Path(__file__).resolve().parent.parent / "data" / "admission_details.csv"
    if not csv_path.exists():
        return {}
    try:
        df = pd.read_csv(csv_path)
    except Exception:
        return {}
    if "id" not in df.columns or "attending_doctor" not in df.columns:
        return {}
    if "event_type" in df.columns:
        df = df[df["event_type"] == "admission"]
    mp: Dict[str, str] = {}
    for _, row in df.iterrows():
        pid = str(row["id"])
        if len(pid) >= 8:
            mp[pid[:8]] = str(row.get("attending_doctor", "主治医不明"))
    return mp


def calc_month_kpis(
    year: int, month: int,
    plans: Dict[str, Dict[str, Any]],
    ward_map: Dict[str, str],
    doctor_map: Dict[str, str],
) -> Dict[str, Any]:
    """月次 KPI を計算."""
    total_days = calendar.monthrange(year, month)[1]
    month_start = date(year, month, 1)
    month_end = date(year, month, total_days)

    # 日別・病棟別の退院予定数
    by_day_ward: Dict[Tuple[date, str], int] = defaultdict(int)
    by_day_ward_unplanned: Dict[Tuple[date, str], int] = defaultdict(int)
    by_day_ward_fixed: Dict[Tuple[date, str], int] = defaultdict(int)
    for uuid, plan in plans.items():
        ward = ward_map.get(uuid, "unknown")
        if ward not in WARDS:
            continue
        try:
            sd = date.fromisoformat(plan["scheduled_date"])
        except (ValueError, KeyError, TypeError):
            continue
        by_day_ward[(sd, ward)] += 1
        if plan.get("unplanned"):
            by_day_ward_unplanned[(sd, ward)] += 1
        if plan.get("movable_reason"):
            by_day_ward_fixed[(sd, ward)] += 1

    # 枠超過日のカウント（病棟別）
    overflow_days: Dict[str, int] = {w: 0 for w in WARDS}
    overflow_total: Dict[str, int] = {w: 0 for w in WARDS}
    total_discharges: Dict[str, int] = {w: 0 for w in WARDS}
    sunday_discharges: Dict[str, int] = {w: 0 for w in WARDS}
    for (d, w), count in by_day_ward.items():
        total_discharges[w] += count
        slot = _get_slot(d)
        if count > slot:
            overflow_days[w] += 1
            overflow_total[w] += count - slot
        if d.weekday() == 6 or d in JP_HOLIDAYS:
            sunday_discharges[w] += count

    # 突発退院合計・主治医別 TOP
    unplanned_total = sum(by_day_ward_unplanned.values())
    unplanned_by_doctor: Dict[str, int] = defaultdict(int)
    for uuid, plan in plans.items():
        if not plan.get("unplanned"):
            continue
        doctor = doctor_map.get(uuid, "主治医不明")
        unplanned_by_doctor[doctor] += 1

    # 動かせない患者の集計
    fixed_total = sum(by_day_ward_fixed.values())
    fixed_by_reason: Dict[str, int] = defaultdict(int)
    for plan in plans.values():
        reason = plan.get("movable_reason")
        if reason:
            fixed_by_reason[reason] += 1

    return {
        "period": f"{year}-{month:02d}",
        "total_days_in_month": total_days,
        "month_start": month_start,
        "month_end": month_end,
        "total_plans": len(plans),
        "overflow_days_by_ward": overflow_days,
        "overflow_total_by_ward": overflow_total,
        "total_discharges_by_ward": total_discharges,
        "sunday_discharges_by_ward": sunday_discharges,
        "unplanned_total": unplanned_total,
        "unplanned_by_doctor": dict(unplanned_by_doctor),
        "fixed_total": fixed_total,
        "fixed_by_reason": dict(fixed_by_reason),
    }


# ---------------------------------------------------------------------------
# Markdown 生成
# ---------------------------------------------------------------------------

_MONTH_JA = {
    1: "1月", 2: "2月", 3: "3月", 4: "4月", 5: "5月", 6: "6月",
    7: "7月", 8: "8月", 9: "9月", 10: "10月", 11: "11月", 12: "12月",
}


def render_markdown(kpis: Dict[str, Any]) -> str:
    """KPI dict から Markdown を生成."""
    y, m = kpis["period"].split("-")
    year, month = int(y), int(m)

    lines = []
    lines.append(f"# 🏥 月次ベッドコントロール レポート — {year} 年 {_MONTH_JA[month]}")
    lines.append("")
    lines.append(
        f"**対象期間**: {kpis['month_start']} 〜 {kpis['month_end']}（"
        f"{kpis['total_days_in_month']} 日）  "
    )
    lines.append(
        f"**生成日時**: {datetime.now().strftime('%Y-%m-%d %H:%M')}  "
    )
    lines.append(
        f"**登録された退院予定総数**: {kpis['total_plans']} 件"
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    # セクション 1: 病棟別サマリー
    lines.append("## 📊 病棟別サマリー")
    lines.append("")
    lines.append("| 病棟 | 総退院数 | 枠超過日数 | 累計超過人数 | 日曜退院実施 |")
    lines.append("|------|---------|-----------|-------------|-------------|")
    for ward in WARDS:
        total = kpis["total_discharges_by_ward"].get(ward, 0)
        od = kpis["overflow_days_by_ward"].get(ward, 0)
        ot = kpis["overflow_total_by_ward"].get(ward, 0)
        sd = kpis["sunday_discharges_by_ward"].get(ward, 0)
        lines.append(f"| {ward} | {total} 名 | {od} 日 | +{ot} 名 | {sd} 名 |")
    lines.append("")

    # セクション 2: 枠超過の状況
    total_od = sum(kpis["overflow_days_by_ward"].values())
    total_ot = sum(kpis["overflow_total_by_ward"].values())
    lines.append("## 🚨 枠超過の発生状況")
    lines.append("")
    if total_od == 0:
        lines.append("✅ **今月は枠超過が発生していません**。枠制限 UI の効果が確認できます。")
    else:
        lines.append(
            f"⚠️ 今月の枠超過は **合計 {total_od} 日 / +{total_ot} 名**"
        )
        for ward in WARDS:
            od = kpis["overflow_days_by_ward"].get(ward, 0)
            if od > 0:
                ot = kpis["overflow_total_by_ward"].get(ward, 0)
                lines.append(f"  - {ward}: {od} 日、累計超過 +{ot} 名")
        lines.append("")
        lines.append(
            "→ 来月以降のカンファで「超過が大きかった曜日」を振り返り、"
            "事前分散の意識を高める改善ポイント"
        )
    lines.append("")

    # セクション 3: 日曜退院（副院長指示: 推奨実施）
    total_sun = sum(kpis["sunday_discharges_by_ward"].values())
    lines.append("## ⭐ 日曜・祝日退院の実施状況（推奨指標）")
    lines.append("")
    lines.append(
        f"今月の日曜・祝日退院: **合計 {total_sun} 名**"
    )
    for ward in WARDS:
        sd = kpis["sunday_discharges_by_ward"].get(ward, 0)
        lines.append(f"  - {ward}: {sd} 名")
    if total_sun == 0:
        lines.append("")
        lines.append(
            "💡 日曜・祝日退院は枠 2 名まで設定されています。"
            "土日退院に対応可能な患者・家族があれば活用すると稼働率維持に有効"
        )
    lines.append("")

    # セクション 4: 突発退院（主治医別）
    lines.append("## ⚡ 突発退院の集計")
    lines.append("")
    up_total = kpis["unplanned_total"]
    if up_total == 0:
        lines.append("✅ **今月は突発退院の発生なし**。全退院がカンファで事前に調整されています。")
    else:
        lines.append(
            f"今月の突発退院件数: **{up_total} 件**"
        )
        lines.append("")
        by_doctor = kpis["unplanned_by_doctor"]
        if by_doctor:
            lines.append("### 主治医別 TOP 3")
            lines.append("")
            lines.append("| 順位 | 主治医 | 件数 |")
            lines.append("|------|-------|------|")
            sorted_docs = sorted(
                by_doctor.items(), key=lambda kv: kv[1], reverse=True
            )[:3]
            for i, (doc, n) in enumerate(sorted_docs, 1):
                lines.append(f"| {i} | {doc} | {n} 件 |")
            lines.append("")
            lines.append(
                "→ ルール違反を意味する数字ではないが、運用ルール周知の対象を絞る指標として参考に"
            )
    lines.append("")

    # セクション 5: 動かせない患者（案 β）
    lines.append("## 🔒 日付固定患者の状況（案 β タグ活用）")
    lines.append("")
    fixed_total = kpis["fixed_total"]
    if fixed_total == 0:
        lines.append(
            "動かせない理由タグが設定された退院予定は **0 件**です。"
            "枠超過時はすべての予定が別日分散の候補になります。"
        )
    else:
        lines.append(
            f"今月の日付固定退院: **合計 {fixed_total} 件**"
        )
        lines.append("")
        lines.append("### 固定理由の内訳")
        lines.append("")
        try:
            from discharge_plan_store import MOVABLE_REASON_LABELS as _mrl  # type: ignore
        except ImportError:
            _mrl = {}
        lines.append("| 理由 | 件数 |")
        lines.append("|------|------|")
        for reason, n in sorted(
            kpis["fixed_by_reason"].items(), key=lambda kv: kv[1], reverse=True
        ):
            label = _mrl.get(reason, reason)
            lines.append(f"| {label} | {n} 件 |")
        lines.append("")
    lines.append("")

    # セクション 6: 経営インパクト
    lines.append("## 💰 経営インパクト（推定）")
    lines.append("")
    # 枠超過 0 日なら、理論上避けられた稼働率急落分の価値
    if total_od > 0:
        # 1 日あたり超過 1 名 = 1 床日の余裕、33,670 円/床日
        saved_est = total_ot * 33670
        lines.append(
            f"枠超過が発生した場合の稼働率低下回避効果（推定）: "
            f"**約 {saved_est:,} 円**"
        )
        lines.append(
            "（累計超過 {} 名 × 1 床日相当 × 3,367 点/日 × 10 円）".format(total_ot)
        )
    else:
        lines.append(
            "✅ 枠超過ゼロのため、今月は稼働率急落の未然防止に成功した月"
        )
    lines.append("")

    # セクション 7: 来月への申し送り
    lines.append("## 📝 来月への申し送り")
    lines.append("")
    notes = []
    if total_od > 0:
        notes.append(
            "- 今月発生した枠超過の曜日パターンを分析し、"
            "カンファで曜日別の退院推奨タイミングを再確認"
        )
    if total_sun == 0:
        notes.append(
            "- 日曜・祝日退院の活用を家族・施設と協議（特に休日迎え可能な方）"
        )
    if up_total > 0:
        notes.append(
            f"- 突発退院 {up_total} 件の背景を主治医と共有、"
            "カンファでの事前決定を優先する運用ルールを再徹底"
        )
    if not notes:
        notes.append("- 今月は目立った課題なし、現運用を継続")
    for n in notes:
        lines.append(n)
    lines.append("")

    # フッター
    lines.append("---")
    lines.append("")
    lines.append(
        "*本レポートは `scripts/generate_monthly_bed_control_report.py` により自動生成されました。*  "
    )
    lines.append(
        "*副院長: 久保田徹 / おもろまちメディカルセンター*"
    )
    lines.append("")
    return "\n".join(lines)


def generate_report(year: int, month: int) -> str:
    """指定月のレポートを Markdown で返す."""
    plans = collect_plans_for_month(year, month)
    ward_map = collect_ward_map()
    doctor_map = collect_doctor_map()
    kpis = calc_month_kpis(year, month, plans, ward_map, doctor_map)
    return render_markdown(kpis)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="月次ベッドコントロールレポートを生成",
    )
    today = date.today()
    parser.add_argument(
        "--year", type=int, default=today.year,
        help="対象年（デフォルト: 今年）",
    )
    parser.add_argument(
        "--month", type=int, default=today.month,
        help="対象月（デフォルト: 今月）",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="出力先パス（デフォルト: docs/admin/reports/bed_control_report_YYYY-MM.md）",
    )
    args = parser.parse_args()

    md = generate_report(args.year, args.month)

    if args.output:
        out_path = Path(args.output)
    else:
        out_dir = Path(__file__).resolve().parent.parent / "docs" / "admin" / "reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"bed_control_report_{args.year:04d}-{args.month:02d}.md"

    out_path.write_text(md, encoding="utf-8")
    print(f"✅ 月次レポート生成: {out_path}")
    print(f"   サイズ: {len(md)} 文字 / {out_path.stat().st_size} bytes")


if __name__ == "__main__":
    main()


__all__ = [
    "generate_report",
    "calc_month_kpis",
    "render_markdown",
]
