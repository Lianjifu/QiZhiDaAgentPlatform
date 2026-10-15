/**
 * PlanProposalCard — 模型提议的执行计划.
 * 视觉走对话叙述流: 头部一句"我打算这样做", 步骤用自然段表达 (不编号 +
 * 不摆工具图标), 底部 "好, 继续" / "调整一下" / "算了" 三个对话化按钮.
 * 批准/拒绝调 POST /api/sessions/{sid}/plans/{pid}/{approve,deny}.
 */
import { Check, PencilLine, X } from 'lucide-react';
import { useState, type ReactNode } from 'react';
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

const KIND_VERB: Record<PlanStep['kind'], string> = {
  ask: '先跟你确认',
  subagent: '交给一个子智能体',
  tool: '用工具',
};

const KIND_DONE: Record<PlanStep['kind'], string> = {
  ask: '把信息对齐',
  subagent: '把子任务做完',
  tool: '拿到结果',
};

function describeStep(step: PlanStep, index: number, total: number): ReactNode {
  const isLast = index === total - 1;
  const verb = KIND_VERB[step.kind];
  const done = KIND_DONE[step.kind];
  const toolLabel = step.tool_name ? (
    <code className="rounded bg-[var(--bg-elevated)] px-1.5 py-0.5 font-mono text-[11px] text-[var(--text-secondary)]">
      {step.tool_name}
    </code>
  ) : null;
  return (
    <span>
      {index === 0 ? '先' : isLast ? '最后' : '接着'}{verb}
      {toolLabel ? <> <span>「</span>{toolLabel}<span>」</span></> : null}
      {step.title ? <span>处理「{step.title}」</span> : null}
      {step.description ? <span className="text-[var(--text-muted)]"> — {step.description}</span> : null}
      <span>, {done}</span>
      {!isLast ? <span>; </span> : <span>。</span>}
    </span>
  );
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

  const total = proposal.steps.length;
  const isPending = state === 'pending' || state === 'submitting';

  return (
    <div className="my-3 overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
      {/* 头部: 一句开场, 弱化版块感, 跟普通 message 接近 */}
      <div className="flex items-baseline justify-between gap-3 px-4 pt-3 pb-1.5">
        <p className="text-[13px] leading-6 text-[var(--text-secondary)]">
          <span className="text-[var(--text)]">我打算这样做, 大概分 {total} 步:</span>
        </p>
        {isPending ? (
          <span className="shrink-0 text-[10px] text-[var(--text-muted)]">等你拍板</span>
        ) : state === 'approved' ? (
          <span className="shrink-0 text-[10px] text-emerald-600">已批准</span>
        ) : (
          <span className="shrink-0 text-[10px] text-[var(--text-muted)]">已忽略</span>
        )}
      </div>

      {/* 副标题 (原 reason) — 可选, 轻量 */}
      {proposal.reason ? (
        <p className="px-4 pb-1.5 text-[11px] text-[var(--text-muted)]">{proposal.reason}</p>
      ) : null}

      {/* 步骤叙述: 一段连写, 不用列表/编号/图标 */}
      <div className="px-4 pb-3 pt-1 text-[13px] leading-7 text-[var(--text-secondary)]">
        {proposal.steps.map((step, idx) => (
          <span key={step.id}>{describeStep(step, idx, total)}</span>
        ))}
      </div>

      {/* 按钮: 三个对话化文案, 居中排, 不放工具图标 */}
      {isPending ? (
        <div className="flex items-center justify-center gap-2 border-t border-[var(--border)] bg-[var(--bg-elevated)]/40 px-4 py-3">
          <button
            type="button"
            onClick={() => void submit('approve')}
            disabled={state === 'submitting'}
            className="inline-flex items-center gap-1 rounded-full bg-[var(--brand)] px-4 py-1.5 text-[12px] font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            <Check className="h-3.5 w-3.5" />
            好, 继续
          </button>
          <button
            type="button"
            disabled
            title="逐项编辑下一轮提供"
            className="inline-flex items-center gap-1 rounded-full border border-[var(--border)] px-3 py-1.5 text-[12px] text-[var(--text-muted)]"
          >
            <PencilLine className="h-3.5 w-3.5" />
            调整一下
          </button>
          <button
            type="button"
            onClick={() => void submit('deny')}
            disabled={state === 'submitting'}
            className="inline-flex items-center gap-1 rounded-full px-3 py-1.5 text-[12px] text-[var(--text-muted)] hover:text-rose-600 disabled:opacity-50"
          >
            <X className="h-3.5 w-3.5" />
            算了
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
