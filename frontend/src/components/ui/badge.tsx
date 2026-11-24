// SPDX-License-Identifier: AGPL-3.0-or-later

import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium",
  {
    variants: {
      variant: {
        default: "bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-200",
        success: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300",
        warning: "bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300",
        danger: "bg-rose-100 text-rose-800 dark:bg-rose-950/60 dark:text-rose-300",
        info: "bg-blue-100 text-blue-800 dark:bg-blue-950/60 dark:text-blue-300",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
