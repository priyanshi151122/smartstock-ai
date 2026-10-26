import { describe, expect, it } from "vitest";
import {
  daysBetween,
  formatCompact,
  formatCurrency,
  formatDate,
  formatNumber,
  formatPercent,
  formatRatioAsPercent,
  formatPeriodLabel,
  slugify,
} from "../lib/format";

describe("formatCurrency", () => {
  it("uses Indian compact notation for large values", () => {
    expect(formatCurrency(25_000_000)).toBe("\u20b92.50 Cr");
    expect(formatCurrency(1_700_000)).toBe("\u20b917.00 L");
  });

  it("falls back to grouped digits for small values", () => {
    expect(formatCurrency(950)).toBe("\u20b9950");
    expect(formatCurrency(12.5)).toBe("\u20b912.5");
  });

  it("returns an em dash for missing values", () => {
    expect(formatCurrency(null)).toBe("\u2014");
    expect(formatCurrency(undefined)).toBe("\u2014");
  });

  it("honours a custom symbol", () => {
    expect(formatCurrency(950, { symbol: "$", locale: "en-US" })).toBe("$950");
  });
});

describe("numeric formatting", () => {
  it("formats integers and decimals", () => {
    expect(formatNumber(1234)).toBe("1,234");
    expect(formatNumber(12.345, 2)).toBe("12.35");
    expect(formatNumber(null)).toBe("\u2014");
  });

  it("compacts large numbers", () => {
    expect(formatCompact(1500)).toBe("1.5k");
    expect(formatCompact(2_400_000)).toBe("2.4M");
  });

  it("formats signed percentages", () => {
    expect(formatPercent(12.34)).toBe("+12.3%");
    expect(formatPercent(-4)).toBe("-4.0%");
    expect(formatPercent(null)).toBe("\u2014");
  });

  it("renders WAPE ratios as percentages without a sign", () => {
    expect(formatRatioAsPercent(0.347)).toBe("34.7%");
    expect(formatRatioAsPercent(null)).toBe("\u2014");
  });
});

describe("date helpers", () => {
  it("formats ISO dates for display", () => {
    expect(formatDate("2026-01-05")).toContain("2026");
    expect(formatDate(null)).toBe("\u2014");
    expect(formatDate("not-a-date")).toBe("not-a-date");
  });

  it("labels month periods", () => {
    expect(formatPeriodLabel("2026-03", "month")).toMatch(/Mar/);
  });

  it("counts inclusive days between dates", () => {
    expect(daysBetween("2026-01-01", "2026-01-02")).toBe(2);
    expect(daysBetween(null, "2026-01-02")).toBeNull();
  });
});

describe("slugify", () => {
  it("creates URL-safe slugs", () => {
    expect(slugify("Reorder Recommendations!")).toBe("reorder-recommendations");
  });
});
