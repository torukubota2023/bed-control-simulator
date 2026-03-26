#!/usr/bin/env node
/**
 * 汎用 Markdown → DOCX 変換スクリプト
 * 使用法: node convert_md_to_docx.js <input.md> [output.docx]
 */

const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  WidthType, AlignmentType, HeadingLevel, PageNumber, Header, Footer,
  ShadingType, LevelFormat, convertInchesToTwip } = require("docx");
const fs = require("fs");
const path = require("path");

// ── CLI 引数 ──
const INPUT = process.argv[2];
if (!INPUT) {
  console.error("使用法: node convert_md_to_docx.js <input.md> [output.docx]");
  process.exit(1);
}
if (!fs.existsSync(INPUT)) {
  console.error("ファイルが見つかりません:", INPUT);
  process.exit(1);
}
const OUTPUT = process.argv[3] || INPUT.replace(/\.md$/, ".docx");

const FONT_MINCHO = "游明朝";
const FONT_GOTHIC = "游ゴシック";
const PT = 2;

// ── Markdown Parser ──
const md = fs.readFileSync(INPUT, "utf-8");
const lines = md.split("\n");

function parseMarkdown(lines) {
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];

    if (/^---+\s*$/.test(line)) {
      blocks.push({ type: "hr" });
      i++;
      continue;
    }

    const h1Match = line.match(/^# (.+)$/);
    if (h1Match) { blocks.push({ type: "heading", level: 1, text: h1Match[1] }); i++; continue; }
    const h2Match = line.match(/^## (.+)$/);
    if (h2Match) { blocks.push({ type: "heading", level: 2, text: h2Match[1] }); i++; continue; }
    const h3Match = line.match(/^### (.+)$/);
    if (h3Match) { blocks.push({ type: "heading", level: 3, text: h3Match[1] }); i++; continue; }

    if (line.includes("|") && i + 1 < lines.length && /^\|[-\s|:]+\|$/.test(lines[i + 1].trim())) {
      const tableLines = [];
      let j = i;
      while (j < lines.length && lines[j].trim().startsWith("|")) { tableLines.push(lines[j]); j++; }
      blocks.push({ type: "table", lines: tableLines });
      i = j;
      continue;
    }

    const numMatch = line.match(/^(\d+)\.\s+(.+)$/);
    if (numMatch) {
      const items = [];
      let j = i;
      while (j < lines.length) {
        const nm = lines[j].match(/^(\d+)\.\s+(.+)$/);
        if (nm) {
          items.push({ text: nm[2], sub: [] });
          j++;
          while (j < lines.length && /^   - /.test(lines[j])) {
            items[items.length - 1].sub.push(lines[j].replace(/^   - /, ""));
            j++;
          }
        } else { break; }
      }
      blocks.push({ type: "numbered_list", items });
      i = j;
      continue;
    }

    if (/^- /.test(line)) {
      const items = [];
      let j = i;
      while (j < lines.length && (/^- /.test(lines[j]) || /^  - /.test(lines[j]) || /^  /.test(lines[j]))) {
        if (/^- /.test(lines[j])) {
          items.push({ text: lines[j].replace(/^- /, ""), sub: [] });
          j++;
          while (j < lines.length && /^  - /.test(lines[j])) {
            items[items.length - 1].sub.push(lines[j].replace(/^  - /, ""));
            j++;
          }
        } else {
          if (items.length > 0) items[items.length - 1].text += " " + lines[j].trim();
          j++;
        }
      }
      blocks.push({ type: "bullet_list", items });
      i = j;
      continue;
    }

    if (line.trim() === "") { i++; continue; }

    let paraText = line;
    i++;
    while (i < lines.length && lines[i].trim() !== "" && !/^#{1,3} /.test(lines[i]) && !/^---/.test(lines[i]) && !/^- /.test(lines[i]) && !/^\d+\.\s/.test(lines[i]) && !lines[i].includes("|")) {
      paraText += " " + lines[i].trim();
      i++;
    }
    blocks.push({ type: "paragraph", text: paraText.trim() });
  }
  return blocks;
}

function parseInline(text, fontSize = 12, font = FONT_MINCHO, defaultBold = false) {
  const runs = [];
  const regex = /(\*\*(.+?)\*\*|\*(.+?)\*|([^*]+))/g;
  let match;
  while ((match = regex.exec(text)) !== null) {
    if (match[2]) runs.push(new TextRun({ text: match[2], bold: true, font, size: fontSize * PT }));
    else if (match[3]) runs.push(new TextRun({ text: match[3], italics: true, font, size: fontSize * PT }));
    else if (match[4]) runs.push(new TextRun({ text: match[4], font, size: fontSize * PT, bold: defaultBold }));
  }
  return runs;
}

function parseTable(tableLines) {
  const rows = [];
  for (const line of tableLines) {
    const trimmed = line.trim();
    if (/^[\|\s\-:]+$/.test(trimmed)) continue;
    const cells = trimmed.split("|").filter((_, idx, arr) => idx > 0 && idx < arr.length - 1).map(c => c.trim());
    rows.push(cells);
  }
  return rows;
}

const numbering = {
  config: [
    {
      reference: "bullet-list",
      levels: [
        { level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: convertInchesToTwip(0.5), hanging: convertInchesToTwip(0.25) } } } },
        { level: 1, format: LevelFormat.BULLET, text: "\u25E6", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: convertInchesToTwip(1.0), hanging: convertInchesToTwip(0.25) } } } },
      ],
    },
    {
      reference: "decimal-list",
      levels: [
        { level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: convertInchesToTwip(0.5), hanging: convertInchesToTwip(0.25) } } } },
        { level: 1, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: convertInchesToTwip(1.0), hanging: convertInchesToTwip(0.25) } } } },
      ],
    },
  ],
};

