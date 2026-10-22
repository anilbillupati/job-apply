import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const PLATFORM_LABEL: Record<string, string> = { linkedin: "LinkedIn", naukri: "Naukri", indeed: "Indeed" };

export function usd(v: number | null | undefined, digits = 2) {
  return v == null ? "—" : `$${v.toFixed(digits)}`;
}

export function fmtDate(v: string | null | undefined) {
  if (!v) return "—";
  const d = new Date(v);
  return isNaN(d.getTime()) ? v : d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export function fmtDateTime(v: string | null | undefined) {
  if (!v) return "—";
  const d = new Date(v);
  return isNaN(d.getTime()) ? v : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function expRange(min: number | null, max: number | null) {
  if (min == null && max == null) return "Not stated";
  if (max == null) return `${min}+ yrs`;
  return `${min ?? 0}–${max} yrs`;
}
