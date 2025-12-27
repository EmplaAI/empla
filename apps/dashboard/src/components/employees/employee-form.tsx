import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Loader2 } from 'lucide-react';
import type { EmployeeRole } from '@empla/react';
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
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';

const formSchema = z.object({
  name: z.string().min(2, 'Name must be at least 2 characters'),
  email: z.string().email('Invalid email address'),
  role: z.enum(['sales_ae', 'csm', 'pm', 'sdr', 'recruiter', 'custom'] as const),
});

type FormData = z.infer<typeof formSchema>;

const roles: { value: EmployeeRole; label: string; description: string }[] = [
  { value: 'sales_ae', label: 'Sales AE', description: 'Account Executive for sales' },
  { value: 'csm', label: 'Customer Success', description: 'Customer relationship manager' },
  { value: 'pm', label: 'Product Manager', description: 'Product development lead' },
  { value: 'sdr', label: 'Sales Development', description: 'Lead generation specialist' },
  { value: 'recruiter', label: 'Recruiter', description: 'Talent acquisition' },
  { value: 'custom', label: 'Custom', description: 'Custom role configuration' },
];

interface EmployeeFormProps {
  onSubmit: (data: FormData) => Promise<void>;
  isLoading?: boolean;
}

export function EmployeeForm({ onSubmit, isLoading }: EmployeeFormProps) {
  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = useForm<FormData>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      name: '',
      email: '',
      role: 'sales_ae',
    },
  });

  const selectedRole = watch('role');

  const onFormSubmit = async (data: FormData) => {
    try {
      await onSubmit(data);
    } catch {
      // Error handling is done in the parent
    }
  };

  return (
    <form onSubmit={handleSubmit(onFormSubmit)} className="space-y-6">
      <Card className="border-border/50 bg-card/80 backdrop-blur-sm">
        <CardHeader>
          <CardTitle className="font-display">Basic Information</CardTitle>
          <CardDescription>
            Enter the employee's name and contact information
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Name */}
          <div className="space-y-2">
            <Label htmlFor="name">Name</Label>
            <Input
              id="name"
              placeholder="Jordan Chen"
              className="bg-background/50"
              {...register('name')}
            />
            {errors.name && (
              <p className="text-sm text-destructive">{errors.name.message}</p>
            )}
          </div>

          {/* Email */}
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              placeholder="jordan.chen@company.com"
              className="bg-background/50"
              {...register('email')}
            />
            {errors.email && (
              <p className="text-sm text-destructive">{errors.email.message}</p>
            )}
          </div>
        </CardContent>
      </Card>

      <Card className="border-border/50 bg-card/80 backdrop-blur-sm">
        <CardHeader>
          <CardTitle className="font-display">Role Configuration</CardTitle>
          <CardDescription>
            Select the role that defines this employee's capabilities
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Role */}
          <div className="space-y-2">
            <Label htmlFor="role">Role</Label>
            <Select
              value={selectedRole}
              onValueChange={(value: EmployeeRole) => setValue('role', value)}
            >
              <SelectTrigger className="bg-background/50">
                <SelectValue placeholder="Select a role" />
              </SelectTrigger>
              <SelectContent>
                {roles.map((role) => (
                  <SelectItem key={role.value} value={role.value}>
                    <div className="flex flex-col items-start">
                      <span>{role.label}</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {errors.role && (
              <p className="text-sm text-destructive">{errors.role.message}</p>
            )}
          </div>

          {/* Role description */}
          <div className="rounded-lg border border-border bg-muted/30 p-4">
            <p className="text-sm text-muted-foreground">
              {roles.find((r) => r.value === selectedRole)?.description}
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Submit */}
      <div className="flex justify-end gap-3">
        <Button type="submit" disabled={isLoading}>
          {isLoading ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Creating...
            </>
          ) : (
            'Create Employee'
          )}
        </Button>
      </div>
    </form>
  );
}
