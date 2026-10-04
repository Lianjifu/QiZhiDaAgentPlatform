/**
 * 技能详情侧边栏的 7 个子面板 — 从原 AdminSkills.tsx 抽出。
 * 全部以纯函数组件形式暴露,SkillsPage 通过 panel id 选择渲染。
 */
import {
  Clock, GitBranch, History, Plus, ShieldCheck, Sparkles, Trash2, Zap,
} from 'lucide-react';
import type { SchemaField, Skill, SkillType } from '../schema';
import { DEFAULT_SKILL_RUNTIME } from '../schema';
import { RISK_BADGE, formatCalls } from './constants';
import { Sparkline } from './Sparkline';

export function DrawerPanelBasic({ draft, onChange }: { draft: Skill; onChange: (patch: Partial<Skill>) => void }) {
  const update = (patch: Partial<Skill>) => onChange(patch);
  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">名称</label>
          <input
            type="text"
            value={draft.name}
            onChange={(event) => update({ name: event.target.value })}
            className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]"
          />
        </div>
        <div>
          <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">类型</label>
          <select
            value={draft.type}
            onChange={(event) => update({ type: event.target.value as SkillType })}
            className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]"
          >
            {(['Skill', 'Tool', 'MCP'] as const).map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
      </div>
      <div>
        <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">描述</label>
        <textarea
          value={draft.description}
          onChange={(event) => update({ description: event.target.value })}
          rows={3}
          className="mt-1.5 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 py-2 text-sm outline-none focus:border-[var(--brand)]"
        />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">负责人</label>
          <input type="text" value={draft.owner} onChange={(event) => update({ owner: event.target.value })} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
        </div>
        <div>
          <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">版本号</label>
          <input type="text" value={draft.version} onChange={(event) => update({ version: event.target.value })} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm font-mono outline-none focus:border-[var(--brand)]" />
        </div>
      </div>
      <div>
        <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">可见范围</label>
        <div className="mt-2 flex flex-wrap gap-2">
          {(['公开', '部门', '个人'] as const).map((scope) => {
            const active = draft.visibleScope.includes(scope);
            return (
              <button
                key={scope}
                type="button"
                onClick={() => update({
                  visibleScope: active
                    ? draft.visibleScope.filter((s) => s !== scope)
                    : [...draft.visibleScope, scope],
                })}
                aria-pressed={active}
                className={`rounded-full border px-3 py-1.5 text-[11px] font-medium transition ${active ? 'border-[var(--brand)] bg-[var(--brand-light)] text-[var(--brand)]' : 'border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]'}`}
              >
                {scope}
              </button>
            );
          })}
        </div>
      </div>
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] p-5">
        <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]" htmlFor="skill-status">当前状态</label>
        <div className="mt-3 flex flex-wrap items-center gap-4 text-xs">
          <select
            id="skill-status"
            aria-label="状态"
            value={draft.status}
            onChange={(event) => update({ status: event.target.value as Skill['status'] })}
            className="h-9 rounded-lg border border-[var(--border-strong)] bg-[var(--surface-1)] px-2.5 text-xs outline-none focus:border-[var(--brand)]"
          >
            <option value="draft">草稿</option>
            <option value="graying">灰度中</option>
            <option value="published">已发布</option>
            <option value="retired">已下线</option>
          </select>
          <span className="text-[var(--text-muted)]">最后更新 {draft.lastUpdate}</span>
          <span className="text-[var(--text-muted)]">调用 {formatCalls(draft.calls)}</span>
        </div>
      </div>
    </div>
  );
}

