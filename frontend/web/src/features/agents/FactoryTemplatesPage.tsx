/**
 * Phase 23: agent_factory templates 列表 — /admin/agents/factory
 *
 * 列 workspace 内所有 agent_template, 顶部「新建」按钮跳 /admin/agents/factory/new.
 * 点行跳 /admin/agents/factory/:id 看详情 + 版本列表.
 *
 * 与现有 /admin/agents (CatalogAgent 列表) 并行, 不替代. 用户可在导航里
 * 切换「标准智能体」vs「策略智能体 (Phase 23)」
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bot, Loader2, Plus, Search, Sparkles } from 'lucide-react';
import {
  useTemplatesList,
  useCreateTemplate,
  type AgentTemplate,
} from './useAgentFactory';

function formatTime(iso: string): string {
  if (!iso) return '—';
  const t = new Date(iso);
  return Number.isNaN(t.getTime()) ? iso : t.toLocaleString('zh-CN');
}

export default function FactoryTemplatesPage() {
  const navigate = useNavigate();
  const { data: wrapped, isLoading, error } = useTemplatesList();
  const templates = wrapped?.items;
  const [search, setSearch] = useState('');
  const [showCreate, setShowCreate] = useState(false);

  const filtered = (templates ?? []).filter((t) => {
    if (!search.trim()) return true;
    const q = search.trim().toLowerCase();
    return t.name.toLowerCase().includes(q) || t.description.toLowerCase().includes(q);
  });

  return (
    <div className="space-y-6 p-6">
      <header className="flex items-start justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold text-[var(--text)]">
            <Sparkles className="h-5 w-5 text-[var(--brand)]" aria-hidden="true" />
            策略智能体 · agent_factory
          </h1>
          <p className="mt-1 text-xs text-[var(--text-muted)]">
            创建带策略路由的智能体 (Phase 15+). 走 release gate → 推送到 catalog.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowCreate(true)}
          className="inline-flex items-center gap-1.5 rounded-xl bg-[var(--brand)] px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-[var(--brand-hover)]"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          新建模板
        </button>
      </header>

      <div className="flex items-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface-1)] px-3 py-2">
        <Search className="h-4 w-4 text-[var(--text-muted)]" aria-hidden="true" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="搜索模板名 / 描述"
          aria-label="搜索模板"
          className="h-7 flex-1 bg-transparent text-sm outline-none placeholder:text-[var(--text-muted)]"
        />
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center gap-2 py-12 text-[var(--text-muted)]">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          <span className="text-xs">加载中…</span>
        </div>
      ) : error ? (
        <div className="rounded-xl border border-rose-300 bg-rose-50 p-4 text-sm text-rose-700">
          加载失败,请刷新重试。
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState onCreate={() => setShowCreate(true)} hasSearch={!!search.trim()} />
      ) : (
        <TemplateTable
          templates={filtered}
          onOpen={(t) => navigate(`/admin/agents/factory/${t.id}`)}
        />
      )}

      {showCreate ? (
        <CreateTemplateModal
          onClose={() => setShowCreate(false)}
          onCreated={(t) => {
            setShowCreate(false);
            navigate(`/admin/agents/factory/${t.id}`);
          }}
        />
      ) : null}
    </div>
  );
}

function EmptyState({ onCreate, hasSearch }: { onCreate: () => void; hasSearch: boolean }) {
  return (
    <div className="rounded-2xl border border-dashed border-[var(--border)] bg-[var(--surface-1)] py-16 text-center">
      <Bot className="mx-auto h-10 w-10 text-[var(--text-muted)]" aria-hidden="true" />
      <p className="mt-3 text-sm font-semibold text-[var(--text)]">
        {hasSearch ? '没有匹配的模板' : '还没有策略智能体模板'}
      </p>
      <p className="mt-1 text-xs text-[var(--text-muted)]">
        {hasSearch ? '换个关键词试试' : '先建一个, 再加 version + 选策略路由'}
      </p>
      {!hasSearch ? (
        <button
          type="button"
          onClick={onCreate}
          className="mt-4 inline-flex items-center gap-1.5 rounded-xl bg-[var(--brand)] px-3 py-1.5 text-xs font-semibold text-white"
        >
          <Plus className="h-3.5 w-3.5" aria-hidden="true" />
          新建模板
        </button>
      ) : null}
    </div>
  );
}

function TemplateTable({
  templates,
  onOpen,
}: {
  templates: AgentTemplate[];
  onOpen: (t: AgentTemplate) => void;
}) {
  return (
    <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
      <table className="w-full text-sm">
        <thead className="border-b border-[var(--border)] bg-[var(--bg-elevated)] text-[10px] uppercase tracking-[0.14em] text-[var(--text-muted)]">
          <tr>
            <th className="px-4 py-2 text-left font-semibold">名称</th>
            <th className="px-4 py-2 text-left font-semibold">状态</th>
            <th className="px-4 py-2 text-left font-semibold">默认模型</th>
            <th className="px-4 py-2 text-left font-semibold">更新时间</th>
          </tr>
        </thead>
        <tbody>
          {templates.map((t) => (
            <tr
              key={t.id}
              onClick={() => onOpen(t)}
              className="cursor-pointer border-b border-[var(--border)] last:border-b-0 transition hover:bg-[var(--bg-elevated)]"
            >
              <td className="px-4 py-3">
                <div className="font-semibold text-[var(--text)]">{t.name}</div>
                {t.description && (
                  <div className="mt-0.5 line-clamp-1 text-[10px] text-[var(--text-muted)]">{t.description}</div>
                )}
              </td>
              <td className="px-4 py-3">
                <StatusPill status={t.status} />
              </td>
              <td className="px-4 py-3 font-mono text-[10px] text-[var(--text-muted)]">
                {t.default_model_id ? t.default_model_id.slice(0, 8) : '—'}
              </td>
              <td className="px-4 py-3 text-[10px] text-[var(--text-muted)]">{formatTime(t.updated_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    active: { label: '活跃', cls: 'bg-emerald-50 text-emerald-700' },
    archived: { label: '已归档', cls: 'bg-slate-50 text-slate-700' },
  };
  const v = map[status] ?? { label: status, cls: 'bg-slate-50 text-slate-700' };
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${v.cls}`}>
      {v.label}
    </span>
  );
}

function CreateTemplateModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (t: AgentTemplate) => void;
}) {
  const create = useCreateTemplate();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [modelId, setModelId] = useState('');
  const [prompt, setPrompt] = useState('');
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!name.trim() || !modelId.trim() || !prompt.trim()) {
      setError('名称、默认模型、默认 system prompt 必填');
      return;
    }
    try {
      const t = await create.mutateAsync({
        name: name.trim(),
        description: description.trim(),
        default_model_id: modelId.trim(),
        default_system_prompt: prompt,
        metadata: { source: 'web' },
      });
      onCreated(t);
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建失败');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-label="新建模板">
      <form
        onSubmit={submit}
        className="w-full max-w-lg space-y-4 rounded-2xl bg-[var(--surface-1)] p-6 shadow-xl"
      >
        <header>
          <h2 className="text-lg font-semibold text-[var(--text)]">新建智能体模板</h2>
          <p className="mt-1 text-xs text-[var(--text-muted)]">先建 template, 再去详情加 version + 选策略路由。</p>
        </header>

        <Field label="名称" required>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="例: 售后客服助手"
            className="h-9 w-full rounded-lg border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]"
            required
          />
        </Field>
        <Field label="描述">
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="一句话说明这个智能体做什么"
            className="h-9 w-full rounded-lg border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]"
          />
        </Field>
        <Field label="默认模型 (上游名或 UUID)" required>
          <input
            value={modelId}
            onChange={(e) => setModelId(e.target.value)}
            placeholder="deepseek-chat 或 4e01f3a7-..."
            className="h-9 w-full rounded-lg border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 font-mono text-xs outline-none focus:border-[var(--brand)]"
            required
          />
        </Field>
        <Field label="默认 system prompt" required>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={4}
            placeholder="你是一名专业、耐心、礼貌的售后客服…"
            className="w-full rounded-lg border border-[var(--border-strong)] bg-[var(--bg-elevated)] p-3 text-sm outline-none focus:border-[var(--brand)]"
            required
          />
        </Field>

        {error ? <p className="text-xs text-rose-600">{error}</p> : null}

        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-3 py-1.5 text-sm text-[var(--text-muted)] hover:bg-[var(--bg-elevated)]"
          >
            取消
          </button>
          <button
            type="submit"
            disabled={create.isPending}
            className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-50"
          >
            {create.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : null}
            创建
          </button>
        </div>
      </form>
    </div>
  );
}

function Field({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
        {label} {required ? <span className="text-rose-500">*</span> : null}
      </span>
      <div className="mt-1.5">{children}</div>
    </label>
  );
}
