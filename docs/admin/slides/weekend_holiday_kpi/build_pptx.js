/**
 * 週末・大型連休の稼働率対策プレゼン v4 (20 スライド + Q&A)
 * Build: node build_pptx.js
 *
 * v4 構成（2026-04-19）:
 *   Slide 1:    タイトル
 *   Slide 2:    エグゼクティブサマリー（3 提案 + 賞与インパクト）
 *   Slide 3-14: Phase 1 実態データ共有（12 スライド）
 *   Slide 15:   提案①連休前+連休中の分散退院型 (+2,055 万円)
 *   Slide 16:   提案②日曜退院の継続定着化 (+348 万円)
 *   Slide 17:   提案③データ駆動×制度適応の三位一体
 *   Slide 18:   賞与インパクト — 290名で分け合う +4%（新設）
 *   Slide 19:   2026-06-01 本則完全適用への備え（新設）
 *   Slide 20:   実行計画とまとめ
 *   Slide 21-22: Q&A 10 問（2 スライドに集約）
 */
const pptxgen = require("pptxgenjs");
const path = require("path");

const CHART_DIR = path.join(__dirname, "charts");
const OUTPUT = path.join(__dirname, "weekend_holiday_kpi.pptx");

// =============================================================================
// 色・フォント（旧版から継承）
// =============================================================================
const COLOR = {
  navy: "1E3A5F",
  navyDark: "122342",
  navyAccent: "4A6FA5",
  cream: "F7F5F0",
  white: "FFFFFF",
  gray: "475569",
  grayLight: "94A3B8",
  grayBg: "F1F5F9",
  blue: "2E86AB",
  orange: "F18F01",
  red: "C73E1D",
  green: "4CAF50",
  gold: "C9A961",
  purple: "6B4E8A",
};

const FONT_H = "Yu Gothic UI";
const FONT_B = "Yu Gothic";

const FOOTER_TEXT = "おもろまちメディカルセンター 経営会議資料 | 2026-04-19";

// =============================================================================
// プレゼンテーション初期化
// =============================================================================
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.author = "おもろまちメディカルセンター 副院長 久保田徹";
pres.title = "週末・大型連休の稼働率対策 v4";
pres.subject = "経営会議資料（v4 新 3 提案・賞与インパクト・2026-06-01 本則）";

const W = 13.3;
const H = 7.5;

// 総スライド数（Q&A 2 スライド含む）
const TOTAL = 22;

// =============================================================================
// 共通ユーティリティ
// =============================================================================
function addFrame(slide, pageNum) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: W, h: 0.12,
    fill: { color: COLOR.navy }, line: { type: "none" },
  });
  slide.addText(FOOTER_TEXT, {
    x: 0.5, y: H - 0.35, w: 9, h: 0.28,
    fontFace: FONT_B, fontSize: 9, color: COLOR.grayLight, margin: 0,
  });
  slide.addText(`${pageNum} / ${TOTAL}`, {
    x: W - 1.3, y: H - 0.35, w: 0.8, h: 0.28,
    fontFace: FONT_B, fontSize: 9, color: COLOR.grayLight, align: "right", margin: 0,
  });
}

function addPageTitle(slide, title, subtitle) {
  slide.addText(title, {
    x: 0.5, y: 0.35, w: W - 1.0, h: 0.75,
    fontFace: FONT_H, fontSize: 26, bold: true, color: COLOR.navy, margin: 0,
    valign: "middle",
  });
  if (subtitle) {
    slide.addText(subtitle, {
      x: 0.5, y: 1.1, w: W - 1.0, h: 0.4,
      fontFace: FONT_B, fontSize: 13, color: COLOR.navyAccent, italic: true, margin: 0,
    });
  }
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.55, w: 1.2, h: 0.04,
    fill: { color: COLOR.gold }, line: { type: "none" },
  });
}

function addNumberCircle(slide, x, y, num, color = COLOR.navy) {
  slide.addShape(pres.shapes.OVAL, {
    x, y, w: 0.5, h: 0.5,
    fill: { color }, line: { type: "none" },
  });
  slide.addText(String(num), {
    x, y, w: 0.5, h: 0.5,
    fontFace: FONT_H, fontSize: 20, bold: true, color: COLOR.white,
    align: "center", valign: "middle", margin: 0,
  });
}

function addAccentCard(slide, x, y, w, h, title, body, accentColor = COLOR.blue) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h,
    fill: { color: COLOR.white }, line: { color: COLOR.grayBg, width: 0.5 },
    shadow: { type: "outer", blur: 8, offset: 2, angle: 90, color: "000000", opacity: 0.08 },
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w: 0.08, h,
    fill: { color: accentColor }, line: { type: "none" },
  });
  slide.addText(title, {
    x: x + 0.25, y: y + 0.1, w: w - 0.35, h: 0.4,
    fontFace: FONT_H, fontSize: 13, bold: true, color: COLOR.navy, margin: 0,
    valign: "top",
  });
  slide.addText(body, {
    x: x + 0.25, y: y + 0.5, w: w - 0.35, h: h - 0.6,
    fontFace: FONT_B, fontSize: 10.5, color: COLOR.gray, margin: 0,
    valign: "top",
  });
}

function addBigStat(slide, x, y, w, h, value, label, unit = "", valueColor = COLOR.navy) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h,
    fill: { color: COLOR.white }, line: { color: COLOR.grayBg, width: 0.5 },
    shadow: { type: "outer", blur: 10, offset: 3, angle: 90, color: "000000", opacity: 0.08 },
  });
  const valueH = h * 0.58;
  const valueFont = h < 1.2 ? 30 : (h < 1.5 ? 36 : 40);
  slide.addText([
    { text: value, options: { fontFace: FONT_H, fontSize: valueFont, bold: true, color: valueColor } },
    { text: "  " + unit, options: { fontFace: FONT_B, fontSize: 12, color: COLOR.gray } },
  ], {
    x: x + 0.2, y: y + 0.1, w: w - 0.4, h: valueH,
    align: "left", valign: "middle", margin: 0,
  });
  slide.addText(label, {
    x: x + 0.2, y: y + valueH + 0.15, w: w - 0.4, h: h - valueH - 0.25,
    fontFace: FONT_B, fontSize: 10.5, color: COLOR.grayLight, margin: 0,
    valign: "top",
  });
}

// =============================================================================
// Slide 1: タイトル
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.navyDark };
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0.6, w: W, h: 0.04, fill: { color: COLOR.gold }, line: { type: "none" } });
  s.addText("DATA-DRIVEN BED CONTROL PROPOSAL  —  v4", {
    x: 0.8, y: 1.1, w: W - 1.6, h: 0.4,
    fontFace: FONT_H, fontSize: 12, bold: true, color: COLOR.gold, charSpacing: 6, margin: 0,
  });
  s.addText("週末・大型連休の\n稼働率対策 v4", {
    x: 0.8, y: 1.7, w: W - 1.6, h: 2.3,
    fontFace: FONT_H, fontSize: 52, bold: true, color: COLOR.white, margin: 0, lineSpacingMultiple: 1.05,
  });
  s.addShape(pres.shapes.RECTANGLE, { x: 0.8, y: 4.2, w: 0.8, h: 0.04, fill: { color: COLOR.gold }, line: { type: "none" } });
  s.addText("— 連休中退院という発想転換と、賞与 +4% への道筋 —", {
    x: 0.8, y: 4.35, w: W - 1.6, h: 0.5,
    fontFace: FONT_B, fontSize: 18, color: COLOR.cream, italic: true, margin: 0,
  });
  s.addText([
    { text: "発表者 ", options: { fontSize: 11, color: COLOR.grayLight } },
    { text: "副院長  久保田  徹  ", options: { fontSize: 14, bold: true, color: COLOR.white, breakLine: true } },
    { text: "内科 / 呼吸器内科", options: { fontSize: 11, color: COLOR.grayLight, breakLine: true } },
    { text: "", options: { fontSize: 6, breakLine: true } },
    { text: "2026年4月19日  経営会議", options: { fontSize: 12, color: COLOR.gold } },
  ], {
    x: 0.8, y: 5.6, w: 6, h: 1.3, fontFace: FONT_B, margin: 0, valign: "top",
  });
  s.addText([
    { text: "おもろまちメディカルセンター", options: { fontSize: 14, bold: true, color: COLOR.white, breakLine: true } },
    { text: "OMOROMACHI MEDICAL CENTER", options: { fontSize: 9, color: COLOR.gold, charSpacing: 4 } },
  ], {
    x: W - 5, y: 6.2, w: 4.3, h: 0.8,
    fontFace: FONT_H, align: "right", margin: 0, valign: "middle",
  });
}

