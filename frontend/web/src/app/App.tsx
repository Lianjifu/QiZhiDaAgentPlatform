import { Navigate, Route, Routes } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import { ToastHost, Spinner } from '@qzdap/web-ui';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { WorkspaceShell } from '@/widgets/app-shell';
import WorkspacePlaceholder from '@/pages/shared/WorkspacePlaceholder';
import Home from '@/features/user/home';
import Agents from '@/features/user/agents';
import Copilot from '@/features/user/copilot';

const Login = lazy(() => import('./pages/Login'));
const MyKnowledge = lazy(() => import('@/features/user/knowledge'));
const MyAutomations = lazy(() => import('@/features/user/automations'));
const MyTeam = lazy(() => import('@/features/user/team'));
const MySkills = lazy(() => import('@/features/user/skills'));
const MyTasks = lazy(() => import('@/features/user/tasks'));
const AccountSettings = lazy(() => import('@/features/user/account'));
const AdminSettings = lazy(() => import('@/features/settings'));
const AdminOverview = lazy(() => import('@/features/overview'));
const AdminAgents = lazy(() => import('@/features/agents'));
const AdminAgentDetail = lazy(() => import('@/features/agents/AgentDetailPage'));
const AdminAgentCreate = lazy(() => import('@/features/agents/AgentCreatePage'));
const AdminKnowledge = lazy(() => import('@/features/knowledge'));
const AdminKnowledgeKbDetail = lazy(() => import('@/features/knowledge/KbDetailPage'));
const AdminKnowledgeDocDetail = lazy(() => import('@/features/knowledge/DocDetailPage'));
const AdminKnowledgeSourceDetail = lazy(() => import('@/features/knowledge/SourceDetailPage'));
const AdminKnowledgeKbCreate = lazy(() => import('@/features/knowledge/KbCreatePage'));
const AdminKnowledgeSourceCreate = lazy(() => import('@/features/knowledge/SourceCreatePage'));
const AdminMemory = lazy(() => import('@/features/memory'));
const AdminMemoryPolicyDetail = lazy(() => import('@/features/memory/PolicyDetailPage'));
const AdminMemoryL1Detail = lazy(() => import('@/features/memory/L1DetailPage'));
const AdminMemoryL2Detail = lazy(() => import('@/features/memory/L2DetailPage'));
const AdminMemoryL3Detail = lazy(() => import('@/features/memory/L3DetailPage'));
const AdminWorkflows = lazy(() => import('@/features/workflows'));
const AdminWorkflowCreate = lazy(() => import('@/features/workflows/WorkflowCreatePage'));
const AdminWorkflowDetail = lazy(() => import('@/features/workflows/WorkflowDetailPage'));
const AdminSkills = lazy(() => import('@/features/skills'));
const AdminSkillCreate = lazy(() => import('@/features/skills/SkillCreatePage'));
const AdminSkillDetail = lazy(() => import('@/features/skills/SkillDetailPage'));
const AdminEvaluations = lazy(() => import('@/features/evaluations'));
const AdminEvaluationCreate = lazy(() => import('@/features/evaluations/EvalSuiteCreatePage'));
const AdminEvaluationDetail = lazy(() => import('@/features/evaluations/EvaluationDetailPage'));
const AdminRegressions = lazy(() => import('@/features/regressions'));
const AdminRegressionDetail = lazy(() => import('@/features/regressions/RegressionDetailPage'));
const AdminRegressionCreate = lazy(() => import('@/features/regressions/RegressionCreatePage'));
const AdminFeedback = lazy(() => import('@/features/feedback'));
const AdminFeedbackDetail = lazy(() => import('@/features/feedback/FeedbackDetailPage'));
const AdminFeedbackCreate = lazy(() => import('@/features/feedback/FeedbackCreatePage'));
const AdminFeedbackRuleCreate = lazy(() => import('@/features/feedback/FeedbackRuleCreatePage'));
const AdminModels = lazy(() => import('@/features/models'));
const AdminModelDetail = lazy(() => import('@/features/models/ModelDetailPage'));
const AdminModelCreate = lazy(() => import('@/features/models/ModelCreatePage'));
const AdminRouteCreate = lazy(() => import('@/features/models/RouteCreatePage'));
const AdminQuotas = lazy(() => import('@/features/quotas'));
const AdminQuotaCreate = lazy(() => import('@/features/quotas/BudgetCreatePage'));
const AdminQuotaAlertCreate = lazy(() => import('@/features/quotas/AlertCreatePage'));
const AdminQuotaDetail = lazy(() => import('@/features/quotas/QuotaDetailPage'));
const AdminNotifications = lazy(() => import('@/features/notifications'));
const AdminChannelCreate = lazy(() => import('@/features/notifications/ChannelCreatePage'));
const AdminChannelDetail = lazy(() => import('@/features/notifications/ChannelDetailPage'));
const AdminOperations = lazy(() => import('@/features/operations'));
const AdminSessionDetail = lazy(() => import('@/features/operations/SessionDetailPage'));
const AdminToolAudit = lazy(() => import('@/features/audit'));
const AdminAuditRuleCreate = lazy(() => import('@/features/audit/AuditRuleCreatePage'));
const AdminAuditDetail = lazy(() => import('@/features/audit/AuditDetailPage'));
const AdminMetrics = lazy(() => import('@/features/metrics'));
const AdminDashboardCreate = lazy(() => import('@/features/metrics/DashboardCreatePage'));
const AdminMetricDetail = lazy(() => import('@/features/metrics/MetricDetailPage'));

