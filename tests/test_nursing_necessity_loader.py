"""scripts/nursing_necessity_loader.py の単体テスト."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from nursing_necessity_loader import (  # noqa: E402
    DEFAULT_CSV_PATH,
    WARDS,
    calculate_monthly_summary,
    calculate_rolling_3month,
    calculate_yearly_average,
    detect_threshold_breaches,
    load_nursing_necessity,
)


# ---------------------------------------------------------------------------
# load_nursing_necessity
# ---------------------------------------------------------------------------

class TestLoadNursingNecessity:
    """CSV ロード."""

    def test_デフォルトパスから読み込み成功(self):
        df = load_nursing_necessity()
        assert len(df) > 0, "data/nursing_necessity_2025fy.csv が読めない"

    def test_期間が_2025_04_から_2026_03(self):
        df = load_nursing_necessity()
        assert df["date"].min().date() == date(2025, 4, 1)
        assert df["date"].max().date() == date(2026, 3, 31)

    def test_病棟は_5F_6F_合計_の_3種類(self):
        df = load_nursing_necessity()
        assert set(df["ward"].unique()) == {"5F", "6F", "合計"}

    def test_必要列が揃っている(self):
        df = load_nursing_necessity()
        required = ["date", "ward", "I_total", "I_pass1", "II_total", "II_pass1", "ym"]
        for col in required:
            assert col in df.columns, f"列 {col} が存在しない"

    def test_存在しないパスは空DF(self):
        df = load_nursing_necessity(Path("/tmp/nonexistent_xxx.csv"))
        assert df.empty

    def test_ym列がYYYY_MM形式(self):
        df = load_nursing_necessity()
        # サンプリング
        for ym in df["ym"].head(5):
            assert len(ym) == 7  # YYYY-MM
            assert ym[4] == "-"


# ---------------------------------------------------------------------------
# calculate_monthly_summary
# ---------------------------------------------------------------------------

class TestCalculateMonthlySummary:
    """月次集計."""

    def test_全月_全病棟が出力される(self):
        df = load_nursing_necessity()
        monthly = calculate_monthly_summary(df)
        assert len(monthly) == 12 * 3  # 12 ヶ月 × 3 病棟

    def test_達成判定列が付与される(self):
        df = load_nursing_necessity()
        monthly = calculate_monthly_summary(df)
        for col in ["I_meets_legacy", "I_meets_new", "II_meets_legacy", "II_meets_new"]:
            assert col in monthly.columns

    def test_既知値_5F_2026_03_Ⅰ_は_18_61percent(self):
        """初期解析で確認した値と一致するか."""
        df = load_nursing_necessity()
        monthly = calculate_monthly_summary(df)
        row = monthly[(monthly["ym"] == "2026-03") & (monthly["ward"] == "5F")]
        assert len(row) == 1
        rate_pct = row["I_rate1"].iloc[0] * 100
        assert rate_pct == pytest.approx(18.61, abs=0.1)

    def test_既知値_6F_2026_02_Ⅰ_は_10_12percent(self):
        df = load_nursing_necessity()
        monthly = calculate_monthly_summary(df)
        row = monthly[(monthly["ym"] == "2026-02") & (monthly["ward"] == "6F")]
        rate_pct = row["I_rate1"].iloc[0] * 100
        assert rate_pct == pytest.approx(10.12, abs=0.1)

    def test_空DFでも例外なし(self):
        result = calculate_monthly_summary(pd.DataFrame())
        assert result.empty


# ---------------------------------------------------------------------------
# calculate_yearly_average
# ---------------------------------------------------------------------------

class TestCalculateYearlyAverage:
    """12 ヶ月通算平均."""

    def test_3病棟分が出力される(self):
        df = load_nursing_necessity()
        avg = calculate_yearly_average(df)
        assert len(avg) == 3
        assert set(avg["ward"]) == set(WARDS)

    def test_既知値_5F_Ⅰ平均_18_21percent(self):
        df = load_nursing_necessity()
        avg = calculate_yearly_average(df)
        row = avg[avg["ward"] == "5F"]
        rate_pct = row["I_rate1_avg"].iloc[0] * 100
        assert rate_pct == pytest.approx(18.21, abs=0.1)

    def test_既知値_6F_Ⅰ平均_16_06percent(self):
        df = load_nursing_necessity()
        avg = calculate_yearly_average(df)
        row = avg[avg["ward"] == "6F"]
        rate_pct = row["I_rate1_avg"].iloc[0] * 100
        assert rate_pct == pytest.approx(16.06, abs=0.1)

    def test_新基準ギャップが計算される(self):
        df = load_nursing_necessity()
        avg = calculate_yearly_average(df)
        row = avg[avg["ward"] == "6F"]
        # 6F Ⅰ 16.06% は新19% に -2.94pt 未達
        assert row["gap_I_new"].iloc[0] < 0
        assert row["gap_I_new"].iloc[0] == pytest.approx(0.1606 - 0.19, abs=0.005)


# ---------------------------------------------------------------------------
# calculate_rolling_3month
# ---------------------------------------------------------------------------

class TestCalculateRolling3Month:
    """直近 3 ヶ月 rolling."""

    def test_3病棟分が返る(self):
        df = load_nursing_necessity()
        result = calculate_rolling_3month(df)
        for ward in WARDS:
            assert ward in result

    def test_最新3ヶ月の月リストが返る(self):
        df = load_nursing_necessity()
        result = calculate_rolling_3month(df)
        # 最新 = 2026-03 から逆算
        assert result["months"] == ["2026-01", "2026-02", "2026-03"]

    def test_today指定で3ヶ月窓が動く(self):
        df = load_nursing_necessity()
        result = calculate_rolling_3month(df, today=date(2025, 9, 30))
        # 2025-09 を含む 3 ヶ月 = 7,8,9
        assert result["months"] == ["2025-07", "2025-08", "2025-09"]

    def test_current_threshold_が含まれる(self):
        df = load_nursing_necessity()
        result = calculate_rolling_3month(df, today=date(2026, 5, 31))
        assert result["current_threshold_I"] == 0.16  # transitional 中
        result = calculate_rolling_3month(df, today=date(2026, 6, 1))
        assert result["current_threshold_I"] == 0.19  # 本則適用後

    def test_空DFでも例外なし(self):
        result = calculate_rolling_3month(pd.DataFrame())
        assert result == {}


# ---------------------------------------------------------------------------
# detect_threshold_breaches
# ---------------------------------------------------------------------------

class TestDetectThresholdBreaches:
    """基準割れ検出."""

    def test_当院データで複数の基準割れが検出される(self):
        df = load_nursing_necessity()
        monthly = calculate_monthly_summary(df)
        breaches = detect_threshold_breaches(monthly)
        assert len(breaches) > 0, "当院データには基準割れがあるはず"

    def test_合計行は除外される(self):
        df = load_nursing_necessity()
        monthly = calculate_monthly_summary(df)
        breaches = detect_threshold_breaches(monthly)
        for b in breaches:
            assert b["ward"] != "合計"

    def test_両基準未達はseverity_fail_both(self):
        df = load_nursing_necessity()
        monthly = calculate_monthly_summary(df)
        breaches = detect_threshold_breaches(monthly)
        # 6F-Ⅱ 2026-02 = 6.03% は両未達のはず
        target = [b for b in breaches if b["ym"] == "2026-02" and b["ward"] == "6F" and b["necessity_type"] == "II"]
        assert len(target) == 1
        assert target[0]["severity"] == "fail_both"

    def test_新基準のみ未達はseverity_fail_new_only(self):
        df = load_nursing_necessity()
        monthly = calculate_monthly_summary(df)
        breaches = detect_threshold_breaches(monthly)
        # 5F-Ⅰ 2025-04 = 22.64% は両達成 → breach に含まれない
        # 5F-Ⅰ 2026-03 = 18.61% は旧16%達成、新19%未達 → fail_new_only
        target = [b for b in breaches if b["ym"] == "2026-03" and b["ward"] == "5F" and b["necessity_type"] == "I"]
        assert len(target) == 1
        assert target[0]["severity"] == "fail_new_only"

    def test_空DFでも例外なし(self):
        result = detect_threshold_breaches(pd.DataFrame())
        assert result == []
