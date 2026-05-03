"""医師別 病棟貢献度 KPI チャート生成（理事会版・運営会議版両対応）.

副院長指示 (2026-05-04):
  - 理事会では実医師コード（KJJ, KUBT...）
  - 運営会議では A 医師, B 医師, C 医師（匿名化）

匿名化ルール: 病院全体の年間収益降順で A, B, C, ... を付与
  → 関係者は誰が誰か特定できないが、ランキングは保たれる

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

RATE_A, RATE_B, RATE_C = 24000, 13200, 6400
COLOR_5F = '#3B82F6'
COLOR_6F = '#EC4899'
COLOR_ACCENT = '#374151'
COLOR_GREEN = '#10B981'
COLOR_RED = '#DC2626'
COLOR_GOLD = '#D97706'
COLOR_BLUE = '#2563EB'


def phase_breakdown(d):
    return min(d, 5), min(max(d - 5, 0), 9), max(d - 14, 0)


def revenue_per_admission(d):
    a, b, c = phase_breakdown(d)
    return a * RATE_A + b * RATE_B + c * RATE_C


def load_and_compute():
    df = pd.read_csv(DATA_PATH)
    df[['A_days', 'B_days', 'C_days']] = df['日数'].apply(
        lambda x: pd.Series(phase_breakdown(x))
    )
    df['収益貢献額'] = df['日数'].apply(revenue_per_admission)

    crosstab = df.groupby(['医師', '病棟'])['日数'].sum().unstack(fill_value=0)
    crosstab.columns.name = None
    ward_total_days = df.groupby('病棟')['日数'].sum().to_dict()

    agg = df.groupby('医師').agg(
        入院件数=('患者番号', 'count'),
        総延日数=('日数', 'sum'),
        総収益=('収益貢献額', 'sum'),
        A群延日数=('A_days', 'sum'),
        C群延日数=('C_days', 'sum'),
    ).reset_index()
    agg['月平均受持数'] = agg['総延日数'] / 365
    agg['ベッド単価'] = agg['総収益'] / agg['総延日数']
    agg['平均在院日数'] = agg['総延日数'] / agg['入院件数']
    agg['A群比率'] = agg['A群延日数'] / agg['総延日数'] * 100
    agg['C群比率'] = agg['C群延日数'] / agg['総延日数'] * 100
    total_hospital_days = df['日数'].sum()
    agg['病院全体寄与率'] = agg['総延日数'] / total_hospital_days * 100

    # 病棟別寄与率
    for w in ['5F', '6F']:
        agg[f'{w}_延日数'] = agg['医師'].map(crosstab[w].to_dict()).fillna(0).astype(int)
        agg[f'{w}_寄与率'] = agg[f'{w}_延日数'] / ward_total_days[w] * 100

    agg = agg[agg['入院件数'] >= 10].sort_values('総収益', ascending=False).reset_index(drop=True)
    return df, agg, ward_total_days, total_hospital_days


def make_anonymous_map(agg):
    """収益順で A, B, C, ... を割り当て"""
    sorted_agg = agg.sort_values('総収益', ascending=False).reset_index(drop=True)
    return {row['医師']: f"{chr(ord('A') + i)}医師" for i, row in sorted_agg.iterrows()}


def apply_label(agg_df, mode, anon_map):
    """mode に応じて表示用ラベルを付ける"""
    out = agg_df.copy()
    if mode == 'named':
        out['表示名'] = out['医師']
    else:
        out['表示名'] = out['医師'].map(anon_map)
    return out


# ====================================================================
# Chart 1: 計算の考え方（面積の概念図）
# ====================================================================
def chart_concept(mode, anon_map):
    fig, ax = plt.subplots(figsize=(13, 7))
    fig.patch.set_alpha(0.0)

    # 例として 3 つの矩形を描画（量と単価の組合せ）
    # シンプルなイラスト
    examples = [
        # (x, y, color, label, desc)
        (3,  16000, '#FCA5A5', '医師 X', '受持 3 人 × 単価 16,000 円\n= 1.75 千万円/年'),
        (8,  12000, '#93C5FD', '医師 Y', '受持 8 人 × 単価 12,000 円\n= 3.50 千万円/年'),
        (12, 10000, '#86EFAC', '医師 Z', '受持 12 人 × 単価 10,000 円\n= 4.38 千万円/年'),
    ]

    for x, y, c, lbl, desc in examples:
        rect = mpatches.Rectangle((0, 0), x, y, linewidth=2,
                                   edgecolor=COLOR_ACCENT, facecolor=c, alpha=0.4, zorder=2)
        ax.add_patch(rect)
        ax.scatter([x], [y], s=120, c=COLOR_ACCENT, zorder=4, edgecolor='white', linewidth=1.5)
        ax.text(x + 0.3, y + 200, lbl, fontsize=12, fontweight='bold', color=COLOR_ACCENT, zorder=5)
        ax.text(x + 0.3, y - 600, desc, fontsize=10, color=COLOR_ACCENT, zorder=5)

    ax.set_xlim(0, 16)
    ax.set_ylim(0, 19000)
    ax.set_xlabel('月平均受持数（人）— 病棟稼働率への量の貢献', fontsize=13)
    ax.set_ylabel('ベッド単価（円/床日）— 1 床 1 日あたりの収益', fontsize=13)
    ax.set_title('計算の考え方：年間収益 = 受持数（横）× ベッド単価（縦）× 365 日',
                 fontsize=15, fontweight='bold', pad=15)
    ax.grid(True, alpha=0.2)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{int(x):,}'))

    # 説明
    ax.text(15.5, 18500,
            '矩形の面積 ∝ 年間収益貢献額\n「縦×横」の長方形が大きいほど経営貢献大',
            ha='right', va='top', fontsize=11, color=COLOR_BLUE, fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.5', facecolor='white',
                      edgecolor=COLOR_BLUE, alpha=0.9))

    plt.tight_layout()
    out_path = OUT_DIR / f'01_concept_{mode}.png'
    plt.savefig(out_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    return out_path


# ====================================================================
# Chart 2: 散布図（稼働率寄与率 vs ベッド単価）
# ====================================================================
def chart_scatter(agg, mode, anon_map):
    agg2 = apply_label(agg, mode, anon_map)
    fig, ax = plt.subplots(figsize=(13, 8))
    fig.patch.set_alpha(0.0)

    # 病棟別の主たる病棟を判定（5F/6F の延日数が多い方）
    agg2['主たる病棟'] = agg2.apply(
        lambda r: '5F' if r['5F_延日数'] >= r['6F_延日数'] else '6F', axis=1)

    for ward, color in [('5F', COLOR_5F), ('6F', COLOR_6F)]:
        sub = agg2[agg2['主たる病棟'] == ward]
        ax.scatter(sub['病院全体寄与率'], sub['ベッド単価'],
                    s=sub['入院件数'] * 4, c=color, alpha=0.7,
                    edgecolor=COLOR_ACCENT, linewidth=1.5,
                    label=f'{ward} 主たる医師', zorder=3)
        for _, r in sub.iterrows():
            ax.annotate(r['表示名'], xy=(r['病院全体寄与率'], r['ベッド単価']),
                        xytext=(8, 4), textcoords='offset points',
                        fontsize=11, fontweight='bold', color=COLOR_ACCENT, zorder=4)

    median_x = agg2['病院全体寄与率'].median()
    median_y = agg2['ベッド単価'].median()
    ax.axvline(median_x, color='#9CA3AF', linestyle='--', linewidth=0.6, alpha=0.5)
    ax.axhline(median_y, color='#9CA3AF', linestyle='--', linewidth=0.6, alpha=0.5)

    ax.set_xlabel('病院全体 稼働率寄与率(%)', fontsize=13)
    ax.set_ylabel('ベッド単価（円/床日）', fontsize=13)
    ax.set_title(
        '医師別 ポジショニング: 稼働率寄与(横) × ベッド単価(縦)',
        fontsize=14, fontweight='bold', pad=12)
    ax.grid(True, alpha=0.2)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{int(x):,}'))
    ax.legend(loc='upper right', fontsize=11, frameon=False)

    # 4 象限の解説
    xlim = ax.get_xlim(); ylim = ax.get_ylim()
    ax.text(xlim[1]*0.98, ylim[1]*0.98, '⭐ 量・単価とも高い\n（理想型・該当なし）',
            ha='right', va='top', fontsize=10, color=COLOR_GREEN, fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                      edgecolor=COLOR_GREEN, alpha=0.9))
    ax.text(xlim[1]*0.98, ylim[0]+(ylim[1]-ylim[0])*0.04, '量で稼働率を支える\n（C 群偏重）',
            ha='right', va='bottom', fontsize=10, color='#6B7280',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                      edgecolor='#9CA3AF', alpha=0.85))
    ax.text(xlim[0]+(xlim[1]-xlim[0])*0.04, ylim[1]*0.98, '単価で経営に貢献\n（少量・短手3 中心）',
            ha='left', va='top', fontsize=10, color='#6B7280',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                      edgecolor='#9CA3AF', alpha=0.85))

    plt.tight_layout()
    out_path = OUT_DIR / f'02_scatter_{mode}.png'
    plt.savefig(out_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    return out_path


# ====================================================================
# Chart 3: 病棟別ランキング（5F vs 6F 横並び）
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
        ax.set_xlabel(f'{ward} 病棟内 寄与率(%)', fontsize=12)
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
                f'集計医師合計: {total:.1f}%\n'
                f'（残 {100-total:.1f}% は件数<10 医師）',
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
# Chart 4: ツリーマップ（経営シェア）
# ====================================================================
def chart_treemap(agg, mode, anon_map):
    agg2 = apply_label(agg, mode, anon_map).sort_values('総収益', ascending=False).reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(15, 8))

    cmap = plt.get_cmap('RdYlGn_r')
    n = len(agg2)
    colors = [cmap(0.15 + 0.7 * i / max(n-1, 1)) for i in range(n)]
    sizes = agg2['総収益'].tolist()
    labels = [
        f"{r['表示名']}\n{r['総収益']/10000:.0f}万円\n受持 {r['月平均受持数']:.1f}人 / 単価 {r['ベッド単価']:,.0f}円"
        for _, r in agg2.iterrows()
    ]

    squarify.plot(sizes=sizes, label=labels, color=colors, alpha=0.78, ax=ax,
                  edgecolor='white', linewidth=2,
                  text_kwargs={'fontsize': 10, 'fontweight': 'bold', 'color': '#1F2937'})
    ax.axis('off')
    total = agg2['総収益'].sum() / 1e8
    ax.set_title(
        f'経営シェア・ツリーマップ：全体年間収益 {total:.2f} 億円 のうち各医師の占有面積',
        fontsize=14, fontweight='bold', pad=14, color=COLOR_ACCENT)
    plt.tight_layout()
    out_path = OUT_DIR / f'04_treemap_{mode}.png'
    plt.savefig(out_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    return out_path


# ====================================================================
# Chart 5: 相関検証
# ====================================================================
def chart_correlation(agg, total_hospital_days, mode, anon_map):
    agg2 = apply_label(agg, mode, anon_map)
    x = agg2['病院全体寄与率'].values
    y = agg2['総収益'].values / 10000

    pearson_r, _ = stats.pearsonr(x, y)
    slope, intercept, r_value, _, _ = stats.linregress(x, y)

    fig, ax = plt.subplots(figsize=(12, 7))
    fig.patch.set_alpha(0.0)
    ax.scatter(x, y, s=agg2['入院件数'] * 4, c=COLOR_BLUE, alpha=0.7,
                edgecolor=COLOR_ACCENT, linewidth=1.5, zorder=3)
    for _, r in agg2.iterrows():
        ax.annotate(r['表示名'], xy=(r['病院全体寄与率'], r['総収益']/10000),
                    xytext=(7, 4), textcoords='offset points',
                    fontsize=11, fontweight='bold', color=COLOR_ACCENT, zorder=4)

    xx = np.linspace(0, agg2['病院全体寄与率'].max() * 1.05, 100)
    yy = slope * xx + intercept
    ax.plot(xx, yy, color=COLOR_RED, linewidth=2.2, linestyle='--',
            label=f'回帰直線: 収益 = {slope:.0f} × 寄与率 + {intercept:.0f}\nR² = {r_value**2:.3f}',
            zorder=2)

    ax.set_xlabel('病院全体 稼働率寄与率(%)', fontsize=13)
    ax.set_ylabel('年間収益貢献額（万円）', fontsize=13)
    ax.set_title(
        f'稼働率寄与率 と 年間収益 の相関検証\n'
        f'相関係数 r = {pearson_r:.3f}（極めて強い正相関）',
        fontsize=14, fontweight='bold', pad=12)
    ax.grid(True, alpha=0.2)
    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    ax.legend(loc='upper left', fontsize=11, frameon=False)

    # 解説テキスト
    ax.text(0.98, 0.02,
            '読み方：\n'
            '・稼働率寄与率が高い医師ほど年間収益も高い\n'
            f'・収益のばらつきの {r_value**2*100:.1f}% は寄与率だけで説明可\n'
            '・残り {} % はベッド単価の差'.format(int((1-r_value**2)*100)),
            transform=ax.transAxes, ha='right', va='bottom', fontsize=10,
            color='#374151',
            bbox=dict(boxstyle='round,pad=0.5', facecolor='#F9FAFB',
                      edgecolor='#D1D5DB', alpha=0.95))
    plt.tight_layout()
    out_path = OUT_DIR / f'05_correlation_{mode}.png'
    plt.savefig(out_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    return out_path


def main(mode: str):
    df, agg, ward_total_days, total_hospital_days = load_and_compute()
    anon_map = make_anonymous_map(agg)

    if mode == 'anonymous':
        # 匿名マッピングを出力（参考用、内部確認）
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

    print(f"✅ Generated {len(paths)} charts (mode={mode}):")
    for p in paths:
        print(f"  - {p}")

    return paths, agg, anon_map


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['named', 'anonymous'], default='named')
    args = parser.parse_args()
    main(args.mode)
