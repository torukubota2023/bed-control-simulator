# CLAUDE.md - おもろまちメディカルセンター AI ワークスペース

## プロジェクト概要
おもろまちメディカルセンター（総病床数94床、月間入院数約150件）の臨床・教育・経営業務を支援するワークスペース。副院長・内科/呼吸器内科医としての実務をClaude Codeで効率化する。

## 🟡 事務確認待ちの課題（次回セッションで確認結果を聞く）

（現在、事務確認待ちの新規課題はありません）

## 📊 過去1年入院データ統合（2026-04-24 データ受領・実装）

**データ受領日:** 2026-04-24（事務から `20260424.xlsx` 1823件）
**保存先:** `data/past_admissions_2025fy.csv`（氏名なし、医師コード化、患者番号通番化）
**期間:** 2025-04-01 〜 2026-03-31（12ヶ月）

**含まれる列（依頼した最小より多い）:**
- 必須: 病棟 / 救急車 / 入経路 / 入院日 / 退院日 / 日数
- ボーナス: 緊急（予定外/予定）/ 退経路（9分類）/ 手術 / 診療科 / 医師

**実装済み（A案=別テーブル共存）:**
1. ✅ `scripts/past_admissions_loader.py` — ローダー＋派生列（救急搬送種別、短手3推定、イ/ロ/ハ判定）
2. ✅ `scripts/bed_control_simulator_app.py` `_build_effective_monthly_summary()` — 既存 `calculate_rolling_emergency_ratio` に `monthly_summary` 経由で注入。日次データ > 過去CSV > 手動シード の優先順位で自動切替
3. ✅ `tests/test_past_admissions_loader.py`（19 tests pass）

**救急搬送後 15% 判定の制度ルール（副院長指示 2026-04-24）:**
- 分子 = **自院救急 + 下り搬送**（救急車=有の全件、制度判定はこれで統一）
- 分母 = **全入院**（短手3 を除外しない）
- 短手3 の識別は `is_short3_certain`（手術○×日数≤2、大腸ポリペク等確実）/ `is_short3_likely`（≤5日）で別途保持するが、救急比率計算とは完全分離

**残課題:**
- A: UI「過去1年 rolling 推移グラフ」追加
- B: UI「イ/ロ/ハ過去遡及」タブ追加
- D: `manual_seed_emergency_ratio.yaml` の bridge 卒業判定（過去CSVで重複する月のシードは廃止できる）

## 📐 2026年度診療報酬改定 対応ステータス（地域包括医療病棟入院料1/2）

**記録日:** 2026-04-20（方針更新 2026-04-20）

### 改定内容（令和 8 年度）

- 地域包括医療病棟入院料は **入院料1（A100 算定病棟なし）** / **入院料2（A100 算定病棟あり）** の 2 種に分離
- それぞれ **イ（入院料1）/ ロ（入院料2）/ ハ（入院料3）** の 3 区分に細分化され、入院形態×手術の有無で判定
- 当院は **入院料1**（A100 一般病棟入院基本料算定病棟なし）の想定

### イ/ロ/ハ の判定ロジック

| 入院形態 | 主傷病に対する手術 | 区分 | 点数（入院料1） |
|---------|-------------------|------|:-:|
| 緊急入院 | なし | **イ（入院料1）** | 3,367 点 |
| 緊急入院 | あり | ロ（入院料2） | 3,267 点 |
| 予定入院 | なし | ロ（入院料2） | 3,267 点 |
| 予定入院 | あり | **ハ（入院料3）** | 3,117 点 |

※ 手術：医科点数表 第二章第十部第一節に掲げるものに限る

### 「救急搬送後 15%」厳密判定の方針（2026-04-20 副院長決定）

**過去データの再エクスポート依頼は行わない**。事務データの既存 2 値分類（`admission_type = 「当日(予定外/緊急) / 予定」`）は制度上の「救急搬送後」と定義が違うため、予定外入院割合として参考値扱いする。

**代わりの運用:** 以下の **段階的厳密化** 戦略で、約 2 ヶ月で純実データ rolling 3 ヶ月計算に到達する：

