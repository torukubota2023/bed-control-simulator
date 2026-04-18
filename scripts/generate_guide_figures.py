#!/usr/bin/env python3
"""
院内アプリ開発ガイド用の図を生成するスクリプト。
全7図をPNGファイルとして保存する。
"""

import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle
import matplotlib.patheffects as pe
import numpy as np

# --- フォント設定 ---
def setup_font():
    """日本語フォントを設定する。Hiragino Sans優先、なければAppleGothic。"""
    import matplotlib.font_manager as fm
    available = [f.name for f in fm.fontManager.ttflist]
    if 'Hiragino Sans' in available:
        font_name = 'Hiragino Sans'
    elif 'AppleGothic' in available:
        font_name = 'AppleGothic'
    else:
        font_name = 'sans-serif'
    plt.rcParams['font.family'] = font_name
    plt.rcParams['axes.unicode_minus'] = False
    return font_name

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'docs', 'admin', 'figures')


# ============================================================
# 図1: 7ステップ全体フロー図
# ============================================================
def fig1_seven_steps():
    fig, ax = plt.subplots(figsize=(14, 5), dpi=150)
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 5)
    ax.axis('off')
    fig.patch.set_facecolor('white')

    steps = [
        ('1', '課題発見', '#D6EAF8'),
        ('2', 'AI開発', '#D5F5E3'),
        ('3', 'デモ公開', '#FEF9E7'),
        ('4', '協力依頼', '#FDEBD0'),
        ('5', '会議提案', '#FDEDEC'),
        ('6', 'PoC実施', '#E8DAEF'),
        ('7', '効果測定', '#F5B7B1'),
    ]
    durations = ['1-2日', '1-3日', '1日', '1-2日', '1日', '2-6週', '2-3週']

    box_w, box_h = 1.5, 1.4
    gap = 0.3
    start_x = 0.5
    y_center = 3.0

    for i, (num, name, color) in enumerate(steps):
        x = start_x + i * (box_w + gap)
        # 角丸四角形
        bbox = FancyBboxPatch(
            (x, y_center - box_h / 2), box_w, box_h,
            boxstyle="round,pad=0.1",
            facecolor=color, edgecolor='#AAAAAA', linewidth=1.2
        )
        ax.add_patch(bbox)
        # 番号
        ax.text(x + box_w / 2, y_center + 0.2, f'Step {num}',
                ha='center', va='center', fontsize=10, fontweight='bold', color='#333333')
        # 名称
        ax.text(x + box_w / 2, y_center - 0.25, name,
                ha='center', va='center', fontsize=11, fontweight='bold', color='#333333')
        # 所要期間
        ax.text(x + box_w / 2, y_center - box_h / 2 - 0.3, durations[i],
                ha='center', va='center', fontsize=8, color='#777777')
        # 矢印（次のステップへ）
        if i < len(steps) - 1:
            ax.annotate('', xy=(x + box_w + gap - 0.05, y_center),
                        xytext=(x + box_w + 0.05, y_center),
                        arrowprops=dict(arrowstyle='->', color='#888888', lw=1.5))

    # Step7 → Step1 の「横展開」点線矢印
    x_last = start_x + 6 * (box_w + gap) + box_w / 2
    x_first = start_x + box_w / 2
    y_bottom = y_center - box_h / 2 - 0.7

    ax.annotate('',
                xy=(x_first, y_center - box_h / 2 - 0.05),
                xytext=(x_last, y_center - box_h / 2 - 0.05),
                arrowprops=dict(arrowstyle='->', color='#E74C3C', lw=1.5,
                                linestyle='dashed', connectionstyle='arc3,rad=0.3'))
    ax.text((x_first + x_last) / 2, y_bottom - 0.15, '横展開（成功パターンの再適用）',
            ha='center', va='center', fontsize=9, color='#E74C3C', fontstyle='italic')

    # タイトル
    ax.text(7, 4.6, '院内アプリ開発 7ステップ', ha='center', va='center',
            fontsize=16, fontweight='bold', color='#2C3E50')

    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, 'guide_fig_7steps.png')
    fig.savefig(path, facecolor='white', bbox_inches='tight')
    plt.close(fig)
    print(f'  保存: {path}')


