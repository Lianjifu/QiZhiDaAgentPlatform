/**
 * Mock → 真实后端路径翻译表。
 *
 * 仅显式列出已**确认 backend 存在对应端点**的映射;其余路径原样透传,
 * 由消费方在真模式下触发 404 后逐步补齐(本计划 Phase B 的 proof-of-pattern
 * 只接通 4 条;其他是后续 ticket)。
 *
 * 设计要点:
 * - 数组按"最长前缀优先"排序,命中即停止;避免 `/api/memory` 抢占
 *   `/api/memory/candidates/:id/...`。
 * - 路径参数 `:id/:cid/:docId/:runId` 走 regex match;为简单起见本表只列
 *   静态子段,参数化路径通过 `matchPath` + `rebuildPath` 在运行时合成。
 * - 未命中返回 `null`,调用方走"原路径 + 默认 method"分支;这意味着该
 *   端点暂时只在 mock 模式下可用,真模式会 404(开发期即可见,便于补表)。
 *
 * **Batch 7 (phantom rules cleanup):** 把 mock 自创、backend 实际未实现的端点
 * 从 ROUTE_TABLE 删掉 —— 之前的 batch 1-2 contributor 把 mock 路径 1:1 翻译
 * 到 `/v1/...`,但很多 `/v1/...` 在 backend 不存在(例如 `/v1/skills/governance/...`,
 * `/v1/skills/catalog`, `/v1/knowledge/sources`, `/v1/knowledge/audit` 等)。
 * 这些 phantom rules 在真模式会得到 404,反而**遮蔽**了"该端点需要 backend 实现"
 * 的真相。让它们走 passthrough(显式 unmatched)更清晰;每个 mock-only 端点
 * 留在 mock.ts 内继续可用(mock 模式行为不变)。
 *
 * Batch 7 audit 标准: 路径对应 `@router.<verb>("<path>")` 必须存在于
 * `backend/modules/{module}/src/qzdap/modules/{module}/adapter/http/router.py`
 * 之一(注意前缀可能不在文件里,而在 `APIRouter(prefix="/v1/...")` 中)。
 */
export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

export interface RouteRule {
  /** 后端真实方法(仅 pathMap 真模式使用,mock 模式按调用方原 method 走) */
  method: HttpMethod;
  /** 后端真实路径,含 `:` 参数占位 */
  backendPath: string;
  /** 简要注释,便于维护 */
  note?: string;
  /**
   * true = 这条 rule 不映射(显式 unmatched),用于在 method-tolerant fallback
   * 抢占"看起来像 :id 但实际是 phantom 子段"的路径(例 `/api/skills/audit`)。
   * 数组顺序敏感 —— 必须排在所有"会命中"的规则之前。
   */
  unmatched?: boolean;
}

/**
 * 顺序敏感:长前缀在前。
 *   key:    mock 路径或前缀
 *   value:  { method, backendPath }
 *
 * 当 `key` 含 `:` 时,整段做 regex match,参数顺序与 backendPath 一一对应。
 * backend 路径里的 `:{name}` 占位与 key 里的 `:id` 不必同名 ——
 * 替换按位置进行,只关心捕获顺序。
 */
