const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, LevelFormat,
  HeadingLevel, BorderStyle, WidthType, ShadingType,
  PageNumber, PageBreak
} = require("docx");

const FONT = "Hiragino Sans";
const FONT_W3 = "Hiragino Sans W3";
const FONT_W6 = "Hiragino Sans W6";
const COLOR_MAIN = "1B4F72";
const COLOR_ACCENT = "2E86C1";
const COLOR_LIGHT_BG = "EBF5FB";
const COLOR_TABLE_HEADER = "1B4F72";
const COLOR_WHITE = "FFFFFF";
const COLOR_GRAY = "666666";
const COLOR_TIP_BG = "FEF9E7";
const COLOR_TIP_BORDER = "F39C12";

const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };
const noBorder = { style: BorderStyle.NONE, size: 0 };
const noBorders = { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder };
const cellMargins = { top: 60, bottom: 60, left: 100, right: 100 };

// Helper: normal paragraph
function p(text, opts = {}) {
  return new Paragraph({
    spacing: { after: opts.afterSpacing || 120, before: opts.beforeSpacing || 0, line: opts.lineSpacing || 300 },
    indent: opts.indent ? { left: opts.indent } : undefined,
    alignment: opts.alignment || AlignmentType.LEFT,
    children: [new TextRun({ text, font: FONT, size: opts.size || 21, bold: opts.bold || false, color: opts.color || "333333", italics: opts.italics || false })],
  });
}

// Helper: multi-run paragraph
function pRuns(runs, opts = {}) {
  return new Paragraph({
    spacing: { after: opts.afterSpacing || 120, before: opts.beforeSpacing || 0, line: opts.lineSpacing || 300 },
    indent: opts.indent ? { left: opts.indent } : undefined,
    alignment: opts.alignment || AlignmentType.LEFT,
    children: runs.map(r => new TextRun({ font: FONT, size: 21, color: "333333", ...r })),
  });
}

// Helper: heading 1
function h1(text) {
  return new Paragraph({
    spacing: { before: 360, after: 200, line: 340 },
    children: [new TextRun({ text, font: FONT, size: 32, bold: true, color: COLOR_MAIN })],
    heading: HeadingLevel.HEADING_1,
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: COLOR_ACCENT, space: 4 } },
  });
}

// Helper: heading 2
function h2(text) {
  return new Paragraph({
    spacing: { before: 280, after: 160, line: 320 },
    children: [new TextRun({ text, font: FONT, size: 26, bold: true, color: COLOR_ACCENT })],
    heading: HeadingLevel.HEADING_2,
  });
}

// Helper: heading 3
function h3(text) {
  return new Paragraph({
    spacing: { before: 200, after: 120, line: 300 },
    children: [new TextRun({ text, font: FONT, size: 23, bold: true, color: "2C3E50" })],
    heading: HeadingLevel.HEADING_3,
  });
}

// Helper: tip/note box (simulated with indented colored text)
function tip(text) {
  return new Paragraph({
    spacing: { before: 80, after: 120, line: 280 },
    indent: { left: 360 },
    border: { left: { style: BorderStyle.SINGLE, size: 12, color: COLOR_TIP_BORDER, space: 8 } },
    children: [new TextRun({ text: "Point: ", font: FONT, size: 20, bold: true, color: COLOR_TIP_BORDER }), new TextRun({ text, font: FONT, size: 20, color: "7D6608" })],
  });
}

// Helper: code block paragraph
function code(text) {
  return new Paragraph({
    spacing: { before: 60, after: 60, line: 260 },
    indent: { left: 360 },
    shading: { fill: "F4F4F4", type: ShadingType.CLEAR },
    children: [new TextRun({ text, font: "Courier New", size: 18, color: "2C3E50" })],
  });
}

// Helper: bullet item
function bullet(text, level = 0) {
  return new Paragraph({
    spacing: { after: 60, line: 280 },
    numbering: { reference: "bullets", level },
    children: [new TextRun({ text, font: FONT, size: 21, color: "333333" })],
  });
}

// Helper: numbered item
function numbered(text, level = 0) {
  return new Paragraph({
    spacing: { after: 60, line: 280 },
    numbering: { reference: "numbers", level },
    children: [new TextRun({ text, font: FONT, size: 21, color: "333333" })],
  });
}

// Helper: checklist item
function check(text) {
  return new Paragraph({
    spacing: { after: 80, line: 280 },
    indent: { left: 360 },
    children: [new TextRun({ text: "\u2610 ", font: FONT, size: 22, color: COLOR_ACCENT }), new TextRun({ text, font: FONT, size: 21, color: "333333" })],
  });
}

// Helper: table
function makeTable(headers, rows, colWidths) {
  const totalWidth = colWidths.reduce((a, b) => a + b, 0);
  const headerRow = new TableRow({
    tableHeader: true,
    children: headers.map((h, i) => new TableCell({
      borders,
      width: { size: colWidths[i], type: WidthType.DXA },
      shading: { fill: COLOR_TABLE_HEADER, type: ShadingType.CLEAR },
      margins: cellMargins,
      verticalAlign: "center",
      children: [new Paragraph({ spacing: { after: 0, line: 260 }, children: [new TextRun({ text: h, font: FONT, size: 19, bold: true, color: COLOR_WHITE })] })],
    })),
  });
  const dataRows = rows.map((row, ri) => new TableRow({
    children: row.map((cell, i) => new TableCell({
      borders,
      width: { size: colWidths[i], type: WidthType.DXA },
      shading: ri % 2 === 0 ? { fill: COLOR_LIGHT_BG, type: ShadingType.CLEAR } : undefined,
      margins: cellMargins,
      children: [new Paragraph({ spacing: { after: 0, line: 260 }, children: [new TextRun({ text: cell, font: FONT, size: 19, color: "333333" })] })],
    })),
  }));
  return new Table({
    width: { size: totalWidth, type: WidthType.DXA },
    columnWidths: colWidths,
    rows: [headerRow, ...dataRows],
  });
}

