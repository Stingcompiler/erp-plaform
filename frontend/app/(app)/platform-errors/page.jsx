"use client";

import { useCallback, useEffect, useState } from "react";
import { BugOff, CheckCircle2, ChevronDown, ChevronUp, ShieldAlert } from "lucide-react";

import { platformErrors } from "@/lib/api";
import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { Badge, Button, Card, PageHeader } from "@/components/ui/kit";

function ErrorRow({ event, onResolve }) {
  const { t, language } = useI18n();
  const [open, setOpen] = useState(false);
  const fmt = (value) => new Date(value).toLocaleString(language === "ar" ? "ar" : "en", { dateStyle: "medium", timeStyle: "short" });
  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm font-semibold" dir="ltr">{event.exc_type}</span>
            <Badge tone={event.resolved_at ? "ok" : "danger"}>
              {event.resolved_at ? t("platformErrors.resolved") : `×${event.count}`}
            </Badge>
          </div>
          <div className="mt-1 truncate font-mono text-xs text-muted" dir="ltr">{event.method} {event.path}</div>
          {event.message && <p className="mt-1 text-sm text-muted">{event.message}</p>}
          <div className="mt-1 text-xs text-muted">{t("platformErrors.lastSeen", { date: fmt(event.last_seen) })}</div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button variant="ghost" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
            {open ? <ChevronUp size={15} /> : <ChevronDown size={15} />}{t("platformErrors.trace")}
          </Button>
          {!event.resolved_at && (
            <Button variant="outline" onClick={() => onResolve(event.id)}>
              <CheckCircle2 size={15} />{t("platformErrors.resolve")}
            </Button>
          )}
        </div>
      </div>
      {open && (
        <pre className="mt-3 max-h-80 overflow-auto rounded-control bg-paper p-3 text-xs leading-relaxed" dir="ltr">{event.traceback || "—"}</pre>
      )}
    </Card>
  );
}

export default function PlatformErrorsPage() {
  const { user, can } = useAuth();
  const { t } = useI18n();
  const [rows, setRows] = useState(null);
  const [showAll, setShowAll] = useState(false);
  const [error, setError] = useState("");

  const allowed = user?.is_platform_admin && can("platform.team.view");
  const load = useCallback(() => {
    platformErrors.list(showAll)
      .then((response) => setRows(response.data.results ?? response.data))
      .catch(() => setError(t("platformErrors.loadError")));
  }, [showAll, t]);
  useEffect(() => { if (allowed) load(); }, [allowed, load]);

  const resolve = async (id) => {
    try { await platformErrors.resolve(id); load(); } catch { setError(t("platformErrors.resolveError")); }
  };

  if (!allowed) {
    return <Card className="mx-auto mt-16 max-w-md p-8 text-center"><p className="text-muted">{t("shell.noAccessBody", { module: t("nav.platformErrors") })}</p></Card>;
  }
  return (
    <div>
      <PageHeader
        title={t("platformErrors.title")}
        subtitle={t("platformErrors.subtitle")}
        actions={
          <Button variant="outline" onClick={() => setShowAll((v) => !v)}>
            {showAll ? t("platformErrors.showOpen") : t("platformErrors.showAll")}
          </Button>
        }
      />
      {error && <p role="alert" className="mb-5 rounded-control bg-danger/10 p-3 text-sm text-danger">{error}</p>}
      {rows === null ? null : rows.length ? (
        <div className="space-y-3">{rows.map((event) => <ErrorRow key={event.id} event={event} onResolve={resolve} />)}</div>
      ) : (
        <Card className="mx-auto mt-10 max-w-md p-8 text-center">
          <BugOff className="mx-auto text-ok" />
          <p className="mt-3 font-medium">{t("platformErrors.emptyTitle")}</p>
          <p className="mt-1 text-sm text-muted">{t("platformErrors.emptyBody")}</p>
        </Card>
      )}
    </div>
  );
}
