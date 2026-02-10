import { useState } from "react";

import type { Schedule } from "@/api/types.ts";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface ScheduleFormProps {
  /** When set, the form operates in edit mode and pre-fills values. */
  schedule?: Schedule | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called when the user submits the form. */
  onSubmit: (values: { name: string; cron: string; prompt: string }) => void;
  /** Whether the mutation is currently in flight. */
  isSubmitting?: boolean;
  /** Optional error message to display. */
  error?: string | null;
}

// ---------------------------------------------------------------------------
// Inner form (remounted via key to reset state)
// ---------------------------------------------------------------------------

function ScheduleFormFields({
  schedule,
  onSubmit,
  onCancel,
  isSubmitting,
  error,
}: {
  schedule?: Schedule | null;
  onSubmit: (values: { name: string; cron: string; prompt: string }) => void;
  onCancel: () => void;
  isSubmitting: boolean;
  error: string | null;
}) {
  const isEdit = !!schedule;

  const [name, setName] = useState(schedule?.name ?? "");
  const [cron, setCron] = useState(schedule?.cron ?? "");
  const [prompt, setPrompt] = useState(schedule?.prompt ?? "");

  const isValid = name.trim() !== "" && cron.trim() !== "" && prompt.trim() !== "";

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!isValid || isSubmitting) return;
    onSubmit({
      name: name.trim(),
      cron: cron.trim(),
      prompt: prompt.trim(),
    });
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-2">
        <label htmlFor="schedule-name" className="text-sm font-medium">
          Name
        </label>
        <Input
          id="schedule-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. daily-digest"
          disabled={isSubmitting}
        />
      </div>

      <div className="space-y-2">
        <label htmlFor="schedule-cron" className="text-sm font-medium">
          Cron Expression
        </label>
        <Input
          id="schedule-cron"
          value={cron}
          onChange={(e) => setCron(e.target.value)}
          placeholder="e.g. 0 9 * * *"
          disabled={isSubmitting}
        />
        <p className="text-xs text-muted-foreground">
          Standard 5-field cron: minute hour day-of-month month day-of-week
        </p>
      </div>

      <div className="space-y-2">
        <label htmlFor="schedule-prompt" className="text-sm font-medium">
          Prompt
        </label>
        <Textarea
          id="schedule-prompt"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="The prompt that will be sent to the butler when this schedule fires..."
          className="min-h-24"
          disabled={isSubmitting}
        />
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <DialogFooter>
        <Button
          type="button"
          variant="outline"
          onClick={onCancel}
          disabled={isSubmitting}
        >
          Cancel
        </Button>
        <Button type="submit" disabled={!isValid || isSubmitting}>
          {isSubmitting
            ? isEdit
              ? "Updating..."
              : "Creating..."
            : isEdit
              ? "Update Schedule"
              : "Create Schedule"}
        </Button>
      </DialogFooter>
    </form>
  );
}

// ---------------------------------------------------------------------------
// ScheduleForm
// ---------------------------------------------------------------------------

export function ScheduleForm({
  schedule,
  open,
  onOpenChange,
  onSubmit,
  isSubmitting = false,
  error = null,
}: ScheduleFormProps) {
  const isEdit = !!schedule;

  // Use a key derived from the schedule id (or "new") to remount the inner
  // form component whenever the dialog opens with different data, which
  // resets the controlled inputs without useEffect + setState.
  const formKey = open ? (schedule?.id ?? "new") : "closed";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit Schedule" : "Create Schedule"}</DialogTitle>
          <DialogDescription>
            {isEdit
              ? "Update the schedule details below."
              : "Define a new scheduled task for this butler."}
          </DialogDescription>
        </DialogHeader>

        <ScheduleFormFields
          key={formKey}
          schedule={schedule}
          onSubmit={onSubmit}
          onCancel={() => onOpenChange(false)}
          isSubmitting={isSubmitting}
          error={error}
        />
      </DialogContent>
    </Dialog>
  );
}

export default ScheduleForm;
