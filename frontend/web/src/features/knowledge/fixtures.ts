/**
 * 管理侧「知识管理」fixtures — 与原 AdminKnowledge.tsx 内联 INITIAL_* 对应。
 * dev:demo 通过 admin-knowledge-mock-handler.ts 返回;测试通过 seedPageQueryData 注入。
 */
import type { Kb, Doc, Source, Task, EvalCase } from './schema';

export const mockKbs: Kb[] = [
  { id: 'kb-prod', name: '产品手册 v3', description: '对外产品说明、功能边界与 FAQ 统一参考。', owner: '产品团队', scope: '公开', status: 'indexed', docCount: 286, vectorCount: 18420, updatedAt: '今天 14:32', tags: ['产品', '客户'], tone: 'brand', evalHitRate: 0.94 },
  { id: 'kb-hr', name: '员工手册', description: '入职、假期、培训、绩效等人事制度。', owner: '人力资源', scope: '部门', status: 'indexed', docCount: 124, vectorCount: 8120, updatedAt: '昨天 18:10', tags: ['人事', '制度'], tone: 'success', evalHitRate: 0.91 },
  { id: 'kb-sec', name: '信息安全规范', description: '数据分级、访问边界、日常安全操作。', owner: '安全团队', scope: '部门', status: 'indexing', docCount: 24, vectorCount: 1480, updatedAt: '2 小时前', tags: ['安全', '合规'], tone: 'warn', evalHitRate: 0.88 },
  { id: 'kb-faq', name: '客服 FAQ', description: '常见客户问题与标准答复。', owner: '客服一组', scope: '部门', status: 'indexed', docCount: 412, vectorCount: 26120, updatedAt: '今天 09:18', tags: ['客服', 'FAQ'], tone: 'info', evalHitRate: 0.93 },
  { id: 'kb-legal', name: '合同模板库', description: '销售合同、保密协议等模板与条款库。', owner: '法务团队', scope: '部门', status: 'paused', docCount: 38, vectorCount: 2120, updatedAt: '上周', tags: ['法务', '合同'], tone: 'danger', evalHitRate: 0.86 },
  { id: 'kb-finance', name: '财务报销指南', description: '差旅、采购、报销流程与表单。', owner: '财务团队', scope: '部门', status: 'indexed', docCount: 56, vectorCount: 3280, updatedAt: '本周', tags: ['财务', '流程'], tone: 'purple', evalHitRate: 0.90 },
  { id: 'kb-meet', name: '会议纪要库', description: '部门周会、复盘与决策记录。', owner: '运营团队', scope: '部门', status: 'indexed', docCount: 184, vectorCount: 11400, updatedAt: '今天 16:45', tags: ['协作', '纪要'], tone: 'info', evalHitRate: 0.85 },
  { id: 'kb-launch', name: '发布协作清单', description: '产品发布、灰度、上线协同步骤。', owner: '产品团队', scope: '部门', status: 'failed', docCount: 12, vectorCount: 740, updatedAt: '昨天', tags: ['发布', '协作'], tone: 'danger', evalHitRate: 0.72 },
  { id: 'kb-research', name: '行业研究报告', description: '季度行业趋势与竞品分析。', owner: '战略团队', scope: '部门', status: 'indexed', docCount: 32, vectorCount: 1860, updatedAt: '本周', tags: ['研究', '市场'], tone: 'purple', evalHitRate: 0.89 },
  { id: 'kb-ops', name: '运维手册', description: '服务部署、监控告警、应急响应。', owner: '运维团队', scope: '部门', status: 'indexing', docCount: 64, vectorCount: 3940, updatedAt: '今天', tags: ['运维', '应急'], tone: 'warn', evalHitRate: 0.87 },
  { id: 'kb-tpl', name: '回复话术模板', description: '客服与销售高频回复模板。', owner: '客服一组', scope: '个人', status: 'indexed', docCount: 28, vectorCount: 1640, updatedAt: '本周', tags: ['话术'], tone: 'info', evalHitRate: 0.92 },
  { id: 'kb-glossary', name: '业务术语表', description: '业务名词、产品代号与缩写。', owner: '产品团队', scope: '公开', status: 'indexed', docCount: 24, vectorCount: 1480, updatedAt: '上周', tags: ['术语'], tone: 'brand', evalHitRate: 0.95 },
];

