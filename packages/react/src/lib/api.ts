/**
 * @empla/react - API Client
 *
 * HTTP client for communicating with the empla API.
 */

import type {
  Activity,
  ActivitySummary,
  Belief,
  ConnectRequest,
  ConnectResponse,
  CredentialSource,
  CredentialStatus,
  CredentialType,
  Employee,
  EmployeeCreate,
  EmployeeGoal,
  EmployeeIntention,
  EmployeeRuntimeStatus,
  EmployeeUpdate,
  BlockedToolsResponse,
  EpisodicMemoryItem,
  IntegrationCredential,
  IntegrationHealth,
  IntegrationProvider,
  LoginResponse,
  MCPServer,
  MCPServerCreate,
  MCPServerTestRequest,
  MCPServerTestResult,
  MCPServerUpdate,
  PaginatedResponse,
  ProceduralMemoryItem,
  ProviderInfo,
  RoleDefinition,
  SemanticMemoryItem,
  ToolCatalogResponse,
  ScheduledAction,
  TenantSettingsData,
  TenantSettingsUpdate,
  TenantSettingsUpdateResult,
  WebhookAuditEvent,
  WebhookTokenInfo,
  WebhookTokenIssued,
  WorkingMemoryItem,
  WorkingMemoryListResponse,
} from '../types';

/**
 * API client configuration.
 */
export interface ApiClientConfig {
  baseUrl: string;
  authToken?: string;
  onAuthError?: () => void;
}

/**
 * API error with status code.
 */
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public data?: unknown
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * Create an API client instance.
 */
