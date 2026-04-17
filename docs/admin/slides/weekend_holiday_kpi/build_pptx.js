/**
 * 週末・大型連休の稼働率対策プレゼン (16スライド)
 * Build: node build_pptx.js
 */
const pptxgen = require("pptxgenjs");
const path = require("path");

const CHART_DIR = path.join(__dirname, "charts");
const OUTPUT = path.join(__dirname, "weekend_holiday_kpi.pptx");

// =============================================================================
// 色・フォント
// =============================================================================
const COLOR = {
  navy: "1E3A5F",        // メインの濃紺（医療・信頼）
  navyDark: "122342",    // 最暗部（タイトル背景）
  navyAccent: "4A6FA5",  // 明るい紺（サブ）
  cream: "F7F5F0",       // 背景の淡いクリーム
  white: "FFFFFF",
  gray: "475569",        // 本文
  grayLight: "94A3B8",   // キャプション
  grayBg: "F1F5F9",      // 区画背景
  blue: "2E86AB",        // 予定入院（チャート連動）
  orange: "F18F01",      // 緊急入院（チャート連動）
  red: "C73E1D",         // 警告・落ち込み
  green: "4CAF50",       // 改善・ポジティブ
  gold: "C9A961",        // アクセント
};

const FONT_H = "Yu Gothic UI";       // 見出し
const FONT_B = "Yu Gothic";           // 本文

// =============================================================================
// ユーティリティ
// =============================================================================
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";  // 13.3" × 7.5" - 広めでリッチに
pres.author = "おもろまちメディカルセンター 副院長 久保田徹";
pres.title = "週末・大型連休の稼働率対策";
pres.subject = "経営会議資料";

const W = 13.3;  // スライド幅
const H = 7.5;   // スライド高

// ヘッダーバー・ページ番号・ロゴ行（タイトル以外の各スライドに適用）
function addFrame(slide, pageNum, totalPages) {
  // 上部の細い navy バー
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: W, h: 0.12,
    fill: { color: COLOR.navy }, line: { type: "none" },
  });
  // 下部フッター
  slide.addText("おもろまちメディカルセンター 経営会議資料 | 2026-04-17", {
    x: 0.5, y: H - 0.35, w: 9, h: 0.28,
    fontFace: FONT_B, fontSize: 9, color: COLOR.grayLight, margin: 0,
  });
  slide.addText(`${pageNum} / ${totalPages}`, {
    x: W - 1.3, y: H - 0.35, w: 0.8, h: 0.28,
    fontFace: FONT_B, fontSize: 9, color: COLOR.grayLight, align: "right", margin: 0,
  });
}

function addPageTitle(slide, title, subtitle) {
  // タイトル
  slide.addText(title, {
    x: 0.5, y: 0.35, w: W - 1.0, h: 0.75,
    fontFace: FONT_H, fontSize: 28, bold: true, color: COLOR.navy, margin: 0,
    valign: "middle",
  });
  // サブタイトル（あれば）
  if (subtitle) {
    slide.addText(subtitle, {
      x: 0.5, y: 1.1, w: W - 1.0, h: 0.4,
      fontFace: FONT_B, fontSize: 14, color: COLOR.navyAccent, italic: true, margin: 0,
    });
  }
  // 区切り線（左寄り）
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.55, w: 1.2, h: 0.04,
    fill: { color: COLOR.gold }, line: { type: "none" },
  });
}

// 数値ラベルのサークル（1,2,3... マーク）
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

// 左に縦アクセントバーのあるカード
function addAccentCard(slide, x, y, w, h, title, body, accentColor = COLOR.blue) {
  // 白背景
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h,
    fill: { color: COLOR.white }, line: { color: COLOR.grayBg, width: 0.5 },
    shadow: { type: "outer", blur: 8, offset: 2, angle: 90, color: "000000", opacity: 0.08 },
  });
  // 左アクセントバー
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w: 0.08, h,
    fill: { color: accentColor }, line: { type: "none" },
  });
  // タイトル
  slide.addText(title, {
    x: x + 0.25, y: y + 0.12, w: w - 0.35, h: 0.45,
    fontFace: FONT_H, fontSize: 14, bold: true, color: COLOR.navy, margin: 0,
    valign: "top",
  });
  // 本文
  slide.addText(body, {
    x: x + 0.25, y: y + 0.55, w: w - 0.35, h: h - 0.65,
    fontFace: FONT_B, fontSize: 11, color: COLOR.gray, margin: 0,
    valign: "top",
  });
}

