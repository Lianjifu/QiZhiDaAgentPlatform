/**
 * AdminRegressions — 5 个子模块内容。
 * OverviewTab / BaselineTab / RiskTab / TimelineTab / AlertTab。
 */
import { AlertTriangle, BellRing, Edit3, Search, Settings, ShieldAlert, ShieldCheck, ShieldQuestion, Trash2 } from 'lucide-react';
import { Mail, MessageSquare, Webhook } from 'lucide-react';
import type { AlertChannel, AlertRule, RegressionRisk, RegressionTrack, TimelineEvent } from '../../schema';
import { CHANNEL_META, RISK_BADGE, RISK_FILTER, STATUS_BADGE, STATUS_FILTER } from '../constants';
import { Delta } from '../Primitives';
import { TrackCard } from '../TrackCard';

const riskIconMap: Record<string, typeof ShieldCheck> = {
  ShieldCheck, ShieldQuestion, AlertTriangle, ShieldAlert,
};
const channelIconMap: Record<string, typeof Mail> = {
  Mail, MessageSquare, Webhook,
};

interface BaselineTabProps {
  tracks: RegressionTrack[];
}

export function BaselineTab({ tracks }: BaselineTabProps) {
  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-indigo-700 dark:text-indigo-300">基线对比</p>
      <h3 className="mt-2 text-lg font-semibold">版本对比详情</h3>
      <p className="mt-1 text-xs text-[var(--text-muted)]">查看每个追踪的基线与当前版本对比指标。</p>
      <div className="mt-5 overflow-x-auto rounded-xl border border-[var(--border)]">
        <table className="w-full text-left text-xs">
          <thead className="bg-[var(--bg-elevated)] text-[var(--text-muted)]">
            <tr>
              <th className="px-3 py-2 font-semibold">追踪</th>
              <th className="px-3 py-2 font-semibold">基线 → 当前</th>
              <th className="px-3 py-2 font-semibold">通过率</th>
              <th className="px-3 py-2 font-semibold">P95 延迟</th>
              <th className="px-3 py-2 font-semibold">单次成本</th>
              <th className="px-3 py-2 font-semibold">评分</th>
              <th className="px-3 py-2 font-semibold">状态</th>
            </tr>
          </thead>
          <tbody>
            {tracks.map((t) => (
              <tr key={t.id} className="border-t border-[var(--border)]">
                <td className="px-3 py-2 font-semibold">{t.name}</td>
                <td className="px-3 py-2 text-[var(--text-muted)]">{t.baselineVersion} → {t.currentVersion}</td>
                <td className="px-3 py-2"><Delta value={t.passRateDelta} /></td>
                <td className="px-3 py-2"><Delta value={t.latencyDelta} suffix=" ms" invertColor /></td>
                <td className="px-3 py-2"><Delta value={t.costDelta} suffix=" ¥" invertColor /></td>
                <td className="px-3 py-2"><Delta value={t.scoreDelta} /></td>
                <td className="px-3 py-2"><span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${STATUS_BADGE[t.status].className}`}><span className={`h-1.5 w-1.5 rounded-full ${STATUS_BADGE[t.status].dot}`} aria-hidden="true" />{STATUS_BADGE[t.status].label}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

interface RiskTabProps {
  tracks: RegressionTrack[];
}

export function RiskTab({ tracks }: RiskTabProps) {
  const filteredTracks = (risk: 'all' | RegressionRisk) => risk === 'all' ? tracks : tracks.filter((t) => t.risk === risk);
  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-indigo-700 dark:text-indigo-300">风险面板</p>
      <h3 className="mt-2 text-lg font-semibold">风险分布</h3>
      <p className="mt-1 text-xs text-[var(--text-muted)]">按风险等级分组的追踪,优先处理「严重」与「高风险」。</p>
      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        {(['critical', 'high', 'medium', 'low'] as RegressionRisk[]).map((risk) => {
          const list = filteredTracks(risk);
          const riskMeta = RISK_BADGE[risk];
          const Icon = riskIconMap[riskMeta.icon] ?? ShieldCheck;
          return (
            <article key={risk} className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-4">
              <header className="flex items-center gap-2">
                <span className={`grid h-9 w-9 place-items-center rounded-lg ${riskMeta.className}`}>
                  <Icon className="h-4 w-4" />
                </span>
                <div>
                  <h4 className="text-sm font-semibold">{riskMeta.label}</h4>
                  <p className="text-[10px] text-[var(--text-muted)]">{list.length} 条追踪</p>
                </div>
              </header>
              <ul className="mt-3 space-y-2">
                {list.length === 0 ? (
                  <li className="rounded-lg border border-dashed border-[var(--border)] px-3 py-2 text-[11px] text-[var(--text-muted)]">无</li>
                ) : list.map((t) => (
                  <li key={t.id} className="rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] p-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold">{t.name}</span>
                      <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${STATUS_BADGE[t.status].className}`}>{STATUS_BADGE[t.status].label}</span>
                    </div>
                    <p className="mt-1 text-[10px] text-[var(--text-muted)]">{t.agent} · {t.notes}</p>
                  </li>
                ))}
              </ul>
            </article>
          );
        })}
      </div>
    </section>
  );
}

interface TimelineTabProps {
  events: TimelineEvent[];
}

