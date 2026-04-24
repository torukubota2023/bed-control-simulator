# 病棟稼働率シミュレーター v3.5j

**空床時間マネジメント** で病床経営を改善する Streamlit アプリ

[![Tests](https://github.com/torukubota2023/bed-control-simulator/actions/workflows/test.yml/badge.svg)](https://github.com/torukubota2023/bed-control-simulator/actions/workflows/test.yml)
[![E2E + Quality Assurance](https://github.com/torukubota2023/bed-control-simulator/actions/workflows/e2e.yml/badge.svg)](https://github.com/torukubota2023/bed-control-simulator/actions/workflows/e2e.yml)

## 現在の開発ステータス

- **主開発環境**: Claude Code
- **Codex の役割**: GitHub Actions / CI / E2E / ドキュメント整合性の補助
- **現行PR**: [PR #17: fix CI compatibility](https://github.com/torukubota2023/bed-control-simulator/pull/17)
- **CI 方針**: 通常CIは Python tests + smoke test + 正準 Playwright E2E を必須化。重い監査E2Eは手動または週次運用で実行する。

## このアプリが解く課題

94床・月間入院150件の地域包括医療病棟で、**不要な空床時間を減らし、稼働率90〜95%を維持する**ためのツールです。

### 価値の中心は「入院予測」ではなく「空床時間の短縮」

- 当院の入院の約8割は救急・予定外 — 誰がいつ入院するかは予測できない
- だからこそ重要なのは、**退院側を整えて、いつ入院が来ても受けられる状態を作ること**
- 目標は空床ゼロではない。5〜10%の余白は救急受入のために必要
- 減らすべきは **夜またぎ空床・週末またぎ空床** という不要な空白時間

## 対象ユーザー

- 病院経営層（理事長・院長・副院長）
- 病棟管理者（看護師長）
- ベッドコントロールに関わるスタッフ

## 主な機能

| 機能 | 概要 |
|------|------|
| **本日の病床状況** | 稼働率ゲージ・空床数・4パターン自動判定を一画面で |
| **日次推移** | 20日間の稼働率推移、週末の谷パターンを可視化 |
| **運営分析** | 稼働率ギャップ、目標との差額、月末予測 |
| **フェーズ構成** | A群(急性期)/B群(回復期)/C群(退院準備期)の理想比率 |
| **What-if分析** | 退院前倒し × 充填確率で週末空床の改善効果を試算 |
| **改善のヒント** | 週末空床コスト、金曜退院集中、空床マネジメント指標を自動検出 |
| **夜勤安全ライン** | 夜勤帯の在院数を守りながら稼働率を上げるシミュレーション |
| **病棟別分析** | 5F/6Fの課題の違いを可視化、均等努力方式 |
| **平均在院日数(rolling)** | 過去90日の病棟別LOS、2026年改定の施設基準判定 |
| **施設基準チェック** | LOS余力・救急搬送割合を自動計算、制度逸脱リスクを信号表示 |
| **需要波** | 前2週vs直近1週の入院トレンド比較、閑散/繁忙の自動判定 |
| **C群コントロール** | 制度余力の中でC群による稼働率下支え効果を可視化 |
| **救急搬送後患者割合** | 15%基準の rolling 3ヶ月管理、病棟別判定、未達アラート |
| **サイドバーナビゲーション** | 今日の運営 / What-if・戦略 / 制度管理 / 退院調整 / データ・設定 の5セクションに整理 |
| **パスワード認証** | アプリ起動時にパスワード認証（session_state管理） |
| **改善仮説の保存・比較** | What-Ifシナリオの名前付き保存、複数比較、ルールベースAI分析 |
| **データエクスポート** | 病棟日次データ・入退院詳細（CSV）、シナリオデータ（JSON） |
| **結論カード（今日の一手）** | 制度・稼働率・受入余力・C群を横断評価し、優先アクションを1枚のカードで提示 |
| **KPI優先表示** | 救急搬送比率 → 稼働率 → 翌朝受入余力 → LOS → C群の優先順で表示 |
| **翌診療日朝受入余力** | 翌朝の空床予測をメインKPIに昇格、色分けステータス表示 |
| **C群候補一覧（lite版）** | C群退院調整候補を患者レベルで一覧表示（院内運用ラベル） |
| **C群/制度/受入余力トレードオフ評価** | C群の延長 vs 退院のトレードオフを制度余力・受入余力と合わせて評価 |

## 起動方法

```bash
# ローカル起動（Python 3.11 推奨）
pip install -r requirements.txt
streamlit run scripts/bed_control_simulator_app.py

# 院内LAN公開（サーバーPC）
streamlit run scripts/bed_control_simulator_app.py --server.address 0.0.0.0 --server.port 8501

# デプロイ版（Streamlit Cloud）
# https://bed-control-simulator.streamlit.app
```

## 院内LAN展開

院内LANへの展開手順は以下を参照してください。

- **設置手順**: [lan_setup_guide.md](docs/admin/lan_setup_guide.md)
- **展開計画**: [intranet_deployment_plan.md](docs/admin/intranet_deployment_plan.md)
- **ブラウザ互換性**: [intranet_browser_compatibility_plan.md](docs/admin/intranet_browser_compatibility_plan.md)
- **ポータブルブラウザ**: [portable_browser_operation_guide.md](docs/admin/portable_browser_operation_guide.md)

> ⚠️ 院内端末の Edge 90 では Streamlit が正常動作しない可能性があります。
> 詳細は [ブラウザ検証マトリクス](docs/admin/browser_validation_matrix.md) を参照してください。

## データの前提

- **病床数**: 5F(47床) + 6F(47床) = 94床
- **入院料**: 地域包括医療病棟入院料1（2026年改定対応）
- **稼働率計算**: 厚労省定義 `(在院患者数 + 退院患者数) / 病床数`
- **デモモード**: サンプルデータで全機能を体験可能

## 注意点

- 稼働率・平均在院日数は**厚労省の公式定義**に準拠しています
- 「受入見込み」の数値は参考値であり、入院を正確に予測するものではありません
- 個人情報は一切含みません（匿名化された統計データのみ使用）

## プロジェクト構成

```
scripts/
  bed_control_simulator_app.py   # Streamlit UI（メイン）
  bed_control_simulator.py       # シミュレーション計算エンジン
  bed_management_metrics.py      # 空床マネジメント指標（pure function）
  bed_data_manager.py            # データ管理・指標計算
  db_manager.py                  # SQLite 永続化
  help_content.py                # ヘルプテキスト
  doctor_master.py               # 医師マスター管理
  hope_message_generator.py      # HOPE連携メッセージ
  guardrail_engine.py            # 施設基準チェックエンジン
  demand_wave.py                 # 需要波モデル
  c_group_control.py             # C群コントロール
  emergency_ratio.py             # 救急搬送後患者割合
  scenario_manager.py            # シナリオ保存・比較・AI分析
  action_recommendation.py       # 結論カード・優先アクション推薦（pure function）
  c_group_candidates.py          # C群候補一覧・トレードオフ評価（pure function）
  views/                         # 表示ロジック分離
    dashboard_view.py            # ダッシュボード表示（結論カード・KPI・翌朝余力）
    c_group_view.py              # C群候補一覧表示
    guardrail_view.py            # 施設基準チェック・需要波表示
tests/
  test_bed_data_manager.py       # データ管理のテスト（18件）
  test_db_manager.py             # SQLite永続化のテスト（8件）
  test_metrics.py                # 空床マネジメント指標のテスト（21件）
  test_guardrail_engine.py       # 施設基準チェックのテスト（11件）
  test_demand_wave.py            # 需要波のテスト（11件）
  test_c_group_control.py        # C群コントロールのテスト（10件）
  test_emergency_ratio.py        # 救急搬送後患者割合のテスト（21件）
  test_hope_message.py           # HOPEメッセージのテスト（8件）
  test_scenario_manager.py       # シナリオマネージャーのテスト（10件）
  test_action_recommendation.py  # 結論カード・優先アクションのテスト（14件）
  test_c_group_candidates.py     # C群候補一覧・トレードオフのテスト（10件）
  test_app_integration.py        # アプリ統合テスト・状態遷移安全性（29件）
  test_deployment_assets.py      # 配布資材・views存在確認（19件）
  （テスト総数は pytest 実行結果を参照）
playwright/
  test_app.spec.ts             # CI必須の正準E2E
  test_audit.spec.ts           # 手動/週次用の包括監査E2E
  test_scenario_qa.spec.ts     # 台本と実画面の数値照合
tools/
  browser_probe.html             # ブラウザ互換性チェック（Streamlit非依存・単体HTML）
deploy/
  launch_bed_control.bat         # サーバー起動スクリプト（Windows）
  launch_portable_firefox.bat    # ポータブルFirefox起動テンプレート
  open_bed_control.ps1           # PowerShellアクセススクリプト
docs/admin/
  intranet_deployment_plan.md    # 院内LAN展開計画（A/B/C方針比較）
  intranet_browser_compatibility_plan.md  # ブラウザ互換性対応方針
  browser_validation_matrix.md   # ブラウザ検証マトリクス
  portable_browser_operation_guide.md     # ポータブルブラウザ運用ガイド
  lan_setup_guide.md             # 院内SE向け設置手順書
pyproject.toml                   # ruff 設定
requirements.txt                 # 本番依存関係
requirements-edge90.txt          # Edge 90互換を目指す固定バージョン（検証前提）
requirements-dev.txt             # 開発用依存関係（pytest, ruff）
.github/workflows/test.yml      # CI（pytest + 2層ruff）
.github/workflows/e2e.yml       # CI（smoke + Playwright正準E2E）
package.json                    # Playwright E2E 用 Node 依存
package-lock.json               # Node 依存の再現性固定
```

## 今後の拡張余地

- 短期滞在手術等基本料3（短手3）の組み込み
- モジュール分割の深化（views/ 分離を開始済み、forecast_view_model.py 等の追加抽出）
- 未充填退院キュー proxy の UI 統合
- 空床ラグ（退院→次の入院までの時間）のリアルタイム計測
- 在宅復帰率の自動計算（退院先データの追加が前提）
- 看護必要度の自動取得（HIS連携が前提）
