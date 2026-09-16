"use client";

// The follow-up strip on a lead or registration card: when the team last
// reached the person and how, the next follow-up date, and the team's own
// note. `onSave(patch)` persists; `onContact(channel)` is fired by the call /
// WhatsApp / email links so the reach-out is recorded without any extra
// click. Read-only members see the values and no controls.
import { useEffect, useState } from "react";
import { CalendarClock, Mail, MessageCircle, Phone, StickyNote } from "lucide-react";

import { useI18n } from "@/app/providers/I18nProvider";
import { Badge, Button, Input } from "@/components/ui/kit";
import PhoneLink from "@/components/ui/PhoneLink";

const CHANNEL_ICON = { whatsapp: MessageCircle, call: Phone, email: Mail };

// datetime-local wants local time without zone; the API speaks ISO/UTC.
function toLocalInput(value) {
  if (!value) return "";
  const date = new Date(value);
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
function fromLocalInput(value) {
  return value ? new Date(value).toISOString() : null;
}

export function FollowUpBadge({ row }) {
  const { t } = useI18n();
  if (!row.next_follow_up_at) return null;
  const due = row.follow_up_due;
  const soon = !due && new Date(row.next_follow_up_at) - Date.now() < 24 * 60 * 60 * 1000;
  if (!due && !soon) return null;
  return <Badge tone={due ? "danger" : "warn"}>{t(due ? "followUp.overdue" : "followUp.dueSoon")}</Badge>;
}

export function ContactLinks({ phone, email, country, onContact, className = "" }) {
  const { t } = useI18n();
  return (
    <div className={`flex flex-wrap items-center gap-x-4 gap-y-1 text-sm ${className}`}>
      {phone && <PhoneLink phone={phone} country={country} className="text-muted" onContact={onContact} />}
      {email && (
        <a href={`mailto:${email}`} onClick={() => onContact?.("email")} className="inline-flex items-center gap-1.5 text-accent hover:underline" title={t("common.email")}>
          <Mail size={14} />{email}
        </a>
      )}
    </div>
  );
}

export default function FollowUpPanel({ row, canEdit, onSave, saving }) {
  const { t, language } = useI18n();
  const [note, setNote] = useState(row.internal_note || "");
  const [next, setNext] = useState(toLocalInput(row.next_follow_up_at));
  useEffect(() => {
    setNote(row.internal_note || "");
    setNext(toLocalInput(row.next_follow_up_at));
  }, [row.internal_note, row.next_follow_up_at]);

  const fmt = (value) => new Date(value).toLocaleString(language === "ar" ? "ar" : "en", { dateStyle: "medium", timeStyle: "short" });
  const dirty = note !== (row.internal_note || "") || next !== toLocalInput(row.next_follow_up_at);
  const Icon = CHANNEL_ICON[row.last_contact_channel] || Phone;

  return (
    <div className="mt-4 rounded-control border border-line bg-paper/60 p-3 text-sm">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
        <span className="inline-flex items-center gap-1">
          <Icon size={13} />
          {row.last_contacted_at
            ? t("followUp.lastContact", { channel: t(`landing.channels.${row.last_contact_channel}`), date: fmt(row.last_contacted_at) })
            : t("followUp.neverContacted")}
        </span>
        {row.next_follow_up_at && (
          <span className={`inline-flex items-center gap-1 ${row.follow_up_due ? "font-medium text-danger" : ""}`}>
            <CalendarClock size={13} />{t("followUp.next", { date: fmt(row.next_follow_up_at) })}
          </span>
        )}
      </div>
      {canEdit ? (
        <div className="mt-2 grid gap-2 sm:grid-cols-[1fr_auto_auto] sm:items-start">
          <label className="block">
            <span className="sr-only">{t("followUp.note")}</span>
            <textarea
              rows={2}
              maxLength={2000}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder={t("followUp.notePlaceholder")}
              className="w-full rounded-control border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-accent"
            />
          </label>
          <label className="block">
            <span className="sr-only">{t("followUp.nextLabel")}</span>
            <Input type="datetime-local" value={next} onChange={(event) => setNext(event.target.value)} className="w-full sm:w-52" aria-label={t("followUp.nextLabel")} />
          </label>
          <Button
            variant="outline"
            disabled={!dirty || saving}
            onClick={() => onSave({ internal_note: note, next_follow_up_at: fromLocalInput(next) })}
          >
            <StickyNote size={15} />{saving ? t("followUp.saving") : t("followUp.save")}
          </Button>
        </div>
      ) : (
        row.internal_note && <p className="mt-2 whitespace-pre-wrap text-muted">{row.internal_note}</p>
      )}
    </div>
  );
}
