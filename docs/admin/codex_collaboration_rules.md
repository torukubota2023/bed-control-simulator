# Codex 協業ルール — Claude Code との並列作業でコンフリクトを防ぐ

**作成日**: 2026-04-25
**契機**: PR #23 マージ時に発生した 4 種類のコンフリクト（ベース違い／フラグ衝突／文言違い／機能重複）を踏まえ、Codex IDE と Claude Code が同じリポジトリで並列作業する際のルールを明文化する。

---

## 🎯 守ってほしいこと（要約）

1. **作業開始前に必ず最新 main から分岐する** — 古い feature ブランチを base にしない
2. **既存モジュールを必ずチェックしてから新規作成** — 重複機能を作らない
3. **グローバル定数・フラグ名はモジュール固有のサフィックスを付ける** — `_NURSING_NECESSITY_AVAILABLE` のような汎用名は衝突する
4. **修正対象ファイルの直近 commit を確認** — 文言・閾値が最近変わっていないか git log で見る
5. **PR 作成時は base を main にする** — 別 feature ブランチを base にしない

---

## 📋 作業開始前チェックリスト

### A. リポジトリ状態の確認

```bash
# 1. 最新を取得
git fetch origin

# 2. main の最新コミットを確認
git log origin/main --oneline -10

# 3. 直近 PR で何がマージされたか確認
gh pr list --state merged --limit 10

# 4. 自分が変更しようとするファイルの直近コミット履歴
git log origin/main --oneline -20 -- scripts/<対象ファイル>.py
```

### B. 必ず main から分岐する

```bash
# ✅ 正しい: 最新 main から分岐
git checkout main
git pull origin main
git checkout -b codex/<feature-name>

# ❌ ダメ: 古い feature ブランチから分岐
git checkout codex/old-feature
git checkout -b codex/new-feature  # ← old-feature の中身を引きずる
```

### C. 重複機能チェック

新規モジュール作成前に、類似モジュールが既に存在しないか必ず検索:

```bash
# 例: nursing_necessity 関連を作るとき
ls scripts/ | grep -i nursing
ls scripts/ | grep -i necessity
grep -rln "看護必要度\|nursing necessity" scripts/ docs/

# 既に nursing_necessity_loader.py / thresholds.py / lecture.py / strategy.py
# があるなら、新規作成ではなく既存モジュールへの追加を検討する
```

### D. PR の base ブランチ確認

```bash
# PR を作るとき、base が main であることを必ず確認
gh pr create --base main --title "..."

# ❌ ダメ: 別 feature ブランチを base にする
gh pr create --base codex/fix-main-ci-actions  # ← main にマージされない
```

---

## 📐 命名規約（衝突回避）

### グローバルフラグ（`_*_AVAILABLE` 系）

汎用名は禁止。モジュール固有のサフィックスを付ける:

| ❌ 悪い例 | ✅ 良い例 |
|---|---|
| `_NURSING_NECESSITY_AVAILABLE` | `_NURSING_NECESSITY_STRATEGY_AVAILABLE` |
| `_LOADER_AVAILABLE` | `_PAST_ADMISSIONS_LOADER_AVAILABLE` |
| `_VIEW_AVAILABLE` | `_DOCTOR_INSIGHT_VIEW_AVAILABLE` |

**ルール**: モジュール名（`nursing_necessity_strategy`）からそのまま `_NURSING_NECESSITY_STRATEGY_AVAILABLE` を生成する。

### エラー変数

```python
# ❌ ダメ
_FOO_ERROR = "..."

# ✅ 良い
_FOO_STRATEGY_ERROR = "..."  # モジュール名と一致させる
```

### Streamlit セッションキー

`st.session_state.<key>` のキー名も同様。`st.session_state.nursing_necessity_df` のような汎用名は、別モジュールが同じキーを書き込む可能性がある。モジュール固有のプレフィックスを付ける（例: `nn_strategy_df`）。

### Streamlit widget key

`st.number_input(..., key="value_5f")` のような汎用キーは禁止。`key="nn_strategy_value_5f"` のようにモジュール接頭辞を付ける（既に Codex は `nursing_necessity_*` プレフィックスで実装済、これは正しい）。

---

## 📁 モジュール配置の基本方針

### 既存パターンを踏襲する

新規モジュールを作る前に、類似機能の既存モジュール構造を読んで真似する:

| 用途 | 配置 | 既存例 |
|---|---|---|
| 計算エンジン（pure function） | `scripts/<feature>_loader.py` or `<feature>_engine.py` | `nursing_necessity_loader.py`, `nursing_necessity_thresholds.py`, `emergency_ratio.py` |
| UI 表示 | `scripts/views/<feature>_view.py` | `dashboard_view.py`, `c_group_view.py` |
| データ抽出スクリプト | `scripts/extract_<feature>.py` | `extract_nursing_necessity_from_xlsm.py` |
| 教育コンテンツ | `scripts/<feature>_lecture.py` | `nursing_necessity_lecture.py` |
| 戦略エンジン | `scripts/<feature>_strategy.py` | `nursing_necessity_strategy.py` |

**重要**: 既存ファイル名と類似する名前（`nursing_necessity_X.py`）を作るときは、**既存モジュールが提供していない機能だけを追加**する。重複しないよう責務を切り分ける。

### モジュール責務の切り分け例

`nursing_necessity_*.py` 系の現在の責務分担（PR #22, #23 の整理結果）:

