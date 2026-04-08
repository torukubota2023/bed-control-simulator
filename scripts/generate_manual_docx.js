const fs = require("fs");
const {
  Document,
  Packer,
  Paragraph,
  TextRun,
  Table,
  TableRow,
  TableCell,
  WidthType,
  AlignmentType,
  HeadingLevel,
  BorderStyle,
  ShadingType,
  LevelFormat,
  PageBreak,
  convertInchesToTwip,
} = require("docx");

// ─── Config ───
const INPUT = "/Users/kubotatoru/ai-management/docs/admin/BedControl_Manual_v3.md";
const OUTPUT = "/Users/kubotatoru/ai-management/docs/admin/BedControl_Manual_v3.docx";

const FONT_BODY = "Hiragino Sans W3";
const FONT_HEADING = "Hiragino Sans W6";
const FONT_MONO = "Courier New";

const SIZE_BODY = 22;      // 11pt
const SIZE_H1 = 36;        // 18pt
const SIZE_H2 = 28;        // 14pt
const SIZE_H3 = 24;        // 12pt
const SIZE_H4 = 22;        // 11pt
const SIZE_H5 = 22;        // 11pt

// ─── Inline text parser ───
// Parses **bold**, `code`, and plain text into TextRun[]
function parseInlineText(text, opts = {}) {
  const runs = [];
  const regex = /(\*\*(.+?)\*\*)|(`(.+?)`)/g;
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(text)) !== null) {
    // plain text before this match
    if (match.index > lastIndex) {
      runs.push(
        new TextRun({
          text: text.slice(lastIndex, match.index),
          font: opts.font || FONT_BODY,
          size: opts.size || SIZE_BODY,
          bold: opts.bold || false,
          italics: opts.italics || false,
          color: opts.color || undefined,
        })
      );
    }
    if (match[2]) {
      // bold
      runs.push(
        new TextRun({
          text: match[2],
          font: opts.font || FONT_BODY,
          size: opts.size || SIZE_BODY,
          bold: true,
          italics: opts.italics || false,
          color: opts.color || undefined,
        })
      );
    } else if (match[4]) {
      // inline code
      runs.push(
        new TextRun({
          text: match[4],
          font: FONT_MONO,
          size: (opts.size || SIZE_BODY) - 2,
          bold: opts.bold || false,
          shading: {
            type: ShadingType.CLEAR,
            color: "auto",
            fill: "E8E8E8",
          },
        })
      );
    }
    lastIndex = match.index + match[0].length;
  }
  // trailing text
  if (lastIndex < text.length) {
    runs.push(
      new TextRun({
        text: text.slice(lastIndex),
        font: opts.font || FONT_BODY,
        size: opts.size || SIZE_BODY,
        bold: opts.bold || false,
        italics: opts.italics || false,
        color: opts.color || undefined,
      })
    );
  }
  if (runs.length === 0) {
    runs.push(new TextRun({ text: "", font: opts.font || FONT_BODY, size: opts.size || SIZE_BODY }));
  }
  return runs;
}

