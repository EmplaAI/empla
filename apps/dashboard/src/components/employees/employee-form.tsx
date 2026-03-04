import { useEffect, useMemo, useRef } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Loader2 } from 'lucide-react';
import { useRoles } from '@empla/react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { buildRoleDescriptions, buildPersonalityPresets } from './constants';

const formSchema = z.object({
  name: z.string().min(2, 'Name must be at least 2 characters'),
  email: z.string().email('Invalid email address'),
  role: z.string().min(1, 'Role is required'),
  roleDescription: z.string().optional(),
  personalityPreset: z.string().optional(),
});

type FormData = z.infer<typeof formSchema>;

interface EmployeeFormProps {
  onSubmit: (data: FormData) => Promise<void>;
  isLoading?: boolean;
}

export function EmployeeForm({ onSubmit, isLoading }: EmployeeFormProps) {
  const { data: rolesData } = useRoles();
  const apiRoles = rolesData?.roles ?? [];

  const roleDescriptions = useMemo(() => buildRoleDescriptions(apiRoles), [apiRoles]);
  const personalityPresets = useMemo(() => buildPersonalityPresets(apiRoles), [apiRoles]);

  // Build role options from API, always include "custom" at the end
  const roles = useMemo(() => {
    const items = apiRoles.map((r) => ({
      value: r.code,
      label: r.title,
      description: r.shortDescription,
    }));
    items.push({ value: 'custom', label: 'Custom', description: 'Custom role configuration' });
    return items;
  }, [apiRoles]);

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    getValues,
    formState: { errors },
  } = useForm<FormData>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      name: '',
      email: '',
      role: 'sales_ae',
      roleDescription: roleDescriptions['sales_ae'] ?? '',
      personalityPreset: 'default',
    },
  });

  const selectedRole = watch('role');
  const prevRoleRef = useRef(selectedRole);

  // Populate roleDescription once roleDescriptions loads from the API.
  // Without this, the field is empty on first render because useForm
  // defaultValues are evaluated before the async data arrives.
  const initializedRef = useRef(false);
  useEffect(() => {
    if (initializedRef.current || !Object.keys(roleDescriptions).length) return;
    const currentDesc = getValues('roleDescription') ?? '';
    if (!currentDesc) {
      setValue('roleDescription', roleDescriptions[selectedRole] ?? '');
    }
    initializedRef.current = true;
  }, [roleDescriptions, selectedRole, getValues, setValue]);

  // Pre-fill role description when role changes, but only if the current
  // value is empty or still matches the previous role's default.
  // For "custom" role, clear the stale default so the user starts fresh.
  useEffect(() => {
    if (selectedRole === prevRoleRef.current) return;
    const currentDesc = getValues('roleDescription') ?? '';
    const prevDefault = roleDescriptions[prevRoleRef.current] ?? '';
    if (!currentDesc || currentDesc === prevDefault) {
      setValue('roleDescription', selectedRole === 'custom' ? '' : (roleDescriptions[selectedRole] ?? ''));
    }
    prevRoleRef.current = selectedRole;
  }, [selectedRole, setValue, getValues, roleDescriptions]);

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
              onValueChange={(value) => setValue('role', value)}
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

          {/* Role summary */}
          <div className="rounded-lg border border-border bg-muted/30 p-4">
            <p className="text-sm text-muted-foreground">
              {roles.find((r) => r.value === selectedRole)?.description}
            </p>
          </div>
        </CardContent>
      </Card>

      <Card className="border-border/50 bg-card/80 backdrop-blur-sm">
        <CardHeader>
          <CardTitle className="font-display">Identity & Personality</CardTitle>
          <CardDescription>
            Customize how this employee describes itself and behaves
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Role Description */}
          <div className="space-y-2">
            <Label htmlFor="roleDescription">Role Description</Label>
            <Textarea
              id="roleDescription"
              placeholder="Describe what this employee does..."
              className="bg-background/50 min-h-[100px]"
              {...register('roleDescription')}
            />
            <p className="text-xs text-muted-foreground">
              This description is included in every LLM prompt so the employee knows its purpose.
            </p>
          </div>

          {/* Personality Preset */}
          <div className="space-y-2">
            <Label htmlFor="personalityPreset">Personality Preset</Label>
            <Select
              value={watch('personalityPreset') ?? 'default'}
              onValueChange={(value) => setValue('personalityPreset', value)}
            >
              <SelectTrigger className="bg-background/50">
                <SelectValue placeholder="Select a preset" />
              </SelectTrigger>
              <SelectContent>
                {personalityPresets.map((preset) => (
                  <SelectItem key={preset.value} value={preset.value}>
                    {preset.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Controls communication style, risk tolerance, and decision-making traits.
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
