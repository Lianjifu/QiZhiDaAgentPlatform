/**
 * 新建模型 — 独立页面 /admin/models/new
 * 左侧填写供应商凭证，从供应商拉取模型列表后再勾选接入；
 * 也可不依赖供应商目录，手动添加模型 ID。
 */
import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, Loader2, Plus, RefreshCw, X } from 'lucide-react';
import type { ModelProtocol } from './schema';
import { useCreateModel, useProbeProviderModels } from './useModels';
import { MODEL_PROTOCOLS, PROTOCOL_META } from './components/constants';

export default function ModelCreatePage() {
  const navigate = useNavigate();
  const createModel = useCreateModel();
  const probe = useProbeProviderModels();
  const [providerName, setProviderName] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [protocol, setProtocol] = useState<ModelProtocol>('openai');
  const [baseUrl, setBaseUrl] = useState(PROTOCOL_META.openai.baseUrl);
  const [catalog, setCatalog] = useState<string[]>([]);
  const [probeError, setProbeError] = useState<string | null>(null);
  const [probed, setProbed] = useState(false);
  const [models, setModels] = useState<string[]>([]);
  const [customDraft, setCustomDraft] = useState('');
  const [query, setQuery] = useState('');

  const switchProtocol = (next: ModelProtocol) => {
    setProtocol(next);
    setBaseUrl(PROTOCOL_META[next].baseUrl);
    setCatalog([]);
    setProbeError(null);
    setProbed(false);
    setModels([]);
    setCustomDraft('');
    setQuery('');
  };

  const toggleModel = (id: string) => {
    setModels((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));
  };

  const removeModel = (id: string) => {
    setModels((cur) => cur.filter((x) => x !== id));
  };

  const addCustomModel = (raw: string) => {
    const id = raw.trim();
    if (!id) return;
    setModels((cur) => (cur.includes(id) ? cur : [...cur, id]));
  };

  const submitCustomDraft = () => {
    addCustomModel(customDraft);
    setCustomDraft('');
  };

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return catalog;
    return catalog.filter((id) => id.toLowerCase().includes(q));
  }, [catalog, query]);

  const probedSet = useMemo(() => new Set(catalog), [catalog]);
  const customModels = useMemo(() => models.filter((id) => !probedSet.has(id)), [models, probedSet]);

  const canProbe = apiKey.trim().length > 0 && baseUrl.trim().length > 0 && !probe.isPending;
  const canSubmit = providerName.trim().length > 0
    && apiKey.trim().length > 0
    && baseUrl.trim().length > 0
    && models.length > 0
    && !createModel.isPending;

  const pullCatalog = () => {
    if (!canProbe) return;
    probe.mutate(
      { apiKey: apiKey.trim(), baseUrl: baseUrl.trim(), protocol },
      {
        onSuccess: (res) => {
          setCatalog(res.models);
          setProbeError(res.error ?? null);
          setProbed(true);
        },
      },
    );
  };

  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-6 p-5 pb-16 sm:p-8 xl:px-10">
      <Link to="/admin/models" className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--brand)]">
        <ArrowLeft className="h-3.5 w-3.5" />返回模型配置
      </Link>
      <header>
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--brand)]">模型配置</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">新建模型</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--text-muted)]">先接入供应商，再从对方拉取可用模型并勾选接入；也可不依赖供应商目录，手动添加模型 ID。</p>
      </header>

      <form
        className="grid items-start gap-5 xl:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]"
        onSubmit={(e) => {
          e.preventDefault();
          if (!canSubmit) return;
          createModel.mutate(
            {
              providerName: providerName.trim(),
              apiKey: apiKey.trim(),
              baseUrl: baseUrl.trim(),
              protocol,
              models,
            },
            {
              onSuccess: (created) => navigate(`/admin/models/${created.id}`),
              onError: () => navigate('/admin/models'),
            },
          );
        }}
      >
        <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
          <h2 className="text-sm font-semibold">供应商凭证</h2>
          <p className="mt-1 text-[11px] leading-5 text-[var(--text-muted)]">协议决定调用格式，模型列表由供应商接口返回。</p>
          <div className="mt-5 space-y-4">
            <div>
              <label htmlFor="provider-name" className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">供应商名称</label>
              <input
                id="provider-name"
                value={providerName}
                onChange={(e) => setProviderName(e.target.value)}
                placeholder="例如:OpenAI 官方"
                className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]"
              />
            </div>
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">协议</p>
              <div className="mt-1.5 grid grid-cols-2 gap-1.5" role="radiogroup" aria-label="协议">
                {MODEL_PROTOCOLS.map((id) => {
                  const selected = protocol === id;
                  return (
                    <button
                      key={id}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      onClick={() => switchProtocol(id)}
                      className={`rounded-lg border px-2.5 py-2 text-left text-xs font-semibold transition ${selected ? 'border-[var(--brand)] bg-[var(--brand-light)] text-[var(--brand)]' : 'border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--brand)]'}`}
                    >
                      {PROTOCOL_META[id].label}
                    </button>
                  );
                })}
              </div>
            </div>
            <div>
              <label htmlFor="api-key" className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">API Key</label>
              <input
                id="api-key"
                type="password"
                autoComplete="off"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="sk-..."
                className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 font-mono text-sm outline-none focus:border-[var(--brand)]"
              />
            </div>
            <div>
              <label htmlFor="base-url" className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">请求地址</label>
              <input
                id="base-url"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder={PROTOCOL_META[protocol].baseUrl}
                className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 font-mono text-sm outline-none focus:border-[var(--brand)]"
              />
            </div>
            <button
              type="button"
              onClick={pullCatalog}
              disabled={!canProbe}
              className="inline-flex h-10 w-full items-center justify-center gap-1.5 rounded-xl bg-[var(--brand)] px-3 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
            >
              {probe.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              {probe.isPending ? '正在拉取…' : probed ? '重新拉取模型' : '从供应商拉取模型'}
            </button>
          </div>
        </section>

        <section className="flex min-h-[28rem] flex-col rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold">模型列表</h2>
              <p className="mt-1 text-[11px] leading-5 text-[var(--text-muted)]">
                {probed
                  ? probeError
                    ? `供应商目录拉取失败：${probeError}`
                    : `供应商返回 ${catalog.length} 个模型，已选 ${models.length} 个。`
                  : '填写凭证后从供应商拉取，或直接手动添加模型 ID。'}
              </p>
            </div>
            {catalog.length > 0 && (
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="筛选模型 ID"
                className="h-9 w-48 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-2.5 text-xs outline-none focus:border-[var(--brand)]"
              />
            )}
          </div>

          <div className="mt-4 min-h-0 flex-1">
            {!probed && catalog.length === 0 && (
              <div className="grid h-full min-h-[16rem] place-items-center rounded-xl border border-dashed border-[var(--border)] bg-[var(--bg-elevated)] px-6 text-center text-sm text-[var(--text-muted)]">
                填写凭证后从供应商拉取模型，或直接使用下方「手动添加」输入模型 ID。
              </div>
            )}
            {probed && catalog.length === 0 && !probeError && (
              <div className="grid h-full min-h-[16rem] place-items-center rounded-xl border border-dashed border-[var(--border)] bg-[var(--bg-elevated)] px-6 text-center text-sm text-[var(--text-muted)]">
                供应商未返回可用模型。请检查密钥、请求地址和协议后重试，或使用下方「手动添加」。
              </div>
            )}
            {probed && probeError && catalog.length === 0 && (
              <div className="grid h-full min-h-[16rem] place-items-center rounded-xl border border-dashed border-rose-300 bg-rose-50 px-6 text-center text-sm text-rose-700">
                {probeError}
              </div>
            )}
            {catalog.length > 0 && (
              <ul className="divide-y divide-[var(--border)] overflow-hidden rounded-xl border border-[var(--border)]">
                {visible.map((id) => {
                  const on = models.includes(id);
                  return (
                    <li key={id}>
                      <label className="flex cursor-pointer items-center gap-3 px-3 py-2.5 hover:bg-[var(--bg-elevated)]">
                        <input type="checkbox" checked={on} onChange={() => toggleModel(id)} className="h-4 w-4 accent-[var(--brand)]" />
                        <span className="font-mono text-sm">{id}</span>
                      </label>
                    </li>
                  );
                })}
                {visible.length === 0 && (
                  <li className="px-3 py-8 text-center text-xs text-[var(--text-muted)]">没有匹配的模型 ID</li>
                )}
              </ul>
            )}
          </div>

          <div className="mt-5 space-y-3 border-t border-[var(--border)] pt-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold">手动添加</h3>
                <p className="mt-0.5 text-[11px] leading-5 text-[var(--text-muted)]">不依赖供应商目录：填写模型 ID 直接加入待创建列表。</p>
              </div>
              <div className="flex w-full max-w-sm items-center gap-2">
                <input
                  value={customDraft}
                  onChange={(e) => setCustomDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      submitCustomDraft();
                    }
                  }}
                  placeholder="例如 deepseek-chat"
                  className="h-9 flex-1 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-2.5 font-mono text-xs outline-none focus:border-[var(--brand)]"
                />
                <button
                  type="button"
                  onClick={submitCustomDraft}
                  disabled={customDraft.trim().length === 0}
                  className="inline-flex h-9 items-center gap-1 rounded-lg border border-[var(--border)] px-2.5 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <Plus className="h-3.5 w-3.5" />添加
                </button>
              </div>
            </div>
            {customModels.length > 0 ? (
              <ul className="flex flex-wrap gap-1.5">
                {customModels.map((id) => (
                  <li
                    key={id}
                    className="inline-flex items-center gap-1 rounded-full border border-[var(--border)] bg-[var(--bg-elevated)] px-2.5 py-1 font-mono text-xs"
                  >
                    {id}
                    <button
                      type="button"
                      onClick={() => removeModel(id)}
                      className="rounded-full p-0.5 text-[var(--text-muted)] hover:bg-rose-50 hover:text-rose-600"
                      aria-label={`移除 ${id}`}
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[11px] text-[var(--text-muted)]">尚未手动添加任何模型。</p>
            )}
          </div>

          <div className="mt-5 flex justify-end gap-2 border-t border-[var(--border)] pt-5">
            <Link to="/admin/models" className="rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold">取消</Link>
            <button type="submit" disabled={!canSubmit} className="rounded-xl bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40">
              {createModel.isPending ? '创建中…' : `创建${models.length > 0 ? ` ${models.length} 个` : ''}模型`}
            </button>
          </div>
        </section>
      </form>
    </div>
  );
}
