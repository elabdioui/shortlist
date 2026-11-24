// SPDX-License-Identifier: AGPL-3.0-or-later

"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  FileText,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  ShieldCheck,
  Sun,
  Users,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState, type ReactNode } from "react";
import { useAppPreferences } from "@/components/providers/AppProviders";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ApiError, authApi } from "@/lib/api/client";
import type { UserResponse } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export function useAuthUser() {
  const router = useRouter();
  const statusQuery = useQuery({
    queryKey: ["auth", "status"],
    queryFn: authApi.status,
  });

  const meQuery = useQuery({
    queryKey: ["auth", "me"],
    queryFn: authApi.me,
    enabled: statusQuery.data?.needs_setup === false,
  });

  useEffect(() => {
    if (statusQuery.data?.needs_setup) {
      router.replace("/setup");
    } else if (meQuery.error instanceof ApiError && meQuery.error.status === 401) {
      router.replace("/login");
    }
  }, [statusQuery.data, meQuery.error, router]);

  return {
    user: meQuery.data as UserResponse | undefined,
    isLoading:
      statusQuery.isLoading || (statusQuery.data?.needs_setup === false && meQuery.isLoading),
  };
}

export function AppShell({ children }: { children: ReactNode }) {
  const t = useTranslations();
  const pathname = usePathname();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { locale, setLocale, theme, toggleTheme } = useAppPreferences();
  const { user, isLoading } = useAuthUser();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  async function handleLogout() {
    await authApi.logout().catch(() => {});
    queryClient.clear();
    router.replace("/login");
  }

  const navItems = [
    { href: "/", label: t("nav.dashboard"), icon: LayoutDashboard },
    { href: "/settings/providers", label: t("nav.providers"), icon: KeyRound },
    { href: "/settings/privacy", label: t("nav.privacy"), icon: ShieldCheck },
    { href: "/logs", label: t("nav.logs"), icon: FileText },
    ...(user?.role === "admin" ? [{ href: "/users", label: t("nav.users"), icon: Users }] : []),
  ];

  if (isLoading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--background)]">
        <div className="text-sm text-[var(--muted-foreground)]">{t("common.loading")}</div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-[var(--background)] text-[var(--foreground)]">
      {/* Desktop Sidebar */}
      <aside className="hidden w-60 shrink-0 flex-col border-r border-[var(--border)] bg-[var(--card)] md:flex">
        <div className="border-b border-[var(--border)] px-5 py-4">
          <Link href="/" className="flex items-center gap-2 font-bold tracking-tight text-lg">
            <span className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-[var(--primary)] text-xs font-bold text-white">
              S
            </span>
            <span>{t("common.appName")}</span>
          </Link>
          <p className="mt-1 text-xs text-[var(--muted-foreground)]">{t("common.tagline")}</p>
        </div>

        <nav className="flex-1 space-y-1 p-3" aria-label="Main navigation">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active =
              item.href === "/"
                ? pathname === "/" ||
                  pathname.startsWith("/jobs") ||
                  pathname.startsWith("/candidates")
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  active
                    ? "bg-[var(--primary)] text-[var(--primary-foreground)]"
                    : "text-[var(--muted-foreground)] hover:bg-[var(--muted)] hover:text-[var(--foreground)]"
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="border-t border-[var(--border)] p-4 text-xs text-[var(--muted-foreground)]">
          <div className="truncate font-medium text-[var(--foreground)]">{user.email}</div>
          <div className="mt-1 flex items-center justify-between">
            <Badge variant="info">{t(`users.roles.${user.role}`)}</Badge>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleLogout}
              aria-label={t("common.logout")}
              title={t("common.logout")}
            >
              <LogOut className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-[var(--border)] bg-[var(--card)]/95 px-4 backdrop-blur md:px-6">
          <div className="flex items-center gap-3 md:hidden">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setMobileNavOpen((prev) => !prev)}
              aria-label="Toggle menu"
            >
              {mobileNavOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </Button>
            <Link href="/" className="font-bold text-base">
              {t("common.appName")}
            </Link>
          </div>

          <div className="hidden md:block" />

          <div className="flex items-center gap-2">
            <div className="inline-flex rounded-lg border border-[var(--border)] p-0.5">
              <button
                type="button"
                onClick={() => setLocale("fr")}
                className={cn(
                  "rounded-md px-2.5 py-1 text-xs font-medium cursor-pointer",
                  locale === "fr"
                    ? "bg-[var(--primary)] text-[var(--primary-foreground)]"
                    : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                )}
              >
                FR
              </button>
              <button
                type="button"
                onClick={() => setLocale("en")}
                className={cn(
                  "rounded-md px-2.5 py-1 text-xs font-medium cursor-pointer",
                  locale === "en"
                    ? "bg-[var(--primary)] text-[var(--primary-foreground)]"
                    : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                )}
              >
                EN
              </button>
            </div>

            <Button
              variant="outline"
              size="icon"
              onClick={toggleTheme}
              aria-label={theme === "light" ? t("common.themeDark") : t("common.themeLight")}
              title={theme === "light" ? t("common.themeDark") : t("common.themeLight")}
            >
              {theme === "light" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
            </Button>
          </div>
        </header>

        {mobileNavOpen && (
          <nav className="border-b border-[var(--border)] bg-[var(--card)] p-3 md:hidden">
            <div className="space-y-1">
              {navItems.map((item) => {
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setMobileNavOpen(false)}
                    className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium text-[var(--foreground)] hover:bg-[var(--muted)]"
                  >
                    <Icon className="h-4 w-4" />
                    <span>{item.label}</span>
                  </Link>
                );
              })}
              <button
                type="button"
                onClick={handleLogout}
                className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium text-rose-600 hover:bg-[var(--muted)] cursor-pointer"
              >
                <LogOut className="h-4 w-4" />
                <span>{t("common.logout")}</span>
              </button>
            </div>
          </nav>
        )}

        <main className="mx-auto w-full max-w-7xl flex-1 p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
