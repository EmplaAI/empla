import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Loader2, TestTube, CheckCircle2, XCircle } from 'lucide-react';
import { toast } from 'sonner';
import {
  useCreateMCPServer,
  useTestMCPServer,
  type MCPAuthType,
  type MCPTransport,
} from '@empla/react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { buildCredentials, parseCommand, parseEnv } from './parse-utils';

const nameSlugRe = /^[a-z][a-z0-9_-]{0,48}[a-z0-9]$/;

const addSchema = z.object({
  name: z
    .string()
    .min(2)
    .max(50)
    .regex(nameSlugRe, 'Lowercase letters, numbers, hyphens, underscores. Must start with a letter.'),
  displayName: z.string().min(1).max(200),
  description: z.string().max(500).optional(),
  transport: z.enum(['http', 'stdio'] as const),
  url: z.string().max(2000).optional(),
  command: z.string().optional(),
  env: z.string().optional(),
  authType: z.enum(['none', 'api_key', 'bearer_token', 'oauth'] as const),
  apiKey: z.string().optional(),
  bearerToken: z.string().optional(),
  oauthClientId: z.string().optional(),
  oauthClientSecret: z.string().optional(),
  oauthTokenUrl: z.string().optional(),
  oauthAuthorizationUrl: z.string().optional(),
  oauthScopes: z.string().optional(),
});

type AddFormData = z.infer<typeof addSchema>;

