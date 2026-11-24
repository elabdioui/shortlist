// SPDX-License-Identifier: AGPL-3.0-or-later

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/input";
import { ApiError, usersApi } from "@/lib/api/client";
import type { UserRole } from "@/lib/api/types";

export default function UsersPage() {
  const t = useTranslations();
  const queryClient = useQueryClient();

  const usersQuery = useQuery({
    queryKey: ["users"],
    queryFn: usersApi.list,
  });

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("recruiter");
  const [locale, setLocale] = useState<"fr" | "en">("fr");
  const [error, setError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: usersApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      setEmail("");
      setPassword("");
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("common.errorGeneric")),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, role: nextRole }: { id: string; role: UserRole }) =>
      usersApi.update(id, { role: nextRole }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: usersApi.delete,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });

  function handleCreate(e: FormEvent) {
    e.preventDefault();
    createMutation.mutate({ email, password, role, locale });
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{t("users.title")}</h1>
          <p className="text-sm text-[var(--muted-foreground)]">{t("users.subtitle")}</p>
        </div>

        {error && <Alert variant="danger">{error}</Alert>}

        <Card>
          <CardHeader>
            <CardTitle>{t("users.addUser")}</CardTitle>
          </CardHeader>
          <CardContent>
            <form
              onSubmit={handleCreate}
              className="grid grid-cols-1 gap-3 sm:grid-cols-5 sm:items-end"
            >
              <div className="space-y-1">
                <Label htmlFor="user-email">{t("users.email")}</Label>
                <Input
                  id="user-email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="user-password">{t("users.password")}</Label>
                <Input
                  id="user-password"
                  type="password"
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="user-role">{t("users.role")}</Label>
                <Select
                  id="user-role"
                  value={role}
                  onChange={(e) => setRole(e.target.value as UserRole)}
                >
                  <option value="recruiter">{t("users.roles.recruiter")}</option>
                  <option value="reader">{t("users.roles.reader")}</option>
                  <option value="admin">{t("users.roles.admin")}</option>
                </Select>
              </div>
              <div className="space-y-1">
                <Label htmlFor="user-locale">{t("users.locale")}</Label>
                <Select
                  id="user-locale"
                  value={locale}
                  onChange={(e) => setLocale(e.target.value === "en" ? "en" : "fr")}
                >
                  <option value="fr">Français</option>
                  <option value="en">English</option>
                </Select>
              </div>
              <Button type="submit" disabled={createMutation.isPending}>
                <Plus className="h-4 w-4" />
                <span>{t("users.addUser")}</span>
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card>
          <div className="overflow-x-auto">
            {usersQuery.isLoading ? (
              <div className="p-8 text-center text-sm text-[var(--muted-foreground)]">
                {t("common.loading")}
              </div>
            ) : usersQuery.isError ? (
              <Alert variant="danger" className="m-4">
                {t("common.errorGeneric")}
              </Alert>
            ) : (
              <table className="w-full text-left text-sm">
                <thead className="border-b border-[var(--border)] bg-[var(--muted)]/50 text-xs uppercase text-[var(--muted-foreground)]">
                  <tr>
                    <th className="px-4 py-3">{t("users.email")}</th>
                    <th className="px-4 py-3">{t("users.role")}</th>
                    <th className="px-4 py-3">{t("users.locale")}</th>
                    <th className="px-4 py-3">{t("common.actions")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border)]">
                  {(usersQuery.data ?? []).map((u) => (
                    <tr key={u.id}>
                      <td className="px-4 py-3 font-medium">{u.email}</td>
                      <td className="px-4 py-3">
                        <Select
                          className="h-8 w-40 text-xs"
                          value={u.role}
                          onChange={(e) =>
                            updateMutation.mutate({ id: u.id, role: e.target.value as UserRole })
                          }
                        >
                          <option value="admin">{t("users.roles.admin")}</option>
                          <option value="recruiter">{t("users.roles.recruiter")}</option>
                          <option value="reader">{t("users.roles.reader")}</option>
                        </Select>
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant="default">{u.locale.toUpperCase()}</Badge>
                      </td>
                      <td className="px-4 py-3">
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={t("common.delete")}
                          onClick={() => {
                            if (window.confirm(t("users.deleteConfirm"))) {
                              deleteMutation.mutate(u.id);
                            }
                          }}
                        >
                          <Trash2 className="h-4 w-4 text-rose-500" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </Card>
      </div>
    </AppShell>
  );
}
