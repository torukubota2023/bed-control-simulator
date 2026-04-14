# ベッドコントロールアプリ v4.0 設計書

## ビジョン

**精神論を、数字に変える。** — v3と同じ。
**ただし、数字だけを見せる。** — v4で加わる原則。

ベテランの主任・師長は数字を見れば判断できる。
アプリの仕事は「正しい数字を、正しい粒度で、1画面に並べる」こと。
指示的な表現（急ぎ退院必要、後ろ倒し可能 等）は不要。

## 設計原則

1. **1画面完結**: 毎日の判断に必要な数字は1画面（メインタブ）で完結する
2. **数字で語る**: 判定ラベルや推奨アクションではなく、数値と基準値の差を見せる
3. **詳細は別タブ**: 深掘りしたいときだけ詳細タブを開く
4. **計算ロジックは既存モジュール活用**: guardrail_engine, c_group_control, emergency_ratio 等はそのまま使う
5. **UIコードは最小限**: 9,000行 → 目標2,000行以下

## タブ構成

```
[📊 メイン] [🔍 詳細分析] [📋 制度確認] [📝 データ入力] [⚙ 設定]
```

### タブ1: メイン（毎日使う）

病棟セレクター: [全体] [5F] [6F]

#### 表示する5指標

| # | 指標 | 現在値 | 基準 | 差分 | データソース |
|---|------|--------|------|------|-------------|
| 1 | 稼働率 | 91.1% | 目標90% | +1.1% | daily_df → 当月平均 |
| 2 | 平均在院日数 | 21.3日 | 上限21日 | -0.3日 | rolling 90日 (calculate_rolling_los) |
| 3 | 救急搬送比率 | 19.6% | 基準15% | +4.6% | 当月累計 (calculate_emergency_ratio) |
| 4 | C群 | 12名 | — | LOS30日超 3名 | get_c_group_summary + generate_c_group_candidate_list |
| 5 | 週末稼働率 | -4.2% | — | 金曜退院集中 30.8% | get_discharge_weekday_stats |

#### レイアウトイメージ

```
┌─────────────────────────────────────────────────────┐
│ 📊 ベッドコントロール           [全体][5F][●6F]      │
├─────────────────────────────────────────────────────┤
│                                                     │
│  稼働率        91.1%   目標90%まで +1.1% ✅         │
│  平均在院日数   21.3日  上限21日   余力 -0.3日 ⚠️    │
│  救急搬送比率   19.6%   基準15%   余力 +4.6% ✅      │
│  C群滞留       12名    30日超 3名                   │
│  週末低下      -4.2%   金曜退院集中 30.8%            │
│                                                     │
│  ─── 稼働率1%の価値: 年間1,199万円 ───              │
│                                                     │
└─────────────────────────────────────────────────────┘
```

各指標は st.metric で表示。基準との差分を delta で見せる。
色分けは Streamlit の delta_color で自動（プラス=緑、マイナス=赤）。

### タブ2: 詳細分析（必要時に開く）

サブタブ構成:
- **C群候補一覧**: 在院日数の長い順の表。判定ラベルなし、数字のみ。
- **What-Ifシミュレーション**: 退院後ろ倒し/前倒しの影響
- **医師別分析**: 入退院パターン
- **週末分析**: 金曜退院偏り、週末空床コスト

### タブ3: 制度確認（月次レビュー）

月1回程度見る制度指標:
- 在宅復帰率
- 同一医療機関からの転棟割合
- 重症度・医療看護必要度
- ADL低下割合

表示形式: 各指標の現在値 vs 基準値の一覧表。シンプルに。

### タブ4: データ入力（毎日）

- 日次データ入力（入院数・退院数・在院患者数）
- 入退院詳細入力（個別イベント）
- CSVインポート/エクスポート
- パスワード認証あり

### タブ5: 設定

- HOPE連携メッセージ生成
- データエクスポート
- シナリオ保存・比較
- パラメータ設定（目標稼働率、LOS上限等）

## 実装方針