// 巨大数字の KPI カード
function addBigStat(slide, x, y, w, h, value, label, unit = "", valueColor = COLOR.navy) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h,
    fill: { color: COLOR.white }, line: { color: COLOR.grayBg, width: 0.5 },
    shadow: { type: "outer", blur: 10, offset: 3, angle: 90, color: "000000", opacity: 0.08 },
  });
  // 大きな数値 + 単位（同じ行） — 上半分に配置
  const valueH = h * 0.58;
  const valueFont = h < 1.2 ? 32 : (h < 1.5 ? 38 : 42);
  slide.addText([
    { text: value, options: { fontFace: FONT_H, fontSize: valueFont, bold: true, color: valueColor } },
    { text: "  " + unit, options: { fontFace: FONT_B, fontSize: 13, color: COLOR.gray } },
  ], {
    x: x + 0.2, y: y + 0.12, w: w - 0.4, h: valueH,
    align: "left", valign: "middle", margin: 0,
  });
  // ラベル — 下部、数値と十分な間隔を確保
  slide.addText(label, {
    x: x + 0.2, y: y + valueH + 0.18, w: w - 0.4, h: h - valueH - 0.28,
    fontFace: FONT_B, fontSize: 11, color: COLOR.grayLight, margin: 0,
    valign: "top",
  });
}

const TOTAL = 16;

// =============================================================================
// Slide 1: タイトル
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.navyDark };
  // 上部装飾ライン
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0.6, w: W, h: 0.04, fill: { color: COLOR.gold }, line: { type: "none" } });
  // 英語サブ (タグライン風)
  s.addText("DATA-DRIVEN BED CONTROL PROPOSAL", {
    x: 0.8, y: 1.1, w: W - 1.6, h: 0.4,
    fontFace: FONT_H, fontSize: 12, bold: true, color: COLOR.gold, charSpacing: 6, margin: 0,
  });
  // メインタイトル
  s.addText("週末・大型連休の\n稼働率対策", {
    x: 0.8, y: 1.7, w: W - 1.6, h: 2.3,
    fontFace: FONT_H, fontSize: 56, bold: true, color: COLOR.white, margin: 0, lineSpacingMultiple: 1.05,
  });
  // 区切り装飾
  s.addShape(pres.shapes.RECTANGLE, { x: 0.8, y: 4.2, w: 0.8, h: 0.04, fill: { color: COLOR.gold }, line: { type: "none" } });
  // サブタイトル
  s.addText("— 過去12ヶ月実績（2025年4月〜2026年3月）に基づく提言 —", {
    x: 0.8, y: 4.35, w: W - 1.6, h: 0.5,
    fontFace: FONT_B, fontSize: 18, color: COLOR.cream, italic: true, margin: 0,
  });
  // 発表者情報ボックス（右下）
  s.addText([
    { text: "発表者 ", options: { fontSize: 11, color: COLOR.grayLight } },
    { text: "副院長  久保田  徹  ", options: { fontSize: 14, bold: true, color: COLOR.white, breakLine: true } },
    { text: "内科 / 呼吸器内科", options: { fontSize: 11, color: COLOR.grayLight, breakLine: true } },
    { text: "", options: { fontSize: 6, breakLine: true } },
    { text: "2026年4月17日  経営会議", options: { fontSize: 12, color: COLOR.gold } },
  ], {
    x: 0.8, y: 5.6, w: 6, h: 1.3, fontFace: FONT_B, margin: 0, valign: "top",
  });
  // 病院名（右下）
  s.addText([
    { text: "おもろまちメディカルセンター", options: { fontSize: 14, bold: true, color: COLOR.white, breakLine: true } },
    { text: "OMOROMACHI MEDICAL CENTER", options: { fontSize: 9, color: COLOR.gold, charSpacing: 4 } },
  ], {
    x: W - 5, y: 6.2, w: 4.3, h: 0.8,
    fontFace: FONT_H, align: "right", margin: 0, valign: "middle",
  });
}

