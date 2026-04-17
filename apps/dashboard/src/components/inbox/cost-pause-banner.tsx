import { Link } from 'react-router-dom';
import { AlertTriangle, ExternalLink } from 'lucide-react';
import { useInbox } from '@empla/react';

/**
 * Persistent dashboard-wide banner shown whenever there's at least one
 * unread urgent message (which, today, means the cost hard-stop
 * fired). Designed to force the decision — dismissal requires opening
 * the message, reading the breakdown, and taking action (raise the
 * budget or resume).
 *
 * Dismisses itself automatically when the user marks the urgent
 * message read. Refreshes on the standard 30s inbox poll.
 */
export function CostPauseBanner() {
  const { data } = useInbox({ unreadOnly: true, priority: 'urgent', pageSize: 5 });
  const urgent = data?.items ?? [];
  if (urgent.length === 0) return null;

  // Highlight the most recent urgent message. If there are multiple
  // (e.g., two employees paused), link to the inbox route and let the
  // user triage each one individually.
  const latest = urgent[0];
  const moreCount = urgent.length - 1;

  return (
    <div
      role="alert"
      className="flex items-start gap-3 border-b border-status-error/40 bg-status-error/10 px-6 py-3"
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-status-error" />
      <div className="flex-1 text-sm">
        <span className="font-medium text-status-error">{latest.subject}</span>
        {moreCount > 0 && (
          <span className="ml-2 text-xs text-muted-foreground">
            + {moreCount} more urgent
          </span>
        )}
      </div>
      <Link
        to="/inbox"
        className="inline-flex shrink-0 items-center gap-1 rounded-md border border-status-error/40 bg-background px-2 py-1 text-xs font-medium text-status-error hover:bg-status-error/10"
      >
        Review <ExternalLink className="h-3 w-3" />
      </Link>
    </div>
  );
}
