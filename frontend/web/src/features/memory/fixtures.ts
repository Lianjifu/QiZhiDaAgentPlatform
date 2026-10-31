/**
 * AdminMemory fixtures — 10 L1 sessions / 14 L2 facts / 12 团队知识 / 8 promotions / 1 policy。
 *
 * ⚠️ **团队知识来自 knowledge** ✓ —— L3 表退役了 ✓（M-47 ✓）→ 这里只是
 * **记忆页视角** ✓（同一份文档 ✓ —— `kbId` 指向它所属的知识库 ✓）。
 */
import type {
  L1Session, L2Fact, L3Entry, MemoryTrend, PromotionEvent, RetentionPolicy,
} from './schema';

export const mockL1Sessions: L1Session[] = [
  { id: 's-1', userName: '张文佳', agentName: '客户沟通助手', bufferSize: 24, tokensUsed: 4820, ttlMinutes: 60, ttlRemainMin: 38, status: 'active', lastFlush: '今天 15:48', startedAt: '今天 15:00' },
  { id: 's-2', userName: '李楠', agentName: '产品调研助手', bufferSize: 18, tokensUsed: 3140, ttlMinutes: 60, ttlRemainMin: 12, status: 'active', lastFlush: '今天 15:42', startedAt: '今天 14:50' },
  { id: 's-3', userName: '王晓阳', agentName: '数据洞察助手', bufferSize: 32, tokensUsed: 6180, ttlMinutes: 90, ttlRemainMin: 4, status: 'active', lastFlush: '今天 15:30', startedAt: '今天 14:20' },
  { id: 's-4', userName: '陈雨晴', agentName: '智能体工程助手', bufferSize: 12, tokensUsed: 1980, ttlMinutes: 60, ttlRemainMin: 0, status: 'paused', lastFlush: '今天 15:00', startedAt: '今天 14:30' },
  { id: 's-5', userName: '赵泽宇', agentName: '客户沟通助手', bufferSize: 28, tokensUsed: 5240, ttlMinutes: 60, ttlRemainMin: 22, status: 'active', lastFlush: '今天 15:50', startedAt: '今天 15:12' },
  { id: 's-6', userName: '黄一凡', agentName: '合同模板助手', bufferSize: 8, tokensUsed: 1240, ttlMinutes: 30, ttlRemainMin: 0, status: 'expired', lastFlush: '今天 14:00', startedAt: '今天 13:50' },
  { id: 's-7', userName: '周欣然', agentName: '产品调研助手', bufferSize: 16, tokensUsed: 2680, ttlMinutes: 60, ttlRemainMin: 16, status: 'active', lastFlush: '今天 15:38', startedAt: '今天 14:48' },
  { id: 's-8', userName: '吴梓涵', agentName: '智能体工程助手', bufferSize: 22, tokensUsed: 4180, ttlMinutes: 90, ttlRemainMin: 48, status: 'active', lastFlush: '今天 15:46', startedAt: '今天 14:32' },
  { id: 's-9', userName: '张文佳', agentName: '数据洞察助手', bufferSize: 14, tokensUsed: 2240, ttlMinutes: 60, ttlRemainMin: 0, status: 'expired', lastFlush: '今天 14:30', startedAt: '今天 13:30' },
  { id: 's-10', userName: '李楠', agentName: '客户沟通助手', bufferSize: 19, tokensUsed: 3320, ttlMinutes: 60, ttlRemainMin: 28, status: 'active', lastFlush: '今天 15:46', startedAt: '今天 15:08' },
];

