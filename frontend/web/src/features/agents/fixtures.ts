/**
 * 管理侧「智能体工作台」fixture — 6 个种子智能体 + 配套的 prompts/knowledgeRefs/memoryPolicy/flowRefs 派生助手。
 */
import type {
  AgentEntry, CustomPromptDoc, KnowledgeRef, FlowRef, MemoryPolicy, FlowTrigger, SkillRef,
} from './schema';

import { buildPrompts } from './components/constants';

const TOOL_TYPE_BY_NAME: Record<string, 'Skill' | 'Tool' | 'MCP'> = {
  '订单查询': 'Tool', '退换货流程': 'Tool', '知识检索': 'Tool', '情绪识别': 'Tool',
  '人工坐席': 'Tool', '邮件发送': 'Tool', '客户画像': 'Tool', 'CRM 查询': 'Tool',
  '报价引擎': 'Tool', '合同条款检索': 'Tool', '日程预约': 'Tool', 'SQL 生成': 'Skill',
  '图表渲染': 'Tool', '指标库查询': 'Tool', '数据脱敏': 'Tool', '导出 PDF': 'Tool',
  'OCR 单据': 'Skill', '报销规则': 'Tool', '预算查询': 'Tool', '对账核对': 'Tool',
  '审批中心': 'Tool', '工作流编辑器': 'Skill', '触发器': 'Skill', '人工审批': 'Tool',
  '通知中心': 'Tool', '审计日志': 'Tool', '图片 OCR': 'Skill', '上下文记忆': 'MCP',
  '审批中心·升级': 'Tool', '审批中心·驳回': 'Tool', '日程预约·同步': 'Tool',
};

export function toolsFromNames(names: string[]): SkillRef[] {
  return names.map((name, idx) => ({
    id: `tool-${name.replace(/\s+/g, '-').toLowerCase()}-${idx}`,
    name,
    type: TOOL_TYPE_BY_NAME[name] ?? 'Tool',
    enabled: true,
  }));
}

const KNOWLEDGE_POOL: Record<string, KnowledgeRef[]> = {
  客服: [
    { id: 'kb-order', name: '订单知识库', scope: '公开', enabled: true },
    { id: 'kb-faq', name: 'FAQ 词库', scope: '公开', enabled: true },
    { id: 'kb-emotion', name: '情绪识别手册', scope: '部门', enabled: false },
  ],
  销售: [
    { id: 'kb-product', name: '产品手册', scope: '公开', enabled: true },
    { id: 'kb-crm', name: 'CRM 客户画像', scope: '部门', enabled: true },
    { id: 'kb-contract', name: '合同条款库', scope: '部门', enabled: true },
  ],
  数据: [
    { id: 'kb-metrics', name: '指标字典', scope: '部门', enabled: true },
    { id: 'kb-sql', name: 'SQL 查询模板', scope: '部门', enabled: true },
    { id: 'kb-report', name: '历史分析报告', scope: '部门', enabled: false },
  ],
  财务: [
    { id: 'kb-finance-rules', name: '报销与税务规则', scope: '部门', enabled: true },
    { id: 'kb-budget', name: '预算执行手册', scope: '部门', enabled: true },
    { id: 'kb-audit', name: '合规审计清单', scope: '部门', enabled: true },
  ],
  流程: [
    { id: 'kb-flow-engine', name: '流程引擎文档', scope: '公开', enabled: true },
    { id: 'kb-approval', name: '审批节点定义', scope: '部门', enabled: true },
  ],
  HR: [
    { id: 'kb-hr-policy', name: 'HR 政策手册', scope: '部门', enabled: true },
    { id: 'kb-onboard', name: '入职离职流程', scope: '部门', enabled: true },
  ],
  IT: [
    { id: 'kb-runbook', name: '运维 Runbook', scope: '部门', enabled: true },
    { id: 'kb-ticket', name: '工单模板', scope: '部门', enabled: true },
  ],
};

