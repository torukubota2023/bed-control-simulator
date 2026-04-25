import { test, expect, Page } from '@playwright/test';
import {
  waitForStreamlitLoad, waitForRerun, getAllMetrics, clickButton,
  selectSidebarRadio, selectSection, selectWard, getAlertMessages,
  parseMetricNumber, takeScreenshot,
} from '../utils/streamlit_helpers';

/**
 * 包括的監査テスト — アプリ全体の動作・矛盾・ベッドコントロール観点の妥当性を検証
 *
 * 目的: 先生のベッドコントロール実務の観点で「おかしい現象」を自動検出
 */

// =====================================================================
// 共通ユーティリティ: 問題検出結果を集約
// =====================================================================
type Issue = {
  severity: 'critical' | 'warning' | 'info';
  category: string;
  message: string;
  context?: string;
};

const issues: Issue[] = [];

function logIssue(severity: Issue['severity'], category: string, message: string, context?: string) {
  issues.push({ severity, category, message, context });
  const prefix = severity === 'critical' ? '🔴' : severity === 'warning' ? '🟡' : '🔵';
  console.log(`${prefix} [${category}] ${message}${context ? ` (${context})` : ''}`);
}

test.afterAll(() => {
  // レポート出力
  console.log('\n========== 監査結果サマリー ==========');
  const critical = issues.filter(i => i.severity === 'critical');
  const warnings = issues.filter(i => i.severity === 'warning');
  const infos = issues.filter(i => i.severity === 'info');
  console.log(`🔴 Critical: ${critical.length}件`);
  console.log(`🟡 Warning:  ${warnings.length}件`);
  console.log(`🔵 Info:     ${infos.length}件`);
  if (critical.length > 0) {
    console.log('\n-- Critical Issues --');
    critical.forEach(i => console.log(`  [${i.category}] ${i.message}`));
  }
  if (warnings.length > 0) {
    console.log('\n-- Warnings --');
    warnings.forEach(i => console.log(`  [${i.category}] ${i.message}`));
  }
});

// =====================================================================
// 監査1: 全セクション × 全病棟の巡回エラーチェック
// =====================================================================
test.describe('監査1: 全セクション×全病棟の巡回', () => {
  test('全セクションを開いて Python エラー・Tracebackを検出', async ({ page }) => {
    test.setTimeout(300000); // 5分タイムアウト（巡回は時間がかかる）
    // Phase 5（2026-04-25）: 「📊 過去1年分析」を新セクション「📈 過去1年分析」に独立化（5→6 セクション）
    const sections = ['今日の運営', 'What-if・戦略', '制度管理', '退院調整', '過去1年分析', 'データ・設定'];
    const wards: Array<'全体' | '5F' | '6F'> = ['全体', '5F', '6F'];

    await page.goto('/');
    await waitForStreamlitLoad(page);
    await clickButton(page, 'シミュレーション実行');

    for (const section of sections) {
      try {
        await selectSection(page, section);
        await page.waitForTimeout(1500);

        // Streamlit Python トレースバックを検出
        const tracebacks = await page.locator('[data-testid="stException"]').count();
        if (tracebacks > 0) {
          const text = await page.locator('[data-testid="stException"]').first().textContent();
          logIssue('critical', `セクション: ${section}`, 'Python例外が発生', text?.slice(0, 200));
        }

        // エラーアラートも検出
        const errors = page.locator('[data-testid="stAlert"][data-baseweb="notification"]');
        const errorCount = await errors.count();
        for (let i = 0; i < errorCount; i++) {
          const text = await errors.nth(i).textContent();
          if (text && (text.includes('Error') || text.includes('エラー') || text.includes('Traceback'))) {
            logIssue('critical', `セクション: ${section}`, 'エラー表示', text.slice(0, 200));
          }
        }

        // 病棟切替でもエラーが出ないか
        for (const ward of wards) {
          try {
            await selectWard(page, ward);
            await page.waitForTimeout(800);
            const wardErrors = await page.locator('[data-testid="stException"]').count();
            if (wardErrors > 0) {
              logIssue('critical', `${section} × ${ward}`, '病棟切替でエラー');
            }
          } catch (e) {
            logIssue('warning', `${section} × ${ward}`, `病棟切替失敗: ${e}`);
          }
        }
      } catch (e) {
        logIssue('warning', `セクション: ${section}`, `セクション選択失敗: ${e}`);
      }
    }
  });
});