| ファイル | 責務 |
|---|---|
| `nursing_necessity_loader.py` | CSV ロード、月次集計、rolling 3ヶ月、breach 検出 |
| `nursing_necessity_thresholds.py` | 旧/新基準の transitional 切替、救急患者応需係数の計算 |
| `nursing_necessity_lecture.py` | 教育コンテンツ markdown + 参考資料庫の render 関数 |
| `nursing_necessity_strategy.py` | A/C項目パッケージ シミュレーション、ギャップ管理エンジン |

新規追加する場合はこの責務リストを更新し、重複がないことを確認する。

---

## 🔄 既存ファイル変更時の確認

### 文言・閾値の最新化チェック

UI 文字列・KPI 閾値・分類ラベル等は、**直近 PR で変更されている可能性**が高い。修正前に以下を確認:

```bash
# 対象ファイルの直近 20 コミットを見る
git log origin/main --oneline -20 -- scripts/bed_control_simulator_app.py

# 特定の文言を変更する場合、最新の表現を確認
git grep "週末空床リスク" origin/main -- scripts/

# 直近で変わった可能性が高い箇所の例（PR #19 で変更済）:
# - 週末空床リスク指標: 「木+金退院率」 → 「金+土退院率」
# - 退院振替方針: 「金曜→火〜木前倒し」 → 「金+土→月曜以降後ろ倒し」
```

### よくある「最近変わった」項目

このプロジェクト固有の高頻度変更項目:

| 項目 | 変更履歴の例 | 注意点 |
|---|---|---|
| サイドバーセクション数 | 7 → 5 → 6（Phase 1〜5） | 必ず最新の `_section_names` を確認 |
| 看護必要度基準値 | 16% → 19% (Ⅰ), 14% → 18% (Ⅱ) | 旧値と新値を transitional で切替 |
| 救急15% 計算ロジック | 単月 → rolling 3ヶ月 (2026-06-01以降) | `is_transitional_period()` ゲートを必ず通す |
| 看護必要度評価項目 | A1 創傷処置（**褥瘡を除く**）、A3 注射薬剤 3 種類以上、A7 救急搬送後 2 日間 | 令和8改定で内容変更 |
| `data-testid` 値 | E2E テストで参照される正準セレクタ | 削除・改名禁止 |

---

## 🧪 PR 作成前のローカルテスト

```bash
# 1. 構文チェック
python3 -m py_compile scripts/<変更したファイル>.py

# 2. 関連テスト
.venv/bin/python -m pytest tests/test_<関連>.py -v

# 3. 統合テスト（必須）
.venv/bin/python -m pytest tests/test_app_integration.py -q

# 4. smoke test（必須）
.venv/bin/python scripts/hooks/smoke_test.py

# 5. もし bed_control_simulator_app.py を変更した場合、
#    Streamlit 起動して該当画面を目視確認すること（Codex 環境で困難なら PR で明記）
```

---

## 🤝 PR 提出時のテンプレート

```markdown
## Summary
（短く 1-3 行）

## Base / Conflict Check
- Base: main（最新 commit: `<sha>`、確認日時 2026-XX-XX）
- 既存類似モジュール: 確認済（`nursing_necessity_loader.py` 等は別責務として共存）
- 命名衝突: 確認済（フラグ名は `_<MODULE>_AVAILABLE` 規約に準拠）

## Files Changed
（gh pr diff で確認した一覧）

## Test plan
- [ ] py_compile OK
- [ ] 関連テスト PASSED
- [ ] test_app_integration.py PASSED
- [ ] smoke_test.py PASSED
- [ ] (UI変更ある場合) 実画面確認
```

---

## 💡 他の AI（Claude Code）との衝突を最小化するコツ

### 並列作業の見取り図

両 AI は別プロセスで作業し互いを直接知らないので、以下のシグナルで「他方が何をしているか」を察知:

1. **`gh pr list --state open`** — 現在オープンな PR 一覧を必ず確認
2. **CLAUDE.md / AGENTS.md** の最新版で、進行中タスクや確定事項をチェック
3. **直近 1 週間のコミット**を `git log --since="7 days ago"` で俯瞰

### 「相手が触りそうな領域」を予測

| Claude Code が活動する傾向の高い領域 | Codex が活動する傾向の高い領域 |
|---|---|
| `bed_control_simulator_app.py`（UI 統合） | 純関数モジュール（戦略エンジン等） |
| `views/` 配下の UI 部品 | 計算ロジック、テスト網羅 |
| ドキュメント類（CLAUDE.md, docs/admin/） | リファクタリング、CI 改善 |
| 副院長との対話的な要件詰め | 仕様確定後の実装 |

→ 両者が同時に `bed_control_simulator_app.py` を変更しようとしている兆候があれば、片方は待つか別ファイルに切り出す等の調整が望ましい。

### コンフリクトが起きやすい hot spot ファイル

直近頻繁に変更されるファイル（並列作業時は特に注意）:

- `scripts/bed_control_simulator_app.py`（10000行超、改修頻度極高）
- `CLAUDE.md`（運用方針の追記が多い）
- `tests/test_app_integration.py`（セクション/タブ追加で同期更新が必要）
- `playwright/test_audit.spec.ts`（同上）

→ これらに大規模追加をする時は、**機能を別モジュール／別 view ファイルに切り出して影響を局所化**することを優先する。

---

## 📞 困った時

PR がコンフリクトして自力で解消できない場合:
1. PR 本文に「Claude Code 側の作業と衝突しました。レビュー時に解消をお願いします」と明記
2. 副院長に相談（Slack/対面）
3. Claude Code セッションでマニュアルマージを依頼（実際 PR #23 はこのパターンで解消した）

---

*このルールは PR #23 マージ時の経験を踏まえて作成。今後追加の事例があれば随時更新する。*
