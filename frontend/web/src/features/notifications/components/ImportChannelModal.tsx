/**
 * 导入渠道模态 — 2 步流程:
 *   1) 选择 JSON / YAML 并粘贴文本
 *   2) 预览解析出的条目数,确认导入
 * 解析只做粗略计数(JSON parse 数组长度 / YAML 按 `- ` 行数),真实后端会校验。
 */
import { useEffect, useState } from 'react';
import { Send } from 'lucide-react';
import { CenterModal } from '@/components/feedback/CenterModal';
import type { ExchangeFormat } from './constants';

interface ImportChannelModalProps {
  open: boolean;
  onClose: () => void;
  onImport: (count: number, content: string, format: ExchangeFormat) => void;
}

export function ImportChannelModal({ open, onClose, onImport }: ImportChannelModalProps) {
  const [step, setStep] = useState(1);
  const [format, setFormat] = useState<ExchangeFormat>('json');
  const [text, setText] = useState('');
  const [parsedCount, setParsedCount] = useState(0);
  useEffect(() => { if (open) { setStep(1); setFormat('json'); setText(''); setParsedCount(0); } }, [open]);
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
      ariaLabel="导入渠道"
      panelClassName="max-w-2xl"
      title={<span className="flex items-center gap-2"><Send className="h-5 w-5 text-[var(--brand)]" />导入渠道</span>}
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
        <div className="flex items-center gap-2">
          <span className={`grid h-6 w-6 place-items-center rounded-full text-[10px] font-semibold ${step >= 1 ? 'bg-[var(--brand)] text-white' : 'bg-[var(--bg-elevated)] text-[var(--text-muted)]'}`}>1</span>
          <span className="text-[11px] font-medium">选择文件</span>
          <span className={`h-px w-8 ${step > 1 ? 'bg-[var(--brand)]' : 'bg-[var(--border)]'}`} />
          <span className={`grid h-6 w-6 place-items-center rounded-full text-[10px] font-semibold ${step >= 2 ? 'bg-[var(--brand)] text-white' : 'bg-[var(--bg-elevated)] text-[var(--text-muted)]'}`}>2</span>
          <span className="text-[11px] font-medium">预览确认</span>
        </div>
        {step === 1 && (
          <>
            <div className="flex flex-wrap gap-2">
              {(['json', 'yaml'] as const).map((f) => (
                <button key={f} type="button" onClick={() => setFormat(f)} aria-pressed={format === f} className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-semibold transition ${format === f ? 'border-[var(--brand)] bg-[var(--brand-light)] text-[var(--brand)]' : 'border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--brand)]'}`}>
                  {f.toUpperCase()}
                </button>
              ))}
            </div>
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={10} placeholder="粘贴 JSON / YAML 内容..." className="w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 py-2 font-mono text-[11px] leading-6 outline-none focus:border-[var(--brand)]" />
          </>
        )}
        {step === 2 && (
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-4 text-xs">
            <p className="font-semibold">解析结果 · 共 {parsedCount} 条</p>
          </div>
        )}
      </div>
    </CenterModal>
  );
}
