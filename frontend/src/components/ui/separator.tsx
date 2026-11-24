// SPDX-License-Identifier: AGPL-3.0-or-later

"use client";

import * as SeparatorPrimitive from "@radix-ui/react-separator";
import type { ComponentPropsWithoutRef } from "react";
import { cn } from "@/lib/utils";

export function Separator({
  className,
  orientation = "horizontal",
  decorative = true,
  ...props
}: ComponentPropsWithoutRef<typeof SeparatorPrimitive.Root>) {
  return (
    <SeparatorPrimitive.Root
      decorative={decorative}
      orientation={orientation}
      className={cn(
        "shrink-0 bg-[var(--border)]",
        orientation === "horizontal" ? "h-px w-full" : "h-full w-px",
        className
      )}
      {...props}
    />
  );
}