// Build the document
const doc = new Document({
  styles: {
    default: {
      document: { run: { font: FONT, size: 21 } },
    },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: FONT, color: COLOR_MAIN },
        paragraph: { spacing: { before: 360, after: 200 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, font: FONT, color: COLOR_ACCENT },
        paragraph: { spacing: { before: 280, after: 160 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 23, bold: true, font: FONT, color: "2C3E50" },
        paragraph: { spacing: { before: 200, after: 120 }, outlineLevel: 2 } },
    ],
  },
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [
          { level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } } },
          { level: 1, format: LevelFormat.BULLET, text: "\u25E6", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 1080, hanging: 360 } } } },
        ],
      },
      {
        reference: "numbers",
        levels: [
          { level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } } },
        ],
      },
    ],
  },
  sections: [
    // ===== TITLE PAGE =====
    {
      properties: {
        page: {
          size: { width: 11906, height: 16838 },
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
        },
      },
      children: [
        new Paragraph({ spacing: { before: 3000 } }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 200 },
          children: [new TextRun({ text: "Claude Code \u00D7 \u30DE\u30CD\u30FC\u30D5\u30A9\u30EF\u30FC\u30C9", font: FONT, size: 44, bold: true, color: COLOR_MAIN })],
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 100 },
          children: [new TextRun({ text: "MCP\u9023\u643A \u5B8C\u5168\u30DE\u30CB\u30E5\u30A2\u30EB", font: FONT, size: 44, bold: true, color: COLOR_MAIN })],
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 600 },
          border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: COLOR_ACCENT, space: 8 } },
          children: [new TextRun({ text: "\u301C\u521D\u5FC3\u8005\u3067\u3082\u3067\u304D\u308B\uFF01AI\u3067\u4F1A\u8A08\u696D\u52D9\u3092\u9769\u65B0\u3059\u308B\u301C", font: FONT, size: 26, color: COLOR_ACCENT })],
        }),
        new Paragraph({ spacing: { before: 800 } }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 100 },
          children: [new TextRun({ text: "\u304A\u3082\u308D\u307E\u3061\u30E1\u30C7\u30A3\u30AB\u30EB\u30BB\u30F3\u30BF\u30FC", font: FONT, size: 24, color: COLOR_GRAY })],
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 100 },
          children: [new TextRun({ text: "\u4F5C\u6210\u65E5: 2026\u5E744\u67085\u65E5", font: FONT, size: 22, color: COLOR_GRAY })],
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [new TextRun({ text: "AI\u7BA1\u7406\u30EF\u30FC\u30AF\u30B9\u30DA\u30FC\u30B9", font: FONT, size: 20, color: COLOR_GRAY })],
        }),
      ],
    },
    // ===== MAIN CONTENT =====
    {
      properties: {
        page: {
          size: { width: 11906, height: 16838 },
          margin: { top: 1440, right: 1300, bottom: 1440, left: 1300 },
        },
      },
      headers: {
        default: new Header({
          children: [new Paragraph({
            alignment: AlignmentType.RIGHT,
            border: { bottom: { style: BorderStyle.SINGLE, size: 2, color: COLOR_ACCENT, space: 4 } },
            children: [new TextRun({ text: "Claude Code \u00D7 \u30DE\u30CD\u30FC\u30D5\u30A9\u30EF\u30FC\u30C9 MCP\u9023\u643A\u30DE\u30CB\u30E5\u30A2\u30EB", font: FONT, size: 16, color: COLOR_GRAY })],
          })],
        }),
      },
      footers: {
        default: new Footer({
          children: [new Paragraph({
            alignment: AlignmentType.CENTER,
            border: { top: { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC", space: 4 } },
            children: [
              new TextRun({ text: "\u304A\u3082\u308D\u307E\u3061\u30E1\u30C7\u30A3\u30AB\u30EB\u30BB\u30F3\u30BF\u30FC AI\u7BA1\u7406\u30EF\u30FC\u30AF\u30B9\u30DA\u30FC\u30B9  |  ", font: FONT, size: 16, color: COLOR_GRAY }),
              new TextRun({ text: "Page ", font: FONT, size: 16, color: COLOR_GRAY }),
              new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 16, color: COLOR_GRAY }),
            ],
          })],
        }),
      },
      children: [
        // ===== 1. はじめに =====
        h1("1. \u306F\u3058\u3081\u306B \u2014 MCP\u3068\u306F\u4F55\u304B\uFF1F"),

        h2("1.1 MCP\u306E\u6982\u8981"),
        p("MCP\uFF08Model Context Protocol\uFF09\u3068\u306F\u3001AI\u30A2\u30B7\u30B9\u30BF\u30F3\u30C8\uFF08Claude\u7B49\uFF09\u304C\u5916\u90E8\u30B5\u30FC\u30D3\u30B9\u306E\u30C7\u30FC\u30BF\u306B\u76F4\u63A5\u30A2\u30AF\u30BB\u30B9\u3067\u304D\u308B\u3088\u3046\u306B\u3059\u308B\u6A19\u6E96\u30D7\u30ED\u30C8\u30B3\u30EB\u3067\u3059\u3002"),

        pRuns([{ text: "\u5F93\u6765\u306E\u65B9\u6CD5\uFF1A", bold: true, color: COLOR_GRAY, size: 20 }], { beforeSpacing: 120 }),
        p("\u4F1A\u8A08\u30BD\u30D5\u30C8\u3092\u958B\u304F \u2192 \u30C7\u30FC\u30BF\u3092\u30B3\u30D4\u30FC \u2192 AI\u306B\u8CBC\u308A\u4ED8\u3051\u3066\u8CEA\u554F \u2192 \u56DE\u7B54\u3092\u78BA\u8A8D", { indent: 360, color: COLOR_GRAY }),

        pRuns([{ text: "MCP\u9023\u643A\u5F8C\uFF1A", bold: true, color: COLOR_ACCENT, size: 20 }], { beforeSpacing: 120 }),
        p("AI\u306B\u81EA\u7136\u8A00\u8A9E\u3067\u8CEA\u554F\u3059\u308B\u3060\u3051\u3067\u3001\u4F1A\u8A08\u30C7\u30FC\u30BF\u3092\u76F4\u63A5\u53C2\u7167\u30FB\u5206\u6790\u30FB\u5165\u529B", { indent: 360, color: COLOR_ACCENT }),

        h2("1.2 \u4F55\u304C\u3067\u304D\u308B\u3088\u3046\u306B\u306A\u308B\u306E\u304B\uFF1F"),
        p("MCP\u3092\u8A2D\u5B9A\u3059\u308B\u3068\u3001Claude Code\u3084Claude Desktop\u304B\u3089\u4EE5\u4E0B\u306E\u3053\u3068\u304C\u53EF\u80FD\u306B\u306A\u308A\u307E\u3059\uFF1A"),

        makeTable(
          ["\u3067\u304D\u308B\u3053\u3068", "\u5177\u4F53\u4F8B"],
          [
            ["\u4ED5\u8A33\u306E\u7167\u4F1A", "\u300C\u4ECA\u6708\u306E\u4EA4\u969B\u8CBB\u306E\u4ED5\u8A33\u3092\u5168\u90E8\u898B\u305B\u3066\u300D"],
            ["\u4ED5\u8A33\u306E\u767B\u9332", "\u300C4\u67081\u65E5\u306B\u6D88\u8017\u54C1\u8CBB5,000\u5186\u3092\u73FE\u91D1\u3067\u8A08\u4E0A\u3057\u3066\u300D"],
            ["\u8A66\u7B97\u8868\u306E\u78BA\u8A8D", "\u300C\u4ECA\u671F\u306E\u640D\u76CA\u8A08\u7B97\u66F8\u3092\u898B\u305B\u3066\u300D"],
            ["\u6708\u6B21\u63A8\u79FB\u306E\u5206\u6790", "\u300C\u58F2\u4E0A\u306E\u6708\u6B21\u63A8\u79FB\u3092\u30B0\u30E9\u30D5\u306B\u3057\u3066\u300D"],
            ["\u52D8\u5B9A\u79D1\u76EE\u306E\u78BA\u8A8D", "\u300C\u4F7F\u3048\u308B\u52D8\u5B9A\u79D1\u76EE\u306E\u4E00\u89A7\u3092\u51FA\u3057\u3066\u300D"],
            ["\u53D6\u5F15\u5148\u306E\u7BA1\u7406", "\u300C\u65B0\u3057\u3044\u53D6\u5F15\u5148\u3092\u767B\u9332\u3057\u3066\u300D"],
            ["\u90E8\u9580\u5225\u5206\u6790", "\u300C\u90E8\u9580\u3054\u3068\u306E\u7D4C\u8CBB\u3092\u6BD4\u8F03\u3057\u3066\u300D"],
          ],
          [3500, 5800]
        ),

        new Paragraph({ children: [new PageBreak()] }),

        // ===== 2. 全体像 =====
        h1("2. \u30DE\u30CD\u30FC\u30D5\u30A9\u30EF\u30FC\u30C9MCP\u306E\u5168\u4F53\u50CF"),

        h2("2.1 \u5229\u7528\u3067\u304D\u308BMCP\u30B5\u30FC\u30D0\u30FC\u4E00\u89A7"),

        makeTable(
          ["\u30B5\u30FC\u30D0\u30FC\u540D", "\u5BFE\u8C61\u30B5\u30FC\u30D3\u30B9", "\u516C\u5F0F/\u975E\u516C\u5F0F", "\u96E3\u6613\u5EA6", "\u304A\u3059\u3059\u3081"],
          [
            ["MF\u30AF\u30E9\u30A6\u30C9\u4F1A\u8A08\u516C\u5F0FMCP", "\u30AF\u30E9\u30A6\u30C9\u4F1A\u8A08/\u78BA\u5B9A\u7533\u544A", "\u2605\u516C\u5F0F", "\u2605\u2606\u2606\uFF08\u7C21\u5358\uFF09", "\u2605\u2605\u2605"],
            ["Admina MCP Server", "IT\u8CC7\u7523\u7BA1\u7406", "\u2605\u516C\u5F0F", "\u2605\u2605\u2606\uFF08\u666E\u901A\uFF09", "\u2605\u2605\u2606"],
            ["MF AI Bridge", "ME/\u4F1A\u8A08/\u7D66\u4E0E", "\u975E\u516C\u5F0F", "\u2605\u2605\u2605\uFF08\u3084\u3084\u96E3\uFF09", "\u2605\u2605\u2606"],
            ["mf-dashboard", "MoneyForward ME", "\u975E\u516C\u5F0F", "\u2605\u2605\u2605\uFF08\u3084\u3084\u96E3\uFF09", "\u2605\u2606\u2606"],
            ["CData Connect AI\u7D4C\u7531", "\u30AF\u30E9\u30A6\u30C9\u7D4C\u8CBB", "\u30B5\u30FC\u30C9\u30D1\u30FC\u30C6\u30A3", "\u2605\u2605\u2606\uFF08\u666E\u901A\uFF09", "\u2605\u2606\u2606"],
          ],
          [2200, 2000, 1600, 1700, 1800]
        ),

        h2("2.2 \u672C\u30DE\u30CB\u30E5\u30A2\u30EB\u306E\u5BFE\u8C61"),
        p("\u672C\u30DE\u30CB\u30E5\u30A2\u30EB\u3067\u306F\u3001\u6700\u3082\u304A\u3059\u3059\u3081\u306E\u300C\u30DE\u30CD\u30FC\u30D5\u30A9\u30EF\u30FC\u30C9 \u30AF\u30E9\u30A6\u30C9\u4F1A\u8A08 \u516C\u5F0FMCP\u30B5\u30FC\u30D0\u30FC\u300D\u306E\u30BB\u30C3\u30C8\u30A2\u30C3\u30D7\u3092\u4E2D\u5FC3\u306B\u89E3\u8AAC\u3057\u307E\u3059\u30022026\u5E743\u670826\u65E5\u3088\u308A\u5168\u30D7\u30E9\u30F3\u3067\u6B63\u5F0F\u63D0\u4F9B\u304C\u958B\u59CB\u3055\u308C\u305F\u516C\u5F0F\u30B5\u30FC\u30D3\u30B9\u3067\u3059\u3002"),

        new Paragraph({ children: [new PageBreak()] }),

        // ===== 3. 事前準備 =====
        h1("3. \u4E8B\u524D\u6E96\u5099"),

        h2("3.1 \u5FC5\u8981\u306A\u3082\u306E\uFF08\u30C1\u30A7\u30C3\u30AF\u30EA\u30B9\u30C8\uFF09"),
        check("\u30DE\u30CD\u30FC\u30D5\u30A9\u30EF\u30FC\u30C9 \u30AF\u30E9\u30A6\u30C9\u4F1A\u8A08\u306E\u30A2\u30AB\u30A6\u30F3\u30C8\uFF08\u3069\u306E\u30D7\u30E9\u30F3\u3067\u3082OK\uFF09"),
        check("\u300C\u5168\u6A29\u7BA1\u7406\u300D\u6A29\u9650\u3092\u6301\u3064\u30E6\u30FC\u30B6\u30FC\u30A2\u30AB\u30A6\u30F3\u30C8\uFF08\u521D\u56DE\u8A2D\u5B9A\u6642\u306B\u5FC5\u8981\uFF09"),
        check("Claude Desktop \u30A2\u30D7\u30EA\uFF08Mac\u7248 \u307E\u305F\u306F Windows\u7248\uFF09\u307E\u305F\u306F Claude Code\uFF08\u30BF\u30FC\u30DF\u30CA\u30EB\uFF09"),
        check("\u30A4\u30F3\u30BF\u30FC\u30CD\u30C3\u30C8\u63A5\u7D9A\u74B0\u5883"),
        check("Web\u30D6\u30E9\u30A6\u30B6\uFF08Chrome\u63A8\u5968\uFF09"),

        h2("3.2 \u6240\u8981\u6642\u9593\u306E\u76EE\u5B89"),
        bullet("\u521D\u56DE\u30BB\u30C3\u30C8\u30A2\u30C3\u30D7: \u7D0415\u301C20\u5206"),
        bullet("2\u56DE\u76EE\u4EE5\u964D\u306E\u8A8D\u8A3C: \u7D042\u5206"),

        new Paragraph({ children: [new PageBreak()] }),

        // ===== 4. セットアップ手順 =====
        h1("4. \u30BB\u30C3\u30C8\u30A2\u30C3\u30D7\u624B\u9806\uFF08\u30AF\u30E9\u30A6\u30C9\u4F1A\u8A08 \u516C\u5F0FMCP\uFF09"),

        h2("4.1 \u30B9\u30C6\u30C3\u30D71: \u30A2\u30D7\u30EA\u30DD\u30FC\u30BF\u30EB\u306E\u5229\u7528\u958B\u59CB"),
        pRuns([{ text: "\u3010\u64CD\u4F5C\u3059\u308B\u4EBA\u3011", bold: true, color: COLOR_MAIN }, { text: " \u5168\u6A29\u7BA1\u7406\u8005" }]),
        p(""),
        numbered("\u30DE\u30CD\u30FC\u30D5\u30A9\u30EF\u30FC\u30C9 \u30AF\u30E9\u30A6\u30C9\u306B\u30ED\u30B0\u30A4\u30F3"),
        numbered("\u5DE6\u30E1\u30CB\u30E5\u30FC\u304B\u3089\u300C\u7BA1\u7406\u8A2D\u5B9A\u300D\u3092\u30AF\u30EA\u30C3\u30AF"),
        numbered("\u300C\u30A2\u30D7\u30EA\u30DD\u30FC\u30BF\u30EB\u300D\u3092\u30AF\u30EA\u30C3\u30AF"),
        numbered("\u300C\u5229\u7528\u3092\u958B\u59CB\u3059\u308B\u300D\u30DC\u30BF\u30F3\u3092\u30AF\u30EA\u30C3\u30AF"),
        numbered("\u5229\u7528\u898F\u7D04\u3092\u78BA\u8A8D\u3057\u3001\u300C\u540C\u610F\u3057\u3066\u958B\u59CB\u300D\u3092\u30AF\u30EA\u30C3\u30AF"),
        tip("\u3053\u306E\u64CD\u4F5C\u306F\u5168\u6A29\u7BA1\u7406\u8005\u306E\u307F\u5B9F\u884C\u53EF\u80FD\u3067\u3059\u3002\u4E00\u822C\u30E6\u30FC\u30B6\u30FC\u3067\u306F\u8A2D\u5B9A\u753B\u9762\u304C\u8868\u793A\u3055\u308C\u307E\u305B\u3093\u3002"),

        h2("4.2 \u30B9\u30C6\u30C3\u30D72: \u30E6\u30FC\u30B6\u30FC\u3078\u306E\u6A29\u9650\u4ED8\u4E0E"),
        pRuns([{ text: "\u3010\u64CD\u4F5C\u3059\u308B\u4EBA\u3011", bold: true, color: COLOR_MAIN }, { text: " \u5168\u6A29\u7BA1\u7406\u8005" }]),
        p(""),
        numbered("\u300C\u7BA1\u7406\u8A2D\u5B9A\u300D\u2192\u300C\u30A2\u30D7\u30EA\u30DD\u30FC\u30BF\u30EB\u300D\u2192\u300C\u30E6\u30FC\u30B6\u30FC\u7BA1\u7406\u300D"),
        numbered("MCP\u9023\u643A\u3092\u5229\u7528\u3055\u305B\u305F\u3044\u30E6\u30FC\u30B6\u30FC\u3092\u9078\u629E"),
        numbered("\u300CMCP\u30B5\u30FC\u30D0\u30FC\u5229\u7528\u300D\u306E\u6A29\u9650\u3092\u4ED8\u4E0E"),
        numbered("\u300C\u4FDD\u5B58\u300D\u3092\u30AF\u30EA\u30C3\u30AF"),

        h2("4.3 \u30B9\u30C6\u30C3\u30D73: Claude Desktop\u3067\u306E\u63A5\u7D9A\u8A2D\u5B9A"),

        h3("\u65B9\u6CD5A: UI\u304B\u3089\u8A2D\u5B9A\u3059\u308B\u65B9\u6CD5\uFF08\u63A8\u5968\u30FB\u7C21\u5358\uFF09"),
        numbered("Claude Desktop\u3092\u958B\u304F"),
        numbered("\u5DE6\u4E0A\u306E\u30E1\u30CB\u30E5\u30FC\u300CClaude\u300D\u2192\u300CSettings...\u300D\u3092\u30AF\u30EA\u30C3\u30AF"),
        numbered("\u300CIntegrations\u300D\u30BF\u30D6\u3092\u30AF\u30EA\u30C3\u30AF"),
        numbered("\u300CAdd custom connector\u300D\u3092\u30AF\u30EA\u30C3\u30AF"),
        numbered("\u4EE5\u4E0B\u3092\u5165\u529B\uFF1A"),
        p("Name: MoneyForward Cloud Accounting", { indent: 720 }),
        p("URL: https://mcp.moneyforward.com/sse", { indent: 720 }),
        numbered("\u300CAdd\u300D\u3092\u30AF\u30EA\u30C3\u30AF"),
        numbered("Claude Desktop\u3092\u518D\u8D77\u52D5"),

        h3("\u65B9\u6CD5B: \u8A2D\u5B9A\u30D5\u30A1\u30A4\u30EB\u3092\u76F4\u63A5\u7DE8\u96C6\u3059\u308B\u65B9\u6CD5"),
        p("\u8A2D\u5B9A\u30D5\u30A1\u30A4\u30EB\u306E\u5834\u6240\uFF1A"),
        bullet("Mac: ~/Library/Application Support/Claude/claude_desktop_config.json"),
        bullet("Windows: %APPDATA%\\Claude\\claude_desktop_config.json"),
        p("\u4EE5\u4E0B\u306EJSON\u3092\u8FFD\u8A18\uFF1A", { beforeSpacing: 120 }),
        code("{"),
        code('  "mcpServers": {'),
        code('    "moneyforward-cloud-accounting": {'),
        code('      "url": "https://mcp.moneyforward.com/sse"'),
        code("    }"),
        code("  }"),
        code("}"),
        p("\u4FDD\u5B58\u5F8C\u3001Claude Desktop\u3092\u518D\u8D77\u52D5\u3057\u3066\u304F\u3060\u3055\u3044\u3002", { beforeSpacing: 120 }),

        h2("4.4 \u30B9\u30C6\u30C3\u30D74: Claude Code\u3067\u306E\u63A5\u7D9A\u8A2D\u5B9A"),
        p("\u30BF\u30FC\u30DF\u30CA\u30EB\u3067\u4EE5\u4E0B\u306E\u30B3\u30DE\u30F3\u30C9\u3092\u5B9F\u884C\uFF1A"),
        code("claude mcp add moneyforward-cloud-accounting \\"),
        code("  --transport sse https://mcp.moneyforward.com/sse"),
        p("\u307E\u305F\u306F\u3001\u30D7\u30ED\u30B8\u30A7\u30AF\u30C8\u306E .claude/settings.json \u306B\u8FFD\u8A18\uFF1A", { beforeSpacing: 120 }),
        code("{"),
        code('  "mcpServers": {'),
        code('    "moneyforward-cloud-accounting": {'),
        code('      "url": "https://mcp.moneyforward.com/sse"'),
        code("    }"),
        code("  }"),
        code("}"),

        h2("4.5 \u30B9\u30C6\u30C3\u30D75: \u521D\u56DE\u8A8D\u8A3C\uFF08OAuth\u8A8D\u8A3C\uFF09"),
        numbered("Claude\uFF08Desktop\u307E\u305F\u306FCode\uFF09\u3067\u300C\u30DE\u30CD\u30FC\u30D5\u30A9\u30EF\u30FC\u30C9\u306B\u63A5\u7D9A\u3057\u3066\u300D\u3068\u5165\u529B"),
        numbered("Claude\u304C\u8A8D\u8A3CURL\u3092\u751F\u6210\u3059\u308B\u306E\u3067\u3001\u30D6\u30E9\u30A6\u30B6\u3067\u958B\u304F"),
        numbered("\u30DE\u30CD\u30FC\u30D5\u30A9\u30EF\u30FC\u30C9\u306E\u30ED\u30B0\u30A4\u30F3\u753B\u9762\u304C\u8868\u793A\u3055\u308C\u308B"),
        numbered("\u30ED\u30B0\u30A4\u30F3\u3057\u3001\u300C\u8A31\u53EF\u3059\u308B\u300D\u3092\u30AF\u30EA\u30C3\u30AF"),
        numbered("\u8A8D\u8A3C\u30B3\u30FC\u30C9\u304C\u8868\u793A\u3055\u308C\u308B\u306E\u3067\u3001\u30B3\u30D4\u30FC"),
        numbered("Claude\u306B\u8A8D\u8A3C\u30B3\u30FC\u30C9\u3092\u4F1D\u3048\u308B"),
        numbered("\u300C\u8A8D\u8A3C\u304C\u5B8C\u4E86\u3057\u307E\u3057\u305F\u300D\u3068\u8868\u793A\u3055\u308C\u308C\u3070\u6210\u529F\uFF01"),
        tip("\u8A8D\u8A3C\u306F\u4E00\u5B9A\u671F\u9593\u6709\u52B9\u3067\u3059\u3002\u671F\u9650\u5207\u308C\u306B\u306A\u3063\u305F\u5834\u5408\u306F\u518D\u5EA6\u540C\u3058\u624B\u9806\u3067\u8A8D\u8A3C\u3057\u307E\u3059\u3002"),

        new Paragraph({ children: [new PageBreak()] }),

        // ===== 5. 機能一覧 =====
        h1("5. \u4F7F\u3048\u308B\u6A5F\u80FD\u4E00\u89A7\uFF0817\u30C4\u30FC\u30EB\uFF09"),
        p("\u516C\u5F0FMCP\u30B5\u30FC\u30D0\u30FC\u304C\u63D0\u4F9B\u3059\u308B17\u500B\u306E\u30C4\u30FC\u30EB\u306E\u5168\u4E00\u89A7\u3067\u3059\u3002"),

        makeTable(
          ["\u30AB\u30C6\u30B4\u30EA", "\u30C4\u30FC\u30EB\u540D", "\u6A5F\u80FD", "\u4F7F\u3044\u65B9\u306E\u4F8B"],
          [
            ["\u8A8D\u8A3C", "mfc_ca_authorize", "\u8A8D\u8A3CURL\u751F\u6210", "\uFF08\u81EA\u52D5\u5B9F\u884C\uFF09"],
            ["\u8A8D\u8A3C", "mfc_ca_exchange", "\u30C8\u30FC\u30AF\u30F3\u4EA4\u63DB", "\uFF08\u81EA\u52D5\u5B9F\u884C\uFF09"],
            ["\u57FA\u672C\u60C5\u5831", "mfc_ca_currentOffice", "\u4E8B\u696D\u8005\u60C5\u5831\u53D6\u5F97", "\u300C\u4E8B\u696D\u8005\u60C5\u5831\u3092\u8868\u793A\u3057\u3066\u300D"],
            ["\u4ED5\u8A33", "mfc_ca_getJournals", "\u4ED5\u8A33\u4E00\u89A7\u53D6\u5F97", "\u300C\u4ECA\u6708\u306E\u4ED5\u8A33\u3092\u898B\u305B\u3066\u300D"],
            ["\u4ED5\u8A33", "mfc_ca_getJournalById", "\u4ED5\u8A331\u4EF6\u53D6\u5F97", "\u300C\u4ED5\u8A33\u756A\u53F7123\u306E\u8A73\u7D30\u300D"],
            ["\u4ED5\u8A33", "mfc_ca_postJournals", "\u4ED5\u8A33\u767B\u9332", "\u300C\u6D88\u8017\u54C1\u8CBB5,000\u5186\u3092\u767B\u9332\u300D"],
            ["\u4ED5\u8A33", "mfc_ca_putJournals", "\u4ED5\u8A33\u66F4\u65B0", "\u300C\u4ED5\u8A33123\u306E\u91D1\u984D\u3092\u4FEE\u6B63\u300D"],
            ["\u8A66\u7B97\u8868", "getReportsTrialBalance BS", "\u6B8B\u9AD8\u8A66\u7B97\u8868BS", "\u300C\u8CB8\u501F\u5BFE\u7167\u8868\u3092\u898B\u305B\u3066\u300D"],
            ["\u8A66\u7B97\u8868", "getReportsTrialBalance PL", "\u6B8B\u9AD8\u8A66\u7B97\u8868PL", "\u300C\u640D\u76CA\u8A08\u7B97\u66F8\u3092\u898B\u305B\u3066\u300D"],
            ["\u63A8\u79FB\u8868", "getReportsTransition BS", "\u63A8\u79FB\u8868BS", "\u300C\u8CC7\u7523\u306E\u6708\u6B21\u63A8\u79FB\u300D"],
            ["\u63A8\u79FB\u8868", "getReportsTransition PL", "\u63A8\u79FB\u8868PL", "\u300C\u58F2\u4E0A\u306E\u6708\u6B21\u63A8\u79FB\u300D"],
            ["\u30DE\u30B9\u30BF", "mfc_ca_getAccounts", "\u52D8\u5B9A\u79D1\u76EE\u4E00\u89A7", "\u300C\u52D8\u5B9A\u79D1\u76EE\u3092\u4E00\u89A7\u3067\u300D"],
            ["\u30DE\u30B9\u30BF", "mfc_ca_getSubAccounts", "\u88DC\u52A9\u79D1\u76EE\u4E00\u89A7", "\u300C\u88DC\u52A9\u79D1\u76EE\u3092\u898B\u305B\u3066\u300D"],
            ["\u30DE\u30B9\u30BF", "mfc_ca_getDepartments", "\u90E8\u9580\u4E00\u89A7", "\u300C\u90E8\u9580\u4E00\u89A7\u3092\u51FA\u3057\u3066\u300D"],
            ["\u30DE\u30B9\u30BF", "mfc_ca_getTaxes", "\u7A0E\u533A\u5206\u4E00\u89A7", "\u300C\u7A0E\u533A\u5206\u3092\u78BA\u8A8D\u3057\u3066\u300D"],
            ["\u53D6\u5F15\u5148", "mfc_ca_getTradePartners", "\u53D6\u5F15\u5148\u4E00\u89A7", "\u300C\u53D6\u5F15\u5148\u3092\u4E00\u89A7\u3067\u300D"],
            ["\u53D6\u5F15\u5148", "mfc_ca_postTradePartners", "\u53D6\u5F15\u5148\u767B\u9332", "\u300C\u53D6\u5F15\u5148\u3092\u65B0\u898F\u767B\u9332\u300D"],
          ],
          [1200, 2800, 2000, 3300]
        ),

        new Paragraph({ children: [new PageBreak()] }),

        // ===== 6. 活用シナリオ集 =====
        h1("6. \u6D3B\u7528\u30B7\u30CA\u30EA\u30AA\u96C6 \u2014 \u3053\u3046\u4F7F\u3046\u3068\u4FBF\u5229\uFF01"),

        h2("\u30B7\u30CA\u30EA\u30AA1: \u6708\u6B21\u6C7A\u7B97\u306E\u9AD8\u901F\u30C1\u30A7\u30C3\u30AF"),
        pRuns([{ text: "\u5165\u529B\u4F8B\uFF1A", bold: true }], { beforeSpacing: 60 }),
        p("\u300C\u4ECA\u6708\u306E\u640D\u76CA\u8A08\u7B97\u66F8\u3092\u898B\u305B\u3066\u3002\u524D\u6708\u3068\u6BD4\u8F03\u3057\u3066\u5927\u304D\u304F\u5909\u52D5\u3057\u305F\u79D1\u76EE\u304C\u3042\u308C\u3070\u6559\u3048\u3066\u300D", { indent: 360, italics: true }),
        p("AI\u304C\u8A66\u7B97\u8868\u3092\u53D6\u5F97\u3057\u3001\u524D\u6708\u6BD4\u3067\u7570\u5E38\u5024\u3092\u81EA\u52D5\u691C\u51FA\u3057\u3066\u304F\u308C\u307E\u3059\u3002", { indent: 360, color: COLOR_GRAY }),

        h2("\u30B7\u30CA\u30EA\u30AA2: \u4ED5\u8A33\u306E\u4E00\u62EC\u78BA\u8A8D\u3068\u4FEE\u6B63"),
        pRuns([{ text: "\u5165\u529B\u4F8B\uFF1A", bold: true }], { beforeSpacing: 60 }),
        p("\u300C\u4ECA\u6708\u306E\u4EA4\u969B\u8CBB\u306E\u4ED5\u8A33\u3092\u5168\u90E8\u898B\u305B\u3066\u3002\u6458\u8981\u306B\u76F8\u624B\u5148\u540D\u304C\u5165\u3063\u3066\u3044\u306A\u3044\u3082\u306E\u304C\u3042\u308C\u3070\u6559\u3048\u3066\u300D", { indent: 360, italics: true }),
        p("\u4ED5\u8A33\u4E00\u89A7\u3092\u53D6\u5F97\u3057\u3001\u5165\u529B\u6F0F\u308C\u3092\u81EA\u52D5\u30C1\u30A7\u30C3\u30AF\u3002", { indent: 360, color: COLOR_GRAY }),

        h2("\u30B7\u30CA\u30EA\u30AA3: \u7D4C\u8CBB\u5206\u6790\u30EC\u30DD\u30FC\u30C8\u306E\u81EA\u52D5\u4F5C\u6210"),
        pRuns([{ text: "\u5165\u529B\u4F8B\uFF1A", bold: true }], { beforeSpacing: 60 }),
        p("\u300C\u4ECA\u671F\u306E\u90E8\u9580\u5225\u7D4C\u8CBB\u3092\u6BD4\u8F03\u3059\u308B\u30EC\u30DD\u30FC\u30C8\u3092Word\u3067\u4F5C\u6210\u3057\u3066\u300D", { indent: 360, italics: true }),
        p("\u90E8\u9580\u4E00\u89A7\u3068\u640D\u76CA\u30C7\u30FC\u30BF\u3092\u53D6\u5F97\u3057\u3001\u5206\u6790\u30EC\u30DD\u30FC\u30C8\u3092\u81EA\u52D5\u751F\u6210\u3002", { indent: 360, color: COLOR_GRAY }),

        h2("\u30B7\u30CA\u30EA\u30AA4: \u4ED5\u8A33\u306E\u81EA\u7136\u8A00\u8A9E\u767B\u9332"),
        pRuns([{ text: "\u5165\u529B\u4F8B\uFF1A", bold: true }], { beforeSpacing: 60 }),
        p("\u300C4\u67081\u65E5\u3001\u6D88\u8017\u54C1\u8CBB\u30675,000\u5186\u3001\u73FE\u91D1\u6255\u3044\u3001\u6458\u8981\u306F\u30B3\u30D4\u30FC\u7528\u7D19\u8CFC\u5165\u300D", { indent: 360, italics: true }),
        p("\u81EA\u7136\u8A00\u8A9E\u304B\u3089\u4ED5\u8A33\u30C7\u30FC\u30BF\u3092\u7D44\u307F\u7ACB\u3066\u3066\u767B\u9332\u3002", { indent: 360, color: COLOR_GRAY }),

        h2("\u30B7\u30CA\u30EA\u30AA5: \u7A0E\u52D9\u7533\u544A\u306E\u6E96\u5099\u30B5\u30DD\u30FC\u30C8"),
        pRuns([{ text: "\u5165\u529B\u4F8B\uFF1A", bold: true }], { beforeSpacing: 60 }),
        p("\u300C\u4ECA\u671F\u306E\u52D8\u5B9A\u79D1\u76EE\u3054\u3068\u306E\u5E74\u9593\u5408\u8A08\u3092\u51FA\u3057\u3066\u3002\u6D88\u8CBB\u7A0E\u306E\u8AB2\u7A0E/\u975E\u8AB2\u7A0E\u3082\u533A\u5206\u3057\u3066\u300D", { indent: 360, italics: true }),
        p("\u8A66\u7B97\u8868\u3068\u7A0E\u533A\u5206\u30C7\u30FC\u30BF\u3092\u7D44\u307F\u5408\u308F\u305B\u3066\u96C6\u8A08\u3002", { indent: 360, color: COLOR_GRAY }),

        h2("\u30B7\u30CA\u30EA\u30AA6: \u30AD\u30E3\u30C3\u30B7\u30E5\u30D5\u30ED\u30FC\u5206\u6790"),
        pRuns([{ text: "\u5165\u529B\u4F8B\uFF1A", bold: true }], { beforeSpacing: 60 }),
        p("\u300C\u904E\u53BB6\u30F6\u6708\u306E\u73FE\u91D1\u30FB\u9810\u91D1\u306E\u63A8\u79FB\u3092\u6708\u5225\u3067\u898B\u305B\u3066\u3002\u5927\u304D\u306A\u5165\u51FA\u91D1\u304C\u3042\u3063\u305F\u6708\u306F\u8A73\u7D30\u3082\u6559\u3048\u3066\u300D", { indent: 360, italics: true }),
        p("\u63A8\u79FB\u8868BS\u304B\u3089\u73FE\u9810\u91D1\u306E\u63A8\u79FB\u3092\u62BD\u51FA\u3057\u3001\u7570\u5E38\u6708\u306E\u4ED5\u8A33\u3092\u6DF1\u6398\u308A\u3002", { indent: 360, color: COLOR_GRAY }),

        h2("\u30B7\u30CA\u30EA\u30AA7: \u75C5\u9662\u7D4C\u55B6\u3078\u306E\u5FDC\u7528\uFF08\u533B\u7642\u6A5F\u95A2\u5411\u3051\uFF09"),
        pRuns([{ text: "\u5165\u529B\u4F8B\uFF1A", bold: true }], { beforeSpacing: 60 }),
        p("\u300C\u4ECA\u6708\u306E\u533B\u696D\u53CE\u76CA\u3068\u533B\u696D\u8CBB\u7528\u306E\u5185\u8A33\u3092\u90E8\u9580\u5225\u306B\u51FA\u3057\u3066\u3002\u75C5\u5E8A\u7A3C\u50CD\u7387\u3068\u306E\u76F8\u95A2\u3092\u5206\u6790\u3057\u3066\u300D", { indent: 360, italics: true }),
        p("\u4F1A\u8A08\u30C7\u30FC\u30BF\u3068\u30D9\u30C3\u30C9\u30B3\u30F3\u30C8\u30ED\u30FC\u30EB\u30C7\u30FC\u30BF\u3092\u6A2A\u65AD\u7684\u306B\u5206\u6790\u3002", { indent: 360, color: COLOR_GRAY }),

        new Paragraph({ children: [new PageBreak()] }),

        // ===== 7. 注意点とTips =====
        h1("7. \u77E5\u3063\u3066\u304A\u304D\u305F\u3044\u6CE8\u610F\u70B9\u3068Tips"),

        h2("7.1 API\u306E\u5236\u9650\u4E8B\u9805"),
        bullet("1\u56DE\u306E\u30EA\u30AF\u30A8\u30B9\u30C8\u3067\u53D6\u5F97\u3067\u304D\u308B\u4ED5\u8A33\u6570\u306B\u4E0A\u9650\u304C\u3042\u308B\u5834\u5408\u304C\u3042\u308A\u307E\u3059"),
        bullet("\u5927\u91CF\u30C7\u30FC\u30BF\u306E\u53D6\u5F97\u6642\u306F\u671F\u9593\u3092\u7D5E\u3063\u3066\u691C\u7D22\u3057\u3066\u304F\u3060\u3055\u3044"),
        bullet("\u4ED5\u8A33\u306E\u524A\u9664\u306FMCP\u7D4C\u7531\u3067\u306F\u3067\u304D\u307E\u305B\u3093\uFF08\u767B\u9332\u30FB\u66F4\u65B0\u306E\u307F\uFF09"),

        h2("7.2 \u30BB\u30AD\u30E5\u30EA\u30C6\u30A3\u306B\u95A2\u3059\u308B\u6CE8\u610F"),
        bullet("OAuth\u8A8D\u8A3C\u306E\u30C8\u30FC\u30AF\u30F3\u306F\u5B89\u5168\u306B\u7BA1\u7406\u3055\u308C\u307E\u3059"),
        bullet("\u4F1A\u8A08\u30C7\u30FC\u30BF\u306F\u6A5F\u5BC6\u6027\u304C\u9AD8\u3044\u305F\u3081\u3001\u5171\u6709PC\u3067\u306E\u5229\u7528\u306F\u907F\u3051\u3066\u304F\u3060\u3055\u3044"),
        bullet("\u4ED5\u8A33\u306E\u767B\u9332\u30FB\u66F4\u65B0\u306F\u53D6\u308A\u6D88\u3057\u304C\u96E3\u3057\u3044\u305F\u3081\u3001\u78BA\u8A8D\u3057\u3066\u304B\u3089\u5B9F\u884C\u3057\u307E\u3057\u3087\u3046"),

        h2("7.3 \u77E5\u3063\u3066\u304A\u304F\u3068\u4FBF\u5229\u306ATips"),
        numbered("\u671F\u9593\u6307\u5B9A\u306E\u30B3\u30C4: \u300C2026\u5E744\u6708\u306E\u301C\u300D\u306E\u3088\u3046\u306B\u5E74\u6708\u3092\u660E\u793A\u3059\u308B\u3068\u6B63\u78BA"),
        numbered("\u52D8\u5B9A\u79D1\u76EE\u540D: \u6B63\u5F0F\u540D\u79F0\u3067\u306A\u304F\u3066\u3082\u3001AI\u304C\u9069\u5207\u306A\u79D1\u76EE\u3092\u63A8\u6E2C\u3057\u3066\u304F\u308C\u307E\u3059"),
        numbered("\u30A8\u30E9\u30FC\u6642: \u300C\u3082\u3046\u4E00\u5EA6\u8A8D\u8A3C\u3057\u3066\u300D\u3068\u8A00\u3048\u3070\u518D\u8A8D\u8A3C\u3067\u304D\u307E\u3059"),
        numbered("\u5927\u91CF\u30C7\u30FC\u30BF: \u300CCSV\u3067\u51FA\u529B\u3057\u3066\u300D\u3068\u8A00\u3048\u3070\u3001\u30C7\u30FC\u30BF\u3092\u30D5\u30A1\u30A4\u30EB\u306B\u4FDD\u5B58\u53EF\u80FD"),

        new Paragraph({ children: [new PageBreak()] }),

        // ===== 8. 家計データ活用ヒント＆事例集 =====
        h1("8. \u5BB6\u8A08\u30C7\u30FC\u30BF\u6D3B\u7528\u30D2\u30F3\u30C8\uFF06\u4E8B\u4F8B\u96C6"),
        p("MoneyForward ME\u306E\u5BB6\u8A08\u30C7\u30FC\u30BF\u3092MCP\u7D4C\u7531\u3067AI\u306B\u63A5\u7D9A\u3059\u308B\u3068\u3001\u5358\u306A\u308B\u5BB6\u8A08\u7C3F\u3092\u8D85\u3048\u305F\u300C\u30D1\u30FC\u30BD\u30CA\u30EB\u30D5\u30A1\u30A4\u30CA\u30F3\u30B9AI\u300D\u304C\u5B9F\u73FE\u3057\u307E\u3059\u3002\u3053\u3053\u3067\u306F\u3001\u5177\u4F53\u7684\u306A\u6D3B\u7528\u30D2\u30F3\u30C8\u3068\u4E8B\u4F8B\u3092\u7D39\u4ECB\u3057\u307E\u3059\u3002"),

        h2("8.1 \u6BCE\u6708\u306E\u5BB6\u8A08\u30EC\u30D3\u30E5\u30FC\u3092\u81EA\u52D5\u5316"),
        pRuns([{ text: "\u5165\u529B\u4F8B\uFF1A", bold: true }], { beforeSpacing: 60 }),
        p("\u300C\u5148\u6708\u306E\u652F\u51FA\u3092\u30AB\u30C6\u30B4\u30EA\u5225\u306B\u96C6\u8A08\u3057\u3066\u3001\u524D\u6708\u6BD4\u3067\u5897\u3048\u305F\u9805\u76EE\u3092\u6559\u3048\u3066\u300D", { indent: 360, italics: true }),
        p("AI\u304C\u81EA\u52D5\u3067\u98DF\u8CBB\u30FB\u5149\u71B1\u8CBB\u30FB\u4EA4\u901A\u8CBB\u306A\u3069\u3092\u5206\u985E\u3057\u3001\u524D\u6708\u3068\u306E\u5DEE\u7570\u3092\u30CF\u30A4\u30E9\u30A4\u30C8\u3002\u300C\u4ECA\u6708\u306F\u5916\u98DF\u304C2\u4E07\u5186\u5897\u3048\u3066\u3044\u307E\u3059\u300D\u306E\u3088\u3046\u306B\u5177\u4F53\u7684\u306B\u6559\u3048\u3066\u304F\u308C\u307E\u3059\u3002", { indent: 360, color: COLOR_GRAY }),

        h2("8.2 \u56FA\u5B9A\u8CBB\u306E\u7121\u99C4\u3092\u767A\u898B"),
        pRuns([{ text: "\u5165\u529B\u4F8B\uFF1A", bold: true }], { beforeSpacing: 60 }),
        p("\u300C\u6BCE\u6708\u306E\u30B5\u30D6\u30B9\u30AF\u30EA\u30D7\u30B7\u30E7\u30F3\u3092\u5168\u90E8\u30EA\u30B9\u30C8\u30A2\u30C3\u30D7\u3057\u3066\u3002\u4F7F\u3063\u3066\u306A\u3055\u305D\u3046\u306A\u3082\u306E\u304C\u3042\u308C\u3070\u6307\u6458\u3057\u3066\u300D", { indent: 360, italics: true }),
        p("\u5B9A\u671F\u7684\u306A\u5F15\u304D\u843D\u3068\u3057\u30D1\u30BF\u30FC\u30F3\u3092\u691C\u51FA\u3057\u3001\u300C\u3053\u306E\u52D5\u753B\u30B5\u30FC\u30D3\u30B9\u306F3\u30F6\u6708\u5229\u7528\u304C\u306A\u3044\u3088\u3046\u3067\u3059\u300D\u3068\u63D0\u6848\u3002\u5E74\u9593\u3067\u6570\u4E07\u5186\u306E\u7BC0\u7D04\u306B\u3064\u306A\u304C\u308B\u30B1\u30FC\u30B9\u3082\u3002", { indent: 360, color: COLOR_GRAY }),

        h2("8.3 \u8CC7\u7523\u30DD\u30FC\u30C8\u30D5\u30A9\u30EA\u30AA\u306E\u5065\u5EB7\u8A3A\u65AD"),
        pRuns([{ text: "\u5165\u529B\u4F8B\uFF1A", bold: true }], { beforeSpacing: 60 }),
        p("\u300C\u73FE\u5728\u306E\u8CC7\u7523\u914D\u5206\u3092\u5186\u30B0\u30E9\u30D5\u3067\u898B\u305B\u3066\u3002\u73FE\u91D1\u6BD4\u7387\u304C\u9AD8\u3059\u304E\u306A\u3044\u304B\u30C1\u30A7\u30C3\u30AF\u3057\u3066\u300D", { indent: 360, italics: true }),
        p("\u9280\u884C\u9810\u91D1\u30FB\u8A3C\u5238\u30FB\u4FDD\u967A\u30FB\u4E0D\u52D5\u7523\u306A\u3069\u306E\u8CC7\u7523\u914D\u5206\u3092\u53EF\u8996\u5316\u3002\u300C\u73FE\u91D1\u6BD4\u7387\u304C60%\u3067\u3059\u3002\u5E74\u9F62\u3092\u8003\u3048\u308B\u3068\u6295\u8CC7\u306B\u56DE\u3059\u4F59\u5730\u304C\u3042\u308A\u305D\u3046\u3067\u3059\u300D\u3068\u3044\u3063\u305F\u793A\u5506\u3082\u3002", { indent: 360, color: COLOR_GRAY }),
        tip("\u8CC7\u7523\u904B\u7528\u306E\u6700\u7D42\u5224\u65AD\u306F\u5FC5\u305A\u3054\u81EA\u8EAB\u3067\u884C\u3063\u3066\u304F\u3060\u3055\u3044\u3002AI\u306E\u51FA\u529B\u306F\u53C2\u8003\u60C5\u5831\u3067\u3059\u3002"),

        h2("8.4 \u5E74\u9593\u30E9\u30A4\u30D5\u30D7\u30E9\u30F3\u30CB\u30F3\u30B0"),
        pRuns([{ text: "\u5165\u529B\u4F8B\uFF1A", bold: true }], { beforeSpacing: 60 }),
        p("\u300C\u904E\u53BB1\u5E74\u306E\u53CE\u5165\u3068\u652F\u51FA\u304B\u3089\u3001\u5E74\u9593\u8CAF\u84C4\u53EF\u80FD\u984D\u3092\u8A08\u7B97\u3057\u3066\u3002\u5B50\u4F9B\u306E\u6559\u80B2\u8CBB\u304C\u304B\u304B\u308B\u6642\u671F\u306E\u30B7\u30DF\u30E5\u30EC\u30FC\u30B7\u30E7\u30F3\u3082\u3057\u3066\u300D", { indent: 360, italics: true }),
        p("\u5B9F\u969B\u306E\u53CE\u652F\u30C7\u30FC\u30BF\u3092\u30D9\u30FC\u30B9\u306B\u3001\u5C06\u6765\u306E\u30AD\u30E3\u30C3\u30B7\u30E5\u30D5\u30ED\u30FC\u3092\u8A66\u7B97\u3002\u300C\u5B50\u4F9B\u304C\u9AD8\u6821\u306B\u5165\u308B3\u5E74\u5F8C\u306B\u306F\u6BCE\u6708\u25CB\u4E07\u5186\u306E\u4E0D\u8DB3\u304C\u898B\u8FBC\u307E\u308C\u307E\u3059\u300D\u306E\u3088\u3046\u306A\u5177\u4F53\u7684\u306A\u8A66\u7B97\u304C\u53EF\u80FD\u3002", { indent: 360, color: COLOR_GRAY }),

        h2("8.5 \u78BA\u5B9A\u7533\u544A\u306E\u4E8B\u524D\u6E96\u5099"),
        pRuns([{ text: "\u5165\u529B\u4F8B\uFF1A", bold: true }], { beforeSpacing: 60 }),
        p("\u300C\u4ECA\u5E74\u306E\u533B\u7642\u8CBB\u3092\u5168\u90E8\u96C6\u8A08\u3057\u3066\u3002\u533B\u7642\u8CBB\u63A7\u9664\u306E\u5BFE\u8C61\u306B\u306A\u308B\u304B\u6559\u3048\u3066\u300D", { indent: 360, italics: true }),
        p("\u533B\u7642\u8CBB\u30FB\u5BFF\u4FDD\u967A\u6599\u30FB\u3075\u308B\u3055\u3068\u7D0D\u7A0E\u306A\u3069\u306E\u63A7\u9664\u5BFE\u8C61\u652F\u51FA\u3092\u81EA\u52D5\u62BD\u51FA\u3002\u300C\u533B\u7642\u8CBB\u304C\u5408\u8A0832\u4E07\u5186\u3067\u3001\u63A7\u9664\u5BFE\u8C61\u306F22\u4E07\u5186\u3067\u3059\u300D\u3068\u5373\u5EA7\u306B\u56DE\u7B54\u3002", { indent: 360, color: COLOR_GRAY }),

        h2("8.6 \u5BB6\u65CF\u3067\u5171\u6709\u3059\u308B\u5BB6\u8A08\u30EC\u30DD\u30FC\u30C8"),
        pRuns([{ text: "\u5165\u529B\u4F8B\uFF1A", bold: true }], { beforeSpacing: 60 }),
        p("\u300C\u4ECA\u6708\u306E\u5BB6\u8A08\u30B5\u30DE\u30EA\u30FC\u3092\u308F\u304B\u308A\u3084\u3059\u304FPDF\u3067\u4F5C\u3063\u3066\u3002\u98DF\u8CBB\u30FB\u5149\u71B1\u8CBB\u30FB\u5A2F\u697D\u8CBB\u3092\u30B0\u30E9\u30D5\u4ED8\u304D\u3067\u300D", { indent: 360, italics: true }),
        p("\u5BB6\u65CF\u306B\u5171\u6709\u3057\u3084\u3059\u3044\u30D3\u30B8\u30E5\u30A2\u30EB\u30EC\u30DD\u30FC\u30C8\u3092\u81EA\u52D5\u751F\u6210\u3002\u6BCE\u6708\u306E\u5B9A\u70B9\u89B3\u6E2C\u306B\u3082\u6D3B\u7528\u3067\u304D\u307E\u3059\u3002", { indent: 360, color: COLOR_GRAY }),

        h2("8.7 \u300C\u304A\u91D1\u306E\u5065\u5EB7\u8A3A\u65AD\u300D\u30D7\u30ED\u30F3\u30D7\u30C6\u30F3\u30D7\u30EC\u30FC\u30C8"),
        p("\u4EE5\u4E0B\u306E\u30D7\u30ED\u30F3\u30D7\u30C8\u3092\u305D\u306E\u307E\u307E\u30B3\u30D4\u30FC\u3057\u3066\u4F7F\u3046\u3060\u3051\u3067\u3001\u5305\u62EC\u7684\u306A\u5BB6\u8A08\u8A3A\u65AD\u304C\u3067\u304D\u307E\u3059\uFF1A"),

        makeTable(
          ["\u8A3A\u65AD\u9805\u76EE", "\u30B3\u30D4\u30FC\u3057\u3066\u4F7F\u3048\u308B\u30D7\u30ED\u30F3\u30D7\u30C8"],
          [
            ["\u652F\u51FA\u30D0\u30E9\u30F3\u30B9", "\u300C\u904E\u53BB3\u30F6\u6708\u306E\u652F\u51FA\u3092\u56FA\u5B9A\u8CBB\u3068\u5909\u52D5\u8CBB\u306B\u5206\u3051\u3066\u3002\u56FA\u5B9A\u8CBB\u7387\u304C50%\u3092\u8D85\u3048\u3066\u3044\u305F\u3089\u8B66\u544A\u3057\u3066\u300D"],
            ["\u8CAF\u84C4\u7387\u30C1\u30A7\u30C3\u30AF", "\u300C\u53CE\u5165\u306B\u5BFE\u3059\u308B\u8CAF\u84C4\u7387\u3092\u6708\u5225\u3067\u51FA\u3057\u3066\u300220%\u672A\u6E80\u306E\u6708\u306F\u539F\u56E0\u3092\u5206\u6790\u3057\u3066\u300D"],
            ["\u7D4C\u8CBB\u7BC0\u7D04", "\u300C\u524D\u5E74\u540C\u6708\u3068\u6BD4\u8F03\u3057\u3066\u3001\u5897\u3048\u305F\u30AB\u30C6\u30B4\u30EA\u30C8\u30C3\u30D73\u3068\u305D\u306E\u5185\u8A33\u3092\u6559\u3048\u3066\u300D"],
            ["\u30E9\u30A4\u30D5\u30A4\u30D9\u30F3\u30C8\u5099\u3048", "\u300C\u73FE\u5728\u306E\u8CAF\u84C4\u30DA\u30FC\u30B9\u3067\u3001\u8ECA\u306E\u8CB7\u3044\u66FF\u3048\u8CC7\u91D1300\u4E07\u5186\u304C\u8CB7\u3048\u308B\u306E\u306F\u3044\u3064\u9803\uFF1F\u300D"],
            ["\u7BC0\u7A0E\u6700\u9069\u5316", "\u300C\u4ECA\u5E74\u306E\u3075\u308B\u3055\u3068\u7D0D\u7A0E\u30FB\u533B\u7642\u8CBB\u30FB\u4FDD\u967A\u6599\u306E\u63A7\u9664\u984D\u3092\u8A08\u7B97\u3057\u3066\u3001\u307E\u3060\u67A0\u304C\u4F59\u3063\u3066\u3044\u308B\u304B\u6559\u3048\u3066\u300D"],
            ["\u5B50\u4F9B\u306E\u6559\u80B2\u8CBB", "\u300C\u904E\u53BB1\u5E74\u306E\u6559\u80B2\u95A2\u9023\u652F\u51FA\u3092\u5168\u90E8\u62BD\u51FA\u3057\u3066\u3002\u5B66\u8CBB\u30FB\u587E\u30FB\u7FD2\u3044\u4E8B\u306B\u5206\u3051\u3066\u300D"],
          ],
          [2000, 7300]
        ),

        h2("8.8 \u6D3B\u7528\u306E\u30B3\u30C4\u3068\u6CE8\u610F\u70B9"),
        numbered("MoneyForward ME\u306E\u30AB\u30C6\u30B4\u30EA\u5206\u3051\u3092\u6574\u7406\u3057\u3066\u304A\u304F\u3068\u3001AI\u306E\u5206\u6790\u7CBE\u5EA6\u304C\u5411\u4E0A\u3057\u307E\u3059"),
        numbered("\u300C\u6BCE\u6708\u306E\u5B9A\u70B9\u89B3\u6E2C\u300D\u3068\u3057\u3066\u540C\u3058\u30D7\u30ED\u30F3\u30D7\u30C8\u3092\u4F7F\u3046\u3068\u3001\u63A8\u79FB\u304C\u8FFD\u3048\u3066\u4FBF\u5229"),
        numbered("\u500B\u4EBA\u306E\u91D1\u878D\u30C7\u30FC\u30BF\u306F\u6A5F\u5BC6\u6027\u304C\u9AD8\u3044\u305F\u3081\u3001\u5171\u6709\u7AEF\u672B\u3067\u306E\u5229\u7528\u306F\u907F\u3051\u307E\u3057\u3087\u3046"),
        numbered("AI\u306E\u51FA\u529B\u306F\u3042\u304F\u307E\u3067\u53C2\u8003\u60C5\u5831\u3067\u3059\u3002\u7279\u306B\u6295\u8CC7\u5224\u65AD\u306F\u5C02\u9580\u5BB6\u306B\u76F8\u8AC7\u3057\u307E\u3057\u3087\u3046"),

        h2("8.9 mf-dashboard\u306E\u30BB\u30C3\u30C8\u30A2\u30C3\u30D7\u624B\u9806\uFF08\u7C21\u6613\u7248\uFF09"),
        p("MoneyForward ME\u306E\u5BB6\u8A08\u30C7\u30FC\u30BF\u3092AI\u3067\u6D3B\u7528\u3059\u308B\u306B\u306F\u3001\u975E\u516C\u5F0F\u306Emf-dashboard\u3092\u5229\u7528\u3057\u307E\u3059\u3002", { beforeSpacing: 60 }),
        p(""),
        pRuns([{ text: "\u524D\u63D0\u6761\u4EF6\uFF1A", bold: true, color: COLOR_MAIN }]),
        bullet("Node.js 18\u4EE5\u4E0A\u304C\u30A4\u30F3\u30B9\u30C8\u30FC\u30EB\u6E08\u307F"),
        bullet("MoneyForward ME\u306E\u30A2\u30AB\u30A6\u30F3\u30C8"),
        bullet("1Password\uFF08\u30ED\u30B0\u30A4\u30F3\u60C5\u5831\u306E\u5B89\u5168\u306A\u7BA1\u7406\u306B\u4F7F\u7528\uFF09"),
        p(""),
        pRuns([{ text: "\u30BB\u30C3\u30C8\u30A2\u30C3\u30D7\u624B\u9806\uFF1A", bold: true, color: COLOR_MAIN }]),
        numbered("GitHub\u304B\u3089\u30AF\u30ED\u30FC\u30F3\uFF1A"),
        code("git clone https://github.com/hiroppy/mf-dashboard"),
        code("cd mf-dashboard && npm install"),
        numbered("\u74B0\u5883\u5909\u6570\u3092\u8A2D\u5B9A\uFF08.env\u30D5\u30A1\u30A4\u30EB\u3092\u4F5C\u6210\uFF09"),
        numbered("\u30C7\u30FC\u30BF\u53CE\u96C6\u3092\u5B9F\u884C\uFF1A"),
        code("npm run crawl"),
        numbered("Claude Desktop\u306E\u8A2D\u5B9A\u30D5\u30A1\u30A4\u30EB\u306BMCP\u30B5\u30FC\u30D0\u30FC\u3092\u8FFD\u52A0"),
        tip("\u8A73\u7D30\u306A\u30BB\u30C3\u30C8\u30A2\u30C3\u30D7\u306FGitHub\u30EA\u30DD\u30B8\u30C8\u30EA\u306EREADME\u3092\u53C2\u7167\u3057\u3066\u304F\u3060\u3055\u3044\u3002"),

        new Paragraph({ children: [new PageBreak()] }),

        // ===== 9. 補足 =====
        h1("9. \u88DC\u8DB3: \u305D\u306E\u4ED6\u306EMCP\u30B5\u30FC\u30D0\u30FC"),

        h2("9.1 Admina MCP Server\uFF08IT\u8CC7\u7523\u7BA1\u7406\uFF09"),
        bullet("\u5BFE\u8C61: Admina by Money Forward"),
        bullet("\u7528\u9014: \u793E\u5185\u306ESaaS\u5229\u7528\u72B6\u6CC1\u3001\u30C7\u30D0\u30A4\u30B9\u7BA1\u7406\u3001\u30A2\u30AB\u30A6\u30F3\u30C8\u7BA1\u7406"),
        p("\u30BB\u30C3\u30C8\u30A2\u30C3\u30D7\u30B3\u30DE\u30F3\u30C9\uFF1A", { beforeSpacing: 120 }),
        code("claude mcp add admina -- npx -y @moneyforward_i/admina-mcp-server"),
        p("\u74B0\u5883\u5909\u6570\u306B ADMINA_ORGANIZATION_ID \u3068 ADMINA_API_KEY \u3092\u8A2D\u5B9A\u3057\u3066\u304F\u3060\u3055\u3044\u3002", { beforeSpacing: 60 }),

        h2("9.2 MoneyForward ME\u5411\u3051\uFF08\u975E\u516C\u5F0F\uFF09"),
        bullet("mf-dashboard: Playwright\u3067ME\u753B\u9762\u3092\u30B9\u30AF\u30EC\u30A4\u30D4\u30F3\u30B0\u3002\u5BB6\u8A08\u7C3F\u30FB\u8CC7\u7523\u7BA1\u7406\u30C7\u30FC\u30BF\u3092AI\u3067\u5206\u6790"),
        bullet("\u500B\u4EBA\u306E\u8CC7\u7523\u7BA1\u7406\u306B\u306F\u4FBF\u5229\u3060\u304C\u3001Playwright\u3068SQLite\u306E\u77E5\u8B58\u304C\u5FC5\u8981"),

        new Paragraph({ children: [new PageBreak()] }),

        // ===== 10. トラブルシューティング =====
        h1("10. \u30C8\u30E9\u30D6\u30EB\u30B7\u30E5\u30FC\u30C6\u30A3\u30F3\u30B0"),

        makeTable(
          ["\u75C7\u72B6", "\u539F\u56E0", "\u5BFE\u51E6\u6CD5"],
          [
            ["MCP\u30B5\u30FC\u30D0\u30FC\u304C\u898B\u3064\u304B\u3089\u306A\u3044", "\u8A2D\u5B9A\u30D5\u30A1\u30A4\u30EB\u306E\u8A18\u8FF0\u30DF\u30B9", "URL\u3084JSON\u69CB\u6587\u3092\u518D\u78BA\u8A8D"],
            ["\u8A8D\u8A3C\u30A8\u30E9\u30FC\u304C\u51FA\u308B", "\u6A29\u9650\u672A\u4ED8\u4E0E or \u30C8\u30FC\u30AF\u30F3\u671F\u9650\u5207\u308C", "\u5168\u6A29\u7BA1\u7406\u8005\u306B\u6A29\u9650\u4ED8\u4E0E\u3092\u4F9D\u983C / \u518D\u8A8D\u8A3C"],
            ["\u4ED5\u8A33\u304C\u53D6\u5F97\u3067\u304D\u306A\u3044", "\u4F1A\u8A08\u671F\u9593\u306E\u6307\u5B9A\u304C\u4E0D\u6B63", "\u300C\u4E8B\u696D\u8005\u60C5\u5831\u3092\u8868\u793A\u3057\u3066\u300D\u3067\u671F\u9593\u78BA\u8A8D"],
            ["\u63A5\u7D9A\u304C\u30BF\u30A4\u30E0\u30A2\u30A6\u30C8", "\u30CD\u30C3\u30C8\u30EF\u30FC\u30AF\u554F\u984C", "\u30A4\u30F3\u30BF\u30FC\u30CD\u30C3\u30C8\u63A5\u7D9A\u3092\u78BA\u8A8D\u3002\u30D7\u30ED\u30AD\u30B7\u74B0\u5883\u3067\u306F\u8A2D\u5B9A\u304C\u5FC5\u8981"],
            ["Claude Desktop\u306B\u8868\u793A\u3055\u308C\u306A\u3044", "\u518D\u8D77\u52D5\u304C\u5FC5\u8981", "Claude Desktop\u3092\u5B8C\u5168\u306B\u7D42\u4E86\u3057\u3066\u518D\u8D77\u52D5"],
          ],
          [2600, 2800, 3900]
        ),

        new Paragraph({ children: [new PageBreak()] }),

        // ===== 11. まとめ =====
        h1("11. \u307E\u3068\u3081"),

        p("\u30DE\u30CD\u30FC\u30D5\u30A9\u30EF\u30FC\u30C9 \u30AF\u30E9\u30A6\u30C9\u4F1A\u8A08\u306EMCP\u9023\u643A\u306B\u3088\u308A\u3001\u4EE5\u4E0B\u306E\u3053\u3068\u304C\u5B9F\u73FE\u3057\u307E\u3059\uFF1A", { beforeSpacing: 120 }),

        bullet("\u4F1A\u8A08\u30C7\u30FC\u30BF\u3078\u306E\u554F\u3044\u5408\u308F\u305B\u304C\u300C\u81EA\u7136\u8A00\u8A9E\u300D\u3067\u53EF\u80FD\u306B"),
        bullet("\u4ED5\u8A33\u5165\u529B\u306E\u624B\u9593\u304C\u5927\u5E45\u306B\u524A\u6E1B"),
        bullet("\u6708\u6B21\u6C7A\u7B97\u30C1\u30A7\u30C3\u30AF\u304C\u6570\u5206\u3067\u5B8C\u4E86"),
        bullet("\u7D4C\u55B6\u5206\u6790\u30EC\u30DD\u30FC\u30C8\u306E\u81EA\u52D5\u751F\u6210\u304C\u53EF\u80FD"),

        p(""),
        p("\u30BB\u30C3\u30C8\u30A2\u30C3\u30D7\u306F15\u5206\u7A0B\u5EA6\u3067\u5B8C\u4E86\u3057\u3001\u4E00\u5EA6\u8A2D\u5B9A\u3059\u308C\u3070\u65E5\u3005\u306E\u696D\u52D9\u3067\u7D99\u7D9A\u7684\u306B\u6D3B\u7528\u3067\u304D\u307E\u3059\u3002"),

        p(""),
        p(""),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          border: { top: { style: BorderStyle.SINGLE, size: 4, color: COLOR_ACCENT, space: 8 } },
          spacing: { before: 400 },
          children: [new TextRun({ text: "\u304A\u3082\u308D\u307E\u3061\u30E1\u30C7\u30A3\u30AB\u30EB\u30BB\u30F3\u30BF\u30FC AI\u7BA1\u7406\u30EF\u30FC\u30AF\u30B9\u30DA\u30FC\u30B9", font: FONT, size: 18, color: COLOR_GRAY })],
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [new TextRun({ text: "2026\u5E744\u67085\u65E5\u4F5C\u6210", font: FONT, size: 18, color: COLOR_GRAY })],
        }),
      ],
    },
  ],
});

const OUTPUT = "/Users/torukubota/ai-management/docs/admin/claude_code_moneyforward_mcp_manual.docx";

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync(OUTPUT, buffer);
  console.log("Created:", OUTPUT);
});
