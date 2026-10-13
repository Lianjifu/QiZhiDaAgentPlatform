/**
 * Step 2 子组件 — 3 个 type 各自的核心配置表单。
 *
 * - StepSkillIO   : Skill 走沙箱,Step 2 仍是手写 input/output JSON。
 * - StepToolEndpoint : Tool 走 HTTP,Step 2 收集鉴权 + 端点 + 出站白名单。
 * - StepMCPServer : MCP 走 MCP 协议,Step 2 收集传输 + 服务器 + 鉴权 + 工具勾选。
 *
 * 三个组件都接受 onChange 回调,父级 wizard 持有草稿状态。
 * 真实模式 (Phase 2) 接入后端 admin_tool_credentials / admin_mcp_servers;
 * 此刻后端忽略 profile,本地草稿在前端 state 即可,提交时随 CreateSkillVars 上传。
 */
import { useEffect, useMemo, useState } from 'react';
import { Check, Copy, Database, ExternalLink, Globe, KeyRound, Loader2, Network, Plus, Terminal, Trash2, X } from 'lucide-react';
import type {
  MCPToolInfo, MCPTransport, RiskLevel, SchemaField, ToolAuthKind, ToolConfig, ToolSourceKind, MCPConfig,
} from '../schema';
import { RISK_BADGE, TYPE_META } from './constants';

// ─── 共享小组件 ────────────────────────────────────────────────────────

export function FieldLabel({ children, hint }: { children: React.ReactNode; hint?: string }) {
  return (
    <div className="mb-1.5 flex items-center justify-between">
      <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">{children}</label>
      {hint && <span className="text-[10px] text-[var(--text-muted)]">{hint}</span>}
    </div>
  );
}

function RadioGroup<T extends string>({
  options, value, onChange, disabled = false,
}: {
  options: Array<{ value: T; label: string; description?: string; icon?: React.ComponentType<{ className?: string }> }>;
  value: T;
  onChange: (v: T) => void;
  disabled?: boolean;
}) {
  return (
    <div className={`grid gap-2 ${options.length > 3 ? 'sm:grid-cols-3' : 'sm:grid-cols-2'}`}>
      {options.map((opt) => {
        const active = opt.value === value;
        const Icon = opt.icon;
        return (
          <button
            key={opt.value}
            type="button"
            disabled={disabled}
            onClick={() => onChange(opt.value)}
            aria-pressed={active}
            className={`flex items-start gap-2 rounded-xl border p-3 text-left transition ${
              active ? 'border-[var(--brand)] bg-[var(--brand-light)]' : 'border-[var(--border)] hover:border-[var(--brand)]'
            } disabled:cursor-not-allowed disabled:opacity-50`}
          >
            {Icon && <Icon className={`mt-0.5 h-4 w-4 ${active ? 'text-[var(--brand)]' : 'text-[var(--text-muted)]'}`} />}
            <div>
              <p className={`text-xs font-semibold ${active ? 'text-[var(--brand)]' : 'text-[var(--text-secondary)]'}`}>{opt.label}</p>
              {opt.description && <p className="mt-0.5 text-[10px] leading-4 text-[var(--text-muted)]">{opt.description}</p>}
            </div>
          </button>
        );
      })}
    </div>
  );
}

function SchemaList({ fields }: { fields: SchemaField[] }) {
  if (fields.length === 0) return <p className="text-[11px] text-[var(--text-muted)]">暂无字段。可在上方填写后点击解析自动生成。</p>;
  return (
    <ul className="space-y-1 text-[11px]">
      {fields.slice(0, 4).map((f) => (
        <li key={f.name} className="flex items-center gap-1.5">
          <span className="font-mono text-[var(--brand)]">{f.name}</span>
          <span className="text-[var(--text-muted)]">:{f.type}</span>
          {f.required && <span className="text-rose-500">*</span>}
          {f.description && <span className="truncate text-[var(--text-muted)]">— {f.description}</span>}
        </li>
      ))}
      {fields.length > 4 && <li className="text-[var(--text-muted)]">…等 {fields.length - 4} 项</li>}
    </ul>
  );
}

// ─── Skill · Step 2 (输入输出 JSON,沿用旧实现) ────────────────────────

