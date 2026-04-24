import { Page } from '@playwright/test';
import { getAllMetrics, getMetricByLabel, parseMetricNumber, getAlertMessages } from './streamlit_helpers';

/** Dashboard KPI data extracted from the app */
export interface DashboardKPIs {
  occupancyRate?: number;        // 稼働率 (0-100)
  emergencyRatio5F?: number;     // 救急搬送比率 5F
  emergencyRatio6F?: number;     // 救急搬送比率 6F
  morningCapacity?: number;      // 翌朝受入余力
  threeDayMin?: number;          // 3診療日最小
  avgLOS?: number;               // 平均在院日数
  losHeadroom?: number;          // LOS余力
  phaseA?: number;               // A群構成比
  phaseB?: number;               // B群構成比
  phaseC?: number;               // C群構成比
  monthlyRevenue?: number;       // 月次運営貢献額
  actionCardLevel?: string;      // 結論カード level (critical/warning/info/success)
  actionCardTitle?: string;      // 結論カード タイトル
  guardrailStatus?: string;      // 施設基準チェック
  bedCount?: number;             // 病床数
  patientCount?: number;         // 在院患者数
}

/** Extract all dashboard KPIs from the current page */
export async function extractDashboardKPIs(page: Page): Promise<DashboardKPIs> {
  const kpis: DashboardKPIs = {};
  const metrics = await getAllMetrics(page);

  for (const m of metrics) {
    const val = parseMetricNumber(m.value);

    if (m.label.includes('稼働率') && !m.label.includes('月末') && !m.label.includes('目標')) {
      if (val !== null) kpis.occupancyRate = val;
    }
    if (m.label.includes('翌朝受入余力')) {
      if (val !== null) kpis.morningCapacity = val;
    }
    if (m.label.includes('3診療日最小')) {
      if (val !== null) kpis.threeDayMin = val;
    }
    if (m.label.includes('平均在院日数') && !m.label.includes('余力') && !m.label.includes('上限')) {
      if (val !== null) kpis.avgLOS = val;
    }
    if (m.label.includes('在院日数余力') || m.label.includes('LOS余力')) {
      if (val !== null) kpis.losHeadroom = val;
    }
    if (m.label.includes('A群')) {
      if (val !== null) kpis.phaseA = val;
    }
    if (m.label.includes('B群') && !m.label.includes('C群')) {
      if (val !== null) kpis.phaseB = val;
    }
    if (m.label.includes('C群') && !m.label.includes('B群')) {
      if (val !== null) kpis.phaseC = val;
    }
    if (m.label.includes('在院患者')) {
      if (val !== null) kpis.patientCount = val;
    }
    if (m.label.includes('運営貢献')) {
      if (val !== null) kpis.monthlyRevenue = val;
    }
  }

  // Extract action card level from alert elements
  const alerts = await getAlertMessages(page);
  for (const alert of alerts) {
    if (alert.text.includes('今日の一手')) {
      kpis.actionCardTitle = alert.text.split('\n')[0];
      if (alert.type === 'stError') kpis.actionCardLevel = 'critical';
      else if (alert.type === 'stWarning') kpis.actionCardLevel = 'warning';
      else if (alert.type === 'stInfo') kpis.actionCardLevel = 'info';
      else if (alert.type === 'stSuccess') kpis.actionCardLevel = 'success';
    }
  }

  // Extract emergency ratio from KPI strip
  const emergencyMetric = await getMetricByLabel(page, '救急搬送');
  if (emergencyMetric) {
    const parts = emergencyMetric.value.match(/5F:\s*([\d.]+)%.*6F:\s*([\d.]+)%/);
    if (parts) {
      kpis.emergencyRatio5F = parseFloat(parts[1]);
      kpis.emergencyRatio6F = parseFloat(parts[2]);
    }
  }

  return kpis;
}

/** Validate basic data integrity */
export function validateKPIIntegrity(kpis: DashboardKPIs): string[] {
  const errors: string[] = [];

  // Occupancy rate must be 0-100%
  if (kpis.occupancyRate !== undefined) {
    if (kpis.occupancyRate < 0 || kpis.occupancyRate > 100) {
      errors.push(`稼働率が異常値: ${kpis.occupancyRate}% (0-100%の範囲外)`);
    }
  }

  // Average LOS must be positive and reasonable (1-60 days)
  if (kpis.avgLOS !== undefined) {
    if (kpis.avgLOS <= 0 || kpis.avgLOS > 60) {
      errors.push(`平均在院日数が異常値: ${kpis.avgLOS}日 (1-60日の範囲外)`);
    }
  }

  // Phase ratios must sum to ≤100% and be reasonable (>50% total)
  // Note: A+B+C < 100% is expected when unclassified patients exist
  if (kpis.phaseA !== undefined && kpis.phaseB !== undefined && kpis.phaseC !== undefined) {
    const sum = kpis.phaseA + kpis.phaseB + kpis.phaseC;
    if (sum > 105) {
      errors.push(`フェーズ構成比の合計が100%超過: A=${kpis.phaseA}% + B=${kpis.phaseB}% + C=${kpis.phaseC}% = ${sum}%`);
    }
    if (sum < 50) {
      errors.push(`[WARNING] フェーズ構成比の合計が低い: A=${kpis.phaseA}% + B=${kpis.phaseB}% + C=${kpis.phaseC}% = ${sum}% — 未分類患者が多い可能性`);
    }
  }

  // Morning capacity must be non-negative
  if (kpis.morningCapacity !== undefined && kpis.morningCapacity < 0) {
    errors.push(`翌朝受入余力が負値: ${kpis.morningCapacity}床`);
  }

  // 3-day min must be <= morning capacity
  if (kpis.morningCapacity !== undefined && kpis.threeDayMin !== undefined) {
    if (kpis.threeDayMin > kpis.morningCapacity) {
      errors.push(`[WARNING] 3診療日最小(${kpis.threeDayMin})が翌朝受入余力(${kpis.morningCapacity})を超過 — 退院前倒しが必要`);
    }
  }

  // Emergency ratio must be 0-100%
  for (const [ward, ratio] of [['5F', kpis.emergencyRatio5F], ['6F', kpis.emergencyRatio6F]] as const) {
    if (ratio !== undefined && (ratio < 0 || ratio > 100)) {
      errors.push(`${ward}救急搬送比率が異常値: ${ratio}% (0-100%の範囲外)`);
    }
  }

  // Patient count vs bed count consistency
  if (kpis.patientCount !== undefined && kpis.bedCount !== undefined) {
    if (kpis.patientCount > kpis.bedCount * 1.1) {
      errors.push(`在院患者数(${kpis.patientCount})が病床数(${kpis.bedCount})の110%を超過`);
    }
  }

  // LOS headroom warning
  if (kpis.losHeadroom !== undefined && kpis.losHeadroom < 0) {
    // Not an error per se, but a critical warning
    errors.push(`[WARNING] LOS余力がマイナス: ${kpis.losHeadroom}日 — 制度上限超過リスク`);
  }

  return errors;
}
