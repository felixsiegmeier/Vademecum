import { useEffect } from "react";

export type ToastKind = "info" | "success" | "warning" | "error";

interface ToastMessage {
  id: number;
  kind: ToastKind;
  text: string;
}

interface Props {
  toast: ToastMessage | null;
  onDismiss: () => void;
}

const COLORS: Record<ToastKind, string> = {
  info: "bg-gray-800 text-white",
  success: "bg-green-600 text-white",
  warning: "bg-amber-500 text-white",
  error: "bg-red-600 text-white",
};

export default function Toast({ toast, onDismiss }: Props) {
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(onDismiss, 4000);
    return () => clearTimeout(t);
  }, [toast, onDismiss]);

  if (!toast) return null;

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 pointer-events-none">
      <div
        className={`pointer-events-auto rounded-xl px-4 py-2 text-sm shadow-lg ${COLORS[toast.kind]}`}
        onClick={onDismiss}
        role="status"
      >
        {toast.text}
      </div>
    </div>
  );
}

export type { ToastMessage };
