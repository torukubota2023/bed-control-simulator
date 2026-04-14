# アプリ品質保証ルール

## このファイルの役割
- Claude Code が常時参照する固定ルールだけをここに置く
- 詳細な運用チェックリストと更新履歴は [docs/admin/bed_control_app_quality_assurance.md](/Users/torukubota/ai-management/docs/admin/bed_control_app_quality_assurance.md) に集約する

## 適用条件
- Python アプリケーションファイル（`*.py`）を変更するとき、このルールに従う
- とくにベッドコントロールシミュレーター本体と `scripts/views/` 配下の変更では必須

## 必須ルール
- 定数・閾値・ラベルは単一ソースに集約し、変更時は参照箇所を全検索する
- コード変更時は関連ドキュメント・ヘルプ・デモシナリオも連動確認する
- 条件分岐外で使う変数は必ず全ブランチで定義し、`st.session_state` の直接参照は初期化とガードを確認する
- UI モード・タブ・選択肢の全状態を確認し、構文チェック（`py_compile` / `ast.parse`）を通す
- [scripts/bed_control_simulator_app.py](/Users/torukubota/ai-management/scripts/bed_control_simulator_app.py) を変更したら [tests/test_app_integration.py](/Users/torukubota/ai-management/tests/test_app_integration.py) と `python3 scripts/hooks/smoke_test.py` を実行する
- 1つのバグを直したら同一パターンを全体検索し、横展開チェックの結果を報告する
- **セクション間整合性チェック（必須）**: 判定ロジックや表示内容を変更したら、同じデータを参照する他セクションと矛盾しないか確認し、結果を報告する（詳細は [bed_control_app_quality_assurance.md](docs/admin/bed_control_app_quality_assurance.md) §7 参照）
- リリース前は `/qa [ファイルパス]` を実行する

## 運用メモ
- よく更新する教訓・チェック項目・手順追加は `.claude` ではなく [docs/admin/bed_control_app_quality_assurance.md](/Users/torukubota/ai-management/docs/admin/bed_control_app_quality_assurance.md) を更新する
