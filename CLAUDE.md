# CLAUDE.md - おもろまちメディカルセンター AI ワークスペース

## プロジェクト概要
おもろまちメディカルセンター（総病床数94床、月間入院数約150件）の臨床・教育・経営業務を支援するワークスペース。副院長・内科/呼吸器内科医としての実務をClaude Codeで効率化する。

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

## ベッドコントロールシミュレーター v3.0 進化（2026-04-04 設計確定・実装完了）
- **設計書:** [bed_control_evolution_design.md](docs/admin/bed_control_evolution_design.md)
- **理事向けプレゼン:** [bed_control_evolution_presentation.pptx](docs/admin/bed_control_evolution_presentation.pptx)
- **ビジョン:** 精神論を、数字に変える。
- **新モジュール:** `scripts/doctor_master.py`（医師マスター管理）、`scripts/hope_message_generator.py`（HOPE送信用サマリー生成）
- **新機能:**
  - 常時表示の基盤指標（稼働率1% = 年間約1,200万円、プリセット連動で自動再計算）
  - 「改善のヒント」自動検出（金額換算付き）
  - 医師別分析（入院創出医・担当医・フェーズ別貢献度）
  - 入退院詳細入力（経路・入院創出医・担当医・在院日数）
  - 医師マスター設定画面
  - 病棟別分析（5F/6F切替、病棟単位の改善のヒント）
  - HOPE送信用サマリー（ToDo一斉送信用メッセージ生成、400文字制限対応）
  - **過去3ヶ月rolling 平均在院日数（v3.1, 2026年改定対応）** — 本日の病床状況・意思決定ダッシュボード・HOPE送信サマリーに常時表示。**施設基準は各病棟ごとに判定**（病院全体ではなく5F・6Fそれぞれが満たす必要あり）。データ不足時は揃っている日数で計算。関数: `calculate_rolling_los()` in `bed_data_manager.py`
  - **制度ガードレール・需要波・C群コントロール（v3.2, 2026-04-11追加）**
    - 新規モジュール: `scripts/guardrail_engine.py`（制度ガードレールエンジン）、`scripts/demand_wave.py`（需要波モデル）、`scripts/c_group_control.py`（C群コントロール）
    - テスト: `tests/test_guardrail_engine.py`（10件）、`tests/test_demand_wave.py`（8件）、`tests/test_c_group_control.py`（10件）、全75テスト通過
    - app.pyに「制度・需要・C群」タブを追加（3サブタブ構成: 制度余力/需要波/C群コントロール）
    - 制度要件は2026年改定対応: 85歳以上患者割合に応じて平均在院日数上限が20〜24日に変動（固定値ではない）
    - 需要波: 前2週間 vs 直近1週間の入院トレンド比較で閑散/繁忙を自動判定
    - C群コントロール: LOS余力から逆算し、C群の退院タイミング調整で吸収できる空床数を可視化（C群運営貢献額28,900円/日）
    - 注意: C群は院内運用ラベルであり制度上の公式区分ではない。推計値はすべてproxy
  - **救急搬送後患者割合15%管理（v3.3, 2026-04-11追加）**
    - 新規モジュール: `scripts/emergency_ratio.py`（救急搬送後患者割合の計算・予測・アラート）
    - テスト: `tests/test_emergency_ratio.py`（15件）
    - 5F・6F別の単月管理、届出確認用/院内運用用（短手3除外）の2系統
    - official/operationalモード切替で全表示（現況・予測・アラート・グラフ）が完全連動
    - 月末着地予測（保守・標準・良好の3シナリオ）
    - 「あと何件必要か」の自動計算（残り必要件数＋残り営業日あたり必要件数の2値）、危険域での受入最優先モード提案
    - 下り搬送（救急患者連携搬送料算定）を分子に含む
    - C群コントロールとの連携: 救急搬送比率未達リスクをC群アラートに反映
    - 翌営業日朝の救急受入余力（`emergency_ratio.py`）: 退院予定・C群在院状況から空床予測
    - 経路別需要トレンド（`demand_wave.py`）: 救急・紹介・直接等の経路ごとにトレンド分解
    - 総合判定（overall_status）に「未完（データ不足）」状態を追加（安全/注意/危険/未完の4状態）
    - C群シナリオシミュレーションの収益影響にdelay_days（後ろ倒し日数）を反映
  - **サイドバーナビゲーション・パスワード認証・HOPE統合・仮説管理（v3.4, 2026-04-11追加）**
    - サイドバーセクション選択: 📊ダッシュボード / 🎯意思決定支援 / 🛡️制度管理 / 📋データ管理 / 📨HOPE連携
    - パスワード認証: アプリ起動時に認証（session_state管理）
    - HOPE送信アラート統合: generate_enhanced_summary_message()で制度/救急/C群アラートを400文字メッセージに統合
    - 新規モジュール: `scripts/scenario_manager.py`（改善仮説の保存・比較・AI分析）
    - テスト: `tests/test_hope_message.py`（8件）、`tests/test_scenario_manager.py`（10件）、全118テスト通過
    - 改善仮説の第2層: What-Ifシナリオの名前付き保存、複数シナリオ比較、ルールベースAI分析（稼働率最適化・LOS準拠・収益ランキング・実行容易性）
    - データエクスポート: 病棟日次データ・入退院詳細（CSV）、シナリオデータ（JSON）
  - **結論カード・KPI優先表示・views分離（v3.5, 2026-04-12追加）**
    - 新規モジュール: `scripts/action_recommendation.py`（優先アクション推薦、pure function）、`scripts/c_group_candidates.py`（C群候補一覧・トレードオフ評価、pure function）
    - 表示ロジック分離: `scripts/views/dashboard_view.py`、`scripts/views/c_group_view.py`（app.pyからの段階的分離）
    - テスト: `tests/test_action_recommendation.py`（14件）、`tests/test_c_group_candidates.py`（10件）、全167テスト通過
    - 結論カード（今日の一手）: ダッシュボード最上部に優先アクション推薦カードを表示。制度・稼働率・受入余力・C群を横断評価し、最も重要な1手を提示
    - KPI優先表示: 救急搬送比率 → 稼働率 → 翌朝受入余力 → LOS → C群の優先順でKPIを並べ替え
    - 翌営業日朝受入余力の主役化: 翌朝の空床予測をメインKPIに昇格、色分けステータス表示（安全/注意/危険）
    - C群候補一覧（lite版）: C群退院調整候補を患者レベルで一覧表示（C群は院内運用ラベルであり制度上の公式区分ではない）
    - C群/制度/受入余力トレードオフ評価: C群の延長（稼働率下支え） vs 退院（空床確保）のトレードオフを制度余力・受入余力と合わせて可視化
