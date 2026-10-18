import { runtimeConfig } from '@/lib/api-mode';
import { getApiClient } from '@qzdap/web-api';
import {
  ArrowUp,
  Bot,
  Menu,
  Paperclip,
  Plus,
  Search,
  Settings2,
  Sparkles,
  Trash2,
} from 'lucide-react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { flushSync } from 'react-dom';
import { useEffect, useRef, useState } from 'react';
import type { CopilotSession } from './schema';
import {
  InteractiveProvider,
  useInteractive,
} from './interactiveStore';
import { InteractionHost } from './InteractionHost';
import { MarkdownView } from '@/features/agents/components/MarkdownView';
import {
  createCopilotSession,
  decideCopilotApproval,
  deleteCopilotSession,
  listCopilotSessions,
  loadCopilotSession,
  streamCopilotTurn,
  type ChatMessage,
} from './copilotApi';
import {
  AttachmentChip,
  type AttachmentReady,
} from './blocks/AttachmentChip';
import {
  ArtifactCard,
  type ArtifactReady,
} from './blocks/ArtifactCard';
import {
  MessageExtrasView,
  type MessageExtras,
  type ToolCallState,
} from './blocks/MessageExtrasView';
import {
  PlanProposalCard,
  type PlanProposal,
} from './blocks/PlanProposalCard';

type Message = ChatMessage & {
  extras?: MessageExtras;
  plan?: PlanProposal;
  artifacts?: ArtifactReady[];
  attachments?: AttachmentReady[];
};
type CopilotEntryState = { knowledgeTitle?: string; agentId?: string; agentName?: string; agentExample?: string; skillName?: string; sessionId?: string };

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
 * CopilotTypingIndicator: 流式生成中占位.
 * 三个点交错闪 + 文字 1.2s 周期轮换, 模拟"在写"的活跃感.
 * deepseek first-token 1.5-7s, 没有这个用户会以为卡死.
 */
