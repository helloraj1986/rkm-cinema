/**
 * Tiny app-level toast store (zustand — already a dependency). Mirrors the
 * legacy `toast()` surface (ok/err/warn) so add/download/refresh actions can
 * report without prop-drilling. Rendered once by <Toaster/> in the AppShell.
 */
import { create } from "zustand";

export type ToastKind = "ok" | "err" | "warn";

export interface Toast {
  id: number;
  title: string;
  sub?: string;
  kind: ToastKind;
}

interface ToastState {
  toasts: Toast[];
  toast: (title: string, sub?: string, kind?: ToastKind, ms?: number) => void;
  dismiss: (id: number) => void;
}

let nextId = 1;

export const useToasts = create<ToastState>((set, get) => ({
  toasts: [],
  toast: (title, sub = "", kind = "ok", ms = 4200) => {
    const id = nextId++;
    set((s) => ({ toasts: [...s.toasts, { id, title, sub, kind }] }));
    setTimeout(() => get().dismiss(id), ms);
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));

export function toast(title: string, sub?: string, kind?: ToastKind, ms?: number) {
  useToasts.getState().toast(title, sub, kind, ms);
}
