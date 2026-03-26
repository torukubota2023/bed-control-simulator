#!/usr/bin/env python3
"""Generate 2026 Nursing Necessity Strategy PDF for Omoromachi Medical Center."""

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

# --- Colors ---
NAVY = HexColor("#1a2744")
TEAL = HexColor("#0d7377")
CORAL = HexColor("#e8524a")
LIGHT_BG = HexColor("#f0f4f8")
LIGHT_TEAL = HexColor("#e6f3f3")
LIGHT_CORAL = HexColor("#fce8e6")
LIGHT_YELLOW = HexColor("#fff8e1")
DARK_GRAY = HexColor("#333333")
MID_GRAY = HexColor("#666666")
LIGHT_GRAY = HexColor("#eeeeee")

# --- Font Registration ---
FONT_TTC = "/System/Library/AssetsV2/com_apple_MobileAsset_Font8/42529d87b12845309dd4a57dea9e58446826e94c.asset/AssetData/BIZ_UDGothic.ttc"
pdfmetrics.registerFont(TTFont("HiraginoW3", FONT_TTC, subfontIndex=0))  # Regular
pdfmetrics.registerFont(TTFont("HiraginoW6", FONT_TTC, subfontIndex=1))  # Bold

# --- Styles ---
def make_styles():
    s = {}
    s["title"] = ParagraphStyle(
        "title", fontName="HiraginoW6", fontSize=22, leading=30,
        textColor=NAVY, alignment=TA_CENTER, spaceAfter=4*mm
    )
    s["subtitle"] = ParagraphStyle(
        "subtitle", fontName="HiraginoW3", fontSize=11, leading=16,
        textColor=MID_GRAY, alignment=TA_CENTER, spaceAfter=8*mm
    )
    s["h1"] = ParagraphStyle(
        "h1", fontName="HiraginoW6", fontSize=16, leading=22,
        textColor=NAVY, spaceBefore=10*mm, spaceAfter=5*mm
    )
    s["h2"] = ParagraphStyle(
        "h2", fontName="HiraginoW6", fontSize=13, leading=18,
        textColor=TEAL, spaceBefore=7*mm, spaceAfter=3*mm
    )
    s["h3"] = ParagraphStyle(
        "h3", fontName="HiraginoW6", fontSize=11, leading=16,
        textColor=DARK_GRAY, spaceBefore=5*mm, spaceAfter=2*mm
    )
    s["body"] = ParagraphStyle(
        "body", fontName="HiraginoW3", fontSize=9.5, leading=15,
        textColor=DARK_GRAY, spaceAfter=2*mm
    )
    s["bold"] = ParagraphStyle(
        "bold", fontName="HiraginoW6", fontSize=9.5, leading=15,
        textColor=DARK_GRAY, spaceAfter=2*mm
    )
    s["bullet"] = ParagraphStyle(
        "bullet", fontName="HiraginoW3", fontSize=9.5, leading=15,
        textColor=DARK_GRAY, leftIndent=12*mm, bulletIndent=5*mm,
        spaceAfter=1.5*mm
    )
    s["code"] = ParagraphStyle(
        "code", fontName="HiraginoW3", fontSize=9, leading=14,
        textColor=DARK_GRAY, backColor=LIGHT_BG, leftIndent=5*mm,
        rightIndent=5*mm, spaceBefore=2*mm, spaceAfter=3*mm,
        borderPadding=(3*mm, 3*mm, 3*mm, 3*mm)
    )
    s["alert"] = ParagraphStyle(
        "alert", fontName="HiraginoW6", fontSize=10, leading=15,
        textColor=CORAL, spaceAfter=2*mm
    )
    s["small"] = ParagraphStyle(
        "small", fontName="HiraginoW3", fontSize=8, leading=12,
        textColor=MID_GRAY, spaceAfter=1*mm
    )
    s["footer"] = ParagraphStyle(
        "footer", fontName="HiraginoW3", fontSize=7, leading=10,
        textColor=MID_GRAY, alignment=TA_CENTER
    )
    return s