// =============================================================================
// Slide 2: エグゼクティブサマリー
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 2, TOTAL);
  addPageTitle(s, "本日の要点", "4つの発見と、そこから導かれる 3つの提案");

  // 左右 2 列ヘッダー
  s.addText("4 つの発見", {
    x: 0.5, y: 1.85, w: 6.1, h: 0.4,
    fontFace: FONT_H, fontSize: 16, bold: true, color: COLOR.navy, margin: 0,
  });
  s.addText("3 つの提案", {
    x: 6.9, y: 1.85, w: 5.9, h: 0.4,
    fontFace: FONT_H, fontSize: 16, bold: true, color: COLOR.red, margin: 0,
  });

  // 発見 1-4（左） — 行間 1.1、4段
  const findings = [
    ["緊急は 8 割ではなく 58%", "予定入院のレバーは依然有効"],
    ["週末・連休の需要谷", "平日の 1/5 〜 1/16（GW -94%）"],
    ["緊急の 64% が日中集中", "13-18時に 694/1,081 件"],
    ["予定入院は 平均 16.3日前に予約", "運用で曜日を動かせる ← 本日の新発見"],
  ];
  findings.forEach(([title, body], i) => {
    const y = 2.35 + i * 1.1;
    addNumberCircle(s, 0.5, y, i + 1, COLOR.navy);
    s.addText(title, {
      x: 1.15, y: y - 0.02, w: 5.45, h: 0.4,
      fontFace: FONT_H, fontSize: 13, bold: true, color: COLOR.navy, margin: 0, valign: "top",
    });
    s.addText(body, {
      x: 1.15, y: y + 0.42, w: 5.45, h: 0.5,
      fontFace: FONT_B, fontSize: 11, color: COLOR.gray, margin: 0, valign: "top",
    });
  });

  // 縦の区切り線
  s.addShape(pres.shapes.RECTANGLE, {
    x: 6.75, y: 2.0, w: 0.02, h: 4.7, fill: { color: COLOR.grayLight }, line: { type: "none" },
  });

  // 提案 1-3（右） — 木曜前倒し提案を撤回し 3 項目に精査
  const proposals = [
    ["大型連休前の退院枠 事前確保", "連休明け詰め込みの回避"],
    ["連休前後の予約枠を data-driven 配置", "既存運用の体系化"],
    ["Phase 3α 需要予測ダッシュボード", "病棟運用判断の数字化基盤を緊急実装"],
  ];
  // 右列は 3 項目なので、縦間隔を広めに取って視認性を上げる
  proposals.forEach(([title, body], i) => {
    const y = 2.55 + i * 1.45;
    addNumberCircle(s, 6.9, y, i + 1, COLOR.red);
    s.addText(title, {
      x: 7.55, y: y - 0.02, w: 5.25, h: 0.45,
      fontFace: FONT_H, fontSize: 14, bold: true, color: COLOR.navy, margin: 0, valign: "top",
    });
    s.addText(body, {
      x: 7.55, y: y + 0.46, w: 5.25, h: 0.6,
      fontFace: FONT_B, fontSize: 11, color: COLOR.gray, margin: 0, valign: "top",
    });
  });

  // 目標 KPI フッターバナー（Phase 2 ベースに書き換え）
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 6.8, w: W - 1.0, h: 0.4,
    fill: { color: COLOR.navy }, line: { type: "none" },
  });
  s.addText([
    { text: "目標 KPI  ", options: { fontSize: 11, bold: true, color: COLOR.gold } },
    { text: "Phase 2 連休対策で 年間 300〜500 万円の空床ロス回収（5 大型連休合計）", options: { fontSize: 11, color: COLOR.white } },
  ], {
    x: 0.7, y: 6.8, w: W - 1.4, h: 0.4, fontFace: FONT_B, align: "center", valign: "middle", margin: 0,
  });

  // 注記: 当初案 Phase 1 撤回を明示（誠実さの担保）
  s.addText([
    { text: "※ 当初検討の「Phase 1 木曜退院前倒し」はデータ精査により撤回（高需要週は年 2〜3回のみ、経営インパクト限定的）。提案を 3 項目に精査。",
      options: { fontSize: 9, italic: true, color: COLOR.grayLight } },
  ], {
    x: 0.5, y: 7.25, w: W - 1.0, h: 0.3, fontFace: FONT_B, align: "center", valign: "middle", margin: 0,
  });
}

// =============================================================================
// Slide 3: データ概要と方法
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 3, TOTAL);
  addPageTitle(s, "データ概要と方法", "12ヶ月・1,876 件の入院実績を精査");

  // KPI 行（4 つの大きな数字カード）
  addBigStat(s, 0.5, 2.0, 3.0, 1.3, "1,876", "総入院件数（dedup 後）", "件", COLOR.navy);
  addBigStat(s, 3.65, 2.0, 3.0, 1.3, "365", "分析対象日数", "日", COLOR.navyAccent);
  addBigStat(s, 6.8, 2.0, 3.0, 1.3, "795", "予定入院（42.4%）", "件", COLOR.blue);
  addBigStat(s, 9.95, 2.0, 3.0, 1.3, "1,081", "緊急入院（57.6%）", "件", COLOR.orange);

  // 中段：方法論
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 3.7, w: W - 1.0, h: 2.3,
    fill: { color: COLOR.white }, line: { color: COLOR.grayBg, width: 0.5 },
    shadow: { type: "outer", blur: 8, offset: 2, angle: 90, color: "000000", opacity: 0.06 },
  });
  s.addText("分析方法", {
    x: 0.8, y: 3.85, w: 4, h: 0.4,
    fontFace: FONT_H, fontSize: 14, bold: true, color: COLOR.navy, margin: 0,
  });

  const methodItems = [
    ["期間", "2025-04-01 〜 2026-03-31（365日）"],
    ["分析単位", "1日あたり入院件数 × 曜日 / 月 / 連休 の3軸"],
    ["通常平日の定義", "祝日・週末・連休期間を除く月〜金（平均 7.06件/日）"],
    ["大型連休の定義", "連続休日 3日以上 かつ祝日を含む期間（GW・SW・お盆・年末年始・冬連休）"],
    ["データ処理", "元 1,965件 → 同一入院日時・病棟・年齢で判定した重複 89件を除去"],
  ];
  methodItems.forEach(([label, body], i) => {
    const y = 4.3 + i * 0.32;
    s.addText(label, {
      x: 0.8, y, w: 2.5, h: 0.28,
      fontFace: FONT_H, fontSize: 10, bold: true, color: COLOR.navyAccent, margin: 0,
    });
    s.addText(body, {
      x: 3.4, y, w: W - 4.3, h: 0.28,
      fontFace: FONT_B, fontSize: 10, color: COLOR.gray, margin: 0,
    });
  });

  // 下段：データソース注記
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 6.3, w: W - 1.0, h: 0.5,
    fill: { color: COLOR.grayBg }, line: { type: "none" },
  });
  s.addText([
    { text: "ソース: ", options: { fontSize: 10, bold: true, color: COLOR.navy } },
    { text: "data/admissions_consolidated_dedup.csv  |  ", options: { fontSize: 10, color: COLOR.gray } },
    { text: "重複検出キー: ", options: { fontSize: 10, bold: true, color: COLOR.navy } },
    { text: "admission_datetime × ward × age_code", options: { fontSize: 10, color: COLOR.gray } },
  ], {
    x: 0.7, y: 6.3, w: W - 1.4, h: 0.5, fontFace: FONT_B, align: "center", valign: "middle", margin: 0,
  });
}

