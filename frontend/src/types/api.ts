/**
 * API types — generated from backend OpenAPI schema via scripts/generate-types.ts.
 * Run: npm run generate-types
 *
 * These are hand-written stubs until A1 is merged and openapi.json is available.
 * Regenerate after any backend schema change.
 */

export interface UserProfile {
  full_name: string;
  avatar_url: string | null;
  preferred_language: string;
  timezone: string;
}

export interface User {
  id: string;
  email: string;
  is_verified: boolean;
  status: "pending_verification" | "active" | "suspended" | "deactivated" | "deletion_requested";
  created_at: string;
  profile: UserProfile | null;
}

export interface RegisterRequest {
  full_name: string;
  email: string;
  password: string;
  confirm_password: string;
  terms_accepted: boolean;
}

export interface LoginRequest {
  email: string;
  password: string;
  remember_me?: boolean;
}

export type WorkspaceType =
  | "university"
  | "personal_learning"
  | "research"
  | "professional_development"
  | "custom";

export interface Workspace {
  id: string;
  name: string;
  description: string | null;
  workspace_type: WorkspaceType;
  icon: string | null;
  colour: string | null;
  is_default: boolean;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateWorkspaceRequest {
  name: string;
  description?: string | null;
  workspace_type?: WorkspaceType;
  icon?: string | null;
  colour?: string | null;
}

export interface UpdateWorkspaceRequest {
  name?: string;
  description?: string | null;
  workspace_type?: WorkspaceType;
  icon?: string | null;
  colour?: string | null;
}
