import { DollarSign, Zap, Hash } from 'lucide-react';
import { useCostSummary, useCostHistory } from '@empla/react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

function StatCard({
  label,
  value,
  icon: Icon,
  subtitle,
}: {
  label: string;
  value: string;
  icon: React.ElementType;
  subtitle?: string;
}) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border/50 bg-muted/30 p-3">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary/10">
        <Icon className="h-5 w-5 text-primary" />
      </div>
      <div>
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-lg font-semibold">{value}</p>
        {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
      </div>
    </div>
  );
}

function CostBar({ cost, maxCost }: { cost: number; maxCost: number }) {
  const width = maxCost > 0 ? Math.min(100, (cost / maxCost) * 100) : 0;
  return (
    <div className="h-2 w-full rounded-full bg-muted">
      <div
        className="h-2 rounded-full bg-primary transition-all"
        style={{ width: `${width}%` }}
      />
    </div>
  );
}

function CostPanelSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="flex items-center gap-3 rounded-lg border border-border/50 p-3">
            <Skeleton className="h-10 w-10 rounded-md" />
            <div className="space-y-1">
              <Skeleton className="h-3 w-16" />
              <Skeleton className="h-5 w-12" />
            </div>
          </div>
        ))}
      </div>
      <Skeleton className="h-40 w-full" />
    </div>
  );
}

export function CostPanel({ employeeId }: { employeeId: string }) {
  const { data: summary, isLoading: summaryLoading } = useCostSummary(employeeId, {
    hours: 24,
    autoRefresh: true,
    interval: 60,
  });
  const { data: history, isLoading: historyLoading } = useCostHistory(employeeId, {
    hours: 24,
  });

  if (summaryLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <DollarSign className="h-4 w-4" /> LLM Costs (24h)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <CostPanelSkeleton />
        </CardContent>
      </Card>
    );
  }

  if (!summary) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <DollarSign className="h-4 w-4" /> LLM Costs (24h)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="py-8 text-center text-sm text-muted-foreground">
            No cost data available yet. Costs are recorded after each BDI cycle.
          </p>
        </CardContent>
      </Card>
    );
  }

  const maxCost = history?.items.length
    ? Math.max(...history.items.map((h) => h.costUsd))
    : 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <DollarSign className="h-4 w-4" /> LLM Costs (24h)
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Summary stats */}
        <div className="grid grid-cols-3 gap-3">
          <StatCard
            label="Total Cost"
            value={`$${summary.totalCostUsd.toFixed(4)}`}
            icon={DollarSign}
            subtitle={`${summary.totalCycles} cycles`}
          />
          <StatCard
            label="Avg / Cycle"
            value={`$${summary.avgCostPerCycle.toFixed(4)}`}
            icon={Zap}
          />
          <StatCard
            label="Tokens"
            value={formatTokens(summary.totalInputTokens + summary.totalOutputTokens)}
            icon={Hash}
            subtitle={`${formatTokens(summary.totalInputTokens)} in / ${formatTokens(summary.totalOutputTokens)} out`}
          />
        </div>

        {/* Cost per cycle history */}
        {!historyLoading && history && history.items.length > 0 && (
          <div>
            <p className="mb-2 text-xs font-medium text-muted-foreground">
              Cost per cycle (recent {history.items.length})
            </p>
            <div className="space-y-1.5">
              {history.items.slice(0, 20).map((item, i) => (
                <div key={i} className="flex items-center gap-2">
                  <span className="w-16 text-right text-xs text-muted-foreground">
                    ${item.costUsd.toFixed(4)}
                  </span>
                  <CostBar cost={item.costUsd} maxCost={maxCost} />
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
}