// =============================================================================
// Slide 4: 曜日別入院パターンの実態
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 4, TOTAL);
  addPageTitle(s, "曜日別 1日あたり入院数", "月曜 7.9件、日曜 0.3件 — 需要の波は明白");

  // チャート（左 70%）
  s.addImage({
    path: path.join(CHART_DIR, "01_dow_admissions.png"),
    x: 0.5, y: 1.9, w: 8.0, h: 4.5, sizing: { type: "contain", w: 8.0, h: 4.5 },
  });

  // キーメッセージカード（右）
  const bullets = [
    { num: "1.", title: "月曜 7.92件/日", body: "院内平均の約1.5倍。週明けの受入負荷集中" },
    { num: "2.", title: "金曜は既に予定抑制", body: "予定 1.50件のみ — 予定入院は週後半を回避済み" },
    { num: "3.", title: "日曜は 0.29件", body: "「埋める」より「空けない」設計へ転換が必要" },
  ];
  bullets.forEach((b, i) => {
    const y = 2.1 + i * 1.45;
    addAccentCard(s, 8.8, y, 4.0, 1.25, `${b.num}  ${b.title}`, b.body, COLOR.navy);
  });
}

// =============================================================================
// Slide 5: ばらつきで見る曜日差
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 5, TOTAL);
  addPageTitle(s, "箱ひげ図で見る構造的パターン", "平日と週末の「箱」は別の領域にある");

  // チャート（中央大）
  s.addImage({
    path: path.join(CHART_DIR, "02_dow_boxplot.png"),
    x: 2.0, y: 1.85, w: 9.3, h: 4.2, sizing: { type: "contain", w: 9.3, h: 4.2 },
  });

  // 下段 3 メッセージ
  const msgs = [
    { title: "平日 × 週末の分布は重ならない", body: "平日 P25 が週末 P75 を上回る曜日が大半" },
    { title: "金曜は境界日", body: "中央値 5件・P25 約3件 — 週末側へ寄りつつある" },
    { title: "偶発性ではなく「曜日構造」", body: "対策は設計で立てるべきもの" },
  ];
  msgs.forEach((m, i) => {
    const x = 0.5 + i * 4.2;
    addAccentCard(s, x, 6.15, 4.0, 0.95, m.title, m.body, [COLOR.blue, COLOR.orange, COLOR.gold][i]);
  });
}

// =============================================================================
// Slide 6: 季節性の観察
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 6, TOTAL);
  addPageTitle(s, "月別トレンド — 季節性", "12月の谷・夏秋の山  月次変動は曜日変動より穏やか");

  // チャート（左）
  s.addImage({
    path: path.join(CHART_DIR, "03_monthly_trend.png"),
    x: 0.5, y: 1.9, w: 8.2, h: 4.5, sizing: { type: "contain", w: 8.2, h: 4.5 },
  });

  // 右側：stat callouts（カード高さを揃える）
  addBigStat(s, 9.0, 2.0, 3.8, 1.45, "4.61", "最低：2025-12", "件/日", COLOR.navyAccent);
  addBigStat(s, 9.0, 3.6, 3.8, 1.45, "5.71", "最高：7月・10月", "件/日", COLOR.green);
  addBigStat(s, 9.0, 5.2, 3.8, 1.2, "1.1", "月次振幅（曜日変動より小）", "件/日", COLOR.gold);

  // 下段のポイント
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 6.55, w: W - 1.0, h: 0.35,
    fill: { color: COLOR.navy }, line: { type: "none" },
  });
  s.addText("12月 = 緩和策（需要を維持）   /   夏秋 = 吸収策（ベッドフロー加速）   — 求められる戦略は季節で逆方向", {
    x: 0.7, y: 6.55, w: W - 1.4, h: 0.35,
    fontFace: FONT_B, fontSize: 12, color: COLOR.white, align: "center", valign: "middle", margin: 0, italic: true,
  });
}

