/**
 * @empla/react - EmployeeForm Component
 *
 * Form for creating or editing employees.
 */

import { useState, type CSSProperties, type FormEvent, type ReactNode } from 'react';

import type { Employee, EmployeeCreate, EmployeeRole, EmployeeUpdate } from '../types';

/**
 * Form field configuration.
 */
interface FormField {
  name: string;
  label: string;
  type: 'text' | 'email' | 'select' | 'multiselect';
  options?: Array<{ value: string; label: string }>;
  required?: boolean;
  placeholder?: string;
}

/**
 * Available roles.
 */
const ROLE_OPTIONS: Array<{ value: EmployeeRole; label: string }> = [
  { value: 'sales_ae', label: 'Sales AE' },
  { value: 'csm', label: 'Customer Success Manager' },
  { value: 'pm', label: 'Product Manager' },
  { value: 'sdr', label: 'Sales Development Rep' },
  { value: 'recruiter', label: 'Recruiter' },
  { value: 'custom', label: 'Custom Role' },
];

/**
 * Available capabilities.
 */
const CAPABILITY_OPTIONS = [
  { value: 'email', label: 'Email' },
  { value: 'calendar', label: 'Calendar' },
  { value: 'crm', label: 'CRM' },
  { value: 'slack', label: 'Slack' },
  { value: 'meetings', label: 'Meetings' },
  { value: 'documents', label: 'Documents' },
];

/**
 * Props for EmployeeForm.
 */
export interface EmployeeFormProps {
  /** Existing employee for edit mode */
  employee?: Employee;

  /** Callback when form is submitted */
  onSubmit: (data: EmployeeCreate | EmployeeUpdate) => void | Promise<void>;

  /** Callback when form is cancelled */
  onCancel?: () => void;

  /** Whether the form is in a loading state */
  isLoading?: boolean;

  /** Error message to display */
  error?: string | null;

  /** Submit button text */
  submitLabel?: string;

  /** Cancel button text */
  cancelLabel?: string;

  /** Custom field renderer */
  renderField?: (field: FormField, value: unknown, onChange: (value: unknown) => void) => ReactNode;

  /** Additional CSS class */
  className?: string;

  /** Additional inline styles */
  style?: CSSProperties;
}

/**
 * Form for creating or editing employees.
 *
 * @example
 * ```tsx
 * // Create mode
 * const createEmployee = useCreateEmployee();
 * <EmployeeForm
 *   onSubmit={(data) => createEmployee.mutate(data)}
 *   isLoading={createEmployee.isPending}
 * />
 *
 * // Edit mode
 * const updateEmployee = useUpdateEmployee();
 * <EmployeeForm
 *   employee={employee}
 *   onSubmit={(data) => updateEmployee.mutate({ id: employee.id, data })}
 *   isLoading={updateEmployee.isPending}
 * />
 * ```
 */
