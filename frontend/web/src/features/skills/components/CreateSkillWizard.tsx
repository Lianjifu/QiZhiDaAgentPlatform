/**
 * 3 步新建 wizard — Skill / Tool / MCP 三类型差异化。
 *
 * - Step 1 通用:名称、负责人、描述(类型锁定,顶部 type 指示)
 * - Step 2 类型专属:Skill=输入输出 JSON / Tool=鉴权+端点+出站 / MCP=传输+服务器+能力
 * - Step 3 类型专属:Skill=沙箱+风险 / Tool=确认粒度+白名单 / MCP=探活+轮换+连接
 *
 * 提交时携带类型专属 profile;后端目前忽略,Phase 2 接入持久化。
 */
import { useEffect, useMemo, useState } from 'react';
import { BookOpen, Layers, ShieldCheck, Plus, Sparkles, Wrench, Network } from 'lucide-react';
import { useApiMutation } from '@/services/query';
import { normalizeError } from '@/api/shared/http-error';
import { CenterModal } from '@/components/feedback/CenterModal';
import type {
  MCPConfig, MCPToolInfo, RiskLevel, Skill, SkillProfile, SkillType, SchemaField, ToolConfig,
} from '../schema';
import { DEFAULT_MCP_CONFIG, DEFAULT_SKILL_RUNTIME, DEFAULT_TOOL_CONFIG } from '../schema';
import { TYPE_META } from './constants';
import { StepIndicator } from './StepIndicator';
import { buildSkillFromDraft, parseSchemaJson } from './skill-io';
import { StepSkillIO, StepToolEndpoint, StepMCPServer } from './CreateStepConfigs';
import {
  SkillRiskPanel, ToolRiskPanel, MCPRiskPanel, type ToolConfirmGranularity,
} from './CreateStepRisks';

interface CreateWizardProps {
  open: boolean;
  onClose: () => void;
  onCreate: (skill: Skill) => void;
  type: SkillType;
  lockType?: boolean;
  embedded?: boolean;
}

const STEP_LABELS: Record<SkillType, { step2: string; step3: string }> = {
  Skill: { step2: '输入输出', step3: '沙箱与风险' },
  Tool:  { step2: '鉴权与端点', step3: '出站与风险' },
  MCP:   { step2: '服务器与凭据', step3: '连接与风险' },
};

const DEFAULT_TOOL_GRANULARITY: ToolConfirmGranularity = 'always';
const DEFAULT_SANDBOX = {
  image: DEFAULT_SKILL_RUNTIME.image,
  entry: DEFAULT_SKILL_RUNTIME.entry,
  source: DEFAULT_SKILL_RUNTIME.source,
  timeoutMs: DEFAULT_SKILL_RUNTIME.timeoutMs,
  network: DEFAULT_SKILL_RUNTIME.network,
  memoryMb: DEFAULT_SKILL_RUNTIME.memoryMb,
} as const;

