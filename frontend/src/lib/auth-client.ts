import {
  UserManager,
  WebStorageStateStore,
  type User,
  type UserManagerSettings,
} from "oidc-client-ts";

const AUTH_MODE = process.env.NEXT_PUBLIC_AUTH_MODE ?? "disabled";
const OIDC_AUTHORITY = process.env.NEXT_PUBLIC_OIDC_AUTHORITY ?? "";
const OIDC_CLIENT_ID = process.env.NEXT_PUBLIC_OIDC_CLIENT_ID ?? "";
const OIDC_AUDIENCE = process.env.NEXT_PUBLIC_OIDC_AUDIENCE ?? "";
const OIDC_SCOPE = process.env.NEXT_PUBLIC_OIDC_SCOPE ?? "openid profile email";
const OIDC_REDIRECT_URI = process.env.NEXT_PUBLIC_OIDC_REDIRECT_URI ?? "";
const PRODUCTION = process.env.NEXT_PUBLIC_APP_MODE === "production";

let manager: UserManager | null = null;

export function isOidcEnabled() {
  return AUTH_MODE === "oidc";
}

export function getUserManager(): UserManager {
  if (!isOidcEnabled()) {
    throw new Error("OIDC authentication is disabled");
  }
  if (!OIDC_AUTHORITY || !OIDC_CLIENT_ID || !OIDC_AUDIENCE) {
    throw new Error("OIDC authority, client ID and API audience are required");
  }
  if (typeof window === "undefined") {
    throw new Error("OIDC UserManager is available only in the browser");
  }
  if (manager) return manager;

  const authority = new URL(OIDC_AUTHORITY);
  if (PRODUCTION && authority.protocol !== "https:") {
    throw new Error("Production OIDC authority must use HTTPS");
  }
  // Keep the callback host stable when local development alternates between
  // localhost and 127.0.0.1. Auth0 requires an exact redirect URI, and the
  // transaction state is stored per browser origin.
  const configuredRedirect = OIDC_REDIRECT_URI ? new URL(OIDC_REDIRECT_URI) : null;
  const origin = configuredRedirect?.origin ?? window.location.origin;
  const redirectUri = configuredRedirect?.toString().replace(/\/$/, "") ?? `${origin}/auth/callback`;
  const settings: UserManagerSettings = {
    authority: authority.toString().replace(/\/$/, ""),
    client_id: OIDC_CLIENT_ID,
    redirect_uri: redirectUri,
    silent_redirect_uri: `${origin}/auth/silent-callback`,
    post_logout_redirect_uri: origin,
    response_type: "code",
    scope: OIDC_SCOPE,
    extraQueryParams: { audience: OIDC_AUDIENCE },
    automaticSilentRenew: true,
    monitorSession: false,
    loadUserInfo: false,
    userStore: new WebStorageStateStore({ store: window.sessionStorage }),
    stateStore: new WebStorageStateStore({ store: window.sessionStorage }),
  };
  manager = new UserManager(settings);
  return manager;
}

export async function getAccessToken(): Promise<string | null> {
  if (!isOidcEnabled()) return null;
  const user = await getUserManager().getUser();
  return user && !user.expired ? user.access_token : null;
}

export async function beginSignIn(returnTo?: string): Promise<void> {
  const safeReturnTo = safeRelativePath(
    returnTo ?? `${window.location.pathname}${window.location.search}`,
  );
  await getUserManager().signinRedirect({ state: { returnTo: safeReturnTo } });
}

export async function completeSignIn(): Promise<{ user: User; returnTo: string }> {
  const user = await getUserManager().signinRedirectCallback();
  const state = user.state;
  const returnTo =
    state && typeof state === "object" && "returnTo" in state
      ? safeRelativePath(String(state.returnTo))
      : "/";
  return { user, returnTo };
}

export async function completeSilentSignIn(): Promise<void> {
  await getUserManager().signinSilentCallback();
}

export async function beginSignOut(): Promise<void> {
  const active = getUserManager();
  try {
    await active.signoutRedirect();
  } catch {
    await active.removeUser();
    window.location.reload();
  }
}

function safeRelativePath(value: string): string {
  return value.startsWith("/") && !value.startsWith("//") ? value : "/";
}
