import { Wrench } from 'lucide-react';
import type { MCPServer } from '@empla/react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

interface MCPServerToolsDialogProps {
  server: MCPServer | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function MCPServerToolsDialog({ server, open, onOpenChange }: MCPServerToolsDialogProps) {
  if (!server) return null;

  const tools = server.discoveredTools;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle className="font-display">
            {server.displayName} Tools
          </DialogTitle>
          <DialogDescription>
            {tools.length} {tools.length === 1 ? 'tool' : 'tools'} discovered from{' '}
            <span className="font-mono">{server.name}</span>
          </DialogDescription>
        </DialogHeader>

        {tools.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
            <Wrench className="h-8 w-8" />
            <p className="mt-3 text-sm">No tools discovered yet</p>
            <p className="mt-1 text-xs">Test the connection to discover available tools</p>
          </div>
        ) : (
          <div className="space-y-2">
            {tools.map((tool) => (
              <div
                key={tool.name}
                className="rounded-md border border-border/50 bg-muted/30 px-3 py-2"
              >
                <p className="font-mono text-sm font-medium">
                  {server.name}.{tool.name}
                </p>
                {tool.description && (
                  <p className="mt-0.5 text-xs text-muted-foreground">{tool.description}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
