import { useServerAction } from '@/services/useServerAction';
/**
 * AdminToolAudit 编排 — 对齐技能/模型：无子模块 Tab，列表工具栏 + 视图筛选。
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Download, Plus, Search, ShieldQuestion } from 'lucide-react';
import { AdminListPagination, paginateItems } from '@/components/feedback/AdminListPagination';
import { AdminListHeader, AdminListHeaderMetrics } from '@/components/feedback/AdminListRow';
import { NoticeBanner } from '@/components/feedback/NoticeBanner';
import {
  useAuditEntries, useAuditRisks, useAuditRules, usePermissionScopes,
} from './useAudit';
import type { AuditEntry, AuditRule, RiskEvent } from './schema';
import { AuditCard } from './components/AuditCard';
import { BatchToolbar } from './components/BatchToolbar';
import { ExportAuditModal, type ExportFormat } from './components/ExportAuditModal';
import { RiskTab } from './components/tabs/RiskTab';
import { PermissionTab } from './components/tabs/PermissionTab';
import { RuleTab } from './components/tabs/RuleTab';

type ViewId = 'record' | 'risk' | 'permission' | 'rule';

function downloadBlob(blob: Blob, filename: string) {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  if (typeof URL.createObjectURL !== 'function') return;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

const VIEW_OPTIONS: { id: ViewId; label: string }[] = [
  { id: 'record', label: '调用记录' },
  { id: 'risk', label: '风险事件' },
  { id: 'permission', label: '权限审查' },
  { id: 'rule', label: '审计规则' },
];

export default function AuditPage() {
  const navigate = useNavigate();
  const entriesQuery = useAuditEntries();
  const risksQuery = useAuditRisks();
  const rulesQuery = useAuditRules();
  const scopesQuery = usePermissionScopes();

  const baseEntries = entriesQuery.data ?? [];
  const baseRisks = risksQuery.data ?? [];
  const baseRules = rulesQuery.data ?? [];
  const baseScopes = scopesQuery.data ?? [];

  const entries = baseEntries;
  const risks = baseRisks;
  const rules = baseRules;
  const [view, setView] = useState<ViewId>('record');
  const [search, setSearch] = useState('');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [exportOpen, setExportOpen] = useState(false);
  const [notice, setNotice] = useState('');
  const server = useServerAction(setNotice);
  const [page, setPage] = useState(1);

  const unresolvedRisks = risks.filter((r) => !r.resolved).length;

  const visibleEntries = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (q.length === 0) return entries;
    return entries.filter((e) =>
      `${e.id} ${e.toolName} ${e.actor} ${e.sessionId} ${e.category} ${e.reason ?? ''}`.toLowerCase().includes(q),
    );
  }, [entries, search]);

  useEffect(() => { setPage(1); }, [search, view]);
  const paged = useMemo(() => paginateItems(visibleEntries, page), [visibleEntries, page]);

  const toggleSelect = (id: string) =>
    setSelectedIds((current) => (current.includes(id) ? current.filter((x) => x !== id) : [...current, id]));

  const toggleStar = (id: string) => server.mutate({ path: `/api/admin/audit/entries/${id}`, method: 'PATCH', body: { starred: !entries.find((e) => e.id === id)?.starred } });
  const handleBatchExport = () => setExportOpen(true);
  const handleBatchResolve = () => server.mutate({ path: '/api/admin/audit/entries/batch-resolve', body: { ids: selectedIds }, success: '已提交处置', onSuccess: () => setSelectedIds([]) });
  const handleBatchMark = () => server.mutate({ path: '/api/admin/audit/entries/batch-review', body: { ids: selectedIds }, success: '已审查', onSuccess: () => setSelectedIds([]) });

  const handleExport = (format: ExportFormat) => {
    const list = selectedIds.length > 0 ? entries.filter((s) => selectedIds.includes(s.id)) : entries;
    if (format === 'json') {
      downloadBlob(new Blob([JSON.stringify(list, null, 2)], { type: 'application/json' }), 'audit.json');
    } else {
      const csv = [
        'id,category,tool,actor,severity,outcome,score,time',
        ...list.map((e) => `${e.id},${e.category},${e.toolName},${e.actor},${e.severity},${e.outcome},${e.riskScore},${e.occurredAt}`),
      ].join('\n');
      downloadBlob(new Blob([csv], { type: 'text/csv' }), 'audit.csv');
    }
    setNotice(`已导出 ${list.length} 条审计为 ${format.toUpperCase()} 文件。`);
  };

  const handleExportOne = (entry: AuditEntry) => {
    downloadBlob(new Blob([JSON.stringify(entry, null, 2)], { type: 'application/json' }), `audit-${entry.id}.json`);
    setNotice(`已导出审计条目「${entry.toolName}」。`);
  };

  const handleResolveEntry = (entry: AuditEntry) => server.mutate({ path: `/api/admin/audit/entries/${entry.id}/resolve`, success: '已提交处置' });
  const handleResolveRisk = (id: string) => server.mutate({ path: `/api/admin/audit/risks/${id}`, method: 'PATCH', body: { resolved: !risks.find((r) => r.id === id)?.resolved } });
  const handleToggleRule = (id: string) => server.mutate({ path: `/api/admin/audit/rules/${id}`, method: 'PATCH', body: { enabled: !rules.find((r) => r.id === id)?.enabled } });
  const handleReReview = (role: string) => server.mutate({ path: '/api/admin/audit/scopes/review', body: { role }, success: '已重新审查' });
  const goEntryDetail = (e: AuditEntry) => navigate(`/admin/tool-audit/${e.id}`);

  const viewSelect = (
    <select
      aria-label="视图"
      value={view}
      onChange={(e) => setView(e.target.value as ViewId)}
      className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 text-xs outline-none focus:border-[var(--brand)]"
    >
      {VIEW_OPTIONS.map((o) => (
        <option key={o.id} value={o.id}>{o.label}</option>
      ))}
    </select>
  );

  return (
    <div className="tool-audit-page mx-auto w-full max-w-[1440px] space-y-6 p-5 pb-16 sm:p-8 xl:px-10">
      <section className="relative overflow-hidden rounded-[28px] border border-[var(--border)] bg-[var(--surface-1)] px-6 py-8 shadow-[var(--shadow-sm)] sm:px-8">
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden rounded-[28px]">
          <div className="absolute right-0 top-0 h-full w-1/2 bg-[radial-gradient(circle_at_top_right,rgba(244,63,94,0.10),transparent_68%)]" />
        </div>
        <div className="relative">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-rose-700 dark:text-rose-300">
            ADMIN / 工具审计
          </p>
          <h2 className="mt-3 text-2xl font-semibold tracking-tight sm:text-3xl xl:text-4xl">
            审查工具调用与风险规则。
          </h2>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-[var(--text-muted)]">
            {entries.length} 条审计 · {unresolvedRisks} 未处置风险。
          </p>
        </div>
      </section>

      {notice && (
        <NoticeBanner tone="violet" onClose={() => setNotice('')}>
          {notice}
        </NoticeBanner>
      )}

      {selectedIds.length > 0 && view === 'record' && (
        <BatchToolbar
          count={selectedIds.length}
          onClear={() => setSelectedIds([])}
          onBatchExport={handleBatchExport}
          onBatchResolve={handleBatchResolve}
          onBatchMark={handleBatchMark}
        />
      )}

      {view === 'record' && (
        <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
          <div className="flex flex-col gap-2 border-b border-[var(--border)] px-4 py-3 sm:flex-row sm:items-center sm:px-5">
            <label className="relative min-w-0 flex-1">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--text-muted)]" />
              <input
                aria-label="搜索审计"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="搜索工具 / 调用方 / 会话"
                className="h-9 w-full rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] pl-8 pr-3 text-sm outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--brand)]"
              />
            </label>
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              {viewSelect}
              <button
                type="button"
                onClick={() => setExportOpen(true)}
                className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-3 text-xs font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]"
              >
                <Download className="h-3.5 w-3.5" />
                导出
              </button>
              <button
                type="button"
                onClick={() => server.mutate({ path: '/api/admin/audit/investigations', success: '已下发核查任务' })}
                className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-3 text-xs font-semibold text-[var(--text-secondary)] hover:border-rose-500 hover:text-rose-600"
              >
                <ShieldQuestion className="h-3.5 w-3.5" />
                紧急核查
              </button>
              <button
                type="button"
                onClick={() => navigate('/admin/tool-audit/rules/new')}
                className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-rose-600 px-3 text-xs font-semibold text-white hover:bg-rose-700"
              >
                <Plus className="h-3.5 w-3.5" />
                新建规则
              </button>
            </div>
          </div>
          <AdminListHeader metrics={<AdminListHeaderMetrics labels={['风险', '时间']} />} />
          <div className="divide-y divide-[var(--border)]">
            {paged.slice.map((e) => (
              <AuditCard
                key={e.id}
                entry={e}
                selected={selectedIds.includes(e.id)}
                onToggleSelect={toggleSelect}
                onSelect={goEntryDetail}
                onToggleStar={toggleStar}
                onExportOne={handleExportOne}
                onResolve={handleResolveEntry}
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
          {visibleEntries.length === 0 && (
            <div className="px-5 pb-8 text-center">
              <Search className="mx-auto h-6 w-6 text-[var(--text-muted)]" />
              <p className="mt-3 text-sm font-semibold">没有匹配的审计记录</p>
              <p className="mt-1 text-xs text-[var(--text-muted)]">尝试其他关键词或清除搜索。</p>
            </div>
          )}
        </div>
      )}

      {view !== 'record' && (
        <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
          <div className="flex flex-wrap items-center gap-2 border-b border-[var(--border)] px-4 py-3 sm:px-5">
            {viewSelect}
            {view === 'rule' && (
              <button
                type="button"
                onClick={() => navigate('/admin/tool-audit/rules/new')}
                className="ml-auto inline-flex h-9 items-center gap-1.5 rounded-lg bg-rose-600 px-3 text-xs font-semibold text-white hover:bg-rose-700"
              >
                <Plus className="h-3.5 w-3.5" />
                新建规则
              </button>
            )}
          </div>
          {view === 'risk' && <RiskTab risks={risks} onToggleResolve={handleResolveRisk} />}
          {view === 'permission' && <PermissionTab scopes={baseScopes} onReReview={handleReReview} />}
          {view === 'rule' && (
            <RuleTab rules={rules} onToggleRule={handleToggleRule} onCreateRule={() => navigate('/admin/tool-audit/rules/new')} />
          )}
        </div>
      )}

      <ExportAuditModal
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        onExport={handleExport}
        total={entries.length}
        selectedCount={selectedIds.length}
      />
    </div>
  );
}
