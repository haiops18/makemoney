export function formatUsd(value: string | number | undefined): string {
  if (value === undefined) return "Chưa có dữ liệu";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Number(value));
}
