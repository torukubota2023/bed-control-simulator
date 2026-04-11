# DOCX ↔ アプリ整合性チェック＆同期

## 目的
docs/admin/ 配下の DOCX ファイルとアプリコード（bed_control_simulator_app.py, help_content.py 等）の整合性を確認し、不整合があれば修正する。

## 実行手順

### Step 1: DOCX からキーワード・数値を抽出
以下の DOCX ファイルを python-docx で読み込み、重要な用語・数値を抽出する:
- `docs/admin/bed_control_demo_scenario.docx`（デモシナリオ台本）
- `docs/admin/BedControl_Manual_v3.docx`（運用マニュアル）
- `docs/admin/app_development_manual_for_hospital_staff.docx`（開発マニュアル）

抽出対象:
- **UI要素名**: タブ名、ボタン名、セクション名（「本日の病床状況」「助け合い」「入退院セット調整」等）
- **判定パターン**: 🟢🔴⚠️🟡📊 のアイコンとラベル
- **数値**: 空床コスト（○万円/日）、稼働率目標（90%等）、在院日数基準（21日等）
- **新しい用語**: DOCX に出現するがアプリに出現しない用語

### Step 2: アプリコードと照合
以下のファイルを Grep で検索し、不整合を検出する:
- `scripts/bed_control_simulator_app.py`
- `scripts/help_content.py`
- `scripts/hope_message_generator.py`

チェック項目:
1. **用語の不一致**: DOCX で使っている用語がアプリの UI 表示やヘルプテキストと異なる
2. **数値の不一致**: DOCX の金額・パーセンテージがアプリの計算結果と異なる
3. **新しい用語の未反映**: DOCX に登場する新用語がアプリ側に取り込まれていない
4. **削除された用語の残存**: DOCX から消えた用語がアプリに残っている

### Step 3: 結果を報告
不整合をテーブル形式で報告する:

| # | ファイル | 用語/数値 | DOCX の記述 | アプリの記述 | 対応 |
|---|---|---|---|---|---|
| 1 | demo_scenario | 入退院セット調整 | ○ 使用中 | ✗ 未反映 | help_content.py に追加 |
| 2 | ... | ... | ... | ... | ... |

### Step 4: 修正（ユーザー承認後）
- 不整合が見つかった場合、修正案を提示する
- ユーザーの承認を得てから修正を実行する
- 修正後は py_compile + smoke_test で検証
- 関連ドキュメント（CLAUDE.md 等）も必要に応じて更新

## 注意
- DOCX の内容が「正」、アプリが「従」の関係（先生が直接修正した内容を尊重）
- ただしアプリの計算ロジックに関わる数値は、アプリ側が正（DOCX の数値が古い可能性）
- 判断が難しい場合はユーザーに確認する
