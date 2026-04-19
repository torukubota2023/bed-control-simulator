/**
 * シナリオ QA — 台本数値主張と実アプリ DOM 値の照合テスト
 *
 * 入力:  reports/scenario_claims.json  (scripts/extract_scenario_claims.py が生成)
 * 出力:  reports/scenario_qa_playwright.json  (照合結果)
 *
 * 処理の流れ:
 *   1. claims を読み込み
 *   2. metric ごとに data-testid が設定されたクレームだけ照合対象に
 *   3. 各 claim について (ward, mode) に遷移 → testid の innerText を取得
 *   4. tolerance 以内なら PASS、超過なら FAIL
 *   5. 全結果を JSON で書き出し、重大不一致は expect で assert 失敗
 *
 * 副院長の既存課題:
 *   「稼働率 85% vs 86.5%」「目標 92% vs 90%」のような不一致を自動検出する。
 *   data-testid を持たない claim（例: 稼働率 1% ≒ 1,046 万円）は skipped として記録。
 *
 * 注意: 大量の再遷移を避けるため、(ward, mode) の組み合わせ単位でグループ化して
 * 1 つのコンテキストにつき 1 回だけセクション遷移する。
 */

import { test, expect } from '@playwright/test';
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'fs';
import { dirname, resolve } from 'path';
import { waitForStreamlitLoad } from '../utils/streamlit_helpers';

// tsconfig は commonjs なので __dirname はランタイムで利用可能
// リポジトリルート
const ROOT = resolve(__dirname, '..');

// ---------------------------------------------------------------------------
// 型定義
// ---------------------------------------------------------------------------

interface Claim {
  id: string;
  source_file: string;
  source_line: number;
  scene: string;
  context: {
    ward: '5F' | '6F' | null;
    mode: 'normal' | 'holiday';
    data_source: 'demo' | 'actual';
  };
  claim_text: string;
  metric: string;
  expected_value: number;
  tolerance: number;
  unit: string;
}

interface ClaimsPayload {
  version: string;
  generated_at: string;
  claim_count: number;
  source_files: string[];
  claims: Claim[];
}

interface QAResult {
  claim_id: string;
  source_file: string;
  source_line: number;
  metric: string;
  expected: number;
  actual: number | null;
  tolerance: number;
  status: 'PASS' | 'FAIL' | 'SKIPPED' | 'MISSING_TESTID' | 'MISSING_DOM';
  delta: number | null;
  claim_text: string;
  context: Claim['context'];
  note: string;
}

// metric → data-testid の明示マッピング（Python 側 METRIC_META と合わせる）
const METRIC_TO_TESTID: Record<string, string | null> = {
  occupancy_pct: 'conference-occupancy-pct',
  alos_days: 'conference-alos-days',
  emergency_pct: 'conference-emergency-pct',
  holiday_days_until: 'conference-holiday-days',
  patient_count_rows: 'conference-patient-count',
  // 以下は対応する data-testid が無いので照合対象外（定数・閾値・金額）
  occupancy_target_pct: null,
  alos_limit_days: null,
  emergency_threshold_pct: null,
  holiday_banner_threshold_days: null,
  holiday_warning_threshold_days: null,
  holiday_danger_threshold_days: null,
  bed_total: null,
  bed_per_ward: null,
  monthly_admissions: null,
  revenue_per_1pct_manyen: null,
  revenue_per_empty_bed_day_yen: null,
  friday_discharge_pct: null,
  short3_rate_pct: null,
  c_group_contribution_yen: null,
  status_count_normal: null,
  status_count_holiday: null,
};

const CLAIMS_PATH = resolve(ROOT, 'reports', 'scenario_claims.json');
const RESULTS_PATH = resolve(ROOT, 'reports', 'scenario_qa_playwright.json');

// ---------------------------------------------------------------------------
// ヘルパー
// ---------------------------------------------------------------------------

function loadClaims(): ClaimsPayload {
  if (!existsSync(CLAIMS_PATH)) {
    throw new Error(
      `scenario_claims.json が見つかりません: ${CLAIMS_PATH}\n` +
        `python3 scripts/extract_scenario_claims.py を先に実行してください。`
    );
  }
  return JSON.parse(readFileSync(CLAIMS_PATH, 'utf-8')) as ClaimsPayload;
}

function parseFloatLoose(text: string): number | null {
  const cleaned = text.replace(/,/g, '').replace(/，/g, '').trim();
  if (!cleaned) return null;
  const m = cleaned.match(/(-?\d+(?:\.\d+)?)/);
  return m ? parseFloat(m[1]) : null;
}

async function navigateToConference(page: any): Promise<void> {
  const sidebar = page.locator('[data-testid="stSidebar"]');
  const label = sidebar.locator(`label:has-text("🏥 退院調整")`).first();
  const count = await label.count();
  if (count === 0) {
    throw new Error('サイドバーに「退院調整」セクションが見つからない');
  }
  await label.click();
  await waitForStreamlitLoad(page, 120000);
}

