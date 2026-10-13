/**
 * 管理侧「智能体详情」独立页面 — 路由 /admin/agents/:id
 *
 * 内容用 AgentEditor 渲染 9 面板;页面级状态:面板切换、版本对比、评测进度。
 *
 * 编辑态切换:URL ?edit=1
 */
import { useEffect, useMemo, useState } from 'react';
import { Navigate, useLocation, useParams, useSearchParams } from 'react-router-dom';
import { Edit3, Save } from 'lucide-react';
import type { AgentEntry, EvalCase, PromptKey } from './schema';
import { useAgentVersions, useDiffVersions, useRunEval, useUpdateAgent } from './useAgents';
import { mockAgents } from './fixtures';
import { DiffDialog, type DiffPair } from './components/DiffDialog';
import { EvalProgress } from './components/Primitives';
import { AgentEditor } from './AgentEditor';

function NotFound() {
  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-4 p-5 pb-16 sm:p-8 xl:px-6">
      <div className="rounded-2xl border border-dashed border-[var(--border)] bg-[var(--surface-1)] p-8 text-center">
        <p className="text-sm font-semibold">智能体不存在或已被删除</p>
        <p className="mt-1 text-xs text-[var(--text-muted)]">请返回列表重新选择。</p>
      </div>
    </div>
  );
}

export default function AgentDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const location = useLocation();
  const [params, setSearchParams] = useSearchParams();
  const editing = params.get('edit') === '1';

  const agent = useMemo(() => mockAgents.find((a) => a.id === id) ?? null, [id]);

  const [promptDoc] = useState<string>('prompt');  // 预留,后续 AgentEditor 支持
  const [evalRunning, setEvalRunning] = useState<{ progress: number } | null>(null);
  const [lastEvalResult, setLastEvalResult] = useState<EvalCase[] | null>(null);
  const [diffOpen, setDiffOpen] = useState(false);
  const [diffPair, setDiffPair] = useState<DiffPair>({ base: { id: 'v3.1', label: 'v3.1' }, target: { id: 'v3.2', label: 'v3.2' } });
  const [diffBase, setDiffBase] = useState<Record<PromptKey, string>>({} as Record<PromptKey, string>);
  const [diffTarget, setDiffTarget] = useState<Record<PromptKey, string>>({} as Record<PromptKey, string>);

  const updateAgent = useUpdateAgent();
  const diffVersions = useDiffVersions();
  const runEval = useRunEval();
  // useAgentVersions used inside DrawerPanelVersions via prop pass; pre-warm cache here:
  useAgentVersions(agent?.id ?? '');

  useEffect(() => { void promptDoc; }, [promptDoc]);

  const handleOpenDiff = async () => {
    if (!agent) return;
    const versions = agent.versions;
    if (versions.length < 2) return;
    const previous = versions.find((v) => !v.current) ?? versions[versions.length - 1];
    const current = versions.find((v) => v.current) ?? versions[0];
    const resp = await diffVersions.mutateAsync({
      agentId: agent.id,
      leftVersion: previous.version,
      rightVersion: current.version,
    });
    setDiffPair({ base: { id: previous.version, label: previous.version }, target: { id: current.version, label: current.version } });
    setDiffBase(resp.leftPrompts);
    setDiffTarget(resp.rightPrompts);
    setDiffOpen(true);
  };

  const handleRunEval = async () => {
    if (!agent) return;
    setEvalRunning({ progress: 0 });
    const timer = window.setInterval(() => {
      setEvalRunning((prev) => prev ? { progress: Math.min(prev.progress + 12, 96) } : null);
    }, 220);
    const resp = await runEval.mutateAsync({ id: agent.id });
    window.clearInterval(timer);
    setEvalRunning(null);
    setLastEvalResult(resp.cases);
  };

  if (location.pathname.endsWith('/edit')) {
    return <Navigate to={`/admin/agents/${id}?edit=1`} replace />;
  }

  if (!agent) return <NotFound />;

  const toggleEdit = () => {
    const next = new URLSearchParams(params);
    if (editing) next.delete('edit');
    else next.set('edit', '1');
    setSearchParams(next, { replace: true });
  };

  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-4 p-5 pb-16 sm:p-8 xl:px-6">
      {/* 顶部 mode 切换 + 返回 */}
      <div className="mb-3 flex items-center justify-between">
        <button
          type="button"
          onClick={() => history.back()}
          className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs text-[var(--text-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--text)]"
        >
          ← 返回
        </button>
        <button
          type="button"
          onClick={toggleEdit}
          className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--brand)] bg-[var(--surface-1)] px-3 py-1.5 text-xs font-semibold text-[var(--brand)] hover:bg-[var(--brand-light)]"
        >
          {editing ? <Save className="h-3.5 w-3.5" /> : <Edit3 className="h-3.5 w-3.5" />}
          {editing ? '完成' : '编辑'}
        </button>
      </div>

      <AgentEditor
        mode={editing ? 'edit' : 'view'}
        initialDraft={agent as AgentEntry}
        onChange={editing
          ? (patch) => updateAgent.mutate({ id: agent.id, patch })
          : undefined
        }
        evalState={
          evalRunning
            ? { isRunning: true, progress: evalRunning.progress }
            : { isRunning: false, lastResult: lastEvalResult ?? undefined }
        }
        onRunEval={handleRunEval}
        onOpenDiff={handleOpenDiff}
      />

      {/* 评测进度 */}
      {evalRunning && (
        <div className="fixed bottom-6 right-6 z-40 w-72 rounded-2xl border border-[var(--brand)] bg-[var(--surface-1)] p-4 shadow-lg">
          <div className="flex items-center gap-2 text-xs font-semibold text-[var(--brand)]">
            正在评测 {agent.name}
          </div>
          <EvalProgress progress={evalRunning.progress} />
        </div>
      )}

      {/* 版本对比 */}
      <DiffDialog
        open={diffOpen}
        onClose={() => setDiffOpen(false)}
        pair={diffPair}
        baseContent={diffBase}
        targetContent={diffTarget}
        onChangePair={setDiffPair}
      />
    </div>
  );
}