// =============================================================================
// Slide 2: エグゼクティブサマリー（3 提案 + 賞与インパクト）
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 2);
  addPageTitle(s, "運用思想を転換すれば、年 2,403 万円が守られる", "3 つの提案と、賞与 +4%（290 名で分け合う）への道筋");

  // 左列「3 つの提案」
  s.addText("3 つの提案", {
    x: 0.5, y: 1.85, w: 7.3, h: 0.4,
    fontFace: FONT_H, fontSize: 16, bold: true, color: COLOR.navy, margin: 0,
  });
  const proposals = [
    { t: "連休前 + 連休中の分散退院型運用への転換", b: "5 大型連休で連休中稼働率 60% → 85% を目指す", v: "+2,055 万円/年" },
    { t: "日曜退院の継続定着化", b: "日曜入院 0.29 件/日という実データに基づく週 2 床シフト", v: "+348 万円/年" },
    { t: "データ駆動 × 制度適応の三位一体", b: "過去実績分析 / 施設基準実態レポート / 需要予測校正", v: "2026-06-01 本則備え" },
  ];
  proposals.forEach((p, i) => {
    const y = 2.35 + i * 1.4;
    addNumberCircle(s, 0.5, y, i + 1, COLOR.navy);
    s.addText(p.t, {
      x: 1.15, y: y - 0.02, w: 6.5, h: 0.4,
      fontFace: FONT_H, fontSize: 13, bold: true, color: COLOR.navy, margin: 0, valign: "top",
    });
    s.addText(p.b, {
      x: 1.15, y: y + 0.4, w: 6.5, h: 0.5,
      fontFace: FONT_B, fontSize: 11, color: COLOR.gray, margin: 0, valign: "top",
    });
    s.addText(p.v, {
      x: 1.15, y: y + 0.9, w: 6.5, h: 0.35,
      fontFace: FONT_H, fontSize: 12, bold: true, color: COLOR.red, margin: 0, valign: "top",
    });
  });

  s.addShape(pres.shapes.RECTANGLE, {
    x: 7.95, y: 2.0, w: 0.02, h: 4.7, fill: { color: COLOR.grayLight }, line: { type: "none" },
  });

  // 右列「賞与インパクト」
  s.addText("賞与インパクト（290 名で分け合う）", {
    x: 8.1, y: 1.85, w: 5.0, h: 0.4,
    fontFace: FONT_H, fontSize: 15, bold: true, color: COLOR.red, margin: 0,
  });
  addBigStat(s, 8.1, 2.35, 4.85, 1.1, "+2,403", "合計効果（3 提案合算）", "万円/年", COLOR.red);
  addBigStat(s, 8.1, 3.55, 4.85, 1.1, "+1,212", "賞与原資（人件費率 58% 維持）", "万円/年", COLOR.navy);
  addBigStat(s, 8.1, 4.75, 4.85, 1.1, "+41,800", "1 人あたり 年間", "円", COLOR.green);
  addBigStat(s, 8.1, 5.95, 4.85, 0.95, "+20,900", "夏冬賞与 各", "円", COLOR.gold);

  // 下部注記
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 7.0, w: W - 1.0, h: 0.3,
    fill: { color: COLOR.navy }, line: { type: "none" },
  });
  s.addText("v4 対応アプリ（2026-04-19 以降） | 根拠データ: 2025FY 入院実績 1,965 件 / 0 埋め完全年間カレンダー方式", {
    x: 0.7, y: 7.0, w: W - 1.4, h: 0.3,
    fontFace: FONT_B, fontSize: 10, color: COLOR.white, align: "center", valign: "middle", italic: true, margin: 0,
  });
}

// =============================================================================
// Slide 3: データ概要 — 1,965 件、完全年間カレンダー
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 3);
  addPageTitle(s, "データ概要 — 1,965 件、完全年間カレンダー", "2025-04-01 〜 2026-03-31（365 日）");

  addBigStat(s, 0.5, 2.0, 3.0, 1.3, "1,965", "総入院件数（v4 再集計）", "件", COLOR.navy);
  addBigStat(s, 3.65, 2.0, 3.0, 1.3, "365", "分析対象日数（0 埋め）", "日", COLOR.navyAccent);
  addBigStat(s, 6.8, 2.0, 3.0, 1.3, "795", "予定入院（40.5%）", "件", COLOR.blue);
  addBigStat(s, 9.95, 2.0, 3.0, 1.3, "1,081", "緊急入院（55.0%）", "件", COLOR.orange);

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 3.7, w: W - 1.0, h: 2.5,
    fill: { color: COLOR.white }, line: { color: COLOR.grayBg, width: 0.5 },
    shadow: { type: "outer", blur: 8, offset: 2, angle: 90, color: "000000", opacity: 0.06 },
  });
  s.addText("v4 での変更点", {
    x: 0.8, y: 3.85, w: 4, h: 0.4,
    fontFace: FONT_H, fontSize: 14, bold: true, color: COLOR.navy, margin: 0,
  });

  const items = [
    ["病棟別内訳", "5F 951 件 / 6F 996 件 / 4F 18 件"],
    ["期間", "2025-04-01 〜 2026-03-31（365 日完全カレンダー）"],
    ["分析軸", "曜日 / 月 / 時間帯 / 年齢 / リードタイム の 5 軸"],
    ["v3.6 からの変更", "1,876 件 → 1,965 件（0 埋めカレンダー方式で再集計）"],
    ["除外処理", "4F 18 件は地域包括医療病棟外のため施設基準計算から除外"],
    ["データソース", "data/actual_admissions_2025fy.csv（電子カルテ抽出）"],
  ];
  items.forEach(([label, body], i) => {
    const y = 4.3 + i * 0.3;
    s.addText(label, {
      x: 0.8, y, w: 2.5, h: 0.28,
      fontFace: FONT_H, fontSize: 10, bold: true, color: COLOR.navyAccent, margin: 0,
    });
    s.addText(body, {
      x: 3.4, y, w: W - 4.3, h: 0.28,
      fontFace: FONT_B, fontSize: 10, color: COLOR.gray, margin: 0,
    });
  });

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 6.5, w: W - 1.0, h: 0.45,
    fill: { color: COLOR.grayBg }, line: { type: "none" },
  });
  s.addText([
    { text: "0 埋めカレンダー方式: ", options: { fontSize: 10, bold: true, color: COLOR.navy } },
    { text: "入院ゼロの日もカレンダー上に保持することで、曜日別平均や連休中の「実質ゼロ」が正確に反映される構造", options: { fontSize: 10, color: COLOR.gray } },
  ], {
    x: 0.7, y: 6.5, w: W - 1.4, h: 0.45, fontFace: FONT_B, align: "center", valign: "middle", margin: 0,
  });
}

// =============================================================================
// Slide 4: 曜日別入院パターンの実態（v4 再集計）
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 4);
  addPageTitle(s, "曜日別入院パターン（v4 再集計）", "月曜 8.15 件、日曜 0.29 件 — 平日の 28 分の 1");

  s.addImage({
    path: path.join(CHART_DIR, "01_dow_admissions.png"),
    x: 0.5, y: 1.9, w: 8.0, h: 4.5, sizing: { type: "contain", w: 8.0, h: 4.5 },
  });

  const bullets = [
    { num: "1.", title: "月曜 8.15 件/日", body: "週明けの受入負荷集中" },
    { num: "2.", title: "金曜は既に予定抑制", body: "予定 1.50 件のみ（緊急 3.81 件）— 週後半を回避済み" },
    { num: "3.", title: "日曜 0.29 件/日", body: "平日の 28 分の 1 — 鍵は退院側にある" },
  ];
  bullets.forEach((b, i) => {
    const y = 2.1 + i * 1.45;
    addAccentCard(s, 8.8, y, 4.0, 1.25, `${b.num}  ${b.title}`, b.body, COLOR.navy);
  });

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 6.85, w: W - 1.0, h: 0.35,
    fill: { color: COLOR.gold }, line: { type: "none" },
  });
  s.addText("v4 転換: 「週末を埋める」から「日曜を退院に使う」発想へ", {
    x: 0.7, y: 6.85, w: W - 1.4, h: 0.35,
    fontFace: FONT_H, fontSize: 12, bold: true, color: COLOR.navyDark, align: "center", valign: "middle", margin: 0,
  });
}

