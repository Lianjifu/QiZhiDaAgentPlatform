/**
 * FilterModal — 状态 / 智能体 / 异常级别 三联筛选。
 */
import { useEffect, useState } from 'react';
import { Filter } from 'lucide-react';
import { CenterModal } from '@/components/feedback/CenterModal';

export interface FilterSelection {
  status: string;
  agent: string;
  severity: string;
}

export function FilterModal({
  open,
  onClose,
  onApply,
  agents,
}: {
  open: boolean;
  onClose: () => void;
  onApply: (f: FilterSelection) => void;
  agents: string[];
}) {
  const [status, setStatus] = useState('all');
  const [agent, setAgent] = useState('all');
  const [severity, setSeverity] = useState('all');
  useEffect(() => {
    if (open) {
      setStatus('all');
      setAgent('all');
      setSeverity('all');
    }
  }, [open]);
  return (
    <CenterModal
      open={open}
      onClose={onClose}
      ariaLabel="筛选调用链路"
      panelClassName="max-w-md"
      title={
        <span className="flex items-center gap-2">
          <Filter className="h-5 w-5 text-[var(--brand)]" />
          筛选调用链路
        </span>
      }
      description="按状态、智能体与异常级别筛选"
      footer={
        <>
          <button type="button" onClick={onClose} className="rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold">
            取消
          </button>
          <button
            type="button"
            onClick={() => {
              onApply({ status, agent, severity });
              onClose();
            }}
            className="rounded-xl bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white"
          >
            应用筛选
          </button>
        </>
      }
    >
      <div className="mt-4 grid gap-3">
        <div>
          <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">状态</label>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]"
          >
            <option value="all">全部</option>
            <option value="success">完成</option>
            <option value="running">执行中</option>
            <option value="partial">部分成功</option>
            <option value="failed">失败</option>
          </select>
        </div>
        <div>
          <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">智能体</label>
          <select
            value={agent}
            onChange={(e) => setAgent(e.target.value)}
            className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]"
          >
            <option value="all">全部</option>
            {agents.map((name) => <option key={name} value={name}>{name}</option>)}
          </select>
        </div>
        <div>
          <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">异常级别</label>
          <select
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
            className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]"
          >
            <option value="all">全部</option>
            <option value="critical">严重</option>
            <option value="error">错误</option>
            <option value="warning">警告</option>
            <option value="info">信息</option>
          </select>
        </div>
      </div>
    </CenterModal>
  );
}
