import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Users } from 'lucide-react';
import { toast } from 'sonner';
import { useEmployees, useEmployeeControl, type EmployeeStatus, type EmployeeRole } from '@empla/react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
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

export function EmployeesPage() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<EmployeeStatus | 'all'>('all');
  const [role, setRole] = useState<EmployeeRole | 'all'>('all');

  // Reset page when filters change
  useEffect(() => {
    setPage(1);
  }, [status, role]);

  const { data, isLoading, refetch } = useEmployees({
    page,
    pageSize: 10,
    status: status === 'all' ? undefined : status,
    role: role === 'all' ? undefined : role,
  });

  // For employee controls
  const EmployeeActions = ({ employeeId }: { employeeId: string }) => {
    const { start, stop, pause } = useEmployeeControl(employeeId);

    const handleStart = async () => {
      try {
        await start.mutateAsync();
        toast.success('Employee started');
        refetch();
      } catch {
        toast.error('Failed to start employee');
      }
    };

    const handleStop = async () => {
      try {
        await stop.mutateAsync();
        toast.success('Employee stopped');
        refetch();
      } catch {
        toast.error('Failed to stop employee');
      }
    };

    const handlePause = async () => {
      try {
        await pause.mutateAsync();
        toast.success('Employee paused');
        refetch();
      } catch {
        toast.error('Failed to pause employee');
      }
    };

    return { onStart: handleStart, onStop: handleStop, onPause: handlePause };
  };

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
      ) : employees.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {employees.map((employee) => {
            const actions = EmployeeActions({ employeeId: employee.id });
            return (
              <EmployeeCard
                key={employee.id}
                employee={employee}
                onStart={actions.onStart}
                onStop={actions.onStop}
                onPause={actions.onPause}
              />
            );
          })}
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