// =====================================================================
// 監査2: 数値の常識チェック（ベッドコントロール観点）
// =====================================================================
test.describe('監査2: 数値の妥当性チェック', () => {
  test('各種KPIが現実的な範囲内にあるか', async ({ page }) => {
    await page.goto('/');
    await waitForStreamlitLoad(page);
    await clickButton(page, 'シミュレーション実行');
    await selectSection(page, 'What-if・戦略');

    const metrics = await getAllMetrics(page);

    for (const m of metrics) {
      const num = parseMetricNumber(m.value);
      if (num === null) continue;

      // 金額・価値系は稼働率判定から除外（ラベルに「稼働率」を含むがパーセント値ではない）
      const isMonetary = m.value.includes('万円') || m.value.includes('¥') || m.value.includes('円') || m.label.includes('価値');
      // delta/変化量は絶対値チェックから除外
      const isDelta = m.value.startsWith('+') || m.value.startsWith('-') || m.label.includes('影響') || m.label.includes('余力');

      // 稼働率は0〜110%（100%超は「在院+退院」で一時的に起こり得る）
      if (m.label.includes('稼働率') && !isMonetary && m.value.includes('%')) {
        if (num < 0 || num > 110) {
          logIssue('critical', '稼働率', `${m.label}: ${m.value} が異常範囲`);
        } else if (num < 50) {
          logIssue('warning', '稼働率', `${m.label}: ${m.value} が低すぎる（デモデータの想定外）`);
        }
      }

      // 在院日数は1〜60日が現実的（delta/変化量は除外）
      if ((m.label.includes('在院日数') || m.label.includes('LOS')) && !isDelta && m.value.includes('日')) {
        if (num < 1 || num > 60) {
          logIssue('critical', '在院日数', `${m.label}: ${m.value} が異常範囲`);
        }
      }

      // 空床数は0〜94床
      if (m.label.includes('空床') || m.label.includes('余力')) {
        if (num < 0 || num > 94) {
          logIssue('critical', '空床数', `${m.label}: ${m.value} が異常範囲`);
        }
      }

      // 在院患者数は0〜94人
      if (m.label.includes('在院患者')) {
        if (num < 0 || num > 94) {
          logIssue('critical', '在院患者数', `${m.label}: ${m.value} が異常範囲`);
        }
      }

      // 金額系（万円）は0以上
      if (m.value.includes('万円') || m.value.includes('¥')) {
        if (num < -10000) {
          logIssue('warning', '金額', `${m.label}: ${m.value} がマイナス`);
        }
      }
    }
  });

  test('5F+6Fの加重平均が全体稼働率と一致する', async ({ page }) => {
    await page.goto('/');
    await waitForStreamlitLoad(page);
    await clickButton(page, 'シミュレーション実行');

    // 稼働率を探す際に「%」を含み「万円」を含まないものに限定
    const findOcc = (metrics: Array<{label: string, value: string}>) => metrics.find(m =>
      m.label.includes('稼働率') && m.value.includes('%') && !m.value.includes('万円')
    );

    await selectWard(page, '全体');
    const allMetrics = await getAllMetrics(page);
    const overallOcc = findOcc(allMetrics);
    const overallOccNum = overallOcc ? parseMetricNumber(overallOcc.value) : null;

    await selectWard(page, '5F');
    const m5f = await getAllMetrics(page);
    const occ5f = findOcc(m5f);
    const occ5fNum = occ5f ? parseMetricNumber(occ5f.value) : null;

    await selectWard(page, '6F');
    const m6f = await getAllMetrics(page);
    const occ6f = findOcc(m6f);
    const occ6fNum = occ6f ? parseMetricNumber(occ6f.value) : null;

    if (overallOccNum && occ5fNum && occ6fNum) {
      // 5F・6F どちらも 47床 なので単純平均
      const avg = (occ5fNum + occ6fNum) / 2;
      const diff = Math.abs(overallOccNum - avg);
      if (diff > 2) {
        logIssue('warning', '加重平均', `全体${overallOccNum}% vs 平均${avg.toFixed(1)}% の乖離 ${diff.toFixed(1)}pt`);
      }
      console.log(`稼働率: 全体=${overallOccNum}%, 5F=${occ5fNum}%, 6F=${occ6fNum}%, 平均=${avg.toFixed(1)}%`);
    }
  });
});

