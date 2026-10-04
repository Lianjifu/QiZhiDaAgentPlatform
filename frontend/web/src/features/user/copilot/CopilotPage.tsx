import { ArrowLeft, ArrowRight, ArrowUp, Bot, ChevronDown, ChevronRight, ClipboardCheck, Copy, FileText, Folder, FolderTree, Globe2, Menu, MoreHorizontal, PanelRightClose, Paperclip, Plus, RefreshCw, Search, Settings2, Sparkles, TerminalSquare } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { useEffect, useState } from 'react';
import type { CopilotSession } from './schema';
import {
  createCopilotSession,
  decideCopilotApproval,
  listCopilotSessions,
  loadCopilotSession,
  streamCopilotTurn,
  type ChatMessage,
} from './copilotApi';

type Message = ChatMessage;
type CopilotEntryState = { knowledgeTitle?: string; agentId?: string; agentName?: string; agentExample?: string; skillName?: string; sessionId?: string };
type PreviewTab = 'review' | 'browser' | 'files' | 'terminal';

const starters = ['帮我整理今天的工作重点', '分析这份资料并提炼结论', '生成一份客户跟进计划'];
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
    void listCopilotSessions().then(setSessions);
  }, []);
  useEffect(() => {
    if (!sessionId) return;
    void loadCopilotSession(sessionId).then((detail) => {
      if (!detail) return;
      const loaded = (detail.messages || [])
        .filter((item) => item.role === 'user' || item.role === 'assistant')
        .map((item) => ({ role: item.role as 'user' | 'assistant', content: item.content }));
      setMessages(loaded);
      const pending = detail.pendingApproval;
      if (pending) {
        setPendingApproval({
          id: String(pending.approval_id || pending.approvalId || ''),
          toolName: String(pending.tool_name || pending.toolName || '工具'),
          reason: String(pending.reason || '需要确认后才会执行'),
        });
      }
    });
  }, [sessionId]);
  const [terminalCommand, setTerminalCommand] = useState('');
  const [terminalOutput, setTerminalOutput] = useState<string[]>(['$ workspace status', 'Workspace ready · qizhida-agent-platform', '$']);
  const runTerminalCommand = () => {
    const command = terminalCommand.trim();
    if (!command) return;
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
  const files = [
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
  ];
  const visibleFiles = files.filter((file) => !fileFilter || file.name.toLowerCase().includes(fileFilter.toLowerCase()));
  const toggleFolder = (name: string) => setExpandedFolders((current) => current.includes(name) ? current.filter((item) => item !== name) : [...current, name]);
  const previewTabs: { id: PreviewTab; label: string; icon: typeof Globe2 }[] = [
    { id: 'review', label: '审查', icon: ClipboardCheck },
    { id: 'browser', label: '浏览器', icon: Globe2 },
    { id: 'files', label: '文件', icon: FileText },
    { id: 'terminal', label: '终端', icon: TerminalSquare },
  ];

  const sendMessage = async (value = input) => {
    const content = value.trim();
    if (!content || isSending) return;
    setIsSending(true);
    setMessages((current) => [...current, { role: 'user', content }]);
    setInput('');
    setComposerMenu(null);
    const demo = `本地演示：已记录${agentName ? `发给“${agentName}”` : ''}的任务。当前尚未连接真实智能体服务，不会生成实际结果或执行外部操作。`;
    try {
      let sid = sessionId;
      if (!sid && entry?.agentId) {
        const created = await createCopilotSession(entry.agentId, agentName ? `与${agentName}对话` : content.slice(0, 24));
        sid = created?.id;
        if (sid) setSessionId(sid);
      }
      if (!sid) {
        setMessages((current) => [...current, { role: 'assistant', content: demo }]);
        return;
      }
      let assistant = '';
      const tools: string[] = [];
      await streamCopilotTurn(sid, content, (event, data) => {
        if (event === 'message') assistant += String(data.content || '');
        if (event === 'tool_call') tools.push(String(data.tool_name || 'tool'));
        if (event === 'approval_required') {
          setPendingApproval({
            id: String(data.approval_id || ''),
            toolName: String(data.tool_name || '工具'),
            reason: String(data.reason || '需要确认后才会执行'),
          });
        }
        if (event === 'context_compacted') setNotices((n) => [...n, '上下文已压缩']);
        if (event === 'memory_write') setNotices((n) => [...n, '已写入记忆']);
        if (event === 'done') assistant = String(data.final_message || assistant);
      });
      setMessages((current) => [...current, { role: 'assistant', content: assistant || '已完成。', tools }]);
      void listCopilotSessions().then(setSessions);
    } catch {
      setMessages((current) => [...current, { role: 'assistant', content: demo }]);
    } finally {
      setIsSending(false);
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
    } finally {
      setIsSending(false);
    }
  };
  const selectComposerOption = (value: string) => {
    setInput((current) => `${current.slice(0, -1)}${value}`);
    setComposerMenu(null);
  };

  return (
    <div className="flex min-h-0 h-full flex-1 flex-row overflow-hidden bg-[var(--bg-elevated)]">
      {sessionListOpen ? <div className="fixed inset-0 z-40 bg-slate-950/40 lg:hidden" onClick={() => setSessionListOpen(false)} aria-hidden="true" /> : null}
      <aside className={`${sessionListOpen ? 'fixed inset-y-0 left-0 z-50 flex w-72' : 'hidden'} min-h-0 shrink-0 flex-col border-r border-[var(--border)] bg-[var(--surface-1)] lg:static lg:z-auto lg:flex lg:w-64`}><div className="flex items-center justify-between border-b border-[var(--border)] p-4"><h2 className="text-sm font-semibold">对话</h2><button type="button" className="rounded-md p-1.5 text-[var(--text-muted)] hover:bg-[var(--bg-hover)]" aria-label="新建对话"><Plus className="h-4 w-4" /></button></div><div className="p-3"><div className="relative"><Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]" /><input placeholder="搜索对话" className="h-9 w-full rounded-md border border-[var(--border)] bg-[var(--bg-elevated)] pl-8 pr-2 text-xs outline-none focus:border-[var(--brand)]" /></div></div><div className="flex-1 overflow-auto px-2"><p className="px-2 py-2 text-[11px] font-semibold text-[var(--text-muted)]">最近对话</p>{(sessions.length ? sessions : [{ id: 'demo', title: '工作重点梳理', preview: '通用助手', updatedAt: '今天 09:20' }]).map((item, index) => <button type="button" key={item.id ?? item.title} onClick={() => { setSessionListOpen(false); if (item.id && item.id !== 'demo') { setSessionId(item.id); } }} className={`flex w-full flex-col gap-1 rounded-md px-2.5 py-2.5 text-left ${ (sessionId ? sessionId === item.id : index === 0) ? 'bg-[var(--brand-light)] text-[var(--brand)]' : 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]'}`}><span className="truncate text-xs font-semibold">{item.title}</span><span className={`flex items-center justify-between gap-2 text-[10px] ${(sessionId ? sessionId === item.id : index === 0) ? 'text-[var(--brand)]/80' : 'text-[var(--text-muted)]'}`}><span className="truncate">{item.preview || '会话'}</span><span className="shrink-0 tabular-nums">{item.updatedAt}</span></span></button>)}</div><div className="border-t border-[var(--border)] p-3"><button type="button" className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-xs text-[var(--text-muted)] hover:bg-[var(--bg-hover)]"><Settings2 className="h-4 w-4" />对话设置</button></div></aside>
      <main className="flex min-h-0 min-w-0 flex-1 flex-col"><div className="flex h-14 items-center justify-between border-b border-[var(--border)] bg-[var(--surface-1)] px-4 sm:px-6"><div className="flex items-center gap-3"><button type="button" className="rounded-md p-2 text-[var(--text-muted)] hover:bg-[var(--bg-hover)] lg:hidden" aria-label="打开对话列表" onClick={() => setSessionListOpen(true)}><Menu className="h-4 w-4" /></button><div><h1 className="text-sm font-semibold">{agentName ? `与${agentName}对话` : '工作重点梳理'}</h1><p className="text-[11px] text-[var(--text-muted)]">{agentName ? '已选择智能体 · 在线会话' : '智能体协作 · 多轮对话'}</p></div></div><button type="button" onClick={() => setShowContext((visible) => !visible)} title={showContext ? '关闭大模型配置与工作区' : '打开大模型配置与工作区'} aria-label={showContext ? '关闭大模型配置与工作区' : '打开大模型配置与工作区'} aria-expanded={showContext} aria-controls="copilot-workspace-preview" className="hidden rounded-md p-2 text-[var(--text-muted)] hover:bg-[var(--bg-hover)] xl:inline-flex"><FileText className="h-4 w-4" /></button></div><div className="flex-1 overflow-y-auto"><div className="mx-auto flex min-h-full w-full max-w-4xl flex-col px-5 py-8 sm:px-10">{agentName && <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface-1)] px-4 py-3 text-xs"><span className="inline-flex items-center gap-2 font-semibold text-[var(--brand)]"><Bot className="h-4 w-4" />当前智能体：{agentName}{skillName ? ` · 能力：${skillName}` : ''}</span><Link to="/agents" className="font-medium text-[var(--text-secondary)] hover:text-[var(--brand)]">更换智能体</Link></div>}{pendingApproval ? <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-xs text-amber-900"><span>待确认：{pendingApproval.toolName} · {pendingApproval.reason}</span><span className="flex gap-2"><button type="button" className="rounded-md bg-amber-700 px-3 py-1 text-white" onClick={() => void resolveApproval(true)}>批准</button><button type="button" className="rounded-md border border-amber-700 px-3 py-1" onClick={() => void resolveApproval(false)}>拒绝</button></span></div> : null}{notices.length ? <p className="mb-3 text-[11px] text-[var(--text-muted)]">{notices.slice(-3).join(' · ')}</p> : null}{!agentName && skillName && <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface-1)] px-4 py-3 text-xs"><span className="inline-flex items-center gap-2 font-semibold text-[var(--brand)]"><Sparkles className="h-4 w-4" />当前能力：{skillName}</span><Link to="/skills" className="font-medium text-[var(--text-secondary)] hover:text-[var(--brand)]">更换能力</Link></div>}{messages.length === 0 ? <div className="flex flex-1 flex-col items-center justify-center pb-12 text-center"><span className="grid h-12 w-12 place-items-center rounded-xl bg-[var(--brand-light)] text-[var(--brand)]"><Sparkles className="h-6 w-6" /></span><h2 className="mt-4 text-lg font-semibold">{agentName ? `开始与${agentName}协作` : '开始一项工作'}</h2><p className="mt-2 max-w-sm text-sm leading-6 text-[var(--text-muted)]">{agentName ? '用一句话说明目标与约束，即可进入演示对话。' : '说明目标、范围与期望产出，从常用开场快速开始。'}</p><div className="mt-6 grid w-full max-w-xl gap-2 sm:grid-cols-3">{(agentName && entry?.agentExample ? [entry.agentExample, ...starters.slice(1)] : starters).map((starter) => <button type="button" key={starter} onClick={() => { void sendMessage(starter); }} className="rounded-xl border border-[var(--border)] bg-[var(--surface-1)] p-3 text-left text-xs leading-5 text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]">{starter}</button>)}</div></div> : <div className="space-y-9 pb-8">{messages.map((message, index) => message.role === 'user' ? <div key={`${message.role}-${index}`} className="flex justify-end"><div className="max-w-[86%] rounded-2xl bg-[var(--text)] px-5 py-3 text-sm leading-6 text-[var(--surface-1)] shadow-sm">{message.content}</div></div> : <article key={`${message.role}-${index}`} className="space-y-4 text-[15px] leading-7 text-[var(--text-secondary)]"><p>{message.content}</p><details className="group overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface-1)]" open={index === messages.length - 1}><summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-xs font-medium text-[var(--text-muted)]"><span><span className="text-[var(--text-secondary)]">Ran 2 commands</span>, read a file, created a file <span className="font-mono text-emerald-500">+1377</span><span className="font-mono text-rose-500">-0</span></span><ChevronRight className="h-4 w-4 transition-transform group-open:rotate-90" /></summary><div className="border-t border-[var(--border)]"><button type="button" onClick={() => { setPreviewTab('files'); setSelectedFile('frontend-agent-platform-reconstruction.md'); setShowContext(true); }} className="flex w-full items-center justify-between border-b border-[var(--border)] px-4 py-3 text-left text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]"><span>确认文档与前端目录</span><ChevronRight className="h-4 w-4 text-[var(--text-muted)]" /></button><button type="button" onClick={() => { setPreviewTab('files'); setSelectedFile('frontend-agent-platform-reconstruction.md'); setShowContext(true); }} className="flex w-full items-center justify-between border-b border-[var(--border)] px-4 py-3 text-left text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]"><span>查看现有文档命名</span><ChevronRight className="h-4 w-4 text-[var(--text-muted)]" /></button><button type="button" onClick={() => { setPreviewTab('files'); setSelectedFile('frontend-agent-platform-reconstruction.md'); setShowContext(true); }} className="flex w-full items-center justify-between px-4 py-3 text-left text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]"><span className="text-emerald-500">Created</span>&nbsp;frontend-agent-platform-reconstruction.md <span className="font-mono text-emerald-500">+1377</span><ChevronRight className="h-4 w-4 text-[var(--text-muted)]" /></button></div></details><p>文档已写入 <code className="rounded bg-[var(--bg-hover)] px-1.5 py-0.5 text-xs text-[var(--brand)]">docs/</code>，现在我检查新增文件状态并把文档打开，便于你直接审阅。</p><details className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface-1)]"><summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-xs text-[var(--text-muted)]"><span>Ran a command, used a tool</span><ChevronRight className="h-4 w-4" /></summary><div className="border-t border-[var(--border)]"><button type="button" onClick={() => { setPreviewTab('files'); setSelectedFile('frontend-agent-platform-reconstruction.md'); setShowContext(true); }} className="flex w-full items-center justify-between px-4 py-3 text-left text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]"><span>检查新增方案文档</span><ChevronRight className="h-4 w-4 text-[var(--text-muted)]" /></button><button type="button" onClick={() => { setPreviewTab('files'); setSelectedFile('frontend-agent-platform-reconstruction.md'); setShowContext(true); }} className="flex w-full items-center justify-between px-4 py-3 text-left text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]"><span>Opened file</span><ChevronRight className="h-4 w-4 text-[var(--text-muted)]" /></button></div></details><p>已完成完整方案文档：</p><button type="button" onClick={() => { setPreviewTab('files'); setSelectedFile('frontend-agent-platform-reconstruction.md'); setShowContext(true); }} className="text-left text-sm text-[var(--brand)] underline underline-offset-4">frontend-agent-platform-reconstruction.md</button></article>)}</div>}</div></div><div className="border-t border-[var(--border)] bg-[var(--surface-1)] p-4 sm:p-5"><form onSubmit={(event) => { event.preventDefault(); void sendMessage(); }} className="mx-auto max-w-4xl">{composerMenu ? <div role="status" aria-live="polite" className="mb-2 rounded-xl border border-[var(--border)] bg-[var(--surface-1)] p-2 shadow-[var(--shadow-xs)]"><div className="flex items-center justify-between px-2 pb-2 text-[10px] text-[var(--text-muted)]"><span className="font-semibold text-[var(--text-secondary)]">{composerMenu === 'slash' ? '快捷命令' : '提及对象'}</span><span>已识别 {composerMenu === 'slash' ? '/' : '@'}</span></div><div role="listbox" aria-label={composerMenu === 'slash' ? '快捷命令列表' : '提及对象列表'} className="flex gap-1 overflow-x-auto">{composerOptions[composerMenu].map((option) => <button key={option.label} type="button" role="option" aria-selected="false" onClick={() => selectComposerOption(option.value)} className="shrink-0 rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs text-[var(--text-secondary)] hover:border-[var(--brand)] hover:bg-[var(--brand-light)] hover:text-[var(--brand)]">{option.label}</button>)}</div></div> : null}<div className="flex items-end gap-2 rounded-2xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] p-2 shadow-[var(--shadow-xs)] focus-within:border-[var(--brand)]"><button type="button" className="rounded-lg p-2 text-[var(--text-muted)] hover:bg-[var(--bg-hover)]" aria-label="添加附件" onClick={() => document.getElementById("copilot-file-input")?.click()}><Paperclip className="h-4 w-4" /><input type="file" className="hidden" id="copilot-file-input" onChange={(event) => { const file = event.target.files?.[0]; if (file) { setInput((current) => `${current}${current && !current.endsWith('\n') ? '\n' : ''}[附件: ${file.name}]`); setComposerMenu(null); event.currentTarget.value = ''; } }} /></button><textarea value={input} onChange={(event) => { const value = event.target.value; setInput(value); if (value.endsWith("/") || value.endsWith("@")) setComposerMenu(value.endsWith("/") ? "slash" : "mention"); else setComposerMenu(null); }} onKeyDown={(event) => { if (event.key === 'Escape' && composerMenu) { event.preventDefault(); setComposerMenu(null); return; } if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void sendMessage(); } }} rows={1} placeholder="描述你想完成的工作..." className="max-h-32 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none placeholder:text-[var(--text-muted)]" /><button type="submit" disabled={!input.trim()} className="grid h-9 w-9 place-items-center rounded-lg bg-[var(--brand)] text-white disabled:cursor-not-allowed disabled:opacity-40" aria-label="发送消息"><ArrowUp className="h-4 w-4" /></button></div><p className="mt-2 text-center text-[10px] text-[var(--text-muted)]">智能体可能会出错，请检查重要结果和来源。</p></form></div></main>
      {showContext ? <aside id="copilot-workspace-preview" className="hidden min-h-0 w-[min(100%,22rem)] shrink-0 border-l border-[var(--border)] bg-[var(--surface-1)] xl:flex xl:flex-col 2xl:w-[26rem]"><div className="flex items-center justify-between border-b border-[var(--border)] px-4 py-3"><div><h2 className="text-sm font-semibold">工作区预览</h2><p className="mt-1 text-[10px] text-[var(--text-muted)]">审查 · 浏览器 · 文件 · 终端</p></div><button type="button" onClick={() => setShowContext(false)} className="rounded-md p-1.5 text-[var(--text-muted)] hover:bg-[var(--bg-hover)]" aria-label="关闭预览面板"><X className="h-4 w-4" /></button></div><div className="grid grid-cols-4 gap-1 border-b border-[var(--border)] px-3 py-2">{previewTabs.map(({ id, label, icon: Icon }) => <button type="button" key={id} onClick={() => setPreviewTab(id)} className={`flex flex-col items-center gap-1 rounded-md px-1 py-2 text-[10px] ${previewTab === id ? 'bg-[var(--brand-light)] font-semibold text-[var(--brand)]' : 'text-[var(--text-muted)] hover:bg-[var(--bg-hover)]'}`}><Icon className="h-4 w-4" />{label}</button>)}</div><div className="flex min-h-0 flex-1">{previewTab === 'files' ? <div className="flex w-[210px] shrink-0 flex-col border-r border-[var(--border)] bg-[var(--bg-elevated)] p-2"> <div className="mb-2 flex items-center justify-between"><span className="text-[11px] font-semibold">文件</span><FolderTree className="h-3.5 w-3.5 text-[var(--text-muted)]" /></div><div className="relative mb-2"><Search className="absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-[var(--text-muted)]" /><input value={fileFilter} onChange={(event) => setFileFilter(event.target.value)} placeholder="筛选文件…" className="h-7 w-full rounded border border-[var(--border)] bg-[var(--surface-1)] pl-6 pr-2 text-[10px] outline-none focus:border-[var(--brand)]" /></div><div className="flex-1 space-y-0.5 overflow-auto text-[10px]">{visibleFiles.map((file) => { const isFolder = file.type === 'folder'; const parentOpen = !file.parent || expandedFolders.includes(file.parent); if (!parentOpen) return null; return <button type="button" key={`${file.parent ?? 'root'}-${file.name}`} onClick={() => isFolder ? toggleFolder(file.name) : setSelectedFile(file.name)} className={`flex w-full items-center gap-1 rounded px-1 py-1 text-left hover:bg-[var(--bg-hover)] ${selectedFile === file.name ? 'bg-[var(--brand-light)] text-[var(--brand)]' : 'text-[var(--text-secondary)]'}`} style={{ paddingLeft: `${file.depth * 10 + 4}px` }}>{isFolder ? (expandedFolders.includes(file.name) ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />) : <FileText className="h-3 w-3" />}<span className="truncate">{file.name}</span></button>; })}</div><div className="mt-2 border-t border-[var(--border)] pt-2 text-[9px] text-[var(--text-muted)]"><p className="truncate">Workspace: qizhida-agent-platform</p><p className="mt-1">本地工作区 · 已同步</p></div></div> : null}<div className="min-w-0 flex-1 overflow-auto bg-[var(--surface-1)] p-3">{previewTab === 'browser' ? <div className="flex h-full min-h-[360px] flex-col overflow-hidden rounded-lg border border-[var(--border)] bg-white dark:bg-slate-950"><div className="flex items-center gap-1 border-b border-slate-200 bg-slate-50 p-2 dark:border-slate-800 dark:bg-slate-900"><button type="button" className="p-1 text-slate-400" aria-label="后退"><ArrowLeft className="h-3.5 w-3.5" /></button><button type="button" className="p-1 text-slate-400" aria-label="前进"><ArrowRight className="h-3.5 w-3.5" /></button><button type="button" onClick={() => setPreviewRunning(false)} className="p-1 text-slate-400" aria-label="刷新"><RefreshCw className="h-3.5 w-3.5" /></button><div className="flex-1 truncate rounded bg-white px-2 py-1 text-[10px] text-slate-400 dark:bg-slate-800">http://localhost:5300/preview</div><button type="button" className="p-1 text-slate-400" aria-label="复制地址"><Copy className="h-3.5 w-3.5" /></button><button type="button" className="p-1 text-slate-400" aria-label="更多"><MoreHorizontal className="h-3.5 w-3.5" /></button></div><div className="flex flex-1 items-center justify-center p-6"><div className="w-full max-w-sm rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] p-6 text-center"><span className={`mx-auto grid h-11 w-11 place-items-center rounded-full ${previewRunning ? 'bg-emerald-100 text-emerald-600' : 'bg-[var(--brand-light)] text-[var(--brand)]'}`}><Globe2 className="h-5 w-5" /></span><p className="mt-4 text-sm font-semibold text-[var(--text)]">{previewRunning ? '预览服务运行中' : '开发服务未启动'}</p><p className="mt-2 text-xs leading-5 text-[var(--text-muted)]">{previewRunning ? '预览地址已就绪，可在工作区查看页面结果。' : '启动预览后，智能体生成的页面会显示在这里。'}</p><div className="mt-5 flex justify-center gap-2"><button type="button" onClick={() => setPreviewRunning(true)} className="rounded-md bg-[var(--brand)] px-3 py-2 text-xs font-medium text-white hover:opacity-90">{previewRunning ? '重新运行' : '启动预览'}</button><button type="button" onClick={() => { setPreviewTab('terminal'); setSelectedFile('App.tsx'); }} className="rounded-md border border-[var(--border)] px-3 py-2 text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]">查看入口文件</button></div></div></div></div> : null}{previewTab === 'files' ? <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] p-5"><div className="flex items-center gap-2 border-b border-[var(--border)] pb-4"><FileText className="h-5 w-5 text-[var(--brand)]" /><div><p className="text-sm font-semibold">{selectedFile}</p><p className="text-[10px] text-[var(--text-muted)]">Markdown 文档预览</p></div></div><div className="space-y-3 pt-5 text-xs leading-6 text-[var(--text-secondary)]"><p>这是当前工作区中的文档预览区域。</p><p>你可以在对话中要求智能体整理、修改并生成新的项目文档。</p></div></div> : null}{previewTab === 'files' ? <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] p-4"><div className="flex items-center gap-2 border-b border-[var(--border)] pb-3 text-xs font-semibold"><Folder className="h-4 w-4 text-[var(--brand)]" />{selectedFile}</div><p className="pt-4 text-xs leading-6 text-[var(--text-muted)]">项目目录已加载，可从左侧 Files 面板选择目录或文件查看详情。</p></div> : null}{previewTab === 'terminal' ? <div className="flex h-full min-h-[420px] flex-col overflow-hidden rounded-xl border border-slate-700 bg-[#0d1117]"><div className="flex items-center justify-between border-b border-slate-700 bg-[#161b22] px-4 py-3"><div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-emerald-400" /><span className="text-xs text-slate-300">终端 · qizhida-agent-platform</span></div><button type="button" onClick={() => setTerminalOutput(['$'])} className="text-[10px] text-slate-400 hover:text-white">清空</button></div><div className="flex-1 overflow-auto p-4 font-mono text-xs leading-6">{terminalOutput.map((line, index) => <div key={`${line}-${index}`} className={line.startsWith('$') ? 'text-emerald-400' : 'text-slate-300'}>{line}</div>)}</div><form onSubmit={(event) => { event.preventDefault(); runTerminalCommand(); }} className="flex items-center gap-2 border-t border-slate-700 bg-[#161b22] px-4 py-3"><span className="font-mono text-xs text-emerald-400">$</span><input value={terminalCommand} onChange={(event) => setTerminalCommand(event.target.value)} placeholder="输入 shell 命令，例如 pwd、ls" className="min-w-0 flex-1 bg-transparent font-mono text-xs text-white outline-none placeholder:text-slate-500" /><button type="submit" className="rounded-md bg-emerald-600 px-3 py-1.5 text-[10px] font-medium text-white hover:bg-emerald-500">执行</button></form></div> : null}</div></div></aside> : null}
    </div>
  );
}
