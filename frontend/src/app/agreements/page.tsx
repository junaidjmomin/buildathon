"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  CalendarRange,
  Check,
  FileCheck2,
  FileText,
  LoaderCircle,
  ScanText,
  ShieldCheck,
  UploadCloud,
} from "lucide-react";

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
  const upload = useMutation({
    mutationFn: api.uploadAgreement,
    onSuccess: (created) => {
      queryClient.setQueryData(["agreements"], [created]);
      queryClient.setQueryData(["agreement-proposals", created.id], []);
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
  if (!agreement) {
    return (
      <AppShell>
        <main className="mx-auto max-w-3xl px-5 py-10 md:px-8">
          <section className="panel rounded-2xl p-6 md:p-8">
            <div className="flex items-start gap-3">
              <span className="grid h-11 w-11 place-items-center rounded-xl bg-[#e5f2eb] text-[#1e6b51]"><UploadCloud size={20} /></span>
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-[#1e6b51]">Tenant agreement registry</p>
                <h1 className="mt-1 text-2xl font-semibold tracking-[-0.03em]">Upload the governing merchant agreement</h1>
                <p className="mt-2 text-sm leading-6 text-[#66716b]">The PDF is stored privately. sl3dge extracts provenance-linked pages, then the agent may propose typed controls for human review.</p>
              </div>
            </div>
            <form
              className="mt-7 grid gap-4 sm:grid-cols-2"
              onSubmit={(event) => {
                event.preventDefault();
                const formData = new FormData(event.currentTarget);
                if (!formData.get("effective_to")) formData.delete("effective_to");
                upload.mutate(formData);
              }}
            >
              <label className="grid gap-1.5 text-xs font-medium">Merchant name<input name="merchant" required maxLength={200} className="rounded-xl border border-[#dfe4de] bg-white px-3 py-2.5 outline-none focus:border-[#1e6b51]" /></label>
              <label className="grid gap-1.5 text-xs font-medium">Agreement title<input name="title" required maxLength={240} className="rounded-xl border border-[#dfe4de] bg-white px-3 py-2.5 outline-none focus:border-[#1e6b51]" /></label>
              <label className="grid gap-1.5 text-xs font-medium">Effective from<input name="effective_from" type="date" required className="rounded-xl border border-[#dfe4de] bg-white px-3 py-2.5 outline-none focus:border-[#1e6b51]" /></label>
              <label className="grid gap-1.5 text-xs font-medium">Effective to <span className="font-normal text-[#7b857f]">(optional)</span><input name="effective_to" type="date" className="rounded-xl border border-[#dfe4de] bg-white px-3 py-2.5 outline-none focus:border-[#1e6b51]" /></label>
              <label className="grid gap-1.5 text-xs font-medium sm:col-span-2">Agreement PDF<input name="file" type="file" accept="application/pdf,.pdf" required className="rounded-xl border border-dashed border-[#cfd8d1] bg-[#f8faf7] px-3 py-5 text-xs file:mr-3 file:rounded-lg file:border-0 file:bg-[#e5f2eb] file:px-3 file:py-2 file:font-semibold file:text-[#1e6b51]" /></label>
              {upload.isError ? <p role="alert" className="text-xs text-[#b34a25] sm:col-span-2">{upload.error.message}</p> : null}
              <button type="submit" disabled={upload.isPending} className="flex items-center justify-center gap-2 rounded-xl bg-[#112a2b] px-4 py-3 text-sm font-medium text-white disabled:opacity-60 sm:col-span-2">
                {upload.isPending ? <LoaderCircle size={15} className="animate-spin" /> : <UploadCloud size={15} />} Upload and extract agreement
              </button>
            </form>
            {DEMO_MODE ? <p className="mt-4 text-center text-[10px] text-[#7a847e]">The seeded NovaCart agreement normally appears after loading the demo.</p> : null}
          </section>
        </main>
      </AppShell>
    );
  }
  if (!proposals.data) {
    return <AppShell><main className="p-8">Agreement proposals could not be loaded.</main></AppShell>;
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

        {extract.isError ? <p role="alert" className="mb-5 rounded-xl border border-[#efc6b3] bg-[#fff7f2] px-4 py-3 text-xs text-[#a9431f]">{extract.error.message}</p> : null}

        <section className="panel mb-6 rounded-2xl p-5">
          <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
            <div className="flex items-start gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-[#e5f2eb] text-[#1e6b51]"><FileText size={18} /></span><div><h2 className="text-sm font-semibold">{agreement.title}</h2><p className="mt-1 text-xs text-[#6c7771]">{agreement.merchant} · Effective {agreement.effective_from}</p></div></div>
            <span className="w-fit rounded-full bg-[#dff2e8] px-2.5 py-1 text-[10px] font-bold text-[#1e6b51]">{agreement.status}</span>
          </div>
          <div className="mt-4 grid gap-3 border-t border-[#e4e8e2] pt-4 text-[10px] text-[#6d7872] sm:grid-cols-3"><div><span className="block uppercase tracking-[0.1em]">Source</span><strong className="mt-1 block text-xs text-[#202b26]">{agreement.source_type}</strong></div><div><span className="block uppercase tracking-[0.1em]">Clauses indexed</span><strong className="mt-1 block text-xs text-[#202b26]">{agreement.clauses.length}</strong></div><div><span className="block uppercase tracking-[0.1em]">Content fingerprint</span><strong className="mt-1 block truncate font-mono text-xs text-[#202b26]">{agreement.content_hash}</strong></div></div>
        </section>

        <section className="mb-6 grid gap-5 xl:grid-cols-[0.8fr_1.2fr]">
          <div className="panel overflow-hidden rounded-2xl">
            <div className="border-b border-[#e2e5df] px-5 py-4"><h2 className="text-sm font-semibold">Agreement clauses</h2><p className="mt-1 text-xs text-[#78827d]">Exact source text and page provenance</p></div>
            <div className="divide-y divide-[#e8ebe6]">{agreement.clauses.map((clause) => <div key={clause.id} className="p-4"><div className="flex items-center justify-between"><p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[#1e6b51]">Clause {clause.reference} · Page {clause.page}</p><span className="text-[9px] text-[#7a847e]">{clause.effective_from}</span></div><h3 className="mt-1.5 text-xs font-semibold">{clause.heading}</h3><p className="mt-2 text-[11px] leading-5 text-[#66716b]">{clause.text}</p></div>)}</div>
          </div>

          <div className="space-y-3">
            <div className="flex items-end justify-between"><div><h2 className="text-sm font-semibold">Structured control proposals</h2><p className="mt-1 text-xs text-[#78827d]">Every parameter points back to a clause</p></div><span className="text-[10px] font-semibold text-[#1e6b51]">{proposals.data.length} extracted</span></div>
            {proposals.data.map((proposal) => {
              const control = proposal.proposed_control;
              const clause = clauses.get(proposal.clause_id);
              return <div key={proposal.id} className={`rounded-xl border p-4 ${proposal.status === "DRAFT" ? "border-[#efc6b3] bg-[#fff8f4]" : "border-[#dbe3dc] bg-white"}`}>
                <div className="flex items-start justify-between gap-4"><div><p className="text-[9px] font-bold uppercase tracking-[0.13em] text-[#68746d]">{control.logical_control_key} · v{control.version}</p><h3 className="mt-1 text-sm font-semibold">{control.name}</h3><p className="mt-1 text-xs text-[#66716b]">{control.expected} · {control.scope}</p></div><span className={`rounded-full px-2 py-1 text-[9px] font-bold ${proposal.status === "APPROVED" ? "bg-[#dff2e8] text-[#1e6b51]" : "bg-[#ffe5d8] text-[#bd4e24]"}`}>{proposal.status}</span></div>
                <div className="mt-3 grid gap-3 rounded-lg bg-[#f5f7f3] p-3 text-[10px] sm:grid-cols-2"><div><span className="text-[#7a847e]">Parameters</span><p className="mt-1 font-mono font-semibold">{JSON.stringify(control.parameters)}</p></div><div><span className="text-[#7a847e]">Applicability</span><p className="mt-1 font-mono font-semibold">{control.conditions.join(" · ")}</p></div></div>
                <div className="mt-3 flex items-center gap-2 text-[10px] text-[#65716b]"><span className="font-semibold text-[#1e6b51]">Clause {clause?.reference}</span><ArrowRight size={11} /><span>{control.id}</span><span className="ml-auto">{formatPercent(proposal.confidence, 0)} extraction confidence</span></div>
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
