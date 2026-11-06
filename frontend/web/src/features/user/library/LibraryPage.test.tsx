/**
 * **资源库** ✓ —— 四个页签合到一页之后的回归 ✓。
 *
 * ⚠️ **原来有四个测试文件** ✓（智能体 / 知识 / 技能 / 工作流 ✓）—— 现在
 * 一页四个页签 ✓ → 一个文件 ✓（骨架共用 ✓ → 断言也共用 ✓）。
 */

import { pageQueryKey } from '@/test-utils/seed';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import Library from '@/features/user/library/LibraryPage';
import Copilot from '@/features/user/copilot';
import { mockAgents as adminAgents } from '@/features/agents/fixtures';
import { mockAdminSkills } from '@/features/skills/fixtures';
import { mockFlows } from '@/features/workflows/fixtures';
import { mockKbs, mockDocs } from '@/features/knowledge/fixtures';
import {
  projectOpenAgents,
  projectOpenSkills,
  projectOpenWorkflows,
  projectKnowledgeDocs,
} from '@/features/user/catalog/mappers';
import { qk } from '@/api/shared/query-keys';
import { runtimeStorageKey } from '@/lib/environment';

const AGENTS_KEY = runtimeStorageKey('user.agents.chosen');
const SKILLS_KEY = runtimeStorageKey('user.skills.chosen');
const AUTOMATIONS_KEY = runtimeStorageKey('user.automations.chosen');
const KNOWLEDGE_KEY = runtimeStorageKey('user.knowledge.chosen');

