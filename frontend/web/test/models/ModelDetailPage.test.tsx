import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, screen } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { ApiError } from '@qzdap/web-api';
import { renderWithProviders } from '@/test-utils/seed';
import ModelDetailPage from '@/features/models/ModelDetailPage';
import { mockModels } from '@/features/models/fixtures';
import type { ConnectivityTestResult, ModelDetail, ProbeModelsResult } from '@/features/models/schema';

const mock = vi.hoisted(() => ({ detail: undefined as ModelDetail | undefined, loading: false, error: null as Error | null, update: vi.fn(), probe: vi.fn(), test: vi.fn(), refetch: vi.fn() }));
vi.mock('@/features/models/useModels', () => ({
  useModelDetail: () => ({ data: mock.detail, isLoading: mock.loading, isError: !!mock.error, error: mock.error, refetch: mock.refetch }),
  useUpdateModel: () => ({ isPending: false, mutate: mock.update }),
  useProbeProviderModels: () => ({ isPending: false, mutate: mock.probe }),
  useModelConnectivityTest: () => ({ isPending: false, mutate: mock.test }),
}));
const detail: ModelDetail = { ...mockModels[0], upstreamModel: 'gpt-4o', contextWindow: 0, calls: 0, provider: { id: mockModels[0].providerId, name: mockModels[0].providerName, baseUrl: 'https://api.example.com/v1', protocol: 'openai', apiKeyMasked: '••••test', hasCredential: true } };
function renderAt() { return renderWithProviders(<Routes><Route path="/admin/models/:id" element={<ModelDetailPage />} /><Route path="/admin/models" element={<p>列表</p>} /></Routes>, { initialEntries: [`/admin/models/${detail.id}`] }); }
const button = (name: string) => screen.getByRole('button', { name }) as HTMLButtonElement;
const change = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });
beforeEach(() => { mock.detail = detail; mock.loading = false; mock.error = null; mock.update.mockReset(); mock.test.mockReset(); mock.probe.mockReset(); mock.refetch.mockReset(); mock.probe.mockImplementation((_v: unknown, cb: { onSuccess: (r: ProbeModelsResult) => void }) => cb.onSuccess({ models: ['gpt-4o', 'replacement'] })); });
afterEach(cleanup);
describe('model editing', () => {
  it('renders known model and saved credential hint without plaintext', () => { renderAt(); expect(screen.getByRole('heading', { level: 1, name: detail.name })).toBeTruthy(); expect(screen.getByText('模型工作区')).toBeTruthy(); expect((screen.getByLabelText('API Key') as HTMLInputElement).value).toBe(''); expect(screen.getByText(/留空保留/)).toBeTruthy(); });
  it('shows loading, error and not-found separately', () => { mock.loading = true; const view = renderAt(); expect(screen.getByRole('status').textContent).toContain('正在加载'); mock.loading = false; mock.error = new Error('failed'); view.unmount(); const errorView = renderAt(); expect(screen.getByRole('alert').textContent).toContain('模型加载失败'); errorView.unmount(); mock.error = new ApiError('NOT_FOUND', 'missing', 404); renderAt(); expect(screen.getByText('模型不存在或已被删除')).toBeTruthy(); });
  it('shows not-found for absent successful response', () => { mock.detail = undefined; renderAt(); expect(screen.getByText('模型不存在或已被删除')).toBeTruthy(); });
  it('pulls catalog using modelId and retained key, replaces upstream without stats patch', () => { renderAt(); fireEvent.click(button('从供应商拉取模型')); expect(mock.probe.mock.calls[0][0]).toMatchObject({ modelId: detail.id, apiKey: undefined }); change('替换上游模型', 'replacement'); fireEvent.click(button('保存修改')); const vars = mock.update.mock.calls[0][0]; expect(vars.id).toBe(detail.id); expect(vars.patch).toMatchObject({ upstreamModel: 'replacement', source: 'catalog', name: detail.name }); expect(vars.patch).not.toHaveProperty('calls'); expect(vars.patch).not.toHaveProperty('trend'); expect(vars.patch).not.toHaveProperty('successRate'); expect(vars.patch).not.toHaveProperty('providerId'); });
  it('allows provider name edit with blank saved key, keeps errors on page', () => { mock.update.mockImplementation((_v: unknown, cb: { onError: (error: Error) => void }) => cb.onError(new Error('failed'))); renderAt(); change('供应商名称', 'renamed'); fireEvent.click(button('保存修改')); expect(mock.update.mock.calls[0][0].patch.provider).toMatchObject({ name: 'renamed', apiKey: '' }); expect(screen.getByRole('alert').textContent).toContain('保存失败'); expect(screen.getByRole('heading', { name: detail.name })).toBeTruthy(); });
  it('requires revalidation after connection changes and sends verified replacement token', () => { const res: ConnectivityTestResult = { success: true, requestedModel: 'replacement', actualModel: 'replacement', statusCode: 200, latencyMs: 1, response: 'ok', error: null, verificationToken: 'token' }; mock.test.mockImplementation((_v: unknown, cb: { onSuccess: (r: ConnectivityTestResult) => void }) => cb.onSuccess(res)); renderAt(); change('请求地址', 'https://new.example/v1'); expect(button('保存修改').disabled).toBe(true); change('测试模型 ID', 'replacement'); fireEvent.click(button('测试真实调用')); fireEvent.click(button('使用已验证模型：replacement')); fireEvent.click(button('保存修改')); expect(mock.update.mock.calls[0][0].patch).toMatchObject({ upstreamModel: 'replacement', source: 'verified', verificationToken: 'token', provider: { apiKey: '' } }); });
  // 「参数与定价」面板连同后端统计一起下线了 —— 编辑页不再伪造调用量/趋势.
  it('keeps the editor free of fabricated parameters and trend', () => { renderAt(); expect(screen.queryByRole('button', { name: '参数与定价' })).toBeNull(); expect(screen.queryByText('累计调用')).toBeNull(); expect(screen.queryByText('12 周趋势')).toBeNull(); expect(screen.queryByText('暂无数据')).toBeNull(); });
  // 「路由引用」面板与 /references 端点一起下线 —— 路由规则留在路由策略里维护.
  it('leaves route references to the route rules instead of the model editor', () => { renderAt(); expect(screen.queryByRole('button', { name: '路由引用' })).toBeNull(); expect(screen.queryByText(/尚未被任何路由规则引用/)).toBeNull(); expect(screen.getByText(/保留模型标识和路由引用/)).toBeTruthy(); });
  // 「变更记录」面板与后端审计一起下线 —— 编辑页不再展示任何本地伪造的变更历史.
  it('shows no change history panel on the editor', () => { renderAt(); expect(screen.queryByRole('button', { name: '变更记录' })).toBeNull(); expect(screen.queryByText('暂无变更记录。')).toBeNull(); expect(screen.queryByText(/审计员/)).toBeNull(); });
});
