import { pageQueryKey } from '@/test-utils/seed';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Automations from '@/features/user/automations';
import { mockFlows } from '@/features/workflows/fixtures';
import { projectOpenWorkflows } from '@/features/user/catalog/mappers';
import { qk } from '@/api/shared/query-keys';
import { runtimeStorageKey } from '@/lib/environment';

const CHOSEN_STORAGE_KEY = runtimeStorageKey('user.automations.chosen');

/** 测试环境没有后端 —— 使用记录要真的"成功"才会写进本地状态. */
const fakeApi = vi.hoisted(() => ({
  request: async (_path: string, _init?: unknown) => ({} as unknown),
  get: async (_path: string, _opts?: unknown) => ({} as unknown),
  post: async (_path: string, _body?: unknown) => ({} as unknown),
  delete: async (_path: string) => undefined as unknown,
  upload: async (_path: string, _form?: unknown) => ({} as unknown),
}));

vi.mock('@qzdap/web-api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@qzdap/web-api')>();
  return { ...actual, getApiClient: () => fakeApi };
});

const openFlows = projectOpenWorkflows(mockFlows);

afterEach(() => cleanup());
beforeEach(() => {
  sessionStorage.removeItem(CHOSEN_STORAGE_KEY);
  fakeApi.request = async (path: string) => {
    // 写操作先判 —— 否则会被下面的目录前缀吃掉
    if (path.endsWith('/run')) return { id: 'run-1', name: '销售周报自动整理', time: '今天 10:00', result: '成功' };
    if (path.endsWith('/favorite')) return {};
    if (path.includes('/api/catalog/workflows')) return openFlows;
    return {};
  };
  fakeApi.get = async () => [];
  fakeApi.post = async () => ({});
});

function renderAutomations(chosen: string[] = []) {
  if (chosen.length) sessionStorage.setItem(CHOSEN_STORAGE_KEY, JSON.stringify(chosen));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(pageQueryKey(qk.user.automations.list), openFlows);
  qc.setQueryData(pageQueryKey(qk.user.automations.runs), []);
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/automations']}>
        <Routes>
          <Route path="/automations" element={<Automations />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('工作流 · 浏览工作流', () => {
  it('opens browse drawer from admin published flows and adds to my workflows', () => {
    renderAutomations();
    expect(screen.getByRole('heading', { name: '工作流' })).toBeTruthy();
    expect(screen.getByText('还没有工作流')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: '浏览工作流' }));
    const drawer = screen.getByRole('dialog', { name: '浏览并选用工作流' });
    expect(within(drawer).getByText('销售周报自动整理')).toBeTruthy();
    expect(within(drawer).queryByText('新成员入职准备')).toBeNull();

    const row = within(drawer).getByText('销售周报自动整理').closest('li') as HTMLElement;
    fireEvent.click(within(row).getByRole('button', { name: '加入工作流' }));
    fireEvent.click(within(drawer).getByRole('button', { name: '完成' }));

    expect(screen.queryByRole('dialog', { name: '浏览并选用工作流' })).toBeNull();
    expect(screen.getByRole('button', { name: '销售周报自动整理' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '移出销售周报自动整理' }));
    expect(screen.getByText('还没有工作流')).toBeTruthy();
  });

  it('uses a chosen workflow and records a local demo run', async () => {
    renderAutomations(['wf-weekly']);
    fireEvent.click(screen.getByRole('button', { name: /使用工作流/ }));
    expect(screen.getByRole('dialog', { name: '使用销售周报自动整理' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '确认使用' }));
    expect((await screen.findByRole('status')).textContent).toContain('使用记录已保存');
  });
});
