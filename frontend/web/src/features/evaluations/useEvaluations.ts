import { useApiQuery, useApiMutation } from '@/services/query';
import { qk } from '@/api/shared/query-keys';
import type { EvalResult, EvalSuite, EvalSuiteStats } from './schema';

export function useEvalSuites() {
  return useApiQuery<EvalSuite[]>(
    [...qk.admin.evaluations.list],
    '/api/admin/evaluations/suites',
    undefined,
    { staleTime: 60_000 },
  );
}

export function useEvalResults() {
  return useApiQuery<EvalResult[]>(
    [...qk.admin.evaluations.results],
    '/api/admin/evaluations/results',
    undefined,
    { staleTime: 60_000 },
  );
}

export function useCreateEvalSuite() {
  return useApiMutation<EvalSuite, Partial<EvalSuite>>(
    () => '/api/admin/evaluations/suites',
    { invalidateKeys: [qk.admin.evaluations.list] },
    'POST',
  );
}

export function useEvalSuiteStats(suites: EvalSuite[]): EvalSuiteStats {
  const total = suites.length;
  const passed = suites.filter((s) => s.status === 'passed').length;
  const failed = suites.filter((s) => s.status === 'failed').length;
  const running = suites.filter((s) => s.status === 'running').length;
  const queued = suites.filter((s) => s.status === 'queued').length;
  const countable = suites.filter((s) => s.status !== 'cancelled' && s.cases > 0);
  const avgPassRate = countable.length === 0
    ? 0
    : countable.reduce((sum, s) => sum + s.passRate, 0) / countable.length;
  return { total, passed, failed, running, queued, avgPassRate };
}
