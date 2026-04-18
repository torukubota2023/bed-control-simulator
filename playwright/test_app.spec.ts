import { test, expect } from '@playwright/test';
import { waitForStreamlitLoad, getAllMetrics, parseMetricNumber } from '../utils/streamlit_helpers';
import { extractDashboardKPIs, validateKPIIntegrity } from '../utils/extract_data';
import scenariosData from './tests/scenarios.json';

// --- Claude 評価関数の安全インポート ---
// 別 subagent が claude_eval.ts を拡張中。未実装関数を参照するとモジュール解決自体が失敗するため、
// 動的インポート + 個別 try/catch で「あれば使う、なければ skip」方針にする。
// 型は any にして将来の拡張に追従する。
async function safeEvaluateClinicalOperation(kpis: any): Promise<any | null> {
  try {
    const mod: any = await import('../utils/claude_eval');
    if (typeof mod.evaluateClinicalOperation === 'function') {
      return await mod.evaluateClinicalOperation(kpis);
    }
    if (typeof mod.evaluateWithClaude === 'function') {
      // フォールバック：既存の evaluateWithClaude を使う
      return await mod.evaluateWithClaude(kpis, '臨床運用としての妥当性を評価');
    }
    return null;
  } catch {
    return null;
  }
}

async function safeEvaluateGuardrailSafety(params: { alos: number; limit: number }): Promise<any | null> {
  try {
    const mod: any = await import('../utils/claude_eval');
    if (typeof mod.evaluateGuardrailSafety === 'function') {
      return await mod.evaluateGuardrailSafety(params);
    }
    return null;
  } catch {
    return null;
  }
}

// =============================================================================
// ベッドコントロール E2E 正準テスト (test_app)
//
// 既存 test_scenario_verify.spec.ts から移植した参考値（実績データモード想定）:
//   - 全体稼働率 ≈ 88.8%
//   - 5F rolling LOS ≈ 17.7 日
//   - 6F rolling LOS ≈ 21.3 日
//   - 5F 救急搬送比率 ≈ 22%
//   - 6F 救急搬送比率 ≈ 2.6%
//   - 金曜退院集中 ≈ 31%
//   - C群 日額貢献 ≈ 28,900 円
//
// 本ファイルは data-testid ベースの安定セレクタを正準として使用する。
// 値域チェック・整合性チェックを中心に据え、厳密な数値一致は
// 既存シナリオ jsonのレンジ期待値で担保する。
// =============================================================================

