import type { InboxBlock } from '@empla/react';
import { ExternalLink, TrendingUp, TrendingDown, Minus } from 'lucide-react';

/**
 * Block renderers for inbox message bodies.
 *
 * Each block kind gets its own component. Unknown kinds fall through
 * to the `<UnknownBlock>` component which renders a JSON preview with
 * a "update your dashboard" hint — this keeps the frontend forward-
 * compatible when the backend introduces new block kinds.
 *
 * All renderers use React text nodes for user-supplied content —
 * never `dangerouslySetInnerHTML`. Blocks come from the LLM via
 * `post_to_inbox()` and must be treated as untrusted HTML.
 */

export function InboxBlockRenderer({ block }: { block: InboxBlock }) {
  switch (block.kind) {
    case 'text':
      return <TextBlock data={block.data} />;
    case 'cost_breakdown':
      return <CostBreakdownBlock data={block.data} />;
    case 'link':
      return <LinkBlock data={block.data} />;
    case 'stat':
      return <StatBlock data={block.data} />;
    case 'list':
      return <ListBlock data={block.data} />;
    default:
      return <UnknownBlock kind={block.kind} data={block.data} />;
  }
}

function TextBlock({ data }: { data: Record<string, unknown> }) {
  const content = typeof data.content === 'string' ? data.content : '';
  // Preserve newlines in the post; the block schema strips HTML.
  return (
    <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">{content}</p>
  );
}

type CostCycle = {
  cycle: number;
  cost_usd: number;
  phase?: string;
  recorded_at?: string;
};

function CostBreakdownBlock({ data }: { data: Record<string, unknown> }) {
  const cycles = Array.isArray(data.cycles) ? (data.cycles as CostCycle[]) : [];
  const total = typeof data.total_usd === 'number' ? data.total_usd : 0;
  const window = typeof data.window === 'string' ? data.window : '';

  return (
    <div className="rounded-lg border border-border bg-muted/30 p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <div className="font-mono text-xs uppercase tracking-wider text-muted-foreground">
            Cost breakdown
          </div>
          {window && <div className="mt-1 text-xs text-muted-foreground">{window}</div>}
        </div>
        <div className="text-right">
          <div className="font-display text-2xl font-bold tabular-nums">
            ${total.toFixed(2)}
          </div>
          <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            Total
          </div>
        </div>
      </div>
      {cycles.length > 0 && (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full text-xs">
            <thead className="border-b border-border bg-muted/50">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Cycle</th>
                <th className="px-3 py-2 text-left font-medium">Phase</th>
                <th className="px-3 py-2 text-right font-medium">Cost</th>
              </tr>
            </thead>
            <tbody>
              {cycles.map((c, idx) => (
                <tr key={idx} className="border-b border-border last:border-0">
                  <td className="px-3 py-2 font-mono">{c.cycle}</td>
                  <td className="px-3 py-2 text-muted-foreground">{c.phase ?? '—'}</td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">
                    ${c.cost_usd.toFixed(4)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function LinkBlock({ data }: { data: Record<string, unknown> }) {
  const label = typeof data.label === 'string' ? data.label : 'Link';
  const url = typeof data.url === 'string' ? data.url : '#';
  // Allow internal routes (start with /) and http(s). Anything else gets
  // flagged to avoid a javascript: URL slipping in from an LLM payload.
  const isSafe = url.startsWith('/') || url.startsWith('http://') || url.startsWith('https://');
  if (!isSafe) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
        Link rejected: unsafe URL scheme
      </span>
    );
  }
  const isExternal = url.startsWith('http://') || url.startsWith('https://');
  return (
    <a
      href={url}
      target={isExternal ? '_blank' : undefined}
      rel={isExternal ? 'noopener noreferrer' : undefined}
      className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium text-primary transition-colors hover:bg-accent"
    >
      {label}
      {isExternal && <ExternalLink className="h-3 w-3" />}
    </a>
  );
}

function StatBlock({ data }: { data: Record<string, unknown> }) {
  const label = typeof data.label === 'string' ? data.label : '';
  const value = typeof data.value === 'string' ? data.value : String(data.value ?? '');
  const trend = data.trend;
  const TrendIcon =
    trend === 'up' ? TrendingUp : trend === 'down' ? TrendingDown : trend === 'flat' ? Minus : null;
  return (
    <div className="inline-flex items-center gap-3 rounded-lg border border-border bg-muted/30 px-4 py-3">
      <div>
        <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          {label}
        </div>
        <div className="font-display text-2xl font-bold tabular-nums">{value}</div>
      </div>
      {TrendIcon && (
        <TrendIcon
          className={
            trend === 'up'
              ? 'h-5 w-5 text-status-active'
              : trend === 'down'
                ? 'h-5 w-5 text-status-error'
                : 'h-5 w-5 text-muted-foreground'
          }
        />
      )}
    </div>
  );
}

type ListItem = { label: string; value?: string | null };

function ListBlock({ data }: { data: Record<string, unknown> }) {
  const items = Array.isArray(data.items) ? (data.items as ListItem[]) : [];
  if (items.length === 0) return null;
  return (
    <ul className="space-y-1 text-sm">
      {items.map((item, idx) => (
        <li key={idx} className="flex items-baseline gap-2">
          <span className="text-muted-foreground">•</span>
          <span className="flex-1">
            <span className="font-medium">{item.label}</span>
            {item.value && <span className="ml-2 font-mono text-xs text-muted-foreground">{item.value}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}

function UnknownBlock({ kind, data }: { kind: string; data: Record<string, unknown> }) {
  return (
    <div className="rounded-md border border-status-paused/40 bg-status-paused/10 p-3">
      <div className="mb-1 font-mono text-[10px] uppercase tracking-wider text-status-paused">
        Unknown block kind: {kind}
      </div>
      <div className="text-xs text-muted-foreground">
        Update your dashboard to render this content. Raw payload:
      </div>
      <pre className="mt-2 overflow-x-auto rounded bg-muted/50 p-2 text-[10px] text-muted-foreground">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}
