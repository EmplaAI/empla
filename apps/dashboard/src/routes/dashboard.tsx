import { useActivitySummary } from '@empla/react';
import { StatsCards } from '@/components/dashboard/stats-cards';
import { QuickActions } from '@/components/dashboard/quick-actions';
import { ActivityFeed } from '@/components/activity/activity-feed';

export function DashboardPage() {
  const { data: summary } = useActivitySummary({ hours: 24 });

  const totalEvents = summary?.total ?? 0;
  const errorCount = summary?.eventCounts?.error ?? 0;

  return (
    <div className="space-y-6">
      {/* Stats overview */}
      <StatsCards />

      {/* Main content grid */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Activity feed - takes 2 columns */}
        <div className="lg:col-span-2">
          <ActivityFeed limit={10} />
        </div>

        {/* Sidebar - quick actions */}
        <div className="space-y-6">
          <QuickActions />

          {/* Activity summary (last 24h) */}
          <div className="rounded-lg border border-border/50 bg-card/80 p-4 backdrop-blur-sm">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-status-active/30 bg-status-active/10">
                <div className="h-3 w-3 rounded-full bg-status-active animate-pulse" />
              </div>
              <div>
                <p className="font-mono text-xs uppercase tracking-wider text-muted-foreground">
                  Last 24 Hours
                </p>
                <p className="text-sm font-medium text-foreground">
                  {totalEvents} event{totalEvents !== 1 ? 's' : ''}
                  {errorCount > 0 && (
                    <span className="ml-2 text-status-error">
                      ({errorCount} error{errorCount !== 1 ? 's' : ''})
                    </span>
                  )}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