// =============================================================================
// Slide 7: 大型連休で何が起きているか
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 7, TOTAL);
  addPageTitle(s, "大型連休の入院ドロップ", "GW は平日の 3% しか機能していない");

  // チャート（左）
  s.addImage({
    path: path.join(CHART_DIR, "04_holiday_drop.png"),
    x: 0.5, y: 1.9, w: 8.0, h: 4.8, sizing: { type: "contain", w: 8.0, h: 4.8 },
  });

  // 右：Alert stat - 巨大数字
  s.addShape(pres.shapes.RECTANGLE, {
    x: 8.8, y: 2.0, w: 4.0, h: 2.2, fill: { color: COLOR.red }, line: { type: "none" },
  });
  s.addText("−94%", {
    x: 8.8, y: 2.1, w: 4.0, h: 1.4,
    fontFace: FONT_H, fontSize: 72, bold: true, color: COLOR.white, align: "center", valign: "middle", margin: 0,
  });
  s.addText("GW 2025 の落ち込み率\n（直前2週比）", {
    x: 8.8, y: 3.4, w: 4.0, h: 0.8,
    fontFace: FONT_B, fontSize: 13, color: COLOR.white, align: "center", valign: "top", margin: 0,
  });

  // 下のリスト
  addAccentCard(s, 8.8, 4.4, 4.0, 0.85, "GW・年末年始: 実質休業", "4日間で合計1件のGWは異常値", COLOR.red);
  addAccentCard(s, 8.8, 5.35, 4.0, 0.85, "お盆 -39.5% は例外", "沖縄固有の帰省医療需要を反映", COLOR.orange);
  addAccentCard(s, 8.8, 6.3, 4.0, 0.55, "二値構造", "連休は「入るか/入らないか」", COLOR.gold);
}

// =============================================================================
// Slide 8: GW の具体例
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 8, TOTAL);
  addPageTitle(s, "ケーススタディ：GW 2025", "連休明けの 13件 を捌くには、連休前の退院枠が必要");

  // チャート（大）
  s.addImage({
    path: path.join(CHART_DIR, "07_gw_daily.png"),
    x: 0.5, y: 1.9, w: 9.5, h: 4.8, sizing: { type: "contain", w: 9.5, h: 4.8 },
  });

  // 右側：縦3カード
  addAccentCard(s, 10.3, 2.0, 2.55, 1.5,
    "5/3 – 5/6", "合計1件 — 実質ゼロ稼働の 4日間", COLOR.red);
  addAccentCard(s, 10.3, 3.6, 2.55, 1.5,
    "5/7（水） 13件", "連休明け — 通常の約2倍", COLOR.orange);
  addAccentCard(s, 10.3, 5.2, 2.55, 1.5,
    "示唆", "連休前に退院枠を確保しなければ連休明けの受入が破綻する", COLOR.navy);
}

// =============================================================================
// Slide 9: 年末年始の具体例
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 9, TOTAL);
  addPageTitle(s, "ケーススタディ：年末年始", "助走期間がある  ＝  計画が立てやすい");

  s.addImage({
    path: path.join(CHART_DIR, "08_nenmatsu_daily.png"),
    x: 0.5, y: 1.9, w: 9.5, h: 4.8, sizing: { type: "contain", w: 9.5, h: 4.8 },
  });

  addAccentCard(s, 10.3, 2.0, 2.55, 1.5,
    "12/27 – 1/4", "9日間 平均 1.00件/日", COLOR.red);
  addAccentCard(s, 10.3, 3.6, 2.55, 1.5,
    "助走期間あり", "12/20 頃から漸減 → 退院計画が立てやすい", COLOR.green);
  addAccentCard(s, 10.3, 5.2, 2.55, 1.5,
    "連休中は緊急のみ", "予定で介入できるのは連休前後のみ", COLOR.navy);
}

// =============================================================================
// Slide 10: 緊急入院の時刻分布
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 10, TOTAL);
  addPageTitle(s, "緊急入院の時刻分布 — 論旨の核心", "退院した床は、その日の午後に埋まる");

  s.addImage({
    path: path.join(CHART_DIR, "05_emergency_hour.png"),
    x: 0.5, y: 1.9, w: 8.0, h: 4.7, sizing: { type: "contain", w: 8.0, h: 4.7 },
  });

  // 右上：巨大 64.2% カード
  s.addShape(pres.shapes.RECTANGLE, {
    x: 8.8, y: 2.0, w: 4.0, h: 2.4,
    fill: { color: COLOR.orange }, line: { type: "none" },
  });
  s.addText("64.2%", {
    x: 8.8, y: 2.15, w: 4.0, h: 1.5,
    fontFace: FONT_H, fontSize: 68, bold: true, color: COLOR.white, align: "center", valign: "middle", margin: 0,
  });
  s.addText("緊急入院が 13–18時 に集中\n（694 / 1,081件）", {
    x: 8.8, y: 3.55, w: 4.0, h: 0.85,
    fontFace: FONT_B, fontSize: 13, color: COLOR.white, align: "center", valign: "top", margin: 0,
  });

  addAccentCard(s, 8.8, 4.6, 4.0, 0.85, "深夜 0-5時: 5件のみ", "「夜中にどんどん来る」は誤認", COLOR.navyAccent);
  addAccentCard(s, 8.8, 5.55, 4.0, 1.15,
    "前倒し退院の正当性", "午前退院の床は、その日の午後に発生する緊急で同日充填される可能性が高い",
    COLOR.green);
}

