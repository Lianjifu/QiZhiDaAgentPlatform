/**
 * 管理侧「知识管理」schema — 实体(Kb / Doc / Source / Task / EvalCase)
 * 以及创建/批量操作的入参形态。颜色/图标等纯展示字段不入 data。
 *
 * 列表页一级入口仅知识库 + 数据源;文档/任务挂在知识库(或数据源)详情,
 * 评测走侧栏评测中心。
 *
 * 实体关系图(单向引用 → 反向查询链):
 *   Kb 1───* Doc              KbDetailPage 通过 kbId 反查 doc
 *   Source 1───* Doc          SourceDetailPage 通过 doc.sourceId 反查 doc
 *   Kb 1───* Task             KbDetailPage 通过 task.kbId 反查 task
 *   Source 1───* Task         SourceDetailPage 通过 task.sourceId 反查 task
 *   Kb ←──→ EvalCase(expected/actualKb)   KbDetailPage / DocDetailPage 通过 actualKb 反查
 */
export type TabId = 'kb' | 'sources';
export type Range = '7d' | '30d' | '90d';

export type KbStatus = 'indexed' | 'indexing' | 'paused' | 'failed';
export type DocStatus = 'parsed' | 'parsing' | 'pending' | 'failed';
export type DocType = 'manual' | 'policy' | 'meeting' | 'contract' | 'faq';
export type SourceType = 'notion' | 'slack' | 'web' | 'postgres' | 's3' | 'api' | 'folder' | 'confluence';
export type SourceStatus = 'online' | 'syncing' | 'error' | 'paused';
export type TaskStatus = 'pending' | 'running' | 'success' | 'failed' | 'paused';
export type TaskKind = 'index' | 'reindex' | 'rebuild';
export type EvalStatus = 'pass' | 'fail' | 'skipped';
export type KbScope = '公开' | '部门' | '个人';
export type Tone = 'brand' | 'info' | 'success' | 'warn' | 'danger' | 'purple';

export interface Kb {
  id: string;
  name: string;
  description: string;
  owner: string;
  scope: KbScope;
  status: KbStatus;
  docCount: number;
  vectorCount: number;
  updatedAt: string;
  tags: string[];
  tone: 'brand' | 'info' | 'success' | 'warn' | 'danger' | 'purple';
  evalHitRate: number;
}

export interface DocChunk {
  index: number;
  heading?: string;
  snippet: string;
  citations: number;
  tokens: number;
}

export interface Doc {
  id: string;
  name: string;
  type: DocType;
  kbId: string;
  sourceId?: string;
  status: DocStatus;
  sizeKb: number;
  chunks: number;
  chunksPreview?: DocChunk[];
  updatedAt: string;
  citations: number;
  /** 类别(自由文本) —— L3 迁过来时带着(M-47) */
  category?: string;
  /** 发布态 —— ⚠️ 不是 status(status 是处理状态) */
  publishState?: 'draft' | 'published' | 'retired';
  /** 贡献者 */
  contributor?: string;
}

export interface Source {
  id: string;
  name: string;
  type: SourceType;
  status: SourceStatus;
  lastSync: string;
  schedule: string;
  itemCount: number;
  lastError?: string;
}

export interface Task {
  id: string;
  name: string;
  kind: TaskKind;
  kbId: string;
  sourceId?: string;
  status: TaskStatus;
  progress: number;
  items: number;
  startedAt: string;
  duration: string;
  failureReason?: string;
}

export interface EvalCase {
  id: string;
  name: string;
  query: string;
  expectedKb: string;
  actualKb: string;
  status: EvalStatus;
  latency: number;
  mrr: number;
}

export interface CreateKbVars {
  name: string;
  description: string;
  scope: KbScope;
  boundSources: string[];
  retrieval: 'hybrid' | 'semantic' | 'keyword';
  topK: number;
}

export interface CreateSourceVars {
  name: string;
  type: SourceType;
  schedule: string;
}

export interface ToggleKbStatusVars {
  id: string;
}

export interface BatchKbVars {
  ids: string[];
  action: 'rebuild' | 'pause' | 'export';
}