import { useState, useCallback, createContext, useContext, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { EmplaProvider } from '@empla/react';
import { TooltipProvider } from '@/components/ui/tooltip';
import { Toaster } from '@/components/ui/sonner';

const STORAGE_KEY = 'empla_auth';

interface AuthState {
  token: string | null;
  userId: string | null;
  tenantId: string | null;
  userName: string | null;
  tenantName: string | null;
}

interface AuthContextValue extends AuthState {
  login: (data: AuthState) => void;
  logout: () => void;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AppProviders');
  }
  return context;
}

function getStoredAuth(): AuthState {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      return JSON.parse(stored);
    }
  } catch {
    // Ignore parsing errors
  }
  return {
    token: null,
    userId: null,
    tenantId: null,
    userName: null,
    tenantName: null,
  };
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60, // 1 minute
      refetchOnWindowFocus: false,
    },
  },
});

interface AppProvidersProps {
  children: ReactNode;
}

export function AppProviders({ children }: AppProvidersProps) {
  const [auth, setAuth] = useState<AuthState>(getStoredAuth);

  const login = useCallback((data: AuthState) => {
    setAuth(data);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  }, []);

  const logout = useCallback(() => {
    setAuth({
      token: null,
      userId: null,
      tenantId: null,
      userName: null,
      tenantName: null,
    });
    localStorage.removeItem(STORAGE_KEY);
    queryClient.clear();
  }, []);

  const handleAuthError = useCallback(() => {
    logout();
    window.location.href = '/login';
  }, [logout]);

  const authValue: AuthContextValue = {
    ...auth,
    login,
    logout,
    isAuthenticated: !!auth.token,
  };

  return (
    <AuthContext.Provider value={authValue}>
      <QueryClientProvider client={queryClient}>
        <EmplaProvider
          config={{
            apiUrl: '/api',
            authToken: auth.token ?? undefined,
            onAuthError: handleAuthError,
            theme: 'dark',
          }}
        >
          <TooltipProvider>
            {children}
            <Toaster />
          </TooltipProvider>
        </EmplaProvider>
      </QueryClientProvider>
    </AuthContext.Provider>
  );
}
