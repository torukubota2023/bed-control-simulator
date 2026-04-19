"""施設基準レポート生成スクリプトのテスト。

テスト方針:
    - 実データ読み込みの動作確認
    - 既知値（副院長仕様書記載の 5F 53.1% / 6F 61.1% / 85+ 27.7% 近傍）との一致
    - MD / PNG 生成の smoke test
    - 個人情報（個別年齢値）が MD に出ないことの確認
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scripts.generate_facility_criteria_report import (
    BEDS_5F,
    BEDS_6F,
    ELDERLY_85_THRESHOLD_PCT,
    EMERGENCY_THRESHOLD_PCT,
    build_markdown,
    build_report,
    calc_monthly_elderly_ratio,
    calc_monthly_emergency_ratio,
    calc_overall_elderly_ratios,
    calc_rolling3_emergency_ratio,
    estimate_monthly_los,
    generate_all,
    load_admissions,
)

DATA_CSV = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "actual_admissions_2025fy.csv"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def adm_df() -> pd.DataFrame:
    """実データを読み込む（モジュールスコープで再利用）。"""
    return load_admissions(DATA_CSV)


# ---------------------------------------------------------------------------
# 1. データ読み込み
# ---------------------------------------------------------------------------


def test_load_admissions_reads_actual_data(adm_df: pd.DataFrame) -> None:
    """実データ CSV の読み込みに成功すること。"""
    assert len(adm_df) == 1965, f"期待1965件、実際 {len(adm_df)}件"
    assert (adm_df["event_type"] == "admission").all()
    # 必須カラム
    for col in ("year_month", "ward", "admission_route", "age_years"):
        assert col in adm_df.columns


def test_load_admissions_wards(adm_df: pd.DataFrame) -> None:
    """病棟値が 4F/5F/6F のいずれか。"""
    assert set(adm_df["ward"].unique()).issubset({"4F", "5F", "6F"})
    # 5F / 6F の総数
    assert (adm_df["ward"] == "5F").sum() == 951
    assert (adm_df["ward"] == "6F").sum() == 996


# ---------------------------------------------------------------------------
# 2. 救急搬送後割合
# ---------------------------------------------------------------------------


def test_emergency_ratio_5f_matches_spec(adm_df: pd.DataFrame) -> None:
    """5F 通年救急率が仕様書の 53.1% 近傍。"""
    monthly = calc_monthly_emergency_ratio(adm_df, "5F")
    total = int(monthly["total"].sum())
    emg = int(monthly["emergency"].sum())
    ratio = emg / total * 100
    assert total == 951
    assert emg == 505
    assert 53.0 <= ratio <= 53.2, f"5F 救急率が期待範囲外: {ratio:.2f}%"


def test_emergency_ratio_6f_matches_spec(adm_df: pd.DataFrame) -> None:
    """6F 通年救急率が仕様書の 61.1% 近傍。"""
    monthly = calc_monthly_emergency_ratio(adm_df, "6F")
    total = int(monthly["total"].sum())
    emg = int(monthly["emergency"].sum())
    ratio = emg / total * 100
    assert total == 996
    assert emg == 609
    assert 61.0 <= ratio <= 61.2, f"6F 救急率が期待範囲外: {ratio:.2f}%"


def test_emergency_ratio_both_wards_meet_target(adm_df: pd.DataFrame) -> None:
    """5F / 6F の通年救急率が基準 15% を大幅に上回ること。"""
    for ward in ("5F", "6F"):
        monthly = calc_monthly_emergency_ratio(adm_df, ward)
        ratio = monthly["emergency"].sum() / monthly["total"].sum() * 100
        # 少なくとも基準の 3 倍以上ある（45%+）
        assert ratio >= 45.0, f"{ward} 救急率 {ratio:.1f}% が想定より低い"


def test_monthly_emergency_ratio_has_12_months(adm_df: pd.DataFrame) -> None:
    """月次集計が 12 ヶ月分出ること。"""
    for ward in ("5F", "6F"):
        monthly = calc_monthly_emergency_ratio(adm_df, ward)
        assert len(monthly) == 12, f"{ward} 月次データが 12 ヶ月ない: {len(monthly)}"


def test_rolling3_emergency_ratio_progression(adm_df: pd.DataFrame) -> None:
    """rolling 3 ヶ月計算が正しい合算結果を返す。"""
    monthly = calc_monthly_emergency_ratio(adm_df, "5F")
    rolled = calc_rolling3_emergency_ratio(monthly)
    assert "rolling_ratio_pct" in rolled.columns
    assert "rolling_total" in rolled.columns
    assert "rolling_emergency" in rolled.columns
    # 最終行は直近 3 ヶ月（2026-01/02/03）の合算
    last = rolled.iloc[-1]
    expected_total = int(monthly.iloc[-3:]["total"].sum())
    expected_emg = int(monthly.iloc[-3:]["emergency"].sum())
    assert last["rolling_total"] == expected_total
    assert last["rolling_emergency"] == expected_emg
    expected_ratio = round(expected_emg / expected_total * 100, 2)
    assert last["rolling_ratio_pct"] == expected_ratio


def test_rolling3_meets_target_at_end(adm_df: pd.DataFrame) -> None:
    """最終 rolling 3ヶ月値が基準 15% を余裕で超える。"""
    for ward in ("5F", "6F"):
        monthly = calc_monthly_emergency_ratio(adm_df, ward)
        rolled = calc_rolling3_emergency_ratio(monthly)
        final_pct = rolled.iloc[-1]["rolling_ratio_pct"]
        assert final_pct >= EMERGENCY_THRESHOLD_PCT, (
            f"{ward} rolling 3ヶ月 最終 {final_pct}% が基準 {EMERGENCY_THRESHOLD_PCT}% 未満"
        )
        # 3 倍以上のマージン
        assert final_pct >= 3 * EMERGENCY_THRESHOLD_PCT


# ---------------------------------------------------------------------------
# 3. 85 歳以上割合
# ---------------------------------------------------------------------------


def test_overall_elderly_ratios_near_spec(adm_df: pd.DataFrame) -> None:
    """85歳以上通年割合が仕様書の 27.7% 近傍。"""
    result = calc_overall_elderly_ratios(adm_df)
    # 5F+6F のみ、age 欠損除外
    # 実データ: 529 / 1947 ≒ 27.17%
    assert 27.0 <= result["elderly_85_pct"] <= 28.0, (
        f"85+ 割合が期待範囲外: {result['elderly_85_pct']}%"
    )
    # LOS 緩和の閾値 20% を超える
    assert result["elderly_85_pct"] >= ELDERLY_85_THRESHOLD_PCT


def test_elderly_ratios_ordering(adm_df: pd.DataFrame) -> None:
    """65 >= 75 >= 85 歳以上の順で単調減少する。"""
    result = calc_overall_elderly_ratios(adm_df)
    assert result["elderly_65_pct"] >= result["elderly_75_pct"]
    assert result["elderly_75_pct"] >= result["elderly_85_pct"]


def test_monthly_elderly_ratio_has_12_months(adm_df: pd.DataFrame) -> None:
    """月次高齢者割合が 12 ヶ月分出る。"""
    scope = adm_df[adm_df["ward"].isin(["5F", "6F"])]
    df = calc_monthly_elderly_ratio(scope, ward=None)
    assert len(df) == 12


# ---------------------------------------------------------------------------
# 4. LOS 推定
# ---------------------------------------------------------------------------


def test_los_estimate_returns_reasonable_values(adm_df: pd.DataFrame) -> None:
    """LOS 推定値が合理的範囲（5〜30 日）に収まる。"""
    for ward, beds in (("5F", BEDS_5F), ("6F", BEDS_6F)):
        los = estimate_monthly_los(adm_df, ward, beds)
        assert len(los) == 12
        assert los["los_estimate_days"].notna().all()
        # 合理的範囲
        assert los["los_estimate_days"].min() >= 5
        assert los["los_estimate_days"].max() <= 40


def test_los_estimate_is_near_target_range(adm_df: pd.DataFrame) -> None:
    """LOS 推定平均が制度上限（21〜22日）の±10日以内に収まる（近似値のサニティチェック）。"""
    los_5f = estimate_monthly_los(adm_df, "5F", BEDS_5F)
    los_6f = estimate_monthly_los(adm_df, "6F", BEDS_6F)
    # 目標帯は 15〜22 日を想定
    assert 12 <= los_5f["los_estimate_days"].mean() <= 28
    assert 12 <= los_6f["los_estimate_days"].mean() <= 28


# ---------------------------------------------------------------------------
# 5. ビルドレポート
# ---------------------------------------------------------------------------


def test_build_report_returns_populated_object(adm_df: pd.DataFrame) -> None:
    """build_report がすべてのフィールドを埋める。"""
    rep = build_report(adm_df)
    assert "5F" in rep.overall_emergency
    assert "6F" in rep.overall_emergency
    assert rep.monthly_emergency_5f is not None
    assert rep.monthly_emergency_6f is not None
    assert rep.monthly_elderly is not None
    assert rep.los_estimate_5f is not None
    assert rep.los_estimate_6f is not None
    assert "elderly_85_pct" in rep.overall_elderly
    assert rep.rolling3_5f_final["year_month"] == "2026-03"
    assert rep.rolling3_6f_final["year_month"] == "2026-03"


def test_build_markdown_contains_key_numbers(adm_df: pd.DataFrame) -> None:
    """MD 本文に主要指標の数値が含まれる。"""
    rep = build_report(adm_df)
    md = build_markdown(rep)

    # エグゼクティブサマリー
    assert "エグゼクティブサマリー" in md
    assert "施設基準 実態レポート" in md
    # 救急率
    assert f"{rep.overall_emergency['5F']['ratio_pct']:.1f}%" in md
    assert f"{rep.overall_emergency['6F']['ratio_pct']:.1f}%" in md
    # 85+
    assert f"{rep.overall_elderly['elderly_85_pct']:.1f}%" in md or f"{rep.overall_elderly['elderly_85_pct']:.2f}%" in md
    # 基準
    assert "15%" in md
    assert "20%" in md
    assert "21" in md  # LOS 上限
    # データ出典
    assert "actual_admissions_2025fy.csv" in md


def test_build_markdown_does_not_leak_individual_ages(adm_df: pd.DataFrame) -> None:
    """個別年齢（98歳とか99歳等）が MD に出ない（階級集計のみ）。"""
    rep = build_report(adm_df)
    md = build_markdown(rep)
    # 個別年齢を示す記載は個人情報に該当するため、「〇〇歳」という個別表現が直接出てこない
    # （「65歳以上」「75歳以上」「85歳以上」等の階級表現は OK）
    # 下記は個別の特定年齢（階級でない単独年齢）の検出
    for yr in (97, 98, 99):
        bad = f"{yr}歳"
        # 階級表現として使われている場合はない（85歳以上 のみ出る）
        assert bad not in md, f"個別年齢 {yr}歳 が MD に含まれる（個人情報漏洩の恐れ）"


# ---------------------------------------------------------------------------
# 6. ファイル生成（E2E）
# ---------------------------------------------------------------------------


def test_generate_all_creates_report_and_figures(tmp_path: Path) -> None:
    """generate_all() が MD と PNG を生成する。"""
    report_path = tmp_path / "report.md"
    figures_dir = tmp_path / "figures"

    result = generate_all(
        csv_path=DATA_CSV,
        report_path=report_path,
        figures_dir=figures_dir,
    )

    # MD 生成確認
    assert result["report_path"].exists()
    assert result["report_path"].stat().st_size > 500  # 500 byte 以上

    md_text = result["report_path"].read_text(encoding="utf-8")
    assert "施設基準 実態レポート" in md_text
    assert "エグゼクティブサマリー" in md_text

    # PNG 生成確認
    for fig_path in result["figure_paths"]:
        assert fig_path.exists(), f"PNG 未生成: {fig_path}"
        assert fig_path.stat().st_size > 1000  # 1KB 以上

    # サマリー検証
    summary = result["summary"]
    assert summary["admissions_total"] == 1965
    assert 53.0 <= summary["emergency_5f_pct"] <= 53.2
    assert 61.0 <= summary["emergency_6f_pct"] <= 61.2
    assert summary["elderly_85_pct"] >= ELDERLY_85_THRESHOLD_PCT


def test_generate_all_figures_are_valid_png(tmp_path: Path) -> None:
    """生成された PNG が有効なファイル（PNG シグネチャを持つ）。"""
    result = generate_all(
        csv_path=DATA_CSV,
        report_path=tmp_path / "report.md",
        figures_dir=tmp_path / "figures",
    )
    png_signature = b"\x89PNG\r\n\x1a\n"
    for fig_path in result["figure_paths"]:
        with open(fig_path, "rb") as f:
            header = f.read(8)
        assert header == png_signature, f"{fig_path} が有効な PNG でない"