- **将来構想（未実装）:**
  - **短期滞在手術等基本料3（短手3）の組み込み** — [リサーチ・設計案](docs/admin/short3_integration_research.md)
    - A群期間（1-5日）と短手3期間（5日以内）が完全一致する点を活用し、A群の内数として管理
    - 入力は「うち短手3」1項目追加のみ（+5秒/日）
    - 平均在院日数計算から自動除外、運営貢献額は包括点数で別計算
    - 段階的導入（Phase 1: 入力のみ → Phase 2: 計算分岐 → Phase 3: 収益精緻化）
  - **短手3の戦略的増加（消化器内科との協議が前提）**
    - 現状: 月22件（ポリペク80%、ヘルニア・ポリソムノ20%）、平均2日入院
    - 短手3の特性: LOS計算除外＋稼働率に退院カウント＋夜勤負担最小 → 「三方よし」
    - 月8件増（22→30件）で年間約1,700万円改善（短手3収益1,200万＋稼働率寄与480万）
    - ポリペク枠の週1コマ追加が最も現実的（大腸がん検診の要精検需要は地域に豊富）
    - 夜勤安全ラインとの統合: 通常5組＋短手3を2組 = 平日7組達成（現場の退院調整負担軽減）
  - ~~第2層: 改善仮説の保存・比較~~ → **v3.4で実装済み**（シナリオ保存・比較・AI分析）
  - 第3層: 提案書ドラフト自動生成（経営会議向け）
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
│   ├── admin/         ← 経営・管理文書
│   └── pubmed/        ← 文献検索結果
├── data/              ← KPI・入院統計・分析用データ
├── templates/         ← 診療情報提供書・退院サマリーのテンプレート
└── scripts/           ← 自動化スクリプト
    ├── views/         ← 表示ロジック（dashboard_view.py, c_group_view.py）
    └── hooks/         ← セキュリティHooksスクリプト
```

## ルール
詳細は `.claude/rules/` を参照：
- [clinical-safety.md](.claude/rules/clinical-safety.md): 患者情報保護・文献引用ルール
- [output-format.md](.claude/rules/output-format.md): 日本語出力・エビデンス併記ルール
- [orchestrator.md](.claude/rules/orchestrator.md): subagent委託・PDCA構築ルール
- [app-quality-assurance.md](.claude/rules/app-quality-assurance.md): アプリ品質保証ルール（単一ソース・連動更新・スコープ安全性・全状態テスト・同一パターン横展開）

## カスタムコマンド
- `/qa [ファイルパス]`: アプリ品質保証3層チェック（数値一貫性・スコープ安全性・ドキュメント整合性）
- `/pico-search`: 臨床疑問 → PubMed文献検索

## 運用ルール（必ず守ること）
- **アプリ修正時の品質保証:** [app-quality-assurance.md](.claude/rules/app-quality-assurance.md) に従い、連動更新・スコープ安全性・全状態テストを実施する。リリース前は `/qa` コマンドで最終確認を行う
