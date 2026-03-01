import { useState } from 'react';
import {
  Server,
  Wrench,
  AlertTriangle,
  MoreVertical,
  TestTube,
  Pencil,
  Trash2,
  Loader2,
} from 'lucide-react';
import { toast } from 'sonner';
import type { MCPServer } from '@empla/react';
import { useDeleteMCPServer, useTestMCPServerConnection } from '@empla/react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';

interface MCPServerCardProps {
  server: MCPServer;
  onEdit: (server: MCPServer) => void;
  onViewTools: (server: MCPServer) => void;
}

export function MCPServerCard({ server, onEdit, onViewTools }: MCPServerCardProps) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  const testConnection = useTestMCPServerConnection();
  const deleteServer = useDeleteMCPServer();

  const toolCount = server.discoveredTools.length;
  const isActive = server.status === 'active';
  const hasError = !!server.lastError;

  const handleTest = async () => {
    try {
      const result = await testConnection.mutateAsync(server.id);
      if (result.success) {
        toast.success('Connection successful', {
          description: `Discovered ${result.toolsDiscovered} tools`,
        });
      } else {
        toast.error('Connection failed', { description: result.error ?? 'Unknown error' });
      }
    } catch (error) {
      toast.error('Test failed', {
        description: error instanceof Error ? error.message : 'Please try again',
      });
    }
  };

  const handleDelete = async () => {
    try {
      await deleteServer.mutateAsync(server.id);
      toast.success('Server removed', { description: `${server.displayName} has been removed` });
    } catch (error) {
      toast.error('Failed to remove server', {
        description: error instanceof Error ? error.message : 'Please try again',
      });
    }
    setConfirmDelete(false);
  };

  return (
    <div
      className={cn(
        'group relative rounded-lg border bg-card/80 p-5 backdrop-blur-sm transition-all',
        isActive
          ? 'border-border/50 hover:border-primary/30 hover:shadow-md'
          : 'border-border/30 opacity-60'
      )}
    >
      <div className="flex items-start gap-4">
        {/* Icon */}
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg border border-border/50 bg-muted/50">
          <Server className="h-6 w-6 text-muted-foreground" />
        </div>

        {/* Info */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="font-display text-sm font-semibold">{server.displayName}</h3>
            <Badge
              variant={isActive ? (hasError ? 'error' : 'active') : 'stopped'}
              className="text-xs"
            >
              {hasError ? 'Error' : server.status}
            </Badge>
          </div>
          {server.description && (
            <p className="mt-0.5 text-xs text-muted-foreground">{server.description}</p>
          )}
          <div className="mt-2 flex items-center gap-3 text-xs text-muted-foreground">
            <span className="font-mono">{server.name}</span>
            <span>{server.transport.toUpperCase()}</span>
            {toolCount > 0 && (
              <button
                type="button"
                onClick={() => onViewTools(server)}
                className="flex items-center gap-1 text-primary hover:underline"
              >
                <Wrench className="h-3 w-3" />
                {toolCount} {toolCount === 1 ? 'tool' : 'tools'}
              </button>
            )}
            {server.authType !== 'none' && (
              <span>
                {server.hasCredentials ? 'Auth configured' : 'No credentials'}
              </span>
            )}
          </div>
          {hasError && (
            <div className="mt-2 flex items-start gap-1.5 text-xs text-status-error">
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
              <span className="line-clamp-2">{server.lastError}</span>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex shrink-0 items-center gap-1">
          <Button
            size="sm"
            variant="outline"
            onClick={handleTest}
            disabled={testConnection.isPending}
          >
            {testConnection.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <TestTube className="h-4 w-4" />
            )}
            <span className="ml-1.5">Test</span>
          </Button>
          <DropdownMenu onOpenChange={(open) => { if (!open) setConfirmDelete(false); }}>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="h-8 w-8 p-0" aria-label="More actions">
                <MoreVertical className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => onEdit(server)}>
                <Pencil className="mr-2 h-4 w-4" />
                Edit
              </DropdownMenuItem>
              {confirmDelete ? (
                <DropdownMenuItem
                  className="text-destructive focus:text-destructive"
                  onClick={handleDelete}
                  disabled={deleteServer.isPending}
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  {deleteServer.isPending ? 'Removing...' : 'Confirm Remove'}
                </DropdownMenuItem>
              ) : (
                <DropdownMenuItem
                  className="text-destructive focus:text-destructive"
                  onSelect={(e) => {
                    e.preventDefault();
                    setConfirmDelete(true);
                  }}
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  Remove
                </DropdownMenuItem>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </div>
  );
}
