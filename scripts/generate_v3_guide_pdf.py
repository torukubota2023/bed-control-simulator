#!/usr/bin/env python3
"""hospital_app_development_guide_v3.md → PDF 変換スクリプト

reportlab + 組み込み CID 日本語フォントで、
追加インストール不要の日本語 PDF を生成する。

出力: docs/admin/hospital_app_development_guide_v3.pdf
"""
import os
import re
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether, ListFlowable, ListItem, Preformatted,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

# ---------------------------------------------------------------------------
# パス
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
INPUT_PATH = os.path.join(PROJECT_DIR, "docs", "admin", "hospital_app_development_guide_v3.md")
OUTPUT_PATH = os.path.join(PROJECT_DIR, "docs", "admin", "hospital_app_development_guide_v3.pdf")

# ---------------------------------------------------------------------------
# 日本語フォント（追加インストール不要の組み込み CID）
# ---------------------------------------------------------------------------
pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
pdfmetrics.registerFont(UnicodeCIDFont("HeiseiMin-W3"))
JP_FONT = "HeiseiKakuGo-W5"
JP_FONT_MIN = "HeiseiMin-W3"

# ---------------------------------------------------------------------------
# スタイル
# ---------------------------------------------------------------------------
title_style = ParagraphStyle(
    "Title", fontName=JP_FONT, fontSize=22, leading=28,
    spaceBefore=12, spaceAfter=18, alignment=1,
    textColor=colors.HexColor("#1E3A8A"),
)
subtitle_style = ParagraphStyle(
    "Subtitle", fontName=JP_FONT_MIN, fontSize=13, leading=18,
    spaceAfter=8, alignment=1, textColor=colors.HexColor("#475569"),
)
meta_style = ParagraphStyle(
    "Meta", fontName=JP_FONT_MIN, fontSize=10, leading=14,
    spaceAfter=4, alignment=1, textColor=colors.HexColor("#64748B"),
)

part_style = ParagraphStyle(
    "Part", fontName=JP_FONT, fontSize=18, leading=24,
    spaceBefore=20, spaceAfter=10, alignment=1,
    textColor=colors.white, backColor=colors.HexColor("#1E40AF"),
    borderPadding=8,
)

h1_style = ParagraphStyle(
    "H1", fontName=JP_FONT, fontSize=16, leading=22,
    spaceBefore=18, spaceAfter=10,
    textColor=colors.HexColor("#1E40AF"),
    borderColor=colors.HexColor("#3B82F6"),
    borderWidth=0, borderPadding=4,
    leftIndent=0,
)

h2_style = ParagraphStyle(
    "H2", fontName=JP_FONT, fontSize=13, leading=18,
    spaceBefore=12, spaceAfter=6,
    textColor=colors.HexColor("#3B82F6"),
)

h3_style = ParagraphStyle(
    "H3", fontName=JP_FONT, fontSize=11, leading=15,
    spaceBefore=8, spaceAfter=4,
    textColor=colors.HexColor("#475569"),
)

body_style = ParagraphStyle(
    "Body", fontName=JP_FONT_MIN, fontSize=9.5, leading=14,
    spaceAfter=4, firstLineIndent=0,
)

body_indent_style = ParagraphStyle(
    "BodyIndent", fontName=JP_FONT_MIN, fontSize=9.5, leading=14,
    spaceAfter=3, leftIndent=12,
)

bullet_style = ParagraphStyle(
    "Bullet", fontName=JP_FONT_MIN, fontSize=9.5, leading=14,
    spaceAfter=3, leftIndent=18, bulletIndent=6,
)

quote_style = ParagraphStyle(
    "Quote", fontName=JP_FONT_MIN, fontSize=9, leading=13,
    spaceBefore=4, spaceAfter=4,
    leftIndent=14, rightIndent=8,
    textColor=colors.HexColor("#475569"),
    borderColor=colors.HexColor("#94A3B8"),
    borderWidth=0, borderPadding=4,
    backColor=colors.HexColor("#F1F5F9"),
)

code_style = ParagraphStyle(
    "Code", fontName="Courier", fontSize=8.5, leading=11,
    spaceBefore=4, spaceAfter=4,
    leftIndent=10, rightIndent=10,
    backColor=colors.HexColor("#F1F5F9"),
    borderPadding=4, borderColor=colors.HexColor("#CBD5E1"),
    borderWidth=0.5,
)

