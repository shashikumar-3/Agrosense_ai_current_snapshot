import React, { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { getApiBase } from "@/lib/api-base";

interface AuthUser {
  id: string;
  email: string;
  name?: string;
}

interface AuthContextType {
  user: AuthUser | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, name: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);
const AUTH_TOKEN_KEY = "agrosense_auth_token";
const AUTH_USER_KEY = "agrosense_user";

async function readApiResponse(res: Response): Promise<Record<string, unknown>> {
  if (!(res.headers.get("content-type") || "").includes("application/json")) {
    throw new Error("The authentication service returned an unexpected response. Ensure the AgroSense Flask API is running on the configured API port.");
  }
  return res.json() as Promise<Record<string, unknown>>;
}

function networkErrorMessage(): string {
  return "Cannot reach the authentication service. Start the AgroSense Flask API and check VITE_API_BASE.";
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const restoreSession = async () => {
      const storedUser = localStorage.getItem(AUTH_USER_KEY);
      const token = localStorage.getItem(AUTH_TOKEN_KEY);

      if (storedUser && token) {
        try {
          const res = await fetch(`${getApiBase()}/auth/me`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (!res.ok) throw new Error("Session expired");
          const data = await res.json();
          setUser(data.user);
          localStorage.setItem(AUTH_USER_KEY, JSON.stringify(data.user));
        } catch {
          localStorage.removeItem(AUTH_TOKEN_KEY);
          localStorage.removeItem(AUTH_USER_KEY);
          setUser(null);
        }
      }
      setIsLoading(false);
    };
    restoreSession();
  }, []);

  const login = async (email: string, password: string) => {
    setIsLoading(true);
    try {
      const res = await fetch(`${getApiBase()}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await readApiResponse(res);
      if (!res.ok) {
        throw new Error(typeof data.error === "string" ? data.error : "Login failed");
      }
      if (typeof data.token !== "string" || !data.user || typeof data.user !== "object") throw new Error("The authentication service returned incomplete account data.");
      setUser(data.user as AuthUser);
      localStorage.setItem(AUTH_TOKEN_KEY, data.token);
      localStorage.setItem(AUTH_USER_KEY, JSON.stringify(data.user));
    } catch (error) {
      if (error instanceof TypeError) throw new Error(networkErrorMessage());
      throw error;
    } finally {
      setIsLoading(false);
    }
  };

  const signup = async (email: string, password: string, name: string) => {
    setIsLoading(true);
    try {
      const res = await fetch(`${getApiBase()}/auth/signup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, name }),
      });
      const data = await readApiResponse(res);
      if (!res.ok) {
        throw new Error(typeof data.error === "string" ? data.error : "Signup failed");
      }
      if (typeof data.token !== "string" || !data.user || typeof data.user !== "object") throw new Error("The authentication service returned incomplete account data.");
      setUser(data.user as AuthUser);
      localStorage.setItem(AUTH_TOKEN_KEY, data.token);
      localStorage.setItem(AUTH_USER_KEY, JSON.stringify(data.user));
    } catch (error) {
      if (error instanceof TypeError) throw new Error(networkErrorMessage());
      throw error;
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async () => {
    const token = localStorage.getItem(AUTH_TOKEN_KEY);
    if (token) {
      try {
        await fetch(`${getApiBase()}/auth/logout`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        });
      } catch {
        // Ignore network errors while logging out locally.
      }
    }
    setUser(null);
    localStorage.removeItem(AUTH_USER_KEY);
    localStorage.removeItem(AUTH_TOKEN_KEY);
  };

  return (
    <AuthContext.Provider value={{ user, isLoading, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