### 活用する既存モジュール（変更なし）

| モジュール | 使う関数 |
|-----------|---------|
| bed_data_manager.py | calculate_rolling_los, get_discharge_weekday_stats, CSV I/O, CRUD |
| guardrail_engine.py | calculate_guardrail_status, calculate_los_headroom |
| c_group_control.py | get_c_group_summary, calculate_c_adjustment_capacity, simulate_c_group_scenario |
| c_group_candidates.py | generate_c_group_candidate_list |
| emergency_ratio.py | calculate_emergency_ratio, calculate_additional_needed |
| demand_wave.py | calculate_demand_trend, classify_demand_period |
| bed_management_metrics.py | calculate_weekend_empty_metrics |
| hope_message_generator.py | render_hope_tab |
| doctor_master.py | 医師マスター管理 |
| scenario_manager.py | save/load/compare scenarios |
| db_manager.py | SQLite永続化 |

### 削除するもの

| 削除対象 | 理由 |
|---------|------|
| action_recommendation.py | 「今日の一手」は不要。数字だけで判断できる |
| views/dashboard_view.py | アクションカード表示。不要 |
| views/guardrail_view.py | 制度余力ダッシュボード。メインタブに統合 |
| views/c_group_view.py | C群候補表示。詳細タブに統合 |
| help_content.py の大半 | 大幅に簡素化 |

### 新ファイル構成

```
scripts/
├── bed_control_app_v4.py      ← 新メインアプリ（目標2,000行以下）
├── app_data_layer.py          ← session_state の一元管理（新規）
├── tabs/                      ← タブごとのUI（新規）
│   ├── __init__.py
│   ├── main_tab.py            ← メインタブ（5指標）
│   ├── detail_tab.py          ← 詳細分析タブ
│   ├── regulation_tab.py      ← 制度確認タブ
│   ├── data_input_tab.py      ← データ入力タブ
│   └── settings_tab.py        ← 設定タブ
├── bed_data_manager.py        ← 既存（変更なし）
├── guardrail_engine.py        ← 既存（変更なし）
├── c_group_control.py         ← 既存（変更なし）
├── c_group_candidates.py      ← 既存（変更なし）
├── emergency_ratio.py         ← 既存（変更なし）
├── demand_wave.py             ← 既存（変更なし）
├── bed_management_metrics.py  ← 既存（変更なし）
└── ... (他の既存モジュール)
```

### session_state の整理

現行: 34キー、6重複コピー
新: 最小限のキーセット

| キー | 内容 |
|------|------|
| daily_data | 日次データ DataFrame |
| daily_data_full | 全期間データ（rolling LOS用） |
| ward_data | {"5F": df, "6F": df} 病棟別データ |
| admission_details | 入退院詳細イベント |
| monthly_summary | 月次サマリー |
| data_authenticated | 認証済みフラグ |
| selected_ward | 選択病棟 |
| app_config | 目標稼働率・LOS上限等の設定値 |

## マイグレーション計画

### Phase 1: メインタブ実装
- bed_control_app_v4.py + tabs/main_tab.py を新規作成
- 5指標の表示を実装
- 既存の bed_control_simulator_app.py は残す（並行運用）

### Phase 2: データ入力タブ移植
- 既存のデータ入力UIを tabs/data_input_tab.py に移植
- CSV I/O、パスワード認証を含む

### Phase 3: 詳細分析・制度確認タブ移植
- C群候補一覧、What-If、医師別分析を移植
- 制度確認タブを新規作成

### Phase 4: 設定タブ・HOPE連携移植
- HOPE連携、シナリオ管理、エクスポートを移植

### Phase 5: 旧アプリ退役
- bed_control_simulator_app.py を削除
- views/ ディレクトリを削除
- テスト更新

## 現行 v3.5 との互換性

- 既存のデモCSVデータはそのまま使える
- 計算ロジック（モジュール群）は変更なし
- session_state のキー名変更によりブラウザキャッシュはリセットされる
- テストは新アプリに合わせて更新