// =============================================================================
// Slide 5: ばらつきで見る曜日差（箱ひげ図）
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 5);
  addPageTitle(s, "ばらつきで見る曜日差（箱ひげ図）", "週末の谷は構造 — 埋めずに、使う");

  s.addImage({
    path: path.join(CHART_DIR, "02_dow_boxplot.png"),
    x: 2.0, y: 1.85, w: 9.3, h: 4.2, sizing: { type: "contain", w: 9.3, h: 4.2 },
  });

  const msgs = [
    { title: "平日 × 週末の分布は別領域", body: "平日の四分位と週末 0〜3 件は重なりがほぼない" },
    { title: "金曜は境界日", body: "平日側だが下側に寄りつつある" },
    { title: "構造は動かない", body: "偶発性ではない「曜日構造」→ 退院側で再配置する" },
  ];
  msgs.forEach((m, i) => {
    const x = 0.5 + i * 4.2;
    addAccentCard(s, x, 6.15, 4.0, 0.95, m.title, m.body, [COLOR.blue, COLOR.orange, COLOR.gold][i]);
  });
}

// =============================================================================
// Slide 6: 月別トレンド — ピークと谷の季節性
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 6);
  addPageTitle(s, "月別トレンド — ピークと谷の季節性", "月係数 0.89 〜 1.11 — 季節戦略が必要");

  s.addImage({
    path: path.join(CHART_DIR, "03_monthly_trend.png"),
    x: 0.5, y: 1.9, w: 8.2, h: 4.5, sizing: { type: "contain", w: 8.2, h: 4.5 },
  });

  addBigStat(s, 9.0, 2.0, 3.8, 1.4, "1.11", "ピーク：7 月", "月係数", COLOR.green);
  addBigStat(s, 9.0, 3.55, 3.8, 1.4, "0.89", "谷：4 月", "月係数", COLOR.navyAccent);
  addBigStat(s, 9.0, 5.1, 3.8, 1.4, "−12.7%", "日別 MAE 改善（日曜 −44%）", "", COLOR.gold);

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 6.6, w: W - 1.0, h: 0.4,
    fill: { color: COLOR.navy }, line: { type: "none" },
  });
  s.addText("需要予測モデル校正（裏側自動適用）— 7 月・10 月は「高負荷吸収」/ 4 月・9 月は「谷の緩和」戦略", {
    x: 0.7, y: 6.6, w: W - 1.4, h: 0.4,
    fontFace: FONT_B, fontSize: 12, color: COLOR.white, align: "center", valign: "middle", italic: true, margin: 0,
  });
}

// =============================================================================
// Slide 7: 大型連休で何が起きているか
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 7);
  addPageTitle(s, "大型連休で何が起きているか", "連休中稼働率 60% 台 — 年 2,055 万円の運営貢献額流出");

  s.addImage({
    path: path.join(CHART_DIR, "04_holiday_drop.png"),
    x: 0.5, y: 1.9, w: 8.0, h: 4.8, sizing: { type: "contain", w: 8.0, h: 4.8 },
  });

  s.addShape(pres.shapes.RECTANGLE, {
    x: 8.8, y: 2.0, w: 4.0, h: 2.2, fill: { color: COLOR.red }, line: { type: "none" },
  });
  s.addText("−2,055", {
    x: 8.8, y: 2.1, w: 4.0, h: 1.4,
    fontFace: FONT_H, fontSize: 56, bold: true, color: COLOR.white, align: "center", valign: "middle", margin: 0,
  });
  s.addText("万円/年 の運営貢献額流出\n（587.5 床日 = 稼働率 +1.71%）", {
    x: 8.8, y: 3.4, w: 4.0, h: 0.8,
    fontFace: FONT_B, fontSize: 13, color: COLOR.white, align: "center", valign: "top", margin: 0,
  });

  addAccentCard(s, 8.8, 4.4, 4.0, 0.85, "5 大型連休すべて 60% 台", "実質的に半休業状態", COLOR.red);
  addAccentCard(s, 8.8, 5.35, 4.0, 0.85, "二値構造", "連休日数は無関係、入るか入らないか", COLOR.orange);
  addAccentCard(s, 8.8, 6.3, 4.0, 0.55, "改善余地あり", "連休前後に需要集中", COLOR.gold);
}

// =============================================================================
// Slide 8: GW の具体例
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 8);
  addPageTitle(s, "GW 2025 の具体例", "連休中退院で 60% → 85% — 連休明けの 13 件も吸収しやすく");

  s.addImage({
    path: path.join(CHART_DIR, "07_gw_daily.png"),
    x: 0.5, y: 1.9, w: 9.5, h: 4.8, sizing: { type: "contain", w: 9.5, h: 4.8 },
  });

  addAccentCard(s, 10.3, 2.0, 2.55, 1.5,
    "5/3 – 5/6（4 日間）", "合計 1 件 — 実質ゼロ稼働", COLOR.red);
  addAccentCard(s, 10.3, 3.6, 2.55, 1.5,
    "5/7（水）13 件", "連休明け — 通常の約 2 倍", COLOR.orange);
  addAccentCard(s, 10.3, 5.2, 2.55, 1.5,
    "v4 転換", "連休前集中型 → 3 タグ分散型（連休前+中+明け）", COLOR.green);
}

// =============================================================================
// Slide 9: 年末年始の具体例
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 9);
  addPageTitle(s, "年末年始の具体例", "助走のある年末年始は、3 タグ分散を組みやすい");

  s.addImage({
    path: path.join(CHART_DIR, "08_nenmatsu_daily.png"),
    x: 0.5, y: 1.9, w: 9.5, h: 4.8, sizing: { type: "contain", w: 9.5, h: 4.8 },
  });

  addAccentCard(s, 10.3, 2.0, 2.55, 1.5,
    "12/27 – 1/4（9 日間）", "平均 1 件前後/日 — 実質休業状態", COLOR.red);
  addAccentCard(s, 10.3, 3.6, 2.55, 1.5,
    "助走期間あり", "12/20 頃から漸減 → 退院計画が立てやすい", COLOR.green);
  addAccentCard(s, 10.3, 5.2, 2.55, 1.5,
    "家族都合逆転", "仕事が休みの家族ほどお迎え可能", COLOR.navy);
}

// =============================================================================
// Slide 10: 緊急入院の時刻分布
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 10);
  addPageTitle(s, "緊急入院の時刻分布", "13-18 時に 64% 集中 — 退院した床は当日埋まる");

  s.addImage({
    path: path.join(CHART_DIR, "05_emergency_hour.png"),
    x: 0.5, y: 1.9, w: 8.0, h: 4.7, sizing: { type: "contain", w: 8.0, h: 4.7 },
  });

  s.addShape(pres.shapes.RECTANGLE, {
    x: 8.8, y: 2.0, w: 4.0, h: 2.4,
    fill: { color: COLOR.orange }, line: { type: "none" },
  });
  s.addText("64%", {
    x: 8.8, y: 2.15, w: 4.0, h: 1.5,
    fontFace: FONT_H, fontSize: 68, bold: true, color: COLOR.white, align: "center", valign: "middle", margin: 0,
  });
  s.addText("緊急入院が 13-18 時 6 時間に集中\n（約 694 / 1,081 件）", {
    x: 8.8, y: 3.55, w: 4.0, h: 0.85,
    fontFace: FONT_B, fontSize: 12, color: COLOR.white, align: "center", valign: "top", margin: 0,
  });

  addAccentCard(s, 8.8, 4.6, 4.0, 0.85, "深夜 0-5 時はごく僅か", "「夜中にどんどん来る」は誤認", COLOR.navyAccent);
  addAccentCard(s, 8.8, 5.55, 4.0, 1.15,
    "連休中も時間帯構造は維持", "連休中の朝退院も、当日中に緊急で埋まる可能性は低くない — 連休中退院のリスクは小さい",
    COLOR.green);
}

