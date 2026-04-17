/**
 * 理事会向け_3提案の具体説明.docx ビルドスクリプト
 * Build: NODE_PATH=$(npm root -g) node build_proposal_docx.js
 */
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Header, Footer,
  AlignmentType, LevelFormat, HeadingLevel, PageBreak, PageNumber,
  BorderStyle, TabStopType, Table, TableRow, TableCell, WidthType, ShadingType,
} = require("docx");

const SRC = path.join(__dirname, "理事会向け_3提案の具体説明.md");
const OUT = path.join(__dirname, "理事会向け_3提案の具体説明.docx");

const raw = fs.readFileSync(SRC, "utf-8");

// 色
const NAVY = "1E3A5F";
const GRAY = "475569";
const GRAY_LIGHT = "94A3B8";
const GOLD = "C9A961";
const GREEN = "16A34A";
const RED = "C73E1D";
const YELLOW = "D97706";

const FONT_H = "Yu Gothic UI";
const FONT_B = "Yu Gothic";

// === Markdown → docx 変換 ===
function parseInlineBold(text, baseOpts = {}) {
  const runs = [];
  // remove backticks, asterisks→bold, strip emojis that aren't renderable
  const re = /\*\*(.+?)\*\*/g;
  let lastIdx = 0;
  let m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > lastIdx) {
      runs.push(new TextRun({ ...baseOpts, text: text.slice(lastIdx, m.index) }));
    }
    runs.push(new TextRun({ ...baseOpts, text: m[1], bold: true }));
    lastIdx = m.index + m[0].length;
  }
  if (lastIdx < text.length) {
    runs.push(new TextRun({ ...baseOpts, text: text.slice(lastIdx) }));
  }
  return runs.length > 0 ? runs : [new TextRun({ ...baseOpts, text })];
}

function paragraph(text, opts = {}) {
  return new Paragraph({
    children: parseInlineBold(text),
    spacing: { line: 340, after: 120 },
    ...opts,
  });
}

function bulletItem(text, level = 0) {
  return new Paragraph({
    numbering: { reference: "bullets", level },
    children: parseInlineBold(text),
    spacing: { line: 300, after: 60 },
  });
}

const children = [];
const lines = raw.split("\n");

// === 表紙 ===
children.push(new Paragraph({
  children: [new TextRun({ text: "", size: 24 })],
  spacing: { after: 400 },
}));
children.push(new Paragraph({
  children: [new TextRun({ text: "FOR BOARD REVIEW", color: GOLD, size: 20, bold: true, characterSpacing: 60 })],
  alignment: AlignmentType.CENTER,
  spacing: { after: 300 },
}));
children.push(new Paragraph({
  children: [new TextRun({ text: "3つの提案", color: NAVY, size: 48, bold: true })],
  alignment: AlignmentType.CENTER,
  spacing: { after: 200 },
}));
children.push(new Paragraph({
  children: [new TextRun({ text: "— 理事会向け具体説明書 —", color: NAVY, size: 26, italics: true })],
  alignment: AlignmentType.CENTER,
  spacing: { after: 200 },
}));
children.push(new Paragraph({
  children: [new TextRun({ text: "誰が・いつ・何を・どうするのかを、医療の専門用語を極力使わずご説明いたします", color: GRAY, size: 20 })],
  alignment: AlignmentType.CENTER,
  spacing: { after: 600 },
}));
children.push(new Paragraph({
  border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: GOLD } },
  spacing: { after: 200 },
}));

// 概要表
const overviewRows = [
  ["対象", "おもろまちメディカルセンター 理事会メンバー"],
  ["発表者", "副院長（内科 / 呼吸器内科）  久保田  徹"],
  ["文書日付", "2026年4月17日"],
  ["本日のご決裁事項", "① Phase 3α アプリ改修の承認 / ② GW2026 緊急パイロットの可否判断"],
  ["関連資料", "weekend_holiday_kpi.pptx（16スライド）、weekend_holiday_kpi_解説書.docx"],
];
const makeBorders = () => {
  const b = { style: BorderStyle.SINGLE, size: 4, color: "D1D5DB" };
  return { top: b, bottom: b, left: b, right: b };
};
children.push(new Table({
  width: { size: 9360, type: WidthType.DXA },
  columnWidths: [2800, 6560],
  rows: overviewRows.map(([k, v]) => new TableRow({
    children: [
      new TableCell({
        width: { size: 2800, type: WidthType.DXA },
        shading: { fill: "E8EEF5", type: ShadingType.CLEAR },
        borders: makeBorders(),
        margins: { top: 100, bottom: 100, left: 140, right: 140 },
        children: [new Paragraph({ children: [new TextRun({ text: k, bold: true, color: NAVY, size: 20 })] })],
      }),
      new TableCell({
        width: { size: 6560, type: WidthType.DXA },
        borders: makeBorders(),
        margins: { top: 100, bottom: 100, left: 140, right: 140 },
        children: [new Paragraph({ children: parseInlineBold(v, { size: 20 }) })],
      }),
    ],
  })),
}));
children.push(new Paragraph({ children: [new PageBreak()] }));

