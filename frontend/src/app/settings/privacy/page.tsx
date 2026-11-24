// SPDX-License-Identifier: AGPL-3.0-or-later

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldAlert, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState, type FormEvent } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/input";
import { ApiError, privacyApi } from "@/lib/api/client";
import type { PurgeResultResponse } from "@/lib/api/types";

export default function PrivacySettingsPage() {
  const t = useTranslations();
  const queryClient = useQueryClient();

  const privacyQuery = useQuery({
    queryKey: ["privacy"],
    queryFn: privacyApi.get,
  });

  const [anonymizationLevel, setAnonymizationLevel] = useState("strict");
  const [retentionDays, setRetentionDays] = useState("180");
  const [autoPurge, setAutoPurge] = useState(true);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);
  const [purgeResult, setPurgeResult] = useState<PurgeResultResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (privacyQuery.data) {
      setAnonymizationLevel(privacyQuery.data.anonymization_level);
      setRetentionDays(String(privacyQuery.data.retention_days));
      setAutoPurge(privacyQuery.data.auto_purge_enabled);
    }
  }, [privacyQuery.data]);

  const updateMutation = useMutation({
    mutationFn: () =>
      privacyApi.update({
        anonymization_level: anonymizationLevel,
        retention_days: Number(retentionDays) || 180,
        auto_purge_enabled: autoPurge,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["privacy"] });
      setSavedMsg(t("privacy.saved"));
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("common.errorGeneric")),
  });

  const purgeMutation = useMutation({
    mutationFn: privacyApi.purge,
    onSuccess: (res) => {
      setPurgeResult(res);
      queryClient.invalidateQueries({ queryKey: ["privacy"] });
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("common.errorGeneric")),
  });

  function handleSave(e: FormEvent) {
    e.preventDefault();
    setSavedMsg(null);
    updateMutation.mutate();
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{t("privacy.title")}</h1>
          <p className="text-sm text-[var(--muted-foreground)]">{t("privacy.subtitle")}</p>
        </div>

        {error && <Alert variant="danger">{error}</Alert>}
        {savedMsg && <Alert variant="success">{savedMsg}</Alert>}
        {purgeResult && (
          <Alert variant="info">
            {t("privacy.purgeResult", {
              jobs: purgeResult.deleted_jobs,
              candidates: purgeResult.deleted_candidates,
              files: purgeResult.deleted_files,
            })}
          </Alert>
        )}

        <Card>
          <CardHeader>
            <CardTitle>{t("privacy.title")}</CardTitle>
          </CardHeader>
          <CardContent>
            {privacyQuery.isLoading ? (
              <div className="text-sm text-[var(--muted-foreground)]">{t("common.loading")}</div>
            ) : (
              <form onSubmit={handleSave} className="space-y-4">
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label htmlFor="anon-level">{t("privacy.anonymizationLevel")}</Label>
                    <Select
                      id="anon-level"
                      value={anonymizationLevel}
                      onChange={(e) => setAnonymizationLevel(e.target.value)}
                    >
                      <option value="standard">{t("privacy.levelStandard")}</option>
                      <option value="strict">{t("privacy.levelStrict")}</option>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="retention-days">{t("privacy.retentionDays")}</Label>
                    <Input
                      id="retention-days"
                      type="number"
                      min="1"
                      max="3650"
                      value={retentionDays}
                      onChange={(e) => setRetentionDays(e.target.value)}
                    />
                  </div>
                </div>

                <label className="flex items-center gap-2 text-sm cursor-pointer">
                  <input
                    type="checkbox"
                    checked={autoPurge}
                    onChange={(e) => setAutoPurge(e.target.checked)}
                    className="h-4 w-4 rounded border-[var(--border)]"
                  />
                  <span>{t("privacy.autoPurge")}</span>
                </label>

                <div className="text-xs text-[var(--muted-foreground)]">
                  {privacyQuery.data?.last_purge_at
                    ? t("privacy.lastPurge", {
                        date: new Date(privacyQuery.data.last_purge_at).toLocaleString(),
                      })
                    : t("privacy.neverPurged")}
                </div>

                <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--border)] pt-4">
                  <Button
                    variant="destructive"
                    onClick={() => {
                      if (window.confirm(t("privacy.purgeConfirm"))) {
                        purgeMutation.mutate();
                      }
                    }}
                    disabled={purgeMutation.isPending}
                  >
                    <Trash2 className="h-4 w-4" />
                    <span>{t("privacy.purgeNow")}</span>
                  </Button>

                  <Button type="submit" disabled={updateMutation.isPending}>
                    <ShieldAlert className="h-4 w-4" />
                    <span>{updateMutation.isPending ? t("common.saving") : t("common.save")}</span>
                  </Button>
                </div>
              </form>
            )}
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
