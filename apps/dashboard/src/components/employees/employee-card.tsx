import { Link } from 'react-router-dom';
import { MoreHorizontal, Play, Pause, Square, ExternalLink } from 'lucide-react';
import type { Employee } from '@empla/react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { EmployeeStatusBadge, LifecycleBadge } from './employee-status-badge';
import { formatRelativeTime, formatRole, getInitials, cn } from '@/lib/utils';

interface EmployeeCardProps {
  employee: Employee;
  onStart?: () => void;
  onStop?: () => void;
  onPause?: () => void;
}

export function EmployeeCard({ employee, onStart, onStop, onPause }: EmployeeCardProps) {
  const canStart = employee.status === 'active' && !employee.isRunning;
  const canStop = employee.isRunning;
  const canPause = employee.isRunning;

  return (
    <Card className="group relative overflow-hidden border-border/50 bg-card/80 backdrop-blur-sm transition-all duration-300 hover:border-border hover:shadow-lg">
      {/* Running indicator */}
      {employee.isRunning && (
        <div className="absolute left-0 top-0 h-full w-0.5 bg-status-running shadow-[0_0_8px] shadow-status-running" />
      )}

      <CardContent className="p-4">
        <div className="flex items-start gap-4">
          {/* Avatar */}
          <Avatar className="h-12 w-12 border-2 border-border">
            <AvatarFallback
              className={cn(
                'font-mono text-sm font-semibold',
                employee.isRunning
                  ? 'bg-status-running/10 text-status-running'
                  : 'bg-primary/10 text-primary'
              )}
            >
              {getInitials(employee.name)}
            </AvatarFallback>
          </Avatar>

          {/* Info */}
          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between">
              <div>
                <Link
                  to={`/employees/${employee.id}`}
                  className="font-display font-semibold hover:text-primary hover:underline"
                >
                  {employee.name}
                </Link>
                <p className="text-sm text-muted-foreground">
                  {formatRole(employee.role)}
                </p>
              </div>

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 opacity-0 transition-opacity group-hover:opacity-100"
                  >
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem asChild>
                    <Link to={`/employees/${employee.id}`}>
                      <ExternalLink className="mr-2 h-4 w-4" />
                      View Details
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  {canStart && (
                    <DropdownMenuItem onClick={onStart}>
                      <Play className="mr-2 h-4 w-4" />
                      Start
                    </DropdownMenuItem>
                  )}
                  {canPause && (
                    <DropdownMenuItem onClick={onPause}>
                      <Pause className="mr-2 h-4 w-4" />
                      Pause
                    </DropdownMenuItem>
                  )}
                  {canStop && (
                    <DropdownMenuItem onClick={onStop} className="text-destructive">
                      <Square className="mr-2 h-4 w-4" />
                      Stop
                    </DropdownMenuItem>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            </div>

            {/* Badges */}
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <EmployeeStatusBadge status={employee.status} isRunning={employee.isRunning} />
              <LifecycleBadge stage={employee.lifecycleStage} />
            </div>

            {/* Meta */}
            <div className="mt-3 flex items-center gap-4 text-xs text-muted-foreground">
              <span className="font-mono">
                ID: {employee.id.slice(0, 8)}
              </span>
              <span>•</span>
              <span>
                Created {formatRelativeTime(employee.createdAt)}
              </span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
