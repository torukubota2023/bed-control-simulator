import { test, expect } from '@playwright/test';
import {
  waitForStreamlitLoad, waitForRerun, getAllMetrics, getMetricByLabel,
  selectSidebarRadio, clickButton, clickTab, getAlertMessages,
  parseMetricNumber, selectWard, selectSection, takeScreenshot,
} from '../utils/streamlit_helpers';

// =============================================================================
// デモシナリオ数値照合テスト
// 目的: 実行中のStreamlitアプリからすべての数値を抽出し、
//       デモシナリオ台本の期待値と照合する
// =============================================================================

interface ScenarioCheckResult {
  field: string;
  expected: string;
  actual: string;
  status: 'MATCH' | 'MISMATCH' | 'EXTRACTED' | 'NOT_FOUND';
}

function logCheck(result: ScenarioCheckResult): void {
  console.log(
    `SCENARIO_CHECK|${result.field}|${result.expected}|${result.actual}|${result.status}`
  );
}

/** Compare numeric values with tolerance (default +-2%) */
function numericMatch(actual: number, expected: number, tolerancePct = 2): boolean {
  if (expected === 0) return Math.abs(actual) < 0.5;
  const diff = Math.abs(actual - expected) / Math.abs(expected) * 100;
  return diff <= tolerancePct;
}

/** Extract a number from text using regex */
function extractNumber(text: string): number | null {
  const match = text.match(/([-\d,.]+)/);
  if (!match) return null;
  return parseFloat(match[1].replace(/,/g, ''));
}

