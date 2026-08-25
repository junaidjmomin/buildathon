export function formatMoney(value: string | number | null, compact = false) {
  if (value === null) return "—";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: compact ? 0 : 2,
    maximumFractionDigits: compact ? 0 : 2,
  }).format(Number(value));
}

export function formatPercent(value: string) {
  return `${(Number(value) * 100).toFixed(1)}%`;
}
