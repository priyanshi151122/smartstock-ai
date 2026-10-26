import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataTable, type Column } from "../components/DataTable";
import { KpiGrid } from "../components/KpiGrid";
import { RiskBadge } from "../components/ui";
import type { KpiCard } from "../lib/types";

interface Row {
  id: number;
  name: string;
  units: number;
}

const rows: Row[] = [
  { id: 1, name: "Alpha", units: 30 },
  { id: 2, name: "Beta", units: 10 },
  { id: 3, name: "Gamma", units: 20 },
];

const columns: Column<Row>[] = [
  { key: "name", header: "Product", value: (row) => row.name, sortable: true },
  { key: "units", header: "Units", align: "right", value: (row) => row.units, sortable: true },
];

describe("DataTable", () => {
  it("renders rows and paginates", async () => {
    render(<DataTable rows={rows} columns={columns} rowKey={(row) => row.id} pageSize={2} caption="Test table" />);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.queryByText("Gamma")).not.toBeInTheDocument();
    expect(screen.getByText(/Showing 1–2 of 3/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /next page/i }));
    expect(screen.getByText("Gamma")).toBeInTheDocument();
  });

  it("sorts descending on first click then ascending", async () => {
    render(<DataTable rows={rows} columns={columns} rowKey={(row) => row.id} pageSize={10} />);
    const unitsHeader = screen.getByRole("button", { name: /units/i });

    await userEvent.click(unitsHeader);
    let cells = within(screen.getAllByRole("row")[1]).getAllByRole("cell");
    expect(cells[0]).toHaveTextContent("Alpha"); // 30 first when desc

    await userEvent.click(unitsHeader);
    cells = within(screen.getAllByRole("row")[1]).getAllByRole("cell");
    expect(cells[0]).toHaveTextContent("Beta"); // 10 first when asc
  });

  it("shows an empty state instead of a broken table", () => {
    render(
      <DataTable
        rows={[]}
        columns={columns}
        rowKey={(row) => row.id}
        emptyTitle="Nothing here"
        emptyDescription="Import data first."
      />,
    );
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
    expect(screen.getByText("Import data first.")).toBeInTheDocument();
  });
});

describe("KpiGrid", () => {
  const cards: KpiCard[] = [
    {
      key: "revenue",
      label: "Total Revenue",
      value: 170000,
      unit: "currency",
      formatted: "\u20b91.70 L",
      change_pct: 12.5,
      comparison_label: "vs previous period",
      available: true,
    },
    {
      key: "aov",
      label: "Average Order Value",
      value: null,
      unit: "currency",
      formatted: "\u2014",
      available: false,
      note: "Requires an order/invoice column with more than one line per order.",
    },
  ];

  it("renders available metrics with their change", () => {
    render(<KpiGrid cards={cards} />);
    expect(screen.getByText("Total Revenue")).toBeInTheDocument();
    expect(screen.getByText("\u20b91.70 L")).toBeInTheDocument();
    expect(screen.getByText("+12.5%")).toBeInTheDocument();
  });

  it("labels unavailable metrics honestly instead of showing a fake zero", () => {
    render(<KpiGrid cards={cards} />);
    const aovCard = screen.getByLabelText("Average Order Value");
    expect(within(aovCard).getByText("Not available")).toBeInTheDocument();
    expect(within(aovCard).getByText(/Requires an order\/invoice column/)).toBeInTheDocument();
  });

  it("renders placeholders while loading", () => {
    const { container } = render(<KpiGrid cards={[]} loading />);
    expect(container.querySelectorAll(".skeleton").length).toBeGreaterThan(0);
  });
});

describe("RiskBadge", () => {
  it("maps risk levels to readable labels", () => {
    const { rerender } = render(<RiskBadge level="stockout" />);
    expect(screen.getByText("Stockout")).toBeInTheDocument();
    rerender(<RiskBadge level="overstock" />);
    expect(screen.getByText("Overstock")).toBeInTheDocument();
    rerender(<RiskBadge level="low" />);
    expect(screen.getByText("Healthy")).toBeInTheDocument();
  });
});
