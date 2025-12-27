import type { EmployeeStatus, EmployeeRole } from '@empla/react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

interface EmployeeFiltersProps {
  status: EmployeeStatus | 'all';
  role: EmployeeRole | 'all';
  onStatusChange: (status: EmployeeStatus | 'all') => void;
  onRoleChange: (role: EmployeeRole | 'all') => void;
}

const statuses: { value: EmployeeStatus | 'all'; label: string }[] = [
  { value: 'all', label: 'All Statuses' },
  { value: 'active', label: 'Active' },
  { value: 'onboarding', label: 'Onboarding' },
  { value: 'paused', label: 'Paused' },
  { value: 'stopped', label: 'Stopped' },
  { value: 'terminated', label: 'Terminated' },
];

const roles: { value: EmployeeRole | 'all'; label: string }[] = [
  { value: 'all', label: 'All Roles' },
  { value: 'sales_ae', label: 'Sales AE' },
  { value: 'csm', label: 'Customer Success' },
  { value: 'pm', label: 'Product Manager' },
  { value: 'sdr', label: 'Sales Development' },
  { value: 'recruiter', label: 'Recruiter' },
  { value: 'custom', label: 'Custom' },
];

export function EmployeeFilters({
  status,
  role,
  onStatusChange,
  onRoleChange,
}: EmployeeFiltersProps) {
  return (
    <div className="flex flex-wrap gap-3">
      <Select value={status} onValueChange={(v) => onStatusChange(v as EmployeeStatus | 'all')}>
        <SelectTrigger className="w-[160px] bg-card/80">
          <SelectValue placeholder="Filter by status" />
        </SelectTrigger>
        <SelectContent>
          {statuses.map((s) => (
            <SelectItem key={s.value} value={s.value}>
              {s.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select value={role} onValueChange={(v) => onRoleChange(v as EmployeeRole | 'all')}>
        <SelectTrigger className="w-[180px] bg-card/80">
          <SelectValue placeholder="Filter by role" />
        </SelectTrigger>
        <SelectContent>
          {roles.map((r) => (
            <SelectItem key={r.value} value={r.value}>
              {r.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