function PageFallback() {
  return (
    <div className="flex h-full items-center justify-center" role="status" aria-live="polite">
      <Spinner size={28} className="text-[var(--brand)]" />
    </div>
  );
}

function RebuildPlaceholder() {
  return (
    <main id="main-content" className="grid min-h-screen place-items-center bg-[var(--bg-elevated)] p-6 text-center">
      <div>
        <p className="text-sm font-medium text-[var(--brand)]">DaAgent</p>
        <h1 className="mt-3 text-2xl font-semibold text-[var(--text)]">智能体工作台正在重建</h1>
        <p className="mt-2 text-sm text-[var(--text-muted)]">登录能力已就绪，新工作台即将开放。</p>
      </div>
    </main>
  );
}

function NotFound() {
  return (
    <main id="main-content" className="grid min-h-screen place-items-center bg-[var(--bg-elevated)] p-6 text-center">
      <div>
        <h1 className="text-2xl font-semibold text-[var(--text)]">页面不存在</h1>
        <p className="mt-2 text-sm text-[var(--text-muted)]">请返回登录页继续。</p>
        <a className="mt-5 inline-block text-sm text-[var(--brand)] hover:underline" href="/login">返回登录</a>
      </div>
    </main>
  );
}

export default function App() {
  return (
    <ErrorBoundary fallbackTitle="应用遇到问题">
      <a href="#main-content" className="skip-link">跳转到主内容</a>
      <Suspense fallback={<PageFallback />}>
        <Routes>
          <Route path="/login" element={<ErrorBoundary><Login /></ErrorBoundary>} />
          <Route path="/" element={<Navigate to="/login" replace />} />
          <Route element={<WorkspaceShell />}>
            <Route path="/home" element={<Home />} />
            <Route path="/agents" element={<Agents />} />
            <Route path="/agents/new" element={<Navigate to="/agents" replace />} />
            <Route path="/agents/templates" element={<Navigate to="/agents" replace />} />
            <Route path="/agents/mine" element={<Navigate to="/agents" replace />} />
            <Route path="/team/agents" element={<Agents />} />
            <Route path="/copilot/*" element={<Copilot />} />
            <Route path="/tasks/*" element={<MyTasks />} />
            <Route path="/knowledge/*" element={<MyKnowledge />} />
            <Route path="/skills/*" element={<MySkills />} />
            <Route path="/automations/*" element={<MyAutomations />} />
            <Route path="/team/*" element={<MyTeam />} />
            <Route path="/insights" element={<Navigate to="/home" replace />} />
            <Route path="/account" element={<AccountSettings />} />
            <Route path="/help" element={<Navigate to="/account" replace />} />
            <Route path="/admin/help" element={<Navigate to="/admin/settings" replace />} />
            <Route path="/admin/settings" element={<AdminSettings />} />
            <Route path="/admin/overview" element={<AdminOverview />} />
            <Route path="/admin/agents" element={<AdminAgents />} />
            <Route path="/admin/agents/new" element={<AdminAgentCreate />} />
            <Route path="/admin/agents/:id/edit" element={<AdminAgentDetail />} />
            <Route path="/admin/agents/:id" element={<AdminAgentDetail />} />
            <Route path="/admin/knowledge" element={<AdminKnowledge />} />
            <Route path="/admin/knowledge/kbs/new" element={<AdminKnowledgeKbCreate />} />
            <Route path="/admin/knowledge/kbs/:id" element={<AdminKnowledgeKbDetail />} />
            <Route path="/admin/knowledge/docs/:id" element={<AdminKnowledgeDocDetail />} />
            <Route path="/admin/knowledge/sources/new" element={<AdminKnowledgeSourceCreate />} />
            <Route path="/admin/knowledge/sources/:id" element={<AdminKnowledgeSourceDetail />} />
            <Route path="/admin/memory" element={<AdminMemory />} />
            <Route path="/admin/memory/policies/:id" element={<AdminMemoryPolicyDetail />} />
            <Route path="/admin/memory/l1/:id" element={<AdminMemoryL1Detail />} />
            <Route path="/admin/memory/l2/:id" element={<AdminMemoryL2Detail />} />
            <Route path="/admin/memory/l3/:id" element={<AdminMemoryL3Detail />} />
            <Route path="/admin/workflows" element={<AdminWorkflows />} />
            <Route path="/admin/workflows/new" element={<AdminWorkflowCreate />} />
            <Route path="/admin/workflows/:id" element={<AdminWorkflowDetail />} />
            <Route path="/admin/tools" element={<AdminSkills />} />
            <Route path="/admin/tools/new" element={<AdminSkillCreate />} />
            <Route path="/admin/tools/:id/edit" element={<AdminSkillDetail />} />
            <Route path="/admin/tools/:id" element={<AdminSkillDetail />} />
            <Route path="/admin/evaluations" element={<AdminEvaluations />} />
            <Route path="/admin/evaluations/new" element={<AdminEvaluationCreate />} />
            <Route path="/admin/evaluations/:id" element={<AdminEvaluationDetail />} />
            <Route path="/admin/regressions" element={<AdminRegressions />} />
            <Route path="/admin/regressions/new" element={<AdminRegressionCreate />} />
            <Route path="/admin/regressions/:id" element={<AdminRegressionDetail />} />
            <Route path="/admin/feedback" element={<AdminFeedback />} />
            <Route path="/admin/feedback/new" element={<AdminFeedbackCreate />} />
            <Route path="/admin/feedback/rules/new" element={<AdminFeedbackRuleCreate />} />
            <Route path="/admin/feedback/:id" element={<AdminFeedbackDetail />} />
            <Route path="/admin/models" element={<AdminModels />} />
            <Route path="/admin/models/new" element={<AdminModelCreate />} />
            <Route path="/admin/models/routes/new" element={<AdminRouteCreate />} />
            <Route path="/admin/models/:id" element={<AdminModelDetail />} />
            <Route path="/admin/quotas" element={<AdminQuotas />} />
            <Route path="/admin/quotas/new" element={<AdminQuotaCreate />} />
            <Route path="/admin/quotas/alerts/new" element={<AdminQuotaAlertCreate />} />
            <Route path="/admin/quotas/:id" element={<AdminQuotaDetail />} />
            <Route path="/admin/notifications" element={<AdminNotifications />} />
            <Route path="/admin/notifications/new" element={<AdminChannelCreate />} />
            <Route path="/admin/notifications/:id" element={<AdminChannelDetail />} />
            <Route path="/admin/operations" element={<AdminOperations />} />
            <Route path="/admin/operations/:id" element={<AdminSessionDetail />} />
            <Route path="/admin/tool-audit" element={<AdminToolAudit />} />
            <Route path="/admin/tool-audit/rules/new" element={<AdminAuditRuleCreate />} />
            <Route path="/admin/tool-audit/:id" element={<AdminAuditDetail />} />
            <Route path="/admin/metrics" element={<AdminMetrics />} />
            <Route path="/admin/metrics/new" element={<AdminDashboardCreate />} />
            <Route path="/admin/metrics/:id" element={<AdminMetricDetail />} />
            <Route path="/admin/*" element={<WorkspacePlaceholder />} />
          </Route>
          <Route path="/app" element={<RebuildPlaceholder />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
      <ToastHost />
    </ErrorBoundary>
  );
}
