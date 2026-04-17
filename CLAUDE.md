# CLAUDE.md - おもろまちメディカルセンター AI ワークスペース

## プロジェクト概要
おもろまちメディカルセンター（総病床数94床、月間入院数約150件）の臨床・教育・経営業務を支援するワークスペース。副院長・内科/呼吸器内科医としての実務をClaude Codeで効率化する。

## 🟡 事務確認待ちの課題（次回セッションで確認結果を聞く）

（現在、事務確認待ちの新規課題はありません）

## 📐 制度ルール確定事項（2026-06-01 以降の地域包括医療病棟運用）

**確定日:** 2026-04-15（事務担当者からの仕様確定を受領）

### 経過措置終了
- 令和6改定の経過措置（最大3ヶ月の困難時期除外）は **2026-05-31 で終了**
- **2026-06-01 以降は本則完全適用**

### 救急搬送後患者割合15% の計算ルール（6/1 以降）
- **判定期間:** rolling **3ヶ月**（単月ではない）
- **病棟別:** 5F / 6F 各病棟単体で判定
- **分母における短手3:** **常に含む**（最初からカウント、除外しない）

### 平均在院日数 の計算ルール（6/1 以降）
- **短手3患者の特殊扱い（階段関数）:**
  - **5日目まで** → 在院日数の分母に **含めない**
  - **6日目以降に滞在が延びた瞬間** → **入院初日まで遡って全日数を分母にカウント**
- → ベッドコントロール上、Day 5 と Day 6 の境界で LOS 分母が +6日 jump する不連続点が発生

### v3/v4 への先回り実装済み（2026-04-15）
- `scripts/emergency_ratio.py` に `TRANSITIONAL_END_DATE = 2026-05-31` / `days_until_transitional_end()` / `is_transitional_period()` を追加
- v3 (`bed_control_simulator_app.py`) と v4 (`bed_control_app_v4.py`) の両サイドバーに残日数バナーを実装（4段階：info/warning/error/終了後）
- テスト 7 件追加、全 39 件パス

### 本格実装の残タスク（2026-04-17 全完了）
1. [x] **`calculate_emergency_ratio()` の rolling 3ヶ月化** — `is_transitional_period()` ゲートで 2026-06-01 以降のみ適用に切替（commit `0347739`）
2. [x] **LOS 計算の短手3階段関数対応** — `calculate_rolling_los(today=None)` に拡張、Day 5/6 境界の不連続点を実装（commit `0347739`）
3. [x] **シミュレーター上の警告:** 短手3患者 Day 5 到達アラート — `get_short3_day5_patients()` 本実装 + UI 有効化（2026-04-17, `scripts/bed_data_manager.py:955`, `scripts/bed_control_simulator_app.py:2910-2929`）
4. [x] **リグレッション確認:** `emergency_ratio.py` の `exclude_short3` コメント更新済。全 267 テスト + smoke test 通過確認済

