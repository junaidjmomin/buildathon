# sl3dge frontend

This is the Next.js App Router interface for sl3dge. It uses FastAPI as its only
finance/data API; it must never receive Supabase service credentials, Razorpay
keys, or Groq keys.

Create `frontend/.env.local` with public values only when you need to override
the repository-root `.env`:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_APP_MODE=demo
NEXT_PUBLIC_AUTH_MODE=disabled
NEXT_PUBLIC_OIDC_AUTHORITY=
NEXT_PUBLIC_OIDC_CLIENT_ID=
NEXT_PUBLIC_OIDC_AUDIENCE=
NEXT_PUBLIC_OIDC_SCOPE=openid profile email
# Optional: pin the exact Auth0 callback host (recommended for local setup).
# NEXT_PUBLIC_OIDC_REDIRECT_URI=http://localhost:3000/auth/callback
```

For Auth0, set auth mode to `oidc`, authority to the tenant HTTPS URL, client ID
to the SPA application ID, and audience to the sl3dge API identifier. Register
`http://localhost:3000/auth/callback` and
`http://localhost:3000/auth/silent-callback` as local callback URLs.

```bash
pnpm install --frozen-lockfile
pnpm dev
```

For local development, `pnpm dev` falls back to the repository-root `.env`
when `.env.local` is absent and passes only `NEXT_PUBLIC_*` values to Next.js.
This keeps the frontend and backend auth modes aligned without exposing backend
secrets to the frontend process.

Quality gates:

```bash
pnpm exec tsc --noEmit
pnpm lint
pnpm build
```

Production public values must be supplied at image/build time because Next.js
embeds `NEXT_PUBLIC_*` values into the browser bundle. See the repository
[operations guide](../docs/operations.md) for the complete deployment contract.