// =============================================================================
// Slide 11: リードタイム分布 (NEW)
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 11, TOTAL);
  addPageTitle(s, "予定入院は運用で動かせる — リードタイム分析", "平均 16.3日前 に予約 — 曜日を動かせる余地がある");

  s.addImage({
    path: path.join(CHART_DIR, "11_lead_time_dist.png"),
    x: 0.5, y: 1.9, w: 8.0, h: 4.7, sizing: { type: "contain", w: 8.0, h: 4.7 },
  });

  // 右：統計 3カード
  addBigStat(s, 8.8, 2.0, 4.0, 1.4, "12.0", "中央値リードタイム", "日", COLOR.navy);
  addBigStat(s, 8.8, 3.55, 4.0, 1.4, "61%", "8日以上前に予約", "", COLOR.green);
  addBigStat(s, 8.8, 5.1, 4.0, 1.4, "3 – 21", "P25 – P75", "日", COLOR.gold);

  // 下帯
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 6.8, w: W - 1.0, h: 0.4,
    fill: { color: COLOR.navy }, line: { type: "none" },
  });
  s.addText("「動かせない」という前提を、数字で更新する", {
    x: 0.7, y: 6.8, w: W - 1.4, h: 0.4,
    fontFace: FONT_H, fontSize: 14, bold: true, color: COLOR.white, align: "center", valign: "middle", margin: 0,
  });
}

// =============================================================================
// Slide 12: 登録曜日×入院曜日 ヒートマップ (NEW)
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 12, TOTAL);
  addPageTitle(s, "登録曜日と入院曜日のマッピング", "木曜・金曜を避けて 月〜水 に寄せる再配置の自由度");

  // チャート中央大
  s.addImage({
    path: path.join(CHART_DIR, "12_register_dow_vs_admit_dow.png"),
    x: 2.5, y: 1.85, w: 8.3, h: 4.3, sizing: { type: "contain", w: 8.3, h: 4.3 },
  });

  // 下段 3 カード
  const msgs = [
    { title: "月〜水 登録 → 火〜金 配置", body: "典型パターンは「同週後半」" },
    { title: "土日 登録はほぼゼロ", body: "週末予約での空床埋めは物理的に不可" },
    { title: "再配置の射程あり", body: "木金 209件の一部を月〜水 に寄せる運用が候補" },
  ];
  msgs.forEach((m, i) => {
    const x = 0.5 + i * 4.2;
    addAccentCard(s, x, 6.25, 4.0, 0.85, m.title, m.body, [COLOR.blue, COLOR.navyAccent, COLOR.green][i]);
  });
}

