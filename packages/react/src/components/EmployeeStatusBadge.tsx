/**
 * @empla/react - EmployeeStatusBadge Component
 *
 * Displays employee status with appropriate visual styling.
 */

import type { CSSProperties, ReactNode } from 'react';

import type { EmployeeStatus, LifecycleStage } from '../types';

/**
 * Status color configuration.
 */
const STATUS_COLORS: Record<EmployeeStatus, { bg: string; text: string; border: string }> = {
  onboarding: { bg: '#FEF3C7', text: '#92400E', border: '#F59E0B' },
  active: { bg: '#D1FAE5', text: '#065F46', border: '#10B981' },
  paused: { bg: '#E0E7FF', text: '#3730A3', border: '#6366F1' },
  stopped: { bg: '#F3F4F6', text: '#374151', border: '#9CA3AF' },
  terminated: { bg: '#FEE2E2', text: '#991B1B', border: '#EF4444' },
};

/**
 * Lifecycle stage color configuration.
 */
const LIFECYCLE_COLORS: Record<LifecycleStage, { bg: string; text: string; border: string }> = {
  shadow: { bg: '#F3F4F6', text: '#374151', border: '#9CA3AF' },
  supervised: { bg: '#DBEAFE', text: '#1E40AF', border: '#3B82F6' },
  autonomous: { bg: '#D1FAE5', text: '#065F46', border: '#10B981' },
};

/**
 * Human-readable status labels.
 */
const STATUS_LABELS: Record<EmployeeStatus, string> = {
  onboarding: 'Onboarding',
  active: 'Active',
  paused: 'Paused',
  stopped: 'Stopped',
  terminated: 'Terminated',
};

/**
 * Human-readable lifecycle labels.
 */
const LIFECYCLE_LABELS: Record<LifecycleStage, string> = {
  shadow: 'Shadow',
  supervised: 'Supervised',
  autonomous: 'Autonomous',
};

/**
 * Props for EmployeeStatusBadge.
 */
export interface EmployeeStatusBadgeProps {
  /** Employee status or lifecycle stage */
  value: EmployeeStatus | LifecycleStage;

  /** Badge variant */
  variant?: 'status' | 'lifecycle';

  /** Size variant */
  size?: 'sm' | 'md' | 'lg';

  /** Show dot indicator */
  showDot?: boolean;

  /** Additional CSS class */
  className?: string;

  /** Additional inline styles */
  style?: CSSProperties;

  /** Custom label override */
  label?: ReactNode;
}

/**
 * Badge component for displaying employee status or lifecycle stage.
 *
 * @example
 * ```tsx
 * <EmployeeStatusBadge value="active" variant="status" />
 * <EmployeeStatusBadge value="autonomous" variant="lifecycle" />
 * ```
 */
export function EmployeeStatusBadge({
  value,
  variant = 'status',
  size = 'md',
  showDot = true,
  className = '',
  style,
  label,
}: EmployeeStatusBadgeProps) {
  const colors =
    variant === 'status'
      ? STATUS_COLORS[value as EmployeeStatus]
      : LIFECYCLE_COLORS[value as LifecycleStage];

  const defaultLabel =
    variant === 'status'
      ? STATUS_LABELS[value as EmployeeStatus]
      : LIFECYCLE_LABELS[value as LifecycleStage];

  const sizeStyles: Record<string, CSSProperties> = {
    sm: { padding: '2px 8px', fontSize: '11px' },
    md: { padding: '4px 10px', fontSize: '12px' },
    lg: { padding: '6px 12px', fontSize: '14px' },
  };

  const dotSizes: Record<string, number> = {
    sm: 6,
    md: 8,
    lg: 10,
  };

  const badgeStyle: CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    borderRadius: '9999px',
    fontWeight: 500,
    backgroundColor: colors.bg,
    color: colors.text,
    border: `1px solid ${colors.border}`,
    ...sizeStyles[size],
    ...style,
  };

  const dotStyle: CSSProperties = {
    width: dotSizes[size],
    height: dotSizes[size],
    borderRadius: '50%',
    backgroundColor: colors.border,
  };

  return (
    <span className={className} style={badgeStyle}>
      {showDot && <span style={dotStyle} />}
      {label ?? defaultLabel}
    </span>
  );
}

/**
 * Props for RunningIndicator.
 */
export interface RunningIndicatorProps {
  /** Whether the employee is running */
  isRunning: boolean;

  /** Whether the employee is paused */
  isPaused?: boolean;

  /** Whether the employee has an error */
  hasError?: boolean;

  /** Size variant */
  size?: 'sm' | 'md' | 'lg';

  /** Additional CSS class */
  className?: string;
}

/**
 * Indicator for employee runtime state.
 *
 * @example
 * ```tsx
 * <RunningIndicator isRunning={true} />
 * <RunningIndicator isRunning={true} isPaused={true} />
 * ```
 */
export function RunningIndicator({
  isRunning,
  isPaused = false,
  hasError = false,
  size = 'md',
  className = '',
}: RunningIndicatorProps) {
  const dotSizes: Record<string, number> = {
    sm: 8,
    md: 10,
    lg: 12,
  };

  let color: string;
  let label: string;

  if (hasError) {
    color = '#EF4444';
    label = 'Error';
  } else if (!isRunning) {
    color = '#9CA3AF';
    label = 'Stopped';
  } else if (isPaused) {
    color = '#F59E0B';
    label = 'Paused';
  } else {
    color = '#10B981';
    label = 'Running';
  }

  const containerStyle: CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    fontSize: size === 'sm' ? '11px' : size === 'lg' ? '14px' : '12px',
    color: '#6B7280',
  };

  const dotStyle: CSSProperties = {
    width: dotSizes[size],
    height: dotSizes[size],
    borderRadius: '50%',
    backgroundColor: color,
    boxShadow: isRunning && !isPaused && !hasError ? `0 0 0 2px ${color}33` : undefined,
  };

  return (
    <span className={className} style={containerStyle}>
      <span style={dotStyle} />
      {label}
    </span>
  );
}
