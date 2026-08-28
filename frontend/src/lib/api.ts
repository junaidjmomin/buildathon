import type {
  Agreement,
  AgreementClause,
  AgreementClauseCreate,
  BackgroundJob,
  Control,
  ControlBacktest,
  ControlCoverageSummary,
  ControlProposal,
  ControlProposalVerification,
  CounterfactualSettlement,
  DemoLoadResponse,
  ExceptionCase,
  ExpectedActualResponse,
  HypothesisResponse,
  HypothesisVerification,
  InvestigationExecution,
  JobSubmission,
  McpEvidenceCapability,
  MutationTestSummary,
  PaymentGraph,
  RootCause,
  RazorpayConnectionStatus,
  RazorpaySyncSummary,
  RunSummary,
  RunListItem,
  SourceUploadResponse,
  SourceUploadBatchResponse,
  SourceRunResponse,
  UnresolvedMatch,
  Violation,
  ViolationLineageResponse,
} from "@/types/api";
import { getAccessToken, isOidcEnabled } from "@/lib/auth-client";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
const REQUEST_TIMEOUT_MS = 15_000;
const segment = (value: string) => encodeURIComponent(value);

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly requestId: string | null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  init?: RequestInit,
  timeoutMs = REQUEST_TIMEOUT_MS,
): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (!(init?.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const accessToken = await getAccessToken();
  if (isOidcEnabled() && !accessToken) {
    throw new ApiError("Your session has expired. Sign in again to continue.", 401, null);
  }
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  init?.signal?.addEventListener("abort", () => controller.abort(), { once: true });
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      credentials: "include",
      headers,
      signal: controller.signal,
    });
  } catch (error) {
    if (controller.signal.aborted) {
      throw new ApiError("The API request timed out. Retry when the service is available.", 0, null);
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
  if (!response.ok) {
    const contentType = response.headers.get("content-type") ?? "";
    const payload = contentType.includes("application/json")
      ? await response.json()
      : await response.text();
    const message =
      typeof payload === "string"
        ? payload
        : payload.detail ?? payload.error?.message ?? `Request failed: ${response.status}`;
    throw new ApiError(message, response.status, response.headers.get("x-request-id"));
  }
  return response.json() as Promise<T>;
}

export const api = {
  loadDemo: () => request<DemoLoadResponse>("/demo/load", { method: "POST" }, 60_000),
  runs: () => request<RunListItem[]>("/runs"),
  summary: (runId: string) => request<RunSummary>(`/runs/${segment(runId)}/summary`),
  violations: (runId: string) => request<Violation[]>(`/runs/${segment(runId)}/violations`),
  rootCauses: (runId: string) => request<RootCause[]>(`/runs/${segment(runId)}/root-causes`),
  expectedActual: (runId: string, paymentId: string) =>
    request<ExpectedActualResponse>(`/runs/${segment(runId)}/payments/${segment(paymentId)}/expected-vs-actual`),
  paymentGraph: (runId: string, paymentId: string) =>
    request<PaymentGraph>(`/runs/${segment(runId)}/payments/${segment(paymentId)}/graph`),
  runMutationTest: (runId: string) =>
    request<MutationTestSummary>(`/runs/${segment(runId)}/mutation-tests`, { method: "POST" }),
  backtestControl: (controlId: string) =>
    request<ControlBacktest>(`/controls/${segment(controlId)}/backtest`, { method: "POST" }),
  approveControl: (controlId: string) =>
    request<{ id: string; status: string }>(`/controls/${segment(controlId)}/approve`, { method: "POST" }),
  controls: () => request<Control[]>("/controls"),
  controlVersions: (logicalControlKey: string) =>
    request<Control[]>(`/controls/${segment(logicalControlKey)}/versions`),
  lineage: (runId: string, paymentId: string) =>
    request<ViolationLineageResponse>(`/runs/${segment(runId)}/payments/${segment(paymentId)}/lineage`),
  counterfactual: (runId: string, paymentId: string) =>
    request<CounterfactualSettlement>(`/runs/${segment(runId)}/payments/${segment(paymentId)}/counterfactual`),
  agreements: () => request<Agreement[]>("/agreements"),
  agreement: (agreementId: string) => request<Agreement>(`/agreements/${segment(agreementId)}`),
  uploadAgreement: (formData: FormData) =>
    request<Agreement>(
      "/agreements/upload",
      { method: "POST", body: formData },
      60_000,
    ),
  addAgreementClause: (agreementId: string, clause: AgreementClauseCreate) =>
    request<AgreementClause>(`/agreements/${segment(agreementId)}/clauses`, {
      method: "POST",
      body: JSON.stringify(clause),
    }),
  agreementProposals: (agreementId: string) =>
    request<ControlProposal[]>(`/agreements/${segment(agreementId)}/control-proposals`),
  extractAgreementControls: (agreementId: string) =>
    request<ControlProposal[]>(
      `/agreements/${segment(agreementId)}/extract-controls`,
      { method: "POST" },
      60_000,
    ),
  verifyControlProposal: (proposalId: string) =>
    request<ControlProposalVerification>(
      `/control-proposals/${segment(proposalId)}/verify`,
      { method: "POST" },
      60_000,
    ),
  approveControlProposal: (proposalId: string, expectedVersion: number) =>
    request<Control>(`/control-proposals/${segment(proposalId)}/approve`, {
      method: "POST",
      body: JSON.stringify({ expected_version: expectedVersion }),
    }),
  controlCoverage: (runId: string) =>
    request<ControlCoverageSummary>(`/runs/${segment(runId)}/control-coverage`),
  exceptionCases: (runId: string) =>
    request<ExceptionCase[]>(`/runs/${segment(runId)}/cases`),
  unresolvedMatches: (runId: string) =>
    request<UnresolvedMatch[]>(`/runs/${segment(runId)}/unresolved`),
  transitionCase: (
    caseId: string,
    action: "verify" | "escalate" | "resolve",
    note = "",
    expectedVersion?: number,
  ) =>
    request<ExceptionCase>(`/cases/${segment(caseId)}/${action}`, {
      method: "POST",
      body: JSON.stringify({ note, expected_version: expectedVersion }),
    }),
  rootCause: (rootCauseId: string) => request<RootCause>(`/root-causes/${segment(rootCauseId)}`),
  generateHypothesis: (rootCauseId: string) =>
    request<HypothesisResponse>(`/root-causes/${segment(rootCauseId)}/generate-hypothesis`, {
      method: "POST",
    }),
  verifyHypothesis: (rootCauseId: string) =>
    request<HypothesisVerification>(`/root-causes/${segment(rootCauseId)}/verify-hypothesis`, {
      method: "POST",
    }),
  investigateRootCause: (rootCauseId: string) =>
    request<InvestigationExecution>(`/root-causes/${segment(rootCauseId)}/investigate`, {
      method: "POST",
    }),
  razorpayStatus: () =>
    request<RazorpayConnectionStatus>("/integrations/razorpay/status"),
  syncRazorpay: () =>
    request<RazorpaySyncSummary>("/integrations/razorpay/sync", {
      method: "POST",
      body: JSON.stringify({ year: 2026, month: 8 }),
    }),
  submitRazorpaySyncJob: (idempotencyKey: string) =>
    request<JobSubmission>("/integrations/razorpay/sync-jobs", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({ year: 2026, month: 8 }),
    }),
  backgroundJob: (jobId: string) => request<BackgroundJob>(`/jobs/${segment(jobId)}`),
  razorpayMcpCapability: () =>
    request<McpEvidenceCapability>("/integrations/razorpay/mcp-evidence-capability"),
  uploadSource: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<SourceUploadResponse>("/sources/upload", { method: "POST", body });
  },
  uploadSources: (files: File[]) => {
    const body = new FormData();
    files.forEach((file) => body.append("files", file));
    return request<SourceUploadBatchResponse>("/sources/uploads", { method: "POST", body }, 120_000);
  },
  createRunFromUploads: (files: File[], uploadIds: string[], name?: string) => {
    const body = new FormData();
    files.forEach((file) => body.append("files", file));
    uploadIds.forEach((uploadId) => body.append("upload_ids", uploadId));
    if (name?.trim()) body.append("name", name.trim());
    return request<SourceRunResponse>(
      "/runs/from-uploads",
      { method: "POST", body },
      120_000,
    );
  },
};
