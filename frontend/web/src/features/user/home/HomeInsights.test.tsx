import { pageQueryKey } from '@/test-utils/seed';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it } from 'vitest';
import Home from './Home';
import { qk } from '@/api/shared/query-keys';

/** 效果摘要的查询键把时间范围算在内 —— 每个范围都要预置一份. */
const insights = {
  points: [
    { label: '7 月', value: 92, tasks: 18 },
    { label: '8 月', value: 88, tasks: 15 },
  ],
  scenarios: [{ label: '销售支持', value: 92, detail: '成单最多', color: 'bg-[var(--brand)]' }],
  outcomes: [{ title: '周报已发出', meta: '今天', type: 'workflow', status: 'done' }],
  savedHours: 6,
};

function renderHome() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(pageQueryKey(['user', 'insights', '近 7 天']), insights);
  qc.setQueryData(pageQueryKey(['user', 'insights', '近 30 天']), insights);
  qc.setQueryData(pageQueryKey(['user', 'insights', '本季度']), insights);
  qc.setQueryData(pageQueryKey(qk.user.tasks.list), []);
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => cleanup());

describe('首页效果摘要', () => {
  it('embeds the insights section and keeps its range/table interaction', () => {
    renderHome();
    expect(screen.getByText('完成任务')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /近 7 天/ }));
    fireEvent.click(screen.getByRole('menuitemradio', { name: '本季度' }));
    expect(screen.getByRole('button', { name: /本季度/ })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '查看数据表' }));
    expect(document.querySelector('caption')?.textContent).toBe('智能体任务完成率趋势数据');
    expect(screen.getByText('7 月')).toBeTruthy();
  });
});
