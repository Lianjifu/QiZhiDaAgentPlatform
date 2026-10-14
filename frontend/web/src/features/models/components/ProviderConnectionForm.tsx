import { ApiError } from '@qzdap/web-api';
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Loader2, RefreshCw } from 'lucide-react';
import type { ConnectivityTestResult, ModelProtocol, ProbeModelsResult, ProviderConnectionValues } from '../schema';
import { MODEL_PROTOCOLS, PROTOCOL_META } from './constants';
import { useModelConnectivityTest, useProbeProviderModels } from '../useModels';

export const connectionInput = 'h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]';
const labelClass = 'text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]';

function connectionError(error: unknown, fallback: string): string {
  if (error instanceof ApiError && error.status === 401) return '平台登录已失效，请重新登录后再试；这不是供应商 API Key 错误。';
  if (error instanceof ApiError && error.status === 403) return '当前账号或工作区没有模型管理权限。';
  return fallback;
}

export function useProviderConnectionWorkflow(initial: ProviderConnectionValues, modelId?: string, hasCredential = false) {
  const [value, setValue] = useState(initial);
  const [catalog, setCatalog] = useState<ProbeModelsResult | null>(null);
  const [testModel, setTestModel] = useState('');
  const [result, setResult] = useState<ConnectivityTestResult | null>(null);
  const generation = useRef(0);
  const catalogGeneration = useRef(0);
  const probe = useProbeProviderModels();
  const test = useModelConnectivityTest();
  useEffect(() => () => { generation.current += 1; catalogGeneration.current += 1; }, []);
  const resetResult = () => { generation.current += 1; setResult(null); };
  const update = (patch: Partial<ProviderConnectionValues>) => {
    resetResult();
    catalogGeneration.current += 1;
    setCatalog(null);
    setValue(current => ({ ...current, ...patch }));
  };
  const updateModel = (model: string) => { resetResult(); setTestModel(model); };
  const vars = {
    modelId,
    apiKey: value.apiKey.trim() || undefined,
    baseUrl: value.baseUrl.trim(),
    protocol: value.protocol,
    apiVersion: value.apiVersion?.trim() || (value.protocol === 'azure' ? '2024-10-21' : undefined),
  };
  const canConnect = !!vars.baseUrl && (!!vars.apiKey || (!!modelId && hasCredential));
  const pullCatalog = () => {
    if (!canConnect || probe.isPending) return;
    const g = ++catalogGeneration.current;
    probe.mutate(vars, {
      onSuccess: res => {
        if (g !== catalogGeneration.current) return;
        setCatalog(res);
        setTestModel(current => {
          if (current || !res.models[0]) return current;
          generation.current += 1;
          setResult(null);
          return res.models[0];
        });
      },
      onError: error => {
        if (g === catalogGeneration.current) setCatalog({ models: [], error: connectionError(error, '目录拉取失败，请检查供应商连接后重试。') });
      },
    });
  };
  const runTest = () => {
    if (!canConnect || !testModel.trim() || test.isPending) return;
    const g = ++generation.current;
    setResult(null);
    const model = testModel.trim();
    test.mutate({ ...vars, model }, {
      onSuccess: res => { if (g === generation.current) setResult(res); },
      onError: error => {
        if (g === generation.current) setResult({ success: false, latencyMs: 0, statusCode: null, requestedModel: model, actualModel: null, response: null, error: connectionError(error, '请求失败，请检查连接或稍后重试。') });
      },
    });
  };
  return { value, update, catalog, pullCatalog, catalogPending: probe.isPending, canConnect, testModel, updateModel, result, runTest, testPending: test.isPending,
    verificationToken: result?.success && result.requestedModel === testModel.trim() ? result.verificationToken : undefined,
    apiVersion: vars.apiVersion,
  };
}

export type ConnectionWorkflow = ReturnType<typeof useProviderConnectionWorkflow>;

