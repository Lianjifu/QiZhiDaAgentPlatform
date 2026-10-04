/**
 * WorkflowsPage — 工作流管理 list hub(纯列表,不再持有内嵌 editor 状态)。
 *
 * 4 tab(状态过滤器):全部 / 草稿 / 已发布 / 已下线。
 * 入口:
 * - 新建 → /admin/workflows/new
 * - 卡片点击 → /admin/workflows/:id(详情/编辑)
 *
 * 列表内 modal:发布为工具。
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { NoticeBanner } from '@/components/feedback/NoticeBanner';
import { useWorkflows } from './useWorkflows';
import type { Flow, WorkflowTabId } from './schema';
import { uid } from './components/constants';
import { OverviewTab } from './components/tabs/OverviewTab';
import { PublishAsToolModal } from './components/PublishAsToolModal';

const EMPTY_FLOWS: Flow[] = [];

export default function WorkflowsPage() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<WorkflowTabId>('all');
  const flowsQuery = useWorkflows();
  const remoteFlows = flowsQuery.data ?? EMPTY_FLOWS;
  const [flows, setFlows] = useState<Flow[]>(remoteFlows);
  const [notice, setNotice] = useState('');
  const [search, setSearch] = useState('');

  const [publishOpen, setPublishOpen] = useState(false);
  const [publishFlow, setPublishFlow] = useState<Flow | null>(null);
  const [toolId, setToolId] = useState('');
  const [toolDesc, setToolDesc] = useState('');
  const [toolInput, setToolInput] = useState('query:string:true');
  const [toolOutput, setToolOutput] = useState('result:string:true');

  useEffect(() => {
    setFlows(remoteFlows);
  }, [flowsQuery.data]);

  const visibleFlows = useMemo(() => {
    const base = tab === 'all' ? flows : flows.filter((f) => f.status === tab);
    if (!search.trim()) return base;
    const q = search.trim().toLowerCase();
    return base.filter((f) => `${f.name} ${f.description} ${f.owner} ${f.scene}`.toLowerCase().includes(q));
  }, [flows, tab, search]);

  const goCreate = () => navigate('/admin/workflows/new');
  const goView = (id: string) => navigate(`/admin/workflows/${id}`);

  const openPublish = (flow: Flow) => {
    setPublishFlow(flow);
    setToolId(flow.id.replace(/^wf-/, ''));
    setToolDesc(flow.description);
    setToolInput('query:string:true');
    setToolOutput('result:string:true');
    setPublishOpen(true);
  };

  const submitPublish = () => {
    if (!publishFlow) return;
    const v = publishFlow.versions[0]?.v || 'v1.0';
    setFlows((prev) => prev.map((f) => f.id === publishFlow.id ? {
      ...f, status: 'published', updatedAt: '刚刚',
      versions: [{ v: `${v}-已发布`, at: '刚刚', operator: '当前管理员', note: `发布为工具 ${toolId || f.id}` }, ...f.versions],
    } : f));
    setPublishOpen(false);
    setNotice(`「${publishFlow.name}」已发布为可被智能体调用的工具。`);
  };

  const retireFlow = (flow: Flow) => {
    setFlows((prev) => prev.map((f) => f.id === flow.id ? { ...f, status: 'retired', updatedAt: '刚刚' } : f));
    setNotice(`「${flow.name}」已下线,不再可被调用。`);
  };

  const copyFlow = (flow: Flow) => {
    const copyId = uid('wf');
    const copy: Flow = {
      ...flow, id: copyId, name: `${flow.name} · 副本`, status: 'draft',
      callCount: 0, boundAgents: [], updatedAt: '刚刚', createdAt: '刚刚',
      versions: [{ v: 'v0.1-草稿', at: '刚刚', operator: '当前管理员', note: '从副本复制' }],
      initialNodes: flow.initialNodes.map((n) => ({ ...n, id: `${n.id}-${copyId.slice(-3)}` })),
      initialEdges: [],
    };
    setFlows((prev) => [copy, ...prev]);
    setNotice(`已复制为「${flow.name} · 副本」。`);
  };

  return (
    <div className="workflow-page mx-auto w-full max-w-[1440px] space-y-6 p-5 pb-16 sm:p-8 xl:px-10">
      <section className="relative overflow-hidden rounded-[28px] border border-[var(--border)] bg-[var(--surface-1)] px-6 py-7 shadow-[var(--shadow-sm)] sm:px-8">
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden rounded-[28px]">
          <div className="absolute right-0 top-0 h-full w-1/2 bg-[radial-gradient(circle_at_top_right,rgba(245,158,11,0.12),transparent_68%)]" />
        </div>
        <div className="relative">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-amber-700 dark:text-amber-300">ADMIN / 工作流管理</p>
          <h2 className="mt-3 text-2xl font-semibold tracking-tight sm:text-3xl xl:text-4xl">编排并发布可执行工作流。</h2>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-[var(--text-muted)]">{flows.length} 条工作流 · {flows.filter((f) => f.status === 'published').length} 已发布。</p>
        </div>
      </section>

      {notice && (
        <NoticeBanner tone="amber" onClose={() => setNotice('')}>
          {notice}
        </NoticeBanner>
      )}

      <OverviewTab
        flows={visibleFlows}
        statusTab={tab}
        onStatus={setTab}
        search={search}
        onSearch={setSearch}
        onCreate={goCreate}
        onView={goView}
        onCopy={copyFlow}
        onPublish={openPublish}
        onRetire={retireFlow}
      />

      <PublishAsToolModal
        open={publishOpen}
        onClose={() => setPublishOpen(false)}
        flow={publishFlow}
        toolId={toolId} setToolId={setToolId}
        toolDesc={toolDesc} setToolDesc={setToolDesc}
        toolInput={toolInput} setToolInput={setToolInput}
        toolOutput={toolOutput} setToolOutput={setToolOutput}
        onSubmit={submitPublish}
      />
    </div>
  );
}
