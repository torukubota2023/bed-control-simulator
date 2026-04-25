"""看護必要度の基準値モジュール — 2026-06-01 transitional 切替対応.

地域包括医療病棟入院料の重症度、医療・看護必要度に関する基準値を、
令和6改定（〜2026-05-31）と令和8改定（2026-06-01〜）で切り替える。

切替日:
    - ~2026-05-31: 必要度Ⅰ ≥ 16%、必要度Ⅱ ≥ 14%
    - 2026-06-01~: 必要度Ⅰ ≥ 19%、必要度Ⅱ ≥ 18%

経過措置終了日（2026-05-31）は救急15% と共通のため、
``emergency_ratio.is_transitional_period()`` を再利用する。

出典:
    - 厚労省「令和8年度診療報酬改定」
    - https://gemmed.ghc-j.com/?p=72897
    - https://med-cpa.jp/hoshu-8/

Streamlit に依存しない pure function のみ。
"""

from __future__ import annotations

from datetime import date
from typing import Optional, Tuple

# 救急15% と同じ経過措置終了日を使う（既存定数を再利用）
from emergency_ratio import is_transitional_period, days_until_transitional_end  # noqa: F401

# ---------------------------------------------------------------------------
# 基準値定数
# ---------------------------------------------------------------------------

# 令和6改定（〜2026-05-31）
THRESHOLD_I_LEGACY: float = 0.16   # 必要度Ⅰ 該当患者割合 16%
THRESHOLD_II_LEGACY: float = 0.14  # 必要度Ⅱ 該当患者割合 14%

# 令和8改定（2026-06-01〜）
THRESHOLD_I_NEW: float = 0.19      # 必要度Ⅰ 該当患者割合 19% (+3pt)
THRESHOLD_II_NEW: float = 0.18     # 必要度Ⅱ 該当患者割合 18% (+4pt)

# 救急患者応需係数（令和8改定で新設）の上限
# 「該当患者割合 + 応需係数 ≥ 基準」で判定
EMERGENCY_RESPONSE_COEFFICIENT_RATE: float = 0.005  # 病床あたり年間救急搬送 × 0.005
EMERGENCY_RESPONSE_COEFFICIENT_CAP: float = 0.10    # 上限 10%


NecessityType = str  # "I" または "II"


# ---------------------------------------------------------------------------
# 救急患者応需係数（2026 改定で新設）
# ---------------------------------------------------------------------------

def calculate_emergency_response_coefficient(
    annual_emergency_count: int,
    bed_count: int,
    eligible_admission_ratio: float = 1.0,
) -> dict:
    """救急患者応需係数を計算する.

    制度ルール（令和8改定 疑義解釈4）:
        係数 = (年間救急搬送件数 × 該当病床入院割合 ÷ 病床数) × 0.005
        上限 = 10%（0.10）

    Args:
        annual_emergency_count: 当該医療機関全体における直近 1 年間の救急搬送受入件数
        bed_count: 該当入院基本料算定病床数（地域包括医療病棟の病床数）
        eligible_admission_ratio: 救急搬送患者のうち該当病床に入院した割合
            （当院のように救急がほぼ地包病棟のみに入る場合は 1.0）

    Returns:
        dict:
            - ``per_bed_count``: 病床あたり年間救急搬送件数
            - ``coefficient_raw``: 計算値（capping 前）
            - ``coefficient``: 最終係数（上限 10% で cap）
            - ``capped``: 上限に達したかどうか
            - ``annual_emergency_count``: 入力値
            - ``bed_count``: 入力値
            - ``eligible_admission_ratio``: 入力値

    Raises:
        ValueError: bed_count <= 0
    """
    if bed_count <= 0:
        raise ValueError(f"bed_count は正の整数。受信: {bed_count}")
    if annual_emergency_count < 0:
        raise ValueError(f"annual_emergency_count は非負。受信: {annual_emergency_count}")
    if not (0.0 <= eligible_admission_ratio <= 1.0):
        raise ValueError(
            f"eligible_admission_ratio は 0.0〜1.0。受信: {eligible_admission_ratio}"
        )

    per_bed = (annual_emergency_count * eligible_admission_ratio) / bed_count
    raw = per_bed * EMERGENCY_RESPONSE_COEFFICIENT_RATE
    capped = raw > EMERGENCY_RESPONSE_COEFFICIENT_CAP
    coefficient = min(raw, EMERGENCY_RESPONSE_COEFFICIENT_CAP)

    return {
        "per_bed_count": per_bed,
        "coefficient_raw": raw,
        "coefficient": coefficient,
        "capped": capped,
        "annual_emergency_count": annual_emergency_count,
        "bed_count": bed_count,
        "eligible_admission_ratio": eligible_admission_ratio,
    }


