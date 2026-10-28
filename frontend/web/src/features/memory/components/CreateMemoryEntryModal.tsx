/**
 * CreateMemoryEntryModal — 手工新建一条 L3 团队知识。
 *
 * 与 PromoteMemoryModal 的区别:那条是 L2 → L3 的批量晋升(写草稿待审核),
 * 这条是管理员直接建一条团队共享知识,默认直接发布。
 */
import { useState } from 'react';
import { Plus, X } from 'lucide-react';

const DEFAULT_TEAMS = ['产品团队', '客服团队', '研发团队', '财务团队', '法务团队', '人力资源', '战略团队'];
const DEFAULT_CATEGORIES = ['流程', '规范', '话术', '术语表', '市场', '合规'];

export function CreateMemoryEntryModal({
  open, teams, onClose, onConfirm, submitting = false,
}: {
  open: boolean;
  teams: string[];
  onClose: () => void;
  onConfirm: (input: { team: string; title: string; summary: string; category: string; status: 'draft' | 'published' }) => void;
  submitting?: boolean;
}) {
  const [team, setTeam] = useState(DEFAULT_TEAMS[0]);
  const [title, setTitle] = useState('');
  const [summary, setSummary] = useState('');
  const [category, setCategory] = useState(DEFAULT_CATEGORIES[0]);
  const [status, setStatus] = useState<'draft' | 'published'>('published');

  if (!open) return null;
  const options = teams.length > 0 ? Array.from(new Set([...teams, ...DEFAULT_TEAMS])) : DEFAULT_TEAMS;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/45 p-4 sm:items-center sm:p-8" role="dialog" aria-modal="true" aria-label="新建团队知识" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <div className="my-4 flex w-full max-w-2xl flex-col overflow-hidden rounded-2xl bg-[var(--surface-1)] shadow-2xl sm:my-0">
        <div className="flex items-center justify-between border-b border-[var(--border)] px-6 py-3">
          <div className="flex items-center gap-2 text-sm font-semibold"><Plus className="h-5 w-5 text-[var(--brand)]" />新建团队知识</div>
          <button type="button" onClick={onClose} aria-label="关闭" className="rounded-lg p-2 text-[var(--text-muted)] hover:bg-[var(--bg-hover)]"><X className="h-5 w-5" /></button>
        </div>
        <div className="space-y-4 overflow-y-auto px-6 py-6">
          <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-app)] p-3 text-xs text-[var(--text-secondary)]">
            这条知识会写入 L3 团队记忆层,发布后立即参与召回。
          </div>
          <label className="block">
            <span className="text-xs font-semibold">所属团队</span>
            <select value={team} onChange={(event) => setTeam(event.target.value)} className="mt-1 h-10 w-full rounded-xl border border-[var(--border)] bg-[var(--surface-1)] px-3 text-sm outline-none focus:border-[var(--brand)]">
              {options.map((t) => <option key={t}>{t}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="text-xs font-semibold">标题</span>
            <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="例如:客服退款话术统一" className="mt-1 h-10 w-full rounded-xl border border-[var(--border)] bg-[var(--surface-1)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
          </label>
          <label className="block">
            <span className="text-xs font-semibold">摘要</span>
            <textarea value={summary} onChange={(event) => setSummary(event.target.value)} placeholder="一句话说明这条团队知识解决了什么问题" className="mt-1 min-h-[100px] w-full rounded-xl border border-[var(--border)] bg-[var(--surface-1)] px-3 py-2 text-sm outline-none focus:border-[var(--brand)]" />
          </label>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="text-xs font-semibold">类别</span>
              <select value={category} onChange={(event) => setCategory(event.target.value)} className="mt-1 h-10 w-full rounded-xl border border-[var(--border)] bg-[var(--surface-1)] px-3 text-sm outline-none focus:border-[var(--brand)]">
                {DEFAULT_CATEGORIES.map((c) => <option key={c}>{c}</option>)}
              </select>
            </label>
            <label className="block">
              <span className="text-xs font-semibold">初始状态</span>
              <select value={status} onChange={(event) => setStatus(event.target.value as 'draft' | 'published')} className="mt-1 h-10 w-full rounded-xl border border-[var(--border)] bg-[var(--surface-1)] px-3 text-sm outline-none focus:border-[var(--brand)]">
                <option value="published">发布</option>
                <option value="draft">草稿</option>
              </select>
            </label>
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-[var(--border)] px-6 py-4">
          <button type="button" onClick={onClose} className="rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold hover:border-[var(--brand)]">取消</button>
          <button
            type="button"
            disabled={!title.trim() || !summary.trim() || submitting}
            onClick={() => onConfirm({ team, title: title.trim(), summary: summary.trim(), category, status })}
            className="inline-flex items-center gap-2 rounded-xl bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-50"
          >
            <Plus className="h-3.5 w-3.5" />{submitting ? '创建中…' : '创建'}
          </button>
        </div>
      </div>
    </div>
  );
}
