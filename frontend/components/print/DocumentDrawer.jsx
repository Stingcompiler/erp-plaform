"use client";

import { useEffect, useState } from "react";
import { Printer } from "lucide-react";

import Drawer from "@/components/ui/Drawer";
import { Button } from "@/components/ui/kit";
import { useI18n } from "../../app/providers/I18nProvider";
import DocumentView from "./DocumentView";
import PrintSheet from "./PrintSheet";
import ReceiptView from "./ReceiptView";

const PAPERS = ["a4", "80mm", "58mm"];
const PAPER_KEY = "print.paper";

// The company sets a default paper; a till with its own roll printer
// overrides it once and the browser remembers.
function initialPaper(doc) {
  try {
    const saved = localStorage.getItem(PAPER_KEY);
    if (PAPERS.includes(saved)) return saved;
  } catch { /* private mode */ }
  const company = doc?.issuer?.receipt_paper;
  return PAPERS.includes(company) ? company : "a4";
}

/**
 * Fetches a document, previews it, and prints it.
 *
 * The preview and the print copy are the same component fed the same payload,
 * so the paper always matches what was proofread. The print copy is portalled
 * out of the drawer (see PrintSheet) because a drawer clips at one screenful.
 *
 * `fetcher` is any function returning the API promise for a document, which is
 * what lets one drawer serve invoices, credit and debit notes, receipts and
 * payment vouchers without knowing anything about them.
 */
export default function DocumentDrawer({ open, onClose, fetcher, id, title }) {
  const { t } = useI18n();
  const [doc, setDoc] = useState(null);
  const [error, setError] = useState(false);
  const [paper, setPaper] = useState("a4");
  useEffect(() => { if (doc) setPaper(initialPaper(doc)); }, [doc]);
  function choosePaper(next) {
    setPaper(next);
    try { localStorage.setItem(PAPER_KEY, next); } catch { /* per-device convenience only */ }
  }
  const View = paper === "a4" ? DocumentView : ReceiptView;

  useEffect(() => {
    if (!open || !id) return;
    setDoc(null);
    setError(false);
    fetcher(id)
      .then((r) => setDoc(r.data))
      .catch(() => setError(true));
  }, [open, id, fetcher]);

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={title || t("doc.document")}
      wide
      footer={
        doc ? (
          <div className="flex w-full flex-wrap items-center justify-between gap-2">
            <div className="flex rounded-control border border-line p-0.5 text-xs" role="group" aria-label={t("doc.paper")}>
              {PAPERS.map((p) => (
                <button
                  key={p} type="button" onClick={() => choosePaper(p)}
                  className={`tap rounded-control px-2.5 py-1.5 ${paper === p ? "bg-accent text-white" : "text-muted hover:text-ink"}`}
                >
                  {t(`doc.paper_${p}`)}
                </button>
              ))}
            </div>
            <Button onClick={() => window.print()} className="w-full sm:w-auto">
              <Printer size={16} /> {t("doc.print")}
            </Button>
          </div>
        ) : null
      }
    >
      {error && <p className="text-muted">{t("sales.loadDocError")}</p>}
      {!doc && !error && <p className="text-muted">{t("common.loading")}</p>}
      {doc && (
        <>
          <div className={`rounded-card border border-line ${paper === "a4" ? "" : "bg-paper py-4"}`}>
            <View doc={doc} paper={paper} />
          </div>
          <PrintSheet paper={paper}>
            <View doc={doc} paper={paper} />
          </PrintSheet>
        </>
      )}
    </Drawer>
  );
}
