# sl3dge Architecture Index

This document shows how the frontend, backend, database, Razorpay integration, MCP evidence boundary, and AI provider fit together. It distinguishes the current implementation from planned or optional architecture so it is not read as a production-readiness claim.

## System Connection

```mermaid
flowchart LR
    UI[Next.js frontend\nTypeScript + React] -->|HTTP JSON /api/v1| API[FastAPI backend\napp/main.py + api/router.py]
    API --> ING[Ingestion and normalization]
    API --> RZP[Razorpay integration\npayments, refunds, settlements, recon]
    RZP -->|official API| RAZORPAY[Razorpay]
    ING --> GRAPH[Financial event graph]
    RZP --> GRAPH
    GRAPH --> ENGINE[Deterministic control engine]
    ENGINE --> RESULTS[Expected vs actual\nPASS / VIOLATION / WARNING / UNRESOLVED]
    RESULTS --> CASES[Root causes, cases, lineage]
    CASES --> AGENT[LangGraph controller\n3 bounded workflows]
    AGENT --> AI[Structured provider abstraction]
    AI -->|optional Groq structured output| GROQ[Groq LLM]
    AGENT --> VERIFY[Deterministic verifier and backtests]
    VERIFY --> RESULTS
    API --> JOBS[Durable job queue]
    JOBS --> WORKER[Razorpay sync worker]
    WORKER --> RZP
    API --> REPO[Repository + SQLAlchemy]
    REPO --> DB[(PostgreSQL\nSupabase or local)]
    API --> STORAGE[Private Supabase Storage]
    STORAGE --> META[Artifact metadata]
    META --> DB
    API -. capability metadata only .-> MCP[MCP evidence boundary]
    MCP -. planned optional official Razorpay MCP .-> RAZORPAY
```

## Runtime Roles

### Frontend

The Next.js App Router UI is the presentation and interaction layer. The typed client in [frontend/src/lib/api.ts](frontend/src/lib/api.ts) sends requests to the FastAPI prefix `/api/v1` and maps responses into frontend types in [frontend/src/types/api.ts](frontend/src/types/api.ts).

It can request:

- Demo loading and run summaries
- Violations, root causes, cases, lineage, and payment graphs
- Agreement and control proposals
- Hypothesis generation and verification
- Razorpay connection and synchronization
- MCP capability status
- CSV source uploads

The browser does not query PostgreSQL or Supabase finance tables directly. FastAPI remains the application API and finance trust boundary.

### Backend

FastAPI is created in [backend/app/main.py](backend/app/main.py) and registers the API router from [backend/app/api/router.py](backend/app/api/router.py). Route handlers coordinate services; the financial decisions are made deeper in the application:

1. Source files or Razorpay records enter ingestion and mapping.
2. Canonical financial events and their relationships form a lifecycle graph.
3. The deterministic control engine calculates expected values and compares them with actual values.
4. Results become pass, violation, warning, or unresolved outcomes.
5. Root-cause and exception services organize verified findings.
6. LangGraph coordinates three bounded workflows using explicit state, branches,
   retries, checkpoints, traces, and human-approval stops.
7. Optional structured AI output proposes hypotheses or draft controls.
8. Deterministic verification and backtesting classify proposals independently.

The core financial pipeline works without an LLM. When Groq is configured the
graphs consume strict structured output; when it is unavailable they degrade to
bounded deterministic demo candidates without changing financial outcomes.

### Database and storage

The intended persistence path is:

```text
FastAPI -> SQLAlchemy repository -> PostgreSQL
                                      ^
                                      |
                         Supabase Postgres in deployment
```

The database implementation is in [backend/app/persistence/database.py](backend/app/persistence/database.py). `DATABASE_URL` selects PostgreSQL; when it is absent, development/demo services can use in-memory state. Alembic manages schema changes.

Current implementation status: production run, summary, violation, root-cause,
case, agreement/control-governance, sync-job, audit, and artifact paths are
repository-backed. The seeded NovaCart experience intentionally keeps a
process-local `DemoStore` read model for repeatable interactive presentation and
persists its canonical events, edges, controls, outcomes, violations, and root
causes when PostgreSQL is configured. Production route guards prevent live
merchant routes from falling back to seeded or process-local state.

Supabase Storage is separate from Postgres:

```text
Uploaded agreement/source/evidence bytes -> private Supabase Storage bucket
Artifact ID, bucket, path, checksum, type, size, provenance -> PostgreSQL
```

The upload flow is implemented by [backend/app/storage/service.py](backend/app/storage/service.py) and the source route in [backend/app/api/router.py](backend/app/api/router.py). The browser receives metadata or an object path, not privileged storage credentials.

## Razorpay and MCP

Razorpay synchronization uses the official API client and mapping modules in [backend/app/integrations/razorpay](backend/app/integrations/razorpay). The sync fetches payments, refunds, settlements, and reconciliation data, maps them into canonical events and edges, and persists them when PostgreSQL is configured.

MCP is an optional supplementary evidence boundary, represented by [backend/app/integrations/razorpay/mcp_evidence.py](backend/app/integrations/razorpay/mcp_evidence.py):

