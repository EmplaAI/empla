/**
 * @empla/react - Webhook Hooks (PR #81)
 *
 * Token management + live event feed. Token values are never cached
 * beyond the one-time issuance response — tokens are stored server-side
 * in `Integration.oauth_config["webhook_token"]` and the list hook only
 * exposes existence + rotation state.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useEmplaApi } from '../provider';

export const webhookKeys = {
  all: ['webhooks'] as const,
  tokens: () => [...webhookKeys.all, 'tokens'] as const,
  events: (params?: Record<string, unknown>) => [...webhookKeys.all, 'events', params] as const,
};

export function useWebhookTokens(options?: { enabled?: boolean }) {
  const api = useEmplaApi();
  const { enabled = true } = options ?? {};
  return useQuery({
    queryKey: webhookKeys.tokens(),
    queryFn: () => api.listWebhookTokens(),
    enabled,
    staleTime: 30_000,
  });
}

export function useCreateWebhookToken() {
  const api = useEmplaApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { integrationId: string }) => api.createWebhookToken(vars),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: webhookKeys.tokens() });
    },
  });
}

export function useRotateWebhookToken() {
  const api = useEmplaApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { integrationId: string }) => api.rotateWebhookToken(vars),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: webhookKeys.tokens() });
    },
  });
}

export function useDeleteWebhookToken() {
  const api = useEmplaApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { integrationId: string }) => api.deleteWebhookToken(vars),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: webhookKeys.tokens() });
    },
  });
}

export function useWebhookEvents(options?: {
  page?: number;
  pageSize?: number;
  provider?: string;
  enabled?: boolean;
  autoRefresh?: boolean;
  interval?: number;
}) {
  const api = useEmplaApi();
  const {
    page = 1,
    pageSize = 50,
    provider,
    enabled = true,
    autoRefresh = true,
    interval = 15,
  } = options ?? {};
  return useQuery({
    queryKey: webhookKeys.events({ page, pageSize, provider }),
    queryFn: () => api.listWebhookEvents({ page, pageSize, provider }),
    enabled,
    staleTime: 10_000,
    refetchInterval: autoRefresh ? interval * 1000 : false,
  });
}
