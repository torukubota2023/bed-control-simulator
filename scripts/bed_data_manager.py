"""
日次ベッドコントロールデータ管理モジュール

おもろまちメディカルセンター（94床）の日次稼働データを
記録・分析・予測するための独立モジュール。
CLI版シミュレーターには依存しない。

個人情報は一切含めない（集計値のみ）。
"""

from __future__ import annotations

import io
from datetime import date, datetime, timedelta
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# データ構造定義
# ---------------------------------------------------------------------------

# 短期滞在手術等基本料3 の平均在院日数仮定値（日）
# 当院の内訳: 大腸ポリペクトミー80%（1-2日）、鼠径ヘルニア（3-4日）、ポリソムノグラフィー（1日）
# 2026年改定で施設基準判定の平均在院日数計算から除外する際に使用する
# 出典: 研究ノート docs/admin/short3_integration_research.md
SHORT3_AVG_LOS_DAYS = 2.0

# 日齢バケット: 1日目〜14日目は個別、15日目以上はまとめる
DAY_BUCKET_KEYS = [f"day_{i}" for i in range(1, 15)] + ["day_15plus"]
# DAY_BUCKET_KEYS = ["day_1", "day_2", ..., "day_14", "day_15plus"]
DAILY_RECORD_COLUMNS = [
    "date",              # 日付 (YYYY-MM-DD)
    "ward",              # 病棟 ("5F", "6F", "all")
    "total_patients",    # 在院患者数
    "new_admissions",    # 新規入院数
    "new_admissions_short3",  # うち短期滞在手術等基本料3 算定（内数, 内訳記録のみ Phase 1）
    "discharges",        # 退院数
    "discharge_a",       # A群相当退院数（1-5日目退院）
    "discharge_b",       # B群相当退院数（6-14日目退院）
    "discharge_c",       # C群相当退院数（15日目以降退院）
    "discharge_los_list",  # 退院患者の在院日数リスト（カンマ区切り, e.g. "3,12,18,25"）
    "phase_a_count",     # A群患者数（1-5日目）— 自動計算、手入力不要
    "phase_b_count",     # B群患者数（6-14日目）— 自動計算、手入力不要
    "phase_c_count",     # C群患者数（15日目以降）— 自動計算、手入力不要
    "avg_los",           # 平均在院日数（任意、空欄可）
    "notes",             # 備考（任意）
]

# 必須入力カラム（phase_a/b/c_countは自動計算のため必須ではない）
REQUIRED_COLUMNS = [
    "date",
    "total_patients",
    "new_admissions",
    "discharges",
]

def parse_discharge_los_list(los_str: str) -> tuple:
    """
    カンマ区切りの在院日数文字列からA/B/C群退院数と平均在院日数を算出。

    Args:
        los_str: カンマ区切りの在院日数文字列 (e.g. "3,12,18,25")

    Returns:
        (los_list, discharge_a, discharge_b, discharge_c, avg_los)
    """
    if not los_str or str(los_str).strip() in ("", "nan", "<NA>"):
        return [], 0, 0, 0, float("nan")
    los_list = [int(x.strip()) for x in str(los_str).split(",") if x.strip().isdigit()]
    if not los_list:
        return [], 0, 0, 0, float("nan")
    da = sum(1 for x in los_list if 1 <= x <= 5)
    db = sum(1 for x in los_list if 6 <= x <= 14)
    dc = sum(1 for x in los_list if x >= 15)
    avg = sum(los_list) / len(los_list)
    return los_list, da, db, dc, avg


# 2026年度改定 地域包括医療病棟入院料1（一般病棟非併設）
# 基本入院料: イ/ロ/ハ加重平均(全国平均 イ45%/ロ35%/ハ20%) ≈ 3,280点
# A群・B群: +初期加算(150点, 14日以内) +リハ加算 +物価対応料(49点)
# C群: 初期加算なし(15日超) +リハ加算2 +物価対応料(49点)
DEFAULT_REVENUE_PARAMS = {
    "phase_a_revenue": 36000,  # A群(急性期1-5日) 全加算込み（初期加算+リハ栄養口腔+物価対応）
    "phase_a_cost": 12000,     # 変動費（検査・薬剤・画像集中）
    "phase_b_revenue": 36000,  # B群(回復期6-14日) A群と同じ加算構造
    "phase_b_cost": 6000,      # 変動費（急性期処置終了、残存薬剤・検査のみ）
    "phase_c_revenue": 33400,  # C群(退院準備15日-) 初期加算+リハ加算消失で-2,600円
    "phase_c_cost": 4500,      # 変動費（薬剤・給食等の最低限変動費のみ）
}

# ---------------------------------------------------------------------------
# 病棟・部屋レイアウト定義
# ---------------------------------------------------------------------------

# 6F 部屋レイアウト（部屋番号: ベッド数）
ROOM_LAYOUT_6F = {
    "601": 4, "602": 1, "603": 1,
    "605": 1, "606": 1, "607": 1, "608": 1,
    "610": 1,
    "611": 0,  # 倉庫（使用不可）
    "612": 1, "613": 1,  # 特室
    "615": 1, "616": 1, "617": 1,
    "618": 4,
    "620": 4, "621": 4, "622": 4, "623": 4,
    "625": 4, "626": 4, "627": 4,
    "628": 1, "630": 1, "631": 2,
}

# 5F 部屋レイアウト（511が個室、他は6Fと同じ構成）
ROOM_LAYOUT_5F = {f"5{k[1:]}": v for k, v in ROOM_LAYOUT_6F.items()}
ROOM_LAYOUT_5F["511"] = 1  # 6Fの611は倉庫だが、5Fの511は個室

# 部屋の種別
ROOM_TYPES_6F = {
    "612": "特室", "613": "特室",
    "610": "個室",
    "611": "倉庫",
    "602": "個室", "603": "個室", "605": "個室", "606": "個室",
    "607": "個室", "608": "個室", "615": "個室", "616": "個室",
    "617": "個室", "628": "個室", "630": "個室",
    "601": "4人部屋", "618": "4人部屋",
    "620": "4人部屋", "621": "4人部屋", "622": "4人部屋", "623": "4人部屋",
    "625": "4人部屋", "626": "4人部屋", "627": "4人部屋",
    "631": "2人部屋",
}
ROOM_TYPES_5F = {f"5{k[1:]}": v for k, v in ROOM_TYPES_6F.items()}
# 5Fの511は個室（6Fの611=倉庫からコピーされた"倉庫"を上書き）
ROOM_TYPES_5F["511"] = "個室"

WARD_CONFIG = {
    "5F": {"beds": 47, "rooms": ROOM_LAYOUT_5F, "room_types": ROOM_TYPES_5F},
    "6F": {"beds": 47, "rooms": ROOM_LAYOUT_6F, "room_types": ROOM_TYPES_6F},
}
TOTAL_BEDS = 94

def get_ward_beds(ward: str) -> int:
    """病棟のベッド数を返す"""
    if ward in WARD_CONFIG:
        return WARD_CONFIG[ward]["beds"]
    return TOTAL_BEDS


# ---------------------------------------------------------------------------
# DataFrame作成・操作
# ---------------------------------------------------------------------------
def create_empty_dataframe() -> pd.DataFrame:
    """空のDataFrameを作成（カラム定義済み）。"""
    df = pd.DataFrame(columns=DAILY_RECORD_COLUMNS)
    # 型を明示的に設定
    df["date"] = pd.to_datetime(df["date"])
    df["ward"] = df["ward"].astype("string")
    for col in ["total_patients", "new_admissions", "new_admissions_short3",
                 "discharges",
                 "discharge_a", "discharge_b", "discharge_c",
                 "phase_a_count", "phase_b_count", "phase_c_count"]:
        df[col] = df[col].astype("Int64")  # nullable int
    df["avg_los"] = df["avg_los"].astype("Float64")  # nullable float
    df["notes"] = df["notes"].astype("string")
    df["discharge_los_list"] = df["discharge_los_list"].astype("string")
    return df


def validate_record(record, existing_df=None):
    """
    入力値のバリデーション。

    Args:
        record: 検証するレコード辞書
        existing_df: 重複日付チェック用の既存DataFrame（任意）

    Returns:
        (有効かbool, エラーメッセージstr)
    """
    errors = []

    # 日付チェック
    try:
        if isinstance(record.get("date"), str):
            pd.to_datetime(record["date"])
        elif not isinstance(record.get("date"), (date, datetime, pd.Timestamp)):
            errors.append("日付が無効です。")
    except (ValueError, TypeError):
        errors.append("日付の形式が無効です（YYYY-MM-DD）。")

    # 在院患者数チェック
    ward = record.get("ward", "all")
    max_beds = get_ward_beds(ward)
    tp = record.get("total_patients")
    if tp is None or not isinstance(tp, (int, np.integer)):
        errors.append("在院患者数は整数で入力してください。")
    elif not (0 <= tp <= max_beds):
        errors.append(f"total_patients は 0〜{max_beds} の範囲で入力してください。")

    # 入退院数チェック
    for key, label in [("new_admissions", "新規入院数"), ("discharges", "退院数")]:
        val = record.get(key)
        if val is None or not isinstance(val, (int, np.integer)):
            errors.append(f"{label}は整数で入力してください。")
        elif val < 0:
            errors.append(f"{label}は0以上で入力してください。")

    # 短手3（内数）チェック: 0以上、かつ新規入院数以下
    s3 = record.get("new_admissions_short3", 0) or 0
    if isinstance(s3, (int, np.integer)):
        if s3 < 0:
            errors.append("短手3（内数）は0以上で入力してください。")
        adm_val = record.get("new_admissions", 0) or 0
        if isinstance(adm_val, (int, np.integer)) and s3 > adm_val:
            errors.append("短手3（内数）は新規入院数以下で入力してください。")

    # 退院内訳チェック
    da = record.get("discharge_a", 0) or 0
    db = record.get("discharge_b", 0) or 0
    dc = record.get("discharge_c", 0) or 0
    for dval, dlabel in [(da, "discharge_a"), (db, "discharge_b"), (dc, "discharge_c")]:
        if isinstance(dval, (int, np.integer)) and dval < 0:
            errors.append(f"{dlabel}は0以上で入力してください。")

    # 重複チェック（日付+病棟の組み合わせ）
    if existing_df is not None and len(existing_df) > 0:
        try:
            check_date = pd.to_datetime(record["date"])
            check_ward = record.get("ward", "all")
            if "ward" in existing_df.columns:
                existing_match = existing_df[(existing_df["date"] == check_date) & (existing_df["ward"] == check_ward)]
            else:
                existing_match = existing_df[existing_df["date"] == check_date]
            if len(existing_match) > 0:
                errors.append(f"日付 {check_date.strftime('%Y-%m-%d')} ({check_ward}) のデータは既に存在します。")
        except (ValueError, TypeError, KeyError):
            pass  # 日付エラーは上で既にキャッチ済み

    if errors:
        return False, "\n".join(errors)
    return True, ""