// =====================================================================
// 監査3: 結論カードの論理矛盾検出
// =====================================================================
test.describe('監査3: 結論カードの論理矛盾', () => {
  test('KPI が赤なのに結論カードが緑でないか', async ({ page }) => {
    await page.goto('/');
    await waitForStreamlitLoad(page);
    await clickButton(page, 'シミュレーション実行');
    await selectSection(page, 'What-if・戦略');

    // 結論カードのメッセージを取得
    const alerts = await getAlertMessages(page);
    const conclusionCard = alerts.find(a => a.text.includes('今日の一手'));

    const metrics = await getAllMetrics(page);

    // 救急搬送比率が赤（<15%）なのに結論カードが緑の場合は矛盾
    const rescueRatio = metrics.find(m => m.label.includes('救急搬送'));
    if (rescueRatio && conclusionCard) {
      const ratioNum = parseMetricNumber(rescueRatio.value);
      if (ratioNum !== null && ratioNum < 15 && conclusionCard.type === 'stSuccess') {
        logIssue('critical', '結論カード矛盾',
          `救急搬送比率 ${ratioNum}% < 15% なのに結論カードが success`);
      }
    }

    // 施設基準チェックが「逸脱」なのに結論カードが緑の場合は矛盾
    const guardrail = metrics.find(m => m.label.includes('施設基準'));
    if (guardrail && conclusionCard) {
      if (guardrail.value.includes('逸脱') && conclusionCard.type === 'stSuccess') {
        logIssue('critical', '結論カード矛盾',
          `施設基準が「逸脱」なのに結論カードが success`);
      }
    }
  });

  test('月平均稼働率と直近稼働率の整合性', async ({ page }) => {
    await page.goto('/');
    await waitForStreamlitLoad(page);
    await clickButton(page, 'シミュレーション実行');

    const metrics = await getAllMetrics(page);
    // 稼働率メトリックは % を含み、万円を含まないものに限定
    const monthlyOcc = metrics.find(m => m.label.includes('月平均') && m.value.includes('%'));
    const currentOcc = metrics.find(m =>
      m.label.includes('稼働率') && !m.label.includes('月') &&
      m.value.includes('%') && !m.value.includes('万円') && !m.label.includes('価値')
    );

    if (monthlyOcc && currentOcc) {
      const monthly = parseMetricNumber(monthlyOcc.value);
      const current = parseMetricNumber(currentOcc.value);
      if (monthly !== null && current !== null) {
        const diff = Math.abs(monthly - current);
        if (diff > 15) {
          logIssue('warning', '稼働率',
            `月平均${monthly}% と 直近${current}% の乖離が大きい (${diff.toFixed(1)}pt)`);
        }
      }
    }
  });
});

