import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import Automations from '@/features/user/automations';
import { mockFlows } from '@/features/workflows/fixtures';
import { projectOpenWorkflows } from '@/features/user/catalog/mappers';
import { qk } from '@/api/shared/query-keys';

const CHOSEN_STORAGE_KEY = 'qzdap.user.automations.chosen';

afterEach(() => cleanup());
beforeEach(() => sessionStorage.removeItem(CHOSEN_STORAGE_KEY));

function renderAutomations(chosen: string[] = []) {
  if (chosen.length) sessionStorage.setItem(CHOSEN_STORAGE_KEY, JSON.stringify(chosen));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData([...qk.user.automations.list, {}, 'w1'], projectOpenWorkflows(mockFlows));
  qc.setQueryData([...qk.user.automations.runs, 'w1'], []);
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

  it('uses a chosen workflow and records a local demo run', () => {
    renderAutomations(['wf-weekly']);
    fireEvent.click(screen.getByRole('button', { name: /使用工作流/ }));
    expect(screen.getByRole('dialog', { name: '使用销售周报自动整理' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '确认使用' }));
    expect(screen.getByRole('status').textContent).toContain('已加入本地使用记录');
  });
});
