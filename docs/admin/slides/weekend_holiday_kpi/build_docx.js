/**
 * 週末・大型連休の稼働率対策 — スライド解説書 (docx)
 * Build: NODE_PATH=$(npm root -g) node build_docx.js
 *
 * script.md をパースし、スライド番号を明示した解説書を生成する。
 */
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Header, Footer,
  AlignmentType, LevelFormat, HeadingLevel, PageBreak, PageNumber,
  BorderStyle, TabStopType, TabStopPosition,
  Table, TableRow, TableCell, WidthType, ShadingType, TableOfContents,
  Bookmark, InternalHyperlink,
} = require("docx");

const SRC = path.join(__dirname, "script.md");
const OUT = path.join(__dirname, "weekend_holiday_kpi_解説書.docx");

// =============================================================================
// script.md パース
// =============================================================================
const raw = fs.readFileSync(SRC, "utf-8");
const lines = raw.split("\n");

// グローバルヘッダー情報の抽出
const meta = {
  title: lines[0].replace(/^#\s*/, "").replace(/\s*—\s*プレゼン台本\s*$/, ""),
  audience: "", presenter: "", duration: "", data: "", style: "",
};
for (const line of lines.slice(0, 10)) {
  const m = line.match(/^\s*-\s+\*\*(.+?):\*\*\s+(.+)$/);
  if (m) {
    const key = m[1], value = m[2];
    if (key === "対象") meta.audience = value;
    else if (key === "発表者") meta.presenter = value;
    else if (key === "所要時間") meta.duration = value;
    else if (key === "前提データ") meta.data = value;
    else if (key === "スタイル") meta.style = value;
  }
}

// スライド分割
const slides = [];
let currentSlide = null;
let currentSection = null;

for (let i = 0; i < lines.length; i++) {
  const line = lines[i];
  // スライド境界
  const slideMatch = line.match(/^##\s+Slide\s+(\d+(?:\.\d+)?):\s*(.+)$/);
  if (slideMatch) {
    if (currentSlide) slides.push(currentSlide);
    currentSlide = {
      number: slideMatch[1],
      title: slideMatch[2].trim(),
      sections: {},
    };
    currentSection = null;
    continue;
  }
  if (!currentSlide) continue;

  // セクション見出し (###)
  const secMatch = line.match(/^###\s+(.+?)(?:（(.+?)）)?\s*$/);
  if (secMatch) {
    const secName = secMatch[1].trim();
    currentSection = secName;
    currentSlide.sections[currentSection] = { time: secMatch[2] || "", lines: [] };
    continue;
  }
  // 区切り線 --- や補足資料見出しで終了
  if (/^##\s+補足資料/.test(line)) {
    if (currentSlide) slides.push(currentSlide);
    currentSlide = null;
    currentSection = null;
    break;
  }
  if (/^---\s*$/.test(line)) continue;

  // 本文蓄積
  if (currentSection && line !== undefined) {
    currentSlide.sections[currentSection].lines.push(line);
  }
}
if (currentSlide) slides.push(currentSlide);

// 補足資料セクションを抽出
const appendixStart = lines.findIndex((l) => /^##\s+補足資料/.test(l));
const appendixLines = appendixStart >= 0 ? lines.slice(appendixStart + 1) : [];

// =============================================================================
// テキスト整形ヘルパ
// =============================================================================
// **bold** を TextRun に変換
function parseInlineBold(text, baseOpts = {}) {
  const runs = [];
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

// 本文段落を生成
function paragraph(text, opts = {}) {
  return new Paragraph({
    children: parseInlineBold(text),
    spacing: { line: 360, after: 140 },  // 1.5 倍行間・段落後余白
    ...opts,
  });
}

// 箇条書きアイテム
function bulletItem(text, level = 0) {
  return new Paragraph({
    numbering: { reference: "bullets", level },
    children: parseInlineBold(text),
    spacing: { line: 300, after: 80 },
  });
}

// Q&A 整形
function formatQA(rawLines) {
  const out = [];
  let buffer = "";
  let mode = null; // "Q" | "A"
  const flush = () => {
    if (!buffer || !mode) return;
    const prefix = mode === "Q" ? "Q: " : "A: ";
    const color = mode === "Q" ? "1E3A5F" : "475569";
    out.push(new Paragraph({
      children: [
        new TextRun({ text: prefix, bold: true, color }),
        ...parseInlineBold(buffer),
      ],
      spacing: { line: 330, after: mode === "A" ? 200 : 60 },
      indent: { left: 240 },
    }));
    buffer = "";
  };
  for (const line of rawLines) {
    const qm = line.match(/^Q:\s*(.+)$/);
    const am = line.match(/^A:\s*(.+)$/);
    if (qm) { flush(); mode = "Q"; buffer = qm[1]; }
    else if (am) { flush(); mode = "A"; buffer = am[1]; }
    else if (line.trim() === "") { /* skip blank lines */ }
    else if (line.trim() === "（タイトルスライドのため省略）") {
      out.push(new Paragraph({
        children: [new TextRun({ text: "（タイトルスライドのため想定質問はございません）", italics: true, color: "94A3B8" })],
        spacing: { after: 120 },
        indent: { left: 240 },
      }));
    }
    else if (mode) { buffer += " " + line.trim(); }
  }
  flush();
  return out;
}

// 箇条書きを整形（画面要素など）
function formatBullets(rawLines) {
  const out = [];
  for (const line of rawLines) {
    const t = line.trim();
    if (!t) continue;
    const m1 = t.match(/^-\s+(.+)$/);  // "- 項目"
    const mn = t.match(/^\s*\d+\.\s+(.+)$/);  // "1. 項目"
    if (m1) {
      // ネスト検出: 行の行頭スペース数で level 決定
      const leading = line.match(/^(\s*)-/);
      const level = leading ? Math.min(2, Math.floor(leading[1].length / 2)) : 0;
      out.push(bulletItem(m1[1], level));
    } else if (mn) {
      out.push(new Paragraph({
        numbering: { reference: "numbers", level: 0 },
        children: parseInlineBold(mn[1]),
        spacing: { line: 300, after: 80 },
      }));
    } else if (t) {
      // 通常段落として
      out.push(paragraph(t, { spacing: { line: 300, after: 100 } }));
    }
  }
  return out;
}

// 話す内容（本文段落）
function formatNarration(rawLines) {
  const out = [];
  // 連続した非空行を段落としてまとめる
  let para = [];
  const flush = () => {
    if (para.length) {
      out.push(paragraph(para.join("")));
      para = [];
    }
  };
  for (const line of rawLines) {
    const t = line.trim();
    if (!t) { flush(); continue; }
    para.push(t);
  }
  flush();
  return out;
}

// =============================================================================
// スタイル定義
// =============================================================================
const NAVY = "1E3A5F";
const GRAY = "475569";
const GRAY_LIGHT = "94A3B8";
const GOLD = "C9A961";
const BG_CREAM = "F7F5F0";

// =============================================================================
// 文書ビルド
// =============================================================================
const children = [];

// ----- 表紙 -----
children.push(new Paragraph({
  children: [new TextRun({ text: "", size: 24 })],
  spacing: { after: 600 },
}));
children.push(new Paragraph({
  children: [new TextRun({ text: "DATA-DRIVEN BED CONTROL PROPOSAL", color: GOLD, size: 20, bold: true, characterSpacing: 60 })],
  alignment: AlignmentType.CENTER,
  spacing: { after: 300 },
}));
children.push(new Paragraph({
  children: [new TextRun({ text: meta.title, color: NAVY, size: 52, bold: true })],
  alignment: AlignmentType.CENTER,
  spacing: { after: 200 },
}));
children.push(new Paragraph({
  children: [new TextRun({ text: "プレゼン解説書（発表台本・想定Q&A 付き）", color: NAVY, size: 26, italics: true })],
  alignment: AlignmentType.CENTER,
  spacing: { after: 600 },
}));
// 区切り線
children.push(new Paragraph({
  border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: GOLD } },
  spacing: { after: 200 },
}));

// 概要表
const overviewRows = [
  ["対象", meta.audience],
  ["発表者", meta.presenter],
  ["所要時間", meta.duration],
  ["前提データ", meta.data],
  ["スタイル", meta.style],
  ["文書作成日", "2026年4月17日"],
];
children.push(new Table({
  width: { size: 9360, type: WidthType.DXA },
  columnWidths: [2340, 7020],
  rows: overviewRows.map(([k, v]) => new TableRow({
    children: [
      new TableCell({
        width: { size: 2340, type: WidthType.DXA },
        shading: { fill: "E8EEF5", type: ShadingType.CLEAR },
        borders: makeBorders(),
        margins: { top: 100, bottom: 100, left: 140, right: 140 },
        children: [new Paragraph({ children: [new TextRun({ text: k, bold: true, color: NAVY, size: 20 })] })],
      }),
      new TableCell({
        width: { size: 7020, type: WidthType.DXA },
        borders: makeBorders(),
        margins: { top: 100, bottom: 100, left: 140, right: 140 },
        children: [new Paragraph({ children: parseInlineBold(v, { size: 20 }) })],
      }),
    ],
  })),
}));

children.push(new Paragraph({ children: [new PageBreak()] }));

// ----- 目次 -----
children.push(new Paragraph({
  heading: HeadingLevel.HEADING_1,
  children: [new TextRun("目次")],
}));

for (const s of slides) {
  children.push(new Paragraph({
    tabStops: [{ type: TabStopType.RIGHT, position: 9200, leader: "dot" }],
    children: [
      new InternalHyperlink({
        anchor: `slide-${s.number}`,
        children: [new TextRun({ text: `Slide ${s.number}：${s.title}`, style: "Hyperlink" })],
      }),
      new TextRun({ text: "\t" }),
    ],
    spacing: { line: 320, after: 60 },
  }));
}
// 反論章への目次リンク
children.push(new Paragraph({
  tabStops: [{ type: TabStopType.RIGHT, position: 9200, leader: "dot" }],
  children: [
    new InternalHyperlink({
      anchor: "rebuttal",
      children: [new TextRun({ text: "【重要】Slide 15 補足 — 「木曜前倒し＝マイナスベッド」への回答", style: "Hyperlink", bold: true, color: "C73E1D" })],
    }),
    new TextRun({ text: "\t" }),
  ],
  spacing: { line: 320, after: 60 },
}));
children.push(new Paragraph({
  tabStops: [{ type: TabStopType.RIGHT, position: 9200, leader: "dot" }],
  children: [
    new InternalHyperlink({
      anchor: "appendix",
      children: [new TextRun({ text: "補足資料（バックアップ）", style: "Hyperlink" })],
    }),
    new TextRun({ text: "\t" }),
  ],
  spacing: { line: 320, after: 60 },
}));

children.push(new Paragraph({ children: [new PageBreak()] }));

// ----- 各スライド解説 -----
for (const s of slides) {
  // スライド見出し
  children.push(new Paragraph({
    heading: HeadingLevel.HEADING_1,
    children: [
      new Bookmark({
        id: `slide-${s.number}`,
        children: [new TextRun(`Slide ${s.number}：${s.title}`)],
      }),
    ],
    pageBreakBefore: false,
    spacing: { before: 300, after: 200 },
  }));

  // 話す内容
  const narration = s.sections["話す内容"];
  if (narration) {
    const timeTag = narration.time ? `（目安: ${narration.time}）` : "";
    children.push(new Paragraph({
      heading: HeadingLevel.HEADING_2,
      children: [
        new TextRun({ text: "話す内容" }),
        new TextRun({ text: " " + timeTag, bold: false, italics: true, color: GRAY_LIGHT, size: 20 }),
      ],
      spacing: { before: 240, after: 120 },
    }));
    for (const p of formatNarration(narration.lines)) children.push(p);
  }

  // 画面に出す要素
  const screen = s.sections["画面に出す要素"];
  if (screen) {
    children.push(new Paragraph({
      heading: HeadingLevel.HEADING_2,
      children: [new TextRun("画面に出す要素")],
      spacing: { before: 240, after: 120 },
    }));
    for (const p of formatBullets(screen.lines)) children.push(p);
  }

  // 想定質問と回答
  const qa = s.sections["想定質問と回答"];
  if (qa) {
    children.push(new Paragraph({
      heading: HeadingLevel.HEADING_2,
      children: [new TextRun("想定質問と回答")],
      spacing: { before: 240, after: 120 },
    }));
    for (const p of formatQA(qa.lines)) children.push(p);
  }

  // スライド終端の薄い区切り線
  children.push(new Paragraph({
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "CBD5E1" } },
    spacing: { before: 200, after: 280 },
  }));
}

// =============================================================================
// ----- 反論章: 「木曜前倒し＝マイナスベッド」への懸念と回答 -----
// =============================================================================
children.push(new Paragraph({ children: [new PageBreak()] }));
children.push(new Paragraph({
  heading: HeadingLevel.HEADING_1,
  children: [
    new Bookmark({
      id: "rebuttal",
      children: [new TextRun("【重要】Slide 15 補足 — 「木曜前倒し＝マイナスベッド」への回答")],
    }),
  ],
  spacing: { before: 200, after: 200 },
}));

// 導入文
children.push(paragraph(
  "Slide 15 でご提案いたしました「金曜・土曜退院を木曜に前倒しする」という運用変更につきまして、現場の多くの方がまず感じられる違和感は、まさに **「それは病棟のベッドを早く空けるだけで、**マイナス**ではないか？」** というものでございます。"
));
children.push(paragraph(
  "看護部長、病棟師長、診療科の先生方、退院支援看護師・MSW、そして患者さんのご家族まで、多くの関係者にとって「木曜退院」は直感的に **「よくない話」** に感じられるのが自然なことと存じます。"
));
children.push(paragraph(
  "本章では、**この施策が「常識に反している」ように見えるにもかかわらず、データに照らすと合理的である** ことを、6 つの代表的な懸念に正面から回答する形で整理いたしました。経営会議での質疑応答、および運用開始時の現場説明にそのままお使いいただけます。"
));

// 核心の一言
children.push(new Paragraph({
  border: {
    top: { style: BorderStyle.SINGLE, size: 12, color: GOLD },
    bottom: { style: BorderStyle.SINGLE, size: 12, color: GOLD },
  },
  shading: { fill: "FFF8DC", type: ShadingType.CLEAR },
  children: [
    new TextRun({ text: "核心: ", bold: true, color: GOLD, size: 26 }),
    new TextRun({ text: "本施策は「入院日数を短くする」ものではない。「空床時間を短くする」ものである。", bold: true, color: NAVY, size: 26 }),
  ],
  spacing: { before: 240, after: 240, line: 360 },
  alignment: AlignmentType.LEFT,
}));
children.push(paragraph(
  "同じ患者さんの在院日数は **1日しか変わりません**。しかし、その患者さんが退いたベッドが、次の入院患者さんを受け入れるまでの **「空床時間」** は、金曜退院なら 2.5〜3 日（土日月）、木曜退院なら 0.5〜1 日（木曜午後〜金曜午前）となり、**5倍以上の差** が生じます。この「空床時間の短縮」こそが、年間 1,000 万円の吸収効果の源泉でございます。"
));

// 6つの懸念と回答
const rebuttals = [
  {
    num: "1",
    title: "「退院を早めたらベッド稼働率が下がる」のでは？",
    common: "常識的感覚: 入院日数が短くなる → 稼働率（延べ在院日数 ÷ 延べ病床数）は下がるはず。",
    data: [
      "対象となる患者さんの在院日数は **1日しか変わりません**（金曜退院 → 木曜退院）。",
      "一方で、空床時間は **2.5 日 → 0.5 日** に短縮されます（緊急入院で同日充填される場合）。",
      "稼働率は **「延べ在院日数 ÷ 延べ病床日数」** で計算されるため、**空床時間が減る = 延べ在院日数が増える = 稼働率は逆に上がります**。",
      "試算: 月 20 名に適用した場合、4床 × 2日 × 月4週 = **年間 約 400 病床日の追加稼働** ≒ 500〜580 万円の収益増。",
    ],
    conclusion: "**稼働率は下がりません。むしろ上がります。** 直感とは逆の結論ですが、「在院日数」と「稼働率」の定義を丁寧に追うと確認できます。",
  },
  {
    num: "2",
    title: "「金曜に入院が入ってこなければ、木曜退院の床は空のままになる」のでは？",
    common: "常識的感覚: 緊急入院は予測不能。木曜に退院させても入院が入ってくる保証はない。",
    data: [
      "過去 12ヶ月の実績では、**木曜の平均入院数は 6.2件/日**（予定 2.8 件 + 緊急 3.3 件）でございます。",
      "緊急入院の **64% が日中 13〜18時** に集中しています（694/1,081 件）。木曜朝に退院させた床は、同日午後の緊急入院で埋まる時間的余裕が **十分** にございます。",
      "**木曜に 3件 以上入院があった日は、過去 51週中 49週（96.1%）**。 空床が「埋まらなかった」ケースは統計的に稀でございます。",
      "深夜 0〜5時の緊急入院は年間 **わずか 5件**、夜間 19時以降も 21件のみ。「夜中にどんどん来る」は誤認です。",
    ],
    conclusion: "**木曜退院の床が空のまま金曜を迎える確率は、統計的に極めて低い** ことが、過去 12ヶ月のデータで裏付けられます。",
  },
  {
    num: "3",
    title: "「DPC 入院期間 II を減らしたら、出来高の逓減がキツくなってマイナスでは？」",
    common: "常識的感覚: 入院期間を短くすると、DPC の高点数期間（II 期）の収益が削られる。",
    data: [
      "対象は **「医学的に木曜退院が可能で、既に入院期間 II〜III の境界付近にいる患者さん」** のみでございます。",
      "既に点数が逓減領域（III 期）に入った患者さんを 1 日早く退院させても、**収益影響はほぼニュートラル** でございます。",
      "そして重要なのは、**退院した床に新規入院患者さんが入れば、その方は入院期間 I の高点数期間から始まる** ということです。",
      "試算: 1件の新規入院 × 入院期間 I の初日〜5日目の高点数分 ≒ **1件あたり約 10〜13 万円** の追加収益。年間 70〜80件の新規入院追加で **年 800 万円+** の潜在。",
    ],
    conclusion: "**DPC 出来高はむしろプラス方向** に作用すると試算されます。対象患者の選定基準（II/III 境界付近）が鍵です。",
  },
  {
    num: "4",
    title: "「患者さん・ご家族は金曜退院を希望している」と言われる ← これが一番の壁では？",
    common: "常識的感覚: ご家族は週末から家事・介護体制を整えたい。木曜退院は「押し付け」になる。",
    data: [
      "**対象は「医学的に木曜退院が可能で、かつご本人・ご家族が了解した患者さん」のみ** でございます。ご希望を無視して動かすわけではございません。",
      "運用設計では、**入院初日に主治医から退院目処を説明** し、**水曜カンファレンスで「木曜退院も選択肢ですよ」とご提示** するステップを組み込みます。",
      "当院の現場感覚として、**入院目的の治療が完了している患者さんの 6〜7 割は、曜日に強いこだわりを持たない** と推定されます（退院支援看護師ヒアリング）。",
      "残り 3〜4 割は金曜退院を希望される方、または月曜以降にご事情がある方。その方々はそのまま金曜退院で構いません。",
    ],
    conclusion: "**「全員を木曜に動かす」施策ではありません。** 「木曜退院でも良い方を選び、その方だけ早める」施策です。",
  },
  {
    num: "5",
    title: "「看護師・MSW の退院調整業務は金曜午前に慣れている。運用変更で混乱する」のでは？",
    common: "常識的感覚: 慣習の変更は必ず混乱とミスを生む。現場負担は追加の残業になる。",
    data: [
      "変更内容は **「退院支援会議を水曜 → 火曜午後に 1時間シフト」** のみ。新規業務の追加はございません。",
      "退院前カンファレンスのテンプレートは既存のものをそのまま転用します。",
      "**3ヶ月間の試験運用** で、残業時間・在宅復帰率・患者満足度を日次モニタリング。",
      "**ロールバック基準を事前に明示**: ① 土日空床が 4週連続で悪化、② 在宅復帰率 3% 以上低下、③ 残業時間 月 20時間以上増加 — いずれか 1 つで即中止。",
    ],
    conclusion: "**実装コストは低く、失敗時の撤退も早い設計** になっております。「取り返しのつかない」変更ではございません。",
  },
  {
    num: "6",
    title: "「試しに木曜退院を増やしても、本当に改善したか分からない」のでは？",
    common: "常識的感覚: 改善のように見えて実は季節変動や偶然かもしれない。評価軸がないと判断不能。",
    data: [
      "**日次自動計測 4 指標** を予め定義いたします: ① 土日平均空床数（目標 16 → 12床）、② 木曜退院数（試験運用で何名シフトされたか）、③ 在宅復帰率（悪化しないか）、④ 退院支援スタッフ残業時間（持続可能性）。",
      "**対照群との比較**: 試験運用 3ヶ月の実測を、前年同期 3ヶ月の実測と並べて差分評価いたします。",
      "**ダッシュボード化** し、毎週自動更新。月末に経営会議に数値報告を行います（Phase 3 で既存のベッドコントロールアプリ v3.5 に統合予定）。",
      "改善が認められない場合、**経営会議で継続・中止・修正を判断** いたします。現場判断で勝手に続けることはございません。",
    ],
    conclusion: "**「感覚」ではなく「数字」で判定する設計** になっております。理事会への定期報告も含めた透明性を確保いたします。",
  },
];

for (const r of rebuttals) {
  // 懸念タイトル
  children.push(new Paragraph({
    heading: HeadingLevel.HEADING_2,
    children: [
      new TextRun({ text: `懸念 ${r.num}: `, color: "C73E1D" }),
      new TextRun({ text: r.title }),
    ],
    spacing: { before: 320, after: 120 },
  }));
  // 常識的感覚
  children.push(new Paragraph({
    children: [
      new TextRun({ text: "💭 ", size: 22 }),
      new TextRun({ text: r.common, italics: true, color: GRAY }),
    ],
    shading: { fill: "F5F5F0", type: ShadingType.CLEAR },
    spacing: { before: 100, after: 160, line: 320 },
    indent: { left: 120 },
  }));
  // データに基づく回答
  children.push(new Paragraph({
    children: [
      new TextRun({ text: "📊 データに基づく回答", bold: true, color: NAVY, size: 22 }),
    ],
    spacing: { before: 100, after: 80 },
  }));
  for (const d of r.data) {
    children.push(bulletItem(d));
  }
  // 結論
  children.push(new Paragraph({
    children: [
      new TextRun({ text: "→ ", bold: true, color: "4CAF50", size: 24 }),
      ...parseInlineBold(r.conclusion, { color: NAVY }),
    ],
    shading: { fill: "E8F5E9", type: ShadingType.CLEAR },
    border: { left: { style: BorderStyle.SINGLE, size: 18, color: "4CAF50" } },
    spacing: { before: 120, after: 200, line: 340 },
    indent: { left: 120 },
  }));
}

// 総まとめ
children.push(new Paragraph({
  heading: HeadingLevel.HEADING_2,
  children: [new TextRun("総まとめ: 「常識との乖離」を超えて、合理的な意思決定へ")],
  spacing: { before: 300, after: 120 },
}));
children.push(paragraph(
  "本施策の本質は、次の 3 つの認識の転換にございます。"
));
children.push(bulletItem("① **「入院日数」ではなく「空床時間」** を指標にする（患者さんの在院は 1日しか変わらないが、ベッドの稼働時間は 2〜3日増える）"));
children.push(bulletItem("② **「全員に一律」ではなく「選択と合意」** で動かす（医学的適応と患者合意を前提にした対象選定）"));
children.push(bulletItem("③ **「感覚的な良否」ではなく「数字でのモニタリング」** で判定する（4指標の日次監視 + 月次報告 + 即ロールバック基準）"));
children.push(paragraph(
  "いずれも「現場を責める」話ではなく、**「現場の努力を数字で正当化する」** 話でございます。これまで金曜退院集中に貢献してきた運用は、曜日の慣習がもたらした結果であって、個々の判断の誤りではございません。本施策は、**運用の慣習を data-driven に微調整する** ことで、現場の負担を増やさず、経営上の空床ロスを取り戻すことを目指しております。"
));
children.push(paragraph(
  "ご質問・ご懸念がございましたら、本章の該当懸念 (1〜6) でそのまま回答申し上げます。"
));

// =============================================================================
// ----- 補足資料 -----
if (appendixLines.length > 0) {
  children.push(new Paragraph({ children: [new PageBreak()] }));
  children.push(new Paragraph({
    heading: HeadingLevel.HEADING_1,
    children: [
      new Bookmark({
        id: "appendix",
        children: [new TextRun("補足資料（質疑が深まった場合のバックアップ）")],
      }),
    ],
    spacing: { before: 200, after: 200 },
  }));

  // 単純にサブ見出し・箇条書きに分解
  let currentSubHeading = null;
  let buffer = [];
  const flushBuf = () => {
    if (buffer.length) {
      for (const p of formatBullets(buffer)) children.push(p);
      buffer = [];
    }
  };
  for (const line of appendixLines) {
    const sub3 = line.match(/^###\s+(.+)$/);
    if (sub3) {
      flushBuf();
      children.push(new Paragraph({
        heading: HeadingLevel.HEADING_2,
        children: [new TextRun(sub3[1].trim())],
        spacing: { before: 240, after: 120 },
      }));
    } else if (/^---\s*$/.test(line)) {
      flushBuf();
    } else {
      buffer.push(line);
    }
  }
  flushBuf();
}

// =============================================================================
// テーブルボーダ ヘルパ
// =============================================================================
function makeBorders() {
  const b = { style: BorderStyle.SINGLE, size: 4, color: "D1D5DB" };
  return { top: b, bottom: b, left: b, right: b };
}

// =============================================================================
// Document 組み立て
// =============================================================================
const doc = new Document({
  creator: "副院長  久保田  徹",
  title: "週末・大型連休の稼働率対策 — スライド解説書",
  description: "経営陣向けプレゼンテーションの発表台本・Q&A 集",
  styles: {
    default: {
      document: {
        run: { font: "Yu Gothic", size: 22 },  // 11pt 本文
      },
    },
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 34, bold: true, color: NAVY, font: "Yu Gothic UI" },
        paragraph: {
          spacing: { before: 400, after: 200 },
          outlineLevel: 0,
          border: { bottom: { style: BorderStyle.SINGLE, size: 18, color: GOLD, space: 4 } },
        },
      },
      {
        id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, color: NAVY, font: "Yu Gothic UI" },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 1 },
      },
      {
        id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 22, bold: true, color: GRAY, font: "Yu Gothic UI" },
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
          { level: 2, format: LevelFormat.BULLET, text: "▪", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 1120, hanging: 240 } } } },
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
            new TextRun({ text: "週末・大型連休の稼働率対策 — 解説書", color: GRAY_LIGHT, size: 18 }),
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
  console.log(`   slides parsed: ${slides.length}`);
  console.log(`   output bytes: ${buffer.length}`);
}).catch((err) => {
  console.error("❌ Error:", err);
  process.exit(1);
});
