"use client";

// A phone number as a call link with a WhatsApp link beside it — the same
// number, opened in WhatsApp. Renders "—" (or nothing) when there is no
// number, and no WhatsApp link when the number cannot be dialled
// internationally (lib/phone.js decides).
import { MessageCircle, Phone } from "lucide-react";

import { useI18n } from "@/app/providers/I18nProvider";
import { telUrl, whatsappUrl } from "@/lib/phone";

export default function PhoneLink({ phone, country, empty = "—", className = "", iconOnly = false, onContact }) {
  const { t } = useI18n();
  if (!phone) return empty ? <span className="text-muted">{empty}</span> : null;
  const tel = telUrl(phone);
  const wa = whatsappUrl(phone, country);
  return (
    <span className={`inline-flex items-center gap-2 ${className}`} dir="ltr">
      {tel ? (
        <a href={tel} onClick={() => onContact?.("call")} className="inline-flex items-center gap-1 hover:text-accent hover:underline" title={t("common.call")}>
          {!iconOnly && <Phone size={13} className="shrink-0 opacity-70" />}{phone}
        </a>
      ) : (
        <span>{phone}</span>
      )}
      {wa && (
        <a
          href={wa}
          target="_blank"
          rel="noreferrer noopener"
          onClick={() => onContact?.("whatsapp")}
          title={t("common.whatsapp")}
          aria-label={t("common.whatsapp")}
          className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#25d366]/15 text-[#128c7e] hover:bg-[#25d366]/30"
        >
          <MessageCircle size={14} />
        </a>
      )}
    </span>
  );
}