export const mockDocs: Doc[] = [
  {
    id: 'doc-001', name: '产品手册 v3.pdf', type: 'manual', kbId: 'kb-prod', sourceId: 'src-1', status: 'parsed', sizeKb: 4820, chunks: 286, updatedAt: '今天 14:32', citations: 1240,
    chunksPreview: [
      { index: 1, heading: '产品定位', snippet: '本产品面向 B 端中型企业的智能体编排场景,核心卖点是一站式的知识接入与权限治理,目标用户为业务负责人 + 智能体运营。', citations: 18, tokens: 184 },
      { index: 2, heading: '核心功能矩阵', snippet: '智能体管理 / 知识检索 / 工具调用 / 工作流编排 四大模块,每个模块均有独立配置面板与权限边界。', citations: 24, tokens: 312 },
      { index: 3, heading: '快速开始 · 5 分钟接入', snippet: '登录后台 → 创建智能体 → 绑定知识库 → 接入企业微信/飞书 → 发布。无需任何代码即可上线。', citations: 32, tokens: 268 },
      { index: 4, heading: '功能边界 · 计费相关', snippet: '免费版支持 3 个智能体 / 1GB 知识;企业版按席位计费,详询商务。私有化部署需采购独立 license。', citations: 14, tokens: 196 },
      { index: 5, heading: '常见 FAQ · 价格政策', snippet: 'Q:试用多久?A:14 天全功能,无需信用卡。Q:能否按月付费?A:仅年付,不支持月付。', citations: 9, tokens: 220 },
      { index: 6, heading: '常见 FAQ · 数据安全', snippet: '数据托管在阿里云上海 region,默认加密存储;支持私有化部署 + 客户自主 KMS 密钥。', citations: 6, tokens: 248 },
    ],
  },
  {
    id: 'doc-001b', name: '产品发布说明 · v3.2.md', type: 'faq', kbId: 'kb-prod', sourceId: 'src-1', status: 'parsed', sizeKb: 32, chunks: 18, updatedAt: '今天 10:08', citations: 68,
    chunksPreview: [
      { index: 1, heading: 'v3.2 重点更新', snippet: '本次发布智能体编排可视化编辑器、向量检索召回率 +6%、新增 12 个企业级模板。', citations: 12, tokens: 156 },
      { index: 2, heading: '可视化编辑器使用', snippet: '从智能体详情页进入工作流编辑器,左侧节点栏拖入节点,右侧实时预览运行结果;支持撤销 / 重做。', citations: 9, tokens: 188 },
      { index: 3, heading: '新增模板列表', snippet: '客服 / 销售 / HR / 财务 / 运维 5 大类共 12 个模板,一键克隆到工作空间,2 分钟即可上线。', citations: 6, tokens: 142 },
    ],
  },
  {
    id: 'doc-002', name: '员工手册 2026.docx', type: 'policy', kbId: 'kb-hr', sourceId: 'src-1', status: 'parsed', sizeKb: 1280, chunks: 124, updatedAt: '昨天 18:10', citations: 412,
    chunksPreview: [
      { index: 1, heading: '入职流程 · Day 1', snippet: '上午 9 点到前台报到,领取设备,签署劳动合同 + 保密协议,IT 协助开通账号,加入欢迎群。', citations: 22, tokens: 312 },
      { index: 2, heading: '假期类型 · 法定假', snippet: '法定节假日按国家规定执行,共 11 天。年假 5~15 天按司龄累计,病假 12 天/年。', citations: 18, tokens: 256 },
      { index: 3, heading: '绩效评估 · OKR 周期', snippet: '每季度一次 OKR 复盘,半年中期 review,年底年终 review;评分分为 S/A/B/C 四档。', citations: 12, tokens: 198 },
      { index: 4, heading: '培训与发展', snippet: '每位员工每年有 5000 元学习基金,可报销课程、书籍、考证费用;鼓励跨部门轮岗。', citations: 8, tokens: 174 },
      { index: 5, heading: '离职流程', snippet: '提前 30 天书面通知,工作交接清单由 HR 提供,最后一个工作日归还设备 + 注销账号。', citations: 4, tokens: 142 },
    ],
  },
  {
    id: 'doc-003', name: '信息安全等级保护指南.pdf', type: 'policy', kbId: 'kb-sec', sourceId: 'src-8', status: 'parsing', sizeKb: 1840, chunks: 24, updatedAt: '2 小时前', citations: 86,
    chunksPreview: [],
  },
  {
    id: 'doc-004', name: '客服 FAQ Top100.csv', type: 'faq', kbId: 'kb-faq', sourceId: 'src-3', status: 'parsed', sizeKb: 412, chunks: 412, updatedAt: '今天 09:18', citations: 2840,
    chunksPreview: [
      { index: 1, heading: '退款政策', snippet: 'Q:7 天内订单如何退款?A:订单详情页提交退款申请,客服 24 小时内审核,3 个工作日内原路退回。', citations: 84, tokens: 96 },
      { index: 2, heading: '发票申请', snippet: 'Q:如何开增值税专票?A:在订单页填写开票信息,3 个工作日内寄出;首次开票需提供税务登记证。', citations: 62, tokens: 88 },
      { index: 3, heading: '套餐变更', snippet: 'Q:能否从基础版升级到企业版?A:随时升级,差价按剩余天数折算,新功能立即生效。', citations: 48, tokens: 92 },
      { index: 4, heading: '账号安全', snippet: 'Q:忘记密码怎么办?A:登录页点忘记密码,通过邮箱 + 手机双重验证重置,5 分钟内有效。', citations: 36, tokens: 84 },
      { index: 5, heading: '数据导出', snippet: 'Q:能否导出我的数据?A:支持 JSONL + CSV 格式导出,工单审核后 24 小时内邮件发送下载链接。', citations: 28, tokens: 102 },
      { index: 6, heading: '合同续签', snippet: 'Q:合同到期前多久提醒?A:到期前 30 / 15 / 7 天分别邮件 + 站内信提醒,自动续签需提前 5 天关闭。', citations: 22, tokens: 108 },
      { index: 7, heading: '第三方集成', snippet: 'Q:支持哪些集成?A:企业微信 / 飞书 / 钉钉 / Slack / 主流 CRM,Webhook 自定义接入。', citations: 18, tokens: 96 },
    ],
  },
  {
    id: 'doc-005', name: '销售合同模板 v2.docx', type: 'contract', kbId: 'kb-legal', sourceId: 'src-5', status: 'parsed', sizeKb: 184, chunks: 38, updatedAt: '上周', citations: 142,
    chunksPreview: [
      { index: 1, heading: '合同主体信息', snippet: '甲方(采购方)名称 / 统一社会信用代码 / 法定代表人 / 通讯地址,乙方填写公司全称 + 开户行 + 账号。', citations: 12, tokens: 156 },
      { index: 2, heading: '服务范围约定', snippet: '本协议项下甲方采购乙方【智能体平台企业版】席位 N 个,有效期 12 个月,自双方盖章之日起生效。', citations: 9, tokens: 220 },
      { index: 3, heading: '费用与付款', snippet: '总费用人民币 XXX 万元,合同生效后 5 个工作日内支付 50%,验收后 30 日内支付剩余 50%。', citations: 6, tokens: 198 },
      { index: 4, heading: '数据归属与保密', snippet: '甲方业务数据全部归甲方所有;乙方对接触到的客户信息负有保密义务,有效期至合同终止后 3 年。', citations: 4, tokens: 244 },
      { index: 5, heading: '违约责任', snippet: '任一方违约,守约方有权要求继续履行 / 解除合同 / 赔偿损失,赔偿金额不超过年度合同金额。', citations: 3, tokens: 188 },
    ],
  },
  {
    id: 'doc-006', name: '差旅报销指南.md', type: 'policy', kbId: 'kb-finance', sourceId: 'src-6', status: 'parsed', sizeKb: 96, chunks: 56, updatedAt: '本周', citations: 318,
    chunksPreview: [
      { index: 1, heading: '差旅申请流程', snippet: '出差前 3 个工作日提交申请,主管 + 财务双签;5000 元以上需 VP 审批。', citations: 28, tokens: 168 },
      { index: 2, heading: '机票住宿标准', snippet: '经济舱 / 高铁二等座 / 三星以内酒店;一线城市 600/晚,二线 450/晚,出差 5 天以上可放宽。', citations: 24, tokens: 196 },
      { index: 3, heading: '餐补与交通', snippet: '餐补 100/天/人,无票据也可领取;市内交通实报实销,出租车需注明起讫地点。', citations: 18, tokens: 144 },
      { index: 4, heading: '报销时限', snippet: '差旅结束后 10 个工作日内提交报销单,过期不予办理;紧急情况下可口头申请延后。', citations: 12, tokens: 132 },
      { index: 5, heading: '常见驳回原因', snippet: '票据缺失 / 日期不符 / 金额超标 / 行程与申请单不匹配 — 请提前核对,避免来回。', citations: 8, tokens: 156 },
    ],
  },
  {
    id: 'doc-007', name: 'Q3 周会纪要.md', type: 'meeting', kbId: 'kb-meet', sourceId: 'src-2', status: 'parsed', sizeKb: 28, chunks: 18, updatedAt: '今天 16:45', citations: 24,
    chunksPreview: [
      { index: 1, heading: '议程 · 上周回顾', snippet: '产品发布按计划落地,知识中台上线 12 个新 KB,客服 FAQ 命中率从 81% 提升至 93%。', citations: 6, tokens: 168 },
      { index: 2, heading: '议程 · 业务进展', snippet: 'Q3 营收同比增长 28%,企业版客户从 32 增至 48 家;流失率 4.2% 创历史新低。', citations: 4, tokens: 184 },
      { index: 3, heading: '决策 · 智能体定价', snippet: '经讨论决定:企业版按席位调整为 198 / 月(原 168);私有化版维持原报价,不再降价。', citations: 3, tokens: 156 },
      { index: 4, heading: '行动项 · 知识库治理', snippet: 'Owner:产品团队。10/15 前完成 12 个核心 KB 的版本对齐 + 标签治理,确保命中率 < 1% 衰减。', citations: 2, tokens: 212 },
      { index: 5, heading: '风险 · 大客户回款', snippet: '客户 X 第 3 期回款延迟 18 天,已在跟进;若月底仍未到账,法务介入。', citations: 1, tokens: 188 },
    ],
  },
  {
    id: 'doc-008', name: 'Q4 发布会清单.md', type: 'meeting', kbId: 'kb-launch', sourceId: 'src-2', status: 'failed', sizeKb: 12, chunks: 0, updatedAt: '昨天', citations: 0,
    chunksPreview: [],
  },
  {
    id: 'doc-009', name: '行业研究 - SaaS.pdf', type: 'manual', kbId: 'kb-research', sourceId: 'src-3', status: 'parsed', sizeKb: 3120, chunks: 32, updatedAt: '本周', citations: 64,
    chunksPreview: [
      { index: 1, heading: '行业总览 · 市场规模', snippet: '2026 年中国 SaaS 市场规模达 1,283 亿美元,YoY +18%;其中 AI Native SaaS 占比首次超过 12%。', citations: 8, tokens: 220 },
      { index: 2, heading: '细分赛道 · 智能体编排', snippet: '智能体编排赛道 2026 年规模 84 亿美元,头部 5 家厂商合计市占率 62%;集中度高于通用 SaaS。', citations: 6, tokens: 244 },
      { index: 3, heading: '竞品分析 · 头部产品', snippet: '头部 A 产品主打大客户私有化,客单价 300 万起;头部 B 产品聚焦 SMB SaaS,ARPU 6,800 元。', citations: 5, tokens: 268 },
      { index: 4, heading: '用户调研 · 痛点 Top 5', snippet: '数据安全 / 知识治理 / 权限边界 / 计费透明 / 集成成本 — 前三项是采购决策核心。', citations: 4, tokens: 212 },
      { index: 5, heading: '趋势展望 · 2027', snippet: 'Agent-as-a-Service 模式将成为主流,客户按"智能体调用次数"付费,取代按席位模式。', citations: 3, tokens: 198 },
    ],
  },
  {
    id: 'doc-010', name: '应急响应 runbook.md', type: 'policy', kbId: 'kb-ops', sourceId: 'src-8', status: 'parsing', sizeKb: 184, chunks: 28, updatedAt: '今天', citations: 48,
    chunksPreview: [],
  },
  {
    id: 'doc-011', name: '常见拒绝话术.md', type: 'faq', kbId: 'kb-tpl', sourceId: 'src-7', status: 'parsed', sizeKb: 18, chunks: 28, updatedAt: '本周', citations: 96,
    chunksPreview: [
      { index: 1, heading: '价格类拒绝', snippet: '客户:"太贵了。"回复:"理解您的顾虑,我们提供年付 8 折 + 3 个月试用,先把效果跑出来再决定长期投入。"', citations: 14, tokens: 168 },
      { index: 2, heading: '功能类拒绝', snippet: '客户:"没有 X 功能。"回复:"目前 X 已在 roadmap,Q2 上线;现阶段我们提供手工方案 + 补偿折扣。"', citations: 11, tokens: 156 },
      { index: 3, heading: '数据安全类拒绝', snippet: '客户:"担心数据泄露。"回复:"我们支持客户自主 KMS 密钥 + 私有化部署,可安排安全团队现场沟通。"', citations: 9, tokens: 174 },
      { index: 4, heading: '竞品类拒绝', snippet: '客户:"X 厂商更便宜。"回复:"X 厂商在 A 模块弱于我们 30%,我们可以做一次对比 demo 让您直观感受。"', citations: 7, tokens: 188 },
      { index: 5, heading: '决策延期', snippet: '客户:"再考虑考虑。"回复:"完全理解,我们可以安排 1 周免费 POC 验证核心场景,跑数据再决定。"', citations: 5, tokens: 162 },
    ],
  },
  {
    id: 'doc-012', name: '业务术语表 v2.csv', type: 'faq', kbId: 'kb-glossary', sourceId: 'src-4', status: 'parsed', sizeKb: 24, chunks: 24, updatedAt: '上周', citations: 184,
    chunksPreview: [
      { index: 1, heading: '企智搭', snippet: 'QiZhiDa · Agent Platform — 企智搭 · 智能体平台,本产品对外品牌名称。', citations: 24, tokens: 92 },
      { index: 2, heading: 'KB', snippet: 'Knowledge Base — 知识库,一组具有相同可见范围与检索策略的文档集合。', citations: 18, tokens: 88 },
      { index: 3, heading: 'Chunk', snippet: '切片 — 文档按语义切分后的最小检索单元,通常 200~500 tokens。', citations: 14, tokens: 84 },
      { index: 4, heading: 'MRR', snippet: 'Mean Reciprocal Rank — 检索评价指标,首条命中位置的倒数,值越高越好。', citations: 8, tokens: 96 },
      { index: 5, heading: 'RAG', snippet: 'Retrieval-Augmented Generation — 检索增强生成,本平台核心架构范式。', citations: 6, tokens: 80 },
      { index: 6, heading: 'HITL', snippet: 'Human-in-the-Loop — 人机协同,关键决策保留人工审核环节的运行模式。', citations: 4, tokens: 88 },
    ],
  },
];

