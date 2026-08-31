import Image from "next/image";

import evidenceMap from "../../public/brand/evidence-map.png";
import sl3dgeMark from "../../public/brand/sl3dge-mark.png";

type BrandMarkProps = {
  className?: string;
  size?: number;
};

export function BrandMark({ className = "", size = 36 }: BrandMarkProps) {
  return (
    <Image
      alt=""
      aria-hidden="true"
      className={className}
      height={size}
      sizes={`${size}px`}
      src={sl3dgeMark}
      unoptimized
      width={size}
    />
  );
}

type EvidenceMapProps = {
  className?: string;
  decorative?: boolean;
  eager?: boolean;
};

export function EvidenceMap({
  className = "",
  decorative = false,
  eager = false,
}: EvidenceMapProps) {
  return (
    <Image
      alt={
        decorative
          ? ""
          : "Payment, refund, settlement, and bank records converging into one reconciled ledger."
      }
      className={className}
      fetchPriority={eager ? "high" : "auto"}
      placeholder="blur"
      sizes="(max-width: 768px) 100vw, 56vw"
      src={evidenceMap}
      unoptimized
    />
  );
}