export function buildKnowledgeRefs(category: string): KnowledgeRef[] {
  const scopedCategory = category.startsWith('客服') ? '客服'
    : category.startsWith('销售') ? '销售'
    : category.startsWith('数据') ? '数据'
    : category.startsWith('财务') ? '财务'
    : category.startsWith('工作流') ? '工作流'
    : category.startsWith('HR') ? 'HR'
    : category.startsWith('IT') ? 'IT'
    : '客服';
  return (KNOWLEDGE_POOL[scopedCategory] || KNOWLEDGE_POOL.客服).map((item) => ({ ...item }));
}

const FLOW_POOL: Record<string, Array<{ name: string; trigger: FlowTrigger; enabled: boolean }>> = {
  客服: [
    { name: '工单自动建档', trigger: '消息触发', enabled: true },
    { name: '高情绪升级人工', trigger: '事件触发', enabled: true },
  ],
  销售: [
    { name: '新线索邮件跟进', trigger: '事件触发', enabled: true },
    { name: '合同到期提醒', trigger: '定时触发', enabled: true },
  ],
  数据: [
    { name: '日报生成', trigger: '定时触发', enabled: true },
    { name: '异常指标告警', trigger: '事件触发', enabled: true },
  ],
};

export function buildFlowRefs(category: string): FlowRef[] {
  const scopedCategory = category.startsWith('客服') ? '客服'
    : category.startsWith('销售') ? '销售'
    : category.startsWith('数据') ? '数据'
    : '客服';
  const items = FLOW_POOL[scopedCategory] || FLOW_POOL.客服;
  return items.map((item, idx) => ({
    id: `flow-${scopedCategory}-${idx}`,
    name: item.name,
    trigger: item.trigger,
    enabled: item.enabled,
  }));
}

export const DEFAULT_MEMORY_POLICY: MemoryPolicy = {
  enabled: true,
  retentionDays: 30,
  scope: 'user',
  autoSummarize: true,
};

type AgentSeed = Omit<AgentEntry, 'prompts' | 'customPrompts' | 'knowledgeRefs' | 'memoryPolicy' | 'flowRefs'>;