export const mockSources: Source[] = [
  { id: 'src-1', name: '产品 Wiki', type: 'notion', status: 'online', lastSync: '今天 14:00', schedule: '每 4 小时', itemCount: 286, lastError: undefined },
  { id: 'src-2', name: '客户成功频道', type: 'slack', status: 'online', lastSync: '今天 13:30', schedule: '每 1 小时', itemCount: 1840, lastError: undefined },
  { id: 'src-3', name: '官网帮助中心', type: 'web', status: 'syncing', lastSync: '正在同步', schedule: '每天 02:00', itemCount: 312, lastError: undefined },
  { id: 'src-4', name: '订单库 (prod)', type: 'postgres', status: 'online', lastSync: '今天 15:12', schedule: '实时', itemCount: 18420, lastError: undefined },
  { id: 'src-5', name: '历史合同扫描件', type: 's3', status: 'error', lastSync: '昨天', schedule: '手动', itemCount: 0, lastError: 'S3 凭据过期,请更新 IAM 角色。' },
  { id: 'src-6', name: '工单系统 API', type: 'api', status: 'online', lastSync: '今天 15:08', schedule: '每 30 分钟', itemCount: 8120, lastError: undefined },
  { id: 'src-7', name: '本地共享盘 · 法务', type: 'folder', status: 'paused', lastSync: '3 天前', schedule: '每天 18:00', itemCount: 124, lastError: undefined },
  { id: 'src-8', name: 'Confluence · 研发', type: 'confluence', status: 'online', lastSync: '今天 11:20', schedule: '每 6 小时', itemCount: 412, lastError: undefined },
];

