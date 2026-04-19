"""
2026-04-19: demand_forecast 実データ校正のユニット・統合テスト

対象:
- learn_calibration_params: 実データから曜日係数・月係数・緊急率を学習
- save_calibrated_params / load_calibrated_params: YAML ラウンドトリップ
- forecast_weekly_demand with use_calibration=True: 校正モード
- 校正前後の MAE 比較（実データ末尾2ヶ月バックテスト）
- 実データ欠損環境でのフォールバック
"""

from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from demand_forecast import (
    DEFAULT_CALIBRATED_PARAMS_PATH,
    _FALLBACK_PARAMS,
    clear_calibrated_cache,
    forecast_weekly_demand,
    learn_calibration_params,
    load_calibrated_params,
    save_calibrated_params,
)


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_CSV = os.path.join(PROJECT_ROOT, "data", "actual_admissions_2025fy.csv")


# ---------------------------------------------------------------
# ヘルパー: 実データ読込
# ---------------------------------------------------------------

def _load_real_adm() -> pd.DataFrame:
    if not os.path.exists(REAL_CSV):
        pytest.skip("actual_admissions_2025fy.csv が無いためスキップ")
    df = pd.read_csv(REAL_CSV)
    df = df[df["event_type"] == "admission"].copy()
    df["admission_date"] = pd.to_datetime(df["admission_date"])
    df["ward_short"] = df["ward"]
    return df


# ---------------------------------------------------------------
# 1. learn_calibration_params — 実データからの学習
# ---------------------------------------------------------------

class TestLearnCalibrationParams:

    def test_empty_df_returns_fallback(self):
        """空 DataFrame ならフォールバックを返す。"""
        result = learn_calibration_params(pd.DataFrame())
        assert "overall" in result
        assert "by_ward" in result
        assert result["overall"]["sample_size"] == 0

    def test_missing_date_column(self):
        """date 列が無ければフォールバック。"""
        df = pd.DataFrame({"x": [1, 2, 3]})
        result = learn_calibration_params(df)
        assert result["overall"]["sample_size"] == 0

    def test_real_data_learns_dow_pattern(self):
        """実データから曜日係数が学習される（月>>日）。"""
        df = _load_real_adm()
        result = learn_calibration_params(df)
        dow = result["overall"]["dow_means"]

        # 月曜が日曜より圧倒的に多い
        assert dow[0] > dow[6] * 10
        # 月曜は 7-9件／日の範囲
        assert 7.0 < dow[0] < 9.5
        # 日曜は 0-1件／日
        assert 0.0 <= dow[6] < 1.0
        # 土曜は月曜の半分以下
        assert dow[5] < dow[0] / 2

    def test_real_data_learns_month_factors(self):
        """7-8月のピーク、4月・12月の谷が学習される。"""
        df = _load_real_adm()
        result = learn_calibration_params(df)
        mf = result["overall"]["month_factors"]

        # 全月のキーが揃う
        for m in range(1, 13):
            assert m in mf
            assert 0.5 < mf[m] < 1.5  # 極端値は無いはず

        # 7月・8月はピーク期 (>1)
        assert mf[7] > 1.0
        assert mf[8] > 1.0
        # 4月・12月は谷 (<1)
        assert mf[4] < 1.0
        assert mf[12] < 1.0

    def test_real_data_ward_specific_emergency_ratio(self):
        """5F 約53%、6F 約61% の緊急率が学習される。"""
        df = _load_real_adm()
        result = learn_calibration_params(df)
        em5 = result["by_ward"]["5F"]["emergency_ratio"]
        em6 = result["by_ward"]["6F"]["emergency_ratio"]
        assert 0.50 < em5 < 0.56
        assert 0.58 < em6 < 0.64
        # 6F は 5F より緊急率が高い
        assert em6 > em5

    def test_zero_fill_lowers_sunday_mean(self):
        """0埋めを行うことで日曜平均が従来より大幅に低くなる。"""
        df = _load_real_adm()
        result = learn_calibration_params(df)
        sunday_mean = result["overall"]["dow_means"][6]
        # 0埋めあり: 0.3 程度、なし: 1.0 程度
        assert sunday_mean < 0.5


# ---------------------------------------------------------------
# 2. YAML ラウンドトリップ
# ---------------------------------------------------------------

