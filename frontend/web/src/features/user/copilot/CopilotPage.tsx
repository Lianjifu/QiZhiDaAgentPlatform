import { getApiClient } from '@qzdap/web-api';
import { Plus, Search, Sparkles } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { flushSync } from 'react-dom';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { ApiTurn, CopilotSession } from './schema';
import {
  InteractiveProvider,
  useInteractive,
} from './interactiveStore';
import { InteractionHost } from './InteractionHost';
import {
  cancelCopilotTurn,
  createCopilotSession,
  decideCopilotApproval,
  deleteCopilotSession,
  listCopilotSessions,
  loadCopilotSession,
  streamCopilotTurn,
  submitCopilotFeedback,
} from './copilotApi';
import type { ToolCallState } from './blocks/MessageExtrasView';
import type { PlanProposal } from './blocks/PlanProposalCard';
import type { ArtifactReady } from './blocks/ArtifactCard';
import type { AttachmentReady } from './blocks/AttachmentChip';
import { normalizeError } from '@/api/shared/http-error';
import { Composer } from './components/Composer';
import { ConversationHeader } from './components/ConversationHeader';
import { SessionListItem } from './components/SessionListItem';
import { TurnBlock } from './components/TurnBlock';
import {
  buildTurns,
  resolveTurnFacts,
  type ChatMessageView,
} from './components/turns';

type CopilotEntryState = {
  knowledgeTitle?: string;
  agentId?: string;
  agentName?: string;
  agentExample?: string;
  skillName?: string;
  sessionId?: string;
};

type SessionInfo = {
  agentName?: string;
  model?: string;
  turnCount?: number;
  waitingApproval?: boolean;
};

