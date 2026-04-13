import { Page, Locator, expect } from '@playwright/test';

/**
 * Streamlit DOM helper — Streamlit renders widgets with specific patterns.
 * All st.metric values appear as [data-testid="stMetricValue"] elements.
 * Sidebar inputs use label text for identification.
 */

/** Wait for Streamlit app to fully load (spinner disappears) */
export async function waitForStreamlitLoad(page: Page, timeout = 15000): Promise<void> {
  // Wait for the main app container
  await page.waitForSelector('[data-testid="stAppViewContainer"]', { timeout });
  // Wait for any running scripts to finish
  await page.waitForFunction(() => {
    const statusWidget = document.querySelector('[data-testid="stStatusWidget"]');
    return !statusWidget || statusWidget.textContent === '';
  }, { timeout });
  // Extra settle time for Streamlit re-renders
  await page.waitForTimeout(1000);
}

/** Wait for Streamlit to finish re-running after an interaction */
export async function waitForRerun(page: Page, timeout = 10000): Promise<void> {
  // Streamlit shows a status widget while running
  try {
    await page.waitForSelector('[data-testid="stStatusWidget"]', { state: 'visible', timeout: 2000 });
    await page.waitForSelector('[data-testid="stStatusWidget"]', { state: 'hidden', timeout });
  } catch {
    // Status widget may not appear for fast reruns
  }
  await page.waitForTimeout(500);
}

/** Get all st.metric elements as {label, value, delta} objects */
export async function getAllMetrics(page: Page): Promise<Array<{label: string, value: string, delta?: string}>> {
  const metrics: Array<{label: string, value: string, delta?: string}> = [];
  const metricContainers = page.locator('[data-testid="stMetric"]');
  const count = await metricContainers.count();

  for (let i = 0; i < count; i++) {
    const container = metricContainers.nth(i);
    const label = await container.locator('[data-testid="stMetricLabel"]').textContent() || '';
    const value = await container.locator('[data-testid="stMetricValue"]').textContent() || '';
    const deltaEl = container.locator('[data-testid="stMetricDelta"]');
    const delta = await deltaEl.count() > 0 ? await deltaEl.textContent() || undefined : undefined;
    metrics.push({ label: label.trim(), value: value.trim(), delta: delta?.trim() });
  }
  return metrics;
}

/** Find a specific metric by label substring */
export async function getMetricByLabel(page: Page, labelSubstring: string): Promise<{label: string, value: string, delta?: string} | null> {
  const all = await getAllMetrics(page);
  return all.find(m => m.label.includes(labelSubstring)) || null;
}

/** Click a sidebar radio option by text */
export async function selectSidebarRadio(page: Page, optionText: string): Promise<void> {
  const sidebar = page.locator('[data-testid="stSidebar"]');
  await sidebar.locator(`label:has-text("${optionText}")`).click();
  await waitForRerun(page);
}

/** Set a sidebar slider value (approximate — Streamlit sliders are tricky) */
export async function setSidebarSlider(page: Page, label: string, value: number): Promise<void> {
  const sidebar = page.locator('[data-testid="stSidebar"]');
  // Find the slider container by its label
  const sliderGroup = sidebar.locator(`[data-testid="stSlider"]:near(:text("${label}"))`).first();
  // Streamlit slider input is a hidden input
  const input = sliderGroup.locator('input[type="range"]');
  await input.fill(String(value));
  await waitForRerun(page);
}

/** Set a sidebar number input */
export async function setSidebarNumberInput(page: Page, label: string, value: number): Promise<void> {
  const sidebar = page.locator('[data-testid="stSidebar"]');
  const container = sidebar.locator(`[data-testid="stNumberInput"]:near(:text("${label}"))`).first();
  const input = container.locator('input[type="number"]');
  await input.fill(String(value));
  await input.press('Enter');
  await waitForRerun(page);
}

/** Click a button by text */
export async function clickButton(page: Page, buttonText: string): Promise<void> {
  await page.locator(`button:has-text("${buttonText}")`).click();
  await waitForRerun(page);
}

/** Click a tab by text */
export async function clickTab(page: Page, tabText: string): Promise<void> {
  await page.locator(`[data-testid="stTab"]:has-text("${tabText}")`).click();
  await waitForRerun(page);
}

/** Get text content of alert/info/warning/error/success boxes */
export async function getAlertMessages(page: Page): Promise<Array<{type: string, text: string}>> {
  const alerts: Array<{type: string, text: string}> = [];
  for (const type of ['stAlert', 'stSuccess', 'stWarning', 'stError', 'stInfo']) {
    const elements = page.locator(`[data-testid="${type}"]`);
    const count = await elements.count();
    for (let i = 0; i < count; i++) {
      const text = await elements.nth(i).textContent() || '';
      alerts.push({ type, text: text.trim() });
    }
  }
  return alerts;
}

/** Get all visible table data as 2D array */
export async function getTableData(page: Page, tableIndex = 0): Promise<string[][]> {
  const tables = page.locator('[data-testid="stTable"] table, [data-testid="stDataFrame"] table');
  const table = tables.nth(tableIndex);
  const rows = table.locator('tr');
  const data: string[][] = [];
  const rowCount = await rows.count();
  for (let i = 0; i < rowCount; i++) {
    const cells = rows.nth(i).locator('th, td');
    const cellCount = await cells.count();
    const row: string[] = [];
    for (let j = 0; j < cellCount; j++) {
      row.push((await cells.nth(j).textContent() || '').trim());
    }
    data.push(row);
  }
  return data;
}

/** Take a full-page screenshot */
export async function takeScreenshot(page: Page, name: string): Promise<void> {
  await page.screenshot({ path: `playwright/screenshots/${name}.png`, fullPage: true });
}

/** Extract a numeric value from a metric string (e.g., "88.8%" → 88.8, "10床" → 10) */
export function parseMetricNumber(value: string): number | null {
  const match = value.match(/([-\d.]+)/);
  return match ? parseFloat(match[1]) : null;
}

/** Select a ward from the sidebar */
export async function selectWard(page: Page, ward: '全体' | '5F' | '6F'): Promise<void> {
  const wardMap: Record<string, string> = {
    '全体': '全体 (94床)',
    '5F': '5F (47床)',
    '6F': '6F (47床)',
  };
  await selectSidebarRadio(page, wardMap[ward]);
}

/** Select a menu section from the sidebar */
export async function selectSection(page: Page, section: string): Promise<void> {
  await selectSidebarRadio(page, section);
}
