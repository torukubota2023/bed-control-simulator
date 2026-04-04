const pptxgen = require("pptxgenjs");

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.author = "おもろまちメディカルセンター";
pres.title = "ベッドコントロール見える化アプリの進化";

// Color palette - Midnight Executive with medical blue accent
const C = {
  navy: "1A2744",
  darkNavy: "0F1A2E",
  blue: "2563EB",
  lightBlue: "3B82F6",
  accent: "F59E0B",
  gold: "F59E0B",
  white: "FFFFFF",
  offWhite: "F8FAFC",
  lightGray: "E2E8F0",
  medGray: "94A3B8",
  darkText: "1E293B",
  subText: "64748B",
  green: "10B981",
  red: "EF4444",
  orange: "F97316",
};

const makeShadow = () => ({
  type: "outer",
  blur: 8,
  offset: 2,
  angle: 135,
  color: "000000",
  opacity: 0.12,
});

// ============================================================
// SLIDE 1: Title
// ============================================================
let slide1 = pres.addSlide();
slide1.background = { color: C.navy };

// Decorative top accent bar
slide1.addShape(pres.shapes.RECTANGLE, {
  x: 0, y: 0, w: 10, h: 0.06, fill: { color: C.gold },
});

// Main title
slide1.addText("ベッドコントロール\n見える化アプリの進化", {
  x: 0.8, y: 1.0, w: 8.4, h: 2.2,
  fontSize: 40, fontFace: "Arial Black",
  color: C.white, bold: true, lineSpacingMultiple: 1.2,
});

// Subtitle with accent
slide1.addShape(pres.shapes.RECTANGLE, {
  x: 0.8, y: 3.3, w: 0.6, h: 0.06, fill: { color: C.gold },
});

slide1.addText("精神論から、数字へ。", {
  x: 0.8, y: 3.5, w: 8.4, h: 0.8,
  fontSize: 28, fontFace: "Georgia",
  color: C.gold, italic: true,
});

// Footer
slide1.addText("おもろまちメディカルセンター  |  2026年4月", {
  x: 0.8, y: 4.8, w: 8.4, h: 0.5,
  fontSize: 14, fontFace: "Calibri",
  color: C.medGray,
});

// ============================================================
// SLIDE 2: 現状の課題
// ============================================================
let slide2 = pres.addSlide();
slide2.background = { color: C.offWhite };

slide2.addText("現状の課題", {
  x: 0.6, y: 0.3, w: 8.8, h: 0.7,
  fontSize: 32, fontFace: "Arial Black", color: C.navy, margin: 0,
});

slide2.addShape(pres.shapes.RECTANGLE, {
  x: 0.6, y: 1.0, w: 1.2, h: 0.05, fill: { color: C.gold },
});

// Card 1
slide2.addShape(pres.shapes.RECTANGLE, {
  x: 0.6, y: 1.4, w: 2.7, h: 2.8,
  fill: { color: C.white }, shadow: makeShadow(),
});
slide2.addShape(pres.shapes.RECTANGLE, {
  x: 0.6, y: 1.4, w: 2.7, h: 0.06, fill: { color: C.red },
});
slide2.addText("精神論の限界", {
  x: 0.8, y: 1.7, w: 2.3, h: 0.5,
  fontSize: 18, fontFace: "Calibri", color: C.navy, bold: true,
});
slide2.addText([
  { text: "「稼働率を上げよう！」", options: { breakLine: true } },
  { text: "という掛け声だけ。", options: { breakLine: true } },
  { text: "", options: { breakLine: true } },
  { text: "具体的な数値目標も", options: { breakLine: true } },
  { text: "改善策もなし。", options: {} },
], {
  x: 0.8, y: 2.3, w: 2.3, h: 1.8,
  fontSize: 13, fontFace: "Calibri", color: C.subText, lineSpacingMultiple: 1.4,
});

// Card 2
slide2.addShape(pres.shapes.RECTANGLE, {
  x: 3.65, y: 1.4, w: 2.7, h: 2.8,
  fill: { color: C.white }, shadow: makeShadow(),
});
slide2.addShape(pres.shapes.RECTANGLE, {
  x: 3.65, y: 1.4, w: 2.7, h: 0.06, fill: { color: C.orange },
});
slide2.addText("価値が不透明", {
  x: 3.85, y: 1.7, w: 2.3, h: 0.5,
  fontSize: 18, fontFace: "Calibri", color: C.navy, bold: true,
});
slide2.addText([
  { text: "稼働率1%の価値を", options: { breakLine: true } },
  { text: "経営陣含め誰も", options: { breakLine: true } },
  { text: "具体的に知らない。", options: { breakLine: true } },
  { text: "", options: { breakLine: true } },
  { text: "運営会議で話題に", options: { breakLine: true } },
  { text: "なったことがない。", options: {} },
], {
  x: 3.85, y: 2.3, w: 2.3, h: 1.8,
  fontSize: 13, fontFace: "Calibri", color: C.subText, lineSpacingMultiple: 1.4,
});

