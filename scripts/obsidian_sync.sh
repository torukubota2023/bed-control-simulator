#!/usr/bin/env bash
# Obsidian AI 共有記憶 ヘルパースクリプト
# 副院長指示 (2026-05-04): MCP server 未起動時の curl ベース代替
#
# 使い方:
#   export OBSIDIAN_API_KEY="..."   # ~/.zshrc 等で永続化推奨
#   scripts/obsidian_sync.sh ls                              # AI共有記憶/ 一覧
#   scripts/obsidian_sync.sh ls projects                     # サブフォルダ一覧
#   scripts/obsidian_sync.sh cat projects/医師別KPI解析.md   # 読込
#   scripts/obsidian_sync.sh put projects/foo.md /tmp/foo.md # 新規/上書
#   scripts/obsidian_sync.sh append 40_未解決課題.md "- [ ] xxx"
#
# 環境変数:
#   OBSIDIAN_API_KEY (必須) — Local REST API のキー
#   OBSIDIAN_HOST    (省略可、既定 127.0.0.1)
#   OBSIDIAN_PORT    (省略可、既定 27124)
set -euo pipefail

HOST="${OBSIDIAN_HOST:-127.0.0.1}"
PORT="${OBSIDIAN_PORT:-27124}"
BASE="https://${HOST}:${PORT}/vault/AI共有記憶"

if [[ -z "${OBSIDIAN_API_KEY:-}" ]]; then
  echo "❌ OBSIDIAN_API_KEY 環境変数が未設定です。" >&2
  echo "   export OBSIDIAN_API_KEY='...' を ~/.zshrc に追加してください。" >&2
  exit 1
fi

CMD="${1:-help}"
shift || true

case "$CMD" in
  ls)
    SUB="${1:-}"
    URL="${BASE}/${SUB}"
    [[ -n "$SUB" && "${SUB: -1}" != "/" ]] && URL="${URL}/"
    curl -sk "$URL" \
      -H "Authorization: Bearer ${OBSIDIAN_API_KEY}" \
      | python3 -m json.tool
    ;;
  cat|read)
    PATH_REL="${1:?path required}"
    curl -sk "${BASE}/${PATH_REL}" \
      -H "Authorization: Bearer ${OBSIDIAN_API_KEY}" \
      -H "Accept: text/markdown"
    ;;
  put|write)
    PATH_REL="${1:?path required}"
    SRC="${2:?source file required}"
    curl -sk -X PUT "${BASE}/${PATH_REL}" \
      -H "Authorization: Bearer ${OBSIDIAN_API_KEY}" \
      -H "Content-Type: text/markdown" \
      --data-binary "@${SRC}"
    echo "✅ Wrote ${PATH_REL}"
    ;;
  append)
    PATH_REL="${1:?path required}"
    TEXT="${2:?text required}"
    curl -sk -X POST "${BASE}/${PATH_REL}" \
      -H "Authorization: Bearer ${OBSIDIAN_API_KEY}" \
      -H "Content-Type: text/markdown" \
      --data-binary $'\n'"${TEXT}"$'\n'
    echo "✅ Appended to ${PATH_REL}"
    ;;
  ping)
    curl -sk "https://${HOST}:${PORT}/" \
      -H "Authorization: Bearer ${OBSIDIAN_API_KEY}" \
      | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"Obsidian REST API: status={d.get('status')}, authenticated={d.get('authenticated')}, version={d.get('versions',{}).get('self')}\")"
    ;;
  help|*)
    cat <<EOF
Obsidian AI 共有記憶 ヘルパー

  $0 ping                          接続確認
  $0 ls [subfolder]                ファイル一覧
  $0 cat <path>                    読込
  $0 put <path> <local-file>       新規作成 / 上書き
  $0 append <path> <text>          末尾追記

例:
  $0 ping
  $0 ls projects
  $0 cat projects/医師別KPI解析.md
  $0 put projects/新ノート.md /tmp/new.md
  $0 append 40_未解決課題.md "- [ ] 新タスク"
EOF
    ;;
esac
