/**
 * @empla/react
 *
 * React components and hooks for empla digital employee dashboard.
 *
 * @example Basic usage with hooks
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
 *
 * @example Using components
 * ```tsx
 * import {
 *   EmplaProvider,
 *   EmployeeList,
 *   EmployeeFilters,
 *   EmployeeForm,
 * } from '@empla/react';
 *
 * function EmployeeDashboard() {
 *   const [status, setStatus] = useState<EmployeeStatus>();
 *   const [role, setRole] = useState<EmployeeRole>();
 *
 *   return (
 *     <EmplaProvider config={{ apiUrl: '/api', authToken: token }}>
 *       <EmployeeFilters
 *         status={status}
 *         role={role}
 *         onStatusChange={setStatus}
 *         onRoleChange={setRole}
 *       />
 *       <EmployeeList
 *         status={status}
 *         role={role}
 *         showControls
 *         onEmployeeClick={(emp) => console.log('Selected:', emp.id)}
 *       />
 *     </EmplaProvider>
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
  // Integrations
  integrationKeys,
  useConnectProvider,
  useCredentials,
  useProviders,
  useRevokeCredential,
} from './hooks';

// Components
export {
  // Status badges
  EmployeeStatusBadge,
  RunningIndicator,
  type EmployeeStatusBadgeProps,
  type RunningIndicatorProps,
  // Employee card
  EmployeeCard,
  EmployeeCardSkeleton,
  type EmployeeCardProps,
  type EmployeeCardSkeletonProps,
  // Employee controls
  EmployeeControls,
  EmployeeControlButton,
  type EmployeeControlsProps,
  type EmployeeControlButtonProps,
  type ControlButtonProps,
  // Employee list
  EmployeeList,
  EmployeeFilters,
  type EmployeeListProps,
  type EmployeeFiltersProps,
  // Employee form
  EmployeeForm,
  DeleteEmployeeButton,
  type EmployeeFormProps,
  type DeleteEmployeeButtonProps,
} from './components';

// Types
export type {
  Activity,
  ActivitySummary,
  ConnectRequest,
  ConnectResponse,
  CredentialSource,
  CredentialStatus,
  CredentialType,
  Employee,
  EmployeeCreate,
  EmployeeRole,
  EmployeeRuntimeStatus,
  EmployeeStatus,
  EmployeeUpdate,
  EmplaConfig,
  IntegrationCredential,
  IntegrationProvider,
  LifecycleStage,
  LoginResponse,
  PaginatedResponse,
  ProviderInfo,
} from './types';

// API Client (for advanced usage)
export { ApiError, createApiClient, type ApiClient, type ApiClientConfig } from './lib/api';