// ─── Table builder ───
function buildTable(headerRow, dataRows) {
  const numCols = headerRow.length;
  // Calculate column widths: distribute A4 content width evenly
  const pageContentWidth = 11906 - 1440 * 2; // ~9026 DXA
  const colWidth = Math.floor(pageContentWidth / numCols);
  const columnWidths = Array(numCols).fill(colWidth);

  const borderStyle = {
    style: BorderStyle.SINGLE,
    size: 1,
    color: "999999",
  };
  const cellBorders = {
    top: borderStyle,
    bottom: borderStyle,
    left: borderStyle,
    right: borderStyle,
  };
  const cellMargins = {
    top: convertInchesToTwip(0.04),
    bottom: convertInchesToTwip(0.04),
    left: convertInchesToTwip(0.06),
    right: convertInchesToTwip(0.06),
  };

  function makeCell(text, isHeader) {
    return new TableCell({
      children: [
        new Paragraph({
          children: parseInlineText(text, {
            bold: isHeader,
            size: isHeader ? SIZE_BODY : SIZE_BODY,
            font: isHeader ? FONT_HEADING : FONT_BODY,
          }),
          spacing: { before: 40, after: 40 },
        }),
      ],
      width: { size: colWidth, type: WidthType.DXA },
      borders: cellBorders,
      margins: cellMargins,
      shading: isHeader
        ? { type: ShadingType.CLEAR, color: "auto", fill: "D9E2F3" }
        : undefined,
    });
  }

  const rows = [];
  // Header row
  rows.push(
    new TableRow({
      children: headerRow.map((h) => makeCell(h, true)),
      tableHeader: true,
    })
  );
  // Data rows
  for (const row of dataRows) {
    rows.push(
      new TableRow({
        children: row.map((c) => makeCell(c, false)),
      })
    );
  }

  return new Table({
    rows,
    width: { size: pageContentWidth, type: WidthType.DXA },
    columnWidths,
  });
}

// ─── Parse table lines ───
// Returns { header: string[], rows: string[][] } or null
function parseTableBlock(lines) {
  // lines[0] = header, lines[1] = separator, lines[2..] = data
  if (lines.length < 2) return null;
  const parseLine = (line) =>
    line
      .replace(/^\|/, "")
      .replace(/\|$/, "")
      .split("|")
      .map((c) => c.trim());

  const header = parseLine(lines[0]);
  // lines[1] is separator (|---|---|)
  const rows = [];
  for (let i = 2; i < lines.length; i++) {
    rows.push(parseLine(lines[i]));
  }
  return { header, rows };
}

