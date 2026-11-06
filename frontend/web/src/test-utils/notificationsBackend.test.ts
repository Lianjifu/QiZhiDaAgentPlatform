/**
 * Sanity check — 测试专用的内存后端返回夹具数据 ✓；写操作在内存里往返 ✓。
 */
import { describe, expect, it } from 'vitest';
import { wrapMockHandlerWithAdminNotifications } from './notificationsBackend';

describe('notificationsBackend', () => {
  it('returns channel/webhook/group/event lists', async () => {
    const fallback = async () => undefined;
    const wrap = wrapMockHandlerWithAdminNotifications(fallback);
    expect((await wrap('/api/admin/notifications/channels', { method: 'GET' })) as Array<unknown>).toHaveLength(7);
    expect((await wrap('/api/admin/notifications/webhooks', { method: 'GET' })) as Array<unknown>).toHaveLength(3);
    expect((await wrap('/api/admin/notifications/groups', { method: 'GET' })) as Array<unknown>).toHaveLength(3);
    expect((await wrap('/api/admin/notifications/events', { method: 'GET' })) as Array<unknown>).toHaveLength(6);
  });

  it('creates a channel via POST and returns it', async () => {
    const fallback = async () => undefined;
    const wrap = wrapMockHandlerWithAdminNotifications(fallback);
    const before = (await wrap('/api/admin/notifications/channels', { method: 'GET' })) as Array<unknown>;
    const created = (await wrap('/api/admin/notifications/channels', {
      method: 'POST',
      body: { name: 'X', kind: 'feishu', target: '测试机器人', config: { appId: 'cli_x', appSecret: 's' } },
    })) as { id: string; name: string };
    expect(created.name).toBe('X');
    const after = (await wrap('/api/admin/notifications/channels', { method: 'GET' })) as Array<unknown>;
    expect(after.length).toBe(before.length + 1);
  });
});