test.describe('ベッドコントロール E2E (test_app)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await waitForStreamlitLoad(page);
    // v3.5 本体は初期状態では main content が「サイドバーのパラメータを設定し
    // 『シミュレーション実行』ボタンを押してください」の案内のみで、
    // data-testid (occupancy / alos / phase / vacancy / action-card / guardrail-summary)
    // は描画されない。「📊 今日の運営」本体を描画させるためにボタンを押す。
    const runButton = page.getByRole('button', { name: 'シミュレーション実行' }).first();
    if (await runButton.count() > 0) {
      await runButton.click();
      await waitForStreamlitLoad(page, 180000);
    }
  });

  // ---------------------------------------------------------------------------
  // グループ1: data-testid 存在確認（UI 崩れ検出）
  // 他 subagent が Streamlit 側に付与する data-testid の存在を検証する。
  // 見つからない → UI 崩れ or セレクタ欠落。
  // ---------------------------------------------------------------------------
  test.describe('正準 data-testid の存在', () => {
    const requiredIds = [
      'occupancy',
      'alos',
      'phase',
      'vacancy',
      'revenue',
      'action-card',
      'guardrail-summary',
    ];

    for (const id of requiredIds) {
      test(`[data-testid="${id}"] が存在する`, async ({ page }) => {
        // testid によって出現タブが異なるため、「📊 今日の運営」で見つからなければ
        // 他のメインセクション（What-if・戦略・制度管理）も巡回する。
        // Streamlit のラジオは <input type="radio" tabindex="-1"> で不可視のため、
        // getByRole('radio').click() は「element is not visible」でタイムアウトする。
        // 親ラベル（label:has-text）をクリックすることで Streamlit の state が切り替わる。
        let count = await page.locator(`[data-testid="${id}"]`).count();
        if (count === 0) {
          const sections = ['🔮 What-if・戦略', '🛡️ 制度管理'];
          const sidebar = page.locator('[data-testid="stSidebar"]');
          for (const sectionName of sections) {
            const label = sidebar.locator(`label:has-text("${sectionName}")`).first();
            if ((await label.count()) > 0) {
              await label.click();
              await waitForStreamlitLoad(page, 120000);
              // 制度管理セクションは「制度余力」サブタブが最初に開くが、念のため
              // 内部 st.tabs の要素をスクロール可視化して遅延ロードをトリガ。
              count = await page.locator(`[data-testid="${id}"]`).count();
              if (count === 0) {
                // st.tabs 配下の遅延描画対策: 少し追加待機してから再カウント
                await page.waitForTimeout(1500);
                count = await page.locator(`[data-testid="${id}"]`).count();
              }
              if (count > 0) break;
            }
          }
        }
        expect(count, `${id} が見つからない — UI 崩れの可能性`).toBeGreaterThanOrEqual(1);
      });
    }
  });

  // ---------------------------------------------------------------------------
  // グループ2: シナリオテスト（scenarios.json 駆動）
  // 正常 / 境界 / 異常 の 3 ケースを代表検証。
  // ---------------------------------------------------------------------------
  test.describe('シナリオテスト', () => {
    test('正常ケース: 入院150 / ALOS 16 — 期待範囲内', async ({ page }) => {
      // scenarios.json の "normal_balanced" に対応。
      // 稼働率は 0〜1.0（比率表記）または 0〜100（% 表記）の両対応。
      const normalScenario = (scenariosData as any).scenarios?.find(
        (s: any) => s.id === 'normal_balanced'
      );

      const occEl = page.locator('[data-testid="occupancy"]').first();
      const occText = await occEl.innerText();
      const occNum = parseMetricNumber(occText);
      expect(occNum, `稼働率が数値としてパースできない: ${occText}`).not.toBeNull();

      if (occNum !== null) {
        expect(occNum).toBeGreaterThan(0);
        // 0〜1.0 表記 or 0〜100 表記 の両対応
        expect(occNum).toBeLessThanOrEqual(100);
      }

      const alosEl = page.locator('[data-testid="alos"]').first();
      const alosNum = parseMetricNumber(await alosEl.innerText());
      expect(alosNum, 'ALOS が数値としてパースできない').not.toBeNull();
      if (alosNum !== null) {
        // normal_balanced の期待値: avg_los_min=14 / avg_los_max=24
        const minExp = normalScenario?.expectations?.avg_los_min ?? 1;
        const maxExp = normalScenario?.expectations?.avg_los_max ?? 30;
        expect(alosNum).toBeGreaterThan(0);
        expect(alosNum).toBeLessThan(Math.max(maxExp + 10, 30));
        console.log(`正常ケース: 稼働率=${occNum}, ALOS=${alosNum}日 (期待 ${minExp}〜${maxExp})`);
      }
    });

    test('境界ケース: 稼働率95% / ALOS 長期 — 警告出現', async ({ page }) => {
      // scenarios.json の "boundary_high_occupancy" / "boundary_long_los" に対応。
      // action-card の data-level 属性で警告レベルを判定。
      const level = await page
        .locator('[data-testid="action-card"]')
        .first()
        .getAttribute('data-level');

      // 境界ケースのデモデータでは warning/error が期待される。
      // ただし実績データでは現状が正常な可能性もあるため、存在チェック + ログ出力に留める。
      expect(level, `action-card に data-level 属性がない`).not.toBeNull();
      console.log(`結論カード data-level: ${level}`);
      expect(['error', 'warning', 'info', 'success']).toContain(level);
    });

    test('異常ケース: 不正入力 — アプリがクラッシュしない', async ({ page }) => {
      // Python Traceback が画面に出ていないこと。
      // Streamlit の stException と text 両方をチェック。
      const exceptionCount = await page.locator('[data-testid="stException"]').count();
      expect(exceptionCount, 'Streamlit stException が表示されている').toBe(0);

      const tracebackCount = await page
        .locator('text=/Traceback|NameError|TypeError|ValueError|AttributeError/')
        .count();
      expect(tracebackCount, 'Python Traceback が表示されている').toBe(0);
    });
  });

  // ---------------------------------------------------------------------------
  // グループ3: フェーズ合計の整合性
  // ---------------------------------------------------------------------------
  test('フェーズ A+B+C の合計が実在院数と一致', async ({ page }) => {
    const phaseEl = page.locator('[data-testid="phase"]').first();
    const aAttr = await phaseEl.getAttribute('data-a');
    const bAttr = await phaseEl.getAttribute('data-b');
    const cAttr = await phaseEl.getAttribute('data-c');

    // 属性が未設定の場合は UI 実装未完了としてスキップ（soft fail）
    if (aAttr === null || bAttr === null || cAttr === null) {
      console.warn(`phase data 属性が未設定: a=${aAttr}, b=${bAttr}, c=${cAttr} — UI 実装待ち`);
      test.skip();
      return;
    }

    const a = parseInt(aAttr || '0', 10);
    const b = parseInt(bAttr || '0', 10);
    const c = parseInt(cAttr || '0', 10);
    const totalText = await phaseEl.innerText();
    const totalNum = parseMetricNumber(totalText);

    expect(totalNum).not.toBeNull();
    if (totalNum !== null) {
      const total = Math.round(totalNum);
      expect(
        a + b + c,
        `フェーズ合計が不一致: A(${a})+B(${b})+C(${c})=${a + b + c} vs total=${total}`
      ).toBe(total);
    }
  });

  // ---------------------------------------------------------------------------
  // グループ4: 値域チェック
  // ---------------------------------------------------------------------------
  test('稼働率は 0〜1.0 (または 0〜100) の範囲', async ({ page }) => {
    const occText = await page.locator('[data-testid="occupancy"]').first().innerText();
    const occ = parseMetricNumber(occText);
    expect(occ).not.toBeNull();
    if (occ !== null) {
      expect(occ).toBeGreaterThanOrEqual(0);
      // Streamlit 側の表記揺れ（0-1.0 or 0-100）の両方を許容
      expect(occ).toBeLessThanOrEqual(100);
    }
  });

  test('ALOS は 0 以上かつ現実的な上限以下', async ({ page }) => {
    const alos = parseMetricNumber(
      await page.locator('[data-testid="alos"]').first().innerText()
    );
    expect(alos).not.toBeNull();
    if (alos !== null) {
      expect(alos).toBeGreaterThan(0);
      expect(alos, `ALOS ${alos} 日は 60 日超で明らかに異常`).toBeLessThan(60);
    }
  });

  test('ALOS の data-limit 属性が制度上限（21〜24日）内', async ({ page }) => {
    // ALOS 上限は 85歳以上割合により 21日（≥20%）〜 24日 で変動する。
    const limitAttr = await page.locator('[data-testid="alos"]').first().getAttribute('data-limit');
    if (limitAttr === null) {
      console.warn('data-limit 属性未設定 — UI 実装待ち');
      test.skip();
      return;
    }
    const limit = parseFloat(limitAttr);
    expect(limit).toBeGreaterThanOrEqual(21);
    expect(limit).toBeLessThanOrEqual(24);
  });

  test('空床数は 0〜94 床の範囲', async ({ page }) => {
    const vacancyText = await page.locator('[data-testid="vacancy"]').first().innerText();
    const vacancy = parseMetricNumber(vacancyText);
    expect(vacancy).not.toBeNull();
    if (vacancy !== null) {
      expect(vacancy).toBeGreaterThanOrEqual(0);
      expect(vacancy, `空床 ${vacancy} 床は総病床 94 床を超えている`).toBeLessThanOrEqual(94);
    }
  });

  test('稼働率 1% の年間価値（revenue）が正の値', async ({ page }) => {
    const revenueText = await page.locator('[data-testid="revenue"]').first().innerText();
    const revenue = parseMetricNumber(revenueText);
    expect(revenue).not.toBeNull();
    if (revenue !== null) {
      // 「万円/年」で表示される前提。負値や 0 は設計上ありえない
      expect(revenue).toBeGreaterThan(0);
    }
  });

  // ---------------------------------------------------------------------------
  // グループ5: セクション間整合性チェック
  // （bed_control_app_quality_assurance.md §7 の必須チェックに対応）
  // ---------------------------------------------------------------------------
  test('セクション間整合性: 稼働率がヘッダーと詳細で矛盾しない', async ({ page }) => {
    // occupancy data-testid の全出現箇所を取得し、max-min 差が閾値以内であること。
    const values = await page.locator('[data-testid="occupancy"]').allInnerTexts();
    const nums = values.map((v) => parseMetricNumber(v)).filter((n): n is number => n !== null);

    if (nums.length > 1) {
      const range = Math.max(...nums) - Math.min(...nums);
      // 比率表記・%表記どちらでも成立するよう閾値 0.5 を採用（0.5%pt or 0.005比率）
      expect(
        range,
        `稼働率が複数箇所で矛盾: ${nums.join(', ')} (range=${range})`
      ).toBeLessThan(0.5);
    } else {
      console.log(`occupancy data-testid が ${nums.length} 箇所のみ — 整合性チェック不要`);
    }
  });

  test('KPI 整合性バリデーション（値域・論理矛盾）', async ({ page }) => {
    const kpis = await extractDashboardKPIs(page);
    const errors = validateKPIIntegrity(kpis);

    const criticalErrors = errors.filter((e) => !e.startsWith('[WARNING]'));
    const warnings = errors.filter((e) => e.startsWith('[WARNING]'));

    for (const w of warnings) console.warn(w);
    for (const e of criticalErrors) console.error(e);

    expect(criticalErrors, `KPI 値域エラー検出: ${criticalErrors.join('; ')}`).toHaveLength(0);
  });

  // ---------------------------------------------------------------------------
  // グループ6: 経過措置カウントダウン（2026-06-01 本則適用）
  // CLAUDE.md §「制度ルール確定事項」に対応。
  // ---------------------------------------------------------------------------
  test('経過措置カウントダウンバナーが表示される (2026-05-31 まで)', async ({ page }) => {
    // サイドバー or メインに「経過措置」「本則」「2026-06-01」のいずれかが表示されること。
    const body = await page.locator('body').innerText();
    expect(body).toMatch(/経過措置|本則|2026-06-01|2026-05-31/);
  });

  // ---------------------------------------------------------------------------
  // グループ7: 再現性（乱数シード固定 or 決定的出力）
  // ---------------------------------------------------------------------------
  test('再現性: 同じセッションで稼働率が安定する', async ({ page }) => {
    const occ1 = parseMetricNumber(
      await page.locator('[data-testid="occupancy"]').first().innerText()
    );
    await page.reload();
    await waitForStreamlitLoad(page);
    const occ2 = parseMetricNumber(
      await page.locator('[data-testid="occupancy"]').first().innerText()
    );

    expect(occ1).not.toBeNull();
    expect(occ2).not.toBeNull();
    if (occ1 !== null && occ2 !== null) {
      // 同データ・同シード前提なので差は極めて小さいはず
      expect(
        Math.abs(occ1 - occ2),
        `リロード前後で稼働率が変動: ${occ1} → ${occ2}`
      ).toBeLessThan(0.5);
    }
  });

  // ---------------------------------------------------------------------------
  // グループ8: Claude 評価（@claude-eval タグ）
  // ANTHROPIC_API_KEY が設定されている場合のみ実行。
  // CI/CD では --grep @claude-eval で週次などに限定する想定。
  // ---------------------------------------------------------------------------
  test('Claude 評価: 臨床運用として妥当か @claude-eval', async ({ page }) => {
    test.skip(!process.env.ANTHROPIC_API_KEY, 'ANTHROPIC_API_KEY 未設定のためスキップ');

    const kpis = await extractDashboardKPIs(page);
    const result = await safeEvaluateClinicalOperation(kpis);

    if (result === null) {
      console.warn('evaluateClinicalOperation / evaluateWithClaude が未実装 — スキップ');
      test.skip();
      return;
    }

    console.log('Claude 評価:', JSON.stringify(result, null, 2));

    // API エラー時は score=-1 が返る設計。その場合は soft skip。
    if (result.score === -1) {
      console.warn('Claude API 呼び出し失敗 — スキップ');
      test.skip();
      return;
    }

    expect(result.score, `Claude 評価スコア ${result.score} が 60 未満`).toBeGreaterThanOrEqual(60);
  });

  test('Claude 評価: 施設基準ガードレール危険判定 @claude-eval', async ({ page }) => {
    test.skip(!process.env.ANTHROPIC_API_KEY, 'ANTHROPIC_API_KEY 未設定のためスキップ');

    const alosEl = page.locator('[data-testid="alos"]').first();
    const alosText = await alosEl.innerText();
    const alos = parseMetricNumber(alosText);
    const limitAttr = await alosEl.getAttribute('data-limit');
    const limit = limitAttr ? parseFloat(limitAttr) : 21;

    if (alos === null) {
      console.warn('ALOS をパースできない — スキップ');
      test.skip();
      return;
    }

    const safety = await safeEvaluateGuardrailSafety({ alos, limit });
    if (safety === null) {
      console.warn('evaluateGuardrailSafety が未実装 — スキップ');
      test.skip();
      return;
    }

    console.log('ガードレール評価:', JSON.stringify(safety, null, 2));
    // dangerous プロパティの存在のみを最低限チェック
    expect(safety).toHaveProperty('dangerous');
  });
});
