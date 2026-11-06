/**
 * 相对时间 ✓ —— 「刚刚 / 3 分钟前 / 昨天 / 11月5日」✓。
 *
 * ⚠️ **会话列表原来直接显示 ISO 串** ✓（``2026-11-06T12:04:26.498470+00:00``
 * ✓ —— 没人看得懂 ✗✗）。
 */
export function formatRelativeTime(iso?: string | null): string {
  if (!iso) return '';
  const ts = Date.parse(iso);
  if (!Number.isFinite(ts)) return '';
  const diff = Date.now() - ts;
  if (diff < 0) return '刚刚';
  if (diff < 60_000) return '刚刚';
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`;
  if (diff < 2 * 86_400_000) return '昨天';
  if (diff < 7 * 86_400_000) return `${Math.floor(diff / 86_400_000)} 天前`;
  const date = new Date(ts);
  return `${date.getMonth() + 1}月${date.getDate()}日`;
}

/** 毫秒 → 「3.2s」✓（小于 1 秒按「<1s」✓ —— 别显示 0.0s ✓）。 */
export function formatDuration(ms?: number | null): string {
  if (ms == null || !Number.isFinite(ms)) return '';
  if (ms < 1000) return '<1s';
  return `${(ms / 1000).toFixed(1)}s`;
}
