/**
 * RetentionPolicyModal — L1/L2/L3 保留策略编辑。
 */
import { useState } from 'react';
import { CheckCircle2, Settings, X } from 'lucide-react';
import type { RetentionPolicy } from '../schema';
import { EVICTION_LABEL } from './constants';

export function RetentionPolicyModal({ open, onClose, policy, onSave }: {
  open: boolean; onClose: () => void; policy: RetentionPolicy | null; onSave: (next: RetentionPolicy) => void;
}) {
  const [draft, setDraft] = useState<RetentionPolicy | null>(policy);
  if (!open || !policy || !draft) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/45 p-4 sm:items-center sm:p-8" role="dialog" aria-modal="true" aria-label="保留策略" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <div className="my-4 flex w-full max-w-2xl flex-col overflow-hidden rounded-2xl bg-[var(--surface-1)] shadow-2xl sm:my-0">
        <div className="flex items-center justify-between border-b border-[var(--border)] px-6 py-3">
          <div className="flex items-center gap-2 text-sm font-semibold"><Settings className="h-5 w-5 text-[var(--brand)]" />{policy.label} · 保留策略</div>
          <button type="button" onClick={onClose} aria-label="关闭" className="rounded-lg p-2 text-[var(--text-muted)] hover:bg-[var(--bg-hover)]"><X className="h-5 w-5" /></button>
        </div>
        <div className="space-y-4 overflow-y-auto px-6 py-6">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="text-xs font-semibold">TTL (分钟)</span>
              <input type="number" min={1} value={draft.ttlMinutes} onChange={(event) => setDraft({ ...draft, ttlMinutes: Number(event.target.value) })} className="mt-1 h-10 w-full rounded-xl border border-[var(--border)] bg-[var(--surface-1)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
              <p className="mt-1 text-[10px] text-[var(--text-muted)]">建议 1-180 天</p>
            </label>
            <label className="block">
              <span className="text-xs font-semibold">最大条目</span>
              <input type="number" min={1} value={draft.maxItems} onChange={(event) => setDraft({ ...draft, maxItems: Number(event.target.value) })} className="mt-1 h-10 w-full rounded-xl border border-[var(--border)] bg-[var(--surface-1)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
            </label>
            <label className="block">
              <span className="text-xs font-semibold">存储上限 (MB)</span>
              <input type="number" min={1} value={draft.storageMb} onChange={(event) => setDraft({ ...draft, storageMb: Number(event.target.value) })} className="mt-1 h-10 w-full rounded-xl border border-[var(--border)] bg-[var(--surface-1)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
            </label>
            <label className="block">
              <span className="text-xs font-semibold">淘汰策略</span>
              <select value={draft.eviction} onChange={(event) => setDraft({ ...draft, eviction: event.target.value as RetentionPolicy['eviction'] })} className="mt-1 h-10 w-full rounded-xl border border-[var(--border)] bg-[var(--surface-1)] px-3 text-sm outline-none focus:border-[var(--brand)]">
                {(['lru', 'fifo', 'confidence'] as const).map((k) => <option key={k} value={k}>{EVICTION_LABEL[k]}</option>)}
              </select>
            </label>
          </div>
          <div className="rounded-xl border border-[var(--warning)]/30 bg-[var(--warning-bg)] p-4 text-xs text-[var(--warning)]">
            <p className="font-semibold">当前命中率 · {(policy.hitRate * 100).toFixed(1)}%</p>
            <p className="mt-1">调整策略后 24 小时内重新统计,届时会推送差异报告。</p>
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-[var(--border)] px-6 py-4">
          <button type="button" onClick={onClose} className="rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold hover:border-[var(--brand)]">取消</button>
          <button type="button" onClick={() => onSave(draft)} className="inline-flex items-center gap-2 rounded-xl bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white hover:opacity-90">
            <CheckCircle2 className="h-3.5 w-3.5" />保存策略
          </button>
        </div>
      </div>
    </div>
  );
}