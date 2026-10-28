/**
 * AdminMetrics — 对齐技能/模型：无子模块 Tab，视图 combobox + 模型卡片。
 */
import { describe, expect, it, afterEach } from 'vitest';
import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { qk } from '@/api/shared/query-keys';
import { renderWithProviders, pageQueryKey } from '@/test-utils/seed';
import {
  mockCostBreakdown, mockLatencyPoints, mockMetricsDashboards, mockModelMetrics, mockThresholdRules,
} from './fixtures';
import MetricsPage from './index';
import MetricDetailPage from './MetricDetailPage';
import DashboardCreatePage from './DashboardCreatePage';

afterEach(() => cleanup());

function renderPage() {
  return renderWithProviders(
    <Routes>
      <Route path="/admin/metrics" element={<MetricsPage />} />
      <Route path="/admin/metrics/new" element={<DashboardCreatePage />} />
      <Route path="/admin/metrics/:id" element={<MetricDetailPage />} />
    </Routes>,
    {
    initialEntries: ['/admin/metrics'],
    seeds: [
      { key: pageQueryKey(qk.admin.metrics.models), data: mockModelMetrics },
      { key: pageQueryKey(qk.admin.metrics.latency), data: mockLatencyPoints },
      { key: pageQueryKey(qk.admin.metrics.costBreakdown), data: mockCostBreakdown },
      { key: pageQueryKey(qk.admin.metrics.dashboards), data: mockMetricsDashboards },
      { key: pageQueryKey(qk.admin.metrics.thresholds), data: mockThresholdRules },
    ],
    },
  );
}

function switchView(value: string) {
  fireEvent.change(screen.getByRole('combobox', { name: '视图' }), { target: { value } });
}

describe('AdminMetrics', () => {
  it('renders hero and default model cards without tab nav', async () => {
    renderPage();
    expect(screen.getByText(/运行指标/)).toBeTruthy();
    expect(screen.getByText('观测可用率、延迟和成本。')).toBeTruthy();
    expect(screen.queryByRole('button', { name: '延迟分析' })).toBeNull();
    expect(screen.getByRole('combobox', { name: '视图' })).toBeTruthy();
    await waitFor(() => {
      expect(screen.getByText('云知-旗舰 v4')).toBeTruthy();
    });
  });

  it('switches to latency view via select', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('云知-旗舰 v4')).toBeTruthy());
    switchView('latency');
    await waitFor(() => {
      expect(screen.getByText('延迟曲线')).toBeTruthy();
    });
  });

  it('switches to token view and shows cost breakdown', async () => {
    renderPage();
    switchView('token');
    await waitFor(() => {
      expect(screen.getByText('成本占比')).toBeTruthy();
    });
  });

  it('switches to dashboard view', async () => {
    renderPage();
    switchView('dashboard');
    await waitFor(() => {
      expect(screen.getByText('指标看板')).toBeTruthy();
    });
    expect(screen.getByText('告警阈值规则')).toBeTruthy();
  });

  it('新建看板进入独立页面', async () => {
    renderPage();
    switchView('dashboard');
    await waitFor(() => expect(screen.getByText('指标看板')).toBeTruthy());
    fireEvent.click(screen.getAllByRole('button', { name: /新建看板/ })[0]);
    expect(screen.getByRole('heading', { level: 1, name: '新建看板' })).toBeTruthy();
    expect(screen.getByRole('link', { name: /返回运行指标/ })).toBeTruthy();
  });

  it('switches to availability view and shows provider column', async () => {
    renderPage();
    switchView('availability');
    await waitFor(() => {
      expect(screen.getByText('Provider')).toBeTruthy();
    });
  });

  it('navigates to metric detail when model card is clicked', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('云知-旗舰 v4')).toBeTruthy());
    const card = screen.getAllByLabelText(/^查看 .* 详情$/)[0];
    fireEvent.click(card);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.getByRole('heading', { level: 1, name: mockModelMetrics[0].model })).toBeTruthy();
  });
});
