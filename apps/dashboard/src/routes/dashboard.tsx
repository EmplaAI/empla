import { StatsCards } from '@/components/dashboard/stats-cards';
import { QuickActions } from '@/components/dashboard/quick-actions';
import { ActivityFeed } from '@/components/activity/activity-feed';

export function DashboardPage() {
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

          {/* System status card */}
          <div className="rounded-lg border border-border/50 bg-card/80 p-4 backdrop-blur-sm">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-status-active/30 bg-status-active/10">
                <div className="h-3 w-3 rounded-full bg-status-active animate-pulse" />
              </div>
              <div>
                <p className="font-mono text-xs uppercase tracking-wider text-muted-foreground">
                  System Status
                </p>
                <p className="text-sm font-medium text-status-active">
                  All Systems Operational
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
