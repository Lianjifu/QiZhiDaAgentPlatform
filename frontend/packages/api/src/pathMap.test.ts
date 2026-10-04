import { describe, expect, it } from 'vitest';
import { translateApiPath, _routeTableSize, USER_ID_PLACEHOLDER } from './pathMap';

describe('translateApiPath', () => {
  it('has at least one rule registered', () => {
    expect(_routeTableSize()).toBeGreaterThan(0);
  });

  it('rewrites POST /api/auth/login → POST /v1/identity/login', () => {
    const out = translateApiPath('/api/auth/login', 'POST');
    expect(out.matched).toBe(true);
    expect(out.method).toBe('POST');
    expect(out.backendPath).toBe('/v1/identity/login');
  });

  it('rewrites GET /api/workspaces → GET /v1/identity/workspaces', () => {
    const out = translateApiPath('/api/workspaces', 'GET');
    expect(out.matched).toBe(true);
    expect(out.backendPath).toBe('/v1/identity/workspaces');
  });

  it('rewrites GET /api/tenant/profile → GET /v1/identity/tenants/current', () => {
    const out = translateApiPath('/api/tenant/profile', 'GET');
    expect(out.backendPath).toBe('/v1/identity/tenants/current');
  });

  it('passes through unknown paths with matched=false', () => {
    const out = translateApiPath('/api/agent-profiles/abc123', 'GET');
    expect(out.matched).toBe(false);
    expect(out.backendPath).toBe('/api/agent-profiles/abc123');
    expect(out.method).toBe('GET');
  });

  it('defaults method to GET when none supplied', () => {
    const out = translateApiPath('/api/auth/me');
    expect(out.method).toBe('GET');
    expect(out.backendPath).toBe('/v1/identity/users/me');
  });

  it('returns backend method (not caller method) on a hit', () => {
    // 即使 caller 传 GET,命中后 method 应是 ROUTE_TABLE 里的 method
    const out = translateApiPath('/api/auth/login', 'GET');
    expect(out.method).toBe('POST');
  });

  it('does not rewrite retired /api/memory sandbox routes', () => {
    const out = translateApiPath('/api/memory/records/mem-1', 'GET');
    expect(out.matched).toBe(false);
  });

  it('does not rewrite retired /api/skills sandbox routes', () => {
    const out = translateApiPath('/api/skills/sk-1/install', 'POST');
    expect(out.matched).toBe(false);
  });

  it('passthroughs /api/admin/skills to the catalog backend', () => {
    const out = translateApiPath('/api/admin/skills', 'GET');
    expect(out.matched).toBe(false);
    expect(out.backendPath).toBe('/api/admin/skills');
  });

  it('maps copilot session routes onto /api/sessions', () => {
    expect(translateApiPath('/api/sessions', 'GET').backendPath).toBe('/api/sessions');
    expect(translateApiPath('/api/sessions', 'POST').backendPath).toBe('/api/sessions');
    expect(translateApiPath('/api/sessions/s1', 'GET').backendPath).toBe('/api/sessions/s1');
    expect(translateApiPath('/api/sessions/s1/turns/stream', 'POST').backendPath).toBe(
      '/api/sessions/s1/turns/stream',
    );
  });

  it('rewrites PATCH /api/agents/:id → PATCH /v1/agents/:id', () => {
    const out = translateApiPath('/api/agents/ag-1', 'PATCH');
    expect(out.backendPath).toBe('/v1/agents/ag-1');
    expect(out.matched).toBe(true);
  });

  it('rewrites POST /api/agents/:id/versions → POST /v1/agents/:id/versions', () => {
    const out = translateApiPath('/api/agents/ag-1/versions', 'POST');
    expect(out.backendPath).toBe('/v1/agents/ag-1/versions');
    expect(out.matched).toBe(true);
  });

  it('marks /api/tenant/profile PATCH as unmatched (backend /v1/platform/tenants/me 缺)', () => {
    const out = translateApiPath('/api/tenant/profile', 'PATCH');
    expect(out.matched).toBe(false);
    expect(out.backendPath).toBe('/api/tenant/profile');
  });

  it('does not rewrite retired /api/memory/policy', () => {
    const out = translateApiPath('/api/memory/policy', 'GET');
    expect(out.matched).toBe(false);
  });

  it('passthroughs /api/admin/memory catalog routes', () => {
    const out = translateApiPath('/api/admin/memory/l1', 'GET');
    expect(out.matched).toBe(false);
    expect(out.backendPath).toBe('/api/admin/memory/l1');
  });

  it('does not rewrite retired /api/workflows to /v1/orchestration', () => {
    const out = translateApiPath('/api/workflows/wf-1/run', 'POST');
    expect(out.matched).toBe(false);
    expect(out.backendPath).toBe('/api/workflows/wf-1/run');
  });

  it('passthroughs /api/admin/knowledge and /api/catalog/knowledge', () => {
    const admin = translateApiPath('/api/admin/knowledge/kbs', 'GET');
    expect(admin.matched).toBe(false);
    expect(admin.backendPath).toBe('/api/admin/knowledge/kbs');
    const catalog = translateApiPath('/api/catalog/knowledge', 'GET');
    expect(catalog.matched).toBe(false);
    expect(catalog.backendPath).toBe('/api/catalog/knowledge');
    const docs = translateApiPath('/api/knowledge/docs', 'GET');
    expect(docs.matched).toBe(false);
    expect(docs.backendPath).toBe('/api/knowledge/docs');
  });

  it('falls through retired /api/memory/records', () => {
    const get = translateApiPath('/api/memory/records', 'GET');
    expect(get.matched).toBe(false);
    const post = translateApiPath('/api/memory/records', 'POST');
    expect(post.matched).toBe(false);
    const delete_ = translateApiPath('/api/memory/records/mem-1', 'DELETE');
    expect(delete_.matched).toBe(false);
  });

  it('rule count grows as we add batches', () => {
    expect(_routeTableSize()).toBeGreaterThan(40);
  });

  it('rewrites /api/release-approvals/:id/reject → /v1/approvals/:id/deny', () => {
    // 后端 governance 用 /deny 不是 /reject
    const out = translateApiPath('/api/release-approvals/req-1/reject', 'POST');
    expect(out.backendPath).toBe('/v1/approvals/req-1/deny');
  });

  it('rewrites /api/zero-trust/policies → /v1/policies (no ZT subpath in backend)', () => {
    const out = translateApiPath('/api/zero-trust/policies', 'GET');
    expect(out.backendPath).toBe('/v1/policies');
  });

  it('does not rewrite retired /api/model-providers', () => {
    const out = translateApiPath('/api/model-providers', 'GET');
    expect(out.matched).toBe(false);
    expect(out.backendPath).toBe('/api/model-providers');
  });

  it('does not rewrite retired /api/model-routing/policies', () => {
    const out = translateApiPath('/api/model-routing/policies', 'GET');
    expect(out.matched).toBe(false);
    expect(out.backendPath).toBe('/api/model-routing/policies');
  });

  it('passthroughs /api/admin/models catalog routes', () => {
    const out = translateApiPath('/api/admin/models', 'GET');
    expect(out.matched).toBe(false);
    expect(out.backendPath).toBe('/api/admin/models');
  });

  it('rewrites /api/tools/:id/invoke → /v1/tools/:id/invoke', () => {
    const out = translateApiPath('/api/tools/t-1/invoke', 'POST');
    expect(out.backendPath).toBe('/v1/tools/t-1/invoke');
  });

  it('does not invent /v1/orchestration/tasks (backend has no such endpoint)', () => {
    // backend orchestration 只有 plans + runs,无 /tasks
    const out = translateApiPath('/api/tasks', 'GET');
    expect(out.matched).toBe(false);
    expect(out.backendPath).toBe('/api/tasks');
  });

  // ── batch 3:evaluation 修正 ────────────────────────────────────────
  it('rewrites GET /api/evaluations → GET /v1/eval/runs (list runs)', () => {
    const out = translateApiPath('/api/evaluations', 'GET');
    expect(out.matched).toBe(true);
    expect(out.backendPath).toBe('/v1/eval/runs');
  });

  it('rewrites POST /api/evaluations → POST /v1/eval/runs (create run)', () => {
    const out = translateApiPath('/api/evaluations', 'POST');
    expect(out.backendPath).toBe('/v1/eval/runs');
  });

  it('rewrites GET /api/evaluations/:id → GET /v1/eval/runs/:id (single run)', () => {
    const out = translateApiPath('/api/evaluations/eval-7', 'GET');
    expect(out.backendPath).toBe('/v1/eval/runs/eval-7');
  });

  it('falls through /api/evaluations/:id/{run,stop,retry,report} (backend has no such lifecycle endpoints)', () => {
    // backend /v1/eval 只有 /datasets 和 /runs,没有 /run /stop /retry /report
    const actions = ['run', 'stop', 'retry', 'report'];
    for (const action of actions) {
      const out = translateApiPath(`/api/evaluations/eval-1/${action}`, 'POST');
      expect(out.matched).toBe(false);
      expect(out.backendPath).toBe(`/api/evaluations/eval-1/${action}`);
    }
  });

  it('falls through GET /api/workflows/:id/runs (plan DSL retired)', () => {
    const out = translateApiPath('/api/workflows/wf-1/runs', 'GET');
    expect(out.matched).toBe(false);
    expect(out.backendPath).toBe('/api/workflows/wf-1/runs');
  });

  // ── batch 3:agents phantom rules 移除 ──────────────────────────────
  it('falls through /api/agents/:id/{publish,install,uninstall} (no backend endpoint)', () => {
    // agent_factory 无 /publish /install /uninstall 端点(publish 需要 vid,install 在 skill 模块)
    const actions = ['publish', 'install', 'uninstall'];
    for (const action of actions) {
      const out = translateApiPath(`/api/agents/a-1/${action}`, 'POST');
      expect(out.matched).toBe(false);
    }
  });

  it('falls through /api/agents/:id/skills[/:bindingId] (no backend endpoint)', () => {
    // agent_factory 不暴露 agent→skill 绑定
    const createOut = translateApiPath('/api/agents/a-1/skills', 'POST');
    expect(createOut.matched).toBe(false);
    const deleteOut = translateApiPath('/api/agents/a-1/skills/b-1', 'DELETE');
    expect(deleteOut.matched).toBe(false);
  });

  it('falls through /api/agents/:id/capabilities[/:bindingId] (no backend endpoint)', () => {
    const createOut = translateApiPath('/api/agents/a-1/capabilities', 'POST');
    expect(createOut.matched).toBe(false);
    const deleteOut = translateApiPath('/api/agents/a-1/capabilities/c-1', 'DELETE');
    expect(deleteOut.matched).toBe(false);
  });

  // ── batch 5:knowledge packages verb mismatch ─────────────────────────
  it('falls through DELETE /api/knowledge/packages/:id/delete (package API retired)', () => {
    const out = translateApiPath('/api/knowledge/packages/p-1/delete', 'DELETE');
    expect(out.matched).toBe(false);
  });

  // ── batch 6:uid-注入型路径 ────────────────────────────────────────
  it('marks GET /api/api-keys as needsUserId with <<USER_ID>> placeholder', () => {
    const out = translateApiPath('/api/api-keys', 'GET');
    expect(out.matched).toBe(true);
    expect(out.needsUserId).toBe(true);
    expect(out.backendPath).toBe('/v1/identity/users/<<USER_ID>>/api-keys');
    expect(out.backendPath).toContain(USER_ID_PLACEHOLDER);
  });

  it('does not mark non-user-id paths as needsUserId', () => {
    const out = translateApiPath('/api/workspaces', 'GET');
    expect(out.needsUserId).toBe(false);
    expect(out.backendPath).toBe('/v1/identity/workspaces');
  });

  // ── batch 7:phantom rules 清理 ──────────────────────────────────────
  // 删除 mock 自创、backend 实际未实现的 mapping,让它们走 passthrough,
  // 显式 unmatched 比"matched=true 但得到 404"更清晰。

  describe('batch 7: skills phantom rules removed', () => {
    it('falls through /api/skills/governance/* (backend has no /governance endpoints)', () => {
      const paths = [
        '/api/skills/governance/overview',
        '/api/skills/governance/health',
        '/api/skills/governance/incidents',
        '/api/skills/governance/events',
        '/api/skills/governance/trends',
      ];
      for (const p of paths) {
        const out = translateApiPath(p, 'GET');
        expect(out.matched).toBe(false);
      }
    });

    it('falls through /api/skills/catalog* (backend has no /catalog endpoint)', () => {
      const out = translateApiPath('/api/skills/catalog', 'GET');
      expect(out.matched).toBe(false);
      expect(out.backendPath).toBe('/api/skills/catalog');
    });

    it('falls through /api/skills/audit (backend has no audit endpoint)', () => {
      const out = translateApiPath('/api/skills/audit', 'GET');
      expect(out.matched).toBe(false);
    });

    it('falls through /api/skills/perms (mock perms → permissions, backend has neither)', () => {
      const out = translateApiPath('/api/skills/perms', 'GET');
      expect(out.matched).toBe(false);
    });

    it('falls through /api/skills/import (no backend endpoint)', () => {
      const out = translateApiPath('/api/skills/import', 'POST');
      expect(out.matched).toBe(false);
    });

    it('falls through /api/skills/packs (no backend endpoint)', () => {
      const out = translateApiPath('/api/skills/packs', 'GET');
      expect(out.matched).toBe(false);
    });

    it('falls through /api/skills/:id/{preflight,impact,lifecycle,runtime,permissions,test,versions,governance} (no backend endpoints; uninstall wired in batch 2)', () => {
      const actions = ['preflight', 'impact', 'lifecycle', 'runtime', 'permissions', 'test', 'versions', 'governance'];
      for (const action of actions) {
        const out = translateApiPath(`/api/skills/s-1/${action}`, 'POST');
        expect(out.matched).toBe(false);
      }
    });
  });

  describe('batch 7: memory phantom rules removed', () => {
    it('falls through /api/memory/audit (backend has no /audit endpoint)', () => {
      const out = translateApiPath('/api/memory/audit', 'GET');
      expect(out.matched).toBe(false);
    });

    it('falls through /api/memory/policy (package API retired)', () => {
      const getOut = translateApiPath('/api/memory/policy', 'GET');
      expect(getOut.matched).toBe(false);
      const patchOut = translateApiPath('/api/memory/policy', 'PATCH');
      expect(patchOut.matched).toBe(false);
    });
  });

  describe('batch 7: knowledge phantom rules removed', () => {
    it('falls through /api/knowledge/{reindex,sources*,governance,audit,eval} (no backend endpoints)', () => {
      const paths = [
        ['/api/knowledge/reindex', 'POST'],
        ['/api/knowledge/sources', 'GET'],
        ['/api/knowledge/sources', 'POST'],
        ['/api/knowledge/sources/src-1/sync', 'POST'],
        ['/api/knowledge/governance', 'GET'],
        ['/api/knowledge/governance', 'PATCH'],
        ['/api/knowledge/audit', 'GET'],
        ['/api/knowledge/eval', 'GET'],
      ] as const;
      for (const [p, m] of paths) {
        const out = translateApiPath(p, m as 'GET' | 'POST' | 'PATCH');
        expect(out.matched).toBe(false);
        expect(out.backendPath).toBe(p);
      }
    });

    it('falls through /api/knowledge/packages/:id/{publish,process} (no backend endpoints)', () => {
      const out = translateApiPath('/api/knowledge/packages/p-1/publish', 'POST');
      expect(out.matched).toBe(false);
      const out2 = translateApiPath('/api/knowledge/packages/p-1/process', 'POST');
      expect(out2.matched).toBe(false);
    });
  });

  describe('batch 7: workflows phantom rules removed', () => {
    it('falls through /api/workflows/:id/{audit,versions,validate,draft} (no backend endpoints)', () => {
      const calls: Array<[string, 'GET' | 'POST' | 'PUT']> = [
        ['/api/workflows/wf-1/audit', 'GET'],
        ['/api/workflows/wf-1/versions', 'GET'],
        ['/api/workflows/wf-1/validate', 'POST'],
        ['/api/workflows/wf-1/draft', 'PUT'],
      ];
      for (const [p, m] of calls) {
        const out = translateApiPath(p, m);
        expect(out.matched).toBe(false);
      }
    });

    it('falls through /api/workflows/:id/runs/:runId/{retry,resume} (no backend endpoints)', () => {
      const out = translateApiPath('/api/workflows/wf-1/runs/run-1/retry', 'POST');
      expect(out.matched).toBe(false);
      const out2 = translateApiPath('/api/workflows/wf-1/runs/run-1/resume', 'POST');
      expect(out2.matched).toBe(false);
    });
  });

  describe('batch 7: models phantom rules removed', () => {
    it('falls through /api/model-providers/:id/{discover-models,test-connection,impact} (no backend endpoints)', () => {
      const out = translateApiPath('/api/model-providers/p-1/discover-models', 'GET');
      expect(out.matched).toBe(false);
      const out2 = translateApiPath('/api/model-providers/p-1/test-connection', 'POST');
      expect(out2.matched).toBe(false);
      const out3 = translateApiPath('/api/model-providers/p-1/impact', 'GET');
      expect(out3.matched).toBe(false);
    });

    it('falls through /api/model-routing/policies/:id/{draft,validate,publish} (no backend endpoints)', () => {
      const draft = translateApiPath('/api/model-routing/policies/p-1/draft', 'PATCH');
      expect(draft.matched).toBe(false);
      const validate = translateApiPath('/api/model-routing/policies/p-1/validate', 'POST');
      expect(validate.matched).toBe(false);
      const publish = translateApiPath('/api/model-routing/policies/p-1/publish', 'POST');
      expect(publish.matched).toBe(false);
    });
  });

  // ── batch 7:channels/:id/test 真正映射是 /send(verb mismatch)──────
  it('rewrites /api/channels/:id/test → /v1/channels/:id/send (verb mismatch fix)', () => {
    const out = translateApiPath('/api/channels/c-1/test', 'POST');
    expect(out.matched).toBe(true);
    expect(out.backendPath).toBe('/v1/channels/c-1/send');
  });

  // ── batch 7:知识/记忆/编排 单项端点的反向补强 ────────────────────────
  it('falls through GET /api/memory/records/:id (package API retired)', () => {
    const out = translateApiPath('/api/memory/records/mem-1', 'GET');
    expect(out.matched).toBe(false);
  });

  it('falls through GET /api/skills/invocations (sandbox skill API retired)', () => {
    const out = translateApiPath('/api/skills/invocations', 'GET');
    expect(out.matched).toBe(false);
  });

  it('falls through POST /api/skills/invocations/:invId/cancel (sandbox skill API retired)', () => {
    const out = translateApiPath('/api/skills/invocations/inv-1/cancel', 'POST');
    expect(out.matched).toBe(false);
  });

  it('falls through POST /api/workflows/:id/runs/:runId/cancel (plan DSL retired)', () => {
    const out = translateApiPath('/api/workflows/wf-1/runs/run-1/cancel', 'POST');
    expect(out.matched).toBe(false);
  });

  it('falls through GET /api/workflows/:id/runs/:runId (plan DSL retired)', () => {
    const out = translateApiPath('/api/workflows/wf-1/runs/run-1', 'GET');
    expect(out.matched).toBe(false);
  });

  it('falls through POST /api/workflows (plan DSL retired)', () => {
    const out = translateApiPath('/api/workflows', 'POST');
    expect(out.matched).toBe(false);
  });

  it('passthroughs /api/admin/workflows and /api/catalog/workflows', () => {
    const admin = translateApiPath('/api/admin/workflows', 'GET');
    expect(admin.matched).toBe(false);
    expect(admin.backendPath).toBe('/api/admin/workflows');
    const catalog = translateApiPath('/api/catalog/workflows', 'GET');
    expect(catalog.matched).toBe(false);
    expect(catalog.backendPath).toBe('/api/catalog/workflows');
  });
});