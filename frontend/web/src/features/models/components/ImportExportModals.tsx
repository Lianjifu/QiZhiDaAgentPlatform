import { useEffect, useState } from 'react';
import { LineChart, Send, Trash2 } from 'lucide-react';
import { CenterModal } from '@/components/feedback/CenterModal';
import type { ExchangeFormat, Model } from '../schema';
import { EXCHANGE_FORMATS } from './constants';

interface ImportModelModalProps {
  open: boolean;
  onClose: () => void;
  onImport: (count: number, content: string, format: ExchangeFormat) => void;
}

export function ImportModelModal({ open, onClose, onImport }: ImportModelModalProps) {
  const [step, setStep] = useState(1);
  const [format, setFormat] = useState<ExchangeFormat>('json');
  const [text, setText] = useState('');
  const [parsedCount, setParsedCount] = useState(0);

  useEffect(() => {
    if (open) {
      setStep(1); setFormat('json'); setText(''); setParsedCount(0);
    }
  }, [open]);

  const handlePreview = () => {
    if (format === 'json') {
      try {
        const arr = JSON.parse(text);
        setParsedCount(Array.isArray(arr) ? arr.length : 1);
      } catch {
        setParsedCount(0);
      }
    } else {
      setParsedCount(text.split(/\n-\s/).filter((s) => s.trim().length > 0).length);
    }
    setStep(2);
  };

  return (
    <CenterModal
      open={open}
      onClose={onClose}
      ariaLabel="导入模型"
      panelClassName="max-w-2xl"
      title={<span className="flex items-center gap-2"><Send className="h-5 w-5 text-[var(--brand)]" />导入模型</span>}
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
        {step === 1 && (
          <>
            <div className="flex flex-wrap gap-2">
              {EXCHANGE_FORMATS.map((f) => (
                <button
                  key={f}
                  type="button"
                  onClick={() => setFormat(f)}
                  aria-pressed={format === f}
                  className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-semibold transition ${format === f ? 'border-[var(--brand)] bg-[var(--brand-light)] text-[var(--brand)]' : 'border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--brand)]'}`}
                >
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
            <p className="mt-2 text-[11px] text-[var(--text-muted)]">确认导入后将创建对应草稿模型,可在「模型列表」中查看。</p>
          </div>
        )}
      </div>
    </CenterModal>
  );
}

interface ExportModelModalProps {
  open: boolean;
  onClose: () => void;
  onExport: (format: ExchangeFormat) => void;
  total: number;
  selectedCount: number;
}

export function ExportModelModal({ open, onClose, onExport, total, selectedCount }: ExportModelModalProps) {
  const [format, setFormat] = useState<ExchangeFormat>('json');
  useEffect(() => { if (open) setFormat('json'); }, [open]);
  return (
    <CenterModal
      open={open}
      onClose={onClose}
      ariaLabel="导出模型"
      panelClassName="max-w-md"
      title={<span className="flex items-center gap-2"><LineChart className="h-5 w-5 text-[var(--brand)]" />导出模型</span>}
      description={`将导出${selectedCount > 0 ? `已选的 ${selectedCount} 条` : `全部 ${total} 条`}模型。`}
      footer={
        <>
          <button type="button" onClick={onClose} className="rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold">取消</button>
          <button type="button" onClick={() => { onExport(format); onClose(); }} className="rounded-xl bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white">开始导出</button>
        </>
      }
    >
      <div className="mt-4 grid gap-2 sm:grid-cols-2">
        {EXCHANGE_FORMATS.map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => setFormat(f)}
            aria-pressed={format === f}
            className={`rounded-xl border p-3 text-xs font-semibold transition ${format === f ? 'border-[var(--brand)] bg-[var(--brand-light)]/40' : 'border-[var(--border)] hover:border-[var(--brand)]'}`}
          >
            {f.toUpperCase()}
          </button>
        ))}
      </div>
    </CenterModal>
  );
}

export function DeleteModelModal({ open, onClose, onConfirm, model }: { open: boolean; onClose: () => void; onConfirm: () => void; model: Model | null }) {
  if (!model) return null;
  return (
    <CenterModal
      open={open}
      onClose={onClose}
      ariaLabel="删除模型"
      panelClassName="max-w-md"
      title={<span className="flex items-center gap-2"><Trash2 className="h-5 w-5 text-rose-600" />删除模型:{model.name}</span>}
      description="确认后将下线该模型,并从所有路由规则中移除。"
      footer={
        <>
          <button type="button" onClick={onClose} className="rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold">取消</button>
          <button type="button" onClick={onConfirm} className="rounded-xl bg-rose-600 px-4 py-2 text-xs font-semibold text-white">确认删除</button>
        </>
      }
    >
      <div className="mt-4 space-y-1 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-xs text-rose-900 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">
        <p>· 提供商:{model.providerName}</p>
        <p>· 本月调用:{model.calls.toLocaleString('zh-CN')}</p>
      </div>
    </CenterModal>
  );
}
