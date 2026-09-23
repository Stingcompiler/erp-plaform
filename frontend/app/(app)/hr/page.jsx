"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Check, FileText, Lock, Plus, RefreshCw, Stethoscope, X } from "lucide-react";

import { hr, org } from "@/lib/api";
import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { useToast } from "@/components/ui/Toast";
import { Badge, Button, Card, Field, Input, PageHeader, Select } from "@/components/ui/kit";
import Drawer from "@/components/ui/Drawer";
import EmployeeDrawer from "@/components/hr/EmployeeDrawer";
import AttendanceRegister from "@/components/hr/AttendanceRegister";
import LeaveBalances from "@/components/hr/LeaveBalances";
import LeavePolicies from "@/components/hr/LeavePolicies";
import { useConfirm } from "@/components/ui/ConfirmDialog";

const EMP_STATUS_TONE = { active: "ok", on_leave: "warn", terminated: "danger" };
const EMP_STATUS_KEY = {
  active: "hr.statusActive",
  on_leave: "hr.statusOnLeave",
  terminated: "hr.statusTerminated",
};
const APPROVAL_TONE = { pending: "warn", approved: "ok", rejected: "danger", cancelled: "muted" };
const APPROVAL_KEY = { pending: "hr.pending", approved: "hr.approved", rejected: "hr.rejected", cancelled: "hr.leaveCancelled" };
const LEAVE_TYPE_KEY = {
  annual: "hr.typeAnnual",
  casual: "hr.typeCasual",
  unpaid: "hr.typeUnpaid",
  sick: "hr.typeSick",
  other: "hr.typeOther",
};
const VIOLATION_KEY = {
  misconduct: "hr.violationMisconduct",
  absence: "hr.violationAbsence",
  tardiness: "hr.violationTardiness",
  other: "hr.violationOther",
};

function StatTile({ label, value }) {
  return (
    <Card className="p-4">
      <div className="text-sm text-muted">{label}</div>
      <div className="tabular mt-1 text-2xl font-semibold text-ink">{value}</div>
    </Card>
  );
}

function EmployeeSelect({ employees, value, onChange }) {
  const { t } = useI18n();
  return (
    <Field label={t("hr.employees")}>
      <Select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">—</option>
        {(employees || []).map((e) => (
          <option key={e.id} value={e.id}>{e.full_name}</option>
        ))}
      </Select>
    </Field>
  );
}

