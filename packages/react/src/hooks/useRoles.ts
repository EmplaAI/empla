/**
 * @empla/react - Role Hooks
 *
 * React Query hook for fetching pre-defined employee roles from the catalog.
 */

import { useQuery } from '@tanstack/react-query';

import { useEmplaApi } from '../provider';
import type { RoleDefinition } from '../types';

/**
 * Query keys for roles.
 */
export const roleKeys = {
  all: ['roles'] as const,
};

/**
 * Fetch all pre-defined employee roles from the catalog API.
 *
 * Roles are static at runtime so the data is cached indefinitely.
 *
 * @example
 * ```tsx
 * const { data } = useRoles();
 * data?.roles.map(role => <option key={role.code}>{role.title}</option>)
 * ```
 */
export function useRoles() {
  const api = useEmplaApi();
  return useQuery<{ roles: RoleDefinition[] }>({
    queryKey: roleKeys.all,
    queryFn: () => api.listRoles(),
    staleTime: Infinity,
  });
}
