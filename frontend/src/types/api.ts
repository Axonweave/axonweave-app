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

export interface UserPreferences {
  theme: "light" | "dark" | "system";
  explanation_style: string | null;
  academic_level: string | null;
  preferred_language: string;
}

export interface SessionInfo {
  id: string;
  user_agent: string | null;
  ip_address: string | null;
  created_at: string;
  last_used_at: string;
  expires_at: string;
  is_current: boolean;
}

export interface UpdateProfileRequest {
  full_name?: string;
  avatar_url?: string | null;
  timezone?: string;
  preferred_language?: string;
}

export interface UpdatePreferencesRequest {
  theme?: "light" | "dark" | "system";
  explanation_style?: string | null;
  academic_level?: string | null;
}

export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
}

export interface ChangeEmailRequest {
  current_password: string;
  new_email: string;
}

export interface DeleteAccountRequest {
  current_password: string;
  confirmation: string;
}