export function DrawerPanelSchema({ draft, onChange }: { draft: Skill; onChange: (patch: Partial<Skill>) => void }) {
  const updateInput = (idx: number, patch: Partial<SchemaField>) => {
    onChange({ inputSchema: draft.inputSchema.map((f, i) => i === idx ? { ...f, ...patch } : f) });
  };
  const updateOutput = (idx: number, patch: Partial<SchemaField>) => {
    onChange({ outputSchema: draft.outputSchema.map((f, i) => i === idx ? { ...f, ...patch } : f) });
  };
  const addInput = () => onChange({ inputSchema: [...draft.inputSchema, { name: '', type: 'string', required: false, description: '' }] });
  const addOutput = () => onChange({ outputSchema: [...draft.outputSchema, { name: '', type: 'string', required: false, description: '' }] });
  const removeInput = (idx: number) => onChange({ inputSchema: draft.inputSchema.filter((_, i) => i !== idx) });
  const removeOutput = (idx: number) => onChange({ outputSchema: draft.outputSchema.filter((_, i) => i !== idx) });
  return (
    <div className="space-y-6">
      <section>
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold">输入参数 · {draft.inputSchema.length} 个字段</p>
          <button type="button" onClick={addInput} className="inline-flex items-center gap-1 rounded-lg border border-[var(--border)] px-2.5 py-1 text-[11px] font-semibold hover:border-[var(--brand)]">
            <Plus className="h-3 w-3" />新增字段
          </button>
        </div>
        <div className="mt-3 space-y-2">
          {draft.inputSchema.length === 0 ? (
            <div className="rounded-xl border border-dashed border-[var(--border)] p-4 text-center text-[11px] text-[var(--text-muted)]">尚未定义输入参数,点击右上角新增。</div>
          ) : draft.inputSchema.map((field, idx) => (
            <div key={`in-${idx}`} className="rounded-xl border border-[var(--border)] bg-[var(--surface-1)] p-3">
              <div className="grid gap-2 sm:grid-cols-[1fr_120px_auto]">
                <input type="text" value={field.name} onChange={(e) => updateInput(idx, { name: e.target.value })} placeholder="参数名" className="h-8 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-2 text-xs outline-none focus:border-[var(--brand)]" />
                <select value={field.type} onChange={(e) => updateInput(idx, { type: e.target.value as SchemaField['type'] })} className="h-8 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-2 text-xs outline-none focus:border-[var(--brand)]">
                  {(['string', 'number', 'boolean', 'object', 'array'] as const).map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
                <button type="button" onClick={() => removeInput(idx)} aria-label="删除字段" className="grid h-8 w-8 place-items-center rounded-lg text-[var(--text-muted)] hover:bg-rose-50 hover:text-rose-600">
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
              <textarea value={field.description} onChange={(e) => updateInput(idx, { description: e.target.value })} placeholder="字段说明" rows={2} className="mt-2 w-full rounded-lg border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-2 py-1.5 text-[11px] outline-none focus:border-[var(--brand)]" />
              <label className="mt-2 flex items-center gap-1.5 text-[11px] text-[var(--text-muted)]">
                <input type="checkbox" checked={field.required} onChange={(e) => updateInput(idx, { required: e.target.checked })} className="h-3.5 w-3.5 accent-[var(--brand)]" />
                必填字段
              </label>
            </div>
          ))}
        </div>
      </section>
      <section>
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold">输出参数 · {draft.outputSchema.length} 个字段</p>
          <button type="button" onClick={addOutput} className="inline-flex items-center gap-1 rounded-lg border border-[var(--border)] px-2.5 py-1 text-[11px] font-semibold hover:border-[var(--brand)]">
            <Plus className="h-3 w-3" />新增字段
          </button>
        </div>
        <div className="mt-3 space-y-2">
          {draft.outputSchema.length === 0 ? (
            <div className="rounded-xl border border-dashed border-[var(--border)] p-4 text-center text-[11px] text-[var(--text-muted)]">尚未定义输出参数。</div>
          ) : draft.outputSchema.map((field, idx) => (
            <div key={`out-${idx}`} className="rounded-xl border border-[var(--border)] bg-[var(--surface-1)] p-3">
              <div className="grid gap-2 sm:grid-cols-[1fr_120px_auto]">
                <input type="text" value={field.name} onChange={(e) => updateOutput(idx, { name: e.target.value })} placeholder="字段名" className="h-8 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-2 text-xs outline-none focus:border-[var(--brand)]" />
                <select value={field.type} onChange={(e) => updateOutput(idx, { type: e.target.value as SchemaField['type'] })} className="h-8 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-2 text-xs outline-none focus:border-[var(--brand)]">
                  {(['string', 'number', 'boolean', 'object', 'array'] as const).map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
                <button type="button" onClick={() => removeOutput(idx)} aria-label="删除字段" className="grid h-8 w-8 place-items-center rounded-lg text-[var(--text-muted)] hover:bg-rose-50 hover:text-rose-600">
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
              <textarea value={field.description} onChange={(e) => updateOutput(idx, { description: e.target.value })} placeholder="字段说明" rows={2} className="mt-2 w-full rounded-lg border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-2 py-1.5 text-[11px] outline-none focus:border-[var(--brand)]" />
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

export function DrawerPanelPermission({ draft, onChange }: { draft: Skill; onChange: (patch: Partial<Skill>) => void }) {
  const update = (patch: Partial<Skill>) => onChange(patch);
  return (
    <div className="space-y-5">
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">风险等级</p>
        <div className="mt-2 grid grid-cols-3 gap-2">
          {(['low', 'medium', 'high'] as const).map((level) => {
            const badge = RISK_BADGE[level];
            const Icon = badge.icon;
            const active = draft.risk === level;
            return (
              <button
                key={level}
                type="button"
                onClick={() => update({ risk: level })}
                aria-pressed={active}
                className={`flex flex-col items-start gap-2 rounded-xl border p-3 text-left transition ${active ? 'border-[var(--brand)] bg-[var(--brand-light)]/40' : 'border-[var(--border)] hover:border-[var(--brand)]'}`}
              >
                <Icon className={`h-4 w-4 ${active ? 'text-[var(--brand)]' : 'text-[var(--text-muted)]'}`} />
                <p className="text-xs font-semibold">{badge.label}</p>
                <p className="text-[10px] text-[var(--text-muted)]">
                  {level === 'low' && '只读或纯计算,无副作用'}
                  {level === 'medium' && '涉及外部查询,影响范围可控'}
                  {level === 'high' && '可能修改数据或写入外部系统'}
                </p>
              </button>
            );
          })}
        </div>
      </div>
      <div className="flex items-center justify-between rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] p-4">
        <div>
          <p className="text-xs font-semibold">需要二次确认</p>
          <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">调用前用户需确认授权,适用于高风险操作。</p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={draft.needConfirm}
          onClick={() => update({ needConfirm: !draft.needConfirm })}
          className={`relative inline-flex h-6 w-11 items-center rounded-full transition ${draft.needConfirm ? 'bg-[var(--brand)]' : 'bg-[var(--bg-hover)]'}`}
        >
          <span className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition ${draft.needConfirm ? 'translate-x-5' : 'translate-x-0.5'}`} />
        </button>
      </div>
      <div>
        <p className="text-xs font-semibold">可见范围</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {draft.visibleScope.map((scope) => (
            <span key={scope} className="inline-flex items-center gap-2 rounded-full bg-[var(--bg-elevated)] px-3 py-1.5 text-xs font-medium">
              <ShieldCheck className="h-3.5 w-3.5 text-[var(--brand)]" />
              {scope}
            </span>
          ))}
        </div>
      </div>
      <div className="rounded-2xl border border-[var(--border)] p-5">
        <p className="text-xs font-semibold">操作审计(最近)</p>
        <ul className="mt-3 space-y-2 text-xs">
          {draft.auditLog.slice(0, 3).map((log, idx) => (
            <li key={idx} className="flex items-center justify-between rounded-lg bg-[var(--bg-elevated)] px-3 py-2">
              <span>{log.actor} · {log.action}</span>
              <span className="text-[var(--text-muted)]">{log.time}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export function DrawerPanelVersions({ draft }: { draft: Skill }) {
  if (draft.versions.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-[var(--border)] p-6 text-center">
        <GitBranch className="mx-auto h-6 w-6 text-[var(--text-muted)]" />
        <p className="mt-3 text-sm font-semibold">暂无历史版本</p>
        <p className="mt-1 text-xs text-[var(--text-muted)]">发布后将自动记录每个版本与发布时间。</p>
      </div>
    );
  }
  return (
    <div className="space-y-3">
      {draft.versions.map((version) => (
        <div key={version.version} className={`flex items-center gap-3 rounded-xl border p-4 ${version.current ? 'border-emerald-200 bg-emerald-50/40 dark:border-emerald-500/30 dark:bg-emerald-500/5' : 'border-[var(--border)]'}`}>
          <span className={`grid h-10 w-10 place-items-center rounded-lg ${version.current ? 'bg-emerald-100 text-emerald-700' : 'bg-[var(--bg-elevated)] text-[var(--text-muted)]'}`}>
            <GitBranch className="h-4 w-4" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <p className="text-sm font-semibold">{version.version}</p>
              {version.current && <span className="rounded-full bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700">当前</span>}
            </div>
            <p className="mt-0.5 text-xs text-[var(--text-muted)]">{version.publisher} · 发布于 {version.releasedAt}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

export function DrawerPanelMonitor({ draft }: { draft: Skill }) {
  const total = draft.calls;
  const successRate = draft.successRate;
  const errorRate = draft.errorRate;
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4 rounded-2xl border border-[var(--border)] p-5">
        <span className="grid h-12 w-12 place-items-center rounded-xl bg-[var(--brand-light)] text-[var(--brand)]">
          <Zap className="h-6 w-6" />
        </span>
        <div className="flex-1">
          <p className="text-[10px] uppercase tracking-[0.18em] text-[var(--text-muted)]">本月调用</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums">{formatCalls(total)}</p>
        </div>
        <div className="text-right">
          <p className="text-[10px] uppercase tracking-[0.18em] text-[var(--text-muted)]">成功率</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums">{total > 0 ? successRate.toFixed(2) : '—'}%</p>
        </div>
      </div>
      <div className="rounded-2xl border border-[var(--border)] p-5">
        <p className="text-xs font-semibold">调用趋势 · 过去 12 个月</p>
        <div className="mt-3 flex items-center justify-center">
          <Sparkline data={draft.trend} stroke="var(--brand)" />
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-xl border border-[var(--border)] p-4">
          <p className="text-[10px] uppercase tracking-[0.18em] text-[var(--text-muted)]">错误率</p>
          <p className="mt-2 text-lg font-semibold tabular-nums">{total > 0 ? errorRate.toFixed(2) : '—'}%</p>
        </div>
        <div className="rounded-xl border border-[var(--border)] p-4">
          <p className="text-[10px] uppercase tracking-[0.18em] text-[var(--text-muted)]">响应延迟</p>
          <p className="mt-2 text-lg font-semibold tabular-nums">{total > 0 ? `${(draft.avgLatencyMs / 1000).toFixed(2)}s` : '—'}</p>
        </div>
        <div className="rounded-xl border border-[var(--border)] p-4">
          <p className="text-[10px] uppercase tracking-[0.18em] text-[var(--text-muted)]">评分</p>
          <p className="mt-2 text-lg font-semibold tabular-nums">{total > 0 ? draft.rating.toFixed(1) : '—'}</p>
        </div>
      </div>
    </div>
  );
}

export function DrawerPanelAgents({ draft }: { draft: Skill }) {
  if (draft.usedByAgents.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-[var(--border)] p-6 text-center">
        <Sparkles className="mx-auto h-6 w-6 text-[var(--text-muted)]" />
        <p className="mt-3 text-sm font-semibold">暂未被任何智能体使用</p>
        <p className="mt-1 text-xs text-[var(--text-muted)]">在智能体编辑器中关联该技能,即可在此处看到引用方。</p>
      </div>
    );
  }
  return (
    <div>
      <p className="text-xs text-[var(--text-muted)]">下列智能体已配置使用本技能,修改技能字段后,变更将随下次发布生效。</p>
      <ul className="mt-4 space-y-2">
        {draft.usedByAgents.map((name) => (
          <li key={name} className="flex items-center gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface-1)] p-3">
            <span className="grid h-9 w-9 place-items-center rounded-lg bg-[var(--brand-light)] text-[var(--brand)]">
              <Sparkles className="h-4 w-4" />
            </span>
            <span className="flex-1 text-xs font-semibold">{name}</span>
            <span className="rounded-full bg-[var(--bg-elevated)] px-2 py-0.5 text-[10px] text-[var(--text-muted)]">已关联</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function DrawerPanelAudit({ draft }: { draft: Skill }) {
  if (draft.auditLog.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-[var(--border)] p-6 text-center">
        <History className="mx-auto h-6 w-6 text-[var(--text-muted)]" />
        <p className="mt-3 text-sm font-semibold">暂无变更记录</p>
      </div>
    );
  }
  return (
    <div>
      <p className="text-xs text-[var(--text-muted)]">按时间倒序展示本技能的发布、权限调整与字段修改记录。</p>
      <ul className="mt-4 space-y-2">
        {draft.auditLog.map((log, idx) => (
          <li key={idx} className="flex items-start gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface-1)] p-3">
            <span className="mt-0.5 grid h-7 w-7 place-items-center rounded-lg bg-[var(--bg-elevated)] text-[var(--text-muted)]">
              <Clock className="h-3.5 w-3.5" />
            </span>
            <div className="flex-1">
              <p className="text-xs font-semibold">{log.actor} · {log.action}</p>
              <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">{log.time}</p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function DrawerPanelRuntime({ draft, onChange }: { draft: Skill; onChange: (patch: Partial<Skill>) => void }) {
  const runtime = { ...DEFAULT_SKILL_RUNTIME, ...draft.runtime };
  const update = (patch: Partial<typeof runtime>) => onChange({ runtime: { ...runtime, ...patch } });
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] p-4">
        <div>
          <p className="text-xs font-semibold">在 gVisor 沙箱中执行</p>
          <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">仅已发布且开启运行时的技能会被智能体调用。</p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={runtime.enabled}
          onClick={() => update({ enabled: !runtime.enabled })}
          className={`relative inline-flex h-6 w-11 items-center rounded-full transition ${runtime.enabled ? 'bg-[var(--brand)]' : 'bg-[var(--bg-hover)]'}`}
        >
          <span className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition ${runtime.enabled ? 'translate-x-5' : 'translate-x-0.5'}`} />
        </button>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">镜像</label>
          <input
            type="text"
            value={runtime.image}
            onChange={(event) => update({ image: event.target.value })}
            className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm font-mono outline-none focus:border-[var(--brand)]"
          />
        </div>
        <div>
          <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">入口文件</label>
          <input
            type="text"
            value={runtime.entry}
            onChange={(event) => update({ entry: event.target.value })}
            className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm font-mono outline-none focus:border-[var(--brand)]"
          />
        </div>
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        <div>
          <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">超时 (ms)</label>
          <input
            type="number"
            value={runtime.timeoutMs}
            onChange={(event) => update({ timeoutMs: Number(event.target.value) || 30000 })}
            className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]"
          />
        </div>
        <div>
          <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">内存 (MB)</label>
          <input
            type="number"
            value={runtime.memoryMb}
            onChange={(event) => update({ memoryMb: Number(event.target.value) || 256 })}
            className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]"
          />
        </div>
        <div>
          <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">网络</label>
          <select
            value={runtime.network}
            onChange={(event) => update({ network: event.target.value as 'none' | 'bridge' })}
            className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]"
          >
            <option value="none">none</option>
            <option value="bridge">bridge</option>
          </select>
        </div>
      </div>
      <div>
        <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">Python 源码</label>
        <textarea
          value={runtime.source}
          onChange={(event) => update({ source: event.target.value })}
          rows={12}
          placeholder={"import json\nprint(json.load(open('/work/input.json')))"}
          className="mt-1.5 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 py-2 font-mono text-xs outline-none focus:border-[var(--brand)]"
        />
      </div>
    </div>
  );
}