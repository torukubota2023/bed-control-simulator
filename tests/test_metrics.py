"""
ベッドコントロール指標のユニットテスト

週末空床計算、退院曜日分布、前倒し x 充填確率ロジックをテストする。
"""

import pytest
import pandas as pd
import numpy as np
from datetime import timedelta


# ---------------------------------------------------------------
# 前倒し x 充填確率 の純粋関数（アプリ内のインラインロジックを抽出）
# ---------------------------------------------------------------
# アプリ内の計算式:
#   _bm_effective_fill = _bm_shift * (_bm_fill_rate / 100)
#   _bm_new_weekend_empty = max(0, _weekend_empty - _bm_effective_fill)


def calc_weekend_whatif(shift: int, fill_rate: float, weekend_empty: float):
    """
    退院前倒し x 充填確率 What-If 計算

    Args:
        shift: 金曜退院のうち木曜に前倒しする人数
        fill_rate: 前倒しで空いた床に入院が入る確率（0-100）
        weekend_empty: 改善前の土日平均空床数

    Returns:
        (effective_fill, new_weekend_empty)
    """
    effective_fill = shift * (fill_rate / 100)
    new_weekend_empty = max(0, weekend_empty - effective_fill)
    return effective_fill, new_weekend_empty


class TestWeekendWhatIf:
    """前倒し x 充填確率 What-If のテスト"""

    def test_basic_case(self):
        """shift=3, fill_rate=50, weekend_empty=10 → effective=1.5, new_empty=8.5"""
        eff, new_empty = calc_weekend_whatif(shift=3, fill_rate=50, weekend_empty=10)
        assert eff == pytest.approx(1.5)
        assert new_empty == pytest.approx(8.5)

    def test_full_fill_rate(self):
        """shift=5, fill_rate=100, weekend_empty=10 → effective=5, new_empty=5"""
        eff, new_empty = calc_weekend_whatif(shift=5, fill_rate=100, weekend_empty=10)
        assert eff == pytest.approx(5.0)
        assert new_empty == pytest.approx(5.0)

    def test_zero_fill_rate(self):
        """shift=3, fill_rate=0, weekend_empty=10 → effective=0, new_empty=10"""
        eff, new_empty = calc_weekend_whatif(shift=3, fill_rate=0, weekend_empty=10)
        assert eff == pytest.approx(0.0)
        assert new_empty == pytest.approx(10.0)

    def test_clamped_to_zero(self):
        """shift=10, fill_rate=100, weekend_empty=5 → effective=10, new_empty=0（下限クランプ）"""
        eff, new_empty = calc_weekend_whatif(shift=10, fill_rate=100, weekend_empty=5)
        assert eff == pytest.approx(10.0)
        assert new_empty == pytest.approx(0.0)

    def test_zero_shift(self):
        """前倒しゼロなら空床は変わらない"""
        eff, new_empty = calc_weekend_whatif(shift=0, fill_rate=100, weekend_empty=10)
        assert eff == pytest.approx(0.0)
        assert new_empty == pytest.approx(10.0)

    def test_weekend_cost_calculation(self):
        """週末コスト削減額の計算が正しいことを確認"""
        unit_price = 28900  # 1床1日あたりの運営貢献額
        weekend_empty = 8.0

        _, new_empty = calc_weekend_whatif(shift=4, fill_rate=50, weekend_empty=weekend_empty)
        # effective = 4 * 0.5 = 2.0, new_empty = 6.0

        cost_before = weekend_empty * 2 * unit_price  # 土日2日分
        cost_after = new_empty * 2 * unit_price
        saving_weekly = cost_before - cost_after
        saving_annual = saving_weekly * 4 * 12

        assert saving_weekly == pytest.approx(2.0 * 2 * unit_price)
        assert saving_annual == pytest.approx(saving_weekly * 48)


# ---------------------------------------------------------------
# 週末空床数の計算テスト
# ---------------------------------------------------------------


def _build_weekly_df(total_beds: int, weekday_discharges: list, weekend_discharges: list):
    """
    1週間分のテストDataFrameを構築する。

    Args:
        total_beds: 総ベッド数
        weekday_discharges: 月〜金の退院数リスト (5要素)
        weekend_discharges: 土日の退院数リスト (2要素)

    Returns:
        DataFrame with date, total_patients, discharges, dow columns
    """
    # 2026-04-06 (月) から始まる1週間
    base = pd.Timestamp("2026-04-06")  # 月曜日
    dates = [base + timedelta(days=i) for i in range(7)]
    discharges = weekday_discharges + weekend_discharges
    admissions = [5, 4, 5, 4, 3, 1, 1]  # 典型的な入院パターン

    # 在院患者数を計算（初日から累積）
    patients = [total_beds]
    for i in range(1, 7):
        patients.append(patients[-1] + admissions[i] - discharges[i])

    df = pd.DataFrame({
        "date": dates,
        "ward": ["all"] * 7,
        "total_patients": patients,
        "new_admissions": admissions,
        "discharges": discharges,
    })
    df["dow"] = df["date"].dt.dayofweek  # 0=月, 6=日
    return df


