import { useServerAction } from '@/services/useServerAction';
/**
 * AdminFeedback — orchestrator。
 * 对齐技能管理 / 模型配置：无子模块 Tab，Hero 轻量，列表工具栏承载筛选与导入/新建。
 * 详情页 + 新建工单 / 新建规则改为独立路由(/admin/feedback/:id · /admin/feedback/new · /admin/feedback/rules/new)。
 */
import { Plus, Search, Upload } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AdminListPagination, paginateItems } from '@/components/feedback/AdminListPagination';
import { AdminListHeader, AdminListHeaderMetrics } from '@/components/feedback/AdminListRow';
import { NoticeBanner } from '@/components/feedback/NoticeBanner';
import { useFeedbackList, useFeedbackRules, useFeedbackTickets, useFeedbackTopics } from './useFeedback';
import type { ExchangeFormat, Feedback, FeedbackPriority, FeedbackSentiment, FeedbackStatus, RoutingRule, Ticket, TopicCluster } from './schema';
import { uid, PRIORITY_FILTER, SENTIMENT_FILTER, STATUS_FILTER } from './components/constants';
import { DeleteFeedbackModal, ExportFeedbackModal, ImportFeedbackModal } from './components/Modals';
import { RuleTab, TicketTab, TopicTab } from './components/tabs/Tabs';
import { FeedbackCard } from './components/FeedbackCard';
import { BatchToolbar } from './components/BatchToolbar';

type ViewId = 'list' | 'ticket' | 'topic' | 'rule';

const EMPTY_FEEDBACK: Feedback[] = [];
const EMPTY_TICKETS: Ticket[] = [];
const EMPTY_TOPICS: TopicCluster[] = [];
const EMPTY_RULES: RoutingRule[] = [];

