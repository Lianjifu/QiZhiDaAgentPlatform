/**
 * KPI 单格 — 颜色块 + Sparkline + 标签 + 数值 + 较昨日 delta。
 */
import { useNavigate } from 'react-router-dom';
import { DeltaDownIcon, DeltaIcon, KPI_ICONS, TONE_CLASS, deltaClass, kpiStroke } from './Primitives';
import { Sparkline } from '@/components/feedback/Sparkline';
import type { KpiTile } from '../schema';

export function KpiTileCard({ tile }: { tile: KpiTile }) {
  const navigate = useNavigate();
  const Icon = KPI_ICONS[tile.iconName] ?? KPI_ICONS.Activity;
  return (
    <button
      type="button"
      onClick={() => navigate(tile.href)}
      className="group flex flex-col gap-3 rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 text-left transition hover:-translate-y-0.5 hover:border-[var(--brand)] hover:shadow-[var(--shadow-sm)]"
    >
      <div className="flex items-start justify-between">
        <span className={`grid h-10 w-10 place-items-center rounded-lg ${TONE_CLASS[tile.tone]}`}>
          <Icon className="h-5 w-5" />
        </span>
        <Sparkline data={tile.sparkline} stroke={kpiStroke(tile.tone)} />
      </div>
      <div>
        <p className="text-xs text-[var(--text-muted)]">{tile.label}</p>
        <p className="mt-1.5 text-2xl font-semibold tracking-tight tabular-nums">{tile.value}</p>
      </div>
      <p className={`inline-flex items-center gap-1 text-xs font-medium ${deltaClass(tile.deltaTone)}`}>
        {tile.deltaTone === 'down' ? <DeltaDownIcon className="h-3.5 w-3.5" /> : <DeltaIcon className="h-3.5 w-3.5" />}
        {tile.delta} 较昨日
      </p>
    </button>
  );
}