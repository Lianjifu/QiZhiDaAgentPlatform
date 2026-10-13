import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowRight, Database, Network, Sparkles, Wrench } from 'lucide-react';
import type { SkillType } from '../schema';
import { TYPE_META } from './constants';

const PICKER_ITEMS: Array<{
  type: SkillType;
  icon: typeof Sparkles;
  href: string;
  description: string;
  bullets: string[];
}> = [
  {
    type: 'Skill',
    icon: Sparkles,
    href: '/admin/tools/new?type=Skill',
    description: TYPE_META.Skill.description,
    bullets: ['沙箱执行 Python/Prompt', '无凭据、无外网', '适合经验沉淀与流程模板'],
  },
  {
    type: 'Tool',
    icon: Wrench,
    href: '/admin/tools/new?type=Tool',
    description: TYPE_META.Tool.description,
    bullets: ['调用外部 HTTP API', 'API Key / Bearer / OAuth', '出站白名单 + 写操作确认'],
  },
  {
    type: 'MCP',
    icon: Network,
    href: '/admin/tools/new?type=MCP',
    description: TYPE_META.MCP.description,
    bullets: ['stdio / SSE / Streamable HTTP', '从 server.tools/list 拉取能力', 'Token 加密 + 探活 + 轮换'],
  },
];

/**
 * 入口 type picker — `/admin/tools/new` 无 type 参数时,先选 3 个类型之一。
 * 选完后路由到 `?type=Skill|Tool|MCP`,由 SkillCreatePage 加载 wizard。
 */
export function SkillTypePicker({ withHint = true }: { withHint?: boolean }) {
  const navigate = useNavigate();
  return (
    <div className="space-y-5">
      {withHint && (
        <p className="text-xs text-[var(--text-muted)]">
          选择要新建的能力类型。三类走完全不同的运行路径,凭据 / schema / 风险模型均不同。
        </p>
      )}
      <div className="grid gap-4 lg:grid-cols-3">
        {PICKER_ITEMS.map((item) => {
          const Icon = item.icon;
          const meta = TYPE_META[item.type];
          return (
            <button
              key={item.type}
              type="button"
              onClick={() => navigate(item.href)}
              className="group flex flex-col items-start gap-3 rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 text-left transition hover:border-[var(--brand)] hover:bg-white"
            >
              <div className="flex w-full items-center gap-3">
                <span className={`grid h-10 w-10 place-items-center rounded-xl ${meta.tone}`}>
                  <Icon className="h-5 w-5" />
                </span>
                <div className="flex-1">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">{item.type} · 技能</p>
                  <h3 className="text-base font-semibold">{meta.subLabel}</h3>
                </div>
                <ArrowRight className="h-4 w-4 text-[var(--text-muted)] transition group-hover:translate-x-0.5 group-hover:text-[var(--brand)]" />
              </div>
              <p className="text-xs leading-5 text-[var(--text-muted)]">{item.description}</p>
              <ul className="mt-1 space-y-1 text-[11px] text-[var(--text-secondary)]">
                {item.bullets.map((b) => (
                  <li key={b} className="flex items-center gap-1.5">
                    <span className="h-1 w-1 rounded-full bg-[var(--brand)]" />
                    {b}
                  </li>
                ))}
              </ul>
            </button>
          );
        })}
      </div>
      <p className="text-[10px] text-[var(--text-muted)]">
        模板市场提供 4-5 个 Skill / 5 个 Tool / 4 个 MCP 范例,选完类型后可在 Step 2 选模板填充。
      </p>
    </div>
  );
}
