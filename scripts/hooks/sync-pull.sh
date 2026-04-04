#!/bin/bash
# sync-pull.sh - 会話開始時にGitHubから最新を取得
# ConversationStart フックで実行

cd "$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0

# リモートが設定されているか確認
if ! git remote get-url origin &>/dev/null; then
    exit 0
fi

# ローカルに未コミットの変更がある場合はstashして保護
has_changes=false
if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
    has_changes=true
    git stash push -m "auto-stash before sync-pull $(date +%Y%m%d-%H%M%S)" --quiet
fi

# pull（fast-forward only で安全に）
if git pull --ff-only origin main --quiet 2>/dev/null; then
    echo "✅ GitHub から最新を取得しました"
else
    echo "⚠️ git pull できませんでした（競合の可能性）。手動確認してください" >&2
fi

# stashを戻す
if [ "$has_changes" = true ]; then
    git stash pop --quiet 2>/dev/null
fi

exit 0
