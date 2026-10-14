import { useApiQuery } from '@/services/query';
/**
 * Drawer 4 个面板 — 调用概要 / 入参输出 / 命中规则 / 审计日志。
 */
import type { AuditEntry, AuditRule } from '../schema';
import { CATEGORY_META, OUTCOME_BADGE, SEVERITY_BADGE } from './constants';
import { RiskBar } from './Primitives';

export function DrawerPanelOverview({ entry }: { entry: AuditEntry }) {
  const sev = SEVERITY_BADGE[entry.severity];
  const cat = CATEGORY_META[entry.category];
  const Icon = cat.icon;
  const out = OUTCOME_BADGE[entry.outcome];
  return (
    <div className="space-y-5">
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] p-5">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`inline-flex h-9 w-9 items-center justify-center rounded-lg ${cat.tone}`}>
            <Icon className="h-4 w-4" />
          </span>
          <p className="font-mono text-sm font-semibold">{entry.toolName}</p>
          <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-semibold ${sev.className}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${sev.dot}`} aria-hidden="true" />
            {sev.label}
          </span>
          <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${out.className}`}>{out.label}</span>
        </div>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          <div>
            <p className="text-[10px] text-[var(--text-muted)]">调用方</p>
            <p className="mt-1 text-xs font-semibold">{entry.actor}</p>
          </div>
          <div>
            <p className="text-[10px] text-[var(--text-muted)]">会话</p>
            <p className="mt-1 font-mono text-xs font-semibold">{entry.sessionId}</p>
          </div>
          <div>
            <p className="text-[10px] text-[var(--text-muted)]">时间</p>
            <p className="mt-1 text-xs font-semibold">{entry.occurredAt}</p>
          </div>
        </div>
      </div>
      <div className="grid gap-4 sm:grid-cols-4">
        <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] p-3">
          <p className="text-[10px] text-[var(--text-muted)]">风险分</p>
          <div className="mt-1">
            <RiskBar score={entry.riskScore} />
          </div>
        </div>
        <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] p-3">
          <p className="text-[10px] text-[var(--text-muted)]">重试</p>
          <p className="mt-1 text-sm font-semibold tabular-nums">{entry.retryCount}</p>
        </div>
        <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] p-3">
          <p className="text-[10px] text-[var(--text-muted)]">敏感数据</p>
          <p className="mt-1 text-sm font-semibold">{entry.hasSensitive ? '是' : '否'}</p>
        </div>
        <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] p-3">
          <p className="text-[10px] text-[var(--text-muted)]">权限范围</p>
          <p className="mt-1 font-mono text-[10px] font-semibold">{entry.scope}</p>
        </div>
      </div>
    </div>
  );
}

export function DrawerPanelArgs({ entry }: { entry: AuditEntry }) {
  const { data: response } = useApiQuery<unknown>(['audit', entry.id, 'response'], `/api/admin/audit/entries/${entry.id}/response`);
  const responseText = response === undefined ? '暂无返回数据' : JSON.stringify(response, null, 2);
  return (
    <div className="space-y-3">
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] p-4">
        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">入参</p>
        <pre className="mt-1.5 whitespace-pre-wrap rounded-lg bg-[var(--surface-1)] p-3 font-mono text-[11px] leading-6">{entry.args}</pre>
      </div>
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] p-4">
        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">返回摘要</p>
        <pre className="mt-1.5 whitespace-pre-wrap rounded-lg bg-[var(--surface-1)] p-3 font-mono text-[11px] leading-6">{responseText}</pre>
      </div>
    </div>
  );
}

export function DrawerPanelRule({ entry, rules }: { entry: AuditEntry; rules: AuditRule[] }) {
  const matched = rules.filter((r) => r.category === entry.category);
  return (
    <ol className="space-y-2">
      {matched.map((r) => {
        const hit = !!entry.reason && r.id.length > 0;
        return (
          <li
            key={r.id}
            className={`rounded-2xl border p-4 ${hit ? 'border-[var(--brand)] bg-[var(--brand-light)]/40' : 'border-[var(--border)] bg-[var(--surface-1)]'}`}
          >
            <div className="flex items-center gap-2">
              <span className="grid h-7 w-7 place-items-center rounded-md bg-[var(--brand-light)] text-[var(--brand)]">
                <span className="text-[10px] font-semibold">R</span>
              </span>
              <p className="text-xs font-semibold">{r.name}</p>
              <span className={`ml-auto rounded-full px-2 py-0.5 text-[10px] font-semibold ${SEVERITY_BADGE[r.severity].className}`}>
                {SEVERITY_BADGE[r.severity].label}
              </span>
            </div>
            <p className="mt-2 font-mono text-[11px] text-[var(--text-muted)]">
              if {r.condition} → {r.action}
            </p>
            <p className="mt-1.5 text-[11px] text-[var(--text-muted)]">{r.description}</p>
          </li>
        );
      })}
    </ol>
  );
}

export function DrawerPanelLog({ entry }: { entry: AuditEntry }) {
  const { data: logs = [] } = useApiQuery<{ time: string; level: string; text: string }[]>(['detail', `/api/admin/audit/entries/${entry.id}/logs`], `/api/admin/audit/entries/${entry.id}/logs`);
  return (
    <ol className="space-y-1.5">
      {logs.map((l, idx) => (
        <li key={idx} className="flex items-start gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] p-2 font-mono text-[11px]">
          <span className="text-[var(--text-muted)]">{l.time}</span>
          <span
            className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${l.level === 'info' ? 'bg-sky-50 text-sky-700' : l.level === 'warn' ? 'bg-amber-50 text-amber-700' : 'bg-rose-50 text-rose-700'}`}
          >
            {l.level.toUpperCase()}
          </span>
          <span className="flex-1">{l.text}</span>
        </li>
      ))}
    </ol>
  );
}