// ─── Main parser ───
function parseMarkdown(content) {
  const lines = content.split("\n");
  const elements = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // ── Blank line ──
    if (line.trim() === "") {
      i++;
      continue;
    }

    // ── Horizontal rule ──
    if (/^---+\s*$/.test(line.trim())) {
      // Add spacing (acts as section separator)
      elements.push(
        new Paragraph({
          spacing: { before: 200, after: 200 },
          children: [],
        })
      );
      i++;
      continue;
    }

    // ── Headings ──
    const headingMatch = line.match(/^(#{1,5})\s+(.+)/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const text = headingMatch[2];
      const sizeMap = { 1: SIZE_H1, 2: SIZE_H2, 3: SIZE_H3, 4: SIZE_H4, 5: SIZE_H5 };
      const headingLevelMap = {
        1: HeadingLevel.HEADING_1,
        2: HeadingLevel.HEADING_2,
        3: HeadingLevel.HEADING_3,
        4: HeadingLevel.HEADING_4,
        5: HeadingLevel.HEADING_5,
      };

      elements.push(
        new Paragraph({
          heading: headingLevelMap[level],
          spacing: { before: level <= 2 ? 360 : 240, after: 120 },
          children: parseInlineText(text, {
            font: FONT_HEADING,
            size: sizeMap[level],
            bold: level >= 4,
          }),
        })
      );
      i++;
      continue;
    }

    // ── Code block ──
    if (line.trim().startsWith("```")) {
      i++; // skip opening ```
      const codeLines = [];
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      if (i < lines.length) i++; // skip closing ```

      // Each line of the code block as a separate paragraph
      for (const cl of codeLines) {
        elements.push(
          new Paragraph({
            spacing: { before: 20, after: 20 },
            indent: { left: convertInchesToTwip(0.3) },
            children: [
              new TextRun({
                text: cl || " ",
                font: FONT_MONO,
                size: 18, // 9pt
              }),
            ],
            shading: {
              type: ShadingType.CLEAR,
              color: "auto",
              fill: "F2F2F2",
            },
          })
        );
      }
      continue;
    }

    // ── Blockquote ──
    if (line.trim().startsWith(">")) {
      const quoteLines = [];
      let j = i;
      while (j < lines.length && (lines[j].trim().startsWith(">") || (lines[j].trim() !== "" && quoteLines.length > 0 && !lines[j].trim().startsWith("#") && !lines[j].trim().startsWith("|") && !lines[j].trim().startsWith("-") && !lines[j].trim().match(/^\d+\./)))) {
        quoteLines.push(lines[j].replace(/^>\s?/, ""));
        j++;
      }
      i = j;

      const quoteText = quoteLines.join(" ").trim();
      elements.push(
        new Paragraph({
          indent: { left: convertInchesToTwip(0.4) },
          spacing: { before: 120, after: 120 },
          border: {
            left: {
              style: BorderStyle.SINGLE,
              size: 6,
              color: "4472C4",
              space: 8,
            },
          },
          children: parseInlineText(quoteText, {
            italics: false,
            size: SIZE_BODY,
            color: "404040",
          }),
        })
      );
      continue;
    }

    // ── Table ──
    if (line.trim().startsWith("|")) {
      const tableLines = [];
      let j = i;
      while (j < lines.length && lines[j].trim().startsWith("|")) {
        tableLines.push(lines[j]);
        j++;
      }
      i = j;

      const tableData = parseTableBlock(tableLines);
      if (tableData) {
        elements.push(buildTable(tableData.header, tableData.rows));
        elements.push(new Paragraph({ spacing: { before: 80, after: 80 }, children: [] }));
      }
      continue;
    }

    // ── Numbered list ──
    const numMatch = line.match(/^(\s*)(\d+)\.\s+(.+)/);
    if (numMatch) {
      const indentLevel = Math.floor(numMatch[1].length / 2);
      const text = numMatch[3];
      elements.push(
        new Paragraph({
          numbering: { reference: "numbered-list", level: indentLevel },
          spacing: { before: 40, after: 40 },
          children: parseInlineText(text),
        })
      );
      i++;
      continue;
    }

    // ── Bullet list ──
    const bulletMatch = line.match(/^(\s*)[-*]\s+(.+)/);
    if (bulletMatch) {
      const indentLevel = Math.floor(bulletMatch[1].length / 2);
      const text = bulletMatch[2];
      elements.push(
        new Paragraph({
          numbering: { reference: "bullet-list", level: indentLevel },
          spacing: { before: 40, after: 40 },
          children: parseInlineText(text),
        })
      );
      i++;
      continue;
    }

    // ── Regular paragraph ──
    // Collect consecutive non-special lines as one paragraph
    const paraLines = [];
    let j = i;
    while (
      j < lines.length &&
      lines[j].trim() !== "" &&
      !lines[j].trim().startsWith("#") &&
      !lines[j].trim().startsWith("|") &&
      !lines[j].trim().startsWith(">") &&
      !lines[j].trim().startsWith("```") &&
      !lines[j].trim().match(/^[-*]\s+/) &&
      !lines[j].trim().match(/^\d+\.\s+/) &&
      !lines[j].trim().match(/^---+$/)
    ) {
      paraLines.push(lines[j].trim());
      j++;
    }
    i = j;

    if (paraLines.length > 0) {
      const text = paraLines.join(" ");
      elements.push(
        new Paragraph({
          spacing: { before: 80, after: 80 },
          children: parseInlineText(text),
        })
      );
    } else {
      // Safety: skip one line to avoid infinite loop
      i++;
    }
  }

  return elements;
}

