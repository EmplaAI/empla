import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

interface ActivityFiltersProps {
  eventType: string;
  importance: string;
  timeRange: string;
  onEventTypeChange: (value: string) => void;
  onImportanceChange: (value: string) => void;
  onTimeRangeChange: (value: string) => void;
}

const eventTypes = [
  { value: 'all', label: 'All Events' },
  { value: 'started', label: 'Started' },
  { value: 'stopped', label: 'Stopped' },
  { value: 'paused', label: 'Paused' },
  { value: 'resumed', label: 'Resumed' },
  { value: 'message', label: 'Message' },
  { value: 'email', label: 'Email' },
  { value: 'meeting', label: 'Meeting' },
  { value: 'completed', label: 'Completed' },
  { value: 'error', label: 'Error' },
];

const importanceLevels = [
  { value: 'all', label: 'All Importance' },
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
];

const timeRanges = [
  { value: '24h', label: 'Last 24 hours' },
  { value: '7d', label: 'Last 7 days' },
  { value: '30d', label: 'Last 30 days' },
  { value: 'all', label: 'All time' },
];

export function ActivityFilters({
  eventType,
  importance,
  timeRange,
  onEventTypeChange,
  onImportanceChange,
  onTimeRangeChange,
}: ActivityFiltersProps) {
  return (
    <div className="flex flex-wrap gap-3">
      <Select value={eventType} onValueChange={onEventTypeChange}>
        <SelectTrigger className="w-[160px] bg-card/80" aria-label="Event type">
          <SelectValue placeholder="Event type" />
        </SelectTrigger>
        <SelectContent>
          {eventTypes.map((t) => (
            <SelectItem key={t.value} value={t.value}>
              {t.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select value={importance} onValueChange={onImportanceChange}>
        <SelectTrigger className="w-[170px] bg-card/80" aria-label="Importance">
          <SelectValue placeholder="Importance" />
        </SelectTrigger>
        <SelectContent>
          {importanceLevels.map((l) => (
            <SelectItem key={l.value} value={l.value}>
              {l.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select value={timeRange} onValueChange={onTimeRangeChange}>
        <SelectTrigger className="w-[170px] bg-card/80" aria-label="Time range">
          <SelectValue placeholder="Time range" />
        </SelectTrigger>
        <SelectContent>
          {timeRanges.map((r) => (
            <SelectItem key={r.value} value={r.value}>
              {r.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
