import { useEffect, useRef, useState } from 'react';
import { Loader2, Sparkles } from 'lucide-react';
import { toast } from 'sonner';
import { useGenerateRole } from '@empla/react';
import type { GeneratedRoleDraft } from '@empla/react';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';

interface RoleBuilderCardProps {
  /**
   * Called when the LLM returns a draft. The parent uses it to pre-fill
   * its form (role description, name, capabilities) and persists the
   * non-visible fields (goals, capabilities, personality) into draft
   * state for submission via createEmployee.
   */
  onDraft: (draft: GeneratedRoleDraft) => void;
  /** Whether role='custom' is still selected (guards stale responses). */
  isActive?: boolean;
}

/**
 * Card that turns a NL job description into a role draft via the LLM.
 *
 * Renders only when role='custom' is selected. Calls
 * `POST /v1/employees/generate-role` (admin-only at the API). On success
 * the draft populates the parent form; the admin reviews + edits the
 * exact text before clicking Create.
 */
export function RoleBuilderCard({ onDraft, isActive = true }: RoleBuilderCardProps) {
  const [description, setDescription] = useState('');
  const generate = useGenerateRole();
  const requestIdRef = useRef(0);
  // Survives unmount: the `isActive` prop prevents overwrites when the
  // parent still renders this component with isActive=false, but the
  // LLM call can also resolve AFTER the parent unmounts the card
  // entirely (user switched to a built-in role → card gone). Track
  // mount status via a ref so late success/failure callbacks don't
  // fire toasts or onDraft on an orphan.
  const isMountedRef = useRef(true);
  useEffect(
    () => () => {
      isMountedRef.current = false;
    },
    [],
  );

  const handleGenerate = async () => {
    const trimmed = description.trim();
    if (trimmed.length < 10) {
      toast.error('Describe the role in a sentence or two first');
      return;
    }
    const thisRequest = ++requestIdRef.current;
    try {
      const draft = await generate.mutateAsync(trimmed);
      // Guard chain: ignore the response if
      //   (a) a newer request has been fired since,
      //   (b) the parent is still mounted but role switched away, or
      //   (c) the component unmounted (e.g., role switched to sales_ae
      //       mid-call, parent dropped the card from the tree).
      if (thisRequest !== requestIdRef.current || !isActive || !isMountedRef.current) return;
      onDraft(draft);
      toast.success('Generated draft', {
        description: 'Review the role description and capabilities below before creating.',
      });
    } catch (err) {
      if (thisRequest !== requestIdRef.current || !isMountedRef.current) return;
      const msg = err instanceof Error && err.message ? err.message : 'Generation failed';
      toast.error(msg);
    }
  };

  return (
    <Card className="border-primary/30 bg-card/80 backdrop-blur-sm">
      <CardHeader>
        <CardTitle className="font-display flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-primary" />
          Describe the job
        </CardTitle>
        <CardDescription>
          Tell us what this employee should do, and the LLM will draft a name,
          role description, capabilities, and starting goals. You'll review
          the exact text before creating.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="e.g. A marketing manager who runs lifecycle email campaigns, coordinates with sales on outbound, and reports weekly on funnel health."
          className="bg-background/50 min-h-[120px]"
          maxLength={2000}
          disabled={generate.isPending}
        />
        <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
          <span>{description.length}/2000</span>
          <Button
            type="button"
            onClick={handleGenerate}
            disabled={generate.isPending || description.trim().length < 10}
          >
            {generate.isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Generating...
              </>
            ) : (
              <>
                <Sparkles className="mr-2 h-4 w-4" />
                Generate draft
              </>
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
