import { useState } from 'react';
import { Trash2, Loader2, AlertCircle } from 'lucide-react';
import { toast } from 'sonner';
import { useCredentials, useRevokeCredential, useEmployees, type IntegrationCredential } from '@empla/react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { formatRelativeTime } from '@/lib/utils';

const PROVIDER_DISPLAY: Record<string, string> = {
  google_workspace: 'Google Workspace',
  microsoft_graph: 'Microsoft 365',
};

const STATUS_VARIANT: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  active: 'default',
  expired: 'destructive',
  revoked: 'secondary',
  refreshing: 'outline',
  revocation_failed: 'destructive',
};

export function CredentialsTable() {
  const { data: credentials, isLoading, isError, error } = useCredentials();
  const { data: employeesData } = useEmployees({ pageSize: 100 });
  const revokeMutation = useRevokeCredential();
  const [revokingId, setRevokingId] = useState<string | null>(null);

  const employeeMap = new Map(
    (employeesData?.items ?? []).map((e) => [e.id, e])
  );

  function handleRevoke(cred: IntegrationCredential) {
    setRevokingId(cred.id);
    revokeMutation.mutate(
      { integrationId: cred.integrationId, employeeId: cred.employeeId },
      {
        onSuccess: () => {
          toast.success('Credential revoked');
          setRevokingId(null);
        },
        onError: (err) => {
          toast.error(`Failed to revoke: ${err.message}`);
          setRevokingId(null);
        },
      }
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-destructive/30 bg-destructive/5 py-8">
        <AlertCircle className="h-6 w-6 text-destructive" />
        <p className="mt-2 text-sm text-destructive">
          Failed to load credentials: {error?.message ?? 'Unknown error'}
        </p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="flex items-center gap-4 rounded-lg border border-border/50 bg-card/80 p-4">
            <Skeleton className="h-10 w-10 rounded-full" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-3 w-24" />
            </div>
            <Skeleton className="h-5 w-16 rounded-full" />
          </div>
        ))}
      </div>
    );
  }

  if (!credentials || credentials.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border py-8 text-center">
        <p className="text-sm text-muted-foreground">No connected credentials yet</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {credentials.map((cred) => {
        const employee = employeeMap.get(cred.employeeId);
        const email = (cred.tokenMetadata as { email?: string })?.email;
        const isRevoking = revokingId === cred.id && revokeMutation.isPending;

        return (
          <div
            key={cred.id}
            className="flex items-center gap-4 rounded-lg border border-border/50 bg-card/80 p-4 transition-colors hover:bg-card"
          >
            {/* Employee info */}
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">
                  {employee?.name ?? 'Unknown employee'}
                </span>
                <Badge variant="outline" className="text-xs">
                  {PROVIDER_DISPLAY[cred.provider] ?? cred.provider}
                </Badge>
                <Badge variant={STATUS_VARIANT[cred.status] ?? 'secondary'} className="text-xs">
                  {cred.status}
                </Badge>
              </div>
              <div className="mt-0.5 flex items-center gap-3 text-xs text-muted-foreground">
                {email && <span>{email}</span>}
                {cred.lastUsedAt && (
                  <span>Last used {formatRelativeTime(cred.lastUsedAt)}</span>
                )}
                {cred.issuedAt && (
                  <span>Connected {formatRelativeTime(cred.issuedAt)}</span>
                )}
              </div>
            </div>

            {/* Revoke button */}
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-muted-foreground hover:text-destructive"
              onClick={() => handleRevoke(cred)}
              disabled={revokeMutation.isPending}
            >
              {isRevoking ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
            </Button>
          </div>
        );
      })}
    </div>
  );
}