# ============================================================
# 図2: Claude Codeの使い方イメージ図
# ============================================================
def fig2_claude_code():
    fig, ax = plt.subplots(figsize=(14, 4), dpi=150)
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 4)
    ax.axis('off')
    fig.patch.set_facecolor('white')

    panels = [
        {'x': 0.5, 'title': 'あなたが書くこと', 'color': '#D6EAF8', 'edge': '#85C1E9',
         'body': '「94床の病院で\n稼働率を可視化する\nアプリを作りたいです」', 'icon': '💬'},
        {'x': 5.0, 'title': 'AIがやること', 'color': '#D5F5E3', 'edge': '#82E0AA',
         'body': 'コード生成\n実行・デバッグ\nアプリ構築', 'icon': '⚙️'},
        {'x': 9.5, 'title': 'できあがるもの', 'color': '#FDEBD0', 'edge': '#F0B27A',
         'body': 'ブラウザで動く\nWebアプリ', 'icon': '🖥️'},
    ]

    pw, ph = 3.8, 2.8
    y0 = 0.4

    for i, p in enumerate(panels):
        # パネル背景
        bbox = FancyBboxPatch(
            (p['x'], y0), pw, ph,
            boxstyle="round,pad=0.15",
            facecolor=p['color'], edgecolor=p['edge'], linewidth=2
        )
        ax.add_patch(bbox)
        # タイトル
        ax.text(p['x'] + pw / 2, y0 + ph - 0.35, p['title'],
                ha='center', va='center', fontsize=12, fontweight='bold', color='#2C3E50')
        # 本文
        ax.text(p['x'] + pw / 2, y0 + ph / 2 - 0.15, p['body'],
                ha='center', va='center', fontsize=10, color='#333333', linespacing=1.5)

        # 矢印
        if i < 2:
            arrow_x = p['x'] + pw + 0.1
            ax.annotate('', xy=(arrow_x + 0.8, y0 + ph / 2),
                        xytext=(arrow_x, y0 + ph / 2),
                        arrowprops=dict(arrowstyle='->', color='#888888', lw=2))

    # タイトル
    ax.text(7, 3.7, 'Claude Code の使い方イメージ', ha='center', va='center',
            fontsize=15, fontweight='bold', color='#2C3E50')

    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, 'guide_fig_claude_code.png')
    fig.savefig(path, facecolor='white', bbox_inches='tight')
    plt.close(fig)
    print(f'  保存: {path}')


# ============================================================
# 図3: AIへの指示の5要素図
# ============================================================
def fig3_prompt_elements():
    fig, ax = plt.subplots(figsize=(8, 8), dpi=150)
    ax.set_xlim(-4, 4)
    ax.set_ylim(-4, 4)
    ax.set_aspect('equal')
    ax.axis('off')
    fig.patch.set_facecolor('white')

    # 中央円
    center_circle = plt.Circle((0, 0), 1.2, facecolor='#EBF5FB', edgecolor='#2980B9',
                                linewidth=2.5)
    ax.add_patch(center_circle)
    ax.text(0, 0.1, 'AIへの', ha='center', va='center', fontsize=13, fontweight='bold', color='#2C3E50')
    ax.text(0, -0.3, '指示', ha='center', va='center', fontsize=13, fontweight='bold', color='#2C3E50')

    elements = [
        ('背景\n（なぜ必要か）', '#D6EAF8', '#2980B9'),
        ('目的\n（何を実現するか）', '#D5F5E3', '#27AE60'),
        ('機能要件\n（何ができるか）', '#FEF9E7', '#F39C12'),
        ('制約\n（技術・運用の制限）', '#FDEDEC', '#E74C3C'),
        ('出力形式\n（どんな形か）', '#E8DAEF', '#8E44AD'),
    ]

    radius = 2.8
    angles = [90, 162, 234, 306, 18]  # 上から時計回り風に配置

    for i, (label, fcolor, ecolor) in enumerate(elements):
        angle_rad = np.radians(angles[i])
        cx = radius * np.cos(angle_rad)
        cy = radius * np.sin(angle_rad)

        # 楕円
        ellipse = mpatches.Ellipse((cx, cy), 2.4, 1.3,
                                    facecolor=fcolor, edgecolor=ecolor, linewidth=2)
        ax.add_patch(ellipse)
        ax.text(cx, cy, label, ha='center', va='center', fontsize=10,
                fontweight='bold', color='#2C3E50', linespacing=1.4)

        # 中央から楕円への線
        line_end_x = cx * (1.2 / radius)
        line_end_y = cy * (1.2 / radius)
        ellipse_start_x = cx - (cx - 0) * (1.1 / radius)
        ellipse_start_y = cy - (cy - 0) * (1.1 / radius)
        ax.plot([line_end_x * 1.1, ellipse_start_x], [line_end_y * 1.1, ellipse_start_y],
                color='#BBBBBB', linewidth=1.5, linestyle='-')

    # タイトル
    ax.text(0, 3.7, 'AIへの指示に含める5要素', ha='center', va='center',
            fontsize=15, fontweight='bold', color='#2C3E50')

    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, 'guide_fig_prompt_elements.png')
    fig.savefig(path, facecolor='white', bbox_inches='tight')
    plt.close(fig)
    print(f'  保存: {path}')


