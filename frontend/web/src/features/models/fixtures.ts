/**
 * 管理侧「模型配置」fixture — 5 providers / 9 models / 6 routes / 4 health events。
 */
import type { Model, Provider, RouteRule, HealthEvent } from './schema';

export const mockProviders: Provider[] = [
  { id: 'pv-openai', name: 'OpenAI 官方', region: 'global', status: 'healthy', baseUrl: 'https://api.openai.com/v1', apiKeyMasked: 'sk-••••••••3aF2', errorRate: 0.4, avgLatencyMs: 480, qps: 120 },
  { id: 'pv-azure', name: 'Azure OpenAI', region: 'eastasia', status: 'healthy', baseUrl: 'https://qzdap.openai.azure.com', apiKeyMasked: '••••••••b821', errorRate: 0.3, avgLatencyMs: 520, qps: 80 },
  { id: 'pv-anthropic', name: 'Anthropic Claude', region: 'us-east', status: 'degraded', baseUrl: 'https://api.anthropic.com', apiKeyMasked: 'sk-ant-•••••7Cd1', errorRate: 1.6, avgLatencyMs: 610, qps: 45 },
  { id: 'pv-qwen', name: '通义千问', region: 'china', status: 'healthy', baseUrl: 'https://dashscope.aliyuncs.com', apiKeyMasked: 'sk-••••••e9a0', errorRate: 0.5, avgLatencyMs: 410, qps: 200 },
  { id: 'pv-deepseek', name: 'DeepSeek', region: 'china', status: 'down', baseUrl: 'https://api.deepseek.com', apiKeyMasked: 'sk-••••••44ac', errorRate: 4.8, avgLatencyMs: 0, qps: 0 },
];

export const mockModels: Model[] = [
  { id: 'md-gpt4o', name: 'GPT-4o', providerId: 'pv-openai', providerName: 'OpenAI 官方', task: ['reasoning', 'generation'], contextWindow: 128000, priceIn: 0.005, priceOut: 0.015, latencyMs: 460, successRate: 99.4, status: 'active', tier: 'premium', starred: true, calls: 184320, trend: [120, 140, 160, 180, 220, 260, 240, 280, 300, 320, 360, 400], description: 'OpenAI 旗舰多模态,适合复杂推理与高质量生成。', tags: ['多模态', '推理'] },
  { id: 'md-gpt4omini', name: 'GPT-4o mini', providerId: 'pv-openai', providerName: 'OpenAI 官方', task: ['generation', 'classification'], contextWindow: 128000, priceIn: 0.00015, priceOut: 0.0006, latencyMs: 280, successRate: 99.6, status: 'active', tier: 'economy', starred: false, calls: 286400, trend: [200, 220, 240, 280, 320, 360, 340, 380, 400, 420, 440, 480], description: '轻量通用模型,适合在线检索/分类任务。', tags: ['轻量'] },
  { id: 'md-o1preview', name: 'o1-preview', providerId: 'pv-openai', providerName: 'OpenAI 官方', task: ['reasoning'], contextWindow: 128000, priceIn: 0.015, priceOut: 0.06, latencyMs: 1840, successRate: 97.2, status: 'graying', tier: 'premium', starred: false, calls: 12480, trend: [40, 60, 80, 120, 160, 200, 220, 240, 260, 280, 320, 380], description: '深度推理专用,延迟较高。', tags: ['深度推理'] },
  { id: 'md-claude35', name: 'Claude 3.5 Sonnet', providerId: 'pv-anthropic', providerName: 'Anthropic Claude', task: ['reasoning', 'generation', 'summarization'], contextWindow: 200000, priceIn: 0.003, priceOut: 0.015, latencyMs: 720, successRate: 98.1, status: 'active', tier: 'premium', starred: true, calls: 96400, trend: [60, 80, 100, 140, 180, 220, 260, 280, 320, 360, 380, 420], description: '长上下文写作与推理均衡,文档摘要优选。', tags: ['长上下文', '写作'] },
  { id: 'md-qwenmax', name: '通义千问 Max', providerId: 'pv-qwen', providerName: '通义千问', task: ['reasoning', 'generation'], contextWindow: 32000, priceIn: 0.002, priceOut: 0.006, latencyMs: 380, successRate: 99.1, status: 'active', tier: 'balanced', starred: false, calls: 142800, trend: [80, 100, 120, 160, 200, 240, 260, 300, 340, 360, 380, 420], description: '中文场景优化,综合性价比优。', tags: ['中文'] },
  { id: 'md-qwen7b', name: '通义千问 7B', providerId: 'pv-qwen', providerName: '通义千问', task: ['classification', 'embedding'], contextWindow: 8000, priceIn: 0.0001, priceOut: 0.0002, latencyMs: 120, successRate: 99.7, status: 'active', tier: 'economy', starred: false, calls: 312000, trend: [220, 240, 280, 320, 360, 400, 440, 480, 520, 560, 600, 640], description: '轻量分类/向量化,大规模在线场景。', tags: ['分类', '向量化'] },
  { id: 'md-dsv3', name: 'DeepSeek-V3', providerId: 'pv-deepseek', providerName: 'DeepSeek', task: ['reasoning'], contextWindow: 64000, priceIn: 0.0014, priceOut: 0.0028, latencyMs: 540, successRate: 96.4, status: 'draft', tier: 'balanced', starred: false, calls: 0, trend: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], description: '高性价比推理,处于内测接入。', tags: ['内测'] },
  { id: 'md-gpt35turbo', name: 'GPT-3.5 Turbo', providerId: 'pv-azure', providerName: 'Azure OpenAI', task: ['generation'], contextWindow: 16000, priceIn: 0.0005, priceOut: 0.0015, latencyMs: 240, successRate: 99.2, status: 'retired', tier: 'economy', starred: false, calls: 48000, trend: [40, 30, 20, 10, 0, 0, 0, 0, 0, 0, 0, 0], description: '老版本通用模型,已下线。', tags: ['已下线'] },
  { id: 'md-embedv3', name: 'text-embedding-3', providerId: 'pv-azure', providerName: 'Azure OpenAI', task: ['embedding'], contextWindow: 8000, priceIn: 0.00002, priceOut: 0, latencyMs: 80, successRate: 99.9, status: 'active', tier: 'economy', starred: true, calls: 524000, trend: [400, 420, 460, 480, 520, 560, 600, 640, 680, 720, 760, 800], description: '向量化主链路。', tags: ['向量化'] },
];

