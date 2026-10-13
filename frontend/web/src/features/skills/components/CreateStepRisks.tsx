/**
 * Step 3 子组件 — 3 个 type 各自的风险 + 权限配置。
 *
 * - SkillRiskPanel: 沙箱镜像/网络/超时 + 通用风险等级 + 二次确认
 * - ToolRiskPanel : 出站白名单确认 + 确认粒度 + 通用风险等级 + 二次确认
 * - MCPRiskPanel : 探活间隔 + token 轮换 + 连接超时 + 通用风险等级 + 二次确认
 */
import { useState } from 'react';
import { Clock, KeyRound, Network, Plus, RefreshCw, X } from 'lucide-react';
import type { MCPConfig, RiskLevel, SchemaField, ToolConfig } from '../schema';
import { RISK_BADGE } from './constants';
import { FieldLabel } from './CreateStepConfigs';

const RISK_OPTIONS: Array<{ value: RiskLevel; label: string; description: string }> = [
  { value: 'low', label: RISK_BADGE.low.label, description: '只读、无副作用' },
  { value: 'medium', label: RISK_BADGE.medium.label, description: '有外部调用,可能产生数据' },
  { value: 'high', label: RISK_BADGE.high.label, description: '写操作、敏感数据、不可逆' },
];

export function RiskLevelPicker({ value, onChange }: { value: RiskLevel; onChange: (v: RiskLevel) => void }) {
  return (
    <div>
      <FieldLabel hint="决定默认确认粒度与告警">风险等级</FieldLabel>
      <div className="mt-1 grid grid-cols-3 gap-2">
        {RISK_OPTIONS.map((opt) => {
          const active = opt.value === value;
          return (
            <button
              key={opt.value}
              type="button"
              onClick={() => onChange(opt.value)}
              aria-pressed={active}
              className={`rounded-xl border p-3 text-left transition ${
                active ? 'border-[var(--brand)] bg-[var(--brand-light)]' : 'border-[var(--border)] hover:border-[var(--brand)]'
              }`}
            >
              <p className={`text-xs font-semibold ${active ? 'text-[var(--brand)]' : 'text-[var(--text-secondary)]'}`}>{opt.label}</p>
              <p className="mt-0.5 text-[10px] leading-4 text-[var(--text-muted)]">{opt.description}</p>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function NeedConfirmSwitch({ value, onChange, hint }: { value: boolean; onChange: (v: boolean) => void; hint?: string }) {
  return (
    <div className="flex items-center justify-between rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] p-4">
      <div>
        <p className="text-xs font-semibold">需要二次确认</p>
        <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">{hint ?? '调用前用户需授权。'}</p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={value}
        onClick={() => onChange(!value)}
        className={`relative inline-flex h-6 w-11 items-center rounded-full transition ${value ? 'bg-[var(--brand)]' : 'bg-[var(--bg-hover)]'}`}
      >
        <span className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition ${value ? 'translate-x-5' : 'translate-x-0.5'}`} />
      </button>
    </div>
  );
}

// ─── Skill · Step 3 (沙箱配置) ──────────────────────────────────────────

export function SkillRiskPanel({
  risk, needConfirm, onRiskChange, onNeedConfirmChange, sandbox, onSandboxChange,
}: {
  risk: RiskLevel;
  needConfirm: boolean;
  onRiskChange: (v: RiskLevel) => void;
  onNeedConfirmChange: (v: boolean) => void;
  sandbox: { image: string; entry: string; source: string; timeoutMs: number; network: 'none' | 'bridge'; memoryMb: number };
  onSandboxChange: (next: typeof sandbox) => void;
}) {
  const update = (patch: Partial<typeof sandbox>) => onSandboxChange({ ...sandbox, ...patch });
  return (
    <div className="space-y-5">
      <RiskLevelPicker value={risk} onChange={onRiskChange} />
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] p-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">沙箱配置</p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <div>
            <FieldLabel>镜像</FieldLabel>
            <input
              value={sandbox.image}
              onChange={(e) => update({ image: e.target.value })}
              className="h-10 w-full rounded-xl border border-[var(--border-strong)] bg-white px-3 font-mono text-xs outline-none focus:border-[var(--brand)]"
            />
          </div>
          <div>
            <FieldLabel>入口</FieldLabel>
            <input
              value={sandbox.entry}
              onChange={(e) => update({ entry: e.target.value })}
              className="h-10 w-full rounded-xl border border-[var(--border-strong)] bg-white px-3 font-mono text-xs outline-none focus:border-[var(--brand)]"
            />
          </div>
          <div>
            <FieldLabel>超时 (ms)</FieldLabel>
            <input
              type="number"
              min={1000}
              max={120000}
              value={sandbox.timeoutMs}
              onChange={(e) => update({ timeoutMs: Number(e.target.value) })}
              className="h-10 w-full rounded-xl border border-[var(--border-strong)] bg-white px-3 text-xs outline-none focus:border-[var(--brand)]"
            />
          </div>
          <div>
            <FieldLabel>内存 (MB)</FieldLabel>
            <input
              type="number"
              min={32}
              max={4096}
              value={sandbox.memoryMb}
              onChange={(e) => update({ memoryMb: Number(e.target.value) })}
              className="h-10 w-full rounded-xl border border-[var(--border-strong)] bg-white px-3 text-xs outline-none focus:border-[var(--brand)]"
            />
          </div>
          <div className="sm:col-span-2">
            <FieldLabel>网络隔离</FieldLabel>
            <div className="flex gap-2">
              {(['none', 'bridge'] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => update({ network: mode })}
                  aria-pressed={sandbox.network === mode}
                  className={`flex-1 rounded-xl border p-2 text-xs font-semibold ${
                    sandbox.network === mode ? 'border-[var(--brand)] bg-[var(--brand-light)] text-[var(--brand)]' : 'border-[var(--border)] text-[var(--text-secondary)]'
                  }`}
                >
                  {mode === 'none' ? 'none (无外网)' : 'bridge (允许出站)'}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
      <NeedConfirmSwitch value={needConfirm} onChange={onNeedConfirmChange} hint="Skill 执行前用户需授权。" />
    </div>
  );
}

// ─── Tool · Step 3 (出站 + 确认粒度) ────────────────────────────────────

export type ToolConfirmGranularity = 'always' | 'writes_only' | 'credential_first';

const CONFIRM_OPTIONS: Array<{ value: ToolConfirmGranularity; label: string; description: string }> = [
  { value: 'always', label: '每次调用', description: '任何 Tool 调用都需用户授权' },
  { value: 'writes_only', label: '仅写操作', description: 'GET/HEAD 等只读调用免确认' },
  { value: 'credential_first', label: '凭据引用前', description: '首次引用 API Key 时确认,后续免确认' },
];

export function ToolRiskPanel({
  risk, needConfirm, onRiskChange, onNeedConfirmChange, config, onConfigChange, granularity, onGranularityChange,
}: {
  risk: RiskLevel;
  needConfirm: boolean;
  onRiskChange: (v: RiskLevel) => void;
  onNeedConfirmChange: (v: boolean) => void;
  config: ToolConfig;
  onConfigChange: (next: ToolConfig) => void;
  granularity: ToolConfirmGranularity;
  onGranularityChange: (v: ToolConfirmGranularity) => void;
}) {
  const updateConfig = (patch: Partial<ToolConfig>) => onConfigChange({ ...config, ...patch });
  return (
    <div className="space-y-5">
      <RiskLevelPicker value={risk} onChange={onRiskChange} />
      <div>
        <FieldLabel hint="基于 HTTP method 推断写操作">确认粒度</FieldLabel>
        <div className="mt-1 space-y-1.5">
          {CONFIRM_OPTIONS.map((opt) => {
            const active = opt.value === granularity;
            return (
              <button
                key={opt.value}
                type="button"
                onClick={() => onGranularityChange(opt.value)}
                aria-pressed={active}
                className={`flex w-full items-start gap-2 rounded-xl border p-3 text-left text-xs transition ${
                  active ? 'border-[var(--brand)] bg-[var(--brand-light)]' : 'border-[var(--border)] hover:border-[var(--brand)]'
                }`}
              >
                <span className={`mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full border-2 ${active ? 'border-[var(--brand)]' : 'border-[var(--border)]'}`}>
                  {active && <span className="h-1.5 w-1.5 rounded-full bg-[var(--brand)]" />}
                </span>
                <div>
                  <p className={`font-semibold ${active ? 'text-[var(--brand)]' : 'text-[var(--text-secondary)]'}`}>{opt.label}</p>
                  <p className="mt-0.5 text-[10px] leading-4 text-[var(--text-muted)]">{opt.description}</p>
                </div>
              </button>
            );
          })}
        </div>
      </div>
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] p-4">
        <div className="flex items-center justify-between">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">出站白名单 (复述)</p>
          <button
            type="button"
            onClick={() => updateConfig({ networkPolicy: config.allowedHosts.length > 0 ? 'allowlist' : 'none' })}
            className="text-[10px] text-[var(--brand)] hover:underline"
          >
            重置
          </button>
        </div>
        {config.allowedHosts.length === 0 ? (
          <p className="mt-2 text-[11px] text-amber-700">⚠ 未配置白名单;Tool 调用将完全禁止出站(可能调用失败)。</p>
        ) : (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {config.allowedHosts.map((h) => (
              <span key={h} className="inline-flex items-center gap-1 rounded-full bg-white px-2 py-0.5 text-[11px] font-mono">{h}</span>
            ))}
          </div>
        )}
      </div>
      <NeedConfirmSwitch value={needConfirm} onChange={onNeedConfirmChange} hint="Tool 调用前的总开关(确认粒度生效前提)。" />
    </div>
  );
}

// ─── MCP · Step 3 (探活 + token 轮换 + 连接超时) ────────────────────────

export function MCPRiskPanel({
  risk, needConfirm, onRiskChange, onNeedConfirmChange, config, onConfigChange,
}: {
  risk: RiskLevel;
  needConfirm: boolean;
  onRiskChange: (v: RiskLevel) => void;
  onNeedConfirmChange: (v: boolean) => void;
  config: MCPConfig;
  onConfigChange: (next: MCPConfig) => void;
}) {
  const updateConfig = (patch: Partial<MCPConfig>) => onConfigChange({ ...config, ...patch });
  return (
    <div className="space-y-5">
      <RiskLevelPicker value={risk} onChange={onRiskChange} />
      <div className="grid gap-3 sm:grid-cols-3">
        <div>
          <FieldLabel hint="后台定时探测 server 健康">探活间隔 (s)</FieldLabel>
          <div className="relative">
            <Clock className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--text-muted)]" />
            <input
              type="number"
              min={30}
              max={86400}
              value={config.probeIntervalS}
              onChange={(e) => updateConfig({ probeIntervalS: Number(e.target.value) })}
              className="h-10 w-full rounded-xl border border-[var(--border-strong)] bg-white pl-8 pr-3 text-xs outline-none focus:border-[var(--brand)]"
            />
          </div>
        </div>
        <div>
          <FieldLabel hint="server 握手 / 调用的硬超时">连接超时 (s)</FieldLabel>
          <div className="relative">
            <Network className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--text-muted)]" />
            <input
              type="number"
              min={1}
              max={120}
              value={config.connectionTimeoutS}
              onChange={(e) => updateConfig({ connectionTimeoutS: Number(e.target.value) })}
              className="h-10 w-full rounded-xl border border-[var(--border-strong)] bg-white pl-8 pr-3 text-xs outline-none focus:border-[var(--brand)]"
            />
          </div>
        </div>
        <div>
          <FieldLabel hint="凭据超过 N 天强制轮换">Token 轮换 (天)</FieldLabel>
          <div className="relative">
            <RefreshCw className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--text-muted)]" />
            <input
              type="number"
              min={0}
              max={365}
              value={config.tokenRotationDays}
              onChange={(e) => updateConfig({ tokenRotationDays: Number(e.target.value) })}
              className="h-10 w-full rounded-xl border border-[var(--border-strong)] bg-white pl-8 pr-3 text-xs outline-none focus:border-[var(--brand)]"
            />
          </div>
        </div>
      </div>
      <NeedConfirmSwitch value={needNeedConfirmValue(config, needConfirm)} onChange={onNeedConfirmChange} hint="MCP 调用前用户需授权(token 已脱敏,平台侧加密存储)。" />
    </div>
  );
}

function needNeedConfirmValue(_config: MCPConfig, fallback: boolean) {
  // 留作扩展点:可以根据 server 能力列表是否包含写操作类工具自动建议
  return fallback;
}
