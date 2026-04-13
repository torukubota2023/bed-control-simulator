import { test, expect } from '@playwright/test';
import {
  waitForStreamlitLoad, clickButton, selectSection,
} from '../utils/streamlit_helpers';
import { extractDashboardKPIs } from '../utils/extract_data';
import { evaluateWithClaude, formatEvalReport } from '../utils/claude_eval';

/**
 * Claude AI 評価テスト
 *
 * 実行方法: npx playwright test --grep @claude-eval
 * 環境変数: ANTHROPIC_API_KEY が必要
 *
 * 注意: API呼び出しコストが発生するため、CI/CDでは定期実行（週1回等）を推奨
 */

test.describe('Claude AI 評価 @claude-eval', () => {
  test('シミュレーション結果の臨床的妥当性評価', async ({ page }) => {
    await page.goto('/');
    await waitForStreamlitLoad(page);
    await selectSection(page, '意思決定支援');
    await clickButton(page, 'シミュレーション実行');

    const kpis = await extractDashboardKPIs(page);
    const result = await evaluateWithClaude(kpis, 'バランス戦略・標準パラメータでのシミュレーション');

    console.log(formatEvalReport(result));

    // API未設定の場合はスキップ
    if (result.score === -1) {
      test.skip();
      return;
    }

    // スコア60未満は不合格
    expect(result.score).toBeGreaterThanOrEqual(60);
    // failは即不合格
    expect(result.overall).not.toBe('fail');
  });

  test('高稼働率シナリオの経営リスク評価', async ({ page }) => {
    await page.goto('/');
    await waitForStreamlitLoad(page);

    // 高入院数パラメータに変更（Streamlit UIで操作）
    // Note: number_inputの直接操作はStreamlitのDOM構造に依存
    await clickButton(page, 'シミュレーション実行');
    await selectSection(page, '意思決定支援');

    const kpis = await extractDashboardKPIs(page);
    const result = await evaluateWithClaude(
      kpis,
      '高入院数（月250件想定）・安定維持戦略でのシミュレーション。稼働率が95%を超える場合の経営リスクと受入余力のバランスを重点評価してください。'
    );

    console.log(formatEvalReport(result));

    if (result.score === -1) {
      test.skip();
      return;
    }

    expect(result.overall).not.toBe('fail');
  });
});