// === 本文変換 ===
// Simple state machine: handle H1 (#), H2 (##), H3 (###), H4 (####), blockquote (>), bullet (-), numbered (1.), table (|), code fence (```).
let i = 0;
let inCodeFence = false;
let codeBuffer = [];
let inTable = false;
let tableRows = [];

const flushCode = () => {
  if (codeBuffer.length) {
    // Code block — plain text, monospaced-like representation
    children.push(new Paragraph({
      shading: { fill: "F1F5F9", type: ShadingType.CLEAR },
      children: [new TextRun({
        text: codeBuffer.join("\n"),
        font: "Menlo", size: 18, color: GRAY,
      })],
      spacing: { after: 160 },
    }));
    codeBuffer = [];
  }
};

const flushTable = () => {
  if (tableRows.length) {
    const headerCells = tableRows[0];
    const nCols = headerCells.length;
    const colW = Math.floor(9360 / nCols);
    const colWidths = Array(nCols).fill(colW);
    const docRows = [];
    docRows.push(new TableRow({
      children: headerCells.map((c, idx) => new TableCell({
        width: { size: colWidths[idx], type: WidthType.DXA },
        shading: { fill: NAVY, type: ShadingType.CLEAR },
        borders: makeBorders(),
        margins: { top: 80, bottom: 80, left: 120, right: 120 },
        children: [new Paragraph({ children: [new TextRun({ text: c, bold: true, color: "FFFFFF", size: 18 })] })],
      })),
    }));
    for (let r = 2; r < tableRows.length; r++) {  // skip separator row (index 1)
      const cells = tableRows[r];
      docRows.push(new TableRow({
        children: cells.map((c, idx) => new TableCell({
          width: { size: colWidths[idx] || colW, type: WidthType.DXA },
          borders: makeBorders(),
          margins: { top: 80, bottom: 80, left: 120, right: 120 },
          children: [new Paragraph({ children: parseInlineBold(c, { size: 18 }) })],
        })),
      }));
    }
    children.push(new Table({
      width: { size: 9360, type: WidthType.DXA },
      columnWidths: colWidths,
      rows: docRows,
    }));
    children.push(new Paragraph({ spacing: { after: 200 }, children: [new TextRun({ text: "" })] }));
    tableRows = [];
    inTable = false;
  }
};

