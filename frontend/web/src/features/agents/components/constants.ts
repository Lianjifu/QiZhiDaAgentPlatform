/**
 * 管理侧「智能体工作台」常量 — Tab/状态徽章/排序/导出字段/导入格式/drawer nav/Prompt 文档/记忆/工作流触发器。
 */
import {
  Activity, AlertTriangle, Beaker, BookOpen, Brain, ChevronDown, ChevronLeft, ChevronRight, CheckCircle2, CheckSquare, Clock, Copy, Download, Edit3, FileJson, FileSpreadsheet, FileText, FolderTree, GitBranch, History, Info, Layers, MoreVertical, Play, Plus, RotateCcw, Save, Search, ShieldCheck, Sparkles, Square, Star, Tag, Timer, Trash2, TrendingUp, Upload, Workflow, X,
} from 'lucide-react';
import type { Tone, Status, TabId, SortKey, DrawerPanel, PromptKey, ExportField, ExportFormat, ExportScope, MemoryRetention, MemoryScope, FlowTrigger, ImportExtension, VisibleScope, DeletePayload } from '../schema';

export {
  Activity, AlertTriangle, Beaker, BookOpen, Brain, ChevronDown, ChevronLeft, ChevronRight, CheckCircle2, CheckSquare, Clock, Copy, Download, Edit3, FileJson, FileSpreadsheet, FileText, FolderTree, GitBranch, History, Info, Layers, MoreVertical, Play, Plus, RotateCcw, Save, Search, ShieldCheck, Sparkles, Square, Star, Tag, Timer, Trash2, TrendingUp, Upload, Workflow, X,
};

export const TABS: Array<{ id: TabId; label: string }> = [
  { id: 'all', label: '全部' },
  { id: 'draft', label: '草稿' },
  { id: 'pending', label: '待审核' },
  { id: 'graying', label: '灰度中' },
  { id: 'published', label: '已发布' },
  { id: 'retired', label: '已下线' },
];

export const SCENES = ['全部场景', '客服', '销售', '数据', '财务', '工作流', 'HR', 'IT'];

export const toneClass: Record<Tone, string> = {
  brand: 'bg-[var(--brand-light)] text-[var(--brand)]',
  info: 'bg-[var(--info-bg)] text-[var(--info)]',
  success: 'bg-[var(--success-bg)] text-[var(--success)]',
  warn: 'bg-[var(--warning-bg)] text-[var(--warning)]',
  danger: 'bg-[var(--danger-bg)] text-[var(--danger)]',
  purple: 'bg-[var(--purple-bg)] text-[var(--purple)]',
};

export const statusBadge: Record<Status, { label: string; className: string; dot: string }> = {
  draft: { label: '草稿', className: 'bg-[var(--bg-elevated)] text-[var(--text-secondary)]', dot: 'bg-[var(--text-muted)]' },
  pending: { label: '待审核', className: 'bg-[var(--warning-bg)] text-[var(--warning)]', dot: 'bg-[var(--warning)]' },
  graying: { label: '灰度中', className: 'bg-[var(--info-bg)] text-[var(--info)]', dot: 'bg-[var(--info)]' },
  published: { label: '已发布', className: 'bg-[var(--success-bg)] text-[var(--success)]', dot: 'bg-[var(--success)]' },
  retired: { label: '已下线', className: 'bg-[var(--danger-bg)] text-[var(--danger)]', dot: 'bg-[var(--danger)]' },
};

export const SORT_OPTIONS: Array<{ id: SortKey; label: string }> = [
  { id: 'calls', label: '调用量' },
  { id: 'updated', label: '最近更新' },
  { id: 'rating', label: '评分' },
  { id: 'name', label: '名称' },
];

export const EXPORT_FIELDS: Array<{ id: ExportField; label: string }> = [
  { id: 'meta', label: '元信息' },
  { id: 'prompt', label: 'Prompt' },
  { id: 'skills', label: '技能' },
  { id: 'knowledge', label: '知识' },
  { id: 'memory', label: '记忆' },
  { id: 'flow', label: '工作流' },
];

export const IMPORT_FORMATS: Array<{ ext: ImportExtension; label: string; description: string }> = [
  { ext: 'json', label: 'JSON', description: '结构化数组,字段一一映射' },
  { ext: 'csv', label: 'CSV', description: '表格导入,首行为表头' },
  { ext: 'yaml', label: 'YAML', description: 'YAML 列表,支持注释' },
  { ext: 'zip', label: 'ZIP', description: '压缩包,可包含多个文件' },
];

export const DEFAULT_EXPORT_FIELDS: Record<ExportField, boolean> = {
  meta: true,
  prompt: true,
  skills: true,
  knowledge: true,
  memory: true,
  flow: false,
};

