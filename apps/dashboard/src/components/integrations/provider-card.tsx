import { Cable, CheckCircle2 } from 'lucide-react';
import type { ProviderInfo } from '@empla/react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

const PROVIDER_ICONS: Record<string, string> = {
  google: '/icons/google.svg',
  microsoft: '/icons/microsoft.svg',
};

interface ProviderCardProps {
  provider: ProviderInfo;
  onConnect: (provider: ProviderInfo) => void;
}

export function ProviderCard({ provider, onConnect }: ProviderCardProps) {
  const hasConnections = provider.connectedEmployees > 0;

  return (
    <div
      className={cn(
        'group relative rounded-lg border bg-card/80 p-5 backdrop-blur-sm transition-all',
        provider.available
          ? 'border-border/50 hover:border-primary/30 hover:shadow-md'
          : 'border-border/30 opacity-60'
      )}
    >
      <div className="flex items-start gap-4">
        {/* Icon */}
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg border border-border/50 bg-muted/50">
          {PROVIDER_ICONS[provider.icon] ? (
            <img
              src={PROVIDER_ICONS[provider.icon]}
              alt={provider.displayName}
              className="h-6 w-6"
              onError={(e) => {
                e.currentTarget.style.display = 'none';
                e.currentTarget.parentElement?.querySelector('.fallback-icon')?.classList.remove('hidden');
              }}
            />
          ) : null}
          <Cable className={cn('h-6 w-6 text-muted-foreground', PROVIDER_ICONS[provider.icon] && 'hidden fallback-icon')} />
        </div>

        {/* Info */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="font-display text-sm font-semibold">{provider.displayName}</h3>
            {hasConnections && (
              <Badge variant="outline" className="border-status-running/30 text-status-running text-xs">
                <CheckCircle2 className="mr-1 h-3 w-3" />
                {provider.connectedEmployees} connected
              </Badge>
            )}
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">{provider.description}</p>

          {provider.source && (
            <p className="mt-1 text-xs text-muted-foreground/60">
              {provider.source === 'platform' ? 'Platform credentials' : 'Custom credentials'}
            </p>
          )}
        </div>

        {/* Connect button */}
        <Button
          size="sm"
          variant={hasConnections ? 'outline' : 'default'}
          disabled={!provider.available}
          onClick={() => onConnect(provider)}
          className="shrink-0"
        >
          {hasConnections ? 'Add' : 'Connect'}
        </Button>
      </div>
    </div>
  );
}
