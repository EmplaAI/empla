import type { UseFormRegister, UseFormSetValue } from 'react-hook-form';
import type { MCPAuthType } from '@empla/react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

/** Minimal form shape that auth fields need. */
interface AuthFormFields {
  authType: 'none' | 'api_key' | 'bearer_token' | 'oauth';
  apiKey?: string;
  bearerToken?: string;
  oauthClientId?: string;
  oauthClientSecret?: string;
  oauthTokenUrl?: string;
  oauthAuthorizationUrl?: string;
  oauthScopes?: string;
}

interface AuthFieldsProps<T extends AuthFormFields> {
  authType: MCPAuthType;
  register: UseFormRegister<T>;
  setValue: UseFormSetValue<T>;
  /** Whether existing credentials are saved (shows placeholder hints in edit mode). */
  hasCredentials?: boolean;
  /** ID prefix for form elements (avoids collisions between add/edit dialogs). */
  idPrefix?: string;
}

export function AuthFields<T extends AuthFormFields>({
  authType,
  register,
  setValue,
  hasCredentials = false,
  idPrefix = 'mcp',
}: AuthFieldsProps<T>) {
  const savedPlaceholder = hasCredentials ? '(credentials saved)' : undefined;

  return (
    <>
      {/* Auth Type Select */}
      <div className="space-y-2">
        <Label>Authentication</Label>
        <Select
          value={authType}
          onValueChange={(v: MCPAuthType) =>
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            (setValue as any)('authType', v)
          }
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
          <Label htmlFor={`${idPrefix}-api-key`}>API Key</Label>
          <Input
            id={`${idPrefix}-api-key`}
            type="password"
            placeholder={savedPlaceholder ?? 'sk-...'}
            className="bg-background/50 font-mono"
            {...register('apiKey' as never)}
          />
          {hasCredentials && (
            <p className="text-xs text-muted-foreground">
              Leave blank to keep existing credentials
            </p>
          )}
        </div>
      )}

      {/* Bearer Token */}
      {authType === 'bearer_token' && (
        <div className="space-y-2">
          <Label htmlFor={`${idPrefix}-bearer-token`}>Bearer Token</Label>
          <Input
            id={`${idPrefix}-bearer-token`}
            type="password"
            placeholder={savedPlaceholder ?? 'Token...'}
            className="bg-background/50 font-mono"
            {...register('bearerToken' as never)}
          />
          {hasCredentials && (
            <p className="text-xs text-muted-foreground">
              Leave blank to keep existing credentials
            </p>
          )}
        </div>
      )}

      {/* OAuth */}
      {authType === 'oauth' && (
        <div className="space-y-3 rounded-md border border-border/50 p-3">
          {hasCredentials && (
            <p className="text-xs text-muted-foreground">
              Leave fields blank to keep existing credentials
            </p>
          )}
          <div className="space-y-2">
            <Label htmlFor={`${idPrefix}-oauth-client-id`}>Client ID</Label>
            <Input
              id={`${idPrefix}-oauth-client-id`}
              placeholder={hasCredentials ? '(saved)' : ''}
              className="bg-background/50"
              {...register('oauthClientId' as never)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor={`${idPrefix}-oauth-client-secret`}>Client Secret</Label>
            <Input
              id={`${idPrefix}-oauth-client-secret`}
              type="password"
              placeholder={hasCredentials ? '(saved)' : ''}
              className="bg-background/50"
              {...register('oauthClientSecret' as never)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor={`${idPrefix}-oauth-token-url`}>Token URL</Label>
            <Input
              id={`${idPrefix}-oauth-token-url`}
              placeholder="https://provider.com/oauth/token"
              className="bg-background/50"
              {...register('oauthTokenUrl' as never)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor={`${idPrefix}-oauth-auth-url`}>Authorization URL</Label>
            <Input
              id={`${idPrefix}-oauth-auth-url`}
              placeholder="https://provider.com/oauth/authorize"
              className="bg-background/50"
              {...register('oauthAuthorizationUrl' as never)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor={`${idPrefix}-oauth-scopes`}>Scopes</Label>
            <Input
              id={`${idPrefix}-oauth-scopes`}
              placeholder="read, write"
              className="bg-background/50"
              {...register('oauthScopes' as never)}
            />
            <p className="text-xs text-muted-foreground">Comma-separated</p>
          </div>
        </div>
      )}
    </>
  );
}
