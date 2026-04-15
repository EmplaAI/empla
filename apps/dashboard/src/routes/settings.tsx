import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertCircle,
  Bot,
  Building2,
  DollarSign,
  Gauge,
  Mail,
  Plug,
  Shield,
  Target,
  Terminal,
  User,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  useCredentials,
  useProviders,
  useSettings,
  useUpdateSettings,
  type TenantSettingsData,
  type TenantSettingsUpdate,
} from '@empla/react';
import { useAuth } from '@/providers/app-providers';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

// Known models — kept small on purpose. Additions happen here (not by typing
// a free string) so operators don't accidentally point at a deprecated model.
const KNOWN_MODELS = [
  'claude-opus-4-6',
  'claude-sonnet-4-6',
  'claude-haiku-4-5-20251001',
  'gpt-5',
  'gpt-4o',
];

export function SettingsPage() {
  const auth = useAuth();
  const settingsQuery = useSettings();

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <div>
        <h1 className="font-display text-2xl font-bold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          LLM routing, cost budgets, cycle tuning, notifications, and trust.
          Saving triggers a ~5-10s runner restart so employees pick up new
          config at startup.
        </p>
      </div>

      <IdentityCards auth={auth} />

      {settingsQuery.isLoading ? (
        <Skeleton className="h-80 w-full" />
      ) : settingsQuery.error || !settingsQuery.data ? (
        <Card className="border-destructive/30 bg-destructive/5">
          <CardContent className="flex items-center gap-3 py-6">
            <AlertCircle className="h-5 w-5 text-destructive" />
            <div>
              <p className="text-sm">Couldn't load settings.</p>
              <Button
                variant="outline"
                size="sm"
                className="mt-2"
                onClick={() => settingsQuery.refetch()}
              >
                Try again
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        <SettingsEditor data={settingsQuery.data} />
      )}
    </div>
  );
}

