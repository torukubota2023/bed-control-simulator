"""医師別 病棟貢献度 KPI 解析 — 理事会・運営会議 プレゼン PPTX 生成（粗利ベース 抜本改訂版）.

副院長指示 (2026-05-04):
  - 旧版で誤った数値（24000/13200/6400）を使用 → 抜本改訂
  - 正しくは粗利ベース（B 32,500 ＞ C 31,000 ＞ A 26,500 円/床日）
  - 理事会で「短期回転＝経営最適」という誤った認識を修正する設計
"""
from __future__ import annotations

import argparse
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

from generate_doctor_kpi_charts import (
    OUT_DIR as CHART_DIR,
    PROFIT_A, PROFIT_B, PROFIT_C,
    REV_A, REV_B, REV_C,
    COST_A, COST_B, COST_C,
    load_and_compute,
    make_anonymous_map,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
JP_FONT = "Hiragino Mincho ProN"

C_TITLE = RGBColor(0x1F, 0x29, 0x37)
C_ACCENT = RGBColor(0x25, 0x63, 0xEB)
C_DANGER = RGBColor(0xDC, 0x26, 0x26)
C_OK = RGBColor(0x10, 0xB9, 0x81)
C_GOLD = RGBColor(0xD9, 0x77, 0x06)
C_MUTED = RGBColor(0x6B, 0x72, 0x80)
C_FAINT = RGBColor(0x9C, 0xA3, 0xAF)
C_BG_BLUE = RGBColor(0xEF, 0xF6, 0xFF)
C_BG_RED = RGBColor(0xFE, 0xF2, 0xF2)
C_BG_GREEN = RGBColor(0xEC, 0xFD, 0xF5)
C_BG_GOLD = RGBColor(0xFE, 0xF3, 0xC7)


def _set_font(run, size_pt=18, bold=False, color=None):
    run.font.name = JP_FONT
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color


def add_textbox(slide, left, top, width, height, text, size=18, bold=False,
                 color=None, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = Pt(2); tf.margin_right = Pt(2)
    tf.margin_top = Pt(2); tf.margin_bottom = Pt(2)
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    _set_font(run, size_pt=size, bold=bold, color=color)
    return tb


def add_multi_para_textbox(slide, left, top, width, height, lines, default_size=16,
                           color=None, align=PP_ALIGN.LEFT):
    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = True
    for i, line in enumerate(lines):
        if isinstance(line, tuple):
            text, size, bold = line + (False,) * (3 - len(line))
        else:
            text, size, bold = line, default_size, False
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        run = p.add_run()
        run.text = text
        _set_font(run, size_pt=size, bold=bold, color=color or C_TITLE)
    return tb


def add_bg_rect(slide, left, top, width, height, fill_color):
    from pptx.enum.shapes import MSO_SHAPE
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    shape.line.fill.background()
    return shape


def add_image_to_slide(slide, image_path, left, top, width, height=None):
    if height:
        slide.shapes.add_picture(str(image_path), left, top, width=width, height=height)
    else:
        slide.shapes.add_picture(str(image_path), left, top, width=width)


def build(mode: str):
    df, agg, ward_total_days, total_hospital_days = load_and_compute()
    anon_map = make_anonymous_map(agg)
    label_map = (lambda x: x) if mode == 'named' else (lambda x: anon_map.get(x, x))
    title_audience = "理事会" if mode == 'named' else "運営会議"

    okuk_label = label_map('OKUK')
    sub_5f = agg[agg['5F_寄与率'] > 0].sort_values('5F_寄与率', ascending=False)
    sub_6f = agg[agg['6F_寄与率'] > 0].sort_values('6F_寄与率', ascending=False)
    top3_6f = sub_6f.head(3)
    top3_share_6f = top3_6f['6F_寄与率'].sum()
    top3_profit = agg.sort_values('総粗利', ascending=False).head(3)
    top3_profit_share = top3_profit['総粗利'].sum() / agg['総粗利'].sum() * 100
    top3_unit = agg.sort_values('ベッド粗利単価', ascending=False).head(3)

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    SW, SH = prs.slide_width, prs.slide_height
    blank_layout = prs.slide_layouts[6]

    # ====================================================================
    # Slide 1: 表紙
    # ====================================================================
    s = prs.slides.add_slide(blank_layout)
    add_bg_rect(s, 0, 0, SW, SH, RGBColor(0xF9, 0xFA, 0xFB))
    add_textbox(s, Inches(1), Inches(1.7), Inches(11.5), Inches(1.2),
                "医師別 病棟貢献度 KPI 解析",
                size=42, bold=True, color=C_TITLE, align=PP_ALIGN.CENTER)
    add_textbox(s, Inches(1), Inches(2.9), Inches(11.5), Inches(0.7),
                f"{title_audience}説明資料",
                size=26, bold=True, color=C_ACCENT, align=PP_ALIGN.CENTER)
    add_textbox(s, Inches(0.5), Inches(3.9), Inches(12.3), Inches(0.7),
                "「短期回転 ＝ 経営最適」は誤り：B 群（回復期）の中心管理が",
                size=18, bold=True, color=C_DANGER, align=PP_ALIGN.CENTER)
    add_textbox(s, Inches(0.5), Inches(4.4), Inches(12.3), Inches(0.7),
                "運営貢献を最大化する",
                size=18, bold=True, color=C_DANGER, align=PP_ALIGN.CENTER)
    add_textbox(s, Inches(1), Inches(5.5), Inches(11.5), Inches(0.6),
                "おもろまちメディカルセンター",
                size=18, color=C_TITLE, align=PP_ALIGN.CENTER)
    add_textbox(s, Inches(1), Inches(6.0), Inches(11.5), Inches(0.5),
                "副院長 久保田 透",
                size=14, color=C_TITLE, align=PP_ALIGN.CENTER)
    add_textbox(s, Inches(1), Inches(6.5), Inches(11.5), Inches(0.5),
                "2026 年 5 月 4 日 / Rev. 2（粗利ベース 抜本改訂版）",
                size=12, color=C_FAINT, align=PP_ALIGN.CENTER)
    if mode == 'anonymous':
        add_textbox(s, Inches(1), Inches(6.95), Inches(11.5), Inches(0.4),
                    "※ 個人名はすべて A 医師, B 医師 ... と匿名化",
                    size=11, color=C_DANGER, align=PP_ALIGN.CENTER)

    # ====================================================================
    # Slide 2: 結論
    # ====================================================================
    s = prs.slides.add_slide(blank_layout)
    add_bg_rect(s, 0, 0, SW, Inches(1.0), C_BG_GOLD)
    add_textbox(s, Inches(0.5), Inches(0.2), Inches(12.3), Inches(0.7),
                "本日の結論", size=32, bold=True, color=C_TITLE)

    conclusions = [
        ("①  ベッド粗利単価の正しい順位は B（32,500）＞ C（31,000）＞ A（26,500）", 22, True),
        ("    → 「短期回転＝経営貢献大」は誤り。コストを差し引いた粗利では B 群最高", 15, False),
        ("", 8, False),
        ("②  長期入院型（B + C 群偏重）の医師ほど粗利単価が高い", 22, True),
        ("    → 上位 3 医師はいずれも B + C 群比率 80% 超の長期管理型", 15, False),
        ("", 8, False),
        ("③  稼働率寄与率と年間粗利は相関 r = 0.96 で極めて強く連動", 22, True),
        ("    → 主指標を「稼働率寄与率（量）」+「ベッド粗利単価（質）」の 2 軸に", 15, False),
        ("", 8, False),
        (f"④  5F 病棟は {okuk_label} 1 名で 23.3% を占有 — 構造的リスク", 22, True),
        ("    → 5F 主治医増員 + バックアップ体制整備を提言", 15, False),
        ("", 8, False),
        ("⑤  運営方針: 「短期回転推進」ではなく「適切な在院期間管理」", 22, True),
        ("    → 適応のある患者を 6〜14 日（B 群）で安定管理する文化を強化", 15, False),
    ]
    add_multi_para_textbox(s, Inches(0.7), Inches(1.3), Inches(12.0), Inches(6.0), conclusions)

    # ====================================================================
    # Slide 3: 重要な認識転換（誤った認識 vs 正しい認識）
    # ====================================================================
    s = prs.slides.add_slide(blank_layout)
    add_bg_rect(s, 0, 0, SW, Inches(1.0), C_BG_RED)
    add_textbox(s, Inches(0.5), Inches(0.2), Inches(12.3), Inches(0.7),
                "重要: 「報酬」ではなく「粗利」で評価する",
                size=28, bold=True, color=C_DANGER)
    add_image_to_slide(s, CHART_DIR / f"06_misconception_{mode}.png",
                       Inches(0.5), Inches(1.2), Inches(12.3))
    add_bg_rect(s, Inches(0.7), Inches(6.5), Inches(12.0), Inches(0.8), C_BG_GREEN)
    add_textbox(s, Inches(0.9), Inches(6.65), Inches(11.6), Inches(0.5),
                "✅ 正しい認識: コストを差し引くと B 群（回復期）が最高、A 群（急性期）が最低",
                size=16, bold=True, color=C_OK)

    # ====================================================================
    # Slide 4: なぜこの分析が必要か
    # ====================================================================
    s = prs.slides.add_slide(blank_layout)
    add_bg_rect(s, 0, 0, SW, Inches(1.0), C_BG_BLUE)
    add_textbox(s, Inches(0.5), Inches(0.2), Inches(12.3), Inches(0.7),
                "なぜ「医師別 病棟貢献度」を見える化するのか", size=28, bold=True, color=C_TITLE)

    body = [
        ("● 病棟稼働率は施設基準（地域包括医療病棟は 90%）達成のための最重要指標", 18, True),
        ("", 8, False),
        ("● 実態は各主治医の入院・在院・退院判断の総和が病棟稼働率を作る", 18, False),
        ("", 16, False),
        ("本資料の 3 つの問い:", 20, True),
        ("    1. 各医師が病棟稼働率をどれだけ支えているか？", 17, False),
        ("    2. それは病院収益（粗利＝運営貢献額）にどう結びついているか？", 17, False),
        ("    3. 構造的なリスク（特定医師への依存など）はないか？", 17, False),
    ]
    add_multi_para_textbox(s, Inches(0.7), Inches(1.4), Inches(12.0), Inches(5.0), body)
    add_bg_rect(s, Inches(0.7), Inches(6.4), Inches(12.0), Inches(0.8), C_BG_RED)
    add_textbox(s, Inches(0.9), Inches(6.5), Inches(11.6), Inches(0.6),
                "📌 大前提: 個別医師の評価ではなく、病棟運営の構造把握を目的とします",
                size=14, bold=True, color=C_DANGER)

    # ====================================================================
    # Slide 5: データ概要
    # ====================================================================
    s = prs.slides.add_slide(blank_layout)
    add_bg_rect(s, 0, 0, SW, Inches(1.0), C_BG_BLUE)
    add_textbox(s, Inches(0.5), Inches(0.2), Inches(12.3), Inches(0.7),
                "データ概要", size=32, bold=True, color=C_TITLE)

    box_y = Inches(1.5); box_h = Inches(2.5); box_w = Inches(2.9); box_gap = Inches(0.2)
    box_x_start = Inches(0.5)
    boxes = [
        ("対象期間", "13 ヶ月", "2025-04 〜 2026-04"),
        ("入院件数", "1,960 件", "事務提供 CSV"),
        ("対象医師", f"{len(agg)} 名", "件数 10 以上"),
        ("総延日数", f"{int(agg['総延日数'].sum()):,}", "床日（5F + 6F）"),
    ]
    for i, (label, value, sub) in enumerate(boxes):
        x = box_x_start + (box_w + box_gap) * i
        add_bg_rect(s, x, box_y, box_w, box_h, C_BG_BLUE)
        add_textbox(s, x, box_y + Inches(0.2), box_w, Inches(0.5), label,
                    size=14, color=C_MUTED, align=PP_ALIGN.CENTER)
        add_textbox(s, x, box_y + Inches(0.7), box_w, Inches(1.2), value,
                    size=32, bold=True, color=C_ACCENT, align=PP_ALIGN.CENTER)
        add_textbox(s, x, box_y + Inches(1.95), box_w, Inches(0.5), sub,
                    size=12, color=C_MUTED, align=PP_ALIGN.CENTER)

    add_textbox(s, Inches(0.5), Inches(4.5), Inches(12.3), Inches(0.5),
                "病棟構成", size=18, bold=True, color=C_TITLE)
    add_textbox(s, Inches(0.7), Inches(5.0), Inches(12.0), Inches(0.6),
                f"5F 病棟 47 床（年間稼働率 {ward_total_days['5F']/(47*365)*100:.1f}%）  /  "
                f"6F 病棟 47 床（年間稼働率 {ward_total_days['6F']/(47*365)*100:.1f}%）",
                size=16, color=C_TITLE)

    add_bg_rect(s, Inches(0.7), Inches(5.9), Inches(12.0), Inches(1.4), C_BG_RED)
    add_multi_para_textbox(s, Inches(0.9), Inches(6.0), Inches(11.6), Inches(1.2), [
        ("⚠️ 本解析の限界（Stage 1）", 14, True),
        ("フェーズ別粗利のみで概算しています。リハ加算・処置加算・手術料は概算に含まず。",
         12, False),
        ("次フェーズで事務から追加データを取得し精緻化します。", 12, False),
    ], color=C_DANGER)

    # ====================================================================
    # Slide 6: フェーズ別単価構造（核心）
    # ====================================================================
    s = prs.slides.add_slide(blank_layout)
    add_bg_rect(s, 0, 0, SW, Inches(1.0), C_BG_BLUE)
    add_textbox(s, Inches(0.5), Inches(0.2), Inches(12.3), Inches(0.7),
                "フェーズ別 単価構造 — 報酬・変動費・粗利",
                size=28, bold=True, color=C_TITLE)
    add_textbox(s, Inches(0.7), Inches(1.2), Inches(12.0), Inches(0.5),
                "アプリ実装の 2026 年度プリセット（入院料 1・イ/ロ/ハ加重平均）に基づく数値:",
                size=14, color=C_MUTED)

    # 3 カラム表
    phase_y = Inches(1.9); phase_h = Inches(3.6); phase_w = Inches(3.9); phase_gap = Inches(0.3)
    phase_x_start = Inches(0.5)
    phases = [
        ("A 群（急性期）", "1 〜 5 日",
         f"報酬 {REV_A:,}", f"変動費 {COST_A:,}", f"粗利 {PROFIT_A:,}",
         "3 位", RGBColor(0xFE, 0xCA, 0xCA), C_DANGER),
        ("B 群（回復期）", "6 〜 14 日",
         f"報酬 {REV_B:,}", f"変動費 {COST_B:,}", f"粗利 {PROFIT_B:,}",
         "★ 1 位", RGBColor(0xBB, 0xF7, 0xD0), C_OK),
        ("C 群（退院準備期）", "15 日以降",
         f"報酬 {REV_C:,}", f"変動費 {COST_C:,}", f"粗利 {PROFIT_C:,}",
         "2 位", RGBColor(0xFD, 0xE0, 0x8A), C_GOLD),
    ]
    for i, (label, days, rev, cost, profit, rank, color, rank_color) in enumerate(phases):
        x = phase_x_start + (phase_w + phase_gap) * i
        add_bg_rect(s, x, phase_y, phase_w, phase_h, color)
        add_textbox(s, x, phase_y + Inches(0.15), phase_w, Inches(0.5), label,
                    size=20, bold=True, color=C_TITLE, align=PP_ALIGN.CENTER)
        add_textbox(s, x, phase_y + Inches(0.7), phase_w, Inches(0.4), days,
                    size=14, color=C_MUTED, align=PP_ALIGN.CENTER)
        add_textbox(s, x, phase_y + Inches(1.2), phase_w, Inches(0.5), rev,
                    size=16, color=C_TITLE, align=PP_ALIGN.CENTER)
        add_textbox(s, x, phase_y + Inches(1.7), phase_w, Inches(0.5), "− " + cost,
                    size=16, color=C_DANGER, align=PP_ALIGN.CENTER)
        add_textbox(s, x, phase_y + Inches(2.25), phase_w, Inches(0.6), "= " + profit,
                    size=22, bold=True, color=C_ACCENT, align=PP_ALIGN.CENTER)
        add_textbox(s, x, phase_y + Inches(2.95), phase_w, Inches(0.6), rank,
                    size=22, bold=True, color=rank_color, align=PP_ALIGN.CENTER)

    add_bg_rect(s, Inches(0.7), Inches(5.7), Inches(12.0), Inches(1.5), C_BG_GREEN)
    add_multi_para_textbox(s, Inches(0.9), Inches(5.85), Inches(11.6), Inches(1.3), [
        ("💡 ベッド粗利単価 = (A 日数×26,500 + B 日数×32,500 + C 日数×31,000) / 総延日数", 14, True),
        ("    → 短期入院（A 群）中心 → 単価 低い", 13, False),
        ("    → 長期入院（B + C 群）中心 → 単価 高い", 13, False),
    ], color=C_TITLE)

    # ====================================================================
    # Slide 7: 計算の考え方（概念図）
    # ====================================================================
    s = prs.slides.add_slide(blank_layout)
    add_bg_rect(s, 0, 0, SW, Inches(1.0), C_BG_BLUE)
    add_textbox(s, Inches(0.5), Inches(0.2), Inches(12.3), Inches(0.7),
                "計算の考え方 — 年間粗利 ＝ 量 × 単価 × 期間",
                size=26, bold=True, color=C_TITLE)
    add_image_to_slide(s, CHART_DIR / f"01_concept_{mode}.png",
                       Inches(0.5), Inches(1.1), Inches(12.3))

    # ====================================================================
    # Slide 8: 散布図
    # ====================================================================
    s = prs.slides.add_slide(blank_layout)
    add_bg_rect(s, 0, 0, SW, Inches(1.0), C_BG_BLUE)
    add_textbox(s, Inches(0.5), Inches(0.2), Inches(12.3), Inches(0.7),
                "結果① 医師別 ポジショニング（散布図）",
                size=28, bold=True, color=C_TITLE)
    add_image_to_slide(s, CHART_DIR / f"02_scatter_{mode}.png",
                       Inches(0.7), Inches(1.2), Inches(11.9))

    # ====================================================================
    # Slide 9: 病棟別ランキング
    # ====================================================================
    s = prs.slides.add_slide(blank_layout)
    add_bg_rect(s, 0, 0, SW, Inches(1.0), C_BG_BLUE)
    add_textbox(s, Inches(0.5), Inches(0.2), Inches(12.3), Inches(0.7),
                "結果② 病棟別 稼働率寄与率ランキング",
                size=28, bold=True, color=C_TITLE)
    add_image_to_slide(s, CHART_DIR / f"03_ward_ranking_{mode}.png",
                       Inches(0.5), Inches(1.2), Inches(12.3))

    # ====================================================================
    # Slide 10: ツリーマップ（粗利シェア）
    # ====================================================================
    s = prs.slides.add_slide(blank_layout)
    add_bg_rect(s, 0, 0, SW, Inches(1.0), C_BG_BLUE)
    total_oku = agg['総粗利'].sum() / 1e8
    add_textbox(s, Inches(0.5), Inches(0.2), Inches(12.3), Inches(0.7),
                f"結果③ 粗利シェア — 全体年間粗利 {total_oku:.2f} 億円 の内訳",
                size=24, bold=True, color=C_TITLE)
    add_image_to_slide(s, CHART_DIR / f"04_treemap_{mode}.png",
                       Inches(0.7), Inches(1.2), Inches(11.9))

    # ====================================================================
    # Slide 11: 相関検証
    # ====================================================================
    s = prs.slides.add_slide(blank_layout)
    add_bg_rect(s, 0, 0, SW, Inches(1.0), C_BG_BLUE)
    add_textbox(s, Inches(0.5), Inches(0.2), Inches(12.3), Inches(0.7),
                "結果④ 稼働率寄与率 と 粗利 の相関検証",
                size=28, bold=True, color=C_TITLE)
    add_image_to_slide(s, CHART_DIR / f"05_correlation_{mode}.png",
                       Inches(0.7), Inches(1.1), Inches(11.9))
    add_bg_rect(s, Inches(0.7), Inches(6.6), Inches(11.9), Inches(0.8), C_BG_GREEN)
    add_textbox(s, Inches(0.9), Inches(6.75), Inches(11.5), Inches(0.5),
                "💡 結論: 稼働率寄与率を主指標にすれば粗利の 9 割以上を説明できる",
                size=18, bold=True, color=C_OK)

    # ====================================================================
    # Slide 12: 主な発見 — 単価トップ 3 はすべて長期入院型
    # ====================================================================
    s = prs.slides.add_slide(blank_layout)
    add_bg_rect(s, 0, 0, SW, Inches(1.0), C_BG_GREEN)
    add_textbox(s, Inches(0.5), Inches(0.2), Inches(12.3), Inches(0.7),
                "主な発見① 粗利単価 トップ 3 はすべて長期入院型",
                size=26, bold=True, color=C_OK)

    rows_top3 = []
    for i, (_, r) in enumerate(top3_unit.iterrows(), 1):
        rows_top3.append((
            f"{i}. {label_map(r['医師'])}",
            f"{r['ベッド粗利単価']:,.0f} 円/床日",
            f"平均在院 {r['平均在院日数']:.1f} 日",
            f"B 群 {r['B群比率']:.0f}% / C 群 {r['C群比率']:.0f}% / A 群 {r['A群比率']:.0f}%",
        ))

    body_lines = [("ベッド粗利単価 上位 3 名:", 22, True), ("", 12, False)]
    for medic, unit, los, mix in rows_top3:
        body_lines.extend([
            (f"  {medic}    {unit}    {los}", 18, True),
            (f"      {mix}", 14, False),
            ("", 6, False),
        ])
    body_lines.extend([
        ("", 12, False),
        ("💡 重要発見: 単価が高い医師は B + C 群が多い → 長期入院型", 20, True),
        ("       「短期回転＝高単価」という思い込みは誤り", 18, True),
    ])
    add_multi_para_textbox(s, Inches(0.7), Inches(1.3), Inches(12.0), Inches(5.8), body_lines)

    # ====================================================================
    # Slide 13: 主な発見 — 5F 構造リスク
    # ====================================================================
    s = prs.slides.add_slide(blank_layout)
    add_bg_rect(s, 0, 0, SW, Inches(1.0), C_BG_RED)
    add_textbox(s, Inches(0.5), Inches(0.2), Inches(12.3), Inches(0.7),
                f"主な発見② 5F 病棟は {okuk_label} 1 名に依存（構造的リスク）",
                size=24, bold=True, color=C_DANGER)

    add_multi_para_textbox(s, Inches(0.7), Inches(1.5), Inches(12.0), Inches(5.5), [
        ("● 5F 病棟の年間延べ床日数 14,557 床日 のうち", 18, False),
        (f"    {okuk_label} 単独で 3,394 床日（23.3%）を占有", 22, True),
        ("", 10, False),
        ("● 次点の 5F 主治医は 13.1% で 10pt 以上の差", 18, False),
        ("", 10, False),
        (f"● {okuk_label} の長期不在で 5F 年間稼働率が", 18, False),
        ("    84.9% → 約 78.5% まで低下するリスク", 22, True),
        ("", 16, False),
        ("⚠️ バックアップ体制の脆弱性 — 緊急対応が必要", 20, True),
    ], color=C_TITLE)

    # ====================================================================
    # Slide 14: 主な発見 — 6F 健全構造
    # ====================================================================
    s = prs.slides.add_slide(blank_layout)
    add_bg_rect(s, 0, 0, SW, Inches(1.0), C_BG_GREEN)
    add_textbox(s, Inches(0.5), Inches(0.2), Inches(12.3), Inches(0.7),
                "主な発見③ 6F 病棟は 3 名でバランスよく支えられている",
                size=24, bold=True, color=C_OK)

    top3_names = '・'.join(top3_6f['医師'].map(label_map).tolist())
    add_multi_para_textbox(s, Inches(0.7), Inches(1.5), Inches(12.0), Inches(5.5), [
        ("● 6F 病棟 上位 3 名:", 20, True),
        (f"    {top3_names}", 22, True),
        (f"    合計 6F 寄与率 {top3_share_6f:.1f}%", 18, False),
        ("", 14, False),
        ("● 5F の中央集中（49%）と比べ、6F は分散度が高い", 18, False),
        ("", 10, False),
        ("● 特定医師不在時のリスクが相対的に小さい", 22, True),
        ("", 10, False),
        ("● 6F 年間稼働率 88.8%（目標 90% にあと 1.2pt）", 18, False),
        ("", 16, False),
        ("✅ 健全な分散型運営", 20, True),
    ], color=C_TITLE)

    # ====================================================================
    # Slide 15: 提言 1
    # ====================================================================
    s = prs.slides.add_slide(blank_layout)
    add_bg_rect(s, 0, 0, SW, Inches(1.0), C_BG_BLUE)
    add_textbox(s, Inches(0.5), Inches(0.2), Inches(12.3), Inches(0.7),
                "提言 1:  5F 病棟の主治医不足リスクを解消する",
                size=26, bold=True, color=C_TITLE)
    add_multi_para_textbox(s, Inches(0.7), Inches(1.6), Inches(12.0), Inches(5.5), [
        (f"課題: 5F の {okuk_label} 依存（23.3%）は経営継続性のリスク", 20, True),
        ("", 14, False),
        ("対応:", 20, True),
        ("    ● 5F に主たる病棟を持つ医師を 1〜2 名増員", 18, False),
        (f"    ● {okuk_label} の患者バックアップ体制を整備", 18, False),
        ("    ● 5F 主治医の月次寄与率を可視化し、依存度を継続モニタリング", 18, False),
        ("", 12, False),
        ("期待効果:", 20, True),
        ("    ● 5F 年間稼働率 84.9% → 90% へ", 18, False),
        ("    ● 不在リスクで稼働率 6pt 下落を防止", 18, False),
    ], color=C_TITLE)

    # ====================================================================
    # Slide 16: 提言 2 — 運営方針の転換
    # ====================================================================
    s = prs.slides.add_slide(blank_layout)
    add_bg_rect(s, 0, 0, SW, Inches(1.0), C_BG_GOLD)
    add_textbox(s, Inches(0.5), Inches(0.2), Inches(12.3), Inches(0.7),
                "提言 2:  「短期回転推進」ではなく「適切な在院期間管理」",
                size=24, bold=True, color=C_GOLD)
    add_multi_para_textbox(s, Inches(0.7), Inches(1.6), Inches(12.0), Inches(5.5), [
        ("本解析で「B 群（回復期 6〜14 日）の中心管理が最も粗利貢献が高い」", 18, False),
        ("ことが明確になりました。", 18, False),
        ("", 14, False),
        ("運営方針:", 20, True),
        ("    ● 適応のある患者を 6〜14 日の B 群中心で安定管理する文化を強化", 18, False),
        ("    ● C 群（15 日以降）への滞留を抑え、退院支援に注力", 18, False),
        ("    ● A 群（急性期）は本来必要な医療を提供（コスト理由で減らさない）", 18, False),
        ("", 14, False),
        ("⚠️ 倫理的配慮:", 16, True),
        ("    患者選別・適応外入院・在院延長を誘発しない設計とする", 14, False),
        ("    「適応のある患者を、適切な期間で治療し、自宅復帰を支援する」が大前提", 14, False),
    ], color=C_TITLE)

    # ====================================================================
    # Slide 17: 提言 3 — KPI モニタリング
    # ====================================================================
    s = prs.slides.add_slide(blank_layout)
    add_bg_rect(s, 0, 0, SW, Inches(1.0), C_BG_BLUE)
    add_textbox(s, Inches(0.5), Inches(0.2), Inches(12.3), Inches(0.7),
                "提言 3:  KPI 月次モニタリング体制を確立する",
                size=26, bold=True, color=C_TITLE)
    add_multi_para_textbox(s, Inches(0.7), Inches(1.6), Inches(12.0), Inches(5.5), [
        ("KPI 設計:", 20, True),
        ("    主指標: 稼働率寄与率（%） — ベッドを埋める量の貢献", 18, False),
        ("    副指標: ベッド粗利単価（円/床日） — 1 床 1 日あたりの運営貢献額", 18, False),
        ("    合成 : 年間粗利 = 主 × 副 × 期間（参考値）", 18, False),
        ("", 14, False),
        ("運用方法:", 20, True),
        ("    ● 月次会議で全医師の寄与率・粗利単価を併記表示", 18, False),
        ("    ● 順位ではなく散布図で「タイプ分類」として議論", 18, False),
        ("    ● ベッドコントロールシミュレーターに月次自動更新機能を組込み", 18, False),
    ], color=C_TITLE)

    # ====================================================================
    # Slide 18: 提言 4 — Stage 2 精緻化
    # ====================================================================
    s = prs.slides.add_slide(blank_layout)
    add_bg_rect(s, 0, 0, SW, Inches(1.0), C_BG_BLUE)
    add_textbox(s, Inches(0.5), Inches(0.2), Inches(12.3), Inches(0.7),
                "提言 4:  Stage 2 — リハ加算・処置加算で精緻化",
                size=26, bold=True, color=C_TITLE)
    add_multi_para_textbox(s, Inches(0.7), Inches(1.6), Inches(12.0), Inches(5.5), [
        ("現状（Stage 1）の限界:", 20, True),
        ("    フェーズ別粗利のみで概算", 18, False),
        ("", 12, False),
        ("Stage 2 追加データ要求（事務へ）:", 20, True),
        ("    ● 患者別 月次リハビリ単位数（PT / OT / ST）", 18, False),
        ("    ● 処置加算（中心静脈、人工呼吸器、ドレーン等）", 18, False),
        ("    ● 検査加算・手術料の患者別月次集計", 18, False),
        ("", 14, False),
        ("Stage 2 完成後の効果:", 20, True),
        ("    ● 「実際にどの加算で単価を上げられるか」が見える", 18, False),
        ("    ● 診療科横断のベストプラクティス共有が可能に", 18, False),
    ], color=C_TITLE)

    # ====================================================================
    # Slide 19: ご質問
    # ====================================================================
    s = prs.slides.add_slide(blank_layout)
    add_bg_rect(s, 0, 0, SW, SH, RGBColor(0xF9, 0xFA, 0xFB))
    add_textbox(s, Inches(0.5), Inches(3.0), Inches(12.3), Inches(1.5),
                "ご質問・ご討議",
                size=60, bold=True, color=C_TITLE, align=PP_ALIGN.CENTER)
    add_textbox(s, Inches(0.5), Inches(4.5), Inches(12.3), Inches(0.7),
                "おもろまちメディカルセンター",
                size=18, color=C_MUTED, align=PP_ALIGN.CENTER)
    add_textbox(s, Inches(0.5), Inches(5.0), Inches(12.3), Inches(0.7),
                "副院長 久保田 透",
                size=14, color=C_MUTED, align=PP_ALIGN.CENTER)

    suffix = '理事会プレゼン' if mode == 'named' else '運営会議プレゼン'
    out_path = REPO_ROOT / 'docs' / 'admin' / f'医師別KPI解析_{suffix}_2026-05-04.pptx'
    prs.save(out_path)
    print(f"✅ Generated: {out_path} ({len(prs.slides)} slides)")
    return out_path


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['named', 'anonymous'], default='named')
    args = parser.parse_args()
    build(args.mode)
