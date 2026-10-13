/**
 * KnowledgePicker — 包装 ResourcePicker,接 useKnowledgeBases。
 *
 * 用法:
 *   <KnowledgePicker selectedIds={...} onChange={ids => ...} />
 *   <KnowledgePicker selectedIds={...} onChange={...} allowedStatuses={['indexed']} />
 */
import { useMemo } from 'react';
import { Database } from 'lucide-react';
import type { Kb, KbStatus } from '@/features/knowledge/schema';
import { useKnowledgeBases } from '@/features/knowledge/useKnowledge';
import { ResourcePicker } from './ResourcePicker';

const STATUS_LABEL: Record<KbStatus, string> = {
  indexed: '已索引',
  indexing: '索引中',
  paused: '已暂停',
  failed: '失败',
};

const STATUS_TONE: Record<KbStatus, string> = {
  indexed: 'bg-emerald-50 text-emerald-700',
  indexing: 'bg-sky-50 text-sky-700',
  paused: 'bg-amber-50 text-amber-700',
  failed: 'bg-rose-50 text-rose-700',
};

const SCOPE_LABEL: Record<string, string> = {
  '公开': '公开',
  '部门': '部门',
  '个人': '个人',
};

interface KnowledgePickerProps {
  selectedIds: string[];
  onChange: (ids: string[]) => void;
  allowedStatuses?: KbStatus[];
  className?: string;
  showPreview?: boolean;
  emptyText?: string;
}

export function KnowledgePicker({
  selectedIds,
  onChange,
  allowedStatuses,
  className,
  showPreview = true,
  emptyText = '暂无可用知识库,先去「知识管理」添加',
}: KnowledgePickerProps) {
  const { data: kbs, isLoading, error } = useKnowledgeBases();
  const filteredKbs = useMemo(() => {
    if (!kbs) return undefined;
    if (!allowedStatuses || allowedStatuses.length === 0) return kbs;
    const set = new Set(allowedStatuses);
    return kbs.filter((k) => set.has(k.status));
  }, [kbs, allowedStatuses]);

  return (
    <ResourcePicker<Kb>
      mode="multi"
      data={filteredKbs}
      isLoading={isLoading}
      error={error}
      queryKey="knowledge"
      selectedIds={selectedIds}
      onChange={onChange}
      searchFields={(k) => [k.name, k.description ?? '', ...(k.tags ?? [])]}
      filterChips={[
        { key: 'indexed', label: '已索引', match: (k) => k.status === 'indexed' },
        { key: 'indexing', label: '索引中', match: (k) => k.status === 'indexing' },
        { key: 'paused', label: '已暂停', match: (k) => k.status === 'paused' },
        { key: '公开', label: '公开', match: (k) => k.scope === '公开' },
        { key: '部门', label: '部门', match: (k) => k.scope === '部门' },
        { key: '个人', label: '个人', match: (k) => k.scope === '个人' },
      ]}
      renderItem={(k, selected) => <KbItem kb={k} selected={selected} />}
      renderPreview={showPreview ? (k) => <KbPreview kb={k} /> : undefined}
      emptyText={emptyText}
      placeholder="搜索知识库名 / 描述 / 标签"
      className={className}
    />
  );
}

function KbItem({ kb, selected }: { kb: Kb; selected: boolean }) {
  return (
    <div className="flex min-w-0 items-center gap-2">
      <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-sky-50 text-sky-600">
        <Database className="h-3.5 w-3.5" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className={`truncate text-xs font-semibold ${selected ? 'text-[var(--brand)]' : 'text-[var(--text)]'}`}>
            {kb.name}
          </span>
          <span className={`shrink-0 rounded-full px-1.5 py-px text-[9px] font-medium ${STATUS_TONE[kb.status]}`}>
            {STATUS_LABEL[kb.status]}
          </span>
        </div>
        <p className="mt-0.5 line-clamp-1 text-[10px] text-[var(--text-muted)]">
          {kb.description || '(无描述)'}
        </p>
      </div>
    </div>
  );
}

function KbPreview({ kb }: { kb: Kb }) {
  return (
    <div className="space-y-3 text-xs">
      <header>
        <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">
          知识库
        </p>
        <h3 className="mt-1 text-sm font-semibold text-[var(--text)]">{kb.name}</h3>
        <p className="mt-1 text-[10px] leading-relaxed text-[var(--text-muted)]">
          {kb.description || '(无描述)'}
        </p>
      </header>

      <div className="flex flex-wrap gap-1.5">
        <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${STATUS_TONE[kb.status]}`}>
          {STATUS_LABEL[kb.status]}
        </span>
        <span className="rounded-full bg-[var(--bg-elevated)] px-2 py-0.5 text-[10px] text-[var(--text-secondary)]">
          {SCOPE_LABEL[kb.scope] ?? kb.scope}
        </span>
        {kb.tags.map((t) => (
          <span key={t} className="rounded-full border border-[var(--border)] px-2 py-0.5 text-[10px] text-[var(--text-muted)]">
            #{t}
          </span>
        ))}
      </div>

      <dl className="grid grid-cols-2 gap-2">
        <Stat label="文档数" value={kb.docCount?.toLocaleString('zh-CN') ?? '0'} />
        <Stat label="向量数" value={kb.vectorCount?.toLocaleString('zh-CN') ?? '0'} />
        <Stat label="命中率" value={kb.evalHitRate ? `${kb.evalHitRate}%` : '—'} />
        <Stat label="更新" value={kb.updatedAt ?? '—'} />
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
