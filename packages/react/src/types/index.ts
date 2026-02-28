/**
 * @empla/react - Type Definitions
 *
 * Core types for the empla React SDK.
 */

/**
 * Configuration for the EmplaProvider.
 */
export interface EmplaConfig {
  /** Base URL for the empla API (e.g., "https://api.empla.io" or "/api") */
  apiUrl: string;

  /** Authentication token (optional, can be set later) */
  authToken?: string;

  /** Callback when authentication fails (e.g., token expired) */
  onAuthError?: () => void;

  /** Theme mode */
  theme?: 'light' | 'dark' | 'system';

  /** Default polling interval in seconds for auto-refresh */
  defaultRefreshInterval?: number;
}

/**
 * Employee status.
 */
export type EmployeeStatus = 'onboarding' | 'active' | 'paused' | 'stopped' | 'terminated';

/**
 * Employee lifecycle stage.
 */
export type LifecycleStage = 'shadow' | 'supervised' | 'autonomous';

/**
 * Employee role.
 */
export type EmployeeRole = 'sales_ae' | 'csm' | 'pm' | 'sdr' | 'recruiter' | 'custom';

/**
 * Employee data from API.
 */
export interface Employee {
  id: string;
  tenantId: string;
  name: string;
  role: EmployeeRole;
  email: string;
  status: EmployeeStatus;
  lifecycleStage: LifecycleStage;
  capabilities: string[];
  personality: Record<string, unknown>;
  config: Record<string, unknown>;
  performanceMetrics: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
  onboardedAt?: string;
  activatedAt?: string;
  isRunning: boolean;
}

/**
 * Employee creation data.
 */
export interface EmployeeCreate {
  name: string;
  role: EmployeeRole;
  email: string;
  capabilities?: string[];
  personality?: Record<string, unknown>;
  config?: Record<string, unknown>;
}

/**
 * Employee update data.
 */
export interface EmployeeUpdate {
  name?: string;
  email?: string;
  capabilities?: string[];
  personality?: Record<string, unknown>;
  config?: Record<string, unknown>;
  status?: EmployeeStatus;
  lifecycleStage?: LifecycleStage;
}

/**
 * Paginated response.
 */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
}

/**
 * Activity event from API.
 */
export interface Activity {
  id: string;
  employeeId: string;
  eventType: string;
  description: string;
  data: Record<string, unknown>;
  importance: number;
  occurredAt: string;
  createdAt: string;
}

/**
 * Activity summary from API.
 */
export interface ActivitySummary {
  eventCounts: Record<string, number>;
  total: number;
}

/**
 * Employee runtime status.
 */
export interface EmployeeRuntimeStatus {
  id: string;
  name: string;
  status: EmployeeStatus;
  lifecycleStage: LifecycleStage;
  isRunning: boolean;
  isPaused: boolean;
  hasError: boolean;
  lastError?: string;
  currentIntention?: string;
  lastActivity?: string;
  cycleCount?: number;
  errorCount?: number;
}

/**
 * Login response.
 */
export interface LoginResponse {
  token: string;
  userId: string;
  tenantId: string;
  userName: string;
  tenantName: string;
  role: string;
}

// =========================================================================
// Integration Types
// =========================================================================

export type IntegrationProvider = 'google_workspace' | 'microsoft_graph';
export type CredentialStatus = 'active' | 'expired' | 'revoked' | 'refreshing' | 'revocation_failed';
export type CredentialType = 'oauth_tokens' | 'service_account_key';
export type CredentialSource = 'platform' | 'tenant';

/**
 * Provider info from GET /providers.
 */
export interface ProviderInfo {
  provider: IntegrationProvider;
  displayName: string;
  description: string;
  icon: string;
  available: boolean;
  source: CredentialSource | null;
  integrationId: string | null;
  connectedEmployees: number;
}

/**
 * Integration credential.
 */
export interface IntegrationCredential {
  id: string;
  integrationId: string;
  employeeId: string;
  employeeName: string;
  provider: IntegrationProvider;
  credentialType: CredentialType;
  status: CredentialStatus;
  issuedAt: string | null;
  expiresAt: string | null;
  lastRefreshedAt: string | null;
  lastUsedAt: string | null;
  tokenMetadata: Record<string, unknown>;
}

/**
 * Connect request data.
 */
export interface ConnectRequest {
  provider: IntegrationProvider;
  employeeId: string;
  redirectAfter?: string;
}

/**
 * Connect response.
 */
export interface ConnectResponse {
  authorizationUrl: string;
  state: string;
  provider: IntegrationProvider;
  employeeId: string;
  integrationId: string;
}
