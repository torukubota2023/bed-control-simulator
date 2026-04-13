/**
 * Claude評価モジュール — Playwright E2Eテストの結果をClaude APIで評価する
 *
 * 使い方:
 *   1. Playwrightテストで extractDashboardKPIs() でKPIを取得
 *   2. evaluateWithClaude(kpis) でClaudeに評価を依頼
 *   3. 結果をテストレポートに含める
 *
 * 環境変数:
 *   ANTHROPIC_API_KEY — Claude API key
 *
 * 注意: CI/CDではAPI呼び出しコストが発生するため、
 *        通常のテスト実行では --grep @claude-eval でフィルタして使う
 */

import { DashboardKPIs } from './extract_data';

interface ClaudeEvalResult {
  overall: 'pass' | 'warning' | 'fail';
  score: number;  // 0-100
  findings: string[];
  recommendation: string;
  raw_response: string;
}

/**
 * Build evaluation prompt from KPI data
 */
function buildEvalPrompt(kpis: DashboardKPIs, context?: string): string {
  const lines: string[] = [
    'あなたは94床の地域包括医療病棟（おもろまちメディカルセンター）の病床運営コンサルタントです。',
    'ベッドコントロールシミュレーターの出力結果を評価してください。',
    '',
    '## 施設情報',
    '- 総病床数: 94床（5F: 47床、6F: 47床）',
    '- 病棟種別: 地域包括医療病棟',
    '- 目標稼働率: 90%',
    '- 平均在院日数上限: 21日（85歳以上20%以上の場合）〜24日',
    '- 救急搬送後患者割合: 各病棟15%以上が必要',
    '- 月間入院数: 約150件/月',
    '',
    '## 今回の出力結果',
  ];

  if (kpis.occupancyRate !== undefined) lines.push(`- 稼働率: ${kpis.occupancyRate}%`);
  if (kpis.avgLOS !== undefined) lines.push(`- 平均在院日数: ${kpis.avgLOS}日`);
  if (kpis.losHeadroom !== undefined) lines.push(`- LOS余力: ${kpis.losHeadroom}日`);
  if (kpis.morningCapacity !== undefined) lines.push(`- 翌朝受入余力: ${kpis.morningCapacity}床`);
  if (kpis.threeDayMin !== undefined) lines.push(`- 3診療日最小: ${kpis.threeDayMin}床`);
  if (kpis.emergencyRatio5F !== undefined) lines.push(`- 救急搬送比率 5F: ${kpis.emergencyRatio5F}%`);
  if (kpis.emergencyRatio6F !== undefined) lines.push(`- 救急搬送比率 6F: ${kpis.emergencyRatio6F}%`);
  if (kpis.phaseA !== undefined) lines.push(`- A群構成比: ${kpis.phaseA}%`);
  if (kpis.phaseB !== undefined) lines.push(`- B群構成比: ${kpis.phaseB}%`);
  if (kpis.phaseC !== undefined) lines.push(`- C群構成比: ${kpis.phaseC}%`);
  if (kpis.patientCount !== undefined) lines.push(`- 在院患者数: ${kpis.patientCount}名`);
  if (kpis.actionCardLevel) lines.push(`- 結論カードレベル: ${kpis.actionCardLevel}`);
  if (kpis.actionCardTitle) lines.push(`- 結論カード: ${kpis.actionCardTitle}`);
  if (kpis.guardrailStatus) lines.push(`- 施設基準チェック: ${kpis.guardrailStatus}`);

  if (context) {
    lines.push('', '## テスト文脈', context);
  }

  lines.push(
    '',
    '## 評価してほしいこと',
    '',
    '以下の観点で評価し、JSON形式で回答してください。',
    '',
    '1. **数値の妥当性**: 各指標が臨床的・制度的に妥当な範囲か',
    '2. **数値間の整合性**: 稼働率と在院患者数、フェーズ構成比の合計、翌朝受入余力と3診療日最小の関係等',
    '3. **結論カードの適切性**: KPIの状況に対して結論カードのレベル（critical/warning/info/success）は適切か',
    '4. **経営リスク**: 稼働率90%目標に対して、現状のリスクは何か',
    '5. **制度リスク**: 平均在院日数上限・救急搬送比率15%に対する充足状況',
    '',
    '回答形式（JSONのみ、他のテキスト不要）:',
    '```json',
    '{',
    '  "overall": "pass" | "warning" | "fail",',
    '  "score": 0-100,',
    '  "findings": ["問題点1", "問題点2", ...],',
    '  "recommendation": "総合的な推奨アクション"',
    '}',
    '```',
  );

  return lines.join('\n');
}

/**
 * Call Claude API for evaluation
 */
export async function evaluateWithClaude(
  kpis: DashboardKPIs,
  context?: string,
): Promise<ClaudeEvalResult> {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    return {
      overall: 'warning',
      score: -1,
      findings: ['ANTHROPIC_API_KEY が未設定のため Claude 評価をスキップしました'],
      recommendation: '環境変数 ANTHROPIC_API_KEY を設定してください',
      raw_response: '',
    };
  }

  const prompt = buildEvalPrompt(kpis, context);

  try {
    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 1024,
        messages: [{ role: 'user', content: prompt }],
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      return {
        overall: 'warning',
        score: -1,
        findings: [`Claude API エラー: ${response.status} ${errorText}`],
        recommendation: 'APIキーとネットワークを確認してください',
        raw_response: errorText,
      };
    }

    const data = await response.json() as any;
    const rawText = data.content?.[0]?.text || '';

    // Parse JSON from response
    const jsonMatch = rawText.match(/\{[\s\S]*\}/);
    if (!jsonMatch) {
      return {
        overall: 'warning',
        score: -1,
        findings: ['Claude の応答からJSONを解析できませんでした'],
        recommendation: rawText.substring(0, 200),
        raw_response: rawText,
      };
    }

    const parsed = JSON.parse(jsonMatch[0]);
    return {
      overall: parsed.overall || 'warning',
      score: parsed.score ?? -1,
      findings: parsed.findings || [],
      recommendation: parsed.recommendation || '',
      raw_response: rawText,
    };
  } catch (error: any) {
    return {
      overall: 'warning',
      score: -1,
      findings: [`Claude 評価中にエラー: ${error.message}`],
      recommendation: 'エラーの詳細を確認してください',
      raw_response: String(error),
    };
  }
}

/**
 * Format evaluation result for test report
 */
export function formatEvalReport(result: ClaudeEvalResult): string {
  const statusEmoji = { pass: '✅', warning: '⚠️', fail: '❌' };
  const lines = [
    `## Claude 評価結果: ${statusEmoji[result.overall] || '❓'} ${result.overall.toUpperCase()}`,
    `スコア: ${result.score}/100`,
    '',
    '### 検出された問題:',
  ];

  if (result.findings.length === 0) {
    lines.push('- なし');
  } else {
    for (const f of result.findings) {
      lines.push(`- ${f}`);
    }
  }

  lines.push('', `### 推奨: ${result.recommendation}`);
  return lines.join('\n');
}
