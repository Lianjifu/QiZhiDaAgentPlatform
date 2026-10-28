import { pageQueryKey } from '@/test-utils/seed';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import MyInsights from '@/features/user/home/MyInsights';
import MyTasks from '@/features/user/tasks';
import AccountSettings from '@/pages/shared/AccountSettings';
import { mockTasks } from '@/features/user/tasks/fixtures';
import { qk } from '@/api/shared/query-keys';

/** 测试环境没有后端 —— 任务完成这类写操作要真的"成功"才会写进本地状态. */
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

/** 效果看板的查询键把时间范围算在内 —— 每个范围都要预置一份. */
const insights = {
  points: [
    { label: '7 月', value: 92, tasks: 18 },
    { label: '8 月', value: 88, tasks: 15 },
  ],
  scenarios: [{ label: '销售支持', value: 92, detail: '成单最多', color: 'bg-[var(--brand)]' }],
  outcomes: [{ title: '周报已发出', meta: '今天', type: 'workflow', status: 'done' }],
  savedHours: 6,
};

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderTasks() {
  const qc = makeClient();
  qc.setQueryData(pageQueryKey(qk.user.tasks.list), mockTasks);
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <MyTasks />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function renderInsights() {
  const qc = makeClient();
  for (const range of ['近 7 天', '近 30 天', '本季度']) {
    qc.setQueryData(pageQueryKey(['user', 'insights', range]), insights);
  }
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <MyInsights />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function renderWith(node: ReactNode) {
  const qc = makeClient();
  qc.setQueryData(pageQueryKey(['user', 'account']), {
    displayName: '林予',
    email: 'lin@company.com',
    language: '简体中文',
    digest: true,
    taskAlert: true,
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  fakeApi.request = async (path: string) => {
    // 写操作先判 —— 否则会被下面的目录前缀吃掉
    if (path.includes('/api/tasks/')) return {};
    if (path.includes('/api/tasks')) return mockTasks;
    return {};
  };
  fakeApi.get = async () => ({});
  fakeApi.post = async () => ({});
});

afterEach(() => cleanup());

describe('效果看板', () => {
  it('switches ranges and toggles the accessible trend table', () => {
    renderInsights();
    fireEvent.click(screen.getByRole('button', { name: /近 7 天/ }));
    fireEvent.click(screen.getByRole('menuitemradio', { name: '本季度' }));
    expect(screen.getByRole('button', { name: /本季度/ })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '查看数据表' }));
    expect(document.querySelector('caption')?.textContent).toBe('智能体任务完成率趋势数据');
    expect(screen.getByText('7 月')).toBeTruthy();
  });

  it('exports the insights report as a local download', () => {
    const createObjectURL = vi.fn(() => 'blob:insights');
    const revokeObjectURL = vi.fn();
    URL.createObjectURL = createObjectURL;
    URL.revokeObjectURL = revokeObjectURL;
    let downloaded = '';
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      downloaded = this.download;
    });

    renderInsights();
    fireEvent.click(screen.getByRole('button', { name: '导出报告' }));
    // 导出在浏览器本地完成 —— 不经过后端
    expect(createObjectURL).toHaveBeenCalled();
    expect(click).toHaveBeenCalled();
    expect(downloaded).toBe('insights.json');
    expect(revokeObjectURL).toHaveBeenCalled();
    click.mockRestore();
  });
});

describe('我的任务', () => {
  it('filters and completes a pending task from the detail drawer', async () => {
    renderTasks();
    fireEvent.change(screen.getByPlaceholderText('搜索任务、来源或负责人'), { target: { value: '报价单' } });
    fireEvent.click(screen.getByRole('button', { name: /确认销售报价单/ }));
    expect(screen.getByRole('dialog', { name: '确认销售报价单详情' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '确认完成' }));
    expect((await screen.findByRole('status')).textContent).toContain('"确认销售报价单"已完成。');
  });

  it('switches to the schedule view', () => {
    renderTasks();
    fireEvent.change(screen.getByLabelText('任务视图'), { target: { value: 'schedule' } });
    expect((screen.getByLabelText('任务视图') as HTMLSelectElement).value).toBe('schedule');
  });
});

describe('设置', () => {
  it('switches setting tabs and toggles a preference', () => {
    renderWith(<AccountSettings />);
    fireEvent.click(screen.getByRole('button', { name: /通知设置/ }));
    expect(screen.getByRole('heading', { name: '通知设置' })).toBeTruthy();
    const checkbox = screen.getByRole('checkbox', { name: /任务与工作流提醒/ });
    expect((checkbox as HTMLInputElement).checked).toBe(true);
    fireEvent.click(checkbox);
    expect((checkbox as HTMLInputElement).checked).toBe(false);
  });
});
