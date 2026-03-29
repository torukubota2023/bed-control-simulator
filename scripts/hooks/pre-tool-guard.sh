#!/bin/bash
# pre-tool-guard.sh - Claude Code PreToolUse フック
# 危険なコマンドやファイルアクセスをブロックする

# 標準入力からJSON読み取り
input=$(cat)
tool_name=$(echo "$input" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null)
tool_input=$(echo "$input" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin).get('tool_input',{})))" 2>/dev/null)

# Bashコマンドの危険パターンチェック
if [ "$tool_name" = "Bash" ]; then
    command=$(echo "$tool_input" | python3 -c "import sys,json; print(json.load(sys.stdin).get('command',''))" 2>/dev/null)

    # 危険なコマンドパターン
    if echo "$command" | grep -qE "rm -rf /|rm -rf ~|DROP TABLE|DROP DATABASE|format "; then
        echo "⛔ ブロック: 危険なコマンドを検出しました: $command" >&2
        exit 2
    fi
fi

# ファイルアクセスの危険パターンチェック
if [ "$tool_name" = "Read" ] || [ "$tool_name" = "Edit" ] || [ "$tool_name" = "Write" ]; then
    file_path=$(echo "$tool_input" | python3 -c "import sys,json; print(json.load(sys.stdin).get('file_path',''))" 2>/dev/null)

    # .envファイルへのアクセスをブロック（.venvは除外）
    if echo "$file_path" | grep -vq "\.venv"; then
        if echo "$file_path" | grep -qE "\.env$|\.env\."; then
            echo "⛔ ブロック: 環境変数ファイルへのアクセスを検出しました: $file_path" >&2
            exit 2
        fi
    fi

    # 認証情報ファイルへのアクセスをブロック
    if echo "$file_path" | grep -iqE "credential|secret"; then
        echo "⛔ ブロック: 認証情報ファイルへのアクセスを検出しました: $file_path" >&2
        exit 2
    fi
fi

# 問題なし
exit 0