const TYPING_PHRASES = ['我在想呢…', '打字中…', '马上就好~', '让我看看…', '嗯,再琢磨一下', '等我一下'];
const CopilotTypingIndicator = () => {
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => setIdx((i) => (i + 1) % TYPING_PHRASES.length), 1200);
    return () => window.clearInterval(t);
  }, []);
  return (
    <div
      data-testid="copilot-generating"
      className="flex items-center gap-2 text-[var(--text-muted)]"
      role="status"
      aria-live="polite"
    >
      <span className="inline-flex items-end gap-0.5" aria-hidden="true">
        <span
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--brand)]"
          style={{ animationDelay: '0ms', animationDuration: '900ms' }}
        />
        <span
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--brand)]"
          style={{ animationDelay: '150ms', animationDuration: '900ms' }}
        />
        <span
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--brand)]"
          style={{ animationDelay: '300ms', animationDuration: '900ms' }}
        />
      </span>
      <span
        key={idx}
        className="text-sm tabular-nums animate-[fadein_300ms_ease-out]"
      >
        {TYPING_PHRASES[idx]}
        <span className="ml-0.5 inline-block w-3 animate-pulse">▍</span>
      </span>
    </div>
  );
};

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
const composerOptions = {
  slash: [
    { label: '/整理', value: '/整理 ' },
    { label: '/总结', value: '/总结 ' },
    { label: '/生成', value: '/生成 ' },
  ],
  mention: [
    { label: '@智能体', value: '@智能体 ' },
    { label: '@团队成员', value: '@团队成员 ' },
    { label: '@知识库', value: '@知识库 ' },
  ],
} as const;

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
  const navigate = useNavigate();
  const demoMode = runtimeConfig().dataMode === 'demo';
  const entry = location.state as CopilotEntryState | null;
  const agentName = entry?.agentName;
  const knowledgeTitle = entry?.knowledgeTitle;
  const skillName = entry?.skillName;
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [sessions, setSessions] = useState<CopilotSession[]>([]);
  const [sessionId, setSessionId] = useState<string | undefined>(entry?.sessionId);
  const [pendingApproval, setPendingApproval] = useState<{ id: string; toolName: string; reason: string } | null>(null);
  const [notices, setNotices] = useState<string[]>([]);
  useEffect(() => {
    void listCopilotSessions().then(setSessions).catch((error) => setNotices((current) => pushNotice(current, `查询失败：${String(error)}`)));
  }, []);
  useEffect(() => {
    // 发送中时不要触发重载, 避免 race:
    // sendMessage 已经把 user message push 进 messages, 紧跟着 setSessionId
    // 会触发本 effect, loadCopilotSession 返回空 / 旧数据 → setMessages([])
    // 把刚加的 user message 覆盖掉, 页面就只剩空态.
    if (!sessionId || isSending) return;
    void loadCopilotSession(sessionId).then((detail) => {
      if (!detail) { setMessages([]); setPendingApproval(null); return; }
      const loaded = (detail.messages || [])
        .filter((item) => item.role === 'user' || item.role === 'assistant')
        .map((item) => ({ role: item.role as 'user' | 'assistant', content: item.content }));
      setMessages(loaded);
      setPendingApproval(null);
      const pending = detail.pendingApproval;
      if (pending) {
        setPendingApproval({
          id: String(pending.approval_id || pending.approvalId || ''),
          toolName: String(pending.tool_name || pending.toolName || '工具'),
          reason: String(pending.reason || '需要确认后才会执行'),
        });
      }
    }).catch((error) => { setMessages([]); setNotices((current) => pushNotice(current, `详情加载失败：${String(error)}`)); });
  }, [sessionId, isSending]);
  const [composerMenu, setComposerMenu] = useState<'slash' | 'mention' | null>(null);
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
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const sendMessage = async (value = input) => {
    const content = value.trim();
    if (!content || isSending) return;
    setIsSending(true);
    setMessages((current) => [...current, { role: 'user', content }]);
    setInput('');
    setComposerMenu(null);
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
        if (sid) setSessionId(sid);
      }
      if (!sid) {
        // 没有 agent 上下文: 回滚刚 push 的 user 消息, 给一个跳转提示, 不污染消息栈.
        setMessages((current) => current.slice(0, -1));
        setNotices((current) => pushNotice(current, '需要先选一个智能体才能开始对话 → 去智能体库选一个'));
        return;
      }
      // 流式输出 + 事件累积
      let assistantIndex = -1;
      setMessages((current) => {
        assistantIndex = current.length;
        return [...current, { role: 'assistant', content: '', tools: [] }];
      });
      const toolCalls: ToolCallState[] = [];
      const toolIndexById = new Map<string, number>();
      let plan: PlanProposal | undefined;
      const artifacts: ArtifactReady[] = [];
      const attachments: AttachmentReady[] = [];
      const workflowRuns: { id: string; workflow_name: string; status: 'started' | 'succeeded' | 'failed' | 'cancelled' }[] = [];
      const knowledgeHits: { query: string; hits: { id: string; title: string; snippet: string; score: number }[]; degraded?: boolean } = { query: '', hits: [] };
      await streamCopilotTurn(sid, content, (event, data) => {
        if (event === 'message') {
          const chunk = String(data.content || '');
          if (chunk) {
            // flushSync: 强制同步重渲染, 避免 React 18 把多个 chunk 的
            // setMessages 批处理成一次渲染 (用户会看到"一下子全出来").
            // 流式 chat 的关键路径 — 切勿合并到 startTransition.
            flushSync(() => {
              setMessages((current) => {
                const idx = assistantIndex < 0 ? current.length - 1 : assistantIndex;
                const next = current.slice();
                const existing = next[idx];
                if (!existing || existing.role !== 'assistant') return current;
                next[idx] = { ...existing, content: existing.content + chunk };
                return next;
              });
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
          setMessages((current) => {
            const idx = assistantIndex < 0 ? current.length - 1 : assistantIndex;
            const next = current.slice();
            const existing = next[idx];
            if (!existing || existing.role !== 'assistant') return current;
            return next;
          });
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
            toolCalls[outIdx]?.name === 'delegate_to_agent' &&
            data.is_error === false
          ) {
            try {
              const parsed = typeof data.output === 'string'
                ? JSON.parse(data.output) as { _meta?: { subagent_dispatched?: boolean; sub_session_id?: string; duration_ms?: number; status?: string }; error_code?: string }
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
          const a: ArtifactReady = {
            artifact_id: String(data.artifact_id || ''),
            // 后端 ArtifactReadyChunk 通过 Field(alias="kind") 输出 kind_ (避免与 envelope kind 冲突),
            // 优先读 data.kind_, 兜底读 data.kind (兼容老数据)
            kind: (data.kind_ as ArtifactReady['kind']) || (data.kind as ArtifactReady['kind']) || 'markdown',
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
        if (event === 'context_compacted') setNotices((n) => pushNotice(n, '上下文已压缩'));
        if (event === 'memory_write') setNotices((n) => pushNotice(n, '已写入记忆'));
        if (event === 'done') {
          const final = String(data.final_message || '');
          if (final) {
            flushSync(() => {
              setMessages((current) => {
                const idx = assistantIndex < 0 ? current.length - 1 : assistantIndex;
                const next = current.slice();
                const existing = next[idx];
                if (!existing || existing.role !== 'assistant') return current;
                next[idx] = { ...existing, content: final };
                return next;
              });
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
      });
      // 把累积的 extras / plan / artifacts / attachments 写回这条 assistant 消息
      setMessages((current) => {
        const idx = assistantIndex < 0 ? current.length - 1 : assistantIndex;
        const next = current.slice();
        const existing = next[idx];
        if (!existing || existing.role !== 'assistant') return current;
        const extras: MessageExtras = {
          toolCalls: toolCalls.length ? toolCalls.slice() : undefined,
          workflowRuns: workflowRuns.length ? workflowRuns.slice() : undefined,
          knowledgeHits: knowledgeHits.hits.length ? knowledgeHits : undefined,
        };
        next[idx] = {
          ...existing,
          tools: toolCalls.map((t) => t.tool_name),
          extras,
          plan,
          artifacts: artifacts.length ? artifacts : undefined,
          attachments: attachments.length ? attachments : undefined,
        };
        return next;
      });
      void listCopilotSessions().then(setSessions).catch((error) => setNotices((current) => pushNotice(current, `查询失败：${String(error)}`)));
    } catch (error) {
      const raw = error instanceof Error ? error.message : String(error);
      // 把 503 / PROVIDER_UNAVAILABLE 翻译成"未配置 LLM 供应商"提示,
      // 引导用户去 /admin/models/new. 历史文案里 "QZDAP_LLM_PROVIDER /
      // QZDAP_LLM_API_KEY" 的 .env 提示已下线, 统一走管理侧.
      const friendly =
        /PROVIDER_UNAVAILABLE/.test(raw) || /\(HTTP\s*503\)/.test(raw)
          ? '当前后端未配置 LLM 供应商, 无法对话. 请到 管理 → 模型管理 → 新建供应商 配置 API key 后再试.'
          : raw;
      setNotices((current) => pushNotice(current, `请求失败：${friendly}`));
    } finally {
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
    if (demoMode) {
      setInput((current) => `${current}\n[附件: ${file.name}]`);
      return;
    }
    if (!sessionId) { setNotices((current) => pushNotice(current, '请先打开会话，再上传附件。')); return; }
    try {
      const form = new FormData();
      form.append('file', file);
      const result = await getApiClient().upload<{ id: string }>(`/api/sessions/${sessionId}/attachments`, form);
      if (!result?.id) throw new Error('后端未返回附件 ID');
      setInput((current) => `${current}\n[附件: ${file.name}, ID: ${result.id}]`);
    } catch (error) { setNotices((current) => pushNotice(current, `上传失败：${String(error)}`)); }
  };
  const selectComposerOption = (value: string) => {
    setInput((current) => `${current.slice(0, -1)}${value}`);
    setComposerMenu(null);
  };

  // ------------------------------------------------------------------
  // Composer 子组件, 让 empty / non-empty 状态都能复用
  // ------------------------------------------------------------------
  const Composer = (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        void sendMessage();
      }}
      className="w-full"
    >
      {composerMenu ? (
        <div role="status" aria-live="polite" className="mb-2 rounded-xl border border-[var(--border)] bg-[var(--surface-1)] p-2 shadow-[var(--shadow-xs)]">
          <div className="flex items-center justify-between px-2 pb-2 text-[10px] text-[var(--text-muted)]">
            <span className="font-semibold text-[var(--text-secondary)]">
              {composerMenu === 'slash' ? '快捷命令' : '提及对象'}
            </span>
            <span>已识别 {composerMenu === 'slash' ? '/' : '@'}</span>
          </div>
          <div role="listbox" aria-label={composerMenu === 'slash' ? '快捷命令列表' : '提及对象列表'} className="flex gap-1 overflow-x-auto">
            {composerOptions[composerMenu].map((option) => (
              <button
                key={option.label}
                type="button"
                role="option"
                aria-selected="false"
                onClick={() => selectComposerOption(option.value)}
                className="shrink-0 rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs text-[var(--text-secondary)] hover:border-[var(--brand)] hover:bg-[var(--brand-light)] hover:text-[var(--brand)]"
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      ) : null}
      <div className="flex items-end gap-2 rounded-2xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] p-2 shadow-[var(--shadow-xs)] focus-within:border-[var(--brand)]">
        <button
          type="button"
          className="rounded-lg p-2 text-[var(--text-muted)] hover:bg-[var(--bg-hover)]"
          aria-label="添加附件"
          onClick={() => document.getElementById('copilot-file-input')?.click()}
        >
          <Paperclip className="h-4 w-4" />
          <input
            type="file"
            className="hidden"
            id="copilot-file-input"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) {
                void handleAttachment(file);
                setComposerMenu(null);
                event.currentTarget.value = '';
              }
            }}
          />
        </button>
        <textarea
          value={input}
          onChange={(event) => {
            const value = event.target.value;
            setInput(value);
            if (value.endsWith('/') || value.endsWith('@')) setComposerMenu(value.endsWith('/') ? 'slash' : 'mention');
            else setComposerMenu(null);
          }}
          onKeyDown={(event) => {
            if (event.key === 'Escape' && composerMenu) {
              event.preventDefault();
              setComposerMenu(null);
              return;
            }
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              void sendMessage();
            }
          }}
          rows={1}
          placeholder="描述你想完成的工作..."
          className="max-h-32 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none placeholder:text-[var(--text-muted)]"
        />
        <button
          type="submit"
          disabled={!input.trim() || isSending}
          className="grid h-9 w-9 place-items-center rounded-lg bg-[var(--brand)] text-white disabled:cursor-not-allowed disabled:opacity-40"
          aria-label="发送消息"
        >
          <ArrowUp className="h-4 w-4" />
        </button>
      </div>
      <p className="mt-2 text-center text-[10px] text-[var(--text-muted)]">
        智能体可能会出错，请检查重要结果和来源。
      </p>
    </form>
  );

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
              placeholder="搜索对话"
              className="h-9 w-full rounded-md border border-[var(--border)] bg-[var(--bg-elevated)] pl-8 pr-2 text-xs outline-none focus:border-[var(--brand)]"
            />
          </div>
        </div>
        <div className="flex-1 overflow-auto px-2">
          <p className="px-2 py-2 text-[11px] font-semibold text-[var(--text-muted)]">最近对话</p>
          {sessions.map((item) => (
            <div
              key={item.id ?? item.title}
              className={`group relative flex w-full cursor-pointer flex-col gap-1 rounded-md px-2.5 py-2.5 text-left ${sessionId === item.id ? 'bg-[var(--brand-light)] text-[var(--brand)]' : 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]'}`}
              onClick={() => {
                setSessionListOpen(false);
                if (item.id) {
                  // 先清当前消息栈, 避免切换 session 时新旧消息混在一起闪
                  setMessages([]);
                  setPendingApproval(null);
                  setSessionId(item.id);
                }
              }}
            >
              <span className="truncate text-xs font-semibold">{item.title}</span>
              <span className="flex items-center justify-between gap-2 text-[10px] text-[var(--text-muted)]">
                <span className="truncate">{item.preview || '会话'}</span>
                <span className="shrink-0 tabular-nums">{item.updatedAt}</span>
              </span>
              {item.id ? (
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    void handleDeleteSession(item.id);
                  }}
                  className="absolute right-1.5 top-1.5 grid h-6 w-6 place-items-center rounded text-[var(--text-muted)] opacity-0 transition hover:bg-[var(--danger-bg)] hover:text-[var(--danger)] group-hover:opacity-100"
                  aria-label={`删除 ${item.title}`}
                  title={`删除 ${item.title}`}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              ) : null}
            </div>
          ))}
        </div>
        <div className="border-t border-[var(--border)] p-3">
          <button type="button" className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-xs text-[var(--text-muted)] hover:bg-[var(--bg-hover)]">
            <Settings2 className="h-4 w-4" />
            对话设置
          </button>
        </div>
      </aside>

      <main className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div className="flex h-14 items-center justify-between border-b border-[var(--border)] bg-[var(--surface-1)] px-4 sm:px-6">
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="rounded-md p-2 text-[var(--text-muted)] hover:bg-[var(--bg-hover)] lg:hidden"
              aria-label="打开对话列表"
              onClick={() => setSessionListOpen(true)}
            >
              <Menu className="h-4 w-4" />
            </button>
            <div>
              <h1 className="text-sm font-semibold">
                {agentName ? `与${agentName}对话` : '工作重点梳理'}
              </h1>
              <p className="text-[11px] text-[var(--text-muted)]">
                {agentName ? '已选择智能体 · 在线会话' : '智能体协作 · 多轮对话'}
              </p>
            </div>
          </div>
        </div>

        {isEmpty ? (
          // 空态: welcome + composer 一起垂直居中
          <div className="flex flex-1 flex-col items-center justify-center overflow-auto px-5 py-8 sm:px-10">
            <div className="flex w-full max-w-4xl flex-col items-center gap-8">
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
                  {agentName ? `开始与${agentName}协作` : '开始一项工作'}
                </h2>
                <p className="mt-2 max-w-md text-sm leading-6 text-[var(--text-muted)]">
                  {agentName
                    ? '用一句话说明目标与约束, 即可开始对话. 支持表格、计划、画布、命令运行与文档下载.'
                    : '说明目标、范围与期望产出, 从常用开场快速开始. 智能体可调用工具/知识/工作流, 并把产物放到右侧工作区.'}
                </p>
                {!agentName ? (
                  <Link
                    to="/agents"
                    className="mt-4 inline-flex items-center gap-1.5 rounded-lg border border-[var(--brand)] bg-[var(--brand-light)] px-3 py-1.5 text-xs font-semibold text-[var(--brand)] transition hover:bg-[var(--brand)] hover:text-white"
                  >
                    去智能体库选一个智能体 →
                  </Link>
                ) : null}
              </div>
              <div className="grid w-full max-w-3xl gap-2 sm:grid-cols-3">
                {(() => {
                  const pool = getStarters();
                  return (agentName && entry?.agentExample
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
              <div className="w-full max-w-3xl">{Composer}</div>
            </div>
          </div>
        ) : (
          // 有消息: 上滚动 + 下贴底 composer
          <>
            <div className="flex-1 overflow-y-auto">
              <div className="mx-auto flex min-h-full w-full max-w-4xl flex-col px-5 py-8 sm:px-10">
                {agentName ? (
                  <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface-1)] px-4 py-3 text-xs">
                    <span className="inline-flex items-center gap-2 font-semibold text-[var(--brand)]">
                      <Bot className="h-4 w-4" />
                      当前智能体:{agentName}
                      {skillName ? ` · 能力:${skillName}` : ''}
                    </span>
                    <Link to="/agents" className="font-medium text-[var(--text-secondary)] hover:text-[var(--brand)]">
                      更换智能体
                    </Link>
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
                {notices.length ? (
                  <button
                    type="button"
                    onClick={() => navigate('/agents')}
                    className="mb-3 inline-flex items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-1.5 text-[11px] font-semibold text-amber-900 transition hover:border-amber-500 hover:bg-amber-100"
                    title="去智能体库选一个智能体"
                  >
                    <span aria-hidden="true">⚠</span>
                    <span>{notices[notices.length - 1]}</span>
                    <span className="ml-1 underline decoration-dotted underline-offset-2">去智能体库</span>
                  </button>
                ) : null}
                {!agentName && skillName ? (
                  <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface-1)] px-4 py-3 text-xs">
                    <span className="inline-flex items-center gap-2 font-semibold text-[var(--brand)]">
                      <Sparkles className="h-4 w-4" />
                      当前能力:{skillName}
                    </span>
                    <Link to="/skills" className="font-medium text-[var(--text-secondary)] hover:text-[var(--brand)]">
                      更换能力
                    </Link>
                  </div>
                ) : null}
                <div className="space-y-9 pb-8">
                  {messages.map((message, index) =>
                    message.role === 'user' ? (
                      <div key={`${message.role}-${index}`} className="flex justify-end">
                        <div className="max-w-[86%] rounded-2xl bg-[var(--text)] px-5 py-3 text-sm leading-6 text-[var(--surface-1)] whitespace-pre-wrap shadow-sm">
                          {message.content}
                        </div>
                      </div>
                    ) : (
                      <article key={`${message.role}-${index}`} className="space-y-3 text-[15px] leading-7 text-[var(--text-secondary)]">
                        {message.plan && sessionId ? (
                          <PlanProposalCard proposal={message.plan} sessionId={sessionId} />
                        ) : null}
                        {message.content ? (
                          <MarkdownView source={message.content} />
                        ) : isSending && index === messages.length - 1 ? (
                          // 首字到达前的占位 — deepseek first-token latency 1.5-7s,
                          // 没有这个提示用户会以为卡死. 看到 ▍ 闪 + 文字轮换就知道在跑.
                          <CopilotTypingIndicator />
                        ) : null}
                        {message.artifacts && message.artifacts.length > 0 ? (
                          <div className="space-y-2">
                            {message.artifacts.map((a) => (
                              <ArtifactCard key={a.artifact_id} artifact={a} />
                            ))}
                          </div>
                        ) : null}
                        {message.attachments && message.attachments.length > 0 ? (
                          <div className="flex flex-wrap gap-1.5">
                            {message.attachments.map((a) => (
                              <AttachmentChip key={a.attachment_id} attachment={a} />
                            ))}
                          </div>
                        ) : null}
                        {message.extras ? <MessageExtrasView extras={message.extras} /> : null}
                      </article>
                    )
                  )}
                </div>
                <div ref={messagesEndRef} />
              </div>
            </div>
            <div className="border-t border-[var(--border)] bg-[var(--surface-1)] p-4 sm:p-5">
              <div className="mx-auto max-w-4xl">{Composer}</div>
            </div>
          </>
        )}
      </main>
      <InteractionHost />
    </div>
  );
}
