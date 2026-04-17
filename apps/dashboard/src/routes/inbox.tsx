import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Inbox as InboxIcon, Check, Trash2, AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';
import {
  useInbox,
  useMarkInboxRead,
  useDeleteInboxMessage,
  type InboxMessage,
  type InboxPriority,
} from '@empla/react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { InboxBlockRenderer } from '@/components/inbox/blocks';

type FilterTab = 'all' | 'unread' | 'urgent';

export function InboxPage() {
  const [tab, setTab] = useState<FilterTab>('all');
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const priorityFilter: InboxPriority | undefined = tab === 'urgent' ? 'urgent' : undefined;
  const unreadOnly = tab === 'unread';
  const { data, isLoading, error } = useInbox(
    { unreadOnly, priority: priorityFilter, pageSize: 50 },
    { refetchInterval: 30_000 },
  );

  const markRead = useMarkInboxRead();
  const del = useDeleteInboxMessage();

  const messages = data?.items ?? [];
  const selected = selectedId ? messages.find((m) => m.id === selectedId) ?? null : null;

  const handleSelect = async (m: InboxMessage) => {
    setSelectedId(m.id);
    if (!m.readAt) {
      try {
        await markRead.mutateAsync(m.id);
      } catch {
        // Non-fatal: the list view will refresh on next poll.
      }
    }
  };

  const handleDelete = async (m: InboxMessage) => {
    if (!window.confirm(`Delete "${m.subject}"? This cannot be undone.`)) return;
    try {
      await del.mutateAsync(m.id);
      if (selectedId === m.id) setSelectedId(null);
      toast.success('Message deleted');
    } catch (err) {
      const msg = err instanceof Error && err.message ? err.message : 'Delete failed';
      toast.error(msg);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-primary/30 bg-primary/10">
          <InboxIcon className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h2 className="font-display text-2xl font-bold tracking-tight">Inbox</h2>
          <p className="text-sm text-muted-foreground">
            Messages from your employees. Urgent items include "why did my employee pause?" cost
            hard-stop notifications.
          </p>
        </div>
      </div>

      {/* Filter tabs */}
      <div className="inline-flex rounded-lg border border-border bg-muted/30 p-1">
        {(['all', 'unread', 'urgent'] as FilterTab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              'rounded-md px-3 py-1.5 text-xs font-medium capitalize transition-colors',
              tab === t
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {t}
            {t === 'unread' && data?.unreadCount ? ` (${data.unreadCount})` : ''}
          </button>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        {/* List column */}
        <div className="lg:col-span-1">
          <Card className="border-border/50 bg-card/80 backdrop-blur-sm">
            <CardContent className="divide-y divide-border p-0">
              {isLoading && (
                <div className="space-y-3 p-4">
                  <Skeleton className="h-14 w-full" />
                  <Skeleton className="h-14 w-full" />
                  <Skeleton className="h-14 w-full" />
                </div>
              )}
              {error && (
                <div className="p-4 text-sm text-status-error">
                  Failed to load inbox. Retrying automatically.
                </div>
              )}
              {!isLoading && messages.length === 0 && (
                <div className="flex flex-col items-center gap-2 p-8 text-center">
                  <InboxIcon className="h-8 w-8 text-muted-foreground opacity-60" />
                  <p className="font-display text-sm">Your inbox is empty.</p>
                  <p className="text-xs text-muted-foreground">
                    Your employees will post updates, questions, and urgent notices here.
                  </p>
                </div>
              )}
              {messages.map((m) => {
                const isSelected = m.id === selectedId;
                const isUnread = !m.readAt;
                const isUrgent = m.priority === 'urgent';
                return (
                  <button
                    key={m.id}
                    onClick={() => handleSelect(m)}
                    className={cn(
                      'block w-full px-4 py-3 text-left transition-colors hover:bg-accent',
                      isSelected && 'bg-accent',
                    )}
                  >
                    <div className="mb-1 flex items-start gap-2">
                      {isUrgent && (
                        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-status-error" />
                      )}
                      <div
                        className={cn(
                          'flex-1 truncate text-sm',
                          isUnread ? 'font-semibold' : 'font-normal text-muted-foreground',
                        )}
                      >
                        {m.subject}
                      </div>
                      {isUnread && (
                        <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-primary" />
                      )}
                    </div>
                    <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                      {new Date(m.createdAt).toLocaleString()}
                    </div>
                  </button>
                );
              })}
            </CardContent>
          </Card>
        </div>

        {/* Detail column */}
        <div className="lg:col-span-2">
          {selected ? (
            <Card className="border-border/50 bg-card/80 backdrop-blur-sm">
              <CardContent className="space-y-4 p-6">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="mb-1 flex items-center gap-2">
                      {selected.priority === 'urgent' && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-status-error/20 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-status-error">
                          <AlertTriangle className="h-3 w-3" /> Urgent
                        </span>
                      )}
                      <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                        {new Date(selected.createdAt).toLocaleString()}
                      </span>
                    </div>
                    <h3 className="font-display text-lg font-semibold">{selected.subject}</h3>
                    <Link
                      to={`/employees/${selected.employeeId}`}
                      className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground hover:text-primary"
                    >
                      From: {selected.employeeId.slice(0, 8)}
                    </Link>
                  </div>
                  <div className="flex shrink-0 gap-2">
                    {!selected.readAt && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => markRead.mutate(selected.id)}
                      >
                        <Check className="mr-1 h-3 w-3" /> Mark read
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleDelete(selected)}
                      aria-label={`Delete ${selected.subject}`}
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                </div>

                {/* Block renderers */}
                <div className="space-y-4">
                  {selected.blocks.map((block, idx) => (
                    <InboxBlockRenderer key={idx} block={block} />
                  ))}
                </div>
              </CardContent>
            </Card>
          ) : (
            <Card className="border-border/50 bg-card/80 backdrop-blur-sm">
              <CardContent className="flex min-h-[300px] items-center justify-center">
                <p className="text-sm text-muted-foreground">Select a message to read</p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
