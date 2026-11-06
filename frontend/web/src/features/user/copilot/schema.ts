/**
 * Copilot 会话 — 类型定义。
 *
 * ⚠️ **会话卡片上的字段都是后端给的** ✓ —— 「最近活动」是**真的最近活动**
 * ✓（后端从轮次表算的 ✓ —— 不是创建时间 ✓）。
 */
import type { MessageExtras } from './blocks/MessageExtrasView';

export interface CopilotSession {
  id: string;
  title: string;
  preview: string;
  /** 最近一次对话的落点 ✓（不是创建时间 ✓）。 */
  updatedAt: string;
  createdAt?: string;
  agentId?: string;
  /** 建会话时写进元数据的智能体名 ✓（不用 join agents ✓）。 */
  agentName?: string;
  model?: string;
  turnCount?: number;
  lastStatus?: string;
  status?: string;
  /** 「等你确认」✓ —— 由轮次表推导 ✓（不是会话上那一列 ✓）。 */
  waitStatus?: string;
}

/**
 * **一轮的事实** ✓ —— 耗时 / token / 成本 / 工具 / 知识命中 ✓。
 *
 * ⚠️ 这些数字**一直躺在库里** ✓（``session_turns`` + ``session_events`` ✓）——
 * 没有这个接口，重开一个会话就全没了 ✗✗。
 */
export interface ApiTurn {
  turnId: string;
  status: string;
  startedAt: string;
  finishedAt: string | null;
  durationMs: number | null;
  modelVersion: string;
  agentVersion: string;
  errorCode: string | null;
  inputTokens: number;
  outputTokens: number;
  costUsd: number;
  degraded: string[];
  extras: MessageExtras;
}

export interface SessionsListParams {
  search?: string;
  limit?: number;
}

export const emptySessions: CopilotSession[] = [];
