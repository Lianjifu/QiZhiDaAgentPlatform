/**
 * TrendChart 测试 — 空数据 / 悬停 / 重取数后数据变短。
 *
 * 回归点: 后端 trend 接口对新租户返回 points: [], 之前 hover 下标会被钳到 0,
 * tooltip 读 data[0].label 直接抛 "Cannot read properties of undefined".
 */
import { describe, expect, it, afterEach, beforeEach, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { TrendPoint, TrendSeries } from '../schema';
import { TrendChart } from './TrendChart';

const POINTS: TrendPoint[] = [
  { label: '00', calls: 120, success: 99.5, errors: 0.5 },
  { label: '12', calls: 340, success: 98.25, errors: 1.75 },
];

function seriesOf(points: TrendPoint[]): TrendSeries {
  return { range: '24h', points };
}

/** jsdom 的 getBoundingClientRect 全 0, scale 会变成 Infinity。 */
function stubChartWidth(width = 720) {
  return vi.spyOn(SVGElement.prototype, 'getBoundingClientRect').mockReturnValue({
    width,
    height: 260,
    top: 0,
    left: 0,
    right: width,
    bottom: 260,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  } as DOMRect);
}

describe('TrendChart', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('renders without crashing when points is empty', () => {
    stubChartWidth();
    render(<TrendChart series={seriesOf([])} />);
    expect(screen.getByRole('img')).toBeTruthy();
  });

  it('does not throw on hover when points is empty', () => {
    stubChartWidth();
    render(<TrendChart series={seriesOf([])} />);
    const svg = screen.getByRole('img');
    expect(() => fireEvent.mouseMove(svg, { clientX: 360 })).not.toThrow();
    // 空数据不该渲染 tooltip (tooltip 里有 "可用率 99.50%" 这种带数字的文案)
    expect(screen.queryByText(/可用率 \d/)).toBeNull();
  });

  it('shows the tooltip for the hovered point', () => {
    stubChartWidth();
    render(<TrendChart series={seriesOf(POINTS)} />);
    fireEvent.mouseMove(screen.getByRole('img'), { clientX: 360 });
    // '12' 同时出现在 x 轴刻度和 tooltip 里, 两处都在才算悬停生效
    expect(screen.getAllByText('12').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('调用量 340')).toBeTruthy();
    expect(screen.getByText('可用率 98.25%')).toBeTruthy();
    expect(screen.getByText('错误率 1.75%')).toBeTruthy();
  });

  it('does not throw when points shrink under a live hover index', () => {
    stubChartWidth();
    const { rerender } = render(<TrendChart series={seriesOf(POINTS)} />);
    fireEvent.mouseMove(screen.getByRole('img'), { clientX: 360 });
    // 重新取数 / 切 range 后 points 可能变短甚至清空, 旧的下标必须失效
    expect(() => rerender(<TrendChart series={seriesOf([])} />)).not.toThrow();
    expect(screen.queryByText(/可用率 \d/)).toBeNull();
  });
});