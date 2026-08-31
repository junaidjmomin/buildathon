"use client";

import { KeyRound, LoaderCircle, ShieldAlert } from "lucide-react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { User } from "oidc-client-ts";

import {
  beginSignIn,
  beginSignOut,
  completeSignIn,
  completeSilentSignIn,
  getCanonicalAppUrl,
  getUserManager,
  isOidcEnabled,
  recoverCompletedSignIn,
} from "@/lib/auth-client";

type AuthContextValue = {
  enabled: boolean;
  displayName: string | null;
  signIn: () => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const enabled = isOidcEnabled();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let active = true;
    let manager: ReturnType<typeof getUserManager>;
    try {
      const canonicalAppUrl = getCanonicalAppUrl();
      if (canonicalAppUrl) {
        window.location.replace(canonicalAppUrl);
        return () => {
          active = false;
        };
      }
      manager = getUserManager();
    } catch {
      queueMicrotask(() => {
        if (!active) return;
        setError("OIDC configuration is incomplete or invalid.");
        setLoading(false);
      });
      return;
    }

    const onLoaded = (next: User) => {
      if (active) setUser(next);
    };
    const onUnloaded = () => {
      if (active) setUser(null);
    };
    const onExpired = () => {
      if (active) setUser(null);
    };
    manager.events.addUserLoaded(onLoaded);
    manager.events.addUserUnloaded(onUnloaded);
    manager.events.addAccessTokenExpired(onExpired);

    async function initialize() {
      try {
        if (window.location.pathname === "/auth/callback") {
          const completed = await completeSignIn();
          if (!active) return;
          setUser(completed.user);
          window.location.replace(completed.returnTo);
          return;
        }
        if (window.location.pathname === "/auth/silent-callback") {
          await completeSilentSignIn();
          if (window.top === window.self) window.location.replace("/");
          return;
        }
        const stored = await manager.getUser();
        if (!active) return;
        setUser(stored && !stored.expired ? stored : null);
        if (stored?.expired) await manager.removeUser();
      } catch (caught) {
        if (window.location.pathname === "/auth/callback") {
          const recovered = await recoverCompletedSignIn().catch(() => null);
          if (recovered && active) {
            setUser(recovered.user);
            window.location.replace(recovered.returnTo);
            return;
          }
        }
        // A rejected callback leaves the oidc-client transaction in
        // sessionStorage. Clear it so the next attempt starts a fresh state
        // transaction instead of looping back through the same error.
        await manager.clearStaleState().catch(() => undefined);
        if (active) {
          if (windowPathIsCallback()) {
            window.history.replaceState({}, "", "/");
          }
          const detail = caught instanceof Error ? caught.message : "Unknown callback error";
          setError(
            process.env.NEXT_PUBLIC_APP_MODE === "production"
              ? "Sign-in could not be completed. Retry through organization SSO."
              : `Sign-in callback failed: ${detail}. Start again from the application sign-in page.`,
          );
        }
      } finally {
        if (active) setLoading(false);
      }
    }
    void initialize();
    return () => {
      active = false;
      manager.events.removeUserLoaded(onLoaded);
      manager.events.removeUserUnloaded(onUnloaded);
      manager.events.removeAccessTokenExpired(onExpired);
    };
  }, [enabled]);

  const signIn = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      await beginSignIn();
    } catch (caught) {
      setLoading(false);
      setError(authActionError("Sign-in could not be started", caught));
    }
  }, []);
  const signOut = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      await beginSignOut();
    } catch (caught) {
      setLoading(false);
      setError(authActionError("Sign-out could not be completed", caught));
    }
  }, []);
  const value = useMemo<AuthContextValue>(
    () => ({
      enabled,
      displayName:
        user?.profile.name ?? user?.profile.preferred_username ?? user?.profile.sub ?? null,
      signIn,
      signOut,
    }),
    [enabled, signIn, signOut, user],
  );

  if (enabled && error) {
    return <AuthGate mode="error" message={error} onSignIn={signIn} />;
  }
  if (enabled && (loading || windowPathIsCallback())) {
    return <AuthGate mode="loading" />;
  }
  if (enabled && !user) {
    return <AuthGate mode="sign-in" onSignIn={signIn} />;
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return value;
}

function windowPathIsCallback(): boolean {
  return (
    typeof window !== "undefined" &&
    (window.location.pathname === "/auth/callback" ||
      window.location.pathname === "/auth/silent-callback")
  );
}

function authActionError(prefix: string, caught: unknown): string {
  if (process.env.NEXT_PUBLIC_APP_MODE === "production") {
    return `${prefix}. Retry or contact your workspace administrator.`;
  }
  const detail = caught instanceof Error ? caught.message : "Unknown authentication error";
  return `${prefix}: ${detail}.`;
}

function AuthGate({
  mode,
  message,
  onSignIn,
}: {
  mode: "loading" | "sign-in" | "error";
  message?: string;
  onSignIn?: () => Promise<void>;
}) {
  return (
    <main className="grid min-h-screen place-items-center bg-[var(--ink-900)] px-5 py-12">
      <section
        aria-busy={mode === "loading"}
        aria-live="polite"
        className="panel w-full max-w-md rounded-2xl p-8 text-center"
      >
        <span className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-[rgba(47,189,127,0.14)] text-[var(--evergreen)]">
          {mode === "loading" ? (
            <LoaderCircle aria-hidden="true" className="animate-spin" size={22} />
          ) : mode === "error" ? (
            <ShieldAlert aria-hidden="true" size={22} />
          ) : (
            <KeyRound aria-hidden="true" size={22} />
          )}
        </span>
        <p className="mt-5 text-[10px] font-bold uppercase tracking-[0.15em] text-[var(--evergreen)]">
          Razorpay workspace access
        </p>
        <h1 className="mt-2 text-2xl font-semibold tracking-[-0.035em]">
          {mode === "loading"
            ? "Verifying your session"
            : mode === "error"
              ? "Authentication needs attention"
              : "Sign in to sl3dge"}
        </h1>
        <p className="mt-3 text-sm leading-6 text-[var(--paper-dim)]">
          {mode === "error"
            ? message
            : mode === "loading"
              ? "Completing the secure OIDC authorization flow."
              : "Use your organization identity. Financial data remains behind FastAPI and tenant isolation."}
        </p>
        {mode !== "loading" ? (
          <button
            className="mt-7 inline-flex items-center justify-center rounded-lg bg-[var(--evergreen)] px-4 py-2.5 text-sm font-semibold text-[#06120c]"
            onClick={() => void onSignIn?.()}
            type="button"
          >
            Continue with organization SSO
          </button>
        ) : null}
      </section>
    </main>
  );
}
