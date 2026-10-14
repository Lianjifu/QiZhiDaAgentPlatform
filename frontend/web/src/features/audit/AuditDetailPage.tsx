import { useServerAction } from '@/services/useServerAction';
/**
 * Admin 工具审计详情 — 独立页面 /admin/tool-audit/:id
 */
import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, ShieldAlert, ShieldOff } from 'lucide-react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { NoticeBanner } from '@/components/feedback/NoticeBanner';
import type { AuditDrawerPanel } from './schema';
import { useAuditEntries, useAuditRules } from './useAudit';
import { DRAWER_NAV, SEVERITY_BADGE } from './components/constants';
import { DrawerPanelArgs, DrawerPanelLog, DrawerPanelOverview, DrawerPanelRule } from './components/DrawerPanels';

function NotFound() {
  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-6 p-5 pb-16 sm:p-8 xl:px-10">
      <Link to="/admin/tool-audit" className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--brand)]">
        <ArrowLeft className="h-3.5 w-3.5" />返回工具审计
      </Link>
      <div className="rounded-2xl border border-dashed border-[var(--border)] bg-[var(--surface-1)] p-8 text-center">
        <p className="text-sm font-semibold">审计条目不存在或已被删除</p>
        <p className="mt-1 text-xs text-[var(--text-muted)]">请返回列表重新选择。</p>
      </div>
    </div>
  );
}

function DrawerSidebar({ panel, setPanel }: { panel: AuditDrawerPanel; setPanel: (p: AuditDrawerPanel) => void }) {
  return (
    <nav aria-label="审计工作区" className="hidden w-[200px] shrink-0 flex-col gap-1 rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] p-4 sm:flex">
      <p className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">工作区</p>
      {DRAWER_NAV.map((item) => {
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

export default function AuditDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const entriesQuery = useAuditEntries();
  const rulesQuery = useAuditRules();
  const entries = entriesQuery.data ?? [];
  const rules = rulesQuery.data ?? [];
  const entry = useMemo(() => entries.find((e) => e.id === id), [entries, id]);
  const [panel, setPanel] = useState<AuditDrawerPanel>('overview');
  const [notice, setNotice] = useState('');
  const server = useServerAction(setNotice);

  useEffect(() => {
    setPanel('overview');
  }, [id]);

  if (!entry) return <NotFound />;

  const sev = SEVERITY_BADGE[entry.severity];

  const handleResolve = () => {
    server.mutate({ path: `/api/admin/audit/entries/${id}/resolve`, success: '已下发处置任务', onSuccess: () => navigate('/admin/tool-audit') });
  };

  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-6 p-5 pb-16 sm:p-8 xl:px-10">
      <Link to="/admin/tool-audit" className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--brand)]">
        <ArrowLeft className="h-3.5 w-3.5" />返回工具审计
      </Link>

      {notice && (
        <NoticeBanner tone="violet" onClose={() => setNotice('')}>
          {notice}
        </NoticeBanner>
      )}

      <header className="flex flex-wrap items-start gap-4">
        <span className="grid h-12 w-12 place-items-center rounded-2xl bg-rose-100 text-rose-700 dark:bg-rose-500/20 dark:text-rose-300">
          <ShieldAlert className="h-5 w-5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-rose-700 dark:text-rose-300">工具审计</p>
          <h1 className="mt-1 font-mono text-3xl font-semibold tracking-tight">{entry.id}</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--text-muted)]">
            记录工具调用 · 权限校验 · 风险命中全过程,用于事后追责与策略优化。
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-[11px] font-semibold ${sev.className}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${sev.dot}`} aria-hidden="true" />
              {sev.label}
            </span>
            <span className="rounded-full bg-[var(--bg-elevated)] px-2 py-1 font-mono text-[11px] font-medium">{entry.toolName}</span>
          </div>
        </div>
      </header>

      <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-6">
        <div className="flex flex-col gap-5 sm:flex-row">
          <DrawerSidebar panel={panel} setPanel={setPanel} />
          <div className="flex-1 space-y-5">
            {panel === 'overview' && <DrawerPanelOverview entry={entry} />}
            {panel === 'args' && <DrawerPanelArgs entry={entry} />}
            {panel === 'rule' && <DrawerPanelRule entry={entry} rules={rules} />}
            {panel === 'log' && <DrawerPanelLog entry={entry} />}
          </div>
        </div>
        <div className="mt-6 flex flex-wrap items-center justify-end gap-2 border-t border-[var(--border)] pt-5">
          <Link to="/admin/tool-audit" className="rounded-lg border border-[var(--border)] px-4 py-2 text-xs font-semibold">
            关闭
          </Link>
          <button
            type="button"
            onClick={handleResolve}
            className="inline-flex items-center gap-1.5 rounded-lg bg-rose-600 px-4 py-2 text-xs font-semibold text-white hover:bg-rose-700"
          >
            <ShieldOff className="h-3.5 w-3.5" />
            立即处置
          </button>
        </div>
      </section>
    </div>
  );
}