const PAGE_WIDTH_DXA = 11906;
const MARGIN_LEFT = 1440;
const MARGIN_RIGHT = 1440;
const CONTENT_WIDTH = PAGE_WIDTH_DXA - MARGIN_LEFT - MARGIN_RIGHT;

const blocks = parseMarkdown(lines);
const children = [];

for (const block of blocks) {
  switch (block.type) {
    case "hr":
      children.push(new Paragraph({ spacing: { before: 300, after: 300 }, children: [] }));
      break;
    case "heading":
      if (block.level === 1) {
        children.push(new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 360, after: 200 },
          children: [new TextRun({ text: block.text, bold: true, font: FONT_GOTHIC, size: 16 * PT })] }));
      } else if (block.level === 2) {
        children.push(new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 300, after: 160 },
          children: [new TextRun({ text: block.text, bold: true, font: FONT_GOTHIC, size: 14 * PT })] }));
      } else {
        children.push(new Paragraph({ heading: HeadingLevel.HEADING_3, spacing: { before: 240, after: 120 },
          children: [new TextRun({ text: block.text, bold: true, font: FONT_GOTHIC, size: 12 * PT })] }));
      }
      break;
    case "paragraph":
      children.push(new Paragraph({ spacing: { before: 100, after: 100 }, children: parseInline(block.text) }));
      break;
    case "bullet_list":
      for (const item of block.items) {
        children.push(new Paragraph({ numbering: { reference: "bullet-list", level: 0 }, spacing: { before: 60, after: 60 }, children: parseInline(item.text) }));
        for (const sub of item.sub) {
          children.push(new Paragraph({ numbering: { reference: "bullet-list", level: 1 }, spacing: { before: 40, after: 40 }, children: parseInline(sub) }));
        }
      }
      break;
    case "numbered_list":
      for (const item of block.items) {
        children.push(new Paragraph({ numbering: { reference: "decimal-list", level: 0 }, spacing: { before: 60, after: 60 }, children: parseInline(item.text) }));
        for (const sub of item.sub) {
          children.push(new Paragraph({ numbering: { reference: "decimal-list", level: 1 }, spacing: { before: 40, after: 40 }, children: parseInline(sub) }));
        }
      }
      break;
    case "table": {
      const tableData = parseTable(block.lines);
      if (tableData.length === 0) break;
      const numCols = tableData[0].length;
      const colWidth = Math.floor(CONTENT_WIDTH / numCols);
      const columnWidths = Array(numCols).fill(colWidth);
      columnWidths[numCols - 1] = CONTENT_WIDTH - colWidth * (numCols - 1);

      const tableRows = tableData.map((row, rowIdx) => {
        const isHeader = rowIdx === 0;
        const cells = row.map((cellText, colIdx) => new TableCell({
          width: { size: columnWidths[colIdx], type: WidthType.DXA },
          margins: { top: 40, bottom: 40, left: 80, right: 80 },
          shading: isHeader
            ? { type: ShadingType.CLEAR, color: "auto", fill: "D9E2F3" }
            : { type: ShadingType.CLEAR, color: "auto", fill: "FFFFFF" },
          children: [new Paragraph({ spacing: { before: 40, after: 40 }, children: parseInline(cellText, 10, FONT_MINCHO, isHeader) })],
        }));
        while (cells.length < numCols) {
          cells.push(new TableCell({ width: { size: columnWidths[cells.length], type: WidthType.DXA }, margins: { top: 40, bottom: 40, left: 80, right: 80 }, children: [new Paragraph({ children: [] })] }));
        }
        return new TableRow({ children: cells });
      });

      children.push(new Table({ columnWidths, rows: tableRows, width: { size: CONTENT_WIDTH, type: WidthType.DXA } }));
      children.push(new Paragraph({ spacing: { before: 100, after: 100 }, children: [] }));
      break;
    }
  }
}

const doc = new Document({
  numbering,
  styles: {
    default: { document: { run: { font: FONT_MINCHO, size: 12 * PT } } },
  },
  sections: [{
    properties: {
      page: {
        size: { width: 11906, height: 16838 },
        margin: { top: 1440, bottom: 1440, left: MARGIN_LEFT, right: MARGIN_RIGHT },
      },
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          alignment: AlignmentType.RIGHT,
          children: [new TextRun({ text: "おもろまちメディカルセンター 内科/呼吸器内科", font: FONT_GOTHIC, size: 9 * PT, color: "666666" })],
        })],
      }),
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT_MINCHO, size: 9 * PT })],
        })],
      }),
    },
    children,
  }],
});

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(OUTPUT, buffer);
  console.log("DOCX generated:", OUTPUT);
}).catch(err => {
  console.error("Error generating DOCX:", err);
  process.exit(1);
});