export function createApiClient(config: ApiClientConfig) {
  const { baseUrl, onAuthError } = config;
  let authToken = config.authToken;

  /**
   * Make an API request.
   */
  async function request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${baseUrl}${endpoint}`;

    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    if (authToken) {
      (headers as Record<string, string>)['Authorization'] = `Bearer ${authToken}`;
    }

    // Wrap fetch to handle network errors
    let response: Response;
    try {
      response = await fetch(url, {
        ...options,
        headers,
      });
    } catch (error) {
      // Network-level error (no response received)
      const message = error instanceof Error ? error.message : 'Network request failed';
      throw new ApiError(
        `Network error: ${message}. Please check your connection.`,
        0, // No HTTP status for network errors
        { networkError: true, originalError: String(error) }
      );
    }

    if (response.status === 401) {
      onAuthError?.();
      throw new ApiError('Unauthorized', 401);
    }

    if (!response.ok) {
      // Preserve raw response for debugging
      let data: unknown = null;
      let rawText: string | null = null;

      try {
        rawText = await response.text();
        data = JSON.parse(rawText);
      } catch {
        // Log parse failure for debugging but don't throw
        console.error(
          `Failed to parse error response as JSON. Status: ${response.status}, Body: ${rawText?.substring(0, 500)}`
        );
      }

      // FastAPI returns detail as a string for HTTPException, or an array for
      // validation errors (422). Extract a readable message from either shape.
      const detail = (data as { detail?: unknown })?.detail;
      let message: string;
      if (typeof detail === 'string') {
        message = detail;
      } else if (Array.isArray(detail) && detail.length > 0) {
        message = detail.map((e: { msg?: string }) => e.msg ?? String(e)).join('; ');
      } else {
        message = rawText?.substring(0, 200) || `Request failed: ${response.statusText}`;
      }

      throw new ApiError(message, response.status, data ?? { rawBody: rawText });
    }

    // Handle 204 No Content
    if (response.status === 204) {
      return undefined as T;
    }

    // Check content-type to detect non-JSON responses
    const contentType = response.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) {
      const rawText = await response.text();
      throw new ApiError(
        `Expected JSON response but received ${contentType || 'unknown content type'}`,
        response.status,
        { url: response.url, rawBody: rawText?.substring(0, 500) }
      );
    }

    // Parse JSON with error handling
    try {
      return await response.json();
    } catch (parseError) {
      throw new ApiError(
        `Failed to parse JSON response: ${parseError instanceof Error ? parseError.message : String(parseError)}`,
        response.status,
        { url: response.url, parseError: String(parseError) }
      );
    }
  }

  /**
   * Set the authentication token.
   */
  function setAuthToken(token: string | undefined) {
    authToken = token;
  }

  // =========================================================================
  // Auth Endpoints
  // =========================================================================

  async function login(email: string, tenantSlug: string): Promise<LoginResponse> {
    const response = await request<{
      token: string;
      user_id: string;
      tenant_id: string;
      user_name: string;
      tenant_name: string;
      role: string;
    }>('/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, tenant_slug: tenantSlug }),
    });

    return {
      token: response.token,
      userId: response.user_id,
      tenantId: response.tenant_id,
      userName: response.user_name,
      tenantName: response.tenant_name,
      role: response.role,
    };
  }

  // =========================================================================
  // Role Endpoints
  // =========================================================================

  async function listRoles(): Promise<{ roles: RoleDefinition[] }> {
    const response = await request<{
      roles: Array<{
        code: string;
        title: string;
        description: string;
        short_description: string;
        default_capabilities: string[];
        has_implementation: boolean;
        has_personality_preset: boolean;
      }>;
    }>('/v1/roles/');

    return {
      roles: response.roles.map((r) => ({
        code: r.code,
        title: r.title,
        description: r.description,
        shortDescription: r.short_description,
        defaultCapabilities: r.default_capabilities,
        hasImplementation: r.has_implementation,
        hasPersonalityPreset: r.has_personality_preset,
      })),
    };
  }

  // =========================================================================
  // Employee Endpoints
  // =========================================================================

  async function listEmployees(params?: {
    page?: number;
    pageSize?: number;
    status?: string;
    role?: string;
  }): Promise<PaginatedResponse<Employee>> {
    const searchParams = new URLSearchParams();
    if (params?.page !== undefined && params?.page !== null)
      searchParams.set('page', params.page.toString());
    if (params?.pageSize !== undefined && params?.pageSize !== null)
      searchParams.set('page_size', params.pageSize.toString());
    if (params?.status) searchParams.set('status', params.status);
    if (params?.role) searchParams.set('role', params.role);

    const query = searchParams.toString();
    const endpoint = `/v1/employees${query ? `?${query}` : ''}`;

    const response = await request<{
      items: Array<{
        id: string;
        tenant_id: string;
        name: string;
        role: string;
        email: string;
        status: string;
        lifecycle_stage: string;
        capabilities: string[];
        personality: Record<string, unknown>;
        config: Record<string, unknown>;
        performance_metrics: Record<string, unknown>;
        created_at: string;
        updated_at: string;
        onboarded_at?: string;
        activated_at?: string;
        is_running: boolean;
      }>;
      total: number;
      page: number;
      page_size: number;
      pages: number;
    }>(endpoint);

    return {
      items: response.items.map(transformEmployee),
      total: response.total,
      page: response.page,
      pageSize: response.page_size,
      pages: response.pages,
    };
  }

  async function getEmployee(id: string): Promise<Employee> {
    const response = await request<{
      id: string;
      tenant_id: string;
      name: string;
      role: string;
      email: string;
      status: string;
      lifecycle_stage: string;
      capabilities: string[];
      personality: Record<string, unknown>;
      config: Record<string, unknown>;
      performance_metrics: Record<string, unknown>;
      created_at: string;
      updated_at: string;
      onboarded_at?: string;
      activated_at?: string;
      is_running: boolean;
    }>(`/v1/employees/${id}`);

    return transformEmployee(response);
  }

  async function createEmployee(data: EmployeeCreate): Promise<Employee> {
    const response = await request<{
      id: string;
      tenant_id: string;
      name: string;
      role: string;
      email: string;
      status: string;
      lifecycle_stage: string;
      capabilities: string[];
      personality: Record<string, unknown>;
      config: Record<string, unknown>;
      performance_metrics: Record<string, unknown>;
      created_at: string;
      updated_at: string;
      is_running: boolean;
    }>('/v1/employees', {
      method: 'POST',
      body: JSON.stringify(data),
    });

    return transformEmployee(response);
  }

  async function updateEmployee(id: string, data: EmployeeUpdate): Promise<Employee> {
    const snakeCaseData: Record<string, unknown> = {};
    if (data.name !== undefined) snakeCaseData.name = data.name;
    if (data.email !== undefined) snakeCaseData.email = data.email;
    if (data.capabilities !== undefined) snakeCaseData.capabilities = data.capabilities;
    if (data.personality !== undefined) snakeCaseData.personality = data.personality;
    if (data.config !== undefined) snakeCaseData.config = data.config;
    if (data.status !== undefined) snakeCaseData.status = data.status;
    if (data.lifecycleStage !== undefined) snakeCaseData.lifecycle_stage = data.lifecycleStage;

    const response = await request<{
      id: string;
      tenant_id: string;
      name: string;
      role: string;
      email: string;
      status: string;
      lifecycle_stage: string;
      capabilities: string[];
      personality: Record<string, unknown>;
      config: Record<string, unknown>;
      performance_metrics: Record<string, unknown>;
      created_at: string;
      updated_at: string;
      is_running: boolean;
    }>(`/v1/employees/${id}`, {
      method: 'PUT',
      body: JSON.stringify(snakeCaseData),
    });

    return transformEmployee(response);
  }

  async function deleteEmployee(id: string): Promise<void> {
    await request<void>(`/v1/employees/${id}`, {
      method: 'DELETE',
    });
  }

  // =========================================================================
  // Employee Control Endpoints
  // =========================================================================

  // Response type for employee control endpoints
  interface EmployeeStatusApiResponse {
    id: string;
    name: string;
    status: string;
    lifecycle_stage: string;
    is_running: boolean;
    is_paused: boolean;
    has_error: boolean;
    last_error?: string;
  }

  function transformStatusResponse(response: EmployeeStatusApiResponse): EmployeeRuntimeStatus {
    return {
      id: response.id,
      name: response.name,
      status: response.status as EmployeeRuntimeStatus['status'],
      lifecycleStage: response.lifecycle_stage as EmployeeRuntimeStatus['lifecycleStage'],
      isRunning: response.is_running,
      isPaused: response.is_paused,
      hasError: response.has_error,
      lastError: response.last_error,
    };
  }

  async function startEmployee(id: string): Promise<EmployeeRuntimeStatus> {
    const response = await request<EmployeeStatusApiResponse>(
      `/v1/employees/${id}/start`,
      { method: 'POST' }
    );
    return transformStatusResponse(response);
  }

  async function stopEmployee(id: string): Promise<EmployeeRuntimeStatus> {
    const response = await request<EmployeeStatusApiResponse>(
      `/v1/employees/${id}/stop`,
      { method: 'POST' }
    );
    return transformStatusResponse(response);
  }

  async function pauseEmployee(id: string): Promise<EmployeeRuntimeStatus> {
    const response = await request<EmployeeStatusApiResponse>(
      `/v1/employees/${id}/pause`,
      { method: 'POST' }
    );
    return transformStatusResponse(response);
  }

  async function resumeEmployee(id: string): Promise<EmployeeRuntimeStatus> {
    const response = await request<EmployeeStatusApiResponse>(
      `/v1/employees/${id}/resume`,
      { method: 'POST' }
    );
    return transformStatusResponse(response);
  }

  async function getEmployeeStatus(id: string): Promise<EmployeeRuntimeStatus> {
    const response = await request<EmployeeStatusApiResponse>(
      `/v1/employees/${id}/status`
    );
    return transformStatusResponse(response);
  }

  // =========================================================================
  // Activity Endpoints
  // =========================================================================

  async function listActivities(params?: {
    employeeId?: string;
    page?: number;
    pageSize?: number;
    eventType?: string;
    minImportance?: number;
    since?: string;
  }): Promise<PaginatedResponse<Activity>> {
    const searchParams = new URLSearchParams();
    if (params?.page !== undefined && params?.page !== null)
      searchParams.set('page', params.page.toString());
    if (params?.pageSize !== undefined && params?.pageSize !== null)
      searchParams.set('page_size', params.pageSize.toString());
    if (params?.eventType) searchParams.set('event_type', params.eventType);
    if (params?.minImportance !== undefined && params?.minImportance !== null)
      searchParams.set('min_importance', params.minImportance.toString());
    if (params?.since) searchParams.set('since', params.since);

    const query = searchParams.toString();
    const basePath = params?.employeeId
      ? `/v1/activity/employees/${params.employeeId}`
      : '/v1/activity';
    const endpoint = `${basePath}${query ? `?${query}` : ''}`;

    const response = await request<{
      items: Array<{
        id: string;
        employee_id: string;
        event_type: string;
        description: string;
        data: Record<string, unknown>;
        importance: number;
        occurred_at: string;
        created_at: string;
      }>;
      total: number;
      page: number;
      page_size: number;
      pages: number;
    }>(endpoint);

    return {
      items: response.items.map(transformActivity),
      total: response.total,
      page: response.page,
      pageSize: response.page_size,
      pages: response.pages,
    };
  }

  async function getRecentActivities(
    employeeId: string,
    limit: number = 20
  ): Promise<Activity[]> {
    const response = await request<
      Array<{
        id: string;
        employee_id: string;
        event_type: string;
        description: string;
        data: Record<string, unknown>;
        importance: number;
        occurred_at: string;
        created_at: string;
      }>
    >(`/v1/activity/employees/${employeeId}/recent?limit=${limit}`);

    return response.map(transformActivity);
  }

  async function getActivitySummary(params?: {
    employeeId?: string;
    hours?: number;
  }): Promise<ActivitySummary> {
    const basePath = params?.employeeId
      ? `/v1/activity/employees/${params.employeeId}/summary`
      : '/v1/activity/summary';
    const query = params?.hours ? `?hours=${params.hours}` : '';

    const response = await request<{
      event_counts: Record<string, number>;
      total: number;
    }>(`${basePath}${query}`);

    return {
      eventCounts: response.event_counts,
      total: response.total,
    };
  }

  // =========================================================================
  // Transform Helpers
  // =========================================================================

  function transformEmployee(data: {
    id: string;
    tenant_id: string;
    name: string;
    role: string;
    email: string;
    status: string;
    lifecycle_stage: string;
    capabilities: string[];
    personality: Record<string, unknown>;
    config: Record<string, unknown>;
    performance_metrics: Record<string, unknown>;
    created_at: string;
    updated_at: string;
    onboarded_at?: string;
    activated_at?: string;
    is_running: boolean;
  }): Employee {
    return {
      id: data.id,
      tenantId: data.tenant_id,
      name: data.name,
      role: data.role as Employee['role'],
      email: data.email,
      status: data.status as Employee['status'],
      lifecycleStage: data.lifecycle_stage as Employee['lifecycleStage'],
      capabilities: data.capabilities,
      personality: data.personality,
      config: data.config,
      performanceMetrics: data.performance_metrics,
      createdAt: data.created_at,
      updatedAt: data.updated_at,
      onboardedAt: data.onboarded_at,
      activatedAt: data.activated_at,
      isRunning: data.is_running,
    };
  }

  function transformActivity(data: {
    id: string;
    employee_id: string;
    event_type: string;
    description: string;
    data: Record<string, unknown>;
    importance: number;
    occurred_at: string;
    created_at: string;
  }): Activity {
    return {
      id: data.id,
      employeeId: data.employee_id,
      eventType: data.event_type,
      description: data.description,
      data: data.data,
      importance: data.importance,
      occurredAt: data.occurred_at,
      createdAt: data.created_at,
    };
  }

  // =========================================================================
  // Integration Endpoints
  // =========================================================================

  async function listProviders(): Promise<ProviderInfo[]> {
    const response = await request<{
      items: Array<{
        provider: IntegrationProvider;
        display_name: string;
        description: string;
        icon: string;
        available: boolean;
        source: CredentialSource | null;
        integration_id: string | null;
        connected_employees: number;
      }>;
    }>('/v1/integrations/providers');

    return response.items.map((p) => ({
      provider: p.provider,
      displayName: p.display_name,
      description: p.description,
      icon: p.icon,
      available: p.available,
      source: p.source,
      integrationId: p.integration_id,
      connectedEmployees: p.connected_employees,
    }));
  }

  async function connectProvider(data: ConnectRequest): Promise<ConnectResponse> {
    const response = await request<{
      authorization_url: string;
      state: string;
      provider: IntegrationProvider;
      employee_id: string;
      integration_id: string;
    }>('/v1/integrations/connect', {
      method: 'POST',
      body: JSON.stringify({
        provider: data.provider,
        employee_id: data.employeeId,
        redirect_after: data.redirectAfter,
      }),
    });

    return {
      authorizationUrl: response.authorization_url,
      state: response.state,
      provider: response.provider,
      employeeId: response.employee_id,
      integrationId: response.integration_id,
    };
  }

  async function listCredentials(): Promise<IntegrationCredential[]> {
    const response = await request<{
      items: Array<{
        id: string;
        integration_id: string;
        employee_id: string;
        employee_name: string;
        provider: IntegrationProvider;
        credential_type: CredentialType;
        status: CredentialStatus;
        issued_at: string | null;
        expires_at: string | null;
        last_refreshed_at: string | null;
        last_used_at: string | null;
        token_metadata: Record<string, unknown>;
      }>;
    }>('/v1/integrations/credentials');

    return response.items.map((c) => ({
      id: c.id,
      integrationId: c.integration_id,
      employeeId: c.employee_id,
      employeeName: c.employee_name,
      provider: c.provider,
      credentialType: c.credential_type,
      status: c.status,
      issuedAt: c.issued_at,
      expiresAt: c.expires_at,
      lastRefreshedAt: c.last_refreshed_at,
      lastUsedAt: c.last_used_at,
      tokenMetadata: c.token_metadata,
    }));
  }

  async function revokeCredential(integrationId: string, employeeId: string): Promise<void> {
    await request<void>(
      `/v1/integrations/${encodeURIComponent(integrationId)}/employees/${encodeURIComponent(employeeId)}/credential`,
      { method: 'DELETE' }
    );
  }

  // =========================================================================
  // MCP Server Endpoints
  // =========================================================================

  interface MCPServerApiResponse {
    id: string;
    name: string;
    display_name: string;
    description: string;
    transport: string;
    url: string | null;
    command: string[] | null;
    auth_type: string;
    has_credentials: boolean;
    status: string;
    discovered_tools: Array<{ name: string; description: string }>;
    last_connected_at: string | null;
    last_error: string | null;
    created_at: string;
    updated_at: string;
  }

  function transformMCPServer(data: MCPServerApiResponse): MCPServer {
    return {
      id: data.id,
      name: data.name,
      displayName: data.display_name,
      description: data.description,
      transport: data.transport as MCPServer['transport'],
      url: data.url,
      command: data.command,
      authType: data.auth_type as MCPServer['authType'],
      hasCredentials: data.has_credentials,
      status: data.status as MCPServer['status'],
      discoveredTools: data.discovered_tools,
      lastConnectedAt: data.last_connected_at,
      lastError: data.last_error,
      createdAt: data.created_at,
      updatedAt: data.updated_at,
    };
  }

  async function listMCPServers(): Promise<{ items: MCPServer[]; total: number }> {
    const response = await request<{
      items: MCPServerApiResponse[];
      total: number;
    }>('/v1/mcp-servers');

    return {
      items: response.items.map(transformMCPServer),
      total: response.total,
    };
  }

  async function getMCPServer(id: string): Promise<MCPServer> {
    const response = await request<MCPServerApiResponse>(`/v1/mcp-servers/${id}`);
    return transformMCPServer(response);
  }

  async function createMCPServer(data: MCPServerCreate): Promise<MCPServer> {
    const response = await request<MCPServerApiResponse>('/v1/mcp-servers', {
      method: 'POST',
      body: JSON.stringify({
        name: data.name,
        display_name: data.displayName,
        description: data.description ?? '',
        transport: data.transport,
        url: data.url,
        command: data.command,
        env: data.env,
        auth_type: data.authType ?? 'none',
        credentials: data.credentials,
      }),
    });
    return transformMCPServer(response);
  }

  async function updateMCPServer(id: string, data: MCPServerUpdate): Promise<MCPServer> {
    const snakeCaseData: Record<string, unknown> = {};
    if (data.displayName !== undefined) snakeCaseData.display_name = data.displayName;
    if (data.description !== undefined) snakeCaseData.description = data.description;
    if (data.url !== undefined) snakeCaseData.url = data.url;
    if (data.command !== undefined) snakeCaseData.command = data.command;
    if (data.env !== undefined) snakeCaseData.env = data.env;
    if (data.authType !== undefined) snakeCaseData.auth_type = data.authType;
    if (data.credentials !== undefined) snakeCaseData.credentials = data.credentials;
    if (data.status !== undefined) snakeCaseData.status = data.status;

    const response = await request<MCPServerApiResponse>(`/v1/mcp-servers/${id}`, {
      method: 'PUT',
      body: JSON.stringify(snakeCaseData),
    });
    return transformMCPServer(response);
  }

  async function deleteMCPServer(id: string): Promise<void> {
    await request<void>(`/v1/mcp-servers/${id}`, { method: 'DELETE' });
  }

  type MCPTestApiResponse = {
    success: boolean;
    tools_discovered: number;
    tool_names: string[];
    error: string | null;
  };

  function transformTestResult(response: MCPTestApiResponse): MCPServerTestResult {
    return {
      success: response.success,
      toolsDiscovered: response.tools_discovered,
      toolNames: response.tool_names,
      error: response.error,
    };
  }

  async function testMCPServer(data: MCPServerTestRequest): Promise<MCPServerTestResult> {
    const response = await request<MCPTestApiResponse>('/v1/mcp-servers/test', {
      method: 'POST',
      body: JSON.stringify({
        transport: data.transport,
        url: data.url,
        command: data.command,
        env: data.env,
        auth_type: data.authType ?? 'none',
        credentials: data.credentials,
      }),
    });
    return transformTestResult(response);
  }

  async function testMCPServerConnection(id: string): Promise<MCPServerTestResult> {
    const response = await request<MCPTestApiResponse>(
      `/v1/mcp-servers/${id}/test-connection`,
      { method: 'POST' },
    );
    return transformTestResult(response);
  }

  // =========================================================================
  // BDI Endpoints (Goals, Intentions, Beliefs)
  // =========================================================================

  async function listGoals(params: {
    employeeId: string;
    page?: number;
    pageSize?: number;
    status?: string;
  }): Promise<PaginatedResponse<EmployeeGoal>> {
    const searchParams = new URLSearchParams();
    if (params.page !== undefined) searchParams.set('page', params.page.toString());
    if (params.pageSize !== undefined) searchParams.set('page_size', params.pageSize.toString());
    if (params.status) searchParams.set('status', params.status);

    const query = searchParams.toString();
    const endpoint = `/v1/employees/${params.employeeId}/goals${query ? `?${query}` : ''}`;

    const response = await request<{
      items: Array<{
        id: string;
        employee_id: string;
        goal_type: string;
        description: string;
        priority: number;
        target: Record<string, unknown>;
        current_progress: Record<string, unknown>;
        status: string;
        created_at: string;
        updated_at: string;
        completed_at: string | null;
        abandoned_at: string | null;
      }>;
      total: number;
      page: number;
      page_size: number;
      pages: number;
    }>(endpoint);

    return {
      items: response.items.map((g) => ({
        id: g.id,
        employeeId: g.employee_id,
        goalType: g.goal_type,
        description: g.description,
        priority: g.priority,
        target: g.target,
        currentProgress: g.current_progress,
        status: g.status as EmployeeGoal['status'],
        createdAt: g.created_at,
        updatedAt: g.updated_at,
        completedAt: g.completed_at ?? undefined,
        abandonedAt: g.abandoned_at ?? undefined,
      })),
      total: response.total,
      page: response.page,
      pageSize: response.page_size,
      pages: response.pages,
    };
  }

  async function listIntentions(params: {
    employeeId: string;
    page?: number;
    pageSize?: number;
    status?: string;
    goalId?: string;
  }): Promise<PaginatedResponse<EmployeeIntention>> {
    const searchParams = new URLSearchParams();
    if (params.page !== undefined) searchParams.set('page', params.page.toString());
    if (params.pageSize !== undefined) searchParams.set('page_size', params.pageSize.toString());
    if (params.status) searchParams.set('status', params.status);
    if (params.goalId) searchParams.set('goal_id', params.goalId);

    const query = searchParams.toString();
    const endpoint = `/v1/employees/${params.employeeId}/intentions${query ? `?${query}` : ''}`;

    const response = await request<{
      items: Array<{
        id: string;
        employee_id: string;
        goal_id: string | null;
        intention_type: string;
        description: string;
        plan: Record<string, unknown>;
        status: string;
        priority: number;
        started_at: string | null;
        completed_at: string | null;
        failed_at: string | null;
        context: Record<string, unknown>;
        dependencies: string[];
        created_at: string;
        updated_at: string;
      }>;
      total: number;
      page: number;
      page_size: number;
      pages: number;
    }>(endpoint);

    return {
      items: response.items.map((i) => ({
        id: i.id,
        employeeId: i.employee_id,
        goalId: i.goal_id ?? undefined,
        intentionType: i.intention_type as EmployeeIntention['intentionType'],
        description: i.description,
        plan: i.plan,
        status: i.status as EmployeeIntention['status'],
        priority: i.priority,
        startedAt: i.started_at ?? undefined,
        completedAt: i.completed_at ?? undefined,
        failedAt: i.failed_at ?? undefined,
        context: i.context,
        dependencies: i.dependencies,
        createdAt: i.created_at,
        updatedAt: i.updated_at,
      })),
      total: response.total,
      page: response.page,
      pageSize: response.page_size,
      pages: response.pages,
    };
  }

  async function listBeliefs(params: {
    employeeId: string;
    page?: number;
    pageSize?: number;
    beliefType?: string;
    minConfidence?: number;
  }): Promise<PaginatedResponse<Belief>> {
    const searchParams = new URLSearchParams();
    if (params.page !== undefined) searchParams.set('page', params.page.toString());
    if (params.pageSize !== undefined) searchParams.set('page_size', params.pageSize.toString());
    if (params.beliefType) searchParams.set('belief_type', params.beliefType);
    if (params.minConfidence !== undefined) searchParams.set('min_confidence', params.minConfidence.toString());

    const query = searchParams.toString();
    const endpoint = `/v1/employees/${params.employeeId}/beliefs${query ? `?${query}` : ''}`;

    const response = await request<{
      items: Array<{
        id: string;
        employee_id: string;
        belief_type: string;
        subject: string;
        predicate: string;
        object: Record<string, unknown>;
        confidence: number;
        source: string;
        evidence: string[];
        formed_at: string;
        last_updated_at: string;
        decay_rate: number;
        created_at: string;
        updated_at: string;
      }>;
      total: number;
      page: number;
      page_size: number;
      pages: number;
    }>(endpoint);

    return {
      items: response.items.map((b) => ({
        id: b.id,
        employeeId: b.employee_id,
        beliefType: b.belief_type as Belief['beliefType'],
        subject: b.subject,
        predicate: b.predicate,
        value: b.object,
        confidence: b.confidence,
        source: b.source,
        evidence: b.evidence,
        formedAt: b.formed_at,
        lastUpdatedAt: b.last_updated_at,
        decayRate: b.decay_rate,
        createdAt: b.created_at,
        updatedAt: b.updated_at,
      })),
      total: response.total,
      page: response.page,
      pageSize: response.page_size,
      pages: response.pages,
    };
  }

  // =========================================================================
  // Cost Endpoints
  // =========================================================================

  async function getCostSummary(params: {
    employeeId: string;
    hours?: number;
  }): Promise<{
    employeeId: string;
    hours: number;
    totalCostUsd: number;
    avgCostPerCycle: number;
    totalCycles: number;
    totalInputTokens: number;
    totalOutputTokens: number;
  }> {
    const searchParams = new URLSearchParams();
    if (params.hours !== undefined) searchParams.set('hours', params.hours.toString());
    const query = searchParams.toString();

    const response = await request<{
      employee_id: string;
      hours: number;
      total_cost_usd: number;
      avg_cost_per_cycle: number;
      total_cycles: number;
      total_input_tokens: number;
      total_output_tokens: number;
    }>(`/v1/metrics/employees/${params.employeeId}/costs${query ? `?${query}` : ''}`);

    return {
      employeeId: response.employee_id,
      hours: response.hours,
      totalCostUsd: response.total_cost_usd,
      avgCostPerCycle: response.avg_cost_per_cycle,
      totalCycles: response.total_cycles,
      totalInputTokens: response.total_input_tokens,
      totalOutputTokens: response.total_output_tokens,
    };
  }

  async function getCostHistory(params: {
    employeeId: string;
    hours?: number;
  }): Promise<{
    items: Array<{ timestamp: string; costUsd: number; cycle: number | null }>;
    total: number;
  }> {
    const searchParams = new URLSearchParams();
    if (params.hours !== undefined) searchParams.set('hours', params.hours.toString());
    const query = searchParams.toString();

    const response = await request<{
      items: Array<{ timestamp: string; cost_usd: number; cycle: number | null }>;
      total: number;
    }>(`/v1/metrics/employees/${params.employeeId}/costs/history${query ? `?${query}` : ''}`);

    return {
      items: response.items.map((item) => ({
        timestamp: item.timestamp,
        costUsd: item.cost_usd,
        cycle: item.cycle,
      })),
      total: response.total,
    };
  }

  // =========================================================================
  // Playbook Endpoints
  // =========================================================================

  async function listPlaybooks(params: {
    employeeId: string;
    minSuccessRate?: number;
    learnedFrom?: string;
    sortBy?: string;
    limit?: number;
  }): Promise<{
    items: Array<{
      id: string;
      name: string;
      description: string | null;
      procedureType: string;
      successRate: number;
      executionCount: number;
      successCount: number;
      avgExecutionTime: number | null;
      lastExecutedAt: string | null;
      promotedAt: string | null;
      learnedFrom: string | null;
    }>;
    total: number;
  }> {
    const searchParams = new URLSearchParams();
    if (params.minSuccessRate !== undefined) searchParams.set('min_success_rate', params.minSuccessRate.toString());
    if (params.learnedFrom) searchParams.set('learned_from', params.learnedFrom);
    if (params.sortBy) searchParams.set('sort_by', params.sortBy);
    if (params.limit !== undefined) searchParams.set('limit', params.limit.toString());
    const query = searchParams.toString();

    const response = await request<{
      items: Array<{
        id: string;
        name: string;
        description: string | null;
        procedure_type: string;
        success_rate: number;
        execution_count: number;
        success_count: number;
        avg_execution_time: number | null;
        last_executed_at: string | null;
        promoted_at: string | null;
        learned_from: string | null;
      }>;
      total: number;
    }>(`/v1/employees/${params.employeeId}/playbooks${query ? `?${query}` : ''}`);

    return {
      items: response.items.map((p) => ({
        id: p.id,
        name: p.name,
        description: p.description,
        procedureType: p.procedure_type,
        successRate: p.success_rate,
        executionCount: p.execution_count,
        successCount: p.success_count,
        avgExecutionTime: p.avg_execution_time,
        lastExecutedAt: p.last_executed_at,
        promotedAt: p.promoted_at,
        learnedFrom: p.learned_from,
      })),
      total: response.total,
    };
  }

  async function getPlaybookStats(params: {
    employeeId: string;
  }): Promise<{
    employeeId: string;
    totalPlaybooks: number;
    avgSuccessRate: number;
    totalExecutions: number;
    promotionCandidates: number;
  }> {
    const response = await request<{
      employee_id: string;
      total_playbooks: number;
      avg_success_rate: number;
      total_executions: number;
      promotion_candidates: number;
    }>(`/v1/employees/${params.employeeId}/playbooks/stats`);

    return {
      employeeId: response.employee_id,
      totalPlaybooks: response.total_playbooks,
      avgSuccessRate: response.avg_success_rate,
      totalExecutions: response.total_executions,
      promotionCandidates: response.promotion_candidates,
    };
  }

  // =========================================================================
  // Memory Endpoints
  // =========================================================================

  async function listEpisodicMemory(params: {
    employeeId: string;
    page?: number;
    pageSize?: number;
    episodeType?: string;
    minImportance?: number;
  }): Promise<PaginatedResponse<EpisodicMemoryItem>> {
    const searchParams = new URLSearchParams();
    if (params.page !== undefined) searchParams.set('page', params.page.toString());
    if (params.pageSize !== undefined) searchParams.set('page_size', params.pageSize.toString());
    if (params.episodeType) searchParams.set('episode_type', params.episodeType);
    if (params.minImportance !== undefined)
      searchParams.set('min_importance', params.minImportance.toString());
    const query = searchParams.toString();

    const response = await request<{
      items: Array<{
        id: string;
        employee_id: string;
        episode_type: string;
        description: string;
        content: Record<string, unknown>;
        participants: string[];
        location: string | null;
        importance: number;
        recall_count: number;
        last_recalled_at: string | null;
        occurred_at: string;
        created_at: string;
        updated_at: string;
      }>;
      total: number;
      page: number;
      page_size: number;
      pages: number;
    }>(`/v1/employees/${params.employeeId}/memory/episodic${query ? `?${query}` : ''}`);

    return {
      items: response.items.map((e) => ({
        id: e.id,
        employeeId: e.employee_id,
        episodeType: e.episode_type,
        description: e.description,
        content: e.content,
        participants: e.participants,
        location: e.location,
        importance: e.importance,
        recallCount: e.recall_count,
        lastRecalledAt: e.last_recalled_at,
        occurredAt: e.occurred_at,
        createdAt: e.created_at,
        updatedAt: e.updated_at,
      })),
      total: response.total,
      page: response.page,
      pageSize: response.page_size,
      pages: response.pages,
    };
  }

  async function listSemanticMemory(params: {
    employeeId: string;
    page?: number;
    pageSize?: number;
    factType?: string;
    subject?: string;
    predicate?: string;
    minConfidence?: number;
  }): Promise<PaginatedResponse<SemanticMemoryItem>> {
    const searchParams = new URLSearchParams();
    if (params.page !== undefined) searchParams.set('page', params.page.toString());
    if (params.pageSize !== undefined) searchParams.set('page_size', params.pageSize.toString());
    if (params.factType) searchParams.set('fact_type', params.factType);
    if (params.subject) searchParams.set('subject', params.subject);
    if (params.predicate) searchParams.set('predicate', params.predicate);
    if (params.minConfidence !== undefined)
      searchParams.set('min_confidence', params.minConfidence.toString());
    const query = searchParams.toString();

    const response = await request<{
      items: Array<{
        id: string;
        employee_id: string;
        fact_type: string;
        subject: string;
        predicate: string;
        object: string;
        confidence: number;
        source: string | null;
        verified: boolean;
        access_count: number;
        last_accessed_at: string | null;
        context: Record<string, unknown>;
        created_at: string;
        updated_at: string;
      }>;
      total: number;
      page: number;
      page_size: number;
      pages: number;
    }>(`/v1/employees/${params.employeeId}/memory/semantic${query ? `?${query}` : ''}`);

    return {
      items: response.items.map((s) => ({
        id: s.id,
        employeeId: s.employee_id,
        factType: s.fact_type,
        subject: s.subject,
        predicate: s.predicate,
        object: s.object,
        confidence: s.confidence,
        source: s.source,
        verified: s.verified,
        accessCount: s.access_count,
        lastAccessedAt: s.last_accessed_at,
        context: s.context,
        createdAt: s.created_at,
        updatedAt: s.updated_at,
      })),
      total: response.total,
      page: response.page,
      pageSize: response.page_size,
      pages: response.pages,
    };
  }

  async function listProceduralMemory(params: {
    employeeId: string;
    page?: number;
    pageSize?: number;
    procedureType?: string;
    minSuccessRate?: number;
    isPlaybook?: boolean;
  }): Promise<PaginatedResponse<ProceduralMemoryItem>> {
    const searchParams = new URLSearchParams();
    if (params.page !== undefined) searchParams.set('page', params.page.toString());
    if (params.pageSize !== undefined) searchParams.set('page_size', params.pageSize.toString());
    if (params.procedureType) searchParams.set('procedure_type', params.procedureType);
    if (params.minSuccessRate !== undefined)
      searchParams.set('min_success_rate', params.minSuccessRate.toString());
    if (params.isPlaybook !== undefined)
      searchParams.set('is_playbook', params.isPlaybook.toString());
    const query = searchParams.toString();

    const response = await request<{
      items: Array<{
        id: string;
        employee_id: string;
        name: string;
        description: string;
        procedure_type: string;
        steps: Array<Record<string, unknown>>;
        trigger_conditions: Record<string, unknown>;
        success_rate: number;
        execution_count: number;
        success_count: number;
        avg_execution_time: number | null;
        last_executed_at: string | null;
        is_playbook: boolean;
        promoted_at: string | null;
        learned_from: string | null;
        created_at: string;
        updated_at: string;
      }>;
      total: number;
      page: number;
      page_size: number;
      pages: number;
    }>(`/v1/employees/${params.employeeId}/memory/procedural${query ? `?${query}` : ''}`);

    return {
      items: response.items.map((p) => ({
        id: p.id,
        employeeId: p.employee_id,
        name: p.name,
        description: p.description,
        procedureType: p.procedure_type,
        steps: p.steps,
        triggerConditions: p.trigger_conditions,
        successRate: p.success_rate,
        executionCount: p.execution_count,
        successCount: p.success_count,
        avgExecutionTime: p.avg_execution_time,
        lastExecutedAt: p.last_executed_at,
        isPlaybook: p.is_playbook,
        promotedAt: p.promoted_at,
        learnedFrom: p.learned_from,
        createdAt: p.created_at,
        updatedAt: p.updated_at,
      })),
      total: response.total,
      page: response.page,
      pageSize: response.page_size,
      pages: response.pages,
    };
  }

  async function listWorkingMemory(params: {
    employeeId: string;
    itemType?: string;
  }): Promise<WorkingMemoryListResponse> {
    const searchParams = new URLSearchParams();
    if (params.itemType) searchParams.set('item_type', params.itemType);
    const query = searchParams.toString();

    const response = await request<{
      items: Array<{
        id: string;
        employee_id: string;
        item_type: string;
        content: Record<string, unknown>;
        importance: number;
        expires_at: number | null;
        access_count: number;
        last_accessed_at: string | null;
        created_at: string;
        updated_at: string;
      }>;
      total: number;
    }>(`/v1/employees/${params.employeeId}/memory/working${query ? `?${query}` : ''}`);

    return {
      items: response.items.map((w): WorkingMemoryItem => ({
        id: w.id,
        employeeId: w.employee_id,
        itemType: w.item_type,
        content: w.content,
        importance: w.importance,
        expiresAt: w.expires_at,
        accessCount: w.access_count,
        lastAccessedAt: w.last_accessed_at,
        createdAt: w.created_at,
        updatedAt: w.updated_at,
      })),
      total: response.total,
    };
  }

  // =========================================================================
  // Tool Catalog Endpoints (PR #80) — proxied from runner, can return 503
  // =========================================================================

  async function listTools(params: { employeeId: string }): Promise<ToolCatalogResponse> {
    const response = await request<{
      items: Array<{ name: string; description: string | null; integration: string | null }>;
      total: number;
      integrations: string[];
      health?: Record<
        string,
        {
          name: string;
          status: string;
          success_count: number;
          failure_count: number;
          timeout_count: number;
          total_calls: number;
          avg_latency_ms: number;
          error_rate: number;
          last_error: string | null;
        }
      >;
    }>(`/v1/employees/${params.employeeId}/tools`);

    const health: Record<string, IntegrationHealth> = {};
    for (const [k, h] of Object.entries(response.health ?? {})) {
      health[k] = {
        name: h.name,
        status: h.status,
        successCount: h.success_count,
        failureCount: h.failure_count,
        timeoutCount: h.timeout_count,
        totalCalls: h.total_calls,
        avgLatencyMs: h.avg_latency_ms,
        errorRate: h.error_rate,
        lastError: h.last_error,
      };
    }
    return {
      items: response.items,
      total: response.total,
      integrations: response.integrations,
      health,
    };
  }

  async function getToolHealth(params: {
    employeeId: string;
    toolName: string;
  }): Promise<IntegrationHealth> {
    const encoded = encodeURIComponent(params.toolName);
    const response = await request<{
      name: string;
      status: string;
      success_count: number;
      failure_count: number;
      timeout_count: number;
      total_calls: number;
      avg_latency_ms: number;
      error_rate: number;
      last_error: string | null;
    }>(`/v1/employees/${params.employeeId}/tools/${encoded}/health`);
    return {
      name: response.name,
      status: response.status,
      successCount: response.success_count,
      failureCount: response.failure_count,
      timeoutCount: response.timeout_count,
      totalCalls: response.total_calls,
      avgLatencyMs: response.avg_latency_ms,
      errorRate: response.error_rate,
      lastError: response.last_error,
    };
  }

  async function listBlockedTools(params: {
    employeeId: string;
  }): Promise<BlockedToolsResponse> {
    const response = await request<{
      items: Array<{
        tool_name: string;
        reason: string;
        employee_role: string | null;
        timestamp: number;
      }>;
      total: number;
      stats: {
        total_decisions: number;
        allowed: number;
        denied: number;
        tainted: boolean;
        cycle_calls: number;
        max_calls_per_cycle: number;
      };
    }>(`/v1/employees/${params.employeeId}/tools/blocked`);
    return {
      items: response.items.map((b) => ({
        toolName: b.tool_name,
        reason: b.reason,
        employeeRole: b.employee_role,
        timestamp: b.timestamp,
      })),
      total: response.total,
      stats: {
        totalDecisions: response.stats.total_decisions,
        allowed: response.stats.allowed,
        denied: response.stats.denied,
        tainted: response.stats.tainted,
        cycleCalls: response.stats.cycle_calls,
        maxCallsPerCycle: response.stats.max_calls_per_cycle,
      },
    };
  }

  // =========================================================================
  // Webhook Token Management + Events (PR #81)
  // =========================================================================

  async function listWebhookTokens(): Promise<WebhookTokenInfo[]> {
    const response = await request<
      Array<{
        integration_id: string;
        provider: string;
        has_token: boolean;
        rotated_at: string | null;
        grace_window_active: boolean;
      }>
    >(`/v1/webhooks/tokens`);
    return response.map((t) => ({
      integrationId: t.integration_id,
      provider: t.provider,
      hasToken: t.has_token,
      rotatedAt: t.rotated_at,
      graceWindowActive: t.grace_window_active,
    }));
  }

  async function createWebhookToken(params: {
    integrationId: string;
  }): Promise<WebhookTokenIssued> {
    const response = await request<{
      integration_id: string;
      provider: string;
      token: string;
      rotated_at: string | null;
    }>(`/v1/webhooks/tokens`, {
      method: 'POST',
      body: JSON.stringify({ integration_id: params.integrationId }),
    });
    return {
      integrationId: response.integration_id,
      provider: response.provider,
      token: response.token,
      rotatedAt: response.rotated_at,
    };
  }

  async function rotateWebhookToken(params: {
    integrationId: string;
  }): Promise<WebhookTokenIssued> {
    const response = await request<{
      integration_id: string;
      provider: string;
      token: string;
      rotated_at: string | null;
    }>(`/v1/webhooks/tokens/${params.integrationId}/rotate`, { method: 'POST' });
    return {
      integrationId: response.integration_id,
      provider: response.provider,
      token: response.token,
      rotatedAt: response.rotated_at,
    };
  }

  async function deleteWebhookToken(params: { integrationId: string }): Promise<void> {
    await request<void>(`/v1/webhooks/tokens/${params.integrationId}`, { method: 'DELETE' });
  }

  async function listWebhookEvents(params: {
    page?: number;
    pageSize?: number;
    provider?: string;
  }): Promise<PaginatedResponse<WebhookAuditEvent>> {
    const searchParams = new URLSearchParams();
    if (params.page !== undefined) searchParams.set('page', params.page.toString());
    if (params.pageSize !== undefined) searchParams.set('page_size', params.pageSize.toString());
    if (params.provider) searchParams.set('provider', params.provider);
    const query = searchParams.toString();

    const response = await request<{
      items: Array<{
        id: string;
        integration_id: string;
        provider: string;
        event_type: string;
        summary: string;
        employees_notified: number;
        occurred_at: string;
      }>;
      total: number;
      page: number;
      page_size: number;
      pages: number;
    }>(`/v1/webhooks/events${query ? `?${query}` : ''}`);

    return {
      items: response.items.map((e) => ({
        id: e.id,
        integrationId: e.integration_id,
        provider: e.provider,
        eventType: e.event_type,
        summary: e.summary,
        employeesNotified: e.employees_notified,
        occurredAt: e.occurred_at,
      })),
      total: response.total,
      page: response.page,
      pageSize: response.page_size,
      pages: response.pages,
    };
  }

  // =========================================================================
  // Scheduler (PR #82)
  // =========================================================================

  function _parseScheduledAction(raw: {
    id: string;
    description: string;
    scheduled_for: string;
    recurring: boolean;
    interval_hours: number | null;
    source: 'employee' | 'user_requested';
    created_at: string | null;
  }): ScheduledAction {
    return {
      id: raw.id,
      description: raw.description,
      scheduledFor: raw.scheduled_for,
      recurring: raw.recurring,
      intervalHours: raw.interval_hours,
      source: raw.source,
      createdAt: raw.created_at,
    };
  }

  async function listScheduledActions(employeeId: string): Promise<{
    items: ScheduledAction[];
    total: number;
  }> {
    const response = await request<{
      items: Array<{
        id: string;
        description: string;
        scheduled_for: string;
        recurring: boolean;
        interval_hours: number | null;
        source: 'employee' | 'user_requested';
        created_at: string | null;
      }>;
      total: number;
    }>(`/v1/employees/${employeeId}/schedule`);
    return {
      items: response.items.map(_parseScheduledAction),
      total: response.total,
    };
  }

  async function createScheduledAction(params: {
    employeeId: string;
    description: string;
    scheduledFor: string;
    recurring: boolean;
    intervalHours?: number;
  }): Promise<ScheduledAction> {
    const body: Record<string, unknown> = {
      description: params.description,
      scheduled_for: params.scheduledFor,
      recurring: params.recurring,
    };
    if (params.intervalHours !== undefined) {
      body.interval_hours = params.intervalHours;
    }
    const response = await request<{
      id: string;
      description: string;
      scheduled_for: string;
      recurring: boolean;
      interval_hours: number | null;
      source: 'employee' | 'user_requested';
      created_at: string | null;
    }>(`/v1/employees/${params.employeeId}/schedule`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
    return _parseScheduledAction(response);
  }

  async function cancelScheduledAction(params: {
    employeeId: string;
    actionId: string;
  }): Promise<void> {
    await request<void>(
      `/v1/employees/${params.employeeId}/schedule/${params.actionId}`,
      { method: 'DELETE' }
    );
  }

  // =========================================================================
  // Tenant Settings (PR #83)
  // =========================================================================

  // The server stores snake_case in a JSONB blob. We convert to camelCase for
  // the frontend. Keep these mappers tight — adding a field is a 4-site edit.

  function _parseSettings(raw: {
    version: number;
    llm: {
      primary_model: string;
      fallback_model: string;
      routing_rules: Record<string, string>;
      provider_allowlist: string[];
    };
    cost: {
      daily_budget_usd: number;
      monthly_budget_usd: number;
      alert_threshold_pct: number;
      hard_stop_budget_usd: number | null;
    };
    cycle: {
      min_interval_seconds: number;
      max_interval_seconds: number;
      adaptive_sensitivity: number;
    };
    trust: {
      current_taint_rules: Array<{
        category: string;
        pattern: string;
        action: 'deny' | 'warn' | 'strip';
        origin: 'platform' | 'tenant';
      }>;
      global_deny_list: string[];
    };
    notifications: {
      inbox_urgent_enabled: boolean;
      inbox_normal_enabled: boolean;
    };
    sales: { quarterly_target_usd: number };
  }): TenantSettingsData {
    return {
      version: raw.version,
      llm: {
        primaryModel: raw.llm.primary_model,
        fallbackModel: raw.llm.fallback_model,
        routingRules: raw.llm.routing_rules,
        providerAllowlist: raw.llm.provider_allowlist,
      },
      cost: {
        dailyBudgetUsd: raw.cost.daily_budget_usd,
        monthlyBudgetUsd: raw.cost.monthly_budget_usd,
        alertThresholdPct: raw.cost.alert_threshold_pct,
        hardStopBudgetUsd: raw.cost.hard_stop_budget_usd,
      },
      cycle: {
        minIntervalSeconds: raw.cycle.min_interval_seconds,
        maxIntervalSeconds: raw.cycle.max_interval_seconds,
        adaptiveSensitivity: raw.cycle.adaptive_sensitivity,
      },
      trust: {
        currentTaintRules: raw.trust.current_taint_rules,
        globalDenyList: raw.trust.global_deny_list,
      },
      notifications: {
        inboxUrgentEnabled: raw.notifications.inbox_urgent_enabled,
        inboxNormalEnabled: raw.notifications.inbox_normal_enabled,
      },
      sales: { quarterlyTargetUsd: raw.sales.quarterly_target_usd },
    };
  }

  function _serializeSettingsUpdate(body: TenantSettingsUpdate): Record<string, unknown> {
    const out: Record<string, unknown> = {};
    if (body.llm) {
      out.llm = {
        primary_model: body.llm.primaryModel,
        fallback_model: body.llm.fallbackModel,
        routing_rules: body.llm.routingRules,
        provider_allowlist: body.llm.providerAllowlist,
      };
    }
    if (body.cost) {
      out.cost = {
        daily_budget_usd: body.cost.dailyBudgetUsd,
        monthly_budget_usd: body.cost.monthlyBudgetUsd,
        alert_threshold_pct: body.cost.alertThresholdPct,
        hard_stop_budget_usd: body.cost.hardStopBudgetUsd,
      };
    }
    if (body.cycle) {
      out.cycle = {
        min_interval_seconds: body.cycle.minIntervalSeconds,
        max_interval_seconds: body.cycle.maxIntervalSeconds,
        adaptive_sensitivity: body.cycle.adaptiveSensitivity,
      };
    }
    if (body.notifications) {
      out.notifications = {
        inbox_urgent_enabled: body.notifications.inboxUrgentEnabled,
        inbox_normal_enabled: body.notifications.inboxNormalEnabled,
      };
    }
    if (body.sales) {
      out.sales = { quarterly_target_usd: body.sales.quarterlyTargetUsd };
    }
    return out;
  }

  async function getSettings(): Promise<TenantSettingsData> {
    const raw = await request<Parameters<typeof _parseSettings>[0]>('/v1/settings');
    return _parseSettings(raw);
  }

  async function updateSettings(
    body: TenantSettingsUpdate
  ): Promise<TenantSettingsUpdateResult> {
    const raw = await request<{
      settings: Parameters<typeof _parseSettings>[0];
      restarting_employees: number;
    }>('/v1/settings', {
      method: 'PUT',
      body: JSON.stringify(_serializeSettingsUpdate(body)),
    });
    return {
      settings: _parseSettings(raw.settings),
      restartingEmployees: raw.restarting_employees,
    };
  }

  return {
    setAuthToken,
    login,
    listRoles,
    listEmployees,
    getEmployee,
    createEmployee,
    updateEmployee,
    deleteEmployee,
    startEmployee,
    stopEmployee,
    pauseEmployee,
    resumeEmployee,
    getEmployeeStatus,
    listActivities,
    getRecentActivities,
    getActivitySummary,
    listProviders,
    connectProvider,
    listCredentials,
    revokeCredential,
    listMCPServers,
    getMCPServer,
    createMCPServer,
    updateMCPServer,
    deleteMCPServer,
    testMCPServer,
    testMCPServerConnection,
    listGoals,
    listIntentions,
    listBeliefs,
    getCostSummary,
    getCostHistory,
    listPlaybooks,
    getPlaybookStats,
    listEpisodicMemory,
    listSemanticMemory,
    listProceduralMemory,
    listWorkingMemory,
    listTools,
    getToolHealth,
    listBlockedTools,
    listWebhookTokens,
    createWebhookToken,
    rotateWebhookToken,
    deleteWebhookToken,
    listWebhookEvents,
    listScheduledActions,
    createScheduledAction,
    cancelScheduledAction,
    getSettings,
    updateSettings,
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
