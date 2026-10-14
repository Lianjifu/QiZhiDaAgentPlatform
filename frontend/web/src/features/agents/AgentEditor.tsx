/**
 * AgentEditor — 智能体统一编辑器(create / edit / view 三模)。
 *
 * 取代 WizardModal 4 步向导 + AgentDetailPage 内嵌的 9 面板 drawer。
 * 9 面板内容完全复用 DrawerPanels;Editor 只负责:
 *   - 局部 draft state(累 onChange patch)
 *   - 模式相关 UI 差异(create 顶部 onboarding 横幅 / Save Draft+Publish;edit 顶部 Edit/Complete;view 只读)
 *   - 头部动作栏与底部 footer
 *
 * Props 设计:
 *   - initialDraft: 必填(空草稿由父 makeEmptyDraft 构造)
 *   - onChange(patch): patch 累到 draft 并上抛(供父立即持久化或积累)
 *   - onSave(draft, nextStatus): 显式保存(create 用),nextStatus 决定草稿/发布
 *   - evalState / onRunEval / onOpenDiff: 侧栏(评测、版本对比)回调
 */
import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, Bot, Edit3, Info, Loader2, Play, Save, Send, Sparkles, X } from 'lucide-react';
import type { AgentEntry, DrawerPanel, EvalCase, Status } from './schema';
import { DrawerSidebar } from './components/DrawerSidebar';
import {
  DrawerPanelBasic, DrawerPanelEvaluation, DrawerPanelFlow, DrawerPanelKnowledge,
  DrawerPanelMemory, DrawerPanelPermission, DrawerPanelPrompt, DrawerPanelSkills, DrawerPanelVersions,
} from './components/DrawerPanels';
import { statusBadge, toneClass } from './components/constants';
import { useAuthStore } from '@/features/auth';

type Mode = 'create' | 'edit' | 'view';

export interface AgentEditorProps {
  mode: Mode;
  initialDraft: AgentEntry;
  onChange?: (patch: Partial<AgentEntry>) => void;
  onSave?: (draft: AgentEntry, nextStatus: Status) => void;
  onCancel?: () => void;
  evalState?: { isRunning: boolean; progress?: number; lastResult?: EvalCase[] };
  onRunEval?: () => void;
  onOpenDiff?: () => void;
}

const REQUIRED_PANELS: ReadonlyArray<DrawerPanel> = ['basic', 'skills'];
const RECOMMENDED_PANELS: ReadonlyArray<DrawerPanel> = ['knowledge', 'prompt', 'flow'];
const OPTIONAL_PANELS: ReadonlyArray<DrawerPanel> = ['memory', 'versions', 'evaluation', 'permission'];

interface Validation {
  errors: Partial<Record<DrawerPanel, string>>;
  canPublish: boolean;
  isValid: boolean;
}

function validate(draft: AgentEntry): Validation {
  const errors: Partial<Record<DrawerPanel, string>> = {};
  if (!draft.name?.trim() || !draft.owner?.trim() || !draft.category?.trim()) {
    errors.basic = '名称 / 负责人 / 场景分类必填';
  }
  if (!draft.tools || draft.tools.length === 0) {
    errors.skills = '至少 1 个能力';
  }
  const requiredHasError = REQUIRED_PANELS.some((p) => errors[p]);
  return {
    errors,
    canPublish: !requiredHasError,
    isValid: !requiredHasError,
  };
}

