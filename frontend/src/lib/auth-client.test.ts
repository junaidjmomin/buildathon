import type { User } from "oidc-client-ts";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const oidc = vi.hoisted(() => ({
  signinRedirect: vi.fn(),
  signinRedirectCallback: vi.fn(),
  signinSilentCallback: vi.fn(),
  getUser: vi.fn(),
  removeUser: vi.fn(),
}));

vi.mock("oidc-client-ts", () => ({
  UserManager: class {
    signinRedirect = oidc.signinRedirect;
    signinRedirectCallback = oidc.signinRedirectCallback;
    signinSilentCallback = oidc.signinSilentCallback;
    getUser = oidc.getUser;
    removeUser = oidc.removeUser;
  },
  WebStorageStateStore: class {},
}));

describe("OIDC callback completion", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.stubEnv("NEXT_PUBLIC_AUTH_MODE", "oidc");
    vi.stubEnv("NEXT_PUBLIC_APP_MODE", "demo");
    vi.stubEnv("NEXT_PUBLIC_OIDC_AUTHORITY", "https://identity.example.test");
    vi.stubEnv("NEXT_PUBLIC_OIDC_CLIENT_ID", "client-id");
    vi.stubEnv("NEXT_PUBLIC_OIDC_AUDIENCE", "https://api.example.test");
    vi.stubEnv("NEXT_PUBLIC_OIDC_SCOPE", "openid profile email");
    vi.stubEnv("NEXT_PUBLIC_OIDC_REDIRECT_URI", "http://localhost:3000/auth/callback");
    oidc.signinRedirect.mockReset().mockResolvedValue(undefined);
    oidc.signinRedirectCallback.mockReset();
    oidc.signinSilentCallback.mockReset();
    oidc.getUser.mockReset();
    oidc.removeUser.mockReset().mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("exchanges an authorization code only once across concurrent callback effects", async () => {
    let resolveCallback!: (user: User) => void;
    const callback = new Promise<User>((resolve) => {
      resolveCallback = resolve;
    });
    oidc.signinRedirectCallback.mockReturnValue(callback);
    const { completeSignIn } = await import("@/lib/auth-client");

    const first = completeSignIn();
    const second = completeSignIn();

    expect(oidc.signinRedirectCallback).toHaveBeenCalledTimes(1);
    const user = { state: { returnTo: "/exceptions" } } as User;
    resolveCallback(user);

    await expect(first).resolves.toEqual({ user, returnTo: "/exceptions" });
    await expect(second).resolves.toEqual({ user, returnTo: "/exceptions" });
  });

  it("shares silent callback completion across concurrent effect runs", async () => {
    let resolveCallback!: () => void;
    const callback = new Promise<void>((resolve) => {
      resolveCallback = resolve;
    });
    oidc.signinSilentCallback.mockReturnValue(callback);
    const { completeSilentSignIn } = await import("@/lib/auth-client");

    const first = completeSilentSignIn();
    const second = completeSilentSignIn();

    expect(oidc.signinSilentCallback).toHaveBeenCalledTimes(1);
    resolveCallback();
    await Promise.all([first, second]);
  });

  it("starts a fresh callback completion for a new sign-in transaction", async () => {
    const firstUser = { state: { returnTo: "/" } } as User;
    const secondUser = { state: { returnTo: "/controls" } } as User;
    oidc.signinRedirectCallback
      .mockResolvedValueOnce(firstUser)
      .mockResolvedValueOnce(secondUser);
    const { beginSignIn, completeSignIn } = await import("@/lib/auth-client");

    await expect(completeSignIn()).resolves.toEqual({ user: firstUser, returnTo: "/" });
    await beginSignIn("/controls");
    await expect(completeSignIn()).resolves.toEqual({
      user: secondUser,
      returnTo: "/controls",
    });

    expect(oidc.signinRedirectCallback).toHaveBeenCalledTimes(2);
  });

  it("canonicalizes alternate local origins before creating OIDC state", async () => {
    const { getCanonicalAppUrl } = await import("@/lib/auth-client");

    expect(
      getCanonicalAppUrl("http://127.0.0.1:3000/controls?status=open#candidate"),
    ).toBe("http://localhost:3000/controls?status=open#candidate");
    expect(getCanonicalAppUrl("http://localhost:3000/controls")).toBeNull();
  });

  it("recovers an already-completed callback from the stored user", async () => {
    const user = { expired: false, state: { returnTo: "/root-causes" } } as User;
    oidc.getUser.mockResolvedValue(user);
    const { recoverCompletedSignIn } = await import("@/lib/auth-client");

    await expect(recoverCompletedSignIn()).resolves.toEqual({
      user,
      returnTo: "/root-causes",
    });
  });

  it("deduplicates concurrent stale-session clears", async () => {
    let resolveRemoval!: () => void;
    oidc.removeUser.mockReturnValue(
      new Promise<void>((resolve) => {
        resolveRemoval = resolve;
      }),
    );
    const { clearAuthSession } = await import("@/lib/auth-client");

    const first = clearAuthSession();
    const second = clearAuthSession();

    expect(oidc.removeUser).toHaveBeenCalledTimes(1);
    resolveRemoval();
    await Promise.all([first, second]);
  });
});
