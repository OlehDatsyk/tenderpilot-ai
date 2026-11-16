import * as RD from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Button } from "./ui";

export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  wide,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  return (
    <RD.Root open={open} onOpenChange={onOpenChange}>
      <RD.Portal>
        <RD.Overlay className="fixed inset-0 z-40 bg-navy-950/40 backdrop-blur-[1px]" />
        <RD.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-50 flex max-h-[92vh] w-[calc(100vw-1.5rem)] -translate-x-1/2 -translate-y-1/2 flex-col rounded-xl border border-line bg-white shadow-xl focus:outline-none",
            wide ? "max-w-3xl" : "max-w-lg",
          )}
        >
          <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
            <div>
              <RD.Title className="text-base font-semibold text-ink">{title}</RD.Title>
              {description ? (
                <RD.Description className="mt-1 text-sm text-muted">{description}</RD.Description>
              ) : (
                <RD.Description className="sr-only">{title}</RD.Description>
              )}
            </div>
            <RD.Close asChild>
              <Button variant="ghost" size="icon" aria-label="Close">
                <X className="h-4 w-4" />
              </Button>
            </RD.Close>
          </div>
          <div className="overflow-y-auto px-5 py-4">{children}</div>
          {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-line bg-slate-50/60 px-5 py-3">{footer}</div>}
        </RD.Content>
      </RD.Portal>
    </RD.Root>
  );
}

/** Button that asks for confirmation before running a (usually destructive) action. */
export function ConfirmButton({
  trigger,
  title,
  description,
  confirmLabel = "Delete",
  onConfirm,
  destructive = true,
}: {
  trigger: (open: () => void) => ReactNode;
  title: string;
  description: ReactNode;
  confirmLabel?: string;
  onConfirm: () => Promise<unknown> | void;
  destructive?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  return (
    <>
      {trigger(() => setOpen(true))}
      <Dialog
        open={open}
        onOpenChange={(o) => !busy && setOpen(o)}
        title={title}
        description={description}
        footer={
          <>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button
              variant={destructive ? "danger" : "primary"}
              loading={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  await onConfirm();
                  setOpen(false);
                } finally {
                  setBusy(false);
                }
              }}
            >
              {confirmLabel}
            </Button>
          </>
        }
      >
        <p className="text-sm text-muted">This action cannot be undone.</p>
      </Dialog>
    </>
  );
}
