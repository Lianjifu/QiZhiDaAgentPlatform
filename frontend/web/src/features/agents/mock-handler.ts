/**
 * 管理侧「智能体工作台」mock handler — 接管 /api/admin/agents/* 端点。
 * dev:demo 注入;prod 永不触达。
 */
import { mockAgents, buildPrompts, buildKnowledgeRefs, buildFlowRefs, DEFAULT_MEMORY_POLICY, SAMPLE_IMPORT, SAMPLE_IMPORT_ZIP } from './fixtures';
import type {
  AgentEntry, PromptDocs, EvalCase,
  CreateAgentVars, UpdateAgentVars, BatchStatusVars, DeleteAgentsVars,
  ToggleStarVars, RunEvalVars, ExportRequestVars, ImportConfirmVars,
} from './schema';

type MockOpts = { method?: string; body?: unknown; query?: Record<string, unknown> };

const state = {
  agents: [...mockAgents] as AgentEntry[],
};

function withDelay<T>(value: T, ms = 60): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

function uid(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
}

function generateEvalCases(agentId: string): EvalCase[] {
  const pool = [
    '订单查询', '退换货流程', '情绪识别', 'FAQ 检索', '工单创建',
    '客户画像', '知识引用', '敏感词检测', '多轮上下文', '工具路由',
    '错误恢复', '回归一致性',
  ];
  const seed = (agentId.charCodeAt(0) || 0) % 4;
  return pool.map((name, idx) => ({
    id: `c-${idx + 1}`,
    name,
    status: (idx + seed) % 7 === 0 ? 'fail' : 'pass',
    latency: 1.2 + ((idx * 0.27) % 1.8),
  }));
}

function mockHistoricalPrompts(version: string, current: PromptDocs): PromptDocs {
  const v = version.toLowerCase();
  if (v.includes('v3.1') || v.includes('v2.6')) {
    return {
      ...current,
      soul: current.soul.replace('默认站在用户业务目标一边', '默认站在用户业务目标与合规一边'),
      user: current.user + '\n- v3.1 新增:支持多语言切换\n',
    };
  }
  if (v.includes('v3.0') || v.includes('v2.5')) {
    return {
      ...current,
      prompt: current.prompt.replace('使用 Markdown,首行说明结论', '使用结构化 Markdown,首行先回答结论'),
      soul: current.soul + '\n## 旧版边界\n- 不接管人工最终决策\n',
      tools: current.tools.replace('关键操作前请求人工确认', '关键操作前请求人工复核'),
    };
  }
  return current;
}

