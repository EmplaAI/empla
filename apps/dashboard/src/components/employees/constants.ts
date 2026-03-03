// Default role descriptions matching the backend ROLE_DESCRIPTIONS
export const ROLE_DESCRIPTIONS: Record<string, string> = {
  sales_ae:
    'You build and manage sales pipeline, prospect new accounts, and close revenue.',
  csm: 'You ensure customer success through onboarding, health monitoring, and retention.',
  pm: 'You drive product strategy, prioritize features, and ship high-impact releases.',
  sdr: 'You generate qualified leads through outbound prospecting and inbound qualification.',
  recruiter:
    'You source, screen, and hire top talent to build high-performing teams.',
};

export const PERSONALITY_PRESETS = [
  { value: 'default', label: 'Role Default' },
  { value: 'sales_ae', label: 'Sales AE' },
  { value: 'csm', label: 'Customer Success' },
  { value: 'pm', label: 'Product Manager' },
  { value: 'custom', label: 'Custom' },
] as const;

export const PERSONALITY_PRESET_VALUES = PERSONALITY_PRESETS.map((p) => p.value);
