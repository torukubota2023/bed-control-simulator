#!/usr/bin/env python3
"""Teams通知スクリプト - Claude CodeからTeamsチャネルにメッセージを送信する"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path


def load_webhook_url() -> str:
    """環境変数または.envファイルからWebhook URLを取得"""
    url = os.environ.get("TEAMS_WEBHOOK_URL")
    if url:
        return url

    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("TEAMS_WEBHOOK_URL="):
                return line.split("=", 1)[1].strip()

    print("エラー: TEAMS_WEBHOOK_URL が設定されていません", file=sys.stderr)
    sys.exit(1)


def send_teams_message(title: str, body: str, webhook_url: str | None = None) -> bool:
    """Teamsにアダプティブカードを送信する"""
    url = webhook_url or load_webhook_url()

    # 本文を段落に分割して個別のTextBlockにする
    paragraphs = [p.strip() for p in body.replace("\\n", "\n").split("\n\n") if p.strip()]

    body_blocks: list[dict] = [
        {
            "type": "TextBlock",
            "text": title,
            "size": "medium",
            "weight": "bolder",
        },
    ]

    for para in paragraphs:
        # 見出し行（【】で始まる）は太字にする
        if para.startswith("【"):
            body_blocks.append({"type": "TextBlock", "text": " ", "size": "small"})
            lines = para.split("\n")
            body_blocks.append({
                "type": "TextBlock",
                "text": lines[0],
                "weight": "bolder",
                "wrap": True,
            })
            if len(lines) > 1:
                body_blocks.append({
                    "type": "TextBlock",
                    "text": "\n".join(lines[1:]),
                    "wrap": True,
                })
        else:
            body_blocks.append({
                "type": "TextBlock",
                "text": para,
                "wrap": True,
            })

    card = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "type": "AdaptiveCard",
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "version": "1.4",
                    "body": body_blocks,
                },
            }
        ],
    }

    data = json.dumps(card).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status == 202
    except Exception as e:
        print(f"送信エラー: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使い方: python notify_teams.py 'タイトル' ['本文']")
        print("例: python notify_teams.py '稼働率レポート' '本日の稼働率: 92.3%'")
        sys.exit(1)

    title = sys.argv[1]
    body = sys.argv[2] if len(sys.argv) > 2 else ""

    if send_teams_message(title, body):
        print("✅ Teams送信成功")
    else:
        print("❌ Teams送信失敗", file=sys.stderr)
        sys.exit(1)
