# ChatGPT検証依頼 — 救急搬送後患者割合15%管理（v3.3）

## 実装概要

地域包括医療病棟の施設基準では「救急搬送後の入院患者割合が15%以上」であることが求められる。本実装（v3.3）では、この要件を **病棟別（5F/6F）・単月** で管理するための新規モジュール `emergency_ratio.py`（690行）を作成し、既存の `bed_control_simulator_app.py` にサブタブ「🚑 救急搬送15%」として統合した。また、既存の `guardrail_engine.py` の救急搬送割合計算に分母バグがあったため修正し、C群コントロールとの連携アラートも追加した。

ChatGPTによる事前レビューのフィードバックを受けて、`calculate_additional_needed()` の過大推定バグを修正し、教育用デモデータ（下り搬送・短手3含む）を拡充した。

## 変更ファイル一覧

| ファイル | 変更種別 | 行数 | 概要 |
|:---|:---|:---|:---|
| `scripts/emergency_ratio.py` | 新規作成 | 690行 | コア計算ロジック（8関数） |
| `tests/test_emergency_ratio.py` | 新規作成 | 579行 | テスト17件 |
| `scripts/bed_control_simulator_app.py` | 変更 | +430行 | サブタブ4追加（UI実装） |
| `scripts/guardrail_engine.py` | 変更 | +9/-4行 | 分母バグ修正 + 下り搬送追加 |
| `scripts/c_group_control.py` | 変更 | +21行 | emergency_ratio_risk連携 |
| `data/admission_details.csv` | 変更 | 再生成 | 教育用デモデータ拡充 |
| `scripts/generate_sample_data.py` | 変更 | +472行 | デモデータ生成ロジック改善 |
| `scripts/help_content.py` | 変更 | +47行 | ヘルプ追加 |
| `docs/admin/BedControl_Manual_v3.md` | 変更 | +179行 | マニュアル追記 |
| `scripts/bed_data_manager.py` | 変更 | +6/-4行 | 軽微修正 |
| `tests/test_guardrail_engine.py` | 変更 | +7/-3行 | 分母修正に伴うテスト調整 |

## 1. データモデル

### 1-1. 分子・分母の定義

```python
# emergency_ratio.py L30-33
EMERGENCY_THRESHOLD_PCT: float = 15.0
EMERGENCY_MARGIN_PCT: float = 17.0  # green 閾値（2pt マージン）
EMERGENCY_ROUTES: list[str] = ["救急", "下り搬送"]
SHORT3_DEFAULT_LABEL: str = "該当なし"
```

- **分子**: `route` が `["救急", "下り搬送"]` のいずれかに該当する入院イベント
- **分母（届出確認用）**: 当該月・当該病棟の全入院イベント（`event_type == "admission"`）
- **分母（院内運用用）**: 上記から短手3を除外した入院イベント

### 1-2. ルートカテゴリ

```python
# emergency_ratio.py L40-46
_ROUTE_KEY_MAP: dict[str, str] = {
    "救急": "ambulance",
    "下り搬送": "downstream",
    "外来紹介": "scheduled",
    "連携室": "liaison",
    "ウォークイン": "walkin",
}
```

v3.2まで `VALID_ROUTES` に「下り搬送」は含まれていなかった。v3.3で追加し、分子にも含めた。「救急患者連携搬送料」が算定される連携搬送であり、制度上の「救急搬送後患者」に含まれる。

### 1-3. 病棟帰属

入院初日の病棟（`detail_df["ward"]`）で判定する設計。入院後に転棟があっても、入院イベント時点の病棟で計上する。

```python
# emergency_ratio.py L64-83
def _filter_admissions(detail_df, ward=None, year_month=None):
    df = detail_df[detail_df["event_type"] == "admission"].copy()
    if ward is not None:
        df = df[df["ward"] == ward]
    if year_month is not None:
        df["_ym"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")
        df = df[df["_ym"] == year_month]
        df = df.drop(columns=["_ym"])
    return df
```

## 2. コア計算ロジック

### 2-1. calculate_emergency_ratio()

```python
# emergency_ratio.py L146-198
def calculate_emergency_ratio(
    detail_df: pd.DataFrame,
    ward: Optional[str] = None,
    year_month: Optional[str] = None,
    exclude_short3: bool = False,
    target_date: Optional[date] = None,
) -> Dict[str, Any]:
```

主要ロジック:

1. `_filter_admissions()` で入院イベントを病棟・月でフィルタ
2. `exclude_short3=True` の場合、`_is_short3()` で短手3判定し分母から除外
3. `EMERGENCY_ROUTES` に含まれるrouteをカウントして分子とする
4. 割合・内訳・ステータスを含む dict を返す

