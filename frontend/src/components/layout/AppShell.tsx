// SPDX-License-Identifier: AGPL-3.0-or-later

"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  FileText,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  ShieldCheck,
  Sparkles,
  Sun,
  Users,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState, type ReactNode } from "react";
import { CommandPalette } from "@/components/layout/CommandPalette";
import { useAppPreferences } from "@/components/providers/AppProviders";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
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
  const [collapsed, setCollapsed] = useState(false);

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

  const activeNav = navItems.find((item) =>
    item.href === "/"
      ? pathname === "/" || pathname.startsWith("/jobs/") || pathname.startsWith("/candidates/")
      : pathname.startsWith(item.href)
  );

  if (isLoading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--background)]">
        <div className="flex flex-col items-center gap-3">
          <Skeleton className="h-10 w-10 rounded-xl" />
          <Skeleton className="h-4 w-32" />
        </div>
      </div>
    );
  }

  const initials = user.email.slice(0, 2).toUpperCase();

  return (
    <div className="flex min-h-screen bg-[var(--background)] text-[var(--foreground)]">
      {/* Desktop collapsible sidebar */}
      <aside
        className={cn(
          "hidden shrink-0 flex-col border-r border-[var(--sidebar-border)] bg-[var(--sidebar)] transition-all duration-200 md:flex",
          collapsed ? "w-[68px]" : "w-64"
        )}
      >
        <div className="flex h-14 items-center justify-between border-b border-[var(--sidebar-border)] px-3.5">
          <Link href="/" className="flex items-center gap-2.5 overflow-hidden">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--primary)] text-white shadow-xs">
              <Sparkles className="h-4 w-4" />
            </span>
            {!collapsed && (
              <div className="flex flex-col truncate">
                <span className="text-sm font-semibold tracking-tight">{t("common.appName")}</span>
                <span className="text-[11px] text-[var(--muted-foreground)] truncate">
                  {t("common.tagline")}
                </span>
              </div>
            )}
          </Link>
          <button
            type="button"
            onClick={() => setCollapsed((c) => !c)}
            aria-label="Toggle sidebar"
            className="rounded-md p-1 text-[var(--muted-foreground)] hover:bg-[var(--muted)] hover:text-[var(--foreground)] cursor-pointer"
          >
            {collapsed ? (
              <ChevronsRight className="h-4 w-4" />
            ) : (
              <ChevronsLeft className="h-4 w-4" />
            )}
          </button>
        </div>

        <nav aria-label="Navigation principale" className="flex-1 space-y-1 p-2.5">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active =
              item.href === "/"
                ? pathname === "/" ||
                  pathname.startsWith("/jobs/") ||
                  pathname.startsWith("/candidates/")
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                title={collapsed ? item.label : undefined}
                className={cn(
                  "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors",
                  collapsed && "justify-center px-0",
                  active
                    ? "bg-[var(--primary)]/10 text-[var(--primary)]"
                    : "text-[var(--muted-foreground)] hover:bg-[var(--muted)] hover:text-[var(--foreground)]"
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                {!collapsed && <span className="truncate">{item.label}</span>}
              </Link>
            );
          })}
        </nav>

        <div className="border-t border-[var(--sidebar-border)] p-2.5">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-lg p-2 text-left transition-colors hover:bg-[var(--muted)] cursor-pointer",
                  collapsed && "justify-center"
                )}
              >
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--primary)]/15 text-xs font-semibold text-[var(--primary)]">
                  {initials}
                </span>
                {!collapsed && (
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-medium">{user.email}</p>
                    <p className="text-[11px] text-[var(--muted-foreground)]">
                      {t(`users.roles.${user.role}`)}
                    </p>
                  </div>
                )}
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-56">
              <div className="px-2.5 py-1.5">
                <p className="truncate text-xs font-medium">{user.email}</p>
                <Badge variant="secondary" className="mt-1">
                  {t(`users.roles.${user.role}`)}
                </Badge>
              </div>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={handleLogout} className="text-[var(--destructive)]">
                <LogOut className="h-4 w-4" />
                <span>{t("common.logout")}</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </aside>

      {/* Main area */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-[var(--border)] bg-[var(--card)]/85 px-4 backdrop-blur-md md:px-6">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="icon"
              className="md:hidden"
              onClick={() => setMobileNavOpen((prev) => !prev)}
              aria-label="Menu"
            >
              {mobileNavOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </Button>

            <div className="flex items-center gap-1.5 text-sm">
              <Link
                href="/"
                className="font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)] md:hidden"
              >
                {t("common.appName")}
              </Link>
              {activeNav && (
                <div className="hidden md:flex items-center gap-1.5 text-sm">
                  <span className="text-[var(--muted-foreground)]">{t("common.appName")}</span>
                  <ChevronRight className="h-3.5 w-3.5 text-[var(--muted-foreground)]" />
                  <span className="font-medium text-[var(--foreground)]">{activeNav.label}</span>
                </div>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <CommandPalette isAdmin={user.role === "admin"} />

            <div className="flex items-center rounded-lg border border-[var(--border)] bg-[var(--muted)]/50 p-0.5 text-xs">
              <button
                type="button"
                onClick={() => setLocale("fr")}
                className={cn(
                  "rounded-md px-2 py-1 font-medium transition-colors cursor-pointer",
                  locale === "fr"
                    ? "bg-[var(--card)] text-[var(--foreground)] shadow-2xs"
                    : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                )}
              >
                FR
              </button>
              <button
                type="button"
                onClick={() => setLocale("en")}
                className={cn(
                  "rounded-md px-2 py-1 font-medium transition-colors cursor-pointer",
                  locale === "en"
                    ? "bg-[var(--card)] text-[var(--foreground)] shadow-2xs"
                    : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                )}
              >
                EN
              </button>
            </div>

            <Button
              variant="ghost"
              size="icon"
              onClick={toggleTheme}
              aria-label={theme === "dark" ? t("common.themeLight") : t("common.themeDark")}
              title={theme === "dark" ? t("common.themeLight") : t("common.themeDark")}
            >
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </Button>

            <Button
              variant="ghost"
              size="icon"
              onClick={handleLogout}
              aria-label={t("common.logout")}
              title={t("common.logout")}
              className="md:hidden"
            >
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </header>

        {mobileNavOpen && (
          <div className="border-b border-[var(--border)] bg-[var(--card)] p-3 md:hidden">
            <nav className="flex flex-col gap-1">
              {navItems.map((item) => {
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setMobileNavOpen(false)}
                    className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium hover:bg-[var(--muted)]"
                  >
                    <Icon className="h-4 w-4" />
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </nav>
          </div>
        )}

        <main className="mx-auto w-full max-w-[1400px] flex-1 p-4 md:p-6 lg:p-8">{children}</main>
      </div>
    </div>
  );
}
