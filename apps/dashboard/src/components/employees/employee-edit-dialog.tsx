import { useEffect, useRef } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { useUpdateEmployee, type Employee, type LifecycleStage } from '@empla/react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

const editSchema = z.object({
  name: z.string().min(2, 'Name must be at least 2 characters').max(200),
  email: z.string().email('Invalid email address'),
  lifecycleStage: z.enum(['shadow', 'supervised', 'autonomous'] as const),
  capabilities: z.string(),
});

type EditFormData = z.infer<typeof editSchema>;

const lifecycleStages: { value: LifecycleStage; label: string }[] = [
  { value: 'shadow', label: 'Shadow' },
  { value: 'supervised', label: 'Supervised' },
  { value: 'autonomous', label: 'Autonomous' },
];

interface EmployeeEditDialogProps {
  employee: Employee;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function EmployeeEditDialog({ employee, open, onOpenChange }: EmployeeEditDialogProps) {
  const updateEmployee = useUpdateEmployee();

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    reset,
    formState: { errors },
  } = useForm<EditFormData>({
    resolver: zodResolver(editSchema),
    defaultValues: {
      name: employee.name,
      email: employee.email,
      lifecycleStage: employee.lifecycleStage,
      capabilities: employee.capabilities.join(', '),
    },
  });

  const prevOpenRef = useRef(false);
  useEffect(() => {
    if (open && !prevOpenRef.current) {
      reset({
        name: employee.name,
        email: employee.email,
        lifecycleStage: employee.lifecycleStage,
        capabilities: employee.capabilities.join(', '),
      });
    }
    prevOpenRef.current = open;
  }, [open, employee, reset]);

  const selectedStage = watch('lifecycleStage');

  const onSubmit = async (data: EditFormData) => {
    const capabilities = data.capabilities
      .split(',')
      .map((c) => c.trim())
      .filter(Boolean);

    try {
      await updateEmployee.mutateAsync({
        id: employee.id,
        data: {
          name: data.name,
          email: data.email,
          lifecycleStage: data.lifecycleStage,
          capabilities,
        },
      });

      toast.success('Employee updated', {
        description: `${data.name} has been updated`,
      });
      onOpenChange(false);
    } catch (error) {
      toast.error('Failed to update employee', {
        description: error instanceof Error ? error.message : 'Please try again',
      });
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle className="font-display">Edit Employee</DialogTitle>
          <DialogDescription>
            Update {employee.name}'s details
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {/* Name */}
          <div className="space-y-2">
            <Label htmlFor="edit-name">Name</Label>
            <Input
              id="edit-name"
              className="bg-background/50"
              {...register('name')}
            />
            {errors.name && (
              <p className="text-sm text-destructive">{errors.name.message}</p>
            )}
          </div>

          {/* Email */}
          <div className="space-y-2">
            <Label htmlFor="edit-email">Email</Label>
            <Input
              id="edit-email"
              type="email"
              className="bg-background/50"
              {...register('email')}
            />
            {errors.email && (
              <p className="text-sm text-destructive">{errors.email.message}</p>
            )}
          </div>

          {/* Lifecycle Stage */}
          <div className="space-y-2">
            <Label htmlFor="lifecycleStage-select">Lifecycle Stage</Label>
            <Select
              value={selectedStage}
              onValueChange={(v: LifecycleStage) => setValue('lifecycleStage', v)}
            >
              <SelectTrigger id="lifecycleStage-select" className="bg-background/50">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {lifecycleStages.map((s) => (
                  <SelectItem key={s.value} value={s.value}>
                    {s.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Capabilities */}
          <div className="space-y-2">
            <Label htmlFor="edit-capabilities">Capabilities</Label>
            <Input
              id="edit-capabilities"
              placeholder="email, calendar, crm"
              className="bg-background/50"
              {...register('capabilities')}
            />
            <p className="text-xs text-muted-foreground">Comma-separated list</p>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={updateEmployee.isPending}>
              {updateEmployee.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Saving...
                </>
              ) : (
                'Save Changes'
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