返り値の構造:
```python
{
    "numerator": int,           # 分子（救急+下り搬送）
    "denominator": int,         # 分母（対象入院数）
    "ratio_pct": float,         # 割合（%）
    "gap_to_target_pt": float,  # 目標15%との差（pt）
    "status": str,              # "green" / "yellow" / "red"
    "exclude_short3": bool,
    "ward": str | None,
    "year_month": str,
    "breakdown": dict,          # 経路別内訳
}
```

ステータス判定（L119-125）:
- `ratio >= 17.0%` → `"green"`（2ptマージンあり）
- `ratio >= 15.0%` → `"yellow"`（基準ぎりぎり）
- `ratio < 15.0%` → `"red"`（未達）

### 2-2. calculate_dual_ratio()

```python
# emergency_ratio.py L206-221
def calculate_dual_ratio(detail_df, ward=None, year_month=None, target_date=None):
    ym = _resolve_year_month(year_month, target_date)
    return {
        "official": calculate_emergency_ratio(
            detail_df, ward=ward, year_month=ym, exclude_short3=False
        ),
        "operational": calculate_emergency_ratio(
            detail_df, ward=ward, year_month=ym, exclude_short3=True
        ),
    }
```

- `official`: 届出確認用（短手3を分母に含む）
- `operational`: 院内運用用（短手3を分母から除外）

### 2-3. project_month_end()

```python
# emergency_ratio.py L229-361
def project_month_end(detail_df, ward=None, year_month=None, target_date=None):
```

3シナリオの予測ロジック:

1. 過去14日間の曜日別入院パターン（曜日0-6ごとの救急件数平均・全入院件数平均）を算出
2. 残日数分の各曜日についてパターン値を積算
3. シナリオ係数を乗じて予測値を算出

```python
# emergency_ratio.py L34-38
SCENARIO_MULTIPLIERS: dict[str, float] = {
    "conservative": 0.7,   # 保守シナリオ
    "standard": 1.0,       # 標準シナリオ
    "optimistic": 1.3,     # 良好シナリオ
}
```

曜日パターン反映の仕組み（L316-327）:
```python
for scenario_name, multiplier in SCENARIO_MULTIPLIERS.items():
    proj_emg = float(current_emergency)
    proj_tot = float(current_total)
    d = next_day
    while d <= month_end:
        dow = d.weekday()
        proj_emg += dow_pattern.get(dow, 0.0) * multiplier
        proj_tot += dow_total_pattern.get(dow, 0.0) * multiplier
        d += timedelta(days=1)
```

### 2-4. calculate_additional_needed() — ChatGPTフィードバック対応済み

**修正前のバグ（過大推定）:**

旧ロジックでは、`additional_needed` を「目標救急件数 - 現在の救急件数」で算出していた。これは残り日数で自然に流入する救急件数を無視しており、必要件数を過大に見積もっていた。

**修正後のロジック:**

```python
# emergency_ratio.py L388-396
projected_total = projection["standard"]["projected_total"]
projected_emergency_standard = projection["standard"]["projected_emergency"]
target_emg = math.ceil(EMERGENCY_THRESHOLD_PCT / 100.0 * projected_total)

# PRIMARY: 標準シナリオの予測救急数を差し引いた追加必要数
needed = max(target_emg - projected_emergency_standard, 0)
# REFERENCE: 現在の実績のみから算出した追加必要数（自然流入を見込まない）
needed_from_actual = max(target_emg - current_emergency, 0)
```

2つの値の違い:
- `additional_needed`: 標準シナリオで自然に来ると予測される救急入院を差し引いた **真に追加で必要な件数**
- `additional_needed_from_actual`: 自然流入を見込まず、現在実績のみから算出した件数（参考値）

**不変条件**: `additional_needed <= additional_needed_from_actual`

これは常に成立する。なぜなら `projected_emergency_standard >= current_emergency`（標準シナリオの予測は現在実績に残り日数分の自然流入を加算したもの）のため。

難易度判定（L414-425）:
```python
if needed <= 0:
    difficulty = "achieved"
elif per_biz < 0.5:
    difficulty = "easy"
elif per_biz < 1.0:
    difficulty = "moderate"
elif per_biz < 1.5:
    difficulty = "difficult"
else:
    difficulty = "very_difficult"
```

### 2-5. generate_emergency_alerts()

4段階のアラートロジック（L449-548）:

| 条件 | レベル | タイトル |
|:---|:---|:---|
| 現在 < 15% かつ 標準予測未達 | `critical` | 未達見込み |
| 現在 < 15% かつ 標準予測達成 | `warning` | 現時点で未達 |
| 現在 15-17%（余裕薄） | `caution` | 余裕薄 |
| 現在 >= 17%（十分） | `safe` | 順調 |

両病棟ともcriticalの場合、全体アラート（「病院全体として緊急対策が必要」）を追加で生成する（L533-548）。