// Card 3
slide2.addShape(pres.shapes.RECTANGLE, {
  x: 6.7, y: 1.4, w: 2.7, h: 2.8,
  fill: { color: C.white }, shadow: makeShadow(),
});
slide2.addShape(pres.shapes.RECTANGLE, {
  x: 6.7, y: 1.4, w: 2.7, h: 0.06, fill: { color: C.blue },
});
slide2.addText("行動が見えない", {
  x: 6.9, y: 1.7, w: 2.3, h: 0.5,
  fontSize: 18, fontFace: "Calibri", color: C.navy, bold: true,
});
slide2.addText([
  { text: "医師別の入退院パターン、", options: { breakLine: true } },
  { text: "入院創出の貢献、", options: { breakLine: true } },
  { text: "退院曜日の偏在——", options: { breakLine: true } },
  { text: "", options: { breakLine: true } },
  { text: "誰でも気づいているが", options: { breakLine: true } },
  { text: "データで示せない。", options: {} },
], {
  x: 6.9, y: 2.3, w: 2.3, h: 1.8,
  fontSize: 13, fontFace: "Calibri", color: C.subText, lineSpacingMultiple: 1.4,
});

// Bottom quote
slide2.addText("「この病院はおかしい」—— そう言われないために、数字で語る仕組みが必要。", {
  x: 0.6, y: 4.6, w: 8.8, h: 0.5,
  fontSize: 14, fontFace: "Georgia", color: C.navy, italic: true,
});

// ============================================================
// SLIDE 3: 稼働率1%の価値（インパクトスライド）
// ============================================================
let slide3 = pres.addSlide();
slide3.background = { color: C.navy };

slide3.addText("稼働率 1% の価値を知っていますか？", {
  x: 0.6, y: 0.3, w: 8.8, h: 0.7,
  fontSize: 28, fontFace: "Arial Black", color: C.white, margin: 0,
});

slide3.addShape(pres.shapes.RECTANGLE, {
  x: 0.6, y: 1.0, w: 1.2, h: 0.05, fill: { color: C.gold },
});

// Calculation flow
slide3.addText("94床", {
  x: 0.6, y: 1.4, w: 1.8, h: 0.8,
  fontSize: 32, fontFace: "Arial Black", color: C.lightBlue, align: "center", valign: "middle",
});
slide3.addText("病床数", {
  x: 0.6, y: 2.1, w: 1.8, h: 0.4,
  fontSize: 12, fontFace: "Calibri", color: C.medGray, align: "center",
});

slide3.addText("\u00D7", {
  x: 2.4, y: 1.5, w: 0.5, h: 0.6,
  fontSize: 24, fontFace: "Calibri", color: C.medGray, align: "center", valign: "middle",
});

slide3.addText("1%", {
  x: 2.9, y: 1.4, w: 1.2, h: 0.8,
  fontSize: 32, fontFace: "Arial Black", color: C.lightBlue, align: "center", valign: "middle",
});
slide3.addText("稼働率UP", {
  x: 2.9, y: 2.1, w: 1.2, h: 0.4,
  fontSize: 12, fontFace: "Calibri", color: C.medGray, align: "center",
});

slide3.addText("\u00D7", {
  x: 4.1, y: 1.5, w: 0.5, h: 0.6,
  fontSize: 24, fontFace: "Calibri", color: C.medGray, align: "center", valign: "middle",
});

slide3.addText("365日", {
  x: 4.6, y: 1.4, w: 1.4, h: 0.8,
  fontSize: 32, fontFace: "Arial Black", color: C.lightBlue, align: "center", valign: "middle",
});

slide3.addText("\u00D7", {
  x: 6.0, y: 1.5, w: 0.5, h: 0.6,
  fontSize: 24, fontFace: "Calibri", color: C.medGray, align: "center", valign: "middle",
});

slide3.addText("\u00A530,500", {
  x: 6.5, y: 1.4, w: 2.0, h: 0.8,
  fontSize: 32, fontFace: "Arial Black", color: C.lightBlue, align: "center", valign: "middle",
});
slide3.addText("1日単価", {
  x: 6.5, y: 2.1, w: 2.0, h: 0.4,
  fontSize: 12, fontFace: "Calibri", color: C.medGray, align: "center",
});

// Arrow
slide3.addText("\u25BC", {
  x: 3.5, y: 2.5, w: 3.0, h: 0.5,
  fontSize: 24, fontFace: "Calibri", color: C.gold, align: "center",
});

