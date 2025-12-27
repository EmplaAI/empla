/**
 * @empla/react - EmployeeCard Component
 *
 * Card display for an employee with status, role, and actions.
 */

import type { CSSProperties, ReactNode } from 'react';

import type { Employee } from '../types';

import { EmployeeStatusBadge, RunningIndicator } from './EmployeeStatusBadge';

/**
 * Human-readable role labels.
 */
const ROLE_LABELS: Record<string, string> = {
  sales_ae: 'Sales AE',
  csm: 'Customer Success',
  pm: 'Product Manager',
  sdr: 'Sales Development',
  recruiter: 'Recruiter',
  custom: 'Custom',
};

/**
 * Props for EmployeeCard.
 */
export interface EmployeeCardProps {
  /** Employee data */
  employee: Employee;

  /** Whether the employee is currently running */
  isRunning?: boolean;

  /** Whether the employee is paused */
  isPaused?: boolean;

  /** Whether the employee has an error */
  hasError?: boolean;

  /** Click handler for the card */
  onClick?: (employee: Employee) => void;

  /** Custom actions to render in the card footer */
  actions?: ReactNode;

  /** Show the running indicator */
  showRunningIndicator?: boolean;

  /** Compact mode with less padding */
  compact?: boolean;

  /** Additional CSS class */
  className?: string;

  /** Additional inline styles */
  style?: CSSProperties;
}

/**
 * Card component for displaying employee information.
 *
 * @example
 * ```tsx
 * <EmployeeCard
 *   employee={employee}
 *   isRunning={status.isRunning}
 *   onClick={(emp) => navigate(`/employees/${emp.id}`)}
 *   actions={<EmployeeControls employeeId={employee.id} />}
 * />
 * ```
 */
export function EmployeeCard({
  employee,
  isRunning,
  isPaused = false,
  hasError = false,
  onClick,
  actions,
  showRunningIndicator = true,
  compact = false,
  className = '',
  style,
}: EmployeeCardProps) {
  // Use employee.isRunning if isRunning prop not provided
  const running = isRunning ?? employee.isRunning;

  const cardStyle: CSSProperties = {
    backgroundColor: '#FFFFFF',
    border: '1px solid #E5E7EB',
    borderRadius: '8px',
    padding: compact ? '12px' : '16px',
    cursor: onClick ? 'pointer' : undefined,
    transition: 'box-shadow 0.2s, border-color 0.2s',
    ...style,
  };

  const headerStyle: CSSProperties = {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: compact ? '8px' : '12px',
  };

  const nameStyle: CSSProperties = {
    fontSize: compact ? '14px' : '16px',
    fontWeight: 600,
    color: '#111827',
    margin: 0,
  };

  const roleStyle: CSSProperties = {
    fontSize: compact ? '12px' : '13px',
    color: '#6B7280',
    marginTop: '2px',
  };

  const emailStyle: CSSProperties = {
    fontSize: compact ? '12px' : '13px',
    color: '#9CA3AF',
    marginTop: '4px',
  };

  const badgesStyle: CSSProperties = {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '8px',
    marginTop: compact ? '8px' : '12px',
  };

  const footerStyle: CSSProperties = {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: compact ? '12px' : '16px',
    paddingTop: compact ? '12px' : '16px',
    borderTop: '1px solid #F3F4F6',
  };

  const handleClick = onClick ? () => onClick(employee) : undefined;

  const handleKeyDown = onClick
    ? (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick(employee);
        }
      }
    : undefined;

  return (
    <div
      className={className}
      style={cardStyle}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      <div style={headerStyle}>
        <div>
          <h3 style={nameStyle}>{employee.name}</h3>
          <div style={roleStyle}>{ROLE_LABELS[employee.role] || employee.role}</div>
          <div style={emailStyle}>{employee.email}</div>
        </div>
        {showRunningIndicator && (
          <RunningIndicator
            isRunning={running}
            isPaused={isPaused}
            hasError={hasError}
            size="sm"
          />
        )}
      </div>

      <div style={badgesStyle}>
        <EmployeeStatusBadge value={employee.status} variant="status" size="sm" />
        <EmployeeStatusBadge value={employee.lifecycleStage} variant="lifecycle" size="sm" />
      </div>

      {(actions || employee.capabilities.length > 0) && (
        <div style={footerStyle}>
          {employee.capabilities.length > 0 && (
            <div style={{ fontSize: '12px', color: '#6B7280' }}>
              {employee.capabilities.slice(0, 3).join(', ')}
              {employee.capabilities.length > 3 && ` +${employee.capabilities.length - 3}`}
            </div>
          )}
          {actions && <div>{actions}</div>}
        </div>
      )}
    </div>
  );
}

/**
 * Props for EmployeeCardSkeleton.
 */
export interface EmployeeCardSkeletonProps {
  /** Compact mode */
  compact?: boolean;

  /** Additional CSS class */
  className?: string;
}

/**
 * Loading skeleton for EmployeeCard.
 */
export function EmployeeCardSkeleton({ compact = false, className = '' }: EmployeeCardSkeletonProps) {
  const cardStyle: CSSProperties = {
    backgroundColor: '#FFFFFF',
    border: '1px solid #E5E7EB',
    borderRadius: '8px',
    padding: compact ? '12px' : '16px',
  };

  const skeletonStyle: CSSProperties = {
    backgroundColor: '#F3F4F6',
    borderRadius: '4px',
    animation: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
  };

  return (
    <div className={className} style={cardStyle}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
        <div>
          <div style={{ ...skeletonStyle, width: '120px', height: '20px', marginBottom: '8px' }} />
          <div style={{ ...skeletonStyle, width: '80px', height: '14px', marginBottom: '4px' }} />
          <div style={{ ...skeletonStyle, width: '150px', height: '14px' }} />
        </div>
        <div style={{ ...skeletonStyle, width: '60px', height: '16px' }} />
      </div>
      <div style={{ display: 'flex', gap: '8px', marginTop: '12px' }}>
        <div style={{ ...skeletonStyle, width: '70px', height: '24px', borderRadius: '12px' }} />
        <div style={{ ...skeletonStyle, width: '90px', height: '24px', borderRadius: '12px' }} />
      </div>
    </div>
  );
}
