import { Link } from 'react-router-dom';
import {
  Play,
  Pause,
  Square,
  RefreshCw,
  MessageSquare,
  Mail,
  Calendar,
  CheckCircle,
  AlertCircle,
  Circle,
} from 'lucide-react';
import type { Activity } from '@empla/react';
import { formatRelativeTime, cn } from '@/lib/utils';

const eventIcons: Record<string, typeof Play> = {
  started: Play,
  stopped: Square,
  paused: Pause,
  resumed: RefreshCw,
  message: MessageSquare,
  email: Mail,
  meeting: Calendar,
  completed: CheckCircle,
  error: AlertCircle,
};

const eventColors: Record<string, string> = {
  started: 'text-status-active bg-status-active/10 border-status-active/30',
  stopped: 'text-status-stopped bg-status-stopped/10 border-status-stopped/30',
  paused: 'text-status-paused bg-status-paused/10 border-status-paused/30',
  resumed: 'text-status-running bg-status-running/10 border-status-running/30',
  completed: 'text-status-active bg-status-active/10 border-status-active/30',
  error: 'text-status-error bg-status-error/10 border-status-error/30',
};

interface ActivityItemProps {
  activity: Activity;
  showEmployee?: boolean;
}

export function ActivityItem({ activity, showEmployee = true }: ActivityItemProps) {
  const Icon = eventIcons[activity.eventType] || Circle;
  const colorClass = eventColors[activity.eventType] || 'text-muted-foreground bg-muted/10 border-border';

  return (
    <div className="group flex items-start gap-3 rounded-lg p-2 transition-colors hover:bg-accent/50">
      {/* Icon */}
      <div
        className={cn(
          'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border',
          colorClass
        )}
      >
        <Icon className="h-4 w-4" />
      </div>

      {/* Content */}
      <div className="min-w-0 flex-1">
        <p className="text-sm text-foreground">
          {activity.description}
        </p>
        <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
          <span className="font-mono">{formatRelativeTime(activity.occurredAt)}</span>
          {showEmployee && activity.employeeId && (
            <>
              <span>•</span>
              <Link
                to={`/employees/${activity.employeeId}`}
                className="font-medium hover:text-primary hover:underline"
              >
                View Employee
              </Link>
            </>
          )}
        </div>
      </div>

      {/* Importance indicator */}
      {activity.importance >= 8 && (
        <div className="flex h-5 items-center rounded-full border border-status-error/30 bg-status-error/10 px-2">
          <span className="font-mono text-[10px] text-status-error uppercase">
            High
          </span>
        </div>
      )}
    </div>
  );
}
