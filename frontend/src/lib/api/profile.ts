import { api } from "./client";
import type {
  ChangeEmailRequest,
  ChangePasswordRequest,
  DeleteAccountRequest,
  SessionInfo,
  UpdatePreferencesRequest,
  UpdateProfileRequest,
  User,
  UserPreferences,
  UserProfile,
} from "@/types/api";

export const profileApi = {
  getProfile: () => api.get<UserProfile>("/users/me/profile"),
  updateProfile: (data: UpdateProfileRequest) => api.patch<UserProfile>("/users/me/profile", data),

  getPreferences: () => api.get<UserPreferences>("/users/me/preferences"),
  updatePreferences: (data: UpdatePreferencesRequest) =>
    api.patch<UserPreferences>("/users/me/preferences", data),

  getSessions: () => api.get<SessionInfo[]>("/users/me/sessions"),
  revokeSession: (id: string) => api.delete<null>(`/users/me/sessions/${id}`),

  changePassword: (data: ChangePasswordRequest) =>
    api.post<null>("/users/me/change-password", data),

  changeEmail: (data: ChangeEmailRequest) =>
    api.post<null>("/users/me/change-email", data),

  exportData: () => api.get<User>("/users/me/export"),

  deleteAccount: (data: DeleteAccountRequest) =>
    api.delete<null>("/users/me", { body: JSON.stringify(data) }),
};