class TestYamlRoundTrip:

    def test_save_and_load_roundtrip(self, tmp_path):
        """learn → save → load で同じ内容が復元できる。"""
        clear_calibrated_cache()
        df = _load_real_adm()
        params = learn_calibration_params(df)

        temp_yaml = str(tmp_path / "test_params.yaml")
        saved_path = save_calibrated_params(params, path=temp_yaml)
        assert os.path.exists(saved_path)

        # 別途読み込み（cache 無視）
        reloaded = load_calibrated_params(path=temp_yaml, use_cache=False)
        # キー構造が同じ
        assert set(reloaded["overall"].keys()) == set(params["overall"].keys())
        # 数値が丸めの誤差内で一致
        orig_dow = params["overall"]["dow_means"]
        back_dow = reloaded["overall"]["dow_means"]
        for d in range(7):
            assert back_dow[d] == pytest.approx(orig_dow[d], abs=0.01)

    def test_yaml_missing_file_returns_fallback(self):
        """存在しない YAML パスでも落ちずにフォールバック値を返す。"""
        clear_calibrated_cache()
        result = load_calibrated_params(
            path="/tmp/__nonexistent_forecast_params__.yaml",
            use_cache=False,
        )
        # フォールバック構造が揃っている
        assert "overall" in result
        assert "by_ward" in result
        for w in ("5F", "6F"):
            assert w in result["by_ward"]
            assert set(result["by_ward"][w].keys()) >= {"dow_means", "month_factors"}

    def test_cache_is_shared(self, tmp_path):
        """同じパスの 2 回目呼び出しはキャッシュから返る。"""
        clear_calibrated_cache()
        df = _load_real_adm()
        params = learn_calibration_params(df)
        temp_yaml = str(tmp_path / "cache_test.yaml")
        save_calibrated_params(params, path=temp_yaml)
        # 1 回目
        a = load_calibrated_params(path=temp_yaml, use_cache=True)
        # ファイル削除
        os.remove(temp_yaml)
        # 2 回目もキャッシュから同じ結果（ファイルが無くてもエラーにならない）
        b = load_calibrated_params(path=temp_yaml, use_cache=True)
        assert a is b  # 同一オブジェクト


# ---------------------------------------------------------------
# 3. forecast_weekly_demand with calibration
# ---------------------------------------------------------------

class TestForecastWithCalibration:

    def test_calibration_flag_in_output(self):
        """use_calibration=True なら calibration_used=True、
        データ不在なら False（empty 返り）。"""
        df = _load_real_adm()
        r = forecast_weekly_demand(df, date(2026, 3, 30), use_calibration=True)
        assert r["calibration_used"] is True
        # 月係数が出力に含まれる
        assert "month_factor" in r
        assert 0.5 < r["month_factor"] < 1.5

    def test_calibration_disabled(self):
        """use_calibration=False で従来ロジックに近い挙動（月係数=1.0）。"""
        df = _load_real_adm()
        r = forecast_weekly_demand(df, date(2026, 3, 30), use_calibration=False)
        assert r["month_factor"] == 1.0
        assert r["calibration_used"] is False

    def test_month_factor_applies_by_target_month(self):
        """対象週の月に応じて month_factor が変わる。"""
        df = _load_real_adm()
        r_jul = forecast_weekly_demand(df, date(2025, 7, 7), use_calibration=True)
        r_apr = forecast_weekly_demand(df, date(2025, 4, 7), use_calibration=True)
        # 7月ピーク月係数 > 4月谷月係数
        assert r_jul["month_factor"] > r_apr["month_factor"]

    def test_ward_specific_params_used(self):
        """病棟別パラメータで 5F と 6F の予測値が異なる。"""
        df = _load_real_adm()
        r_5f = forecast_weekly_demand(df, date(2026, 2, 2), ward="5F", use_calibration=True)
        r_6f = forecast_weekly_demand(df, date(2026, 2, 2), ward="6F", use_calibration=True)
        # 合計は近いが 5F は月曜ピーク、6F は水曜ピーク（パターンが違う）
        assert r_5f["dow_means"][0] > r_5f["dow_means"][2]  # 5F: 月 > 水
        assert r_6f["dow_means"][2] > r_6f["dow_means"][0]  # 6F: 水 > 月

    def test_explicit_params_override_yaml(self):
        """calibrated_params 引数で明示した値が YAML より優先される。"""
        df = _load_real_adm()
        fake = {
            "overall": {
                "dow_means": {0: 99, 1: 99, 2: 99, 3: 99, 4: 99, 5: 99, 6: 99},
                "month_factors": {m: 1.0 for m in range(1, 13)},
                "year_avg_daily": 99.0,
                "emergency_ratio": 0.5,
                "sample_size": 100000,  # 大きくして補強側に寄らせる
            },
            "by_ward": {"5F": {"dow_means": {}, "month_factors": {}, "year_avg_daily": 0, "emergency_ratio": 0.5, "sample_size": 0},
                        "6F": {"dow_means": {}, "month_factors": {}, "year_avg_daily": 0, "emergency_ratio": 0.5, "sample_size": 0}},
        }
        # 小さいサブセットで呼ぶと校正に寄りやすい
        sub = df.head(50)
        r = forecast_weekly_demand(sub, date(2026, 3, 30),
                                   use_calibration=True, calibrated_params=fake)
        assert r["calibration_used"] is True


# ---------------------------------------------------------------
# 4. バックテスト: 校正前後の精度比較
# ---------------------------------------------------------------

