#!/bin/bash
# sync-push.sh - 会話終了時にGitHubへ変更をプッシュ
# ConversationTurnEnd フックで実行（コミットがある場合のみ）

cd "$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0

# リモートが設定されているか確認
if ! git remote get-url origin &>/dev/null; then
    exit 0
fi

# ローカルにリモートより先のコミットがあるか確認
git fetch origin main --quiet 2>/dev/null
ahead=$(git rev-list origin/main..HEAD --count 2>/dev/null)

if [ "$ahead" -gt 0 ] 2>/dev/null; then
    if git push origin main --quiet 2>/dev/null; then
        echo "✅ GitHub へ ${ahead} コミットをプッシュしました"
    else
        echo "⚠️ git push できませんでした。手動確認してください" >&2
    fi
fi

exit 0