// Big number result
slide3.addShape(pres.shapes.RECTANGLE, {
  x: 1.5, y: 3.1, w: 7.0, h: 1.6,
  fill: { color: "1E3A5F" },
});

slide3.addText([
  { text: "年間 ", options: { fontSize: 24, color: C.white } },
  { text: "1,046", options: { fontSize: 60, color: C.gold, bold: true } },
  { text: " 万円", options: { fontSize: 24, color: C.white } },
], {
  x: 1.5, y: 3.1, w: 7.0, h: 1.0,
  fontFace: "Arial Black", align: "center", valign: "middle",
});

slide3.addText("= 年間黒字額 3,550万円 の 29% 相当", {
  x: 1.5, y: 4.0, w: 7.0, h: 0.5,
  fontSize: 18, fontFace: "Calibri", color: C.lightBlue, align: "center", bold: true,
});

// Footer note
slide3.addText("たった1%の改善が、年間黒字額の約3分の1に匹敵する。", {
  x: 0.6, y: 4.9, w: 8.8, h: 0.4,
  fontSize: 14, fontFace: "Georgia", color: C.medGray, italic: true,
});

// ============================================================
// SLIDE 4: 令和7年度実績
// ============================================================
let slide4 = pres.addSlide();
slide4.background = { color: C.offWhite };

slide4.addText("令和7年度 経営実績", {
  x: 0.6, y: 0.3, w: 8.8, h: 0.7,
  fontSize: 32, fontFace: "Arial Black", color: C.navy, margin: 0,
});

slide4.addShape(pres.shapes.RECTANGLE, {
  x: 0.6, y: 1.0, w: 1.2, h: 0.05, fill: { color: C.gold },
});

// Left column - big metrics
const metrics = [
  { label: "売上高", value: "30\u51847,890\u4E07\u5186", y: 1.4 },
  { label: "年間黒字額", value: "3,550\u4E07\u5186", y: 2.5 },
  { label: "黒字率", value: "1.15%", y: 3.6 },
];

metrics.forEach((m) => {
  slide4.addShape(pres.shapes.RECTANGLE, {
    x: 0.6, y: m.y, w: 4.2, h: 0.9,
    fill: { color: C.white }, shadow: makeShadow(),
  });
  slide4.addShape(pres.shapes.RECTANGLE, {
    x: 0.6, y: m.y, w: 0.08, h: 0.9, fill: { color: C.blue },
  });
  slide4.addText(m.label, {
    x: 0.9, y: m.y + 0.05, w: 1.5, h: 0.4,
    fontSize: 12, fontFace: "Calibri", color: C.subText,
  });
  slide4.addText(m.value, {
    x: 0.9, y: m.y + 0.35, w: 3.7, h: 0.5,
    fontSize: 22, fontFace: "Arial Black", color: C.navy,
  });
});

// Right column
const metrics2 = [
  { label: "人件費率", value: "58%", y: 1.4 },
  { label: "地域包括医療病棟 稼働率", value: "89%", y: 2.5 },
  { label: "職員数", value: "290\u540D", y: 3.6 },
];

metrics2.forEach((m) => {
  slide4.addShape(pres.shapes.RECTANGLE, {
    x: 5.2, y: m.y, w: 4.2, h: 0.9,
    fill: { color: C.white }, shadow: makeShadow(),
  });
  slide4.addShape(pres.shapes.RECTANGLE, {
    x: 5.2, y: m.y, w: 0.08, h: 0.9, fill: { color: C.green },
  });
  slide4.addText(m.label, {
    x: 5.5, y: m.y + 0.05, w: 3.0, h: 0.4,
    fontSize: 12, fontFace: "Calibri", color: C.subText,
  });
  slide4.addText(m.value, {
    x: 5.5, y: m.y + 0.35, w: 3.7, h: 0.5,
    fontSize: 22, fontFace: "Arial Black", color: C.navy,
  });
});

// Bottom insight
slide4.addShape(pres.shapes.RECTANGLE, {
  x: 0.6, y: 4.7, w: 8.8, h: 0.6,
  fill: { color: C.navy },
});
slide4.addText("稼働率目標 90% まで、あと 1%。 その 1% = 年間 1,046万円。", {
  x: 0.8, y: 4.7, w: 8.4, h: 0.6,
  fontSize: 16, fontFace: "Calibri", color: C.gold, bold: true, valign: "middle",
});

// ============================================================
// SLIDE 5: 新機能① 常時表示の基盤指標
// ============================================================
let slide5 = pres.addSlide();
slide5.background = { color: C.offWhite };

