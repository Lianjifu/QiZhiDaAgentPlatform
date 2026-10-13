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
import { ArrowLeft, Bot, Edit3, Info, Save, Send, Sparkles } from 'lucide-react';
import type { AgentEntry, DrawerPanel, EvalCase, Status } from './schema';
import { DrawerSidebar } from './components/DrawerSidebar';
import {
  DrawerPanelBasic, DrawerPanelEvaluation, DrawerPanelFlow, DrawerPanelKnowledge,
  DrawerPanelMemory, DrawerPanelPermission, DrawerPanelPrompt, DrawerPanelSkills, DrawerPanelVersions,
} from './components/DrawerPanels';
import { statusBadge, toneClass } from './components/constants';

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

  return (
    <div className="space-y-4">
      {/* 顶部 action bar */}
      <ActionBar
        mode={mode}
        draft={draft}
        validation={validation}
        onCancel={onCancel}
        onSave={(status) => onSave?.(draft, status)}
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
    </div>
  );
}

interface ActionBarProps {
  mode: Mode;
  draft: AgentEntry;
  validation: Validation;
  onCancel?: () => void;
  onSave: (status: Status) => void;
}

function ActionBar({ mode, draft, validation, onCancel, onSave }: ActionBarProps) {
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
