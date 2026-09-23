"use client";

// What a list shows when it has nothing in it. "No products yet." tells a
// new owner what is missing but not what the list is for or what to do
// next; this says both, and puts the first action right there.
//
// Two cases, deliberately different:
//   - nothing exists yet  → what this list holds + the button to add one
//     (only for people who may add; others get the explanation alone);
//   - a search or filter hid everything → "no results" + clear it.
//
//   <EmptyState icon={Package} title={t("…")} body={t("…")}
//               action={writable && <Button onClick={…}>…</Button>} />
//   <EmptyTableRow cols={6} … />   (inside a <tbody>)

import { SearchX } from "lucide-react";

import { useI18n } from "../../app/providers/I18nProvider";
import { Button } from "@/components/ui/kit";

export function EmptyState({ icon: Icon, title, body, action, filtered = false, onClearFilters, className = "" }) {
  const { t } = useI18n();
  const Shown = filtered ? SearchX : Icon;
  return (
    <div className={`mx-auto flex max-w-md flex-col items-center px-4 py-10 text-center ${className}`}>
      {Shown && (
        <span className="grid h-12 w-12 place-items-center rounded-full bg-accent/10 text-accent" aria-hidden="true">
          <Shown size={22} />
        </span>
      )}
      <h3 className="mt-3 font-display text-base font-semibold text-ink">
        {filtered ? t("empty.noResultsTitle") : title}
      </h3>
      {(filtered || body) && <p className="mt-1 text-sm leading-6 text-muted">{filtered ? t("empty.noResultsBody") : body}</p>}
      {filtered
        ? onClearFilters && (
            <Button variant="outline" className="mt-4" onClick={onClearFilters}>{t("empty.clearFilters")}</Button>
          )
        : action && <div className="mt-4 flex flex-wrap justify-center gap-2">{action}</div>}
    </div>
  );
}

export function EmptyTableRow({ cols, ...props }) {
  return (
    <tr>
      <td colSpan={cols} className="p-0">
        <EmptyState {...props} />
      </td>
    </tr>
  );
}
