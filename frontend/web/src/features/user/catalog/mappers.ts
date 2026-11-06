/**
 * 管理端实体 → 用户侧目录 DTO 投影。
 * 可见规则：已发布/灰度，且可见范围含「公开」或「部门」（工作区成员可用）。
 */
import type { AgentEntry } from '@/features/agents/schema';
import type { Skill as AdminSkill } from '@/features/skills/schema';
import type { Flow as AdminFlow, FlowNodeData } from '@/features/workflows/schema';
import type { Kb, Doc } from '@/features/knowledge/schema';
import type { Agent, AgentCategory } from '@/features/user/library/kinds/agents';
import type { Capability } from '@/features/user/library/kinds/skills';
import type { Flow as UserFlow } from '@/features/user/library/kinds/automations';
import type { KnowledgeKind, KnowledgeResource } from '@/features/user/library/kinds/knowledge';
import type { Node } from 'reactflow';

const OPEN_SCOPES = new Set(['公开', '部门']);

const TONE_CLASS: Record<string, string> = {
  brand: 'bg-[var(--brand-light)] text-[var(--brand)]',
  info: 'bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300',
  success: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300',
  warn: 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300',
  danger: 'bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300',
  purple: 'bg-violet-50 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300',
};

function isWorkspaceVisible(scopes: string[] | string | undefined): boolean {
  if (!scopes) return false;
  const list = Array.isArray(scopes) ? scopes : [scopes];
  return list.some((scope) => OPEN_SCOPES.has(scope));
}

export function mapAgentCategory(raw: string): AgentCategory {
  if (raw.includes('销售')) return '销售支持';
  if (raw.includes('客服')) return '客服应答';
  if (raw.includes('数据')) return '数据分析';
  if (raw.includes('文案') || raw.includes('写作') || raw.includes('市场')) return '文案创作';
  return '企业通用';
}

function projectAgent(entry: AgentEntry): Agent {
  const category = mapAgentCategory(entry.category);
  const exampleHint = entry.prompts?.user?.split('\n').find((line) => line.trim().startsWith('-'))?.replace(/^-\s*/, '')
    ?? `请用「${entry.name}」帮我完成一项与${category}相关的工作。`;
  return {
    id: entry.id,
    name: entry.name,
    description: entry.description,
    category,
    owner: entry.owner,
    useCase: entry.tags.slice(0, 2).join('、') || `${category}相关工作`,
    input: entry.dataAccess ? `与「${entry.dataAccess}」相关的上下文` : '任务目标与必要背景',
    output: '结构化结论与可执行建议',
    example: exampleHint,
    tone: TONE_CLASS[entry.tone] ?? TONE_CLASS.brand,
  };
}

export function projectOpenAgents(entries: AgentEntry[]): Agent[] {
  return entries
    .filter((entry) => (entry.status === 'published' || entry.status === 'graying') && isWorkspaceVisible(entry.visibleScope))
    .map(projectAgent);
}

function projectSkill(skill: AdminSkill): Capability {
  const inputDesc = skill.inputSchema.map((field) => field.description || field.name).filter(Boolean).join('；');
  const outputDesc = skill.outputSchema.map((field) => field.description || field.name).filter(Boolean).join('；');
  return {
    id: skill.id,
    name: skill.name,
    type: skill.type,
    description: skill.description,
    owner: skill.owner,
    useCase: skill.tags.slice(0, 2).join('、') || skill.description,
    input: inputDesc || '按能力说明提供输入',
    output: outputDesc || '结构化结果',
    risk: skill.needConfirm || skill.risk !== 'low' ? 'needsConfirm' : 'low',
    status: skill.status === 'published' || skill.status === 'graying' ? 'available' : 'unavailable',
    tags: skill.tags,
    lastUsed: skill.lastUpdate,
    relatedAgents: skill.usedByAgents ?? [],
  };
}

export function projectOpenSkills(skills: AdminSkill[]): Capability[] {
  return skills
    .filter((skill) => (skill.status === 'published' || skill.status === 'graying') && isWorkspaceVisible(skill.visibleScope))
    .map(projectSkill);
}

function cadenceFromTrigger(trigger: string): string {
  if (trigger.includes('定时')) return '按计划自动运行';
  if (trigger.includes('消息')) return '消息触发';
  if (trigger.includes('事件')) return '事件触发';
  return '手动启动';
}

function projectWorkflow(flow: AdminFlow): UserFlow {
  const steps = (flow.initialNodes as Node<FlowNodeData>[])
    .map((node) => node.data?.label)
    .filter((label): label is string => Boolean(label));
  return {
    id: flow.id,
    name: flow.name,
    scene: flow.scene,
    description: flow.description,
    owner: flow.owner,
    cadence: cadenceFromTrigger(flow.trigger),
    availability: flow.status === 'published' ? 'available' : 'unavailable',
    steps: steps.length > 0 ? steps : ['确认输入', '执行步骤', '查看结果'],
    lastRun: flow.updatedAt,
    usage: flow.callCount,
  };
}

export function projectOpenWorkflows(flows: AdminFlow[]): UserFlow[] {
  return flows
    .filter((flow) => flow.status === 'published')
    .map(projectWorkflow);
}

function mapDocKind(type: Doc['type']): KnowledgeKind {
  if (type === 'policy' || type === 'contract') return '制度';
  if (type === 'meeting' || type === 'manual') return '项目';
  return '指南';
}

export function projectKnowledgeDocs(kbs: Kb[], docs: Doc[]): KnowledgeResource[] {
  const openKbIds = new Set(
    kbs
      .filter((kb) => kb.status === 'indexed' && isWorkspaceVisible(kb.scope))
      .map((kb) => kb.id),
  );
  return docs
    .filter((doc) => doc.status === 'parsed' && openKbIds.has(doc.kbId))
    .map((doc) => {
      const kb = kbs.find((item) => item.id === doc.kbId);
      const excerpt = doc.chunksPreview?.[0]?.snippet
        ?? doc.chunksPreview?.[0]?.heading
        ?? kb?.description
        ?? '暂无摘要';
      return {
        id: doc.id,
        title: doc.name,
        kind: mapDocKind(doc.type),
        description: kb?.description ?? doc.name,
        owner: kb?.owner ?? '知识管理',
        updated: doc.updatedAt,
        tags: kb?.tags?.length ? kb.tags : [doc.type],
        excerpt,
      };
    });
}
