import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { toast } from 'sonner';
import { useCreateEmployee } from '@empla/react';
import { Button } from '@/components/ui/button';
import { EmployeeForm } from '@/components/employees/employee-form';

export function EmployeeNewPage() {
  const navigate = useNavigate();
  const createEmployee = useCreateEmployee();

  const handleSubmit = async (data: {
    name: string;
    email: string;
    role: string;
    roleDescription?: string;
    personalityPreset?: string;
  }) => {
    try {
      const config: Record<string, unknown> = {};
      const trimmedDescription = data.roleDescription?.trim();
      if (trimmedDescription) {
        config.role_description = trimmedDescription;
      }

      const personality: Record<string, unknown> | undefined =
        data.personalityPreset && data.personalityPreset !== 'default'
          ? { preset: data.personalityPreset }
          : undefined;

      const employee = await createEmployee.mutateAsync({
        name: data.name,
        email: data.email,
        role: data.role as 'sales_ae' | 'csm' | 'pm' | 'sdr' | 'recruiter' | 'custom',
        ...(Object.keys(config).length > 0 ? { config } : {}),
        ...(personality ? { personality } : {}),
      });

      toast.success('Employee created', {
        description: `${employee.name} has been added to your workforce`,
      });

      navigate(`/employees/${employee.id}`);
    } catch (error) {
      toast.error('Failed to create employee', {
        description: error instanceof Error ? error.message : 'Please try again',
      });
      throw error;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" asChild>
          <Link to="/employees">
            <ArrowLeft className="h-4 w-4" />
          </Link>
        </Button>
        <div>
          <h2 className="font-display text-2xl font-bold tracking-tight">
            Create Employee
          </h2>
          <p className="text-sm text-muted-foreground">
            Add a new digital employee to your workforce
          </p>
        </div>
      </div>

      {/* Form */}
      <div className="max-w-2xl">
        <EmployeeForm onSubmit={handleSubmit} isLoading={createEmployee.isPending} />
      </div>
    </div>
  );
}
