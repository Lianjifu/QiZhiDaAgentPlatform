/**
 * MessageExtrasView — 工具/技能/知识/工作流调用块, 嵌入 assistant message 流.
 * 不带业务逻辑, 纯展示. 数据由 CopilotPage 在 SSE 流式阶段累积后传入.
 */
import { Sparkles, Wrench, BookOpen, Workflow, CheckCircle2, AlertTriangle, Loader2 } from 'lucide-react';
import { useState } from 'react';

export type ToolCallState = {
  id: string;
  tool_name: string;
  status: 'running' | 'succeeded' | 'failed';
  arguments?: Record<string, unknown>;
  output?: string;
  latency_ms?: number;
};

export type SkillInvocationState = {
  id: string;
  skill_name: string;
  status: 'started' | 'stream' | 'succeeded' | 'failed' | 'cancelled';
};

export type KnowledgeHit = {
  id: string;
  title: string;
  snippet: string;
  score: number;
};

export type WorkflowRun = {
  id: string;
  workflow_name: string;
  status: 'started' | 'succeeded' | 'failed' | 'cancelled';
};

export type MessageExtras = {
  toolCalls?: ToolCallState[];
  skillInvocations?: SkillInvocationState[];
  knowledgeHits?: { query: string; hits: KnowledgeHit[]; degraded?: boolean };
  workflowRuns?: WorkflowRun[];
};

function StatusDot({ status }: { status: string }) {
  if (status === 'running' || status === 'started' || status === 'stream') {
    return <Loader2 className="h-3 w-3 animate-spin text-[var(--brand)]" />;
  }
  if (status === 'succeeded') return <CheckCircle2 className="h-3 w-3 text-emerald-500" />;
  if (status === 'failed') return <AlertTriangle className="h-3 w-3 text-rose-500" />;
  return <span className="h-2 w-2 rounded-full bg-slate-300" />;
}

function Chip({ icon: Icon, label, status }: { icon: typeof Wrench; label: string; status: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md border border-[var(--border)] bg-[var(--surface-1)] px-2 py-1 text-[11px] text-[var(--text-secondary)]">
      <Icon className="h-3 w-3 text-[var(--text-muted)]" />
      <span className="font-medium">{label}</span>
      <StatusDot status={status} />
    </span>
  );
}

function ToolCallRow({ tc }: { tc: ToolCallState }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-md border border-[var(--border)] bg-[var(--surface-1)]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-2.5 py-1.5 text-left"
      >
        <span className="inline-flex items-center gap-2 text-[11px]">
          <Wrench className="h-3 w-3 text-[var(--text-muted)]" />
          <span className="font-mono text-[var(--text)]">{tc.tool_name}</span>
          {tc.latency_ms != null ? (
            <span className="text-[var(--text-muted)]">{tc.latency_ms}ms</span>
          ) : null}
        </span>
        <StatusDot status={tc.status} />
      </button>
      {open ? (
        <div className="space-y-2 border-t border-[var(--border)] bg-[var(--bg-elevated)] px-2.5 py-2 text-[10px] leading-5 text-[var(--text-secondary)]">
          {tc.arguments && Object.keys(tc.arguments).length > 0 ? (
            <div>
              <p className="mb-1 font-semibold text-[var(--text-muted)]">arguments</p>
              <pre className="overflow-auto rounded bg-[var(--surface-1)] p-1.5 font-mono text-[10px]">
                {JSON.stringify(tc.arguments, null, 2)}
              </pre>
            </div>
          ) : null}
          {tc.output ? (
            <div>
              <p className="mb-1 font-semibold text-[var(--text-muted)]">output</p>
              <pre className="overflow-auto rounded bg-[var(--surface-1)] p-1.5 font-mono text-[10px]">
                {tc.output}
              </pre>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function MessageExtrasView({ extras }: { extras: MessageExtras }) {
  const hasContent =
    (extras.toolCalls?.length ?? 0) +
      (extras.skillInvocations?.length ?? 0) +
      (extras.workflowRuns?.length ?? 0) +
      (extras.knowledgeHits?.hits.length ?? 0) >
    0;
  if (!hasContent) return null;

  return (
    <div className="space-y-2.5 border-t border-[var(--border)] pt-3 text-[11px]">
      {extras.toolCalls && extras.toolCalls.length > 0 ? (
        <div className="space-y-1.5">
          <p className="font-semibold text-[var(--text-muted)]">
            工具调用 · {extras.toolCalls.length}
          </p>
          <div className="space-y-1">
            {extras.toolCalls.map((tc) => (
              <ToolCallRow key={tc.id} tc={tc} />
            ))}
          </div>
        </div>
      ) : null}

      {extras.skillInvocations && extras.skillInvocations.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="font-semibold text-[var(--text-muted)]">技能:</span>
          {extras.skillInvocations.map((s) => (
            <Chip key={s.id} icon={Sparkles} label={s.skill_name} status={s.status} />
          ))}
        </div>
      ) : null}

      {extras.workflowRuns && extras.workflowRuns.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="font-semibold text-[var(--text-muted)]">工作流:</span>
          {extras.workflowRuns.map((w) => (
            <Chip key={w.id} icon={Workflow} label={w.workflow_name} status={w.status} />
          ))}
        </div>
      ) : null}

      {extras.knowledgeHits && extras.knowledgeHits.hits.length > 0 ? (
        <div className="rounded-md border border-[var(--border)] bg-[var(--surface-1)] p-2">
          <div className="mb-1.5 flex items-center justify-between">
            <span className="inline-flex items-center gap-1.5 font-semibold text-[var(--text-muted)]">
              <BookOpen className="h-3 w-3" />
              知识检索 · {extras.knowledgeHits.hits.length} 条命中
            </span>
            {extras.knowledgeHits.degraded ? (
              <span className="text-[10px] text-amber-600">降级</span>
            ) : null}
          </div>
          <ul className="space-y-1">
            {extras.knowledgeHits.hits.map((h) => (
              <li key={h.id} className="flex items-start gap-2 text-[11px]">
                <span className="mt-0.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--brand)]" />
                <span className="flex-1">
                  <span className="font-medium text-[var(--text)]">{h.title}</span>
                  <span className="ml-1.5 text-[10px] text-[var(--text-muted)]">
                    相似度 {(h.score * 100).toFixed(0)}%
                  </span>
                  {h.snippet ? (
                    <span className="mt-0.5 block text-[10px] leading-4 text-[var(--text-muted)]">
                      {h.snippet}
                    </span>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
