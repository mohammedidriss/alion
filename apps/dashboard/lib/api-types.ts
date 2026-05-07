/**
 * Type aliases over `api-schema.ts` (auto-generated from FastAPI's
 * `/openapi.json`). Use these instead of hand-writing interfaces — every
 * Pydantic schema change becomes a one-command refresh:
 *
 *     pnpm gen:api      # requires the API to be running on localhost:8000
 *
 * Old hand-written interfaces in `lib/api.ts` will be migrated to these
 * gradually. New entities should use the generated types from day one.
 */

import type { components } from "@/lib/api-schema";

type S = components["schemas"];

// Identity / profiles
export type FighterRead = S["FighterRead"];
export type CoachRead = S["CoachRead"];
export type RefereeRead = S["RefereeRead"];

// Sessions / events
export type SessionRead = S["SessionRead"];
export type PunchEventRead = S["PunchEventRead"];

// Phase 2 / HRV
export type ReadinessResponse = S["ReadinessResponse"];
export type MatrixResponse = S["MatrixResponse"];
export type MatrixPoint = S["MatrixPoint"];

// Medical
export type MedicalRecordRead = S["MedicalRecordRead"];
export type AllergyRead = S["AllergyRead"];
export type MedicationRead = S["MedicationRead"];
export type MedicalConditionRead = S["MedicalConditionRead"];

// Performance
export type PerformanceResponse = S["PerformanceResponse"];

// Sub-types worth surfacing
export type Stance = S["Stance"];
export type SkillLevel = S["SkillLevel"];
export type SessionSourceEnum = S["SessionSourceEnum"];
export type SessionStatus = S["SessionStatus"];
export type AllergySeverity = S["AllergySeverity"];
export type ConditionStatus = S["ConditionStatus"];
export type CoachingLevel = S["CoachingLevel"];
export type RefereeCertLevel = S["RefereeCertLevel"];
