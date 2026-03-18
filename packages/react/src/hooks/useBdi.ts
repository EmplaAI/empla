/**
 * @empla/react - BDI Hooks
 *
 * React Query hooks for goals, intentions, and beliefs.
 */

import { useQuery } from '@tanstack/react-query';

import { useEmplaApi } from '../provider';
import type { Belief, EmployeeGoal, EmployeeIntention, PaginatedResponse } from '../types';

/**
 * Query keys for BDI state.
 */
export const bdiKeys = {
  all: ['bdi'] as const,
  goals: (employeeId: string, params?: Record<string, unknown>) =>
    [...bdiKeys.all, 'goals', employeeId, params] as const,
  intentions: (employeeId: string, params?: Record<string, unknown>) =>
    [...bdiKeys.all, 'intentions', employeeId, params] as const,
  beliefs: (employeeId: string, params?: Record<string, unknown>) =>
    [...bdiKeys.all, 'beliefs', employeeId, params] as const,
};

/**
 * Hook to list goals for an employee.
 */
export function useGoals(
  employeeId: string,
  options?: {
    page?: number;
    pageSize?: number;
    status?: string;
    enabled?: boolean;
    autoRefresh?: boolean;
    interval?: number;
  }
) {
  const api = useEmplaApi();
  const {
    page = 1,
    pageSize = 50,
    status,
    enabled = true,
    autoRefresh = false,
    interval = 30,
  } = options ?? {};

  return useQuery<PaginatedResponse<EmployeeGoal>>({
    queryKey: bdiKeys.goals(employeeId, { page, status }),
    queryFn: () => api.listGoals({ employeeId, page, pageSize, status }),
    enabled: enabled && !!employeeId,
    refetchInterval: autoRefresh ? interval * 1000 : false,
  });
}

/**
 * Hook to list intentions for an employee.
 */
export function useIntentions(
  employeeId: string,
  options?: {
    page?: number;
    pageSize?: number;
    status?: string;
    goalId?: string;
    enabled?: boolean;
    autoRefresh?: boolean;
    interval?: number;
  }
) {
  const api = useEmplaApi();
  const {
    page = 1,
    pageSize = 50,
    status,
    goalId,
    enabled = true,
    autoRefresh = false,
    interval = 30,
  } = options ?? {};

  return useQuery<PaginatedResponse<EmployeeIntention>>({
    queryKey: bdiKeys.intentions(employeeId, { page, status, goalId }),
    queryFn: () => api.listIntentions({ employeeId, page, pageSize, status, goalId }),
    enabled: enabled && !!employeeId,
    refetchInterval: autoRefresh ? interval * 1000 : false,
  });
}

/**
 * Hook to list beliefs for an employee.
 */
export function useBeliefs(
  employeeId: string,
  options?: {
    page?: number;
    pageSize?: number;
    beliefType?: string;
    minConfidence?: number;
    enabled?: boolean;
    autoRefresh?: boolean;
    interval?: number;
  }
) {
  const api = useEmplaApi();
  const {
    page = 1,
    pageSize = 50,
    beliefType,
    minConfidence,
    enabled = true,
    autoRefresh = false,
    interval = 30,
  } = options ?? {};

  return useQuery<PaginatedResponse<Belief>>({
    queryKey: bdiKeys.beliefs(employeeId, { page, beliefType, minConfidence }),
    queryFn: () => api.listBeliefs({ employeeId, page, pageSize, beliefType, minConfidence }),
    enabled: enabled && !!employeeId,
    refetchInterval: autoRefresh ? interval * 1000 : false,
  });
}
