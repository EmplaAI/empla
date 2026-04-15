/**
 * @empla/react - Playbook Hooks
 *
 * React Query hooks for playbook list, stats, and editor mutations (PR #84).
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

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

// ---------------------------------------------------------------------------
// Editor mutations (PR #84)
// ---------------------------------------------------------------------------

function _invalidateEmployee(qc: ReturnType<typeof useQueryClient>, employeeId: string) {
  // Invalidate every list query for this employee (filters vary). Stats too.
  qc.invalidateQueries({
    predicate: (q) =>
      q.queryKey[0] === 'playbooks' &&
      q.queryKey[1] === 'list' &&
      q.queryKey[2] === employeeId,
  });
  qc.invalidateQueries({ queryKey: playbookKeys.stats(employeeId) });
}

export function useCreatePlaybook(employeeId: string) {
  const api = useEmplaApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: {
      name: string;
      description: string;
      steps: Array<{ description: string } & Record<string, unknown>>;
      triggerConditions?: Record<string, unknown>;
      enabled?: boolean;
    }) => api.createPlaybook({ employeeId, ...vars }),
    onSuccess: () => _invalidateEmployee(qc, employeeId),
  });
}

export function useUpdatePlaybook(employeeId: string) {
  const api = useEmplaApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: {
      playbookId: string;
      expectedVersion: number;
      name?: string;
      description?: string;
      steps?: Array<{ description: string } & Record<string, unknown>>;
      triggerConditions?: Record<string, unknown>;
      enabled?: boolean;
    }) => api.updatePlaybook({ employeeId, ...vars }),
    onSuccess: () => _invalidateEmployee(qc, employeeId),
  });
}

export function useTogglePlaybook(employeeId: string) {
  const api = useEmplaApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { playbookId: string; enabled: boolean }) =>
      api.togglePlaybook({ employeeId, ...vars }),
    onSuccess: () => _invalidateEmployee(qc, employeeId),
  });
}

export function useDeletePlaybook(employeeId: string) {
  const api = useEmplaApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { playbookId: string }) =>
      api.deletePlaybook({ employeeId, ...vars }),
    onSuccess: () => _invalidateEmployee(qc, employeeId),
  });
}