function IdentityCards({ auth }: { auth: ReturnType<typeof useAuth> }) {
  const { data: providers } = useProviders();
  const { data: credentials } = useCredentials();
  const availableProviders = providers?.filter((p) => p.available).length ?? 0;
  const activeCredentials = credentials?.length ?? 0;

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card className="border-border/50 bg-card/80 backdrop-blur-sm">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base font-display">
            <User className="h-4 w-4 text-primary" />
            Your account
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <InfoRow label="Name" value={auth.userName ?? 'Unknown'} />
          <InfoRow label="User ID" value={auth.userId ?? 'Unknown'} mono />
        </CardContent>
      </Card>

      <Card className="border-border/50 bg-card/80 backdrop-blur-sm">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base font-display">
            <Building2 className="h-4 w-4 text-primary" />
            Organization
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <InfoRow label="Tenant" value={auth.tenantName ?? 'Unknown'} />
          <InfoRow label="Tenant ID" value={auth.tenantId ?? 'Unknown'} mono />
          <div className="flex items-center justify-between pt-1 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <Plug className="h-3 w-3" /> {availableProviders} providers /{' '}
              {activeCredentials} credentials
            </span>
            <Button variant="ghost" size="sm" className="h-7 px-2" asChild>
              <Link to="/integrations">Manage</Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function SettingsEditor({ data }: { data: TenantSettingsData }) {
  const update = useUpdateSettings();
  const [draft, setDraft] = useState<TenantSettingsData>(data);
  const [saving, setSaving] = useState(false);

  // Reset draft when upstream data changes (e.g., after save).
  useEffect(() => {
    setDraft(data);
  }, [data]);

  const dirty = JSON.stringify(draft) !== JSON.stringify(data);

  const handleSave = async () => {
    setSaving(true);
    try {
      // Build a diff'd update — only send sections the user actually changed.
      const body: TenantSettingsUpdate = {};
      if (JSON.stringify(draft.llm) !== JSON.stringify(data.llm)) body.llm = draft.llm;
      if (JSON.stringify(draft.cost) !== JSON.stringify(data.cost))
        body.cost = draft.cost;
      if (JSON.stringify(draft.cycle) !== JSON.stringify(data.cycle))
        body.cycle = draft.cycle;
      if (JSON.stringify(draft.notifications) !== JSON.stringify(data.notifications))
        body.notifications = draft.notifications;
      if (JSON.stringify(draft.sales) !== JSON.stringify(data.sales))
        body.sales = draft.sales;

      const result = await update.mutateAsync(body);
      const n = result.restartingEmployees;
      toast.success(
        n > 0
          ? `Saved. Restarting ${n} employee${n === 1 ? '' : 's'} (~5-10s)...`
          : 'Saved.',
      );
    } catch (err) {
      const msg = err instanceof Error && err.message ? err.message : 'Save failed';
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="border-border/50 bg-card/80 backdrop-blur-sm">
      <CardHeader className="flex flex-row items-start justify-between pb-3">
        <div>
          <CardTitle className="font-display text-lg font-semibold">
            Tenant configuration
          </CardTitle>
          <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
            v{data.version}
          </p>
        </div>
        <Button onClick={handleSave} disabled={!dirty || saving}>
          {saving ? 'Saving...' : dirty ? 'Save changes' : 'Saved'}
        </Button>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="llm">
          <TabsList className="w-full justify-start overflow-x-auto">
            <TabsTrigger value="llm">
              <Bot className="mr-1.5 h-3.5 w-3.5" /> LLM
            </TabsTrigger>
            <TabsTrigger value="cost">
              <DollarSign className="mr-1.5 h-3.5 w-3.5" /> Cost
            </TabsTrigger>
            <TabsTrigger value="cycle">
              <Gauge className="mr-1.5 h-3.5 w-3.5" /> Cycle
            </TabsTrigger>
            <TabsTrigger value="trust">
              <Shield className="mr-1.5 h-3.5 w-3.5" /> Trust
            </TabsTrigger>
            <TabsTrigger value="notifications">
              <Mail className="mr-1.5 h-3.5 w-3.5" /> Notifications
            </TabsTrigger>
            <TabsTrigger value="sales">
              <Target className="mr-1.5 h-3.5 w-3.5" /> Sales
            </TabsTrigger>
          </TabsList>

          <TabsContent value="llm">
            <LLMSection draft={draft} setDraft={setDraft} />
          </TabsContent>
          <TabsContent value="cost">
            <CostSection draft={draft} setDraft={setDraft} />
          </TabsContent>
          <TabsContent value="cycle">
            <CycleSection draft={draft} setDraft={setDraft} />
          </TabsContent>
          <TabsContent value="trust">
            <TrustSection draft={draft} />
          </TabsContent>
          <TabsContent value="notifications">
            <NotificationsSection draft={draft} setDraft={setDraft} />
          </TabsContent>
          <TabsContent value="sales">
            <SalesSection draft={draft} setDraft={setDraft} />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Sections
// ---------------------------------------------------------------------------

type SetDraft = React.Dispatch<React.SetStateAction<TenantSettingsData>>;

function LLMSection({ draft, setDraft }: { draft: TenantSettingsData; setDraft: SetDraft }) {
  return (
    <div className="space-y-4 py-2">
      <div className="grid gap-4 md:grid-cols-2">
        <ModelSelect
          label="Primary model"
          hint="Used for tool-calling, deep reasoning, and intent execution."
          value={draft.llm.primaryModel}
          onChange={(v) => setDraft((d) => ({ ...d, llm: { ...d.llm, primaryModel: v } }))}
        />
        <ModelSelect
          label="Fallback model"
          hint="Cheaper/faster model used when primary is rate-limited or times out."
          value={draft.llm.fallbackModel}
          onChange={(v) => setDraft((d) => ({ ...d, llm: { ...d.llm, fallbackModel: v } }))}
        />
      </div>
      <div>
        <Label className="text-xs">Provider allowlist</Label>
        <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
          {draft.llm.providerAllowlist.join(', ') || '(empty — platform admin will set)'}
        </p>
      </div>
    </div>
  );
}

function ModelSelect({
  label,
  hint,
  value,
  onChange,
}: {
  label: string;
  hint?: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs">{label}</Label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      >
        {(KNOWN_MODELS.includes(value) ? KNOWN_MODELS : [value, ...KNOWN_MODELS]).map(
          (m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ),
        )}
      </select>
      {hint ? <p className="text-[11px] text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

function CostSection({ draft, setDraft }: { draft: TenantSettingsData; setDraft: SetDraft }) {
  const { cost } = draft;
  const burn = cost.dailyBudgetUsd > 0 ? cost.monthlyBudgetUsd / cost.dailyBudgetUsd : 0;
  return (
    <div className="space-y-4 py-2">
      <div className="grid gap-4 md:grid-cols-2">
        <NumberField
          label="Daily budget (USD)"
          value={cost.dailyBudgetUsd}
          step={1}
          onChange={(v) => setDraft((d) => ({ ...d, cost: { ...d.cost, dailyBudgetUsd: v } }))}
        />
        <NumberField
          label="Monthly budget (USD)"
          value={cost.monthlyBudgetUsd}
          step={10}
          onChange={(v) =>
            setDraft((d) => ({ ...d, cost: { ...d.cost, monthlyBudgetUsd: v } }))
          }
        />
        <NumberField
          label="Alert threshold (%)"
          value={cost.alertThresholdPct}
          step={5}
          min={1}
          max={99}
          onChange={(v) =>
            setDraft((d) => ({ ...d, cost: { ...d.cost, alertThresholdPct: v } }))
          }
        />
        <NumberField
          label="Hard-stop budget (USD)"
          hint="Enforcement lands in PR #86 (with inbox)."
          value={cost.hardStopBudgetUsd ?? 0}
          step={10}
          onChange={(v) =>
            setDraft((d) => ({
              ...d,
              cost: { ...d.cost, hardStopBudgetUsd: v > 0 ? v : null },
            }))
          }
        />
      </div>
      {burn > 0 ? (
        <p className="text-xs text-muted-foreground">
          At daily spend = daily budget, your monthly budget covers{' '}
          <span className="font-mono">{burn.toFixed(1)}</span> days of spend.
        </p>
      ) : null}
    </div>
  );
}

function CycleSection({ draft, setDraft }: { draft: TenantSettingsData; setDraft: SetDraft }) {
  const { cycle } = draft;
  return (
    <div className="grid gap-4 py-2 md:grid-cols-3">
      <NumberField
        label="Min interval (seconds)"
        value={cycle.minIntervalSeconds}
        step={5}
        min={5}
        onChange={(v) =>
          setDraft((d) => ({ ...d, cycle: { ...d.cycle, minIntervalSeconds: v } }))
        }
      />
      <NumberField
        label="Max interval (seconds)"
        value={cycle.maxIntervalSeconds}
        step={60}
        min={30}
        onChange={(v) =>
          setDraft((d) => ({ ...d, cycle: { ...d.cycle, maxIntervalSeconds: v } }))
        }
      />
      <NumberField
        label="Adaptive sensitivity"
        hint="0 = fixed cadence; 1 = fully reactive to opportunity signal."
        value={cycle.adaptiveSensitivity}
        step={0.05}
        min={0}
        max={1}
        onChange={(v) =>
          setDraft((d) => ({ ...d, cycle: { ...d.cycle, adaptiveSensitivity: v } }))
        }
      />
    </div>
  );
}

function TrustSection({ draft }: { draft: TenantSettingsData }) {
  return (
    <div className="space-y-4 py-2">
      <div className="rounded-lg border border-border/40 bg-muted/30 p-3">
        <p className="text-sm">
          <Shield className="mr-1 inline h-3.5 w-3.5 text-muted-foreground" />
          Trust rules are read-only here. Editing taint semantics without a
          design review is a foot-gun we're not shipping yet.
        </p>
      </div>
      <div>
        <p className="mb-2 font-mono text-xs uppercase tracking-wider text-muted-foreground">
          Active taint rules ({draft.trust.currentTaintRules.length})
        </p>
        {draft.trust.currentTaintRules.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            None active. Employees execute tools against the default trust boundary.
          </p>
        ) : (
          <ul className="space-y-1 text-sm">
            {draft.trust.currentTaintRules.map((r, i) => (
              <li
                key={i}
                className="rounded-md border border-border/40 bg-muted/20 px-3 py-1.5 font-mono text-xs"
              >
                <span className="text-primary">{r.category}</span>{' '}
                <span className="text-muted-foreground">{r.pattern}</span>{' '}
                <span className="text-status-paused">{r.action}</span>{' '}
                <span className="text-muted-foreground">({r.origin})</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function NotificationsSection({
  draft,
  setDraft,
}: {
  draft: TenantSettingsData;
  setDraft: SetDraft;
}) {
  const { notifications } = draft;
  return (
    <div className="space-y-3 py-2">
      <ToggleRow
        label="Urgent inbox messages"
        hint="Things like cost hard-stops and trust-boundary blocks (PR #86 delivers these)."
        checked={notifications.inboxUrgentEnabled}
        onChange={(v) =>
          setDraft((d) => ({
            ...d,
            notifications: { ...d.notifications, inboxUrgentEnabled: v },
          }))
        }
      />
      <ToggleRow
        label="Normal inbox messages"
        hint="Summaries, questions, suggestions the employee surfaces to you."
        checked={notifications.inboxNormalEnabled}
        onChange={(v) =>
          setDraft((d) => ({
            ...d,
            notifications: { ...d.notifications, inboxNormalEnabled: v },
          }))
        }
      />
    </div>
  );
}

function SalesSection({ draft, setDraft }: { draft: TenantSettingsData; setDraft: SetDraft }) {
  return (
    <div className="space-y-3 py-2">
      <NumberField
        label="Quarterly target (USD)"
        hint="Used by HubSpot pipeline-coverage calculations. Replaces the 100k default."
        value={draft.sales.quarterlyTargetUsd}
        step={10_000}
        onChange={(v) =>
          setDraft((d) => ({ ...d, sales: { quarterlyTargetUsd: v } }))
        }
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Leaf inputs
// ---------------------------------------------------------------------------

function NumberField({
  label,
  hint,
  value,
  onChange,
  step,
  min,
  max,
}: {
  label: string;
  hint?: string;
  value: number;
  onChange: (v: number) => void;
  step?: number;
  min?: number;
  max?: number;
}) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs">{label}</Label>
      <Input
        type="number"
        value={value}
        step={step}
        min={min}
        max={max}
        onChange={(e) => {
          const v = parseFloat(e.target.value);
          if (!Number.isNaN(v)) onChange(v);
        }}
      />
      {hint ? <p className="text-[11px] text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

function ToggleRow({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-start gap-3 rounded-lg border border-border/40 bg-muted/20 p-3">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5"
      />
      <div className="min-w-0 flex-1">
        <p className="text-sm">{label}</p>
        {hint ? <p className="mt-0.5 text-[11px] text-muted-foreground">{hint}</p> : null}
      </div>
    </label>
  );
}

// ---------------------------------------------------------------------------
// Footer — platform admin
// ---------------------------------------------------------------------------

function InfoRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span
        className={mono ? 'font-mono text-sm text-foreground' : 'text-sm font-medium text-foreground'}
      >
        {value}
      </span>
    </div>
  );
}

export function _PlatformAdminHint() {
  // Kept for future reference; platform admin operations still ship via CLI.
  return (
    <div className="rounded-md bg-muted/30 p-3">
      <Terminal className="mr-1 inline h-3.5 w-3.5" />
      <code className="text-xs text-muted-foreground">
        uv run python scripts/manage-platform-apps.py list
      </code>
    </div>
  );
}
