import { ArrowRight, CheckCircle2, Clock3, Plus, Sparkles } from 'lucide-react';
import { useLocation } from 'react-router-dom';

/**
 * 管理端兜底占位页 —— 只挂在 `/admin/*` 上 ✓
 * （用户侧每一页都有真页面 ✓ —— 这里只描述管理端还没实现的子页 ✓）。
 */
const pageCopy: Record<string, { title: string; description: string; actions: string[] }> = {
  '/admin/overview': { title: '运营概览', description: '查看平台健康、异常事项和下一步建议动作。', actions: ['查看运营概览', '处理待办事项', '查看平台健康'] },
  '/admin/agents': { title: '智能体管理', description: '创建、评测和发布企业智能体与应用。', actions: ['智能体目录', '草稿与待发布', '版本与发布'] },
  '/admin/knowledge': { title: '知识管理', description: '管理企业知识库、文档资产、数据来源、加工状态和访问权限。', actions: ['知识库', '文档资产', '数据来源', '加工任务', '检索评测'] },
  '/admin/memory': { title: '记忆管理', description: '管理智能体记忆、用户偏好与跨会话上下文，配置保留策略与可见范围。', actions: ['记忆条目', '保留策略', '可见范围', '评测与导出'] },
  '/admin/workflows': { title: '工作流管理', description: '设计、发布和分析企业工作流。', actions: ['工作流目录', '草稿工作流', '版本与发布'] },
  '/admin/tools': { title: '技能管理', description: '管理企业 Skill、Tool 与 MCP 等可被智能体调用的技能能力。', actions: ['技能目录', '新增接入', '访问权限'] },
  '/admin/evaluations': { title: '评测中心', description: '评测智能体、知识与工作流的质量，对比版本差异并跟踪回归。', actions: ['评测集', '运行评测', '结果对比', '回归追踪'] },
  '/admin/regressions': { title: '回归追踪', description: '智能体 / 知识 / 模型版本变更后自动跑回归用例，发现质量退化。', actions: ['回归用例', '运行结果', '历史对比'] },
  '/admin/feedback': { title: '用户反馈', description: '收集用户对智能体回答的赞踩、修正建议和 badcase。', actions: ['反馈列表', '修正建议', '反馈转用例'] },
  '/admin/models': { title: '模型配置', description: '配置模型服务、算力资源和运行策略。', actions: ['模型服务', '运行策略', '健康状态'] },
  '/admin/quotas': { title: '额度管理', description: '管理企业用量、预算和成本策略。', actions: ['用量概览', '预算策略', '成本明细'] },
  '/admin/operations': { title: '调用链路', description: '会话追溯：还原智能体 / 工具 / MCP 的完整调用链与上下文。', actions: ['实时链路', '慢调用分析', '错误追踪', '调用检索'] },
  '/admin/settings': { title: '平台设置', description: '配置品牌与界面、合规策略、审计日志与成员管理。模型、渠道配置与额度请在「平台治理」侧栏处理。', actions: ['品牌与界面', '合规策略', '审计日志', '成员管理'] },
  '/admin/notifications': { title: '渠道配置', description: '对接飞书、企业微信、钉钉与 Web，让用户在熟悉的入口与智能体对话。', actions: ['飞书', '企业微信', '钉钉', 'Web'] },
};

const DEFAULT_COPY = {
  title: '管理端功能',
  description: '该模块正在建设中，你可以先从左侧导航进入其它管理功能。',
  actions: ['查看运营概览', '处理待办事项'],
};

export default function WorkspacePlaceholder() {
  const { pathname } = useLocation();
  const copy =
    pageCopy[Object.keys(pageCopy).find((key) => pathname === key || pathname.startsWith(`${key}/`)) ??
      ''] ?? DEFAULT_COPY;
  return (
    <div className="mx-auto max-w-7xl p-5 sm:p-8">
      <section className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] shadow-[var(--shadow-sm)]">
        <div className="border-b border-[var(--border)] p-6 sm:p-8">
          <div className="flex items-start justify-between gap-6">
            <div><h2 className="text-2xl font-semibold tracking-tight">{copy.title}</h2><p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--text-muted)]">{copy.description}</p></div>
            <div className="hidden rounded-xl bg-[var(--brand-light)] p-3 text-[var(--brand)] sm:block"><Sparkles className="h-5 w-5" /></div>
          </div>
          <div className="mt-6 flex flex-wrap gap-2">{copy.actions.map((action) => <button key={action} type="button" className="inline-flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-3.5 py-2 text-sm font-medium text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]"><Plus className="h-4 w-4" />{action}</button>)}</div>
        </div>
        <div className="grid gap-4 p-6 sm:grid-cols-3 sm:p-8">
          {[['待我处理', '暂时没有新的事项', Clock3], ['最近使用', '登录后将显示你的工作记录', CheckCircle2], ['下一步', '选择上方操作开始使用', ArrowRight]].map(([label, text, Icon]) => <div key={label as string} className="rounded-xl border border-dashed border-[var(--border)] p-5"><Icon className="h-5 w-5 text-[var(--brand)]" /><h3 className="mt-4 text-sm font-semibold">{label as string}</h3><p className="mt-1 text-xs leading-5 text-[var(--text-muted)]">{text as string}</p></div>)}
        </div>
      </section>
    </div>
  );
}