// =============================================================================
// Slide 11: 予定入院のリードタイム
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 11);
  addPageTitle(s, "予定入院のリードタイム — 動かせる余地は十分ある", "中央値 12 日、平均 16.3 日 — 6 割は 8 日以上前に予約済み");

  s.addImage({
    path: path.join(CHART_DIR, "11_lead_time_dist.png"),
    x: 0.5, y: 1.9, w: 8.0, h: 4.7, sizing: { type: "contain", w: 8.0, h: 4.7 },
  });

  addBigStat(s, 8.8, 2.0, 4.0, 1.4, "12", "中央値リードタイム", "日", COLOR.navy);
  addBigStat(s, 8.8, 3.55, 4.0, 1.4, "60%", "8 日以上前に予約済み", "", COLOR.green);
  addBigStat(s, 8.8, 5.1, 4.0, 1.4, "3 – 21", "P25 – P75", "日", COLOR.gold);

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 6.8, w: W - 1.0, h: 0.4,
    fill: { color: COLOR.navy }, line: { type: "none" },
  });
  s.addText("v4 運用: 連休中退院 + 連休明け入院の分散予約で平準化（リードタイム 12 日を活用）", {
    x: 0.7, y: 6.8, w: W - 1.4, h: 0.4,
    fontFace: FONT_H, fontSize: 13, bold: true, color: COLOR.white, align: "center", valign: "middle", margin: 0,
  });
}

// =============================================================================
// Slide 12: 登録曜日と入院曜日のマッピング
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 12);
  addPageTitle(s, "登録曜日と入院曜日のマッピング", "登録時点で入院曜日はどう選ばれているか");

  s.addImage({
    path: path.join(CHART_DIR, "12_register_dow_vs_admit_dow.png"),
    x: 2.5, y: 1.85, w: 8.3, h: 4.3, sizing: { type: "contain", w: 8.3, h: 4.3 },
  });

  const msgs = [
    { title: "月〜水 登録 → 火〜金 配置", body: "典型パターンは「同週後半」" },
    { title: "土日 登録はほぼゼロ", body: "週末予約での空床埋めは物理的に不可" },
    { title: "v4 運用", body: "📉 過去実績分析タブで月次確認 + 連休前後の予約曜日の分散" },
  ];
  msgs.forEach((m, i) => {
    const x = 0.5 + i * 4.2;
    addAccentCard(s, x, 6.25, 4.0, 0.85, m.title, m.body, [COLOR.blue, COLOR.navyAccent, COLOR.green][i]);
  });
}

// =============================================================================
// Slide 13: 連休前後の予約集中 — 既に動いている運用の延長
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 13);
  addPageTitle(s, "連休前後の予約集中 — 既に動いている運用の延長", "連休明けの集中をほどく — リードタイム 12 日を活かす");

  s.addImage({
    path: path.join(CHART_DIR, "13_holiday_lead_window.png"),
    x: 0.5, y: 1.9, w: 8.0, h: 4.7, sizing: { type: "contain", w: 8.0, h: 4.7 },
  });

  addAccentCard(s, 8.8, 2.0, 4.0, 1.3, "連休期間内の予定はほぼゼロ", "GW・SW は完全にゼロ、お盆のみ例外（16 件）", COLOR.red);
  addAccentCard(s, 8.8, 3.45, 4.0, 1.3, "明け週 > 前週", "既に現場で部分的に実施されている運用", COLOR.green);
  addAccentCard(s, 8.8, 4.9, 4.0, 1.35, "v4 進化", "連休明け 1 週間で平準化 — リードタイムを活用した体系化", COLOR.navy);

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 6.8, w: W - 1.0, h: 0.4,
    fill: { color: COLOR.gold }, line: { type: "none" },
  });
  s.addText("沖縄固有の帰省医療需要（お盆 16 件）は地域特性として存置 — 一律削減はしない", {
    x: 0.7, y: 6.8, w: W - 1.4, h: 0.4,
    fontFace: FONT_B, fontSize: 12, bold: true, color: COLOR.navyDark, align: "center", valign: "middle", margin: 0,
  });
}

// =============================================================================
// Slide 14: 区分別比較
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 14);
  addPageTitle(s, "区分別比較", "ギャップの 1/3 を取り戻す — 687.5 床日/年");

  s.addImage({
    path: path.join(CHART_DIR, "06_category_comparison.png"),
    x: 0.5, y: 1.9, w: 8.0, h: 4.7, sizing: { type: "contain", w: 8.0, h: 4.7 },
  });

  s.addShape(pres.shapes.RECTANGLE, {
    x: 8.8, y: 2.0, w: 4.0, h: 2.4,
    fill: { color: COLOR.navyDark }, line: { type: "none" },
  });
  s.addText("687.5", {
    x: 8.8, y: 2.15, w: 4.0, h: 1.3,
    fontFace: FONT_H, fontSize: 54, bold: true, color: COLOR.gold, align: "center", valign: "middle", margin: 0,
  });
  s.addText("床日/年 = 約 2,403 万円/年\n日曜 100 + 連休中 587.5", {
    x: 8.8, y: 3.4, w: 4.0, h: 1.0,
    fontFace: FONT_B, fontSize: 12, color: COLOR.white, align: "center", valign: "top", margin: 0,
  });

  addAccentCard(s, 8.8, 4.6, 4.0, 1.0, "完全解消は不要", "ギャップの 1/3 だけで年 2,400 万円", COLOR.green);
  addAccentCard(s, 8.8, 5.75, 4.0, 1.0, "保守的試算", "実運用開始後の実測で精度を上げる", COLOR.gold);
}

