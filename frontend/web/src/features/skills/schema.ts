/**
 * 管理侧「技能管理」类型 — 字段对齐原 AdminSkills.tsx 的内联结构,
 * 方便从 useState 直接迁过来,fixtures 与 mock 一一对应。
 */
export type SkillType = 'Skill' | 'Tool' | 'MCP';
export type SkillStatus = 'published' | 'draft' | 'graying' | 'retired';
export type RiskLevel = 'low' | 'medium' | 'high';
export type SkillSortKey = 'updated' | 'calls' | 'name';
export type SkillExportField = 'meta' | 'schema' | 'permission' | 'version';
export type SkillExportFormat = 'json' | 'yaml';

export interface SchemaField {
  name: string;
  type: 'string' | 'number' | 'boolean' | 'object' | 'array';
  required: boolean;
  description: string;
}

export interface VersionEntry {
  version: string;
  publisher: string;
  releasedAt: string;
  current?: boolean;
}

export interface AuditEntry {
  time: string;
  actor: string;
  action: string;
}

export interface SkillRuntimeSpec {
  enabled: boolean;
  language: 'python';
  image: string;
  entry: string;
  source: string;
  timeoutMs: number;
  network: 'none' | 'bridge';
  memoryMb: number;
}

export const DEFAULT_SKILL_RUNTIME: SkillRuntimeSpec = {
  enabled: false,
  language: 'python',
  image: 'qzdap/sandbox-python:latest',
  entry: 'main.py',
  source: '',
  timeoutMs: 30000,
  network: 'none',
  memoryMb: 256,
};

// ── 类型专属 profile ──────────────────────────────────────────────────
// Skill 走沙箱(用 SkillRuntimeSpec);Tool / MCP 走各自的 profile。
// 前端收集后随 create/update 提交,后端目前忽略,Phase 2 接入持久化。

export type ToolAuthKind = 'api_key' | 'oauth2' | 'bearer';
export type ToolSourceKind = 'openapi_url' | 'openapi_inline' | 'http_endpoint';
export type ToolNetworkPolicy = 'none' | 'bridge' | 'allowlist';

export interface ToolConfig {
  authKind: ToolAuthKind;
  apiKey?: string;                // 提交时由后端加密,前端只持有明文草稿
  baseUrl: string;
  endpointPath: string;
  httpMethod: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  sourceKind: ToolSourceKind;
  openapiSpec?: Record<string, unknown>;
  networkPolicy: ToolNetworkPolicy;
  allowedHosts: string[];
  timeoutMs: number;
}

export const DEFAULT_TOOL_CONFIG: ToolConfig = {
  authKind: 'api_key',
  baseUrl: '',
  endpointPath: '',
  httpMethod: 'POST',
  sourceKind: 'http_endpoint',
  networkPolicy: 'allowlist',
  allowedHosts: [],
  timeoutMs: 30000,
};

export type MCPTransport = 'stdio' | 'sse' | 'streamable-http';

export interface MCPConfig {
  transport: MCPTransport;
  serverUrl: string;              // sse/streamable-http 时使用
  command: string;                // stdio 时使用
  args: string[];
  env: Record<string, string>;
  token?: string;                 // 提交时由后端加密
  probeIntervalS: number;
  connectionTimeoutS: number;
  tokenRotationDays: number;
  selectedTools: string[];        // 从 server 拉取后勾选用哪些
}

export const DEFAULT_MCP_CONFIG: MCPConfig = {
  transport: 'streamable-http',
  serverUrl: '',
  command: '',
  args: [],
  env: {},
  probeIntervalS: 300,
  connectionTimeoutS: 10,
  tokenRotationDays: 90,
  selectedTools: [],
};

// MCP server 拉到的 tool schema(简版,用于前端展示与勾选)
export interface MCPToolInfo {
  name: string;
  description: string;
  inputSchema: SchemaField[];
}

export interface SkillConfig {
  /** Skill 走沙箱,profile 实际上就是 SkillRuntimeSpec;保留包装便于未来扩展。 */
  runtime: SkillRuntimeSpec;
}

export type SkillProfile =
  | ({ kind: 'Skill' } & SkillConfig)
  | ({ kind: 'Tool' } & ToolConfig)
  | ({ kind: 'MCP' } & MCPConfig);

export interface Skill {
  id: string;
  name: string;
  description: string;
  type: SkillType;
  owner: string;
  status: SkillStatus;
  version: string;
  lastUpdate: string;
  calls: number;
  successRate: number;
  errorRate: number;
  avgLatencyMs: number;
  rating: number;
  risk: RiskLevel;
  needConfirm: boolean;
  visibleScope: Array<'公开' | '部门' | '个人'>;
  tags: string[];
  starred: boolean;
  inputSchema: SchemaField[];
  outputSchema: SchemaField[];
  versions: VersionEntry[];
  trend: number[];
  usedByAgents: string[];
  auditLog: AuditEntry[];
  runtime?: SkillRuntimeSpec;
  /** 类型专属 profile;后端当前忽略,Phase 2 持久化到 admin_tool_credentials / admin_mcp_servers。 */
  profile?: SkillProfile;
}

export interface TemplateSeed {
  id: string;
  name: string;
  description: string;
  type: SkillType;
  owner: string;
  iconKey: 'FileText' | 'MessageSquare' | 'FileSpreadsheet' | 'Clock' | 'Database' | 'Webhook' | 'Globe';
  risk: RiskLevel;
  needConfirm: boolean;
  tags: string[];
  inputExample: SchemaField[];
  outputExample: SchemaField[];
}

export interface AdminSkillFilters {
  type?: 'all' | SkillType;
  status?: 'all' | SkillStatus;
  q?: string;
  sort?: SkillSortKey;
}

export interface AdminSkillListParams extends AdminSkillFilters {
  workspaceId?: string;
}

export interface CreateSkillVars {
  id?: string;
  name: string;
  type: SkillType;
  description: string;
  owner: string;
  risk: RiskLevel;
  needConfirm: boolean;
  inputSchema: SchemaField[];
  outputSchema: SchemaField[];
  /** 类型专属配置;后端当前忽略,Phase 2 持久化到 admin_tool_credentials / admin_mcp_servers。 */
  profile?: SkillProfile;
  /** 沙箱执行参数;Skill 类型必填(包含 main.py 的 Python 源码)。 */
  runtime?: SkillRuntimeSpec;
}

export interface UpdateSkillVars {
  id: string;
  patch: Partial<Pick<Skill,
    'name' | 'description' | 'owner' | 'version' | 'type' | 'status' | 'risk' | 'needConfirm' |
    'visibleScope' | 'tags' | 'starred' | 'inputSchema' | 'outputSchema' | 'runtime'>>;
}

export interface DeleteSkillVars {
  id: string;
}

export interface BulkPublishVars {
  ids: string[];
  action: 'publish' | 'retire';
}