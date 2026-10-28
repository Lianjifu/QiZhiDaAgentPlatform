import { pageQueryKey } from '@/test-utils/seed';
import type { ReactNode } from 'react';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import MyKnowledge from '@/features/user/knowledge';
import MyAutomations from '@/features/user/automations';
import MyTeam from '@/features/user/team';
import MySkills from '@/features/user/skills';
import { mockAdminSkills } from '@/features/skills/fixtures';
import { mockFlows } from '@/features/workflows/fixtures';
import { mockKbs, mockDocs } from '@/features/knowledge/fixtures';
import { mockTeams, mockMembers, mockSharedItems } from '@/features/user/team/fixtures';
import { mockAgents as adminAgents } from '@/features/agents/fixtures';
import { projectOpenSkills, projectOpenWorkflows, projectKnowledgeDocs, projectOpenAgents } from '@/features/user/catalog/mappers';
import { qk } from '@/api/shared/query-keys';
import { runtimeStorageKey } from '@/lib/environment';

const SKILLS_CHOSEN_KEY = runtimeStorageKey('user.skills.chosen');
const AUTOMATIONS_CHOSEN_KEY = runtimeStorageKey('user.automations.chosen');
const KNOWLEDGE_CHOSEN_KEY = runtimeStorageKey('user.knowledge.chosen');

/** 测试环境没有后端 —— 收藏/提问/使用记录这些写操作要真的"成功". */
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

const openSkills = projectOpenSkills(mockAdminSkills);
const openFlows = projectOpenWorkflows(mockFlows);
const openDocs = projectKnowledgeDocs(mockKbs, mockDocs);
const openAgents = projectOpenAgents(adminAgents);

function renderWithProviders(node: ReactNode, chosenSkillIds: string[] = ['skill-summary', 'tool-calendar', 'mcp-drive']) {
  sessionStorage.setItem(SKILLS_CHOSEN_KEY, JSON.stringify(chosenSkillIds));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(pageQueryKey(qk.user.skills.list), openSkills);
  qc.setQueryData(pageQueryKey(qk.user.agents.list), openAgents);
  serveCatalog({ '/api/catalog/skills': openSkills, '/api/catalog/agents': openAgents });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function wrap(qc: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

afterEach(() => cleanup());
beforeEach(() => {
  sessionStorage.removeItem(SKILLS_CHOSEN_KEY);
  sessionStorage.removeItem(AUTOMATIONS_CHOSEN_KEY);
  sessionStorage.removeItem(KNOWLEDGE_CHOSEN_KEY);
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
    configurable: true,
  });
  fakeApi.request = async () => ({});
  fakeApi.get = async () => ({});
  fakeApi.post = async (path: string) => {
    if (path.endsWith('/record-use')) return { id: 'use-1', recordedAt: '今天 10:00' };
    return {};
  };
});

/** 收藏会触发缓存失效并重新拉取 —— 假客户端要回同一份目录数据. */
function serveCatalog(catalog: Record<string, unknown>) {
  // 前缀长的先匹配 —— '/api/workspaces' 不能盖掉 '/api/workspaces/current/members'
  const entries = Object.entries(catalog).sort((a, b) => b[0].length - a[0].length);
  fakeApi.request = async (path: string) => {
    // 写操作先判 —— 否则会被下面的目录前缀吃掉
    if (path.endsWith('/record-use')) return { id: 'use-1', recordedAt: '今天 10:00' };
    if (path.endsWith('/favorite')) return {};
    const hit = entries.find(([prefix]) => path.includes(prefix));
    return hit ? hit[1] : {};
  };
}