/**
 * 测试环境没有后端 —— 但「收藏」「选用」「开始对话」这类写操作要走真实
 * mutation, 不然收藏永远不生效. 这里给一个最小的假客户端.
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
const openSkills = projectOpenSkills(mockAdminSkills);
const openFlows = projectOpenWorkflows(mockFlows);
const openDocs = projectKnowledgeDocs(mockKbs, mockDocs);
const customerAgent = openAgents.find((agent) => agent.id === 'a-customer-v3')!;

beforeAll(() => {
  // jsdom 没有实现 scrollIntoView —— 对话页发消息后会调用它.
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => cleanup());
beforeEach(() => {
  [AGENTS_KEY, SKILLS_KEY, AUTOMATIONS_KEY, KNOWLEDGE_KEY].forEach((key) =>
    sessionStorage.removeItem(key),
  );
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
    configurable: true,
  });
  fakeApi.request = async (path: string) => {
    if (path.endsWith('/record-use')) return { id: 'use-1', recordedAt: '今天 10:00' };
    if (path.endsWith('/favorite')) return {};
    if (path.includes('/api/catalog/agents')) return openAgents;
    if (path.includes('/api/catalog/skills')) return openSkills;
    if (path.includes('/api/catalog/workflows')) return openFlows;
    if (path.includes('/api/catalog/knowledge')) return openDocs;
    return {};
  };
  fakeApi.get = async () => [];
  fakeApi.post = async (path: string) => (path === '/api/sessions' ? { id: 'session-1' } : {});
});

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderLibrary(tab: string, chosen?: { key: string; ids: string[] }) {
  if (chosen) sessionStorage.setItem(chosen.key, JSON.stringify(chosen.ids));
  const qc = makeClient();
  qc.setQueryData(pageQueryKey(qk.user.agents.list), openAgents);
  qc.setQueryData(pageQueryKey(qk.user.skills.list), openSkills);
  qc.setQueryData(pageQueryKey(qk.user.automations.list), openFlows);
  qc.setQueryData(pageQueryKey(qk.user.automations.runs), []);
  qc.setQueryData(pageQueryKey(qk.user.knowledge.list), openDocs);
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/library?tab=${tab}`]}>
        <Routes>
          <Route path="/library" element={<Library />} />
          <Route path="/copilot" element={<Copilot />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('资源库 · 智能体页签', () => {
  it('opens browse drawer from empty state and adds chosen agents to the library', () => {
    renderLibrary('agents');
    expect(screen.getByText('还没有选用智能体')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: '浏览并选用' }));
    const drawer = screen.getByRole('dialog', { name: '浏览并选用' });
    expect(within(drawer).getByText('客户沟通助手')).toBeTruthy();

    fireEvent.change(within(drawer).getByLabelText('场景'), { target: { value: '数据分析' } });
    expect(within(drawer).getByText('数据洞察助手')).toBeTruthy();
    expect(within(drawer).queryByText('客户沟通助手')).toBeNull();

    fireEvent.change(within(drawer).getByLabelText('场景'), { target: { value: 'all' } });
    const customerRow = within(drawer).getByText('客户沟通助手').closest('li') as HTMLElement;
    fireEvent.click(within(customerRow).getByRole('button', { name: '选用' }));
    expect(within(customerRow).getByRole('button', { name: '已选用' })).toBeTruthy();
    fireEvent.click(within(drawer).getByRole('button', { name: '完成选用' }));

    expect(screen.queryByRole('dialog', { name: '浏览并选用' })).toBeNull();
    expect(screen.getByRole('button', { name: '客户沟通助手' })).toBeTruthy();
    expect(screen.getByText(/已选用 1/)).toBeTruthy();
  });

  it('filters chosen agents by scene and keyword', () => {
    renderLibrary('agents', { key: AGENTS_KEY, ids: ['a-customer-v3', 'a-insight-v2'] });
    fireEvent.change(screen.getByLabelText('场景'), { target: { value: '数据分析' } });
    expect(screen.getByRole('button', { name: '数据洞察助手' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: '客户沟通助手' })).toBeNull();
    fireEvent.change(screen.getByRole('textbox', { name: '搜索智能体' }), {
      target: { value: '不匹配的查询' },
    });
    expect(screen.getByText('没有找到符合条件的智能体')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '清除筛选' }));
    expect(screen.getByRole('button', { name: '客户沟通助手' })).toBeTruthy();
  });

  it('combines favorites and keyword filtering on chosen agents', async () => {
    renderLibrary('agents', { key: AGENTS_KEY, ids: ['a-customer-v3', 'a-finance-v1'] });
    fireEvent.click(screen.getByRole('button', { name: '收藏客户沟通助手' }));
    await screen.findByRole('button', { name: '取消收藏客户沟通助手' });
    fireEvent.click(screen.getByRole('button', { name: '收藏财务问答' }));
    await screen.findByRole('button', { name: '取消收藏财务问答' });
    fireEvent.change(screen.getByLabelText('收藏筛选'), { target: { value: 'favorites' } });
    expect(screen.getByRole('button', { name: '财务问答' })).toBeTruthy();
    fireEvent.change(screen.getByRole('textbox', { name: '搜索智能体' }), {
      target: { value: '客户' },
    });
    expect(screen.getByRole('button', { name: '客户沟通助手' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: '财务问答' })).toBeNull();
  });

  it('opens details, closes on Escape and restores focus', () => {
    renderLibrary('agents', { key: AGENTS_KEY, ids: ['a-flow-v1'] });
    const trigger = screen.getByRole('button', { name: '工作流编排' });
    fireEvent.click(trigger);
    const dialog = screen.getByRole('dialog', { name: '工作流编排详情' });
    expect(within(dialog).getByRole('heading', { name: '工作流编排' })).toBeTruthy();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it('starts conversation from browse drawer and carries the agent into copilot', async () => {
    renderLibrary('agents');
    fireEvent.click(screen.getByRole('button', { name: '浏览并选用' }));
    const drawer = screen.getByRole('dialog', { name: '浏览并选用' });
    fireEvent.click(within(drawer).getByRole('button', { name: '与客户沟通助手开始对话' }));
    expect(screen.getByRole('heading', { name: '与客户沟通助手对话' })).toBeTruthy();
    // ⚠️ **头部显示的是真的智能体名** ✓（不是编的 ✓）。
    expect(screen.getByText('客户沟通助手')).toBeTruthy();
    expect(screen.getByRole('button', { name: customerAgent.example })).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: customerAgent.example }));
    expect(await screen.findByText(customerAgent.example)).toBeTruthy();
    // ⚠️ **「当前智能体」收进头部了** ✓ —— 名字还在 ✓（不再浮在消息流中间 ✓）。
    expect(screen.getByText('客户沟通助手')).toBeTruthy();
    expect(screen.getByRole('link', { name: '更换智能体' }).getAttribute('href')).toBe(
      '/library?tab=agents',
    );
  });
});

describe('资源库 · 知识页签', () => {
  it('filters resources and opens source details', () => {
    renderLibrary('knowledge', { key: KNOWLEDGE_KEY, ids: ['doc-001', 'doc-006'] });
    fireEvent.change(screen.getByPlaceholderText('搜索标题、团队或标签'), {
      target: { value: '报销' },
    });
    expect(screen.getAllByText('差旅报销指南.md').length).toBeGreaterThan(0);
    expect(screen.queryByText('产品手册 v3.pdf')).toBeNull();
    fireEvent.click(screen.getByText('差旅报销指南.md'));
    expect(screen.getByRole('dialog', { name: '差旅报销指南.md详情' })).toBeTruthy();
    expect(within(screen.getByRole('dialog', { name: '差旅报销指南.md详情' })).getByText('财务团队')).toBeTruthy();
  });

  it('answers from the knowledge service and opens a knowledge source', async () => {
    renderLibrary('knowledge', { key: KNOWLEDGE_KEY, ids: ['doc-001', 'doc-006'] });
    fakeApi.request = async (path: string) => {
      if (path.endsWith('/ask')) return { question: '产品', resourceId: 'doc-001' };
      if (path.includes('/api/catalog/knowledge')) return openDocs;
      return {};
    };
    fireEvent.change(screen.getByPlaceholderText('例如：报销标准是什么？'), {
      target: { value: '产品' },
    });
    fireEvent.click(screen.getByRole('button', { name: '检索知识' }));
    expect(await screen.findByText('知识服务返回的参考来源')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /参考：/ }));
    expect(screen.getByRole('dialog')).toBeTruthy();
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '带入对话' }));
  });

  it('filters by tag and copies a citation', async () => {
    renderLibrary('knowledge', { key: KNOWLEDGE_KEY, ids: ['doc-001', 'doc-006'] });
    fireEvent.change(screen.getByLabelText('标签'), { target: { value: '产品' } });
    expect(screen.getByText('产品手册 v3.pdf')).toBeTruthy();
    fireEvent.click(screen.getByText('产品手册 v3.pdf'));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '复制引用' }));
    expect((await screen.findByRole('status')).textContent).toContain('引用摘要已复制');
  });
});

describe('资源库 · 工作流页签', () => {
  it('filters published flows and records a local use', async () => {
    renderLibrary('automations', { key: AUTOMATIONS_KEY, ids: ['wf-weekly', 'wf-complaint'] });
    fireEvent.change(screen.getByPlaceholderText('搜索工作流、场景或团队'), {
      target: { value: '周报' },
    });
    expect(screen.getByRole('button', { name: '销售周报自动整理' })).toBeTruthy();
    expect(screen.queryByText('新成员入职准备')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /运行/ }));
    expect(screen.getByRole('dialog', { name: '使用销售周报自动整理' })).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText('例如：整理本周华东客户进展'), {
      target: { value: '本周摘要' },
    });
    fireEvent.click(screen.getByRole('button', { name: '确认使用' }));
    expect((await screen.findByRole('status')).textContent).toContain('执行完成');
  });

  it('opens steps and favorites a flow', async () => {
    renderLibrary('automations', { key: AUTOMATIONS_KEY, ids: ['wf-weekly', 'wf-complaint'] });
    fireEvent.click(screen.getAllByRole('button', { name: /查看步骤/ })[0]);
    expect(screen.getByRole('dialog', { name: /工作流详情/ })).toBeTruthy();
    expect(screen.getByText(/定时触发/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /关闭工作流详情/ }));
    fireEvent.click(screen.getByRole('button', { name: '收藏销售周报自动整理' }));
    expect(await screen.findByRole('button', { name: '取消收藏销售周报自动整理' })).toBeTruthy();
  });
});

describe('资源库 · 技能页签', () => {
  it('switches capability types, favorites, and opens details', async () => {
    renderLibrary('skills', {
      key: SKILLS_KEY,
      ids: ['skill-summary', 'tool-calendar', 'mcp-drive'],
    });
    fireEvent.change(screen.getByLabelText('类型'), { target: { value: 'Tool' } });
    expect(screen.getByText('日历安排工具')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '收藏日历安排工具' }));
    expect(await screen.findByRole('button', { name: '取消收藏日历安排工具' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '日历安排工具' }));
    expect(screen.getByRole('dialog', { name: '日历安排工具详情' })).toBeTruthy();
  });

  it('confirms a Skill use and records it locally', async () => {
    renderLibrary('skills', {
      key: SKILLS_KEY,
      ids: ['skill-summary', 'tool-calendar', 'mcp-drive'],
    });
    fireEvent.click(screen.getByRole('button', { name: '资料摘要助手' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '开始使用' }));
    expect(screen.getByRole('dialog', { name: '使用资料摘要助手' })).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText('例如：整理本周客户反馈并提取三个行动项'), {
      target: { value: '整理本周资料' },
    });
    fireEvent.click(screen.getByRole('button', { name: '确认使用' }));
    expect((await screen.findByRole('status')).textContent).toContain('使用记录已保存');
  });

  it('shows open MCP capabilities from admin skills', () => {
    renderLibrary('skills', {
      key: SKILLS_KEY,
      ids: ['skill-summary', 'tool-calendar', 'mcp-drive'],
    });
    fireEvent.change(screen.getByLabelText('类型'), { target: { value: 'MCP' } });
    fireEvent.click(screen.getByRole('button', { name: '团队云盘连接' }));
    expect(screen.getByRole('dialog', { name: '团队云盘连接详情' })).toBeTruthy();
    expect(within(screen.getByRole('dialog')).getByRole('button', { name: '开始使用' })).toBeTruthy();
  });
});
