import { pageQueryKey } from '@/test-utils/seed';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import Skills from '@/features/user/skills';
import Copilot from '@/features/user/copilot';
import { mockAdminSkills } from '@/features/skills/fixtures';
import { mockAgents as adminAgents } from '@/features/agents/fixtures';
import { projectOpenSkills, projectOpenAgents } from '@/features/user/catalog/mappers';
import { qk } from '@/api/shared/query-keys';
import { runtimeStorageKey } from '@/lib/environment';

const CHOSEN_STORAGE_KEY = runtimeStorageKey('user.skills.chosen');

/** 测试环境没有后端 —— 收藏/使用记录要真的"成功"才能落到本地状态. */
const fakeApi = vi.hoisted(() => ({
  request: async (_path: string, _init?: unknown) => ({} as unknown),
  get: async (_path: string, _opts?: unknown) => ({} as unknown),
  post: async (_path: string, _body?: unknown) => ({} as unknown),
  delete: async (_path: string) => undefined as unknown,
  upload: async (_path: string, _form?: unknown) => ({} as unknown),
  streamEvents: async function* () {
    // 空流: 对话页不产出任何后端事件.
  },
}));

vi.mock('@qzdap/web-api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@qzdap/web-api')>();
  return { ...actual, getApiClient: () => fakeApi };
});

const openSkills = projectOpenSkills(mockAdminSkills);
const openAgents = projectOpenAgents(adminAgents);
const summarySkill = openSkills.find((skill) => skill.id === 'skill-summary')!;
const customerAgent = openAgents.find((agent) => agent.name === '客户沟通助手')!;

beforeAll(() => {
  // jsdom 没有实现 scrollIntoView —— 对话页发消息后会调用它.
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => cleanup());
beforeEach(() => {
  sessionStorage.removeItem(CHOSEN_STORAGE_KEY);
  sessionStorage.removeItem(runtimeStorageKey('user.agents.chosen'));
  fakeApi.request = async (path: string) => {
    // 写操作先判 —— 否则会被下面的目录前缀吃掉
    if (path.endsWith('/record-use')) return { id: 'use-1', recordedAt: '今天 10:00' };
    if (path.endsWith('/favorite')) return {};
    if (path === '/api/sessions') return { id: 'session-1' };
    if (path.includes('/api/catalog/skills')) return openSkills;
    if (path.includes('/api/catalog/agents')) return openAgents;
    return {};
  };
  fakeApi.get = async () => [];
  // 对话页用 post 建会话 —— 要给一个会话 id, 否则这一轮会被回滚
  fakeApi.post = async (path: string) => (path === '/api/sessions' ? { id: 'session-1' } : {});
});

function renderSkills(chosen: string[] = []) {
  if (chosen.length) sessionStorage.setItem(CHOSEN_STORAGE_KEY, JSON.stringify(chosen));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(pageQueryKey(qk.user.skills.list), openSkills);
  qc.setQueryData(pageQueryKey(qk.user.agents.list), openAgents);
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
  it('opens browse drawer and adds chosen capabilities with related agents', async () => {
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

  it('starts copilot with related agent and skill context', async () => {
    renderSkills();
    fireEvent.click(screen.getByRole('button', { name: '浏览能力' }));
    const drawer = screen.getByRole('dialog', { name: '浏览并选用能力' });
    fireEvent.click(within(drawer).getByRole('button', { name: '用客户沟通助手使用资料摘要助手' }));

    expect(screen.getByRole('heading', { name: '与客户沟通助手对话' })).toBeTruthy();
    // 能力上下文带进了输入框
    expect((screen.getByPlaceholderText('描述你想完成的工作...') as HTMLTextAreaElement).value)
      .toContain('资料摘要助手');

    // 发一轮对话 —— 顶部横幅展示当前智能体与能力
    fireEvent.click(screen.getByRole('button', { name: customerAgent.example }));
    expect(await screen.findByText(/当前智能体/)).toBeTruthy();
    expect(screen.getByText(/能力:资料摘要助手/)).toBeTruthy();
  });

  it('records local use from chosen capability details', async () => {
    renderSkills(['skill-summary']);
    fireEvent.click(screen.getByRole('heading', { name: '资料摘要助手' }));
    fireEvent.click(within(screen.getByRole('dialog', { name: '资料摘要助手详情' })).getByRole('button', { name: '使用能力' }));
    fireEvent.change(screen.getByPlaceholderText('例如：整理本周客户反馈并提取三个行动项'), { target: { value: '整理本周资料' } });
    fireEvent.click(screen.getByRole('button', { name: '确认使用' }));
    expect(await screen.findByRole('status')).toHaveProperty('textContent');
    expect(screen.getByRole('status').textContent).toContain('使用记录已保存');
    // 这次使用进了"最近使用" —— 卡片标题之外多了一处同名条目
    expect(screen.getAllByText('资料摘要助手').length).toBeGreaterThan(1);
    expect(summarySkill.name).toBe('资料摘要助手');
  });

  it('连点收藏两个能力,两个都要生效', async () => {
    renderSkills(['skill-summary', 'skill-followup']);
    // 不 await —— 两次 mutation 重叠,先发那次的回调会被 React Query v5 的
    // observer 换人丢掉. 两个收藏必须都落到本地状态.
    fireEvent.click(screen.getByRole('button', { name: '收藏资料摘要助手' }));
    fireEvent.click(screen.getByRole('button', { name: '收藏客户跟进建议' }));
    expect(await screen.findByRole('button', { name: '取消收藏资料摘要助手' })).toBeTruthy();
    expect(await screen.findByRole('button', { name: '取消收藏客户跟进建议' })).toBeTruthy();
  });
});
