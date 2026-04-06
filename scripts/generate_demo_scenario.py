#!/usr/bin/env python3
"""ベッドコントロールシミュレーター 幹部会議 実演シナリオ Word文書生成"""

from docx import Document
from docx.shared import Pt, Cm, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml
import os

OUTPUT = "/Users/torukubota/ai-management/docs/admin/bed_control_demo_scenario.docx"

doc = Document()

# --- Page setup ---
section = doc.sections[0]
section.page_width = Cm(21.0)
section.page_height = Cm(29.7)
section.top_margin = Cm(2.5)
section.bottom_margin = Cm(2.5)
section.left_margin = Cm(2.5)
section.right_margin = Cm(2.5)

# --- Font helpers ---
JP_FONT = "游ゴシック"
JP_FONT_FALLBACK = "Hiragino Sans"

def set_font(run, name=JP_FONT, size=Pt(11), color=None, bold=False):
    run.font.name = name
    run.font.size = size
    run.font.bold = bold
    r = run._element
    r.rPr.rFonts.set(qn('w:eastAsia'), name)
    if color:
        run.font.color.rgb = color

def add_paragraph_with_style(text, size=Pt(11), color=None, bold=False, align=None, space_after=Pt(6), space_before=Pt(0), font_name=JP_FONT):
    p = doc.add_paragraph()
    if align is not None:
        p.alignment = align
    pf = p.paragraph_format
    pf.space_after = space_after
    pf.space_before = space_before
    run = p.add_run(text)
    set_font(run, name=font_name, size=size, color=color, bold=bold)
    return p, run

def add_empty_line():
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.space_before = Pt(0)
    run = p.add_run("")
    run.font.size = Pt(6)

def add_separator():
    """Add a horizontal rule using bottom border on an empty paragraph."""
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(12)
    p.paragraph_format.space_before = Pt(12)
    pPr = p._element.get_or_add_pPr()
    pBdr = parse_xml(
        '<w:pBdr %s>'
        '  <w:bottom w:val="single" w:sz="6" w:space="1" w:color="AAAAAA"/>'
        '</w:pBdr>' % nsdecls('w')
    )
    pPr.append(pBdr)