slide5.addText("新機能 1", {
  x: 0.6, y: 0.3, w: 2.0, h: 0.7,
  fontSize: 14, fontFace: "Calibri", color: C.blue, bold: true,
});
slide5.addText("常時表示の基盤指標", {
  x: 0.6, y: 0.6, w: 8.8, h: 0.7,
  fontSize: 30, fontFace: "Arial Black", color: C.navy, margin: 0,
});
slide5.addShape(pres.shapes.RECTANGLE, {
  x: 0.6, y: 1.3, w: 1.2, h: 0.05, fill: { color: C.gold },
});

// Mock app header
slide5.addShape(pres.shapes.RECTANGLE, {
  x: 1.0, y: 1.8, w: 8.0, h: 0.8,
  fill: { color: C.navy }, shadow: makeShadow(),
});
slide5.addText([
  { text: "現在の稼働率 ", options: { fontSize: 16, color: C.white } },
  { text: "89%", options: { fontSize: 22, color: C.gold, bold: true } },
  { text: "  |  あと1%で年間 ", options: { fontSize: 16, color: C.white } },
  { text: "+1,046万円", options: { fontSize: 22, color: C.gold, bold: true } },
  { text: " （年間黒字額の29%相当）", options: { fontSize: 13, color: C.lightBlue } },
], {
  x: 1.0, y: 1.8, w: 8.0, h: 0.8,
  fontFace: "Calibri", align: "center", valign: "middle",
});

// Description
slide5.addText("どのタブを見ていても、常に目に入る位置に表示", {
  x: 1.0, y: 2.8, w: 8.0, h: 0.5,
  fontSize: 16, fontFace: "Calibri", color: C.navy, align: "center", bold: true,
});

// Benefits
const benefits5 = [
  { title: "全員が共通認識を持つ", desc: "稼働率1%の経済的インパクトを全職員が理解" },
  { title: "日々の判断が変わる", desc: "入退院の判断が「金額」と紐づいて意識される" },
  { title: "目標が具体的になる", desc: "「あと1%」が精神論ではなく経営数値として語られる" },
];

benefits5.forEach((b, i) => {
  const x = 0.6 + i * 3.1;
  slide5.addShape(pres.shapes.RECTANGLE, {
    x: x, y: 3.5, w: 2.8, h: 1.6,
    fill: { color: C.white }, shadow: makeShadow(),
  });
  slide5.addShape(pres.shapes.RECTANGLE, {
    x: x, y: 3.5, w: 2.8, h: 0.06, fill: { color: C.blue },
  });
  slide5.addText(b.title, {
    x: x + 0.15, y: 3.7, w: 2.5, h: 0.5,
    fontSize: 15, fontFace: "Calibri", color: C.navy, bold: true,
  });
  slide5.addText(b.desc, {
    x: x + 0.15, y: 4.2, w: 2.5, h: 0.7,
    fontSize: 12, fontFace: "Calibri", color: C.subText, lineSpacingMultiple: 1.4,
  });
});

// ============================================================
// SLIDE 6: 新機能② 「改善のヒント」
// ============================================================
let slide6 = pres.addSlide();
slide6.background = { color: C.offWhite };

slide6.addText("新機能 2", {
  x: 0.6, y: 0.3, w: 2.0, h: 0.5,
  fontSize: 14, fontFace: "Calibri", color: C.blue, bold: true,
});
slide6.addText("「改善のヒント」自動検出", {
  x: 0.6, y: 0.6, w: 8.8, h: 0.7,
  fontSize: 30, fontFace: "Arial Black", color: C.navy, margin: 0,
});
slide6.addShape(pres.shapes.RECTANGLE, {
  x: 0.6, y: 1.3, w: 1.2, h: 0.05, fill: { color: C.gold },
});

// Hint card mock 1
slide6.addShape(pres.shapes.RECTANGLE, {
  x: 0.6, y: 1.6, w: 4.2, h: 1.8,
  fill: { color: C.white }, shadow: makeShadow(),
});
slide6.addShape(pres.shapes.RECTANGLE, {
  x: 0.6, y: 1.6, w: 0.08, h: 1.8, fill: { color: C.orange },
});
slide6.addText("金曜退院の集中", {
  x: 0.9, y: 1.7, w: 3.7, h: 0.4,
  fontSize: 16, fontFace: "Calibri", color: C.navy, bold: true,
});
slide6.addText([
  { text: "先月の金曜退院は32件（全体の40%）", options: { breakLine: true } },
  { text: "土日の平均稼働率が82%に低下", options: { breakLine: true } },
  { text: "", options: { breakLine: true } },
  { text: "年間推定ロス: 576万円", options: { bold: true, color: C.red, breakLine: true } },
  { text: "（年間黒字額の16%相当）", options: { color: C.red } },
], {
  x: 0.9, y: 2.15, w: 3.7, h: 1.2,
  fontSize: 12, fontFace: "Calibri", color: C.subText, lineSpacingMultiple: 1.5,
});

