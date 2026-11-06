/**
 * 配额用量 —— 每个 (模型, 周期) 的真实用量与配置上限 ✓
 * （``GET /api/admin/models/quotas/usage`` ✓）。
 */
import type { QuotaUsage } from '../schema';

function pct(used: number, max: number | null): string {
  if (!max || max <= 0) return '—';
  return `${Math.min(100, Math.round((used / max) * 100))}%`;
}

export function QuotaUsagePanel({ usage, modelName }: { usage: QuotaUsage[]; modelName: (id: string) => string }) {
  if (usage.length === 0) {
    return <p className="px-5 py-10 text-center text-xs text-[var(--text-muted)]">还没有配额用量记录。</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-left text-xs">
        <thead className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-muted)]">
          <tr>
            <th className="px-5 py-3 font-semibold">模型</th>
            <th className="px-5 py-3 font-semibold">周期</th>
            <th className="px-5 py-3 font-semibold">请求</th>
            <th className="px-5 py-3 font-semibold">输入 Token</th>
            <th className="px-5 py-3 font-semibold">输出 Token</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--border)]">
          {usage.map((row) => (
            <tr key={`${row.modelId}-${row.period}`}>
              <td className="px-5 py-3 font-semibold">{modelName(row.modelId)}</td>
              <td className="px-5 py-3 text-[var(--text-secondary)]">
                {row.period}
                <span className="ml-1 text-[var(--text-muted)]">{row.latestPeriodKey}</span>
              </td>
              <td className="px-5 py-3 tabular-nums">
                {row.requests.toLocaleString('zh-CN')}
                <span className="ml-1 text-[var(--text-muted)]">
                  {row.maxRequests ? `/ ${row.maxRequests.toLocaleString('zh-CN')}` : ''}
                </span>
                <span className="ml-1 text-[var(--text-muted)]">{pct(row.requests, row.maxRequests)}</span>
              </td>
              <td className="px-5 py-3 tabular-nums">
                {row.tokensIn.toLocaleString('zh-CN')}
                <span className="ml-1 text-[var(--text-muted)]">
                  {row.maxTokensIn ? `/ ${row.maxTokensIn.toLocaleString('zh-CN')}` : ''}
                </span>
              </td>
              <td className="px-5 py-3 tabular-nums">
                {row.tokensOut.toLocaleString('zh-CN')}
                <span className="ml-1 text-[var(--text-muted)]">
                  {row.maxTokensOut ? `/ ${row.maxTokensOut.toLocaleString('zh-CN')}` : ''}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
