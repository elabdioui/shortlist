// SPDX-License-Identifier: AGPL-3.0-or-later

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, KeyRound, Pause, Play, Plus, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Select, Textarea } from "@/components/ui/input";
import { ApiError, providersApi } from "@/lib/api/client";
import type {
  APIKeyTestResult,
  KeyStatus,
  KeyTier,
  ModelProfileEntry,
  ProviderType,
  RoutingStrategy,
} from "@/lib/api/types";
import { formatCostUsd } from "@/lib/utils";

function keyStatusVariant(status: KeyStatus): "success" | "warning" | "danger" | "default" {
  switch (status) {
    case "active":
      return "success";
    case "cooldown":
      return "warning";
    case "invalid":
      return "danger";
    default:
      return "default";
  }
}

export default function ProvidersSettingsPage() {
  const t = useTranslations();
  const queryClient = useQueryClient();

  const providersQuery = useQuery({
    queryKey: ["providers"],
    queryFn: providersApi.listProviders,
  });

  const keysQuery = useQuery({
    queryKey: ["keys"],
    queryFn: providersApi.listKeys,
  });

  const profilesQuery = useQuery({
    queryKey: ["profiles"],
    queryFn: providersApi.listProfiles,
  });

  // Add Provider state
  const [providerType, setProviderType] = useState<ProviderType>("gemini");
  const [baseUrl, setBaseUrl] = useState("");

  // Add Key state
  const [keyProviderId, setKeyProviderId] = useState("");
  const [keyLabel, setKeyLabel] = useState("");
  const [keySecret, setKeySecret] = useState("");
  const [keyTier, setKeyTier] = useState<KeyTier>("paid");
  const [keyPriority, setKeyPriority] = useState("1");
  const [keyAllowedModels, setKeyAllowedModels] = useState("");
  const [keyRpm, setKeyRpm] = useState("");
  const [keyTpm, setKeyTpm] = useState("");
  const [keyRpd, setKeyRpd] = useState("");
  const [keyConcurrency, setKeyConcurrency] = useState("4");
  const [keyBudget, setKeyBudget] = useState("");

  // Add Profile state
  const [profileName, setProfileName] = useState("");
  const [profileStrategy, setProfileStrategy] = useState<RoutingStrategy>("priority");
  const [profileModelsText, setProfileModelsText] = useState("gemini:gemini-2.0-flash");

  const [testResults, setTestResults] = useState<Record<string, APIKeyTestResult>>({});
  const [error, setError] = useState<string | null>(null);

  const createProviderMutation = useMutation({
    mutationFn: providersApi.createProvider,
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ["providers"] });
      setKeyProviderId(created.id);
      setBaseUrl("");
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("common.errorGeneric")),
  });

  const createKeyMutation = useMutation({
    mutationFn: providersApi.createKey,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["keys"] });
      setKeyLabel("");
      setKeySecret("");
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("common.errorGeneric")),
  });

  const updateKeyMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: KeyStatus }) =>
      providersApi.updateKey(id, { status }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["keys"] }),
  });

  const deleteKeyMutation = useMutation({
    mutationFn: providersApi.deleteKey,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["keys"] }),
  });

  const testKeyMutation = useMutation({
    mutationFn: (keyId: string) => providersApi.testKey(keyId),
    onSuccess: (res, keyId) => {
      setTestResults((prev) => ({ ...prev, [keyId]: res }));
      queryClient.invalidateQueries({ queryKey: ["keys"] });
    },
  });

  const createProfileMutation = useMutation({
    mutationFn: providersApi.createProfile,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["profiles"] });
      setProfileName("");
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("common.errorGeneric")),
  });

  const providers = providersQuery.data ?? [];
  const keys = keysQuery.data ?? [];
  const profiles = profilesQuery.data ?? [];

  const invalidKeysCount = keys.filter((k) => k.status === "invalid").length;
  const effectiveProviderId = keyProviderId || providers[0]?.id || "";

  function handleAddProvider(e: FormEvent) {
    e.preventDefault();
    createProviderMutation.mutate({
      type: providerType,
      base_url: baseUrl.trim() || null,
      active: true,
    });
  }

  function handleAddKey(e: FormEvent) {
    e.preventDefault();
    if (!effectiveProviderId) return;
    createKeyMutation.mutate({
      provider_id: effectiveProviderId,
      label: keyLabel,
      secret: keySecret,
      tier: keyTier,
      priority: Number(keyPriority) || 1,
      allowed_models: keyAllowedModels
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      rpm_limit: keyRpm ? Number(keyRpm) : null,
      tpm_limit: keyTpm ? Number(keyTpm) : null,
      rpd_limit: keyRpd ? Number(keyRpd) : null,
      concurrency: Number(keyConcurrency) || 4,
      monthly_budget_usd: keyBudget ? Number(keyBudget) : null,
    });
  }

  function handleAddProfile(e: FormEvent) {
    e.preventDefault();
    const models: ModelProfileEntry[] = profileModelsText
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const [prov, ...rest] = line.split(":");
        return {
          provider: (prov?.trim() || "gemini") as ProviderType,
          model: rest.join(":").trim() || "gemini-2.0-flash",
        };
      });
    createProfileMutation.mutate({
      name: profileName,
      strategy: profileStrategy,
      models,
    });
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{t("providers.title")}</h1>
          <p className="text-sm text-[var(--muted-foreground)]">{t("providers.subtitle")}</p>
        </div>

        {error && <Alert variant="danger">{error}</Alert>}

        {invalidKeysCount > 0 && (
          <Alert variant="danger" className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span>{t("providers.invalidKeyAlert", { count: invalidKeysCount })}</span>
          </Alert>
        )}

        {/* Providers */}
        <Card>
          <CardHeader>
            <CardTitle>{t("providers.providersList")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap gap-2">
              {providers.map((p) => (
                <Badge key={p.id} variant={p.active ? "info" : "default"}>
                  {p.type}
                  {p.base_url ? ` (${p.base_url})` : ""}
                </Badge>
              ))}
            </div>

            <form
              onSubmit={handleAddProvider}
              className="grid grid-cols-1 gap-3 border-t border-[var(--border)] pt-4 sm:grid-cols-3 sm:items-end"
            >
              <div className="space-y-1">
                <Label htmlFor="provider-type">{t("providers.providerType")}</Label>
                <Select
                  id="provider-type"
                  value={providerType}
                  onChange={(e) => setProviderType(e.target.value as ProviderType)}
                >
                  <option value="ollama">Ollama (Local)</option>
                  <option value="gemini">Google Gemini</option>
                  <option value="openai">OpenAI</option>
                  <option value="anthropic">Anthropic</option>
                  <option value="mistral">Mistral</option>
                  <option value="groq">Groq</option>
                  <option value="openrouter">OpenRouter</option>
                  <option value="openai_compatible">OpenAI-compatible</option>
                </Select>
              </div>
              <div className="space-y-1">
                <Label htmlFor="provider-url">{t("providers.baseUrl")}</Label>
                <Input
                  id="provider-url"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  placeholder="http://localhost:11434"
                />
              </div>
              <Button type="submit" disabled={createProviderMutation.isPending}>
                <Plus className="h-4 w-4" />
                <span>{t("providers.addProvider")}</span>
              </Button>
            </form>
          </CardContent>
        </Card>

        {/* AI Keys Pool */}
        <Card>
          <CardHeader>
            <CardTitle>{t("providers.keysList")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            {keys.length > 0 && (
              <div className="space-y-3">
                {keys.map((k) => {
                  const testRes = testResults[k.id];
                  const prov = providers.find((p) => p.id === k.provider_id);
                  return (
                    <div
                      key={k.id}
                      className="flex flex-col justify-between gap-3 rounded-lg border border-[var(--border)] p-4 sm:flex-row sm:items-center"
                    >
                      <div className="space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <KeyRound className="h-4 w-4 text-[var(--muted-foreground)]" />
                          <span className="font-semibold">{k.label}</span>
                          <Badge variant="default">{prov?.type ?? k.provider_id}</Badge>
                          <Badge variant={keyStatusVariant(k.status)}>
                            {t(`providers.keyStatus.${k.status}`)}
                          </Badge>
                          <Badge variant={k.tier === "free" ? "warning" : "info"}>
                            {k.tier === "free" ? t("providers.tierFree") : t("providers.tierPaid")}
                          </Badge>
                        </div>
                        <div className="text-xs text-[var(--muted-foreground)]">
                          {k.masked_secret} · P{k.priority} · Concurrency {k.concurrency}
                          {k.monthly_budget_usd != null &&
                            ` · Budget ${formatCostUsd(k.monthly_budget_usd)}`}
                        </div>
                        {testRes && (
                          <div
                            className={`flex items-center gap-1 text-xs ${
                              testRes.ok ? "text-emerald-600" : "text-rose-600"
                            }`}
                          >
                            {testRes.ok ? (
                              <>
                                <CheckCircle2 className="h-3.5 w-3.5" />
                                <span>
                                  {t("providers.testOk", {
                                    model: testRes.model ?? "ok",
                                    latency: Math.round(testRes.latency_ms ?? 0),
                                  })}
                                </span>
                              </>
                            ) : (
                              <span>
                                {t("providers.testFail", { error: testRes.error ?? "error" })}
                              </span>
                            )}
                          </div>
                        )}
                      </div>

                      <div className="flex flex-wrap items-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => testKeyMutation.mutate(k.id)}
                          disabled={testKeyMutation.isPending}
                        >
                          {t("providers.testKey")}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() =>
                            updateKeyMutation.mutate({
                              id: k.id,
                              status: k.status === "paused" ? "active" : "paused",
                            })
                          }
                        >
                          {k.status === "paused" ? (
                            <>
                              <Play className="h-3.5 w-3.5" />
                              <span>{t("providers.activateKey")}</span>
                            </>
                          ) : (
                            <>
                              <Pause className="h-3.5 w-3.5" />
                              <span>{t("providers.pauseKey")}</span>
                            </>
                          )}
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={t("common.delete")}
                          onClick={() => deleteKeyMutation.mutate(k.id)}
                        >
                          <Trash2 className="h-4 w-4 text-rose-500" />
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Add Key Form */}
            <form
              onSubmit={handleAddKey}
              className="space-y-4 border-t border-[var(--border)] pt-4"
            >
              <h3 className="text-sm font-semibold">{t("providers.addKey")}</h3>
              {keyTier === "free" && (
                <Alert variant="warning">{t("providers.freeTierWarning")}</Alert>
              )}

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div className="space-y-1">
                  <Label htmlFor="key-provider">{t("providers.keyProvider")}</Label>
                  <Select
                    id="key-provider"
                    value={effectiveProviderId}
                    onChange={(e) => setKeyProviderId(e.target.value)}
                  >
                    {providers.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.type}
                      </option>
                    ))}
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="key-label">{t("providers.keyLabel")}</Label>
                  <Input
                    id="key-label"
                    required
                    value={keyLabel}
                    onChange={(e) => setKeyLabel(e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="key-secret">{t("providers.keySecret")}</Label>
                  <Input
                    id="key-secret"
                    type="password"
                    required
                    value={keySecret}
                    onChange={(e) => setKeySecret(e.target.value)}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 sm:grid-cols-6">
                <div className="space-y-1">
                  <Label htmlFor="key-tier">{t("providers.keyTier")}</Label>
                  <Select
                    id="key-tier"
                    value={keyTier}
                    onChange={(e) => setKeyTier(e.target.value as KeyTier)}
                  >
                    <option value="paid">{t("providers.tierPaid")}</option>
                    <option value="free">{t("providers.tierFree")}</option>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="key-priority">{t("providers.keyPriority")}</Label>
                  <Input
                    id="key-priority"
                    type="number"
                    min="1"
                    max="100"
                    value={keyPriority}
                    onChange={(e) => setKeyPriority(e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="key-rpm">{t("providers.keyRpm")}</Label>
                  <Input
                    id="key-rpm"
                    type="number"
                    min="1"
                    value={keyRpm}
                    onChange={(e) => setKeyRpm(e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="key-tpm">{t("providers.keyTpm")}</Label>
                  <Input
                    id="key-tpm"
                    type="number"
                    min="1"
                    value={keyTpm}
                    onChange={(e) => setKeyTpm(e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="key-rpd">{t("providers.keyRpd")}</Label>
                  <Input
                    id="key-rpd"
                    type="number"
                    min="1"
                    value={keyRpd}
                    onChange={(e) => setKeyRpd(e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="key-budget">{t("providers.keyBudget")}</Label>
                  <Input
                    id="key-budget"
                    type="number"
                    min="0"
                    step="0.01"
                    value={keyBudget}
                    onChange={(e) => setKeyBudget(e.target.value)}
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="space-y-1">
                  <Label htmlFor="key-models">{t("providers.keyAllowedModels")}</Label>
                  <Input
                    id="key-models"
                    value={keyAllowedModels}
                    onChange={(e) => setKeyAllowedModels(e.target.value)}
                    placeholder="gemini-2.0-flash, gemini-2.0-flash-lite"
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="key-concurrency">{t("providers.keyConcurrency")}</Label>
                  <Input
                    id="key-concurrency"
                    type="number"
                    min="1"
                    max="32"
                    value={keyConcurrency}
                    onChange={(e) => setKeyConcurrency(e.target.value)}
                  />
                </div>
              </div>

              <div className="flex justify-end">
                <Button
                  type="submit"
                  disabled={createKeyMutation.isPending || !effectiveProviderId}
                >
                  <Plus className="h-4 w-4" />
                  <span>{t("providers.addKey")}</span>
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

        {/* Model Profiles */}
        <Card>
          <CardHeader>
            <CardTitle>{t("providers.profilesList")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              {profiles.map((prof) => (
                <div
                  key={prof.id}
                  className="flex flex-wrap items-center justify-between rounded-lg border border-[var(--border)] p-3 text-sm"
                >
                  <div className="font-medium">{prof.name}</div>
                  <div className="flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
                    <Badge variant="info">{prof.strategy}</Badge>
                    <span>{prof.models.map((m) => `${m.provider}:${m.model}`).join(" → ")}</span>
                  </div>
                </div>
              ))}
            </div>

            <form
              onSubmit={handleAddProfile}
              className="space-y-3 border-t border-[var(--border)] pt-4"
            >
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="space-y-1">
                  <Label htmlFor="profile-name">{t("providers.profileName")}</Label>
                  <Input
                    id="profile-name"
                    required
                    value={profileName}
                    onChange={(e) => setProfileName(e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="profile-strategy">{t("providers.profileStrategy")}</Label>
                  <Select
                    id="profile-strategy"
                    value={profileStrategy}
                    onChange={(e) => setProfileStrategy(e.target.value as RoutingStrategy)}
                  >
                    <option value="priority">{t("providers.strategyPriority")}</option>
                    <option value="round_robin">{t("providers.strategyRoundRobin")}</option>
                    <option value="lowest_cost">{t("providers.strategyLowestCost")}</option>
                  </Select>
                </div>
              </div>
              <div className="space-y-1">
                <Label htmlFor="profile-models">{t("providers.profileModels")}</Label>
                <Textarea
                  id="profile-models"
                  rows={2}
                  value={profileModelsText}
                  onChange={(e) => setProfileModelsText(e.target.value)}
                />
              </div>
              <div className="flex justify-end">
                <Button type="submit" disabled={createProfileMutation.isPending}>
                  <Plus className="h-4 w-4" />
                  <span>{t("providers.addProfile")}</span>
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
