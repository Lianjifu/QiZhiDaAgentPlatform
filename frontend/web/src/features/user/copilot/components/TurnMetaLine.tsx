/**
 * **本轮小结** ✓ —— 耗时 / token / 成本 / 工具 / 知识命中 / 模型 ✓。
 *
 * ⚠️ **没有数据就不显示** ✓（不编 ✓ —— 空着比假数字强 ✓）。
 * ⚠️ **数字都来自后端** ✓（重开会话也在 ✓ —— 事件流里记着 ✓）。
 */
import { BookOpen, Clock3, Cpu, Wrench } from 'lucide-react';
import type { TurnFacts } from './turns';
import { formatDuration } from './relativeTime';

function formatTokens(value: number): string {
  return value.toLocaleString('zh-CN');
}

export function TurnMetaLine({ facts }: { facts: TurnFacts }) {
  const items: Array<{ icon: typeof Clock3; text: string }> = [];
  if (facts.durationMs != null) {
    items.push({ icon: Clock3, text: `耗时 ${formatDuration(facts.durationMs)}` });
  }
  if ((facts.inputTokens ?? 0) > 0 || (facts.outputTokens ?? 0) > 0) {
    items.push({
      icon: Cpu,
      text: `输入 ${formatTokens(facts.inputTokens ?? 0)} · 输出 ${formatTokens(facts.outputTokens ?? 0)}`,
    });
  }
  if ((facts.costUsd ?? 0) > 0) {
    items.push({ icon: Cpu, text: `成本 $${(facts.costUsd ?? 0).toFixed(4)}` });
  }
  if ((facts.toolCount ?? 0) > 0) {
    items.push({ icon: Wrench, text: `工具 ${facts.toolCount} 次` });
  }
  if ((facts.knowledgeCount ?? 0) > 0) {
    items.push({ icon: BookOpen, text: `知识 ${facts.knowledgeCount} 条` });
  }
  if (facts.modelVersion) {
    items.push({ icon: Cpu, text: facts.modelVersion });
  }
  if (!items.length) return null;

  return (
    <div
      className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-[var(--text-muted)]"
      data-testid="turn-meta"
    >
      {items.map((item) => (
        <span key={item.text} className="inline-flex items-center gap-1">
          <item.icon className="h-3 w-3" aria-hidden="true" />
          {item.text}
        </span>
      ))}
    </div>
  );
}