def colored_box(text, bg_color, text_color=white, font="HiraginoW6", size=10):
    """Create a colored background paragraph."""
    style = ParagraphStyle(
        "cbox", fontName=font, fontSize=size, leading=size+5,
        textColor=text_color, backColor=bg_color, alignment=TA_CENTER,
        borderPadding=(3*mm, 5*mm, 3*mm, 5*mm), spaceAfter=3*mm
    )
    return Paragraph(text, style)


def make_table(headers, rows, col_widths=None, header_bg=NAVY, stripe=True):
    """Create a styled table."""
    data = [headers] + rows
    if col_widths is None:
        col_widths = [170*mm / len(headers)] * len(headers)

    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, 0), "HiraginoW6"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTNAME", (0, 1), (-1, -1), "HiraginoW3"),
        ("FONTSIZE", (0, 1), (-1, -1), 8.5),
        ("LEADING", (0, 0), (-1, -1), 13),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#cccccc")),
        ("TOPPADDING", (0, 0), (-1, -1), 3*mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3*mm),
        ("LEFTPADDING", (0, 0), (-1, -1), 3*mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3*mm),
    ]
    if stripe:
        for i in range(1, len(data)):
            if i % 2 == 0:
                style_cmds.append(("BACKGROUND", (0, i), (-1, i), LIGHT_BG))

    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle(style_cmds))
    return t


def add_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("HiraginoW3", 7)
    canvas.setFillColor(MID_GRAY)
    canvas.drawCentredString(
        A4[0] / 2, 12*mm,
        f"おもろまちメディカルセンター | 2026年度改定 看護必要度 統一戦略 | {doc.page}"
    )
    # Top color bar
    canvas.setFillColor(NAVY)
    canvas.rect(0, A4[1] - 5*mm, A4[0], 5*mm, fill=1, stroke=0)
    canvas.setFillColor(TEAL)
    canvas.rect(0, A4[1] - 7*mm, A4[0], 2*mm, fill=1, stroke=0)
    canvas.restoreState()