while (i < lines.length) {
  const line = lines[i];

  // Code fence
  if (/^```/.test(line)) {
    if (inCodeFence) { flushCode(); inCodeFence = false; }
    else { flushTable(); inCodeFence = true; }
    i++; continue;
  }
  if (inCodeFence) {
    codeBuffer.push(line);
    i++; continue;
  }

  // Table
  if (/^\s*\|/.test(line)) {
    if (!inTable) { inTable = true; }
    const cells = line.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim());
    tableRows.push(cells);
    i++; continue;
  } else if (inTable) {
    flushTable();
  }

  // H1: # title
  const h1 = line.match(/^#\s+(.+)$/);
  if (h1) {
    // Skip the top title (already in 表紙)
    i++; continue;
  }
  // H2: ## section
  const h2 = line.match(/^##\s+(.+)$/);
  if (h2) {
    const title = h2[1].replace(/[📝🎯🔧💰❓💡🎬🗳📎🗓📊]/g, "").trim();
    children.push(new Paragraph({
      heading: HeadingLevel.HEADING_1,
      children: [new TextRun(title)],
      spacing: { before: 400, after: 200 },
    }));
    i++; continue;
  }
  // H3: ### subsection
  const h3 = line.match(/^###\s+(.+)$/);
  if (h3) {
    const title = h3[1].replace(/[📝🎯🔧💰❓💡]/g, "").trim();
    children.push(new Paragraph({
      heading: HeadingLevel.HEADING_2,
      children: [new TextRun(title)],
      spacing: { before: 280, after: 120 },
    }));
    i++; continue;
  }
  // H4: #### subsubsection
  const h4 = line.match(/^####\s+(.+)$/);
  if (h4) {
    children.push(new Paragraph({
      heading: HeadingLevel.HEADING_3,
      children: [new TextRun(h4[1].trim())],
      spacing: { before: 220, after: 100 },
    }));
    i++; continue;
  }

  // Blockquote
  if (/^>\s/.test(line) || /^>$/.test(line)) {
    const text = line.replace(/^>\s?/, "").trim();
    if (text) {
      children.push(new Paragraph({
        children: parseInlineBold(text, { italics: true, color: GRAY }),
        shading: { fill: "FFF8DC", type: ShadingType.CLEAR },
        border: { left: { style: BorderStyle.SINGLE, size: 18, color: GOLD } },
        indent: { left: 240 },
        spacing: { line: 320, after: 80 },
      }));
    }
    i++; continue;
  }

  // Horizontal rule
  if (/^---+\s*$/.test(line)) {
    children.push(new Paragraph({
      border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "CBD5E1" } },
      spacing: { before: 160, after: 200 },
    }));
    i++; continue;
  }

  // Bullet - item
  const bulletMatch = line.match(/^-\s+(.+)$/);
  if (bulletMatch) {
    children.push(bulletItem(bulletMatch[1]));
    i++; continue;
  }
  // Numbered item
  const numMatch = line.match(/^(\d+)\.\s+(.+)$/);
  if (numMatch) {
    children.push(new Paragraph({
      numbering: { reference: "numbers", level: 0 },
      children: parseInlineBold(numMatch[2]),
      spacing: { line: 300, after: 60 },
    }));
    i++; continue;
  }

  // Q: / A: formatted
  const qm = line.match(/^\*\*Q:\s*(.+?)\*\*\s*$/);
  const am = line.match(/^A:\s*(.+)$/);
  if (qm) {
    children.push(new Paragraph({
      children: [
        new TextRun({ text: "Q: ", bold: true, color: NAVY }),
        ...parseInlineBold(qm[1]),
      ],
      spacing: { line: 320, after: 60 },
      indent: { left: 240 },
    }));
    i++; continue;
  }
  if (am) {
    children.push(new Paragraph({
      children: [
        new TextRun({ text: "A: ", bold: true, color: GRAY }),
        ...parseInlineBold(am[1]),
      ],
      spacing: { line: 320, after: 200 },
      indent: { left: 240 },
    }));
    i++; continue;
  }

  // Empty line
  if (line.trim() === "") {
    i++; continue;
  }

  // Default: paragraph
  children.push(paragraph(line));
  i++;
}

flushCode();
flushTable();

// === Document 組み立て ===
const doc = new Document({
  creator: "副院長  久保田  徹",
  title: "3つの提案 — 理事会向け具体説明書",
  description: "おもろまちメディカルセンター 経営会議資料",
  styles: {
    default: {
      document: { run: { font: FONT_B, size: 22 } },
    },
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, color: NAVY, font: FONT_H },
        paragraph: {
          spacing: { before: 400, after: 200 },
          outlineLevel: 0,
          border: { bottom: { style: BorderStyle.SINGLE, size: 18, color: GOLD, space: 4 } },
        },
      },
      {
        id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, color: NAVY, font: FONT_H },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 1 },
      },
      {
        id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 22, bold: true, color: GRAY, font: FONT_H },
        paragraph: { spacing: { before: 180, after: 80 }, outlineLevel: 2 },
      },
    ],
  },
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [
          { level: 0, format: LevelFormat.BULLET, text: "●", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 480, hanging: 240 } } } },
          { level: 1, format: LevelFormat.BULLET, text: "○", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 800, hanging: 240 } } } },
        ],
      },
      {
        reference: "numbers",
        levels: [
          { level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 480, hanging: 240 } } } },
        ],
      },
    ],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 11906, height: 16838 },  // A4
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
      },
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          tabStops: [{ type: TabStopType.RIGHT, position: 9026 }],
          children: [
            new TextRun({ text: "3つの提案 — 理事会向け具体説明書", color: GRAY_LIGHT, size: 18 }),
            new TextRun({ text: "\t" }),
            new TextRun({ text: "おもろまちメディカルセンター", color: GRAY_LIGHT, size: 18 }),
          ],
          border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: GOLD, space: 4 } },
        })],
      }),
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [
            new TextRun({ text: "Page ", color: GRAY_LIGHT, size: 18 }),
            new TextRun({ children: [PageNumber.CURRENT], color: NAVY, size: 18, bold: true }),
            new TextRun({ text: " / ", color: GRAY_LIGHT, size: 18 }),
            new TextRun({ children: [PageNumber.TOTAL_PAGES], color: GRAY_LIGHT, size: 18 }),
          ],
        })],
      }),
    },
    children,
  }],
});

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(OUT, buffer);
  console.log("✅ Wrote:", OUT);
  console.log(`   output bytes: ${buffer.length}`);
}).catch((err) => {
  console.error("❌ Error:", err);
  process.exit(1);
});
