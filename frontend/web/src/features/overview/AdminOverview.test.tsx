/**
 * AdminOverview 页面测试 — Hero / KPI / 趋势图 / 告警 / 服务 / Top 智能体 / SideDrawer。
 */
import { describe, expect, it, afterEach } from 'vitest';
import { cleanup, fireEvent, screen } from '@testing-library/react';
import { qk } from '@/api/shared/query-keys';
import { renderWithProviders, pageQueryKey } from '@/test-utils/seed';
import OverviewPage from './OverviewPage';
import {
  mockAlerts,
  mockOverviewSummary,
  mockTrendByRange,
} from './fixtures';
import { mockProviders } from '@/features/models/fixtures';
import { mockAgents } from '@/features/agents/fixtures';

function renderPage() {
  return renderWithProviders(<OverviewPage />, {
    initialEntries: ['/admin/overview'],
    seeds: [
      { key: pageQueryKey(qk.admin.overview.summary), data: mockOverviewSummary },
      { key: pageQueryKey(qk.admin.overview.alerts), data: mockAlerts },
      { key: pageQueryKey(qk.admin.overview.trend('24h')), data: mockTrendByRange['24h'] },
      { key: pageQueryKey(qk.admin.overview.trend('1h')), data: mockTrendByRange['1h'] },
      { key: pageQueryKey(qk.admin.overview.trend('6h')), data: mockTrendByRange['6h'] },
      { key: pageQueryKey(qk.admin.overview.trend('7d')), data: mockTrendByRange['7d'] },
      { key: pageQueryKey([...qk.admin.overview.root, 'providers']), data: mockProviders },
      { key: pageQueryKey([...qk.admin.overview.root, 'agents']), data: mockAgents },
    ],
  });
}

describe('AdminOverview', () => {
  afterEach(() => cleanup());

  it('renders hero eyebrow, headline, and sub copy', () => {
    renderPage();
    expect(screen.getByText('ADMIN / 运营总览')).toBeTruthy();
    expect(screen.getByText(/看调用量、可用率和告警/)).toBeTruthy();
  });

  it('renders all 6 KPI tiles from summary fixture', () => {
    renderPage();
    expect(screen.getByText('今日调用')).toBeTruthy();
    expect(screen.getAllByText('可用率').length).toBeGreaterThan(0);
    expect(screen.getByText('P95 延迟')).toBeTruthy();
    expect(screen.getAllByText('错误率').length).toBeGreaterThan(0);
    expect(screen.getByText('活跃智能体')).toBeTruthy();
    expect(screen.getByText('告警事件')).toBeTruthy();
    expect(screen.getByText('128,432')).toBeTruthy();
  });

  it('renders range selector with 24h active by default', () => {
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /24 小时/ }));
    for (const label of ['1 小时', '6 小时', '24 小时', '最近 7 天']) {
      expect(screen.getByRole('menuitemradio', { name: label })).toBeTruthy();
    }
    expect(screen.getByRole('menuitemradio', { name: '24 小时', checked: true })).toBeTruthy();
  });

  it('renders trend chart x-axis labels from 24h fixture', () => {
    renderPage();
    expect(screen.getByText('00')).toBeTruthy();
    expect(screen.getByText('12')).toBeTruthy();
    expect(screen.getByText('22')).toBeTruthy();
  });

  it('renders all 5 alerts from fixture', () => {
    renderPage();
    expect(screen.getByText(/模型 qzdap-gpt-4o 错误率突增/)).toBeTruthy();
    expect(screen.getByText(/企查查/)).toBeTruthy();
    expect(screen.getByText(/知识库「产品手册 v3」需要重建索引/)).toBeTruthy();
    expect(screen.getByText(/3 个智能体版本待审核/)).toBeTruthy();
    expect(screen.getByText(/审计日志归档已完成/)).toBeTruthy();
  });

  it('renders service health from model providers', () => {
    renderPage();
    expect(screen.getByText('OpenAI 官方')).toBeTruthy();
    expect(screen.getByText('Anthropic Claude')).toBeTruthy();
    expect(screen.getByText('DeepSeek')).toBeTruthy();
    expect(screen.getAllByText('健康').length).toBeGreaterThan(0);
    expect(screen.getByText('降级')).toBeTruthy();
    expect(screen.getByText('异常')).toBeTruthy();
  });

  it('renders top agents from real agent call counts', () => {
    renderPage();
    const ranked = [...mockAgents].sort((a, b) => b.calls - a.calls).slice(0, 5);
    for (const agent of ranked) {
      expect(screen.getByText(agent.name)).toBeTruthy();
    }
  });

  it('opens SideDrawer when an alert row is clicked', () => {
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /模型 qzdap-gpt-4o 错误率突增/ }));
    const drawer = screen.getByRole('dialog', { name: /模型 qzdap-gpt-4o 错误率突增/ });
    expect(drawer).toBeTruthy();
    expect(drawer.textContent).toContain('建议处理');
    expect(drawer.textContent).toContain('立即处理');
    // 关闭
    fireEvent.click(screen.getByRole('button', { name: '关闭面板' }));
    expect(screen.queryByRole('dialog', { name: /模型 qzdap-gpt-4o 错误率突增/ })).toBeNull();
  });

  it('switches range to 7d and shows weekly labels', () => {
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /24 小时/ }));
    fireEvent.click(screen.getByRole('menuitemradio', { name: '最近 7 天' }));
    expect(screen.getByText('周一')).toBeTruthy();
    expect(screen.getByText('周日')).toBeTruthy();
  });
});