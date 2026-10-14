/**
 * 导入 + 导出对话框。
 */
import { AlertTriangle, CheckCircle2, CheckSquare, ChevronLeft, ChevronRight, Download, FileJson, Info, Square, Upload } from 'lucide-react';
import { CenterModal } from '@/components/feedback/CenterModal';
import type { ImportExtension, ImportRow, ExportField, ExportFormat, ExportScope } from '../schema';
import { EXPORT_FIELDS, IMPORT_FORMATS } from './constants';
import { StepIndicator } from './Primitives';

export function ImportDialog({
  open, onClose, step, setStep, fileName, preview, extension, onLoadSample, onImportFile, onConfirm,
}: {
  open: boolean;
  onClose: () => void;
  step: 1 | 2 | 3;
  setStep: (s: 1 | 2 | 3) => void;
  fileName: string;
  preview: ImportRow[];
  extension: ImportExtension;
  onLoadSample: (ext: ImportExtension) => void;
  onImportFile: (file: File) => void;
  onConfirm: (force: boolean) => void;
}) {
  const labels = ['上传文件', '字段映射', '校验结果'];
  const okCount = preview.filter((r) => r.status === 'ok').length;
  const duplicateCount = preview.filter((r) => r.status === 'duplicate').length;
  const missingCount = preview.filter((r) => r.status === 'missing').length;

  const title = <span className="flex items-center gap-2"><Upload className="h-5 w-5 text-[var(--brand)]" />导入智能体 · {labels[step - 1]}</span>;
  const description = `第 ${step} / 3 步 · 支持 JSON / CSV / YAML / ZIP 格式的批量导入。`;

  const footer = (
    <>
      <button type="button" onClick={onClose} className="rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)]">取消</button>
      {step > 1 && (
        <button type="button" onClick={() => setStep((step - 1) as 1 | 2 | 3)} className="inline-flex items-center gap-1 rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold hover:border-[var(--brand)]">
          <ChevronLeft className="h-3.5 w-3.5" />上一步
        </button>
      )}
      {step < 3 ? (
        <button type="button" onClick={() => setStep((step + 1) as 1 | 2 | 3)} disabled={step === 1 ? !fileName : preview.length === 0} className="inline-flex items-center gap-1 rounded-xl bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white hover:bg-[var(--brand-hover)] disabled:opacity-50">
          下一步<ChevronRight className="h-3.5 w-3.5" />
        </button>
      ) : (
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => onConfirm(false)} disabled={okCount === 0} className="rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] disabled:opacity-50">跳过重复 · 导入 {okCount} 条</button>
          <button type="button" onClick={() => onConfirm(true)} disabled={okCount + duplicateCount === 0} className="inline-flex items-center gap-2 rounded-xl bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white hover:bg-[var(--brand-hover)] disabled:opacity-50">
            <Upload className="h-3.5 w-3.5" />强制导入 {okCount + duplicateCount} 条
          </button>
        </div>
      )}
    </>
  );

  return (
    <CenterModal
      open={open}
      onClose={onClose}
      ariaLabel="导入智能体"
      title={title}
      description={description}
      panelClassName="max-w-2xl"
      footer={footer}
    >
      <div className="mt-4">
        <StepIndicator current={step} total={3} labels={labels} />
      </div>

      {step === 1 && (
        <div className="mt-6 space-y-4">
          <div className="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-[var(--border)] bg-[var(--bg-elevated)] px-6 py-10 text-center">
            <FileJson className="h-8 w-8 text-[var(--brand)]" />
            <p className="mt-3 text-sm font-semibold">拖放 JSON / CSV / YAML / ZIP 文件到此</p>
            <p className="mt-1 text-[11px] text-[var(--text-muted)]">或</p>
            <label className="mt-3 inline-flex cursor-pointer items-center gap-2 rounded-xl border border-[var(--brand)] bg-[var(--brand-light)] px-4 py-2 text-xs font-semibold text-[var(--brand)] hover:opacity-80">
              <Upload className="h-4 w-4" />选择本地文件
              <input
                type="file"
                accept=".json,.csv,.yaml,.yml,.zip"
                className="hidden"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) onImportFile(file);
                  event.target.value = '';
                }}
              />
            </label>
            {fileName && (
              <p className="mt-4 inline-flex items-center gap-2 rounded-lg bg-[var(--surface-1)] px-3 py-1.5 text-[11px] text-[var(--text-muted)]">
                <FileJson className="h-3 w-3" />已选择:{fileName}
                <span className="rounded bg-[var(--brand-light)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--brand)]">{extension.toUpperCase()}</span>
              </p>
            )}
          </div>
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">或选择示例数据</p>
            <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
              {IMPORT_FORMATS.map((fmt) => {
                const active = extension === fmt.ext && fileName.startsWith('agents-sample');
                return (
                  <button
                    key={fmt.ext}
                    type="button"
                    onClick={() => onLoadSample(fmt.ext)}
                    className={`flex flex-col items-start gap-0.5 rounded-xl border px-3 py-2 text-left transition ${active ? 'border-[var(--brand)] bg-[var(--brand-light)]' : 'border-[var(--border)] hover:border-[var(--brand)]'}`}
                  >
                    <span className="text-xs font-semibold">{fmt.label}</span>
                    <span className="text-[10px] text-[var(--text-muted)]">{fmt.description}</span>
                  </button>
                );
              })}
            </div>
          </div>
          <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] p-3 text-[11px] text-[var(--text-muted)]">
            <p className="font-semibold text-[var(--text)]">支持的字段</p>
            <p className="mt-1">name · description · category · owner · tags · tools · visibleScope</p>
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="mt-6 space-y-3">
          <div className="flex items-center justify-between text-[11px] text-[var(--text-muted)]">
            <span>从 <code className="rounded bg-[var(--bg-elevated)] px-1.5 py-0.5 font-mono">{fileName}</code> 识别到 {preview.length} 条记录</span>
            <span>字段映射关系如下</span>
          </div>
          <div className="overflow-hidden rounded-xl border border-[var(--border)]">
            <table className="w-full text-xs">
              <thead className="bg-[var(--bg-elevated)] text-[var(--text-muted)]">
                <tr>
                  <th className="px-3 py-2 text-left font-semibold">文件字段</th>
                  <th className="px-3 py-2 text-left font-semibold">平台字段</th>
                  <th className="px-3 py-2 text-center font-semibold">导入</th>
                </tr>
              </thead>
              <tbody>
                {[
                  { from: 'name', to: '名称' },
                  { from: 'description', to: '描述' },
                  { from: 'category', to: '场景分类' },
                  { from: 'owner', to: '负责人' },
                  { from: 'tags', to: '标签' },
                  { from: 'tools', to: '技能' },
                  { from: 'visibleScope', to: '可见范围' },
                ].map((row) => (
                  <tr key={row.from} className="border-t border-[var(--border)]">
                    <td className="px-3 py-2 font-mono text-[var(--brand)]">{row.from}</td>
                    <td className="px-3 py-2">{row.to}</td>
                    <td className="px-3 py-2 text-center"><CheckSquare className="inline h-4 w-4 text-[var(--brand)]" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="mt-6 space-y-3">
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-xl border border-[var(--success)]/30 bg-[var(--success-bg)]/40 p-3 text-center">
              <CheckCircle2 className="mx-auto h-5 w-5 text-[var(--success)]" />
              <p className="mt-2 text-xl font-semibold tabular-nums text-[var(--success)]">{okCount}</p>
              <p className="mt-0.5 text-[10px] text-[var(--success)]/80">可正常导入</p>
            </div>
            <div className="rounded-xl border border-[var(--warning)]/30 bg-[var(--warning-bg)]/40 p-3 text-center">
              <AlertTriangle className="mx-auto h-5 w-5 text-[var(--warning)]" />
              <p className="mt-2 text-xl font-semibold tabular-nums text-[var(--warning)]">{duplicateCount}</p>
              <p className="mt-0.5 text-[10px] text-[var(--warning)]/80">重名需确认</p>
            </div>
            <div className="rounded-xl border border-[var(--danger)]/30 bg-[var(--danger-bg)]/40 p-3 text-center">
              <Info className="mx-auto h-5 w-5 text-[var(--danger)]" />
              <p className="mt-2 text-xl font-semibold tabular-nums text-[var(--danger)]">{missingCount}</p>
              <p className="mt-0.5 text-[10px] text-[var(--danger)]/80">字段缺失</p>
            </div>
          </div>
          <div className="max-h-60 overflow-auto rounded-xl border border-[var(--border)]">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-[var(--bg-elevated)] text-[var(--text-muted)]">
                <tr>
                  <th className="px-3 py-2 text-left font-semibold">名称</th>
                  <th className="px-3 py-2 text-left font-semibold">负责人</th>
                  <th className="px-3 py-2 text-left font-semibold">状态</th>
                </tr>
              </thead>
              <tbody>
                {preview.map((row, idx) => (
                  <tr key={idx} className="border-t border-[var(--border)]">
                    <td className="px-3 py-2 font-medium">{String(row.source.name || '—')}</td>
                    <td className="px-3 py-2 text-[var(--text-muted)]">{String(row.source.owner || '未指定')}</td>
                    <td className="px-3 py-2">
                      {row.status === 'ok' && <span className="inline-flex items-center gap-1 text-[var(--success)]"><CheckCircle2 className="h-3 w-3" />通过</span>}
                      {row.status === 'duplicate' && <span className="inline-flex items-center gap-1 text-[var(--warning)]"><AlertTriangle className="h-3 w-3" />{row.message}</span>}
                      {row.status === 'missing' && <span className="inline-flex items-center gap-1 text-[var(--danger)]"><Info className="h-3 w-3" />{row.message}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </CenterModal>
  );
}

export function ExportDialog({
  open, onClose, scope, setScope, format, setFormat, fields, setFields, counts, onConfirm,
}: {
  open: boolean;
  onClose: () => void;
  scope: ExportScope;
  setScope: (s: ExportScope) => void;
  format: ExportFormat;
  setFormat: (f: ExportFormat) => void;
  fields: Record<ExportField, boolean>;
  setFields: React.Dispatch<React.SetStateAction<Record<ExportField, boolean>>>;
  counts: { all: number; tab: number; selected: number };
  onConfirm: () => void;
}) {
  const targetCount = scope === 'all' ? counts.all : scope === 'tab' ? counts.tab : counts.selected;
  const enabledFieldCount = EXPORT_FIELDS.filter((f) => fields[f.id]).length;

  const title = <span className="flex items-center gap-2"><Download className="h-5 w-5 text-[var(--brand)]" />导出智能体</span>;
  const description = `选择导出范围、格式与字段 · 预计 ${targetCount} 个智能体 · 约 ${Math.max(targetCount * 4, 4)} KB`;

  const footer = (
    <>
      <button type="button" onClick={onClose} className="rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)]">取消</button>
      <button type="button" onClick={onConfirm} disabled={targetCount === 0 || enabledFieldCount === 0} className="inline-flex items-center gap-2 rounded-xl bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white hover:bg-[var(--brand-hover)] disabled:opacity-50">
        <Download className="h-3.5 w-3.5" />确认导出 ({format.toUpperCase()})
      </button>
    </>
  );

  return (
    <CenterModal
      open={open}
      onClose={onClose}
      ariaLabel="导出智能体"
      title={title}
      description={description}
      panelClassName="max-w-xl"
      footer={footer}
    >
      <div className="mt-5 space-y-5">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">范围</p>
          <div className="mt-2 space-y-2">
            {([
              { id: 'all' as const, label: '全部智能体', count: counts.all },
              { id: 'tab' as const, label: '当前 Tab / 视图', count: counts.tab },
              { id: 'selected' as const, label: '已选中', count: counts.selected },
            ]).map((opt) => {
              const active = scope === opt.id;
              const disabled = opt.count === 0;
              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => !disabled && setScope(opt.id)}
                  disabled={disabled}
                  className={`flex w-full items-center justify-between rounded-xl border px-4 py-2.5 text-left text-xs transition ${active ? 'border-[var(--brand)] bg-[var(--brand-light)]' : 'border-[var(--border)] hover:border-[var(--brand)]'} ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}
                >
                  <span className="inline-flex items-center gap-2 font-medium">
                    <span className={`grid h-4 w-4 place-items-center rounded-full border ${active ? 'border-[var(--brand)] bg-[var(--brand)]' : 'border-[var(--border)]'}`}>
                      {active && <span className="h-1.5 w-1.5 rounded-full bg-white" />}
                    </span>
                    {opt.label}
                  </span>
                  <span className="text-[var(--text-muted)]">{opt.count} 个</span>
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">格式</p>
          <div className="mt-2 flex gap-2">
            {(['json', 'csv', 'yaml'] as const).map((f) => {
              const active = format === f;
              return (
                <button
                  key={f}
                  type="button"
                  onClick={() => setFormat(f)}
                  aria-pressed={active}
                  className={`flex-1 rounded-xl border px-4 py-2 text-xs font-semibold transition ${active ? 'border-[var(--brand)] bg-[var(--brand-light)] text-[var(--brand)]' : 'border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]'}`}
                >
                  {f.toUpperCase()}
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">字段</p>
          <div className="mt-2 grid grid-cols-2 gap-2">
            {EXPORT_FIELDS.map((f) => {
              const active = fields[f.id];
              return (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => setFields((prev) => ({ ...prev, [f.id]: !prev[f.id] }))}
                  aria-pressed={active}
                  className={`inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-xs transition ${active ? 'border-[var(--brand)] bg-[var(--brand-light)] text-[var(--brand)]' : 'border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]'}`}
                >
                  {active ? <CheckSquare className="h-3.5 w-3.5" /> : <Square className="h-3.5 w-3.5" />}
                  {f.label}
                </button>
              );
            })}
          </div>
        </div>

        <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] px-4 py-3 text-[11px] text-[var(--text-muted)]">
          预览:<span className="font-semibold text-[var(--text)]">{targetCount}</span> 个 · {enabledFieldCount} 个字段 · 约 {Math.max(targetCount * 4, 4)} KB
        </div>
      </div>
    </CenterModal>
  );
}