const ROUTE_TABLE: Array<{ key: string; rule: RouteRule }> = [
  // ── batch 7:phantom 子段显式 unmatched(must come before :id wildcard)─
  // 这些是 mock 自创、backend 未实现的端点。如果不加显式 unmatched,
  // method-tolerant fallback 会让 `/api/skills/:id` GET rule 抢占这些路径
  // (`audit` 之类会作为 `:id` 的 value),误导性地声称"matched=true"。
  // 显式 unmatched 让 translateApiPath 返回 matched=false,前端真模式会 404
  // —— 路径未映射的真相。
  { key: '/api/skills/audit', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/skills/catalog', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/skills/perms', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/skills/import', rule: { method: 'POST', backendPath: '', unmatched: true } },
  { key: '/api/skills/import-package', rule: { method: 'POST', backendPath: '', unmatched: true } },
  { key: '/api/skills/packs', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/skills/dependency-matrix', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/skills/upgrade-plan', rule: { method: 'GET', backendPath: '', unmatched: true } },

  // ── memory phantom 子段(必须排在 :id wildcard 之前)────────────────
  // /api/memory/policy wired in batch 3, removed from phantom list
  { key: '/api/memory/audit', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/memory/candidates', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/memory/refinement/run', rule: { method: 'POST', backendPath: '', unmatched: true } },
  { key: '/api/memory/overview', rule: { method: 'GET', backendPath: '', unmatched: true } },

  // ── knowledge phantom 子段 ────────────────────────────────────────
  { key: '/api/knowledge/reindex', rule: { method: 'POST', backendPath: '', unmatched: true } },
  { key: '/api/knowledge/sources', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/knowledge/sources', rule: { method: 'POST', backendPath: '', unmatched: true } },
  { key: '/api/knowledge/governance', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/knowledge/governance', rule: { method: 'PATCH', backendPath: '', unmatched: true } },
  { key: '/api/knowledge/audit', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/knowledge/eval', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/knowledge/bindings', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/knowledge/processing-jobs', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/knowledge/retrieval-profiles', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/knowledge/citation-trace', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/knowledge/chunks/top', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/knowledge/chunks/rescore', rule: { method: 'POST', backendPath: '', unmatched: true } },
  { key: '/api/knowledge/graph/entities', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/knowledge/graph/relations', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/knowledge/evaluations', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/knowledge/evaluations/run', rule: { method: 'POST', backendPath: '', unmatched: true } },

  // ── workflows phantom 子段 ────────────────────────────────────────
  { key: '/api/workflows/generate', rule: { method: 'POST', backendPath: '', unmatched: true } },
  { key: '/api/workflows/generations', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/workflows/orchestration-sessions', rule: { method: 'GET', backendPath: '', unmatched: true } },

  // ── models phantom 子段 ──────────────────────────────────────────
  { key: '/api/model-providers/discover-models', rule: { method: 'POST', backendPath: '', unmatched: true } },
  { key: '/api/model-providers/test-connection', rule: { method: 'POST', backendPath: '', unmatched: true } },

  // ── identity(prefix=/v1/identity)─────────────────────────────────
  { key: '/api/auth/login', rule: { method: 'POST', backendPath: '/v1/identity/login', note: '响应折形见 responseAdapters.ts' } },
  { key: '/api/auth/me', rule: { method: 'GET', backendPath: '/v1/identity/users/me', note: '取当前用户 profile' } },
  { key: '/api/workspaces', rule: { method: 'GET', backendPath: '/v1/identity/workspaces', note: '租户下工作空间列表' } },
  { key: '/api/tenant/profile', rule: { method: 'GET', backendPath: '/v1/identity/tenants/current', note: '当前租户 profile + plan' } },
  // uid-注入型:backend 用 /users/{uid}/api-keys,前端不知道 uid —— ApiClient
  // 通过 getUserId 回调在 fetch 前替换 <<USER_ID>>
  { key: '/api/api-keys', rule: { method: 'GET', backendPath: '/v1/identity/users/<<USER_ID>>/api-keys', note: '需要当前用户 uid' } },

  // ── skill catalog: frontend already calls /api/admin/skills + /api/catalog/skills
  // (passthrough to qzdap-app). Old /api/skills → /v1/skills sandbox routes are gone.
  { key: '/api/skills/:id/invoke', rule: { method: 'POST', backendPath: '', unmatched: true } },
  { key: '/api/skills/:id/install', rule: { method: 'POST', backendPath: '', unmatched: true } },
  { key: '/api/skills/:id/uninstall', rule: { method: 'POST', backendPath: '', unmatched: true } },
  { key: '/api/skills/:id', rule: { method: 'PATCH', backendPath: '', unmatched: true } },
  { key: '/api/skills/:id', rule: { method: 'DELETE', backendPath: '', unmatched: true } },
  { key: '/api/skills/:id', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/skills/invocations/:invId/cancel', rule: { method: 'POST', backendPath: '', unmatched: true } },
  { key: '/api/skills/invocations/:invId', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/skills/invocations', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/skills', rule: { method: 'POST', backendPath: '', unmatched: true } },
  { key: '/api/skills', rule: { method: 'GET', backendPath: '', unmatched: true } },

  // ── memory catalog: /api/admin/memory  (old /api/memory → /v1/memories retired)
  { key: '/api/memory/records/:id', rule: { method: 'DELETE', backendPath: '', unmatched: true } },
  { key: '/api/memory/records/:id', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/memory/policy', rule: { method: 'PATCH', backendPath: '', unmatched: true } },
  { key: '/api/memory/policy', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/memory/recall', rule: { method: 'POST', backendPath: '', unmatched: true } },
  { key: '/api/memory/records', rule: { method: 'POST', backendPath: '', unmatched: true } },
  { key: '/api/memory/records', rule: { method: 'GET', backendPath: '', unmatched: true } },

  // ── knowledge catalog: /api/admin/knowledge + /api/catalog/knowledge
  // Old /api/knowledge → /v1/knowledge package/asset routes are gone.
  { key: '/api/knowledge/doc/:id', rule: { method: 'DELETE', backendPath: '', unmatched: true } },
  { key: '/api/knowledge/doc/:id', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/knowledge/docs', rule: { method: 'POST', backendPath: '', unmatched: true } },
  { key: '/api/knowledge/packages/:id/delete', rule: { method: 'DELETE', backendPath: '', unmatched: true } },
  { key: '/api/knowledge/packages/:id', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/knowledge/packages', rule: { method: 'POST', backendPath: '', unmatched: true } },
  { key: '/api/knowledge/packages', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/knowledge/retrieve', rule: { method: 'POST', backendPath: '', unmatched: true } },

  // ── workflows: catalog lives on /api/admin/workflows + /api/catalog/workflows
  { key: '/api/workflows/:id/runs/:runId/cancel', rule: { method: 'POST', backendPath: '', unmatched: true } },
  { key: '/api/workflows/:id/runs/:runId', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/workflows/:id/runs', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/workflows/:id/run', rule: { method: 'POST', backendPath: '', unmatched: true } },
  { key: '/api/workflows/:id', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/workflows', rule: { method: 'POST', backendPath: '', unmatched: true } },
  { key: '/api/workflows', rule: { method: 'GET', backendPath: '', unmatched: true } },

  // ── agent_factory(prefix=/v1/agents,inline paths 实际是 /v1/agents/{aid}/*)──
  // 注:agent_factory router 只有 {aid}, {aid}/versions, {aid}/versions/{vid}/{publish,release,retire,notes}
  // 不暴露 :id/skills, :id/capabilities, :id/install, :id/uninstall, :id/publish(无 version_id)。
  // 这些 pathMap 规则全部删除,前端真模式调用时走 passthrough(404);
  // mock 模式自身也未实现这些路径,删除不影响 mock 行为。
  { key: '/api/agents/:id/versions', rule: { method: 'POST', backendPath: '/v1/agents/:id/versions' } },
  { key: '/api/agents/:id/versions', rule: { method: 'GET', backendPath: '/v1/agents/:id/versions' } },
  { key: '/api/agents/:id', rule: { method: 'PATCH', backendPath: '/v1/agents/:id' } },
  { key: '/api/agents/:id', rule: { method: 'GET', backendPath: '/v1/agents/:id' } },
  { key: '/api/agents', rule: { method: 'GET', backendPath: '/v1/agents' } },

  // ── copilot sessions: backend exposes /api/sessions* (catalog-style passthrough)
  { key: '/api/sessions/:id/turns/stream', rule: { method: 'POST', backendPath: '/api/sessions/:id/turns/stream' } },
  { key: '/api/sessions/:id/approvals/:approvalId/approve', rule: { method: 'POST', backendPath: '/api/sessions/:id/approvals/:approvalId/approve' } },
  { key: '/api/sessions/:id/approvals/:approvalId/deny', rule: { method: 'POST', backendPath: '/api/sessions/:id/approvals/:approvalId/deny' } },
  { key: '/api/sessions/:id', rule: { method: 'DELETE', backendPath: '/api/sessions/:id' } },
  { key: '/api/sessions/:id', rule: { method: 'GET', backendPath: '/api/sessions/:id' } },
  { key: '/api/sessions', rule: { method: 'POST', backendPath: '/api/sessions' } },
  { key: '/api/sessions', rule: { method: 'GET', backendPath: '/api/sessions' } },

  // ── channel(prefix=/v1,paths "/channels/*")────────────────────────
  // backend 实际端点: POST|GET "/channels", GET|PATCH "/channels/{id}",
  // POST "/channels/{id}/send", POST "/channels/{id}/webhook"
  // /api/channels/:id/test mock 用 test,backend 用 send(verb mismatch fix)
  // /api/channels/:id/toggle 与 /api/channels/:id/config 都是 PATCH /channels/{id}
  { key: '/api/channels/:id/test', rule: { method: 'POST', backendPath: '/v1/channels/:id/send', note: 'mock 用 test,backend 用 send(verb-mismatch fix)' } },
  { key: '/api/channels/:id/config', rule: { method: 'PATCH', backendPath: '/v1/channels/:id' } },
  { key: '/api/channels/:id/toggle', rule: { method: 'PATCH', backendPath: '/v1/channels/:id' } },
  { key: '/api/channels/:id', rule: { method: 'GET', backendPath: '/v1/channels/:id' } },
  { key: '/api/channels', rule: { method: 'GET', backendPath: '/v1/channels' } },

  // ── evaluation(prefix=/v1/eval)────────────────────────────────────
  // backend 实际端点: GET "/datasets", GET "/datasets/{did}", GET "/datasets/{did}/cases",
  // GET "/runs", GET "/runs/{rid}", POST "/runs"
  // 注:backend 的资源是 /v1/eval/datasets 和 /v1/eval/runs
  // GET /api/evaluations → list runs(backend 不暴露 datasets 列表的 mock 入口)
  // GET /api/evaluations/:id → single run
  // /api/evaluations/:id/{run,stop,retry,report} 全部 fallback passthrough —— backend 无对应端点
  { key: '/api/evaluations/:id', rule: { method: 'GET', backendPath: '/v1/eval/runs/:id' } },
  { key: '/api/evaluations', rule: { method: 'POST', backendPath: '/v1/eval/runs', note: 'create run' } },
  { key: '/api/evaluations', rule: { method: 'GET', backendPath: '/v1/eval/runs', note: 'list runs(backend 不暴露 datasets 列表)' } },

  // ── platform(prefix=/v1/platform)──────────────────────────────────
  // /api/tenant/profile PATCH maps to /v1/platform/tenants/me which doesn't
  // exist in the backend (no PATCH endpoint exposed); mark unmatched so the
  // frontend gets a clean 404 instead of a misleading matched=true.
  { key: '/api/tenant/profile', rule: { method: 'PATCH', backendPath: '/v1/platform/tenants/me', unmatched: true, note: 'backend /v1/platform/tenants/me 缺,显式 unmatched' } },
  { key: '/api/billing', rule: { method: 'GET', backendPath: '/v1/platform/subscriptions/me' } },

  // ── governance(prefix-less, paths 都是 /v1/policies 与 /v1/approvals)──
  // 实际后端路径:approval 用 /deny 不是 /reject
  // 无 /zero-trust 子路径 —— /zero-trust/evaluate /events /authorizations /overview 走 passthrough
  { key: '/api/release-approvals/:id/reject', rule: { method: 'POST', backendPath: '/v1/approvals/:id/deny' } },
  { key: '/api/release-approvals/:id/approve', rule: { method: 'POST', backendPath: '/v1/approvals/:id/approve' } },
  { key: '/api/release-approvals/:id', rule: { method: 'GET', backendPath: '/v1/approvals/:id' } },
  { key: '/api/release-approvals', rule: { method: 'POST', backendPath: '/v1/approvals' } },
  { key: '/api/release-approvals', rule: { method: 'GET', backendPath: '/v1/approvals' } },
  { key: '/api/zero-trust/policies/:id', rule: { method: 'PATCH', backendPath: '/v1/policies/:id' } },
  { key: '/api/zero-trust/policies', rule: { method: 'POST', backendPath: '/v1/policies' } },
  { key: '/api/zero-trust/policies', rule: { method: 'GET', backendPath: '/v1/policies' } },

  // ── observability(prefix=/v1/observability)────────────────────────
  // backend 实际端点: GET "/runs", GET "/costs", GET "/quality/{template_id}/{version_id}"
  { key: '/api/observability/costs', rule: { method: 'GET', backendPath: '/v1/observability/costs' } },
  { key: '/api/observability/runs', rule: { method: 'GET', backendPath: '/v1/observability/runs' } },

  // ── tool(prefix=/v1/tools)─────────────────────────────────────────
  // backend 实际端点: POST|GET ""(列表/创建), GET|PATCH|DELETE "/{tid}",
  // POST "/{name}/invoke", POST "/batch_invoke"
  { key: '/api/tools/:id/invoke', rule: { method: 'POST', backendPath: '/v1/tools/:id/invoke' } },
  { key: '/api/tools/:id', rule: { method: 'PATCH', backendPath: '/v1/tools/:id' } },
  { key: '/api/tools/:id', rule: { method: 'DELETE', backendPath: '/v1/tools/:id' } },
  { key: '/api/tools/:id', rule: { method: 'GET', backendPath: '/v1/tools/:id' } },
  { key: '/api/tools', rule: { method: 'POST', backendPath: '/v1/tools' } },
  { key: '/api/tools', rule: { method: 'GET', backendPath: '/v1/tools' } },

  // ── models: catalog lives on /api/admin/models
  { key: '/api/model-providers/:id/rotate', rule: { method: 'POST', backendPath: '', unmatched: true } },
  { key: '/api/model-providers/:id', rule: { method: 'PATCH', backendPath: '', unmatched: true } },
  { key: '/api/model-providers/:id', rule: { method: 'DELETE', backendPath: '', unmatched: true } },
  { key: '/api/model-providers', rule: { method: 'POST', backendPath: '', unmatched: true } },
  { key: '/api/model-providers', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/models/:id/invoke', rule: { method: 'POST', backendPath: '', unmatched: true } },
  { key: '/api/models/:id', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/models', rule: { method: 'GET', backendPath: '', unmatched: true } },
  { key: '/api/model-routing/policies', rule: { method: 'POST', backendPath: '', unmatched: true } },
  { key: '/api/model-routing/policies', rule: { method: 'GET', backendPath: '', unmatched: true } },

  // ── self_evolution(prefix-less, paths 都是 /v1/evolve/candidates)──
  // backend 实际端点: GET|POST "/v1/evolve/candidates", GET|POST "/v1/evolve/candidates/{id}",
  // POST "/v1/evolve/candidates/{id}/{approve,reject,apply}"
  { key: '/api/evolve/candidates/:id/apply', rule: { method: 'POST', backendPath: '/v1/evolve/candidates/:id/apply' } },
  { key: '/api/evolve/candidates/:id/reject', rule: { method: 'POST', backendPath: '/v1/evolve/candidates/:id/reject' } },
  { key: '/api/evolve/candidates/:id/approve', rule: { method: 'POST', backendPath: '/v1/evolve/candidates/:id/approve' } },
  { key: '/api/evolve/candidates/:id', rule: { method: 'GET', backendPath: '/v1/evolve/candidates/:id' } },
  { key: '/api/evolve/candidates', rule: { method: 'POST', backendPath: '/v1/evolve/candidates' } },
  { key: '/api/evolve/candidates', rule: { method: 'GET', backendPath: '/v1/evolve/candidates' } },
];

export interface TranslatedRoute {
  method: HttpMethod;
  backendPath: string;
  /** true = 在 ROUTE_TABLE 命中;false = 透传原路径 */
  matched: boolean;
  /** true = backendPath 含 <<USER_ID>> 占位,调用方需在 fetch 前替换为当前用户 uid */
  needsUserId?: boolean;
}

function matchExactOrWildcard(key: string, path: string): { name: string; value: string }[] | null {
  // 把 key 转成 regex(`:xxx` → `([^/]+)`),并收集占位名
  const parts = key.split('/');
  const names: string[] = [];
  const reParts = parts.map((p) => {
    if (p.startsWith(':')) {
      names.push(p.slice(1));
      return '([^/]+)';
    }
    if (p === '') return '';
    return p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  });
  const re = new RegExp('^' + reParts.join('/') + '$');
  const m = path.match(re);
  if (!m) return null;
  return names.map((name, i) => ({ name, value: m[i + 1] ?? '' }));
}

/**
 * 按**命名**把 backend 模板里的 `:name` 替换为对应 capture。
 *
 * 例: key='/api/workflows/:id/runs/:runId/cancel',
 *     backendPath='/v1/orchestration/runs/:runId/cancel'
 *   captures=[{name:'id', value:'wf-1'}, {name:'runId', value:'run-1'}]
 *   结果='/v1/orchestration/runs/run-1/cancel'  ← 按 name 匹配,不污染 :runId
 *
 * 如果模板里的 `:name` 在 captures 里找不到对应命名 capture,fallback 到按
 * 出现顺序消费 captures(向后兼容旧规则 —— 不再需要,但保留以防 mock key
 * 用 `:id` 而 backend path 用 `:id` 同名的情况)。
 */
function rebuildBackendPath(template: string, captures: { name: string; value: string }[]): string {
  let fallbackIdx = 0;
  return template.replace(/:[a-zA-Z]+/g, (placeholder) => {
    const name = placeholder.slice(1);
    const hit = captures.find((c) => c.name === name);
    if (hit) return hit.value;
    const fallback = captures[fallbackIdx++];
    return fallback?.value ?? placeholder;
  });
}

/** 标记 backend path 需要调用方从 auth context 注入当前用户的 uid */
export const USER_ID_PLACEHOLDER = '<<USER_ID>>';

/**
 * 把 mock 风格的 `/api/...` 路径翻译到后端真实 `/v1/...` 路径。
 * 未命中 → { backendPath: 原路径, matched: false }。
 *
 * 匹配策略:
 * 1. **method-aware**:先按 (path, method) 找完全匹配的条目
 * 2. **method-tolerant fallback**:没有 method 匹配时,按 path 找任意条目,
 *    仍返回 rule.method 作为方法提示(用于响应里)
 */
export function translateApiPath(
  path: string,
  method: HttpMethod = 'GET',
): TranslatedRoute {
  let fallback: { backendPath: string; method: HttpMethod } | null = null;
  for (const { key, rule } of ROUTE_TABLE) {
    const params = matchExactOrWildcard(key, path);
    if (params === null) continue;
    // 显式 unmatched 立即返回(优先级最高,用于 phantom 路径拒绝 fallback)
    if (rule.unmatched) {
      return { method, backendPath: path, matched: false };
    }
    const backendPath = rebuildBackendPath(rule.backendPath, params);
    const needsUserId = backendPath.includes(USER_ID_PLACEHOLDER);
    if (rule.method === method) {
      return { method: rule.method, backendPath, matched: true, needsUserId };
    }
    // method-tolerant fallback 只在 path 精确等于某 key(无 wildcard 替换)
    // 时启用 —— 否则 `:id` 占位会替任意字符串兜底命中,把 phantom 路径
    // (如 `/api/skills/dependency-matrix`)误判为合法映射。
    if (fallback === null && key === path) {
      fallback = { method: rule.method, backendPath };
    }
  }
  if (fallback !== null) {
    const fallbackNeedsUserId = fallback.backendPath.includes(USER_ID_PLACEHOLDER);
    return { method: fallback.method, backendPath: fallback.backendPath, matched: true, needsUserId: fallbackNeedsUserId };
  }
  // 未命中:保持调用方原 method(GET/POST/PATCH…),仅给个标记便于打日志
  return { method, backendPath: path, matched: false };
}

/** 仅供单测使用:返回当前规则命中数(>=0 表示表非空) */
export function _routeTableSize(): number {
  return ROUTE_TABLE.length;
}