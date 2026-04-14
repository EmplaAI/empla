import { useState } from 'react';
import {
  AlertCircle,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Clock,
  Lightbulb,
  Workflow,
  Zap,
} from 'lucide-react';
import {
  useEpisodicMemory,
  useProceduralMemory,
  useSemanticMemory,
  useWorkingMemory,
  type EpisodicMemoryItem,
  type ProceduralMemoryItem,
  type SemanticMemoryItem,
  type WorkingMemoryItem,
} from '@empla/react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';

const PAGE_SIZE = 30;

// ---------------------------------------------------------------------------
// Shared pieces
// ---------------------------------------------------------------------------

function PanelSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="rounded-lg border border-border/50 p-3 space-y-2">
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-3 w-1/3" />
        </div>
      ))}
    </div>
  );
}

function ErrorState({ onRetry, label }: { onRetry: () => void; label: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-8 text-center">
      <AlertCircle className="h-5 w-5 text-destructive" />
      <p className="mt-2 text-sm text-muted-foreground">Failed to load {label}</p>
      <Button variant="outline" size="sm" className="mt-3" onClick={onRetry}>
        Try again
      </Button>
    </div>
  );
}

function EmptyState({
  icon: Icon,
  title,
  description,
}: {
  icon: typeof BookOpen;
  title: string;
  description: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-8 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full border border-border bg-muted/50">
        <Icon className="h-5 w-5 text-muted-foreground" />
      </div>
      <p className="mt-3 text-sm font-medium text-muted-foreground">{title}</p>
      <p className="text-xs text-muted-foreground">{description}</p>
    </div>
  );
}

function Pager({
  page,
  totalPages,
  onChange,
}: {
  page: number;
  totalPages: number;
  onChange: (next: number) => void;
}) {
  if (totalPages <= 1) return null;
  return (
    <div className="flex items-center gap-1">
      <Button
        variant="ghost"
        size="icon"
        className="h-7 w-7"
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
      >
        <ChevronLeft className="h-4 w-4" />
      </Button>
      <span className="text-xs text-muted-foreground">
        {page}/{totalPages}
      </span>
      <Button
        variant="ghost"
        size="icon"
        className="h-7 w-7"
        disabled={page >= totalPages}
        onClick={() => onChange(page + 1)}
      >
        <ChevronRight className="h-4 w-4" />
      </Button>
    </div>
  );
}

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString();
}

function ImportanceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-primary/60 transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="shrink-0 font-mono text-xs text-muted-foreground">{pct}%</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Episodic
// ---------------------------------------------------------------------------

function EpisodicItem({ item }: { item: EpisodicMemoryItem }) {
  return (
    <div className="rounded-lg border border-border/50 bg-muted/30 p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">{item.description}</p>
          <p className="mt-0.5 font-mono text-xs text-muted-foreground">
            {item.episodeType} · {formatDate(item.occurredAt)}
          </p>
        </div>
      </div>
      <div className="mt-2">
        <ImportanceBar value={item.importance} />
      </div>
    </div>
  );
}

