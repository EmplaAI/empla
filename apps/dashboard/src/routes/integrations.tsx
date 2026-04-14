import { useState } from 'react';
import { Cable, AlertCircle, Plus, Server } from 'lucide-react';
import { useProviders, useMCPServers, type ProviderInfo, type MCPServer } from '@empla/react';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { ProviderCard } from '@/components/integrations/provider-card';
import { ConnectDialog } from '@/components/integrations/connect-dialog';
import { CredentialsTable } from '@/components/integrations/credentials-table';
import { MCPServerCard } from '@/components/mcp-servers/mcp-server-card';
import { AddMCPServerDialog } from '@/components/mcp-servers/add-mcp-server-dialog';
import { EditMCPServerDialog } from '@/components/mcp-servers/edit-mcp-server-dialog';
import { MCPServerToolsDialog } from '@/components/mcp-servers/mcp-server-tools-dialog';

export function IntegrationsPage() {
  const { data: providers, isLoading, isError, error } = useProviders();
  const { data: mcpData, isLoading: mcpLoading, isError: mcpError, error: mcpErrorObj } = useMCPServers();
  const [connectProvider, setConnectProvider] = useState<ProviderInfo | null>(null);
  const [showAddServer, setShowAddServer] = useState(false);
  const [editServer, setEditServer] = useState<MCPServer | null>(null);
  const [toolsServer, setToolsServer] = useState<MCPServer | null>(null);

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

      {/* MCP Servers */}
      <section>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-display text-lg font-semibold">MCP Servers</h2>
          <Button onClick={() => setShowAddServer(true)}>
            <Plus className="mr-1.5 h-4 w-4" />
            Add Server
          </Button>
        </div>

        {mcpError ? (
          <div className="flex flex-col items-center justify-center rounded-lg border border-destructive/30 bg-destructive/5 py-12">
            <AlertCircle className="h-8 w-8 text-destructive" />
            <p className="mt-3 text-sm text-destructive">
              Failed to load MCP servers: {mcpErrorObj?.message ?? 'Unknown error'}
            </p>
          </div>
        ) : mcpLoading ? (
          <div className="grid gap-4 md:grid-cols-2">
            {[1, 2].map((i) => (
              <div key={i} className="rounded-lg border border-border/50 bg-card/80 p-5">
                <div className="flex items-start gap-4">
                  <Skeleton className="h-12 w-12 rounded-lg" />
                  <div className="flex-1 space-y-2">
                    <Skeleton className="h-5 w-32" />
                    <Skeleton className="h-4 w-48" />
                    <Skeleton className="h-3 w-24" />
                  </div>
                  <Skeleton className="h-9 w-16 rounded-md" />
                </div>
              </div>
            ))}
          </div>
        ) : mcpData && mcpData.items.length > 0 ? (
          <div className="grid gap-4 md:grid-cols-2">
            {mcpData.items.map((s) => (
              <MCPServerCard
                key={s.id}
                server={s}
                onEdit={setEditServer}
                onViewTools={setToolsServer}
              />
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border py-12">
            <Server className="h-8 w-8 text-muted-foreground" />
            <p className="mt-3 text-sm text-muted-foreground">
              No MCP servers configured yet
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              Add external MCP servers to give your employees more tools
            </p>
          </div>
        )}
      </section>

      {/* Dialogs */}
      <ConnectDialog
        provider={connectProvider}
        open={connectProvider !== null}
        onOpenChange={(open) => {
          if (!open) setConnectProvider(null);
        }}
      />

      <AddMCPServerDialog
        open={showAddServer}
        onOpenChange={setShowAddServer}
      />

      {editServer && (
        <EditMCPServerDialog
          server={editServer}
          open={!!editServer}
          onOpenChange={(open) => {
            if (!open) setEditServer(null);
          }}
        />
      )}

      <MCPServerToolsDialog
        server={toolsServer}
        open={!!toolsServer}
        onOpenChange={(open) => {
          if (!open) setToolsServer(null);
        }}
      />
    </div>
  );
}
