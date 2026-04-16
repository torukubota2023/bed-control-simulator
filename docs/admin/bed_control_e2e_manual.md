# ベッドコントロールアプリ E2E テスト & Claude 評価 実行マニュアル

## 1. このマニュアルの目的

ベッドコントロールシミュレーターの数値誤りや UI 崩れを、ブラウザ自動操作 (Playwright) で検出します。さらに、Claude AI が「医療経営の運用として妥当か」を言語化し、コードだけでは見えない課題を洗い出します。非エンジニアの医療スタッフ・事務担当の方も、コマンドを 1 つずつコピーすれば実行できるように書いています。

## 2. 前提環境の確認

このマニュアルは macOS を前提にしています。実行前に、以下の 3 つのソフトが入っているか確認してください。

- Node.js 18 以上
- npm (Node.js 付属)
- Python 3.11 以上

### 確認コマンド

ターミナルを開いて、以下を 1 行ずつ実行してください。

```bash
node --version
npm --version
python3 --version
```

表示例:

```
v18.19.0
10.2.3
Python 3.11.7
```

### 足りない場合の導入コマンド

Homebrew が入っていれば、以下でまとめて導入できます。

```bash
brew install node
brew install python@3.11
```

Homebrew 自体が無い場合は、公式サイト <https://brew.sh> の手順で先に導入してください。

## 3. 初回セットアップ (一度だけ)

リポジトリのクローンは既に済んでいる前提です (作業フォルダは `/Users/torukubota/ai-management`)。

### 作業フォルダに移動

```bash
cd /Users/torukubota/ai-management
```

### Playwright ライブラリ導入

```bash
npm install
```

所要時間は 1-2 分です。`node_modules/` フォルダが作成されます。

### ブラウザ (Chromium) 導入

```bash
npx playwright install chromium
```

所要時間は 2-3 分です。自動テスト専用の Chromium ブラウザがダウンロードされます。

### Claude API キー設定 (省略可)

Claude AI による運用妥当性の評価を使う場合は、リポジトリルートの `.env` ファイルに API キーを記載します。設定しなくてもテスト自体は動きますが、`@claude-eval` タグが付いたテストはスキップされます。

`playwright.config.ts` が dotenv で `.env` を自動読み込み（`override: true`）するため、**shell に `export` する必要はありません**。`.env` に書くだけで `npm run test:e2e` 実行時に自動で注入されます。

`.env` ファイルがまだ無い場合は `.env.example` をコピーして作成します。

```bash
cp .env.example .env
```

作成した `.env` ファイルを開いて、以下の行を追加または編集します。`sk-ant-...` の部分は Anthropic コンソールで取得した実際のキーに置き換えてください。

```
ANTHROPIC_API_KEY=sk-ant-...
```

`.env` は `.gitignore` されているため、git にはコミットされません。設定済みか確認するには以下を実行します（キー値は表示されず、存在だけ確認できます）。

```bash
grep -c "^ANTHROPIC_API_KEY=" .env
```

出力が `1` なら設定済み、`0` または `grep: .env: No such file or directory` なら未設定です。

## 4. 日常の実行手順 — 3 ステップ

### ステップ 1: テスト実行

```bash
npm run test:e2e:headed
```

このコマンド 1 つで、以下が自動で起きます。

1. Streamlit がポート 8501 で自動起動する
2. Chromium ブラウザが画面上に立ち上がる
3. テストシナリオが順に実行される (入力 → 画面遷移 → 数値検証)
4. 各ステップで Claude 評価が走る (API キー設定時のみ)

想定所要時間は 2-5 分です。ブラウザを触らずに待ってください。

### ステップ 2: 結果を確認

実行が終わると、ターミナルに以下のような一覧が出ます。

```
  ✓ 正常ケース: 入院 150 件 / ALOS 16
  ✓ 境界ケース: 稼働率 95% / ALOS 長期
  ✗ 異常ケース: 不正入力 (失敗)
```

緑の `✓` が成功、赤の `✗` が失敗です。より詳しく見るには HTML レポートを開きます。

```bash
npm run test:e2e:report
```

ブラウザが自動で開き、失敗箇所のスクリーンショットと差分が確認できます。

### ステップ 3: 失敗時は Claude 評価を読む

失敗が出た場合、`test-results/` 配下に Claude が生成した改善提案のテキストファイルが出力されます。

```bash
ls test-results/
```

