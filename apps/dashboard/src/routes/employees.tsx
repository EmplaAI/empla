import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Users, AlertCircle } from 'lucide-react';
import { toast } from 'sonner';
import {
  useEmployees,
  useEmployeeControl,
  type EmployeeStatus,
  type EmployeeRole,
  type Employee,
} from '@empla/react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Card, CardContent } from '@/components/ui/card';
import { EmployeeCard } from '@/components/employees/employee-card';
import { EmployeeFilters } from '@/components/employees/employee-filters';
import { Pagination } from '@/components/employees/pagination';

function EmployeeListSkeleton() {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className="rounded-lg border border-border/50 bg-card/80 p-4">
          <div className="flex items-start gap-4">
            <Skeleton className="h-12 w-12 rounded-full" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-5 w-32" />
              <Skeleton className="h-4 w-24" />
              <div className="flex gap-2">
                <Skeleton className="h-5 w-16 rounded-full" />
                <Skeleton className="h-5 w-20 rounded-full" />
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border py-16">
      <div className="flex h-16 w-16 items-center justify-center rounded-full border border-border bg-muted/50">
        <Users className="h-8 w-8 text-muted-foreground" />
      </div>
      <h3 className="mt-4 font-display text-lg font-semibold">No employees found</h3>
      <p className="mt-1 text-sm text-muted-foreground">
        Get started by creating your first digital employee
      </p>
      <Button className="mt-4" asChild>
        <Link to="/employees/new">
          <Plus className="mr-2 h-4 w-4" />
          Create Employee
        </Link>
      </Button>
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <Card className="border-destructive/50 bg-card/80">
      <CardContent className="flex flex-col items-center justify-center py-12">
        <div className="flex h-12 w-12 items-center justify-center rounded-full border border-destructive/30 bg-destructive/10">
          <AlertCircle className="h-6 w-6 text-destructive" />
        </div>
        <h3 className="mt-4 font-display text-lg font-semibold">Failed to load employees</h3>
        <p className="mt-1 text-sm text-muted-foreground">{message}</p>
        <Button variant="outline" className="mt-4" onClick={onRetry}>
          Try again
        </Button>
      </CardContent>
    </Card>
  );
}

/** Wrapper component that properly uses useEmployeeControl hook */
function EmployeeCardWithActions({
  employee,
  onActionComplete,
}: {
  employee: Employee;
  onActionComplete: () => void;
}) {
  const { start, stop, pause } = useEmployeeControl(employee.id);

  const handleStart = () => {
    start.mutate(undefined, {
      onSuccess: () => {
        toast.success('Employee started', {
          description: `${employee.name} is now running`,
        });
        onActionComplete();
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
        onActionComplete();
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
        onActionComplete();
      },
      onError: (error) => {
        toast.error('Failed to pause employee', {
          description: error instanceof Error ? error.message : 'Please try again',
        });
      },
    });
  };

  return (
    <EmployeeCard
      employee={employee}
      onStart={handleStart}
      onStop={handleStop}
      onPause={handlePause}
    />
  );
}

export function EmployeesPage() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<EmployeeStatus | 'all'>('all');
  const [role, setRole] = useState<EmployeeRole | 'all'>('all');

  // Reset page when filters change
  useEffect(() => {
    setPage(1);
  }, [status, role]);

  const { data, isLoading, error, refetch } = useEmployees({
    page,
    pageSize: 10,
    status: status === 'all' ? undefined : status,
    role: role === 'all' ? undefined : role,
  });

  const employees = data?.items ?? [];
  const totalPages = data?.pages ?? 1;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="font-display text-2xl font-bold tracking-tight">
            Digital Employees
          </h2>
          <p className="text-sm text-muted-foreground">
            {data?.total ?? 0} employees in your workforce
          </p>
        </div>

        <Button asChild>
          <Link to="/employees/new">
            <Plus className="mr-2 h-4 w-4" />
            New Employee
          </Link>
        </Button>
      </div>

      {/* Filters */}
      <EmployeeFilters
        status={status}
        role={role}
        onStatusChange={setStatus}
        onRoleChange={setRole}
      />

      {/* List */}
      {isLoading ? (
        <EmployeeListSkeleton />
      ) : error ? (
        <ErrorState
          message={error instanceof Error ? error.message : 'An unexpected error occurred'}
          onRetry={() => refetch()}
        />
      ) : employees.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {employees.map((employee) => (
            <EmployeeCardWithActions
              key={employee.id}
              employee={employee}
              onActionComplete={() => refetch()}
            />
          ))}
        </div>
      )}

      {/* Pagination */}
      <Pagination
        page={page}
        totalPages={totalPages}
        onPageChange={setPage}
      />
    </div>
  );
}
