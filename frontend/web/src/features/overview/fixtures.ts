/**
 * 管理侧「运营总览」fixtures — 6 个 KPI / 4 段时间序列 / 5 条告警 / 5 项服务 / 5 个 Top 智能体。
 */
import type { KpiTile, OverviewAlert, OverviewService, OverviewSummary, TopAgent, TrendSeries } from './schema';

export const mockKpis: KpiTile[] = [
  { label: '今日调用', value: '128,432', delta: '+12.4%', deltaTone: 'up', tone: 'brand', href: '/admin/metrics', sparkline: [62, 70, 55, 80, 72, 90, 85, 95, 100, 88, 92, 105], iconName: 'Activity' },
  { label: '可用率', value: '99.94%', delta: '-0.02%', deltaTone: 'flat', tone: 'success', href: '/admin/metrics', sparkline: [99.92, 99.93, 99.91, 99.94, 99.95, 99.93, 99.94, 99.95, 99.92, 99.94, 99.95, 99.94], iconName: 'ShieldCheck' },
  { label: 'P95 延迟', value: '1.82 s', delta: '-6.1%', deltaTone: 'down', tone: 'info', href: '/admin/metrics', sparkline: [2.4, 2.2, 2.1, 1.9, 2.0, 1.8, 1.7, 1.9, 2.0, 1.85, 1.82, 1.8], iconName: 'Timer' },
  { label: '错误率', value: '0.42%', delta: '+0.08%', deltaTone: 'up', tone: 'danger', href: '/admin/alerts', sparkline: [0.3, 0.32, 0.28, 0.35, 0.4, 0.38, 0.36, 0.42, 0.45, 0.4, 0.42, 0.42], iconName: 'AlertTriangle' },
  { label: '活跃智能体', value: '87 / 142', delta: '+5 个', deltaTone: 'up', tone: 'purple', href: '/admin/agents', sparkline: [70, 72, 75, 78, 80, 82, 84, 85, 86, 87, 87, 87], iconName: 'Brain' },
  { label: '告警事件', value: '3 待处理', delta: '+1 高优', deltaTone: 'up', tone: 'warn', href: '/admin/alerts', sparkline: [1, 1, 0, 2, 2, 1, 1, 2, 3, 3, 3, 3], iconName: 'BellRing' },
];

export const mockTrendByRange: Record<string, TrendSeries> = {
  '1h': {
    range: '1h',
    points: [
      { label: '-60', calls: 8200, success: 99.96, errors: 0.30 },
      { label: '-50', calls: 9100, success: 99.95, errors: 0.32 },
      { label: '-40', calls: 8500, success: 99.94, errors: 0.28 },
      { label: '-30', calls: 9800, success: 99.93, errors: 0.35 },
      { label: '-20', calls: 9300, success: 99.95, errors: 0.40 },
      { label: '-10', calls: 9600, success: 99.94, errors: 0.38 },
      { label: '00', calls: 9100, success: 99.94, errors: 0.42 },
    ],
  },
  '6h': {
    range: '6h',
    points: [
      { label: '-6h', calls: 48000, success: 99.95, errors: 0.30 },
      { label: '-5h', calls: 52000, success: 99.96, errors: 0.32 },
      { label: '-4h', calls: 58000, success: 99.93, errors: 0.34 },
      { label: '-3h', calls: 54000, success: 99.94, errors: 0.38 },
      { label: '-2h', calls: 61000, success: 99.92, errors: 0.42 },
      { label: '-1h', calls: 59000, success: 99.94, errors: 0.40 },
      { label: '00', calls: 56000, success: 99.94, errors: 0.42 },
    ],
  },
  '24h': {
    range: '24h',
    points: [
      { label: '00', calls: 3200, success: 99.97, errors: 0.30 },
      { label: '02', calls: 2800, success: 99.96, errors: 0.32 },
      { label: '04', calls: 3100, success: 99.95, errors: 0.34 },
      { label: '06', calls: 5400, success: 99.94, errors: 0.36 },
      { label: '08', calls: 9200, success: 99.93, errors: 0.38 },
      { label: '10', calls: 12400, success: 99.94, errors: 0.40 },
      { label: '12', calls: 14800, success: 99.92, errors: 0.42 },
      { label: '14', calls: 13200, success: 99.93, errors: 0.41 },
      { label: '16', calls: 11900, success: 99.94, errors: 0.40 },
      { label: '18', calls: 10500, success: 99.95, errors: 0.38 },
      { label: '20', calls: 8800, success: 99.94, errors: 0.40 },
      { label: '22', calls: 6400, success: 99.94, errors: 0.42 },
    ],
  },
  '7d': {
    range: '7d',
    points: [
      { label: '周一', calls: 98000, success: 99.94, errors: 0.42 },
      { label: '周二', calls: 112000, success: 99.93, errors: 0.45 },
      { label: '周三', calls: 124000, success: 99.92, errors: 0.48 },
      { label: '周四', calls: 118000, success: 99.94, errors: 0.44 },
      { label: '周五', calls: 132000, success: 99.95, errors: 0.40 },
      { label: '周六', calls: 76000, success: 99.96, errors: 0.36 },
      { label: '周日', calls: 64000, success: 99.96, errors: 0.34 },
    ],
  },
};

