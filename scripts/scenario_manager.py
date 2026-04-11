"""
シナリオ保存・比較・AI分析マネージャー

ベッドコントロールシミュレーターの What-if 分析結果を保存・比較し、
ルールベースの分析（LLM不使用）で改善提案を生成する pure function モジュール。

病院概要:
    - 総病床数94床（5F: 47床、6F: 47床）
    - 月間入院数 約150件
    - 稼働率1% ≈ 年間約1,200万円の収益影響
    - 目標稼働率: 90-95%（最適ゾーン 92.5%）
    - 平均在院日数上限: 85歳以上割合に応じて20-24日（2026年改定）

Streamlit に依存しない。すべての関数は dict / list を返す。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# 外部モジュールのインポート（フォールバック付き）
# ---------------------------------------------------------------------------

try:
    from scripts.db_manager import get_connection, DB_PATH
except ImportError:
    try:
        from db_manager import get_connection, DB_PATH
    except ImportError:
        get_connection = None  # type: ignore
        DB_PATH = None

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

TARGET_OCCUPANCY_OPTIMAL = 92.5  # 最適稼働率 (%)
TARGET_OCCUPANCY_LOWER = 90.0   # 目標下限 (%)
TARGET_OCCUPANCY_UPPER = 95.0   # 目標上限 (%)
OCCUPANCY_DANGER_LOW = 85.0     # 危険域下限 (%)
REVENUE_PER_OCCUPANCY_PCT = 1200  # 稼働率1%あたり年間収益影響（万円）
C_GROUP_DAILY_CONTRIBUTION = 28900  # C群運営貢献額（円/日）

# 実現可能性の判定基準
FEASIBILITY_THRESHOLDS = {
    "c_discharge_easy": 2,       # C群退院調整 1-2名 = 容易
    "admission_increase_moderate": 0.05,  # 入院数5%増 = 中程度
}


# ---------------------------------------------------------------------------
# DB ヘルパー関数
# ---------------------------------------------------------------------------


def _get_db_path(db_path: Optional[str] = None) -> str:
    """DBパスを解決する。"""
    return db_path if db_path is not None else (DB_PATH or "")


def _serialize(obj: Any) -> str:
    """dict/list を JSON 文字列にシリアライズする。"""
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    return json.dumps(obj, ensure_ascii=False, default=str)


def _deserialize(s: str) -> Any:
    """JSON 文字列を dict/list にデシリアライズする。"""
    if not s:
        return None
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return s


# ---------------------------------------------------------------------------
# 1. Save / Load / List / Delete — シナリオ CRUD
# ---------------------------------------------------------------------------


def save_scenario(
    name: str,
    scenario_type: str,
    parameters: dict,
    results: dict,
    baseline_snapshot: Optional[dict] = None,
    tags: Optional[List[str]] = None,
    notes: str = "",
    db_path: Optional[str] = None,
) -> str:
    """シナリオを保存し、生成された ID を返す。

    Args:
        name: シナリオ名（例: "C群2名退院前倒し"）
        scenario_type: シナリオ種別（"whatif_mixed", "whatif_weekly", "whatif_phase" 等）
        parameters: シナリオのパラメータ dict
        results: シミュレーション結果 dict
        baseline_snapshot: ベースライン状態のスナップショット（任意）
        tags: タグリスト（任意）
        notes: メモ
        db_path: データベースファイルパス

    Returns:
        生成された UUID 文字列
    """
    scenario_id = str(uuid.uuid4())
    created_at = datetime.now().isoformat()
    tags_str = ",".join(tags) if tags else ""

    conn = get_connection(_get_db_path(db_path))
    if conn is None:
        return scenario_id

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO saved_scenarios
            (id, name, scenario_type, created_at, parameters, results,
             baseline_snapshot, tags, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scenario_id,
                name,
                scenario_type,
                created_at,
                _serialize(parameters),
                _serialize(results),
                _serialize(baseline_snapshot),
                tags_str,
                notes,
            ),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"シナリオ保存エラー: {e}")
    finally:
        conn.close()

    return scenario_id


def load_scenario(
    scenario_id: str,
    db_path: Optional[str] = None,
) -> Optional[dict]:
    """シナリオを ID で読み込む。

    Args:
        scenario_id: シナリオ UUID
        db_path: データベースファイルパス

    Returns:
        シナリオ dict。見つからない場合は None
    """
    conn = get_connection(_get_db_path(db_path))
    if conn is None:
        return None

    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, scenario_type, created_at, parameters, results, "
            "baseline_snapshot, tags, notes FROM saved_scenarios WHERE id = ?",
            (scenario_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        return {
            "id": row[0],
            "name": row[1],
            "scenario_type": row[2],
            "created_at": row[3],
            "parameters": _deserialize(row[4]),
            "results": _deserialize(row[5]),
            "baseline_snapshot": _deserialize(row[6]),
            "tags": row[7].split(",") if row[7] else [],
            "notes": row[8] or "",
        }
    except Exception as e:
        print(f"シナリオ読み込みエラー: {e}")
        return None
    finally:
        conn.close()


def list_scenarios(
    scenario_type: Optional[str] = None,
    limit: int = 50,
    db_path: Optional[str] = None,
) -> List[dict]:
    """保存済みシナリオの一覧を返す。

    Args:
        scenario_type: フィルタ（None なら全件）
        limit: 最大件数
        db_path: データベースファイルパス

    Returns:
        シナリオ dict のリスト（新しい順）
    """
    conn = get_connection(_get_db_path(db_path))
    if conn is None:
        return []

    try:
        cursor = conn.cursor()
        if scenario_type is not None:
            cursor.execute(
                "SELECT id, name, scenario_type, created_at, tags, notes "
                "FROM saved_scenarios WHERE scenario_type = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (scenario_type, limit),
            )
        else:
            cursor.execute(
                "SELECT id, name, scenario_type, created_at, tags, notes "
                "FROM saved_scenarios ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )

        rows = cursor.fetchall()
        return [
            {
                "id": r[0],
                "name": r[1],
                "scenario_type": r[2],
                "created_at": r[3],
                "tags": r[4].split(",") if r[4] else [],
                "notes": r[5] or "",
            }
            for r in rows
        ]
    except Exception as e:
        print(f"シナリオ一覧取得エラー: {e}")
        return []
    finally:
        conn.close()


def delete_scenario(
    scenario_id: str,
    db_path: Optional[str] = None,
) -> bool:
    """シナリオを削除する。

    Args:
        scenario_id: シナリオ UUID
        db_path: データベースファイルパス

    Returns:
        削除成功なら True
    """
    conn = get_connection(_get_db_path(db_path))
    if conn is None:
        return False

    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM saved_scenarios WHERE id = ?", (scenario_id,))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        conn.rollback()
        print(f"シナリオ削除エラー: {e}")
        return False
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 2. 比較保存 CRUD
# ---------------------------------------------------------------------------


def save_comparison(
    name: str,
    scenario_ids: List[str],
    analysis_result: Optional[dict] = None,
    notes: str = "",
    db_path: Optional[str] = None,
) -> str:
    """比較結果を保存する。

    Args:
        name: 比較名
        scenario_ids: 比較対象シナリオ ID リスト
        analysis_result: 分析結果 dict
        notes: メモ
        db_path: データベースファイルパス

    Returns:
        生成された UUID 文字列
    """
    comparison_id = str(uuid.uuid4())
    created_at = datetime.now().isoformat()

    conn = get_connection(_get_db_path(db_path))
    if conn is None:
        return comparison_id

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO scenario_comparisons
            (id, name, created_at, scenario_ids, analysis_result, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                comparison_id,
                name,
                created_at,
                _serialize(scenario_ids),
                _serialize(analysis_result),
                notes,
            ),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"比較結果保存エラー: {e}")
    finally:
        conn.close()

    return comparison_id


def load_comparison(
    comparison_id: str,
    db_path: Optional[str] = None,
) -> Optional[dict]:
    """比較結果を読み込む。

    Args:
        comparison_id: 比較 UUID
        db_path: データベースファイルパス

    Returns:
        比較結果 dict。見つからない場合は None
    """
    conn = get_connection(_get_db_path(db_path))
    if conn is None:
        return None

    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, created_at, scenario_ids, analysis_result, notes "
            "FROM scenario_comparisons WHERE id = ?",
            (comparison_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        return {
            "id": row[0],
            "name": row[1],
            "created_at": row[2],
            "scenario_ids": _deserialize(row[3]),
            "analysis_result": _deserialize(row[4]),
            "notes": row[5] or "",
        }
    except Exception as e:
        print(f"比較結果読み込みエラー: {e}")
        return None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 3. compare_scenarios — シナリオ比較
# ---------------------------------------------------------------------------


def _extract_occupancy(scenario: dict) -> Optional[float]:
    """シナリオ結果から稼働率(%)を抽出する。"""
    results = scenario.get("results")
    if not results:
        return None
    # whatif_mixed_scenario 形式
    if isinstance(results, dict):
        sc = results.get("scenario", {})
        occ = sc.get("occupancy")
        if occ is not None:
            return float(occ) * 100.0 if occ <= 1.0 else float(occ)
    return None


def _extract_revenue(scenario: dict) -> Optional[float]:
    """シナリオ結果から年間収益影響(万円)を抽出する。"""
    results = scenario.get("results")
    if not results:
        return None
    if isinstance(results, dict):
        diff = results.get("diff", {})
        daily_profit = diff.get("daily_profit")
        if daily_profit is not None:
            # 日次差分 × 365 / 10000 で万円/年
            return round(float(daily_profit) * 365 / 10000, 1)
        # scenario側の daily_profit から直接算出
        sc = results.get("scenario", {})
        dp = sc.get("daily_profit")
        if dp is not None:
            bl = results.get("baseline", {}).get("daily_profit", 0)
            return round(float(dp - bl) * 365 / 10000, 1)
    return None


def _extract_los(scenario: dict) -> Optional[float]:
    """シナリオ結果から在院日数を抽出する。"""
    results = scenario.get("results")
    if not results or not isinstance(results, dict):
        return None
    # whatif_phase 形式
    los = results.get("target_los")
    if los is not None:
        return float(los)
    # パラメータから推定
    params = scenario.get("parameters")
    if params and isinstance(params, dict):
        los_p = params.get("target_los") or params.get("avg_los")
        if los_p is not None:
            return float(los_p)
    return None


def compare_scenarios(
    scenario_ids: List[str],
    db_path: Optional[str] = None,
) -> dict:
    """複数シナリオを比較し、メトリクス表を生成する。

    Args:
        scenario_ids: 比較対象シナリオ ID リスト
        db_path: データベースファイルパス

    Returns:
        比較結果 dict
    """
    scenarios = []
    for sid in scenario_ids:
        s = load_scenario(sid, db_path=db_path)
        if s is not None:
            scenarios.append(s)

    if not scenarios:
        return {
            "scenarios": [],
            "comparison": {
                "occupancy_range": [0, 0],
                "revenue_range": [0, 0],
                "best_occupancy_id": None,
                "best_revenue_id": None,
                "metrics_table": [],
            },
        }

    occupancies = []
    revenues = []
    metrics_table = []

    best_occ_id = None
    best_occ_dist = float("inf")
    best_rev_id = None
    best_rev_val = float("-inf")

    for s in scenarios:
        occ = _extract_occupancy(s)
        rev = _extract_revenue(s)
        los = _extract_los(s)

        if occ is not None:
            occupancies.append(occ)
            dist = abs(occ - TARGET_OCCUPANCY_OPTIMAL)
            if dist < best_occ_dist:
                best_occ_dist = dist
                best_occ_id = s["id"]

        if rev is not None:
            revenues.append(rev)
            if rev > best_rev_val:
                best_rev_val = rev
                best_rev_id = s["id"]

        metrics_table.append({
            "name": s.get("name", ""),
            "稼働率": f"{occ:.1f}%" if occ is not None else "N/A",
            "収益影響": f"{rev:+.1f}万円/年" if rev is not None else "N/A",
            "在院日数": f"{los:.1f}日" if los is not None else "N/A",
        })

    occ_range = [min(occupancies), max(occupancies)] if occupancies else [0, 0]
    rev_range = [min(revenues), max(revenues)] if revenues else [0, 0]

    return {
        "scenarios": scenarios,
        "comparison": {
            "occupancy_range": occ_range,
            "revenue_range": rev_range,
            "best_occupancy_id": best_occ_id,
            "best_revenue_id": best_rev_id,
            "metrics_table": metrics_table,
        },
    }


# ---------------------------------------------------------------------------
# 4. analyze_scenarios — ルールベース AI 分析
# ---------------------------------------------------------------------------


def _classify_feasibility(scenario: dict) -> tuple[str, str]:
    """シナリオの実現可能性を判定する。

    Returns:
        (星表示, 説明テキスト)
    """
    params = scenario.get("parameters", {})
    results = scenario.get("results", {})

    if not params and not results:
        return ("★★☆", "情報不足のため中程度と仮定")

    # C群退院調整の検出
    discharge_detail = results.get("discharge_detail", {}) if isinstance(results, dict) else {}
    c_discharge = discharge_detail.get("c", 0)
    total_discharge = discharge_detail.get("total", 0)
    new_admissions = discharge_detail.get("new_admissions", 0)

    # C群1-2名退院 = 容易
    if c_discharge > 0 and c_discharge <= FEASIBILITY_THRESHOLDS["c_discharge_easy"] and new_admissions <= 2:
        return ("★☆☆", "C群退院調整のみで実現可能")

    # 入院数増加が大きい場合 = 困難
    if new_admissions > 5:
        return ("★★★", "入院数の大幅増加が必要")

    # デフォルト = 中程度
    if total_discharge > 3 or new_admissions > 2:
        return ("★★☆", "複数の退院調整または入院増加が必要")

    return ("★☆☆", "小規模な運用調整で実現可能")


def _calculate_occupancy_score(occupancy_pct: Optional[float]) -> float:
    """稼働率の最適度スコア（0-100）を返す。92.5%に近いほど高い。"""
    if occupancy_pct is None:
        return 0.0
    distance = abs(occupancy_pct - TARGET_OCCUPANCY_OPTIMAL)
    # 10ポイント離れたらスコア0
    return max(0.0, 100.0 - distance * 10.0)


def analyze_scenarios(
    scenarios: List[dict],
    current_metrics: Optional[dict] = None,
    guardrail_status: Optional[List[dict]] = None,
    emergency_summary: Optional[dict] = None,
) -> dict:
    """シナリオ群をルールベースで分析し、提案を生成する。

    LLM APIを使用しない決定論的分析（院内ネットワーク分離環境対応）。

    Args:
        scenarios: シナリオ dict のリスト
        current_metrics: 現在の病棟指標（occupancy_pct, los, daily_profit 等）
        guardrail_status: calculate_guardrail_status() の戻り値
        emergency_summary: get_ward_emergency_summary() の戻り値

    Returns:
        分析結果 dict
    """
    if not scenarios:
        return {
            "insights": [],
            "recommendations": [],
            "best_scenario": None,
            "risk_assessment": "分析対象のシナリオがありません。",
            "summary": "シナリオが選択されていないため、分析を実行できません。",
        }

    insights: List[Dict[str, Any]] = []
    scored_scenarios: List[Dict[str, Any]] = []

    # --- LOS ガードレール情報の取得 ---
    los_limit = None
    los_current = None
    los_status = None
    if guardrail_status:
        for item in guardrail_status:
            if item.get("name") == "平均在院日数":
                los_limit = item.get("threshold")
                los_current = item.get("current_value")
                los_status = item.get("status")
                break

    # --- 救急搬送比率の状態取得 ---
    emergency_red_wards: List[str] = []
    if emergency_summary:
        for ward in ("5F", "6F"):
            ward_data = emergency_summary.get(ward, {})
            dual = ward_data.get("dual_ratio", {})
            official = dual.get("official", {})
            if official.get("status") == "red":
                emergency_red_wards.append(ward)

    # --- 各シナリオの分析 ---
    for s in scenarios:
        occ = _extract_occupancy(s)
        rev = _extract_revenue(s)
        los = _extract_los(s)
        feasibility, feasibility_note = _classify_feasibility(s)
        occ_score = _calculate_occupancy_score(occ)

        # 稼働率の判定
        penalty = 0.0
        if occ is not None:
            if occ > TARGET_OCCUPANCY_UPPER:
                insights.append({
                    "type": "finding",
                    "text": f"「{s.get('name', '')}」は稼働率{occ:.1f}%で目標上限{TARGET_OCCUPANCY_UPPER:.0f}%を超過。"
                            f"受入余力が不足し、救急対応に支障が出る可能性があります。",
                    "priority": "high",
                })
                penalty += 20.0
            elif occ < OCCUPANCY_DANGER_LOW:
                insights.append({
                    "type": "finding",
                    "text": f"「{s.get('name', '')}」は稼働率{occ:.1f}%で危険域（{OCCUPANCY_DANGER_LOW:.0f}%未満）。"
                            f"年間約{(TARGET_OCCUPANCY_OPTIMAL - occ) * REVENUE_PER_OCCUPANCY_PCT / 100:.0f}万円の機会損失。",
                    "priority": "high",
                })
                penalty += 30.0

        # LOS コンプライアンス
        if los is not None and los_limit is not None:
            if los > los_limit:
                insights.append({
                    "type": "finding",
                    "text": f"「{s.get('name', '')}」の平均在院日数{los:.1f}日はガードレール上限{los_limit:.0f}日を超過。"
                            f"施設基準違反のリスクがあります。",
                    "priority": "high",
                })
                penalty += 40.0
            elif los > los_limit - 2.0:
                insights.append({
                    "type": "finding",
                    "text": f"「{s.get('name', '')}」の平均在院日数{los:.1f}日はガードレール上限{los_limit:.0f}日に接近。"
                            f"余力{los_limit - los:.1f}日と薄いため注意が必要です。",
                    "priority": "medium",
                })
                penalty += 10.0

        # LOS ガードレール warning/danger 時の追加インサイト
        if los_status in ("warning", "danger"):
            insights.append({
                "type": "finding",
                "text": f"現在の在院日数がガードレール警告域です（現在値{los_current}日 / 上限{los_limit}日）。"
                        f"「{s.get('name', '')}」が在院日数に与える影響に注意してください。",
                "priority": "high" if los_status == "danger" else "medium",
            })

        # 救急搬送比率との相互作用
        if emergency_red_wards and occ is not None and occ > TARGET_OCCUPANCY_OPTIMAL:
            affected_wards = "・".join(emergency_red_wards)
            insights.append({
                "type": "finding",
                "text": f"{affected_wards}の救急搬送後患者割合が未達（赤）です。"
                        f"「{s.get('name', '')}」は稼働率を上げるため、空床が減少し救急受入に支障が出る可能性があります。",
                "priority": "high",
            })
            penalty += 15.0

        # 総合スコア（100点満点）
        rev_score = 0.0
        if rev is not None:
            # 収益影響を正規化（+500万円/年で100点）
            rev_score = min(max(rev / 500.0 * 100.0, -50.0), 100.0)

        total_score = occ_score * 0.4 + rev_score * 0.4 + (100.0 if feasibility == "★☆☆" else 50.0 if feasibility == "★★☆" else 20.0) * 0.2
        total_score = max(0.0, total_score - penalty)

        scored_scenarios.append({
            "scenario": s,
            "occupancy_pct": occ,
            "revenue_万円_year": rev,
            "los": los,
            "feasibility": feasibility,
            "feasibility_note": feasibility_note,
            "score": round(total_score, 1),
        })

    # --- 収益ランキング ---
    revenue_sorted = sorted(
        [ss for ss in scored_scenarios if ss["revenue_万円_year"] is not None],
        key=lambda x: x["revenue_万円_year"],  # type: ignore
        reverse=True,
    )
    if len(revenue_sorted) >= 2:
        best_rev = revenue_sorted[0]
        worst_rev = revenue_sorted[-1]
        diff = (best_rev["revenue_万円_year"] or 0) - (worst_rev["revenue_万円_year"] or 0)
        if diff > 0:
            insights.append({
                "type": "finding",
                "text": f"収益影響の差は最大{diff:.1f}万円/年。"
                        f"最良は「{best_rev['scenario'].get('name', '')}」（{best_rev['revenue_万円_year']:+.1f}万円/年）。",
                "priority": "medium",
            })

    # --- 推奨シナリオ（スコア順） ---
    scored_scenarios.sort(key=lambda x: x["score"], reverse=True)

    recommendations: List[Dict[str, Any]] = []
    for rank, ss in enumerate(scored_scenarios[:3], start=1):
        s = ss["scenario"]
        rev = ss["revenue_万円_year"]
        occ = ss["occupancy_pct"]
        risk_parts = []
        if occ is not None and occ > TARGET_OCCUPANCY_UPPER:
            risk_parts.append(f"稼働率{occ:.1f}%で目標上限超過")
        if ss["los"] is not None and los_limit is not None and ss["los"] > los_limit - 2.0:
            risk_parts.append(f"在院日数{ss['los']:.1f}日でガードレール接近")
        if emergency_red_wards and occ is not None and occ > TARGET_OCCUPANCY_OPTIMAL:
            risk_parts.append("救急受入余力の低下")
        risk_text = "、".join(risk_parts) if risk_parts else "特になし"

        recommendations.append({
            "rank": rank,
            "action": s.get("name", f"シナリオ{rank}"),
            "expected_impact": f"年間{rev:+.1f}万円" if rev is not None else "算出不可",
            "feasibility": ss["feasibility"],
            "risk": risk_text,
        })

    # --- ベストシナリオ ---
    best = scored_scenarios[0] if scored_scenarios else None
    best_scenario = None
    if best:
        reason_parts = []
        if best["occupancy_pct"] is not None:
            reason_parts.append(f"稼働率{best['occupancy_pct']:.1f}%")
        if best["revenue_万円_year"] is not None:
            reason_parts.append(f"収益影響{best['revenue_万円_year']:+.1f}万円/年")
        reason_parts.append(f"実現可能性{best['feasibility']}")

        best_scenario = {
            "id": best["scenario"].get("id", ""),
            "name": best["scenario"].get("name", ""),
            "reason": "、".join(reason_parts) + "の総合評価で最良",
        }

    # --- リスク評価 ---
    risk_items = []
    if los_status in ("warning", "danger"):
        risk_items.append("在院日数がガードレール警告/危険域にあり、シナリオ実行時に施設基準違反のリスクがあります")
    if emergency_red_wards:
        risk_items.append(f"{'・'.join(emergency_red_wards)}の救急搬送後患者割合が未達のため、空床を確保する必要があります")
    high_occ = [ss for ss in scored_scenarios if ss["occupancy_pct"] is not None and ss["occupancy_pct"] > TARGET_OCCUPANCY_UPPER]
    if high_occ:
        risk_items.append(f"{len(high_occ)}件のシナリオが稼働率上限を超過しており、受入余力が不足する可能性があります")
    risk_assessment = "。".join(risk_items) if risk_items else "重大なリスクは検出されませんでした。"

    # --- サマリー ---
    summary_parts = [f"{len(scenarios)}件のシナリオを分析しました。"]
    if best:
        summary_parts.append(
            f"総合評価では「{best['scenario'].get('name', '')}」が最良です"
            + (f"（稼働率{best['occupancy_pct']:.1f}%、年間{best['revenue_万円_year']:+.1f}万円）。"
               if best["occupancy_pct"] is not None and best["revenue_万円_year"] is not None
               else "。")
        )
    if risk_items:
        summary_parts.append(f"ただし、{risk_items[0]}。")

    # 重複インサイトの除去
    seen_texts = set()
    unique_insights = []
    for ins in insights:
        if ins["text"] not in seen_texts:
            seen_texts.add(ins["text"])
            unique_insights.append(ins)

    return {
        "insights": unique_insights,
        "recommendations": recommendations,
        "best_scenario": best_scenario,
        "risk_assessment": risk_assessment,
        "summary": "".join(summary_parts),
    }