// =============================================================================
// Slide 13: 連休前後の予約集中 (NEW)
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 13, TOTAL);
  addPageTitle(s, "連休前後の予約集中", "既に動いている運用の延長  ＝  新規運用ではなく体系化");

  s.addImage({
    path: path.join(CHART_DIR, "13_holiday_lead_window.png"),
    x: 0.5, y: 1.9, w: 8.0, h: 4.7, sizing: { type: "contain", w: 8.0, h: 4.7 },
  });

  // 右
  addAccentCard(s, 8.8, 2.0, 4.0, 1.3, "連休期間内の予定はほぼゼロ", "GW・SW は完全にゼロ、お盆のみ例外", COLOR.red);
  addAccentCard(s, 8.8, 3.45, 4.0, 1.3, "明け週 > 前週", "GW: 4 → 28件  /  年末年始: 12 → 13件", COLOR.green);
  addAccentCard(s, 8.8, 4.9, 4.0, 1.35, "Phase 2 の本質", "新規運用の導入ではなく、既存の現場運用を data-driven に体系化する", COLOR.navy);

  // 帯
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 6.8, w: W - 1.0, h: 0.4,
    fill: { color: COLOR.gold }, line: { type: "none" },
  });
  s.addText("沖縄固有の帰省医療需要（お盆）は地域特性として存置 — 一律削減はしない", {
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
  addFrame(s, 14, TOTAL);
  addPageTitle(s, "区分別 1日平均", "ギャップ -5.69件/日 の 1/3 を取り戻す");

  s.addImage({
    path: path.join(CHART_DIR, "06_category_comparison.png"),
    x: 0.5, y: 1.9, w: 8.0, h: 4.7, sizing: { type: "contain", w: 8.0, h: 4.7 },
  });

  // 巨大ギャップ数字
  s.addShape(pres.shapes.RECTANGLE, {
    x: 8.8, y: 2.0, w: 4.0, h: 2.4,
    fill: { color: COLOR.navyDark }, line: { type: "none" },
  });
  s.addText("−5.69", {
    x: 8.8, y: 2.15, w: 4.0, h: 1.3,
    fontFace: FONT_H, fontSize: 60, bold: true, color: COLOR.gold, align: "center", valign: "middle", margin: 0,
  });
  s.addText("件/日  平日 vs 週末の差\n= 吸収したい「谷」", {
    x: 8.8, y: 3.4, w: 4.0, h: 1.0,
    fontFace: FONT_B, fontSize: 13, color: COLOR.white, align: "center", valign: "top", margin: 0,
  });

  // 下
  addAccentCard(s, 8.8, 4.6, 4.0, 1.0, "完全解消は不要", "ギャップの 1/3 取り戻しで土日平均 4床改善", COLOR.green);
  addAccentCard(s, 8.8, 5.75, 4.0, 1.0, "経営効果", "入院単価 13-15万円 × 年700件 ≒ 1,000万円/年", COLOR.gold);
}

// =============================================================================
// Slide 15: Phase 2 連休対策（旧 Slide 16 — 番号繰り上げ）
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.cream };
  addFrame(s, 15, TOTAL);
  addPageTitle(s, "Phase 2 — 連休対策：前退院枠 & 予約枠最適化", "連休 3週前 からの退院調整と連休明け予約枠の事前確保");

  // 大きな図解スペース
  // 左側: Phase 2 のフロー図
  const flowY = 2.0;
  const stages = [
    { label: "連休 3週前", text: "退院ターゲット\nリスト作成", color: COLOR.blue },
    { label: "連休 2週前", text: "多職種会議で\n退院計画確定", color: COLOR.navyAccent },
    { label: "連休 1週前", text: "退院実行\n病棟空床準備", color: COLOR.orange },
    { label: "連休中", text: "低稼働を前提とした\n運営体制", color: COLOR.red },
    { label: "連休明け", text: "予約枠最大活用で\n需要の波を受ける", color: COLOR.green },
  ];
  stages.forEach((st, i) => {
    const x = 0.5 + i * 2.56;
    // 上ラベル
    s.addText(st.label, {
      x, y: flowY, w: 2.4, h: 0.35,
      fontFace: FONT_H, fontSize: 11, bold: true, color: COLOR.navy, align: "center", margin: 0,
    });
    // 箱
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: flowY + 0.4, w: 2.4, h: 1.5,
      fill: { color: st.color }, line: { type: "none" },
    });
    s.addText(st.text, {
      x, y: flowY + 0.4, w: 2.4, h: 1.5,
      fontFace: FONT_B, fontSize: 12, bold: true, color: COLOR.white, align: "center", valign: "middle", margin: 0,
    });
    // 矢印
    if (i < stages.length - 1) {
      s.addShape(pres.shapes.RIGHT_TRIANGLE, {
        x: x + 2.45, y: flowY + 1.05, w: 0.12, h: 0.2,
        fill: { color: COLOR.navy }, line: { type: "none" }, rotate: 90,
      });
    }
  });

  // 下半分: 4 メッセージ箱 + GW2026 提案
  const bullets = [
    { n: "1", t: "同日充填は効かない", b: "連休中は緊急入院も激減 — Phase 1 の発想が通用しない" },
    { n: "2", t: "連休前に退院を済ませる", b: "3週前からの退院調整 + ターゲット患者リスト" },
    { n: "3", t: "連休明け初日の受入最大化", b: "GW2025 では明け水曜に 13件の突発対応が発生" },
    { n: "4", t: "既に動いている運用の延長", b: "Slide 13 のとおり、現場では部分的に実施中 → 体系化" },
  ];
  bullets.forEach((b, i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const x = 0.5 + col * 6.4;
    const y = 4.2 + row * 1.15;
    addNumberCircle(s, x, y + 0.15, b.n, COLOR.navy);
    s.addText(b.t, {
      x: x + 0.65, y: y + 0.12, w: 5.6, h: 0.4,
      fontFace: FONT_H, fontSize: 12, bold: true, color: COLOR.navy, margin: 0, valign: "top",
    });
    s.addText(b.b, {
      x: x + 0.65, y: y + 0.5, w: 5.6, h: 0.5,
      fontFace: FONT_B, fontSize: 10, color: COLOR.gray, margin: 0, valign: "top",
    });
  });

  // GW2026 緊急提案 帯
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 6.6, w: W - 1.0, h: 0.6,
    fill: { color: COLOR.red }, line: { type: "none" },
  });
  s.addText([
    { text: "緊急提案: ", options: { fontSize: 14, bold: true, color: COLOR.gold } },
    { text: "GW2026（4/29〜5/5 の9連休）を Phase 2 の緊急パイロットに設定し、今月下旬から退院調整会議で試行",
      options: { fontSize: 13, color: COLOR.white } },
  ], {
    x: 0.7, y: 6.6, w: W - 1.4, h: 0.6, fontFace: FONT_B, align: "center", valign: "middle", margin: 0,
  });
}

