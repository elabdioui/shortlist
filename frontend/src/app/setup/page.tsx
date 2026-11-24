// SPDX-License-Identifier: AGPL-3.0-or-later

"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Moon, Sun } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useAppPreferences } from "@/components/providers/AppProviders";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/input";
import { ApiError, authApi } from "@/lib/api/client";

export default function SetupPage() {
  const t = useTranslations();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { locale, setLocale, theme, toggleTheme } = useAppPreferences();

  const completedRef = useRef(false);

  const statusQuery = useQuery({
    queryKey: ["auth", "status"],
    queryFn: authApi.status,
  });

  useEffect(() => {
    if (!completedRef.current && statusQuery.data && !statusQuery.data.needs_setup) {
      router.replace("/login");
    }
  }, [statusQuery.data, router]);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [preferredLocale, setPreferredLocale] = useState<"fr" | "en">(locale);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const res = await authApi.setup({
        email,
        password,
        locale: preferredLocale,
      });
      completedRef.current = true;
      setLocale(preferredLocale);
      queryClient.setQueryData(["auth", "status"], { needs_setup: false });
      queryClient.setQueryData(["auth", "me"], res.user);
      router.replace("/");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError(t("common.errorGeneric"));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[var(--background)] p-4">
      <div className="mb-4 flex w-full max-w-md items-center justify-end gap-2">
        <div className="inline-flex rounded-lg border border-[var(--border)] bg-[var(--card)] p-0.5">
          <button
            type="button"
            onClick={() => setLocale("fr")}
            className={`rounded-md px-2.5 py-1 text-xs font-medium cursor-pointer ${
              locale === "fr" ? "bg-[var(--primary)] text-white" : "text-[var(--muted-foreground)]"
            }`}
          >
            FR
          </button>
          <button
            type="button"
            onClick={() => setLocale("en")}
            className={`rounded-md px-2.5 py-1 text-xs font-medium cursor-pointer ${
              locale === "en" ? "bg-[var(--primary)] text-white" : "text-[var(--muted-foreground)]"
            }`}
          >
            EN
          </button>
        </div>
        <Button variant="outline" size="icon" onClick={toggleTheme} aria-label="Toggle theme">
          {theme === "light" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
        </Button>
      </div>

      <Card className="w-full max-w-md">
        <CardHeader>
          <div className="mb-2 flex items-center gap-2 font-bold text-lg">
            <span className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-[var(--primary)] text-xs font-bold text-white">
              S
            </span>
            <span>{t("common.appName")}</span>
          </div>
          <CardTitle>{t("auth.setupTitle")}</CardTitle>
          <CardDescription>{t("auth.setupSubtitle")}</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && <Alert variant="danger">{error}</Alert>}

            <div className="space-y-1.5">
              <Label htmlFor="setup-email">{t("auth.email")}</Label>
              <Input
                id="setup-email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="admin@example.com"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="setup-password">{t("auth.password")}</Label>
              <Input
                id="setup-password"
                type="password"
                required
                minLength={8}
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="setup-locale">{t("auth.preferredLanguage")}</Label>
              <Select
                id="setup-locale"
                value={preferredLocale}
                onChange={(e) => setPreferredLocale(e.target.value === "en" ? "en" : "fr")}
              >
                <option value="fr">Français</option>
                <option value="en">English</option>
              </Select>
            </div>

            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? t("auth.creatingAccount") : t("auth.createAdmin")}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
