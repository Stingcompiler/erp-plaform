"use client";

import { useCallback, useEffect, useState } from "react";
import { CalendarDays } from "lucide-react";

import { hr } from "@/lib/api";
import { offlineStore } from "@/lib/offlineStore";
import { useOfflineMutation } from "@/components/sync/useOfflineMutation";
import { useI18n } from "../../app/providers/I18nProvider";
import { useToast } from "@/components/ui/Toast";
import TabBar from "@/components/ui/TabBar";
import { Badge, Card, Input, Select } from "@/components/ui/kit";
import { errorText } from "@/lib/errors";
import { SkeletonRows } from "@/components/ui/Skeleton";

const STATUSES = ["present", "absent", "half_day", "leave"];
const TONE = { present: "ok", absent: "danger", half_day: "warn", leave: "accent" };
const today = () => new Date().toISOString().slice(0, 10);

async function allEmployees() {
  const rows = [];
  let page = 1;
  try {
    for (;;) {
      const { data } = await hr.employees({ page, status: "active" });
      rows.push(...data.results);
      if (!data.next) return rows;
      page += 1;
    }
  } catch (err) {
    if (err?.response || rows.length) throw err;
    // Server unreachable: the mirrored staff list still lets the day be marked.
    const local = await offlineStore.getAll("employees");
    return local.filter((e) => e.status === "active");
  }
}

/**
 * The attendance register. The model and endpoint existed since the first
 * HR release; the only writer was the leave-approval sync, so a day's
 * presence was never recorded and the payroll deductions that read it had
 * nothing to work from. Day view: one row per active employee, saved as
 * soon as a status or time changes. Month view: days per status.
 */
