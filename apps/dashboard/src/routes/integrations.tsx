import { useState } from 'react';
import { Cable, AlertCircle } from 'lucide-react';
import { useProviders, type ProviderInfo } from '@empla/react';
import { Skeleton } from '@/components/ui/skeleton';
import { ProviderCard } from '@/components/integrations/provider-card';
import { ConnectDialog } from '@/components/integrations/connect-dialog';
import { CredentialsTable } from '@/components/integrations/credentials-table';

export function IntegrationsPage() {
  const { data: providers, isLoading, isError, error } = useProviders();
  const [connectProvider, setConnectProvider] = useState<ProviderInfo | null>(null);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="font-display text-2xl font-bold tracking-tight">Integrations</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Connect your tools and services to empower your digital employees
        </p>
      </div>

      {/* Provider cards */}
      <section>
        <h2 className="mb-4 font-display text-lg font-semibold">Available Providers</h2>
        {isError ? (
          <div className="flex flex-col items-center justify-center rounded-lg border border-destructive/30 bg-destructive/5 py-12">
            <AlertCircle className="h-8 w-8 text-destructive" />
            <p className="mt-3 text-sm text-destructive">
              Failed to load providers: {error?.message ?? 'Unknown error'}
            </p>
          </div>
        ) : isLoading ? (
          <div className="grid gap-4 md:grid-cols-2">
            {[1, 2].map((i) => (
              <div key={i} className="rounded-lg border border-border/50 bg-card/80 p-5">
                <div className="flex items-start gap-4">
                  <Skeleton className="h-12 w-12 rounded-lg" />
                  <div className="flex-1 space-y-2">
                    <Skeleton className="h-5 w-32" />
                    <Skeleton className="h-4 w-48" />
                  </div>
                  <Skeleton className="h-9 w-20 rounded-md" />
                </div>
              </div>
            ))}
          </div>
        ) : providers && providers.length > 0 ? (
          <div className="grid gap-4 md:grid-cols-2">
            {providers.map((p) => (
              <ProviderCard
                key={p.provider}
                provider={p}
                onConnect={setConnectProvider}
              />
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border py-12">
            <Cable className="h-8 w-8 text-muted-foreground" />
            <p className="mt-3 text-sm text-muted-foreground">
              No providers configured yet
            </p>
          </div>
        )}
      </section>

      {/* Connected credentials */}
      <section>
        <h2 className="mb-4 font-display text-lg font-semibold">Connected Credentials</h2>
        <CredentialsTable />
      </section>

      {/* Connect dialog */}
      <ConnectDialog
        provider={connectProvider}
        open={connectProvider !== null}
        onOpenChange={(open) => {
          if (!open) setConnectProvider(null);
        }}
      />
    </div>
  );
}
