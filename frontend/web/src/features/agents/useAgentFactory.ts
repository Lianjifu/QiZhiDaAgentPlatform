/**
 * Phase 22: agent_factory 相关 hooks — 当前只暴露 useRouteOptions.
 *
 * 后续 Phase 给 agent version 编辑表单加策略路由选择时, 沿用 useRouteOptions
 * + RoutePicker. 这里的 hook 跟 features/models/useRouteRules 是分开的两套:
 *   - useRouteRules(): /api/admin/models/routes — 走 model catalog (admin)
 *   - useRouteOptions(): /v1/agents/options/routes — 走 agent_factory,
 *     入参需要 X-Tenant-Id/X-Workspace-Id (本 hook 通过 query 注入)
 */
import { useApiQuery } from '@/services/query';
import { qk } from '@/api/shared/query-keys';

export type RouteStrategy =
  | 'fallback'
  | 'quality-first'
  | 'cost-first'
  | 'latency-first'
  | 'round-robin'
  | 'weighted';

export interface RouteOption {
  id: string;
  name: string;
  strategy: RouteStrategy;
  primary_model_id: string;
  fallback_model_ids: Array<string | { id: string; weight: number }>;
  task: string;
  description: string;
  enabled: boolean;
}

export function useRouteOptions() {
  return useApiQuery<RouteOption[]>(
    [...qk.admin.agentFactory.routes],
    '/v1/agents/options/routes',
    {},
    { staleTime: 30_000, placeholderData: (prev) => prev },
  );
}

export const ROUTE_STRATEGY_LABEL: Record<RouteStrategy, string> = {
  'fallback': '失败转移',
  'quality-first': '质量优先',
  'cost-first': '成本优先',
  'latency-first': '延迟优先',
  'round-robin': '轮询',
  'weighted': '加权',
};

export const ROUTE_STRATEGY_DESCRIPTION: Record<RouteStrategy, string> = {
  'fallback': '按 fallback_model_ids 顺序依次试',
  'quality-first': '按 tier / 成功率 / 延迟选最优',
  'cost-first': '按 (输入价+输出价) 选最便宜',
  'latency-first': '按历史延迟选最快',
  'round-robin': 'fallback 链跨请求轮转, 流量均摊',
  'weighted': '按 weight 比例采样首, 其它按 weight 降序',
};