caption_style = ParagraphStyle(
    "Caption", fontName=JP_FONT_MIN, fontSize=8, leading=11,
    spaceAfter=3, textColor=colors.HexColor("#94A3B8"), alignment=1,
)


# ---------------------------------------------------------------------------
# Markdown インライン → reportlab マークアップ変換
# ---------------------------------------------------------------------------

def md_inline_to_rl(text: str) -> str:
    """Markdown inline 記法を reportlab Paragraph 用 XML に変換。"""
    if not text:
        return ""
    # XML 特殊文字をエスケープ
    text = (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))
    # 太字: **xxx**
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    # 斜体: *xxx*（ただし bold と被らない）
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)
    # インラインコード: `xxx`
    text = re.sub(r"`([^`]+)`", r'<font name="Courier">\1</font>', text)
    # リンク: [text](url) → text のみ
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text


# ---------------------------------------------------------------------------
# Markdown → flowables
# ---------------------------------------------------------------------------

def parse_markdown(md_text: str):
    """Markdown を reportlab flowables のリストに変換する。"""
    flowables = []
    lines = md_text.split("\n")
    i = 0

    in_code = False
    code_buffer = []
    in_table = False
    table_buffer = []

    def flush_code():
        nonlocal code_buffer
        if code_buffer:
            text = "\n".join(code_buffer).rstrip()
            # 長すぎる場合はスキップ（PDFが破綻するので）
            if len(text) < 4000:
                try:
                    flowables.append(Preformatted(text, code_style))
                except Exception:
                    pass
            code_buffer = []

    def flush_table():
        nonlocal table_buffer
        if len(table_buffer) >= 2:
            try:
                # ヘッダ + 行（区切り行スキップ）
                rows = []
                for idx, row in enumerate(table_buffer):
                    if idx == 1 and re.match(r"^[\s|:\-]+$", row):
                        continue
                    cells = [c.strip() for c in row.strip("|").split("|")]
                    rows.append(cells)
                if not rows:
                    table_buffer = []
                    return
                # セルを Paragraph に変換
                cell_p_style = ParagraphStyle(
                    "TblCell", fontName=JP_FONT_MIN, fontSize=8, leading=11,
                )
                cell_h_style = ParagraphStyle(
                    "TblHdr", fontName=JP_FONT, fontSize=8.5, leading=11,
                    textColor=colors.white, alignment=1,
                )
                wrapped = []
                for ridx, row in enumerate(rows):
                    wrapped_row = []
                    for cell in row:
                        text = md_inline_to_rl(cell)
                        if ridx == 0:
                            wrapped_row.append(Paragraph(text, cell_h_style))
                        else:
                            wrapped_row.append(Paragraph(text, cell_p_style))
                    wrapped.append(wrapped_row)
                # 列幅を均等に
                ncols = len(wrapped[0]) if wrapped else 1
                avail = 174 * mm
                col_widths = [avail / ncols] * ncols
                t = Table(wrapped, colWidths=col_widths, repeatRows=1)
                t.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E40AF")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#94A3B8")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                     [colors.white, colors.HexColor("#F8FAFC")]),
                ]))
                flowables.append(t)
                flowables.append(Spacer(1, 6))
            except Exception as e:
                # テーブル構文が壊れていたら諦めて段落として出す
                for row in table_buffer:
                    flowables.append(Paragraph(md_inline_to_rl(row), body_style))
            table_buffer = []

    while i < len(lines):
        line = lines[i]
        rstripped = line.rstrip()

        # コードブロック
        if rstripped.startswith("```"):
            if in_code:
                flush_code()
                in_code = False
            else:
                if in_table:
                    flush_table()
                    in_table = False
                in_code = True
            i += 1
            continue
        if in_code:
            code_buffer.append(line)
            i += 1
            continue

        # テーブル検出
        if "|" in rstripped and rstripped.lstrip().startswith("|"):
            if not in_table:
                in_table = True
                table_buffer = []
            table_buffer.append(rstripped)
            i += 1
            continue
        else:
            if in_table:
                flush_table()
                in_table = False

        # 空行
        if not rstripped:
            flowables.append(Spacer(1, 4))
            i += 1
            continue

        # 見出し
        if rstripped.startswith("#### "):
            txt = md_inline_to_rl(rstripped[5:].strip())
            flowables.append(Paragraph(txt, h3_style))
            i += 1
            continue
        if rstripped.startswith("### "):
            txt = md_inline_to_rl(rstripped[4:].strip())
            flowables.append(Paragraph(txt, h3_style))
            i += 1
            continue
        if rstripped.startswith("## "):
            txt = md_inline_to_rl(rstripped[3:].strip())
            flowables.append(Paragraph(txt, h2_style))
            i += 1
            continue
        if rstripped.startswith("# "):
            txt = rstripped[2:].strip()
            # 第N部 / 付録 / おわりに 系は part_style 扱い
            if (txt.startswith("第") and "部" in txt[:5]) or txt == "目次" or txt.startswith("おわりに"):
                flowables.append(PageBreak())
                flowables.append(Paragraph(md_inline_to_rl(txt), part_style))
            else:
                # 第N章 系は h1_style + ページブレイク
                if txt.startswith("第") and "章" in txt[:5]:
                    flowables.append(PageBreak())
                flowables.append(Paragraph(md_inline_to_rl(txt), h1_style))
            i += 1
            continue

        # 区切り線
        if rstripped == "---" or rstripped == "***":
            flowables.append(Spacer(1, 6))
            i += 1
            continue

        # 引用
        if rstripped.startswith("> "):
            quote_lines = []
            while i < len(lines) and lines[i].rstrip().startswith(">"):
                quote_lines.append(lines[i].rstrip().lstrip("> ").lstrip(">"))
                i += 1
            quote_text = "<br/>".join(md_inline_to_rl(l) for l in quote_lines if l.strip())
            if quote_text:
                flowables.append(Paragraph(quote_text, quote_style))
            continue

        # 番号付きリスト
        m_ol = re.match(r"^(\s*)(\d+)\.\s+(.*)$", line)
        if m_ol:
            num = m_ol.group(2)
            content = md_inline_to_rl(m_ol.group(3))
            flowables.append(Paragraph(f"{num}. {content}", bullet_style))
            i += 1
            continue

        # 箇条書き
        m_ul = re.match(r"^(\s*)[-*•]\s+(.*)$", line)
        if m_ul:
            content = md_inline_to_rl(m_ul.group(2))
            flowables.append(Paragraph(f"• {content}", bullet_style))
            i += 1
            continue

        # 通常段落
        text = md_inline_to_rl(rstripped)
        try:
            flowables.append(Paragraph(text, body_style))
        except Exception:
            # パラグラフ作成エラーはスキップ
            pass
        i += 1

    # 終了処理
    if in_code:
        flush_code()
    if in_table:
        flush_table()

    return flowables


