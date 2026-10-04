/**
 * Admin 新建规则模板 — 独立页面 /admin/feedback/rules/new
 *
 * 把 CreateRuleModal 的单页表单搬到页面形态;
 * 复用 FeedbackDetailPage 一样的 wrapper + 返回 Link + header;
 * 提交成功 navigate('/admin/feedback')。
 */
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Workflow } from 'lucide-react';
import type { FeedbackSentiment, RoutingAction } from './schema';
import { ROUTING_ACTION_LABEL } from './components/constants';
import { useCreateFeedbackRule } from './useFeedback';

export default function FeedbackRuleCreatePage() {
  const navigate = useNavigate();
  const createRule = useCreateFeedbackRule();
  const [name, setName] = useState('');
  const [topic, setTopic] = useState('');
  const [sentiment, setSentiment] = useState<FeedbackSentiment | 'all'>('all');
  const [action, setAction] = useState<RoutingAction>('create-ticket');
  const [target, setTarget] = useState('内容团队');
  const [description, setDescription] = useState('');

  const canSubmit = name.trim().length > 0 && topic.trim().length > 0;

  const handleCreate = () => {
    if (!canSubmit || createRule.isPending) return;
    createRule.mutate(
      {
        name: name.trim(),
        matchTopic: topic.trim(),
        matchSentiment: sentiment,
        action,
        target: target.trim(),
        enabled: true,
        description: description.trim() || '管理员手动创建',
      },
      { onSuccess: () => navigate('/admin/feedback'), onError: () => navigate('/admin/feedback') },
    );
  };

  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-6 p-5 pb-16 sm:p-8 xl:px-10">
      <Link to="/admin/feedback" className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--brand)]">
        <span aria-hidden="true">←</span>返回用户反馈
      </Link>

      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--brand)]">用户反馈 · 规则模板</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">新建规则模板</h1>
        </div>
        <p className="max-w-sm text-xs leading-5 text-[var(--text-muted)]">设置主题、情感、动作与目标团队</p>
      </header>

      <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-6">
        <div className="mb-5 flex items-center gap-2 border-b border-[var(--border)] pb-4">
          <Workflow className="h-4 w-4 text-[var(--brand)]" />
          <h2 className="text-sm font-semibold">规则信息</h2>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">规则名称</label>
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="例如:PII 越权自动派单" className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
          </div>
          <div>
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">匹配主题</label>
            <input type="text" value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="例如:PII 越权" className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
          </div>
          <div>
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">情感</label>
            <select value={sentiment} onChange={(e) => setSentiment(e.target.value as FeedbackSentiment | 'all')} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]">
              <option value="all">全部</option>
              <option value="positive">正面</option>
              <option value="neutral">中性</option>
              <option value="negative">负面</option>
            </select>
          </div>
          <div>
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">动作</label>
            <select value={action} onChange={(e) => setAction(e.target.value as RoutingAction)} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]">
              {(Object.keys(ROUTING_ACTION_LABEL) as RoutingAction[]).map((a) => (
                <option key={a} value={a}>{ROUTING_ACTION_LABEL[a]}</option>
              ))}
            </select>
          </div>
          <div className="sm:col-span-2">
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">目标团队</label>
            <input type="text" value={target} onChange={(e) => setTarget(e.target.value)} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
          </div>
          <div className="sm:col-span-2">
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">说明</label>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} className="mt-1.5 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 py-2 text-sm outline-none focus:border-[var(--brand)]" />
          </div>
        </div>

        <div className="mt-6 flex flex-wrap items-center justify-end gap-2 border-t border-[var(--border)] pt-5">
          <Link to="/admin/feedback" className="rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold">取消</Link>
          <button type="button" onClick={handleCreate} disabled={!canSubmit || createRule.isPending} className="rounded-xl bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40">创建规则</button>
        </div>
      </section>
    </div>
  );
}