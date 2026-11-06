/**
 * 开发目录的前端测试 —— 三个智能体在管理台上的呈现 + 绑定关系。
 *
 * ⚠️ **数据源是后端那份清单** ✓ —— `backend/composition/qzdap_app/src/qzdap/
 * composition/dev_catalog/catalog.json` ✓（后端落库脚本读同一份 ✓）。
 * 这里的 id 用 **uuid5** 复算 ✓ —— 和后端 ``catalog_id`` 一致 ✓。
 */
import { createHash } from 'node:crypto';
import { describe, expect, it, afterEach } from 'vitest';
import { cleanup, fireEvent, screen, within } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { qk } from '@/api/shared/query-keys';
import { renderWithProviders, pageQueryKey } from '@/test-utils/seed';
import AgentsPage from './AgentsPage';
import AgentDetailPage from './AgentDetailPage';
import type { AgentEntry, FlowRef, KnowledgeRef, SkillRef } from './schema';
import type { Flow } from '@/features/workflows/schema';
import type { Kb } from '@/features/knowledge/schema';
import type { Skill } from '@/features/skills/schema';
import catalog from '../../../../../backend/composition/qzdap_app/src/qzdap/composition/dev_catalog/catalog.json';

// ── uuid5 —— 和 Python 的 uuid.uuid5 逐位对齐 ──────────────────────────
function uuid5(namespace: Buffer, name: string): string {
  const hash = createHash('sha1')
    .update(Buffer.concat([namespace, Buffer.from(name, 'utf-8')]))
    .digest();
  hash[6] = (hash[6] & 0x0f) | 0x50;
  hash[8] = (hash[8] & 0x3f) | 0x80;
  const hex = hash.toString('hex');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20, 32)}`;
}

/** Python 的 ``uuid.NAMESPACE_URL`` ✓. */
const NS_URL = Buffer.from('6ba7b8119dad11d180b400c04fd430c8', 'hex');
const NS = Buffer.from(uuid5(NS_URL, catalog.namespace).replace(/-/g, ''), 'hex');
const idOf = (kind: string, key: string) => uuid5(NS, `${kind}/${key}`);

// ── 从清单拼出前端要的形状 ────────────────────────────────────────────
const skillFixtures: Skill[] = catalog.skills.map((skill) => ({
  id: idOf('skill', skill.key),
  name: skill.name,
  description: skill.description,
  type: skill.type as Skill['type'],
  owner: skill.owner,
  status: 'published',
  version: 'v1.0',
  lastUpdate: '刚刚',
  calls: 0,
  successRate: 100,
  errorRate: 0,
  avgLatencyMs: 0,
  rating: 0,
  risk: skill.risk as Skill['risk'],
  needConfirm: skill.needConfirm,
  visibleScope: skill.visibleScope as Skill['visibleScope'],
  tags: skill.tags,
  starred: false,
  inputSchema: skill.inputSchema,
  outputSchema: skill.outputSchema,
  versions: [],
  trend: [],
  usedByAgents: [],
  auditLog: [],
}) as Skill);

const kbFixtures: Kb[] = catalog.knowledgeBases.map((kb) => ({
  id: idOf('kb', kb.key),
  name: kb.name,
  description: kb.description,
  owner: '目录',
  scope: kb.scope as Kb['scope'],
  status: 'indexed',
  docCount: kb.docs.length,
  vectorCount: kb.docs.length,
  updatedAt: '刚刚',
  tags: [],
  tone: 'info',
  evalHitRate: 0,
}) as Kb);

const flowFixtures: Flow[] = catalog.workflows.map((flow) => ({
  id: idOf('workflow', flow.key),
  name: flow.name,
  description: flow.description,
  owner: flow.owner,
  scene: flow.scene,
  trigger: flow.trigger as Flow['trigger'],
  status: flow.status as Flow['status'],
  callCount: 0,
  inputs: 1,
  outputs: 1,
  createdAt: '2026-11-06',
  updatedAt: '刚刚',
  boundAgents: flow.agentKeys.map((key) => idOf('agent', key)),
  versions: [],
  initialNodes: [],
  initialEdges: [],
}) as Flow);

const agentFixtures: AgentEntry[] = catalog.agents.map((agent) => {
  const tools: SkillRef[] = agent.skillKeys.map((key) => {
    const skill = skillFixtures.find((item) => item.id === idOf('skill', key));
    return { id: idOf('skill', key), name: skill?.name ?? key, type: skill?.type ?? 'Skill', enabled: true };
  });
  const knowledgeRefs: KnowledgeRef[] = agent.kbKeys.map((key) => {
    const kb = kbFixtures.find((item) => item.id === idOf('kb', key));
    return { id: idOf('kb', key), name: kb?.name ?? key, scope: kb?.scope ?? '部门', enabled: true };
  });
  const flowRefs: FlowRef[] = agent.workflowKeys.map((key) => {
    const flow = flowFixtures.find((item) => item.id === idOf('workflow', key));
    return { id: idOf('workflow', key), name: flow?.name ?? key, trigger: flow?.trigger ?? '消息触发', enabled: true };
  });
  return {
    id: idOf('agent', agent.key),
    name: agent.name,
    description: agent.description,
    category: agent.category,
    owner: agent.owner,
    tags: agent.tags,
    tone: agent.tone,
    status: agent.status,
    version: 'v1.0',
    model: agent.model,
    lastUpdate: '刚刚',
    createdAt: '2026-11-06',
    calls: 0,
    successRate: 0,
    errorRate: 0,
    avgLatencyMs: 0,
    rating: 0,
    tools,
    starred: false,
    visibleScope: agent.visibleScope,
    dataAccess: agent.dataAccess,
    versions: [],
    evaluationPassRate: 0,
    evaluationRuns: 0,
    evaluationFailedCases: 0,
    trend: [],
    prompts: agent.prompts,
    customPrompts: [],
    knowledgeRefs,
    memoryPolicy: agent.memoryPolicy,
    flowRefs,
  } as AgentEntry;
});

function renderApp(path: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/admin/agents" element={<AgentsPage />} />
      <Route path="/admin/agents/:id" element={<AgentDetailPage />} />
    </Routes>,
    {
      initialEntries: [path],
      seeds: [
        { key: pageQueryKey(qk.admin.agents.list), data: agentFixtures },
        { key: pageQueryKey(qk.admin.skills.list), data: skillFixtures },
        { key: pageQueryKey([...qk.admin.knowledge.root, 'kbs']), data: kbFixtures },
        { key: pageQueryKey(qk.admin.workflows.list), data: flowFixtures },
        ...agentFixtures.map((agent) => ({
          key: pageQueryKey(qk.admin.agents.detail(agent.id)),
          data: agent,
        })),
      ],
    },
  );
}

describe('开发目录 · 三个业务智能体', () => {
  afterEach(() => cleanup());

  it('renders the three agents on 智能体管理', () => {
    renderApp('/admin/agents');
    expect(screen.getByText('办公智能体')).toBeTruthy();
    expect(screen.getByText('招聘智能体')).toBeTruthy();
    expect(screen.getByText('调研智能体')).toBeTruthy();
    expect(screen.getByText('办公协同 · 办公协同组')).toBeTruthy();
    expect(screen.getByText('人才招聘 · 招聘组')).toBeTruthy();
    expect(screen.getByText('市场调研 · 调研组')).toBeTruthy();
  });

  it.each([
    ['办公智能体', ['日程助手', '会议纪要生成', '文档摘要'], ['员工手册', '会议纪要库'], ['会议纪要生成流程', '报销审批流程']],
    ['招聘智能体', ['简历解析', 'JD 生成', '面试排期'], ['岗位说明书库', '面试题库'], ['简历初筛流程', '面试安排流程']],
    ['调研智能体', ['竞品检索', '竞品对比分析', '调研报告生成'], ['行业报告库', '竞品资料库'], ['竞品分析流程', '调研报告撰写流程']],
  ])('%s 绑定自己的技能 / 知识 / 工作流', (name, skills, kbs, flows) => {
    const agent = agentFixtures.find((item) => item.name === name);
    expect(agent).toBeTruthy();
    renderApp(`/admin/agents/${agent?.id}`);

    const sidebar = screen.getByLabelText('智能体工作区导航');
    fireEvent.click(within(sidebar).getByText('技能'));
    skills.forEach((label) => expect(screen.getByText(label)).toBeTruthy());

    fireEvent.click(within(sidebar).getByText('知识'));
    kbs.forEach((label) => expect(screen.getByText(label)).toBeTruthy());

    fireEvent.click(within(sidebar).getByText('工作流'));
    flows.forEach((label) => expect(screen.getByText(label)).toBeTruthy());
  });

  it('每个智能体的技能绑定都指向真实技能条目', () => {
    const skillIds = new Set(skillFixtures.map((skill) => skill.id));
    agentFixtures.forEach((agent) => {
      expect(agent.tools.length).toBeGreaterThan(0);
      agent.tools.forEach((tool) => {
        expect(skillIds.has(tool.id)).toBe(true);
        expect(tool.enabled).toBe(true);
      });
    });
  });
});