export default function FeedbackPage() {
  const navigate = useNavigate();
  const remoteList = useFeedbackList();
  const remoteTickets = useFeedbackTickets();
  const remoteTopics = useFeedbackTopics();
  const remoteRules = useFeedbackRules();
  const feedbackData = remoteList.data ?? EMPTY_FEEDBACK;
  const ticketsData = remoteTickets.data ?? EMPTY_TICKETS;
  const topicsData = remoteTopics.data ?? EMPTY_TOPICS;
  const rulesData = remoteRules.data ?? EMPTY_RULES;

  const feedback = feedbackData;
  const tickets = ticketsData;
  const topics = topicsData;
  const rules = rulesData;
  const [view, setView] = useState<ViewId>('list');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | FeedbackStatus>('all');
  const [sentimentFilter, setSentimentFilter] = useState<'all' | FeedbackSentiment>('all');
  const [priorityFilter, setPriorityFilter] = useState<'all' | FeedbackPriority>('all');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [deleteTarget, setDeleteTarget] = useState<Feedback | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [notice, setNotice] = useState('');
  const server = useServerAction(setNotice);
  const [page, setPage] = useState(1);






  const counts = useMemo(() => {
    const total = feedback.length;
    const negative = feedback.filter((f) => f.sentiment === 'negative').length;
    const positive = feedback.filter((f) => f.sentiment === 'positive').length;
    const newOnes = feedback.filter((f) => f.status === 'new').length;
    return { total, negative, positive, newOnes };
  }, [feedback]);

  const visibleFeedback = useMemo(() => {
    const q = search.trim().toLowerCase();
    return feedback.filter((f) =>
      (statusFilter === 'all' || f.status === statusFilter) &&
      (sentimentFilter === 'all' || f.sentiment === sentimentFilter) &&
      (priorityFilter === 'all' || f.priority === priorityFilter) &&
      (q.length === 0 || `${f.user} ${f.agent} ${f.topic} ${f.comment} ${f.tags.join(' ')}`.toLowerCase().includes(q)),
    );
  }, [feedback, statusFilter, sentimentFilter, priorityFilter, search]);

  useEffect(() => { setPage(1); }, [search, statusFilter, sentimentFilter, priorityFilter, view]);
  const paged = useMemo(() => paginateItems(visibleFeedback, page), [visibleFeedback, page]);

  const toggleSelect = (id: string) => setSelectedIds((current) => current.includes(id) ? current.filter((x) => x !== id) : [...current, id]);

  const handleSelectFeedback = (id: string) => navigate('/admin/feedback/' + id);

  const handleDelete = (fb: Feedback) => server.mutate({ path: `/api/admin/feedback/${fb.id}`, method: 'DELETE', success: '已删除反馈', onSuccess: () => setDeleteTarget(null) });
  const handleQuickTriage = (fb: Feedback) => server.mutate({ path: `/api/admin/feedback/${fb.id}`, method: 'PATCH', body: { status: 'triaged' }, success: '已分诊' });
  const handleQuickResolve = (fb: Feedback) => server.mutate({ path: `/api/admin/feedback/${fb.id}`, method: 'PATCH', body: { status: 'resolved' }, success: '已解决' });
  const batch = (action: string) => server.mutate({ path: `/api/admin/feedback/batch-${action}`, body: { ids: selectedIds }, success: '已完成批量操作', onSuccess: () => setSelectedIds([]) });
  const handleBatchTriage = () => batch('triage');
  const handleBatchResolve = () => batch('resolve');
  const handleBatchDelete = () => batch('delete');
  const handleImport = (_count: number, content: string, format: ExchangeFormat) => server.mutate({ path: '/api/admin/feedback/import', body: { content, format }, success: '已导入', onSuccess: () => setImportOpen(false) });

  const handleExport = (format: ExchangeFormat) => {
    const list = selectedIds.length > 0 ? feedback.filter((f) => selectedIds.includes(f.id)) : feedback;
    const payload = list.map((f) => ({ id: f.id, user: f.user, agent: f.agent, topic: f.topic, comment: f.comment, sentiment: f.sentiment, status: f.status }));
    if (typeof window === 'undefined' || typeof document === 'undefined') return;
    if (format === 'json') {
      downloadBlob(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }), 'feedback.json');
    } else {
      const yaml = payload.map((p) => `- id: "${p.id}"\n  user: "${p.user}"\n  topic: "${p.topic}"\n  comment: "${p.comment}"\n  sentiment: "${p.sentiment}"`).join('\n');
      downloadBlob(new Blob([`${yaml}\n`], { type: 'text/yaml' }), 'feedback.yaml');
    }
    setNotice(`已导出 ${list.length} 条反馈为 ${format.toUpperCase()} 文件。`);
  };

  const handleRuleToggle = (id: string) => server.mutate({ path: `/api/admin/feedback/rules/${id}`, method: 'PATCH', body: { enabled: !rules.find((r) => r.id === id)?.enabled }, success: '已更新规则' });
  const handleRuleDelete = (id: string) => server.mutate({ path: `/api/admin/feedback/rules/${id}`, method: 'DELETE', success: '已删除规则' });

  const positivePct = counts.total > 0 ? (counts.positive / counts.total) * 100 : 0;

  const viewSelect = (
    <select
      aria-label="视图"
      value={view}
      onChange={(e) => setView(e.target.value as ViewId)}
      className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 text-xs outline-none focus:border-[var(--brand)]"
    >
      <option value="list">反馈列表</option>
      <option value="ticket">工单管理</option>
      <option value="topic">反馈主题</option>
      <option value="rule">规则模板</option>
    </select>
  );

  return (
    <div className="feedback-page mx-auto w-full max-w-[1440px] space-y-6 p-5 pb-16 sm:p-8 xl:px-10">
      <section className="relative overflow-hidden rounded-[28px] border border-[var(--border)] bg-[var(--surface-1)] px-6 py-8 shadow-[var(--shadow-sm)] sm:px-8">
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden rounded-[28px]">
          <div className="absolute right-0 top-0 h-full w-1/2 bg-[radial-gradient(circle_at_top_right,rgba(245,158,11,0.10),transparent_68%)]" />
        </div>
        <div className="relative">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-amber-700 dark:text-amber-300">ADMIN / 用户反馈</p>
          <h2 className="mt-3 text-2xl font-semibold tracking-tight sm:text-3xl xl:text-4xl">收集、分诊并处理用户意见。</h2>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-[var(--text-muted)]">{feedback.length} 条反馈 · {counts.newOnes} 条待分诊 · 正面率 {positivePct.toFixed(0)}%。</p>
        </div>
      </section>

      {notice && (
        <NoticeBanner tone="violet" onClose={() => setNotice('')}>
          {notice}
        </NoticeBanner>
      )}

      {selectedIds.length > 0 && view === 'list' && (
        <BatchToolbar
          count={selectedIds.length}
          onClear={() => setSelectedIds([])}
          onBatchTriage={handleBatchTriage}
          onBatchResolve={handleBatchResolve}
          onBatchDelete={handleBatchDelete}
        />
      )}

      {view === 'list' && (
        <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
          <div className="flex flex-col gap-2 border-b border-[var(--border)] px-4 py-3 sm:flex-row sm:items-center sm:px-5">
            <label className="relative min-w-0 flex-1">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--text-muted)]" />
              <input
                aria-label="搜索反馈"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="搜索反馈 / 用户 / 主题"
                className="h-9 w-full rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] pl-8 pr-3 text-sm outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--brand)]"
              />
            </label>
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              {viewSelect}
              <select
                aria-label="状态"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as 'all' | FeedbackStatus)}
                className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 text-xs outline-none focus:border-[var(--brand)]"
              >
                {STATUS_FILTER.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
              </select>
              <select
                aria-label="情感"
                value={sentimentFilter}
                onChange={(e) => setSentimentFilter(e.target.value as 'all' | FeedbackSentiment)}
                className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 text-xs outline-none focus:border-[var(--brand)]"
              >
                {SENTIMENT_FILTER.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
              </select>
              <select
                aria-label="优先级"
                value={priorityFilter}
                onChange={(e) => setPriorityFilter(e.target.value as 'all' | FeedbackPriority)}
                className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 text-xs outline-none focus:border-[var(--brand)]"
              >
                {PRIORITY_FILTER.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
              </select>
              <button type="button" onClick={() => setImportOpen(true)} className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-3 text-xs font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]">
                <Upload className="h-3.5 w-3.5" />导入
              </button>
              <button type="button" onClick={() => navigate('/admin/feedback/new')} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]">
                <Plus className="h-3.5 w-3.5" />新建工单
              </button>
            </div>
          </div>
          <AdminListHeader hasStar={false} metrics={<AdminListHeaderMetrics labels={['评分', '提交时间']} />} />
          <div className="divide-y divide-[var(--border)]">
            {paged.slice.map((fb) => (
              <FeedbackCard
                key={fb.id}
                fb={fb}
                selected={selectedIds.includes(fb.id)}
                onToggleSelect={toggleSelect}
                onSelect={handleSelectFeedback}
                onQuickTriage={handleQuickTriage}
                onQuickResolve={handleQuickResolve}
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
          {visibleFeedback.length === 0 && (
            <div className="px-5 pb-8 text-center">
              <Search className="mx-auto h-6 w-6 text-[var(--text-muted)]" />
              <p className="mt-3 text-sm font-semibold">没有匹配的反馈</p>
              <p className="mt-1 text-xs text-[var(--text-muted)]">尝试其他关键词或清除筛选。</p>
            </div>
          )}
        </div>
      )}

      {view !== 'list' && (
        <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
          <div className="flex flex-wrap items-center gap-2 border-b border-[var(--border)] px-4 py-3 sm:px-5">
            {viewSelect}
            {view === 'ticket' && (
              <button type="button" onClick={() => navigate('/admin/feedback/new')} className="ml-auto inline-flex h-9 items-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]">
                <Plus className="h-3.5 w-3.5" />新建工单
              </button>
            )}
            {view === 'rule' && (
              <button type="button" onClick={() => navigate('/admin/feedback/rules/new')} className="ml-auto inline-flex h-9 items-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]">
                <Plus className="h-3.5 w-3.5" />新建规则
              </button>
            )}
          </div>
          {view === 'ticket' && (
            <TicketTab tickets={tickets} onCreate={() => navigate('/admin/feedback/new')} hideHeaderCreate />
          )}
          {view === 'topic' && (
            <TopicTab topics={topics} onJumpToTickets={() => setView('ticket')} />
          )}
          {view === 'rule' && (
            <RuleTab rules={rules} onCreate={() => navigate('/admin/feedback/rules/new')} onToggle={handleRuleToggle} onDelete={handleRuleDelete} hideHeaderCreate />
          )}
        </div>
      )}

      <DeleteFeedbackModal open={deleteTarget !== null} onClose={() => setDeleteTarget(null)} onConfirm={() => deleteTarget && handleDelete(deleteTarget)} fb={deleteTarget} />
      <ImportFeedbackModal open={importOpen} onClose={() => setImportOpen(false)} onImport={handleImport} />
      <ExportFeedbackModal open={exportOpen} onClose={() => setExportOpen(false)} onExport={handleExport} total={feedback.length} selectedCount={selectedIds.length} />
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
