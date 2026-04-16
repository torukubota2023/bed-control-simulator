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
 *
 * 拡張 (2026-04-17): 医療経営アプリとしての妥当性評価 6 観点を追加
 *   1. evaluateCrossSectionConsistency  — セクション間整合性
 *   2. evaluateGuardrailSafety           — 施設基準ガードレール危険判定
 *   3. evaluateClinicalOperation         — 臨床運用妥当性（詰まりかけ検出）
 *   4. detectAlosDiscontinuity           — Day 5/6 不連続点検出（純粋ロジック）
 *   5. evaluateTransitionalPeriod        — 経過措置カウントダウン（純粋ロジック）
 *   6. generateImprovementSuggestions    — 改善提案（自然言語コメント）
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
 * Internal: call Claude API with a plain text prompt and return the raw response text.
 * Returns { ok: false, errorMessage } if API key is missing or request fails.
 */
interface RawClaudeResponse {
  ok: boolean;
  text: string;
  errorMessage?: string;
  skipped?: boolean;  // true when ANTHROPIC_API_KEY is not set
}

async function callClaudeAPI(prompt: string, maxTokens: number = 1024): Promise<RawClaudeResponse> {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    return {
      ok: false,
      text: '',
      errorMessage: 'ANTHROPIC_API_KEY が未設定のため Claude 評価をスキップしました',
      skipped: true,
    };
  }

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
        max_tokens: maxTokens,
        messages: [{ role: 'user', content: prompt }],
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      return {
        ok: false,
        text: errorText,
        errorMessage: `Claude API エラー: ${response.status} ${errorText}`,
      };
    }

    const data = await response.json() as any;
    const rawText = data.content?.[0]?.text || '';
    return { ok: true, text: rawText };
  } catch (error: any) {
    return {
      ok: false,
      text: '',
      errorMessage: `Claude 評価中にエラー: ${error.message}`,
    };
  }
}

/**
 * Internal: try to extract the first JSON object from a raw text response.
 */
