import { useParams, useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, Trash2, Edit, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { useEmployee, useDeleteEmployee } from '@empla/react';
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

export function EmployeeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: employee, isLoading, error, refetch } = useEmployee(id!);
  const deleteEmployee = useDeleteEmployee();

  const handleDelete = () => {
    if (!id) return;
    deleteEmployee.mutate(id, {
      onSuccess: () => {
        toast.success('Employee deleted');
        navigate('/employees');
      },
      onError: () => {
        toast.error('Failed to delete employee');
      },
    });
  };

  if (isLoading) {
    return <EmployeeDetailSkeleton />;
  }

  if (error || !employee) {
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
