"""医師別 病棟貢献度 KPI 解析 — 理事会・運営会議 説明資料 DOCX 生成.

副院長指示 (2026-05-04):
  - 理事会版: 個人名（実医師コード）
  - 運営会議版: A 医師, B 医師（匿名化）
  - ヒラギノ明朝、A4 縦
  - 素人医師にも分かりやすい計算根拠の解説

使い方:
  .venv/bin/python scripts/generate_doctor_kpi_report_docx.py --mode named
  .venv/bin/python scripts/generate_doctor_kpi_report_docx.py --mode anonymous
"""
from __future__ import annotations

import argparse
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from generate_doctor_kpi_charts import (
    OUT_DIR as CHART_DIR,
    load_and_compute,
    make_anonymous_map,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
JP_FONT = "Hiragino Mincho ProN"

C_TITLE = RGBColor(0x1F, 0x29, 0x37)
C_ACCENT = RGBColor(0x25, 0x63, 0xEB)
C_DANGER = RGBColor(0xDC, 0x26, 0x26)
C_OK = RGBColor(0x10, 0xB9, 0x81)
C_MUTED = RGBColor(0x6B, 0x72, 0x80)
C_FAINT = RGBColor(0x9C, 0xA3, 0xAF)


def _set_jp_font(run, size_pt=11, bold=False, color=None):
    run.font.name = JP_FONT
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    rFonts.set(qn("w:eastAsia"), JP_FONT)
    rFonts.set(qn("w:ascii"), JP_FONT)
    rFonts.set(qn("w:hAnsi"), JP_FONT)


def add_para(doc, text, size=11, bold=False, align=None, color=None):
    p = doc.add_paragraph()
    if align is not None:
        p.alignment = align
    run = p.add_run(text)
    _set_jp_font(run, size_pt=size, bold=bold, color=color)
    return p


def add_heading(doc, text, level=1):
    sizes = {0: 24, 1: 18, 2: 15, 3: 13}
    h = doc.add_heading(level=level)
    run = h.add_run(text)
    _set_jp_font(run, size_pt=sizes.get(level, 12), bold=True, color=C_TITLE)


def add_callout(doc, label, body, color=None):
    if color is None:
        color = C_ACCENT
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.5)
    run_label = p.add_run(label + " ")
    _set_jp_font(run_label, size_pt=11, bold=True, color=color)
    run_body = p.add_run(body)
    _set_jp_font(run_body, size_pt=11)


def add_image(doc, path, width_cm=16):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    run.add_picture(str(path), width=Cm(width_cm))


def add_table(doc, header, rows, col_widths_cm=None):
    table = doc.add_table(rows=1 + len(rows), cols=len(header))
    table.style = "Light Grid Accent 1"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    if col_widths_cm:
        for col, w in zip(table.columns, col_widths_cm):
            for cell in col.cells:
                cell.width = Cm(w)
    hdr = table.rows[0].cells
    for i, label in enumerate(header):
        hdr[i].text = ""
        run = hdr[i].paragraphs[0].add_run(label)
        _set_jp_font(run, size_pt=10, bold=True, color=C_TITLE)
    for r_i, row_data in enumerate(rows, start=1):
        cells = table.rows[r_i].cells
        for c_i, val in enumerate(row_data):
            cells[c_i].text = ""
            run = cells[c_i].paragraphs[0].add_run(str(val))
            _set_jp_font(run, size_pt=10)


