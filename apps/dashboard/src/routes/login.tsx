import { Navigate } from 'react-router-dom';
import { useAuth } from '@/providers/app-providers';
import { LoginForm } from '@/components/auth/login-form';

export function LoginPage() {
  const { isAuthenticated } = useAuth();

  // Redirect if already authenticated
  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  return (
    <div className="relative min-h-screen w-full bg-background">
      {/* Background grid pattern */}
      <div className="absolute inset-0 bg-grid opacity-50" />

      {/* Gradient orbs */}
      <div className="absolute left-1/4 top-1/4 h-96 w-96 rounded-full bg-primary/5 blur-3xl" />
      <div className="absolute bottom-1/4 right-1/4 h-96 w-96 rounded-full bg-primary/10 blur-3xl" />

      {/* Content */}
      <div className="relative flex min-h-screen flex-col items-center justify-center p-4">
        {/* Logo and branding */}
        <div className="mb-8 text-center">
          <h1 className="font-display text-4xl font-bold tracking-tight">
            <span className="text-gradient-cyan">empla</span>
          </h1>
          <p className="mt-2 text-sm text-muted-foreground font-mono uppercase tracking-widest">
            Digital Employee Platform
          </p>
        </div>

        <LoginForm />

        {/* Footer */}
        <p className="mt-8 text-xs text-muted-foreground">
          Autonomous AI workers for the modern enterprise
        </p>
      </div>
    </div>
  );
}
