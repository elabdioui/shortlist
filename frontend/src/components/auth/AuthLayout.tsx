// SPDX-License-Identifier: AGPL-3.0-or-later

"use client";

import { CheckCircle2, Moon, ShieldCheck, Sparkles, Sun } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { useAppPreferences } from "@/components/providers/AppProviders";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function AuthLayout({ children }: { children: ReactNode }) {
  const t = useTranslations();
  const { locale, setLocale, theme, toggleTheme } = useAppPreferences();

  return (
    <div className="grid min-h-screen lg:grid-cols-2 bg-[var(--background)] text-[var(--foreground)]">
      {/* Left brand / value panel */}
      <div className="relative hidden flex-col justify-between overflow-hidden bg-zinc-950 p-10 text-zinc-100 lg:flex">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(99,102,241,0.28),transparent_55%),radial-gradient(circle_at_bottom_right,rgba(16,185,129,0.14),transparent_50%)]"
        />
        <div className="relative flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-sm">
            <Sparkles className="h-4 w-4" />
          </span>
          <span className="text-lg font-semibold tracking-tight">{t("common.appName")}</span>
        </div>

        <div className="relative max-w-md space-y-6">
          <h2 className="text-3xl font-semibold tracking-tight leading-tight">
            {t("common.tagline")}
          </h2>
          <ul className="space-y-3 text-sm text-zinc-300">
            <li className="flex items-start gap-2.5">
              <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
              <span>Anonymisation locale avant tout appel IA externe</span>
            </li>
            <li className="flex items-start gap-2.5">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-indigo-400" />
              <span>Chaque verdict appuyé par une citation exacte vérifiée dans le CV</span>
            </li>
            <li className="flex items-start gap-2.5">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-indigo-400" />
              <span>Score déterministe et décision finale toujours humaine</span>
            </li>
          </ul>
        </div>

        <p className="relative text-xs text-zinc-500">AGPL-3.0 · Self-hosted AI CV Screening</p>
      </div>

      {/* Right form panel */}
      <div className="flex flex-col justify-between p-6 md:p-10">
        <div className="flex items-center justify-between lg:justify-end gap-2">
          <div className="flex items-center gap-2 lg:hidden">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--primary)] text-white">
              <Sparkles className="h-4 w-4" />
            </span>
            <span className="font-semibold tracking-tight">{t("common.appName")}</span>
          </div>

          <div className="flex items-center gap-2">
            <div className="inline-flex rounded-lg border border-[var(--border)] bg-[var(--muted)]/60 p-0.5 text-xs">
              <button
                type="button"
                onClick={() => setLocale("fr")}
                className={cn(
                  "rounded-md px-2.5 py-1 font-medium transition-colors cursor-pointer",
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
                  "rounded-md px-2.5 py-1 font-medium transition-colors cursor-pointer",
                  locale === "en"
                    ? "bg-[var(--card)] text-[var(--foreground)] shadow-2xs"
                    : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                )}
              >
                EN
              </button>
            </div>
            <Button variant="outline" size="icon" onClick={toggleTheme} aria-label="Toggle theme">
              {theme === "light" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
            </Button>
          </div>
        </div>

        <div className="mx-auto flex w-full max-w-md flex-col justify-center py-8">{children}</div>

        <div />
      </div>
    </div>
  );
}