function LeaveDrawer({ open, sick, employees, writable, onClose, onSaved }) {
  const { t } = useI18n();
  const toast = useToast();
  const empty = { employee: "", start_date: "", end_date: "", leave_type: "annual", reason: "" };
  const [form, setForm] = useState(empty);
  const [file, setFile] = useState(null);
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    if (open) {
      setForm({ ...empty, leave_type: sick ? "sick" : "annual" });
      setFile(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, sick]);

  const isSick = form.leave_type === "sick";

  async function save() {
    setSaving(true);
    try {
      if (isSick && file) {
        const fd = new FormData();
        Object.entries(form).forEach(([k, v]) => fd.append(k, v));
        fd.append("medical_report", file);
        await hr.createLeaveMultipart(fd);
      } else {
        await hr.createLeave(form);
      }
      toast.success(t("common.save"));
      onSaved?.();
      onClose();
    } catch {
      toast.error(t("hr.saveError"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={sick ? t("hr.newSickLeave") : t("hr.newLeave")}
      footer={
        writable && (
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onClose}>{t("common.cancel")}</Button>
            <Button onClick={save} disabled={saving || !form.employee || !form.start_date || !form.end_date}>
              {saving ? t("common.saving") : t("common.save")}
            </Button>
          </div>
        )
      }
    >
      <div className="space-y-4">
        <EmployeeSelect employees={employees} value={form.employee} onChange={(v) => set("employee", v)} />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label={t("hr.startDate")}>
            <Input type="date" value={form.start_date} onChange={(e) => set("start_date", e.target.value)} />
          </Field>
          <Field label={t("hr.endDate")}>
            <Input type="date" value={form.end_date} onChange={(e) => set("end_date", e.target.value)} />
          </Field>
        </div>
        <Field label={t("hr.leaveType")}>
          <Select value={form.leave_type} onChange={(e) => set("leave_type", e.target.value)}>
            {Object.entries(LEAVE_TYPE_KEY).map(([val, key]) => (
              <option key={val} value={val}>{t(key)}</option>
            ))}
          </Select>
        </Field>
        {isSick && (
          <Field label={t("hr.medicalReport")} hint={t("hr.medicalReportHint")}>
            <Input
              type="file"
              accept="image/*,application/pdf"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
            />
          </Field>
        )}
        <Field label={t("hr.reason")}>
          <Input value={form.reason} onChange={(e) => set("reason", e.target.value)} />
        </Field>
      </div>
    </Drawer>
  );
}

function PositionDrawer({ open, position, writable, onClose, onSaved }) {
  const { t } = useI18n();
  const toast = useToast();
  const [form, setForm] = useState({ title: "", description: "", base_salary: "" });
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    if (open) setForm({ title: position?.title || "", description: position?.description || "", base_salary: position?.base_salary || "" });
  }, [open, position]);

  async function save() {
    setSaving(true);
    try {
      if (position?.id) await hr.updatePosition(position.id, { ...form, base_salary: form.base_salary || "0" });
      else await hr.createPosition({ ...form, base_salary: form.base_salary || "0" });
      toast.success(t("common.save"));
      onSaved?.();
      onClose();
    } catch {
      toast.error(t("hr.positionSaveError"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={position?.id ? t("hr.editPosition") : t("hr.newPosition")}
      footer={
        writable && (
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onClose}>{t("common.cancel")}</Button>
            <Button onClick={save} disabled={saving || !form.title}>
              {saving ? t("common.saving") : position?.id ? t("common.save") : t("hr.createPosition")}
            </Button>
          </div>
        )
      }
    >
      <div className="space-y-4">
        <Field label={t("hr.positionTitle")}>
          <Input value={form.title} onChange={(e) => set("title", e.target.value)} />
        </Field>
        <Field label={t("hr.baseSalary")}>
          <Input type="number" value={form.base_salary} onChange={(e) => set("base_salary", e.target.value)} />
        </Field>
        <Field label={t("hr.positionDesc")}>
          <Input value={form.description} onChange={(e) => set("description", e.target.value)} />
        </Field>
      </div>
    </Drawer>
  );
}

function DepartmentDrawer({ open, department, writable, onClose, onSaved }) {
  const { t } = useI18n();
  const toast = useToast();
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (open) setName(department?.name || ""); }, [open, department]);
  async function save() {
    setSaving(true);
    try {
      if (department?.id) await org.updateDepartment(department.id, { name });
      else await org.createDepartment({ name });
      toast.success(t("common.save")); onSaved?.(); onClose();
    } catch { toast.error(t("common.loadError")); } finally { setSaving(false); }
  }
  return <Drawer open={open} onClose={onClose} title={department?.id ? t("hr.editDepartment") : t("hr.newDepartment")} footer={writable && <div className="flex justify-end gap-2"><Button variant="outline" onClick={onClose}>{t("common.cancel")}</Button><Button onClick={save} disabled={saving || !name.trim()}>{saving ? t("common.saving") : t("common.save")}</Button></div>}><Field label={t("hr.departmentName")}><Input value={name} onChange={(e) => setName(e.target.value)} disabled={!writable} /></Field></Drawer>;
}

