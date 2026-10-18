import { runtimeConfig } from '@/lib/api-mode';
import { getApiClient } from '@qzdap/web-api';
import {
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  Bot,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  Copy,
  FileText,
  Folder,
  FolderTree,
  Globe2,
  Menu,
  MoreHorizontal,
  PanelRightClose,
  Paperclip,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  Sparkles,
  TerminalSquare,
  Trash2,
} from 'lucide-react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useEffect, useRef, useState } from 'react';
import type { CopilotSession } from './schema';
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
type PreviewTab = 'review' | 'browser' | 'files' | 'terminal';

const starters = ['帮我整理今天的工作重点', '分析这份资料并提炼结论', '生成一份客户跟进计划'];

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
const X = PanelRightClose;

export default function Copilot() {
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
    if (!sessionId) return;
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
  }, [sessionId]);
  const [terminalCommand, setTerminalCommand] = useState('');
  const [terminalOutput, setTerminalOutput] = useState<string[]>(['$ workspace status', 'Workspace ready · qizhida-agent-platform', '$']);
  const runTerminalCommand = () => {
    const command = terminalCommand.trim();
    if (!command) return;
    if (!demoMode) { void getApiClient().post<{ output: string }>('/api/workspace/terminal', { command }).then((result) => setTerminalOutput((current) => [...current, result.output])).catch((error) => setNotices((current) => pushNotice(current, `执行失败：${String(error)}`))); return; }
    setTerminalOutput((current) => [...current.filter((line) => line !== '$').slice(-8), `$ ${command}`, command === 'pwd' ? '/workspace/qizhida-agent-platform' : command === 'ls' ? 'frontend  backend  docs  README.md' : `Command accepted: ${command}`, '$']);
    setTerminalCommand('');
  };
  const [composerMenu, setComposerMenu] = useState<'slash' | 'mention' | null>(null);
  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === '\\') {
        event.preventDefault();
        setShowContext((visible) => !visible);
      }
    };
    window.addEventListener('keydown', handleShortcut);
    return () => window.removeEventListener('keydown', handleShortcut);
  }, []);
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
  const [showContext, setShowContext] = useState(true);
  const [previewTab, setPreviewTab] = useState<PreviewTab>('browser');
  const [fileFilter, setFileFilter] = useState('');
  const [expandedFolders, setExpandedFolders] = useState<string[]>(['.claude', 'worktrees', 'qizhida-agent-platform']);
  const [selectedFile, setSelectedFile] = useState('README.md');
  const [previewRunning, setPreviewRunning] = useState(false);
  const [previewContent, setPreviewContent] = useState<string>('');
  const files = demoMode ? [
    { name: '.claude', type: 'folder', depth: 0 },
    { name: 'worktrees', type: 'folder', depth: 1, parent: '.claude' },
    { name: 'qizhida-agent-platform', type: 'folder', depth: 2, parent: 'worktrees' },
    { name: 'frontend', type: 'folder', depth: 3, parent: 'qizhida-agent-platform' },
    { name: 'Copilot.tsx', type: 'file', depth: 4, parent: 'frontend' },
    { name: 'App.tsx', type: 'file', depth: 4, parent: 'frontend' },
    { name: 'backend', type: 'folder', depth: 3, parent: 'qizhida-agent-platform' },
    { name: 'docs', type: 'folder', depth: 3, parent: 'qizhida-agent-platform' },
    { name: 'README.md', type: 'file', depth: 3, parent: 'qizhida-agent-platform' },
    { name: 'frontend-agent-platform-reconstruction.md', type: 'file', depth: 3, parent: 'qizhida-agent-platform' },
  ] : [];
  const visibleFiles = files.filter((file) => !fileFilter || file.name.toLowerCase().includes(fileFilter.toLowerCase()));
  const toggleFolder = (name: string) => setExpandedFolders((current) => current.includes(name) ? current.filter((item) => item !== name) : [...current, name]);
  const previewTabs: { id: PreviewTab; label: string; icon: typeof Globe2 }[] = [
    { id: 'review', label: '审查', icon: ClipboardCheck },
    { id: 'browser', label: '浏览器', icon: Globe2 },
    { id: 'files', label: '文件', icon: FileText },
    { id: 'terminal', label: '终端', icon: TerminalSquare },
  ];
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 右侧工作区事件路由: tool_name 命中规则 → 切 tab + 必要副作用
  const routeToolToTab = (toolName: string, kind: 'tool_call' | 'tool_result' | 'workflow_invocation', payload?: Record<string, unknown>) => {
    const name = toolName.toLowerCase();
    const matches = (prefix: string) => name === prefix || name.startsWith(prefix + '_');
    if (matches('browser') || matches('navigate') || matches('web_search') || matches('http')) {
      setPreviewTab('browser');
      setShowContext(true);
      return;
    }
    if (matches('shell') || matches('run_command') || matches('terminal')) {
      setPreviewTab('terminal');
      setShowContext(true);
      if (kind === 'tool_result' && typeof payload?.output === 'string') {
        setTerminalOutput((current) => [...current, payload.output as string, '$']);
      } else if (kind === 'tool_call' && payload?.arguments && typeof (payload.arguments as { command?: string }).command === 'string') {
        setTerminalOutput((current) => [...current, `$ ${(payload.arguments as { command: string }).command}`]);
      }
      return;
    }
    if (matches('write') || matches('generate') || matches('artifact')) {
      setPreviewTab('files');
      setShowContext(true);
      if (kind === 'tool_result' && typeof payload?.output === 'object' && payload.output && 'name' in (payload.output as object)) {
        setSelectedFile(String((payload.output as { name: string }).name));
      }
      return;
    }
    if (matches('read') || matches('list_files')) {
      setPreviewTab('files');
      setShowContext(true);
      return;
    }
    // 兜底: 不切 tab, 留个 notice
    setNotices((current) => pushNotice(current, `工具 ${toolName} 已调用`));
  };

  const sendMessage = async (value = input) => {
    const content = value.trim();
    if (!content || isSending) return;
    setIsSending(true);
    setMessages((current) => [...current, { role: 'user', content }]);
    setInput('');
    setComposerMenu(null);
    try {
      let sid = sessionId;
      if (!sid && entry?.agentId) {
        const created = await createCopilotSession(entry.agentId, agentName ? `与${agentName}对话` : content.slice(0, 24));
        sid = created?.id;
        if (sid) setSessionId(sid);
      }
      if (!sid) {
        // 没有 agent 上下文: 不是后端 bug, 是用户没选智能体。
        // 回滚刚 push 的 user 消息, 给一个跳转提示, 不污染消息栈。
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
            setMessages((current) => {
              const idx = assistantIndex < 0 ? current.length - 1 : assistantIndex;
              const next = current.slice();
              const existing = next[idx];
              if (!existing || existing.role !== 'assistant') return current;
              next[idx] = { ...existing, content: existing.content + chunk };
              return next;
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
          routeToolToTab(tc.tool_name, 'tool_call', { arguments: tc.arguments });
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
            routeToolToTab(tc.tool_name, 'tool_result', { output: tc.output });
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
          setShowContext(false); // plan 占主区, 收起右侧避免抢焦点
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
          setSelectedFile(a.name);
          setPreviewTab('files');
          setShowContext(true);
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
            setMessages((current) => {
              const idx = assistantIndex < 0 ? current.length - 1 : assistantIndex;
              const next = current.slice();
              const existing = next[idx];
              if (!existing || existing.role !== 'assistant') return current;
              next[idx] = { ...existing, content: final };
              return next;
            });
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
      // dev 模式 503 + PROVIDER_UNAVAILABLE: 把生硬的 "流式请求失败 (HTTP 503)"
      // 替换成可操作提示
      const friendly =
        /PROVIDER_UNAVAILABLE|Mock\s*LLM/.test(raw) || /\(HTTP\s*503\)/.test(raw)
          ? '当前后端没接真实模型: dev 模式不允许 mock LLM. 演示用 `QZDAP_ENV=demo` 重启后端, 或在 backend/.env.local 配 QZDAP_LLM_PROVIDER=openai-compatible + QZDAP_LLM_API_KEY=...'
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

  // 加载选中的 artifact 内容到右侧预览
  useEffect(() => {
    if (previewTab !== 'files' || !selectedFile) return;
    if (selectedFile.startsWith('Copilot') || selectedFile.endsWith('.md') || selectedFile.endsWith('.tsx') || selectedFile.endsWith('.ts')) {
      // 走 artifact download
      const artifact = messages.flatMap((m) => m.artifacts ?? []).find((a) => a.name === selectedFile);
      if (artifact) {
        void fetch(artifact.download_path, { credentials: 'include' })
          .then((r) => (r.ok ? r.text() : ''))
          .then((text) => setPreviewContent(text));
        return;
      }
    }
    setPreviewContent('');
  }, [previewTab, selectedFile, messages]);

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
          <button
            type="button"
            onClick={() => setShowContext((visible) => !visible)}
            title={showContext ? '关闭大模型配置与工作区' : '打开大模型配置与工作区'}
            aria-label={showContext ? '关闭大模型配置与工作区' : '打开大模型配置与工作区'}
            aria-expanded={showContext}
            aria-controls="copilot-workspace-preview"
            className="hidden rounded-md p-2 text-[var(--text-muted)] hover:bg-[var(--bg-hover)] xl:inline-flex"
          >
            <FileText className="h-4 w-4" />
          </button>
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
                {(agentName && entry?.agentExample ? [entry.agentExample, ...starters.slice(1)] : starters).map((starter) => (
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
                ))}
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
                        {message.content ? <MarkdownView source={message.content} /> : null}
                        {message.artifacts && message.artifacts.length > 0 ? (
                          <div className="space-y-2">
                            {message.artifacts.map((a) => (
                              <ArtifactCard
                                key={a.artifact_id}
                                artifact={a}
                                onOpenInWorkspace={(art) => {
                                  setSelectedFile(art.name);
                                  setPreviewTab('files');
                                  setShowContext(true);
                                }}
                              />
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

      {showContext ? (
        <aside
          id="copilot-workspace-preview"
          className="hidden min-h-0 w-[min(100%,22rem)] shrink-0 border-l border-[var(--border)] bg-[var(--surface-1)] xl:flex xl:flex-col 2xl:w-[26rem]"
        >
          <div className="flex items-center justify-between border-b border-[var(--border)] px-4 py-3">
            <div>
              <h2 className="text-sm font-semibold">工作区预览</h2>
              <p className="mt-1 text-[10px] text-[var(--text-muted)]">审查 · 浏览器 · 文件 · 终端</p>
            </div>
            <button
              type="button"
              onClick={() => setShowContext(false)}
              className="rounded-md p-1.5 text-[var(--text-muted)] hover:bg-[var(--bg-hover)]"
              aria-label="关闭预览面板"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="grid grid-cols-4 gap-1 border-b border-[var(--border)] px-3 py-2">
            {previewTabs.map(({ id, label, icon: Icon }) => (
              <button
                type="button"
                key={id}
                onClick={() => setPreviewTab(id)}
                className={`flex flex-col items-center gap-1 rounded-md px-1 py-2 text-[10px] ${
                  previewTab === id
                    ? 'bg-[var(--brand-light)] font-semibold text-[var(--brand)]'
                    : 'text-[var(--text-muted)] hover:bg-[var(--bg-hover)]'
                }`}
              >
                <Icon className="h-4 w-4" />
                {label}
              </button>
            ))}
          </div>
          <div className="flex min-h-0 flex-1">
            {previewTab === 'files' ? (
              <div className="flex w-[210px] shrink-0 flex-col border-r border-[var(--border)] bg-[var(--bg-elevated)] p-2">
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-[11px] font-semibold">文件</span>
                  <FolderTree className="h-3.5 w-3.5 text-[var(--text-muted)]" />
                </div>
                <div className="relative mb-2">
                  <Search className="absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-[var(--text-muted)]" />
                  <input
                    value={fileFilter}
                    onChange={(event) => setFileFilter(event.target.value)}
                    placeholder="筛选文件…"
                    className="h-7 w-full rounded border border-[var(--border)] bg-[var(--surface-1)] pl-6 pr-2 text-[10px] outline-none focus:border-[var(--brand)]"
                  />
                </div>
                <div className="flex-1 space-y-0.5 overflow-auto text-[10px]">
                  {visibleFiles.map((file) => {
                    const isFolder = file.type === 'folder';
                    const parentOpen = !file.parent || expandedFolders.includes(file.parent);
                    if (!parentOpen) return null;
                    return (
                      <button
                        type="button"
                        key={`${file.parent ?? 'root'}-${file.name}`}
                        onClick={() => (isFolder ? toggleFolder(file.name) : setSelectedFile(file.name))}
                        className={`flex w-full items-center gap-1 rounded px-1 py-1 text-left hover:bg-[var(--bg-hover)] ${
                          selectedFile === file.name ? 'bg-[var(--brand-light)] text-[var(--brand)]' : 'text-[var(--text-secondary)]'
                        }`}
                        style={{ paddingLeft: `${file.depth * 10 + 4}px` }}
                      >
                        {isFolder ? (
                          expandedFolders.includes(file.name) ? (
                            <ChevronDown className="h-3 w-3" />
                          ) : (
                            <ChevronRight className="h-3 w-3" />
                          )
                        ) : (
                          <FileText className="h-3 w-3" />
                        )}
                        <span className="truncate">{file.name}</span>
                      </button>
                    );
                  })}
                </div>
                <div className="mt-2 border-t border-[var(--border)] pt-2 text-[9px] text-[var(--text-muted)]">
                  <p className="truncate">Workspace: qizhida-agent-platform</p>
                  <p className="mt-1">本地工作区 · 已同步</p>
                </div>
              </div>
            ) : null}
            <div className="min-w-0 flex-1 overflow-auto bg-[var(--surface-1)] p-3">
              {previewTab === 'browser' ? (
                <div className="flex h-full min-h-[360px] flex-col overflow-hidden rounded-lg border border-[var(--border)] bg-white dark:bg-slate-950">
                  <div className="flex items-center gap-1 border-b border-slate-200 bg-slate-50 p-2 dark:border-slate-800 dark:bg-slate-900">
                    <button type="button" className="p-1 text-slate-400" aria-label="后退">
                      <ArrowLeft className="h-3.5 w-3.5" />
                    </button>
                    <button type="button" className="p-1 text-slate-400" aria-label="前进">
                      <ArrowRight className="h-3.5 w-3.5" />
                    </button>
                    <button type="button" onClick={() => setPreviewRunning(false)} className="p-1 text-slate-400" aria-label="刷新">
                      <RefreshCw className="h-3.5 w-3.5" />
                    </button>
                    <div className="flex-1 truncate rounded bg-white px-2 py-1 text-[10px] text-slate-400 dark:bg-slate-800">
                      http://localhost:5300/preview
                    </div>
                    <button type="button" className="p-1 text-slate-400" aria-label="复制地址">
                      <Copy className="h-3.5 w-3.5" />
                    </button>
                    <button type="button" className="p-1 text-slate-400" aria-label="更多">
                      <MoreHorizontal className="h-3.5 w-3.5" />
                    </button>
                  </div>
                  <div className="flex flex-1 items-center justify-center p-6">
                    <div className="w-full max-w-sm rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] p-6 text-center">
                      <span
                        className={`mx-auto grid h-11 w-11 place-items-center rounded-full ${
                          previewRunning ? 'bg-emerald-100 text-emerald-600' : 'bg-[var(--brand-light)] text-[var(--brand)]'
                        }`}
                      >
                        <Globe2 className="h-5 w-5" />
                      </span>
                      <p className="mt-4 text-sm font-semibold text-[var(--text)]">
                        {previewRunning ? '预览服务运行中' : '开发服务未启动'}
                      </p>
                      <p className="mt-2 text-xs leading-5 text-[var(--text-muted)]">
                        {previewRunning ? '预览地址已就绪，可在工作区查看页面结果。' : '启动预览后，智能体生成的页面会显示在这里。'}
                      </p>
                      <div className="mt-5 flex justify-center gap-2">
                        <button
                          type="button"
                          onClick={() => {
                            if (demoMode) setPreviewRunning(true);
                            else setNotices((current) => [...current, '预览服务接口暂未提供']);
                          }}
                          className="rounded-md bg-[var(--brand)] px-3 py-2 text-xs font-medium text-white hover:opacity-90"
                        >
                          {previewRunning ? '重新运行' : '启动预览'}
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setPreviewTab('terminal');
                            setSelectedFile('App.tsx');
                          }}
                          className="rounded-md border border-[var(--border)] px-3 py-2 text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]"
                        >
                          查看入口文件
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              ) : null}
              {previewTab === 'files' ? (
                previewContent ? (
                  <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] p-5">
                    <div className="mb-3 flex items-center gap-2 border-b border-[var(--border)] pb-3">
                      <FileText className="h-5 w-5 text-[var(--brand)]" />
                      <div>
                        <p className="text-sm font-semibold">{selectedFile}</p>
                        <p className="text-[10px] text-[var(--text-muted)]">从 artifact 流式加载的预览</p>
                      </div>
                    </div>
                    <MarkdownView source={previewContent.slice(0, 4000)} />
                  </div>
                ) : (
                  <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] p-4">
                    <div className="flex items-center gap-2 border-b border-[var(--border)] pb-3 text-xs font-semibold">
                      <Folder className="h-4 w-4 text-[var(--brand)]" />
                      {selectedFile}
                    </div>
                    <p className="pt-4 text-xs leading-6 text-[var(--text-muted)]">
                      项目目录已加载，可从左侧 Files 面板选择目录或文件查看详情。
                    </p>
                  </div>
                )
              ) : null}
              {previewTab === 'terminal' ? (
                <div className="flex h-full min-h-[420px] flex-col overflow-hidden rounded-xl border border-slate-700 bg-[#0d1117]">
                  <div className="flex items-center justify-between border-b border-slate-700 bg-[#161b22] px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className="h-2 w-2 rounded-full bg-emerald-400" />
                      <span className="text-xs text-slate-300">终端 · qizhida-agent-platform</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => setTerminalOutput(['$'])}
                      className="text-[10px] text-slate-400 hover:text-white"
                    >
                      清空
                    </button>
                  </div>
                  <div className="flex-1 overflow-auto p-4 font-mono text-xs leading-6">
                    {terminalOutput.map((line, index) => (
                      <div
                        key={`${line}-${index}`}
                        className={line.startsWith('$') ? 'text-emerald-400' : 'text-slate-300'}
                      >
                        {line}
                      </div>
                    ))}
                  </div>
                  <form
                    onSubmit={(event) => {
                      event.preventDefault();
                      runTerminalCommand();
                    }}
                    className="flex items-center gap-2 border-t border-slate-700 bg-[#161b22] px-4 py-3"
                  >
                    <span className="font-mono text-xs text-emerald-400">$</span>
                    <input
                      value={terminalCommand}
                      onChange={(event) => setTerminalCommand(event.target.value)}
                      placeholder="输入 shell 命令，例如 pwd、ls"
                      className="min-w-0 flex-1 bg-transparent font-mono text-xs text-white outline-none placeholder:text-slate-500"
                    />
                    <button
                      type="submit"
                      className="rounded-md bg-emerald-600 px-3 py-1.5 text-[10px] font-medium text-white hover:bg-emerald-500"
                    >
                      执行
                    </button>
                  </form>
                </div>
              ) : null}
            </div>
          </div>
        </aside>
      ) : null}
    </div>
  );
}