def add_scene_heading(text):
    """Scene heading: 13pt, navy, bold, underline."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(8)
    run = p.add_run(text)
    set_font(run, size=Pt(13), color=RGBColor(0x1B, 0x4F, 0x72), bold=True)
    run.underline = True

def add_operation(text):
    """Operation line (▶): green, bold."""
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.space_before = Pt(4)
    run = p.add_run(text)
    set_font(run, size=Pt(11), color=RGBColor(0x1E, 0x84, 0x49), bold=True)

def add_serif(text, size=Pt(11), color=RGBColor(0x2C, 0x3E, 0x50), bold=False):
    """Serif line (speech): dark blue."""
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.left_indent = Cm(0.5)
    run = p.add_run(text)
    set_font(run, size=size, color=color, bold=bold)
    return p

def add_serif_with_highlight(parts):
    """Speech line with mixed formatting. parts = [(text, {kwargs}), ...]"""
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.left_indent = Cm(0.5)
    for text, kwargs in parts:
        run = p.add_run(text)
        size = kwargs.get('size', Pt(11))
        color = kwargs.get('color', RGBColor(0x2C, 0x3E, 0x50))
        bold = kwargs.get('bold', False)
        set_font(run, size=size, color=color, bold=bold)
    return p

# Color constants
NAVY = RGBColor(0x1B, 0x4F, 0x72)
GREY = RGBColor(0x66, 0x66, 0x66)
PURPLE = RGBColor(0x8E, 0x44, 0xAD)
GREEN = RGBColor(0x1E, 0x84, 0x49)
DARK_BLUE = RGBColor(0x2C, 0x3E, 0x50)
RED = RGBColor(0xE7, 0x4C, 0x3C)

# ===== TITLE =====
add_paragraph_with_style(
    "ベッドコントロールシミュレーター\n幹部会議 実演シナリオ（約15分）",
    size=Pt(16), color=NAVY, bold=True,
    align=WD_ALIGN_PARAGRAPH.CENTER, space_after=Pt(8), space_before=Pt(24)
)

add_paragraph_with_style(
    "2026年4月　副院長　久保田 徹",
    size=Pt(12), color=GREY,
    align=WD_ALIGN_PARAGRAPH.CENTER, space_after=Pt(8)
)

add_paragraph_with_style(
    "【改訂版 v2.0 — 平均在院日数クリア計画・稼働率ギャップ分析を追加】",
    size=Pt(11), color=PURPLE, bold=True,
    align=WD_ALIGN_PARAGRAPH.CENTER, space_after=Pt(16)
)

add_separator()

# ===== 事前準備 =====
add_paragraph_with_style("■ 事前準備", size=Pt(13), color=NAVY, bold=True, space_after=Pt(8))

# Table with light blue background
table = doc.add_table(rows=1, cols=1)
table.alignment = WD_TABLE_ALIGNMENT.CENTER
cell = table.cell(0, 0)
# Set light blue background
shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="DCE6F1" w:val="clear"/>')
cell._element.get_or_add_tcPr().append(shading)

# Set table width
tbl = table._tbl
tblPr = tbl.tblPr if tbl.tblPr is not None else parse_xml(f'<w:tblPr {nsdecls("w")}/>')
tblW = parse_xml(f'<w:tblW {nsdecls("w")} w:type="pct" w:w="5000"/>')
tblPr.append(tblW)

# Remove borders or set light ones
borders = parse_xml(
    '<w:tblBorders %s>'
    '  <w:top w:val="single" w:sz="4" w:color="8DB4E2"/>'
    '  <w:left w:val="single" w:sz="4" w:color="8DB4E2"/>'
    '  <w:bottom w:val="single" w:sz="4" w:color="8DB4E2"/>'
    '  <w:right w:val="single" w:sz="4" w:color="8DB4E2"/>'
    '</w:tblBorders>' % nsdecls('w')
)
tblPr.append(borders)

prep_items = [
    "会議室モニターにノートPCを接続し、ブラウザでアプリを開いておく",
    "サイドバーで「シミュレーション実行」を押し、データが表示された状態にしておく\n　→ 月の日数（経過日数）: 19、カレンダー月日数: 30 を確認",
    "病棟セレクターは「全体（94床）」にしておく",
    "診療報酬改定プリセット：2024年度（令和6年度）",
    "「85歳以上が20%以上（在院日数+1日緩和）」にチェック済み",
    "運営分析タブを開いた状態でスタート",
]

# Clear default paragraph
cell.paragraphs[0].clear()
for i, item in enumerate(prep_items):
    if i == 0:
        p = cell.paragraphs[0]
    else:
        p = cell.add_paragraph()
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.space_before = Pt(2)
    run = p.add_run(f"・{item}")
    set_font(run, size=Pt(11))

add_empty_line()

# Red bold point
p = doc.add_paragraph()
p.paragraph_format.space_after = Pt(12)
run = p.add_run("＊ポイント：「今日は4月19日、月の半ばです。残り11日で何ができるかをお見せします」から入る")
set_font(run, size=Pt(11), color=RED, bold=True)

add_separator()

# ===== Scene 1 =====
add_scene_heading("■ Scene 1　「今日は4月19日。あと11日で、いくら取り戻せますか？」　(2分)")

add_operation("▶ 運営分析タブの稼働率ギャップパネルを見せる")
add_serif("💬 画面をご覧ください。今日4月19日時点の成績表です。")
add_operation("▶ パネルを指しながら")

add_serif_with_highlight([
    ("💬 稼働率 ", {}),
    ("87.2%", {'color': RED, 'bold': True}),
    ("。目標の", {}),
    ("90%", {'color': RED, 'bold': True}),
    ("に対して", {}),
    ("マイナス2.8ポイント", {'color': RED, 'bold': True}),
    ("。これが今の私たちの現在地です。", {}),
])

add_serif_with_highlight([
    ("💬 この下に書いてあるのが大事です。「運営貢献額：実績 ", {}),
    ("4,389万円", {'color': RED, 'bold': True}),
    (" / 目標 ", {}),
    ("4,501万円", {'color': RED, 'bold': True}),
    ("（達成率 ", {}),
    ("97.5%", {'color': RED, 'bold': True}),
    ("）」「残り11日で現ペース継続時の未活用病床コスト：約", {}),
    ("598万円", {'color': RED, 'bold': True}),
    ("」", {}),
])

add_serif_with_highlight([
    ("💬 つまり、このまま何もしなければ、今月あと", {}),
    ("598万円", {'color': RED, 'bold': True}),
    ("が消えていく。逆に言えば、残り11日の動き方次第で、", {}),
    ("598万円", {'color': RED, 'bold': True}),
    ("を取り戻せる可能性がある。", {}),
])

add_operation("▶ 左サイドバーの「稼働率1%（≈1名の入院）の価値：年間1,046万円」を指す")

add_serif_with_highlight([
    ("💬 稼働率1%、つまりあと1名の入院で", {}),
    ("年間約1,000万円", {'color': RED, 'bold': True}),
    ("。常勤医師1名分の手取り年収に相当します。この数字を常に画面上に表示しています。感覚ではなく、金額で判断する文化をつくるためです。", {}),
])

add_separator()

# ===== Scene 2 =====
add_scene_heading("■ Scene 2　稼働率の波を「見る」— 週末の谷に隠れたコスト　(2分)")

add_operation("▶ 「日次推移」タブをクリック")
add_serif("💬 過去19日間の稼働率の推移です。黄色い帯が目標レンジの90〜95%。グレーの背景が土日。")
add_operation("▶ グラフの週末の谷を指しながら")
add_serif("💬 注目してほしいのは、この繰り返しのパターンです。金曜日に退院が集中して、土日に稼働率が落ちる。そして月曜に入院が入って回復する。毎週、同じ波形を繰り返しています。")

add_serif_with_highlight([
    ("💬 この「谷」の1つ1つが、空床コストです。空床1床は1日約", {}),
    ("3万4千円", {'color': RED, 'bold': True}),
    ("。週末に5床空けば、2日で", {}),
    ("34万円", {'color': RED, 'bold': True}),
    ("のロス。月4回で", {}),
    ("136万円", {'color': RED, 'bold': True}),
    ("。パターンが見えれば、対策が打てます。", {}),
])

add_serif("💬 退院の曜日を平準化する。木曜にも退院を入れる。それだけで谷が浅くなり、月間で数十万円の改善になります。")

add_separator()

# ===== Scene 3 =====
add_scene_heading("■ Scene 3　「平均在院日数 21.9日」— 算定基準を超えています　(3分)")

add_operation("▶ 「運営分析」タブに戻る")
add_operation("▶ 下段のメトリクスカード「平均在院日数 21.9日」の赤いdelta表示を見せる")

add_serif_with_highlight([
    ("💬 ここを見てください。平均在院日数 ", {}),
    ("21.9日", {'color': RED, 'bold': True}),
    ("。赤い矢印で「基準超過 ", {}),
    ("+0.9日", {'color': RED, 'bold': True}),
    ("」と出ています。", {}),
])

add_serif_with_highlight([
    ("💬 地域包括医療病棟の算定基準は、平均在院日数", {}),
    ("21日以内", {'color': RED, 'bold': True}),
    ("です。2026年改定では", {}),
    ("20日以内", {'color': RED, 'bold': True}),
    ("に短縮されますが、当院は85歳以上が20%を超えているため+1日の緩和措置で21日以内。いずれにしても、今の", {}),
    ("21.9日は超過", {'color': RED, 'bold': True}),
    ("しています。", {}),
])

add_operation("▶ その下の赤いアラートを見せる")

add_serif("💬 アプリが自動で検知して、赤いアラートを出しています。「施設基準を満たさなくなるリスク」と、具体的な4つの対策。C群——在院15日以上の患者さんから退院調整を進める必要があります。")

add_serif("💬 でも、「何人退院させればいいのか」が分からなければ動けません。その答えが、次のタブにあります。")

add_separator()

# ===== Scene 4 =====
add_scene_heading("■ Scene 4　クリア計画 —「C群からあと何名退院させれば基準クリアか」　(3分)")

# Highlight badge
p = doc.add_paragraph()
p.paragraph_format.space_after = Pt(8)
run = p.add_run("★ 本日のハイライト")
set_font(run, size=Pt(12), color=RED, bold=True)

add_operation("▶ 「運営改善アラート」タブをクリック")
add_operation("▶ 下にスクロールして「平均在院日数 21日以内クリア計画」を見せる")

add_serif("💬 これが今日のハイライトです。")

add_operation("▶ 赤いパネルを指しながら")

add_serif_with_highlight([
    ("💬 現状：平均在院日数 ", {}),
    ("21.9日", {'color': RED, 'bold': True}),
    ("、基準を", {}),
    ("+0.9日超過", {'color': RED, 'bold': True}),
    ("。このままのペースだと月末には約", {}),
    ("21.4日", {'color': RED, 'bold': True}),
    ("——基準超過が継続します。必要な対策：残り11日でC群から追加", {}),
    ("3名", {'color': RED, 'bold': True}),
    ("の退院で基準クリア見込み。", {}),
])

add_serif_with_highlight([
    ("💬 「", {}),
    ("3名", {'color': RED, 'bold': True}),
    ("」。この数字があるだけで、行動が変わります。漠然と「在院日数を短くしましょう」ではなく、「C群から3名、今週中に退院調整を進めましょう」と具体的に動ける。", {}),
])

add_operation("▶ 左側のシミュレーションテーブルを見せる")

add_serif_with_highlight([
    ("💬 ここに退院計画シミュレーションがあります。C群追加退院0名なら", {}),
    ("21.4日で超過", {'color': RED, 'bold': True}),
    ("、2名なら", {}),
    ("21.1日でまだ超過", {'color': RED, 'bold': True}),
    ("、3名退院させると", {}),
    ("21.0日でクリア", {'color': RGBColor(0x1E, 0x84, 0x49), 'bold': True}),
    ("。", {}),
])

add_serif("💬 数字の根拠があるから、連携室にも「あと3名の退院先確保をお願いします」と明確に依頼できます。看護師長にも「C群の中で退院可能な方を3名リストアップしてください」と具体的に相談できます。")

add_operation("▶ 右側の「退院候補の優先順位」を見せる")

add_serif("💬 在院日数の長い方から順に退院調整。同時に新規入院の受入れも有効です。分母が増えれば平均在院日数は下がります。入院を創出してくださる先生方の貢献が、ここでも活きてきます。")

add_separator()

# ===== Scene 5 =====
add_scene_heading("■ Scene 5　病棟別に見る — 5Fと6Fでは課題が違う　(2分)")

add_operation("▶ 病棟セレクターで「5F（47床）」に切り替える")

add_serif_with_highlight([
    ("💬 5Fに切り替えます。稼働率が", {}),
    ("80%台", {'color': RED, 'bold': True}),
    ("で推移していて、空床が多い。5Fの課題は「入院を増やすこと」です。", {}),
])

add_operation("▶ 病棟セレクターで「6F（47床）」に切り替える")

add_serif_with_highlight([
    ("💬 一方、6Fは", {}),
    ("95%以上", {'color': RED, 'bold': True}),
    ("で推移。ほぼ満床です。6Fの課題は「長期入院の方の退院調整」です。", {}),
])

add_serif("💬 同じ病院の中でも、病棟ごとに打つべき手が違う。それが一目で分かるのが、このアプリの強みです。")

add_operation("▶ 「全体（94床）」に戻す")

add_separator()

# ===== Scene 6 =====
add_scene_heading("■ Scene 6　2026年度改定への備え　(1分)")

add_operation("▶ サイドバーの「診療報酬改定プリセット」を「2026年度（令和8年度）」に切り替える")

add_serif("💬 2026年度の診療報酬改定にも対応しています。プリセットを切り替えるだけで、入院料1のイ・ロ・ハ区分に基づく新しい報酬で自動再計算されます。")

add_operation("▶ サイドバーの「平均在院日数上限: 21日以内（通常20日+1日緩和）」を指す")

add_serif_with_highlight([
    ("💬 注目してほしいのはここです。2026年改定では基準が", {}),
    ("20日", {'color': RED, 'bold': True}),
    ("に短縮されます。ただし当院は85歳以上の割合が20%を超えているため、+1日の緩和で", {}),
    ("21日以内", {'color': RED, 'bold': True}),
    ("。このチェックボックス一つで切り替えられます。改定前後の影響を事前にシミュレーションして、今から準備できます。", {}),
])

add_separator()

# ===== Scene 7 =====
add_scene_heading("■ Scene 7　まとめ —「見える」が「動ける」に変わる　(2分)")

add_serif("💬 今日お見せしたことをまとめます。")
add_empty_line()
add_serif("💬 1つ目。稼働率の現在地と、残り日数でいくら取り戻せるかが分かる。")
add_serif("💬 2つ目。平均在院日数が基準を超えそうなとき、「C群からあと何名」と具体的に分かる。")
add_serif("💬 3つ目。病棟ごとに課題が違うことが一目で分かり、的確に手が打てる。")
add_empty_line()
add_serif("💬 このアプリに必要なのは、毎日5分のデータ入力だけです。電子カルテとの連携なし。追加コストゼロ。")
add_empty_line()

# Special emphasized paragraphs (12pt, navy)
add_serif(
    "💬 入院を創出してくださる先生方。外来で患者さんを診て、「この方は入院が必要だ」と判断してくださるその一つひとつの意思決定が、年間1,000万円の価値を生んでいます。このアプリは、その貢献を数字で可視化します。",
    size=Pt(12), color=NAVY, bold=False
)

add_serif(
    "💬 そして病棟で患者さんを受けてくださる看護スタッフの皆さん。「また入院が来た」「ベッドが足りない」——そう感じる日もあるでしょう。でもこのデータが示しているのは、皆さんが1名を受けるたびに、病院に年間1,000万円の価値が生まれているということです。皆さんの頑張りは、ちゃんと数字に表れています。",
    size=Pt(12), color=NAVY, bold=False
)

add_empty_line()

add_serif("💬 目的は、誰かを責めることではありません。「見えなかったものを見えるようにする」こと。見えれば、自分で考えて、自分で動ける。そういう文化を、このアプリで一緒につくっていきたいと思います。")

add_serif("💬 まずは1ヶ月、試してみませんか。ご質問はありますか？")

add_separator()

# ===== Q&A =====
add_paragraph_with_style("■ 想定Q&A", size=Pt(13), color=NAVY, bold=True, space_after=Pt(12))

qa_pairs = [
    ("Q. データ入力の手間はどのくらいか？",
     "A. 1日5分程度です。入院数・退院数・在院患者数をプルダウンと数字で入力するだけです。"),
    ("Q. 平均在院日数の「C群から3名」はどうやって計算しているのか？",
     "A. 厚労省公式の平均在院日数（在院患者延日数÷半回転数）を使い、残り日数での入退院ペースを現ペースで推計した上で、C群退院の追加による在院患者延日数の減少と退院数の増加を反映しています。退院が早いほど効果が大きいため、退院1名あたり残り日数の6割分の患者日数を節約する前提です。"),
    ("Q. 数字の精度は信頼できるのか？",
     "A. 診療報酬のイ/ロ/ハ区分による誤差は±8%程度です。「稼働率を上げるべきか」「退院の偏りを減らすべきか」という方向性の判断には影響しません。カーナビの到着予想時刻のようなもので、30分か3時間かの判断には十分な精度です。"),
    ("Q. 効果が出なかったらどうなるか？",
     "A. 導入コストがゼロですので、金銭的な損失はありません。むしろ、PoCで得られた稼働データ自体が今後の病棟運営判断に活用できます。「やってみて損はない」のが最大の強みです。"),
    ("Q. 個人の評価に使われないか？",
     "A. 使いません。このツールは病棟全体の傾向を把握し、改善の方向性を示すものです。将来的に医師別分析機能もありますが、目的は個人攻撃ではなく、貢献の可視化とフィードバックです。"),
    ("Q. 2026年改定で平均在院日数が20日になったらどうするのか？",
     "A. アプリのプリセットを切り替えるだけで対応できます。当院は85歳以上が20%を超えているため+1日の緩和で21日以内ですが、もし患者構成が変わった場合はチェックボックスを外せば20日基準に切り替わります。今から改定後の影響をシミュレーションして備えることが重要です。"),
]

for q, a in qa_pairs:
    # Question: bold, navy
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.space_before = Pt(8)
    run = p.add_run(q)
    set_font(run, size=Pt(11), color=NAVY, bold=True)

    # Answer: normal
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(8)
    p.paragraph_format.left_indent = Cm(0.5)
    run = p.add_run(a)
    set_font(run, size=Pt(11))

# --- Set default font for document ---
style = doc.styles['Normal']
font = style.font
font.name = JP_FONT
font.size = Pt(11)
style.element.rPr.rFonts.set(qn('w:eastAsia'), JP_FONT)

doc.save(OUTPUT)
print(f"Saved: {OUTPUT}")
