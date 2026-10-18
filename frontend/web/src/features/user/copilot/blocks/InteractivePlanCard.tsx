/**
 * InteractivePlanCard — 顶部 sticky 计划卡片.
 *
 * 当 LLM 通过 plan_submit stub tool 提交计划时, 这里渲染一个紧凑条,
 * 用户点批准 / 拒绝(可填理由), 调 onResolve 通知 store.
 * 响应后变灰, 标注用户的决定.
 */
import { useState } from 'react';
import { Check, X } from 'lucide-react';
import type { PendingPlan } from '../interactiveStore';

export function InteractivePlanCard({
  pending,
  onResolve,
}: {
  pending: PendingPlan;
  onResolve: PendingPlan['onResolve'];
}) {
  const [busy, setBusy] = useState<'approve' | 'reject' | null>(null);
  const [decided, setDecided] = useState<'approve' | 'reject' | null>(null);
  const [showReject, setShowReject] = useState(false);
  const [reason, setReason] = useState('');

  const approve = async () => {
    setBusy('approve');
    try {
      await onResolve('approve');
      setDecided('approve');
    } finally {
      setBusy(null);
    }
  };

  const reject = async () => {
    setBusy('reject');
    try {
      await onResolve('reject', reason.trim() || undefined);
      setDecided('reject');
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="border-b border-[var(--border)] bg-[var(--surface-1)] px-5 py-3">
      <header className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--brand)]">
            执行计划
          </p>
          <h3 className="mt-0.5 truncate text-sm font-semibold">{pending.title}</h3>
          {pending.reason && (
            <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">{pending.reason}</p>
          )}
        </div>
        {decided ? (
          <span
            className={`shrink-0 rounded-md px-2 py-1 text-[10px] font-semibold ${
              decided === 'approve'
                ? 'bg-emerald-100 text-emerald-700'
                : 'bg-rose-100 text-rose-700'
            }`}
          >
            已{decided === 'approve' ? '批准' : '拒绝'}
          </span>
        ) : (
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={approve}
              disabled={busy !== null}
              className="inline-flex items-center gap-1 rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
            >
              <Check className="h-3.5 w-3.5" />
              批准
            </button>
            <button
              type="button"
              onClick={() => setShowReject((v) => !v)}
              disabled={busy !== null}
              className="inline-flex items-center gap-1 rounded-md border border-[var(--border)] px-3 py-1.5 text-xs font-medium hover:bg-[var(--bg-hover)]"
            >
              <X className="h-3.5 w-3.5" />
              拒绝
            </button>
          </div>
        )}
      </header>
      {pending.steps.length > 0 && (
        <ol className="mt-2 space-y-1 text-[11px] text-[var(--text-secondary)]">
          {pending.steps.map((s, i) => (
            <li key={s.id || i} className="flex gap-2">
              <span className="shrink-0 rounded bg-[var(--bg-elevated)] px-1.5 text-[10px] tabular-nums text-[var(--text-muted)]">
                {i + 1}
              </span>
              <span className="min-w-0">{s.title}</span>
            </li>
          ))}
        </ol>
      )}
      {showReject && !decided && (
        <div className="mt-3 flex items-center gap-2">
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="拒绝理由 (可选)"
            className="h-8 flex-1 rounded-md border border-[var(--border)] bg-[var(--surface-1)] px-2 text-xs outline-none focus:border-[var(--brand)]"
          />
          <button
            type="button"
            onClick={reject}
            disabled={busy !== null}
            className="h-8 rounded-md bg-rose-600 px-3 text-xs font-semibold text-white hover:bg-rose-500 disabled:opacity-50"
          >
            确认拒绝
          </button>
        </div>
      )}
    </section>
  );
}