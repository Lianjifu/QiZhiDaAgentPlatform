import { Download, Send } from 'lucide-react';
import { useEffect, useState } from 'react';
import { CenterModal } from '@/components/feedback/CenterModal';
import type { ExchangeFormat } from '../schema';
import { EXCHANGE_FORMATS } from './constants';
import { StepIndicator } from './Primitives';

export function ImportBudgetModal({ open, onClose, onImport }: {
  open: boolean;
  onClose: () => void;
  onImport: (count: number, content: string, format: ExchangeFormat) => void;
}) {
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
    } else if (format === 'yaml') {
      setParsedCount(text.split(/\n-\s/).filter((s) => s.trim().length > 0).length);
    } else {
      setParsedCount(text.split('\n').filter((s) => s.trim().length > 0 && !s.startsWith('name')).length);
    }
    setStep(2);
  };
  return (
    <CenterModal
      open={open}
      onClose={onClose}
      ariaLabel="导入预算"
      panelClassName="max-w-2xl"
      title={<span className="flex items-center gap-2"><Send className="h-5 w-5 text-[var(--brand)]" />导入预算</span>}
      description={step === 1 ? '选择 JSON / YAML / CSV 文件' : '确认条目并导入'}
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
              {EXCHANGE_FORMATS.map((f) => (
                <button key={f} type="button" onClick={() => setFormat(f)} aria-pressed={format === f} className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-semibold transition ${format === f ? 'border-[var(--brand)] bg-[var(--brand-light)] text-[var(--brand)]' : 'border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--brand)]'}`}>
                  {f.toUpperCase()}
                </button>
              ))}
            </div>
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={10} placeholder="粘贴 JSON / YAML / CSV 内容..." className="w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 py-2 font-mono text-[11px] leading-6 outline-none focus:border-[var(--brand)]" />
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

export function ExportBudgetModal({ open, onClose, onExport, total, selectedCount }: {
  open: boolean;
  onClose: () => void;
  onExport: (format: ExchangeFormat) => void;
  total: number;
  selectedCount: number;
}) {
  const [format, setFormat] = useState<ExchangeFormat>('json');
  useEffect(() => { if (open) setFormat('json'); }, [open]);
  return (
    <CenterModal
      open={open}
      onClose={onClose}
      ariaLabel="导出预算"
      panelClassName="max-w-md"
      title={<span className="flex items-center gap-2"><Download className="h-5 w-5 text-[var(--brand)]" />导出预算</span>}
      description={`将导出${selectedCount > 0 ? `已选的 ${selectedCount} 条` : `全部 ${total} 条`}预算。`}
      footer={
        <>
          <button type="button" onClick={onClose} className="rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold">取消</button>
          <button type="button" onClick={() => { onExport(format); onClose(); }} className="rounded-xl bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white">开始导出</button>
        </>
      }
    >
      <div className="mt-4 grid gap-2 sm:grid-cols-3">
        {EXCHANGE_FORMATS.map((f) => (
          <button key={f} type="button" onClick={() => setFormat(f)} aria-pressed={format === f} className={`rounded-xl border p-3 text-xs font-semibold transition ${format === f ? 'border-[var(--brand)] bg-[var(--brand-light)]/40' : 'border-[var(--border)] hover:border-[var(--brand)]'}`}>{f.toUpperCase()}</button>
        ))}
      </div>
    </CenterModal>
  );
}
