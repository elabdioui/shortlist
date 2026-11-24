// SPDX-License-Identifier: AGPL-3.0-or-later

import { cn } from "@/lib/utils";

export function Progress({ value, className }: { value: number; className?: string }) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div
      role="progressbar"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
      className={cn("h-2.5 w-full overflow-hidden rounded-full bg-[var(--muted)]", className)}
    >
      <div
        className="h-full bg-[var(--primary)] transition-all duration-300"
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}