# ---------------------------------------------------------------------------
# 表紙
# ---------------------------------------------------------------------------

def build_cover():
    out = []
    out.append(Spacer(1, 60))
    out.append(Paragraph("院内アプリ開発・導入<br/>実践プレイブック", title_style))
    out.append(Spacer(1, 12))
    out.append(Paragraph("v3.0（統合版）", subtitle_style))
    out.append(Spacer(1, 24))
    out.append(Paragraph(
        "AI時代の病院DX：プログラミング不要！<br/>"
        "現場スタッフのためのアプリ作成ガイド",
        subtitle_style,
    ))
    out.append(Spacer(1, 80))
    out.append(Paragraph("対象: パソコンの基本操作（Excel・メール等）が<br/>"
                        "できる病院スタッフの方", meta_style))
    out.append(Paragraph("前提知識: プログラミングの知識は一切不要", meta_style))
    out.append(Spacer(1, 30))
    out.append(Paragraph("作成日: 2026年4月15日", meta_style))
    out.append(Paragraph("バージョン: 3.0（統合版）", meta_style))
    out.append(Paragraph("おもろまちメディカルセンター", meta_style))
    out.append(Paragraph("副院長 久保田 徹", meta_style))
    out.append(PageBreak())
    return out


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main():
    print(f"読み込み: {INPUT_PATH}")
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        md_text = f.read()
    print(f"  Markdown {len(md_text):,} chars / {md_text.count(chr(10)):,} lines")

    flowables = build_cover()
    flowables.extend(parse_markdown(md_text))

    print(f"  Flowables: {len(flowables):,}")

    doc = SimpleDocTemplate(
        OUTPUT_PATH,
        pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title="院内アプリ開発・導入 実践プレイブック v3.0",
        author="副院長 久保田 徹（おもろまちメディカルセンター）",
    )

    print("PDF 生成中...")
    doc.build(flowables)

    size = os.path.getsize(OUTPUT_PATH)
    print(f"完了: {OUTPUT_PATH}")
    print(f"  ファイルサイズ: {size:,} bytes ({size/1024/1024:.2f} MB)")


if __name__ == "__main__":
    main()