const SEEDS: AgentSeed[] = [
  {
    id: 'a-customer-v3', name: '客户沟通助手',
    description: '处理客户咨询、订单查询、退换货引导,自动识别情绪并升级人工。',
    category: '客服一组', owner: '张敏', tone: 'brand', status: 'published',
    version: 'v3.2', lastUpdate: '2 小时前', createdAt: '2026-08-21',
    calls: 18200, successRate: 99.62, errorRate: 0.42, avgLatencyMs: 1820, rating: 4.7,
    tags: ['客服', '订单', '情绪识别', '高频'],
    tools: toolsFromNames(['订单查询', '退换货流程', '知识检索', '情绪识别', '人工坐席', '邮件发送']),
    starred: true, visibleScope: ['公开', '部门'], dataAccess: '客户档案 · 订单系统',
    versions: [
      { version: 'v3.2', publisher: '张敏', releasedAt: '2026-09-24', current: true },
      { version: 'v3.1', publisher: '张敏', releasedAt: '2026-09-03' },
      { version: 'v3.0', publisher: '李雷', releasedAt: '2026-08-21' },
    ],
    evaluationPassRate: 96.4, evaluationRuns: 12, evaluationFailedCases: 3,
    trend: [180, 220, 260, 310, 340, 380, 420, 470, 510, 540, 580, 620],
  },
  {
    id: 'a-sales-v2', name: '销售支持',
    description: '为销售提供客户画像、报价辅助、合同条款查询与跟进建议。',
    category: '销售支持', owner: '李雷', tone: 'success', status: 'published',
    version: 'v2.7', lastUpdate: '昨天', createdAt: '2026-07-15',
    calls: 14700, successRate: 99.41, errorRate: 0.55, avgLatencyMs: 1980, rating: 4.5,
    tags: ['销售', 'CRM', '合同', '报价'],
    tools: toolsFromNames(['客户画像', 'CRM 查询', '报价引擎', '合同条款检索', '邮件发送', '日程预约']),
    starred: true, visibleScope: ['部门'], dataAccess: 'CRM · 销售订单',
    versions: [
      { version: 'v2.7', publisher: '李雷', releasedAt: '2026-09-20', current: true },
      { version: 'v2.6', publisher: '李雷', releasedAt: '2026-08-30' },
      { version: 'v2.5', publisher: '王芳', releasedAt: '2026-08-15' },
    ],
    evaluationPassRate: 93.1, evaluationRuns: 9, evaluationFailedCases: 5,
    trend: [120, 140, 160, 180, 210, 230, 250, 270, 290, 310, 330, 350],
  },
  {
    id: 'a-insight-v2', name: '数据洞察助手',
    description: '自然语言提问企业数据,自动生成 SQL、可视化与解读报告。',
    category: '数据团队', owner: '王芳', tone: 'info', status: 'published',
    version: 'v2.4', lastUpdate: '3 天前', createdAt: '2026-06-30',
    calls: 9800, successRate: 98.92, errorRate: 0.74, avgLatencyMs: 2400, rating: 4.6,
    tags: ['数据', 'SQL', '可视化', 'BI'],
    tools: toolsFromNames(['SQL 生成', '图表渲染', '指标库查询', '数据脱敏', '导出 PDF']),
    starred: false, visibleScope: ['部门'], dataAccess: '数据仓库 · 指标平台',
    versions: [
      { version: 'v2.4', publisher: '王芳', releasedAt: '2026-09-15', current: true },
      { version: 'v2.3', publisher: '王芳', releasedAt: '2026-08-25' },
      { version: 'v2.2', publisher: '周强', releasedAt: '2026-07-30' },
    ],
    evaluationPassRate: 91.8, evaluationRuns: 14, evaluationFailedCases: 7,
    trend: [80, 90, 100, 110, 120, 140, 150, 160, 170, 175, 180, 190],
  },
  {
    id: 'a-finance-v1', name: '财务问答',
    description: '回答费用报销、预算执行、税务规则等问题,支持单据 OCR 与对账。',
    category: '财务', owner: '陈晨', tone: 'purple', status: 'published',
    version: 'v1.8', lastUpdate: '今天 09:14', createdAt: '2026-04-12',
    calls: 6100, successRate: 99.81, errorRate: 0.21, avgLatencyMs: 1620, rating: 4.8,
    tags: ['财务', '报销', '税务', 'OCR'],
    tools: toolsFromNames(['OCR 单据', '报销规则', '预算查询', '对账核对', '审批中心']),
    starred: false, visibleScope: ['部门'], dataAccess: 'ERP · 报销系统',
    versions: [
      { version: 'v1.8', publisher: '陈晨', releasedAt: '2026-09-12', current: true },
      { version: 'v1.7', publisher: '陈晨', releasedAt: '2026-08-22' },
      { version: 'v1.6', publisher: '李雷', releasedAt: '2026-07-18' },
    ],
    evaluationPassRate: 97.2, evaluationRuns: 11, evaluationFailedCases: 2,
    trend: [60, 70, 75, 80, 85, 90, 95, 100, 105, 110, 115, 120],
  },
  {
    id: 'a-flow-v1', name: '工作流编排',
    description: '把重复工作配置成可追踪、可复用的工作流,支持条件分支与人工介入。',
    category: '工作流', owner: '李雷', tone: 'warn', status: 'published',
    version: 'v1.5', lastUpdate: '上周', createdAt: '2026-05-08',
    calls: 5400, successRate: 99.55, errorRate: 0.34, avgLatencyMs: 2100, rating: 4.4,
    tags: ['工作流', '自动化', '审批'],
    tools: toolsFromNames(['工作流编辑器', '触发器', '人工审批', '通知中心', '审计日志']),
    starred: false, visibleScope: ['公开'], dataAccess: '工作流引擎',
    versions: [
      { version: 'v1.5', publisher: '李雷', releasedAt: '2026-09-08', current: true },
      { version: 'v1.4', publisher: '李雷', releasedAt: '2026-08-18' },
    ],
    evaluationPassRate: 92.0, evaluationRuns: 8, evaluationFailedCases: 4,
    trend: [40, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100],
  },
  {
    id: 'a-customer-gray', name: '客户沟通助手 v4',
    description: '在 v3 基础上引入多模态订单图片识别与上下文记忆。',
    category: '客服一组', owner: '张敏', tone: 'info', status: 'graying',
    version: 'v4.0-beta', lastUpdate: '今天 10:32', createdAt: '2026-09-26',
    calls: 320, successRate: 99.10, errorRate: 0.62, avgLatencyMs: 2050, rating: 4.6,
    tags: ['客服', '多模态', '图片识别', 'Beta'],
    tools: toolsFromNames(['订单查询', '图片 OCR', '上下文记忆', '情绪识别', '人工坐席']),
    starred: false, visibleScope: ['部门'], dataAccess: '客户档案 · 订单系统',
    versions: [
      { version: 'v4.0-beta', publisher: '张敏', releasedAt: '2026-09-26', current: true },
      { version: 'v3.2', publisher: '张敏', releasedAt: '2026-09-24' },
    ],
    evaluationPassRate: 89.5, evaluationRuns: 4, evaluationFailedCases: 6,
    trend: [10, 20, 40, 80, 120, 160, 200, 240, 280, 300, 320, 340],
  },
];

