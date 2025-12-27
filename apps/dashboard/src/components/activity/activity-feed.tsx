import { Link } from 'react-router-dom';
import { ArrowRight, Activity as ActivityIcon } from 'lucide-react';
import { useActivity, type Activity } from '@empla/react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { ActivityItem } from './activity-item';

interface ActivityFeedProps {
  limit?: number;
  employeeId?: string;
  showHeader?: boolean;
}

function ActivityFeedSkeleton() {
  return (
    <div className="space-y-3">
      {[1, 2, 3, 4, 5].map((i) => (
        <div key={i} className="flex items-start gap-3 p-2">
          <Skeleton className="h-8 w-8 rounded-lg" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-3 w-1/4" />
          </div>
        </div>
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-8 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full border border-border bg-muted/50">
        <ActivityIcon className="h-5 w-5 text-muted-foreground" />
      </div>
      <p className="mt-3 text-sm font-medium text-muted-foreground">
        No activity yet
      </p>
      <p className="text-xs text-muted-foreground">
        Activity will appear here as employees work
      </p>
    </div>
  );
}

export function ActivityFeed({ limit = 10, employeeId, showHeader = true }: ActivityFeedProps) {
  const { data, isLoading } = useActivity({
    employeeId,
    pageSize: limit,
    autoRefresh: true,
    interval: 30,
  });

  const activities: Activity[] = data?.items ?? [];

  return (
    <Card className="border-border/50 bg-card/80 backdrop-blur-sm">
      {showHeader && (
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <CardTitle className="text-base font-display">Recent Activity</CardTitle>
          <Button variant="ghost" size="sm" className="text-xs" asChild>
            <Link to="/activity">
              View all
              <ArrowRight className="ml-1 h-3 w-3" />
            </Link>
          </Button>
        </CardHeader>
      )}
      <CardContent className={showHeader ? '' : 'pt-6'}>
        {isLoading ? (
          <ActivityFeedSkeleton />
        ) : activities.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="space-y-1">
            {activities.map((activity) => (
              <ActivityItem
                key={activity.id}
                activity={activity}
                showEmployee={!employeeId}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