function extractJSON(rawText: string): any | null {
  const jsonMatch = rawText.match(/\{[\s\S]*\}/);
  if (!jsonMatch) return null;
  try {
    return JSON.parse(jsonMatch[0]);
  } catch {
    return null;
  }
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
  const prompt = buildEvalPrompt(kpis, context);
  const raw = await callClaudeAPI(prompt, 1024);

  if (!raw.ok) {
    return {
      overall: 'warning',
      score: -1,
      findings: [raw.errorMessage || 'Claude API 呼び出しに失敗しました'],
      recommendation: raw.skipped
        ? '環境変数 ANTHROPIC_API_KEY を設定してください'
        : 'APIキーとネットワークを確認してください',
      raw_response: raw.text,
    };
  }

  const parsed = extractJSON(raw.text);
  if (!parsed) {
    return {
      overall: 'warning',
      score: -1,
      findings: ['Claude の応答からJSONを解析できませんでした'],
      recommendation: raw.text.substring(0, 200),
      raw_response: raw.text,
    };
  }

  return {
    overall: parsed.overall || 'warning',
    score: parsed.score ?? -1,
    findings: parsed.findings || [],
    recommendation: parsed.recommendation || '',
    raw_response: raw.text,
  };
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

// ============================================================================
// 追加観点 1: セクション間整合性
// ============================================================================

export interface CrossSectionConsistencyResult {
  consistent: boolean;
  conflicts: string[];
  summary: string;
}

/**
 * 複数セクション（ダッシュボード、C群ビュー、ガードレールビュー等）で
 * 同じKPIが異なる値で表示されていないかを評価する。
 */
export async function evaluateCrossSectionConsistency(
  kpisBySection: Record<string, Record<string, number>>,
): Promise<CrossSectionConsistencyResult> {
  const sectionNames = Object.keys(kpisBySection);

  // Quick local pre-check: collect KPIs that appear in multiple sections and check equality
  const localConflicts: string[] = [];
  const kpiSources: Record<string, Array<{ section: string; value: number }>> = {};
  for (const [section, kpis] of Object.entries(kpisBySection)) {
    for (const [k, v] of Object.entries(kpis)) {
      if (!kpiSources[k]) kpiSources[k] = [];
      kpiSources[k].push({ section, value: v });
    }
  }
  for (const [kpi, sources] of Object.entries(kpiSources)) {
    if (sources.length < 2) continue;
    const first = sources[0].value;
    const diff = sources.some(s => Math.abs(s.value - first) > 0.01);
    if (diff) {
      const detail = sources.map(s => `${s.section}=${s.value}`).join(', ');
      localConflicts.push(`${kpi}: ${detail}`);
    }
  }

  const promptLines: string[] = [
    'あなたは94床の地域包括医療病棟のベッドコントロールアプリをレビューしています。',
    'アプリには複数のセクション（ダッシュボード・C群コントロール・ガードレールチェック等）があり、',
    '同じKPIが複数箇所で表示されることがあります。矛盾があればユーザーの信頼を損ねるため検出してください。',
    '',
    '## 各セクションのKPI',
  ];
  for (const section of sectionNames) {
    promptLines.push(`### ${section}`);
    for (const [k, v] of Object.entries(kpisBySection[section])) {
      promptLines.push(`- ${k}: ${v}`);
    }
  }
  if (localConflicts.length > 0) {
    promptLines.push('', '## ローカル事前チェックで検出された不一致候補');
    localConflicts.forEach(c => promptLines.push(`- ${c}`));
  }
  promptLines.push(
    '',
    '## 回答形式（JSONのみ）',
    '```json',
    '{',
    '  "consistent": true | false,',
    '  "conflicts": ["セクションAとセクションBでXXXが不一致（具体的な差分）", ...],',
    '  "summary": "整合性の総評（1-2文）"',
    '}',
    '```',
  );

  const raw = await callClaudeAPI(promptLines.join('\n'), 1024);

  if (!raw.ok) {
    // API 未設定 or 失敗時は、ローカル事前チェックの結果で返す
    return {
      consistent: localConflicts.length === 0,
      conflicts: localConflicts,
      summary: raw.skipped
        ? 'ANTHROPIC_API_KEY 未設定 — ローカル簡易チェックのみ実施'
        : raw.errorMessage || 'Claude 評価失敗 — ローカル簡易チェックのみ実施',
    };
  }

  const parsed = extractJSON(raw.text);
  if (!parsed) {
    return {
      consistent: localConflicts.length === 0,
      conflicts: localConflicts,
      summary: 'Claude の応答をパースできず — ローカル簡易チェックのみ反映',
    };
  }

  return {
    consistent: parsed.consistent ?? (localConflicts.length === 0),
    conflicts: parsed.conflicts || localConflicts,
    summary: parsed.summary || '',
  };
}

// ============================================================================
// 追加観点 2: 施設基準ガードレール危険判定
// ============================================================================

export interface GuardrailSafetyResult {
  dangerous: boolean;
  level: 'green' | 'yellow' | 'red';
  reasons: string[];
}

/**
 * 平均在院日数 21 日（施設基準上限）、救急搬送後患者割合 15% 本則などの
 * ガードレールに対して現在の KPI が危険か判定する。
 */
export async function evaluateGuardrailSafety(
  kpis: { alos?: number; limit?: number; emergency_ratio?: number; occupancy?: number },
): Promise<GuardrailSafetyResult> {
  // Local deterministic pre-check
  const localReasons: string[] = [];
  let localLevel: 'green' | 'yellow' | 'red' = 'green';

  const alos = kpis.alos;
  const limit = kpis.limit ?? 21;
  const emergencyRatio = kpis.emergency_ratio;
  const occupancy = kpis.occupancy;

  if (alos !== undefined) {
    if (alos > limit) {
      localLevel = 'red';
      localReasons.push(`平均在院日数 ${alos}日 が制度上限 ${limit}日 を超過`);
    } else if (alos > limit - 1.5) {
      if (localLevel !== 'red') localLevel = 'yellow';
      localReasons.push(`平均在院日数 ${alos}日 が制度上限 ${limit}日 に接近（余力1.5日未満）`);
    }
  }
  if (emergencyRatio !== undefined) {
    if (emergencyRatio < 15) {
      localLevel = 'red';
      localReasons.push(`救急搬送後患者割合 ${emergencyRatio}% が本則 15% を下回る`);
    } else if (emergencyRatio < 17) {
      if (localLevel !== 'red') localLevel = 'yellow';
      localReasons.push(`救急搬送後患者割合 ${emergencyRatio}% が 15% 近傍（余裕 2pt 未満）`);
    }
  }
  if (occupancy !== undefined) {
    const occPct = occupancy <= 1 ? occupancy * 100 : occupancy;
    if (occPct >= 98) {
      if (localLevel !== 'red') localLevel = 'yellow';
      localReasons.push(`稼働率 ${occPct.toFixed(1)}% が極端に高い（受入余力逼迫）`);
    }
  }

  const promptLines = [
    'あなたは94床の地域包括医療病棟の施設基準コンプライアンス専門家です。',
    '以下の KPI に対して施設基準上のリスクを判定してください。',
    '',
    '## 施設基準ルール (2026-06-01 以降本則)',
    '- 平均在院日数: 21 日以下（85歳以上20%以上の場合は 24日 まで）',
    '- 救急搬送後患者割合: 各病棟 15% 以上',
    '- 稼働率目標: 90%',
    '',
    '## KPI',
    `- 平均在院日数: ${alos ?? '未計測'}`,
    `- ALOS 上限: ${limit}`,
    `- 救急搬送比率: ${emergencyRatio ?? '未計測'}`,
    `- 稼働率: ${occupancy ?? '未計測'}`,
    '',
    '## ローカル事前判定',
    `- level: ${localLevel}`,
    `- reasons: ${localReasons.length > 0 ? localReasons.join(' / ') : '(なし)'}`,
    '',
    '## 回答形式（JSONのみ）',
    '```json',
    '{',
    '  "dangerous": true | false,',
    '  "level": "green" | "yellow" | "red",',
    '  "reasons": ["具体的な理由1", ...]',
    '}',
    '```',
  ];

  const raw = await callClaudeAPI(promptLines.join('\n'), 512);
  if (!raw.ok) {
    return {
      dangerous: localLevel === 'red',
      level: localLevel,
      reasons: raw.skipped
        ? ['ANTHROPIC_API_KEY 未設定 — ローカル判定のみ', ...localReasons]
        : [raw.errorMessage || 'Claude 評価失敗', ...localReasons],
    };
  }

  const parsed = extractJSON(raw.text);
  if (!parsed) {
    return {
      dangerous: localLevel === 'red',
      level: localLevel,
      reasons: ['Claude の応答パース失敗 — ローカル判定を採用', ...localReasons],
    };
  }

  const level = (parsed.level as 'green' | 'yellow' | 'red') || localLevel;
  return {
    dangerous: parsed.dangerous ?? (level === 'red'),
    level,
    reasons: parsed.reasons || localReasons,
  };
}

// ============================================================================
// 追加観点 3: 臨床運用妥当性（「一見健全だが詰まりかけ」を検出）
// ============================================================================

export interface ClinicalOperationResult {
  score: number;  // 0-100, -1 when skipped
  narrative: string;
  warnings: string[];
}

/**
 * 稼働率や在院日数など「単独で見ると健全に見える」が組み合わせでは詰まりかけなど
 * 危険パターンを示す KPI を自然言語で評価する。
 */
export async function evaluateClinicalOperation(
  kpis: Record<string, any>,
): Promise<ClinicalOperationResult> {
  const promptLines = [
    'あなたは病床運用の専門家です。94床の地域包括医療病棟における KPI を評価します。',
    '各指標は単独では健全に見えても、組み合わせで危険なパターンを示すことがあります。',
    '特に注意すべきパターン:',
    '- 稼働率 95% 超 かつ 平均在院日数 25日 超 → 「詰まりかけ」（退院滞留で回転停止の兆候）',
    '- 稼働率 70% 未満 かつ 救急搬送比率 低 → 「需要消失」',
    '- フェーズC比率が極端に高い → 「DPC 期間III 到達患者が多く収益逓減」',
    '',
    '## KPI',
    '```json',
    JSON.stringify(kpis, null, 2),
    '```',
    '',
    '## 評価してほしいこと',
    '1. 臨床運用として妥当か 0-100 で採点（100 = 理想、50 = 注意、0 = 危険）',
    '2. 危険パターンを言語化した narrative を 2-4 文で記述',
    '3. 個別警告を warnings 配列で列挙（該当なしなら空配列）',
    '',
    '## 回答形式（JSONのみ）',
    '```json',
    '{',
    '  "score": 0-100,',
    '  "narrative": "臨床運用観点での総評（詰まりかけ等の危険パターンを言語化）",',
    '  "warnings": ["警告1", "警告2"]',
    '}',
    '```',
  ];

  const raw = await callClaudeAPI(promptLines.join('\n'), 1024);
  if (!raw.ok) {
    return {
      score: -1,
      narrative: raw.skipped ? 'skipped' : (raw.errorMessage || 'Claude 評価失敗'),
      warnings: raw.skipped ? ['ANTHROPIC_API_KEY 未設定'] : [raw.errorMessage || ''],
    };
  }

  const parsed = extractJSON(raw.text);
  if (!parsed) {
    return {
      score: -1,
      narrative: 'Claude の応答パース失敗',
      warnings: [raw.text.substring(0, 200)],
    };
  }

  return {
    score: typeof parsed.score === 'number' ? parsed.score : -1,
    narrative: parsed.narrative || '',
    warnings: parsed.warnings || [],
  };
}

// ============================================================================
// 追加観点 4: 不連続点検出 (Day 5/6 境界) — 純粋ロジック
// ============================================================================

export interface AlosDiscontinuityResult {
  jump_detected: boolean;
  explanation: string;
}

/**
 * 2026-06-01 以降の本則では、短手3患者が Day 5 までは在院日数の分母に含まれず、
 * Day 6 以降に滞在が延びた瞬間に「入院初日まで遡って全日数」が分母にカウントされる。
 * 結果として Day 5 と Day 6 の境界で LOS 分母が +6 日 jump する不連続点が発生する。
 *
 * current_date が effective_date (既定 2026-06-01) 以降で short3_days >= 6 なら jump_detected = true。
 */
export function detectAlosDiscontinuity(
  short3_days: number,
  current_date: string,
  effective_date?: string,
): AlosDiscontinuityResult {
  const effDate = effective_date || '2026-06-01';
  const current = new Date(current_date);
  const eff = new Date(effDate);

  if (isNaN(current.getTime())) {
    return {
      jump_detected: false,
      explanation: `current_date "${current_date}" を日付としてパースできません`,
    };
  }
  if (isNaN(eff.getTime())) {
    return {
      jump_detected: false,
      explanation: `effective_date "${effDate}" を日付としてパースできません`,
    };
  }

  if (current < eff) {
    return {
      jump_detected: false,
      explanation: `経過措置期間中（${effDate} 未満）のため本則は未適用。不連続点なし。`,
    };
  }

  if (short3_days < 6) {
    return {
      jump_detected: false,
      explanation: `短手3 Day ${short3_days} は分母除外範囲（Day 5 以下）。Day 6 以降で不連続点が発生するが現時点ではなし。`,
    };
  }

  // short3_days >= 6 かつ 本則適用後
  return {
    jump_detected: true,
    explanation:
      `本則適用日 ${effDate} 以降、短手3患者が Day ${short3_days}（>=6）に到達したため、` +
      `入院初日まで遡って全日数（${short3_days}日）が平均在院日数の分母に一気にカウントされます。` +
      `Day 5 → Day 6 の境界で分母が +6 日 jump する不連続点が発生しました。`,
  };
}

// ============================================================================
// 追加観点 5: 経過措置カウントダウン判定 — 純粋ロジック
// ============================================================================

export interface TransitionalPeriodResult {
  status: 'active' | 'warning' | 'error' | 'ended';
  days_remaining: number;
  message: string;
}

/**
 * 令和6改定の経過措置（短手3・救急搬送15% 困難時期除外）は 2026-05-31 で終了、
 * 2026-06-01 以降は本則完全適用。残日数から status を判定する。
 *
 * - 残日数 > 30 日    → active
 * - 30 日以内        → warning
 * - 7 日以内         → error
 * - 0 日未満（超過）  → ended
 */
export function evaluateTransitionalPeriod(
  today: string,
  end_date?: string,
): TransitionalPeriodResult {
  const endStr = end_date || '2026-05-31';
  const todayDate = new Date(today);
  const endDate = new Date(endStr);

  if (isNaN(todayDate.getTime()) || isNaN(endDate.getTime())) {
    return {
      status: 'active',
      days_remaining: NaN,
      message: `日付パース失敗: today="${today}", end_date="${endStr}"`,
    };
  }

  // 日単位差分（切り捨てで日数）
  const msPerDay = 24 * 60 * 60 * 1000;
  const daysRemaining = Math.floor(
    (endDate.getTime() - todayDate.getTime()) / msPerDay,
  );

  if (daysRemaining < 0) {
    return {
      status: 'ended',
      days_remaining: daysRemaining,
      message: `経過措置は ${endStr} で終了済み（${Math.abs(daysRemaining)}日経過）。本則完全適用中。`,
    };
  }
  if (daysRemaining <= 7) {
    return {
      status: 'error',
      days_remaining: daysRemaining,
      message: `経過措置終了まで残り ${daysRemaining}日。本則適用準備を急いでください（${endStr} 終了）。`,
    };
  }
  if (daysRemaining <= 30) {
    return {
      status: 'warning',
      days_remaining: daysRemaining,
      message: `経過措置終了まで残り ${daysRemaining}日。切替準備を進めてください（${endStr} 終了）。`,
    };
  }
  return {
    status: 'active',
    days_remaining: daysRemaining,
    message: `経過措置期間中（${endStr} 終了まで残り ${daysRemaining}日）。`,
  };
}

// ============================================================================
// 追加観点 6: 改善提案（自然言語コメント）
// ============================================================================

/**
 * KPI と任意の運用コンテキストから、改善のヒントを自然言語で生成する。
 */
export async function generateImprovementSuggestions(
  kpis: Record<string, any>,
  context?: string,
): Promise<string> {
  const promptLines = [
    'あなたは94床の地域包括医療病棟の経営コンサルタントです。',
    '以下の KPI を基に、現場で実行可能な改善提案を 3-5 点、短く具体的に提示してください。',
    '',
    '## 制度ルール要約',
    '- ALOS 上限 21日（85歳以上20%以上なら 24日まで）',
    '- 救急搬送後患者割合 15% 以上（2026-06-01 以降は rolling 3ヶ月判定、5F/6F 別）',
    '- 稼働率目標 90%',
    '',
    '## KPI',
    '```json',
    JSON.stringify(kpis, null, 2),
    '```',
  ];

  if (context) {
    promptLines.push('', '## コンテキスト', context);
  }

  promptLines.push(
    '',
    '## 提案フォーマット',
    'Markdown の箇条書き（各項目は 1-2 文）で、数値的な目標や具体的アクションを含めてください。',
    '日本語で記述してください。',
  );

  const raw = await callClaudeAPI(promptLines.join('\n'), 1024);
  if (!raw.ok) {
    if (raw.skipped) {
      return '（ANTHROPIC_API_KEY 未設定のため改善提案をスキップしました）';
    }
    return `（改善提案生成に失敗: ${raw.errorMessage}）`;
  }
  return raw.text.trim();
}
