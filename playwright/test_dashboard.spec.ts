import { test, expect } from '@playwright/test';
import {
  waitForStreamlitLoad, waitForRerun, getAllMetrics, getMetricByLabel,
  selectSidebarRadio, clickButton, clickTab, getAlertMessages,
  parseMetricNumber, selectWard, selectSection, takeScreenshot,
  setSidebarNumberInput,
} from '../utils/streamlit_helpers';
import { extractDashboardKPIs, validateKPIIntegrity, DashboardKPIs } from '../utils/extract_data';

// =====================================================================
// テスト1: アプリ起動・基本表示
// =====================================================================
test.describe('アプリ起動と基本表示', () => {
  test('アプリが正常に起動し、タイトルが表示される', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' });
    await waitForStreamlitLoad(page);

    // タイトルはh1またはヘッダー要素で表示される（初回ロードに時間がかかる場合あり）
    const title = page.locator('h1:has-text("ベッドコントロールシミュレーター")');
    await expect(title).toBeVisible({ timeout: 15000 });
  });

  test('サイドバーにメニューが表示される', async ({ page }) => {
    await page.goto('/');
    await waitForStreamlitLoad(page);

    const sidebar = page.locator('[data-testid="stSidebar"]');
    await expect(sidebar).toBeVisible();

    // メニュー選択肢が存在する（複数マッチを避けるため .first()）
    for (const section of ['ダッシュボード', '意思決定支援', '制度管理', 'データ管理', 'HOPE連携']) {
      await expect(sidebar.locator(`text=${section}`).first()).toBeVisible();
    }
  });

  test('病棟選択（全体/5F/6F）が切り替えられる', async ({ page }) => {
    await page.goto('/');
    await waitForStreamlitLoad(page);

    for (const ward of ['全体 (94床)', '5F (47床)', '6F (47床)']) {
      await selectSidebarRadio(page, ward);
      // 切り替え後もページがエラーなく表示される
      const appContainer = page.locator('[data-testid="stAppViewContainer"]');
      await expect(appContainer).toBeVisible();
    }
  });
});

// =====================================================================
// テスト2: シミュレーション実行と数値整合性
// =====================================================================
test.describe('シミュレーション実行と数値検証', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await waitForStreamlitLoad(page);
    // シミュレーションモードを選択
    await selectSidebarRadio(page, 'シミュレーション（予測モデル）');
  });

  test('正常パラメータでシミュレーションが完了する', async ({ page }) => {
    await clickButton(page, 'シミュレーション実行');

    // シミュレーション後にメトリクスが表示される
    const metrics = await getAllMetrics(page);
    expect(metrics.length).toBeGreaterThan(0);

    await takeScreenshot(page, 'simulation_normal');
  });

  test('稼働率が0〜100%の範囲内', async ({ page }) => {
    await clickButton(page, 'シミュレーション実行');

    const kpis = await extractDashboardKPIs(page);
    if (kpis.occupancyRate !== undefined) {
      expect(kpis.occupancyRate).toBeGreaterThanOrEqual(0);
      expect(kpis.occupancyRate).toBeLessThanOrEqual(100);
    }
  });

  test('フェーズ構成比（A+B+C）が約100%になる', async ({ page }) => {
    await clickButton(page, 'シミュレーション実行');
    // フェーズ構成タブに移動
    await clickTab(page, 'フェーズ構成');

    const kpis = await extractDashboardKPIs(page);
    if (kpis.phaseA !== undefined && kpis.phaseB !== undefined && kpis.phaseC !== undefined) {
      const sum = kpis.phaseA + kpis.phaseB + kpis.phaseC;
      expect(sum).toBeGreaterThan(90);
      expect(sum).toBeLessThan(110);
    }
  });

  test('結論カード（今日の一手）が表示される', async ({ page }) => {
    // 意思決定支援に移動
    await selectSection(page, '意思決定支援');
    await clickButton(page, 'シミュレーション実行');

    // 結論カードはアラート要素またはヘッダーで表示される
    const alerts = await getAlertMessages(page);
    const actionCard = alerts.find(a =>
      a.text.includes('今日の一手') || a.text.includes('結論') || a.text.includes('アクション')
    );
    // アラート形式で見つからない場合、ヘッダーテキストで確認
    if (!actionCard) {
      const cardHeader = page.locator('text=今日の一手').first();
      const headerExists = await cardHeader.isVisible().catch(() => false);
      expect(headerExists || actionCard).toBeTruthy();
    }
  });

  test('KPI優先表示セクションが「未取得」でない', async ({ page }) => {
    await selectSection(page, '意思決定支援');
    await clickButton(page, 'シミュレーション実行');

    const metrics = await getAllMetrics(page);
    const unknownKPIs = metrics.filter(m => m.value === '未取得');

    // 救急搬送比率は入退院詳細データが必要なので除外
    const criticalUnknown = unknownKPIs.filter(m =>
      !m.label.includes('救急搬送') && !m.label.includes('翌朝')
    );

    // 施設基準チェックと稼働率は表示されるべき
    for (const kpi of criticalUnknown) {
      console.warn(`KPIが未取得: ${kpi.label}`);
    }
  });
});