export function EmployeeForm({
  employee,
  onSubmit,
  onCancel,
  isLoading = false,
  error,
  submitLabel,
  cancelLabel = 'Cancel',
  renderField: _renderField,
  className = '',
  style,
}: EmployeeFormProps) {
  const isEditMode = !!employee;

  const [formData, setFormData] = useState({
    name: employee?.name ?? '',
    email: employee?.email ?? '',
    role: employee?.role ?? 'sales_ae' as EmployeeRole,
    capabilities: employee?.capabilities ?? ['email'],
  });

  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});

  const formStyle: CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    gap: '20px',
    ...style,
  };

  const fieldStyle: CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  };

  const labelStyle: CSSProperties = {
    fontSize: '14px',
    fontWeight: 500,
    color: '#374151',
  };

  const inputStyle: CSSProperties = {
    padding: '10px 12px',
    border: '1px solid #E5E7EB',
    borderRadius: '6px',
    fontSize: '14px',
    color: '#111827',
    backgroundColor: '#FFFFFF',
  };

  const inputErrorStyle: CSSProperties = {
    ...inputStyle,
    borderColor: '#EF4444',
  };

  const errorTextStyle: CSSProperties = {
    fontSize: '12px',
    color: '#EF4444',
    marginTop: '4px',
  };

  const buttonContainerStyle: CSSProperties = {
    display: 'flex',
    gap: '12px',
    justifyContent: 'flex-end',
    marginTop: '8px',
  };

  const primaryButtonStyle: CSSProperties = {
    padding: '10px 20px',
    border: 'none',
    borderRadius: '6px',
    fontSize: '14px',
    fontWeight: 500,
    backgroundColor: '#10B981',
    color: '#FFFFFF',
    cursor: isLoading ? 'not-allowed' : 'pointer',
    opacity: isLoading ? 0.7 : 1,
  };

  const secondaryButtonStyle: CSSProperties = {
    padding: '10px 20px',
    border: '1px solid #E5E7EB',
    borderRadius: '6px',
    fontSize: '14px',
    fontWeight: 500,
    backgroundColor: '#FFFFFF',
    color: '#374151',
    cursor: 'pointer',
  };

  const checkboxContainerStyle: CSSProperties = {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '12px',
  };

  const checkboxLabelStyle: CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    fontSize: '14px',
    color: '#374151',
    cursor: 'pointer',
  };

  const validate = (): boolean => {
    const errors: Record<string, string> = {};

    if (!formData.name.trim()) {
      errors.name = 'Name is required';
    } else if (formData.name.length < 2) {
      errors.name = 'Name must be at least 2 characters';
    }

    if (!formData.email.trim()) {
      errors.email = 'Email is required';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      errors.email = 'Invalid email address';
    }

    if (formData.capabilities.length === 0) {
      errors.capabilities = 'At least one capability is required';
    }

    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();

    if (!validate()) {
      return;
    }

    const data = isEditMode
      ? {
          name: formData.name,
          email: formData.email,
          capabilities: formData.capabilities,
        }
      : {
          name: formData.name,
          email: formData.email,
          role: formData.role,
          capabilities: formData.capabilities,
        };

    try {
      await onSubmit(data);
    } catch {
      // Error handling is delegated to the parent via the `error` prop
      // or handled by the mutation's onError callback
    }
  };

  const handleCapabilityToggle = (capability: string) => {
    setFormData((prev) => ({
      ...prev,
      capabilities: prev.capabilities.includes(capability)
        ? prev.capabilities.filter((c) => c !== capability)
        : [...prev.capabilities, capability],
    }));
  };

  return (
    <form className={className} style={formStyle} onSubmit={handleSubmit}>
      {error && (
        <div style={{ padding: '12px', backgroundColor: '#FEE2E2', borderRadius: '6px', color: '#991B1B' }}>
          {error}
        </div>
      )}

      {/* Name Field */}
      <div style={fieldStyle}>
        <label style={labelStyle} htmlFor="name">
          Name <span style={{ color: '#EF4444' }}>*</span>
        </label>
        <input
          id="name"
          type="text"
          value={formData.name}
          onChange={(e) => setFormData((prev) => ({ ...prev, name: e.target.value }))}
          placeholder="e.g., Jordan Chen"
          style={validationErrors.name ? inputErrorStyle : inputStyle}
          disabled={isLoading}
        />
        {validationErrors.name && <span style={errorTextStyle}>{validationErrors.name}</span>}
      </div>

      {/* Email Field */}
      <div style={fieldStyle}>
        <label style={labelStyle} htmlFor="email">
          Email <span style={{ color: '#EF4444' }}>*</span>
        </label>
        <input
          id="email"
          type="email"
          value={formData.email}
          onChange={(e) => setFormData((prev) => ({ ...prev, email: e.target.value }))}
          placeholder="e.g., jordan@company.com"
          style={validationErrors.email ? inputErrorStyle : inputStyle}
          disabled={isLoading}
        />
        {validationErrors.email && <span style={errorTextStyle}>{validationErrors.email}</span>}
      </div>

      {/* Role Field (only in create mode) */}
      {!isEditMode && (
        <div style={fieldStyle}>
          <label style={labelStyle} htmlFor="role">
            Role <span style={{ color: '#EF4444' }}>*</span>
          </label>
          <select
            id="role"
            value={formData.role}
            onChange={(e) => setFormData((prev) => ({ ...prev, role: e.target.value as EmployeeRole }))}
            style={inputStyle}
            disabled={isLoading}
          >
            {ROLE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Capabilities Field */}
      <div style={fieldStyle}>
        <label style={labelStyle}>
          Capabilities <span style={{ color: '#EF4444' }}>*</span>
        </label>
        <div style={checkboxContainerStyle}>
          {CAPABILITY_OPTIONS.map((option) => (
            <label key={option.value} style={checkboxLabelStyle}>
              <input
                type="checkbox"
                checked={formData.capabilities.includes(option.value)}
                onChange={() => handleCapabilityToggle(option.value)}
                disabled={isLoading}
              />
              {option.label}
            </label>
          ))}
        </div>
        {validationErrors.capabilities && (
          <span style={errorTextStyle}>{validationErrors.capabilities}</span>
        )}
      </div>

      {/* Buttons */}
      <div style={buttonContainerStyle}>
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            style={secondaryButtonStyle}
            disabled={isLoading}
          >
            {cancelLabel}
          </button>
        )}
        <button
          type="submit"
          style={primaryButtonStyle}
          disabled={isLoading}
        >
          {isLoading ? 'Saving...' : (submitLabel ?? (isEditMode ? 'Save Changes' : 'Create Employee'))}
        </button>
      </div>
    </form>
  );
}

/**
 * Props for DeleteEmployeeButton.
 */
export interface DeleteEmployeeButtonProps {
  /** Callback when delete is confirmed */
  onDelete: () => void | Promise<void>;

  /** Whether deletion is in progress */
  isLoading?: boolean;

  /** Require confirmation before deleting */
  confirmMessage?: string;

  /** Button content */
  children?: ReactNode;

  /** Additional CSS class */
  className?: string;

  /** Additional inline styles */
  style?: CSSProperties;
}

/**
 * Button to delete an employee with confirmation.
 *
 * @example
 * ```tsx
 * const deleteEmployee = useDeleteEmployee();
 *
 * <DeleteEmployeeButton
 *   onDelete={() => deleteEmployee.mutate(employee.id)}
 *   isLoading={deleteEmployee.isPending}
 * />
 * ```
 */
export function DeleteEmployeeButton({
  onDelete,
  isLoading = false,
  confirmMessage = 'Are you sure you want to delete this employee? This action cannot be undone.',
  children = 'Delete Employee',
  className = '',
  style,
}: DeleteEmployeeButtonProps) {
  const handleClick = async () => {
    if (window.confirm(confirmMessage)) {
      try {
        await onDelete();
      } catch {
        // Error is expected to be handled by the caller
      }
    }
  };

  const buttonStyle: CSSProperties = {
    padding: '10px 20px',
    border: 'none',
    borderRadius: '6px',
    fontSize: '14px',
    fontWeight: 500,
    backgroundColor: '#EF4444',
    color: '#FFFFFF',
    cursor: isLoading ? 'not-allowed' : 'pointer',
    opacity: isLoading ? 0.7 : 1,
    ...style,
  };

  return (
    <button
      type="button"
      className={className}
      style={buttonStyle}
      onClick={handleClick}
      disabled={isLoading}
    >
      {isLoading ? 'Deleting...' : children}
    </button>
  );
}
