/**
 * ModelPicker — 包装 ResourcePicker,接 useModelsList。
 *
 * 用法:
 *   <ModelPicker selectedId={...} onChange={(id) => ...} />
 *   <ModelPicker selectedId={...} onChange={...} allowedStatuses={['active', 'graying']} />
 */
import { useMemo } from 'react';
import type { Model, ModelStatus } from '@/features/models/schema';
import { STATUS_BADGE as MODEL_STATUS_BADGE } from '@/features/models/components/constants';
import { useModelsList } from '@/features/models/useModels';
import { ResourcePicker } from './ResourcePicker';

const STATUS_LABEL: Record<ModelStatus, string> = {
  active: '启用',
  graying: '灰度',
  draft: '草稿',
  retired: '已下线',
};

const TIER_LABEL: Record<string, string> = {
  premium: '旗舰',
  balanced: '均衡',
  economy: '经济',
};

interface ModelPickerProps {
  selectedId: string | null;
  onChange: (id: string | null) => void;
  allowedStatuses?: ModelStatus[];
  className?: string;
  showPreview?: boolean;
  emptyText?: string;
}

export function ModelPicker({
  selectedId,
  onChange,
  allowedStatuses,
  className,
  showPreview = true,
  emptyText = '暂无可用模型,先去「模型配置」添加',
}: ModelPickerProps) {
  const { data: models, isLoading, error } = useModelsList();
  const filteredModels = useMemo(() => {
    if (!models) return undefined;
    if (!allowedStatuses || allowedStatuses.length === 0) return models;
    const set = new Set(allowedStatuses);
    return models.filter((m) => set.has(m.status));
  }, [models, allowedStatuses]);

  return (
    <ResourcePicker<Model>
      mode="single"
      data={filteredModels}
      isLoading={isLoading}
      error={error}
      queryKey="models"
      selectedIds={selectedId ? [selectedId] : []}
      onChange={(ids) => onChange(ids[0] ?? null)}
      searchFields={(m) => [m.name, m.providerName, m.upstreamModel ?? '', ...(m.tags ?? [])]}
      filterChips={[
        { key: 'active', label: '启用', match: (m) => m.status === 'active' },
        { key: 'graying', label: '灰度', match: (m) => m.status === 'graying' },
        { key: 'draft', label: '草稿', match: (m) => m.status === 'draft' },
        { key: 'retired', label: '已下线', match: (m) => m.status === 'retired' },
        { key: 'premium', label: '旗舰', match: (m) => m.tier === 'premium' },
        { key: 'balanced', label: '均衡', match: (m) => m.tier === 'balanced' },
        { key: 'economy', label: '经济', match: (m) => m.tier === 'economy' },
      ]}
      renderItem={(m, selected) => <ModelItem model={m} selected={selected} />}
      renderPreview={showPreview ? (m) => <ModelPreview model={m} /> : undefined}
      emptyText={emptyText}
      placeholder="搜索模型名 / 提供商 / 标签"
      className={className}
    />
  );
}

function ModelItem({ model, selected }: { model: Model; selected: boolean }) {
  const status = MODEL_STATUS_BADGE[model.status];
  return (
    <div className="flex min-w-0 items-center gap-2">
      <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-md ${status.className}`}>
        <span className={`h-1.5 w-1.5 rounded-full ${status.dot}`} aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className={`truncate text-xs font-semibold ${selected ? 'text-[var(--brand)]' : 'text-[var(--text)]'}`}>
            {model.name}
          </span>
          <span className="shrink-0 rounded-full bg-[var(--bg-elevated)] px-1.5 py-px text-[9px] font-medium uppercase tracking-wide text-[var(--text-muted)]">
            {TIER_LABEL[model.tier] ?? model.tier}
          </span>
        </div>
        <div className="mt-0.5 flex items-center gap-1.5 text-[10px] text-[var(--text-muted)]">
          <span className="truncate">{model.providerName}</span>
          {model.task.length > 0 && (
            <>
              <span aria-hidden="true">·</span>
              <span className="truncate">{model.task.join('/')}</span>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function ModelPreview({ model }: { model: Model }) {
  const status = MODEL_STATUS_BADGE[model.status];
  return (
    <div className="space-y-3 text-xs">
      <header>
        <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">
          {model.providerName}
        </p>
        <h3 className="mt-1 text-sm font-semibold text-[var(--text)]">{model.name}</h3>
        {model.upstreamModel && (
          <p className="mt-0.5 font-mono text-[10px] text-[var(--text-muted)]">upstream: {model.upstreamModel}</p>
        )}
      </header>

      <div className="flex flex-wrap gap-1.5">
        <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${status.className}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${status.dot}`} aria-hidden="true" />
          {STATUS_LABEL[model.status]}
        </span>
        {model.task.map((t) => (
          <span key={t} className="rounded-full bg-[var(--bg-elevated)] px-2 py-0.5 text-[10px]">{t}</span>
        ))}
        {model.tags.map((t) => (
          <span key={t} className="rounded-full border border-[var(--border)] px-2 py-0.5 text-[10px] text-[var(--text-muted)]">#{t}</span>
        ))}
      </div>

      {model.description && (
        <p className="rounded-lg bg-[var(--bg-elevated)] p-2.5 text-[11px] leading-relaxed text-[var(--text-secondary)]">
          {model.description}
        </p>
      )}

      <dl className="grid grid-cols-2 gap-2">
        <Stat label="上下文窗口" value={model.contextWindow ? `${(model.contextWindow / 1000).toLocaleString('zh-CN')}k` : '—'} />
        <Stat label="成功率" value={model.calls ? `${model.successRate}%` : '暂无数据'} />
        <Stat label="输入价" value={model.priceIn ? `¥ ${model.priceIn}/1k` : '—'} />
        <Stat label="输出价" value={model.priceOut ? `¥ ${model.priceOut}/1k` : '—'} />
        <Stat label="平均延迟" value={model.latencyMs ? `${model.latencyMs} ms` : '—'} />
        <Stat label="累计调用" value={model.calls ? model.calls.toLocaleString('zh-CN') : '0'} />
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
