import { pageQueryKey } from '@/test-utils/seed';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import Agents from '@/features/user/agents';
import Copilot from '@/features/user/copilot';
import { mockAgents as adminAgents } from '@/features/agents/fixtures';
import { projectOpenAgents } from '@/features/user/catalog/mappers';
import { qk } from '@/api/shared/query-keys';
import { runtimeStorageKey } from '@/lib/environment';

const CHOSEN_STORAGE_KEY = runtimeStorageKey('user.agents.chosen');

/**
 * 测试环境没有后端 —— 但「收藏」「开始对话」这类写操作要走真实 mutation,
 * 不然收藏永远不生效. 这里给一个最小的假客户端:
 * 目录查询返回预置的同一份 fixture, 其余请求返回空对象.
 */
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

const openAgents = projectOpenAgents(adminAgents);
const customerAgent = openAgents.find((agent) => agent.id === 'a-customer-v3')!;

beforeAll(() => {
  // jsdom 没有实现 scrollIntoView —— 对话页发消息后会调用它.
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => cleanup());
beforeEach(() => {
  sessionStorage.removeItem(CHOSEN_STORAGE_KEY);
  fakeApi.request = async (path: string) => {
    // 写操作先判 —— 否则会被下面的目录前缀吃掉
    if (path.endsWith('/favorite')) return {};
    if (path.includes('/api/catalog/agents')) return openAgents;
    return {};
  };
  fakeApi.get = async () => [];
  fakeApi.post = async (path: string) => (path === '/api/sessions' ? { id: 'session-1' } : {});
});

function renderDirectory(path = '/agents', chosen: string[] = []) {
  if (chosen.length) sessionStorage.setItem(CHOSEN_STORAGE_KEY, JSON.stringify(chosen));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(pageQueryKey(qk.user.agents.list), openAgents);
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

  it('combines favorites and keyword filtering on chosen agents', async () => {
    renderDirectory('/agents', ['a-customer-v3', 'a-finance-v1']);
    // 收藏走后端 —— 等收藏回调落到本地状态再点下一个/再筛.
    fireEvent.click(screen.getByRole('button', { name: '收藏客户沟通助手' }));
    await screen.findByRole('button', { name: '取消收藏客户沟通助手' });
    fireEvent.click(screen.getByRole('button', { name: '收藏财务问答' }));
    await screen.findByRole('button', { name: '取消收藏财务问答' });
    fireEvent.change(screen.getByLabelText('收藏筛选'), { target: { value: 'favorites' } });
    expect(screen.getByRole('button', { name: '财务问答' })).toBeTruthy();
    fireEvent.change(screen.getByRole('textbox', { name: '搜索智能体' }), { target: { value: '客户' } });
    expect(screen.getByRole('button', { name: '客户沟通助手' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: '财务问答' })).toBeNull();
  });

  it('连点收藏两个智能体,两个都要生效', async () => {
    renderDirectory('/agents', ['a-customer-v3', 'a-finance-v1']);
    // 不 await —— 两次 mutation 重叠。React Query v5 的 observer 换人会丢掉
    // 先发那次调用的回调, 两个收藏必须都落到本地状态.
    fireEvent.click(screen.getByRole('button', { name: '收藏客户沟通助手' }));
    fireEvent.click(screen.getByRole('button', { name: '收藏财务问答' }));
    expect(await screen.findByRole('button', { name: '取消收藏客户沟通助手' })).toBeTruthy();
    expect(await screen.findByRole('button', { name: '取消收藏财务问答' })).toBeTruthy();
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

  it('starts conversation from browse drawer and carries the agent into copilot', async () => {
    renderDirectory();
    fireEvent.click(screen.getByRole('button', { name: '浏览并选用' }));
    const drawer = screen.getByRole('dialog', { name: '浏览并选用智能体' });
    fireEvent.click(within(drawer).getByRole('button', { name: '与客户沟通助手开始对话' }));
    expect(screen.getByRole('heading', { name: '与客户沟通助手对话' })).toBeTruthy();
    expect(screen.getByText('已选择智能体 · 在线会话')).toBeTruthy();
    // 智能体的示例问题带进了对话页 —— agentExample 也跟着导航状态传过去了
    expect(screen.getByRole('button', { name: customerAgent.example })).toBeTruthy();

    // 对话不再伪造本地回复 —— 这一轮真的发往后端会话
    fireEvent.click(screen.getByRole('button', { name: customerAgent.example }));
    expect(await screen.findByText(customerAgent.example)).toBeTruthy();
    expect(screen.getByText(/当前智能体/)).toBeTruthy();
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
