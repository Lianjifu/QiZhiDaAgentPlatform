import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const query = vi.hoisted(() => vi.fn());
const mutation = vi.hoisted(() => vi.fn());
const navigateMock = vi.hoisted(() => vi.fn());
const authState = vi.hoisted(() => ({
  isAuthed: false,
  user: null as null | { id: string; role: string; name?: string; email?: string },
  login: vi.fn(),
}));

vi.mock('@/services/query', () => ({
  useApiQuery: query,
  useApiMutation: mutation,
  useApiUploadMutation: vi.fn(),
}));

vi.mock('@/features/auth', () => ({
  useAuthStore: (selector: any) => {
    if (typeof selector === 'function') return selector(authState);
    return authState;
  },
}));

vi.mock('@/stores/uiStore', () => ({
  useUiStore: () => ({ theme: 'light', toggleTheme: vi.fn() }),
}));

vi.mock('react-router-dom', async () => {
  const real = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...real, useNavigate: () => navigateMock };
});

import Login from '@/features/auth/login';
import { I18nProvider } from '@/i18n';

function renderLogin(initialEntries: string[] | string) {
  const entries = typeof initialEntries === 'string' ? [initialEntries] : initialEntries;
  return render(
    <I18nProvider>
      <MemoryRouter initialEntries={entries}>
        <Login />
      </MemoryRouter>
    </I18nProvider>,
  );
}

const idleMutation = { mutate: vi.fn(), isPending: false, data: undefined, error: null };
const idleQuery = {
  data: undefined as undefined | null | Record<string, unknown>,
  isLoading: false,
  error: null,
  refetch: vi.fn().mockResolvedValue({ data: null }),
};

beforeEach(() => {
  vi.stubGlobal('localStorage', { getItem: () => null, setItem: vi.fn() });
  query.mockReset();
  mutation.mockReset();
  navigateMock.mockReset();
  authState.isAuthed = false;
  authState.user = null;
  authState.login.mockReset();
  query.mockReturnValue(idleQuery);
  mutation.mockReturnValue(idleMutation);
});

afterEach(cleanup);