def add_record(df: pd.DataFrame, record: dict) -> pd.DataFrame:
    """レコードを追加し日付順にソート。"""
    record_copy = record.copy()
    record_copy["date"] = pd.to_datetime(record_copy["date"])
    if "notes" not in record_copy or record_copy["notes"] is None:
        record_copy["notes"] = ""
    if "data_source" not in record_copy:
        record_copy["data_source"] = "manual"
    # 退院内訳のデフォルト値
    for col in ["discharge_a", "discharge_b", "discharge_c"]:
        if col not in record_copy or record_copy[col] is None:
            record_copy[col] = 0
    if "discharge_los_list" not in record_copy or record_copy["discharge_los_list"] is None:
        record_copy["discharge_los_list"] = ""
    # 短手3（内数）デフォルト 0
    if "new_admissions_short3" not in record_copy or record_copy["new_admissions_short3"] is None:
        record_copy["new_admissions_short3"] = 0
    # phase_a/b/c_count はオプション（自動計算される場合がある）
    for col in ["phase_a_count", "phase_b_count", "phase_c_count"]:
        if col not in record_copy:
            record_copy[col] = pd.NA
    if "avg_los" not in record_copy:
        record_copy["avg_los"] = pd.NA
    new_row = pd.DataFrame([record_copy])
    # カラム型を合わせる
    for col in ["total_patients", "new_admissions", "new_admissions_short3",
                 "discharges",
                 "discharge_a", "discharge_b", "discharge_c",
                 "phase_a_count", "phase_b_count", "phase_c_count"]:
        if col in new_row.columns:
            new_row[col] = new_row[col].astype("Int64")
    new_row["avg_los"] = new_row["avg_los"].astype("Float64")
    new_row["notes"] = new_row["notes"].astype("string")
    if "discharge_los_list" in new_row.columns:
        new_row["discharge_los_list"] = new_row["discharge_los_list"].fillna("").astype("string")

    df = pd.concat([df, new_row], ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


def update_record(df: pd.DataFrame, date_str: str, updates: dict) -> pd.DataFrame:
    """既存レコードを修正。"""
    target_date = pd.to_datetime(date_str)
    mask = df["date"] == target_date
    if mask.sum() == 0:
        raise ValueError(f"日付 {date_str} のレコードが見つかりません。")
    for key, value in updates.items():
        if key in df.columns and key != "date":
            df.loc[mask, key] = value
    return df


def delete_record(df, date_str, ward=None):
    """レコードを削除。

    Args:
        df: 日次データ DataFrame
        date_str: 削除対象の日付（YYYY-MM-DD）
        ward: 病棟指定（"5F" / "6F"）。None の場合は当該日付の全レコードを削除。

    Returns:
        削除後の DataFrame
    """
    target_date = pd.to_datetime(date_str)
    if ward is None:
        df = df[df["date"] != target_date].reset_index(drop=True)
    else:
        mask = ~((df["date"] == target_date) & (df["ward"].astype(str) == str(ward)))
        df = df[mask].reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# メトリクス計算
# ---------------------------------------------------------------------------
def calculate_daily_metrics(df: pd.DataFrame, num_beds: int = 94) -> pd.DataFrame:
    """
    記録データから自動計算カラムを追加。

    追加カラム:
        occupancy_rate, phase_a_ratio, phase_b_ratio, phase_c_ratio,
        daily_net_change, occupancy_7d_ma, admission_7d_ma, discharge_7d_ma
    """
    if len(df) == 0:
        return df.copy()

    result = df.copy()
    result["date"] = pd.to_datetime(result["date"])
    result = result.sort_values("date").reset_index(drop=True)

    # 稼働率
    result["occupancy_rate"] = result["total_patients"] / num_beds

    # フェーズ構成比（ゼロ除算対応）
    # phase_a/b/c_count が NULL または合計0の行は目標比率(A:18% B:43% C:39%)で自動推定
    result["phase_a_count"] = pd.to_numeric(result["phase_a_count"], errors="coerce").fillna(0)
    result["phase_b_count"] = pd.to_numeric(result["phase_b_count"], errors="coerce").fillna(0)
    result["phase_c_count"] = pd.to_numeric(result["phase_c_count"], errors="coerce").fillna(0)
    _total_phase = result["phase_a_count"] + result["phase_b_count"] + result["phase_c_count"]
    _needs_estimate = _total_phase == 0
    if _needs_estimate.any():
        _tp_est = result.loc[_needs_estimate, "total_patients"]
        result.loc[_needs_estimate, "phase_a_count"] = (_tp_est * 0.18).round()
        result.loc[_needs_estimate, "phase_b_count"] = (_tp_est * 0.43).round()
        result.loc[_needs_estimate, "phase_c_count"] = (
            _tp_est
            - result.loc[_needs_estimate, "phase_a_count"]
            - result.loc[_needs_estimate, "phase_b_count"]
        )
    tp = result["total_patients"].replace(0, np.nan)
    result["phase_a_ratio"] = result["phase_a_count"] / tp
    result["phase_b_ratio"] = result["phase_b_count"] / tp
    result["phase_c_ratio"] = result["phase_c_count"] / tp

    # 日次純増減
    result["daily_net_change"] = result["new_admissions"] - result["discharges"]

    # 7日移動平均
    result["occupancy_7d_ma"] = result["occupancy_rate"].rolling(7, min_periods=1).mean()
    result["admission_7d_ma"] = result["new_admissions"].rolling(7, min_periods=1).mean()
    result["discharge_7d_ma"] = result["discharges"].rolling(7, min_periods=1).mean()

    return result


# ---------------------------------------------------------------------------
# 予測
# ---------------------------------------------------------------------------
def predict_occupancy_from_history(
    df: pd.DataFrame, num_beds: int = 94, horizon: int = 7
) -> pd.DataFrame:
    """
    過去データから向こうN日の稼働率を予測。

    方法:
      - 直近14日間の入退院データから1日あたり純増減の移動平均を算出
      - 直近7日のトレンド（線形回帰の傾き）を算出
      - 曜日別補正（7日以上のデータがある場合）
      - confidence列を付与

    Args:
        df: 日次データ（date, total_patients, new_admissions, discharges必須）
        num_beds: 総病床数
        horizon: 予測日数

    Returns:
        予測DataFrame（date, predicted_patients, predicted_occupancy, confidence）
    """
    if len(df) < 3:
        return pd.DataFrame(columns=[
            "date", "predicted_patients", "predicted_occupancy", "confidence"
        ])

    work = df.copy()
    work["date"] = pd.to_datetime(work["date"])
    work = work.sort_values("date").reset_index(drop=True)

    # 直近14日分（データがそれ未満ならあるだけ使う）
    recent = work.tail(min(14, len(work))).copy()
    recent["net_change"] = recent["new_admissions"] - recent["discharges"]

    # 純増減の移動平均
    net_change_ma = float(recent["net_change"].mean())

    # 直近7日の線形トレンド（傾き）
    trend_data = work.tail(min(7, len(work))).copy()
    if len(trend_data) >= 3:
        x = np.arange(len(trend_data), dtype=float)
        y = trend_data["total_patients"].astype(float).values
        # 線形回帰
        slope = np.polyfit(x, y, 1)[0]
    else:
        slope = 0.0

    # 曜日別補正（7日以上のデータがある場合）
    dow_adjustment = {}
    if len(work) >= 7:
        work["dow"] = work["date"].dt.dayofweek
        work["_net"] = work["new_admissions"] - work["discharges"]
        dow_mean = work.groupby("dow")["_net"].mean()
        overall_mean = work["_net"].mean()
        for dow in range(7):
            if dow in dow_mean.index:
                dow_adjustment[dow] = float(dow_mean[dow] - overall_mean)
            else:
                dow_adjustment[dow] = 0.0

    # 予測生成
    last_date = work["date"].iloc[-1]
    last_patients = float(work["total_patients"].iloc[-1])

    # トレンドと移動平均の加重平均（トレンド30%, MA70%）
    blended_daily_change = 0.3 * slope + 0.7 * net_change_ma

    predictions = []
    current_patients = last_patients

    for i in range(1, horizon + 1):
        pred_date = last_date + timedelta(days=i)
        dow = pred_date.dayofweek

        daily_change = blended_daily_change
        if dow_adjustment:
            daily_change += dow_adjustment.get(dow, 0.0)

        current_patients += daily_change
        # 0〜num_beds にクリップ
        current_patients = max(0, min(num_beds, current_patients))

        occupancy = current_patients / num_beds

        # 信頼度（データ量と予測距離で判定）
        if len(work) >= 14 and i <= 3:
            confidence = "high"
        elif len(work) >= 7 and i <= 5:
            confidence = "medium"
        else:
            confidence = "low"

        predictions.append({
            "date": pred_date,
            "predicted_patients": round(current_patients, 1),
            "predicted_occupancy": round(occupancy, 4),
            "confidence": confidence,
        })

    return pd.DataFrame(predictions)


def predict_monthly_kpi(
    df,
    num_beds=94,
    revenue_params=None,
):
    """
    過去データから今月の着地予想を算出。

    Returns:
        dict: 月末予想稼働率, 月末予想在院患者数, 今月の入院数合計,
              推定平均在院日数, 推定月次運営貢献額
    """
    if len(df) == 0:
        return {}

    if revenue_params is None:
        revenue_params = DEFAULT_REVENUE_PARAMS.copy()

    work = df.copy()
    work["date"] = pd.to_datetime(work["date"])
    work = work.sort_values("date").reset_index(drop=True)

    today = pd.Timestamp.now().normalize()
    current_month_start = today.replace(day=1)

    # 今月のデータ
    month_data = work[work["date"] >= current_month_start].copy()

    # 月末日
    if today.month == 12:
        month_end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        month_end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)

    remaining_days = max(0, (month_end - today).days)

    # 実績
    actual_admissions = int(month_data["new_admissions"].sum()) if len(month_data) > 0 else 0

    # 予測
    pred = predict_occupancy_from_history(df, num_beds=num_beds, horizon=remaining_days)

    if len(pred) > 0:
        end_patients = pred["predicted_patients"].iloc[-1]
        end_occupancy = pred["predicted_occupancy"].iloc[-1]
    elif len(work) > 0:
        end_patients = float(work["total_patients"].iloc[-1])
        end_occupancy = end_patients / num_beds
    else:
        end_patients = 0
        end_occupancy = 0.0

    # 残り日数の入院予測（直近7日平均）
    recent_admissions = work.tail(min(7, len(work)))
    daily_admission_avg = float(recent_admissions["new_admissions"].mean()) if len(recent_admissions) > 0 else 0
    predicted_remaining_admissions = round(daily_admission_avg * remaining_days)
    total_admissions = actual_admissions + predicted_remaining_admissions

    # 推定平均在院日数（厚生労働省 病院報告の定義に準拠）
    # 平均在院日数 = 在院患者延日数 ÷ ((新入院患者数 + 退院患者数) ÷ 2)
    total_patient_days = float(month_data["total_patients"].sum()) if len(month_data) > 0 else 0
    total_new_admissions = float(month_data["new_admissions"].sum()) if len(month_data) > 0 else 0
    total_discharges_month = float(month_data["discharges"].sum()) if len(month_data) > 0 else 0
    los_denominator = (total_new_admissions + total_discharges_month) / 2
    estimated_avg_los = total_patient_days / max(los_denominator, 1) if total_patient_days > 0 else 18.0

    # 推定月次運営貢献額
    # 今月実績分の運営貢献額
    actual_gross_profit = 0.0
    if len(month_data) > 0:
        for _, row in month_data.iterrows():
            _pa_val = row.get("phase_a_count", 0)
            pa = 0 if pd.isna(_pa_val) else int(_pa_val)
            _pb_val = row.get("phase_b_count", 0)
            pb = 0 if pd.isna(_pb_val) else int(_pb_val)
            _pc_val = row.get("phase_c_count", 0)
            pc = 0 if pd.isna(_pc_val) else int(_pc_val)
            actual_gross_profit += (
                pa * (revenue_params["phase_a_revenue"] - revenue_params["phase_a_cost"])
                + pb * (revenue_params["phase_b_revenue"] - revenue_params["phase_b_cost"])
                + pc * (revenue_params["phase_c_revenue"] - revenue_params["phase_c_cost"])
            )

    # 残り日数分は直近のフェーズ構成比で推定
    if len(work) >= 3:
        recent = work.tail(min(7, len(work)))
        avg_a = float(recent["phase_a_count"].fillna(0).mean())
        avg_b = float(recent["phase_b_count"].fillna(0).mean())
        avg_c = float(recent["phase_c_count"].fillna(0).mean())
    else:
        # フォールバック: 全体平均
        avg_a = float(work["phase_a_count"].fillna(0).mean()) if len(work) > 0 else 0
        avg_b = float(work["phase_b_count"].fillna(0).mean()) if len(work) > 0 else 0
        avg_c = float(work["phase_c_count"].fillna(0).mean()) if len(work) > 0 else 0

    predicted_daily_profit = (
        avg_a * (revenue_params["phase_a_revenue"] - revenue_params["phase_a_cost"])
        + avg_b * (revenue_params["phase_b_revenue"] - revenue_params["phase_b_cost"])
        + avg_c * (revenue_params["phase_c_revenue"] - revenue_params["phase_c_cost"])
    )
    predicted_gross_profit = actual_gross_profit + predicted_daily_profit * remaining_days

    return {
        "月末予想稼働率": round(float(end_occupancy) * 100, 1),
        "月末予想在院患者数": round(float(end_patients), 1),
        "今月入院数_実績": actual_admissions,
        "今月入院数_予測": predicted_remaining_admissions,
        "今月入院数_合計": total_admissions,
        "推定平均在院日数": round(estimated_avg_los, 1),
        "推定月次運営貢献額": int(round(predicted_gross_profit)),
        "残り日数": remaining_days,
    }


