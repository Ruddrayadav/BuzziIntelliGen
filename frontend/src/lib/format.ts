export function money(value: number) {
  const formatted = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(Math.abs(value));
  return `${value < 0 ? "-" : ""}₹${formatted}`;
}

export function signedPercent(value: number) {
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

export function plainDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short" }).format(date);
}
