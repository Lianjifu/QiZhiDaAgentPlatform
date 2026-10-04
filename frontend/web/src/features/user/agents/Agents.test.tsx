import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import Agents from '@/features/user/agents';
import Copilot from '@/features/user/copilot';
import { mockAgents as adminAgents } from '@/features/agents/fixtures';
import { projectOpenAgents } from '@/features/user/catalog/mappers';
import { qk } from '@/api/shared/query-keys';

const CHOSEN_STORAGE_KEY = 'qzdap.user.agents.chosen';

afterEach(() => cleanup());
beforeEach(() => sessionStorage.removeItem(CHOSEN_STORAGE_KEY));

function renderDirectory(path = '/agents', chosen: string[] = []) {
  if (chosen.length) sessionStorage.setItem(CHOSEN_STORAGE_KEY, JSON.stringify(chosen));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData([...qk.user.agents.list, {}, 'w1'], projectOpenAgents(adminAgents));
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/agents" element={<Agents />} />
          <Route path="/team/agents" element={<Agents />} />
          <Route path="/copilot" element={<Copilot />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('智能体库', () => {
  it('opens browse drawer from empty state and adds chosen agents to the library', () => {
    renderDirectory();
    expect(screen.getByRole('heading', { name: '智能体' })).toBeTruthy();
    expect(screen.getByText('还没有选用智能体')).toBeTruthy();
    expect(screen.queryByRole('button', { name: '创建智能体' })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: '浏览并选用' }));
    const drawer = screen.getByRole('dialog', { name: '浏览并选用智能体' });
    expect(within(drawer).getByText('客户沟通助手')).toBeTruthy();

    fireEvent.change(within(drawer).getByLabelText('选用场景'), { target: { value: '数据分析' } });
    expect(within(drawer).getByText('数据洞察助手')).toBeTruthy();
    expect(within(drawer).queryByText('客户沟通助手')).toBeNull();

    fireEvent.change(within(drawer).getByLabelText('选用场景'), { target: { value: 'all' } });
    const customerRow = within(drawer).getByText('客户沟通助手').closest('li') as HTMLElement;
    fireEvent.click(within(customerRow).getByRole('button', { name: '选用' }));
    expect(within(customerRow).getByRole('button', { name: '已选用' })).toBeTruthy();
    fireEvent.click(within(drawer).getByRole('button', { name: '完成选用' }));

    expect(screen.queryByRole('dialog', { name: '浏览并选用智能体' })).toBeNull();
    expect(screen.getByRole('button', { name: '客户沟通助手' })).toBeTruthy();
    expect(screen.getByText(/已选用 1/)).toBeTruthy();
  });

  it('filters chosen agents by scene and keyword', () => {
    renderDirectory('/agents', ['a-customer-v3', 'a-insight-v2']);
    fireEvent.change(screen.getByLabelText('场景'), { target: { value: '数据分析' } });
    expect(screen.getByRole('button', { name: '数据洞察助手' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: '客户沟通助手' })).toBeNull();
    fireEvent.change(screen.getByRole('textbox', { name: '搜索智能体' }), { target: { value: '不匹配的查询' } });
    expect(screen.getByText('没有找到符合条件的智能体')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '清除筛选' }));
    expect(screen.getByRole('button', { name: '客户沟通助手' })).toBeTruthy();
  });

  it('combines favorites and keyword filtering on chosen agents', () => {
    renderDirectory('/agents', ['a-customer-v3', 'a-finance-v1']);
    fireEvent.click(screen.getByRole('button', { name: '收藏客户沟通助手' }));
    fireEvent.click(screen.getByRole('button', { name: '收藏财务问答' }));
    fireEvent.change(screen.getByLabelText('收藏筛选'), { target: { value: 'favorites' } });
    expect(screen.getByRole('button', { name: '财务问答' })).toBeTruthy();
    fireEvent.change(screen.getByRole('textbox', { name: '搜索智能体' }), { target: { value: '客户' } });
    expect(screen.getByRole('button', { name: '客户沟通助手' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: '财务问答' })).toBeNull();
  });

  it('opens details, closes on Escape and restores focus', () => {
    renderDirectory('/team/agents', ['a-flow-v1']);
    const trigger = screen.getByRole('button', { name: '工作流编排' });
    fireEvent.click(trigger);
    const dialog = screen.getByRole('dialog', { name: '工作流编排详情' });
    expect(within(dialog).getByRole('heading', { name: '工作流编排' })).toBeTruthy();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it('starts conversation from browse drawer and records a local demo reply', async () => {
    renderDirectory();
    fireEvent.click(screen.getByRole('button', { name: '浏览并选用' }));
    const drawer = screen.getByRole('dialog', { name: '浏览并选用智能体' });
    fireEvent.click(within(drawer).getByRole('button', { name: '与客户沟通助手开始对话' }));
    expect(screen.getByRole('heading', { name: '与客户沟通助手对话' })).toBeTruthy();
    expect(screen.getByText('当前智能体：客户沟通助手')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '分析这份资料并提炼结论' }));
    expect(await screen.findByText(/尚未连接真实智能体服务/)).toBeTruthy();
    expect(screen.getByRole('link', { name: '更换智能体' }).getAttribute('href')).toBe('/agents');
  });

  it('browse empty-state shortcut opens the same drawer and keeps selection', () => {
    renderDirectory();
    fireEvent.click(screen.getByRole('button', { name: '去浏览并选用' }));
    const drawer = screen.getByRole('dialog', { name: '浏览并选用智能体' });
    const row = within(drawer).getByText('财务问答').closest('li') as HTMLElement;
    fireEvent.click(within(row).getByRole('button', { name: '选用' }));
    fireEvent.click(within(drawer).getByRole('button', { name: '完成选用' }));
    expect(screen.getByRole('button', { name: '财务问答' })).toBeTruthy();
  });
});
