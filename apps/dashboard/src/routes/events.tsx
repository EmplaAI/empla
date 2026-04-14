import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertCircle,
  Copy,
  KeyRound,
  Plus,
  Radio,
  RefreshCw,
  Trash2,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  useCreateWebhookToken,
  useDeleteWebhookToken,
  useRotateWebhookToken,
  useWebhookEvents,
  useWebhookTokens,
  type WebhookTokenInfo,
} from '@empla/react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

// Providers that currently emit webhooks empla knows how to parse.
// Kept narrow intentionally — future wizards land in later PRs.
const WIZARD_PROVIDERS: Array<{
  key: string;
  label: string;
  steps: string[];
}> = [
  {
    key: 'hubspot',
    label: 'HubSpot',
    steps: [
      'Open HubSpot Settings → Integrations → Private Apps → your app.',
      'Under "Webhooks," subscribe to the events you care about.',
      'Paste the Target URL (shown above after you generate a token).',
      'Send the token in the X-Webhook-Token header (not Authorization).',
    ],
  },
  {
    key: 'google_calendar',
    label: 'Google Calendar',
    steps: [
      'In Google Cloud Console, enable the Calendar API for your project.',
      'Create a push notification channel via Calendar API: events.watch.',
      'Set the address to the Target URL above.',
      'Forward the token in the X-Webhook-Token header on each delivery.',
    ],
  },
  {
    key: 'gmail',
    label: 'Gmail',
    steps: [
      'Create a Pub/Sub topic in Google Cloud. Grant Gmail API the Pub/Sub Publisher role on it.',
      'Call gmail.users.watch with the topic name and label filter.',
      'Add a Pub/Sub push subscription pointing at the Target URL.',
      'Send the token in the X-Webhook-Token header (not Authorization).',
    ],
  },
];