export const mockAgents: AgentEntry[] = SEEDS.map((s, idx) => ({
  ...s,
  prompts: buildPrompts(s.name, s.category, s.owner),
  customPrompts: idx === 0 ? [
    {
      id: 'cdoc-faq-001',
      file: 'FAQ.md',
      label: 'FAQ',
      description: '常见问题与标准回复 · 客服高频问答',
      content: `# FAQ · 高频问答\n\n## 订单类\n- **订单号格式**:1xx-2xx-3xx 共 16 位\n- **查询路径**:订单中心 → 输入订单号 → 状态/物流\n- **修改收货地址**:订单未发货前自助,已发货需客服\n\n## 退换货类\n- 7 天无理由,质量问题 15 天\n- 已使用影响二次销售的不予退货\n- 退款 1-3 工作日到账\n\n## 发票类\n- 默认电子普通发票,可在订单页切换专票\n- 抬头修改需在开票前完成`,
    },
  ] : [],
  knowledgeRefs: buildKnowledgeRefs(s.category),
  memoryPolicy: { ...DEFAULT_MEMORY_POLICY },
  flowRefs: buildFlowRefs(s.category),
}));

export const SAMPLE_IMPORT = [
  { source: { name: '合同摘要助手', description: '快速摘要合同正文,提取关键条款', category: '法务', owner: '孙浩' }, status: 'ok' as const },
  { source: { name: '客户沟通助手', description: '处理客户咨询、订单查询', category: '客服一组', owner: '张敏' }, status: 'duplicate' as const, message: '已存在同名智能体' },
  { source: { name: '差旅助手', description: '差旅政策查询与报销引导', category: 'HR', owner: '' }, status: 'missing' as const, message: '缺少负责人字段' },
  { source: { name: '翻译小助手', description: '中英互译,保留专有名词', category: 'IT', owner: '周强' }, status: 'ok' as const },
  { source: { name: '销售支持', description: '客户画像、报价辅助、合同查询', category: '销售支持', owner: '李雷' }, status: 'duplicate' as const, message: '已存在同名智能体' },
];

export const SAMPLE_IMPORT_ZIP = [
  { source: { name: '差旅助手', description: '差旅政策查询与报销引导', category: 'HR', owner: '赵琳' }, status: 'ok' as const },
  { source: { name: '差旅助手 v2', description: '差旅审批流接入与机票比价', category: 'HR', owner: '赵琳' }, status: 'ok' as const },
  { source: { name: '差旅助手', description: '已存在同名', category: 'HR', owner: '赵琳' }, status: 'duplicate' as const, message: '已存在同名智能体' },
  { source: { name: '会议纪要助手', description: '实时转写 + 待办抽取', category: 'IT', owner: '周强' }, status: 'ok' as const },
  { source: { name: '客户回访', description: '', category: '客服一组', owner: '' }, status: 'missing' as const, message: '缺少描述与负责人' },
];

export function getLifecycleMetrics(list: AgentEntry[]) {
  return {
    total: list.length,
    published: list.filter((a) => a.status === 'published').length,
    graying: list.filter((a) => a.status === 'graying').length,
    draft: list.filter((a) => a.status === 'draft').length,
    pending: list.filter((a) => a.status === 'pending').length,
    retired: list.filter((a) => a.status === 'retired').length,
    totalCalls: list.reduce((s, a) => s + a.calls, 0),
  };
}