export async function adminAgentsMockHandler(path: string, opts: MockOpts): Promise<unknown> {
  const method = (opts.method ?? 'GET').toUpperCase();

  if (method === 'GET' && path === '/api/admin/agents') return withDelay(state.agents.slice());

  const versionsMatch = path.match(/^\/api\/admin\/agents\/([^/]+)\/versions$/);
  if (method === 'GET' && versionsMatch) {
    const a = state.agents.find((x) => x.id === versionsMatch[1]);
    return a ? withDelay({ agentId: a.id, versions: a.versions }) : withDelay({ error: 'not found' }, 200);
  }

  const evalsMatch = path.match(/^\/api\/admin\/agents\/([^/]+)\/evaluations$/);
  if (method === 'GET' && evalsMatch) {
    const a = state.agents.find((x) => x.id === evalsMatch[1]);
    return a
      ? withDelay({ agentId: a.id, runs: [{ runId: `run-${a.id}-${a.evaluationRuns}`, passRate: a.evaluationPassRate, failedCases: a.evaluationFailedCases, at: new Date().toISOString() }] })
      : withDelay({ error: 'not found' }, 200);
  }

  const evalMatch = path.match(/^\/api\/admin\/agents\/([^/]+)\/eval$/);
  if (method === 'POST' && evalMatch) {
    const id = evalMatch[1];
    const cases = generateEvalCases(id);
    const passRate = (cases.filter((c) => c.status === 'pass').length / cases.length) * 100;
    const a = state.agents.find((x) => x.id === id);
    if (a) {
      a.evaluationPassRate = passRate;
      a.evaluationRuns += 1;
      a.evaluationFailedCases = cases.filter((c) => c.status === 'fail').length;
    }
    return withDelay({ cases, passRate });
  }

  const starMatch = path.match(/^\/api\/admin\/agents\/([^/]+)\/star$/);
  if (method === 'POST' && starMatch) {
    const id = starMatch[1];
    const v = (opts.body ?? {}) as ToggleStarVars;
    const a = state.agents.find((x) => x.id === id);
    if (!a) return withDelay({ error: 'not found' }, 200);
    a.starred = v.starred;
    return withDelay(a);
  }

  const detailMatch = path.match(/^\/api\/admin\/agents\/([^/]+)$/);
  if (method === 'GET' && detailMatch) {
    const a = state.agents.find((x) => x.id === detailMatch[1]);
    return a ? withDelay(a) : withDelay({ error: 'not found' }, 200);
  }
  if (method === 'PATCH' && detailMatch) {
    const v = (opts.body ?? {}) as UpdateAgentVars;
    const a = state.agents.find((x) => x.id === v.id);
    if (!a) return withDelay({ error: 'not found' }, 200);
    Object.assign(a, v.patch);
    return withDelay(a);
  }

  if (method === 'POST' && path === '/api/admin/agents') {
    const v = (opts.body ?? {}) as CreateAgentVars;
    const today = new Date().toISOString().slice(0, 10);
    const created: AgentEntry = {
      id: v.id ?? uid('a'),
      name: v.name,
      description: v.description ?? '',
      category: v.category,
      owner: v.owner,
      tags: v.tags ?? [],
      tone: v.tone ?? 'info',
      status: v.status ?? 'draft',
      version: v.version ?? 'v0.1',
      lastUpdate: '刚刚',
      createdAt: today,
      calls: 0,
      successRate: 0,
      errorRate: 0,
      avgLatencyMs: 0,
      rating: 0,
      tools: v.tools ?? [],
      starred: v.starred ?? false,
      visibleScope: v.visibleScope ?? ['部门'],
      dataAccess: v.dataAccess ?? '基础数据',
      versions: [],
      evaluationPassRate: 0,
      evaluationRuns: 0,
      evaluationFailedCases: 0,
      trend: Array.from({ length: 12 }, () => 0),
      prompts: buildPrompts(v.name, v.category, v.owner),
      customPrompts: [],
      knowledgeRefs: buildKnowledgeRefs(v.category),
      memoryPolicy: { ...DEFAULT_MEMORY_POLICY },
      flowRefs: buildFlowRefs(v.category),
    };
    state.agents.unshift(created);
    return withDelay(created);
  }

  if (method === 'DELETE' && path === '/api/admin/agents/bulk-delete') {
    const v = (opts.body ?? {}) as DeleteAgentsVars;
    const idSet = new Set(v.ids);
    state.agents = state.agents.filter((a) => !idSet.has(a.id));
    return withDelay({ ids: v.ids });
  }

  if (method === 'POST' && path === '/api/admin/agents/batch-status') {
    const v = (opts.body ?? {}) as BatchStatusVars;
    state.agents.forEach((a) => {
      if (v.ids.includes(a.id)) a.status = v.status;
    });
    return withDelay({ ids: v.ids });
  }

  if (method === 'POST' && path === '/api/admin/agents/diff') {
    const body = (opts.body ?? {}) as { agentId: string; leftVersion: string; rightVersion: string };
    const a = state.agents.find((x) => x.id === body.agentId);
    if (!a) return withDelay({ error: 'not found' }, 200);
    return withDelay({
      leftPrompts: mockHistoricalPrompts(body.leftVersion, a.prompts),
      rightPrompts: mockHistoricalPrompts(body.rightVersion, a.prompts),
    });
  }

  if (method === 'POST' && path === '/api/admin/agents/import') {
    const v = (opts.body ?? {}) as ImportConfirmVars;
    const rowsToImport = v.force
      ? v.rows.filter((row) => row.status !== 'missing')
      : v.rows.filter((row) => row.status === 'ok');
    const tonePalette = ['brand', 'info', 'success', 'warn', 'purple'] as const;
    const today = new Date().toISOString().slice(0, 10);
    rowsToImport.forEach((row, idx) => {
      const created: AgentEntry = {
        id: uid('a-imp'),
        name: String(row.source.name || `导入智能体 ${idx + 1}`),
        description: String(row.source.description || '通过导入创建的智能体'),
        category: String(row.source.category || '未分类'),
        owner: String(row.source.owner || '未指定'),
        tags: [],
        tone: tonePalette[idx % tonePalette.length],
        status: 'draft',
        version: 'draft',
        lastUpdate: '刚刚',
        createdAt: today,
        calls: 0,
        successRate: 0,
        errorRate: 0,
        avgLatencyMs: 0,
        rating: 0,
        tools: [],
        starred: false,
        visibleScope: ['部门'],
        dataAccess: '尚未配置',
        versions: [],
        evaluationPassRate: 0,
        evaluationRuns: 0,
        evaluationFailedCases: 0,
        trend: Array.from({ length: 12 }, () => 0),
        prompts: buildPrompts(String(row.source.name || `导入智能体 ${idx + 1}`), String(row.source.category || '未分类'), String(row.source.owner || '未指定')),
        customPrompts: [],
        knowledgeRefs: buildKnowledgeRefs(String(row.source.category || '未分类')),
        memoryPolicy: { ...DEFAULT_MEMORY_POLICY },
        flowRefs: buildFlowRefs(String(row.source.category || '未分类')),
      };
      state.agents.unshift(created);
    });
    return withDelay({ created: rowsToImport.length });
  }

  if (method === 'POST' && path === '/api/admin/agents/export') {
    const v = (opts.body ?? {}) as ExportRequestVars;
    return withDelay({
      url: `data:text/plain;charset=utf-8,${encodeURIComponent(`${v.format.toUpperCase()} export · ${v.fields.length} fields · ${v.ids?.length ?? 'all'} agents`)}`,
      count: v.ids?.length ?? state.agents.length,
    });
  }

  return undefined;
}

/** 供用户侧 catalog 投影读取同一份内存 store */
export function listAdminAgents(): AgentEntry[] {
  return state.agents.slice();
}

export function wrapMockHandlerWithAdminAgents(fallback: (path: string, opts: any) => Promise<unknown>): (path: string, opts: any) => Promise<unknown> {
  return async (path, opts) => {
    const r = await adminAgentsMockHandler(path, opts);
    return r === undefined ? fallback(path, opts) : r;
  };
}
