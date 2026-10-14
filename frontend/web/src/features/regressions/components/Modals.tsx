/**
 * AdminRegressions — 模态框集合。
 * ImportTrackModal / ExportTrackModal / DeleteTrackModal / AlertEditModal。
 */
import { BellRing, Download, FileCode, FileJson, Mail, MessageSquare, Trash2, Upload, Webhook } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { CenterModal } from '@/components/feedback/CenterModal';
import type { AlertChannel, AlertRule, ExchangeFormat, RegressionTrack } from '../schema';
import { CHANNEL_META } from './constants';
import { StepIndicator } from './Primitives';

const channelIconMap: Record<string, typeof Mail> = {
  Mail, MessageSquare, Webhook,
};

interface ImportTrackModalProps {
  open: boolean;
  onClose: () => void;
  onImport: (count: number, content: string, format: ExchangeFormat) => void;
}

export function ImportTrackModal({ open, onClose, onImport }: ImportTrackModalProps) {
  const [step, setStep] = useState(1);
  const [format, setFormat] = useState<ExchangeFormat>('json');
  const [text, setText] = useState('');
  const [fileName, setFileName] = useState('');
  const [parsedCount, setParsedCount] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => { if (open) { setStep(1); setFormat('json'); setText(''); setFileName(''); setParsedCount(0); } }, [open]);
  const handleFile = async (file: File) => {
    setFileName(file.name);
    const ext = file.name.split('.').pop()?.toLowerCase();
    setFormat(ext === 'yaml' || ext === 'yml' ? 'yaml' : 'json');
    setText(await file.text());
  };
  const handlePreview = () => {
    if (format === 'json') {
      try {
        const arr = JSON.parse(text);
        setParsedCount(Array.isArray(arr) ? arr.length : 1);
      } catch { setParsedCount(0); }
    } else {
      setParsedCount(text.split(/\n-\s/).filter((s) => s.trim().length > 0).length);
    }
    setStep(2);
  };
  return (
    <CenterModal
      open={open}
      onClose={onClose}
      ariaLabel="导入回归追踪"
      panelClassName="max-w-2xl"
      title={<span className="flex items-center gap-2"><Upload className="h-5 w-5 text-[var(--brand)]" />导入回归追踪</span>}
      description={step === 1 ? '选择 JSON / YAML 文件' : '确认条目并导入'}
      footer={
        <>
          {step > 1 && <button type="button" onClick={() => setStep(1)} className="rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold">上一步</button>}
          {step === 1 && <button type="button" onClick={handlePreview} disabled={text.trim().length === 0} className="rounded-xl bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40">预览解析</button>}
          {step === 2 && <button type="button" onClick={() => { onImport(parsedCount, text, format); }} disabled={parsedCount === 0} className="rounded-xl bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40">导入 {parsedCount} 条</button>}
        </>
      }
    >
      <div className="mt-4 space-y-4">
        <StepIndicator current={step} total={2} labels={['选择文件', '预览确认']} />
        {step === 1 && (
          <>
            <div className="flex flex-wrap gap-2">
              {(['json', 'yaml'] as const).map((f) => (
                <button key={f} type="button" onClick={() => setFormat(f)} aria-pressed={format === f} className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-semibold transition ${format === f ? 'border-[var(--brand)] bg-[var(--brand-light)] text-[var(--brand)]' : 'border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--brand)]'}`}>
                  {f === 'json' ? <FileJson className="h-3.5 w-3.5" /> : <FileCode className="h-3.5 w-3.5" />}{f.toUpperCase()}
                </button>
              ))}
            </div>
            <div className="rounded-2xl border-2 border-dashed border-[var(--border)] p-6 text-center" onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files?.[0]; if (f) handleFile(f); }}>
              <Upload className="mx-auto h-6 w-6 text-[var(--text-muted)]" />
              <p className="mt-3 text-xs font-semibold">将文件拖到此处,或点击下方按钮选择</p>
              <p className="mt-1 text-[11px] text-[var(--text-muted)]">支持 .json / .yaml / .yml</p>
              <input ref={inputRef} type="file" accept=".json,.yaml,.yml" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }} />
              <button type="button" onClick={() => inputRef.current?.click()} className="mt-4 inline-flex items-center gap-1.5 rounded-xl border border-[var(--brand)] bg-[var(--brand-light)] px-3 py-2 text-xs font-semibold text-[var(--brand)]">选择文件</button>
              {fileName && <p className="mt-3 text-[11px] text-[var(--text-muted)]">已选择:{fileName}</p>}
            </div>
            <details className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] p-3">
              <summary className="cursor-pointer text-[11px] font-semibold text-[var(--text-muted)]">或粘贴文件内容</summary>
              <textarea value={text} onChange={(e) => setText(e.target.value)} rows={6} className="mt-2 w-full rounded-lg border border-[var(--border-strong)] bg-[var(--surface-1)] px-3 py-2 font-mono text-[11px] leading-6 outline-none focus:border-[var(--brand)]" />
            </details>
          </>
        )}
        {step === 2 && (
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-4 text-xs">
            <p className="font-semibold">解析结果 · 共 {parsedCount} 条</p>
            <p className="mt-2 text-[var(--text-muted)]">导入后将创建「稳定」状态的追踪,需重新设定基线与当前版本。</p>
          </div>
        )}
      </div>
    </CenterModal>
  );
}

interface ExportTrackModalProps {
  open: boolean;
  onClose: () => void;
  onExport: (format: ExchangeFormat) => void;
  total: number;
  selectedCount: number;
}

export function ExportTrackModal({ open, onClose, onExport, total, selectedCount }: ExportTrackModalProps) {
  const [format, setFormat] = useState<ExchangeFormat>('json');
  useEffect(() => { if (open) setFormat('json'); }, [open]);
  return (
    <CenterModal
      open={open}
      onClose={onClose}
      ariaLabel="导出回归追踪"
      panelClassName="max-w-md"
      title={<span className="flex items-center gap-2"><Download className="h-5 w-5 text-[var(--brand)]" />导出回归追踪</span>}
      description={`将导出${selectedCount > 0 ? `已选的 ${selectedCount} 条` : `全部 ${total} 条`}追踪。`}
      footer={
        <>
          <button type="button" onClick={onClose} className="rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold">取消</button>
          <button type="button" onClick={() => { onExport(format); onClose(); }} className="rounded-xl bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white">开始导出</button>
        </>
      }
    >
      <div className="mt-4 grid gap-2 sm:grid-cols-2">
        {(['json', 'yaml'] as const).map((f) => (
          <button key={f} type="button" onClick={() => setFormat(f)} aria-pressed={format === f} className={`flex items-start gap-3 rounded-xl border p-3 text-left transition ${format === f ? 'border-[var(--brand)] bg-[var(--brand-light)]/40' : 'border-[var(--border)] hover:border-[var(--brand)]'}`}>
            <span className="grid h-9 w-9 place-items-center rounded-lg bg-[var(--bg-elevated)]">{f === 'json' ? <FileJson className="h-4 w-4 text-[var(--brand)]" /> : <FileCode className="h-4 w-4 text-[var(--brand)]" />}</span>
            <div>
              <p className="text-xs font-semibold">{f.toUpperCase()}</p>
              <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">{f === 'json' ? '结构化数组' : '缩进式清单'}</p>
            </div>
          </button>
        ))}
      </div>
    </CenterModal>
  );
}

interface DeleteTrackModalProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  track: RegressionTrack | null;
}

export function DeleteTrackModal({ open, onClose, onConfirm, track }: DeleteTrackModalProps) {
  if (!track) return null;
  return (
    <CenterModal
      open={open}
      onClose={onClose}
      ariaLabel="删除追踪"
      panelClassName="max-w-md"
      title={<span className="flex items-center gap-2"><Trash2 className="h-5 w-5 text-rose-600" />删除追踪:{track.name}</span>}
      description="确认后将删除该追踪及其历史变更记录,且无法恢复。"
      footer={
        <>
          <button type="button" onClick={onClose} className="rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold">取消</button>
          <button type="button" onClick={onConfirm} className="rounded-xl bg-rose-600 px-4 py-2 text-xs font-semibold text-white">确认删除</button>
        </>
      }
    >
      <div className="mt-4 space-y-1 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-xs text-rose-900 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">
        <p>· 对象:{track.agent}</p>
        <p>· 历史变更:{track.history.length} 条</p>
        <p>· 用例数:{track.cases} 条</p>
      </div>
    </CenterModal>
  );
}

interface AlertEditModalProps {
  open: boolean;
  onClose: () => void;
  onSave: (rule: AlertRule) => void;
  rule: AlertRule | null;
}

export function AlertEditModal({ open, onClose, onSave, rule }: AlertEditModalProps) {
  const [name, setName] = useState('');
  const [metric, setMetric] = useState<AlertRule['metric']>('passRate');
  const [operator, setOperator] = useState<AlertRule['operator']>('lt');
  const [threshold, setThreshold] = useState(90);
  const [channels, setChannels] = useState<AlertChannel[]>(['email']);
  const [enabled, setEnabled] = useState(true);
  const [scope, setScope] = useState('所有追踪');
  const [description, setDescription] = useState('');
  const [cooldown, setCooldown] = useState('30 分钟');
  useEffect(() => {
    if (open && rule) {
      setName(rule.name);
      setMetric(rule.metric);
      setOperator(rule.operator);
      setThreshold(rule.threshold);
      setChannels(rule.channels);
      setEnabled(rule.enabled);
      setScope(rule.scope);
      setDescription(rule.description);
      setCooldown(rule.cooldown);
    }
  }, [open, rule]);
  if (!rule) return null;
  const handleSave = () => {
    onSave({ ...rule, name, metric, operator, threshold, channels, enabled, scope, description, cooldown });
  };
  const toggleChannel = (c: AlertChannel) => {
    setChannels((current) => current.includes(c) ? current.filter((x) => x !== c) : [...current, c]);
  };
  return (
    <CenterModal
      open={open}
      onClose={onClose}
      ariaLabel="编辑告警规则"
      panelClassName="max-w-2xl"
      title={<span className="flex items-center gap-2"><BellRing className="h-5 w-5 text-[var(--brand)]" />编辑告警规则</span>}
      description="设置规则的触发条件、阈值与通知渠道"
      footer={
        <>
          <button type="button" onClick={onClose} className="rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold">取消</button>
          <button type="button" onClick={handleSave} className="rounded-xl bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white">保存规则</button>
        </>
      }
    >
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">规则名称</label>
          <input type="text" value={name} onChange={(e) => setName(e.target.value)} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
        </div>
        <div>
          <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">触发范围</label>
          <input type="text" value={scope} onChange={(e) => setScope(e.target.value)} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
        </div>
        <div>
          <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">监控指标</label>
          <select value={metric} onChange={(e) => setMetric(e.target.value as AlertRule['metric'])} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]">
            {(['passRate', 'latency', 'cost', 'score'] as const).map((m) => <option key={m} value={m}>{m === 'passRate' ? '通过率' : m === 'latency' ? 'P95 延迟' : m === 'cost' ? '单次成本' : '平均评分'}</option>)}
          </select>
        </div>
        <div>
          <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">条件</label>
          <select value={operator} onChange={(e) => setOperator(e.target.value as AlertRule['operator'])} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]">
            {(['gt', 'lt'] as const).map((o) => <option key={o} value={o}>{o === 'gt' ? '高于' : '低于'}</option>)}
          </select>
        </div>
        <div>
          <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">阈值</label>
          <input type="number" value={threshold} onChange={(e) => setThreshold(Number(e.target.value) || 0)} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
        </div>
        <div>
          <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">冷却时间</label>
          <input type="text" value={cooldown} onChange={(e) => setCooldown(e.target.value)} placeholder="例如:30 分钟" className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
        </div>
      </div>
      <div>
        <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">通知渠道</label>
        <div className="mt-2 flex flex-wrap gap-2">
          {(['email', 'sms', 'webhook'] as const).map((c) => {
            const meta = CHANNEL_META[c];
            const Icon = channelIconMap[meta.icon] ?? Mail;
            const active = channels.includes(c);
            return (
              <button key={c} type="button" onClick={() => toggleChannel(c)} aria-pressed={active} className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition ${active ? `${meta.tone} border-current` : 'border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--brand)]'}`}>
                <Icon className="h-3.5 w-3.5" />{meta.label}
              </button>
            );
          })}
        </div>
      </div>
      <div>
        <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">规则说明</label>
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} className="mt-1.5 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 py-2 text-sm outline-none focus:border-[var(--brand)]" />
      </div>
      <div className="flex items-center justify-between rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] px-4 py-3">
        <div>
          <p className="text-xs font-semibold">启用规则</p>
          <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">停用后规则仍保留,但不会再触发告警。</p>
        </div>
        <button type="button" onClick={() => setEnabled((v) => !v)} aria-pressed={enabled} className={`relative inline-flex h-6 w-11 items-center rounded-full transition ${enabled ? 'bg-[var(--brand)]' : 'bg-[var(--bg-elevated)]'}`}>
          <span className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition ${enabled ? 'translate-x-5' : 'translate-x-1'}`} />
        </button>
      </div>
    </CenterModal>
  );
}
