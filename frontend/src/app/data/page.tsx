"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowRight, Database, FileUp, KeyRound, LoaderCircle, RefreshCw, ShieldCheck, WalletCards } from "lucide-react";
import Link from "next/link";

import { AppShell } from "@/components/app-shell";
import { api } from "@/lib/api";

export default function DataSourcesPage() {
  const status = useQuery({ queryKey: ["razorpay-status"], queryFn: api.razorpayStatus });
  const sync = useMutation({ mutationFn: api.syncRazorpay });
  return <AppShell><main className="mx-auto max-w-[1160px] px-5 py-8 md:px-8 md:py-10">
    <div className="mb-8"><p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#1e6b51]">Ingestion</p><h1 className="text-3xl font-semibold tracking-[-0.035em]">Choose a financial data source</h1><p className="mt-2 text-sm text-[#66716b]">Every source normalizes into the same financial event graph and deterministic control pipeline.</p></div>
    <section className="mb-6 grid gap-4 md:grid-cols-3">
      <SourceCard icon={Database} title="NovaCart Demo Dataset" description="Seeded 500-payment run with hidden ground truth and stable proof cases." badge="ACTIVE"><Link href="/" className="mt-5 flex items-center gap-2 text-xs font-semibold text-[#1e6b51]">Open demo run <ArrowRight size={13} /></Link></SourceCard>
      <SourceCard icon={WalletCards} title="Razorpay Test Account" description="Read-only payment, refund, settlement and reconciliation ingestion." badge={status.data?.configured ? "CONFIGURED" : "NOT CONFIGURED"}><button onClick={() => sync.mutate()} disabled={!status.data?.configured || sync.isPending} className="mt-5 flex items-center gap-2 rounded-lg bg-[#112a2b] px-3 py-2 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-45">{sync.isPending ? <LoaderCircle size={13} className="animate-spin" /> : <RefreshCw size={13} />} Sync Razorpay</button></SourceCard>
      <SourceCard icon={FileUp} title="Upload Files" description="Upload orders, payments, settlements, bank, refunds and chargebacks." badge="MANUAL"><button className="mt-5 rounded-lg border border-[#d6ddd7] bg-white px-3 py-2 text-xs font-semibold text-[#4e5c55]">Choose files</button></SourceCard>
    </section>

    <section className="panel overflow-hidden rounded-2xl">
      <div className="flex flex-col justify-between gap-3 border-b border-[#e2e5df] px-5 py-4 sm:flex-row sm:items-center"><div><h2 className="flex items-center gap-2 text-sm font-semibold"><WalletCards size={16} className="text-[#1e6b51]" /> Razorpay read-only connector</h2><p className="mt-1 text-xs text-[#78827d]">Actual behaviour enters sl3dge; approved controls still define expected behaviour.</p></div><span className={`w-fit rounded-full px-2.5 py-1 text-[10px] font-bold ${status.data?.configured ? "bg-[#dff2e8] text-[#1e6b51]" : "bg-[#eceeed] text-[#68736d]"}`}>{status.data?.configured ? "CONNECTED · TEST MODE" : "BACKEND CREDENTIALS REQUIRED"}</span></div>
      <div className="p-5">
        {!status.data?.configured && <div className="mb-5 flex items-start gap-3 rounded-xl border border-[#e1e5df] bg-[#f7f8f5] p-4"><KeyRound size={18} className="mt-0.5 text-[#5d6b64]" /><div><p className="text-xs font-semibold">Configure credentials on the backend</p><p className="mt-1 text-[11px] leading-5 text-[#68736d]">Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in the backend environment. Secrets are never requested by or returned to this browser.</p></div></div>}
        {sync.data ? <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5"><SyncMetric label="Payments imported" value={sync.data.payments_imported} /><SyncMetric label="Refunds imported" value={sync.data.refunds_imported} /><SyncMetric label="Settlements imported" value={sync.data.settlements_imported} /><SyncMetric label="Recon records" value={sync.data.reconciliation_records_imported} /><SyncMetric label="Last sync" value="Complete" /></div> : <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5"><SyncMetric label="Payments imported" value="—" /><SyncMetric label="Refunds imported" value="—" /><SyncMetric label="Settlements imported" value="—" /><SyncMetric label="Recon records" value="—" /><SyncMetric label="Last sync" value={status.data?.last_sync_status ?? "—"} /></div>}
        <div className="mt-5 flex items-center gap-2 border-t border-[#e5e8e2] pt-4 text-[11px] text-[#66716b]"><ShieldCheck size={14} className="text-[#1e6b51]" /> Connector permissions are GET-only. No payment, refund or settlement action is available.</div>
      </div>
    </section>
  </main></AppShell>;
}

function SourceCard({ icon: Icon, title, description, badge, children }: { icon: typeof Database; title: string; description: string; badge: string; children: React.ReactNode }) {
  return <div className="panel rounded-2xl p-5"><div className="flex items-start justify-between gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-[#e7f2ec] text-[#1e6b51]"><Icon size={19} /></span><span className="rounded-full bg-[#eef1ec] px-2 py-1 text-[9px] font-bold text-[#66716b]">{badge}</span></div><h2 className="mt-5 text-sm font-semibold">{title}</h2><p className="mt-2 min-h-12 text-xs leading-5 text-[#6b7670]">{description}</p>{children}</div>;
}

function SyncMetric({ label, value }: { label: string; value: string | number }) {
  return <div className="rounded-xl border border-[#e2e6e0] bg-[#fafbf8] p-3"><p className="number-tabular text-lg font-semibold">{value}</p><p className="mt-1 text-[10px] text-[#758079]">{label}</p></div>;
}
