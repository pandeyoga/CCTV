import type { ReactNode } from "react";
import { X } from "lucide-react";
import * as DialogPrimitive from "@radix-ui/react-dialog";

interface Props {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: ReactNode;
  testId: string;
}

/** Light-theme modal on the dashboard tokens (card radius, ink header). */
export const Modal = ({ open, onClose, title, description, children, testId }: Props) => (
  <DialogPrimitive.Root open={open} onOpenChange={(o) => !o && onClose()}>
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-ink/40 backdrop-blur-[2px] fade-in" />
      <DialogPrimitive.Content data-testid={testId}
        className="card modal-in fixed left-1/2 top-1/2 z-50 max-h-[calc(100vh-2rem)] w-[calc(100vw-2rem)] max-w-lg overflow-y-auto p-0 focus:outline-none">
        <div className="flex items-start justify-between gap-4 border-b border-line px-6 py-4">
          <div>
            <DialogPrimitive.Title className="text-base font-semibold text-txt">{title}</DialogPrimitive.Title>
            {description && <DialogPrimitive.Description className="mt-0.5 text-xs text-txt-2">{description}</DialogPrimitive.Description>}
          </div>
          <DialogPrimitive.Close aria-label="Tutup" data-testid={`${testId}-close`} className="ctl ctl-ghost h-8 w-8 min-w-8 px-0 text-txt-2">
            <X className="h-4 w-4" />
          </DialogPrimitive.Close>
        </div>
        <div className="px-6 py-5">{children}</div>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  </DialogPrimitive.Root>
);

export const inputCls = "login-input h-11 w-full rounded-ctl border border-line bg-surface px-3 text-sm text-txt placeholder:text-txt-3";

export const Field = ({ label, hint, children, testId }: { label: string; hint?: string; children: ReactNode; testId?: string }) => (
  <label className="block" data-testid={testId}>
    <span className="mb-1.5 block text-xs font-medium text-txt-2">{label}</span>
    {children}
    {hint && <span className="mt-1 block text-[11px] text-txt-3">{hint}</span>}
  </label>
);

export const FormActions = ({ onCancel, submitLabel, pending, testId }: { onCancel: () => void; submitLabel: string; pending: boolean; testId: string }) => (
  <div className="mt-6 flex justify-end gap-2">
    <button type="button" onClick={onCancel} className="ctl h-10" data-testid={`${testId}-cancel`}>Batal</button>
    <button type="submit" disabled={pending} className="ctl ctl-ink h-10" data-testid={`${testId}-submit`}>{pending ? "Menyimpan…" : submitLabel}</button>
  </div>
);
