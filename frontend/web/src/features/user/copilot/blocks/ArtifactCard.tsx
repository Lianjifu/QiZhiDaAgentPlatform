/**
 * ArtifactCard — 模型/工具产出的可下载文档.
 *
 * 视觉: 默认折叠. 顶部条显示 icon + 名称 + 大小 + 3 按钮 (下载/右侧打开/预览).
 * 点 "预览" 或点顶部条展开预览区 (max-h-96 overflow auto).
 *
 * 格式分发:
 *   - markdown / text        → MarkdownView
 *   - html                   → <iframe sandbox srcDoc>
 *   - pdf                    → <iframe type="application/pdf"> (browser native)
 *   - code / json            → <pre> with highlight.js (按 name 推语言)
 *   - image                  → <img>
 *   - word / excel / ppt / unsupported → 不预览, 加大下载按钮
 *
 * 后端 kind 字段优先; 否则 inferKind 从 mime/扩展名兜底.
 */
import {
  ChevronDown,
  ChevronRight,
  Download,
  Eye,
  FileCode2,
  FileJson,
  FileSpreadsheet,
  FileText,
  FileType2,
  Image as ImageIcon,
  Presentation,
  AlertCircle,
} from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { MarkdownView } from '@/features/agents/components/MarkdownView';
import { CodeBlock } from './CodeBlock';
import { getApiClient } from '@qzdap/web-api';

export type ArtifactKind =
  | 'markdown'
  | 'text'
  | 'html'
  | 'json'
  | 'code'
  | 'image'
  | 'pdf'
  | 'word'
  | 'excel'
  | 'ppt'
  | 'unsupported';

export type ArtifactReady = {
  artifact_id: string;
  kind?: ArtifactKind | string;
  name: string;
  mime: string;
  size_bytes: number;
  download_path: string;
  preview_path?: string | null;
  snippet?: string;
};

const MIME_MAP: Record<string, ArtifactKind> = {
  'application/pdf': 'pdf',
  'application/json': 'json',
  'text/markdown': 'markdown',
  'text/html': 'html',
  'text/plain': 'text',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'word',
  'application/msword': 'word',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'excel',
  'application/vnd.ms-excel': 'excel',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'ppt',
  'application/vnd.ms-powerpoint': 'ppt',
  'image/png': 'image',
  'image/jpeg': 'image',
  'image/gif': 'image',
  'image/webp': 'image',
  'image/svg+xml': 'image',
};

const EXT_MAP: Record<string, ArtifactKind> = {
  md: 'markdown', markdown: 'markdown',
  txt: 'text', log: 'text',
  html: 'html', htm: 'html',
  json: 'json',
  ts: 'code', tsx: 'code', js: 'code', jsx: 'code', py: 'code',
  rs: 'code', go: 'code', java: 'code', rb: 'code', sh: 'code',
  bash: 'code', zsh: 'code', yaml: 'code', yml: 'code', toml: 'code',
  pdf: 'pdf',
  doc: 'word', docx: 'word',
  xls: 'excel', xlsx: 'excel', csv: 'excel',
  ppt: 'ppt', pptx: 'ppt',
  png: 'image', jpg: 'image', jpeg: 'image', gif: 'image', webp: 'image', svg: 'image',
};

function inferKind(artifact: ArtifactReady): ArtifactKind {
  // 1) 后端声明优先
  if (artifact.kind && (artifact.kind as string) !== 'unsupported') {
    return artifact.kind as ArtifactKind;
  }
  // 2) mime 兜底
  if (artifact.mime) {
    const base = artifact.mime.split(';')[0].trim().toLowerCase();
    if (MIME_MAP[base]) return MIME_MAP[base];
  }
  // 3) 文件扩展名兜底
  const dot = artifact.name.lastIndexOf('.');
  if (dot >= 0) {
    const ext = artifact.name.slice(dot + 1).toLowerCase();
    if (EXT_MAP[ext]) return EXT_MAP[ext];
  }
  return 'unsupported';
}

