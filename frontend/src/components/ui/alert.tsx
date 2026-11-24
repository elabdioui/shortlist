// SPDX-License-Identifier: AGPL-3.0-or-later

import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const alertVariants = cva("relative w-full rounded-xl border px-4 py-3 text-sm", {
  variants: {
    variant: {
      info: "border-indigo-200 bg-indigo-50/70 text-indigo-950 dark:border-indigo-900/60 dark:bg-indigo-950/30 dark:text-indigo-100",
      warning:
        "border-amber-200 bg-amber-50/70 text-amber-950 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-100",
      danger:
        "border-rose-200 bg-rose-50/70 text-rose-950 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-100",
      success:
        "border-emerald-200 bg-emerald-50/70 text-emerald-950 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-100",
    },
  },
  defaultVariants: {
    variant: "info",
  },
});

export interface AlertProps
  extends HTMLAttributes<HTMLDivElement>, VariantProps<typeof alertVariants> {}

export function Alert({ className, variant, ...props }: AlertProps) {
  return <div role="alert" className={cn(alertVariants({ variant }), className)} {...props} />;
}
