import { useParams, useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, Trash2, Edit, Loader2, AlertCircle } from 'lucide-react';
import { toast } from 'sonner';
import { useEmployee, useDeleteEmployee, ApiError } from '@empla/react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogClose,
} from '@/components/ui/dialog';
import { EmployeeStatusBadge, LifecycleBadge } from '@/components/employees/employee-status-badge';
import { EmployeeControls } from '@/components/employees/employee-controls';
import { EmployeeInfoCard } from '@/components/employees/employee-info-card';
import { ActivityFeed } from '@/components/activity/activity-feed';
import { getInitials, cn } from '@/lib/utils';

function EmployeeDetailSkeleton() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Skeleton className="h-9 w-9" />
        <Skeleton className="h-8 w-48" />
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-6">
          <Skeleton className="h-48 w-full rounded-lg" />
          <Skeleton className="h-96 w-full rounded-lg" />
        </div>
        <div>
          <Skeleton className="h-64 w-full rounded-lg" />
        </div>
      </div>
    </div>
  );
}

function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center py-16">
      <h2 className="font-display text-2xl font-bold">Employee Not Found</h2>
      <p className="mt-2 text-muted-foreground">
        The employee you're looking for doesn't exist
      </p>
      <Button className="mt-4" asChild>
        <Link to="/employees">
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Employees
        </Link>
      </Button>
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-16">
      <div className="flex h-12 w-12 items-center justify-center rounded-full border border-destructive/30 bg-destructive/10">
        <AlertCircle className="h-6 w-6 text-destructive" />
      </div>
      <h2 className="mt-4 font-display text-2xl font-bold">Something went wrong</h2>
      <p className="mt-2 text-muted-foreground">{message}</p>
      <div className="mt-4 flex gap-2">
        <Button variant="outline" onClick={onRetry}>
          Try again
        </Button>
        <Button asChild>
          <Link to="/employees">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Employees
          </Link>
        </Button>
      </div>
    </div>
  );
}

export function EmployeeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const deleteEmployee = useDeleteEmployee();
  // Call hook unconditionally with enabled option to satisfy Rules of Hooks
  const { data: employee, isLoading, error, refetch } = useEmployee(id ?? '', {
    enabled: !!id,
  });

  // Early return if no ID provided
  if (!id) {
    return <NotFound />;
  }

  const handleDelete = () => {
    deleteEmployee.mutate(id, {
      onSuccess: () => {
        toast.success('Employee deleted', {
          description: `${employee?.name ?? 'Employee'} has been removed`,
        });
        navigate('/employees');
      },
      onError: (error) => {
        toast.error('Failed to delete employee', {
          description: error instanceof Error ? error.message : 'Please try again',
        });
      },
    });
  };

  if (isLoading) {
    return <EmployeeDetailSkeleton />;
  }

  // Handle errors with appropriate UI
  if (error) {
    // Check if it's a 404 error
    if (error instanceof ApiError && error.status === 404) {
      return <NotFound />;
    }
    // Other errors show error state with retry option
    return (
      <ErrorState
        message={error instanceof Error ? error.message : 'Failed to load employee'}
        onRetry={() => refetch()}
      />
    );
  }

  if (!employee) {
    return <NotFound />;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" asChild>
          <Link to="/employees">
            <ArrowLeft className="h-4 w-4" />
          </Link>
        </Button>
        <h2 className="font-display text-2xl font-bold tracking-tight">
          {employee.name}
        </h2>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Main content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Employee hero card */}
          <Card className="relative overflow-hidden border-border/50 bg-card/80 backdrop-blur-sm">
            {/* Running indicator */}
            {employee.isRunning && (
              <div className="absolute left-0 top-0 h-full w-1 bg-status-running shadow-[0_0_12px] shadow-status-running" />
            )}

            <CardContent className="p-6">
              <div className="flex flex-col gap-6 sm:flex-row sm:items-start">
                {/* Avatar */}
                <Avatar className="h-20 w-20 border-2 border-border">
                  <AvatarFallback
                    className={cn(
                      'font-mono text-xl font-semibold',
                      employee.isRunning
                        ? 'bg-status-running/10 text-status-running'
                        : 'bg-primary/10 text-primary'
                    )}
                  >
                    {getInitials(employee.name)}
                  </AvatarFallback>
                </Avatar>

                {/* Info */}
                <div className="flex-1 space-y-4">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <EmployeeStatusBadge
                        status={employee.status}
                        isRunning={employee.isRunning}
                      />
                      <LifecycleBadge stage={employee.lifecycleStage} />
                    </div>
                    <p className="mt-2 text-sm text-muted-foreground">
                      Employee ID:{' '}
                      <span className="font-mono text-foreground">{employee.id}</span>
                    </p>
                  </div>

                  {/* Controls */}
                  <EmployeeControls employee={employee} onActionComplete={refetch} />
                </div>

                {/* Actions */}
                <div className="flex gap-2">
                  <Button variant="outline" size="icon" disabled>
                    <Edit className="h-4 w-4" />
                  </Button>

                  <Dialog>
                    <DialogTrigger asChild>
                      <Button
                        variant="outline"
                        size="icon"
                        className="border-destructive/50 text-destructive hover:bg-destructive/10"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </DialogTrigger>
                    <DialogContent>
                      <DialogHeader>
                        <DialogTitle>Delete Employee</DialogTitle>
                        <DialogDescription>
                          Are you sure you want to delete {employee.name}? This action
                          cannot be undone.
                        </DialogDescription>
                      </DialogHeader>
                      <DialogFooter>
                        <DialogClose asChild>
                          <Button variant="outline">Cancel</Button>
                        </DialogClose>
                        <Button
                          variant="destructive"
                          onClick={handleDelete}
                          disabled={deleteEmployee.isPending}
                        >
                          {deleteEmployee.isPending ? (
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          ) : null}
                          Delete
                        </Button>
                      </DialogFooter>
                    </DialogContent>
                  </Dialog>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Activity */}
          <ActivityFeed employeeId={employee.id} />
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          <EmployeeInfoCard employee={employee} />
        </div>
      </div>
    </div>
  );
}
