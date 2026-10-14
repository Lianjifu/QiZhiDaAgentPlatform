/**
 * AdminFeedback — 弹窗合集。
 * ImportFeedbackModal (2-step) / ExportFeedbackModal / DeleteFeedbackModal。
 */
import { Download, FileCode, FileJson, Trash2, Upload } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { CenterModal } from '@/components/feedback/CenterModal';
import type { ExchangeFormat, Feedback } from '../schema';
import { SENTIMENT_META } from './constants';
import { StepIndicator } from './Primitives';

interface ImportFeedbackModalProps {
  open: boolean;
  onClose: () => void;
  onImport: (count: number, content: string, format: ExchangeFormat) => void;
}

export function ImportFeedbackModal({ open, onClose, onImport }: ImportFeedbackModalProps) {
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
      ariaLabel="导入反馈"
      panelClassName="max-w-2xl"
      title={<span className="flex items-center gap-2"><Upload className="h-5 w-5 text-[var(--brand)]" />导入反馈</span>}
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
            <p className="mt-2 text-[var(--text-muted)]">导入后将以「新反馈」状态加入列表,等待分诊。</p>
          </div>
        )}
      </div>
    </CenterModal>
  );
}

interface ExportFeedbackModalProps {
  open: boolean;
  onClose: () => void;
  onExport: (format: ExchangeFormat) => void;
  total: number;
  selectedCount: number;
}

export function ExportFeedbackModal({ open, onClose, onExport, total, selectedCount }: ExportFeedbackModalProps) {
  const [format, setFormat] = useState<ExchangeFormat>('json');
  useEffect(() => { if (open) setFormat('json'); }, [open]);
  return (
    <CenterModal
      open={open}
      onClose={onClose}
      ariaLabel="导出反馈"
      panelClassName="max-w-md"
      title={<span className="flex items-center gap-2"><Download className="h-5 w-5 text-[var(--brand)]" />导出反馈</span>}
      description={`将导出${selectedCount > 0 ? `已选的 ${selectedCount} 条` : `全部 ${total} 条`}反馈。`}
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

interface DeleteFeedbackModalProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  fb: Feedback | null;
}

export function DeleteFeedbackModal({ open, onClose, onConfirm, fb }: DeleteFeedbackModalProps) {
  if (!fb) return null;
  return (
    <CenterModal
      open={open}
      onClose={onClose}
      ariaLabel="删除反馈"
      panelClassName="max-w-md"
      title={<span className="flex items-center gap-2"><Trash2 className="h-5 w-5 text-rose-600" />删除反馈:{fb.id}</span>}
      description="确认后将删除该反馈记录,且无法恢复。"
      footer={
        <>
          <button type="button" onClick={onClose} className="rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold">取消</button>
          <button type="button" onClick={onConfirm} className="rounded-xl bg-rose-600 px-4 py-2 text-xs font-semibold text-white">确认删除</button>
        </>
      }
    >
      <div className="mt-4 space-y-1 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-xs text-rose-900 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">
        <p>· 用户:{fb.user}</p>
        <p>· 主题:{fb.topic}</p>
        <p>· 情感:{SENTIMENT_META[fb.sentiment].label}</p>
      </div>
    </CenterModal>
  );
}
