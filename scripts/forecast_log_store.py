"""退院カレンダー予測の backtesting ログ store.

2026-04-24 実装: 副院長の「予測精度を事後検証したい」要望に応える。

毎日カレンダー予測グラフを描画するときに、その時点での予測 snapshot
（日毎の在院数・稼働率）を JSON で保存する。後日、実データが入った
タイミングで `compare_with_actuals()` を呼べば、MAPE・バイアス・的中率が
算出でき、予測モデルの精度改善の根拠データとなる。

データ形式
----------
- 保存先: `data/forecast_snapshots/ward_YYYY-MM-DD.json`
  - 1 ファイル = 1 (病棟 × 生成日) の snapshot
  - 同じ日に複数回生成されても最新で上書き（精度評価上の問題なし）
- レコード構造:
  {
    "ward": "5F",
    "generated_at": "2026-04-24T12:00:00",
    "horizon_days": 30,
    "items": [
      {"date": "2026-04-25", "inpatients": 45.0, "occupancy": 95.7, "total_beds": 47},
      ...
    ]
  }

精度評価指標
-------------
- MAPE (Mean Absolute Percentage Error): 予測値 vs 実績値の相対誤差平均
- Bias: 予測値 − 実績値の平均（+ なら過大予測、− なら過小予測）
- Hit rate (±2 名以内): 在院数の絶対誤差が 2 名以下の日の割合
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

SNAPSHOT_DIR: Path = Path(__file__).resolve().parent.parent / "data" / "forecast_snapshots"
HIT_RATE_TOLERANCE: float = 2.0  # ±2 名以内なら的中扱い


def _ensure_dir() -> None:
    """保存ディレクトリを作成（存在しなければ）."""
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


def _snapshot_path(ward: str, generated_on: date) -> Path:
    """snapshot ファイルパスを返す."""
    return SNAPSHOT_DIR / f"{ward}_{generated_on.isoformat()}.json"


def save_forecast_snapshot(
    ward: str,
    forecast: List[Dict[str, Any]],
    total_beds: int,
    generated_at: Optional[datetime] = None,
) -> bool:
    """予測 snapshot を保存.

    Args:
        ward: 病棟名（"5F" or "6F"）
        forecast: `_compute_occupancy_forecast` の戻り値（list of dict）
        total_beds: 病床数
        generated_at: 生成時刻（省略時は now）

    Returns:
        True = 保存成功、False = 失敗
    """
    if not forecast or not ward:
        return False
    _ensure_dir()
    gen = generated_at if generated_at is not None else datetime.now()
    record = {
        "ward": ward,
        "generated_at": gen.isoformat(timespec="seconds"),
        "total_beds": int(total_beds),
        "horizon_days": len(forecast),
        "items": [
            {
                "date": r["date"].isoformat() if isinstance(r["date"], date) else str(r["date"]),
                "inpatients": float(r.get("inpatients", 0)),
                "occupancy": float(r.get("occupancy", 0)),
            }
            for r in forecast
        ],
    }
    path = _snapshot_path(ward, gen.date())
    try:
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except OSError:
        return False


def load_all_snapshots(ward: Optional[str] = None) -> List[Dict[str, Any]]:
    """全 snapshot を読み込む.

    Args:
        ward: 病棟フィルタ。None なら全病棟。

    Returns:
        snapshot レコードのリスト（古い順）。
    """
    if not SNAPSHOT_DIR.exists():
        return []

    records: List[Dict[str, Any]] = []
    pattern = f"{ward}_*.json" if ward else "*.json"
    for path in sorted(SNAPSHOT_DIR.glob(pattern)):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "items" in data:
                records.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return records


def compare_with_actuals(
    snapshots: List[Dict[str, Any]],
    actual_by_date_ward: Dict[str, Dict[str, float]],
    min_horizon_days: int = 1,
    max_horizon_days: int = 14,
) -> Dict[str, Any]:
    """予測 snapshot を実績と突合.

    各 snapshot の各予測日について、実績在院数と比較する。
    評価対象は ``[min_horizon_days, max_horizon_days]`` の horizon のみ
    （当日予測や遠すぎる予測を除外）。

    Args:
        snapshots: ``load_all_snapshots`` の戻り値
        actual_by_date_ward: ``{"YYYY-MM-DD": {"5F": 在院数, "6F": 在院数}}``
        min_horizon_days: 評価する最小 horizon（既定 1 = 翌日）
        max_horizon_days: 評価する最大 horizon（既定 14 = 2 週）

    Returns:
        dict: {
            "by_ward": {
                "5F": {
                    "n": int, "mape": float, "bias": float,
                    "hit_rate_2": float, "mae": float,
                    "by_horizon": {1: {...}, 2: {...}, ...},
                },
                "6F": {...},
            },
            "total_comparisons": int,
        }
    """
    if not snapshots or not actual_by_date_ward:
        return {"by_ward": {}, "total_comparisons": 0}

    by_ward: Dict[str, List[Dict[str, float]]] = {}

    for snap in snapshots:
        ward = snap.get("ward")
        if not ward:
            continue
        gen_at = snap.get("generated_at", "")
        try:
            gen_date = datetime.fromisoformat(gen_at).date()
        except (ValueError, TypeError):
            continue

        for item in snap.get("items", []):
            iso = item.get("date", "")
            try:
                target_date = date.fromisoformat(iso)
            except (ValueError, TypeError):
                continue
            horizon = (target_date - gen_date).days
            if horizon < min_horizon_days or horizon > max_horizon_days:
                continue
            actual_rec = actual_by_date_ward.get(iso, {})
            actual = actual_rec.get(ward)
            if actual is None:
                continue

            predicted = item.get("inpatients", 0.0)
            error = predicted - actual
            by_ward.setdefault(ward, []).append({
                "horizon": horizon,
                "predicted": float(predicted),
                "actual": float(actual),
                "error": float(error),
                "abs_error": float(abs(error)),
                "pct_error": float(abs(error) / actual * 100) if actual > 0 else 0.0,
            })

    result: Dict[str, Any] = {"by_ward": {}, "total_comparisons": 0}
    total = 0

    for ward, records in by_ward.items():
        if not records:
            continue
        n = len(records)
        total += n
        mape = sum(r["pct_error"] for r in records) / n
        bias = sum(r["error"] for r in records) / n
        mae = sum(r["abs_error"] for r in records) / n
        hit = sum(1 for r in records if r["abs_error"] <= HIT_RATE_TOLERANCE) / n * 100

        # horizon 別集計
        by_horizon: Dict[int, Dict[str, float]] = {}
        horizons = sorted(set(r["horizon"] for r in records))
        for h in horizons:
            h_records = [r for r in records if r["horizon"] == h]
            if not h_records:
                continue
            by_horizon[h] = {
                "n": len(h_records),
                "mae": round(sum(r["abs_error"] for r in h_records) / len(h_records), 2),
                "bias": round(sum(r["error"] for r in h_records) / len(h_records), 2),
            }

        result["by_ward"][ward] = {
            "n": n,
            "mape": round(mape, 2),
            "bias": round(bias, 2),
            "mae": round(mae, 2),
            "hit_rate_2": round(hit, 1),
            "by_horizon": by_horizon,
        }

    result["total_comparisons"] = total
    return result


def estimate_dow_stats(
    daily_values: Dict[date, float],
) -> Dict[int, Dict[str, float]]:
    """日次値を曜日別に集計し、平均と標準偏差を返す.

    Args:
        daily_values: ``{date: 値}`` の辞書（全期間分）

    Returns:
        ``{0: {"mean": x, "std": y, "n": int}, ...}``。weekday 番号をキー。
    """
    from statistics import mean, pstdev
    by_dow: Dict[int, List[float]] = {i: [] for i in range(7)}
    for d, v in daily_values.items():
        by_dow[d.weekday()].append(float(v))

    result: Dict[int, Dict[str, float]] = {}
    for dow, vals in by_dow.items():
        if not vals:
            result[dow] = {"mean": 0.0, "std": 0.0, "n": 0}
            continue
        m = mean(vals)
        s = pstdev(vals) if len(vals) >= 2 else 0.0
        result[dow] = {
            "mean": round(m, 2),
            "std": round(s, 2),
            "n": len(vals),
        }
    return result


def build_actual_inpatients_map(
    admission_details_df,
    start_date: date,
    end_date: date,
) -> Dict[str, Dict[str, float]]:
    """admission_details から日次実績在院数を計算.

    予測精度評価のため、過去の各日の在院数を再構築する。
    admission/discharge イベントから時点在院数を累積計算。

    Args:
        admission_details_df: イベント DataFrame
        start_date: 対象期間の開始
        end_date: 対象期間の終了

    Returns:
        ``{"YYYY-MM-DD": {"5F": 在院数, "6F": 在院数}}``
    """
    result: Dict[str, Dict[str, float]] = {}
    if admission_details_df is None or len(admission_details_df) == 0:
        return result
    required = {"event_type", "date", "ward"}
    if not required.issubset(admission_details_df.columns):
        return result

    import pandas as pd  # 遅延 import

    df = admission_details_df.copy()
    df["_date"] = pd.to_datetime(df["date"], errors="coerce").dt.date

    # 病棟別に累積在院数を計算
    for ward in ("5F", "6F"):
        ward_df = df[df["ward"] == ward]
        if ward_df.empty:
            continue

        adm_by_date = ward_df[ward_df["event_type"] == "admission"].groupby("_date").size()
        dis_by_date = ward_df[ward_df["event_type"] == "discharge"].groupby("_date").size()

        # 累積在院数
        all_dates = sorted(set(adm_by_date.index) | set(dis_by_date.index))
        running = 0
        daily_inp: Dict[date, int] = {}
        for d in all_dates:
            running += int(adm_by_date.get(d, 0))
            running -= int(dis_by_date.get(d, 0))
            daily_inp[d] = max(0, running)

        # 対象期間のみ抽出して結果に反映
        cur = start_date
        last_known = 0
        while cur <= end_date:
            if cur in daily_inp:
                last_known = daily_inp[cur]
            iso = cur.isoformat()
            result.setdefault(iso, {})[ward] = float(last_known)
            cur = cur + timedelta(days=1)

    return result
