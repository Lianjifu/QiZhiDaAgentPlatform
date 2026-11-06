import { Trash2 } from 'lucide-react';
import { CenterModal } from '@/components/feedback/CenterModal';
import type { Skill } from '../schema';
import { STATUS_BADGE } from './constants';
import { useAgentsUsingSkill } from '@/features/agents/usage';

interface DeleteConfirmModalProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  skill: Skill | null;
}

export function DeleteConfirmModal({ open, onClose, onConfirm, skill }: DeleteConfirmModalProps) {
  // ⚠️ **反查智能体目录** ✓ —— `usedByAgents` 是没人写的空列 ✓，
  // 真事实是「哪些智能体的 tools 里带这个技能 id」✓。
  // ⚠️ **hook 必须在早退之前调** ✓（React 规则 ✓）。
  const boundAgents = useAgentsUsingSkill(skill?.id ?? '');
  const affectedAgents = boundAgents.length;
  if (!skill) return null;
  return (
    <CenterModal
      open={open}
      onClose={onClose}
      ariaLabel="删除技能"
      panelClassName="max-w-md"
      title={<span className="flex items-center gap-2"><Trash2 className="h-5 w-5 text-rose-600" />删除技能:{skill.name}</span>}
      description={`确认后将永久删除该技能,且${affectedAgents > 0 ? `会影响 ${affectedAgents} 个智能体的调用` : '当前未被任何智能体使用'}。`}
      footer={
        <>
          <button type="button" onClick={onClose} className="rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold">取消</button>
          <button type="button" onClick={onConfirm} className="rounded-xl bg-rose-600 px-4 py-2 text-xs font-semibold text-white">确认删除</button>
        </>
      }
    >
      <div className="mt-4 space-y-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-xs text-rose-900 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">
        <p>· 类型:{skill.type}</p>
        <p>· 状态:{STATUS_BADGE[skill.status].label}</p>
        <p>· 关联智能体:{affectedAgents > 0 ? boundAgents.map((a) => a.name).join('、') : '无'}</p>
        <p>· 最后更新:{skill.lastUpdate}</p>
      </div>
    </CenterModal>
  );
}