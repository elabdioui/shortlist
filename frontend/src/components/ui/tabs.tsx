// SPDX-License-Identifier: AGPL-3.0-or-later

"use client";

import * as TabsPrimitive from "@radix-ui/react-tabs";
import type { ComponentPropsWithoutRef } from "react";
import { cn } from "@/lib/utils";

export const Tabs = TabsPrimitive.Root;

export function TabsList({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof TabsPrimitive.List>) {
  return (
    <TabsPrimitive.List
      className={cn(
        "inline-flex h-10 items-center justify-center rounded-xl border border-[var(--border)] bg-[var(--muted)]/70 p-1 text-[var(--muted-foreground)]",
        className
      )}
      {...props}
    />
  );
}

export function TabsTrigger({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      className={cn(
        "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg px-3.5 py-1.5 text-sm font-medium transition-all cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)] disabled:pointer-events-none disabled:opacity-50 data-[state=active]:bg-[var(--card)] data-[state=active]:text-[var(--foreground)] data-[state=active]:shadow-xs",
        className
      )}
      {...props}
    />
  );
}

export function TabsContent({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof TabsPrimitive.Content>) {
  return (
    <TabsPrimitive.Content
      className={cn(
        "mt-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]",
        className
      )}
      {...props}
    />
  );
}
