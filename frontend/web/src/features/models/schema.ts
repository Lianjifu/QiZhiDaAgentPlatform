/**
 * 管理侧「模型配置」数据类型 — 实体 + 筛选 + 变更参数。
 */
export type TabId = 'overview' | 'model' | 'provider' | 'route' | 'health';
export type ModelStatus = 'active' | 'graying' | 'draft' | 'retired';
export type ProviderStatus = 'healthy' | 'degraded' | 'down';
export type RouteStrategy = 'quality-first' | 'cost-first' | 'latency-first' | 'fallback';
export type TaskType = 'reasoning' | 'generation' | 'classification' | 'embedding' | 'summarization';
export type ModelTier = 'premium' | 'balanced' | 'economy';
export type ExchangeFormat = 'json' | 'yaml';
export type HealthEventType = 'incident' | 'latency' | 'quota' | 'recovery';
export type ModelProtocol = 'openai' | 'azure' | 'anthropic' | 'openai-compatible' | 'anthropic-compatible' | 'google' | 'deepseek' | 'glm' | 'kimi' | 'qwen' | 'minimax';

export interface Model {
  id: string;
  name: string;
  upstreamModel?: string;
  providerId: string;
  providerName: string;
  task: TaskType[];
  contextWindow: number;
  priceIn: number;
  priceOut: number;
  latencyMs: number;
  successRate: number;
  status: ModelStatus;
  tier: ModelTier;
  starred: boolean;
  calls: number;
  trend: number[];
  description: string;
  tags: string[];
}

export interface Provider {
  id: string;
  name: string;
  region: string;
  status: ProviderStatus;
  baseUrl: string;
  apiKeyMasked: string;
  protocol?: ModelProtocol;
  errorRate: number;
  avgLatencyMs: number;
  qps: number;
}

export interface RouteRule {
  id: string;
  name: string;
  task: TaskType;
  strategy: RouteStrategy;
  priority: number;
  primaryModelId: string;
  fallbackModelIds: string[];
  enabled: boolean;
  description: string;
}

export interface HealthEvent {
  id: string;
  type: HealthEventType;
  providerId: string;
  providerName: string;
  message: string;
  occurredAt: string;
}

export interface ModelFilters {
  search?: string;
  status?: 'all' | ModelStatus;
  tier?: 'all' | ModelTier;
}

export type CreateModelVars = {
  providerName: string;
  apiKey: string;
  baseUrl: string;
  protocol: ModelProtocol;
  models: string[];
  apiVersion?: string;
  source: 'catalog' | 'verified';
  verificationToken?: string;
};

export type ModelDetail = Model & { provider: ProviderConnection };

export type ProviderConnection = {
  id: string;
  name: string;
  baseUrl: string;
  protocol: ModelProtocol;
  apiKeyMasked: string;
  hasCredential: boolean;
  apiVersion?: string;
};

export type ProviderConnectionValues = {
  name: string;
  baseUrl: string;
  protocol: ModelProtocol;
  apiKey: string;
  apiVersion?: string;
};

export type ProbeModelsVars = {
  modelId?: string;
  apiKey?: string;
  baseUrl: string;
  protocol: ModelProtocol;
  apiVersion?: string;
};

export type ProbeModelsResult = {
  models: string[];
  discoverySupported?: boolean;
  /** Present when the probe could not return real supplier data. */
  error?: string;
};

export type ConnectivityTestVars = ProbeModelsVars & {
  model: string;
  apiVersion?: string;
};

export type ConnectivityTestResult = {
  success: boolean;
  verificationToken?: string;
  latencyMs: number;
  statusCode: number | null;
  requestedModel: string;
  actualModel: string | null;
  response: string | null;
  error: string | null;
};

export type CreateRouteVars = {
  name: string;
  task: TaskType;
  strategy: RouteStrategy;
  priority: number;
  primaryModelId: string;
  description: string;
};

export type UpdateModelVars = {
  id: string;
  patch: Partial<Pick<Model, 'name' | 'description' | 'tier' | 'status' | 'contextWindow' | 'priceIn' | 'priceOut' | 'task' | 'tags'>> & {
    provider?: ProviderConnectionValues;
    upstreamModel?: string;
    source?: 'catalog' | 'verified';
    verificationToken?: string;
  };
};

export type ToggleRouteVars = { id: string };
export type DeleteModelVars = { id: string };
export type ToggleStarVars = { id: string; starred: boolean };
export type BatchStatusVars = { ids: string[]; status: ModelStatus };
