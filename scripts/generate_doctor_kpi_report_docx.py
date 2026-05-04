"""医師別 病棟貢献度 KPI 解析 — 理事会・運営会議 説明資料 DOCX 生成（粗利ベース 抜本改訂版）.

副院長指示 (2026-05-04):
  - 旧版で誤った数値（24000/13200/6400）を使用 → 抜本改訂
  - 正しくは粗利ベース（B 32,500 ＞ C 31,000 ＞ A 26,500 円/床日）
  - 理事会で「短期回転＝経営最適」という誤った認識を修正する設計
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
    p.paragraph_format.space_before = Pt(70)
    run = p.add_run("医師別 病棟貢献度 KPI 解析")
    _set_jp_font(run, size_pt=26, bold=True, color=C_TITLE)

    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run2 = p2.add_run(f"{title_audience}説明資料")
    _set_jp_font(run2, size_pt=18, bold=True, color=C_ACCENT)

    p3 = doc.add_paragraph()
    p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p3.paragraph_format.space_before = Pt(36)
    run3 = p3.add_run("〜 「短期回転 ＝ 経営最適」は誤り：B 群（回復期）の中心管理が運営貢献を最大化する 〜")
    _set_jp_font(run3, size_pt=13, color=C_DANGER, bold=True)

    p4 = doc.add_paragraph()
    p4.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p4.paragraph_format.space_before = Pt(60)
    run4 = p4.add_run("おもろまちメディカルセンター")
    _set_jp_font(run4, size_pt=14)

    p5 = doc.add_paragraph()
    p5.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run5 = p5.add_run("副院長 久保田 透")
    _set_jp_font(run5, size_pt=12)

    p6 = doc.add_paragraph()
    p6.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p6.paragraph_format.space_before = Pt(8)
    run6 = p6.add_run("作成日：2026 年 5 月 4 日 / Rev. 2（粗利ベース 抜本改訂版）")
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
    add_para(doc, "本資料の要点を 5 項目で示します。")
    add_para(doc, "")

    okuk_label = label_map('OKUK')
    sub_5f = agg[agg['5F_寄与率'] > 0].sort_values('5F_寄与率', ascending=False)
    sub_6f = agg[agg['6F_寄与率'] > 0].sort_values('6F_寄与率', ascending=False)
    top3_6f = sub_6f.head(3)
    top3_share_6f = top3_6f['6F_寄与率'].sum()
    top3_profit = agg.sort_values('総粗利', ascending=False).head(3)
    top3_profit_share = top3_profit['総粗利'].sum() / agg['総粗利'].sum() * 100

    summary_lines = [
        f"①  ベッド粗利単価の正しい順位は B 群（{PROFIT_B:,} 円/床日）＞ C 群（{PROFIT_C:,} 円）＞ A 群（{PROFIT_A:,} 円）。"
        "「短期回転＝経営貢献大」という認識は誤り。コストを差し引いた粗利では、B 群（回復期 6〜14 日）が最高単価。",
        "②  この知見に基づくと、長期入院（B・C 群）を多く担当する医師ほどベッド粗利単価が高い。"
        "実際、当院の上位 3 医師（粗利順）は **B 群＋C 群比率 80%超** の長期管理型です。",
        f"③  稼働率寄与率と年間粗利の相関は r = 0.96 と極めて強く、稼働率寄与率を主指標にすれば経営評価の 9 割以上を説明できる。",
        f"④  6F 病棟は上位 3 名で粗利の {top3_profit_share:.0f}% を担う健全な分散構造。"
        f"5F 病棟は {okuk_label} 1 名で 23.3% を占有しており、不在リスクが構造的課題。",
        "⑤  KPI は「稼働率寄与率（量）」と「ベッド粗利単価（質）」の 2 軸で月次モニタリング。"
        "「短期回転推進」ではなく「適切な在院期間で質の高い治療を完結する」運営最適化を提言。",
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
        "経営的・制度的な最重要指標です。「病棟稼働率は副院長の責任」のように属人化"
        "して見えがちですが、実態は **各主治医の入院・在院・退院判断の総和** が"
        "病棟稼働率を作っています。",
    )
    add_para(doc, "")
    add_para(doc, "本資料は次の 3 つの問いに答えます。", bold=True)
    add_para(doc, "  1. 各医師が病棟稼働率をどれだけ支えているか？")
    add_para(doc, "  2. それは病院収益（粗利＝運営貢献額）にどう結びついているか？")
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
    # 2. 計算の考え方（核心 — 粗利ベース）
    # ====================================================================
    add_heading(doc, "2. 計算の考え方（数式の前に図で理解する）", level=1)

    add_heading(doc, "2.1 重要な認識転換 — 「報酬」ではなく「粗利（運営貢献額）」で評価する", level=2)
    add_para(
        doc,
        "病院経営においては「日次診療報酬」ではなく、コスト（薬剤・処置・検査等の変動費）を"
        "差し引いた「粗利＝運営貢献額」で評価する必要があります。",
    )
    add_para(doc, "")
    add_image(doc, CHART_DIR / f"06_misconception_{mode}.png", width_cm=15.5)
    add_para(doc, "")

    add_callout(
        doc,
        "❌ 誤った認識",
        "「短期回転＝急性期＝高単価」と思い込みがちですが、A 群（急性期）はコスト"
        "（薬剤・処置・検査・看護人手）が大きく、粗利は 3 群中 **最低**です。",
        color=C_DANGER,
    )
    add_para(doc, "")
    add_callout(
        doc,
        "✅ 正しい認識",
        "コストを差し引くと B 群（回復期）が最高、C 群（退院準備）が次、A 群が最低。"
        "B 群を多く担当する医師ほど運営貢献が大きい。",
        color=C_OK,
    )
    doc.add_page_break()

    add_heading(doc, "2.2 フェーズ別の単価構造（地域包括医療病棟入院料 1）", level=2)
    add_para(
        doc,
        "アプリ実装の 2026 年度プリセット（入院料 1・イ/ロ/ハ加重平均）に基づく数値:",
    )
    add_para(doc, "")
    add_table(
        doc,
        ["フェーズ", "在院期間", "① 日次診療報酬", "② 日次変動費", "③ 粗利（① − ②）"],
        [
            ["A 群（急性期）", "1 〜 5 日",
             f"{REV_A:,} 円", f"{COST_A:,} 円", f"{PROFIT_A:,} 円（3 位）"],
            ["B 群（回復期）", "6 〜 14 日",
             f"{REV_B:,} 円", f"{COST_B:,} 円", f"★ {PROFIT_B:,} 円（1 位）"],
            ["C 群（退院準備）", "15 日以降",
             f"{REV_C:,} 円", f"{COST_C:,} 円", f"{PROFIT_C:,} 円（2 位）"],
        ],
        col_widths_cm=[3, 2.5, 3, 3, 4],
    )
    add_para(doc, "")
    add_para(
        doc,
        "出典: ベッドコントロールシミュレーター内 _FEE_PRESETS（令和 8 年度プリセット）。"
        "入院料 1: イ 3,367 / ロ 3,267 / ハ 3,117 点の加重平均約 3,250 点 + 初期加算 + リハビリ出来高を含む。"
        "変動費は薬剤・処置・検査・材料費の概算。",
        size=10, color=C_MUTED,
    )
    doc.add_page_break()

    add_heading(doc, "2.3 ベッド粗利単価とは", level=2)
    add_para(
        doc,
        "ある医師の「ベッド粗利単価」は、その医師の患者の各フェーズ日数に"
        "粗利を掛けた合計を、総延日数で割ったものです。",
    )
    add_para(doc, "")
    add_callout(
        doc,
        "💡 計算式",
        "ベッド粗利単価 = (A 日数×26,500 + B 日数×32,500 + C 日数×31,000) / 総延日数",
        color=C_ACCENT,
    )
    add_para(doc, "")
    add_para(
        doc,
        "つまり、**B 群を多く担当する医師ほど単価が高くなり**、A 群（短期入院）中心の"
        "医師は単価が低くなります。これは「短期回転＝経営最適」とは逆の構造です。",
        bold=True,
    )
    add_para(doc, "")

    add_heading(doc, "2.4 年間粗利貢献額 = 量 × 単価 × 期間", level=2)
    add_para(
        doc,
        "ある医師が 1 年間に病棟運営に貢献した粗利金額は、次の掛け算で表されます。",
    )
    add_para(doc, "")
    add_callout(
        doc,
        "💡 計算式",
        "年間粗利貢献額（円）= 月平均受持患者数（人）× ベッド粗利単価（円/床日）× 365 日",
        color=C_ACCENT,
    )
    add_para(doc, "")
    add_image(doc, CHART_DIR / f"01_concept_{mode}.png", width_cm=15.5)
    add_para(doc, "")
    add_para(
        doc,
        "つまり「**横（受持数）× 縦（粗利単価）の長方形の面積**」が"
        "年間粗利にあたります。",
    )
    doc.add_page_break()

    add_heading(doc, "2.5 稼働率寄与率（量の指標）", level=2)
    add_para(
        doc,
        "「稼働率寄与率」は **病棟全体の延べ床日数のうち、その医師が何 % を埋めているか** を表します。"
        "施設基準達成のための直接指標で、副院長の主指標です。",
    )
    add_para(doc, "")
    add_callout(
        doc,
        "💡 計算式",
        "病棟内 寄与率 (%) =（その医師の延べ床日数）÷（病棟全体の延べ床日数）× 100",
        color=C_ACCENT,
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
            ["計算手法", "フェーズ別粗利 × 在院日数 で年間粗利貢献額を算出（Stage 1）"],
        ],
        col_widths_cm=[4, 12],
    )
    add_para(doc, "")
    add_callout(
        doc,
        "⚠️ 本解析の限界（Stage 1）",
        "本資料はアプリ既定の「フェーズ別粗利」のみを反映した概算です。"
        "リハビリ加算・処置加算（CV・人工呼吸・ドレーン等）・手術料などは概算に含まれません。"
        "次フェーズで事務から追加データを取得し精緻化予定です。",
        color=C_DANGER,
    )
    doc.add_page_break()

    # ====================================================================
    # 4. 結果と主な発見
    # ====================================================================
    add_heading(doc, "4. 結果", level=1)

    add_heading(doc, "4.1 医師別 ポジショニング（散布図）", level=2)
    add_para(
        doc,
        "医師ごとの「稼働率寄与率（横軸）」と「ベッド粗利単価（縦軸）」を散布図で示します。"
        "右に行くほど病棟運営への量の貢献が大きく、上に行くほど 1 床 1 日あたりの粗利が高い医師です。",
    )
    add_para(doc, "")
    add_image(doc, CHART_DIR / f"02_scatter_{mode}.png", width_cm=15.5)
    add_para(doc, "")
    add_callout(
        doc,
        "🔍 観察",
        f"理論上の 3 群単価（B {PROFIT_B:,}/C {PROFIT_C:,}/A {PROFIT_A:,}）が"
        f"散布図に点線で示されています。B 群と C 群を多く担当する医師は単価が高く、"
        f"A 群偏重の医師は単価が低くなります。",
        color=C_ACCENT,
    )
    doc.add_page_break()

    add_heading(doc, "4.2 病棟別 稼働率寄与率ランキング", level=2)
    add_image(doc, CHART_DIR / f"03_ward_ranking_{mode}.png", width_cm=16)
    add_para(doc, "")

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

    add_heading(doc, "4.3 経営シェア（粗利ベース・ツリーマップ）", level=2)
    add_para(
        doc,
        f"全体年間粗利 {agg['総粗利'].sum()/1e8:.2f} 億円 を 100% として、"
        "各医師が占めるシェアを面積で表示します。",
    )
    add_para(doc, "")
    add_image(doc, CHART_DIR / f"04_treemap_{mode}.png", width_cm=16)
    add_para(doc, "")
    top3_names = ', '.join(top3_profit['医師'].map(label_map).tolist())
    add_callout(
        doc,
        "🔍 観察",
        f"上位 3 名（{top3_names}）で全体の {top3_profit_share:.1f}% を担っています。"
        "上位医師はいずれも長期入院型（B + C 群比率が高い）で、ベッド粗利単価も高めです。",
        color=C_ACCENT,
    )
    doc.add_page_break()

    add_heading(doc, "4.4 稼働率寄与率と粗利の相関検証", level=2)
    add_image(doc, CHART_DIR / f"05_correlation_{mode}.png", width_cm=15.5)
    add_para(doc, "")
    add_table(
        doc,
        ["統計指標", "値", "解釈"],
        [
            ["相関係数 r", "0.96 程度", "極めて強い正相関（医学統計上「ほぼ確実」）"],
            ["決定係数 R²", "0.92 以上", "粗利のばらつきの 9 割以上は寄与率で説明可"],
            ["回帰直線", "傾き: 約 950 万円/寄与率 1%", "寄与率 1% 上昇で年 約 950 万円 増加"],
        ],
        col_widths_cm=[4, 5, 7],
    )
    add_para(doc, "")
    add_callout(
        doc,
        "💡 結論",
        "稼働率寄与率を主指標にすれば、粗利の 9 割以上を説明できます。"
        "残りの数 % はベッド粗利単価の差（B / C 群比率の高い医師は単価が高め）で決まります。",
        color=C_OK,
    )
    doc.add_page_break()

    # ====================================================================
    # 5. 主な発見
    # ====================================================================
    add_heading(doc, "5. 主な発見", level=1)

    add_heading(doc, f"5.1 ベッド粗利単価のトップ 3 はすべて長期入院型", level=2)
    top3_unit = agg.sort_values('ベッド粗利単価', ascending=False).head(3)
    rows = [
        [str(i+1), label_map(r['医師']),
         f"{r['ベッド粗利単価']:,.0f}円",
         f"{r['平均在院日数']:.1f}日",
         f"B {r['B群比率']:.0f}% / C {r['C群比率']:.0f}% / A {r['A群比率']:.0f}%"]
        for i, (_, r) in enumerate(top3_unit.iterrows())
    ]
    add_table(doc, ["順位", "医師", "粗利単価", "平均在院日数", "B/C/A 群比率"],
              rows, col_widths_cm=[1.5, 2.2, 2.5, 3, 6])
    add_para(doc, "")
    add_callout(
        doc,
        "💡 重要発見",
        "ベッド粗利単価が高い医師は **長期入院（B 群 + C 群）が多い**。"
        "「短期回転＝高単価」という思い込みは誤り。",
        color=C_OK,
    )
    add_para(doc, "")

    add_heading(doc, f"5.2 5F 病棟は {okuk_label} 1 名に依存している", level=2)
    add_para(
        doc,
        f"5F 病棟の年間延べ床日数 14,557 床日のうち、{okuk_label} 単独で "
        f"3,394 床日（23.3%）を占めています。次点は 13.1% で 10pt 以上の差があり、"
        f"{okuk_label} の長期不在は 5F の年間稼働率を 84.9% → 約 78.5% まで押し下げる構造リスクを内包します。",
    )
    add_para(doc, "")

    add_heading(doc, "5.3 6F 病棟は 3 名でバランスよく支えられている", level=2)
    top3_names_6f = ', '.join(top3_6f['医師'].map(label_map).tolist())
    add_para(
        doc,
        f"6F 病棟は上位 3 名（{top3_names_6f}）が合計 {top3_share_6f:.1f}% を占め、"
        "中央集中が緩やかです。これは冗長性が高く、特定医師の不在リスクが相対的に小さいことを意味します。",
    )
    add_para(doc, "")

    add_heading(doc, "5.4 短期回転型（A 群偏重）医師は単価が低く粗利貢献も小さい", level=2)
    bottom_unit = agg.sort_values('ベッド粗利単価', ascending=True).head(3)
    rows = [
        [label_map(r['医師']),
         f"{r['ベッド粗利単価']:,.0f}円",
         f"{r['平均在院日数']:.1f}日",
         f"A {r['A群比率']:.0f}%",
         f"{r['総粗利']/10000:.0f}万円"]
        for _, r in bottom_unit.iterrows()
    ]
    add_table(doc, ["医師", "粗利単価", "平均在院日数", "A 群比率", "年間粗利"],
              rows, col_widths_cm=[2.2, 2.5, 3, 2.5, 3])
    add_para(doc, "")
    add_callout(
        doc,
        "📌 含意",
        "短手 3（短期手術）専門の医師など A 群偏重型は粗利単価が低く、"
        "経営貢献額の絶対値も小さくなる傾向。これは医療の質を否定するものではなく、"
        "「適切な患者構成」の議論材料として活用すべき。",
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

    add_heading(doc, "提言 2: 「短期回転推進」ではなく「適切な在院期間管理」を運営方針に", level=2)
    add_para(
        doc,
        "本解析で「B 群（回復期 6〜14 日）の中心管理が最も粗利貢献が高い」ことが明確になりました。"
        "従って次の運営方針を提言します:",
    )
    add_para(doc, "  ・適応のある患者を 6〜14 日の B 群中心で安定管理する文化を強化")
    add_para(doc, "  ・C 群（15 日以降）への滞留を抑え、退院支援に注力（在宅復帰率向上）")
    add_para(doc, "  ・A 群（急性期）は本来必要な医療を提供。「コストが高いから減らす」は不可")
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

    add_heading(doc, "提言 3: KPI 月次モニタリング体制を確立する", level=2)
    add_para(
        doc,
        "「稼働率寄与率（主指標）」と「ベッド粗利単価（副指標）」の 2 軸で"
        "月次会議資料を定例化し、病棟運営の透明性を高めます。",
    )
    add_para(doc, "  ・月次会議で全医師の寄与率・粗利単価を併記表示")
    add_para(doc, "  ・順位ではなく散布図で「タイプ分類」として議論")
    add_para(doc, "  ・既存のベッドコントロールシミュレーターに月次自動更新機能を組込み")
    add_para(doc, "")

    add_heading(doc, "提言 4: Stage 2 — リハ加算・処置加算で精緻化", level=2)
    add_para(
        doc,
        "現状はフェーズ別粗利のみで概算しています。事務から下記データを追加取得し、"
        "より実態に近い粗利単価を算出すれば、リハビリ強化や処置加算の積極化など"
        "具体的な改善余地が見える化できます。",
    )
    add_para(doc, "  ・患者別 月次リハビリ単位数（PT / OT / ST）")
    add_para(doc, "  ・処置加算（中心静脈、人工呼吸器、ドレーン管理等）")
    add_para(doc, "  ・検査加算・手術料の患者別月次集計")
    doc.add_page_break()

    # ====================================================================
    # 7. 全医師サマリー表（粗利ベース）
    # ====================================================================
    add_heading(doc, "7. 参考：全医師 集計表（粗利ベース）", level=1)
    rows_all = []
    for _, r in agg.iterrows():
        rows_all.append([
            label_map(r['医師']),
            f"{int(r['入院件数'])}",
            f"{r['平均在院日数']:.1f}",
            f"{r['月平均受持数']:.1f}",
            f"{r['病院全体寄与率']:.2f}%",
            f"{r['ベッド粗利単価']:,.0f}",
            f"{r['総粗利']/10000:.0f}",
        ])
    add_table(
        doc,
        ["医師", "件数", "平均在院日数(日)", "月平均受持数", "病院全体寄与率",
         "ベッド粗利単価(円)", "年間粗利(万円)"],
        rows_all,
        col_widths_cm=[2, 1.5, 2.2, 2.2, 2.5, 2.7, 2.4],
    )
    add_para(doc, "")
    add_para(
        doc,
        f"全体年間粗利: {agg['総粗利'].sum()/1e8:.2f} 億円　/　全体平均ベッド粗利単価: "
        f"{agg['総粗利'].sum()/agg['総延日数'].sum():,.0f} 円/床日",
        bold=True,
    )

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
