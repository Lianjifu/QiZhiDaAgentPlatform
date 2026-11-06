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
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AdminHero } from '@/components/feedback/AdminHero';
import { AdminPage } from '@/components/feedback/AdminPage';
import { NoticeBanner } from '@/components/feedback/NoticeBanner';
import { useWorkflows, useCreateWorkflow, useUpdateWorkflow } from './useWorkflows';
import { normalizeError } from '@/api/shared/http-error';
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
  const flows = remoteFlows;
  const [notice, setNotice] = useState('');
  const [search, setSearch] = useState('');

  const [publishOpen, setPublishOpen] = useState(false);
  const [publishFlow, setPublishFlow] = useState<Flow | null>(null);
  const [toolId, setToolId] = useState('');
  const [toolDesc, setToolDesc] = useState('');
  const [toolInput, setToolInput] = useState('query:string:true');
  const [toolOutput, setToolOutput] = useState('result:string:true');

  const update = useUpdateWorkflow();
  const create = useCreateWorkflow();

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
    update.mutate({ id: publishFlow.id, patch: { status: 'published' } }, {
      onSuccess: () => { setPublishOpen(false); setNotice(`「${publishFlow.name}」已发布为可被智能体调用的工具。`); },
      onError: (cause) => setNotice(`发布失败：${normalizeError(cause).message}`),
    });
  };

  const retireFlow = (flow: Flow) => {
    update.mutate({ id: flow.id, patch: { status: 'retired' } }, {
      onSuccess: () => setNotice(`「${flow.name}」已下线,不再可被调用。`),
      onError: (cause) => setNotice(`下线失败：${normalizeError(cause).message}`),
    });
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
    create.mutate(copy, {
      onSuccess: () => setNotice(`已复制为「${flow.name} · 副本」。`),
      onError: (cause) => setNotice(`复制失败：${normalizeError(cause).message}`),
    });
  };

  return (
    <AdminPage pageClass="workflow-page" density="lg">
      <AdminHero
        eyebrow="ADMIN / 工作流管理"
        title="编排并发布可执行工作流。"
        description={<>{flows.length} 条工作流 · {flows.filter((f) => f.status === 'published').length} 已发布。</>}
        tone="amber"
        headingLevel="h2"
      />

      {notice && (
        <NoticeBanner tone="amber" onClose={() => setNotice('')}>
          {notice}
        </NoticeBanner>
      )}
      {flowsQuery.isError && <p role="alert" className="rounded-xl border border-rose-300 bg-rose-50 px-4 py-3 text-sm text-rose-700">加载失败：{normalizeError(flowsQuery.error).message}</p>}

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
    </AdminPage>
  );
}
