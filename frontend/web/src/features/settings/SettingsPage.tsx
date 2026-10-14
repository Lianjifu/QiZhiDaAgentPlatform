import { useApiQuery } from '@/services/query';
import { useServerAction } from '@/services/useServerAction';
import { useEffect } from 'react';
/**
 * 平台设置 — 品牌、合规、审计、成员。
 * 品牌名称和主题色支持草稿预览，保存结果以服务端响应为准。
 */
import { Building2, Check, ListTodo, Save, Search, ShieldCheck, Upload, UsersRound } from 'lucide-react';
import { useMemo, useState, type ReactNode } from 'react';
import { BrandLogo } from '@/components/feedback/BrandLogo';
import { NoticeBanner, type NoticeTone } from '@/components/feedback/NoticeBanner';

type SettingTab = 'brand' | 'compliance' | 'audit' | 'members';
type MemberRole = '管理员' | '成员';
type Member = { id: string; name: string; email: string; role: MemberRole; team: string };
type Policies = { sensitive: boolean; block: boolean; egress: boolean; trail: boolean };

const SWATCHES = ['#6828D8', '#F87818', '#0f766e', '#b45309', '#be123c'];

export default function SettingsPage() {
  const [tab, setTab] = useState<SettingTab>('brand');
  const settingsQuery = useApiQuery<{ items: Array<{ key: string; value: { brandName?: string; brandColor?: string; policies?: Policies } }> }>(['admin', 'settings'], '/v1/platform/settings');
  const membersQuery = useApiQuery<Member[]>(['admin', 'settings', 'members'], '/api/workspaces/current/members');
  const auditQuery = useApiQuery<Array<{ time: string; actor: string; action: string; result: string }>>(['admin', 'settings', 'audit'], '/api/admin/settings/audit');
  const members = membersQuery.data ?? [];
  const auditRows = auditQuery.data ?? [];
  const [brandName, setBrandName] = useState('');
  const [brandColor, setBrandColor] = useState('#6828D8');
  const [policies, setPolicies] = useState<Policies>({ sensitive: false, block: false, egress: false, trail: false });

  const [query, setQuery] = useState('');
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<MemberRole>('成员');
  const [saved, setSaved] = useState(false);
  const [notice, setNotice] = useState<{ tone: NoticeTone; text: string } | null>(null);
  const server = useServerAction((text) => setNotice({ tone: text.startsWith('请求失败') ? 'amber' : 'emerald', text }));
  useEffect(() => {
    const value = settingsQuery.data?.items.find((item) => item.key === 'console')?.value;
    setBrandName(value?.brandName ?? '');
    setBrandColor(value?.brandColor ?? '#6828D8');
    setPolicies(value?.policies ?? { sensitive: false, block: false, egress: false, trail: false });
  }, [settingsQuery.data]);

  const policyOn = Object.values(policies).filter(Boolean).length;
  const adminCount = members.filter((item) => item.role === '管理员').length;
  const visibleMembers = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return members;
    return members.filter((item) => `${item.name} ${item.email} ${item.team}`.toLowerCase().includes(keyword));
  }, [members, query]);

  const tabs: { id: SettingTab; label: string; hint: string; icon: typeof Building2 }[] = [
    { id: 'brand', label: '品牌与界面', hint: brandName, icon: Building2 },
    { id: 'compliance', label: '合规策略', hint: `${policyOn}/4 项开启`, icon: ShieldCheck },
    { id: 'audit', label: '审计日志', hint: `近 7 天 ${auditRows.length} 条`, icon: ListTodo },
    { id: 'members', label: '成员管理', hint: `${members.length} 人 · ${adminCount} 位管理员`, icon: UsersRound },
  ];

  const save = () => server.mutate({ path: '/v1/platform/settings/console', method: 'PUT', body: { value: { brandName, brandColor, policies } }, success: '设置已保存到后端。', onSuccess: () => setSaved(true) });

  const togglePolicy = (key: keyof Policies) => {
    setPolicies((current) => ({ ...current, [key]: !current[key] }));
  };

  const sendInvite = () => {
    const email = inviteEmail.trim().toLowerCase();
    if (!email.includes('@') || email.startsWith('@')) {
      setNotice({ tone: 'amber', text: '请填写有效的邮箱地址。' });
      return;
    }
    if (members.some((item) => item.email === email)) {
      setNotice({ tone: 'amber', text: '这个邮箱已经在成员列表里。' });
      return;
    }
    server.mutate({ path: '/api/workspaces/current/members/invite', body: { email, role: inviteRole }, success: `已为 ${email} 创建邀请，等待接受。`, onSuccess: () => { setInviteEmail(''); setInviteOpen(false); } });
  };

  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-5 p-5 pb-16 sm:p-8 xl:px-10">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--brand)]">ADMIN / 平台设置</p>
          <h2 className="mt-3 text-2xl font-semibold tracking-tight sm:text-3xl xl:text-4xl">配置品牌、合规开关和成员。</h2>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-[var(--text-muted)]">品牌、合规、审计记录与成员。</p>
        </div>
        <button type="button" onClick={save} className="inline-flex h-9 items-center gap-2 self-start rounded-lg bg-[var(--brand)] px-3.5 text-xs font-semibold text-white hover:bg-[var(--brand-hover)] sm:self-auto">
          {saved ? <Check className="h-3.5 w-3.5" /> : <Save className="h-3.5 w-3.5" />}
          {saved ? '已保存' : '保存设置'}
        </button>
      </header>

      {notice ? <NoticeBanner tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</NoticeBanner> : null}

      <div role="tablist" aria-label="设置分类" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {tabs.map((item) => {
          const Icon = item.icon;
          const selected = tab === item.id;
          return (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={selected}
              onClick={() => setTab(item.id)}
              className={`flex items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition ${selected ? 'border-[var(--brand)] bg-[var(--brand-light)] text-[var(--brand)]' : 'border-[var(--border)] bg-[var(--surface-1)] text-[var(--text)] hover:border-[var(--border-strong)]'}`}
            >
              <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-lg ${selected ? 'bg-[var(--surface-1)]' : 'bg-[var(--bg-elevated)]'}`}>
                <Icon className="h-4 w-4" />
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-semibold">{item.label}</span>
                <span className="mt-0.5 block truncate text-[11px] text-[var(--text-muted)]">{item.hint}</span>
              </span>
            </button>
          );
        })}
      </div>

      <section role="tabpanel" className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-4 sm:p-6">
        {tab === 'brand' && (
          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
            <div>
              <PanelTitle title="对外品牌" desc="名称和主题色用于登录页、邮件头和对外文档。" />
              <Field label="品牌名称">
                <input value={brandName} onChange={(event) => setBrandName(event.target.value)} className="h-9 w-full rounded-lg border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
              </Field>
              <Field label="主题色" hint="点色块，或用取色器自定义。">
                <div className="flex flex-wrap items-center gap-2">
                  {SWATCHES.map((color) => (
                    <button
                      key={color}
                      type="button"
                      aria-label={`主题色 ${color}`}
                      aria-pressed={brandColor.toLowerCase() === color}
                      onClick={() => setBrandColor(color)}
                      className={`h-7 w-7 rounded-full ring-2 ring-offset-2 ring-offset-[var(--surface-1)] ${brandColor.toLowerCase() === color ? 'ring-[var(--text)]' : 'ring-transparent'}`}
                      style={{ background: color }}
                    />
                  ))}
                  <label className="inline-flex items-center gap-2 text-xs text-[var(--text-muted)]">
                    <input type="color" value={toHex(brandColor)} onChange={(event) => setBrandColor(event.target.value)} aria-label="自定义主题色" className="h-7 w-9 cursor-pointer rounded border border-[var(--border)] bg-transparent" />
                    <span className="font-mono">{brandColor}</span>
                  </label>
                </div>
              </Field>
              <Field label="登录页主图" hint="1440×720 的 JPG 或 PNG，不超过 2MB。">
                <button type="button" onClick={() => setNotice({ tone: 'sky', text: '上传入口将在连接资源服务后开放。' })} className="inline-flex h-9 items-center gap-2 rounded-lg border border-dashed border-[var(--border-strong)] px-3 text-xs font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]">
                  <Upload className="h-3.5 w-3.5" />上传主图
                </button>
              </Field>
            </div>
            <BrandPreview name={brandName || '未命名品牌'} color={toHex(brandColor)} />
          </div>
        )}

        {tab === 'compliance' && (
          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
            <div>
              <PanelTitle title="策略开关" desc="关闭后只影响新请求，已经放行的会话不会回溯。" />
              <PolicyRow title="敏感词过滤" desc="命中词库的输入会先拦截，再记一条审计。" on={policies.sensitive} onToggle={() => togglePolicy('sensitive')} />
              <PolicyRow title="违规输出拦截" desc="模型输出命中红线时替换为安全回复。" on={policies.block} onToggle={() => togglePolicy('block')} />
              <PolicyRow title="数据出境需审批" desc="把知识库或日志发到外部地域前需要管理员确认。" on={policies.egress} onToggle={() => togglePolicy('egress')} />
              <PolicyRow title="操作留痕" desc="成员的发布、权限和导出都会写入审计。" on={policies.trail} onToggle={() => togglePolicy('trail')} />
            </div>
            <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] p-4">
              <p className="text-sm font-semibold">近 30 天风险</p>
              <p className="mt-1 text-xs text-[var(--text-muted)]">风险数据请查看工具审计。</p>
              <button type="button" onClick={() => setNotice({ tone: 'sky', text: '策略说明导出接口暂未提供。' })} className="mt-3 text-xs font-semibold text-[var(--brand)] hover:underline">导出策略说明</button>
            </div>
          </div>
        )}

        {tab === 'audit' && (
          <div>
            <div className="mb-4 flex items-center justify-between gap-3">
              <PanelTitle title="最近活动" desc="只展示这个工作空间近 7 天的关键操作。" />
              <button type="button" onClick={() => setNotice({ tone: 'sky', text: '审计导出接口暂未提供。' })} className="inline-flex h-8 shrink-0 items-center rounded-lg border border-[var(--border)] px-3 text-xs font-semibold hover:border-[var(--brand)]">导出</button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-left text-sm">
                <thead>
                  <tr className="border-b border-[var(--border)] text-[11px] text-[var(--text-muted)]">
                    <th className="px-2 py-2 font-medium">时间</th>
                    <th className="px-2 py-2 font-medium">操作者</th>
                    <th className="px-2 py-2 font-medium">动作</th>
                    <th className="px-2 py-2 font-medium">结果</th>
                  </tr>
                </thead>
                <tbody>
                  {auditRows.map((row) => (
                    <tr key={`${row.time}-${row.action}`} className="border-b border-[var(--border)] last:border-0">
                      <td className="px-2 py-2.5 text-xs text-[var(--text-muted)]">{row.time}</td>
                      <td className="px-2 py-2.5 text-sm">{row.actor}</td>
                      <td className="px-2 py-2.5 text-sm text-[var(--text-secondary)]">{row.action}</td>
                      <td className="px-2 py-2.5 text-xs text-emerald-700 dark:text-emerald-300">{row.result}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {tab === 'members' && (
          <div>
            <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <PanelTitle title="工作空间成员" desc={`${members.length} 人，其中 ${adminCount} 位管理员。`} />
              <div className="flex flex-wrap items-center gap-2">
                <label className="relative">
                  <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--text-muted)]" />
                  <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索姓名或邮箱" aria-label="搜索成员" className="h-8 w-48 rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] pl-8 pr-2 text-xs outline-none focus:border-[var(--brand)]" />
                </label>
                <button type="button" onClick={() => setInviteOpen((open) => !open)} className="inline-flex h-8 items-center rounded-lg bg-[var(--text)] px-3 text-xs font-semibold text-[var(--surface-1)]">邀请成员</button>
              </div>
            </div>
            {inviteOpen ? (
              <form
                className="mb-4 flex flex-col gap-2 rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] p-3 sm:flex-row sm:items-center"
                onSubmit={(event) => { event.preventDefault(); sendInvite(); }}
              >
                <input value={inviteEmail} onChange={(event) => setInviteEmail(event.target.value)} placeholder="name@acme.com" aria-label="邀请邮箱" className="h-8 min-w-0 flex-1 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-3 text-xs outline-none focus:border-[var(--brand)]" />
                <select value={inviteRole} onChange={(event) => setInviteRole(event.target.value as MemberRole)} aria-label="邀请角色" className="h-8 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2 text-xs">
                  <option value="成员">成员</option>
                  <option value="管理员">管理员</option>
                </select>
                <button type="submit" className="h-8 rounded-lg bg-[var(--brand)] px-3 text-xs font-semibold text-white">创建邀请</button>
              </form>
            ) : null}
            <ul className="divide-y divide-[var(--border)]">
              {visibleMembers.length === 0 ? <li className="py-8 text-center text-xs text-[var(--text-muted)]">没有匹配的成员。</li> : null}
              {visibleMembers.map((member) => (
                <li key={member.id} className="flex items-center gap-3 py-2.5">
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[var(--brand-light)] text-xs font-semibold text-[var(--brand)]">{member.name.slice(0, 1)}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{member.name}</span>
                    <span className="block truncate text-[11px] text-[var(--text-muted)]">{member.email} · {member.team}</span>
                  </span>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${member.role === '管理员' ? 'bg-[var(--brand-light)] text-[var(--brand)]' : 'bg-[var(--bg-elevated)] text-[var(--text-secondary)]'}`}>{member.role}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
    </div>
  );
}

function PanelTitle({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="mb-1">
      <h3 className="text-sm font-semibold">{title}</h3>
      <p className="mt-0.5 text-xs text-[var(--text-muted)]">{desc}</p>
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="mt-4 block">
      <span className="text-xs font-semibold">{label}</span>
      {hint ? <span className="mt-0.5 block text-[11px] font-normal text-[var(--text-muted)]">{hint}</span> : null}
      <span className="mt-2 block">{children}</span>
    </label>
  );
}

function PolicyRow({ title, desc, on, onToggle }: { title: string; desc: string; on: boolean; onToggle: () => void }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-[var(--border)] py-3.5 last:border-0">
      <div className="min-w-0">
        <p className="text-sm font-medium">{title}</p>
        <p className="mt-0.5 text-xs text-[var(--text-muted)]">{desc}</p>
      </div>
      <button type="button" role="switch" aria-checked={on} aria-label={title} onClick={onToggle} className={`relative h-5 w-9 shrink-0 rounded-full transition ${on ? 'bg-[var(--brand)]' : 'bg-[var(--border-strong)]'}`}>
        <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-[left] ${on ? 'left-4' : 'left-0.5'}`} />
      </button>
    </div>
  );
}

function BrandPreview({ name, color }: { name: string; color: string }) {
  return (
    <div>
      <p className="text-xs font-semibold">预览</p>
      <div className="mt-2 overflow-hidden rounded-xl border border-[var(--border)]">
        <div className="flex items-center gap-2.5 bg-[var(--surface-1)] px-4 py-3" style={{ borderBottom: `3px solid ${color}` }}>
          <BrandLogo size={28} variant="icon" ariaLabel={name} />
          <span className="truncate text-sm font-semibold" style={{ color }}>{name}</span>
        </div>
        <div className="space-y-2 bg-[var(--bg-elevated)] p-4">
          <div className="h-2 w-20 rounded bg-[var(--border-strong)]" />
          <div className="h-8 rounded-lg border border-[var(--border)] bg-[var(--surface-1)]" />
          <div className="h-8 rounded-lg border border-[var(--border)] bg-[var(--surface-1)]" />
          <div className="grid h-8 place-items-center rounded-lg text-xs font-semibold text-white" style={{ background: color }}>登录工作台</div>
        </div>
      </div>
      <p className="mt-2 text-[11px] leading-5 text-[var(--text-muted)]">改名称或颜色后，这里会马上跟着变。保存不会改控制台本身的品牌色。</p>
    </div>
  );
}

function toHex(value: string): string {
  return /^#[0-9a-fA-F]{6}$/.test(value) ? value : '#6828D8';
}
