import { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { AlertCircle, PlugZap, Shield, ShieldCheck, Wrench } from 'lucide-react';
import { useTools, useBlockedTools, type ToolCatalogItem } from '@empla/react';
import type { UseQueryResult } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';

const STATUS_STYLES: Record<string, string> = {
  healthy: 'border-status-active/20 bg-status-active/10 text-status-active',
  degraded: 'border-status-paused/20 bg-status-paused/10 text-status-paused',
  down: 'border-status-error/20 bg-status-error/10 text-status-error',
  unknown: 'border-border/50 bg-muted/40 text-muted-foreground',
};

// ---------------------------------------------------------------------------
// Generic <DataPanel> shell — handles loading / offline / error / empty.
// All Phase 5 panels render through this so they get the same behaviors.
// ---------------------------------------------------------------------------

function isOfflineError(error: unknown): boolean {
  if (error && typeof error === 'object' && 'status' in error) {
    const status = (error as { status?: number }).status;
    return status === 503 || status === 502 || status === 504;
  }
  return false;
}

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
    <div className="flex flex-col items-center justify-center py-10 text-center">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full border border-destructive/30 bg-destructive/10">
        <AlertCircle className="h-6 w-6 text-destructive" />
      </div>
      <h3 className="font-display text-lg">Something went wrong</h3>
      <p className="mt-2 max-w-sm text-sm text-muted-foreground">Failed to load {label}.</p>
      <Button variant="outline" className="mt-4" onClick={onRetry}>
        Try again
      </Button>
    </div>
  );
}

function OfflineState({ children }: { children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center py-10 text-center">
      <PlugZap className="mb-4 h-10 w-10 text-muted-foreground/60" />
      <h3 className="font-display text-lg">Employee not running</h3>
      <p className="mt-2 max-w-sm text-sm text-muted-foreground">
        Tool data is read live from the running employee. Start the employee to see what
        tools it has available, integration health, and trust-boundary blocks.
      </p>
      {children}
    </div>
  );
}

interface DataPanelProps<T> {
  title: ReactNode;
  query: UseQueryResult<T, Error>;
  errorLabel: string;
  emptyState: ReactNode;
  isEmpty: (data: T) => boolean;
  renderContent: (data: T) => ReactNode;
  skeletonRows?: number;
}

function DataPanel<T>({
  title,
  query,
  errorLabel,
  emptyState,
  isEmpty,
  renderContent,
  skeletonRows = 5,
}: DataPanelProps<T>) {
  const { data, isLoading, error, refetch } = query;
  return (
    <Card className="border-border/50 bg-card/80 backdrop-blur-sm">
      <CardHeader className="flex flex-row items-center justify-between pb-3">
        <CardTitle className="font-display text-lg font-semibold">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <PanelSkeleton rows={skeletonRows} />
        ) : isOfflineError(error) ? (
          <OfflineState />
        ) : error ? (
          <ErrorState onRetry={() => refetch()} label={errorLabel} />
        ) : !data || isEmpty(data) ? (
          <>{emptyState}</>
        ) : (
          renderContent(data)
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// ToolsPanel — uses the embedded `health` map from the catalog response,
// so we render N tool rows without firing N health requests.
// ---------------------------------------------------------------------------

function ToolRow({
  item,
  health,
}: {
  item: ToolCatalogItem;
  health: { status: string; totalCalls?: number; errorRate?: number; avgLatencyMs?: number } | undefined;
}) {
  const status = health?.status ?? 'unknown';
  return (
    <div className="rounded-lg border border-border/50 bg-muted/30 p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="font-mono text-sm">
            <span className="text-primary">{item.name}</span>
          </p>
          {item.description ? (
            <p className="mt-0.5 text-xs text-muted-foreground">{item.description}</p>
          ) : null}
        </div>
        <span
          className={`shrink-0 rounded-full border px-2 py-0 text-[10px] font-medium ${STATUS_STYLES[status] ?? STATUS_STYLES.unknown}`}
        >
          {status}
        </span>
      </div>
      {health && (health.totalCalls ?? 0) > 0 ? (
        <p className="mt-1.5 font-mono text-[10px] text-muted-foreground">
          {health.totalCalls} calls · {Math.round((1 - (health.errorRate ?? 0)) * 100)}% success
          {' · '}
          {Math.round(health.avgLatencyMs ?? 0)}ms avg
        </p>
      ) : null}
    </div>
  );
}

export function ToolsPanel({ employeeId }: { employeeId: string }) {
  const query = useTools(employeeId);
  return (
    <DataPanel
      title={
        <>
          <Wrench className="mr-2 inline h-4 w-4 text-muted-foreground" />
          Tools {query.data ? `(${query.data.total})` : ''}
        </>
      }
      query={query}
      errorLabel="tool catalog"
      isEmpty={(d) => d.items.length === 0}
      emptyState={
        <div className="flex flex-col items-center justify-center py-10 text-center">
          <Wrench className="mb-4 h-10 w-10 text-muted-foreground/60" />
          <h3 className="font-display text-lg">No tools attached yet</h3>
          <p className="mt-2 max-w-sm text-sm text-muted-foreground">
            Connect an integration on the Integrations page to give this employee tools to
            call.
          </p>
          <Button asChild variant="outline" className="mt-4">
            <Link to="/integrations">Connect an integration</Link>
          </Button>
        </div>
      }
      renderContent={(d) => (
        <div className="space-y-2">
          {d.items.map((item) => (
            <ToolRow
              key={item.name}
              item={item}
              health={item.integration ? d.health?.[item.integration] : undefined}
            />
          ))}
        </div>
      )}
    />
  );
}

// ---------------------------------------------------------------------------
// BlockedToolsPanel
// ---------------------------------------------------------------------------

export function BlockedToolsPanel({ employeeId }: { employeeId: string }) {
  const query = useBlockedTools(employeeId, { autoRefresh: true, interval: 30 });
  return (
    <DataPanel
      title={
        <>
          <Shield className="mr-2 inline h-4 w-4 text-muted-foreground" />
          Trust boundary {query.data ? `(${query.data.total} blocked)` : ''}
        </>
      }
      query={query}
      errorLabel="trust boundary"
      skeletonRows={3}
      isEmpty={(d) => d.items.length === 0}
      emptyState={
        <div className="flex flex-col items-center justify-center py-10 text-center">
          <ShieldCheck className="mb-4 h-10 w-10 text-muted-foreground/60" />
          <h3 className="font-display text-lg">No tools blocked this cycle</h3>
          <p className="mt-2 max-w-sm text-sm text-muted-foreground">
            Tools that violate trust rules are blocked here. An empty list means the employee
            is operating cleanly.
            {query.data?.stats ? (
              <>
                {' '}
                This cycle: {query.data.stats.allowed} allowed, {query.data.stats.denied} denied.
              </>
            ) : null}
          </p>
        </div>
      }
      renderContent={(d) => (
        <div className="space-y-2">
          {d.items.map((b, i) => (
            <div
              key={`${b.toolName}-${b.timestamp}-${i}`}
              className="rounded-lg border border-status-error/20 bg-status-error/5 p-3"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <p className="font-mono text-sm text-status-error">{b.toolName}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">{b.reason}</p>
                </div>
                {b.employeeRole ? (
                  <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
                    role: {b.employeeRole}
                  </span>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      )}
    />
  );
}
