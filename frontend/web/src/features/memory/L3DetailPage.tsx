/**
 * L3 团队知识详情 — 路由 /admin/memory/l3/:id
 * Wave 5:4 KPI(去「引用方式」占位)+ 引用趋势 + 晋升来源 + 被引用 Agent + 相关知识(同团队)。
 */
import { useMemo } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  ArrowUp, BookOpen, Bot, Calendar, Hash, Layers, TrendingUp, User,
} from 'lucide-react';
import { useL3Entry, useL3Entries, useL2Facts } from './useMemory';
import {
  DetailShell, DetailHeader, DetailStatGrid, DetailStat,
  DetailSection, DetailField, DetailNotFound, DetailSkeleton,
} from '@/features/knowledge/components/DetailLayout';
import { useApiQuery } from '@/services/query';
import type { AgentEntry } from '@/features/agents/schema';
import { L3_STATUS_BADGE, LAYER_META } from './components/constants';

export default function L3DetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const decoded = useMemo(() => decodeURIComponent(id), [id]);
  const { data: referencedAgents = [] } = useApiQuery<AgentEntry[]>(['memory', 'l3', decoded, 'agents'], `/api/admin/memory/l3/${encodeURIComponent(decoded)}/agents`, undefined, { enabled: Boolean(decoded) });
  const { data: entry, isLoading } = useL3Entry(decoded || null);
  const { data: allL3 } = useL3Entries();
  const { data: allL2 } = useL2Facts();
  const meta = LAYER_META.l3;
  const Icon = meta.icon;

  const sameTeamEntries = useMemo(() => {
    if (!entry) return [];
    return (allL3 ?? [])
      .filter((k) => k.team === entry.team && k.id !== entry.id)
      .slice(0, 4);
  }, [entry, allL3]);

  const promotedFromL2 = useMemo(() => {
    if (!entry?.promotedFromL2Ids) return [];
    const ids = new Set(entry.promotedFromL2Ids);
    return (allL2 ?? []).filter((f) => ids.has(f.id)).slice(0, 4);
  }, [entry, allL2]);


  if (isLoading) {
    return (
      <DetailShell backTo="/admin/memory" backLabel="返回记忆管理">
        <DetailSkeleton rows={3} />
      </DetailShell>
    );
  }
  if (!entry) {
    return (
      <DetailShell backTo="/admin/memory" backLabel="返回记忆管理">
        <DetailNotFound subject="团队知识不存在或已被下线" />
      </DetailShell>
    );
  }

  const status = L3_STATUS_BADGE[entry.status];
  const trendMax = entry.hitsTrend && entry.hitsTrend.length > 0 ? Math.max(...entry.hitsTrend) : 0;

  return (
    <DetailShell backTo="/admin/memory" backLabel="返回记忆管理">
      <DetailHeader
        eyebrow={`知识记忆 · ${entry.team}`}
        title={entry.title}
        icon={Icon}
        iconClass="bg-blue-50 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300"
        subtitle={`贡献者 ${entry.contributor} · 更新 ${entry.updatedAt} · 分类 ${entry.category}`}
        badges={[
          { label: status.label, className: status.className },
          { label: entry.category, className: 'bg-[var(--bg-elevated)] text-[var(--text-secondary)]' },
        ]}
      />

      <DetailStatGrid columns={4}>
        <DetailStat label="命中次数" value={entry.hits} tone={entry.hits > 100 ? 'success' : 'info'} hint={`累计 ${entry.hits.toLocaleString()} 次`} />
        <DetailStat label="状态" value={status.label} tone={entry.status === 'published' ? 'success' : entry.status === 'draft' ? 'warn' : 'danger'} />
        <DetailStat label="团队" value={entry.team} tone="brand" />
        <DetailStat label="分类" value={entry.category} />
      </DetailStatGrid>

      <DetailSection title="知识摘要" icon={Layers}>
        <p className="text-sm leading-7 text-[var(--text-secondary)]">{entry.summary}</p>
      </DetailSection>

      <DetailSection title="引用趋势" icon={TrendingUp}>
        {entry.hitsTrend && entry.hitsTrend.length > 0 ? (
          <div className="space-y-2">
            <div className="flex h-16 items-end gap-1.5">
              {entry.hitsTrend.map((v, idx) => {
                const heightPct = trendMax === 0 ? 0 : Math.max(8, Math.round((v / trendMax) * 100));
                const isLatest = idx === entry.hitsTrend!.length - 1;
                return (
                  <div key={idx} className="group relative flex flex-1 flex-col items-center justify-end">
                    <span className={`mb-1 text-[10px] tabular-nums ${isLatest ? 'font-semibold text-[var(--brand)]' : 'text-[var(--text-muted)]'}`}>{v.toLocaleString()}</span>
                    <div
                      className={`w-full rounded-t ${isLatest ? 'bg-[var(--brand)]' : 'bg-[var(--bg-elevated)] group-hover:bg-[var(--brand-light)]'}`}
                      style={{ height: `${heightPct}%`, minHeight: '4px' }}
                      aria-label={`第 ${idx + 1} 期 ${v} 次`}
                    />
                  </div>
                );
              })}
            </div>
            <div className="flex items-center justify-between text-[10px] text-[var(--text-muted)]">
              <span>近 {entry.hitsTrend.length} 期</span>
              <span>峰值 {trendMax.toLocaleString()} · 当前 {entry.hitsTrend[entry.hitsTrend.length - 1]?.toLocaleString()}</span>
            </div>
          </div>
        ) : (
          <p className="text-xs text-[var(--text-muted)]">暂无命中数据</p>
        )}
      </DetailSection>

      <DetailSection title="晋升来源" icon={ArrowUp}>
        {promotedFromL2.length > 0 ? (
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {promotedFromL2.map((f) => (
              <li key={f.id} className="flex items-center justify-between gap-2 rounded-xl border border-[var(--border)] bg-[var(--bg-app)] px-3 py-2 text-xs">
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{f.userName} · {f.key}</span>
                  <span className="mt-0.5 block truncate text-[11px] text-[var(--text-muted)]">{f.value}</span>
                </span>
                <Link to={`/admin/memory/l2/${f.id}`} className="shrink-0 text-[var(--brand)] hover:underline">查看长期记忆 →</Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-[var(--text-muted)]">
            {entry.promotedFromL2Ids && entry.promotedFromL2Ids.length > 0
              ? '晋升来源长期事实不存在或已被清空'
              : '直接创建,未通过长期晋升'}
          </p>
        )}
      </DetailSection>

      <DetailSection title="被引用 Agent" icon={Bot}>
        <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {referencedAgents.map((a) => (
            <li key={a.id} className="flex items-center justify-between rounded-xl border border-[var(--border)] bg-[var(--bg-app)] px-3 py-2 text-xs">
              <span className="min-w-0 flex-1 truncate">
                <span className="block font-medium">{a.name}</span>
                <span className="mt-0.5 block truncate text-[11px] text-[var(--text-muted)]">{a.category}</span>
              </span>
              <Link to={`/admin/agents/${a.id}`} className="shrink-0 text-[var(--brand)] hover:underline">查看 →</Link>
            </li>
          ))}
        </ul>
      </DetailSection>

      <DetailSection title="相关知识(同团队)" icon={BookOpen}>
        {sameTeamEntries.length === 0 ? (
          <p className="text-xs text-[var(--text-muted)]">该团队暂无其他条目</p>
        ) : (
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {sameTeamEntries.map((k) => {
              const sb = L3_STATUS_BADGE[k.status];
              return (
                <li key={k.id} className="flex items-center justify-between gap-2 rounded-xl border border-[var(--border)] bg-[var(--bg-app)] px-3 py-2 text-xs">
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{k.title}</span>
                    <span className="mt-0.5 block text-[11px] text-[var(--text-muted)]">命中 {k.hits.toLocaleString()} · {k.updatedAt}</span>
                  </span>
                  <span className={`shrink-0 inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${sb.className}`}>{sb.label}</span>
                  <Link to={`/admin/memory/l3/${k.id}`} className="shrink-0 text-[var(--brand)] hover:underline">查看 →</Link>
                </li>
              );
            })}
          </ul>
        )}
      </DetailSection>

      <DetailSection title="归档与归属" icon={User}>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <DetailField icon={Hash} label="知识 ID"><code className="text-xs">{entry.id}</code></DetailField>
          <DetailField icon={User} label="贡献者">{entry.contributor}</DetailField>
          <DetailField icon={Layers} label="分类">{entry.category}</DetailField>
          <DetailField icon={Calendar} label="更新时间">{entry.updatedAt}</DetailField>
        </div>
      </DetailSection>
    </DetailShell>
  );
}
