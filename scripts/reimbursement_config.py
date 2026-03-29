"""
地域包括医療病棟入院料 診療報酬シミュレーター 設定モジュール

令和8年度（2026年度）診療報酬改定に基づく点数体系・施設基準・加算の定義。
全ての定数をこのファイルで一元管理する。

参考資料:
- 厚労省「令和8年度診療報酬改定 4.包括期・慢性期入院医療」
- GemMed: 地域包括医療病棟を「3367-3066点」の6区分に細分化
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ===========================================================================
# 列挙型（Enum）
# ===========================================================================

class WardType(Enum):
    """届出区分: A100一般病棟入院基本料算定病棟の有無で決定"""
    TYPE_1 = "地域包括医療病棟入院料1"  # 急性期一般病棟を算定する病棟なし
    TYPE_2 = "地域包括医療病棟入院料2"  # 急性期一般病棟を算定する病棟あり


class AdmissionTier(Enum):
    """入院料1/2/3: 入院形態×手術有無で決定

    判定ロジック:
    - 入院料1: 救急搬送後の入院 かつ 手術なし → 最高点（救急医療の負荷を評価）
    - 入院料2: 救急搬送後の入院で手術あり ／ 予定入院で手術なし
    - 入院料3: 予定入院 かつ 手術あり → 最低点（計画的で効率的）
    """
    TIER_1 = "入院料1"  # 救急・手術なし（最高点）
    TIER_2 = "入院料2"  # 救急・手術あり ／ 予定・手術なし
    TIER_3 = "入院料3"  # 予定・手術あり（最低点）


class Department(Enum):
    """診療科"""
    INTERNAL = "内科"
    PAIN = "ペイン科"
    ORTHOPEDICS = "整形外科"
    SURGERY = "外科"


class ConstraintSeverity(Enum):
    """施設基準の重要度"""
    MUST = "MUST"      # 必須（満たさないと算定不可）
    SHOULD = "SHOULD"  # 推奨（満たさないと警告）


# ===========================================================================
# 点数テーブル（6区分）
# ===========================================================================

# WardType × AdmissionTier → 基本点数（1日につき）
POINT_TABLE: dict[tuple[WardType, AdmissionTier], int] = {
    # 地域包括医療病棟入院料1（A100一般病棟なし）
    (WardType.TYPE_1, AdmissionTier.TIER_1): 3367,  # 救急・手術なし
    (WardType.TYPE_1, AdmissionTier.TIER_2): 3267,  # 救急・手術あり / 予定・手術なし
    (WardType.TYPE_1, AdmissionTier.TIER_3): 3117,  # 予定・手術あり
    # 地域包括医療病棟入院料2（A100一般病棟あり）
    (WardType.TYPE_2, AdmissionTier.TIER_1): 3316,  # 救急・手術なし
    (WardType.TYPE_2, AdmissionTier.TIER_2): 3216,  # 救急・手術あり / 予定・手術なし
    (WardType.TYPE_2, AdmissionTier.TIER_3): 3066,  # 予定・手術あり
}

# 90日超の逓減点数
POINT_OVER_90_DAYS: int = 988  # 地域一般入院料3相当


# ===========================================================================
# 加算定義
# ===========================================================================

@dataclass
class AdditionalFee:
    """加算の定義

    Attributes:
        name: 加算名称
        points: 点数（1日につき）
        day_start: 適用開始日（1-indexed）
        day_end: 適用終了日（Noneなら無制限）
        enabled_default: デフォルトで有効か
        category: UI表示用のグループ名
        mutual_exclusion_group: 相互排他グループ（同グループ内で1つのみ選択可）
        description: 算定条件の説明
    """
    name: str
    points: int
    day_start: int
    day_end: Optional[int]
    enabled_default: bool
    category: str
    mutual_exclusion_group: Optional[str] = None
    description: str = ""


DEFAULT_FEES: list[AdditionalFee] = [
    # --- 基本加算 ---
    AdditionalFee(
        name="初期加算",
        points=150,
        day_start=1, day_end=14,
        enabled_default=True,
        category="基本加算",
        description="入院14日以内の全患者に算定",
    ),
    # --- リハ・栄養・口腔連携 ---
    AdditionalFee(
        name="リハビリテーション・栄養・口腔連携加算1",
        points=110,
        day_start=1, day_end=14,
        enabled_default=True,
        category="リハ・栄養・口腔連携",
        mutual_exclusion_group="リハ栄養口腔",
        description="リハ・栄養・口腔の3領域全てで計画策定・連携（入院14日以内）",
    ),
    AdditionalFee(
        name="リハビリテーション・栄養・口腔連携加算2",
        points=50,
        day_start=1, day_end=14,
        enabled_default=False,
        category="リハ・栄養・口腔連携",
        mutual_exclusion_group="リハ栄養口腔",
        description="リハ・栄養・口腔のうち一部で計画策定（入門編、入院14日以内）",
    ),
    # --- 看護補助体制 ---
    AdditionalFee(
        name="看護補助体制加算(25対1)",
        points=240,
        day_start=1, day_end=14,
        enabled_default=False,
        category="看護補助体制",
        mutual_exclusion_group="看護補助体制",
        description="看護補助者25対1配置（入院14日以内）",
    ),
    AdditionalFee(
        name="看護補助体制加算(50対1)",
        points=160,
        day_start=1, day_end=14,
        enabled_default=False,
        category="看護補助体制",
        mutual_exclusion_group="看護補助体制",
        description="看護補助者50対1配置（入院14日以内）",
    ),
    # --- 夜間看護 ---
    AdditionalFee(
        name="夜間看護補助体制加算(50対1)",
        points=125,
        day_start=1, day_end=None,
        enabled_default=False,
        category="夜間看護",
        mutual_exclusion_group="夜間看護",
        description="夜間看護補助者50対1配置（入院期間全体）",
    ),
    AdditionalFee(
        name="夜間看護補助体制加算(100対1)",
        points=105,
        day_start=1, day_end=None,
        enabled_default=False,
        category="夜間看護",
        mutual_exclusion_group="夜間看護",
        description="夜間看護補助者100対1配置（入院期間全体）",
    ),
    # --- 看護職員夜間配置 ---
    AdditionalFee(
        name="看護職員夜間配置加算(12対1)",
        points=110,
        day_start=1, day_end=14,
        enabled_default=False,
        category="看護職員夜間配置",
        mutual_exclusion_group="看護夜間配置",
        description="看護職員夜間12対1配置（入院14日以内）",
    ),
    AdditionalFee(
        name="看護職員夜間配置加算(16対1)",
        points=45,
        day_start=1, day_end=14,
        enabled_default=False,
        category="看護職員夜間配置",
        mutual_exclusion_group="看護夜間配置",
        description="看護職員夜間16対1配置（入院14日以内）",
    ),
    # --- 物価対応 ---
    AdditionalFee(
        name="物価対応料(令和8年度)",
        points=49,
        day_start=1, day_end=None,
        enabled_default=True,
        category="物価対応",
        mutual_exclusion_group="物価対応",
        description="令和8年度の物価高騰対応（入院期間全体）",
    ),
    AdditionalFee(
        name="物価対応料(令和9年度)",
        points=98,
        day_start=1, day_end=None,
        enabled_default=False,
        category="物価対応",
        mutual_exclusion_group="物価対応",
        description="令和9年度の物価高騰対応（入院期間全体、倍増）",
    ),
]


# ===========================================================================
# ケースミックス入力単位
# ===========================================================================

@dataclass
class CaseMixCell:
    """ケースミックスの1セル（病棟×診療科×入院形態×手術有無）

    Attributes:
        ward: 病棟名（"5F" or "6F"）
        department: 診療科
        is_emergency: 救急搬送後入院かどうか
        has_surgery: 主傷病に対する手術の有無
        monthly_count: 月間入院件数
        avg_los: 平均在院日数（日）
    """
    ward: str
    department: Department
    is_emergency: bool
    has_surgery: bool
    monthly_count: int = 0
    avg_los: float = 17.0

    @property
    def admission_tier(self) -> AdmissionTier:
        """入院形態と手術有無から入院料区分を自動判定"""
        if self.is_emergency and not self.has_surgery:
            return AdmissionTier.TIER_1  # 救急・手術なし → 最高点
        elif self.is_emergency and self.has_surgery:
            return AdmissionTier.TIER_2  # 救急・手術あり
        elif not self.is_emergency and not self.has_surgery:
            return AdmissionTier.TIER_2  # 予定・手術なし
        else:
            return AdmissionTier.TIER_3  # 予定・手術あり → 最低点

    @property
    def label(self) -> str:
        """表示用ラベル"""
        emg = "救急" if self.is_emergency else "予定"
        surg = "手術あり" if self.has_surgery else "手術なし"
        return f"{self.ward} {self.department.value} {emg} {surg}"


# ===========================================================================
# 施設基準（制約条件）
# ===========================================================================

@dataclass
class FacilityConstraint:
    """施設基準の制約条件

    Attributes:
        name: 基準名
        threshold: 閾値
        operator: 比較演算子（"<=", ">=", "<", ">"）
        severity: MUST or SHOULD
        description: 基準の説明
        unit: 単位
        adjustable: 85歳以上割合等で閾値が変動するか
    """
    name: str
    threshold: float
    operator: str
    severity: ConstraintSeverity
    description: str
    unit: str
    adjustable: bool = False


FACILITY_CONSTRAINTS: list[FacilityConstraint] = [
    FacilityConstraint(
        name="平均在院日数",
        threshold=20.0,
        operator="<=",
        severity=ConstraintSeverity.MUST,
        description="20日以内（85歳以上割合20%ごとに+1日、最大24日）",
        unit="日",
        adjustable=True,
    ),
    FacilityConstraint(
        name="救急搬送後患者割合",
        threshold=15.0,
        operator=">=",
        severity=ConstraintSeverity.MUST,
        description="入院患者のうち救急搬送後の患者が15%以上",
        unit="%",
    ),
    FacilityConstraint(
        name="ADL低下割合",
        threshold=5.0,
        operator="<",
        severity=ConstraintSeverity.MUST,
        description="退院時ADLが入院時より低下した患者が5%未満"
                    "（85歳以上割合による緩和あり）",
        unit="%",
        adjustable=True,
    ),
    FacilityConstraint(
        name="在宅復帰率",
        threshold=72.5,
        operator=">=",
        severity=ConstraintSeverity.MUST,
        description="自宅等に退院した患者割合が72.5%以上",
        unit="%",
    ),
    FacilityConstraint(
        name="重症度・医療看護必要度",
        threshold=16.0,
        operator=">=",
        severity=ConstraintSeverity.MUST,
        description="重症度、医療・看護必要度の該当患者割合が16%以上"
                    "（必要度IまたはII）",
        unit="%",
    ),
    FacilityConstraint(
        name="データ提出加算",
        threshold=1.0,
        operator=">=",
        severity=ConstraintSeverity.MUST,
        description="データ提出加算の届出を行っていること",
        unit="（届出済=1）",
    ),
    FacilityConstraint(
        name="リハ専門職配置",
        threshold=1.0,
        operator=">=",
        severity=ConstraintSeverity.SHOULD,
        description="リハビリテーション専門職（PT/OT/ST）の病棟配置（推奨）",
        unit="名以上",
    ),
]


# ===========================================================================
# 病院デフォルト設定（おもろまちメディカルセンター）
# ===========================================================================

HOSPITAL_DEFAULTS = {
    "name": "おもろまちメディカルセンター",
    "total_beds": 94,
    "wards": {"5F": 47, "6F": 47},
    "ward_descriptions": {
        "5F": "外科・整形外科（手術・リハ中心）",
        "6F": "内科・ペイン科（内科系・疼痛管理中心）",
    },
    "department_mix": {
        Department.INTERNAL: 0.50,
        Department.PAIN: 0.15,
        Department.ORTHOPEDICS: 0.15,
        Department.SURGERY: 0.20,
    },
    "default_ward_type": WardType.TYPE_1,
    "default_avg_los": 17.0,
    "age_85_plus_ratio": 0.25,  # 推定25%
}


# ===========================================================================
# 診療科別デフォルトケースミックス
# ===========================================================================

# 診療科ごとの典型的な入院パターン
# (救急割合, 手術割合, 平均在院日数, 主な配置病棟)
DEPARTMENT_DEFAULTS: dict[Department, dict] = {
    Department.INTERNAL: {
        "emergency_ratio": 0.70,  # 内科は救急搬送が多い
        "surgery_ratio": 0.05,    # 内科で手術はほぼなし
        "avg_los": 16.0,
        "primary_ward": "6F",
        "monthly_count": 75,      # 月150件の50%
    },
    Department.PAIN: {
        "emergency_ratio": 0.10,  # ペインは予定入院が多い
        "surgery_ratio": 0.05,    # ペインで手術はほぼなし
        "avg_los": 12.0,
        "primary_ward": "6F",
        "monthly_count": 22,      # 月150件の約15%
    },
    Department.ORTHOPEDICS: {
        "emergency_ratio": 0.40,  # 骨折等の救急あり
        "surgery_ratio": 0.80,    # 整形は手術が多い
        "avg_los": 20.0,
        "primary_ward": "5F",
        "monthly_count": 23,      # 月150件の約15%
    },
    Department.SURGERY: {
        "emergency_ratio": 0.30,  # 緊急手術あり
        "surgery_ratio": 0.85,    # 外科は手術が多い
        "avg_los": 14.0,
        "primary_ward": "5F",
        "monthly_count": 30,      # 月150件の約20%
    },
}


# ===========================================================================
# コスト関連定数（ベッドコントロールシミュレーターとの連携用）
# ===========================================================================

# フェーズ別コスト（限界利益ベース: 変動費のみ。固定費は空床でも発生するため除外）
PHASE_COSTS = {
    "A": {  # 入院1-5日目
        "revenue_per_day": 36000,   # 全加算込み（初期加算+リハ栄養口腔+物価対応）
        "cost_per_day": 12000,      # 変動費（検査・薬剤・画像集中）
        "profit_per_day": 24000,
    },
    "B": {  # 入院6-14日目
        "revenue_per_day": 36000,   # A群と同じ加算構造
        "cost_per_day": 6000,       # 変動費（急性期処置終了、残存薬剤・検査のみ）
        "profit_per_day": 30000,    # ★最大限界利益フェーズ
    },
    "C": {  # 入院15日目以降
        "revenue_per_day": 33400,   # 初期加算+リハ加算消失で-2,600円
        "cost_per_day": 4500,       # 変動費（薬剤・給食等の最低限変動費のみ）
        "profit_per_day": 28900,
    },
}

# 空床1日あたり機会損失（限界利益ベース）
OPPORTUNITY_COST_PER_EMPTY_BED: int = 25000  # 円/日

# 1点あたり単価
YEN_PER_POINT: int = 10