export function StepSkillIO({
  inputJson, outputJson, onInputChange, onOutputChange,
}: {
  inputJson: string;
  outputJson: string;
  onInputChange: (v: string) => void;
  onOutputChange: (v: string) => void;
}) {
  const canNext = useMemo(() => {
    try { JSON.parse(inputJson); JSON.parse(outputJson); return true; } catch { return false; }
  }, [inputJson, outputJson]);
  return (
    <div className="space-y-4">
      <div>
        <FieldLabel hint="沙箱内可用的入参">输入参数 (JSON 数组)</FieldLabel>
        <textarea
          value={inputJson}
          onChange={(e) => onInputChange(e.target.value)}
          rows={6}
          className="w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 py-2 font-mono text-xs leading-6 outline-none focus:border-[var(--brand)]"
        />
        {!canNext && <p className="mt-1 text-[11px] text-rose-600">JSON 格式无效,请检查括号或逗号。</p>}
      </div>
      <div>
        <FieldLabel hint="Skill 执行后返回的字段">输出参数 (JSON 数组)</FieldLabel>
        <textarea
          value={outputJson}
          onChange={(e) => onOutputChange(e.target.value)}
          rows={6}
          className="w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 py-2 font-mono text-xs leading-6 outline-none focus:border-[var(--brand)]"
        />
      </div>
      <p className="text-[11px] text-[var(--text-muted)]">每个字段:name · type (string/number/boolean/object/array) · required · description。</p>
    </div>
  );
}

// ─── Tool · Step 2 (鉴权 + 端点 + 出站白名单) ──────────────────────────

export function StepToolEndpoint({
  config, onChange,
}: {
  config: ToolConfig;
  onChange: (next: ToolConfig) => void;
}) {
  const update = (patch: Partial<ToolConfig>) => onChange({ ...config, ...patch });
  const authOptions: Array<{ value: ToolAuthKind; label: string; description: string; icon: React.ComponentType<{ className?: string }> }> = [
    { value: 'api_key', label: 'API Key', description: '在 Header / Query 中传 key', icon: KeyRound },
    { value: 'bearer', label: 'Bearer', description: 'Authorization: Bearer <token>', icon: KeyRound },
    { value: 'oauth2', label: 'OAuth 2.0', description: '客户端凭据或授权码', icon: KeyRound },
  ];
  const sourceOptions: Array<{ value: ToolSourceKind; label: string; description: string; icon: React.ComponentType<{ className?: string }> }> = [
    { value: 'http_endpoint', label: '自定义端点', description: '手动填写 baseUrl + path + method', icon: Network },
    { value: 'openapi_url', label: 'OpenAPI URL', description: '粘贴规范地址,自动解析', icon: ExternalLink },
    { value: 'openapi_inline', label: 'OpenAPI 内联', description: '粘贴 OpenAPI JSON 文本', icon: Database },
  ];
  return (
    <div className="space-y-5">
      <section>
        <FieldLabel hint="Tool 调用外部 API 时的鉴权">鉴权方式</FieldLabel>
        <RadioGroup value={config.authKind} onChange={(v) => update({ authKind: v })} options={authOptions} />
        <input
          type="password"
          value={config.apiKey ?? ''}
          onChange={(e) => update({ apiKey: e.target.value })}
          placeholder={config.authKind === 'oauth2' ? '粘贴 access_token 或填写 client_id:client_secret' : '粘贴 API Key,提交后自动加密存储'}
          className="mt-3 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 font-mono text-xs outline-none focus:border-[var(--brand)]"
        />
      </section>

      <section>
        <FieldLabel>调用源</FieldLabel>
        <RadioGroup value={config.sourceKind} onChange={(v) => update({ sourceKind: v })} options={sourceOptions} />
        {config.sourceKind === 'http_endpoint' && (
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            <div className="sm:col-span-2">
              <FieldLabel>Base URL</FieldLabel>
              <input
                value={config.baseUrl}
                onChange={(e) => update({ baseUrl: e.target.value })}
                placeholder="https://api.example.com"
                className="h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 font-mono text-xs outline-none focus:border-[var(--brand)]"
              />
            </div>
            <div>
              <FieldLabel>Method</FieldLabel>
              <select
                value={config.httpMethod}
                onChange={(e) => update({ httpMethod: e.target.value as ToolConfig['httpMethod'] })}
                className="h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-xs outline-none"
              >
                {(['GET', 'POST', 'PUT', 'PATCH', 'DELETE'] as const).map((m) => <option key={m}>{m}</option>)}
              </select>
            </div>
            <div className="sm:col-span-3">
              <FieldLabel>Path</FieldLabel>
              <input
                value={config.endpointPath}
                onChange={(e) => update({ endpointPath: e.target.value })}
                placeholder="/v1/chat/completions"
                className="h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 font-mono text-xs outline-none focus:border-[var(--brand)]"
              />
            </div>
          </div>
        )}
        {config.sourceKind === 'openapi_url' && (
          <div className="mt-3 space-y-3">
            <div>
              <FieldLabel>OpenAPI 文档 URL</FieldLabel>
              <input
                value={config.baseUrl}
                onChange={(e) => update({ baseUrl: e.target.value })}
                placeholder="https://api.example.com/openapi.json"
                className="h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 font-mono text-xs outline-none focus:border-[var(--brand)]"
              />
            </div>
            <button type="button" disabled className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] px-3 py-1.5 text-[11px] text-[var(--text-muted)]">
              <Loader2 className="h-3 w-3" />解析(Phase 2 接通 OpenAPI 客户端后启用)
            </button>
          </div>
        )}
        {config.sourceKind === 'openapi_inline' && (
          <div className="mt-3">
            <FieldLabel>OpenAPI JSON 文本</FieldLabel>
            <textarea
              rows={4}
              placeholder='{"openapi":"3.1.0","paths":{...}}'
              className="w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 py-2 font-mono text-[10px] leading-5 outline-none focus:border-[var(--brand)]"
            />
          </div>
        )}
      </section>

      <section className="grid gap-3 sm:grid-cols-2">
        <div>
          <FieldLabel hint="主机域名;空 = 仅允许 baseUrl 域名">出站白名单</FieldLabel>
          <HostTagList
            hosts={config.allowedHosts}
            onChange={(hosts) => update({ allowedHosts: hosts, networkPolicy: hosts.length > 0 ? 'allowlist' : 'none' })}
          />
        </div>
        <div>
          <FieldLabel hint="单次 HTTP 调用总超时">超时 (ms)</FieldLabel>
          <input
            type="number"
            min={1000}
            max={120000}
            value={config.timeoutMs}
            onChange={(e) => update({ timeoutMs: Number(e.target.value) })}
            className="h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-xs outline-none focus:border-[var(--brand)]"
          />
        </div>
      </section>
    </div>
  );
}

