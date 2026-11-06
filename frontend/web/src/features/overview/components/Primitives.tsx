/**
 * AdminOverview 共享视觉元素 — tone 配色 / 严重度徽章 / Sparkline / 状态点。
 */
import { Activity, AlertTriangle, ArrowDownRight, ArrowUpRight, BellRing, Brain, ShieldCheck, Timer } from 'lucide-react';
import type { KpiTile, ServiceStatus, Severity, Tone } from '../schema';

export const TONE_CLASS: Record<Tone, string> = {
  brand: 'bg-[var(--brand-light)] text-[var(--brand)]',
  info: 'bg-[var(--info-bg)] text-[var(--info)]',
  success: 'bg-[var(--success-bg)] text-[var(--success)]',
  warn: 'bg-[var(--warning-bg)] text-[var(--warning)]',
  danger: 'bg-[var(--danger-bg)] text-[var(--danger)]',
  purple: 'bg-[var(--purple-bg)] text-[var(--purple)]',
};

export const SEVERITY_BADGE: Record<Severity, { label: string; className: string }> = {
  high: { label: '高', className: 'bg-[var(--danger-bg)] text-[var(--danger)]' },
  medium: { label: '中', className: 'bg-[var(--warning-bg)] text-[var(--warning)]' },
  low: { label: '低', className: 'bg-[var(--info-bg)] text-[var(--info)]' },
  info: { label: '提示', className: 'bg-[var(--bg-elevated)] text-[var(--text-secondary)]' },
};

export const KPI_ICONS: Record<string, typeof Activity> = {
  Activity,
  ShieldCheck,
  Timer,
  AlertTriangle,
  Brain,
  BellRing,
};



export function StatusDot({ status }: { status: ServiceStatus }) {
  const cls = status === 'ok' ? 'bg-[var(--success)]' : status === 'degraded' ? 'bg-[var(--warning)]' : 'bg-[var(--danger)]';
  return <span className={`grid h-2.5 w-2.5 place-items-center rounded-full ${cls}`} aria-hidden="true" />;
}

export function kpiStroke(tone: Tone) {
  return tone === 'success' ? 'var(--success)'
    : tone === 'danger' ? 'var(--danger)'
    : tone === 'warn' ? 'var(--warning)'
    : tone === 'info' ? 'var(--chart-info)'
    : tone === 'purple' ? 'var(--chart-purple)'
    : 'var(--brand)';
}

export function deltaClass(tone: KpiTile['deltaTone']) {
  return tone === 'up' ? 'text-[var(--success)]'
    : tone === 'down' ? 'text-[var(--danger)]'
    : 'text-[var(--text-muted)]';
}

export const DeltaIcon = ArrowUpRight;
export const DeltaDownIcon = ArrowDownRight;