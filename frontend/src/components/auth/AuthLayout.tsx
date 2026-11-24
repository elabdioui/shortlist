// SPDX-License-Identifier: AGPL-3.0-or-later

"use client";

import { Moon, Sun } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { ShortlistMark } from "@/components/layout/ShortlistMark";
import { useAppPreferences } from "@/components/providers/AppProviders";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function AuthLayout({ children }: { children: ReactNode }) {
  const t = useTranslations();
  const { locale, setLocale, theme, toggleTheme } = useAppPreferences();

  return (
    <div className="grid min-h-screen lg:grid-cols-2 bg-[var(--background)] text-[var(--foreground)]">
      {/* Left product preview panel — quiet graphite, no radial blobs */}
      <div className="hidden flex-col justify-between border-r border-[var(--border)] bg-[#0f0f10] p-10 text-[#ededed] lg:flex">
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#ededed] text-[#0f0f10]">
            <ShortlistMark className="h-4 w-4" />
          </span>
          <span className="text-base font-medium tracking-tight">{t("common.appName")}</span>
        </div>

        <div className="mx-auto w-full max-w-md space-y-6">
          <div className="space-y-2">
            <h2 className="text-2xl font-medium tracking-tight leading-snug text-[#ededed]">
              {t("common.tagline")}
            </h2>
            <p className="text-sm text-[#8c8c94]">
              Anonymisation locale, citations vérifiées dans le CV et score déterministe.
            </p>
          </div>

          {/* Product dossier preview */}
          <div className="rounded-xl border border-white/10 bg-[#19191b] p-5 space-y-4">
            <div className="flex items-center justify-between border-b border-white/8 pb-3">
              <div>
                <p className="text-sm font-medium text-[#ededed]">Acheteur Supply Chain</p>
                <p className="text-xs text-[#8c8c94] font-mono tabular-nums">
                  Grille v2 · Seuils 70/45
                </p>
              </div>
              <span className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 font-mono text-xs font-medium tabular-nums text-emerald-400">
                86 / 100
              </span>
            </div>

            <div className="space-y-2.5 text-xs">
              <div className="flex items-center justify-between text-[#a1a1a6]">
                <span>Négociation fournisseurs (5 ans)</span>
                <span className="font-mono text-emerald-400">Oui · Vérifié</span>
              </div>
              <blockquote className="rounded-lg border border-white/8 bg-[#141415] p-3 text-[#d4d4d8] leading-relaxed">
                «{" "}
                <mark className="rounded bg-amber-300/20 px-1 py-0.5 text-amber-200">
                  pilotage d&apos;appels d&apos;offres internationaux et négociation de contrats
                  cadres sur 6 ans
                </mark>{" "}
                »
              </blockquote>
            </div>
          </div>
        </div>

        <p className="font-mono text-xs text-[#66666e]">AGPL-3.0 · Self-hosted</p>
      </div>

      {/* Right form panel */}
      <div className="flex flex-col justify-between p-6 md:p-10">
        <div className="flex items-center justify-between lg:justify-end gap-2">
          <div className="flex items-center gap-2 lg:hidden">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--primary)] text-[var(--primary-foreground)]">
              <ShortlistMark className="h-4 w-4" />
            </span>
            <span className="font-medium tracking-tight">{t("common.appName")}</span>
          </div>

          <div className="flex items-center gap-2">
            <div className="inline-flex rounded-lg border border-[var(--border)] bg-[var(--muted)] p-0.5 text-xs">
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
              {theme === "light" ? (
                <Moon className="h-4 w-4" strokeWidth={1.5} />
              ) : (
                <Sun className="h-4 w-4" strokeWidth={1.5} />
              )}
            </Button>
          </div>
        </div>

        <div className="mx-auto flex w-full max-w-md flex-col justify-center py-8">{children}</div>

        <div />
      </div>
    </div>
  );
}
