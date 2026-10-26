export type Tab = "overview" | "compare" | "unusual" | "diagnosis";
export type Granularity = "daily" | "weekly" | "monthly";
export type ProductViewMode = "revenue" | "units_top" | "units_bottom";

export const tabs: Array<{ value: Tab; label: string }> = [
  { value: "overview", label: "Overview" },
  { value: "compare", label: "Compare months" },
  { value: "unusual", label: "Unusual activity" },
  { value: "diagnosis", label: "Why profit changed" },
];

export const palette = [
  "#2563eb",
  "#60a5fa",
  "#a78bfa",
  "#34d399",
  "#fbbf24",
  "#fb7185",
  "#38bdf8",
  "#818cf8",
];