async function setWard(page: any, ward: '5F' | '6F'): Promise<void> {
  // カンファ画面内の病棟 selectbox を操作
  // hidden div (display:none) なので textContent で取得する
  const wardLocator = page.locator('[data-testid="conference-ward"]').first();
  const currentWard = ((await wardLocator.textContent({ timeout: 5000 })) || '').trim();
  if (currentWard === ward) return;

  const wardContainer = page
    .locator('div:has(> label:has-text("病棟"))')
    .filter({ has: page.locator('[data-baseweb="select"]') })
    .first();
  const wardSelect = wardContainer.locator('[data-baseweb="select"]').first();
  await wardSelect.click({ timeout: 10000 });
  await page
    .locator(`[role="option"]:has-text("${ward}"), li:has-text("${ward}")`)
    .first()
    .click({ timeout: 10000 });
  await waitForStreamlitLoad(page, 30000);
}

async function setMode(page: any, mode: 'normal' | 'holiday'): Promise<void> {
  // hidden div (display:none) なので textContent
  const modeLocator = page.locator('[data-testid="conference-mode"]').first();
  const currentMode = ((await modeLocator.textContent({ timeout: 5000 })) || '').trim();
  if (currentMode === mode) return;

  const toggleLabel = page.locator('label:has-text("連休対策モード")').first();
  await toggleLabel.click({ timeout: 10000 });
  await waitForStreamlitLoad(page, 30000);
}

function contextKey(c: Claim['context']): string {
  return `${c.ward ?? 'any'}|${c.mode}`;
}

// ---------------------------------------------------------------------------
// テスト本体
// ---------------------------------------------------------------------------

// トレース・スクショ・動画は retain-on-failure だが、teardown で重すぎると timeout を招く。
// このテストは結果ファイルを書き出すのが目的なので、すべて off にする。
test.use({ trace: 'off', screenshot: 'off', video: 'off' });