// =============================================================================
// Slide 15: v4 新提案① — 連休前 + 連休中の分散退院型運用への転換
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 15);
  addPageTitle(s, "提案① 3 タグ分散型運用への転換", "連休前 + 連休中 + 連休明け の 3 タグ分散で +2,055 万円/年");

  // 左: 運用思想の転換
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.9, w: 6.0, h: 3.2,
    fill: { color: COLOR.white }, line: { color: COLOR.grayBg, width: 0.5 },
    shadow: { type: "outer", blur: 8, offset: 2, angle: 90, color: "000000", opacity: 0.08 },
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.9, w: 0.08, h: 3.2, fill: { color: COLOR.navy }, line: { type: "none" },
  });
  s.addText("運用思想の転換", {
    x: 0.75, y: 2.05, w: 5.7, h: 0.4,
    fontFace: FONT_H, fontSize: 15, bold: true, color: COLOR.navy, margin: 0,
  });
  s.addText([
    { text: "v3.6 以前: ", options: { fontSize: 12, bold: true, color: COLOR.red } },
    { text: "連休前に退院を集中させて受入能力を確保", options: { fontSize: 12, color: COLOR.gray, breakLine: true } },
    { text: "", options: { fontSize: 8, breakLine: true } },
    { text: "v4: ", options: { fontSize: 12, bold: true, color: COLOR.green } },
    { text: "退院を「連休前 + 連休中 + 連休明け」の 3 タグに分散 → 連休全期間を平準化", options: { fontSize: 12, color: COLOR.gray, breakLine: true } },
    { text: "", options: { fontSize: 8, breakLine: true } },
    { text: "キー発想: ", options: { fontSize: 12, bold: true, color: COLOR.gold } },
    { text: "「家族都合逆転」— 連休中こそ家族は仕事が休みで、お迎えの都合が取りやすい", options: { fontSize: 12, color: COLOR.gray } },
  ], {
    x: 0.75, y: 2.5, w: 5.7, h: 2.5, fontFace: FONT_B, margin: 0, valign: "top",
  });

  // 右: 具体的な運用 4 ステップ
  s.addShape(pres.shapes.RECTANGLE, {
    x: 6.8, y: 1.9, w: 6.0, h: 3.2,
    fill: { color: COLOR.white }, line: { color: COLOR.grayBg, width: 0.5 },
    shadow: { type: "outer", blur: 8, offset: 2, angle: 90, color: "000000", opacity: 0.08 },
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 6.8, y: 1.9, w: 0.08, h: 3.2, fill: { color: COLOR.green }, line: { type: "none" },
  });
  s.addText("具体的な運用 4 ステップ", {
    x: 7.05, y: 2.05, w: 5.7, h: 0.4,
    fontFace: FONT_H, fontSize: 15, bold: true, color: COLOR.navy, margin: 0,
  });
  const steps = [
    "① カンファで 3 タグ分類（連休 3 週前）",
    "② 一日 N 名までの退院枠を設定",
    "③ 連休 5 日間で合計 M 名を分散",
    "④ What-if タブでシミュレーション",
  ];
  steps.forEach((t, i) => {
    s.addText(t, {
      x: 7.05, y: 2.55 + i * 0.55, w: 5.7, h: 0.5,
      fontFace: FONT_B, fontSize: 12, color: COLOR.gray, margin: 0, valign: "top",
    });
  });

  // 下: チャート + 効果試算
  s.addImage({
    path: path.join(CHART_DIR, "09_impact_simulation.png"),
    x: 0.5, y: 5.3, w: 7.5, h: 1.6, sizing: { type: "contain", w: 7.5, h: 1.6 },
  });

  s.addShape(pres.shapes.RECTANGLE, {
    x: 8.3, y: 5.3, w: 4.5, h: 1.6,
    fill: { color: COLOR.red }, line: { type: "none" },
  });
  s.addText("+2,055", {
    x: 8.3, y: 5.35, w: 4.5, h: 0.9,
    fontFace: FONT_H, fontSize: 48, bold: true, color: COLOR.white, align: "center", valign: "middle", margin: 0,
  });
  s.addText("万円/年（連休中 60% → 85%）\n587.5 床日/年 = 稼働率 +1.71%", {
    x: 8.3, y: 6.25, w: 4.5, h: 0.65,
    fontFace: FONT_B, fontSize: 10, color: COLOR.white, align: "center", valign: "top", margin: 0,
  });

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 7.0, w: W - 1.0, h: 0.3,
    fill: { color: COLOR.gold }, line: { type: "none" },
  });
  s.addText("「患者さんに無理はさせない」を第一原則に — 家族の同意が得られた方だけを連休中退院可タグに残す", {
    x: 0.7, y: 7.0, w: W - 1.4, h: 0.3,
    fontFace: FONT_B, fontSize: 10, bold: true, color: COLOR.navyDark, align: "center", valign: "middle", italic: true, margin: 0,
  });
}

// =============================================================================
// Slide 16: v4 新提案② — 日曜退院の継続定着化
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 16);
  addPageTitle(s, "提案② 日曜退院の継続定着化", "週 2 床を土曜 → 日曜へシフト × 50 週 = +348 万円/年");

  s.addImage({
    path: path.join(CHART_DIR, "01_dow_admissions.png"),
    x: 0.5, y: 1.9, w: 7.0, h: 4.0, sizing: { type: "contain", w: 7.0, h: 4.0 },
  });

  // 右: 実データ構造 + 運用設計
  s.addShape(pres.shapes.RECTANGLE, {
    x: 7.8, y: 1.9, w: 5.0, h: 1.85,
    fill: { color: COLOR.white }, line: { color: COLOR.grayBg, width: 0.5 },
    shadow: { type: "outer", blur: 8, offset: 2, angle: 90, color: "000000", opacity: 0.08 },
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 7.8, y: 1.9, w: 0.08, h: 1.85, fill: { color: COLOR.blue }, line: { type: "none" },
  });
  s.addText("実データ構造", {
    x: 8.05, y: 2.0, w: 4.7, h: 0.35,
    fontFace: FONT_H, fontSize: 13, bold: true, color: COLOR.navy, margin: 0,
  });
  s.addText([
    { text: "日曜入院: ", options: { fontSize: 11, bold: true, color: COLOR.red } },
    { text: "0.29 件/日（平日の 28 分の 1）", options: { fontSize: 11, color: COLOR.gray, breakLine: true } },
    { text: "土曜退院: ", options: { fontSize: 11, bold: true, color: COLOR.navyAccent } },
    { text: "2.44 件/日（従来水準）", options: { fontSize: 11, color: COLOR.gray, breakLine: true } },
    { text: "日曜退院: ", options: { fontSize: 11, bold: true, color: COLOR.green } },
    { text: "動かせる余地が大きい", options: { fontSize: 11, color: COLOR.gray } },
  ], {
    x: 8.05, y: 2.4, w: 4.7, h: 1.3, fontFace: FONT_B, margin: 0, valign: "top",
  });

  s.addShape(pres.shapes.RECTANGLE, {
    x: 7.8, y: 3.9, w: 5.0, h: 2.0,
    fill: { color: COLOR.white }, line: { color: COLOR.grayBg, width: 0.5 },
    shadow: { type: "outer", blur: 8, offset: 2, angle: 90, color: "000000", opacity: 0.08 },
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 7.8, y: 3.9, w: 0.08, h: 2.0, fill: { color: COLOR.green }, line: { type: "none" },
  });
  s.addText("運用設計", {
    x: 8.05, y: 4.0, w: 4.7, h: 0.35,
    fontFace: FONT_H, fontSize: 13, bold: true, color: COLOR.navy, margin: 0,
  });
  s.addText([
    { text: "週 2 床を土曜 → 日曜へシフト × 50 週", options: { fontSize: 11, color: COLOR.gray, breakLine: true } },
    { text: "年 100 床日 = +0.29% 稼働率", options: { fontSize: 11, color: COLOR.gray, breakLine: true } },
    { text: "", options: { fontSize: 4, breakLine: true } },
    { text: "運営貢献額 +348 万円/年", options: { fontSize: 15, bold: true, color: COLOR.red } },
  ], {
    x: 8.05, y: 4.4, w: 4.7, h: 1.4, fontFace: FONT_B, margin: 0, valign: "top",
  });

  // 下帯: 家族都合逆転
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 6.2, w: W - 1.0, h: 0.9,
    fill: { color: COLOR.gold }, line: { type: "none" },
  });
  s.addText("家族都合逆転", {
    x: 0.7, y: 6.3, w: W - 1.4, h: 0.35,
    fontFace: FONT_H, fontSize: 14, bold: true, color: COLOR.navyDark, align: "center", margin: 0,
  });
  s.addText("日曜は家族が仕事休みの方が多く、お迎えが取りやすい — 「日曜のお迎えはご都合いかがですか」のルーチン化", {
    x: 0.7, y: 6.7, w: W - 1.4, h: 0.4,
    fontFace: FONT_B, fontSize: 11, color: COLOR.navyDark, align: "center", italic: true, margin: 0,
  });
}

