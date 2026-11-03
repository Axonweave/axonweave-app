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
