/**
 * @empla/react - Playbook Hooks
 *
 * React Query hooks for playbook list and stats.
 */

import { useQuery } from '@tanstack/react-query';

import { useEmplaApi } from '../provider';

export const playbookKeys = {
  all: ['playbooks'] as const,
  list: (employeeId: string, params?: Record<string, unknown>) =>
    [...playbookKeys.all, 'list', employeeId, params] as const,
  stats: (employeeId: string) =>
    [...playbookKeys.all, 'stats', employeeId] as const,
};

/**
 * Hook to list playbooks for an employee.
 */
export function usePlaybooks(
  employeeId: string,
  options?: {
    minSuccessRate?: number;
    learnedFrom?: string;
    sortBy?: string;
    limit?: number;
    enabled?: boolean;
  }
) {
  const api = useEmplaApi();
  const { minSuccessRate, learnedFrom, sortBy, limit, enabled = true } = options ?? {};

  return useQuery({
    queryKey: playbookKeys.list(employeeId, { minSuccessRate, learnedFrom, sortBy, limit }),
    queryFn: () =>
      api.listPlaybooks({ employeeId, minSuccessRate, learnedFrom, sortBy, limit }),
    enabled: enabled && !!employeeId,
  });
}

/**
 * Hook to get playbook stats for an employee.
 */
export function usePlaybookStats(
  employeeId: string,
  options?: {
    enabled?: boolean;
    autoRefresh?: boolean;
    interval?: number;
  }
) {
  const api = useEmplaApi();
  const { enabled = true, autoRefresh = false, interval = 60 } = options ?? {};

  return useQuery({
    queryKey: playbookKeys.stats(employeeId),
    queryFn: () => api.getPlaybookStats({ employeeId }),
    enabled: enabled && !!employeeId,
    refetchInterval: autoRefresh ? interval * 1000 : false,
  });
}