export const mockL2Facts: L2Fact[] = [
  { id: 'f-1', userName: '张文佳', key: '答复风格', value: '喜欢精简答复,3 行内给结论', category: 'preference', sourceSession: 's-1', confidence: 0.96, lastUsed: '今天 15:40', promotedAt: '2 天前', status: 'confirmed', promotedToL3: false, usageHistory: ['今天 15:40', '今天 14:10', '昨天 16:00', '昨天 10:20', '3 天前', '4 天前', '5 天前'] },
  { id: 'f-2', userName: '张文佳', key: '工作领域', value: '负责客户成功团队,日常对接 SaaS 客户', category: 'fact', sourceSession: 's-1', confidence: 0.92, lastUsed: '今天 14:20', promotedAt: '1 周前', status: 'confirmed', promotedToL3: false, usageHistory: ['今天 14:20', '昨天 15:00', '2 天前', '3 天前', '4 天前', '1 周前', '2 周前'] },
  { id: 'f-3', userName: '李楠', key: '禁用领域', value: '不讨论价格折扣细节,需转人工', category: 'context', sourceSession: 's-2', confidence: 0.98, lastUsed: '今天 15:30', promotedAt: '昨天', status: 'confirmed', promotedToL3: true, usageHistory: ['今天 15:30', '今天 11:20', '昨天', '2 天前', '4 天前', '1 周前', '2 周前'] },
  { id: 'f-4', userName: '王晓阳', key: '数据单位偏好', value: '金额一律使用 ¥,保留两位小数', category: 'preference', sourceSession: 's-3', confidence: 0.89, lastUsed: '今天 15:00', promotedAt: '3 天前', status: 'confirmed', promotedToL3: false },
  { id: 'f-5', userName: '王晓阳', key: '关注指标', value: '日活、留存、转化漏斗', category: 'fact', sourceSession: 's-3', confidence: 0.84, lastUsed: '今天 14:50', promotedAt: '今天', status: 'pending', promotedToL3: false },
  { id: 'f-6', userName: '陈雨晴', key: '技术栈', value: '主要使用 TypeScript + PostgreSQL', category: 'fact', sourceSession: 's-4', confidence: 0.94, lastUsed: '今天 14:10', promotedAt: '1 周前', status: 'confirmed', promotedToL3: true, usageHistory: ['今天 14:10', '昨天', '2 天前', '4 天前', '6 天前', '1 周前', '2 周前'] },
  { id: 'f-7', userName: '陈雨晴', key: '代码风格', value: '函数式优先,避免 class', category: 'style', sourceSession: 's-4', confidence: 0.81, lastUsed: '昨天', promotedAt: '3 天前', status: 'confirmed', promotedToL3: false },
  { id: 'f-8', userName: '赵泽宇', key: '项目代号', value: '项目代号 "海燕" = Q4 发布', category: 'context', sourceSession: 's-5', confidence: 0.78, lastUsed: '今天 15:20', promotedAt: '今天', status: 'pending', promotedToL3: false },
  { id: 'f-9', userName: '周欣然', key: '报告格式', value: '周报需要带图表,Markdown 输出', category: 'preference', sourceSession: 's-7', confidence: 0.92, lastUsed: '今天 15:00', promotedAt: '上周', status: 'confirmed', promotedToL3: false },
  { id: 'f-10', userName: '吴梓涵', key: '调试偏好', value: '先看日志再读源码', category: 'style', sourceSession: 's-8', confidence: 0.88, lastUsed: '今天 14:00', promotedAt: '4 天前', status: 'confirmed', promotedToL3: false },
  { id: 'f-11', userName: '张文佳', key: '联系人偏好', value: '客户问技术问题直接转 @李楠', category: 'context', sourceSession: 's-1', confidence: 0.76, lastUsed: '今天 15:30', promotedAt: '今天', status: 'pending', promotedToL3: false },
  { id: 'f-12', userName: '李楠', key: '调研方法', value: '先看公开数据,再做 5 客户访谈', category: 'style', sourceSession: 's-10', confidence: 0.83, lastUsed: '今天 14:00', promotedAt: '2 天前', status: 'confirmed', promotedToL3: false },
  { id: 'f-13', userName: '王晓阳', key: '看板结构', value: '团队使用 4 列看板:待办/进行/复审/完成', category: 'fact', sourceSession: 's-3', confidence: 0.71, lastUsed: '上周', promotedAt: '2 周前', status: 'retired', promotedToL3: false },
  { id: 'f-14', userName: '赵泽宇', key: '语言偏好', value: '回复中文优先,专有名词保留英文', category: 'preference', sourceSession: 's-5', confidence: 0.94, lastUsed: '今天 15:00', promotedAt: '5 天前', status: 'confirmed', promotedToL3: true },
];

