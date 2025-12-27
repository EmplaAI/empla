/**
 * @empla/react - EmployeeControls Component
 *
 * Control buttons for starting, stopping, pausing, and resuming employees.
 */

import type { CSSProperties, ReactNode } from 'react';

import { useEmployeeControl } from '../hooks/useEmployeeControl';

/**
 * Props for EmployeeControls.
 */
export interface EmployeeControlsProps {
  /** Employee ID */
  employeeId: string;

  /** Size variant */
  size?: 'sm' | 'md' | 'lg';

  /** Layout direction */
  direction?: 'horizontal' | 'vertical';

  /** Show all controls or just primary (start/stop) */
  showAll?: boolean;

  /** Disable all controls */
  disabled?: boolean;

  /** Callback when an action completes */
  onActionComplete?: (action: 'start' | 'stop' | 'pause' | 'resume') => void;

  /** Callback when an action fails */
  onActionError?: (action: 'start' | 'stop' | 'pause' | 'resume', error: Error) => void;

  /** Custom render for buttons (for styling integration) */
  renderButton?: (props: ControlButtonProps) => ReactNode;

  /** Additional CSS class */
  className?: string;

  /** Additional inline styles */
  style?: CSSProperties;
}

/**
 * Props passed to custom button renderer.
 */
export interface ControlButtonProps {
  /** Action type */
  action: 'start' | 'stop' | 'pause' | 'resume';

  /** Button label */
  label: string;

  /** Whether the button is disabled */
  disabled: boolean;

  /** Whether the action is in progress */
  loading: boolean;

  /** Click handler */
  onClick: () => void;

  /** Default button styles */
  style: CSSProperties;

  /** Variant for styling */
  variant: 'primary' | 'secondary' | 'danger';
}

/**
 * Default button component.
 */
function DefaultButton({
  label,
  disabled,
  loading,
  onClick,
  style,
}: ControlButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || loading}
      style={{
        ...style,
        opacity: disabled || loading ? 0.5 : 1,
        cursor: disabled || loading ? 'not-allowed' : 'pointer',
      }}
    >
      {loading ? '...' : label}
    </button>
  );
}

/**
 * Control buttons for employee lifecycle management.
 *
 * @example
 * ```tsx
 * // Basic usage
 * <EmployeeControls employeeId={id} />
 *
 * // With custom styling
 * <EmployeeControls
 *   employeeId={id}
 *   renderButton={(props) => (
 *     <MyButton variant={props.variant} onClick={props.onClick}>
 *       {props.label}
 *     </MyButton>
 *   )}
 * />
 * ```
 */
