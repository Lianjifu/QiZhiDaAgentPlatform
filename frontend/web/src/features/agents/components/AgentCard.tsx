/**
 * 智能体卡片 — 选择、收藏，以及查看、编辑、发布、导出、删除。
 */
import { AlertTriangle, Bot, CheckCircle2, CheckSquare, Clock, Download, Edit3, Sparkles, Square, Star, Timer, Trash2, TrendingUp } from 'lucide-react';
import type { AgentEntry } from '../schema';
import { formatCalls } from './constants';
import { statusBadge, toneClass } from './constants';

export interface AgentCardProps {
  agent: AgentEntry;
  onSelect: (agent: AgentEntry) => void;
  onToggleStar: (id: string) => void;
  selected: boolean;
  onToggleSelect: (id: string) => void;
  onEdit: (agent: AgentEntry) => void;
  onPublish: (agent: AgentEntry) => void;
  onExportOne: (agent: AgentEntry) => void;
  onRequestDelete: (agent: AgentEntry) => void;
}

export function AgentCard({
  agent, onSelect, onToggleStar, selected, onToggleSelect,
  onEdit, onPublish, onExportOne, onRequestDelete,
}: AgentCardProps) {
  const badge = statusBadge[agent.status];
  const Icon = Bot;
  const isInactive = agent.calls === 0;
  const handleCardKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onSelect(agent);
    }
  };
  return (
    <article
      className={`group relative flex flex-col gap-4 rounded-2xl border bg-[var(--surface-1)] p-5 text-left transition hover:-translate-y-0.5 hover:shadow-[var(--shadow-sm)] ${
        selected ? 'border-[var(--brand)] shadow-[var(--shadow-sm)]' : 'border-[var(--border)] hover:border-[var(--brand)]'
      }`}
    >
      <div
        role="button"
        tabIndex={0}
        onClick={() => onSelect(agent)}
        onKeyDown={handleCardKeyDown}
        aria-label={`查看 ${agent.name} 详情`}
        className="absolute inset-0 z-0 cursor-pointer rounded-2xl focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand)]"
      />
      <div className="relative z-10 flex items-start justify-between">
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onToggleSelect(agent.id);
          }}
          aria-label={selected ? `取消选择 ${agent.name}` : `选择 ${agent.name}`}
          aria-pressed={selected}
          className={`grid h-9 w-9 place-items-center rounded-lg transition ${
            selected ? 'bg-[var(--brand-light)] text-[var(--brand)]' : 'text-[var(--text-muted)] hover:bg-[var(--bg-hover)]'
          }`}
        >
          {selected ? <CheckSquare className="h-4 w-4" /> : <Square className="h-4 w-4" />}
        </button>
        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-label={agent.starred ? '取消收藏' : '收藏'}
            aria-pressed={agent.starred}
            onClick={(event) => {
              event.stopPropagation();
              onToggleStar(agent.id);
            }}
            className={`grid h-9 w-9 place-items-center rounded-lg transition ${agent.starred ? 'bg-[var(--warning-bg)] text-[var(--warning)]' : 'text-[var(--text-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--warning)]'}`}
          >
            <Star className={`h-4 w-4 ${agent.starred ? 'fill-current' : ''}`} />
          </button>
        </div>
      </div>
      <div className="pointer-events-none relative z-10 flex items-start gap-3">
        <span className={`grid h-12 w-12 shrink-0 place-items-center rounded-xl ${toneClass[agent.tone]}`}>
          <Icon className="h-6 w-6" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-[var(--text-muted)]">{agent.category} · {agent.owner}</p>
          <h4 className="mt-1.5 text-base font-semibold tracking-tight text-[var(--text)]">{agent.name}</h4>
        </div>
      </div>
      <p className="pointer-events-none relative z-10 line-clamp-2 text-xs leading-5 text-[var(--text-muted)]">{agent.description}</p>
      <div className="pointer-events-none relative z-10 mt-auto flex flex-wrap items-center gap-3 border-t border-[var(--border)] pt-3 text-[11px]">
        <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 font-semibold ${badge.className}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${badge.dot}`} aria-hidden="true" />
          {badge.label} · {agent.version}
        </span>
        {isInactive ? (
          <span className="inline-flex items-center gap-1 text-[var(--text-muted)]">
            <Clock className="h-3 w-3" />{agent.lastUpdate}
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 text-[var(--text-muted)]">
            <TrendingUp className="h-3 w-3" />调用 {formatCalls(agent.calls)}
          </span>
        )}
      </div>
      {isInactive ? (
        <div className="pointer-events-none relative z-10 text-[11px] text-[var(--text-muted)]">{agent.lastUpdate} · 等待评估</div>
      ) : (
        <div className="pointer-events-none relative z-10 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[var(--text-muted)]">
          <span className="inline-flex items-center gap-1"><Sparkles className="h-3 w-3" />评分 {agent.rating.toFixed(1)}</span>
          <span className="inline-flex items-center gap-1"><AlertTriangle className="h-3 w-3" />错误 {agent.errorRate.toFixed(2)}%</span>
          <span className="inline-flex items-center gap-1"><Timer className="h-3 w-3" />延迟 {(agent.avgLatencyMs / 1000).toFixed(1)}s</span>
        </div>
      )}
      <div className="relative z-10 flex flex-wrap gap-1.5 border-t border-[var(--border)] pt-3">
        <button type="button" onClick={(event) => { event.stopPropagation(); onEdit(agent); }} className="inline-flex flex-1 items-center justify-center gap-1 rounded-lg border border-[var(--border)] px-1.5 py-1.5 text-[11px] font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]">
          <Edit3 className="h-3.5 w-3.5" />编辑
        </button>
        <button
          type="button"
          disabled={agent.status === 'published'}
          onClick={(event) => { event.stopPropagation(); onPublish(agent); }}
          className="inline-flex flex-1 items-center justify-center gap-1 rounded-lg border border-[var(--border)] px-1.5 py-1.5 text-[11px] font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)] disabled:cursor-default disabled:opacity-40 disabled:hover:border-[var(--border)] disabled:hover:text-[var(--text-secondary)]"
        >
          <CheckCircle2 className="h-3.5 w-3.5" />{agent.status === 'published' ? '已发布' : '发布'}
        </button>
        <button type="button" onClick={(event) => { event.stopPropagation(); onExportOne(agent); }} className="inline-flex flex-1 items-center justify-center gap-1 rounded-lg border border-[var(--border)] px-1.5 py-1.5 text-[11px] font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]">
          <Download className="h-3.5 w-3.5" />导出
        </button>
        <button type="button" onClick={(event) => { event.stopPropagation(); onRequestDelete(agent); }} className="inline-flex flex-1 items-center justify-center gap-1 rounded-lg border border-[var(--danger)]/30 px-1.5 py-1.5 text-[11px] font-semibold text-[var(--danger)] hover:bg-[var(--danger-bg)]">
          <Trash2 className="h-3.5 w-3.5" />删除
        </button>
      </div>
    </article>
  );
}
