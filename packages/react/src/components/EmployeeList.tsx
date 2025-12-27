/**
 * @empla/react - EmployeeList Component
 *
 * List of employees with filtering, pagination, and optional controls.
 */

import { useState, type CSSProperties, type ReactNode } from 'react';

import { useEmployees } from '../hooks/useEmployees';
import type { Employee, EmployeeRole, EmployeeStatus } from '../types';

import { EmployeeCard, EmployeeCardSkeleton } from './EmployeeCard';
import { EmployeeControls } from './EmployeeControls';

/**
 * Props for EmployeeList.
 */
export interface EmployeeListProps {
  /** Filter by status */
  status?: EmployeeStatus;

  /** Filter by role */
  role?: EmployeeRole;

  /** Items per page */
  pageSize?: number;

  /** Layout mode */
  layout?: 'grid' | 'list';

  /** Show employee controls in each card */
  showControls?: boolean;

  /** Click handler for employee cards */
  onEmployeeClick?: (employee: Employee) => void;

  /** Custom card renderer */
  renderCard?: (employee: Employee, controls: ReactNode) => ReactNode;

  /** Custom empty state */
  emptyState?: ReactNode;

  /** Custom loading state */
  loadingState?: ReactNode;

  /** Custom error state */
  errorState?: (error: Error) => ReactNode;

  /** Additional CSS class */
  className?: string;

  /** Additional inline styles */
  style?: CSSProperties;
}

/**
 * Paginated list of employees.
 *
 * @example
 * ```tsx
 * // Basic usage
 * <EmployeeList showControls />
 *
 * // With filtering
 * <EmployeeList status="active" role="sales_ae" />
 *
 * // With custom click handler
 * <EmployeeList onEmployeeClick={(emp) => navigate(`/employees/${emp.id}`)} />
 * ```
 */
