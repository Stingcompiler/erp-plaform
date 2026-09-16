"use client";

// The platform's own contact details, set by the team on /platform-seo and
// read here by every visitor: a floating WhatsApp button, the footer's
// contact lines, and a direct link under the walkthrough form. Nothing
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

// Under the walkthrough form: "or message us directly".
export function DirectWhatsAppLink() {
  const { t } = useI18n();
  const { whatsappHref } = useSiteContact();
  if (!whatsappHref) return null;
  return (
    <p className="mt-4 text-center text-sm text-muted">
      {t("landing.orWhatsApp")}{" "}
      <a href={whatsappHref} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 font-medium text-[#128c7e] hover:underline">
        <MessageCircle size={15} />{t("landing.whatsappDirect")}
      </a>
    </p>
  );
}
