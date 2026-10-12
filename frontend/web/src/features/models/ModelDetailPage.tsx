import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Save } from 'lucide-react';
import { ApiError } from '@qzdap/web-api';
import type { Model, ModelDetail, UpdateModelVars } from './schema';
import { useModelDetail, useUpdateModel } from './useModels';
import { DrawerPanelDetail } from './components/DrawerPanels';
import { STATUS_BADGE } from './components/constants';
import { CatalogNotice, ConnectivityTestPanel, ProviderConnectionForm, useProviderConnectionWorkflow } from './components/ProviderConnectionForm';

const back = <Link to="/admin/models" className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)]"><ArrowLeft className="h-3.5 w-3.5" />返回模型配置</Link>;
const pageClass = 'mx-auto w-full max-w-[1440px] space-y-6 p-5 pb-16 sm:p-8 xl:px-10';

export default function ModelDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const query = useModelDetail(id);
  if (query.isLoading) return <div className={pageClass}>{back}<p role="status">正在加载模型…</p></div>;
  if (query.isError) {
    const missing = query.error instanceof ApiError && query.error.status === 404;
    return <div className={pageClass}>{back}<p role="alert">{missing ? '模型不存在或已被删除' : '模型加载失败，请重试。'}</p>{!missing && <button onClick={() => query.refetch()} className="text-sm text-[var(--brand)]">重试</button>}</div>;
  }
  if (!query.data) return <div className={pageClass}>{back}<p>模型不存在或已被删除</p></div>;
  return <DetailEditor key={id} original={query.data} />;
}

function DetailEditor({ original }: { original: ModelDetail }) {
  const navigate = useNavigate();
  const updateModel = useUpdateModel();
  const [draft, setDraft] = useState<Model>(original);
  const [saveError, setSaveError] = useState(false);
  const [replacement, setReplacement] = useState<{ catalog: ReturnType<typeof useProviderConnectionWorkflow>['catalog']; model: string; token?: string }>();
  const connection = useProviderConnectionWorkflow({ name: original.provider.name, protocol: original.provider.protocol, baseUrl: original.provider.baseUrl, apiVersion: original.provider.apiVersion, apiKey: '' }, original.id, original.provider.hasCredential);
  const currentModel = original.upstreamModel ?? original.name;
  const selectedReplacement = replacement?.token
    ? replacement.token === connection.verificationToken ? replacement.model : undefined
    : replacement?.catalog === connection.catalog && connection.catalog ? replacement?.model : undefined;
  const providerChanged = connection.value.name !== original.provider.name || connection.value.protocol !== original.provider.protocol || connection.value.baseUrl !== original.provider.baseUrl || connection.value.apiVersion !== original.provider.apiVersion || !!connection.value.apiKey.trim();
  const upstream = selectedReplacement ?? currentModel;
  // Credential/protocol/address changes must validate the retained upstream too.
  const connectionChanged = connection.value.protocol !== original.provider.protocol || connection.value.baseUrl !== original.provider.baseUrl || connection.value.apiVersion !== original.provider.apiVersion || !!connection.value.apiKey.trim();
  const catalogValid = connection.catalog?.models.includes(upstream);
  const verifiedValid = connection.verificationToken && connection.testModel.trim() === upstream;
  const canSave = !!draft.name.trim() && !!connection.value.name.trim() && (!connectionChanged || connection.canConnect) && !updateModel.isPending && (!connectionChanged || !!catalogValid || !!verifiedValid);
  const save = () => {
    if (!canSave) return;
    const patch: UpdateModelVars['patch'] = { name: draft.name, description: draft.description, tier: draft.tier, status: draft.status, contextWindow: draft.contextWindow, priceIn: draft.priceIn, priceOut: draft.priceOut, task: draft.task, tags: draft.tags };
    if (providerChanged) patch.provider = { ...connection.value, apiVersion: connection.apiVersion };
    if (upstream !== currentModel || connectionChanged) {
      patch.upstreamModel = upstream;
      patch.source = verifiedValid ? 'verified' : 'catalog';
      if (verifiedValid) patch.verificationToken = connection.verificationToken;
    }
    setSaveError(false);
    updateModel.mutate({ id: original.id, patch }, { onSuccess: () => navigate('/admin/models'), onError: () => setSaveError(true) });
  };
  const badge = STATUS_BADGE[draft.status];
  return <div className={pageClass}>{back}
    <header><p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--brand)]">模型工作区</p><h1 className="mt-1 text-3xl font-semibold tracking-tight">{draft.name}</h1><div className="mt-3 flex gap-2"><span className={`rounded-full px-2 py-1 text-[11px] ${badge.className}`}>{badge.label}</span><span className="text-xs text-[var(--text-muted)]">{connection.value.name} · {upstream}</span></div></header>
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-6"><div className="space-y-5">
      <DrawerPanelDetail model={{ ...draft, providerName: connection.value.name }} onChange={p => setDraft({ ...draft, ...p })} />
      <div className="grid gap-5 xl:grid-cols-2"><ProviderConnectionForm connection={connection} savedKeyHint={original.provider.hasCredential ? `已保存密钥 ${original.provider.apiKeyMasked}` : undefined} /><section className="rounded-2xl border border-[var(--border)] p-5"><h2 className="text-sm font-semibold">替换当前模型</h2><p className="mt-1 text-xs text-[var(--text-muted)]">仅替换当前模型的上游 ID，保留模型标识和路由引用。显示名称独立编辑。</p><CatalogNotice connection={connection} />{connection.catalog?.models.length ? <label className="mt-3 block text-xs">供应商模型<select aria-label="替换上游模型" className="mt-2 h-10 w-full rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] px-3" value={selectedReplacement ?? ''} onChange={e => setReplacement(e.target.value ? { catalog: connection.catalog, model: e.target.value } : undefined)}><option value="">保留：{currentModel}</option>{connection.catalog.models.map(m => <option key={m} value={m}>{m}</option>)}</select></label> : null}<ConnectivityTestPanel connection={connection} />{connection.verificationToken && <button type="button" onClick={() => setReplacement({ catalog: connection.catalog, model: connection.testModel.trim(), token: connection.verificationToken })} className="mt-3 rounded-lg border border-[var(--brand)] p-2 text-xs text-[var(--brand)]">使用已验证模型：{connection.testModel}</button>}{connectionChanged && !catalogValid && !verifiedValid && <p className="mt-3 text-xs text-amber-600">连接已变更，请拉取目录确认当前模型，或真实测试后再保存。</p>}</section></div>
    </div>{saveError && <p role="alert" className="mt-4 text-xs text-rose-600">保存失败，修改仍保留在当前页面，请重试。</p>}<div className="mt-6 flex justify-end gap-3 border-t border-[var(--border)] pt-5"><Link to="/admin/models" className="rounded-lg border border-[var(--border)] px-4 py-2 text-xs font-semibold">关闭</Link><button type="button" disabled={!canSave} onClick={save} className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white disabled:opacity-40"><Save className="h-3.5 w-3.5" />{updateModel.isPending ? '保存中…' : '保存修改'}</button></div></section>
  </div>;
}
