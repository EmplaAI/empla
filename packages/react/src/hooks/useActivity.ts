/**
 * @empla/react - Activity Hooks
 *
 * React Query hooks for activity feed data.
 */

import { useQuery } from '@tanstack/react-query';

import { useEmplaApi } from '../provider';
import type { Activity, ActivitySummary, PaginatedResponse } from '../types';

/**
 * Query keys for activities.
 */
export const activityKeys = {
  all: ['activities'] as const,
  lists: () => [...activityKeys.all, 'list'] as const,
  list: (params?: { employeeId?: string; page?: number; eventType?: string }) =>
    [...activityKeys.lists(), params] as const,
  recent: (employeeId: string, limit?: number) =>
    [...activityKeys.all, 'recent', employeeId, limit] as const,
  summaries: () => [...activityKeys.all, 'summary'] as const,
  summary: (params?: { employeeId?: string; hours?: number }) =>
    [...activityKeys.summaries(), params] as const,
};

/**
 * Options for useActivity hook.
 */
export interface UseActivityOptions {
  /** Filter by employee ID */
  employeeId?: string;

  /** Page number (1-indexed) */
  page?: number;

  /** Items per page */
  pageSize?: number;

  /** Filter by event type */
  eventType?: string;

  /** Minimum importance score (0-1) */
  minImportance?: number;

  /** Only activities after this date */
  since?: string;

  /** Enable auto-refresh */
  autoRefresh?: boolean;

  /** Auto-refresh interval in seconds (default: 30) */
  interval?: number;

  /** Enable the query */
  enabled?: boolean;
}

/**
 * Hook to list activities with optional filtering and auto-refresh.
 *
 * @example
 * ```tsx
 * function ActivityFeed({ employeeId }: { employeeId?: string }) {
 *   const { data, isLoading, refetch } = useActivity({
 *     employeeId,
 *     autoRefresh: true,
 *     interval: 30,
 *   });
 *
 *   return (
 *     <div>
 *       <button onClick={() => refetch()}>Refresh</button>
 *       {data?.items.map(activity => (
 *         <ActivityItem key={activity.id} activity={activity} />
 *       ))}
 *     </div>
 *   );
 * }
 * ```
 */
export function useActivity(options: UseActivityOptions = {}) {
  const api = useEmplaApi();
  const {
    employeeId,
    page = 1,
    pageSize = 50,
    eventType,
    minImportance,
    since,
    autoRefresh = false,
    interval = 30,
    enabled = true,
  } = options;

  return useQuery<PaginatedResponse<Activity>>({
    queryKey: activityKeys.list({ employeeId, page, eventType }),
    queryFn: () =>
      api.listActivities({
        employeeId,
        page,
        pageSize,
        eventType,
        minImportance,
        since,
      }),
    enabled,
    refetchInterval: autoRefresh ? interval * 1000 : false,
  });
}

/**
 * Hook to get recent activities for an employee.
 *
 * Convenience hook for the common case of showing recent activity.
 *
 * @example
 * ```tsx
 * function RecentActivity({ employeeId }: { employeeId: string }) {
 *   const { data: activities } = useRecentActivity(employeeId, 10);
 *
 *   return (
 *     <ul>
 *       {activities?.map(a => <li key={a.id}>{a.description}</li>)}
 *     </ul>
 *   );
 * }
 * ```
 */
export function useRecentActivity(
  employeeId: string,
  limit: number = 20,
  options?: {
    enabled?: boolean;
    autoRefresh?: boolean;
    interval?: number;
  }
) {
  const api = useEmplaApi();
  const { enabled = true, autoRefresh = false, interval = 30 } = options ?? {};

  return useQuery<Activity[]>({
    queryKey: activityKeys.recent(employeeId, limit),
    queryFn: () => api.getRecentActivities(employeeId, limit),
    enabled: enabled && !!employeeId,
    refetchInterval: autoRefresh ? interval * 1000 : false,
  });
}

/**
 * Hook to get activity summary (counts by event type).
 *
 * @example
 * ```tsx
 * function ActivityStats() {
 *   const { data: summary } = useActivitySummary({ hours: 24 });
 *
 *   return (
 *     <div>
 *       <span>Total: {summary?.total}</span>
 *       <span>Emails: {summary?.eventCounts.email_sent || 0}</span>
 *     </div>
 *   );
 * }
 * ```
 */
export function useActivitySummary(options?: {
  employeeId?: string;
  hours?: number;
  enabled?: boolean;
}) {
  const api = useEmplaApi();
  const { employeeId, hours = 24, enabled = true } = options ?? {};

  return useQuery<ActivitySummary>({
    queryKey: activityKeys.summary({ employeeId, hours }),
    queryFn: () => api.getActivitySummary({ employeeId, hours }),
    enabled,
  });
}