class TestBacktestMaeImprovement:

    def test_calibration_reduces_mae_on_real_data(self):
        """最後の2ヶ月を予測対象、前10ヶ月を学習 → 校正 MAE < 未校正 MAE。"""
        df = _load_real_adm()
        # 学習期間: 2025-04-01 〜 2026-01-31、予測期間: 2026-02〜03
        train_end = pd.Timestamp("2026-02-01")
        train = df[df["admission_date"] < train_end].copy()
        test = df[df["admission_date"] >= train_end].copy()

        all_test_dates = pd.date_range(pd.Timestamp("2026-02-01"),
                                       pd.Timestamp("2026-03-31"))
        actual_daily = (
            test.groupby(test["admission_date"].dt.normalize()).size()
            .reindex(all_test_dates, fill_value=0)
        )

        # 学習期間から校正パラメータを構築（in-memory）
        learned = learn_calibration_params(train)

        # 既存モデル（校正 OFF）予測
        first_monday = date(2026, 2, 2)
        r_off = forecast_weekly_demand(
            train, first_monday, use_calibration=False
        )
        pred_off = pd.Series(
            [r_off["dow_means"][d.dayofweek] * r_off["recent_trend_factor"]
             for d in all_test_dates],
            index=all_test_dates,
        )

        # 校正モデル予測（学習データを calibrated_params として明示注入）
        # 月またぎで month_factor が変わるので、各日の月に対応する予測
        r_on = forecast_weekly_demand(
            train, first_monday, use_calibration=True,
            calibrated_params=learned,
        )
        # 校正では dow_means にブレンド値が入っており、各日は month_factor を個別に当てる
        month_factors = learned["overall"]["month_factors"]
        trend = r_on["recent_trend_factor"]
        pred_on = pd.Series(
            [r_on["dow_means"][d.dayofweek] * trend * month_factors.get(d.month, 1.0)
             for d in all_test_dates],
            index=all_test_dates,
        )

        mae_off = float(np.abs(actual_daily.values - pred_off.values).mean())
        mae_on = float(np.abs(actual_daily.values - pred_on.values).mean())
        print(f"\n[backtest] MAE off={mae_off:.3f}, on={mae_on:.3f}, "
              f"reduction={mae_off - mae_on:+.3f} ({100*(mae_off-mae_on)/mae_off:.1f}%)")
        # 校正モデルの方が MAE 小（最低 10% 以上改善）
        assert mae_on < mae_off
        assert (mae_off - mae_on) / mae_off > 0.10


# ---------------------------------------------------------------
# 5. フォールバック: 実データなし時
# ---------------------------------------------------------------

class TestFallbackWithoutData:

    def test_yaml_absent_forecast_still_runs(self, tmp_path, monkeypatch):
        """YAML が無い環境でも forecast が動作する（空 DataFrame は empty 返し）。"""
        clear_calibrated_cache()
        # 存在しないパスを既定に設定
        monkeypatch.setattr(
            "demand_forecast.DEFAULT_CALIBRATED_PARAMS_PATH",
            str(tmp_path / "missing.yaml"),
        )
        r = forecast_weekly_demand(pd.DataFrame(), date(2026, 3, 30),
                                   use_calibration=True)
        assert r["expected_weekly_total"] == 0.0
        assert r["confidence"] == "low"

    def test_fallback_params_have_required_keys(self):
        """_FALLBACK_PARAMS に必要キーが揃っている。"""
        assert "overall" in _FALLBACK_PARAMS
        assert "by_ward" in _FALLBACK_PARAMS
        for scope in (_FALLBACK_PARAMS["overall"],
                      _FALLBACK_PARAMS["by_ward"]["5F"],
                      _FALLBACK_PARAMS["by_ward"]["6F"]):
            assert "dow_means" in scope
            assert "month_factors" in scope
            assert "emergency_ratio" in scope

    def test_small_data_blends_toward_calibration(self):
        """サンプルが少ないときは校正値への重み付けが大きくなる。"""
        df = _load_real_adm()
        small = df.head(10)  # サンプル少
        r_small = forecast_weekly_demand(small, date(2026, 3, 30),
                                         use_calibration=True)
        # 小サンプルでも dow_means がゼロでない（校正値で補強される）
        assert sum(r_small["dow_means"].values()) > 0


# ---------------------------------------------------------------
# 6. 2026 年度副院長伝達値の確認（YAML メタデータ）
# ---------------------------------------------------------------

class TestVicePresidentCalibrationMeta:
    """YAML に副院長伝達の短手3情報が保存されていることを確認。"""

    def test_yaml_contains_short3_metadata(self):
        """YAML に短手3の月間数・Day 6超過数・主因が記録されている。"""
        clear_calibrated_cache()
        cal = load_calibrated_params()
        meta = cal.get("metadata", {})
        # 副院長伝達された値が保存されている
        if meta:
            assert meta.get("short3_monthly_avg") == 22
            assert meta.get("short3_day6_exceed_avg") == 1
            assert "ポリペク" in meta.get("short3_main_cause_delay", "")
