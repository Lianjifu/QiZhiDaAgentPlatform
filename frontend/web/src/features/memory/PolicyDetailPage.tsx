/**
 * 管理侧「记忆策略详情」独立页面 — 路由 /admin/memory/policies/:id
 *
 * Wave 5:迁移到 DetailLayout + 4 section(参数/状态/数据量/被 Agent 引用)。
 */
import { useMemo } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  Activity, BarChart3, Clock, HardDrive, Hash, Layers, Percent, Settings, Trash2, Users,
} from 'lucide-react';
import { useRetentionPolicy, useL1Sessions, useL2Facts, useL3Entries } from './useMemory';
import { useApiQuery } from '@/services/query';
import type { AgentEntry } from '@/features/agents/schema';
import {
  DetailShell, DetailHeader, DetailStatGrid, DetailStat,
  DetailSection, DetailField, DetailNotFound, DetailSkeleton,
} from '@/features/knowledge/components/DetailLayout';

const LAYER_LABEL: Record<string, { label: string; className: string; full: string }> = {
  l1: { label: '短期记忆', className: 'bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300', full: '短期记忆' },
  l2: { label: '长期记忆', className: 'bg-violet-50 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300', full: '长期记忆' },
  l3: { label: '知识记忆', className: 'bg-blue-50 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300', full: '知识记忆' },
};

const EVICTION_LABEL: Record<string, string> = {
  lru: 'LRU · 最近最少使用',
  fifo: 'FIFO · 先进先出',
  confidence: 'Confidence · 低置信度优先',
};

function policyHealth(hitRate: number): { tone: 'success' | 'warn' | 'danger'; label: string; advice: string } {
  if (hitRate >= 0.9) return { tone: 'success', label: '运行良好', advice: '策略与数据匹配,无需调整' };
  if (hitRate >= 0.75) return { tone: 'warn', label: '关注中', advice: '建议观察 2 周后再决定' };
  return { tone: 'danger', label: '需调整', advice: '考虑扩容或更换淘汰策略' };
}

