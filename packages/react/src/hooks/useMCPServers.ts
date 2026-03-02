/**
 * @empla/react - MCP Server Hooks
 *
 * React Query hooks for MCP server management.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useEmplaApi } from '../provider';
import type { MCPServerCreate, MCPServerTestRequest, MCPServerUpdate } from '../types';

export const mcpServerKeys = {
  all: ['mcp-servers'] as const,
  list: () => [...mcpServerKeys.all, 'list'] as const,
  detail: (id: string) => [...mcpServerKeys.all, 'detail', id] as const,
};

/**
 * List all MCP servers for the current tenant.
 */
export function useMCPServers() {
  const api = useEmplaApi();
  return useQuery({
    queryKey: mcpServerKeys.list(),
    queryFn: () => api.listMCPServers(),
  });
}

/**
 * Get a single MCP server by ID.
 */
export function useMCPServer(id: string) {
  const api = useEmplaApi();
  return useQuery({
    queryKey: mcpServerKeys.detail(id),
    queryFn: () => api.getMCPServer(id),
    enabled: !!id,
  });
}

/**
 * Create a new MCP server.
 */
export function useCreateMCPServer() {
  const api = useEmplaApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: MCPServerCreate) => api.createMCPServer(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: mcpServerKeys.list() });
    },
  });
}

/**
 * Update an existing MCP server.
 */
export function useUpdateMCPServer() {
  const api = useEmplaApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: MCPServerUpdate }) =>
      api.updateMCPServer(id, data),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: mcpServerKeys.list() });
      queryClient.invalidateQueries({ queryKey: mcpServerKeys.detail(variables.id) });
    },
  });
}

/**
 * Delete an MCP server.
 */
export function useDeleteMCPServer() {
  const api = useEmplaApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteMCPServer(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: mcpServerKeys.list() });
    },
  });
}

/**
 * Test an unsaved MCP server connection.
 */
export function useTestMCPServer() {
  const api = useEmplaApi();
  return useMutation({
    mutationFn: (data: MCPServerTestRequest) => api.testMCPServer(data),
  });
}

/**
 * Test a saved MCP server's connection and refresh discovered tools.
 */
export function useTestMCPServerConnection() {
  const api = useEmplaApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.testMCPServerConnection(id),
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: mcpServerKeys.list() });
      queryClient.invalidateQueries({ queryKey: mcpServerKeys.detail(id) });
    },
  });
}