1. **2026-04 以降の新規入院**：v4 `data_input_tab.py` で 5 区分経路 + 手術有無を記録（既に実装済）
2. **rolling 3 ヶ月計算が必要な期間** (2026-04〜2026-06)：
   - 先月・先々月（2026-02 / 2026-03）の救急搬送後割合を副院長が電子カルテ・レセプト画面で手集計し、`settings/manual_seed_emergency_ratio.yaml` に **手動シード入力**
   - `emergency_ratio.py` は shaded month の実データがなければシード値を使って rolling 3 ヶ月を計算
3. **2026-07 以降**：実データが 3 ヶ月蓄積するため、シードは自動的に不要化（純実データ計算に移行）

### アプリ対応ステータス

- [x] 経路 5 分類の入力欄（v4 `data_input_tab.py`）
- [x] **主傷病に対する手術の有無** フラグの入力欄（v4 `data_input_tab.py`）
- [x] **イ/ロ/ハ 自動判定関数** `classify_admission_tier()` (`scripts/reimbursement_config.py`)
- [x] 2026 改定点数表（入院料1/2 × イ/ロ/ハ 6 区分）の定数化
- [x] 過去/新規データの区別（`data_version` カラム：`legacy_binary` vs `detailed_v1`）
- [ ] **手動シード入力機構**：`settings/manual_seed_emergency_ratio.yaml` + `settings_tab.py` UI + `emergency_ratio.py` 統合（2026-04-20 実装予定）

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

## 📐 情報階層リデザイン（2026-04-18 Phase 1 + Phase 2 + Phase 3 + Phase 4 完了・最終形）

### Phase 1: セクション統合
旧「🗓 連休対策」「🏥 多職種退院調整カンファ」を「🏥 退院調整」に統合。
旧「🎯 意思決定支援」→「👨‍⚕️ 退院タイミング」タブも同セクションへ移設。
旧セクション名のリダイレクト／エイリアスは設けず、クリーンカット方針で一本化。

### Phase 2（2026-04-18）: 日常モニタリング1画面化
- 「📊 ダッシュボード」→「📊 今日の運営」に改名（朝30秒で状況把握する画面）
- 「🎯 意思決定ダッシュボード」「🚨 運営改善アラート」タブを「📊 今日の運営」に移設
- 並びは「意思決定ダッシュボード → 運営改善アラート → 日次推移 → フェーズ構成 → 運営分析 → トレンド分析」の 6 タブ（朝の目線の流れ: 総合状況 → アラート → 詳細指標）
- 「🎯 意思決定支援」は What-if 分析 + 仮説管理（+ 戦略比較）の 1-3 タブに縮小 — Phase 3 で「🔮 What-if・戦略」に改名予定

### Phase 3（2026-04-18）
- 「🎯 意思決定支援」→「🔮 What-if・戦略」に改名
- セクション責務が明確化: 仮説検証・経営シミュレーション専用
- タブ構成は変更なし（What-if 分析 + 仮説管理 ± 戦略比較）

### Phase 4（2026-04-18） — 最終
- 「📋 データ管理」→「⚙️ データ・設定」に改名
- 旧「📨 HOPE連携」セクションを削除 → 「📨 HOPE送信」タブとしてデータ・設定に吸収
- サイドバーの「🏃 短手3（包括点数・種類別）パラメータ」エクスパンダーを削除 → 「🏃 短手3設定」タブとして移設
- `_short3_revenue_map` / `_short3_cost_map` は `st.session_state` 経由で再構築し、widget は新タブに移動しても下流集計（運営貢献額・分離表示）の参照箇所は非変更
- **情報階層リデザイン完了**: 7 → 5 セクション

### 新しい動線（最終形）
- 日常モニタリングは「📊 今日の運営」へ一本化（6 タブ）
- 仮説検証・経営シミュレーションは「🔮 What-if・戦略」へ
- 退院判断関連は全て「🏥 退院調整」へ
- タブ: カンファ資料 / 退院タイミング / 今週の需要予測 / 退院候補リスト / 予約可能枠
- 入力・出力・マスター・連携は「⚙️ データ・設定」へ集約
- タブ: 日次データ入力 / 実績分析・予測 / 医師別分析 / 医師マスター / データエクスポート / HOPE送信 / 短手3設定（最大 7 タブ）
- **サイドバーは 5 セクション**（今日の運営 / What-if・戦略 / 制度管理 / 退院調整 / データ・設定）

