/**
 * LoginMfaStep — Step 2: 多因素验证
 */
import { ArrowLeft, RotateCw } from 'lucide-react';
import { Button, Input, toast } from '@qzdap/web-ui';
import type { ComponentProps } from 'react';

interface LoginMfaStepProps {
  mfa: string;
  setMfa: (v: string) => void;
  compositionHandlers: {
    onCompositionStart: () => void;
    onCompositionEnd: () => void;
  };
  submit: (e?: React.FormEvent) => void;
  isPending: boolean;
  goBack: () => void;
  title: string;
  subtitle: string;
  mfaLabel: string;
  mfaPlaceholder: string;
  submitLabel: string;
  submittingLabel: string;
  backLabel: string;
  resendLabel: string;
  soonLabel: string;
}

type InputProps = ComponentProps<typeof Input>;

export function LoginMfaStep(props: LoginMfaStepProps) {
  return (
    <div className="animate-[loginSlideUp_420ms_ease-out]">
      <button
        type="button"
        onClick={props.goBack}
        className="mb-6 inline-flex items-center gap-1.5 text-[12px] text-[var(--text-muted)] hover:text-[var(--text)]"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        {props.backLabel}
      </button>

      <p className="login-kicker text-[var(--text-muted)]">SECOND FACTOR</p>
      <h1 className="login-sheet-title mt-3 text-[34px] leading-none text-[var(--text)]">{props.title}</h1>
      <p className="mt-3 text-[13px] leading-6 text-[var(--text-muted)]">{props.subtitle}</p>

      <form
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          props.submit();
        }}
        className="mt-8 space-y-6"
      >
        <div className="login-field">
          <label className="mb-1 block text-[12px] text-[var(--text-secondary)]">{props.mfaLabel}</label>
          <Input
            value={props.mfa}
            onChange={(e) => props.setMfa(e.target.value.replace(/\D/g, '').slice(0, 6))}
            placeholder={props.mfaPlaceholder}
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            className="text-center font-mono text-lg tracking-[0.42em]"
            autoFocus
            {...(props.compositionHandlers as InputProps)}
          />
        </div>

        <Button
          type="submit"
          loading={props.isPending}
          size="lg"
          className="login-cta w-full text-[14px] font-medium"
        >
          {props.isPending ? props.submittingLabel : props.submitLabel}
        </Button>

        <button
          type="button"
          onClick={() => toast.info(props.soonLabel)}
          className="inline-flex w-full items-center justify-center gap-1.5 text-[12px] text-[var(--text-muted)] hover:text-[var(--text)]"
        >
          <RotateCw className="h-3.5 w-3.5" />
          {props.resendLabel}
        </button>
      </form>
    </div>
  );
}
