import type {
  BudgetPeriod, BudgetStatus, AlertSeverity, UsageCategory, ExchangeFormat,
} from '../schema';
import { BarChart3, Building2, LineChart, Settings2, ShieldCheck, Sparkles } from 'lucide-react';

export const PERIOD_LABEL: Record<BudgetPeriod, string> = {
  monthly: '月度',
  quarterly: '季度',
  yearly: '年度',
};

export const BUDGET_BADGE: Record<BudgetStatus, { label: string; className: string; dot: string }> = {
  healthy: { label: '正常', className: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300', dot: 'bg-emerald-500' },
  warning: { label: '预警', className: 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300', dot: 'bg-amber-500' },
  exceeded: { label: '超支', className: 'bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300', dot: 'bg-rose-500' },
  frozen: { label: '已冻结', className: 'bg-[var(--bg-elevated)] text-[var(--text-muted)]', dot: 'bg-[var(--text-muted)]' },
};

export const SEVERITY_BADGE: Record<AlertSeverity, { label: string; className: string; dot: string }> = {
  info: { label: '信息', className: 'bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300', dot: 'bg-sky-500' },
  warning: { label: '警告', className: 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300', dot: 'bg-amber-500' },
  critical: { label: '严重', className: 'bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300', dot: 'bg-rose-500' },
};

export const CATEGORY_META: Record<UsageCategory, { label: string; tone: string; icon: typeof Sparkles }> = {
  token: { label: 'Token', tone: 'bg-violet-50 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300', icon: Sparkles },
  tool: { label: '工具调用', tone: 'bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300', icon: Settings2 },
  storage: { label: '存储', tone: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300', icon: Building2 },
  embedding: { label: 'Embedding', tone: 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300', icon: LineChart },
};

export const DRAWER_NAV_ITEMS: Array<{ id: 'detail' | 'trend' | 'allocation' | 'history'; label: string; icon: typeof Settings2 }> = [
  { id: 'detail', label: '基本信息', icon: Settings2 },
  { id: 'trend', label: '使用趋势', icon: LineChart },
  { id: 'allocation', label: '额度分配', icon: BarChart3 },
  { id: 'history', label: '变更记录', icon: ShieldCheck },
];


export const SCOPE_LABEL: Record<'enterprise' | 'department' | 'channel', string> = {
  enterprise: '企业',
  department: '部门',
  channel: '渠道',
};

export const EXCHANGE_FORMATS: ExchangeFormat[] = ['json', 'yaml', 'csv'];