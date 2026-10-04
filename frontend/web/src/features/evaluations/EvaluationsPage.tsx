/**
 * AdminEvaluations — 评测中心 orchestrator。
 * 对齐技能管理 / ModelsPage：无子模块 Tab，Hero 轻量，列表工具栏 + 视图筛选。
 */
import { Plus, Search, Upload } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AdminListPagination, paginateItems } from '@/components/feedback/AdminListPagination';
import { AdminListHeader, AdminListHeaderMetrics } from '@/components/feedback/AdminListRow';
import { NoticeBanner } from '@/components/feedback/NoticeBanner';
import { useEvalResults, useEvalSuites, useEvalSuiteStats } from './useEvaluations';
import type { CaseTemplate, EvalResult, EvalSuite, EvalStatus, EvalSuiteType, ExchangeFormat } from './schema';
import { mockCaseTemplates } from './fixtures';
import { BatchToolbar } from './components/BatchToolbar';
import { STATUS_FILTER, TYPE_FILTER, uid } from './components/constants';
import { DeleteSuiteModal, ExportSuiteModal, ImportSuiteModal, RunConfirmModal } from './components/Modals';
import { SuiteCard } from './components/SuiteCard';
import { CaseTab, ResultTab, TemplateTab } from './components/tabs/Tabs';

type ViewId = 'suite' | 'result' | 'case' | 'template';

const EMPTY_SUITES: EvalSuite[] = [];
const EMPTY_RESULTS: EvalResult[] = [];

