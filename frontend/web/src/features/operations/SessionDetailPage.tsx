/**
 * Admin 调用链路详情 — 独立页面 /admin/operations/:id
 */
import { useEffect, useMemo, useState } from 'react';
import { Activity, ArrowLeft, FileText } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import type { DrawerPanel } from './schema';
import { useSessions, useSpans } from './useOperations';
import { SESSION_BADGE } from './components/constants';
import {
  DrawerPanelContext,
  DrawerPanelLogs,
  DrawerPanelOverview,
  DrawerPanelSpans,
  DrawerSidebar,
} from './components/DrawerPanels';
import { AdminPage } from '@/components/feedback/AdminPage';

function NotFound() {
  return (
    <AdminPage density="lg">
      <Link to="/admin/operations" className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--brand)]">
        <ArrowLeft className="h-3.5 w-3.5" />返回调用链路
      </Link>
      <div className="rounded-2xl border border-dashed border-[var(--border)] bg-[var(--surface-1)] p-8 text-center">
        <p className="text-sm font-semibold">会话不存在或已被删除</p>
        <p className="mt-1 text-xs text-[var(--text-muted)]">请返回列表重新选择。</p>
      </div>
    </AdminPage>
  );
}

export default function SessionDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const sessionsQuery = useSessions();
  const spansQuery = useSpans();
  const sessions = sessionsQuery.data ?? [];
  const spans = spansQuery.data ?? [];
  const session = useMemo(() => sessions.find((s) => s.id === id), [sessions, id]);
  const [panel, setPanel] = useState<DrawerPanel>('overview');

  useEffect(() => {
    setPanel('overview');
  }, [id]);

  if (!session) return <NotFound />;

  const badge = SESSION_BADGE[session.status];

  return (
    <AdminPage density="lg">
      <Link to="/admin/operations" className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--brand)]">
        <ArrowLeft className="h-3.5 w-3.5" />返回调用链路
      </Link>

      <header className="flex flex-wrap items-start gap-4">
        <span className="grid h-12 w-12 place-items-center rounded-2xl bg-[var(--brand-light)] text-[var(--brand)]">
          <Activity className="h-5 w-5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--brand)]">调用链路</p>
          <h1 className="mt-1 font-mono text-3xl font-semibold tracking-tight">{session.id}</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--text-muted)]">{session.summary}</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-[11px] font-semibold ${badge.className}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${badge.dot}`} aria-hidden="true" />
              {badge.label}
            </span>
            <span className="rounded-full bg-[var(--bg-elevated)] px-2 py-1 text-[11px] font-medium">{session.agentName}</span>
            <span className="rounded-full bg-[var(--bg-elevated)] px-2 py-1 text-[11px] font-medium">{session.user}</span>
          </div>
        </div>
      </header>

      <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-6">
        <div className="flex flex-col gap-5 sm:flex-row">
          <DrawerSidebar panel={panel} setPanel={setPanel} />
          <div className="flex-1 space-y-5">
            {panel === 'overview' && <DrawerPanelOverview session={session} />}
            {panel === 'spans' && <DrawerPanelSpans session={session} spans={spans} />}
            {panel === 'context' && <DrawerPanelContext session={session} />}
            {panel === 'logs' && <DrawerPanelLogs session={session} />}
          </div>
        </div>
        <div className="mt-6 flex flex-wrap items-center justify-end gap-2 border-t border-[var(--border)] pt-5">
          <Link to="/admin/operations" className="rounded-lg border border-[var(--border)] px-4 py-2 text-xs font-semibold">
            关闭
          </Link>
          <button
            type="button"
            onClick={() => alert('已生成调用链路报告')}
            className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]"
          >
            <FileText className="h-3.5 w-3.5" />
            生成报告
          </button>
        </div>
      </section>
    </AdminPage>
  );
}
