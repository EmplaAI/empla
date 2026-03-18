import { Brain, AlertCircle } from 'lucide-react';
import { useBeliefs, type Belief } from '@empla/react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';

const TYPE_STYLES: Record<string, string> = {
  state: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
  event: 'bg-amber-500/10 text-amber-500 border-amber-500/20',
  causal: 'bg-violet-500/10 text-violet-500 border-violet-500/20',
  evaluative: 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20',
};

function formatValue(value: Record<string, unknown>): string {
  if ('value' in value) {
    const v = value.value;
    if (typeof v === 'number') return String(Math.round(v * 100) / 100);
    if (typeof v === 'boolean') return v ? 'true' : 'false';
    if (typeof v === 'string') return v;
  }
  const keys = Object.keys(value);
  if (keys.length === 0) return '{}';
  if (keys.length <= 2) {
    return keys.map((k) => `${k}: ${JSON.stringify(value[k])}`).join(', ');
  }
  return `{${keys.length} fields}`;
}

function BeliefItem({ belief }: { belief: Belief }) {
  const confidencePct = Math.round(belief.confidence * 100);

  return (
    <div className="rounded-lg border border-border/50 bg-muted/30 p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">
            <span className="text-primary">{belief.subject}</span>
            <span className="mx-1.5 text-muted-foreground">·</span>
            <span className="text-muted-foreground">{belief.predicate}</span>
          </p>
          <p className="mt-0.5 text-xs text-foreground/80 font-mono">
            {formatValue(belief.value)}
          </p>
        </div>
        <span className="shrink-0 text-xs font-mono text-muted-foreground">
          {confidencePct}%
        </span>
      </div>
      <div className="mt-2 flex items-center gap-2">
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-primary/60 transition-all"
            style={{ width: `${confidencePct}%` }}
          />
        </div>
        <span className={`inline-flex items-center rounded-full border px-1.5 py-0 text-[10px] font-medium ${TYPE_STYLES[belief.beliefType] ?? TYPE_STYLES.state}`}>
          {belief.beliefType}
        </span>
      </div>
    </div>
  );
}

function BeliefsPanelSkeleton() {
  return (
    <div className="space-y-3">
      {[1, 2, 3, 4, 5].map((i) => (
        <div key={i} className="rounded-lg border border-border/50 p-3 space-y-2">
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-3 w-1/3" />
          <Skeleton className="h-1.5 w-full rounded-full" />
        </div>
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-8 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full border border-border bg-muted/50">
        <Brain className="h-5 w-5 text-muted-foreground" />
      </div>
      <p className="mt-3 text-sm font-medium text-muted-foreground">No beliefs yet</p>
      <p className="text-xs text-muted-foreground">Beliefs form as the employee perceives and reasons</p>
    </div>
  );
}

export function BeliefsPanel({ employeeId }: { employeeId: string }) {
  const { data, isLoading, error, refetch } = useBeliefs(employeeId, {
    pageSize: 30,
    autoRefresh: true,
    interval: 30,
  });

  const beliefs = data?.items ?? [];

  return (
    <Card className="border-border/50 bg-card/80 backdrop-blur-sm">
      <CardHeader className="flex flex-row items-center justify-between pb-3">
        <CardTitle className="text-base font-display">
          Beliefs {data ? `(${data.total})` : ''}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <BeliefsPanelSkeleton />
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <AlertCircle className="h-5 w-5 text-destructive" />
            <p className="mt-2 text-sm text-muted-foreground">Failed to load beliefs</p>
            <Button variant="outline" size="sm" className="mt-3" onClick={() => refetch()}>
              Try again
            </Button>
          </div>
        ) : beliefs.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="space-y-2">
            {beliefs.map((belief) => (
              <BeliefItem key={belief.id} belief={belief} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
