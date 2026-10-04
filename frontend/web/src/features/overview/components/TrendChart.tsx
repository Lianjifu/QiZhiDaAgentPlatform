/**
 * 三轴趋势图 — 调用量(面积)+ 可用率 + 错误率,带悬停十字线 + tooltip。
 */
import { useState } from 'react';
import type { TrendSeries } from '../schema';

export function TrendChart({ series }: { series: TrendSeries }) {
  const width = 720;
  const height = 260;
  const padding = { top: 16, right: 56, bottom: 28, left: 48 };
  const data = series.points;
  const calls = data.map((p) => p.calls);
  const success = data.map((p) => p.success);
  const errors = data.map((p) => p.errors);
  const rawMax = calls.length === 0 ? 0 : Math.max(...calls);
  const callsMax = Math.max(1, Math.ceil(rawMax / 20000) * 20000);
  const xCount = Math.max(data.length, 1);
  const xStep = (width - padding.left - padding.right) / Math.max(xCount - 1, 1);
  const xAt = (index: number) => padding.left + index * xStep;
  const yCalls = (value: number) => padding.top + ((callsMax - value) / callsMax) * (height - padding.top - padding.bottom);
  const yPct = (value: number) => padding.top + ((100 - value) / 1) * (height - padding.top - padding.bottom);
  const pathFor = (series: number[], y: (v: number) => number) => series.map((value, index) => `${index === 0 ? 'M' : 'L'} ${xAt(index)} ${y(value)}`).join(' ');
  const callPath = pathFor(calls, yCalls);
  const successPath = pathFor(success, yPct);
  const errorPath = pathFor(errors, yPct);
  const callArea = `${callPath} L ${xAt(xCount - 1)} ${height - padding.bottom} L ${xAt(0)} ${height - padding.bottom} Z`;
  const gridValues = [0, 0.25, 0.5, 0.75, 1];
  const [hover, setHover] = useState<number | null>(null);

  const onMove = (event: React.MouseEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const scale = width / rect.width;
    const localX = (event.clientX - rect.left) * scale;
    const index = Math.round((localX - padding.left) / xStep);
    setHover(Math.min(Math.max(index, 0), xCount - 1));
  };
  const onLeave = () => setHover(null);
  const hoverX = hover == null ? null : xAt(hover);

  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full min-w-0" role="img" aria-label={`${series.range} 调用量与质量趋势`} onMouseMove={onMove} onMouseLeave={onLeave}>
        <defs>
          <linearGradient id="overviewCallFill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="var(--brand)" stopOpacity="0.22" />
            <stop offset="100%" stopColor="var(--brand)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {gridValues.map((g) => {
          const y = padding.top + g * (height - padding.top - padding.bottom);
          return <g key={g}>
            <line x1={padding.left} x2={width - padding.right} y1={y} y2={y} stroke="var(--chart-grid)" strokeDasharray="3 5" />
            <text x={padding.left - 8} y={y + 4} textAnchor="end" fill="var(--text-muted)" fontSize="11">{(callsMax * (1 - g) / 1000).toFixed(0)}k</text>
          </g>;
        })}
        <text x={padding.left} y={padding.top - 4} fill="var(--text-muted)" fontSize="10">调用量</text>
        <text x={width - padding.right} y={padding.top - 4} textAnchor="end" fill="var(--text-muted)" fontSize="10">可用率 / 错误率 %</text>
        <path d={callArea} fill="url(#overviewCallFill)" />
        <path d={callPath} fill="none" stroke="var(--brand)" strokeWidth="2.5" strokeLinecap="round" />
        <path d={successPath} fill="none" stroke="var(--chart-success)" strokeWidth="2" strokeLinecap="round" />
        <path d={errorPath} fill="none" stroke="var(--danger)" strokeWidth="2" strokeLinecap="round" />
        {data.map((point, index) => (
          <text key={point.label} x={xAt(index)} y={height - 10} textAnchor="middle" fill="var(--text-muted)" fontSize="11">{point.label}</text>
        ))}
        {hoverX != null && (
          <line x1={hoverX} x2={hoverX} y1={padding.top} y2={height - padding.bottom} stroke="var(--border-strong)" strokeDasharray="2 3" />
        )}
        {hover != null && (
          <g>
            <circle cx={xAt(hover)} cy={yCalls(calls[hover])} r="5" fill="var(--surface-1)" stroke="var(--brand)" strokeWidth="2.5" />
            <circle cx={xAt(hover)} cy={yPct(success[hover])} r="4" fill="var(--surface-1)" stroke="var(--chart-success)" strokeWidth="2" />
            <circle cx={xAt(hover)} cy={yPct(errors[hover])} r="4" fill="var(--surface-1)" stroke="var(--danger)" strokeWidth="2" />
          </g>
        )}
      </svg>
      {hover != null && (
        <div className="mt-3 flex flex-wrap items-center gap-4 rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] px-4 py-3 text-xs">
          <span className="font-semibold tabular-nums">{data[hover].label}</span>
          <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-[var(--brand)]" />调用量 {calls[hover].toLocaleString()}</span>
          <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-[var(--chart-success)]" />可用率 {success[hover].toFixed(2)}%</span>
          <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-[var(--danger)]" />错误率 {errors[hover].toFixed(2)}%</span>
        </div>
      )}
    </div>
  );
}