例: `test-results/normal_case_claude_eval.txt` を開くと、「結論カードと詳細ビューで稼働率の表示が 0.3% ずれている可能性があります」のような具体的コメントが書かれています。該当箇所を修正して、再度ステップ 1 から実行してください。

## 5. シナリオテスト 3 ケースの意味

テストは 3 つの典型的な運用シーンを自動で再現します。

### 正常ケース: 入院 150 件 / ALOS 16

月間入院 150 件、平均在院日数 16 日の日常運用を模擬します。ここでアプリが「健全」と判定しなければ、基本ロジックが壊れている可能性があります。

### 境界ケース: 稼働率 95% / ALOS 長期

稼働率 95% 超、平均在院日数が長めの「ギリギリの運用」を検知できるかを確認します。施設基準の赤線 (ALOS 21 日、救急搬送 15%) を跨いだら、警告が正しく出るはずです。

### 異常ケース: 不正入力

マイナス値や文字列など、想定外の入力を与えてもアプリがクラッシュしないことを確認します。入力検証が壊れると、経営会議中に画面が固まる事故が起きるため、重要なチェックです。

## 6. 追加提案 6 観点 (医療経営アプリとしての評価)

3 ケースに加えて、以下 6 観点で「医療経営アプリとして妥当か」を Claude が評価します。

### セクション間整合性

結論カード (今日の一手) と詳細ビュー (ダッシュボード・ガードレール) で、同じ KPI の数字が矛盾していないかを確認します。片方が「稼働率 92%」、もう片方が「89%」だと、現場は混乱します。

### 施設基準ガードレール

ALOS 21 日、救急搬送後患者割合 15% の赤線を跨いだら「危険」判定が出るかを確認します。2026-06-01 以降は本則適用のため、特に重要です。

### 不連続点検出

2026-06-01 以降の短手3 Day 5/6 境界で、LOS 分母が +6 日 jump する仕様が正しく動作するかを検証します。Day 5 と Day 6 で結果が変わるはずです。

### 経過措置カウントダウンバナー

サイドバーに「経過措置終了まで残り XX 日」のバナーが表示されるかを確認します。2026-05-31 を過ぎたら「終了しました」に切り替わることも確認します。

### 「一見健全だが詰まりかけ」検出

稼働率 95% 超 × ALOS 25 日超のような、個別指標は緑でも組み合わせると危険な状態を Claude が言語化します。ルールベースでは検出しにくいパターンです。

### 再現性

同じ入力で何度リロードしても、同じ KPI・同じ結論カードが表示されるかを確認します。乱数や時刻依存が混入していると、経営会議のたびに数字が変わる事故につながります。

## 7. トラブルシューティング (FAQ 形式)

### Q1: 「localhost:8501 に接続できない」と出る

A: Streamlit の自動起動がタイムアウトした可能性があります。別ターミナルで以下を手動実行して、先にアプリを立ち上げてから再度テストを走らせてください。

```bash
streamlit run scripts/bed_control_simulator_app.py
```

画面が表示されたら、元のターミナルで `npm run test:e2e:headed` を再実行します。

### Q2: 「data-testid が見つからない」と出る

A: `dashboard_view.py` などで UI の data-testid 属性が壊れた可能性があります。以下で直近の変更を確認してください。

```bash
git diff scripts/views/
```

該当箇所を直すか、Git で一時的に戻してから再実行します。

### Q3: Claude 評価がスキップされる

A: `.env` ファイルに `ANTHROPIC_API_KEY` が設定されていない可能性があります。shell の `$ANTHROPIC_API_KEY` ではなく、`.env` ファイルを確認してください（Playwright は dotenv で `.env` から自動読み込みするため、shell の export は不要です）。

```bash
grep -c "^ANTHROPIC_API_KEY=" .env
```

出力が `1` でなければ、第 3 章の「Claude API キー設定」を実施してください。

### Q4: テストが重くて待ち時間が長い

A: 一部のテストだけを走らせる方法があります。

```bash
npm run test:e2e -- --project=chromium --grep "UI"
```

`--grep` の後ろにキーワードを入れると、そのテストだけが実行されます。例: `--grep "正常ケース"`。

### Q5: `npm install` でエラーが出る

A: Node.js のバージョンが古い可能性があります。第 2 章の確認コマンドで、18 以上になっているか確認してください。古ければ `brew upgrade node` で更新します。

## 8. CI/CD 組み込み (実装済み)