# ============================================================
# 図4: PoC 3フェーズ図
# ============================================================
def fig4_poc_phases():
    fig, ax = plt.subplots(figsize=(12, 4), dpi=150)
    fig.patch.set_facecolor('white')

    phases = [
        ('Phase 1: デモモード', 0, 2, '#D6EAF8', '#2980B9',
         '・模擬データで操作体験\n・フィードバック収集'),
        ('Phase 2: 実データ試行', 2, 3, '#D5F5E3', '#27AE60',
         '・実データ投入\n・運用フロー検証'),
        ('Phase 3: 効果測定', 5, 3, '#FDEBD0', '#E67E22',
         '・KPI比較（前後）\n・費用対効果の算出'),
    ]

    y_positions = [2.5, 1.5, 0.5]
    bar_height = 0.6

    for i, (label, start, duration, fcolor, ecolor, note) in enumerate(phases):
        y = y_positions[i]
        ax.barh(y, duration, left=start, height=bar_height,
                color=fcolor, edgecolor=ecolor, linewidth=1.5)
        # フェーズラベル（バーの中）
        ax.text(start + duration / 2, y, label,
                ha='center', va='center', fontsize=10, fontweight='bold', color='#2C3E50')
        # 注釈（バーの右側）
        ax.text(start + duration + 0.2, y, note,
                ha='left', va='center', fontsize=8, color='#555555', linespacing=1.4)

    ax.set_xlim(-0.5, 11)
    ax.set_ylim(0, 3.5)
    ax.set_xlabel('週', fontsize=10, color='#555555')

    # X軸の目盛り
    ax.set_xticks(range(0, 9))
    ax.set_xticklabels([f'{i}週' for i in range(0, 9)], fontsize=9, color='#555555')
    ax.set_yticks([])
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_visible(False)
    ax.spines['bottom'].set_color('#CCCCCC')

    # タイトル
    ax.set_title('PoC（概念実証）の3フェーズ', fontsize=14, fontweight='bold',
                 color='#2C3E50', pad=15)

    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, 'guide_fig_poc_phases.png')
    fig.savefig(path, facecolor='white', bbox_inches='tight')
    plt.close(fig)
    print(f'  保存: {path}')


# ============================================================
# 図5: As-Is / To-Be 概念図
# ============================================================
def fig5_asis_tobe():
    fig, ax = plt.subplots(figsize=(12, 5), dpi=150)
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 5)
    ax.axis('off')
    fig.patch.set_facecolor('white')

    # As-Is 枠
    asis_box = FancyBboxPatch((0.5, 0.8), 3.5, 3.2,
                               boxstyle="round,pad=0.15",
                               facecolor='#F2F3F4', edgecolor='#AAB7B8', linewidth=2)
    ax.add_patch(asis_box)
    ax.text(2.25, 3.7, '現状 (As-Is)', ha='center', va='center',
            fontsize=13, fontweight='bold', color='#7F8C8D')

    asis_items = ['属人化した判断', '紙・Excelで管理', '見えない損失']
    for i, item in enumerate(asis_items):
        y = 2.8 - i * 0.6
        ax.text(2.25, y, f'  {item}', ha='center', va='center',
                fontsize=10, color='#555555')

    # To-Be 枠
    tobe_box = FancyBboxPatch((8.0, 0.8), 3.5, 3.2,
                               boxstyle="round,pad=0.15",
                               facecolor='#D6EAF8', edgecolor='#5DADE2', linewidth=2)
    ax.add_patch(tobe_box)
    ax.text(9.75, 3.7, '理想 (To-Be)', ha='center', va='center',
            fontsize=13, fontweight='bold', color='#2471A3')

    tobe_items = ['データに基づく判断', 'アプリで一元管理', '損失の可視化']
    for i, item in enumerate(tobe_items):
        y = 2.8 - i * 0.6
        ax.text(9.75, y, f'  {item}', ha='center', va='center',
                fontsize=10, color='#2C3E50')

    # 中央矢印
    arrow = FancyBboxPatch((4.6, 1.6), 2.8, 1.5,
                            boxstyle="round,pad=0.1",
                            facecolor='#ABEBC6', edgecolor='#27AE60', linewidth=2)
    ax.add_patch(arrow)
    ax.text(6.0, 2.55, 'アプリで', ha='center', va='center',
            fontsize=12, fontweight='bold', color='#1E8449')
    ax.text(6.0, 2.1, '解決', ha='center', va='center',
            fontsize=12, fontweight='bold', color='#1E8449')

    # 矢印描画
    ax.annotate('', xy=(4.55, 2.35), xytext=(4.05, 2.35),
                arrowprops=dict(arrowstyle='<-', color='#27AE60', lw=2.5))
    ax.annotate('', xy=(7.95, 2.35), xytext=(7.45, 2.35),
                arrowprops=dict(arrowstyle='->', color='#27AE60', lw=2.5))

    # タイトル
    ax.text(6.0, 4.6, 'As-Is / To-Be 概念図', ha='center', va='center',
            fontsize=15, fontweight='bold', color='#2C3E50')

    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, 'guide_fig_asis_tobe.png')
    fig.savefig(path, facecolor='white', bbox_inches='tight')
    plt.close(fig)
    print(f'  保存: {path}')


