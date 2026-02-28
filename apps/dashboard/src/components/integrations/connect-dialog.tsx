import { useState } from 'react';
import { Loader2, AlertCircle } from 'lucide-react';
import { toast } from 'sonner';
import { useEmployees, useConnectProvider, type ProviderInfo } from '@empla/react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

interface ConnectDialogProps {
  provider: ProviderInfo | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ConnectDialog({ provider, open, onOpenChange }: ConnectDialogProps) {
  const [selectedEmployeeId, setSelectedEmployeeId] = useState<string>('');
  const { data: employeesData, isLoading: isEmployeesLoading, isError: isEmployeesError } = useEmployees({ pageSize: 100 });
  const connectMutation = useConnectProvider();

  const employees = employeesData?.items ?? [];

  function handleConnect() {
    if (!provider || !selectedEmployeeId) return;

    connectMutation.mutate(
      {
        provider: provider.provider,
        employeeId: selectedEmployeeId,
        redirectAfter: '/integrations',
      },
      {
        onError: (error) => {
          toast.error(`Failed to connect: ${error.message}`);
        },
      }
    );
  }

  function handleOpenChange(nextOpen: boolean) {
    if (!nextOpen) {
      setSelectedEmployeeId('');
    }
    onOpenChange(nextOpen);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Connect {provider?.displayName}</DialogTitle>
          <DialogDescription>
            Select an employee to authorize with {provider?.displayName}.
            They'll be able to use {provider?.description?.toLowerCase()}.
          </DialogDescription>
        </DialogHeader>

        <div className="py-4">
          <label className="mb-2 block text-sm font-medium">Employee</label>
          {isEmployeesError ? (
            <div className="flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-3">
              <AlertCircle className="h-4 w-4 text-destructive" />
              <p className="text-sm text-destructive">
                Failed to load employees. Please close and try again.
              </p>
            </div>
          ) : isEmployeesLoading ? (
            <div className="flex items-center gap-2 p-3 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading employees...
            </div>
          ) : (
            <Select value={selectedEmployeeId} onValueChange={setSelectedEmployeeId}>
              <SelectTrigger>
                <SelectValue placeholder="Select an employee..." />
              </SelectTrigger>
              <SelectContent>
                {employees.map((emp) => (
                  <SelectItem key={emp.id} value={emp.id}>
                    {emp.name}{emp.email ? ` (${emp.email})` : ''}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleConnect}
            disabled={!selectedEmployeeId || connectMutation.isPending || isEmployeesError}
          >
            {connectMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Authorize
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
