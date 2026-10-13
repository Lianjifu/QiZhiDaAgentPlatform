/**
 * 左侧栏 / 顶栏 env 徽标。
 * 颜色编码:
 *   - production : 红色,告诉用户"这是真实环境"
 *   - demo       : 蓝色,告诉用户"展示数据,不会持久化"
 *   - development: 琥珀色,告诉用户"开发态,会改本地 PG"
 *   - test / ci  : 灰色
 */
import { Beaker, FlaskConical, Server, TestTube } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

type ResolvedEnv = 'production' | 'development' | 'demo' | 'test' | 'ci' | 'staging' | 'unknown';

export function resolveQzdapEnv(): ResolvedEnv {
  const raw = (import.meta.env.VITE_QZDAP_ENV ?? '').toString().trim().toLowerCase();
  if (import.meta.env.VITE_USE_DEMO === 'true' || raw === 'demo') return 'demo';
  if (raw === 'production' || raw === 'prod') return 'production';
  if (raw === 'development' || raw === 'dev') return 'development';
  if (raw === 'test') return 'test';
  if (raw === 'ci') return 'ci';
  if (raw === 'staging') return 'staging';
  return 'unknown';
}

const META: Record<ResolvedEnv, { label: string; tone: string; Icon: LucideIcon; tooltip: string }> = {
  production: { label: '生产环境', tone: 'bg-rose-50 text-rose-700 ring-1 ring-rose-200 dark:bg-rose-500/15 dark:text-rose-300 dark:ring-rose-500/30', Icon: Server, tooltip: '当前为生产环境 — 修改将落到真实数据库' },
  development: { label: '开发环境', tone: 'bg-amber-50 text-amber-700 ring-1 ring-amber-200 dark:bg-amber-500/15 dark:text-amber-300 dark:ring-amber-500/30', Icon: FlaskConical, tooltip: '当前为开发环境 — DEBUG=true,会落到本地 PG' },
  demo: { label: '演示环境', tone: 'bg-sky-50 text-sky-700 ring-1 ring-sky-200 dark:bg-sky-500/15 dark:text-sky-300 dark:ring-sky-500/30', Icon: Beaker, tooltip: '当前为演示环境 — 数据由前端 mock 接管,不会持久化' },
  test: { label: '测试环境', tone: 'bg-slate-100 text-slate-700 ring-1 ring-slate-200 dark:bg-slate-500/15 dark:text-slate-300 dark:ring-slate-500/30', Icon: TestTube, tooltip: '当前为测试环境' },
  ci: { label: 'CI', tone: 'bg-slate-100 text-slate-700 ring-1 ring-slate-200 dark:bg-slate-500/15 dark:text-slate-300 dark:ring-slate-500/30', Icon: TestTube, tooltip: '当前为 CI 流水线' },
  staging: { label: '预发环境', tone: 'bg-violet-50 text-violet-700 ring-1 ring-violet-200 dark:bg-violet-500/15 dark:text-violet-300 dark:ring-violet-500/30', Icon: Server, tooltip: '当前为预发环境' },
  unknown: { label: '环境未识别', tone: 'bg-slate-100 text-slate-600 ring-1 ring-slate-200 dark:bg-slate-500/15 dark:text-slate-400 dark:ring-slate-500/30', Icon: Beaker, tooltip: '未设置 VITE_QZDAP_ENV' },
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
