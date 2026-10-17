/**
 * RoutePicker — Phase 22: 策略路由选择器 (admin agent_factory)
 *
 * 与 ModelPicker 同型 — 包 ResourcePicker, 接 useRouteOptions, 展示:
 *   - 列表项: route.name + strategy 标签 + 任务 + fallback 数量
 *   - 详情预览: strategy 说明 + primary model + fallback 链 (含 weight)
 *   - filter chip: 按 strategy 过滤
 *
 * 用法:
 *   <RoutePicker selectedId={version.route_id} onChange={(id) => ...} />
 *   <RoutePicker ... strategy="round-robin" onChange={...} />  // 也可加策略限制
 */
import { useMemo } from 'react';
import {
  GitBranch, Layers, Network, Shuffle, Sparkles, Wallet, Zap,
} from 'lucide-react';
import { ResourcePicker } from './ResourcePicker';
import {
  ROUTE_STRATEGY_DESCRIPTION,
  ROUTE_STRATEGY_LABEL,
  useRouteOptions,
  type RouteOption,
  type RouteStrategy,
} from '../useAgentFactory';

const STRATEGY_ICON: Record<RouteStrategy, React.ReactNode> = {
  'fallback': <Layers className="h-3.5 w-3.5" aria-hidden="true" />,
  'quality-first': <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />,
  'cost-first': <Wallet className="h-3.5 w-3.5" aria-hidden="true" />,
  'latency-first': <Zap className="h-3.5 w-3.5" aria-hidden="true" />,
  'round-robin': <Shuffle className="h-3.5 w-3.5" aria-hidden="true" />,
  'weighted': <Network className="h-3.5 w-3.5" aria-hidden="true" />,
};

const TASK_LABEL: Record<string, string> = {
  reasoning: '推理',
  generation: '生成',
  classification: '分类',
  embedding: '嵌入',
  summarization: '摘要',
};

interface RoutePickerProps {
  selectedId: string | null;
  onChange: (id: string | null) => void;
  /** 只显示启用 / 禁用的 (默认只显示 enabled) */
  enabledOnly?: boolean;
  /** 限制可选项到指定 strategy (admin 可能只配一类) */
  strategyFilter?: RouteStrategy | RouteStrategy[];
  className?: string;
  showPreview?: boolean;
  emptyText?: string;
}

export function RoutePicker({
  selectedId,
  onChange,
  enabledOnly = true,
  strategyFilter,
  className,
  showPreview = true,
  emptyText = '暂无可用策略路由, 先去「模型配置」→ 路由配置添加',
}: RoutePickerProps) {
  const { data: routes, isLoading, error } = useRouteOptions();
  const filtered = useMemo(() => {
    if (!routes) return undefined;
    let out = routes;
    if (enabledOnly) {
      out = out.filter((r) => r.enabled);
    }
    if (strategyFilter) {
      const allow = Array.isArray(strategyFilter) ? new Set(strategyFilter) : new Set([strategyFilter]);
      out = out.filter((r) => allow.has(r.strategy));
    }
    return out;
  }, [routes, enabledOnly, strategyFilter]);

  return (
    <ResourcePicker<RouteOption>
      mode="single"
      data={filtered}
      isLoading={isLoading}
      error={error}
      queryKey="routes"
      selectedIds={selectedId ? [selectedId] : []}
      onChange={(ids) => onChange(ids[0] ?? null)}
      searchFields={(r) => [r.name, r.task ?? '', r.description ?? '']}
      filterChips={[
        { key: 'quality-first', label: '质量优先', match: (r) => r.strategy === 'quality-first' },
        { key: 'cost-first', label: '成本优先', match: (r) => r.strategy === 'cost-first' },
        { key: 'latency-first', label: '延迟优先', match: (r) => r.strategy === 'latency-first' },
        { key: 'round-robin', label: '轮询', match: (r) => r.strategy === 'round-robin' },
        { key: 'weighted', label: '加权', match: (r) => r.strategy === 'weighted' },
        { key: 'fallback', label: '失败转移', match: (r) => r.strategy === 'fallback' },
      ]}
      renderItem={(r, selected) => <RouteItem route={r} selected={selected} />}
      renderPreview={showPreview ? (r) => <RoutePreview route={r} /> : undefined}
      emptyText={emptyText}
      placeholder="搜索路由名 / 任务 / 描述"
      className={className}
    />
  );
}