// Hint card mock 2
slide6.addShape(pres.shapes.RECTANGLE, {
  x: 5.2, y: 1.6, w: 4.2, h: 1.8,
  fill: { color: C.white }, shadow: makeShadow(),
});
slide6.addShape(pres.shapes.RECTANGLE, {
  x: 5.2, y: 1.6, w: 0.08, h: 1.8, fill: { color: C.green },
});
slide6.addText("入院創出の貢献", {
  x: 5.5, y: 1.7, w: 3.7, h: 0.4,
  fontSize: 16, fontFace: "Calibri", color: C.navy, bold: true,
});
slide6.addText([
  { text: "C先生の入院創出: 月12件（前月比+4件）", options: { breakLine: true } },
  { text: "稼働率への貢献: +0.3%", options: { breakLine: true } },
  { text: "", options: { breakLine: true } },
  { text: "年間換算: +334万円の売上貢献", options: { bold: true, color: C.green } },
], {
  x: 5.5, y: 2.15, w: 3.7, h: 1.2,
  fontSize: 12, fontFace: "Calibri", color: C.subText, lineSpacingMultiple: 1.5,
});

// Design philosophy
slide6.addText("設計思想: データが問いかける仕組み", {
  x: 0.6, y: 3.7, w: 8.8, h: 0.5,
  fontSize: 18, fontFace: "Calibri", color: C.navy, bold: true,
});

const philosophy = [
  { num: "1", text: "何が起きているか\n事実の提示" },
  { num: "2", text: "いくらの影響か\n金額換算" },
  { num: "3", text: "年間黒字額の何%か\n比率で実感" },
  { num: "4", text: "どうすれば良いか\n改善策の提示" },
];

philosophy.forEach((p, i) => {
  const x = 0.6 + i * 2.35;
  slide6.addShape(pres.shapes.RECTANGLE, {
    x: x, y: 4.3, w: 2.1, h: 1.0,
    fill: { color: C.white }, shadow: makeShadow(),
  });
  slide6.addShape(pres.shapes.OVAL, {
    x: x + 0.1, y: 4.4, w: 0.35, h: 0.35,
    fill: { color: C.blue },
  });
  slide6.addText(p.num, {
    x: x + 0.1, y: 4.4, w: 0.35, h: 0.35,
    fontSize: 14, fontFace: "Calibri", color: C.white, bold: true, align: "center", valign: "middle",
  });
  slide6.addText(p.text, {
    x: x + 0.5, y: 4.35, w: 1.5, h: 0.9,
    fontSize: 11, fontFace: "Calibri", color: C.darkText, lineSpacingMultiple: 1.3,
  });
});

// ============================================================
// SLIDE 7: 新機能③ 医師別分析
// ============================================================
let slide7 = pres.addSlide();
slide7.background = { color: C.offWhite };

slide7.addText("新機能 3", {
  x: 0.6, y: 0.3, w: 2.0, h: 0.5,
  fontSize: 14, fontFace: "Calibri", color: C.blue, bold: true,
});
slide7.addText("医師別分析", {
  x: 0.6, y: 0.6, w: 8.8, h: 0.7,
  fontSize: 30, fontFace: "Arial Black", color: C.navy, margin: 0,
});
slide7.addShape(pres.shapes.RECTANGLE, {
  x: 0.6, y: 1.3, w: 1.2, h: 0.05, fill: { color: C.gold },
});

// Input flow
slide7.addText("入院時の入力フロー（プルダウン選択のみ）", {
  x: 0.6, y: 1.5, w: 8.8, h: 0.5,
  fontSize: 16, fontFace: "Calibri", color: C.navy, bold: true,
});

const steps = [
  { step: "STEP 1", label: "入院経路", ex: "外来紹介 / 救急\n連携室 / ウォークイン" },
  { step: "STEP 2", label: "入院創出医", ex: "入院を生んだ医師\n（いれば選択）" },
  { step: "STEP 3", label: "入院担当医", ex: "病棟で受け持つ\n主治医" },
];

steps.forEach((s, i) => {
  const x = 0.6 + i * 3.1;
  slide7.addShape(pres.shapes.RECTANGLE, {
    x: x, y: 2.1, w: 2.8, h: 1.5,
    fill: { color: C.white }, shadow: makeShadow(),
  });
  slide7.addShape(pres.shapes.RECTANGLE, {
    x: x, y: 2.1, w: 2.8, h: 0.06, fill: { color: C.blue },
  });
  slide7.addText(s.step, {
    x: x + 0.15, y: 2.2, w: 1.0, h: 0.3,
    fontSize: 10, fontFace: "Calibri", color: C.blue, bold: true,
  });
  slide7.addText(s.label, {
    x: x + 0.15, y: 2.5, w: 2.5, h: 0.4,
    fontSize: 16, fontFace: "Calibri", color: C.navy, bold: true,
  });
  slide7.addText(s.ex, {
    x: x + 0.15, y: 2.9, w: 2.5, h: 0.6,
    fontSize: 11, fontFace: "Calibri", color: C.subText, lineSpacingMultiple: 1.3,
  });

  // Arrow between steps
  if (i < 2) {
    slide7.addText("\u25B6", {
      x: x + 2.8, y: 2.5, w: 0.3, h: 0.5,
      fontSize: 14, fontFace: "Calibri", color: C.medGray, align: "center", valign: "middle",
    });
  }
});