describe('我的知识', () => {
  function renderKnowledge(chosen: string[] = ['doc-001', 'doc-006']) {
    sessionStorage.setItem(KNOWLEDGE_CHOSEN_KEY, JSON.stringify(chosen));
    const qc = makeClient();
    qc.setQueryData(pageQueryKey(qk.user.knowledge.list), openDocs);
    fakeApi.request = async (path: string) => {
      if (path.endsWith('/ask')) return { question: '产品', resourceId: 'doc-001' };
      if (path.includes('/api/catalog/knowledge')) return openDocs;
      return {};
    };
    return render(<MyKnowledge />, { wrapper: wrap(qc) });
  }

  it('filters resources and opens source details', () => {
    renderKnowledge();
    fireEvent.change(screen.getByPlaceholderText('搜索标题、团队或标签'), { target: { value: '报销' } });
    expect(screen.getAllByText('差旅报销指南.md').length).toBeGreaterThan(0);
    expect(screen.queryByText('产品手册 v3.pdf')).toBeNull();
    fireEvent.click(screen.getByText('差旅报销指南.md'));
    expect(screen.getByRole('dialog', { name: '差旅报销指南.md详情' })).toBeTruthy();
    expect(within(screen.getByRole('dialog', { name: '差旅报销指南.md详情' })).getByText('财务团队')).toBeTruthy();
  });

  it('answers from the knowledge service and opens a knowledge source', async () => {
    renderKnowledge();
    fireEvent.change(screen.getByPlaceholderText('例如：入职第一周要完成什么？'), { target: { value: '产品' } });
    fireEvent.click(screen.getByRole('button', { name: '检索知识' }));
    // 答案来自后端知识服务 —— 返回可用的引用来源
    expect(await screen.findByText('知识服务返回的参考来源')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /参考：/ }));
    expect(screen.getByRole('dialog')).toBeTruthy();
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '带入对话' }));
  });

  it('filters by tag and copies a citation', async () => {
    renderKnowledge();
    fireEvent.change(screen.getByLabelText('标签'), { target: { value: '产品' } });
    expect(screen.getByText('产品手册 v3.pdf')).toBeTruthy();
    fireEvent.click(screen.getByText('产品手册 v3.pdf'));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '复制引用' }));
    expect((await screen.findByRole('status')).textContent).toContain('引用摘要已复制');
  });
});

describe('我的工作流', () => {
  function renderAutomations(chosen: string[] = ['wf-weekly', 'wf-complaint']) {
    sessionStorage.setItem(AUTOMATIONS_CHOSEN_KEY, JSON.stringify(chosen));
    const qc = makeClient();
    qc.setQueryData(pageQueryKey(qk.user.automations.list), openFlows);
    qc.setQueryData(pageQueryKey(qk.user.automations.runs), []);
    serveCatalog({ '/api/catalog/workflows': openFlows });
    return render(<MyAutomations />, { wrapper: wrap(qc) });
  }

  it('filters published flows and records a local use', async () => {
    renderAutomations();
    fireEvent.change(screen.getByPlaceholderText('搜索工作流、场景或团队'), { target: { value: '周报' } });
    expect(screen.getByRole('button', { name: '销售周报自动整理' })).toBeTruthy();
    expect(screen.queryByText('新成员入职准备')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /使用工作流/ }));
    expect(screen.getByRole('dialog', { name: '使用销售周报自动整理' })).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText('例如：整理本周华东客户进展'), { target: { value: '本周摘要' } });
    fireEvent.click(screen.getByRole('button', { name: '确认使用' }));
    expect((await screen.findByRole('status')).textContent).toContain('使用记录已保存');
  });

  it('opens steps and favorites a flow', async () => {
    renderAutomations();
    fireEvent.click(screen.getAllByRole('button', { name: /查看步骤/ })[0]);
    expect(screen.getByRole('dialog', { name: /工作流详情/ })).toBeTruthy();
    expect(screen.getByText('定时触发')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /关闭工作流详情/ }));
    fireEvent.click(screen.getByRole('button', { name: '收藏销售周报自动整理' }));
    expect(await screen.findByRole('button', { name: '取消收藏销售周报自动整理' })).toBeTruthy();
  });
});

