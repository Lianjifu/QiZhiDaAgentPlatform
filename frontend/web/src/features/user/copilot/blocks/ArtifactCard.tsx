/**
 * ArtifactCard — 模型/工具产出的可下载文档.
 * - markdown / text: 用 MarkdownView 渲染前 800 字 snippet
 * - html: <iframe sandbox> 预览
 * - code / json: <pre> 等宽展示
 * - 操作: 下载 (blob 拉取) + "在右侧工作区打开"
 */
import { Download, ExternalLink, FileText, FileCode2, FileJson, Image as ImageIcon, FileType2 } from 'lucide-react';
import { useState } from 'react';
import { MarkdownView } from '@/features/agents/components/MarkdownView';

export type ArtifactReady = {
  artifact_id: string;
  kind: 'markdown' | 'code' | 'html' | 'json' | 'image' | 'text';
  name: string;
  mime: string;
  size_bytes: number;
  download_path: string;
  preview_path?: string | null;
  snippet?: string;
};

function KindIcon({ kind }: { kind: ArtifactReady['kind'] }) {
  const cls = 'h-4 w-4 text-[var(--brand)]';
  if (kind === 'markdown') return <FileText className={cls} />;
  if (kind === 'code') return <FileCode2 className={cls} />;
  if (kind === 'json') return <FileJson className={cls} />;
  if (kind === 'image') return <ImageIcon className={cls} />;
  if (kind === 'html') return <FileType2 className={cls} />;
  return <FileText className={cls} />;
}

function formatSize(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function ArtifactCard({
  artifact,
  onOpenInWorkspace,
}: {
  artifact: ArtifactReady;
  onOpenInWorkspace?: (a: ArtifactReady) => void;
}) {
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string>('');

  const download = async () => {
    setDownloading(true);
    setError('');
    try {
      const r = await fetch(artifact.download_path, { credentials: 'include' });
      if (!r.ok) throw new Error(`下载失败: HTTP ${r.status}`);
      const blob = await r.blob();
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

  return (
    <div className="my-3 overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface-1)]">
      <div className="flex items-center justify-between gap-2 border-b border-[var(--border)] bg-[var(--bg-elevated)] px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <KindIcon kind={artifact.kind} />
          <div className="min-w-0">
            <p className="truncate text-xs font-semibold text-[var(--text)]">{artifact.name}</p>
            <p className="text-[10px] text-[var(--text-muted)]">
              {artifact.mime} · {formatSize(artifact.size_bytes)}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {onOpenInWorkspace ? (
            <button
              type="button"
              onClick={() => onOpenInWorkspace(artifact)}
              className="inline-flex items-center gap-1 rounded-md border border-[var(--border)] px-2 py-1 text-[10px] font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]"
              title="在右侧工作区打开"
            >
              <ExternalLink className="h-3 w-3" />
              右侧打开
            </button>
          ) : null}
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

      <div className="max-h-72 overflow-auto p-3 text-xs">
        {artifact.kind === 'markdown' ? (
          <MarkdownView source={artifact.snippet ?? ''} />
        ) : artifact.kind === 'html' ? (
          <iframe
            sandbox=""
            title={artifact.name}
            srcDoc={artifact.snippet ?? ''}
            className="h-40 w-full rounded border border-[var(--border)] bg-white"
          />
        ) : (
          <pre className="overflow-auto rounded bg-[var(--bg-elevated)] p-2 font-mono text-[11px] leading-5 text-[var(--text)]">
            {artifact.snippet ?? '(空)'}
          </pre>
        )}
      </div>

      {error ? (
        <p className="border-t border-rose-200 bg-rose-50 px-3 py-1.5 text-[10px] text-rose-700">
          {error}
        </p>
      ) : null}
    </div>
  );
}
