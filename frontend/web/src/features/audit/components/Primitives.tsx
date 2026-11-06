/**
 * 基础可视化 — RiskBar(score 0-100)。
 */
export function RiskBar({ score }: { score: number }) {
  const pct = Math.min(100, Math.max(0, score));
  const tone = score >= 80 ? 'bg-rose-500' : score >= 60 ? 'bg-orange-500' : score >= 40 ? 'bg-amber-500' : 'bg-emerald-500';
  return (
    <div className="flex items-center gap-2">
      <div className="relative h-1.5 w-20 overflow-hidden rounded-full bg-[var(--bg-elevated)]">
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-7 text-right text-[10px] tabular-nums">{score}</span>
    </div>
  );
}