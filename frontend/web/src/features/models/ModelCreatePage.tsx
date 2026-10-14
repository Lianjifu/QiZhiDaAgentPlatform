import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { useCreateModel } from './useModels';
import { CatalogNotice, ConnectivityTestPanel, ProviderConnectionForm, useProviderConnectionWorkflow } from './components/ProviderConnectionForm';

export default function ModelCreatePage() {
  const navigate = useNavigate();
  const createModel = useCreateModel();
  const connection = useProviderConnectionWorkflow({ name: '', apiKey: '', baseUrl: 'https://api.openai.com/v1', protocol: 'openai' });
  const [selection, setSelection] = useState<{ catalog: typeof connection.catalog; models: string[] }>({ catalog: null, models: [] });
  const [verifiedSelection, setVerifiedSelection] = useState<string | undefined>();
  const [saveError, setSaveError] = useState(false);
  const models = selection.catalog === connection.catalog && connection.catalog ? selection.models : [];
  const verified = !!connection.verificationToken && verifiedSelection === connection.verificationToken;
  const selected = verified ? [connection.testModel.trim()] : models;
  const canSubmit = !!connection.value.name.trim() && connection.canConnect && selected.length > 0 && !createModel.isPending;
  const toggle = (id: string) => { setVerifiedSelection(undefined); setSelection({ catalog: connection.catalog, models: models.includes(id) ? models.filter(x => x !== id) : [...models, id] }); };
  return <div className="mx-auto w-full max-w-[1440px] space-y-6 p-5 pb-16 sm:p-8 xl:px-10">
    <Link to="/admin/models" className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)]"><ArrowLeft className="h-3.5 w-3.5" />返回模型配置</Link>
    <header><p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--brand)]">模型配置</p><h1 className="mt-1 text-2xl font-semibold tracking-tight">新建模型</h1><p className="mt-2 text-sm text-[var(--text-muted)]">选择供应商目录中的模型，或验证目录外模型后接入。</p></header>
    <form className="grid items-start gap-5 xl:grid-cols-[minmax(0,24rem)_minmax(0,1fr)]" onSubmit={e => {
      e.preventDefault();
      if (!canSubmit) return;
      setSaveError(false);
      createModel.mutate({ providerName: connection.value.name.trim(), apiKey: connection.value.apiKey.trim(), baseUrl: connection.value.baseUrl.trim(), protocol: connection.value.protocol, apiVersion: connection.apiVersion, models: selected, source: verified ? 'verified' : 'catalog', verificationToken: verified ? connection.verificationToken : undefined }, { onSuccess: created => navigate(`/admin/models/${created.id}`), onError: () => setSaveError(true) });
    }}>
      <ProviderConnectionForm connection={connection} />
      <section className="flex min-h-[28rem] flex-col rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
        <h2 className="text-sm font-semibold">模型列表</h2><CatalogNotice connection={connection} />
        <div className="mt-4 flex-1">{connection.catalog?.models.length ? <ul className="divide-y divide-[var(--border)] overflow-hidden rounded-xl border border-[var(--border)]">{connection.catalog.models.map(id => <li key={id}><label className="flex cursor-pointer items-center gap-3 px-3 py-2.5 text-sm"><input type="checkbox" checked={models.includes(id)} onChange={() => toggle(id)} className="accent-[var(--brand)]" /><span className="font-mono">{id}</span></label></li>)}</ul> : <div className="grid min-h-[12rem] place-items-center rounded-xl border border-dashed border-[var(--border)] text-sm text-[var(--text-muted)]">模型列表从供应商拉取，不会预置本地目录。</div>}</div>
        <ConnectivityTestPanel connection={connection} />
        {connection.verificationToken && <button type="button" onClick={() => setVerifiedSelection(connection.verificationToken)} className="mt-3 rounded-lg border border-[var(--brand)] p-2 text-xs font-semibold text-[var(--brand)]">{verified ? '已选择验证模型' : '接入已验证模型'}：{connection.testModel}</button>}
        {saveError && <p role="alert" className="mt-3 text-xs text-rose-600">创建失败，请检查配置并重试。</p>}
        <div className="mt-5 flex justify-end gap-2 border-t border-[var(--border)] pt-5"><Link to="/admin/models" className="rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold">取消</Link><button type="submit" disabled={!canSubmit} className="rounded-xl bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white disabled:opacity-40">{createModel.isPending ? '创建中…' : `创建${selected.length ? ` ${selected.length} 个` : ''}模型`}</button></div>
      </section>
    </form>
  </div>;
}
