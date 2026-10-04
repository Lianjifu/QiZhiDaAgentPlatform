import { describe, expect, it } from 'vitest';
import { applyResponseAdapter, adaptErrorCode } from './responseAdapters';

describe('applyResponseAdapter', () => {
  it('adapts POST /v1/identity/login from snake_case to frontend shape', () => {
    const out = applyResponseAdapter('POST', '/v1/identity/login', {
      access_token: 'tok-abc',
      expires_at: '2026-09-25T12:00:00Z',
    });
    expect(out).toEqual({
      token: 'tok-abc',
      user: {
        id: '',
        email: '',
        role: 'user',
        tenantId: '',
        name: '',
        permissions: [],
        workspaceId: '',
        workspaceIds: [],
        environmentScopes: [],
        mfaEnabled: false,
      },
      expiresAt: '2026-09-25T12:00:00Z',
    });
  });

  it('tolerates camelCase accessToken as well', () => {
    const out = applyResponseAdapter('POST', '/v1/identity/login', {
      accessToken: 'tok-xyz',
      expiresAt: '2026-09-25T13:00:00Z',
    });
    expect((out as { token: string }).token).toBe('tok-xyz');
    expect((out as { expiresAt: string }).expiresAt).toBe('2026-09-25T13:00:00Z');
  });

  it('passes through unknown paths but camelizes keys', () => {
    const out = applyResponseAdapter('GET', '/v1/identity/workspaces', {
      items: [
        { tenant_id: 't-1', workspace_id: 'w-1', created_at: '2026-09-25' },
      ],
      total_count: 1,
    });
    expect(out).toEqual({
      items: [
        { tenantId: 't-1', workspaceId: 'w-1', createdAt: '2026-09-25' },
      ],
      totalCount: 1,
    });
  });

  it('passes through non-object data unchanged', () => {
    expect(applyResponseAdapter('GET', '/anything', null)).toBeNull();
    expect(applyResponseAdapter('GET', '/anything', 'hello')).toBe('hello');
    expect(applyResponseAdapter('GET', '/anything', 42)).toBe(42);
  });

  it('returns raw data when login response lacks access_token', () => {
    const raw = { code: 'E_AUTH_FAILED', message: 'bad password' };
    const out = applyResponseAdapter('POST', '/v1/identity/login', raw);
    // login 适配器 passthrough;后续 camelize 把 code/message 保持原样
    expect(out).toEqual(raw);
  });

  it('camelizes skill list response correctly', () => {
    const raw = {
      items: [
        {
          id: 'sk-1',
          tenant_id: 't-1',
          workspace_id: 'w-1',
          name: 'echo',
          version: '1.0.0',
          parameters_schema: { type: 'object' },
          created_at: '2026-09-25',
          updated_at: '2026-09-25',
        },
      ],
      total: 1,
    };
    const out = applyResponseAdapter('GET', '/v1/skills', raw);
    expect(out).toEqual({
      items: [
        {
          id: 'sk-1',
          tenantId: 't-1',
          workspaceId: 'w-1',
          name: 'echo',
          version: '1.0.0',
          parametersSchema: { type: 'object' },
          createdAt: '2026-09-25',
          updatedAt: '2026-09-25',
        },
      ],
      total: 1,
    });
  });
});

describe('adaptErrorCode', () => {
  it('maps backend AUTHENTICATION_FAILED → frontend E_AUTH_FAILED', () => {
    expect(adaptErrorCode('AUTHENTICATION_FAILED')).toBe('E_AUTH_FAILED');
  });

  it('maps every backend error.py stable code', () => {
    expect(adaptErrorCode('VALIDATION_ERROR')).toBe('E_BAD_REQUEST');
    expect(adaptErrorCode('FORBIDDEN')).toBe('E_FORBIDDEN');
    expect(adaptErrorCode('ACTION_DENIED')).toBe('E_FORBIDDEN');
    expect(adaptErrorCode('APPROVAL_REQUIRED')).toBe('E_APPROVAL_REQUIRED');
    expect(adaptErrorCode('NOT_FOUND')).toBe('E_NOT_FOUND');
    expect(adaptErrorCode('CONFLICT')).toBe('E_CONFLICT');
    expect(adaptErrorCode('BUSINESS_RULE_VIOLATED')).toBe('E_BUSINESS_RULE');
    expect(adaptErrorCode('RATE_LIMITED')).toBe('E_RATE_LIMITED');
    expect(adaptErrorCode('EXTERNAL_SERVICE_ERROR')).toBe('E_UPSTREAM');
    expect(adaptErrorCode('INTERNAL_ERROR')).toBe('E_INTERNAL');
  });

  it('passes through frontend E_* codes unchanged (idempotent for already-normalized inputs)', () => {
    expect(adaptErrorCode('E_AUTH_FAILED')).toBe('E_AUTH_FAILED');
    expect(adaptErrorCode('E_FORBIDDEN')).toBe('E_FORBIDDEN');
    expect(adaptErrorCode('E_IDENTITY_MOCK_FORBIDDEN')).toBe('E_IDENTITY_MOCK_FORBIDDEN');
  });

  it('returns the original code when backend raises a domain-specific error we have not catalogued', () => {
    // 保留运维可读性:不认识的 backend code 原样返回,便于日志定位
    expect(adaptErrorCode('TENANT_DENIED')).toBe('TENANT_DENIED');
    expect(adaptErrorCode('WORKSPACE_NOT_FOUND')).toBe('WORKSPACE_NOT_FOUND');
  });

  it('returns E_UNKNOWN for empty / missing input', () => {
    expect(adaptErrorCode('')).toBe('E_UNKNOWN');
  });
});