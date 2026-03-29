# 文献サマリー DOCX変換スキル
あなたはオーケストレーターです。以下のワークフローを**全て subagent/Taskに委託**して実行し
てください。自分では実装しないこと。
## 対象ファイルパス（省略時は最新ファイル）
$ARGUMENTS
---
## ワークフロー
### Step 1: 対象 MDファイルの特定（subagentに委託）
- 引数がファイルパスの場合: そのファイルを使用
- 引数が空の場合: `/Users/kubotatoru/ai-management/docs/pubmed/` 内の最新の.mdファイル
を使用（ファイル名の日付で判断）
- INPUT と OUTPUT パスを確定する（OUTPUTは同ディレクトリ・同名で拡張子を.docxに変更）
### Step 2: 汎用変換スクリプトの実行（subagentに委託）
以下のコマンドを実行:
```
node /Users/torukubota/ai-management/scripts/convert_md_to_docx.js "<INPUT_PATH>"
"<OUTPUT_PATH>"
```
スクリプトが存在しない場合、またはエラーが発生した場合はユーザーに報告して停止。
### Step 3: 完了確認
- 生成された DOCXファイルのパスを報告
- ファイルサイズを確認して正常生成を確認---
## 完了報告
1. 生成した DOCXファイルパス
2. ファイルサイズ
3. 変換元の MDファイル
