/**
 * @empla/react - LLM Cost Hooks
 *
 * React Query hooks for LLM cost summary and history.
 */

import { useQuery } from '@tanstack/react-query';

import { useEmplaApi } from '../provider';

export const costKeys = {
  all: ['costs'] as const,
  summary: (employeeId: string, hours?: number) =>
    [...costKeys.all, 'summary', employeeId, hours] as const,
  history: (employeeId: string, hours?: number) =>
    [...costKeys.all, 'history', employeeId, hours] as const,
};

/**
 * Hook to get LLM cost summary for an employee.
 */
export function useCostSummary(
  employeeId: string,
  options?: {
    hours?: number;
    enabled?: boolean;
    autoRefresh?: boolean;
    interval?: number;
  }
) {
  const api = useEmplaApi();
  const { hours = 24, enabled = true, autoRefresh = false, interval = 60 } = options ?? {};

  return useQuery({
    queryKey: costKeys.summary(employeeId, hours),
    queryFn: () => api.getCostSummary({ employeeId, hours }),
    enabled: enabled && !!employeeId,
    refetchInterval: autoRefresh ? interval * 1000 : false,
  });
}

/**
 * Hook to get LLM cost history for an employee.
 */
export function useCostHistory(
  employeeId: string,
  options?: {
    hours?: number;
    enabled?: boolean;
  }
) {
  const api = useEmplaApi();
  const { hours = 24, enabled = true } = options ?? {};

  return useQuery({
    queryKey: costKeys.history(employeeId, hours),
    queryFn: () => api.getCostHistory({ employeeId, hours }),
    enabled: enabled && !!employeeId,
  });
}
