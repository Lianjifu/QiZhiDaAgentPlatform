/**
 * AdminToolAudit 页面测试 — 对齐模型/技能：视图 combobox + 卡片操作 + 抽屉。
 */
import { describe, expect, it, afterEach, beforeAll } from 'vitest';
import { cleanup, fireEvent, screen } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { ApiClient, setApiClient, type RequestOptions } from '@qzdap/web-api';
import { qk } from '@/api/shared/query-keys';
import { renderWithProviders, pageQueryKey } from '@/test-utils/seed';
import AuditPage from './AuditPage';
import AuditDetailPage from './AuditDetailPage';
import AuditRuleCreatePage from './AuditRuleCreatePage';
import {
  mockAuditEntries, mockAuditRisks, mockAuditRules, mockPermissionScopes,
} from './fixtures';

/**
 * 规则的启停是真的写后端 —— 用一个内存版 mock handler 当 ApiClient,
 * PATCH /api/admin/audit/rules/:id 落到这份 store 上,列表重新拉取后状态才变。
 */
const auditRuleStore = mockAuditRules.map((rule) => ({ ...rule }));

const auditMockHandler = async (path: string, opts: RequestOptions = {}) => {
  const method = (opts.method ?? 'GET').toUpperCase();
  if (path === '/api/admin/audit/entries') return mockAuditEntries;
  if (path === '/api/admin/audit/risks') return mockAuditRisks;
  if (path === '/api/admin/audit/scopes') return mockPermissionScopes;
  if (path === '/api/admin/audit/rules') {
    if (method === 'GET') return auditRuleStore.map((rule) => ({ ...rule }));
    return undefined;
  }
  const ruleMatch = /^\/api\/admin\/audit\/rules\/([^/]+)$/.exec(path);
  if (ruleMatch && method === 'PATCH') {
    const target = auditRuleStore.find((rule) => rule.id === ruleMatch[1]);
    if (target) Object.assign(target, (opts.body ?? {}) as Record<string, unknown>);
    return target ? { ...target } : undefined;
  }
  return undefined;
};

beforeAll(() => {
  setApiClient(new ApiClient('', () => null, auditMockHandler));
});

function renderPage() {
  return renderWithProviders(
    <Routes>
      <Route path="/admin/tool-audit" element={<AuditPage />} />
      <Route path="/admin/tool-audit/rules/new" element={<AuditRuleCreatePage />} />
      <Route path="/admin/tool-audit/:id" element={<AuditDetailPage />} />
    </Routes>,
    {
    initialEntries: ['/admin/tool-audit'],
    seeds: [
      { key: pageQueryKey(qk.admin.audit.entries), data: mockAuditEntries },
      { key: pageQueryKey(qk.admin.audit.risks), data: mockAuditRisks },
      { key: pageQueryKey(qk.admin.audit.rules), data: mockAuditRules },
      { key: pageQueryKey(qk.admin.audit.scopes), data: mockPermissionScopes },
    ],
    },
  );
}

describe('AdminToolAudit', () => {
  afterEach(() => cleanup());

  it('renders hero without sub-module tabs', () => {
    renderPage();
    expect(screen.getByText(/审查工具调用与风险规则/)).toBeTruthy();
    expect(screen.queryByLabelText('子模块导航')).toBeNull();
    expect(screen.getByRole('combobox', { name: '视图' })).toBeTruthy();
    expect(screen.getByText(/条审计/)).toBeTruthy();
  });

  it('renders audit entries and card action buttons', () => {
    renderPage();
    expect(screen.getAllByText('tool.send_email').length).toBeGreaterThan(0);
    expect(screen.getAllByText('tool.delete_record').length).toBeGreaterThan(0);
    expect(screen.getAllByLabelText(/^查看审计条目 /).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('button', { name: /导出/ }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('button', { name: /^处置$/ }).length).toBeGreaterThan(0);
  });

  it('navigates to audit detail page when card is clicked', () => {
    renderPage();
    const card = screen.getAllByLabelText(/^查看审计条目 /)[0];
    fireEvent.click(card);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.getByRole('heading', { level: 1, name: mockAuditEntries[0].id })).toBeTruthy();
    expect(screen.getByRole('link', { name: /返回工具审计/ })).toBeTruthy();
  });

  it('switches to risk view via select and toggles resolve', () => {
    renderPage();
    fireEvent.change(screen.getByRole('combobox', { name: '视图' }), { target: { value: 'risk' } });
    expect(screen.getByText(/MCP 鉴权失败/)).toBeTruthy();
    const resolveBtn = screen.getAllByRole('button', { name: /标记处置/ })[0];
    fireEvent.click(resolveBtn);
    expect(screen.getAllByRole('button', { name: /重新打开/ }).length).toBeGreaterThan(0);
  });

  it('switches through risk, permission, and rule views', () => {
    renderPage();
    fireEvent.change(screen.getByRole('combobox', { name: '视图' }), { target: { value: 'permission' } });
    expect(screen.getByText('角色权限清单')).toBeTruthy();
    fireEvent.change(screen.getByRole('combobox', { name: '视图' }), { target: { value: 'rule' } });
    expect(screen.getByText(/Token 过期阻断/)).toBeTruthy();
    fireEvent.change(screen.getByRole('combobox', { name: '视图' }), { target: { value: 'record' } });
    expect(screen.getAllByText('tool.send_email').length).toBeGreaterThan(0);
  });

  it('toggles star and selection on record view', () => {
    renderPage();
    const star = screen.getAllByRole('button', { name: /^收藏 / })[0];
    fireEvent.click(star);
    expect(screen.getAllByRole('button', { name: /取消收藏/ }).length).toBeGreaterThan(0);
    const select = screen.getAllByRole('button', { name: /^选择 / })[0];
    fireEvent.click(select);
    expect(screen.getByLabelText('批量操作')).toBeTruthy();
  });

  it('toggles rule enable/disable on rule view', async () => {
    renderPage();
    fireEvent.change(screen.getByRole('combobox', { name: '视图' }), { target: { value: 'rule' } });
    expect(screen.getByText(/Token 过期阻断/)).toBeTruthy();
    const toggleBtn = screen.getAllByRole('button', { name: /^停用$/ })[0];
    fireEvent.click(toggleBtn);
    // 停用写回后端 → 列表重新拉取 → 该规则的按钮变成「启用」
    expect((await screen.findAllByRole('button', { name: /^启用$/ })).length).toBeGreaterThan(0);
  });

  it('新建规则进入独立页面', () => {
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /新建规则/ }));
    expect(screen.getByRole('heading', { level: 1, name: '新建审计规则' })).toBeTruthy();
    expect(screen.getByRole('link', { name: /返回工具审计/ })).toBeTruthy();
  });

  it('export one entry from card shows notice', () => {
    renderPage();
    const exportBtns = screen.getAllByRole('button', { name: /^导出$/ });
    fireEvent.click(exportBtns[exportBtns.length - 1]);
    expect(screen.getByText(/已导出审计条目/)).toBeTruthy();
  });
});
