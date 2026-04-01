const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, LevelFormat, HeadingLevel,
  BorderStyle, WidthType, ShadingType, PageNumber, PageBreak
} = require("docx");

// コードブロック用のスタイル
function codeLine(text) {
  return new Paragraph({
    spacing: { before: 0, after: 0 },
    shading: { fill: "F5F5F5", type: ShadingType.CLEAR },
    indent: { left: 360 },
    children: [new TextRun({ text: text, font: "Courier New", size: 18 })]
  });
}

function codeBlock(lines) {
  return lines.map(l => codeLine(l));
}

// 表のセル
const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };

function headerCell(text, width) {
  return new TableCell({
    borders,
    width: { size: width, type: WidthType.DXA },
    shading: { fill: "2E75B6", type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    children: [new Paragraph({ children: [new TextRun({ text, bold: true, color: "FFFFFF", font: "Arial", size: 20 })] })]
  });
}

function dataCell(text, width) {
  return new TableCell({
    borders,
    width: { size: width, type: WidthType.DXA },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    children: [new Paragraph({ children: [new TextRun({ text, font: "Arial", size: 20 })] })]
  });
}

const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "Arial", color: "2E75B6" },
        paragraph: { spacing: { before: 360, after: 200 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: "Arial", color: "2E75B6" },
        paragraph: { spacing: { before: 280, after: 160 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "Arial", color: "404040" },
        paragraph: { spacing: { before: 200, after: 120 }, outlineLevel: 2 } },
    ]
  },
  numbering: {
    config: [
      { reference: "bullets",
        levels: [{ level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "numbers",
        levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
    ]
  },
  sections: [
    // セクション1: 依頼文
    {
      properties: {
        page: {
          size: { width: 11906, height: 16838 }, // A4
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
        }
      },
      headers: {
        default: new Header({
          children: [new Paragraph({
            alignment: AlignmentType.RIGHT,
            children: [new TextRun({ text: "おもろまちメディカルセンター", font: "Arial", size: 16, color: "999999" })]
          })]
        })
      },
      footers: {
        default: new Footer({
          children: [new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [new TextRun({ text: "Page ", size: 16 }), new TextRun({ children: [PageNumber.CURRENT], size: 16 })]
          })]
        })
      },
      children: [
        // タイトル
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("院内SE様への依頼文書")] }),

        // 依頼文サブタイトル
        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("依頼文")] }),

        // 区切り線
        new Paragraph({ border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "2E75B6", space: 1 } },
          spacing: { after: 200 }, children: [] }),

        new Paragraph({ spacing: { after: 200 }, children: [new TextRun("SE担当者様")] }),
        new Paragraph({ spacing: { after: 200 }, children: [new TextRun("お疲れ様です。副院長の久保田です。")] }),
        new Paragraph({ spacing: { after: 200 }, children: [
          new TextRun("病棟のベッドコントロール業務を支援するWebアプリケーションを開発しました。院内LANの適切なサーバー（常時稼働PC）に設置し、病棟スタッフがブラウザからアクセスできるようにしていただきたくお願いいたします。")
        ] }),

        // 概要
        new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun("概要")] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("病棟の入退院データを日次で入力し、稼働率・在院日数・収益を可視化するツール")] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("患者個人情報は一切含まない（匿名集計データのみ）")] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 }, spacing: { after: 200 },
          children: [new TextRun("Webブラウザ（Chrome推奨）からアクセスする形式")] }),

        // 技術要件
        new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun("技術要件")] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Python 3.11以上")] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("常時稼働するPC（Mac/Windows/Linux）")] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 }, spacing: { after: 200 },
          children: [new TextRun("院内LANに接続されていること")] }),

        new Paragraph({ spacing: { after: 100 }, children: [new TextRun("詳細な設置手順は下記をご参照ください。")] }),
        new Paragraph({ spacing: { after: 200 }, children: [new TextRun("ご不明点があれば声をかけてください。よろしくお願いいたします。")] }),

        // 区切り線
        new Paragraph({ border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "2E75B6", space: 1 } },
          spacing: { after: 200 }, children: [] }),

        // ページ区切り
        new Paragraph({ children: [new PageBreak()] }),

        // === 設置手順書 ===
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("設置手順書")] }),

        // 前提条件
        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("前提条件")] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("OS: macOS / Windows / Linux いずれか")] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Python 3.11以上がインストール済み")] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Git がインストール済み")] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 }, spacing: { after: 200 },
          children: [new TextRun("院内LANに接続済み")] }),

        // 手順1
        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("手順1: リポジトリの取得")] }),
        ...codeBlock([
          "cd ~",
          "git clone https://github.com/torukubota2023/bed-control-simulator.git",
          "cd bed-control-simulator"
        ]),
        new Paragraph({ spacing: { after: 200 }, children: [] }),

        // 手順2
        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("手順2: Python仮想環境の作成")] }),
        ...codeBlock([
          "python3 -m venv .venv",
          "source .venv/bin/activate   # Windows: .venv\\Scripts\\activate"
        ]),
        new Paragraph({ spacing: { after: 200 }, children: [] }),

        // 手順3
        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("手順3: 依存パッケージのインストール")] }),
        ...codeBlock(["pip install -r requirements.txt"]),
        new Paragraph({ spacing: { after: 200 }, children: [] }),

        // 手順4
        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("手順4: 動作確認（ローカル）")] }),
        ...codeBlock(["streamlit run scripts/bed_control_simulator_app.py"]),
        new Paragraph({ spacing: { before: 100, after: 200 }, children: [
          new TextRun("ブラウザで "),
          new TextRun({ text: "http://localhost:8501", bold: true }),
          new TextRun(" が開けば成功。")
        ] }),

        // 手順5
        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("手順5: 院内LAN公開設定")] }),
        new Paragraph({ spacing: { after: 100 }, children: [new TextRun("サーバーのIPアドレスを確認（例: 192.168.1.100）")] }),
        ...codeBlock([
          "streamlit run scripts/bed_control_simulator_app.py \\",
          "  --server.address 0.0.0.0 \\",
          "  --server.port 8501"
        ]),
        new Paragraph({ spacing: { before: 100, after: 200 }, children: [
          new TextRun("病棟PCから "),
          new TextRun({ text: "http://192.168.1.100:8501", bold: true }),
          new TextRun(" でアクセス可能。")
        ] }),

        // 手順6
        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("手順6: 自動起動設定（推奨）")] }),
        new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun("macOSの場合（launchd）")] }),
        new Paragraph({ spacing: { after: 100 }, children: [
          new TextRun({ text: "~/Library/LaunchAgents/com.omc.bed-control.plist", font: "Courier New", size: 20 }),
          new TextRun(" を作成：")
        ] }),
        ...codeBlock([
          '<?xml version="1.0" encoding="UTF-8"?>',
          '<plist version="1.0">',
          '<dict>',
          '    <key>Label</key>',
          '    <string>com.omc.bed-control</string>',
          '    <key>ProgramArguments</key>',
          '    <array>',
          '        <string>.venv/bin/streamlit</string>',
          '        <string>run</string>',
          '        <string>scripts/bed_control_simulator_app.py</string>',
          '        <string>--server.address</string>',
          '        <string>0.0.0.0</string>',
          '    </array>',
          '    <key>RunAtLoad</key>',
          '    <true/>',
          '    <key>KeepAlive</key>',
          '    <true/>',
          '</dict>',
          '</plist>'
        ]),
        new Paragraph({ spacing: { before: 100, after: 100 }, children: [new TextRun("有効化:")] }),
        ...codeBlock(["launchctl load ~/Library/LaunchAgents/com.omc.bed-control.plist"]),
        new Paragraph({ spacing: { after: 100 }, children: [] }),

        new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun("Windowsの場合")] }),
        new Paragraph({ spacing: { after: 100 }, children: [new TextRun("タスクスケジューラで「ログオン時に実行」設定。")] }),

        new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun("Linuxの場合（systemd）")] }),
        new Paragraph({ spacing: { after: 200 }, children: [new TextRun("/etc/systemd/system/bed-control.service を作成。")] }),

        // 手順7
        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("手順7: ファイアウォール設定")] }),
        new Paragraph({ spacing: { after: 200 }, children: [new TextRun("ポート8501を院内LANからアクセスできるよう開放してください。")] }),

        // データ保存場所
        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("データ保存場所")] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 },
          children: [
            new TextRun({ text: "data/bed_control.db", font: "Courier New", size: 20 }),
            new TextRun(" \u2014 SQLiteデータベース（全データ）")
          ] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 }, spacing: { after: 200 },
          children: [new TextRun("バックアップ: このファイルをコピーするだけ")] }),

        // ページ区切り
        new Paragraph({ children: [new PageBreak()] }),

        // トラブルシューティング
        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("トラブルシューティング")] }),
        new Table({
          width: { size: 9026, type: WidthType.DXA },
          columnWidths: [3500, 5526],
          rows: [
            new TableRow({ children: [headerCell("症状", 3500), headerCell("対処", 5526)] }),
            new TableRow({ children: [
              dataCell("アプリが起動しない", 3500),
              dataCell("source .venv/bin/activate 後に再実行", 5526)
            ] }),
            new TableRow({ children: [
              dataCell("他のPCからアクセスできない", 3500),
              dataCell("--server.address 0.0.0.0 を確認、ファイアウォール確認", 5526)
            ] }),
            new TableRow({ children: [
              dataCell("データが消えた", 3500),
              dataCell("data/bed_control.db のバックアップから復元", 5526)
            ] }),
            new TableRow({ children: [
              dataCell("ポート8501が使用中", 3500),
              dataCell("--server.port 8502 で別ポート指定", 5526)
            ] }),
          ]
        }),
        new Paragraph({ spacing: { after: 200 }, children: [] }),

        // データリセット
        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("データリセット（院内LAN設置時）")] }),
        new Paragraph({ spacing: { after: 200 }, children: [
          new TextRun("開発・テスト時のデータが残っている場合、本番運用開始前にリセットしてください。")
        ] }),

        new Paragraph({ spacing: { after: 100 }, children: [new TextRun({ text: "方法1: DBファイルを削除（推奨）", bold: true })] }),
        ...codeBlock([
          "cd ~/bed-control-simulator",
          "rm -f data/bed_control.db",
          "# アプリを再起動すれば空のDBが自動作成される"
        ]),
        new Paragraph({ spacing: { after: 200 }, children: [] }),

        new Paragraph({ spacing: { after: 100 }, children: [new TextRun({ text: "方法2: アプリ画面からリセット", bold: true })] }),
        new Paragraph({ numbering: { reference: "numbers", level: 0 },
          children: [new TextRun("「日次データ入力」タブを開く")] }),
        new Paragraph({ numbering: { reference: "numbers", level: 0 },
          children: [new TextRun("「記録データ一覧」の下にある削除エリアで「全て消去」と入力")] }),
        new Paragraph({ numbering: { reference: "numbers", level: 0 }, spacing: { after: 200 },
          children: [new TextRun("削除ボタンを押す")] }),

        // 警告
        new Paragraph({
          shading: { fill: "FFF3CD", type: ShadingType.CLEAR },
          indent: { left: 360 },
          spacing: { after: 200 },
          children: [
            new TextRun({ text: "\u26A0\uFE0F 注意: ", bold: true }),
            new TextRun("本番運用開始後は誤ってリセットしないよう注意してください。定期的に data/bed_control.db をコピーしてバックアップを取ることを推奨します。")
          ]
        }),

        // アップデート方法
        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("アップデート方法")] }),
        ...codeBlock([
          "cd ~/bed-control-simulator",
          "git pull origin main",
          "# アプリを再起動"
        ]),
        new Paragraph({ spacing: { after: 200 }, children: [] }),

        // セキュリティ注意事項
        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("セキュリティ注意事項")] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("患者個人情報は一切含まない設計")] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("院内LANのみのアクセスを想定（外部公開禁止）")] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("必要に応じてBasic認証を追加可能")] }),
      ]
    }
  ]
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync("/Users/kubotatoru/ai-management/docs/admin/lan_setup_guide.docx", buffer);
  console.log("DOCX generated: docs/admin/lan_setup_guide.docx");
});
