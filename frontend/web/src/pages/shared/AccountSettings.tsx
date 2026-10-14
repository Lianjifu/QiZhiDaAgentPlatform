import { useServerAction } from '@/services/useServerAction';
import { useApiQuery } from '@/services/query';
import { useEffect } from 'react';
import { Bell, Check, ChevronRight, KeyRound, LogOut, Monitor, Palette, Save, ShieldCheck, UserRound } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { NoticeBanner } from '@/components/feedback/NoticeBanner';
import { useAuthStore } from '@/features/auth';
import { useUiStore } from '@/stores/uiStore';

type SettingTab = '个人资料' | '偏好设置' | '通知' | '账号安全';
type TabDef = { id: SettingTab; label: string; description: string; icon: typeof UserRound };

const tabs: TabDef[] = [
  { id: '个人资料', label: '个人资料', description: '姓名、邮箱与工作空间身份', icon: UserRound },
  { id: '偏好设置', label: '偏好设置', description: '主题、语言与工作台体验', icon: Palette },
  { id: '通知', label: '通知设置', description: '任务、工作流和系统提醒', icon: Bell },
  { id: '账号安全', label: '账号安全', description: '登录保护与访问记录', icon: ShieldCheck },
];

export default function AccountSettings() {
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);
  const { theme, toggleTheme } = useUiStore();
  const [tab, setTab] = useState<SettingTab>('个人资料');
  const [displayName, setDisplayName] = useState(user?.name ?? '');
  const [email, setEmail] = useState(user?.email ?? '');
  const [language, setLanguage] = useState('简体中文');
  const [digest, setDigest] = useState(true);
  const [taskAlert, setTaskAlert] = useState(true);
  const [saved, setSaved] = useState(false);
  const [notice, setNotice] = useState('');
  const current = tabs.find((item) => item.id === tab);
  const server = useServerAction(setNotice);
  const account = useApiQuery<{ displayName?: string; email?: string; language?: string; digest?: boolean; taskAlert?: boolean }>(['user', 'account'], '/api/account/settings');
  useEffect(() => {
    const value = account.data;
    setDisplayName(value?.displayName ?? user?.name ?? '');
    setEmail(value?.email ?? user?.email ?? '');
    setLanguage(value?.language ?? '');
    setDigest(value?.digest ?? false);
    setTaskAlert(value?.taskAlert ?? false);
  }, [account.data, user]);
  const save = () => server.mutate({ path: '/api/account/settings', method: 'PUT', body: { displayName, email, language, digest, taskAlert }, success: '设置已保存到后端。', onSuccess: () => setSaved(true) });
  const handleLogout = () => { logout(); navigate('/login', { replace: true }); };

  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-6 p-5 pb-16 sm:p-8 xl:px-10">
      <section className="relative overflow-hidden rounded-[28px] border border-[var(--border)] bg-[var(--surface-1)] px-6 py-8 shadow-[var(--shadow-sm)] sm:px-8">
        <div aria-hidden="true" className="pointer-events-none absolute right-0 top-0 h-full w-1/2 bg-[radial-gradient(circle_at_top_right,var(--brand-light),transparent_68%)]" />
        <div className="relative flex flex-col justify-between gap-5 xl:flex-row xl:items-end">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--brand)]">ACCOUNT / 设置</p>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight sm:text-3xl xl:text-4xl">把工作台调成你的样子。</h2>
            <p className="mt-3 max-w-2xl text-sm leading-7 text-[var(--text-muted)]">管理个人信息、通知偏好和账号安全。设置通过后端 API 保存。</p>
          </div>
          <div className="flex items-center gap-3 rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-3">
            <span className="grid h-11 w-11 place-items-center rounded-xl bg-[var(--brand-light)] text-lg font-bold text-[var(--brand)]">{displayName.slice(0, 1)}</span>
            <div>
              <p className="text-sm font-semibold">{displayName}</p>
              <p className="mt-1 text-xs text-[var(--text-muted)]">{email}</p>
            </div>
          </div>
        </div>
      </section>
      {notice && <NoticeBanner tone="emerald" onClose={() => setNotice('')}>{notice}</NoticeBanner>}
      <div className="grid gap-6 xl:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-3">
          <p className="px-3 pb-3 pt-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">SETTINGS</p>
          <nav aria-label="设置分类" className="space-y-1">
            {tabs.map((item) => {
              const Icon = item.icon;
              return (
                <button key={item.id} type="button" aria-current={tab === item.id ? 'page' : undefined} onClick={() => setTab(item.id)} className={`flex w-full items-center gap-3 rounded-xl p-3 text-left transition ${tab === item.id ? 'bg-[var(--brand-light)] text-[var(--brand)] dark:text-indigo-200' : 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]'}`}>
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[var(--bg-elevated)]"><Icon className="h-4 w-4" /></span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-xs font-semibold">{item.label}</span>
                    <span className="mt-0.5 block truncate text-[10px] opacity-70">{item.description}</span>
                  </span>
                  <ChevronRight className="h-4 w-4 shrink-0" />
                </button>
              );
            })}
          </nav>
          <div className="mt-6 border-t border-[var(--border)] pt-4">
            <button type="button" onClick={handleLogout} className="flex w-full items-center gap-3 rounded-xl p-3 text-left text-xs font-semibold text-[var(--danger)] hover:bg-[var(--danger-bg)]"><LogOut className="h-4 w-4" />退出当前账号</button>
          </div>
        </aside>
        <section className="min-w-0 rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
          <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-5 sm:px-8">
            <div>
              <h3 className="text-xl font-semibold">{current?.label}</h3>
              <p className="mt-1 text-xs text-[var(--text-muted)]">{current?.description}</p>
            </div>
            <button type="button" onClick={save} className="inline-flex items-center gap-2 rounded-xl bg-[var(--brand)] px-4 py-2.5 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]">{saved ? <Check className="h-4 w-4" /> : <Save className="h-4 w-4" />}{saved ? '已保存' : '保存设置'}</button>
          </div>
          <div className="p-5 sm:p-8">
            {tab === '个人资料' && (
              <div className="max-w-3xl space-y-7">
                <div className="flex items-center gap-4 rounded-2xl bg-[var(--bg-elevated)] p-5">
                  <span className="grid h-16 w-16 place-items-center rounded-2xl bg-[var(--brand)] text-xl font-bold text-white">{displayName.slice(0, 1)}</span>
                  <div>
                    <p className="text-sm font-semibold">你的工作台身份</p>
                    <p className="mt-1 text-xs leading-5 text-[var(--text-muted)]">用于显示在任务、协作和产出物中。</p>
                  </div>
                </div>
                <div className="grid gap-5 md:grid-cols-2">
                  <label className="text-xs font-semibold">显示名称<input value={displayName} onChange={(event) => setDisplayName(event.target.value)} className="mt-2 h-11 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm font-normal outline-none focus:border-[var(--brand)]" /></label>
                  <label className="text-xs font-semibold">工作邮箱<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} className="mt-2 h-11 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm font-normal outline-none focus:border-[var(--brand)]" /></label>
                </div>
                <div className="rounded-xl border border-[var(--border)] p-5">
                  <p className="text-xs font-semibold">当前工作空间</p>
                  <p className="mt-2 text-sm font-medium">默认工作空间</p>
                  <p className="mt-1 text-xs text-[var(--text-muted)]">你的资料、对话和协作内容会显示在这里。</p>
                </div>
              </div>
            )}
            {tab === '偏好设置' && (
              <div className="max-w-3xl divide-y divide-[var(--border)]">
                <div className="flex items-center gap-4 py-5 first:pt-0">
                  <span className="grid h-10 w-10 place-items-center rounded-xl bg-[var(--brand-light)] text-[var(--brand)]"><Monitor className="h-5 w-5" /></span>
                  <div className="flex-1">
                    <p className="text-sm font-semibold">外观主题</p>
                    <p className="mt-1 text-xs text-[var(--text-muted)]">当前：{theme === 'light' ? '浅色模式' : '深色模式'}</p>
                  </div>
                  <button type="button" onClick={toggleTheme} className="rounded-xl border border-[var(--border)] px-3 py-2 text-xs font-semibold hover:border-[var(--brand)]">切换主题</button>
                </div>
                <div className="flex items-center gap-4 py-5">
                  <span className="grid h-10 w-10 place-items-center rounded-xl bg-[var(--bg-elevated)] text-[var(--text-muted)]"><UserRound className="h-5 w-5" /></span>
                  <div className="flex-1">
                    <p className="text-sm font-semibold">界面语言</p>
                    <p className="mt-1 text-xs text-[var(--text-muted)]">选择工作台显示语言</p>
                  </div>
                  <select value={language} onChange={(event) => setLanguage(event.target.value)} className="h-10 rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] px-3 text-xs outline-none"><option>简体中文</option><option>English</option></select>
                </div>
              </div>
            )}
            {tab === '通知' && (
              <div className="max-w-3xl divide-y divide-[var(--border)]">
                <label className="flex cursor-pointer items-center gap-4 py-5 first:pt-0">
                  <span className="grid h-10 w-10 place-items-center rounded-xl bg-amber-50 text-amber-600 dark:bg-amber-500/15 dark:text-amber-300"><Bell className="h-5 w-5" /></span>
                  <span className="flex-1"><span className="block text-sm font-semibold">任务与工作流提醒</span><span className="mt-1 block text-xs text-[var(--text-muted)]">当任务需要确认或工作流发生异常时提醒我</span></span>
                  <input type="checkbox" checked={taskAlert} onChange={(event) => setTaskAlert(event.target.checked)} className="h-5 w-5 accent-[var(--brand)]" />
                </label>
                <label className="flex cursor-pointer items-center gap-4 py-5">
                  <span className="grid h-10 w-10 place-items-center rounded-xl bg-sky-50 text-sky-600 dark:bg-sky-500/15 dark:text-sky-300"><MailIcon /></span>
                  <span className="flex-1"><span className="block text-sm font-semibold">每周使用小结</span><span className="mt-1 block text-xs text-[var(--text-muted)]">接收关于任务完成和节省时间的摘要</span></span>
                  <input type="checkbox" checked={digest} onChange={(event) => setDigest(event.target.checked)} className="h-5 w-5 accent-[var(--brand)]" />
                </label>
              </div>
            )}
            {tab === '账号安全' && (
              <div className="max-w-3xl space-y-4">
                <div className="flex items-center gap-4 rounded-2xl border border-emerald-400/25 bg-emerald-50 p-5 dark:bg-emerald-500/10">
                  <ShieldCheck className="h-6 w-6 text-emerald-600" />
                  <div>
                    <p className="text-sm font-semibold text-emerald-800 dark:text-emerald-200">账号保护正常</p>
                    <p className="mt-1 text-xs text-emerald-700/80 dark:text-emerald-300/80">最近一次登录：刚刚 · 当前浏览器</p>
                  </div>
                </div>
                <button type="button" onClick={() => setNotice('密码修改入口将在连接账号服务后开放。')} className="flex w-full items-center gap-4 rounded-xl border border-[var(--border)] p-5 text-left hover:border-[var(--brand)]">
                  <KeyRound className="h-5 w-5 text-[var(--brand)]" />
                  <span className="flex-1"><span className="block text-sm font-semibold">修改密码</span><span className="mt-1 block text-xs text-[var(--text-muted)]">更新登录凭据和验证方式</span></span>
                  <ChevronRight className="h-4 w-4 text-[var(--text-muted)]" />
                </button>
                <div className="rounded-xl border border-[var(--border)] p-5">
                  <p className="text-sm font-semibold">最近访问</p>
                  <p className="mt-2 text-xs text-[var(--text-muted)]">当前浏览器 · 当前工作空间 · 刚刚</p>
                </div>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

function MailIcon() { return <svg aria-hidden="true" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m3 7 9 6 9-6" /></svg>; }

function ChannelRow({ icon, tone, title, desc, defaultEnabled = true, children }: { icon: ReactNode; tone: string; title: string; desc: string; defaultEnabled?: boolean; children?: ReactNode }) {
  const [enabled, setEnabled] = useState(defaultEnabled);
  return (
    <div className="py-5 first:pt-0">
      <label className="flex cursor-pointer items-center gap-4">
        <span className={`grid h-10 w-10 place-items-center rounded-xl ${tone}`}>{icon}</span>
        <span className="flex-1"><span className="block text-sm font-semibold">{title}</span><span className="mt-1 block text-xs text-[var(--text-muted)]">{desc}</span></span>
        <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} className="h-5 w-5 accent-[var(--brand)]" />
      </label>
      {children && enabled && <div className="mt-3 pl-14">{children}</div>}
    </div>
  );
}
