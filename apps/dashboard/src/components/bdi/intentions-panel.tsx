import { useState } from 'react';
import { Zap, AlertCircle, ChevronLeft, ChevronRight } from 'lucide-react';
import { useIntentions, type EmployeeIntention } from '@empla/react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';

const PAGE_SIZE = 20;

const STATUS_STYLES: Record<string, string> = {
  planned: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
  in_progress: 'bg-amber-500/10 text-amber-500 border-amber-500/20',
  completed: 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20',
  failed: 'bg-red-500/10 text-red-500 border-red-500/20',
  abandoned: 'bg-muted text-muted-foreground border-border',
};

const TYPE_STYLES: Record<string, string> = {
  action: 'bg-cyan-500/10 text-cyan-500 border-cyan-500/20',
  tactic: 'bg-violet-500/10 text-violet-500 border-violet-500/20',
  strategy: 'bg-orange-500/10 text-orange-500 border-orange-500/20',
};

function IntentionItem({ intention }: { intention: EmployeeIntention }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-border/50 bg-muted/30 p-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary/10 font-mono text-xs font-bold text-primary">
        P{intention.priority}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium leading-snug">{intention.description}</p>
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium ${STATUS_STYLES[intention.status] ?? STATUS_STYLES.planned}`}>
            {intention.status.replace('_', ' ')}
          </span>
          <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium ${TYPE_STYLES[intention.intentionType] ?? TYPE_STYLES.action}`}>
            {intention.intentionType}
          </span>
        </div>
      </div>
    </div>
  );
}

function IntentionsPanelSkeleton() {
  return (
    <div className="space-y-3">
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className="flex items-start gap-3 rounded-lg border border-border/50 p-3">
          <Skeleton className="h-8 w-8 rounded-md" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-3 w-1/3" />
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
        <Zap className="h-5 w-5 text-muted-foreground" />
      </div>
      <p className="mt-3 text-sm font-medium text-muted-foreground">No intentions yet</p>
      <p className="text-xs text-muted-foreground">Intentions are generated from goals during planning</p>
    </div>
  );
}

export function IntentionsPanel({ employeeId }: { employeeId: string }) {
  const [page, setPage] = useState(1);
  const { data, isLoading, error, refetch } = useIntentions(employeeId, {
    page,
    pageSize: PAGE_SIZE,
    autoRefresh: true,
    interval: 30,
  });

  const intentions = data?.items ?? [];
  const totalPages = data?.pages ?? 1;

  return (
    <Card className="border-border/50 bg-card/80 backdrop-blur-sm">
      <CardHeader className="flex flex-row items-center justify-between pb-3">
        <CardTitle className="text-base font-display">
          Intentions {data ? `(${data.total})` : ''}
        </CardTitle>
        {totalPages > 1 && (
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="icon" className="h-7 w-7" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="text-xs text-muted-foreground">{page}/{totalPages}</span>
            <Button variant="ghost" size="icon" className="h-7 w-7" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        )}
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <IntentionsPanelSkeleton />
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <AlertCircle className="h-5 w-5 text-destructive" />
            <p className="mt-2 text-sm text-muted-foreground">Failed to load intentions</p>
            <Button variant="outline" size="sm" className="mt-3" onClick={() => refetch()}>
              Try again
            </Button>
          </div>
        ) : intentions.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="space-y-2">
            {intentions.map((intention) => (
              <IntentionItem key={intention.id} intention={intention} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
