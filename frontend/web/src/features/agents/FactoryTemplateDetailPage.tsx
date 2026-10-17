/**
 * Phase 23: agent_factory template 详情 — /admin/agents/factory/:id
 *
 * 模板信息 (name/description/默认 model) + 版本列表 (按时间倒序) +
 * 「新建 version」按钮 + 每个 version 行: route + strategy 标签 +
 * publish/release/retire 按钮 (按状态条件显示).
 *
 * 这是 Phase 22 的 <RoutePicker> 真正被接入的地方.
 */
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft, ChevronDown, ChevronRight, Edit3, GitBranch, Loader2,
  Network, Plus, Send, Sparkles, Trash2,
} from 'lucide-react';
import {
  TEMPLATE_STATUS_LABEL, VERSION_STATUS_LABEL, ROUTE_STRATEGY_LABEL,
  useCreateVersion, usePublishVersion, useReleaseVersion, useRetireVersion,
  useTemplateDetail, useTemplateVersions, useUpdateVersionNotes,
  useRouteOptions,
  type AgentTemplate, type AgentVersion, type VersionStatus,
} from './useAgentFactory';
import { RoutePicker } from './components/RoutePicker';

function formatTime(iso: string | null): string {
  if (!iso) return '—';
  const t = new Date(iso);
  return Number.isNaN(t.getTime()) ? iso : t.toLocaleString('zh-CN');
}

export default function FactoryTemplateDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: template, isLoading: tplLoading, error: tplError } = useTemplateDetail(id);
  const { data: versions, isLoading: verLoading } = useTemplateVersions(id);
  const { data: routes } = useRouteOptions();
  const [showCreateVer, setShowCreateVer] = useState(false);

  if (tplLoading) {
    return (
      <div className="flex items-center justify-center gap-2 py-24 text-[var(--text-muted)]">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        <span className="text-xs">加载模板…</span>
      </div>
    );
  }
  if (tplError || !template) {
    return (
      <div className="p-6">
        <button
          type="button"
          onClick={() => navigate('/admin/agents/factory')}
          className="inline-flex items-center gap-1 text-xs text-[var(--text-muted)] hover:text-[var(--brand)]"
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
          返回列表
        </button>
        <p className="mt-6 rounded-xl border border-rose-300 bg-rose-50 p-4 text-sm text-rose-700">
          加载失败,模板可能已被删除。
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      <button
        type="button"
        onClick={() => navigate('/admin/agents/factory')}
        className="inline-flex items-center gap-1 text-xs text-[var(--text-muted)] hover:text-[var(--brand)]"
      >
        <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
        返回模板列表
      </button>

      <TemplateHeader template={template} />

      <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
        <header className="mb-4 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-[var(--text)]">
            <GitBranch className="h-4 w-4 text-[var(--text-muted)]" aria-hidden="true" />
            版本
          </h2>
          <button
            type="button"
            onClick={() => setShowCreateVer(true)}
            className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 py-1.5 text-xs font-semibold text-white"
          >
            <Plus className="h-3.5 w-3.5" aria-hidden="true" />
            新建 version
          </button>
        </header>
        {verLoading ? (
          <div className="flex items-center justify-center gap-2 py-8 text-[var(--text-muted)]">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            <span className="text-xs">加载版本…</span>
          </div>
        ) : (versions ?? []).length === 0 ? (
          <p className="rounded-xl border border-dashed border-[var(--border)] py-8 text-center text-xs text-[var(--text-muted)]">
            还没有 version, 先建一个。
          </p>
        ) : (
          <ul className="space-y-2">
            {versions!.map((v) => (
              <VersionRow key={v.id} version={v} routeName={findRouteName(routes, v.route_id)} />
            ))}
          </ul>
        )}
      </section>

      {showCreateVer ? (
        <CreateVersionModal
          template={template}
          onClose={() => setShowCreateVer(false)}
          onCreated={() => setShowCreateVer(false)}
        />
      ) : null}
    </div>
  );
}

