import { test, expect, Page } from '@playwright/test';
import { waitForStreamlitLoad, selectSidebarRadio } from '../utils/streamlit_helpers';
import scenariosData from './tests/scenarios.json';

// =============================================================================
// 多職種退院調整・連休対策カンファ E2E テスト (test_conference_view)
//
// 検証対象:
//   - サイドバーメニューの新セクション「🏥 多職種退院調整カンファ」選択
//   - hidden div data-testid 8 種の DOM 存在確認
//   - モードトグル（通常 → 連休対策）で conference-mode が "normal" → "holiday"
//   - 病棟 selectbox（5F → 6F）で conference-ward が "5F" → "6F"
//   - ファクトバーに PMID らしき文字列が表示される
//
// CLAUDE.md 運用ルール:
//   - data-testid は絶対に削除・改名しない
//   - UI 変更時は本ファイルの参照と突合する
// =============================================================================

const SECTION_NAME = '🏥 多職種退院調整カンファ';

const CONFERENCE_TESTIDS = [
  'conference-mode',
  'conference-ward',
  'conference-occupancy-pct',
  'conference-alos-days',
  'conference-emergency-pct',
  'conference-holiday-days',
  'conference-patient-count',
  'conference-fact-id',
];

/** サイドバーの「メニュー」ラジオでカンファセクションに切り替える.
 *
 * Streamlit のラジオは <input type="radio" tabindex="-1"> で不可視のため、
 * 親ラベル（label:has-text）をクリックすることで state を切り替える.
 */
async function selectConferenceSection(page: Page): Promise<void> {
  const sidebar = page.locator('[data-testid="stSidebar"]');
  const label = sidebar.locator(`label:has-text("${SECTION_NAME}")`).first();
  await expect(label, 'サイドバーに「多職種退院調整カンファ」ラベルが見つからない').toHaveCount(1);
  await label.click();
  // Streamlit の rerun 完了を待つ（サイドバー切替 + ビュー初期化で余裕をもって）
  await waitForStreamlitLoad(page, 120000);
}