// What this enables
slide7.addText("これだけで自動的に得られる分析", {
  x: 0.6, y: 3.9, w: 8.8, h: 0.5,
  fontSize: 16, fontFace: "Calibri", color: C.navy, bold: true,
});

const analyses = [
  "医師別の月間入院・退院件数",
  "医師別の退院曜日分布",
  "医師別の在院日数・フェーズ構成",
  "医師別の稼働貢献度（金額換算）",
  "入院経路別の件数推移",
  "入院創出医の貢献ランキング",
];

// 2 columns
analyses.forEach((a, i) => {
  const col = i < 3 ? 0 : 1;
  const row = i % 3;
  const x = 0.8 + col * 4.5;
  const y = 4.45 + row * 0.35;
  slide7.addText(a, {
    x: x, y: y, w: 4.0, h: 0.35,
    fontSize: 12, fontFace: "Calibri", color: C.darkText,
    bullet: true,
  });
});

// ============================================================
// SLIDE 8: 改善の積み重ね効果
// ============================================================
let slide8 = pres.addSlide();
slide8.background = { color: C.navy };

slide8.addText("改善の積み重ね効果", {
  x: 0.6, y: 0.3, w: 8.8, h: 0.7,
  fontSize: 32, fontFace: "Arial Black", color: C.white, margin: 0,
});
slide8.addShape(pres.shapes.RECTANGLE, {
  x: 0.6, y: 1.0, w: 1.2, h: 0.05, fill: { color: C.gold },
});

// Bar chart: stacked improvements
slide8.addChart(pres.charts.BAR, [
  {
    name: "改善効果（万円/年）",
    labels: ["退院曜日\n平準化", "空床ラグ\n短縮", "入院創出\n強化", "在院日数\n適正化"],
    values: [576, 334, 890, 445],
  },
], {
  x: 0.6, y: 1.3, w: 5.5, h: 3.5,
  barDir: "col",
  chartColors: [C.gold],
  chartArea: { fill: { color: C.navy }, roundedCorners: true },
  catAxisLabelColor: C.medGray,
  catAxisLabelFontSize: 10,
  valAxisLabelColor: C.medGray,
  valAxisLabelFontSize: 10,
  valGridLine: { color: "2A3F5F", size: 0.5 },
  catGridLine: { style: "none" },
  showValue: true,
  dataLabelPosition: "outEnd",
  dataLabelColor: C.gold,
  dataLabelFontSize: 14,
  showLegend: false,
  valAxisNumFmt: "#,##0",
});

// Right side: total
slide8.addShape(pres.shapes.RECTANGLE, {
  x: 6.5, y: 1.5, w: 3.2, h: 3.0,
  fill: { color: "1E3A5F" },
});
slide8.addText("合計改善ポテンシャル", {
  x: 6.5, y: 1.7, w: 3.2, h: 0.4,
  fontSize: 13, fontFace: "Calibri", color: C.medGray, align: "center",
});
slide8.addText("2,245", {
  x: 6.5, y: 2.2, w: 3.2, h: 1.0,
  fontSize: 52, fontFace: "Arial Black", color: C.gold, align: "center", valign: "middle",
});
slide8.addText("万円/年", {
  x: 6.5, y: 3.1, w: 3.2, h: 0.4,
  fontSize: 16, fontFace: "Calibri", color: C.white, align: "center",
});
slide8.addText("稼働率換算: 約+2%", {
  x: 6.5, y: 3.5, w: 3.2, h: 0.4,
  fontSize: 14, fontFace: "Calibri", color: C.lightBlue, align: "center",
});

// Bottom note
slide8.addText("個別は小さくても、積み重ねれば年間黒字額の 63% に相当する改善余地がある。", {
  x: 0.6, y: 5.0, w: 8.8, h: 0.4,
  fontSize: 14, fontFace: "Georgia", color: C.medGray, italic: true,
});

// ============================================================
// SLIDE 9: 3ステップの体験
// ============================================================
let slide9 = pres.addSlide();
slide9.background = { color: C.offWhite };

