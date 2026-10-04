/**
 * LoginBrandPanel — 左侧品牌区，占视口 2/3。
 * 企业蓝管结构，活力橙管强调。左侧是星空：浅色黄昏，深色夜空。
 */
import type { ComponentType } from 'react';
import { BrandLogo } from '@/components/feedback/BrandLogo';

export interface LoginHeroStat {
  value: string;
  label: string;
}

export interface LoginHeroBullet {
  Icon: ComponentType<{ className?: string }>;
  tone: 'brand' | 'purple' | 'muted';
  title: string;
  desc: string;
}

interface LoginBrandPanelProps {
  product: string;
  tagline: string;
  badge: string;
  buildVersion: string;
  title1: string;
  title2: string;
  subtitle: string;
  bullets: LoginHeroBullet[];
  stats: LoginHeroStat[];
  footnote: string;
}

export function LoginBrandPanel(props: LoginBrandPanelProps) {
  return (
    <aside className="login-stage relative hidden min-h-full overflow-hidden md:flex md:flex-col" aria-label="产品介绍">
      <div className="login-stars" aria-hidden />
      <div className="login-stars-bright" aria-hidden />
      <div className="login-stars-accent" aria-hidden />
      <span className="login-watermark" aria-hidden>搭</span>

      <div className="relative z-10 flex h-full min-h-full flex-col justify-center px-10 py-10 lg:px-14 xl:px-16 2xl:px-24">
        <div className="login-rise login-copy w-full max-w-[40rem] xl:ml-auto 2xl:max-w-[44rem]">
          <div className="flex items-center gap-3">
          <div>
            <BrandLogo
              size={48}
              withWordmark
              wordmark="企智搭"
              subtitle="智能体平台 · QiZhiDa Agent Platform"
              wordmarkClassName="text-[22px] font-bold tracking-tight text-[var(--login-fg)]"
              subtitleClassName="mt-0.5 truncate text-[11px] tracking-wide text-[var(--login-fg-muted)]"
              ariaLabel={props.product}
            />
            <p className="mt-2 text-[12px] text-[var(--login-fg-muted)]">{props.tagline}</p>
          </div>
          </div>

          <p className="login-kicker mt-14 text-[var(--login-fg-muted)]">{props.badge}</p>
          <h2 className="login-display mt-5 text-[var(--login-fg)]">
            {props.title1}
            <span className="mt-1 block text-[var(--login-accent)]">{props.title2}</span>
          </h2>
          <p className="mt-6 max-w-[42ch] text-[15px] leading-8 text-[var(--login-fg-soft)]">{props.subtitle}</p>

          <ol className="mt-8 space-y-5">
            {props.bullets.map((b, index) => (
              <li key={b.title} className="grid grid-cols-[3.2rem_1fr] gap-3">
                <span className="login-kicker pt-1 text-[var(--login-accent)]">
                  {String(index + 1).padStart(2, '0')}
                </span>
                <span>
                  <span className="block text-[15px] text-[var(--login-fg)]">{b.title}</span>
                  <span className="mt-1 block text-[13px] leading-6 text-[var(--login-fg-muted)]">{b.desc}</span>
                </span>
              </li>
            ))}
          </ol>

          <div className="mt-8 grid grid-cols-3 gap-6">
            {props.stats.map((s) => (
              <div key={s.label}>
                <div className="font-mono text-[22px] font-medium leading-none tracking-tight text-[var(--login-fg)]">
                  {s.value}
                </div>
                <div className="mt-2 text-[12px] text-[var(--login-fg-muted)]">{s.label}</div>
              </div>
            ))}
          </div>
          <p className="mt-5 text-[12px] tracking-wide text-[var(--login-fg-muted)]">{props.footnote}</p>
          <span className="sr-only">{props.buildVersion}</span>
        </div>
      </div>
    </aside>
  );
}
