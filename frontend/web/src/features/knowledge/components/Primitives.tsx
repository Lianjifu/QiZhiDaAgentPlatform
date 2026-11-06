/**
 * AdminKnowledge 共享视觉元素 — tone 配色 / 状态徽章 / Sparkline / Lucide icon 映射。
 */
import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  Database,
  FileText,
  Folder,
  GitBranch,
  Globe,
  HardDrive,
  Hash,
  Plug,
  Sparkles,
  XCircle,
} from 'lucide-react';
import type { KbStatus, DocStatus, SourceStatus, TaskStatus, EvalStatus, TabId, Tone } from '../schema';

export const TONE_CLASS: Record<Tone, string> = {
  brand: 'bg-[var(--brand-light)] text-[var(--brand)]',
  info: 'bg-sky-50 text-sky-600 dark:bg-sky-500/15 dark:text-sky-300',
  success: 'bg-emerald-50 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-300',
  warn: 'bg-amber-50 text-amber-600 dark:bg-amber-500/15 dark:text-amber-300',
  danger: 'bg-rose-50 text-rose-600 dark:bg-rose-500/15 dark:text-rose-300',
  purple: 'bg-violet-50 text-violet-600 dark:bg-violet-500/15 dark:text-violet-300',
};

export function toneClass(tone: string): string {
  return TONE_CLASS[tone as Tone] ?? TONE_CLASS.info;
}

export const KB_STATUS_BADGE: Record<KbStatus, { label: string; className: string }> = {
  indexed: { label: '已索引', className: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300' },
  indexing: { label: '索引中', className: 'bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300' },
  paused: { label: '已暂停', className: 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300' },
  failed: { label: '失败', className: 'bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300' },
};

export const DOC_STATUS_BADGE: Record<DocStatus, { label: string; className: string }> = {
  parsed: { label: '已解析', className: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300' },
  parsing: { label: '解析中', className: 'bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300' },
  pending: { label: '待处理', className: 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300' },
  failed: { label: '失败', className: 'bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300' },
};

export const SOURCE_STATUS_BADGE: Record<SourceStatus, { label: string; className: string }> = {
  online: { label: '在线', className: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300' },
  syncing: { label: '同步中', className: 'bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300' },
  error: { label: '异常', className: 'bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300' },
  paused: { label: '已暂停', className: 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300' },
};

export const TASK_STATUS_BADGE: Record<TaskStatus, { label: string; className: string }> = {
  pending: { label: '排队', className: 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300' },
  running: { label: '进行中', className: 'bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300' },
  success: { label: '完成', className: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300' },
  failed: { label: '失败', className: 'bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300' },
  paused: { label: '暂停', className: 'bg-[var(--bg-elevated)] text-[var(--text-secondary)]' },
};

export const EVAL_STATUS_BADGE: Record<EvalStatus, { label: string; className: string }> = {
  pass: { label: '通过', className: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300' },
  fail: { label: '未命中', className: 'bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300' },
  skipped: { label: '跳过', className: 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300' },
};

export const SOURCE_TYPE_ICON: Record<string, typeof Database> = {
  notion: FileText,
  slack: Hash,
  web: Globe,
  postgres: Database,
  s3: HardDrive,
  api: Plug,
  folder: Folder,
  confluence: GitBranch,
};

export const TAB_ICON: Record<TabId, typeof BookOpen> = {
  kb: BookOpen,
  sources: Database,
};

export function ProgressBar({ value, tone = 'brand' as Tone }: { value: number; tone?: Tone }) {
  const stroke = tone === 'success' ? 'bg-emerald-500'
    : tone === 'warn' ? 'bg-amber-500'
    : tone === 'danger' ? 'bg-rose-500'
    : 'bg-[var(--brand)]';
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--bg-elevated)]">
      <div className={`h-1.5 rounded-full ${stroke} transition-all`} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}

export const STATUS_ICON = { CheckCircle2, XCircle, AlertTriangle, Sparkles };