// =============================================================================
// Slide 17: v4 新提案③ — データ駆動×制度適応の三位一体
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 17);
  addPageTitle(s, "提案③ 三位一体 — 2026-06-01 本則適用の備え", "データ駆動 × 制度適応 × 需要予測校正の基盤を理事会定期報告に");

  // 3 基盤（横並び 3 カード）
  const bases = [
    { t: "📉 過去実績分析タブ", b: "サマリー KPI / 月別推移 / 曜日パターン / 時間帯 / 年齢 / リードタイム の 6 サブタブ — 毎週のカンファで確認", color: COLOR.blue },
    { t: "施設基準実態レポート", b: "救急搬送後 5F 53.1% / 6F 61.1%（基準 15% の 3.5-4.1 倍）、85+ 27.3% を理事会四半期報告", color: COLOR.navy },
    { t: "需要予測モデル校正", b: "月係数・曜日係数・時間帯係数を裏側自動適用。日別 MAE −12.7%、日曜 −44% 改善", color: COLOR.green },
  ];
  bases.forEach((b, i) => {
    const x = 0.5 + i * 4.2;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 1.9, w: 4.0, h: 2.3,
      fill: { color: COLOR.white }, line: { color: COLOR.grayBg, width: 0.5 },
      shadow: { type: "outer", blur: 8, offset: 2, angle: 90, color: "000000", opacity: 0.08 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 1.9, w: 4.0, h: 0.5, fill: { color: b.color }, line: { type: "none" },
    });
    s.addText(b.t, {
      x: x + 0.15, y: 1.95, w: 3.7, h: 0.4,
      fontFace: FONT_H, fontSize: 13, bold: true, color: COLOR.white, valign: "middle", margin: 0,
    });
    s.addText(b.b, {
      x: x + 0.2, y: 2.55, w: 3.6, h: 1.6,
      fontFace: FONT_B, fontSize: 11, color: COLOR.gray, margin: 0, valign: "top",
    });
  });

  // 下: 主要指標ダッシュボード表
  s.addText("主要指標ダッシュボード（v4 施設基準実態レポートより）", {
    x: 0.5, y: 4.4, w: W - 1.0, h: 0.35,
    fontFace: FONT_H, fontSize: 13, bold: true, color: COLOR.navy, margin: 0,
  });

  // 表ヘッダ
  const tableX = 0.5;
  const tableY = 4.85;
  const colW = [3.8, 2.8, 2.8, 2.9];
  s.addShape(pres.shapes.RECTANGLE, {
    x: tableX, y: tableY, w: W - 1.0, h: 0.4, fill: { color: COLOR.navy }, line: { type: "none" },
  });
  const headers = ["指標", "制度基準", "当院実績", "倍率・コメント"];
  headers.forEach((h, i) => {
    const x = tableX + colW.slice(0, i).reduce((a, b) => a + b, 0);
    s.addText(h, {
      x: x + 0.1, y: tableY, w: colW[i] - 0.2, h: 0.4,
      fontFace: FONT_H, fontSize: 11, bold: true, color: COLOR.white, valign: "middle", margin: 0,
    });
  });

  const rows = [
    ["救急搬送後 5F（通年）", "15% 以上", "53.1%", "約 3.5 倍"],
    ["救急搬送後 6F（通年）", "15% 以上", "61.1%", "約 4.1 倍"],
    ["救急搬送後 5F（rolling 3ヶ月）", "15% 以上", "54.4%", "3.6 倍"],
    ["救急搬送後 6F（rolling 3ヶ月）", "15% 以上", "60.1%", "4.0 倍"],
    ["85 歳以上患者割合", "20% 以上で LOS 緩和", "27.3%", "閾値 +7.3pt"],
  ];
  rows.forEach((row, i) => {
    const y = tableY + 0.4 + i * 0.35;
    s.addShape(pres.shapes.RECTANGLE, {
      x: tableX, y, w: W - 1.0, h: 0.35,
      fill: { color: i % 2 === 0 ? COLOR.white : COLOR.grayBg }, line: { color: COLOR.grayBg, width: 0.3 },
    });
    row.forEach((cell, j) => {
      const x = tableX + colW.slice(0, j).reduce((a, b) => a + b, 0);
      const isValue = j === 2;
      s.addText(cell, {
        x: x + 0.1, y, w: colW[j] - 0.2, h: 0.35,
        fontFace: isValue ? FONT_H : FONT_B, fontSize: 10.5,
        bold: isValue, color: isValue ? COLOR.red : COLOR.gray,
        valign: "middle", margin: 0,
      });
    });
  });
}

// =============================================================================
// Slide 18: 賞与インパクト — 290 名で分け合う +4%（新設）
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 18);
  addPageTitle(s, "賞与インパクト — 290 名で分け合う +4%", "+2,403 万円/年 → 夏冬賞与 各 +20,900 円/人の余地");

  // 左: 経営構造
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.9, w: 5.8, h: 3.2,
    fill: { color: COLOR.white }, line: { color: COLOR.grayBg, width: 0.5 },
    shadow: { type: "outer", blur: 8, offset: 2, angle: 90, color: "000000", opacity: 0.08 },
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.9, w: 0.08, h: 3.2, fill: { color: COLOR.navy }, line: { type: "none" },
  });
  s.addText("経営構造（当院の値）", {
    x: 0.75, y: 2.0, w: 5.5, h: 0.4,
    fontFace: FONT_H, fontSize: 14, bold: true, color: COLOR.navy, margin: 0,
  });

  const fiscal = [
    ["総スタッフ数", "290 名"],
    ["人件費率（売上対比）", "58%"],
    ["賞与率（月給に対する年間合計）", "190 – 200%（月給 3.9 ヶ月分/年）"],
    ["病床 / 稼働率 1% の価値", "94 床、1,199 万円/年"],
    ["人件費内の賞与原資比率", "約 21%"],
  ];
  fiscal.forEach(([l, v], i) => {
    const y = 2.5 + i * 0.48;
    s.addText(l, {
      x: 0.75, y, w: 3.5, h: 0.42,
      fontFace: FONT_B, fontSize: 11, color: COLOR.gray, margin: 0, valign: "middle",
    });
    s.addText(v, {
      x: 4.25, y, w: 2.0, h: 0.42,
      fontFace: FONT_H, fontSize: 11.5, bold: true, color: COLOR.navy, align: "right", margin: 0, valign: "middle",
    });
  });

  // 右: 試算ロジック（流れ図）
  s.addShape(pres.shapes.RECTANGLE, {
    x: 6.6, y: 1.9, w: 6.2, h: 3.2,
    fill: { color: COLOR.white }, line: { color: COLOR.grayBg, width: 0.5 },
    shadow: { type: "outer", blur: 8, offset: 2, angle: 90, color: "000000", opacity: 0.08 },
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 6.6, y: 1.9, w: 0.08, h: 3.2, fill: { color: COLOR.red }, line: { type: "none" },
  });
  s.addText("賞与インパクト試算式", {
    x: 6.85, y: 2.0, w: 5.9, h: 0.4,
    fontFace: FONT_H, fontSize: 14, bold: true, color: COLOR.navy, margin: 0,
  });

  const calc = [
    ["売上増（運営貢献額）", "+2,403 万円/年", COLOR.red],
    ["× 人件費率 58%", "= 1,394 万円/年", COLOR.navyAccent],
    ["÷ 1.15（社保分除く）", "= 1,212 万円/年 賞与原資", COLOR.navyAccent],
    ["÷ 290 名", "= +41,800 円/人/年", COLOR.green],
    ["÷ 2（夏冬）", "= +20,900 円/人/回", COLOR.gold],
  ];
  calc.forEach(([l, v, c], i) => {
    const y = 2.5 + i * 0.48;
    s.addShape(pres.shapes.RECTANGLE, {
      x: 6.85, y: y + 0.03, w: 0.15, h: 0.35, fill: { color: c }, line: { type: "none" },
    });
    s.addText(l, {
      x: 7.1, y, w: 2.9, h: 0.42,
      fontFace: FONT_B, fontSize: 11, color: COLOR.gray, margin: 0, valign: "middle",
    });
    s.addText(v, {
      x: 10.0, y, w: 2.7, h: 0.42,
      fontFace: FONT_H, fontSize: 11.5, bold: true, color: c, align: "right", margin: 0, valign: "middle",
    });
  });

  // 副院長ヒューリスティックとの整合性バナー
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 5.3, w: W - 1.0, h: 1.4,
    fill: { color: COLOR.navyDark }, line: { type: "none" },
  });
  s.addText("副院長ヒューリスティックとの整合性", {
    x: 0.7, y: 5.4, w: W - 1.4, h: 0.4,
    fontFace: FONT_H, fontSize: 14, bold: true, color: COLOR.gold, margin: 0,
  });
  s.addText([
    { text: "既存経験則: ", options: { fontSize: 12, color: COLOR.grayLight } },
    { text: "稼働率 +5% → 賞与原資 +10%", options: { fontSize: 12, bold: true, color: COLOR.white, breakLine: true } },
    { text: "本試算: ", options: { fontSize: 12, color: COLOR.grayLight } },
    { text: "稼働率 +2.00% → 賞与原資 +4.0% = +41,800 円/人/年（100 万 × 4% に一致）", options: { fontSize: 12, bold: true, color: COLOR.white, breakLine: true } },
    { text: "判定: ", options: { fontSize: 12, color: COLOR.grayLight } },
    { text: "整合 ✓", options: { fontSize: 14, bold: true, color: COLOR.green } },
  ], {
    x: 0.7, y: 5.85, w: W - 1.4, h: 0.85, fontFace: FONT_B, margin: 0, valign: "top",
  });

  // 最終スタンス注記
  s.addText("※ 本試算は「構造として存在する余力（上限）」を示すもので、実際の賞与配分は経営判断・内部留保とのバランスを含みます", {
    x: 0.5, y: 6.85, w: W - 1.0, h: 0.3,
    fontFace: FONT_B, fontSize: 9, color: COLOR.grayLight, italic: true, align: "center", margin: 0,
  });
}

