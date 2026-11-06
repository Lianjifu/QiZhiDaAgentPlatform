import type { AttachmentReady } from '../blocks/AttachmentChip';
import type { ArtifactReady } from '../blocks/ArtifactCard';
import type { MessageExtras } from '../blocks/MessageExtrasView';
import type { PlanProposal } from '../blocks/PlanProposalCard';
import type { ApiTurn } from '../schema';

/**
 * 一条消息 —— 流式那条与重载那条**同一个形状** ✓。
 *
 * ⚠️ **重载时也要有这些** ✓ —— 否则「重开一个会话, 工具卡片全没了」✗✗
 * （后端的事件流里明明记着 ✓ —— 现在读得出来了 ✓）。
 */
export type ChatMessageView = {
  role: 'user' | 'assistant';
  content: string;
  tools?: string[];
  compacted?: boolean;
  extras?: MessageExtras;
  plan?: PlanProposal;
  artifacts?: ArtifactReady[];
  attachments?: AttachmentReady[];
  usage?: { inputTokens: number; outputTokens: number; costUsd?: number };
  /** 本轮的降级标记 ✓（召回 / 压缩降级时回答是不完整的 ✓ —— 不说就是骗 ✓）。 */
  degraded?: string[];
  /** 这一轮跑了多久 ✓（流式那条是**客户端量的** ✓ —— 后端那份才是权威 ✓）。 */
  durationMs?: number;
  /** 这一轮是哪个轮次 ✓（后端的 ``turn_id`` ✓）。 */
  turnId?: string;
  /** 这一轮失败了 ✓（消息区里放失败卡片 ✓）。 */
  error?: { title?: string; message: string; code?: string; kind: 'provider' | 'generic' };
};

/** 一次对话里的一轮 ✓ —— 一个问题 + 一个回答 ✓。 */
export type TurnView = {
  key: string;
  turnId?: string;
  question?: ChatMessageView;
  answer?: ChatMessageView;
  /** 回答那条消息在消息数组里的下标 ✓ —— 重试要靠它复用原来的位置 ✓。 */
  answerIndex?: number;
};

/** 一轮的「小结」✓ —— 数字全部来自后端 ✓（没有就不显示 ✓ —— 不编 ✓）。 */
export type TurnFacts = {
  durationMs?: number;
  inputTokens?: number;
  outputTokens?: number;
  costUsd?: number;
  toolCount?: number;
  knowledgeCount?: number;
  modelVersion?: string;
  degraded: string[];
  status?: string;
  errorCode?: string | null;
  extras?: MessageExtras;
};

/**
 * 把平铺的消息**分成轮次** ✓ —— 一问一答一块 ✓。
 *
 * ⚠️ **按 ``turnId`` 认轮次** ✓（审批恢复会开**新一轮** ✓ —— 光靠相邻
 * 关系会把两轮并成一块 ✗✗）。
 */
export function buildTurns(messages: ChatMessageView[]): TurnView[] {
  const turns: TurnView[] = [];
  let current: TurnView | undefined;
  messages.forEach((message, index) => {
    const turnId = message.turnId;
    if (message.role === 'user') {
      current = { key: turnId ?? `u-${turns.length}`, turnId, question: message };
      turns.push(current);
      return;
    }
    // ⚠️ **换了一轮** ✓（审批恢复 → 新轮次 ✓）—— 别把两轮并成一块 ✓。
    if (current?.turnId && turnId && current.turnId !== turnId) current = undefined;
    if (!current) {
      current = { key: turnId ?? `a-${turns.length}`, turnId };
      turns.push(current);
    }
    current.answer = message;
    current.answerIndex = index;
  });
  return turns;
}

/**
 * 一轮的事实 —— **后端的那份优先** ✓（它是权威 ✓），流式累积的补空 ✓。
 */
export function resolveTurnFacts(
  turn: TurnView,
  apiTurns: Map<string, ApiTurn>,
): TurnFacts {
  const api = turn.turnId ? apiTurns.get(turn.turnId) : undefined;
  const answer = turn.answer;
  const extras = answer?.extras ?? api?.extras;
  const degraded = Array.from(new Set([...(api?.degraded ?? []), ...(answer?.degraded ?? [])]));
  return {
    durationMs: api?.durationMs ?? answer?.durationMs,
    inputTokens: api?.inputTokens ?? answer?.usage?.inputTokens,
    outputTokens: api?.outputTokens ?? answer?.usage?.outputTokens,
    costUsd: api?.costUsd ?? answer?.usage?.costUsd,
    toolCount: extras?.toolCalls?.length ?? 0,
    knowledgeCount: extras?.knowledgeHits?.hits.length ?? 0,
    modelVersion: api?.modelVersion || undefined,
    degraded,
    status: api?.status,
    errorCode: api?.errorCode ?? null,
    extras,
  };
}

/**
 * ⚠️ **降级标记 → 人话** ✓（后端信封上的 ``flags`` ✓）。
 * ⚠️ **名字对不上就原样显示** ✓（不吞 ✓ —— 未知标记也让人看见 ✓）。
 */
export const DEGRADED_FLAG_TEXT: Record<string, string> = {
  recall_degraded: '知识召回降级',
  compaction_degraded: '上下文压缩降级',
  interactive_degraded: '交互降级',
};

export function degradedLabel(flags: string[]): string {
  return flags.map((flag) => DEGRADED_FLAG_TEXT[flag] ?? flag).join('、');
}
