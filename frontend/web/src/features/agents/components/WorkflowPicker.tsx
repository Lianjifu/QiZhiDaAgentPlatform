/**
 * WorkflowPicker — 包装 ResourcePicker,接 useWorkflows。
 *
 * 用法:
 *   <WorkflowPicker selectedIds={...} onChange={ids => ...} />
 *   <WorkflowPicker selectedIds={...} onChange={...} allowedTriggers={['消息触发']} />
 */
import { useMemo } from 'react';
import { Workflow } from 'lucide-react';
import type { Flow, FlowStatus, TriggerType } from '@/features/workflows/schema';
import { useWorkflows } from '@/features/workflows/useWorkflows';
import { ResourcePicker } from './ResourcePicker';

const STATUS_LABEL: Record<FlowStatus, string> = {
  draft: '草稿',
  published: '已发布',
  retired: '已下线',
};

const STATUS_TONE: Record<FlowStatus, string> = {
  draft: 'bg-[var(--bg-elevated)] text-[var(--text-secondary)]',
  published: 'bg-emerald-50 text-emerald-700',
  retired: 'bg-rose-50 text-rose-700',
};

const TRIGGER_TONE: Record<TriggerType, string> = {
  '消息触发': 'bg-sky-50 text-sky-700',
  '定时触发': 'bg-violet-50 text-violet-700',
  '事件触发': 'bg-amber-50 text-amber-700',
  '手动触发': 'bg-slate-100 text-slate-700',
};

interface WorkflowPickerProps {
  selectedIds: string[];
  onChange: (ids: string[]) => void;
  allowedStatuses?: FlowStatus[];
  allowedTriggers?: TriggerType[];
  className?: string;
  showPreview?: boolean;
  emptyText?: string;
}

export function WorkflowPicker({
  selectedIds,
  onChange,
  allowedStatuses,
  allowedTriggers,
  className,
  showPreview = true,
  emptyText = '暂无可用工作流,先去「工作流管理」添加',
}: WorkflowPickerProps) {
  const { data: flows, isLoading, error } = useWorkflows();
  const filteredFlows = useMemo(() => {
    if (!flows) return undefined;
    let result = flows;
    if (allowedStatuses && allowedStatuses.length > 0) {
      const set = new Set(allowedStatuses);
      result = result.filter((f) => set.has(f.status));
    }
    if (allowedTriggers && allowedTriggers.length > 0) {
      const set = new Set(allowedTriggers);
      result = result.filter((f) => set.has(f.trigger));
    }
    return result;
  }, [flows, allowedStatuses, allowedTriggers]);

  return (
    <ResourcePicker<Flow>
      mode="multi"
      data={filteredFlows}
      isLoading={isLoading}
      error={error}
      queryKey="workflows"
      selectedIds={selectedIds}
      onChange={onChange}
      searchFields={(f) => [f.name, f.description, f.scene ?? '']}
      filterChips={[
        { key: 'published', label: '已发布', match: (f) => f.status === 'published' },
        { key: 'draft', label: '草稿', match: (f) => f.status === 'draft' },
        { key: '消息触发', label: '消息触发', match: (f) => f.trigger === '消息触发' },
        { key: '定时触发', label: '定时触发', match: (f) => f.trigger === '定时触发' },
        { key: '事件触发', label: '事件触发', match: (f) => f.trigger === '事件触发' },
        { key: '手动触发', label: '手动触发', match: (f) => f.trigger === '手动触发' },
      ]}
      renderItem={(f, selected) => <FlowItem flow={f} selected={selected} />}
      renderPreview={showPreview ? (f) => <FlowPreview flow={f} /> : undefined}
      emptyText={emptyText}
      placeholder="搜索工作流名 / 场景"
      className={className}
    />
  );
}

function FlowItem({ flow, selected }: { flow: Flow; selected: boolean }) {
  return (
    <div className="flex min-w-0 items-center gap-2">
      <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-violet-50 text-violet-600">
        <Workflow className="h-3.5 w-3.5" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className={`truncate text-xs font-semibold ${selected ? 'text-[var(--brand)]' : 'text-[var(--text)]'}`}>
            {flow.name}
          </span>
          <span className={`shrink-0 rounded-full px-1.5 py-px text-[9px] font-medium ${TRIGGER_TONE[flow.trigger]}`}>
            {flow.trigger}
          </span>
          <span className={`shrink-0 rounded-full px-1.5 py-px text-[9px] font-medium ${STATUS_TONE[flow.status]}`}>
            {STATUS_LABEL[flow.status]}
          </span>
        </div>
        {flow.description && (
          <p className="mt-0.5 line-clamp-1 text-[10px] text-[var(--text-muted)]">{flow.description}</p>
        )}
      </div>
    </div>
  );
}

function FlowPreview({ flow }: { flow: Flow }) {
  return (
    <div className="space-y-3 text-xs">
      <header>
        <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">
          工作流 · {flow.scene ?? '通用场景'}
        </p>
        <h3 className="mt-1 text-sm font-semibold text-[var(--text)]">{flow.name}</h3>
        <p className="mt-1 text-[10px] leading-relaxed text-[var(--text-muted)]">
          {flow.description || '(无描述)'}
        </p>
      </header>

      <div className="flex flex-wrap gap-1.5">
        <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${TRIGGER_TONE[flow.trigger]}`}>
          {flow.trigger}
        </span>
        <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${STATUS_TONE[flow.status]}`}>
          {STATUS_LABEL[flow.status]}
        </span>
        <span className="rounded-full bg-[var(--bg-elevated)] px-2 py-0.5 text-[10px] text-[var(--text-secondary)]">
          负责人 {flow.owner}
        </span>
      </div>

      <dl className="grid grid-cols-2 gap-2">
        <Stat label="调用次数" value={flow.callCount?.toLocaleString('zh-CN') ?? '0'} />
        <Stat label="入参 / 出参" value={`${flow.inputs ?? 0} / ${flow.outputs ?? 0}`} />
        <Stat label="绑定智能体" value={`${flow.boundAgents?.length ?? 0} 个`} />
        <Stat label="版本" value={`v${flow.versions?.length ?? 0}`} />
        <Stat label="创建" value={flow.createdAt ?? '—'} />
        <Stat label="更新" value={flow.updatedAt ?? '—'} />
      </dl>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-1)] p-2">
      <p className="text-[10px] text-[var(--text-muted)]">{label}</p>
      <p className="mt-0.5 text-xs font-semibold tabular-nums">{value}</p>
    </div>
  );
}