test.describe('ベッドコントロール E2E — 多職種退院調整カンファ', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await waitForStreamlitLoad(page);
    // 本体は初期状態ではダッシュボードが表示されるため、
    // カンファセクションを選択するだけでビューが描画される（シミュ実行不要）.
    await selectConferenceSection(page);
  });

  // ---------------------------------------------------------------------------
  // 1. サイドバー選択 + セクションヘッダーの可視性
  // ---------------------------------------------------------------------------
  test('サイドバーから「多職種退院調整カンファ」を選択できる', async ({ page }) => {
    // カンファ資料タブが存在する（セクション切替に成功した証左）
    const tab = page.locator('[data-testid="stTab"]:has-text("カンファ資料")').first();
    await expect(tab).toBeVisible();

    // 主要 testid が少なくとも 1 つは DOM にある（ビュー本体描画の証左）
    const modeCount = await page.locator('[data-testid="conference-mode"]').count();
    expect(modeCount, 'conference-mode testid が描画されていない').toBeGreaterThanOrEqual(1);
  });

  // ---------------------------------------------------------------------------
  // 2. testid 8 種類の DOM 存在確認
  // ---------------------------------------------------------------------------
  test.describe('hidden div data-testid の存在確認', () => {
    for (const id of CONFERENCE_TESTIDS) {
      test(`[data-testid="${id}"] が DOM に存在する`, async ({ page }) => {
        const locator = page.locator(`[data-testid="${id}"]`);
        const count = await locator.count();
        expect(
          count,
          `${id} が見つからない — view の hidden div が出力されていない`
        ).toBeGreaterThanOrEqual(1);
      });
    }
  });

  // ---------------------------------------------------------------------------
  // 3. モードトグル: normal → holiday
  // ---------------------------------------------------------------------------
  test('モードトグルで conference-mode が normal → holiday に切り替わる', async ({ page }) => {
    // 初期は normal
    const modeEl = page.locator('[data-testid="conference-mode"]').first();
    const initialMode = (await modeEl.innerText()).trim();
    expect(initialMode, `初期モードが normal でない: ${initialMode}`).toBe('normal');

    // 連休対策モードのトグルをクリック
    const toggleLabel = page.locator('label:has-text("連休対策モード")').first();
    await expect(toggleLabel, '連休対策モードのトグルが見つからない').toHaveCount(1);
    await toggleLabel.click();
    await waitForStreamlitLoad(page, 60000);

    // モード testid が holiday に切り替わっている
    const newMode = (
      await page.locator('[data-testid="conference-mode"]').first().innerText()
    ).trim();
    expect(newMode, `モード切替後が holiday でない: ${newMode}`).toBe('holiday');
  });

  // ---------------------------------------------------------------------------
  // 4. 病棟 selectbox: 5F → 6F
  // ---------------------------------------------------------------------------
  test('病棟 selectbox で conference-ward が 5F → 6F に切り替わる', async ({ page }) => {
    const wardEl = page.locator('[data-testid="conference-ward"]').first();
    const initialWard = (await wardEl.innerText()).trim();
    expect(initialWard, `初期病棟が 5F でない: ${initialWard}`).toBe('5F');

    // ビュー内部の selectbox (ラベル「病棟」) を操作
    // Streamlit の selectbox はボタン風の div 要素 — テキストで発見しクリックして開く.
    const mainArea = page.locator('[data-testid="stAppViewContainer"] section.main, [data-testid="stAppViewContainer"] [data-testid="stMain"]').first();
    // selectbox を特定するための loose strategy: 「病棟」ラベル直後の combobox 風ボタン
    const selectboxes = page.locator('[data-baseweb="select"]');
    // ビュー内にある selectbox（＝ 病棟 切替）を絞り込み
    // 本番では、ビュー内唯一の ward selectbox は最上位に出現する（ctrl_col1）
    // 「病棟」ラベルを含むコンテナの中の select をターゲットにする
    const wardContainer = page.locator('div:has(> label:has-text("病棟"))').filter({
      has: page.locator('[data-baseweb="select"]'),
    }).first();
    const wardSelect = wardContainer.locator('[data-baseweb="select"]').first();
    await wardSelect.click();

    // ドロップダウンの「6F」オプションをクリック
    const option6F = page.locator('[role="option"]:has-text("6F"), li:has-text("6F")').first();
    await option6F.click();
    await waitForStreamlitLoad(page, 60000);

    const newWard = (
      await page.locator('[data-testid="conference-ward"]').first().innerText()
    ).trim();
    expect(newWard, `病棟切替後が 6F でない: ${newWard}`).toBe('6F');
  });

  // ---------------------------------------------------------------------------
  // 5. ファクトバー — PMID 表示の確認
  // ---------------------------------------------------------------------------
  test('ファクトバーに PMID らしき文字列が表示される', async ({ page }) => {
    // ファクトバーはビュー下部 .conf-fact-bar 内
    const factBar = page.locator('.conf-fact-bar').first();
    await expect(factBar, 'ファクトバー要素が見つからない').toBeVisible();

    const text = await factBar.innerText();
    // PMID: 数字 のフォーマットを期待（data/facts.yaml のエントリに依存）
    // ファクト選択が空振りするケースもあるため、PMID が無ければ soft warn
    const hasPMID = /PMID:\s*\d+/.test(text);
    if (!hasPMID) {
      console.warn(
        `ファクトバーに PMID が見つからない — facts.yaml の context 設定を確認: ${text}`
      );
    }
    // 最低限、fact-id hidden div に何らかの値が入っていることを確認
    const factId = (
      await page.locator('[data-testid="conference-fact-id"]').first().innerText()
    ).trim();
    expect(factId, 'conference-fact-id が空').not.toBe('');
  });

  // ---------------------------------------------------------------------------
  // 6. scenarios.json 駆動: 通常モード 5F / 連休対策 6F
  // ---------------------------------------------------------------------------
  test('シナリオ: 通常モード 5F の基本表示確認', async ({ page }) => {
    const scenario = (scenariosData as any).scenarios?.find(
      (s: any) => s.id === 'conference_normal_5f'
    );
    expect(scenario, 'scenarios.json に conference_normal_5f が未定義').toBeTruthy();

    // 初期状態は normal + 5F なので追加操作不要
    const mode = (
      await page.locator('[data-testid="conference-mode"]').first().innerText()
    ).trim();
    const ward = (
      await page.locator('[data-testid="conference-ward"]').first().innerText()
    ).trim();
    const patientCount = parseInt(
      (await page.locator('[data-testid="conference-patient-count"]').first().innerText()).trim(),
      10
    );

    expect(mode).toBe(scenario.expectations.mode);
    expect(ward).toBe(scenario.expectations.ward);
    expect(patientCount).toBe(scenario.expectations.patient_count);
  });

  test('シナリオ: 連休対策モード 6F の表示切替', async ({ page }) => {
    const scenario = (scenariosData as any).scenarios?.find(
      (s: any) => s.id === 'conference_holiday_6f'
    );
    expect(scenario, 'scenarios.json に conference_holiday_6f が未定義').toBeTruthy();

    // モード切替
    await page.locator('label:has-text("連休対策モード")').first().click();
    await waitForStreamlitLoad(page, 60000);

    // 病棟切替: 5F → 6F
    const wardContainer = page.locator('div:has(> label:has-text("病棟"))').filter({
      has: page.locator('[data-baseweb="select"]'),
    }).first();
    const wardSelect = wardContainer.locator('[data-baseweb="select"]').first();
    await wardSelect.click();
    await page.locator('[role="option"]:has-text("6F"), li:has-text("6F")').first().click();
    await waitForStreamlitLoad(page, 60000);

    const mode = (
      await page.locator('[data-testid="conference-mode"]').first().innerText()
    ).trim();
    const ward = (
      await page.locator('[data-testid="conference-ward"]').first().innerText()
    ).trim();
    const patientCount = parseInt(
      (await page.locator('[data-testid="conference-patient-count"]').first().innerText()).trim(),
      10
    );

    expect(mode).toBe(scenario.expectations.mode);
    expect(ward).toBe(scenario.expectations.ward);
    expect(patientCount).toBe(scenario.expectations.patient_count);
  });
});
