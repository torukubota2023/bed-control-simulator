#!/bin/bash
# qa-precommit.sh - コミット前品質チェック
#
# 使い方:
#   スタンドアロン: bash scripts/hooks/qa-precommit.sh [ファイルパス...]
#   pre-commit hook: .git/hooks/pre-commit からこのスクリプトを呼び出す
#
# チェック内容:
#   1. py_compile による構文チェック
#   2. ast.parse による AST 解析チェック
#   3. 数値リテラルの重複検出（同じ値が3回以上出現 → 定数化を推奨）

set -euo pipefail

# 引数がなければ、git でステージされた .py ファイルを対象とする
if [ $# -eq 0 ]; then
    FILES=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null | grep '\.py$' || true)
else
    FILES="$@"
fi

if [ -z "$FILES" ]; then
    echo "✅ 対象の .py ファイルがありません"
    exit 0
fi

ERRORS=0
WARNINGS=0

for FILE in $FILES; do
    if [ ! -f "$FILE" ]; then
        continue
    fi

    # 1. py_compile による構文チェック
    if ! python3 -m py_compile "$FILE" 2>/tmp/qa_pycompile.log; then
        echo "❌ 構文エラー: $FILE"
        cat /tmp/qa_pycompile.log
        ERRORS=$((ERRORS + 1))
        continue
    fi

    # 2. AST parse チェック
    if ! python3 -c "import ast; ast.parse(open('$FILE').read())" 2>/dev/null; then
        echo "❌ AST解析エラー: $FILE"
        ERRORS=$((ERRORS + 1))
        continue
    fi

    echo "✅ 構文OK: $FILE"

    # 3. 数値リテラルの重複検出（警告のみ、コミットは止めない）
    python3 -c "
import ast, collections
with open('$FILE') as f:
    tree = ast.parse(f.read())
nums = collections.Counter()
for node in ast.walk(tree):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        if node.value not in (0, 1, 2, -1, 0.0, 1.0, True, False, None) and abs(node.value) > 9:
            nums[node.value] += 1
dupes = {k: v for k, v in nums.items() if v >= 3}
if dupes:
    print(f'⚠️  定数重複の疑い ($FILE):')
    for val, count in sorted(dupes.items(), key=lambda x: -x[1]):
        print(f'   値 {val} が {count} 回出現 → 定数化を検討')
" 2>/dev/null && true
done

echo ""
if [ $ERRORS -gt 0 ]; then
    echo "🚫 $ERRORS 件のエラーが検出されました。コミットを中止します。"
    exit 1
fi

echo "✅ QA事前チェック完了"
exit 0
