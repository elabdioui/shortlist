// SPDX-License-Identifier: AGPL-3.0-or-later

import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("animate-pulse rounded-lg bg-[var(--muted)]", className)} {...props} />;
}
