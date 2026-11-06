/**
 * 测试专用的**内存后端** ✓ —— 只给单测用 ✓（演示环境退役后 ✓，
 * 前端不再有任何「mock 接管 API」的运行时能力 ✓）。
 */
import type { BulkPublishVars, CreateSkillVars, Skill, UpdateSkillVars } from '@/features/skills/schema';
import { mockAdminSkills } from '@/features/skills/fixtures';

const skills: Skill[] = [...mockAdminSkills];

function sleep(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms));
}

function uid(prefix: string) {
  return `${prefix}-${Math.random().toString(36).slice(2, 8)}`;
}

function withDelay<T>(value: T): Promise<T> {
  return sleep(60).then(() => value);
}

function matches(path: string, prefix: string) {
  return path === prefix || path.startsWith(`${prefix}/`);
}

async function adminSkillsMockHandler(
  path: string,
  opts: { method?: string; body?: unknown },
): Promise<unknown> {
  const method = opts.method?.toUpperCase() ?? 'GET';
  if (!matches(path, '/api/admin/skills')) return undefined;

  if (method === 'GET' && path === '/api/admin/skills') {
    return withDelay(skills.map((s) => ({ ...s })));
  }
  if (method === 'POST' && path === '/api/admin/skills') {
    const body = (opts.body ?? {}) as CreateSkillVars;
    const next: Skill = {
      id: body.id || uid('skill'),
      name: body.name,
      description: body.description,
      type: body.type,
      owner: body.owner,
      status: 'draft',
      version: 'draft',
      lastUpdate: '刚刚',
      calls: 0,
      successRate: 0,
      errorRate: 0,
      avgLatencyMs: 0,
      rating: 0,
      risk: body.risk,
      needConfirm: body.needConfirm || body.risk !== 'low',
      visibleScope: ['部门'],
      tags: [],
      starred: false,
      inputSchema: body.inputSchema ?? [],
      outputSchema: body.outputSchema ?? [],
      versions: [],
      trend: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
      usedByAgents: [],
      auditLog: [{ time: '刚刚', actor: body.owner, action: '新建技能' }],
    };
    skills.unshift(next);
    return withDelay({ ...next });
  }
  if (method === 'POST' && path === '/api/admin/skills/bulk') {
    const body = (opts.body ?? {}) as BulkPublishVars;
    for (let i = 0; i < skills.length; i += 1) {
      const skill = skills[i];
      if (!body.ids.includes(skill.id)) continue;
      skills[i] = { ...skill, status: body.action === 'publish' ? 'published' : 'retired', lastUpdate: '刚刚' };
    }
    return withDelay({ affected: body.ids.length });
  }
  const detailMatch = /^\/api\/admin\/skills\/([^/]+)$/.exec(path);
  if (detailMatch) {
    const id = detailMatch[1];
    if (method === 'GET') {
      const skill = skills.find((s) => s.id === id);
      if (!skill) throw new Error('E_NOT_FOUND: 技能不存在');
      return withDelay({ ...skill });
    }
    if (method === 'PATCH') {
      const body = (opts.body ?? {}) as UpdateSkillVars;
      const index = skills.findIndex((s) => s.id === id);
      if (index >= 0) skills[index] = { ...skills[index], ...body.patch, lastUpdate: '刚刚' };
      return withDelay({ ...skills[index] });
    }
    if (method === 'DELETE') {
      const index = skills.findIndex((s) => s.id === id);
      if (index >= 0) skills.splice(index, 1);
      return withDelay({ ok: true as const, id });
    }
  }
  return undefined;
}

/** 供用户侧 catalog 投影读取同一份内存 store */
export function listAdminSkills(): Skill[] {
  return skills.map((skill) => ({ ...skill }));
}

export function wrapMockHandlerWithAdminSkills(
  fallback: (path: string, opts: any) => Promise<unknown> | unknown,
) {
  return async (path: string, opts: any = {}) => {
    const local = await adminSkillsMockHandler(path, opts);
    if (local !== undefined) return local;
    return fallback(path, opts);
  };
}
