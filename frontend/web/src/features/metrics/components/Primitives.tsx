/**
 * Primitives — Sparkline(120x28) + LatencyChart(560x160 三分位曲线)。
 */
import type { LatencyPercentile, LatencyPoint } from '../schema';

const PERCENTILE_STROKE: Record<LatencyPercentile, string> = {
  p50: 'var(--chart-success)',
  p95: 'var(--chart-warning)',
  p99: 'var(--danger)',
};

export function LatencyChart({ data, metric }: { data: LatencyPoint[]; metric: LatencyPercentile }) {
  const width = 560;
  const height = 160;
  const padX = 30;
  const padY = 16;
  const all = data.map((d) => d[metric]);
  const max = Math.max(...all);
  const min = Math.min(...all);
  const range = Math.max(max - min, 1);
  const x = (i: number) => padX + (i * (width - padX * 2)) / Math.max(data.length - 1, 1);
  const y = (v: number) => padY + ((max - v) / range) * (height - padY * 2);
  const path = data.map((d, i) => `${i === 0 ? 'M' : 'L'} ${x(i)} ${y(d[metric])}`).join(' ');
  const area = `${path} L ${x(data.length - 1)} ${height - padY} L ${x(0)} ${height - padY} Z`;
  const stroke = PERCENTILE_STROKE[metric];
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-44 w-full" preserveAspectRatio="none" aria-label={`延迟曲线 ${metric}`}>
      <path d={area} fill={stroke} fillOpacity="0.08" />
      <path d={path} fill="none" stroke={stroke} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      {data.map((d, i) => i % 4 === 0 ? (
        <g key={i}>
          <line x1={x(i)} x2={x(i)} y1={height - padY} y2={height - padY + 4} stroke="var(--text-muted)" strokeWidth="0.6" />
          <text x={x(i)} y={height - 4} fontSize="9" textAnchor="middle" fill="var(--text-muted)">{d.t}</text>
        </g>
      ) : null)}
    </svg>
  );
}