/**
 * API 客户端层 — 默认请求真实后端（粗粒度网关 / Vite 代理）。
 * Mock 适配器仅在应用入口显式注入时启用（VITE_USE_MOCK=true）。
 */
import type { ApiResponse } from '@qzdap/web-types';
import { translateApiPath, USER_ID_PLACEHOLDER, type HttpMethod } from './pathMap';
import { applyResponseAdapter, adaptErrorCode } from './responseAdapters';

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined>;
  headers?: Record<string, string>;
  signal?: AbortSignal;
  timeoutMs?: number;
}

export class ApiError extends Error {
  constructor(public code: string, message: string, public status = 500) {
    super(message);
  }
}

const DEFAULT_TIMEOUT = 15_000;

/** fetch Header values must be ByteString (ISO-8859-1); encode anything outside. */
function sanitizeHeaderValue(value: string): string {
  for (let i = 0; i < value.length; i += 1) {
    if (value.charCodeAt(i) > 255) return encodeURIComponent(value);
  }
  return value;
}

function sanitizeHeaders(headers: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(headers)) {
    if (v == null || String(v).trim() === '') continue;
    out[k] = sanitizeHeaderValue(String(v));
  }
  return out;
}

function extractErrorPayload(json: unknown, fallback: string): { code: string; message: string } {
  if (!json || typeof json !== 'object') return { code: 'E_UNKNOWN', message: fallback };
  const root = json as Record<string, unknown>;
  const nested = root.error && typeof root.error === 'object'
    ? root.error as Record<string, unknown>
    : null;
  const codeRaw = String(nested?.code ?? root.code ?? '');
  const fromNested = nested?.message;
  const fromRoot = root.message;
  let message = fallback;
  if (typeof fromNested === 'string' && fromNested) message = fromNested;
  else if (typeof fromRoot === 'string' && fromRoot) message = fromRoot;
  else if (typeof root.detail === 'string' && root.detail) message = root.detail;
  else if (Array.isArray(root.detail) && root.detail[0] && typeof root.detail[0] === 'object') {
    const first = root.detail[0] as { msg?: unknown };
    if (typeof first.msg === 'string' && first.msg) message = first.msg;
  }
  return { code: adaptErrorCode(codeRaw), message };
}

function isLoginPath(path: string): boolean {
  const lower = path.toLowerCase();
  return lower.includes('/identity/login') || lower.includes('/auth/login');
}

function resolveRequestURL(baseURL: string, path: string, query?: RequestOptions['query']): string {
  let href: string;
  if (!baseURL) {
    href = path.startsWith('/') ? path : `/${path}`;
  } else {
    href = new URL(path, baseURL.endsWith('/') ? baseURL : `${baseURL}/`).toString();
  }
  if (!query) return href;
  const u = href.startsWith('http') ? new URL(href) : new URL(href, 'http://local.invalid');
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined) u.searchParams.set(k, String(v));
  }
  if (!href.startsWith('http')) {
    return `${u.pathname}${u.search}`;
  }
  return u.toString();
}

export class ApiClient {
  constructor(
    private baseURL: string,
    private getAuthToken: () => string | null = () => null,
    private mockHandler?: (path: string, opts: RequestOptions) => Promise<unknown>,
    private getContextHeaders: () => Record<string, string> = () => ({}),
    private onUnauthorized?: (info: { path: string; status: number }) => void,
    /** uid-注入型路径(/api/api-keys 等)需要替换 <<USER_ID>> 占位符时调用;
     *  返回 null 表示未登录,会在 request() 抛 E_AUTH_REQUIRED */
    private getUserId?: () => string | null,
  ) {}

