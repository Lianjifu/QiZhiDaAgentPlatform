/**
 * LoginPage — 企智搭 · 门禁账册
 *
 * 左:墨色舞台(品牌、编号能力、指标)
 * 右:暖纸表单(凭据 / MFA)
 * 鉴权副作用全部委托给 useLogin。
 */
import { ShieldCheck, Sun, Moon, UserRound, Shield, ScrollText, Gauge, Lock, Bot } from 'lucide-react';
import { toast } from '@qzdap/web-ui';
import { BrandLogo } from '@/components/feedback/BrandLogo';
import { useUiStore } from '@/stores/uiStore';
import { useT } from '@/i18n';
import { TrustStrip } from '@/features/auth/TrustStrip';
import { useLogin } from './useLogin';
import { LoginBrandPanel, type LoginHeroBullet, type LoginHeroStat } from './LoginBrandPanel';
import { LoginCredentialsForm } from './LoginCredentialsForm';
import { LoginMfaStep } from './LoginMfaStep';
import type { LoginDemoRole } from './LoginDemoChips';

export default function LoginPage() {
  const { theme, toggleTheme } = useUiStore();
  const { t } = useT();

  const {
    step,
    goBack,
    email,
    setEmail,
    password,
    setPassword,
    mfa,
    setMfa,
    compositionHandlers,
    submit,
    isPending,
    chooseRole,
  } = useLogin({
    onAuthenticated: (data) => {
      const name = data.user.name || data.user.email || '';
      toast.success(t('login.welcomeToastPrefix') + name);
    },
    onMfaRequired: () => {
      toast.info(t('login.mfa.requiredHint'));
    },
    onEmptyCredentials: () => {
      toast.warn(t('login.error.empty'));
    },
    onInvalidMfa: () => {
      toast.warn(t('login.mfa.codeLength'));
    },
    onLoginError: (message) => {
      toast.error(message ?? t('login.error.generic'));
    },
    onMfaSoon: () => {
      toast.info(t('login.mfa.soon'));
    },
  });

  const trustItems = [
    { label: t('login.trust.grade'), sub: t('login.trust.gradeSub'), icon: <ShieldCheck className="h-3 w-3" /> },
    { label: t('login.trust.soc'), sub: t('login.trust.socSub'), icon: <Shield className="h-3 w-3" /> },
    { label: t('login.trust.private'), sub: t('login.trust.privateSub'), icon: <Lock className="h-3 w-3" /> },
    { label: t('login.trust.audit'), sub: t('login.trust.auditSub'), icon: <ScrollText className="h-3 w-3" /> },
  ];

  const demoRoles: LoginDemoRole[] = [
    {
      email: 'user@acme.com',
      label: t('login.demoRoleUser'),
      sub: t('login.demoRoleUserSub'),
      Icon: UserRound,
    },
    {
      email: 'admin@acme.com',
      label: t('login.demoRoleAdmin'),
      sub: t('login.demoRoleAdminSub'),
      Icon: Shield,
    },
  ];

  const heroBullets: LoginHeroBullet[] = [
    {
      Icon: ShieldCheck,
      tone: 'brand',
      title: t('login.hero.bullet1Title'),
      desc: t('login.hero.bullet1Desc'),
    },
    {
      Icon: Bot,
      tone: 'purple',
      title: t('login.hero.bullet2Title'),
      desc: t('login.hero.bullet2Desc'),
    },
    {
      Icon: Gauge,
      tone: 'muted',
      title: t('login.hero.bullet3Title'),
      desc: t('login.hero.bullet3Desc'),
    },
  ];

  const heroStats: LoginHeroStat[] = [
    { value: t('login.hero.stat1Value'), label: t('login.hero.stat1Label') },
    { value: t('login.hero.stat2Value'), label: t('login.hero.stat2Label') },
    { value: t('login.hero.stat3Value'), label: t('login.hero.stat3Label') },
  ];

  return (
    <div className="login-page relative h-screen w-screen overflow-x-hidden overflow-y-auto">
      <div className="grid min-h-full grid-cols-1 md:grid-cols-[minmax(0,2fr)_minmax(22rem,1fr)]">
        <LoginBrandPanel
          product={t('login.brand.product')}
          tagline={t('login.brand.tagline')}
          badge={t('login.hero.badge')}
          title1={t('login.hero.title1')}
          title2={t('login.hero.title2')}
          subtitle={t('login.hero.subtitle')}
          bullets={heroBullets}
          stats={heroStats}
        />

        <main className="login-sheet relative flex min-h-full flex-col">
          <button
            onClick={toggleTheme}
            aria-label={theme === 'light' ? t('login.theme.lightTip') : t('login.theme.darkTip')}
            title={theme === 'light' ? t('login.theme.lightTip') : t('login.theme.darkTip')}
            className="absolute right-5 top-5 z-30 grid h-9 w-9 place-items-center rounded-full border border-[var(--login-rule)] text-[var(--text-muted)] transition-colors hover:text-[var(--login-blue)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--login-blue)]/30 md:right-7 md:top-7"
          >
            {theme === 'light' ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
          </button>

          <div className="flex flex-1 items-start justify-center px-6 py-16 sm:px-8 md:items-center xl:px-12 2xl:px-16">
            <div className="w-full max-w-[26rem] xl:max-w-[28rem]">
              <div className="mb-8 flex items-center gap-2.5 md:hidden">
                <BrandLogo
                  size={36}
                  withWordmark
                  wordmark="企智搭"
                  ariaLabel="企智搭 · 智能体平台"
                />
              </div>
              {step === 'credentials' ? (
                <header className="mb-8">
                  <p className="login-kicker text-[var(--text-muted)]">WORKSPACE GATE</p>
                  <h1 className="login-sheet-title mt-3 text-[34px] leading-none text-[var(--text)]">{t('login.title')}</h1>
                  <p className="mt-3 max-w-[34ch] text-[13px] leading-6 text-[var(--text-muted)]">{t('login.subtitle')}</p>
                </header>
              ) : null}
              {step === 'credentials' ? (
                <LoginCredentialsForm
                  email={email}
                  setEmail={setEmail}
                  password={password}
                  setPassword={setPassword}
                  mfa={mfa}
                  setMfa={setMfa}
                  compositionHandlers={compositionHandlers}
                  submit={submit}
                  isPending={isPending}
                  rememberLabel={t('login.rememberMe')}
                  forgotLabel={t('login.forgotPassword')}
                  emailLabel={t('login.emailLabel')}
                  emailPlaceholder={t('login.emailPlaceholder')}
                  passwordLabel={t('login.passwordLabel')}
                  passwordPlaceholder={t('login.passwordPlaceholder')}
                  mfaLabel={t('login.mfaLabel')}
                  mfaHint={t('login.mfaHint')}
                  mfaPlaceholder={t('login.mfaPlaceholder')}
                  submitLabel={t('login.submit')}
                  submittingLabel={t('login.submitting')}
                  ssoLabel={t('login.sso')}
                  ssoTooltip={t('login.sso.tooltip')}
                  soonLabel={t('login.mfa.soon')}
                  demoTitle={t('login.demoTitle')}
                  demoRoles={demoRoles}
                  onChooseRole={chooseRole}
                  termsPrefix={t('login.termsPrefix')}
                  termsTos={t('login.terms.tos')}
                  termsPrivacy={t('login.terms.privacy')}
                />
              ) : (
                <LoginMfaStep
                  mfa={mfa}
                  setMfa={setMfa}
                  compositionHandlers={compositionHandlers}
                  submit={submit}
                  isPending={isPending}
                  goBack={goBack}
                  title={t('login.mfa.title')}
                  subtitle={t('login.mfa.subtitle')}
                  mfaLabel={t('login.mfaLabel')}
                  mfaPlaceholder={t('login.mfaPlaceholder')}
                  submitLabel={t('login.submit')}
                  submittingLabel={t('login.submitting')}
                  backLabel={t('login.mfa.back')}
                  resendLabel={t('login.mfa.resend')}
                  soonLabel={t('login.mfa.soon')}
                />
              )}

              <div id="security" className="mt-8 border-t border-[var(--login-rule)] pt-5">
                <TrustStrip items={trustItems} tone="light" className="login-trust" />
                <div className="mt-3 text-[11px] text-[var(--text-muted)]">
                  <a href="#security" className="hover:text-[var(--text)]">安全与合规说明</a>
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
