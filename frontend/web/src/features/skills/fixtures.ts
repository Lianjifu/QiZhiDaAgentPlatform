/**
 * 管理侧 fixtures — 与原 AdminSkills.tsx INITIAL_SKILLS 一一对应,
 * 测试通过 seedPageQueryData 注入（运行时不再有 mock 后端 ✓）。
 */
import type { Skill, TemplateSeed } from './schema';

export const mockAdminSkills: Skill[] = [
  {
    id: 'skill-summary',
    name: '资料摘要助手',
    description: '把长文档提炼成结构清晰的重点、结论和行动项,适合会议准备与研究整理。',
    type: 'Skill', owner: '知识工作台', status: 'published', version: 'v2.3', lastUpdate: '今天 09:14',
    calls: 18420, successRate: 99.62, errorRate: 0.42, avgLatencyMs: 1480, rating: 4.7,
    risk: 'low', needConfirm: false, visibleScope: ['公开', '部门'], tags: ['整理', '写作'], starred: true,
    inputSchema: [
      { name: 'document', type: 'string', required: true, description: '文档全文或文件引用' },
      { name: 'focus', type: 'string', required: false, description: '希望突出的角度' },
    ],
    outputSchema: [
      { name: 'summary', type: 'string', required: true, description: '不超过 200 字的摘要' },
      { name: 'actions', type: 'array', required: false, description: '建议的行动项' },
    ],
    versions: [
      { version: 'v2.3', publisher: '张敏', releasedAt: '2026-09-20', current: true },
      { version: 'v2.2', publisher: '张敏', releasedAt: '2026-08-28' },
      { version: 'v2.1', publisher: '李雷', releasedAt: '2026-07-15' },
    ],
    trend: [120, 140, 160, 180, 210, 210, 280, 320, 360, 400, 440, 480],
    usedByAgents: ['客户沟通助手', '销售支持', '会议纪要助手'],
    auditLog: [
      { time: '今天 09:14', actor: '张敏', action: '发布 v2.3,补充行动项输出' },
      { time: '昨天 17:22', actor: '张敏', action: '调整 focus 字段描述' },
      { time: '2026-09-01', actor: '系统', action: '自动回归通过' },
    ],
  },
  {
    id: 'skill-followup',
    name: '客户跟进建议',
    description: '根据客户沟通记录生成下一步跟进建议与回复草稿,辅助销售与客户成功。',
    type: 'Skill', owner: '销售支持团队', status: 'published', version: 'v1.7', lastUpdate: '昨天 17:22',
    calls: 9320, successRate: 99.41, errorRate: 0.55, avgLatencyMs: 1620, rating: 4.5,
    risk: 'medium', needConfirm: true, visibleScope: ['部门'], tags: ['客户', '销售'], starred: false,
    inputSchema: [
      { name: 'context', type: 'string', required: true, description: '历史沟通记录或客户问题' },
      { name: 'goal', type: 'string', required: false, description: '本次跟进目标' },
    ],
    outputSchema: [
      { name: 'reply', type: 'string', required: true, description: '回复草稿' },
      { name: 'nextStep', type: 'array', required: true, description: '建议的后续步骤' },
    ],
    versions: [
      { version: 'v1.7', publisher: '李雷', releasedAt: '2026-09-18', current: true },
      { version: 'v1.6', publisher: '李雷', releasedAt: '2026-08-30' },
    ],
    trend: [80, 95, 110, 125, 140, 155, 170, 185, 200, 215, 230, 245],
    usedByAgents: ['销售支持'],
    auditLog: [
      { time: '昨天 17:22', actor: '李雷', action: '调整 nextStep 输出顺序' },
      { time: '2026-09-01', actor: '系统', action: '自动回归通过' },
    ],
  },
  {
    id: 'skill-meeting',
    name: '会议纪要整理',
    description: '提取会议中的决定、负责人与待办时间,生成可追踪纪要与待办列表。',
    type: 'Skill', owner: '运营支持团队', status: 'graying', version: 'v1.2-beta', lastUpdate: '今天 10:32',
    calls: 1240, successRate: 98.92, errorRate: 0.74, avgLatencyMs: 1820, rating: 4.4,
    risk: 'low', needConfirm: false, visibleScope: ['部门'], tags: ['会议', '协作'], starred: false,
    inputSchema: [
      { name: 'transcript', type: 'string', required: true, description: '会议转写文本' },
      { name: 'language', type: 'string', required: false, description: '语言代码,默认 zh' },
    ],
    outputSchema: [
      { name: 'summary', type: 'string', required: true, description: '会议摘要' },
      { name: 'todos', type: 'array', required: true, description: '待办列表' },
    ],
    versions: [
      { version: 'v1.2-beta', publisher: '王芳', releasedAt: '2026-09-26', current: true },
      { version: 'v1.1', publisher: '王芳', releasedAt: '2026-08-15' },
    ],
    trend: [10, 20, 40, 80, 120, 160, 200, 240, 280, 300, 320, 340],
    usedByAgents: ['会议纪要助手'],
    auditLog: [
      { time: '今天 10:32', actor: '王芳', action: '进入灰度,放量 10%' },
    ],
  },
  {
    id: 'skill-draft',
    name: '差旅助手(草稿)',
    description: '差旅政策查询与报销引导,支持出差申请草稿生成,目前仍在完善字段定义。',
    type: 'Skill', owner: 'HR', status: 'draft', version: 'draft', lastUpdate: '今天 11:08',
    calls: 0, successRate: 0, errorRate: 0, avgLatencyMs: 0, rating: 0,
    risk: 'low', needConfirm: false, visibleScope: ['部门'], tags: ['差旅', 'HR'], starred: false,
    inputSchema: [
      { name: 'employee', type: 'object', required: true, description: '员工基本信息' },
      { name: 'trip', type: 'object', required: true, description: '行程描述' },
    ],
    outputSchema: [
      { name: 'draft', type: 'string', required: true, description: '申请单草稿' },
    ],
    versions: [],
    trend: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    usedByAgents: [],
    auditLog: [
      { time: '今天 11:08', actor: '赵琳', action: '从模板加入草稿' },
    ],
  },
  {
    id: 'tool-calendar',
    name: '日历安排工具',
    description: '在确认后帮助查找空闲时间并创建日程安排,适用于约会、排期、提醒设置。',
    type: 'Tool', owner: '平台工具', status: 'published', version: 'v3.1', lastUpdate: '今天 09:14',
    calls: 14760, successRate: 99.81, errorRate: 0.21, avgLatencyMs: 1180, rating: 4.8,
    risk: 'medium', needConfirm: true, visibleScope: ['公开', '部门'], tags: ['日历', '排期'], starred: true,
    inputSchema: [
      { name: 'attendees', type: 'array', required: true, description: '参与人列表' },
      { name: 'duration', type: 'number', required: true, description: '会议时长(分钟)' },
      { name: 'window', type: 'object', required: false, description: '候选时间窗口' },
    ],
    outputSchema: [
      { name: 'slot', type: 'object', required: true, description: '候选时段' },
      { name: 'eventUrl', type: 'string', required: false, description: '创建后的事件链接' },
    ],
    versions: [
      { version: 'v3.1', publisher: '陈晨', releasedAt: '2026-09-12', current: true },
      { version: 'v3.0', publisher: '陈晨', releasedAt: '2026-08-22' },
    ],
    trend: [200, 240, 280, 320, 360, 400, 440, 480, 520, 560, 600, 640],
    usedByAgents: ['客户沟通助手', '销售支持'],
    auditLog: [
      { time: '今天 09:14', actor: '陈晨', action: '发布 v3.1,优化候选时段排序' },
    ],
  },
  {
    id: 'tool-spreadsheet',
    name: '表格分析工具',
    description: '读取授权的表格内容,完成统计、筛选和摘要,支持导出 PDF / 图表。',
    type: 'Tool', owner: '平台工具', status: 'published', version: 'v2.6', lastUpdate: '昨天',
    calls: 11240, successRate: 99.55, errorRate: 0.34, avgLatencyMs: 1980, rating: 4.6,
    risk: 'medium', needConfirm: true, visibleScope: ['部门'], tags: ['表格', '分析'], starred: false,
    inputSchema: [
      { name: 'fileId', type: 'string', required: true, description: '表格文件 ID' },
      { name: 'analysisType', type: 'string', required: true, description: '分析维度' },
    ],
    outputSchema: [
      { name: 'summary', type: 'string', required: true, description: '摘要' },
      { name: 'chart', type: 'object', required: false, description: '可视化图表数据' },
    ],
    versions: [
      { version: 'v2.6', publisher: '王芳', releasedAt: '2026-09-15', current: true },
      { version: 'v2.5', publisher: '王芳', releasedAt: '2026-08-25' },
    ],
    trend: [100, 120, 140, 160, 180, 200, 220, 240, 260, 280, 300, 320],
    usedByAgents: ['数据洞察助手', '销售支持'],
    auditLog: [
      { time: '昨天', actor: '王芳', action: '调整 chart 输出格式' },
    ],
  },
  {
    id: 'tool-mailer',
    name: '邮件发送工具',
    description: '在授权邮箱范围内发送邮件,支持模板、附件与确认提示。',
    type: 'Tool', owner: '平台工具', status: 'retired', version: 'v1.x', lastUpdate: '2026-08-10',
    calls: 0, successRate: 0, errorRate: 0, avgLatencyMs: 0, rating: 3.6,
    risk: 'high', needConfirm: true, visibleScope: ['公开'], tags: ['邮件'], starred: false,
    inputSchema: [
      { name: 'to', type: 'array', required: true, description: '收件人列表' },
      { name: 'subject', type: 'string', required: true, description: '邮件主题' },
      { name: 'body', type: 'string', required: true, description: '邮件正文' },
    ],
    outputSchema: [
      { name: 'messageId', type: 'string', required: true, description: '邮件消息 ID' },
    ],
    versions: [
      { version: 'v1.4', publisher: '陈晨', releasedAt: '2026-03-12', current: true },
      { version: 'v1.3', publisher: '陈晨', releasedAt: '2025-12-22' },
    ],
    trend: [120, 80, 40, 20, 10, 5, 0, 0, 0, 0, 0, 0],
    usedByAgents: [],
    auditLog: [
      { time: '2026-08-10', actor: '陈晨', action: '下线旧版邮件发送,迁移至 v3' },
    ],
  },
  {
    id: 'mcp-crm',
    name: '客户系统连接',
    description: '通过受控连接查询客户资料与服务记录,不直接修改数据。',
    type: 'MCP', owner: '客户成功团队', status: 'published', version: 'v2.0', lastUpdate: '今天 09:14',
    calls: 7560, successRate: 99.74, errorRate: 0.18, avgLatencyMs: 1320, rating: 4.7,
    risk: 'medium', needConfirm: true, visibleScope: ['部门'], tags: ['MCP', '客户'], starred: true,
    inputSchema: [
      { name: 'query', type: 'string', required: true, description: '客户名称或编号' },
      { name: 'fields', type: 'array', required: false, description: '指定返回字段' },
    ],
    outputSchema: [
      { name: 'records', type: 'array', required: true, description: '客户记录' },
    ],
    versions: [
      { version: 'v2.0', publisher: '李雷', releasedAt: '2026-09-08', current: true },
      { version: 'v1.8', publisher: '李雷', releasedAt: '2026-08-18' },
    ],
    trend: [80, 90, 100, 110, 120, 140, 150, 160, 170, 175, 180, 190],
    usedByAgents: ['客户沟通助手', '销售支持'],
    auditLog: [
      { time: '今天 09:14', actor: '李雷', action: '发布 v2.0,新增 fields 参数' },
    ],
  },
  {
    id: 'mcp-drive',
    name: '团队云盘连接',
    description: '在授权范围内查找团队共享资料和最近更新内容,只读不写。',
    type: 'MCP', owner: '平台连接', status: 'graying', version: 'v1.3-beta', lastUpdate: '昨天',
    calls: 320, successRate: 98.10, errorRate: 1.42, avgLatencyMs: 1620, rating: 4.1,
    risk: 'low', needConfirm: false, visibleScope: ['部门'], tags: ['MCP', '文件'], starred: false,
    inputSchema: [
      { name: 'keyword', type: 'string', required: true, description: '关键词或文件名' },
      { name: 'scope', type: 'string', required: false, description: '搜索范围' },
    ],
    outputSchema: [
      { name: 'files', type: 'array', required: true, description: '匹配的文件' },
    ],
    versions: [
      { version: 'v1.3-beta', publisher: '周强', releasedAt: '2026-09-25', current: true },
    ],
    trend: [0, 10, 20, 30, 60, 90, 120, 140, 160, 170, 175, 180],
    usedByAgents: ['团队协作助手'],
    auditLog: [
      { time: '昨天', actor: '周强', action: '进入灰度,放量 5%' },
    ],
  },
];

