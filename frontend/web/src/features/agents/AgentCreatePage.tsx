/**
 * 管理侧「新建智能体」— 路由 /admin/tools/new 的镜像:/admin/agents/new
 *
 * 使用 AgentEditor mode='create' — 9 面板全功能 + onboarding 提示 + 必填徽标。
 * Save Draft / Publish 按钮在 ActionBar;保存后跳详情页。
 */
import { useNavigate } from 'react-router-dom';
import { useCreateAgent } from './useAgents';
import { AgentEditor } from './AgentEditor';
import type { AgentEntry, Status } from './schema';

function makeEmptyDraft(): AgentEntry {
  const today = new Date().toISOString().slice(0, 10);
  return {
    id: `a-${Date.now()}`,
    name: '',
    description: '',
    category: '',
    owner: '张敏',
    tags: [],
    tone: 'info',
    status: 'draft',
    version: 'v0.1',
    lastUpdate: '刚刚',
    createdAt: today,
    calls: 0,
    successRate: 0,
    errorRate: 0,
    avgLatencyMs: 0,
    rating: 0,
    tools: [],
    starred: false,
    visibleScope: ['部门'],
    dataAccess: '基础数据',
    versions: [],
    evaluationPassRate: 0,
    evaluationRuns: 0,
    evaluationFailedCases: 0,
    trend: Array(12).fill(0),
    prompts: { prompt: '', soul: '', agents: '', user: '', tools: '' },
    customPrompts: [],
    knowledgeRefs: [],
    memoryPolicy: { enabled: false, retentionDays: 30, scope: 'user', autoSummarize: false },
    flowRefs: [],
  };
}

export default function AgentCreatePage() {
  const navigate = useNavigate();
  const createAgent = useCreateAgent();

  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-4 p-5 pb-16 sm:p-8 xl:px-6">
      <AgentEditor
        mode="create"
        initialDraft={makeEmptyDraft()}
        onCancel={() => navigate('/admin/agents')}
        onSave={(draft, status: Status) => {
          createAgent.mutate({ ...draft, status }, {
            onSuccess: (created) => navigate(`/admin/agents/${created.id}`),
          });
        }}
      />
    </div>
  );
}
