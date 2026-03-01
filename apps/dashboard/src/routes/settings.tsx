import { Link } from 'react-router-dom';
import { User, Building2, Plug, Terminal } from 'lucide-react';
import { useAuth } from '@/providers/app-providers';
import { useProviders, useCredentials } from '@empla/react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

export function SettingsPage() {
  const auth = useAuth();
  const { data: providers } = useProviders();
  const { data: credentials } = useCredentials();

  const availableProviders = providers?.filter((p) => p.available).length ?? 0;
  const activeCredentials = credentials?.length ?? 0;

  return (
    <div className="space-y-6">
      <div className="grid gap-6 md:grid-cols-2">
        {/* Your Account */}
        <Card className="border-border/50 bg-card/80 backdrop-blur-sm">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base font-display">
              <User className="h-4 w-4 text-primary" />
              Your Account
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <InfoRow label="Name" value={auth.userName ?? 'Unknown'} />
            <InfoRow label="User ID" value={auth.userId ?? 'Unknown'} mono />
          </CardContent>
        </Card>

        {/* Organization */}
        <Card className="border-border/50 bg-card/80 backdrop-blur-sm">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base font-display">
              <Building2 className="h-4 w-4 text-primary" />
              Organization
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <InfoRow label="Tenant" value={auth.tenantName ?? 'Unknown'} />
            <InfoRow label="Tenant ID" value={auth.tenantId ?? 'Unknown'} mono />
          </CardContent>
        </Card>

        {/* Integrations Summary */}
        <Card className="border-border/50 bg-card/80 backdrop-blur-sm">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base font-display">
              <Plug className="h-4 w-4 text-primary" />
              Integrations Summary
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <InfoRow label="Available Providers" value={String(availableProviders)} />
            <InfoRow label="Active Credentials" value={String(activeCredentials)} />
            <Button variant="outline" size="sm" asChild className="mt-2">
              <Link to="/integrations">Manage Integrations</Link>
            </Button>
          </CardContent>
        </Card>

        {/* Platform Administration */}
        <Card className="border-border/50 bg-card/80 backdrop-blur-sm">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base font-display">
              <Terminal className="h-4 w-4 text-primary" />
              Platform Administration
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Admin operations (managing OAuth apps, tenants, users) are handled via CLI.
            </p>
            <div className="mt-3 rounded-md bg-muted/30 p-3">
              <code className="text-xs text-muted-foreground">
                uv run python scripts/manage-platform-apps.py list
              </code>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function InfoRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className={mono ? 'font-mono text-sm text-foreground' : 'text-sm font-medium text-foreground'}>
        {value}
      </span>
    </div>
  );
}
