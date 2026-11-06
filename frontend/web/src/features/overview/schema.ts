/**
 * 管理侧「运营总览」数据类型 — 6 个 KPI / 趋势曲线 / 实时告警 / 服务健康 / Top 智能体。
 */
import type { ComponentType } from 'react';
import type { LucideIcon } from 'lucide-react';

export type Tone = 'brand' | 'info' | 'success' | 'warn' | 'danger' | 'purple';
export type DeltaTone = 'up' | 'down' | 'flat';
export type Severity = 'high' | 'medium' | 'low' | 'info';
export type ServiceStatus = 'ok' | 'degraded' | 'down';
export type Range = '1h' | '6h' | '24h' | '7d';

export interface KpiTile {
  label: string;
  value: string;
  delta: string;
  deltaTone: DeltaTone;
  tone: Tone;
  href: string;
  sparkline: number[];
  /** icon 由调用方按 tone/name 解析,数据层只携带 id */
  iconName: string;
}

export interface TrendPoint {
  label: string;
  calls: number;
  success: number;
  errors: number;
}

export interface TrendSeries {
  range: Range;
  points: TrendPoint[];
}

export interface OverviewAlert {
  id: string;
  severity: Severity;
  title: string;
  time: string;
  affected: string;
  suggestion: string;
}

export interface OverviewService {
  name: string;
  status: ServiceStatus;
  latency: string;
  detail: string;
}

export interface TopAgent {
  name: string;
  calls: string;
  share: number;
  tone: 'brand' | 'success' | 'info' | 'purple' | 'warn';
}

export interface OverviewSummary {
  kpis: KpiTile[];
  alerts: OverviewAlert[];
  /** ⚠️ **服务健康 / Top 智能体不在这里** ✓ —— 那是真实数据 ✓，各读各的端点 ✓。 */
}

export type { ComponentType, LucideIcon };