function AdvanceDrawer({ open, employees, writable, onClose, onSaved }) {
  const { t } = useI18n();
  const toast = useToast();
  const [form, setForm] = useState({ employee: "", amount: "", reason: "" });
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    if (open) setForm({ employee: "", amount: "", reason: "" });
  }, [open]);

  async function save() {
    setSaving(true);
    try {
      await hr.createSalaryAdvance(form);
      toast.success(t("common.save"));
      onSaved?.();
      onClose();
    } catch {
      toast.error(t("hr.saveError"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={t("hr.newAdvance")}
      footer={
        writable && (
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onClose}>{t("common.cancel")}</Button>
            <Button onClick={save} disabled={saving || !form.employee || !form.amount}>
              {saving ? t("common.saving") : t("common.save")}
            </Button>
          </div>
        )
      }
    >
      <div className="space-y-4">
        <EmployeeSelect employees={employees} value={form.employee} onChange={(v) => set("employee", v)} />
        <Field label={t("hr.amount")}>
          <Input type="number" value={form.amount} onChange={(e) => set("amount", e.target.value)} />
        </Field>
        <Field label={t("hr.advanceReason")}>
          <Input value={form.reason} onChange={(e) => set("reason", e.target.value)} />
        </Field>
      </div>
    </Drawer>
  );
}

function PolicyDrawer({ open, writable, onClose, onSaved }) {
  const { t } = useI18n();
  const toast = useToast();
  const [form, setForm] = useState({ name: "", violation_type: "misconduct", description: "" });
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    if (open) setForm({ name: "", violation_type: "misconduct", description: "" });
  }, [open]);

  async function save() {
    setSaving(true);
    try {
      await hr.createPolicy(form);
      toast.success(t("common.save"));
      onSaved?.();
      onClose();
    } catch {
      toast.error(t("hr.saveError"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={t("hr.newPolicy")}
      footer={
        writable && (
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onClose}>{t("common.cancel")}</Button>
            <Button onClick={save} disabled={saving || !form.name}>
              {saving ? t("common.saving") : t("hr.createPolicy")}
            </Button>
          </div>
        )
      }
    >
      <div className="space-y-4">
        <Field label={t("hr.policyName")}>
          <Input value={form.name} onChange={(e) => set("name", e.target.value)} />
        </Field>
        <Field label={t("hr.violationType")}>
          <Select value={form.violation_type} onChange={(e) => set("violation_type", e.target.value)}>
            {Object.entries(VIOLATION_KEY).map(([val, key]) => (
              <option key={val} value={val}>{t(key)}</option>
            ))}
          </Select>
        </Field>
        <Field label={t("hr.positionDesc")}>
          <Input value={form.description} onChange={(e) => set("description", e.target.value)} />
        </Field>
      </div>
    </Drawer>
  );
}

function DeductionDrawer({ open, employees, policies, writable, onClose, onSaved }) {
  const { t } = useI18n();
  const toast = useToast();
  const [form, setForm] = useState({ employee: "", policy: "", amount: "", note: "" });
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    if (open) setForm({ employee: "", policy: "", amount: "", note: "" });
  }, [open]);

  async function save() {
    setSaving(true);
    try {
      await hr.createDeduction({ ...form, policy: form.policy || null });
      toast.success(t("common.save"));
      onSaved?.();
      onClose();
    } catch {
      toast.error(t("hr.saveError"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={t("hr.newDeduction")}
      footer={
        writable && (
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onClose}>{t("common.cancel")}</Button>
            <Button onClick={save} disabled={saving || !form.employee || !form.amount}>
              {saving ? t("common.saving") : t("hr.recordDeduction")}
            </Button>
          </div>
        )
      }
    >
      <div className="space-y-4">
        <EmployeeSelect employees={employees} value={form.employee} onChange={(v) => set("employee", v)} />
        <Field label={t("hr.policy")}>
          <Select value={form.policy} onChange={(e) => set("policy", e.target.value)}>
            <option value="">—</option>
            {(policies || []).map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </Select>
        </Field>
        <Field label={t("hr.amount")}>
          <Input type="number" value={form.amount} onChange={(e) => set("amount", e.target.value)} />
        </Field>
        <Field label={t("hr.deductionNote")}>
          <Input value={form.note} onChange={(e) => set("note", e.target.value)} />
        </Field>
      </div>
    </Drawer>
  );
}

const TABS = [
  ["employees", "hr.employees"],
  ["positions", "hr.positions"],
  ["departments", "hr.departments"],
  ["attendance", "hr.attendance.tab"],
  ["leave", "hr.leaveRequests"],
  ["leave-balances", "hr.leaveBalances"],
  ["leave-policies", "hr.leavePolicies"],
  ["advances", "hr.salaryAdvances"],
  ["payroll", "hr.payroll"],
  ["policies", "hr.workPolicies"],
  ["deductions", "hr.deductions"],
];

export default function HrPage() {
  const { user, canRead, canWrite } = useAuth();
  const { t, language } = useI18n();
  const confirm = useConfirm();
  const toast = useToast();
  const writable = canWrite("hr");
  // Mirrors core.permissions.PayrollReportAccess: HR/finance oversight, but
  // a branch manager sees staff, not salaries.
  const canViewPayroll = user?.role_name !== "Branch Manager"
    && (user?.report_areas || []).some((area) => area === "hr" || area === "finance");
  const canApproveAdvances = Boolean(
    user?.is_platform_admin || [
      "Chief Financial Officer",
      "Business Owner",
      "General Manager",
      "Super Administrator",
    ].includes(user?.role_name)
  );

  const [tab, setTab] = useState("employees");
  const [employees, setEmployees] = useState([]);
  const [positions, setPositions] = useState([]);
  const [leave, setLeave] = useState([]);
  const [advances, setAdvances] = useState([]);
  const [policies, setPolicies] = useState([]);
  const [deductions, setDeductions] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [payrollRuns, setPayrollRuns] = useState([]);
  const [payrollPeriod, setPayrollPeriod] = useState(() => new Date().toISOString().slice(0, 7));
  const [loading, setLoading] = useState(true);

  const [empDrawer, setEmpDrawer] = useState({ open: false, employee: null });
  const [leaveDrawer, setLeaveDrawer] = useState({ open: false, sick: false });
  const [positionDrawer, setPositionDrawer] = useState({ open: false, position: null });
  const [departmentDrawer, setDepartmentDrawer] = useState({ open: false, department: null });
  const [advanceDrawerOpen, setAdvanceDrawerOpen] = useState(false);
  const [policyDrawerOpen, setPolicyDrawerOpen] = useState(false);
  const [deductionDrawerOpen, setDeductionDrawerOpen] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([
      hr.employees({ page: 1 }).then((r) => setEmployees(r.data.results)).catch(() => setEmployees([])),
      hr.positions().then((r) => setPositions(r.data.results)).catch(() => setPositions([])),
      hr.leave({ page: 1 }).then((r) => setLeave(r.data.results)).catch(() => setLeave([])),
      hr.salaryAdvances({ page: 1 }).then((r) => setAdvances(r.data.results)).catch(() => setAdvances([])),
      hr.policies().then((r) => setPolicies(r.data.results)).catch(() => setPolicies([])),
      hr.deductions({ page: 1 }).then((r) => setDeductions(r.data.results)).catch(() => setDeductions([])),
      org.departments().then((r) => setDepartments(r.data.results || r.data)).catch(() => setDepartments([])),
      canViewPayroll ? hr.payrollRuns().then((r) => setPayrollRuns(r.data.results || r.data)).catch(() => setPayrollRuns([])) : Promise.resolve(setPayrollRuns([])),
    ]).finally(() => setLoading(false));
  }, [canViewPayroll]);

  useEffect(() => {
    if (canRead("hr")) load();
  }, [canRead, load]);

  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get("tab");
    if (TABS.some(([key]) => key === requested) && (requested !== "payroll" || canViewPayroll)) setTab(requested);
    else if (!canViewPayroll) setTab((current) => current === "payroll" ? "employees" : current);
  }, [canViewPayroll]);

  const stats = useMemo(() => {
    const active = employees.filter((e) => e.status === "active").length;
    const onLeave = employees.filter((e) => e.status === "on_leave").length;
    const pending = leave.filter((l) => l.status === "pending").length;
    return { headcount: employees.length, active, onLeave, pending };
  }, [employees, leave]);

  const dateFmt = (d) => (d ? new Date(d).toLocaleDateString(language === "ar" ? "ar" : "en") : "—");
  const money = (v) =>
    Number(v ?? 0).toLocaleString(language === "ar" ? "ar" : "en", { minimumFractionDigits: 2 });

  async function decide(kind, id, approveFn, rejectFn) {
    try {
      await (kind === "approve" ? approveFn(id) : rejectFn(id));
      load();
    } catch (error) {
      toast.error(t(error.response?.data?.code === "insufficient_leave_balance" ? "hr.insufficientLeaveBalance" : "common.loadError"));
    }
  }

  async function createPayroll() {
    try {
      await hr.createPayrollRun(payrollPeriod);
      toast.success(t("common.save"));
      load();
    } catch {
      toast.error(t("common.loadError"));
    }
  }

  async function cancelLeave(id) {
    const reason = await confirm(t("hr.cancelLeaveConfirm"), {
      tone: "danger", input: { label: t("hr.cancelLeavePrompt"), required: true },
    });
    if (reason === false) return;
    try {
      await hr.cancelLeave(id, reason.trim());
      toast.success(t("hr.leaveCancelled"));
      load();
    } catch (error) {
      const code = error.response?.data?.code;
      toast.error(t(code === "legacy_attendance" ? "hr.cancelLegacyAttendance" : code === "approved_payroll" ? "hr.cancelApprovedPayroll" : "common.loadError"));
    }
  }

  async function refreshPayroll(id) {
    try {
      await hr.refreshPayrollRun(id);
      toast.success(t("hr.payrollRefreshed"));
      load();
    } catch {
      toast.error(t("common.loadError"));
    }
  }

  function headerAction() {
    if (!writable) return null;
    if (tab === "leave-balances" || tab === "leave-policies" || tab === "attendance") return null;
    const map = {
      employees: () => setEmpDrawer({ open: true, employee: null }),
      positions: () => setPositionDrawer({ open: true, position: null }),
      departments: () => setDepartmentDrawer({ open: true, department: null }),
      advances: () => setAdvanceDrawerOpen(true),
      policies: () => setPolicyDrawerOpen(true),
      deductions: () => setDeductionDrawerOpen(true),
    };
    const label = {
      employees: "hr.newEmployee",
      positions: "hr.newPosition",
      departments: "hr.newDepartment",
      advances: "hr.newAdvance",
      policies: "hr.newPolicy",
      deductions: "hr.newDeduction",
    };
    if (tab === "leave") {
      return (
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setLeaveDrawer({ open: true, sick: true })}>
            <Stethoscope size={16} /> {t("hr.newSickLeave")}
          </Button>
          <Button onClick={() => setLeaveDrawer({ open: true, sick: false })}>
            <Plus size={16} /> {t("hr.newLeave")}
          </Button>
        </div>
      );
    }
    if (tab === "payroll") {
      return <div className="flex gap-2"><Input type="month" value={payrollPeriod} onChange={(e) => setPayrollPeriod(e.target.value)} /><Button onClick={createPayroll}><Plus size={16} /> {t("hr.createPayroll")}</Button></div>;
    }
    return (
      <Button onClick={map[tab]}>
        <Plus size={16} /> {t(label[tab])}
      </Button>
    );
  }

  if (!canRead("hr")) {
    return (
      <div className="mx-auto mt-16 max-w-md rounded-card border border-line bg-surface p-8 text-center">
        <Lock className="mx-auto text-muted" />
        <h1 className="mt-3 font-display text-xl font-semibold">{t("shell.noAccessTitle")}</h1>
        <p className="mt-1 text-muted">{t("hr.noAccess")}</p>
      </div>
    );
  }

  return (
    <div>
      <PageHeader title={t("hr.title")} subtitle={t("hr.subtitle")} actions={headerAction()} />

      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <StatTile label={t("hr.headcount")} value={stats.headcount} />
        <StatTile label={t("hr.activeStaff")} value={stats.active} />
        <StatTile label={t("hr.onLeave")} value={stats.onLeave} />
        <StatTile label={t("hr.pendingLeave")} value={stats.pending} />
      </div>

      {/* Tabs */}
      <div className="mt-6 flex gap-1 overflow-x-auto border-b border-line">
        {TABS.filter(([key]) => key !== "payroll" || canViewPayroll).map(([key, labelKey]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`tap -mb-px shrink-0 border-b-2 px-4 py-2.5 text-sm font-medium transition-colors ${
              tab === key ? "border-accent text-ink" : "border-transparent text-muted hover:text-ink"
            }`}
          >
            {t(labelKey)}
          </button>
        ))}
      </div>

      {loading && <p className="py-8 text-center text-muted">{t("common.loading")}</p>}
      {tab === "attendance" && <AttendanceRegister writable={writable} />}
      {tab === "leave-balances" && <LeaveBalances writable={writable} />}
      {tab === "leave-policies" && <LeavePolicies writable={writable} />}

      {/* Employees */}
      {!loading && tab === "employees" && (
        <div className="mt-4 space-y-2">
          {employees.length === 0 && (
            <Card className="p-8 text-center text-muted">{t("hr.noEmployees")}</Card>
          )}
          {employees.map((e) => (
            <button
              key={e.id}
              onClick={() => setEmpDrawer({ open: true, employee: e })}
              className="flex w-full items-center gap-3 rounded-card border border-line bg-surface p-4 text-start shadow-card transition-colors hover:border-accent"
            >
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium text-ink">{e.full_name}</div>
                <div className="truncate text-sm text-muted">
                  {[e.department_name, e.position_title].filter(Boolean).join(" · ") || e.email || "—"}
                </div>
              </div>
              <Badge tone={EMP_STATUS_TONE[e.status]}>{t(EMP_STATUS_KEY[e.status])}</Badge>
            </button>
          ))}
        </div>
      )}

      {/* Positions */}
      {!loading && tab === "positions" && (
        <div className="mt-4 space-y-2">
          {positions.length === 0 && (
            <Card className="p-8 text-center text-muted">{t("hr.noPositions")}</Card>
          )}
          {positions.map((p) => (
            <button key={p.id} onClick={() => setPositionDrawer({ open: true, position: p })} className="flex w-full items-center gap-3 rounded-card border border-line bg-surface p-4 text-start shadow-card transition-colors hover:border-accent">
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium text-ink">{p.title}</div>
                {p.description && <div className="truncate text-sm text-muted">{p.description}</div>}
              </div>
              {Number(p.base_salary) > 0 && (
                <span className="tabular text-sm text-muted">{money(p.base_salary)}</span>
              )}
              <Badge tone="muted">{p.employee_count ?? 0} {t("hr.employeesUsing")}</Badge>
            </button>
          ))}
        </div>
      )}

      {!loading && tab === "departments" && (
        <div className="mt-4 space-y-2">
          {departments.length === 0 && <Card className="p-8 text-center text-muted">{t("hr.noDepartments")}</Card>}
          {departments.map((department) => <button key={department.id} onClick={() => setDepartmentDrawer({ open: true, department })} className="flex w-full items-center justify-between rounded-card border border-line bg-surface p-4 text-start shadow-card transition-colors hover:border-accent"><span className="font-medium text-ink">{department.name}</span><Badge tone={department.is_active ? "ok" : "muted"}>{department.is_active ? t("common.active") : t("common.inactive")}</Badge></button>)}
        </div>
      )}

      {!loading && canViewPayroll && tab === "payroll" && (
        <div className="mt-4 space-y-3">
          {payrollRuns.length === 0 && <Card className="p-8 text-center text-muted">{t("hr.noPayroll")}</Card>}
          {payrollRuns.map((run) => (
            <Card key={run.id} className="p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div><div className="font-medium text-ink">{t("hr.payrollFor", { period: run.period?.slice(0, 7) })}</div><div className="text-sm text-muted">{t("hr.payrollEmployees", { count: run.employee_count })}</div></div>
                <div className="flex items-center gap-2"><Badge tone={run.status === "approved" ? "ok" : "warn"}>{run.status === "approved" ? t("hr.approved") : t("hr.pending")}</Badge>{writable && run.status === "draft" && <Button variant="outline" onClick={() => refreshPayroll(run.id)}><RefreshCw size={15} /> {t("hr.refreshPayroll")}</Button>}{canApproveAdvances && run.status === "draft" && <Button variant="outline" onClick={() => decide("approve", run.id, hr.approvePayrollRun, hr.approvePayrollRun)}><Check size={15} /> {t("hr.approve")}</Button>}</div>
              </div>
              <div className="mt-3 divide-y divide-line border-t border-line">
                {(run.entries || []).map((entry) => <div key={entry.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm"><div><span className="font-medium text-ink">{entry.employee_name}</span><span className="text-muted"> · {entry.department_name || "—"} · {entry.position_title || "—"}</span></div><div className="tabular text-ink">{money(entry.net_salary)}</div></div>)}
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Leave */}
      {!loading && tab === "leave" && (
        <div className="mt-4 space-y-2">
          {leave.length === 0 && (
            <Card className="p-8 text-center text-muted">{t("hr.noLeave")}</Card>
          )}
          {leave.map((l) => (
            <div key={l.id} className="flex flex-wrap items-center gap-3 rounded-card border border-line bg-surface p-4 shadow-card">
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium text-ink">{l.employee_name}</div>
                <div className="flex flex-wrap items-center gap-x-2 text-sm text-muted">
                  <span>{dateFmt(l.start_date)} → {dateFmt(l.end_date)}</span>
                  <Badge tone={l.leave_type === "sick" ? "warn" : "muted"}>
                    {t(LEAVE_TYPE_KEY[l.leave_type] || "hr.typeOther")}
                  </Badge>
                  {l.has_report && (
                    <a
                      href={hr.reportUrl(l.id)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-accent hover:underline"
                    >
                      <FileText size={13} /> {t("hr.viewReport")}
                    </a>
                  )}
                </div>
              </div>
              <Badge tone={APPROVAL_TONE[l.status]}>{t(APPROVAL_KEY[l.status])}</Badge>
              {writable && l.status === "approved" && <Button variant="outline" onClick={() => cancelLeave(l.id)}>{t("hr.cancelLeave")}</Button>}
              {writable && l.status === "pending" && (
                <div className="flex gap-2">
                  <Button variant="outline" onClick={() => decide("approve", l.id, hr.approveLeave, hr.rejectLeave)}>
                    <Check size={15} /> {t("hr.approve")}
                  </Button>
                  <Button variant="outline" onClick={() => decide("reject", l.id, hr.approveLeave, hr.rejectLeave)}>
                    <X size={15} /> {t("hr.reject")}
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Salary advances */}
      {!loading && tab === "advances" && (
        <div className="mt-4 space-y-2">
          {advances.length === 0 && (
            <Card className="p-8 text-center text-muted">{t("hr.noAdvances")}</Card>
          )}
          {advances.map((a) => (
            <div key={a.id} className="flex flex-wrap items-center gap-3 rounded-card border border-line bg-surface p-4 shadow-card">
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium text-ink">{a.employee_name}</div>
                <div className="text-sm text-muted">
                  <span className="tabular">{money(a.amount)}</span>
                  {a.reason ? ` · ${a.reason}` : ""}
                </div>
              </div>
              <Badge tone={APPROVAL_TONE[a.status]}>{t(APPROVAL_KEY[a.status])}</Badge>
              {canApproveAdvances && a.status === "pending" && (
                <div className="flex gap-2">
                  <Button variant="outline" onClick={() => decide("approve", a.id, hr.approveAdvance, hr.rejectAdvance)}>
                    <Check size={15} /> {t("hr.approve")}
                  </Button>
                  <Button variant="outline" onClick={() => decide("reject", a.id, hr.approveAdvance, hr.rejectAdvance)}>
                    <X size={15} /> {t("hr.reject")}
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Work policies */}
      {!loading && tab === "policies" && (
        <div className="mt-4 space-y-2">
          {policies.length === 0 && (
            <Card className="p-8 text-center text-muted">{t("hr.noPolicies")}</Card>
          )}
          {policies.map((p) => (
            <div key={p.id} className="flex items-center gap-3 rounded-card border border-line bg-surface p-4 shadow-card">
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium text-ink">{p.name}</div>
                {p.description && <div className="truncate text-sm text-muted">{p.description}</div>}
              </div>
              <Badge tone="accent">{t(VIOLATION_KEY[p.violation_type] || "hr.violationOther")}</Badge>
            </div>
          ))}
        </div>
      )}

      {/* Deductions */}
      {!loading && tab === "deductions" && (
        <div className="mt-4 space-y-2">
          {deductions.length === 0 && (
            <Card className="p-8 text-center text-muted">{t("hr.noDeductions")}</Card>
          )}
          {deductions.map((d) => (
            <div key={d.id} className="flex flex-wrap items-center gap-3 rounded-card border border-line bg-surface p-4 shadow-card">
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium text-ink">{d.employee_name}</div>
                <div className="text-sm text-muted">
                  {d.policy_name || "—"}
                  {d.note ? ` · ${d.note}` : ""}
                </div>
              </div>
              <span className="tabular text-sm font-medium text-danger">-{money(d.amount)}</span>
            </div>
          ))}
        </div>
      )}

      <EmployeeDrawer
        open={empDrawer.open}
        employee={empDrawer.employee}
        positions={positions}
        departments={departments}
        writable={writable}
        onClose={() => setEmpDrawer({ open: false, employee: null })}
        onSaved={load}
      />
      <LeaveDrawer
        open={leaveDrawer.open}
        sick={leaveDrawer.sick}
        employees={employees}
        writable={writable}
        onClose={() => setLeaveDrawer({ open: false, sick: false })}
        onSaved={load}
      />
      <PositionDrawer
        open={positionDrawer.open}
        position={positionDrawer.position}
        writable={writable}
        onClose={() => setPositionDrawer({ open: false, position: null })}
        onSaved={load}
      />
      <DepartmentDrawer open={departmentDrawer.open} department={departmentDrawer.department} writable={writable} onClose={() => setDepartmentDrawer({ open: false, department: null })} onSaved={load} />
      <AdvanceDrawer
        open={advanceDrawerOpen}
        employees={employees}
        writable={writable}
        onClose={() => setAdvanceDrawerOpen(false)}
        onSaved={load}
      />
      <PolicyDrawer
        open={policyDrawerOpen}
        writable={writable}
        onClose={() => setPolicyDrawerOpen(false)}
        onSaved={load}
      />
      <DeductionDrawer
        open={deductionDrawerOpen}
        employees={employees}
        policies={policies}
        writable={writable}
        onClose={() => setDeductionDrawerOpen(false)}
        onSaved={load}
      />
    </div>
  );
}
