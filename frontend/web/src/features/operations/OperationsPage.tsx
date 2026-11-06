import { useServerAction } from '@/services/useServerAction';
/**
 * AdminOperations 编排 — 对齐技能管理 / ModelsPage：无子模块 Tab，Hero 轻量，列表工具栏 + 视图筛选。
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FileText, Filter, RefreshCw, Search, ShieldCheck } from 'lucide-react';
import { AdminListPagination, paginateItems } from '@/components/feedback/AdminListPagination';
import { AdminListHeader, AdminListHeaderMetrics } from '@/components/feedback/AdminListRow';
import { AdminHero } from '@/components/feedback/AdminHero';
import { AdminPage } from '@/components/feedback/AdminPage';
import { NoticeBanner } from '@/components/feedback/NoticeBanner';
import {
  useIncidents,
  useKindStats,
  useSessions,
  useSpans,
} from './useOperations';
import type { ExchangeFormat, Incident, Session } from './schema';
import { SessionCard } from './components/SessionCard';
import { FilterModal, type FilterSelection } from './components/FilterModal';
import { ExportTraceModal } from './components/ExportModal';
import { AdminBatchBar } from '@/components/feedback/AdminBatchBar';
import { TraceTab } from './components/tabs/TraceTab';
import { KindTab } from './components/tabs/KindTab';
import { IncidentTab } from './components/tabs/IncidentTab';
import { downloadBlob } from '@/lib/download';
import { AdminEmptyState } from '@/components/feedback/AdminEmptyState';

type ViewId = 'session' | 'trace' | 'kind' | 'incident';


export default function OperationsPage() {
  const navigate = useNavigate();
  const sessionsQuery = useSessions();
  const spansQuery = useSpans();
  const incidentsQuery = useIncidents();
  const kindStatsQuery = useKindStats();

  const baseSessions = sessionsQuery.data ?? [];
  const baseSpans = spansQuery.data ?? [];
  const baseIncidents = incidentsQuery.data ?? [];
  const baseKindStats = kindStatsQuery.data ?? [];

  const sessions = baseSessions;
  const incidents = baseIncidents;
  const [view, setView] = useState<ViewId>('session');
  const [search, setSearch] = useState('');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [filterOpen, setFilterOpen] = useState(false);
  const [filters, setFilters] = useState<FilterSelection>({ status: 'all', agent: 'all', severity: 'all' });
  const [exportOpen, setExportOpen] = useState(false);
  const [notice, setNotice] = useState('');
  const server = useServerAction(setNotice);
  const [page, setPage] = useState(1);

  const stats = useMemo(() => {
    const total = sessions.length;
    const failed = sessions.filter((s) => s.status === 'failed').length;
    const partial = sessions.filter((s) => s.status === 'partial').length;
    const errorRate = Math.round(((failed + partial) / Math.max(total, 1)) * 1000) / 10;
    return { total, errorRate };
  }, [sessions]);

  const visibleSessions = useMemo(() => {
    const q = search.trim().toLowerCase();
    return sessions.filter((s) =>
      (q.length === 0 || `${s.id} ${s.user} ${s.agentName} ${s.summary}`.toLowerCase().includes(q)) &&
      (filters.status === 'all' || s.status === filters.status) &&
      (filters.agent === 'all' || s.agentName === filters.agent) &&
      (filters.severity === 'all' || incidents.some((item) => item.sessionId === s.id && item.severity === filters.severity)),
    );
  }, [sessions, search, filters, incidents]);

  useEffect(() => { setPage(1); }, [search, view, filters]);
  const paged = useMemo(() => paginateItems(visibleSessions, page), [visibleSessions, page]);

  const toggleSelect = (id: string) =>
    setSelectedIds((current) => (current.includes(id) ? current.filter((x) => x !== id) : [...current, id]));

  const toggleStar = (id: string) => server.mutate({ path: `/api/admin/operations/sessions/${id}`, method: 'PATCH', body: { starred: !sessions.find((s) => s.id === id)?.starred } });
  const handleBatchExport = () => setExportOpen(true);
  const handleBatchResolve = () => server.mutate({ path: '/api/admin/operations/incidents/batch-resolve', body: { sessionIds: selectedIds }, success: '已批量解决', onSuccess: () => setSelectedIds([]) });

  const handleExport = (format: ExchangeFormat) => {
    const list = selectedIds.length > 0 ? sessions.filter((s) => selectedIds.includes(s.id)) : sessions;
    const payload = list.map((s) => ({ id: s.id, user: s.user, agent: s.agentName, status: s.status, durationMs: s.totalDurationMs }));
    if (format === 'json') {
      downloadBlob(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }), 'traces.json');
    } else {
      const yaml = payload.map((s) => `- id: "${s.id}"\n  user: "${s.user}"\n  agent: "${s.agent}"\n  status: "${s.status}"`).join('\n');
      downloadBlob(new Blob([`${yaml}\n`], { type: 'text/yaml' }), 'traces.yaml');
    }
    setNotice(`已导出 ${list.length} 条会话为 ${format.toUpperCase()} 文件。`);
  };

  const handleExportOne = (session: Session) => {
    downloadBlob(new Blob([JSON.stringify(session, null, 2)], { type: 'application/json' }), `session-${session.id}.json`);
    setNotice(`已导出会话「${session.id}」。`);
  };

  const handleResolveSession = (session: Session) => server.mutate({ path: '/api/admin/operations/incidents/batch-resolve', body: { sessionIds: [session.id] }, success: '已解决会话相关异常' });
  const handleResolve = (id: string) => server.mutate({ path: `/api/admin/operations/incidents/${id}`, method: 'PATCH', body: { resolved: !incidents.find((i) => i.id === id)?.resolved } });

  const handleFilter = (f: FilterSelection) => setFilters(f);

  const goSessionDetail = (s: Session) => navigate(`/admin/operations/${s.id}`);

  const handleRefresh = async () => {
    const results = await Promise.all([sessionsQuery.refetch(), spansQuery.refetch(), incidentsQuery.refetch(), kindStatsQuery.refetch()]);
    setNotice(results.some((result) => result.isError) ? '刷新失败，请查看请求错误。' : '数据已从后端刷新');
  };

  const viewSelect = (
    <select
      aria-label="视图"
      value={view}
      onChange={(e) => setView(e.target.value as ViewId)}
      className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 text-xs outline-none focus:border-[var(--brand)]"
    >
      <option value="session">会话列表</option>
      <option value="trace">轨迹详情</option>
      <option value="kind">类型分布</option>
      <option value="incident">异常事件</option>
    </select>
  );

  return (
    <AdminPage pageClass="operations-page" density="lg">
      <AdminHero
        eyebrow="ADMIN / 调用链路"
        title="还原会话的完整调用过程。"
        description={<>今日会话 {stats.total} · 异常率 {stats.errorRate}%。</>}
        tone="sky"
        headingLevel="h2"
      />

      {notice && (
        <NoticeBanner tone="violet" onClose={() => setNotice('')}>
          {notice}
        </NoticeBanner>
      )}

      {selectedIds.length > 0 && view === 'session' && (
        <AdminBatchBar
          count={selectedIds.length}
          onClear={() => setSelectedIds([])}
          actions={[
            { id: 'resolve', label: '批量标记已解决', icon: ShieldCheck, tone: 'brand', onClick: handleBatchResolve },
            { id: 'export', label: '批量导出', icon: FileText, tone: 'neutral', onClick: handleBatchExport },
          ]}
        />
      )}

      {view === 'session' && (
        <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
          <div className="flex flex-col gap-2 border-b border-[var(--border)] px-4 py-3 sm:flex-row sm:items-center sm:px-5">
            <label className="relative min-w-0 flex-1">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--text-muted)]" />
              <input
                aria-label="搜索会话"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="搜索会话 ID / 用户 / 智能体"
                className="h-9 w-full rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] pl-8 pr-3 text-sm outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--brand)]"
              />
            </label>
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              {viewSelect}
              <button
                type="button"
                onClick={() => setFilterOpen(true)}
                className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-3 text-xs font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]"
              >
                <Filter className="h-3.5 w-3.5" />
                筛选
              </button>
              <button
                type="button"
                onClick={() => setExportOpen(true)}
                className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-3 text-xs font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]"
              >
                <FileText className="h-3.5 w-3.5" />
                导出
              </button>
              <button
                type="button"
                onClick={handleRefresh}
                className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]"
              >
                <RefreshCw className="h-4 w-4" />
                实时刷新
              </button>
            </div>
          </div>
          <AdminListHeader metrics={<AdminListHeaderMetrics labels={['Span', '耗时', '成本', '开始']} />} />
          <div className="divide-y divide-[var(--border)]">
            {paged.slice.map((session) => (
              <SessionCard
                key={session.id}
                session={session}
                selected={selectedIds.includes(session.id)}
                onToggleSelect={toggleSelect}
                onSelect={goSessionDetail}
                onToggleStar={toggleStar}
                onExportOne={handleExportOne}
                onResolve={handleResolveSession}
              />
            ))}
          </div>
          <AdminListPagination
            page={paged.safePage}
            totalPages={paged.totalPages}
            total={paged.total}
            pageStart={paged.pageStart}
            pageEnd={paged.pageEnd}
            onPageChange={setPage}
          />
          {visibleSessions.length === 0 && <AdminEmptyState title="没有匹配的会话" />}
        </div>
      )}

      {view !== 'session' && (
        <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
          <div className="flex flex-wrap items-center gap-2 border-b border-[var(--border)] px-4 py-3 sm:px-5">
            {viewSelect}
          </div>
          <div className="p-5">
            {view === 'trace' && <TraceTab spans={baseSpans} />}
            {view === 'kind' && (
              <KindTab
                kindStats={baseKindStats}
                total={baseKindStats.reduce((s, k) => s + k.count, 0)}
              />
            )}
            {view === 'incident' && <IncidentTab incidents={incidents} onToggleResolve={handleResolve} />}
          </div>
        </div>
      )}

      <FilterModal open={filterOpen} agents={[...new Set(sessions.map((session) => session.agentName))]} onClose={() => setFilterOpen(false)} onApply={handleFilter} />
      <ExportTraceModal
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        onExport={handleExport}
        total={sessions.length}
        selectedCount={selectedIds.length}
      />
    </AdminPage>
  );
}