// =============================================================================
// Slide 19: 2026-06-01 本則完全適用への備え（新設）
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 19);
  addPageTitle(s, "2026-06-01 本則完全適用への備え", "LOS 21 → 20 日、rolling 3 ヶ月判定、短手 3 階段関数 — 当院は準備済");

  // 変更 3 点の表
  const tx = 0.5;
  const ty = 1.9;
  const tColW = [2.8, 2.8, 3.2, 3.5];
  s.addShape(pres.shapes.RECTANGLE, {
    x: tx, y: ty, w: W - 1.0, h: 0.45, fill: { color: COLOR.navy }, line: { type: "none" },
  });
  const tHead = ["変更点", "現行（〜2026-05-31）", "本則（2026-06-01〜）", "当院実績"];
  tHead.forEach((h, i) => {
    const x = tx + tColW.slice(0, i).reduce((a, b) => a + b, 0);
    s.addText(h, {
      x: x + 0.1, y: ty, w: tColW[i] - 0.2, h: 0.45,
      fontFace: FONT_H, fontSize: 11, bold: true, color: COLOR.white, valign: "middle", margin: 0,
    });
  });

  const tRows = [
    ["① 平均在院日数", "21 日（緩和 22 日）", "20 日（緩和 21 日）", "5F 16.5 / 6F 15.6 日（余裕あり）"],
    ["② 救急搬送後割合", "単月 15% 以上", "rolling 3 ヶ月 15% 以上", "5F 54.4% / 6F 60.1%（約 3.6-4.0 倍）"],
    ["③ 短手 3 LOS 分母", "単純組入", "階段関数（Day 5/6 境界）", "月 22 名、Day 6 超過は月 1 名（4.5%）"],
  ];
  tRows.forEach((row, i) => {
    const y = ty + 0.45 + i * 0.55;
    s.addShape(pres.shapes.RECTANGLE, {
      x: tx, y, w: W - 1.0, h: 0.55,
      fill: { color: i % 2 === 0 ? COLOR.white : COLOR.grayBg }, line: { color: COLOR.grayBg, width: 0.3 },
    });
    row.forEach((cell, j) => {
      const x = tx + tColW.slice(0, j).reduce((a, b) => a + b, 0);
      const isImpact = j === 3;
      s.addText(cell, {
        x: x + 0.1, y, w: tColW[j] - 0.2, h: 0.55,
        fontFace: isImpact ? FONT_H : FONT_B, fontSize: 10.5,
        bold: j === 0 || isImpact, color: isImpact ? COLOR.green : (j === 0 ? COLOR.navy : COLOR.gray),
        valign: "middle", margin: 0,
      });
    });
  });

  // 中段: 85 歳以上 +1 日の明確化
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 4.3, w: W - 1.0, h: 1.1,
    fill: { color: COLOR.gold }, line: { type: "none" },
  });
  s.addText("85 歳以上 20% 以上で +1 日緩和 — 20 + 1 = 21 日（22 日ではない）", {
    x: 0.7, y: 4.4, w: W - 1.4, h: 0.4,
    fontFace: FONT_H, fontSize: 14, bold: true, color: COLOR.navyDark, align: "center", margin: 0,
  });
  s.addText("当院 85+ 割合 27.3% で閾値 20% を +7.3pt 上回っており、緩和条件クリア。推定 LOS 5F 16.5 / 6F 15.6 日 → 緩和後基準 21 日に対し 4〜5 日の余裕", {
    x: 0.7, y: 4.8, w: W - 1.4, h: 0.55,
    fontFace: FONT_B, fontSize: 11, color: COLOR.navyDark, align: "center", valign: "top", margin: 0,
  });

  // 下: 判定 + v4 先回り実装
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 5.55, w: 6.1, h: 1.55,
    fill: { color: COLOR.green }, line: { type: "none" },
  });
  s.addText("🟢 判定", {
    x: 0.7, y: 5.65, w: 5.7, h: 0.4,
    fontFace: FONT_H, fontSize: 14, bold: true, color: COLOR.white, margin: 0,
  });
  s.addText("現状の運営パターンで 2026-06-01 本則完全適用に対応可能\n全項目で安全マージンを持って達成", {
    x: 0.7, y: 6.05, w: 5.7, h: 1.0,
    fontFace: FONT_B, fontSize: 12, color: COLOR.white, margin: 0, valign: "top",
  });

  s.addShape(pres.shapes.RECTANGLE, {
    x: 6.9, y: 5.55, w: 5.9, h: 1.55,
    fill: { color: COLOR.navy }, line: { type: "none" },
  });
  s.addText("v4 先回り実装済", {
    x: 7.1, y: 5.65, w: 5.5, h: 0.4,
    fontFace: FONT_H, fontSize: 14, bold: true, color: COLOR.gold, margin: 0,
  });
  s.addText("• サイドバーに経過措置終了カウントダウンバナー\n• rolling 3 ヶ月判定（is_transitional_period() ゲート付）\n• LOS 階段関数（短手 3 Day 5/6 境界）+ Day 5 到達アラート", {
    x: 7.1, y: 6.05, w: 5.5, h: 1.0,
    fontFace: FONT_B, fontSize: 10.5, color: COLOR.white, margin: 0, valign: "top",
  });
}

// =============================================================================
// Slide 20: 実行計画とまとめ
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.navyDark };
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: W, h: 0.12, fill: { color: COLOR.gold }, line: { type: "none" },
  });
  s.addText(FOOTER_TEXT, {
    x: 0.5, y: H - 0.35, w: 9, h: 0.28,
    fontFace: FONT_B, fontSize: 9, color: COLOR.grayLight, margin: 0,
  });
  s.addText(`20 / ${TOTAL}`, {
    x: W - 1.3, y: H - 0.35, w: 0.8, h: 0.28,
    fontFace: FONT_B, fontSize: 9, color: COLOR.grayLight, align: "right", margin: 0,
  });

  s.addText("実行計画とまとめ", {
    x: 0.5, y: 0.35, w: W - 1.0, h: 0.7,
    fontFace: FONT_H, fontSize: 28, bold: true, color: COLOR.white, margin: 0, valign: "middle",
  });
  s.addText("v4 新 3 提案で年 2,403 万円 → 賞与 +4% の道筋", {
    x: 0.5, y: 1.1, w: W - 1.0, h: 0.4,
    fontFace: FONT_B, fontSize: 14, color: COLOR.gold, italic: true, margin: 0,
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.55, w: 1.2, h: 0.04, fill: { color: COLOR.gold }, line: { type: "none" },
  });

  s.addImage({
    path: path.join(CHART_DIR, "10_action_roadmap.png"),
    x: 0.5, y: 1.85, w: 8.5, h: 3.8, sizing: { type: "contain", w: 8.5, h: 3.8 },
  });

  // 実行計画 4 点
  const plans = [
    { t: "カンファで 3 タグ運用開始", b: "2026-05 〜（v4 カンファ資料タブで即運用可）", color: COLOR.blue },
    { t: "毎週の過去実績タブ確認", b: "2026-05 〜（病棟運営会議のルーチン化）", color: COLOR.navyAccent },
    { t: "GW2026 緊急パイロット", b: "2026-04-29 〜 9 連休で提案①先行試行", color: COLOR.red },
    { t: "理事会四半期定期報告", b: "2026-07 〜 施設基準実態レポート提出", color: COLOR.green },
  ];
  plans.forEach((p, i) => {
    const y = 1.95 + i * 0.92;
    s.addShape(pres.shapes.RECTANGLE, {
      x: 9.3, y, w: 3.5, h: 0.82,
      fill: { color: COLOR.white }, line: { color: p.color, width: 1.5 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x: 9.3, y, w: 0.08, h: 0.82, fill: { color: p.color }, line: { type: "none" },
    });
    s.addText(p.t, {
      x: 9.45, y: y + 0.08, w: 3.3, h: 0.32,
      fontFace: FONT_H, fontSize: 12, bold: true, color: COLOR.navy, margin: 0,
    });
    s.addText(p.b, {
      x: 9.45, y: y + 0.42, w: 3.3, h: 0.38,
      fontFace: FONT_B, fontSize: 10, color: COLOR.gray, margin: 0, valign: "top",
    });
  });

  // 本日のご決裁事項
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 5.85, w: W - 1.0, h: 1.3,
    fill: { color: COLOR.gold }, line: { type: "none" },
  });
  s.addText("本日のご決裁事項（3 項目）", {
    x: 0.7, y: 5.95, w: W - 1.4, h: 0.35,
    fontFace: FONT_H, fontSize: 15, bold: true, color: COLOR.navyDark, margin: 0,
  });
  s.addText([
    { text: "① v4 新 3 提案 の方向性ご承認（連休前+連休中分散退院型 / 日曜退院定着化 / 三位一体基盤）", options: { fontSize: 11, bold: true, color: COLOR.navyDark, breakLine: true } },
    { text: "② GW2026 緊急パイロット の実施可否判断（2026-04-29 〜 5/5 の 9 連休で先行試行）", options: { fontSize: 11, bold: true, color: COLOR.navyDark, breakLine: true } },
    { text: "③ 施設基準実態レポート の理事会四半期定期報告枠組のご承認（初回 2026-07）", options: { fontSize: 11, bold: true, color: COLOR.navyDark } },
  ], {
    x: 0.7, y: 6.35, w: W - 1.4, h: 0.8, fontFace: FONT_B, margin: 0, valign: "top",
  });
}