interface AddMCPServerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AddMCPServerDialog({ open, onOpenChange }: AddMCPServerDialogProps) {
  const createServer = useCreateMCPServer();
  const testServer = useTestMCPServer();
  const [testResult, setTestResult] = useState<{ success: boolean; tools: number } | null>(null);

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    reset,
    formState: { errors },
  } = useForm<AddFormData>({
    resolver: zodResolver(addSchema),
    defaultValues: {
      transport: 'http',
      authType: 'none',
    },
  });

  const transport = watch('transport');
  const authType = watch('authType');

  const handleClose = (isOpen: boolean) => {
    if (!isOpen) {
      reset();
      setTestResult(null);
    }
    onOpenChange(isOpen);
  };

  const handleTest = async () => {
    const data = watch();
    setTestResult(null);
    try {
      const result = await testServer.mutateAsync({
        transport: data.transport as MCPTransport,
        url: data.transport === 'http' ? data.url : undefined,
        command: data.transport === 'stdio' ? parseCommand(data.command) : undefined,
        env: data.transport === 'stdio' ? parseEnv(data.env) : undefined,
        authType: data.authType as MCPAuthType,
        credentials: buildCredentials(data.authType, data),
      });
      setTestResult({ success: result.success, tools: result.toolsDiscovered });
      if (result.success) {
        toast.success(`Discovered ${result.toolsDiscovered} tools`);
      } else {
        toast.error('Connection failed', { description: result.error ?? 'Unknown error' });
      }
    } catch (error) {
      toast.error('Test failed', {
        description: error instanceof Error ? error.message : 'Please try again',
      });
    }
  };

  const onSubmit = async (data: AddFormData) => {
    try {
      await createServer.mutateAsync({
        name: data.name,
        displayName: data.displayName,
        description: data.description,
        transport: data.transport as MCPTransport,
        url: data.transport === 'http' ? data.url : undefined,
        command: data.transport === 'stdio' ? parseCommand(data.command) : undefined,
        env: data.transport === 'stdio' ? parseEnv(data.env) : undefined,
        authType: data.authType as MCPAuthType,
        credentials: buildCredentials(data.authType, data),
      });

      toast.success('MCP server added', { description: `${data.displayName} has been configured` });
      handleClose(false);
    } catch (error) {
      toast.error('Failed to add server', {
        description: error instanceof Error ? error.message : 'Please try again',
      });
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-[540px]">
        <DialogHeader>
          <DialogTitle className="font-display">Add MCP Server</DialogTitle>
          <DialogDescription>
            Configure an external MCP server to provide tools to your employees
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {/* Name (slug) */}
          <div className="space-y-2">
            <Label htmlFor="mcp-name">Name</Label>
            <Input
              id="mcp-name"
              placeholder="salesforce"
              className="bg-background/50 font-mono"
              {...register('name')}
            />
            <p className="text-xs text-muted-foreground">
              Used as tool prefix (e.g. salesforce.query)
            </p>
            {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
          </div>

          {/* Display Name */}
          <div className="space-y-2">
            <Label htmlFor="mcp-display-name">Display Name</Label>
            <Input
              id="mcp-display-name"
              placeholder="Salesforce CRM"
              className="bg-background/50"
              {...register('displayName')}
            />
            {errors.displayName && (
              <p className="text-sm text-destructive">{errors.displayName.message}</p>
            )}
          </div>

          {/* Description */}
          <div className="space-y-2">
            <Label htmlFor="mcp-description">Description</Label>
            <Input
              id="mcp-description"
              placeholder="CRM data access and management tools"
              className="bg-background/50"
              {...register('description')}
            />
          </div>

          {/* Transport */}
          <div className="space-y-2">
            <Label>Transport</Label>
            <Select
              value={transport}
              onValueChange={(v: MCPTransport) => setValue('transport', v)}
            >
              <SelectTrigger className="bg-background/50">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="http">HTTP / SSE</SelectItem>
                <SelectItem value="stdio">stdio (local process)</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* URL (HTTP) */}
          {transport === 'http' && (
            <div className="space-y-2">
              <Label htmlFor="mcp-url">URL</Label>
              <Input
                id="mcp-url"
                placeholder="https://mcp.example.com/sse"
                className="bg-background/50"
                {...register('url')}
              />
              {errors.url && <p className="text-sm text-destructive">{errors.url.message}</p>}
            </div>
          )}

          {/* Command (stdio) */}
          {transport === 'stdio' && (
            <>
              <div className="space-y-2">
                <Label htmlFor="mcp-command">Command</Label>
                <Input
                  id="mcp-command"
                  placeholder="npx -y @modelcontextprotocol/server-filesystem /tmp"
                  className="bg-background/50 font-mono text-sm"
                  {...register('command')}
                />
                <p className="text-xs text-muted-foreground">
                  Full command to start the MCP server process
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="mcp-env">Environment Variables</Label>
                <textarea
                  id="mcp-env"
                  rows={3}
                  placeholder="KEY=value (one per line)"
                  className="flex w-full rounded-md border border-input bg-background/50 px-3 py-2 font-mono text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  {...register('env')}
                />
              </div>
            </>
          )}

          {/* Auth Type */}
          <div className="space-y-2">
            <Label>Authentication</Label>
            <Select
              value={authType}
              onValueChange={(v: MCPAuthType) => setValue('authType', v)}
            >
              <SelectTrigger className="bg-background/50">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">None</SelectItem>
                <SelectItem value="api_key">API Key</SelectItem>
                <SelectItem value="bearer_token">Bearer Token</SelectItem>
                <SelectItem value="oauth">OAuth</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* API Key */}
          {authType === 'api_key' && (
            <div className="space-y-2">
              <Label htmlFor="mcp-api-key">API Key</Label>
              <Input
                id="mcp-api-key"
                type="password"
                placeholder="sk-..."
                className="bg-background/50 font-mono"
                {...register('apiKey')}
              />
            </div>
          )}

          {/* Bearer Token */}
          {authType === 'bearer_token' && (
            <div className="space-y-2">
              <Label htmlFor="mcp-bearer-token">Bearer Token</Label>
              <Input
                id="mcp-bearer-token"
                type="password"
                placeholder="Token..."
                className="bg-background/50 font-mono"
                {...register('bearerToken')}
              />
            </div>
          )}

          {/* OAuth */}
          {authType === 'oauth' && (
            <div className="space-y-3 rounded-md border border-border/50 p-3">
              <div className="space-y-2">
                <Label htmlFor="mcp-oauth-client-id">Client ID</Label>
                <Input
                  id="mcp-oauth-client-id"
                  className="bg-background/50"
                  {...register('oauthClientId')}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="mcp-oauth-client-secret">Client Secret</Label>
                <Input
                  id="mcp-oauth-client-secret"
                  type="password"
                  className="bg-background/50"
                  {...register('oauthClientSecret')}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="mcp-oauth-token-url">Token URL</Label>
                <Input
                  id="mcp-oauth-token-url"
                  placeholder="https://provider.com/oauth/token"
                  className="bg-background/50"
                  {...register('oauthTokenUrl')}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="mcp-oauth-auth-url">Authorization URL</Label>
                <Input
                  id="mcp-oauth-auth-url"
                  placeholder="https://provider.com/oauth/authorize"
                  className="bg-background/50"
                  {...register('oauthAuthorizationUrl')}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="mcp-oauth-scopes">Scopes</Label>
                <Input
                  id="mcp-oauth-scopes"
                  placeholder="read, write"
                  className="bg-background/50"
                  {...register('oauthScopes')}
                />
                <p className="text-xs text-muted-foreground">Comma-separated</p>
              </div>
            </div>
          )}

          {/* Test result */}
          {testResult && (
            <div
              className={`flex items-center gap-2 rounded-md border p-3 text-sm ${
                testResult.success
                  ? 'border-status-active/30 bg-status-active/5 text-status-active'
                  : 'border-status-error/30 bg-status-error/5 text-status-error'
              }`}
            >
              {testResult.success ? (
                <CheckCircle2 className="h-4 w-4" />
              ) : (
                <XCircle className="h-4 w-4" />
              )}
              {testResult.success
                ? `Connection successful - ${testResult.tools} tools discovered`
                : 'Connection failed'}
            </div>
          )}

          <DialogFooter className="gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={handleTest}
              disabled={testServer.isPending}
            >
              {testServer.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <TestTube className="mr-2 h-4 w-4" />
              )}
              Test Connection
            </Button>
            <Button type="submit" disabled={createServer.isPending}>
              {createServer.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Adding...
                </>
              ) : (
                'Add Server'
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
