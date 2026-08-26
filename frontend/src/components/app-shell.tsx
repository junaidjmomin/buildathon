"use client";

import {
  Activity,
  Boxes,
  FileCheck2,
  Gauge,
  GitBranch,
  LayoutDashboard,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const items = [
  { label: "Overview", icon: LayoutDashboard, href: "/" },
  { label: "Control runs", icon: Activity, href: "/" },
  { label: "Controls", icon: ShieldCheck, href: "/runs/RUN_NOVACART_AUG_2026/coverage" },
  { label: "Exceptions", icon: TriangleAlert, href: "/exceptions" },
  { label: "Root causes", icon: GitBranch, href: "/root-causes/RC_MDR_01" },
  { label: "Agreements", icon: FileCheck2, href: "/agreements" },
  { label: "Data sources", icon: Boxes, href: "/data" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[236px_1fr]">
      <aside className="hidden min-h-screen bg-[#112a2b] px-4 py-5 text-white lg:flex lg:flex-col">
        <Link href="/" className="mb-8 flex items-center gap-3 px-2">
          <span className="grid h-9 w-9 place-items-center rounded-[10px] bg-[#dff2e8] text-[#174b3b]">
            <Gauge size={20} strokeWidth={2.4} />
          </span>
          <span>
            <span className="block text-[21px] font-semibold leading-5 tracking-[-0.04em]">sl3dge</span>
            <span className="text-[10px] uppercase tracking-[0.18em] text-white/45">Control engine</span>
          </span>
        </Link>
        <nav className="space-y-1">
          {items.map(({ label, icon: Icon, href }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
            <Link
              key={label}
              href={href ?? "#"}
              className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-[13px] transition ${
                active ? "bg-white/10 font-medium text-white" : "text-white/58 hover:bg-white/5 hover:text-white"
              }`}
            >
              <Icon size={16} /> {label}
            </Link>
            );
          })}
        </nav>
        <div className="mt-auto rounded-xl border border-white/10 bg-white/[0.055] p-3.5">
          <div className="mb-2 flex items-center gap-2 text-xs font-medium">
            <Sparkles size={14} className="text-[#95d6b8]" /> Verification principle
          </div>
          <p className="text-[11px] leading-5 text-white/50">AI proposes. Controls calculate. Evidence decides.</p>
        </div>
      </aside>
      <div className="min-w-0">
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-[#dfe2db] bg-[#f3f4ef]/90 px-5 backdrop-blur-xl md:px-8">
          <div className="flex items-center gap-2 text-xs text-[#66716b]">
            <ShieldCheck size={15} className="text-[#1e6b51]" />
            <span className="font-medium text-[#17211d]">NovaCart India</span><span>·</span><span>August 2026</span>
          </div>
          <div className="flex items-center gap-2 rounded-full border border-[#cdd7cf] bg-white px-3 py-1.5 text-[11px] font-medium text-[#1e6b51]">
            <span className="h-1.5 w-1.5 rounded-full bg-[#2a9b6a]" /> Deterministic engine ready
          </div>
        </header>
        {children}
      </div>
    </div>
  );
}