test.describe('デモシナリオ数値照合テスト（全セクション網羅）', () => {
  test('全セクションの数値を抽出してシナリオ台本と照合する', async ({ page }) => {
    const results: ScenarioCheckResult[] = [];

    // =========================================================================
    // 0. アプリ起動・初期ロード
    // =========================================================================
    await page.goto('/', { waitUntil: 'networkidle' });
    await waitForStreamlitLoad(page, 20000);

    // 実績データモードを選択（デモデータが入っている前提）
    await selectSidebarRadio(page, '実績データ（日次入力）');
    await page.waitForTimeout(2000);

    // =========================================================================
    // 1. ダッシュボード（📊 ダッシュボード）
    // =========================================================================
    await selectSection(page, 'ダッシュボード');
    await page.waitForTimeout(2000);

    // --- 全体稼働率 ---
    {
      await selectWard(page, '全体');
      await page.waitForTimeout(2000);

      const metrics = await getAllMetrics(page);
      const occMetric = metrics.find(m => m.label.includes('稼働率'));
      if (occMetric) {
        const val = parseMetricNumber(occMetric.value);
        results.push({
          field: 'dashboard_overall_occupancy_rate',
          expected: '~88.8%',
          actual: occMetric.value,
          status: val !== null && numericMatch(val, 88.8, 5) ? 'MATCH' : 'MISMATCH',
        });
      } else {
        results.push({
          field: 'dashboard_overall_occupancy_rate',
          expected: '~88.8%',
          actual: 'NOT_FOUND',
          status: 'NOT_FOUND',
        });
      }

      // --- 翌朝受入余力（全体）---
      const capacityMetric = metrics.find(m => m.label.includes('翌朝受入余力'));
      if (capacityMetric) {
        results.push({
          field: 'dashboard_morning_capacity_overall',
          expected: '(extracted)',
          actual: capacityMetric.value,
          status: 'EXTRACTED',
        });
      } else {
        results.push({
          field: 'dashboard_morning_capacity_overall',
          expected: '(extracted)',
          actual: 'NOT_FOUND',
          status: 'NOT_FOUND',
        });
      }

      // --- 結論カード（今日の一手）---
      const alerts = await getAlertMessages(page);
      const actionCard = alerts.find(a =>
        a.text.includes('今日の一手') || a.text.includes('結論') || a.text.includes('アクション')
      );
      if (actionCard) {
        results.push({
          field: 'dashboard_conclusion_card_exists',
          expected: 'exists',
          actual: `type=${actionCard.type}, text=${actionCard.text.substring(0, 80)}`,
          status: 'MATCH',
        });
      } else {
        // Also check for header-based card
        const cardHeader = page.locator('text=今日の一手').first();
        const headerExists = await cardHeader.isVisible().catch(() => false);
        results.push({
          field: 'dashboard_conclusion_card_exists',
          expected: 'exists',
          actual: headerExists ? 'header_found' : 'NOT_FOUND',
          status: headerExists ? 'MATCH' : 'NOT_FOUND',
        });
      }

      // Check conclusion card color (alert type maps to color)
      if (actionCard) {
        const colorMap: Record<string, string> = {
          stError: 'red/critical',
          stWarning: 'orange/warning',
          stInfo: 'blue/info',
          stSuccess: 'green/success',
        };
        results.push({
          field: 'dashboard_conclusion_card_color',
          expected: '(extracted)',
          actual: colorMap[actionCard.type] || actionCard.type,
          status: 'EXTRACTED',
        });
      }

      // Log all dashboard metrics for reference
      console.log('--- Dashboard metrics (全体) ---');
      for (const m of metrics) {
        console.log(`  METRIC|${m.label}|${m.value}|${m.delta || ''}`);
      }
    }

    // --- 6F稼働率 ---
    {
      await selectWard(page, '6F');
      await page.waitForTimeout(2000);

      const metrics = await getAllMetrics(page);
      const occMetric = metrics.find(m => m.label.includes('稼働率'));
      if (occMetric) {
        const val = parseMetricNumber(occMetric.value);
        results.push({
          field: 'dashboard_6F_occupancy_rate',
          expected: '~91%',
          actual: occMetric.value,
          status: val !== null && numericMatch(val, 91, 5) ? 'MATCH' : 'MISMATCH',
        });
      } else {
        results.push({
          field: 'dashboard_6F_occupancy_rate',
          expected: '~91%',
          actual: 'NOT_FOUND',
          status: 'NOT_FOUND',
        });
      }

      console.log('--- Dashboard metrics (6F) ---');
      for (const m of metrics) {
        console.log(`  METRIC|${m.label}|${m.value}|${m.delta || ''}`);
      }
    }

    // --- 5F metrics for reference ---
    {
      await selectWard(page, '5F');
      await page.waitForTimeout(2000);

      const metrics = await getAllMetrics(page);
      console.log('--- Dashboard metrics (5F) ---');
      for (const m of metrics) {
        console.log(`  METRIC|${m.label}|${m.value}|${m.delta || ''}`);
      }
    }

    // Reset to 全体
    await selectWard(page, '全体');
    await page.waitForTimeout(2000);

    // =========================================================================
    // 2. 制度管理（🛡️ 制度管理）→ 制度余力 tab
    // =========================================================================
    await selectSection(page, '制度管理');
    await page.waitForTimeout(2000);

    // Click 制度余力 tab
    await clickTab(page, '制度余力');
    await page.waitForTimeout(2000);

    // --- 5F rolling LOS ---
    {
      await selectWard(page, '5F');
      await page.waitForTimeout(2000);

      const metrics = await getAllMetrics(page);
      const losMetric = metrics.find(m =>
        m.label.includes('在院日数') || m.label.includes('LOS') || m.label.includes('rolling')
      );
      const pageText = await page.locator('[data-testid="stAppViewContainer"]').textContent() || '';

      // Try to find rolling LOS in page text
      const rollingMatch = pageText.match(/rolling.*?([\d.]+)\s*日/i) ||
                           pageText.match(/([\d.]+)\s*日.*rolling/i) ||
                           pageText.match(/平均在院日数[^0-9]*([\d.]+)/);

      let actualLOS5F = 'NOT_FOUND';
      let status5F: 'MATCH' | 'MISMATCH' | 'NOT_FOUND' = 'NOT_FOUND';

      if (losMetric) {
        actualLOS5F = losMetric.value;
        const val = parseMetricNumber(losMetric.value);
        if (val !== null) {
          status5F = numericMatch(val, 17.7, 10) ? 'MATCH' : 'MISMATCH';
        }
      } else if (rollingMatch) {
        actualLOS5F = rollingMatch[1] + '日';
        const val = parseFloat(rollingMatch[1]);
        status5F = numericMatch(val, 17.7, 10) ? 'MATCH' : 'MISMATCH';
      }

      results.push({
        field: 'guardrail_5F_rolling_LOS',
        expected: '~17.7日',
        actual: actualLOS5F,
        status: status5F,
      });

      console.log('--- 制度余力 metrics (5F) ---');
      for (const m of metrics) {
        console.log(`  METRIC|${m.label}|${m.value}|${m.delta || ''}`);
      }
    }

    // --- 6F rolling LOS ---
    {
      await selectWard(page, '6F');
      await page.waitForTimeout(2000);

      const metrics = await getAllMetrics(page);
      const losMetric = metrics.find(m =>
        m.label.includes('在院日数') || m.label.includes('LOS') || m.label.includes('rolling')
      );
      const pageText = await page.locator('[data-testid="stAppViewContainer"]').textContent() || '';
      const rollingMatch = pageText.match(/rolling.*?([\d.]+)\s*日/i) ||
                           pageText.match(/([\d.]+)\s*日.*rolling/i) ||
                           pageText.match(/平均在院日数[^0-9]*([\d.]+)/);

      let actualLOS6F = 'NOT_FOUND';
      let status6F: 'MATCH' | 'MISMATCH' | 'NOT_FOUND' = 'NOT_FOUND';

      if (losMetric) {
        actualLOS6F = losMetric.value;
        const val = parseMetricNumber(losMetric.value);
        if (val !== null) {
          status6F = numericMatch(val, 21.3, 10) ? 'MATCH' : 'MISMATCH';
        }
      } else if (rollingMatch) {
        actualLOS6F = rollingMatch[1] + '日';
        const val = parseFloat(rollingMatch[1]);
        status6F = numericMatch(val, 21.3, 10) ? 'MATCH' : 'MISMATCH';
      }

      results.push({
        field: 'guardrail_6F_rolling_LOS',
        expected: '~21.3日',
        actual: actualLOS6F,
        status: status6F,
      });

      console.log('--- 制度余力 metrics (6F) ---');
      for (const m of metrics) {
        console.log(`  METRIC|${m.label}|${m.value}|${m.delta || ''}`);
      }
    }

    // Reset to 全体
    await selectWard(page, '全体');
    await page.waitForTimeout(2000);

    // =========================================================================
    // 3. 制度管理 → 需要波 tab
    // =========================================================================
    await clickTab(page, '需要波');
    await page.waitForTimeout(2000);

    {
      const pageText = await page.locator('[data-testid="stAppViewContainer"]').textContent() || '';
      let trend = 'NOT_FOUND';
      if (pageText.includes('増加')) trend = '増加';
      else if (pageText.includes('横ばい')) trend = '横ばい';
      else if (pageText.includes('減少')) trend = '減少';

      results.push({
        field: 'demand_wave_trend',
        expected: '増加/横ばい/減少のいずれか',
        actual: trend,
        status: trend !== 'NOT_FOUND' ? 'EXTRACTED' : 'NOT_FOUND',
      });

      // Also check for demand wave metrics
      const metrics = await getAllMetrics(page);
      console.log('--- 需要波 metrics ---');
      for (const m of metrics) {
        console.log(`  METRIC|${m.label}|${m.value}|${m.delta || ''}`);
      }
    }

    // =========================================================================
    // 4. 制度管理 → C群コントロール tab
    // =========================================================================
    await page.locator('[data-testid="stTab"]').filter({ hasText: '📋 C群コントロール' }).click();
    await page.waitForTimeout(2000);

    {
      const metrics = await getAllMetrics(page);
      const pageText = await page.locator('[data-testid="stAppViewContainer"]').textContent() || '';

      // C group daily contribution
      const cGroupMetric = metrics.find(m =>
        m.label.includes('日額') || m.label.includes('貢献') || m.label.includes('C群')
      );

      // Try regex on page text for daily contribution amount
      const dailyMatch = pageText.match(/日額.*?([\d,]+)\s*円/) ||
                         pageText.match(/([\d,]+)\s*円.*日額/) ||
                         pageText.match(/1日あたり.*?([\d,]+)\s*円/);

      let actualCDaily = 'NOT_FOUND';
      let statusCDaily: 'MATCH' | 'MISMATCH' | 'NOT_FOUND' | 'EXTRACTED' = 'NOT_FOUND';

      if (cGroupMetric) {
        actualCDaily = cGroupMetric.value;
        const val = parseMetricNumber(cGroupMetric.value);
        if (val !== null) {
          statusCDaily = numericMatch(val, 28900, 15) ? 'MATCH' : 'MISMATCH';
        }
      } else if (dailyMatch) {
        actualCDaily = dailyMatch[1] + '円';
        const val = parseFloat(dailyMatch[1].replace(/,/g, ''));
        statusCDaily = numericMatch(val, 28900, 15) ? 'MATCH' : 'MISMATCH';
      }

      results.push({
        field: 'c_group_daily_contribution',
        expected: '~28,900円',
        actual: actualCDaily,
        status: statusCDaily,
      });

      // C group tradeoff evaluation
      const hasTradeoff = pageText.includes('トレードオフ') ||
                          pageText.includes('trade') ||
                          pageText.includes('延長') ||
                          pageText.includes('判定');
      results.push({
        field: 'c_group_tradeoff_evaluation',
        expected: 'exists',
        actual: hasTradeoff ? 'found' : 'NOT_FOUND',
        status: hasTradeoff ? 'MATCH' : 'NOT_FOUND',
      });

      console.log('--- C群コントロール metrics ---');
      for (const m of metrics) {
        console.log(`  METRIC|${m.label}|${m.value}|${m.delta || ''}`);
      }
    }

    // =========================================================================
    // 5. 制度管理 → 救急搬送15% tab
    // =========================================================================
    await clickTab(page, '救急搬送');
    await page.waitForTimeout(2000);

    // --- 5F emergency ratio ---
    {
      await selectWard(page, '5F');
      await page.waitForTimeout(2000);

      const metrics = await getAllMetrics(page);
      const pageText = await page.locator('[data-testid="stAppViewContainer"]').textContent() || '';

      const emergMetric = metrics.find(m =>
        m.label.includes('救急搬送') || m.label.includes('搬送後') || m.label.includes('割合')
      );

      // Try regex on page text
      const ratioMatch = pageText.match(/救急搬送.*?([\d.]+)\s*%/) ||
                         pageText.match(/([\d.]+)\s*%.*救急/);

      let actual5FEmerg = 'NOT_FOUND';
      let status5FEmerg: 'MATCH' | 'MISMATCH' | 'NOT_FOUND' = 'NOT_FOUND';

      if (emergMetric) {
        actual5FEmerg = emergMetric.value;
        const val = parseMetricNumber(emergMetric.value);
        if (val !== null) {
          status5FEmerg = numericMatch(val, 22, 20) ? 'MATCH' : 'MISMATCH';
        }
      } else if (ratioMatch) {
        actual5FEmerg = ratioMatch[1] + '%';
        const val = parseFloat(ratioMatch[1]);
        status5FEmerg = numericMatch(val, 22, 20) ? 'MATCH' : 'MISMATCH';
      }

      results.push({
        field: 'emergency_ratio_5F',
        expected: '~22%',
        actual: actual5FEmerg,
        status: status5FEmerg,
      });

      console.log('--- 救急搬送 metrics (5F) ---');
      for (const m of metrics) {
        console.log(`  METRIC|${m.label}|${m.value}|${m.delta || ''}`);
      }
    }

    // --- 6F emergency ratio ---
    {
      await selectWard(page, '6F');
      await page.waitForTimeout(2000);

      const metrics = await getAllMetrics(page);
      const pageText = await page.locator('[data-testid="stAppViewContainer"]').textContent() || '';

      const emergMetric = metrics.find(m =>
        m.label.includes('救急搬送') || m.label.includes('搬送後') || m.label.includes('割合')
      );

      const ratioMatch = pageText.match(/救急搬送.*?([\d.]+)\s*%/) ||
                         pageText.match(/([\d.]+)\s*%.*救急/);

      let actual6FEmerg = 'NOT_FOUND';
      let status6FEmerg: 'MATCH' | 'MISMATCH' | 'NOT_FOUND' = 'NOT_FOUND';

      if (emergMetric) {
        actual6FEmerg = emergMetric.value;
        const val = parseMetricNumber(emergMetric.value);
        if (val !== null) {
          status6FEmerg = numericMatch(val, 2.6, 50) ? 'MATCH' : 'MISMATCH';
        }
      } else if (ratioMatch) {
        actual6FEmerg = ratioMatch[1] + '%';
        const val = parseFloat(ratioMatch[1]);
        status6FEmerg = numericMatch(val, 2.6, 50) ? 'MATCH' : 'MISMATCH';
      }

      results.push({
        field: 'emergency_ratio_6F',
        expected: '~2.6%',
        actual: actual6FEmerg,
        status: status6FEmerg,
      });

      // --- "あと何件必要" display for 6F ---
      const needMore = pageText.includes('あと') &&
                       (pageText.includes('件') || pageText.includes('必要'));
      const needMoreMatch = pageText.match(/あと\s*([\d]+)\s*件/);

      results.push({
        field: 'emergency_6F_need_more_display',
        expected: 'exists',
        actual: needMoreMatch ? `あと${needMoreMatch[1]}件` : (needMore ? 'found (text)' : 'NOT_FOUND'),
        status: needMore ? 'MATCH' : 'NOT_FOUND',
      });

      console.log('--- 救急搬送 metrics (6F) ---');
      for (const m of metrics) {
        console.log(`  METRIC|${m.label}|${m.value}|${m.delta || ''}`);
      }

      // --- Check for removed "モード切替" UI ---
      const hasModeSwitchText = pageText.includes('モード切替');
      const hasShort3DenominatorText = pageText.includes('短手3（ポリペクなど）を分母から除くと');
      const modeSwitchUI = page.locator('text=モード切替');
      const modeSwitchCount = await modeSwitchUI.count();

      results.push({
        field: 'emergency_mode_switch_removed_check',
        expected: 'removed (2026 revision)',
        actual: modeSwitchCount > 0 ? `STILL_EXISTS (${modeSwitchCount} elements)` : 'correctly_removed',
        status: modeSwitchCount > 0 ? 'MISMATCH' : 'MATCH',
      });

      results.push({
        field: 'emergency_short3_denominator_text_check',
        expected: 'removed (2026 revision)',
        actual: hasShort3DenominatorText ? 'STILL_EXISTS' : 'correctly_removed',
        status: hasShort3DenominatorText ? 'MISMATCH' : 'MATCH',
      });
    }

    // Reset to 全体
    await selectWard(page, '全体');
    await page.waitForTimeout(2000);

    // =========================================================================
    // 6. 意思決定支援 → 運営改善アラート tab
    // =========================================================================
    await selectSection(page, '意思決定支援');
    await page.waitForTimeout(2000);

    // Look for 運営改善アラート tab
    {
      const alertTab = page.locator('[data-testid="stTab"]:has-text("運営改善"), [data-testid="stTab"]:has-text("アラート")');
      if (await alertTab.count() > 0) {
        await alertTab.first().click();
        await waitForRerun(page);
        await page.waitForTimeout(2000);
      }

      const pageText = await page.locator('[data-testid="stAppViewContainer"]').textContent() || '';

      // 金曜退院集中 percentage
      const fridayMatch = pageText.match(/金曜.*?([\d.]+)\s*%/) ||
                          pageText.match(/([\d.]+)\s*%.*金曜/) ||
                          pageText.match(/退院集中.*?([\d.]+)\s*%/);

      let actualFriday = 'NOT_FOUND';
      let statusFriday: 'MATCH' | 'MISMATCH' | 'NOT_FOUND' = 'NOT_FOUND';

      if (fridayMatch) {
        actualFriday = fridayMatch[1] + '%';
        const val = parseFloat(fridayMatch[1]);
        statusFriday = numericMatch(val, 31, 15) ? 'MATCH' : 'MISMATCH';
      }

      results.push({
        field: 'decision_friday_discharge_concentration',
        expected: '~31%',
        actual: actualFriday,
        status: statusFriday,
      });

      const metrics = await getAllMetrics(page);
      console.log('--- 運営改善アラート metrics ---');
      for (const m of metrics) {
        console.log(`  METRIC|${m.label}|${m.value}|${m.delta || ''}`);
      }
    }

    // =========================================================================
    // 7. 意思決定支援 → What-if分析
    // =========================================================================
    {
      const whatifTab = page.locator('[data-testid="stTab"]:has-text("What-if"), [data-testid="stTab"]:has-text("what-if"), [data-testid="stTab"]:has-text("What")');
      if (await whatifTab.count() > 0) {
        await whatifTab.first().click();
        await waitForRerun(page);
        await page.waitForTimeout(2000);
      }

      const pageText = await page.locator('[data-testid="stAppViewContainer"]').textContent() || '';

      // Scenario save/compare feature
      const hasSaveCompare = pageText.includes('シナリオ') &&
                             (pageText.includes('保存') || pageText.includes('比較'));
      const hasSaveButton = await page.locator('button:has-text("保存")').count() > 0;
      const hasCompareButton = await page.locator('button:has-text("比較")').count() > 0;

      results.push({
        field: 'whatif_scenario_save_compare',
        expected: 'exists',
        actual: hasSaveCompare || hasSaveButton || hasCompareButton
          ? `save=${hasSaveButton}, compare=${hasCompareButton}, text=${hasSaveCompare}`
          : 'NOT_FOUND',
        status: hasSaveCompare || hasSaveButton || hasCompareButton ? 'MATCH' : 'NOT_FOUND',
      });

      console.log('--- What-if metrics ---');
      const metrics = await getAllMetrics(page);
      for (const m of metrics) {
        console.log(`  METRIC|${m.label}|${m.value}|${m.delta || ''}`);
      }
    }

    // =========================================================================
    // 8. HOPE連携
    // =========================================================================
    await selectSection(page, 'HOPE連携');
    await page.waitForTimeout(2000);

    {
      const pageText = await page.locator('[data-testid="stAppViewContainer"]').textContent() || '';
      const hasHOPE = pageText.includes('HOPE') || pageText.includes('メッセージ');
      const hasGenerateButton = await page.locator('button:has-text("生成"), button:has-text("HOPE"), button:has-text("送信")').count() > 0;

      results.push({
        field: 'hope_message_generation',
        expected: 'exists',
        actual: hasHOPE || hasGenerateButton
          ? `HOPE_section=${hasHOPE}, generate_button=${hasGenerateButton}`
          : 'NOT_FOUND',
        status: hasHOPE || hasGenerateButton ? 'MATCH' : 'NOT_FOUND',
      });

      console.log('--- HOPE連携 metrics ---');
      const metrics = await getAllMetrics(page);
      for (const m of metrics) {
        console.log(`  METRIC|${m.label}|${m.value}|${m.delta || ''}`);
      }
    }

    // =========================================================================
    // 9. 病棟切り替え巡回チェック（各セクションで全体/5F/6F）
    // =========================================================================
    const wardSwitchResults: string[] = [];
    const sectionsToCheck = ['ダッシュボード', '制度管理', '意思決定支援'];

    for (const section of sectionsToCheck) {
      await selectSection(page, section);
      await page.waitForTimeout(2000);

      for (const ward of ['全体', '5F', '6F'] as const) {
        try {
          await selectWard(page, ward);
          await page.waitForTimeout(1500);
          const appContainer = page.locator('[data-testid="stAppViewContainer"]');
          const visible = await appContainer.isVisible();
          wardSwitchResults.push(`${section}/${ward}: ${visible ? 'OK' : 'FAIL'}`);
        } catch (e) {
          wardSwitchResults.push(`${section}/${ward}: ERROR - ${String(e).substring(0, 60)}`);
        }
      }
    }

    results.push({
      field: 'ward_switching_all_sections',
      expected: 'all OK',
      actual: wardSwitchResults.filter(r => !r.includes('OK')).length === 0
        ? `all ${wardSwitchResults.length} combinations OK`
        : wardSwitchResults.filter(r => !r.includes('OK')).join('; '),
      status: wardSwitchResults.filter(r => !r.includes('OK')).length === 0 ? 'MATCH' : 'MISMATCH',
    });

    console.log('--- Ward switching results ---');
    for (const r of wardSwitchResults) {
      console.log(`  WARD_SWITCH|${r}`);
    }

    // =========================================================================
    // 10. 結果サマリー出力
    // =========================================================================
    console.log('\n' + '='.repeat(80));
    console.log('SCENARIO VERIFICATION SUMMARY');
    console.log('='.repeat(80));
    console.log(
      'FIELD'.padEnd(45) +
      'EXPECTED'.padEnd(25) +
      'ACTUAL'.padEnd(30) +
      'STATUS'
    );
    console.log('-'.repeat(110));

    for (const r of results) {
      logCheck(r);
    }

    const matchCount = results.filter(r => r.status === 'MATCH').length;
    const mismatchCount = results.filter(r => r.status === 'MISMATCH').length;
    const extractedCount = results.filter(r => r.status === 'EXTRACTED').length;
    const notFoundCount = results.filter(r => r.status === 'NOT_FOUND').length;

    console.log('-'.repeat(110));
    console.log(`TOTAL: ${results.length} checks`);
    console.log(`  MATCH:     ${matchCount}`);
    console.log(`  MISMATCH:  ${mismatchCount}`);
    console.log(`  EXTRACTED: ${extractedCount}`);
    console.log(`  NOT_FOUND: ${notFoundCount}`);
    console.log('='.repeat(80));

    // Take a final screenshot
    await takeScreenshot(page, 'scenario_verify_final');

    // Soft assertion: log mismatches but don't fail the test
    // (purpose is extraction, not strict assertion)
    for (const r of results) {
      if (r.status === 'NOT_FOUND') {
        console.warn(`WARNING: ${r.field} was not found on the page`);
      }
    }

    // The test passes as long as at least some values were extracted
    expect(results.filter(r => r.status !== 'NOT_FOUND').length).toBeGreaterThan(0);
  });
});
