/**
 * @empla/react - Tenant Settings Hooks (PR #83)
 *
 * Read + write the tenant settings document. A successful update invalidates
 * the cache so the dashboard picks up the new `version` number and any
 * server-side migration/normalisation.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useEmplaApi } from '../provider';
import type { TenantSettingsUpdate } from '../types';

export const settingsKeys = {
  all: ['settings'] as const,
  tenant: () => [...settingsKeys.all, 'tenant'] as const,
};

export function useSettings(options?: { enabled?: boolean }) {
  const api = useEmplaApi();
  const { enabled = true } = options ?? {};
  return useQuery({
    queryKey: settingsKeys.tenant(),
    queryFn: () => api.getSettings(),
    enabled,
    staleTime: 60_000,
  });
}

export function useUpdateSettings() {
  const api = useEmplaApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: TenantSettingsUpdate) => api.updateSettings(body),
    onSuccess: (data) => {
      // Prime the cache with the freshly-returned settings so the UI
      // doesn't flash to an older version during the refetch.
      qc.setQueryData(settingsKeys.tenant(), data.settings);
      qc.invalidateQueries({ queryKey: settingsKeys.tenant() });
    },
  });
}