// =====================================================================
// 監査4: タブ切替でコンテンツが正しく切り替わるか
// =====================================================================
test.describe('監査4: 各タブの内容確認', () => {
  test('今日の運営全タブで内容が表示される', async ({ page }) => {
    await page.goto('/');
    await waitForStreamlitLoad(page);
    await selectSection(page, '今日の運営');
    await clickButton(page, 'シミュレーション実行');

    // Phase 2 情報階層リデザイン（2026-04-18）以降、意思決定ダッシュボード・運営改善アラートは
    // 「📊 今日の運営」配下へ移設（旧「📊 ダッシュボード」セクションを改名）
    const tabs = ['意思決定ダッシュボード', '運営改善アラート', '日次推移', 'フェーズ構成', '運営分析', 'トレンド分析'];
    for (const tabName of tabs) {
      try {
        const tab = page.locator(`[data-testid="stTab"]:has-text("${tabName}")`).first();
        if (await tab.count() === 0) {
          logIssue('warning', `タブ: ${tabName}`, 'タブが存在しない');
          continue;
        }
        await tab.click();
        await page.waitForTimeout(1500);

        // 各タブで例外がないこと
        const exceptions = await page.locator('[data-testid="stException"]').count();
        if (exceptions > 0) {
          const text = await page.locator('[data-testid="stException"]').first().textContent();
          logIssue('critical', `タブ: ${tabName}`, '例外発生', text?.slice(0, 200));
        }

        // 何かしらのコンテンツが表示されているか
        const hasContent = await page.locator('[data-testid="stMetric"], [data-testid="stPlotlyChart"], canvas, img').count() > 0;
        if (!hasContent) {
          logIssue('warning', `タブ: ${tabName}`, 'コンテンツが表示されていない');
        }
      } catch (e) {
        logIssue('warning', `タブ: ${tabName}`, `タブ操作失敗: ${e}`);
      }
    }
  });

  test('What-if・戦略タブ', async ({ page }) => {
    await page.goto('/');
    await waitForStreamlitLoad(page);
    await selectSection(page, 'What-if・戦略');
    await clickButton(page, 'シミュレーション実行');

    // Phase 1: 退院タイミングは「退院調整」へ移設
    // Phase 2: 意思決定ダッシュボード・運営改善アラートは「今日の運営」へ移設 → What-if のみ残る
    const tabs = ['What-if分析'];
    for (const tabName of tabs) {
      try {
        const tab = page.locator(`[data-testid="stTab"]:has-text("${tabName}")`).first();
        if (await tab.count() === 0) {
          logIssue('warning', `タブ: ${tabName}`, 'タブが存在しない');
          continue;
        }
        await tab.click();
        await page.waitForTimeout(1500);
        const exceptions = await page.locator('[data-testid="stException"]').count();
        if (exceptions > 0) {
          const text = await page.locator('[data-testid="stException"]').first().textContent();
          logIssue('critical', `タブ: ${tabName}`, '例外発生', text?.slice(0, 200));
        }
      } catch (e) {
        logIssue('warning', `タブ: ${tabName}`, `タブ操作失敗: ${e}`);
      }
    }
  });

  test('退院調整タブ', async ({ page }) => {
    // Phase 1 情報階層リデザイン（2026-04-18）で新設。
    // 旧「連休対策」「多職種退院調整カンファ」＋旧意思決定支援（現 What-if・戦略）「退院タイミング」を統合。
    await page.goto('/');
    await waitForStreamlitLoad(page);
    await selectSection(page, '退院調整');
    await page.waitForTimeout(1500);

    const tabs = ['カンファ資料', '退院タイミング', '今週の需要予測', '退院候補リスト', '予約可能枠'];
    for (const tabName of tabs) {
      try {
        const tab = page.locator(`[data-testid="stTab"]:has-text("${tabName}")`).first();
        if (await tab.count() === 0) {
          logIssue('warning', `タブ: ${tabName}`, 'タブが存在しない');
          continue;
        }
        await tab.click();
        await page.waitForTimeout(1500);
        const exceptions = await page.locator('[data-testid="stException"]').count();
        if (exceptions > 0) {
          const text = await page.locator('[data-testid="stException"]').first().textContent();
          logIssue('critical', `タブ: ${tabName}`, '例外発生', text?.slice(0, 200));
        }
      } catch (e) {
        logIssue('warning', `タブ: ${tabName}`, `タブ操作失敗: ${e}`);
      }
    }
  });
});

// =====================================================================
// 監査5: データ・設定タブでの入力・保存・削除
// Phase 4（2026-04-18・最終）: 旧「データ管理」→「データ・設定」に改名
// =====================================================================
test.describe('監査5: データ入力機能', () => {
  test('日次データ入力フォームが正しく表示される', async ({ page }) => {
    await page.goto('/');
    await waitForStreamlitLoad(page);
    await selectSection(page, 'データ・設定');
    await page.waitForTimeout(2000);

    // 日次データ入力タブをクリック
    const inputTab = page.locator('[data-testid="stTab"]:has-text("日次データ入力")').first();
    if (await inputTab.count() > 0) {
      await inputTab.click();
      await page.waitForTimeout(1500);

      // 統合フォームの要素が存在するか
      const inputs = page.locator('[data-testid="stNumberInput"], [data-testid="stSelectbox"]');
      const inputCount = await inputs.count();
      if (inputCount < 3) {
        logIssue('warning', 'データ入力', `入力フォームの要素が少ない (${inputCount}個)`);
      }

      // 例外がないこと
      const exceptions = await page.locator('[data-testid="stException"]').count();
      if (exceptions > 0) {
        logIssue('critical', 'データ入力タブ', '例外発生');
      }
    } else {
      logIssue('warning', 'データ入力タブ', 'タブが存在しない');
    }
  });
});

// =====================================================================
// 監査6: コンソールエラー検出
// =====================================================================
test.describe('監査6: コンソールエラー検出', () => {
  test('各セクションでJSコンソールエラーがないか', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', msg => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });
    page.on('pageerror', err => consoleErrors.push(err.message));

    await page.goto('/');
    await waitForStreamlitLoad(page);
    await clickButton(page, 'シミュレーション実行');

    for (const section of ['今日の運営', 'What-if・戦略', '制度管理']) {
      await selectSection(page, section);
      await page.waitForTimeout(1500);
    }

    // Streamlit内部のノイズを除外
    const appErrors = consoleErrors.filter(e =>
      !e.includes('ResizeObserver') &&
      !e.includes('favicon') &&
      !e.includes('WebSocket')
    );

    if (appErrors.length > 0) {
      for (const err of appErrors) {
        logIssue('warning', 'コンソール', err.slice(0, 200));
      }
    }
  });
});
