// SPDX-License-Identifier: AGPL-3.0-or-later

"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState, type FormEvent } from "react";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { ApiError, authApi } from "@/lib/api/client";

export default function LoginPage() {
  const t = useTranslations();
  const router = useRouter();
  const queryClient = useQueryClient();

  const statusQuery = useQuery({
    queryKey: ["auth", "status"],
    queryFn: authApi.status,
  });

  useEffect(() => {
    if (statusQuery.data?.needs_setup) {
      router.replace("/setup");
    }
  }, [statusQuery.data, router]);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const res = await authApi.login({ email, password });
      queryClient.setQueryData(["auth", "me"], res.user);
      router.replace("/");
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 429) {
          setError(t("auth.rateLimited"));
        } else if (err.status === 401) {
          setError(t("auth.invalidCredentials"));
        } else {
          setError(err.detail);
        }
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
          <CardTitle className="text-xl">{t("auth.loginTitle")}</CardTitle>
          <CardDescription>{t("auth.loginSubtitle")}</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && <Alert variant="danger">{error}</Alert>}

            <div className="space-y-1.5">
              <Label htmlFor="login-email">{t("auth.email")}</Label>
              <Input
                id="login-email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="recruiter@example.com"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="login-password">{t("auth.password")}</Label>
              <Input
                id="login-password"
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
              />
            </div>

            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? t("auth.signingIn") : t("auth.signIn")}
            </Button>
          </form>
        </CardContent>
      </Card>
    </AuthLayout>
  );
}
