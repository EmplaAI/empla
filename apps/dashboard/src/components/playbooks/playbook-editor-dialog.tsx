import { useEffect, useState } from 'react';
import { GripVertical, Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import {
  useCreatePlaybook,
  useUpdatePlaybook,
} from '@empla/react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

/** Step shape preserves arbitrary keys (tool, args, condition, etc.) that
 *  reflection-promoted playbooks attach. The editor only mutates `description`
 *  but round-trips the rest verbatim so admin edits don't strip tool bindings. */
export type PlaybookEditableStep = { description: string } & Record<string, unknown>;

export interface PlaybookEditableData {
  id?: string;
  name: string;
  description: string;
  steps: PlaybookEditableStep[];
  enabled: boolean;
  version?: number;
}

interface PlaybookEditorDialogProps {
  open: boolean;
  onClose: () => void;
  employeeId: string;
  initial?: PlaybookEditableData; // undefined → create mode
  /** Notifies the parent that the upstream list should refetch
   *  (parent is responsible for calling refetch / invalidate). */
  onSaved?: (savedVersion: number) => void;
}

const EMPTY: PlaybookEditableData = {
  name: '',
  description: '',
  steps: [{ description: '' }],
  enabled: true,
};

export function PlaybookEditorDialog({
  open,
  onClose,
  employeeId,
  initial,
  onSaved,
}: PlaybookEditorDialogProps) {
  const isEdit = initial?.id !== undefined;
  const create = useCreatePlaybook(employeeId);
  const update = useUpdatePlaybook(employeeId);
  const [draft, setDraft] = useState<PlaybookEditableData>(initial ?? EMPTY);

  const saving = create.isPending || update.isPending;

  // Reset draft when the dialog reopens with new initial data. Only
  // fires when the dialog actually opens (open transitions false→true)
  // so reopens with the same initial don't clobber an in-progress draft
  // from a re-render.
  useEffect(() => {
    if (open) {
      setDraft(initial ?? EMPTY);
    }
  }, [initial, open]);

  const isDirty = JSON.stringify(draft) !== JSON.stringify(initial ?? EMPTY);

  // Confirm before discarding unsaved edits. Used by both the Esc/overlay
  // close path AND the Cancel button so the guard is consistent.
  const requestClose = () => {
    if (saving) return;
    if (isDirty && !window.confirm('Discard unsaved changes?')) return;
    onClose();
  };

  const handleOpenChange = (next: boolean) => {
    if (next) return;
    requestClose();
  };

  const moveStep = (from: number, to: number) => {
    if (to < 0 || to >= draft.steps.length) return;
    const next = [...draft.steps];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    setDraft({ ...draft, steps: next });
  };

  const addStep = () => {
    if (draft.steps.length >= 50) {
      toast.error('Max 50 steps per playbook');
      return;
    }
    // New step has only `description` — that's intentional: we don't
    // know what extras the LLM/loop expects unless the playbook came
    // pre-promoted. Tool bindings on user-created steps would be a
    // separate UX surface (future PR).
    setDraft({ ...draft, steps: [...draft.steps, { description: '' }] });
  };

  const removeStep = (i: number) => {
    if (draft.steps.length === 1) {
      toast.error('A playbook needs at least one step');
      return;
    }
    setDraft({
      ...draft,
      steps: draft.steps.filter((_, idx) => idx !== i),
    });
  };

  const setStep = (i: number, description: string) => {
    setDraft({
      ...draft,
      steps: draft.steps.map((s, idx) =>
        // PRESERVE every other key on the step (tool bindings, args,
        // conditions). The editor only mutates description; everything
        // else round-trips verbatim. Stripping extras would silently
        // delete tool bindings on autonomously-promoted playbooks.
        idx === i ? { ...s, description } : s,
      ),
    });
  };

  const handleSave = async () => {
    if (!draft.name.trim() || !draft.description.trim()) {
      toast.error('Name and description are required');
      return;
    }
    if (draft.steps.some((s) => !s.description.trim())) {
      toast.error('Empty step — fill it in or remove it');
      return;
    }

    try {
      if (isEdit && initial?.id !== undefined && initial.version !== undefined) {
        const result = await update.mutateAsync({
          playbookId: initial.id,
          expectedVersion: initial.version,
          name: draft.name,
          description: draft.description,
          steps: draft.steps,
          enabled: draft.enabled,
        });
        toast.success(`Saved (v${result.version})`);
        onSaved?.(result.version);
      } else {
        const result = await create.mutateAsync({
          name: draft.name,
          description: draft.description,
          steps: draft.steps,
          enabled: draft.enabled,
        });
        toast.success('Playbook created');
        onSaved?.(result.version);
      }
      onClose();
    } catch (err) {
      // The API surfaces 409 conflicts as Error.message via the empla
      // ApiError unwrapping. Show that text so the user knows to reload.
      const msg =
        err instanceof Error && err.message ? err.message : 'Save failed';
      toast.error(msg);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="font-display">
            {isEdit ? 'Edit playbook' : 'New playbook'}
          </DialogTitle>
          <DialogDescription>
            Playbooks are reusable procedures the employee can run. Steps fire
            in order; the employee binds tools to each step at execution time.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="pb-name" className="text-xs">
              Name
            </Label>
            <Input
              id="pb-name"
              value={draft.name}
              maxLength={200}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              placeholder="e.g. Send weekly customer health check"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="pb-desc" className="text-xs">
              Description
            </Label>
            <Input
              id="pb-desc"
              value={draft.description}
              maxLength={500}
              onChange={(e) => setDraft({ ...draft, description: e.target.value })}
              placeholder="What the employee uses this for and when"
            />
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label className="text-xs">Steps ({draft.steps.length})</Label>
              <Button type="button" variant="ghost" size="sm" onClick={addStep}>
                <Plus className="mr-1 h-3.5 w-3.5" /> Add step
              </Button>
            </div>
            <div className="max-h-72 space-y-2 overflow-y-auto rounded-lg border border-border/40 bg-muted/20 p-2">
              {draft.steps.map((s, i) => (
                <div
                  key={i}
                  className="flex items-center gap-2 rounded-md border border-border/40 bg-background p-2"
                >
                  <button
                    type="button"
                    title="Move up"
                    onClick={() => moveStep(i, i - 1)}
                    disabled={i === 0}
                    className="text-muted-foreground hover:text-foreground disabled:opacity-30"
                  >
                    <GripVertical className="h-4 w-4" />
                  </button>
                  <span className="font-mono text-[10px] text-muted-foreground">
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <Input
                    value={s.description}
                    maxLength={500}
                    onChange={(e) => setStep(i, e.target.value)}
                    placeholder="What this step does"
                    className="flex-1"
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => removeStep(i)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))}
            </div>
          </div>

          <label className="flex items-center gap-2 rounded-lg border border-border/40 bg-muted/20 p-3">
            <input
              type="checkbox"
              checked={draft.enabled}
              onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
            />
            <div>
              <p className="text-sm">Enabled</p>
              <p className="text-[11px] text-muted-foreground">
                Disabled playbooks stay in the catalog but the loop won't pick
                them up. Toggleable later without losing version history.
              </p>
            </div>
          </label>

          {isEdit && initial?.version !== undefined ? (
            <p className="font-mono text-[10px] text-muted-foreground">
              Editing v{initial.version}. Save fails with a conflict if someone
              else (or an autonomous promotion) wrote in the meantime.
            </p>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={requestClose} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? 'Saving...' : isEdit ? 'Save changes' : 'Create playbook'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