### 影響範囲
- `scripts/bed_control_simulator_app.py` サイドバー `_section_names`・dispatch 判定・短手3 widget 移設・HOPE dispatch 分岐削除（Phase 4）
- `tests/test_app_integration.py` `_needs_sim_data` テストを「データ・設定」に更新（Phase 4）
- `playwright/test_audit.spec.ts` セクション巡回リストを 5 セクションに更新、監査5 の section 名を「データ・設定」に（Phase 4）
- `playwright/tests/scenarios.json` `section` 参照はカンファシナリオのみなので変更なし
- data-testid（conference-*, action-card, occupancy, alos, phase, vacancy, revenue, guardrail-summary）は一切変更していない
- `st.session_state` キー（`short3_rev_*`, `short3_cost_*`）は変更なし

### 2026-04-18: 戦略選択 UI 廃止
サイドバーの「戦略選択」（バランス/回転重視/安定維持）を UI から削除。
理由: 実運用で活用されておらず、選択ガイドも UI 上に存在しないため判断不能。
- UI: サイドバーから radio + checkbox 削除、戦略比較タブ削除、フッターの「戦略: バランス戦略」表記も削除
- ロジック: `simulate_bed_control(strategy="balanced")` にハードコード（`strategy = "バランス戦略"` 固定）
- 戦略別パラメータ辞書（`STRATEGY_MAP`）・`run_comparison()` キャッシュ関数・戦略別ユニットテストは保持（将来の復活に備えて温存）
- `playwright/tests/scenarios.json` の `strategy` フィールドはメタデータ扱いで未使用のため変更なし
- 全 691 pytest + smoke test 通過、Streamlit 起動確認済

## 🎨 デザインシステム（2026-04-18 構築）

ニュートラル・グレースケール中心の統一されたビジュアル言語。数値を目立たせ、装飾を抑え、医療専門職が毎日使う前提のトーン。

### 構成

| モジュール | 役割 |
|-----------|------|
| `scripts/design_tokens.py` | 色・タイポ・余白・角丸・シャドウの定数40+（単一ソース） |
| `scripts/theme_css.py` | `render_theme_css()` で全画面共通 CSS を生成 |
| `scripts/ui_components.py` | `section_title()` / `kpi_card()` / `alert()` + 純粋関数版 |
| `.streamlit/config.toml` | Streamlit ネイティブテーマ（`primaryColor=#374151` 等） |

`bed_control_simulator_app.py` 冒頭に `_bc_section_title()` / `_bc_kpi_card()` / `_bc_alert()` のフォールバック付きラッパーが用意されており、import 失敗しても本体機能は停止しない。

### カラートークン

| トークン | 値 | 用途 |
|---------|----|------|
| `COLOR_BG` | `#FAFAFA` | 画面全体の背景 |
| `COLOR_SURFACE` | `#FFFFFF` | カード・パネル背景 |
| `COLOR_BORDER` | `#E5E7EB` | 区切り線・境界 |
| `COLOR_TEXT_PRIMARY` | `#1F2937` | メインテキスト |
| `COLOR_TEXT_SECONDARY` | `#6B7280` | サブテキスト |
| `COLOR_TEXT_MUTED` | `#9CA3AF` | キャプション |
| `COLOR_ACCENT` | `#374151` | プライマリアクセント（ダークグレー） |
| `COLOR_SUCCESS` | `#10B981` | 達成 |
| `COLOR_WARNING` | `#F59E0B` | 注意 |
| `COLOR_DANGER` | `#DC2626` | 未達・警告 |
| `COLOR_INFO` | `#2563EB` | 情報（限定利用） |

### 使い方（実装パターン）

```python
# サイド: 定数利用（グラフスタイル等）
from design_tokens import COLOR_ACCENT, COLOR_SUCCESS, FONT_SIZE_CAPTION
fig.update_layout(colorway=[COLOR_ACCENT, COLOR_SUCCESS])

# メインアプリ内: ラッパー経由（フォールバック付き）
_bc_section_title("今朝の病棟状況", icon="🌅")
_bc_kpi_card("稼働率", "85", "%", severity="warning", size="lg")  # Hero
_bc_kpi_card("空床", "14", "床", severity="neutral", size="md")   # Secondary
_bc_kpi_card("内訳", "C群 31名", size="sm")                      # Detail
_bc_alert("救急搬送後割合が危険域 — 受入最優先モードへ", severity="danger")
```

