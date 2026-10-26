/** Accessible, sortable and paginated table used across the app. */

import { useMemo, useState, type ReactNode } from "react";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, ChevronsUpDown } from "lucide-react";
import { cx, EmptyState } from "./ui";

export interface Column<T> {
  key: string;
  header: string;
  align?: "left" | "right" | "center";
  sortable?: boolean;
  /** Value used for sorting and (optionally) search matching. */
  value?: (row: T) => string | number | null | undefined;
  render?: (row: T) => ReactNode;
  className?: string;
  headerClassName?: string;
  hideBelow?: "sm" | "md" | "lg" | "xl" | "2xl";
}

interface DataTableProps<T> {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string | number;
  initialSort?: { key: string; dir: "asc" | "desc" };
  pageSize?: number;
  emptyTitle?: string;
  emptyDescription?: string;
  emptyAction?: ReactNode;
  caption?: string;
  dense?: boolean;
  onRowClick?: (row: T) => void;
  footer?: ReactNode;
}

const HIDE_CLASS = {
  sm: "hidden sm:table-cell",
  md: "hidden md:table-cell",
  lg: "hidden lg:table-cell",
  xl: "hidden xl:table-cell",
  "2xl": "hidden 2xl:table-cell",
} as const;

export function DataTable<T>({
  rows,
  columns,
  rowKey,
  initialSort,
  pageSize = 10,
  emptyTitle = "Nothing to show yet",
  emptyDescription,
  emptyAction,
  caption,
  dense = false,
  onRowClick,
  footer,
}: DataTableProps<T>) {
  const [sort, setSort] = useState<{ key: string; dir: "asc" | "desc" } | null>(initialSort ?? null);
  const [page, setPage] = useState(1);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const column = columns.find((item) => item.key === sort.key);
    if (!column?.value) return rows;
    const accessor = column.value;
    const factor = sort.dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const left = accessor(a);
      const right = accessor(b);
      if (left === right) return 0;
      if (left === null || left === undefined) return 1;
      if (right === null || right === undefined) return -1;
      if (typeof left === "number" && typeof right === "number") return (left - right) * factor;
      return String(left).localeCompare(String(right), undefined, { numeric: true }) * factor;
    });
  }, [rows, sort, columns]);

  const pages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const currentPage = Math.min(page, pages);
  const start = (currentPage - 1) * pageSize;
  const visible = sorted.slice(start, start + pageSize);

  const toggleSort = (column: Column<T>) => {
    if (!column.sortable || !column.value) return;
    setPage(1);
    setSort((current) => {
      if (current?.key !== column.key) return { key: column.key, dir: "desc" };
      if (current.dir === "desc") return { key: column.key, dir: "asc" };
      return null;
    });
  };

  if (!rows.length) {
    return <EmptyState title={emptyTitle} description={emptyDescription} action={emptyAction} />;
  }

  return (
    <div>
      <div className="overflow-x-auto scroll-thin">
        <table className="table-base">
          {caption ? <caption className="sr-only">{caption}</caption> : null}
          <thead>
            <tr>
              {columns.map((column) => {
                const active = sort?.key === column.key;
                const ariaSort = active ? (sort.dir === "asc" ? "ascending" : "descending") : "none";
                return (
                  <th
                    key={column.key}
                    scope="col"
                    aria-sort={column.sortable ? ariaSort : undefined}
                    className={cx(
                      column.align === "right" && "text-right",
                      column.align === "center" && "text-center",
                      column.hideBelow && HIDE_CLASS[column.hideBelow],
                      column.headerClassName,
                    )}
                  >
                    {column.sortable && column.value ? (
                      <button
                        type="button"
                        onClick={() => toggleSort(column)}
                        className={cx(
                          "inline-flex items-center gap-1 rounded px-0.5 py-0.5 hover:text-ink",
                          active && "text-ink",
                          column.align === "right" && "flex-row-reverse",
                        )}
                      >
                        {column.header}
                        {active ? (
                          sort.dir === "asc" ? (
                            <ArrowUp size={11} aria-hidden />
                          ) : (
                            <ArrowDown size={11} aria-hidden />
                          )
                        ) : (
                          <ChevronsUpDown size={11} className="opacity-50" aria-hidden />
                        )}
                      </button>
                    ) : (
                      column.header
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {visible.map((row) => (
              <tr
                key={rowKey(row)}
                className={cx(onRowClick && "cursor-pointer")}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                tabIndex={onRowClick ? 0 : undefined}
                onKeyDown={
                  onRowClick
                    ? (event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          onRowClick(row);
                        }
                      }
                    : undefined
                }
              >
                {columns.map((column) => (
                  <td
                    key={column.key}
                    className={cx(
                      column.align === "right" && "text-right tabular-nums",
                      column.align === "center" && "text-center",
                      column.hideBelow && HIDE_CLASS[column.hideBelow],
                      dense && "py-1.5",
                      column.className,
                    )}
                  >
                    {column.render ? column.render(row) : String(column.value?.(row) ?? "—")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2.5 text-[11px] text-muted">
        <span>
          Showing {sorted.length ? start + 1 : 0}–{Math.min(start + pageSize, sorted.length)} of {sorted.length}
        </span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            className="btn-ghost p-1"
            onClick={() => setPage((value) => Math.max(1, value - 1))}
            disabled={currentPage <= 1}
            aria-label="Previous page"
          >
            <ChevronLeft size={14} aria-hidden />
          </button>
          <span className="px-1 tabular-nums">
            Page {currentPage} / {pages}
          </span>
          <button
            type="button"
            className="btn-ghost p-1"
            onClick={() => setPage((value) => Math.min(pages, value + 1))}
            disabled={currentPage >= pages}
            aria-label="Next page"
          >
            <ChevronRight size={14} aria-hidden />
          </button>
        </div>
        {footer}
      </div>
    </div>
  );
}