function detectCodeLanguage(name: string): string {
  const dot = name.lastIndexOf('.');
  if (dot < 0) return 'plaintext';
  const ext = name.slice(dot + 1).toLowerCase();
  const map: Record<string, string> = {
    ts: 'typescript', tsx: 'typescript', js: 'javascript', jsx: 'javascript',
    py: 'python', rb: 'ruby', go: 'go', rs: 'rust', java: 'java',
    sh: 'bash', bash: 'bash', zsh: 'bash',
    yml: 'yaml', yaml: 'yaml', toml: 'toml', json: 'json',
    sql: 'sql', xml: 'xml', html: 'xml', css: 'css',
  };
  return map[ext] ?? 'plaintext';
}

function KindIcon({ kind, className }: { kind: ArtifactKind; className?: string }) {
  const cls = className ?? 'h-4 w-4';
  const wrap = (child: ReactNode, color = 'text-[var(--brand)]') => (
    <span className={cls + ' ' + color}>{child}</span>
  );
  switch (kind) {
    case 'markdown':
    case 'text':
    case 'unsupported':
      return wrap(<FileText className={cls} />);
    case 'html':
      return wrap(<FileType2 className={cls} />);
    case 'json':
      return wrap(<FileJson className={cls} />);
    case 'code':
      return wrap(<FileCode2 className={cls} />);
    case 'image':
      return wrap(<ImageIcon className={cls} />, 'text-sky-500');
    case 'pdf':
      return wrap(<FileText className={cls} />, 'text-rose-500');
    case 'word':
      return wrap(<FileText className={cls} />, 'text-blue-500');
    case 'excel':
      return wrap(<FileSpreadsheet className={cls} />, 'text-emerald-500');
    case 'ppt':
      return wrap(<Presentation className={cls} />, 'text-amber-500');
    default:
      return wrap(<FileText className={cls} />);
  }
}

