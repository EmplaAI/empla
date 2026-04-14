import { AlertCircle, PlugZap, Shield, Wrench, Activity } from 'lucide-react';
import {
  useBlockedTools,
  useToolHealth,
  useTools,
  type ToolCatalogItem,
} from '@empla/react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';

const STATUS_STYLES: Record<string, string> = {
  healthy: 'border-status-active/20 bg-status-active/10 text-status-active',
  degraded: 'border-status-paused/20 bg-status-paused/10 text-status-paused',
  down: 'border-status-error/20 bg-status-error/10 text-status-error',
  unknown: 'border-border/50 bg-muted/40 text-muted-foreground',
};

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

function isOfflineError(error: unknown): boolean {
  // ApiError exposes status; runner-offline → 503/502/504
  if (error && typeof error === 'object' && 'status' in error) {
    const status = (error as { status?: number }).status;
    return status === 503 || status === 502 || status === 504;
  }
  return false;
}

function OfflineState({ children }: { children?: React.ReactNode }) {
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

function GenericErrorState({
  onRetry,
  label,
}: {
  onRetry: () => void;
  label: string;
}) {
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

// ---------------------------------------------------------------------------
// Tool catalog (with on-demand health for the integration prefix)
// ---------------------------------------------------------------------------

function ToolRow({
  item,
  employeeId,
}: {
  item: ToolCatalogItem;
  employeeId: string;
}) {
  // Only fetch health for namespaced tools (integration.tool); standalone
  // tools have no integration to report on.
  const integration = item.integration;
  const { data } = useToolHealth(employeeId, item.name, {
    enabled: !!integration,
  });

  const status = data?.status ?? 'unknown';
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
      {data && data.totalCalls > 0 ? (
        <p className="mt-1.5 font-mono text-[10px] text-muted-foreground">
          {data.totalCalls} calls · {Math.round((1 - data.errorRate) * 100)}% success ·{' '}
          {Math.round(data.avgLatencyMs)}ms avg
        </p>
      ) : null}
    </div>
  );
}

export function ToolsPanel({ employeeId }: { employeeId: string }) {
  const { data, isLoading, error, refetch } = useTools(employeeId);

  return (
    <Card className="border-border/50 bg-card/80 backdrop-blur-sm">
      <CardHeader className="flex flex-row items-center justify-between pb-3">
        <CardTitle className="font-display text-lg font-semibold">
          <Wrench className="mr-2 inline h-4 w-4 text-muted-foreground" />
          Tools {data ? `(${data.total})` : ''}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <PanelSkeleton />
        ) : isOfflineError(error) ? (
          <OfflineState />
        ) : error ? (
          <GenericErrorState onRetry={() => refetch()} label="tool catalog" />
        ) : !data || data.items.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 text-center">
            <Wrench className="mb-4 h-10 w-10 text-muted-foreground/60" />
            <h3 className="font-display text-lg">No tools attached yet</h3>
            <p className="mt-2 max-w-sm text-sm text-muted-foreground">
              Connect an integration on the Integrations page to give this employee tools
              to call.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {data.items.map((item) => (
              <ToolRow key={item.name} item={item} employeeId={employeeId} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Trust-boundary blocks
// ---------------------------------------------------------------------------

export function BlockedToolsPanel({ employeeId }: { employeeId: string }) {
  const { data, isLoading, error, refetch } = useBlockedTools(employeeId, {
    autoRefresh: true,
    interval: 30,
  });

  return (
    <Card className="border-border/50 bg-card/80 backdrop-blur-sm">
      <CardHeader className="flex flex-row items-center justify-between pb-3">
        <CardTitle className="font-display text-lg font-semibold">
          <Shield className="mr-2 inline h-4 w-4 text-muted-foreground" />
          Trust boundary {data ? `(${data.total} blocked)` : ''}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <PanelSkeleton rows={3} />
        ) : isOfflineError(error) ? (
          <OfflineState />
        ) : error ? (
          <GenericErrorState onRetry={() => refetch()} label="trust boundary" />
        ) : !data || data.items.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 text-center">
            <Activity className="mb-4 h-10 w-10 text-muted-foreground/60" />
            <h3 className="font-display text-lg">No tools blocked this cycle</h3>
            <p className="mt-2 max-w-sm text-sm text-muted-foreground">
              Tools that violate trust rules are blocked here. An empty list means the
              employee is operating cleanly.
              {data?.stats ? (
                <>
                  {' '}
                  This cycle: {data.stats.allowed} allowed, {data.stats.denied} denied.
                </>
              ) : null}
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {data.items.map((b, i) => (
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
      </CardContent>
    </Card>
  );
}