def get_threshold(
    necessity_type: NecessityType,
    today: Optional[date] = None,
) -> float:
    """指定日時点の看護必要度基準値を返す.

    Args:
        necessity_type: "I" または "II"
        today: 基準日。省略時は ``date.today()``。

    Returns:
        基準値（小数、例: 0.16 = 16%）

    Raises:
        ValueError: necessity_type が "I" / "II" 以外
    """
    if necessity_type not in ("I", "II"):
        raise ValueError(f"necessity_type は 'I' または 'II' のみ。受信: {necessity_type!r}")

    in_legacy = is_transitional_period(today)
    if necessity_type == "I":
        return THRESHOLD_I_LEGACY if in_legacy else THRESHOLD_I_NEW
    return THRESHOLD_II_LEGACY if in_legacy else THRESHOLD_II_NEW


def get_both_thresholds(necessity_type: NecessityType) -> Tuple[float, float]:
    """旧基準と新基準の両方を返す（並列表示用）.

    Args:
        necessity_type: "I" または "II"

    Returns:
        (legacy_threshold, new_threshold) の tuple

    Raises:
        ValueError: necessity_type が "I" / "II" 以外
    """
    if necessity_type not in ("I", "II"):
        raise ValueError(f"necessity_type は 'I' または 'II' のみ。受信: {necessity_type!r}")

    if necessity_type == "I":
        return (THRESHOLD_I_LEGACY, THRESHOLD_I_NEW)
    return (THRESHOLD_II_LEGACY, THRESHOLD_II_NEW)


def evaluate_compliance(
    rate: float,
    necessity_type: NecessityType,
    today: Optional[date] = None,
    emergency_coefficient: float = 0.0,
) -> dict:
    """達成率を旧基準・新基準と照合し、判定結果を返す.

    Args:
        rate: 該当患者割合（小数、例: 0.182 = 18.2%）
        necessity_type: "I" または "II"
        today: 基準日。省略時は ``date.today()``。
        emergency_coefficient: 救急患者応需係数（小数、例: 0.0148 = 1.48%）.
            令和8改定で導入。``calculate_emergency_response_coefficient()`` の戻り値の
            ``coefficient`` キーをそのまま渡す。新基準判定でのみ加算される
            （旧基準には適用されない）。

    Returns:
        dict with keys:
            - ``rate``: 入力値
            - ``adjusted_rate_new``: 新基準判定で使う値（rate + emergency_coefficient）
            - ``emergency_coefficient``: 入力された係数
            - ``legacy_threshold``: 旧基準
            - ``new_threshold``: 新基準
            - ``current_threshold``: 現在適用される基準（today に依存）
            - ``meets_legacy``: 旧基準達成（rate ≥ legacy）
            - ``meets_new``: 新基準達成（adjusted_rate_new ≥ new）
            - ``meets_new_without_coefficient``: 係数なしで新基準達成するか（rate ≥ new）
            - ``meets_current``: 現在基準達成（today で動的に決定）
            - ``gap_legacy``: 旧基準とのギャップ（rate - legacy）
            - ``gap_new``: 新基準とのギャップ（adjusted_rate_new - new）
            - ``status``: "ok_new" / "ok_new_with_coefficient" / "ok_legacy_only" / "fail"
    """
    legacy, new = get_both_thresholds(necessity_type)
    current = get_threshold(necessity_type, today)
    adjusted_rate_new = rate + emergency_coefficient

    meets_legacy = rate >= legacy
    meets_new_without_coef = rate >= new
    meets_new = adjusted_rate_new >= new

    # current 判定: 経過措置中は legacy（係数は新基準でのみ意味を持つ）、
    # 本則適用後は new（係数加算後で判定）
    if is_transitional_period(today):
        meets_current = meets_legacy
    else:
        meets_current = meets_new

    if meets_new_without_coef:
        status = "ok_new"
    elif meets_new:
        status = "ok_new_with_coefficient"
    elif meets_legacy:
        status = "ok_legacy_only"
    else:
        status = "fail"

    return {
        "rate": rate,
        "adjusted_rate_new": adjusted_rate_new,
        "emergency_coefficient": emergency_coefficient,
        "legacy_threshold": legacy,
        "new_threshold": new,
        "current_threshold": current,
        "meets_legacy": meets_legacy,
        "meets_new": meets_new,
        "meets_new_without_coefficient": meets_new_without_coef,
        "meets_current": meets_current,
        "gap_legacy": rate - legacy,
        "gap_new": adjusted_rate_new - new,
        "status": status,
    }
