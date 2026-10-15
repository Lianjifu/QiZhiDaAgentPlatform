/**
 * Drawer 左侧垂直导航 + 必填/错误/访问徽标。
 *
 * panels: 必填/推荐/可选 三档徽标在每个 panel 名称右侧。
 * 错误:validation.errors[panel] 有值时,徽标变红。
 * 完成:基于 draft 实际内容判断,而不只是"点过";避免重新打开页面后
 * visited useState 丢失导致状态回退.
 */
import { AlertTriangle, Check, CheckCircle2, CheckSquare, Circle, Clock, Download, Trash2, X } from 'lucide-react';
import type { AgentEntry, DrawerPanel } from '../schema';
import { DRAWER_NAV_ITEMS } from './constants';

interface PanelMeta {
  required?: boolean;
  recommended?: boolean;
  error?: string | null;
  filled?: boolean;
}

interface ValidationLike {
  errors: Partial<Record<DrawerPanel, string>>;
}

/** 判断单个 panel 是否"实际填了" (基于 draft, 跨刷新稳定). */
function isPanelFilled(panel: DrawerPanel, draft: AgentEntry): boolean {
  switch (panel) {
    case 'basic':
      return draft.name.trim().length > 0 && draft.description.trim().length > 0;
    case 'skills':
      return draft.tools.length > 0;
    case 'knowledge':
      return draft.knowledgeRefs.length > 0;
    case 'flow':
      return draft.flowRefs.length > 0;
    case 'memory':
      return draft.memoryPolicy.enabled;
    case 'prompt': {
      const p = draft.prompts ?? ({} as AgentEntry['prompts']);
      return [p.prompt, p.soul, p.agents, p.user, p.tools].some(
        (s) => typeof s === 'string' && s.trim().length > 0,
      );
    }
    case 'permission':
      return draft.visibleScope.length > 0;
    case 'versions':
    case 'evaluation':
      // 这两个 panel 状态由 detail 页签独立跟踪, 不参与基础"已填"判断
      return true;
    default:
      return false;
  }
}

export function DrawerSidebar({
  panel,
  setPanel,
  validation,
  draft,
  showTierBadges = true,
  className,
}: {
  panel: DrawerPanel;
  setPanel: (p: DrawerPanel) => void;
  validation?: ValidationLike;
  draft: AgentEntry;
  showTierBadges?: boolean;
  className?: string;
}) {
  const tierFor = (id: DrawerPanel): PanelMeta => {
    const error = validation?.errors[id] ?? null;
    const filled = isPanelFilled(id, draft);
    return {
      required: id === 'basic' || id === 'skills',
      recommended: id === 'knowledge' || id === 'prompt' || id === 'flow',
      error,
      filled: filled && !error,
    };
  };

  return (
    <nav
      aria-label="智能体工作区导航"
      className={`flex w-full shrink-0 flex-col gap-1 border-b border-[var(--border)] bg-[var(--bg-elevated)] p-4 lg:w-[260px] lg:border-b-0 lg:border-r ${className ?? ''}`}
    >
      <p className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">工作区</p>
      {DRAWER_NAV_ITEMS.map((item) => {
        const Icon = item.icon;
        const active = panel === item.id;
        const meta = tierFor(item.id);
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => setPanel(item.id)}
            aria-pressed={active}
            className={`flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left text-xs font-semibold transition ${
              active ? 'bg-[var(--brand-light)] text-[var(--brand)]' : 'text-[var(--text-secondary)] hover:bg-[var(--surface-1)]'
            }`}
          >
            <Icon className="h-4 w-4" />
            <span className="flex-1 truncate">{item.label}</span>
            {showTierBadges && (
              <span className="flex shrink-0 items-center gap-1">
                {meta.error ? (
                  <AlertTriangle className="h-3.5 w-3.5 text-rose-500" aria-label="未填必填" />
                ) : meta.filled ? (
                  <Check className="h-3.5 w-3.5 text-emerald-500" aria-label="已填写" />
                ) : meta.required ? (
                  <span className="rounded-full bg-rose-100 px-1.5 py-px text-[9px] font-semibold uppercase tracking-wide text-rose-600">必填</span>
                ) : meta.recommended ? (
                  <span className="rounded-full bg-amber-100 px-1.5 py-px text-[9px] font-semibold uppercase tracking-wide text-amber-700">推荐</span>
                ) : (
                  <Circle className="h-3 w-3 text-[var(--text-muted)]" aria-label="可选" />
                )}
              </span>
            )}
          </button>
        );
      })}
    </nav>
  );
}

export function BatchToolbar({
  count, onClear, onBatchPublish, onBatchRetire, onBatchDelete, onBatchExport,
}: {
  count: number;
  onClear: () => void;
  onBatchPublish: () => void;
  onBatchRetire: () => void;
  onBatchDelete: () => void;
  onBatchExport: () => void;
}) {
  return (
    <section
      aria-label="批量操作"
      className="flex flex-wrap items-center gap-3 rounded-2xl border border-[var(--brand)] bg-[var(--brand-light)] px-4 py-3 sm:px-5"
    >
      <div className="flex items-center gap-2 text-sm font-semibold text-[var(--brand)]">
        <CheckSquare className="h-4 w-4" />已选 {count} 项
      </div>
      <div className="ml-auto flex flex-wrap items-center gap-2">
        <button type="button" onClick={onBatchPublish} className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--brand)] bg-[var(--surface-1)] px-3 py-1.5 text-[11px] font-semibold text-[var(--brand)] hover:bg-[var(--brand-light)]">
          <CheckCircle2 className="h-3.5 w-3.5" />批量发布
        </button>
        <button type="button" onClick={onBatchRetire} className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-3 py-1.5 text-[11px] font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]">
          <Clock className="h-3.5 w-3.5" />批量下线
        </button>
        <button type="button" onClick={onBatchDelete} className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--danger)]/40 bg-[var(--surface-1)] px-3 py-1.5 text-[11px] font-semibold text-[var(--danger)] hover:bg-[var(--danger-bg)]">
          <Trash2 className="h-3.5 w-3.5" />批量删除
        </button>
        <button type="button" onClick={onBatchExport} className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-3 py-1.5 text-[11px] font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]">
          <Download className="h-3.5 w-3.5" />批量导出
        </button>
        <button type="button" onClick={onClear} className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-semibold text-[var(--text-muted)] hover:text-[var(--brand)]">
          <X className="h-3.5 w-3.5" />取消选择
        </button>
      </div>
    </section>
  );
}