export const mockL3Entries: L3Entry[] = [
  { id: 'k-1', team: '产品团队', kbId: 'kb-产品团队', title: '业务术语对照表', summary: '内部术语、缩写、产品代号的官方解释,所有 Agent 引用时优先检索。', category: '术语表', chunks: 1280, updatedAt: '本周', contributor: '产品团队', status: 'published', promotedFromL2Ids: ['f-2'] },
  { id: 'k-2', team: '客服团队', kbId: 'kb-客服团队', title: '价格折扣规则', summary: '标准折扣、审批阈值、对外口径,所有客服 Agent 必须遵循。', category: '流程', chunks: 842, updatedAt: '今天', contributor: '客服一组', status: 'published', promotedFromL2Ids: ['f-3'] },
  { id: 'k-3', team: '研发团队', kbId: 'kb-研发团队', title: 'API 设计规范', summary: 'REST 命名、错误码、版本策略;新智能体工程助手输出代码需符合。', category: '规范', chunks: 612, updatedAt: '上周', contributor: '研发架构组', status: 'published', promotedFromL2Ids: ['f-6'] },
  { id: 'k-4', team: '财务团队', kbId: 'kb-财务团队', title: '报销审批流程', summary: '差旅、采购、超额审批的分级权限说明。', category: '流程', chunks: 248, updatedAt: '本周', contributor: '财务团队', status: 'published' },
  { id: 'k-5', team: '法务团队', kbId: 'kb-法务团队', title: '合同条款红线', summary: '不可对外承诺的条款清单,销售合同审阅 Agent 自动校验。', category: '合规', chunks: 184, updatedAt: '上周', contributor: '法务团队', status: 'published' },
  { id: 'k-6', team: '客服团队', kbId: 'kb-客服团队', title: '退款话术模板', summary: '5 类退款场景的标准回复模板,带情绪分级。', category: '话术', chunks: 524, updatedAt: '3 天前', contributor: '客服一组', status: 'published' },
  { id: 'k-7', team: '产品团队', kbId: 'kb-产品团队', title: '发布检查清单', summary: '产品发布前 38 项检查项,灰度 / 上线 / 回滚动作。', category: '流程', chunks: 96, updatedAt: '昨天', contributor: '产品团队', status: 'published' },
  { id: 'k-8', team: '研发团队', kbId: 'kb-研发团队', title: '部署 runbook', summary: '各环境部署命令、回滚步骤、值班联系方式。', category: '流程', chunks: 412, updatedAt: '本周', contributor: '运维团队', status: 'published' },
  { id: 'k-9', team: '人力资源', kbId: 'kb-人力资源', title: '员工入职清单', summary: '新员工入职第一周的 18 项动作与负责人。', category: '流程', chunks: 76, updatedAt: '上周', contributor: '人力资源', status: 'published' },
  { id: 'k-10', team: '战略团队', kbId: 'kb-战略团队', title: '竞品对照表', summary: '主要竞品的定价、核心功能、市场份额,调研 Agent 优先引用。', category: '市场', chunks: 318, updatedAt: '本周', contributor: '战略团队', status: 'published' },
  { id: 'k-11', team: '客服团队', kbId: 'kb-客服团队', title: '常见投诉应对草稿', summary: '正在编写的统一投诉应对指南,未发布。', category: '话术', chunks: 0, updatedAt: '今天', contributor: '客服一组', status: 'draft' },
  { id: 'k-12', team: '财务团队', kbId: 'kb-财务团队', title: '旧版报销规则', summary: '已被新规则取代,保留作历史参考。', category: '流程', chunks: 12, updatedAt: '2 周前', contributor: '财务团队', status: 'retired' },
];

export const mockPromotions: PromotionEvent[] = [
  { id: 'p-1', layer: 'l1→l2', label: '张文佳 · 答复风格: 喜欢精简答复', at: '今天 15:48', operator: '系统自动提炼', targetId: 'f-1' },
  { id: 'p-2', layer: 'l2→knowledge', label: '客服团队 · 价格折扣规则发布', at: '今天 15:30', operator: '管理员', targetId: 'k-2' },
  { id: 'p-3', layer: 'l1→l2', label: '王晓阳 · 关注指标: 日活/留存/转化漏斗', at: '今天 15:12', operator: '系统自动提炼', targetId: 'f-5' },
  { id: 'p-4', layer: 'l1→l2', label: '陈雨晴 · 代码风格: 函数式优先', at: '今天 14:48', operator: '系统自动提炼', targetId: 'f-7' },
  { id: 'p-5', layer: 'l2→knowledge', label: '研发团队 · API 设计规范发布', at: '今天 14:30', operator: '管理员', targetId: 'k-3' },
  { id: 'p-6', layer: 'l1→l2', label: '赵泽宇 · 语言禁用: 中文优先', at: '今天 14:18', operator: '系统自动提炼', targetId: 'f-14' },
  { id: 'p-7', layer: 'l1→l2', label: '李楠 · 调研方法: 先公开数据后访谈', at: '今天 13:40', operator: '系统自动提炼', targetId: 'f-12' },
  { id: 'p-8', layer: 'l2→knowledge', label: '产品团队 · 业务术语对照表发布', at: '今天 11:20', operator: '管理员', targetId: 'k-1' },
];

export const mockRetentionPolicies: RetentionPolicy[] = [
  { layer: 'l2', label: '长期记忆', description: '用户偏好与事实', ttlMinutes: 60 * 24 * 90, maxItems: 200, storageMb: 32, eviction: 'lru', hitRate: 0.88 },
];

export const mockMemoryTrend: MemoryTrend = {
  l1Active: [42, 48, 53, 50, 56, 61, 58, 64],
  l2Hits: [820, 940, 1020, 1100, 1180, 1240, 1320, 1380],
};