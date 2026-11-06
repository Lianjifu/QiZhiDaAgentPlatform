/**
 * 智能体引用的**反向查询** —— 「哪些智能体用了这个技能 / 这个知识库」。
 *
 * ⚠️ **为什么在前端算** ✓ —— 智能体目录里已经带着 ``tools`` /
 * ``knowledgeRefs`` ✓（``GET /api/admin/agents`` 一次就全量返回 ✓），
 * 管理台反查一遍列表即可 ✓；后端那两个字段（``used_by_agents`` /
 * 知识库的引用方）是**没人写的空列** ✓ —— 靠它们显示永远是空的 ✓。
 *
 * 口径：**按 id 比对** ✓ —— 智能体侧存的就是技能 / 知识库的 id ✓。
 */
import { useMemo } from 'react';
import type { AgentEntry } from './schema';
import { useAgentsList } from './useAgents';

/** 用了这个技能的智能体 ✓ */
export function agentsUsingSkill(agents: AgentEntry[], skillId: string): AgentEntry[] {
  if (!skillId) return [];
  return agents.filter((agent) => (agent.tools ?? []).some((tool) => tool.id === skillId));
}

/** 引用了这个知识库的智能体 ✓ */
export function agentsUsingKnowledge(agents: AgentEntry[], kbId: string): AgentEntry[] {
  if (!kbId) return [];
  return agents.filter((agent) =>
    (agent.knowledgeRefs ?? []).some((ref) => ref.id === kbId),
  );
}

export function useAgentsUsingSkill(skillId: string): AgentEntry[] {
  const { data: agents = [] } = useAgentsList();
  return useMemo(() => agentsUsingSkill(agents, skillId), [agents, skillId]);
}

export function useAgentsUsingKnowledge(kbId: string): AgentEntry[] {
  const { data: agents = [] } = useAgentsList();
  return useMemo(() => agentsUsingKnowledge(agents, kbId), [agents, kbId]);
}