  async request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
    const token = this.getAuthToken();
    const requestHeaders: Record<string, string> = {
      ...opts.headers,
      ...this.getContextHeaders(),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
    const method = (opts.method?.toUpperCase() ?? 'GET') as HttpMethod;
    const translated = translateApiPath(path, method);
    if (this.mockHandler) {
      // mock 模式：保留原 /api/... 路径喂给 mockHandler 的 if/else ladder；
      // 响应经 mockAdapter 出口时已经走 adapters，形状与真模式对齐。
      const data = await this.mockHandler(path, { ...opts, headers: requestHeaders });
      return data as T;
    }
    const controller = new AbortController();
    const t = setTimeout(() => controller.abort(), opts.timeoutMs ?? DEFAULT_TIMEOUT);
    try {
      // uid-注入:仅真模式触发;getUserId 缺失或返回 null 时直接抛 E_AUTH_REQUIRED
      let backendPath = translated.backendPath;
      if (translated.needsUserId && backendPath.includes(USER_ID_PLACEHOLDER)) {
        const uid = this.getUserId?.();
        if (!uid) {
          throw new ApiError('E_AUTH_REQUIRED', '该端点需要当前用户身份,请先登录', 401);
        }
        backendPath = backendPath.split(USER_ID_PLACEHOLDER).join(encodeURIComponent(uid));
      }
      const url = resolveRequestURL(this.baseURL, backendPath, opts.query);
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        ...sanitizeHeaders(requestHeaders),
      };

      let res: Response;
      try {
        res = await fetch(url, {
          method: opts.method ?? 'GET',
          headers,
          body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
          signal: opts.signal ?? controller.signal,
        });
      } catch (err) {
        const aborted = err instanceof DOMException && err.name === 'AbortError';
        if (aborted) {
          throw new ApiError('E_TIMEOUT', '请求超时，请确认控制面网关是否可达', 408);
        }
        const hint = this.baseURL
          ? `无法连接控制面 ${this.baseURL}，请先启动：cd backend && make run`
          : '无法连接控制面（同源 /api → Vite 代理 → :8089 网关）。请确认已启动后端栈（cd backend && make compose-up-monolith 或 make run），并重启前端 dev（环境变量变更需重启 Vite）';
        throw new ApiError('E_NETWORK', hint, 0);
      }
      let json: ApiResponse<T>;
      try {
        json = (await res.json()) as ApiResponse<T>;
      } catch {
        throw new ApiError('E_BAD_RESPONSE', `控制面返回非 JSON（HTTP ${res.status}）`, res.status);
      }
      if (!res.ok) {
        const { code, message } = extractErrorPayload(json, '请求失败');
        if ((res.status === 401 || code === 'E_IDENTITY_MOCK_FORBIDDEN') && !isLoginPath(backendPath)) {
          this.onUnauthorized?.({ path: backendPath, status: res.status });
        }
        throw new ApiError(code, message, res.status);
      }
      // Envelope-tolerant rawData pick:
      //  - 大多数 endpoint 返回 `{ok, data}` → 取 data 喂 adapter
      //  - 部分端点(login 等)直接返回 raw shape(`{access_token, user}`,
      //    无 `ok` 字段)→ 整个 json 喂 adapter,由 per-path adapter 折字段
      //  后端偶发返回 data: null（Go nil slice）；对数组消费方统一兜底为 []，避免 .filter 崩溃
      const isEnvelope = json && typeof json === 'object' && 'ok' in (json as object);
      const rawData = (
        isEnvelope ? (json as { data?: unknown }).data ?? null : (json as unknown)
      ) as T;
      return applyResponseAdapter(method, backendPath, rawData) as T;
    } finally {
      clearTimeout(t);
    }
  }

  get<T>(path: string, opts?: Omit<RequestOptions, 'method' | 'body'>) {
    return this.request<T>(path, { ...opts, method: 'GET' });
  }
  post<T>(path: string, body?: unknown, opts?: Omit<RequestOptions, 'method' | 'body'>) {
    return this.request<T>(path, { ...opts, method: 'POST', body });
  }
  put<T>(path: string, body?: unknown, opts?: Omit<RequestOptions, 'method' | 'body'>) {
    return this.request<T>(path, { ...opts, method: 'PUT', body });
  }
  delete<T>(path: string, opts?: Omit<RequestOptions, 'method' | 'body'>) {
    return this.request<T>(path, { ...opts, method: 'DELETE' });
  }

  /** multipart 上传；Mock 模式下自动转为 contentBase64 JSON。 */
  async upload<T>(path: string, form: FormData, opts: Omit<RequestOptions, 'method' | 'body'> = {}): Promise<T> {
    const token = this.getAuthToken();
    const requestHeaders: Record<string, string> = {
      ...opts.headers,
      ...this.getContextHeaders(),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
    if (this.mockHandler) {
      const file = form.get('file');
      if (file == null || typeof file === 'string') {
        throw new ApiError('E_BAD_REQUEST', '缺少 file 字段', 400);
      }
      const name = 'name' in file && typeof file.name === 'string' ? file.name : 'upload.bin';
      const buf = new Uint8Array(await file.arrayBuffer());
      let binary = '';
      for (let i = 0; i < buf.length; i += 1) binary += String.fromCharCode(buf[i]!);
      const contentBase64 = btoa(binary);
      return (await this.mockHandler(path, {
        ...opts,
        method: 'POST',
        headers: requestHeaders,
        body: { fileName: name, contentBase64 },
      })) as T;
    }
    const controller = new AbortController();
    const t = setTimeout(() => controller.abort(), opts.timeoutMs ?? DEFAULT_TIMEOUT);
    try {
      const uploadTranslated = translateApiPath(path, 'POST');
      const url = resolveRequestURL(this.baseURL, uploadTranslated.backendPath, opts.query);
      const headers = sanitizeHeaders(requestHeaders);
      // 不要手动设置 Content-Type，由浏览器带 multipart boundary
      let res: Response;
      try {
        res = await fetch(url, {
          method: 'POST',
          headers,
          body: form,
          signal: opts.signal ?? controller.signal,
        });
      } catch (err) {
        const aborted = err instanceof DOMException && err.name === 'AbortError';
        if (aborted) {
          throw new ApiError('E_TIMEOUT', '上传超时，请确认控制面网关是否可达', 408);
        }
        throw new ApiError('E_NETWORK', '无法连接控制面完成上传', 0);
      }
      let json: ApiResponse<T>;
      try {
        json = (await res.json()) as ApiResponse<T>;
      } catch {
        throw new ApiError('E_BAD_RESPONSE', `控制面返回非 JSON（HTTP ${res.status}）`, res.status);
      }
      if (!res.ok || !json.ok) {
        const { code, message } = extractErrorPayload(json, '上传失败');
        if ((res.status === 401 || code === 'E_IDENTITY_MOCK_FORBIDDEN') && !isLoginPath(uploadTranslated.backendPath)) {
          this.onUnauthorized?.({ path: uploadTranslated.backendPath, status: res.status });
        }
        throw new ApiError(code, message, res.status);
      }
      return (json.data ?? null) as T;
    } finally {
      clearTimeout(t);
    }
  }

  /** SSE 流式读取。mock 模式按 JSON 一次性返回。 */
  async *streamEvents(
    path: string,
    body?: unknown,
    opts: Omit<RequestOptions, 'method' | 'body'> = {},
  ): AsyncGenerator<{ event: string; data: unknown }> {
    const token = this.getAuthToken();
    const requestHeaders: Record<string, string> = {
      ...opts.headers,
      ...this.getContextHeaders(),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
    const translated = translateApiPath(path, 'POST');
    if (this.mockHandler) {
      const data = await this.mockHandler(path, { ...opts, method: 'POST', headers: requestHeaders, body });
      yield { event: 'message', data };
      yield { event: 'done', data: { kind: 'done' } };
      return;
    }
    const controller = new AbortController();
    const t = setTimeout(() => controller.abort(), opts.timeoutMs ?? 120_000);
    try {
      const url = resolveRequestURL(this.baseURL, translated.backendPath, opts.query);
      const res = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
          ...sanitizeHeaders(requestHeaders),
        },
        body: body !== undefined ? JSON.stringify(body) : undefined,
        signal: opts.signal ?? controller.signal,
      });
      if (!res.ok || !res.body) {
        throw new ApiError('E_STREAM', `流式请求失败（HTTP ${res.status}）`, res.status);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
        const parts = buffer.split('\n\n');
        buffer = parts.pop() ?? '';
        for (const block of parts) {
          let event = 'message';
          let dataLine = '';
          for (const line of block.split('\n')) {
            if (line.startsWith('event:')) event = line.slice(6).trim();
            if (line.startsWith('data:')) dataLine += line.slice(5).trim();
          }
          if (!dataLine) continue;
          try {
            yield { event, data: JSON.parse(dataLine) };
          } catch {
            yield { event, data: dataLine };
          }
        }
        if (done) break;
      }
    } finally {
      clearTimeout(t);
    }
  }
}

/** 全局单例 — 在 web 应用启动时注入 */
let _client: ApiClient | null = null;

export function setApiClient(c: ApiClient) {
  _client = c;
}

export function getApiClient(): ApiClient {
  if (!_client) throw new Error('ApiClient 未初始化 — 请在应用入口调用 setApiClient');
  return _client;
}

export * from './mock';
import * as mockModule from './mock';
export const mock = mockModule;

export { mockHandlerWithAdapters } from './mockAdapter';
export { translateApiPath } from './pathMap';
export { applyResponseAdapter, adaptErrorCode } from './responseAdapters';
