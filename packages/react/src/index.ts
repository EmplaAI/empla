/**
 * @empla/react
 *
 * React components and hooks for empla digital employee dashboard.
 *
 * @example Basic usage
 * ```tsx
 * import { EmplaProvider, useEmployees, useActivity } from '@empla/react';
 *
 * function App() {
 *   return (
 *     <EmplaProvider config={{ apiUrl: '/api', authToken: token }}>
 *       <Dashboard />
 *     </EmplaProvider>
 *   );
 * }
 *
 * function Dashboard() {
 *   const { data: employees } = useEmployees();
 *   const { data: activity } = useActivity({ autoRefresh: true });
 *
 *   return (
 *     <div>
 *       <h1>Employees ({employees?.total})</h1>
 *       <h2>Recent Activity ({activity?.total})</h2>
 *     </div>
 *   );
 * }
 * ```
 */

// Provider
export {
  EmplaContext,
  EmplaProvider,
  useEmplaApi,
  useEmplaContext,
  type EmplaProviderProps,
} from './provider';

// Hooks
export {
  // Activity
  activityKeys,
  useActivity,
  useActivitySummary,
  useRecentActivity,
  type UseActivityOptions,
  // Employee Control
  useEmployeeControl,
  useEmployeeStatus,
  // Employees
  employeeKeys,
  useCreateEmployee,
  useDeleteEmployee,
  useEmployee,
  useEmployees,
  useUpdateEmployee,
} from './hooks';

// Types
export type {
  Activity,
  ActivitySummary,
  Employee,
  EmployeeCreate,
  EmployeeRole,
  EmployeeRuntimeStatus,
  EmployeeStatus,
  EmployeeUpdate,
  EmplaConfig,
  LifecycleStage,
  LoginResponse,
  PaginatedResponse,
} from './types';

// API Client (for advanced usage)
export { ApiError, createApiClient, type ApiClient, type ApiClientConfig } from './lib/api';
