function scaledInteger(value: string | number, scale: number): bigint {
  const source = String(value).trim();
  const negative = source.startsWith("-");
  const unsigned = source.replace(/^[+-]/, "");
  const [whole = "0", fraction = ""] = unsigned.split(".");
  const kept = fraction.padEnd(scale, "0").slice(0, scale);
  const next = fraction[scale] ?? "0";
  let result = BigInt(whole || "0") * 10n ** BigInt(scale) + BigInt(kept || "0");
  if (next >= "5") result += 1n;
  return negative ? -result : result;
}

function indianGrouping(value: string): string {
  if (value.length <= 3) return value;
  const tail = value.slice(-3);
  const head = value.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",");
  return `${head},${tail}`;
}

function fixed(value: string | number, scale: number): string {
  const scaled = scaledInteger(value, scale);
  const negative = scaled < 0n;
  const digits = (negative ? -scaled : scaled).toString().padStart(scale + 1, "0");
  const whole = scale ? digits.slice(0, -scale) : digits;
  const fraction = scale ? `.${digits.slice(-scale)}` : "";
  return `${negative ? "-" : ""}${indianGrouping(whole)}${fraction}`;
}

export function formatMoney(value: string | number | null, compact = false) {
  if (value === null) return "—";
  return `₹${fixed(value, compact ? 0 : 2)}`;
}

export function formatPercent(value: string, digits = 1) {
  const scaled = scaledInteger(value, digits + 2);
  const negative = scaled < 0n;
  const absolute = (negative ? -scaled : scaled).toString().padStart(digits + 1, "0");
  const whole = digits ? absolute.slice(0, -digits) : absolute;
  const fraction = digits ? `.${absolute.slice(-digits)}` : "";
  return `${negative ? "-" : ""}${whole}${fraction}%`;
}

export function compareDecimals(left: string, right: string): number {
  const leftFraction = left.split(".")[1]?.length ?? 0;
  const rightFraction = right.split(".")[1]?.length ?? 0;
  const scale = Math.max(leftFraction, rightFraction);
  const a = scaledInteger(left, scale);
  const b = scaledInteger(right, scale);
  return a < b ? -1 : a > b ? 1 : 0;
}
