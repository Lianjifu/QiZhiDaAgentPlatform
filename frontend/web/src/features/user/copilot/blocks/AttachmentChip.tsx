/**
 * AttachmentChip — 附件就绪小卡片 (下载 + 名称 + 大小).
 * 比 ArtifactCard 轻量, 不带预览; 嵌入 assistant message 底部.
 */
import { Download, Paperclip } from 'lucide-react';
import { getApiClient } from '@qzdap/web-api';

function formatSize(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export type AttachmentReady = {
  attachment_id: string;
  name: string;
  mime: string;
  size_bytes: number;
  download_path: string;
};

export function AttachmentChip({ attachment }: { attachment: AttachmentReady }) {
  const download = async () => {
    try {
      const blob = await getApiClient().download(attachment.download_path);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = attachment.name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      // ignore
    }
  };
  return (
    <span className="inline-flex items-center gap-2 rounded-md border border-[var(--border)] bg-[var(--surface-1)] px-2 py-1 text-[11px] text-[var(--text-secondary)]">
      <Paperclip className="h-3 w-3 text-[var(--text-muted)]" />
      <span className="max-w-[180px] truncate font-medium text-[var(--text)]">
        {attachment.name}
      </span>
      <span className="text-[10px] text-[var(--text-muted)]">
        {formatSize(attachment.size_bytes)}
      </span>
      <button
        type="button"
        onClick={() => void download()}
        className="grid h-5 w-5 place-items-center rounded text-[var(--text-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--brand)]"
        title="下载"
      >
        <Download className="h-3 w-3" />
      </button>
    </span>
  );
}