// ─── Build document ───
async function main() {
  const md = fs.readFileSync(INPUT, "utf-8");
  const children = parseMarkdown(md);

  const doc = new Document({
    styles: {
      paragraphStyles: [
        {
          id: "Heading1",
          name: "Heading 1",
          basedOn: "Normal",
          next: "Normal",
          run: { font: FONT_HEADING, size: SIZE_H1, bold: true, color: "1F3864" },
          paragraph: {
            spacing: { before: 360, after: 120 },
            outlineLevel: 0,
          },
        },
        {
          id: "Heading2",
          name: "Heading 2",
          basedOn: "Normal",
          next: "Normal",
          run: { font: FONT_HEADING, size: SIZE_H2, bold: true, color: "2E5090" },
          paragraph: {
            spacing: { before: 360, after: 120 },
            outlineLevel: 1,
          },
        },
        {
          id: "Heading3",
          name: "Heading 3",
          basedOn: "Normal",
          next: "Normal",
          run: { font: FONT_HEADING, size: SIZE_H3, bold: true, color: "404040" },
          paragraph: {
            spacing: { before: 240, after: 120 },
            outlineLevel: 2,
          },
        },
        {
          id: "Heading4",
          name: "Heading 4",
          basedOn: "Normal",
          next: "Normal",
          run: { font: FONT_HEADING, size: SIZE_H4, bold: true, color: "404040" },
          paragraph: {
            spacing: { before: 240, after: 120 },
            outlineLevel: 3,
          },
        },
        {
          id: "Heading5",
          name: "Heading 5",
          basedOn: "Normal",
          next: "Normal",
          run: { font: FONT_HEADING, size: SIZE_H5, bold: true, color: "404040" },
          paragraph: {
            spacing: { before: 240, after: 120 },
            outlineLevel: 4,
          },
        },
      ],
      default: {
        document: {
          run: {
            font: FONT_BODY,
            size: SIZE_BODY,
          },
        },
      },
    },
    numbering: {
      config: [
        {
          reference: "bullet-list",
          levels: [
            {
              level: 0,
              format: LevelFormat.BULLET,
              text: "\u2022",
              alignment: AlignmentType.LEFT,
              style: { paragraph: { indent: { left: convertInchesToTwip(0.5), hanging: convertInchesToTwip(0.25) } }, run: { font: FONT_BODY } },
            },
            {
              level: 1,
              format: LevelFormat.BULLET,
              text: "\u25E6",
              alignment: AlignmentType.LEFT,
              style: { paragraph: { indent: { left: convertInchesToTwip(1.0), hanging: convertInchesToTwip(0.25) } }, run: { font: FONT_BODY } },
            },
            {
              level: 2,
              format: LevelFormat.BULLET,
              text: "\u25AA",
              alignment: AlignmentType.LEFT,
              style: { paragraph: { indent: { left: convertInchesToTwip(1.5), hanging: convertInchesToTwip(0.25) } }, run: { font: FONT_BODY } },
            },
          ],
        },
        {
          reference: "numbered-list",
          levels: [
            {
              level: 0,
              format: LevelFormat.DECIMAL,
              text: "%1.",
              alignment: AlignmentType.LEFT,
              style: { paragraph: { indent: { left: convertInchesToTwip(0.5), hanging: convertInchesToTwip(0.25) } } },
            },
            {
              level: 1,
              format: LevelFormat.LOWER_LETTER,
              text: "%2.",
              alignment: AlignmentType.LEFT,
              style: { paragraph: { indent: { left: convertInchesToTwip(1.0), hanging: convertInchesToTwip(0.25) } } },
            },
            {
              level: 2,
              format: LevelFormat.LOWER_ROMAN,
              text: "%3.",
              alignment: AlignmentType.LEFT,
              style: { paragraph: { indent: { left: convertInchesToTwip(1.5), hanging: convertInchesToTwip(0.25) } } },
            },
          ],
        },
      ],
    },
    sections: [
      {
        properties: {
          page: {
            size: { width: 11906, height: 16838, orientation: "portrait" },
            margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
          },
        },
        children,
      },
    ],
  });

  const buffer = await Packer.toBuffer(doc);
  fs.writeFileSync(OUTPUT, buffer);
  console.log("Generated:", OUTPUT);
  console.log("Size:", (buffer.length / 1024).toFixed(1), "KB");
}

main().catch((err) => {
  console.error("Error:", err);
  process.exit(1);
});
