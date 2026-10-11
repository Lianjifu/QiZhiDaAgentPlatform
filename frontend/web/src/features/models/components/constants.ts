import type { ModelStatus, ProviderStatus, RouteStrategy, TaskType, ModelTier, ExchangeFormat, TabId, ModelProtocol } from '../schema';
import { BarChart3, Bot, Filter, LineChart, Settings2, ShieldCheck, Sparkles, Activity } from 'lucide-react';

export const TABS: Array<{ id: TabId; label: string }> = [
  { id: 'overview', label: '模型总览' },
  { id: 'model', label: '模型列表' },
  { id: 'provider', label: '提供商' },
  { id: 'route', label: '路由策略' },
  { id: 'health', label: '健康监控' },
];

export const STATUS_BADGE: Record<ModelStatus, { label: string; className: string; dot: string }> = {
  active: { label: '启用', className: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300', dot: 'bg-emerald-500' },
  graying: { label: '灰度', className: 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300', dot: 'bg-amber-500' },
  draft: { label: '草稿', className: 'bg-[var(--bg-elevated)] text-[var(--text-secondary)]', dot: 'bg-[var(--text-muted)]' },
  retired: { label: '已下线', className: 'bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300', dot: 'bg-rose-500' },
};

export const PROVIDER_BADGE: Record<ProviderStatus, { label: string; className: string; dot: string }> = {
  healthy: { label: '正常', className: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300', dot: 'bg-emerald-500' },
  degraded: { label: '降级', className: 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300', dot: 'bg-amber-500' },
  down: { label: '故障', className: 'bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300', dot: 'bg-rose-500' },
};

export const STRATEGY_META: Record<RouteStrategy, { label: string; tone: string; icon: typeof Sparkles }> = {
  'quality-first': { label: '质量优先', tone: 'bg-violet-50 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300', icon: Sparkles },
  'cost-first': { label: '成本优先', tone: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300', icon: BarChart3 },
  'latency-first': { label: '延迟优先', tone: 'bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300', icon: Activity },
  fallback: { label: '降级链', tone: 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300', icon: ShieldCheck },
};

export const STRATEGY_LABEL: Record<RouteStrategy, string> = {
  'quality-first': '质量优先',
  'cost-first': '成本优先',
  'latency-first': '延迟优先',
  fallback: '降级链',
};

export const TASK_LABEL: Record<TaskType, string> = {
  reasoning: '推理',
  generation: '生成',
  classification: '分类',
  embedding: '向量化',
  summarization: '摘要',
};

export const TIER_LABEL: Record<ModelTier, string> = {
  premium: '旗舰',
  balanced: '均衡',
  economy: '经济',
};

export const STATUS_FILTER: Array<{ id: 'all' | ModelStatus; label: string }> = [
  { id: 'all', label: '全部状态' },
  { id: 'active', label: '启用' },
  { id: 'graying', label: '灰度' },
  { id: 'draft', label: '草稿' },
  { id: 'retired', label: '已下线' },
];

export const TIER_FILTER: Array<{ id: 'all' | ModelTier; label: string }> = [
  { id: 'all', label: '全部层级' },
  { id: 'premium', label: '旗舰' },
  { id: 'balanced', label: '均衡' },
  { id: 'economy', label: '经济' },
];

export const DRAWER_NAV_ITEMS: Array<{ id: 'detail' | 'params' | 'route' | 'audit'; label: string; icon: typeof Settings2 }> = [
  { id: 'detail', label: '基本信息', icon: Settings2 },
  { id: 'params', label: '参数与定价', icon: LineChart },
  { id: 'route', label: '路由引用', icon: Filter },
  { id: 'audit', label: '变更记录', icon: ShieldCheck },
];

export const EXCHANGE_FORMATS: ExchangeFormat[] = ['json', 'yaml'];

export function downloadBlob(blob: Blob, filename: string) {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function formatPrice(value: number, kind: 'in' | 'out'): string {
  const v = kind === 'in' ? value : value;
  if (v === 0) return '—';
  if (v < 0.001) return `¥ ${v.toFixed(5)}`;
  return `¥ ${v.toFixed(v < 0.01 ? 4 : 3)}`;
}

export const MODEL_PROTOCOLS: ModelProtocol[] = ['openai', 'azure', 'anthropic', 'openai-compatible', 'anthropic-compatible'];

export const PROTOCOL_META: Record<ModelProtocol, { label: string; summary: string; baseUrl: string }> = {
  openai: {
    label: 'OpenAI',
    summary: '官方 Chat Completions',
    baseUrl: 'https://api.openai.com/v1',
  },
  azure: {
    label: 'Azure OpenAI',
    summary: 'Azure 部署名调用',
    baseUrl: 'https://example.openai.azure.com',
  },
  anthropic: {
    label: 'Anthropic',
    summary: 'Messages API',
    baseUrl: 'https://api.anthropic.com',
  },
  'openai-compatible': {
    label: 'OpenAI 兼容',
    summary: '兼容 /v1 的自建或第三方网关',
    baseUrl: 'https://',
  },
  'anthropic-compatible': {
    label: 'Anthropic 兼容',
    summary: '兼容 Anthropic /v1/models 的自建或第三方网关',
    baseUrl: 'https://',
  },
};

/** demo 探测供应商时按协议返回的模型 ID，生产由供应商 /models 接口给出 */
export const DEMO_PROVIDER_CATALOG: Record<ModelProtocol, string[]> = {
  openai: ['gpt-4o', 'gpt-4o-mini', 'o1-preview', 'text-embedding-3-large'],
  azure: ['gpt-4o', 'gpt-35-turbo', 'text-embedding-3'],
  anthropic: ['claude-3-5-sonnet', 'claude-3-5-haiku', 'claude-3-opus'],
  'openai-compatible': ['llama-3.1-70b', 'qwen-max', 'deepseek-chat'],
  'anthropic-compatible': ['claude-3-5-sonnet-proxy', 'claude-3-haiku-proxy'],
};