// =============================================================================
// Slide 16: ロードマップとネクストアクション（旧 Slide 17 — 番号繰り上げ）
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: COLOR.navyDark };  // 最後はダークで締める
  // フレームも少し変える
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: W, h: 0.12, fill: { color: COLOR.gold }, line: { type: "none" },
  });
  s.addText("おもろまちメディカルセンター 経営会議資料 | 2026-04-17", {
    x: 0.5, y: H - 0.35, w: 9, h: 0.28,
    fontFace: FONT_B, fontSize: 9, color: COLOR.grayLight, margin: 0,
  });
  s.addText(`${TOTAL} / ${TOTAL}`, {
    x: W - 1.3, y: H - 0.35, w: 0.8, h: 0.28,
    fontFace: FONT_B, fontSize: 9, color: COLOR.grayLight, align: "right", margin: 0,
  });

  // タイトル
  s.addText("ロードマップと本日のご決裁事項", {
    x: 0.5, y: 0.35, w: W - 1.0, h: 0.7,
    fontFace: FONT_H, fontSize: 28, bold: true, color: COLOR.white, margin: 0, valign: "middle",
  });
  s.addText("Phase 3α 緊急追加で 4 フェーズ構成 — 本則適用と同期して稼働", {
    x: 0.5, y: 1.1, w: W - 1.0, h: 0.4,
    fontFace: FONT_B, fontSize: 14, color: COLOR.gold, italic: true, margin: 0,
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.55, w: 1.2, h: 0.04, fill: { color: COLOR.gold }, line: { type: "none" },
  });

  // チャート
  s.addImage({
    path: path.join(CHART_DIR, "10_action_roadmap.png"),
    x: 0.5, y: 1.85, w: 8.5, h: 3.8, sizing: { type: "contain", w: 8.5, h: 3.8 },
  });

  // 右側：4 Phase カード（Phase 1 撤回で 4 段構成）
  const phases = [
    { t: "Phase 3α (4月下旬〜)", b: "アプリ緊急改修・需要予測モジュール", color: COLOR.red },
    { t: "GW 緊急パイロット", b: "4/20〜5/7 先行試行（α 版活用）", color: "9333EA" },
    { t: "Phase 2 (8月〜)", b: "連休前退院枠・予約枠最適化", color: COLOR.orange },
    { t: "Phase 3β (10月〜)", b: "ダッシュボード完成・院内展開", color: COLOR.green },
  ];
  phases.forEach((p, i) => {
    const y = 1.95 + i * 0.92;
    // 白いカード（完全不透明）
    s.addShape(pres.shapes.RECTANGLE, {
      x: 9.3, y, w: 3.5, h: 0.82,
      fill: { color: COLOR.white }, line: { color: p.color, width: 1.5 },
    });
    // 左アクセントバー
    s.addShape(pres.shapes.RECTANGLE, {
      x: 9.3, y, w: 0.08, h: 0.82, fill: { color: p.color }, line: { type: "none" },
    });
    // タイトル（濃紺）
    s.addText(p.t, {
      x: 9.45, y: y + 0.08, w: 3.3, h: 0.32,
      fontFace: FONT_H, fontSize: 12, bold: true, color: COLOR.navy, margin: 0,
    });
    // 本文（グレー）
    s.addText(p.b, {
      x: 9.45, y: y + 0.42, w: 3.3, h: 0.38,
      fontFace: FONT_B, fontSize: 10, color: COLOR.gray, margin: 0, valign: "top",
    });
  });

  // 下段：本日のご決裁事項ボックス（2 項目に縮小）
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 5.85, w: W - 1.0, h: 1.3,
    fill: { color: COLOR.gold }, line: { type: "none" },
  });
  s.addText("本日のご決裁事項（2 項目）", {
    x: 0.7, y: 5.95, w: W - 1.4, h: 0.35,
    fontFace: FONT_H, fontSize: 15, bold: true, color: COLOR.navyDark, margin: 0,
  });
  s.addText([
    { text: "① Phase 3α（アプリ緊急改修）の開始承認 ― 2026年4月下旬〜5月中旬", options: { fontSize: 11, bold: true, color: COLOR.navyDark, breakLine: true } },
    { text: "② GW2026 緊急パイロットの可否判断（4/20 頃からの退院調整試行）", options: { fontSize: 11, bold: true, color: COLOR.navyDark } },
  ], {
    x: 0.7, y: 6.35, w: W - 1.4, h: 0.8, fontFace: FONT_B, margin: 0, valign: "top",
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
