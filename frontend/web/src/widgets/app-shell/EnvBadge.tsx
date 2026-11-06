/**
 * 左侧栏 / 顶栏 env 徽标 —— **只剩开发环境** ✓（演示环境已退役 ✓）。
 */
import { FlaskConical } from 'lucide-react';

const META = {
  label: '开发环境',
  tone: 'bg-amber-50 text-amber-700 ring-1 ring-amber-200 dark:bg-amber-500/15 dark:text-amber-300 dark:ring-amber-500/30',
  tooltip: '当前为开发环境 — DEBUG=true,会落到本地 PG',
} as const;

interface EnvBadgeProps {
  size?: 'sm' | 'md';
  className?: string;
}

export function EnvBadge({ size = 'sm', className = '' }: EnvBadgeProps) {
  const Icon = FlaskConical;
  const pad = size === 'md' ? 'px-2.5 py-1 text-xs' : 'px-2 py-0.5 text-[10px]';
  return (
    <span
      title={META.tooltip}
      aria-label={META.tooltip}
      className={`inline-flex shrink-0 items-center gap-1 rounded-full font-semibold uppercase tracking-wide tabular-nums ${pad} ${META.tone} ${className}`}
    >
      <Icon className={size === 'md' ? 'h-3.5 w-3.5' : 'h-3 w-3'} aria-hidden="true" />
      <span>{META.label}</span>
    </span>
  );
}