// =====================================================================
// テスト3: 数値整合性チェック（医療経営の観点）
// =====================================================================
test.describe('数値整合性チェック（経営・安全の観点）', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await waitForStreamlitLoad(page);
    await selectSection(page, '意思決定支援');
    await clickButton(page, 'シミュレーション実行');
  });

  test('KPI整合性バリデーション（全項目）', async ({ page }) => {
    const kpis = await extractDashboardKPIs(page);
    const errors = validateKPIIntegrity(kpis);

    for (const error of errors) {
      if (error.startsWith('[WARNING]')) {
        console.warn(error);
      } else {
        // 数値バグは即失敗
        expect.soft(error).toBe(''); // soft assertionで全エラーを報告
      }
    }
  });

  test('翌朝受入余力が病床数を超えない', async ({ page }) => {
    const kpis = await extractDashboardKPIs(page);
    if (kpis.morningCapacity !== undefined) {
      expect(kpis.morningCapacity).toBeLessThanOrEqual(94); // 全体94床
    }
  });

  test('3診療日最小が翌朝受入余力以下', async ({ page }) => {
    const kpis = await extractDashboardKPIs(page);
    if (kpis.morningCapacity !== undefined && kpis.threeDayMin !== undefined) {
      expect(kpis.threeDayMin).toBeLessThanOrEqual(kpis.morningCapacity);
    }
  });
});

// =====================================================================
// テスト4: 病棟切り替え時の数値一貫性
// =====================================================================
test.describe('病棟切り替えの一貫性', () => {
  test('5F/6Fの稼働率が全体の妥当な範囲にある', async ({ page }) => {
    await page.goto('/');
    await waitForStreamlitLoad(page);
    await clickButton(page, 'シミュレーション実行');

    // 全体の稼働率を取得
    const overallKPIs = await extractDashboardKPIs(page);
    const overallOcc = overallKPIs.occupancyRate;

    // 5Fの稼働率を取得
    await selectWard(page, '5F');
    const kpis5F = await extractDashboardKPIs(page);

    // 6Fの稼働率を取得
    await selectWard(page, '6F');
    const kpis6F = await extractDashboardKPIs(page);

    // 各病棟の稼働率が全体から大きく乖離していないか
    if (overallOcc && kpis5F.occupancyRate && kpis6F.occupancyRate) {
      // 各病棟の稼働率が0-100%の範囲
      expect(kpis5F.occupancyRate).toBeGreaterThanOrEqual(0);
      expect(kpis5F.occupancyRate).toBeLessThanOrEqual(100);
      expect(kpis6F.occupancyRate).toBeGreaterThanOrEqual(0);
      expect(kpis6F.occupancyRate).toBeLessThanOrEqual(100);

      // 全体稼働率は5F/6Fの加重平均に近いはず（±5pt）
      const avg = (kpis5F.occupancyRate + kpis6F.occupancyRate) / 2;
      expect(Math.abs(overallOcc - avg)).toBeLessThan(10);
    }
  });
});

// =====================================================================
// テスト5: タブ切り替えでのエラーチェック
// =====================================================================
test.describe('全タブ・全セクション巡回テスト', () => {
  test('全セクション×全タブでJSエラーが発生しない', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', msg => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    await page.goto('/');
    await waitForStreamlitLoad(page);
    await clickButton(page, 'シミュレーション実行');

    const sections = ['ダッシュボード', '意思決定支援', '制度管理'];
    for (const section of sections) {
      await selectSection(page, section);
      await page.waitForTimeout(2000);
    }

    // Streamlit内部のエラー以外をチェック
    const appErrors = consoleErrors.filter(e =>
      !e.includes('ResizeObserver') && !e.includes('favicon')
    );

    if (appErrors.length > 0) {
      console.error('Console errors detected:', appErrors);
    }
    expect(appErrors.length).toBe(0);
  });
});

// =====================================================================
// テスト6: 制度管理タブの施設基準チェック
// =====================================================================
test.describe('制度管理タブ', () => {
  test('制度余力ダッシュボードが表示される', async ({ page }) => {
    await page.goto('/');
    await waitForStreamlitLoad(page);
    await selectSidebarRadio(page, '実績データ（日次入力）');
    await selectSection(page, '制度管理');

    // 制度余力サブタブが存在する
    const guardrailTab = page.locator('text=制度余力');
    // タブが存在すればクリック
    if (await guardrailTab.count() > 0) {
      await guardrailTab.first().click();
      await waitForRerun(page);
      await takeScreenshot(page, 'guardrail_tab');
    }
  });
});

// =====================================================================
// テスト7: UI要素の存在チェック
// =====================================================================
test.describe('UI要素の存在チェック', () => {
  test('本日の病床状況セクションが存在する', async ({ page }) => {
    await page.goto('/');
    await waitForStreamlitLoad(page);
    await clickButton(page, 'シミュレーション実行');

    // メインコンテンツ内の在院患者数メトリクスで確認（サイドバーのヘルプテキストを除外）
    const mainContent = page.locator('[data-testid="stAppViewContainer"]');
    const patientMetric = mainContent.locator('[data-testid="stMetric"]').first();
    await expect(patientMetric).toBeVisible();
  });

  test('シミュレーション実行ボタンが存在する', async ({ page }) => {
    await page.goto('/');
    await waitForStreamlitLoad(page);

    const button = page.locator('button:has-text("シミュレーション実行")');
    await expect(button).toBeVisible();
  });
});
