/**
 * PlanProposalCard — 模型提议的计划列表.
 * 用户可整体批准/拒绝; 逐项编辑留待下一轮. 批准/拒绝调
 * POST /api/sessions/{sid}/plans/{pid}/{approve,deny}.
 */
import { Bot, Check, HelpCircle, ListChecks, X, Wrench, UserCircle2 } from 'lucide-react';
import { useState } from 'react';
import { getApiClient } from '@qzdap/web-api';

export type PlanStep = {
  id: string;
  title: string;
  description?: string;
  kind: 'tool' | 'subagent' | 'ask';
  tool_name?: string;
};

export type PlanProposal = {
  plan_id: string;
  title: string;
  steps: PlanStep[];
  reason?: string;
};

function StepIcon({ kind }: { kind: PlanStep['kind'] }) {
  if (kind === 'tool') return <Wrench className="h-3.5 w-3.5 text-[var(--brand)]" />;
  if (kind === 'subagent') return <Bot className="h-3.5 w-3.5 text-[var(--brand)]" />;
  return <HelpCircle className="h-3.5 w-3.5 text-amber-600" />;
}

export function PlanProposalCard({
  proposal,
  sessionId,
}: {
  proposal: PlanProposal;
  sessionId: string;
}) {
  const [state, setState] = useState<'pending' | 'approved' | 'denied' | 'submitting'>('pending');
  const [error, setError] = useState<string>('');

  const submit = async (decision: 'approve' | 'deny') => {
    setState('submitting');
    setError('');
    try {
      await getApiClient().post(
        `/api/sessions/${sessionId}/plans/${proposal.plan_id}/${decision}`,
        {},
      );
      setState(decision === 'approve' ? 'approved' : 'denied');
    } catch (e) {
      setError(String(e));
      setState('pending');
    }
  };

  return (
    <div className="my-3 overflow-hidden rounded-xl border border-[var(--brand)]/30 bg-[var(--brand-light)]/30">
      <div className="flex items-start justify-between gap-3 border-b border-[var(--brand)]/15 bg-[var(--brand-light)]/50 px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--brand)]">
            <ListChecks className="h-3 w-3" />
            待你确认的计划
          </div>
          <h4 className="mt-0.5 text-sm font-semibold text-[var(--text)]">{proposal.title}</h4>
          {proposal.reason ? (
            <p className="mt-1 text-[11px] text-[var(--text-muted)]">{proposal.reason}</p>
          ) : null}
        </div>
        {state === 'pending' || state === 'submitting' ? (
          <span className="shrink-0 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-800">
            {state === 'submitting' ? '提交中…' : '待确认'}
          </span>
        ) : state === 'approved' ? (
          <span className="shrink-0 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-medium text-emerald-800">
            已批准
          </span>
        ) : (
          <span className="shrink-0 rounded-full bg-slate-200 px-2 py-0.5 text-[10px] font-medium text-slate-700">
            已拒绝
          </span>
        )}
      </div>

      <ol className="space-y-1 px-4 py-3 text-xs">
        {proposal.steps.map((step, idx) => (
          <li
            key={step.id}
            className="flex items-start gap-2.5 rounded-md border border-transparent px-2 py-1.5 hover:border-[var(--border)] hover:bg-[var(--surface-1)]"
          >
            <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full border border-[var(--border)] bg-[var(--bg-elevated)] text-[10px] font-semibold text-[var(--text-secondary)]">
              {idx + 1}
            </span>
            <StepIcon kind={step.kind} />
            <div className="min-w-0 flex-1">
              <p className="font-medium text-[var(--text)]">{step.title}</p>
              {step.description ? (
                <p className="mt-0.5 text-[10px] leading-4 text-[var(--text-muted)]">
                  {step.description}
                </p>
              ) : null}
              {step.tool_name ? (
                <span className="mt-0.5 inline-flex items-center gap-1 rounded bg-[var(--bg-elevated)] px-1.5 py-0.5 font-mono text-[9px] text-[var(--text-muted)]">
                  tool: {step.tool_name}
                </span>
              ) : null}
            </div>
          </li>
        ))}
      </ol>

      {state === 'pending' || state === 'submitting' ? (
        <div className="flex items-center gap-2 border-t border-[var(--brand)]/15 bg-[var(--surface-1)] px-4 py-3">
          <button
            type="button"
            onClick={() => void submit('approve')}
            disabled={state === 'submitting'}
            className="inline-flex items-center gap-1.5 rounded-md bg-[var(--brand)] px-3 py-1.5 text-[11px] font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            <Check className="h-3 w-3" />
            全部批准
          </button>
          <button
            type="button"
            disabled
            className="inline-flex items-center gap-1.5 rounded-md border border-[var(--border)] px-3 py-1.5 text-[11px] font-medium text-[var(--text-muted)]"
            title="逐项编辑下一轮提供"
          >
            <UserCircle2 className="h-3 w-3" />
            逐项编辑
          </button>
          <button
            type="button"
            onClick={() => void submit('deny')}
            disabled={state === 'submitting'}
            className="ml-auto inline-flex items-center gap-1.5 rounded-md border border-[var(--border)] px-3 py-1.5 text-[11px] font-medium text-[var(--text-secondary)] hover:border-rose-300 hover:text-rose-600 disabled:opacity-50"
          >
            <X className="h-3 w-3" />
            拒绝
          </button>
        </div>
      ) : null}

      {error ? (
        <p className="border-t border-rose-200 bg-rose-50 px-4 py-2 text-[10px] text-rose-700">
          {error}
        </p>
      ) : null}
    </div>
  );
}
