/**
 * Phase 22+23: agent_factory hooks — route options (Phase 22) +
 * template/version/release CRUD (Phase 23).
 *
 * 与 features/models/useRouteRules 区分:
 *   - useRouteOptions: /v1/agents/options/routes  (agent_factory 下拉数据)
 *   - useRouteRules:   /api/admin/models/routes  (model admin)
 *
 * agent_factory 走 /v1/agents/*, 默认注入 X-Tenant-Id/X-Workspace-Id
 * (useApiQuery 自动从 useAuthStore 拿).
 */
import { useApiQuery, useApiMutation } from '@/services/query';
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

// ── Phase 23: agent_factory templates + versions + releases ──────────

export type TemplateStatus = 'active' | 'archived';
export type VersionStatus = 'draft' | 'published' | 'released' | 'retired';

export interface AgentTemplate {
  id: string;
  tenant_id: string;
  workspace_id: string;
  name: string;
  description: string;
  default_model_id: string | null;
  default_system_prompt: string;
  status: TemplateStatus;
  metadata: Record<string, unknown>;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface AgentVersion {
  id: string;
  tenant_id: string;
  workspace_id: string;
  template_id: string;
  version_tag: string;
  status: VersionStatus;
  system_prompt: string;
  model_id: string | null;
  route_id: string | null;
  route_strategy: RouteStrategy | null;
  allowed_tools: string[];
  allowed_skills: string[];
  knowledge_package_ids: string[];
  plan_dsl_snapshot: Record<string, unknown> | null;
  max_total_steps: number | null;
  release_notes: string;
  published_at: string | null;
  released_at: string | null;
  metadata: Record<string, unknown>;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface AgentRelease {
  id: string;
  tenant_id: string;
  workspace_id: string;
  template_id: string;
  version_id: string;
  eval_run_id: string | null;
  eval_score: number | null;
  status: string;
  released_by: string;
  released_at: string;
  notes: string;
}

export interface CreateTemplateVars {
  name: string;
  description?: string;
  default_model_id: string;
  default_system_prompt: string;
  metadata?: Record<string, unknown>;
}

export interface CreateVersionVars {
  templateId: string;
  version_tag: string;
  system_prompt?: string | null;
  model_id?: string | null;
  route_id?: string | null;
  route_strategy?: RouteStrategy | null;
  release_notes?: string;
}

export interface UpdateVersionNotesVars {
  templateId: string;
  versionId: string;
  release_notes: string;
}

export interface ReleaseVersionVars {
  templateId: string;
  versionId: string;
  notes?: string;
}

const AF_ROOT = qk.admin.agentFactory.root;
const TPL_LIST = [...AF_ROOT, 'templates', 'list'] as const;
const TPL_DETAIL = (id: string) => [...AF_ROOT, 'templates', 'detail', id] as const;
const VER_LIST = (tid: string) => [...AF_ROOT, 'versions', 'list', tid] as const;
const REL_LIST = (tid: string, vid: string) => [...AF_ROOT, 'releases', 'list', tid, vid] as const;

export function useTemplatesList() {
  return useApiQuery<AgentTemplate[]>(
    [...TPL_LIST],
    '/v1/agents',
    {},
    { staleTime: 30_000, placeholderData: (prev) => prev },
  );
}

export function useTemplateDetail(id: string) {
  return useApiQuery<AgentTemplate>(
    [...TPL_DETAIL(id)],
    `/v1/agents/${id}`,
    {},
    { enabled: id.length > 0 },
  );
}

export function useTemplateVersions(templateId: string) {
  return useApiQuery<AgentVersion[]>(
    [...VER_LIST(templateId)],
    `/v1/agents/${templateId}/versions`,
    {},
    { enabled: templateId.length > 0, staleTime: 15_000 },
  );
}

export function useVersionReleases(templateId: string, versionId: string) {
  return useApiQuery<AgentRelease[]>(
    [...REL_LIST(templateId, versionId)],
    `/v1/agents/${templateId}/versions/${versionId}/releases`,
    {},
    { enabled: templateId.length > 0 && versionId.length > 0 },
  );
}

export function useCreateTemplate() {
  return useApiMutation<AgentTemplate, CreateTemplateVars>(
    '/v1/agents',
    { invalidateKeys: [AF_ROOT] },
    'POST',
  );
}

export function useUpdateTemplate() {
  return useApiMutation<AgentTemplate, { id: string; status?: string }>(
    (v) => `/v1/agents/${v.id}`,
    { invalidateKeys: [AF_ROOT] },
    'PATCH',
  );
}

export function useCreateVersion() {
  return useApiMutation<AgentVersion, CreateVersionVars>(
    (v) => `/v1/agents/${v.templateId}/versions`,
    { invalidateKeys: [AF_ROOT] },
    'POST',
  );
}

export function useUpdateVersionNotes() {
  return useApiMutation<AgentVersion, UpdateVersionNotesVars>(
    (v) => `/v1/agents/${v.templateId}/versions/${v.versionId}/notes`,
    { invalidateKeys: [AF_ROOT] },
    'PATCH',
  );
}

export function usePublishVersion() {
  return useApiMutation<AgentVersion, { templateId: string; versionId: string }>(
    (v) => `/v1/agents/${v.templateId}/versions/${v.versionId}/publish`,
    { invalidateKeys: [AF_ROOT] },
    'POST',
  );
}

export function useReleaseVersion() {
  return useApiMutation<AgentRelease, ReleaseVersionVars>(
    (v) => `/v1/agents/${v.templateId}/versions/${v.versionId}/release`,
    { invalidateKeys: [AF_ROOT] },
    'POST',
  );
}

export function useRetireVersion() {
  return useApiMutation<AgentVersion, { templateId: string; versionId: string }>(
    (v) => `/v1/agents/${v.templateId}/versions/${v.versionId}/retire`,
    { invalidateKeys: [AF_ROOT] },
    'POST',
  );
}

export const VERSION_STATUS_LABEL: Record<VersionStatus, string> = {
  draft: '草稿',
  published: '已发布',
  released: '已上线',
  retired: '已下线',
};

export const TEMPLATE_STATUS_LABEL: Record<TemplateStatus, string> = {
  active: '活跃',
  archived: '已归档',
};