`main` への push / PR / 手動実行のタイミングで、Playwright E2E + Python テスト + smoke test を自動実行するワークフローを `.github/workflows/e2e.yml` に導入済みです。

### 8.1 トリガー
- `push` to `main`
- `pull_request` to `main`
- `workflow_dispatch`（GitHub Actions 画面から手動実行）

### 8.2 実行されるステップ
1. リポジトリチェックアウト（`actions/checkout@v4`）
2. Python 3.11 セットアップ＋`pip` キャッシュ
3. Python 依存関係インストール（`requirements.txt` / `requirements-dev.txt` を自動検出）
4. **Python テスト**: `PYTHONPATH=.:scripts python -m pytest tests/ -q`
5. **Smoke test**: `python scripts/hooks/smoke_test.py`
6. Node.js 20 セットアップ＋`npm` キャッシュ
7. Node 依存関係インストール（`package-lock.json` があれば `npm ci`、無ければ `npm install`）
8. Playwright ブラウザインストール（`chromium` のみ、`--with-deps` で OS 依存も含む）
9. **Playwright E2E**: `npm run test:e2e`（`ANTHROPIC_API_KEY` をシークレットから注入）
10. Playwright レポートを artifact としてアップロード（保持 14 日、常時）
11. 失敗時のみ `test-results/` を artifact としてアップロード（保持 7 日）

ランナーは `ubuntu-latest`、タイムアウトは 20 分です。

### 8.3 シークレット登録

GitHub リポジトリ Settings → Secrets and variables → Actions で `ANTHROPIC_API_KEY` を登録すると、Claude 評価ステップが有効化されます。未登録の場合は Claude 評価が自動 skip され、他のテストは正常に実行されます。

### 8.4 実ファイル

実装は `.github/workflows/e2e.yml` を直接参照してください。雛形ではなく本番適用ファイルです。

## 9. ディレクトリ構成一覧

```
playwright/
  test_app.spec.ts      ← メインテスト (3 ケース + 追加 6 観点)
  test_audit.spec.ts    ← 包括的監査テスト
  tests/
    scenarios.json      ← 9 シナリオ定義
utils/
  extract_data.ts       ← KPI 抽出
  streamlit_helpers.ts  ← Streamlit DOM 待機
  claude_eval.ts        ← Claude 評価関数群
```

`playwright/` にテスト本体、`playwright/tests/scenarios.json` にシナリオの入力値、`utils/` に共通ヘルパーが入っています。テストを追加する場合は `playwright/test_app.spec.ts` をコピーして編集します。

### 参考: data-testid 正準一覧

Streamlit 側（`dashboard_view.py` / `guardrail_view.py` / `bed_control_simulator_app.py`）に埋め込まれた hidden div 属性。`playwright/test_app.spec.ts` が正準セレクタとして参照します。変更・削除は破壊的です。

| data-testid | 意味 | 主な補助属性 |
|-------------|------|-------------|
| `occupancy` | 稼働率 | — |
| `alos` | 平均在院日数 | `data-limit`（制度上限 21〜24 日） |
| `phase` | 在院患者数（フェーズ合計） | `data-a`, `data-b`, `data-c` |
| `vacancy` | 空床数 | — |
| `revenue` | 稼働率1%の年間価値 | — |
| `action-card` | 結論カード（今日の一手） | `data-level`（error/warning/info/success） |
| `guardrail-summary` | 施設基準サマリー | — |

### 参考: scenarios.json の 9 シナリオ ID

| ID | 種別 | 概要 |
|----|------|------|
| `normal_balanced` | 正常 | バランス戦略（入院150・ALOS18） |
| `boundary_high_occupancy` | 境界 | 稼働率 95% 超 |
| `boundary_long_los` | 境界 | ALOS 制度上限近傍 |
| `boundary_low_admissions` | 境界 | 入院数極小 |
| `actual_data_mode` | 実績 | CSV 読み込みモード |
| `normal_150_alos16` | 正常 | おもろまち典型運用 |
| `safety_facility_standard_violation` | 安全性 | ALOS 21 日超過（赤） |
| `safety_discontinuity_day5_6` | 安全性 | 短手3 Day 5/6 不連続点（2026-06-01 本則） |
| `safety_clinical_dangerous_pattern` | 安全性 | 一見健全だが詰まりかけ |

## 10. 更新履歴

- 2026-04-17: 初版作成 (Playwright + Claude 評価の統合)
