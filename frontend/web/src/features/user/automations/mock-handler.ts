/**
 * 本地 mock handler — 在 demo 模式下接管 /api/user/automations 调用。
 * 其他路径走 `mockHandlerWithAdapters`。装配见 `src/main.tsx → installApiClient`。
 */
import type { Flow, FlowRun } from './schema';
import { mockFlows, mockFlowRuns } from './fixtures';

interface MockState {
  flows: Flow[];
  runs: FlowRun[];
}

const state: MockState = {
  flows: [...mockFlows],
  runs: [...mockFlowRuns],
};

function sleep(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms));
}

function withDelay<T>(value: T): Promise<T> {
  return sleep(60).then(() => value);
}

function uid(prefix: string) {
  return `${prefix}-${Math.random().toString(36).slice(2, 8)}`;
}

export async function automationsMockHandler(
  path: string,
  opts: { method?: string; body?: unknown },
): Promise<unknown> {
  const method = opts.method?.toUpperCase() ?? 'GET';

  if (path === '/api/user/automations' && method === 'GET') {
    return withDelay(state.flows.map((flow) => ({ ...flow })));
  }
  if (path === '/api/user/automations/__runs__' && method === 'GET') {
    return withDelay(state.runs.map((run) => ({ ...run })));
  }
  const favMatch = /^\/api\/user\/automations\/([^/]+)\/favorite$/.exec(path);
  if (favMatch && method === 'POST') {
    const id = favMatch[1];
    const body = (opts.body ?? {}) as { on?: boolean };
    return withDelay({ id, on: Boolean(body.on) });
  }
  const runMatch = /^\/api\/user\/automations\/([^/]+)\/run$/.exec(path);
  if (runMatch && method === 'POST') {
    const flowId = runMatch[1];
    const body = (opts.body ?? {}) as { note?: string };
    const flow = state.flows.find((f) => f.id === flowId);
    if (!flow) throw new Error('E_NOT_FOUND: 工作流不存在');
    if (flow.availability !== 'available') throw new Error('E_NOT_AVAILABLE: 工作流当前不可用');
    const run: FlowRun = {
      id: uid('local'),
      name: flow.name,
      time: '刚刚 · 本地演示',
      result: body.note?.trim() ? `演示完成（${body.note.trim()}）` : '演示完成',
      // ⚠️ **本地演示也走「执行」的形状** ✓（真模式返回每一步 ✓）。
      ok: true,
      summary: body.note?.trim() ? `演示完成（${body.note.trim()}）` : '演示完成',
      steps: flow.steps.map((label, index) => ({
        nodeId: `n-${index}`,
        kind: index === 0 ? 'trigger' : index === flow.steps.length - 1 ? 'end' : 'tool',
        label,
        ok: true,
      })),
    };
    state.runs = [run, ...state.runs];
    return withDelay({ ...run });
  }

  return undefined;
}

export function wrapMockHandlerWithAutomations(
  fallback: (path: string, opts: any) => Promise<unknown>,
) {
  return async (path: string, opts: any) => {
    const local = await automationsMockHandler(path, opts);
    if (local !== undefined) return local;
    return fallback(path, opts);
  };
}