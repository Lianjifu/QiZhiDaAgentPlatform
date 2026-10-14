import { ApiError } from '@qzdap/web-api';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, screen } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { renderWithProviders } from '@/test-utils/seed';
import ModelCreatePage from '@/features/models/ModelCreatePage';
import type { ConnectivityTestResult, ConnectivityTestVars, ProbeModelsResult, ProbeModelsVars } from '@/features/models/schema';

type Callbacks<T> = { onSuccess?: (result: T) => void; onError?: (error: Error) => void };
const mock = vi.hoisted(() => ({ create: vi.fn(), probe: vi.fn(), test: vi.fn(), testPending: false, probePending: false }));
vi.mock('@/features/models/useModels', () => ({
  useCreateModel: () => ({ isPending: false, mutate: mock.create }),
  useProbeProviderModels: () => ({ isPending: mock.probePending, mutate: mock.probe }),
  useModelConnectivityTest: () => ({ isPending: mock.testPending, mutate: mock.test }),
}));
const result: ConnectivityTestResult = { success: true, latencyMs: 12, statusCode: 200, requestedModel: 'custom-model', actualModel: 'upstream-model', response: '<script>alert(1)</script>', error: null, verificationToken: 'verified-token' };
const change = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });
const button = (name: string | RegExp) => screen.getByRole('button', { name }) as HTMLButtonElement;
function renderAt() { return renderWithProviders(<Routes><Route path="/admin/models/new" element={<ModelCreatePage />} /></Routes>, { initialEntries: ['/admin/models/new'] }); }
function credentials() { change('供应商名称', '自建网关'); change('API Key', 'sk-secret'); }
function testCustom() { credentials(); change('测试模型 ID', 'custom-model'); fireEvent.click(button('测试真实调用')); }

