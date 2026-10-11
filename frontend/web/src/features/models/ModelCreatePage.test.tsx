/**
 * ModelCreatePage 测试 — 路由 /admin/models/new
 */
import { describe, expect, it, afterEach, vi } from 'vitest';
import { cleanup, fireEvent, screen } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { renderWithProviders } from '@/test-utils/seed';
import ModelCreatePage from './ModelCreatePage';

vi.mock('./useModels', async () => {
  const actual = await vi.importActual<typeof import('./useModels')>('./useModels');
  return {
    ...actual,
    useCreateModel: () => ({ isPending: false, mutate: vi.fn() }),
    useProbeProviderModels: () => ({
      isPending: false,
      mutate: (
        vars: { protocol: string },
        opts?: { onSuccess?: (res: { models: string[]; error?: string }) => void },
      ) => {
        const models = vars.protocol === 'anthropic'
          ? ['claude-3-5-sonnet', 'claude-3-5-haiku']
          : ['gpt-4o', 'gpt-4o-mini', 'o1-preview'];
        opts?.onSuccess?.({ models });
      },
    }),
  };
});

function renderAt() {
  return renderWithProviders(
    <Routes>
      <Route path="/admin/models/new" element={<ModelCreatePage />} />
    </Routes>,
    { initialEntries: ['/admin/models/new'] },
  );
}

describe('AdminModelCreate', () => {
  afterEach(() => cleanup());

  it('keeps model list empty until probing the provider', () => {
    renderAt();
    expect(screen.getByRole('heading', { level: 1, name: '新建模型' })).toBeTruthy();
    expect(screen.getByLabelText('供应商名称')).toBeTruthy();
    expect(screen.getByLabelText('API Key')).toBeTruthy();
    expect(screen.getByLabelText('请求地址')).toBeTruthy();
    expect(screen.getByRole('radiogroup', { name: '协议' })).toBeTruthy();
    expect(screen.queryByText('gpt-4o')).toBeNull();
    expect(screen.getByText(/模型列表从供应商拉取/)).toBeTruthy();

    fireEvent.change(screen.getByLabelText('供应商名称'), { target: { value: '自建网关' } });
    fireEvent.change(screen.getByLabelText('API Key'), { target: { value: 'sk-test' } });
    fireEvent.click(screen.getByRole('button', { name: /从供应商拉取模型/ }));
    expect(screen.getByText('gpt-4o')).toBeTruthy();
    expect(screen.getByText('gpt-4o-mini')).toBeTruthy();
    expect((screen.getByRole('button', { name: /创建/ }) as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(screen.getByText('gpt-4o').closest('label')!);
    expect((screen.getByRole('button', { name: /创建 1 个模型/ }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('shows Anthropic 兼容 in the protocol radio group', () => {
    renderAt();
    expect(screen.getByRole('radio', { name: 'Anthropic 兼容' })).toBeTruthy();
  });
});