slide9.addText("気づき \u2192 確認 \u2192 対話", {
  x: 0.6, y: 0.3, w: 8.8, h: 0.7,
  fontSize: 32, fontFace: "Arial Black", color: C.navy, margin: 0,
});
slide9.addShape(pres.shapes.RECTANGLE, {
  x: 0.6, y: 1.0, w: 1.2, h: 0.05, fill: { color: C.gold },
});

slide9.addText("データに基づく建設的な対話を生む3ステップ", {
  x: 0.6, y: 1.2, w: 8.8, h: 0.5,
  fontSize: 16, fontFace: "Calibri", color: C.subText,
});

// Step cards
const stepsData = [
  {
    num: "1", title: "気づき",
    desc: "「改善のヒント」が\n問題を自動で提示。\n\nアプリを開くだけで\n今日注目すべきことがわかる。",
    color: C.blue,
  },
  {
    num: "2", title: "確認",
    desc: "データとグラフで\n裏付けを自分の目で確認。\n\n医師別・曜日別の\nパターンが一目瞭然。",
    color: C.green,
  },
  {
    num: "3", title: "対話",
    desc: "根拠を持って相手に提示。\n\n「あなたの退院パターンが\n月○万円の影響です」と\n数字で対話できる。",
    color: C.gold,
  },
];

stepsData.forEach((s, i) => {
  const x = 0.6 + i * 3.1;
  slide9.addShape(pres.shapes.RECTANGLE, {
    x: x, y: 1.9, w: 2.8, h: 3.2,
    fill: { color: C.white }, shadow: makeShadow(),
  });

  // Number circle
  slide9.addShape(pres.shapes.OVAL, {
    x: x + 1.05, y: 2.1, w: 0.7, h: 0.7,
    fill: { color: s.color },
  });
  slide9.addText(s.num, {
    x: x + 1.05, y: 2.1, w: 0.7, h: 0.7,
    fontSize: 24, fontFace: "Arial Black", color: C.white, align: "center", valign: "middle",
  });

  slide9.addText(s.title, {
    x: x + 0.2, y: 2.9, w: 2.4, h: 0.5,
    fontSize: 22, fontFace: "Arial Black", color: C.navy, align: "center",
  });

  slide9.addText(s.desc, {
    x: x + 0.2, y: 3.4, w: 2.4, h: 1.6,
    fontSize: 12, fontFace: "Calibri", color: C.subText, lineSpacingMultiple: 1.4, align: "center",
  });

  // Arrow between cards
  if (i < 2) {
    slide9.addText("\u25B6", {
      x: x + 2.8, y: 3.1, w: 0.3, h: 0.5,
      fontSize: 18, fontFace: "Calibri", color: C.medGray, align: "center", valign: "middle",
    });
  }
});

// ============================================================
// SLIDE 10: 将来構想
// ============================================================
let slide10 = pres.addSlide();
slide10.background = { color: C.offWhite };

slide10.addText("将来構想", {
  x: 0.6, y: 0.3, w: 8.8, h: 0.7,
  fontSize: 32, fontFace: "Arial Black", color: C.navy, margin: 0,
});
slide10.addShape(pres.shapes.RECTANGLE, {
  x: 0.6, y: 1.0, w: 1.2, h: 0.05, fill: { color: C.gold },
});

// Phase 2
slide10.addShape(pres.shapes.RECTANGLE, {
  x: 0.6, y: 1.3, w: 4.2, h: 2.0,
  fill: { color: C.white }, shadow: makeShadow(),
});
slide10.addShape(pres.shapes.RECTANGLE, {
  x: 0.6, y: 1.3, w: 0.08, h: 2.0, fill: { color: C.blue },
});
slide10.addText("第2層: 改善仮説の保存・比較", {
  x: 0.9, y: 1.4, w: 3.7, h: 0.4,
  fontSize: 16, fontFace: "Calibri", color: C.navy, bold: true,
});
slide10.addText([
  { text: "What-if分析を「名前付き仮説」として保存", options: { bullet: true, breakLine: true } },
  { text: "複数仮説の同時シミュレーション", options: { bullet: true, breakLine: true } },
  { text: "改善の積み重ね効果を可視化", options: { bullet: true } },
], {
  x: 0.9, y: 1.9, w: 3.7, h: 1.2,
  fontSize: 12, fontFace: "Calibri", color: C.subText, lineSpacingMultiple: 1.6,
});