// =============================================================================
// Slide 21: Q&A セクション 前半（Q1-Q5）
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 21);
  addPageTitle(s, "想定 Q&A（1/2）", "データ信頼性 / 本則安全性 / 短手 3 余力 / 家族説明 / 他職種連携");

  const qas1 = [
    {
      q: "Q1: 実データ 1,965 件の信頼性は？",
      a: "電子カルテ抽出の月次 xlsx 12 ヶ月を統合。v3.6 までの 1,876 件は重複除去が過剰で、「同日・同病棟再入院」「転棟記録」の誤判定を含んでいた。v4 は 0 埋めカレンダー方式で再集計。4F 18 件は施設基準計算から除外。",
    },
    {
      q: "Q2: 2026-06-01 本則適用は本当に安全か？",
      a: "全項目で安全マージンを持って達成。救急搬送後 5F 53.1% / 6F 61.1%（基準 15% の 3.5-4.1 倍）、85+ 27.3%、推定 LOS 5F 16.5 / 6F 15.6 日（緩和後 21 日に対し 4-5 日の余裕）。",
    },
    {
      q: "Q3: 短手 3 の戦略的増加余力はあるか？",
      a: "救急搬送後割合が 3.5-4.1 倍の余裕なので十分にある。現在月 22 名 → 月 30 名程度は技術的可能。ただし消化器内科・紹介元病院との段階的調整が前提。v4 では Day 5/6 境界の影響を可視化する仕組みを整備。",
    },
    {
      q: "Q4: 連休中退院を家族にどう説明する？",
      a: "「状態が安定していれば、連休中のお迎えはご都合いかがですか」と選択肢として提示。強制ではない。カンファの「家族確認済み」フラグで管理し、同意が得られた方だけを連休中退院可タグに残す。",
    },
    {
      q: "Q5: 他職種との連携はどう進める？",
      a: "師長・MSW・リハ PT/OT/ST・主治医の 4 職種が既存の多職種カンファで 3 タグ分類。連休対策モード切替トグルを追加するだけで、新しい会議体は不要。",
    },
  ];
  qas1.forEach((qa, i) => {
    const y = 1.85 + i * 1.02;
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.5, y, w: W - 1.0, h: 0.97,
      fill: { color: COLOR.white }, line: { color: COLOR.grayBg, width: 0.5 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.5, y, w: 0.08, h: 0.97, fill: { color: COLOR.navy }, line: { type: "none" },
    });
    s.addText(qa.q, {
      x: 0.7, y: y + 0.08, w: W - 1.4, h: 0.35,
      fontFace: FONT_H, fontSize: 12, bold: true, color: COLOR.navy, margin: 0, valign: "top",
    });
    s.addText(qa.a, {
      x: 0.7, y: y + 0.42, w: W - 1.4, h: 0.5,
      fontFace: FONT_B, fontSize: 10, color: COLOR.gray, margin: 0, valign: "top",
    });
  });
}

// =============================================================================
// Slide 22: Q&A セクション 後半（Q6-Q10）
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 22);
  addPageTitle(s, "想定 Q&A（2/2）", "短期/長期効果 / 他病院事例 / 賞与保証 / スタッフ合意 / 失敗シナリオ");

  const qas2 = [
    {
      q: "Q6: 短期/長期それぞれの効果は？",
      a: "短期（2026-05〜07）: GW + 日曜退院で年換算 500-700 万円。中期（2026-08〜12）: お盆・SW・年末年始の本格運用で 1,200-1,800 万円。長期（2027 年度〜）: 5 大型連休で分散退院定着、年 2,400 万円 + 賞与 +4% が恒常化。",
    },
    {
      q: "Q7: 他病院の事例はあるのか？",
      a: "大学病院・大規模急性期病院では「連休前退院調整会議」の実装例あり。ただし中規模ケアミックス病院で「連休中退院も推奨する分散型」を体系化した事例は限定的。当院が先行事例・沖縄県内の地域医療連携モデルとなり得る。",
    },
    {
      q: "Q8: 賞与への自動反映は保証されるか？",
      a: "直接的な自動反映は組織構造として保証されない。本試算は「構造として存在する余力」を示すもの。当院の人件費構造上、売上増の約 21% が賞与原資として集約されるので、経営判断として還元方針が明示されれば試算通りの反映が可能。",
    },
    {
      q: "Q9: スタッフの理解・合意をどう形成するか？",
      a: "3 段階: ①師長会議で運用思想と賞与インパクト説明 / ②各病棟カンファで運用手順共有 / ③全スタッフに個別賞与インパクト試算を配布。「自分の賞与が +41,800 円/年」という具体数字で納得感を醸成。",
    },
    {
      q: "Q10: 失敗シナリオと撤退基準は？",
      a: "3 トリガー: ①連休明け週の空床吸収が前年同期比で 3 回連続改善なし / ②在宅復帰率が過去 12 ヶ月平均を 3% 以上下回る / ③退院支援 NS・MSW の残業が月 20 時間以上増加。いずれか該当で即時ロールバック + 原因分析。四半期理事会で可視化。",
    },
  ];
  qas2.forEach((qa, i) => {
    const y = 1.85 + i * 1.02;
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.5, y, w: W - 1.0, h: 0.97,
      fill: { color: COLOR.white }, line: { color: COLOR.grayBg, width: 0.5 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.5, y, w: 0.08, h: 0.97, fill: { color: COLOR.red }, line: { type: "none" },
    });
    s.addText(qa.q, {
      x: 0.7, y: y + 0.08, w: W - 1.4, h: 0.35,
      fontFace: FONT_H, fontSize: 12, bold: true, color: COLOR.red, margin: 0, valign: "top",
    });
    s.addText(qa.a, {
      x: 0.7, y: y + 0.42, w: W - 1.4, h: 0.5,
      fontFace: FONT_B, fontSize: 10, color: COLOR.gray, margin: 0, valign: "top",
    });
  });
}

// =============================================================================
// 書き出し
// =============================================================================
pres.writeFile({ fileName: OUTPUT }).then((fileName) => {
  console.log("✅ Wrote:", fileName);
}).catch((err) => {
  console.error("❌ Error:", err);
  process.exit(1);
});
