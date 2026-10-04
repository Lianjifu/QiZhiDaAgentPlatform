/**
 * 新建审计规则 — 独立页面 /admin/tool-audit/rules/new
 */
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, Shield } from 'lucide-react';
import type { AuditCategory, AuditRuleAction, AuditSeverity } from './schema';
import { useCreateAuditRule } from './useAudit';

export default function AuditRuleCreatePage() {
  const navigate = useNavigate();
  const createRule = useCreateAuditRule();
  const [name, setName] = useState('');
  const [category, setCategory] = useState<AuditCategory>('tool');
  const [condition, setCondition] = useState('');
  const [action, setAction] = useState<AuditRuleAction>('log');
  const [severity, setSeverity] = useState<AuditSeverity>('medium');
  const canSubmit = name.trim().length > 0 && condition.trim().length > 0;

  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-6 p-5 pb-16 sm:p-8 xl:px-10">
      <Link to="/admin/tool-audit" className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--brand)]">
        <ArrowLeft className="h-3.5 w-3.5" />返回工具审计
      </Link>
      <header>
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--brand)]">工具审计</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">新建审计规则</h1>
        <p className="mt-2 max-w-2xl text-sm text-[var(--text-muted)]">为工具调用、数据访问或 MCP 通道设置命中条件与处置动作。</p>
      </header>
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-6">
        <div className="mb-5 flex items-center gap-2 border-b border-[var(--border)] pb-4">
          <Shield className="h-4 w-4 text-[var(--brand)]" />
          <h2 className="text-sm font-semibold">规则配置</h2>
        </div>
        <form
          className="grid gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (!canSubmit || createRule.isPending) return;
            createRule.mutate(
              { name: name.trim(), category, condition: condition.trim(), action, severity },
              { onSuccess: () => navigate('/admin/tool-audit'), onError: () => navigate('/admin/tool-audit') },
            );
          }}
        >
          <div>
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">规则名称</label>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="例如:工具循环调用熔断" className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <div>
              <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">类型</label>
              <select value={category} onChange={(e) => setCategory(e.target.value as AuditCategory)} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]">
                <option value="tool">工具</option>
                <option value="data">数据</option>
                <option value="auth">鉴权</option>
                <option value="mcp">MCP</option>
              </select>
            </div>
            <div>
              <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">动作</label>
              <select value={action} onChange={(e) => setAction(e.target.value as AuditRuleAction)} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]">
                <option value="log">记录</option>
                <option value="alert">告警</option>
                <option value="confirm">需审批</option>
                <option value="block">阻断</option>
              </select>
            </div>
            <div>
              <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">级别</label>
              <select value={severity} onChange={(e) => setSeverity(e.target.value as AuditSeverity)} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]">
                <option value="low">低风险</option>
                <option value="medium">中风险</option>
                <option value="high">高风险</option>
                <option value="critical">严重</option>
              </select>
            </div>
          </div>
          <div>
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">命中条件</label>
            <input value={condition} onChange={(e) => setCondition(e.target.value)} placeholder="例如:tool.repeat_count > 5 within 60s" className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 font-mono text-sm outline-none focus:border-[var(--brand)]" />
          </div>
          <div className="flex justify-end gap-2 border-t border-[var(--border)] pt-5">
            <Link to="/admin/tool-audit" className="rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold">取消</Link>
            <button type="submit" disabled={!canSubmit || createRule.isPending} className="rounded-xl bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white disabled:opacity-40">创建规则</button>
          </div>
        </form>
      </section>
    </div>
  );
}