export const mockRoutes: RouteRule[] = [
  { id: 'rt-reasoning', name: '推理任务 · 质量优先', task: 'reasoning', strategy: 'quality-first', priority: 90, primaryModelId: 'md-gpt4o', fallbackModelIds: ['md-claude35', 'md-qwenmax'], enabled: true, description: 'GPT-4o 为主,Claude 与千问降级。' },
  { id: 'rt-writing', name: '写作任务 · 长上下文', task: 'generation', strategy: 'quality-first', priority: 80, primaryModelId: 'md-claude35', fallbackModelIds: ['md-gpt4o'], enabled: true, description: 'Claude 3.5 优选,适合长文档写作。' },
  { id: 'rt-classification', name: '分类任务 · 成本优先', task: 'classification', strategy: 'cost-first', priority: 70, primaryModelId: 'md-qwen7b', fallbackModelIds: ['md-gpt4omini'], enabled: true, description: '高吞吐低成本,首选通义 7B。' },
  { id: 'rt-summary', name: '摘要任务 · 延迟优先', task: 'summarization', strategy: 'latency-first', priority: 60, primaryModelId: 'md-gpt4omini', fallbackModelIds: ['md-claude35'], enabled: true, description: '延迟敏感型摘要,首选 4o-mini。' },
  { id: 'rt-embedding', name: '向量化 · 单链路', task: 'embedding', strategy: 'fallback', priority: 100, primaryModelId: 'md-embedv3', fallbackModelIds: ['md-qwen7b'], enabled: true, description: '向量化主链路,千问 7B 兜底。' },
  { id: 'rt-reasoning-graying', name: '推理灰度 · DeepSeek', task: 'reasoning', strategy: 'cost-first', priority: 50, primaryModelId: 'md-dsv3', fallbackModelIds: ['md-qwenmax'], enabled: false, description: '新模型灰度发布,仅在 Canary 环境启用。' },
];

export const mockHealth: HealthEvent[] = [
  { id: 'he-001', type: 'incident', providerId: 'pv-deepseek', providerName: 'DeepSeek', message: 'API 网关返回 502,持续 12 分钟。已切到备用接入点。', occurredAt: '2026-09-28 03:14' },
  { id: 'he-002', type: 'latency', providerId: 'pv-anthropic', providerName: 'Anthropic Claude', message: '平均延迟由 480ms 升至 720ms(+50%),持续中。', occurredAt: '2026-09-28 02:48' },
  { id: 'he-003', type: 'quota', providerId: 'pv-openai', providerName: 'OpenAI 官方', message: '组织配额剩余 18%,触发告警。', occurredAt: '2026-09-27 22:05' },
  { id: 'he-004', type: 'recovery', providerId: 'pv-azure', providerName: 'Azure OpenAI', message: 'eastasia 区域故障恢复,延迟与错误率回到基线。', occurredAt: '2026-09-27 19:32' },
];
