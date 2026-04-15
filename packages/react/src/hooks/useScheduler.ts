/**
 * @empla/react - Scheduler Hooks (PR #82)
 *
 * Read/cancel/add scheduled actions. Mirrors the existing feature-hook
 * pattern (useWebhooks, useTools) with React Query key conventions.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useEmplaApi } from '../provider';

export const scheduleKeys = {
  all: ['schedule'] as const,
  forEmployee: (employeeId: string) => [...scheduleKeys.all, employeeId] as const,
};

export function useSchedule(
  employeeId: string,
  options?: { enabled?: boolean; autoRefresh?: boolean; interval?: number }
) {
  const api = useEmplaApi();
  const { enabled = true, autoRefresh = true, interval = 30 } = options ?? {};
  return useQuery({
    queryKey: scheduleKeys.forEmployee(employeeId),
    queryFn: () => api.listScheduledActions(employeeId),
    enabled: enabled && !!employeeId,
    staleTime: 15_000,
    refetchInterval: autoRefresh ? interval * 1000 : false,
  });
}

export function useCreateScheduledAction() {
  const api = useEmplaApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: {
      employeeId: string;
      description: string;
      scheduledFor: string;
      recurring: boolean;
      intervalHours?: number;
    }) => api.createScheduledAction(vars),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: scheduleKeys.forEmployee(vars.employeeId) });
    },
  });
}

export function useCancelScheduledAction() {
  const api = useEmplaApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { employeeId: string; actionId: string }) =>
      api.cancelScheduledAction(vars),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: scheduleKeys.forEmployee(vars.employeeId) });
    },
  });
}
