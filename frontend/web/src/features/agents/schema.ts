/**
 * 管理侧「智能体工作台」数据类型 — 智能体实体 + 配套子结构 + 变更参数。
 */
export type Tone = 'brand' | 'info' | 'success' | 'warn' | 'danger' | 'purple';
export type Status = 'draft' | 'pending' | 'graying' | 'published' | 'retired';
export type TabId = 'all' | Status;
export type SortKey = 'calls' | 'updated' | 'rating' | 'name';
export type DrawerPanel = 'basic' | 'prompt' | 'skills' | 'knowledge' | 'memory' | 'flow' | 'versions' | 'evaluation' | 'permission';
export type PromptKey = 'prompt' | 'soul' | 'agents' | 'user' | 'tools';
export type ExportField = 'meta' | 'prompt' | 'skills' | 'knowledge' | 'memory' | 'flow';
export type ExportFormat = 'json' | 'csv' | 'yaml';
export type ExportScope = 'all' | 'tab' | 'selected';
export type MemoryRetention = 7 | 30 | 90 | 365;
export type MemoryScope = 'session' | 'user' | 'tenant';
export type FlowTrigger = '消息触发' | '定时触发' | '事件触发' | '手动触发';
export type ImportExtension = 'json' | 'csv' | 'yaml' | 'zip';
export type VisibleScope = '公开' | '部门' | '个人';

export interface ImportRow {
  source: Record<string, string>;
  status: 'ok' | 'duplicate' | 'missing';
  message?: string;
}

export interface VersionEntry {
  version: string;
  publisher: string;
  releasedAt: string;
  current?: boolean;
}

export interface PromptDocs {
  prompt: string;
  soul: string;
  agents: string;
  user: string;
  tools: string;
}

export interface CustomPromptDoc {
  id: string;
  file: string;
  label: string;
  description: string;
  content: string;
}

export interface KnowledgeRef {
  id: string;
  name: string;
  scope: VisibleScope;
  enabled: boolean;
}

export interface MemoryPolicy {
  enabled: boolean;
  retentionDays: MemoryRetention;
  scope: MemoryScope;
  autoSummarize: boolean;
}

export interface FlowRef {
  id: string;
  name: string;
  trigger: FlowTrigger;
  enabled: boolean;
}

export type SkillKind = 'Skill' | 'Tool' | 'MCP';

export interface SkillRef {
  id: string;
  name: string;
  type: SkillKind;
  enabled: boolean;
}

export type SourceModule = 'skills' | 'knowledge' | 'memory' | 'workflows';

export interface SourceLink {
  module: SourceModule;
  href: string;
  label: string;
}

export interface EvalCase {
  id: string;
  name: string;
  status: 'pass' | 'fail';
  latency: number;
}

export interface DiffOp {
  type: 'eq' | 'del' | 'add' | 'mod';
  leftLine?: string;
  rightLine?: string;
}

export interface AgentEntry {
  id: string;
  name: string;
  description: string;
  category: string;
  owner: string;
  tags: string[];
  tone: Tone;
  status: Status;
  version: string;
  lastUpdate: string;
  createdAt: string;
  calls: number;
  successRate: number;
  errorRate: number;
  avgLatencyMs: number;
  rating: number;
  tools: SkillRef[];
  starred: boolean;
  visibleScope: VisibleScope[];
  dataAccess: string;
  versions: VersionEntry[];
  evaluationPassRate: number;
  evaluationRuns: number;
  evaluationFailedCases: number;
  trend: number[];
  prompts: PromptDocs;
  customPrompts: CustomPromptDoc[];
  knowledgeRefs: KnowledgeRef[];
  memoryPolicy: MemoryPolicy;
  flowRefs: FlowRef[];
}

export interface AgentFilters {
  search?: string;
  tab?: TabId;
  scene?: string;
  sortKey?: SortKey;
}

export type CreateAgentVars = Partial<AgentEntry> & { name: string; category: string; owner: string };

export type UpdateAgentVars = { id: string; patch: Partial<AgentEntry> };

export type BatchStatusVars = { ids: string[]; status: Status };

export type DeleteAgentsVars = { ids: string[] };

export type ToggleStarVars = { id: string; starred: boolean };

export type RunEvalVars = { id: string };

export type EvalResult = { cases: EvalCase[]; passRate: number };

export type ExportRequestVars = { scope: ExportScope; format: ExportFormat; fields: ExportField[]; ids?: string[] };

export type ImportConfirmVars = { rows: ImportRow[]; force?: boolean };

export interface DiffRequest {
  agentId: string;
  leftVersion: string;
  rightVersion: string;
}

export interface DiffResult {
  leftPrompts: PromptDocs;
  rightPrompts: PromptDocs;
}

export interface DeletePayload {
  kind: 'single' | 'bulk';
  agentName?: string;
  agentNames?: string[];
}