function HostTagList({ hosts, onChange }: { hosts: string[]; onChange: (h: string[]) => void }) {
  const [draft, setDraft] = useState('');
  const add = () => {
    const value = draft.trim();
    if (!value || hosts.includes(value)) return;
    onChange([...hosts, value]);
    setDraft('');
  };
  return (
    <div className="rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] p-2">
      <div className="flex flex-wrap gap-1.5">
        {hosts.length === 0 && <span className="px-1 py-1 text-[11px] text-[var(--text-muted)]">尚未添加主机</span>}
        {hosts.map((h) => (
          <span key={h} className="inline-flex items-center gap-1 rounded-full bg-white px-2 py-0.5 text-[11px] font-mono">
            {h}
            <button type="button" onClick={() => onChange(hosts.filter((x) => x !== h))} className="text-[var(--text-muted)] hover:text-rose-600">
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
      </div>
      <div className="mt-2 flex gap-1.5">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add(); } }}
          placeholder="api.openai.com"
          className="h-8 flex-1 rounded-lg border border-[var(--border)] bg-white px-2 font-mono text-[11px] outline-none focus:border-[var(--brand)]"
        />
        <button type="button" onClick={add} className="inline-flex items-center gap-1 rounded-lg border border-[var(--brand)] bg-[var(--brand-light)] px-2 text-[11px] text-[var(--brand)]">
          <Plus className="h-3 w-3" />添加
        </button>
      </div>
    </div>
  );
}

// ─── MCP · Step 2 (传输 + 服务器 + 鉴权 + 工具勾选) ────────────────────