export const mockAlerts: OverviewAlert[] = [
  { id: 'a1', severity: 'high', title: '模型 qzdap-gpt-4o 错误率突增', time: '2 分钟前', affected: '客户沟通助手 · 销售支持', suggestion: '建议临时切换到 qzdap-deepseek-v3 并下发限流保护。' },
  { id: 'a2', severity: 'medium', title: '工具「企查查」连续 3 次超时', time: '8 分钟前', affected: '数据洞察助手', suggestion: '已自动重试 2 次，建议人工介入确认供应商限流。' },
  { id: 'a3', severity: 'low', title: '知识库「产品手册 v3」需要重建索引', time: '1 小时前', affected: '全平台', suggestion: '预计重建耗时 12 分钟，可在低峰期执行。' },
  { id: 'a4', severity: 'info', title: '3 个智能体版本待审核', time: '2 小时前', affected: '智能体管理', suggestion: '运营总览待办 → 智能体管理 → 待审核。' },
  { id: 'a5', severity: 'low', title: '审计日志归档已完成', time: '今天 03:00', affected: '平台', suggestion: '归档后可清理 30 天前的明细日志。' },
];

export const mockServices: OverviewService[] = [
  { name: '模型服务', status: 'ok', latency: '42 ms', detail: '10 个模型 · 平均可用率 99.95%' },
  { name: '知识检索', status: 'ok', latency: '87 ms', detail: '32 个索引 · 平均召回 0.91' },
  { name: '工具网关', status: 'ok', latency: '23 ms', detail: '128 个工具在线' },
  { name: '模型降级池', status: 'degraded', latency: '—', detail: '1 个模型触发降级 · qzdap-gpt-4o 切到 qzdap-deepseek-v3' },
  { name: '审计服务', status: 'ok', latency: '—', detail: '实时落库 · 队列 12 / 10000' },
];

export const mockTopAgents: TopAgent[] = [
  { name: '客户沟通助手', calls: '18.2k', share: 0.42, tone: 'brand' },
  { name: '销售支持', calls: '14.7k', share: 0.34, tone: 'success' },
  { name: '数据洞察助手', calls: '9.8k', share: 0.23, tone: 'info' },
  { name: '财务问答', calls: '6.1k', share: 0.14, tone: 'purple' },
  { name: '工作流编排', calls: '5.4k', share: 0.12, tone: 'warn' },
];

export const mockOverviewSummary: OverviewSummary = {
  kpis: mockKpis,
  alerts: mockAlerts,
  services: mockServices,
  topAgents: mockTopAgents,
};