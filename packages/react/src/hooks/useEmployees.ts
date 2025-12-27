/**
 * @empla/react - Employee Hooks
 *
 * React Query hooks for employee data fetching and mutations.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useEmplaApi } from '../provider';
import type { Employee, EmployeeCreate, EmployeeUpdate, PaginatedResponse } from '../types';

/**
 * Query keys for employees.
 */
export const employeeKeys = {
  all: ['employees'] as const,
  lists: () => [...employeeKeys.all, 'list'] as const,
  list: (params?: { page?: number; pageSize?: number; status?: string; role?: string }) =>
    [...employeeKeys.lists(), params] as const,
  details: () => [...employeeKeys.all, 'detail'] as const,
  detail: (id: string) => [...employeeKeys.details(), id] as const,
  status: (id: string) => [...employeeKeys.all, 'status', id] as const,
};

/**
 * Hook to list employees.
 *
 * @example
 * ```tsx
 * function EmployeeList() {
 *   const { data, isLoading } = useEmployees({ status: 'active' });
 *
 *   if (isLoading) return <Spinner />;
 *
 *   return (
 *     <ul>
 *       {data?.items.map(emp => (
 *         <li key={emp.id}>{emp.name}</li>
 *       ))}
 *     </ul>
 *   );
 * }
 * ```
 */
export function useEmployees(params?: {
  page?: number;
  pageSize?: number;
  status?: string;
  role?: string;
  enabled?: boolean;
}) {
  const api = useEmplaApi();
  const { enabled = true, ...queryParams } = params ?? {};

  return useQuery<PaginatedResponse<Employee>>({
    queryKey: employeeKeys.list(queryParams),
    queryFn: () => api.listEmployees(queryParams),
    enabled,
  });
}

/**
 * Hook to get a single employee.
 *
 * @example
 * ```tsx
 * function EmployeeDetail({ id }: { id: string }) {
 *   const { data: employee, isLoading } = useEmployee(id);
 *
 *   if (isLoading) return <Spinner />;
 *   if (!employee) return <NotFound />;
 *
 *   return <div>{employee.name}</div>;
 * }
 * ```
 */
export function useEmployee(id: string, options?: { enabled?: boolean }) {
  const api = useEmplaApi();

  return useQuery<Employee>({
    queryKey: employeeKeys.detail(id),
    queryFn: () => api.getEmployee(id),
    enabled: options?.enabled ?? !!id,
  });
}

/**
 * Hook to create an employee.
 *
 * @example
 * ```tsx
 * function CreateEmployee() {
 *   const createEmployee = useCreateEmployee();
 *
 *   const handleSubmit = async (data: EmployeeCreate) => {
 *     const employee = await createEmployee.mutateAsync(data);
 *     console.log('Created:', employee.id);
 *   };
 *
 *   return <EmployeeForm onSubmit={handleSubmit} />;
 * }
 * ```
 */
export function useCreateEmployee() {
  const api = useEmplaApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: EmployeeCreate) => api.createEmployee(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: employeeKeys.lists() });
    },
  });
}

/**
 * Hook to update an employee.
 *
 * @example
 * ```tsx
 * function EditEmployee({ employee }: { employee: Employee }) {
 *   const updateEmployee = useUpdateEmployee();
 *
 *   const handleSave = async (data: EmployeeUpdate) => {
 *     await updateEmployee.mutateAsync({ id: employee.id, data });
 *   };
 *
 *   return <EmployeeForm employee={employee} onSubmit={handleSave} />;
 * }
 * ```
 */
export function useUpdateEmployee() {
  const api = useEmplaApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: EmployeeUpdate }) =>
      api.updateEmployee(id, data),
    onSuccess: (employee) => {
      queryClient.setQueryData(employeeKeys.detail(employee.id), employee);
      queryClient.invalidateQueries({ queryKey: employeeKeys.lists() });
    },
  });
}

/**
 * Hook to delete an employee.
 *
 * @example
 * ```tsx
 * function DeleteButton({ id }: { id: string }) {
 *   const deleteEmployee = useDeleteEmployee();
 *
 *   return (
 *     <button onClick={() => deleteEmployee.mutate(id)}>
 *       Delete
 *     </button>
 *   );
 * }
 * ```
 */
export function useDeleteEmployee() {
  const api = useEmplaApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => api.deleteEmployee(id),
    onSuccess: (_, id) => {
      queryClient.removeQueries({ queryKey: employeeKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: employeeKeys.lists() });
    },
  });
}