def build(mode: str):
    df, agg, ward_total_days, total_hospital_days = load_and_compute()
    anon_map = make_anonymous_map(agg)

    label_map = (lambda x: x) if mode == 'named' else (lambda x: anon_map.get(x, x))

    title_audience = "理事会" if mode == 'named' else "運営会議"

    doc = Document()

    style = doc.styles["Normal"]
    style.font.name = JP_FONT
    style.font.size = Pt(11)

    for section in doc.sections:
        section.top_margin = Cm(2.0)
        section.bottom_margin = Cm(2.0)
        section.left_margin = Cm(2.2)
        section.right_margin = Cm(2.2)

    # ====================================================================
    # 表紙
    # ====================================================================
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(80)
    run = p.add_run("医師別 病棟貢献度 KPI 解析")
    _set_jp_font(run, size_pt=26, bold=True, color=C_TITLE)

    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run2 = p2.add_run(f"{title_audience}説明資料")
    _set_jp_font(run2, size_pt=18, bold=True, color=C_ACCENT)

    p3 = doc.add_paragraph()
    p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p3.paragraph_format.space_before = Pt(48)
    run3 = p3.add_run("〜 過去 1 年の入院データから医師別の病棟運営貢献を見える化 〜")
    _set_jp_font(run3, size_pt=12, color=C_MUTED)

    p4 = doc.add_paragraph()
    p4.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p4.paragraph_format.space_before = Pt(120)
    run4 = p4.add_run("おもろまちメディカルセンター")
    _set_jp_font(run4, size_pt=14)

    p5 = doc.add_paragraph()
    p5.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run5 = p5.add_run("副院長 久保田 透")
    _set_jp_font(run5, size_pt=12)

    p6 = doc.add_paragraph()
    p6.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p6.paragraph_format.space_before = Pt(8)
    run6 = p6.add_run("作成日：2026 年 5 月 4 日")
    _set_jp_font(run6, size_pt=11, color=C_FAINT)

    if mode == 'anonymous':
        p7 = doc.add_paragraph()
        p7.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p7.paragraph_format.space_before = Pt(20)
        run7 = p7.add_run("※ 個人名はすべて A 医師, B 医師 ... と匿名化しています")
        _set_jp_font(run7, size_pt=10, color=C_DANGER)

    doc.add_page_break()

    # ====================================================================
    # 0. エグゼクティブサマリー
    # ====================================================================
    add_heading(doc, "エグゼクティブサマリー", level=1)
    add_para(doc, "本資料の要点を 5 行で示します。")
    add_para(doc, "")
    summary_lines = [
        "①  過去 1 年（2025-04 〜 2026-04）の入院 1,960 件を医師別に集計し、各医師が病棟稼働率と病院収益にどれだけ貢献しているかを算出しました。",
        "②  「医師別 稼働率寄与率」は **「年間収益貢献額」と相関係数 r = 0.96** で極めて強く連動します。つまり稼働率寄与率を主指標にすれば経営評価の 9 割以上を説明できます。",
        "③  6F 病棟は上位 3 名（収益順 1〜3 位の医師）が約 55% を担い、バランスが取れた構造です。",
        "④  5F 病棟は **収益 4 位の医師 1 名で 23.3%** を占有しており、その医師の不在リスクが構造的課題として浮上しました。",
        "⑤  KPI は「稼働率寄与率（量）」と「ベッド単価（質）」の 2 軸で月次モニタリングし、施設基準達成と単価向上を同時に管理することを提言します。",
    ]
    for line in summary_lines:
        add_para(doc, line)
    doc.add_page_break()

    # ====================================================================
    # 1. 目的
    # ====================================================================
    add_heading(doc, "1. なぜ「医師別 病棟貢献度」を見える化するのか", level=1)
    add_para(
        doc,
        "病棟稼働率は施設基準（地域包括医療病棟は 90% 目標）を満たすための"
        "経営的・制度的な最重要指標です。これまで「病棟稼働率は副院長の責任」"
        "のように属人化して見えがちでしたが、実態は **各主治医の入院・在院・"
        "退院判断の総和** が病棟稼働率を作っています。",
    )
    add_para(doc, "")
    add_para(doc, "本資料は次の 3 つの問いに答えます。", bold=True)
    add_para(doc, "  1. 各医師が病棟稼働率をどれだけ支えているか？")
    add_para(doc, "  2. それは病院収益にどう結びついているか？")
    add_para(doc, "  3. 構造的なリスク（特定医師への依存など）はないか？")
    add_para(doc, "")
    add_callout(
        doc,
        "📌 重要な前提",
        "本解析は「医師の評価」ではなく「病棟運営の構造把握」を目的とします。"
        "個別医師の優劣ではなく、診療科特性や役割分担を踏まえた上で、"
        "病棟全体の運営最適化に向けた議論材料として提示します。",
        color=C_DANGER,
    )
    doc.add_page_break()

    # ====================================================================
    # 2. 計算の考え方（素人向け）
    # ====================================================================
    add_heading(doc, "2. 計算の考え方（数式の前に図で理解する）", level=1)
    add_para(
        doc,
        "本資料では「医師別 病棟貢献度」を 2 つの掛け算で表現します。"
        "数式を見る前に、図で意味を理解してください。",
    )
    add_para(doc, "")
    add_image(doc, CHART_DIR / f"01_concept_{mode}.png", width_cm=15.5)
    add_para(doc, "")

    add_heading(doc, "2.1 年間収益 = 受持数 × ベッド単価 × 365 日", level=2)
    add_para(
        doc,
        "ある医師が 1 年間に病棟運営に貢献した金額（年間収益）は、"
        "次の掛け算で表されます。",
    )
    add_para(doc, "")
    add_callout(
        doc,
        "💡 計算式",
        "年間収益（円） = 月平均受持患者数（人） × 1 床 1 日あたりの収益（円）× 365 日",
        color=C_ACCENT,
    )
    add_para(doc, "")
    add_para(
        doc,
        "つまり「**横（受持数）× 縦（ベッド単価）の長方形の面積**」が"
        "年間収益にあたります。図のように、受持数が多いだけでも・単価が高いだけでも"
        "収益は上がりますが、両方を高めるのが理想です。",
    )
    add_para(doc, "")

    add_heading(doc, "2.2 ベッド単価とは何か（地域包括医療病棟の特徴）", level=2)
    add_para(
        doc,
        "地域包括医療病棟入院料は、入院日数によって 1 日あたりの報酬が変わる仕組みです。"
        "本資料では次のように単価を分けて計算しています。",
    )
    add_para(doc, "")
    add_table(
        doc,
        ["フェーズ", "在院期間", "1 床 1 日あたり収益（概算）"],
        [
            ["A 群（急性期）", "入院 1〜5 日", "約 24,000 円"],
            ["B 群（回復期）", "入院 6〜14 日", "約 13,200 円"],
            ["C 群（退院準備期）", "入院 15 日以降", "約 6,400 円"],
        ],
        col_widths_cm=[4, 4, 7],
    )
    add_para(doc, "")
    add_para(
        doc,
        "ある医師の患者が短期入院（A 群）中心ならベッド単価は高くなり、"
        "長期入院（C 群）中心ならベッド単価は低くなります。"
        "医師ごとに「ベッド単価」を計算することで、診療科特性が見える化されます。",
    )
    add_para(doc, "")

    add_heading(doc, "2.3 稼働率寄与率とは", level=2)
    add_para(
        doc,
        "「稼働率寄与率」は **病棟全体の延べ床日数のうち、その医師が何 % を埋めているか** を表します。",
    )
    add_para(doc, "")
    add_callout(
        doc,
        "💡 計算式",
        "病棟内 寄与率 (%) = （その医師の延べ床日数）÷（病棟全体の延べ床日数）× 100",
        color=C_ACCENT,
    )
    add_para(doc, "")
    add_para(
        doc,
        "病棟稼働率は施設基準達成のために最も重要な指標です。"
        "「ベッドを埋めることへの貢献度」を直接的に表します。",
    )
    doc.add_page_break()

    # ====================================================================
    # 3. データ概要
    # ====================================================================
    add_heading(doc, "3. データ概要", level=1)
    add_table(
        doc,
        ["項目", "内容"],
        [
            ["対象期間", "2025-04-01 〜 2026-04-25（約 13 ヶ月）"],
            ["対象データ", "全入院 1,960 件（事務提供 CSV、患者氏名なし、医師コード化）"],
            ["対象病棟", "5F 病棟（47 床）+ 6F 病棟（47 床）= 計 94 床"],
            ["分析対象医師", f"年間入院 10 件以上の {len(agg)} 名"],
            ["除外", "件数 10 未満の医師（4 名）は統計的に弱いため集計から除外"],
            ["計算手法", "フェーズ別単価 × 在院日数 で年間収益貢献額を算出（Stage 1）"],
        ],
        col_widths_cm=[4, 12],
    )
    add_para(doc, "")
    add_callout(
        doc,
        "⚠️ 本解析の限界（Stage 1）",
        "本資料は「フェーズ別単価」のみを反映した概算です。"
        "リハビリ加算・処置加算・手術料・救急加算などは未反映のため、"
        "実額には差があります。次フェーズで事務から追加データを取得し精緻化予定です。",
        color=C_DANGER,
    )
    doc.add_page_break()

    # ====================================================================
    # 4. 結果と主な発見
    # ====================================================================
    add_heading(doc, "4. 結果と主な発見", level=1)
    add_heading(doc, "4.1 医師別 ポジショニング（散布図）", level=2)
    add_para(
        doc,
        "医師ごとの「稼働率寄与率（横軸）」と「ベッド単価（縦軸）」を散布図で示します。"
        "右に行くほど病棟運営への量の貢献が大きく、上に行くほど 1 床 1 日あたりの収益が高い医師です。",
    )
    add_para(doc, "")
    add_image(doc, CHART_DIR / f"02_scatter_{mode}.png", width_cm=15.5)
    add_para(doc, "")
    add_callout(
        doc,
        "🔍 観察",
        "右上の「量も単価も両立した理想型」には誰も該当しません。"
        "現状、量で稼ぐ医師（右下）と単価で稼ぐ医師（左上）に分かれており、"
        "両立は今後の課題です。",
        color=C_ACCENT,
    )
    doc.add_page_break()

    add_heading(doc, "4.2 病棟別 稼働率寄与率ランキング", level=2)
    add_para(
        doc,
        "5F 病棟と 6F 病棟それぞれについて、各医師の寄与率をランキング表示します。",
    )
    add_para(doc, "")
    add_image(doc, CHART_DIR / f"03_ward_ranking_{mode}.png", width_cm=16)
    add_para(doc, "")

    # 病棟別合計表
    sub_5f = agg[agg['5F_寄与率'] > 0].sort_values('5F_寄与率', ascending=False)
    sub_6f = agg[agg['6F_寄与率'] > 0].sort_values('6F_寄与率', ascending=False)
    add_para(doc, "5F 病棟 上位 5 名:", bold=True)
    rows_5f = [
        [str(i+1), label_map(r['医師']), f"{r['5F_寄与率']:.1f}%",
         f"{int(r['5F_延日数']):,}床日", f"{r['平均在院日数']:.1f}日"]
        for i, (_, r) in enumerate(sub_5f.head(5).iterrows())
    ]
    add_table(doc, ["順位", "医師", "5F 寄与率", "延日数", "平均在院日数"],
              rows_5f, col_widths_cm=[1.5, 2.5, 3, 3, 3])
    add_para(doc, "")
    add_para(doc, "6F 病棟 上位 5 名:", bold=True)
    rows_6f = [
        [str(i+1), label_map(r['医師']), f"{r['6F_寄与率']:.1f}%",
         f"{int(r['6F_延日数']):,}床日", f"{r['平均在院日数']:.1f}日"]
        for i, (_, r) in enumerate(sub_6f.head(5).iterrows())
    ]
    add_table(doc, ["順位", "医師", "6F 寄与率", "延日数", "平均在院日数"],
              rows_6f, col_widths_cm=[1.5, 2.5, 3, 3, 3])
    doc.add_page_break()

    add_heading(doc, "4.3 経営シェア・ツリーマップ", level=2)
    add_para(
        doc,
        f"全体年間収益 {agg['総収益'].sum()/1e8:.2f} 億円 を 100% として、"
        "各医師が占めるシェアを面積で表示します。",
    )
    add_para(doc, "")
    add_image(doc, CHART_DIR / f"04_treemap_{mode}.png", width_cm=16)
    add_para(doc, "")
    top3 = agg.sort_values('総収益', ascending=False).head(3)
    top3_share = top3['総収益'].sum() / agg['総収益'].sum() * 100
    add_callout(
        doc,
        "🔍 観察",
        f"上位 3 名（{', '.join(top3['医師'].map(label_map).tolist())}）で"
        f"全体の {top3_share:.1f}% を担っています。",
        color=C_ACCENT,
    )
    doc.add_page_break()

    add_heading(doc, "4.4 稼働率寄与率と病院収益の相関検証", level=2)
    add_para(
        doc,
        "「稼働率寄与率は病院収益と相関するか」を統計的に検証しました。",
    )
    add_para(doc, "")
    add_image(doc, CHART_DIR / f"05_correlation_{mode}.png", width_cm=15.5)
    add_para(doc, "")
    add_table(
        doc,
        ["統計指標", "値", "解釈"],
        [
            ["相関係数 r", "0.962", "極めて強い正相関（医学統計上「ほぼ確実」）"],
            ["決定係数 R²", "0.925", "収益のばらつきの 92.5% は寄与率で説明可"],
            ["回帰直線", "収益 = 322 × 寄与率 + 493 万円", "寄与率 1% 上昇で年 約 322 万円 増収"],
        ],
        col_widths_cm=[4, 5, 7],
    )
    add_para(doc, "")
    add_callout(
        doc,
        "💡 結論",
        "稼働率寄与率を主指標にすれば、収益の 9 割以上を説明できます。"
        "残り 7.5% はベッド単価の差（短期回転型かどうか）で決まります。",
        color=C_OK,
    )
    doc.add_page_break()

    # ====================================================================
    # 5. 主な発見（個別）
    # ====================================================================
    add_heading(doc, "5. 主な発見", level=1)

    okuk_label = label_map('OKUK')
    add_heading(doc, f"5.1 5F 病棟は {okuk_label} 1 名に依存している", level=2)
    add_para(
        doc,
        f"5F 病棟の年間延べ床日数 14,557 床日のうち、{okuk_label} 単独で "
        f"3,394 床日（23.3%）を占めています。次点は 13.1% で 10pt 以上の差があり、"
        f"{okuk_label} の長期不在は 5F の年間稼働率を 84.9% → 約 78.5% まで押し下げる構造リスクを内包します。",
    )
    add_para(doc, "")
    add_callout(
        doc,
        "⚠️ リスク",
        f"特定医師への依存はバックアップ体制の脆弱性。"
        f"{okuk_label} が病気・退職・休暇等で不在となった場合の代替体制が不十分です。",
        color=C_DANGER,
    )
    add_para(doc, "")

    add_heading(doc, "5.2 6F 病棟は 3 名でバランスよく支えられている", level=2)
    top3_6f = sub_6f.head(3)
    top3_names = ', '.join(top3_6f['医師'].map(label_map).tolist())
    top3_share_6f = top3_6f['6F_寄与率'].sum()
    add_para(
        doc,
        f"6F 病棟は上位 3 名（{top3_names}）が合計 {top3_share_6f:.1f}% を占め、"
        "中央集中が緩やかです。これは冗長性が高く、特定医師の不在リスクが相対的に小さいことを意味します。",
    )
    add_para(doc, "")

    add_heading(doc, "5.3 量で支える医師は単価面で下振れする傾向", level=2)
    add_para(
        doc,
        "回帰直線からの偏差を見ると、寄与率が高い医師ほどベッド単価が低めで"
        "「予測値より下振れ」する傾向があります。これは長期入院（C 群）が増えると"
        "1 床 1 日あたりの単価が下がるためで、診療科特性を反映しています。",
    )
    add_para(doc, "")
    add_callout(
        doc,
        "💡 含意",
        "量で稼働率を支えてくれている医師に対し、単価が低いことを理由に"
        "評価を下げてはいけません。彼らの貢献なくして施設基準達成は不可能です。",
        color=C_ACCENT,
    )
    doc.add_page_break()

    # ====================================================================
    # 6. 提言
    # ====================================================================
    add_heading(doc, "6. 提言", level=1)

    add_heading(doc, f"提言 1: 5F 病棟の主治医不足リスクを解消する", level=2)
    add_para(
        doc,
        f"5F の {okuk_label} 依存（23.3%）は経営継続性のリスクです。次の対応を提言します。",
    )
    add_para(doc, "  ・5F に主たる病棟を持つ医師を 1〜2 名増員する")
    add_para(doc, f"  ・{okuk_label} の患者バックアップ体制を整備する（指示・指導の引継ぎ）")
    add_para(doc, "  ・5F 主治医の月次寄与率を可視化し、依存度を継続モニタリング")
    add_para(doc, "")

    add_heading(doc, "提言 2: KPI 月次モニタリング体制を確立する", level=2)
    add_para(
        doc,
        "「稼働率寄与率（主指標）」と「ベッド単価（副指標）」の 2 軸で"
        "月次会議資料を定例化し、病棟運営の透明性を高めます。",
    )
    add_para(doc, "  ・月次会議で全医師の寄与率・単価を併記表示")
    add_para(doc, "  ・順位ではなく散布図で「タイプ分類」として議論")
    add_para(doc, "  ・既存のベッドコントロールシミュレーターに月次自動更新機能を組込み")
    add_para(doc, "")
    add_callout(
        doc,
        "📌 倫理的配慮",
        "KPI は患者選別・適応外入院・在院延長の誘因にしてはいけません。"
        "「適応のある患者を、適切な期間で治療し、自宅復帰を支援する」"
        "という医療の質を犠牲にしないことを大前提とします。",
        color=C_DANGER,
    )
    add_para(doc, "")

    add_heading(doc, "提言 3: 単価向上余地の構造分析（Stage 2 提案）", level=2)
    add_para(
        doc,
        "現状はフェーズ別単価のみで概算しています。事務から下記データを追加取得し、"
        "より実態に近いベッド単価を算出すれば、リハビリ強化や処置加算の積極化など"
        "具体的な改善余地が見える化できます。",
    )
    add_para(doc, "  ・患者別 月次リハビリ単位数（PT/OT/ST）")
    add_para(doc, "  ・処置加算（中心静脈、人工呼吸器、ドレーン管理等）")
    add_para(doc, "  ・検査加算・手術料の患者別月次集計")
    doc.add_page_break()

    # ====================================================================
    # 7. 参考: 全医師サマリー表
    # ====================================================================
    add_heading(doc, "7. 参考：全医師 集計表", level=1)
    rows_all = []
    for _, r in agg.iterrows():
        rows_all.append([
            label_map(r['医師']),
            f"{int(r['入院件数'])}",
            f"{r['平均在院日数']:.1f}",
            f"{r['月平均受持数']:.1f}",
            f"{r['病院全体寄与率']:.2f}%",
            f"{r['ベッド単価']:,.0f}",
            f"{r['総収益']/10000:.0f}",
        ])
    add_table(
        doc,
        ["医師", "件数", "平均在院日数(日)", "月平均受持数", "病院全体寄与率",
         "ベッド単価(円)", "年間収益(万円)"],
        rows_all,
        col_widths_cm=[2, 1.5, 2.2, 2.2, 2.5, 2.5, 2.5],
    )
    add_para(doc, "")
    add_para(
        doc,
        f"全体年間収益: {agg['総収益'].sum()/1e8:.2f} 億円　/　全体平均ベッド単価: "
        f"{agg['総収益'].sum()/agg['総延日数'].sum():,.0f} 円/床日",
        bold=True,
    )

    # ====================================================================
    # 保存
    # ====================================================================
    suffix = '理事会説明資料' if mode == 'named' else '運営会議説明資料'
    out_path = REPO_ROOT / 'docs' / 'admin' / f'医師別KPI解析_{suffix}_2026-05-04.docx'
    doc.save(out_path)
    print(f"✅ Generated: {out_path}")
    return out_path


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['named', 'anonymous'], default='named')
    args = parser.parse_args()
    build(args.mode)