### リサーチ出典
- [GemMed 地域包括医療病棟 施設基準・要件詳細](https://gemmed.ghc-j.com/?p=59593)
- [しろぼんねっとQ&A](https://shirobon.net/qabbs_detail.php?bbs_id=59150)
- [令和8年改定 通則5（PT-OT-ST.NET）](https://www.pt-ot-st.net/contents4/medical-treatment-reiwa-8/department/4941)
- [A304 地域包括医療病棟入院料（PT-OT-ST.NET）](https://www.pt-ot-st.net/contents4/medical-treatment-reiwa-6/department/2842)

## ✅ 解決済みの課題
- [x] 週末空床コスト What-If の論理修正 — 「前倒し人数 × 充填確率」の2スライダー方式に修正済み（2026-04-11）

## 今週の臨床疑問
- [x] ヘルペス脳炎後1ヶ月の非細菌性両下肢蜂窩織炎様所見 + 好酸球1500 → Wells症候群 vs DRESS（[検索結果](docs/pubmed/2026-03-19_eosinophilic_cellulitis_post_herpes_encephalitis.md)）
- [x] ポストコロナ時代の病院内ユニバーサルマスキング継続の是非 → リスク層別化・流行期連動型アプローチが主流（[検索結果](docs/pubmed/2026-03-20_hospital_universal_masking_post_COVID.md)）

## MCP接続
- PubMed: 文献検索・メタデータ取得・フルテキスト取得
  - 検索結果は必ずPMID・DOIを記録する
  - 臨床疑問はPICO形式で検索する

## 認知機能検査トレーニングアプリ（2026-04-02 新規作成）
- **デプロイ済み:** https://cognitive-test-trainer.streamlit.app
- ファイル: `scripts/cognitive_test_trainer.py`, `scripts/cognitive_help_content.py`
- 機能: テスト本番モード / 毎日5分トレーニング / 学習記録
- 4パターン×16イラスト（公式検査準拠）、公式採点方式
- 文字サイズ3段階切替（標準・大きめ・特大）
- iPad対応レスポンシブレイアウト

## ベッドコントロールシミュレーター（現行 v3.5）
- **設計書:** [bed_control_evolution_design.md](docs/admin/bed_control_evolution_design.md)
- **ビジョン:** 精神論を、数字に変える。
- **現行バージョン:** v3.5i（2026-04-17時点、全 267 Python テスト + 7 Playwright E2E testid テスト通過）
- **注意:** 以下の機能はすべて**実装済み**。再実装・再検討の必要はない。

### 実装済み機能一覧（変更不要 — 参照用）
| バージョン | 機能 | 主要モジュール |
|-----------|------|---------------|
| v3.0 | 基盤指標・改善のヒント・医師別分析・入退院詳細入力・HOPE送信 | `doctor_master.py`, `hope_message_generator.py` |
| v3.1 | rolling 90日平均在院日数（病棟別判定） | `bed_data_manager.py` → `calculate_rolling_los()` |
| v3.2 | 施設基準チェック・需要波・C群コントロール | `guardrail_engine.py`, `demand_wave.py`, `c_group_control.py` |
| v3.3 | 救急搬送後患者割合15%管理（official/operational 2系統） | `emergency_ratio.py` |
| v3.4 | サイドバー5セクション・パスワード認証・HOPE統合・シナリオ保存比較・CSVエクスポート | `scenario_manager.py` |
| v3.5 | 結論カード（今日の一手）・KPI優先表示・views分離・他病棟協力表示 | `action_recommendation.py`, `views/` |
| v3.5h | 院内LAN展開準備（Edge 90対応・ポータブルブラウザ方針） | `tools/browser_probe.html`, `deploy/` |
| v3.5i | 2026-06-01 本則適用準備（救急 rolling 3ヶ月・LOS 階段関数・短手3 Day 5 アラート）・Playwright E2E Green 化（7 testid） | `emergency_ratio.py`, `bed_data_manager.py → get_short3_day5_patients()`, `playwright/test_app.spec.ts` |

### 設計上の重要ルール（コード修正時に参照）
- C群は**院内運用ラベル**であり制度上の公式区分ではない。推計値はすべてproxy
- 施設基準は**各病棟ごとに判定**（病院全体ではなく5F・6Fそれぞれ）
- LOS計算は**全期間データ**（`actual_df_raw_full`）を使用。当月データ（`_daily_df`）は非LOS計算用
- 結論カードは`overall_status`ベースで判定し、`cross_ward_alerts`で他病棟の問題を補足表示

### 将来構想（未実装 — 指示があれば着手）
- 短手3の組み込み — [設計案](docs/admin/short3_integration_research.md)
- 短手3の戦略的増加（消化器内科との協議が前提）
- 提案書ドラフト自動生成（経営会議向け）
- 立場別ビュー（医師・看護師・経営者）

## 教育資料ドラフト
- 次回レジデント勉強会テーマ：未定
- 作成中の資料：

## 経営メモ
- 地域包括医療病棟 稼働状況：稼働率90%目標、在院日数19日前後が最適ゾーン
- 月間入院数トレンド：約150件/月
- 2026年度改定戦略：[統一戦略ドキュメント](docs/admin/2026_nursing_necessity_unified_strategy.md)
  - 6F（内科・ペイン）のギャップ6.8%克服が最大課題
  - 5F（外科・整形）はあと1.8%で到達可能

## よく使うコマンド・ワークフロー
- 文献検索 → PubMed MCP で最新エビデンスを取得し、結果を/docs/pubmed 以下に .md → .docx or .pdf で出力
- 教育資料作成 → /docs 以下に .md → .docx or .pdf で出力
- KPI分析 → /data 以下のデータを集計・可視化
- E2E テスト（Playwright + Claude 評価）→ `npm run test:e2e` / `npm run test:e2e:headed`（ブラウザ表示あり）/ `npm run test:e2e:report`（HTMLレポート）
  - 初回セットアップと詳細手順は [docs/admin/bed_control_e2e_manual.md](docs/admin/bed_control_e2e_manual.md) を参照

## フォルダ構成
```
/
├── CLAUDE.md          ← このファイル（プロジェクトメモリ）
├── .claude/           ← Claude Code設定
│   ├── commands/      ← カスタムコマンド
│   ├── rules/         ← ルール集（臨床安全性・出力形式・オーケストレーター）
│   └── settings.json  ← Hooks・共有設定
├── docs/              ← 教育資料・マニュアル・ガイド
│   ├── respiratory/   ← 呼吸器フィジカル関連
│   ├── education/     ← レジデント教育資料
│   ├── admin/         ← 経営・管理文書（bed_control_e2e_manual.md 等）
│   └── pubmed/        ← 文献検索結果
├── data/              ← KPI・入院統計・分析用データ
├── templates/         ← 診療情報提供書・退院サマリーのテンプレート
├── scripts/           ← 自動化スクリプト
│   ├── views/         ← 表示ロジック（dashboard_view.py, c_group_view.py, guardrail_view.py）
│   └── hooks/         ← セキュリティHooksスクリプト
├── tools/             ← ブラウザ互換性チェック（browser_probe.html）
├── deploy/            ← 院内LAN起動スクリプト（bat, ps1）
├── tests/             ← Python ユニット/統合テスト（pytest）
├── playwright/        ← E2E テスト（TypeScript）
│   ├── test_app.spec.ts     ← 正準テスト（3ケース + 追加6観点）
│   ├── test_audit.spec.ts   ← 包括的監査テスト
│   └── tests/
│       └── scenarios.json   ← 9 シナリオ定義（正常/境界/安全性）
└── utils/             ← E2E 共通ヘルパー（TypeScript）
    ├── claude_eval.ts       ← Claude による運用妥当性評価
    ├── extract_data.ts      ← KPI 抽出
    └── streamlit_helpers.ts ← Streamlit DOM 待機
```

## ルール
詳細は `.claude/rules/` を参照：
- [clinical-safety.md](.claude/rules/clinical-safety.md): 患者情報保護・文献引用ルール
- [output-format.md](.claude/rules/output-format.md): 日本語出力・エビデンス併記ルール
- [orchestrator.md](.claude/rules/orchestrator.md): subagent委託・PDCA構築ルール
- [app-quality-assurance.md](.claude/rules/app-quality-assurance.md): Claude Code 常駐用の短い品質保証ルール
- [bed_control_app_quality_assurance.md](docs/admin/bed_control_app_quality_assurance.md): ベッドコントロールアプリの詳細QA運用ルール

## カスタムコマンド
- `/qa [ファイルパス]`: アプリ品質保証3層チェック（数値一貫性・スコープ安全性・ドキュメント整合性）
- `/pico-search`: 臨床疑問 → PubMed文献検索

## 運用ルール（必ず守ること）
- **アプリ修正時の品質保証:** [app-quality-assurance.md](.claude/rules/app-quality-assurance.md) の固定ルールに従い、詳細手順は [bed_control_app_quality_assurance.md](docs/admin/bed_control_app_quality_assurance.md) を参照する。リリース前は `/qa` コマンドで最終確認を行う
- **Claude Code でのベッドコントロール開発:** 実装は `scripts/` と `tests/` を優先し、可変の運用メモや教訓は [bed_control_claude_code_workflow.md](docs/admin/bed_control_claude_code_workflow.md) と [bed_control_app_quality_assurance.md](docs/admin/bed_control_app_quality_assurance.md) に集約する。`.claude` は固定ルールとコマンド定義を中心に保つ
