/**
 * AdminMemory schema — 3 层记忆(L1 短期 / L2 长期 / L3 知识)+ 保留策略 + 晋升事件。
 */
export type MemoryTabId = 'l1' | 'l2' | 'l3';
export type MemoryLayer = 'l1' | 'l2' | 'l3';
export type MemoryRange = '7d' | '30d' | '90d';
export type L1Status = 'active' | 'paused' | 'expired';
export type L2Status = 'pending' | 'confirmed' | 'retired';
export type L3Status = 'draft' | 'published' | 'retired';
export type L2Category = 'preference' | 'fact' | 'style' | 'context';
export type EvictionStrategy = 'lru' | 'fifo' | 'confidence';
export type Tone = 'brand' | 'info' | 'success' | 'warn' | 'danger' | 'purple';

export interface L1Session {
  id: string; userName: string; agentName: string;
  bufferSize: number; tokensUsed: number; ttlMinutes: number; ttlRemainMin: number;
  status: L1Status; lastFlush: string; startedAt: string;
}

export interface L2Fact {
  id: string; userName: string; key: string; value: string; category: L2Category;
  sourceSession: string; confidence: number;
  lastUsed: string; promotedAt: string; status: L2Status; promotedToL3: boolean;
  /** 近 7 天使用时间戳,可选 */
  usageHistory?: string[];
}

/**
 * **团队知识** ✓ —— L3 表退役了 ✓（决策 #1 ✓ —— M-47 ✓）→
 * 现在的来源是 **knowledge 的文档** ✓（一个团队一个知识库 ✓ —— team = 库名 ✓）。
 */
export interface L3Entry {
  id: string; team: string; title: string; summary: string; category: string;
  /** ⚠️ **切片数** ✓ —— 不是命中数 ✓（L3 的命中统计随表一起退役了 ✓）。 */
  chunks: number; updatedAt: string; contributor: string; status: L3Status;
  /** **所属知识库 id** ✓（团队 = 知识库 ✓ —— M-47 ✓）。 */
  kbId: string;
  /** **切片预览** ✓（正文按块切 ✓ —— 详情页展示用 ✓）。 */
  chunkPreview?: Array<{ index: number; snippet: string; heading?: string }>;
  /** 晋升来源 L2 fact id,可选 */
  promotedFromL2Ids?: string[];
}

export interface PromotionEvent {
  /** ⚠️ **L2 → 团队知识** ✓ —— 终点是 knowledge 的文档 ✓（不再是 L3 条目 ✓）。 */
  id: string; layer: 'l1→l2' | 'l2→knowledge';
  label: string; at: string; operator: string;
  /** 晋升结果实体 id(l1→l2 → L2 fact id,l2→knowledge → knowledge doc id) */
  targetId: string;
}

export interface RetentionPolicy {
  /**
   * ⚠️ **只有 L2 了** ✓ —— 「短期记忆」(L1 ✓ —— M-46 ✓ 已退役)与
   * 「知识记忆」(L3 ✓ —— M-47 ✓ 已退役)都没有了 ✓。
   */
  layer: 'l2'; label: string; description: string;
  ttlMinutes: number; maxItems: number; storageMb: number;
  eviction: EvictionStrategy; hitRate: number;
}

export interface MemoryStats {
  l1Active: number; l2Confirmed: number; l3Published: number; events: number;
}

/** 总览趋势 8 期(由旧到新),按所选时间范围步长。 */
export interface MemoryTrend {
  l1Active: number[];
  l2Hits: number[];
  /** ⚠️ **没有 L3 了** ✓ —— 团队知识的趋势归 knowledge ✓（不在这儿编 ✓）。 */
}