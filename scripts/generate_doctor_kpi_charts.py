"""医師別 病棟貢献度 KPI チャート生成（粗利＝運営貢献額ベース、抜本改訂版）.

副院長指示 (2026-05-04):
  - 旧版は誤った数値（24000/13200/6400）を使用。これは出典不明・順序逆転。
  - 正しくは「報酬 - 変動費 = 粗利（運営貢献額）」で、順序は B > C > A。
  - 理事会・運営会議で「短期回転 = 経営最適」という誤った認識を修正する設計。

【抜本改訂のポイント】
  1. 単価を「報酬」ではなく「粗利（運営貢献額）」に統一
     → 出典: アプリ実装 _FEE_PRESETS の 2026 年度プリセット
     → A 群: 38,500 - 12,000 = 26,500 円/床日
     → B 群: 38,500 -  6,000 = 32,500 円/床日（最高）
     → C 群: 35,500 -  4,500 = 31,000 円/床日
  2. 「ベッド単価」という用語を「ベッド粗利単価（運営貢献額/床日）」に明示
  3. 概念図で「報酬・変動費・粗利」の 3 段表示
  4. 「短期回転＝経営貢献大」という誤認を覆す数値を強調

使い方:
  .venv/bin/python scripts/generate_doctor_kpi_charts.py --mode named
  .venv/bin/python scripts/generate_doctor_kpi_charts.py --mode anonymous
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
import squarify
from scipy import stats

matplotlib.rcParams['font.family'] = 'Hiragino Mincho ProN'
matplotlib.rcParams['axes.unicode_minus'] = False

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = REPO_ROOT / 'data' / 'past_admissions_2025fy.csv'
OUT_DIR = REPO_ROOT / 'docs' / 'admin' / 'figures' / 'doctor_kpi'
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ====================================================================
# 抜本改訂: 単価の出典を明示し、粗利（運営貢献額）で統一
# ====================================================================
# 出典: scripts/bed_control_simulator_app.py L1846-1853
# _FEE_PRESETS["2026年度（令和8年度）"] より:
#   A 群（1〜5 日）: 38,500 円報酬 - 12,000 円変動費 = 26,500 円粗利
#   B 群（6〜14 日）: 38,500 円報酬 -  6,000 円変動費 = 32,500 円粗利
#   C 群（15 日〜）: 35,500 円報酬 -  4,500 円変動費 = 31,000 円粗利
# 順序: B > C > A（副院長指摘 2026-05-04）
# ====================================================================
REV_A, REV_B, REV_C = 38500, 38500, 35500       # 日次診療報酬
COST_A, COST_B, COST_C = 12000, 6000, 4500       # 日次変動費
PROFIT_A = REV_A - COST_A   # 26,500 円
PROFIT_B = REV_B - COST_B   # 32,500 円（最高）
PROFIT_C = REV_C - COST_C   # 31,000 円

# 配色
COLOR_5F = '#3B82F6'
COLOR_6F = '#EC4899'
COLOR_ACCENT = '#374151'
COLOR_GREEN = '#10B981'
COLOR_RED = '#DC2626'
COLOR_GOLD = '#D97706'
COLOR_BLUE = '#2563EB'
COLOR_PHASE_A = '#FECACA'  # 薄赤（コスト高い）
COLOR_PHASE_B = '#BBF7D0'  # 薄緑（粗利最高 ★）
COLOR_PHASE_C = '#FDE08A'  # 薄黄（粗利中）


def phase_breakdown(d):
    return min(d, 5), min(max(d - 5, 0), 9), max(d - 14, 0)


def profit_per_admission(d):
    """各入院の粗利（運営貢献額）を計算"""
    a, b, c = phase_breakdown(d)
    return a * PROFIT_A + b * PROFIT_B + c * PROFIT_C


def load_and_compute():
    df = pd.read_csv(DATA_PATH)
    df[['A_days', 'B_days', 'C_days']] = df['日数'].apply(
        lambda x: pd.Series(phase_breakdown(x))
    )
    df['粗利貢献額'] = df['日数'].apply(profit_per_admission)

    crosstab = df.groupby(['医師', '病棟'])['日数'].sum().unstack(fill_value=0)
    crosstab.columns.name = None
    ward_total_days = df.groupby('病棟')['日数'].sum().to_dict()

    agg = df.groupby('医師').agg(
        入院件数=('患者番号', 'count'),
        総延日数=('日数', 'sum'),
        総粗利=('粗利貢献額', 'sum'),
        A群延日数=('A_days', 'sum'),
        B群延日数=('B_days', 'sum'),
        C群延日数=('C_days', 'sum'),
    ).reset_index()
    agg['月平均受持数'] = agg['総延日数'] / 365
    agg['ベッド粗利単価'] = agg['総粗利'] / agg['総延日数']
    agg['平均在院日数'] = agg['総延日数'] / agg['入院件数']
    agg['A群比率'] = agg['A群延日数'] / agg['総延日数'] * 100
    agg['B群比率'] = agg['B群延日数'] / agg['総延日数'] * 100
    agg['C群比率'] = agg['C群延日数'] / agg['総延日数'] * 100
    total_hospital_days = df['日数'].sum()
    agg['病院全体寄与率'] = agg['総延日数'] / total_hospital_days * 100

    for w in ['5F', '6F']:
        agg[f'{w}_延日数'] = agg['医師'].map(crosstab[w].to_dict()).fillna(0).astype(int)
        agg[f'{w}_寄与率'] = agg[f'{w}_延日数'] / ward_total_days[w] * 100

    agg = agg[agg['入院件数'] >= 10].sort_values('総粗利', ascending=False).reset_index(drop=True)
    return df, agg, ward_total_days, total_hospital_days


def make_anonymous_map(agg):
    """総粗利順で A, B, C, ... を割り当て"""
    sorted_agg = agg.sort_values('総粗利', ascending=False).reset_index(drop=True)
    return {row['医師']: f"{chr(ord('A') + i)}医師" for i, row in sorted_agg.iterrows()}


def apply_label(agg_df, mode, anon_map):
    out = agg_df.copy()
    if mode == 'named':
        out['表示名'] = out['医師']
    else:
        out['表示名'] = out['医師'].map(anon_map)
    return out


# ====================================================================
# Chart 1: 計算の考え方（フェーズ別粗利の3段比較）
# ====================================================================
def chart_concept(mode, anon_map):
    fig = plt.figure(figsize=(15, 8))
    gs = fig.add_gridspec(2, 1, height_ratios=[1, 1.2], hspace=0.4)

    # 上段: フェーズ別「報酬・変動費・粗利」3 段棒
    ax_top = fig.add_subplot(gs[0])
    phases = ['A 群\n（1〜5 日）', 'B 群\n（6〜14 日）', 'C 群\n（15 日以降）']
    revs = [REV_A, REV_B, REV_C]
    costs = [COST_A, COST_B, COST_C]
    profits = [PROFIT_A, PROFIT_B, PROFIT_C]
    x = np.arange(len(phases))
    width = 0.25
    bars_rev = ax_top.bar(x - width, revs, width, label='① 日次診療報酬',
                          color='#9CA3AF', alpha=0.85, edgecolor=COLOR_ACCENT)
    bars_cost = ax_top.bar(x, costs, width, label='② 日次変動費',
                           color=COLOR_RED, alpha=0.7, edgecolor=COLOR_ACCENT)
    bars_profit = ax_top.bar(x + width, profits, width,
                              label='③ 粗利（① − ②） = 運営貢献額',
                              color=[COLOR_PHASE_A, COLOR_PHASE_B, COLOR_PHASE_C],
                              edgecolor=COLOR_ACCENT, linewidth=1.5)

    for bars, vals in [(bars_rev, revs), (bars_cost, costs), (bars_profit, profits)]:
        for b, v in zip(bars, vals):
            ax_top.text(b.get_x() + b.get_width()/2, v + 800, f'{v:,}',
                        ha='center', fontsize=11, fontweight='bold',
                        color=COLOR_ACCENT)

    ax_top.set_xticks(x)
    ax_top.set_xticklabels(phases, fontsize=12)
    ax_top.set_ylabel('円 / 床日', fontsize=12)
    ax_top.set_title(
        '【正しい認識】フェーズ別 粗利順位は B 群 ＞ C 群 ＞ A 群\n'
        '報酬は A・B 群が同額でも、A 群はコスト（薬剤・検査・処置）が大きく粗利は最低',
        fontsize=14, fontweight='bold', pad=12,
    )
    ax_top.legend(loc='upper right', fontsize=10, frameon=False)
    ax_top.set_ylim(0, max(revs) * 1.15)
    ax_top.grid(True, axis='y', alpha=0.2)
    ax_top.spines['top'].set_visible(False)
    ax_top.spines['right'].set_visible(False)
    ax_top.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{int(x):,}'))

    # 下段: 概念図（ベッド粗利単価 × 受持数 = 年間粗利）
    ax_bot = fig.add_subplot(gs[1])
    examples = [
        (3,  PROFIT_A, COLOR_PHASE_A,
         '医師 X（A 群中心）',
         '受持 3 人 × 粗利 26,500 円 × 365\n= 年間 約 2,902 万円'),
        (8,  PROFIT_B, COLOR_PHASE_B,
         '医師 Y（B 群中心 ★）',
         '受持 8 人 × 粗利 32,500 円 × 365\n= 年間 約 9,490 万円'),
        (12, PROFIT_C, COLOR_PHASE_C,
         '医師 Z（C 群中心）',
         '受持 12 人 × 粗利 31,000 円 × 365\n= 年間 約 13,578 万円'),
    ]
    for x_, y, c, lbl, desc in examples:
        rect = mpatches.Rectangle((0, 0), x_, y, linewidth=2,
                                   edgecolor=COLOR_ACCENT, facecolor=c,
                                   alpha=0.45, zorder=2)
        ax_bot.add_patch(rect)
        ax_bot.scatter([x_], [y], s=150, c=COLOR_ACCENT, zorder=4,
                       edgecolor='white', linewidth=1.5)
        ax_bot.text(x_ + 0.3, y + 600, lbl, fontsize=12, fontweight='bold',
                    color=COLOR_ACCENT, zorder=5)
        ax_bot.text(x_ + 0.3, y - 1500, desc, fontsize=10,
                    color=COLOR_ACCENT, zorder=5)

    ax_bot.set_xlim(0, 16)
    ax_bot.set_ylim(0, 36000)
    ax_bot.set_xlabel('月平均受持数（人）— 量の貢献', fontsize=13)
    ax_bot.set_ylabel('ベッド粗利単価（円 / 床日）— 質の貢献', fontsize=13)
    ax_bot.set_title(
        '【KPI の考え方】年間粗利 = 受持数（横）× ベッド粗利単価（縦）× 365 日　= 矩形の面積',
        fontsize=13, fontweight='bold', pad=12,
    )
    ax_bot.grid(True, alpha=0.2)
    ax_bot.spines['top'].set_visible(False)
    ax_bot.spines['right'].set_visible(False)
    ax_bot.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{int(x):,}'))

    out_path = OUT_DIR / f'01_concept_{mode}.png'
    plt.savefig(out_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    return out_path


# ====================================================================
# Chart 2: 散布図（粗利単価 × 寄与率）
# ====================================================================
def chart_scatter(agg, mode, anon_map):
    agg2 = apply_label(agg, mode, anon_map)
    fig, ax = plt.subplots(figsize=(13, 8))
    fig.patch.set_alpha(0.0)

    agg2['主たる病棟'] = agg2.apply(
        lambda r: '5F' if r['5F_延日数'] >= r['6F_延日数'] else '6F', axis=1)

    for ward, color in [('5F', COLOR_5F), ('6F', COLOR_6F)]:
        sub = agg2[agg2['主たる病棟'] == ward]
        ax.scatter(sub['病院全体寄与率'], sub['ベッド粗利単価'],
                    s=sub['入院件数'] * 4, c=color, alpha=0.7,
                    edgecolor=COLOR_ACCENT, linewidth=1.5,
                    label=f'{ward} 主たる医師', zorder=3)
        for _, r in sub.iterrows():
            ax.annotate(r['表示名'],
                        xy=(r['病院全体寄与率'], r['ベッド粗利単価']),
                        xytext=(8, 4), textcoords='offset points',
                        fontsize=11, fontweight='bold', color=COLOR_ACCENT, zorder=4)

    median_x = agg2['病院全体寄与率'].median()
    median_y = agg2['ベッド粗利単価'].median()
    ax.axvline(median_x, color='#9CA3AF', linestyle='--', linewidth=0.6, alpha=0.5)
    ax.axhline(median_y, color='#9CA3AF', linestyle='--', linewidth=0.6, alpha=0.5)

    # 参照線: フェーズ別粗利単価
    for y_ref, label, c in [
        (PROFIT_A, f'A 群 単価 {PROFIT_A:,}', '#F87171'),
        (PROFIT_B, f'B 群 単価 {PROFIT_B:,}（最高）', '#10B981'),
        (PROFIT_C, f'C 群 単価 {PROFIT_C:,}', '#D97706'),
    ]:
        ax.axhline(y_ref, color=c, linestyle=':', linewidth=1.2, alpha=0.5, zorder=1)
        ax.text(ax.get_xlim()[1] * 0.98, y_ref + 50, label,
                ha='right', va='bottom', fontsize=9, color=c, alpha=0.8)

    ax.set_xlabel('病院全体 稼働率寄与率（%）— 量の貢献', fontsize=13)
    ax.set_ylabel('ベッド粗利単価（円 / 床日）— 質の貢献', fontsize=13)
    ax.set_title(
        '医師別 ポジショニング: 稼働率寄与（横）× ベッド粗利単価（縦）\n'
        '点線: A・B・C 群理論単価（B 32,500 ＞ C 31,000 ＞ A 26,500）',
        fontsize=13, fontweight='bold', pad=12)
    ax.grid(True, alpha=0.2)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{int(x):,}'))
    ax.legend(loc='lower right', fontsize=11, frameon=False)

    out_path = OUT_DIR / f'02_scatter_{mode}.png'
    plt.savefig(out_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    return out_path


# ====================================================================
# Chart 3: 病棟別ランキング
# ====================================================================
def chart_ward_ranking(agg, ward_total_days, mode, anon_map):
    agg2 = apply_label(agg, mode, anon_map)
    fig, axes = plt.subplots(1, 2, figsize=(15, 8))

    for ax, ward, color in [(axes[0], '5F', COLOR_5F), (axes[1], '6F', COLOR_6F)]:
        sub = agg2[agg2[f'{ward}_寄与率'] > 0].sort_values(f'{ward}_寄与率', ascending=True)
        if sub.empty:
            continue
        y_pos = np.arange(len(sub))
        shares = sub[f'{ward}_寄与率'].values
        ax.barh(y_pos, shares, color=color, alpha=0.85,
                edgecolor=COLOR_ACCENT, linewidth=0.8)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(sub['表示名'].tolist(), fontsize=11)
        ax.set_xlabel(f'{ward} 病棟内 寄与率 (%)', fontsize=12)
        ax.set_title(
            f'{ward} 病棟（年間稼働率 {ward_total_days[ward]/(47*365)*100:.1f}%）',
            fontsize=14, fontweight='bold', pad=10, color=color)

        for i, (_, r) in enumerate(sub.iterrows()):
            s = r[f'{ward}_寄与率']
            d = r[f'{ward}_延日数']
            ax.text(s + 0.5, i, f'{s:.1f}%（{int(d):,}床日）',
                    va='center', fontsize=10, color='#374151')

        ax.set_xlim(0, max(shares) * 1.4)
        ax.grid(True, axis='x', alpha=0.2)
        ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)

        total = shares.sum()
        ax.text(0.98, 0.02,
                f'集計医師合計: {total:.1f}%\n（残 {100-total:.1f}% は件数<10 医師）',
                transform=ax.transAxes, ha='right', va='bottom', fontsize=10,
                color='#6B7280',
                bbox=dict(boxstyle='round,pad=0.4', facecolor='white',
                          edgecolor='#D1D5DB', alpha=0.9))

    plt.suptitle('病棟別 稼働率寄与率ランキング — 各病棟稼働率を誰が支えているか',
                 fontsize=15, fontweight='bold', y=1.005, color=COLOR_ACCENT)
    plt.tight_layout()
    out_path = OUT_DIR / f'03_ward_ranking_{mode}.png'
    plt.savefig(out_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    return out_path


# ====================================================================
# Chart 4: ツリーマップ（粗利シェア）
# ====================================================================
def chart_treemap(agg, mode, anon_map):
    agg2 = apply_label(agg, mode, anon_map).sort_values('総粗利', ascending=False).reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(15, 8))

    cmap = plt.get_cmap('RdYlGn_r')
    n = len(agg2)
    colors = [cmap(0.15 + 0.7 * i / max(n-1, 1)) for i in range(n)]
    sizes = agg2['総粗利'].tolist()
    labels = [
        f"{r['表示名']}\n{r['総粗利']/10000:.0f}万円\n受持 {r['月平均受持数']:.1f}人 / 単価 {r['ベッド粗利単価']:,.0f}円"
        for _, r in agg2.iterrows()
    ]

    squarify.plot(sizes=sizes, label=labels, color=colors, alpha=0.78, ax=ax,
                  edgecolor='white', linewidth=2,
                  text_kwargs={'fontsize': 10, 'fontweight': 'bold', 'color': '#1F2937'})
    ax.axis('off')
    total = agg2['総粗利'].sum() / 1e8
    ax.set_title(
        f'経営シェア（粗利ベース）：全体年間粗利 {total:.2f} 億円 のうち各医師の占有面積',
        fontsize=14, fontweight='bold', pad=14, color=COLOR_ACCENT)
    plt.tight_layout()
    out_path = OUT_DIR / f'04_treemap_{mode}.png'
    plt.savefig(out_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    return out_path


# ====================================================================
# Chart 5: 相関検証（粗利ベース）
# ====================================================================
def chart_correlation(agg, total_hospital_days, mode, anon_map):
    agg2 = apply_label(agg, mode, anon_map)
    x = agg2['病院全体寄与率'].values
    y = agg2['総粗利'].values / 10000

    pearson_r, _ = stats.pearsonr(x, y)
    slope, intercept, r_value, _, _ = stats.linregress(x, y)

    fig, ax = plt.subplots(figsize=(12, 7))
    fig.patch.set_alpha(0.0)
    ax.scatter(x, y, s=agg2['入院件数'] * 4, c=COLOR_BLUE, alpha=0.7,
                edgecolor=COLOR_ACCENT, linewidth=1.5, zorder=3)
    for _, r in agg2.iterrows():
        ax.annotate(r['表示名'], xy=(r['病院全体寄与率'], r['総粗利']/10000),
                    xytext=(7, 4), textcoords='offset points',
                    fontsize=11, fontweight='bold', color=COLOR_ACCENT, zorder=4)

    xx = np.linspace(0, agg2['病院全体寄与率'].max() * 1.05, 100)
    yy = slope * xx + intercept
    ax.plot(xx, yy, color=COLOR_RED, linewidth=2.2, linestyle='--',
            label=f'回帰直線: 粗利 = {slope:.0f} × 寄与率 + {intercept:.0f}\nR² = {r_value**2:.3f}',
            zorder=2)

    ax.set_xlabel('病院全体 稼働率寄与率 (%)', fontsize=13)
    ax.set_ylabel('年間粗利貢献額（万円）', fontsize=13)
    ax.set_title(
        f'稼働率寄与率 と 年間粗利（運営貢献額）の相関検証\n'
        f'相関係数 r = {pearson_r:.3f}（極めて強い正相関）',
        fontsize=14, fontweight='bold', pad=12)
    ax.grid(True, alpha=0.2)
    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    ax.legend(loc='upper left', fontsize=11, frameon=False)

    ax.text(0.98, 0.02,
            '読み方：\n'
            '・稼働率寄与率が高い医師ほど年間粗利も高い\n'
            f'・粗利のばらつきの {r_value**2*100:.1f}% は寄与率だけで説明可\n'
            f'・残り {(1-r_value**2)*100:.1f}% はベッド粗利単価の差\n'
            '  （A 群偏重 ＜ C 群偏重 ＜ B 群偏重）',
            transform=ax.transAxes, ha='right', va='bottom', fontsize=10,
            color='#374151',
            bbox=dict(boxstyle='round,pad=0.5', facecolor='#F9FAFB',
                      edgecolor='#D1D5DB', alpha=0.95))
    plt.tight_layout()
    out_path = OUT_DIR / f'05_correlation_{mode}.png'
    plt.savefig(out_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    return out_path


# ====================================================================
# Chart 6 (新規): 「誤った認識」と「正しい認識」の対比
# ====================================================================
def chart_misconception(mode, anon_map):
    """理事会で「短期回転 = 経営最適」という誤認を解く対比図."""
    fig, axes = plt.subplots(1, 2, figsize=(15, 7))

    # 左: 誤った認識（報酬ベース、実は内部値の引用ミスだが理事会で抱きやすい誤認）
    ax_left = axes[0]
    phases = ['A 群\n(急性期)', 'B 群\n(回復期)', 'C 群\n(退院準備)']
    wrong_values = [38500, 38500, 35500]  # 報酬だけ見た場合
    bars = ax_left.bar(phases, wrong_values, color=['#FCA5A5', '#FCA5A5', '#FCA5A5'],
                        alpha=0.7, edgecolor=COLOR_ACCENT)
    for b, v in zip(bars, wrong_values):
        ax_left.text(b.get_x() + b.get_width()/2, v + 700, f'{v:,}',
                     ha='center', fontsize=12, fontweight='bold', color=COLOR_ACCENT)
    ax_left.set_ylabel('日次診療報酬（円/床日）', fontsize=11)
    ax_left.set_ylim(0, 45000)
    ax_left.set_title(
        '❌ 誤った認識: 「報酬」だけ見ると差が小さく見える\n'
        '「短期 = 急性期 = 高単価」と思い込みがち',
        fontsize=12, fontweight='bold', color=COLOR_RED, pad=10)
    ax_left.grid(True, axis='y', alpha=0.2)
    ax_left.spines['top'].set_visible(False)
    ax_left.spines['right'].set_visible(False)
    ax_left.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{int(x):,}'))

    # 右: 正しい認識（粗利ベース）
    ax_right = axes[1]
    correct_values = [PROFIT_A, PROFIT_B, PROFIT_C]
    correct_colors = [COLOR_PHASE_A, COLOR_PHASE_B, COLOR_PHASE_C]
    bars = ax_right.bar(phases, correct_values, color=correct_colors,
                        alpha=0.85, edgecolor=COLOR_ACCENT, linewidth=1.5)
    for b, v in zip(bars, correct_values):
        ax_right.text(b.get_x() + b.get_width()/2, v + 700, f'{v:,}',
                      ha='center', fontsize=13, fontweight='bold', color=COLOR_ACCENT)
    # 順位マーカー
    rank_marks = ['3位', '★ 1位', '2位']
    rank_colors = [COLOR_RED, COLOR_GREEN, COLOR_GOLD]
    for b, rk, rc in zip(bars, rank_marks, rank_colors):
        ax_right.text(b.get_x() + b.get_width()/2, b.get_height()/2, rk,
                      ha='center', va='center', fontsize=18, fontweight='bold',
                      color=rc)

    ax_right.set_ylabel('粗利＝運営貢献額（円/床日）', fontsize=11)
    ax_right.set_ylim(0, 38000)
    ax_right.set_title(
        '✅ 正しい認識: コストを差し引くと B ＞ C ＞ A\n'
        'A 群はコスト（薬・検査・処置）が大きく、粗利は最低',
        fontsize=12, fontweight='bold', color=COLOR_GREEN, pad=10)
    ax_right.grid(True, axis='y', alpha=0.2)
    ax_right.spines['top'].set_visible(False)
    ax_right.spines['right'].set_visible(False)
    ax_right.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{int(x):,}'))

    plt.suptitle(
        '【理事会へのメッセージ】「短期回転 = 経営貢献大」は誤り。'
        'B 群（回復期 6〜14 日）の中心管理が運営貢献を最大化する。',
        fontsize=14, fontweight='bold', y=1.02, color=COLOR_ACCENT)
    plt.tight_layout()
    out_path = OUT_DIR / f'06_misconception_{mode}.png'
    plt.savefig(out_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    return out_path


def main(mode: str):
    df, agg, ward_total_days, total_hospital_days = load_and_compute()
    anon_map = make_anonymous_map(agg)

    if mode == 'anonymous':
        map_path = OUT_DIR / 'anonymous_mapping.json'
        with open(map_path, 'w', encoding='utf-8') as f:
            json.dump(anon_map, f, ensure_ascii=False, indent=2)
        print(f"  匿名マッピング: {map_path}")

    paths = []
    paths.append(chart_concept(mode, anon_map))
    paths.append(chart_scatter(agg, mode, anon_map))
    paths.append(chart_ward_ranking(agg, ward_total_days, mode, anon_map))
    paths.append(chart_treemap(agg, mode, anon_map))
    paths.append(chart_correlation(agg, total_hospital_days, mode, anon_map))
    paths.append(chart_misconception(mode, anon_map))

    print(f"✅ Generated {len(paths)} charts (mode={mode}):")
    for p in paths:
        print(f"  - {p}")

    # 結果テーブル出力（参考）
    print()
    print(f"全体年間粗利: {agg['総粗利'].sum()/1e8:.2f} 億円")
    print(f"全体平均ベッド粗利単価: {agg['総粗利'].sum()/agg['総延日数'].sum():,.0f} 円/床日")
    print()
    print("医師別 ベッド粗利単価ランキング（高い順）:")
    print(f"{'順位':>3} {'医師':<8} {'単価':>10} {'B群%':>6} {'C群%':>6} {'A群%':>6} {'年粗利':>10}")
    for i, (_, r) in enumerate(agg.sort_values('ベッド粗利単価', ascending=False).iterrows(), 1):
        label = r['医師'] if mode == 'named' else anon_map.get(r['医師'], '?')
        print(f"{i:>3} {label:<8} {r['ベッド粗利単価']:>10,.0f} {r['B群比率']:>5.1f}% {r['C群比率']:>5.1f}% {r['A群比率']:>5.1f}% {r['総粗利']/10000:>9,.0f}万")

    return paths, agg, anon_map


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['named', 'anonymous'], default='named')
    args = parser.parse_args()
    main(args.mode)
