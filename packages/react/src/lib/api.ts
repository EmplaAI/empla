/**
 * @empla/react - API Client
 *
 * HTTP client for communicating with the empla API.
 */

import type {
  Activity,
  ActivitySummary,
  ConnectRequest,
  ConnectResponse,
  CredentialSource,
  CredentialStatus,
  CredentialType,
  Employee,
  EmployeeCreate,
  EmployeeRuntimeStatus,
  EmployeeUpdate,
  IntegrationCredential,
  IntegrationProvider,
  LoginResponse,
  PaginatedResponse,
  ProviderInfo,
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

      const message =
        (data as { detail?: string })?.detail ||
        rawText?.substring(0, 200) ||
        `Request failed: ${response.statusText}`;

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

  return {
    setAuthToken,
    login,
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
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
