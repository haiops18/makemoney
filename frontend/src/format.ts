export function formatUsd(value: string | number | undefined, missing = "No verified data"): string {
  if (value === undefined) return missing;
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Number(value));
}