## 3. 既存バグ修正

### 3-1. guardrail_engine.py の分母バグ

**修正前（L258付近）:**
```python
# 旧: len(detail_df) で入退院全レコードをカウント（退院イベントも含む）
total_admissions = len(detail_df)
emergency_count = int(detail_df["route"].isin(["救急"]).sum())
```

**修正後（L259-263）:**
```python
# 新: 入院イベントのみをフィルタ
admissions_df = detail_df[detail_df["event_type"] == "admission"]
total_admissions = len(admissions_df)
# 救急・下り搬送の両方をカウント
emergency_count = int(admissions_df["route"].isin(["救急", "下り搬送"]).sum())
```

修正内容:
1. 分母を `detail_df` 全体 → `event_type == "admission"` のみにフィルタ（退院イベントが分母に含まれていた）
2. 分子に `"下り搬送"` を追加（`["救急"]` → `["救急", "下り搬送"]`）

## 4. C群コントロール連携

`generate_c_group_alerts()` に `emergency_ratio_risk` パラメータを追加（c_group_control.py L473-556）:

```python
def generate_c_group_alerts(
    c_summary: dict,
    c_capacity: dict,
    demand_classification: str | None = None,
    emergency_ratio_risk: dict | None = None,   # 新規追加
) -> list[dict]:
```

救急搬送後患者割合が `"red"`（15%未満）の病棟がある場合、C群キープとのトレードオフアラートを生成する（L539-555）:

```python
if emergency_ratio_risk is not None:
    for ward_name, ward_risk in emergency_ratio_risk.items():
        if isinstance(ward_risk, dict) and ward_risk.get("status") == "red":
            additional = ward_risk.get("additional_needed", 0)
            ratio_pct = ward_risk.get("ratio_pct", 0.0)
            alerts.append({
                "level": "warning",
                "category": "emergency_ratio",
                "message": (
                    f"{ward_name} の救急搬送後患者割合が {ratio_pct:.1f}%（目標15%）と低く、"
                    f"あと {additional} 件の救急入院が必要です。"
                    "C群の長期滞在がベッドを占有すると救急受入枠が減り、"
                    "割合改善が困難になります"
                    "（C群キープ↔救急受入のトレードオフに注意）"
                ),
            })
```

app.py側の連携（L8243-8269）で、C群アラート生成前に各病棟の救急搬送割合をチェックし、`emergency_ratio_risk` dict を構築して渡している。

## 5. UI実装

### 5-1. サブタブ構成

既存の3サブタブに4つ目「🚑 救急搬送15%」を追加（app.py L8005）:

```python
_gr_sub1, _gr_sub2, _gr_sub3, _gr_sub4 = st.tabs([
    "🛡️ 制度余力", "🌊 需要波", "📋 C群コントロール", "🚑 救急搬送15%"
])
```

サブタブ内は5セクションで構成（app.py L8286-8638）:

1. **今月の状況（5F / 6F）** — 届出確認用 / 院内運用用の2系統カード表示
2. **月末着地予測** — 3シナリオ（保守/標準/良好）の予測値
3. **15%達成に必要な追加件数** — additional_needed + 難易度判定
4. **危険域アラート** — critical/warning/cautionの階層表示
5. **推移グラフ** — 月内累積推移、過去12か月実績、入院経路構成比（3タブ）

### 5-2. 英語→日本語化

2回目のコミット（a7219d7）で以下11箇所の英語表記を日本語に置換:

- "WARNING" → アラートレベル表示を日本語化
- "LOS" → "平均在院日数"
- "additional_needed" のUI表示を「あと N 件必要」に
- "difficulty" の各レベルを「達成済み」「達成見込み」「やや厳しい」「厳しい」「非常に厳しい」に
- "meets_target" → 「達成」/「未達」
- "conservative"/"standard"/"optimistic" → 「保守」/「標準」/「良好」
- "per_remaining_calendar_day" → 「残り日数あたり」
- "per_remaining_business_day" → 「営業日あたり」
- "this_week_needed" → 「今週中に必要」
- 各アラートメッセージを日本語化
- グラフの軸ラベル・タイトルを日本語化

## 6. デモデータ

教育シナリオの設計意図: 2つの病棟で対照的な状況を作り、アラートの動作確認ができるようにした。

| 病棟 | 4月入院数 | 救急+下り搬送 | 割合 | 短手3 | 状態 |
|:---|:---|:---|:---|:---|:---|
| 5F | 22件 | 5件（救急4+下り搬送1） | 22.7% | 5件 | 安全圏（green） |
| 6F | 20件 | 1件（下り搬送1） | 5.0% | 2件 | 危険域（red） |