function findRouteName(
  routes: ReturnType<typeof useRouteOptions>['data'],
  routeId: string | null,
): string | null {
  if (!routeId || !routes) return null;
  return routes.find((r) => r.id === routeId)?.name ?? null;
}

function TemplateHeader({ template }: { template: AgentTemplate }) {
  return (
    <header className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
      <div className="flex items-start gap-3">
        <div className="grid h-12 w-12 place-items-center rounded-xl bg-[var(--brand-light)] text-[var(--brand)]">
          <Sparkles className="h-6 w-6" aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold text-[var(--text)]">{template.name}</h1>
            <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-700">
              {TEMPLATE_STATUS_LABEL[template.status] ?? template.status}
            </span>
          </div>
          {template.description ? (
            <p className="mt-1 text-xs text-[var(--text-muted)]">{template.description}</p>
          ) : null}
          <dl className="mt-3 grid grid-cols-2 gap-2 text-[10px] text-[var(--text-muted)] sm:grid-cols-4">
            <Pair label="ID" value={template.id} mono />
            <Pair label="默认模型" value={template.default_model_id ?? '—'} mono />
            <Pair label="创建时间" value={formatTime(template.created_at)} />
            <Pair label="更新时间" value={formatTime(template.updated_at)} />
          </dl>
        </div>
      </div>
    </header>
  );
}

function Pair({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] p-2">
      <p className="text-[10px] text-[var(--text-muted)]">{label}</p>
      <p className={`mt-0.5 truncate text-xs font-semibold ${mono ? 'font-mono' : ''}`}>{value}</p>
    </div>
  );
}