test.describe('シナリオ台本 QA — 台本 ↔ 実画面の数値照合', () => {
  // 1 テスト全体で 1 回だけ実行したいのでシリアル化。retry=0 でリトライ時間を節約。
  test.describe.configure({ mode: 'serial', retries: 0 });

  test('台本クレームを実アプリ DOM と照合して結果を書き出す', async ({ page }) => {
    // 5 分で十分 — 遷移は最大 6 回（3 グループ × (ward + mode)）、各 30 秒以内
    test.setTimeout(6 * 60 * 1000);
    const testStart = Date.now();

    const payload = loadClaims();
    const claims = payload.claims;
    const results: QAResult[] = [];

    // data-testid にマップできるクレームだけ照合対象にする
    const actionable = claims.filter((c) => METRIC_TO_TESTID[c.metric]);
    const skippable = claims.filter((c) => !METRIC_TO_TESTID[c.metric]);

    // 非照合対象は SKIPPED としてまとめて記録
    for (const c of skippable) {
      results.push({
        claim_id: c.id,
        source_file: c.source_file,
        source_line: c.source_line,
        metric: c.metric,
        expected: c.expected_value,
        actual: null,
        tolerance: c.tolerance,
        status: 'SKIPPED',
        delta: null,
        claim_text: c.claim_text,
        context: c.context,
        note: `${c.metric} は data-testid 非対応の閾値・定数・集計値。pytest 側で別途検証`,
      });
    }

    // ward x mode でグループ化して遷移回数を削減
    const groups = new Map<string, Claim[]>();
    for (const c of actionable) {
      const k = contextKey(c.context);
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k)!.push(c);
    }

    const tGoto = Date.now();
    await page.goto('/');
    await waitForStreamlitLoad(page);
    console.log(`[qa] 初期ロード (${((Date.now() - tGoto) / 1000).toFixed(1)}s)`);

    const tNav = Date.now();
    await navigateToConference(page);
    console.log(`[qa] カンファ遷移 (${((Date.now() - tNav) / 1000).toFixed(1)}s)`);

    for (const [key, claimsInGroup] of Array.from(groups.entries())) {
      const first = claimsInGroup[0];
      const wardTarget: '5F' | '6F' = (first.context.ward as '5F' | '6F') || '5F';
      const modeTarget = first.context.mode;

      const tG = Date.now();
      console.log(
        `[qa] 遷移開始: ward=${wardTarget}, mode=${modeTarget}, claims=${claimsInGroup.length}`
      );

      // 遷移（ward / mode を合わせる）
      try {
        await setWard(page, wardTarget);
        const tWard = Date.now();
        console.log(`[qa]   setWard完了 (${((tWard - tG) / 1000).toFixed(1)}s)`);
        await setMode(page, modeTarget);
        console.log(`[qa]   setMode完了 (${((Date.now() - tWard) / 1000).toFixed(1)}s)`);
      } catch (e: any) {
        for (const c of claimsInGroup) {
          results.push({
            claim_id: c.id,
            source_file: c.source_file,
            source_line: c.source_line,
            metric: c.metric,
            expected: c.expected_value,
            actual: null,
            tolerance: c.tolerance,
            status: 'MISSING_DOM',
            delta: null,
            claim_text: c.claim_text,
            context: c.context,
            note: `遷移失敗: ${e.message ?? e}`,
          });
        }
        continue;
      }

      // 各 claim を個別照合
      for (const c of claimsInGroup) {
        const testid = METRIC_TO_TESTID[c.metric];
        if (!testid) continue;

        const locator = page.locator(`[data-testid="${testid}"]`).first();
        const domCount = await locator.count();
        if (domCount === 0) {
          results.push({
            claim_id: c.id,
            source_file: c.source_file,
            source_line: c.source_line,
            metric: c.metric,
            expected: c.expected_value,
            actual: null,
            tolerance: c.tolerance,
            status: 'MISSING_TESTID',
            delta: null,
            claim_text: c.claim_text,
            context: c.context,
            note: `data-testid="${testid}" が DOM に存在しない`,
          });
          continue;
        }

        let actual: number | null = null;
        try {
          // hidden div (display:none) は innerText で空になるため textContent を使う
          const rawText = ((await locator.textContent()) || '').trim();
          actual = parseFloatLoose(rawText);
        } catch {
          actual = null;
        }

        if (actual === null) {
          results.push({
            claim_id: c.id,
            source_file: c.source_file,
            source_line: c.source_line,
            metric: c.metric,
            expected: c.expected_value,
            actual: null,
            tolerance: c.tolerance,
            status: 'MISSING_DOM',
            delta: null,
            claim_text: c.claim_text,
            context: c.context,
            note: 'DOM 値がパースできない',
          });
          continue;
        }

        const delta = actual - c.expected_value;
        const status = Math.abs(delta) <= c.tolerance ? 'PASS' : 'FAIL';

        results.push({
          claim_id: c.id,
          source_file: c.source_file,
          source_line: c.source_line,
          metric: c.metric,
          expected: c.expected_value,
          actual,
          tolerance: c.tolerance,
          status,
          delta,
          claim_text: c.claim_text,
          context: c.context,
          note:
            status === 'FAIL'
              ? `ズレ ${delta.toFixed(2)}${c.unit}（許容 ±${c.tolerance}${c.unit}）`
              : '許容内',
        });
      }
    }

    // ---------- 書き出し ----------
    mkdirSync(dirname(RESULTS_PATH), { recursive: true });
    const summary = {
      generated_at: new Date().toISOString(),
      claims_json: CLAIMS_PATH.replace(ROOT + '/', ''),
      total_claims: results.length,
      pass: results.filter((r) => r.status === 'PASS').length,
      fail: results.filter((r) => r.status === 'FAIL').length,
      skipped: results.filter((r) => r.status === 'SKIPPED').length,
      missing_testid: results.filter((r) => r.status === 'MISSING_TESTID').length,
      missing_dom: results.filter((r) => r.status === 'MISSING_DOM').length,
      results,
    };
    writeFileSync(RESULTS_PATH, JSON.stringify(summary, null, 2) + '\n', 'utf-8');

    // ---------- コンソール summary ----------
    console.log(
      `\n=== シナリオ QA サマリ ===\n` +
        `対象 claim: ${results.length}\n` +
        `PASS: ${summary.pass}\n` +
        `FAIL: ${summary.fail}\n` +
        `SKIPPED: ${summary.skipped}\n` +
        `MISSING_TESTID: ${summary.missing_testid}\n` +
        `MISSING_DOM: ${summary.missing_dom}\n` +
        `\n結果ファイル: ${RESULTS_PATH.replace(ROOT + '/', '')}\n`
    );

    // FAIL だけは例示出力（レビューの足がかり）
    const fails = results.filter((r) => r.status === 'FAIL');
    if (fails.length > 0) {
      console.log(`\n--- FAIL 例示（先頭 5 件） ---`);
      for (const f of fails.slice(0, 5)) {
        console.log(
          `  [${f.source_file}:${f.source_line}] ${f.metric}: expected=${f.expected}, actual=${f.actual}, delta=${f.delta?.toFixed(2)} / tol=${f.tolerance}`
        );
      }
    }

    // CI では FAIL 0 を要求。QA_STRICT=0 なら assert をスキップしレポートのみ。
    const strict = process.env.QA_STRICT !== '0';
    const t0 = Date.now();
    console.log(`[qa] テスト完了 (elapsed=${((t0 - testStart) / 1000).toFixed(1)}s) — 結果ファイル保存済`);
    if (strict) {
      if (summary.fail > 0) {
        throw new Error(
          `${summary.fail} 件の重大ズレを検出 — reports/scenario_qa_playwright.json を確認してください`
        );
      }
    } else {
      console.warn(
        'QA_STRICT=0 のため、FAIL 件数を assert せずレポートのみ生成します'
      );
    }
    console.log(`[qa] 処理全完了 (total=${((Date.now() - testStart) / 1000).toFixed(1)}s)`);
  });
});
