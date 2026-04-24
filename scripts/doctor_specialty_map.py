"""医師コード → 診療科グループ マッピング.

副院長指示 (2026-04-24): 事務提供データの「診療科」列は細かすぎたり
医師の実態と合わないケースがあるため、副院長が医師本人の所属で
明示的に定義するマッピングを正とする。

例: TATM/UEMH は事務データ上 "内科" だが、実質的には
外来専任・訪問診療医として機能しており、病棟担当の peer 比較には
含めない方が妥当。
"""

from __future__ import annotations

from typing import Dict

# 医師コード → 診療科グループ
DOCTOR_SPECIALTY_GROUP: Dict[str, str] = {
    # 内科（循環器内科を含む）
    "OHSY": "内科",
    "TERUH": "内科",
    "KONA": "内科",
    "KUBT": "内科",
    "INOT": "内科",   # 事務データ上 循内科 → 実務は内科
    "HAYT": "内科",
    "SIROK": "内科",
    "FKDM": "内科",
    # ペイン科
    "HIGT": "ペイン科",
    "KJJ": "ペイン科",
    # 整形外科
    "OKUK": "整形外科",
    # 外科
    "HIGN": "外科",
    "TAM": "外科",
    "TAIRK": "外科",
    # 脳神経外科
    "HOKM": "脳神経外科",
    # 病棟担当なし（peer 比較対象外）
    "TATM": "外来専任",
    "UEMH": "訪問診療医",
}


def get_specialty_group(doctor_code: str) -> str:
    """医師コードから診療科グループを取得. 未登録は "未分類" を返す."""
    return DOCTOR_SPECIALTY_GROUP.get(doctor_code, "未分類")