describe('我的技能', () => {
  it('switches capability types, favorites, and opens details', async () => {
    renderWithProviders(<MySkills />);
    fireEvent.change(screen.getByLabelText('类型'), { target: { value: 'Tool' } });
    expect(screen.getByText('日历安排工具')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '收藏日历安排工具' }));
    expect(await screen.findByRole('button', { name: '取消收藏日历安排工具' })).toBeTruthy();
    fireEvent.click(screen.getByRole('heading', { name: '日历安排工具' }));
    expect(screen.getByRole('dialog', { name: '日历安排工具详情' })).toBeTruthy();
  });

  it('confirms a Skill use and records it locally', async () => {
    renderWithProviders(<MySkills />);
    fireEvent.click(screen.getByRole('heading', { name: '资料摘要助手' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '使用能力' }));
    expect(screen.getByRole('dialog', { name: '使用资料摘要助手' })).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText('例如：整理本周客户反馈并提取三个行动项'), { target: { value: '整理本周资料' } });
    fireEvent.click(screen.getByRole('button', { name: '确认使用' }));
    expect((await screen.findByRole('status')).textContent).toContain('使用记录已保存');
  });

  it('shows open MCP capabilities from admin skills', () => {
    renderWithProviders(<MySkills />);
    fireEvent.change(screen.getByLabelText('类型'), { target: { value: 'MCP' } });
    fireEvent.click(screen.getByRole('heading', { name: '团队云盘连接' }));
    expect(screen.getByRole('dialog', { name: '团队云盘连接详情' })).toBeTruthy();
    expect(within(screen.getByRole('dialog')).getByRole('button', { name: '使用能力' })).toBeTruthy();
  });
});

describe('我的协作', () => {
  function renderTeam() {
    const qc = makeClient();
    qc.setQueryData(pageQueryKey([...qk.user.team.root, 'teams']), mockTeams);
    qc.setQueryData(pageQueryKey(qk.user.team.members), mockMembers);
    qc.setQueryData(pageQueryKey([...qk.user.team.shared, 'agents']), mockSharedItems.filter((item) => item.kind === 'agent'));
    qc.setQueryData(pageQueryKey([...qk.user.team.shared, 'knowledge']), mockSharedItems.filter((item) => item.kind === 'knowledge'));
    serveCatalog({
      '/api/catalog/agents': mockSharedItems.filter((item) => item.kind === 'agent'),
      '/api/catalog/knowledge': mockSharedItems.filter((item) => item.kind === 'knowledge'),
      '/api/workspaces/current/members': mockMembers,
      '/api/workspaces': mockTeams,
    });
    return render(<MyTeam />, { wrapper: wrap(qc) });
  }

  it('switches teams and resource tabs, then favorites a shared item', async () => {
    renderTeam();
    fireEvent.click(screen.getByRole('tab', { name: '智能体' }));
    expect(screen.getByText('需求梳理伙伴')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '收藏需求梳理伙伴' }));
    expect(await screen.findByRole('button', { name: '取消收藏需求梳理伙伴' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /客户成功组/ }));
    expect(screen.getByText('客户沟通助手')).toBeTruthy();
    expect(screen.queryByText('需求梳理伙伴')).toBeNull();
    fireEvent.click(screen.getByText('客户沟通助手'));
    expect(screen.getByRole('dialog', { name: '客户沟通助手详情' })).toBeTruthy();
  });

  it('creates an invitation through the workspace API', async () => {
    renderTeam();
    fireEvent.click(screen.getByRole('button', { name: '邀请成员' }));
    fireEvent.change(screen.getByPlaceholderText('name@company.com'), { target: { value: 'new@company.com' } });
    fireEvent.click(screen.getByRole('button', { name: '创建邀请' }));
    // 邀请落到后端 —— 页面提示"等待接受"
    expect((await screen.findByRole('status')).textContent).toContain('new@company.com');
    expect(screen.getByRole('status').textContent).toContain('等待接受');
  });
});
