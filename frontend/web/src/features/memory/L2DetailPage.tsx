/**
 * L2 长期事实详情 — 路由 /admin/memory/l2/:id
 * Wave 5:4 KPI(去冗余)+ 使用历史 + 同用户其他事实 + 溯源归档。
 */
import { useMemo } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Activity, Hash, Link as LinkIcon, User } from 'lucide-react';
import { useL2Fact, useL2Facts } from './useMemory';
import {
  DetailShell, DetailHeader, DetailStatGrid, DetailStat,
  DetailSection, DetailField, DetailNotFound, DetailSkeleton,
} from '@/components/feedback/DetailLayout';
import { L2_CATEGORY_LABEL, L2_STATUS_BADGE, LAYER_META } from './components/constants';

export default function L2DetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const decoded = useMemo(() => decodeURIComponent(id), [id]);
  const { data: fact, isLoading } = useL2Fact(decoded || null);
  const { data: allL2 } = useL2Facts();
  const meta = LAYER_META.l2;
  const Icon = meta.icon;

  const sameUserFacts = useMemo(() => {
    if (!fact) return [];
    return (allL2 ?? [])
      .filter((f) => f.userName === fact.userName && f.id !== fact.id)
      .slice(0, 4);
  }, [fact, allL2]);

  if (isLoading) {
    return (
      <DetailShell backTo="/admin/memory" backLabel="返回记忆管理">
        <DetailSkeleton rows={3} />
      </DetailShell>
    );
  }
  if (!fact) {
    return (
      <DetailShell backTo="/admin/memory" backLabel="返回记忆管理">
        <DetailNotFound subject="长期事实不存在或已被删除" />
      </DetailShell>
    );
  }

  const status = L2_STATUS_BADGE[fact.status];
  const confPct = Math.round(fact.confidence * 100);
  const confTone = confPct >= 85 ? 'success' : confPct >= 70 ? 'warn' : 'danger';
  const catLabel = L2_CATEGORY_LABEL[fact.category];

  return (
    <DetailShell backTo="/admin/memory" backLabel="返回记忆管理">
      <DetailHeader
        eyebrow="长期记忆 · 事实"
        title={fact.key}
        icon={Icon}
        iconClass="bg-violet-50 text-violet-600 dark:bg-violet-500/15 dark:text-violet-300"
        subtitle={`归属 ${fact.userName} · 置信度 ${confPct}% · 来源 sess-${fact.sourceSession.split('-')[1]?.padStart(3, '0') ?? '000'}`}
        badges={[
          { label: status.label, className: status.className },
          { label: catLabel, className: 'bg-[var(--bg-elevated)] text-[var(--text-secondary)]' },
          ...(fact.promotedToL3 ? [{ label: '已晋升为团队知识', className: 'bg-blue-50 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300' }] : []),
        ]}
      />

      <DetailStatGrid columns={4}>
        <DetailStat label="置信度" value={`${confPct}%`} tone={confTone} hint={`类别 · ${catLabel}`} />
        <DetailStat label="最后使用" value={fact.lastUsed} />
        <DetailStat label="归属用户" value={fact.userName} />
        <DetailStat label="归档时间" value={fact.promotedAt} />
      </DetailStatGrid>

      <DetailSection title="使用历史" icon={Activity}>
        {fact.usageHistory && fact.usageHistory.length > 0 ? (
          <ol className="flex flex-wrap items-center gap-x-2 gap-y-1.5 text-xs text-[var(--text-secondary)]">
            {fact.usageHistory.map((at, idx) => (
              <li key={idx} className="flex items-center gap-2">
                {idx > 0 && <span className="h-px w-4 bg-[var(--border)]" aria-hidden="true" />}
                <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border)] bg-[var(--bg-app)] px-2.5 py-1">
                  <span className={`h-1.5 w-1.5 rounded-full ${idx === 0 ? 'bg-[var(--brand)]' : 'bg-[var(--text-muted)]'}`} aria-hidden="true" />
                  {at}
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-xs text-[var(--text-muted)]">暂无使用记录</p>
        )}
      </DetailSection>

      <DetailSection title="事实内容" icon={Hash}>
        <p className="text-sm leading-7 text-[var(--text-secondary)]">{fact.value}</p>
      </DetailSection>

      <DetailSection title="同用户其他事实" icon={User}>
        {sameUserFacts.length === 0 ? (
          <p className="text-xs text-[var(--text-muted)]">该用户暂无其他事实</p>
        ) : (
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {sameUserFacts.map((f) => {
              const sb = L2_STATUS_BADGE[f.status];
              return (
                <li key={f.id} className="flex items-center justify-between gap-2 rounded-xl border border-[var(--border)] bg-[var(--bg-app)] px-3 py-2 text-xs">
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{f.key}</span>
                    <span className="mt-0.5 block truncate text-[11px] text-[var(--text-muted)]">{f.value}</span>
                  </span>
                  <span className={`shrink-0 inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${sb.className}`}>{sb.label}</span>
                  <Link to={`/admin/memory/l2/${f.id}`} className="shrink-0 text-[var(--brand)] hover:underline">查看 →</Link>
                </li>
              );
            })}
          </ul>
        )}
      </DetailSection>

      <DetailSection title="溯源与归档" icon={LinkIcon}>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <DetailField icon={Hash} label="事实 ID"><code className="text-xs">{fact.id}</code></DetailField>
          <DetailField icon={User} label="归属用户">{fact.userName}</DetailField>
          <DetailField icon={LinkIcon} label="来源会话">
            <Link to={`/admin/memory/l1/${fact.sourceSession}`} className="text-[var(--brand)] hover:underline">
              sess-{fact.sourceSession.split('-')[1]?.padStart(3, '0') ?? '000'}
            </Link>
          </DetailField>
          <DetailField icon={Activity} label="归档时间">{fact.promotedAt}</DetailField>
        </div>
      </DetailSection>
    </DetailShell>
  );
}