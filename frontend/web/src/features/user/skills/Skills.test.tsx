import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import Skills from '@/features/user/skills';
import Copilot from '@/features/user/copilot';
import { mockAdminSkills } from '@/features/skills/fixtures';
import { mockAgents as adminAgents } from '@/features/agents/fixtures';
import { projectOpenSkills, projectOpenAgents } from '@/features/user/catalog/mappers';
import { qk } from '@/api/shared/query-keys';

const CHOSEN_STORAGE_KEY = 'qzdap.user.skills.chosen';

afterEach(() => cleanup());
beforeEach(() => {
  sessionStorage.removeItem(CHOSEN_STORAGE_KEY);
  sessionStorage.removeItem('qzdap.user.agents.chosen');
});

function renderSkills(chosen: string[] = []) {
  if (chosen.length) sessionStorage.setItem(CHOSEN_STORAGE_KEY, JSON.stringify(chosen));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData([...qk.user.skills.list, {}, 'w1'], projectOpenSkills(mockAdminSkills));
  qc.setQueryData([...qk.user.agents.list, {}, 'w1'], projectOpenAgents(adminAgents));
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/skills']}>
        <Routes>
          <Route path="/skills" element={<Skills />} />
          <Route path="/copilot" element={<Copilot />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('技能 · 浏览能力', () => {
  it('opens browse drawer and adds chosen capabilities with related agents', () => {
    renderSkills();
    expect(screen.getByRole('heading', { name: '技能' })).toBeTruthy();
    expect(screen.getByText('还没有技能')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: '浏览能力' }));
    const drawer = screen.getByRole('dialog', { name: '浏览并选用能力' });
    expect(within(drawer).getByText('资料摘要助手')).toBeTruthy();
    expect(within(drawer).getAllByText('关联智能体').length).toBeGreaterThan(0);
    expect(within(drawer).getByRole('button', { name: '用客户沟通助手使用资料摘要助手' })).toBeTruthy();

    const row = within(drawer).getByText('资料摘要助手').closest('li') as HTMLElement;
    fireEvent.click(within(row).getByRole('button', { name: '加入技能' }));
    fireEvent.click(within(drawer).getByRole('button', { name: '完成' }));

    expect(screen.queryByRole('dialog', { name: '浏览并选用能力' })).toBeNull();
    expect(screen.getByRole('heading', { name: '资料摘要助手' })).toBeTruthy();
    expect(screen.getByText(/关联 客户沟通助手/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '移出资料摘要助手' }));
    expect(screen.getByText('还没有技能')).toBeTruthy();
  });

  it('starts copilot with related agent and skill context', () => {
    renderSkills();
    fireEvent.click(screen.getByRole('button', { name: '浏览能力' }));
    const drawer = screen.getByRole('dialog', { name: '浏览并选用能力' });
    fireEvent.click(within(drawer).getByRole('button', { name: '用客户沟通助手使用资料摘要助手' }));

    expect(screen.getByRole('heading', { name: '与客户沟通助手对话' })).toBeTruthy();
    expect(screen.getByText(/当前智能体：客户沟通助手 · 能力：资料摘要助手/)).toBeTruthy();
  });

  it('records local use from chosen capability details', () => {
    renderSkills(['skill-summary']);
    fireEvent.click(screen.getByRole('heading', { name: '资料摘要助手' }));
    fireEvent.click(within(screen.getByRole('dialog', { name: '资料摘要助手详情' })).getByRole('button', { name: '使用能力' }));
    fireEvent.change(screen.getByPlaceholderText('例如：整理本周客户反馈并提取三个行动项'), { target: { value: '整理本周资料' } });
    fireEvent.click(screen.getByRole('button', { name: '确认使用' }));
    expect(screen.getByRole('status').textContent).toContain('已加入本地使用记录');
  });
});