# ---------------------------------------------------------------------------
# 理論的フェーズ構成比（Little法則 + 決定論的フローモデル）
# ---------------------------------------------------------------------------
def calculate_ideal_phase_ratios(
    num_beds=94,
    monthly_admissions=150,
    target_occupancy=0.925,
    days_per_month=30,
    phase_a_days=5,
    phase_b_end=14,
    phase_a_contrib=24000,
    phase_b_contrib=30000,
    phase_c_contrib=28900,
):
    """
    Little法則に基づくフェーズ構成の **理論上限** を計算する。

    ⚠️ これは「全患者が14日以上在院する」という強い仮定の下での上限値です。
       現実には早期退院があるため、実績は B < 上限、C > 上限 となるのが普通です。
       合計人数（= target_patients）は Little法則により分布に関わらず保存されます。

    前提となる理論モデル（決定論的フロー／上限シナリオ）:
    1. 月間入院数 × 目標稼働率 から Little法則で平均在院日数 L を逆算
       L = (target_occupancy × num_beds × days_per_month) / monthly_admissions
    2. **全員が L 日以上 (≥14日) 在院する仮定** で、1日目から順にフェーズを流れる
       - A群: 入院1-5日目（phase_a_days=5日間）
       - B群: 入院6-14日目（9日間）
       - C群: 入院15日目以降（L-14日間）
    3. 上記仮定下での各フェーズ患者数:
       - A群上限 = 入院率/日 × 5
       - B群上限 = 入院率/日 × 9  （L ≥ 14 の場合）
       - C群上限 = 入院率/日 × (L - 14)
    4. 月150人入院・稼働率92.5%の場合、L=17.4日となり、
       A:28.8% / B:51.8% / C:19.5% が理論上限となる。

    実績との差の読み方:
    - B群実績が上限より低い → 早期退院が多い（必ずしも悪ではない）
    - C群実績が上限より高い → 長期在院層が厚い（退院調整の余地の指標）

    Args:
        num_beds: 総病床数
        monthly_admissions: 月間入院数
        target_occupancy: 目標稼働率（0-1, 例: 0.925）
        days_per_month: 月の日数（デフォルト30）
        phase_a_days: A群境界（1〜phase_a_days日目, デフォルト5）
        phase_b_end: B群終端（phase_a_days+1〜phase_b_end日目, デフォルト14）

    Returns:
        dict: {
            "target_los": 目標平均在院日数(日),
            "target_patients": 目標在院患者数,
            "daily_admissions": 1日あたり入院数,
            "a_count": A群人数,
            "b_count": B群人数,
            "c_count": C群人数,
            "total_count": 総患者数,
            "a_pct": A群構成比(%),
            "b_pct": B群構成比(%),
            "c_pct": C群構成比(%),
            "daily_contribution": 日次運営貢献額(円, デフォルトコスト前提),
            "feasible": 理論値が物理的に達成可能か,
            "notes": 注記メッセージ,
        }
    """
    # 1日あたり入院数
    daily_admissions = monthly_admissions / days_per_month
    # 目標在院患者数
    target_patients = target_occupancy * num_beds
    # 平均在院日数を Little法則で逆算
    if daily_admissions <= 0:
        target_los = 0
    else:
        target_los = target_patients / daily_admissions

    # 決定論的フローモデルで各フェーズの患者数を算出
    # A群: 入院1-phase_a_days日目
    a_duration = min(phase_a_days, target_los)
    a_count = daily_admissions * a_duration

    # B群: phase_a_days+1 〜 phase_b_end 日目
    b_duration = max(0, min(phase_b_end, target_los) - phase_a_days)
    b_count = daily_admissions * b_duration

    # C群: phase_b_end+1 日目以降
    c_duration = max(0, target_los - phase_b_end)
    c_count = daily_admissions * c_duration

    total_count = a_count + b_count + c_count

    if total_count > 0:
        a_pct = a_count / total_count * 100
        b_pct = b_count / total_count * 100
        c_pct = c_count / total_count * 100
    else:
        a_pct = b_pct = c_pct = 0

    # 日次運営貢献額（呼び出し元から診療報酬プリセットの値を受け取る）
    # デフォルトは 2024年度相当（A=24,000 / B=30,000 / C=28,900 円/日）
    # 2026年度プリセット等ではここに改定後の1日次貢献額が渡される
    daily_contribution = a_count * phase_a_contrib + b_count * phase_b_contrib + c_count * phase_c_contrib

    # 物理的に達成可能か判定
    feasible = True
    notes = ""
    if target_los < phase_b_end:
        feasible = False
        notes = (
            f"目標在院日数{target_los:.1f}日 < {phase_b_end}日のため、"
            f"C群は存在しません（全員がB群までで退院）。"
            f"入院数を減らすか、目標稼働率を上げる必要があります。"
        )
    elif target_los > 60:
        feasible = False
        notes = (
            f"目標在院日数{target_los:.1f}日 が長すぎます。"
            f"入院数を増やすか、目標稼働率を下げる必要があります。"
        )

    return {
        "target_los": round(target_los, 2),
        "target_patients": round(target_patients, 1),
        "daily_admissions": round(daily_admissions, 2),
        "a_count": round(a_count, 1),
        "b_count": round(b_count, 1),
        "c_count": round(c_count, 1),
        "total_count": round(total_count, 1),
        "a_pct": round(a_pct, 1),
        "b_pct": round(b_pct, 1),
        "c_pct": round(c_pct, 1),
        "daily_contribution": int(daily_contribution),
        "feasible": feasible,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# 過去3ヶ月rolling 平均在院日数（2026年改定対応）
# ---------------------------------------------------------------------------
def calculate_rolling_los(df, window_days=90):
    """
    過去window_days日間の厚労省公式rolling平均在院日数を計算する。

    計算式（厚労省 病院報告の定義）:
        平均在院日数 = 在院患者延日数 ÷ ((新入院患者数 + 退院患者数) ÷ 2)

    データが window_days 日に満たない場合は、揃っている日数で計算する。
    2026年度改定対応: 地域包括医療病棟入院料1の施設基準判定は
    過去3ヶ月rolling平均で行われる。

    短手3（短期滞在手術等基本料3）除外後の値も同時に返す:
        - 分子: 在院延日数 − (短手3新入院数 × SHORT3_AVG_LOS_DAYS)
        - 分母: ((新入院数 − 短手3新入院数) + (退院数 − 短手3新入院数)) ÷ 2
          ※ 短手3は4泊5日以内なので当月内に入退院が完結すると仮定
        - new_admissions_short3 列がない or 全て0なら通常値と同じ

    Args:
        df: 日次データ（date, total_patients, new_admissions, discharges列必須
            + new_admissions_short3列があれば除外計算も実施）
            全体 or 病棟フィルタ済みのものを渡す
        window_days: rolling window 日数（デフォルト90日=3ヶ月）

    Returns:
        dict or None: {
            "rolling_los": float or None,           # rolling平均在院日数（日）
            "rolling_los_ex_short3": float or None, # 短手3除外後のrolling平均在院日数
            "actual_days": int,                     # 実際に使った日数
            "total_patient_days": float,            # 在院患者延日数
            "total_admissions": float,              # 期間内新入院数
            "total_discharges": float,              # 期間内退院数
            "total_short3": float,                  # 期間内短手3新入院数
            "is_partial": bool,                     # window_daysに満たないか
            "end_date": Timestamp or None,          # 計算対象期間の最終日
            "start_date": Timestamp or None,        # 計算対象期間の開始日
        }
    """
    if df is None or len(df) == 0:
        return None

    df_sorted = df.copy()
    # date列の検出（date または 日付）
    date_col = None
    for _c in ["date", "日付"]:
        if _c in df_sorted.columns:
            date_col = _c
            break
    if date_col is None:
        return None

    df_sorted[date_col] = pd.to_datetime(df_sorted[date_col])
    df_sorted = df_sorted.sort_values(date_col).reset_index(drop=True)

    # 最新のwindow_days日分を取得
    window_df = df_sorted.tail(window_days)
    actual_days = len(window_df)

    # 列名の検出（英語/日本語両対応）
    tp_col = "total_patients" if "total_patients" in window_df.columns else "在院患者数"
    adm_col = "new_admissions" if "new_admissions" in window_df.columns else "新規入院"
    dis_col = "discharges" if "discharges" in window_df.columns else "退院"
    s3_col = "new_admissions_short3" if "new_admissions_short3" in window_df.columns else None

    if tp_col not in window_df.columns or adm_col not in window_df.columns or dis_col not in window_df.columns:
        return None

    total_patient_days = float(window_df[tp_col].sum())
    total_admissions = float(window_df[adm_col].sum())
    total_discharges = float(window_df[dis_col].sum())
    total_short3 = float(window_df[s3_col].fillna(0).sum()) if s3_col else 0.0

    denominator = (total_admissions + total_discharges) / 2

    result = {
        "actual_days": actual_days,
        "total_patient_days": total_patient_days,
        "total_admissions": total_admissions,
        "total_discharges": total_discharges,
        "total_short3": total_short3,
        "is_partial": actual_days < window_days,
        "end_date": window_df[date_col].iloc[-1] if actual_days > 0 else None,
        "start_date": window_df[date_col].iloc[0] if actual_days > 0 else None,
    }

    if denominator <= 0 or total_patient_days <= 0:
        result["rolling_los"] = None
    else:
        result["rolling_los"] = round(total_patient_days / denominator, 1)

    # 短手3 除外版（2026年改定: 施設基準判定では短手3算定患者を除外）
    # 短手3 がゼロなら通常値と同じ
    if total_short3 > 0:
        adj_patient_days = total_patient_days - (total_short3 * SHORT3_AVG_LOS_DAYS)
        # 当月内に入退院完結と仮定 → 新入院・退院の両方から短手3を引く
        adj_admissions = total_admissions - total_short3
        adj_discharges = total_discharges - total_short3
        adj_denominator = (adj_admissions + adj_discharges) / 2
        if adj_denominator > 0 and adj_patient_days > 0:
            result["rolling_los_ex_short3"] = round(adj_patient_days / adj_denominator, 1)
        else:
            result["rolling_los_ex_short3"] = None
    else:
        # 短手3 がゼロ → 通常値と同じ
        result["rolling_los_ex_short3"] = result["rolling_los"]

    return result


# ---------------------------------------------------------------------------
# 週次サマリー
# ---------------------------------------------------------------------------
def generate_weekly_summary(df: pd.DataFrame, num_beds: int = 94) -> list[dict]:
    """
    週次サマリーを生成（過去の週ごとに集計）。

    Returns:
        list[dict]: 週ごとのサマリー辞書リスト
            - week_start, week_end
            - avg_occupancy_rate
            - total_admissions, total_discharges
            - avg_phase_a_ratio, avg_phase_b_ratio, avg_phase_c_ratio
            - prev_week_occupancy_change（前週比）
    """
    if len(df) == 0:
        return []

    work = df.copy()
    work["date"] = pd.to_datetime(work["date"])
    work = work.sort_values("date").reset_index(drop=True)

    # 週番号で集約（ISO週）
    work["year_week"] = work["date"].dt.isocalendar().year.astype(str) + "-W" + \
                        work["date"].dt.isocalendar().week.astype(str).str.zfill(2)

    summaries = []
    prev_occupancy = None

    for yw, group in work.groupby("year_week", sort=True):
        avg_occ = float(group["total_patients"].mean()) / num_beds
        total_adm = int(group["new_admissions"].sum())
        total_dis = int(group["discharges"].sum())

        tp = group["total_patients"].replace(0, np.nan)
        avg_a = float((group["phase_a_count"].fillna(0) / tp).mean()) if tp.notna().any() else 0
        avg_b = float((group["phase_b_count"].fillna(0) / tp).mean()) if tp.notna().any() else 0
        avg_c = float((group["phase_c_count"].fillna(0) / tp).mean()) if tp.notna().any() else 0

        occ_change = None
        if prev_occupancy is not None:
            occ_change = round((avg_occ - prev_occupancy) * 100, 1)

        summaries.append({
            "week_label": yw,
            "week_start": group["date"].min().strftime("%m/%d"),
            "week_end": group["date"].max().strftime("%m/%d"),
            "days": len(group),
            "avg_occupancy_rate": round(avg_occ * 100, 1),
            "total_admissions": total_adm,
            "total_discharges": total_dis,
            "avg_phase_a_ratio": round(avg_a * 100, 1),
            "avg_phase_b_ratio": round(avg_b * 100, 1),
            "avg_phase_c_ratio": round(avg_c * 100, 1),
            "prev_week_occupancy_change": occ_change,
        })
        prev_occupancy = avg_occ

    return summaries


# ---------------------------------------------------------------------------
# CSV入出力
# ---------------------------------------------------------------------------
def export_to_csv(df: pd.DataFrame) -> str:
    """CSV文字列を返す（ダウンロード用、UTF-8 BOM付き）。"""
    work = df.copy()
    if "date" in work.columns:
        work["date"] = pd.to_datetime(work["date"]).dt.strftime("%Y-%m-%d")
    buf = io.StringIO()
    work.to_csv(buf, index=False, encoding="utf-8")
    return buf.getvalue()


def import_from_csv(csv_content: str) -> tuple[pd.DataFrame, str]:
    """
    CSVからインポート（バリデーション付き）。

    Returns:
        (DataFrame, エラーメッセージ) — エラーがなければ空文字列
    """
    try:
        buf = io.StringIO(csv_content)
        raw = pd.read_csv(buf)
    except Exception as e:
        return create_empty_dataframe(), f"CSVの読み込みに失敗しました: {e}"

    # カラムチェック（必須は基本4列のみ、phase_a/b/c_countは自動計算可能）
    required = REQUIRED_COLUMNS  # date, total_patients, new_admissions, discharges
    missing = [c for c in required if c not in raw.columns]
    if missing:
        return create_empty_dataframe(), f"必須カラムが不足しています: {', '.join(missing)}"

    # 型変換
    try:
        raw["date"] = pd.to_datetime(raw["date"])
    except Exception:
        return create_empty_dataframe(), "date列の日付変換に失敗しました。YYYY-MM-DD形式で記載してください。"

    # ward カラムがない場合は "all" で埋める（後方互換性）
    if "ward" not in raw.columns:
        raw["ward"] = "all"
    raw["ward"] = raw["ward"].fillna("all").astype("string")

    # 旧CSVに退院内訳カラムがない場合は0で埋める
    for col in ["discharge_a", "discharge_b", "discharge_c"]:
        if col not in raw.columns:
            raw[col] = 0

    # 短手3（内数）がない旧CSVは0で埋める（後方互換性）
    if "new_admissions_short3" not in raw.columns:
        raw["new_admissions_short3"] = 0

    # discharge_los_list がない場合は空文字で埋める（後方互換性）
    if "discharge_los_list" not in raw.columns:
        raw["discharge_los_list"] = ""
    raw["discharge_los_list"] = raw["discharge_los_list"].fillna("").astype("string")

    # phase_a/b/c_count がない場合はNAで埋める（自動計算対応）
    for col in ["phase_a_count", "phase_b_count", "phase_c_count"]:
        if col not in raw.columns:
            raw[col] = pd.NA

    for col in ["total_patients", "new_admissions", "new_admissions_short3",
                 "discharges",
                 "discharge_a", "discharge_b", "discharge_c",
                 "phase_a_count", "phase_b_count", "phase_c_count"]:
        if col in raw.columns:
            raw[col] = pd.to_numeric(raw[col], errors="coerce").astype("Int64")

    if "avg_los" in raw.columns:
        raw["avg_los"] = pd.to_numeric(raw["avg_los"], errors="coerce").astype("Float64")
    else:
        raw["avg_los"] = pd.array([pd.NA] * len(raw), dtype="Float64")

    if "notes" not in raw.columns:
        raw["notes"] = ""
    raw["notes"] = raw["notes"].fillna("").astype("string")

    # 既知カラムだけ残す
    raw = raw[[c for c in DAILY_RECORD_COLUMNS if c in raw.columns]]

    # data_source カラムを追加（インポートデータ）
    raw["data_source"] = "imported"

    # 重複チェック（日付+病棟の組み合わせで判定）
    _dup_cols = ["date", "ward"] if "ward" in raw.columns else ["date"]
    dup = raw.duplicated(subset=_dup_cols)
    if dup.any():
        dup_dates = raw.loc[dup, "date"].dt.strftime("%Y-%m-%d").tolist()
        return create_empty_dataframe(), f"重複があります: {', '.join(dup_dates)}"

    raw = raw.sort_values(["date"] + (["ward"] if "ward" in raw.columns else [])).reset_index(drop=True)

    # phase_a/b/c_count が全てNAの場合、在院患者数と退院内訳から推定
    _phase_cols = ["phase_a_count", "phase_b_count", "phase_c_count"]
    if all(c in raw.columns for c in _phase_cols) and raw[_phase_cols].isna().all().all():
        # 推定ロジック: 退院内訳の比率から在院患者の構成を推定
        # A群(1-5日目): 新規入院×5日分の蓄積 / 在院日数に応じた割合
        # 典型的な割合: A群20-25%, B群35-40%, C群35-45%（在院日数18日想定）
        for idx, row in raw.iterrows():
            tp = int(row["total_patients"]) if pd.notna(row["total_patients"]) else 0
            if tp == 0:
                continue
            adm = int(row["new_admissions"]) if pd.notna(row["new_admissions"]) else 0
            # 退院内訳が入力されている場合はその比率をヒントにする
            da = int(row["discharge_a"]) if pd.notna(row["discharge_a"]) else 0
            db = int(row["discharge_b"]) if pd.notna(row["discharge_b"]) else 0
            dc = int(row["discharge_c"]) if pd.notna(row["discharge_c"]) else 0
            total_d = da + db + dc
            if total_d > 0 and adm > 0:
                # 退院構成比に基づく推定（滞在日数の重み付け）
                # A群: 短期入院が多い → 入院数×2.5日（平均滞在）/ 在院日数
                est_a = min(int(adm * 2.5), tp)
                est_c = min(int(tp * dc / max(total_d, 1) * 1.5), tp - est_a)
                est_b = tp - est_a - est_c
            else:
                # デフォルト比率: A群22%, B群38%, C群40%
                est_a = int(tp * 0.22)
                est_b = int(tp * 0.38)
                est_c = tp - est_a - est_b
            # 負にならないよう補正
            est_a = max(est_a, 0)
            est_b = max(est_b, 0)
            est_c = max(est_c, 0)
            # 合計がtotal_patientsに一致するよう調整
            total_est = est_a + est_b + est_c
            if total_est != tp and total_est > 0:
                ratio = tp / total_est
                est_a = int(est_a * ratio)
                est_b = int(est_b * ratio)
                est_c = tp - est_a - est_b
            raw.at[idx, "phase_a_count"] = est_a
            raw.at[idx, "phase_b_count"] = est_b
            raw.at[idx, "phase_c_count"] = est_c

    # 値レンジの警告（エラーではなく警告、病棟別にベッド数を判定）
    warnings = []
    def _check_range(row):
        w = row.get("ward", "all") if "ward" in raw.columns else "all"
        mb = get_ward_beds(w)
        tp_val = row.get("total_patients", 0)
        return pd.isna(tp_val) or tp_val < 0 or tp_val > mb
    out_of_range = raw[raw.apply(_check_range, axis=1)]
    if len(out_of_range) > 0:
        warnings.append(f"在院患者数がベッド数の範囲外のレコードが{len(out_of_range)}件あります。")

    return raw, "\n".join(warnings) if warnings else ""


# ---------------------------------------------------------------------------
# 病棟データ集約
# ---------------------------------------------------------------------------
def aggregate_wards(df: pd.DataFrame) -> pd.DataFrame:
    """5F+6Fのデータを日付ごとに合算して'all'レコードを生成"""
    if "ward" not in df.columns:
        return df
    ward_data = df[df["ward"].isin(["5F", "6F"])]
    if len(ward_data) == 0:
        return df

    numeric_cols = ["total_patients", "new_admissions", "discharges",
                    "discharge_a", "discharge_b", "discharge_c",
                    "phase_a_count", "phase_b_count", "phase_c_count"]

    grouped = ward_data.groupby("date")[numeric_cols].sum(min_count=1).reset_index()
    grouped["ward"] = "all"

    # avg_los は加重平均
    if "avg_los" in ward_data.columns:
        los_data = ward_data.dropna(subset=["avg_los", "total_patients"])
        if len(los_data) > 0:
            avg_los_by_date = los_data.groupby("date").apply(
                lambda g: (g["avg_los"] * g["total_patients"]).sum() / g["total_patients"].sum()
                if g["total_patients"].sum() > 0 else pd.NA
            ).reset_index(name="avg_los")
            grouped = grouped.merge(avg_los_by_date, on="date", how="left")
        else:
            grouped["avg_los"] = pd.NA

    if "notes" in ward_data.columns:
        grouped["notes"] = ""

    return grouped


# ---------------------------------------------------------------------------
# サンプルデータ生成（デモ・テスト用）
# ---------------------------------------------------------------------------
def convert_actual_to_display(actual_df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """
    実績データをシミュレーション出力と同じカラム構造に変換するブリッジ関数。

    Args:
        actual_df: 日次データ（date, total_patients, new_admissions, discharges,
                   phase_a_count, phase_b_count, phase_c_count を含むDataFrame）
        params: パラメータ辞書（num_beds, phase_a_revenue, phase_a_cost 等を含む）

    Returns:
        シミュレーション出力と同じカラム構造のDataFrame
    """
    if len(actual_df) == 0:
        return pd.DataFrame()

    df = actual_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    num_beds = params.get("num_beds", 94)

    # 基本カラム
    df["day"] = range(1, len(df) + 1)

    # 数値型に変換（nullable Int64 を通常の float に）
    for col in ["total_patients", "new_admissions", "discharges",
                "discharge_a", "discharge_b", "discharge_c",
                "phase_a_count", "phase_b_count", "phase_c_count"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(float)

    df["occupancy_rate"] = df["total_patients"] / num_beds
    tp_safe = df["total_patients"].clip(lower=1)

    # フェーズデータがない（全て0）場合、total_patientsからデフォルト比率で推定
    _phase_sum = df["phase_a_count"].fillna(0) + df["phase_b_count"].fillna(0) + df["phase_c_count"].fillna(0)
    _phase_missing = (_phase_sum == 0)
    if _phase_missing.any():
        # デフォルト比率: A群17%, B群45%, C群38%（地域包括医療病棟の標準的構成）
        _default_a_ratio = params.get("phase_a_ratio_default", 0.17)
        _default_b_ratio = params.get("phase_b_ratio_default", 0.45)
        _default_c_ratio = params.get("phase_c_ratio_default", 0.38)
        df.loc[_phase_missing, "phase_a_count"] = (df.loc[_phase_missing, "total_patients"] * _default_a_ratio).round()
        df.loc[_phase_missing, "phase_b_count"] = (df.loc[_phase_missing, "total_patients"] * _default_b_ratio).round()
        df.loc[_phase_missing, "phase_c_count"] = (
            df.loc[_phase_missing, "total_patients"]
            - df.loc[_phase_missing, "phase_a_count"]
            - df.loc[_phase_missing, "phase_b_count"]
        ).clip(lower=0)

    df["phase_a_ratio"] = df["phase_a_count"].fillna(0) / tp_safe
    df["phase_b_ratio"] = df["phase_b_count"].fillna(0) / tp_safe
    df["phase_c_ratio"] = df["phase_c_count"].fillna(0) / tp_safe

    # 収益・コスト計算
    df["daily_revenue"] = (
        df["phase_a_count"].fillna(0) * params.get("phase_a_revenue", 30000)
        + df["phase_b_count"].fillna(0) * params.get("phase_b_revenue", 30000)
        + df["phase_c_count"].fillna(0) * params.get("phase_c_revenue", 30000)
    )
    df["daily_cost"] = (
        df["phase_a_count"].fillna(0) * params.get("phase_a_cost", 28000)
        + df["phase_b_count"].fillna(0) * params.get("phase_b_cost", 13000)
        + df["phase_c_count"].fillna(0) * params.get("phase_c_cost", 11000)
    )
    df["daily_profit"] = df["daily_revenue"] - df["daily_cost"]

    df["empty_beds"] = (num_beds - df["total_patients"]).clip(lower=0)
    df["excess_demand"] = 0  # 実データでは不明
    df["opportunity_loss"] = df["empty_beds"] * params.get("opportunity_cost", 18000)

    # フラグ
    target_lower = params.get("target_occupancy_lower", 0.90)
    target_upper = params.get("target_occupancy_upper", 0.95)
    df["flag_low_occupancy"] = df["occupancy_rate"] < target_lower
    df["flag_high_occupancy"] = df["occupancy_rate"] > target_upper
    df["flag_excess_a"] = df["phase_a_ratio"] > 0.35
    df["flag_shortage_b"] = df["phase_b_ratio"] < 0.25
    df["flag_stagnant_c"] = df["phase_c_ratio"] > 0.30

    # 推奨退院数・保持許容数
    target_upper_patients = int(num_beds * target_upper)
    target_lower_patients = int(num_beds * target_lower)
    df["recommended_discharges"] = (df["total_patients"] - target_upper_patients).clip(lower=0)
    df["allowable_holds"] = (target_lower_patients - df["total_patients"]).clip(lower=0)

    return df


# ---------------------------------------------------------------------------
# 日齢バケット管理
# ---------------------------------------------------------------------------
def advance_day_buckets(prev_buckets: dict, new_admissions: int, discharge_a: int, discharge_b: int, discharge_c: int) -> dict:
    """
    日齢バケットを1日進める。

    処理順序（厳守）：
    1. 日齢進行: 各バケットの患者を翌日に移動
       - day_1 → day_2, day_2 → day_3, ..., day_14 → day_15plus
       - day_15plus はそのまま（day_14からの加算あり）
    2. 新規入院: day_1 に追加
    3. 退院処理:
       - A群退院(discharge_a): day_1〜day_5から按分で引く
       - B群退院(discharge_b): day_6〜day_14から按分で引く
       - C群退院(discharge_c): day_15plusから引く
    4. 負の値防止: 全バケットを max(0, x) で制御

    Args:
        prev_buckets: 前日の日齢バケット辞書 {"day_1": int, "day_2": int, ..., "day_15plus": int}
        new_admissions: 新規入院数
        discharge_a: A群相当退院数（1-5日目）
        discharge_b: B群相当退院数（6-14日目）
        discharge_c: C群相当退院数（15日目以降）

    Returns:
        更新後の日齢バケット辞書
    """
    new_buckets = {}

    # 1. 日齢進行
    # day_15plus = 前日のday_15plus + 前日のday_14
    new_buckets["day_15plus"] = prev_buckets.get("day_15plus", 0) + prev_buckets.get("day_14", 0)
    # day_14 = 前日のday_13, ..., day_2 = 前日のday_1
    for i in range(14, 1, -1):
        new_buckets[f"day_{i}"] = prev_buckets.get(f"day_{i-1}", 0)
    # day_1 = 0 (新規入院で追加される)
    new_buckets["day_1"] = 0

    # 2. 新規入院
    new_buckets["day_1"] += new_admissions

    # 3. 退院処理（按分）
    # A群退院: day_1〜day_5から按分
    a_total = sum(new_buckets.get(f"day_{i}", 0) for i in range(1, 6))
    if a_total > 0 and discharge_a > 0:
        remaining_discharge = discharge_a
        for i in range(1, 6):
            key = f"day_{i}"
            proportion = new_buckets[key] / a_total
            subtract = min(round(proportion * discharge_a), new_buckets[key], remaining_discharge)
            new_buckets[key] -= subtract
            remaining_discharge -= subtract
        # 端数処理: 残りがあれば最大バケットから引く
        if remaining_discharge > 0:
            for i in sorted(range(1, 6), key=lambda x: new_buckets[f"day_{x}"], reverse=True):
                key = f"day_{i}"
                subtract = min(remaining_discharge, new_buckets[key])
                new_buckets[key] -= subtract
                remaining_discharge -= subtract
                if remaining_discharge <= 0:
                    break

    # B群退院: day_6〜day_14から按分
    b_total = sum(new_buckets.get(f"day_{i}", 0) for i in range(6, 15))
    if b_total > 0 and discharge_b > 0:
        remaining_discharge = discharge_b
        for i in range(6, 15):
            key = f"day_{i}"
            proportion = new_buckets[key] / b_total
            subtract = min(round(proportion * discharge_b), new_buckets[key], remaining_discharge)
            new_buckets[key] -= subtract
            remaining_discharge -= subtract
        if remaining_discharge > 0:
            for i in sorted(range(6, 15), key=lambda x: new_buckets[f"day_{x}"], reverse=True):
                key = f"day_{i}"
                subtract = min(remaining_discharge, new_buckets[key])
                new_buckets[key] -= subtract
                remaining_discharge -= subtract
                if remaining_discharge <= 0:
                    break

    # C群退院: day_15plusから引く
    new_buckets["day_15plus"] = max(0, new_buckets["day_15plus"] - discharge_c)

    # 4. 負の値防止
    for key in new_buckets:
        new_buckets[key] = max(0, int(new_buckets[key]))

    return new_buckets


def buckets_to_abc(buckets: dict) -> tuple:
    """日齢バケットからA/B/C群人数を算出"""
    a = sum(buckets.get(f"day_{i}", 0) for i in range(1, 6))
    b = sum(buckets.get(f"day_{i}", 0) for i in range(6, 15))
    c = buckets.get("day_15plus", 0)
    return a, b, c


def create_initial_buckets_from_list(day_list: list) -> dict:
    """
    患者ごとの入院日数リストから日齢バケットを作成。

    Args:
        day_list: [3, 12, 22, 5, 8, ...] 各患者の入院日数

    Returns:
        日齢バケット辞書
    """
    buckets = {key: 0 for key in DAY_BUCKET_KEYS}
    for days in day_list:
        days = max(1, int(days))
        if days >= 15:
            buckets["day_15plus"] += 1
        else:
            buckets[f"day_{days}"] += 1
    return buckets


def _generate_los_distribution(max_days: int, rng) -> list:
    """
    リアルな在院日数の確率分布を生成（内部ヘルパー関数）。

    短期（1-5日）が少なめ、中期（6-14日）が最多、長期（15日以上）が一定割合。

    Args:
        max_days: 最大日数
        rng: numpy乱数ジェネレータ

    Returns:
        確率分布リスト（合計1.0）
    """
    weights = []
    for d in range(1, max_days + 1):
        if d <= 5:
            # A群相当: 比較的少ない（新規入院直後）
            w = 1.5
        elif d <= 14:
            # B群相当: 最も多い（入院中盤）
            w = 4.0
        else:
            # C群相当: やや多い（長期入院）
            w = 3.0
        # 若干のランダム変動
        w *= rng.uniform(0.8, 1.2)
        weights.append(w)
    total = sum(weights)
    return [w / total for w in weights]


def generate_sample_data(num_days=30, num_beds=None, seed=42, ward="all"):
    """
    デモ用サンプルデータを生成（個人情報なし、集計値のみ）。

    稼働率85-97%の範囲でランダム変動。
    入退院はポアソン分布（平均5名/日）。
    A/B/C構成比は日齢バケットから算出。
    週末は入院がやや少ない。

    Note:
        日齢バケット履歴は df.attrs["bucket_history"] に格納される。
        アプリ側では session_state で管理することを推奨。
    """
    if num_beds is None:
        num_beds = get_ward_beds(ward)
    rng = np.random.default_rng(seed)
    today = pd.Timestamp.now().normalize()
    start_date = today - timedelta(days=num_days - 1)

    records = []
    bucket_history = []  # 日齢バケット履歴（session_state管理用）

    # 初期患者数（稼働率90%付近）
    current_patients = int(num_beds * 0.90)

    # 初日の日齢バケットをランダム生成（1〜30日の範囲で分布）
    initial_day_list = []
    for _ in range(current_patients):
        # リアルな在院日数分布: 短期〜長期まで幅広く
        los = int(rng.choice(
            list(range(1, 31)),
            p=_generate_los_distribution(30, rng),
        ))
        initial_day_list.append(los)
    current_buckets = create_initial_buckets_from_list(initial_day_list)

    for i in range(num_days):
        d = start_date + timedelta(days=i)
        dow = d.dayofweek  # 0=月, 6=日

        # 入院数（週末はやや少ない）
        if dow >= 5:  # 土日
            admission_mean = 3.5
        elif dow == 0:  # 月曜
            admission_mean = 6.0
        else:
            admission_mean = 5.0
        new_admissions = int(rng.poisson(admission_mean))

        # 短手3（内数）: 新規入院数の0〜30%程度をランダムに設定（Phase 1: 記録のみ）
        # 当院実績: 月20-25件（≒新規入院の15%前後）を反映
        if new_admissions > 0:
            short3_ratio = rng.uniform(0.0, 0.30)
            new_admissions_short3 = int(round(new_admissions * short3_ratio))
        else:
            new_admissions_short3 = 0

        # 退院数（退院は在院患者数に比例、週末はやや少ない）
        discharge_rate = 0.055 if dow < 5 else 0.035
        expected_discharges = current_patients * discharge_rate
        discharges_raw = int(rng.poisson(max(1, expected_discharges)))
        discharges = min(discharges_raw, current_patients)

        # 退院内訳を生成（退院数をA/B/Cに分配）
        if discharges > 0:
            # A群退院（短期入院 1-5日目）: 10-20%
            da_ratio = rng.uniform(0.10, 0.20)
            # B群退院（中期入院 6-14日目）: 30-40%
            db_ratio = rng.uniform(0.30, 0.40)
            dc_ratio = 1.0 - da_ratio - db_ratio

            discharge_a = int(round(discharges * da_ratio))
            discharge_b = int(round(discharges * db_ratio))
            discharge_c = discharges - discharge_a - discharge_b  # 端数調整
            discharge_c = max(0, discharge_c)
        else:
            discharge_a = 0
            discharge_b = 0
            discharge_c = 0

        # 日齢バケットの進行（2日目以降はadvance_day_bucketsで更新）
        if i == 0:
            # 初日: 初期バケットに新規入院と退院を反映
            current_buckets["day_1"] = current_buckets.get("day_1", 0) + new_admissions
            # 退院処理（初日も按分で処理）
            a_total = sum(current_buckets.get(f"day_{j}", 0) for j in range(1, 6))
            if a_total > 0 and discharge_a > 0:
                rem = discharge_a
                for j in range(1, 6):
                    key = f"day_{j}"
                    prop = current_buckets[key] / a_total
                    sub = min(round(prop * discharge_a), current_buckets[key], rem)
                    current_buckets[key] -= sub
                    rem -= sub
            b_total = sum(current_buckets.get(f"day_{j}", 0) for j in range(6, 15))
            if b_total > 0 and discharge_b > 0:
                rem = discharge_b
                for j in range(6, 15):
                    key = f"day_{j}"
                    prop = current_buckets[key] / b_total
                    sub = min(round(prop * discharge_b), current_buckets[key], rem)
                    current_buckets[key] -= sub
                    rem -= sub
            current_buckets["day_15plus"] = max(0, current_buckets.get("day_15plus", 0) - discharge_c)
            for key in current_buckets:
                current_buckets[key] = max(0, int(current_buckets[key]))
        else:
            current_buckets = advance_day_buckets(
                current_buckets, new_admissions, discharge_a, discharge_b, discharge_c
            )

        # バケットからA/B/C群を算出
        phase_a, phase_b, phase_c = buckets_to_abc(current_buckets)

        # 患者数更新（バケット合計と整合性を取る）
        bucket_total = phase_a + phase_b + phase_c
        current_patients = max(0, min(num_beds, bucket_total))

        # バケット履歴を保存
        bucket_history.append(current_buckets.copy())

        # 平均在院日数（やや変動）
        avg_los_val = round(rng.normal(17.5, 1.5), 1)
        avg_los_val = max(12.0, min(25.0, avg_los_val))

        records.append({
            "date": d,
            "ward": ward,
            "total_patients": current_patients,
            "new_admissions": new_admissions,
            "new_admissions_short3": new_admissions_short3,
            "discharges": discharges,
            "discharge_a": discharge_a,
            "discharge_b": discharge_b,
            "discharge_c": discharge_c,
            "phase_a_count": phase_a,
            "phase_b_count": phase_b,
            "phase_c_count": phase_c,
            "avg_los": avg_los_val,
            "notes": "",
        })

    df = pd.DataFrame(records)
    df["ward"] = df["ward"].astype("string")
    # バケット履歴をDataFrameの属性として保持（session_state管理用）
    df.attrs["bucket_history"] = bucket_history
    for col in ["total_patients", "new_admissions", "new_admissions_short3",
                 "discharges",
                 "discharge_a", "discharge_b", "discharge_c",
                 "phase_a_count", "phase_b_count", "phase_c_count"]:
        df[col] = df[col].astype("Int64")
    df["avg_los"] = df["avg_los"].astype("Float64")
    df["notes"] = df["notes"].astype("string")
    df["data_source"] = "demo"

    return df


# ===========================================================================
# 入退院詳細レコード管理（医師別・イベント単位）
# ===========================================================================
import uuid
from collections import defaultdict

# 入退院詳細レコードのカラム定義
ADMISSION_DETAIL_COLUMNS = [
    "id",                # ユニークイベントID (UUID)
    "date",              # イベント日付 (YYYY-MM-DD)
    "ward",              # 病棟 ("5F" or "6F")
    "event_type",        # "admission" or "discharge"
    "route",             # 入院経路（外来紹介/救急/連携室/ウォークイン）— 入院のみ
    "source_doctor",     # 入院創出医 — 入院のみ、空欄可
    "attending_doctor",  # 入院担当医/主治医
    "los_days",          # 在院日数 — 退院のみ、入院時は空欄
    "phase",             # A/B/C — 退院のみ、los_daysから自動計算
    "short3_type",       # 短手3 種類 — 入院のみ、"該当なし"/"大腸ポリペク..."等、Phase 3
]

# 有効な入院経路
VALID_ROUTES = ["外来紹介", "救急", "連携室", "ウォークイン"]

# 有効なイベント種別
VALID_EVENT_TYPES = ["admission", "discharge"]

# 有効な病棟
VALID_WARDS = ["5F", "6F"]


def _los_to_phase(los_days: int) -> str:
    """在院日数からフェーズ（A/B/C）を自動判定する。"""
    if los_days <= 5:
        return "A"
    elif los_days <= 14:
        return "B"
    else:
        return "C"


def create_empty_detail_dataframe() -> pd.DataFrame:
    """入退院詳細レコード用の空DataFrameを作成（カラム定義済み）。"""
    df = pd.DataFrame(columns=ADMISSION_DETAIL_COLUMNS)
    df["id"] = df["id"].astype("string")
    df["date"] = pd.to_datetime(df["date"])
    df["ward"] = df["ward"].astype("string")
    df["event_type"] = df["event_type"].astype("string")
    df["route"] = df["route"].astype("string")
    df["source_doctor"] = df["source_doctor"].astype("string")
    df["attending_doctor"] = df["attending_doctor"].astype("string")
    df["los_days"] = df["los_days"].astype("Int64")
    df["phase"] = df["phase"].astype("string")
    df["short3_type"] = df["short3_type"].astype("string")
    return df


def add_admission_event(
    df,
    date,
    ward,
    route,
    source_doctor,
    attending_doctor,
    short3_type=None,
):
    """
    入院イベントを追加する。

    Args:
        df: 既存の詳細DataFrame
        date: 入院日（YYYY-MM-DD形式の文字列またはdatetime）
        ward: 病棟（"5F" or "6F"）
        route: 入院経路（外来紹介/救急/連携室/ウォークイン）
        source_doctor: 入院創出医（空文字列可）
        attending_doctor: 入院担当医/主治医
        short3_type: 短手3 の種類（"該当なし"/"大腸ポリペク..."等、Phase 3）

    Returns:
        レコード追加後のDataFrame
    """
    event_id = str(uuid.uuid4())
    new_row = pd.DataFrame([{
        "id": event_id,
        "date": pd.to_datetime(date),
        "ward": ward,
        "event_type": "admission",
        "route": route,
        "source_doctor": source_doctor if source_doctor else pd.NA,
        "attending_doctor": attending_doctor,
        "los_days": pd.NA,
        "phase": pd.NA,
        "short3_type": short3_type if short3_type else pd.NA,
    }])
    # 型を合わせる
    new_row["id"] = new_row["id"].astype("string")
    new_row["ward"] = new_row["ward"].astype("string")
    new_row["event_type"] = new_row["event_type"].astype("string")
    new_row["route"] = new_row["route"].astype("string")
    new_row["source_doctor"] = new_row["source_doctor"].astype("string")
    new_row["attending_doctor"] = new_row["attending_doctor"].astype("string")
    new_row["los_days"] = new_row["los_days"].astype("Int64")
    new_row["phase"] = new_row["phase"].astype("string")
    new_row["short3_type"] = new_row["short3_type"].astype("string")

    # 既存 df に short3_type 列がない場合は追加（後方互換）
    if "short3_type" not in df.columns:
        df = df.copy()
        df["short3_type"] = pd.Series([pd.NA] * len(df), dtype="string")

    df = pd.concat([df, new_row], ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


def add_discharge_event(
    df: pd.DataFrame,
    date: str | datetime,
    ward: str,
    attending_doctor: str,
    los_days: int,
) -> pd.DataFrame:
    """
    退院イベントを追加する。phaseはlos_daysから自動計算。

    Args:
        df: 既存の詳細DataFrame
        date: 退院日（YYYY-MM-DD形式の文字列またはdatetime）
        ward: 病棟（"5F" or "6F"）
        attending_doctor: 主治医
        los_days: 在院日数

    Returns:
        レコード追加後のDataFrame
    """
    event_id = str(uuid.uuid4())
    phase = _los_to_phase(los_days)
    new_row = pd.DataFrame([{
        "id": event_id,
        "date": pd.to_datetime(date),
        "ward": ward,
        "event_type": "discharge",
        "route": pd.NA,
        "source_doctor": pd.NA,
        "attending_doctor": attending_doctor,
        "los_days": los_days,
        "phase": phase,
        "short3_type": pd.NA,
    }])
    # 型を合わせる
    new_row["id"] = new_row["id"].astype("string")
    new_row["ward"] = new_row["ward"].astype("string")
    new_row["event_type"] = new_row["event_type"].astype("string")
    new_row["route"] = new_row["route"].astype("string")
    new_row["source_doctor"] = new_row["source_doctor"].astype("string")
    new_row["attending_doctor"] = new_row["attending_doctor"].astype("string")
    new_row["los_days"] = new_row["los_days"].astype("Int64")
    new_row["phase"] = new_row["phase"].astype("string")
    new_row["short3_type"] = new_row["short3_type"].astype("string")

    # 既存 df に short3_type 列がない場合は追加（後方互換）
    if "short3_type" not in df.columns:
        df = df.copy()
        df["short3_type"] = pd.Series([pd.NA] * len(df), dtype="string")

    df = pd.concat([df, new_row], ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


def get_events_by_date(df: pd.DataFrame, date_str: str) -> pd.DataFrame:
    """指定日付のイベントを抽出する。"""
    target_date = pd.to_datetime(date_str)
    return df[df["date"] == target_date].reset_index(drop=True)


def get_events_by_doctor(
    df: pd.DataFrame,
    doctor_name: str,
    role: str = "attending",
) -> pd.DataFrame:
    """
    医師名でイベントを抽出する。

    Args:
        df: 詳細DataFrame
        doctor_name: 医師名
        role: "attending"（主治医）or "source"（入院創出医）

    Returns:
        該当医師のイベントDataFrame
    """
    if role == "source":
        return df[df["source_doctor"] == doctor_name].reset_index(drop=True)
    else:
        return df[df["attending_doctor"] == doctor_name].reset_index(drop=True)


def get_monthly_summary_by_doctor(
    df: pd.DataFrame,
    year_month_str: str,
) -> dict:
    """
    指定月の医師別サマリーを返す。

    Args:
        df: 詳細DataFrame
        year_month_str: "YYYY-MM" 形式（例: "2026-04"）

    Returns:
        dict: {
            "doctor_name": {
                "admissions": int,        # 主治医としての入院数
                "admissions_created": int, # 入院創出医としての入院数
                "discharges": int,         # 退院数
                "avg_los": float,          # 平均在院日数
                "phase_distribution": {"A": int, "B": int, "C": int},
            },
            ...
        }
    """
    # 月でフィルタ
    df_copy = df.copy()
    df_copy["date"] = pd.to_datetime(df_copy["date"])
    df_copy["year_month"] = df_copy["date"].dt.strftime("%Y-%m")
    monthly = df_copy[df_copy["year_month"] == year_month_str]

    # 全医師名を収集（attending_doctor + source_doctor）
    doctors = set()
    doctors.update(monthly["attending_doctor"].dropna().unique())
    doctors.update(monthly["source_doctor"].dropna().unique())

    result = {}
    for doc in sorted(doctors):
        # 主治医としての入院数
        adm_attending = monthly[
            (monthly["attending_doctor"] == doc) & (monthly["event_type"] == "admission")
        ]
        # 入院創出医としての入院数
        adm_source = monthly[
            (monthly["source_doctor"] == doc) & (monthly["event_type"] == "admission")
        ]
        # 退院数（主治医として）
        dis = monthly[
            (monthly["attending_doctor"] == doc) & (monthly["event_type"] == "discharge")
        ]
        # 平均在院日数
        los_vals = dis["los_days"].dropna()
        avg_los = float(los_vals.mean()) if len(los_vals) > 0 else 0.0

        # フェーズ分布
        phase_dist = {"A": 0, "B": 0, "C": 0}
        for p in dis["phase"].dropna():
            if p in phase_dist:
                phase_dist[p] += 1

        result[doc] = {
            "admissions": len(adm_attending),
            "admissions_created": len(adm_source),
            "discharges": len(dis),
            "avg_los": round(avg_los, 1),
            "phase_distribution": phase_dist,
        }

    return result


def get_discharge_weekday_distribution(
    df,
    doctor_name=None,
):
    """
    退院の曜日別分布を返す。

    Args:
        df: 詳細DataFrame
        doctor_name: 医師名（Noneなら全体）

    Returns:
        dict: {0: count, 1: count, ..., 6: count}  (0=月曜)
    """
    discharges = df[df["event_type"] == "discharge"].copy()
    if doctor_name is not None:
        discharges = discharges[discharges["attending_doctor"] == doctor_name]

    discharges["date"] = pd.to_datetime(discharges["date"])
    discharges["weekday"] = discharges["date"].dt.dayofweek  # 0=月曜

    # 0〜6の全曜日を初期化
    dist = {i: 0 for i in range(7)}
    counts = discharges["weekday"].value_counts().to_dict()
    dist.update({int(k): int(v) for k, v in counts.items()})
    return dist


def export_details_to_csv(df: pd.DataFrame) -> str:
    """入退院詳細DataFrameをCSV文字列として返す（UTF-8）。"""
    work = df.copy()
    if "date" in work.columns:
        work["date"] = pd.to_datetime(work["date"]).dt.strftime("%Y-%m-%d")
    buf = io.StringIO()
    work.to_csv(buf, index=False, encoding="utf-8")
    return buf.getvalue()


def import_details_from_csv(csv_content: str) -> tuple[pd.DataFrame, str]:
    """
    CSVから入退院詳細レコードをインポートする。

    Returns:
        (DataFrame, エラーメッセージ) — エラーがなければ空文字列
    """
    try:
        buf = io.StringIO(csv_content)
        raw = pd.read_csv(buf)
    except Exception as e:
        return create_empty_detail_dataframe(), f"CSVの読み込みに失敗しました: {e}"

    # 必須カラムチェック
    required = ["date", "ward", "event_type", "attending_doctor"]
    missing = [c for c in required if c not in raw.columns]
    if missing:
        return create_empty_detail_dataframe(), f"必須カラムが不足しています: {', '.join(missing)}"

    # 型変換
    try:
        raw["date"] = pd.to_datetime(raw["date"])
    except Exception:
        return create_empty_detail_dataframe(), "date列の日付変換に失敗しました。YYYY-MM-DD形式で記載してください。"

    # idがない場合はUUIDを自動生成
    if "id" not in raw.columns:
        raw["id"] = [str(uuid.uuid4()) for _ in range(len(raw))]

    # オプションカラムの補完
    for col in ["route", "source_doctor", "phase"]:
        if col not in raw.columns:
            raw[col] = pd.NA
    if "los_days" not in raw.columns:
        raw["los_days"] = pd.NA

    # 文字列型
    for col in ["id", "ward", "event_type", "route", "source_doctor",
                 "attending_doctor", "phase"]:
        if col in raw.columns:
            raw[col] = raw[col].astype("string")

    # 数値型
    raw["los_days"] = pd.to_numeric(raw["los_days"], errors="coerce").astype("Int64")

    # 退院レコードのphase自動計算（phaseが空でlos_daysがある場合）
    discharge_mask = (raw["event_type"] == "discharge") & raw["los_days"].notna()
    if discharge_mask.any():
        raw.loc[discharge_mask, "phase"] = raw.loc[discharge_mask, "los_days"].apply(
            lambda x: _los_to_phase(int(x))
        ).astype("string")

    # event_typeバリデーション
    invalid_events = raw[~raw["event_type"].isin(VALID_EVENT_TYPES)]
    if len(invalid_events) > 0:
        return create_empty_detail_dataframe(), \
            f"無効なevent_typeがあります（admission/dischargeのみ有効）: 行 {invalid_events.index.tolist()}"

    # wardバリデーション
    invalid_wards = raw[~raw["ward"].isin(VALID_WARDS)]
    if len(invalid_wards) > 0:
        return create_empty_detail_dataframe(), \
            f"無効なwardがあります（5F/6Fのみ有効）: 行 {invalid_wards.index.tolist()}"

    # 既知カラムだけ残す
    raw = raw[[c for c in ADMISSION_DETAIL_COLUMNS if c in raw.columns]]

    raw = raw.sort_values("date").reset_index(drop=True)
    return raw, ""


def save_details(
    df: pd.DataFrame,
    filepath: str = "data/admission_details.csv",
) -> None:
    """入退院詳細DataFrameをCSVファイルに保存する。"""
    import os
    work = df.copy()
    if "date" in work.columns:
        work["date"] = pd.to_datetime(work["date"]).dt.strftime("%Y-%m-%d")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    work.to_csv(filepath, index=False, encoding="utf-8-sig")


def load_details(
    filepath: str = "data/admission_details.csv",
) -> pd.DataFrame:
    """CSVファイルから入退院詳細レコードを読み込む。ファイルがなければ空DataFrameを返す。"""
    import os
    if not os.path.exists(filepath):
        return create_empty_detail_dataframe()

    try:
        raw = pd.read_csv(filepath)
    except Exception:
        return create_empty_detail_dataframe()

    # 型変換
    if "date" in raw.columns:
        raw["date"] = pd.to_datetime(raw["date"])
    for col in ["id", "ward", "event_type", "route", "source_doctor",
                 "attending_doctor", "phase"]:
        if col in raw.columns:
            raw[col] = raw[col].astype("string")
    if "los_days" in raw.columns:
        raw["los_days"] = pd.to_numeric(raw["los_days"], errors="coerce").astype("Int64")

    # 欠損カラム補完
    for col in ADMISSION_DETAIL_COLUMNS:
        if col not in raw.columns:
            raw[col] = pd.NA

    raw = raw[[c for c in ADMISSION_DETAIL_COLUMNS if c in raw.columns]]
    return raw


def analyze_doctor_performance(
    df: pd.DataFrame,
    doctor_name: str,
    num_beds: int = 94,
) -> dict:
    """
    医師別パフォーマンス分析を行う。

    Args:
        df: 入退院詳細DataFrame
        doctor_name: 分析対象の医師名
        num_beds: 総病床数（稼働率寄与度の計算用）

    Returns:
        dict: {
            "monthly_admissions": int,          # 主治医としての月間入院数
            "monthly_admissions_created": int,   # 入院創出医としての月間入院数
            "monthly_discharges": int,           # 月間退院数
            "avg_los": float,                    # 平均在院日数
            "phase_distribution": {"A": int, "B": int, "C": int},
            "discharge_weekday_dist": {0: int, ..., 6: int},  # 0=月曜
            "occupancy_contribution_pct": float, # 稼働率への推定寄与度(%)
        }
    """
    df_copy = df.copy()
    df_copy["date"] = pd.to_datetime(df_copy["date"])

    # 主治医としての入院
    adm_attending = df_copy[
        (df_copy["attending_doctor"] == doctor_name) & (df_copy["event_type"] == "admission")
    ]
    # 入院創出医としての入院
    adm_source = df_copy[
        (df_copy["source_doctor"] == doctor_name) & (df_copy["event_type"] == "admission")
    ]
    # 主治医としての退院
    dis = df_copy[
        (df_copy["attending_doctor"] == doctor_name) & (df_copy["event_type"] == "discharge")
    ]

    # 平均在院日数
    los_vals = dis["los_days"].dropna()
    avg_los = float(los_vals.mean()) if len(los_vals) > 0 else 0.0

    # フェーズ分布
    phase_dist = {"A": 0, "B": 0, "C": 0}
    for p in dis["phase"].dropna():
        if p in phase_dist:
            phase_dist[p] += 1

    # 退院曜日分布
    weekday_dist = get_discharge_weekday_distribution(df_copy, doctor_name)

    # 稼働率への推定寄与度
    # = (この医師の入院患者が占める延べ患者日数) / (全体の延べ患者日数) の推定
    # 入院数 × 平均在院日数 で延べ患者日数を推定
    if avg_los > 0 and len(adm_attending) > 0:
        # データの期間（日数）を算出
        if len(df_copy) > 0:
            date_range_days = max(
                (df_copy["date"].max() - df_copy["date"].min()).days, 1
            )
        else:
            date_range_days = 30
        # この医師の推定延べ患者日数
        doctor_patient_days = len(adm_attending) * avg_los
        # 全体の推定延べ患者日数（病床数 × 日数）
        total_capacity_days = num_beds * date_range_days
        occupancy_contribution = (doctor_patient_days / total_capacity_days) * 100
    else:
        occupancy_contribution = 0.0

    return {
        "monthly_admissions": len(adm_attending),
        "monthly_admissions_created": len(adm_source),
        "monthly_discharges": len(dis),
        "avg_los": round(avg_los, 1),
        "phase_distribution": phase_dist,
        "discharge_weekday_dist": weekday_dist,
        "occupancy_contribution_pct": round(occupancy_contribution, 2),
    }


# ---------------------------------------------------------------------------
# 退院マネジメント機能
# ---------------------------------------------------------------------------

# フェーズ別日次運営貢献額（円）
_PHASE_DAILY_CONTRIBUTION = {
    "A": 24000,
    "B": 30000,
    "C": 28900,
}


def get_sunday_discharge_candidates(
    detail_df: pd.DataFrame,
    daily_df: pd.DataFrame,
    ward_beds: dict | None = None,
    max_avg_los: float = 21.0,
) -> list[dict]:
    """
    退院予定者のうち、日曜退院に調整可能な候補を抽出する。

    パターンA「延ばす」: 金曜・土曜退院 → 日曜退院（在院+1〜2日、週末稼働率UP）
    パターンB「早める」: 月曜・火曜退院 → 前の日曜退院（在院-1〜2日、月曜入院枠確保）

    Args:
        detail_df: admission_details.csv の DataFrame
            (columns: date, ward, event_type, los_days, phase, attending_doctor 等)
        daily_df: 日次データの DataFrame
            (columns: date, total_patients, new_admissions, discharges 等)
        ward_beds: 病棟別ベッド数 dict (例: {"5F": 47, "6F": 47})。
            None の場合はデフォルト値を使用。
        max_avg_los: 施設基準の平均在院日数上限（デフォルト 21.0 日）

    Returns:
        list[dict]: 各候補の情報を含む辞書のリスト。キー:
            ward, date, phase, los_days, attending_doctor,
            sunday_date, additional_days, los_margin,
            daily_contribution, recommendation, shift_type, benefit
    """
    if ward_beds is None:
        ward_beds = {"5F": 47, "6F": 47}

    if detail_df is None or len(detail_df) == 0:
        return []

    df = detail_df.copy()
    df["date"] = pd.to_datetime(df["date"])

    # 退院レコードを抽出
    discharges = df[df["event_type"] == "discharge"].copy()
    if len(discharges) == 0:
        return []

    discharges["weekday"] = discharges["date"].dt.dayofweek  # 0=月, 1=火, 4=金, 5=土
    # パターンA: 金曜(4)・土曜(5)、パターンB: 月曜(0)・火曜(1)
    target_discharges = discharges[discharges["weekday"].isin([0, 1, 4, 5])].copy()

    if len(target_discharges) == 0:
        return []

    # 現在のrolling平均在院日数を取得
    rolling_result = calculate_rolling_los(daily_df)
    current_rolling_los = (
        rolling_result["rolling_los"]
        if rolling_result is not None and rolling_result.get("rolling_los") is not None
        else 0.0
    )
    # rolling計算に使われた分母情報（影響度推定用）
    total_admissions = (
        rolling_result["total_admissions"]
        if rolling_result is not None
        else 0.0
    )
    total_discharges = (
        rolling_result["total_discharges"]
        if rolling_result is not None
        else 0.0
    )
    denominator = (total_admissions + total_discharges) / 2.0 if (total_admissions + total_discharges) > 0 else 1.0

    candidates = []
    for _, row in target_discharges.iterrows():
        weekday = int(row["weekday"])
        original_date = row["date"]

        if weekday in [4, 5]:
            # パターンA「延ばす」: 金曜→日曜(+2日), 土曜→日曜(+1日)
            additional_days = 7 - weekday  # 金(4)→+3ではなく6-4=2, 土(5)→1
            sunday_date = original_date + timedelta(days=additional_days)
            shift_type = "延ばす"
            benefit = "週末稼働率UP"
        else:
            # パターンB「早める」: 月曜→前日曜(-1日), 火曜→前々日曜(-2日)
            additional_days = -(weekday + 1)  # 月(0)→-1, 火(1)→-2
            sunday_date = original_date + timedelta(days=additional_days)
            shift_type = "早める"
            benefit = "在院日数短縮＋月曜入院枠確保"

        los_days = int(row["los_days"]) if pd.notna(row.get("los_days")) else 0
        phase = str(row["phase"]) if pd.notna(row.get("phase")) else ""

        # los_margin: 追加日数がrolling LOSに与える影響を加味
        # additional_daysが正なら延長、負なら短縮
        los_impact = additional_days / denominator if denominator > 0 else 0.0
        estimated_new_los = current_rolling_los + los_impact
        los_margin = round(max_avg_los - estimated_new_los, 1)

        # recommendation 判定
        if shift_type == "早める":
            # 早める場合は在院日数短縮なので基本的に推奨
            if phase == "C":
                recommendation = "◎"
            elif phase == "B":
                recommendation = "◎"
            else:
                recommendation = "△"
        else:
            # 延ばす場合は従来ロジック
            if phase == "C":
                if los_margin > 0:
                    recommendation = "◎"
                elif los_margin >= -0.5:
                    recommendation = "△"
                else:
                    recommendation = "✗"
            elif phase == "B":
                if los_margin < -0.5:
                    recommendation = "✗"
                else:
                    recommendation = "△"
            else:
                recommendation = "△"

        daily_contribution = _PHASE_DAILY_CONTRIBUTION.get(phase, 0)

        ward = str(row["ward"]) if pd.notna(row.get("ward")) else ""
        attending_doctor = str(row["attending_doctor"]) if pd.notna(row.get("attending_doctor")) else ""

        candidates.append({
            "ward": ward,
            "date": original_date.strftime("%Y-%m-%d"),
            "phase": phase,
            "los_days": los_days,
            "attending_doctor": attending_doctor,
            "sunday_date": sunday_date.strftime("%Y-%m-%d"),
            "additional_days": additional_days,
            "los_margin": los_margin,
            "daily_contribution": daily_contribution,
            "recommendation": recommendation,
            "shift_type": shift_type,
            "benefit": benefit,
        })

    # ソート: C群優先 → 同フェーズ内で「延ばす」先 → LOS余裕大きい順
    phase_priority = {"C": 0, "B": 1, "A": 2}
    shift_priority = {"延ばす": 0, "早める": 1}
    candidates.sort(key=lambda x: (
        phase_priority.get(x["phase"], 9),
        shift_priority.get(x["shift_type"], 9),
        -x["los_margin"],
    ))

    return candidates


def simulate_discharge_shift(
    daily_df: pd.DataFrame,
    detail_df: pd.DataFrame,
    n_shifts: int,
    beds_total: int = 94,
) -> dict:
    """
    「金曜退院のN人を日曜に移したら」の What-if シミュレーション。

    金曜退院をやめて日曜退院にすると、金曜・土曜に患者が残るため
    週末稼働率が向上し、追加の運営貢献額が発生する。

    Args:
        daily_df: 日次データの DataFrame
        detail_df: 入退院詳細の DataFrame
        n_shifts: 日曜にシフトする人数
        beds_total: 総病床数（デフォルト 94）

    Returns:
        dict: before / after / impact の3キーを持つ辞書
    """
    if daily_df is None or len(daily_df) == 0:
        empty_day = {"fri_occ_pct": 0.0, "sat_occ_pct": 0.0, "sun_occ_pct": 0.0,
                     "weekday_avg_occ": 0.0, "weekend_avg_occ": 0.0}
        return {
            "before": dict(empty_day),
            "after": dict(empty_day),
            "impact": {
                "weekend_occ_change_pt": 0.0,
                "additional_contribution_per_week": 0,
                "additional_contribution_per_month": 0,
                "los_impact_days": 0.0,
                "weekly_influence_amount": 0,
            },
        }

    df = daily_df.copy()
    date_col = "date" if "date" in df.columns else "日付"
    tp_col = "total_patients" if "total_patients" in df.columns else "在院患者数"

    df[date_col] = pd.to_datetime(df[date_col])
    df["weekday"] = df[date_col].dt.dayofweek  # 0=月曜

    # 曜日別平均在院患者数
    weekday_avg = df.groupby("weekday")[tp_col].mean()

    def occ_pct(patients):
        return round(patients / beds_total * 100, 1) if beds_total > 0 else 0.0

    fri_patients = weekday_avg.get(4, 0.0)
    sat_patients = weekday_avg.get(5, 0.0)
    sun_patients = weekday_avg.get(6, 0.0)

    # 平日平均（月〜金: 0-4）、週末平均（土日: 5-6）
    weekday_patients = np.mean([weekday_avg.get(i, 0.0) for i in range(5)])
    weekend_patients = np.mean([weekday_avg.get(i, 0.0) for i in [5, 6]])

    before = {
        "fri_occ_pct": occ_pct(fri_patients),
        "sat_occ_pct": occ_pct(sat_patients),
        "sun_occ_pct": occ_pct(sun_patients),
        "weekday_avg_occ": occ_pct(weekday_patients),
        "weekend_avg_occ": occ_pct(weekend_patients),
    }

    # シフト後の計算
    # 「延ばす」パターン（金土→日曜）: 金・土・日すべてに+n_shifts人
    #   退院日＝最終在院日なので、日曜も在院としてカウントされる
    # 注: 「早める」パターンとの混在はsimulate関数では未分離のため、
    #   ここでは従来の「延ばす」ベースで計算する
    after_fri = fri_patients + n_shifts
    after_sat = sat_patients + n_shifts
    after_sun = sun_patients + n_shifts  # 日曜も在院日（退院日＝最終在院日）

    # 平日平均の再計算（金曜に+n_shiftsの影響）
    after_weekday_patients = np.mean([
        weekday_avg.get(i, 0.0) + (n_shifts if i == 4 else 0)
        for i in range(5)
    ])
    after_weekend_patients = np.mean([after_sat, after_sun])

    after = {
        "fri_occ_pct": occ_pct(after_fri),
        "sat_occ_pct": occ_pct(after_sat),
        "sun_occ_pct": occ_pct(after_sun),
        "weekday_avg_occ": occ_pct(after_weekday_patients),
        "weekend_avg_occ": occ_pct(after_weekend_patients),
    }

    # 影響度計算
    weekend_occ_change = after["weekend_avg_occ"] - before["weekend_avg_occ"]

    # 追加運営貢献額: n_shifts人 × 追加2日（金土） × C群日次貢献額
    c_daily = _PHASE_DAILY_CONTRIBUTION["C"]
    additional_per_week = n_shifts * 2 * c_daily
    additional_per_month = additional_per_week * 4

    # 平均在院日数への影響
    rolling_result = calculate_rolling_los(daily_df)
    if rolling_result is not None:
        total_adm = rolling_result.get("total_admissions", 0)
        total_dis = rolling_result.get("total_discharges", 0)
        denom = (total_adm + total_dis) / 2.0 if (total_adm + total_dis) > 0 else 1.0
        # n_shifts人がそれぞれ2日延びる → 分子に+2*n_shifts
        los_impact_days = round((2 * n_shifts) / denom, 2)
    else:
        los_impact_days = 0.0

    # 週あたり空床影響額の削減（空床1床/日 ≒ 28,900円の機会損失）
    weekly_influence = n_shifts * 2 * c_daily

    impact = {
        "weekend_occ_change_pt": round(weekend_occ_change, 1),
        "additional_contribution_per_week": additional_per_week,
        "additional_contribution_per_month": additional_per_month,
        "los_impact_days": los_impact_days,
        "weekly_influence_amount": weekly_influence,
    }

    return {
        "before": before,
        "after": after,
        "impact": impact,
    }


def get_discharge_weekday_stats(detail_df: pd.DataFrame) -> dict:
    """
    退院曜日分布の統計情報を返す。

    既存の get_discharge_weekday_distribution() を拡張し、
    集中度指標や金曜比率などの追加統計を提供する。

    Args:
        detail_df: 入退院詳細の DataFrame

    Returns:
        dict: distribution, total, friday_count, friday_pct,
              weekend_count, weekend_pct, concentration_index, labels
    """
    labels = ["月", "火", "水", "木", "金", "土", "日"]

    if detail_df is None or len(detail_df) == 0:
        return {
            "distribution": {i: 0 for i in range(7)},
            "total": 0,
            "friday_count": 0,
            "friday_pct": 0.0,
            "weekend_count": 0,
            "weekend_pct": 0.0,
            "concentration_index": 0.0,
            "labels": labels,
        }

    distribution = get_discharge_weekday_distribution(detail_df)
    total = sum(distribution.values())

    friday_count = distribution.get(4, 0)
    friday_pct = round(friday_count / total * 100, 1) if total > 0 else 0.0

    weekend_count = distribution.get(5, 0) + distribution.get(6, 0)
    weekend_pct = round(weekend_count / total * 100, 1) if total > 0 else 0.0

    # 集中度: 金曜の退院数 / (全体の退院数 / 7) = 金曜が均等分布の何倍か
    avg_per_day = total / 7.0 if total > 0 else 1.0
    concentration_index = round(friday_count / avg_per_day, 2) if avg_per_day > 0 else 0.0

    return {
        "distribution": distribution,
        "total": total,
        "friday_count": friday_count,
        "friday_pct": friday_pct,
        "weekend_count": weekend_count,
        "weekend_pct": weekend_pct,
        "concentration_index": concentration_index,
        "labels": labels,
    }
