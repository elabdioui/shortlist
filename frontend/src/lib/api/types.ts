// SPDX-License-Identifier: AGPL-3.0-or-later

import type { components } from "@/lib/api/schema";

export type Schemas = components["schemas"];

export type APIKeyCreate = Schemas["APIKeyCreate"];
export type APIKeyResponse = Schemas["APIKeyResponse"];
export type APIKeyTestResult = Schemas["APIKeyTestResult"];
export type APIKeyUpdate = Schemas["APIKeyUpdate"];
export type AnalysisRunResponse = Schemas["AnalysisRunResponse"];
export type AnonymizedPreviewResponse = Schemas["AnonymizedPreviewResponse"];
export type AuditLogResponse = Schemas["AuditLogResponse"];
export type AuthSessionResponse = Schemas["AuthSessionResponse"];
export type AuthSetupRequest = Schemas["AuthSetupRequest"];
export type CandidateDetail = Schemas["CandidateDetail"];
export type CandidateSummary = Schemas["CandidateSummary"];
export type CandidateUploadResponse = Schemas["CandidateUploadResponse"];
export type CriteriaGenerateResponse = Schemas["CriteriaGenerateResponse"];
export type CriteriaSetResponse = Schemas["CriteriaSetResponse"];
export type CriteriaSetUpdate = Schemas["CriteriaSetUpdate"];
export type CriterionItem = Schemas["CriterionItem"];
export type CriterionType = Schemas["CriterionType"];
export type CriterionVerdict = Schemas["CriterionVerdict"];
export type DecisionCreate = Schemas["DecisionCreate"];
export type DecisionResponse = Schemas["DecisionResponse"];
export type EstimateResponse = Schemas["EstimateResponse"];
export type EvaluationResult = Schemas["EvaluationResult"];
export type ExtractionStatus = Schemas["ExtractionStatus"];
export type HumanDecision = Schemas["HumanDecision"];
export type JobCreate = Schemas["JobCreate"];
export type JobResponse = Schemas["JobResponse"];
export type JobStatus = Schemas["JobStatus"];
export type JobUpdate = Schemas["JobUpdate"];
export type KeyStatus = Schemas["KeyStatus"];
export type KeyTier = Schemas["KeyTier"];
export type LoginRequest = Schemas["LoginRequest"];
export type ModelProfileCreate = Schemas["ModelProfileCreate"];
export type ModelProfileEntry = Schemas["ModelProfileEntry"];
export type ModelProfileResponse = Schemas["ModelProfileResponse"];
export type PaginatedAuditLogs = Schemas["PaginatedResponse_AuditLogResponse_"];
export type PaginatedCandidates = Schemas["PaginatedResponse_CandidateSummary_"];
export type PrivacySettingsResponse = Schemas["PrivacySettingsResponse"];
export type PrivacySettingsUpdate = Schemas["PrivacySettingsUpdate"];
export type ProviderCreate = Schemas["ProviderCreate"];
export type ProviderResponse = Schemas["ProviderResponse"];
export type ProviderType = Schemas["ProviderType"];
export type PurgeResultResponse = Schemas["PurgeResultResponse"];
export type Recommendation = Schemas["Recommendation"];
export type RoutingStrategy = Schemas["RoutingStrategy"];
export type RunStartRequest = Schemas["RunStartRequest"];
export type RunStatus = Schemas["RunStatus"];
export type SetupStatusResponse = Schemas["SetupStatusResponse"];
export type UsageLogResponse = Schemas["UsageLogResponse"];
export type UserCreate = Schemas["UserCreate"];
export type UserResponse = Schemas["UserResponse"];
export type UserRole = Schemas["UserRole"];
export type UserUpdate = Schemas["UserUpdate"];
export type VerifiedCriterionResult = Schemas["VerifiedCriterionResult"];

export interface RunProgressEvent {
  run_id: string;
  status: RunStatus;
  processed_count: number;
  total_count: number;
  cumulative_cost_usd: number;
}
