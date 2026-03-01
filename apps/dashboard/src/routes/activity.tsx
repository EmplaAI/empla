import { useState } from 'react';
import { Activity as ActivityIcon, AlertCircle, Loader2 } from 'lucide-react';
import { useActivity, useActivitySummary } from '@empla/react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ActivityItem } from '@/components/activity/activity-item';
import { ActivityFilters } from '@/components/activity/activity-filters';
import { Pagination } from '@/components/employees/pagination';

const HOURS_FOR_RANGE: Record<string, number> = {
  '24h': 24,
  '7d': 168,
  '30d': 720,
};

function timeRangeToSince(range: string): string | undefined {
  const hours = HOURS_FOR_RANGE[range];
  if (!hours) return undefined;
  const now = new Date();
  return new Date(now.getTime() - hours * 60 * 60 * 1000).toISOString();
}

function timeRangeToHours(range: string): number | undefined {
  return HOURS_FOR_RANGE[range];
}

function importanceToMin(importance: string): number | undefined {
  if (importance === 'high') return 0.8;
  if (importance === 'medium') return 0.5;
  return undefined;
}

export function ActivityPage() {
  const [page, setPage] = useState(1);
  const [eventType, setEventType] = useState('all');
  const [importance, setImportance] = useState('all');
  const [timeRange, setTimeRange] = useState('24h');

  const resetPage = () => setPage(1);

  const { data: summary } = useActivitySummary({
    hours: timeRangeToHours(timeRange),
  });

  const { data, isLoading, isError, error } = useActivity({
    page,
    pageSize: 20,
    eventType: eventType === 'all' ? undefined : eventType,
    minImportance: importanceToMin(importance),
    since: timeRangeToSince(timeRange),
    autoRefresh: true,
    interval: 30,
  });

  const totalEvents = summary?.total ?? 0;
  const startedCount = summary?.eventCounts?.started ?? 0;
  const errorCount = summary?.eventCounts?.error ?? 0;
  const completedCount = summary?.eventCounts?.completed ?? 0;

  return (
    <div className="space-y-6">
      {/* Summary stats */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Total Events" value={totalEvents} />
        <StatCard label="Started" value={startedCount} />
        <StatCard label="Errors" value={errorCount} variant={errorCount > 0 ? 'error' : 'default'} />
        <StatCard label="Completed" value={completedCount} />
      </div>

      {/* Filters */}
      <ActivityFilters
        eventType={eventType}
        importance={importance}
        timeRange={timeRange}
        onEventTypeChange={(v) => { setEventType(v); resetPage(); }}
        onImportanceChange={(v) => { setImportance(v); resetPage(); }}
        onTimeRangeChange={(v) => { setTimeRange(v); resetPage(); }}
      />

      {/* Activity list */}
      <Card className="border-border/50 bg-card/80 backdrop-blur-sm">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base font-display">
            <ActivityIcon className="h-4 w-4 text-primary" />
            Activity Feed
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isError ? (
            <div className="flex flex-col items-center justify-center py-12">
              <AlertCircle className="h-8 w-8 text-destructive" />
              <p className="mt-3 text-sm text-destructive">
                Failed to load activity: {error?.message ?? 'Unknown error'}
              </p>
            </div>
          ) : isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : data?.items && data.items.length > 0 ? (
            <div className="space-y-1">
              {data.items.map((activity) => (
                <ActivityItem key={activity.id} activity={activity} />
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-12">
              <ActivityIcon className="h-8 w-8 text-muted-foreground" />
              <p className="mt-3 text-sm text-muted-foreground">
                No activity found for the selected filters
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
      {data && data.pages > 1 && (
        <Pagination
          page={page}
          totalPages={data.pages}
          onPageChange={setPage}
        />
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  variant = 'default',
}: {
  label: string;
  value: number;
  variant?: 'default' | 'error';
}) {
  return (
    <div className="rounded-lg border border-border/50 bg-card/80 p-4 backdrop-blur-sm">
      <p className="font-mono text-xs uppercase tracking-wider text-muted-foreground">
        {label}
      </p>
      <p
        className={
          variant === 'error' && value > 0
            ? 'mt-1 font-mono text-2xl font-bold text-status-error'
            : 'mt-1 font-mono text-2xl font-bold text-foreground'
        }
      >
        {value.toLocaleString()}
      </p>
    </div>
  );
}
