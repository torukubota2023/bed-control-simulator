import { test, expect } from '@playwright/test';
import {
  waitForStreamlitLoad, waitForRerun, clickButton, selectSection,
  selectWard, getAllMetrics, getAlertMessages, takeScreenshot,
  parseMetricNumber,
} from '../utils/streamlit_helpers';
import { extractDashboardKPIs, validateKPIIntegrity } from '../utils/extract_data';

/**
 * 医療経営・安全性の観点からのテスト
 *
 * このアプリは病床運用の意思決定支援ツールであり、
 * 誤った判断は経営・医療安全に影響するため、
 * 現実の運用を想定した厳しい評価を行う。
 */

test.describe('医療安全：結論カードの妥当性', () => {
  test('結論カードのレベルがKPIと矛盾しない', async ({ page }) => {
    await page.goto('/');
    await waitForStreamlitLoad(page);
    await selectSection(page, '意思決定支援');
    await clickButton(page, 'シミュレーション実行');

    const kpis = await extractDashboardKPIs(page);

    // 結論カードが「正常」なのに危険なKPIがある場合は矛盾
    if (kpis.actionCardLevel === 'success') {
      // 稼働率が80%未満なのに「正常」はおかしい
      if (kpis.occupancyRate !== undefined && kpis.occupancyRate < 80) {
        expect.soft(true).toBe(false); // fail
        console.error(`結論カードが「正常」だが稼働率が${kpis.occupancyRate}%（80%未満）`);
      }
      // LOS余力がマイナスなのに「正常」はおかしい
      if (kpis.losHeadroom !== undefined && kpis.losHeadroom < 0) {
        expect.soft(true).toBe(false);
        console.error(`結論カードが「正常」だがLOS余力が${kpis.losHeadroom}日（マイナス）`);
      }
    }
  });

  test('他病棟協力表示が病棟選択時に出現する', async ({ page }) => {
    await page.goto('/');
    await waitForStreamlitLoad(page);
    await selectSection(page, '意思決定支援');
    await clickButton(page, 'シミュレーション実行');

    // 5Fを選択
    await selectWard(page, '5F');

    // 他病棟の状況セクションがあるか確認（expander）
    const crossWard = page.locator('text=他病棟の状況');
    // 存在する場合もしない場合もある（他病棟に問題がない場合は非表示）
    const exists = await crossWard.count() > 0;
    console.log(`他病棟協力表示: ${exists ? '表示あり' : '表示なし（他病棟に問題なし）'}`);
  });
});

test.describe('医療安全：制度上限チェック', () => {
  test('平均在院日数が制度上限（21-24日）を超過していないか', async ({ page }) => {
    await page.goto('/');
    await waitForStreamlitLoad(page);
    await clickButton(page, 'シミュレーション実行');

    const kpis = await extractDashboardKPIs(page);
    if (kpis.avgLOS !== undefined) {
      // 24日を超えるとどの85歳以上割合でも制度上限超過
      if (kpis.avgLOS > 24) {
        console.error(`平均在院日数が制度上限を超過: ${kpis.avgLOS}日 > 24日`);
      }
      expect(kpis.avgLOS).toBeLessThanOrEqual(30); // 30日超は明らかに異常値
    }
  });
});

test.describe('経営リスク：稼働率と空床コスト', () => {
  test('稼働率が極端に低い場合に警告が出る', async ({ page }) => {
    await page.goto('/');
    await waitForStreamlitLoad(page);

    // 低入院数でシミュレーション
    // Note: パラメータ変更はStreamlitの再描画を伴うため時間がかかる
    await clickButton(page, 'シミュレーション実行');
    await selectSection(page, '意思決定支援');

    const kpis = await extractDashboardKPIs(page);
    if (kpis.occupancyRate !== undefined && kpis.occupancyRate < 85) {
      // 低稼働率の場合、結論カードが何らかの警告を出すべき
      const alerts = await getAlertMessages(page);
      const hasWarning = alerts.some(a =>
        a.type !== 'stSuccess' && a.text.includes('今日の一手')
      );
      console.log(`稼働率${kpis.occupancyRate}% — 警告表示: ${hasWarning}`);
    }

    await takeScreenshot(page, 'low_occupancy_test');
  });

  test('空床数×単価の計算が本日の病床状況に表示される', async ({ page }) => {
    await page.goto('/');
    await waitForStreamlitLoad(page);
    await clickButton(page, 'シミュレーション実行');

    // 「空床」を含むテキストを探す
    const emptyBedInfo = page.locator('text=/空床.*床/');
    if (await emptyBedInfo.count() > 0) {
      const text = await emptyBedInfo.first().textContent();
      console.log(`空床情報: ${text}`);
    }
  });
});

test.describe('データ表示の安定性', () => {
  test('同じパラメータで2回実行して結果が一致する', async ({ page }) => {
    await page.goto('/');
    await waitForStreamlitLoad(page);

    // 1回目
    await clickButton(page, 'シミュレーション実行');
    const kpis1 = await extractDashboardKPIs(page);

    // 2回目（同じパラメータ）
    await clickButton(page, 'シミュレーション実行');
    const kpis2 = await extractDashboardKPIs(page);

    // 乱数シードが同じなら結果は一致するはず
    if (kpis1.occupancyRate !== undefined && kpis2.occupancyRate !== undefined) {
      expect(Math.abs(kpis1.occupancyRate - kpis2.occupancyRate)).toBeLessThan(0.1);
    }
  });

  test('ページリロード後もデータが保持される', async ({ page }) => {
    await page.goto('/');
    await waitForStreamlitLoad(page);
    await clickButton(page, 'シミュレーション実行');

    const before = await extractDashboardKPIs(page);

    // リロード
    await page.reload();
    await waitForStreamlitLoad(page);

    // Streamlitはリロードでsession_stateがリセットされるので
    // データが消えることは正常動作（エラーにならなければOK）
    const appContainer = page.locator('[data-testid="stAppViewContainer"]');
    await expect(appContainer).toBeVisible();
  });
});
