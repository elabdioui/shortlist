// SPDX-License-Identifier: AGPL-3.0-or-later

"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { Card } from "@/components/ui/card";
import { logsApi } from "@/lib/api/client";
import { cn, formatCostUsd } from "@/lib/utils";

export default function LogsPage() {
  const t = useTranslations();
  const [tab, setTab] = useState<"usage" | "audit">("usage");

  const usageQuery = useQuery({
    queryKey: ["logs", "usage"],
    queryFn: logsApi.listUsage,
    enabled: tab === "usage",
  });

  const auditQuery = useQuery({
    queryKey: ["logs", "audit"],
    queryFn: () => logsApi.listAudit(100, 0),
    enabled: tab === "audit",
  });

  return (
    <AppShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{t("logs.title")}</h1>
          <p className="text-sm text-[var(--muted-foreground)]">{t("logs.subtitle")}</p>
        </div>

        <div className="flex gap-2 border-b border-[var(--border)] pb-2">
          <button
            type="button"
            onClick={() => setTab("usage")}
            className={cn(
              "rounded-lg px-4 py-2 text-sm font-medium cursor-pointer",
              tab === "usage"
                ? "bg-[var(--primary)] text-white"
                : "text-[var(--muted-foreground)] hover:bg-[var(--muted)]"
            )}
          >
            {t("logs.usageTab")}
          </button>
          <button
            type="button"
            onClick={() => setTab("audit")}
            className={cn(
              "rounded-lg px-4 py-2 text-sm font-medium cursor-pointer",
              tab === "audit"
                ? "bg-[var(--primary)] text-white"
                : "text-[var(--muted-foreground)] hover:bg-[var(--muted)]"
            )}
          >
            {t("logs.auditTab")}
          </button>
        </div>

        <Card>
          <div className="overflow-x-auto">
            {tab === "usage" ? (
              usageQuery.isLoading ? (
                <div className="p-8 text-center text-sm text-[var(--muted-foreground)]">
                  {t("common.loading")}
                </div>
              ) : (usageQuery.data ?? []).length === 0 ? (
                <div className="p-8 text-center text-sm text-[var(--muted-foreground)]">
                  {t("common.noData")}
                </div>
              ) : (
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-[var(--border)] bg-[var(--muted)]/50 text-xs uppercase text-[var(--muted-foreground)]">
                    <tr>
                      <th className="px-4 py-3">{t("logs.date")}</th>
                      <th className="px-4 py-3">{t("logs.keyId")}</th>
                      <th className="px-4 py-3">{t("logs.requests")}</th>
                      <th className="px-4 py-3">{t("logs.inputTokens")}</th>
                      <th className="px-4 py-3">{t("logs.outputTokens")}</th>
                      <th className="px-4 py-3">{t("logs.cost")}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border)]">
                    {(usageQuery.data ?? []).map((row) => (
                      <tr key={row.id}>
                        <td className="px-4 py-3">{row.usage_date}</td>
                        <td className="px-4 py-3 font-mono text-xs">{row.api_key_id}</td>
                        <td className="px-4 py-3 tabular-nums">{row.requests}</td>
                        <td className="px-4 py-3 tabular-nums">{row.input_tokens}</td>
                        <td className="px-4 py-3 tabular-nums">{row.output_tokens}</td>
                        <td className="px-4 py-3 font-medium tabular-nums">
                          {formatCostUsd(row.cost_usd)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )
            ) : auditQuery.isLoading ? (
              <div className="p-8 text-center text-sm text-[var(--muted-foreground)]">
                {t("common.loading")}
              </div>
            ) : (auditQuery.data?.items ?? []).length === 0 ? (
              <div className="p-8 text-center text-sm text-[var(--muted-foreground)]">
                {t("common.noData")}
              </div>
            ) : (
              <table className="w-full text-left text-sm">
                <thead className="border-b border-[var(--border)] bg-[var(--muted)]/50 text-xs uppercase text-[var(--muted-foreground)]">
                  <tr>
                    <th className="px-4 py-3">{t("logs.date")}</th>
                    <th className="px-4 py-3">{t("logs.action")}</th>
                    <th className="px-4 py-3">{t("logs.resource")}</th>
                    <th className="px-4 py-3">{t("logs.actor")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border)]">
                  {(auditQuery.data?.items ?? []).map((row) => (
                    <tr key={row.id}>
                      <td className="px-4 py-3 text-xs">
                        {new Date(row.created_at).toLocaleString()}
                      </td>
                      <td className="px-4 py-3 font-medium">{row.action}</td>
                      <td className="px-4 py-3 text-xs text-[var(--muted-foreground)]">
                        {row.resource_type} {row.resource_id ?? ""}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs">{row.user_id ?? "system"}</td>
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
