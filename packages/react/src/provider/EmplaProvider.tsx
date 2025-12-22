/**
 * @empla/react - Empla Provider
 *
 * Context provider for the empla React SDK.
 * Provides API client and React Query configuration to child components.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

import { createApiClient, type ApiClient } from '../lib/api';
import type { EmplaConfig, LoginResponse } from '../types';

/**
 * Context value containing API client and auth state.
 */
interface EmplaContextValue {
  /** API client instance */
  api: ApiClient;

  /** Configuration */
  config: EmplaConfig;

  /** Whether user is authenticated */
  isAuthenticated: boolean;

  /** Current auth token */
  authToken: string | undefined;

  /** Login and set auth token */
  login: (email: string, tenantSlug: string) => Promise<LoginResponse>;

  /** Logout and clear auth token */
  logout: () => void;

  /** Set auth token directly */
  setAuthToken: (token: string | undefined) => void;
}

const EmplaContext = createContext<EmplaContextValue | null>(null);

/**
 * Default React Query client configuration.
 */
function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 1000 * 60, // 1 minute
        retry: 1,
        refetchOnWindowFocus: false,
      },
    },
  });
}

/**
 * Props for EmplaProvider.
 */
export interface EmplaProviderProps {
  /** Configuration for the empla SDK */
  config: EmplaConfig;

  /** Child components */
  children: ReactNode;

  /** Optional custom QueryClient */
  queryClient?: QueryClient;
}

/**
 * Provider component for the empla React SDK.
 *
 * Wraps your application to provide empla functionality to all components.
 *
 * @example
 * ```tsx
 * import { EmplaProvider } from '@empla/react';
 *
 * function App() {
 *   return (
 *     <EmplaProvider config={{ apiUrl: '/api', authToken: token }}>
 *       <YourApp />
 *     </EmplaProvider>
 *   );
 * }
 * ```
 */
export function EmplaProvider({
  config,
  children,
  queryClient: providedQueryClient,
}: EmplaProviderProps) {
  const [authToken, setAuthTokenState] = useState<string | undefined>(
    config.authToken
  );

  // Create query client (memoized)
  const queryClient = useMemo(
    () => providedQueryClient ?? createQueryClient(),
    [providedQueryClient]
  );

  // Create API client (memoized, updates when authToken changes)
  const api = useMemo(
    () =>
      createApiClient({
        baseUrl: config.apiUrl,
        authToken,
        onAuthError: config.onAuthError,
      }),
    [config.apiUrl, authToken, config.onAuthError]
  );

  // Set auth token
  const setAuthToken = useCallback((token: string | undefined) => {
    setAuthTokenState(token);
  }, []);

  // Login
  const login = useCallback(
    async (email: string, tenantSlug: string): Promise<LoginResponse> => {
      const response = await api.login(email, tenantSlug);
      setAuthTokenState(response.token);
      api.setAuthToken(response.token);
      return response;
    },
    [api]
  );

  // Logout
  const logout = useCallback(() => {
    setAuthTokenState(undefined);
    api.setAuthToken(undefined);
    queryClient.clear();
  }, [api, queryClient]);

  // Context value
  const contextValue = useMemo<EmplaContextValue>(
    () => ({
      api,
      config,
      isAuthenticated: !!authToken,
      authToken,
      login,
      logout,
      setAuthToken,
    }),
    [api, config, authToken, login, logout, setAuthToken]
  );

  return (
    <EmplaContext.Provider value={contextValue}>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </EmplaContext.Provider>
  );
}

/**
 * Hook to access the empla context.
 *
 * @throws Error if used outside of EmplaProvider
 *
 * @example
 * ```tsx
 * function MyComponent() {
 *   const { api, isAuthenticated, login, logout } = useEmplaContext();
 *
 *   if (!isAuthenticated) {
 *     return <LoginForm onLogin={login} />;
 *   }
 *
 *   return <Dashboard />;
 * }
 * ```
 */
export function useEmplaContext(): EmplaContextValue {
  const context = useContext(EmplaContext);

  if (!context) {
    throw new Error('useEmplaContext must be used within an EmplaProvider');
  }

  return context;
}

/**
 * Hook to access the API client.
 *
 * Convenience hook for just getting the API client.
 */
export function useEmplaApi(): ApiClient {
  const { api } = useEmplaContext();
  return api;
}

export { EmplaContext };
