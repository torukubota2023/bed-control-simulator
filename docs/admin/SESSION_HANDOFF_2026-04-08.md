# セッション引き継ぎメモ — 2026年4月8日

別PCで作業を継続するための記録です。

## 直近のセッションで行った主な修正（新しい順）

### 1. 病棟別表示時の Little法則計算修正 + 日次推移チャートの全体主義ライン表示（`ec8c81a`）

**問題1: フェーズ構成タブで C群が0%（理論在院日数 8.7日）になる**
- 原因: 病棟別表示時、`view_beds=47`（病棟値）と `monthly_admissions=150`（全体値）が混在していた
  - LOS = 47×0.925 / (150/30) = 8.7日 → A+B=70 > target_patients(43.5) → C群=0
- 修正: 病棟別表示時は月間入院数も病床比率で按分
  ```python
  if _selected_ward_key in ("5F", "6F"):
      _bed_ratio_phase = _view_beds / _TOTAL_BEDS_METRIC  # 47/94 = 0.5
      _monthly_adm_input = int(round(_monthly_adm_full * _bed_ratio_phase))  # 75
  ```
- What-if スライダーも病棟別では 60-90人 レンジに調整

**問題2: 日次推移タブで全体主義（均等努力）目標ラインが表示されない**
- 原因: 単体目標と全体主義目標が「どちらか一方のみ」表示の排他構造になっていた + データ取得フォールバックが弱かった
- 修正:
  - 単体目標線（赤/オレンジ/緑破線）と均等努力目標線（青点線）の **両方** を併記表示
  - データ取得を3段階フォールバック化（session_state → globals → 空辞書）
  - ラベル位置を上下に分けて視認性向上

### 2. デモデータ再生成 + クリア計画を全モードで病棟別表示（`9da557a`）

**デモデータの問題:**
- 旧 6F は C群29人（66.3%）と非現実的に多かった
- クリア計画が「C群15名退院」という非現実的な指示
- 過去90日のデータがなく3ヶ月rollingが計算できなかった

**新デモデータの数値:**
- **5F**: 過去90日 rolling LOS 18.5日（基準内）/ 4月集計 19.3日 / C群 12.6人（30.9%）
- **6F**: 過去90日 rolling LOS 20.0日（ぎりぎり基準内）/ 4月集計 21.7日（基準超過 +0.7日）
       / C群 19.6人（旧29人から削減）/ クリア計画: **C群追加退院3名でクリア**

**ストーリー性:** 6Fは過去3ヶ月はぎりぎり基準内 → 今月drifting → 早期対応必要

**クリア計画の病棟別表示:**
- `_render_clearance_plan()` ヘルパー関数を新規実装
- 「全体」モード時: 5F・6F それぞれを個別判定し、超過病棟のクリア計画を順次表示
- 「病棟」モード時: 該当病棟のクリア計画のみ表示

### 3. 平均在院日数の施設基準判定を「各病棟ごと」に変更（`a6c476d` — 重要な仕様修正）

地域包括医療病棟の平均在院日数基準は **病院全体ではなく各病棟それぞれ** が満たす必要がある、というユーザー指摘に基づく全面修正：

- **本日の病床状況**: 5F・6Fの rolling LOS を並列表示
- **意思決定ダッシュボード**: 各病棟の rolling LOS を専用セクションで並列表示、いずれかが超過するとアラート発動
- **HOPE送信サマリー**: `ward_rolling_los` パラメータ追加、UIを5F/6F個別入力に変更
- **マニュアル/help**: 「病院全体ではなく各病棟ごと」を明示

### 4. フェーズ構成タブに What-if シミュレーション追加（`4b911ab`）

経営会議で「もし月間入院数を○人にしたら」を即座に試算できる機能：
- 左列: 月間入院数スライダー(120-180)、目標稼働率スライダー(85-100%)
- 右列: 主要メトリクス3つ + 施設基準リスク自動判定 + フェーズ構成棒グラフ
- 下部: 現状との比較で日/月/年の運営貢献額差分を表示

### 5. フェーズ構成の理想比率を Little法則ベースの動的計算に変更（`f528698`）

従来のハードコード値 A:15/B:45/C:40（経験則・根拠不明）を、Little法則ベースの動的計算に変更：
- `calculate_ideal_phase_ratios()` 関数を `bed_data_manager.py` に新規追加
- 月間入院数・目標稼働率に応じて理論値を動的計算
- 「🔎 この理論値はどう計算しているか（Little法則）」expander で4ステップの計算を表示