# ============================================================
# 図6: 院内LAN共有の仕組み図
# ============================================================
def fig6_lan_sharing():
    fig, ax = plt.subplots(figsize=(10, 7), dpi=150)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 7)
    ax.set_aspect('equal')
    ax.axis('off')
    fig.patch.set_facecolor('white')

    # 院内LAN枠
    lan_box = FancyBboxPatch((0.5, 0.5), 9.0, 5.5,
                              boxstyle="round,pad=0.2",
                              facecolor='#FDFEFE', edgecolor='#5DADE2',
                              linewidth=2.5, linestyle='-')
    ax.add_patch(lan_box)
    ax.text(5.0, 5.7, '院内LAN', ha='center', va='center',
            fontsize=14, fontweight='bold', color='#2980B9',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='#5DADE2'))

    # 中央PC（アプリ実行PC）
    center_x, center_y = 5.0, 3.2
    center_box = FancyBboxPatch((center_x - 1.2, center_y - 0.6), 2.4, 1.2,
                                 boxstyle="round,pad=0.1",
                                 facecolor='#D5F5E3', edgecolor='#27AE60', linewidth=2)
    ax.add_patch(center_box)
    ax.text(center_x, center_y + 0.15, 'アプリ実行PC', ha='center', va='center',
            fontsize=10, fontweight='bold', color='#1E8449')
    ax.text(center_x, center_y - 0.25, '(Streamlitサーバー)', ha='center', va='center',
            fontsize=8, color='#555555')

    # 周辺PC
    clients = [
        (2.0, 4.8, 'ナースステーション'),
        (8.0, 4.8, '医事課'),
        (1.5, 1.5, '事務室'),
        (8.5, 1.5, '病棟PC'),
    ]

    for cx, cy, label in clients:
        client_box = FancyBboxPatch((cx - 1.0, cy - 0.45), 2.0, 0.9,
                                     boxstyle="round,pad=0.1",
                                     facecolor='#D6EAF8', edgecolor='#85C1E9', linewidth=1.5)
        ax.add_patch(client_box)
        ax.text(cx, cy + 0.08, label, ha='center', va='center',
                fontsize=9, fontweight='bold', color='#2C3E50')
        ax.text(cx, cy - 0.22, 'ブラウザ', ha='center', va='center',
                fontsize=7, color='#777777')

        # 接続線
        ax.annotate('', xy=(center_x + (cx - center_x) * 0.35,
                            center_y + (cy - center_y) * 0.35),
                    xytext=(cx - (cx - center_x) * 0.25,
                            cy - (cy - center_y) * 0.25),
                    arrowprops=dict(arrowstyle='<->', color='#AAAAAA', lw=1.2,
                                    linestyle='--'))

    # インターネット（外側、バツ印）
    inet_y = 6.5
    ax.text(5.0, inet_y, 'インターネット', ha='center', va='center',
            fontsize=11, color='#E74C3C',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#FDEDEC', edgecolor='#E74C3C'))

    # バツ印
    ax.plot([4.4, 4.7], [6.15, 6.0], color='#E74C3C', lw=3)
    ax.plot([4.4, 4.7], [6.0, 6.15], color='#E74C3C', lw=3)
    ax.text(5.0, 6.08, '外部接続なし', ha='center', va='center',
            fontsize=9, fontweight='bold', color='#E74C3C')
    ax.plot([5.3, 5.6], [6.15, 6.0], color='#E74C3C', lw=3)
    ax.plot([5.3, 5.6], [6.0, 6.15], color='#E74C3C', lw=3)

    # タイトル
    ax.text(5.0, 0.15, '※ 全通信は院内ネットワーク内で完結（患者情報は外部に出ません）',
            ha='center', va='center', fontsize=8, color='#777777', fontstyle='italic')

    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, 'guide_fig_lan_sharing.png')
    fig.savefig(path, facecolor='white', bbox_inches='tight')
    plt.close(fig)
    print(f'  保存: {path}')


