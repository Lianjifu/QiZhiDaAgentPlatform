/**
 * **资源库** ✓ —— 智能体 ✓ / 知识 ✓ / 技能 ✓ / 工作流 ✓ 四类资源合到一页 ✓。
 *
 * ⚠️ **为什么合并** ✓ —— 四页的**骨架完全一样** ✓（列表 ✓ + 卡片 ✓ + 详情
 * 抽屉 ✓ + 浏览抽屉 ✓）—— 分四页只是把同一段代码抄了四遍 ✓。
 * 合并后骨架只写一遍 ✓（``ResourceSection`` ✓ / ``ResourceDrawers`` ✓），
 * **每类资源只保留它自己的动作** ✓（在 ``kinds/`` 里 ✓）。
 *
 * ⚠️ **页签写进 URL** ✓（``?tab=`` ✓）—— 深链要能直达 ✓（旧路径
 * ``/agents`` 之类的会重定向过来 ✓）。
 */

import { useSearchParams } from 'react-router-dom';

import { WorkspacePage } from '../components';
import { AgentsKind } from './kinds/agents';
import { AutomationsKind } from './kinds/automations';
import { KnowledgeKind } from './kinds/knowledge';
import { SkillsKind } from './kinds/skills';
import type { ResourceKindKey } from './schema';

const TABS: { key: ResourceKindKey; label: string }[] = [
  { key: 'agents', label: '智能体' },
  { key: 'knowledge', label: '知识' },
  { key: 'skills', label: '技能' },
  { key: 'automations', label: '工作流' },
];

const DEFAULT_TAB: ResourceKindKey = 'agents';

function readTab(raw: string | null): ResourceKindKey {
  const found = TABS.find((tab) => tab.key === raw);
  return found ? found.key : DEFAULT_TAB;
}

export default function LibraryPage() {
  const [params, setParams] = useSearchParams();
  const tab = readTab(params.get('tab'));

  return (
    <WorkspacePage>
      <nav aria-label="资源库分类" className="flex flex-wrap gap-1 border-b border-[var(--border)] pb-2">
        {TABS.map((item) => (
          <button
            key={item.key}
            type="button"
            aria-current={tab === item.key ? 'page' : undefined}
            onClick={() => setParams(item.key === DEFAULT_TAB ? {} : { tab: item.key })}
            className={`min-w-16 rounded-md px-3 py-1.5 text-xs font-semibold transition ${
              tab === item.key
                ? 'bg-[var(--text)] text-[var(--surface-1)]'
                : 'text-[var(--text-muted)] hover:bg-[var(--bg-hover)]'
            }`}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {tab === 'agents' ? <AgentsKind /> : null}
      {tab === 'knowledge' ? <KnowledgeKind /> : null}
      {tab === 'skills' ? <SkillsKind /> : null}
      {tab === 'automations' ? <AutomationsKind /> : null}
    </WorkspacePage>
  );
}
