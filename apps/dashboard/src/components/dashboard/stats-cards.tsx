import { useMemo } from 'react';
import { Users, Play, Pause, AlertCircle } from 'lucide-react';
import { useEmployees } from '@empla/react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

interface StatCardProps {
  title: string;
  value: number | string;
  description?: string;
  icon: React.ReactNode;
  color: 'cyan' | 'green' | 'amber' | 'gray';
  pulse?: boolean;
}

function StatCard({ title, value, description, icon, color, pulse }: StatCardProps) {
  const colorClasses = {
    cyan: 'text-status-running border-status-running/30 bg-status-running/10',
    green: 'text-status-active border-status-active/30 bg-status-active/10',
    amber: 'text-status-paused border-status-paused/30 bg-status-paused/10',
    gray: 'text-status-stopped border-status-stopped/30 bg-status-stopped/10',
  };

  const glowClasses = {
    cyan: 'glow-cyan',
    green: 'glow-green',
    amber: 'glow-amber',
    gray: '',
  };

  return (
    <Card className="relative overflow-hidden border-border/50 bg-card/80 backdrop-blur-sm transition-all duration-300 hover:border-border">
      <CardContent className="p-6">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <p className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
              {title}
            </p>
            <p className="font-display text-3xl font-bold tracking-tight">
              {value}
            </p>
            {description && (
              <p className="text-xs text-muted-foreground">{description}</p>
            )}
          </div>
          <div
            className={cn(
              'flex h-12 w-12 items-center justify-center rounded-lg border',
              colorClasses[color],
              pulse && glowClasses[color],
              pulse && 'animate-pulse'
            )}
          >
            {icon}
          </div>
        </div>

        {/* Decorative line */}
        <div
          className={cn(
            'absolute bottom-0 left-0 h-0.5 w-full opacity-50',
            color === 'cyan' && 'bg-gradient-to-r from-transparent via-status-running to-transparent',
            color === 'green' && 'bg-gradient-to-r from-transparent via-status-active to-transparent',
            color === 'amber' && 'bg-gradient-to-r from-transparent via-status-paused to-transparent',
            color === 'gray' && 'bg-gradient-to-r from-transparent via-status-stopped to-transparent'
          )}
        />
      </CardContent>
    </Card>
  );
}

function StatCardSkeleton() {
  return (
    <Card className="border-border/50 bg-card/80">
      <CardContent className="p-6">
        <div className="flex items-start justify-between">
          <div className="space-y-2">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-8 w-16" />
          </div>
          <Skeleton className="h-12 w-12 rounded-lg" />
        </div>
      </CardContent>
    </Card>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <Card className="border-destructive/50 bg-card/80 col-span-full">
      <CardContent className="flex flex-col items-center justify-center py-8">
        <div className="flex h-12 w-12 items-center justify-center rounded-full border border-destructive/30 bg-destructive/10">
          <AlertCircle className="h-6 w-6 text-destructive" />
        </div>
        <p className="mt-3 text-sm font-medium">Failed to load stats</p>
        <p className="text-xs text-muted-foreground">{message}</p>
        <Button variant="outline" size="sm" className="mt-3" onClick={onRetry}>
          Try again
        </Button>
      </CardContent>
    </Card>
  );
}

export function StatsCards() {
  // Fetch employees to compute stats (API max page_size is 100)
  const { data, isLoading, error, refetch } = useEmployees({ page: 1, pageSize: 100 });

  const stats = useMemo(() => {
    const employees = data?.items ?? [];
    const total = data?.total ?? 0;
    // If we fetched fewer employees than total, status counts are approximate
    const isApproximate = employees.length < total;
    return {
      total,
      active: employees.filter((e) => e.status === 'active').length,
      running: employees.filter((e) => e.isRunning).length,
      paused: employees.filter((e) => e.status === 'paused').length,
      isApproximate,
    };
  }, [data]);

  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCardSkeleton />
        <StatCardSkeleton />
        <StatCardSkeleton />
        <StatCardSkeleton />
      </div>
    );
  }

  if (error) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <ErrorState
          message={error instanceof Error ? error.message : 'An unexpected error occurred'}
          onRetry={() => refetch()}
        />
      </div>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      <StatCard
        title="Total Employees"
        value={stats.total}
        description="Digital workforce size"
        icon={<Users className="h-5 w-5" />}
        color="cyan"
      />
      <StatCard
        title="Active"
        value={stats.isApproximate ? `~${stats.active}` : stats.active}
        description="Ready to operate"
        icon={<Play className="h-5 w-5" />}
        color="green"
        pulse={stats.active > 0}
      />
      <StatCard
        title="Running"
        value={stats.isApproximate ? `~${stats.running}` : stats.running}
        description="Currently executing"
        icon={<Play className="h-5 w-5" />}
        color="cyan"
        pulse={stats.running > 0}
      />
      <StatCard
        title="Paused"
        value={stats.isApproximate ? `~${stats.paused}` : stats.paused}
        description="On standby"
        icon={<Pause className="h-5 w-5" />}
        color="amber"
      />
    </div>
  );
}
