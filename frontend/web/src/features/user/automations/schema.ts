/**
 * 用户侧「我的工作流」实体 — 用户只选择 / 使用 / 收藏,工作流由管理员维护。
 */
export type FlowAvailability = 'available' | 'unavailable';

export interface Flow {
  id: string;
  name: string;
  scene: string;
  description: string;
  owner: string;
  cadence: string;
  availability: FlowAvailability;
  steps: string[];
  lastRun: string;
  usage: number;
}

export interface FlowRun {
  id: string;
  name: string;
  time: string;
  result: string;
  /** ⚠️ **执行结论** ✓ —— 工作流是真的跑了一遍 ✓（不是「记一条使用记录」✓）。 */
  ok?: boolean;
  /** 每一步的执行明细 ✓（节点 / 类别 / 输出 ✓）。 */
  steps?: { nodeId: string; kind: string; label: string; ok: boolean; error?: string }[];
  summary?: string;
  error?: string;
}

export interface FlowListParams {
  q?: string;
  scene?: 'all' | string;
  availability?: 'all' | FlowAvailability;
}

export interface ToggleFavoriteVars {
  id: string;
  on: boolean;
}

export interface RecordRunVars {
  flowId: string;
  note?: string;
}