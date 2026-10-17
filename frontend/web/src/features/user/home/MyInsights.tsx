import { useApiQuery } from '@/services/query';
import { ArrowUpRight, BarChart3, CheckCircle2, ChevronDown, Clock3, Download, FileText, Gauge, MoreHorizontal, Sparkles, Target, TrendingUp } from 'lucide-react';
import { useMemo, useState } from 'react';
import { NoticeBanner } from '@/components/feedback/NoticeBanner';
import { TimeRangeDropdown } from '@/components/TimeRangeDropdown';
import { PageIntro, WorkspacePage } from '../components';

type Range = '近 7 天' | '近 30 天' | '本季度';
const INSIGHT_RANGES: { id: Range; label: string }[] = [
  { id: '近 7 天', label: '近 7 天' },
  { id: '近 30 天', label: '近 30 天' },
  { id: '本季度', label: '本季度' },
];

type TrendPoint = { label: string; value: number; tasks: number };

function TrendChart({ points, showTable }: { points: TrendPoint[]; showTable: boolean }) {
  const width = 720;
  const height = 240;
  const padding = { top: 24, right: 20, bottom: 38, left: 42 };
  const max = 100;
  const x = (index: number) => padding.left + (index * (width - padding.left - padding.right)) / Math.max(points.length - 1, 1);
  const y = (value: number) => padding.top + ((max - value) * (height - padding.top - padding.bottom)) / max;
  const line = points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${x(index)} ${y(point.value)}`).join(' ');
  const area = `${line} L ${x(points.length - 1)} ${height - padding.bottom} L ${x(0)} ${height - padding.bottom} Z`;
  const gridValues = [0, 25, 50, 75, 100];

  return (
    <div>
      {showTable ? (
        <div className="overflow-hidden rounded-xl border border-[var(--border)]">
          <table className="w-full text-left text-xs">
            <caption className="sr-only">智能体任务完成率趋势数据</caption>
            <thead className="bg-[var(--bg-elevated)] text-[var(--text-muted)]">
              <tr>
                <th className="px-4 py-3 font-medium">时间</th>
                <th className="px-4 py-3 font-medium">完成率</th>
                <th className="px-4 py-3 font-medium">完成任务</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border)]">
              {points.map((point, index) => (
                <tr key={`${point.label}-${index}`}>
                  <td className="px-4 py-3 font-medium">{point.label}</td>
                  <td className="px-4 py-3">{point.value}%</td>
                  <td className="px-4 py-3 text-[var(--text-muted)]">{point.tasks} 次</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="overflow-x-auto" role="img" aria-label="智能体任务完成率趋势图">
          <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full min-w-0" preserveAspectRatio="none">
            <defs>
              <linearGradient id="insightTrendFill" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor="var(--brand)" stopOpacity="0.24" />
                <stop offset="100%" stopColor="var(--brand)" stopOpacity="0" />
              </linearGradient>
            </defs>
            {gridValues.map((value) => (
              <g key={value}>
                <line x1={padding.left} x2={width - padding.right} y1={y(value)} y2={y(value)} stroke="var(--border)" strokeDasharray="3 5" />
                <text x={padding.left - 10} y={y(value) + 4} textAnchor="end" fill="var(--text-muted)" fontSize="11">{value}%</text>
              </g>
            ))}
            <path d={area} fill="url(#insightTrendFill)" />
            <path d={line} fill="none" stroke="var(--brand)" strokeLinecap="round" strokeWidth="3" />
            {points.map((point, index) => (
              <g key={`${point.label}-${index}`}>
                <circle cx={x(index)} cy={y(point.value)} r="8" fill="var(--surface-1)" stroke="var(--brand)" strokeWidth="3" tabIndex={0}>
                  <title>{`${point.label}：${point.value}% · ${point.tasks} 次任务`}</title>
                </circle>
                <text x={x(index)} y={height - 12} textAnchor="middle" fill="var(--text-muted)" fontSize="11">{point.label}</text>
              </g>
            ))}
          </svg>
        </div>
      )}
    </div>
  );
}

export default function MyInsights({ embedded = false }: { embedded?: boolean }) {
  const [range, setRange] = useState<Range>('近 7 天');
  const [showTable, setShowTable] = useState(false);
  const [notice, setNotice] = useState('');
  const query = useApiQuery<{ points: TrendPoint[]; scenarios: Array<{ label: string; value: number; detail: string; color: string }>; outcomes: Array<{ title: string; meta: string; type: string; status: string }>; savedHours?: number }>(['user', 'insights', range], '/api/home/insights', { query: { range } });
  const points = query.data?.points ?? [];
  const scenarios = query.data?.scenarios ?? [];
  const outcomes = query.data?.outcomes ?? [];
  const average = Math.round(points.reduce((sum, point) => sum + point.value, 0) / Math.max(points.length, 1));
  const totalTasks = points.reduce((sum, point) => sum + point.tasks, 0);
  const bestDay = useMemo(() => points.reduce((best, point) => (point.value > best.value ? point : best), points[0] ?? { label: '暂无数据', value: 0, tasks: 0 }), [points]);

  const intro = (
    <PageIntro
      title={embedded ? '效果摘要' : '效果看板'}
      description="智能体与工作流近期完成情况与效率。"
      meta={<span>范围：{range}</span>}
      actions={
        <>
          <TimeRangeDropdown value={range} onChange={setRange} options={INSIGHT_RANGES} />
          <button
            type="button"
            onClick={() => {
              if (!query.data) { setNotice('暂无数据可导出。'); return; }
              const url = URL.createObjectURL(new Blob([JSON.stringify(query.data, null, 2)], { type: 'application/json' }));
              const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'insights.json'; anchor.click(); URL.revokeObjectURL(url);
            }}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--border)] px-3 text-xs font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]"
          >
            <Download className="h-3.5 w-3.5" />{embedded ? '导出摘要' : '导出报告'}
          </button>
        </>
      }
    />
  );

  const body = (
    <>
      {embedded ? (
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-6">{intro}</div>
      ) : (
        <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-6">{intro}</section>
      )}
      {notice && <NoticeBanner tone="emerald" onClose={() => setNotice('')}>{notice}</NoticeBanner>}
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs text-[var(--text-muted)]">完成任务</span>
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-[var(--brand-light)] text-[var(--brand)]"><CheckCircle2 className="h-4 w-4" /></span>
          </div>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{totalTasks}</p>
          <p className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-emerald-600"><ArrowUpRight className="h-3.5 w-3.5" /></p>
        </div>
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs text-[var(--text-muted)]">平均完成率</span>
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-emerald-50 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-300"><Gauge className="h-4 w-4" /></span>
          </div>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{average}%</p>
          <p className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-emerald-600"><ArrowUpRight className="h-3.5 w-3.5" /></p>
        </div>
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs text-[var(--text-muted)]">预计节省</span>
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-amber-50 text-amber-600 dark:bg-amber-500/15 dark:text-amber-300"><Clock3 className="h-4 w-4" /></span>
          </div>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{query.data?.savedHours ?? 0}<span className="ml-1 text-base font-medium">小时</span></p>
          <p className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-emerald-600"><ArrowUpRight className="h-3.5 w-3.5" /></p>
        </div>
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs text-[var(--text-muted)]">活跃场景</span>
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-sky-50 text-sky-600 dark:bg-sky-500/15 dark:text-sky-300"><Target className="h-4 w-4" /></span>
          </div>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{scenarios.length}</p>
          <p className="mt-2 text-xs text-[var(--text-muted)]">最近表现最好：{bestDay.label}</p>
        </div>
      </section>
      <div className="grid min-w-0 gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,0.65fr)]">
        <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <TrendingUp className="h-5 w-5 text-[var(--brand)]" />
                <h3 className="text-base font-semibold">任务完成率趋势</h3>
              </div>
              <p className="mt-1 text-xs text-[var(--text-muted)]">完成任务 ÷ 发起任务 · 单位：百分比</p>
            </div>
            <button
              type="button"
              onClick={() => setShowTable((value) => !value)}
              className="inline-flex items-center gap-2 rounded-lg border border-[var(--border)] px-3 py-2 text-xs font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]"
              aria-pressed={showTable}
            >
              {showTable ? '查看趋势图' : '查看数据表'}
              <ChevronDown className={`h-3.5 w-3.5 transition ${showTable ? 'rotate-180' : ''}`} />
            </button>
          </div>
          <div className="mt-6">{points.length ? <TrendChart points={points} showTable={showTable} /> : <p className="text-sm text-[var(--text-muted)]">暂无数据</p>}</div>
        </section>
        <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-6">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-base font-semibold">场景效率</h3>
              <p className="mt-1 text-xs text-[var(--text-muted)]">按完成率排序</p>
            </div>
            <BarChart3 className="h-5 w-5 text-[var(--brand)]" />
          </div>
          <div className="mt-6 space-y-5">
            {scenarios.map((item, index) => (
              <div key={`${item.label}-${index}`}>
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold">{item.label}</span>
                  <span className="tabular-nums text-[var(--text-muted)]">{item.value}%</span>
                </div>
                <div className="mt-2 h-2 rounded-full bg-[var(--bg-hover)]">
                  <div className={`h-2 rounded-full ${item.color}`} style={{ width: `${item.value}%` }} />
                </div>
                <p className="mt-1.5 text-[11px] text-[var(--text-muted)]">{item.detail}</p>
              </div>
            ))}
          </div>
        </section>
      </div>
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
        <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-4 sm:px-6">
          <div>
            <h3 className="flex items-center gap-2 text-base font-semibold"><Sparkles className="h-4 w-4 text-[var(--brand)]" />最近成果</h3>
            <p className="mt-1 text-xs text-[var(--text-muted)]">智能体与工作流最近留下的结果</p>
          </div>
          <button type="button" className="rounded-lg p-2 text-[var(--text-muted)] hover:bg-[var(--bg-hover)]" aria-label="更多成果">
            <MoreHorizontal className="h-4 w-4" />
          </button>
        </div>
        <div className="grid divide-y divide-[var(--border)] md:grid-cols-3 md:divide-x md:divide-y-0">
          {outcomes.map((item, index) => (
            <div key={`outcome-${index}-${item.type}`} className="flex items-center gap-3 px-5 py-4 sm:px-6">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[var(--bg-elevated)] text-[var(--brand)]">
                <FileText className="h-4 w-4" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold">{item.title}</p>
                <p className="mt-1 truncate text-xs text-[var(--text-muted)]">{item.meta}</p>
              </div>
              <span className="shrink-0 rounded-full bg-[var(--success-bg)] px-2 py-1 text-[10px] font-semibold text-[var(--success)]">{item.status}</span>
            </div>
          ))}
        </div>
      </section>
    </>
  );

  if (embedded) {
    return <div className="w-full space-y-6">{body}</div>;
  }

  return <WorkspacePage>{body}</WorkspacePage>;
}