### severity の使い分け
- `success`: 目標達成・好調
- `warning`: 注意喚起・レンジ下限
- `danger`: 制度基準未達・満床・死活リスク
- `info`: 情報・補足（濫用しない）
- `neutral`: 単純な数値表示

### リデザイン適用済み画面（Track 2, 2026-04-18）
| 画面 | 適用結果 |
|------|---------|
| 📊 今日の運営 > 意思決定ダッシュボード | 9 section + 19 KPI card + 9 alert、Hero/Secondary/Detail 3層化 |
| 📊 今日の運営 > 日次推移 | 4グラフ統一スタイル + KPI サマリー3枚 |
| ⚙️ データ・設定 > 日次データ入力 | 3 KPI + 9 section + 16 alert + expander折りたたみ |

### 運用ルール
- 新規画面は `_bc_*` ラッパーから使う（直接 `st.metric` / `st.success` を使わない）
- グラフスタイルは `design_tokens` の色を参照する
- `data-testid` が必要な箇所は `kpi_card(testid=...)` で hidden div 付き
- severity 色は意味が一意に定まるまで `neutral` を選ぶ（将来判断しやすいように）

## 📚 エビデンス検証完了記録（2026-04-18）

カンファ画面下部のエビデンスバー用 `data/facts.yaml`（80 件、v2）について、**全件を一次文献として PubMed MCP で精密検証**。副院長の医療倫理的要求（毎日表示されるローテーション 12 件は看護師・リハ・退院支援 NS・医師の信頼を損なってはならない）に応えるため実施。

### 検証範囲
- ローテーション 12 件（`rotation_eligible: true`）
- 折りたたみ 68 件（`rotation_eligible: false`、Layer 1-3 / 4-6 / 7）
- PMID 付き 約 54 件 + 国内統計 26 件

### 最終結果
| 項目 | 結果 |
|------|------|
| ハルシネーション | **0 件** ✅ |
| 致命的誤引用（別論文） | 先行で 2 件発見→修正済（f015 Loertscher / f021 Hartley） |
| PMID 実在確認 | 100% |
| 数値・内容一致 | 100%（軽微修正 7 件を含む） |
| DOI 整合率 | **100%**（全件 PubMed 公式 DOI に統一） |

### 累計修正 32 件
- DOI 誤記修正: 25 件（全 PMID 付きで公式 DOI に統一）
- n 数・内容修正: 5 件（f009, f036, f038, f079, f080）
- 致命的誤引用修正: 2 件（f015, f021）

### 検証レポート（7 本）
- [evidence_verification_rotation_12_2026-04-18.md](docs/admin/evidence_verification_rotation_12_2026-04-18.md)
- [evidence_verification_layer123_2026-04-18.md](docs/admin/evidence_verification_layer123_2026-04-18.md)
- [evidence_verification_layer456_2026-04-18.md](docs/admin/evidence_verification_layer456_2026-04-18.md)
- [evidence_verification_layer7_2026-04-18.md](docs/admin/evidence_verification_layer7_2026-04-18.md)
- [evidence_doi_crosscheck_2026-04-18.md](docs/admin/evidence_doi_crosscheck_2026-04-18.md)
- [evidence_doi_crosscheck_layer7_2026-04-18.md](docs/admin/evidence_doi_crosscheck_layer7_2026-04-18.md)
- [evidence_f079_verification_2026-04-18.md](docs/admin/evidence_f079_verification_2026-04-18.md)

### 今後の運用ルール
- 新規エビデンス追加時は必ず PubMed MCP で fetch_summary を取得し、PMID＋公式 DOI をそのままコピーする
- 「論文を知っている」状態から記憶で書かない
- 数値・n 数は abstract から直接取る
- 二次引用・孫引き・レビューからの孫引きは禁止（原著に必ずトレースダウン）

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
- **現行バージョン:** v3.5j（2026-04-23、退院カレンダー新設・入院受入枠改名、全 Python テスト + Playwright E2E testid テスト通過）
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
| v3.5j | 📅 退院カレンダー新設（月俯瞰 × 病棟別 × 当月/翌月、3 層カラー表示、枠超過警告、日曜推奨、動的枠調整インフラ）・既存「予約可能枠」を「入院受入枠」に改名 | `discharge_plan_store.py`, `discharge_slot_config.py`, `views/discharge_calendar_view.py` |