function formatSize(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

const PREVIEWABLE: ReadonlySet<ArtifactKind> = new Set([
  'markdown', 'text', 'html', 'pdf', 'code', 'json', 'image',
]);

export function ArtifactCard({
  artifact,
}: {
  artifact: ArtifactReady;
}) {
  const kind = inferKind(artifact);
  const [expanded, setExpanded] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string>('');
  const [imageUrl, setImageUrl] = useState<string>('');
  const [pdfUrl, setPdfUrl] = useState<string>('');

  const canPreview = PREVIEWABLE.has(kind);

  const download = async () => {
    setDownloading(true);
    setError('');
    try {
      const blob = await getApiClient().download(artifact.download_path);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = artifact.name || `${artifact.artifact_id}.md`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setError(String(e));
    } finally {
      setDownloading(false);
    }
  };

  const ensureBlobUrl = async (kind: ArtifactKind): Promise<string | null> => {
    if (kind === 'image' && imageUrl) return imageUrl;
    if (kind === 'pdf' && pdfUrl) return pdfUrl;
    try {
      const blob = await getApiClient().download(artifact.download_path);
      const url = URL.createObjectURL(blob);
      if (kind === 'image') setImageUrl(url);
      if (kind === 'pdf') setPdfUrl(url);
      return url;
    } catch {
      return null;
    }
  };

  const togglePreview = async () => {
    if (!canPreview) return;
    if (!expanded && (kind === 'image' || kind === 'pdf')) {
      await ensureBlobUrl(kind);
    }
    setExpanded((v) => !v);
  };

  // 120 字摘要, 给默认折叠态的"味道"
  const snippetPreview = (artifact.snippet ?? '').slice(0, 120).replace(/\n+/g, ' ').trim();

  return (
    <div className="my-3 overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface-1)]">
      {/* 顶部条: 整行可点展开 (除了按钮), 默认只显示概要 */}
      <div className="flex items-center justify-between gap-2 px-3 py-2">
        <button
          type="button"
          onClick={togglePreview}
          disabled={!canPreview}
          className="flex min-w-0 flex-1 items-center gap-2 text-left disabled:cursor-default"
          title={canPreview ? '点击展开预览' : '此格式暂不支持预览'}
        >
          <KindIcon kind={kind} />
          <div className="min-w-0 flex-1">
            <p className="flex items-center gap-1.5 truncate text-xs font-semibold text-[var(--text)]">
              {artifact.name}
              {canPreview ? (
                expanded ? (
                  <ChevronDown className="h-3 w-3 shrink-0 text-[var(--text-muted)]" />
                ) : (
                  <ChevronRight className="h-3 w-3 shrink-0 text-[var(--text-muted)]" />
                )
              ) : null}
            </p>
            <p className="truncate text-[10px] text-[var(--text-muted)]">
              {artifact.mime || '未知类型'} · {formatSize(artifact.size_bytes)}
            </p>
          </div>
        </button>
        <div className="flex shrink-0 items-center gap-1">
          {canPreview ? (
            <button
              type="button"
              onClick={togglePreview}
              className="inline-flex items-center gap-1 rounded-md border border-[var(--border)] px-2 py-1 text-[10px] font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]"
              title={expanded ? '收起预览' : '预览'}
            >
              <Eye className="h-3 w-3" />
              {expanded ? '收起' : '预览'}
            </button>
          ) : (
            <span className="inline-flex items-center gap-1 rounded-md bg-[var(--bg-elevated)] px-2 py-1 text-[10px] text-[var(--text-muted)]" title="不支持预览">
              <AlertCircle className="h-3 w-3" />
              仅下载
            </span>
          )}
          <button
            type="button"
            onClick={() => void download()}
            disabled={downloading}
            className="inline-flex items-center gap-1 rounded-md bg-[var(--brand)] px-2 py-1 text-[10px] font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            <Download className="h-3 w-3" />
            {downloading ? '下载中…' : '下载'}
          </button>
        </div>
      </div>

      {/* 摘要: 默认态露一行 snippet 文字 (可选) */}
      {!expanded && snippetPreview ? (
        <p className="border-t border-[var(--border)]/50 px-3 py-1.5 text-[11px] leading-5 text-[var(--text-muted)] line-clamp-1">
          {snippetPreview}{snippetPreview.length === 120 ? '…' : ''}
        </p>
      ) : null}

      {/* 展开预览 */}
      {expanded && canPreview ? (
        <div className="max-h-96 overflow-auto border-t border-[var(--border)] bg-[var(--bg-elevated)]/40 p-3 text-xs">
          {kind === 'markdown' ? (
            <MarkdownView source={artifact.snippet ?? ''} />
          ) : kind === 'html' ? (
            <iframe
              sandbox=""
              title={artifact.name}
              srcDoc={artifact.snippet ?? ''}
              className="h-80 w-full rounded border border-[var(--border)] bg-white"
            />
          ) : kind === 'pdf' ? (
            pdfUrl ? (
              <iframe src={pdfUrl} title={artifact.name} className="h-96 w-full rounded border border-[var(--border)] bg-white" />
            ) : (
              <p className="py-6 text-center text-[11px] text-[var(--text-muted)]">PDF 加载中…</p>
            )
          ) : kind === 'image' ? (
            imageUrl ? (
              <img src={imageUrl} alt={artifact.name} className="mx-auto max-h-80 rounded" />
            ) : (
              <p className="py-6 text-center text-[11px] text-[var(--text-muted)]">图片加载中…</p>
            )
          ) : kind === 'json' ? (
            <CodeBlock language="json" code={artifact.snippet ?? ''} />
          ) : kind === 'code' ? (
            <CodeBlock language={detectCodeLanguage(artifact.name)} code={artifact.snippet ?? ''} />
          ) : (
            <pre className="overflow-auto rounded bg-[var(--surface-1)] p-2 font-mono text-[11px] leading-5 text-[var(--text)]">
              {artifact.snippet ?? '(空)'}
            </pre>
          )}
        </div>
      ) : null}

      {error ? (
        <p className="border-t border-rose-200 bg-rose-50 px-3 py-1.5 text-[10px] text-rose-700">
          {error}
        </p>
      ) : null}
    </div>
  );
}
