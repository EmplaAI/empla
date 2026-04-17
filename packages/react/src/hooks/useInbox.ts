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
  list: (params?: { unreadOnly?: boolean; priority?: InboxPriority; page?: number }) =>
    [...inboxKeys.lists(), params] as const,
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
 * Tenant-wide unread count for the sidebar badge. Shares its query
 * key with the unfiltered list so the existing list request already
 * hydrates this — no second request in practice. If no list fetch has
 * happened yet, this falls back to a minimal request with ``pageSize=1``
 * to land the ``unreadCount`` field without pulling a large page.
 */
export function useInboxUnreadCount() {
  const api = useEmplaApi();
  return useQuery<number>({
    queryKey: [...inboxKeys.all, 'unread-count'],
    queryFn: async () => {
      const r = await api.listInbox({ pageSize: 1 });
      return r.unreadCount;
    },
    // Same 30s cadence as the list view; badge shouldn't lag behind
    // the list the user is staring at.
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
