/**
 * Admin 新建工单 — 独立页面 /admin/feedback/new
 *
 * 把 CreateTicketModal 的 3 步表单搬到页面形态;
 * 复用 FeedbackDetailPage 一样的 wrapper + 返回 Link + header;
 * 提交成功 navigate('/admin/feedback')。
 * 支持 ?fromFeedback=<id> 自动预填(title/topic/priority/description)。
 */
import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Plus } from 'lucide-react';
import type { FeedbackPriority } from './schema';
import { useCreateFeedbackTicket, useFeedbackList } from './useFeedback';
import { StepIndicator } from './components/Primitives';

export default function FeedbackCreatePage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const fromFeedbackId = params.get('fromFeedback');
  const feedbacksQuery = useFeedbackList();
  const feedbacks = feedbacksQuery.data ?? [];
  const preset = fromFeedbackId ? feedbacks.find((f) => f.id === fromFeedbackId) : undefined;

  const createTicket = useCreateFeedbackTicket();
  const [step, setStep] = useState(1);
  const [title, setTitle] = useState('');
  const [topic, setTopic] = useState('');
  const [priority, setPriority] = useState<FeedbackPriority>('medium');
  const [owner, setOwner] = useState('张敏');
  const [description, setDescription] = useState('');
  const [dueAt, setDueAt] = useState('本周内');

  useEffect(() => {
    if (preset) {
      setTitle(`${preset.topic} 反馈工单`);
      setTopic(preset.topic);
      setPriority(preset.priority);
      setDescription(preset.comment);
    }
  }, [preset?.id]);

  const canNext = title.trim().length > 0 && topic.trim().length > 0;

  const handleCreate = () => {
    createTicket.mutate(
      {
        title: title.trim(),
        feedbackIds: preset ? [preset.id] : [],
        owner,
        priority,
        topic: topic.trim(),
        description: description.trim() || '由管理员手动创建',
        dueAt,
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
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--brand)]">用户反馈 · 工单管理</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">新建工单</h1>
          {preset && (
            <p className="mt-2 max-w-2xl text-xs leading-5 text-[var(--text-muted)]">
              来自反馈「{preset.id}」 · {preset.user} · {preset.topic}
            </p>
          )}
        </div>
        <p className="max-w-sm text-xs leading-5 text-[var(--text-muted)]">
          {step === 1 ? '工单基本信息' : step === 2 ? '处理人与时限' : '确认创建'}
        </p>
      </header>

      <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-6">
        <div className="mb-5 flex items-center gap-2 border-b border-[var(--border)] pb-4">
          <Plus className="h-4 w-4 text-[var(--brand)]" />
          <h2 className="text-sm font-semibold">{step === 1 ? '基本信息' : step === 2 ? '处理人与时限' : '确认信息'}</h2>
        </div>
        <div className="mb-5">
          <StepIndicator current={step} total={3} labels={['基本信息', '处理人与时限', '确认']} />
        </div>

        {step === 1 && (
          <div className="space-y-4">
            <div>
              <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">工单标题</label>
              <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="例如:PII 越权反馈" className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">主题</label>
                <input type="text" value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="例如:PII 越权" className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
              </div>
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">优先级</label>
                <select value={priority} onChange={(e) => setPriority(e.target.value as FeedbackPriority)} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]">
                  <option value="low">低</option>
                  <option value="medium">中</option>
                  <option value="high">高</option>
                  <option value="urgent">紧急</option>
                </select>
              </div>
            </div>
            <div>
              <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">描述</label>
              <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} className="mt-1.5 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 py-2 text-sm outline-none focus:border-[var(--brand)]" />
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">处理人</label>
                <input type="text" value={owner} onChange={(e) => setOwner(e.target.value)} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
              </div>
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">截止时间</label>
                <input type="text" value={dueAt} onChange={(e) => setDueAt(e.target.value)} placeholder="例如:本周内 / 今天 18:00" className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
              </div>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] p-5 text-xs">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">确认信息</p>
            <ul className="mt-3 space-y-1">
              <li>· 标题:<span className="font-semibold">{title}</span></li>
              <li>· 主题:{topic}</li>
              <li>· 优先级:{priority}</li>
              <li>· 处理人:{owner}</li>
              <li>· 截止:{dueAt}</li>
            </ul>
          </div>
        )}

        <div className="mt-6 flex flex-wrap items-center justify-end gap-2 border-t border-[var(--border)] pt-5">
          {step > 1 && <button type="button" onClick={() => setStep((s) => Math.max(1, s - 1))} className="rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold">上一步</button>}
          <Link to="/admin/feedback" className="rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold">取消</Link>
          {step < 3 && <button type="button" onClick={() => setStep((s) => s + 1)} disabled={step === 1 && !canNext} className="rounded-xl bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40">下一步</button>}
          {step === 3 && <button type="button" onClick={handleCreate} disabled={createTicket.isPending} className="rounded-xl bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white disabled:opacity-40">创建工单</button>}
        </div>
      </section>
    </div>
  );
}