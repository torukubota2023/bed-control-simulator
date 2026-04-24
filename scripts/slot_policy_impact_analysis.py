"""退院枠制限ポリシーの稼働率への影響分析.

副院長の疑問 (2026-04-24):
    「前日超過→翌日-N の枠制限は、翌々日以降で通常に戻るので、
     結局稼働率低下は同じなのでは？」

検証:
    過去 1 年 (2025-04〜2026-03) の実データで 3 シナリオを比較:
    A. 実績（何もしない）: そのまま記録通りの退院
    B. 翌日繰越のみ（現仕様）: 超過分を翌営業日に繰越（累積なし）
    C. 完全均等分散（理想）: 退院を曜日別で均等に配分
    D. 3 日間繰越（参考）: 超過分を最大 3 営業日まで繰越

分析項目:
    - 日次在院数のばらつき (std)
    - 月次平均稼働率 (各日稼働率の平均)
    - 「枠超過日数」がどれだけ減るか
    - 稼働率が目標 (90-95%) から外れた日数

結論の出し方:
    各シナリオで月次平均稼働率を計算し、差分が副院長の懸念する
    「結局同じ」なのか、意味のある改善があるのかを判定。

Streamlit に依存しない pure Python スクリプト。
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

# ---------------------------------------------------------------------------
# 設定（副院長の確定仕様に準拠）
# ---------------------------------------------------------------------------

WEEKDAY_SLOT = 5        # 月〜土 の 1 病棟あたり退院枠
HOLIDAY_SLOT = 2        # 日・祝 の 1 病棟あたり退院枠
BEDS_PER_WARD = 47      # 5F / 6F 各 47 床

# 病棟フィルタ（5F/6F のみ対象）
WARDS = ["5F", "6F"]

# 2025 年度の日本の祝日（簡略版、月曜振替を含む）
JP_HOLIDAYS_2025_2026 = {
    date(2025, 4, 29),   # 昭和の日
    date(2025, 5, 3),    # 憲法記念日
    date(2025, 5, 4),    # みどりの日
    date(2025, 5, 5),    # こどもの日
    date(2025, 5, 6),    # 振替
    date(2025, 7, 21),   # 海の日
    date(2025, 8, 11),   # 山の日
    date(2025, 9, 15),   # 敬老の日
    date(2025, 9, 23),   # 秋分の日
    date(2025, 10, 13),  # 体育の日
    date(2025, 11, 3),   # 文化の日
    date(2025, 11, 23),  # 勤労感謝の日
    date(2025, 11, 24),  # 振替
    date(2026, 1, 1),    # 元日
    date(2026, 1, 12),   # 成人の日
    date(2026, 2, 11),   # 建国記念日
    date(2026, 2, 23),   # 天皇誕生日
    date(2026, 3, 20),   # 春分の日
}


def get_slot(d: date) -> int:
    """指定日の基本枠を返す（祝日を考慮）."""
    if d in JP_HOLIDAYS_2025_2026:
        return HOLIDAY_SLOT
    if d.weekday() == 6:  # 日曜
        return HOLIDAY_SLOT
    return WEEKDAY_SLOT


def next_business_day(d: date) -> date:
    """翌営業日を返す（日曜・祝日を飛ばす）."""
    nxt = d + timedelta(days=1)
    while nxt.weekday() == 6 or nxt in JP_HOLIDAYS_2025_2026:
        nxt += timedelta(days=1)
    return nxt


# ---------------------------------------------------------------------------
# データ読み込み
# ---------------------------------------------------------------------------

def load_data() -> pd.DataFrame:
    """過去 1 年データを読み込む."""
    path = Path(__file__).resolve().parent.parent / "data" / "past_admissions_2025fy.csv"
    df = pd.read_csv(path)
    # 5F / 6F 病棟のみ
    df = df[df["病棟"].isin(WARDS)].copy()
    # 日付カラムのパース（不正値は NaT になる）
    df["入院日"] = pd.to_datetime(df["入院日"], errors="coerce")
    df["退院日"] = pd.to_datetime(df["退院日"], errors="coerce")
    # 両方欠損していない行のみ残す
    df = df.dropna(subset=["入院日", "退院日"]).copy()
    # date オブジェクトに変換
    df["入院日"] = df["入院日"].dt.date
    df["退院日"] = df["退院日"].dt.date
    return df


def build_daily_events(df: pd.DataFrame, ward: str) -> Tuple[Dict[date, int], Dict[date, int]]:
    """指定病棟の日別入院件数・退院件数を集計."""
    ward_df = df[df["病棟"] == ward]
    admissions: Dict[date, int] = defaultdict(int)
    discharges: Dict[date, int] = defaultdict(int)
    for _, row in ward_df.iterrows():
        admissions[row["入院日"]] += 1
        discharges[row["退院日"]] += 1
    return dict(admissions), dict(discharges)


# ---------------------------------------------------------------------------
# シナリオ
# ---------------------------------------------------------------------------

def scenario_a_actual(
    admissions: Dict[date, int],
    discharges: Dict[date, int],
    start_date: date,
    end_date: date,
) -> Dict[date, int]:
    """A. 実績そのまま（何もしない）."""
    return dict(discharges)


def scenario_b_next_day_carry(
    admissions: Dict[date, int],
    discharges: Dict[date, int],
    start_date: date,
    end_date: date,
) -> Dict[date, int]:
    """B. 翌日繰越のみ（現仕様、累積なし）.

    各日の退院数が枠を超えたら、超過分を **翌営業日だけ** に繰越。
    翌営業日も枠オーバーなら、そこで実行（繰越しない、帳消し）。
    """
    result: Dict[date, int] = defaultdict(int)
    days = pd.date_range(start_date, end_date).date

    for d in days:
        scheduled = discharges.get(d, 0)
        slot = get_slot(d)

        # 繰越は前日から受け取る（1 営業日前のみ）
        # 仕様通り: 累積しない、翌々日は元の枠
        if d > start_date:
            prev = _prev_business_day(d)
            prev_scheduled = discharges.get(prev, 0)
            prev_slot = get_slot(prev)
            carry_from_prev = max(0, prev_scheduled - prev_slot)
        else:
            carry_from_prev = 0

        # 今日の実効枠
        effective_slot = max(0, slot - carry_from_prev)

        # 今日の退院実施数
        actual_today = min(scheduled, effective_slot)
        result[d] = actual_today

        # 超過分（今日の「当初予定」から「実施」を引いた分）は、翌日に繰越
        # → 翌日の枠が減るが、繰越そのものは今日の退院数には含めない
        # （つまり、超過分は「その日に退院できなかった」と扱い、実質は
        #  翌日の枠 -N の状態を作ることで均す）
        # ただし、副院長の仕様は「超過したまま退院は起きる。ただし翌日の
        # 枠が減る」なので、実際の運用では超過分も退院は実行される。
        # → 正確には result[d] = scheduled にすべき。翌日枠縮小は別ロジック。
        # ここは仕様の厳密解釈で再修正:
        result[d] = scheduled  # 超過分も含めて退院は起きる
        # 翌日の枠は prev_scheduled - prev_slot 分だけ減る

    # 仕様の本質: 「退院数自体は変わらないが、枠制限が副院長の判断を促して
    # 超過を避ける」
    # → このシナリオでは副院長が事前に超過を避けるという効果を模擬:
    return scenario_b_with_decision_support(admissions, discharges, start_date, end_date)


def _prev_business_day(d: date) -> date:
    """前営業日を返す（日曜・祝日を飛ばす）."""
    prv = d - timedelta(days=1)
    while prv.weekday() == 6 or prv in JP_HOLIDAYS_2025_2026:
        prv -= timedelta(days=1)
    return prv


def scenario_b_with_decision_support(
    admissions: Dict[date, int],
    discharges: Dict[date, int],
    start_date: date,
    end_date: date,
) -> Dict[date, int]:
    """B (実効版). 枠制限 UI が副院長の意思決定を促し、超過分は翌営業日以降に
    自動的に移動させるシミュレーション.

    想定運用:
        1. カレンダーで「この日満杯」と副院長が気づく
        2. 超過分の患者の退院予定日を翌営業日にずらす
        3. 翌営業日も満杯なら、その翌営業日... ただし **翌日 1 日のみ吸収可**
           （累積しないので、翌々日はまた空きがあれば使える）

    つまり **「満杯の日は枠以上に退院しない」**。
    超過する分は翌営業日に試し、翌営業日も満杯なら、そのまた翌営業日の「通常枠」に流す
    （枠縮小は翌日だけ）。
    """
    result: Dict[date, int] = defaultdict(int)
    carry: Dict[date, int] = defaultdict(int)  # 翌日に繰り越された分
    days = pd.date_range(start_date, end_date).date

    for d in days:
        scheduled = discharges.get(d, 0)
        slot = get_slot(d)

        # 前日からの繰越を加算
        today_demand = scheduled + carry.get(d, 0)
        # 今日の枠（前日超過があれば -N、ただし 1 営業日前のみ）
        prev_bd = _prev_business_day(d) if d > start_date else None
        if prev_bd is not None and prev_bd >= start_date:
            # 前日の「本来の退院需要」が前日枠を超えていたら、今日の枠から -N
            prev_demand_orig = discharges.get(prev_bd, 0)
            prev_slot_val = get_slot(prev_bd)
            prev_excess = max(0, prev_demand_orig - prev_slot_val)
            effective_slot = max(0, slot - prev_excess)
        else:
            effective_slot = slot

        # 今日の退院実施数 = min(需要, 実効枠)
        actual = min(today_demand, effective_slot)
        result[d] = actual

        # 超過分を翌日に繰越
        overflow = today_demand - actual
        if overflow > 0:
            nxt = next_business_day(d)
            if nxt <= end_date:
                carry[nxt] += overflow

    return dict(result)


def scenario_c_even_distribution(
    admissions: Dict[date, int],
    discharges: Dict[date, int],
    start_date: date,
    end_date: date,
) -> Dict[date, int]:
    """C. 完全均等分散（理想）.

    **総退院数は保存**しつつ、各月内で枠超過分を余裕日に再配分。
    枠超過日がゼロになるまで、超過分を 1 名ずつ余裕日に移動。
    """
    result: Dict[date, int] = {d: n for d, n in discharges.items()}
    all_days = pd.date_range(start_date, end_date).date

    # 月単位で処理
    months: Dict[Tuple[int, int], List[date]] = defaultdict(list)
    for d in all_days:
        months[(d.year, d.month)].append(d)

    for ym, days_in_month in months.items():
        # 月内で枠超過がなくなるまで 1 名ずつ移動
        max_iterations = 100  # 無限ループ防止
        for _ in range(max_iterations):
            excess_days = sorted(
                [(d, result.get(d, 0) - get_slot(d))
                 for d in days_in_month
                 if result.get(d, 0) > get_slot(d)],
                key=lambda x: -x[1]  # 超過が大きい順
            )
            if not excess_days:
                break
            available_days = sorted(
                [(d, get_slot(d) - result.get(d, 0))
                 for d in days_in_month
                 if result.get(d, 0) < get_slot(d)],
                key=lambda x: x[0]  # 日付順
            )
            if not available_days:
                break  # 移動先がない

            src = excess_days[0][0]
            dst = available_days[0][0]
            result[src] -= 1
            result[dst] = result.get(dst, 0) + 1

    return result


# ---------------------------------------------------------------------------
# 稼働率シミュレーション
# ---------------------------------------------------------------------------

def simulate_daily_census(
    admissions: Dict[date, int],
    modified_discharges: Dict[date, int],
    start_date: date,
    end_date: date,
    initial_census: int,
) -> Dict[date, float]:
    """各日の夜の在院数を漸化式で計算."""
    census: Dict[date, float] = {}
    current = float(initial_census)
    days = pd.date_range(start_date, end_date).date
    for d in days:
        adm = admissions.get(d, 0)
        dis = modified_discharges.get(d, 0)
        current = max(0, current - dis + adm)
        census[d] = current
    return census


def calculate_metrics(
    census: Dict[date, float],
    beds: int,
) -> Dict[str, float]:
    """稼働率関連の指標を計算."""
    values = list(census.values())
    occ = [v / beds * 100 for v in values]  # % 単位
    if not occ:
        return {}
    avg_occ = sum(occ) / len(occ)
    import statistics
    std_occ = statistics.stdev(occ) if len(occ) > 1 else 0.0
    below_90 = sum(1 for o in occ if o < 90)
    in_target = sum(1 for o in occ if 90 <= o <= 95)
    above_95 = sum(1 for o in occ if o > 95)
    return {
        "avg_occ_pct": round(avg_occ, 2),
        "std_occ_pct": round(std_occ, 2),
        "days_below_90_pct": below_90,
        "days_in_target_90_95": in_target,
        "days_above_95": above_95,
        "total_days": len(occ),
    }


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def analyze_ward(ward: str, df: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """1 病棟分の分析.

    シナリオ A (実績)、B (翌日繰越)、C (月内均等) の 3 種類で
    日次在院数を計算し、絶対値ではなく「**A からの差分**」で効果を測る。
    絶対値は初期在院数の仮定に依存するため信頼できないが、
    差分は A と同じ初期値を使うので**意味のある比較**が可能。
    """
    admissions, discharges = build_daily_events(df, ward)

    all_dates = sorted(set(admissions.keys()) | set(discharges.keys()))
    start_date = min(all_dates)
    end_date = max(all_dates)

    # 初期在院数: 期間内の退院が全部記録に残る前提なら、
    # 全期間の入院件数と退院件数の差が期間終了時との差分
    # これを 0 とするため、初期在院数 = 期間内退院 - 期間内入院（もし正なら）
    # ただし期間内で入退院完結しない患者がいると偏りが出る
    # シンプルに「A の月次平均稼働率」が 90% 付近になるように調整して対比する
    total_adm = sum(admissions.values())
    total_dis = sum(discharges.values())
    # 初期在院数を逆算: 最終在院数を期待稼働率 (89%) で設定
    # 初期在院 + total_adm - total_dis = 最終在院 = 47 * 0.89 ≒ 42
    target_final = 42
    initial_census = max(0, target_final - (total_adm - total_dis))

    scenarios = {
        "A_actual": scenario_a_actual(admissions, discharges, start_date, end_date),
        "B_next_day_carry": scenario_b_with_decision_support(admissions, discharges, start_date, end_date),
        "C_even_distribution": scenario_c_even_distribution(admissions, discharges, start_date, end_date),
    }

    results: Dict[str, Dict[str, float]] = {}
    for name, mod_disc in scenarios.items():
        census = simulate_daily_census(
            admissions, mod_disc, start_date, end_date, initial_census
        )
        metrics = calculate_metrics(census, BEDS_PER_WARD)
        metrics["total_discharges"] = sum(mod_disc.values())
        metrics["overflow_days"] = _count_overflow_days(mod_disc)
        results[name] = metrics

    return results


def _count_overflow_days(discharges: Dict[date, int]) -> int:
    """枠超過日数を数える."""
    count = 0
    for d, n in discharges.items():
        if n > get_slot(d):
            count += 1
    return count


def main() -> None:
    df = load_data()
    print(f"データ読み込み: {len(df)} 件（5F+6F）")
    print(f"期間: {df['入院日'].min()} 〜 {df['退院日'].max()}")
    print()

    all_results: Dict[str, Dict[str, Dict[str, float]]] = {}
    for ward in WARDS:
        print(f"=" * 70)
        print(f"📊 {ward} 病棟分析")
        print(f"=" * 70)
        results = analyze_ward(ward, df)
        all_results[ward] = results

        # 表形式で表示
        header = f"{'指標':<30} {'A 実績':>12} {'B 翌日繰越':>12} {'C 完全均等':>12}"
        print(header)
        print("-" * len(header))
        labels = [
            ("平均稼働率 (%)", "avg_occ_pct"),
            ("稼働率の標準偏差", "std_occ_pct"),
            ("90% 未満の日数", "days_below_90_pct"),
            ("目標範囲 90-95% の日数", "days_in_target_90_95"),
            ("95% 超の日数", "days_above_95"),
            ("枠超過日数", "overflow_days"),
            ("総退院数", "total_discharges"),
        ]
        for label, key in labels:
            a = results["A_actual"].get(key, "-")
            b = results["B_next_day_carry"].get(key, "-")
            c = results["C_even_distribution"].get(key, "-")
            print(f"{label:<30} {str(a):>12} {str(b):>12} {str(c):>12}")
        print()

        # 改善幅
        a_occ = results["A_actual"]["avg_occ_pct"]
        b_occ = results["B_next_day_carry"]["avg_occ_pct"]
        c_occ = results["C_even_distribution"]["avg_occ_pct"]
        print(f"💡 改善幅:")
        print(f"  B (翌日繰越のみ)  vs A (実績): {b_occ - a_occ:+.2f} pt")
        print(f"  C (完全均等分散) vs A (実績): {c_occ - a_occ:+.2f} pt")
        print(f"  B が A と C のどちらに近いか: "
              f"A寄り {(b_occ - a_occ) / (c_occ - a_occ) * 100 if c_occ != a_occ else 0:.0f}% C寄り")
        print()

    # 総括
    print("=" * 70)
    print("🎯 副院長の疑問への回答")
    print("=" * 70)
    for ward in WARDS:
        r = all_results[ward]
        a_occ = r["A_actual"]["avg_occ_pct"]
        b_occ = r["B_next_day_carry"]["avg_occ_pct"]
        c_occ = r["C_even_distribution"]["avg_occ_pct"]
        delta_b = b_occ - a_occ
        delta_c = c_occ - a_occ

        if delta_b > 0.5:
            verdict = "✅ 有効（0.5pt 以上の改善）"
        elif delta_b > 0.1:
            verdict = "🟡 わずかに有効（0.1-0.5pt 改善）"
        else:
            verdict = "⚠️ 効果ほぼなし"

        print(f"\n{ward} 病棟:")
        print(f"  現仕様 (翌日繰越のみ) で平均稼働率 {delta_b:+.2f}pt → {verdict}")
        print(f"  理論上限 (完全均等分散) は {delta_c:+.2f}pt の改善が可能")


if __name__ == "__main__":
    main()
