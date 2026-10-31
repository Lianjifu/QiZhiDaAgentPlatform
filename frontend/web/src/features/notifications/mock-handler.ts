/**
 * 本地 mock handler — 在 demo 模式下接管 /api/admin/notifications 调用。
 * 其他路径走 `mockHandlerWithAdapters`(默认仓库内 mock)。
 * 装配见 `src/main.tsx → installApiClient`。
 */
import type {
  NotificationChannel,
  WebhookEntry,
  NotificationGroup,
  DeliveryEvent,
  CreateChannelVars,
  UpdateChannelVars,
  CreateGroupVars,
  BatchStatusVars,
} from './schema';
import {
  mockChannels,
  mockWebhooks,
  mockGroups,
  mockEvents,
} from './fixtures';
import { defaultChannelConfig, defaultChannelTemplate } from './components/constants';

interface MockState {
  channels: NotificationChannel[];
  webhooks: WebhookEntry[];
  groups: NotificationGroup[];
  events: DeliveryEvent[];
}

const state: MockState = {
  channels: [...mockChannels],
  webhooks: [...mockWebhooks],
  groups: [...mockGroups],
  events: [...mockEvents],
};

function sleep(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms));
}

function withDelay<T>(value: T): Promise<T> {
  return sleep(60).then(() => value);
}

function uid(prefix: string) {
  return `${prefix}-${Math.random().toString(36).slice(2, 8)}`;
}

export async function adminNotificationsMockHandler(
  path: string,
  opts: { method?: string; body?: unknown },
): Promise<unknown> {
  const method = opts.method?.toUpperCase() ?? 'GET';

  if (path === '/api/admin/notifications/channels' && method === 'GET') {
    return withDelay(state.channels.map((c) => ({ ...c })));
  }
  if (path === '/api/admin/notifications/webhooks' && method === 'GET') {
    return withDelay(state.webhooks.map((w) => ({ ...w })));
  }
  if (path === '/api/admin/notifications/groups' && method === 'GET') {
    return withDelay(state.groups.map((g) => ({ ...g })));
  }
  if (path === '/api/admin/notifications/events' && method === 'GET') {
    return withDelay(state.events.map((e) => ({ ...e })));
  }

  if (path === '/api/admin/notifications/channels/__batch__' && method === 'POST') {
    const body = (opts.body ?? {}) as BatchStatusVars;
    state.channels = state.channels.map((c) =>
      body.ids.includes(c.id) ? { ...c, status: body.status, lastUsed: '刚刚' } : c,
    );
    return withDelay({ updated: body.ids.length });
  }

  if (path === '/api/admin/notifications/channels' && method === 'POST') {
    const body = (opts.body ?? {}) as CreateChannelVars;
    const next: NotificationChannel = {
      id: uid('ch'),
      name: body.name,
      kind: body.kind,
      status: 'draft',
      target: body.target,
      description: body.description ?? '由管理员手动创建',
      lastUsed: '从未',
      successRate: 0,
      sentToday: 0,
      config: defaultChannelConfig(body.kind, body.config),
      starred: false,
      scope: [],
      template: defaultChannelTemplate(body.kind),
    };
    state.channels = [next, ...state.channels];
    return withDelay({ ...next });
  }

  if (path === '/api/admin/notifications/groups' && method === 'POST') {
    const body = (opts.body ?? {}) as CreateGroupVars;
    const next: NotificationGroup = {
      id: uid('gp'),
      name: body.name,
      description: body.description ?? '由管理员手动创建',
      members: body.members,
      rules: 0,
    };
    state.groups = [next, ...state.groups];
    return withDelay({ ...next });
  }

  const detailMatch = /^\/api\/admin\/notifications\/channels\/([^/]+)$/.exec(path);
  if (detailMatch) {
    const id = detailMatch[1];
    if (method === 'PATCH') {
      const body = (opts.body ?? {}) as UpdateChannelVars;
      state.channels = state.channels.map((c) =>
        c.id === id ? { ...c, ...body.patch, lastUsed: '刚刚' } : c,
      );
      const next = state.channels.find((c) => c.id === id);
      if (!next) throw new Error('E_NOT_FOUND: 渠道不存在');
      return withDelay({ ...next });
    }
    if (method === 'DELETE') {
      const next = state.channels.find((c) => c.id === id);
      if (!next) throw new Error('E_NOT_FOUND: 渠道不存在');
      state.channels = state.channels.filter((c) => c.id !== id);
      return withDelay(null);
    }
  }

  return undefined;
}

/** 在 demo 模式下包裹默认 mockHandler,先试本地 notifications handler,再 fallback */
export function wrapMockHandlerWithAdminNotifications(
  fallback: (path: string, opts: any) => Promise<unknown>,
) {
  return async (path: string, opts: any) => {
    const local = await adminNotificationsMockHandler(path, opts);
    if (local !== undefined) return local;
    return fallback(path, opts);
  };
}