def build_pdf():
    output_path = "/Users/torukubota/ai-management/docs/admin/2026_nursing_necessity_unified_strategy.pdf"
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        topMargin=18*mm, bottomMargin=20*mm,
        leftMargin=15*mm, rightMargin=15*mm
    )
    S = make_styles()
    story = []

    # ============================================================
    # COVER / TITLE
    # ============================================================
    story.append(Spacer(1, 20*mm))
    story.append(Paragraph("2026年度改定", S["title"]))
    story.append(Paragraph("看護必要度 統一戦略", S["title"]))
    story.append(Spacer(1, 5*mm))
    story.append(Paragraph(
        "おもろまちメディカルセンター ── 稼働率90%と基準クリアの両立",
        S["subtitle"]
    ))
    story.append(Spacer(1, 8*mm))

    # Purpose box
    story.append(colored_box(
        "目的：全職員が「何をすればいいか」を理解し、一致団結して基準達成 → 十分な賞与確保",
        TEAL, white, "HiraginoW6", 11
    ))
    story.append(Spacer(1, 5*mm))
    story.append(Paragraph("作成日: 2026-03-19 | 院内スタッフ向け配布資料", S["small"]))

    story.append(Spacer(1, 15*mm))

    # Three numbers box
    three_nums = [
        ["19%", "90%", "Day8"],
        ["看護必要度の基準値\n（これを超える）", "病床稼働率の目標\n（これを維持する）", "スコアが落ちる崖\n（ここから退院支援）"],
    ]
    t = Table(three_nums, colWidths=[55*mm, 55*mm, 55*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, 0), "HiraginoW6"),
        ("FONTSIZE", (0, 0), (-1, 0), 24),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 1), (-1, 1), "HiraginoW3"),
        ("FONTSIZE", (0, 1), (-1, 1), 9),
        ("TEXTCOLOR", (0, 1), (-1, 1), DARK_GRAY),
        ("BACKGROUND", (0, 1), (-1, 1), LIGHT_BG),
        ("GRID", (0, 0), (-1, -1), 1, white),
        ("TOPPADDING", (0, 0), (-1, -1), 5*mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5*mm),
    ]))
    story.append(t)
    story.append(Spacer(1, 10*mm))
    story.append(Paragraph(
        "<b>覚えてほしい3つの数字</b> ── 一人ひとりの「記録の正確さ」と「算定への意識」が基準達成の全てです。",
        S["body"]
    ))

    story.append(PageBreak())

    # ============================================================
    # PAGE 2: WHY THIS MATTERS
    # ============================================================
    story.append(Paragraph("なぜこれが全員の問題なのか", S["h1"]))

    # Flow diagram as table
    flow_ok = [["基準クリア", "→", "入院料の届出維持", "→", "病院収入の確保", "→", "十分な賞与"]]
    flow_ng = [["基準未達", "→", "入院料ダウン", "→", "年間数千万円の減収", "→", "賞与に直撃"]]

    t_ok = Table(flow_ok, colWidths=[28*mm, 8*mm, 35*mm, 8*mm, 35*mm, 8*mm, 28*mm])
    t_ok.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), TEAL),
        ("BACKGROUND", (2, 0), (2, 0), TEAL),
        ("BACKGROUND", (4, 0), (4, 0), TEAL),
        ("BACKGROUND", (6, 0), (6, 0), TEAL),
        ("TEXTCOLOR", (0, 0), (-1, -1), white),
        ("FONTNAME", (0, 0), (-1, -1), "HiraginoW6"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TEXTCOLOR", (1, 0), (1, 0), TEAL),
        ("TEXTCOLOR", (3, 0), (3, 0), TEAL),
        ("TEXTCOLOR", (5, 0), (5, 0), TEAL),
        ("BACKGROUND", (1, 0), (1, 0), white),
        ("BACKGROUND", (3, 0), (3, 0), white),
        ("BACKGROUND", (5, 0), (5, 0), white),
        ("TOPPADDING", (0, 0), (-1, -1), 3*mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3*mm),
    ]))
    story.append(t_ok)
    story.append(Spacer(1, 2*mm))

    t_ng = Table(flow_ng, colWidths=[28*mm, 8*mm, 35*mm, 8*mm, 35*mm, 8*mm, 28*mm])
    t_ng.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), CORAL),
        ("BACKGROUND", (2, 0), (2, 0), CORAL),
        ("BACKGROUND", (4, 0), (4, 0), CORAL),
        ("BACKGROUND", (6, 0), (6, 0), CORAL),
        ("TEXTCOLOR", (0, 0), (-1, -1), white),
        ("FONTNAME", (0, 0), (-1, -1), "HiraginoW6"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TEXTCOLOR", (1, 0), (1, 0), CORAL),
        ("TEXTCOLOR", (3, 0), (3, 0), CORAL),
        ("TEXTCOLOR", (5, 0), (5, 0), CORAL),
        ("BACKGROUND", (1, 0), (1, 0), white),
        ("BACKGROUND", (3, 0), (3, 0), white),
        ("BACKGROUND", (5, 0), (5, 0), white),
        ("TOPPADDING", (0, 0), (-1, -1), 3*mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3*mm),
    ]))
    story.append(t_ng)
    story.append(Spacer(1, 5*mm))

    story.append(Paragraph("2026年度改定の公式", S["h2"]))
    story.append(Paragraph(
        "指数 ＝ 該当患者割合 ＋ 救急搬送応需係数 ≧ <b>19%</b>（必要度I）",
        S["bold"]
    ))
    story.append(Paragraph(
        "当院の救急搬送応需係数 ＝ 220件 ÷ 94床 × 0.005 ＝ <b>1.2%</b>（わずか）",
        S["body"]
    ))
    story.append(colored_box(
        "救急係数はたった1.2%。残り17.8%をA項目+C項目で稼ぐしかない。",
        CORAL, white, "HiraginoW6", 10
    ))

    # ============================================================
    # DILEMMA
    # ============================================================
    story.append(Paragraph("最大の落とし穴：「稼働率」と「必要度」のジレンマ", S["h2"]))
    story.append(Paragraph(
        "該当患者割合 ＝ 該当日数（<b>分子</b>） ÷ 全在院日数（<b>分母</b>）",
        S["bold"]
    ))
    story.append(Paragraph(
        "在院日数を延ばすと稼働率は上がるが、分母が膨張して該当割合が下がる（<b>希釈効果</b>）",
        S["body"]
    ))

    dilemma_data = [
        ["平均在院日数", "稼働率", "該当割合", "判定"],
        ["16日（現状）", "85.1%", "25.0%", "必要度クリアだが稼働率不足"],
        ["17日（+1日）", "90.4%", "23.5%", "両方ギリギリ達成"],
        ["21日（+5日）", "100%", "19.0%", "必要度の崖っぷち"],
    ]
    story.append(make_table(
        dilemma_data[0], dilemma_data[1:],
        col_widths=[30*mm, 25*mm, 25*mm, 90*mm]
    ))
    story.append(Spacer(1, 3*mm))
    story.append(colored_box(
        "ベスト戦略：入院初期にスコアを稼ぎ、Day8以降は速やかに退院支援。在院日数17日前後が最適ゾーン。",
        NAVY, white, "HiraginoW6", 9
    ))

    story.append(PageBreak())

    # ============================================================
    # PAGE 3: WARD GAP
    # ============================================================
    story.append(Paragraph("病棟別ギャップと目標", S["h1"]))

    # 5F
    story.append(Paragraph("5階病棟（外科・整形 47床）── あと1.8%", S["h2"]))
    gap5_data = [
        ["項目", "現状", "救急係数込み", "基準", "ギャップ"],
        ["A項目", "13%", "", "", ""],
        ["C項目", "3%", "", "", ""],
        ["合計", "16%", "17.2%", "19%", "あと1.8%"],
    ]
    story.append(make_table(
        gap5_data[0], gap5_data[1:],
        col_widths=[25*mm, 25*mm, 35*mm, 25*mm, 60*mm],
        header_bg=TEAL
    ))
    story.append(Paragraph(
        "対策：CV挿入のC21確実計上 + 術後A項目の記録漏れゼロ → <b>到達可能</b>",
        S["body"]
    ))

    # 6F
    story.append(Paragraph("6階病棟（内科・ペイン 47床）── あと6.8%（最大課題）", S["h2"]))
    gap6_data = [
        ["項目", "現状", "救急係数込み", "基準", "ギャップ"],
        ["A項目", "10%", "", "", ""],
        ["C項目", "1%", "", "", ""],
        ["合計", "11%", "12.2%", "19%", "あと6.8%（深刻）"],
    ]
    t6 = make_table(
        gap6_data[0], gap6_data[1:],
        col_widths=[25*mm, 25*mm, 35*mm, 25*mm, 60*mm],
        header_bg=CORAL
    )
    story.append(t6)
    story.append(colored_box(
        "6Fの6.8%ギャップ克服が当院の最大の経営課題",
        CORAL, white, "HiraginoW6", 11
    ))

    story.append(PageBreak())

    # ============================================================
    # PAGE 4: PILLAR 1 - A ITEMS
    # ============================================================
    story.append(Paragraph("3つの柱：全員で取り組む具体策", S["h1"]))
    story.append(Paragraph("柱1: A項目で「2点以上」を毎日確保する", S["h2"]))
    story.append(Paragraph("「A2点以上」の達成パターン（覚えてほしい4つ）:", S["bold"]))

    pattern_data = [
        ["パターン", "内容", "点数", "対象場面"],
        ["最強パターン", "キシロカイン点滴→A6⑧", "3点（単独達成）", "ペイン科の日常"],
        ["重症パターン", "昇圧剤注射→A6⑦", "3点（単独達成）", "敗血症・ショック"],
        ["肺炎パターン", "酸素(A2=1)+注射薬3種(A3=1)", "2点（組合せ達成）", "内科の日常"],
        ["処置パターン", "酸素(A2=1)+創傷処置(A1=1)", "2点（組合せ達成）", "CV管理中"],
    ]
    story.append(make_table(
        pattern_data[0], pattern_data[1:],
        col_widths=[30*mm, 55*mm, 35*mm, 50*mm],
        header_bg=TEAL
    ))

    story.append(Spacer(1, 3*mm))
    story.append(Paragraph("肺炎患者のタイムライン例:", S["h3"]))

    timeline_data = [
        ["期間", "スコア構成", "該当判定"],
        ["Day 1-2", "救急搬送後 A7=2点", "自動的に該当"],
        ["Day 3-7", "注射薬3種(A3=1) + 酸素(A2=1) = 2点", "該当維持"],
        ["Day 8+", "注射終了 → 非該当へ転落", "退院支援加速！"],
    ]
    story.append(make_table(
        timeline_data[0], timeline_data[1:],
        col_widths=[25*mm, 85*mm, 60*mm]
    ))

    story.append(Spacer(1, 3*mm))
    story.append(Paragraph("注射薬3種のカウント注意:", S["h3"]))
    story.append(Paragraph("  OK: 抗菌薬、H2ブロッカー、制吐剤 等", S["body"]))
    story.append(Paragraph("  NG: アミノ酸・糖・電解質・ビタミン（2024年改定で除外済み）", S["alert"]))
    story.append(Paragraph("  上限: 7日間まで", S["body"]))

    story.append(PageBreak())

    # ============================================================
    # PAGE 5: PILLAR 2 - C ITEMS
    # ============================================================
    story.append(Paragraph("柱2: C項目を内科系処置でフル活用する", S["h2"]))
    story.append(colored_box(
        "2026年改定の最大の追い風：「A2点 又は C1点」で該当 → A項目が2点届かなくてもC項目1点あれば該当！",
        TEAL, white, "HiraginoW6", 10
    ))

    c_data = [
        ["区分", "該当日数", "主な処置（内科系）", "月間目標", "効果試算"],
        ["C21", "4日間", "CVカテーテル挿入、腰椎穿刺、\nERCP、内視鏡止血、CHDF/PMX", "8件", "+2.7%"],
        ["C22", "2日間", "気管支鏡/BAL、TEE、EBUS-TBNA", "5件", "+0.8%"],
        ["C23", "5日間", "PEG、PTCD、CART（胸腹水）、\n消化管ステント", "2件", "+0.8%"],
        ["合計", "", "", "15件", "+4.3%"],
    ]
    story.append(make_table(
        c_data[0], c_data[1:],
        col_widths=[18*mm, 20*mm, 70*mm, 22*mm, 22*mm],
        header_bg=TEAL
    ))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        "<b>C23は5日間カウント</b> = 少件数でも効果大。PEG・CARTは見逃し厳禁。",
        S["alert"]
    ))

    # ============================================================
    # PILLAR 3 - DISCHARGE
    # ============================================================
    story.append(Paragraph("柱3: Day8の崖を意識した戦略的退院支援", S["h2"]))
    story.append(Paragraph(
        "A・C項目が非該当になった瞬間に「治療」から「回復・在宅復帰」へフェーズを切り替え、分母の膨張を断ち切る。",
        S["body"]
    ))

    day8_data = [
        ["期間", "状態", "対応"],
        ["Day 1-7", "A2/C1該当（スコア確保期間）", "分子に貢献 → 記録漏れゼロ"],
        ["Day 8+", "非該当（分母だけ膨張）", "退院支援を加速！"],
    ]
    story.append(make_table(
        day8_data[0], day8_data[1:],
        col_widths=[25*mm, 65*mm, 80*mm]
    ))

    story.append(Spacer(1, 3*mm))
    story.append(Paragraph("看護部の3つのアクション:", S["h3"]))
    story.append(Paragraph("1. <b>入院Day3以内:</b> 退院困難因子スクリーニング（入退院支援加算1の必須要件）", S["bullet"]))
    story.append(Paragraph("2. <b>Day7まで:</b> 老健・サ高住への退院パスを確定", S["bullet"]))
    story.append(Paragraph("3. <b>Day8以降:</b> 在宅復帰率80%要件クリアのため速やかに退院調整", S["bullet"]))

    story.append(PageBreak())

    # ============================================================
    # PAGE 6: 6F SIMULATION + OCCUPANCY
    # ============================================================
    story.append(Paragraph("6Fの達成シミュレーション", S["h1"]))

    sim_data = [
        ["項目", "上乗せ", "累計"],
        ["現状", "", "11.0%"],
        ["+ 救急搬送応需係数", "+1.2%", "12.2%"],
        ["+ キシロカイン等A6（月15件x3日）", "+3.8%", "16.0%"],
        ["+ C項目（C21+C22+C23）", "+4.3%", "20.3%"],
        ["+ A2呼吸ケア等の記録改善", "+α", "20%超"],
    ]
    story.append(make_table(
        sim_data[0], sim_data[1:],
        col_widths=[80*mm, 35*mm, 35*mm],
        header_bg=TEAL
    ))
    story.append(colored_box(
        "基準19%クリア！ 前提：全科の協力 + 記録漏れゼロ",
        TEAL, white, "HiraginoW6", 11
    ))

    story.append(Spacer(1, 5*mm))
    story.append(Paragraph("稼働率90%を同時に達成する方法", S["h1"]))
    story.append(Paragraph(
        "「ベッドを埋める」思考から「<b>数式をコントロールする</b>」思考へ",
        S["bold"]
    ))

    story.append(Paragraph("収益のスイートスポット = 「緊急入院 x 手術なし」", S["h2"]))
    sweet_data = [
        ["", "緊急入院", "予定入院"],
        ["手術なし", "入院料最高値（3,367点）", "-"],
        ["手術あり", "入院料1-1（3,367点）", "入院料1-2（3,267点）"],
    ]
    story.append(make_table(
        sweet_data[0], sweet_data[1:],
        col_widths=[30*mm, 70*mm, 70*mm],
        header_bg=NAVY
    ))
    story.append(Paragraph(
        "肺炎・尿路感染症・心不全等の<b>内科系高齢救急</b>が最も有利な患者ミックス",
        S["body"]
    ))

    story.append(Paragraph("稼働率を上げる正しい方法:", S["h3"]))
    story.append(Paragraph("1. <b>救急搬送受入の拡大</b> → 稼働率UP + 救急係数UP + 入院料最高値の一石三鳥", S["bullet"]))
    story.append(Paragraph("2. <b>介護施設との協力医療機関協定</b> → 安定した上り搬送ルート確保", S["bullet"]))
    story.append(Paragraph("3. <b>在院日数は17日前後を目標</b> → 稼働率90%と必要度19%の両立ゾーン", S["bullet"]))

    story.append(PageBreak())

    # ============================================================
    # PAGE 7: DAILY CHECKLIST
    # ============================================================
    story.append(Paragraph("毎日のチェックリスト（算定漏れ防止）", S["h1"]))

    story.append(Paragraph("A項目（毎日確認）", S["h2"]))
    a_checks = [
        ["チェック", "項目", "点数"],
        ["□", "キシロカイン等の点滴 → A6⑧「抗不整脈剤」", "3点"],
        ["□", "昇圧剤（ノルアド等）→ A6⑦「昇圧剤」", "3点"],
        ["□", "抗がん剤注射 → A6① / 麻薬注射 → A6③", "3点"],
        ["□", "酸素投与中 → A2「呼吸ケア」（1L/分でも、HFNCでも）", "1点"],
        ["□", "NPPV/BiPAP → A2「呼吸ケア」（夜間のみでも）", "1点"],
        ["□", "注射薬剤3種類以上 → A3（栄養系は除外・7日上限）", "1点"],
        ["□", "輸血・血液製剤 → A5（見落とし注意）", "2点"],
        ["□", "シリンジポンプ管理 → A4", "1点"],
    ]
    story.append(make_table(
        a_checks[0], a_checks[1:],
        col_widths=[18*mm, 115*mm, 18*mm],
        header_bg=TEAL
    ))

    story.append(Spacer(1, 3*mm))
    story.append(Paragraph("C項目（処置・検査実施時）", S["h2"]))
    c_checks = [
        ["チェック", "処置", "区分・日数"],
        ["□", "CV挿入", "C21（4日間）"],
        ["□", "腰椎穿刺・脳脊髄腔注射", "C21（4日間）"],
        ["□", "ERCP・内視鏡止血", "C21（4日間）"],
        ["□", "気管支鏡・TEE・EBUS", "C22（2日間）"],
        ["□", "PEG・PTCD・CART", "C23（5日間）← 最長！"],
    ]
    story.append(make_table(
        c_checks[0], c_checks[1:],
        col_widths=[18*mm, 85*mm, 48*mm],
        header_bg=CORAL
    ))

    story.append(PageBreak())

    # ============================================================
    # PAGE 8: ROLES + ACTION PLAN
    # ============================================================
    story.append(Paragraph("役割分担：全員が「数式のどこ」に貢献するか", S["h1"]))

    role_data = [
        ["職種", "担当する数式の部分", "具体的にやること"],
        ["医師", "分子\n（A/C項目のスコア）", "処置時にC項目該当を意識\nキシロカイン等A項目の活用\n注射3種のプロトコル設計"],
        ["看護師", "分子（記録）+\n分母（退院支援）", "毎日の必要度評価を正確に記録\nDay3退院困難因子スクリーニング\nDay8以降の退院加速"],
        ["医事課", "全体の数式管理", "レセプトコード整合チェック\n週次の該当割合集計\nコーディング最適化"],
        ["管理者", "モニタリング", "週次で病棟別数値確認\n目標未達時の即時アクション"],
        ["副院長", "戦略統括", "全体最適化\n介護施設連携・救急受入拡大の推進"],
    ]
    story.append(make_table(
        role_data[0], role_data[1:],
        col_widths=[22*mm, 42*mm, 100*mm],
        header_bg=NAVY
    ))

    story.append(Spacer(1, 5*mm))
    story.append(Paragraph("アクションプラン", S["h1"]))

    # Phase boxes
    phases = [
        ("Phase 1: 準備期（2026年4-5月）", TEAL, [
            "全体研修: 新基準「A2点以上 又は C1点以上」の周知",
            "電子カルテテンプレートにA/C項目チェックを組み込み",
            "キシロカイン算定フローをペイン科と確立",
            "介護施設との協力医療機関協定の締結推進",
        ]),
        ("Phase 2: 導入期（2026年6-8月）", NAVY, [
            "毎週の該当患者割合モニタリング（病棟別・項目別）",
            "各科カンファでC項目取得状況を共有",
            "算定漏れの原因分析 → PDCAサイクル",
            "消防ホットライン運用開始（救急搬送受入拡大）",
        ]),
        ("Phase 3: 定着期（2026年9月〜）", CORAL, [
            "月次レビュー体制に移行",
            "ダッシュボードによるリアルタイム進捗可視化",
            "5F⇔6Fのベストプラクティス横展開",
            "在院日数17日前後の最適ゾーン維持",
        ]),
    ]

    for phase_title, color, items in phases:
        story.append(colored_box(phase_title, color, white, "HiraginoW6", 10))
        for item in items:
            story.append(Paragraph(f"  □  {item}", S["body"]))
        story.append(Spacer(1, 2*mm))

    # ============================================================
    # FINAL MESSAGE
    # ============================================================
    story.append(Spacer(1, 10*mm))
    story.append(HRFlowable(width="100%", thickness=1, color=NAVY))
    story.append(Spacer(1, 5*mm))
    story.append(Paragraph(
        "全スタッフの皆さんへ",
        S["h2"]
    ))
    story.append(Paragraph(
        "救急係数に頼れない当院では、一人ひとりの「記録の正確さ」と「算定への意識」が基準達成の全てです。",
        S["bold"]
    ))
    story.append(Paragraph(
        "<b>全員で協力して2026年度改定を乗り越え、十分な賞与を確保しましょう。</b>",
        S["bold"]
    ))

    # Build
    doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)
    print(f"PDF generated: {output_path}")
    return output_path


if __name__ == "__main__":
    build_pdf()
