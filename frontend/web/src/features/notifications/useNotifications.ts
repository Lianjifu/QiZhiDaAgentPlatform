/**
 * 管理侧「渠道配置」hooks — 飞书 / 企业微信 / 钉钉 / Web 对话渠道。
 * 以及 create/update/batch operations。
 * 端点 /api/admin/notifications/* 由 features/notifications/mock-handler.ts 接管
 * (全局 mock.ts ladder 未覆盖)。
 */
import { useApiQuery, useApiMutation } from '@/services/query';
import { qk } from '@/api/shared/query-keys';
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

const PATH = '/api/admin/notifications';

export function useNotificationChannels() {
  return useApiQuery<NotificationChannel[]>(
    [...qk.admin.notifications.root, 'channels'],
    `${PATH}/channels`,
    undefined,
    { staleTime: 30_000, placeholderData: (prev) => prev },
  );
}

export function useNotificationWebhooks() {
  return useApiQuery<WebhookEntry[]>(
    [...qk.admin.notifications.root, 'webhooks'],
    `${PATH}/webhooks`,
    undefined,
    { staleTime: 30_000 },
  );
}

export function useNotificationGroups() {
  return useApiQuery<NotificationGroup[]>(
    [...qk.admin.notifications.root, 'groups'],
    `${PATH}/groups`,
    undefined,
    { staleTime: 30_000, placeholderData: (prev) => prev },
  );
}

export function useDeliveryEvents() {
  return useApiQuery<DeliveryEvent[]>(
    [...qk.admin.notifications.root, 'events'],
    `${PATH}/events`,
    undefined,
    { staleTime: 15_000 },
  );
}

export function useCreateChannel() {
  return useApiMutation<NotificationChannel, CreateChannelVars>(
    () => `${PATH}/channels`,
    { invalidateKeys: [qk.admin.notifications.root] },
    'POST',
  );
}

export function useUpdateChannel() {
  return useApiMutation<NotificationChannel, UpdateChannelVars>(
    (vars) => `${PATH}/channels/${vars.id}`,
    { invalidateKeys: [qk.admin.notifications.root] },
    'PATCH',
  );
}

export function useBatchChannelStatus() {
  return useApiMutation<{ updated: number }, BatchStatusVars>(
    () => `${PATH}/channels/__batch__`,
    { invalidateKeys: [qk.admin.notifications.root] },
    'POST',
  );
}

export function useCreateGroup() {
  return useApiMutation<NotificationGroup, CreateGroupVars>(
    () => `${PATH}/groups`,
    { invalidateKeys: [qk.admin.notifications.root] },
    'POST',
  );
}

export function useDeleteChannel() {
  return useApiMutation<void, { id: string }>(
    (vars) => `${PATH}/channels/${vars.id}`,
    { invalidateKeys: [qk.admin.notifications.root] },
    'DELETE',
  );
}