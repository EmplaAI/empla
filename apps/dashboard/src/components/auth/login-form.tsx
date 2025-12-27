import { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';
import { useAuth } from '@/providers/app-providers';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import type { LoginResponse } from '@empla/react';

export function LoginForm() {
  const [email, setEmail] = useState('');
  const [tenantSlug, setTenantSlug] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const from = (location.state as { from?: { pathname: string } })?.from?.pathname || '/';

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setIsLoading(true);

    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          email,
          tenant_slug: tenantSlug,
        }),
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Login failed' }));
        throw new Error(error.detail || 'Login failed');
      }

      const data: LoginResponse = await response.json();

      login({
        token: data.token,
        userId: data.userId,
        tenantId: data.tenantId,
        userName: data.userName,
        tenantName: data.tenantName,
      });

      toast.success('Welcome back!', {
        description: `Logged in as ${data.userName}`,
      });

      navigate(from, { replace: true });
    } catch (error) {
      toast.error('Authentication failed', {
        description: error instanceof Error ? error.message : 'Please check your credentials',
      });
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <Card className="w-full max-w-md border-border/50 bg-card/80 backdrop-blur-sm">
      <CardHeader className="space-y-1 text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full border border-primary/30 bg-primary/10">
          <svg
            className="h-6 w-6 text-primary"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
          >
            <path d="M6 9L12 5L18 9V15L12 19L6 15V9Z" />
            <circle cx="12" cy="12" r="3" fill="currentColor" />
          </svg>
        </div>
        <CardTitle className="text-2xl font-display">Command Center</CardTitle>
        <CardDescription className="text-muted-foreground">
          Access your digital employee dashboard
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="email" className="text-sm font-medium">
              Email
            </Label>
            <Input
              id="email"
              type="email"
              placeholder="you@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              className="bg-background/50"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="tenant" className="text-sm font-medium">
              Organization
            </Label>
            <Input
              id="tenant"
              type="text"
              placeholder="your-company"
              value={tenantSlug}
              onChange={(e) => setTenantSlug(e.target.value)}
              required
              autoComplete="organization"
              className="bg-background/50"
            />
            <p className="text-xs text-muted-foreground">
              Your organization's unique identifier
            </p>
          </div>
          <Button
            type="submit"
            className="w-full"
            disabled={isLoading}
          >
            {isLoading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Authenticating...
              </>
            ) : (
              'Access Dashboard'
            )}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
