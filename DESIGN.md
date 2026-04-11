# empla Design System

> **Name:** Neo-Industrial Control Center
> **Status:** Extracted from working code 2026-04-11 (PR #77). Source of truth for Phase 5+ UI work.
> **Implementation:** `apps/dashboard/tailwind.config.ts` + `apps/dashboard/src/index.css`

---

## Philosophy

empla is an **operator dashboard** for autonomous digital employees. The aesthetic is a working control center, not a marketing site. Users are running, watching, and trusting their digital workforce. The interface is dense, calm, and deliberate.

**Design principles:**

1. **Industrial, not decorative.** Status glow effects only on actively-running things. No floating circles, no decorative gradients.
2. **Dense but legible.** Operators check many things at once. Prioritize information density over whitespace.
3. **Data is primary, chrome is secondary.** The dashboard shows employees' lived reality. UI frames the data, never competes with it.
4. **Trust through specificity.** Real timestamps in monospace. Real error messages. Never "Something went wrong."
5. **Subtraction default.** If an element doesn't earn its pixels, cut it. No icon decorations in colored circles. No cookie-cutter feature grids.

---

## Palette

Dark theme. HSL values in CSS variables. Defined in `src/index.css`.

| Token | HSL | Purpose |
|---|---|---|
| `--background` | `220 20% 6%` | Page background (deep blue-gray) |
| `--foreground` | `210 20% 95%` | Primary text |
| `--card` | `220 18% 10%` | Card surface (lifted above background) |
| `--card-foreground` | `210 20% 95%` | Text on cards |
| `--popover` | `220 18% 10%` | Popover/dropdown surface |
| `--primary` | `190 100% 50%` | **Cyan — the signature color.** Interactive elements, running status, focus rings. |
| `--primary-foreground` | `220 20% 6%` | Text on cyan backgrounds |
| `--secondary` | `220 15% 18%` | Less-prominent surfaces, buttons |
| `--muted` | `220 15% 15%` | Muted surfaces |
| `--muted-foreground` | `215 16% 55%` | Secondary text, labels, metadata |
| `--accent` | `220 15% 18%` | Hover states on interactive elements |
| `--destructive` | `0 72% 51%` | Errors, delete actions |
| `--border` | `220 15% 18%` | Borders on cards, inputs, separators |
| `--input` | `220 15% 18%` | Form input background |
| `--ring` | `190 100% 50%` | Focus ring (same as primary) |
| `--radius` | `0.5rem` | Base border radius |

**Status colors** (in `tailwind.config.ts`):

| Token | Hex | Use |
|---|---|---|
| `status-active` | `#10B981` | Employee active, healthy tool, saved state |
| `status-running` | `#00D4FF` | Employee running RIGHT NOW, loading indicators |
| `status-paused` | `#F59E0B` | Paused, budget warning, pending admin review |
| `status-stopped` | `#6B7280` | Stopped, inactive, disabled |
| `status-error` | `#EF4444` | Errors, failures, hard-stop triggered |

**Usage rules:**
- Only use status colors for actual status, never for decoration.
- Pair status color with glow (`.glow-cyan`, `.glow-green`, `.glow-amber`, `.glow-red`) only on running entities.
- Never use color alone to convey status — always pair with text or icon.

---

## Typography

Three families, each with a purpose. Defined in `tailwind.config.ts`:

```ts
fontFamily: {
  sans: ['Plus Jakarta Sans', 'system-ui', 'sans-serif'],
  display: ['Outfit', 'system-ui', 'sans-serif'],
  mono: ['JetBrains Mono', 'monospace'],
}
```

| Usage | Family | Tailwind class | Example |
|---|---|---|---|
| Page headings, card titles, stat values | Outfit | `font-display` | `Employees`, `1,896 tests` |
| Body text, form labels, button text | Plus Jakarta Sans | `font-sans` (default) | Paragraphs, descriptions |
| IDs, tokens, timestamps, code, metric labels | JetBrains Mono | `font-mono` | `8f2e...`, `14:32:04`, `cycle.duration_seconds` |

**Typographic scale:**

- Display headings: `font-display text-2xl font-bold tracking-tight`
- Stat values: `font-display text-3xl font-bold`
- Card titles: `font-display text-lg font-semibold`
- Body: `text-sm` (14px)
- Small metadata: `text-xs text-muted-foreground`
- Mono labels: `font-mono text-xs uppercase tracking-wider text-muted-foreground`

**Banned:**
- Default font stacks: `Inter`, `Roboto`, `Arial`, `system-ui` alone
- System-font-only UI — the theme defines three purposeful families

---

## Component Patterns

### Card shell

```tsx
<Card className="border-border/50 bg-card/80 backdrop-blur-sm">
  <CardHeader>
    <CardTitle className="font-display">Title</CardTitle>
    <CardDescription>Optional description</CardDescription>
  </CardHeader>
  <CardContent className="space-y-4">
    {children}
  </CardContent>
</Card>
```

The `backdrop-blur-sm` + `bg-card/80` gives the lifted control-panel look. Do NOT use solid card backgrounds.

### Tabs

Horizontal tab strip. Active state has a cyan underline. Use for primary navigation inside a page (not for top-level routing).

```tsx
<Tabs defaultValue="goals">
  <TabsList>
    <TabsTrigger value="goals">Goals</TabsTrigger>
    <TabsTrigger value="intentions">Intentions</TabsTrigger>
  </TabsList>
  <TabsContent value="goals">...</TabsContent>
  <TabsContent value="intentions">...</TabsContent>
</Tabs>
```

For pages with 4+ tabs, collapse top-level to dropdown at `<768px` viewport.

### Dialog

Modal dialogs for focused actions. Max width `max-w-2xl` for forms, `max-w-md` for confirmations.

```tsx
<Dialog>
  <DialogTrigger asChild>
    <Button>Open</Button>
  </DialogTrigger>
  <DialogContent>
    <DialogHeader>
      <DialogTitle className="font-display">Title</DialogTitle>
    </DialogHeader>
    {content}
    <DialogFooter>
      <DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
      <Button>Save</Button>
    </DialogFooter>
  </DialogContent>
</Dialog>
```

### Stats cards

Use for top-of-page quantitative summaries. See `apps/dashboard/src/components/dashboard/stats-cards.tsx`.

```tsx
<div className="rounded-lg border border-border/50 bg-card/80 p-4 backdrop-blur-sm">
  <p className="font-mono text-xs uppercase tracking-wider text-muted-foreground">
    LABEL
  </p>
  <p className="font-display text-3xl font-bold text-foreground">
    {value}
  </p>
</div>
```

### Empty states

**Every new feature MUST ship with a non-default empty state.** "No items found." is prohibited.

Pattern:
1. Icon in muted color (60% opacity)
2. Heading in `font-display text-lg` explaining WHY it's empty
3. Body in `text-sm text-muted-foreground` explaining what WILL appear
4. Primary action button if one exists ("[Start Employee]", "[Setup Guide]")

Example:
```tsx
<div className="flex flex-col items-center justify-center py-12 text-center">
  <Icon className="h-10 w-10 text-muted-foreground/60 mb-4" />
  <h3 className="font-display text-lg">No episodes yet</h3>
  <p className="mt-2 text-sm text-muted-foreground max-w-sm">
    Your employee's actions will appear here once it starts working.
  </p>
  <Button className="mt-4">Start Employee</Button>
</div>
```

### Error states

Every error has a [Retry] button. Silent failures are prohibited.

```tsx
<div className="flex flex-col items-center justify-center py-16">
  <div className="flex h-12 w-12 items-center justify-center rounded-full border border-destructive/30 bg-destructive/10">
    <AlertCircle className="h-6 w-6 text-destructive" />
  </div>
  <h2 className="mt-4 font-display text-2xl font-bold">Something went wrong</h2>
  <p className="mt-2 text-muted-foreground">{message}</p>
  <Button variant="outline" onClick={onRetry} className="mt-4">
    Try again
  </Button>
</div>
```

---

## Layout Rules

- Max width on content: none (use full viewport) EXCEPT forms: `max-w-2xl`
- Gap between sections: `space-y-6`
- Gap inside cards: `space-y-4`
- Grid columns for card grids: `grid gap-4 md:grid-cols-2 lg:grid-cols-3`
- Main + sidebar: `grid gap-6 lg:grid-cols-3` with main at `lg:col-span-2`

### Responsive breakpoints

| Breakpoint | Width | Target |
|---|---|---|
| `base` | 0-767px | Phone |
| `md` | 768-1023px | Tablet |
| `lg` | 1024-1439px | Laptop |
| `xl` | 1440px+ | Desktop |

Desktop-first is correct for an operator dashboard. Mobile and tablet must work (checking a paused employee at night from a phone) but are not the primary experience.

---

## Accessibility

**Touch targets:** Minimum 44×44px per WCAG 2.5.5. Enforced via `<Button>` primitive: `default` size is `h-11` (44px), `lg` is `h-12` (48px), `sm` is `h-9` (36px — use only in dense non-touch contexts).

**Keyboard navigation:**
- All interactive elements reachable via Tab in logical order
- `focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2`
- Dialog ESC closes, traps focus while open
- Tabs: arrow keys switch, Home/End jump, Enter/Space activate

**Screen reader:**
- Landmarks: `<header role="banner">`, `<main>`, `<nav>`, `<aside role="complementary">`
- Status badges: `aria-label="Status: Active"` — glow alone is not enough
- Loading skeletons: `aria-busy="true"` + `aria-label="Loading {thing}"`
- Toasts: `role="status"` + `aria-live="polite"` for success, `aria-live="assertive"` for urgent

**Color contrast:** All text on `bg-background` must hit 4.5:1 minimum. Already verified for existing `foreground` and `muted-foreground` tokens.

**Motion sensitivity:** `prefers-reduced-motion` is honored via a global media query in `index.css` that disables all animation durations and transitions. See the bottom of `src/index.css`.

**Never rely on color alone.** Status always pairs color with text or icon.

---

## Anti-Slop Rules (what NOT to do)

Patterns that scream "AI-generated" and must be avoided:

1. **Purple/violet/indigo gradient backgrounds.** empla is cyan.
2. **3-column feature grids** with icon-in-colored-circle + bold title + 2-line description. This is the most recognizable AI layout. Never ship it.
3. **Icons in colored circles as section decoration.** Use icons for function, not decoration.
4. **Centered everything.** Left-align text. Grid-align layouts.
5. **Uniform bubbly border-radius on every element.** empla uses `0.5rem` consistently. No "fun" bloat.
6. **Decorative blobs, floating circles, wavy SVG dividers.** If a section feels empty, add better content. Not decoration.
7. **Emoji as design elements.** empla is operator-grade. Icons, not emoji.
8. **Colored left-border on cards.** The only exception is the running indicator on employee cards (`absolute left-0 top-0 h-full w-1 bg-status-running`) which is intentional status, not decoration.
9. **Generic hero copy.** "Welcome to empla", "Unlock the power of autonomous employees" — banned. Be specific about what the user sees and does.
10. **Cookie-cutter section rhythm.** hero → 3 features → testimonials → pricing → CTA is marketing template. empla is an app, not a landing page.

---

## Updating this document

This document is extracted from working code. When you change the design system:

1. Update `apps/dashboard/tailwind.config.ts` or `src/index.css` first.
2. Update this document to match.
3. Both changes ship in the same PR.

Stale design docs are worse than none. Keep this honest.
