# 院内SE様への依頼文書

## 依頼文（メール文面として使える形式）

---

SE担当者様

お疲れ様です。副院長の久保田です。

病棟のベッドコントロール業務を支援するWebアプリケーションを開発しました。
院内LANの適切なサーバー（常時稼働PC）に設置し、病棟スタッフがブラウザからアクセスできるようにしていただきたくお願いいたします。

### 概要
- 病棟の入退院データを日次で入力し、稼働率・在院日数・収益を可視化するツール
- 患者個人情報は一切含まない（匿名集計データのみ）
- Webブラウザ（Chrome推奨）からアクセスする形式

### 技術要件
- Python 3.11以上
- 常時稼働するPC（Mac/Windows/Linux）
- 院内LANに接続されていること

詳細な設置手順は下記をご参照ください。
ご不明点があれば声をかけてください。よろしくお願いいたします。

---

## 設置手順書

### 前提条件
- OS: macOS / Windows / Linux いずれか
- Python 3.11以上がインストール済み
- Git がインストール済み
- 院内LANに接続済み

### 手順1: リポジトリの取得

```bash
cd ~
git clone https://github.com/torukubota2023/bed-control-simulator.git
cd bed-control-simulator
```

### 手順2: Python仮想環境の作成

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

### 手順3: 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 手順4: 動作確認（ローカル）

```bash
streamlit run scripts/bed_control_simulator_app.py
```

ブラウザで http://localhost:8501 が開けば成功。

### 手順5: 院内LAN公開設定

サーバーのIPアドレスを確認（例: 192.168.1.100）

```bash
streamlit run scripts/bed_control_simulator_app.py \
  --server.address 0.0.0.0 \
  --server.port 8501
```

病棟PCから http://192.168.1.100:8501 でアクセス可能。

### 手順6: 自動起動設定（推奨）

#### macOSの場合（launchd）
~/Library/LaunchAgents/com.omc.bed-control.plist を作成：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.omc.bed-control</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/[ユーザー名]/bed-control-simulator/.venv/bin/streamlit</string>
        <string>run</string>
        <string>/Users/[ユーザー名]/bed-control-simulator/scripts/bed_control_simulator_app.py</string>
        <string>--server.address</string>
        <string>0.0.0.0</string>
        <string>--server.port</string>
        <string>8501</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>/Users/[ユーザー名]/bed-control-simulator</string>
</dict>
</plist>
```

有効化:
```bash
launchctl load ~/Library/LaunchAgents/com.omc.bed-control.plist
```

#### Windowsの場合
タスクスケジューラで「ログオン時に実行」設定。

#### Linuxの場合（systemd）
/etc/systemd/system/bed-control.service を作成。

### 手順7: ファイアウォール設定

ポート8501を院内LANからアクセスできるよう開放してください。

### データ保存場所

- `data/bed_control.db` — SQLiteデータベース（全データ）
- バックアップ: このファイルをコピーするだけ

### トラブルシューティング

| 症状 | 対処 |
|---|---|
| アプリが起動しない | `source .venv/bin/activate` 後に再実行 |
| 他のPCからアクセスできない | `--server.address 0.0.0.0` を確認、ファイアウォール確認 |
| データが消えた | `data/bed_control.db` のバックアップから復元 |
| ポート8501が使用中 | `--server.port 8502` で別ポート指定 |

### データリセット（院内LAN設置時）

開発・テスト時のデータが残っている場合、本番運用開始前にリセットしてください。

**方法1: DBファイルを削除（推奨）**
```bash
cd ~/bed-control-simulator
rm -f data/bed_control.db
# アプリを再起動すれば空のDBが自動作成される
```

**方法2: アプリ画面からリセット**
1. 「日次データ入力」タブを開く
2. 「記録データ一覧」の下にある削除エリアで「全て消去」と入力
3. 削除ボタンを押す

> ⚠️ 本番運用開始後は誤ってリセットしないよう注意してください。
> 定期的に `data/bed_control.db` をコピーしてバックアップを取ることを推奨します。

### アップデート方法

```bash
cd ~/bed-control-simulator
git pull origin main
# アプリを再起動
```

### セキュリティ注意事項
- 患者個人情報は一切含まない設計
- 院内LANのみのアクセスを想定（外部公開禁止）
- 必要に応じてBasic認証を追加可能