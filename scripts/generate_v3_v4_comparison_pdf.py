"""v3.5 vs v4.0 比較表 PDF 生成スクリプト

reportlab で日本語対応の PDF を生成。
日本語フォントは Hiragino Sans (macOS 標準) を使用。
"""
import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

# ---------------------------------------------------------------------------
# 日本語フォント設定
# ---------------------------------------------------------------------------
# 組み込みCID日本語フォント（追加インストール不要）
pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
JP_FONT = "HeiseiKakuGo-W5"

# ---------------------------------------------------------------------------
# スタイル定義
# ---------------------------------------------------------------------------
styles = getSampleStyleSheet()

title_style = ParagraphStyle(
    "TitleJP", parent=styles["Title"], fontName=JP_FONT,
    fontSize=18, leading=24, spaceAfter=12, alignment=1,
)
h1_style = ParagraphStyle(
    "H1JP", parent=styles["Heading1"], fontName=JP_FONT,
    fontSize=14, leading=18, spaceBefore=14, spaceAfter=8,
    textColor=colors.HexColor("#1E40AF"),
)
h2_style = ParagraphStyle(
    "H2JP", parent=styles["Heading2"], fontName=JP_FONT,
    fontSize=12, leading=16, spaceBefore=10, spaceAfter=6,
    textColor=colors.HexColor("#3B82F6"),
)
body_style = ParagraphStyle(
    "BodyJP", parent=styles["BodyText"], fontName=JP_FONT,
    fontSize=9, leading=13, spaceAfter=4,
)
caption_style = ParagraphStyle(
    "CaptionJP", parent=styles["BodyText"], fontName=JP_FONT,
    fontSize=8, leading=11, textColor=colors.HexColor("#6B7280"),
    spaceAfter=4,
)

# ---------------------------------------------------------------------------
# 表ユーティリティ
# ---------------------------------------------------------------------------

def make_table(data, col_widths=None, header_bg="#1E40AF", body_size=8, header_size=9):
    """表を作る。data は2D list（行頭が header）。"""
    # セルを Paragraph に変換（自動折り返し）
    cell_style = ParagraphStyle(
        "CellJP", fontName=JP_FONT, fontSize=body_size, leading=body_size + 2,
        textColor=colors.black,
    )
    header_style = ParagraphStyle(
        "HeaderJP", fontName=JP_FONT, fontSize=header_size, leading=header_size + 2,
        textColor=colors.white, alignment=1,
    )

    wrapped = []
    for r, row in enumerate(data):
        wrapped_row = []
        for cell in row:
            text = str(cell) if cell is not None else ""
            if r == 0:
                wrapped_row.append(Paragraph(text, header_style))
            else:
                wrapped_row.append(Paragraph(text, cell_style))
        wrapped.append(wrapped_row)

    t = Table(wrapped, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_bg)),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9CA3AF")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#F3F4F6")]),
    ]))
    return t

# ---------------------------------------------------------------------------
# コンテンツ
# ---------------------------------------------------------------------------

