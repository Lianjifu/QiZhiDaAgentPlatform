import { useApiQuery } from '@/services/query';
/**
 * 4 个 SideDrawer 子面板(概要 / 调用链 / 上下文 / 日志)+ 工作区侧栏。
 */
import { useMemo, useState } from 'react';
import { Activity } from 'lucide-react';
import type { Session, Span, SpanKind } from '../schema';
import { DRAWER_NAV_ITEMS, SEVERITY_BADGE, SPAN_FILTER, SESSION_BADGE } from './constants';
import { SpanRow, buildSpanTree } from './SpanRow';

const STATUS_FILTER_OPTIONS: Array<{ id: 'all' | Span['status']; label: string }> = [
  { id: 'all', label: '全部状态' },
  { id: 'ok', label: '成功' },
  { id: 'error', label: '失败' },
  { id: 'pending', label: '进行中' },
];

export function DrawerPanelOverview({ session }: { session: Session }) {
  const badge = SESSION_BADGE[session.status];
  return (
    <div className="space-y-5">
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] p-5">
        <div className="flex items-center gap-2">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-[var(--brand-light)] text-[var(--brand)]">
            <Activity className="h-4 w-4" />
          </span>
          <div>
            <p className="text-sm font-semibold">{session.agentName}</p>
            <p className="text-[11px] text-[var(--text-muted)]">
              用户 {session.user} · 渠道 {session.channel}
            </p>
          </div>
          <span className={`ml-auto inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-semibold ${badge.className}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${badge.dot}`} aria-hidden="true" />
            {badge.label}
          </span>
        </div>
        <p className="mt-3 text-[11px] leading-5 text-[var(--text-muted)]">{session.summary}</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-4">
        <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] p-3">
          <p className="text-[10px] text-[var(--text-muted)]">Span 数</p>
          <p className="mt-1 text-sm font-semibold tabular-nums">{session.spanCount}</p>
        </div>
        <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] p-3">
          <p className="text-[10px] text-[var(--text-muted)]">总耗时</p>
          <p className="mt-1 text-sm font-semibold tabular-nums">{(session.totalDurationMs / 1000).toFixed(1)}s</p>
        </div>
        <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] p-3">
          <p className="text-[10px] text-[var(--text-muted)]">Token</p>
          <p className="mt-1 text-sm font-semibold tabular-nums">{session.totalTokens.toLocaleString('zh-CN')}</p>
        </div>
        <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] p-3">
          <p className="text-[10px] text-[var(--text-muted)]">成本</p>
          <p className="mt-1 text-sm font-semibold tabular-nums">¥ {session.totalCost.toFixed(2)}</p>
        </div>
      </div>
    </div>
  );
}

export function DrawerPanelSpans({ session, spans }: { session: Session; spans: Span[] }) {
  const [kindFilter, setKindFilter] = useState<'all' | SpanKind>('all');
  const [statusFilter, setStatusFilter] = useState<'all' | Span['status']>('all');
  const [selectedSpan, setSelectedSpan] = useState<string | null>(null);
  const filtered = useMemo(
    () =>
      spans.filter(
        (s) => (kindFilter === 'all' || s.kind === kindFilter) && (statusFilter === 'all' || s.status === statusFilter),
      ),
    [spans, kindFilter, statusFilter],
  );
  const tree = buildSpanTree(filtered);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <label className="sr-only" htmlFor="span-kind">
          按类型筛选
        </label>
        <select
          id="span-kind"
          value={kindFilter}
          onChange={(e) => setKindFilter(e.target.value as 'all' | SpanKind)}
          className="h-9 rounded-xl border border-[var(--border)] bg-[var(--surface-1)] px-3 text-xs font-medium outline-none"
        >
          {SPAN_FILTER.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
            </option>
          ))}
        </select>
        <label className="sr-only" htmlFor="span-status">
          按状态筛选
        </label>
        <select
          id="span-status"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as 'all' | Span['status'])}
          className="h-9 rounded-xl border border-[var(--border)] bg-[var(--surface-1)] px-3 text-xs font-medium outline-none"
        >
          {STATUS_FILTER_OPTIONS.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
      <div className="space-y-1.5">
        {tree.map(({ span, depth }) => (
          <SpanRow
            key={span.id}
            span={span}
            depth={depth}
            totalDurationMs={session.totalDurationMs}
            selected={selectedSpan === span.id}
            onSelect={() => setSelectedSpan(span.id)}
          />
        ))}
        {tree.length === 0 && (
          <p className="rounded-xl border border-dashed border-[var(--border-strong)] p-8 text-center text-xs text-[var(--text-muted)]">
            没有匹配的 span。
          </p>
        )}
      </div>
    </div>
  );
}

export function DrawerPanelContext({ session }: { session: Session }) {
  const { data: ctx = [] } = useApiQuery<{ label: string; value: string }[]>(['detail', `/api/admin/operations/sessions/${session.id}/context`], `/api/admin/operations/sessions/${session.id}/context`);
  return (
    <ul className="space-y-2">
      {ctx.map((c) => (
        <li key={c.label} className="rounded-xl border border-[var(--border)] bg-[var(--surface-1)] p-3">
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">{c.label}</p>
          <pre className="mt-1 whitespace-pre-wrap rounded-lg bg-[var(--bg-elevated)] p-2 font-mono text-[11px] leading-6 text-[var(--text-secondary)]">
            {c.value}
          </pre>
        </li>
      ))}
    </ul>
  );
}

export function DrawerPanelLogs({ session }: { session: Session }) {
  const { data: logs = [] } = useApiQuery<{ time: string; level: string; text: string }[]>(['detail', `/api/admin/operations/sessions/${session.id}/logs`], `/api/admin/operations/sessions/${session.id}/logs`);
  return (
    <ol className="space-y-1.5">
      {logs.map((l, idx) => (
        <li key={idx} className="flex items-start gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] p-2 font-mono text-[11px]">
          <span className="text-[var(--text-muted)]">{l.time}</span>
          <span
            className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${l.level === 'info' ? 'bg-sky-50 text-sky-700' : 'bg-amber-50 text-amber-700'}`}
          >
            {l.level.toUpperCase()}
          </span>
          <span className="flex-1">{l.text}</span>
        </li>
      ))}
    </ol>
  );
}

export function DrawerSidebar({
  panel,
  setPanel,
}: {
  panel: 'overview' | 'spans' | 'context' | 'logs';
  setPanel: (p: 'overview' | 'spans' | 'context' | 'logs') => void;
}) {
  return (
    <nav
      aria-label="会话工作区"
      className="hidden w-[200px] shrink-0 flex-col gap-1 border-r border-[var(--border)] bg-[var(--bg-elevated)] p-4 sm:flex"
    >
      <p className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">工作区</p>
      {DRAWER_NAV_ITEMS.map((item) => {
        const Icon = item.icon;
        const active = panel === item.id;
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => setPanel(item.id)}
            aria-pressed={active}
            className={`flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left text-xs font-semibold transition ${active ? 'bg-[var(--brand-light)] text-[var(--brand)]' : 'text-[var(--text-secondary)] hover:bg-[var(--surface-1)]'}`}
          >
            <Icon className="h-4 w-4" />
            {item.label}
          </button>
        );
      })}
    </nav>
  );
}

// Re-export for legacy import
export { SEVERITY_BADGE };