export function StepMCPServer({
  config, onChange, tools, onProbe, probing, probeError,
}: {
  config: MCPConfig;
  onChange: (next: MCPConfig) => void;
  tools: MCPToolInfo[];
  onProbe: () => void;
  probing: boolean;
  probeError: string | null;
}) {
  const update = (patch: Partial<MCPConfig>) => onChange({ ...config, ...patch });
  const transportOptions: Array<{ value: MCPTransport; label: string; description: string; icon: React.ComponentType<{ className?: string }> }> = [
    { value: 'streamable-http', label: 'Streamable HTTP', description: '2025 规范,推荐', icon: Globe },
    { value: 'sse', label: 'SSE', description: 'Server-Sent Events', icon: Network },
    { value: 'stdio', label: 'stdio', description: '本地子进程', icon: Terminal },
  ];
  const toggleTool = (name: string) => {
    const next = config.selectedTools.includes(name)
      ? config.selectedTools.filter((n) => n !== name)
      : [...config.selectedTools, name];
    update({ selectedTools: next });
  };
  return (
    <div className="space-y-5">
      <section>
        <FieldLabel>传输方式</FieldLabel>
        <RadioGroup value={config.transport} onChange={(v) => update({ transport: v })} options={transportOptions} />
      </section>

      {config.transport === 'stdio' ? (
        <section className="space-y-3">
          <div>
            <FieldLabel>启动命令</FieldLabel>
            <input
              value={config.command}
              onChange={(e) => update({ command: e.target.value })}
              placeholder="例如:npx -y @modelcontextprotocol/server-github"
              className="h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 font-mono text-xs outline-none focus:border-[var(--brand)]"
            />
          </div>
          <div>
            <FieldLabel hint="每行一个,会在保存时按行拆分">参数 (rows)</FieldLabel>
            <textarea
              rows={3}
              value={config.args.join('\n')}
              onChange={(e) => update({ args: e.target.value.split('\n').map((s) => s.trim()).filter(Boolean) })}
              className="w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 py-2 font-mono text-xs leading-5 outline-none focus:border-[var(--brand)]"
            />
          </div>
          <div>
            <FieldLabel hint="KEY=VALUE,每行一个">环境变量 (rows)</FieldLabel>
            <textarea
              rows={3}
              value={Object.entries(config.env).map(([k, v]) => `${k}=${v}`).join('\n')}
              onChange={(e) => {
                const env: Record<string, string> = {};
                e.target.value.split('\n').forEach((line) => {
                  const idx = line.indexOf('=');
                  if (idx > 0) env[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
                });
                update({ env });
              }}
              className="w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 py-2 font-mono text-xs leading-5 outline-none focus:border-[var(--brand)]"
            />
          </div>
        </section>
      ) : (
        <section className="space-y-3">
          <div>
            <FieldLabel hint="例如:https://mcp.example.com/sse">Server URL</FieldLabel>
            <input
              value={config.serverUrl}
              onChange={(e) => update({ serverUrl: e.target.value })}
              placeholder={config.transport === 'sse' ? 'https://mcp.example.com/sse' : 'https://mcp.example.com/mcp'}
              className="h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 font-mono text-xs outline-none focus:border-[var(--brand)]"
            />
          </div>
          <div>
            <FieldLabel hint="可空;填了会随创建一并加密存储">鉴权 Token</FieldLabel>
            <input
              type="password"
              value={config.token ?? ''}
              onChange={(e) => update({ token: e.target.value })}
              placeholder="Bearer / OAuth token / API Key"
              className="h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 font-mono text-xs outline-none focus:border-[var(--brand)]"
            />
          </div>
        </section>
      )}

      <section>
        <div className="mb-2 flex items-center justify-between">
          <FieldLabel hint="点击探测会调用 server 的 tools/list">能力发现</FieldLabel>
          <button
            type="button"
            onClick={onProbe}
            disabled={probing || !canProbe(config)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--brand)] bg-[var(--brand-light)] px-3 py-1.5 text-[11px] font-semibold text-[var(--brand)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {probing ? <Loader2 className="h-3 w-3 animate-spin" /> : <Network className="h-3 w-3" />}
            {probing ? '探测中…' : '测试连接 & 拉取工具'}
          </button>
        </div>
        {probeError && (
          <p className="mb-2 rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-[11px] text-rose-700">{probeError}</p>
        )}
        {tools.length === 0 ? (
          <p className="rounded-lg border border-dashed border-[var(--border)] px-3 py-4 text-center text-[11px] text-[var(--text-muted)]">
            尚未探测,或 server 未返回任何工具。
          </p>
        ) : (
          <ul className="space-y-1.5">
            {tools.map((t) => {
              const checked = config.selectedTools.includes(t.name);
              return (
                <li key={t.name}>
                  <button
                    type="button"
                    onClick={() => toggleTool(t.name)}
                    aria-pressed={checked}
                    className={`flex w-full items-start gap-2 rounded-xl border p-2.5 text-left text-xs transition ${
                      checked ? 'border-[var(--brand)] bg-[var(--brand-light)]' : 'border-[var(--border)] hover:border-[var(--brand)]'
                    }`}
                  >
                    <span className={`mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded border ${checked ? 'border-[var(--brand)] bg-[var(--brand)] text-white' : 'border-[var(--border)] bg-white'}`}>
                      {checked && <Check className="h-3 w-3" />}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="font-mono text-[11px] font-semibold">{t.name}</p>
                      <p className="mt-0.5 line-clamp-2 text-[10px] text-[var(--text-muted)]">{t.description || '(无描述)'}</p>
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}

function canProbe(c: MCPConfig): boolean {
  if (c.transport === 'stdio') return c.command.trim().length > 0;
  return c.serverUrl.trim().length > 0;
}

// ─── 通用输入输出 schema 摘要(展示从 profile 推导出的字段) ────────────────

export function ProfileSchemaSummary({ label, fields }: { label: string; fields: SchemaField[] }) {
  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">{label}</p>
      <div className="mt-2">
        <SchemaList fields={fields} />
      </div>
    </div>
  );
}