export function EmployeeControls({
  employeeId,
  size = 'md',
  direction = 'horizontal',
  showAll = true,
  disabled = false,
  onActionComplete,
  onActionError,
  renderButton,
  className = '',
  style,
}: EmployeeControlsProps) {
  const {
    isRunning,
    isPaused,
    isActionPending,
    start,
    stop,
    pause,
    resume,
  } = useEmployeeControl(employeeId);

  const sizeStyles: Record<string, CSSProperties> = {
    sm: { padding: '4px 8px', fontSize: '12px' },
    md: { padding: '6px 12px', fontSize: '13px' },
    lg: { padding: '8px 16px', fontSize: '14px' },
  };

  const baseButtonStyle: CSSProperties = {
    border: 'none',
    borderRadius: '6px',
    fontWeight: 500,
    transition: 'background-color 0.2s, opacity 0.2s',
    ...sizeStyles[size],
  };

  const variantStyles: Record<string, CSSProperties> = {
    primary: {
      ...baseButtonStyle,
      backgroundColor: '#10B981',
      color: '#FFFFFF',
    },
    secondary: {
      ...baseButtonStyle,
      backgroundColor: '#F3F4F6',
      color: '#374151',
      border: '1px solid #E5E7EB',
    },
    danger: {
      ...baseButtonStyle,
      backgroundColor: '#EF4444',
      color: '#FFFFFF',
    },
  };

  const containerStyle: CSSProperties = {
    display: 'flex',
    flexDirection: direction === 'vertical' ? 'column' : 'row',
    gap: size === 'sm' ? '4px' : '8px',
    ...style,
  };

  const handleAction = (
    action: 'start' | 'stop' | 'pause' | 'resume',
    mutate: typeof start.mutate
  ) => {
    mutate(undefined, {
      onSuccess: () => onActionComplete?.(action),
      onError: (error) => onActionError?.(action, error as Error),
    });
  };

  const ButtonComponent = renderButton || DefaultButton;

  const buttons: ControlButtonProps[] = [];

  if (!isRunning) {
    // Show start button when not running
    buttons.push({
      action: 'start',
      label: 'Start',
      disabled: disabled || isActionPending,
      loading: start.isPending,
      onClick: () => handleAction('start', start.mutate),
      style: variantStyles.primary,
      variant: 'primary',
    });
  } else {
    // Show stop button when running
    buttons.push({
      action: 'stop',
      label: 'Stop',
      disabled: disabled || isActionPending,
      loading: stop.isPending,
      onClick: () => handleAction('stop', stop.mutate),
      style: variantStyles.danger,
      variant: 'danger',
    });

    // Show pause/resume when running and showAll is true
    if (showAll) {
      if (isPaused) {
        buttons.push({
          action: 'resume',
          label: 'Resume',
          disabled: disabled || isActionPending,
          loading: resume.isPending,
          onClick: () => handleAction('resume', resume.mutate),
          style: variantStyles.secondary,
          variant: 'secondary',
        });
      } else {
        buttons.push({
          action: 'pause',
          label: 'Pause',
          disabled: disabled || isActionPending,
          loading: pause.isPending,
          onClick: () => handleAction('pause', pause.mutate),
          style: variantStyles.secondary,
          variant: 'secondary',
        });
      }
    }
  }

  return (
    <div className={className} style={containerStyle}>
      {buttons.map((buttonProps) => (
        <ButtonComponent key={buttonProps.action} {...buttonProps} />
      ))}
    </div>
  );
}

/**
 * Props for EmployeeControlButton.
 */
export interface EmployeeControlButtonProps {
  /** Employee ID */
  employeeId: string;

  /** Action to perform */
  action: 'start' | 'stop' | 'pause' | 'resume';

  /** Button content */
  children?: ReactNode;

  /** Disable the button */
  disabled?: boolean;

  /** Additional CSS class */
  className?: string;

  /** Additional inline styles */
  style?: CSSProperties;

  /** Callback on success */
  onSuccess?: () => void;

  /** Callback on error */
  onError?: (error: Error) => void;
}

/**
 * Single control button for a specific action.
 *
 * @example
 * ```tsx
 * <EmployeeControlButton employeeId={id} action="start">
 *   Launch Employee
 * </EmployeeControlButton>
 * ```
 */
export function EmployeeControlButton({
  employeeId,
  action,
  children,
  disabled = false,
  className = '',
  style,
  onSuccess,
  onError,
}: EmployeeControlButtonProps) {
  const { start, stop, pause, resume, isActionPending } = useEmployeeControl(employeeId);

  const mutations = { start, stop, pause, resume };
  const mutation = mutations[action];

  const labels: Record<string, string> = {
    start: 'Start',
    stop: 'Stop',
    pause: 'Pause',
    resume: 'Resume',
  };

  const handleClick = () => {
    mutation.mutate(undefined, {
      onSuccess: () => onSuccess?.(),
      onError: (error) => onError?.(error as Error),
    });
  };

  const buttonStyle: CSSProperties = {
    padding: '6px 12px',
    border: 'none',
    borderRadius: '6px',
    fontWeight: 500,
    cursor: disabled || isActionPending ? 'not-allowed' : 'pointer',
    opacity: disabled || isActionPending ? 0.5 : 1,
    backgroundColor: action === 'stop' ? '#EF4444' : action === 'start' ? '#10B981' : '#F3F4F6',
    color: action === 'stop' || action === 'start' ? '#FFFFFF' : '#374151',
    ...style,
  };

  return (
    <button
      type="button"
      className={className}
      style={buttonStyle}
      onClick={handleClick}
      disabled={disabled || isActionPending}
    >
      {mutation.isPending ? '...' : (children ?? labels[action])}
    </button>
  );
}