export function ProviderConnectionForm({ connection, savedKeyHint }: { connection: ConnectionWorkflow; savedKeyHint?: string }) {
  const { value, update } = connection;
  return <section className="space-y-4 rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
    <h2 className="text-sm font-semibold">供应商凭证</h2>
    {(connection.catalog?.error?.includes('平台登录已失效') || connection.result?.error?.includes('平台登录已失效')) && <Link to="/login" className="inline-flex text-sm font-semibold text-[var(--brand)] underline">重新登录平台</Link>}
    <ConnectionField label="供应商名称" id="provider-name"><input id="provider-name" value={value.name} onChange={e => update({ name: e.target.value })} placeholder="例如：自建网关" className={connectionInput} /></ConnectionField>
    <div><p className={labelClass}>协议</p><div className="mt-1.5 grid grid-cols-2 gap-1.5" role="radiogroup" aria-label="协议">{MODEL_PROTOCOLS.map(p => <button type="button" role="radio" aria-checked={p === value.protocol} key={p} onClick={() => update({ protocol: p as ModelProtocol, baseUrl: PROTOCOL_META[p].baseUrl, apiVersion: p === 'azure' ? '2024-10-21' : undefined })} className={`rounded-lg border px-2.5 py-2 text-left text-xs font-semibold ${p === value.protocol ? 'border-[var(--brand)] bg-[var(--brand-light)] text-[var(--brand)]' : 'border-[var(--border)] text-[var(--text-secondary)]'}`}>{PROTOCOL_META[p].label}</button>)}</div><p className="mt-2 text-[11px] leading-5 text-[var(--text-muted)]">{PROTOCOL_META[value.protocol].summary}</p></div>
    <ConnectionField label="API Key" id="api-key"><input id="api-key" type="password" autoComplete="off" value={value.apiKey} onChange={e => update({ apiKey: e.target.value })} placeholder={savedKeyHint ? '留空则保留已保存密钥' : 'sk-...'} className={connectionInput} />{savedKeyHint && <p className="mt-1 text-[11px] text-[var(--text-muted)]">{savedKeyHint}；留空保留，仅填写新密钥时替换。</p>}</ConnectionField>
    <ConnectionField label="请求地址" id="base-url"><input id="base-url" value={value.baseUrl} onChange={e => update({ baseUrl: e.target.value })} placeholder={value.protocol === 'qwen' ? '填写账户所属区域的 API 地址' : PROTOCOL_META[value.protocol].baseUrl} className={connectionInput} /></ConnectionField>
    {value.protocol === 'azure' && <ConnectionField label="API 版本（可选）" id="api-version"><input id="api-version" value={value.apiVersion ?? '2024-10-21'} onChange={e => update({ apiVersion: e.target.value })} className={connectionInput} /></ConnectionField>}
    {value.protocol === 'deepseek' && /\/anthropic(?:\/|$)/.test(value.baseUrl) && <p role="alert" className="text-xs text-amber-700">DeepSeek 官方协议使用 OpenAI 格式，请将地址改为 https://api.deepseek.com；如需使用 /anthropic 地址，请选择 Anthropic 兼容。</p>}
    <button type="button" onClick={connection.pullCatalog} disabled={!connection.canConnect || connection.catalogPending} className="inline-flex h-10 w-full items-center justify-center gap-1.5 rounded-xl bg-[var(--brand)] px-3 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40">{connection.catalogPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}{connection.catalogPending ? '正在拉取…' : '从供应商拉取模型'}</button>
  </section>;
}

export function ConnectivityTestPanel({ connection }: { connection: ConnectionWorkflow }) {
  const { result, value } = connection;
  const redact = (text: string) => value.apiKey.trim() ? text.split(value.apiKey.trim()).join('[已隐藏密钥]') : text;
  return <section aria-label="真实调用测试" className="mt-5 space-y-3 rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] p-4">
    <div><h3 className="text-sm font-semibold">真实调用测试</h3><p className="mt-1 text-[11px] leading-5 text-[var(--text-muted)]">发送一次真实的最小推理请求，可能消耗 tokens；测试不会保存供应商或模型。目录内模型无需测试即可接入。</p></div>
    <ConnectionField label={value.protocol === 'azure' ? '测试部署名称' : '测试模型 ID'} id="test-model"><input id="test-model" list="test-model-catalog" value={connection.testModel} onChange={e => connection.updateModel(e.target.value)} placeholder={value.protocol === 'azure' ? '部署名称' : '可编辑的供应商模型 ID'} className={connectionInput} /><datalist id="test-model-catalog">{connection.catalog?.models.map(m => <option key={m} value={m} />)}</datalist></ConnectionField>
    <button type="button" onClick={connection.runTest} disabled={!connection.canConnect || !connection.testModel.trim() || connection.testPending} className="inline-flex h-9 items-center justify-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40">{connection.testPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}{connection.testPending ? '正在测试…' : '测试真实调用'}</button>
    <div aria-live="polite">{connection.testPending && <p className="text-xs text-[var(--text-muted)]">正在发送真实请求，请稍候…</p>}{result && <div className={`space-y-1 rounded-lg border p-3 text-xs ${result.success ? 'border-emerald-300 text-emerald-700' : 'border-rose-300 text-rose-700'}`}><p className="font-semibold">{result.success ? '测试成功' : '测试失败'}</p><p>HTTP 状态：{result.statusCode ?? '无响应'} · 耗时：{result.latencyMs} ms</p><p>请求模型：{redact(result.requestedModel)}</p><p>实际模型：{result.actualModel ? redact(result.actualModel) : '未返回'}</p>{result.error && <p className="whitespace-pre-wrap break-words">{redact(result.error)}</p>}{result.response !== null && <pre className="whitespace-pre-wrap break-words font-mono">{redact(result.response)}</pre>}</div>}</div>
  </section>;
}

export function CatalogNotice({ connection }: { connection: ConnectionWorkflow }) {
  const catalog = connection.catalog;
  return <p className="mt-1 text-[11px] leading-5 text-[var(--text-muted)]">{!catalog ? '填写凭证后从供应商拉取模型，再选择要接入的模型。' : catalog.error ? `目录拉取失败：${catalog.error}` : catalog.discoverySupported === false ? '暂无自动目录，请填写模型 ID 并验证接入。' : catalog.models.length ? `供应商返回 ${catalog.models.length} 个模型。` : '供应商未返回可用模型，可填写模型 ID 并验证接入。'}</p>;
}

function ConnectionField({ label, id, children }: { label: string; id: string; children: React.ReactNode }) {
  return <div><label htmlFor={id} className={labelClass}>{label}</label><div className="mt-1.5">{children}</div></div>;
}