describe('Login', () => {
  it('renders email, password, MFA fields, submit, three demo chips and trust strip', () => {
    renderLogin(['/login']);
    expect(screen.getByPlaceholderText('name@company.com')).toBeTruthy();
    expect(screen.getByPlaceholderText('••••••••')).toBeTruthy();
    expect(screen.getByPlaceholderText('请输入 6 位验证码')).toBeTruthy();
    expect(screen.getByRole('button', { name: '登录工作台' })).toBeTruthy();
    // 2 demo chips
    expect(screen.getByRole('button', { name: /普通用户登录/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: /管理员登录/ })).toBeTruthy();
    // 4 trust badges
    expect(screen.getByText('等保三级')).toBeTruthy();
    expect(screen.getByText('SOC 2')).toBeTruthy();
    expect(screen.getByText('私有化')).toBeTruthy();
    expect(screen.getByText('审计留痕')).toBeTruthy();
    // hero stats
    expect(screen.getByText('15+')).toBeTruthy();
    expect(screen.getByText('99.99%')).toBeTruthy();
    expect(screen.getByText('< 50ms')).toBeTruthy();
    // hero title (appears in both brand mark and hero — assert at least one match)
    expect(screen.getAllByText('企智搭').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByLabelText('企智搭 · 智能体平台').length).toBeGreaterThanOrEqual(1);
    // new copy: smart/control/governance terminology
    expect(screen.getByText('持续验证 · 零信任')).toBeTruthy();
    expect(screen.getByText('智能体协同 · 受控执行')).toBeTruthy();
    expect(screen.getByText('资源治理 · 价值可度量')).toBeTruthy();
    expect(screen.getByText('智能体能力')).toBeTruthy();
  });

  it('clicking 管理员登录 demo chip auto-fills and submits admin credentials', () => {
    const mutate = vi.fn();
    mutation.mockReturnValue({ mutate, isPending: false, data: undefined, error: null });
    renderLogin(['/login']);
    fireEvent.click(screen.getByRole('button', { name: /管理员登录/ }));
    const emailInput = screen.getByPlaceholderText('name@company.com') as HTMLInputElement;
    const pwInput = screen.getByPlaceholderText('••••••••') as HTMLInputElement;
    expect(emailInput.value).toBe('admin@acme.com');
    expect(pwInput.value).toBe('dev-admin-password-change-me');
    expect(mutate).toHaveBeenCalledWith({ email: 'admin@acme.com', password: 'dev-admin-password-change-me' });
  });

  it('clicking 普通用户登录 demo chip uses the user account', () => {
    const mutate = vi.fn();
    mutation.mockReturnValue({ mutate, isPending: false, data: undefined, error: null });
    renderLogin(['/login']);
    fireEvent.click(screen.getByRole('button', { name: /普通用户登录/ }));
    expect((screen.getByPlaceholderText('name@company.com') as HTMLInputElement).value).toBe('user@acme.com');
    expect(mutate).toHaveBeenCalledWith({ email: 'user@acme.com', password: 'dev-admin-password-change-me' });
  });

  it('form submit calls mutate with email + password', () => {
    const mutate = vi.fn();
    mutation.mockReturnValue({ mutate, isPending: false, data: undefined, error: null });
    renderLogin(['/login']);
    fireEvent.change(screen.getByPlaceholderText('name@company.com'), { target: { value: 'me@acme.com' } });
    fireEvent.change(screen.getByPlaceholderText('••••••••'), { target: { value: 'secret' } });
    fireEvent.click(screen.getByRole('button', { name: '登录工作台' }));
    expect(mutate).toHaveBeenCalledOnce();
    expect(mutate).toHaveBeenCalledWith({ email: 'me@acme.com', password: 'secret' });
  });

  it('redirects already-authed user to /home', () => {
    authState.isAuthed = true;
    authState.user = { id: 'u1', role: 'user', name: 'Tester' };
    renderLogin(['/login']);
    expect(navigateMock).toHaveBeenCalledWith('/home', { replace: true });
  });

  it('redirects already-authed admin to /admin/overview', () => {
    authState.isAuthed = true;
    authState.user = { id: 'u1', role: 'admin', name: 'Admin', email: 'admin@acme.com' };
    renderLogin(['/login']);
    expect(navigateMock).toHaveBeenCalledWith('/admin/overview', { replace: true });
  });

  it('blocks form submit during IME composition and fires after compositionend', () => {
    const mutate = vi.fn();
    mutation.mockReturnValue({ mutate, isPending: false, data: undefined, error: null });
    renderLogin(['/login']);
    fireEvent.change(screen.getByPlaceholderText('name@company.com'), { target: { value: 'me@acme.com' } });
    fireEvent.change(screen.getByPlaceholderText('••••••••'), { target: { value: 'secret' } });

    const email = screen.getByPlaceholderText('name@company.com');
    fireEvent.compositionStart(email);
    fireEvent.click(screen.getByRole('button', { name: '登录工作台' }));
    expect(mutate).not.toHaveBeenCalled();

    fireEvent.compositionEnd(email);
    fireEvent.click(screen.getByRole('button', { name: '登录工作台' }));
    expect(mutate).toHaveBeenCalledOnce();
  });

  it('transitions to MFA step when URL has ?step=mfa', () => {
    renderLogin(['/login?step=mfa']);
    // MFA step: page title becomes "验证身份"
    expect(screen.getByText('验证身份')).toBeTruthy();
    expect(screen.getByRole('button', { name: '返回登录' })).toBeTruthy();
  });

  it('transitions to MFA step when submitted email matches _mfa@acme.com pattern', () => {
    let capturedSuccess: ((d: any) => void) | undefined;
    const mutate = vi.fn((vars: { email: string }) => {
      capturedSuccess?.({
        token: 'tk',
        user: { id: '', email: vars.email, role: 'user', tenantId: '', name: '', permissions: [] },
      });
    });
    mutation.mockImplementation((_path: string, opts: any) => {
      capturedSuccess = opts?.onSuccess;
      return { mutate, isPending: false, data: undefined, error: null };
    });
    renderLogin(['/login']);
    fireEvent.change(screen.getByPlaceholderText('name@company.com'), {
      target: { value: 'admin_mfa@acme.com' },
    });
    fireEvent.change(screen.getByPlaceholderText('••••••••'), { target: { value: 'secret' } });
    fireEvent.click(screen.getByRole('button', { name: '登录工作台' }));

    // Should now show MFA step
    expect(screen.getByText('验证身份')).toBeTruthy();
  });

  it('SSO button is disabled with tooltip', () => {
    renderLogin(['/login']);
    const sso = screen.getByRole('button', { name: /企业 SSO 登录/ }) as HTMLButtonElement;
    expect(sso.disabled).toBe(true);
    expect(sso.getAttribute('aria-disabled')).toBe('true');
    expect(sso.getAttribute('title')).toBe('即将支持企业 SSO 登录');
  });
});
