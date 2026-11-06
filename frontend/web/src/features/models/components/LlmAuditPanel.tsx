/**
 * LLM 调用审计 —— 直接读 audit_log 里的 llm.* 事件 ✓
 * （``GET /api/admin/llm/audit`` ✓ → 只读治理表 ✓）。
 */
import type { LlmAuditItem } from '../schema';

function payloadText(item: LlmAuditItem): string {
  const payload = item.payload ?? {};
  const parts: string[] = [];
  if (typeof payload.model_id === 'string') parts.push(`模型 ${payload.model_id}`);
  if (typeof payload.error_class === 'string') parts.push(`错误 ${payload.error_class}`);
  if (typeof payload.latency_ms === 'number') parts.push(`${payload.latency_ms} ms`);
  return parts.join(' · ');
}

export function LlmAuditPanel({ items, total }: { items: LlmAuditItem[]; total: number }) {
  if (items.length === 0) {
    return <p className="px-5 py-10 text-center text-xs text-[var(--text-muted)]">还没有 LLM 调用记录。</p>;
  }
  return (
    <div>
      <ol className="divide-y divide-[var(--border)]">
        {items.map((item) => (
          <li key={item.id} className="flex flex-wrap items-center gap-3 px-5 py-3 text-xs">
            <span className="rounded-lg bg-[var(--bg-elevated)] px-2 py-1 font-semibold">{item.event_type}</span>
            <span className="min-w-0 flex-1 truncate text-[var(--text-secondary)]">
              {payloadText(item) || '—'}
            </span>
            <span className="shrink-0 text-[var(--text-muted)]">{item.created_at ?? '—'}</span>
          </li>
        ))}
      </ol>
      <p className="px-5 py-3 text-[11px] text-[var(--text-muted)]">
        显示最近 {items.length} 条 · 共 {total.toLocaleString('zh-CN')} 条 LLM 调用记录
      </p>
    </div>
  );
}