def build_content():
    story = []
    story.append(Paragraph("ベッドコントロールアプリ v3.5 vs v4.0 機能比較", title_style))
    story.append(Paragraph("現場が必要な機能を v4 に追加するための整理資料", caption_style))
    story.append(Paragraph("作成日: 2026-04-15 / 副院長 久保田 徹", caption_style))
    story.append(Spacer(1, 6))

    # ============================================================
    # 1. 設計思想の違い
    # ============================================================
    story.append(Paragraph("1. 設計思想の違い（最重要）", h1_style))

    data1 = [
        ["観点", "v3.5（現行）", "v4.0（新設計）"],
        ["ビジョン", "精神論を、数字に変える", "数字だけを、最小限に並べる"],
        ["対象ユーザー", "全職員（初心者にも親切）", "ベテランの主任・師長"],
        ["判断支援",
         "アクション提案型<br/>（「今日の一手」「結論カード」）",
         "数値提示型<br/>（差分のみ表示）"],
        ["画面の情報量",
         "多い<br/>（複数 KPI + アラート + アクションカード + ヒント）",
         "最小（5指標のみ）"],
        ["アプリ規模", "9,332行", "<b>211行</b>（メイン）+ 955行（タブ）= 1,166行"],
        ["タブ数", "セクション5×タブ平均3 = 約15画面", "<b>5タブのみ</b>"],
    ]
    story.append(make_table(data1, col_widths=[35*mm, 65*mm, 75*mm]))

    # ============================================================
    # 2. タブ構成
    # ============================================================
    story.append(Paragraph("2. タブ構成の対応関係", h1_style))

    data2 = [
        ["v4 タブ", "v3 の対応箇所", "主な機能"],
        ["📊 メイン", "ダッシュボード「本日の病床状況」+ 結論カード", "5指標を1画面表示"],
        ["🔍 詳細分析", "意思決定支援タブ群 + 改善のヒント", "C群候補・What-If・医師別・週末分析"],
        ["📋 制度確認", "制度管理タブ「制度・需要・C群」", "施設基準の月次レビュー"],
        ["📝 データ入力", "データ管理「日次データ入力」", "CSV取込 + 手動入力"],
        ["⚙ 設定", "データ管理「データエクスポート」「HOPE連携」", "HOPE・シナリオ・エクスポート"],
    ]
    story.append(make_table(data2, col_widths=[30*mm, 70*mm, 75*mm]))

    # ============================================================
    # 3. メイン画面の指標
    # ============================================================
    story.append(Paragraph("3. メイン画面で表示される指標", h1_style))

    data3 = [
        ["#", "指標", "v3.5 表示", "v4.0 表示"],
        ["1", "稼働率",
         "ゲージ + 月平均 + 結論カード判定 + アクション提案",
         "数値 + 目標との差分のみ"],
        ["2", "平均在院日数",
         "rolling 90日 + 短手3除外後 + 余力日数 + 警告",
         "数値 + 上限との差分のみ"],
        ["3", "救急搬送比率",
         "当月累計 + 残り必要件数 + 到達確度判定",
         "数値 + 基準15%との差分のみ"],
        ["4", "C群",
         "数 + 内訳 + 推奨アクション + What-If リンク",
         "人数 + 30日超 N名のみ"],
        ["5", "週末稼働率低下",
         "金曜退院集中率 + コスト換算 + 改善提案",
         "差分 % + 金曜集中率のみ"],
    ]
    story.append(make_table(data3, col_widths=[8*mm, 25*mm, 75*mm, 65*mm]))

    story.append(PageBreak())

    # ============================================================
    # 4. ✅ v4 に既に実装済み
    # ============================================================
    story.append(Paragraph("4. v4 に既に実装済みの機能（Phase 1〜4 完了）", h1_style))

    data4 = [
        ["機能", "v3", "v4", "状態・備考"],
        ["5指標表示（メイン）", "✓", "✓", "完了"],
        ["病棟切替（全体/5F/6F）", "✓", "✓", "完了"],
        ["C群候補一覧", "✓", "✓", "完了"],
        ["What-If（退院前倒し/後ろ倒し）", "✓", "△", "v3 は充填確率付き、v4 はシンプル版"],
        ["医師別分析", "✓", "△", "v3 は詳細、v4 はテーブルのみ"],
        ["週末分析", "✓", "✓", "コスト分離パネル同等"],
        ["施設基準チェック", "✓", "✓", "完了"],
        ["日次データ入力", "✓", "△", "v3 は統合フォーム、v4 はシンプル"],
        ["CSV インポート/エクスポート", "✓", "✓", "完了"],
        ["HOPE 連携", "✓", "✓", "既存モジュール再利用"],
        ["シナリオ管理", "✓", "✓", "完了"],
    ]
    story.append(make_table(data4, col_widths=[55*mm, 12*mm, 12*mm, 95*mm]))

    # ============================================================
    # 5. ❌ v3 にあって v4 にまだ無い機能
    # ============================================================
    story.append(Paragraph("5. v3 にあって v4 にまだ無い機能（要追加検討）", h1_style))

    data5 = [
        ["機能", "優先度", "備考"],
        ["結論カード（今日の一手）", "—",
         "設計思想上 <b>追加しない</b>方針<br/>ベテラン向けには不要"],
        ["KPI 優先順位リスト", "—", "同上"],
        ["翌診療日朝の受入余力", "🟡 中", "朝のブリーフィングで使う重要指標"],
        ["入退院セット調整 What-If（充填確率付き）", "🟡 中", "週末空床の改善試算"],
        ["短手3 包括点数の収益分離", "🟡 中", "経営分析タブで使用"],
        ["rolling LOS の短手3 除外併記", "<b>🔴 高</b>",
         "<b>2026年改定対応に必須</b>"],
        ["救急搬送比率 official/operational 2系統", "<b>🔴 高</b>",
         "<b>同上</b>"],
        ["詳細な医師別分析（金曜退院偏り検出）", "🟡 中", "改善のヒント機能"],
        ["デモ専用シナリオ（プレゼン用）", "🟢 低",
         "デモには v3 を残す"],
        ["パスワード認証（データ改ざん防止）", "🟡 中", "院内LAN展開時に必要"],
        ["C群コントロール詳細（rolling, バケット）", "🟢 低", "—"],
        ["需要波分析（曜日パターン分類）", "🟢 低", "—"],
        ["教育用ヘルプ", "🟢 低",
         "v4 は最小限主義のため不要"],
        ["入退院統合フォーム（医師・経路・短手3 種類）", "<b>🔴 高</b>",
         "<b>v3 で苦労した重要機能</b>"],
        ["データベース永続化（SQLite）", "<b>🔴 高</b>",
         "<b>院内LAN運用に必須</b>"],
        ["ベッドマップ初期化UI", "🟢 低", "—"],
        ["削除ドロップダウン（病棟+日付）", "🟢 低", "—"],
    ]
    story.append(make_table(data5, col_widths=[80*mm, 22*mm, 72*mm]))

    story.append(PageBreak())

    # ============================================================
    # 6. v4 のみの強み
    # ============================================================
    story.append(Paragraph("6. v4 のみの強み", h1_style))

    data6 = [
        ["機能", "説明"],
        ["211行のメイン",
         "9,332行 → 211行で本質を実装。保守性が大幅向上"],
        ["タブ別ファイル分離",
         "tabs/main_tab.py, tabs/detail_tab.py 等で1機能1ファイル"],
        ["session_state 整理",
         "34キー6重複 → 8キーに圧縮"],
        ["判定ロジックなし",
         "アクション提案を一切しない清潔な数値表示"],
    ]
    story.append(make_table(data6, col_widths=[55*mm, 119*mm]))

    # ============================================================
    # 7. 移植の優先順位
    # ============================================================
    story.append(Paragraph("7. 現場が必要な機能の v4 への移植 優先順位案", h1_style))

    story.append(Paragraph("Phase A（優先度 高 / 必須）", h2_style))
    data7a = [
        ["#", "機能", "理由", "移植元"],
        ["1", "救急搬送比率<br/>official/operational 2系統",
         "2026年改定対応に必須<br/>短手3 を分母に含むかどうかで値が変わる",
         "emergency_ratio.py の<br/>既存ロジックを呼ぶだけ"],
        ["2", "rolling LOS の<br/>短手3 除外併記",
         "同上",
         "calculate_rolling_los() の<br/>rolling_los_ex_short3 を表示"],
        ["3", "入退院統合フォーム<br/>（医師・経路・短手3 種類）",
         "v3 で時間をかけて完成させた重要 UI<br/>退化させると現場で使えない",
         "tabs/data_input_tab.py を<br/>v3 の統合フォームで置き換え"],
        ["4", "データベース永続化<br/>（SQLite）",
         "院内LAN運用ではセッション保持<br/>できないと困る",
         "db_manager.py を再利用"],
    ]
    story.append(make_table(data7a, col_widths=[8*mm, 50*mm, 60*mm, 55*mm]))

    story.append(Paragraph("Phase B（中優先 / 運用で必要）", h2_style))
    data7b = [
        ["#", "機能", "理由"],
        ["5", "翌診療日朝の受入余力（推計）", "朝のブリーフィングで使う"],
        ["6", "入退院セット調整 What-If（充填確率付き）", "週末空床の改善試算"],
        ["7", "短手3 包括点数の収益分離", "経営分析の精度向上"],
        ["8", "詳細な医師別分析（金曜退院偏り）", "改善のヒント機能"],
        ["9", "パスワード認証", "データ改ざん防止"],
    ]
    story.append(make_table(data7b, col_widths=[8*mm, 80*mm, 86*mm]))

    story.append(Paragraph("Phase C（後回し可）", h2_style))
    data7c = [
        ["#", "機能"],
        ["10", "デモ専用シナリオ（プレゼン用 → v3 を残す方が良い）"],
        ["11", "C群コントロールの詳細（rolling, バケット遷移）"],
        ["12", "需要波分析（曜日パターン分類）"],
        ["13", "ベッドマップ初期化UI"],
        ["14", "教育用ヘルプ（v4 は最小限主義なので入れない方が良い）"],
    ]
    story.append(make_table(data7c, col_widths=[8*mm, 166*mm]))

    story.append(PageBreak())

    # ============================================================
    # 8. 推奨と並行運用戦略
    # ============================================================
    story.append(Paragraph("8. 推奨と並行運用戦略", h1_style))

    recommendation = """
現状 v4 はベテラン主任・師長向けの「シンプル監査ツール」としては完成度が高いですが、
現場で日々運用するには上記 Phase A の4機能が必須です。理由：<br/><br/>
• ① ② は <b>2026年改定への適合</b> に必須（これがないと施設基準判定が古いまま）<br/>
• ③ は v3 で1日かけて完成させた <b>入力UX の核心</b>。退化させると入力時間が倍になる<br/>
• ④ は <b>院内LAN運用</b> で必須（ブラウザを閉じたらデータが消えると使い物にならない）<br/><br/>
Phase B は <b>3ヶ月運用してから</b> 必要に応じて追加。Phase C は v3 を並行運用すれば不要です。
"""
    story.append(Paragraph(recommendation, body_style))

    story.append(Paragraph("並行運用の戦略", h2_style))

    data8 = [
        ["v3.5 = デモ・プレゼン用", "v4.0 = 現場の毎日運用ツール"],
        ["• 理事会向け<br/>"
         "• 「精神論を数字に」のストーリー<br/>"
         "• リッチな UI で初心者にも親切",
         "• 主任・師長が毎朝10秒で確認<br/>"
         "• 数字だけ、最小限<br/>"
         "• Phase A の4機能を追加して完成"],
    ]
    story.append(make_table(data8, col_widths=[87*mm, 87*mm], header_bg="#3B82F6"))

    story.append(Spacer(1, 8))
    final_msg = """
この方向で <b>v4 に Phase A の4機能を順次追加</b> すれば、
現場運用とプレゼン両方をカバーできます。
"""
    story.append(Paragraph(final_msg, body_style))

    return story

# ---------------------------------------------------------------------------
# 生成
# ---------------------------------------------------------------------------

def main():
    output_path = "docs/admin/bed_control_v3_v4_comparison.pdf"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=15*mm, bottomMargin=15*mm,
        title="ベッドコントロールアプリ v3.5 vs v4.0 機能比較",
        author="副院長 久保田 徹",
    )
    story = build_content()
    doc.build(story)
    print(f"PDF generated: {output_path}")
    print(f"File size: {os.path.getsize(output_path):,} bytes")

if __name__ == "__main__":
    main()
