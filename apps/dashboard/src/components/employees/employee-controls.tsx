import { Play, Pause, Square, RefreshCw, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import type { Employee } from '@empla/react';
import { useEmployeeControl } from '@empla/react';
import { Button } from '@/components/ui/button';

interface EmployeeControlsProps {
  employee: Employee;
  onActionComplete?: () => void;
}

export function EmployeeControls({ employee, onActionComplete }: EmployeeControlsProps) {
  const { start, stop, pause, resume } = useEmployeeControl(employee.id);

  const isLoading = start.isPending || stop.isPending || pause.isPending || resume.isPending;

  const handleStart = () => {
    start.mutate(undefined, {
      onSuccess: () => {
        toast.success('Employee started', {
          description: `${employee.name} is now running`,
        });
        onActionComplete?.();
      },
      onError: (error) => {
        toast.error('Failed to start employee', {
          description: error instanceof Error ? error.message : 'Please try again',
        });
      },
    });
  };

  const handleStop = () => {
    stop.mutate(undefined, {
      onSuccess: () => {
        toast.success('Employee stopped', {
          description: `${employee.name} has been stopped`,
        });
        onActionComplete?.();
      },
      onError: (error) => {
        toast.error('Failed to stop employee', {
          description: error instanceof Error ? error.message : 'Please try again',
        });
      },
    });
  };

  const handlePause = () => {
    pause.mutate(undefined, {
      onSuccess: () => {
        toast.success('Employee paused', {
          description: `${employee.name} is now paused`,
        });
        onActionComplete?.();
      },
      onError: (error) => {
        toast.error('Failed to pause employee', {
          description: error instanceof Error ? error.message : 'Please try again',
        });
      },
    });
  };

  const handleResume = () => {
    resume.mutate(undefined, {
      onSuccess: () => {
        toast.success('Employee resumed', {
          description: `${employee.name} is now running`,
        });
        onActionComplete?.();
      },
      onError: (error) => {
        toast.error('Failed to resume employee', {
          description: error instanceof Error ? error.message : 'Please try again',
        });
      },
    });
  };

  const canStart = employee.status === 'active' && !employee.isRunning;
  const canStop = employee.isRunning;
  const canPause = employee.isRunning && employee.status !== 'paused';
  const canResume = employee.status === 'paused';

  return (
    <div className="flex flex-wrap gap-2">
      {canStart && (
        <Button
          onClick={handleStart}
          disabled={isLoading}
          className="gap-2 bg-status-active hover:bg-status-active/90"
        >
          {start.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Play className="h-4 w-4" />
          )}
          Start
        </Button>
      )}

      {canResume && (
        <Button
          onClick={handleResume}
          disabled={isLoading}
          className="gap-2"
        >
          {resume.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          Resume
        </Button>
      )}

      {canPause && (
        <Button
          onClick={handlePause}
          disabled={isLoading}
          variant="outline"
          className="gap-2 border-status-paused/50 text-status-paused hover:bg-status-paused/10"
        >
          {pause.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Pause className="h-4 w-4" />
          )}
          Pause
        </Button>
      )}

      {canStop && (
        <Button
          onClick={handleStop}
          disabled={isLoading}
          variant="outline"
          className="gap-2 border-destructive/50 text-destructive hover:bg-destructive/10"
        >
          {stop.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Square className="h-4 w-4" />
          )}
          Stop
        </Button>
      )}
    </div>
  );
}
