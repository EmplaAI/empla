/**
 * @empla/react - Integration Hooks
 *
 * React Query hooks for the integration/connect flow.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useEmplaApi } from '../provider';
import type { ConnectRequest } from '../types';

export const integrationKeys = {
  all: ['integrations'] as const,
  providers: () => [...integrationKeys.all, 'providers'] as const,
  credentials: () => [...integrationKeys.all, 'credentials'] as const,
};

/**
 * List available providers from the catalog.
 */
export function useProviders() {
  const api = useEmplaApi();
  return useQuery({
    queryKey: integrationKeys.providers(),
    queryFn: () => api.listProviders(),
    staleTime: 5 * 60 * 1000, // Provider catalog rarely changes
  });
}

/**
 * List all credentials for the current tenant.
 */
export function useCredentials() {
  const api = useEmplaApi();
  return useQuery({
    queryKey: integrationKeys.credentials(),
    queryFn: () => api.listCredentials(),
  });
}

/**
 * Start the OAuth connect flow.
 * On success, redirects the browser to the authorization URL.
 */
export function useConnectProvider() {
  const api = useEmplaApi();
  return useMutation({
    mutationFn: (data: ConnectRequest) => api.connectProvider(data),
    onSuccess: (response) => {
      const url = response.authorizationUrl;
      if (!url) {
        throw new Error('Server returned empty authorization URL');
      }
      let parsed: URL;
      try {
        parsed = new URL(url);
      } catch {
        throw new Error(`Server returned malformed authorization URL: ${url}`);
      }
      if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
        throw new Error('Server returned unsafe authorization URL');
      }
      window.location.href = url;
    },
  });
}

/**
 * Revoke an integration credential.
 */
export function useRevokeCredential() {
  const api = useEmplaApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ integrationId, employeeId }: { integrationId: string; employeeId: string }) =>
      api.revokeCredential(integrationId, employeeId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: integrationKeys.credentials() });
      queryClient.invalidateQueries({ queryKey: integrationKeys.providers() });
    },
  });
}
