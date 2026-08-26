export type EvaluationStatus = "PASS" | "VIOLATION" | "WARNING" | "UNRESOLVED";

export interface DemoLoadResponse {
  run_id: string;
  name: string;
  counts: Record<string, number>;
  known_demo_ids: Record<string, string>;
  persistence_status: "IN_MEMORY" | "POSTGRES";
}

export interface SourceUploadResponse {
  upload_id: string;
  filename: string;
  row_count: number;
  columns: string[];
  decimal_values_checked: number;
  storage_status: "VALIDATED_ONLY" | "PRIVATE_STORAGE";
  object_path: string | null;
}

export interface RunSummary {
  id: string;
  name: string;
  status: string;
  transaction_count: number;
  event_count: number;
  relationship_count: number;
  control_evaluation_count: number;
  breakdown: { passed: number; violation: number; warning: number; unresolved: number };
  precision: string;
  recall: string;
  false_positive_rate: string;
  verified_leakage: string;
  cash_delayed: string;
  unresolved_count: number;
  processing_ms: number;
  evaluations_per_second: number;
}

export interface Violation {
  id: string;
  payment_id: string;
  category: string;
  expected: string;
  actual: string;
  financial_impact: string;
  status: EvaluationStatus;
}

export interface RootCause {
  id: string;
  title: string;
  category: string;
  affected_count: number;
  verified_impact: string;
  expected_value: string;
  observed_value: string;
  hypothesis: string | null;
  verification_status: string;
  primary_violation_count: number;
  downstream_effect_count: number;
}

export interface ExpectedActualResponse {
  payment_id: string;
  descriptor: string;
  amount: string;
  status: EvaluationStatus;
  rows: Array<{
    label: string;
    expected: string;
    actual: string | null;
    status: EvaluationStatus;
    difference: string;
  }>;
  verified_leakage: string;
  gateway_net: string;
  bank_credit: string | null;
  expected_net: string;
  applied_control_id: string;
  applied_control_version: number;
  applied_control_effective_period: string;
  evidence: Array<{
    title: string;
    control: string;
    calculation: string;
    expected: string | null;
    actual: string | null;
    difference: string | null;
    source: string;
    source_clause: string;
  }>;
}

export interface PaymentGraph {
  payment_id: string;
  nodes: Array<{
    id: string;
    kind: string;
    label: string;
    amount: string;
    status: EvaluationStatus;
    detail: string | null;
  }>;
}

export interface MutationTestSummary {
  id: string;
  source_run_id: string;
  status: string;
  mutation_count: number;
  detected_count: number;
  missed_count: number;
  mutation_detection_rate: string;
  false_positive_count: number;
  blind_spot_count: number;
  canonical_data_unchanged: boolean;
  coverage: Array<{
    mutation_type: string;
    injected: number;
    detected: number;
    detection_rate: string;
  }>;
  results: Array<{
    id: string;
    mutation_type: string;
    target_event_id: string;
    description: string;
    detected: boolean;
    expected_control_type: string;
    detected_by_control_types: string[];
    blind_spot_reason: string | null;
  }>;
}

export interface ControlBacktest {
  control_id: string;
  status: string;
  candidate_status: string;
  historical_false_positives: number;
  before: {
    detected_count: number;
    mutation_count: number;
    mutation_detection_rate: string;
    false_positive_count: number;
  };
  after: {
    detected_count: number;
    mutation_count: number;
    mutation_detection_rate: string;
    false_positive_count: number;
  };
  detection_rate_delta: string;
  false_positive_delta: number;
  newly_detected_mutation_ids: string[];
  canonical_data_unchanged: boolean;
}

export interface ViolationLineageResponse {
  payment_id: string;
  primary_violation_count: number;
  downstream_effect_count: number;
  nodes: Array<{
    id: string;
    category: string;
    lineage_type: "PRIMARY" | "DOWNSTREAM";
    parent_violation_id: string | null;
    root_violation_id: string;
    expected: string;
    actual: string;
    difference: string;
    financial_impact: string;
    causal_evidence: string;
  }>;
}

