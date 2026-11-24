// SPDX-License-Identifier: AGPL-3.0-or-later

"use client";

import { Command } from "cmdk";
import { FileText, KeyRound, LayoutDashboard, Search, ShieldCheck, Users } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";

export function CommandPalette({ isAdmin }: { isAdmin: boolean }) {
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const t = useTranslations();

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  function navigate(href: string) {
    setOpen(false);
    router.push(href);
  }

  const items = [
    { href: "/", label: t("nav.dashboard"), icon: LayoutDashboard },
    { href: "/settings/providers", label: t("nav.providers"), icon: KeyRound },
    { href: "/settings/privacy", label: t("nav.privacy"), icon: ShieldCheck },
    { href: "/logs", label: t("nav.logs"), icon: FileText },
    ...(isAdmin ? [{ href: "/users", label: t("nav.users"), icon: Users }] : []),
  ];

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="hidden sm:inline-flex h-8 items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--muted)]/50 px-2.5 text-xs text-[var(--muted-foreground)] transition-colors hover:bg-[var(--muted)] hover:text-[var(--foreground)] cursor-pointer"
      >
        <Search className="h-3.5 w-3.5" />
        <span>{t("common.search")}</span>
        <kbd className="ml-1 rounded border border-[var(--border)] bg-[var(--card)] px-1.5 py-0.5 font-mono text-[10px]">
          ⌘K
        </kbd>
      </button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="overflow-hidden p-0 max-w-md">
          <DialogTitle className="sr-only">{t("common.search")}</DialogTitle>
          <Command className="flex h-full w-full flex-col overflow-hidden bg-[var(--card)] text-[var(--foreground)]">
            <div className="flex items-center border-b border-[var(--border)] px-3">
              <Search className="mr-2 h-4 w-4 shrink-0 text-[var(--muted-foreground)]" />
              <Command.Input
                placeholder={t("common.search")}
                className="flex h-11 w-full bg-transparent py-3 text-sm outline-none placeholder:text-[var(--muted-foreground)]"
              />
            </div>
            <Command.List className="max-h-72 overflow-y-auto p-2">
              <Command.Empty className="py-6 text-center text-sm text-[var(--muted-foreground)]">
                —
              </Command.Empty>
              <Command.Group>
                {items.map((item) => {
                  const Icon = item.icon;
                  return (
                    <Command.Item
                      key={item.href}
                      value={item.label}
                      onSelect={() => navigate(item.href)}
                      className="flex cursor-pointer items-center gap-2.5 rounded-lg px-3 py-2 text-sm aria-selected:bg-[var(--accent)] aria-selected:text-[var(--accent-foreground)]"
                    >
                      <Icon className="h-4 w-4 text-[var(--muted-foreground)]" />
                      <span>{item.label}</span>
                    </Command.Item>
                  );
                })}
              </Command.Group>
            </Command.List>
          </Command>
        </DialogContent>
      </Dialog>
    </>
  );
}