### 📅 退院カレンダー（v3.5j, 2026-04-23 副院長判断）
副院長の「不在のベッドコントローラーの代理」要望に応える機能。木曜カンファで
「退院が 8 名重なって稼働率崩壊」のような偶発事を未然に防ぐため、退院を
日付軸で平準化する。

**場所:** 🏥 退院調整 セクション > 📅 退院カレンダー タブ（カンファ資料の右隣）

**退院枠ルール（単一ソース: `scripts/discharge_slot_config.py`）:**
- 月〜土: 1 病棟 5 名 / 日祝: 1 病棟 2 名（固定）
- 超過は翌営業日 −1（連続累積なし、翌々日は 5 枠復帰）
- 日曜・祝日は動的調整対象外（2 枠固定）
- 稼働率 ≥ 95% or 空床 ≤ 3 で枠 +1（動的調整、呼び出し側からの稼働率注入は後続 PR）

**データモデル:**
- 患者 UUID をキーに `data/discharge_plans.json` に退院予定を永続化（.gitignore 済）
- 「調整開始日」は既存の `patient_status_history.json` から自動抽出（"new" 以外への最初の遷移日）
- 再入院は別 UUID（副院長判断：同一患者の再入院は独立した退院調整として扱う）

**UI 要素:**
- 3 層カラー表示（● 決定 / ○ 予定 / — 予定なし）
- 日曜・祝日は黄色背景で「⭐推奨枠」バッジ
- 入院予定を紫「入 N」で重ね表示、入退院差分「↑+N / ↓-N」で稼働率方向を示唆
- 前日超過は「↩-N」で翌営業日への繰り越しを可視化
- 動的枠調整は「✨」マーカー
- 突発退院は「⚡」マーカー、下部に主治医別頻度を集計（運用改善向け）

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

## 🔀 ブランチ・PR 運用ルール（2026-04-22 副院長決定、2PC 運用対応）

**原則:** 変更作業は **常に作業ブランチ**で行い、副院長が納得・承認した時に PR → main マージで本番反映する。`main` に直接コミットしない。

### セッション標準ワークフロー

**セッション開始時（自動化済み）:**
- `.claude/settings.json` の SessionStart フックが `git fetch && git pull` を自動実行
- 起動メッセージ「✅ GitHub から最新を取得しました」を確認

**作業開始時:**
```bash
git checkout -b <ブランチ名>   # 新規作業ブランチを切る
# もしくは既存ブランチで続行する場合
git checkout <ブランチ名> && git pull origin <ブランチ名>
```

**作業中:**
- `git add` / `git commit` でこまめに変更を確定
- ブランチ名は内容を反映: `feature/...` / `fix/...` / `refactor/...` / `docs/...`

**セッション終了時（必須）:**
```bash
git push origin <ブランチ名>
```
- **必ず push してから終了**（別 PC で引継げるようにするため）
- 次の作業予定・残タスクは本 CLAUDE.md の該当セクションに追記して push

### PR/マージのタイミング

- **副院長が「PR 作って」「マージして」と明示指示した時のみ実行**
- 勝手にマージしない（main を守る）
- 関連する複数変更は同じブランチに積み上げ、**まとめて 1 PR** にする方が履歴が追いやすい
- マージ方式は通常マージ（squash ではなく）— 個別コミットの履歴を残す

### 2PC 引継ぎ

**A PC → B PC への引継ぎ:**
1. A PC: 作業終了時に `git push`、次回予定を CLAUDE.md に追記して push
2. B PC: Claude Code 起動（フックが自動 fetch）、`git checkout <ブランチ名>` + `git pull`
3. 同じコンテキストで作業再開

**衝突予防（必須）:**
- 同じ作業ブランチを 2 PC 同時編集しない（時間で分ける or ブランチを別にする）
- セッション終了時の push を欠かさない
- セッション開始時の pull を欠かさない

### リポジトリ情報

- **リモート:** `torukubota2023/bed-control-simulator`
- **本番デプロイ:** Streamlit Cloud（main ブランチを参照、マージ後数分で再デプロイ）
- **使用 PC:** torumac-mini / mac-mini（両方から同じブランチで作業可能）

