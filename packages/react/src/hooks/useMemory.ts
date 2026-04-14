/**
 * @empla/react - Memory Hooks
 *
 * React Query hooks for episodic, semantic, procedural, and working memory.
 */

import { useQuery } from '@tanstack/react-query';

import { useEmplaApi } from '../provider';

export const memoryKeys = {
  all: ['memory'] as const,
  episodic: (employeeId: string, params?: Record<string, unknown>) =>
    [...memoryKeys.all, 'episodic', employeeId, params] as const,
  semantic: (employeeId: string, params?: Record<string, unknown>) =>
    [...memoryKeys.all, 'semantic', employeeId, params] as const,
  procedural: (employeeId: string, params?: Record<string, unknown>) =>
    [...memoryKeys.all, 'procedural', employeeId, params] as const,
  working: (employeeId: string, params?: Record<string, unknown>) =>
    [...memoryKeys.all, 'working', employeeId, params] as const,
};

/**
 * Paginated episodic memory for an employee, newest first.
 */
export function useEpisodicMemory(
  employeeId: string,
  options?: {
    page?: number;
    pageSize?: number;
    episodeType?: string;
    minImportance?: number;
    enabled?: boolean;
  }
) {
  const api = useEmplaApi();
  const { page = 1, pageSize = 50, episodeType, minImportance, enabled = true } = options ?? {};

  return useQuery({
    queryKey: memoryKeys.episodic(employeeId, { page, pageSize, episodeType, minImportance }),
    queryFn: () =>
      api.listEpisodicMemory({ employeeId, page, pageSize, episodeType, minImportance }),
    enabled: enabled && !!employeeId,
  });
}

/**
 * Paginated semantic (subject-predicate-object) facts for an employee.
 */
export function useSemanticMemory(
  employeeId: string,
  options?: {
    page?: number;
    pageSize?: number;
    factType?: string;
    subject?: string;
    predicate?: string;
    minConfidence?: number;
    enabled?: boolean;
  }
) {
  const api = useEmplaApi();
  const {
    page = 1,
    pageSize = 50,
    factType,
    subject,
    predicate,
    minConfidence,
    enabled = true,
  } = options ?? {};

  return useQuery({
    queryKey: memoryKeys.semantic(employeeId, {
      page,
      pageSize,
      factType,
      subject,
      predicate,
      minConfidence,
    }),
    queryFn: () =>
      api.listSemanticMemory({
        employeeId,
        page,
        pageSize,
        factType,
        subject,
        predicate,
        minConfidence,
      }),
    enabled: enabled && !!employeeId,
  });
}

/**
 * Paginated procedural memory (skills, workflows, playbooks) for an employee.
 */
export function useProceduralMemory(
  employeeId: string,
  options?: {
    page?: number;
    pageSize?: number;
    procedureType?: string;
    minSuccessRate?: number;
    isPlaybook?: boolean;
    enabled?: boolean;
  }
) {
  const api = useEmplaApi();
  const {
    page = 1,
    pageSize = 50,
    procedureType,
    minSuccessRate,
    isPlaybook,
    enabled = true,
  } = options ?? {};

  return useQuery({
    queryKey: memoryKeys.procedural(employeeId, {
      page,
      pageSize,
      procedureType,
      minSuccessRate,
      isPlaybook,
    }),
    queryFn: () =>
      api.listProceduralMemory({
        employeeId,
        page,
        pageSize,
        procedureType,
        minSuccessRate,
        isPlaybook,
      }),
    enabled: enabled && !!employeeId,
  });
}

/**
 * Current working-memory items for an employee (no pagination).
 */
export function useWorkingMemory(
  employeeId: string,
  options?: {
    itemType?: string;
    enabled?: boolean;
    autoRefresh?: boolean;
    interval?: number;
  }
) {
  const api = useEmplaApi();
  const { itemType, enabled = true, autoRefresh = false, interval = 30 } = options ?? {};

  return useQuery({
    queryKey: memoryKeys.working(employeeId, { itemType }),
    queryFn: () => api.listWorkingMemory({ employeeId, itemType }),
    enabled: enabled && !!employeeId,
    refetchInterval: autoRefresh ? interval * 1000 : false,
  });
}
