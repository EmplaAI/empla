/**
 * @empla/react - Inbox Hooks
 *
 * React Query hooks for the employee → human inbox. Polling-based
 * (the Phase 5 plan defers SSE/WebSocket to a later phase) — the
 * ``unread_count`` shortcut in the list response lets the sidebar
 * badge piggyback on the same request rather than running its own.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useEmplaApi } from '../provider';
import type { InboxListResponse, InboxMessage, InboxPriority } from '../types';

export const inboxKeys = {
  all: ['inbox'] as const,
  lists: () => [...inboxKeys.all, 'list'] as const,
  list: (params?: {
    unreadOnly?: boolean;
    priority?: InboxPriority;
    page?: number;
    pageSize?: number;
  }) => [...inboxKeys.lists(), params] as const,
};

/**
 * List inbox messages. Defaults refetch every 30s so a dashboard tab
 * left open on the inbox sees new urgent messages (e.g., a cost hard-
 * stop firing) within one polling window. Caller can override via
 * ``options.refetchInterval`` or disable polling with ``false``.
 */
export function useInbox(
  params?: {
    unreadOnly?: boolean;
    priority?: InboxPriority;
    page?: number;
    pageSize?: number;
  },
  options?: { refetchInterval?: number | false; enabled?: boolean },
) {
  const api = useEmplaApi();
  return useQuery<InboxListResponse>({
    queryKey: inboxKeys.list(params),
    queryFn: () => api.listInbox(params),
    refetchInterval: options?.refetchInterval ?? 30_000,
    enabled: options?.enabled ?? true,
  });
}

/**
 * Tenant-wide unread count for the sidebar badge. Seeds from any
 * cached inbox list response (the API always returns ``unreadCount``
 * tenant-wide regardless of list filters, so any cached list in the
 * client is authoritative for seeding). When no list fetch has
 * happened yet — e.g., sidebar mounts before the inbox route opens —
 * falls back to a minimal network request with ``pageSize=1`` so we
 * get ``unreadCount`` without pulling a large page.
 *
 * Refetch cadence matches ``useInbox`` (30s) so the badge never lags
 * behind a list view the user is actively staring at.
 */
export function useInboxUnreadCount() {
  const api = useEmplaApi();
  const qc = useQueryClient();
  return useQuery<number>({
    queryKey: [...inboxKeys.all, 'unread-count'],
    queryFn: async () => {
      // Piggyback on any cached list first. Avoids a duplicate network
      // request when the inbox page is open (useInbox already fetched).
      const cached = qc.getQueriesData<InboxListResponse>({
        queryKey: inboxKeys.lists(),
      });
      for (const [, data] of cached) {
        if (data && typeof data.unreadCount === 'number') {
          return data.unreadCount;
        }
      }
      const r = await api.listInbox({ pageSize: 1 });
      return r.unreadCount;
    },
    refetchInterval: 30_000,
  });
}

/** Mark a message as read. Idempotent. Invalidates the inbox list
 * queries so the badge updates without a manual refetch. */
export function useMarkInboxRead() {
  const api = useEmplaApi();
  const qc = useQueryClient();
  return useMutation<InboxMessage, Error, string>({
    mutationFn: (messageId: string) => api.markInboxRead(messageId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: inboxKeys.all });
    },
  });
}

/** Soft-delete a message. Idempotent 204. */
export function useDeleteInboxMessage() {
  const api = useEmplaApi();
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (messageId: string) => api.deleteInboxMessage(messageId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: inboxKeys.all });
    },
  });
}