export default function AttendanceRegister({ writable }) {
  const { t, language } = useI18n();
  const toast = useToast();
  const mutate = useOfflineMutation();
  const [view, setView] = useState("day");
  const [day, setDay] = useState(today);
  const [month, setMonth] = useState(() => today().slice(0, 7));
  const [employees, setEmployees] = useState(null);
  const [records, setRecords] = useState({});
  const [summary, setSummary] = useState(null);
  const [busy, setBusy] = useState(null);

  useEffect(() => { allEmployees().then(setEmployees).catch(() => setEmployees([])); }, []);

  const loadDay = useCallback(() => {
    hr.attendance({ date: day, page_size: 500 })
      .then((r) => setRecords(Object.fromEntries((r.data.results ?? r.data).map((a) => [a.employee, a]))))
      .catch((err) => { if (err?.response) setRecords({}); });
  }, [day]);
  useEffect(() => { if (view === "day") loadDay(); }, [view, loadDay]);
  useEffect(() => {
    if (view !== "month") return;
    setSummary(null);
    hr.attendanceSummary(month).then((r) => setSummary(r.data)).catch(() => setSummary({ rows: [] }));
  }, [view, month]);

  async function save(employee, patch) {
    const existing = records[employee.id];
    setBusy(employee.id);
    try {
      if (existing?.id) {
        const r = await hr.updateAttendance(existing.id, patch);
        setRecords((m) => ({ ...m, [employee.id]: r.data }));
      } else {
        // One mark per employee and day; the server upserts, so a queued
        // offline mark (or a correction to it) never collides on sync.
        // A fresh id per mark: a queued record carries the id of the op that
        // created it, and reusing it would make the queue keep the old mark.
        const { id: _id, client_uuid: _cu, queued: _q, ...carried } = existing || {};
        const body = {
          employee: employee.id, date: day, status: "present", ...carried, ...patch,
          client_uuid: crypto.randomUUID(),
        };
        const r = await mutate("attendance", (payload) => hr.createAttendance(payload), body);
        if (r.queued) {
          setRecords((m) => ({ ...m, [employee.id]: { ...body, queued: true } }));
          toast.info(t("hr.attendance.queued"));
        } else {
          setRecords((m) => ({ ...m, [employee.id]: r.data }));
        }
      }
    } catch (err) {
      toast.error(errorText(err, t, "hr.attendance.saveError"));
    } finally { setBusy(null); }
  }

  const fmtMonth = (m) => new Date(`${m}-01T00:00:00`).toLocaleDateString(language === "ar" ? "ar" : "en", { month: "long", year: "numeric" });
  const marked = Object.keys(records).length;

  return (
    <Card className="mt-4">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-4">
        <h2 className="flex items-center gap-2 font-display text-lg font-semibold"><CalendarDays size={18} className="text-accent" />{t("hr.attendance.title")}</h2>
        {view === "day" ? (
          <div className="flex items-center gap-2 text-sm">
            <Input type="date" value={day} onChange={(e) => setDay(e.target.value)} className="w-44" aria-label={t("hr.attendance.day")} />
            {employees && <span className="text-muted">{t("hr.attendance.markedOf", { marked, total: employees.length })}</span>}
          </div>
        ) : (
          <Input type="month" value={month} onChange={(e) => setMonth(e.target.value)} className="w-44" aria-label={t("hr.attendance.month")} />
        )}
      </div>
      <div className="px-4 pt-3">
        <TabBar value={view} onChange={setView} tabs={[{ id: "day", label: t("hr.attendance.dayView") }, { id: "month", label: t("hr.attendance.monthView") }]} />
      </div>

      {view === "day" && (employees === null ? <SkeletonRows /> : employees.length === 0 ? (
        <p className="p-8 text-center text-muted">{t("hr.noEmployees")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="stack-sm w-full text-sm">
            <thead><tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
              <th className="px-3 py-2 text-start font-medium">{t("hr.fullName")}</th>
              <th className="px-3 py-2 text-start font-medium">{t("hr.status")}</th>
              <th className="px-3 py-2 text-start font-medium">{t("hr.attendance.checkIn")}</th>
              <th className="px-3 py-2 text-start font-medium">{t("hr.attendance.checkOut")}</th>
              <th className="px-3 py-2 text-start font-medium">{t("hr.attendance.note")}</th>
            </tr></thead>
            <tbody>{employees.map((e) => {
              const a = records[e.id];
              const locked = !writable || Boolean(a?.source_leave) || a?.status === "leave";
              return (
                <tr key={e.id} className={`border-b border-line last:border-0 ${busy === e.id ? "opacity-60" : ""}`}>
                  <td className="px-3 py-2"><div className="font-medium text-ink">{e.full_name}</div><div className="text-xs text-muted">{[e.department_name, e.position_title].filter(Boolean).join(" · ")}</div></td>
                  <td className="px-3 py-2">
                    {locked ? <Badge tone={TONE[a?.status] || "muted"}>{a ? t(`hr.attendance.status.${a.status}`) : t("hr.attendance.unmarked")}</Badge> : (
                      <div className="w-36"><Select value={a?.status || ""} onChange={(ev) => save(e, { status: ev.target.value })} aria-label={t("hr.status")}>
                        <option value="" disabled>{t("hr.attendance.unmarked")}</option>
                        {STATUSES.filter((s) => s !== "leave").map((s) => <option key={s} value={s}>{t(`hr.attendance.status.${s}`)}</option>)}
                      </Select></div>
                    )}
                  </td>
                  <td className="px-3 py-2"><Input type="time" value={a?.check_in?.slice(0, 5) || ""} disabled={locked || !a} onChange={(ev) => save(e, { check_in: ev.target.value || null })} className="w-28" aria-label={t("hr.attendance.checkIn")} /></td>
                  <td className="px-3 py-2"><Input type="time" value={a?.check_out?.slice(0, 5) || ""} disabled={locked || !a} onChange={(ev) => save(e, { check_out: ev.target.value || null })} className="w-28" aria-label={t("hr.attendance.checkOut")} /></td>
                  <td className="px-3 py-2"><Input defaultValue={a?.note || ""} key={`${e.id}-${a?.id || "new"}`} disabled={locked || !a} onBlur={(ev) => { if (a && ev.target.value !== (a.note || "")) save(e, { note: ev.target.value }); }} placeholder="—" aria-label={t("hr.attendance.note")} /></td>
                </tr>
              );
            })}</tbody>
          </table>
        </div>
      ))}

      {view === "month" && (summary === null ? <SkeletonRows /> : summary.rows.length === 0 ? (
        <p className="p-8 text-center text-muted">{t("hr.attendance.emptyMonth", { month: fmtMonth(month) })}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="stack-sm w-full text-sm">
            <thead><tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
              <th className="px-3 py-2 text-start font-medium">{t("hr.fullName")}</th>
              {STATUSES.map((s) => <th key={s} className="px-3 py-2 text-end font-medium">{t(`hr.attendance.status.${s}`)}</th>)}
            </tr></thead>
            <tbody>{summary.rows.map((r) => (
              <tr key={r.employee} className="border-b border-line last:border-0">
                <td className="px-3 py-2 font-medium text-ink">{r.employee_name}</td>
                {STATUSES.map((s) => <td key={s} className={`tabular px-3 py-2 text-end ${r[s] ? "" : "text-muted"}`}>{r[s]}</td>)}
              </tr>
            ))}</tbody>
          </table>
        </div>
      ))}
    </Card>
  );
}
