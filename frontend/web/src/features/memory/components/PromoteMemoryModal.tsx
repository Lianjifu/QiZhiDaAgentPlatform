/**
 * PromoteMemoryModal — L2 → **团队知识**批量晋升(团队 + 标题 + 摘要)。
 *
 * ⚠️ **终点是 knowledge 的候选** ✓ —— L3 表退役了 ✓（M-47 ✓）。
 */
import { useState } from 'react';
import { ArrowUpRight, X } from 'lucide-react';

const TEAMS = ['产品团队', '客服团队', '研发团队', '财务团队', '法务团队', '人力资源', '战略团队'];

export function PromoteMemoryModal({ open, factIds, onClose, onConfirm }: {
  open: boolean; factIds: string[]; onClose: () => void; onConfirm: (team: string, title: string, summary: string) => void;
}) {
  const [team, setTeam] = useState(TEAMS[1]);
  const [title, setTitle] = useState('');
  const [summary, setSummary] = useState('');
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/45 p-4 sm:items-center sm:p-8" role="dialog" aria-modal="true" aria-label="晋升为团队知识" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <div className="my-4 flex w-full max-w-2xl flex-col overflow-hidden rounded-2xl bg-[var(--surface-1)] shadow-2xl sm:my-0">
        <div className="flex items-center justify-between border-b border-[var(--border)] px-6 py-3">
          <div className="flex items-center gap-2 text-sm font-semibold"><ArrowUpRight className="h-5 w-5 text-[var(--brand)]" />L2 → 团队知识晋升 · 共 {factIds.length} 条</div>
          <button type="button" onClick={onClose} aria-label="关闭" className="rounded-lg p-2 text-[var(--text-muted)] hover:bg-[var(--bg-hover)]"><X className="h-5 w-5" /></button>
        </div>
        <div className="space-y-4 overflow-y-auto px-6 py-6">
          <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-app)] p-3 text-xs text-[var(--text-secondary)]">
            即将晋升 <span className="font-semibold text-[var(--brand)]">{factIds.length}</span> 条 L2 事实为团队共享知识。晋升后会写入**知识库**的候选文档,管理员审核后发布。
          </div>
          <label className="block">
            <span className="text-xs font-semibold">目标团队</span>
            <select value={team} onChange={(event) => setTeam(event.target.value)} className="mt-1 h-10 w-full rounded-xl border border-[var(--border)] bg-[var(--surface-1)] px-3 text-sm outline-none focus:border-[var(--brand)]">
              {TEAMS.map((t) => <option key={t}>{t}</option>)}
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
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-[var(--border)] px-6 py-4">
          <button type="button" onClick={onClose} className="rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold hover:border-[var(--brand)]">取消</button>
          <button type="button" disabled={!title.trim() || !summary.trim()} onClick={() => onConfirm(team, title.trim(), summary.trim())} className="inline-flex items-center gap-2 rounded-xl bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-50">
            <ArrowUpRight className="h-3.5 w-3.5" />写入知识候选
          </button>
        </div>
      </div>
    </div>
  );
}