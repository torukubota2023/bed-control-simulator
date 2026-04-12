# ChatGPT Pro 用: 修正報告書 & 検証依頼（2026-04-12）

以下のプロンプトをChatGPT Proに貼り付けて使用してください。
Claude Codeが実施した修正内容を報告し、GitHubリポジトリを直接確認して検証を依頼します。

---

## プロンプト（ここから下をコピー）

```
あなたは病院業務支援アプリの品質監査者です。
Claude Codeが本日実施した修正内容を確認し、修正が正しく行われたかを検証してください。

## リポジトリ
https://github.com/torukubota2023/bed-control-simulator

## 最新コミット
コミットメッセージ: "feat: 制度余力タブのLOS全期間データ化 & 結論カードに他病棟協力表示を追加"

---

## 修正1: 制度余力タブ・C群コントロールのLOSデータソース修正

### 問題の経緯
- 制度余力タブ（🛡️ 制度・需要・C群 → 制度余力）とC群コントロールパネルで使われるLOS（平均在院日数）が、`_daily_df`（当月データのみ、約12日分）から計算されていた
- rolling 90日平均在院日数は90日分のデータが必要だが、当月分しか使っていなかったため、ダッシュボードの結論カード（全期間データ使用）と制度余力タブで数値が異なっていた
- ダッシュボードでは5F: 17.7日、6F: 21.3日と正しく表示されるが、制度余力タブでは不正確な値が表示されていた

### 修正内容
**ファイル:** `scripts/bed_control_simulator_app.py`
- `_gr_daily_df_full` 変数を新設。`st.session_state["actual_df_raw_full"]`（全期間データ）を参照
- 制度余力サブタブの `calculate_los_headroom()` 呼び出しを `_gr_daily_df` → `_gr_daily_df_full` に変更
- C群コントロールの `calculate_los_headroom()` と `calculate_rolling_los()` も同様に変更
- 非LOS計算（`calculate_guardrail_status`, `get_c_group_summary`, `calculate_demand_trend` 等）は当月データのまま変更なし

### 検証ポイント
1. `_gr_daily_df_full` が `st.session_state.get("actual_df_raw_full")` から取得されているか
2. フォールバック（全期間データがない場合）が `_gr_daily_df`（当月データ）になっているか
3. `calculate_los_headroom()` と `calculate_rolling_los()` の呼び出し箇所（制度余力・C群コントロール）がすべて `_gr_daily_df_full` を使っているか
4. 病棟別LOS余力（5F/6F個別表示）は以前の修正で `sim_ward_raw_dfs_full` / `ward_raw_dfs_full` を使用済み — これが変更されていないこと
5. 非LOS計算が `_gr_daily_df`（当月データ）のままであること

---

## 修正2: 結論カードに他病棟協力表示を追加

### 問題の経緯
- 結論カード（今日の一手）は `generate_action_card()` で生成され、`overall_status`（全病棟の最悪値）で判定を行う
- 例えば6Fの救急搬送比率が危険域のとき、5Fを選択しても「救急搬送比率が危険域」と表示される
- しかし、これが「自分の病棟（5F）の問題なのか、他の病棟（6F）の問題なのか」が区別できなかった
- 副院長の設計意図: 「どの病棟を選択しても問題のある病棟は表示して、協力する意識に働きかける。ただし、他の病棟の問題であることがわかるように表示する」

### 修正内容

**ファイル1:** `scripts/action_recommendation.py`
- `_collect_cross_ward_alerts()` 関数を新設
  - `selected_ward` と異なる病棟の `emergency_summary` を走査
  - 救急搬送比率が `red` または `additional_needed > 0` → `critical` レベルのアラート
  - 救急搬送比率が `yellow` → `warning` レベルのアラート
  - 返り値: `[{"ward": "6F", "type": "emergency_ratio", "level": "critical", "message": "..."}]`
- `generate_action_card()` 内の `_finalize()` ヘルパーで、`selected_ward` 指定時に `cross_ward_alerts` キーをカードに追加

**ファイル2:** `scripts/views/dashboard_view.py`
- `render_action_card()` に他病棟協力セクションを追加
  - `cross_ward_alerts` が空でない場合、`st.expander("🤝 他病棟の状況（協力体制）", expanded=True)` で表示
  - critical → `st.error`（赤）、warning → `st.warning`（黄）で視覚的に区別
  - キャプション: 「自病棟の問題でなくても、病院全体の施設基準達成に協力が必要です」

**ファイル3:** `tests/test_consistency.py`
- `test_card_level_reflects_overall_risk`: 6F危険 + 5F選択時に `cross_ward_alerts` が存在することを検証するアサーション追加
- `test_cross_ward_alerts_empty_when_no_other_ward_problem`: 他病棟に問題がないとき `cross_ward_alerts` が空であることを検証する新テスト追加

### 検証ポイント
1. `_collect_cross_ward_alerts()` が `selected_ward` と異なる病棟のみを走査しているか
2. operational（短手3除外）モードを優先し、なければofficialを使う設計が `_check_emergency_risk()` と一貫しているか
3. `generate_action_card()` の主判定ロジック（`overall_status` ベース）は変更されていないか — 「今日の一手」の結論自体は従来通り病院全体の最悪値で判定
4. `cross_ward_alerts` は `selected_ward` 指定時のみ付与され、全体表示時には付与されないか
5. `render_action_card()` で、メインの結論カードの後にセクションが追加されていること（結論カード自体の表示は変更なし）

---

## 全体検証

### テスト結果
- 全208テスト通過（新規2件追加含む）
- smoke test 全項目パス
- rolling LOS: 5F=17.7日、6F=21.3日（変更なし）

### 以前の修正との整合性確認
以下の以前の修正が壊れていないか確認してください:

1. **ダッシュボード結論カード** — `_ac_daily_df_full` を使ったLOS計算（変更なし）
2. **ダッシュボード翌朝受入余力** — `_ac_overall_df` による全体データ使用（変更なし）
3. **病棟別LOS余力表示** — `guardrail_view.py` の5F/6F並列表示、マイナス値の赤色表示（変更なし）
4. **KPI救急搬送比率のモード表示** — 「院内運用用」/「届出確認用」ラベル（変更なし）
5. **結論カードの病棟スコープ表示** — 「対象: ○○病棟」/「対象: 病院全体」（変更なし）

### 未解決の設計課題（参考情報）
- 結論カードの主判定は `overall_status` ベース。将来的に病棟選択時は「自病棟の状態を主結論にし、他病棟は補足情報」とする設計に進化する可能性がある
- 現状は「全体の最悪値で判定 + 他病棟の問題を別セクションで明示」というハイブリッド方式

## 対象ファイル一覧

### 今回の変更ファイル
- `scripts/bed_control_simulator_app.py` — 制度余力タブのデータソース修正
- `scripts/action_recommendation.py` — cross_ward_alerts 機能追加
- `scripts/views/dashboard_view.py` — 他病棟協力表示の描画
- `tests/test_consistency.py` — テスト2件追加

### 参照すべき関連ファイル
- `scripts/emergency_ratio.py` — `get_ward_emergency_summary()`, `estimate_next_morning_capacity()`
- `scripts/guardrail_engine.py` — `calculate_los_headroom()`, `calculate_los_limit()`
- `scripts/bed_data_manager.py` — `calculate_rolling_los()`
- `scripts/views/guardrail_view.py` — 制度余力の描画
- `docs/admin/demo_scenario_v3.5.md` — デモシナリオ台本

### デモデータ
- `data/sample_actual_data_ward_202604.csv`
- `data/admission_details.csv`

## 出力フォーマット

以下の形式で報告してください:

### ✅ 修正確認済み
| # | 修正項目 | 確認結果 | 備考 |
|---|---------|---------|------|

### 🔴 問題あり（修正が不完全・不正確）
| # | 箇所 | 問題の詳細 | 修正案 |
|---|------|----------|--------|

### 🟡 設計上の懸念
| # | 箇所 | 懸念事項 | 推奨 |
|---|------|---------|------|

### 🟢 追加改善提案
| # | 箇所 | 提案内容 | 理由 |
|---|------|---------|------|

### 📊 整合性サマリー
- 修正1（LOSデータソース）: ✅/❌
- 修正2（他病棟協力表示）: ✅/❌
- 既存機能への影響: なし/あり
- テストカバレッジ: 十分/不足
```

---

## 使い方

1. 上記の ``` で囲まれた部分をコピー
2. ChatGPT Pro に貼り付け
3. ChatGPT Pro がGitHubリポジトリにアクセスして修正内容を検証
4. 問題が見つかった場合はClaude Codeに戻して修正を指示
