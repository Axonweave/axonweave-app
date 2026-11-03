"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { User } from "@/types/api";

interface AuthState {
  user: User | null;
  loading: boolean;
  error: string | null;
}

export function useAuth(): AuthState {
  const [state, setState] = useState<AuthState>({ user: null, loading: true, error: null });

  useEffect(() => {
    api
      .get<{ user: User }>("/auth/me")
      .then((res) => setState({ user: res.data.user, loading: false, error: null }))
      .catch(() => setState({ user: null, loading: false, error: "unauthenticated" }));
  }, []);

  return state;
}