beforeEach(() => {
  mock.create.mockReset(); mock.probe.mockReset(); mock.test.mockReset(); mock.testPending = false; mock.probePending = false;
  mock.probe.mockImplementation((_vars: ProbeModelsVars, cb: Callbacks<ProbeModelsResult>) => cb.onSuccess?.({ models: ['gpt-4o', 'gpt-4o-mini'] }));
  mock.test.mockImplementation((_vars: ConnectivityTestVars, cb: Callbacks<ConnectivityTestResult>) => cb.onSuccess?.(result));
});
afterEach(cleanup);
describe('model creation and real connectivity', () => {
  it('keeps empty catalog, defaults test ID after pull and does not select test ID for creation', () => {
    renderAt(); expect(screen.getByRole('heading', { name: '新建模型' })).toBeTruthy(); expect(screen.getByRole('radiogroup', { name: '协议' })).toBeTruthy(); expect(screen.getByText(/模型列表从供应商拉取/)).toBeTruthy();
    expect(button('测试真实调用').disabled).toBe(true); credentials(); fireEvent.click(button('从供应商拉取模型'));
    expect((screen.getByLabelText('测试模型 ID') as HTMLInputElement).value).toBe('gpt-4o'); expect(button(/创建/).disabled).toBe(true);
    fireEvent.click(screen.getByRole('checkbox', { name: 'gpt-4o' })); expect(button('创建 1 个模型').disabled).toBe(false);
    fireEvent.click(button('创建 1 个模型')); expect(mock.create.mock.calls[0][0]).toMatchObject({ models: ['gpt-4o'], source: 'catalog' });
  });
  it('keeps manually entered test model when catalog arrives', () => {
    renderAt(); credentials(); change('测试模型 ID', 'private-model'); fireEvent.click(button('从供应商拉取模型'));
    expect((screen.getByLabelText('测试模型 ID') as HTMLInputElement).value).toBe('private-model');
  });
  it('tests before catalog and requires explicit verified-model selection for custom creation', () => {
    renderAt(); testCustom(); expect(mock.test.mock.calls[0][0]).toMatchObject({ apiKey: 'sk-secret', model: 'custom-model', protocol: 'openai' });
    expect(screen.getByText('测试成功')).toBeTruthy(); expect(screen.getByText('实际模型：upstream-model')).toBeTruthy(); expect(screen.getByText('<script>alert(1)</script>')).toBeTruthy(); expect(document.querySelector('script')).toBeNull();
    expect(button(/创建/).disabled).toBe(true); fireEvent.click(button(/接入已验证模型/)); fireEvent.click(button('创建 1 个模型'));
    expect(mock.create.mock.calls[0][0]).toMatchObject({ source: 'verified', verificationToken: 'verified-token', models: ['custom-model'] });
  });
  it.each(['API Key', '请求地址', '测试模型 ID'])('clears success and verification on %s edit', label => {
    renderAt(); testCustom(); fireEvent.click(button(/接入已验证模型/)); change(label, 'changed-value'); expect(screen.queryByText('测试成功')).toBeNull(); expect(button(/创建/).disabled).toBe(true);
  });
  it('protocol switch resets response and supports expanded providers', () => {
    renderAt(); testCustom(); fireEvent.click(screen.getByRole('radio', { name: '通义千问' })); expect(screen.queryByText('测试成功')).toBeNull(); expect((screen.getByLabelText('请求地址') as HTMLInputElement).value).toBe('');
    for (const name of ['Google Gemini', 'DeepSeek', '智谱 GLM', 'Kimi', 'MiniMax', 'Anthropic 兼容']) expect(screen.getByRole('radio', { name })).toBeTruthy();
  });
  it('shows Azure version and deployment name, sends optional version', () => {
    renderAt(); fireEvent.click(screen.getByRole('radio', { name: 'Azure OpenAI' })); credentials(); expect((screen.getByLabelText('API 版本（可选）') as HTMLInputElement).value).toBe('2024-10-21'); change('测试部署名称', 'deployment'); change('API 版本（可选）', '2025-01-01'); fireEvent.click(button('测试真实调用')); expect(mock.test.mock.calls[0][0]).toMatchObject({ protocol: 'azure', model: 'deployment', apiVersion: '2025-01-01' });
  });
  it('shows failure and hides any echoed credential', () => {
    mock.test.mockImplementation((_v: ConnectivityTestVars, cb: Callbacks<ConnectivityTestResult>) => cb.onSuccess?.({ ...result, success: false, statusCode: 401, error: 'denied sk-secret', verificationToken: undefined }));
    renderAt(); testCustom(); expect(screen.getByText('测试失败')).toBeTruthy(); expect(screen.getByText(/denied \[已隐藏密钥\]/)).toBeTruthy(); expect(screen.queryByText('denied sk-secret')).toBeNull(); expect(screen.queryByRole('button', { name: /接入已验证模型/ })).toBeNull();
  });
  it('shows transport errors and unsupported discovery honestly', () => {
    mock.probe.mockImplementation((_v: ProbeModelsVars, cb: Callbacks<ProbeModelsResult>) => cb.onSuccess?.({ models: [], discoverySupported: false }));
    mock.test.mockImplementation((_v: ConnectivityTestVars, cb: Callbacks<ConnectivityTestResult>) => cb.onError?.(new Error('sk-secret')));
    renderAt(); credentials(); fireEvent.click(button('从供应商拉取模型')); expect(screen.getByText(/暂无自动目录/)).toBeTruthy(); change('测试模型 ID', 'custom-model'); fireEvent.click(button('测试真实调用')); expect(screen.getByText('测试失败')).toBeTruthy(); expect(screen.getByText(/请求失败/)).toBeTruthy();
  });
  it('disables during pending and rejects stale callbacks', () => {
    let callbacks!: Callbacks<ConnectivityTestResult>; mock.test.mockImplementation((_v: ConnectivityTestVars, cb: Callbacks<ConnectivityTestResult>) => { callbacks = cb; });
    const view = renderAt(); testCustom(); mock.testPending = true; change('测试模型 ID', 'another-model'); expect(button('正在测试…').disabled).toBe(true);
    act(() => callbacks.onSuccess?.(result)); expect(screen.queryByText('测试成功')).toBeNull(); view.unmount();
  });
  it('ignores stale catalog after credential change', () => {
    let cb!: Callbacks<ProbeModelsResult>; mock.probe.mockImplementation((_v: ProbeModelsVars, opts: Callbacks<ProbeModelsResult>) => { cb = opts; });
    renderAt(); credentials(); fireEvent.click(button('从供应商拉取模型')); change('API Key', 'new-key'); act(() => cb.onSuccess?.({ models: ['old-catalog'] })); expect(screen.queryByRole('checkbox')).toBeNull();
  });
  it('distinguishes platform authentication failure from provider credentials', () => {
    mock.probe.mockImplementation((_v: ProbeModelsVars, cb: Callbacks<ProbeModelsResult>) => cb.onError?.(new ApiError('HTTP_401', 'authentication required', 401)));
    renderAt(); credentials(); fireEvent.click(button('从供应商拉取模型'));
    expect(screen.getByText(/平台登录已失效/)).toBeTruthy();
    expect(screen.getByRole('link', { name: '重新登录平台' }).getAttribute('href')).toBe('/login');
  });
  it('shows platform login failure for inference without treating it as supplier HTTP status', () => {
    mock.test.mockImplementation((_v: ConnectivityTestVars, cb: Callbacks<ConnectivityTestResult>) => cb.onError?.(new ApiError('HTTP_401', 'authentication required', 401)));
    renderAt(); testCustom(); expect(screen.getByText(/平台登录已失效/)).toBeTruthy();
    expect(screen.getByText(/HTTP 状态：无响应/)).toBeTruthy();
  });
  it('warns when DeepSeek OpenAI preset uses an Anthropic endpoint', () => {
    renderAt(); fireEvent.click(screen.getByRole('radio', { name: 'DeepSeek' }));
    change('请求地址', 'https://api.deepseek.com/anthropic');
    expect(screen.getByRole('alert').textContent).toContain('请选择 Anthropic 兼容');
  });
  it('keeps creation errors on page', () => {
    mock.create.mockImplementation((_v: unknown, cb: Callbacks<unknown>) => cb.onError?.(new Error('failed')));
    renderAt(); credentials(); fireEvent.click(button('从供应商拉取模型')); fireEvent.click(screen.getByRole('checkbox', { name: 'gpt-4o' })); fireEvent.click(button('创建 1 个模型')); expect(screen.getByRole('alert').textContent).toContain('创建失败');
  });
});
