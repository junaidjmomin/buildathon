import type {
  Agreement,
  ControlBacktest,
  ControlCoverageSummary,
  ControlProposal,
  CounterfactualSettlement,
  DemoLoadResponse,
  ExceptionCase,
  ExpectedActualResponse,
  HypothesisResponse,
  HypothesisVerification,
  McpEvidenceCapability,
  MutationTestSummary,
  PaymentGraph,
  RootCause,
  RazorpayConnectionStatus,
  RazorpaySyncSummary,
  RunSummary,
  UnresolvedMatch,
  Violation,
  ViolationLineageResponse,
} from "@/types/api";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) throw new Error((await response.text()) || `Request failed: ${response.status}`);
  return response.json() as Promise<T>;
}

export const api = {
  loadDemo: () => request<DemoLoadResponse>("/demo/load", { method: "POST" }),
  summary: (runId: string) => request<RunSummary>(`/runs/${runId}/summary`),
  violations: (runId: string) => request<Violation[]>(`/runs/${runId}/violations`),
  rootCauses: (runId: string) => request<RootCause[]>(`/runs/${runId}/root-causes`),
  expectedActual: (runId: string, paymentId: string) =>
    request<ExpectedActualResponse>(`/runs/${runId}/payments/${paymentId}/expected-vs-actual`),
  paymentGraph: (runId: string, paymentId: string) =>
    request<PaymentGraph>(`/runs/${runId}/payments/${paymentId}/graph`),
  runMutationTest: (runId: string) =>
    request<MutationTestSummary>(`/runs/${runId}/mutation-tests`, { method: "POST" }),
  backtestControl: (controlId: string) =>
    request<ControlBacktest>(`/controls/${controlId}/backtest`, { method: "POST" }),
  approveControl: (controlId: string) =>
    request<{ id: string; status: string }>(`/controls/${controlId}/approve`, { method: "POST" }),
  lineage: (runId: string, paymentId: string) =>
    request<ViolationLineageResponse>(`/runs/${runId}/payments/${paymentId}/lineage`),
  counterfactual: (runId: string, paymentId: string) =>
    request<CounterfactualSettlement>(`/runs/${runId}/payments/${paymentId}/counterfactual`),
  agreements: () => request<Agreement[]>("/agreements"),
  agreementProposals: (agreementId: string) =>
    request<ControlProposal[]>(`/agreements/${agreementId}/control-proposals`),
  extractAgreementControls: (agreementId: string) =>
    request<ControlProposal[]>(`/agreements/${agreementId}/extract-controls`, { method: "POST" }),
  controlCoverage: (runId: string) =>
    request<ControlCoverageSummary>(`/runs/${runId}/control-coverage`),
  exceptionCases: (runId: string) =>
    request<ExceptionCase[]>(`/runs/${runId}/cases`),
  unresolvedMatches: (runId: string) =>
    request<UnresolvedMatch[]>(`/runs/${runId}/unresolved`),
  transitionCase: (caseId: string, action: "verify" | "escalate" | "resolve", note = "") =>
    request<ExceptionCase>(`/cases/${caseId}/${action}`, {
      method: "POST",
      body: JSON.stringify({ note }),
    }),
  rootCause: (rootCauseId: string) => request<RootCause>(`/root-causes/${rootCauseId}`),
  generateHypothesis: (rootCauseId: string) =>
    request<HypothesisResponse>(`/root-causes/${rootCauseId}/generate-hypothesis`, {
      method: "POST",
    }),
  verifyHypothesis: (rootCauseId: string) =>
    request<HypothesisVerification>(`/root-causes/${rootCauseId}/verify-hypothesis`, {
      method: "POST",
    }),
  razorpayStatus: () =>
    request<RazorpayConnectionStatus>("/integrations/razorpay/status"),
  syncRazorpay: () =>
    request<RazorpaySyncSummary>("/integrations/razorpay/sync", {
      method: "POST",
      body: JSON.stringify({ year: 2026, month: 8 }),
    }),
  razorpayMcpCapability: () =>
    request<McpEvidenceCapability>("/integrations/razorpay/mcp-evidence-capability"),
};
