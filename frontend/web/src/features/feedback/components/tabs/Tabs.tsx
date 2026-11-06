/**
 * AdminFeedback — 5 个子模块内容。
 * OverviewTab / ListTab / TicketTab / TopicTab / RuleTab。
 */
import { Plus, Search, Smile, ThumbsDown, ThumbsUp, Trash2, User, Clock, Workflow } from 'lucide-react';
import type { Feedback, FeedbackSentiment, FeedbackStatus, RoutingRule, Ticket, TopicCluster } from '../../schema';
import { PRIORITY_BADGE, PRIORITY_FILTER, ROUTING_ACTION_LABEL, SENTIMENT_FILTER, SENTIMENT_META, STATUS_BADGE, STATUS_FILTER } from '../constants';
import { Sparkline } from '@/components/feedback/Sparkline';
import { FeedbackCard } from '../FeedbackCard';

const sentimentIconMap: Record<string, typeof ThumbsUp> = {
  ThumbsUp, ThumbsDown, Smile,
};

interface TicketTabProps {
  tickets: Ticket[];
  onCreate: () => void;
  hideHeaderCreate?: boolean;
}

export function TicketTab({ tickets, onCreate, hideHeaderCreate }: TicketTabProps) {
  return (
    <section className="p-5">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-amber-700 dark:text-amber-300">工单管理</p>
          <h3 className="mt-2 text-lg font-semibold">所有工单</h3>
          <p className="mt-1 text-xs text-[var(--text-muted)]">共 {tickets.length} 张 · 已解决 {tickets.filter((t) => t.status === 'resolved').length}</p>
        </div>
        {!hideHeaderCreate && (
          <button type="button" onClick={onCreate} className="inline-flex h-9 items-center gap-1.5 rounded-xl bg-[var(--brand)] px-3 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]">
            <Plus className="h-3.5 w-3.5" />新建工单
          </button>
        )}
      </div>
      <div className="mt-5 grid gap-3 md:grid-cols-2">
        {tickets.map((tk) => {
          const badge = STATUS_BADGE[tk.status];
          const prio = PRIORITY_BADGE[tk.priority];
          return (
            <article key={tk.id} className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-4 transition hover:border-[var(--brand)]">
              <header className="flex flex-wrap items-center gap-2">
                <h4 className="text-sm font-semibold">{tk.title}</h4>
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${prio.className}`}>{prio.label}优先</span>
                <span className={`ml-auto inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-semibold ${badge.className}`}>
                  <span className={`h-1.5 w-1.5 rounded-full ${badge.dot}`} aria-hidden="true" />{badge.label}
                </span>
              </header>
              <p className="mt-2 line-clamp-2 text-[11px] leading-5 text-[var(--text-muted)]">{tk.description}</p>
              <div className="mt-3 flex flex-wrap items-center gap-3 text-[11px] text-[var(--text-muted)]">
                <span className="rounded-full bg-[var(--bg-elevated)] px-2 py-0.5 font-medium">{tk.topic}</span>
                <span>· {tk.feedbackIds.length} 条关联反馈</span>
                <span className="ml-auto inline-flex items-center gap-1"><User className="h-3 w-3" />{tk.owner}</span>
              </div>
              <div className="mt-3 flex items-center gap-3 text-[11px] text-[var(--text-muted)]">
                <Clock className="h-3 w-3" />{tk.createdAt}
                <span>· 截止 {tk.dueAt}</span>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

interface TopicTabProps {
  topics: TopicCluster[];
  onJumpToTickets: () => void;
}

export function TopicTab({ topics, onJumpToTickets }: TopicTabProps) {
  return (
    <section className="p-5">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-amber-700 dark:text-amber-300">反馈主题</p>
      <h3 className="mt-2 text-lg font-semibold">主题聚类</h3>
      <p className="mt-1 text-xs text-[var(--text-muted)]">根据反馈文本自动聚类,可按主题创建工单或配置规则。</p>
      <div className="mt-5 grid gap-4 md:grid-cols-2">
        {topics.map((t) => {
          const sen = SENTIMENT_META[t.sentiment];
          const SenIcon = sentimentIconMap[sen.icon] ?? Smile;
          return (
            <article key={t.id} className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 transition hover:border-[var(--brand)]">
              <header className="flex items-start gap-3">
                <span className={`grid h-10 w-10 place-items-center rounded-xl ${sen.tone}`}>
                  <SenIcon className="h-5 w-5" />
                </span>
                <div className="min-w-0 flex-1">
                  <h4 className="text-sm font-semibold">{t.name}</h4>
                  <p className="mt-1 line-clamp-2 text-[11px] leading-5 text-[var(--text-muted)]">{t.description}</p>
                </div>
                <Sparkline data={t.trend} stroke={t.sentiment === 'negative' ? '#f43f5e' : '#10b981'} />
              </header>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${sen.tone}`}>{sen.label}</span>
                <span className="rounded-full bg-[var(--bg-elevated)] px-2 py-0.5 text-[10px] font-semibold">{t.count} 条</span>
              </div>
              <ul className="mt-3 space-y-1 text-[11px] text-[var(--text-muted)]">
                {t.recentComments.slice(0, 2).map((c, idx) => <li key={idx}>· {c}</li>)}
              </ul>
              <div className="mt-3 flex items-center gap-2">
                <button type="button" onClick={onJumpToTickets} className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-[var(--brand)] bg-[var(--brand-light)] px-3 py-1.5 text-[11px] font-semibold text-[var(--brand)] hover:bg-white">
                  <Plus className="h-3 w-3" />基于主题建工单
                </button>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

interface RuleTabProps {
  rules: RoutingRule[];
  onCreate: () => void;
  onToggle: (id: string) => void;
  onDelete: (id: string) => void;
  hideHeaderCreate?: boolean;
}

export function RuleTab({ rules, onCreate, onToggle, onDelete, hideHeaderCreate }: RuleTabProps) {
  return (
    <section className="p-5">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-amber-700 dark:text-amber-300">规则模板</p>
          <h3 className="mt-2 text-lg font-semibold">反馈路由规则</h3>
          <p className="mt-1 text-xs text-[var(--text-muted)]">配置主题 / 情感 / 动作 / 目标团队的自动化路由</p>
        </div>
        {!hideHeaderCreate && (
          <button type="button" onClick={onCreate} className="inline-flex h-9 items-center gap-1.5 rounded-xl bg-[var(--brand)] px-3 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]">
            <Plus className="h-3.5 w-3.5" />新建规则
          </button>
        )}
      </div>
      <div className="mt-5 space-y-3">
        {rules.map((r) => (
          <article key={r.id} className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-4">
            <header className="flex flex-wrap items-center gap-2">
              <button type="button" onClick={() => onToggle(r.id)} aria-pressed={r.enabled} className={`relative inline-flex h-5 w-9 items-center rounded-full transition ${r.enabled ? 'bg-[var(--brand)]' : 'bg-[var(--bg-elevated)]'}`}>
                <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition ${r.enabled ? 'translate-x-4' : 'translate-x-0.5'}`} />
              </button>
              <h4 className="text-sm font-semibold">{r.name}</h4>
              <span className="ml-auto flex items-center gap-2">
                <button type="button" onClick={() => onDelete(r.id)} aria-label="删除规则" className="grid h-7 w-7 place-items-center rounded-lg text-[var(--text-muted)] hover:bg-rose-50 hover:text-rose-600">
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </span>
            </header>
            <p className="mt-2 text-[11px] text-[var(--text-muted)]">{r.description}</p>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px]">
              <span className="rounded-lg bg-[var(--bg-elevated)] px-2 py-1 font-semibold">主题:{r.matchTopic}</span>
              <span className="rounded-lg bg-[var(--bg-elevated)] px-2 py-1 font-semibold">情感:{r.matchSentiment === 'all' ? '全部' : SENTIMENT_META[r.matchSentiment].label}</span>
              <span className="rounded-lg bg-[var(--bg-elevated)] px-2 py-1 font-semibold">{ROUTING_ACTION_LABEL[r.action]}</span>
              <span className="ml-auto rounded-lg border border-[var(--border)] px-2 py-1 font-medium">目标:{r.target}</span>
            </div>
          </article>
        ))}
        {rules.length === 0 && (
          <div className="rounded-2xl border border-dashed border-[var(--border)] p-8 text-center">
            <Workflow className="mx-auto h-6 w-6 text-[var(--text-muted)]" />
            <p className="mt-3 text-sm font-semibold">暂无规则</p>
            <p className="mt-1 text-xs text-[var(--text-muted)]">所有规则都已删除。</p>
          </div>
        )}
      </div>
    </section>
  );
}

