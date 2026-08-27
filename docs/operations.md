# sl3dge Operations and Release Runbook

## Deployment topology

The supported production boundary is:

```text
Vercel or hardened Next.js container
  -> HTTPS FastAPI API
      -> Supabase PostgreSQL
      -> private Supabase Storage
      -> Razorpay read APIs
      -> Groq (optional, advisory)
```

Run the FastAPI API and worker as separate processes from the same immutable
backend image. Run Alembic and LangGraph checkpoint setup as one-shot release
jobs before shifting traffic.

## Required configuration

Start from `.env.example`. Secrets belong in the deployment platform's secret
manager, never a frontend variable or committed file.

Backend release requirements:

- `ENVIRONMENT=production`
- `DATABASE_URL`: TLS Supabase runtime/transaction pooler DSN
- `MIGRATION_DATABASE_URL`: distinct TLS direct/session pooler DSN
- `DATABASE_DISABLE_PREPARED_STATEMENTS=true` for a transaction pooler
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and a private Storage bucket
- `AUTH_MODE=oidc`, HTTPS issuer/JWKS URL, audience, tenant claim, and roles claim
- HTTPS-only explicit `CORS_ORIGINS`, deployment `TRUSTED_HOSTS`, and
  `FORCE_HTTPS=true`
- TLS `AGENT_CHECKPOINT_DATABASE_URL`
- at least one `WORKER_TENANT_IDS` value
- optional `GROQ_API_KEY`; the deterministic pipeline remains available without it
- Razorpay key ID/secret when live or sandbox synchronization is enabled

Frontend build requirements:

- final HTTPS `NEXT_PUBLIC_API_BASE_URL`
- `NEXT_PUBLIC_APP_MODE=production`
- `NEXT_PUBLIC_AUTH_MODE=oidc`
- final OIDC authority, SPA client ID, API audience, and scopes

`NEXT_PUBLIC_*` values are public by definition and are compiled into the
frontend. No privileged value may use that prefix.

## Supabase preparation

1. Create the project and a private `sl3dge-private` Storage bucket.
2. Use the transaction pooler for API/worker traffic and the direct or session
   pooler for migrations. Both production DSNs must require TLS.
3. Apply schema migrations with the privileged migration identity:

   ```bash
   python -m alembic -c backend/alembic.ini upgrade head
   ```

4. Initialize LangGraph checkpoint tables:

   ```bash
   python -m app.agents.checkpoint setup
   ```

5. Grant the runtime identity only the required table/sequence permissions. Do
   not use the Postgres owner or Supabase service role as the application
   database identity.
6. Verify forced RLS using two synthetic tenant IDs: tenant A cannot select,
   update, or insert tenant B rows. The application sets `app.tenant_id` locally
   on every PostgreSQL transaction.
7. Verify Storage upload/delete using a disposable object and confirm the bucket
   is not public. Store only bucket/path/checksum/provenance metadata in Postgres.

## Auth0/OIDC preparation

Create a Single Page Application and an API whose identifier exactly matches
`OIDC_AUDIENCE`/`NEXT_PUBLIC_OIDC_AUDIENCE`.

Configure local callback URLs:

- `http://localhost:3000/auth/callback`
- `http://localhost:3000/auth/silent-callback`

Configure the equivalent HTTPS production URLs, allowed web origins, and logout
URLs. Add a Post Login Action that copies trusted application metadata to
namespaced access-token claims:

```javascript
exports.onExecutePostLogin = async (event, api) => {
  const namespace = "https://sl3dge.app";
  const merchantId = event.user.app_metadata?.merchant_id;
  const roles = event.user.app_metadata?.roles ?? [];

  if (merchantId) {
    api.accessToken.setCustomClaim(`${namespace}/merchant_id`, merchantId);
  }
  api.accessToken.setCustomClaim(`${namespace}/roles`, roles);
};
```

Set backend claims to `https://sl3dge.app/merchant_id` and
`https://sl3dge.app/roles`. Assign merchant and role values through
`app_metadata`, not user-editable metadata. Test an authorized admin, a user
without the required role, a wrong audience token, and an expired token.

## Release sequence

1. Build immutable backend and frontend artifacts from the same revision.
2. Run backend unit/integration checks and frontend type/lint/build checks.
3. Back up the database and record the current Alembic revision.
4. Run `alembic upgrade head` and checkpoint setup as one-shot jobs.
5. Start the API; require `/health/live` and `/health/ready` to pass.
6. Start one worker, verify it can acquire and renew a job lease, then scale it.
7. Deploy the frontend built with final HTTPS API/OIDC values.
8. Run the smoke suite below before enabling merchant traffic.

## Smoke suite

- Sign in and confirm the access token contains the expected audience, tenant,
  and role claims.
- Load the seeded NovaCart run and compare all counts and stable IDs with
  `data/demo/manifest.json`.
- Open `PAY_82HD9`; verify expected net `9817.10`, observed net/bank credit
  `9793.50`, and leakage `23.60`.
- Verify `REF_91`, `SET_1042`, `RC_MDR_01`, and unresolved `UNR_003`.
- Run mutation testing and confirm 47/50 detected with no canonical-source
  mutation.
- Upload and remove a disposable private Storage object.
- Run a two-tenant RLS isolation probe using the least-privilege runtime role.
- If Groq is configured, verify one structured response; then disable the key and
  confirm deterministic routes still work.
- If Razorpay keys are configured, run a bounded test-mode sync, retry with the
  same idempotency key, and verify no duplicate canonical records.

## Monitoring and incident response

Monitor API 5xx/latency, readiness, worker lease age, failed/retryable jobs,
database pool saturation, Supabase quota/storage errors, OIDC failures, and
Razorpay/Groq upstream errors. Propagate and search `X-Request-ID`; never log
tokens, API keys, raw agreement contents, or full provider payloads.

On an upstream AI outage, leave deterministic controls active and disable only
AI-assisted actions. On Razorpay degradation, stop or drain workers without
changing existing verified results. On database failure, fail readiness and
pause workers; do not fall back to process memory in production.

## Rollback and recovery

Application rollback means redeploying the previous immutable image. Database
downgrades are not automatic: review each Alembic downgrade against retained
data and prefer a forward repair migration. Restore tests must be exercised in a
non-production project, including tenant policies, audit rows, artifact metadata,
and checkpoint tables. Rotate any credential suspected of exposure before
resuming traffic.

## External launch gates

The repository cannot perform these account-level actions by itself:

- provision production Supabase/Auth0/Razorpay/Groq projects and rotate secrets
- confirm Supabase backups, point-in-time recovery, quotas, alerting, and Storage policies
- complete Razorpay sandbox/live contract tests with merchant credentials
- configure production DNS/TLS, WAF/rate limits, monitoring, paging, and retention
- obtain security/privacy review and Razorpay deployment approval
