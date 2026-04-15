import { useState } from 'react';
import {
  AlertCircle,
  CalendarClock,
  Plus,
  RefreshCw,
  Trash2,
  User,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  useCancelScheduledAction,
  useCreateScheduledAction,
  useSchedule,
  type ScheduledAction,
} from '@empla/react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

interface SchedulerPanelProps {
  employeeId: string;
}

// --- inline form ---------------------------------------------------------

function ScheduleRequestForm({
  employeeId,
  onDone,
}: {
  employeeId: string;
  onDone: () => void;
}) {
  const create = useCreateScheduledAction();
  const [description, setDescription] = useState('');
  const [scheduledFor, setScheduledFor] = useState('');
  const [recurring, setRecurring] = useState(false);
  const [intervalHours, setIntervalHours] = useState<string>('24');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!description.trim() || !scheduledFor) return;

    // <input type="datetime-local"> gives us a naive ISO string without tz.
    // Convert to UTC ISO with Z suffix so the backend's tz check passes.
    const scheduledForIso = new Date(scheduledFor).toISOString();

    try {
      await create.mutateAsync({
        employeeId,
        description: description.trim(),
        scheduledFor: scheduledForIso,
        recurring,
        intervalHours: recurring ? parseFloat(intervalHours) : undefined,
      });
      toast.success('Request filed. The employee will see it on its next cycle.');
      setDescription('');
      setScheduledFor('');
      setRecurring(false);
      setIntervalHours('24');
      onDone();
    } catch (err) {
      const msg =
        err instanceof Error && err.message ? err.message : 'Failed to file request';
      toast.error(msg);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3 rounded-lg border border-border/50 bg-muted/20 p-4">
      <div className="space-y-1.5">
        <Label htmlFor="scheduler-description" className="text-xs">
          What should the employee do?
        </Label>
        <Input
          id="scheduler-description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="e.g. check pipeline coverage and send a summary"
          maxLength={500}
          required
        />
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="scheduler-when" className="text-xs">
            When <span className="text-muted-foreground">(your local time)</span>
          </Label>
          <Input
            id="scheduler-when"
            type="datetime-local"
            value={scheduledFor}
            onChange={(e) => setScheduledFor(e.target.value)}
            required
          />
          {scheduledFor ? (
            <p className="font-mono text-[10px] text-muted-foreground">
              → {new Date(scheduledFor).toISOString()}
            </p>
          ) : null}
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs">Cadence</Label>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-1.5 text-sm">
              <input
                type="checkbox"
                checked={recurring}
                onChange={(e) => setRecurring(e.target.checked)}
              />
              <span>Recurring</span>
            </label>
            {recurring ? (
              <div className="flex items-center gap-1.5">
                <Input
                  type="number"
                  step="0.5"
                  min="0.5"
                  max="8760"
                  value={intervalHours}
                  onChange={(e) => setIntervalHours(e.target.value)}
                  className="h-9 w-24"
                />
                <span className="text-xs text-muted-foreground">hours between runs</span>
              </div>
            ) : null}
          </div>
        </div>
      </div>

      <div className="flex items-center justify-end gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" size="sm" disabled={create.isPending}>
          File request
        </Button>
      </div>
    </form>
  );
}

// --- row ----------------------------------------------------------------

function ScheduledActionRow({
  action,
  employeeId,
}: {
  action: ScheduledAction;
  employeeId: string;
}) {
  const cancel = useCancelScheduledAction();
  const userSourced = action.source === 'user_requested';

  const handleCancel = async () => {
    const verb = action.recurring ? 'Stop this recurring action?' : 'Cancel this action?';
    if (!window.confirm(verb)) return;
    try {
      await cancel.mutateAsync({ employeeId, actionId: action.id });
      toast.success('Cancelled');
    } catch (err) {
      const msg =
        err instanceof Error && err.message ? err.message : 'Failed to cancel';
      toast.error(msg);
    }
  };

  const when = new Date(action.scheduledFor);
  const isOverdue = when.getTime() < Date.now();

  return (
    <div className="rounded-lg border border-border/50 bg-muted/30 p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="truncate text-sm">{action.description}</p>
            {userSourced ? (
              <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-primary/30 bg-primary/10 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-primary">
                <User className="h-3 w-3" /> user
              </span>
            ) : null}
            {action.recurring ? (
              <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-border/60 bg-muted/60 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                <RefreshCw className="h-3 w-3" />
                every {action.intervalHours}h
              </span>
            ) : null}
          </div>
          <p
            className={
              'mt-1 font-mono text-[11px] ' +
              (isOverdue ? 'text-status-paused' : 'text-muted-foreground')
            }
          >
            {isOverdue ? 'Overdue · ' : ''}
            {when.toLocaleString()}
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={handleCancel}
          disabled={cancel.isPending}
        >
          <Trash2 className="mr-1.5 h-3.5 w-3.5" /> Cancel
        </Button>
      </div>
    </div>
  );
}

// --- panel --------------------------------------------------------------

export function SchedulerPanel({ employeeId }: SchedulerPanelProps) {
  const { data, isLoading, error, refetch } = useSchedule(employeeId);
  const [formOpen, setFormOpen] = useState(false);

  return (
    <Card className="border-border/50 bg-card/80 backdrop-blur-sm">
      <CardHeader className="flex flex-row items-center justify-between pb-3">
        <CardTitle className="font-display text-lg font-semibold">
          <CalendarClock className="mr-2 inline h-4 w-4 text-muted-foreground" />
          Scheduler {data ? `(${data.total})` : ''}
        </CardTitle>
        {!formOpen ? (
          <Button size="sm" variant="outline" onClick={() => setFormOpen(true)}>
            <Plus className="mr-1.5 h-3.5 w-3.5" /> Add request
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="space-y-3">
        {formOpen ? (
          <ScheduleRequestForm
            employeeId={employeeId}
            onDone={() => setFormOpen(false)}
          />
        ) : null}

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
            <h3 className="font-display text-lg">Couldn't load schedule</h3>
            <Button variant="outline" className="mt-4" onClick={() => refetch()}>
              Try again
            </Button>
          </div>
        ) : !data || data.items.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 text-center">
            <CalendarClock className="mb-4 h-10 w-10 text-muted-foreground/60" />
            <h3 className="font-display text-lg">Nothing queued</h3>
            <p className="mt-2 max-w-sm text-sm text-muted-foreground">
              The employee schedules its own work during its BDI cycles. You can also file a
              request and it'll see it on the next cycle.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {data.items.map((a) => (
              <ScheduledActionRow key={a.id} action={a} employeeId={employeeId} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