export default function EvaluationsPage() {
  const navigate = useNavigate();
  const remoteSuites = useEvalSuites();
  const remoteResults = useEvalResults();
  const suitesData = remoteSuites.data ?? EMPTY_SUITES;
  const resultsData = remoteResults.data ?? EMPTY_RESULTS;

  const [suites, setSuites] = useState<EvalSuite[]>([]);
  const [view, setView] = useState<ViewId>('suite');
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState<'all' | EvalSuiteType>('all');
  const [statusFilter, setStatusFilter] = useState<'all' | EvalStatus>('all');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [runTarget, setRunTarget] = useState<EvalSuite | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<EvalSuite | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [notice, setNotice] = useState('');
  const [page, setPage] = useState(1);

  const stats = useEvalSuiteStats(suites);

  useEffect(() => { setSuites(suitesData); }, [remoteSuites.data]);

  const visibleSuites = useMemo(() => {
    const q = search.trim().toLowerCase();
    return suites.filter((s) =>
      (typeFilter === 'all' || s.type === typeFilter) &&
      (statusFilter === 'all' || s.status === statusFilter) &&
      (q.length === 0 || `${s.name} ${s.description} ${s.owner} ${s.tags.join(' ')}`.toLowerCase().includes(q)),
    );
  }, [suites, typeFilter, statusFilter, search]);

  useEffect(() => { setPage(1); }, [search, typeFilter, statusFilter, view]);
  const paged = useMemo(() => paginateItems(visibleSuites, page), [visibleSuites, page]);

  const goDetail = (suite: EvalSuite) => navigate(`/admin/evaluations/${suite.id}`);

  const toggleSelect = (id: string) => setSelectedIds((current) => current.includes(id) ? current.filter((x) => x !== id) : [...current, id]);
  const toggleStar = (id: string) => setSuites((current) => current.map((s) => s.id === id ? { ...s, starred: !s.starred } : s));

  const handleRun = (suite: EvalSuite) => {
    setSuites((current) => current.map((s) => s.id === suite.id ? { ...s, status: 'running', lastRunAt: '运行中' } : s));
    setNotice(`已加入运行队列:${suite.name}`);
    setRunTarget(null);
  };

  const handleDuplicate = (suite: EvalSuite) => {
    const copy: EvalSuite = { ...suite, id: uid('suite'), name: `${suite.name} 副本`, status: 'queued', cases: 0, passRate: 0, avgScore: 0, lastRunAt: '排队中', starred: false, trend: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], history: [] };
    setSuites((current) => [copy, ...current]);
    setNotice(`已复制套件:${copy.name}`);
  };

  const handleDelete = (suite: EvalSuite) => {
    setSuites((current) => current.filter((s) => s.id !== suite.id));
    setNotice(`已删除「${suite.name}」。`);
    setDeleteTarget(null);
  };

  const handleBatchRun = () => {
    setSuites((current) => current.map((s) => selectedIds.includes(s.id) ? { ...s, status: 'running', lastRunAt: '运行中' } : s));
    setNotice(`已批量运行 ${selectedIds.length} 个套件。`);
    setSelectedIds([]);
  };
  const handleBatchDelete = () => {
    setSuites((current) => current.filter((s) => !selectedIds.includes(s.id)));
    setNotice(`已批量删除 ${selectedIds.length} 个套件。`);
    setSelectedIds([]);
  };

  const handleImport = (count: number) => {
    for (let i = 0; i < count; i += 1) {
      const newSuite: EvalSuite = {
        id: uid('suite'),
        name: `导入套件 ${i + 1}`,
        description: '从外部文件导入,根据系统提示配置评分标准与用例。',
        type: 'capability',
        owner: '张敏',
        status: 'queued',
        cases: 0,
        passRate: 0,
        avgScore: 0,
        lastRunAt: '排队中',
        schedule: '每周一 09:00',
        target: '待指定',
        starred: false,
        tags: [],
        trend: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        casesList: [],
        criteria: [],
        history: [],
      };
      setSuites((current) => [newSuite, ...current]);
    }
    setNotice(`已导入 ${count} 个套件(以草稿状态进入)。`);
  };

  const handleExport = (format: ExchangeFormat) => {
    const list = selectedIds.length > 0 ? suites.filter((s) => selectedIds.includes(s.id)) : suites;
    const payload = list.map((s) => ({ id: s.id, name: s.name, type: s.type, target: s.target, schedule: s.schedule, criteria: s.criteria }));
    if (typeof window === 'undefined' || typeof document === 'undefined') return;
    if (format === 'json') {
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
      downloadBlob(blob, 'eval-suites.json');
    } else {
      const yaml = payload.map((p) => `- id: "${p.id}"\n  name: "${p.name}"\n  type: "${p.type}"\n  target: "${p.target}"\n  schedule: "${p.schedule}"`).join('\n');
      const blob = new Blob([`${yaml}\n`], { type: 'text/yaml' });
      downloadBlob(blob, 'eval-suites.yaml');
    }
    setNotice(`已导出 ${list.length} 个套件为 ${format.toUpperCase()} 文件。`);
  };

  const handleAddTemplate = (template: CaseTemplate) => {
    const newSuite: EvalSuite = {
      id: uid('suite'),
      name: `${template.name} 套件`,
      description: template.description,
      type: template.type,
      owner: '张敏',
      status: 'queued',
      cases: 0,
      passRate: 0,
      avgScore: 0,
      lastRunAt: '排队中',
      schedule: '每周一 09:00',
      target: '待指定',
      starred: false,
      tags: [],
      trend: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
      casesList: [{ id: uid('case'), name: `${template.name} 示例`, input: template.inputExample, expected: template.expectedExample, status: 'skipped', durationMs: 0, score: 0 }],
      criteria: [...template.criteria],
      history: [],
    };
    setSuites((current) => [newSuite, ...current]);
    setNotice(`已从模板加入:${newSuite.name}`);
    setView('suite');
  };

  return (
    <div className="evaluations-page mx-auto w-full max-w-[1440px] space-y-6 p-5 pb-16 sm:p-8 xl:px-10">
      <section className="relative overflow-hidden rounded-[28px] border border-[var(--border)] bg-[var(--surface-1)] px-6 py-8 shadow-[var(--shadow-sm)] sm:px-8">
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden rounded-[28px]">
          <div className="absolute right-0 top-0 h-full w-1/2 bg-[radial-gradient(circle_at_top_right,rgba(20,184,166,0.10),transparent_68%)]" />
        </div>
        <div className="relative">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-teal-700 dark:text-teal-300">ADMIN / 评测中心</p>
          <h2 className="mt-3 text-2xl font-semibold tracking-tight sm:text-3xl xl:text-4xl">用套件评测智能体质量。</h2>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-[var(--text-muted)]">{suites.length} 个套件 · 本月通过 {stats.passed}。</p>
        </div>
      </section>

      {notice && (
        <NoticeBanner tone="violet" onClose={() => setNotice('')}>
          {notice}
        </NoticeBanner>
      )}

      {selectedIds.length > 0 && view === 'suite' && (
        <BatchToolbar
          count={selectedIds.length}
          onClear={() => setSelectedIds([])}
          onBatchRun={handleBatchRun}
          onBatchDelete={handleBatchDelete}
        />
      )}

      {view === 'suite' && (
        <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
          <div className="flex flex-col gap-2 border-b border-[var(--border)] px-4 py-3 sm:flex-row sm:items-center sm:px-5">
            <label className="relative min-w-0 flex-1">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--text-muted)]" />
              <input
                aria-label="搜索套件"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="搜索套件 / 标签"
                className="h-9 w-full rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] pl-8 pr-3 text-sm outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--brand)]"
              />
            </label>
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              <select
                aria-label="视图"
                value={view}
                onChange={(e) => setView(e.target.value as ViewId)}
                className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 text-xs outline-none focus:border-[var(--brand)]"
              >
                <option value="suite">评测套件</option>
                <option value="result">评测结果</option>
                <option value="case">评测用例</option>
                <option value="template">评测模板</option>
              </select>
              <select
                aria-label="类型"
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value as 'all' | EvalSuiteType)}
                className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 text-xs outline-none focus:border-[var(--brand)]"
              >
                {TYPE_FILTER.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
              </select>
              <select
                aria-label="状态"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as 'all' | EvalStatus)}
                className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 text-xs outline-none focus:border-[var(--brand)]"
              >
                {STATUS_FILTER.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
              </select>
              <button type="button" onClick={() => setImportOpen(true)} className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-3 text-xs font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]">
                <Upload className="h-3.5 w-3.5" />导入
              </button>
              <button type="button" onClick={() => navigate('/admin/evaluations/new')} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]">
                <Plus className="h-3.5 w-3.5" />新建套件
              </button>
            </div>
          </div>
          <AdminListHeader metrics={<AdminListHeaderMetrics labels={['用例', '通过率', '最近运行']} />} />
          <div className="divide-y divide-[var(--border)]">
            {paged.slice.map((suite) => (
              <SuiteCard
                key={suite.id}
                suite={suite}
                selected={selectedIds.includes(suite.id)}
                onToggleSelect={toggleSelect}
                onSelect={goDetail}
                onToggleStar={toggleStar}
                onRun={(s) => setRunTarget(s)}
                onDuplicate={handleDuplicate}
                onRequestDelete={setDeleteTarget}
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
          {visibleSuites.length === 0 && (
            <div className="px-5 pb-8 text-center">
              <Search className="mx-auto h-6 w-6 text-[var(--text-muted)]" />
              <p className="mt-3 text-sm font-semibold">没有匹配的套件</p>
              <p className="mt-1 text-xs text-[var(--text-muted)]">尝试其他关键词或清除筛选。</p>
            </div>
          )}
        </div>
      )}

      {view !== 'suite' && (
        <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
          <div className="flex flex-wrap items-center gap-2 border-b border-[var(--border)] px-4 py-3 sm:px-5">
            <select
              aria-label="视图"
              value={view}
              onChange={(e) => setView(e.target.value as ViewId)}
              className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 text-xs outline-none focus:border-[var(--brand)]"
            >
              <option value="suite">评测套件</option>
              <option value="result">评测结果</option>
              <option value="case">评测用例</option>
              <option value="template">评测模板</option>
            </select>
          </div>
          <div className="p-5">
            {view === 'result' && <ResultTab results={resultsData as EvalResult[]} />}
            {view === 'case' && <CaseTab suites={suites} />}
            {view === 'template' && (
              <TemplateTab
                templates={mockCaseTemplates}
                onAddTemplate={handleAddTemplate}
              />
            )}
          </div>
        </div>
      )}

      <RunConfirmModal
        open={runTarget !== null}
        onClose={() => setRunTarget(null)}
        onConfirm={() => runTarget && handleRun(runTarget)}
        suite={runTarget}
      />

      <DeleteSuiteModal
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => deleteTarget && handleDelete(deleteTarget)}
        suite={deleteTarget}
      />

      <ImportSuiteModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImport={handleImport}
      />

      <ExportSuiteModal
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        onExport={handleExport}
        total={suites.length}
        selectedCount={selectedIds.length}
      />
    </div>
  );
}

function downloadBlob(blob: Blob, filename: string) {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
