import type { EmployeeStatus, LifecycleStage } from '@empla/react';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

interface EmployeeStatusBadgeProps {
  status: EmployeeStatus;
  isRunning?: boolean;
  className?: string;
}

const statusVariants: Record<EmployeeStatus, { variant: 'active' | 'running' | 'paused' | 'stopped' | 'error'; label: string }> = {
  active: { variant: 'active', label: 'Active' },
  onboarding: { variant: 'running', label: 'Onboarding' },
  paused: { variant: 'paused', label: 'Paused' },
  stopped: { variant: 'stopped', label: 'Stopped' },
  terminated: { variant: 'error', label: 'Terminated' },
};

export function EmployeeStatusBadge({ status, isRunning, className }: EmployeeStatusBadgeProps) {
  const { variant, label } = statusVariants[status] ?? { variant: 'stopped', label: status };

  // Override to show "Running" if the employee is currently running
  if (isRunning && status === 'active') {
    return (
      <Badge variant="running" className={cn('status-pulse', className)}>
        Running
      </Badge>
    );
  }

  return (
    <Badge variant={variant} className={className}>
      {label}
    </Badge>
  );
}

interface LifecycleBadgeProps {
  stage: LifecycleStage;
  className?: string;
}

const lifecycleColors: Record<LifecycleStage, string> = {
  shadow: 'border-purple-500/30 bg-purple-500/10 text-purple-400',
  supervised: 'border-blue-500/30 bg-blue-500/10 text-blue-400',
  autonomous: 'border-status-active/30 bg-status-active/10 text-status-active',
};

export function LifecycleBadge({ stage, className }: LifecycleBadgeProps) {
  return (
    <Badge variant="outline" className={cn(lifecycleColors[stage], className)}>
      {stage}
    </Badge>
  );
}