export const mockTasks: Task[] = [
  { id: 'task-1', name: '产品手册 v3 全文索引', kind: 'index', kbId: 'kb-prod', sourceId: 'src-1', status: 'success', progress: 100, items: 286, startedAt: '今天 14:00', duration: '32 分钟' },
  { id: 'task-2', name: 'FAQ Top100 增量索引', kind: 'reindex', kbId: 'kb-faq', sourceId: 'src-3', status: 'running', progress: 68, items: 412, startedAt: '今天 15:20', duration: '进行中' },
  { id: 'task-3', name: '员工手册 2026 重建', kind: 'rebuild', kbId: 'kb-hr', sourceId: 'src-1', status: 'failed', progress: 42, items: 124, startedAt: '昨天', duration: '失败 @ 第 52 项', failureReason: '文档中含有损坏的 PDF 附件,解析器在第 52 项中止。' },
  { id: 'task-4', name: '会议纪要导入', kind: 'index', kbId: 'kb-meet', sourceId: 'src-2', status: 'success', progress: 100, items: 18, startedAt: '今天 16:00', duration: '4 分钟' },
  { id: 'task-5', name: '应急 runbook 索引', kind: 'index', kbId: 'kb-ops', sourceId: 'src-8', status: 'running', progress: 28, items: 28, startedAt: '今天 15:48', duration: '进行中' },
  { id: 'task-6', name: '合同模板全量重建', kind: 'rebuild', kbId: 'kb-legal', sourceId: 'src-5', status: 'paused', progress: 56, items: 38, startedAt: '上周', duration: '已暂停', failureReason: '管理员手动暂停,等待法务团队复核条款变更后再继续。' },
  { id: 'task-7', name: '行业研究同步', kind: 'reindex', kbId: 'kb-research', sourceId: 'src-3', status: 'success', progress: 100, items: 32, startedAt: '本周', duration: '18 分钟' },
  { id: 'task-8', name: '话术模板清洗', kind: 'reindex', kbId: 'kb-tpl', sourceId: 'src-7', status: 'success', progress: 100, items: 28, startedAt: '本周', duration: '6 分钟' },
  { id: 'task-9', name: '安全规范 v3 重建', kind: 'rebuild', kbId: 'kb-sec', sourceId: 'src-8', status: 'running', progress: 84, items: 24, startedAt: '今天 13:10', duration: '进行中' },
  { id: 'task-10', name: '历史合同 OCR', kind: 'index', kbId: 'kb-legal', sourceId: 'src-5', status: 'failed', progress: 12, items: 184, startedAt: '昨天', duration: '失败 · 凭据过期', failureReason: 'S3 IAM 角色凭据已过期,请前往 src-5 配置页更新访问密钥。' },
  { id: 'task-11', name: '回复话术增量', kind: 'reindex', kbId: 'kb-tpl', sourceId: 'src-7', status: 'pending', progress: 0, items: 28, startedAt: '排队', duration: '—' },
  { id: 'task-12', name: '术语表同步', kind: 'reindex', kbId: 'kb-glossary', sourceId: 'src-4', status: 'success', progress: 100, items: 24, startedAt: '上周', duration: '2 分钟' },
  { id: 'task-13', name: '应急响应案例', kind: 'index', kbId: 'kb-ops', sourceId: 'src-8', status: 'pending', progress: 0, items: 36, startedAt: '排队', duration: '—' },
  { id: 'task-14', name: '客服录音转写', kind: 'index', kbId: 'kb-faq', sourceId: 'src-3', status: 'failed', progress: 23, items: 312, startedAt: '昨天', duration: '失败 · 队列满', failureReason: '并发任务数超过工作空间配额,排队队列已满。' },
];

