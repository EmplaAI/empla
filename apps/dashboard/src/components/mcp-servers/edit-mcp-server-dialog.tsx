import { useEffect, useRef } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { useUpdateMCPServer, type MCPServer, type MCPAuthType } from '@empla/react';
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
import { AuthFields } from './auth-fields';
import { buildCredentials, parseCommand, parseEnv } from './parse-utils';

const editSchema = z.object({
  displayName: z.string().min(1).max(200),
  description: z.string().max(500).optional(),
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
  status: z.enum(['active', 'disabled'] as const),
});

type EditFormData = z.infer<typeof editSchema>;

interface EditMCPServerDialogProps {
  server: MCPServer;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function EditMCPServerDialog({ server, open, onOpenChange }: EditMCPServerDialogProps) {
  const updateServer = useUpdateMCPServer();

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    reset,
    formState: { errors },
  } = useForm<EditFormData>({
    resolver: zodResolver(editSchema),
    defaultValues: {
      displayName: server.displayName,
      description: server.description,
      url: server.url ?? '',
      command: server.command?.join(' ') ?? '',
      authType: server.authType as EditFormData['authType'],
      status: (server.status === 'active' ? 'active' : 'disabled') as EditFormData['status'],
    },
  });

  const prevOpenRef = useRef(false);
  useEffect(() => {
    if (open && !prevOpenRef.current) {
      reset({
        displayName: server.displayName,
        description: server.description,
        url: server.url ?? '',
        command: server.command?.join(' ') ?? '',
        authType: server.authType as EditFormData['authType'],
        status: (server.status === 'active' ? 'active' : 'disabled') as EditFormData['status'],
      });
    }
    prevOpenRef.current = open;
  }, [open, server, reset]);

  const authType = watch('authType');
  const selectedStatus = watch('status');

  const onSubmit = async (data: EditFormData) => {
    try {
      await updateServer.mutateAsync({
        id: server.id,
        data: {
          displayName: data.displayName,
          description: data.description,
          url: server.transport === 'http' ? data.url : undefined,
          command: server.transport === 'stdio' ? parseCommand(data.command) : undefined,
          env: server.transport === 'stdio' ? parseEnv(data.env) : undefined,
          authType: data.authType as MCPAuthType,
          credentials: buildCredentials(data.authType, data),
          status: data.status,
        },
      });

      toast.success('Server updated', { description: `${data.displayName} has been updated` });
      onOpenChange(false);
    } catch (error) {
      toast.error('Failed to update server', {
        description: error instanceof Error ? error.message : 'Please try again',
      });
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-[540px]">
        <DialogHeader>
          <DialogTitle className="font-display">Edit MCP Server</DialogTitle>
          <DialogDescription>
            Update configuration for <span className="font-mono">{server.name}</span>
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {/* Display Name */}
          <div className="space-y-2">
            <Label htmlFor="edit-display-name">Display Name</Label>
            <Input
              id="edit-display-name"
              className="bg-background/50"
              {...register('displayName')}
            />
            {errors.displayName && (
              <p className="text-sm text-destructive">{errors.displayName.message}</p>
            )}
          </div>

          {/* Description */}
          <div className="space-y-2">
            <Label htmlFor="edit-description">Description</Label>
            <Input
              id="edit-description"
              className="bg-background/50"
              {...register('description')}
            />
          </div>

          {/* URL or Command based on transport */}
          {server.transport === 'http' ? (
            <div className="space-y-2">
              <Label htmlFor="edit-url">URL</Label>
              <Input id="edit-url" className="bg-background/50" {...register('url')} />
            </div>
          ) : (
            <>
              <div className="space-y-2">
                <Label htmlFor="edit-command">Command</Label>
                <Input
                  id="edit-command"
                  className="bg-background/50 font-mono text-sm"
                  {...register('command')}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-env">Environment Variables</Label>
                <textarea
                  id="edit-env"
                  rows={3}
                  placeholder="KEY=value (one per line)"
                  className="flex w-full rounded-md border border-input bg-background/50 px-3 py-2 font-mono text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  {...register('env')}
                />
              </div>
            </>
          )}

          {/* Status */}
          <div className="space-y-2">
            <Label>Status</Label>
            <Select
              value={selectedStatus}
              onValueChange={(v: 'active' | 'disabled') => setValue('status', v)}
            >
              <SelectTrigger className="bg-background/50">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="active">Active</SelectItem>
                <SelectItem value="disabled">Disabled</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <AuthFields
            authType={authType}
            register={register}
            setValue={setValue}
            hasCredentials={server.hasCredentials}
            idPrefix="edit"
          />

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={updateServer.isPending}>
              {updateServer.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Saving...
                </>
              ) : (
                'Save Changes'
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