// Phase 3
slide10.addShape(pres.shapes.RECTANGLE, {
  x: 5.2, y: 1.3, w: 4.2, h: 2.0,
  fill: { color: C.white }, shadow: makeShadow(),
});
slide10.addShape(pres.shapes.RECTANGLE, {
  x: 5.2, y: 1.3, w: 0.08, h: 2.0, fill: { color: C.green },
});
slide10.addText("第3層: 提案書の自動生成", {
  x: 5.5, y: 1.4, w: 3.7, h: 0.4,
  fontSize: 16, fontFace: "Calibri", color: C.navy, bold: true,
});
slide10.addText([
  { text: "検証済み仮説を経営会議フォーマットに", options: { bullet: true, breakLine: true } },
  { text: "現状\u2192目標\u2192想定効果\u2192施策の構造", options: { bullet: true, breakLine: true } },
  { text: "PDF・院内メールで配布", options: { bullet: true } },
], {
  x: 5.5, y: 1.9, w: 3.7, h: 1.2,
  fontSize: 12, fontFace: "Calibri", color: C.subText, lineSpacingMultiple: 1.6,
});

// Role-based views
slide10.addText("立場別ビュー", {
  x: 0.6, y: 3.6, w: 8.8, h: 0.5,
  fontSize: 18, fontFace: "Calibri", color: C.navy, bold: true,
});

const roles = [
  { role: "コントローラー", desc: "改善アクションの\n優先順位", color: C.blue },
  { role: "医師", desc: "自分の入退院パターン\nと全体への影響", color: C.green },
  { role: "看護師", desc: "改善が人件費原資\nとしていくらか", color: C.orange },
  { role: "経営者", desc: "経営指標サマリー\nと改善トレンド", color: C.gold },
];

roles.forEach((r, i) => {
  const x = 0.6 + i * 2.35;
  slide10.addShape(pres.shapes.RECTANGLE, {
    x: x, y: 4.2, w: 2.1, h: 1.1,
    fill: { color: C.white }, shadow: makeShadow(),
  });
  slide10.addShape(pres.shapes.RECTANGLE, {
    x: x, y: 4.2, w: 2.1, h: 0.06, fill: { color: r.color },
  });
  slide10.addText(r.role, {
    x: x + 0.1, y: 4.3, w: 1.9, h: 0.4,
    fontSize: 14, fontFace: "Calibri", color: C.navy, bold: true, align: "center",
  });
  slide10.addText(r.desc, {
    x: x + 0.1, y: 4.7, w: 1.9, h: 0.5,
    fontSize: 11, fontFace: "Calibri", color: C.subText, align: "center", lineSpacingMultiple: 1.3,
  });
});

// ============================================================
// SLIDE 11: まとめ
// ============================================================
let slide11 = pres.addSlide();
slide11.background = { color: C.navy };

// Top accent bar
slide11.addShape(pres.shapes.RECTANGLE, {
  x: 0, y: 0, w: 10, h: 0.06, fill: { color: C.gold },
});

slide11.addText("精神論を、数字に変える。", {
  x: 0.8, y: 0.8, w: 8.4, h: 0.8,
  fontSize: 36, fontFace: "Arial Black", color: C.gold,
});

slide11.addText("全職員が自発的に改善に動く仕組みを作る。", {
  x: 0.8, y: 1.6, w: 8.4, h: 0.6,
  fontSize: 22, fontFace: "Georgia", color: C.white, italic: true,
});

// Key takeaways
const takeaways = [
  { text: "稼働率1% = 年間1,046万円", icon: "\u25A0" },
  { text: "「改善のヒント」で問題を自動検出し、金額で示す", icon: "\u25A0" },
  { text: "医師別の入退院パターンを可視化し、対話の根拠を作る", icon: "\u25A0" },
  { text: "改善の積み重ねで、一人ひとりの給与・賞与の原資を増やす", icon: "\u25A0" },
  { text: "コストゼロで運用可能（電子カルテ連携不要）", icon: "\u25A0" },
];

takeaways.forEach((t, i) => {
  slide11.addShape(pres.shapes.RECTANGLE, {
    x: 0.8, y: 2.5 + i * 0.55, w: 0.12, h: 0.12,
    fill: { color: C.gold },
  });
  slide11.addText(t.text, {
    x: 1.15, y: 2.4 + i * 0.55, w: 7.5, h: 0.45,
    fontSize: 16, fontFace: "Calibri", color: C.white, valign: "middle",
  });
});

// Bottom CTA
slide11.addShape(pres.shapes.RECTANGLE, {
  x: 0, y: 4.8, w: 10, h: 0.825,
  fill: { color: "0F1A2E" },
});
slide11.addText("おもろまちメディカルセンター  |  ベッドコントロールシミュレーター v3.0", {
  x: 0.8, y: 4.9, w: 8.4, h: 0.5,
  fontSize: 14, fontFace: "Calibri", color: C.medGray, valign: "middle",
});

// Write file
pres.writeFile({ fileName: "/Users/torukubota/ai-management/docs/admin/bed_control_evolution_presentation.pptx" })
  .then(() => console.log("Presentation created successfully!"))
  .catch((err) => console.error("Error:", err));