export const PROMPT_DOCS: Array<{ key: PromptKey; file: string; label: string; description: string; placeholder: string; targetChars: number }> = [
  { key: 'prompt', file: 'PROMPT.md', label: 'PROMPT', description: '主提示词 · 决定智能体的任务目标与输出格式', placeholder: '# 主提示词\n\n## 任务目标\n\n## 输出约束\n\n## 边界\n', targetChars: 1500 },
  { key: 'soul', file: 'SOUL.md', label: 'SOUL', description: '人格与价值观 · 语气、立场、行为边界', placeholder: '# 人格\n\n## 人格定位\n\n## 立场\n\n## 行为边界\n', targetChars: 1200 },
  { key: 'agents', file: 'AGENTS.md', label: 'AGENTS', description: '子智能体协作 · 拆分任务、转发与回传结果', placeholder: '# 子智能体\n\n## 协作角色\n\n## 任务编排\n\n## 回传规范\n', targetChars: 1000 },
  { key: 'user', file: 'USER.md', label: 'USER', description: '用户画像 · 行业、角色、偏好与上下文', placeholder: '# 用户画像\n\n## 默认画像\n\n## 偏好\n\n## 上下文\n', targetChars: 1000 },
  { key: 'tools', file: 'TOOLS.md', label: 'TOOLS', description: '工具说明 · Skill / Tool / MCP 调用意图', placeholder: '# 工具\n\n## 工具调用原则\n\n## 工具分类\n\n## 边界\n', targetChars: 1200 },
];

export const PROMPT_SNIPPETS: Record<PromptKey, Array<{ name: string; body: string }>> = {
  prompt: [
    { name: '任务目标', body: '## 任务目标\n- \n' },
    { name: '输出约束', body: '## 输出约束\n- 使用 Markdown,首行说明结论\n- 关键判断附上数据/条款来源\n- 不确定时说明限制与下一步建议\n' },
    { name: '边界', body: '## 边界\n- 仅回答与本职相关的问题\n- 不代替人工决策的关键审批\n- 涉及个人敏感信息时脱敏后再输出\n' },
  ],
  soul: [
    { name: '人格定位', body: '## 人格定位\n- 语气专业、稳定,不夸张也不敷衍\n- 面对冲突先承认事实,再给出建议\n' },
    { name: '立场', body: '## 立场\n- 真实性优于流畅性\n- 不确定时坦诚,不编造数据\n- 拒绝在不熟悉的领域硬答\n' },
    { name: '行为边界', body: '## 行为边界\n- 不冒充身份(不假装是真人)\n- 不提供违法、违规、医疗/法律终局判断\n' },
  ],
  agents: [
    { name: '协作角色', body: '## 协作角色\n- researcher · 资料检索与事实核对\n- writer · 长文档撰写与润色\n- reviewer · 风险与合规复核\n' },
    { name: '任务编排', body: '## 任务编排\n1. 接收请求,定位问题类型\n2. 视情况分发给 researcher / writer\n3. 复杂产出交 reviewer 复核\n' },
  ],
  user: [
    { name: '默认画像', body: '## 默认画像\n- 企业内部员工\n- 默认中文沟通\n- 时间敏感\n' },
    { name: '偏好', body: '## 偏好\n- 喜欢结构化要点 + 简短解释\n- 关键数字与日期会再次核对\n' },
  ],
  tools: [
    { name: '调用原则', body: '## 调用原则\n- 只在确实需要事实/动作时调用\n- 单次调用最小化\n- 调用失败需要重试或显式告知\n' },
    { name: '工具分类', body: '## 工具分类\n- 查询类:订单 / 客户 / 知识 / 指标\n- 动作类:发送邮件 / 创建工单 / 触发工作流\n- 审计类:操作前需复核,失败要回滚\n' },
  ],
};

export const DOCUMENT_TARGET_LIMITS = { soft: 1.0, warn: 1.4, danger: 1.8 };

export const MEMORY_RETENTION_OPTIONS: MemoryRetention[] = [7, 30, 90, 365];

export const MEMORY_SCOPE_OPTIONS: Array<{ value: MemoryScope; label: string; description: string }> = [
  { value: 'session', label: '单次会话', description: '随对话结束自动清除' },
  { value: 'user', label: '用户级', description: '同一用户跨会话保留' },
  { value: 'tenant', label: '租户级', description: '团队内共享上下文' },
];

export const FLOW_TRIGGERS: FlowTrigger[] = ['消息触发', '定时触发', '事件触发', '手动触发'];

export const DRAWER_NAV_ITEMS: Array<{ id: DrawerPanel; label: string; icon: typeof Activity }> = [
  { id: 'basic', label: '基本信息', icon: BookOpen },
  { id: 'prompt', label: '提示词', icon: FileText },
  { id: 'skills', label: '技能', icon: Layers },
  { id: 'knowledge', label: '知识', icon: FolderTree },
  { id: 'memory', label: '记忆', icon: Brain },
  { id: 'flow', label: '工作流', icon: Workflow },
  { id: 'versions', label: '版本', icon: GitBranch },
  { id: 'evaluation', label: '评测', icon: Beaker },
  { id: 'permission', label: '权限', icon: ShieldCheck },
];

export type { Tone, Status, TabId, SortKey, DrawerPanel, PromptKey, ExportField, ExportFormat, ExportScope, VisibleScope, DeletePayload };