# ============================================================
# 図7: 横展開イメージ図
# ============================================================
def fig7_expansion():
    fig, ax = plt.subplots(figsize=(10, 8), dpi=150)
    ax.set_xlim(-5, 5)
    ax.set_ylim(-5, 5)
    ax.set_aspect('equal')
    ax.axis('off')
    fig.patch.set_facecolor('white')

    # 中央の成功事例
    center_circle = plt.Circle((0, 0), 1.5, facecolor='#D5F5E3', edgecolor='#27AE60',
                                linewidth=2.5)
    ax.add_patch(center_circle)
    ax.text(0, 0.2, '成功事例', ha='center', va='center',
            fontsize=14, fontweight='bold', color='#1E8449')
    ax.text(0, -0.3, 'ベッドコントロール', ha='center', va='center',
            fontsize=10, color='#2C3E50')

    # 横展開候補
    expansions = [
        ('シフト最適化', '#D6EAF8', '#2980B9'),
        ('在庫管理', '#FEF9E7', '#F39C12'),
        ('患者満足度', '#FDEDEC', '#E74C3C'),
        ('感染対策', '#E8DAEF', '#8E44AD'),
        ('研修管理', '#FDEBD0', '#E67E22'),
    ]

    radius = 3.5
    for i, (label, fcolor, ecolor) in enumerate(expansions):
        angle = np.radians(90 + i * 72)
        cx = radius * np.cos(angle)
        cy = radius * np.sin(angle)

        ellipse = mpatches.Ellipse((cx, cy), 2.2, 1.2,
                                    facecolor=fcolor, edgecolor=ecolor, linewidth=2)
        ax.add_patch(ellipse)
        ax.text(cx, cy, label, ha='center', va='center',
                fontsize=11, fontweight='bold', color='#2C3E50')

        # 点線矢印
        dx = cx * (1.5 / radius)
        dy = cy * (1.5 / radius)
        sx = cx * (2.2 / radius)  # 楕円端付近
        sy = cy * (2.2 / radius)
        ax.annotate('', xy=(sx, sy),
                    xytext=(dx * 1.1, dy * 1.1),
                    arrowprops=dict(arrowstyle='->', color=ecolor, lw=1.5,
                                    linestyle='dashed'))

    # メッセージ
    ax.text(0, -4.5, '同じ手法（7ステップ）で横展開可能', ha='center', va='center',
            fontsize=13, fontweight='bold', color='#2C3E50',
            bbox=dict(boxstyle='round,pad=0.4', facecolor='#FCF3CF', edgecolor='#F4D03F',
                      linewidth=1.5))

    # タイトル
    ax.text(0, 4.6, '横展開イメージ', ha='center', va='center',
            fontsize=15, fontweight='bold', color='#2C3E50')

    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, 'guide_fig_expansion.png')
    fig.savefig(path, facecolor='white', bbox_inches='tight')
    plt.close(fig)
    print(f'  保存: {path}')


# ============================================================
# メイン
# ============================================================
if __name__ == '__main__':
    font = setup_font()
    print(f'使用フォント: {font}')
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f'出力先: {OUTPUT_DIR}\n')

    print('図1: 7ステップ全体フロー図')
    fig1_seven_steps()

    print('図2: Claude Codeの使い方イメージ図')
    fig2_claude_code()

    print('図3: AIへの指示の5要素図')
    fig3_prompt_elements()

    print('図4: PoC 3フェーズ図')
    fig4_poc_phases()

    print('図5: As-Is / To-Be 概念図')
    fig5_asis_tobe()

    print('図6: 院内LAN共有の仕組み図')
    fig6_lan_sharing()

    print('図7: 横展開イメージ図')
    fig7_expansion()

    print('\n全図の生成が完了しました。')
