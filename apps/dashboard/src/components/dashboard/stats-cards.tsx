import { Users, Play, Pause } from 'lucide-react';
import { useEmployees } from '@empla/react';
import { Card, CardContent } from '@/components/ui/card';
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

export function StatsCards() {
  const { data, isLoading } = useEmployees({ page: 1, pageSize: 100 });

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

  const employees = data?.items ?? [];
  const total = data?.total ?? 0;
  const active = employees.filter((e) => e.status === 'active').length;
  const running = employees.filter((e) => e.isRunning).length;
  const paused = employees.filter((e) => e.status === 'paused').length;

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      <StatCard
        title="Total Employees"
        value={total}
        description="Digital workforce size"
        icon={<Users className="h-5 w-5" />}
        color="cyan"
      />
      <StatCard
        title="Active"
        value={active}
        description="Ready to operate"
        icon={<Play className="h-5 w-5" />}
        color="green"
        pulse={active > 0}
      />
      <StatCard
        title="Running"
        value={running}
        description="Currently executing"
        icon={<Play className="h-5 w-5" />}
        color="cyan"
        pulse={running > 0}
      />
      <StatCard
        title="Paused"
        value={paused}
        description="On standby"
        icon={<Pause className="h-5 w-5" />}
        color="amber"
      />
    </div>
  );
}