### 別 PC で作業ブランチの Streamlit を起動して確認する手順（2026-04-24 副院長指示）

作業ブランチに `git pull` してブラウザで動作確認したいとき、以下を実行：

```bash
cd ~/ai-management/.claude/worktrees/<worktree名>
git pull
~/ai-management/.venv/bin/streamlit run scripts/bed_control_simulator_app.py
```

**手順のポイント:**
- `cd` 先は Claude Code が自動生成する **worktree ディレクトリ**（例: `~/ai-management/.claude/worktrees/great-wozniak-e298a3`）。`ls ~/ai-management/.claude/worktrees/` で確認
- `git pull` で別 PC の最新コミットを取り込む（SessionStart フックが入っていればこれは自動化済み、手動でも OK）
- `~/ai-management/.venv/bin/streamlit` は **absolute path 指定が必要**。worktree 側には venv がないため、メインリポジトリの venv を参照する
- 起動後は http://localhost:8501 をブラウザで開く
- 終了は Ctrl+C

**worktree がない場合（= Claude Code を経由せず直接確認したい時）:**

```bash
cd ~/ai-management
git fetch origin
git checkout <ブランチ名>
git pull
.venv/bin/streamlit run scripts/bed_control_simulator_app.py
```
こちらはメインリポジトリ直下なので `.venv/bin/streamlit` が相対パスで使える。ただし同一ブランチを worktree が既に使っている場合は `fatal: already used by worktree` エラーが出るので、worktree 側でのセッションを先に終了すること。

## 🎓 学びの可視化ルール（2026-04-19 副院長指示、義務）

**背景:** 副院長の指摘「3（原因切り分け）と 4（指示や設計を変える）が貴方の裏で動いていて、
私には、あまり見えてこない。それだと、6（差分から学ぶ）が効いてこない」。

Claude は作業の裏で「診断 → 方針変更 → 再試行」を高速に繰り返すが、
結果だけでは副院長が学べない。以下を**義務**とする。

### 1. 結果＋判断理由の併記（毎回、義務）

**「B をやります」ではなく「A と C も検討したが B を選んだ理由は〜」を必ず示す。**

特に次の場面:
- 複数の実装アプローチから 1 つを選んだとき
- エラー原因を複数の可能性から絞り込んだとき
- デフォルト値・閾値・配置を決めたとき

### 2. ハイブリッド詳述（状況に応じた粒度）

- **小さい作業**（typo 修正、パス変更、単純な追加）: 結果のみで OK、冗長にしない
- **大きい設計判断・失敗対応**: 以下の 4 段構造を明示
  ```
  🔍 観察: 現状こうなっている / スクショで XX が見える
  💡 仮説: 原因は X の可能性が高い / なぜなら〜
  🎯 方針: A/B/C のうち B を選ぶ / 理由は〜
  ⚠️ リスク: 副作用として Y の可能性あり（あれば）
  ```

### 3. テスト失敗時は「切り分け → 根本原因 → 修正方針」を 3-5 行で開示

```
❌ FAIL: test_XX が落ちた
🔍 切り分け: A/B/C のどれか確認
→ B が原因（〜のため）
💡 根本原因: 〜
🎯 修正方針: 〜
```

### 4. セッション末の「📚 学び」要約

大きい作業が一区切りしたら、その日の作業で副院長が次回使える
**横展開可能な原則を 3 点** 抽出して `📚 学び` セクションとして要約する。

例:
> 📚 学び
> 1. 「次回カンファから表示」メッセージは教育用デモでは意味がない → デモフォールバック機構は他の画面でも応用可能
> 2. 要約バッジと既存セクションの役割分離は「上部に速報、下部に詳細」の原則で整理できる
> 3. 台本と実画面の不整合は「片方を直す vs 両方歩み寄る」を明示的に選ぶこと

### 5. インライン配置

学びや判断理由はログファイル別にせず、**回答内にインラインで混ぜる**。
（別ファイルだと読まれない実績がある）

### 6. 適用例外

以下は冗長化を避けるため詳述しない:
- git add/commit/push のような機械的操作
- ファイル名変更・単純なリネーム
- make qa / テスト実行の結果確認（PASS のみ）