function VersionRow({ version, routeName }: { version: AgentVersion; routeName: string | null }) {
  const [expanded, setExpanded] = useState(false);
  const publish = usePublishVersion();
  const release = useReleaseVersion();
  const retire = useRetireVersion();
  const updateNotes = useUpdateVersionNotes();
  const [editingNotes, setEditingNotes] = useState(false);
  const [draftNotes, setDraftNotes] = useState(version.release_notes);
  const [actionError, setActionError] = useState<string | null>(null);

  const runAction = async (
    label: string,
    fn: () => Promise<unknown>,
  ) => {
    setActionError(null);
    try {
      await fn();
    } catch (err) {
      setActionError(`${label}: ${err instanceof Error ? err.message : '失败'}`);
    }
  };

  return (
    <li className="rounded-xl border border-[var(--border)] bg-[var(--surface-1)]">
      <div className="flex items-center gap-2 p-3">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-label={expanded ? '折叠' : '展开'}
          className="grid h-7 w-7 place-items-center rounded-md text-[var(--text-muted)] hover:bg-[var(--bg-elevated)]"
        >
          {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs font-semibold text-[var(--text)]">{version.version_tag}</span>
            <VersionStatusPill status={version.status} />
            {routeName && (
              <span className="inline-flex items-center gap-1 rounded-full bg-[var(--bg-elevated)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-muted)]">
                <Network className="h-3 w-3" aria-hidden="true" />
                {routeName}
              </span>
            )}
            {version.route_strategy && (
              <span className="rounded-full bg-[var(--brand-light)] px-2 py-0.5 text-[10px] font-semibold text-[var(--brand)]">
                {ROUTE_STRATEGY_LABEL[version.route_strategy] ?? version.route_strategy}
              </span>
            )}
          </div>
          <p className="mt-0.5 line-clamp-1 text-[10px] text-[var(--text-muted)]">
            创建 {formatTime(version.created_at)} · 更新 {formatTime(version.updated_at)}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {version.status === 'draft' ? (
            <button
              type="button"
              disabled={publish.isPending}
              onClick={() => runAction('发布', () => publish.mutateAsync({
                templateId: version.template_id, versionId: version.id,
              }))}
              className="inline-flex items-center gap-1 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-2 py-1 text-[10px] font-semibold text-[var(--text)] hover:border-[var(--brand)] hover:text-[var(--brand)] disabled:opacity-50"
            >
              <Send className="h-3 w-3" aria-hidden="true" />
              发布
            </button>
          ) : null}
          {version.status === 'published' ? (
            <button
              type="button"
              disabled={release.isPending}
              onClick={() => runAction('上线', () => release.mutateAsync({
                templateId: version.template_id, versionId: version.id, notes: version.release_notes,
              }))}
              className="inline-flex items-center gap-1 rounded-lg bg-[var(--brand)] px-2 py-1 text-[10px] font-semibold text-white disabled:opacity-50"
            >
              <Sparkles className="h-3 w-3" aria-hidden="true" />
              上线 (release)
            </button>
          ) : null}
          {version.status === 'released' ? (
            <button
              type="button"
              disabled={retire.isPending}
              onClick={() => runAction('下线', () => retire.mutateAsync({
                templateId: version.template_id, versionId: version.id,
              }))}
              className="inline-flex items-center gap-1 rounded-lg border border-rose-300 px-2 py-1 text-[10px] font-semibold text-rose-600 hover:bg-rose-50 disabled:opacity-50"
            >
              <Trash2 className="h-3 w-3" aria-hidden="true" />
              下线
            </button>
          ) : null}
        </div>
      </div>

      {expanded ? (
        <div className="space-y-3 border-t border-[var(--border)] p-3">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">System Prompt</p>
            <pre className="mt-1 max-h-48 overflow-auto rounded-lg bg-[var(--bg-elevated)] p-2 font-mono text-[11px] leading-relaxed text-[var(--text-secondary)]">
              {version.system_prompt || '(空)'}
            </pre>
          </div>
          <div>
            <div className="mb-1 flex items-center justify-between">
              <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">Release notes</p>
              {version.status === 'draft' ? (
                <button
                  type="button"
                  onClick={() => setEditingNotes((v) => !v)}
                  className="inline-flex items-center gap-1 text-[10px] text-[var(--text-muted)] hover:text-[var(--brand)]"
                >
                  <Edit3 className="h-3 w-3" aria-hidden="true" />
                  {editingNotes ? '取消' : '编辑'}
                </button>
              ) : null}
            </div>
            {editingNotes ? (
              <div className="space-y-2">
                <textarea
                  value={draftNotes}
                  onChange={(e) => setDraftNotes(e.target.value)}
                  rows={3}
                  className="w-full rounded-lg border border-[var(--border-strong)] bg-[var(--bg-elevated)] p-2 text-xs outline-none focus:border-[var(--brand)]"
                />
                <button
                  type="button"
                  disabled={updateNotes.isPending}
                  onClick={() => runAction('保存', () => updateNotes.mutateAsync({
                    templateId: version.template_id,
                    versionId: version.id,
                    release_notes: draftNotes,
                  }).then(() => setEditingNotes(false)))}
                  className="rounded-lg bg-[var(--brand)] px-2 py-1 text-[10px] font-semibold text-white disabled:opacity-50"
                >
                  保存
                </button>
              </div>
            ) : (
              <p className="rounded-lg bg-[var(--bg-elevated)] p-2 text-xs text-[var(--text-secondary)]">
                {version.release_notes || '(空)'}
              </p>
            )}
          </div>
          {actionError ? <p className="text-[10px] text-rose-600">{actionError}</p> : null}
        </div>
      ) : null}
    </li>
  );
}

function VersionStatusPill({ status }: { status: VersionStatus }) {
  const map: Record<VersionStatus, { label: string; cls: string }> = {
    draft: { label: '草稿', cls: 'bg-slate-50 text-slate-700' },
    published: { label: '已发布', cls: 'bg-amber-50 text-amber-700' },
    released: { label: '已上线', cls: 'bg-emerald-50 text-emerald-700' },
    retired: { label: '已下线', cls: 'bg-rose-50 text-rose-700' },
  };
  const v = map[status] ?? { label: status, cls: 'bg-slate-50 text-slate-700' };
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${v.cls}`}>
      {v.label}
    </span>
  );
}

function CreateVersionModal({
  template,
  onClose,
  onCreated,
}: {
  template: AgentTemplate;
  onClose: () => void;
  onCreated: () => void;
}) {
  const create = useCreateVersion();
  const [versionTag, setVersionTag] = useState('v1');
  const [systemPrompt, setSystemPrompt] = useState(template.default_system_prompt);
  const [routeId, setRouteId] = useState<string | null>(null);
  const [routeStrategy, setRouteStrategy] = useState<AgentVersion['route_strategy']>(null);
  const [releaseNotes, setReleaseNotes] = useState('');
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!versionTag.trim()) {
      setError('version tag 必填');
      return;
    }
    try {
      await create.mutateAsync({
        templateId: template.id,
        version_tag: versionTag.trim(),
        system_prompt: systemPrompt,
        route_id: routeId,
        route_strategy: routeStrategy,
        release_notes: releaseNotes.trim(),
      });
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建失败');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-label="新建 version">
      <form onSubmit={submit} className="w-full max-w-2xl space-y-4 rounded-2xl bg-[var(--surface-1)] p-6 shadow-xl">
        <header>
          <h2 className="text-lg font-semibold text-[var(--text)]">新建 version</h2>
          <p className="mt-1 text-xs text-[var(--text-muted)]">
            模板: {template.name} · Phase 15+ 持久化 route_id + route_strategy
          </p>
        </header>

        <Field label="Version tag" required>
          <input
            value={versionTag}
            onChange={(e) => setVersionTag(e.target.value)}
            placeholder="v1 / v0.3.1"
            className="h-9 w-full rounded-lg border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 font-mono text-xs outline-none focus:border-[var(--brand)]"
            required
          />
        </Field>

        <Field label="System prompt (留空用模板默认)">
          <textarea
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            rows={4}
            className="w-full rounded-lg border border-[var(--border-strong)] bg-[var(--bg-elevated)] p-3 text-sm outline-none focus:border-[var(--brand)]"
          />
        </Field>

        <div>
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
            策略路由 (Phase 22 — RoutePicker)
          </p>
          <RoutePicker
            selectedId={routeId}
            onChange={(id) => {
              setRouteId(id);
              // 选了 route 后, 把它的 strategy 同步过来 (admin 也可手动覆盖)
              if (id) {
                // 同步在 submit 时根据 routeId 找 — 这里不强同步避免重渲染
                setRouteStrategy(null);
              } else {
                setRouteStrategy(null);
              }
            }}
          />
          <p className="mt-1 text-[10px] text-[var(--text-muted)]">
            选 route 后, 该 route 自带的 strategy 会作为 default. 也可以下方手动覆盖.
          </p>
        </div>

        <Field label="Route strategy (覆盖)">
          <select
            value={routeStrategy ?? ''}
            onChange={(e) => setRouteStrategy((e.target.value || null) as AgentVersion['route_strategy'])}
            className="h-9 w-full rounded-lg border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-xs outline-none focus:border-[var(--brand)]"
          >
            <option value="">— 用 route 自带 —</option>
            <option value="fallback">失败转移</option>
            <option value="quality-first">质量优先</option>
            <option value="cost-first">成本优先</option>
            <option value="latency-first">延迟优先</option>
            <option value="round-robin">轮询</option>
            <option value="weighted">加权</option>
          </select>
        </Field>

        <Field label="Release notes (release gate 通过后用)">
          <textarea
            value={releaseNotes}
            onChange={(e) => setReleaseNotes(e.target.value)}
            rows={2}
            className="w-full rounded-lg border border-[var(--border-strong)] bg-[var(--bg-elevated)] p-2 text-xs outline-none focus:border-[var(--brand)]"
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
