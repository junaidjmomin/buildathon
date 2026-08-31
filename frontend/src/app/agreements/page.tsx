"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  CalendarRange,
  Check,
  FileCheck2,
  FileText,
  LoaderCircle,
  Plus,
  ScanText,
  ShieldCheck,
  UploadCloud,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Badge, ErrorState, PageHeader } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { formatPercent } from "@/lib/format";

export default function AgreementsPage() {
  const queryClient = useQueryClient();
  const [selectedAgreementId, setSelectedAgreementId] = useState<string | null>(null);
  const agreements = useQuery({ queryKey: ["agreements"], queryFn: api.agreements });
  const agreement =
    agreements.data?.find((item) => item.id === selectedAgreementId) ?? agreements.data?.[0];
  const proposals = useQuery({
    queryKey: ["agreement-proposals", agreement?.id],
    queryFn: () => api.agreementProposals(agreement!.id),
    enabled: Boolean(agreement),
  });
  const extract = useMutation({
    mutationFn: (agreementId: string) => api.extractAgreementControls(agreementId),
    onSuccess: (data, agreementId) =>
      queryClient.setQueryData(["agreement-proposals", agreementId], data),
  });
  const refreshProposals = () =>
    queryClient.invalidateQueries({ queryKey: ["agreement-proposals", agreement?.id] });
  const verify = useMutation({
    mutationFn: (proposalId: string) => api.verifyControlProposal(proposalId),
    onSuccess: refreshProposals,
  });
  const approve = useMutation({
    mutationFn: ({ proposalId, expectedVersion }: { proposalId: string; expectedVersion: number }) =>
      api.approveControlProposal(proposalId, expectedVersion),
    onSuccess: refreshProposals,
  });
  const upload = useMutation({
    mutationFn: api.uploadAgreement,
    onSuccess: (created) => {
      queryClient.setQueryData(
        ["agreements"],
        [created, ...(agreements.data ?? []).filter((item) => item.id !== created.id)],
      );
      queryClient.setQueryData(["agreement-proposals", created.id], []);
      setSelectedAgreementId(created.id);
      // A previous extraction attempt may have failed while the agreement was
      // still being persisted.  Do not carry that stale error into the now
      // successfully uploaded agreement view.
      extract.reset();
      verify.reset();
      approve.reset();
      extract.mutate(created.id);
    },
  });
  const addClause = useMutation({
    mutationFn: (payload: {
      reference: string;
      heading: string;
      text: string;
      effective_from?: string;
      effective_to?: string;
    }) => api.addAgreementClause(agreement!.id, payload),
    onSuccess: (created) => {
      queryClient.setQueryData(
        ["agreements"],
        agreements.data?.map((item) =>
          item.id === agreement?.id ? { ...item, clauses: [...item.clauses, created] } : item,
        ),
      );
      queryClient.invalidateQueries({ queryKey: ["agreement-proposals", agreement?.id] });
    },
  });

  if (agreements.isPending || (Boolean(agreement) && proposals.isPending)) {
    return (
      <div className="grid min-h-[calc(100vh-64px)] place-items-center">
        <LoaderCircle className="animate-spin text-[var(--evergreen)]" />
      </div>
    );
  }
  if (agreements.isError) {
    return (
      <main className="mx-auto max-w-3xl px-5 py-10 md:px-8">
        <ErrorState what="Agreements" onRetry={() => agreements.refetch()} />
      </main>
    );
  }
  if (!agreement) {
    return (
      <main className="mx-auto max-w-3xl px-5 py-10 md:px-8">
        <AgreementIntake upload={upload} />
      </main>
    );
  }
  if (proposals.isError || !proposals.data) {
    return (
      <main className="mx-auto max-w-3xl px-5 py-10 md:px-8">
        <ErrorState what="Agreement proposals" onRetry={() => proposals.refetch()} />
      </main>
    );
  }

  const clauses = new Map(agreement.clauses.map((clause) => [clause.id, clause]));
  const controlVersions = proposals.data.slice().sort((a, b) => {
    const keyOrder = a.proposed_control.logical_control_key.localeCompare(
      b.proposed_control.logical_control_key,
    );
    return keyOrder || a.proposed_control.version - b.proposed_control.version;
  });

  return (
    <main className="mx-auto max-w-[1320px] px-5 py-8 md:px-8 md:py-10">
      <section className="mb-7 flex flex-col justify-between gap-5 md:flex-row md:items-end">
        <PageHeader
          eyebrow={
            <>
              <FileCheck2 size={14} /> Contract control compiler
            </>
          }
          title="Turn clauses into governed controls"
          subtitle="Source text, extracted proposals, deterministic checks and explicit approval remain separate and inspectable."
        />
        <div className="flex w-full flex-col gap-3 md:w-auto md:items-end">
          {agreements.data && agreements.data.length > 1 ? (
            <label className="grid w-full gap-1.5 text-xs font-medium text-[var(--paper-dim)] md:w-72">
              Active agreement
              <select
                className="h-10 w-full rounded-lg border border-[var(--line)] bg-[var(--ink-800)] px-3 text-xs font-semibold text-[var(--paper)]"
                onChange={(event) => {
                  setSelectedAgreementId(event.currentTarget.value);
                  extract.reset();
                  verify.reset();
                  approve.reset();
                }}
                value={agreement.id}
              >
                {agreements.data.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.title} · {item.merchant}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <button
            onClick={() => extract.mutate(agreement.id)}
            disabled={extract.isPending}
            className="flex items-center justify-center gap-2 rounded-lg bg-[var(--evergreen)] px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[var(--evergreen-deep)] disabled:opacity-60"
            type="button"
          >
            {extract.isPending ? (
              <LoaderCircle size={15} className="animate-spin" />
            ) : (
              <ScanText size={15} />
            )}{" "}
            Extract structured controls
          </button>
        </div>
      </section>

      <AgreementIntake
        agreementId={agreement.id}
        agreementSourceType={agreement.source_type}
        addClause={addClause}
        upload={upload}
      />

      {extract.isError ? (
        <p
          role="alert"
          className="mb-5 rounded-lg border border-[var(--crimson-line)] bg-[var(--crimson-soft)] px-4 py-3 text-xs text-[var(--crimson-deep)]"
        >
          {extract.error.message}
        </p>
      ) : null}
      {verify.isError || approve.isError ? (
        <p
          role="alert"
          className="mb-5 rounded-lg border border-[var(--crimson-line)] bg-[var(--crimson-soft)] px-4 py-3 text-xs text-[var(--crimson-deep)]"
        >
          {(verify.error ?? approve.error)?.message}
        </p>
      ) : null}

      <section className="panel mb-6 mt-6 rounded-2xl p-5">
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
          <div className="flex items-start gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-lg bg-[var(--evergreen-soft)] text-[var(--evergreen)]">
              <FileText size={18} />
            </span>
            <div>
              <h2 className="text-sm font-semibold text-[var(--paper)]">
                <Link
                  href={`/agreements/${agreement.id}`}
                  className="transition-colors duration-150 hover:text-[var(--evergreen)] hover:underline"
                >
                  {agreement.title}
                </Link>
              </h2>
              <p className="mt-1 text-xs text-[var(--paper-dim)]">
                {agreement.merchant} · Effective {agreement.effective_from}
              </p>
            </div>
          </div>
          <Badge status="PASS" label={agreement.status} />
        </div>
        <div className="mt-4 grid gap-3 border-t border-[var(--line)] pt-4 text-[10px] text-[var(--paper-faint)] sm:grid-cols-3">
          <div>
            <span className="block uppercase tracking-[0.1em]">Source</span>
            <strong className="mt-1 block text-xs text-[var(--paper)]">
              {agreement.source_type === "SEEDED_TEXT" ? "Agreement Extraction" : agreement.source_type === "PDF_UPLOAD" ? "PDF Upload" : agreement.source_type}
            </strong>
          </div>
          <div>
            <span className="block uppercase tracking-[0.1em]">Clauses indexed</span>
            <strong className="number-tabular mt-1 block font-mono text-xs text-[var(--paper)]">
              {agreement.clauses.length}
            </strong>
          </div>
          <div>
            <span className="block uppercase tracking-[0.1em]">Content fingerprint</span>
            <strong className="mt-1 block truncate font-mono text-xs text-[var(--paper)]">
              {agreement.content_hash}
            </strong>
          </div>
        </div>
      </section>

      <section className="mb-6 grid gap-5 xl:grid-cols-[0.8fr_1.2fr]">
        <div className="panel overflow-hidden rounded-2xl">
          <div className="border-b border-[var(--line)] px-5 py-4">
            <h2 className="text-sm font-semibold text-[var(--paper)]">Agreement clauses</h2>
            <p className="mt-1 text-xs text-[var(--paper-dim)]">Exact source text and page provenance</p>
          </div>
          <div className="divide-y divide-[var(--line)]">
            {agreement.clauses.map((clause) => (
              <div key={clause.id} className="p-4">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--evergreen)]">
                    Clause {clause.clause_number ?? clause.reference} ·{" "}
                    {clause.source_type === "MANUAL_ENTRY" ? "Manual entry" : `Page ${clause.page}`}
                  </p>
                  <span className="font-mono text-[9px] text-[var(--paper-faint)]">
                    {clause.effective_from}
                  </span>
                </div>
                <h3 className="mt-1.5 text-xs font-semibold text-[var(--paper)]">
                  {clause.clause_title ?? clause.heading}
                </h3>
                <p className="mt-2 text-[11px] leading-5 text-[var(--paper-dim)]">{clause.text}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-3">
          <div className="flex items-end justify-between">
            <div>
              <h2 className="text-sm font-semibold text-[var(--paper)]">Structured control proposals</h2>
              <p className="mt-1 text-xs text-[var(--paper-dim)]">Every parameter points back to a clause</p>
            </div>
            <span className="number-tabular font-mono text-[10px] font-semibold text-[var(--evergreen)]">
              {proposals.data.length} extracted
            </span>
          </div>
          <p className="rounded-xl border border-[var(--line)] bg-[var(--ink-700)] px-4 py-3 text-[11px] leading-5 text-[var(--paper-dim)]">
            Deterministic verification is required first. Only a workspace admin can approve and activate a control.
          </p>
          {proposals.data.map((proposal) => {
            const control = proposal.proposed_control;
            const clause = clauses.get(proposal.clause_id);
            const isVerifying = verify.isPending && verify.variables === proposal.id;
            const isApproving = approve.isPending && approve.variables?.proposalId === proposal.id;
            const reviewable = proposal.status === "DRAFT" || proposal.status === "REVIEW_REQUIRED";
            const verificationPassed = proposal.verification_status === "PASSED";
            const needsReview = proposal.extraction_method === "DETERMINISTIC_CLAUSE_EXTRACTION";
            return (
              <div
                key={proposal.id}
                className={`rounded-xl border p-4 ${
                  proposal.status === "DRAFT"
                    ? "border-[var(--amber-line)] bg-[var(--amber-soft)]"
                    : "border-[var(--line)] bg-[var(--ink-800)]"
                }`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="font-mono text-[9px] font-bold uppercase tracking-[0.13em] text-[var(--paper-faint)]">
                      {control.logical_control_key} · v{control.version}
                    </p>
                    <h3 className="mt-1 text-sm font-semibold text-[var(--paper)]">{control.name}</h3>
                    <p className="mt-1 text-xs text-[var(--paper-dim)]">
                      {control.expected} · {control.scope}
                    </p>
                  </div>
                  {proposal.status === "APPROVED" ? (
                    <Badge status="PASS" label={proposal.status} />
                  ) : proposal.status === "REVIEW_REQUIRED" ? (
                    <Badge status="UNRESOLVED" label={proposal.status} />
                  ) : (
                    <Badge status={proposal.status as "DRAFT"} label={proposal.status} />
                  )}
                </div>
                <div className="mt-3 grid grid-cols-2 gap-3 rounded-lg bg-[var(--ink-700)] p-3 text-[10px]">
                  <div className="min-w-0">
                    <span className="text-[var(--paper-faint)]">Parameters</span>
                    <p className="mt-1 break-all font-mono font-semibold text-[var(--paper)]">
                      {JSON.stringify(control.parameters)}
                    </p>
                  </div>
                  <div className="min-w-0">
                    <span className="text-[var(--paper-faint)]">Applicability</span>
                    <p className="mt-1 break-words font-mono font-semibold text-[var(--paper)]">
                      {control.conditions.join(" · ")}
                    </p>
                  </div>
                </div>
                <div className="mt-3 flex items-center gap-2 text-[10px] text-[var(--paper-dim)]">
                  <span className="font-semibold text-[var(--evergreen)]">
                    Clause {clause?.clause_number ?? clause?.reference} · page {clause?.page}
                  </span>
                  <ArrowRight size={11} />
                  <span className="font-mono">{control.id}</span>
                  <span className="number-tabular ml-auto font-mono">
                    {needsReview
                      ? "Needs review"
                      : `${formatPercent(proposal.confidence, 0)} extraction confidence`}
                  </span>
                </div>
                <p className="mt-2 text-[10px] text-[var(--paper-faint)]">
                  Effective {control.effective_from} → {control.effective_to ?? "open"}
                </p>
                {proposal.validation_warnings?.length ? (
                  <div className="mt-2 rounded-lg border border-[var(--amber-line)] bg-[var(--amber-soft)] px-3 py-2 text-[10px] text-[var(--amber)]">
                    <p className="font-semibold">Extraction validation warnings</p>
                    <ul className="mt-1 list-disc space-y-0.5 pl-4">
                      {proposal.validation_warnings.map((warning) => (
                        <li key={warning}>{warning}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                <div className="mt-3 border-t border-[var(--line)] pt-3">
                  <div className="flex flex-wrap items-center justify-between gap-2 text-[10px]">
                    <span className="font-semibold text-[var(--paper-dim)]">
                      Deterministic verification:{" "}
                      <span
                        className={
                          verificationPassed
                            ? "text-[var(--evergreen)]"
                            : proposal.verification_status === "FAILED"
                              ? "text-[var(--crimson)]"
                              : "text-[var(--paper-faint)]"
                        }
                      >
                        {proposal.verification_status}
                      </span>
                    </span>
                    <span className="number-tabular font-mono text-[var(--paper-faint)]">
                      review v{proposal.version}
                    </span>
                  </div>
                  {proposal.verification_result ? (
                    <div className="mt-2 rounded-lg bg-[var(--ink-700)] px-3 py-2 text-[10px] text-[var(--paper-dim)]">
                      <p className="number-tabular font-mono">
                        {
                          proposal.verification_result.checks.filter(
                            (check) => check.status === "PASSED",
                          ).length
                        }
                        /{proposal.verification_result.checks.length} checks passed ·{" "}
                        {proposal.verification_result.detected_mutation_count}/
                        {proposal.verification_result.mutation_probe_count} mutations detected
                      </p>
                      <p className="mt-1 truncate font-mono text-[9px] text-[var(--paper-faint)]">
                        {proposal.verification_result.input_fingerprint}
                      </p>
                    </div>
                  ) : null}
                  {reviewable ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => verify.mutate(proposal.id)}
                        disabled={verify.isPending || approve.isPending}
                        className="flex items-center gap-1.5 rounded-lg border border-[var(--line-strong)] px-3 py-2 text-[10px] font-semibold text-[var(--evergreen)] transition-colors duration-150 hover:bg-[var(--ink-600)] disabled:opacity-50"
                      >
                        {isVerifying ? (
                          <LoaderCircle size={12} className="animate-spin" />
                        ) : (
                          <ShieldCheck size={12} />
                        )}{" "}
                        Verify deterministically
                      </button>
                      <button
                        type="button"
                        onClick={() =>
                          approve.mutate({ proposalId: proposal.id, expectedVersion: proposal.version })
                        }
                        disabled={!verificationPassed || verify.isPending || approve.isPending}
                        className="flex items-center gap-1.5 rounded-lg bg-[var(--evergreen)] px-3 py-2 text-[10px] font-semibold text-white transition-colors hover:bg-[var(--evergreen-deep)] disabled:opacity-40"
                      >
                        {isApproving ? (
                          <LoaderCircle size={12} className="animate-spin" />
                        ) : (
                          <Check size={12} />
                        )}{" "}
                        Admin approve control
                      </button>
                    </div>
                  ) : null}
                  {verificationPassed && reviewable ? (
                    <p className="mt-2 text-[9px] leading-4 text-[var(--paper-faint)]">
                      Maker-checker rule: approval must be completed by a different signed-in reviewer.
                    </p>
                  ) : null}
                  {proposal.status === "APPROVED" ? (
                    <p className="mt-2 text-[9px] text-[var(--evergreen)]">
                      Approved by {proposal.approved_by ?? "workspace admin"} with immutable source
                      provenance.
                    </p>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section className="rounded-2xl border border-[var(--line)] bg-[var(--ink-700)] p-5">
        <div className="flex items-center gap-2 text-sm font-semibold text-[var(--paper)]">
          <CalendarRange size={16} className="text-[var(--evergreen)]" /> Immutable control-version
          timeline
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {controlVersions.map((proposal) => {
            const control = proposal.proposed_control;
            return (
              <div
                key={control.id}
                className="rounded-xl border border-[var(--line)] bg-[var(--ink-800)] p-4"
              >
                <div className="flex justify-between gap-3">
                  <div>
                    <p className="text-[10px] uppercase tracking-[0.12em] text-[var(--paper-faint)]">
                      {control.logical_control_key.replaceAll("_", " ")} · version {control.version}
                    </p>
                    <p className="number-tabular mt-1 font-mono text-lg font-semibold text-[var(--paper)]">
                      {control.expected}
                    </p>
                  </div>
                  <Check size={16} className="text-[var(--evergreen)]" />
                </div>
                <p className="number-tabular mt-3 font-mono text-xs text-[var(--paper-dim)]">
                  {control.effective_from} → {control.effective_to ?? "open"}
                </p>
                <p className="mt-1 font-mono text-[10px] text-[var(--paper-faint)]">
                  {control.source_clause}
                </p>
              </div>
            );
          })}
        </div>
        <p className="mt-4 flex items-center gap-2 border-t border-[var(--line)] pt-4 text-[11px] text-[var(--paper-dim)]">
          <ShieldCheck size={14} className="text-[var(--evergreen)]" /> New amendments create a
          version; they never rewrite the control definition used by a completed run.
        </p>
      </section>
    </main>
  );
}

type IntakeMutation = {
  isPending: boolean;
  isError: boolean;
  error: Error | null;
  mutate: (formData: FormData) => void;
};

type ClauseMutation = {
  isPending: boolean;
  isError: boolean;
  isSuccess: boolean;
  error: Error | null;
  mutate: (payload: {
    reference: string;
    heading: string;
    text: string;
    effective_from?: string;
    effective_to?: string;
  }) => void;
};

function AgreementIntake({
  upload,
  agreementId,
  agreementSourceType,
  addClause,
}: {
  upload: IntakeMutation;
  agreementId?: string;
  agreementSourceType?: string;
  addClause?: ClauseMutation;
}) {
  const seededAgreement = agreementSourceType === "SEEDED_TEXT";
  const manualDisabled = !agreementId || seededAgreement;
  return (
    <section className="mb-6 grid gap-5 lg:grid-cols-2">
      <div className="panel rounded-2xl p-5 md:p-6">
        <div className="flex items-start gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-[var(--evergreen-soft)] text-[var(--evergreen)]">
            <UploadCloud size={19} />
          </span>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-[var(--evergreen)]">
              Agreement intake
            </p>
            <h2 className="mt-1 text-lg font-semibold text-[var(--paper)]">Upload agreement PDF</h2>
            <p className="mt-1 text-xs leading-5 text-[var(--paper-dim)]">
              Stored privately; pages and clause provenance are extracted automatically.
            </p>
          </div>
        </div>
        <form
          className="mt-5 grid gap-3 sm:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            if (!data.get("effective_to")) data.delete("effective_to");
            upload.mutate(data);
          }}
        >
          <label className="grid min-w-0 gap-1.5 text-xs font-medium text-[var(--paper-dim)]">
            Merchant name
            <input
              name="merchant"
              required
              maxLength={200}
              className="w-full min-w-0 rounded-xl border border-[var(--line)] bg-[var(--ink-700)] px-3 py-2.5 text-[var(--paper)] outline-none transition-colors duration-150 focus:border-[var(--evergreen)]"
            />
          </label>
          <label className="grid min-w-0 gap-1.5 text-xs font-medium text-[var(--paper-dim)]">
            Agreement title
            <input
              name="title"
              required
              maxLength={240}
              className="w-full min-w-0 rounded-xl border border-[var(--line)] bg-[var(--ink-700)] px-3 py-2.5 text-[var(--paper)] outline-none transition-colors duration-150 focus:border-[var(--evergreen)]"
            />
          </label>
          <label className="grid min-w-0 gap-1.5 text-xs font-medium text-[var(--paper-dim)]">
            Effective from
            <input
              name="effective_from"
              type="date"
              required
              className="w-full min-w-0 rounded-xl border border-[var(--line)] bg-[var(--ink-700)] px-3 py-2.5 text-[var(--paper)] outline-none transition-colors duration-150 focus:border-[var(--evergreen)]"
            />
          </label>
          <label className="grid min-w-0 gap-1.5 text-xs font-medium text-[var(--paper-dim)]">
            Effective to <span className="font-normal text-[var(--paper-faint)]">(optional)</span>
            <input
              name="effective_to"
              type="date"
              className="w-full min-w-0 rounded-xl border border-[var(--line)] bg-[var(--ink-700)] px-3 py-2.5 text-[var(--paper)] outline-none transition-colors duration-150 focus:border-[var(--evergreen)]"
            />
          </label>
          <label className="grid gap-1.5 text-xs font-medium text-[var(--paper-dim)] sm:col-span-2">
            PDF file
            <input
              name="file"
              type="file"
              accept="application/pdf,.pdf"
              required
              className="rounded-lg border border-dashed border-[var(--line-strong)] bg-[var(--ink-700)] px-3 py-4 text-xs text-[var(--paper-dim)] file:mr-3 file:rounded-md file:border-0 file:bg-[var(--evergreen-soft)] file:px-3 file:py-2 file:font-semibold file:text-[var(--evergreen)]"
            />
          </label>
          {upload.isError ? (
            <p role="alert" className="text-xs text-[var(--crimson)] sm:col-span-2">
              {upload.error?.message}
            </p>
          ) : null}
          <button
            type="submit"
            disabled={upload.isPending}
            className="flex items-center justify-center gap-2 rounded-lg bg-[var(--evergreen)] px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-[var(--evergreen-deep)] disabled:opacity-60 sm:col-span-2"
          >
            {upload.isPending ? (
              <LoaderCircle size={15} className="animate-spin" />
            ) : (
              <UploadCloud size={15} />
            )}{" "}
            Upload and ingest PDF
          </button>
        </form>
      </div>

      <div className="panel rounded-2xl p-5 md:p-6">
        <div className="flex items-start gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[var(--ink-600)] text-[var(--paper-dim)]">
            <Plus size={19} />
          </span>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-[var(--paper-dim)]">
              Clause registry
            </p>
            <h2 className="mt-1 text-lg font-semibold text-[var(--paper)]">Add clause manually</h2>
            <p className="mt-1 text-xs leading-5 text-[var(--paper-dim)]">
              For amendments or clauses that cannot be extracted reliably from a PDF.
            </p>
          </div>
        </div>
        {manualDisabled ? (
          <p className="mt-4 rounded-xl border border-[var(--line)] bg-[var(--ink-700)] px-3 py-2.5 text-[11px] leading-5 text-[var(--paper-dim)]">
            {"Upload an agreement PDF first; manual clauses must belong to an agreement."}
          </p>
        ) : null}
        <form
          className="mt-4 grid gap-3 sm:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (!addClause) return;
            const data = new FormData(event.currentTarget);
            const payload = {
              reference: String(data.get("reference") ?? ""),
              heading: String(data.get("heading") ?? ""),
              text: String(data.get("text") ?? ""),
              effective_from: String(data.get("effective_from") ?? "") || undefined,
              effective_to: String(data.get("effective_to") ?? "") || undefined,
            };
            addClause.mutate(payload);
          }}
        >
          <label className="grid min-w-0 gap-1.5 text-xs font-medium text-[var(--paper-dim)]">
            Reference
            <input
              name="reference"
              required
              disabled={manualDisabled}
              placeholder="e.g. 4.2(a)"
              className="w-full min-w-0 rounded-xl border border-[var(--line)] bg-[var(--ink-700)] px-3 py-2.5 text-[var(--paper)] outline-none transition-colors duration-150 focus:border-[var(--evergreen)] disabled:opacity-50"
            />
          </label>
          <label className="grid min-w-0 gap-1.5 text-xs font-medium text-[var(--paper-dim)]">
            Heading
            <input
              name="heading"
              required
              disabled={manualDisabled}
              placeholder="Domestic MDR"
              className="w-full min-w-0 rounded-xl border border-[var(--line)] bg-[var(--ink-700)] px-3 py-2.5 text-[var(--paper)] outline-none transition-colors duration-150 focus:border-[var(--evergreen)] disabled:opacity-50"
            />
          </label>
          <label className="grid min-w-0 gap-1.5 text-xs font-medium text-[var(--paper-dim)]">
            Effective from
            <input
              name="effective_from"
              type="date"
              disabled={manualDisabled}
              className="w-full min-w-0 rounded-xl border border-[var(--line)] bg-[var(--ink-700)] px-3 py-2.5 text-[var(--paper)] outline-none transition-colors duration-150 focus:border-[var(--evergreen)] disabled:opacity-50"
            />
          </label>
          <label className="grid min-w-0 gap-1.5 text-xs font-medium text-[var(--paper-dim)]">
            Effective to
            <input
              name="effective_to"
              type="date"
              disabled={manualDisabled}
              className="w-full min-w-0 rounded-xl border border-[var(--line)] bg-[var(--ink-700)] px-3 py-2.5 text-[var(--paper)] outline-none transition-colors duration-150 focus:border-[var(--evergreen)] disabled:opacity-50"
            />
          </label>
          <label className="grid min-w-0 gap-1.5 text-xs font-medium text-[var(--paper-dim)] sm:col-span-2">
            Clause text
            <textarea
              name="text"
              required
              disabled={manualDisabled}
              rows={4}
              className="w-full min-w-0 resize-y rounded-xl border border-[var(--line)] bg-[var(--ink-700)] px-3 py-2.5 text-[var(--paper)] outline-none transition-colors duration-150 focus:border-[var(--evergreen)] disabled:opacity-50"
            />
          </label>
          {addClause?.isError ? (
            <p role="alert" className="text-xs text-[var(--crimson)] sm:col-span-2">
              {addClause.error?.message}
            </p>
          ) : null}
          {addClause?.isSuccess ? (
            <p role="status" className="text-xs text-[var(--evergreen)] sm:col-span-2">
              Clause added with immutable audit provenance.
            </p>
          ) : null}
          <button
            type="submit"
            disabled={manualDisabled || addClause?.isPending}
            className="flex items-center justify-center gap-2 rounded-xl border border-[var(--line-strong)] px-4 py-3 text-sm font-semibold text-[var(--evergreen)] transition-colors duration-150 hover:bg-[var(--ink-600)] disabled:cursor-not-allowed disabled:opacity-45 sm:col-span-2"
          >
            {addClause?.isPending ? (
              <LoaderCircle size={15} className="animate-spin" />
            ) : (
              <Plus size={15} />
            )}{" "}
            Add clause
          </button>
        </form>
      </div>
    </section>
  );
}
