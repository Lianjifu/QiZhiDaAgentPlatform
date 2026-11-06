/**
 * 登记告警 —— 写进概览的告警集合（POST /api/admin/overview/alerts ✓）。
 * 概览的告警 = 管理员登记的告警 + 异常事件 + 额度告警（后端合并 ✓）。
 */
import { useState, type FormEvent } from 'react';
import { CenterModal } from '@/components/feedback/CenterModal';
import type { CreateOverviewAlertVars } from '../useOverview';

const SEVERITY_OPTIONS: { value: CreateOverviewAlertVars['severity']; label: string }[] = [
  { value: 'high', label: '高' },
  { value: 'medium', label: '中' },
  { value: 'low', label: '低' },
  { value: 'info', label: '提示' },
];

export interface AlertCreateModalProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (vars: CreateOverviewAlertVars) => void;
  submitting?: boolean;
}

export function AlertCreateModal({ open, onClose, onSubmit, submitting }: AlertCreateModalProps) {
  const [severity, setSeverity] = useState<CreateOverviewAlertVars['severity']>('medium');
  const [title, setTitle] = useState('');
  const [affected, setAffected] = useState('');
  const [suggestion, setSuggestion] = useState('');

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!title.trim()) return;
    onSubmit({
      severity,
      title: title.trim(),
      affected: affected.trim() || '工作空间',
      suggestion: suggestion.trim(),
    });
  };

  return (
    <CenterModal
      open={open}
      onClose={onClose}
      ariaLabel="登记告警"
      title="登记告警"
      description="登记一条运维告警，会出现在运营概览的「实时告警」里。"
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
            disabled={submitting || !title.trim()}
            className="rounded-lg bg-[var(--brand)] px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
          >
            {submitting ? '登记中…' : '登记'}
          </button>
        </>
      }
    >
      <div className="mt-4 space-y-3">
        <label className="block text-xs font-semibold">
          严重度
          <select
            aria-label="严重度"
            value={severity}
            onChange={(event) => setSeverity(event.target.value as CreateOverviewAlertVars['severity'])}
            className="mt-1 h-9 w-full rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 text-sm outline-none focus:border-[var(--brand)]"
          >
            {SEVERITY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-xs font-semibold">
          标题
          <input
            aria-label="标题"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="例如：模型错误率突增"
            className="mt-1 h-9 w-full rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 text-sm outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--brand)]"
          />
        </label>
        <label className="block text-xs font-semibold">
          影响范围
          <input
            aria-label="影响范围"
            value={affected}
            onChange={(event) => setAffected(event.target.value)}
            placeholder="例如：客户沟通助手"
            className="mt-1 h-9 w-full rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 text-sm outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--brand)]"
          />
        </label>
        <label className="block text-xs font-semibold">
          处理建议
          <textarea
            aria-label="处理建议"
            value={suggestion}
            onChange={(event) => setSuggestion(event.target.value)}
            rows={3}
            placeholder="例如：切换备用模型"
            className="mt-1 w-full rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 py-2 text-sm outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--brand)]"
          />
        </label>
      </div>
    </CenterModal>
  );
}
