import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { toast } from 'sonner';
import { useCreateEmployee } from '@empla/react';
import type { GeneratedRoleDraft } from '@empla/react';
import { Button } from '@/components/ui/button';
import { EmployeeForm } from '@/components/employees/employee-form';
import { RoleBuilderCard } from '@/components/employees/role-builder-card';

/**
 * Hidden draft state — the LLM-generated capabilities, goals, and
 * personality that don't yet have a dedicated form widget. The visible
 * form lets the user edit name + email + role + roleDescription; this
 * state carries the rest through to the create call.
 *
 * Cleared the moment the user changes role away from 'custom' so a
 * stale draft can't leak into a built-in employee.
 */
interface CustomDraft {
  capabilities: string[];
  goals: GeneratedRoleDraft['goals'];
  personality: Record<string, number>;
}

export function EmployeeNewPage() {
  const navigate = useNavigate();
  const createEmployee = useCreateEmployee();
  const [selectedRole, setSelectedRole] = useState('sales_ae');
  const [draft, setDraft] = useState<CustomDraft | null>(null);
  // Pre-fill values pushed into the form when the LLM draft lands.
  // The form owns its own state via react-hook-form, so we use these
  // overrides to seed it on draft updates.
  const [overrides, setOverrides] = useState<{
    name?: string;
    roleDescription?: string;
  }>({});

  const handleDraft = (d: GeneratedRoleDraft) => {
    setDraft({
      capabilities: d.capabilities,
      goals: d.goals,
      personality: d.personality,
    });
    setOverrides({
      name: d.nameSuggestion,
      roleDescription: d.roleDescription,
    });
  };

  const handleRoleChange = (role: string) => {
    setSelectedRole(role);
    if (role !== 'custom') {
      // Don't carry custom-role state into a built-in employee creation.
      setDraft(null);
      setOverrides({});
    }
  };

  const handleSubmit = async (data: {
    name: string;
    email: string;
    role: string;
    roleDescription?: string;
    personalityPreset?: string;
  }) => {
    try {
      const trimmedDescription = data.roleDescription?.trim();

      // Built-in role path — preserve the existing config.role_description
      // override behavior.
      if (data.role !== 'custom') {
        const config: Record<string, unknown> = {};
        if (trimmedDescription) {
          config.role_description = trimmedDescription;
        }
        const personality =
          data.personalityPreset && data.personalityPreset !== 'default'
            ? { preset: data.personalityPreset }
            : undefined;

        const employee = await createEmployee.mutateAsync({
          name: data.name,
          email: data.email,
          role: data.role as 'sales_ae' | 'csm' | 'pm' | 'sdr' | 'recruiter',
          ...(Object.keys(config).length > 0 ? { config } : {}),
          ...(personality ? { personality } : {}),
        });

        toast.success('Employee created', {
          description: `${employee.name} has been added to your workforce`,
        });
        navigate(`/employees/${employee.id}`);
        return;
      }

      // Custom role path — must carry roleDescription + non-empty goals.
      // The LLM draft is the source of capabilities/goals/personality; if
      // the user skipped the Generate step, surface a clear error rather
      // than silently shipping defaults.
      if (!trimmedDescription) {
        toast.error('A role description is required for custom employees');
        return;
      }
      if (!draft || draft.goals.length === 0) {
        toast.error('Use "Describe the job" above to generate goals first', {
          description: 'Custom employees need at least one goal to start working.',
        });
        return;
      }

      const employee = await createEmployee.mutateAsync({
        name: data.name,
        email: data.email,
        role: 'custom',
        roleDescription: trimmedDescription,
        capabilities: draft.capabilities,
        goals: draft.goals,
        personality: draft.personality,
      });

      toast.success('Custom employee created', {
        description: `${employee.name} is ready. Review the goals on the detail page before starting.`,
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

      <div className="max-w-2xl space-y-6">
        {selectedRole === 'custom' && (
          <RoleBuilderCard onDraft={handleDraft} isActive={selectedRole === 'custom'} />
        )}
        <EmployeeForm
          onSubmit={handleSubmit}
          onRoleChange={handleRoleChange}
          isLoading={createEmployee.isPending}
          overrides={overrides}
        />
      </div>
    </div>
  );
}
