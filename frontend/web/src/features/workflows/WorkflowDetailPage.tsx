/**
 * 管理侧「工作流详情」独立页面 — 路由 /admin/workflows/:id
 *
 * 布局:画布为主的三栏(节点类型树 + 画布 + 属性面板)
 * 顶部:
 * - 左上角 icon-only 返回按钮
 * - 名称 + 状态 + 触发方式(精简)
 * - 右侧动作组:编辑 toggle / 保存 / 版本 / 发布
 *
 * 「查看 / 编辑」通过 readOnly prop 切换:FlowEditor 内部控制画布可拖/可连/可改属性。
 */
import { useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { ArrowLeft, History, Rocket, Save, Pencil, X, Workflow as WorkflowIcon } from 'lucide-react';
import { useWorkflow, useUpdateWorkflow } from './useWorkflows';
import { normalizeError } from '@/api/shared/http-error';
import type { Flow } from './schema';
import { STATUS_BADGE } from './components/constants';
import { FlowEditor } from './components/FlowEditor';

function NotFound() {
  return (
    <div className="mx-auto w-full max-w-[1600px] p-5 pb-16 sm:p-8 xl:px-8">
      <button
        type="button"
        onClick={() => { window.location.href = '/admin/workflows'; }}
        aria-label="返回工作流管理"
        className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-[var(--text-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--brand)]"
      >
        <ArrowLeft className="h-4 w-4" />
      </button>
      <div className="mt-6 rounded-2xl border border-dashed border-[var(--border)] bg-[var(--surface-1)] p-8 text-center">
        <p className="text-sm font-semibold">工作流不存在或已被删除</p>
        <p className="mt-1 text-xs text-[var(--text-muted)]">请返回列表重新选择。</p>
      </div>
    </div>
  );
}

export default function WorkflowDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const isEditMode = searchParams.get('edit') === '1';
  const { data: flow, isLoading, isError, error } = useWorkflow(id || null);
  const [notice, setNotice] = useState('');
  const [localFlows, setLocalFlows] = useState<Flow[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const update = useUpdateWorkflow();

  useEffect(() => {
    if (flow && (localFlows.length === 0 || localFlows[0]?.id !== flow.id)) {
      setLocalFlows([flow]);
    }
  }, [flow, localFlows]);

  if (isLoading) {
    return (
      <div className="mx-auto w-full max-w-[1600px] p-5 pb-16 sm:p-8 xl:px-8">
        <button
          type="button"
          onClick={() => { window.location.href = '/admin/workflows'; }}
          aria-label="返回工作流管理"
          className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-[var(--text-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--brand)]"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <p className="mt-6 text-sm text-[var(--text-muted)]">加载中…</p>
      </div>
    );
  }

  if (isError) return <div className="mx-auto w-full max-w-[1600px] p-5 pb-16 sm:p-8 xl:px-8"><p role="alert" className="rounded-xl border border-rose-300 bg-rose-50 p-4 text-sm text-rose-700">加载失败：{normalizeError(error).message}</p></div>;
  if (!flow) return <NotFound />;

  const editorFlow = localFlows[0] ?? flow;
  const readOnly = !isEditMode;
  const badge = STATUS_BADGE[flow.status];

  const onSave = () => {
    update.mutate({
      id: editorFlow.id,
      patch: { initialNodes: editorFlow.initialNodes, initialEdges: editorFlow.initialEdges },
    }, {
      onSuccess: () => setNotice(`已保存工作流「${editorFlow.name}」,共 ${editorFlow.initialNodes.length} 个节点 / ${editorFlow.initialEdges.length} 条连线。`),
      onError: (cause) => setNotice(`保存失败：${normalizeError(cause).message}`),
    });
  };

  return (
    <div className="mx-auto w-full max-w-[1600px] space-y-2 p-3 pb-6 sm:p-4 xl:px-6">
      <div className="flex items-start gap-3">
        <button
          type="button"
          onClick={() => { window.location.href = '/admin/workflows'; }}
          aria-label="返回工作流管理"
          title="返回工作流管理"
          className="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-[var(--text-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--brand)]"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <WorkflowIcon className="h-4 w-4 text-[var(--brand)]" />
            <h1 className="truncate text-base font-semibold tracking-tight">{flow.name}</h1>
            <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${badge.className}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${badge.dot}`} />
              {badge.label}
            </span>
            <span className="rounded-md bg-[var(--bg-elevated)] px-2 py-0.5 text-[10px] font-mono text-[var(--text-muted)]">{flow.trigger}</span>
          </div>
          <p className="mt-0.5 truncate text-[11px] text-[var(--text-muted)]">{flow.description}</p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {isEditMode && (
            <>
              <button type="button" onClick={onSave} className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]">
                <Save className="h-3.5 w-3.5" />保存
              </button>
              <button type="button" onClick={() => setNotice('版本管理接口暂未提供,请求未执行。')} className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 text-xs font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]">
                <History className="h-3.5 w-3.5" />版本
              </button>
              <button type="button" onClick={() => update.mutate({ id: flow.id, patch: { status: 'published' } }, { onSuccess: () => setNotice('已发布'), onError: (cause) => setNotice(`发布失败：${normalizeError(cause).message}`) })} disabled={flow.status === 'published'} className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-emerald-300 bg-emerald-50 px-2.5 text-xs font-semibold text-emerald-700 disabled:cursor-not-allowed disabled:opacity-50 hover:bg-emerald-100 dark:bg-emerald-500/15 dark:text-emerald-300">
                <Rocket className="h-3.5 w-3.5" />发布
              </button>
            </>
          )}
          <button
            type="button"
            onClick={() => {
              if (isEditMode) setSearchParams({});
              else setSearchParams({ edit: '1' });
            }}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-[var(--brand)] bg-[var(--brand)] px-3 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]"
          >
            <Pencil className="h-3.5 w-3.5" />
            {isEditMode ? '退出编辑' : '编辑'}
          </button>
        </div>
      </div>

      {notice && (
        <div className="flex items-center gap-3 rounded-xl border border-amber-300 bg-amber-50 px-4 py-2 text-xs text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
          <span className="flex-1">{notice}</span>
          <button type="button" onClick={() => setNotice('')} aria-label="关闭提示" className="rounded p-0.5 hover:bg-amber-100 dark:hover:bg-amber-500/20"><X className="h-3.5 w-3.5" /></button>
        </div>
      )}

      <FlowEditor
        flow={editorFlow}
        selectedNodeId={selectedNodeId}
        setSelectedNodeId={setSelectedNodeId}
        setFlows={setLocalFlows}
        onChange={(nodes, edges) => setLocalFlows((current) => current.length ? [{ ...current[0], initialNodes: nodes, initialEdges: edges }] : current)}
        onOpenNodeConfig={() => setNotice('节点高级配置接口暂未提供,请求未执行。')}
        setNotice={setNotice}
        readOnly={readOnly}
      />
    </div>
  );
}
