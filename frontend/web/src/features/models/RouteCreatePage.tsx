/**
 * 新建路由规则 — 独立页面 /admin/models/routes/new
 */
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, Filter } from 'lucide-react';
import type { RouteStrategy, TaskType } from './schema';
import { useCreateRoute, useModelsList } from './useModels';
import { STRATEGY_LABEL, TASK_LABEL } from './components/constants';
import { AdminPage } from '@/components/feedback/AdminPage';

const TASK_OPTIONS: TaskType[] = ['reasoning', 'generation', 'classification', 'embedding', 'summarization'];
const STRATEGY_OPTIONS: RouteStrategy[] = ['quality-first', 'cost-first', 'latency-first', 'fallback'];

export default function RouteCreatePage() {
  const navigate = useNavigate();
  const { data: models = [] } = useModelsList();
  const createRoute = useCreateRoute();
  const [name, setName] = useState('');
  const [task, setTask] = useState<TaskType>('reasoning');
  const [strategy, setStrategy] = useState<RouteStrategy>('quality-first');
  const [priority, setPriority] = useState(50);
  const [primaryModelId, setPrimaryModelId] = useState('');
  const [description, setDescription] = useState('');
  const resolvedModelId = primaryModelId || models[0]?.id || '';
  const canSubmit = name.trim().length > 0 && resolvedModelId.length > 0 && !createRoute.isPending;

  return (
    <AdminPage density="lg">
      <Link to="/admin/models" className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--brand)]">
        <ArrowLeft className="h-3.5 w-3.5" />返回模型配置
      </Link>
      <header>
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--brand)]">模型配置</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">新建路由规则</h1>
        <p className="mt-2 max-w-2xl text-sm text-[var(--text-muted)]">为指定任务配置主模型与降级链。</p>
      </header>
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-6">
        <div className="mb-5 flex items-center gap-2 border-b border-[var(--border)] pb-4">
          <Filter className="h-4 w-4 text-[var(--brand)]" />
          <h2 className="text-sm font-semibold">路由配置</h2>
        </div>
        <form
          className="grid gap-4 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!canSubmit) return;
            createRoute.mutate(
              { name: name.trim(), task, strategy, priority, primaryModelId: resolvedModelId, description: description.trim() || '由管理员手动创建' },
              { onSuccess: () => navigate('/admin/models'), onError: () => navigate('/admin/models') },
            );
          }}
        >
          <div>
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">规则名称</label>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="例如:推理任务 · 质量优先" className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
          </div>
          <div>
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">任务类型</label>
            <select value={task} onChange={(e) => setTask(e.target.value as TaskType)} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]">
              {TASK_OPTIONS.map((t) => <option key={t} value={t}>{TASK_LABEL[t]}</option>)}
            </select>
          </div>
          <div>
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">策略</label>
            <select value={strategy} onChange={(e) => setStrategy(e.target.value as RouteStrategy)} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]">
              {STRATEGY_OPTIONS.map((s) => <option key={s} value={s}>{STRATEGY_LABEL[s]}</option>)}
            </select>
          </div>
          <div>
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">优先级</label>
            <input type="number" value={priority} onChange={(e) => setPriority(Number(e.target.value))} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
          </div>
          <div className="sm:col-span-2">
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">主模型</label>
            <select value={resolvedModelId} onChange={(e) => setPrimaryModelId(e.target.value)} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]">
              {models.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          </div>
          <div className="sm:col-span-2">
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">说明</label>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} className="mt-1.5 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 py-2 text-sm outline-none focus:border-[var(--brand)]" />
          </div>
          <div className="sm:col-span-2 flex justify-end gap-2 border-t border-[var(--border)] pt-5">
            <Link to="/admin/models" className="rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold">取消</Link>
            <button type="submit" disabled={!canSubmit} className="rounded-xl bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white disabled:opacity-40">创建规则</button>
          </div>
        </form>
      </section>
    </AdminPage>
  );
}
