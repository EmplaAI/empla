// Static UI constants that don't come from the API.
// Role data (descriptions, personality presets) is now served by GET /v1/roles
// and consumed via the useRoles() hook.

import type { RoleDefinition } from '@empla/react';

/**
 * Build a role-description lookup map from API role data.
 */
export function buildRoleDescriptions(roles: RoleDefinition[]): Record<string, string> {
  const map: Record<string, string> = {};
  for (const r of roles) {
    map[r.code] = r.description;
  }
  return map;
}

/**
 * Build personality preset options from API role data.
 * Includes "default" and "custom" bookends plus every role that has a preset.
 */
export function buildPersonalityPresets(
  roles: RoleDefinition[],
): { value: string; label: string }[] {
  const presets: { value: string; label: string }[] = [
    { value: 'default', label: 'Role Default' },
  ];
  for (const r of roles) {
    if (r.hasPersonalityPreset) {
      presets.push({ value: r.code, label: r.title });
    }
  }
  presets.push({ value: 'custom', label: 'Custom' });
  return presets;
}
