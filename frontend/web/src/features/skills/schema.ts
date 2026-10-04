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