export default function PolicyDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const decoded = useMemo(() => decodeURIComponent(id), [id]);
  const { data: boundAgents = [] } = useApiQuery<AgentEntry[]>(['memory', 'policies', decoded, 'agents'], `/api/admin/memory/policies/${encodeURIComponent(decoded)}/agents`, undefined, { enabled: Boolean(decoded) });
  const { data: policy, isLoading } = useRetentionPolicy(decoded || null);
  const { data: l1Sessions } = useL1Sessions();
  const { data: l2Facts } = useL2Facts();
  const { data: l3Entries } = useL3Entries();

  const layerCount = useMemo(() => {
    if (!policy) return null;
    if (policy.layer === 'l1') return l1Sessions?.filter((s) => s.status !== 'expired').length ?? 0;
    if (policy.layer === 'l2') return l2Facts?.filter((f) => f.status !== 'retired').length ?? 0;
    return l3Entries?.filter((k) => k.status === 'published').length ?? 0;
  }, [policy, l1Sessions, l2Facts, l3Entries]);

  const otherLayers = useMemo(() => {
    if (!policy) return [] as Array<{ key: string; label: string; count: number | undefined }>;
    const items: Array<{ key: string; label: string; count: number | undefined }> = [];
    if (policy.layer !== 'l1') items.push({ key: 'l1', label: '短期记忆', count: l1Sessions?.filter((s) => s.status !== 'expired').length });
    if (policy.layer !== 'l2') items.push({ key: 'l2', label: '长期记忆', count: l2Facts?.filter((f) => f.status !== 'retired').length });
    if (policy.layer !== 'l3') items.push({ key: 'l3', label: '知识记忆', count: l3Entries?.filter((k) => k.status === 'published').length });
    return items;
  }, [policy, l1Sessions, l2Facts, l3Entries]);


  if (isLoading) {
    return (
      <DetailShell backTo="/admin/memory" backLabel="返回记忆管理">
        <DetailSkeleton rows={3} />
      </DetailShell>
    );
  }
  if (!policy) {
    return (
      <DetailShell backTo="/admin/memory" backLabel="返回记忆管理">
        <DetailNotFound subject="策略不存在或已被删除" />
      </DetailShell>
    );
  }

  const layerBadge = LAYER_LABEL[policy.layer] ?? LAYER_LABEL.l2;
  const eviction = EVICTION_LABEL[policy.eviction] ?? policy.eviction;
  const ttlDisplay = policy.ttlMinutes < 1440
    ? `${policy.ttlMinutes} 分钟`
    : policy.ttlMinutes < 1440 * 30
    ? `${Math.round(policy.ttlMinutes / 1440)} 天`
    : `${Math.round(policy.ttlMinutes / (1440 * 30))} 月`;
  const health = policyHealth(policy.hitRate);
  const usagePct = layerCount !== null && layerCount !== undefined && policy.maxItems > 0
    ? Math.min(100, Math.round((layerCount / policy.maxItems) * 100))
    : 0;
  const storagePct = policy.storageMb > 0 && layerCount !== null && layerCount !== undefined
    ? Math.min(100, Math.round(((layerCount * 0.16) / policy.storageMb) * 100))
    : 0;

  return (
    <DetailShell backTo="/admin/memory" backLabel="返回记忆管理">
      <DetailHeader
        eyebrow={`保留策略 · ${layerBadge.full}`}
        title={policy.label}
        icon={Settings}
        iconClass="bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-200"
        subtitle={policy.description}
        badges={[
          { label: layerBadge.full, className: layerBadge.className },
          { label: `淘汰 ${policy.eviction}`, className: 'bg-[var(--bg-elevated)] text-[var(--text-secondary)]' },
        ]}
      />

      <DetailStatGrid columns={4}>
        <DetailStat label="存活时间" value={ttlDisplay} hint={`${policy.ttlMinutes.toLocaleString()} 分钟`} />
        <DetailStat label="最大条目" value={policy.maxItems.toLocaleString()} />
        <DetailStat label="存储上限" value={`${policy.storageMb}MB`} />
        <DetailStat label="命中率" value={`${(policy.hitRate * 100).toFixed(0)}%`} tone={health.tone} hint={health.label} />
      </DetailStatGrid>

      <DetailSection title="策略参数" icon={Layers}>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <DetailField icon={Layers} label="记忆层级">{layerBadge.full}</DetailField>
          <DetailField icon={Clock} label="存活时间">{ttlDisplay} · {policy.ttlMinutes.toLocaleString()} 分钟</DetailField>
          <DetailField icon={Hash} label="最大条目">{policy.maxItems.toLocaleString()} 条</DetailField>
          <DetailField icon={HardDrive} label="存储上限">{policy.storageMb} MB</DetailField>
          <DetailField icon={Trash2} label="淘汰策略">{eviction}</DetailField>
          <DetailField icon={Percent} label="实际命中率">{(policy.hitRate * 100).toFixed(1)}%</DetailField>
        </div>
      </DetailSection>

      <DetailSection title="策略状态" icon={Activity}>
        <DetailStatGrid columns={4}>
          <DetailStat label="运行状态" value={health.label} tone={health.tone} />
          <DetailStat label="实际命中率" value={`${(policy.hitRate * 100).toFixed(1)}%`} tone={health.tone} />
          <DetailStat label="目标命中率" value="≥ 90%" hint="策略设计目标" />
          <DetailStat label="调整建议" value={health.advice} hint={health.tone === 'success' ? '保持当前配置' : health.tone === 'warn' ? '2 周后复评' : '本周内决策'} />
        </DetailStatGrid>
      </DetailSection>

      <DetailSection title="当前数据量" icon={BarChart3}>
        <div className="space-y-4">
          <div>
            <div className="flex items-center justify-between text-xs text-[var(--text-secondary)]">
              <span className="font-medium">{layerBadge.full} · 本策略对应层级</span>
              <span>
                已用 <span className="font-semibold tabular-nums">{layerCount ?? '—'}</span>
                {' '}/ {policy.maxItems.toLocaleString()}({usagePct}%)
              </span>
            </div>
            <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-[var(--bg-elevated)]">
              <div
                className={`h-full rounded-full ${usagePct >= 90 ? 'bg-rose-500' : usagePct >= 70 ? 'bg-amber-500' : 'bg-emerald-500'}`}
                style={{ width: `${usagePct}%` }}
              />
            </div>
          </div>
          <div>
            <div className="flex items-center justify-between text-xs text-[var(--text-secondary)]">
              <span className="font-medium">存储占用</span>
              <span>
                估算 <span className="font-semibold tabular-nums">{layerCount !== null && layerCount !== undefined ? (layerCount * 0.16).toFixed(1) : '—'}</span>
                {' '}/ {policy.storageMb} MB({storagePct}%)
              </span>
            </div>
            <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-[var(--bg-elevated)]">
              <div className="h-full rounded-full bg-blue-500" style={{ width: `${storagePct}%` }} />
            </div>
          </div>
          {otherLayers.length > 0 && (
            <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {otherLayers.map((o) => (
                <li key={o.key} className="flex items-center justify-between rounded-lg border border-[var(--border)] bg-[var(--bg-app)] px-3 py-2 text-xs">
                  <span className="font-medium text-[var(--text-secondary)]">{o.label}</span>
                  <span className="tabular-nums text-[var(--text-muted)]">{o.count ?? '—'} 条</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </DetailSection>

      <DetailSection title="被以下 Agent 引用" icon={Users}>
        {boundAgents.length === 0 ? (
          <p className="text-xs text-[var(--text-muted)]">暂无 Agent 引用</p>
        ) : (
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {boundAgents.map((a) => (
              <li key={a.id} className="flex items-center justify-between rounded-xl border border-[var(--border)] bg-[var(--bg-app)] px-3 py-2 text-xs">
                <span className="min-w-0 flex-1 truncate">
                  <span className="block font-medium">{a.name}</span>
                  <span className="mt-0.5 block truncate text-[11px] text-[var(--text-muted)]">{a.category}</span>
                </span>
                <Link to={`/admin/agents/${a.id}`} className="shrink-0 text-[var(--brand)] hover:underline">查看 →</Link>
              </li>
            ))}
          </ul>
        )}
      </DetailSection>
    </DetailShell>
  );
}
