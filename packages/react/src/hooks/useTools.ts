/**
 * @empla/react - Tool Catalog Hooks
 *
 * Read-only hooks for the per-employee tool catalog and trust-boundary
 * blocks. The API proxies to the runner subprocess, so 503 means the
 * employee is not running — handle that as an "offline" state, not an
 * error.
 */

import { useQuery } from '@tanstack/react-query';

import { useEmplaApi } from '../provider';

export const toolKeys = {
  all: ['tools'] as const,
  list: (employeeId: string) => [...toolKeys.all, 'list', employeeId] as const,
  health: (employeeId: string, toolName: string) =>
    [...toolKeys.all, 'health', employeeId, toolName] as const,
  blocked: (employeeId: string) => [...toolKeys.all, 'blocked', employeeId] as const,
};

/** List the tools an employee can call. */
export function useTools(
  employeeId: string,
  options?: { enabled?: boolean; autoRefresh?: boolean; interval?: number }
) {
  const api = useEmplaApi();
  const { enabled = true, autoRefresh = false, interval = 60 } = options ?? {};

  return useQuery({
    queryKey: toolKeys.list(employeeId),
    queryFn: () => api.listTools({ employeeId }),
    enabled: enabled && !!employeeId,
    staleTime: 30_000,
    refetchInterval: autoRefresh ? interval * 1000 : false,
    // 503 from the proxy means "runner offline" — don't retry, the dashboard
    // shows the offline state until the user starts the employee.
    retry: false,
  });
}

/** Per-integration health for the integration that owns *toolName*. */
export function useToolHealth(
  employeeId: string,
  toolName: string,
  options?: { enabled?: boolean }
) {
  const api = useEmplaApi();
  const { enabled = true } = options ?? {};

  return useQuery({
    queryKey: toolKeys.health(employeeId, toolName),
    queryFn: () => api.getToolHealth({ employeeId, toolName }),
    enabled: enabled && !!employeeId && !!toolName,
    staleTime: 15_000,
    retry: false,
  });
}

/** Trust-boundary blocks observed in the runner's current cycle. */
export function useBlockedTools(
  employeeId: string,
  options?: { enabled?: boolean; autoRefresh?: boolean; interval?: number }
) {
  const api = useEmplaApi();
  const { enabled = true, autoRefresh = false, interval = 30 } = options ?? {};

  return useQuery({
    queryKey: toolKeys.blocked(employeeId),
    queryFn: () => api.listBlockedTools({ employeeId }),
    enabled: enabled && !!employeeId,
    staleTime: 10_000,
    refetchInterval: autoRefresh ? interval * 1000 : false,
    retry: false,
  });
}
