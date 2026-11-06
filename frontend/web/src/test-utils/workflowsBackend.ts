/**
 * 测试专用的**内存后端** ✓ —— 只给单测用 ✓（演示环境退役后 ✓，
 * 前端不再有任何「mock 接管 API」的运行时能力 ✓）。
 */
import type { Flow } from '@/features/workflows/schema';
import { mockFlows } from '@/features/workflows/fixtures';

const workflows: Flow[] = mockFlows;

/** 供用户侧 catalog 投影读取同一份内存 store */
export function listAdminWorkflows(): Flow[] {
  return workflows.slice();
}

export function wrapMockHandlerWithAdminWorkflows<F extends (path: string, opts: any) => Promise<unknown>>(fallback: F): F {
  const wrapped = (async (path: string, opts: any) => {
    if (path === '/api/admin/workflows' && (!opts?.method || opts.method === 'GET')) {
      return workflows.slice();
    }
    if (path === '/api/admin/workflows' && opts?.method === 'POST') {
      const body = (opts?.body ?? {}) as Partial<Flow>;
      const id = body.id ?? `wf-${Math.random().toString(36).slice(2, 8)}`;
      const created: Flow = {
        id,
        name: body.name ?? '未命名工作流',
        description: body.description ?? '尚未填写描述',
        owner: body.owner ?? '当前管理员',
        scene: body.scene ?? '团队协作',
        trigger: body.trigger ?? '消息触发',
        status: body.status ?? 'draft',
        callCount: body.callCount ?? 0,
        inputs: body.inputs ?? 1,
        outputs: body.outputs ?? 1,
        createdAt: body.createdAt ?? '今天',
        updatedAt: body.updatedAt ?? '刚刚',
        boundAgents: body.boundAgents ?? [],
        versions: body.versions ?? [{ v: 'v0.1-草稿', at: '刚刚', operator: '当前管理员', note: '新建工作流' }],
        initialNodes: body.initialNodes ?? [],
        initialEdges: body.initialEdges ?? [],
      };
      workflows.unshift(created);
      return created;
    }
    const detailMatch = /^\/api\/admin\/workflows\/([^/]+)$/.exec(path);
    if (detailMatch && (!opts?.method || opts.method === 'GET')) {
      const id = detailMatch[1];
      if (id === '__noop__') return null;
      const flow = workflows.find((f) => f.id === id) ?? null;
      if (!flow) throw Object.assign(new Error('workflow not found'), { status: 404 });
      return flow;
    }
    return fallback(path, opts);
  }) as F;
  return wrapped;
}