export function TimelineTab({ events }: TimelineTabProps) {
  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-indigo-700 dark:text-indigo-300">时间线</p>
      <h3 className="mt-2 text-lg font-semibold">最近事件</h3>
      <p className="mt-1 text-xs text-[var(--text-muted)]">追踪变更、检测告警与基线更新等事件。</p>
      <ol className="relative mt-5 space-y-4 border-l border-[var(--border)] pl-5">
        {events.map((e) => {
          const sevBadge = STATUS_BADGE[e.severity];
          return (
            <li key={e.id} className="relative">
              <span className="absolute -left-[26px] top-1 grid h-5 w-5 place-items-center rounded-full bg-[var(--surface-1)] ring-2 ring-[var(--brand)]">
                <span className="h-2 w-2 rounded-full bg-[var(--brand)]" aria-hidden="true" />
              </span>
              <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-1)] p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${sevBadge.className}`}>
                    <span className={`h-1.5 w-1.5 rounded-full ${sevBadge.dot}`} aria-hidden="true" />{sevBadge.label}
                  </span>
                  <span className="text-xs font-semibold">{e.trackName}</span>
                  <span className="ml-auto text-[11px] text-[var(--text-muted)]">{e.occurredAt}</span>
                </div>
                <p className="mt-1 text-[11px] text-[var(--text-muted)]">{e.message}</p>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

interface AlertTabProps {
  alerts: AlertRule[];
  onToggle: (id: string) => void;
  onDelete: (id: string) => void;
  onEdit: (rule: AlertRule) => void;
}

export function AlertTab({ alerts, onToggle, onDelete, onEdit }: AlertTabProps) {
  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-indigo-700 dark:text-indigo-300">告警规则</p>
          <h3 className="mt-2 text-lg font-semibold">所有告警规则</h3>
          <p className="mt-1 text-xs text-[var(--text-muted)]">共 {alerts.length} 条 · 已启用 {alerts.filter((a) => a.enabled).length}</p>
        </div>
        <button type="button" onClick={() => alerts[0] && onEdit(alerts[0])} disabled={alerts.length === 0} className="inline-flex h-9 items-center gap-1.5 rounded-xl bg-[var(--brand)] px-3 text-xs font-semibold text-white hover:bg-[var(--brand-hover)] disabled:cursor-not-allowed disabled:opacity-40">
          <Settings className="h-3.5 w-3.5" />编辑第一条规则
        </button>
      </div>
      <div className="mt-5 space-y-3">
        {alerts.map((a) => (
          <article key={a.id} className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-4">
            <header className="flex flex-wrap items-center gap-2">
              <button type="button" onClick={() => onToggle(a.id)} aria-pressed={a.enabled} className={`relative inline-flex h-5 w-9 items-center rounded-full transition ${a.enabled ? 'bg-[var(--brand)]' : 'bg-[var(--bg-elevated)]'}`}>
                <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition ${a.enabled ? 'translate-x-4' : 'translate-x-0.5'}`} />
              </button>
              <h4 className="text-sm font-semibold">{a.name}</h4>
              <span className="rounded-full bg-[var(--bg-elevated)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-secondary)]">{a.scope}</span>
              <div className="ml-auto flex items-center gap-2">
                <button type="button" onClick={() => onEdit(a)} aria-label="编辑规则" className="inline-flex items-center gap-1 rounded-lg border border-[var(--border)] px-2.5 py-1 text-[11px] font-semibold hover:border-[var(--brand)]">
                  <Edit3 className="h-3 w-3" />编辑
                </button>
                <button type="button" onClick={() => onDelete(a.id)} aria-label="删除规则" className="grid h-7 w-7 place-items-center rounded-lg text-[var(--text-muted)] hover:bg-rose-50 hover:text-rose-600">
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </header>
            <p className="mt-2 text-[11px] text-[var(--text-muted)]">{a.description}</p>
            <div className="mt-3 flex flex-wrap items-center gap-3 text-[11px]">
              <span className="rounded-lg bg-[var(--bg-elevated)] px-2 py-1 font-semibold">
                {a.metric === 'passRate' ? '通过率' : a.metric === 'latency' ? 'P95 延迟' : a.metric === 'cost' ? '单次成本' : '平均评分'} {a.operator === 'gt' ? '高于' : '低于'} {a.threshold}{a.metric === 'passRate' ? '%' : a.metric === 'latency' ? ' ms' : a.metric === 'cost' ? ' ¥' : ''}
              </span>
              <span className="text-[var(--text-muted)]">冷却 {a.cooldown}</span>
              <div className="ml-auto flex flex-wrap items-center gap-1.5">
                {a.channels.map((c: AlertChannel) => {
                  const meta = CHANNEL_META[c];
                  const Icon = channelIconMap[meta.icon] ?? Mail;
                  return (
                    <span key={c} className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${meta.tone}`}>
                      <Icon className="h-3 w-3" />{meta.label}
                    </span>
                  );
                })}
              </div>
            </div>
          </article>
        ))}
        {alerts.length === 0 && (
          <div className="rounded-2xl border border-dashed border-[var(--border)] p-8 text-center">
            <BellRing className="mx-auto h-6 w-6 text-[var(--text-muted)]" />
            <p className="mt-3 text-sm font-semibold">暂无告警规则</p>
            <p className="mt-1 text-xs text-[var(--text-muted)]">所有规则都已删除。</p>
          </div>
        )}
      </div>
    </section>
  );
}