export const mockSkillTemplates: TemplateSeed[] = [
  { id: 'tpl-doc-summary', name: '文档摘要', description: '提炼长文档重点、结论与行动项', type: 'Skill', owner: '知识工作台', iconKey: 'FileText', risk: 'low', needConfirm: false, tags: ['整理', '写作'], inputExample: [{ name: 'document', type: 'string', required: true, description: '文档全文' }], outputExample: [{ name: 'summary', type: 'string', required: true, description: '摘要' }, { name: 'actions', type: 'array', required: false, description: '行动项' }] },
  { id: 'tpl-meeting-note', name: '会议纪要', description: '提取决定、负责人与待办时间', type: 'Skill', owner: '运营支持团队', iconKey: 'MessageSquare', risk: 'low', needConfirm: false, tags: ['会议'], inputExample: [{ name: 'transcript', type: 'string', required: true, description: '会议转写' }], outputExample: [{ name: 'todos', type: 'array', required: true, description: '待办列表' }] },
  { id: 'tpl-report-write', name: '报告撰写', description: '根据数据点生成结构化报告', type: 'Skill', owner: '运营支持团队', iconKey: 'FileSpreadsheet', risk: 'low', needConfirm: false, tags: ['报告'], inputExample: [{ name: 'data', type: 'object', required: true, description: '数据点' }], outputExample: [{ name: 'report', type: 'string', required: true, description: '报告' }] },
  { id: 'tpl-followup', name: '跟进建议', description: '基于沟通记录生成下一步建议', type: 'Skill', owner: '销售支持团队', iconKey: 'MessageSquare', risk: 'medium', needConfirm: true, tags: ['客户'], inputExample: [{ name: 'context', type: 'string', required: true, description: '沟通记录' }], outputExample: [{ name: 'reply', type: 'string', required: true, description: '回复草稿' }] },
  { id: 'tpl-tool-calendar', name: '日历操作', description: '查找空闲时间,创建日程安排', type: 'Tool', owner: '平台工具', iconKey: 'Clock', risk: 'medium', needConfirm: true, tags: ['日历'], inputExample: [{ name: 'attendees', type: 'array', required: true, description: '参与人' }, { name: 'duration', type: 'number', required: true, description: '时长(分钟)' }], outputExample: [{ name: 'slot', type: 'object', required: true, description: '候选时段' }] },
  { id: 'tpl-tool-spreadsheet', name: '表格分析', description: '读取授权表格,生成统计与摘要', type: 'Tool', owner: '平台工具', iconKey: 'FileSpreadsheet', risk: 'medium', needConfirm: true, tags: ['表格'], inputExample: [{ name: 'fileId', type: 'string', required: true, description: '文件 ID' }], outputExample: [{ name: 'summary', type: 'string', required: true, description: '摘要' }] },
  { id: 'tpl-tool-mailer', name: '邮件发送', description: '在授权邮箱内发送邮件', type: 'Tool', owner: '平台工具', iconKey: 'MessageSquare', risk: 'high', needConfirm: true, tags: ['邮件'], inputExample: [{ name: 'to', type: 'array', required: true, description: '收件人' }, { name: 'subject', type: 'string', required: true, description: '主题' }], outputExample: [{ name: 'messageId', type: 'string', required: true, description: '消息 ID' }] },
  { id: 'tpl-tool-database', name: '数据库查询', description: '对授权数据源执行只读 SQL', type: 'Tool', owner: '平台工具', iconKey: 'Database', risk: 'high', needConfirm: true, tags: ['数据'], inputExample: [{ name: 'sql', type: 'string', required: true, description: 'SQL 语句' }], outputExample: [{ name: 'rows', type: 'array', required: true, description: '查询结果' }] },
  { id: 'tpl-tool-webhook', name: 'Webhook 触发', description: '调用外部 HTTP 接口', type: 'Tool', owner: '平台工具', iconKey: 'Webhook', risk: 'high', needConfirm: true, tags: ['集成'], inputExample: [{ name: 'url', type: 'string', required: true, description: '回调地址' }, { name: 'payload', type: 'object', required: true, description: '请求体' }], outputExample: [{ name: 'status', type: 'number', required: true, description: 'HTTP 状态码' }] },
  { id: 'tpl-mcp-crm', name: '客户系统', description: '查询客户资料与服务记录,只读', type: 'MCP', owner: '客户成功团队', iconKey: 'Database', risk: 'medium', needConfirm: true, tags: ['客户'], inputExample: [{ name: 'query', type: 'string', required: true, description: '客户编号' }], outputExample: [{ name: 'records', type: 'array', required: true, description: '客户记录' }] },
  { id: 'tpl-mcp-drive', name: '团队云盘', description: '在授权范围内查找共享资料', type: 'MCP', owner: '平台连接', iconKey: 'Database', risk: 'low', needConfirm: false, tags: ['文件'], inputExample: [{ name: 'keyword', type: 'string', required: true, description: '关键词' }], outputExample: [{ name: 'files', type: 'array', required: true, description: '匹配文件' }] },
  { id: 'tpl-mcp-github', name: 'GitHub', description: '查询仓库、Issue 与 PR', type: 'MCP', owner: '平台连接', iconKey: 'Globe', risk: 'medium', needConfirm: true, tags: ['代码'], inputExample: [{ name: 'repo', type: 'string', required: true, description: '仓库名' }], outputExample: [{ name: 'issues', type: 'array', required: true, description: 'Issue 列表' }] },
  { id: 'tpl-mcp-finance', name: '财务系统', description: '查询预算与报销,只读', type: 'MCP', owner: '财务支持', iconKey: 'Database', risk: 'high', needConfirm: true, tags: ['财务'], inputExample: [{ name: 'period', type: 'string', required: true, description: '期间' }], outputExample: [{ name: 'budget', type: 'object', required: true, description: '预算数据' }] },
];