- It currently reports static capability metadata through `/api/v1/integrations/razorpay/mcp-evidence-capability`.
- The capability flag is enabled only when `RAZORPAY_MCP_ENABLED=true`.
- There is currently no MCP client call, remote evidence lookup, or MCP evidence persistence in this repository.
- A future implementation may add bounded read-only lookups against the official Razorpay MCP endpoint.
- It is not authoritative and cannot change controls, calculations, case status, or hypothesis verdicts.
- Direct Razorpay API ingestion remains the input of record.

## AI Boundary

The provider abstraction is in [backend/app/ai/provider.py](backend/app/ai/provider.py).
The development default is Groq `openai/gpt-oss-120b`; the API key is supplied
through `GROQ_API_KEY`. `ChatGroq.with_structured_output` produces strict
Pydantic results for the three graph workflows, with deterministic fallbacks
when the provider is not configured or fails.

AI may assist with:

- Agreement clause to candidate-control proposals
- Schema-mapping suggestions
- Root-cause hypotheses
- Human-readable evidence summaries
- Explanations of already-computed results

AI may not decide:

- Arithmetic truth
- Control pass/fail status
- Leakage or financial impact
- Precision/recall
- Ambiguous record matching
- Automatic approval of a financial control

The deterministic control and verification layers remain authoritative even when AI is configured. Without provider configuration, AI-only endpoints degrade explicitly while the core pipeline remains available.

## Current Integration Status

| Area | Current behavior | Boundary or limitation |
| --- | --- | --- |
| Frontend to backend | Typed Next.js client calls FastAPI `/api/v1` routes with OIDC access tokens | Seeded demo reads use the dedicated deterministic demo read model |
| Database | SQLAlchemy/Alembic repositories support local PostgreSQL and Supabase; production routes fail closed without it | Runtime identity, backups, quotas, and monitoring are deployment responsibilities |
| Controls | All five authoritative live controls run deterministically from approved, effective control versions | Merchant-specific approved controls must exist before a live run |
| Razorpay | GET-only, paginated, bounded ingestion through durable idempotent jobs and worker leases | Sandbox/live certification awaits Razorpay credentials |
| Supabase Storage | Backend-only private-object adapter stores bytes; PostgreSQL stores metadata and provenance | Bucket privacy, retention, and policies are deployment responsibilities |
| MCP | Capability metadata endpoint | No remote MCP invocation or evidence retrieval is implemented |
| AI | Groq structured-output adapter has been exercised with the configured demo model and has deterministic fallback | Model output is advisory and cannot establish financial truth |
| LangGraph | Three explicit graphs with checkpoints, bounded retries, deterministic verification, traces, and human gates | Production requires the checkpoint Postgres DSN |
| Identity/tenancy | Auth0 OIDC login, namespaced tenant/role claims, transaction tenant context, and forced RLS are implemented | Production tenant/role assignment remains an operator responsibility |

## Verification and Remaining Launch Gates

The configured development services have been exercised with the current code:

- Alembic reached revision `0010_manual_agreement_clauses` on Supabase.
- A temporary least-privilege runtime role proved cross-tenant read/update/insert
  isolation on every tenant-owned table, then was removed.
- Private Supabase Storage upload and exact-path compensation delete passed.
- Groq `openai/gpt-oss-120b` returned schema-valid structured output; removing
  its key leaves deterministic routes functional.
- Auth0 authorization-code/PKCE login and namespaced tenant/role claims reached
  the application successfully.
- The complete seeded load persisted its canonical graph and reproduced the
  exact manifest counts and stable IDs.

Remaining gates are external or environment-specific: Razorpay sandbox/live
contract tests need credentials; the deployment owner must configure Storage
policies, backups/PITR, quotas, alerts, DNS/TLS, rate limiting, retention, and
security/privacy approval. Docker images are built in CI, but this Windows host
does not have Docker for an additional local container smoke test.

## Is LangGraph Used?

**Yes, for three bounded workflows only.**

The root-cause investigation, mutation blind-spot remediation, and
agreement-to-control compiler are explicit LangGraph state machines. Production
uses Postgres checkpoints and durable final execution records. Deterministic
Python remains the only authority for financial calculations, graph matching,
backtests, and verdicts.

## Trust Boundary Summary

```text
Frontend
  -> FastAPI API
      -> deterministic domain and control logic  [authoritative]
      -> repository / PostgreSQL                  [durable records]
      -> private Supabase Storage                 [file bytes]
      -> Razorpay API                             [source integration]
      -> optional MCP evidence                    [supplementary only]
      -> LangGraph controller                     [bounded orchestration only]
          -> optional AI provider                 [proposal / explanation only]
          -> deterministic verifier               [authoritative verdict]
```

The central rule is: AI and MCP can add context, but only deterministic sl3dge
verification can establish financial truth. Repository-backed live read models
and the five-control suite are implemented. Razorpay credentialed contract
testing, optional real MCP evidence retrieval, and production account-level
operations remain launch gates.