export interface CounterfactualSettlement {
  payment_id: string;
  actual: Record<"gross" | "mdr" | "gst" | "refunds" | "other_fees" | "net", string>;
  expected: Record<"gross" | "mdr" | "gst" | "refunds" | "other_fees" | "net", string>;
  difference: string;
  drivers: Array<{ type: string; amount: string }>;
}

export interface RazorpayConnectionStatus {
  configured: boolean;
  mode: string;
  connected: boolean;
  last_sync_status: string;
  last_synced_at: string | null;
}

export interface RazorpaySyncSummary {
  sync_id: string;
  status: string;
  payments_imported: number;
  refunds_imported: number;
  settlements_imported: number;
  reconciliation_records_imported: number;
  events_created: number;
  edges_created: number;
  synced_at: string;
}

export interface Control {
  id: string;
  name: string;
  control_type: string;
  expected: string;
  scope: string;
  source: string;
  source_clause: string;
  status: string;
  agreement_id: string;
  clause_id: string | null;
  logical_control_key: string;
  version: number;
  effective_from: string;
  effective_to: string | null;
  supersedes_control_id: string | null;
  parameters: Record<string, unknown>;
  conditions: string[];
  extraction_method: string;
  approved_at: string | null;
}

export interface AgreementClause {
  id: string;
  reference: string;
  page: number;
  heading: string;
  text: string;
  effective_from: string;
  effective_to: string | null;
}

export interface Agreement {
  id: string;
  merchant: string;
  title: string;
  status: string;
  effective_from: string;
  effective_to: string | null;
  source_type: string;
  content_hash: string;
  clauses: AgreementClause[];
}

export interface ControlProposal {
  id: string;
  agreement_id: string;
  clause_id: string;
  control_id: string;
  status: string;
  confidence: string;
  rationale: string;
  source_excerpt: string;
  extraction_method: string;
  proposed_control: Control;
}

export interface ControlCoverageSummary {
  run_id: string;
  total_material_edges: number;
  governed_edges: number;
  partially_governed_edges: number;
  ungoverned_edges: number;
  coverage_percentage: string;
  items: Array<{
    id: string;
    relationship: string;
    description: string;
    material_edge_count: number;
    governed_edge_count: number;
    status: "GOVERNED" | "PARTIALLY_GOVERNED" | "UNGOVERNED";
    control_ids: string[];
    blind_spot: string | null;
  }>;
}

export type ExceptionCaseStatus = "OPEN" | "VERIFIED" | "ESCALATED" | "RESOLVED";

export interface ExceptionCase {
  id: string;
  run_id: string;
  title: string;
  payment_id: string;
  primary_violation_id: string;
  violation_ids: string[];
  status: ExceptionCaseStatus;
  verified_impact: string;
  evidence: Array<{
    id: string;
    kind: string;
    title: string;
    summary: string;
    source_id: string;
    verified: boolean;
  }>;
  audit_trail: Array<{
    from_status: ExceptionCaseStatus | null;
    to_status: ExceptionCaseStatus;
    actor: string;
    note: string;
    occurred_at: string;
  }>;
  created_at: string;
  updated_at: string;
  resolution_note: string | null;
}

export interface UnresolvedMatch {
  id: string;
  payment_id: string;
  status: "UNRESOLVED";
  amount: string;
  settlement_id: string;
  missing_evidence: string;
  candidate_bank_references: string[];
  safe_conclusion: string;
}

export interface HypothesisResponse {
  root_cause_id: string;
  hypothesis: string;
  status: string;
}

export interface HypothesisVerification {
  root_cause_id: string;
  status: "PROVEN" | "REJECTED" | "UNRESOLVED";
  classification: string;
  checks: Array<{ label: string; value: string; result: string }>;
  conclusion: string;
}

export interface McpEvidenceCapability {
  enabled: boolean;
  authoritative: false;
  provider: string;
  allowed_tools: string[];
  prohibited_tool_classes: string[];
  result_policy: string;
}