function newRequestId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `req-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/**
 * getStarters — 按时间 + 周末动态产出问候语, 拟人/亲切型.
 * 4 条循环, 同一会话多次进 empty 态会有不同开场.
 */
function getStarters(now: Date = new Date()): string[] {
  const h = now.getHours();
  const dow = now.getDay();
  const weekday = dow >= 1 && dow <= 5;
  if (h < 5) {
    return ['这么晚还没睡呀~', '我陪你熬会儿', '要不来杯热茶?'];
  }
  if (h < 11) {
    return weekday
      ? ['早安,今天精神不错嘛', '新的一天,想问点啥?', '先吃早饭再说?']
      : ['周末好~睡饱了没?', '难得清闲,聊点啥?', '要不要出门转转?'];
  }
  if (h < 14) {
    return ['中午好~困不困?', '别忘了午饭', '有什么我能搭把手的?'];
  }
  if (h < 18) {
    return weekday
      ? ['下午好,冲劲十足啊', '今天进展怎么样?', '遇到啥难题了?']
      : ['周日下午好~', '今天过得咋样?', '需要理一理啥?'];
  }
  if (h < 22) {
    return ['晚上好~今天辛苦啦', '终于到收工时间啦', '想聊点轻松的?'];
  }
  return ['夜深啦,要不明天再说?', '需要陪你说说话吗?', '我在,你说'];
}

/**
 * pushNotice: 加一条提示, 同样的内容在最近 N 条里已存在则跳过 (避免
 * onEvent('error') 和 streamCopilotTurn.throw 两次 add 到 notices).
 */
const DEDUPE_WINDOW = 6;
const pushNotice = (current: string[], next: string): string[] => {
  const trimmed = next.trim();
  if (!trimmed) return current;
  const recent = current.slice(-DEDUPE_WINDOW);
  if (recent.includes(trimmed)) return current;
  return [...current, trimmed];
};

export default function Copilot() {
  return (
    <InteractiveProvider>
      <CopilotInner />
    </InteractiveProvider>
  );
}

function CopilotInner() {
  const interactive = useInteractive();
  const handleInteractiveAction = interactive.handleAction;
  const dismissQuestion = interactive.dismissQuestion;
  const dismissPlan = interactive.dismissPlan;
  const location = useLocation();
  const entry = location.state as CopilotEntryState | null;
  const agentName = entry?.agentName;
  const knowledgeTitle = entry?.knowledgeTitle;
  const skillName = entry?.skillName;
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<ChatMessageView[]>([]);
  const [turns, setTurns] = useState<ApiTurn[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [sessions, setSessions] = useState<CopilotSession[]>([]);
  const [search, setSearch] = useState('');
  const [sessionId, setSessionId] = useState<string | undefined>(entry?.sessionId);
  const [sessionInfo, setSessionInfo] = useState<SessionInfo>({});
  const [pendingApproval, setPendingApproval] = useState<{ id: string; toolName: string; reason: string } | null>(null);
  const [notices, setNotices] = useState<string[]>([]);
  useEffect(() => {
    // ⚠️ **搜索是真的** ✓ —— 后端 ``GET /api/sessions?search=`` ✓（以前这个
    // 输入框只是个摆设 ✗✗ —— 输了什么都不会变 ✗✗）。
    const timer = window.setTimeout(() => {
      void listCopilotSessions({ search })
        .then(setSessions)
        .catch((error) => setNotices((current) => pushNotice(current, `查询失败：${String(error)}`)));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [search]);
  // 已经跟服务端同步过的会话 —— 每个会话只同步一次.
  // 之前这个 effect 依赖 isSending: 一轮结束后 isSending 变 false 会再跑一次,
  // 用服务端的消息整个替换本地状态, 于是刚渲染出来的工具卡片 / 产物 / 用量
  // 全被抹掉. 本地消息本来就比服务端那条更全, 不该被覆盖.
  const syncedSessionRef = useRef<string | undefined>(undefined);
  useEffect(() => {
    // 发送中时不要触发重载, 避免 race:
    // sendMessage 已经把 user message push 进 messages, 紧跟着 setSessionId
    // 会触发本 effect, loadCopilotSession 返回空 / 旧数据 → setMessages([])
    // 把刚加的 user message 覆盖掉, 页面就只剩空态.
    if (!sessionId || isSending) return;
    if (syncedSessionRef.current === sessionId) return;
    syncedSessionRef.current = sessionId;
    void loadCopilotSession(sessionId).then((detail) => {
      if (!detail) { setMessages([]); setTurns([]); setPendingApproval(null); return; }
      const loaded = (detail.messages || [])
        .filter((item) => item.role === 'user' || item.role === 'assistant')
        .map((item) => ({
          role: item.role as 'user' | 'assistant',
          content: item.content,
          // ⚠️ **轮次 id 带上** ✓ —— 审批恢复会开新一轮 ✓ —— 靠它分轮次 ✓。
          turnId: item.turnId,
        }));
      setMessages(loaded);
      setTurns(detail.turns ?? []);
      setPendingApproval(null);
      const pending = detail.pendingApproval;
      if (pending) {
        setPendingApproval({
          id: String(pending.approval_id || pending.approvalId || ''),
          toolName: String(pending.tool_name || pending.toolName || '工具'),
          reason: String(pending.reason || '需要确认后才会执行'),
        });
      }
      setSessionInfo({
        agentName: detail.agentName || (detail.agent?.name as string | undefined) || undefined,
        model: detail.model || undefined,
        turnCount: (detail.turns ?? []).length,
        waitingApproval: Boolean(pending),
      });
    }).catch((error) => { setMessages([]); setTurns([]); setNotices((current) => pushNotice(current, `详情加载失败：${String(error)}`)); });
  }, [sessionId, isSending]);
  useEffect(() => {
    if (!knowledgeTitle) return;
    setInput((current) => current || `请基于《${knowledgeTitle}》帮我整理一份可执行的摘要。`);
  }, [knowledgeTitle]);
  useEffect(() => {
    if (!skillName || knowledgeTitle) return;
    setInput((current) => current || (agentName
      ? `请用「${skillName}」能力，协助完成与${agentName}相关的工作。`
      : `请使用「${skillName}」帮我完成这项工作。`));
  }, [skillName, agentName, knowledgeTitle]);
  const [sessionListOpen, setSessionListOpen] = useState(false);
  const [feedbackGiven, setFeedbackGiven] = useState<Record<string, 5 | 1>>({});
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const sendFeedback = async (turnKey: string, turnId: string | undefined, rating: 5 | 1) => {
    if (!sessionId || feedbackGiven[turnKey]) return;
    setFeedbackGiven((current) => ({ ...current, [turnKey]: rating }));
    try {
      await submitCopilotFeedback(sessionId, rating, turnId ? { turnId } : undefined);
    } catch {
      // 反馈写失败不该打扰用户 —— 标记先撤掉.
      setFeedbackGiven((current) => {
        const next = { ...current };
        delete next[turnKey];
        return next;
      });
    }
  };

  const stopSending = async () => {
    // 先断掉前端的流, 再让后端停 —— 用户立刻看到停止, 后端随后收尾.
    abortRef.current?.abort();
    const sid = sessionId;
    if (!sid) return;
    try {
      await cancelCopilotTurn(sid);
    } catch {
      // 后端收尾失败不影响前端 —— 流已经断了.
    }
  };

  const sendMessage = async (
    value = input,
    options?: { retry?: { question: string; assistantIndex: number } },
  ) => {
    const content = (options?.retry?.question ?? value).trim();
    if (!content || isSending) return;
    setIsSending(true);
    const isRetry = Boolean(options?.retry);
    if (!isRetry) {
      setMessages((current) => [...current, { role: 'user', content }]);
      setInput('');
    }
    const controller = new AbortController();
    abortRef.current = controller;
    // ⚠️ **这一轮跑了多久** ✓ —— 流式这边是**客户端量的** ✓（后端那份
    // （重开会话时读的）才是权威 ✓）。
    const turnStartedAt = Date.now();
    // 幂等 id —— 双击 / 网络重试不会跑出两轮对话.
    const clientRequestId = newRequestId();
    // ⚠️ **回答落在哪一条** ✓ —— 流式累积 / 失败 / 重试都改这一条 ✓。
    let assistantIndex = options?.retry?.assistantIndex ?? -1;
    const patchAssistant = (patch: (message: ChatMessageView) => ChatMessageView) => {
      setMessages((current) => {
        const idx = assistantIndex < 0 ? current.length - 1 : assistantIndex;
        const next = current.slice();
        const existing = next[idx];
        if (!existing || existing.role !== 'assistant') return current;
        next[idx] = patch(existing);
        return next;
      });
    };
    try {
      let sid = sessionId;
      let effectiveAgentId = entry?.agentId;
      // Phase 24 fallback: 入口没传 agentId (例如直接 /copilot 进, 或 state 过期),
      // 但有 agentName 时, 从 admin agents 列表里按名字找 id. 都找不到则用第一个 published.
      if (!effectiveAgentId) {
        try {
          const rows = await getApiClient().get<{ items?: Array<{ id: string; name: string; status?: string }> } | Array<{ id: string; name: string; status?: string }>>('/api/admin/agents', { query: { tab: 'all' } });
          const list: Array<{ id: string; name: string; status?: string }> = Array.isArray(rows) ? rows : (rows?.items ?? []);
          const target = agentName
            ? list.find((row) => row.name === agentName || row.name?.includes(agentName))
            : list.find((row) => row.status === 'published') ?? list[0];
          if (target?.id) effectiveAgentId = target.id;
        } catch (error) {
          console.debug('copilot agent lookup failed:', error);
        }
      }
      if (!sid && effectiveAgentId) {
        const created = await createCopilotSession(effectiveAgentId, agentName ? `与${agentName}对话` : content.slice(0, 24));
        sid = created?.id;
        if (sid) {
          setSessionId(sid);
          // 本地新建的会话不需要再从服务端拉一遍 —— 拉了会把刚加的消息冲掉.
          syncedSessionRef.current = sid;
          setSessionInfo({
            agentName: created?.agentName || agentName,
            model: created?.model,
            turnCount: 0,
          });
        }
      }
      if (!sid) {
        // 没有 agent 上下文: 回滚刚 push 的 user 消息, 给一个跳转提示, 不污染消息栈.
        if (!isRetry) setMessages((current) => current.slice(0, -1));
        setNotices((current) => pushNotice(current, '需要先选一个智能体才能开始对话 → 去智能体库选一个'));
        return;
      }
      // 流式输出 + 事件累积
      if (assistantIndex < 0) {
        setMessages((current) => {
          assistantIndex = current.length;
          return [...current, { role: 'assistant', content: '' }];
        });
      } else {
        // 重试 —— 复用原来那条空位 ✓（不重复摆一遍问题 ✓）。
        setMessages((current) => {
          const next = current.slice();
          const existing = next[assistantIndex];
          if (!existing || existing.role !== 'assistant') return current;
          next[assistantIndex] = { role: 'assistant', content: '' };
          return next;
        });
      }
      const toolCalls: ToolCallState[] = [];
      const toolIndexById = new Map<string, number>();
      let plan: PlanProposal | undefined;
      const artifacts: ArtifactReady[] = [];
      const attachments: AttachmentReady[] = [];
      const workflowRuns: { id: string; workflow_name: string; status: 'started' | 'succeeded' | 'failed' | 'cancelled' }[] = [];
      const knowledgeHits: { query: string; hits: { id: string; title: string; snippet: string; score: number }[]; degraded?: boolean } = { query: '', hits: [] };
      // ⚠️ **降级标记** ✓（后端每一块都带 ✓）—— 用户要看得见 ✓
      // （召回 / 压缩降级时回答是不完整的 ✓ —— 不说就是骗 ✓）。
      const degradedFlags = new Set<string>();
      await streamCopilotTurn(sid, content, (event, data) => {
        // ⚠️ **每一块都盖章** ✓（信封上的 `flags` ✓ —— 读哪块都一样 ✓）。
        if (Array.isArray(data.flags)) {
          let changed = false;
          for (const flag of data.flags as string[]) {
            if (flag && !degradedFlags.has(flag)) {
              degradedFlags.add(flag);
              changed = true;
            }
          }
          if (changed) patchAssistant((message) => ({ ...message, degraded: [...degradedFlags] }));
        }
        if (event === 'queued') {
          // ⚠️ **排队中** ✓（Router Stage 3 ✓）—— 不显示的话用户只看到转圈
          // ✗✗（后端每个轮询周期都发一块 ✓ —— 所以文案要**稳定** ✓ ——
          // 否则每秒一条提示 ✗✗）。
          const position = Number(data.position || 0);
          setNotices((current) => pushNotice(current, `排队中（第 ${position} 位）`));
        }
        if (event === 'message') {
          const chunk = String(data.content || '');
          if (chunk) {
            // flushSync: 强制同步重渲染, 避免 React 18 把多个 chunk 的
            // setMessages 批处理成一次渲染 (用户会看到"一下子全出来").
            // 流式 chat 的关键路径 — 切勿合并到 startTransition.
            flushSync(() => {
              patchAssistant((message) => ({ ...message, content: message.content + chunk }));
            });
          }
        }
        if (event === 'tool_call') {
          const tcId = String(data.tool_call_id || '');
          const tc: ToolCallState = {
            id: tcId,
            tool_name: String(data.tool_name || 'tool'),
            status: 'running',
            arguments: (data.arguments as Record<string, unknown>) || {},
          };
          toolIndexById.set(tcId, toolCalls.length);
          toolCalls.push(tc);
        }
        if (event === 'tool_result') {
          const tcId = String(data.tool_call_id || '');
          const outIdx = toolIndexById.get(tcId);
          if (outIdx != null) {
            const tc = toolCalls[outIdx];
            tc.status = data.is_error ? 'failed' : 'succeeded';
            tc.output = typeof data.output === 'string' ? data.output : JSON.stringify(data.output);
            tc.latency_ms = Number(data.latency_ms || 0);
          }
          // Phase 14: delegate_to_agent 是真派发 (sub-agent 同步跑完),
          // 工具结果里带 _meta.subagent_dispatched. 这里把结果摘要 push 成
          // 一条提示 — 父 turn 继续生成, 用户只是被通知 "X 帮我处理完了, 用时 Ns".
          if (
            outIdx != null &&
            toolCalls[outIdx]?.tool_name === 'delegate_to_agent' &&
            data.is_error === false
          ) {
            try {
              const parsed = typeof data.output === 'string'
                ? JSON.parse(data.output) as { _meta?: { subagent_dispatched?: boolean; sub_session_id?: string; duration_ms?: number; status?: string }; error_code?: string; error?: string }
                : null;
              const meta = parsed?._meta;
              if (meta?.subagent_dispatched) {
                const dur = Math.round((meta.duration_ms || 0) / 100) / 10;
                const status = meta.status === 'succeeded' ? '✓' : '✗';
                setNotices((current) => pushNotice(
                  current,
                  `${status} 已派给子智能体, 用时 ${dur}s (${meta.sub_session_id?.slice(0, 8) ?? '?'})`,
                ));
              } else if (parsed?.error_code) {
                setNotices((current) => pushNotice(
                  current,
                  `派发失败: ${parsed.error_code} — ${parsed.error ?? ''}`,
                ));
              }
            } catch {
              // 解析失败就静默 — 不阻塞主流程
            }
          }
        }
        if (event === 'knowledge_search') {
          knowledgeHits.query = String(data.query || '');
          knowledgeHits.hits = Array.isArray(data.hits)
            ? (data.hits as { id?: string; title?: string; snippet?: string; score?: number }[]).map((h, i) => ({
                id: String(h.id ?? `hit-${i}`),
                title: String(h.title ?? '未命名片段'),
                snippet: String(h.snippet ?? ''),
                score: Number(h.score ?? 0),
              }))
            : [];
          knowledgeHits.degraded = Boolean(data.degraded);
        }
        if (event === 'workflow_invocation') {
          const id = String(data.invocation_id || '');
          const wname = String(data.workflow_name || '');
          const status = String(data.status || 'started') as 'started' | 'succeeded' | 'failed' | 'cancelled';
          const existing = workflowRuns.find((w) => w.id === id);
          if (existing) existing.status = status;
          else workflowRuns.push({ id, workflow_name: wname, status });
        }
        if (event === 'plan_proposed') {
          plan = {
            plan_id: String(data.plan_id || ''),
            title: String(data.title || '执行计划'),
            steps: Array.isArray(data.steps) ? (data.steps as PlanProposal['steps']) : [],
            reason: String(data.reason || ''),
          };
        }
        if (event === 'artifact_ready') {
          const a = {
            artifact_id: String(data.artifact_id || ''),
            // 后端 ArtifactReadyChunk 通过 Field(alias="kind") 输出 kind_ (避免与 envelope kind 冲突),
            // 优先读 data.kind_, 兜底读 data.kind (兼容老数据)
            kind: (data.kind_ as 'markdown' | 'code' | 'html' | 'json' | 'image' | 'text') || (data.kind as 'markdown') || 'markdown',
            name: String(data.name || 'artifact.md'),
            mime: String(data.mime || 'text/markdown'),
            size_bytes: Number(data.size_bytes || 0),
            download_path: String(data.download_path || ''),
            preview_path: (data.preview_path as string | null | undefined) ?? null,
            snippet: String(data.snippet || ''),
          };
          artifacts.push(a);
        }
        if (event === 'attachment_ready') {
          attachments.push({
            attachment_id: String(data.attachment_id || ''),
            name: String(data.name || 'attachment'),
            mime: String(data.mime || ''),
            size_bytes: Number(data.size_bytes || 0),
            download_path: String(data.download_path || ''),
          });
        }
        if (event === 'approval_required') {
          setPendingApproval({
            id: String(data.approval_id || ''),
            toolName: String(data.tool_name || '工具'),
            reason: String(data.reason || '需要确认后才会执行'),
          });
        }
        if (event === 'usage') {
          const usage = {
            inputTokens: Number(data.input_tokens || 0),
            outputTokens: Number(data.output_tokens || 0),
            costUsd: Number(data.cost_usd || 0),
          };
          patchAssistant((message) => ({ ...message, usage }));
        }
        if (event === 'skill_invocation') {
          // 技能执行状态 — 合并进对应的工具调用条目.
          const tcId = String(data.tool_call_id || '');
          const outIdx = toolIndexById.get(tcId);
          if (outIdx != null) {
            const tc = toolCalls[outIdx];
            const status = String(data.status || '');
            if (status === 'succeeded') tc.status = 'succeeded';
            else if (status === 'failed') tc.status = 'failed';
          }
        }
        if (event === 'context_compacted') setNotices((n) => pushNotice(n, '上下文已压缩'));
        if (event === 'memory_write') setNotices((n) => pushNotice(n, '已写入记忆'));
        if (event === 'done') {
          const final = String(data.final_message || '');
          if (final) {
            flushSync(() => {
              patchAssistant((message) => ({ ...message, content: final }));
            });
          }
        }
        if (event === 'interactive_action') {
          // 5 个 stub tool (ask_user_question / notify_user / plan_submit /
          // todo_write / delegate_to_agent) 完成后, backend 在 tool_result
          // chunk 之后再发一个 interactive_action chunk. 这里接到后分派到
          // store, 让 <InteractionHost> 渲染对应 UI.
          const callId = String(data.call_id || '')
          const action = String(data.action || '') as
            | 'show_question_card'
            | 'toast'
            | 'render_plan'
            | 'render_todo_list'
            | 'delegate_agent'
          const payload = (data.payload && typeof data.payload === 'object'
            ? (data.payload as Record<string, unknown>)
            : {}) as Record<string, unknown>
          if (action === 'delegate_agent') {
            // Phase 14: delegate_to_agent 现在走真派发, 不再 emit
            // interactive_action chunk. 这里保留分支是兜底 (旧 backend /
            // 测试桩可能仍 emit), 但只 push 提示, 不再 router.push —
            // LLM 拿到 sub-agent 结果会继续生成, 父 turn 不需要换页.
            void (async () => {
              const targetAgentId = String(payload.agent_id || '');
              const taskPreview = typeof payload.task === 'string'
                ? payload.task.slice(0, 24)
                : '?';
              setNotices((current) => pushNotice(
                current,
                `已派给子智能体 ${targetAgentId.slice(0, 8)} (任务: ${taskPreview})`,
              ));
            })()
          } else {
            handleInteractiveAction(
              callId,
              action,
              payload,
              async (resolvedPayload) => {
                // 把用户答案 POST 给后端, 留 audit log + transcript
                if (!sessionId) return
                await getApiClient()
                  .post(
                    `/api/sessions/${sessionId}/interactive/answer`,
                    { call_id: callId, action, payload: resolvedPayload },
                  )
                  .catch(() => {
                    // audit 失败不阻塞 UI
                  })
                // 通知 store 关闭 (render_plan / show_question_card 自己也会
                // 通过 onResolve 关闭, 这里双保险)
                if (action === 'render_plan') dismissPlan()
                if (action === 'show_question_card') dismissQuestion()
              },
            )
          }
        }
        if (event === 'error') {
          // 不在这里 pushNotice, 让 streamCopilotTurn 的 throw 走 sendMessage 的 catch
          // (统一出口 + dedupe 避免双显示)
        }
      }, controller.signal, clientRequestId);
      // 把累积的 extras / plan / artifacts / attachments 写回这条 assistant 消息
      patchAssistant((message) => {
        const extras = {
          toolCalls: toolCalls.length ? toolCalls.slice() : undefined,
          workflowRuns: workflowRuns.length ? workflowRuns.slice() : undefined,
          knowledgeHits: knowledgeHits.hits.length ? knowledgeHits : undefined,
        };
        return {
          ...message,
          tools: toolCalls.map((t) => t.tool_name),
          extras,
          plan,
          artifacts: artifacts.length ? artifacts : undefined,
          attachments: attachments.length ? attachments : undefined,
          degraded: degradedFlags.size ? [...degradedFlags] : message.degraded,
          durationMs: Date.now() - turnStartedAt,
        };
      });
      // ⚠️ **轮次 +1** ✓ —— 头部的「N 轮」要跟着长 ✓。
      setSessionInfo((current) => ({ ...current, turnCount: (current.turnCount ?? 0) + 1 }));
      void listCopilotSessions({ search }).then(setSessions).catch((error) => setNotices((current) => pushNotice(current, `查询失败：${String(error)}`)));
    } catch (error) {
      if (controller.signal.aborted) {
        // 用户主动停止 —— 不是错误 ✓（但要看得见 ✓）。
        patchAssistant((message) => ({
          ...message,
          durationMs: Date.now() - turnStartedAt,
          error: { title: '已停止生成', message: '这一轮在生成途中停下了。', kind: 'generic' },
        }));
      } else {
        const norm = normalizeError(error);
        const raw = norm.message;
        // 把 503 / PROVIDER_UNAVAILABLE 翻译成"未配置 LLM 供应商"提示.
        //
        // 判据用**结构化的 status/code**, 不要去正则匹配错误文案 ——
        // 流式请求失败的消息是 "流式请求失败（HTTP 503）", 括号是全角的,
        // 匹配 ASCII 括号的正则从来没生效过, 提示语一直退化成原始报错.
        if (/DUPLICATE_REQUEST/.test(raw)) {
          // 同一个请求已经跑过了 —— 静默忽略, 不要当成错误.
          return;
        }
        const isProvider =
          norm.code === 'PROVIDER_UNAVAILABLE' ||
          norm.status === 503 ||
          /PROVIDER_UNAVAILABLE/.test(raw);
        // ⚠️ **用户侧去不了管理台** ✓（member 只能走非 /admin 路径 ✓）——
        // 所以这里**不给死链接** ✓（点了只会弹回首页 ✗✗）—— 写清楚找谁 ✓。
        const friendly = isProvider
          ? '当前环境未配置 LLM 供应商, 无法生成回答. 请联系管理员在「模型管理 → 新建供应商」配置 API key 后重试.'
          : raw;
        patchAssistant((message) => ({
          ...message,
          durationMs: Date.now() - turnStartedAt,
          error: {
            title: '这一轮没跑完',
            message: friendly,
            code: norm.code,
            kind: isProvider ? 'provider' : 'generic',
          },
        }));
      }
    } finally {
      abortRef.current = null;
      setIsSending(false);
    }
  };

  // 自动滚到底
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages]);

  const handleDeleteSession = async (id: string | undefined) => {
    if (!id) return;
    if (!window.confirm('确认删除这条对话？删除后无法恢复。')) return;
    try {
      await deleteCopilotSession(id);
      setSessions((current) => current.filter((s) => s.id !== id));
      if (sessionId === id) {
        setSessionId(undefined);
        setMessages([]);
        setTurns([]);
        setSessionInfo({});
      }
    } catch (error) {
      setNotices((current) => pushNotice(current, `删除失败：${String(error)}`));
    }
  };
  const resolveApproval = async (approved: boolean) => {
    if (!sessionId || !pendingApproval) return;
    setIsSending(true);
    try {
      let assistant = '';
      await decideCopilotApproval(sessionId, pendingApproval.id, approved, (event, data) => {
        if (event === 'message') assistant += String(data.content || '');
        if (event === 'done') assistant = String(data.final_message || assistant);
      });
      setPendingApproval(null);
      if (assistant) setMessages((current) => [...current, { role: 'assistant', content: assistant }]);
    } catch (error) { setNotices((current) => pushNotice(current, `审批失败：${String(error)}`)); } finally {
      setIsSending(false);
    }
  };
  const handleAttachment = async (file: File) => {
    // 演示环境同样真上传 —— 演示后端有真的附件端点. 以前演示模式下只把
    // 文件名写进输入框, 附件根本不存在.
    if (!sessionId) { setNotices((current) => pushNotice(current, '请先打开会话，再上传附件。')); return; }
    try {
      const form = new FormData();
      form.append('file', file);
      const result = await getApiClient().upload<{ id: string }>(`/api/sessions/${sessionId}/attachments`, form);
      if (!result?.id) throw new Error('后端未返回附件 ID');
      setInput((current) => `${current}\n[附件: ${file.name}, ID: ${result.id}]`);
    } catch (error) { setNotices((current) => pushNotice(current, `上传失败：${String(error)}`)); }
  };

  // ── 视图数据 ──────────────────────────────────────────────────────
  const apiTurns = useMemo(() => new Map(turns.map((turn) => [turn.turnId, turn])), [turns]);
  const turnViews = useMemo(() => buildTurns(messages), [messages]);
  const displayAgentName = sessionInfo.agentName || agentName;
  const headerStatus = isSending
    ? 'running'
    : pendingApproval || sessionInfo.waitingApproval
      ? 'waiting_approval'
      : 'idle';
  const headerTurnCount = sessionInfo.turnCount ?? turns.length;
  const isEmpty = messages.length === 0;

  return (
    <div className="flex min-h-0 h-full flex-1 flex-row overflow-hidden bg-[var(--bg-elevated)]">
      {sessionListOpen ? <div className="fixed inset-0 z-40 bg-slate-950/40 lg:hidden" onClick={() => setSessionListOpen(false)} aria-hidden="true" /> : null}
      <aside
        className={`${sessionListOpen ? 'fixed inset-y-0 left-0 z-50 flex w-72' : 'hidden'} min-h-0 shrink-0 flex-col border-r border-[var(--border)] bg-[var(--surface-1)] lg:static lg:z-auto lg:flex lg:w-64`}
      >
        <div className="flex items-center justify-between border-b border-[var(--border)] p-4">
          <h2 className="text-sm font-semibold">对话</h2>
          <button
            type="button"
            onClick={() => {
              // 新建 (清空当前会话 + 消息栈, 不导航)
              setSessionId(undefined);
              setMessages([]);
              setTurns([]);
              setSessionInfo({});
              setPendingApproval(null);
              setNotices([]);
              setInput('');
              setSessionListOpen(false);
            }}
            className="rounded-md p-1.5 text-[var(--text-muted)] hover:bg-[var(--bg-hover)]"
            aria-label="新建对话"
            title="新建对话"
          >
            <Plus className="h-4 w-4" />
          </button>
        </div>
        <div className="p-3">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="搜索对话"
              aria-label="搜索对话"
              className="h-9 w-full rounded-md border border-[var(--border)] bg-[var(--bg-elevated)] pl-8 pr-2 text-xs outline-none focus:border-[var(--brand)]"
            />
          </div>
        </div>
        <div className="flex-1 overflow-auto px-2">
          <p className="px-2 py-2 text-[11px] font-semibold text-[var(--text-muted)]">最近对话</p>
          {sessions.length === 0 ? (
            <p className="px-2 py-3 text-[11px] leading-5 text-[var(--text-muted)]">
              {search ? '没有匹配的对话。' : '还没有对话 —— 问一句就开始。'}
            </p>
          ) : null}
          {sessions.map((item) => (
            <SessionListItem
              key={item.id ?? item.title}
              session={item}
              active={sessionId === item.id}
              onSelect={() => {
                setSessionListOpen(false);
                if (!item.id) return;
                // 先清当前消息栈, 避免切换 session 时新旧消息混在一起闪
                setMessages([]);
                setTurns([]);
                setPendingApproval(null);
                setSessionId(item.id);
                setSessionInfo({
                  agentName: item.agentName || undefined,
                  model: item.model || undefined,
                  turnCount: item.turnCount ?? 0,
                  waitingApproval: item.waitStatus === 'waiting_approval',
                });
              }}
              onDelete={() => void handleDeleteSession(item.id)}
            />
          ))}
        </div>
      </aside>

      <main className="flex min-h-0 min-w-0 flex-1 flex-col">
        <ConversationHeader
          agentName={displayAgentName}
          skillName={skillName}
          model={sessionInfo.model}
          status={headerStatus}
          turnCount={headerTurnCount}
          onOpenSessions={() => setSessionListOpen(true)}
        />

        {isEmpty ? (
          // 空态: welcome + composer 一起垂直居中
          <div className="flex flex-1 flex-col items-center justify-center overflow-auto px-5 py-8 sm:px-10">
            <div className="flex w-full max-w-4xl flex-col items-center gap-8">
              {notices.length ? (
                // 空态也要能看到提示 —— 否则"没有会话就上传附件"这类错误
                // 在默认界面里完全静默.
                <div className="w-full max-w-2xl rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-xs font-semibold text-amber-900">
                  {notices[notices.length - 1]}
                </div>
              ) : null}
              {!entry?.agentId ? (
                // 没选智能体: 顶部显眼提示 (不是右下 notice, notice 只在非空态显示)
                <div className="w-full max-w-2xl rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-xs text-amber-900">
                  <p className="font-semibold">要先选一个智能体才能开始对话</p>
                  <p className="mt-1 text-amber-800">从智能体库选一个, 然后刷新这个页面 (或点"更换智能体").</p>
                </div>
              ) : null}
              <div className="flex flex-col items-center text-center">
                <span className="grid h-14 w-14 place-items-center rounded-2xl bg-[var(--brand-light)] text-[var(--brand)]">
                  <Sparkles className="h-7 w-7" />
                </span>
                <h2 className="mt-5 text-2xl font-semibold tracking-tight text-[var(--text)]">
                  {displayAgentName ? `开始与${displayAgentName}协作` : '开始一项工作'}
                </h2>
                <p className="mt-2 max-w-md text-sm leading-6 text-[var(--text-muted)]">
                  {displayAgentName
                    ? '用一句话说明目标与约束, 即可开始对话. 智能体会调用工具、知识与工作流, 答案与产物直接留在这一页.'
                    : '说明目标、范围与期望产出, 从常用开场快速开始. 智能体会调用工具、知识与工作流, 答案与产物直接留在这一页.'}
                </p>
                {!displayAgentName ? (
                  <Link
                    to="/library?tab=agents"
                    className="mt-4 inline-flex items-center gap-1.5 rounded-lg border border-[var(--brand)] bg-[var(--brand-light)] px-3 py-1.5 text-xs font-semibold text-[var(--brand)] transition hover:bg-[var(--brand)] hover:text-white"
                  >
                    去智能体库选一个智能体 →
                  </Link>
                ) : null}
              </div>
              <div className="grid w-full max-w-3xl gap-2 sm:grid-cols-3">
                {(() => {
                  const pool = getStarters();
                  return (displayAgentName && entry?.agentExample
                    ? [entry.agentExample, ...pool.slice(1)]
                    : pool
                  ).map((starter) => (
                  <button
                    type="button"
                    key={starter}
                    onClick={() => {
                      void sendMessage(starter);
                    }}
                    className="rounded-xl border border-[var(--border)] bg-[var(--surface-1)] p-3 text-left text-xs leading-5 text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]"
                  >
                    {starter}
                  </button>
                  ));
                })()}
              </div>
              <div className="w-full max-w-3xl">
                <Composer
                  input={input}
                  onInputChange={setInput}
                  onSubmit={() => void sendMessage()}
                  onStop={() => void stopSending()}
                  isSending={isSending}
                  onAttach={(file) => void handleAttachment(file)}
                />
              </div>
            </div>
          </div>
        ) : (
          // 有消息: 上滚动 + 下贴底 composer
          <>
            <div className="flex-1 overflow-y-auto">
              <div className="mx-auto flex min-h-full w-full max-w-4xl flex-col px-5 py-6 sm:px-10">
                {notices.length ? (
                  // ⚠️ **瞬时提示** ✓ —— 排队 / 压缩 / 派发这类 ✓ —— 不是错误 ✓
                  // （错误在**那一轮里** ✓ —— 失败卡片 ✓）。
                  <div className="mb-4 flex flex-wrap gap-1.5">
                    {notices.slice(-3).map((notice, index) => (
                      <span
                        key={`${notice}-${index}`}
                        className="rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1 text-[11px] text-amber-900"
                      >
                        {notice}
                      </span>
                    ))}
                  </div>
                ) : null}
                {pendingApproval ? (
                  <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-xs text-amber-900">
                    <span>
                      待确认:{pendingApproval.toolName} · {pendingApproval.reason}
                    </span>
                    <span className="flex gap-2">
                      <button
                        type="button"
                        className="rounded-md bg-amber-700 px-3 py-1 text-white"
                        onClick={() => void resolveApproval(true)}
                      >
                        批准
                      </button>
                      <button
                        type="button"
                        className="rounded-md border border-amber-700 px-3 py-1"
                        onClick={() => void resolveApproval(false)}
                      >
                        拒绝
                      </button>
                    </span>
                  </div>
                ) : null}
                <div className="space-y-9 pb-8">
                  {turnViews.map((turn) => {
                    const facts = resolveTurnFacts(turn, apiTurns);
                    const isLast = turn === turnViews[turnViews.length - 1];
                    return (
                      <TurnBlock
                        key={turn.key}
                        turn={turn}
                        facts={facts}
                        sessionId={sessionId}
                        streaming={isSending && isLast}
                        feedback={feedbackGiven[turn.key]}
                        onFeedback={(rating) => void sendFeedback(turn.key, turn.turnId, rating)}
                        onRetry={
                          turn.question && turn.answerIndex != null
                            ? () => void sendMessage(undefined, {
                              retry: {
                                question: turn.question?.content ?? '',
                                assistantIndex: turn.answerIndex ?? -1,
                              },
                            })
                            : undefined
                        }
                      />
                    );
                  })}
                </div>
                <div ref={messagesEndRef} />
              </div>
            </div>
            <div className="border-t border-[var(--border)] bg-[var(--surface-1)] p-4 sm:p-5">
              <div className="mx-auto max-w-4xl">
                <Composer
                  input={input}
                  onInputChange={setInput}
                  onSubmit={() => void sendMessage()}
                  onStop={() => void stopSending()}
                  isSending={isSending}
                  onAttach={(file) => void handleAttachment(file)}
                />
              </div>
            </div>
          </>
        )}
      </main>
      <InteractionHost />
    </div>
  );
}
