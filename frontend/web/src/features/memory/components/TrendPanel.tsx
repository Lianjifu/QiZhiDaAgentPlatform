/**
 * 记忆趋势 —— L1 活跃会话 / L2 命中（后端按所选范围聚合 ✓）。
 *
 * ⚠️ **这面板接的是真数据** ✓（``GET /api/admin/memory/trend?range=`` ✓）——
 * 之前页面上那个时间范围下拉**选了没用** ✓（``range`` 没人消费 ✓）——
 * 现在下拉真的驱动这个面板 ✓。
 */
import { Sparkline } from '@/components/feedback/Sparkline';

export interface MemoryTrendPanelProps {
  l1Active: number[];
  l2Hits: number[];
  rangeLabel: string;
}

function last(values: number[]): number {
  return values.length > 0 ? values[values.length - 1] : 0;
}

export function MemoryTrendPanel({ l1Active, l2Hits, rangeLabel }: MemoryTrendPanelProps) {
  const items = [
    {
      label: 'L1 活跃会话',
      value: last(l1Active),
      series: l1Active,
      stroke: 'var(--brand)',
      hint: '当前生效的短期会话记忆',
    },
    {
      label: 'L2 命中',
      value: last(l2Hits),
      series: l2Hits,
      stroke: 'var(--chart-purple)',
      hint: '长期记忆被检索命中的次数',
    },
  ];
  return (
    <section aria-label="记忆趋势" className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h3 className="text-base font-semibold">记忆趋势</h3>
          <p className="mt-1 text-xs text-[var(--text-muted)]">按所选范围聚合 · {rangeLabel}</p>
        </div>
      </div>
      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        {items.map((item) => (
          <div key={item.label} className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] p-4">
            <p className="text-xs font-semibold text-[var(--text-muted)]">{item.label}</p>
            <p className="mt-1 text-2xl font-semibold tabular-nums">{item.value}</p>
            <div className="mt-2">
              <Sparkline data={item.series} stroke={item.stroke} width={120} height={28} className="h-7 w-28" />
            </div>
            <p className="mt-2 text-[11px] text-[var(--text-muted)]">{item.hint}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