### 6. 過去3ヶ月rolling 平均在院日数を実装（`e6d40d2` + `c0641bd`）

2026年度改定対応:
- `calculate_rolling_los()` 関数を `bed_data_manager.py` に追加
- 厚労省公式（在院患者延日数 ÷ (新入院+退院)/2）を90日windowに適用
- データ90日未満時は揃っている日数で計算
- 本日の病床状況・意思決定ダッシュボード・HOPE送信サマリーに常時表示
- Streamlit Cloud（Python 3.9）互換のため型ヒント `dict | None` を削除

### 7. デモシナリオ Scene 9 に再演チェックリスト + 毎日5分の入力項目を追加（`cc728aa`）

経営会議向けプレゼン台本に：
- 🎬 アプリ実演の再確認（8ステップのオペレーション手順）
- 📝 毎日5分の入力項目（具体リスト・表形式）

---

## 現在の主要ファイル状態

### アプリ本体
- `scripts/bed_control_simulator_app.py` — メインアプリ（Streamlit）
- `scripts/bed_data_manager.py` — 日次データ管理 + 計算関数（rolling_los, ideal_phase_ratios）
- `scripts/hope_message_generator.py` — HOPE送信サマリー生成
- `scripts/help_content.py` — ヘルプテキスト

### デモデータ
- `data/sample_actual_data_ward_202604.csv` — 220レコード（過去90日 + 4月20日分）
  - 5F: 過去90日 rolling LOS 18.5日 / 4月 19.3日
  - 6F: 過去90日 rolling LOS 20.0日 / 4月 21.7日（クリア計画3名）

### ドキュメント
- `docs/admin/BedControl_Manual_v3.md/.docx` — 公式マニュアル
- `docs/admin/bed_control_demo_scenario.docx` — デモシナリオ台本（Scene 1-9 + Scene 2-B/2-C）
- `docs/admin/presentation_script_bedcontrol.md/.docx` — 講演原稿（15スライド構成）
- `docs/admin/bed_control_evolution_presentation.pptx` — 理事向けプレゼン

---

## デプロイ環境

- **Streamlit Cloud**: https://bed-control-simulator.streamlit.app
- **GitHub repo**: https://github.com/torukubota2023/bed-control-simulator
- **デプロイブランチ**: `main`（pushすると自動再デプロイ）
- **Python バージョン**: 3.9（PEP 604 型ヒント `X | None` は使えない、`Optional[X]` か型ヒント削除で対応）

---

## 既知の制約・注意点

### Streamlit Cloud Python 3.9 制約
- `X | None` 構文（PEP 604）は import 失敗の原因になる
- `from __future__ import annotations` があっても一部の環境で評価エラー
- 解決策: 型ヒントを完全削除するか `Optional[X]` を使う

### 病棟別表示時の按分
- `_view_beds = 47`（病棟値）にする際は、`monthly_admissions` も病床比率で按分する必要あり
- 既に対応済み: `bed_control_simulator_app.py` line ~3700 付近

### 施設基準は各病棟ごと
- 平均在院日数基準（21日 or 20日）は **病院全体ではなく各病棟が個別に** 満たす必要がある
- 5F・6F それぞれを独立に rolling LOS で判定する仕組み済み

---

## 残タスク・次回検討事項

特になし（現在の修正サイクルは完了）。

実機での動作確認待ち：
- Streamlit Cloud再デプロイ後の表示確認
- 6F選択時のフェーズ構成タブで C群が0%でなく適切な値になっているか
- 日次推移チャートで単体目標線（赤）と均等努力目標線（青）が両方表示されているか
- クリア計画が「全体」モードでも病棟別に表示されているか

---

## 引き継ぎチェックリスト（別PCで作業を始める前に）

- [ ] `git pull origin main` で最新を取得
- [ ] `pip install streamlit pandas numpy matplotlib python-docx python-pptx jpholiday` で依存関係インストール
- [ ] `streamlit run scripts/bed_control_simulator_app.py` でローカル起動テスト
- [ ] デモデータをロードして上記4点の表示確認
- [ ] このセッションメモ（`docs/admin/SESSION_HANDOFF_2026-04-08.md`）を確認

---

**最終コミット:** `ec8c81a fix: 病棟別表示時のLittle法則計算と日次推移チャートの全体主義ライン表示`
**作成日:** 2026-04-08