function RouteItem({ route, selected }: { route: RouteOption; selected: boolean }) {
  const fallbackCount = Array.isArray(route.fallback_model_ids) ? route.fallback_model_ids.length : 0;
  return (
    <div className="flex min-w-0 items-center gap-2">
      <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-[var(--brand-light)] text-[var(--brand)]">
        {STRATEGY_ICON[route.strategy]}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className={`truncate text-xs font-semibold ${selected ? 'text-[var(--brand)]' : 'text-[var(--text)]'}`}>
            {route.name}
          </span>
          <span className="shrink-0 rounded-full bg-[var(--bg-elevated)] px-1.5 py-px text-[9px] font-medium uppercase tracking-wide text-[var(--text-muted)]">
            {ROUTE_STRATEGY_LABEL[route.strategy] ?? route.strategy}
          </span>
        </div>
        <div className="mt-0.5 flex items-center gap-1.5 text-[10px] text-[var(--text-muted)]">
          {route.task && <span className="truncate">{TASK_LABEL[route.task] ?? route.task}</span>}
          {fallbackCount > 0 && (
            <>
              <span aria-hidden="true">·</span>
              <span className="truncate">fallback × {fallbackCount}</span>
            </>
          )}
          {!route.enabled && (
            <>
              <span aria-hidden="true">·</span>
              <span className="truncate text-[var(--text-muted)]">已禁用</span>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function RoutePreview({ route }: { route: RouteOption }) {
  const fallbackCount = Array.isArray(route.fallback_model_ids) ? route.fallback_model_ids.length : 0;
  return (
    <div className="space-y-3 text-xs">
      <header>
        <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">
          {TASK_LABEL[route.task] ?? route.task ?? '通用'}
        </p>
        <h3 className="mt-1 flex items-center gap-1.5 text-sm font-semibold text-[var(--text)]">
          <GitBranch className="h-3.5 w-3.5" aria-hidden="true" />
          {route.name}
        </h3>
      </header>

      <div className="flex flex-wrap items-center gap-1.5">
        <span className="inline-flex items-center gap-1 rounded-full bg-[var(--brand-light)] px-2 py-0.5 text-[10px] font-semibold text-[var(--brand)]">
          {STRATEGY_ICON[route.strategy]}
          {ROUTE_STRATEGY_LABEL[route.strategy] ?? route.strategy}
        </span>
        {!route.enabled && (
          <span className="rounded-full border border-[var(--border)] px-2 py-0.5 text-[10px] text-[var(--text-muted)]">已禁用</span>
        )}
      </div>

      <p className="rounded-lg bg-[var(--bg-elevated)] p-2.5 text-[11px] leading-relaxed text-[var(--text-secondary)]">
        {ROUTE_STRATEGY_DESCRIPTION[route.strategy]}
      </p>

      <dl className="grid grid-cols-2 gap-2">
        <Stat label="主模型" value={route.primary_model_id ? shortId(route.primary_model_id) : '—'} />
        <Stat label="Fallback 数" value={fallbackCount > 0 ? String(fallbackCount) : '无'} />
      </dl>

      {fallbackCount > 0 && (
        <div>
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
            Fallback 链
          </p>
          <ol className="space-y-0.5 text-[10px] font-mono text-[var(--text-secondary)]">
            {route.fallback_model_ids.map((item, idx) => {
              if (typeof item === 'string') {
                return (
                  <li key={`${item}-${idx}`} className="flex items-center gap-1.5">
                    <span className="text-[var(--text-muted)]">{idx + 1}.</span>
                    <span className="truncate">{shortId(item)}</span>
                  </li>
                );
              }
              return (
                <li key={`${item.id}-${idx}`} className="flex items-center gap-1.5">
                  <span className="text-[var(--text-muted)]">{idx + 1}.</span>
                  <span className="truncate">{shortId(item.id)}</span>
                  <span className="ml-auto rounded bg-[var(--bg-elevated)] px-1 text-[var(--text-muted)]">w={item.weight}</span>
                </li>
              );
            })}
          </ol>
        </div>
      )}

      {route.description && (
        <p className="rounded-lg bg-[var(--bg-elevated)] p-2.5 text-[11px] leading-relaxed text-[var(--text-secondary)]">
          {route.description}
        </p>
      )}
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

function shortId(raw: string): string {
  if (!raw) return '—';
  return raw.length > 8 ? `${raw.slice(0, 4)}…${raw.slice(-4)}` : raw;
}
