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
 * Memory types (episodic, semantic, procedural, working).
 */
export interface EpisodicMemoryItem {
  id: string;
  employeeId: string;
  episodeType: string;
  description: string;
  content: Record<string, unknown>;
  participants: string[];
  location: string | null;
  importance: number;
  recallCount: number;
  lastRecalledAt: string | null;
  occurredAt: string;
  createdAt: string;
  updatedAt: string;
}

export interface SemanticMemoryItem {
  id: string;
  employeeId: string;
  factType: string;
  subject: string;
  predicate: string;
  object: string;
  confidence: number;
  source: string | null;
  verified: boolean;
  accessCount: number;
  lastAccessedAt: string | null;
  context: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface ProceduralMemoryItem {
  id: string;
  employeeId: string;
  name: string;
  description: string;
  procedureType: string;
  steps: Array<Record<string, unknown>>;
  triggerConditions: Record<string, unknown>;
  successRate: number;
  executionCount: number;
  successCount: number;
  avgExecutionTime: number | null;
  lastExecutedAt: string | null;
  isPlaybook: boolean;
  promotedAt: string | null;
  learnedFrom: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface WorkingMemoryItem {
  id: string;
  employeeId: string;
  itemType: string;
  content: Record<string, unknown>;
  importance: number;
  expiresAt: number | null;
  accessCount: number;
  lastAccessedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface WorkingMemoryListResponse {
  items: WorkingMemoryItem[];
  total: number;
}

/**
 * Per-employee tool catalog + health (proxied from the runner).
 */
export interface ToolCatalogItem {
  name: string;
  description: string | null;
  integration: string | null;
}

export interface ToolCatalogResponse {
  items: ToolCatalogItem[];
  total: number;
  integrations: string[];
}

export interface IntegrationHealth {
  name: string;
  status: string;
  successCount: number;
  failureCount: number;
  timeoutCount: number;
  totalCalls: number;
  avgLatencyMs: number;
  errorRate: number;
  lastError: string | null;
}

export interface BlockedToolEntry {
  toolName: string;
  reason: string;
  employeeRole: string | null;
  timestamp: number;
}

export interface TrustCycleStats {
  totalDecisions: number;
  allowed: number;
  denied: number;
  tainted: boolean;
  cycleCalls: number;
  maxCallsPerCycle: number;
}

export interface BlockedToolsResponse {
  items: BlockedToolEntry[];
  total: number;
  stats: TrustCycleStats;
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
// Role Definition Types
// =========================================================================

/**
 * Pre-defined employee role from the catalog API.
 */
export interface RoleDefinition {
  code: string;
  title: string;
  description: string;
  shortDescription: string;
  defaultCapabilities: string[];
  hasImplementation: boolean;
  hasPersonalityPreset: boolean;
}

// =========================================================================
// Integration Types
// =========================================================================

export type IntegrationProvider = 'google_workspace' | 'microsoft_graph';
export type CredentialStatus = 'active' | 'expired' | 'revoked' | 'refreshing' | 'revocation_failed';
export type CredentialType = 'oauth_tokens' | 'service_account_key' | 'api_key' | 'bearer_token';
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

// =========================================================================
// MCP Server Types
// =========================================================================

export type MCPTransport = 'http' | 'stdio';
export type MCPAuthType = 'none' | 'api_key' | 'bearer_token' | 'oauth';
export type MCPServerStatus = 'active' | 'disabled' | 'revoked';

/**
 * Discovered tool from an MCP server.
 */
export interface MCPToolInfo {
  name: string;
  description: string;
}

/**
 * MCP server from API.
 */
export interface MCPServer {
  id: string;
  name: string;
  displayName: string;
  description: string;
  transport: MCPTransport;
  url: string | null;
  command: string[] | null;
  authType: MCPAuthType;
  hasCredentials: boolean;
  status: MCPServerStatus;
  discoveredTools: MCPToolInfo[];
  lastConnectedAt: string | null;
  lastError: string | null;
  createdAt: string;
  updatedAt: string;
}

/**
 * MCP server creation data.
 */
export interface MCPServerCreate {
  name: string;
  displayName: string;
  description?: string;
  transport: MCPTransport;
  url?: string;
  command?: string[];
  env?: Record<string, string>;
  authType?: MCPAuthType;
  credentials?: Record<string, unknown>;
}

/**
 * MCP server update data.
 */
export interface MCPServerUpdate {
  displayName?: string;
  description?: string;
  url?: string;
  command?: string[];
  env?: Record<string, string>;
  authType?: MCPAuthType;
  credentials?: Record<string, unknown>;
  status?: MCPServerStatus;
}

/**
 * MCP server test result.
 */
export interface MCPServerTestResult {
  success: boolean;
  toolsDiscovered: number;
  toolNames: string[];
  error: string | null;
}

/**
 * MCP server test request (unsaved).
 */
export interface MCPServerTestRequest {
  transport: MCPTransport;
  url?: string;
  command?: string[];
  env?: Record<string, string>;
  authType?: MCPAuthType;
  credentials?: Record<string, unknown>;
}

// =========================================================================
// BDI Types (Goals, Intentions, Beliefs)
// =========================================================================

export type GoalStatus = 'active' | 'in_progress' | 'completed' | 'abandoned' | 'blocked';

export interface EmployeeGoal {
  id: string;
  employeeId: string;
  goalType: string;
  description: string;
  priority: number;
  target: Record<string, unknown>;
  currentProgress: Record<string, unknown>;
  status: GoalStatus;
  createdAt: string;
  updatedAt: string;
  completedAt?: string;
  abandonedAt?: string;
}

export type IntentionStatus = 'planned' | 'in_progress' | 'completed' | 'failed' | 'abandoned';
export type IntentionType = 'action' | 'tactic' | 'strategy';

export interface EmployeeIntention {
  id: string;
  employeeId: string;
  goalId?: string;
  intentionType: IntentionType;
  description: string;
  plan: Record<string, unknown>;
  status: IntentionStatus;
  priority: number;
  startedAt?: string;
  completedAt?: string;
  failedAt?: string;
  context: Record<string, unknown>;
  dependencies: string[];
  createdAt: string;
  updatedAt: string;
}

export type BeliefType = 'state' | 'event' | 'causal' | 'evaluative';

export interface Belief {
  id: string;
  employeeId: string;
  beliefType: BeliefType;
  subject: string;
  predicate: string;
  value: Record<string, unknown>;
  confidence: number;
  source: string;
  evidence: string[];
  formedAt: string;
  lastUpdatedAt: string;
  decayRate: number;
  createdAt: string;
  updatedAt: string;
}
