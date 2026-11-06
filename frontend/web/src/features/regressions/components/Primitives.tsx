/**
 * AdminRegressions — 可视化基元。
 * Sparkline (SVG 折线图)、StepIndicator (wizard 进度条)、Delta (带 +/- 方向感的色块)。
 */
import { ArrowDown, ArrowUp, CircleAlert } from 'lucide-react';



export function StepIndicator({ current, total, labels }: { current: number; total: number; labels: string[] }) {
  return (
    <div className="flex items-center gap-2">
      {Array.from({ length: total }).map((_, idx) => {
        const stepNum = idx + 1;
        const isActive = stepNum === current;
        const isDone = stepNum < current;
        return (
          <div key={stepNum} className="flex items-center gap-2">
            <div className="flex items-center gap-2">
              <span className={`grid h-6 w-6 place-items-center rounded-full text-[10px] font-semibold ${isActive || isDone ? 'bg-[var(--brand)] text-white' : 'bg-[var(--bg-elevated)] text-[var(--text-muted)]'}`}>{stepNum}</span>
              <span className={`text-[11px] font-medium ${isActive ? 'text-[var(--brand)]' : 'text-[var(--text-muted)]'}`}>{labels[idx]}</span>
            </div>
            {stepNum < total && <span className={`h-px w-8 ${isDone ? 'bg-[var(--brand)]' : 'bg-[var(--border)]'}`} />}
          </div>
        );
      })}
    </div>
  );
}

export function Delta({ value, suffix = '%', invertColor = false }: { value: number; suffix?: string; invertColor?: boolean }) {
  const positive = invertColor ? value < 0 : value > 0;
  const negative = invertColor ? value > 0 : value < 0;
  const tone = value === 0
    ? 'bg-[var(--bg-elevated)] text-[var(--text-muted)]'
    : positive
      ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300'
      : negative
        ? 'bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300'
        : 'bg-[var(--bg-elevated)] text-[var(--text-muted)]';
  const Icon = value > 0 ? ArrowUp : value < 0 ? ArrowDown : CircleAlert;
  const sign = value > 0 ? '+' : '';
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${tone}`}>
      <Icon className="h-3 w-3" />{sign}{value.toFixed(1)}{suffix}
    </span>
  );
}