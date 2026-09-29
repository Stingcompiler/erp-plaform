"use client";

// The platform's own contact details, set by the team on /platform-seo and
// read here by every visitor: a floating WhatsApp button, the footer's
// contact lines, and the channel links on the home page. Nothing
// renders until the API answers, and nothing renders when nothing is set.
import { createContext, useContext, useEffect, useState } from "react";
import { Mail, MessageCircle, Phone } from "lucide-react";

import { useI18n } from "@/app/providers/I18nProvider";
import { publicSite } from "@/lib/api";
import { telUrl, whatsappUrl } from "@/lib/phone";

const EMPTY = { whatsapp: "", phone: "", email: "" };
const CACHE_KEY = "vezano.siteContact.v1";
const SiteContactContext = createContext(EMPTY);

function readCache() {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    return raw ? { ...EMPTY, ...JSON.parse(raw) } : null;
  } catch {
    return null;
  }
}

export function SiteContactProvider({ children }) {
  const [contact, setContact] = useState(EMPTY);
  useEffect(() => {
    let cancelled = false;
    const cached = readCache();
    if (cached) setContact(cached);
    publicSite.contact()
      .then((response) => {
        if (cancelled) return;
        const next = { ...EMPTY, ...response.data };
        setContact(next);
        try { sessionStorage.setItem(CACHE_KEY, JSON.stringify(next)); } catch { /* private mode */ }
      })
      .catch(() => { /* the page is fine without it */ });
    return () => { cancelled = true; };
  }, []);
  return <SiteContactContext.Provider value={contact}>{children}</SiteContactContext.Provider>;
}

export function useSiteContact() {
  const contact = useContext(SiteContactContext);
  return {
    ...contact,
    whatsappHref: contact.whatsapp ? whatsappUrl(contact.whatsapp) : "",
    phoneHref: contact.phone ? telUrl(contact.phone) : "",
  };
}

// Bottom corner of every marketing page; the side follows the text direction.
export function WhatsAppFloat() {
  const { t } = useI18n();
  const { whatsappHref } = useSiteContact();
  if (!whatsappHref) return null;
  return (
    <a
      href={whatsappHref}
      target="_blank"
      rel="noreferrer noopener"
      aria-label={t("landing.whatsappFloat")}
      title={t("landing.whatsappFloat")}
      className="fixed bottom-5 end-5 z-40 flex h-14 items-center gap-2 rounded-full bg-[#25d366] px-4 text-white shadow-lg transition-transform hover:scale-105 print:hidden"
    >
      <MessageCircle size={24} />
      <span className="hidden text-sm font-semibold sm:inline">{t("landing.whatsappFloat")}</span>
    </a>
  );
}

// Footer column lines: WhatsApp, phone, email — only the ones that are set.
export function SiteContactLines({ className = "" }) {
  const { t } = useI18n();
  const { whatsapp, whatsappHref, phone, phoneHref, email } = useSiteContact();
  if (!whatsappHref && !phoneHref && !email) return null;
  return (
    <ul className={className}>
      {whatsappHref && <li><a href={whatsappHref} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-2 hover:text-paper" dir="ltr"><MessageCircle size={14} />{whatsapp}</a></li>}
      {phoneHref && <li><a href={phoneHref} className="inline-flex items-center gap-2 hover:text-paper" dir="ltr"><Phone size={14} />{phone}</a></li>}
      {email && <li><a href={`mailto:${email}`} className="inline-flex items-center gap-2 hover:text-paper" dir="ltr"><Mail size={14} />{email}</a></li>}
      <li className="sr-only">{t("landing.footerContact")}</li>
    </ul>
  );
}

// The platform's channels that are set, as links (WhatsApp, phone, email),
// after a short lead-in ("Or reach us directly:"). Used by the support card
// and next to the walkthrough form; renders nothing when no channel is set,
// so the page never points at a channel that does not exist.
const CHANNEL_LINK = "inline-flex min-h-11 items-center gap-2 rounded-control border border-line bg-paper px-4 py-2 text-sm font-medium text-ink hover:border-accent";

export function ContactChannels({ lead, className = "" }) {
  const { t } = useI18n();
  const { whatsapp, whatsappHref, phone, phoneHref, email } = useSiteContact();
  if (!whatsappHref && !phoneHref && !email) return null;
  return (
    <div className={className}>
      {lead && <p className="text-sm text-muted">{lead}</p>}
      <ul className="mt-2 flex flex-wrap gap-2">
        {whatsappHref && (
          <li>
            <a href={whatsappHref} target="_blank" rel="noreferrer noopener" className={CHANNEL_LINK}>
              <MessageCircle size={15} aria-hidden="true" />{t("home.supportWhatsApp")}: <bdi dir="ltr">{whatsapp}</bdi>
            </a>
          </li>
        )}
        {phoneHref && (
          <li>
            <a href={phoneHref} className={CHANNEL_LINK}>
              <Phone size={15} aria-hidden="true" />{t("home.supportPhone")}: <bdi dir="ltr">{phone}</bdi>
            </a>
          </li>
        )}
        {email && (
          <li>
            <a href={`mailto:${email}`} className={CHANNEL_LINK}>
              <Mail size={15} aria-hidden="true" />{t("home.supportEmail")}: <bdi dir="ltr">{email}</bdi>
            </a>
          </li>
        )}
      </ul>
    </div>
  );
}
