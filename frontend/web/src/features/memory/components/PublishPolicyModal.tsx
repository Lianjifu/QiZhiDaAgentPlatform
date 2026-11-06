/**
 * 发布记忆策略 —— 把策略配置写进绑定这个 label 的 Agent ✓
 * （``POST /api/admin/memory/policies/{label}/publish`` ✓ → 运行时**立刻生效** ✓）。
 *
 * ⚠️ **作用域不能选「工作区」** ✓ —— 后端明确拒绝 ✓（L3 退役 ✓）。
 */
import { useState, type FormEvent } from 'react';
import { CenterModal } from '@/components/feedback/CenterModal';

export interface PublishPolicyVars {
  enabled: boolean;
  scope: 'user' | 'tenant';
  retentionDays: number;
  autoSummarize: boolean;
}

export interface PublishPolicyModalProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (vars: PublishPolicyVars) => void;
  submitting?: boolean;
  /** 绑定了这个策略的 Agent 数量 ✓ */
  boundCount: number;
  /** 默认保留天数 ✓（从策略的 ttlMinutes 推 ✓） */
  defaultRetentionDays: number;
}

export function PublishPolicyModal({
  open,
  onClose,
  onSubmit,
  submitting,
  boundCount,
  defaultRetentionDays,
}: PublishPolicyModalProps) {
  const [enabled, setEnabled] = useState(true);
  const [scope, setScope] = useState<'user' | 'tenant'>('user');
  const [retentionDays, setRetentionDays] = useState(defaultRetentionDays);
  const [autoSummarize, setAutoSummarize] = useState(false);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmit({ enabled, scope, retentionDays, autoSummarize });
  };

  return (
    <CenterModal
      open={open}
      onClose={onClose}
      ariaLabel="发布记忆策略"
      title="发布记忆策略"
      description={`发布后写进 ${boundCount} 个绑定的 Agent，运行时下一次调用即生效。`}
      onSubmit={handleSubmit}
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-3 py-2 text-xs font-semibold text-[var(--text-muted)] hover:text-[var(--brand)]"
          >
            取消
          </button>
          <button
            type="submit"
            disabled={submitting || boundCount === 0}
            className="rounded-lg bg-[var(--brand)] px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
          >
            {submitting ? '发布中…' : '发布'}
          </button>
        </>
      }
    >
      <div className="mt-4 space-y-3">
        <label className="flex items-center gap-2 text-xs font-semibold">
          <input
            type="checkbox"
            aria-label="启用"
            checked={enabled}
            onChange={(event) => setEnabled(event.target.checked)}
            className="h-4 w-4 rounded border-[var(--border)]"
          />
          启用该策略
        </label>
        <label className="block text-xs font-semibold">
          作用域
          <select
            aria-label="作用域"
            value={scope}
            onChange={(event) => setScope(event.target.value as 'user' | 'tenant')}
            className="mt-1 h-9 w-full rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 text-sm outline-none focus:border-[var(--brand)]"
          >
            <option value="user">用户级</option>
            <option value="tenant">租户级</option>
          </select>
        </label>
        <label className="block text-xs font-semibold">
          保留天数
          <input
            aria-label="保留天数"
            type="number"
            min={1}
            value={retentionDays}
            onChange={(event) => setRetentionDays(Number(event.target.value) || 1)}
            className="mt-1 h-9 w-full rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 text-sm outline-none focus:border-[var(--brand)]"
          />
        </label>
        <label className="flex items-center gap-2 text-xs font-semibold">
          <input
            type="checkbox"
            aria-label="自动摘要"
            checked={autoSummarize}
            onChange={(event) => setAutoSummarize(event.target.checked)}
            className="h-4 w-4 rounded border-[var(--border)]"
          />
          自动摘要
        </label>
      </div>
    </CenterModal>
  );
}
