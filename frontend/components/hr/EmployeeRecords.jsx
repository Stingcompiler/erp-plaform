"use client";

import { useCallback, useEffect, useState } from "react";
import { ExternalLink, Plus, Star, Trash2 } from "lucide-react";

import { hr } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import { useToast } from "@/components/ui/Toast";
import TabBar from "@/components/ui/TabBar";
import { Button, Field, Input, Select, controlClass } from "@/components/ui/kit";
import { errorText } from "@/lib/errors";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { SkeletonLines } from "@/components/ui/Skeleton";

const today = () => new Date().toISOString().slice(0, 10);
const DOC_TYPES = ["contract", "id", "certificate", "warning", "other"];

function Stars({ value }) {
  return (
    <span className="inline-flex items-center gap-0.5" aria-label={`${value}/5`}>
      {[1, 2, 3, 4, 5].map((n) => <Star key={n} size={14} className={n <= value ? "fill-warn text-warn" : "text-line"} />)}
    </span>
  );
}

/**
 * Performance reviews and documents for one employee, shown inside the
 * employee drawer. Both models shipped with the HR module and had list and
 * create endpoints, but no screen ever read or wrote them.
 */
export default function EmployeeRecords({ employee, writable }) {
  const { t, language } = useI18n();
  const confirm = useConfirm();
  const toast = useToast();
  const [tab, setTab] = useState("reviews");
  const [reviews, setReviews] = useState(null);
  const [docs, setDocs] = useState(null);
  const [adding, setAdding] = useState(false);
  const [review, setReview] = useState({ review_date: today(), rating: 3, summary: "" });
  const [doc, setDoc] = useState({ title: "", doc_type: "contract", file_url: "", note: "" });
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    hr.performanceRecords({ employee: employee.id, page_size: 100 }).then((r) => setReviews(r.data.results ?? r.data)).catch(() => setReviews([]));
    hr.employeeDocuments({ employee: employee.id, page_size: 100 }).then((r) => setDocs(r.data.results ?? r.data)).catch(() => setDocs([]));
  }, [employee.id]);
  useEffect(() => { load(); }, [load]);

  const fail = (err, fallback) => {
    toast.error(errorText(err, t, fallback));
  };

  async function saveReview() {
    setBusy(true);
    try {
      await hr.createPerformanceRecord({ employee: employee.id, ...review, rating: Number(review.rating) });
      toast.success(t("hr.records.reviewSaved"));
      setReview({ review_date: today(), rating: 3, summary: "" }); setAdding(false); load();
    } catch (err) { fail(err, t("hr.records.saveError")); } finally { setBusy(false); }
  }
  async function saveDoc() {
    setBusy(true);
    try {
      await hr.createEmployeeDocument({ employee: employee.id, ...doc });
      toast.success(t("hr.records.docSaved"));
      setDoc({ title: "", doc_type: "contract", file_url: "", note: "" }); setAdding(false); load();
    } catch (err) { fail(err, t("hr.records.saveError")); } finally { setBusy(false); }
  }
  async function removeDoc(d) {
    if (!(await confirm(t("hr.records.removeDocConfirm", { title: d.title }), { tone: "danger" }))) return;
    try { await hr.deleteEmployeeDocument(d.id); load(); } catch (err) { fail(err, t("hr.records.saveError")); }
  }

  const fmt = (v) => new Date(`${v}`.length === 10 ? `${v}T00:00:00` : v).toLocaleDateString(language === "ar" ? "ar" : "en", { dateStyle: "medium" });

  return (
    <div className="mt-6 border-t border-line pt-4">
      <div className="flex items-center justify-between gap-2">
        <TabBar className="mb-0 flex-1" value={tab} onChange={(v) => { setTab(v); setAdding(false); }} tabs={[
          { id: "reviews", label: `${t("hr.records.reviews")}${reviews ? ` (${reviews.length})` : ""}` },
          { id: "documents", label: `${t("hr.records.documents")}${docs ? ` (${docs.length})` : ""}` },
        ]} />
        {writable && !adding && <Button variant="outline" onClick={() => setAdding(true)}><Plus size={14} />{tab === "reviews" ? t("hr.records.newReview") : t("hr.records.newDocument")}</Button>}
      </div>

      {adding && tab === "reviews" && (
        <div className="mt-3 space-y-3 rounded-control border border-line bg-paper p-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t("hr.records.reviewDate")}><Input type="date" value={review.review_date} onChange={(e) => setReview({ ...review, review_date: e.target.value })} /></Field>
            <Field label={t("hr.records.rating")}><Select value={review.rating} onChange={(e) => setReview({ ...review, rating: e.target.value })}>{[5, 4, 3, 2, 1].map((n) => <option key={n} value={n}>{n} / 5</option>)}</Select></Field>
          </div>
          <Field label={t("hr.records.summary")}><textarea rows={3} className={controlClass} value={review.summary} onChange={(e) => setReview({ ...review, summary: e.target.value })} /></Field>
          <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setAdding(false)}>{t("common.cancel")}</Button><Button onClick={saveReview} disabled={busy || !review.review_date}>{busy ? t("common.saving") : t("common.save")}</Button></div>
        </div>
      )}
      {adding && tab === "documents" && (
        <div className="mt-3 space-y-3 rounded-control border border-line bg-paper p-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t("hr.records.docTitle")}><Input value={doc.title} onChange={(e) => setDoc({ ...doc, title: e.target.value })} autoFocus /></Field>
            <Field label={t("hr.records.docType")}><Select value={doc.doc_type} onChange={(e) => setDoc({ ...doc, doc_type: e.target.value })}>{DOC_TYPES.map((k) => <option key={k} value={k}>{t(`hr.records.docTypes.${k}`)}</option>)}</Select></Field>
          </div>
          <Field label={t("hr.records.fileUrl")} hint={t("hr.records.fileUrlHint")}><Input type="url" value={doc.file_url} onChange={(e) => setDoc({ ...doc, file_url: e.target.value })} placeholder="https://" dir="ltr" /></Field>
          <Field label={t("hr.attendance.note")}><Input value={doc.note} onChange={(e) => setDoc({ ...doc, note: e.target.value })} /></Field>
          <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setAdding(false)}>{t("common.cancel")}</Button><Button onClick={saveDoc} disabled={busy || !doc.title.trim()}>{busy ? t("common.saving") : t("common.save")}</Button></div>
        </div>
      )}

      {tab === "reviews" && (reviews === null ? <SkeletonLines /> : reviews.length === 0 ? (
        <p className="py-4 text-sm text-muted">{t("hr.records.noReviews")}</p>
      ) : (
        <ul className="mt-3 divide-y divide-line">{reviews.map((r) => (
          <li key={r.id} className="py-3 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2"><Stars value={r.rating} /><span className="text-xs text-muted">{fmt(r.review_date)}{r.reviewer_name ? ` · ${r.reviewer_name}` : ""}</span></div>
            {r.summary && <p className="mt-1 whitespace-pre-wrap text-ink">{r.summary}</p>}
          </li>
        ))}</ul>
      ))}
      {tab === "documents" && (docs === null ? <SkeletonLines /> : docs.length === 0 ? (
        <p className="py-4 text-sm text-muted">{t("hr.records.noDocuments")}</p>
      ) : (
        <ul className="mt-3 divide-y divide-line">{docs.map((d) => (
          <li key={d.id} className="flex items-center gap-3 py-3 text-sm">
            <div className="min-w-0 flex-1">
              <div className="font-medium text-ink">{d.title} <span className="text-xs font-normal text-muted">· {DOC_TYPES.includes(d.doc_type) ? t(`hr.records.docTypes.${d.doc_type}`) : d.doc_type || t("hr.records.docTypes.other")}</span></div>
              <div className="text-xs text-muted">{fmt(d.created_at)}{d.uploaded_by_name ? ` · ${d.uploaded_by_name}` : ""}{d.note ? ` · ${d.note}` : ""}</div>
            </div>
            {d.file_url && <a href={d.file_url} target="_blank" rel="noopener noreferrer" className="text-accent" aria-label={t("hr.records.open")}><ExternalLink size={15} /></a>}
            {writable && <button onClick={() => removeDoc(d)} className="text-muted hover:text-danger" aria-label={t("common.remove")}><Trash2 size={15} /></button>}
          </li>
        ))}</ul>
      ))}
    </div>
  );
}