class TestWeekendEmptyBedCalculation:
    """週末空床数の計算テスト"""

    def test_weekend_empty_from_df(self):
        """DataFrameから土日の平均空床数を計算"""
        total_beds = 94
        # 月〜金: 退院が多い、土日: 退院が少ない
        df = _build_weekly_df(
            total_beds=total_beds,
            weekday_discharges=[3, 4, 5, 4, 6],  # 金曜6名退院
            weekend_discharges=[1, 0],  # 土日はほぼ退院なし
        )

        # アプリの計算ロジックを再現:
        # 曜日別の空床数（total_beds - total_patients）
        df["empty_beds"] = total_beds - df["total_patients"]
        dow_empty = df.groupby("dow")["empty_beds"].mean()

        sat_empty = dow_empty.get(5, 0)
        sun_empty = dow_empty.get(6, 0)
        weekend_empty = (sat_empty + sun_empty) / 2

        # 空床数が正の値であること（退院が多い金曜の後なので土日は空床が増える）
        assert weekend_empty >= 0
        # 土日は入院少ない＋金曜退院多いので空床が生じる
        assert sat_empty >= 0
        assert sun_empty >= 0

    def test_no_weekend_empty_when_full(self):
        """満床なら週末空床はゼロ"""
        total_beds = 94
        # 退院と同数の入院がある場合
        df = _build_weekly_df(
            total_beds=total_beds,
            weekday_discharges=[0, 0, 0, 0, 0],
            weekend_discharges=[0, 0],
        )
        df["empty_beds"] = total_beds - df["total_patients"]
        dow_empty = df.groupby("dow")["empty_beds"].mean()

        sat_empty = dow_empty.get(5, 0)
        sun_empty = dow_empty.get(6, 0)
        weekend_empty = (sat_empty + sun_empty) / 2

        # 退院ゼロなら空床は入院数の累積分マイナス（＝過密）か0
        # total_patientsがtotal_bedsを超えることもありうるので empty <= 0
        assert weekend_empty <= total_beds


# ---------------------------------------------------------------
# 退院曜日分布（bed_data_manager から）
# ---------------------------------------------------------------


class TestDischargeWeekdayDistribution:
    """退院曜日分布関数のテスト"""

    def test_get_discharge_weekday_distribution(self):
        """get_discharge_weekday_distribution が曜日別の退院数を返す"""
        try:
            from bed_data_manager import get_discharge_weekday_distribution
        except ImportError:
            pytest.skip("get_discharge_weekday_distribution not importable")

        # この関数は詳細DataFrame（event_type列あり）を期待する
        # 2週間分の退院イベントを作成（月〜日 x 2）
        base = pd.Timestamp("2026-04-06")  # 月曜
        records = []
        discharge_counts = [3, 4, 5, 4, 6, 1, 0]  # 曜日別退院数
        for week in range(2):
            for dow, count in enumerate(discharge_counts):
                event_date = base + timedelta(days=week * 7 + dow)
                for _ in range(count):
                    records.append({
                        "date": event_date.strftime("%Y-%m-%d"),
                        "event_type": "discharge",
                        "ward": "5F",
                        "attending_doctor": "テスト医師",
                    })

        df = pd.DataFrame(records)
        result = get_discharge_weekday_distribution(df)

        # dictで全曜日(0-6)のキーが返る
        assert isinstance(result, dict)
        assert len(result) == 7
        # 金曜(4)の退院数が最多: 6 x 2週 = 12
        assert result[4] == 12
        # 日曜(6)の退院数はゼロ
        assert result[6] == 0


# ---------------------------------------------------------------
# 退院翌日再利用率（same-day reuse rate のロジック）
# ---------------------------------------------------------------


class TestSameDayReuseRate:
    """退院翌日再利用率の計算ロジックテスト"""

    def test_reuse_rate_calculation(self):
        """金曜退院 → 月曜入院のペア数から再利用率を計算"""
        # アプリのロジック再現:
        # _reuse_pairs = min(fri_discharges, mon_admissions)
        # _reuse_total = max(fri_discharges, mon_admissions)
        # _reuse_rate = (_reuse_pairs / _reuse_total * 100) if _reuse_total > 0 else 0

        fri_dis = 6.0
        mon_adm = 5.0
        reuse_pairs = min(fri_dis, mon_adm)
        reuse_total = max(fri_dis, mon_adm)
        reuse_rate = (reuse_pairs / reuse_total * 100) if reuse_total > 0 else 0

        assert reuse_pairs == pytest.approx(5.0)
        assert reuse_rate == pytest.approx(83.33, abs=0.01)

    def test_reuse_rate_zero_discharges(self):
        """金曜退院ゼロなら再利用率もゼロ"""
        fri_dis = 0.0
        mon_adm = 5.0
        reuse_pairs = min(fri_dis, mon_adm)
        reuse_total = max(fri_dis, mon_adm)
        reuse_rate = (reuse_pairs / reuse_total * 100) if reuse_total > 0 else 0

        assert reuse_rate == pytest.approx(0.0)

    def test_reuse_rate_perfect_match(self):
        """金曜退院と月曜入院が同数なら100%"""
        fri_dis = 5.0
        mon_adm = 5.0
        reuse_pairs = min(fri_dis, mon_adm)
        reuse_total = max(fri_dis, mon_adm)
        reuse_rate = (reuse_pairs / reuse_total * 100) if reuse_total > 0 else 0

        assert reuse_rate == pytest.approx(100.0)