function TokenReceivedDialog({
  token,
  provider,
  onClose,
}: {
  token: string | null;
  provider: string | null;
  onClose: () => void;
}) {
  const [saved, setSaved] = useState(false);
  const targetUrl =
    token && provider ? `${window.location.origin}/api/v1/webhooks/${provider}` : '';

  // Reset the "saved" confirmation when the dialog closes. Doing this in
  // render would violate React's rule against setState during render
  // (StrictMode re-renders into an infinite loop).
  useEffect(() => {
    if (!token) setSaved(false);
  }, [token]);

  // Warn the user before unload if they've generated a token but haven't
  // confirmed they saved it yet. The token is one-time; losing it forces a
  // rotate + reconfigure of the provider webhook.
  useEffect(() => {
    if (!token || saved) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [token, saved]);

  const copy = async (value: string, label: string) => {
    try {
      await navigator.clipboard.writeText(value);
      toast.success(`${label} copied`);
    } catch {
      toast.error('Clipboard blocked — select the text and copy manually.');
    }
  };

  return (
    <Dialog open={!!token} onOpenChange={(open) => !open && saved && onClose()}>
      <DialogContent
        onInteractOutside={(e) => e.preventDefault()}
        onEscapeKeyDown={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle className="font-display">Token generated</DialogTitle>
          <DialogDescription>
            Copy this token now. You won't see it again — if you lose it, rotate to get a new
            one.
          </DialogDescription>
        </DialogHeader>
        <div className="mt-2 space-y-3">
          <div>
            <p className="mb-1 text-xs font-medium text-muted-foreground">Token</p>
            <div className="rounded-lg border border-border/50 bg-muted p-3 font-mono text-xs break-all">
              {token ?? ''}
            </div>
          </div>
          <div>
            <p className="mb-1 text-xs font-medium text-muted-foreground">
              Target URL (set this as the webhook destination in {provider ?? 'your provider'})
            </p>
            <div className="rounded-lg border border-border/50 bg-muted p-3 font-mono text-xs break-all">
              {targetUrl}
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            Send the token in the <code className="font-mono">X-Webhook-Token</code> header.
          </p>
        </div>
        <DialogFooter className="flex-col gap-2 sm:flex-row">
          <Button variant="outline" onClick={() => targetUrl && copy(targetUrl, 'URL')}>
            <Copy className="mr-2 h-4 w-4" /> Copy URL
          </Button>
          <Button onClick={() => token && copy(token, 'Token')}>
            <Copy className="mr-2 h-4 w-4" /> Copy token
          </Button>
          <Button
            variant={saved ? 'default' : 'outline'}
            onClick={() => {
              setSaved(true);
              onClose();
            }}
          >
            I've saved it
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function TokenRow({
  token,
  onGenerated,
}: {
  token: WebhookTokenInfo;
  onGenerated: (value: string, provider: string) => void;
}) {
  const create = useCreateWebhookToken();
  const rotate = useRotateWebhookToken();
  const del = useDeleteWebhookToken();

  const targetUrl = `${window.location.origin}/api/v1/webhooks/${token.provider}`;

  // The API client (ApiError) already unpacks FastAPI's `detail` into
  // .message, so surfacing err.message gives users the real reason
  // ("Webhook token already exists…") instead of a generic failure toast.
  const errorMessage = (err: unknown, fallback: string) =>
    err instanceof Error && err.message ? err.message : fallback;

  const handleGenerate = async () => {
    try {
      const result = await create.mutateAsync({ integrationId: token.integrationId });
      onGenerated(result.token, token.provider);
    } catch (err) {
      toast.error(errorMessage(err, 'Failed to generate token'));
    }
  };

  const handleRotate = async () => {
    if (
      !window.confirm(
        'Rotate this token? The previous token keeps working for 5 minutes while providers catch up.',
      )
    ) {
      return;
    }
    try {
      const result = await rotate.mutateAsync({ integrationId: token.integrationId });
      onGenerated(result.token, token.provider);
    } catch (err) {
      toast.error(errorMessage(err, 'Failed to rotate token'));
    }
  };

  const handleCopyUrl = async () => {
    try {
      await navigator.clipboard.writeText(targetUrl);
      toast.success('Target URL copied');
    } catch {
      toast.error('Clipboard blocked — select the text and copy manually.');
    }
  };

  const handleDelete = async () => {
    if (!window.confirm('Delete this token? Webhooks will start returning 401 immediately.')) {
      return;
    }
    try {
      await del.mutateAsync({ integrationId: token.integrationId });
      toast.success('Token deleted');
    } catch (err) {
      toast.error(errorMessage(err, 'Failed to delete token'));
    }
  };

  return (
    <div className="rounded-lg border border-border/50 bg-muted/30 p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="font-mono text-sm">
            <span className="text-primary">{token.provider}</span>
          </p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {token.hasToken ? (
              <>
                Active.{' '}
                {token.graceWindowActive ? (
                  <span className="text-status-paused">
                    Previous token still accepted (rotation grace window).
                  </span>
                ) : (
                  'No rotation in progress.'
                )}
              </>
            ) : (
              'No token yet.'
            )}
          </p>
          {token.hasToken ? (
            <div className="mt-2 flex items-center gap-2">
              <code className="min-w-0 flex-1 truncate rounded border border-border/40 bg-background/60 px-2 py-1 font-mono text-[11px] text-muted-foreground">
                {targetUrl}
              </code>
              <Button variant="ghost" size="sm" className="h-7 px-2" onClick={handleCopyUrl}>
                <Copy className="h-3 w-3" />
              </Button>
            </div>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {token.hasToken ? (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={handleRotate}
                disabled={rotate.isPending}
              >
                <RefreshCw className="mr-1.5 h-3.5 w-3.5" /> Rotate
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleDelete}
                disabled={del.isPending}
              >
                <Trash2 className="mr-1.5 h-3.5 w-3.5" /> Delete
              </Button>
            </>
          ) : (
            <Button size="sm" onClick={handleGenerate} disabled={create.isPending}>
              <Plus className="mr-1.5 h-3.5 w-3.5" /> Generate token
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

function TokenManager({
  onGenerated,
}: {
  onGenerated: (value: string, provider: string) => void;
}) {
  const { data, isLoading, error, refetch } = useWebhookTokens();

  return (
    <Card className="border-border/50 bg-card/80 backdrop-blur-sm">
      <CardHeader className="pb-3">
        <CardTitle className="font-display text-lg font-semibold">
          <KeyRound className="mr-2 inline h-4 w-4 text-muted-foreground" />
          Webhook tokens
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-10 text-center">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full border border-destructive/30 bg-destructive/10">
              <AlertCircle className="h-6 w-6 text-destructive" />
            </div>
            <h3 className="font-display text-lg">Couldn't load tokens</h3>
            <Button variant="outline" className="mt-4" onClick={() => refetch()}>
              Try again
            </Button>
          </div>
        ) : !data || data.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 text-center">
            <KeyRound className="mb-4 h-10 w-10 text-muted-foreground/60" />
            <h3 className="font-display text-lg">No integrations yet</h3>
            <p className="mt-2 max-w-sm text-sm text-muted-foreground">
              Connect an integration to an employee first. Each integration gets its own webhook
              token.
            </p>
            <Button asChild variant="outline" className="mt-4">
              <Link to="/integrations">Connect an integration</Link>
            </Button>
          </div>
        ) : (
          <div className="space-y-2">
            {data.map((t) => (
              <TokenRow key={t.integrationId} token={t} onGenerated={onGenerated} />
            ))}
          </div>
        )}
        <p className="mt-4 text-xs text-muted-foreground">
          Wizards available for: {WIZARD_PROVIDERS.map((w) => w.label).join(', ')}. See setup
          steps below after you generate a token.
        </p>
      </CardContent>
    </Card>
  );
}

function EventFeed() {
  const [page, setPage] = useState(1);
  const { data, isLoading, error, refetch } = useWebhookEvents({ page, pageSize: 30 });

  const items = data?.items ?? [];
  const totalPages = data?.pages ?? 1;

  return (
    <Card className="border-border/50 bg-card/80 backdrop-blur-sm">
      <CardHeader className="flex flex-row items-center justify-between pb-3">
        <CardTitle className="font-display text-lg font-semibold">
          <Radio className="mr-2 inline h-4 w-4 text-muted-foreground" />
          Event stream {data ? `(${data.total})` : ''}
        </CardTitle>
        {totalPages > 1 ? (
          <div className="flex items-center gap-2 text-xs">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage(page - 1)}
            >
              Prev
            </Button>
            <span className="text-muted-foreground font-mono">
              {page} / {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => setPage(page + 1)}
            >
              Next
            </Button>
          </div>
        ) : null}
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            {[1, 2, 3, 4, 5].map((i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-10 text-center">
            <AlertCircle className="h-5 w-5 text-destructive" />
            <p className="mt-2 text-sm text-muted-foreground">Couldn't load events</p>
            <Button variant="outline" className="mt-3" onClick={() => refetch()}>
              Try again
            </Button>
          </div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 text-center">
            <Radio className="mb-4 h-10 w-10 text-muted-foreground/60" />
            <h3 className="font-display text-lg">No webhooks yet</h3>
            <p className="mt-2 max-w-sm text-sm text-muted-foreground">
              Once a provider sends a webhook, the event will appear here in near real time.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {items.map((ev) => (
              <div
                key={ev.id}
                className="rounded-lg border border-border/50 bg-muted/30 p-3"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="font-mono text-sm">
                      <span className="text-primary">{ev.provider}</span>
                      <span className="mx-1.5 text-muted-foreground">·</span>
                      <span className="text-foreground/80">{ev.eventType}</span>
                    </p>
                    {ev.summary ? (
                      <p className="mt-0.5 text-xs text-muted-foreground">{ev.summary}</p>
                    ) : null}
                    <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                      {new Date(ev.occurredAt).toLocaleString()} ·{' '}
                      {ev.employeesNotified} employee
                      {ev.employeesNotified === 1 ? '' : 's'} notified
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function SetupWizards() {
  return (
    <Card className="border-border/50 bg-card/80 backdrop-blur-sm">
      <CardHeader className="pb-3">
        <CardTitle className="font-display text-lg font-semibold">Setup wizards</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4 md:grid-cols-3">
          {WIZARD_PROVIDERS.map((w) => (
            <div key={w.key} className="rounded-lg border border-border/50 bg-muted/30 p-4">
              <p className="font-display text-sm font-semibold">{w.label}</p>
              <ol className="mt-3 list-decimal space-y-1.5 pl-4 text-xs text-muted-foreground">
                {w.steps.map((step, i) => (
                  <li key={i}>{step}</li>
                ))}
              </ol>
            </div>
          ))}
        </div>
        <p className="mt-4 text-xs text-muted-foreground">
          More providers ship in later phases.
        </p>
      </CardContent>
    </Card>
  );
}

export function EventsPage() {
  const [issued, setIssued] = useState<{ token: string; provider: string } | null>(null);

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <div>
        <h1 className="font-display text-2xl font-bold tracking-tight">Webhooks + Events</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Manage per-integration webhook tokens and watch incoming events in real time.
        </p>
      </div>

      <TokenManager onGenerated={(token, provider) => setIssued({ token, provider })} />
      <EventFeed />
      <SetupWizards />

      <TokenReceivedDialog
        token={issued?.token ?? null}
        provider={issued?.provider ?? null}
        onClose={() => setIssued(null)}
      />
    </div>
  );
}
