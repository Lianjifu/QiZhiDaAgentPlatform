/**
 * Phase 23: FactoryTemplatesPage 单测 — mock useTemplatesList + useCreateTemplate.
 * 验证:
 *   - 列表渲染
 *   - 搜索过滤
 *   - 新建按钮 → 弹窗 → 必填校验 + 提交
 *   - 空态 (无数据)
 *   - 错误态
 *   - 点行跳详情
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import type { ReactElement, ReactNode } from 'react';
import type { AgentTemplate } from './useAgentFactory';

const TEMPLATES: AgentTemplate[] = [
  {
    id: 'tpl-001', tenant_id: 't', workspace_id: 'w',
    name: '售后客服', description: '处理售后咨询',
    default_model_id: 'md-deepseek', default_system_prompt: '你是售后助手。',
    status: 'active', metadata: {}, created_by: 'u-1',
    created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-10T00:00:00Z',
  },
  {
    id: 'tpl-002', tenant_id: 't', workspace_id: 'w',
    name: '销售助手', description: '辅助销售',
    default_model_id: 'md-gpt4o', default_system_prompt: '你是销售。',
    status: 'active', metadata: {}, created_by: 'u-1',
    created_at: '2026-10-05T00:00:00Z', updated_at: '2026-10-15T00:00:00Z',
  },
];

const mockMutateAsync = vi.fn();
const mockRefetch = vi.fn();
const mockCreateMutateAsync = vi.fn();

const mockListReturn: { data: { items: AgentTemplate[]; count: number } | undefined; isLoading: boolean; error: unknown } = {
  data: { items: TEMPLATES, count: TEMPLATES.length }, isLoading: false, error: undefined,
};
let listReturn = mockListReturn;
const createReturn: { mutateAsync: typeof mockCreateMutateAsync; isPending: boolean } = {
  mutateAsync: mockCreateMutateAsync, isPending: false,
};

vi.mock('./useAgentFactory', () => ({
  useTemplatesList: () => listReturn,
  useCreateTemplate: () => createReturn,
  TEMPLATE_STATUS_LABEL: { active: '活跃', archived: '已归档' },
}));

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const mod = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...mod,
    useNavigate: () => mockNavigate,
  };
});

// eslint-disable-next-line import/first
import FactoryTemplatesPage from './FactoryTemplatesPage';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  listReturn = { data: { items: TEMPLATES, count: TEMPLATES.length }, isLoading: false, error: undefined };
  mockCreateMutateAsync.mockReset();
});

function Wrapper({ children, initialEntries }: { children: ReactNode; initialEntries: string[] }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={initialEntries}>
        <Routes>
          <Route path="/admin/agents/factory" element={children} />
          <Route path="/admin/agents/factory/:id" element={<div data-testid="detail-page" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function renderAt(path: string) {
  return render(
    <Wrapper initialEntries={[path]}>
      <FactoryTemplatesPage />
    </Wrapper>,
  );
}

describe('FactoryTemplatesPage', () => {
  it('页面标题 + 描述渲染', () => {
    renderAt('/admin/agents/factory');
    expect(screen.getByText('策略智能体 · agent_factory')).toBeTruthy();
    expect(screen.getByText(/创建带策略路由的智能体/)).toBeTruthy();
  });

  it('渲染模板列表', () => {
    renderAt('/admin/agents/factory');
    expect(screen.getByText('售后客服')).toBeTruthy();
    expect(screen.getByText('销售助手')).toBeTruthy();
    // description 出现
    expect(screen.getByText('处理售后咨询')).toBeTruthy();
  });

  it('搜索按 name 过滤', () => {
    renderAt('/admin/agents/factory');
    fireEvent.change(screen.getByLabelText('搜索模板'), { target: { value: '销售' } });
    expect(screen.getByText('销售助手')).toBeTruthy();
    expect(screen.queryByText('售后客服')).toBeNull();
  });

  it('空态: 没数据时显示空提示 + 新建按钮', () => {
    listReturn = { data: { items: [], count: 0 }, isLoading: false, error: undefined };
    renderAt('/admin/agents/factory');
    expect(screen.getByText('还没有策略智能体模板')).toBeTruthy();
    expect(screen.getByText('先建一个, 再加 version + 选策略路由')).toBeTruthy();
  });

  it('空态: 有搜索时显示「没匹配」', () => {
    renderAt('/admin/agents/factory');
    fireEvent.change(screen.getByLabelText('搜索模板'), { target: { value: 'xxx' } });
    expect(screen.getByText('没有匹配的模板')).toBeTruthy();
  });

  it('loading 态', () => {
    listReturn = { data: undefined, isLoading: true, error: undefined };
    renderAt('/admin/agents/factory');
    expect(screen.getByText('加载中…')).toBeTruthy();
  });

  it('error 态', () => {
    listReturn = { data: undefined, isLoading: false, error: new Error('boom') };
    renderAt('/admin/agents/factory');
    expect(screen.getByText('加载失败,请刷新重试。')).toBeTruthy();
  });

  it('点行 → navigate 到详情', () => {
    renderAt('/admin/agents/factory');
    fireEvent.click(screen.getByText('售后客服'));
    expect(mockNavigate).toHaveBeenCalledWith('/admin/agents/factory/tpl-001');
  });

  it('新建 → 名称空时必填校验', () => {
    renderAt('/admin/agents/factory');
    fireEvent.click(screen.getAllByText('新建模板')[0]);
    // 弹窗打开
    expect(screen.getByText('新建智能体模板')).toBeTruthy();
    // 只填 model + prompt, 留空名称 → 我们 JS 校验应触发
    fireEvent.change(screen.getByPlaceholderText('deepseek-chat 或 4e01f3a7-...'), { target: { value: 'md-x' } });
    fireEvent.change(screen.getByPlaceholderText('你是一名专业、耐心、礼貌的售后客服…'), { target: { value: 'P' } });
    // 移除 required 强制让我们 JS 校验跑
    const nameInput = screen.getByPlaceholderText('例: 售后客服助手');
    nameInput.removeAttribute('required');
    fireEvent.click(screen.getByText('创建'));
    expect(screen.getByText('名称、默认模型、默认 system prompt 必填')).toBeTruthy();
  });

  it('新建提交成功 → 跳详情', async () => {
    mockCreateMutateAsync.mockResolvedValueOnce({
      id: 'tpl-new', tenant_id: 't', workspace_id: 'w',
      name: '财务审核', description: '',
      default_model_id: 'md-x', default_system_prompt: '你是财务审核。',
      status: 'active', metadata: {}, created_by: 'u',
      created_at: '2026-10-17', updated_at: '2026-10-17',
    } as AgentTemplate);
    renderAt('/admin/agents/factory');
    fireEvent.click(screen.getAllByText('新建模板')[0]);
    fireEvent.change(screen.getByPlaceholderText('例: 售后客服助手'), { target: { value: '财务审核' } });
    fireEvent.change(screen.getByPlaceholderText('deepseek-chat 或 4e01f3a7-...'), { target: { value: 'md-x' } });
    fireEvent.change(screen.getByPlaceholderText('你是一名专业、耐心、礼貌的售后客服…'), { target: { value: '你是财务审核。' } });
    fireEvent.click(screen.getByText('创建'));
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/admin/agents/factory/tpl-new'));
    expect(mockCreateMutateAsync).toHaveBeenCalledWith(expect.objectContaining({
      name: '财务审核',
      default_model_id: 'md-x',
      default_system_prompt: '你是财务审核。',
    }));
  });

  it('新建失败 → 错误信息显示', async () => {
    mockCreateMutateAsync.mockRejectedValueOnce(new Error('422 名称重复'));
    renderAt('/admin/agents/factory');
    fireEvent.click(screen.getAllByText('新建模板')[0]);
    fireEvent.change(screen.getByPlaceholderText('例: 售后客服助手'), { target: { value: 'X' } });
    fireEvent.change(screen.getByPlaceholderText('deepseek-chat 或 4e01f3a7-...'), { target: { value: 'md' } });
    fireEvent.change(screen.getByPlaceholderText('你是一名专业、耐心、礼貌的售后客服…'), { target: { value: 'P' } });
    fireEvent.click(screen.getByText('创建'));
    await waitFor(() => expect(screen.getByText('422 名称重复')).toBeTruthy());
  });

  it('弹窗取消 → 关闭', () => {
    renderAt('/admin/agents/factory');
    fireEvent.click(screen.getAllByText('新建模板')[0]);
    expect(screen.getByText('新建智能体模板')).toBeTruthy();
    fireEvent.click(screen.getByText('取消'));
    expect(screen.queryByText('新建智能体模板')).toBeNull();
  });
});
