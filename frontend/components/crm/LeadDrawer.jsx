"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, Clock, Plus } from "lucide-react";

import { crm } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import { useToast } from "@/components/ui/Toast";
import Drawer from "@/components/ui/Drawer";
import { Badge, Button, Field, Input, Select } from "@/components/ui/kit";

const STAGES = [
  ["new", "crm.stageNew"],
  ["contacted", "crm.stageContacted"],
  ["qualified", "crm.stageQualified"],
  ["proposal", "crm.stageProposal"],
  ["won", "crm.stageWon"],
  ["lost", "crm.stageLost"],
];

const EMPTY = {
  name: "",
  contact_name: "",
  email: "",
  phone: "",
  source: "",
  stage: "new",
  estimated_value: "",
  customer_group: "",
};

export default function LeadDrawer({ open, lead, groups, writable, onClose, onSaved, onGroupsChanged }) {
  const { t, language } = useI18n();
  const toast = useToast();
  const editing = Boolean(lead?.id);

  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);
  const [followups, setFollowups] = useState([]);
  const [notes, setNotes] = useState([]);
  const [newFollowup, setNewFollowup] = useState({ due_date: "", summary: "" });
  const [noteBody, setNoteBody] = useState("");

  // Segments (customer groups) had an API and translations but no screen:
  // the dropdown could only show groups nobody could create.
  const [addingSegment, setAddingSegment] = useState(false);
  const [segmentName, setSegmentName] = useState("");
  const [savingSegment, setSavingSegment] = useState(false);
  async function createSegment() {
    const name = segmentName.trim();
    if (!name) return;
    setSavingSegment(true);
    try {
      const r = await crm.createGroup({ name });
      onGroupsChanged?.();
      set("customer_group", String(r.data.id));
      setSegmentName(""); setAddingSegment(false);
      toast.success(t("crm.segmentCreated"));
    } catch {
      toast.error(t("crm.segmentError"));
    } finally {
      setSavingSegment(false);
    }
  }
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const loadActivity = useCallback(() => {
    if (!lead?.id) return;
    crm.followups({ lead: lead.id }).then((r) => setFollowups(r.data.results)).catch(() => {});
    crm.notes({ lead: lead.id }).then((r) => setNotes(r.data.results)).catch(() => {});
  }, [lead?.id]);

  useEffect(() => {
    if (!open) return;
    if (lead?.id) {
      setForm({
        name: lead.name || "",
        contact_name: lead.contact_name || "",
        email: lead.email || "",
        phone: lead.phone || "",
        source: lead.source || "",
        stage: lead.stage || "new",
        estimated_value: lead.estimated_value ?? "",
        customer_group: lead.customer_group ?? "",
      });
      loadActivity();
    } else {
      setForm(EMPTY);
      setFollowups([]);
      setNotes([]);
    }
    setNewFollowup({ due_date: "", summary: "" });
    setNoteBody("");
  }, [open, lead, loadActivity]);

  async function save() {
    setSaving(true);
    const payload = {
      ...form,
      estimated_value: form.estimated_value === "" ? "0" : form.estimated_value,
      customer_group: form.customer_group === "" ? null : form.customer_group,
    };
    try {
      if (editing) await crm.updateLead(lead.id, payload);
      else await crm.createLead(payload);
      toast.success(t("common.save"));
      onSaved?.();
      onClose();
    } catch {
      toast.error(t("common.loadError"));
    } finally {
      setSaving(false);
    }
  }

  async function addFollowup() {
    if (!newFollowup.due_date || !newFollowup.summary) return;
    try {
      await crm.createFollowup({ lead: lead.id, ...newFollowup });
      setNewFollowup({ due_date: "", summary: "" });
      loadActivity();
      onSaved?.();
    } catch {
      toast.error(t("common.loadError"));
    }
  }

  async function toggleFollowup(fu) {
    try {
      await crm.updateFollowup(fu.id, { done: !fu.done });
      loadActivity();
      onSaved?.();
    } catch {
      toast.error(t("common.loadError"));
    }
  }

  async function addNote() {
    if (!noteBody.trim()) return;
    try {
      await crm.createNote({ lead: lead.id, body: noteBody.trim() });
      setNoteBody("");
      loadActivity();
    } catch {
      toast.error(t("common.loadError"));
    }
  }

  const dateFmt = (d) =>
    d ? new Date(d).toLocaleDateString(language === "ar" ? "ar" : "en") : "";
  const isOverdue = (fu) => !fu.done && fu.due_date && new Date(fu.due_date) < new Date();

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={editing ? t("crm.editLead") : t("crm.newLead")}
      footer={
        writable && (
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button onClick={save} disabled={saving || !form.name}>
              {saving ? t("common.saving") : t("common.save")}
            </Button>
          </div>
        )
      }
    >
      <div className="space-y-4">
        <Field label={t("crm.leadName")}>
          <Input value={form.name} onChange={(e) => set("name", e.target.value)} disabled={!writable} />
        </Field>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label={t("crm.contactName")}>
            <Input value={form.contact_name} onChange={(e) => set("contact_name", e.target.value)} disabled={!writable} />
          </Field>
          <Field label={t("common.phone")}>
            <Input value={form.phone} onChange={(e) => set("phone", e.target.value)} disabled={!writable} />
          </Field>
          <Field label={t("common.email")}>
            <Input type="email" value={form.email} onChange={(e) => set("email", e.target.value)} disabled={!writable} />
          </Field>
          <Field label={t("crm.source")}>
            <Input value={form.source} onChange={(e) => set("source", e.target.value)} disabled={!writable} />
          </Field>
          <Field label={t("crm.stage")}>
            <Select value={form.stage} onChange={(e) => set("stage", e.target.value)} disabled={!writable}>
              {STAGES.map(([val, key]) => (
                <option key={val} value={val}>{t(key)}</option>
              ))}
            </Select>
          </Field>
          <Field label={t("crm.estimatedValue")}>
            <Input type="number" value={form.estimated_value} onChange={(e) => set("estimated_value", e.target.value)} disabled={!writable} />
          </Field>
        </div>
        <Field label={t("crm.segment")} hint={t("crm.segmentHint")}>
          <div className="flex gap-2">
            <Select value={form.customer_group} onChange={(e) => set("customer_group", e.target.value)} disabled={!writable}>
              <option value="">—</option>
              {(groups || []).map((g) => (
                <option key={g.id} value={g.id}>{g.name}</option>
              ))}
            </Select>
            {writable && (
              <Button type="button" variant="outline" className="shrink-0" onClick={() => setAddingSegment((v) => !v)} aria-label={t("crm.newSegment")} title={t("crm.newSegment")}>
                <Plus size={16} />
              </Button>
            )}
          </div>
          {addingSegment && (
            <div className="mt-2 flex gap-2">
              <Input value={segmentName} onChange={(e) => setSegmentName(e.target.value)} placeholder={t("crm.segmentName")} autoFocus
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); createSegment(); } }} />
              <Button type="button" className="shrink-0" onClick={createSegment} disabled={!segmentName.trim() || savingSegment}>
                {savingSegment ? t("common.saving") : t("common.save")}
              </Button>
            </div>
          )}
        </Field>

        {editing && (
          <div className="space-y-6 border-t border-line pt-5">
            {/* Follow-ups */}
            <div>
              <h3 className="mb-2 font-display text-sm font-semibold">{t("crm.followups")}</h3>
              <ul className="space-y-2">
                {followups.length === 0 && (
                  <li className="text-sm text-muted">{t("crm.noFollowups")}</li>
                )}
                {followups.map((fu) => (
                  <li key={fu.id} className="flex items-center gap-2 rounded-control border border-line px-3 py-2">
                    <button
                      onClick={() => writable && toggleFollowup(fu)}
                      className={`grid h-6 w-6 shrink-0 place-items-center rounded-full border ${
                        fu.done ? "border-ok bg-ok text-white" : "border-line text-transparent hover:border-accent"
                      }`}
                      aria-label={t("crm.markDone")}
                    >
                      <Check size={14} />
                    </button>
                    <div className="min-w-0 flex-1">
                      <div className={`truncate text-sm ${fu.done ? "text-muted line-through" : "text-ink"}`}>
                        {fu.summary}
                      </div>
                      <div className="flex items-center gap-1.5 text-xs text-muted">
                        <Clock size={12} /> {dateFmt(fu.due_date)}
                        {isOverdue(fu) && <Badge tone="danger">{t("crm.overdue")}</Badge>}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
              {writable && (
                <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                  <Input
                    type="date"
                    value={newFollowup.due_date}
                    onChange={(e) => setNewFollowup((f) => ({ ...f, due_date: e.target.value }))}
                    className="sm:w-40"
                  />
                  <Input
                    placeholder={t("crm.followupSummary")}
                    value={newFollowup.summary}
                    onChange={(e) => setNewFollowup((f) => ({ ...f, summary: e.target.value }))}
                  />
                  <Button variant="outline" onClick={addFollowup} className="shrink-0">
                    <Plus size={16} /> {t("common.add")}
                  </Button>
                </div>
              )}
            </div>

            {/* Notes / activity */}
            <div>
              <h3 className="mb-2 font-display text-sm font-semibold">{t("crm.notes")}</h3>
              {writable && (
                <div className="mb-3 flex flex-col gap-2 sm:flex-row">
                  <Input
                    placeholder={t("crm.writeNote")}
                    value={noteBody}
                    onChange={(e) => setNoteBody(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && addNote()}
                  />
                  <Button variant="outline" onClick={addNote} className="shrink-0">
                    <Plus size={16} /> {t("crm.addNote")}
                  </Button>
                </div>
              )}
              <ul className="space-y-2">
                {notes.length === 0 && (
                  <li className="text-sm text-muted">{t("crm.noNotes")}</li>
                )}
                {notes.map((n) => (
                  <li key={n.id} className="rounded-control bg-paper px-3 py-2">
                    <div className="text-sm text-ink">{n.body}</div>
                    <div className="mt-1 text-xs text-muted">
                      {n.created_by_name || ""} · {dateFmt(n.created_at)}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>
    </Drawer>
  );
}
