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
import { DetailHeader } from '@/components/feedback/DetailLayout';

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

      <DetailHeader
  eyebrow="调用链路"
  title={session.id}
  titleClassName="font-mono"
  subtitle={session.summary}
  badges={[
    { label: badge.label, className: badge.className, dot: badge.dot },
    { label: session.agentName, className: "bg-[var(--bg-elevated)]" },
    { label: session.user, className: "bg-[var(--bg-elevated)]" },
  ]}
  icon={Activity}
  iconClass="bg-[var(--brand-light)] text-[var(--brand)]"
/>

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
