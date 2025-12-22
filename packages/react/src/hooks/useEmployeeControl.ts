/**
 * @empla/react - Employee Control Hooks
 *
 * React hooks for starting, stopping, and controlling employees.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useEmplaApi } from '../provider';
import type { EmployeeRuntimeStatus } from '../types';

import { employeeKeys } from './useEmployees';

/**
 * Hook to control an employee's lifecycle.
 *
 * Provides start, stop, pause, and resume mutations.
 *
 * @example
 * ```tsx
 * function EmployeeControls({ id }: { id: string }) {
 *   const { start, stop, pause, resume, status, isRunning } = useEmployeeControl(id);
 *
 *   return (
 *     <div>
 *       <span>Status: {isRunning ? 'Running' : 'Stopped'}</span>
 *       {isRunning ? (
 *         <button onClick={() => stop.mutate()}>Stop</button>
 *       ) : (
 *         <button onClick={() => start.mutate()}>Start</button>
 *       )}
 *     </div>
 *   );
 * }
 * ```
 */
export function useEmployeeControl(employeeId: string) {
  const api = useEmplaApi();
  const queryClient = useQueryClient();

  // Query for current status
  const statusQuery = useQuery<EmployeeRuntimeStatus>({
    queryKey: employeeKeys.status(employeeId),
    queryFn: () => api.getEmployeeStatus(employeeId),
    enabled: !!employeeId,
    refetchInterval: 30000, // Refresh every 30 seconds
  });

  // Invalidate queries after mutations
  const invalidateQueries = () => {
    queryClient.invalidateQueries({
      queryKey: employeeKeys.status(employeeId),
    });
    queryClient.invalidateQueries({
      queryKey: employeeKeys.detail(employeeId),
    });
    queryClient.invalidateQueries({
      queryKey: employeeKeys.lists(),
    });
  };

  // Start mutation
  const startMutation = useMutation({
    mutationFn: () => api.startEmployee(employeeId),
    onSuccess: (data) => {
      queryClient.setQueryData(employeeKeys.status(employeeId), data);
      invalidateQueries();
    },
    onError: (error: Error) => {
      console.error(`Failed to start employee ${employeeId}:`, error);
      // Consumer can access error via startMutation.error
    },
  });

  // Stop mutation
  const stopMutation = useMutation({
    mutationFn: () => api.stopEmployee(employeeId),
    onSuccess: (data) => {
      queryClient.setQueryData(employeeKeys.status(employeeId), data);
      invalidateQueries();
    },
    onError: (error: Error) => {
      console.error(`Failed to stop employee ${employeeId}:`, error);
    },
  });

  // Pause mutation
  const pauseMutation = useMutation({
    mutationFn: () => api.pauseEmployee(employeeId),
    onSuccess: (data) => {
      queryClient.setQueryData(employeeKeys.status(employeeId), data);
      invalidateQueries();
    },
    onError: (error: Error) => {
      console.error(`Failed to pause employee ${employeeId}:`, error);
    },
  });

  // Resume mutation
  const resumeMutation = useMutation({
    mutationFn: () => api.resumeEmployee(employeeId),
    onSuccess: (data) => {
      queryClient.setQueryData(employeeKeys.status(employeeId), data);
      invalidateQueries();
    },
    onError: (error: Error) => {
      console.error(`Failed to resume employee ${employeeId}:`, error);
    },
  });

  return {
    // Status
    status: statusQuery.data,
    isLoading: statusQuery.isLoading,
    isRunning: statusQuery.data?.isRunning ?? false,
    isPaused: statusQuery.data?.status === 'paused' && statusQuery.data?.isRunning,
    refetchStatus: statusQuery.refetch,

    // Actions
    start: startMutation,
    stop: stopMutation,
    pause: pauseMutation,
    resume: resumeMutation,

    // Combined loading state
    isActionPending:
      startMutation.isPending ||
      stopMutation.isPending ||
      pauseMutation.isPending ||
      resumeMutation.isPending,

    // Error state - consumers should check this to show error feedback
    actionError:
      startMutation.error ||
      stopMutation.error ||
      pauseMutation.error ||
      resumeMutation.error,
  };
}

/**
 * Hook to just get employee status (read-only).
 *
 * Lighter weight than useEmployeeControl if you only need status.
 */
export function useEmployeeStatus(
  employeeId: string,
  options?: {
    enabled?: boolean;
    refetchInterval?: number | false;
  }
) {
  const api = useEmplaApi();

  return useQuery<EmployeeRuntimeStatus>({
    queryKey: employeeKeys.status(employeeId),
    queryFn: () => api.getEmployeeStatus(employeeId),
    enabled: options?.enabled ?? !!employeeId,
    refetchInterval: options?.refetchInterval ?? 30000,
  });
}
