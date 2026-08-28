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

import { AppShell } from "@/components/app-shell";
import { api } from "@/lib/api";
import { formatPercent } from "@/lib/format";

const DEMO_MODE = process.env.NEXT_PUBLIC_APP_MODE !== "production";

export default function AgreementsPage() {
  const queryClient = useQueryClient();
  const agreements = useQuery({ queryKey: ["agreements"], queryFn: api.agreements });
  const agreement = agreements.data?.[0];
  const proposals = useQuery({
    queryKey: ["agreement-proposals", agreement?.id],
    queryFn: () => api.agreementProposals(agreement!.id),
    enabled: Boolean(agreement),
  });
  const extract = useMutation({
    mutationFn: () => api.extractAgreementControls(agreement!.id),
    onSuccess: (data) => queryClient.setQueryData(["agreement-proposals", agreement?.id], data),
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
      queryClient.setQueryData(["agreements"], [created]);
      queryClient.setQueryData(["agreement-proposals", created.id], []);
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
      <AppShell>
        <div className="grid min-h-[calc(100vh-64px)] place-items-center">
          <LoaderCircle className="animate-spin text-[#1e6b51]" />
        </div>
      </AppShell>
    );
  }
  if (agreements.isError) {
    return (
      <AppShell>
        <main className="mx-auto max-w-3xl px-5 py-10 md:px-8">
          <div className="panel rounded-2xl p-8 text-sm text-[#a43d32]" role="alert">
            Agreements could not be loaded.{" "}
            <button type="button" onClick={() => agreements.refetch()} className="font-semibold underline">
              Retry
            </button>
          </div>
        </main>
      </AppShell>
    );
  }
  if (!agreement) {
    return (
      <AppShell>
        <main className="mx-auto max-w-3xl px-5 py-10 md:px-8">
          <AgreementIntake upload={upload} />
        </main>
      </AppShell>
    );
  }
  if (proposals.isError || !proposals.data) {
    return (
      <AppShell>
        <main className="mx-auto max-w-3xl px-5 py-10 md:px-8">
          <div className="panel rounded-2xl p-8 text-sm text-[#a43d32]" role="alert">
            Agreement proposals could not be loaded.{" "}
            <button type="button" onClick={() => proposals.refetch()} className="font-semibold underline">
              Retry
            </button>
          </div>
        </main>
      </AppShell>
    );
  }

  const clauses = new Map(agreement.clauses.map((clause) => [clause.id, clause]));
  const mdrVersions = proposals.data
    .filter((proposal) => proposal.proposed_control.logical_control_key === "DOMESTIC_CARD_MDR")
    .sort((a, b) => a.proposed_control.version - b.proposed_control.version);

  return (
    <AppShell>
      <main className="mx-auto max-w-[1320px] px-5 py-8 md:px-8 md:py-10">
        <section className="mb-7 flex flex-col justify-between gap-5 md:flex-row md:items-end">
          <div>
            <p className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#1e6b51]"><FileCheck2 size={14} /> Contract control compiler</p>
            <h1 className="text-3xl font-semibold tracking-[-0.035em]">Clause to executable control</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-[#66716b]">The model proposes structure. Source clauses, effective dates and explicit approval remain inspectable.</p>
          </div>
          <button onClick={() => extract.mutate()} disabled={extract.isPending} className="flex items-center gap-2 rounded-xl bg-[#112a2b] px-4 py-3 text-sm font-medium text-white disabled:opacity-60">
            {extract.isPending ? <LoaderCircle size={15} className="animate-spin" /> : <ScanText size={15} />} Extract structured controls
          </button>
        </section>

        <AgreementIntake
          agreementId={agreement.id}
          addClause={addClause}
          upload={upload}
        />

        {extract.isError ? <p role="alert" className="mb-5 rounded-xl border border-[#efc6b3] bg-[#fff7f2] px-4 py-3 text-xs text-[#a9431f]">{extract.error.message}</p> : null}
        {verify.isError || approve.isError ? <p role="alert" className="mb-5 rounded-xl border border-[#efc6b3] bg-[#fff7f2] px-4 py-3 text-xs text-[#a9431f]">{(verify.error ?? approve.error)?.message}</p> : null}

        <section className="panel mb-6 mt-6 rounded-2xl p-5">
          <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
            <div className="flex items-start gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-[#e5f2eb] text-[#1e6b51]"><FileText size={18} /></span><div><h2 className="text-sm font-semibold"><Link href={`/agreements/${agreement.id}`} className="hover:underline">{agreement.title}</Link></h2><p className="mt-1 text-xs text-[#6c7771]">{agreement.merchant} · Effective {agreement.effective_from}</p></div></div>
            <span className="w-fit rounded-full bg-[#dff2e8] px-2.5 py-1 text-[10px] font-bold text-[#1e6b51]">{agreement.status}</span>
          </div>
          <div className="mt-4 grid gap-3 border-t border-[#e4e8e2] pt-4 text-[10px] text-[#6d7872] sm:grid-cols-3"><div><span className="block uppercase tracking-[0.1em]">Source</span><strong className="mt-1 block text-xs text-[#202b26]">{agreement.source_type}</strong></div><div><span className="block uppercase tracking-[0.1em]">Clauses indexed</span><strong className="mt-1 block text-xs text-[#202b26]">{agreement.clauses.length}</strong></div><div><span className="block uppercase tracking-[0.1em]">Content fingerprint</span><strong className="mt-1 block truncate font-mono text-xs text-[#202b26]">{agreement.content_hash}</strong></div></div>
        </section>

        <section className="mb-6 grid gap-5 xl:grid-cols-[0.8fr_1.2fr]">
          <div className="panel overflow-hidden rounded-2xl">
            <div className="border-b border-[#e2e5df] px-5 py-4"><h2 className="text-sm font-semibold">Agreement clauses</h2><p className="mt-1 text-xs text-[#78827d]">Exact source text and page provenance</p></div>
            <div className="divide-y divide-[#e8ebe6]">{agreement.clauses.map((clause) => <div key={clause.id} className="p-4"><div className="flex items-center justify-between gap-3"><p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[#1e6b51]">Clause {clause.reference} · {clause.source_type === "MANUAL_ENTRY" ? "Manual entry" : `Page ${clause.page}`}</p><span className="text-[9px] text-[#7a847e]">{clause.effective_from}</span></div><h3 className="mt-1.5 text-xs font-semibold">{clause.heading}</h3><p className="mt-2 text-[11px] leading-5 text-[#66716b]">{clause.text}</p></div>)}</div>
          </div>

          <div className="space-y-3">
            <div className="flex items-end justify-between"><div><h2 className="text-sm font-semibold">Structured control proposals</h2><p className="mt-1 text-xs text-[#78827d]">Every parameter points back to a clause</p></div><span className="text-[10px] font-semibold text-[#1e6b51]">{proposals.data.length} extracted</span></div>
            {DEMO_MODE ? <p className="rounded-xl border border-[#dce4dd] bg-[#f6f8f5] px-4 py-3 text-[11px] leading-5 text-[#66716b]">Verification and maker-checker approval are enabled for durable production proposals. Seeded demo controls remain read-only.</p> : null}
            {proposals.data.map((proposal) => {
              const control = proposal.proposed_control;
              const clause = clauses.get(proposal.clause_id);
              const isVerifying = verify.isPending && verify.variables === proposal.id;
              const isApproving = approve.isPending && approve.variables?.proposalId === proposal.id;
              const reviewable = proposal.status === "DRAFT" || proposal.status === "REVIEW_REQUIRED";
              const verificationPassed = proposal.verification_status === "PASSED";
              return <div key={proposal.id} className={`rounded-xl border p-4 ${proposal.status === "DRAFT" ? "border-[#efc6b3] bg-[#fff8f4]" : "border-[#dbe3dc] bg-white"}`}>
                <div className="flex items-start justify-between gap-4"><div><p className="text-[9px] font-bold uppercase tracking-[0.13em] text-[#68746d]">{control.logical_control_key} · v{control.version}</p><h3 className="mt-1 text-sm font-semibold">{control.name}</h3><p className="mt-1 text-xs text-[#66716b]">{control.expected} · {control.scope}</p></div><span className={`rounded-full px-2 py-1 text-[9px] font-bold ${proposal.status === "APPROVED" ? "bg-[#dff2e8] text-[#1e6b51]" : "bg-[#ffe5d8] text-[#bd4e24]"}`}>{proposal.status}</span></div>
                <div className="mt-3 grid gap-3 rounded-lg bg-[#f5f7f3] p-3 text-[10px] sm:grid-cols-2"><div><span className="text-[#7a847e]">Parameters</span><p className="mt-1 font-mono font-semibold">{JSON.stringify(control.parameters)}</p></div><div><span className="text-[#7a847e]">Applicability</span><p className="mt-1 font-mono font-semibold">{control.conditions.join(" · ")}</p></div></div>
                <div className="mt-3 flex items-center gap-2 text-[10px] text-[#65716b]"><span className="font-semibold text-[#1e6b51]">Clause {clause?.reference}</span><ArrowRight size={11} /><span>{control.id}</span><span className="ml-auto">{formatPercent(proposal.confidence, 0)} extraction confidence</span></div>
                <div className="mt-3 border-t border-[#e1e6e0] pt-3">
                  <div className="flex flex-wrap items-center justify-between gap-2 text-[10px]"><span className="font-semibold">Deterministic verification: <span className={verificationPassed ? "text-[#1e6b51]" : proposal.verification_status === "FAILED" ? "text-[#b34a25]" : "text-[#77817b]"}>{proposal.verification_status}</span></span><span className="font-mono text-[#7a847e]">review v{proposal.version}</span></div>
                  {proposal.verification_result ? <div className="mt-2 rounded-lg bg-white/70 px-3 py-2 text-[10px] text-[#65716b]"><p>{proposal.verification_result.checks.filter((check) => check.status === "PASSED").length}/{proposal.verification_result.checks.length} checks passed · {proposal.verification_result.detected_mutation_count}/{proposal.verification_result.mutation_probe_count} mutations detected</p><p className="mt-1 truncate font-mono text-[9px] text-[#849089]">{proposal.verification_result.input_fingerprint}</p></div> : null}
                  {!DEMO_MODE && reviewable ? <div className="mt-3 flex flex-wrap gap-2"><button type="button" onClick={() => verify.mutate(proposal.id)} disabled={verify.isPending || approve.isPending} className="flex items-center gap-1.5 rounded-lg border border-[#b8c9bc] bg-white px-3 py-2 text-[10px] font-semibold text-[#1e6b51] disabled:opacity-50">{isVerifying ? <LoaderCircle size={12} className="animate-spin" /> : <ShieldCheck size={12} />} Verify deterministically</button><button type="button" onClick={() => approve.mutate({ proposalId: proposal.id, expectedVersion: proposal.version })} disabled={!verificationPassed || verify.isPending || approve.isPending} className="flex items-center gap-1.5 rounded-lg bg-[#112a2b] px-3 py-2 text-[10px] font-semibold text-white disabled:opacity-40">{isApproving ? <LoaderCircle size={12} className="animate-spin" /> : <Check size={12} />} Approve control</button></div> : null}
                  {!DEMO_MODE && verificationPassed && reviewable ? <p className="mt-2 text-[9px] leading-4 text-[#7a847e]">Maker-checker rule: approval must be completed by a different signed-in reviewer.</p> : null}
                  {proposal.status === "APPROVED" ? <p className="mt-2 text-[9px] text-[#1e6b51]">Approved by {proposal.approved_by ?? "authorized reviewer"} with immutable source provenance.</p> : null}
                </div>
              </div>;
            })}
          </div>
        </section>

        <section className="rounded-2xl bg-[#112a2b] p-5 text-white">
          <div className="flex items-center gap-2 text-sm font-semibold"><CalendarRange size={16} className="text-[#9bd0b7]" /> Immutable control-version timeline</div>
          <div className="mt-4 grid gap-3 md:grid-cols-2">{mdrVersions.map((proposal) => { const control = proposal.proposed_control; return <div key={control.id} className="rounded-xl border border-white/10 bg-white/[0.06] p-4"><div className="flex justify-between gap-3"><div><p className="text-[10px] uppercase tracking-[0.12em] text-white/45">Version {control.version}</p><p className="mt-1 text-lg font-semibold">{control.expected}</p></div><Check size={16} className="text-[#95d6b8]" /></div><p className="mt-3 text-xs text-white/58">{control.effective_from} → {control.effective_to ?? "open"}</p><p className="mt-1 text-[10px] text-white/38">{control.source_clause}</p></div>; })}</div>
          <p className="mt-4 flex items-center gap-2 border-t border-white/10 pt-4 text-[11px] text-white/50"><ShieldCheck size={14} className="text-[#95d6b8]" /> Completed August runs continue to use v1; the September amendment creates v2 instead of rewriting history.</p>
        </section>
      </main>
    </AppShell>
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
  addClause,
}: {
  upload: IntakeMutation;
  agreementId?: string;
  addClause?: ClauseMutation;
}) {
  const seededAgreement = DEMO_MODE && agreementId === "AGR_NOVACART_2026";
  const manualDisabled = !agreementId || seededAgreement;
  return (
    <section className="mb-6 grid gap-5 lg:grid-cols-2">
      <div className="panel rounded-2xl p-5 md:p-6">
        <div className="flex items-start gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#e5f2eb] text-[#1e6b51]"><UploadCloud size={19} /></span>
          <div><p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-[#1e6b51]">Agreement intake</p><h2 className="mt-1 text-lg font-semibold">Upload agreement PDF</h2><p className="mt-1 text-xs leading-5 text-[#66716b]">Stored privately; pages and clause provenance are extracted automatically.</p></div>
        </div>
        <form className="mt-5 grid gap-3 sm:grid-cols-2" onSubmit={(event) => { event.preventDefault(); const data = new FormData(event.currentTarget); if (!data.get("effective_to")) data.delete("effective_to"); upload.mutate(data); }}>
          <label className="grid min-w-0 gap-1.5 text-xs font-medium">Merchant name<input name="merchant" required maxLength={200} className="w-full min-w-0 rounded-xl border border-[#dfe4de] bg-white px-3 py-2.5 outline-none focus:border-[#1e6b51]" /></label>
          <label className="grid min-w-0 gap-1.5 text-xs font-medium">Agreement title<input name="title" required maxLength={240} className="w-full min-w-0 rounded-xl border border-[#dfe4de] bg-white px-3 py-2.5 outline-none focus:border-[#1e6b51]" /></label>
          <label className="grid min-w-0 gap-1.5 text-xs font-medium">Effective from<input name="effective_from" type="date" required className="w-full min-w-0 rounded-xl border border-[#dfe4de] bg-white px-3 py-2.5 outline-none focus:border-[#1e6b51]" /></label>
          <label className="grid min-w-0 gap-1.5 text-xs font-medium">Effective to <span className="font-normal text-[#7b857f]">(optional)</span><input name="effective_to" type="date" className="w-full min-w-0 rounded-xl border border-[#dfe4de] bg-white px-3 py-2.5 outline-none focus:border-[#1e6b51]" /></label>
          <label className="grid gap-1.5 text-xs font-medium sm:col-span-2">PDF file<input name="file" type="file" accept="application/pdf,.pdf" required className="rounded-xl border border-dashed border-[#cfd8d1] bg-[#f8faf7] px-3 py-4 text-xs file:mr-3 file:rounded-lg file:border-0 file:bg-[#e5f2eb] file:px-3 file:py-2 file:font-semibold file:text-[#1e6b51]" /></label>
          {upload.isError ? <p role="alert" className="text-xs text-[#b34a25] sm:col-span-2">{upload.error?.message}</p> : null}
          <button type="submit" disabled={upload.isPending} className="flex items-center justify-center gap-2 rounded-xl bg-[#112a2b] px-4 py-3 text-sm font-medium text-white disabled:opacity-60 sm:col-span-2">{upload.isPending ? <LoaderCircle size={15} className="animate-spin" /> : <UploadCloud size={15} />} Upload and extract PDF</button>
        </form>
      </div>

      <div className="panel rounded-2xl p-5 md:p-6">
        <div className="flex items-start gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#eef0eb] text-[#52615a]"><Plus size={19} /></span>
          <div><p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-[#52615a]">Clause registry</p><h2 className="mt-1 text-lg font-semibold">Add clause manually</h2><p className="mt-1 text-xs leading-5 text-[#66716b]">For amendments or clauses that cannot be extracted reliably from a PDF.</p></div>
        </div>
        {manualDisabled ? <p className="mt-4 rounded-xl border border-[#e0e4de] bg-[#f7f8f5] px-3 py-2.5 text-[11px] leading-5 text-[#66716b]">{seededAgreement ? "The seeded agreement is immutable. Upload your PDF first; the newly uploaded agreement will support manual clauses immediately." : "Upload an agreement PDF first; manual clauses must belong to an agreement."}</p> : null}
        <form className="mt-4 grid gap-3 sm:grid-cols-2" onSubmit={(event) => { event.preventDefault(); if (!addClause) return; const data = new FormData(event.currentTarget); const payload = { reference: String(data.get("reference") ?? ""), heading: String(data.get("heading") ?? ""), text: String(data.get("text") ?? ""), effective_from: String(data.get("effective_from") ?? "") || undefined, effective_to: String(data.get("effective_to") ?? "") || undefined }; addClause.mutate(payload); }}>
          <label className="grid min-w-0 gap-1.5 text-xs font-medium">Reference<input name="reference" required disabled={manualDisabled} placeholder="e.g. 4.2(a)" className="w-full min-w-0 rounded-xl border border-[#dfe4de] bg-white px-3 py-2.5 disabled:bg-[#f1f3ef]" /></label>
          <label className="grid min-w-0 gap-1.5 text-xs font-medium">Heading<input name="heading" required disabled={manualDisabled} placeholder="Domestic MDR" className="w-full min-w-0 rounded-xl border border-[#dfe4de] bg-white px-3 py-2.5 disabled:bg-[#f1f3ef]" /></label>
          <label className="grid min-w-0 gap-1.5 text-xs font-medium">Effective from<input name="effective_from" type="date" disabled={manualDisabled} className="w-full min-w-0 rounded-xl border border-[#dfe4de] bg-white px-3 py-2.5 disabled:bg-[#f1f3ef]" /></label>
          <label className="grid min-w-0 gap-1.5 text-xs font-medium">Effective to<input name="effective_to" type="date" disabled={manualDisabled} className="w-full min-w-0 rounded-xl border border-[#dfe4de] bg-white px-3 py-2.5 disabled:bg-[#f1f3ef]" /></label>
          <label className="grid min-w-0 gap-1.5 text-xs font-medium sm:col-span-2">Clause text<textarea name="text" required disabled={manualDisabled} rows={4} className="w-full min-w-0 resize-y rounded-xl border border-[#dfe4de] bg-white px-3 py-2.5 disabled:bg-[#f1f3ef]" /></label>
          {addClause?.isError ? <p role="alert" className="text-xs text-[#b34a25] sm:col-span-2">{addClause.error?.message}</p> : null}
          {addClause?.isSuccess ? <p role="status" className="text-xs text-[#1e6b51] sm:col-span-2">Clause added with immutable audit provenance.</p> : null}
          <button type="submit" disabled={manualDisabled || addClause?.isPending} className="flex items-center justify-center gap-2 rounded-xl border border-[#b8c9bc] bg-white px-4 py-3 text-sm font-semibold text-[#1e6b51] disabled:cursor-not-allowed disabled:opacity-45 sm:col-span-2">{addClause?.isPending ? <LoaderCircle size={15} className="animate-spin" /> : <Plus size={15} />} Add clause</button>
        </form>
      </div>
    </section>
  );
}