export const mockEvalCases: EvalCase[] = [
  { id: 'e1', name: '退款政策查询', query: '客户申请退款,7 天内的订单怎么办?', expectedKb: 'kb-faq', actualKb: 'kb-faq', status: 'pass', latency: 0.84, mrr: 0.92 },
  { id: 'e2', name: '差旅报销', query: '出差 5 天的住宿费上限是多少?', expectedKb: 'kb-finance', actualKb: 'kb-finance', status: 'pass', latency: 0.72, mrr: 0.88 },
  { id: 'e3', name: '产品功能 FAQ', query: '智能体支持自定义知识库吗?', expectedKb: 'kb-prod', actualKb: 'kb-prod', status: 'pass', latency: 0.96, mrr: 0.94 },
  { id: 'e4', name: '入职流程', query: '新员工第一天要做什么?', expectedKb: 'kb-hr', actualKb: 'kb-hr', status: 'pass', latency: 0.68, mrr: 0.86 },
  { id: 'e5', name: '安全合规', query: '出差可以携带敏感数据吗?', expectedKb: 'kb-sec', actualKb: 'kb-sec', status: 'pass', latency: 0.92, mrr: 0.90 },
  { id: 'e6', name: '合同模板', query: 'NDA 模板在哪里?', expectedKb: 'kb-legal', actualKb: 'kb-legal', status: 'pass', latency: 0.81, mrr: 0.88 },
  { id: 'e7', name: '行业研究', query: 'SaaS 市场规模数据?', expectedKb: 'kb-research', actualKb: 'kb-prod', status: 'fail', latency: 1.12, mrr: 0.62 },
  { id: 'e8', name: '应急响应', query: '服务宕机怎么上报?', expectedKb: 'kb-ops', actualKb: 'kb-ops', status: 'pass', latency: 0.74, mrr: 0.84 },
  { id: 'e9', name: '话术引用', query: '客户抱怨价格怎么回复?', expectedKb: 'kb-tpl', actualKb: 'kb-tpl', status: 'pass', latency: 0.66, mrr: 0.90 },
  { id: 'e10', name: '术语解释', query: 'EOS 是什么的缩写?', expectedKb: 'kb-glossary', actualKb: 'kb-glossary', status: 'pass', latency: 0.54, mrr: 0.96 },
  { id: 'e11', name: '会议纪要查询', query: '上次发布复盘的结论是什么?', expectedKb: 'kb-meet', actualKb: 'kb-meet', status: 'pass', latency: 0.88, mrr: 0.86 },
  { id: 'e12', name: '灰度规则', query: '新智能体灰度规则怎么配置?', expectedKb: 'kb-launch', actualKb: 'kb-meet', status: 'fail', latency: 1.04, mrr: 0.58 },
  { id: 'e13', name: '废弃案例', query: 'Q&A 已取消', expectedKb: 'kb-faq', actualKb: 'kb-faq', status: 'skipped', latency: 0, mrr: 0 },
  { id: 'e14', name: '性能瓶颈', query: '检索延迟高的常见原因?', expectedKb: 'kb-ops', actualKb: 'kb-ops', status: 'pass', latency: 0.82, mrr: 0.88 },
];