export function AgentEditor({
  mode,
  initialDraft,
  onChange,
  onSave,
  onCancel,
  evalState,
  onRunEval,
  onOpenDiff,
}: AgentEditorProps) {
  const [draft, setDraft] = useState<AgentEntry>(initialDraft);
  const [panel, setPanel] = useState<DrawerPanel>('basic');
  const [promptDoc, setPromptDoc] = useState<string>('prompt');
  const [dryRunOpen, setDryRunOpen] = useState(false);

  // 当父传入的 initialDraft 变化(create 模式初次填充 / edit 模式远端刷新)时同步
  useEffect(() => {
    setDraft(initialDraft);
  }, [initialDraft]);

  const validation = useMemo(() => validate(draft), [draft]);
  const isReadonly = mode === 'view';
  const badge = statusBadge[draft.status];

  const patch = (next: Partial<AgentEntry>) => {
    setDraft((d) => ({ ...d, ...next }));
    onChange?.(next);
  };

  const firstSkill = draft.tools?.[0];

  return (
    <div className="space-y-4">
      {/* 顶部 action bar */}
      <ActionBar
        mode={mode}
        draft={draft}
        validation={validation}
        onCancel={onCancel}
        onSave={(status) => onSave?.(draft, status)}
        onDryRun={firstSkill ? () => setDryRunOpen((v) => !v) : undefined}
        dryRunOpen={dryRunOpen}
      />

      {/* create 模式额外 onboarding 提示 */}
      {mode === 'create' && <OnboardingBanner validation={validation} />}

      <section className="flex min-h-[480px] flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] lg:flex-row">
        <DrawerSidebar panel={panel} setPanel={setPanel} validation={validation} />
        <main
          className={
            isReadonly
              ? 'min-w-0 flex-1 overflow-auto bg-[var(--bg-app] p-5 [&_button:not([data-view])]:pointer-events-none [&_input]:pointer-events-none [&_select]:pointer-events-none [&_textarea]:pointer-events-none [&_[role=switch]]:pointer-events-none'
              : 'min-w-0 flex-1 overflow-auto bg-[var(--bg-app] p-5'
          }
        >
          <div className="mb-5 flex items-center justify-between gap-3 border-b border-[var(--border)] pb-4">
            <div className="flex min-w-0 items-center gap-3">
              <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${toneClass[draft.tone]}`}>
                <Bot className="h-5 w-5" />
              </span>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-sm font-semibold">{draft.name || '未命名智能体'}</h2>
                  <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${badge.className}`}>
                    <span className={`h-1.5 w-1.5 rounded-full ${badge.dot}`} />
                    {badge.label}
                  </span>
                  <span className="rounded-md bg-[var(--bg-elevated)] px-2 py-0.5 font-mono text-[11px] text-[var(--text-muted)]">{draft.version}</span>
                </div>
                <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">{draft.category || '未分类'} · {draft.owner || '未指派'}</p>
              </div>
            </div>
          </div>
          {renderPanel({
            mode, draft, panel, promptDoc, setPromptDoc, patch,
            evalState, onRunEval, onOpenDiff,
          })}
        </main>
      </section>

      {/* 底部 footer */}
      <footer className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-[var(--text-muted)]">
        <span>
          {mode === 'view'
            ? '当前为只读查看。'
            : mode === 'create'
              ? '创建后落「草稿」状态,可在编辑态继续完善并发布。'
              : '变更后自动暂存,可在「版本」面板提交审核。'}
        </span>
        <span>{draft.versions?.length ?? 0} 个版本 · 最近更新 {draft.lastUpdate}</span>
      </footer>

      {/* 试运行面板 — mode=edit 且有 skills 时可用 */}
      {dryRunOpen && firstSkill && (
        <DryRunPanel skill={firstSkill} workspaceId={undefined} onClose={() => setDryRunOpen(false)} />
      )}
    </div>
  );
}

interface ActionBarProps {
  mode: Mode;
  draft: AgentEntry;
  validation: Validation;
  onCancel?: () => void;
  onSave: (status: Status) => void;
  onDryRun?: () => void;
  dryRunOpen?: boolean;
}

