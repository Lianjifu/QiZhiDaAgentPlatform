/**
 * 左侧栏 / 顶栏 env 徽标。
 * 只展示业务环境：演示和开发。
 */
import { Beaker, FlaskConical } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { resolveRuntimeConfig } from '@/lib/environment';

type ResolvedEnv = 'development' | 'demo';

export function resolveQzdapEnv(): ResolvedEnv {
  return resolveRuntimeConfig().environment;
}

const META: Record<ResolvedEnv, { label: string; tone: string; Icon: LucideIcon; tooltip: string }> = {
  development: { label: '开发环境', tone: 'bg-amber-50 text-amber-700 ring-1 ring-amber-200 dark:bg-amber-500/15 dark:text-amber-300 dark:ring-amber-500/30', Icon: FlaskConical, tooltip: '当前为开发环境 — DEBUG=true,会落到本地 PG' },
  demo: { label: '演示环境', tone: 'bg-sky-50 text-sky-700 ring-1 ring-sky-200 dark:bg-sky-500/15 dark:text-sky-300 dark:ring-sky-500/30', Icon: Beaker, tooltip: '当前为演示环境 — 数据由前端 mock 接管,不会持久化' },
};

interface EnvBadgeProps {
  size?: 'sm' | 'md';
  className?: string;
}

export function EnvBadge({ size = 'sm', className = '' }: EnvBadgeProps) {
  const env = resolveQzdapEnv();
  const meta = META[env];
  const Icon = meta.Icon;
  const pad = size === 'md' ? 'px-2.5 py-1 text-xs' : 'px-2 py-0.5 text-[10px]';
  return (
    <span
      title={meta.tooltip}
      aria-label={meta.tooltip}
      className={`inline-flex shrink-0 items-center gap-1 rounded-full font-semibold uppercase tracking-wide tabular-nums ${pad} ${meta.tone} ${className}`}
    >
      <Icon className={size === 'md' ? 'h-3.5 w-3.5' : 'h-3 w-3'} aria-hidden="true" />
      <span>{meta.label}</span>
    </span>
  );
}