export function EmployeeList({
  status,
  role,
  pageSize = 10,
  layout = 'grid',
  showControls = false,
  onEmployeeClick,
  renderCard,
  emptyState,
  loadingState,
  errorState,
  className = '',
  style,
}: EmployeeListProps) {
  const [page, setPage] = useState(1);

  const {
    data,
    isLoading,
    error,
    refetch,
  } = useEmployees({
    page,
    pageSize,
    status,
    role,
  });

  const containerStyle: CSSProperties = {
    ...style,
  };

  const gridStyle: CSSProperties = {
    display: 'grid',
    gridTemplateColumns: layout === 'grid' ? 'repeat(auto-fill, minmax(300px, 1fr))' : '1fr',
    gap: '16px',
  };

  const paginationStyle: CSSProperties = {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    gap: '12px',
    marginTop: '24px',
  };

  const buttonStyle: CSSProperties = {
    padding: '8px 16px',
    border: '1px solid #E5E7EB',
    borderRadius: '6px',
    backgroundColor: '#FFFFFF',
    color: '#374151',
    fontSize: '14px',
    cursor: 'pointer',
  };

  const disabledButtonStyle: CSSProperties = {
    ...buttonStyle,
    opacity: 0.5,
    cursor: 'not-allowed',
  };

  // Loading state
  if (isLoading) {
    if (loadingState) {
      return <>{loadingState}</>;
    }

    return (
      <div className={className} style={containerStyle}>
        <div style={gridStyle}>
          {Array.from({ length: pageSize }).map((_, i) => (
            <EmployeeCardSkeleton key={i} />
          ))}
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    if (errorState) {
      return <>{errorState(error as Error)}</>;
    }

    return (
      <div className={className} style={containerStyle}>
        <div style={{ textAlign: 'center', padding: '40px', color: '#EF4444' }}>
          <p>Failed to load employees</p>
          <button
            type="button"
            onClick={() => refetch()}
            style={{ ...buttonStyle, marginTop: '16px' }}
          >
            Try Again
          </button>
        </div>
      </div>
    );
  }

  // Empty state
  if (!data?.items.length) {
    if (emptyState) {
      return <>{emptyState}</>;
    }

    return (
      <div className={className} style={containerStyle}>
        <div style={{ textAlign: 'center', padding: '40px', color: '#6B7280' }}>
          <p>No employees found</p>
          {(status || role) && (
            <p style={{ fontSize: '14px', marginTop: '8px' }}>
              Try adjusting your filters
            </p>
          )}
        </div>
      </div>
    );
  }

  const { items: employees, total, pages } = data;

  return (
    <div className={className} style={containerStyle}>
      <div style={gridStyle}>
        {employees.map((employee) => {
          const controls = showControls ? (
            <EmployeeControls employeeId={employee.id} size="sm" showAll={false} />
          ) : null;

          if (renderCard) {
            return <div key={employee.id}>{renderCard(employee, controls)}</div>;
          }

          return (
            <EmployeeCard
              key={employee.id}
              employee={employee}
              onClick={onEmployeeClick}
              actions={controls}
            />
          );
        })}
      </div>

      {/* Pagination */}
      {pages > 1 && (
        <div style={paginationStyle}>
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            style={page === 1 ? disabledButtonStyle : buttonStyle}
          >
            Previous
          </button>

          <span style={{ color: '#6B7280', fontSize: '14px' }}>
            Page {page} of {pages} ({total} employees)
          </span>

          <button
            type="button"
            onClick={() => setPage((p) => Math.min(pages, p + 1))}
            disabled={page === pages}
            style={page === pages ? disabledButtonStyle : buttonStyle}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * Props for EmployeeFilters.
 */
export interface EmployeeFiltersProps {
  /** Current status filter */
  status?: EmployeeStatus;

  /** Current role filter */
  role?: EmployeeRole;

  /** Callback when status changes */
  onStatusChange?: (status: EmployeeStatus | undefined) => void;

  /** Callback when role changes */
  onRoleChange?: (role: EmployeeRole | undefined) => void;

  /** Additional CSS class */
  className?: string;

  /** Additional inline styles */
  style?: CSSProperties;
}

/**
 * Filter controls for employee list.
 *
 * @example
 * ```tsx
 * const [status, setStatus] = useState<EmployeeStatus>();
 * const [role, setRole] = useState<EmployeeRole>();
 *
 * <>
 *   <EmployeeFilters
 *     status={status}
 *     role={role}
 *     onStatusChange={setStatus}
 *     onRoleChange={setRole}
 *   />
 *   <EmployeeList status={status} role={role} />
 * </>
 * ```
 */
export function EmployeeFilters({
  status,
  role,
  onStatusChange,
  onRoleChange,
  className = '',
  style,
}: EmployeeFiltersProps) {
  const containerStyle: CSSProperties = {
    display: 'flex',
    gap: '12px',
    flexWrap: 'wrap',
    ...style,
  };

  const selectStyle: CSSProperties = {
    padding: '8px 12px',
    border: '1px solid #E5E7EB',
    borderRadius: '6px',
    backgroundColor: '#FFFFFF',
    color: '#374151',
    fontSize: '14px',
    minWidth: '150px',
  };

  const statuses: Array<{ value: EmployeeStatus; label: string }> = [
    { value: 'onboarding', label: 'Onboarding' },
    { value: 'active', label: 'Active' },
    { value: 'paused', label: 'Paused' },
    { value: 'stopped', label: 'Stopped' },
    { value: 'terminated', label: 'Terminated' },
  ];

  const roles: Array<{ value: EmployeeRole; label: string }> = [
    { value: 'sales_ae', label: 'Sales AE' },
    { value: 'csm', label: 'Customer Success' },
    { value: 'pm', label: 'Product Manager' },
    { value: 'sdr', label: 'Sales Development' },
    { value: 'recruiter', label: 'Recruiter' },
    { value: 'custom', label: 'Custom' },
  ];

  return (
    <div className={className} style={containerStyle}>
      <select
        value={status || ''}
        onChange={(e) => onStatusChange?.(e.target.value as EmployeeStatus || undefined)}
        style={selectStyle}
      >
        <option value="">All Statuses</option>
        {statuses.map((s) => (
          <option key={s.value} value={s.value}>
            {s.label}
          </option>
        ))}
      </select>

      <select
        value={role || ''}
        onChange={(e) => onRoleChange?.(e.target.value as EmployeeRole || undefined)}
        style={selectStyle}
      >
        <option value="">All Roles</option>
        {roles.map((r) => (
          <option key={r.value} value={r.value}>
            {r.label}
          </option>
        ))}
      </select>
    </div>
  );
}
