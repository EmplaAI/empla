import { BookOpen, TrendingUp, Award, Clock } from 'lucide-react';
import { usePlaybooks, usePlaybookStats } from '@empla/react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

const LEARNED_FROM_LABELS: Record<string, string> = {
  human_demonstration: 'Human Demo',
  trial_and_error: 'Trial & Error',
  instruction: 'Instruction',
  autonomous_discovery: 'Discovered',
};

function SuccessBar({ rate }: { rate: number }) {
  const pct = Math.round(rate * 100);
  const color =
    pct >= 80 ? 'bg-emerald-500' : pct >= 60 ? 'bg-amber-500' : 'bg-red-500';
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-20 rounded-full bg-muted">
        <div
          className={`h-2 rounded-full ${color} transition-all`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs tabular-nums">{pct}%</span>
    </div>
  );
}

function StatBadge({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string | number;
  icon: React.ElementType;
}) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-border/50 bg-muted/30 px-3 py-2">
      <Icon className="h-4 w-4 text-muted-foreground" />
      <div>
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-sm font-semibold">{value}</p>
      </div>
    </div>
  );
}

function PlaybookPanelSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-4 gap-3">
        {[1, 2, 3, 4].map((i) => (
          <Skeleton key={i} className="h-14 rounded-lg" />
        ))}
      </div>
      {[1, 2, 3].map((i) => (
        <Skeleton key={i} className="h-12 w-full" />
      ))}
    </div>
  );
}

export function PlaybookPanel({ employeeId }: { employeeId: string }) {
  const { data: stats, isLoading: statsLoading } = usePlaybookStats(employeeId, {
    autoRefresh: true,
    interval: 60,
  });
  const { data: playbooks, isLoading: listLoading } = usePlaybooks(employeeId, {
    sortBy: 'success_rate',
    limit: 50,
  });

  if (statsLoading || listLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <BookOpen className="h-4 w-4" /> Playbooks
          </CardTitle>
        </CardHeader>
        <CardContent>
          <PlaybookPanelSkeleton />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <BookOpen className="h-4 w-4" /> Playbooks
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Stats row */}
        {stats && (
          <div className="grid grid-cols-4 gap-3">
            <StatBadge label="Total" value={stats.totalPlaybooks} icon={BookOpen} />
            <StatBadge
              label="Avg Success"
              value={`${Math.round(stats.avgSuccessRate * 100)}%`}
              icon={TrendingUp}
            />
            <StatBadge label="Executions" value={stats.totalExecutions} icon={Clock} />
            <StatBadge
              label="Candidates"
              value={stats.promotionCandidates}
              icon={Award}
            />
          </div>
        )}

        {/* Playbook table */}
        {playbooks && playbooks.items.length > 0 ? (
          <div className="rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="px-3 py-2 text-left font-medium">Name</th>
                  <th className="px-3 py-2 text-left font-medium">Success</th>
                  <th className="px-3 py-2 text-right font-medium">Runs</th>
                  <th className="px-3 py-2 text-left font-medium">Source</th>
                  <th className="px-3 py-2 text-left font-medium">Promoted</th>
                </tr>
              </thead>
              <tbody>
                {playbooks.items.map((p) => (
                  <tr key={p.id} className="border-b border-border/50 last:border-0">
                    <td className="px-3 py-2">
                      <div>
                        <p className="font-medium">{p.name}</p>
                        {p.description && (
                          <p className="mt-0.5 text-xs text-muted-foreground line-clamp-1">
                            {p.description}
                          </p>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <SuccessBar rate={p.successRate} />
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {p.executionCount}
                    </td>
                    <td className="px-3 py-2">
                      <span className="inline-flex rounded-full border border-border bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                        {LEARNED_FROM_LABELS[p.learnedFrom ?? ''] ?? p.learnedFrom ?? 'unknown'}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-xs text-muted-foreground">
                      {p.promotedAt
                        ? new Date(p.promotedAt).toLocaleDateString()
                        : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full border border-border bg-muted/50">
              <BookOpen className="h-5 w-5 text-muted-foreground" />
            </div>
            <p className="mt-3 text-sm font-medium">No playbooks yet</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Playbooks are discovered autonomously when procedures prove successful.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