export function CreateSkillWizard({ open, onClose, onCreate, type: lockedType, lockType = true, embedded = false }: CreateWizardProps) {
  const [step, setStep] = useState(1);
  const [pickedType, setPickedType] = useState<SkillType>(lockedType);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [owner, setOwner] = useState('张敏');
  const [risk, setRisk] = useState<RiskLevel>('low');
  const [needConfirm, setNeedConfirm] = useState(false);

  // Skill 专属
  const [inputJson, setInputJson] = useState('[{ "name": "input", "type": "string", "required": true, "description": "示例输入" }]');
  const [outputJson, setOutputJson] = useState('[{ "name": "result", "type": "string", "required": true, "description": "示例输出" }]');
  const [skillSource, setSkillSource] = useState(
    'import json, sys\n' +
    'raw = sys.stdin.read() or "{}"\n' +
    'args = json.loads(raw) if raw.strip().startswith("{") else {}\n' +
    'doc = args.get("document", "")\n' +
    'lines = [l for l in doc.splitlines() if l.strip()]\n' +
    'print(json.dumps({\n' +
    '  "summary": (" ".join(lines))[:int(args.get("maxSummary", 500))],\n' +
    '  "keyPoints": lines[:5],\n' +
    '  "actions": []\n' +
    '}, ensure_ascii=False))\n'
  );

  // Tool 专属
  const [toolConfig, setToolConfig] = useState<ToolConfig>(DEFAULT_TOOL_CONFIG);
  const [toolGranularity, setToolGranularity] = useState<ToolConfirmGranularity>(DEFAULT_TOOL_GRANULARITY);

  // MCP 专属
  const [mcpConfig, setMcpConfig] = useState<MCPConfig>(DEFAULT_MCP_CONFIG);
  const [mcpTools, setMcpTools] = useState<MCPToolInfo[]>([]);
  const [probing, setProbing] = useState(false);
  const [probeError, setProbeError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setStep(1);
      setPickedType(lockedType);
      setName('');
      setDescription('');
      setOwner('张敏');
      setRisk('low');
      setNeedConfirm(false);
      setInputJson('[{ "name": "input", "type": "string", "required": true, "description": "示例输入" }]');
      setOutputJson('[{ "name": "result", "type": "string", "required": true, "description": "示例输出" }]');
      setSkillSource(`import json, sys
raw = sys.stdin.read() or "{}"
args = json.loads(raw) if raw.strip().startswith("{") else {}
doc = args.get("document", "")
lines = [l for l in doc.splitlines() if l.strip()]
print(json.dumps({
  "summary": (" ".join(lines))[:int(args.get("maxSummary", 500))],
  "keyPoints": lines[:5],
  "actions": []
}, ensure_ascii=False))`);
      setToolConfig(DEFAULT_TOOL_CONFIG);
      setToolGranularity(DEFAULT_TOOL_GRANULARITY);
      setMcpConfig(DEFAULT_MCP_CONFIG);
      setMcpTools([]);
      setProbing(false);
      setProbeError(null);
    }
  }, [open, lockedType]);

  const type = lockType ? lockedType : pickedType;
  const labels = STEP_LABELS[type];

  // canNext per step
  const canNext1 = name.trim().length > 0;
  const canNext2 = useMemo(() => {
    if (type === 'Skill') {
      try { JSON.parse(inputJson); JSON.parse(outputJson); return true; } catch { return false; }
    }
    if (type === 'Tool') {
      if (!toolConfig.baseUrl.trim()) return false;
      if (toolConfig.sourceKind === 'http_endpoint' && !toolConfig.endpointPath.trim()) return false;
      return true;
    }
    if (type === 'MCP') {
      if (mcpConfig.transport === 'stdio') return mcpConfig.command.trim().length > 0;
      return mcpConfig.serverUrl.trim().length > 0;
    }
    return false;
  }, [type, inputJson, outputJson, toolConfig, mcpConfig]);

  const probe = useApiMutation<{ tools: MCPToolInfo[] }, MCPConfig>('/api/admin/skills/mcp/probe');

  // 演示环境和开发环境一样请求后端 —— 演示环境连的是 demo 后端实例,
  // 它有真的 /api/admin/skills/mcp/probe. 以前这里在演示模式下**本地模拟**
  // 一份假的 MCP 工具列表, 那正是"演示数据与真实 API 各写各的"的又一处.
  const probeMcp = async () => {
    setProbing(true);
    setProbeError(null);
    setMcpTools([]);
    try {
      const result = await probe.mutateAsync(mcpConfig);
      const tools = result.tools ?? [];
      setMcpTools(tools);
      setMcpConfig((c) => ({ ...c, selectedTools: c.selectedTools.filter((n) => tools.some((t) => t.name === n)) }));
    } catch (error) {
      setProbeError(normalizeError(error).message);
    } finally {
      setProbing(false);
    }
  };

  const handleSubmit = () => {
    let inputSchema: SchemaField[] = [];
    let outputSchema: SchemaField[] = [];
    let profile: SkillProfile | undefined;

    if (type === 'Skill') {
      inputSchema = parseSchemaJson(inputJson);
      outputSchema = parseSchemaJson(outputJson);
      const baseRuntime = { ...DEFAULT_SKILL_RUNTIME, ...DEFAULT_SANDBOX, source: skillSource };
      profile = { kind: 'Skill', runtime: baseRuntime };
    } else if (type === 'Tool') {
      // Tool:从 endpoint / openapi 推断 schema(此处保留简版:用户可在 Step 2 末尾编辑)
      inputSchema = [];
      outputSchema = [];
      profile = { kind: 'Tool', ...toolConfig };
    } else {
      // MCP:从勾选的 tool 汇总 input schema(同一 server 共享一个 toolset)
      const selected = mcpTools.filter((t) => mcpConfig.selectedTools.includes(t.name));
      const collectedInputs: SchemaField[] = [];
      selected.forEach((t) => {
        t.inputSchema.forEach((f) => {
          if (!collectedInputs.some((x) => x.name === `${t.name}.${f.name}`)) {
            collectedInputs.push({ ...f, name: `${t.name}.${f.name}`, description: `[${t.name}] ${f.description}` });
          }
        });
      });
      inputSchema = collectedInputs;
      outputSchema = [];
      profile = { kind: 'MCP', ...mcpConfig };
    }

    const skill = buildSkillFromDraft(name.trim(), type, description.trim(), owner, risk, profile, inputSchema, outputSchema);
    skill.needConfirm = needConfirm || risk !== 'low';
    onCreate(skill);
  };

  const title = type === 'Tool' ? '新建 Tool' : type === 'MCP' ? '新建 MCP' : '新建技能';
  const TypeIcon = type === 'Tool' ? Wrench : type === 'MCP' ? Network : Sparkles;
  const step2Title = labels.step2;
  const step3Title = labels.step3;

  const footer = (
    <>
      {step > 1 && <button type="button" onClick={() => setStep((s) => Math.max(1, s - 1))} className="rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold">上一步</button>}
      {step < 3 && (
        <button type="button" onClick={() => setStep((s) => s + 1)} disabled={(step === 1 && !canNext1) || (step === 2 && !canNext2)} className="rounded-xl bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40">
          下一步
        </button>
      )}
      {step === 3 && (
        <button type="button" onClick={handleSubmit} className="rounded-xl bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white">
          创建技能
        </button>
      )}
    </>
  );

  const stepBody = (
    <>
      {step === 1 && (
        <div className="space-y-4">
          {lockType && (
            <div className={`flex items-center gap-2 rounded-xl border border-[var(--brand)] bg-[var(--brand-light)] px-3 py-2 text-xs ${TYPE_META[type].tone}`}>
              <TypeIcon className="h-4 w-4" />
              <span className="font-semibold">{type} · {TYPE_META[type].label}</span>
              <span className="ml-auto text-[10px] text-[var(--text-muted)]">类型已锁定</span>
            </div>
          )}
          <div>
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">技能名称</label>
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="例如:客户跟进建议" className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">负责人</label>
              <input type="text" value={owner} onChange={(e) => setOwner(e.target.value)} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
            </div>
            <div>
              <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">可见范围</label>
              <select className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none">
                <option>部门</option>
                <option>公开</option>
                <option>个人</option>
              </select>
            </div>
          </div>
          <div>
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">描述</label>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} placeholder="用一句话说清这个技能的作用" className="mt-1.5 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 py-2 text-sm outline-none focus:border-[var(--brand)]" />
          </div>
        </div>
      )}
      {step === 2 && (
        <div className="space-y-4">
          <div className={`flex items-center gap-2 rounded-xl border border-[var(--brand)] bg-[var(--brand-light)] px-3 py-2 text-xs ${TYPE_META[type].tone}`}>
            <TypeIcon className="h-4 w-4" />
            <span className="font-semibold">{type} · {step2Title}</span>
            <span className="ml-auto text-[10px] text-[var(--text-muted)]">{TYPE_META[type].description}</span>
          </div>
          {type === 'Skill' && <StepSkillIO inputJson={inputJson} outputJson={outputJson} onInputChange={setInputJson} onOutputChange={setOutputJson} />}
          {type === 'Tool' && <StepToolEndpoint config={toolConfig} onChange={setToolConfig} />}
          {type === 'MCP' && <StepMCPServer config={mcpConfig} onChange={setMcpConfig} tools={mcpTools} onProbe={probeMcp} probing={probing} probeError={probeError} />}
        </div>
      )}
      {step === 3 && (
        <div className="space-y-4">
          <div className={`flex items-center gap-2 rounded-xl border border-[var(--brand)] bg-[var(--brand-light)] px-3 py-2 text-xs ${TYPE_META[type].tone}`}>
            <TypeIcon className="h-4 w-4" />
            <span className="font-semibold">{type} · {step3Title}</span>
            <span className="ml-auto text-[10px] text-[var(--text-muted)]">创建后状态为草稿</span>
          </div>
          {type === 'Skill' && (
            <>
              <SkillRiskPanel
                risk={risk} needConfirm={needConfirm}
                onRiskChange={setRisk} onNeedConfirmChange={setNeedConfirm}
                sandbox={DEFAULT_SANDBOX} onSandboxChange={() => { /* 暂不持久化到草稿 */ }}
              />
              <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] p-5">
                <header className="mb-3 flex items-center justify-between">
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">沙箱代码</p>
                    <h4 className="mt-0.5 text-sm font-semibold">main.py</h4>
                    <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">从 stdin 读 JSON args,print 出来的内容会作为技能输出。</p>
                  </div>
                  <span className="text-[10px] text-[var(--text-muted)]">{skillSource.length} 字符</span>
                </header>
                <textarea
                  value={skillSource}
                  onChange={(event) => setSkillSource(event.target.value)}
                  rows={16}
                  spellCheck={false}
                  className="w-full rounded-xl border border-[var(--border-strong)] bg-[var(--surface-1)] p-3 font-mono text-[11px] leading-5 outline-none focus:border-[var(--brand)]"
                />
              </section>
            </>
          )}
          {type === 'Tool' && (
            <ToolRiskPanel
              risk={risk} needConfirm={needConfirm}
              onRiskChange={setRisk} onNeedConfirmChange={setNeedConfirm}
              config={toolConfig} onConfigChange={setToolConfig}
              granularity={toolGranularity} onGranularityChange={setToolGranularity}
            />
          )}
          {type === 'MCP' && (
            <MCPRiskPanel
              risk={risk} needConfirm={needConfirm}
              onRiskChange={setRisk} onNeedConfirmChange={setNeedConfirm}
              config={mcpConfig} onConfigChange={setMcpConfig}
            />
          )}
        </div>
      )}
    </>
  );

  const createSteps = [
    { index: 1, title: '基本信息', description: '名称、负责人与描述', icon: BookOpen },
    { index: 2, title: step2Title, description: STEP_DESCRIPTION[type].step2, icon: Layers },
    { index: 3, title: step3Title, description: STEP_DESCRIPTION[type].step3, icon: ShieldCheck },
  ] as const;
  const currentStep = createSteps[step - 1];

  if (embedded) {
    return (
      <section className="flex min-h-[480px] flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] lg:flex-row">
        <aside aria-label="创建步骤" className="w-full shrink-0 border-b border-[var(--border)] bg-[var(--bg-elevated)] p-4 lg:w-[260px] lg:border-b-0 lg:border-r">
          <p className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">工作区</p>
          <ol className="space-y-1">
            {createSteps.map((item) => {
              const active = step === item.index;
              const done = step > item.index;
              const Icon = item.icon;
              return (
                <li key={item.index}>
                  <button
                    type="button"
                    onClick={() => setStep(item.index)}
                    aria-current={active ? 'step' : undefined}
                    className={`flex w-full items-start gap-3 rounded-xl px-3 py-3 text-left transition ${active ? 'bg-[var(--brand-light)]' : 'hover:bg-[var(--bg-hover)]'}`}
                  >
                    <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-full border-2 ${done ? 'border-[var(--brand)] bg-[var(--brand)] text-white' : active ? 'border-[var(--brand)] bg-[var(--surface-1)] text-[var(--brand)]' : 'border-[var(--border)] bg-[var(--surface-1)] text-[var(--text-muted)]'}`}>
                      <Icon className="h-4 w-4" />
                    </span>
                    <span className="min-w-0 pt-0.5">
                      <span className={`text-[11px] font-semibold uppercase tracking-wide ${active ? 'text-[var(--brand)]' : 'text-[var(--text-muted)]'}`}>第 {item.index} 步</span>
                      <span className={`mt-0.5 block text-sm font-semibold ${active ? 'text-[var(--text)]' : 'text-[var(--text-secondary)]'}`}>{item.title}</span>
                      <span className={`mt-0.5 block text-[11px] leading-4 text-[var(--text-muted)]`}>{item.description}</span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
        </aside>
        <main className="min-w-0 flex-1 overflow-auto bg-[var(--bg-app)] p-5">
          <div className="mb-5 flex items-center justify-between border-b border-[var(--border)] pb-4">
            <h2 className="text-sm font-semibold">{currentStep?.title}</h2>
            <span className="text-[11px] font-medium tabular-nums text-[var(--text-muted)]">{step} / 3</span>
          </div>
          {stepBody}
          <div className="mt-6 flex flex-wrap justify-end gap-2 border-t border-[var(--border)] pt-4">{footer}</div>
        </main>
      </section>
    );
  }
  return (
    <CenterModal
      open={open}
      onClose={onClose}
      ariaLabel={title}
      panelClassName="max-w-3xl"
      title={<span className="flex items-center gap-2"><Plus className="h-5 w-5 text-[var(--brand)]" />{title}</span>}
      description={step === 1 ? '设置技能的基本信息' : step === 2 ? step2Title : step3Title}
      footer={footer}
    >
      <div className="mt-4 mb-5">
        <StepIndicator current={step} total={3} labels={['基本信息', step2Title, step3Title]} />
      </div>
      {stepBody}
    </CenterModal>
  );
}

const STEP_DESCRIPTION: Record<SkillType, { step2: string; step3: string }> = {
  Skill: { step2: '用 JSON 描述字段', step3: '沙箱镜像与确认粒度' },
  Tool:  { step2: '鉴权方式与调用源', step3: '出站白名单与告警' },
  MCP:   { step2: '传输协议与凭据', step3: '探活与 token 轮换' },
};
