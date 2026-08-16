import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { apiFetch } from "../lib/api";

interface User {
  id: number;
  email: string;
}

interface AuthResponse {
  token: string;
  user: User;
}

interface AuthContextValue {
  user: User | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const STORAGE_KEY = "auth";

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function loadStoredAuth(): AuthResponse | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthResponse;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => loadStoredAuth()?.user ?? null);

  useEffect(() => {
    const handleUnauthorized = () => {
      localStorage.removeItem(STORAGE_KEY);
      setUser(null);
    };
    window.addEventListener("auth:unauthorized", handleUnauthorized);
    return () => window.removeEventListener("auth:unauthorized", handleUnauthorized);
  }, []);

  const persist = (data: AuthResponse) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    setUser(data.user);
  };

  const login = async (email: string, password: string) => {
    const data = await apiFetch<AuthResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    persist(data);
  };

  const signup = async (email: string, password: string) => {
    const data = await apiFetch<AuthResponse>("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    persist(data);
  };

  const logout = () => {
    localStorage.removeItem(STORAGE_KEY);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, isAuthenticated: user !== null, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
