/**
 * IncidentTab — 异常事件列表,每行可标记 / 重开。
 */
import type { Incident } from '../../schema';
import { SEVERITY_BADGE } from '../constants';

export function IncidentTab({
  incidents,
  onResolve,
  onReopen,
}: {
  incidents: Incident[];
  /** 标记解决 —— 走 action 端点 ✓ */
  onResolve: (id: string) => void;
  /** 重新打开 —— 走 PATCH ✓（置 resolved=false ✓） */
  onReopen: (id: string) => void;
}) {
  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-sky-700 dark:text-sky-300">异常事件</p>
      <h3 className="mt-2 text-lg font-semibold">异常事件列表</h3>
      <p className="mt-1 text-xs text-[var(--text-muted)]">
        {incidents.length} 个事件 · {incidents.filter((i) => !i.resolved).length} 个未解决
      </p>
      <ol className="mt-5 space-y-3">
        {incidents.map((i) => {
          const badge = SEVERITY_BADGE[i.severity];
          return (
            <li key={i.id} className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
              <header className="flex flex-wrap items-center gap-2">
                <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${badge.className}`}>
                  <span className={`h-1.5 w-1.5 rounded-full ${badge.dot}`} aria-hidden="true" />
                  {badge.label}
                </span>
                <h4 className="text-sm font-semibold">{i.title}</h4>
                <span className="font-mono text-[10px] text-[var(--text-muted)]">{i.sessionId}</span>
                <span
                  className={`ml-auto rounded-full px-2 py-0.5 text-[10px] font-semibold ${i.resolved ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'}`}
                >
                  {i.resolved ? '已解决' : '未解决'}
                </span>
                <button
                  type="button"
                  onClick={() => (i.resolved ? onReopen(i.id) : onResolve(i.id))}
                  className="rounded-lg border border-[var(--border)] px-2 py-1 text-[10px] font-semibold hover:border-[var(--brand)]"
                >
                  {i.resolved ? '重新打开' : '标记解决'}
                </button>
              </header>
              <p className="mt-2 text-[11px] text-[var(--text-muted)]">{i.message}</p>
              <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px]">
                <span className="rounded-lg bg-[var(--bg-elevated)] px-2 py-1 font-medium">用户:{i.affectedUser}</span>
                <span className="rounded-lg bg-[var(--bg-elevated)] px-2 py-1 font-medium">发生:{i.occurredAt}</span>
                <span className="rounded-lg bg-[var(--bg-elevated)] px-2 py-1 font-medium">重试:{i.retryCount} 次</span>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}