export function EpisodicMemoryPanel({ employeeId }: { employeeId: string }) {
  const [page, setPage] = useState(1);
  const { data, isLoading, error, refetch } = useEpisodicMemory(employeeId, {
    page,
    pageSize: PAGE_SIZE,
  });

  const items = data?.items ?? [];
  const totalPages = data?.pages ?? 1;

  return (
    <Card className="border-border/50 bg-card/80 backdrop-blur-sm">
      <CardHeader className="flex flex-row items-center justify-between pb-3">
        <CardTitle className="font-display text-base">
          Episodic {data ? `(${data.total})` : ''}
        </CardTitle>
        <Pager page={page} totalPages={totalPages} onChange={setPage} />
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <PanelSkeleton />
        ) : error ? (
          <ErrorState onRetry={() => refetch()} label="episodes" />
        ) : items.length === 0 ? (
          <EmptyState
            icon={BookOpen}
            title="No episodes yet"
            description="Your employee's actions and events will appear here once it starts working."
          />
        ) : (
          <div className="space-y-2">
            {items.map((item) => (
              <EpisodicItem key={item.id} item={item} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Semantic
// ---------------------------------------------------------------------------

function SemanticItem({ item }: { item: SemanticMemoryItem }) {
  const pct = Math.round(item.confidence * 100);
  return (
    <div className="rounded-lg border border-border/50 bg-muted/30 p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="font-mono text-xs text-foreground/80">
            <span className="text-primary">{item.subject}</span>
            <span className="mx-1.5 text-muted-foreground">·</span>
            <span className="text-muted-foreground">{item.predicate}</span>
            <span className="mx-1.5 text-muted-foreground">·</span>
            <span>{item.object}</span>
          </p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {item.factType}
            {item.verified ? ' · verified' : ''}
          </p>
        </div>
        <span className="shrink-0 font-mono text-xs text-muted-foreground">{pct}%</span>
      </div>
    </div>
  );
}

export function SemanticMemoryPanel({ employeeId }: { employeeId: string }) {
  const [page, setPage] = useState(1);
  const { data, isLoading, error, refetch } = useSemanticMemory(employeeId, {
    page,
    pageSize: PAGE_SIZE,
  });

  const items = data?.items ?? [];
  const totalPages = data?.pages ?? 1;

  return (
    <Card className="border-border/50 bg-card/80 backdrop-blur-sm">
      <CardHeader className="flex flex-row items-center justify-between pb-3">
        <CardTitle className="font-display text-base">
          Semantic {data ? `(${data.total})` : ''}
        </CardTitle>
        <Pager page={page} totalPages={totalPages} onChange={setPage} />
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <PanelSkeleton />
        ) : error ? (
          <ErrorState onRetry={() => refetch()} label="facts" />
        ) : items.length === 0 ? (
          <EmptyState
            icon={Lightbulb}
            title="Your employee hasn't learned any facts yet"
            description="Facts accumulate from interactions and observations."
          />
        ) : (
          <div className="space-y-2">
            {items.map((item) => (
              <SemanticItem key={item.id} item={item} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Procedural
// ---------------------------------------------------------------------------

function ProceduralItem({ item }: { item: ProceduralMemoryItem }) {
  const pct = Math.round(item.successRate * 100);
  return (
    <div className="rounded-lg border border-border/50 bg-muted/30 p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-2 text-sm font-medium">
            {item.name}
            {item.isPlaybook ? (
              <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-1.5 py-0 text-[10px] font-medium text-emerald-500">
                playbook
              </span>
            ) : null}
          </p>
          <p className="mt-0.5 text-xs text-muted-foreground">{item.description}</p>
          <p className="mt-1 font-mono text-[10px] text-muted-foreground">
            {item.procedureType} · {item.executionCount} runs ·{' '}
            {item.steps.length} steps
          </p>
        </div>
        <span className="shrink-0 font-mono text-xs text-muted-foreground">{pct}%</span>
      </div>
      <div className="mt-2">
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-emerald-500/60 transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>
    </div>
  );
}

export function ProceduralMemoryPanel({ employeeId }: { employeeId: string }) {
  const [page, setPage] = useState(1);
  const { data, isLoading, error, refetch } = useProceduralMemory(employeeId, {
    page,
    pageSize: PAGE_SIZE,
  });

  const items = data?.items ?? [];
  const totalPages = data?.pages ?? 1;

  return (
    <Card className="border-border/50 bg-card/80 backdrop-blur-sm">
      <CardHeader className="flex flex-row items-center justify-between pb-3">
        <CardTitle className="font-display text-base">
          Procedural {data ? `(${data.total})` : ''}
        </CardTitle>
        <Pager page={page} totalPages={totalPages} onChange={setPage} />
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <PanelSkeleton />
        ) : error ? (
          <ErrorState onRetry={() => refetch()} label="procedures" />
        ) : items.length === 0 ? (
          <EmptyState
            icon={Workflow}
            title="No procedures recorded"
            description="Playbooks will appear here after a few successful cycles."
          />
        ) : (
          <div className="space-y-2">
            {items.map((item) => (
              <ProceduralItem key={item.id} item={item} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Working
// ---------------------------------------------------------------------------

function WorkingItem({ item }: { item: WorkingMemoryItem }) {
  return (
    <div className="rounded-lg border border-border/50 bg-muted/30 p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium capitalize">{item.itemType}</p>
          <p className="mt-0.5 font-mono text-xs text-muted-foreground">
            {Object.keys(item.content).length > 0
              ? Object.entries(item.content)
                  .slice(0, 3)
                  .map(([k, v]) => `${k}: ${typeof v === 'string' ? v : JSON.stringify(v)}`)
                  .join(' · ')
              : '—'}
          </p>
          {item.lastAccessedAt ? (
            <p className="mt-1 flex items-center gap-1 text-[10px] text-muted-foreground">
              <Clock className="h-3 w-3" />
              {formatDate(item.lastAccessedAt)}
            </p>
          ) : null}
        </div>
      </div>
      <div className="mt-2">
        <ImportanceBar value={item.importance} />
      </div>
    </div>
  );
}

export function WorkingMemoryPanel({ employeeId }: { employeeId: string }) {
  const { data, isLoading, error, refetch } = useWorkingMemory(employeeId, {
    autoRefresh: true,
    interval: 30,
  });

  const items = data?.items ?? [];

  return (
    <Card className="border-border/50 bg-card/80 backdrop-blur-sm">
      <CardHeader className="flex flex-row items-center justify-between pb-3">
        <CardTitle className="font-display text-base">
          Working {data ? `(${data.total})` : ''}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <PanelSkeleton rows={3} />
        ) : error ? (
          <ErrorState onRetry={() => refetch()} label="working memory" />
        ) : items.length === 0 ? (
          <EmptyState
            icon={Zap}
            title="Idle"
            description="No active focus right now."
          />
        ) : (
          <div className="space-y-2">
            {items.map((item) => (
              <WorkingItem key={item.id} item={item} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
