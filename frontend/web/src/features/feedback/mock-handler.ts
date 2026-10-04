/**
 * AdminFeedback — 用户反馈的本地 mock wrap。
 * 演示模式下, 走 useApiQuery('/api/admin/feedback/{list|tickets|topics|rules}') 时由本 handler 兜底。
 */
import { mockFeedbackList, mockFeedbackRules, mockFeedbackTickets, mockFeedbackTopics } from './fixtures';

type Handler<F> = (path: string, opts: any) => Promise<unknown> | unknown;

export function wrapMockHandlerWithAdminFeedback<F extends Handler<F>>(fallback: F): F {
  const wrapped = (async (path: string, opts: any) => {
    if (path === '/api/admin/feedback/list' && (!opts?.method || opts.method === 'GET')) {
      return mockFeedbackList;
    }
    if (path === '/api/admin/feedback/tickets' && opts?.method === 'POST') {
      const body = (opts.body ?? {}) as Record<string, unknown>;
      return {
        id: `tk-${Date.now()}`,
        title: body.title || '未命名工单',
        feedbackIds: body.feedbackIds || [],
        owner: body.owner || '产品组',
        priority: body.priority || 'medium',
        status: 'triaged',
        topic: body.topic || '其他',
        description: body.description || '由管理员手动创建',
        createdAt: '刚刚',
        dueAt: body.dueAt || '本周内',
      };
    }
    if (path === '/api/admin/feedback/rules' && opts?.method === 'POST') {
      const body = (opts.body ?? {}) as Record<string, unknown>;
      return {
        id: `rl-${Date.now()}`,
        name: body.name || '未命名规则',
        matchTopic: body.matchTopic || '',
        matchSentiment: body.matchSentiment || 'all',
        action: body.action || 'create-ticket',
        target: body.target || '产品组',
        enabled: true,
        description: body.description || '由管理员手动创建',
      };
    }
    if (path === '/api/admin/feedback/topics' && (!opts?.method || opts.method === 'GET')) {
      return mockFeedbackTopics;
    }
    if (path === '/api/admin/feedback/rules' && (!opts?.method || opts.method === 'GET')) {
      return mockFeedbackRules;
    }
    return fallback(path, opts);
  }) as F;
  return wrapped;
}