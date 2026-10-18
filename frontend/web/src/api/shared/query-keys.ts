/**
 * 集中 query key 命名空间 — 按 侧 / 模块 / 操作 三段式。
 * 任何失效规则都必须用这些 key,避免散落的 `['skill', 'list']` 拼写差异。
 */
export const qk = {
  user: {
    skills: {
      root: ['user', 'skills'] as const,
      list: ['user', 'skills', 'list'] as const,
      detail: (id: string) => ['user', 'skills', 'detail', id] as const,
      recent: ['user', 'skills', 'recent'] as const,
    },
    home: {
      root: ['user', 'home'] as const,
    },
    agents: {
      root: ['user', 'agents'] as const,
      list: ['user', 'agents', 'list'] as const,
      detail: (id: string) => ['user', 'agents', 'detail', id] as const,
    },
    knowledge: {
      root: ['user', 'knowledge'] as const,
      list: ['user', 'knowledge', 'list'] as const,
      detail: (id: string) => ['user', 'knowledge', 'detail', id] as const,
      favorites: ['user', 'knowledge', 'favorites'] as const,
      history: ['user', 'knowledge', 'history'] as const,
    },
    tasks: {
      root: ['user', 'tasks'] as const,
      list: ['user', 'tasks', 'list'] as const,
      detail: (id: string) => ['user', 'tasks', 'detail', id] as const,
    },
    automations: {
      root: ['user', 'automations'] as const,
      list: ['user', 'automations', 'list'] as const,
      detail: (id: string) => ['user', 'automations', 'detail', id] as const,
      runs: ['user', 'automations', 'runs'] as const,
    },
    team: {
      root: ['user', 'team'] as const,
      members: ['user', 'team', 'members'] as const,
      shared: ['user', 'team', 'shared'] as const,
    },
    copilot: {
      root: ['user', 'copilot'] as const,
      sessions: ['user', 'copilot', 'sessions'] as const,
    },
  },
  admin: {
    overview: {
      root: ['admin', 'overview'] as const,
      summary: ['admin', 'overview', 'summary'] as const,
      trend: (range: string) => ['admin', 'overview', 'trend', range] as const,
      alerts: ['admin', 'overview', 'alerts'] as const,
    },
    skills: {
      root: ['admin', 'skills'] as const,
      list: ['admin', 'skills', 'list'] as const,
      detail: (id: string) => ['admin', 'skills', 'detail', id] as const,
    },
    agents: {
      root: ['admin', 'agents'] as const,
      list: ['admin', 'agents', 'list'] as const,
      detail: (id: string) => ['admin', 'agents', 'detail', id] as const,
      versions: (id: string) => ['admin', 'agents', 'versions', id] as const,
      evaluations: (id: string) => ['admin', 'agents', 'evaluations', id] as const,
    },
    knowledge: {
      root: ['admin', 'knowledge'] as const,
    },
    workflows: {
      root: ['admin', 'workflows'] as const,
      list: ['admin', 'workflows', 'list'] as const,
    },
    evaluations: {
      root: ['admin', 'evaluations'] as const,
      list: ['admin', 'evaluations', 'suites', 'list'] as const,
      results: ['admin', 'evaluations', 'results', 'list'] as const,
    },
    regressions: {
      root: ['admin', 'regressions'] as const,
      list: ['admin', 'regressions', 'tracks', 'list'] as const,
      alerts: ['admin', 'regressions', 'alerts', 'list'] as const,
      timeline: ['admin', 'regressions', 'timeline', 'list'] as const,
    },
    feedback: {
      root: ['admin', 'feedback'] as const,
      list: ['admin', 'feedback', 'list'] as const,
      tickets: ['admin', 'feedback', 'tickets', 'list'] as const,
      topics: ['admin', 'feedback', 'topics', 'list'] as const,
      rules: ['admin', 'feedback', 'rules', 'list'] as const,
    },
    models: {
      root: ['admin', 'models'] as const,
      list: ['admin', 'models', 'list'] as const,
      providers: ['admin', 'models', 'providers'] as const,
      routes: ['admin', 'models', 'routes'] as const,
      health: ['admin', 'models', 'health'] as const,
      detail: (id: string) => ['admin', 'models', 'detail', id] as const,
    },
    quotas: {
      root: ['admin', 'quotas'] as const,
    },
    notifications: {
      root: ['admin', 'notifications'] as const,
    },
    operations: {
      root: ['admin', 'operations'] as const,
      summary: ['admin', 'operations', 'summary'] as const,
      sessions: ['admin', 'operations', 'sessions'] as const,
      spans: ['admin', 'operations', 'spans'] as const,
      incidents: ['admin', 'operations', 'incidents'] as const,
      kindStats: ['admin', 'operations', 'kind-stats'] as const,
    },
    audit: {
      root: ['admin', 'audit'] as const,
      entries: ['admin', 'audit', 'entries'] as const,
      risks: ['admin', 'audit', 'risks'] as const,
      rules: ['admin', 'audit', 'rules'] as const,
      scopes: ['admin', 'audit', 'scopes'] as const,
    },
    metrics: {
      root: ['admin', 'metrics'] as const,
      models: ['admin', 'metrics', 'models'] as const,
      latency: ['admin', 'metrics', 'latency'] as const,
      costBreakdown: ['admin', 'metrics', 'cost-breakdown'] as const,
      dashboards: ['admin', 'metrics', 'dashboards'] as const,
      thresholds: ['admin', 'metrics', 'thresholds'] as const,
    },
    memory: {
      root: ['admin', 'memory'] as const,
      l1: ['admin', 'memory', 'l1'] as const,
      l2: ['admin', 'memory', 'l2'] as const,
      l3: ['admin', 'memory', 'l3'] as const,
      l1Detail: (id: string) => ['admin', 'memory', 'l1', 'detail', id] as const,
      l2Detail: (id: string) => ['admin', 'memory', 'l2', 'detail', id] as const,
      l3Detail: (id: string) => ['admin', 'memory', 'l3', 'detail', id] as const,
      promotions: ['admin', 'memory', 'promotions'] as const,
      policies: ['admin', 'memory', 'policies'] as const,
      trend: (range: string) => ['admin', 'memory', 'trend', range] as const,
    },
  },
} as const;