- 5F は22.7%で十分なマージンがあり、`safe` アラートが出る
- 6F は5.0%で大幅に未達、`critical` アラートが出る
- 下り搬送データ: 5Fに1件、6Fに1件（分子に含まれることの確認用）
- 短手3データ: 大腸ポリペクトミー5件、ヘルニア手術1件、ポリソムノグラフィー1件

## 7. テスト

全17テスト通過（`tests/test_emergency_ratio.py`, 579行）:

| # | テスト名 | 検証内容 |
|:---|:---|:---|
| 1 | `test_ward_separate_calculation` | 5F/6Fが別々に計算される（要件1） |
| 2 | `test_admission_day_ward_attribution` | 入院初日病棟で正しく計上される（要件2） |
| 3 | `test_downstream_included_in_numerator` | 下り搬送が分子に含まれる（要件3） |
| 4 | `test_short3_exclusion_mode` | 短手3除外モードで分母から除外される（要件4） |
| 5 | `test_additional_needed_calculation` | 必要件数の計算が正しい（要件5） |
| 6 | `test_additional_needed_zero_when_above_target` | 目標達成済みならadditional_needed=0（要件5補足） |
| 7 | `test_critical_alert_on_undershoot` | 未達見込み時にcriticalアラートが出る（要件6） |
| 8 | `test_one_ward_fail_not_masked_by_other` | 片方未達でも病院全体平均でごまかされない（要件7） |
| 9 | `test_ward_filtering_correct` | 病棟フィルタリングが正しく動作する（要件8） |
| 10 | `test_empty_dataframe_no_crash` | 空DataFrameでもクラッシュしない（要件9） |
| 11 | `test_missing_columns_no_crash` | routeカラム欠損時にKeyErrorが発生する（設計通り） |
| 12 | `test_unknown_route_no_crash` | 未知のrouteでもクラッシュせずotherに計上される |
| 13 | `test_dual_ratio_both_modes` | 公式/運用の分母が異なることの確認 |
| 14 | `test_monthly_history` | 3ヶ月分の月別データが正しく返る |
| 15 | `test_cumulative_progress` | 日別累積が単調非減少になる |
| 16 | `test_additional_needed_standard_projection_deduction` | 標準シナリオで自然達成時にadditional_needed=0 |
| 17 | `test_additional_needed_invariant_primary_le_reference` | additional_needed <= additional_needed_from_actual の不変条件 |

テスト実行結果: 17 passed in 0.04s

## 8. 検証してほしいポイント

1. **calculate_additional_needed()の修正は正しいか?**
   - `additional_needed = max(target_emg - projected_emergency_standard, 0)` のロジック
   - `projected_emergency_standard` は標準シナリオの月末予測救急件数（現在実績 + 残り日数の自然流入見込み）
   - `target_emg = ceil(0.15 * projected_total)` で月末総入院予測に対する必要件数を算出
   - 修正前は `max(target_emg - current_emergency, 0)` で自然流入を無視して過大推定していた

2. **project_month_end()の曜日パターン反映は妥当か?**
   - 直近14日間の曜日別平均を算出し、残り日数の各曜日に適用
   - シナリオ係数（0.7/1.0/1.3）を乗じる
   - 14日間という観測期間は十分か?

3. **分子に「救急」「下り搬送」を含めるのは制度上正しいか?**
   - 救急患者連携搬送料が算定される連携搬送は「救急搬送後の患者」に該当するか

4. **短手3除外の分母計算は正しいか?**
   - `_is_short3()` の判定: `short3_type` が `NaN`、空文字、`"該当なし"` 以外なら短手3とみなす
   - 除外は院内運用用（`exclude_short3=True`）のみで、届出確認用は除外しない

5. **guardrail_engine.pyの分母バグ修正で既存テストへの影響はないか?**
   - 分母を `len(detail_df)` → `len(admissions_df)` に変更
   - 分子に `"下り搬送"` を追加
   - 既存の `test_guardrail_engine.py` のテストデータにも修正が必要だったか

6. **C群連携のトレードオフアラートは運用上適切か?**
   - C群キープで稼働率を維持したいが、ベッドが埋まると救急受入枠が減る
   - 「C群キープ↔救急受入のトレードオフ」という概念は現場に伝わるか

7. **月末予測の3シナリオ係数（0.7/1.0/1.3）は妥当か?**
   - 保守0.7 = 直近14日の70%ペース
   - 標準1.0 = 直近14日と同ペース
   - 良好1.3 = 直近14日の130%ペース
   - 係数の幅は適切か（0.5-1.5など、より広い範囲が必要か）

## 実行確認

- テスト: `tests/test_emergency_ratio.py` 17件全通過（0.04s）
- ruff lint: エラーなし
- コミット:
  - `bb48fc7` feat: 救急搬送後患者割合15%管理機能（v3.3）
  - `a7219d7` fix: UI英語→日本語化、必要件数の過大推定修正、教育デモデータ追加
