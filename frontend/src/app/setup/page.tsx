// SPDX-License-Identifier: AGPL-3.0-or-later

"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { AuthLayout } from "@/components/auth/AuthLayout";
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
  const { locale, setLocale } = useAppPreferences();

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
    <AuthLayout>
      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="text-xl">{t("auth.setupTitle")}</CardTitle>
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
                placeholder="••••••••"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="setup-locale">{t("auth.preferredLanguage")}</Label>
              <Select
                id="setup-locale"
                value={preferredLocale}
                onChange={(e) => setPreferredLocale(e.target.value as "fr" | "en")}
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
    </AuthLayout>
  );
}
