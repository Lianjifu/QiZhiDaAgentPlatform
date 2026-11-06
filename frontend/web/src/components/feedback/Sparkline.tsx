/**
 * 管理台迷你折线 —— 10 个管理域各抄了一份 ✓（只差宽高 ✓）。
 */

export interface SparklineProps {
  data: number[];
  stroke: string;
  width?: number;
  height?: number;
  className?: string;
}

export function Sparkline({
  data,
  stroke,
  width = 96,
  height = 28,
  className = 'h-7 w-24',
}: SparklineProps) {
  if (data.length === 0) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = Math.max(max - min, 0.01);
  const x = (index: number) => (index * width) / Math.max(data.length - 1, 1);
  const y = (value: number) => height - ((value - min) / range) * height;
  const line = data.map((value, index) => `${index === 0 ? 'M' : 'L'} ${x(index)} ${y(value)}`).join(' ');
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className={className} preserveAspectRatio="none" aria-hidden="true">
      <path
        d={line}
        fill="none"
        stroke={stroke}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
