import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, sessionStore, type Session } from "./api";
import type { Me } from "./types";

interface RegisterInput {
  email: string;
  password: string;
  full_name: string;
  organization_name?: string;
  invitation_token?: string;
}

interface AuthValue {
  me: Me | undefined;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (input: RegisterInput) => Promise<void>;
  logout: () => Promise<void>;
  refreshMe: () => Promise<unknown>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [hasSession, setHasSession] = useState(() => sessionStore.get() !== null);

  const meQuery = useQuery({
    queryKey: ["me"],
    queryFn: () => api<Me>("/api/v1/auth/me"),
    enabled: hasSession,
    staleTime: 60_000,
    retry: false,
  });

  useEffect(() => {
    const onLogout = () => {
      setHasSession(false);
      qc.clear();
    };
    window.addEventListener("tp:logout", onLogout);
    return () => window.removeEventListener("tp:logout", onLogout);
  }, [qc]);

  const start = useCallback(
    (s: Session) => {
      sessionStore.set(s);
      qc.clear();
      setHasSession(true);
    },
    [qc],
  );

  const login = useCallback(
    async (email: string, password: string) => {
      start(await api<Session>("/api/v1/auth/login", { method: "POST", body: { email, password }, auth: false }));
    },
    [start],
  );

  const register = useCallback(
    async (input: RegisterInput) => {
      start(await api<Session>("/api/v1/auth/register", { method: "POST", body: input, auth: false }));
    },
    [start],
  );

  const logout = useCallback(async () => {
    const s = sessionStore.get();
    if (s) {
      try {
        await api("/api/v1/auth/logout", { method: "POST", body: { refresh_token: s.refresh_token }, auth: false });
      } catch {
        /* best effort */
      }
    }
    sessionStore.clear();
    setHasSession(false);
    qc.clear();
  }, [qc]);

  const value = useMemo<AuthValue>(
    () => ({
      me: meQuery.data,
      isAuthenticated: hasSession && !!meQuery.data,
      isLoading: hasSession && meQuery.isLoading,
      login,
      register,
      logout,
      refreshMe: () => meQuery.refetch(),
    }),
    [hasSession, meQuery, login, register, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
