"use client";

import { useEffect, useState } from "react";
import { Printer } from "lucide-react";

import Drawer from "@/components/ui/Drawer";
import { Button } from "@/components/ui/kit";
import { useI18n } from "../../app/providers/I18nProvider";
import DocumentView from "./DocumentView";
import PrintSheet from "./PrintSheet";

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
          <Button onClick={() => window.print()} className="w-full sm:w-auto">
            <Printer size={16} /> {t("doc.print")}
          </Button>
        ) : null
      }
    >
      {error && <p className="text-muted">{t("sales.loadDocError")}</p>}
      {!doc && !error && <p className="text-muted">{t("common.loading")}</p>}
      {doc && (
        <>
          <div className="rounded-card border border-line">
            <DocumentView doc={doc} />
          </div>
          <PrintSheet>
            <DocumentView doc={doc} />
          </PrintSheet>
        </>
      )}
    </Drawer>
  );
}
