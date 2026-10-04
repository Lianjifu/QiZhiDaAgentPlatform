/**
 * LoginCredentialsForm — Step 1: 邮箱 / 密码 / MFA(可选) + 演示角色
 */
import { Eye, EyeOff } from 'lucide-react';
import { Button, Input } from '@qzdap/web-ui';
import { useState, type ComponentProps } from 'react';
import { LoginDemoChips, type LoginDemoRole } from './LoginDemoChips';

interface LoginCredentialsFormProps {
  email: string;
  setEmail: (v: string) => void;
  password: string;
  setPassword: (v: string) => void;
  mfa: string;
  setMfa: (v: string) => void;
  compositionHandlers: {
    onCompositionStart: () => void;
    onCompositionEnd: () => void;
  };
  submit: (e?: React.FormEvent) => void;
  isPending: boolean;
  rememberLabel: string;
  forgotLabel: string;
  emailLabel: string;
  emailPlaceholder: string;
  passwordLabel: string;
  passwordPlaceholder: string;
  mfaLabel: string;
  mfaHint: string;
  mfaPlaceholder: string;
  submitLabel: string;
  submittingLabel: string;
  ssoLabel: string;
  ssoTooltip: string;
  soonLabel: string;
  demoTitle: string;
  demoRoles: LoginDemoRole[];
  onChooseRole: (email: string) => void;
  termsPrefix: string;
  termsTos: string;
  termsPrivacy: string;
}

type InputProps = ComponentProps<typeof Input>;

export function LoginCredentialsForm(props: LoginCredentialsFormProps) {
  const [showPassword, setShowPassword] = useState(false);
  return (
    <div className="animate-[loginSlideUp_420ms_ease-out]">
      <form noValidate onSubmit={props.submit} className="space-y-6">
        <div className="login-field">
          <label className="mb-1 flex items-baseline justify-between text-[12px] text-[var(--text-secondary)]">
            <span>{props.emailLabel}</span>
          </label>
          <Input
            value={props.email}
            onChange={(e) => props.setEmail(e.target.value)}
            placeholder={props.emailPlaceholder}
            autoComplete="username"
            inputMode="email"
            {...(props.compositionHandlers as InputProps)}
          />
        </div>

        <div className="login-field">
          <label className="mb-1 block text-[12px] text-[var(--text-secondary)]">{props.passwordLabel}</label>
          <div className="relative">
            <Input
              type={showPassword ? 'text' : 'password'}
              value={props.password}
              onChange={(e) => props.setPassword(e.target.value)}
              placeholder={props.passwordPlaceholder}
              autoComplete="current-password"
              {...(props.compositionHandlers as InputProps)}
            />
            <button
              type="button"
              onClick={() => setShowPassword((value) => !value)}
              aria-label={showPassword ? '隐藏密码' : '显示密码'}
              title={showPassword ? '隐藏密码' : '显示密码'}
              className="absolute right-0 top-1/2 grid h-8 w-8 -translate-y-1/2 place-items-center text-[var(--text-muted)] hover:text-[var(--text)]"
            >
              {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        </div>

        <div className="login-field">
          <label className="mb-1 flex items-center justify-between text-[12px] text-[var(--text-secondary)]">
            <span>{props.mfaLabel}</span>
            <span className="text-[11px] text-[var(--text-muted)]">{props.mfaHint}</span>
          </label>
          <Input
            value={props.mfa}
            onChange={(e) => props.setMfa(e.target.value.replace(/\D/g, '').slice(0, 6))}
            placeholder={props.mfaPlaceholder}
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            className="font-mono tracking-[0.28em]"
            {...(props.compositionHandlers as InputProps)}
          />
        </div>

        <div className="flex items-center justify-between pt-1 text-[13px]">
          <label className="flex cursor-pointer items-center gap-2 text-[var(--text-muted)]">
            <input
              type="checkbox"
              defaultChecked
              className="h-3.5 w-3.5 rounded-sm border-[var(--login-rule)] accent-[var(--login-blue)]"
            />
            {props.rememberLabel}
          </label>
          <a className="text-[var(--text)] underline decoration-[var(--login-rule)] underline-offset-4 hover:decoration-[var(--login-blue)]" href="#">
            {props.forgotLabel}
          </a>
        </div>

        <Button
          type="submit"
          loading={props.isPending}
          size="lg"
          className="login-cta mt-1 w-full text-[14px] font-medium"
        >
          {props.isPending ? props.submittingLabel : props.submitLabel}
        </Button>

        <button
          type="button"
          disabled
          aria-disabled="true"
          title={props.ssoTooltip}
          className="login-sso flex w-full items-center justify-between border border-[var(--login-rule)] px-4 py-3 text-left text-[13px] text-[var(--text-secondary)] disabled:cursor-not-allowed"
        >
          <span>{props.ssoLabel}</span>
          <span className="login-kicker text-[10px] text-[var(--text-muted)]">{props.soonLabel}</span>
        </button>

        <LoginDemoChips title={props.demoTitle} roles={props.demoRoles} onChoose={props.onChooseRole} />
      </form>

      <p className="mt-6 text-[11px] leading-relaxed text-[var(--text-muted)]">
        {props.termsPrefix}{' '}
        <a className="text-[var(--text)] underline decoration-[var(--login-rule)] underline-offset-4" href="#">
          {props.termsTos}
        </a>{' '}
        ·{' '}
        <a className="text-[var(--text)] underline decoration-[var(--login-rule)] underline-offset-4" href="#">
          {props.termsPrivacy}
        </a>
      </p>
    </div>
  );
}
