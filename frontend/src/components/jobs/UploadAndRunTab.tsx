// SPDX-License-Identifier: AGPL-3.0-or-later

"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Upload } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRef, useState, type DragEvent } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, jobsApi } from "@/lib/api/client";
import type { CandidateUploadResponse, JobResponse } from "@/lib/api/types";

/** Upload step only: starting and following the analysis lives in JobRunBar. */
export function UploadAndRunTab({ job }: { job: JobResponse }) {
  const t = useTranslations();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [dragActive, setDragActive] = useState(false);
  const [uploadResult, setUploadResult] = useState<CandidateUploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const uploadMutation = useMutation({
    mutationFn: (files: File[]) => jobsApi.uploadCandidates(job.id, files),
    onSuccess: (res) => {
      setUploadResult(res);
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["job", job.id] });
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.detail : t("common.errorGeneric"));
    },
  });

  function handleFiles(fileList: FileList | null) {
    if (!fileList || fileList.length === 0) return;
    uploadMutation.mutate(Array.from(fileList));
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragActive(false);
    handleFiles(e.dataTransfer.files);
  }

  return (
    <div className="space-y-4">
      {error && <Alert variant="danger">{error}</Alert>}

      <Card>
        <CardHeader>
          <CardTitle>{t("job.tabs.upload")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragActive(true);
            }}
            onDragLeave={() => setDragActive(false)}
            onDrop={handleDrop}
            className={`flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-8 text-center transition-colors ${
              dragActive
                ? "border-[var(--primary)] bg-blue-50/50 dark:bg-blue-950/20"
                : "border-[var(--border)] bg-[var(--background)]"
            }`}
          >
            <Upload className="mb-3 h-8 w-8 text-[var(--muted-foreground)]" />
            <p className="text-sm font-medium">{t("job.upload.dropzoneTitle")}</p>
            <p className="mt-1 text-xs text-[var(--muted-foreground)]">
              {t("job.upload.dropzoneSubtitle")}
            </p>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".pdf,.docx,.txt,.zip"
              className="hidden"
              onChange={(e) => handleFiles(e.target.files)}
            />
            <Button
              variant="outline"
              className="mt-4"
              disabled={uploadMutation.isPending}
              onClick={() => fileInputRef.current?.click()}
            >
              {uploadMutation.isPending ? t("job.upload.uploading") : t("job.upload.browseFiles")}
            </Button>
          </div>

          {uploadResult && (
            <Alert variant={uploadResult.uploaded.length > 0 ? "success" : "warning"}>
              <div>
                {t("job.upload.uploadSuccess", {
                  uploaded: uploadResult.uploaded.length,
                  duplicates: (uploadResult.duplicates_skipped ?? []).length,
                })}
              </div>
              {uploadResult.uploaded.length > 0 && (
                <div className="mt-1 text-xs">{t("job.upload.uploadedHint")}</div>
              )}
              {(uploadResult.errors ?? []).length > 0 && (
                <div className="mt-2 text-xs text-rose-700 dark:text-rose-300">
                  <div className="font-semibold">{t("job.upload.uploadErrors")}</div>
                  <ul className="list-disc pl-5">
                    {(uploadResult.errors ?? []).map((err, i) => (
                      <li key={i}>{err}</li>
                    ))}
                  </ul>
                </div>
              )}
            </Alert>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