function ActionBar({ mode, draft, validation, onCancel, onSave, onDryRun, dryRunOpen }: ActionBarProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] px-4 py-3">
      <div className="flex items-center gap-2 text-xs">
        <Sparkles className="h-3.5 w-3.5 text-[var(--brand)]" />
        <span className="text-[var(--text-secondary)]">
          {mode === 'create' && '新建智能体 · 必填:基础信息、至少 1 个能力'}
          {mode === 'edit' && `编辑 · ${draft.name || '未命名'} · 变更自动暂存`}
          {mode === 'view' && `查看 · ${draft.name || '未命名'}`}
        </span>
      </div>
      <div className="flex items-center gap-2">
        {onDryRun && (
          <button
            type="button"
            onClick={onDryRun}
            aria-pressed={dryRunOpen}
            className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition ${
              dryRunOpen
                ? 'border-[var(--brand)] bg-[var(--brand-light)] text-[var(--brand)]'
                : 'border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]'
            }`}
          >
            <Play className="h-3.5 w-3.5" />试运行
          </button>
        )}
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs font-semibold text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]"
          >
            <ArrowLeft className="h-3.5 w-3.5" />返回
          </button>
        )}
        {mode === 'create' && (
          <>
            <button
              type="button"
              onClick={() => onSave('draft')}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-3 py-1.5 text-xs font-semibold text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]"
            >
              <Save className="h-3.5 w-3.5" />保存草稿
            </button>
            <button
              type="button"
              onClick={() => onSave('published')}
              disabled={!validation.canPublish}
              className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 py-1.5 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Send className="h-3.5 w-3.5" />发布
            </button>
          </>
        )}
        {mode === 'view' && (
          <span className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--brand)] bg-[var(--brand-light)] px-3 py-1.5 text-xs font-semibold text-[var(--brand)]">
            <Edit3 className="h-3.5 w-3.5" />只读模式
          </span>
        )}
      </div>
    </div>
  );
}

function OnboardingBanner({ validation }: { validation: Validation }) {
  const requiredOk = REQUIRED_PANELS.every((p) => !validation.errors[p]);
  return (
    <div className="flex items-start gap-2 rounded-2xl border border-[var(--brand)] bg-[var(--brand-light)] px-4 py-2.5 text-[11px] text-[var(--text-secondary)]">
      <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--brand)]" />
      <span>
        必填:基础信息 · 至少 1 个能力
        {' · '}
        推荐:Prompt / 知识库 / 工作流
        {' · '}
        可选:记忆 / 版本 / 评测 / 权限
        {requiredOk ? ' · 可发布' : ' · 仍有必填项未填'}
      </span>
    </div>
  );
}

interface RenderArgs {
  mode: Mode;
  draft: AgentEntry;
  panel: DrawerPanel;
  promptDoc: string;
  setPromptDoc: (v: string) => void;
  patch: (next: Partial<AgentEntry>) => void;
  evalState?: { isRunning: boolean; progress?: number; lastResult?: EvalCase[] };
  onRunEval?: () => void;
  onOpenDiff?: () => void;
}

function renderPanel(args: RenderArgs) {
  const { mode, draft, panel, promptDoc, setPromptDoc, patch, evalState, onRunEval, onOpenDiff } = args;
  switch (panel) {
    case 'basic':
      return <DrawerPanelBasic draft={draft} onChange={patch} />;
    case 'prompt':
      return (
        <DrawerPanelPrompt
          draft={draft}
          promptDoc={promptDoc}
          setPromptDoc={setPromptDoc}
          onChange={(p) => patch({ prompts: { ...draft.prompts, ...p } })}
          onChangeCustom={(custom) => patch({ customPrompts: custom })}
        />
      );
    case 'skills':
      return <DrawerPanelSkills draft={draft} onChange={patch} />;
    case 'knowledge':
      return <DrawerPanelKnowledge draft={draft} onChange={(refs) => patch({ knowledgeRefs: refs })} />;
    case 'memory':
      return <DrawerPanelMemory draft={draft} onChange={(memoryPolicy) => patch({ memoryPolicy })} />;
    case 'flow':
      return <DrawerPanelFlow draft={draft} onChange={(refs) => patch({ flowRefs: refs })} />;
    case 'versions':
      return <DrawerPanelVersions draft={draft} onOpenDiff={onOpenDiff} />;
    case 'evaluation':
      return (
        <DrawerPanelEvaluation
          draft={draft}
          isRunning={evalState?.isRunning ?? false}
          progress={evalState?.progress}
          lastResult={evalState?.lastResult}
          onRunEval={onRunEval}
        />
      );
    case 'permission':
      return <DrawerPanelPermission draft={draft} />;
    default:
      return null;
  }
}

export type { Validation, Mode };
export { REQUIRED_PANELS, RECOMMENDED_PANELS, OPTIONAL_PANELS };

// ─── 试运行面板(dev-only) ────────────────────────────────────────────────

interface DryRunSkillResult {
  ok?: boolean;
  status?: string;
  exit_code?: number | null;
  stdout?: string;
  stderr?: string;
  latency_ms?: number;
  error_code?: string | null;
  error_message?: string;
  call_id?: string;
}

function DryRunPanel({
  skill,
  workspaceId,
  onClose,
}: {
  skill: { id: string; name: string; type: string };
  workspaceId?: string;
  onClose: () => void;
}) {
  const [argsText, setArgsText] = useState('{\n  "document": "今天讨论了 Q4 路线图,重点包括新功能发布计划、人员招聘和预算分配。会议决定:Q4 上线 3 个核心功能,招聘 2 名工程师,预算增加 15%。下周一前提交详细计划。"\n}');
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<DryRunSkillResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setRunning(true);
    setError(null);
    setResult(null);
    let args: Record<string, unknown> = {};
    try {
      args = JSON.parse(argsText) as Record<string, unknown>;
    } catch (e) {
      setError(`参数 JSON 解析失败: ${(e as Error).message}`);
      setRunning(false);
      return;
    }
    const token = useAuthStore.getState().token ?? '';
    const tenant = useAuthStore.getState().user?.tenantId ?? '';
    try {
      const resp = await fetch(`/api/dev/skills/${encodeURIComponent(skill.name)}/invoke`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          'X-Tenant-Id': tenant,
          ...(workspaceId ? { 'X-Workspace-Id': workspaceId } : {}),
        },
        body: JSON.stringify({ arguments: args, confirmed: true }),
      });
      const data = await resp.json() as DryRunSkillResult;
      setResult(data);
      if (!resp.ok) setError(`HTTP ${resp.status}`);
    } catch (e) {
      setError(`请求失败: ${(e as Error).message}`);
    } finally {
      setRunning(false);
    }
  };

  return (
    <section className="rounded-2xl border border-[var(--brand)] bg-[var(--surface-1)] p-5">
      <header className="mb-3 flex items-center justify-between">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--brand)]">dev-only 试运行</p>
          <h3 className="mt-0.5 text-sm font-semibold">直接调用 {skill.name}(跳过 LLM,直跑沙箱)</h3>
          <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">后端 dev API 需 QZDAP_ALLOW_DEV_API=1;workspace / tenant 从本地 storage 读。</p>
        </div>
        <button type="button" onClick={onClose} aria-label="关闭" className="grid h-7 w-7 place-items-center rounded-md text-[var(--text-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--text)]">
          <X className="h-4 w-4" />
        </button>
      </header>
      <div className="grid gap-3 md:grid-cols-2">
        <div>
          <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">参数 arguments (JSON)</label>
          <textarea
            value={argsText}
            onChange={(e) => setArgsText(e.target.value)}
            rows={10}
            spellCheck={false}
            className="mt-1.5 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] p-2.5 font-mono text-[11px] leading-5 outline-none focus:border-[var(--brand)]"
          />
          <button
            type="button"
            onClick={run}
            disabled={running}
            className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 py-1.5 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            {running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
            {running ? '运行中…' : '运行'}
          </button>
        </div>
        <div>
          <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">结果</label>
          {error && <p className="mt-1.5 rounded-lg border border-rose-200 bg-rose-50 p-2.5 text-[11px] text-rose-700">{error}</p>}
          {result && (
            <div className="mt-1.5 space-y-2">
              <div className="flex flex-wrap gap-2 text-[10px]">
                <span className={`rounded-full px-2 py-0.5 font-semibold ${result.status === 'succeeded' ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'}`}>
                  {result.status ?? result.error_code ?? 'unknown'}
                </span>
                {typeof result.latency_ms === 'number' && <span className="rounded-full bg-[var(--bg-elevated)] px-2 py-0.5 text-[var(--text-muted)]">{result.latency_ms} ms</span>}
                {typeof result.exit_code === 'number' && <span className="rounded-full bg-[var(--bg-elevated)] px-2 py-0.5 text-[var(--text-muted)]">exit {result.exit_code}</span>}
              </div>
              {result.stdout && (
                <pre className="max-h-60 overflow-auto whitespace-pre-wrap break-all rounded-lg border border-[var(--border)] bg-[var(--surface-1)] p-2.5 font-mono text-[10px] leading-5 text-[var(--text)]">
                  {result.stdout}
                </pre>
              )}
              {result.stderr && (
                <pre className="max-h-32 overflow-auto whitespace-pre-wrap break-all rounded-lg border border-rose-200 bg-rose-50 p-2.5 font-mono text-[10px] leading-5 text-rose-700">
                  {result.stderr}
                </pre>
              )}
            </div>
          )}
          {!error && !result && (
            <p className="mt-1.5 rounded-lg border border-dashed border-[var(--border)] bg-[var(--bg-app)] p-3 text-center text-[11px] text-[var(--text-muted)]">
              填好参数 → 点「运行」→ 沙箱 stdout / stderr 会显示在这里。
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
