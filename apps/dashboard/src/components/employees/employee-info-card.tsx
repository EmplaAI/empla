import type { Employee } from '@empla/react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { formatDate, formatRole } from '@/lib/utils';

interface EmployeeInfoCardProps {
  employee: Employee;
}

export function EmployeeInfoCard({ employee }: EmployeeInfoCardProps) {
  const infoItems = [
    { label: 'Email', value: employee.email },
    { label: 'Role', value: formatRole(employee.role) },
    { label: 'Created', value: formatDate(employee.createdAt) },
    { label: 'Updated', value: formatDate(employee.updatedAt) },
    ...(employee.onboardedAt
      ? [{ label: 'Onboarded', value: formatDate(employee.onboardedAt) }]
      : []),
    ...(employee.activatedAt
      ? [{ label: 'Activated', value: formatDate(employee.activatedAt) }]
      : []),
  ];

  return (
    <Card className="border-border/50 bg-card/80 backdrop-blur-sm">
      <CardHeader className="pb-3">
        <CardTitle className="text-base font-display">Details</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {infoItems.map((item, index) => (
          <div key={item.label}>
            <div className="flex items-center justify-between py-1">
              <span className="text-sm text-muted-foreground">{item.label}</span>
              <span className="text-sm font-medium text-right truncate max-w-[200px]">
                {item.value}
              </span>
            </div>
            {index < infoItems.length - 1 && <Separator className="mt-2" />}
          </div>
        ))}

        {/* Capabilities */}
        {employee.capabilities.length > 0 && (
          <>
            <Separator className="my-3" />
            <div>
              <span className="text-sm text-muted-foreground">Capabilities</span>
              <div className="mt-2 flex flex-wrap gap-1">
                {employee.capabilities.map((cap) => (
                  <span
                    key={cap}
                    className="rounded-md border border-border bg-muted/50 px-2 py-0.5 font-mono text-xs"
                  >
                    {cap}
                  </span>
                ))}
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
